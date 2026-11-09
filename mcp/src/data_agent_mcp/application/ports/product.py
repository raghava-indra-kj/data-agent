"""Replaceable database, storage and cloud embedding boundaries."""

from typing import Any, Protocol

from data_agent_mcp.application.ports.credentials import ResolvedSecret
from data_agent_mcp.domain.data_sources.models import DataSource
from data_agent_mcp.domain.knowledge import KnowledgeDocument
from data_agent_mcp.domain.queries import TableRef


class DatabaseReader(Protocol):
    def list_tables(
        self,
        source: DataSource,
        password: ResolvedSecret | None,
        search: str,
        offset: int,
        limit: int,
    ) -> dict: ...
    def schema(
        self, source: DataSource, password: ResolvedSecret | None, table: TableRef
    ) -> dict: ...
    def sample(
        self,
        source: DataSource,
        password: ResolvedSecret | None,
        table: TableRef,
        columns: list[str],
        sample_rows: int,
    ) -> dict: ...
    def query(
        self,
        source: DataSource,
        password: ResolvedSecret | None,
        sql: str,
        parameters: list[Any],
        max_rows: int,
        max_bytes: int,
        timeout_seconds: int,
    ) -> dict: ...


class EmbeddingProvider(Protocol):
    @property
    def configured(self) -> bool: ...
    @property
    def model_key(self) -> str: ...
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class ProductStore(Protocol):
    def get_document(
        self, identifier: str, version: int | None = None
    ) -> KnowledgeDocument | None: ...
    def list_documents(
        self, filters: dict, offset: int, limit: int
    ) -> tuple[list[KnowledgeDocument], int]: ...
    def save_document(
        self,
        document: KnowledgeDocument,
        expected_version: int | None,
        embedding: list[float] | None = None,
        embedding_model: str | None = None,
    ) -> KnowledgeDocument: ...
    def generated_document(self, key: str) -> KnowledgeDocument | None: ...
    def search_documents(
        self, query: str, filters: dict, limit: int, vector: list[float] | None, model: str | None
    ) -> list[dict]: ...
    def put_profile(self, key: str, fingerprint: str, value: dict) -> None: ...
    def get_profile(self, key: str, fingerprint: str) -> dict | None: ...
    def create_job(self, kind: str, request: dict) -> str: ...
    def update_job(self, identifier: str, **changes: Any) -> None: ...
    def get_job(self, identifier: str) -> dict | None: ...
    def interrupt_unfinished_jobs(self) -> None: ...
    def list_schedules(self) -> list[dict]: ...
    def save_schedule(self, schedule: dict, expected_version: int | None) -> dict: ...


class RuntimeLease(Protocol):
    """One running MCP process may own a metadata store and its schedules."""

    def acquire(self) -> None: ...
    def release(self) -> None: ...
