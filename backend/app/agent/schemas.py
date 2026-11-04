from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.agent.table_rows import TableRowsInfo


class ToolExecutionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_id: uuid.UUID
    sequence: int
    tool_name: str
    status: str
    input_summary: dict[str, object]
    output_summary: dict[str, object] | None
    error_code: str | None
    error_message: str | None
    started_at: datetime
    finished_at: datetime | None


class SQLExecutionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tool_execution_id: uuid.UUID
    data_source_id: uuid.UUID
    sql_text: str
    status: str
    row_count: int | None
    truncated: bool
    columns: list[str] | None
    result_bytes: int | None
    duration_ms: int | None
    error_code: str | None
    error_message: str | None
    started_at: datetime
    finished_at: datetime | None


class ModelExecutionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_id: uuid.UUID
    sequence: int
    model_profile_id: uuid.UUID
    model_name: str
    reasoning_effort: str | None = None
    phase: str
    status: str
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    cached_input_tokens: int | None = None
    input_price_per_million: float | None = None
    cached_input_price_per_million: float | None = None
    output_price_per_million: float | None = None
    cost: float | None = None
    error_code: str | None
    error_message: str | None
    provider_error_response: dict[str, object] | None = None
    started_at: datetime
    finished_at: datetime | None


class DaxExecutionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    tool_execution_id: uuid.UUID
    data_source_id: uuid.UUID
    semantic_model_id: str
    dax_text: str
    status: str
    columns: list[str] | None
    row_count: int | None
    truncated: bool
    result_bytes: int | None
    duration_ms: int | None
    error_code: str | None
    error_message: str | None
    context: dict[str, object]
    started_at: datetime
    finished_at: datetime | None


class JobArtifactResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_id: uuid.UUID
    kind: str
    name: str | None
    source_sql_execution_id: uuid.UUID | None
    source_dax_execution_id: uuid.UUID | None = None
    payload: dict[str, object]
    created_at: datetime
    # Tables only: the trace carries the first rows; the rest are paged from the rows endpoint.
    table_rows: TableRowsInfo | None = None


class JobExecutionTraceResponse(BaseModel):
    tools: list[ToolExecutionResponse] = Field(default_factory=list)
    sql: list[SQLExecutionResponse] = Field(default_factory=list)
    dax: list[DaxExecutionResponse] = Field(default_factory=list)
    models: list[ModelExecutionResponse] = Field(default_factory=list)
    artifacts: list[JobArtifactResponse] = Field(default_factory=list)
