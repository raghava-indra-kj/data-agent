from __future__ import annotations

import re
import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.checkpoints import delete_job_checkpoints
from app.agent.clarification import ClarificationAnswers, answers_text, validate_answers
from app.conversations.models import Conversation, ConversationDataSource, Message
from app.conversations.titles import default_conversation_title
from app.conversations.repository import ConversationRepository
from app.conversations.schemas import (
    AnswerReviewCounts,
    ConversationCreate,
    ConversationPage,
    ConversationRename,
    ConversationResponse,
    ConversationTableScopeUpdate,
    MessageCreate,
    MessagePage,
    MessageResponse,
    MessageVerificationUpdate,
)
from app.conversations.table_scope import SourceTableScope, resolve_table_scope
from app.core.config import Settings
from app.core.errors import AppError
from app.core.pagination import CursorCodec, split_page
from app.core.time import utc_now
from app.data_sources.service import DataSourceService
from app.instructions.repository import InstructionRepository
from app.jobs.repository import JobRepository
from app.jobs.service import JobService
from app.jobs.state import WAITING_STATUS
from app.models.models import ModelProfile
from app.models.reasoning import reasoning_support
from app.models.service import ModelConfigurationService


class ConversationService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.repo = ConversationRepository(session)

    async def verify_message(self, conversation_id, message_id, organization_id, user, role, payload: MessageVerificationUpdate) -> Message:
        if role not in {"owner", "admin"}:
            raise AppError("FORBIDDEN", "Only workspace owners and admins can verify answers.", 403)
        await self.require_for_org(conversation_id, organization_id)
        item = await self.session.get(Message, message_id)
        if item is None or item.conversation_id != conversation_id:
            raise AppError("MESSAGE_NOT_FOUND", "Message not found.", 404)
        if item.role != "assistant":
            raise AppError("INVALID_VERIFICATION_TARGET", "Only assistant answers can be verified.", 422)
        item.verification_status = payload.verification_status
        item.verification_percentage = payload.verification_percentage
        item.verification_summary = payload.verification_summary
        item.verified_by = user.id if payload.verification_status else None
        item.verified_by_name = user.display_name if payload.verification_status else None
        item.verified_at = utc_now() if payload.verification_status else None
        await self.session.commit()
        await self.session.refresh(item)
        return item

    async def create(
        self,
        *,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        payload: ConversationCreate,
    ) -> Conversation:
        source_service = DataSourceService(self.session, self.settings)
        power_bi_private = False
        power_bi_identity = None
        for source_id in payload.data_source_ids:
            source = await source_service.require_for_org(source_id, organization_id)
            if source.kind == "powerbi":
                from app.power_bi.service import PowerBIService
                power_bi = PowerBIService(self.session, self.settings, organization_id, user_id)
                await power_bi.metadata(source_id)
                power_bi_identity = await power_bi.current_identity()
                power_bi_private = True
            if source.status != "active":
                raise AppError(
                    "DATASOURCE_NOT_ACTIVE",
                    "All conversation datasources must be active.",
                    409,
                )

        if payload.model_profile_id is not None:
            profile = await ModelConfigurationService(self.session, self.settings).require_profile(
                payload.model_profile_id, organization_id
            )
            if not profile.enabled:
                raise AppError("MODEL_PROFILE_DISABLED", "Model profile is disabled.", 409)

        table_scope = await resolve_table_scope(
            self.session, organization_id, payload.data_source_ids, payload.table_scope
        )
        conversation = Conversation(
            organization_id=organization_id,
            title=payload.title,
            private_to_creator=power_bi_private,
            power_bi_identity=power_bi_identity,
            table_scope=table_scope,
            created_by=user_id,
            model_profile_id=payload.model_profile_id,
        )
        self.repo.add_conversation(conversation)
        await self.session.flush()
        for source_id in payload.data_source_ids:
            self.repo.add_source(
                ConversationDataSource(
                    conversation_id=conversation.id,
                    data_source_id=source_id,
                )
            )
        await self.session.commit()
        return conversation

    async def require_for_org(
        self, conversation_id: uuid.UUID, organization_id: uuid.UUID
    ) -> Conversation:
        item = await self.repo.get_for_org(conversation_id, organization_id)
        if item is None:
            raise AppError("CONVERSATION_NOT_FOUND", "Conversation not found.", 404)
        return item

    async def to_response(self, item: Conversation) -> ConversationResponse:
        return (await self.to_responses([item]))[0]

    async def to_responses(self, items: list[Conversation]) -> list[ConversationResponse]:
        ids = [item.id for item in items]
        sources = await self.repo.source_ids_for(ids)
        counts = await self.repo.answer_review_counts(ids)
        return [
            ConversationResponse.model_validate(item).model_copy(update={
                "data_source_ids": sources.get(item.id, []),
                "answer_review_counts": counts.get(item.id, AnswerReviewCounts()),
            })
            for item in items
        ]

    async def list_page(
        self, organization_id: uuid.UUID, *, search: str, cursor: str | None, limit: int
    ) -> ConversationPage:
        search = search.strip()
        codec = CursorCodec(self.settings, "conversations", organization_id, search.casefold())
        after = codec.decode(cursor, [datetime.fromisoformat, uuid.UUID]) if cursor else None
        rows, has_more = split_page(await self.repo.list_page_for_org(
            organization_id, search=search, after=after, limit=limit
        ), limit)
        return ConversationPage(
            items=await self.to_responses(rows),
            next_cursor=codec.encode([rows[-1].updated_at, rows[-1].id]) if has_more else None,
            has_more=has_more,
        )

    async def message_page(
        self,
        conversation_id: uuid.UUID,
        organization_id: uuid.UUID,
        *,
        cursor: str | None,
        limit: int,
    ) -> MessagePage:
        await self.require_for_org(conversation_id, organization_id)
        codec = CursorCodec(self.settings, "messages", organization_id, conversation_id)
        before = codec.decode(cursor, [datetime.fromisoformat, uuid.UUID]) if cursor else None
        rows, has_more = split_page(
            await self.repo.list_message_page(conversation_id, before=before, limit=limit), limit
        )
        return MessagePage(
            items=[MessageResponse.model_validate(row) for row in reversed(rows)],
            next_cursor=codec.encode([rows[-1].created_at, rows[-1].id]) if has_more else None,
            has_more=has_more,
        )

    async def answer_clarification(
        self,
        *,
        conversation_id: uuid.UUID,
        message_id: uuid.UUID,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        payload: ClarificationAnswers,
    ) -> tuple[Message, uuid.UUID]:
        """Answer the agent's questions; the answers continue the original request."""
        # The lock serializes concurrent submissions so a question card is answered once.
        conversation = await self.repo.lock_for_org(conversation_id, organization_id)
        if conversation is None:
            raise AppError("CONVERSATION_NOT_FOUND", "Conversation not found.", 404)
        asked = await self.repo.get_message(message_id, conversation_id)
        request = (asked.metadata_json or {}).get("clarification") if asked else None
        if asked is None or asked.role != "assistant" or not isinstance(request, dict):
            raise AppError("CLARIFICATION_NOT_FOUND", "These questions were not found.", 404)
        if await self.repo.has_user_message_after(conversation_id, asked):
            raise AppError(
                "CLARIFICATION_CLOSED",
                "These questions were already answered or the conversation has moved on.",
                409,
            )
        answers = validate_answers(request, payload)
        content = answers_text(request, answers)
        if (asked.metadata_json or {}).get("resumable"):
            return await self._resume_paused_job(asked, organization_id, answers, content)
        original = await self.repo.message_for_job(asked.job_id, "user") if asked.job_id else None
        original_metadata = original.metadata_json if original else {}
        original_request = str(
            original_metadata.get("expanded_prompt") or (original.content if original else "")
        ).strip()
        extra: dict[str, object] = {
            "clarification_answers": answers,
            "answers_message_id": str(asked.id),
            "clarification_round": int(original_metadata.get("clarification_round") or 0) + 1,
            "expanded_prompt": f"{original_request}\n\n{content}".strip(),
        }
        for key in ("instruction_id", "command", "raw_prompt"):
            if key in original_metadata:
                extra[key] = original_metadata[key]
        profile = (asked.metadata_json or {}).get("model_profile_id")
        report_context = None
        if getattr(conversation, "private_to_creator", False):
            original_job = (
                await JobRepository(self.session).get_for_organization(
                    asked.job_id, organization_id
                )
                if asked.job_id else None
            )
            if original_job is None:
                raise AppError(
                    "CLARIFICATION_NOT_FOUND", "The original question was not found.", 404
                )
            # A clarification continues the captured view even if the canvas has since closed.
            report_context = (original_job.input_data or {}).get("power_bi_context")
        return await self.submit_message(
            conversation_id=conversation_id,
            organization_id=organization_id,
            user_id=user_id,
            payload=MessageCreate(
                content=content,
                model_profile_id=uuid.UUID(str(profile)) if profile else None,
                reasoning_effort=original_metadata.get("reasoning_effort"),
                power_bi_context=report_context,
            ),
            extra_metadata=extra,
        )

    async def _resume_paused_job(
        self,
        asked: Message,
        organization_id: uuid.UUID,
        answers: list[dict[str, object]],
        content: str,
    ) -> tuple[Message, uuid.UUID]:
        """Record the answers on the paused job and queue it to continue where it stopped."""
        jobs = JobService(self.session, self.settings)
        job = (
            await JobRepository(self.session).lock_for_organization(asked.job_id, organization_id)
            if asked.job_id
            else None
        )
        pause = job.input.get("pause") if job is not None else None
        if (
            job is None
            or job.status != WAITING_STATUS
            or not isinstance(pause, dict)
            or pause.get("question_message_id") != str(asked.id)
        ):
            raise AppError(
                "CLARIFICATION_CLOSED", "These questions are no longer waiting for answers.", 409
            )
        if jobs.pause_expired(job):
            await jobs.expire_waiting(job)
            await delete_job_checkpoints(self.session, [job.id])
            raise AppError(
                "CLARIFICATION_EXPIRED",
                "These questions expired. Ask your question again to start a new analysis.",
                409,
            )
        original = await self.repo.message_for_job(job.id, "user")
        original_metadata = original.metadata_json if original else {}
        original_request = str(
            original_metadata.get("expanded_prompt") or (original.content if original else "")
        ).strip()
        message = Message(
            conversation_id=asked.conversation_id,
            role="user",
            content=content,
            job_id=job.id,
            metadata_json={"clarification_answers": answers, "answers_message_id": str(asked.id)},
            created_at=utc_now(),
        )
        self.repo.add_message(message)
        await self.session.flush()
        await jobs.resume_with_answers(job, {
            "answers": answers,
            "text": content,
            "answer_message_id": str(message.id),
            "expanded_prompt": f"{original_request}\n\n{content}".strip(),
        })
        return message, job.id

    async def _ensure_no_pending_questions(self, conversation_id: uuid.UUID) -> None:
        """A paused analysis waits for its answers; new questions would queue behind it."""
        repo = JobRepository(self.session)
        waiting = await repo.waiting_chat_for_conversation(conversation_id)
        if waiting is None:
            return
        jobs = JobService(self.session, self.settings)
        if not jobs.pause_expired(waiting):
            raise AppError(
                "CLARIFICATION_PENDING",
                "Answer or cancel the questions above before asking something new.",
                409,
            )
        locked = await repo.lock(waiting.id)
        if locked is not None and jobs.pause_expired(locked):
            await jobs.expire_waiting(locked)
            await delete_job_checkpoints(self.session, [locked.id])

    async def delete(self, conversation_id: uuid.UUID, organization_id: uuid.UUID) -> None:
        item = await self.require_for_org(conversation_id, organization_id)
        await self.session.delete(item)
        await self.session.commit()

    async def delete_all(self, organization_id: uuid.UUID) -> int:
        count = await self.repo.delete_all_for_org(organization_id)
        await self.session.commit()
        return count

    async def rename(
        self,
        conversation_id: uuid.UUID,
        organization_id: uuid.UUID,
        payload: ConversationRename,
    ) -> Conversation:
        item = await self.require_for_org(conversation_id, organization_id)
        item.title = payload.title
        item.updated_at = utc_now()
        await self.session.commit()
        return item

    async def update_table_scope(
        self,
        conversation_id: uuid.UUID,
        organization_id: uuid.UUID,
        payload: ConversationTableScopeUpdate,
    ) -> Conversation:
        """Running and paused jobs keep their own scope; the change applies to new questions."""
        item = await self.repo.lock_for_org(conversation_id, organization_id)
        if item is None:
            raise AppError("CONVERSATION_NOT_FOUND", "Conversation not found.", 404)
        item.table_scope = await resolve_table_scope(
            self.session, organization_id, await self.repo.source_ids(item.id), payload.table_scope
        )
        item.updated_at = utc_now()
        await self.session.commit()
        return item

    async def resolve_model_profile(
        self,
        *,
        conversation: Conversation,
        organization_id: uuid.UUID,
        override_profile_id: uuid.UUID | None,
    ) -> ModelProfile:
        model_service = ModelConfigurationService(self.session, self.settings)
        requested = override_profile_id or conversation.model_profile_id
        if requested is not None:
            profile = await model_service.require_profile(requested, organization_id)
            if not profile.enabled:
                raise AppError("MODEL_PROFILE_DISABLED", "Model profile is disabled.", 409)
            return profile
        default = await model_service.get_default(organization_id)
        if default is None or not default.enabled:
            raise AppError(
                "MODEL_PROFILE_REQUIRED",
                "Configure an enabled default model before asking a question.",
                409,
            )
        return default

    async def submit_message(
        self,
        *,
        conversation_id: uuid.UUID,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        payload: MessageCreate,
        extra_metadata: dict[str, object] | None = None,
    ) -> tuple[Message, uuid.UUID]:
        conversation = await self.require_for_org(conversation_id, organization_id)
        await self._ensure_no_pending_questions(conversation.id)
        if getattr(conversation, "private_to_creator", False):
            from app.power_bi.service import PowerBIService
            await PowerBIService(self.session, self.settings, organization_id, user_id).require_identity(conversation.power_bi_identity)
        source_ids = await self.repo.source_ids(conversation.id)
        if payload.power_bi_context is not None:
            from app.power_bi.context import validate_context
            from app.power_bi.service import PowerBIService
            service = PowerBIService(self.session, self.settings, organization_id, user_id)
            report = await service.report(payload.power_bi_context.report_binding_id)
            if report.data_source_id not in source_ids:
                raise AppError("POWER_BI_CONTEXT_INVALID", "Select this report's source for the conversation first.", 422)
            validate_context(payload.power_bi_context)
            token, _, _ = await service.token()
            await service.validate_report(report, token)
        if not source_ids:
            raise AppError(
                "CONVERSATION_DATASOURCE_REQUIRED",
                "The conversation has no datasource.",
                409,
            )
        profile = await self.resolve_model_profile(
            conversation=conversation,
            organization_id=organization_id,
            override_profile_id=payload.model_profile_id,
        )
        profile_id = profile.id
        effort = payload.reasoning_effort
        support = reasoning_support(profile.model_name)
        if effort is not None and (support is None or effort not in support.efforts):
            raise AppError(
                "REASONING_EFFORT_UNSUPPORTED",
                f"{profile.display_name} does not support {effort} reasoning effort.",
                422,
            )
        table_scope = await resolve_table_scope(
            self.session, organization_id, source_ids,
            [SourceTableScope.model_validate(item) for item in (conversation.table_scope or [])],
        )

        # User message and job are both durable. The job contains only identifiers/content and
        # never credentials. JobService performs the queue publish after PostgreSQL commit.
        metadata: dict[str, object] = {"model_profile_id": str(profile_id)}
        if effort is not None:
            metadata["reasoning_effort"] = effort
        content = payload.content.strip()
        match = re.match(r"^/([a-zA-Z0-9_-]+)(?:\s+(.*))?$", content, re.DOTALL)
        if match:
            cmd = match.group(1).lower()
            extra_prompt = (match.group(2) or "").strip()
            instruction = await InstructionRepository(self.session).get_by_command(
                organization_id, cmd
            )
            if instruction and instruction.enabled:
                metadata["instruction_id"] = str(instruction.id)
                metadata["command"] = instruction.command
                metadata["raw_prompt"] = payload.content
                if instruction.prompt_template:
                    if "{prompt}" in instruction.prompt_template:
                        expanded = instruction.prompt_template.replace(
                            "{prompt}", extra_prompt
                        ).strip()
                    else:
                        expanded = (
                            f"{instruction.prompt_template}\n\n{extra_prompt}".strip()
                            if extra_prompt
                            else instruction.prompt_template.strip()
                        )
                else:
                    expanded = extra_prompt if extra_prompt else (
                        instruction.description or payload.content
                    )
                metadata["expanded_prompt"] = expanded

        metadata.update(extra_metadata or {})
        message = Message(
            conversation_id=conversation.id,
            role="user",
            content=payload.content,
            metadata_json=metadata,
            created_at=utc_now(),
        )
        self.repo.add_message(message)
        if conversation.title is None:
            conversation.title = default_conversation_title(payload.content)
        await self.session.flush()

        job = await JobService(self.session, self.settings).create_job(
            organization_id=organization_id,
            requested_by=user_id,
            job_type="chat_query",
            input_data={
                "conversation_id": str(conversation.id),
                "user_message_id": str(message.id),
                "model_profile_id": str(profile_id),
                "reasoning_effort": effort,
                "table_scope": table_scope,
                **({"power_bi_private": True} if getattr(conversation, "private_to_creator", False) else {}),
                **({"power_bi_identity": conversation.power_bi_identity} if getattr(conversation, "private_to_creator", False) else {}),
                **({"power_bi_context": payload.power_bi_context.model_dump(mode="json")} if payload.power_bi_context else {}),
            },
            conversation_id=conversation.id,
            # LLM/query mistakes are corrected inside the bounded agent loop; only the generic
            # worker retry path should handle true infrastructure failures.
            max_attempts=self.settings.job_max_attempts,
        )
        message.job_id = job.id
        await self.session.commit()
        return message, job.id
