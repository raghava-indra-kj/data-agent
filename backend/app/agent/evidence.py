from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import dataclass, replace

import sqlglot
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlglot import expressions as exp

from app.agent.models import JobArtifact, SQLExecution
from app.agent.repository import AgentExecutionRepository
from app.agent.sql_safety import SQLSafetyViolation, dialect_for_source
from app.agent.time_context import RequestTimeContext, is_time_only_question
from app.data_sources.models import DataSource

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SQLResultEvidence:
    execution_id: uuid.UUID
    tool_sequence: int
    data_source_id: uuid.UUID
    sql_text: str
    columns: tuple[str, ...]
    rows: tuple[tuple[object, ...], ...]
    stored_row_count: int
    preview_row_count: int
    preview_truncated: bool
    stored_result_truncated: bool
    is_aggregate: bool
    table_artifact_id: uuid.UUID | None
    title: str
    display: str
    classification_error: str | None = None


@dataclass(frozen=True, slots=True)
class ArtifactEvidence:
    artifact_id: uuid.UUID
    kind: str
    title: str
    source_sql_execution_id: uuid.UUID | None
    payload: dict[str, object]
    valid: bool
    visible: bool = False
    source_dax_execution_id: uuid.UUID | None = None


@dataclass(frozen=True, slots=True)
class DaxResultEvidence:
    execution_id: uuid.UUID
    data_source_id: uuid.UUID
    dax_text: str
    columns: tuple[str, ...]
    rows: tuple[tuple[object, ...], ...]
    truncated: bool
    preview_truncated: bool
    context: dict[str, object]


@dataclass(frozen=True, slots=True)
class EvidenceBundle:
    job_id: uuid.UUID
    question: str
    analyst_notes: str
    sql_results: tuple[SQLResultEvidence, ...]
    artifacts: tuple[ArtifactEvidence, ...]
    unavailable_information: bool
    management_results: tuple[dict[str, object], ...] = ()
    dax_results: tuple[DaxResultEvidence, ...] = ()
    time_context: RequestTimeContext | None = None
    clock_results: tuple[dict[str, object], ...] = ()
    current_time: dict[str, str] | None = None

    @property
    def visible_artifacts(self) -> tuple[ArtifactEvidence, ...]:
        return tuple(item for item in self.artifacts if item.visible)


