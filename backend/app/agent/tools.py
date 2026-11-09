from __future__ import annotations

import asyncio
import json
import math
import time
import uuid
from collections import Counter
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from langgraph.errors import GraphBubbleUp
from langgraph.types import interrupt
from pydantic import BaseModel, ValidationError

from app.agent.clarification import (
    MAX_QUESTIONS,
    MAX_ROUNDS,
    AskUserArgs,
    ClarificationError,
    build_request,
)
from app.agent.html_artifacts import HtmlArtifactStorage, HtmlArtifactValidationError
from app.agent.matrix import CreateMatrixArgs, MatrixError, build_matrix
from app.agent.models import JobArtifact, SQLExecution, ToolExecution
from app.agent.repository import AgentExecutionRepository
from app.agent.serialization import bound_query_result, model_result_preview
from app.agent.sql_safety import SQLSafetyViolation, validate_read_only_sql
from app.agent.time_context import RequestTimeContext
from app.agent.tool_schemas import (
    CreateChartArgs,
    CreateHtmlArtifactArgs,
    ExecuteSQLArgs,
    GetCurrentTimeArgs,
    ReadKnowledgeIndexArgs,
    ReadTableSchemaArgs,
)
from app.conversations.table_scope import SourceTableScope
from app.core.config import Settings, get_settings
from app.core.database import get_session_factory
from app.core.time import clock_snapshot, utc_now
from app.data_sources.errors import DataSourceOperationError
from app.data_sources.service import DataSourceService
from app.jobs.repository import JobRepository
from app.jobs.service import JobService
from app.knowledge.repository import KnowledgeRepository


class AgentCancelledError(Exception):
    pass


class AgentLimitError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.public_message = message
        super().__init__(message)


class AgentTurnEnded(Exception):  # noqa: N818 - a stop signal, not an error
    """Raised after a turn-ending tool succeeds, so the agent stops without a final answer."""

    def __init__(self, tool_name: str, result: dict[str, object]) -> None:
        self.tool_name = tool_name
        self.result = result
        super().__init__(tool_name)


class AgentToolError(Exception):
    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        self.code = code
        self.public_message = message
        self.retryable = retryable
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class AgentToolContext:
    job_id: uuid.UUID
    organization_id: uuid.UUID
    conversation_id: uuid.UUID
    allowed_data_source_ids: frozenset[uuid.UUID]
    settings: Settings
    default_instructions: str | None = None
    command_instructions: str | None = None
    command_name: str | None = None
    table_scope: tuple[SourceTableScope, ...] = ()
    # Clarification rounds already answered for the current request in earlier turns.
    clarification_round: int = 0
    # True when a checkpointer can pause this run for the user's answers and resume it later.
    pausable: bool = False
    requested_by: uuid.UUID | None = None
    power_bi_source_ids: frozenset[uuid.UUID] = frozenset()
    power_bi_context: dict[str, object] | None = None
    power_bi_identity: dict[str, str] | None = None
    time_context: RequestTimeContext | None = None

    def selected_scope(self, source_id: uuid.UUID) -> SourceTableScope | None:
        return next((item for item in self.table_scope
            if item.data_source_id == source_id and item.mode == "selected"), None)


ToolHandler = Callable[
    [AgentToolContext, dict[str, object], uuid.UUID], Awaitable[dict[str, object]]
]


@dataclass(frozen=True, slots=True)
class AgentToolDefinition:
    name: str
    description: str
    args_schema: type[BaseModel]
    handler: ToolHandler
    # The agent stops after this tool succeeds; the turn ends without a final answer.
    ends_turn: bool = False


class AgentToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, AgentToolDefinition] = {}

    def register(self, tool: AgentToolDefinition) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Agent tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> AgentToolDefinition | None:
        return self._tools.get(name)

    def all(self) -> tuple[AgentToolDefinition, ...]:
        return tuple(self._tools.values())


async def append_agent_event(
    job_id: uuid.UUID,
    event_type: str,
    payload: dict[str, object],
    *,
    level: str = "info",
) -> None:
    settings = get_settings()
    async with get_session_factory()() as session:
        await JobService(session, settings).append_event(
            job_id, event_type, payload, level=level
        )


async def is_cancel_requested(job_id: uuid.UUID) -> bool:
    async with get_session_factory()() as session:
        job = await JobRepository(session).get(job_id)
        return bool(job and job.cancel_requested_at is not None)


async def run_cancellable(
    job_id: uuid.UUID,
    awaitable: Awaitable[object],
    *,
    timeout_seconds: float,
) -> object:
    """Run an awaitable while polling the durable job cancellation flag."""

    task = asyncio.create_task(awaitable)
    started = time.monotonic()
    try:
        while True:
            elapsed = time.monotonic() - started
            remaining = timeout_seconds - elapsed
            if remaining <= 0:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
                raise TimeoutError
            done, _ = await asyncio.wait({task}, timeout=min(0.5, remaining))
            if task in done:
                return await task
            if await is_cancel_requested(job_id):
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
                raise AgentCancelledError
    except asyncio.CancelledError:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        raise


def _parse_source_id(context: AgentToolContext, arguments: dict[str, object]) -> uuid.UUID:
    raw = arguments.get("data_source_id")
    try:
        source_id = uuid.UUID(str(raw))
    except (ValueError, TypeError, AttributeError) as exc:
        raise AgentToolError(
            "TOOL_ARGUMENT_INVALID", "A valid data_source_id is required."
        ) from exc
    if source_id not in context.allowed_data_source_ids:
        raise AgentToolError(
            "DATASOURCE_NOT_AUTHORIZED",
            "This datasource is not available in the current conversation.",
        )
    return source_id


def _index_line(key: str, metadata: dict[str, object]) -> str:
    """Match the generated index line so selected tables read like the full index."""
    primary_key = metadata.get("primary_key") or []
    pk = f"; PK: {', '.join(map(str, primary_key))}" if primary_key else ""
    return (
        f"- `{key}` — {metadata.get('object_type', 'table')}; "
        f"{metadata.get('column_count', 0)} columns{pk}; schema document key: `{key}`"
    )


