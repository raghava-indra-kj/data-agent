from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from app.agent.models import JobArtifact, SQLExecution, ToolExecution
from app.auth.repository import AuthRepository
from app.core.config import get_settings
from app.core.database import get_session_factory
from app.core.errors import AppError
from app.core.time import utc_now
from app.data_sources.models import DataSource
from app.data_sources.types import QueryResult
from app.jobs.models import Job
from app.jobs.service import JobService
from app.reporting.jobs import run_dashboard_refresh_job
from app.reporting.models import DashboardWidget


async def identity(client: AsyncClient, email: str) -> tuple[dict[str, str], uuid.UUID, uuid.UUID]:
    signup = await client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": "StrongPassword1", "display_name": "Task Six"},
    )
    assert signup.status_code == 201
    headers = {"Authorization": f"Bearer {signup.json()['access_token']}"}
    org = await client.get("/api/v1/organizations/current", headers=headers)
    assert org.status_code == 200
    async with get_session_factory()() as session:
        user = await AuthRepository(session).get_user_by_email(email)
        assert user is not None
        return headers, user.id, uuid.UUID(org.json()["id"])


@pytest.mark.asyncio
async def test_dashboard_crud_and_audit(client: AsyncClient) -> None:
    headers, _, _ = await identity(client, "task6-dashboard@example.com")
    created = await client.post(
        "/api/v1/dashboards",
        headers=headers,
        json={"title": "Executive", "description": "Company KPIs"},
    )
    assert created.status_code == 201
    dashboard_id = created.json()["id"]

    listing = await client.get("/api/v1/dashboards", headers=headers)
    assert listing.status_code == 200
    assert listing.json()[0]["title"] == "Executive"

    detail = await client.get(f"/api/v1/dashboards/{dashboard_id}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["widgets"] == []

    audit = await client.get("/api/v1/audit", headers=headers)
    assert audit.status_code == 200
    assert any(item["action"] == "dashboard.created" for item in audit.json())


@pytest.mark.asyncio
async def test_active_job_limit_is_enforced_atomically(client: AsyncClient) -> None:
    _, user_id, org_id = await identity(client, "task6-limits@example.com")
    settings = get_settings()
    async with get_session_factory()() as session:
        service = JobService(session, settings)
        for index in range(settings.max_active_jobs_per_user):
            await service.create_job(
                organization_id=org_id,
                requested_by=user_id,
                job_type=f"limit_test_{index}",
            )
        with pytest.raises(AppError) as captured:
            await service.create_job(
                organization_id=org_id,
                requested_by=user_id,
                job_type="limit_overflow",
            )
        assert captured.value.code == "USER_ACTIVE_JOB_LIMIT_REACHED"
        assert captured.value.status_code == 429


@pytest.mark.asyncio
async def test_save_widget_and_background_refresh_preserves_provenance(
    client: AsyncClient, monkeypatch
) -> None:
    headers, user_id, org_id = await identity(client, "task6-widget@example.com")
    dashboard = await client.post(
        "/api/v1/dashboards", headers=headers, json={"title": "Revenue"}
    )
    dashboard_id = uuid.UUID(dashboard.json()["id"])

    source_id = uuid.uuid4()
    source_job_id = uuid.uuid4()
    tool_id = uuid.uuid4()
    source_sql_id = uuid.uuid4()
    now = utc_now()
    async with get_session_factory()() as session:
        session.add(
            DataSource(
                id=source_id,
                organization_id=org_id,
                name="Reporting Source",
                kind="postgres",
                display_type="postgres",
                status="active",
                config={"host": "unused", "port": 5432, "database": "unused"},
                created_by=user_id,
            )
        )
        session.add(
            Job(
                id=source_job_id,
                organization_id=org_id,
                requested_by=user_id,
                job_type="chat_query",
                status="succeeded",
                input={},
                result={},
                attempt_count=1,
                max_attempts=1,
                created_at=now,
                started_at=now,
                finished_at=now,
            )
        )
        session.add(
            ToolExecution(
                id=tool_id,
                job_id=source_job_id,
                sequence=1,
                tool_name="execute_sql",
                status="succeeded",
                input_summary={},
                output_summary={},
                started_at=now,
                finished_at=now,
            )
        )
        session.add(
            SQLExecution(
                id=source_sql_id,
                tool_execution_id=tool_id,
                data_source_id=source_id,
                sql_text="SELECT month, revenue FROM revenue_monthly",
                status="succeeded",
                row_count=2,
                truncated=False,
                columns=["month", "revenue"],
                result_bytes=64,
                duration_ms=5,
                started_at=now,
                finished_at=now,
            )
        )
        session.add(
            JobArtifact(
                job_id=source_job_id,
                kind="table",
                name="Revenue source",
                source_sql_execution_id=source_sql_id,
                payload={
                    "schema_version": 1,
                    "data_source_id": str(source_id),
                    "columns": ["month", "revenue"],
                    "rows": [["Jan", 100], ["Feb", 120]],
                    "row_count": 2,
                    "truncated": False,
                },
                created_at=now,
            )
        )
        await session.commit()

    widget = await client.post(
        f"/api/v1/dashboards/{dashboard_id}/widgets",
        headers=headers,
        json={
            "source_job_id": str(source_job_id),
            "source_sql_execution_id": str(source_sql_id),
            "widget_type": "line",
            "title": "Monthly revenue",
            "visualization_config": {
                "x_field": "month",
                "series": [{"field": "revenue", "label": "Revenue"}],
            },
        },
    )
    assert widget.status_code == 201, widget.text
    widget_id = uuid.UUID(widget.json()["id"])
    assert widget.json()["created_from_sql_execution_id"] == str(source_sql_id)

    refresh = await client.post(f"/api/v1/dashboards/widgets/{widget_id}/refresh", headers=headers)
    assert refresh.status_code == 202
    refresh_job_id = uuid.UUID(refresh.json()["job_id"])

    class FakeAdapter:
        async def execute_read_query(self, sql: str, *, max_rows: int) -> QueryResult:
            assert sql == "SELECT month, revenue FROM revenue_monthly"
            assert max_rows > 1
            return QueryResult(
                columns=("month", "revenue"),
                rows=(("Jan", 101), ("Feb", 125)),
                truncated=False,
            )

    async def fake_resolve(self, source):  # type: ignore[no-untyped-def]
        return FakeAdapter()

    monkeypatch.setattr("app.reporting.jobs.DataSourceService.resolve_adapter", fake_resolve)
    async with get_session_factory()() as session:
        claimed = await JobService(session, get_settings()).claim(
            refresh_job_id, "task6-test-worker"
        )
        assert claimed is not None
    result = await run_dashboard_refresh_job(refresh_job_id)
    async with get_session_factory()() as session:
        await JobService(session, get_settings()).complete(refresh_job_id, result)
        saved = await session.get(DashboardWidget, widget_id)
        assert saved is not None
        assert saved.last_refresh_job_id == refresh_job_id
        assert saved.last_refreshed_at is not None

    refreshed = await client.get(f"/api/v1/dashboards/{dashboard_id}", headers=headers)
    item = refreshed.json()["widgets"][0]
    assert item["latest_artifact"]["kind"] == "chart"
    assert item["latest_artifact"]["payload"]["renderer"] == "frontend"
    assert item["latest_artifact"]["payload"]["data"][1]["revenue"] == 125
