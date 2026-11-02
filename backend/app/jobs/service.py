from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.conversations.models import Conversation
from app.core.config import Settings
from app.core.errors import AppError
from app.core.time import utc_now
from app.jobs.events import notify_job_event, notify_job_queued
from app.jobs.models import Job, JobEvent
from app.jobs.repository import JobRepository
from app.jobs.state import TERMINAL_STATUSES, WAITING_STATUS, assert_transition
from app.organizations.models import Organization


class JobDeferredError(Exception):
    """An accepted question is waiting for an earlier turn in its conversation."""


class JobService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.repo = JobRepository(session)

    async def create_job(
        self,
        *,
        organization_id: uuid.UUID,
        requested_by: uuid.UUID,
        job_type: str,
        input_data: dict[str, object] | None = None,
        max_attempts: int | None = None,
        conversation_id: uuid.UUID | None = None,
    ) -> Job:
        # Serialize active-limit checks per organization so multiple API replicas cannot race past
        # the configured workspace/user concurrency caps. The internal control DB is PostgreSQL.
        await self.session.execute(
            select(Organization.id).where(Organization.id == organization_id).with_for_update()
        )
        active_user = await self.repo.count_active_for_user(organization_id, requested_by)
        if active_user >= self.settings.max_active_jobs_per_user:
            raise AppError(
                "USER_ACTIVE_JOB_LIMIT_REACHED",
                "You already have the maximum number of active jobs.",
                429,
            )
        active_org = await self.repo.count_active_for_organization(organization_id)
        if active_org >= self.settings.max_active_jobs_per_organization:
            raise AppError(
                "ORGANIZATION_ACTIVE_JOB_LIMIT_REACHED",
                "This workspace already has the maximum number of active jobs.",
                429,
            )
        now = utc_now()
        job = Job(
            organization_id=organization_id,
            requested_by=requested_by,
            job_type=job_type,
            status="queued",
            conversation_id=conversation_id,
            input=input_data or {},
            attempt_count=0,
            max_attempts=max_attempts or self.settings.job_max_attempts,
            created_at=now,
            available_at=now,
        )
        self.repo.add(job)
        await self.session.flush()
        await self._append_event_locked(job, "job.queued", {"job_type": job_type})
        # The row is the queue entry, so creating and enqueueing commit together. There is no
        # window where a job exists but no worker will ever see it.
        await notify_job_queued(self.session)
        await self.session.commit()
        return job

    async def list_for_org(
        self, organization_id: uuid.UUID, *, status: str | None = None, limit: int = 50
    ) -> list[tuple[Job, datetime | None, datetime | None]]:
        if status is not None and status not in {
            "queued", "running", WAITING_STATUS, "succeeded", "failed", "cancelled"
        }:
            raise AppError("INVALID_JOB_STATUS", "Invalid job status filter.", 400)
        return await self.repo.list_for_organization(
            organization_id, status=status, limit=limit
        )

    async def get_for_org(self, job_id: uuid.UUID, organization_id: uuid.UUID) -> Job:
        job = await self.repo.get_for_organization(job_id, organization_id)
        if job is None:
            raise AppError("JOB_NOT_FOUND", "Job not found.", 404)
        return job

    async def list_events(
        self, job_id: uuid.UUID, organization_id: uuid.UUID, after_sequence: int = 0
    ) -> list[JobEvent]:
        await self.get_for_org(job_id, organization_id)
        return await self.repo.list_events(job_id, after_sequence)

    async def request_cancel(self, job_id: uuid.UUID, organization_id: uuid.UUID) -> Job:
        job = await self.repo.lock_for_organization(job_id, organization_id)
        if job is None:
            raise AppError("JOB_NOT_FOUND", "Job not found.", 404)
        if job.status in TERMINAL_STATUSES:
            await self.session.rollback()
            return job
        now = utc_now()
        job.cancel_requested_at = now
        if job.status in ("queued", WAITING_STATUS):
            assert_transition(job.status, "cancelled")
            job.status = "cancelled"
            job.finished_at = now
            await self._append_event_locked(job, "job.cancelled", {})
        else:
            await self._append_event_locked(job, "job.cancel_requested", {})
        await self.session.commit()
        return job

    async def claim(self, job_id: uuid.UUID, worker_id: str) -> Job | None:
        snapshot = await self.repo.get(job_id)
        if snapshot and snapshot.job_type == "chat_query" and snapshot.conversation_id:
            # All workers take the conversation lock before the job lock. No lock is
            # held while analysis runs; the persisted running status gates later turns.
            await self.session.execute(
                select(Conversation.id).where(
                    Conversation.id == snapshot.conversation_id
                ).with_for_update()
            )
        job = await self.repo.lock(job_id)
        if job is None:
            await self.session.rollback()
            return None
        now = utc_now()
        if job.status in TERMINAL_STATUSES:
            await self.session.rollback()
            return None
        if job.cancel_requested_at is not None:
            if job.status != "cancelled":
                assert_transition(job.status, "cancelled")
                job.status = "cancelled"
                job.finished_at = now
                await self._append_event_locked(job, "job.cancelled", {})
                await self.session.commit()
            return None
        if job.status == "running" and job.lease_expires_at and job.lease_expires_at > now:
            await self.session.rollback()
            return None
        if (
            job.job_type == "chat_query"
            and job.conversation_id
            and await self.repo.has_earlier_chat(job)
        ):
            await self.session.rollback()
            raise JobDeferredError()
        if job.status == "running":
            assert_transition("running", "queued")
            job.status = "queued"
        assert_transition(job.status, "running")
        job.status = "running"
        job.claimed_by = worker_id
        job.lease_expires_at = now + timedelta(seconds=self.settings.worker_lease_seconds)
        job.attempt_count += 1
        if job.started_at is None:
            job.started_at = now
        await self._append_event_locked(
            job, "job.started", {"attempt": job.attempt_count, "worker_id": worker_id}
        )
        await self.session.commit()
        return job

    async def heartbeat(self, job_id: uuid.UUID, worker_id: str) -> bool:
        job = await self.repo.lock(job_id)
        if job is None or job.status != "running" or job.claimed_by != worker_id:
            await self.session.rollback()
            return False
        job.lease_expires_at = utc_now() + timedelta(seconds=self.settings.worker_lease_seconds)
        await self.session.commit()
        return True

    async def is_cancel_requested(self, job_id: uuid.UUID) -> bool:
        job = await self.repo.get(job_id)
        return bool(job and job.cancel_requested_at is not None)

    async def complete(self, job_id: uuid.UUID, result: dict[str, object] | None) -> None:
        job = await self.repo.lock(job_id)
        if job is None:
            raise AppError("JOB_NOT_FOUND", "Job not found.", 404)
        if job.cancel_requested_at is not None:
            await self._finish_cancelled(job)
            return
        assert_transition(job.status, "succeeded")
        job.status = "succeeded"
        job.result = result
        job.finished_at = utc_now()
        job.lease_expires_at = None
        await self._append_event_locked(job, "job.completed", {})
        await self.session.commit()

    async def fail(
        self,
        job_id: uuid.UUID,
        *,
        code: str,
        message: str,
        retryable: bool,
    ) -> bool:
        job = await self.repo.lock(job_id)
        if job is None:
            return False
        if job.cancel_requested_at is not None:
            await self._finish_cancelled(job)
            return False
        now = utc_now()
        if retryable and job.attempt_count < job.max_attempts:
            assert_transition(job.status, "queued")
            job.status = "queued"
            job.claimed_by = None
            job.lease_expires_at = None
            await self._append_event_locked(
                job,
                "job.retry_scheduled",
                {"attempt": job.attempt_count, "max_attempts": job.max_attempts},
                level="warning",
            )
            await self._requeue(job)
            await self.session.commit()
            return True
        assert_transition(job.status, "failed")
        job.status = "failed"
        job.error_code = code[:100]
        job.error_message = message[:2000]
        job.finished_at = now
        job.lease_expires_at = None
        await self._append_event_locked(
            job, "job.failed", {"code": job.error_code}, level="error"
        )
        await self.session.commit()
        return False

    async def wait_for_input(self, job_id: uuid.UUID, pause: dict[str, object]) -> None:
        """Release the worker while the analysis waits for the user's answers."""
        job = await self.repo.lock(job_id)
        if job is None:
            raise AppError("JOB_NOT_FOUND", "Job not found.", 404)
        if job.cancel_requested_at is not None:
            await self._finish_cancelled(job)
            return
        assert_transition(job.status, WAITING_STATUS)
        job.status = WAITING_STATUS
        job.input = {
            **{key: value for key, value in job.input.items() if key != "resume"},
            "pause": pause,
        }
        job.claimed_by = None
        job.lease_expires_at = None
        await self._append_event_locked(
            job,
            "job.waiting_for_input",
            {"question_message_id": pause.get("question_message_id")},
        )
        await self.session.commit()

    def pause_expired(self, job: Job) -> bool:
        pause = job.input.get("pause") if isinstance(job.input, dict) else None
        asked_at = pause.get("asked_at") if isinstance(pause, dict) else None
        if job.status != WAITING_STATUS or not isinstance(asked_at, str):
            return False
        expiry = timedelta(hours=self.settings.clarification_expiry_hours)
        return datetime.fromisoformat(asked_at) + expiry < utc_now()

    async def resume_with_answers(self, job: Job, resume: dict[str, object]) -> None:
        """Queue a paused analysis again with the answers; the caller holds the job lock."""
        assert_transition(job.status, "queued")
        job.status = "queued"
        job.input = {**job.input, "resume": resume}
        await self._append_event_locked(
            job, "job.resumed", {"answer_message_id": resume.get("answer_message_id")}
        )
        await self._requeue(job)
        await self.session.commit()

    async def expire_waiting(self, job: Job) -> None:
        """End a paused analysis whose questions went unanswered; the caller holds the lock."""
        assert_transition(job.status, "failed")
        job.status = "failed"
        job.error_code = "CLARIFICATION_EXPIRED"
        job.error_message = "The questions were not answered in time."
        job.finished_at = utc_now()
        await self._append_event_locked(
            job, "job.failed", {"code": job.error_code}, level="warning"
        )
        await self.session.commit()

    async def expire_waiting_jobs(self, *, limit: int = 100) -> list[uuid.UUID]:
        expired: list[uuid.UUID] = []
        for job in await self.repo.list_waiting(limit=limit):
            locked = await self.repo.lock(job.id)
            if locked is not None and self.pause_expired(locked):
                await self.expire_waiting(locked)
                expired.append(locked.id)
            else:
                await self.session.rollback()
        return expired

    async def recover_abandoned_jobs(self, *, before, limit: int = 100) -> int:
        """Requeue jobs whose worker lease expired.

        A reserved job that no worker claimed becomes dispatchable again on its own once its
        reservation lapses. This covers the other case: a worker that claimed a job and then
        died without releasing it.
        """
        rows = await self.repo.list_stale_running(before, limit=limit)
        recovered = 0
        for candidate in rows:
            job = await self.repo.lock(candidate.id)
            if (
                job is None
                or job.status != "running"
                or job.lease_expires_at is None
                or job.lease_expires_at >= before
            ):
                continue
            assert_transition("running", "queued")
            job.status = "queued"
            job.claimed_by = None
            job.lease_expires_at = None
            await self._append_event_locked(
                job, "job.recovered", {"reason": "expired_worker_lease"}
            )
            await self._requeue(job)
            await self.session.commit()
            recovered += 1
        return recovered

    async def append_event(
        self,
        job_id: uuid.UUID,
        event_type: str,
        payload: dict[str, object] | None = None,
        *,
        level: str = "info",
    ) -> JobEvent:
        job = await self.repo.lock(job_id)
        if job is None:
            raise AppError("JOB_NOT_FOUND", "Job not found.", 404)
        event = await self._append_event_locked(job, event_type, payload or {}, level=level)
        await self.session.commit()
        return event

    async def _finish_cancelled(self, job: Job) -> None:
        if job.status not in TERMINAL_STATUSES:
            assert_transition(job.status, "cancelled")
            job.status = "cancelled"
            job.finished_at = utc_now()
            job.lease_expires_at = None
            await self._append_event_locked(job, "job.cancelled", {})
            await self.session.commit()

    async def _requeue(self, job: Job) -> None:
        """Make a queued job dispatchable now and wake a worker when this transaction commits."""
        job.available_at = utc_now()
        await notify_job_queued(self.session)

    async def _append_event_locked(
        self,
        job: Job,
        event_type: str,
        payload: dict[str, object],
        *,
        level: str = "info",
    ) -> JobEvent:
        sequence = await self.repo.next_sequence(job.id)
        event = JobEvent(
            job_id=job.id,
            sequence=sequence,
            event_type=event_type,
            level=level,
            payload=payload,
            created_at=utc_now(),
        )
        self.repo.add_event(event)
        await self.session.flush()
        # Announced inside the transaction, so the notification and the row it points at become
        # visible together. A rollback discards both.
        await notify_job_event(self.session, job.id, sequence)
        return event
