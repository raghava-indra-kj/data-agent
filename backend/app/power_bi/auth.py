from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import timedelta
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.auth.models import User
from app.core.config import Settings
from app.core.database import get_session_factory
from app.core.errors import AppError
from app.core.time import utc_now
from app.organizations.models import OrganizationMembership
from app.power_bi.models import MicrosoftAuthTransaction, MicrosoftConnection
from app.secrets.service import SecretService

RESOURCE = "https://analysis.windows.net/powerbi/api"
SCOPES = [
    f"{RESOURCE}/{scope}" for scope in ("Item.Read.All", "Item.Execute.All", "Report.Read.All")
]


def configured(settings: Settings) -> bool:
    return bool(
        settings.power_bi_tenant_id
        and settings.power_bi_client_id
        and settings.power_bi_client_secret
    )


def require_enabled(settings: Settings) -> None:
    if not settings.power_bi_enabled:
        raise AppError("POWER_BI_DISABLED", "Power BI integration is not enabled.", 409)
    if not configured(settings):
        raise AppError(
            "POWER_BI_NOT_CONFIGURED", "Ask your administrator to configure Power BI.", 409
        )
    try:
        uuid.UUID(str(settings.power_bi_tenant_id))
        uuid.UUID(str(settings.power_bi_client_id))
    except ValueError as exc:
        raise AppError(
            "POWER_BI_NOT_CONFIGURED", "The Microsoft registration is invalid.", 409
        ) from exc
    for raw in (settings.power_bi_redirect_uri, settings.power_bi_frontend_url):
        parsed = urlparse(raw)
        if (
            parsed.username
            or parsed.password
            or not parsed.hostname
            or (
                parsed.scheme != "https"
                and not (
                    settings.app_env != "production"
                    and parsed.scheme == "http"
                    and parsed.hostname in {"localhost", "127.0.0.1"}
                )
            )
        ):
            raise AppError(
                "POWER_BI_NOT_CONFIGURED", "Microsoft callback URLs must use HTTPS.", 409
            )


def client(settings: Settings, cache: object | None = None):
    # Lazy import keeps installations without Microsoft configuration independent of the SDK.
    import msal

    return msal.ConfidentialClientApplication(
        str(settings.power_bi_client_id),
        authority=f"https://login.microsoftonline.com/{settings.power_bi_tenant_id}",
        client_credential=settings.power_bi_client_secret,
        token_cache=cache,
        timeout=30,
    )


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


async def require_actor(
    session: AsyncSession, organization_id: uuid.UUID, user_id: uuid.UUID
) -> None:
    user = await session.get(User, user_id)
    membership = await session.scalar(
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.user_id == user_id,
        )
    )
    if user is None or not user.is_active or membership is None:
        raise AppError(
            "POWER_BI_ACCESS_DENIED", "Your workspace access is no longer available.", 403
        )


async def begin_connection(
    session: AsyncSession, settings: Settings, organization_id: uuid.UUID, user_id: uuid.UUID
) -> tuple[str, str]:
    require_enabled(settings)
    await require_actor(session, organization_id, user_id)
    app = await run_in_threadpool(client, settings)
    flow = await run_in_threadpool(
        app.initiate_auth_code_flow,
        SCOPES,
        redirect_uri=settings.power_bi_redirect_uri,
        prompt="select_account",
    )
    if not flow.get("auth_uri") or not flow.get("state"):
        raise AppError("POWER_BI_SIGNIN_FAILED", "Microsoft sign-in could not be started.", 502)
    browser_key = secrets.token_urlsafe(32)
    secret = await SecretService(session, settings).create(
        organization_id=organization_id, purpose="power_bi_oauth_transaction", payload=flow
    )
    session.add(
        MicrosoftAuthTransaction(
            organization_id=organization_id,
            user_id=user_id,
            state_hash=digest(flow["state"]),
            browser_hash=digest(browser_key),
            secret_id=secret.id,
            expires_at=utc_now() + timedelta(minutes=10),
        )
    )
    await session.commit()
    return str(flow["auth_uri"]), browser_key


