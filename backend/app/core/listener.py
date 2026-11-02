from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections import defaultdict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import asyncpg

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# Two fixed channels. Routing to the interested subscriber happens in-process, so no
# LISTEN/UNLISTEN runs per client and the connection setup never changes at runtime.
JOBS_CHANNEL = "dbassistant_jobs_new"
JOB_EVENTS_CHANNEL = "dbassistant_job_events"

RECONNECT_DELAY_SECONDS = 2.0
CONNECTION_CHECK_SECONDS = 30.0


def to_asyncpg_dsn(database_url: str) -> str:
    """asyncpg connects on its own, so SQLAlchemy's dialect suffix has to go."""
    return database_url.replace("postgresql+asyncpg://", "postgresql://", 1)


def _offer(queue: asyncio.Queue[None]) -> None:
    try:
        queue.put_nowait(None)
    except asyncio.QueueFull:
        # A wake-up is already pending. Consumers re-read every committed row they have not
        # seen, so one wake-up covers any number of notifications.
        pass


class PostgresListener:
    """One long-lived connection that fans PostgreSQL notifications out in-process.

    LISTEN is connection-scoped and long-lived, so this connection stays outside the
    SQLAlchemy pool; an SSE client must never hold a pooled connection open.

    Notifications are advisory. Every consumer re-reads committed rows after a wake-up, so a
    dropped notification costs a short delay and nothing else. That is what lets this
    reconnect freely without tracking which notifications were missed.
    """

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._job_event_waiters: dict[uuid.UUID, set[asyncio.Queue[None]]] = defaultdict(set)
        self._queue_waiters: set[asyncio.Queue[None]] = set()
        self._task: asyncio.Task[None] | None = None
        self._stopping = False

    async def start(self) -> None:
        if self._task is None or self._task.done():
            self._stopping = False
            self._task = asyncio.create_task(self._run())

    async def aclose(self) -> None:
        self._stopping = True
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    @asynccontextmanager
    async def watch_jobs(self) -> AsyncIterator[asyncio.Queue[None]]:
        """Wake whenever a job is queued. Workers wait on this instead of polling tightly."""
        queue: asyncio.Queue[None] = asyncio.Queue(maxsize=1)
        self._queue_waiters.add(queue)
        try:
            yield queue
        finally:
            self._queue_waiters.discard(queue)

    @asynccontextmanager
    async def watch_job_events(self, job_id: uuid.UUID) -> AsyncIterator[asyncio.Queue[None]]:
        """Wake whenever this job records an event."""
        queue: asyncio.Queue[None] = asyncio.Queue(maxsize=1)
        self._job_event_waiters[job_id].add(queue)
        try:
            yield queue
        finally:
            waiters = self._job_event_waiters.get(job_id)
            if waiters is not None:
                waiters.discard(queue)
                if not waiters:
                    self._job_event_waiters.pop(job_id, None)

    def _wake_all(self) -> None:
        for queue in list(self._queue_waiters):
            _offer(queue)
        for waiters in list(self._job_event_waiters.values()):
            for queue in list(waiters):
                _offer(queue)

    def _on_jobs(self, *_args: object) -> None:
        for queue in list(self._queue_waiters):
            _offer(queue)

    def _on_job_event(self, _conn: object, _pid: object, _channel: object, payload: str) -> None:
        try:
            job_id = uuid.UUID(str(json.loads(payload)["job_id"]))
        except Exception:
            logger.warning("job_event_notification_unreadable")
            return
        for queue in list(self._job_event_waiters.get(job_id, ())):
            _offer(queue)

    async def _run(self) -> None:
        while not self._stopping:
            connection: asyncpg.Connection | None = None
            try:
                connection = await asyncpg.connect(self._dsn)
                await connection.add_listener(JOBS_CHANNEL, self._on_jobs)
                await connection.add_listener(JOB_EVENTS_CHANNEL, self._on_job_event)
                # Notifications sent while disconnected are gone. Wake every subscriber so it
                # re-reads, which is also what makes the first connection safe.
                self._wake_all()
                while not self._stopping:
                    await asyncio.sleep(CONNECTION_CHECK_SECONDS)
                    # Doubles as a keep-alive and as the check that the connection is alive.
                    await connection.execute("SELECT 1")
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("job_listener_connection_failed")
            finally:
                if connection is not None:
                    try:
                        # Synchronous: awaiting a graceful close here would be interrupted when
                        # this task is cancelled at shutdown, leaving the connection open.
                        connection.terminate()
                    except Exception:
                        logger.debug("job_listener_close_failed", exc_info=True)
            if not self._stopping:
                await asyncio.sleep(RECONNECT_DELAY_SECONDS)


_listener: PostgresListener | None = None


def get_listener() -> PostgresListener:
    global _listener
    if _listener is None:
        _listener = PostgresListener(to_asyncpg_dsn(get_settings().database_url))
    return _listener


async def close_listener() -> None:
    global _listener
    if _listener is not None:
        await _listener.aclose()
    _listener = None
