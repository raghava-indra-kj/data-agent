from __future__ import annotations

import json
import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from app.agent import deep_agent as runtime_module
from app.agent import tools
from app.agent.clarification import (
    EXTRA_QUESTION_ID,
    OTHER_LABEL,
    AskUserArgs,
    ClarificationAnswers,
    ClarificationError,
    answers_text,
    build_request,
    questions_markdown,
    validate_answers,
)
from app.agent.deep_agent import DeepAgentRuntime, ProductionDeepAgentFactory, ToolBinding
from app.agent.tools import AgentToolContext, AgentToolError, AgentTurnEnded
from app.conversations.service import ConversationService
from app.core.config import Settings
from app.core.errors import AppError
from app.models.client import ModelRuntimeConfiguration


def args(**overrides: object) -> AskUserArgs:
    payload: dict[str, object] = {
        "reason": "Division and date range change the totals.",
        "questions": [
            {
                "id": "division",
                "kind": "choice",
                "prompt": "Which division?",
                "options": [
                    {"label": "BID"}, {"label": "LSG"}, {"label": "Other (please specify)"},
                ],
            },
            {"id": "regions", "kind": "choice", "prompt": "Which regions?", "multiple": True,
             "options": [{"label": "ANZ"}, {"label": "Japan"}, {"label": "India"}]},
            {"id": "exclude", "kind": "text", "prompt": "Anything to exclude?", "required": False},
        ],
    }
    payload.update(overrides)
    return AskUserArgs.model_validate(payload)


def answers(*items: dict[str, object]) -> ClarificationAnswers:
    return ClarificationAnswers.model_validate({"answers": list(items)})


def test_request_always_ends_choice_options_with_one_server_owned_other():
    request = build_request(args())
    division, regions, exclude, extra = request["questions"]
    assert [option["label"] for option in division["options"]] == ["BID", "LSG", OTHER_LABEL]
    assert division["options"][-1]["is_other"] is True
    assert [option["label"] for option in regions["options"]][-1] == OTHER_LABEL
    assert "options" not in exclude and exclude["required"] is False
    assert (extra["id"], extra["kind"], extra["required"], extra["is_extra"]) == (
        EXTRA_QUESTION_ID, "text", False, True,
    )
    assert extra["prompt"] == "Anything else I should know?"


def test_the_anything_else_box_is_reserved_and_only_reported_when_filled():
    with pytest.raises(ClarificationError, match="reserved"):
        build_request(args(questions=[{"id": EXTRA_QUESTION_ID, "kind": "text", "prompt": "Q"}]))
    request = build_request(
        args(questions=[{"id": "period", "kind": "text", "prompt": "Which period?"}])
    )
    filled = validate_answers(request, answers(
        {"question_id": "period", "text": "September"},
        {"question_id": EXTRA_QUESTION_ID, "text": " Missing Stock = Clean Partial Stock "},
    ))
    assert answers_text(request, filled).splitlines() == [
        "Answers to your questions:",
        "- Which period? September",
        "- Additional context: Missing Stock = Clean Partial Stock",
    ]
    empty = validate_answers(request, answers({"question_id": "period", "text": "September"}))
    assert answers_text(request, empty).splitlines() == [
        "Answers to your questions:",
        "- Which period? September",
    ]


@pytest.mark.parametrize(
    "questions, message",
    [
        ([{"id": "a", "kind": "text", "prompt": "A"}, {"id": "a", "kind": "text", "prompt": "B"}],
         "unique"),
        (
            [{"id": "a", "kind": "choice", "prompt": "A",
              "options": [{"label": "X"}, {"label": "Other"}]}],
            "concrete options",
        ),
        (
            [{"id": "a", "kind": "choice", "prompt": "A",
              "options": [{"label": "X"}, {"label": "x "}]}],
            "repeats",
        ),
        ([{"id": "a", "kind": "text", "prompt": "A", "options": [{"label": "X"}]}],
         "must not have options"),
    ],
)
def test_invalid_requests_explain_what_to_fix(questions, message):
    with pytest.raises(ClarificationError, match=message):
        build_request(args(questions=questions))


