from __future__ import annotations

import uuid

from fastapi import Depends, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.auth.repository import AuthRepository
from app.core.config import Settings, get_settings
from app.core.database import get_db_session
from app.core.errors import AppError
from app.core.security import decode_access_token
from app.organizations.models import Organization, OrganizationMembership
from app.organizations.repository import OrganizationRepository

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AppError("AUTHENTICATION_REQUIRED", "Authentication required.", 401)
    claims = decode_access_token(credentials.credentials, settings)
    user = await AuthRepository(session).get_user(claims.user_id)
    if user is None or not user.is_active:
        raise AppError("AUTHENTICATION_REQUIRED", "Authentication required.", 401)
    session.info["actor_user_id"] = user.id
    return user


async def get_current_organization(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    x_organization_id: str | None = Header(default=None, alias="X-Organization-ID"),
) -> tuple[Organization, OrganizationMembership]:
    repo = OrganizationRepository(session)
    if x_organization_id:
        try:
            organization_id = uuid.UUID(x_organization_id)
        except ValueError as exc:
            raise AppError("INVALID_ORGANIZATION_ID", "Invalid organization identifier.", 400) from exc
        membership = await repo.get_membership(organization_id, current_user.id)
        organization = await repo.get(organization_id)
        if membership is None or organization is None:
            raise AppError("ORGANIZATION_NOT_FOUND", "Organization not found.", 404)
        return organization, membership

    first = await repo.first_membership(current_user.id)
    if first is None:
        raise AppError("ORGANIZATION_NOT_FOUND", "No organization is available for this user.", 404)
    organization, role = first
    membership = await repo.get_membership(organization.id, current_user.id)
    assert membership is not None
    return organization, membership
