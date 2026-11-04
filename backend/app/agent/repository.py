from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.models import JobArtifact, ModelExecution, SQLExecution, ToolExecution
from app.models.models import ModelProfile
from app.models.pricing import ModelPrice, model_call_cost


class AgentExecutionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add_tool(self, item: ToolExecution) -> None:
        self.session.add(item)

    def add_sql(self, item: SQLExecution) -> None:
        self.session.add(item)

    def add_model(self, item: ModelExecution) -> None:
        self.session.add(item)

    async def job_cost(self, job_id: uuid.UUID) -> Decimal | None:
        """Total priced cost of a job's model calls so far; None until a call has a cost."""
        return await self.session.scalar(
            select(func.sum(ModelExecution.cost)).where(ModelExecution.job_id == job_id)
        )

    async def price_model_execution(self, item: ModelExecution) -> None:
        """Copy the profile's current prices onto the call and record its cost."""
        profile = await self.session.get(ModelProfile, item.model_profile_id)
        price = ModelPrice(
            input_per_million=profile.input_price_per_million if profile else None,
            output_per_million=profile.output_price_per_million if profile else None,
            cached_input_per_million=profile.cached_input_price_per_million if profile else None,
        )
        item.input_price_per_million = price.input_per_million
        item.output_price_per_million = price.output_per_million
        item.cached_input_price_per_million = price.cached_input_per_million
        item.cost = model_call_cost(
            price,
            input_tokens=item.input_tokens,
            output_tokens=item.output_tokens,
            cached_input_tokens=item.cached_input_tokens,
        )

    def add_artifact(self, item: JobArtifact) -> None:
        self.session.add(item)

    async def next_tool_sequence(self, job_id: uuid.UUID) -> int:
        value = await self.session.scalar(
            select(func.coalesce(func.max(ToolExecution.sequence), 0)).where(
                ToolExecution.job_id == job_id
            )
        )
        return int(value or 0) + 1

    async def next_model_sequence(self, job_id: uuid.UUID) -> int:
        value = await self.session.scalar(
            select(func.coalesce(func.max(ModelExecution.sequence), 0)).where(
                ModelExecution.job_id == job_id
            )
        )
        return int(value or 0) + 1

    async def count_tools(
        self, job_id: uuid.UUID, *, tool_name: str | None = None, status: str | None = None
    ) -> int:
        statement = select(func.count(ToolExecution.id)).where(ToolExecution.job_id == job_id)
        if tool_name is not None:
            statement = statement.where(ToolExecution.tool_name == tool_name)
        if status is not None:
            statement = statement.where(ToolExecution.status == status)
        value = await self.session.scalar(statement)
        return int(value or 0)

    async def started_tool(self, job_id: uuid.UUID, tool_name: str) -> ToolExecution | None:
        """The unfinished call of a tool, such as questions awaiting the user's answers."""
        result = await self.session.execute(
            select(ToolExecution)
            .where(
                ToolExecution.job_id == job_id,
                ToolExecution.tool_name == tool_name,
                ToolExecution.status == "started",
            )
            .order_by(ToolExecution.sequence.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_sql_for_job(
        self, sql_execution_id: uuid.UUID, job_id: uuid.UUID
    ) -> SQLExecution | None:
        result = await self.session.execute(
            select(SQLExecution)
            .join(ToolExecution, ToolExecution.id == SQLExecution.tool_execution_id)
            .where(SQLExecution.id == sql_execution_id, ToolExecution.job_id == job_id)
        )
        return result.scalar_one_or_none()

    async def get_table_artifact_for_sql(
        self, job_id: uuid.UUID, sql_execution_id: uuid.UUID
    ) -> JobArtifact | None:
        result = await self.session.execute(
            select(JobArtifact)
            .where(
                JobArtifact.job_id == job_id,
                JobArtifact.kind == "table",
                JobArtifact.source_sql_execution_id == sql_execution_id,
            )
            .order_by(JobArtifact.created_at.asc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_tools(self, job_id: uuid.UUID) -> list[ToolExecution]:
        result = await self.session.execute(
            select(ToolExecution)
            .where(ToolExecution.job_id == job_id)
            .order_by(ToolExecution.sequence.asc())
        )
        return list(result.scalars().all())

    async def list_sql(self, job_id: uuid.UUID) -> list[SQLExecution]:
        result = await self.session.execute(
            select(SQLExecution)
            .join(ToolExecution, ToolExecution.id == SQLExecution.tool_execution_id)
            .where(ToolExecution.job_id == job_id)
            .order_by(ToolExecution.sequence.asc())
        )
        return list(result.scalars().all())

    async def list_model(self, job_id: uuid.UUID) -> list[ModelExecution]:
        result = await self.session.execute(
            select(ModelExecution)
            .where(ModelExecution.job_id == job_id)
            .order_by(ModelExecution.sequence.asc())
        )
        return list(result.scalars().all())

    async def list_dax(self, job_id: uuid.UUID):
        from app.power_bi.models import DaxExecution
        result = await self.session.scalars(select(DaxExecution).join(ToolExecution).where(
            ToolExecution.job_id == job_id).order_by(ToolExecution.sequence))
        return list(result)

    async def list_artifacts(self, job_id: uuid.UUID) -> list[JobArtifact]:
        result = await self.session.execute(
            select(JobArtifact)
            .where(JobArtifact.job_id == job_id)
            .order_by(JobArtifact.created_at.asc())
        )
        return list(result.scalars().all())

    async def get_artifact_for_job(
        self, job_id: uuid.UUID, artifact_id: uuid.UUID
    ) -> JobArtifact | None:
        result = await self.session.execute(
            select(JobArtifact).where(
                JobArtifact.job_id == job_id,
                JobArtifact.id == artifact_id,
            )
        )
        return result.scalar_one_or_none()

    async def artifact_kind_for_job(
        self, job_id: uuid.UUID, artifact_id: uuid.UUID
    ) -> str | None:
        result = await self.session.execute(
            select(JobArtifact.kind).where(
                JobArtifact.job_id == job_id,
                JobArtifact.id == artifact_id,
            )
        )
        return result.scalar_one_or_none()

    async def artifact_payload(self, artifact_id: uuid.UUID) -> dict[str, object] | None:
        result = await self.session.execute(
            select(JobArtifact.payload).where(JobArtifact.id == artifact_id)
        )
        return result.scalar_one_or_none()

    async def answer_artifact_for_job(self, job_id: uuid.UUID) -> JobArtifact | None:
        result = await self.session.execute(
            select(JobArtifact)
            .where(
                JobArtifact.job_id == job_id,
                JobArtifact.kind == "text",
                JobArtifact.name == "Answer",
            )
            .order_by(JobArtifact.created_at.asc())
            .limit(1)
        )
        return result.scalar_one_or_none()


def model_usage_event(item: ModelExecution, job_cost: Decimal | None) -> dict[str, object]:
    """Payload for the event published after each model call, used for the live job cost."""
    return {
        "input_tokens": item.input_tokens,
        "output_tokens": item.output_tokens,
        "cached_input_tokens": item.cached_input_tokens,
        "cost": None if item.cost is None else float(item.cost),
        "job_cost": None if job_cost is None else float(job_cost),
    }
