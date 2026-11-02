from __future__ import annotations

import asyncio
import logging
import os
import socket
import uuid

from app.agent.checkpoints import delete_job_checkpoints
from app.core.config import Settings
from app.core.database import get_session_factory
from app.core.listener import get_listener
from app.jobs.handlers import JobHandlerRegistry, registry
from app.jobs.queue import PgJobQueue
from app.jobs.service import JobDeferredError, JobService

logger = logging.getLogger(__name__)

# How long a turn waiting on an earlier turn in its conversation is held back.
DEFER_SECONDS = 1.0


class RetryableJobError(Exception):
    """A handler may raise this only for transient infrastructure failures."""


class JobWaitingForInput(Exception):  # noqa: N818 - a pause signal, not an error
    """A handler paused for the user's answers; the worker releases the job until then."""

    def __init__(self, pause: dict[str, object]) -> None:
        self.pause = pause
        super().__init__("waiting for input")


class JobFailureError(Exception):
    """A handler may raise a sanitized, machine-readable job failure."""

    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        self.code = code
        self.public_message = message
        self.retryable = retryable
        super().__init__(message)


class Worker:
    def __init__(self, settings: Settings, handlers: JobHandlerRegistry = registry) -> None:
        self.settings = settings
        self.handlers = handlers
        self.queue = PgJobQueue(settings)
        self.worker_id = settings.worker_id or self._default_worker_id()
        self._stop = asyncio.Event()
        self._wake: asyncio.Queue[None] | None = None
        self._wake_tasks: set[asyncio.Task[None]] = set()

    @staticmethod
    def _default_worker_id() -> str:
        return f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"

    async def run(self) -> None:
        listener = get_listener()
        await listener.start()
        logger.info(
            "worker_started",
            extra={"worker_id": self.worker_id, "concurrency": self.settings.worker_concurrency},
        )
        active: set[asyncio.Task[None]] = set()
        try:
            async with listener.watch_jobs() as wake:
                self._wake = wake
                while not self._stop.is_set():
                    finished = {task for task in active if task.done()}
                    if finished:
                        active.difference_update(finished)
                        await asyncio.gather(*finished, return_exceptions=True)

                    capacity = self.settings.worker_concurrency - len(active)
                    if capacity <= 0:
                        done, _ = await asyncio.wait(active, return_when=asyncio.FIRST_COMPLETED)
                        active.difference_update(done)
                        await asyncio.gather(*done, return_exceptions=True)
                        continue

                    job_ids = await self.queue.reserve(capacity)
                    for job_id in job_ids:
                        active.add(asyncio.create_task(self._process_job(job_id)))
                    if len(job_ids) < capacity:
                        # Nothing else is ready right now.
                        await self._wait_for_work()
        finally:
            self._wake = None
            for task in self._wake_tasks:
                task.cancel()
            if self._wake_tasks:
                await asyncio.gather(*self._wake_tasks, return_exceptions=True)
            if active:
                await asyncio.gather(*active, return_exceptions=True)

    def stop(self) -> None:
        self._stop.set()

    async def _wait_for_work(self) -> None:
        """Sleep until a job is queued, bounded so a missed notification cannot stall work."""
        timeout = self.settings.worker_poll_interval_ms / 1000
        if self._wake is None:
            await asyncio.sleep(timeout)
            return
        try:
            await asyncio.wait_for(self._wake.get(), timeout)
        except TimeoutError:
            pass

    def _wake_later(self, delay: float) -> None:
        """Re-check after a deferred job becomes available, rather than waiting for the poll."""

        async def _later() -> None:
            await asyncio.sleep(delay)
            queue = self._wake
            if queue is not None:
                try:
                    queue.put_nowait(None)
                except asyncio.QueueFull:
                    pass

        task = asyncio.create_task(_later())
        self._wake_tasks.add(task)
        task.add_done_callback(self._wake_tasks.discard)

    async def _process_job(self, job_id: uuid.UUID) -> None:
        session_factory = get_session_factory()
        # Claim and persist ownership in a short-lived DB session. Do not hold a PostgreSQL
        # transaction/session while the potentially long handler talks to external systems.
        try:
            async with session_factory() as session:
                service = JobService(session, self.settings)
                job = await service.claim(job_id, self.worker_id)
        except JobDeferredError:
            # Hold the turn back instead of occupying a worker slot while it waits. This does
            # not consume an analysis attempt or emit repeated progress events.
            await self.queue.defer(job_id, delay_seconds=DEFER_SECONDS)
            self._wake_later(DEFER_SECONDS)
            return
        except asyncio.CancelledError:
            raise
        except Exception:
            # Record the failure rather than letting the job silently come back round on every
            # reservation (asyncio.gather(..., return_exceptions=True) in run() would otherwise
            # discard the error without a trace).
            logger.exception("job_claim_failed", extra={"job_id": str(job_id)})
            try:
                async with session_factory() as session:
                    await JobService(session, self.settings).fail(
                        job_id,
                        code="JOB_CLAIM_FAILED",
                        message="The job failed unexpectedly while being claimed.",
                        retryable=False,
                    )
            except Exception:
                logger.exception("job_claim_failure_record_failed", extra={"job_id": str(job_id)})
            return
        if job is None:
            # Already terminal, cancelled, or held by a live lease. It is no longer queued, so
            # it will not be offered again.
            return

        handler = self.handlers.get(job.job_type)
        if handler is None:
            async with session_factory() as session:
                await JobService(session, self.settings).fail(
                    job.id,
                    code="JOB_HANDLER_NOT_REGISTERED",
                    message="No worker handler is registered for this job type.",
                    retryable=False,
                )
            return

        heartbeat_task = asyncio.create_task(self._heartbeat(job.id))
        try:
            result = await handler(job.id)
            async with session_factory() as session:
                await JobService(session, self.settings).complete(job.id, result)
            await self._release_checkpoints(job.id)
        except JobWaitingForInput as exc:
            async with session_factory() as session:
                await JobService(session, self.settings).wait_for_input(job.id, exc.pause)
        except JobFailureError as exc:
            async with session_factory() as session:
                retried = await JobService(session, self.settings).fail(
                    job.id,
                    code=exc.code,
                    message=exc.public_message,
                    retryable=exc.retryable,
                )
            if not retried:
                await self._release_checkpoints(job.id)
        except RetryableJobError as exc:
            async with session_factory() as session:
                await JobService(session, self.settings).fail(
                    job.id,
                    code="TRANSIENT_JOB_FAILURE",
                    message=str(exc) or "Transient job failure.",
                    retryable=True,
                )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("job_handler_failed", extra={"job_id": str(job.id)})
            async with session_factory() as session:
                await JobService(session, self.settings).fail(
                    job.id,
                    code="JOB_EXECUTION_FAILED",
                    message="The job failed unexpectedly.",
                    retryable=False,
                )
        finally:
            heartbeat_task.cancel()
            await asyncio.gather(heartbeat_task, return_exceptions=True)

    async def _release_checkpoints(self, job_id: uuid.UUID) -> None:
        """A finished job never resumes, so its paused-analysis state is no longer needed."""
        try:
            async with get_session_factory()() as session:
                await delete_job_checkpoints(session, [job_id])
        except Exception:
            logger.exception("checkpoint_cleanup_failed", extra={"job_id": str(job_id)})

    async def _heartbeat(self, job_id: uuid.UUID) -> None:
        session_factory = get_session_factory()
        while True:
            await asyncio.sleep(self.settings.worker_heartbeat_seconds)
            async with session_factory() as session:
                service = JobService(session, self.settings)
                alive = await service.heartbeat(job_id, self.worker_id)
                if not alive:
                    return
