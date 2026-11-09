from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from data_agent_mcp.application.ports.credentials import ResolvedSecret
from data_agent_mcp.domain.data_sources.models import DataSource


class ConnectionStage(StrEnum):
    CONFIGURATION = "loading configuration"
    CREDENTIALS = "resolving credentials"
    DRIVER = "checking database driver"
    CONNECT = "opening database connection"
    VERIFY = "verifying database connection"
    CLEANUP = "closing database connection"
    COMPLETE = "completed"


@dataclass(frozen=True, slots=True)
class ConnectionDiagnostics:
    code: str
    stage: ConnectionStage
    category: str
    message: str
    driver_message: str | None = None
    sqlstate: str | None = None
    error_number: int | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class ConnectionTestResult:
    success: bool
    data_source_id: str
    duration_ms: float
    source_name: str | None = None
    engine: str | None = None
    authentication_method: str | None = None
    configured_server: str | None = None
    configured_database: str | None = None
    actual_server: str | None = None
    actual_database: str | None = None
    diagnostics: ConnectionDiagnostics | None = None


class ConnectionTester(Protocol):
    def test(self, source: DataSource, password: ResolvedSecret | None) -> ConnectionTestResult: ...
