from __future__ import annotations

import asyncio
import logging
import uuid

from app.core.config import get_settings
from app.core.database import get_session_factory
from app.core.time import utc_now
from app.data_sources.errors import DataSourceOperationError
from app.data_sources.service import DataSourceService
from app.jobs.handlers import JobHandlerRegistry
from app.jobs.repository import JobRepository
from app.jobs.service import JobService
from app.jobs.worker import JobFailureError
from app.knowledge.builder import build_snapshot
from app.knowledge.models import KnowledgeDocument, KnowledgeVersion
from app.knowledge.repository import KnowledgeRepository

logger = logging.getLogger(__name__)


async def _event(job_id: uuid.UUID, event_type: str, payload: dict[str, object] | None = None) -> None:
    settings = get_settings()
    async with get_session_factory()() as session:
        await JobService(session, settings).append_event(job_id, event_type, payload or {})


async def _cancel_requested(job_id: uuid.UUID) -> bool:
    settings = get_settings()
    async with get_session_factory()() as session:
        return await JobService(session, settings).is_cancel_requested(job_id)


async def _mark_cancelled(base_id: uuid.UUID) -> None:
    async with get_session_factory()() as session:
        repo = KnowledgeRepository(session)
        base = await repo.lock_base(base_id)
        if base is not None:
            base.status = "ready" if base.current_version_id is not None else "empty"
            base.last_error_code = None
            await session.commit()


async def _mark_failed(base_id: uuid.UUID, code: str) -> None:
    async with get_session_factory()() as session:
        repo = KnowledgeRepository(session)
        base = await repo.lock_base(base_id)
        if base is not None:
            base.status = "error"
            base.last_error_code = code[:100]
            await session.commit()


async def knowledge_generation_handler(job_id: uuid.UUID) -> dict[str, object]:
    settings = get_settings()
    session_factory = get_session_factory()

    async with session_factory() as session:
        job = await JobRepository(session).get(job_id)
        if job is None:
            raise JobFailureError("JOB_NOT_FOUND", "The knowledge-generation job is unavailable.")
        try:
            data_source_id = uuid.UUID(str(job.input["data_source_id"]))
            base_id = uuid.UUID(str(job.input["knowledge_base_id"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise JobFailureError("JOB_INPUT_INVALID", "The knowledge-generation job input is invalid.") from exc
        repo = KnowledgeRepository(session)
        base = await repo.get_base_for_org(base_id, job.organization_id)
        if base is None or base.data_source_id != data_source_id:
            raise JobFailureError("KNOWLEDGE_NOT_FOUND", "The knowledge base is unavailable.")
        source_service = DataSourceService(session, settings)
        source = await source_service.require_for_org(data_source_id, job.organization_id)
        adapter = await source_service.resolve_adapter(source)
        organization_id = job.organization_id

    await _event(job_id, "knowledge.generation.started", {"data_source_id": str(data_source_id)})
    try:
        async with asyncio.timeout(settings.datasource_operation_timeout_seconds):
            metadata = await adapter.introspect()
        await _event(
            job_id,
            "knowledge.schema.inspected",
            {"data_source_id": str(data_source_id), "object_count": len(metadata.tables)},
        )
        if await _cancel_requested(job_id):
            await _mark_cancelled(base_id)
            await _event(job_id, "knowledge.generation.cancelled", {"data_source_id": str(data_source_id)})
            # Worker sees cancel_requested and persists the terminal cancelled state.
            return {"data_source_id": str(data_source_id), "cancelled": True}
        snapshot = build_snapshot(metadata)
        await _event(
            job_id,
            "knowledge.index.generated",
            {
                "data_source_id": str(data_source_id),
                "object_count": len(snapshot.tables),
                "estimated_tokens": snapshot.index.estimated_tokens,
            },
        )

        async with session_factory() as session:
            repo = KnowledgeRepository(session)
            base = await repo.lock_base(base_id)
            if base is None or base.organization_id != organization_id:
                raise JobFailureError("KNOWLEDGE_NOT_FOUND", "The knowledge base is unavailable.")
            number = await repo.next_version_number(base.id)
            version = KnowledgeVersion(
                knowledge_base_id=base.id,
                version_number=number,
                schema_fingerprint=snapshot.schema_fingerprint,
                generated_by_job_id=job_id,
                created_at=utc_now(),
            )
            repo.add_version(version)
            await session.flush()
            docs = (snapshot.index, *snapshot.tables)
            for doc in docs:
                repo.add_document(
                    KnowledgeDocument(
                        knowledge_version_id=version.id,
                        document_type=doc.document_type,
                        document_key=doc.document_key,
                        title=doc.title,
                        content_markdown=doc.content_markdown,
                        metadata_json=doc.metadata,
                        estimated_tokens=doc.estimated_tokens,
                        created_at=utc_now(),
                    )
                )
            # Atomic promotion: previous version is never mutated/deleted.
            base.current_version_id = version.id
            base.status = "ready"
            base.last_error_code = None
            await session.commit()

        await _event(
            job_id,
            "knowledge.documents.generated",
            {"data_source_id": str(data_source_id), "document_count": 1 + len(snapshot.tables)},
        )
        await _event(
            job_id,
            "knowledge.generation.completed",
            {
                "data_source_id": str(data_source_id),
                "version_number": number,
                "schema_fingerprint": snapshot.schema_fingerprint,
            },
        )
        return {
            "data_source_id": str(data_source_id),
            "knowledge_base_id": str(base_id),
            "version_id": str(version.id),
            "version_number": number,
            "schema_fingerprint": snapshot.schema_fingerprint,
            "object_count": len(snapshot.tables),
        }
    except TimeoutError as exc:
        await _mark_failed(base_id, "KNOWLEDGE_INTROSPECTION_TIMEOUT")
        await _event(job_id, "knowledge.generation.failed", {"code": "KNOWLEDGE_INTROSPECTION_TIMEOUT"})
        raise JobFailureError(
            "KNOWLEDGE_INTROSPECTION_TIMEOUT", "Datasource inspection timed out.", retryable=True
        ) from exc
    except DataSourceOperationError as exc:
        await _mark_failed(base_id, exc.code)
        await _event(job_id, "knowledge.generation.failed", {"code": exc.code})
        raise JobFailureError(exc.code, exc.public_message, retryable=exc.retryable) from exc
    except JobFailureError:
        raise
    except Exception as exc:
        logger.exception("knowledge_generation_unexpected_failure", extra={"job_id": str(job_id)})
        await _mark_failed(base_id, "KNOWLEDGE_GENERATION_FAILED")
        await _event(job_id, "knowledge.generation.failed", {"code": "KNOWLEDGE_GENERATION_FAILED"})
        raise JobFailureError(
            "KNOWLEDGE_GENERATION_FAILED", "Knowledge generation failed unexpectedly."
        ) from exc


def register_knowledge_handlers(handler_registry: JobHandlerRegistry) -> None:
    if handler_registry.get("knowledge_generation") is None:
        handler_registry.register("knowledge_generation", knowledge_generation_handler)
