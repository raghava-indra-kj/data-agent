from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_organization, get_current_user
from app.auth.models import User
from app.core.config import Settings, get_settings
from app.core.database import get_db_session
from app.organizations.models import Organization, OrganizationMembership
from app.reporting.schemas import (
    DashboardCreate,
    DashboardDetailResponse,
    DashboardRefreshResponse,
    DashboardResponse,
    DashboardUpdate,
    DashboardWidgetCreate,
    DashboardWidgetResponse,
    DashboardWidgetUpdate,
)
from app.reporting.service import ReportingService

router = APIRouter(prefix="/dashboards", tags=["dashboards"])


@router.get("", response_model=list[DashboardResponse])
async def list_dashboards(
    context: tuple[Organization, OrganizationMembership] = Depends(get_current_organization),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> list[DashboardResponse]:
    organization, _ = context
    return await ReportingService(session, settings).list_dashboards(organization.id)


@router.post("", response_model=DashboardResponse, status_code=201)
async def create_dashboard(
    payload: DashboardCreate,
    current_user: User = Depends(get_current_user),
    context: tuple[Organization, OrganizationMembership] = Depends(get_current_organization),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> DashboardResponse:
    organization, _ = context
    item = await ReportingService(session, settings).create_dashboard(
        organization_id=organization.id, user_id=current_user.id, payload=payload
    )
    return DashboardResponse.model_validate(item)


@router.get("/{dashboard_id}", response_model=DashboardDetailResponse)
async def get_dashboard(
    dashboard_id: uuid.UUID,
    context: tuple[Organization, OrganizationMembership] = Depends(get_current_organization),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> DashboardDetailResponse:
    organization, _ = context
    service = ReportingService(session, settings)
    item = await service.require_dashboard(dashboard_id, organization.id)
    response = DashboardDetailResponse.model_validate(item)
    widgets = await service.repo.list_widgets(item.id)
    response.widget_count = len(widgets)
    response.widgets = [await service.widget_response(widget) for widget in widgets]
    return response


@router.patch("/{dashboard_id}", response_model=DashboardResponse)
async def update_dashboard(
    dashboard_id: uuid.UUID,
    payload: DashboardUpdate,
    current_user: User = Depends(get_current_user),
    context: tuple[Organization, OrganizationMembership] = Depends(get_current_organization),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> DashboardResponse:
    organization, _ = context
    item = await ReportingService(session, settings).update_dashboard(
        dashboard_id=dashboard_id, organization_id=organization.id, user_id=current_user.id, payload=payload
    )
    return DashboardResponse.model_validate(item)


@router.delete("/{dashboard_id}", status_code=204)
async def delete_dashboard(
    dashboard_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    context: tuple[Organization, OrganizationMembership] = Depends(get_current_organization),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> Response:
    organization, _ = context
    await ReportingService(session, settings).delete_dashboard(
        dashboard_id=dashboard_id, organization_id=organization.id, user_id=current_user.id
    )
    return Response(status_code=204)


@router.post("/{dashboard_id}/refresh", response_model=DashboardRefreshResponse, status_code=202)
async def refresh_dashboard(
    dashboard_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    context: tuple[Organization, OrganizationMembership] = Depends(get_current_organization),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> DashboardRefreshResponse:
    organization, _ = context
    job_id = await ReportingService(session, settings).enqueue_dashboard_refresh(
        dashboard_id=dashboard_id,
        organization_id=organization.id,
        requested_by=current_user.id,
    )
    return DashboardRefreshResponse(job_id=job_id)


@router.post("/{dashboard_id}/widgets", response_model=DashboardWidgetResponse, status_code=201)
async def add_widget(
    dashboard_id: uuid.UUID,
    payload: DashboardWidgetCreate,
    current_user: User = Depends(get_current_user),
    context: tuple[Organization, OrganizationMembership] = Depends(get_current_organization),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> DashboardWidgetResponse:
    organization, _ = context
    service = ReportingService(session, settings)
    item = await service.add_widget(
        dashboard_id=dashboard_id, organization_id=organization.id, user_id=current_user.id, payload=payload
    )
    return await service.widget_response(item)


@router.patch("/widgets/{widget_id}", response_model=DashboardWidgetResponse)
async def update_widget(
    widget_id: uuid.UUID,
    payload: DashboardWidgetUpdate,
    current_user: User = Depends(get_current_user),
    context: tuple[Organization, OrganizationMembership] = Depends(get_current_organization),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> DashboardWidgetResponse:
    organization, _ = context
    service = ReportingService(session, settings)
    item = await service.update_widget(
        widget_id=widget_id, organization_id=organization.id, user_id=current_user.id, payload=payload
    )
    return await service.widget_response(item)


@router.delete("/widgets/{widget_id}", status_code=204)
async def delete_widget(
    widget_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    context: tuple[Organization, OrganizationMembership] = Depends(get_current_organization),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> Response:
    organization, _ = context
    await ReportingService(session, settings).delete_widget(
        widget_id=widget_id, organization_id=organization.id, user_id=current_user.id
    )
    return Response(status_code=204)


@router.post("/widgets/{widget_id}/refresh", response_model=DashboardRefreshResponse, status_code=202)
async def refresh_widget(
    widget_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    context: tuple[Organization, OrganizationMembership] = Depends(get_current_organization),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> DashboardRefreshResponse:
    organization, _ = context
    job_id = await ReportingService(session, settings).enqueue_refresh(
        widget_id=widget_id, organization_id=organization.id, requested_by=current_user.id
    )
    return DashboardRefreshResponse(job_id=job_id)
