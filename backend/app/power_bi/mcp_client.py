from __future__ import annotations

import asyncio
import base64
import csv
import io
import json
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Any

import httpx

from app.core.config import Settings
from app.core.errors import AppError
from app.data_sources.types import QueryResult

ALLOWED_TOOLS = frozenset(
    {
        "DiscoverArtifacts",
        "ResolveFabricItem",
        "GetReportMetadata",
        "GetSemanticModelSchema",
        "ValueSearch",
        "ExecuteQuery",
    }
)
ALLOWED_ENDPOINTS = frozenset(
    {
        "https://fabriciq.svc.cloud.microsoft/v1/mcp/fabriciq",
        "https://api.fabric.microsoft.com/v1/mcp/fabriciq",
    }
)


def microsoft_http_client(headers=None, timeout=None, auth=None):
    # Do not forward delegated bearer tokens through unexpected redirects.
    return httpx.AsyncClient(headers=headers, timeout=timeout, auth=auth, follow_redirects=False)


class FabricIQClient:
    def __init__(self, session: Any, schemas: dict[str, dict[str, object]], settings: Settings):
        self.session = session
        self.schemas = schemas
        self.settings = settings

    async def call(self, name: str, arguments: dict[str, object]) -> dict[str, object]:
        from jsonschema import Draft202012Validator
        from jsonschema.exceptions import ValidationError

        if name not in ALLOWED_TOOLS or name not in self.schemas:
            raise AppError(
                "POWER_BI_TOOL_UNAVAILABLE",
                "The required Fabric IQ capability is unavailable.",
                502,
            )
        try:
            Draft202012Validator(self.schemas[name]).validate(arguments)
        except ValidationError as exc:
            raise AppError(
                "POWER_BI_TOOL_CONTRACT_CHANGED",
                "Fabric IQ's tool contract has changed. Contact your administrator.",
                502,
            ) from exc
        result = await self.session.call_tool(name, arguments)
        payload = result.model_dump(mode="json", exclude_none=True)
        if len(json.dumps(payload).encode()) > self.settings.power_bi_metadata_max_bytes:
            raise AppError(
                "POWER_BI_RESULT_TOO_LARGE",
                "Power BI returned too much data. Narrow the request.",
                422,
            )
        if payload.get("isError"):
            raise AppError(
                "POWER_BI_TOOL_FAILED",
                "Power BI could not complete this operation. Check the model, query, and access.",
                422,
            )
        return payload


@asynccontextmanager
async def fabric_client(settings: Settings, token: str):
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    if settings.power_bi_mcp_url.lower().rstrip("/") not in ALLOWED_ENDPOINTS:
        raise AppError(
            "POWER_BI_ENDPOINT_INVALID",
            "Only the supported Microsoft Fabric IQ endpoints are allowed.",
            409,
        )
    timeout = timedelta(seconds=settings.agent_query_timeout_seconds)
    try:
        async with asyncio.timeout(settings.agent_query_timeout_seconds):
            async with streamablehttp_client(
                settings.power_bi_mcp_url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-Variants": settings.power_bi_tool_variant,
                },
                timeout=timeout,
                sse_read_timeout=timeout,
                httpx_client_factory=microsoft_http_client,
            ) as (read, write, _):
                async with ClientSession(read, write, read_timeout_seconds=timeout) as session:
                    await session.initialize()
                    schemas = {}
                    cursor = None
                    for _ in range(10):
                        page = await session.list_tools(cursor=cursor)
                        schemas.update(
                            {
                                tool.name: tool.inputSchema
                                for tool in page.tools
                                if tool.name in ALLOWED_TOOLS
                            }
                        )
                        cursor = page.nextCursor
                        if not cursor:
                            break
                    yield FabricIQClient(session, schemas, settings)
    except AppError:
        raise
    except Exception as exc:
        # Task groups can wrap HTTP failures; never expose headers or tokens from exceptions.
        errors = list(getattr(exc, "exceptions", [exc]))
        while any(hasattr(error, "exceptions") for error in errors):
            errors = [child for error in errors for child in getattr(error, "exceptions", [error])]
        domain = next((error for error in errors if isinstance(error, AppError)), None)
        if domain:
            raise domain from exc
        statuses = {
            getattr(getattr(error, "response", None), "status_code", None) for error in errors
        }
        if 401 in statuses:
            raise AppError(
                "POWER_BI_RECONNECT_REQUIRED", "Reconnect your Microsoft account.", 409
            ) from exc
        if 403 in statuses:
            raise AppError(
                "POWER_BI_ACCESS_DENIED", "Your Microsoft account cannot access this content.", 403
            ) from exc
        if 429 in statuses:
            raise AppError(
                "POWER_BI_THROTTLED", "Power BI is busy. Please retry shortly.", 429
            ) from exc
        raise AppError(
            "POWER_BI_UNAVAILABLE", "Fabric IQ is temporarily unavailable. Please retry.", 502
        ) from exc


