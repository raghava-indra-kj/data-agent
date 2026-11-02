from __future__ import annotations

import io
import os
import uuid
from pathlib import Path

import pytest
from httpx import AsyncClient
from openpyxl import Workbook

from app.core.config import get_settings
from app.core.database import get_session_factory
from app.data_sources.adapters.duckdb import DuckDBAdapter
from app.data_sources.jobs import register_data_source_handlers
from app.data_sources.repository import DataSourceRepository
from app.data_sources.schemas import DatabaseCredentials, MSSQLConfig, MySQLConfig
from app.data_sources.adapters.mssql import MSSQLAdapter
from app.data_sources.adapters.mysql import MySQLAdapter
from app.jobs.handlers import JobHandlerRegistry
from app.jobs.queue import PgJobQueue
from app.jobs.worker import Worker


async def signup(client: AsyncClient, email: str) -> tuple[dict[str, str], uuid.UUID]:
    response = await client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": "StrongPassword1"},
    )
    assert response.status_code == 201
    token = response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    org = await client.get("/api/v1/organizations/current", headers=headers)
    assert org.status_code == 200
    return headers, uuid.UUID(org.json()["id"])


def workbook_bytes(*, mixed: bool = False) -> bytes:
    workbook = Workbook()
    orders = workbook.active
    orders.title = "Order Items"
    orders.append(["Order ID", "Amount", "Status"])
    orders.append([1, 12.5, "paid"])
    orders.append([2, 20 if not mixed else "unknown", "pending"])
    customers = workbook.create_sheet("Customers")
    customers.append(["Customer ID", "Name"])
    customers.append([100, "Anita"])
    output = io.BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


async def run_next_job() -> None:
    settings = get_settings()
    job_ids = await PgJobQueue(settings).reserve(1)
    assert job_ids
    handlers = JobHandlerRegistry()
    register_data_source_handlers(handlers)
    worker = Worker(settings, handlers)
    worker.worker_id = "task2-integration-worker"
    await worker._process_job(job_ids[0])


