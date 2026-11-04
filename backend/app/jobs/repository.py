from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.jobs.models import Job, JobEvent
from app.power_bi.access import job_visibility


class JobRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, job: Job) -> None:
        self.session.add(job)

    async def has_earlier_chat(self, job: Job) -> bool:
        return bool(await self.session.scalar(
            select(Job.id).where(
                Job.conversation_id == job.conversation_id,
                Job.job_type == "chat_query",
                Job.status.in_(("queued", "running", "waiting_for_input")),
                or_(Job.created_at < job.created_at,
                    and_(Job.created_at == job.created_at, Job.id < job.id)),
            ).limit(1)
        ))

    async def get(self, job_id: uuid.UUID) -> Job | None:
        return await self.session.get(Job, job_id)

    async def get_for_organization(
        self, job_id: uuid.UUID, organization_id: uuid.UUID
    ) -> Job | None:
        result = await self.session.execute(
            select(Job).where(Job.id == job_id, Job.organization_id == organization_id, job_visibility(self.session))
        )
        return result.scalar_one_or_none()


    async def list_for_organization(
        self,
        organization_id: uuid.UUID,
        *,
        status: str | None = None,
        limit: int = 50,
    ) -> list[tuple[Job, datetime | None, datetime | None]]:
        first_event_at = (
            select(func.min(JobEvent.created_at))
            .where(JobEvent.job_id == Job.id)
            .correlate(Job)
            .scalar_subquery()
        )
        last_event_at = (
            select(func.max(JobEvent.created_at))
            .where(JobEvent.job_id == Job.id)
            .correlate(Job)
            .scalar_subquery()
        )
        statement = select(Job, first_event_at, last_event_at).where(
            Job.organization_id == organization_id, job_visibility(self.session)
        )
        if status is not None:
            statement = statement.where(Job.status == status)
        result = await self.session.execute(
            statement.order_by(Job.created_at.desc()).limit(limit)
        )
        return [
            (job, first_recorded_at, last_recorded_at)
            for job, first_recorded_at, last_recorded_at in result.all()
        ]


    async def count_active_for_user(self, organization_id: uuid.UUID, user_id: uuid.UUID) -> int:
        value = await self.session.scalar(
            select(func.count(Job.id)).where(
                Job.organization_id == organization_id,
                Job.requested_by == user_id,
                Job.status.in_(("queued", "running")),
            )
        )
        return int(value or 0)

    async def count_active_for_organization(self, organization_id: uuid.UUID) -> int:
        value = await self.session.scalar(
            select(func.count(Job.id)).where(
                Job.organization_id == organization_id,
                Job.status.in_(("queued", "running")),
            )
        )
        return int(value or 0)

    async def count_queued(self) -> int:
        """Jobs waiting for a worker across every organization."""
        value = await self.session.scalar(
            select(func.count(Job.id)).where(Job.status == "queued")
        )
        return int(value or 0)

    async def status_counts_for_organization(self, organization_id: uuid.UUID) -> dict[str, int]:
        result = await self.session.execute(
            select(Job.status, func.count(Job.id))
            .where(Job.organization_id == organization_id)
            .group_by(Job.status)
        )
        return {str(status): int(count) for status, count in result.all()}

    async def lock(self, job_id: uuid.UUID) -> Job | None:
        result = await self.session.execute(
            select(Job).where(Job.id == job_id).with_for_update()
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def lock_for_organization(
        self, job_id: uuid.UUID, organization_id: uuid.UUID
    ) -> Job | None:
        result = await self.session.execute(
            select(Job)
            .where(Job.id == job_id, Job.organization_id == organization_id, job_visibility(self.session))
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def next_sequence(self, job_id: uuid.UUID) -> int:
        result = await self.session.execute(
            select(func.coalesce(func.max(JobEvent.sequence), 0)).where(JobEvent.job_id == job_id)
        )
        return int(result.scalar_one()) + 1

    def add_event(self, event: JobEvent) -> None:
        self.session.add(event)

    async def list_events(self, job_id: uuid.UUID, after_sequence: int = 0) -> list[JobEvent]:
        result = await self.session.execute(
            select(JobEvent)
            .where(JobEvent.job_id == job_id, JobEvent.sequence > after_sequence)
            .order_by(JobEvent.sequence.asc())
        )
        return list(result.scalars().all())

    async def list_waiting(self, limit: int = 100) -> list[Job]:
        result = await self.session.execute(
            select(Job)
            .where(Job.status == "waiting_for_input")
            .order_by(Job.created_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def waiting_chat_for_conversation(self, conversation_id: uuid.UUID) -> Job | None:
        result = await self.session.execute(
            select(Job)
            .where(
                Job.conversation_id == conversation_id,
                Job.job_type == "chat_query",
                Job.status == "waiting_for_input",
            )
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_stale_running(self, before: datetime, limit: int = 100) -> list[Job]:
        result = await self.session.execute(
            select(Job)
            .where(
                Job.status == "running",
                Job.lease_expires_at.is_not(None),
                Job.lease_expires_at < before,
            )
            .order_by(Job.lease_expires_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())
