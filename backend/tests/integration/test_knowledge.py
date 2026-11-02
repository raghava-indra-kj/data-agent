from __future__ import annotations

import io
import os
import uuid

import pytest
from httpx import AsyncClient
from openpyxl import Workbook

from app.core.config import get_settings
from app.core.database import get_session_factory
from app.data_sources.adapters.mssql import MSSQLAdapter
from app.data_sources.adapters.mysql import MySQLAdapter
from app.data_sources.errors import DataSourceOperationError
from app.data_sources.service import DataSourceService
from app.data_sources.jobs import register_data_source_handlers
from app.data_sources.schemas import DatabaseCredentials, MSSQLConfig, MySQLConfig
from app.jobs.handlers import JobHandlerRegistry
from app.jobs.repository import JobRepository
from app.jobs.queue import PgJobQueue
from app.jobs.worker import Worker
from app.knowledge.builder import build_snapshot
from app.knowledge.jobs import register_knowledge_handlers


async def signup(client: AsyncClient, email: str) -> dict[str, str]:
    response = await client.post(
        "/api/v1/auth/signup", json={"email": email, "password": "StrongPassword1"}
    )
    assert response.status_code == 201
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def run_next_job() -> None:
    settings = get_settings()
    job_ids = await PgJobQueue(settings).reserve(1)
    assert job_ids
    handlers = JobHandlerRegistry()
    register_data_source_handlers(handlers)
    register_knowledge_handlers(handlers)
    worker = Worker(settings, handlers)
    worker.worker_id = "task4-integration-worker"
    await worker._process_job(job_ids[0])


def workbook_bytes() -> bytes:
    workbook = Workbook()
    orders = workbook.active
    orders.title = "Orders"
    orders.append(["Order ID", "Amount"])
    orders.append([1, 25.5])
    customers = workbook.create_sheet("Customers")
    customers.append(["Customer ID", "Name"])
    customers.append([100, "Anita"])
    output = io.BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


@pytest.mark.asyncio
async def test_postgres_knowledge_generation_selective_documents_annotations_and_versioning(
    client: AsyncClient,
) -> None:
    headers = await signup(client, "knowledge-postgres@example.com")
    source = await client.post(
        "/api/v1/data-sources",
        headers=headers,
        json={
            "kind": "postgres",
            "name": "Application DB",
            "config": {
                "host": "localhost",
                "port": 5432,
                "database": "dbassistant",
                "schema_name": "public",
                "ssl_mode": "disable",
            },
            "credentials": {"username": "dbassistant", "password": "dbassistant"},
        },
    )
    assert source.status_code == 201
    source_id = source.json()["id"]

    annotation = await client.post(
        f"/api/v1/knowledge/data-sources/{source_id}/annotations",
        headers=headers,
        json={
            "scope_type": "metric",
            "scope_key": "active users",
            "content": "Users whose account is active.",
        },
    )
    assert annotation.status_code == 201
    annotation_id = annotation.json()["id"]

    generated = await client.post(
        f"/api/v1/knowledge/data-sources/{source_id}/generate", headers=headers
    )
    assert generated.status_code == 202
    await run_next_job()

    status = await client.get(f"/api/v1/knowledge/data-sources/{source_id}", headers=headers)
    assert status.status_code == 200
    first_version_id = status.json()["current_version_id"]
    assert status.json()["status"] == "ready"
    assert first_version_id
    first_job_id = uuid.UUID(generated.json()["job_id"])
    async with get_session_factory()() as session:
        event_types = [
            item.event_type for item in await JobRepository(session).list_events(first_job_id)
        ]
    assert "knowledge.generation.started" in event_types
    assert "knowledge.schema.inspected" in event_types
    assert "knowledge.index.generated" in event_types
    assert "knowledge.generation.completed" in event_types

    index = await client.get(f"/api/v1/knowledge/data-sources/{source_id}/index", headers=headers)
    assert index.status_code == 200
    assert index.json()["document_type"] == "index"
    assert "users" in index.json()["content_markdown"]

    documents = await client.get(
        f"/api/v1/knowledge/data-sources/{source_id}/documents",
        headers=headers,
        params={"document_type": "table_schema"},
    )
    assert documents.status_code == 200
    assert documents.json()
    assert all("content_markdown" not in item for item in documents.json())

    users_key = next(item["document_key"] for item in documents.json() if item["document_key"].endswith(".users"))
    users_document = await client.get(
        f"/api/v1/knowledge/data-sources/{source_id}/table",
        headers=headers,
        params={"key": users_key},
    )
    assert users_document.status_code == 200
    assert "## Columns" in users_document.json()["content_markdown"]

    # Regeneration creates a new immutable version and does not destroy human business knowledge.
    regenerated = await client.post(
        f"/api/v1/knowledge/data-sources/{source_id}/generate", headers=headers
    )
    assert regenerated.status_code == 202
    await run_next_job()
    after = await client.get(f"/api/v1/knowledge/data-sources/{source_id}", headers=headers)
    assert after.json()["current_version_id"] != first_version_id
    versions = await client.get(
        f"/api/v1/knowledge/data-sources/{source_id}/versions", headers=headers
    )
    assert [item["version_number"] for item in versions.json()][:2] == [2, 1]
    annotations = await client.get(
        f"/api/v1/knowledge/data-sources/{source_id}/annotations", headers=headers
    )
    assert any(item["id"] == annotation_id for item in annotations.json())


