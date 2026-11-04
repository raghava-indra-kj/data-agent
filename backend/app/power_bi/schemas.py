from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PowerBIFeatures(BaseModel):
    enabled: bool
    configured: bool
    embedding_enabled: bool


class ConnectionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    display_name: str
    tenant_id: str
    status: str


class ConnectionStart(BaseModel):
    authorization_url: str


class ReportLookup(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=1, max_length=2000)


class ReportCandidate(BaseModel):
    report_id: str
    workspace_id: str | None = None
    semantic_model_id: str
    name: str
    web_url: str


class PowerBICreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=180)
    report_url: str = Field(min_length=1, max_length=2000)
    embedding_enabled: bool = True


class ReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    data_source_id: uuid.UUID
    report_id: str
    name: str
    web_url: str
    embedding_enabled: bool


class EmbedConfiguration(BaseModel):
    report_id: str
    embed_url: str
    access_token: str = Field(repr=False)
    expires_at: datetime
    token_type: Literal["Aad"] = "Aad"


class ReportContext(BaseModel):
    model_config = ConfigDict(extra="forbid")
    report_binding_id: uuid.UUID
    page_name: str = Field(max_length=255)
    page_display_name: str = Field(max_length=255)
    captured_at: datetime
    mode: Literal["report_view", "model"] = "report_view"
    filters: list[dict[str, object]] = Field(default_factory=list, max_length=100)
    unsupported: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("filters")
    @classmethod
    def bounded_filters(cls, value: list[dict[str, object]]) -> list[dict[str, object]]:
        import json

        if len(json.dumps(value)) > 64_000:
            raise ValueError("Report filter context is too large")
        return value
