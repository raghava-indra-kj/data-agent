import os
from pathlib import Path

from data_agent_mcp.application.use_cases.test_connection import TestConnection
from data_agent_mcp.domain.data_sources.models import DatabaseEngine
from data_agent_mcp.infrastructure.configuration.file_data_sources import FileDataSourceRepository
from data_agent_mcp.infrastructure.credentials.environment import EnvironmentCredentialResolver
from data_agent_mcp.infrastructure.databases.mssql.connection_tester import MssqlConnectionTester


def sources_path(path: Path | None = None) -> Path:
    if path is not None:
        return path.resolve()
    return Path(os.environ.get("DATA_AGENT_SOURCES_FILE", "sources.json")).resolve()


def build_test_connection(path: Path | None = None) -> TestConnection:
    # Construct dependencies without reading secrets or opening database connections.
    return TestConnection(
        sources=FileDataSourceRepository(sources_path(path)),
        credentials=EnvironmentCredentialResolver(),
        testers={DatabaseEngine.MSSQL: MssqlConnectionTester()},
    )


def build_product(
    path: Path | None = None, settings_file: Path | None = None, state_file: Path | None = None
):
    from dotenv import load_dotenv

    from data_agent_mcp.application.use_cases.catalog import (
        CatalogService,
        QueryService,
        SourceService,
    )
    from data_agent_mcp.application.use_cases.knowledge import KnowledgeService
    from data_agent_mcp.application.use_cases.refresh import (
        JobCoordinator,
        RefreshService,
        ScheduleService,
    )
    from data_agent_mcp.application.use_cases.runtime import PluginServices
    from data_agent_mcp.infrastructure.configuration.settings import load_settings
    from data_agent_mcp.infrastructure.databases.mssql.reader import MssqlDatabaseReader
    from data_agent_mcp.infrastructure.embeddings.cloud import CloudEmbeddingProvider
    from data_agent_mcp.infrastructure.storage.runtime_lease import FileRuntimeLease
    from data_agent_mcp.infrastructure.storage.sqlite_store import SqliteProductStore

    owner_root = path.resolve().parent if path else sources_path().parent
    load_dotenv(
        Path(os.environ.get("DATA_AGENT_ENV_FILE", str(owner_root / ".env"))), override=False
    )
    root = sources_path(path).parent

    def owner_path(value):
        value = Path(value)
        return value if value.is_absolute() else root / value

    settings = load_settings(
        settings_file or owner_path(os.environ.get("DATA_AGENT_SETTINGS_FILE", "settings.json"))
    )
    store = SqliteProductStore(
        state_file or owner_path(os.environ.get("DATA_AGENT_STATE_FILE", "state/metadata.sqlite3")),
        settings,
    )
    repository = FileDataSourceRepository(sources_path(path))
    credentials = EnvironmentCredentialResolver()
    sources = SourceService(
        repository,
        credentials,
        {DatabaseEngine.MSSQL: MssqlDatabaseReader(settings=settings)},
        settings,
    )
    catalog = CatalogService(sources, store, settings)
    knowledge = KnowledgeService(sources, store, CloudEmbeddingProvider(settings), settings)
    jobs = JobCoordinator(store, settings)
    refresh = RefreshService(catalog, knowledge, jobs, store, settings)
    schedules = ScheduleService(store, refresh, settings)
    return PluginServices(
        settings,
        sources,
        catalog,
        knowledge,
        QueryService(sources, settings),
        jobs,
        refresh,
        schedules,
        FileRuntimeLease(store.path.with_suffix(store.path.suffix + ".runtime.lock")),
    )