async def read_knowledge_index(
    context: AgentToolContext,
    arguments: dict[str, object],
    _tool_execution_id: uuid.UUID,
) -> dict[str, object]:
    source_id = _parse_source_id(context, arguments)
    async with get_session_factory()() as session:
        repo = KnowledgeRepository(session)
        base = await repo.get_base_for_source(source_id, context.organization_id)
        if base is None or base.current_version_id is None or base.status != "ready":
            raise AgentToolError(
                "KNOWLEDGE_NOT_READY",
                "Knowledge has not been generated for this datasource yet.",
            )
        doc = await repo.get_document(base.current_version_id, "index", "index")
        if doc is None:
            raise AgentToolError("KNOWLEDGE_INDEX_MISSING", "The knowledge index is unavailable.")
        annotations = await repo.list_annotations(base.id)
        business = [
            {"scope_type": item.scope_type, "scope_key": item.scope_key, "content": item.content}
            for item in annotations
            if item.scope_type in {"datasource", "metric"}
        ]
        index_markdown = doc.content_markdown
        selected = context.selected_scope(source_id)
        if selected is not None:
            lines = []
            for table in selected.tables:
                key = f"{table.schema_name}.{table.name}" if table.schema_name else table.name
                entry = await repo.get_document(base.current_version_id, "table_schema", key)
                if entry is not None:
                    lines.append(_index_line(key, entry.metadata_json))
            others = int(doc.metadata_json.get("object_count", 0)) - len(lines)
            index_markdown = "# Tables selected by the user\n\n" + "\n".join(lines) + "\n"
            if arguments.get("include_all_tables"):
                index_markdown += "\n" + doc.content_markdown
            elif others > 0:
                index_markdown += (
                    f"\n{others} other tables and views exist in this datasource. Call "
                    "read_knowledge_index with include_all_tables=true if the selected tables "
                    "cannot answer the question.\n"
                )
        payload: dict[str, object] = {
            "data_source_id": str(source_id),
            "knowledge_version_id": str(base.current_version_id),
            "index_markdown": index_markdown,
            "business_annotations": business,
        }
        estimated_tokens = len(index_markdown) // 4
    await append_agent_event(
        context.job_id,
        "knowledge.index.loaded",
        {"data_source_id": str(source_id), "estimated_tokens": estimated_tokens},
    )
    return payload


async def read_table_schema(
    context: AgentToolContext,
    arguments: dict[str, object],
    _tool_execution_id: uuid.UUID,
) -> dict[str, object]:
    source_id = _parse_source_id(context, arguments)
    raw_key = arguments.get("table_key")
    if not isinstance(raw_key, str) or not raw_key.strip():
        raise AgentToolError("TOOL_ARGUMENT_INVALID", "table_key is required.")
    table_key = raw_key.strip()
    async with get_session_factory()() as session:
        repo = KnowledgeRepository(session)
        base = await repo.get_base_for_source(source_id, context.organization_id)
        if base is None or base.current_version_id is None or base.status != "ready":
            raise AgentToolError(
                "KNOWLEDGE_NOT_READY",
                "Knowledge has not been generated for this datasource yet.",
            )
        doc = await repo.get_document(base.current_version_id, "table_schema", table_key)
        if doc is None:
            raise AgentToolError(
                "KNOWLEDGE_TABLE_NOT_FOUND",
                "The requested table schema is not present in the current knowledge version.",
            )
        annotations = await repo.list_annotations(base.id)
        relevant = [
            {"scope_type": item.scope_type, "scope_key": item.scope_key, "content": item.content}
            for item in annotations
            if (item.scope_type == "table" and item.scope_key == table_key)
            or (
                item.scope_type == "column"
                and item.scope_key is not None
                and item.scope_key.startswith(f"{table_key}.")
            )
        ]
        payload = {
            "data_source_id": str(source_id),
            "table_key": table_key,
            "schema_markdown": doc.content_markdown,
            "business_annotations": relevant,
        }
        estimated_tokens = doc.estimated_tokens
    await append_agent_event(
        context.job_id,
        "knowledge.schema.loaded",
        {
            "data_source_id": str(source_id),
            "table_key": table_key,
            "estimated_tokens": estimated_tokens,
        },
    )
    return payload