async def finish_connection(
    session: AsyncSession, settings: Settings, response: dict[str, str], browser_key: str
) -> None:
    import msal

    require_enabled(settings)
    transaction = await session.scalar(
        select(MicrosoftAuthTransaction)
        .where(MicrosoftAuthTransaction.state_hash == digest(response.get("state", "")))
        .with_for_update()
    )
    if (
        transaction is None
        or transaction.expires_at < utc_now()
        or not browser_key
        or not secrets.compare_digest(transaction.browser_hash, digest(browser_key))
    ):
        raise AppError("POWER_BI_SIGNIN_EXPIRED", "Sign-in expired. Please connect again.", 400)
    await require_actor(session, transaction.organization_id, transaction.user_id)
    secret_service = SecretService(session, settings)
    flow = await secret_service.read(
        secret_id=transaction.secret_id, organization_id=transaction.organization_id
    )
    cache = msal.SerializableTokenCache()
    app = await run_in_threadpool(client, settings, cache)
    try:
        result = await run_in_threadpool(app.acquire_token_by_auth_code_flow, flow, response)
    except ValueError as exc:
        raise AppError(
            "POWER_BI_SIGNIN_INVALID", "Microsoft sign-in could not be verified.", 400
        ) from exc
    claims = result.get("id_token_claims", {})
    if (
        "access_token" not in result
        or claims.get("tid") != settings.power_bi_tenant_id
        or not claims.get("oid")
    ):
        raise AppError(
            "POWER_BI_SIGNIN_FAILED", "Microsoft sign-in was not completed. Please reconnect.", 400
        )
    accounts = app.get_accounts()
    if len(accounts) != 1:
        raise AppError("POWER_BI_SIGNIN_INVALID", "Select one Microsoft account.", 400)
    existing = await session.scalar(
        select(MicrosoftConnection)
        .where(
            MicrosoftConnection.organization_id == transaction.organization_id,
            MicrosoftConnection.user_id == transaction.user_id,
            MicrosoftConnection.tenant_id == claims["tid"],
        )
        .with_for_update()
    )
    if existing and existing.object_id != claims["oid"]:
        raise AppError(
            "POWER_BI_ACCOUNT_CHANGED",
            "Disconnect the previous Microsoft account before switching accounts.",
            409,
        )
    payload = {"cache": cache.serialize()}
    if existing:
        stored = await secret_service.repo.get_for_org(
            existing.secret_id, transaction.organization_id
        )
        if stored is None:
            raise AppError(
                "POWER_BI_RECONNECT_REQUIRED", "Disconnect and reconnect your account.", 409
            )
        await secret_service.replace(stored, payload)
        existing.status = "connected"
        existing.account_id = accounts[0]["home_account_id"]
        existing.display_name = str(
            claims.get("preferred_username") or claims.get("name") or "Microsoft account"
        )[:255]
    else:
        stored = await secret_service.create(
            organization_id=transaction.organization_id,
            purpose="power_bi_token_cache",
            payload=payload,
        )
        session.add(
            MicrosoftConnection(
                organization_id=transaction.organization_id,
                user_id=transaction.user_id,
                tenant_id=claims["tid"],
                object_id=claims["oid"],
                account_id=accounts[0]["home_account_id"],
                display_name=str(
                    claims.get("preferred_username") or claims.get("name") or "Microsoft account"
                )[:255],
                secret_id=stored.id,
                status="connected",
            )
        )
    transaction_secret = await secret_service.repo.get_for_org(
        transaction.secret_id, transaction.organization_id
    )
    await session.delete(transaction)
    if transaction_secret:
        await session.delete(transaction_secret)
    await session.commit()


async def acquire_token(
    settings: Settings, organization_id: uuid.UUID, user_id: uuid.UUID
) -> tuple[str, int, uuid.UUID]:
    """Refresh under a database row lock, isolated from the caller's transaction."""
    import msal

    require_enabled(settings)
    async with get_session_factory()() as session:
        await require_actor(session, organization_id, user_id)
        connection = await session.scalar(
            select(MicrosoftConnection)
            .where(
                MicrosoftConnection.organization_id == organization_id,
                MicrosoftConnection.user_id == user_id,
                MicrosoftConnection.tenant_id == settings.power_bi_tenant_id,
            )
            .with_for_update()
        )
        if connection is None or connection.status != "connected":
            raise AppError(
                "POWER_BI_RECONNECT_REQUIRED",
                "Connect your Microsoft account to use Power BI.",
                409,
            )
        secret_service = SecretService(session, settings)
        stored = await secret_service.repo.get_for_org(connection.secret_id, organization_id)
        payload = await secret_service.read(
            secret_id=connection.secret_id, organization_id=organization_id
        )
        cache = msal.SerializableTokenCache()
        try:
            cache.deserialize(str(payload.get("cache", "")))
        except (ValueError, TypeError) as exc:
            connection.status = "reconnect_required"
            await session.commit()
            raise AppError(
                "POWER_BI_RECONNECT_REQUIRED", "Reconnect your Microsoft account.", 409
            ) from exc
        app = await run_in_threadpool(client, settings, cache)
        account = next(
            (a for a in app.get_accounts() if a["home_account_id"] == connection.account_id), None
        )
        result = (
            (await run_in_threadpool(app.acquire_token_silent_with_error, SCOPES, account=account))
            if account
            else None
        )
        if not result or "access_token" not in result:
            connection.status = "reconnect_required"
            await session.commit()
            raise AppError(
                "POWER_BI_RECONNECT_REQUIRED",
                "Microsoft requires you to reconnect your account.",
                409,
            )
        if cache.has_state_changed and stored:
            await secret_service.replace(stored, {"cache": cache.serialize()})
        await session.commit()
        return str(result["access_token"]), int(result.get("expires_in", 300)), connection.id
