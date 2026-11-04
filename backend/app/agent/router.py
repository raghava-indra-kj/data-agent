from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse, Response
from pydantic import Field
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.agent.html_artifacts import HTML_CONTENT_SECURITY_POLICY, HtmlArtifactStorage
from app.agent.matrix import CreateMatrixArgs, MatrixError, MatrixViewState, validate_stored_matrix
from app.agent.models import JobArtifact
from app.agent.repository import AgentExecutionRepository
from app.agent.schemas import (
    DaxExecutionResponse,
    JobArtifactResponse,
    JobExecutionTraceResponse,
    ModelExecutionResponse,
    SQLExecutionResponse,
    ToolExecutionResponse,
)
from app.agent.table_rows import (
    DEFAULT_TABLE_PAGE_SIZE,
    MAX_TABLE_PAGE_SIZE,
    TRACE_TABLE_ROWS,
    StoredTable,
    StoredTableCache,
    TableRowsPage,
    TableView,
    first_page_info,
    stored_table,
    table_rows_page,
)
from app.auth.dependencies import get_current_organization
from app.core.config import Settings, get_settings
from app.core.database import get_db_session
from app.core.errors import AppError
from app.exports.excel import ExcelTableExport, build_excel, export_filename
from app.exports.matrix import build_matrix_excel
from app.jobs.service import JobService
from app.organizations.models import Organization, OrganizationMembership

router = APIRouter(prefix="/jobs", tags=["job execution"])


