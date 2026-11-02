from __future__ import annotations

import copy
import uuid
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from openpyxl import load_workbook

from app.agent import router
from app.agent.table_rows import (
    TRACE_TABLE_ROWS,
    StoredTableCache,
    TableView,
    stored_table,
    table_rows_page,
    table_view_rows,
)
from app.core.config import Settings
from app.core.errors import AppError

SETTINGS = Settings(jwt_secret="table-rows-test-secret-that-is-long-enough-12345")
ORG, OTHER_ORG = uuid.uuid4(), uuid.uuid4()
COLUMNS = ["reference", "region", "amount"]


def payload(count: int) -> dict[str, object]:
    rows = [
        [f"REF-{i}", f"Region {i % 7}", None if i % 50 == 0 else f"{i % 97}.5"]
        for i in range(count)
    ]
    return {"schema_version": 1, "columns": COLUMNS, "rows": rows, "row_count": count}


def collect(artifact_id, data, view, limit, *, organization_id=ORG):
    rows, cursor, matching = [], None, None
    while True:
        page = table_rows_page(
            SETTINGS, organization_id, artifact_id, stored_table(data), view,
            cursor=cursor, limit=limit,
        )
        rows += page.rows
        matching = page.matching_count
        assert page.has_more is (page.next_cursor is not None)
        if not page.has_more:
            return rows, matching
        cursor = page.next_cursor


def test_sorts_numbers_and_decimal_text_by_value_with_empty_cells_last():
    rows = [["a", "10"], ["b", None], ["c", 9], ["d", "9.5"], ["e", "x"], ["f", -1]]
    ascending = table_view_rows(["k", "v"], rows, TableView(sort="v"))
    descending = table_view_rows(["k", "v"], rows, TableView(sort="v", descending=True))
    assert [row[0] for row in ascending] == ["f", "c", "d", "a", "e", "b"]
    assert [row[0] for row in descending] == ["e", "a", "d", "c", "f", "b"]


def test_text_sorts_naturally_and_search_matches_any_cell_case_insensitively():
    rows = [["Item 10"], ["item 2"], ["Item 1"], [None]]
    assert table_view_rows(["name"], rows, TableView(sort="name")) == [
        ["Item 1"], ["item 2"], ["Item 10"], [None],
    ]
    assert table_view_rows(["name"], rows, TableView(search="  ITEM 1")) == [
        ["Item 10"], ["Item 1"],
    ]


def test_unknown_sort_column_is_rejected():
    with pytest.raises(AppError) as error:
        table_view_rows(COLUMNS, [], TableView(sort="secret_column"))
    assert error.value.code == "TABLE_SORT_INVALID"


@pytest.mark.parametrize(
    "view",
    [TableView(), TableView(sort="amount", descending=True), TableView(search="region 3")],
)
def test_pages_cover_the_view_without_duplicates_or_gaps(view):
    data, artifact_id = payload(1050), uuid.uuid4()
    rows, matching = collect(artifact_id, data, view, 200)
    expected = table_view_rows(COLUMNS, data["rows"], view)
    assert rows == expected
    assert matching == len(expected)
    assert len({row[0] for row in rows}) == len(rows)


def test_cursor_is_bound_to_artifact_view_and_organization():
    data, artifact_id = payload(500), uuid.uuid4()
    view = TableView(sort="amount")
    table = stored_table(data)
    first = table_rows_page(SETTINGS, ORG, artifact_id, table, view, cursor=None, limit=100)
    for organization_id, other_artifact, other_view in [
        (OTHER_ORG, artifact_id, view),
        (ORG, uuid.uuid4(), view),
        (ORG, artifact_id, TableView(sort="amount", descending=True)),
        (ORG, artifact_id, TableView(sort="amount", search="x")),
    ]:
        with pytest.raises(AppError) as error:
            table_rows_page(
                SETTINGS, organization_id, other_artifact, table, other_view,
                cursor=first.next_cursor, limit=100,
            )
        assert error.value.code == "INVALID_CURSOR"


def test_trace_sends_first_rows_and_a_cursor_that_continues_exactly_after_them():
    artifact = SimpleNamespace(
        id=uuid.uuid4(), job_id=uuid.uuid4(), kind="table", name="Rows",
        source_sql_execution_id=None, payload=payload(450), created_at="2026-10-20T00:00:00Z",
    )
    stored = copy.deepcopy(artifact.payload)

    response = router.trace_artifact(artifact, ORG, SETTINGS)

    assert response.payload["rows"] == stored["rows"][:TRACE_TABLE_ROWS]
    assert response.table_rows.stored_row_count == 450 and response.table_rows.has_more
    assert artifact.payload == stored  # the ORM payload is never trimmed in place
    rest, _ = collect(artifact.id, stored, TableView(), 200)
    second = table_rows_page(
        SETTINGS, ORG, artifact.id, stored_table(stored), TableView(),
        cursor=response.table_rows.next_cursor, limit=200,
    )
    assert second.rows == rest[TRACE_TABLE_ROWS : TRACE_TABLE_ROWS + 200]


def test_trace_leaves_small_tables_and_other_artifacts_complete():
    small = SimpleNamespace(
        id=uuid.uuid4(), job_id=uuid.uuid4(), kind="table", name=None,
        source_sql_execution_id=None, payload=payload(12), created_at="2026-10-20T00:00:00Z",
    )
    chart = SimpleNamespace(**{**vars(small), "kind": "chart", "payload": {"data": [1] * 500}})
    table = router.trace_artifact(small, ORG, SETTINGS)
    assert len(table.payload["rows"]) == 12
    assert table.table_rows.has_more is False and table.table_rows.next_cursor is None
    assert router.trace_artifact(chart, ORG, SETTINGS).table_rows is None


