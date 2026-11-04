from __future__ import annotations

import uuid
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import AuditService
from app.auth.dependencies import get_current_organization, get_current_user
from app.auth.models import User
from app.core.config import Settings, get_settings
from app.core.database import get_db_session
from app.core.errors import AppError
from app.data_sources.schemas import DataSourceResponse
from app.data_sources.service import DataSourceService
from app.organizations.models import Organization, OrganizationMembership
from app.power_bi.auth import begin_connection, configured, finish_connection, require_enabled
from app.power_bi.models import MicrosoftConnection
from app.power_bi.schemas import (
    ConnectionResponse,
    ConnectionStart,
    EmbedConfiguration,
    PowerBICreate,
    PowerBIFeatures,
    ReportCandidate,
    ReportLookup,
    ReportResponse,
)
from app.power_bi.service import PowerBIService
from app.secrets.service import SecretService

router = APIRouter(tags=["power-bi"])
COOKIE = "power_bi_signin"


@router.get("/power-bi/features", response_model=PowerBIFeatures)
async def features(
    settings: Settings = Depends(get_settings), _user: User = Depends(get_current_user)
) -> PowerBIFeatures:
    return PowerBIFeatures(
        enabled=settings.power_bi_enabled,
        configured=configured(settings),
        embedding_enabled=settings.power_bi_enabled and settings.power_bi_embedding_enabled,
    )


@router.post("/power-bi/connections/start", response_model=ConnectionStart)
async def connect(
    response: Response,
    user: User = Depends(get_current_user),
    context: tuple[Organization, OrganizationMembership] = Depends(get_current_organization),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
):
    url, browser_key = await begin_connection(session, settings, context[0].id, user.id)
    response.set_cookie(
        COOKIE,
        browser_key,
        max_age=600,
        httponly=True,
        secure=settings.power_bi_redirect_uri.startswith("https:"),
        samesite="lax",
        path=urlparse(settings.power_bi_redirect_uri).path,
    )
    response.headers["Cache-Control"] = "no-store"
    return ConnectionStart(authorization_url=url)


@router.get("/power-bi/connections/callback", include_in_schema=False)
async def callback(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
):
    require_enabled(settings)
    status = "connected"
    try:
        await finish_connection(
            session, settings, dict(request.query_params), request.cookies.get(COOKIE, "")
        )
    except AppError as exc:
        await session.rollback()
        status = exc.code
    except Exception:
        await session.rollback()
        status = "POWER_BI_SIGNIN_FAILED"
    # Only a static configured origin/path and a server-owned code are returned, never tokens.
    response = RedirectResponse(
        settings.power_bi_frontend_url.rstrip("/") + "/power-bi/connected?power_bi=" + status,
        status_code=303,
    )
    response.delete_cookie(COOKIE, path=urlparse(settings.power_bi_redirect_uri).path)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@router.get("/power-bi/connections", response_model=list[ConnectionResponse])
async def connections(
    user: User = Depends(get_current_user),
    context: tuple[Organization, OrganizationMembership] = Depends(get_current_organization),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
):
    require_enabled(settings)
    return list(
        (
            await session.scalars(
                select(MicrosoftConnection).where(
                    MicrosoftConnection.organization_id == context[0].id,
                    MicrosoftConnection.user_id == user.id,
                )
            )
        ).all()
    )


@router.delete("/power-bi/connections/{connection_id}", status_code=204)
async def disconnect(
    connection_id: uuid.UUID,
    user: User = Depends(get_current_user),
    context: tuple[Organization, OrganizationMembership] = Depends(get_current_organization),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
):
    connection = await session.scalar(
        select(MicrosoftConnection)
        .where(
            MicrosoftConnection.id == connection_id,
            MicrosoftConnection.user_id == user.id,
            MicrosoftConnection.organization_id == context[0].id,
        )
        .with_for_update()
    )
    if not connection:
        raise AppError("POWER_BI_CONNECTION_NOT_FOUND", "Connection not found.", 404)
    stored = await SecretService(session, settings).repo.get_for_org(
        connection.secret_id, context[0].id
    )
    await session.delete(connection)
    await session.flush()
    if stored:
        await session.delete(stored)
    AuditService(session).record(
        organization_id=context[0].id,
        user_id=user.id,
        action="power_bi.disconnected",
        resource_type="power_bi_connection",
        resource_id=connection_id,
        metadata={},
    )
    await session.commit()


@router.post("/power-bi/reports/discover", response_model=list[dict[str, str]])
async def discover(
    payload: ReportLookup,
    user: User = Depends(get_current_user),
    context: tuple[Organization, OrganizationMembership] = Depends(get_current_organization),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
):
    return await PowerBIService(session, settings, context[0].id, user.id).discover(payload.query)


@router.post("/power-bi/reports/resolve", response_model=ReportCandidate)
async def resolve(
    payload: ReportLookup,
    user: User = Depends(get_current_user),
    context: tuple[Organization, OrganizationMembership] = Depends(get_current_organization),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
):
    return await PowerBIService(session, settings, context[0].id, user.id).resolve(payload.query)


@router.post("/data-sources/power-bi", response_model=DataSourceResponse, status_code=201)
async def create_source(
    payload: PowerBICreate,
    user: User = Depends(get_current_user),
    context: tuple[Organization, OrganizationMembership] = Depends(get_current_organization),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
):
    if context[1].role not in {"owner", "admin"}:
        raise AppError("FORBIDDEN", "Only workspace administrators can register reports.", 403)
    source = await PowerBIService(session, settings, context[0].id, user.id).create(payload)
    AuditService(session).record(
        organization_id=context[0].id,
        user_id=user.id,
        action="datasource.created",
        resource_type="data_source",
        resource_id=source.id,
        metadata={"kind": "powerbi"},
    )
    await session.commit()
    return await DataSourceService(session, settings).to_response(source)


@router.get("/data-sources/{source_id}/power-bi/reports", response_model=list[ReportResponse])
async def reports(
    source_id: uuid.UUID,
    user: User = Depends(get_current_user),
    context: tuple[Organization, OrganizationMembership] = Depends(get_current_organization),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
):
    return await PowerBIService(session, settings, context[0].id, user.id).reports(source_id)


@router.post("/data-sources/{source_id}/power-bi/refresh")
async def refresh(
    source_id: uuid.UUID,
    user: User = Depends(get_current_user),
    context: tuple[Organization, OrganizationMembership] = Depends(get_current_organization),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
):
    service = PowerBIService(session, settings, context[0].id, user.id)
    await service.reports(source_id)
    await service.metadata(source_id)
    return {"ok": True, "message": "Your report access and model metadata have been refreshed."}


@router.post("/power-bi/reports/{binding_id}/embed-config", response_model=EmbedConfiguration)
async def embed(
    binding_id: uuid.UUID,
    response: Response,
    user: User = Depends(get_current_user),
    context: tuple[Organization, OrganizationMembership] = Depends(get_current_organization),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
):
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return await PowerBIService(session, settings, context[0].id, user.id).embed(binding_id)
