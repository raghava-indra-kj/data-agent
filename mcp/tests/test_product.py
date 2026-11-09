import json
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import Mock

import httpx
import pytest
from fastmcp import Client
from pydantic import ValidationError

from data_agent_mcp.application.sql_policy import validate_select
from data_agent_mcp.application.use_cases.catalog import CatalogService, QueryService, SourceService
from data_agent_mcp.application.use_cases.knowledge import KnowledgeService
from data_agent_mcp.application.use_cases.refresh import (
    JobCoordinator,
    RefreshService,
    ScheduleService,
)
from data_agent_mcp.application.use_cases.runtime import PluginServices
from data_agent_mcp.bootstrap import build_product, build_test_connection
from data_agent_mcp.domain.data_sources.models import (
    AccessScope,
    ConnectionSettings,
    DatabaseEngine,
    DataSource,
    TableIdentifier,
    WindowsAuthentication,
)
from data_agent_mcp.domain.knowledge import KnowledgeScope, utc_now
from data_agent_mcp.domain.queries import OperationError, TableRef
from data_agent_mcp.domain.settings import RuntimeSettings
from data_agent_mcp.infrastructure.configuration.file_data_sources import FileDataSourceRepository
from data_agent_mcp.infrastructure.configuration.settings import load_settings
from data_agent_mcp.infrastructure.credentials.environment import EnvironmentCredentialResolver
from data_agent_mcp.infrastructure.databases.mssql.reader import MssqlDatabaseReader, json_value
from data_agent_mcp.infrastructure.embeddings.cloud import CloudEmbeddingProvider
from data_agent_mcp.infrastructure.storage.sqlite_store import SqliteProductStore
from data_agent_mcp.presentation.mcp.inputs import SourceConfiguration
from data_agent_mcp.presentation.mcp.server import create_server


def source(name="Offline source"):
    return DataSource(
        name=name,
        engine=DatabaseEngine.MSSQL,
        connection=ConnectionSettings("offline.invalid", "offline"),
        authentication=WindowsAuthentication(),
        access_scope=AccessScope(
            ("dbo",), (TableIdentifier("dbo", "orders"), TableIdentifier("dbo", "items"))
        ),
    )


class FakeReader:
    def __init__(self):
        self.schema_calls = 0
        self.sample_calls = 0

    def list_tables(self, source, password, search, offset, limit):
        return {
            "tables": [{"schema_name": "dbo", "table_name": "orders", "columns": ["amount"]}],
            "total": 1,
            "next_offset": None,
        }

    def schema(self, source, password, table):
        self.schema_calls += 1
        return {
            **asdict(table),
            "columns": [
                {"name": "amount", "type": "decimal", "max_length_bytes": 9},
                {"name": "status", "type": "varchar", "max_length_bytes": 20},
            ],
            "check_constraints": [],
            "observed_at": utc_now(),
        }

    def sample(self, source, password, table, columns, sample_rows):
        self.sample_calls += 1
        raw = {"amount": ["10.00", None, "25.10"], "status": ["open", "closed", "open"]}
        return {
            "rows": [[raw[c][i] for c in columns] for i in range(min(sample_rows, 3))],
            "sample_rows": min(sample_rows, 3),
            "truncated": False,
            "sampling_method": "bounded TOP sample",
            "observed_at": utc_now(),
        }

    def query(self, source, password, sql, parameters, max_rows, max_bytes, timeout_seconds):
        validate_select(sql, source, parameters, max_rows)
        return {"columns": [{"name": "total"}], "rows": [[35]], "row_count": 1, "truncated": False}


class FakeEmbeddings:
    configured = False
    model_key = "fake-cloud/model"

    def embed(self, texts):
        return [[1.0, 0.0] for _ in texts]


