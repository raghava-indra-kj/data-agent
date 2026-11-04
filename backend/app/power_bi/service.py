from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import timedelta
from urllib.parse import urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError
from app.core.time import utc_now
from app.data_sources.models import DataSource
from app.power_bi.auth import acquire_token, require_enabled
from app.power_bi.mcp_client import content_values, fabric_client, walk
from app.power_bi.models import MicrosoftConnection, PowerBIMetadata, PowerBIReport, PowerBISource
from app.power_bi.schemas import EmbedConfiguration, PowerBICreate, ReportCandidate


def guid(value: object) -> str | None:
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        return None


def report_url(value: str) -> str:
    parsed = urlparse(value)
    try:
        port = parsed.port
    except ValueError as exc:
        raise AppError("POWER_BI_URL_INVALID", "The report URL is invalid.", 422) from exc
    if (
        parsed.scheme != "https"
        or parsed.hostname != "app.powerbi.com"
        or parsed.username
        or parsed.password
        or port not in (None, 443)
        or "/reports/" not in parsed.path
    ):
        raise AppError(
            "POWER_BI_URL_INVALID", "Paste the report's app.powerbi.com browser URL.", 422
        )
    return value


def identity(payload: dict[str, object], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        values = {
            result
            for value in walk(content_values(payload))
            if isinstance(value, dict) and (result := guid(value.get(key)))
        }
        if len(values) > 1:
            raise AppError(
                "POWER_BI_IDENTITY_AMBIGUOUS",
                "Power BI returned multiple identities. Select a specific report.",
                422,
            )
        if values:
            return values.pop()
    return None


async def rest_report(token: str, report_id: str, workspace_id: str | None) -> dict[str, object]:
    prefix = f"groups/{uuid.UUID(workspace_id)}/" if workspace_id else ""
    url = f"https://api.powerbi.com/v1.0/myorg/{prefix}reports/{uuid.UUID(report_id)}"
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
            response = await client.get(url, headers={"Authorization": f"Bearer {token}"})
        if response.status_code in (401, 403, 404):
            raise AppError(
                "POWER_BI_REPORT_UNAVAILABLE",
                "This report is unavailable to your Microsoft account. Check access or reconnect.",
                403,
            )
        if response.status_code == 429:
            raise AppError("POWER_BI_THROTTLED", "Power BI is busy. Please retry shortly.", 429)
        response.raise_for_status()
        value = response.json()
        if not isinstance(value, dict) or not guid(value.get("datasetId")):
            raise AppError(
                "POWER_BI_REPORT_UNSUPPORTED",
                "Select a published Power BI report with a semantic model.",
                422,
            )
        return value
    except (httpx.HTTPError, ValueError) as exc:
        raise AppError(
            "POWER_BI_UNAVAILABLE", "Power BI could not be reached. Please retry.", 502
        ) from exc


class PowerBIService:
    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
    ):
        self.session, self.settings = session, settings
        self.organization_id, self.user_id = organization_id, user_id

    async def token(self):
        return await acquire_token(self.settings, self.organization_id, self.user_id)

    async def current_identity(self) -> dict[str, str]:
        require_enabled(self.settings)
        connection = await self.session.scalar(
            select(MicrosoftConnection).where(
                MicrosoftConnection.organization_id == self.organization_id,
                MicrosoftConnection.user_id == self.user_id,
                MicrosoftConnection.tenant_id == self.settings.power_bi_tenant_id,
                MicrosoftConnection.status == "connected",
            )
        )
        if connection is None:
            raise AppError(
                "POWER_BI_RECONNECT_REQUIRED", "Connect your Microsoft account to continue.", 409
            )
        return {"tenant_id": connection.tenant_id, "object_id": connection.object_id}

    async def require_identity(self, expected: dict[str, str] | None) -> None:
        if not expected or expected != await self.current_identity():
            raise AppError(
                "POWER_BI_ACCOUNT_CHANGED",
                "Reconnect the Microsoft account used for this conversation, "
                "or start a new conversation.",
                409,
            )

    async def resolve(self, url: str) -> ReportCandidate:
        report_url(url)
        token, _, _ = await self.token()
        async with fabric_client(self.settings, token) as client:
            resolved = await client.call("ResolveFabricItem", {"fabricItemId": url})
            report_id = identity(resolved, ("fabricItemId", "reportObjectId", "reportId", "id"))
            if report_id is None:
                raise AppError(
                    "POWER_BI_REPORT_UNSUPPORTED", "Fabric IQ could not resolve this report.", 422
                )
            metadata = await client.call("GetReportMetadata", {"reportObjectId": report_id})
        workspace_id = identity(resolved, ("workspaceId",)) or identity(
            metadata, ("workspaceId", "groupId")
        )
        # Ordinary browser URLs identify the location even if MCP omits it for My Workspace.
        if not workspace_id:
            match = re.search(r"/groups/([0-9a-fA-F-]{36})/", urlparse(url).path)
            workspace_id = guid(match[1]) if match else None
        report = await rest_report(token, report_id, workspace_id)
        canonical = f"https://app.powerbi.com/groups/{workspace_id or 'me'}/reports/{report_id}"
        return ReportCandidate(
            report_id=report_id,
            workspace_id=workspace_id,
            semantic_model_id=str(report["datasetId"]),
            name=str(report.get("name") or "Power BI report"),
            web_url=canonical,
        )

    async def discover(self, query: str) -> list[dict[str, str]]:
        token, _, _ = await self.token()
        async with fabric_client(self.settings, token) as client:
            result = await client.call(
                "DiscoverArtifacts", {"searchQuery": query, "maxResults": 25}
            )
        candidates: dict[str, dict[str, str]] = {}
        for item in walk(content_values(result)):
            if not isinstance(item, dict):
                continue
            kind = str(item.get("artifactType", item.get("itemType", item.get("type", "")))).lower()
            url = next(
                (
                    v
                    for k in ("webUrl", "url", "artifactUrl")
                    if isinstance(v := item.get(k), str) and "/reports/" in v
                ),
                None,
            )
            if not url and "report" in kind:
                report_id = next(
                    (
                        v
                        for key in ("fabricItemId", "artifactId", "id", "objectId")
                        if (v := guid(item.get(key)))
                    ),
                    None,
                )
                if report_id:
                    workspace = guid(item.get("workspaceId")) or "me"
                    url = f"https://app.powerbi.com/groups/{workspace}/reports/{report_id}"
            if url:
                try:
                    report_url(url)
                except AppError:
                    continue
                candidates[url] = {
                    "name": str(item.get("name", item.get("displayName", "Power BI report"))),
                    "web_url": url,
                }
        return list(candidates.values())[:25]

    async def create(self, payload: PowerBICreate) -> DataSource:
        candidate = await self.resolve(payload.report_url)
        tenant = str(self.settings.power_bi_tenant_id)
        binding = await self.session.scalar(
            select(PowerBIReport).where(
                PowerBIReport.organization_id == self.organization_id,
                PowerBIReport.tenant_id == tenant,
                PowerBIReport.report_id == candidate.report_id,
            )
        )
        details = await self.session.scalar(
            select(PowerBISource).where(
                PowerBISource.organization_id == self.organization_id,
                PowerBISource.tenant_id == tenant,
                PowerBISource.semantic_model_id == candidate.semantic_model_id,
            )
        )
        if binding:
            if details is None or binding.data_source_id != details.data_source_id:
                raise AppError(
                    "POWER_BI_REPORT_REBOUND",
                    "The report now uses another model. Register it as an explicit replacement.",
                    409,
                )
            return await self.session.get(DataSource, binding.data_source_id)
        if details:
            source = await self.session.get(DataSource, details.data_source_id)
        else:
            source = DataSource(
                organization_id=self.organization_id,
                name=payload.name.strip(),
                kind="powerbi",
                display_type="powerbi",
                status="active",
                config={"connector": "fabric_iq"},
                created_by=self.user_id,
            )
            self.session.add(source)
            try:
                await self.session.flush()
            except IntegrityError as exc:
                await self.session.rollback()
                raise AppError(
                    "POWER_BI_SOURCE_EXISTS",
                    "A source with this name already exists. Use another name.",
                    409,
                ) from exc
            self.session.add(
                PowerBISource(
                    data_source_id=source.id,
                    organization_id=self.organization_id,
                    tenant_id=tenant,
                    semantic_model_id=candidate.semantic_model_id,
                )
            )
        self.session.add(
            PowerBIReport(
                organization_id=self.organization_id,
                data_source_id=source.id,
                tenant_id=tenant,
                report_id=candidate.report_id,
                workspace_id=candidate.workspace_id,
                name=candidate.name,
                web_url=candidate.web_url,
                embedding_enabled=payload.embedding_enabled,
            )
        )
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise AppError(
                "POWER_BI_SOURCE_EXISTS",
                "A source with this name or report already exists. Refresh and try again.",
                409,
            ) from exc
        return source

    async def source(self, source_id: uuid.UUID) -> tuple[DataSource, PowerBISource]:
        require_enabled(self.settings)
        row = (
            await self.session.execute(
                select(DataSource, PowerBISource)
                .join(PowerBISource, PowerBISource.data_source_id == DataSource.id)
                .where(
                    DataSource.id == source_id,
                    DataSource.organization_id == self.organization_id,
                    PowerBISource.tenant_id == self.settings.power_bi_tenant_id,
                )
            )
        ).first()
        if row is None or row[0].status != "active":
            raise AppError(
                "POWER_BI_SOURCE_UNAVAILABLE", "The Power BI source is unavailable.", 404
            )
        return row[0], row[1]

    async def reports(self, source_id: uuid.UUID) -> list[PowerBIReport]:
        await self.source(source_id)
        token, _, _ = await self.token()
        rows = (
            await self.session.scalars(
                select(PowerBIReport)
                .where(
                    PowerBIReport.organization_id == self.organization_id,
                    PowerBIReport.data_source_id == source_id,
                )
                .order_by(PowerBIReport.name)
            )
        ).all()
        allowed = []
        for report in rows:
            try:
                await self.validate_report(report, token)
                allowed.append(report)
            except AppError as exc:
                if exc.code != "POWER_BI_REPORT_UNAVAILABLE":
                    raise
        return allowed

    async def validate_report(self, report: PowerBIReport, token: str) -> dict[str, object]:
        _, source = await self.source(report.data_source_id)
        current = await rest_report(token, report.report_id, report.workspace_id)
        if guid(current.get("datasetId")) != source.semantic_model_id:
            raise AppError(
                "POWER_BI_REPORT_REBOUND",
                "This report's model has changed. An administrator must review the source binding.",
                409,
            )
        return current

    async def report(self, binding_id: uuid.UUID) -> PowerBIReport:
        report = await self.session.scalar(
            select(PowerBIReport).where(
                PowerBIReport.id == binding_id,
                PowerBIReport.organization_id == self.organization_id,
            )
        )
        if report is None:
            raise AppError("POWER_BI_REPORT_UNAVAILABLE", "Report not found.", 404)
        return report

    async def embed(self, binding_id: uuid.UUID) -> EmbedConfiguration:
        report = await self.report(binding_id)
        if not self.settings.power_bi_embedding_enabled or not report.embedding_enabled:
            raise AppError("POWER_BI_EMBED_DISABLED", "Embedding is disabled for this report.", 409)
        token, expires, _ = await self.token()
        current = await self.validate_report(report, token)
        url = str(current.get("embedUrl", ""))
        parsed = urlparse(url)
        if (
            parsed.scheme != "https"
            or parsed.hostname != "app.powerbi.com"
            or parsed.username
            or parsed.password
        ):
            raise AppError(
                "POWER_BI_EMBED_URL_INVALID", "Power BI returned an unsupported embedding URL.", 502
            )
        return EmbedConfiguration(
            report_id=report.report_id,
            embed_url=url,
            access_token=token,
            expires_at=utc_now() + timedelta(seconds=expires),
        )

    async def metadata(
        self, source_id: uuid.UUID, queries: list[str] | None = None
    ) -> dict[str, object]:
        _, source = await self.source(source_id)
        token, _, connection_id = await self.token()
        async with fabric_client(self.settings, token) as client:
            arguments: dict[str, object] = {"artifactId": source.semantic_model_id}
            if queries:
                arguments["queries"] = queries
            result = await client.call("GetSemanticModelSchema", arguments)
        content = {"content": content_values(result)}
        # Partial projections must not replace the complete snapshot.
        if not queries:
            from sqlalchemy.dialects.postgresql import insert

            fingerprint = hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()
            await self.session.execute(
                insert(PowerBIMetadata)
                .values(
                    data_source_id=source_id,
                    connection_id=connection_id,
                    content=content,
                    fingerprint=fingerprint,
                )
                .on_conflict_do_update(
                    index_elements=[PowerBIMetadata.data_source_id, PowerBIMetadata.connection_id],
                    set_={"content": content, "fingerprint": fingerprint, "updated_at": utc_now()},
                )
            )
            await self.session.commit()
        return content
