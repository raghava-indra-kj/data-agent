from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from app.agent import final_answer as final_answer_module
from app.agent.deep_agent import _build_chat_model, model_failure_details
from app.agent.final_answer import FinalAnswerError, FinalAnswerRuntime
from app.conversations import service as service_module
from app.conversations.schemas import MessageCreate
from app.conversations.service import ConversationService
from app.core.config import Settings
from app.core.errors import AppError
from app.models.client import ModelCompletion, ModelRuntimeConfiguration, ModelUsage
from app.models.errors import ModelProviderError
from app.models.reasoning import reasoning_support, request_settings
from app.models.schemas import ModelProfileCreate, ModelProfileResponse


def runtime(model_name: str, effort: str | None, settings: dict[str, object] | None = None):
    return ModelRuntimeConfiguration(
        profile_id=str(uuid.uuid4()), model_name=model_name, base_url="https://api.openai.com/v1",
        api_key="test-key", settings=settings or {}, reasoning_effort=effort,
    )


@pytest.mark.parametrize(
    ("model_name", "efforts", "default"),
    [
        ("gpt-5", ("minimal", "low", "medium", "high"), "medium"),
        ("gpt-5-mini-2025-08-07", ("minimal", "low", "medium", "high"), "medium"),
        ("gpt-5.1", ("none", "low", "medium", "high"), "none"),
        ("gpt-5.4-mini", ("none", "low", "medium", "high", "xhigh"), "none"),
        ("gpt-5.6-terra", ("none", "low", "medium", "high", "xhigh", "max"), "medium"),
        ("gpt-6.1-sol", ("low", "medium", "high", "xhigh", "max"), "medium"),
        ("gpt-6-astra", ("low", "medium", "high", "xhigh", "max"), None),
        ("openai/o3-mini", ("low", "medium", "high"), "medium"),
    ],
)
def test_catalog_lists_each_reasoning_family(model_name, efforts, default) -> None:
    support = reasoning_support(model_name)
    assert support is not None
    assert (support.efforts, support.default) == (efforts, default)


@pytest.mark.parametrize(
    "model_name", ["gpt-4o", "gpt-4.1-mini", "gpt-5-chat-latest", "gpt-5-pro", "gpt-5.3-codex", "mistral-large-4-0"],
)
def test_models_without_a_known_effort_list_get_no_control(model_name) -> None:
    assert reasoning_support(model_name) is None


def test_request_settings_add_the_effort_and_drop_sampling_while_reasoning() -> None:
    profile = {"temperature": 0.2, "top_p": 0.9, "max_tokens": 4000}
    assert request_settings("gpt-5.5", profile, "high") == {"max_tokens": 4000, "reasoning_effort": "high"}
    # The model default (medium) reasons too.
    assert request_settings("gpt-5.5", profile, None) == {"max_tokens": 4000}
    # Effort none, or a default of none, keeps sampling.
    assert request_settings("gpt-5.2", profile, "none") == {**profile, "reasoning_effort": "none"}
    assert request_settings("gpt-5.2", profile, None) == profile
    assert request_settings("gpt-4o", profile, None) == profile


def test_agent_model_sends_the_effort_without_temperature() -> None:
    model = _build_chat_model(runtime("gpt-5.5", "high", {"temperature": 0.2, "max_tokens": 900}), 30)
    assert model.reasoning_effort == "high"
    assert model.temperature is None
    assert model.max_tokens == 900

    plain = _build_chat_model(runtime("gpt-4o", None, {"temperature": 0.2}), 30)
    assert plain.reasoning_effort is None
    assert plain.temperature == 0.2


@pytest.mark.parametrize(
    ("status", "body"),
    [
        (400, {"error": {"param": "reasoning_effort", "message": "Unsupported value: 'none'"}}),
        (400, {"error": {"param": "reasoning.effort", "message": "not supported with this model"}}),
        (422, {"error": {"message": "Unrecognized request argument supplied: reasoning_effort"}}),
    ],
)
def test_rejected_effort_is_reported_as_an_unsupported_parameter(status, body) -> None:
    error = Exception("provider error")
    error.status_code = status
    error.body = body
    code, message = model_failure_details(error)
    assert code == "MODEL_PARAMETER_UNSUPPORTED"
    assert "reasoning effort" in message


def test_profiles_no_longer_store_an_effort_and_report_what_questions_may_choose() -> None:
    for key in ("reasoning_effort", "reasoning"):
        with pytest.raises(ValidationError, match="per question"):
            ModelProfileCreate(
                connection_id=uuid.uuid4(), display_name="GPT", model_name="gpt-5.5",
                settings={key: "high"},
            )
    now = datetime.now(timezone.utc)
    common = dict(
        id=uuid.uuid4(), organization_id=uuid.uuid4(), connection_id=uuid.uuid4(), display_name="GPT",
        settings={}, is_default=True, enabled=True, created_at=now, updated_at=now,
    )
    reasoning = ModelProfileResponse(**common, model_name="gpt-5.2").model_dump()
    assert reasoning["reasoning_efforts"] == ["none", "low", "medium", "high", "xhigh"]
    assert reasoning["default_reasoning_effort"] == "none"
    plain = ModelProfileResponse(**common, model_name="gpt-4o").model_dump()
    assert (plain["reasoning_efforts"], plain["default_reasoning_effort"]) == ([], None)