@pytest.fixture
def product(tmp_path):
    settings = RuntimeSettings()
    repository = FileDataSourceRepository(tmp_path / "sources.json")
    first = repository.save(source())
    second = repository.save(source("Second source"))
    reader = FakeReader()
    sources = SourceService(
        repository, EnvironmentCredentialResolver({}), {DatabaseEngine.MSSQL: reader}, settings
    )
    store = SqliteProductStore(tmp_path / "state.sqlite3", settings)
    catalog = CatalogService(sources, store, settings)
    knowledge = KnowledgeService(sources, store, FakeEmbeddings(), settings)
    jobs = JobCoordinator(store, settings)
    refresh = RefreshService(catalog, knowledge, jobs, store, settings)
    schedules = ScheduleService(store, refresh, settings)
    services = PluginServices(
        settings,
        sources,
        catalog,
        knowledge,
        QueryService(sources, settings),
        jobs,
        refresh,
        schedules,
    )
    yield services, first, second, store, reader, repository
    services.stop()


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM dbo.orders",
        "SELECT * INTO dbo.copy FROM dbo.orders",
        "SELECT * FROM dbo.orders; DROP TABLE dbo.orders",
        "EXEC xp_cmdshell 'whoami'",
        "SELECT * FROM otherdb.dbo.orders",
        "SELECT * FROM secret.orders",
        "SELECT * FROM orders",
        "SELECT * FROM dbo.secret",
        "SELECT * FROM OPENROWSET('provider','connection','query')",
        "SELECT dbo.external_function()",
        "SELECT NEXT VALUE FOR dbo.sequence",
        "SELECT * FROM dbo.orders WITH (UPDLOCK)",
        "SELECT TOP 10 PERCENT * FROM dbo.orders",
        "SELECT TOP 10 WITH TIES * FROM dbo.orders ORDER BY amount",
        "SELECT * FROM dbo.orders UNION SELECT * FROM secret.orders",
        "WITH x AS (SELECT * FROM secret.orders) SELECT * FROM x",
    ],
)
def test_unsafe_queries_rejected_before_driver(sql):
    with pytest.raises(OperationError):
        validate_select(sql, source(), [], 10)


def test_cte_joins_and_outer_budget():
    result = validate_select(
        "WITH x AS (SELECT amount FROM dbo.orders WHERE amount > ?) SELECT SUM(x.amount) FROM x JOIN dbo.items i ON 1=1",
        source(),
        [10],
        20,
    )
    assert "TOP 21" in result
    assert "?" in result
    assert "TOP 3" in validate_select("SELECT TOP 3 * FROM dbo.orders", source(), [], 20)
    with pytest.raises(OperationError, match="placeholders"):
        validate_select("SELECT * FROM dbo.orders WHERE amount=?", source(), [], 20)


def test_source_atomic_revisions_and_no_plaintext(product):
    services, first, _, _, _, repository = product
    assert len(services.sources.list()["sources"]) == 2
    changed = repository.save(replace(first, name="Changed"), expected_revision=1)
    assert changed.revision == 2
    with pytest.raises(OperationError, match="revision"):
        repository.save(first, expected_revision=1)
    with pytest.raises(ValidationError):
        SourceConfiguration.model_validate(
            {
                "name": "unsafe",
                "connection": {"server": "a", "database": "b"},
                "authentication": {
                    "method": "username_password",
                    "username": "u",
                    "password": "DO_NOT_STORE",
                },
                "access_scope": {"allowed_schemas": ["dbo"]},
            }
        )
    assert "DO_NOT_STORE" not in repository.path.read_text()


def test_two_table_schemas_and_profiles_cache_and_scope(product):
    services, first, _, _, reader, _ = product
    tables = [TableRef(str(first.id), "dbo", t) for t in ("orders", "items")]
    assert len(services.catalog.schemas(tables)["results"]) == 2
    assert reader.schema_calls == 2
    profiles = services.catalog.profiles(tables)
    assert reader.schema_calls == 2
    assert profiles["results"][0]["columns"][0]["observed_min"] == "10.00"
    assert profiles["results"][0]["columns"][0]["observed_max"] == "25.10"
    assert profiles["results"][0]["columns"][0]["sample_null_count"] == 1
    services.catalog.profiles(tables)
    assert reader.sample_calls == 2
    bad = services.catalog.schemas([TableRef(str(first.id), "dbo", "secret")])
    assert bad["results"][0]["code"] == "TABLE_NOT_ALLOWED"
    assert reader.schema_calls == 2


def test_profile_and_query_limits(product):
    services, first, *_ = product
    with pytest.raises(OperationError):
        services.catalog.profile(
            TableRef(str(first.id), "dbo", "orders"),
            sample_rows=services.settings.profile_max_sample_rows + 1,
        )
    result = services.queries.execute(
        [
            {"data_source_id": str(first.id), "sql": "SELECT SUM(amount) FROM dbo.orders"},
            {"data_source_id": str(first.id), "sql": "DROP TABLE dbo.orders"},
            {"data_source_id": str(first.id), "sql": "SELECT COUNT(*) FROM dbo.orders WHERE amount > ?", "parameters": [10]},
        ]
    )
    assert len(result["results"]) == 3
    assert result["results"][0]["success"]
    assert not result["results"][1]["success"]
    assert result["results"][1]["code"] == "READ_ONLY_REQUIRED"
    assert result["results"][2]["success"]


