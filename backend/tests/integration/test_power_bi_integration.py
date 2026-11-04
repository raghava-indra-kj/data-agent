from __future__ import annotations

import json
import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from app.agent.evidence import collect_evidence, validate_evidence
from app.agent.models import ToolExecution
from app.agent.tools import AgentToolContext, AuditedToolExecutor, build_default_tool_registry
from app.auth.repository import AuthRepository
from app.conversations.models import Conversation
from app.core.config import get_settings
from app.core.database import get_session_factory
from app.core.time import utc_now
from app.jobs.service import JobService
from app.organizations.models import OrganizationMembership
from app.power_bi import auth, service, tools
from app.power_bi.models import MicrosoftAuthTransaction, MicrosoftConnection
from app.power_bi.schemas import ReportCandidate
from app.secrets.service import SecretService


async def identity(client, email):
    response = await client.post(
        "/api/v1/auth/signup", json={"email": email, "password": "StrongPassword1"}
    )
    assert response.status_code == 201
    headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
    org = await client.get("/api/v1/organizations/current", headers=headers)
    async with get_session_factory()() as session:
        user = await AuthRepository(session).get_user_by_email(email)
    return headers, user.id, uuid.UUID(org.json()["id"])


def enable(monkeypatch):
    settings = get_settings()
    for name, value in {
        "power_bi_enabled": True,
        "power_bi_embedding_enabled": True,
        "power_bi_tenant_id": str(uuid.uuid4()),
        "power_bi_client_id": str(uuid.uuid4()),
        "power_bi_client_secret": "test-only-not-a-credential",
    }.items():
        monkeypatch.setattr(settings, name, value)
    return settings


async def connection(org, user, settings):
    async with get_session_factory()() as session:
        secret = await SecretService(session, settings).create(
            organization_id=org, purpose="power_bi_token_cache", payload={"cache": "{}"}
        )
        item = MicrosoftConnection(
            organization_id=org,
            user_id=user,
            tenant_id=settings.power_bi_tenant_id,
            object_id=str(uuid.uuid4()),
            account_id="test",
            display_name="Test account",
            secret_id=secret.id,
            status="connected",
        )
        session.add(item)
        await session.commit()
    return item


def resolved(monkeypatch, model_id=None):
    model_id = model_id or str(uuid.uuid4())

    async def resolve(_self, url):
        return ReportCandidate(
            report_id=url.rsplit("/", 1)[-1],
            workspace_id=str(uuid.uuid4()),
            semantic_model_id=model_id,
            name="Backlog report",
            web_url=url,
        )

    monkeypatch.setattr(service.PowerBIService, "resolve", resolve)
    return model_id


@pytest.mark.asyncio
async def test_disabled_power_bi_does_not_require_configuration(client):
    headers, _, _ = await identity(client, "disabled@example.com")
    flags = await client.get("/api/v1/power-bi/features", headers=headers)
    assert flags.status_code == 200 and flags.json()["enabled"] is False
    start = await client.post("/api/v1/power-bi/connections/start", headers=headers)
    assert start.status_code == 409


@pytest.mark.asyncio
async def test_multiple_reports_share_one_source_and_duplicates_are_safe(client, monkeypatch):
    enable(monkeypatch)
    headers, _, _ = await identity(client, "reports@example.com")
    resolved(monkeypatch)
    payload = {
        "name": "Backlog",
        "report_url": f"https://app.powerbi.com/groups/me/reports/{uuid.uuid4()}",
    }
    first = await client.post("/api/v1/data-sources/power-bi", headers=headers, json=payload)
    assert first.status_code == 201, first.text
    again = await client.post("/api/v1/data-sources/power-bi", headers=headers, json=payload)
    second = await client.post(
        "/api/v1/data-sources/power-bi",
        headers=headers,
        json={**payload, "report_url": f"https://app.powerbi.com/groups/me/reports/{uuid.uuid4()}"},
    )
    assert first.json()["id"] == again.json()["id"] == second.json()["id"]
    resolved(monkeypatch)
    clash = await client.post(
        "/api/v1/data-sources/power-bi",
        headers=headers,
        json={**payload, "report_url": f"https://app.powerbi.com/groups/me/reports/{uuid.uuid4()}"},
    )
    assert clash.status_code == 409
    listing = await client.get("/api/v1/data-sources", headers=headers)
    assert len(listing.json()) == 1