def test_message_effort_must_be_a_known_value() -> None:
    assert MessageCreate(content="Q", reasoning_effort="xhigh").reasoning_effort == "xhigh"
    with pytest.raises(ValidationError):
        MessageCreate(content="Q", reasoning_effort="extreme")


def conversation_service(model_name: str) -> ConversationService:
    service = ConversationService(AsyncMock(), Settings(_env_file=None))
    service.require_for_org = AsyncMock(return_value=SimpleNamespace(id=uuid.uuid4(), table_scope=[], title="T"))
    service._ensure_no_pending_questions = AsyncMock()
    service.repo = SimpleNamespace(source_ids=AsyncMock(return_value=[uuid.uuid4()]), add_message=lambda _m: None)
    service.resolve_model_profile = AsyncMock(
        return_value=SimpleNamespace(id=uuid.uuid4(), model_name=model_name, display_name="Analyst")
    )
    return service


@pytest.mark.asyncio
@pytest.mark.parametrize(("model_name", "effort"), [("gpt-5.2", "minimal"), ("gpt-4o", "low")])
async def test_questions_cannot_choose_an_effort_the_model_does_not_support(model_name, effort) -> None:
    service = conversation_service(model_name)
    with pytest.raises(AppError) as error:
        await service.submit_message(
            conversation_id=uuid.uuid4(), organization_id=uuid.uuid4(), user_id=uuid.uuid4(),
            payload=MessageCreate(content="Q", reasoning_effort=effort),
        )
    assert error.value.code == "REASONING_EFFORT_UNSUPPORTED"


@pytest.mark.asyncio
async def test_the_question_effort_is_saved_on_the_message_and_job(monkeypatch) -> None:
    service = conversation_service("gpt-5.5")
    created: dict[str, object] = {}

    class FakeJobService:
        def __init__(self, *_args) -> None:
            pass

        async def create_job(self, **kwargs):
            created.update(kwargs)
            return SimpleNamespace(id=uuid.uuid4())

    monkeypatch.setattr(service_module, "JobService", FakeJobService)
    monkeypatch.setattr(service_module, "resolve_table_scope", AsyncMock(return_value=[]))
    message, _job_id = await service.submit_message(
        conversation_id=uuid.uuid4(), organization_id=uuid.uuid4(), user_id=uuid.uuid4(),
        payload=MessageCreate(content="Q", reasoning_effort="high"),
    )
    assert message.metadata_json["reasoning_effort"] == "high"
    assert created["input_data"]["reasoning_effort"] == "high"


class RecordingClient:
    def __init__(self, error: ModelProviderError | None = None) -> None:
        self.error = error
        self.settings: dict[str, object] | None = None

    async def chat_completion(self, *, model, messages, settings=None):
        del model, messages
        self.settings = settings
        if self.error:
            raise self.error
        return ModelCompletion("# Answer\n\nDone.", "gpt-5.5", ModelUsage(1, 1, 2))


def final_answer_runtime(client: RecordingClient, monkeypatch) -> FinalAnswerRuntime:
    async def run(_job, awaitable, **_kwargs):
        return await awaitable

    monkeypatch.setattr(final_answer_module, "run_cancellable", run)
    answers = FinalAnswerRuntime(settings=Settings(_env_file=None, final_answer_streaming_enabled=False))
    answers.client_factory = lambda *_: client
    answers._start_execution = AsyncMock(return_value=uuid.uuid4())
    answers._finish_execution = AsyncMock()
    return answers


@pytest.mark.asyncio
async def test_final_answer_uses_the_same_effort_and_drops_temperature(monkeypatch) -> None:
    client = RecordingClient()
    answers = final_answer_runtime(client, monkeypatch)
    await answers._complete(job_id=uuid.uuid4(), model=runtime("gpt-5.5", "low", {"temperature": 0.2}), messages=[])
    assert client.settings == {"reasoning_effort": "low"}


@pytest.mark.asyncio
async def test_final_answer_reports_a_rejected_effort_clearly(monkeypatch) -> None:
    client = RecordingClient(ModelProviderError(
        "MODEL_PROVIDER_REJECTED_REQUEST", "The model provider rejected the request.",
        diagnostics={"http_status": 400, "parameter": "reasoning_effort", "provider_message": "Unsupported value"},
    ))
    answers = final_answer_runtime(client, monkeypatch)
    with pytest.raises(FinalAnswerError) as error:
        await answers._complete(job_id=uuid.uuid4(), model=runtime("gpt-5.5", "max"), messages=[])
    assert error.value.code == "MODEL_PARAMETER_UNSUPPORTED"
    assert answers._finish_execution.call_args.kwargs["error_code"] == "MODEL_PARAMETER_UNSUPPORTED"