def test_schema_limits_questions_and_ids():
    with pytest.raises(ValidationError):
        args(questions=[{"id": f"q{i}", "kind": "text", "prompt": "Q"} for i in range(5)])
    with pytest.raises(ValidationError):
        args(questions=[{"id": "Bad id", "kind": "text", "prompt": "Q"}])


def test_valid_answers_are_normalized_in_question_order():
    request = build_request(args())
    result = validate_answers(request, answers(
        {"question_id": "regions", "selected": ["ANZ", OTHER_LABEL], "other_text": " Korea "},
        {"question_id": "division", "selected": ["BID"], "other_text": "ignored"},
    ))
    assert result == [
        {"question_id": "division", "selected": ["BID"], "other_text": None},
        {"question_id": "regions", "selected": ["ANZ", OTHER_LABEL], "other_text": "Korea"},
        {"question_id": "exclude", "text": None},
        {"question_id": EXTRA_QUESTION_ID, "text": None},
    ]
    assert answers_text(request, result).splitlines() == [
        "Answers to your questions:",
        "- Which division? BID",
        "- Which regions? ANZ; Other: Korea",
        "- Anything to exclude? (no answer)",
    ]


@pytest.mark.parametrize(
    "submitted, field, message",
    [
        ({"question_id": "division", "selected": ["BID", "LSG"]}, "division", "Choose one"),
        ({"question_id": "division", "selected": ["Nope"]}, "division", "listed options"),
        ({"question_id": "division", "selected": [OTHER_LABEL]}, "division", "Other"),
        ({"question_id": "ghost", "selected": ["X"]}, "ghost", "Unknown"),
    ],
)
def test_invalid_answers_report_each_field(submitted, field, message):
    request = build_request(args())
    with pytest.raises(AppError) as error:
        validate_answers(request, answers(
            submitted, {"question_id": "regions", "selected": ["ANZ"]},
        ))
    assert error.value.status_code == 422
    assert message in error.value.field_errors[field]


def test_required_questions_need_answers_but_optional_ones_do_not():
    request = build_request(args())
    with pytest.raises(AppError) as error:
        validate_answers(request, answers())
    assert set(error.value.field_errors) == {"division", "regions"}


def test_questions_markdown_lists_every_question_and_option():
    text = questions_markdown(build_request(args()))
    assert text.startswith("# A few questions before I continue")
    assert "1. **Which division?** (choose one: BID, LSG, Other)" in text
    assert "3. **Anything to exclude?** (free text)" in text
    assert "Anything else I should know?" not in text


def context(round_: int = 0) -> AgentToolContext:
    return AgentToolContext(
        job_id=uuid.uuid4(), organization_id=uuid.uuid4(), conversation_id=uuid.uuid4(),
        allowed_data_source_ids=frozenset(), settings=Settings(_env_file=None),
        clarification_round=round_,
    )


def no_answered_rounds(monkeypatch, answered: int = 0) -> None:
    """ask_user counts rounds answered earlier in its job; keep the tests off the database."""

    @asynccontextmanager
    async def session():
        yield object()

    monkeypatch.setattr(tools, "get_session_factory", lambda: session)
    monkeypatch.setattr(
        tools.AgentExecutionRepository, "count_tools", AsyncMock(return_value=answered)
    )


@pytest.mark.asyncio
async def test_ask_user_tool_returns_the_request_and_respects_the_round_limit(monkeypatch):
    monkeypatch.setattr(tools, "append_agent_event", AsyncMock())
    no_answered_rounds(monkeypatch)
    result = await tools.ask_user(context(), args().model_dump(), uuid.uuid4())
    assert result["ok"] is True and len(result["clarification"]["questions"]) == 4

    with pytest.raises(AgentToolError) as limited:
        await tools.ask_user(context(round_=2), args().model_dump(), uuid.uuid4())
    assert limited.value.code == "CLARIFICATION_LIMIT_REACHED"

    bad = args().model_dump()
    bad["questions"][0]["options"] = [{"label": "Only one"}]
    with pytest.raises(AgentToolError) as invalid:
        await tools.ask_user(context(), bad, uuid.uuid4())
    assert invalid.value.code == "CLARIFICATION_INVALID"


