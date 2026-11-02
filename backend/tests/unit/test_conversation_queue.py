import uuid
from contextlib import asynccontextmanager
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy import JSON, Column, MetaData, Table, create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

from app.conversations.models import Message
from app.conversations.repository import ConversationRepository
from app.core.config import Settings
from app.core.time import utc_now
from app.jobs.models import Job
from app.jobs.repository import JobRepository
from app.jobs.service import JobDeferredError, JobService
from app.jobs.worker import Worker


@pytest.fixture
def database():
    # An isolated in-memory database; no application database or runtime data is touched.
    engine = create_engine("sqlite://")
    metadata = MetaData()
    for model in (Job, Message):
        Table(
            model.__tablename__,
            metadata,
            *(
                Column(
                    column.name,
                    JSON() if isinstance(column.type, JSONB) else column.type,
                    primary_key=column.primary_key,
                    nullable=column.nullable,
                )
                for column in model.__table__.columns
            ),
        )
    metadata.create_all(engine)
    with Session(engine) as session:
        yield session, metadata
    engine.dispose()


def insert_job(session, metadata, *, conversation, created, status="queued"):
    job = Job(
        id=uuid.uuid4(),
        conversation_id=conversation,
        organization_id=uuid.uuid4(),
        requested_by=uuid.uuid4(),
        job_type="chat_query",
        status=status,
        input={},
        created_at=created,
        available_at=created,
        attempt_count=0,
        max_attempts=3,
    )
    session.execute(
        metadata.tables["jobs"]
        .insert()
        .values(**{column.name: getattr(job, column.name) for column in Job.__table__.columns})
    )
    session.commit()
    return job


@pytest.mark.parametrize("status", ["queued", "running"])
async def test_only_earlier_active_turns_in_the_same_conversation_block(database, status):
    session, metadata = database
    conversation, other = uuid.uuid4(), uuid.uuid4()
    start = utc_now()
    insert_job(session, metadata, conversation=other, created=start, status="running")
    earlier = insert_job(session, metadata, conversation=conversation, created=start, status=status)
    current = insert_job(
        session, metadata, conversation=conversation, created=start + timedelta(seconds=1)
    )
    insert_job(session, metadata, conversation=conversation, created=start + timedelta(seconds=2))
    repo = JobRepository(SimpleNamespace(scalar=AsyncMock(side_effect=session.scalar)))
    assert await repo.has_earlier_chat(current)
    session.execute(
        metadata.tables["jobs"]
        .update()
        .where(metadata.tables["jobs"].c.id == earlier.id)
        .values(status="cancelled")
    )
    session.commit()
    assert not await repo.has_earlier_chat(current)


async def test_queued_turn_history_includes_previous_answer_and_excludes_future_questions(database):
    session, metadata = database
    conversation = uuid.uuid4()
    start = utc_now()
    first = insert_job(
        session, metadata, conversation=conversation, created=start, status="succeeded"
    )
    current = insert_job(
        session, metadata, conversation=conversation, created=start + timedelta(seconds=1)
    )
    future = insert_job(
        session, metadata, conversation=conversation, created=start + timedelta(seconds=2)
    )
    question_id = uuid.uuid4()
    rows = [
        (uuid.uuid4(), first.id, "user", "First question", 0),
        (question_id, current.id, "user", "Follow up", 1),
        (uuid.uuid4(), future.id, "user", "Future question", 2),
        (uuid.uuid4(), first.id, "assistant", "First answer", 3),
    ]
    for message_id, job_id, role, content, seconds in rows:
        session.execute(
            metadata.tables["messages"]
            .insert()
            .values(
                id=message_id,
                conversation_id=conversation,
                job_id=job_id,
                role=role,
                content=content,
                metadata={},
                created_at=start + timedelta(seconds=seconds),
            )
        )
    session.commit()
    repo = ConversationRepository(SimpleNamespace(execute=AsyncMock(side_effect=session.execute)))
    history = await repo.recent_messages(
        conversation, 50, through_job=current, user_message_id=question_id
    )
    assert [message.content for message in history] == [
        "First question",
        "First answer",
        "Follow up",
    ]


async def test_waiting_turn_is_not_started_or_charged_an_attempt():
    job = SimpleNamespace(
        id=uuid.uuid4(),
        job_type="chat_query",
        conversation_id=uuid.uuid4(),
        status="queued",
        cancel_requested_at=None,
        attempt_count=0,
        started_at=None,
    )
    session = AsyncMock()
    service = JobService(session, Settings(_env_file=None))
    service.repo = SimpleNamespace(
        get=AsyncMock(return_value=job),
        lock=AsyncMock(return_value=job),
        has_earlier_chat=AsyncMock(return_value=True),
    )
    with pytest.raises(JobDeferredError):
        await service.claim(job.id, "worker")
    assert job.status == "queued"
    assert job.attempt_count == 0
    assert job.started_at is None
    session.rollback.assert_awaited_once()
    session.commit.assert_not_awaited()
    assert session.execute.call_args.args[0]._for_update_arg is not None


async def test_worker_defers_waiting_turn_instead_of_holding_a_slot(monkeypatch):
    from app.jobs import worker as module

    session = AsyncMock()

    @asynccontextmanager
    async def factory():
        yield session

    monkeypatch.setattr(module, "get_session_factory", lambda: factory)
    service = Mock(claim=AsyncMock(side_effect=JobDeferredError))
    monkeypatch.setattr(module, "JobService", lambda *args: service)
    worker = Worker.__new__(Worker)
    worker.settings, worker.worker_id = Settings(_env_file=None), "worker"
    worker._wake, worker._wake_tasks = None, set()
    calls = []
    worker.queue = SimpleNamespace(
        defer=AsyncMock(
            side_effect=lambda job_id, *, delay_seconds: calls.append((job_id, delay_seconds))
        )
    )
    job_id = uuid.uuid4()
    await worker._process_job(job_id)
    # The turn goes back to the queue with a short delay; the worker slot is freed at once.
    assert calls == [(job_id, module.DEFER_SECONDS)]
    service.fail.assert_not_called()
    for task in list(worker._wake_tasks):
        task.cancel()
