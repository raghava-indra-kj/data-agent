from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.listener import get_listener
from app.jobs.service import JobService

KEEPALIVE_SECONDS = 15.0


def _encode_sse(*, event_id: int, event_type: str, data: dict[str, object]) -> str:
    return (
        f"id: {event_id}\n"
        f"event: {event_type}\n"
        f"data: {json.dumps(data, separators=(',', ':'), default=str)}\n\n"
    )


async def stream_job_events(
    *,
    job_id: uuid.UUID,
    organization_id: uuid.UUID,
    after_sequence: int,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> AsyncIterator[str]:
    listener = get_listener()
    await listener.start()
    # Subscribe before the first read. Anything committed while that read runs either appears
    # in it or arrives as a notification, so nothing can slip between the two.
    async with listener.watch_job_events(job_id) as wake:
        last_sent = after_sequence
        while True:
            # Notifications only say that something changed; PostgreSQL holds the content.
            # Reading by sequence makes a missed notification cost a delay, not an event.
            # The session is closed before the wait, so an idle SSE client holds no
            # connection from the pool.
            async with session_factory() as session:
                events = await JobService(session, settings).list_events(
                    job_id, organization_id, last_sent
                )
            for event in events:
                last_sent = max(last_sent, event.sequence)
                yield _encode_sse(
                    event_id=event.sequence,
                    event_type=event.event_type,
                    data={
                        "sequence": event.sequence,
                        "event_type": event.event_type,
                        "level": event.level,
                        "payload": event.payload,
                        "created_at": event.created_at.isoformat(),
                    },
                )

            try:
                await asyncio.wait_for(wake.get(), KEEPALIVE_SECONDS)
            except TimeoutError:
                yield ": keep-alive\n\n"