def save(services, scope=None, **kwargs):
    return services.knowledge.save(
        "Retention policy",
        "Business retention definition",
        "# Rule\nCustomers are active for 90 days.\n# Example\nAn example.",
        "business",
        scope or KnowledgeScope(),
        **kwargs,
    )["knowledge"]


def test_knowledge_versions_disable_sections_and_scopes(product):
    services, first, second, _, _, _ = product
    one = save(services, KnowledgeScope("table", str(first.id), "dbo", "orders"))
    two = save(services, KnowledgeScope("table", str(second.id), "dbo", "orders"))
    found = services.knowledge.search("retention", source_ids=[str(first.id)])
    assert [m["id"] for m in found["matches"]] == [one["id"]]
    section = services.knowledge.get([one["id"]], section="Rule")["results"][0]
    assert "Example" not in section["content"]
    assert (
        services.knowledge.set_enabled(
            [{"id": one["id"], "enabled": False, "expected_version": 1}]
        )["results"][0]["version"]
        == 2
    )
    assert not services.knowledge.search("retention", source_ids=[str(first.id)])["matches"]
    historical = services.knowledge.get([one["id"]], version=1)
    assert historical["results"][0]["code"] == "KNOWLEDGE_DISABLED"
    assert services.knowledge.get([one["id"]], include_disabled=True, version=1)["results"][0][
        "enabled"
    ]
    assert services.knowledge.get([two["id"]])["results"][0]["success"]
    with pytest.raises(OperationError):
        save(services, identifier=one["id"], expected_version=1)


def test_generated_refresh_preserves_disabled_and_authored_content(product):
    services, first, _, store, _, _ = product
    table = TableRef(str(first.id), "dbo", "orders")
    services.jobs.start()
    result = services.refresh.submit([table], ["schema", "data_profile"])
    services.jobs._pool.shutdown(wait=True)
    job = store.get_job(result["job_id"])
    assert job["status"] == "succeeded"
    generated = store.generated_document("schema:" + table.key)
    services.knowledge.set_enabled(
        [{"id": generated.id, "enabled": False, "expected_version": generated.version}]
    )
    generated = store.generated_document("schema:" + table.key)
    services.knowledge.generated(
        "schema:" + table.key,
        "Schema",
        "Description",
        {"columns": []},
        "schema",
        generated.scope,
        {},
    )
    assert not store.generated_document("schema:" + table.key).enabled
    edited = services.knowledge.save(
        "My description",
        "User edit",
        "Authored content",
        "schema",
        generated.scope,
        generated.id,
        generated.version + 1,
    )
    assert not edited["knowledge"]["generated"]
    assert store.generated_document("schema:" + table.key) is None
    assert store.get_document(generated.id).content == "Authored content"


def test_jobs_are_durable_and_restart_marks_interrupted(product):
    _, _, _, store, _, _ = product
    identifier = store.create_job("refresh", {"tables": []})
    store.interrupt_unfinished_jobs()
    assert store.get_job(identifier)["status"] == "interrupted"
    reloaded = SqliteProductStore(store.path)
    assert reloaded.get_job(identifier)["error"]["code"] == "PROCESS_RESTARTED"


def test_schedule_is_not_immediate_and_disable_works(product):
    services, first, _, store, reader, _ = product
    table = TableRef(str(first.id), "dbo", "orders")
    result = services.schedules.configure("Schema refresh", [table], ["schema"], 3600)
    assert reader.schema_calls == 0
    schedule = result["schedule"]
    assert datetime.fromisoformat(schedule["next_run_at"]) > datetime.now(UTC)
    disabled = services.schedules.configure(
        "Schema refresh", [table], ["schema"], 3600, False, schedule["id"], schedule["version"]
    )["schedule"]
    disabled["next_run_at"] = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
    store.save_schedule(disabled, disabled["version"])
    services.schedules.tick()
    assert reader.schema_calls == 0


def test_cloud_embedding_response_and_secret_safe_errors():
    settings = RuntimeSettings()

    def handler(request):
        assert request.url.path == "/v1/embeddings"
        assert json.loads(request.content)["model"] == "text-embedding-3-small"
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": [0.5, 1.0]}]})

    provider = CloudEmbeddingProvider(
        settings, {"DATA_AGENT_EMBEDDING_API_KEY": "PRIVATE_SECRET"}, httpx.MockTransport(handler)
    )
    assert provider.embed(["revenue"]) == [[0.5, 1.0]]
    failed = CloudEmbeddingProvider(
        settings,
        {"DATA_AGENT_EMBEDDING_API_KEY": "PRIVATE_SECRET"},
        httpx.MockTransport(lambda _: httpx.Response(401, text="PRIVATE_SECRET")),
    )
    with pytest.raises(OperationError) as error:
        failed.embed(["revenue"])
    assert "PRIVATE_SECRET" not in str(error.value)
    assert error.value.diagnostics["http_status"] == 401
    local = CloudEmbeddingProvider(
        settings,
        {
            "DATA_AGENT_EMBEDDING_API_KEY": "a",
            "DATA_AGENT_EMBEDDING_BASE_URL": "https://localhost/v1",
        },
    )
    with pytest.raises(OperationError, match="Local"):
        local.embed(["revenue"])


