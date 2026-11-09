import json
import sys
from dataclasses import asdict, replace
from pathlib import Path
from unittest.mock import Mock
from uuid import uuid4

import pyodbc
import pytest
from fastmcp import Client
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from data_agent_mcp.application.ports.credentials import CredentialResolutionError, ResolvedSecret
from data_agent_mcp.application.ports.data_sources import ConfigurationError
from data_agent_mcp.application.ports.database import ConnectionStage
from data_agent_mcp.application.use_cases.test_connection import TestConnection
from data_agent_mcp.bootstrap import build_test_connection
from data_agent_mcp.domain.data_sources.models import (
    AccessScope,
    ConnectionSettings,
    DatabaseEngine,
    DataSource,
    SecretReference,
    UsernamePasswordAuthentication,
    WindowsAuthentication,
)
from data_agent_mcp.infrastructure.configuration.file_data_sources import FileDataSourceRepository
from data_agent_mcp.infrastructure.credentials.environment import EnvironmentCredentialResolver
from data_agent_mcp.infrastructure.databases.mssql.connection_tester import (
    DRIVER,
    PROBE_SQL,
    MssqlConnectionTester,
)
from data_agent_mcp.presentation.cli import main
from data_agent_mcp.presentation.mcp.server import create_server


def source_for(server="localhost", sql_login=False):
    return DataSource(
        name="Offline fixture",
        engine=DatabaseEngine.MSSQL,
        connection=ConnectionSettings(server=server, database="FixtureDatabase"),
        authentication=UsernamePasswordAuthentication(
            "fixture-login", SecretReference("FIXTURE_SQL_PASSWORD")
        )
        if sql_login
        else WindowsAuthentication(),
        access_scope=AccessScope(("fixture-schema",)),
    )


def config_for(source):
    settings = source.connection
    auth = {"method": source.authentication.method.value}
    if isinstance(source.authentication, UsernamePasswordAuthentication):
        auth.update(
            username=source.authentication.username,
            password_reference=source.authentication.password_reference.key,
        )
    return {
        "id": str(source.id),
        "name": source.name,
        "engine": source.engine.value,
        "enabled": source.enabled,
        "connection": {
            "server": settings.server,
            "database": settings.database,
            "port": settings.port,
            "encryption": asdict(settings.encryption),
            "connect_timeout_seconds": settings.connect_timeout_seconds,
            "query_timeout_seconds": settings.query_timeout_seconds,
        },
        "authentication": auth,
        "access_scope": {"allowed_schemas": list(source.access_scope.allowed_schemas)},
    }


def write_sources(path, *sources):
    path.write_text(
        json.dumps({"version": 1, "sources": [config_for(s) for s in sources]}), encoding="utf-8"
    )
    return path


def test_username_environment_reference_is_resolved_and_preserved(tmp_path, monkeypatch):
    source = source_for(sql_login=True)
    item = config_for(source)
    item["authentication"].pop("username")
    item["authentication"]["username_reference"] = "FIXTURE_SQL_USERNAME"
    path = tmp_path / "sources.json"
    path.write_text(json.dumps({"version": 1, "sources": [item]}), encoding="utf-8")
    monkeypatch.setenv("FIXTURE_SQL_USERNAME", "environment-login")
    repository = FileDataSourceRepository(path)
    loaded = repository.get(source.id)
    assert loaded.authentication.username == "environment-login"
    repository.save(loaded, expected_revision=loaded.revision)
    saved_auth = json.loads(path.read_text())["sources"][0]["authentication"]
    assert saved_auth["username_reference"] == "FIXTURE_SQL_USERNAME"
    assert "username" not in saved_auth
    assert "environment-login" not in path.read_text()
    monkeypatch.setenv("FIXTURE_SQL_USERNAME", "updated-login")
    assert repository.get(source.id).authentication.username == "updated-login"


@pytest.mark.parametrize("reference", ["FIXTURE_MISSING_USERNAME", "invalid-variable!"])
def test_unavailable_username_reference_fails_without_echoing_values(
    tmp_path, monkeypatch, reference
):
    item = config_for(source_for(sql_login=True))
    item["authentication"].pop("username")
    item["authentication"]["username_reference"] = reference
    monkeypatch.delenv(reference, raising=False)
    path = tmp_path / "sources.json"
    path.write_text(json.dumps({"version": 1, "sources": [item]}), encoding="utf-8")
    with pytest.raises(ConfigurationError, match="username environment variable") as error:
        FileDataSourceRepository(path).list_all()
    assert reference not in str(error.value)


