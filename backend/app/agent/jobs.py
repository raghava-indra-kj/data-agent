from __future__ import annotations

import json
import uuid

from app.agent.artifact_directives import replace_artifact_directives
from app.agent.checkpoints import current_checkpointer, thread_id
from app.agent.clarification import questions_markdown
from app.agent.deep_agent import (
    AnalysisRunResult,
    DeepAgentDependencyError,
    DeepAgentRuntime,
    model_failure_details,
)
from app.agent.evidence import (
    EvidenceBundle,
    build_evidence_correction,
    collect_evidence,
    validate_evidence,
)
from app.agent.final_answer import FinalAnswerError, FinalAnswerRuntime
from app.agent.final_answer_validation import answer_title
from app.agent.models import JobArtifact
from app.agent.repository import AgentExecutionRepository
from app.agent.tools import (
    AgentCancelledError,
    AgentLimitError,
    AgentToolContext,
    is_cancel_requested,
)
from app.conversations.models import Message
from app.conversations.repository import ConversationRepository
from app.conversations.table_scope import SourceTableScope
from app.conversations.titles import adopt_answer_title
from app.core.config import get_settings
from app.core.database import get_session_factory
from app.core.errors import AppError
from app.core.time import utc_now
from app.instructions.repository import InstructionRepository
from app.jobs.handlers import JobHandlerRegistry
from app.jobs.repository import JobRepository
from app.jobs.worker import JobFailureError, JobWaitingForInput
from app.models.reasoning import REASONING_EFFORTS
from app.models.service import ModelConfigurationService


async def _model_history(
    messages: list[Message], execution_repo: AgentExecutionRepository
) -> list[object]:
    history: list[object] = []
    for item in messages:
        content = item.content
        if item.role == "assistant" and item.job_id is not None and "[[artifact:" in content:
            artifacts = await execution_repo.list_artifacts(item.job_id)
            labels = {
                str(artifact.id): f"{artifact.kind.title()} shown: {artifact.name or 'Output'}"
                for artifact in artifacts
                if artifact.kind != "text"
            }
            content = replace_artifact_directives(content, labels, prefix="")
        elif item.role == "user" and item.metadata_json and "expanded_prompt" in item.metadata_json:
            content = str(item.metadata_json["expanded_prompt"])
        history.append({"role": item.role, "content": content})
    return history


async def _save_clarification(
    *,
    job_id: uuid.UUID,
    conversation_id: uuid.UUID,
    profile_id: uuid.UUID,
    request: dict[str, object],
    pause: dict[str, object] | None = None,
) -> dict[str, object]:
    """Show the agent's questions. A paused job then waits; otherwise the turn ends."""
    async with get_session_factory()() as session:
        repo = ConversationRepository(session)
        metadata: dict[str, object] = {
            "runtime": "deepagents",
            "clarification": request,
            "model_profile_id": str(profile_id),
            "resumable": pause is not None,
        }
        message = Message(
            conversation_id=conversation_id,
            role="assistant",
            content=questions_markdown(request),
            job_id=job_id,
            metadata_json=metadata,
            created_at=utc_now(),
        )
        repo.add_message(message)
        await session.commit()
    if pause is not None:
        raise JobWaitingForInput({
            **pause,
            "question_message_id": str(message.id),
            "asked_at": message.created_at.isoformat(),
        })
    return {
        "conversation_id": str(conversation_id),
        "assistant_message_id": str(message.id),
        "clarification_requested": True,
        "question_count": len(request.get("questions", [])),
    }


async def _load_evidence(
    *,
    job_id: uuid.UUID,
    question: str,
    analysis: AnalysisRunResult,
) -> EvidenceBundle:
    async with get_session_factory()() as session:
        return await collect_evidence(
            session,
            job_id=job_id,
            question=question,
            analyst_notes=analysis.notes,
        )