@pytest.mark.asyncio
async def test_failed_regeneration_preserves_previous_current_version(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers = await signup(client, "knowledge-failure@example.com")
    source = await client.post(
        "/api/v1/data-sources",
        headers=headers,
        json={
            "kind": "postgres",
            "name": "Failure Test DB",
            "config": {
                "host": "localhost",
                "port": 5432,
                "database": "dbassistant",
                "schema_name": "public",
                "ssl_mode": "disable",
            },
            "credentials": {"username": "dbassistant", "password": "dbassistant"},
        },
    )
    source_id = source.json()["id"]
    assert (await client.post(f"/api/v1/knowledge/data-sources/{source_id}/generate", headers=headers)).status_code == 202
    await run_next_job()
    before = (await client.get(f"/api/v1/knowledge/data-sources/{source_id}", headers=headers)).json()
    current_version = before["current_version_id"]

    class FailingAdapter:
        async def introspect(self):
            raise DataSourceOperationError(
                "DATASOURCE_INTROSPECTION_FAILED", "Unable to inspect the datasource."
            )

    async def failing_resolve(self, data_source):  # type: ignore[no-untyped-def]
        return FailingAdapter()

    monkeypatch.setattr(DataSourceService, "resolve_adapter", failing_resolve)
    accepted = await client.post(
        f"/api/v1/knowledge/data-sources/{source_id}/generate", headers=headers
    )
    assert accepted.status_code == 202
    await run_next_job()

    after = (await client.get(f"/api/v1/knowledge/data-sources/{source_id}", headers=headers)).json()
    assert after["status"] == "error"
    assert after["current_version_id"] == current_version
    versions = await client.get(f"/api/v1/knowledge/data-sources/{source_id}/versions", headers=headers)
    assert len(versions.json()) == 1


@pytest.mark.asyncio
async def test_excel_duckdb_uses_same_knowledge_model(client: AsyncClient) -> None:
    headers = await signup(client, "knowledge-excel@example.com")
    upload = await client.post(
        "/api/v1/data-sources/excel",
        headers=headers,
        data={"name": "Workbook"},
        files={
            "file": (
                "workbook.xlsx",
                workbook_bytes(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert upload.status_code == 202
    source_id = upload.json()["data_source"]["id"]
    await run_next_job()

    generated = await client.post(
        f"/api/v1/knowledge/data-sources/{source_id}/generate", headers=headers
    )
    assert generated.status_code == 202
    await run_next_job()
    index = await client.get(f"/api/v1/knowledge/data-sources/{source_id}/index", headers=headers)
    assert index.status_code == 200
    text = index.json()["content_markdown"]
    assert "orders" in text
    assert "customers" in text


@pytest.mark.asyncio
async def test_knowledge_isolation(client: AsyncClient) -> None:
    first = await signup(client, "knowledge-one@example.com")
    second = await signup(client, "knowledge-two@example.com")
    source = await client.post(
        "/api/v1/data-sources",
        headers=first,
        json={
            "kind": "postgres",
            "name": "Private DB",
            "config": {"host": "localhost", "database": "dbassistant", "ssl_mode": "disable"},
            "credentials": {"username": "dbassistant", "password": "dbassistant"},
        },
    )
    source_id = source.json()["id"]
    assert (await client.get(f"/api/v1/knowledge/data-sources/{source_id}", headers=second)).status_code == 404
    assert (
        await client.post(f"/api/v1/knowledge/data-sources/{source_id}/generate", headers=second)
    ).status_code == 404


@pytest.mark.asyncio
async def test_optional_mysql_knowledge_introspection() -> None:
    host = os.getenv("TEST_MYSQL_HOST")
    if not host:
        pytest.skip("Set TEST_MYSQL_HOST and related credentials to run MySQL knowledge integration")
    adapter = MySQLAdapter(
        MySQLConfig(
            host=host,
            port=int(os.getenv("TEST_MYSQL_PORT", "3306")),
            database=os.environ["TEST_MYSQL_DATABASE"],
            ssl=os.getenv("TEST_MYSQL_SSL", "false").lower() == "true",
        ),
        DatabaseCredentials(
            username=os.environ["TEST_MYSQL_USERNAME"], password=os.environ["TEST_MYSQL_PASSWORD"]
        ),
    )
    snapshot = build_snapshot(await adapter.introspect())
    assert len(snapshot.schema_fingerprint) == 64
    assert snapshot.index.document_type == "index"


@pytest.mark.asyncio
async def test_optional_mssql_knowledge_introspection() -> None:
    host = os.getenv("TEST_MSSQL_HOST")
    if not host:
        pytest.skip("Set TEST_MSSQL_HOST and related credentials to run MSSQL knowledge integration")
    adapter = MSSQLAdapter(
        MSSQLConfig(
            host=host,
            port=int(os.getenv("TEST_MSSQL_PORT", "1433")),
            database=os.environ["TEST_MSSQL_DATABASE"],
            encrypt=os.getenv("TEST_MSSQL_ENCRYPT", "true").lower() == "true",
            trust_server_certificate=os.getenv("TEST_MSSQL_TRUST_CERT", "false").lower() == "true",
        ),
        DatabaseCredentials(
            username=os.environ["TEST_MSSQL_USERNAME"], password=os.environ["TEST_MSSQL_PASSWORD"]
        ),
    )
    snapshot = build_snapshot(await adapter.introspect())
    assert len(snapshot.schema_fingerprint) == 64
    assert snapshot.index.document_type == "index"