def route_mocks(monkeypatch, artifact, *, forbidden=False):
    authorized = AsyncMock(side_effect=AppError("JOB_NOT_FOUND", "x", 404) if forbidden else None)
    repo = SimpleNamespace(
        artifact_kind_for_job=AsyncMock(return_value=artifact.kind),
        artifact_payload=AsyncMock(return_value=artifact.payload),
    )
    monkeypatch.setattr(router, "STORED_TABLES", StoredTableCache())
    monkeypatch.setattr(router, "AgentExecutionRepository", lambda _: repo)
    monkeypatch.setattr(router, "JobService", lambda *_: SimpleNamespace(get_for_org=authorized))
    return authorized, repo


@pytest.mark.asyncio
async def test_rows_endpoint_checks_the_job_organization_before_reading(monkeypatch):
    artifact = SimpleNamespace(id=uuid.uuid4(), kind="table", payload=payload(10))
    authorized, repo = route_mocks(monkeypatch, artifact, forbidden=True)
    job_id = uuid.uuid4()
    with pytest.raises(AppError) as error:
        await router.list_table_rows(
            job_id, artifact.id, None, False, "", None, 200,
            context=(SimpleNamespace(id=OTHER_ORG), None), session=object(), settings=SETTINGS,
        )
    assert error.value.status_code == 404
    authorized.assert_awaited_once_with(job_id, OTHER_ORG)
    repo.artifact_kind_for_job.assert_not_awaited()
    repo.artifact_payload.assert_not_awaited()


@pytest.mark.asyncio
async def test_rows_endpoint_rejects_non_table_artifacts(monkeypatch):
    route_mocks(monkeypatch, SimpleNamespace(id=uuid.uuid4(), kind="chart", payload={}))
    with pytest.raises(AppError) as error:
        await router.list_table_rows(
            uuid.uuid4(), uuid.uuid4(), None, False, "", None, 200,
            context=(SimpleNamespace(id=ORG), None), session=object(), settings=SETTINGS,
        )
    assert error.value.code == "TABLE_ARTIFACT_NOT_FOUND"


@pytest.mark.asyncio
async def test_excel_export_contains_every_stored_row_in_the_requested_view(monkeypatch):
    artifact = SimpleNamespace(id=uuid.uuid4(), kind="table", payload=payload(1200))
    route_mocks(monkeypatch, artifact)
    request = router.TableExcelRequest(
        title="Open lines", headers=["Reference", "Region", "Amount"],
        sort="amount", descending=True, search="ref-1",
    )
    result = await router.export_table(
        uuid.uuid4(), artifact.id, request,
        context=(SimpleNamespace(id=ORG), None), session=object(), settings=SETTINGS,
    )
    values = list(load_workbook(BytesIO(result.body)).active.values)
    expected = table_view_rows(COLUMNS, artifact.payload["rows"], request)
    assert values[0] == ("Reference", "Region", "Amount")
    assert [row[0] for row in values[1:]] == [row[0] for row in expected]
    assert len(expected) > TRACE_TABLE_ROWS

    request.headers = ["Only one"]
    with pytest.raises(AppError) as error:
        await router.export_table(
            uuid.uuid4(), artifact.id, request,
            context=(SimpleNamespace(id=ORG), None), session=object(), settings=SETTINGS,
        )
    assert error.value.code == "TABLE_HEADERS_INVALID"


@pytest.mark.asyncio
async def test_rows_endpoint_reads_the_payload_once_but_checks_access_every_time(monkeypatch):
    artifact = SimpleNamespace(id=uuid.uuid4(), kind="table", payload=payload(900))
    authorized, repo = route_mocks(monkeypatch, artifact)
    job_id, context = uuid.uuid4(), (SimpleNamespace(id=ORG), None)
    first = await router.list_table_rows(
        job_id, artifact.id, "amount", True, "", None, 200,
        context=context, session=object(), settings=SETTINGS,
    )
    second = await router.list_table_rows(
        job_id, artifact.id, "amount", True, "", first.next_cursor, 200,
        context=context, session=object(), settings=SETTINGS,
    )
    view = TableView(sort="amount", descending=True)
    expected = table_view_rows(COLUMNS, artifact.payload["rows"], view)
    assert first.rows + second.rows == expected[:400]
    assert authorized.await_count == 2 and repo.artifact_kind_for_job.await_count == 2
    repo.artifact_payload.assert_awaited_once()


def test_cache_evicts_least_recently_used_tables_and_their_views():
    cache = StoredTableCache(max_tables=2, max_views=3)
    ids = [uuid.uuid4() for _ in range(3)]
    tables = [stored_table(payload(5)) for _ in ids]
    cache.put(ids[0], tables[0])
    cache.put(ids[1], tables[1])
    sorted_first = cache.view_rows(ids[0], tables[0], TableView(sort="amount"))
    assert cache.view_rows(ids[0], tables[0], TableView(sort="amount")) is sorted_first
    assert cache.get(ids[0]) is tables[0]  # now most recently used
    cache.put(ids[2], tables[2])
    assert cache.get(ids[1]) is None and cache.get(ids[0]) is tables[0]
    cache.put(ids[1], tables[1])
    assert list(cache._tables) == [ids[0], ids[1]]  # ids[2] was least recently used
    # Views never outlive their table, and an uncached table's view is computed but not kept.
    assert {key[0] for key in cache._views} <= {ids[0], ids[1]}
    loose = cache.view_rows(uuid.uuid4(), tables[0], TableView(search="ref-1"))
    assert loose == table_view_rows(COLUMNS, tables[0].rows, TableView(search="ref-1"))
    assert len(cache._views) <= 3
