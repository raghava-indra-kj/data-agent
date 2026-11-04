from __future__ import annotations

import base64
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.agent.clarification import AskUserArgs, ClarificationAnswers, build_request
from app.agent.evidence import (
    DaxResultEvidence,
    EvidenceBundle,
    render_evidence_context,
    validate_evidence,
)
from app.agent.tools import AgentToolContext, build_default_tool_registry
from app.conversations.service import ConversationService
from app.core.config import Settings
from app.core.errors import AppError
from app.jobs.repository import JobRepository
from app.power_bi.auth import require_enabled
from app.power_bi.context import filter_expression, scoped_dax
from app.power_bi.mcp_client import FabricIQClient, query_result
from app.power_bi.schemas import ReportContext
from app.power_bi.service import identity, report_url
from app.power_bi.tools import DaxChartArgs, with_power_bi_tools


def context(**changes):
    return ReportContext(
        report_binding_id=uuid.uuid4(),
        page_name="ReportSection",
        page_display_name="Backlog",
        captured_at="2026-11-04T00:00:00Z",
        **changes,
    )


def basic(**changes):
    return {
        "filterType": 1,
        "target": {"table": "Orders", "column": "Region"},
        "operator": "In",
        "values": ["West"],
        **changes,
    }


@pytest.mark.asyncio
async def test_clarification_preserves_the_original_report_filters(monkeypatch):
    captured = context(filters=[basic()])
    conversation_id, job_id, message_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    request = build_request(
        AskUserArgs.model_validate(
            {
                "reason": "Choose a metric.",
                "questions": [{"id": "metric", "kind": "text", "prompt": "Which metric?"}],
            }
        )
    )
    service = ConversationService(AsyncMock(), Settings(_env_file=None))
    service.repo = SimpleNamespace(
        lock_for_org=AsyncMock(return_value=SimpleNamespace(private_to_creator=True)),
        get_message=AsyncMock(
            return_value=SimpleNamespace(
                id=message_id,
                role="assistant",
                job_id=job_id,
                metadata_json={"clarification": request},
            )
        ),
        has_user_message_after=AsyncMock(return_value=False),
        message_for_job=AsyncMock(
            return_value=SimpleNamespace(
                content="Show this report's backlog",
                metadata_json={},
            )
        ),
    )
    monkeypatch.setattr(
        JobRepository,
        "get_for_organization",
        AsyncMock(
            return_value=SimpleNamespace(
                input_data={
                    "power_bi_context": captured.model_dump(mode="json"),
                }
            ),
        ),
    )
    service.submit_message = AsyncMock(return_value=("message", "job"))
    await service.answer_clarification(
        conversation_id=conversation_id,
        message_id=message_id,
        organization_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        payload=ClarificationAnswers.model_validate(
            {
                "answers": [{"question_id": "metric", "text": "Open orders"}],
            }
        ),
    )
    assert service.submit_message.await_args.kwargs["payload"].power_bi_context == captured


@pytest.mark.parametrize(
    "url",
    [
        "http://app.powerbi.com/groups/me/reports/a",
        "https://evil.test/reports/a",
        "https://app.powerbi.com.evil.test/reports/a",
        "https://user:pass@app.powerbi.com/reports/a",
        "https://app.powerbi.com:bad/reports/a",
    ],
)
def test_report_urls_never_allow_arbitrary_hosts_or_credentials(url):
    with pytest.raises(AppError):
        report_url(url)


def test_resolving_ambiguous_identities_fails_closed():
    payload = {
        "structuredContent": [
            {"fabricItemId": str(uuid.uuid4())},
            {"fabricItemId": str(uuid.uuid4())},
        ]
    }
    with pytest.raises(AppError, match="multiple identities"):
        identity(payload, ("fabricItemId",))


def test_default_installation_does_not_require_microsoft_configuration():
    settings = Settings(_env_file=None)
    assert not settings.power_bi_enabled
    with pytest.raises(AppError) as error:
        require_enabled(settings)
    assert error.value.code == "POWER_BI_DISABLED"


def test_filter_values_and_identifiers_are_escaped_as_data():
    result = filter_expression(
        basic(
            target={"table": "O'rders", "column": "Re]gion"}, values=['West"), EVALUATE ROW("x",1)']
        )
    )
    assert "'O''rders'[Re]]gion]" in result
    assert '"West""), EVALUATE ROW(""x"",1)"' in result


