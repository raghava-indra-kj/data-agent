"""Request-local visibility for delegated results; internal worker sessions set their actor."""

from __future__ import annotations

import uuid

from sqlalchemy import func, or_, true
from sqlalchemy.ext.asyncio import AsyncSession


def actor_id(session: AsyncSession) -> uuid.UUID | None:
    info = session.info
    value = info.get("actor_user_id") if isinstance(info, dict) else None
    return value if isinstance(value, uuid.UUID) else None


def conversation_visibility(session: AsyncSession):
    from app.conversations.models import Conversation

    actor = actor_id(session)
    return (
        or_(Conversation.private_to_creator.is_(False), Conversation.created_by == actor)
        if actor
        else true()
    )


def job_visibility(session: AsyncSession):
    from app.jobs.models import Job

    actor = actor_id(session)
    return (
        or_(
            func.coalesce(Job.input["power_bi_private"].as_boolean(), False).is_(False),
            Job.requested_by == actor,
        )
        if actor
        else true()
    )
