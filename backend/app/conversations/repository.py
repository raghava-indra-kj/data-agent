from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import and_, delete, func, or_, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.conversations.models import Conversation, ConversationDataSource, Message
from app.conversations.schemas import AnswerReviewCounts
from app.core.pagination import keyset_page
from app.jobs.models import Job
from app.power_bi.access import conversation_visibility

UNTITLED_CONVERSATION = "Untitled analysis"


class ConversationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add_conversation(self, item: Conversation) -> None:
        self.session.add(item)

    def add_source(self, item: ConversationDataSource) -> None:
        self.session.add(item)

    def add_message(self, item: Message) -> None:
        self.session.add(item)

    async def delete_all_for_org(self, organization_id: uuid.UUID) -> int:
        result = await self.session.execute(
            delete(Conversation).where(Conversation.organization_id == organization_id, conversation_visibility(self.session))
        )
        return result.rowcount

    async def get_for_org(
        self, conversation_id: uuid.UUID, organization_id: uuid.UUID
    ) -> Conversation | None:
        result = await self.session.execute(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.organization_id == organization_id,
                conversation_visibility(self.session),
            )
        )
        return result.scalar_one_or_none()

    async def lock_for_org(
        self, conversation_id: uuid.UUID, organization_id: uuid.UUID
    ) -> Conversation | None:
        result = await self.session.execute(
            select(Conversation)
            .where(
                Conversation.id == conversation_id,
                Conversation.organization_id == organization_id,
                conversation_visibility(self.session),
            )
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def list_page_for_org(
        self,
        organization_id: uuid.UUID,
        *,
        search: str,
        after: Sequence[object] | None,
        limit: int,
    ) -> list[Conversation]:
        statement = select(Conversation).where(Conversation.organization_id == organization_id, conversation_visibility(self.session))
        if search:
            escaped = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            title = func.coalesce(
                func.nullif(func.trim(Conversation.title), ""), UNTITLED_CONVERSATION
            )
            statement = statement.where(title.ilike(f"%{escaped}%", escape="\\"))
        result = await self.session.execute(keyset_page(
            statement, [Conversation.updated_at, Conversation.id],
            after=after, descending=True, limit=limit,
        ))
        return list(result.scalars().all())

    async def source_ids(self, conversation_id: uuid.UUID) -> list[uuid.UUID]:
        return (await self.source_ids_for([conversation_id])).get(conversation_id, [])

    async def source_ids_for(
        self, conversation_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, list[uuid.UUID]]:
        if not conversation_ids:
            return {}
        result = await self.session.execute(
            select(ConversationDataSource.conversation_id, ConversationDataSource.data_source_id)
            .where(ConversationDataSource.conversation_id.in_(conversation_ids))
            .order_by(ConversationDataSource.conversation_id, ConversationDataSource.data_source_id)
        )
        sources: dict[uuid.UUID, list[uuid.UUID]] = {}
        for conversation_id, data_source_id in result.all():
            sources.setdefault(conversation_id, []).append(data_source_id)
        return sources

    async def answer_review_counts(
        self, conversation_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, AnswerReviewCounts]:
        if not conversation_ids:
            return {}
        result = await self.session.execute(
            select(
                Message.conversation_id,
                func.count().label("total"),
                func.count().filter(Message.verification_status == "CORRECT").label("correct"),
                func.count().filter(Message.verification_status == "PARTIALLY_CORRECT").label("partially_correct"),
                func.count().filter(Message.verification_status == "INCORRECT").label("incorrect"),
                func.count().filter(Message.verification_status.is_(None)).label("unreviewed"),
            )
            .where(Message.conversation_id.in_(conversation_ids), Message.role == "assistant")
            .group_by(Message.conversation_id)
        )
        return {
            row.conversation_id: AnswerReviewCounts(
                **{name: getattr(row, name) for name in AnswerReviewCounts.model_fields}
            )
            for row in result.all()
        }

    async def list_message_page(
        self, conversation_id: uuid.UUID, *, before: Sequence[object] | None, limit: int
    ) -> list[Message]:
        """Newest messages first, continuing toward older ones; callers restore chronology."""
        result = await self.session.execute(keyset_page(
            select(Message).where(Message.conversation_id == conversation_id),
            [Message.created_at, Message.id], after=before, descending=True, limit=limit,
        ))
        return list(result.scalars().all())

    async def recent_messages(
        self, conversation_id: uuid.UUID, limit: int, *,
        through_job: Job | None = None, user_message_id: uuid.UUID | None = None,
    ) -> list[Message]:
        statement = select(Message).where(Message.conversation_id == conversation_id)
        if through_job is not None:
            # A queued question may predate the previous answer. Order by turn, and
            # include earlier answers while excluding all subsequently queued questions.
            statement = statement.outerjoin(Job, Message.job_id == Job.id).where(or_(
                Message.id == user_message_id,
                Message.job_id == through_job.id,
                Job.created_at < through_job.created_at,
                and_(Job.created_at == through_job.created_at, Job.id < through_job.id),
            )).order_by(func.coalesce(Job.created_at, Message.created_at).desc(),
                       func.coalesce(Job.id, Message.id).desc(), Message.created_at.desc())
        else:
            statement = statement.order_by(Message.created_at.desc())
        result = await self.session.execute(statement.limit(limit))
        rows = list(result.scalars().all())
        rows.reverse()
        return rows

    async def first_user_message(self, conversation_id: uuid.UUID) -> Message | None:
        result = await self.session.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id, Message.role == "user")
            .order_by(Message.created_at.asc(), Message.id.asc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_message(
        self, message_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> Message | None:
        result = await self.session.execute(
            select(Message).where(
                Message.id == message_id, Message.conversation_id == conversation_id
            )
        )
        return result.scalar_one_or_none()

    async def has_user_message_after(self, conversation_id: uuid.UUID, message: Message) -> bool:
        result = await self.session.execute(
            select(Message.id)
            .where(
                Message.conversation_id == conversation_id,
                Message.role == "user",
                tuple_(Message.created_at, Message.id) > tuple_(message.created_at, message.id),
            )
            .limit(1)
        )
        return result.first() is not None

    async def message_for_job(self, job_id: uuid.UUID, role: str) -> Message | None:
        """The first message of a role for a job: its question, or its first reply."""
        result = await self.session.execute(
            select(Message)
            .where(Message.job_id == job_id, Message.role == role)
            .order_by(Message.created_at.asc(), Message.id.asc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def answer_message_for_job(self, job_id: uuid.UUID) -> Message | None:
        """The job's final answer; clarifying questions are separate assistant messages."""
        result = await self.session.execute(
            select(Message).where(
                Message.job_id == job_id,
                Message.role == "assistant",
                ~Message.metadata_json.has_key("clarification"),
            ).limit(1)
        )
        return result.scalar_one_or_none()