@pytest.mark.asyncio
async def test_private_conversations_jobs_and_events_are_hidden_from_other_workspace_members(
    client,
):
    first, first_user, org = await identity(client, "private-owner@example.com")
    second, second_user, _ = await identity(client, "private-member@example.com")
    second["X-Organization-ID"] = str(org)
    async with get_session_factory()() as session:
        session.add(
            OrganizationMembership(
                organization_id=org, user_id=second_user, role="admin", created_at=utc_now()
            )
        )
        private = Conversation(
            organization_id=org,
            created_by=first_user,
            title="Private Power BI answer",
            private_to_creator=True,
        )
        shared = Conversation(
            organization_id=org,
            created_by=first_user,
            title="Existing SQL conversation",
            private_to_creator=False,
        )
        session.add_all([private, shared])
        await session.commit()
        job = await JobService(session, get_settings()).create_job(
            organization_id=org,
            requested_by=first_user,
            job_type="chat_query",
            input_data={"power_bi_private": True},
            conversation_id=private.id,
        )
    for path in [
        f"/conversations/{private.id}",
        f"/conversations/{private.id}/messages",
        f"/jobs/{job.id}",
        f"/jobs/{job.id}/execution",
        f"/jobs/{job.id}/events",
    ]:
        denied = await client.get("/api/v1" + path, headers=second)
        assert denied.status_code == 404, (path, denied.text)
    assert (
        await client.get(f"/api/v1/conversations/{shared.id}", headers=second)
    ).status_code == 200
    assert (await client.get(f"/api/v1/jobs/{job.id}/execution", headers=first)).status_code == 200
    listed = await client.get("/api/v1/conversations", headers=second)
    assert [item["id"] for item in listed.json()["items"]] == [str(shared.id)]
    assert (await client.get("/api/v1/jobs", headers=second)).json() == []
    await client.delete("/api/v1/conversations", headers=second)
    assert (
        await client.get(f"/api/v1/conversations/{private.id}", headers=first)
    ).status_code == 200