async def execute_sql(
    context: AgentToolContext,
    arguments: dict[str, object],
    tool_execution_id: uuid.UUID,
) -> dict[str, object]:
    source_id = _parse_source_id(context, arguments)
    raw_sql = arguments.get("sql")
    if not isinstance(raw_sql, str):
        raise AgentToolError("TOOL_ARGUMENT_INVALID", "sql is required.")

    async with get_session_factory()() as session:
        source_service = DataSourceService(session, context.settings)
        source = await source_service.require_for_org(source_id, context.organization_id)
        if source.status != "active":
            raise AgentToolError("DATASOURCE_NOT_ACTIVE", "The datasource is not active.")
        try:
            sql = validate_read_only_sql(raw_sql, source_kind=source.kind)
        except SQLSafetyViolation as exc:
            raise AgentToolError(exc.code, exc.public_message) from exc
        adapter = await source_service.resolve_adapter(source)
        source_kind = source.kind
        sql_execution = SQLExecution(
            tool_execution_id=tool_execution_id,
            data_source_id=source_id,
            sql_text=sql,
            status="started",
            started_at=utc_now(),
        )
        repo = AgentExecutionRepository(session)
        repo.add_sql(sql_execution)
        await session.commit()
        sql_execution_id = sql_execution.id

    await append_agent_event(
        context.job_id,
        "sql.started",
        {
            "sql_execution_id": str(sql_execution_id),
            "tool_execution_id": str(tool_execution_id),
            "data_source_id": str(source_id),
            "sql": sql,
        },
    )

    started = time.perf_counter()
    try:
        result = await run_cancellable(
            context.job_id,
            adapter.execute_read_query(sql, max_rows=context.settings.agent_result_max_rows),
            timeout_seconds=context.settings.agent_query_timeout_seconds,
        )
        columns, rows, truncated, result_bytes = bound_query_result(  # type: ignore[arg-type]
            result, max_bytes=context.settings.agent_result_max_bytes
        )
        duration_ms = max(0, int((time.perf_counter() - started) * 1000))
        preview = model_result_preview(
            columns=columns,
            rows=rows,
            truncated=truncated,
            max_rows=context.settings.agent_model_result_max_rows,
            max_bytes=context.settings.agent_model_result_max_bytes,
        )
        preview_rows = preview.get("rows")
        preview_row_count = len(preview_rows) if isinstance(preview_rows, list) else 0
        preview_truncated = preview.get("truncated") is True

        async with get_session_factory()() as session:
            sql_item = await session.get(SQLExecution, sql_execution_id)
            if sql_item is None:
                raise AgentToolError(
                    "SQL_EXECUTION_NOT_FOUND", "SQL execution audit state is unavailable."
                )
            sql_item.status = "succeeded"
            sql_item.columns = columns
            sql_item.row_count = len(rows)
            sql_item.truncated = truncated
            sql_item.result_bytes = result_bytes
            sql_item.duration_ms = duration_ms
            sql_item.finished_at = utc_now()

            custom_title = arguments.get("title")
            artifact_name = (
                str(custom_title).strip()
                if custom_title and str(custom_title).strip()
                else "Query result"
            )
            display_mode = str(arguments.get("display") or "auto")
            raw_column_labels = arguments.get("column_labels")
            column_labels = (
                {str(k): str(v) for k, v in raw_column_labels.items()}
                if isinstance(raw_column_labels, dict)
                else None
            )

            artifact = JobArtifact(
                job_id=context.job_id,
                kind="table",
                name=artifact_name,
                source_sql_execution_id=sql_execution_id,
                payload={
                    "schema_version": 1,
                    "data_source_id": str(source_id),
                    "columns": columns,
                    "rows": rows,
                    "row_count": len(rows),
                    "truncated": truncated,
                    "stored_row_count": len(rows),
                    "stored_result_truncated": truncated,
                    "model_preview_row_count": preview_row_count,
                    "model_preview_truncated": preview_truncated,
                    "display": display_mode,
                    "column_labels": column_labels,
                },
                created_at=utc_now(),
            )
            session.add(artifact)
            await session.commit()
            artifact_id = artifact.id

        await append_agent_event(
            context.job_id,
            "sql.completed",
            {
                "sql_execution_id": str(sql_execution_id),
                "data_source_id": str(source_id),
                "row_count": len(rows),
                "truncated": truncated,
                "duration_ms": duration_ms,
                "result_bytes": result_bytes,
            },
        )
        return {
            "ok": True,
            "data_source_id": str(source_id),
            "source_kind": source_kind,
            "sql_execution_id": str(sql_execution_id),
            "table_artifact_id": str(artifact_id),
            "table_display": display_mode,
            "stored_row_count": len(rows),
            "stored_row_limit": context.settings.agent_result_max_rows,
            "preview_row_count": preview_row_count,
            "stored_result_truncated": truncated,
            "preview_truncated": preview_truncated,
            "listing_guidance": (
                "The stored result reached its limit. Do not page through the remaining rows "
                "with more queries; tell the user the listing is capped and suggest narrower "
                "filters."
                if truncated
                else None
            ),
            "evidence_warning": (
                "The model received only a partial preview. Do not make totals, percentages, "
                "rankings, distributions, primary-reason, or whole-population claims from this "
                "preview. Execute a complete aggregate query for those conclusions."
                if preview_truncated
                else None
            ),
            "presentation_guidance": (
                "This result is hidden in the UI. Use it only for analysis, or present it once in "
                "the written answer if the user needs to see it."
                if display_mode == "hidden"
                else (
                    "The UI presents this table artifact. Do not repeat these rows as a "
                    "Markdown table."
                )
            ),
            **preview,
        }
    except AgentCancelledError:
        duration_ms = max(0, int((time.perf_counter() - started) * 1000))
        await _mark_sql_failed(
            sql_execution_id,
            status="cancelled",
            code="JOB_CANCELLED",
            message="SQL execution was cancelled.",
            duration_ms=duration_ms,
        )
        await append_agent_event(
            context.job_id,
            "sql.cancelled",
            {"sql_execution_id": str(sql_execution_id), "data_source_id": str(source_id)},
        )
        raise
    except TimeoutError as exc:
        duration_ms = max(0, int((time.perf_counter() - started) * 1000))
        await _mark_sql_failed(
            sql_execution_id,
            status="failed",
            code="SQL_QUERY_TIMEOUT",
            message="The analytical query timed out.",
            duration_ms=duration_ms,
        )
        await append_agent_event(
            context.job_id,
            "sql.failed",
            {"sql_execution_id": str(sql_execution_id), "code": "SQL_QUERY_TIMEOUT"},
            level="warning",
        )
        raise AgentToolError("SQL_QUERY_TIMEOUT", "The analytical query timed out.") from exc
    except DataSourceOperationError as exc:
        duration_ms = max(0, int((time.perf_counter() - started) * 1000))
        await _mark_sql_failed(
            sql_execution_id,
            status="failed",
            code=exc.code,
            message=exc.public_message,
            duration_ms=duration_ms,
        )
        await append_agent_event(
            context.job_id,
            "sql.failed",
            {"sql_execution_id": str(sql_execution_id), "code": exc.code},
            level="warning",
        )
        raise AgentToolError(exc.code, exc.public_message, retryable=exc.retryable) from exc
    except AgentToolError:
        raise
    except Exception as exc:
        duration_ms = max(0, int((time.perf_counter() - started) * 1000))
        await _mark_sql_failed(
            sql_execution_id,
            status="failed",
            code="SQL_EXECUTION_FAILED",
            message="The analytical query failed.",
            duration_ms=duration_ms,
        )
        await append_agent_event(
            context.job_id,
            "sql.failed",
            {"sql_execution_id": str(sql_execution_id), "code": "SQL_EXECUTION_FAILED"},
            level="warning",
        )
        raise AgentToolError("SQL_EXECUTION_FAILED", "The analytical query failed.") from exc


async def create_chart(
    context: AgentToolContext,
    arguments: dict[str, object],
    _tool_execution_id: uuid.UUID,
) -> dict[str, object]:
    """Create a frontend chart artifact grounded in an already persisted SQL result."""

    try:
        parsed = CreateChartArgs.model_validate(arguments)
    except ValidationError as exc:
        raise AgentToolError(
            "CHART_SPEC_INVALID", "The frontend chart specification is invalid."
        ) from exc

    async with get_session_factory()() as session:
        repo = AgentExecutionRepository(session)
        sql_item = await repo.get_sql_for_job(parsed.sql_execution_id, context.job_id)
        if sql_item is None or sql_item.status != "succeeded":
            raise AgentToolError(
                "CHART_SOURCE_NOT_FOUND",
                "The chart must reference a successful SQL execution from this job.",
            )
        table_artifact = await repo.get_table_artifact_for_sql(
            context.job_id, parsed.sql_execution_id
        )
        if table_artifact is None:
            raise AgentToolError(
                "CHART_SOURCE_NOT_FOUND", "The SQL result is unavailable for charting."
            )
        payload = table_artifact.payload
        if parsed.chart_type == "combo" and (sql_item.truncated or payload.get("truncated")):
            raise AgentToolError(
                "CHART_SOURCE_TRUNCATED",
                "Combo charts require a complete SQL result. Aggregate or limit the categories in SQL.",
                retryable=True,
            )
        columns = payload.get("columns")
        rows = payload.get("rows")
        if not isinstance(columns, list) or not all(isinstance(item, str) for item in columns):
            raise AgentToolError("CHART_SOURCE_INVALID", "The SQL result columns are unavailable.")
        if not isinstance(rows, list):
            raise AgentToolError("CHART_SOURCE_INVALID", "The SQL result rows are unavailable.")
        if len(rows) > context.settings.agent_chart_max_rows:
            raise AgentToolError(
                "CHART_SOURCE_TOO_LARGE",
                "The SQL result has too many rows for a chart. Run an aggregation query first.",
            )

        chart_payload, records = build_frontend_chart_payload(parsed, columns, rows)

        artifact = JobArtifact(
            job_id=context.job_id,
            kind="chart",
            name=parsed.title,
            source_sql_execution_id=parsed.sql_execution_id,
            payload=chart_payload,
            created_at=utc_now(),
        )
        repo.add_artifact(artifact)
        await session.commit()
        artifact_id = artifact.id

    await append_agent_event(
        context.job_id,
        "chart.generated",
        {
            "artifact_id": str(artifact_id),
            "sql_execution_id": str(parsed.sql_execution_id),
            "chart_type": parsed.chart_type,
            "title": parsed.title,
            "row_count": len(records),
        },
    )
    return {
        "ok": True,
        "chart_artifact_id": str(artifact_id),
        "chart_type": parsed.chart_type,
        "title": parsed.title,
        "source_sql_execution_id": str(parsed.sql_execution_id),
        "row_count": len(records),
        "renderer": "frontend",
    }