def test_settings_json_environment_overrides_and_invalid_values(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"query_default_max_rows": 10, "query_max_rows": 50}))
    monkeypatch.setenv("DATA_AGENT_QUERY_MAX_ROWS", "75")
    assert load_settings(path).query_max_rows == 75
    monkeypatch.setenv("DATA_AGENT_RESPONSE_MAX_BYTES", "-1")
    with pytest.raises(OperationError):
        load_settings(path)


def test_effective_settings_budgets_and_internal_errors(product):
    services, *_ = product
    services.settings = replace(services.settings, response_max_bytes=500)
    assert services.invoke(lambda: {"text": "x" * 501})["code"] == "RESPONSE_SIZE_LIMIT"

    def bad():
        raise RuntimeError("PRIVATE_SECRET")

    assert "PRIVATE_SECRET" not in json.dumps(services.invoke(bad))


def test_reader_policy_runs_before_connect_and_preserves_decimal():
    connect = Mock()
    reader = MssqlDatabaseReader(
        connect=connect, drivers=lambda: ["ODBC Driver 18 for SQL Server"], platform="win32"
    )
    with pytest.raises(OperationError):
        reader.query(source(), None, "DELETE FROM dbo.orders", [], 10, 1000, 10)
    connect.assert_not_called()
    assert json_value(Decimal("123456789.12345")) == "123456789.12345"


async def test_all_tools_discovered_and_management_works_without_database(product):
    services, first, _, _, _, repository = product
    async with Client(create_server(build_test_connection(repository.path), services)) as client:
        tools = await client.list_tools()
        assert len(tools) == 16
        assert all(tool.inputSchema.get("type") == "object" for tool in tools)
        sources = await client.call_tool("list_data_sources", {})
        assert len(sources.structured_content["sources"]) == 2
        schemas = await client.call_tool(
            "get_table_schemas",
            {
                "tables": [
                    {"data_source_id": str(first.id), "schema_name": "dbo", "table_name": "orders"},
                    {"data_source_id": str(first.id), "schema_name": "dbo", "table_name": "items"},
                ]
            },
        )
        assert len(schemas.structured_content["results"]) == 2
        saved = await client.call_tool(
            "save_knowledge",
            {
                "title": "Fiscal calendar",
                "description": "Fiscal start",
                "content": "The fiscal year begins in October.",
                "kind": "business",
                "scope": {"level": "global"},
            },
        )
        assert saved.structured_content["success"]
        found = await client.call_tool("search_knowledge", {"query": "October"})
        assert len(found.structured_content["matches"]) == 1


def test_bootstrap_no_database_and_paths_follow_source_directory(tmp_path, monkeypatch):
    root = tmp_path / "owner"
    root.mkdir()
    path = root / "sources.json"
    path.write_text('{"version":1,"sources":[]}')
    (root / ".env").write_text(
        "DATA_AGENT_QUERY_DEFAULT_MAX_ROWS=7\nDATA_AGENT_SETTINGS_FILE=settings.json\nDATA_AGENT_STATE_FILE=metadata.sqlite3\n"
    )
    (root / "settings.json").write_text('{"query_max_rows":99}')
    for key in (
        "DATA_AGENT_QUERY_DEFAULT_MAX_ROWS",
        "DATA_AGENT_SETTINGS_FILE",
        "DATA_AGENT_STATE_FILE",
    ):
        monkeypatch.delenv(key, raising=False)
    # dotenv mutates environment; ensure pytest restores these keys afterwards.
    for key in (
        "DATA_AGENT_QUERY_DEFAULT_MAX_ROWS",
        "DATA_AGENT_SETTINGS_FILE",
        "DATA_AGENT_STATE_FILE",
    ):
        monkeypatch.setenv(key, "")
        monkeypatch.delenv(key)
    services = build_product(path)
    assert services.settings.query_default_max_rows == 7
    assert services.settings.query_max_rows == 99
    assert (root / "metadata.sqlite3").exists()
    assert services.sources.list()["sources"] == []
    services.stop()
