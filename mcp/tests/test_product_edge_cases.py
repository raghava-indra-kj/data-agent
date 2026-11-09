"""Offline regression checks for execution boundaries, state and resource budgets."""

import json
from dataclasses import replace
from unittest.mock import Mock
from uuid import uuid4

import httpx
import pyodbc
import pytest
from test_product import product as product_fixture
from test_product import save, source

from data_agent_mcp.application.ports.credentials import ResolvedSecret
from data_agent_mcp.application.sql_policy import validate_select
from data_agent_mcp.domain.data_sources.models import (
    SecretReference,
    UsernamePasswordAuthentication,
)
from data_agent_mcp.domain.knowledge import KnowledgeScope, utc_now
from data_agent_mcp.domain.queries import OperationError, TableRef
from data_agent_mcp.domain.settings import RuntimeSettings
from data_agent_mcp.infrastructure.databases.mssql.reader import MssqlDatabaseReader
from data_agent_mcp.infrastructure.embeddings.cloud import CloudEmbeddingProvider
from data_agent_mcp.infrastructure.storage.runtime_lease import FileRuntimeLease


@pytest.fixture
def product(tmp_path):
    yield from product_fixture.__wrapped__(tmp_path)


def adapter(rows, *, error=None, database="offline"):
    cursor = Mock()
    cursor.description = [("amount", int, None, None, 10, 0, True)]
    cursor.fetchone.side_effect = [(database,), *rows, None]
    if error:

        def execute(sql, *args):
            if sql.startswith("SELECT TOP"):
                raise error

        cursor.execute.side_effect = execute
    connection = Mock()
    connection.cursor.return_value = cursor
    connect = Mock(return_value=connection)
    reader = MssqlDatabaseReader(
        connect=connect, drivers=lambda: ["ODBC Driver 18 for SQL Server"], platform="win32"
    )
    return reader, connect, connection, cursor


def test_reader_row_cap_parameters_and_cleanup():
    reader, connect, connection, cursor = adapter([(1,), (2,), (3,)])
    result = reader.query(
        source(), None, "SELECT amount FROM dbo.orders WHERE amount > ?", [0], 2, 3000, 7
    )
    assert result["rows"] == [[1], [2]]
    assert result["truncation_reason"] == "row_limit"
    assert cursor.execute.call_args.args[1:] == (0,)
    assert "TOP 3" in cursor.execute.call_args.args[0]
    assert connection.timeout == 7
    assert connect.call_args.kwargs["autocommit"] is True
    cursor.cancel.assert_called_once()
    cursor.close.assert_called_once()
    connection.close.assert_called_once()


def test_reader_byte_cap_preserves_bounded_result():
    reader, _, connection, cursor = adapter([("x" * 500,), ("y" * 500,)])
    result = reader.query(source(), None, "SELECT amount FROM dbo.orders", [], 10, 1200, 5)
    assert result["truncated"] and result["truncation_reason"] == "response_size_limit"
    assert len(json.dumps(result).encode()) <= 1200
    assert any("TEXTSIZE" in c.args[0] for c in cursor.execute.call_args_list)
    connection.close.assert_called_once()


def test_reader_diagnostics_redact_and_release_after_failure():
    error = pyodbc.Error(
        "28000", "Login failed for user 'fixture-login'. PWD=PRIVATE_SECRET; (18456)"
    )
    reader, _, connection, cursor = adapter([], error=error)
    configured = replace(
        source(),
        authentication=UsernamePasswordAuthentication(
            "fixture-login", SecretReference("OFFLINE_KEY")
        ),
    )
    with pytest.raises(OperationError) as caught:
        reader.query(
            configured,
            ResolvedSecret("PRIVATE_SECRET"),
            "SELECT * FROM dbo.orders",
            [],
            10,
            3000,
            5,
        )
    serialized = json.dumps(caught.value.diagnostics)
    assert "PRIVATE_SECRET" not in serialized and "fixture-login" not in serialized
    assert caught.value.diagnostics["sqlstate"] == "28000"
    assert caught.value.diagnostics["error_number"] == 18456
    cursor.close.assert_called_once()
    connection.close.assert_called_once()
    assert reader._slots.acquire(blocking=False)
    reader._slots.release()


def test_reader_rejects_wrong_database_and_closes():
    reader, _, connection, cursor = adapter([], database="different")
    with pytest.raises(OperationError, match="differs"):
        reader.query(source(), None, "SELECT * FROM dbo.orders", [], 1, 3000, 5)
    connection.close.assert_called_once()
    cursor.close.assert_called_once()


def test_sample_is_bounded_does_not_store_rows_and_closes():
    reader, _, connection, cursor = adapter([("x" * 600,), ("y" * 600,)])
    reader.settings = replace(
        reader.settings, profile_sample_max_bytes=1000, profile_row_max_bytes=700
    )
    configured = source()
    result = reader.sample(
        configured, None, TableRef(str(configured.id), "dbo", "orders"), ["status"], 100
    )
    assert len(result["rows"]) == 1 and result["truncated"]
    assert "TOP (100)" in cursor.execute.call_args.args[0]
    cursor.close.assert_called_once()
    connection.close.assert_called_once()