async def run_chat_query_job(job_id: uuid.UUID) -> dict[str, object]:
    settings = get_settings()
    async with get_session_factory()() as session:
        job = await JobRepository(session).get(job_id)
        if job is None:
            raise JobFailureError("JOB_NOT_FOUND", "The analytical job no longer exists.")
        if job.job_type != "chat_query":
            raise JobFailureError("JOB_TYPE_INVALID", "The analytical job type is invalid.")
        raw_conversation_id = job.input.get("conversation_id")
        raw_profile_id = job.input.get("model_profile_id")
        try:
            conversation_id = uuid.UUID(str(raw_conversation_id))
            profile_id = uuid.UUID(str(raw_profile_id))
            user_message_id = uuid.UUID(str(job.input.get("user_message_id")))
        except (TypeError, ValueError, AttributeError) as exc:
            raise JobFailureError(
                "JOB_INPUT_INVALID", "The analytical job input is invalid."
            ) from exc
        reasoning_effort = job.input.get("reasoning_effort")
        if reasoning_effort is not None and reasoning_effort not in REASONING_EFFORTS:
            raise JobFailureError("JOB_INPUT_INVALID", "The analytical job input is invalid.")

        convo_repo = ConversationRepository(session)
        conversation = await convo_repo.get_for_org(conversation_id, job.organization_id)
        if conversation is None:
            raise JobFailureError("CONVERSATION_NOT_FOUND", "Conversation not found.")
        source_ids = await convo_repo.source_ids(conversation.id)
        power_bi_source_ids: set[uuid.UUID] = set()
        if settings.power_bi_enabled or getattr(conversation, "private_to_creator", False):
            from sqlalchemy import select
            from app.data_sources.models import DataSource
            from app.power_bi.service import PowerBIService
            session.info["actor_user_id"] = job.requested_by
            if conversation.private_to_creator and conversation.created_by != job.requested_by:
                raise JobFailureError("CONVERSATION_NOT_FOUND", "Conversation not found.")
            if conversation.private_to_creator:
                try:
                    await PowerBIService(session, settings, job.organization_id, job.requested_by).require_identity(job.input.get("power_bi_identity"))
                except AppError as exc:
                    raise JobFailureError(exc.code, exc.message) from exc
            power_bi_source_ids = set(await session.scalars(select(DataSource.id).where(
                DataSource.id.in_(source_ids), DataSource.kind == "powerbi",
                DataSource.organization_id == job.organization_id,
            )))
            for source_id in power_bi_source_ids:
                try:
                    await PowerBIService(session, settings, job.organization_id, job.requested_by).metadata(source_id)
                except AppError as exc:
                    raise JobFailureError(exc.code, exc.message) from exc
        requested_by = getattr(job, "requested_by", None)
        power_bi_context = job.input.get("power_bi_context")
        power_bi_identity = job.input.get("power_bi_identity")
        table_scope = tuple(
            SourceTableScope.model_validate(item) for item in job.input["table_scope"]
        )
        if not source_ids:
            raise JobFailureError(
                "CONVERSATION_DATASOURCE_REQUIRED", "The conversation has no datasource."
            )
        messages = await convo_repo.recent_messages(
            conversation.id, settings.agent_max_history_messages,
            through_job=job, user_message_id=user_message_id,
        )
        messages = [
            item for item in messages
            if not (item.role == "assistant" and item.job_id == job_id)
        ]
        user_message = next(
            (item for item in messages if item.id == user_message_id and item.role == "user"), None
        )
        if user_message is not None:
            messages = messages[:messages.index(user_message) + 1]
        question = (
            str(user_message.metadata_json.get("expanded_prompt") or user_message.content)
            if user_message
            else ""
        ).strip()
        pause = job.input.get("pause")
        resume = job.input.get("resume")
        resuming = isinstance(pause, dict) and isinstance(resume, dict)
        if resuming:
            question = str(resume.get("expanded_prompt") or question).strip()
        if not question:
            raise JobFailureError("JOB_INPUT_INVALID", "The analytical question is unavailable.")

        instruction_repo = InstructionRepository(session)
        default_inst = await instruction_repo.get_default(job.organization_id)
        default_instructions = default_inst.content if default_inst else None

        command_instructions = None
        command_name = None
        clarification_round = 0
        if user_message and user_message.metadata_json:
            raw_round = user_message.metadata_json.get("clarification_round", 0)
            clarification_round = raw_round if isinstance(raw_round, int) else 0
            cmd_instruction_id = user_message.metadata_json.get("instruction_id")
            if cmd_instruction_id:
                try:
                    cmd_inst = await instruction_repo.get(
                        uuid.UUID(str(cmd_instruction_id)), job.organization_id
                    )
                    if cmd_inst and cmd_inst.enabled:
                        command_instructions = cmd_inst.content
                        command_name = cmd_inst.command
                except (ValueError, TypeError):
                    pass

        history = await _model_history(messages, AgentExecutionRepository(session))
        model_service = ModelConfigurationService(session, settings)
        try:
            runtime_model = await model_service.get_runtime_configuration(
                profile_id=profile_id,
                organization_id=job.organization_id,
                reasoning_effort=reasoning_effort,
            )
        except AppError as exc:
            raise JobFailureError(
                exc.code,
                "The selected analysis model profile is unavailable or disabled.",
            ) from exc
        organization_id = job.organization_id
    checkpointer = current_checkpointer()

    context = AgentToolContext(
        job_id=job_id,
        organization_id=organization_id,
        conversation_id=conversation_id,
        allowed_data_source_ids=frozenset(source_ids),
        settings=settings,
        table_scope=table_scope,
        default_instructions=default_instructions,
        command_instructions=command_instructions,
        command_name=command_name,
        clarification_round=clarification_round,
        pausable=checkpointer is not None,
        requested_by=requested_by,
        power_bi_source_ids=frozenset(power_bi_source_ids),
        power_bi_context=power_bi_context,
        power_bi_identity=power_bi_identity,
    )
    run = int(pause.get("run", 1)) if resuming else 1
    try:
        if resuming and checkpointer is None:
            raise JobFailureError(
                "AGENT_RESUME_UNAVAILABLE",
                "The paused analysis cannot resume because its saved state is unavailable.",
            )
        analysis_runtime = DeepAgentRuntime()
        analysis = await analysis_runtime.run(
            context=context,
            model=runtime_model,
            history=[] if resuming else history,
            checkpointer=checkpointer,
            thread=thread_id(job_id, run),
            resume=(
                {"answers": resume.get("answers"), "text": resume.get("text")}
                if resuming
                else None
            ),
        )
        if analysis.clarification is not None:
            return await _save_clarification(
                job_id=job_id,
                conversation_id=conversation_id,
                profile_id=profile_id,
                request=analysis.clarification,
                pause={"run": run} if analysis.paused else None,
            )
        evidence = await _load_evidence(job_id=job_id, question=question, analysis=analysis)
        evidence_issues = validate_evidence(evidence)

        retries = 0
        while evidence_issues and retries < settings.analysis_evidence_retries:
            retries += 1
            run += 1
            correction = build_evidence_correction(evidence_issues)
            analysis = await analysis_runtime.run(
                context=context,
                model=runtime_model,
                history=[*analysis.messages, {"role": "user", "content": correction}],
                checkpointer=checkpointer,
                thread=thread_id(job_id, run),
            )
            if analysis.clarification is not None:
                return await _save_clarification(
                    job_id=job_id,
                    conversation_id=conversation_id,
                    profile_id=profile_id,
                    request=analysis.clarification,
                    pause={"run": run} if analysis.paused else None,
                )
            evidence = await _load_evidence(job_id=job_id, question=question, analysis=analysis)
            evidence_issues = validate_evidence(evidence)

        if evidence_issues:
            artifact_issue = any(issue.startswith("Artifact ") for issue in evidence_issues)
            raise JobFailureError(
                "ARTIFACT_REFERENCE_INVALID"
                if artifact_issue
                else "ANALYSIS_EVIDENCE_INSUFFICIENT",
                (
                    "The generated outputs could not be validated safely."
                    if artifact_issue
                    else "The analysis did not produce sufficient verified evidence."
                ),
            )

        if await is_cancel_requested(job_id):
            raise AgentCancelledError
        follow_up_suggestions: list[str] = []
        answer = await FinalAnswerRuntime(settings=settings).run(
            job_id=job_id,
            model=runtime_model,
            evidence=evidence,
            default_instructions=default_instructions,
            command_instructions=command_instructions,
            command_name=command_name,
            follow_up_suggestions=follow_up_suggestions,
            follow_up_context=json.dumps({
                "data_source_ids": [str(source_id) for source_id in source_ids],
                "table_scope": [item.model_dump(mode="json", by_alias=True) for item in table_scope],
                "recent_questions": [item.content for item in messages if item.role == "user"],
            }, ensure_ascii=False),
        )
        if await is_cancel_requested(job_id):
            raise AgentCancelledError
    except AgentCancelledError as exc:
        raise JobFailureError("JOB_CANCELLED", "The analytical job was cancelled.") from exc
    except AgentLimitError as exc:
        raise JobFailureError(exc.code, exc.public_message) from exc
    except FinalAnswerError as exc:
        raise JobFailureError(exc.code, exc.public_message) from exc
    except DeepAgentDependencyError as exc:
        raise JobFailureError(
            "AGENT_RUNTIME_UNAVAILABLE",
            "The Deep Agents runtime is unavailable on this server.",
        ) from exc
    except (JobFailureError, JobWaitingForInput):
        raise
    except Exception as exc:
        code, message = model_failure_details(exc)
        if code == "MODEL_PARAMETER_UNSUPPORTED":
            raise JobFailureError(code, message) from exc
        # Never leak provider/LangGraph internals to API-visible job errors.
        raise JobFailureError(
            "AGENT_EXECUTION_FAILED",
            "The analytical agent failed to complete the request.",
        ) from exc

    async with get_session_factory()() as session:
        repo = ConversationRepository(session)
        existing = await repo.answer_message_for_job(job_id)
        title = answer_title(answer)
        metadata: dict[str, object] = {
            "runtime": "deepagents+finalizer",
            "title": title,
            "follow_up_suggestions": follow_up_suggestions,
            "model_profile_id": str(profile_id),
        }
        conversation = await repo.get_for_org(conversation_id, organization_id)
        if conversation is not None:
            first_question = await repo.first_user_message(conversation_id)
            adopt_answer_title(
                conversation, first_question.content if first_question else None, title
            )
        if existing is None:
            message = Message(
                conversation_id=conversation_id,
                role="assistant",
                content=answer,
                job_id=job_id,
                metadata_json=metadata,
                created_at=utc_now(),
            )
            repo.add_message(message)
        else:
            message = existing
            message.content = answer
            message.metadata_json = metadata

        execution_repo = AgentExecutionRepository(session)
        text_artifact = await execution_repo.answer_artifact_for_job(job_id)
        if text_artifact is None:
            text_artifact = JobArtifact(
                job_id=job_id,
                kind="text",
                name="Answer",
                source_sql_execution_id=None,
                payload={"schema_version": 1, "markdown": answer},
                created_at=utc_now(),
            )
            execution_repo.add_artifact(text_artifact)
        else:
            text_artifact.payload = {"schema_version": 1, "markdown": answer}
        await session.commit()
        tools = await execution_repo.list_tools(job_id)
        sql = await execution_repo.list_sql(job_id)
        artifacts = await execution_repo.list_artifacts(job_id)

    return {
        "conversation_id": str(conversation_id),
        "assistant_message_id": str(message.id),
        "tool_execution_count": len(tools),
        "sql_execution_count": len(sql),
        "artifact_ids": [str(item.id) for item in artifacts],
    }


def register_agent_handlers(registry: JobHandlerRegistry) -> None:
    if registry.get("chat_query") is None:
        registry.register("chat_query", run_chat_query_job)