@router.post(
    "/{job_id}/artifacts/{artifact_id}/matrix/excel",
    response_class=Response,
    responses={
        200: {"content": {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {}}}
    },
)
async def export_matrix(
    job_id: uuid.UUID,
    artifact_id: uuid.UUID,
    state: MatrixViewState,
    context: tuple[Organization, OrganizationMembership] = Depends(get_current_organization),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> Response:
    organization, _ = context
    await JobService(session, settings).get_for_org(job_id, organization.id)
    artifact = await AgentExecutionRepository(session).get_artifact_for_job(job_id, artifact_id)
    if artifact is None or artifact.kind != "matrix":
        raise AppError("MATRIX_NOT_FOUND", "Matrix artifact not found.", 404)
    from app.agent.evidence import _valid_table_artifact

    repo = AgentExecutionRepository(session)
    source = await repo.get_sql_for_job(artifact.source_sql_execution_id, job_id)
    table = await repo.get_table_artifact_for_sql(job_id, artifact.source_sql_execution_id)
    if (
        source is None
        or source.status != "succeeded"
        or table is None
        or not _valid_table_artifact(table.payload, source)
        or not await run_in_threadpool(
            validate_stored_matrix,
            artifact.payload,
            source.id,
            table.payload,
            truncated=source.truncated,
        )
    ):
        raise AppError(
            "MATRIX_INVALID", "Matrix source evidence is unavailable or inconsistent.", 422
        )
    try:
        spec = CreateMatrixArgs.model_validate(artifact.payload.get("spec"))
        content = await run_in_threadpool(build_matrix_excel, artifact.payload, state)
    except MatrixError as exc:
        raise AppError(exc.code, str(exc), 422) from exc
    except (ValueError, KeyError, TypeError) as exc:
        raise AppError("MATRIX_INVALID", "The stored matrix is invalid.", 422) from exc
    return Response(
        content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{export_filename(spec.title)}"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get(
    "/{job_id}/artifacts/{artifact_id}/html",
    response_class=FileResponse,
    responses={200: {"content": {"text/html": {}}}},
)
async def get_html_artifact(
    job_id: uuid.UUID,
    artifact_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> FileResponse:
    """Serve a shareable POC HTML artifact; UUIDs are the public capability URL."""
    from app.jobs.repository import JobRepository
    job = await JobRepository(session).get(job_id)
    if job is not None and job.input.get("power_bi_private"):
        raise AppError("HTML_ARTIFACT_NOT_FOUND", "HTML artifact not found.", 404)
    artifact = await AgentExecutionRepository(session).get_artifact_for_job(job_id, artifact_id)
    if artifact is None or artifact.kind != "html":
        raise AppError("HTML_ARTIFACT_NOT_FOUND", "HTML artifact not found.", 404)
    payload = artifact.payload
    if payload.get("schema_version") != 1 or payload.get("file_name") != "index.html":
        raise AppError("HTML_ARTIFACT_INVALID", "HTML artifact metadata is invalid.", 500)
    path = HtmlArtifactStorage(
        settings.data_directory,
        settings.agent_html_artifact_max_bytes,
    ).path_for(job_id, artifact_id)
    if not path.is_file():
        raise AppError("HTML_ARTIFACT_FILE_MISSING", "HTML artifact file is unavailable.", 404)
    return FileResponse(
        path,
        media_type="text/html; charset=utf-8",
        headers={
            "Content-Security-Policy": HTML_CONTENT_SECURITY_POLICY,
            "Cache-Control": "public, max-age=300",
            "Referrer-Policy": "no-referrer",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/{job_id}/execution", response_model=JobExecutionTraceResponse)
async def get_job_execution_trace(
    job_id: uuid.UUID,
    context: tuple[Organization, OrganizationMembership] = Depends(get_current_organization),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> JobExecutionTraceResponse:
    organization, _ = context
    # Authorization is against the durable job's organization before exposing any trace rows.
    await JobService(session, settings).get_for_org(job_id, organization.id)
    repo = AgentExecutionRepository(session)
    return JobExecutionTraceResponse(
        tools=[
            ToolExecutionResponse.model_validate(item) for item in await repo.list_tools(job_id)
        ],
        sql=[SQLExecutionResponse.model_validate(item) for item in await repo.list_sql(job_id)],
        dax=[DaxExecutionResponse.model_validate(item) for item in await repo.list_dax(job_id)],
        models=[
            ModelExecutionResponse.model_validate(item) for item in await repo.list_model(job_id)
        ],
        artifacts=[
            trace_artifact(item, organization.id, settings)
            for item in await repo.list_artifacts(job_id)
        ],
    )


def trace_artifact(
    artifact: JobArtifact, organization_id: uuid.UUID, settings: Settings
) -> JobArtifactResponse:
    response = JobArtifactResponse.model_validate(artifact)
    rows = artifact.payload.get("rows")
    if artifact.kind != "table" or not isinstance(rows, list):
        return response
    # Copy rather than mutate the ORM payload, which the session would otherwise persist.
    return response.model_copy(update={
        "payload": {**artifact.payload, "rows": rows[:TRACE_TABLE_ROWS]},
        "table_rows": first_page_info(settings, organization_id, artifact.id, len(rows)),
    })


STORED_TABLES = StoredTableCache()


async def load_stored_table(
    session: AsyncSession,
    settings: Settings,
    organization_id: uuid.UUID,
    job_id: uuid.UUID,
    artifact_id: uuid.UUID,
) -> StoredTable:
    # Access is checked on every request; only the immutable rows come from the cache.
    await JobService(session, settings).get_for_org(job_id, organization_id)
    repo = AgentExecutionRepository(session)
    if await repo.artifact_kind_for_job(job_id, artifact_id) != "table":
        raise AppError("TABLE_ARTIFACT_NOT_FOUND", "Table artifact not found.", 404)
    table = STORED_TABLES.get(artifact_id)
    if table is None:
        table = stored_table(await repo.artifact_payload(artifact_id) or {})
        STORED_TABLES.put(artifact_id, table)
    return table


@router.get("/{job_id}/artifacts/{artifact_id}/rows", response_model=TableRowsPage)
async def list_table_rows(
    job_id: uuid.UUID,
    artifact_id: uuid.UUID,
    sort: str | None = Query(default=None, max_length=512),
    descending: bool = False,
    search: str = Query(default="", max_length=240),
    cursor: str | None = Query(default=None, max_length=1024),
    limit: int = Query(default=DEFAULT_TABLE_PAGE_SIZE, ge=1, le=MAX_TABLE_PAGE_SIZE),
    context: tuple[Organization, OrganizationMembership] = Depends(get_current_organization),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> TableRowsPage:
    organization, _ = context
    table = await load_stored_table(session, settings, organization.id, job_id, artifact_id)
    view = TableView(sort=sort, descending=descending, search=search)
    return await run_in_threadpool(
        table_rows_page, settings, organization.id, artifact_id, table, view,
        cursor=cursor, limit=limit, cache=STORED_TABLES,
    )


class TableExcelRequest(TableView):
    title: str = Field(default="Table", max_length=240)
    headers: list[str] | None = Field(default=None, max_length=256)


@router.post(
    "/{job_id}/artifacts/{artifact_id}/table/excel",
    response_class=Response,
    responses={
        200: {"content": {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {}}}
    },
)
async def export_table(
    job_id: uuid.UUID,
    artifact_id: uuid.UUID,
    request: TableExcelRequest,
    context: tuple[Organization, OrganizationMembership] = Depends(get_current_organization),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> Response:
    """Export every stored row in the viewer's current sort and search."""
    organization, _ = context
    table = await load_stored_table(session, settings, organization.id, job_id, artifact_id)
    if request.headers is not None and len(request.headers) != len(table.columns):
        raise AppError("TABLE_HEADERS_INVALID", "Provide one header per column.", 400)

    def build() -> bytes:
        return build_excel(ExcelTableExport(
            title=request.title,
            headers=request.headers or table.columns,
            rows=STORED_TABLES.view_rows(artifact_id, table, request),
            truncated=table.truncated,
        ))

    content = await run_in_threadpool(build)
    return Response(
        content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{export_filename(request.title)}"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
