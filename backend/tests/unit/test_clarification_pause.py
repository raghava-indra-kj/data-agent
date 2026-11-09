"""Pausing an analysis for the user's answers and resuming it, on a real LangGraph graph."""

from __future__ import annotations

import json
import uuid
from typing import Any

import pytest

pytest.importorskip("langchain_openai")

from contextlib import asynccontextmanager  # noqa: E402
from datetime import timedelta  # noqa: E402
from types import SimpleNamespace  # noqa: E402
from unittest.mock import AsyncMock  # noqa: E402

import langchain_openai  # noqa: E402
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel  # noqa: E402
from langchain_core.messages import AIMessage, ToolMessage  # noqa: E402
from langchain_core.outputs import ChatGeneration, ChatResult  # noqa: E402
from langgraph.checkpoint.memory import InMemorySaver  # noqa: E402
from langgraph.types import Command, interrupt  # noqa: E402

from app.agent import jobs as agent_jobs  # noqa: E402
from app.agent import tools  # noqa: E402
from app.agent.clarification import AskUserArgs, build_request  # noqa: E402
from app.agent.deep_agent import (  # noqa: E402  # noqa: E402
    DeepAgentRuntime,
    ProductionDeepAgentFactory,
    ToolBinding,
    _FinishedState,
)
from app.agent.tool_schemas import ExecuteSQLArgs  # noqa: E402
from app.agent.tools import AgentToolContext  # noqa: E402
from app.conversations.service import ConversationService  # noqa: E402
from app.core.config import Settings  # noqa: E402
from app.core.errors import AppError  # noqa: E402
from app.core.time import utc_now  # noqa: E402
from app.jobs.models import Job  # noqa: E402
from app.jobs.service import JobService  # noqa: E402
from app.jobs.state import WAITING_STATUS, assert_transition  # noqa: E402
from app.jobs.worker import JobWaitingForInput, Worker  # noqa: E402
from app.models.client import ModelRuntimeConfiguration  # noqa: E402

QUESTION = {
    "reason": "The division changes the totals.",
    "questions": [{"id": "division", "kind": "choice", "prompt": "Which division?",
                   "options": [{"label": "BID"}, {"label": "LSG"}]}],
}


class ScriptedModel(FakeMessagesListChatModel):
    """Asks a question alongside a query, then answers using the tool results."""

    def bind_tools(self, tools: Any, **kwargs: Any) -> ScriptedModel:
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        results = [message for message in messages if isinstance(message, ToolMessage)]
        if not results:
            message = AIMessage(content="", tool_calls=[
                {"id": "sql-1", "name": "execute_sql",
                 "args": {"data_source_id": str(uuid.uuid4()), "sql": "SELECT 1"}},
                {"id": "ask-1", "name": "ask_user", "args": QUESTION},
            ])
        else:
            answer = next(json.loads(item.content) for item in results if item.name == "ask_user")
            message = AIMessage(content=f"Final answer for {answer['user_answers']}")
        return ChatResult(generations=[ChatGeneration(message=message)])


def factory_runnable(monkeypatch, saver, calls):
    monkeypatch.setattr(
        langchain_openai, "ChatOpenAI", lambda **kwargs: ScriptedModel(responses=[])
    )

    async def execute(**kwargs: object) -> str:
        calls.append("execute_sql")
        return json.dumps({"ok": True, "rows": [[1]]})

    async def ask(**kwargs: object) -> str:
        calls.append("ask_user")
        reply = interrupt({"questions": ["Which division?"]})
        return json.dumps({"ok": True, "user_answers": reply["text"]})

    return ProductionDeepAgentFactory().create(
        model=ModelRuntimeConfiguration(
            profile_id=str(uuid.uuid4()), model_name="fake", base_url="http://x.invalid",
            api_key=None, settings={},
        ),
        tools=[
            ToolBinding("execute_sql", "Run SQL", ExecuteSQLArgs, execute),
            ToolBinding("ask_user", "Ask", AskUserArgs, ask),
        ],
        system_prompt="Ask when unsure.",
        timeout_seconds=1,
        checkpointer=saver,
    )


@pytest.mark.asyncio
async def test_a_paused_run_resumes_with_answers_without_repeating_finished_tools(monkeypatch):
    saver, calls = InMemorySaver(), []
    runnable = factory_runnable(monkeypatch, saver, calls)
    config = {"configurable": {"thread_id": "job-1:1"}}

    paused = await runnable.ainvoke({"messages": [{"role": "user", "content": "Backlog"}]}, config)

    assert paused["__interrupt__"][0].value == {"questions": ["Which division?"]}
    assert sorted(calls) == ["ask_user", "execute_sql"]
    state = await runnable.aget_state(config)
    assert any(task.interrupts for task in state.tasks)

    finished = await runnable.ainvoke(Command(resume={"text": "Division: BID"}), config)

    assert finished["messages"][-1].content == "Final answer for Division: BID"
    # Only the paused call runs again on resume; the query in the same step is not repeated.
    assert calls.count("execute_sql") == 1 and calls.count("ask_user") == 2
    assert "__interrupt__" not in finished
    assert not (await runnable.aget_state(config)).next