async def create_matrix(
    context: AgentToolContext,
    arguments: dict[str, object],
    _tool_execution_id: uuid.UUID,
) -> dict[str, object]:
    """Build an immutable matrix from this job's complete persisted SQL result."""
    if not context.settings.agent_matrix_enabled:
        raise AgentToolError("MATRIX_DISABLED", "Matrix creation is not enabled.")
    try:
        parsed = CreateMatrixArgs.model_validate(arguments)
    except ValidationError as exc:
        raise AgentToolError("MATRIX_SPEC_INVALID", str(exc), retryable=True) from exc
    async with get_session_factory()() as session:
        repo = AgentExecutionRepository(session)
        source = await repo.get_sql_for_job(parsed.sql_execution_id, context.job_id)
        if (
            source is None
            or source.status != "succeeded"
            or source.data_source_id not in context.allowed_data_source_ids
        ):
            raise AgentToolError(
                "MATRIX_SOURCE_NOT_FOUND",
                "Use a successful authorized SQL execution from this job.",
            )
        table = await repo.get_table_artifact_for_sql(context.job_id, source.id)
        if table is None:
            raise AgentToolError("MATRIX_SOURCE_NOT_FOUND", "The stored SQL result is unavailable.")
        from app.agent.evidence import _valid_table_artifact

        if not _valid_table_artifact(table.payload, source):
            raise AgentToolError("MATRIX_SOURCE_INVALID", "The stored SQL result is inconsistent.")
        try:
            payload = await asyncio.to_thread(
                build_matrix,
                parsed,
                table.payload["columns"],
                table.payload["rows"],
                truncated=source.truncated or table.payload.get("stored_result_truncated") is True,
                max_nodes=context.settings.agent_matrix_max_nodes,
                max_columns=context.settings.agent_matrix_max_columns,
                max_cells=context.settings.agent_matrix_max_cells,
                max_bytes=context.settings.agent_result_max_bytes,
            )
        except MatrixError as exc:
            raise AgentToolError(exc.code, str(exc), retryable=True) from exc
        existing = await repo.list_artifacts(context.job_id)
        artifact = next(
            (item for item in existing if item.kind == "matrix" and item.payload == payload), None
        )
        if artifact is None:
            artifact = JobArtifact(
                job_id=context.job_id,
                kind="matrix",
                name=parsed.title,
                source_sql_execution_id=source.id,
                payload=payload,
                created_at=utc_now(),
            )
            repo.add_artifact(artifact)
        # A failed matrix leaves the table intact. Hide it only after successful construction.
        table.payload = {**table.payload, "display": "hidden"}
        await session.commit()
        artifact_id = artifact.id
    await append_agent_event(
        context.job_id,
        "matrix.generated",
        {
            "artifact_id": str(artifact_id),
            "sql_execution_id": str(parsed.sql_execution_id),
            "source_rows": payload["source_row_count"],
            "cell_count": len(payload["cells"]),
        },
    )
    return {
        "ok": True,
        "matrix_artifact_id": str(artifact_id),
        "title": parsed.title,
        "source_sql_execution_id": str(parsed.sql_execution_id),
        "renderer": "frontend",
        "presentation_guidance": "Reference this matrix artifact once. Do not reproduce it in Markdown.",
    }


async def create_html_artifact(
    context: AgentToolContext,
    arguments: dict[str, object],
    _tool_execution_id: uuid.UUID,
) -> dict[str, object]:
    """Persist one complete HTML document as a managed file plus small DB metadata."""

    try:
        parsed = CreateHtmlArtifactArgs.model_validate(arguments)
    except ValidationError as exc:
        raise AgentToolError("HTML_ARTIFACT_INVALID", "The HTML artifact is invalid.") from exc

    if parsed.source_sql_execution_id is not None:
        async with get_session_factory()() as session:
            source = await AgentExecutionRepository(session).get_sql_for_job(
                parsed.source_sql_execution_id, context.job_id
            )
            if source is None or source.status != "succeeded":
                raise AgentToolError(
                    "HTML_SOURCE_NOT_FOUND",
                    "The HTML artifact must reference a successful SQL execution from this job.",
                )

    artifact_id = uuid.uuid4()
    storage = HtmlArtifactStorage(
        context.settings.data_directory,
        context.settings.agent_html_artifact_max_bytes,
    )
    try:
        size_bytes = storage.write(context.job_id, artifact_id, parsed.html)
    except HtmlArtifactValidationError as exc:
        raise AgentToolError("HTML_ARTIFACT_INVALID", str(exc)) from exc
    except OSError as exc:
        raise AgentToolError(
            "HTML_ARTIFACT_WRITE_FAILED",
            "The HTML artifact file could not be written.",
            retryable=True,
        ) from exc

    try:
        async with get_session_factory()() as session:
            repo = AgentExecutionRepository(session)
            repo.add_artifact(
                JobArtifact(
                    id=artifact_id,
                    job_id=context.job_id,
                    kind="html",
                    name=parsed.title,
                    source_sql_execution_id=parsed.source_sql_execution_id,
                    payload={
                        "schema_version": 1,
                        "file_name": "index.html",
                        "size_bytes": size_bytes,
                    },
                    created_at=utc_now(),
                )
            )
            await session.commit()
    except Exception:
        storage.delete(context.job_id, artifact_id)
        raise

    event_payload: dict[str, object] = {
        "artifact_id": str(artifact_id),
        "title": parsed.title,
        "file_name": "index.html",
        "size_bytes": size_bytes,
    }
    if parsed.source_sql_execution_id is not None:
        event_payload["sql_execution_id"] = str(parsed.source_sql_execution_id)
    await append_agent_event(context.job_id, "html.generated", event_payload)
    return {"ok": True, **event_payload}


