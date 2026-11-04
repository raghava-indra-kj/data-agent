from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.models import TimestampMixin


class MicrosoftConnection(TimestampMixin, Base):
    __tablename__ = "power_bi_connections"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "user_id", "tenant_id", name="uq_power_bi_connection_account"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    tenant_id: Mapped[str] = mapped_column(String(36))
    object_id: Mapped[str] = mapped_column(String(36))
    account_id: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(255))
    secret_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("encrypted_secrets.id", ondelete="RESTRICT")
    )
    status: Mapped[str] = mapped_column(String(30), default="connected")


class MicrosoftAuthTransaction(Base):
    __tablename__ = "power_bi_auth_transactions"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    state_hash: Mapped[str] = mapped_column(String(64), unique=True)
    browser_hash: Mapped[str] = mapped_column(String(64))
    secret_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("encrypted_secrets.id", ondelete="CASCADE")
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class PowerBISource(Base):
    __tablename__ = "power_bi_sources"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "tenant_id", "semantic_model_id", name="uq_power_bi_source_model"
        ),
    )
    data_source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("data_sources.id", ondelete="CASCADE"), primary_key=True
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    tenant_id: Mapped[str] = mapped_column(String(36))
    semantic_model_id: Mapped[str] = mapped_column(String(36))


class PowerBIReport(TimestampMixin, Base):
    __tablename__ = "power_bi_reports"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "tenant_id", "report_id", name="uq_power_bi_report_identity"
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    data_source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("data_sources.id", ondelete="CASCADE"), index=True
    )
    tenant_id: Mapped[str] = mapped_column(String(36))
    report_id: Mapped[str] = mapped_column(String(36))
    workspace_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    name: Mapped[str] = mapped_column(String(255))
    web_url: Mapped[str] = mapped_column(Text)
    embedding_enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class PowerBIMetadata(TimestampMixin, Base):
    __tablename__ = "power_bi_metadata"
    __table_args__ = (
        UniqueConstraint("data_source_id", "connection_id", name="uq_power_bi_metadata_identity"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    data_source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("data_sources.id", ondelete="CASCADE")
    )
    connection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("power_bi_connections.id", ondelete="CASCADE")
    )
    fingerprint: Mapped[str] = mapped_column(String(64))
    content: Mapped[dict[str, object]] = mapped_column(JSONB)


class DaxExecution(Base):
    __tablename__ = "dax_executions"
    __table_args__ = (Index("ix_dax_source_started", "data_source_id", "started_at"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tool_execution_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tool_executions.id", ondelete="CASCADE"), unique=True
    )
    data_source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("data_sources.id", ondelete="RESTRICT")
    )
    requested_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    semantic_model_id: Mapped[str] = mapped_column(String(36))
    dax_text: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20))
    columns: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    truncated: Mapped[bool] = mapped_column(Boolean, default=False)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    result_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    context: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