def test_batch_credential_failure_does_not_abort_other_sources(product):
    services, first, second, _, _, repository = product
    repository.save(
        replace(
            first,
            authentication=UsernamePasswordAuthentication(
                "fixture", SecretReference("MISSING_PASSWORD")
            ),
        ),
        first.revision,
    )
    result = services.catalog.list_tables([str(first.id), str(second.id)])
    assert result["results"][0]["code"] == "CREDENTIAL_UNAVAILABLE"
    assert result["results"][1]["success"]


def test_knowledge_management_survives_disabled_source(product):
    services, first, _, _, _, repository = product
    document = save(services, KnowledgeScope("table", str(first.id), "dbo", "orders"))
    repository.save(replace(first, enabled=False), first.revision)
    assert not services.knowledge.search("retention")["matches"]
    assert services.knowledge.get([document["id"]])["results"][0]["code"] == "KNOWLEDGE_NOT_FOUND"
    assert services.knowledge.get([document["id"]], include_disabled=True)["results"][0]["success"]
    assert services.knowledge.list(include_disabled=True)["knowledge"][0]["id"] == document["id"]
    disabled = services.knowledge.set_enabled(
        [{"id": document["id"], "enabled": False, "expected_version": 1}]
    )
    assert disabled["results"][0]["success"] and not disabled["results"][0]["enabled"]


def test_schedule_disable_does_not_require_working_credentials(product):
    services, first, _, _, _, repository = product
    table = TableRef(str(first.id), "dbo", "orders")
    schedule = services.schedules.configure("refresh", [table], ["schema"], 3600)["schedule"]
    repository.save(replace(first, enabled=False), first.revision)
    result = services.schedules.configure(
        "refresh", [table], ["schema"], 3600, False, schedule["id"], schedule["version"]
    )
    assert not result["schedule"]["enabled"]
    with pytest.raises(OperationError):
        services.schedules.configure(
            "bad", [table], ["data_profile"], 3600, False, sample_rows=100000
        )


def test_generated_identity_collision_preserves_original(product):
    services, first, _, store, _, _ = product
    scope = KnowledgeScope("table", str(first.id), "dbo", "orders")
    original = services.knowledge.generated(
        "fixed-key", "Schema", "Description", {"columns": []}, "schema", scope, {}
    )["knowledge"]
    document = replace(store.get_document(original["id"]), id=str(uuid4()))
    with pytest.raises(OperationError, match="Another refresh"):
        store.save_document(document, None)
    assert store.get_document(original["id"])
    assert store.generated_document("fixed-key").id == original["id"]
    assert store.get_document(document.id) is None
    assert len(services.knowledge.search("Schema", semantic=False)["matches"]) == 1


def test_generated_freshness_identifies_configuration_change(product):
    services, first, _, _, _, repository = product
    scope = KnowledgeScope("table", str(first.id), "dbo", "orders")
    from data_agent_mcp.application.use_cases.catalog import fingerprint

    doc = services.knowledge.generated(
        "fixed-key",
        "Schema",
        "Description",
        {},
        "schema",
        scope,
        {"observed_at": utc_now(), "source_fingerprint": fingerprint(first)},
    )["knowledge"]
    assert doc["freshness"]["status"] == "current"
    repository.save(replace(first, description="Changed"), first.revision)
    result = services.knowledge.get([doc["id"]])["results"][0]
    assert result["freshness"]["status"] == "source_changed"
    assert not result["freshness"]["database_changes_checked"]


def test_runtime_lease_rejects_second_owner_and_releases(tmp_path):
    one = FileRuntimeLease(tmp_path / "store.lock")
    two = FileRuntimeLease(tmp_path / "store.lock")
    one.acquire()
    try:
        with pytest.raises(OperationError, match="Another MCP"):
            two.acquire()
    finally:
        one.release()
    two.acquire()
    two.release()


def test_write_receipts_and_error_details_respect_response_budget(product):
    services, *_ = product
    services.settings = replace(services.settings, response_max_bytes=500)
    written = services.invoke(
        lambda: {"knowledge": {"id": "saved-id", "version": 2, "description": "x" * 1000}},
        _mutation=True,
    )
    assert written["success"] and written["receipts"] == [{"id": "saved-id", "version": 2}]

    def error():
        raise OperationError("DRIVER_FAILED", "Safe error", {"driver_message": "x" * 1000})

    failed = services.invoke(error)
    assert failed["code"] == "DRIVER_FAILED" and failed["response_truncated"]
    assert len(json.dumps(failed).encode()) <= 500


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM",
        "SELECT * FROM dbo.orders WITH (XLOCK)",
        "SELECT * FROM dbo.orders WITH (NOLOCK)",
    ],
)
def test_malformed_and_hinted_sql_fails_closed(sql):
    with pytest.raises(OperationError):
        validate_select(sql, source(), [], 10)


@pytest.mark.parametrize(
    "payload",
    [
        {"data": [{"index": 0, "embedding": [True]}]},
        {"data": [{"index": 1, "embedding": [1.0]}]},
        {"data": [{"index": 0, "embedding": []}]},
    ],
)
def test_malformed_cloud_vectors_fail_safely(payload):
    provider = CloudEmbeddingProvider(
        RuntimeSettings(),
        {"DATA_AGENT_EMBEDDING_API_KEY": "PRIVATE_SECRET"},
        httpx.MockTransport(lambda _: httpx.Response(200, json=payload)),
    )
    with pytest.raises(OperationError) as caught:
        provider.embed(["text"])
    assert "PRIVATE_SECRET" not in str(caught.value)