class EvidenceSQLClassificationError(ValueError):
    def __init__(self, code: str, message: str, *, dialect: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.dialect = dialect


def is_aggregate_sql(sql: str, *, source_kind: str) -> bool:
    try:
        dialect = dialect_for_source(source_kind)
    except SQLSafetyViolation as exc:
        raise EvidenceSQLClassificationError(
            exc.code, f"Unsupported datasource type {source_kind!r} for evidence classification."
        ) from exc
    try:
        statement = sqlglot.parse_one(sql, read=dialect)
    except sqlglot.errors.ParseError as exc:
        raise EvidenceSQLClassificationError(
            "EVIDENCE_SQL_PARSE_FAILED",
            f"Evidence SQL could not be parsed using dialect {dialect!r}.",
            dialect=dialect,
        ) from exc
    return statement.find(exp.AggFunc) is not None or statement.find(exp.Group) is not None


def notes_report_unavailable(notes: str) -> bool:
    match = re.search(r"(?ims)^##\s+Unavailable information\s*$\s*(.*?)(?=^##\s+|\Z)", notes)
    if match is None:
        return False
    body = re.sub(r"[`*_]", "", match.group(1)).strip().strip(".- ").casefold()
    return body not in {"", "none", "not applicable", "n/a", "nothing"}


def _payload_rows(payload: dict[str, object]) -> tuple[tuple[object, ...], ...]:
    raw = payload.get("rows")
    if not isinstance(raw, list):
        return ()
    return tuple(tuple(row) for row in raw if isinstance(row, list))


def _payload_columns(payload: dict[str, object]) -> tuple[str, ...]:
    raw = payload.get("columns")
    if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
        return ()
    return tuple(raw)


def _valid_table_artifact(payload: dict[str, object], source: SQLExecution | None) -> bool:
    columns = _payload_columns(payload)
    rows = _payload_rows(payload)
    return bool(
        source is not None
        and payload.get("schema_version") == 1
        and columns
        and isinstance(payload.get("rows"), list)
        and payload.get("row_count") == len(rows)
        and source.row_count == len(rows)
        and columns == tuple(source.columns or ())
        and payload.get("data_source_id") == str(source.data_source_id)
        and (payload.get("truncated") is True) == source.truncated
    )


def _valid_chart_artifact(payload: dict[str, object], source: SQLExecution | None) -> bool:
    if (
        source is None
        or payload.get("schema_version") != 1
        or payload.get("renderer") != "frontend"
        or payload.get("source_sql_execution_id") != str(source.id)
    ):
        return False
    chart_type = payload.get("chart_type")
    if chart_type not in {"bar", "line", "area", "pie", "donut", "metric", "combo"}:
        return False
    orientation = payload.get("orientation", "vertical")
    stacked = payload.get("stacked", False)
    if orientation not in ("vertical", "horizontal") or not isinstance(stacked, bool):
        return False
    if chart_type not in {"bar", "combo"} and (orientation != "vertical" or stacked):
        return False
    data = payload.get("data")
    encoding = payload.get("encoding")
    if not isinstance(data, list) or not all(isinstance(item, dict) for item in data):
        return False
    if not isinstance(encoding, dict):
        return False
    if chart_type == "combo":
        if source.truncated:
            return False
        # Reuse the creation contract for saved artifacts and final-answer evidence.
        from pydantic import ValidationError

        from app.agent.tool_schemas import CreateChartArgs
        from app.agent.tools import AgentToolError, build_frontend_chart_payload

        try:
            spec = CreateChartArgs(
                sql_execution_id=source.id,
                chart_type="combo",
                title=payload.get("title"),
                x_field=(encoding.get("x") or {}).get("field"),
                series=encoding.get("series"),
                orientation=orientation,
                stacked=stacked,
                y_label=payload.get("y_label"),
                secondary_y_label=payload.get("secondary_y_label"),
            )
            columns = list(source.columns or [])
            build_frontend_chart_payload(
                spec, columns, [[row.get(column) for column in columns] for row in data]
            )
        except (ValidationError, AgentToolError, TypeError, AttributeError, ValueError):
            return False

    def encoded_field(value: object) -> str | None:
        if not isinstance(value, dict):
            return None
        field = value.get("field")
        return field if isinstance(field, str) and field else None

    fields: list[str]
    if chart_type in {"pie", "donut"}:
        category = encoded_field(encoding.get("category"))
        value = encoded_field(encoding.get("value"))
        if category is None or value is None:
            return False
        fields = [category, value]
    elif chart_type == "metric":
        from pydantic import ValidationError

        from app.agent.tool_schemas import MAX_METRICS, MetricInput

        raw_metrics = encoding.get("metrics")
        if not isinstance(raw_metrics, list) or not 1 <= len(raw_metrics) <= MAX_METRICS:
            return False
        try:
            metrics = [MetricInput.model_validate(item) for item in raw_metrics]
        except ValidationError:
            return False
        if len(data) != 1:
            return False
        fields = [field for item in metrics for field in item.referenced_fields()]
    else:
        x_field = encoded_field(encoding.get("x"))
        series = encoding.get("series")
        if x_field is None or not isinstance(series, list) or not series:
            return False
        series_fields = [encoded_field(item) for item in series]
        if any(field is None for field in series_fields):
            return False
        fields = [x_field, *(field for field in series_fields if field is not None)]
    source_columns = set(source.columns or ())
    return all(field in source_columns for field in fields) and all(
        all(field in row for field in fields) for row in data
    )


async def collect_evidence(
    session: AsyncSession,
    *,
    job_id: uuid.UUID,
    question: str,
    analyst_notes: str,
) -> EvidenceBundle:
    repo = AgentExecutionRepository(session)
    tools = await repo.list_tools(job_id)
    sql_items = await repo.list_sql(job_id)
    dax_items = await repo.list_dax(job_id) if any(item.tool_name == "execute_dax" for item in tools) else []
    successful_dax = {item.id: item for item in dax_items if item.status == "succeeded"}
    artifact_items = await repo.list_artifacts(job_id)
    tool_sequence = {item.id: item.sequence for item in tools}
    tools_by_id = {item.id: item for item in tools}
    fallback_source_kinds: dict[uuid.UUID, str | None] = {}
    tables_by_sql: dict[uuid.UUID, JobArtifact] = {}
    for artifact in artifact_items:
        if artifact.kind == "table" and artifact.source_sql_execution_id is not None:
            tables_by_sql.setdefault(artifact.source_sql_execution_id, artifact)

    successful_sql = {item.id: item for item in sql_items if item.status == "succeeded"}
    successful_ids = set(successful_sql)
    sql_results: list[SQLResultEvidence] = []
    for sql_item in sql_items:
        if sql_item.status != "succeeded":
            continue
        table = tables_by_sql.get(sql_item.id)
        payload = table.payload if table is not None and isinstance(table.payload, dict) else {}
        rows = _payload_rows(payload)
        columns = tuple(sql_item.columns or ()) or _payload_columns(payload)
        stored_count = sql_item.row_count if sql_item.row_count is not None else len(rows)
        raw_preview_count = payload.get("model_preview_row_count")
        preview_count = (
            raw_preview_count
            if isinstance(raw_preview_count, int) and raw_preview_count >= 0
            else stored_count
        )
        preview_truncated = bool(
            sql_item.truncated or payload.get("model_preview_truncated") is True
        )
        display = str(payload.get("display") or "auto")
        tool = tools_by_id.get(sql_item.tool_execution_id)
        summary = tool.output_summary if tool is not None and tool.status == "succeeded" else None
        source_kind = summary.get("source_kind") if isinstance(summary, dict) else None
        if not isinstance(source_kind, str) or not source_kind.strip():
            # Older execution records may lack the server-captured datasource kind.
            # Read only the kind, once per datasource; never infer it from SQL syntax.
            if sql_item.data_source_id not in fallback_source_kinds:
                fallback_source_kinds[sql_item.data_source_id] = await session.scalar(
                    select(DataSource.kind).where(DataSource.id == sql_item.data_source_id)
                )
            source_kind = fallback_source_kinds[sql_item.data_source_id]

        classification_error = None
        is_aggregate = False
        try:
            if source_kind is None:
                raise EvidenceSQLClassificationError(
                    "EVIDENCE_SOURCE_KIND_MISSING",
                    "Datasource type is unavailable for evidence classification.",
                )
            is_aggregate = is_aggregate_sql(sql_item.sql_text, source_kind=source_kind)
        except EvidenceSQLClassificationError as exc:
            classification_error = f"{exc.code}: {exc}"
            logger.warning(
                "evidence_sql_classification_failed",
                extra={
                    "job_id": str(job_id),
                    "sql_execution_id": str(sql_item.id),
                    "source_kind": source_kind,
                    "dialect": exc.dialect,
                    "error_code": exc.code,
                },
            )
        sql_results.append(
            SQLResultEvidence(
                execution_id=sql_item.id,
                tool_sequence=tool_sequence.get(sql_item.tool_execution_id, 0),
                data_source_id=sql_item.data_source_id,
                sql_text=sql_item.sql_text,
                columns=columns,
                rows=rows,
                stored_row_count=stored_count,
                preview_row_count=preview_count,
                preview_truncated=preview_truncated,
                stored_result_truncated=sql_item.truncated,
                is_aggregate=is_aggregate,
                table_artifact_id=table.id if table is not None else None,
                title=(table.name or "Query result") if table is not None else "Query result",
                display=display,
                classification_error=classification_error,
            )
        )

    artifacts: list[ArtifactEvidence] = []
    for artifact_item in artifact_items:
        payload = artifact_item.payload if isinstance(artifact_item.payload, dict) else {}
        source_ok = (
            artifact_item.source_sql_execution_id is None
            or artifact_item.source_sql_execution_id in successful_ids
        )
        source = (
            successful_sql.get(artifact_item.source_sql_execution_id)
            if artifact_item.source_sql_execution_id is not None
            else None
        )
        dax_source_id = getattr(artifact_item, "source_dax_execution_id", None)
        if dax_source_id is not None:
            source = successful_dax.get(dax_source_id)
            source_ok = source is not None
        if artifact_item.kind == "table":
            valid = source_ok and _valid_table_artifact(payload, source)
        elif artifact_item.kind == "chart":
            chart_payload = {**payload, "source_sql_execution_id": str(dax_source_id)} if dax_source_id else payload
            valid = source_ok and _valid_chart_artifact(chart_payload, source)
        elif artifact_item.kind == "matrix":
            from app.agent.matrix import validate_stored_matrix

            table = tables_by_sql.get(artifact_item.source_sql_execution_id)
            valid = False
            if (
                source is not None
                and table is not None
                and _valid_table_artifact(table.payload, source)
            ):
                valid = validate_stored_matrix(
                    payload, source.id, table.payload, truncated=source.truncated
                )
        elif artifact_item.kind == "html":
            valid = bool(
                source_ok
                and payload.get("schema_version") == 1
                and payload.get("file_name") == "index.html"
                and isinstance(payload.get("size_bytes"), int)
                and int(payload["size_bytes"]) > 0
            )
        else:
            valid = artifact_item.kind == "text"
        artifacts.append(
            ArtifactEvidence(
                artifact_id=artifact_item.id,
                kind=artifact_item.kind,
                title=artifact_item.name or "Output",
                source_sql_execution_id=artifact_item.source_sql_execution_id,
                payload=payload,
                valid=valid,
                source_dax_execution_id=dax_source_id,
            )
        )

    visible_artifacts = mark_visible_artifacts(artifacts)

    return EvidenceBundle(
        job_id=job_id,
        question=question,
        analyst_notes=analyst_notes,
        sql_results=tuple(sql_results),
        dax_results=tuple(
            DaxResultEvidence(
                execution_id=item.id, data_source_id=item.data_source_id, dax_text=item.dax_text,
                columns=tuple(item.columns or ()), rows=_payload_rows(table.payload),
                truncated=item.truncated,
                preview_truncated=table.payload.get("model_preview_truncated") is True,
                context=item.context,
            )
            for item in successful_dax.values()
            for table in artifact_items
            if table.kind == "table" and getattr(table, "source_dax_execution_id", None) == item.id
        ),
        artifacts=visible_artifacts,
        unavailable_information=notes_report_unavailable(analyst_notes),
        clock_results=tuple(
            dict(item.output_summary)
            for item in tools
            if item.tool_name == "get_current_time" and item.status == "succeeded"
            and isinstance(item.output_summary, dict) and item.output_summary.get("ok") is True
        ),
        management_results=tuple(
            {
                "tool": item.tool_name,
                "status": item.status,
                "result": item.output_summary
                if item.status == "succeeded"
                else {"error_code": item.error_code, "error_message": item.error_message},
            }
            for item in tools
            if item.tool_name in {"save_knowledge", "save_skill", "edit_skill"}
            and item.status in {"succeeded", "failed"}
        ),
    )


def mark_visible_artifacts(
    artifacts: list[ArtifactEvidence] | tuple[ArtifactEvidence, ...],
) -> tuple[ArtifactEvidence, ...]:
    has_chart = any(item.kind == "chart" and item.valid for item in artifacts)
    has_nonempty_table = any(_is_nonempty_table(item) for item in artifacts)
    visible_artifacts: list[ArtifactEvidence] = []
    seen_renderables: set[str] = set()
    for artifact_evidence in artifacts:
        visible = False
        if artifact_evidence.valid and artifact_evidence.kind in {"chart", "matrix"}:
            signature = _renderable_signature(artifact_evidence)
            if signature not in seen_renderables:
                seen_renderables.add(signature)
                visible = True
        elif artifact_evidence.valid and artifact_evidence.kind == "html":
            visible = True
        elif artifact_evidence.valid and artifact_evidence.kind == "table":
            display = str(artifact_evidence.payload.get("display") or "auto")
            row_count = artifact_evidence.payload.get("row_count")
            exploratory_empty = (
                display == "auto" and row_count == 0 and (has_chart or has_nonempty_table)
            )
            if display != "hidden" and not exploratory_empty:
                signature = _renderable_signature(artifact_evidence)
                if signature not in seen_renderables:
                    seen_renderables.add(signature)
                    visible = True
        visible_artifacts.append(replace(artifact_evidence, visible=visible))

    # A large stored detail result cannot be represented faithfully in the bounded finalizer
    # context. If analysis hid every output, expose the largest such table as an explicit inline
    # candidate rather than encouraging the writer to invent a directive from an execution ID.
    if not any(item.visible for item in visible_artifacts):
        large_hidden_tables = [
            (index, item)
            for index, item in enumerate(visible_artifacts)
            if item.kind == "table"
            and item.valid
            and item.payload.get("display") == "hidden"
            and isinstance(item.payload.get("row_count"), int)
            and int(item.payload["row_count"]) > 50
        ]
        if large_hidden_tables:
            index, _ = max(
                large_hidden_tables,
                key=lambda pair: int(pair[1].payload["row_count"]),
            )
            visible_artifacts[index] = replace(visible_artifacts[index], visible=True)
    return tuple(visible_artifacts)


def _renderable_signature(item: ArtifactEvidence) -> str:
    payload = {
        key: value for key, value in item.payload.items() if key != "source_sql_execution_id"
    }
    return json.dumps(
        {"kind": item.kind, "title": item.title, "payload": payload},
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _is_nonempty_table(item: ArtifactEvidence) -> bool:
    row_count = item.payload.get("row_count")
    return item.kind == "table" and item.valid and isinstance(row_count, int) and row_count > 0


def validate_evidence(bundle: EvidenceBundle) -> list[str]:
    issues: list[str] = []
    if (
        not bundle.sql_results
        and not bundle.dax_results
        and not bundle.unavailable_information
        and not bundle.management_results
        and not (
            (bundle.time_context is not None or bundle.clock_results)
            and is_time_only_question(bundle.question)
        )
    ):
        issues.append(
            "No successful analytical SQL supports the answer, and the notes do not establish "
            "that the requested information is unavailable."
        )

    for result in bundle.dax_results:
        if result.truncated or result.preview_truncated:
            # A complete follow-up from the same model is required; the finalizer also receives
            # explicit truncation metadata and may not extrapolate from the partial table.
            if not any(item.data_source_id == result.data_source_id and not item.truncated
                       and not item.preview_truncated for item in bundle.dax_results):
                issues.append(f"DAX execution {result.execution_id} is partial. Query a complete aggregate before answering.")
    for artifact in bundle.artifacts:
        if artifact.kind != "text" and not artifact.valid:
            issues.append(
                f"Artifact {artifact.artifact_id} ({artifact.kind}) is not grounded in a valid "
                "successful execution from this job."
            )

    aggregates = [
        item
        for item in bundle.sql_results
        if item.is_aggregate
        and not item.classification_error
        and not item.preview_truncated
        and not item.stored_result_truncated
    ]
    for detail in bundle.sql_results:
        if detail.classification_error:
            issues.append(
                f"SQL execution {detail.execution_id} could not be classified: "
                f"{detail.classification_error}"
            )
            continue
        if detail.is_aggregate or not detail.preview_truncated:
            continue
        if not any(item.tool_sequence > detail.tool_sequence for item in aggregates):
            issues.append(
                f"Detailed SQL execution {detail.execution_id} was only partially visible to the "
                "analysis model and has no later complete aggregate query supporting "
                "population-wide conclusions."
            )
    return issues


def build_evidence_correction(issues: list[str]) -> str:
    bullets = "\n".join(f"- {item}" for item in issues)
    return (
        "The analysis is not ready for finalization. Correct the evidence gaps below using the "
        "existing conversation and tool results. Execute only the additional aggregate or "
        "validation queries required; do not repeat an existing detail query. Then return a "
        "complete updated internal analysis handoff.\n\n"
        f"{bullets}"
    )


def _render_rows(item: SQLResultEvidence, *, limit: int) -> list[str]:
    lines = [" | ".join(item.columns)] if item.columns else []
    for row in item.rows[:limit]:
        lines.append(" | ".join("NULL" if value is None else str(value) for value in row))
    return lines


def render_evidence_context(bundle: EvidenceBundle) -> str:
    sections = [
        "ORIGINAL USER REQUEST\n" + bundle.question.strip(),
        "INTERNAL ANALYST NOTES\n" + bundle.analyst_notes.strip(),
    ]
    if bundle.management_results:
        sections.append(
            "VERIFIED WORKSPACE ACTION RESULTS\n"
            + json.dumps(bundle.management_results, ensure_ascii=False, default=str)
        )
    if bundle.clock_results:
        sections.append(
            "VERIFIED SERVER CLOCK READINGS (date/time facts only, not analytical evidence)\n"
            + json.dumps(bundle.clock_results, ensure_ascii=False)
        )
    sql_blocks: list[str] = []
    for sql_result in bundle.sql_results:
        lines = [
            f"SQL EVIDENCE: {sql_result.title}",
            f"Evidence kind: {'aggregate' if sql_result.is_aggregate else 'detail'}",
            f"Stored rows: {sql_result.stored_row_count}",
            f"Model preview rows: {sql_result.preview_row_count}",
            f"Preview truncated: {'Yes' if sql_result.preview_truncated else 'No'}",
            f"Stored result truncated: {'Yes' if sql_result.stored_result_truncated else 'No'}",
            f"Columns: {', '.join(sql_result.columns) if sql_result.columns else 'Unavailable'}",
            f"SQL: {sql_result.sql_text}",
        ]
        row_limit = 200 if sql_result.is_aggregate else 50
        if not sql_result.preview_truncated and len(sql_result.rows) <= row_limit:
            rendered = _render_rows(sql_result, limit=row_limit)
            if rendered:
                lines.extend(["Complete rows:", *rendered])
        else:
            lines.append(
                "Rows omitted from finalizer context; use the visible artifact for detail."
            )
        sql_blocks.append("\n".join(lines))
    sections.append("VERIFIED SQL EVIDENCE\n" + ("\n\n".join(sql_blocks) or "None."))
    if bundle.dax_results:
        sections.append("VERIFIED POWER BI DAX EVIDENCE\n" + json.dumps([
            {"execution_id": str(item.execution_id), "data_source_id": str(item.data_source_id),
             "dax": item.dax_text, "columns": item.columns,
             "rows": item.rows if not item.preview_truncated and len(item.rows) <= 200 else "See table artifact; do not extrapolate.",
             "truncated": item.truncated, "preview_truncated": item.preview_truncated,
             "report_context": item.context}
            for item in bundle.dax_results
        ], ensure_ascii=False, default=str))

    artifact_blocks = []
    for artifact in bundle.visible_artifacts:
        artifact_blocks.append(
            "\n".join(
                [
                    "DISPLAYABLE ARTIFACT",
                    f"ARTIFACT DIRECTIVE: [[artifact:{artifact.artifact_id}]]",
                    f"Type: {artifact.kind}",
                    f"Title: {artifact.title}",
                ]
            )
        )
    sections.append(
        "AVAILABLE ARTIFACT MANIFEST\n"
        + (
            "\n\n".join(artifact_blocks)
            if artifact_blocks
            else "No displayable artifacts. Do not emit artifact directives."
        )
    )
    sections.append(
        "VERIFIED AVAILABILITY STATUS\n"
        + (
            "The analyst established that at least one requested part is unavailable."
            if bundle.unavailable_information
            else "The analyst did not establish any unavailable requested information."
        )
    )
    return "\n\n---\n\n".join(sections)
