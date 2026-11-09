from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from app.core.errors import AppError
from app.power_bi.context import filter_expression, scoped_dax, validate_context
from app.power_bi.schemas import ReportContext


def hierarchy(**overrides: object) -> dict[str, object]:
    return {
        "$schema": "http://powerbi.com/product/schema#hierarchy",
        "filterType": 9,
        "target": [{"table": "Backlog_Main", "column": "TypeGroup"}],
        "hierarchyData": [{"operator": "Selected", "value": "Core"}],
        **overrides,
    }


def context(filters: list[dict[str, object]]) -> ReportContext:
    return ReportContext(
        report_binding_id=uuid.uuid4(),
        page_name="ReportSection1",
        page_display_name="Stock Allocation CTA",
        captured_at=datetime.now(UTC),
        filters=filters,
    )


def test_single_column_hierarchy_preserves_selected_values() -> None:
    assert filter_expression(hierarchy()) == (
        "KEEPFILTERS(TREATAS({\"Core\"}, 'Backlog_Main'[TypeGroup]))"
    )
    assert (
        filter_expression(
            hierarchy(
                hierarchyData=[
                    {"operator": "Selected", "value": "Core", "children": []},
                    {"operator": "Selected", "value": "Service"},
                ]
            )
        )
        == 'KEEPFILTERS(TREATAS({"Core","Service"}, \'Backlog_Main\'[TypeGroup]))'
    )


def test_hierarchy_values_and_identifiers_remain_data() -> None:
    assert filter_expression(
        hierarchy(
            target=[{"table": "O'rders", "column": "Ty]pe"}],
            hierarchyData=[
                {"operator": "Selected", "value": 'Core"), EVALUATE ROW("x",1)'},
                {"operator": "Selected", "value": None},
                {"operator": "Selected", "value": False},
                {"operator": "Selected", "value": 0},
            ],
        )
    ) == (
        'KEEPFILTERS(TREATAS({"Core""), EVALUATE ROW(""x"",1)",BLANK(),FALSE(),0}, '
        "'O''rders'[Ty]]pe]))"
    )


@pytest.mark.parametrize(
    "overrides",
    [
        {"target": []},
        {"target": {"table": "T", "column": "C"}},
        {"target": [{"table": "T", "column": "C"}, {"table": "T", "column": "D"}]},
        {"target": [{"table": "T", "hierarchy": "H", "hierarchyLevel": "L"}]},
        {"target": [{"table": "T", "column": "C", "keys": ["Id"]}]},
        {"target": [{"table": "", "column": "C"}]},
        {"hierarchyData": []},
        {"hierarchyData": None},
        {"hierarchyData": [None]},
        {"hierarchyData": [{"operator": "Selected"}]},
        {"hierarchyData": [{"value": "Core"}]},
        {"hierarchyData": [{"operator": "Inherited", "value": "Core"}]},
        {"hierarchyData": [{"operator": "NotSelected", "value": "Core"}]},
        {"hierarchyData": [{"operator": "Selected", "keyValues": ["Core"]}]},
        {"hierarchyData": [{"operator": "Selected", "value": "Core", "keyValues": [1]}]},
        {"hierarchyData": [{"operator": "Selected", "value": "Core", "children": None}]},
        {
            "hierarchyData": [
                {
                    "operator": "Selected",
                    "value": "Core",
                    "children": [{"operator": "Selected", "value": "Child"}],
                }
            ]
        },
        {"hierarchyData": [{"operator": "Selected", "value": {"unexpected": "object"}}]},
        {"hierarchyData": [{"operator": "Selected", "value": float("nan")}]},
        {"hierarchyData": [{"operator": "Selected", "value": "x" * 4001}]},
        {"hierarchyData": [{"operator": "Selected", "value": "Core"}] * 1001},
    ],
)
def test_unsupported_hierarchy_never_silently_widens_scope(overrides: dict[str, object]) -> None:
    with pytest.raises(AppError) as error:
        filter_expression(hierarchy(**overrides))
    assert error.value.code == "POWER_BI_CONTEXT_UNSUPPORTED"


@pytest.mark.parametrize("logic", ["And", "Or"])
def test_empty_advanced_filter_is_unconstrained(logic: str) -> None:
    item = {
        "filterType": 0,
        "target": {"table": "Backlog_Main", "column": "yCRDWeekNumber"},
        "logicalOperator": logic,
        "conditions": [],
    }
    assert filter_expression(item) is None
    query = 'EVALUATE ROW("Total", [Total Backlog])'
    assert scoped_dax(query, context([item])) == query


@pytest.mark.parametrize(
    "overrides",
    [
        {"target": {"table": "T", "column": ""}},
        {"target": {"table": "T", "hierarchy": "H"}},
        {"logicalOperator": "Xor"},
        {"conditions": None},
        {"conditions": [{}]},
    ],
)
def test_empty_filter_support_does_not_accept_malformed_filters(
    overrides: dict[str, object],
) -> None:
    with pytest.raises(AppError):
        filter_expression(
            {
                "filterType": 0,
                "target": {"table": "T", "column": "C"},
                "logicalOperator": "And",
                "conditions": [],
                **overrides,
            }
        )


def test_report_view_combines_hierarchy_and_other_active_filters() -> None:
    snapshot = context(
        [
            hierarchy(),
            {
                "filterType": 0,
                "target": {"table": "Backlog_Main", "column": "yCRDWeekNumber"},
                "logicalOperator": "And",
                "conditions": [],
            },
            {
                "filterType": 1,
                "target": {"table": "Backlog_Main", "column": "New_div1"},
                "operator": "In",
                "values": ["BID"],
            },
            {
                "filterType": 1,
                "target": {"table": "Backlog_Main", "column": "Region"},
                "operator": "NotIn",
                "values": [None],
            },
        ]
    )
    validate_context(snapshot)
    query = 'EVALUATE ROW("Total", SUM(Backlog_Main[amount p$]))'
    assert scoped_dax(query, snapshot) == (
        'EVALUATE CALCULATETABLE(\nROW("Total", SUM(Backlog_Main[amount p$])),\n'
        "KEEPFILTERS(TREATAS({\"Core\"}, 'Backlog_Main'[TypeGroup])),\n"
        "KEEPFILTERS(TREATAS({\"BID\"}, 'Backlog_Main'[New_div1])),\n"
        "KEEPFILTERS(FILTER(ALL('Backlog_Main'[Region]), "
        "NOT ('Backlog_Main'[Region] IN {BLANK()})))\n) "
    )
