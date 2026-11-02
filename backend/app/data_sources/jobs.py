from __future__ import annotations

import asyncio
import logging
import os
import uuid

from app.core.config import get_settings
from app.core.database import get_session_factory
from app.core.time import utc_now
from app.data_sources.errors import DataSourceOperationError
from app.data_sources.diagnostics import connection_error
from app.data_sources.excel import ExcelMaterializer, unique_identifiers
from app.data_sources.repository import DataSourceRepository
from app.data_sources.service import DataSourceService
from app.data_sources.storage import LocalDataSourceStorage
from app.jobs.handlers import JobHandlerRegistry
from app.jobs.repository import JobRepository
from app.jobs.service import JobService
from app.jobs.worker import JobFailureError

logger = logging.getLogger(__name__)


async def _append_event(job_id: uuid.UUID, event_type: str, payload: dict[str, object]) -> None:
    settings = get_settings()
    session_factory = get_session_factory()
    async with session_factory() as session:
        await JobService(session, settings).append_event(job_id, event_type, payload)


async def _cancel_requested(job_id: uuid.UUID) -> bool:
    settings = get_settings()
    session_factory = get_session_factory()
    async with session_factory() as session:
        return await JobService(session, settings).is_cancel_requested(job_id)


async def datasource_test_handler(job_id: uuid.UUID) -> dict[str, object]:
    settings = get_settings()
    session_factory = get_session_factory()

    async with session_factory() as session:
        job = await JobRepository(session).get(job_id)
        if job is None:
            raise JobFailureError("JOB_NOT_FOUND", "The datasource test job is unavailable.")
        try:
            data_source_id = uuid.UUID(str(job.input["data_source_id"]))
        except (KeyError, ValueError, TypeError) as exc:
            raise JobFailureError(
                "JOB_INPUT_INVALID", "The datasource test job input is invalid."
            ) from exc
        service = DataSourceService(session, settings)
        data_source = await service.require_for_org(data_source_id, job.organization_id)
        if data_source.status == "disabled":
            raise JobFailureError("DATASOURCE_DISABLED", "The datasource is disabled.")
        try:
            adapter = await service.resolve_adapter(data_source)
        except DataSourceOperationError as error:
            await _mark_test_failure(job_id, data_source_id, error)
            raise JobFailureError(error.code, error.public_message) from error

    await _append_event(job_id, "datasource.test.started", {"data_source_id": str(data_source_id)})
    try:
        async with asyncio.timeout(settings.datasource_operation_timeout_seconds):
            result = await adapter.test_connection()
        if not result.ok:
            raise DataSourceOperationError(
                "DATASOURCE_CONNECTION_FAILED", "Unable to connect to the datasource."
            )
    except TimeoutError as exc:
        error = connection_error(exc, stage="connection test")
        await _mark_test_failure(job_id, data_source_id, error)
        raise JobFailureError(error.code, error.public_message, retryable=True) from exc
    except DataSourceOperationError as error:
        await _mark_test_failure(job_id, data_source_id, error)
        raise JobFailureError(
            error.code, error.public_message, retryable=error.retryable
        ) from error

    async with session_factory() as session:
        service = DataSourceService(session, settings)
        current = await service.require_for_org(data_source_id, data_source.organization_id)
        await service.mark_test_succeeded(current)
    await _append_event(
        job_id, "datasource.test.succeeded", {"data_source_id": str(data_source_id)}
    )
    return {"data_source_id": str(data_source_id), "connected": True}