SETTINGS = Settings(_env_file=None, clarification_expiry_hours=24)


def job(status: str = "running", **input_data: object) -> Job:
    return Job(
        id=uuid.uuid4(), organization_id=uuid.uuid4(), requested_by=uuid.uuid4(),
        job_type="chat_query", status=status, conversation_id=uuid.uuid4(),
        input={"user_message_id": str(uuid.uuid4()), **input_data},
        attempt_count=1, max_attempts=3, created_at=utc_now(),
        claimed_by="worker-1", lease_expires_at=utc_now(),
    )


def job_service(locked: Job | None = None) -> JobService:
    service = JobService(AsyncMock(), SETTINGS)
    service.repo = SimpleNamespace(lock=AsyncMock(return_value=locked))
    service._append_event_locked = AsyncMock(return_value=SimpleNamespace())
    service._requeue = AsyncMock()
    return service


def test_waiting_jobs_can_resume_be_cancelled_or_expire_but_not_complete():
    assert_transition("running", WAITING_STATUS)
    for target in ("queued", "cancelled", "failed"):
        assert_transition(WAITING_STATUS, target)
    with pytest.raises(AppError):
        assert_transition(WAITING_STATUS, "succeeded")
    with pytest.raises(AppError):
        assert_transition("queued", WAITING_STATUS)


@pytest.mark.asyncio
async def test_pausing_releases_the_worker_and_records_where_to_resume():
    paused = job(resume={"answers": []})
    service = job_service(paused)
    await service.wait_for_input(paused.id, {"run": 1, "question_message_id": "m1"})
    assert paused.status == WAITING_STATUS
    assert paused.claimed_by is None and paused.lease_expires_at is None
    assert paused.input["pause"] == {"run": 1, "question_message_id": "m1"}
    assert "resume" not in paused.input  # earlier answers never leak into the next round
    assert service._append_event_locked.await_args.args[1] == "job.waiting_for_input"


@pytest.mark.asyncio
async def test_answers_queue_the_job_again_and_unanswered_questions_expire():
    asked_at = utc_now() - timedelta(hours=1)
    waiting = job(WAITING_STATUS, pause={"run": 1, "asked_at": asked_at.isoformat()})
    service = job_service(waiting)
    assert service.pause_expired(waiting) is False
    await service.resume_with_answers(waiting, {"answers": [], "text": "Division: BID"})
    assert waiting.status == "queued" and waiting.input["resume"]["text"] == "Division: BID"
    service._requeue.assert_awaited_once_with(waiting)

    stale = job(WAITING_STATUS, pause={"asked_at": (utc_now() - timedelta(hours=25)).isoformat()})
    assert service.pause_expired(stale) is True
    await service.expire_waiting(stale)
    assert (stale.status, stale.error_code) == ("failed", "CLARIFICATION_EXPIRED")


@pytest.mark.asyncio
async def test_cancelling_a_waiting_job_ends_it_immediately():
    waiting = job(WAITING_STATUS, pause={"run": 1})
    service = job_service()
    service.repo = SimpleNamespace(lock_for_organization=AsyncMock(return_value=waiting))
    await service.request_cancel(waiting.id, waiting.organization_id)
    assert waiting.status == "cancelled" and waiting.finished_at is not None


def clarification_message(job_id, *, resumable=True):
    return SimpleNamespace(
        id=uuid.uuid4(), conversation_id=uuid.uuid4(), role="assistant", job_id=job_id,
        metadata_json={
            "clarification": build_request(AskUserArgs.model_validate(QUESTION)),
            "resumable": resumable,
        },
    )


def answering_service(asked, paused, monkeypatch):
    service = ConversationService(AsyncMock(), SETTINGS)
    service.repo = SimpleNamespace(
        lock_for_org=AsyncMock(return_value=SimpleNamespace(id=asked.conversation_id)),
        get_message=AsyncMock(return_value=asked),
        has_user_message_after=AsyncMock(return_value=False),
        message_for_job=AsyncMock(return_value=SimpleNamespace(
            content="Show overdue backlog", metadata_json={}
        )),
        add_message=lambda message: setattr(message, "id", uuid.uuid4()),
    )
    monkeypatch.setattr(
        "app.conversations.service.JobRepository",
        lambda session: SimpleNamespace(lock_for_organization=AsyncMock(return_value=paused)),
    )
    resumed = AsyncMock()
    expired = AsyncMock()
    monkeypatch.setattr(JobService, "resume_with_answers", resumed)
    monkeypatch.setattr(JobService, "expire_waiting", expired)
    monkeypatch.setattr("app.conversations.service.delete_job_checkpoints", AsyncMock())
    return service, resumed, expired


