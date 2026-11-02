from __future__ import annotations

import uuid

from sqlalchemy import text

from app.core.config import Settings
from app.core.database import get_session_factory

# Reserve and hide in one statement. SKIP LOCKED hands each row to exactly one worker, and
# pushing available_at forward hides it for the reservation window, the same way a Redis
# consumer group hid a delivered entry until its pending idle time elapsed.
_RESERVE = text(
    """
    WITH ready AS (
        SELECT id
        FROM jobs
        WHERE status = 'queued' AND available_at <= now()
        ORDER BY created_at, id
        FOR UPDATE SKIP LOCKED
        LIMIT :count
    )
    UPDATE jobs
    SET available_at = now() + make_interval(secs => :reservation)
    FROM ready
    WHERE jobs.id = ready.id
    RETURNING jobs.id
    """
)

_DEFER = text(
    """
    UPDATE jobs
    SET available_at = now() + make_interval(secs => :delay)
    WHERE id = :job_id AND status = 'queued'
    """
)


class PgJobQueue:
    """Dispatch backed by the jobs table itself.

    A job row is its own queue entry, so enqueueing is part of the transaction that creates or
    requeues the job. There is no second system that can fall out of step with job state.
    """

    def __init__(self, settings: Settings) -> None:
        # make_interval takes double precision, so keep these floats.
        self.reservation_seconds = float(settings.worker_reservation_seconds)

    async def reserve(self, count: int) -> list[uuid.UUID]:
        """Take up to `count` dispatchable jobs.

        This commits before the caller claims anything, so it holds no row locks while the
        claim takes the conversation lock and then the job lock, in that order.
        """
        if count <= 0:
            return []
        async with get_session_factory()() as session, session.begin():
            result = await session.execute(
                _RESERVE, {"count": count, "reservation": self.reservation_seconds}
            )
            return list(result.scalars().all())

    async def defer(self, job_id: uuid.UUID, *, delay_seconds: float) -> None:
        """Hold a still-queued job back briefly without consuming an attempt."""
        async with get_session_factory()() as session, session.begin():
            await session.execute(_DEFER, {"job_id": job_id, "delay": float(delay_seconds)})