async def _mark_test_failure(
    job_id: uuid.UUID, data_source_id: uuid.UUID, error: DataSourceOperationError
) -> None:
    settings = get_settings()
    session_factory = get_session_factory()
    async with session_factory() as session:
        job = await JobRepository(session).get(job_id)
        if job is not None:
            service = DataSourceService(session, settings)
            data_source = await service.require_for_org(data_source_id, job.organization_id)
            diagnostics = {**(error.diagnostics or {
                "category": "unknown", "stage": "connection test", "message": error.public_message,
                "driver_message": "No further driver details were provided.", "next_steps": ["Review the error code and server logs."],
            }), "job_id": str(job_id)}
            await service.mark_test_failed(data_source, error.code, diagnostics)
    await _append_event(
        job_id,
        "datasource.test.failed",
        {"data_source_id": str(data_source_id), "code": error.code, "diagnostics": error.diagnostics or {}},
    )


async def excel_materialization_handler(job_id: uuid.UUID) -> dict[str, object]:
    settings = get_settings()
    storage = LocalDataSourceStorage(settings)
    materializer = ExcelMaterializer(settings)
    session_factory = get_session_factory()

    async with session_factory() as session:
        job = await JobRepository(session).get(job_id)
        if job is None:
            raise JobFailureError("JOB_NOT_FOUND", "The Excel materialization job is unavailable.")
        try:
            data_source_id = uuid.UUID(str(job.input["data_source_id"]))
            file_id = uuid.UUID(str(job.input["file_id"]))
        except (KeyError, ValueError, TypeError) as exc:
            raise JobFailureError(
                "JOB_INPUT_INVALID", "The Excel materialization job input is invalid."
            ) from exc
        repo = DataSourceRepository(session)
        pair = await repo.get_file_for_org(file_id, job.organization_id)
        if pair is None or pair[1].id != data_source_id:
            raise JobFailureError(
                "DATASOURCE_FILE_NOT_FOUND", "The uploaded workbook is unavailable."
            )
        file, data_source = pair
        previous_active = await repo.active_file(data_source.id)
        file.status = "materializing"
        file.error_code = None
        file.updated_at = utc_now()
        if previous_active is None:
            data_source.status = "preparing"
        await session.commit()
        organization_id = job.organization_id
        source_path = storage.from_record_path(file.source_path)
        temp_db, final_db = storage.database_paths(organization_id, data_source_id, file_id)

    await _append_event(
        job_id,
        "excel.materialization.started",
        {"data_source_id": str(data_source_id), "file_id": str(file_id)},
    )
    try:
        sheet_names = await materializer.list_sheets(source_path)
        if not sheet_names:
            raise DataSourceOperationError(
                "EXCEL_NO_USABLE_SHEETS", "The workbook contains no worksheets."
            )
        table_names = unique_identifiers(list(sheet_names), prefix="sheet")
        await materializer.initialize_database(temp_db)
        mappings: list[dict[str, object]] = []
        for sheet_name, table_name in zip(sheet_names, table_names, strict=True):
            if await _cancel_requested(job_id):
                storage.remove_file(temp_db)
                await _mark_materialization_cancelled(
                    job_id, organization_id, data_source_id, file_id
                )
                return {"data_source_id": str(data_source_id), "cancelled": True}
            await _append_event(
                job_id,
                "excel.sheet.started",
                {"sheet_name": sheet_name, "table_name": table_name},
            )
            result = await materializer.materialize_sheet(
                source_path=source_path,
                database_path=temp_db,
                sheet_name=sheet_name,
                table_name=table_name,
            )
            mappings.append(result.as_dict())
            await _append_event(
                job_id,
                "excel.sheet.completed",
                result.as_dict(),
            )
        await materializer.validate_database(temp_db)
        final_db.parent.mkdir(parents=True, exist_ok=True)
        os.replace(temp_db, final_db)

        old_paths: tuple[str | None, str | None] | None = None
        async with session_factory() as session:
            repo = DataSourceRepository(session)
            pair = await repo.get_file_for_org(file_id, organization_id)
            if pair is None:
                raise JobFailureError(
                    "DATASOURCE_FILE_NOT_FOUND", "The uploaded workbook is unavailable."
                )
            current_file, current_source = pair
            previous = await repo.active_file(current_source.id)
            if previous is not None and previous.id != current_file.id:
                old_paths = (previous.source_path, previous.materialized_database_path)
            current_file.materialized_database_path = storage.to_record_path(final_db)
            current_file.sheet_mapping = mappings
            current_file.updated_at = utc_now()
            await repo.activate_file(current_source.id, current_file.id)
            if previous is not None and previous.id != current_file.id:
                await session.delete(previous)
            current_source.status = "active"
            current_source.last_error_code = None
            current_source.last_tested_at = utc_now()
            await session.commit()

        if old_paths is not None:
            storage.remove_file(old_paths[0])
            storage.remove_file(old_paths[1])
        await _append_event(
            job_id,
            "excel.database.created",
            {
                "data_source_id": str(data_source_id),
                "file_id": str(file_id),
                "table_count": sum(1 for item in mappings if not bool(item["skipped"])),
            },
        )
        await _append_event(
            job_id, "datasource.ready", {"data_source_id": str(data_source_id)}
        )
        return {
            "data_source_id": str(data_source_id),
            "file_id": str(file_id),
            "sheets": mappings,
        }
    except JobFailureError:
        storage.remove_file(temp_db)
        raise
    except DataSourceOperationError as error:
        storage.remove_file(temp_db)
        storage.remove_file(final_db)
        await _mark_materialization_failure(
            job_id, organization_id, data_source_id, file_id, error.code
        )
        raise JobFailureError(
            error.code, error.public_message, retryable=error.retryable
        ) from error
    except Exception as exc:
        logger.exception("excel_materialization_unexpected_failure", extra={"job_id": str(job_id)})
        storage.remove_file(temp_db)
        storage.remove_file(final_db)
        await _mark_materialization_failure(
            job_id,
            organization_id,
            data_source_id,
            file_id,
            "EXCEL_MATERIALIZATION_FAILED",
        )
        raise JobFailureError(
            "EXCEL_MATERIALIZATION_FAILED",
            "The workbook could not be converted into an analytical database.",
        ) from exc


