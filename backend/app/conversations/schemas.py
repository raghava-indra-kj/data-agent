from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.conversations.table_scope import SourceTableScope
from app.core.pagination import CursorPage
from app.core.time import validate_timezone
from app.models.reasoning import ReasoningEffort
from app.power_bi.schemas import ReportContext


class ConversationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=240)
    data_source_ids: list[uuid.UUID] = Field(min_length=1, max_length=10)
    table_scope: list[SourceTableScope] = Field(default_factory=list, max_length=10)
    model_profile_id: uuid.UUID | None = None

    @field_validator("title")
    @classmethod
    def clean_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @field_validator("data_source_ids")
    @classmethod
    def unique_sources(cls, value: list[uuid.UUID]) -> list[uuid.UUID]:
        if len(set(value)) != len(value):
            raise ValueError("data_source_ids must not contain duplicates")
        return value


class ConversationTableScopeUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    table_scope: list[SourceTableScope] = Field(max_length=10)


class ConversationRename(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=240)

    @field_validator("title")
    @classmethod
    def clean_title(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("title is required")
        return cleaned


class AnswerReviewCounts(BaseModel):
    total: int = Field(default=0, ge=0)
    correct: int = Field(default=0, ge=0)
    partially_correct: int = Field(default=0, ge=0)
    incorrect: int = Field(default=0, ge=0)
    unreviewed: int = Field(default=0, ge=0)


class ConversationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    title: str | None
    created_by: uuid.UUID
    model_profile_id: uuid.UUID | None
    data_source_ids: list[uuid.UUID] = Field(default_factory=list)
    table_scope: list[SourceTableScope] = Field(default_factory=list)
    answer_review_counts: AnswerReviewCounts = Field(default_factory=AnswerReviewCounts)
    created_at: datetime
    updated_at: datetime


class MessageCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1, max_length=50_000)
    model_profile_id: uuid.UUID | None = None
    # None uses the model's default effort.
    reasoning_effort: ReasoningEffort | None = None
    power_bi_context: ReportContext | None = None
    timezone: str | None = Field(
        default=None, min_length=1, max_length=100,
        description="User's IANA timezone, such as Asia/Kolkata. Omitted values use UTC.",
    )

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str | None) -> str | None:
        return validate_timezone(value) if value is not None else None

    @field_validator("content")
    @classmethod
    def clean_content(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Message content is required")
        return cleaned


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    conversation_id: uuid.UUID
    role: str
    content: str
    job_id: uuid.UUID | None
    verification_status: Literal["CORRECT", "PARTIALLY_CORRECT", "INCORRECT"] | None = None
    verification_percentage: int | None = None
    verification_summary: str | None = None
    verified_by: uuid.UUID | None = None
    verified_by_name: str | None = None
    verified_at: datetime | None = None
    metadata: dict[str, object] = Field(validation_alias="metadata_json")
    created_at: datetime


class MessageAcceptedResponse(BaseModel):
    message_id: uuid.UUID
    job_id: uuid.UUID


class ConversationPage(CursorPage[ConversationResponse]):
    """Conversations, most recently updated first."""


class MessagePage(CursorPage[MessageResponse]):
    """Chronological messages; next_cursor continues toward older messages."""


class MessageVerificationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    verification_status: Literal["CORRECT", "PARTIALLY_CORRECT", "INCORRECT"] | None
    verification_percentage: int | None = Field(default=None, strict=True, ge=1, le=99)
    verification_summary: str | None = Field(default=None, max_length=20000)

    @model_validator(mode="after")
    def validate_review(self):
        self.verification_summary = (self.verification_summary or "").strip() or None
        if self.verification_status is None:
            if self.verification_summary is not None or self.verification_percentage is not None:
                raise ValueError("Clear verification using a null status without summary or percentage.")
        else:
            if not self.verification_summary:
                raise ValueError("A verification summary is required.")
            if self.verification_status == "PARTIALLY_CORRECT":
                if self.verification_percentage is None:
                    raise ValueError("Partially correct reviews require a percentage from 1 to 99.")
            elif self.verification_percentage is not None:
                raise ValueError("Percentage applies only to partially correct reviews.")
        return self
