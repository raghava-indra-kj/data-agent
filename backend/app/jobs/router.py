from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_organization
from app.core.config import Settings, get_settings
from app.core.database import get_db_session, get_session_factory
from app.jobs.schemas import JobResponse
from app.jobs.service import JobService
from app.jobs.sse import stream_job_events
from app.organizations.models import Organization, OrganizationMembership

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("", response_model=list[JobResponse])
async def list_jobs(
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    context: tuple[Organization, OrganizationMembership] = Depends(get_current_organization),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> list[JobResponse]:
    organization, _ = context
    jobs = await JobService(session, settings).list_for_org(
        organization.id, status=status, limit=limit
    )
    responses = []
    for job, first_event_at, last_event_at in jobs:
        duration_ms = None
        if first_event_at is not None and last_event_at is not None:
            duration_ms = max(0, round((last_event_at - first_event_at).total_seconds() * 1000))
        responses.append(
            JobResponse.model_validate(job).model_copy(update={"duration_ms": duration_ms})
        )
    return responses


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: uuid.UUID,
    context: tuple[Organization, OrganizationMembership] = Depends(get_current_organization),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> JobResponse:
    organization, _ = context
    job = await JobService(session, settings).get_for_org(job_id, organization.id)
    return JobResponse.model_validate(job)


@router.post("/{job_id}/cancel", response_model=JobResponse)
async def cancel_job(
    job_id: uuid.UUID,
    context: tuple[Organization, OrganizationMembership] = Depends(get_current_organization),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> JobResponse:
    organization, _ = context
    job = await JobService(session, settings).request_cancel(job_id, organization.id)
    return JobResponse.model_validate(job)


@router.get("/{job_id}/events")
async def job_events(
    job_id: uuid.UUID,
    after_sequence: int = Query(default=0, ge=0),
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    context: tuple[Organization, OrganizationMembership] = Depends(get_current_organization),
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    organization, _ = context
    session_factory = get_session_factory()
    # Authorize before StreamingResponse sends HTTP 200 headers, using a short-lived session.
    async with session_factory() as session:
        await JobService(session, settings).get_for_org(job_id, organization.id)
    if last_event_id and last_event_id.isdigit():
        after_sequence = max(after_sequence, int(last_event_id))
    generator = stream_job_events(
        job_id=job_id,
        organization_id=organization.id,
        after_sequence=after_sequence,
        session_factory=session_factory,
        settings=settings,
    )
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
