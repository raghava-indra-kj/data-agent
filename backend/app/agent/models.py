from __future__ import annotations

import uuid
from datetime import datetime

from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ToolExecution(Base):
    __tablename__ = "tool_executions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('started','succeeded','failed','cancelled')",
            name="valid_status",
        ),
        UniqueConstraint("job_id", "sequence", name="uq_tool_executions_job_sequence"),
        Index("ix_tool_executions_job_started", "job_id", "started_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    tool_name: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    input_summary: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    output_summary: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SQLExecution(Base):
    __tablename__ = "sql_executions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('started','succeeded','failed','cancelled')",
            name="valid_status",
        ),
        UniqueConstraint("tool_execution_id", name="uq_sql_executions_tool"),
        Index("ix_sql_executions_datasource_started", "data_source_id", "started_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tool_execution_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tool_executions.id", ondelete="CASCADE"), nullable=False
    )
    data_source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("data_sources.id", ondelete="RESTRICT"), nullable=False
    )
    sql_text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    truncated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    columns: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    result_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ModelExecution(Base):
    __tablename__ = "model_executions"
    __table_args__ = (
        CheckConstraint("status IN ('started','succeeded','failed')", name="valid_status"),
        UniqueConstraint("job_id", "sequence", name="uq_model_executions_job_sequence"),
        Index("ix_model_executions_job_started", "job_id", "started_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    model_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("model_profiles.id", ondelete="RESTRICT"), nullable=False
    )
    model_name: Mapped[str] = mapped_column(String(255), nullable=False)
    # The effort the question chose; None means the model's default.
    reasoning_effort: Mapped[str | None] = mapped_column(String(20), nullable=True)
    phase: Mapped[str] = mapped_column(String(80), nullable=False, default="agent")
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cached_input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Prices copied from the profile when the call is recorded, so later price edits keep history.
    input_price_per_million: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    cached_input_price_per_million: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 6), nullable=True
    )
    output_price_per_million: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    cost: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider_error_response: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class JobArtifact(Base):
    __tablename__ = "job_artifacts"
    __table_args__ = (
        CheckConstraint("kind IN ('text','table','chart','html','matrix')", name="valid_kind"),
        Index("ix_job_artifacts_job_created", "job_id", "created_at"),
        Index("ix_job_artifacts_source_sql", "source_sql_execution_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str | None] = mapped_column(String(240), nullable=True)
    source_sql_execution_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sql_executions.id", ondelete="SET NULL"), nullable=True
    )
    source_dax_execution_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("dax_executions.id", ondelete="SET NULL"), nullable=True
    )
    payload: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