async def _mark_materialization_failure(
    job_id: uuid.UUID,
    organization_id: uuid.UUID,
    data_source_id: uuid.UUID,
    file_id: uuid.UUID,
    code: str,
) -> None:
    session_factory = get_session_factory()
    async with session_factory() as session:
        repo = DataSourceRepository(session)
        data_source = await repo.get_for_org(data_source_id, organization_id)
        file = await repo.get_file(file_id)
        if data_source is not None and file is not None:
            file.status = "error"
            file.error_code = code[:100]
            file.updated_at = utc_now()
            data_source.last_error_code = code[:100]
            data_source.status = "active" if await repo.active_file(data_source_id) else "error"
            await session.commit()
    await _append_event(
        job_id,
        "excel.materialization.failed",
        {"data_source_id": str(data_source_id), "file_id": str(file_id), "code": code},
    )


async def _mark_materialization_cancelled(
    job_id: uuid.UUID,
    organization_id: uuid.UUID,
    data_source_id: uuid.UUID,
    file_id: uuid.UUID,
) -> None:
    session_factory = get_session_factory()
    async with session_factory() as session:
        repo = DataSourceRepository(session)
        data_source = await repo.get_for_org(data_source_id, organization_id)
        file = await repo.get_file(file_id)
        if data_source is not None and file is not None:
            file.status = "error"
            file.error_code = "JOB_CANCELLED"
            file.updated_at = utc_now()
            data_source.status = "active" if await repo.active_file(data_source_id) else "error"
            await session.commit()
    await _append_event(
        job_id,
        "excel.materialization.cancelled",
        {"data_source_id": str(data_source_id), "file_id": str(file_id)},
    )


def register_data_source_handlers(handler_registry: JobHandlerRegistry) -> None:
    if handler_registry.get("datasource_test") is None:
        handler_registry.register("datasource_test", datasource_test_handler)
    if handler_registry.get("excel_materialization") is None:
        handler_registry.register("excel_materialization", excel_materialization_handler)