@pytest.mark.parametrize("both", [True, False])
def test_sql_auth_requires_exactly_one_username_source(tmp_path, both):
    item = config_for(source_for(sql_login=True))
    if both:
        item["authentication"]["username_reference"] = "FIXTURE_SQL_USERNAME"
    else:
        item["authentication"].pop("username")
    path = tmp_path / "sources.json"
    path.write_text(json.dumps({"version": 1, "sources": [item]}), encoding="utf-8")
    with pytest.raises(ConfigurationError, match="does not match the schema"):
        FileDataSourceRepository(path).list_all()


def fake_adapter(row=("ActualServer\\Instance", "FixtureDatabase", 1)):
    cursor = Mock()
    cursor.execute.return_value = cursor
    cursor.fetchone.return_value = row
    connection = Mock()
    connection.cursor.return_value = cursor
    connect = Mock(return_value=connection)
    adapter = MssqlConnectionTester(connect=connect, drivers=lambda: [DRIVER], platform="win32")
    return adapter, connect, connection, cursor


@pytest.mark.parametrize("server", ["localhost", r"remote.example.invalid\instance"])
@pytest.mark.parametrize("sql_login", [False, True])
def test_local_and_remote_with_both_authentication_methods(server, sql_login):
    source = source_for(server, sql_login)
    adapter, connect, connection, cursor = fake_adapter()
    result = adapter.test(source, ResolvedSecret("fixture-pass") if sql_login else None)
    assert result.success and result.actual_database == "FixtureDatabase"
    assert result.actual_server == r"ActualServer\Instance"
    text = connect.call_args.args[0]
    assert f"SERVER={{{server}}}" in text
    assert "Encrypt={yes}" in text and "TrustServerCertificate={no}" in text
    assert ("Trusted_Connection={no}" if sql_login else "Trusted_Connection={yes}") in text
    assert ("PWD=" in text) is sql_login
    assert connect.call_args.kwargs == {"timeout": 15, "autocommit": True}
    assert connection.timeout == 30
    cursor.execute.assert_called_once_with(PROBE_SQL)
    cursor.close.assert_called_once()
    connection.close.assert_called_once()


def test_port_and_timeouts_are_forwarded():
    source = source_for("host.example.invalid")
    source = replace(
        source,
        connection=replace(
            source.connection, port=1500, connect_timeout_seconds=7, query_timeout_seconds=9
        ),
    )
    adapter, connect, connection, _ = fake_adapter()
    assert adapter.test(source, None).success
    assert "SERVER={tcp:host.example.invalid,1500}" in connect.call_args.args[0]
    assert connect.call_args.kwargs["timeout"] == 7 and connection.timeout == 9


def test_quoted_odbc_values_cannot_inject_connection_attributes():
    source = source_for(sql_login=True)
    source = replace(
        source,
        connection=replace(source.connection, database="FixtureDatabase};Trusted_Connection=no"),
    )
    adapter, connect, _, _ = fake_adapter(row=("ActualServer", source.connection.database, 1))
    password = ResolvedSecret("braced};UID=intruder;pwd")
    assert adapter.test(source, password).success
    text = connect.call_args.args[0]
    assert "DATABASE={FixtureDatabase}};Trusted_Connection=no}" in text
    assert "PWD={braced}};UID=intruder;pwd}" in text


@pytest.mark.parametrize(
    "row",
    [None, ("s", "FixtureDatabase", 0), (None, "FixtureDatabase", 1), ("s", "FixtureDatabase")],
)
def test_invalid_probe_results_fail_and_close_resources(row):
    adapter, _, connection, cursor = fake_adapter(row)
    result = adapter.test(source_for(), None)
    assert not result.success and result.diagnostics.code == "CONNECTION_PROBE_INVALID"
    connection.close.assert_called_once()
    cursor.close.assert_called_once()


def test_wrong_database_is_reported():
    adapter, _, _, _ = fake_adapter(("ActualServer", "WrongDatabase", 1))
    result = adapter.test(source_for(), None)
    assert not result.success and result.actual_database == "WrongDatabase"
    assert result.diagnostics.code == "DATABASE_MISMATCH"