@pytest.mark.parametrize(
    "filter",
    [
        basic(filterType=4),
        basic(target={"table": "Orders", "hierarchy": "Region"}),
        basic(values=[{}]),
        {
            "filterType": 0,
            "target": {"table": "T", "column": "C"},
            "conditions": [{"operator": "Contains", "value": "a"}],
        },
    ],
)
def test_unsupported_filters_never_silently_widen_scope(filter):
    with pytest.raises(AppError):
        scoped_dax('EVALUATE ROW("Count", [Orders])', context(filters=[filter]))


def test_report_scope_wraps_the_result_without_breaking_define_or_order_by():
    query = (
        'DEFINE MEASURE Orders[N] = COUNTROWS(Orders)\nEVALUATE ROW("Count", [N]) ORDER BY [Count]'
    )
    result = scoped_dax(query, context(filters=[basic()]))
    assert result.startswith("DEFINE MEASURE Orders[N]")
    assert "EVALUATE CALCULATETABLE(" in result
    assert "TREATAS({\"West\"}, 'Orders'[Region])" in result
    assert result.endswith("ORDER BY [Count]")
    assert scoped_dax(query, context(mode="model", filters=[basic()])) == query


@pytest.mark.parametrize(
    "query",
    [
        'EVALUATE ROW("x",1) EVALUATE ROW("x",2)',
        "DELETE FROM Orders",
        'EVALUATE ROW("x",1); CREATE TABLE X',
    ],
)
def test_only_one_read_only_query_is_accepted(query):
    with pytest.raises(AppError):
        scoped_dax(query, None)


def test_structured_results_preserve_columns_nulls_and_truncation():
    result = query_result(
        {
            "structuredContent": {
                "results": [
                    {"tables": [{"rows": [{"Region": "West", "Orders": 42}, {"Region": "East"}]}]}
                ]
            }
        },
        2,
    )
    assert result.columns == ("Region", "Orders")
    assert result.rows == (("West", 42), ("East", None))
    assert result.truncated


def test_embedded_csv_is_used_instead_of_its_inline_preview():
    result = query_result(
        {
            "content": [
                {"type": "text", "text": '{"rows":[{"Region":"West","Orders":42}]}'},
                {
                    "type": "resource",
                    "resource": {
                        "mimeType": "text/csv",
                        "blob": base64.b64encode(b"Region,Orders\nWest,42\nEast,53\n").decode(),
                    },
                },
            ]
        },
        1000,
    )
    assert result.rows == (("West", 42), ("East", 53))
    assert not result.truncated


def test_mismatched_resources_and_upstream_query_errors_are_rejected():
    for payload in [
        {"structuredContent": {"rows": [{"Count": 2}], "error": "denied"}},
        {
            "structuredContent": {"rows": [{"Count": 2}]},
            "content": [
                {"type": "resource", "resource": {"mimeType": "text/csv", "text": "Count\n3"}}
            ],
        },
    ]:
        with pytest.raises(AppError):
            query_result(payload, 1000)


@pytest.mark.asyncio
async def test_runtime_schema_and_tool_allowlist_are_enforced():
    session = SimpleNamespace(call_tool=AsyncMock())
    client = FabricIQClient(
        session,
        {"ExecuteQuery": {"type": "object", "required": ["newRequiredField"]}},
        Settings(_env_file=None),
    )
    for name in ("DeleteItem", "ExecuteQuery"):
        with pytest.raises(AppError):
            await client.call(name, {})
    session.call_tool.assert_not_awaited()


def test_power_bi_cannot_write_private_data_to_public_artifacts_or_shared_knowledge():
    ctx = AgentToolContext(
        job_id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        allowed_data_source_ids=frozenset(),
        settings=Settings(_env_file=None),
    )
    default = build_default_tool_registry()
    integrated = with_power_bi_tools(default, ctx)
    assert default.get("create_html_artifact") is not None
    for name in ("create_html_artifact", "save_knowledge", "save_skill", "edit_skill"):
        assert integrated.get(name) is None
    assert integrated.get("execute_dax")
    assert integrated.get("execute_sql")
    assert "series" in DaxChartArgs.model_json_schema()["$defs"]["PowerBIChartSpec"]["properties"]


def test_dax_results_are_grounded_evidence_without_fabricating_sql():
    result = DaxResultEvidence(
        uuid.uuid4(),
        uuid.uuid4(),
        'EVALUATE ROW("Total", 42)',
        ("Total",),
        ((42,),),
        False,
        False,
        {},
    )
    bundle = EvidenceBundle(uuid.uuid4(), "How many?", "42", (), (), False, dax_results=(result,))
    assert validate_evidence(bundle) == []
    assert "VERIFIED POWER BI DAX EVIDENCE" in render_evidence_context(bundle)
    assert '"rows": [[42]]' in render_evidence_context(bundle)