def answers_payload():
    from app.agent.clarification import ClarificationAnswers

    return ClarificationAnswers.model_validate(
        {"answers": [{"question_id": "division", "selected": ["BID"]}]}
    )


@pytest.mark.asyncio
async def test_answers_resume_the_paused_job_with_the_original_request(monkeypatch):
    paused = job(WAITING_STATUS)
    reference = {
        "reference_at": "2026-11-05T18:29:00+00:00", "timezone": "Asia/Kolkata",
        "timezone_source": "client",
    }
    paused.input["time_context"] = reference
    asked = clarification_message(paused.id)
    paused.input["pause"] = {
        "run": 1, "question_message_id": str(asked.id), "asked_at": utc_now().isoformat(),
    }
    service, resumed, _ = answering_service(asked, paused, monkeypatch)

    message, job_id = await service.answer_clarification(
        conversation_id=asked.conversation_id, message_id=asked.id,
        organization_id=paused.organization_id, user_id=uuid.uuid4(), payload=answers_payload(),
    )

    assert job_id == paused.id and message.job_id == paused.id
    assert message.metadata_json["answers_message_id"] == str(asked.id)
    resume = resumed.await_args.args[1]
    assert resume["text"].startswith("Answers to your questions:")
    assert resume["expanded_prompt"].startswith("Show overdue backlog\n\nAnswers")
    assert resume["answer_message_id"] == str(message.id)
    assert paused.input["time_context"] == reference


@pytest.mark.asyncio
@pytest.mark.parametrize("problem", ["expired", "other_question", "not_waiting"])
async def test_closed_or_expired_questions_are_not_resumed(monkeypatch, problem):
    asked_at = utc_now() - timedelta(hours=30 if problem == "expired" else 1)
    paused = job("queued" if problem == "not_waiting" else WAITING_STATUS)
    asked = clarification_message(paused.id)
    paused.input["pause"] = {
        "run": 1, "asked_at": asked_at.isoformat(),
        "question_message_id": str(uuid.uuid4() if problem == "other_question" else asked.id),
    }
    service, resumed, expired = answering_service(asked, paused, monkeypatch)
    with pytest.raises(AppError) as error:
        await service.answer_clarification(
            conversation_id=asked.conversation_id, message_id=asked.id,
            organization_id=paused.organization_id, user_id=uuid.uuid4(),
            payload=answers_payload(),
        )
    expected = "CLARIFICATION_EXPIRED" if problem == "expired" else "CLARIFICATION_CLOSED"
    assert (error.value.code, error.value.status_code) == (expected, 409)
    resumed.assert_not_awaited()
    assert expired.await_count == (1 if problem == "expired" else 0)


@pytest.mark.asyncio
async def test_new_questions_wait_until_pending_questions_are_answered(monkeypatch):
    waiting = job(WAITING_STATUS, pause={"asked_at": utc_now().isoformat()})
    monkeypatch.setattr(
        "app.conversations.service.JobRepository",
        lambda session: SimpleNamespace(
            waiting_chat_for_conversation=AsyncMock(return_value=waiting)
        ),
    )
    service = ConversationService(AsyncMock(), SETTINGS)
    with pytest.raises(AppError) as error:
        await service._ensure_no_pending_questions(waiting.conversation_id)
    assert (error.value.code, error.value.status_code) == ("CLARIFICATION_PENDING", 409)


@pytest.mark.asyncio
async def test_pausable_ask_user_returns_the_answers_given_on_resume(monkeypatch):
    @asynccontextmanager
    async def session():
        yield object()

    monkeypatch.setattr(tools, "get_session_factory", lambda: session)
    monkeypatch.setattr(tools.AgentExecutionRepository, "count_tools", AsyncMock(return_value=1))
    asked: list[dict] = []
    monkeypatch.setattr(
        tools, "interrupt", lambda request: asked.append(request) or {
            "text": "Answers to your questions:\n- Which division? BID",
            "answers": [{"question_id": "division", "selected": ["BID"]}],
        },
    )
    context = AgentToolContext(
        job_id=uuid.uuid4(), organization_id=uuid.uuid4(), conversation_id=uuid.uuid4(),
        allowed_data_source_ids=frozenset(), settings=SETTINGS, pausable=True,
    )
    result = await tools.ask_user(context, QUESTION, uuid.uuid4())
    assert asked[0]["questions"][0]["id"] == "division"
    assert result["user_answers"].endswith("BID") and "clarification" not in result

    monkeypatch.setattr(tools.AgentExecutionRepository, "count_tools", AsyncMock(return_value=2))
    with pytest.raises(tools.AgentToolError) as limited:
        await tools.ask_user(context, QUESTION, uuid.uuid4())
    assert limited.value.code == "CLARIFICATION_LIMIT_REACHED"


