from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.models import JobArtifact
from app.audit.service import AuditService
from app.conversations.models import Message
from app.core.config import Settings
from app.core.errors import AppError
from app.data_sources.service import DataSourceService
from app.jobs.models import Job
from app.jobs.service import JobService
from app.reporting.models import Dashboard, DashboardWidget
from app.reporting.repository import ReportingRepository
from app.reporting.schemas import (
    DashboardCreate,
    DashboardResponse,
    DashboardUpdate,
    DashboardWidgetCreate,
    DashboardWidgetResponse,
    DashboardWidgetUpdate,
)


class ReportingService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.repo = ReportingRepository(session)

    async def create_dashboard(
        self, *, organization_id: uuid.UUID, user_id: uuid.UUID, payload: DashboardCreate
    ) -> Dashboard:
        item = Dashboard(
            organization_id=organization_id,
            title=payload.title,
            description=payload.description,
            created_by=user_id,
        )
        self.repo.add_dashboard(item)
        try:
            await self.session.flush()
        except IntegrityError as exc:
            await self.session.rollback()
            raise AppError(
                "DASHBOARD_TITLE_EXISTS",
                "A dashboard with this title already exists in the organization.",
                409,
            ) from exc
        AuditService(self.session).record(
            organization_id=organization_id,
            user_id=user_id,
            action="dashboard.created",
            resource_type="dashboard",
            resource_id=item.id,
        )
        await self.session.commit()
        return item

    async def list_dashboards(self, organization_id: uuid.UUID) -> list[DashboardResponse]:
        rows = await self.repo.list_dashboards(organization_id)
        result: list[DashboardResponse] = []
        for item, count in rows:
            response = DashboardResponse.model_validate(item)
            response.widget_count = count
            result.append(response)
        return result

    async def require_dashboard(self, dashboard_id: uuid.UUID, organization_id: uuid.UUID) -> Dashboard:
        item = await self.repo.get_dashboard_for_org(dashboard_id, organization_id)
        if item is None:
            raise AppError("DASHBOARD_NOT_FOUND", "Dashboard not found.", 404)
        return item

    async def update_dashboard(
        self,
        *,
        dashboard_id: uuid.UUID,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        payload: DashboardUpdate,
    ) -> Dashboard:
        item = await self.require_dashboard(dashboard_id, organization_id)
        if payload.title is not None:
            title = payload.title.strip()
            if not title:
                raise AppError("DASHBOARD_TITLE_REQUIRED", "Dashboard title is required.", 400)
            item.title = title
        if payload.description is not None:
            item.description = payload.description.strip() or None
        try:
            await self.session.flush()
        except IntegrityError as exc:
            await self.session.rollback()
            raise AppError(
                "DASHBOARD_TITLE_EXISTS",
                "A dashboard with this title already exists in the organization.",
                409,
            ) from exc
        AuditService(self.session).record(
            organization_id=organization_id,
            user_id=user_id,
            action="dashboard.updated",
            resource_type="dashboard",
            resource_id=item.id,
        )
        await self.session.commit()
        return item

    async def delete_dashboard(
        self, *, dashboard_id: uuid.UUID, organization_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        item = await self.require_dashboard(dashboard_id, organization_id)
        AuditService(self.session).record(
            organization_id=organization_id,
            user_id=user_id,
            action="dashboard.deleted",
            resource_type="dashboard",
            resource_id=item.id,
        )
        await self.session.delete(item)
        await self.session.commit()

    async def add_widget(
        self,
        *,
        dashboard_id: uuid.UUID,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        payload: DashboardWidgetCreate,
    ) -> DashboardWidget:
        await self.require_dashboard(dashboard_id, organization_id)
        job = await self.session.get(Job, payload.source_job_id)
        if job is None or job.organization_id != organization_id or job.status != "succeeded":
            raise AppError("WIDGET_SOURCE_JOB_INVALID", "The source analysis is unavailable.", 400)
        sql_item = await self.repo.source_sql_for_job(payload.source_sql_execution_id, job.id)
        if sql_item is None or sql_item.status != "succeeded":
            raise AppError("WIDGET_SOURCE_SQL_INVALID", "The source SQL execution is unavailable.", 400)
        await DataSourceService(self.session, self.settings).require_for_org(
            sql_item.data_source_id, organization_id
        )
        question: str | None = None
        raw_message_id = job.input.get("user_message_id")
        if raw_message_id:
            try:
                user_message = await self.session.get(Message, uuid.UUID(str(raw_message_id)))
            except (ValueError, TypeError, AttributeError):
                user_message = None
            if user_message is not None and user_message.role == "user":
                question = user_message.content
        title = (payload.title or question or "Analysis").strip()[:240]
        if not title:
            title = "Analysis"
        await self._validate_widget_config(
            job_id=job.id,
            sql_execution_id=sql_item.id,
            widget_type=payload.widget_type,
            config=payload.visualization_config,
        )
        item = DashboardWidget(
            dashboard_id=dashboard_id,
            data_source_id=sql_item.data_source_id,
            title=title,
            widget_type=payload.widget_type,
            question=question,
            sql_text=sql_item.sql_text,
            visualization_config=payload.visualization_config,
            layout_config=payload.layout_config,
            created_from_job_id=job.id,
            created_from_sql_execution_id=sql_item.id,
            enabled=True,
        )
        self.repo.add_widget(item)
        await self.session.flush()
        AuditService(self.session).record(
            organization_id=organization_id,
            user_id=user_id,
            action="dashboard_widget.created",
            resource_type="dashboard_widget",
            resource_id=item.id,
            metadata={"dashboard_id": str(dashboard_id), "widget_type": item.widget_type},
        )
        await self.session.commit()
        return item

    async def update_widget(
        self,
        *,
        widget_id: uuid.UUID,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        payload: DashboardWidgetUpdate,
    ) -> DashboardWidget:
        item = await self.repo.get_widget_for_org(widget_id, organization_id)
        if item is None:
            raise AppError("DASHBOARD_WIDGET_NOT_FOUND", "Dashboard widget not found.", 404)
        if payload.title is not None:
            title = payload.title.strip()
            if not title:
                raise AppError("WIDGET_TITLE_REQUIRED", "Widget title is required.", 400)
            item.title = title
        if payload.visualization_config is not None:
            await self._validate_widget_config(
                job_id=item.created_from_job_id,
                sql_execution_id=item.created_from_sql_execution_id,
                widget_type=item.widget_type,
                config=payload.visualization_config,
            )
            item.visualization_config = payload.visualization_config
        if payload.layout_config is not None:
            item.layout_config = payload.layout_config
        if payload.enabled is not None:
            item.enabled = payload.enabled
        AuditService(self.session).record(
            organization_id=organization_id,
            user_id=user_id,
            action="dashboard_widget.updated",
            resource_type="dashboard_widget",
            resource_id=item.id,
        )
        await self.session.commit()
        return item

    async def delete_widget(
        self, *, widget_id: uuid.UUID, organization_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        item = await self.repo.get_widget_for_org(widget_id, organization_id)
        if item is None:
            raise AppError("DASHBOARD_WIDGET_NOT_FOUND", "Dashboard widget not found.", 404)
        AuditService(self.session).record(
            organization_id=organization_id,
            user_id=user_id,
            action="dashboard_widget.deleted",
            resource_type="dashboard_widget",
            resource_id=item.id,
        )
        await self.session.delete(item)
        await self.session.commit()

    async def enqueue_dashboard_refresh(
        self,
        *,
        dashboard_id: uuid.UUID,
        organization_id: uuid.UUID,
        requested_by: uuid.UUID,
    ) -> uuid.UUID:
        dashboard = await self.require_dashboard(dashboard_id, organization_id)
        widgets = await self.repo.list_widgets(dashboard.id)
        if not any(widget.enabled for widget in widgets):
            raise AppError(
                "DASHBOARD_HAS_NO_ENABLED_WIDGETS",
                "The dashboard has no enabled widgets to refresh.",
                409,
            )
        job = await JobService(self.session, self.settings).create_job(
            organization_id=organization_id,
            requested_by=requested_by,
            job_type="dashboard_refresh",
            input_data={"dashboard_id": str(dashboard_id)},
        )
        AuditService(self.session).record(
            organization_id=organization_id,
            user_id=requested_by,
            action="dashboard.refresh_requested",
            resource_type="dashboard",
            resource_id=dashboard.id,
            metadata={"job_id": str(job.id)},
        )
        await self.session.commit()
        return job.id

    async def enqueue_refresh(
        self,
        *,
        widget_id: uuid.UUID,
        organization_id: uuid.UUID,
        requested_by: uuid.UUID,
    ) -> uuid.UUID:
        item = await self.repo.get_widget_for_org(widget_id, organization_id)
        if item is None:
            raise AppError("DASHBOARD_WIDGET_NOT_FOUND", "Dashboard widget not found.", 404)
        if not item.enabled:
            raise AppError("DASHBOARD_WIDGET_DISABLED", "Dashboard widget is disabled.", 409)
        job = await JobService(self.session, self.settings).create_job(
            organization_id=organization_id,
            requested_by=requested_by,
            job_type="dashboard_refresh",
            input_data={"widget_id": str(widget_id)},
        )
        AuditService(self.session).record(
            organization_id=organization_id,
            user_id=requested_by,
            action="dashboard_widget.refresh_requested",
            resource_type="dashboard_widget",
            resource_id=item.id,
            metadata={"job_id": str(job.id)},
        )
        await self.session.commit()
        return job.id

    async def widget_response(self, item: DashboardWidget) -> DashboardWidgetResponse:
        response = DashboardWidgetResponse.model_validate(item)
        artifact = await self._artifact_for_widget(item)
        if artifact is not None:
            response.latest_artifact = {
                "id": str(artifact.id),
                "kind": artifact.kind,
                "name": artifact.name,
                "payload": artifact.payload,
                "created_at": artifact.created_at.isoformat(),
            }
        return response

    async def _artifact_for_widget(self, item: DashboardWidget) -> JobArtifact | None:
        job_id = item.last_refresh_job_id or item.created_from_job_id
        if job_id is None:
            return None
        desired = (
            "chart" if item.widget_type in {"bar", "line", "area", "pie", "donut", "combo"} else "table"
        )
        conditions = [JobArtifact.job_id == job_id, JobArtifact.kind == desired]
        if item.last_refresh_job_id is None and item.created_from_sql_execution_id is not None:
            conditions.append(
                JobArtifact.source_sql_execution_id == item.created_from_sql_execution_id
            )
        result = await self.session.execute(
            select(JobArtifact)
            .where(*conditions)
            .order_by(JobArtifact.created_at.desc())
            .limit(1)
        )
        artifact = result.scalar_one_or_none()
        if artifact is not None:
            return artifact
        # A newly saved chart may use a different chart artifact or a table source. The frontend can
        # still render from the persisted source until first refresh.
        if desired == "chart" and item.created_from_job_id == job_id:
            result = await self.session.execute(
                select(JobArtifact)
                .where(
                    JobArtifact.job_id == job_id,
                    JobArtifact.kind == "table",
                    JobArtifact.source_sql_execution_id == item.created_from_sql_execution_id,
                )
                .order_by(JobArtifact.created_at.desc())
                .limit(1)
            )
            return result.scalar_one_or_none()
        return None

    async def _validate_widget_config(
        self,
        *,
        job_id: uuid.UUID | None,
        sql_execution_id: uuid.UUID | None,
        widget_type: str,
        config: dict[str, object],
    ) -> None:
        if widget_type == "table":
            return
        if job_id is None or sql_execution_id is None:
            raise AppError("WIDGET_CONFIG_INVALID", "Widget provenance is unavailable.", 400)
        artifact = await self.session.scalar(
            select(JobArtifact)
            .where(
                JobArtifact.job_id == job_id,
                JobArtifact.kind == "table",
                JobArtifact.source_sql_execution_id == sql_execution_id,
            )
            .order_by(JobArtifact.created_at.desc())
            .limit(1)
        )
        if artifact is None:
            raise AppError("WIDGET_SOURCE_RESULT_MISSING", "The source result is unavailable.", 400)
        columns = artifact.payload.get("columns")
        rows = artifact.payload.get("rows")
        if widget_type == "combo" and artifact.payload.get("truncated"):
            raise AppError("CHART_SOURCE_TRUNCATED", "Combo charts require a complete SQL result.", 400)
        if not isinstance(columns, list) or not all(isinstance(item, str) for item in columns) or not isinstance(rows, list):
            raise AppError("WIDGET_SOURCE_RESULT_INVALID", "The source result is invalid.", 400)
        if widget_type == "metric":
            field = config.get("field")
            if not isinstance(field, str) or not field:
                raise AppError("WIDGET_CONFIG_INVALID", "Metric widgets require a field.", 400)
            if field not in columns:
                raise AppError("WIDGET_COLUMN_NOT_FOUND", "The metric field is not present in the source result.", 400)
            return

        from pydantic import ValidationError
        from app.agent.tool_schemas import ChartSeriesInput, CreateChartArgs
        try:
            if widget_type in {"pie", "donut"}:
                parsed = CreateChartArgs(
                    sql_execution_id=sql_execution_id,
                    chart_type=widget_type,  # type: ignore[arg-type]
                    title="Validation",
                    category_field=config.get("category_field"),
                    value_field=config.get("value_field"),
                    value_label=config.get("value_label"),
                )
            else:
                raw_series = config.get("series") or []
                series = (
                    [ChartSeriesInput.model_validate(item) for item in raw_series]
                    if isinstance(raw_series, list)
                    else []
                )
                parsed = CreateChartArgs(
                    sql_execution_id=sql_execution_id,
                    chart_type=widget_type,  # type: ignore[arg-type]
                    title="Validation",
                    x_field=config.get("x_field"),
                    x_label=config.get("x_label"),
                    series=series,
                    orientation=config.get("orientation", "vertical"),
                    stacked=config.get("stacked", False),
                    y_label=config.get("y_label"),
                    secondary_y_label=config.get("secondary_y_label"),
                )
        except (ValidationError, ValueError, TypeError) as exc:
            raise AppError("WIDGET_CONFIG_INVALID", "The widget visualization configuration is invalid.", 400) from exc

        from app.agent.tools import AgentToolError, build_frontend_chart_payload
        try:
            build_frontend_chart_payload(parsed, columns, rows)  # type: ignore[arg-type]
        except AgentToolError as exc:
            raise AppError(exc.code, exc.public_message, 400) from exc