def _finite_number(value: object) -> float | None:
    """Return a finite float for a number or numeric text, otherwise None (booleans excluded)."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) if math.isfinite(float(value)) else None
    if isinstance(value, str):
        cleaned = value.replace(",", "").replace("$", "").replace(" ", "").strip()
        try:
            number = float(cleaned)
        except ValueError:
            return None
        return number if math.isfinite(number) else None
    return None


def build_frontend_chart_payload(
    parsed: CreateChartArgs, columns: list[str], rows: list[object]
) -> tuple[dict[str, object], list[dict[str, object]]]:
    required_fields: list[str]
    if parsed.chart_type in ("pie", "donut"):
        required_fields = [parsed.category_field or "", parsed.value_field or ""]
    elif parsed.chart_type == "metric":
        required_fields = [field for item in parsed.metrics for field in item.referenced_fields()]
    else:
        required_fields = [parsed.x_field or "", *[item.field for item in parsed.series]]
    missing = sorted({field for field in required_fields if field not in columns})
    if missing:
        raise AgentToolError(
            "CHART_COLUMN_NOT_FOUND",
            f"The chart references unavailable SQL result column(s): {', '.join(missing)}.",
        )

    if parsed.chart_type in ("bar", "line", "area", "combo"):
        series_fields = [item.field for item in parsed.series]
        repeated_fields = sorted(
            field for field, count in Counter(series_fields).items() if count > 1
        )
        if repeated_fields:
            raise AgentToolError(
                "CHART_SERIES_FIELD_REUSED",
                "Each chart series must reference a distinct numeric SQL output column. "
                "Series labels only rename columns and do not filter category rows. Re-run SQL "
                "at the chart's final grain, pivoting long-form category/value data into one "
                "numeric column per series, then retry the chart.",
                retryable=True,
            )
        if parsed.x_field in series_fields:
            raise AgentToolError(
                "CHART_FIELD_ROLE_CONFLICT",
                "The chart x-axis field cannot also be used as a numeric series field. Re-run "
                "SQL with separate dimension and measure columns, then retry the chart.",
                retryable=True,
            )
    elif parsed.chart_type in ("pie", "donut") and parsed.category_field == parsed.value_field:
        raise AgentToolError(
            "CHART_FIELD_ROLE_CONFLICT",
            "Pie and donut charts require different category and numeric value columns.",
            retryable=True,
        )

    records: list[dict[str, object]] = []
    for raw_row in rows:
        if not isinstance(raw_row, list):
            continue
        records.append(
            {
                column: raw_row[index] if index < len(raw_row) else None
                for index, column in enumerate(columns)
            }
        )

    if not records:
        raise AgentToolError(
            "CHART_SOURCE_EMPTY",
            "The SQL result has no rows to chart. Continue with a textual empty-result answer "
            "instead of creating a chart.",
        )

    if parsed.chart_type in ("bar", "line", "area", "combo"):
        dimension_field = parsed.x_field or ""
        dimension_values = [record.get(dimension_field) for record in records]
        if any(value is None for value in dimension_values):
            raise AgentToolError(
                "CHART_DIMENSION_MISSING",
                f"The chart dimension field {dimension_field!r} contains null values. Aggregate "
                "or clean the dimension in SQL before retrying the chart.",
                retryable=True,
            )
        dimension_keys = [
            json.dumps(value, sort_keys=True, default=str) for value in dimension_values
        ]
        if len(set(dimension_keys)) != len(dimension_keys):
            raise AgentToolError(
                "CHART_DIMENSION_NOT_UNIQUE",
                "Bar, line, and area chart SQL must return one row per x-axis value. Aggregate or "
                "pivot repeated dimension rows into distinct numeric series columns, then retry "
                "the chart.",
                retryable=True,
            )
    elif parsed.chart_type in ("pie", "donut"):
        category_field = parsed.category_field or ""
        category_values = [record.get(category_field) for record in records]
        if any(value is None for value in category_values):
            raise AgentToolError(
                "CHART_CATEGORY_MISSING",
                f"The chart category field {category_field!r} contains null values. Group or label "
                "null categories in SQL before retrying the chart.",
                retryable=True,
            )
        category_keys = [
            json.dumps(value, sort_keys=True, default=str) for value in category_values
        ]
        if len(set(category_keys)) != len(category_keys):
            raise AgentToolError(
                "CHART_CATEGORY_NOT_UNIQUE",
                "Pie and donut SQL must return one aggregated row per category. Aggregate repeated "
                "categories in SQL, then retry the chart.",
                retryable=True,
            )
    elif parsed.chart_type == "metric" and len(records) != 1:
        raise AgentToolError(
            "CHART_METRIC_ROW_COUNT_INVALID",
            "Metric cards require SQL that returns exactly one aggregate row with one numeric "
            "column per figure. Aggregate the result to one row, then retry the metric.",
            retryable=True,
        )

    chart_payload: dict[str, object] = {
        "schema_version": 1,
        "renderer": "frontend",
        "chart_type": parsed.chart_type,
        "title": parsed.title,
        "source_sql_execution_id": str(parsed.sql_execution_id),
        "data": records,
    }
    if parsed.chart_type in ("bar", "combo"):
        chart_payload["orientation"] = parsed.orientation
        chart_payload["stacked"] = parsed.stacked
    if parsed.chart_type == "combo":
        chart_payload["y_label"] = parsed.y_label
        chart_payload["secondary_y_label"] = parsed.secondary_y_label
    if parsed.chart_type == "metric":
        numeric_fields = [item.field for item in parsed.metrics]
        optional_numeric_fields = [
            field
            for item in parsed.metrics
            for field in item.referenced_fields()
            if field != item.field
        ]
        for field in optional_numeric_fields:
            for record in records:
                value = record.get(field)
                if value is not None and _finite_number(value) is None:
                    raise AgentToolError(
                        "CHART_VALUE_NOT_NUMERIC",
                        f"Metric field {field!r} contains non-numeric values.",
                    )
    else:
        numeric_fields = (
            [parsed.value_field or ""]
            if parsed.chart_type in ("pie", "donut")
            else [item.field for item in parsed.series]
        )
    for field in numeric_fields:
        has_numeric_value = False
        has_positive_value = False
        for record in records:
            value = record.get(field)
            if value is None:
                is_column = (
                    parsed.chart_type != "combo"
                    or next(item for item in parsed.series if item.field == field).type == "bar"
                )
                if parsed.chart_type == "donut" or (parsed.stacked and is_column):
                    raise AgentToolError(
                        "CHART_VALUE_MISSING",
                        "Donut and stacked charts require complete numeric values. "
                        "Resolve missing measurements in SQL before creating the chart.",
                        retryable=True,
                    )
                continue
            if isinstance(value, bool):
                raise AgentToolError(
                    "CHART_VALUE_NOT_NUMERIC",
                    f"Chart value field {field!r} contains non-numeric values.",
                )
            if isinstance(value, (int, float)):
                if math.isfinite(float(value)):
                    if parsed.chart_type == "donut" and value < 0:
                        raise AgentToolError(
                            "CHART_VALUE_NEGATIVE", "Donut charts require non-negative values."
                        )
                    has_numeric_value = True
                    has_positive_value |= value > 0
                    continue
            if isinstance(value, str):
                cleaned = value.replace(",", "").replace("$", "").replace(" ", "").strip()
                try:
                    number = float(cleaned)
                except ValueError:
                    number = float("nan")
                if math.isfinite(number):
                    if parsed.chart_type == "donut" and number < 0:
                        raise AgentToolError(
                            "CHART_VALUE_NEGATIVE", "Donut charts require non-negative values."
                        )
                    has_numeric_value = True
                    has_positive_value |= number > 0
                    continue
            raise AgentToolError(
                "CHART_VALUE_NOT_NUMERIC",
                f"Chart value field {field!r} contains non-numeric values.",
            )
        if not has_numeric_value:
            raise AgentToolError(
                "CHART_VALUE_EMPTY",
                f"Chart value field {field!r} contains no numeric values.",
            )
        if parsed.chart_type == "donut" and not has_positive_value:
            raise AgentToolError(
                "CHART_TOTAL_EMPTY",
                "Donut charts require a positive total. "
                "Present the zero result as text or a metric.",
            )

    if parsed.chart_type in ("pie", "donut"):
        chart_payload["encoding"] = {
            "category": {"field": parsed.category_field},
            "value": {"field": parsed.value_field, "label": parsed.value_label},
        }
    elif parsed.chart_type == "metric":
        chart_payload["encoding"] = {
            "metrics": [item.model_dump(mode="json", exclude_none=True) for item in parsed.metrics],
        }
    else:
        chart_payload["encoding"] = {
            "x": {"field": parsed.x_field, "label": parsed.x_label},
            "series": [
                {
                    "field": item.field,
                    "label": item.label,
                    **({"unit": item.unit} if item.unit is not None else {}),
                    **(
                        {"type": item.type, "axis": item.axis}
                        if parsed.chart_type == "combo"
                        else {}
                    ),
                }
                for item in parsed.series
            ],
        }
    return chart_payload, records


async def _mark_sql_failed(
    sql_execution_id: uuid.UUID,
    *,
    status: str,
    code: str,
    message: str,
    duration_ms: int,
) -> None:
    async with get_session_factory()() as session:
        item = await session.get(SQLExecution, sql_execution_id)
        if item is None:
            return
        item.status = status
        item.error_code = code[:100]
        item.error_message = message[:2000]
        item.duration_ms = duration_ms
        item.finished_at = utc_now()
        await session.commit()


async def get_current_time(
    context: AgentToolContext, arguments: dict[str, object], _tool_id: uuid.UUID
) -> dict[str, object]:
    parsed = GetCurrentTimeArgs.model_validate(arguments)
    timezone = parsed.timezone or (context.time_context.timezone if context.time_context else "UTC")
    return {"ok": True, **clock_snapshot(timezone)}


def build_default_tool_registry() -> AgentToolRegistry:
    registry = AgentToolRegistry()
    registry.register(AgentToolDefinition(
        name="get_current_time",
        description=(
            "Read the application server's current UTC and local date/time, timezone, and UTC "
            "offset. Defaults to the request timezone; optionally specify another IANA timezone. "
            "Use for a fresh clock reading or a time-only question; no datasource discovery or "
            "SQL is needed. Does not change the question's reference time or prove data freshness."
        ),
        args_schema=GetCurrentTimeArgs,
        handler=get_current_time,
    ))
    registry.register(
        AgentToolDefinition(
            name="read_knowledge_index",
            description=(
                "Start data discovery for one authorized datasource. Returns its compact table/view "
                "catalog plus datasource- and metric-level business guidance; it does not return "
                "columns or data rows. When the user selected tables, it lists those and counts the "
                "rest; set include_all_tables=true to list every table. Call this before "
                "read_table_schema or execute_sql, use it to shortlist likely tables, and revisit "
                "discovery if the first candidates are not sufficient."
            ),
            args_schema=ReadKnowledgeIndexArgs,
            handler=read_knowledge_index,
        )
    )
    registry.register(
        AgentToolDefinition(
            name="read_table_schema",
            description=(
                "Inspect one exact table or view selected from read_knowledge_index. Returns verified "
                "columns, native types, keys, relationships, and relevant table/column annotations; "
                "it does not return data rows. Read the schema of every table you intend to reference "
                "in SQL. If it cannot support the question, inspect another indexed table instead of "
                "guessing identifiers."
            ),
            args_schema=ReadTableSchemaArgs,
            handler=read_table_schema,
        )
    )
    registry.register(
        AgentToolDefinition(
            name="execute_sql",
            description=(
                "Run one read-only analytical statement after inspecting the knowledge index and the "
                "schema of every referenced table. Use the datasource's native SQL dialect and only "
                "verified identifiers. The server validates, limits, executes, and audits the query, "
                "then returns a bounded preview and persists a table artifact. If an identifier fails, "
                "read the missing schema before retrying; do not guess successive names. Choose display "
                "to ensure the result appears only once in the final presentation."
            ),
            args_schema=ExecuteSQLArgs,
            handler=execute_sql,
        )
    )
    registry.register(
        AgentToolDefinition(
            name="create_chart",
            description=(
                "Create a frontend visualization from one successful execute_sql result in this job. "
                "Use metric for a headline figure from one aggregate row: one to six cards, each with "
                "an optional comparison column (the UI calculates the change), supporting figures, "
                "format, icon and tone. Use line or area for an ordered trend, bar for category "
                "comparison, and pie or donut for a small part-to-whole result. Bar charts support "
                "orientation='horizontal' or 'vertical' and stacked=true for additive components "
                "in the same unit. Use combo with stacked=true for a line and stacked column chart: "
                "each series declares type='bar' or 'line', columns use axis='primary', and lines "
                "use primary for a shared scale or secondary for another scale/unit. Multiple lines "
                "and columns are supported. Units on each axis must agree. Reference exact output "
                "fields; this tool reads persisted rows and never accepts invented values. The SQL must "
                "already have the final grain, ordering, and manageable category count. For bar, line, "
                "and area charts, return one row per x-axis value and one distinct numeric output column "
                "per series. A series label never filters long-form category rows. Do not create a chart "
                "when a table or sentence communicates the result more clearly."
            ),
            args_schema=CreateChartArgs,
            handler=create_chart,
        )
    )
    if get_settings().agent_matrix_enabled:
        registry.register(AgentToolDefinition(
            name="create_matrix",
            description=(
                "Present exact comparisons across two or more dimensions as an interactive matrix. "
                "Reference one complete successful execute_sql result in this job; supply only field "
                "mappings, never numbers or HTML. SQL must return unique detail cells and every requested "
                "subtotal with row_depth_field/column_depth_field integers (active prefix lengths; "
                "0 means grand total). Totals are SQL values, never sums of visible cells. "
                "Use SQL GROUPING flags to distinguish totals from real NULL categories. Use sort_field "
                "for ordering and numeric/date sort_type for numeric/date dimensions. "
                "All grouping and measure definitions come from SQL and knowledge. Turn off totals for "
                "a leaf-only result. Prefer ordinary tables for lists and lookups, a metric card "
                "for a headline figure, and charts for visual trends."
            ), args_schema=CreateMatrixArgs, handler=create_matrix,
        ))
    registry.register(
        AgentToolDefinition(
            name="create_html_artifact",
            description=(
                "Create one separately stored, self-contained HTML document for a custom result "
                "that a normal answer, table, or chart cannot present well. Supply exactly one "
                "complete HTML document with inline CSS and optional inline JavaScript. External "
                "resources and Markdown fences are not allowed. If the document presents queried "
                "data, reference the successful SQL execution from this job and use only its values."
            ),
            args_schema=CreateHtmlArtifactArgs,
            handler=create_html_artifact,
        )
    )
    registry.register(
        AgentToolDefinition(
            name="ask_user",
            description=(
                "Ask the user clarifying questions when an ambiguity would materially change the "
                "result and cannot be resolved from the schema, knowledge, saved instructions or "
                f"conversation. Put every question you need in one call (at most {MAX_QUESTIONS}), "
                "one decision per question. Use 'choice' questions with concrete fields or values "
                "from the data (the interface always adds 'Other' with a text box) or 'text' "
                "questions for free-form details. Questions must be answerable by choosing or "
                "typing; never ask for files, screenshots, or uploads. The interface also adds an "
                "optional 'Anything else I should know?' box. Call it alone, before running large "
                "queries. The turn ends after this call and the answers arrive in the user's next "
                "message."
            ),
            args_schema=AskUserArgs,
            handler=ask_user,
            ends_turn=True,
        )
    )
    from app.agent.management_tools import (
        edit_skill,
        read_saved_context,
        save_knowledge,
        save_skill,
    )
    from app.agent.tool_schemas import (
        EditSkillArgs,
        ReadSavedContextArgs,
        SaveKnowledgeArgs,
        SaveSkillArgs,
    )

    for name, description, schema, handler in (
        (
            "read_saved_context",
            "Read existing business knowledge or workspace skills. Lists IDs and summaries; pass item_id to read an item in full before updating it.",
            ReadSavedContextArgs,
            read_saved_context,
        ),
        (
            "save_knowledge",
            "Create or update a business definition, mapping, or rule only when the current user explicitly requests saving it. Supply their exact authorization quote. Use annotation_id only after reading the existing note; omit it to create one.",
            SaveKnowledgeArgs,
            save_knowledge,
        ),
        (
            "save_skill",
            "Save the user's approved format or approach as a reusable workspace skill only on an explicit current user save request. Create by default; replace a specifically requested existing skill only when it is rewritten as a whole. It does not change the workspace default.",
            SaveSkillArgs,
            save_skill,
        ),
        (
            "edit_skill",
            "Make small changes to an existing skill on an explicit current user request: replace, insert, append, or delete specific text without rewriting the rest. Read the skill in full first and pass its content_hash. Prefer this over save_skill for partial changes.",
            EditSkillArgs,
            edit_skill,
        ),
    ):
        registry.register(
            AgentToolDefinition(
                name=name, description=description, args_schema=schema, handler=handler
            )
        )
    return registry


async def ask_user(
    context: AgentToolContext,
    arguments: dict[str, object],
    tool_execution_id: uuid.UUID,
) -> dict[str, object]:
    async with get_session_factory()() as session:
        # Rounds already answered in this paused-and-resumed job; the waiting call is unfinished.
        answered = await AgentExecutionRepository(session).count_tools(
            context.job_id, tool_name="ask_user", status="succeeded"
        )
    if context.clarification_round + answered >= MAX_ROUNDS:
        raise AgentToolError(
            "CLARIFICATION_LIMIT_REACHED",
            "The user already answered clarifying questions for this request. Continue with "
            "the best interpretation and state your assumptions in the answer.",
        )
    try:
        request = build_request(AskUserArgs.model_validate(arguments))
    except ClarificationError as exc:
        raise AgentToolError("CLARIFICATION_INVALID", str(exc)) from exc
    if not context.pausable:
        await append_agent_event(
            context.job_id,
            "clarification.requested",
            {"question_count": len(request["questions"])},
        )
        return {"ok": True, "clarification": request}
    # Pauses the run until the user answers; on resume the same call returns their answers.
    reply = interrupt(request)
    if not isinstance(reply, dict):
        raise AgentToolError("CLARIFICATION_ANSWERS_INVALID", "The answers could not be read.")
    return {
        "ok": True,
        "user_answers": reply.get("text"),
        "answers": reply.get("answers"),
        "guidance": "Continue the original request using these answers. Do not ask again about "
        "the same points.",
    }


def tool_result_json(payload: dict[str, object]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)


def enforce_tool_preconditions(
    name: str,
    arguments: dict[str, object],
    *,
    loaded_knowledge_indexes: set[uuid.UUID],
) -> None:
    """Enforce deterministic orchestration prerequisites outside the model prompt."""

    if name != "read_table_schema":
        return
    try:
        source_id = uuid.UUID(str(arguments.get("data_source_id")))
    except (TypeError, ValueError, AttributeError) as exc:
        raise AgentToolError(
            "TOOL_ARGUMENT_INVALID", "A valid data_source_id is required."
        ) from exc
    if source_id not in loaded_knowledge_indexes:
        raise AgentToolError(
            "KNOWLEDGE_INDEX_REQUIRED",
            "Read the datasource knowledge index before requesting table schemas.",
        )


class AuditedToolExecutor:
    """Applies DB Assistant limits/audit/events around tools invoked by Deep Agents."""

    def __init__(self, context: AgentToolContext, registry: AgentToolRegistry) -> None:
        self.context = context
        self.registry = registry
        self._sequence_lock = asyncio.Lock()
        self._loaded_knowledge_indexes: set[uuid.UUID] = set()

    async def invoke(self, name: str, arguments: dict[str, object]) -> str:
        definition = self.registry.get(name)
        if definition is None:
            return tool_result_json(
                {"ok": False, "error": {"code": "TOOL_NOT_FOUND", "message": "Tool not found."}}
            )
        if await is_cancel_requested(self.context.job_id):
            raise AgentCancelledError

        try:
            parsed = definition.args_schema.model_validate(arguments)
        except ValidationError:
            return tool_result_json(
                {
                    "ok": False,
                    "error": {
                        "code": "TOOL_ARGUMENT_INVALID",
                        "message": "The tool arguments are invalid.",
                    },
                }
            )
        safe_arguments = parsed.model_dump(mode="json")

        async with self._sequence_lock:
            async with get_session_factory()() as session:
                repo = AgentExecutionRepository(session)
                # A resumed run repeats the paused call; continue its audit record.
                paused = (
                    await repo.started_tool(self.context.job_id, name)
                    if definition.ends_turn and self.context.pausable
                    else None
                )
                total_calls = await repo.count_tools(self.context.job_id)
                if paused is None and total_calls >= self.context.settings.agent_max_tool_calls:
                    raise AgentLimitError(
                        "AGENT_TOOL_LIMIT_EXCEEDED",
                        "The analytical job exceeded its maximum tool-call limit.",
                    )
                if name == "execute_sql":
                    sql_attempts = await repo.count_tools(
                        self.context.job_id, tool_name="execute_sql"
                    )
                    if sql_attempts >= self.context.settings.agent_max_sql_attempts:
                        raise AgentLimitError(
                            "AGENT_SQL_ATTEMPT_LIMIT_EXCEEDED",
                            "The analytical job exceeded its maximum SQL-attempt limit.",
                        )
                if paused is not None:
                    tool_execution_id = paused.id
                else:
                    sequence = await repo.next_tool_sequence(self.context.job_id)
                    item = ToolExecution(
                        job_id=self.context.job_id,
                        sequence=sequence,
                        tool_name=name,
                        status="started",
                        input_summary=_safe_tool_input(name, safe_arguments),
                        started_at=utc_now(),
                    )
                    repo.add_tool(item)
                    await session.commit()
                    tool_execution_id = item.id

        await append_agent_event(
            self.context.job_id,
            "tool.started",
            {"tool_execution_id": str(tool_execution_id), "tool_name": name},
        )

        try:
            enforce_tool_preconditions(
                name,
                safe_arguments,
                loaded_knowledge_indexes=self._loaded_knowledge_indexes,
            )
            result = await definition.handler(self.context, safe_arguments, tool_execution_id)
            if name == "read_knowledge_index" and bool(result.get("data_source_id")):
                self._loaded_knowledge_indexes.add(uuid.UUID(str(result["data_source_id"])))
        except GraphBubbleUp:
            # A LangGraph interrupt pauses the run; the call stays "started" until it resumes.
            raise
        except AgentCancelledError:
            await self._finish_tool(
                tool_execution_id,
                status="cancelled",
                error_code="JOB_CANCELLED",
                error_message="Tool execution was cancelled.",
            )
            await append_agent_event(
                self.context.job_id,
                "tool.cancelled",
                {"tool_execution_id": str(tool_execution_id), "tool_name": name},
            )
            raise
        except AgentLimitError:
            raise
        except AgentToolError as exc:
            await self._finish_tool(
                tool_execution_id,
                status="failed",
                error_code=exc.code,
                error_message=exc.public_message,
            )
            await append_agent_event(
                self.context.job_id,
                "tool.failed",
                {
                    "tool_execution_id": str(tool_execution_id),
                    "tool_name": name,
                    "code": exc.code,
                },
                level="warning",
            )
            # Tool/domain failures are observations the agent may correct. Credentials and raw
            # driver/provider exceptions are never included.
            return tool_result_json(
                {
                    "ok": False,
                    "error": {
                        "code": exc.code,
                        "message": exc.public_message,
                        "retryable": exc.retryable,
                    },
                }
            )
        except Exception:
            await self._finish_tool(
                tool_execution_id,
                status="failed",
                error_code="TOOL_EXECUTION_FAILED",
                error_message="The tool failed unexpectedly.",
            )
            await append_agent_event(
                self.context.job_id,
                "tool.failed",
                {
                    "tool_execution_id": str(tool_execution_id),
                    "tool_name": name,
                    "code": "TOOL_EXECUTION_FAILED",
                },
                level="error",
            )
            return tool_result_json(
                {
                    "ok": False,
                    "error": {
                        "code": "TOOL_EXECUTION_FAILED",
                        "message": "The tool failed unexpectedly.",
                    },
                }
            )

        await self._finish_tool(
            tool_execution_id,
            status="succeeded",
            output_summary=_safe_tool_output(name, result),
        )
        await append_agent_event(
            self.context.job_id,
            "tool.completed",
            {"tool_execution_id": str(tool_execution_id), "tool_name": name},
        )
        if definition.ends_turn and "clarification" in result:
            raise AgentTurnEnded(name, result)
        return tool_result_json(result)

    async def _finish_tool(
        self,
        tool_execution_id: uuid.UUID,
        *,
        status: str,
        output_summary: dict[str, object] | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> None:
        async with get_session_factory()() as session:
            item = await session.get(ToolExecution, tool_execution_id)
            if item is None:
                return
            item.status = status
            item.output_summary = output_summary
            item.error_code = error_code[:100] if error_code else None
            item.error_message = error_message[:2000] if error_message else None
            item.finished_at = utc_now()
            await session.commit()


def _safe_tool_input(name: str, arguments: dict[str, object]) -> dict[str, object]:
    if name in {"save_knowledge", "save_skill"}:
        return {key: value for key, value in arguments.items() if key != "content"}
    if name == "edit_skill":
        edits = arguments.get("edits")
        return {
            "instruction_id": arguments.get("instruction_id"),
            "content_hash": arguments.get("content_hash"),
            "authorization_quote": arguments.get("authorization_quote"),
            "edit_ops": [item.get("op") for item in edits] if isinstance(edits, list) else [],
        }
    if name == "execute_sql":
        return {
            "data_source_id": arguments.get("data_source_id"),
            "sql": arguments.get("sql"),
        }
    if name == "create_html_artifact":
        html = arguments.get("html")
        return {
            "title": arguments.get("title"),
            "source_sql_execution_id": arguments.get("source_sql_execution_id"),
            "size_bytes": len(str(html).encode("utf-8")) if html is not None else 0,
        }
    return arguments


def _safe_tool_output(name: str, result: dict[str, object]) -> dict[str, object]:
    # Avoid duplicating result rows into the tool audit record. Full bounded rows already live in
    # a table artifact; the Deep Agent receives the bounded tool return directly.
    if name == "execute_sql":
        return {key: value for key, value in result.items() if key not in {"rows"}}
    if name == "read_saved_context":
        return {"kind": result.get("kind"), "item_count": len(result.get("items", []))}
    if name in {"read_knowledge_index", "read_table_schema"}:
        return {key: value for key, value in result.items() if not key.endswith("_markdown")}
    return result