def content_values(payload: dict[str, object]) -> list[object]:
    """Keep structured and text content: providers may return data only in text blocks."""
    values: list[object] = []
    if payload.get("structuredContent") is not None:
        values.append(payload["structuredContent"])
    for block in payload.get("content", []):
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text" and isinstance(block.get("text"), str):
            try:
                values.append(json.loads(block["text"]))
            except ValueError:
                values.append(block["text"])
        elif block.get("type") == "resource":
            resource = block.get("resource", {})
            if isinstance(resource, dict):
                values.append({"embedded_resource": resource})
    return values


def walk(value: object):
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def query_result(payload: dict[str, object], max_rows: int) -> QueryResult:
    candidates: list[tuple[list[str], list[list[object]]]] = []
    csv_candidates: list[tuple[list[str], list[list[object]]]] = []
    values = content_values(payload)
    truncated = False
    for item in walk(values):
        if not isinstance(item, dict):
            continue
        if item.get("error") or item.get("errors"):
            raise AppError(
                "POWER_BI_QUERY_FAILED",
                "The semantic model rejected this query. "
                "Check its schema, measures and permissions.",
                422,
            )
        truncated = truncated or any(
            item.get(key) is True for key in ("truncated", "isTruncated", "hasMoreRows")
        )
        rows = item.get("rows")
        if isinstance(rows, list):
            columns = item.get("columns", [])
            if columns and isinstance(columns, list):
                columns = [
                    str(c.get("name", c.get("columnName", ""))) if isinstance(c, dict) else str(c)
                    for c in columns
                ]
            if rows and all(isinstance(row, dict) for row in rows):
                columns = list(dict.fromkeys(key for row in rows for key in row))
                candidates.append((columns, [[row.get(c) for c in columns] for row in rows]))
            elif (
                isinstance(columns, list)
                and columns
                and all(isinstance(row, list) and len(row) == len(columns) for row in rows)
            ):
                candidates.append((columns, rows))
        resource = item.get("embedded_resource")
        if isinstance(resource, dict) and str(resource.get("mimeType", "")).split(";")[0] in {
            "text/csv",
            "application/csv",
        }:
            raw = resource.get("text")
            if raw is None and isinstance(resource.get("blob"), str):
                raw = base64.b64decode(resource["blob"], validate=True).decode("utf-8-sig")
            if isinstance(raw, str):
                reader = csv.reader(io.StringIO(raw))
                columns = next(reader, [])
                csv_rows = list(reader)
                if columns and all(len(row) == len(columns) for row in csv_rows):
                    csv_candidates.append(
                        (columns, [[_csv_scalar(v) for v in row] for row in csv_rows])
                    )
    if csv_candidates:
        full = {json.dumps(value, default=str): value for value in csv_candidates}
        if len(full) != 1:
            raise AppError(
                "POWER_BI_RESULT_UNSUPPORTED", "Power BI returned multiple tabular resources.", 422
            )
        columns, rows = next(iter(full.values()))

        # MCP includes a small inline preview alongside the complete embedded CSV.
        def comparable(values):
            return [["" if cell is None else str(cell) for cell in row] for row in values]

        for preview_columns, preview_rows in candidates:
            if preview_columns != columns or comparable(preview_rows) != comparable(
                rows[: len(preview_rows)]
            ):
                raise AppError(
                    "POWER_BI_RESULT_UNSUPPORTED",
                    "Power BI's inline preview does not match its CSV result.",
                    422,
                )
        candidates = [(columns, rows)]
    unique = {
        json.dumps(candidate, sort_keys=True, default=str): candidate for candidate in candidates
    }
    if len(unique) != 1:
        raise AppError(
            "POWER_BI_RESULT_UNSUPPORTED",
            "Power BI did not return one unambiguous tabular result. Narrow the query.",
            422,
        )
    columns, rows = next(iter(unique.values()))
    if len(set(columns)) != len(columns) or not all(columns):
        raise AppError(
            "POWER_BI_RESULT_UNSUPPORTED", "Power BI returned ambiguous column names.", 422
        )
    # A full cap is conservatively incomplete even if upstream omitted its truncation flag.
    truncated = truncated or len(rows) >= max_rows
    return QueryResult(tuple(columns), tuple(tuple(row) for row in rows[:max_rows]), truncated)


def _csv_scalar(value: str) -> object:
    if value == "":
        return None
    # Preserve identifiers with leading zeros and locale-dependent numbers as strings.
    import re

    if re.fullmatch(r"-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?", value):
        return float(value) if any(c in value for c in ".eE") else int(value)
    return value
