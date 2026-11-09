from typing import Protocol
from uuid import UUID

from data_agent_mcp.domain.data_sources.models import DataSource


class ConfigurationError(Exception):
    """Safe, actionable configuration error; never embed raw configuration input."""


class DataSourceRepository(Protocol):
    def get(self, source_id: UUID) -> DataSource | None: ...

    def list_all(self) -> list[DataSource]: ...

    def save(self, source: DataSource, expected_revision: int | None = None) -> DataSource: ...
