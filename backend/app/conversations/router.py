from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.clarification import ClarificationAnswers
from app.auth.dependencies import get_current_organization, get_current_user
from app.auth.models import User
from app.conversations.schemas import (
    ConversationCreate,
    ConversationPage,
    ConversationRename,
    ConversationResponse,
    ConversationTableScopeUpdate,
    MessageAcceptedResponse,
    MessageCreate,
    MessagePage,
    MessageResponse,
    MessageVerificationUpdate,
)
from app.conversations.service import ConversationService
from app.core.config import Settings, get_settings
from app.core.database import get_db_session
from app.core.pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from app.organizations.models import Organization, OrganizationMembership

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.post("", response_model=ConversationResponse, status_code=201)
async def create_conversation(
    payload: ConversationCreate,
    current_user: User = Depends(get_current_user),
    context: tuple[Organization, OrganizationMembership] = Depends(get_current_organization),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> ConversationResponse:
    organization, _ = context
    service = ConversationService(session, settings)
    item = await service.create(
        organization_id=organization.id,
        user_id=current_user.id,
        payload=payload,
    )
    return await service.to_response(item)


@router.get("", response_model=ConversationPage)
async def list_conversations(
    search: str = Query(default="", max_length=240),
    cursor: str | None = Query(default=None, max_length=1024),
    limit: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    context: tuple[Organization, OrganizationMembership] = Depends(get_current_organization),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> ConversationPage:
    organization, _ = context
    return await ConversationService(session, settings).list_page(
        organization.id, search=search, cursor=cursor, limit=limit
    )


@router.get("/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(
    conversation_id: uuid.UUID,
    context: tuple[Organization, OrganizationMembership] = Depends(get_current_organization),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> ConversationResponse:
    organization, _ = context
    service = ConversationService(session, settings)
    item = await service.require_for_org(conversation_id, organization.id)
    return await service.to_response(item)


@router.patch("/{conversation_id}", response_model=ConversationResponse)
async def rename_conversation(
    conversation_id: uuid.UUID,
    payload: ConversationRename,
    context: tuple[Organization, OrganizationMembership] = Depends(get_current_organization),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> ConversationResponse:
    organization, _ = context
    service = ConversationService(session, settings)
    item = await service.rename(conversation_id, organization.id, payload)
    return await service.to_response(item)


@router.put("/{conversation_id}/table-scope", response_model=ConversationResponse)
async def update_table_scope(
    conversation_id: uuid.UUID,
    payload: ConversationTableScopeUpdate,
    context: tuple[Organization, OrganizationMembership] = Depends(get_current_organization),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> ConversationResponse:
    organization, _ = context
    service = ConversationService(session, settings)
    item = await service.update_table_scope(conversation_id, organization.id, payload)
    return await service.to_response(item)


@router.delete("/{conversation_id}", status_code=204)
async def delete_conversation(
    conversation_id: uuid.UUID,
    context: tuple[Organization, OrganizationMembership] = Depends(get_current_organization),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> None:
    organization, _ = context
    service = ConversationService(session, settings)
    await service.delete(conversation_id, organization.id)


@router.delete("", status_code=204)
async def delete_all_conversations(
    context: tuple[Organization, OrganizationMembership] = Depends(get_current_organization),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> None:
    organization, _ = context
    service = ConversationService(session, settings)
    await service.delete_all(organization.id)


@router.get("/{conversation_id}/messages", response_model=MessagePage)
async def list_messages(
    conversation_id: uuid.UUID,
    cursor: str | None = Query(default=None, max_length=1024),
    limit: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    context: tuple[Organization, OrganizationMembership] = Depends(get_current_organization),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> MessagePage:
    organization, _ = context
    return await ConversationService(session, settings).message_page(
        conversation_id, organization.id, cursor=cursor, limit=limit
    )


@router.post(
    "/{conversation_id}/messages",
    response_model=MessageAcceptedResponse,
    status_code=202,
)
async def submit_message(
    conversation_id: uuid.UUID,
    payload: MessageCreate,
    current_user: User = Depends(get_current_user),
    context: tuple[Organization, OrganizationMembership] = Depends(get_current_organization),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> MessageAcceptedResponse:
    organization, _ = context
    message, job_id = await ConversationService(session, settings).submit_message(
        conversation_id=conversation_id,
        organization_id=organization.id,
        user_id=current_user.id,
        payload=payload,
    )
    return MessageAcceptedResponse(message_id=message.id, job_id=job_id)


@router.post(
    "/{conversation_id}/messages/{message_id}/clarification-answers",
    response_model=MessageAcceptedResponse,
    status_code=202,
)
async def answer_clarification(
    conversation_id: uuid.UUID,
    message_id: uuid.UUID,
    payload: ClarificationAnswers,
    current_user: User = Depends(get_current_user),
    context: tuple[Organization, OrganizationMembership] = Depends(get_current_organization),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> MessageAcceptedResponse:
    organization, _ = context
    message, job_id = await ConversationService(
        session, settings
    ).answer_clarification(
        conversation_id=conversation_id,
        message_id=message_id,
        organization_id=organization.id,
        user_id=current_user.id,
        payload=payload,
    )
    return MessageAcceptedResponse(message_id=message.id, job_id=job_id)


@router.patch("/{conversation_id}/messages/{message_id}/verification", response_model=MessageResponse)
async def verify_message(
    conversation_id: uuid.UUID,
    message_id: uuid.UUID,
    payload: MessageVerificationUpdate,
    current_user: User = Depends(get_current_user),
    context: tuple[Organization, OrganizationMembership] = Depends(get_current_organization),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> MessageResponse:
    organization, membership = context
    item = await ConversationService(session, settings).verify_message(
        conversation_id, message_id, organization.id, current_user, membership.role, payload
    )
    return MessageResponse.model_validate(item)
