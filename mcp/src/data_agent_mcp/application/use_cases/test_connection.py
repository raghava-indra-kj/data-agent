from collections.abc import Mapping
from dataclasses import replace
from time import perf_counter
from uuid import UUID

from data_agent_mcp.application.ports.credentials import (
    CredentialResolutionError,
    CredentialResolver,
)
from data_agent_mcp.application.ports.data_sources import ConfigurationError, DataSourceRepository
from data_agent_mcp.application.ports.database import (
    ConnectionDiagnostics,
    ConnectionStage,
    ConnectionTester,
    ConnectionTestResult,
)
from data_agent_mcp.domain.data_sources.models import (
    DatabaseEngine,
    DataSource,
    UsernamePasswordAuthentication,
)


class TestConnection:
    __test__ = False

    def __init__(
        self,
        sources: DataSourceRepository,
        credentials: CredentialResolver,
        testers: Mapping[DatabaseEngine, ConnectionTester],
    ):
        self._sources = sources
        self._credentials = credentials
        self._testers = dict(testers)

    def execute(self, data_source_id: str) -> ConnectionTestResult:
        started = perf_counter()
        source: DataSource | None = None

        def failure(code: str, stage: ConnectionStage, category: str, message: str):
            return ConnectionTestResult(
                success=False,
                data_source_id=str(data_source_id)[:100],
                duration_ms=round((perf_counter() - started) * 1000, 2),
                source_name=source.name if source else None,
                engine=source.engine.value if source else None,
                authentication_method=source.authentication.method.value if source else None,
                configured_server=source.connection.server if source else None,
                configured_database=source.connection.database if source else None,
                diagnostics=ConnectionDiagnostics(code, stage, category, message),
            )

        try:
            identifier = UUID(data_source_id)
        except (ValueError, TypeError, AttributeError):
            return failure(
                "INVALID_SOURCE_ID",
                ConnectionStage.CONFIGURATION,
                "configuration",
                "Source ID must be a UUID from your sources file.",
            )
        try:
            source = self._sources.get(identifier)
        except ConfigurationError as exc:
            return failure(
                "INVALID_CONFIGURATION", ConnectionStage.CONFIGURATION, "configuration", str(exc)
            )
        if source is None:
            return failure(
                "SOURCE_NOT_FOUND",
                ConnectionStage.CONFIGURATION,
                "configuration",
                "No source with this ID is configured.",
            )
        if not source.enabled:
            return failure(
                "SOURCE_DISABLED",
                ConnectionStage.CONFIGURATION,
                "configuration",
                "This source is disabled. Enable it in your local configuration.",
            )
        tester = self._testers.get(source.engine)
        if tester is None:
            return failure(
                "UNSUPPORTED_ENGINE",
                ConnectionStage.CONFIGURATION,
                "configuration",
                f"No adapter is installed for {source.engine.value}. This release implements MSSQL only.",
            )
        password = None
        if isinstance(source.authentication, UsernamePasswordAuthentication):
            try:
                password = self._credentials.resolve(source.authentication.password_reference)
            except CredentialResolutionError as exc:
                return failure(
                    "CREDENTIAL_UNAVAILABLE", ConnectionStage.CREDENTIALS, "credentials", str(exc)
                )
            except Exception:
                return failure(
                    "CREDENTIAL_RESOLUTION_FAILED",
                    ConnectionStage.CREDENTIALS,
                    "internal",
                    "The credential provider failed. Raw exception details were withheld.",
                )
        # The adapter owns driver error handling; unexpected implementation errors
        # must not expose driver inputs or secrets through the MCP transport.
        try:
            result = tester.test(source, password)
        except Exception:
            return failure(
                "INTERNAL_TEST_ERROR",
                ConnectionStage.CONNECT,
                "internal",
                "An unexpected connection adapter error occurred. No raw exception was exposed.",
            )
        return replace(result, duration_ms=round((perf_counter() - started) * 1000, 2))