def test_prompt_and_tool_forbid_upload_requests_and_bundled_questions():
    from app.agent.deep_agent import SYSTEM_PROMPT

    description = tools.build_default_tool_registry().get("ask_user").description
    assert "Never ask the user to\n  attach, upload, or share files, screenshots" in SYSTEM_PROMPT
    assert "one decision per question" in SYSTEM_PROMPT.lower()
    assert "never ask for files, screenshots, or uploads" in description
    assert "Anything else I should know?" in description


def test_ask_user_is_registered_as_a_turn_ending_tool():
    definition = tools.build_default_tool_registry().get("ask_user")
    assert definition is not None and definition.ends_turn is True


@pytest.mark.asyncio
async def test_runtime_returns_questions_instead_of_failing_without_an_answer(monkeypatch):
    request = build_request(args())

    class AskingRunnable:
        async def ainvoke(self, input: dict[str, object], config: Any = None) -> dict:
            raise AgentTurnEnded("ask_user", {"ok": True, "clarification": request})

    class Factory:
        def create(self, **kwargs: Any) -> AskingRunnable:
            return AskingRunnable()

    async def run(job_id, awaitable, timeout_seconds):
        return await awaitable

    monkeypatch.setattr(runtime_module, "append_agent_event", AsyncMock())
    monkeypatch.setattr(runtime_module, "run_cancellable", run)
    monkeypatch.setattr(runtime_module, "build_model_audit_callback", lambda _: None)
    result = await DeepAgentRuntime(factory=Factory()).run(
        context=context(),
        model=ModelRuntimeConfiguration(
            profile_id=str(uuid.uuid4()), model_name="fake", base_url="http://x.invalid",
            api_key=None, settings={},
        ),
        history=[{"role": "user", "content": "Show overdue backlog"}],
    )
    assert result.clarification == request and result.notes == ""


@pytest.mark.asyncio
async def test_a_real_langgraph_tool_node_lets_the_stop_signal_end_the_run(monkeypatch):
    pytest.importorskip("langchain_openai")
    import langchain_openai
    from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
    from langchain_core.messages import AIMessage
    from langchain_core.outputs import ChatGeneration, ChatResult

    class AskingModel(FakeMessagesListChatModel):
        def bind_tools(self, tools: Any, **kwargs: Any) -> AskingModel:
            return self

        def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
            call = {"id": "c1", "name": "ask_user", "args": args().model_dump()}
            return ChatResult(generations=[ChatGeneration(
                message=AIMessage(content="", tool_calls=[call])
            )])

    monkeypatch.setattr(langchain_openai, "ChatOpenAI", lambda **kwargs: AskingModel(responses=[]))
    asked: list[dict] = []

    async def ask(**kwargs: object) -> str:
        asked.append(kwargs)
        raise AgentTurnEnded("ask_user", {"ok": True, "clarification": {"questions": []}})

    runnable = ProductionDeepAgentFactory().create(
        model=ModelRuntimeConfiguration(
            profile_id=str(uuid.uuid4()), model_name="fake", base_url="http://x.invalid",
            api_key=None, settings={},
        ),
        tools=[ToolBinding("ask_user", "Ask", AskUserArgs, ask)],
        system_prompt="Ask when unsure.",
        timeout_seconds=1,
    )
    with pytest.raises(AgentTurnEnded):
        await runnable.ainvoke({"messages": [{"role": "user", "content": "Show backlog"}]})
    assert len(asked) == 1
    # Nested arguments arrive as models; the executor validates and dumps them back to JSON.
    assert json.dumps(AskUserArgs.model_validate(asked[0]).model_dump(mode="json"))


class FakeRepo:
    def __init__(self, asked, original, *, answered_already=False):
        self.lock_for_org = AsyncMock(return_value=SimpleNamespace(id=asked.conversation_id))
        self.get_message = AsyncMock(return_value=asked)
        self.has_user_message_after = AsyncMock(return_value=answered_already)
        self.message_for_job = AsyncMock(return_value=original)