@pytest.mark.parametrize(
    "sqlstate, message, category, number",
    [
        (
            "28000",
            "[SQL Server]Login failed for user 'fixture-login'. (18456)",
            "authentication",
            18456,
        ),
        ("HYT00", "Login timeout expired (0)", "timeout", 0),
        ("08001", "Server unreachable (10060)", "connection", 10060),
        ("08001", "SSL certificate chain is not trusted (-1)", "encryption", None),
        ("42000", "Cannot open database (4060)", "database_access", 4060),
    ],
)
def test_driver_failures_keep_diagnostics_and_do_not_retry(sqlstate, message, category, number):
    connect = Mock(side_effect=pyodbc.Error(sqlstate, message))
    adapter = MssqlConnectionTester(connect, lambda: [DRIVER], "win32")
    result = adapter.test(source_for(sql_login=True), ResolvedSecret("fixture-pass"))
    assert not result.success
    assert result.diagnostics.sqlstate == sqlstate and result.diagnostics.error_number == number
    assert result.diagnostics.category == category
    assert result.diagnostics.stage == ConnectionStage.CONNECT
    assert "fixture-login" not in result.diagnostics.driver_message
    connect.assert_called_once()


def test_password_redaction_in_raw_and_odbc_escaped_messages():
    password = "secret};part"
    connect = Mock(
        side_effect=pyodbc.Error(
            "28000",
            f"PWD={{{password.replace('}', '}}')}}}; leaked {password}; UID=fixture-login; (18456)",
        )
    )
    adapter = MssqlConnectionTester(connect, lambda: [DRIVER], "win32")
    result = adapter.test(source_for(sql_login=True), ResolvedSecret(password))
    rendered = json.dumps(asdict(result))
    assert password not in rendered and password.replace("}", "}}") not in rendered
    assert "fixture-login" not in rendered
    assert "[redacted]" in rendered


def test_windows_login_is_redacted_from_driver_error():
    connect = Mock(
        side_effect=pyodbc.Error("28000", "Login failed for user 'DOMAIN\\fixture-user'. (18456)")
    )
    result = MssqlConnectionTester(connect, lambda: [DRIVER], "win32").test(source_for(), None)
    assert "fixture-user" not in result.diagnostics.driver_message


def test_query_failure_preserves_error_even_if_cleanup_fails():
    adapter, _, connection, cursor = fake_adapter()
    cursor.execute.side_effect = pyodbc.Error("HYT00", "Probe timed out (0)")
    cursor.close.side_effect = RuntimeError("cleanup")
    result = adapter.test(source_for(), None)
    assert not result.success and result.diagnostics.category == "timeout"
    assert result.diagnostics.stage == ConnectionStage.VERIFY
    connection.close.assert_called_once()


def test_cleanup_failure_changes_success_to_failure():
    adapter, _, connection, cursor = fake_adapter()
    cursor.close.side_effect = RuntimeError("cleanup")
    result = adapter.test(source_for(), None)
    assert not result.success and result.diagnostics.code == "CONNECTION_CLEANUP_FAILED"
    connection.close.assert_called_once()


@pytest.mark.parametrize(
    "mode", ["missing_driver", "windows_on_linux", "missing_password", "wrong_engine"]
)
def test_invalid_adapter_prerequisites_never_connect(mode):
    source = source_for(sql_login=mode == "missing_password")
    if mode == "wrong_engine":
        source = replace(source, engine=DatabaseEngine.MYSQL)
    connect = Mock()
    adapter = MssqlConnectionTester(
        connect,
        lambda: [] if mode == "missing_driver" else [DRIVER],
        "linux" if mode == "windows_on_linux" else "win32",
    )
    assert not adapter.test(source, None).success
    connect.assert_not_called()


def test_unknown_adapter_error_does_not_expose_secrets():
    connect = Mock(side_effect=RuntimeError("sensitive internal data"))
    result = MssqlConnectionTester(connect, lambda: [DRIVER], "win32").test(source_for(), None)
    assert not result.success and "sensitive internal data" not in json.dumps(asdict(result))