@pytest.mark.asyncio
async def test_a_paused_analysis_saves_its_questions_and_hands_the_job_back(monkeypatch):
    saved: list = []

    @asynccontextmanager
    async def session():
        yield SimpleNamespace(commit=AsyncMock())

    monkeypatch.setattr(agent_jobs, "get_session_factory", lambda: session)
    monkeypatch.setattr(
        agent_jobs, "ConversationRepository",
        lambda _: SimpleNamespace(add_message=lambda message: (
            setattr(message, "id", uuid.uuid4()), saved.append(message)
        )),
    )
    request = build_request(AskUserArgs.model_validate(QUESTION))
    with pytest.raises(JobWaitingForInput) as paused:
        await agent_jobs._save_clarification(
            job_id=uuid.uuid4(), conversation_id=uuid.uuid4(), profile_id=uuid.uuid4(),
            request=request, pause={"run": 2},
        )
    assert saved[0].metadata_json["resumable"] is True
    assert paused.value.pause["run"] == 2
    assert paused.value.pause["question_message_id"] == str(saved[0].id)
    assert paused.value.pause["asked_at"] == saved[0].created_at.isoformat()


@pytest.mark.asyncio
async def test_the_worker_parks_paused_jobs_and_cleans_up_finished_ones(monkeypatch):
    paused_job = SimpleNamespace(id=uuid.uuid4(), job_type="chat_query")
    calls: dict[str, list] = {"wait": [], "complete": [], "cleanup": []}

    class FakeJobService:
        def __init__(self, *args):
            pass

        async def claim(self, job_id, worker_id):
            return paused_job

        async def wait_for_input(self, job_id, pause):
            calls["wait"].append(pause)

        async def complete(self, job_id, result):
            calls["complete"].append(result)

    @asynccontextmanager
    async def session():
        yield object()

    import app.jobs.worker as worker_module

    monkeypatch.setattr(worker_module, "JobService", FakeJobService)
    monkeypatch.setattr(worker_module, "get_session_factory", lambda: session)
    monkeypatch.setattr(
        worker_module, "delete_job_checkpoints",
        AsyncMock(side_effect=lambda _session, ids: calls["cleanup"].extend(ids)),
    )

    async def pausing_handler(job_id):
        raise JobWaitingForInput({"run": 1})

    async def finishing_handler(job_id):
        return {"ok": True}

    for handler in (pausing_handler, finishing_handler):
        worker = Worker(SETTINGS, {"chat_query": handler})
        worker._heartbeat = AsyncMock()
        await worker._process_job(paused_job.id)

    assert calls["wait"] == [{"run": 1}]
    assert calls["complete"] == [{"ok": True}]
    assert calls["cleanup"] == [paused_job.id]  # only the finished run releases checkpoints


class StateRunnable:
    def __init__(self, state):
        self.state = state

    async def aget_state(self, config):
        return self.state


@pytest.mark.asyncio
async def test_resume_answers_pending_questions_or_continues_after_a_crash():
    pending = SimpleNamespace(tasks=[SimpleNamespace(interrupts=["q"])], next=("tools",), values={})
    midway = SimpleNamespace(tasks=[SimpleNamespace(interrupts=[])], next=("agent",), values={})
    done = SimpleNamespace(tasks=[], next=(), values={"messages": ["final"]})
    lost = SimpleNamespace(tasks=[], next=(), values={})
    answers = {"text": "BID"}

    command = await DeepAgentRuntime._resume_input(StateRunnable(pending), {}, answers)
    assert isinstance(command, Command) and command.resume == answers
    assert await DeepAgentRuntime._resume_input(StateRunnable(midway), {}, answers) is None
    finished = await DeepAgentRuntime._resume_input(StateRunnable(done), {}, answers)
    assert isinstance(finished, _FinishedState) and finished.values == {"messages": ["final"]}
    with pytest.raises(tools.AgentLimitError) as error:
        await DeepAgentRuntime._resume_input(StateRunnable(lost), {}, answers)
    assert error.value.code == "AGENT_RESUME_UNAVAILABLE"