@pytest.mark.asyncio
async def test_dax_and_chart_persist_as_private_evidence_with_empty_sql_contract(
    client, monkeypatch
):
    settings = enable(monkeypatch)
    headers, user, org = await identity(client, "dax@example.com")
    conn = await connection(org, user, settings)
    model_id = resolved(monkeypatch)
    created = await client.post(
        "/api/v1/data-sources/power-bi",
        headers=headers,
        json={
            "name": "Backlog",
            "report_url": f"https://app.powerbi.com/groups/me/reports/{uuid.uuid4()}",
        },
    )
    source_id = uuid.UUID(created.json()["id"])
    monkeypatch.setattr(
        service, "acquire_token", AsyncMock(return_value=("fake-test-token", 3600, conn.id))
    )
    calls = []

    class FakeFabric:
        async def call(self, name, arguments):
            calls.append((name, arguments))
            return {
                "structuredContent": {"tables": [{"rows": [{"Region": "West", "Open orders": 42}]}]}
            }

    @asynccontextmanager
    async def fake_client(*_args):
        yield FakeFabric()

    monkeypatch.setattr(tools, "fabric_client", fake_client)
    async with get_session_factory()() as session:
        job = await JobService(session, settings).create_job(
            organization_id=org,
            requested_by=user,
            job_type="chat_query",
            input_data={"power_bi_private": True},
        )
        session.add(
            ToolExecution(
                job_id=job.id,
                sequence=1,
                tool_name="read_power_bi_schema",
                status="succeeded",
                input_summary={"data_source_id": str(source_id)},
                started_at=utc_now(),
            )
        )
        await session.commit()
    ctx = AgentToolContext(
        job_id=job.id,
        organization_id=org,
        conversation_id=uuid.uuid4(),
        allowed_data_source_ids=frozenset({source_id}),
        settings=settings,
        requested_by=user,
        power_bi_source_ids=frozenset({source_id}),
        power_bi_identity={"tenant_id": conn.tenant_id, "object_id": conn.object_id},
    )
    executor = AuditedToolExecutor(
        ctx, tools.with_power_bi_tools(build_default_tool_registry(), ctx)
    )
    result = json.loads(
        await executor.invoke(
            "execute_dax",
            {
                "data_source_id": str(source_id),
                "dax": 'EVALUATE SUMMARIZECOLUMNS(Orders[Region], "Open orders", [Open orders])',
            },
        )
    )
    assert result["ok"], result
    assert calls[0][1]["artifactId"] == model_id
    chart = json.loads(
        await executor.invoke(
            "create_power_bi_chart",
            {
                "dax_execution_id": result["dax_execution_id"],
                "chart": {
                    "chart_type": "bar",
                    "title": "Open orders by region",
                    "x_field": "Region",
                    "series": [{"field": "Open orders"}],
                },
            },
        )
    )
    assert chart["ok"], chart
    trace = await client.get(f"/api/v1/jobs/{job.id}/execution", headers=headers)
    assert trace.status_code == 200, trace.text
    body = trace.json()
    assert body["sql"] == [] and len(body["dax"]) == 1
    assert len(body["artifacts"]) == 2
    assert all(
        item["source_dax_execution_id"] == result["dax_execution_id"] for item in body["artifacts"]
    )
    async with get_session_factory()() as session:
        evidence = await collect_evidence(
            session, job_id=job.id, question="Open orders?", analyst_notes="42 open orders"
        )
    assert validate_evidence(evidence) == []
    assert len(evidence.dax_results) == 1

    # Switching accounts between tool calls must not query the new account in the old chat.
    async with get_session_factory()() as session:
        stored = await session.get(MicrosoftConnection, conn.id)
        stored.object_id = str(uuid.uuid4())
        await session.commit()
    previous_calls = len(calls)
    denied = json.loads(
        await executor.invoke(
            "execute_dax", {"data_source_id": str(source_id), "dax": 'EVALUATE ROW("Count", 1)'}
        )
    )
    assert denied["ok"] is False
    assert denied["error"]["code"] == "POWER_BI_ACCOUNT_CHANGED"
    assert len(calls) == previous_calls


@pytest.mark.asyncio
async def test_oauth_state_is_bound_to_browser_and_consumed_once(client, monkeypatch):
    settings = enable(monkeypatch)
    _, user, org = await identity(client, "oauth@example.com")
    oid = str(uuid.uuid4())
    fake = SimpleNamespace(
        initiate_auth_code_flow=lambda *args, **kwargs: {
            "auth_uri": "https://login.microsoftonline.com/test",
            "state": "test-state",
            "nonce": "test-nonce",
        },
        acquire_token_by_auth_code_flow=lambda *args: {
            "access_token": "not-real",
            "id_token_claims": {"tid": settings.power_bi_tenant_id, "oid": oid},
        },
        get_accounts=lambda: [{"home_account_id": "home-test"}],
    )
    monkeypatch.setattr(auth, "client", lambda *args: fake)
    async with get_session_factory()() as session:
        _, cookie = await auth.begin_connection(session, settings, org, user)
    async with get_session_factory()() as session:
        with pytest.raises(Exception) as error:
            await auth.finish_connection(
                session, settings, {"state": "test-state"}, "wrong-browser"
            )
        assert error.value.code == "POWER_BI_SIGNIN_EXPIRED"
    async with get_session_factory()() as session:
        await auth.finish_connection(session, settings, {"state": "test-state"}, cookie)
    async with get_session_factory()() as session:
        assert await session.scalar(select(MicrosoftAuthTransaction)) is None
        stored = await session.scalar(select(MicrosoftConnection))
        assert stored.object_id == oid
        with pytest.raises(Exception) as error:
            await auth.finish_connection(session, settings, {"state": "test-state"}, cookie)
        assert error.value.code == "POWER_BI_SIGNIN_EXPIRED"
