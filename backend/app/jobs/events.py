from __future__ import annotations

import json
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.listener import JOB_EVENTS_CHANNEL, JOBS_CHANNEL

_NOTIFY = text("SELECT pg_notify(:channel, :payload)")


async def notify_job_event(session: AsyncSession, job_id: uuid.UUID, sequence: int) -> None:
    """Announce a durable job event to live listeners.

    The payload carries only a pointer. NOTIFY caps payloads at 8000 bytes and job event
    payloads are unbounded JSONB, so subscribers read the row itself from job_events.

    PostgreSQL delivers this when the surrounding transaction commits, which makes the
    announcement atomic with the write it announces.
    """
    await session.execute(
        _NOTIFY,
        {
            "channel": JOB_EVENTS_CHANNEL,
            "payload": json.dumps({"job_id": str(job_id), "sequence": sequence}),
        },
    )


async def notify_job_queued(session: AsyncSession) -> None:
    """Wake an idle worker once this transaction commits."""
    await session.execute(_NOTIFY, {"channel": JOBS_CHANNEL, "payload": ""})