def clarification_messages(original_metadata: dict[str, object]):
    conversation_id, job_id = uuid.uuid4(), uuid.uuid4()
    asked = SimpleNamespace(
        id=uuid.uuid4(), conversation_id=conversation_id, role="assistant", job_id=job_id,
        metadata_json={
            "clarification": build_request(args()),
            "model_profile_id": str(uuid.uuid4()),
        },
    )
    original = SimpleNamespace(content="Show overdue backlog", metadata_json=original_metadata)
    return asked, original


@pytest.mark.asyncio
async def test_answers_continue_the_original_request_with_the_next_round():
    reference = {
        "reference_at": "2026-11-05T18:29:00+00:00", "timezone": "Asia/Kolkata",
        "timezone_source": "client",
    }
    asked, original = clarification_messages({
        "instruction_id": "inst-1", "command": "kpi", "time_context": reference,
    })
    service = ConversationService(AsyncMock(), Settings(_env_file=None))
    service.repo = FakeRepo(asked, original)
    service.submit_message = AsyncMock(return_value=("message", "job"))

    await service.answer_clarification(
        conversation_id=asked.conversation_id, message_id=asked.id,
        organization_id=uuid.uuid4(), user_id=uuid.uuid4(),
        payload=answers(
            {"question_id": "division", "selected": ["BID"]},
            {"question_id": "regions", "selected": ["Japan"]},
        ),
    )
    call = service.submit_message.await_args.kwargs
    extra = call["extra_metadata"]
    assert call["payload"].content.startswith("Answers to your questions:")
    assert extra["expanded_prompt"].startswith("Show overdue backlog\n\nAnswers to your questions:")
    assert extra["clarification_round"] == 1
    assert extra["time_context"] == reference
    assert extra["answers_message_id"] == str(asked.id)
    assert (extra["instruction_id"], extra["command"]) == ("inst-1", "kpi")
    assert str(call["payload"].model_profile_id) == asked.metadata_json["model_profile_id"]
    assert call["payload"].reasoning_effort is None


@pytest.mark.asyncio
async def test_answers_keep_the_reasoning_effort_of_the_original_question():
    asked, original = clarification_messages({"reasoning_effort": "high"})
    service = ConversationService(AsyncMock(), Settings(_env_file=None))
    service.repo = FakeRepo(asked, original)
    service.submit_message = AsyncMock(return_value=("message", "job"))

    await service.answer_clarification(
        conversation_id=asked.conversation_id, message_id=asked.id,
        organization_id=uuid.uuid4(), user_id=uuid.uuid4(),
        payload=answers(
            {"question_id": "division", "selected": ["BID"]},
            {"question_id": "regions", "selected": ["Japan"]},
        ),
    )
    assert service.submit_message.await_args.kwargs["payload"].reasoning_effort == "high"


@pytest.mark.asyncio
async def test_answered_or_stale_questions_cannot_be_answered_again():
    asked, original = clarification_messages({"clarification_round": 1})
    service = ConversationService(AsyncMock(), Settings(_env_file=None))
    service.repo = FakeRepo(asked, original, answered_already=True)
    service.submit_message = AsyncMock()
    with pytest.raises(AppError) as error:
        await service.answer_clarification(
            conversation_id=asked.conversation_id, message_id=asked.id,
            organization_id=uuid.uuid4(), user_id=uuid.uuid4(),
            payload=answers({"question_id": "division", "selected": ["BID"]}),
        )
    assert (error.value.code, error.value.status_code) == ("CLARIFICATION_CLOSED", 409)
    service.submit_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_ordinary_answers_and_unknown_messages_are_not_clarifications():
    asked, original = clarification_messages({})
    asked.metadata_json = {"follow_up_suggestions": []}
    service = ConversationService(AsyncMock(), Settings(_env_file=None))
    service.repo = FakeRepo(asked, original)
    with pytest.raises(AppError) as error:
        await service.answer_clarification(
            conversation_id=asked.conversation_id, message_id=asked.id,
            organization_id=uuid.uuid4(), user_id=uuid.uuid4(), payload=answers(),
        )
    assert (error.value.code, error.value.status_code) == ("CLARIFICATION_NOT_FOUND", 404)