def test_use_case_routes_and_resolves_sql_password():
    source = source_for(sql_login=True)
    repository = Mock()
    repository.get.return_value = source
    adapter, connect, _, _ = fake_adapter()
    resolver = EnvironmentCredentialResolver({"FIXTURE_SQL_PASSWORD": "fixture-pass"})
    result = TestConnection(repository, resolver, {DatabaseEngine.MSSQL: adapter}).execute(
        str(source.id)
    )
    assert result.success and result.duration_ms >= 0
    assert "PWD={fixture-pass}" in connect.call_args.args[0]


def test_windows_authentication_does_not_resolve_credentials():
    source = source_for()
    repository = Mock()
    repository.get.return_value = source
    resolver = Mock()
    adapter, _, _, _ = fake_adapter()
    assert (
        TestConnection(repository, resolver, {DatabaseEngine.MSSQL: adapter})
        .execute(str(source.id))
        .success
    )
    resolver.resolve.assert_not_called()


@pytest.mark.parametrize(
    "case, code",
    [
        ("unknown", "SOURCE_NOT_FOUND"),
        ("disabled", "SOURCE_DISABLED"),
        ("unsupported", "UNSUPPORTED_ENGINE"),
        ("missing_secret", "CREDENTIAL_UNAVAILABLE"),
        ("invalid_config", "INVALID_CONFIGURATION"),
    ],
)
def test_use_case_failures_prevent_adapter_calls(case, code):
    source = source_for(sql_login=case == "missing_secret")
    if case == "disabled":
        source = source.set_enabled(False)
    if case == "unsupported":
        source = replace(source, engine=DatabaseEngine.POSTGRESQL)
    repository = Mock()
    repository.get.return_value = None if case == "unknown" else source
    if case == "invalid_config":
        repository.get.side_effect = ConfigurationError("Invalid configuration")
    adapter = Mock()
    result = TestConnection(
        repository, EnvironmentCredentialResolver({}), {DatabaseEngine.MSSQL: adapter}
    ).execute(str(source.id))
    assert not result.success and result.diagnostics.code == code
    adapter.test.assert_not_called()


def test_invalid_id_does_not_read_configuration():
    repository = Mock()
    result = TestConnection(repository, Mock(), {}).execute("not-a-uuid")
    assert result.diagnostics.code == "INVALID_SOURCE_ID"
    repository.get.assert_not_called()


@pytest.mark.parametrize(
    "mapping, key",
    [
        ({}, "ABSENT"),
        ({"EMPTY": ""}, "EMPTY"),
        ({}, "not an env name"),
        ({"BAD": "contains\0nul"}, "BAD"),
    ],
)
def test_invalid_or_missing_secret_does_not_echo_values(mapping, key):
    with pytest.raises(CredentialResolutionError) as error:
        EnvironmentCredentialResolver(mapping).resolve(SecretReference(key))
    assert "contains\0nul" not in str(error.value)


def test_configuration_reloads_and_accepts_multiple_sources(tmp_path):
    first, second = source_for(), source_for("remote.example.invalid", True)
    path = write_sources(tmp_path / "sources.json", first, second)
    repository = FileDataSourceRepository(path)
    assert repository.get(first.id) == first and repository.get(second.id) == second
    write_sources(path, first.set_enabled(False))
    assert not repository.get(first.id).enabled
    assert repository.get(second.id) is None


@pytest.mark.parametrize(
    "case",
    [
        "duplicate_id",
        "raw_password",
        "invalid_json",
        "duplicate_key",
        "missing",
        "invalid_domain",
        "coerced_bool",
        "coerced_version",
        "oversized",
    ],
)
def test_configuration_fails_closed_without_echoing_raw_input(tmp_path, case):
    source = source_for()
    path = write_sources(tmp_path / "sources.json", source)
    document = json.loads(path.read_text())
    if case == "duplicate_id":
        document["sources"].append(document["sources"][0])
    elif case == "raw_password":
        document["sources"][0]["authentication"]["password"] = "DO_NOT_ECHO_THIS_PASSWORD"
    elif case == "invalid_domain":
        document["sources"][0]["connection"]["port"] = 0
    elif case == "coerced_bool":
        document["sources"][0]["enabled"] = "false"
    elif case == "coerced_version":
        document["version"] = True
    path.write_text(json.dumps(document))
    if case == "invalid_json":
        path.write_text("invalid DO_NOT_ECHO_THIS_PASSWORD")
    elif case == "duplicate_key":
        path.write_text('{"version": 1, "sources": [], "sources": []}')
    elif case == "missing":
        path.unlink()
    elif case == "oversized":
        path.write_text(" " * 1_000_001)
    with pytest.raises(ConfigurationError) as error:
        FileDataSourceRepository(path).get(source.id)
    assert "DO_NOT_ECHO_THIS_PASSWORD" not in str(error.value)