@pytest.mark.asyncio
async def test_postgres_datasource_crud_secret_redaction_and_job_test(client: AsyncClient) -> None:
    headers, _ = await signup(client, "datasource@example.com")
    create = await client.post(
        "/api/v1/data-sources",
        headers=headers,
        json={
            "kind": "postgres",
            "name": "Internal PostgreSQL",
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
    assert create.status_code == 201
    payload = create.json()
    assert "secret_id" not in payload
    assert "password" not in create.text
    assert "username" not in create.text
    data_source_id = payload["id"]

    accepted = await client.post(f"/api/v1/data-sources/{data_source_id}/test", headers=headers)
    assert accepted.status_code == 202
    await run_next_job()

    detail = await client.get(f"/api/v1/data-sources/{data_source_id}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["status"] == "active"
    assert detail.json()["last_tested_at"] is not None

    schema = await client.get(f"/api/v1/data-sources/{data_source_id}/schema", headers=headers)
    assert schema.status_code == 200
    table_names = {item["name"] for item in schema.json()["tables"]}
    assert "users" in table_names


@pytest.mark.asyncio
async def test_datasource_organization_isolation(client: AsyncClient) -> None:
    first_headers, _ = await signup(client, "first-ds@example.com")
    second_headers, _ = await signup(client, "second-ds@example.com")
    created = await client.post(
        "/api/v1/data-sources",
        headers=first_headers,
        json={
            "kind": "postgres",
            "name": "Private Source",
            "config": {"host": "localhost", "database": "dbassistant", "ssl_mode": "disable"},
            "credentials": {"username": "dbassistant", "password": "dbassistant"},
        },
    )
    assert created.status_code == 201
    data_source_id = created.json()["id"]
    assert (await client.get(f"/api/v1/data-sources/{data_source_id}", headers=second_headers)).status_code == 404
    assert (await client.get("/api/v1/data-sources", headers=second_headers)).json() == []


@pytest.mark.asyncio
async def test_excel_materializes_once_to_persistent_duckdb_and_deletes_cleanly(client: AsyncClient) -> None:
    headers, org_id = await signup(client, "excel@example.com")
    upload = await client.post(
        "/api/v1/data-sources/excel",
        headers=headers,
        data={"name": "Workbook Sales"},
        files={
            "file": (
                "sales.xlsx",
                workbook_bytes(mixed=True),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert upload.status_code == 202
    data_source_id = uuid.UUID(upload.json()["data_source"]["id"])
    await run_next_job()

    detail = await client.get(f"/api/v1/data-sources/{data_source_id}", headers=headers)
    assert detail.status_code == 200
    body = detail.json()
    assert body["status"] == "active"
    assert body["display_type"] == "excel"
    assert body["kind"] == "duckdb"
    assert body["active_file"]["status"] == "ready"
    assert {item["table_name"] for item in body["active_file"]["sheet_mapping"] if not item["skipped"]} == {
        "order_items",
        "customers",
    }
    assert "materialized_database_path" not in detail.text
    assert "source_path" not in detail.text

    settings = get_settings()
    async with get_session_factory()() as session:
        repo = DataSourceRepository(session)
        file = await repo.active_file(data_source_id)
        assert file is not None and file.materialized_database_path
        database_path = Path(settings.data_directory) / file.materialized_database_path
    assert database_path.is_file()

    adapter = DuckDBAdapter(database_path)
    first = await adapter.execute_read_query(
        "SELECT order_id, amount FROM order_items ORDER BY order_id", max_rows=10
    )
    assert len(first.rows) == 2
    assert str(first.rows[1][1]) == "unknown"
    # Re-open through a fresh adapter instance: the workbook is not reloaded for queries.
    second = await DuckDBAdapter(database_path).execute_read_query(
        "SELECT COUNT(*) AS count FROM customers", max_rows=10
    )
    assert second.rows[0][0] == 1

    deleted = await client.delete(f"/api/v1/data-sources/{data_source_id}", headers=headers)
    assert deleted.status_code == 204
    managed_dir = Path(settings.data_directory) / "organizations" / str(org_id) / "datasources" / str(data_source_id)
    assert not managed_dir.exists()


@pytest.mark.asyncio
async def test_failed_excel_replacement_preserves_previous_active_database(client: AsyncClient) -> None:
    headers, _ = await signup(client, "replacement@example.com")
    upload = await client.post(
        "/api/v1/data-sources/excel",
        headers=headers,
        data={"name": "Replace Me"},
        files={"file": ("good.xlsx", workbook_bytes(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert upload.status_code == 202
    data_source_id = upload.json()["data_source"]["id"]
    await run_next_job()
    before = (await client.get(f"/api/v1/data-sources/{data_source_id}", headers=headers)).json()
    active_file_id = before["active_file"]["id"]

    replacement = await client.post(
        f"/api/v1/data-sources/{data_source_id}/excel/replace",
        headers=headers,
        files={"file": ("broken.xlsx", b"not an xlsx file", "application/octet-stream")},
    )
    assert replacement.status_code == 202
    await run_next_job()

    after = (await client.get(f"/api/v1/data-sources/{data_source_id}", headers=headers)).json()
    assert after["status"] == "active"
    assert after["active_file"]["id"] == active_file_id


@pytest.mark.asyncio
async def test_optional_mysql_connection() -> None:
    host = os.getenv("TEST_MYSQL_HOST")
    if not host:
        pytest.skip("Set TEST_MYSQL_HOST and related credentials to run MySQL adapter integration")
    adapter = MySQLAdapter(
        MySQLConfig(
            host=host,
            port=int(os.getenv("TEST_MYSQL_PORT", "3306")),
            database=os.environ["TEST_MYSQL_DATABASE"],
            ssl=os.getenv("TEST_MYSQL_SSL", "false").lower() == "true",
        ),
        DatabaseCredentials(
            username=os.environ["TEST_MYSQL_USERNAME"],
            password=os.environ["TEST_MYSQL_PASSWORD"],
        ),
    )
    assert (await adapter.test_connection()).ok


@pytest.mark.asyncio
async def test_optional_mssql_connection() -> None:
    host = os.getenv("TEST_MSSQL_HOST")
    if not host:
        pytest.skip("Set TEST_MSSQL_HOST and related credentials to run MSSQL adapter integration")
    adapter = MSSQLAdapter(
        MSSQLConfig(
            host=host,
            port=int(os.getenv("TEST_MSSQL_PORT", "1433")),
            database=os.environ["TEST_MSSQL_DATABASE"],
            encrypt=os.getenv("TEST_MSSQL_ENCRYPT", "true").lower() == "true",
            trust_server_certificate=os.getenv("TEST_MSSQL_TRUST_CERT", "false").lower() == "true",
        ),
        DatabaseCredentials(
            username=os.environ["TEST_MSSQL_USERNAME"],
            password=os.environ["TEST_MSSQL_PASSWORD"],
        ),
    )
    assert (await adapter.test_connection()).ok
