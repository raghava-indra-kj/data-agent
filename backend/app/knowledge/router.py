from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_organization, get_current_user
from app.auth.models import User
from app.audit.service import AuditService
from app.core.config import Settings, get_settings
from app.core.database import get_db_session
from app.core.errors import AppError
from app.knowledge.compact import compact_schema
from app.knowledge.schemas import (
    CompactSchemaResponse,
    KnowledgeAnnotationCreate,
    KnowledgeAnnotationResponse,
    KnowledgeAnnotationUpdate,
    KnowledgeDocumentResponse,
    KnowledgeDocumentSummary,
    KnowledgeImportResponse,
    KnowledgeJobResponse,
    KnowledgeStatusResponse,
    KnowledgeVersionResponse,
)
from app.knowledge.markdown_io import MAX_IMPORT_FILE_BYTES, MAX_IMPORT_FILES, export_zip
from app.knowledge.service import KnowledgeService
from app.organizations.models import Organization, OrganizationMembership

# Upper bound on the objects included in one compact schema response.
MAX_COMPACT_TABLES = 10000

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


def require_admin(membership: OrganizationMembership) -> None:
    if membership.role not in {"owner", "admin"}:
        raise AppError("FORBIDDEN", "You do not have permission for this action.", 403)


@router.get("/data-sources/{data_source_id}", response_model=KnowledgeStatusResponse)
async def get_knowledge_status(
    data_source_id: uuid.UUID,
    context: tuple[Organization, OrganizationMembership] = Depends(get_current_organization),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> KnowledgeStatusResponse:
    organization, _ = context
    service = KnowledgeService(session, settings)
    await service.require_source(data_source_id, organization.id)
    base = await service.repo.get_base_for_source(data_source_id, organization.id)
    if base is None:
        return KnowledgeStatusResponse(
            data_source_id=data_source_id,
            knowledge_base_id=None,
            status="empty",
            current_version_id=None,
            current_version_number=None,
            schema_fingerprint=None,
            generated_at=None,
            object_count=None,
            last_error_code=None,
        )
    version = await service.current_version(base)
    object_count: int | None = None
    if version is not None:
        index = await service.repo.get_document(version.id, "index", "index")
        if index is not None:
            raw_count = index.metadata_json.get("object_count")
            if isinstance(raw_count, int):
                object_count = raw_count
    return KnowledgeStatusResponse(
        data_source_id=data_source_id,
        knowledge_base_id=base.id,
        status=base.status,
        current_version_id=base.current_version_id,
        current_version_number=(version.version_number if version else None),
        schema_fingerprint=(version.schema_fingerprint if version else None),
        generated_at=(version.created_at if version else None),
        object_count=object_count,
        last_error_code=base.last_error_code,
    )


@router.post("/data-sources/{data_source_id}/generate", response_model=KnowledgeJobResponse, status_code=202)
async def generate_knowledge(
    data_source_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    context: tuple[Organization, OrganizationMembership] = Depends(get_current_organization),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> KnowledgeJobResponse:
    organization, membership = context
    require_admin(membership)
    base, job_id = await KnowledgeService(session, settings).enqueue_generation(
        data_source_id=data_source_id,
        organization_id=organization.id,
        requested_by=current_user.id,
    )
    AuditService(session).record(
        organization_id=organization.id, user_id=current_user.id, action="knowledge.regeneration_requested",
        resource_type="knowledge_base", resource_id=base.id, metadata={"data_source_id": str(data_source_id), "job_id": str(job_id)},
    )
    await session.commit()
    return KnowledgeJobResponse(job_id=job_id, knowledge_base_id=base.id)


@router.get("/data-sources/{data_source_id}/versions", response_model=list[KnowledgeVersionResponse])
async def list_versions(
    data_source_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=200),
    context: tuple[Organization, OrganizationMembership] = Depends(get_current_organization),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> list[KnowledgeVersionResponse]:
    organization, _ = context
    service = KnowledgeService(session, settings)
    base = await service.require_base(data_source_id, organization.id)
    return [KnowledgeVersionResponse.model_validate(item) for item in await service.repo.list_versions(base.id, limit)]


@router.get("/data-sources/{data_source_id}/index", response_model=KnowledgeDocumentResponse)
async def get_index(
    data_source_id: uuid.UUID,
    context: tuple[Organization, OrganizationMembership] = Depends(get_current_organization),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> KnowledgeDocumentResponse:
    organization, _ = context
    service = KnowledgeService(session, settings)
    base = await service.require_base(data_source_id, organization.id)
    version = await service.require_current_version(base)
    document = await service.repo.get_document(version.id, "index", "index")
    if document is None:
        raise AppError("KNOWLEDGE_DOCUMENT_NOT_FOUND", "Knowledge index not found.", 404)
    return KnowledgeDocumentResponse.model_validate(document)


@router.get("/data-sources/{data_source_id}/documents", response_model=list[KnowledgeDocumentSummary])
async def list_documents(
    data_source_id: uuid.UUID,
    document_type: Literal["index", "table_schema"] | None = None,
    limit: int = Query(default=500, ge=1, le=2000),
    context: tuple[Organization, OrganizationMembership] = Depends(get_current_organization),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> list[KnowledgeDocumentSummary]:
    organization, _ = context
    service = KnowledgeService(session, settings)
    base = await service.require_base(data_source_id, organization.id)
    version = await service.require_current_version(base)
    items = await service.repo.list_documents(version.id, document_type=document_type, limit=limit)
    return [KnowledgeDocumentSummary.model_validate(item) for item in items]


@router.get("/data-sources/{data_source_id}/documents/{document_id}", response_model=KnowledgeDocumentResponse)
async def get_document(
    data_source_id: uuid.UUID,
    document_id: uuid.UUID,
    context: tuple[Organization, OrganizationMembership] = Depends(get_current_organization),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> KnowledgeDocumentResponse:
    organization, _ = context
    service = KnowledgeService(session, settings)
    base = await service.require_base(data_source_id, organization.id)
    item = await service.repo.get_document_by_id_for_base(document_id, base.id)
    if item is None:
        raise AppError("KNOWLEDGE_DOCUMENT_NOT_FOUND", "Knowledge document not found.", 404)
    if item.knowledge_version_id != base.current_version_id:
        raise AppError("KNOWLEDGE_DOCUMENT_NOT_FOUND", "Knowledge document not found.", 404)
    return KnowledgeDocumentResponse.model_validate(item)


@router.get("/data-sources/{data_source_id}/schema-compact", response_model=CompactSchemaResponse)
async def get_compact_schema(
    data_source_id: uuid.UUID,
    context: tuple[Organization, OrganizationMembership] = Depends(get_current_organization),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> CompactSchemaResponse:
    organization, _ = context
    service = KnowledgeService(session, settings)
    source = await service.require_source(data_source_id, organization.id)
    base = await service.require_base(data_source_id, organization.id)
    version = await service.require_current_version(base)
    documents = await service.repo.list_documents(
        version.id, document_type="table_schema", limit=MAX_COMPACT_TABLES
    )
    text, count = compact_schema(source.name, documents)
    return CompactSchemaResponse(knowledge_version_id=version.id, table_count=count, text=text)


@router.get("/data-sources/{data_source_id}/table", response_model=KnowledgeDocumentResponse)
async def get_table_document(
    data_source_id: uuid.UUID,
    key: str = Query(min_length=1, max_length=600),
    context: tuple[Organization, OrganizationMembership] = Depends(get_current_organization),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> KnowledgeDocumentResponse:
    organization, _ = context
    service = KnowledgeService(session, settings)
    base = await service.require_base(data_source_id, organization.id)
    version = await service.require_current_version(base)
    item = await service.repo.get_document(version.id, "table_schema", key)
    if item is None:
        raise AppError("KNOWLEDGE_DOCUMENT_NOT_FOUND", "Table knowledge document not found.", 404)
    return KnowledgeDocumentResponse.model_validate(item)


@router.get("/data-sources/{data_source_id}/annotations", response_model=list[KnowledgeAnnotationResponse])
async def list_annotations(
    data_source_id: uuid.UUID,
    scope_type: Literal["datasource", "table", "column", "metric"] | None = None,
    scope_key: str | None = Query(default=None, max_length=600),
    context: tuple[Organization, OrganizationMembership] = Depends(get_current_organization),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> list[KnowledgeAnnotationResponse]:
    organization, _ = context
    service = KnowledgeService(session, settings)
    await service.require_source(data_source_id, organization.id)
    base = await service.repo.get_base_for_source(data_source_id, organization.id)
    if base is None:
        return []
    items = await service.repo.list_annotations(base.id, scope_type=scope_type, scope_key=scope_key)
    return [KnowledgeAnnotationResponse.model_validate(item) for item in items]


@router.get("/data-sources/{data_source_id}/annotations/export")
async def export_annotations(
    data_source_id: uuid.UUID,
    context: tuple[Organization, OrganizationMembership] = Depends(get_current_organization),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> Response:
    organization, _ = context
    service = KnowledgeService(session, settings)
    await service.require_source(data_source_id, organization.id)
    base = await service.repo.get_base_for_source(data_source_id, organization.id)
    items = await service.repo.list_annotations(base.id) if base else []
    return Response(
        content=export_zip(items),
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="business-knowledge.zip"'},
    )


@router.post("/data-sources/{data_source_id}/annotations/import", response_model=KnowledgeImportResponse)
async def import_annotations(
    data_source_id: uuid.UUID,
    files: list[UploadFile] = File(...),
    on_duplicate: Literal["skip", "replace"] = "skip",
    dry_run: bool = False,
    current_user: User = Depends(get_current_user),
    context: tuple[Organization, OrganizationMembership] = Depends(get_current_organization),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> KnowledgeImportResponse:
    organization, membership = context
    require_admin(membership)
    if len(files) > MAX_IMPORT_FILES:
        raise AppError(
            "KNOWLEDGE_IMPORT_TOO_MANY_FILES", f"Import at most {MAX_IMPORT_FILES} files at a time.", 422
        )
    uploads = [(file.filename or "unnamed.md", await file.read(MAX_IMPORT_FILE_BYTES + 1)) for file in files]
    return await KnowledgeService(session, settings).import_notes(
        data_source_id=data_source_id,
        organization_id=organization.id,
        user_id=current_user.id,
        files=uploads,
        replace_duplicates=on_duplicate == "replace",
        dry_run=dry_run,
    )


@router.post("/data-sources/{data_source_id}/annotations", response_model=KnowledgeAnnotationResponse, status_code=201)
async def create_annotation(
    data_source_id: uuid.UUID,
    payload: KnowledgeAnnotationCreate,
    current_user: User = Depends(get_current_user),
    context: tuple[Organization, OrganizationMembership] = Depends(get_current_organization),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> KnowledgeAnnotationResponse:
    organization, membership = context
    require_admin(membership)
    item = await KnowledgeService(session, settings).create_annotation(
        data_source_id=data_source_id,
        organization_id=organization.id,
        user_id=current_user.id,
        payload=payload,
    )
    return KnowledgeAnnotationResponse.model_validate(item)


@router.patch("/annotations/{annotation_id}", response_model=KnowledgeAnnotationResponse)
async def update_annotation(
    annotation_id: uuid.UUID,
    payload: KnowledgeAnnotationUpdate,
    context: tuple[Organization, OrganizationMembership] = Depends(get_current_organization),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> KnowledgeAnnotationResponse:
    organization, membership = context
    require_admin(membership)
    item = await KnowledgeService(session, settings).update_annotation(
        annotation_id=annotation_id, organization_id=organization.id, payload=payload
    )
    return KnowledgeAnnotationResponse.model_validate(item)


@router.delete("/annotations/{annotation_id}", status_code=204)
async def delete_annotation(
    annotation_id: uuid.UUID,
    context: tuple[Organization, OrganizationMembership] = Depends(get_current_organization),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> Response:
    organization, membership = context
    require_admin(membership)
    await KnowledgeService(session, settings).delete_annotation(
        annotation_id=annotation_id, organization_id=organization.id
    )
    return Response(status_code=204)
