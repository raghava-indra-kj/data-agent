from __future__ import annotations

import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError
from app.core.time import utc_now
from app.data_sources.models import DataSource
from app.data_sources.repository import DataSourceRepository
from app.jobs.service import JobService
from app.knowledge.models import KnowledgeAnnotation, KnowledgeBase, KnowledgeVersion
from app.knowledge.repository import KnowledgeRepository
from app.knowledge.markdown_io import NoteFileError, parse_note
from app.knowledge.schemas import (
    KnowledgeAnnotationCreate,
    KnowledgeAnnotationUpdate,
    KnowledgeImportItem,
    KnowledgeImportResponse,
)


class KnowledgeService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.repo = KnowledgeRepository(session)
        self.data_sources = DataSourceRepository(session)

    async def require_source(
        self, data_source_id: uuid.UUID, organization_id: uuid.UUID
    ) -> DataSource:
        source = await self.data_sources.get_for_org(data_source_id, organization_id)
        if source is None:
            raise AppError("DATASOURCE_NOT_FOUND", "Datasource not found.", 404)
        return source

    async def ensure_base(self, data_source_id: uuid.UUID, organization_id: uuid.UUID) -> KnowledgeBase:
        await self.require_source(data_source_id, organization_id)
        base = await self.repo.get_base_for_source(data_source_id, organization_id)
        if base is not None:
            return base
        base = KnowledgeBase(
            organization_id=organization_id,
            data_source_id=data_source_id,
            status="empty",
            current_version_id=None,
            last_error_code=None,
        )
        self.repo.add_base(base)
        try:
            await self.session.flush()
            return base
        except IntegrityError:
            # Concurrent first-use requests can race to create the one-per-datasource base.
            # The unique constraint is authoritative; recover by reading the winner.
            await self.session.rollback()
            existing = await self.repo.get_base_for_source(data_source_id, organization_id)
            if existing is None:
                raise
            return existing

    async def require_base(self, data_source_id: uuid.UUID, organization_id: uuid.UUID) -> KnowledgeBase:
        base = await self.repo.get_base_for_source(data_source_id, organization_id)
        if base is None:
            raise AppError("KNOWLEDGE_NOT_FOUND", "Knowledge has not been created for this datasource.", 404)
        return base

    async def enqueue_generation(
        self,
        *,
        data_source_id: uuid.UUID,
        organization_id: uuid.UUID,
        requested_by: uuid.UUID,
    ) -> tuple[KnowledgeBase, uuid.UUID]:
        source = await self.require_source(data_source_id, organization_id)
        if source.kind == "powerbi":
            raise AppError("POWER_BI_KNOWLEDGE_MANAGED", "Power BI metadata is retrieved privately from Fabric IQ when you ask a question.", 422)
        if source.status == "disabled":
            raise AppError("DATASOURCE_DISABLED", "The datasource is disabled.", 409)
        if source.kind == "duckdb" and source.status != "active":
            raise AppError("DATASOURCE_NOT_READY", "The uploaded datasource is not ready.", 409)
        base = await self.ensure_base(data_source_id, organization_id)
        if base.status == "generating":
            raise AppError("KNOWLEDGE_GENERATION_IN_PROGRESS", "Knowledge generation is already running.", 409)
        base.status = "generating"
        base.last_error_code = None
        await self.session.flush()
        job = await JobService(self.session, self.settings).create_job(
            organization_id=organization_id,
            requested_by=requested_by,
            job_type="knowledge_generation",
            input_data={
                "data_source_id": str(data_source_id),
                "knowledge_base_id": str(base.id),
            },
        )
        return base, job.id

    async def current_version(self, base: KnowledgeBase) -> KnowledgeVersion | None:
        if base.current_version_id is None:
            return None
        return await self.repo.get_version(base.current_version_id)

    async def require_current_version(self, base: KnowledgeBase) -> KnowledgeVersion:
        version = await self.current_version(base)
        if version is None:
            raise AppError("KNOWLEDGE_NOT_READY", "Knowledge has not been generated yet.", 409)
        return version

    async def create_annotation(
        self,
        *,
        data_source_id: uuid.UUID,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        payload: KnowledgeAnnotationCreate,
    ) -> KnowledgeAnnotation:
        base = await self.ensure_base(data_source_id, organization_id)
        item = KnowledgeAnnotation(
            knowledge_base_id=base.id,
            scope_type=payload.scope_type,
            scope_key=payload.scope_key,
            title=payload.title,
            content=payload.content.strip(),
            created_by=user_id,
        )
        self.repo.add_annotation(item)
        await self.session.commit()
        return item

    async def update_annotation(
        self,
        *,
        annotation_id: uuid.UUID,
        organization_id: uuid.UUID,
        payload: KnowledgeAnnotationUpdate,
    ) -> KnowledgeAnnotation:
        item = await self.repo.get_annotation_for_org(annotation_id, organization_id)
        if item is None:
            raise AppError("KNOWLEDGE_ANNOTATION_NOT_FOUND", "Knowledge annotation not found.", 404)
        item.content = payload.content.strip()
        if payload.title is not None:
            item.title = payload.title.strip() or None
        item.updated_at = utc_now()
        await self.session.commit()
        return item

    async def delete_annotation(self, *, annotation_id: uuid.UUID, organization_id: uuid.UUID) -> None:
        item = await self.repo.get_annotation_for_org(annotation_id, organization_id)
        if item is None:
            raise AppError("KNOWLEDGE_ANNOTATION_NOT_FOUND", "Knowledge annotation not found.", 404)
        await self.session.delete(item)
        await self.session.commit()

    async def import_notes(
        self,
        *,
        data_source_id: uuid.UUID,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        files: list[tuple[str, bytes]],
        replace_duplicates: bool,
        dry_run: bool,
    ) -> KnowledgeImportResponse:
        """Import Markdown notes. A duplicate has the same scope, key and title; each file is judged alone."""
        await self.require_source(data_source_id, organization_id)
        base = await self.repo.get_base_for_source(data_source_id, organization_id)
        existing = await self.repo.list_annotations(base.id) if base else []
        by_identity = {self._identity(item.scope_type, item.scope_key, item.title): item for item in existing}
        items: list[KnowledgeImportItem] = []
        new_notes: list[KnowledgeAnnotationCreate] = []
        seen: set[tuple[str, str, str]] = set()
        for filename, raw in files:
            try:
                payload = parse_note(filename, raw).payload
            except NoteFileError as error:
                items.append(KnowledgeImportItem(filename=filename, status="error", message=str(error)))
                continue
            identity = self._identity(payload.scope_type, payload.scope_key, payload.title)
            info = {
                "filename": filename,
                "title": payload.title,
                "scope_type": payload.scope_type,
                "scope_key": payload.scope_key,
            }
            if identity in seen:
                message = "Another file in this upload has the same scope, key and title."
                items.append(KnowledgeImportItem(**info, status="skipped", message=message))
                continue
            seen.add(identity)
            match = by_identity.get(identity)
            if match is None:
                new_notes.append(payload)
                items.append(KnowledgeImportItem(**info, status="created"))
            elif replace_duplicates:
                if not dry_run:
                    match.content = payload.content
                    match.updated_at = utc_now()
                items.append(KnowledgeImportItem(**info, status="updated"))
            else:
                items.append(KnowledgeImportItem(**info, status="skipped", message="Already exists."))
        if not dry_run:
            if new_notes:
                base = await self.ensure_base(data_source_id, organization_id)
                for payload in new_notes:
                    self.repo.add_annotation(
                        KnowledgeAnnotation(
                            knowledge_base_id=base.id,
                            scope_type=payload.scope_type,
                            scope_key=payload.scope_key,
                            title=payload.title,
                            content=payload.content,
                            created_by=user_id,
                        )
                    )
            await self.session.commit()

        def count(status: str) -> int:
            return sum(item.status == status for item in items)

        return KnowledgeImportResponse(
            dry_run=dry_run,
            created=count("created"),
            updated=count("updated"),
            skipped=count("skipped"),
            failed=count("error"),
            items=items,
        )

    @staticmethod
    def _identity(scope_type: str, scope_key: str | None, title: str | None) -> tuple[str, str, str]:
        return (scope_type, (scope_key or "").casefold(), (title or "").casefold())
