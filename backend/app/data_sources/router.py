from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import AuditService
from app.auth.dependencies import get_current_organization, get_current_user
from app.auth.models import User
from app.core.config import Settings, get_settings
from app.core.database import get_db_session
from app.core.errors import AppError
from app.data_sources.errors import DataSourceOperationError
from app.data_sources.schemas import (
    ColumnMetadataResponse,
    DataSourceResponse,
    DataSourceUpdate,
    ExcelUploadResponse,
    ForeignKeyMetadataResponse,
    JobAcceptedResponse,
    RelationalDataSourceCreate,
    SchemaMetadataResponse,
    TableMetadataResponse,
)
from app.data_sources.service import DataSourceService
from app.data_sources.table_catalog import TableCatalogResponse, table_catalog
from app.organizations.models import Organization, OrganizationMembership

router = APIRouter(prefix="/data-sources", tags=["data-sources"])


@router.get("/{data_source_id}/tables", response_model=TableCatalogResponse)
async def list_source_tables(
    data_source_id: uuid.UUID,
    search: str = Query(default="", max_length=600),
    cursor: str | None = Query(default=None, max_length=600),
    limit: int = Query(default=100, ge=1, le=200),
    knowledge_version_id: uuid.UUID | None = None,
    context: tuple[Organization, OrganizationMembership] = Depends(get_current_organization),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> TableCatalogResponse:
    organization, _ = context
    source = await DataSourceService(session, settings).require_for_org(data_source_id, organization.id)
    if source.status != "active":
        raise AppError("DATASOURCE_NOT_ACTIVE", "The datasource is not active.", 409)
    return await table_catalog(session, organization.id, data_source_id, search=search,
        cursor=cursor, limit=limit, version_id=knowledge_version_id)


def require_admin(membership: OrganizationMembership) -> None:
    if membership.role not in {"owner", "admin"}:
        raise AppError("FORBIDDEN", "You do not have permission for this action.", 403)


@router.get("", response_model=list[DataSourceResponse])
async def list_data_sources(
    context: tuple[Organization, OrganizationMembership] = Depends(get_current_organization),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> list[DataSourceResponse]:
    organization, _ = context
    service = DataSourceService(session, settings)
    items = await service.list_for_org(organization.id)
    return [await service.to_response(item) for item in items]


@router.post("", response_model=DataSourceResponse, status_code=201)
async def create_relational_data_source(
    payload: RelationalDataSourceCreate,
    current_user: User = Depends(get_current_user),
    context: tuple[Organization, OrganizationMembership] = Depends(get_current_organization),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> DataSourceResponse:
    organization, membership = context
    require_admin(membership)
    service = DataSourceService(session, settings)
    item = await service.create_relational(
        organization_id=organization.id,
        user_id=current_user.id,
        payload=payload,
    )
    AuditService(session).record(
        organization_id=organization.id, user_id=current_user.id, action="datasource.created",
        resource_type="data_source", resource_id=item.id, metadata={"kind": item.display_type},
    )
    await session.commit()
    return await service.to_response(item)


@router.post("/excel", response_model=ExcelUploadResponse, status_code=202)
async def create_excel_data_source(
    name: str = Form(min_length=1, max_length=180),
    file: UploadFile = File(),
    current_user: User = Depends(get_current_user),
    context: tuple[Organization, OrganizationMembership] = Depends(get_current_organization),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> ExcelUploadResponse:
    organization, membership = context
    require_admin(membership)
    service = DataSourceService(session, settings)
    item, job_id = await service.create_excel(
        organization_id=organization.id,
        user_id=current_user.id,
        name=name,
        upload=file,
    )
    AuditService(session).record(
        organization_id=organization.id, user_id=current_user.id, action="datasource.created",
        resource_type="data_source", resource_id=item.id, metadata={"kind": "excel", "job_id": str(job_id)},
    )
    await session.commit()
    return ExcelUploadResponse(data_source=await service.to_response(item), job_id=job_id)


@router.get("/{data_source_id}", response_model=DataSourceResponse)
async def get_data_source(
    data_source_id: uuid.UUID,
    context: tuple[Organization, OrganizationMembership] = Depends(get_current_organization),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> DataSourceResponse:
    organization, _ = context
    service = DataSourceService(session, settings)
    item = await service.require_for_org(data_source_id, organization.id)
    return await service.to_response(item)


@router.patch("/{data_source_id}", response_model=DataSourceResponse)
async def update_data_source(
    data_source_id: uuid.UUID,
    payload: DataSourceUpdate,
    current_user: User = Depends(get_current_user),
    context: tuple[Organization, OrganizationMembership] = Depends(get_current_organization),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> DataSourceResponse:
    organization, membership = context
    require_admin(membership)
    service = DataSourceService(session, settings)
    item = await service.update(
        data_source_id=data_source_id,
        organization_id=organization.id,
        payload=payload,
    )
    AuditService(session).record(
        organization_id=organization.id, user_id=current_user.id, action="datasource.updated",
        resource_type="data_source", resource_id=item.id,
    )
    await session.commit()
    return await service.to_response(item)


@router.delete("/{data_source_id}", status_code=204)
async def delete_data_source(
    data_source_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    context: tuple[Organization, OrganizationMembership] = Depends(get_current_organization),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> Response:
    organization, membership = context
    require_admin(membership)
    await DataSourceService(session, settings).delete(
        data_source_id=data_source_id,
        organization_id=organization.id,
    )
    AuditService(session).record(
        organization_id=organization.id, user_id=current_user.id, action="datasource.deleted",
        resource_type="data_source", resource_id=data_source_id,
    )
    await session.commit()
    return Response(status_code=204)


@router.post("/{data_source_id}/test", response_model=JobAcceptedResponse, status_code=202)
async def test_data_source(
    data_source_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    context: tuple[Organization, OrganizationMembership] = Depends(get_current_organization),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> JobAcceptedResponse:
    organization, membership = context
    require_admin(membership)
    job_id = await DataSourceService(session, settings).enqueue_test(
        data_source_id=data_source_id,
        organization_id=organization.id,
        requested_by=current_user.id,
    )
    return JobAcceptedResponse(job_id=job_id)


@router.get("/{data_source_id}/schema", response_model=SchemaMetadataResponse)
async def inspect_data_source(
    data_source_id: uuid.UUID,
    context: tuple[Organization, OrganizationMembership] = Depends(get_current_organization),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> SchemaMetadataResponse:
    organization, _ = context
    service = DataSourceService(session, settings)
    item = await service.require_for_org(data_source_id, organization.id)
    try:
        schema = await service.introspect_now(item)
    except DataSourceOperationError as exc:
        raise AppError(exc.code, exc.public_message, 502) from exc
    return SchemaMetadataResponse(
        tables=[
            TableMetadataResponse(
                schema=table.schema,
                name=table.name,
                object_type=table.object_type,
                columns=[
                    ColumnMetadataResponse(
                        name=column.name,
                        native_type=column.native_type,
                        nullable=column.nullable,
                        default=column.default,
                    )
                    for column in table.columns
                ],
                primary_key=list(table.primary_key),
                foreign_keys=[
                    ForeignKeyMetadataResponse(
                        constrained_columns=list(fk.constrained_columns),
                        referred_schema=fk.referred_schema,
                        referred_table=fk.referred_table,
                        referred_columns=list(fk.referred_columns),
                    )
                    for fk in table.foreign_keys
                ],
            )
            for table in schema.tables
        ]
    )


@router.post(
    "/{data_source_id}/excel/replace",
    response_model=JobAcceptedResponse,
    status_code=202,
)
async def replace_excel_data_source(
    data_source_id: uuid.UUID,
    file: UploadFile = File(),
    current_user: User = Depends(get_current_user),
    context: tuple[Organization, OrganizationMembership] = Depends(get_current_organization),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> JobAcceptedResponse:
    organization, membership = context
    require_admin(membership)
    job_id = await DataSourceService(session, settings).replace_excel(
        organization_id=organization.id,
        user_id=current_user.id,
        data_source_id=data_source_id,
        upload=file,
    )
    AuditService(session).record(
        organization_id=organization.id, user_id=current_user.id, action="datasource.file_replaced",
        resource_type="data_source", resource_id=data_source_id, metadata={"job_id": str(job_id)},
    )
    await session.commit()
    return JobAcceptedResponse(job_id=job_id)