def test_empty_configuration_and_bootstrap_never_connect(tmp_path):
    path = write_sources(tmp_path / "sources.json")
    result = build_test_connection(path).execute(str(uuid4()))
    assert result.diagnostics.code == "SOURCE_NOT_FOUND"


def test_examples_are_disabled_and_valid():
    path = Path(__file__).parents[1] / "sources.example.json"
    sources = FileDataSourceRepository(path).list_all()
    assert len(sources) == 2 and all(not s.enabled for s in sources)


def test_cli_offline_validation_and_diagnostic_export(tmp_path, capsys):
    path = write_sources(tmp_path / "sources.json", source_for())
    assert main(["check-config", "--sources", str(path)]) == 0
    assert json.loads(capsys.readouterr().out)["valid"]
    output = tmp_path / "result.json"
    assert (
        main(
            [
                "test-connection",
                "--sources",
                str(path),
                "--source-id",
                str(uuid4()),
                "--output",
                str(output),
            ]
        )
        == 1
    )
    assert json.loads(output.read_text())["diagnostics"]["code"] == "SOURCE_NOT_FOUND"


async def test_mcp_exposes_exactly_one_tool_and_returns_structured_results():
    source = source_for()
    repository = Mock()
    repository.get.return_value = source
    adapter, _, _, _ = fake_adapter()
    server = create_server(TestConnection(repository, Mock(), {DatabaseEngine.MSSQL: adapter}))
    async with Client(server) as client:
        tools = await client.list_tools()
        assert [tool.name for tool in tools] == ["test_connection"]
        assert tools[0].annotations.readOnlyHint is True
        assert set(tools[0].inputSchema["properties"]) == {"data_source_id"}
        result = await client.call_tool("test_connection", {"data_source_id": str(source.id)})
        assert result.structured_content["success"] is True
        assert result.structured_content["actual_database"] == "FixtureDatabase"


async def test_mcp_reports_configuration_failure_without_driver_call(tmp_path):
    path = write_sources(tmp_path / "sources.json")
    async with Client(create_server(build_test_connection(path))) as client:
        result = await client.call_tool("test_connection", {"data_source_id": str(uuid4())})
        assert result.structured_content["diagnostics"]["code"] == "SOURCE_NOT_FOUND"


async def test_actual_stdio_entry_point_initializes_and_returns_offline_failure(tmp_path):
    path = write_sources(tmp_path / "sources.json")
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "data_agent_mcp", "serve", "--sources", str(path)],
    )
    # The subprocess receives an explicitly empty source file, so this test cannot
    # reach a database even though subprocesses do not inherit pytest's patches.
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            assert len(tools.tools) == 16
            assert {
                "test_connection",
                "list_data_sources",
                "get_table_schemas",
                "execute_readonly_queries",
                "save_knowledge",
                "configure_refresh_schedule",
            } <= {tool.name for tool in tools.tools}
            discovered = await session.call_tool("list_data_sources", {})
            assert discovered.structuredContent["sources"] == []
            response = await session.call_tool("test_connection", {"data_source_id": str(uuid4())})
            assert not response.isError
            assert response.structuredContent["diagnostics"]["code"] == "SOURCE_NOT_FOUND"


def test_unexpected_credential_provider_errors_are_sanitized():
    source = source_for(sql_login=True)
    repository = Mock()
    repository.get.return_value = source
    credentials = Mock()
    credentials.resolve.side_effect = RuntimeError("DO_NOT_EXPOSE_SECRET")
    adapter = Mock()
    result = TestConnection(repository, credentials, {DatabaseEngine.MSSQL: adapter}).execute(
        str(source.id)
    )
    assert result.diagnostics.code == "CREDENTIAL_RESOLUTION_FAILED"
    assert "DO_NOT_EXPOSE_SECRET" not in json.dumps(asdict(result))
    adapter.test.assert_not_called()
