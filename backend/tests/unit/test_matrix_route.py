from __future__ import annotations

import uuid
from io import BytesIO, StringIO
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from openpyxl import load_workbook

from app.agent import router
from app.agent.matrix import MatrixViewState, build_matrix, validate_stored_matrix
from app.core.config import Settings
from app.core.errors import AppError
from tests.unit.test_matrix import example


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [None, "forbidden", "missing", "tampered", "bad_state"])
async def test_export_checks_org_and_source_before_exporting(monkeypatch, failure):
    spec, columns, rows = example()
    job_id, org_id, artifact_id, source_id = [uuid.uuid4() for _ in range(4)]
    payload = build_matrix(spec, columns, rows)
    if failure == "tampered":
        payload["cells"][0]["values"][0] = "999"
    artifact = SimpleNamespace(
        kind="matrix", source_sql_execution_id=spec.sql_execution_id, payload=payload
    )
    source = SimpleNamespace(
        id=spec.sql_execution_id,
        status="succeeded",
        columns=columns,
        row_count=len(rows),
        data_source_id=source_id,
        truncated=False,
    )
    table = SimpleNamespace(
        payload={
            "schema_version": 1,
            "columns": columns,
            "rows": rows,
            "row_count": len(rows),
            "data_source_id": str(source_id),
            "truncated": False,
        }
    )
    repo = SimpleNamespace(
        get_artifact_for_job=AsyncMock(return_value=None if failure == "missing" else artifact),
        get_sql_for_job=AsyncMock(return_value=source),
        get_table_artifact_for_sql=AsyncMock(return_value=table),
    )
    authorized = AsyncMock()
    if failure == "forbidden":
        authorized.side_effect = AppError("NOT_FOUND", "Not found", 404)
    monkeypatch.setattr(router, "AgentExecutionRepository", lambda _: repo)
    monkeypatch.setattr(router, "JobService", lambda *_: SimpleNamespace(get_for_org=authorized))
    state = (
        MatrixViewState(collapsed_rows=["r" + "0" * 24])
        if failure == "bad_state"
        else MatrixViewState()
    )
    args = dict(
        job_id=job_id,
        artifact_id=artifact_id,
        state=state,
        context=(SimpleNamespace(id=org_id), None),
        session=object(),
        settings=Settings(),
    )
    if failure:
        with pytest.raises(AppError) as error:
            await router.export_matrix(**args)
        assert error.value.status_code in (404, 422)
        if failure == "forbidden":
            repo.get_artifact_for_job.assert_not_awaited()
    else:
        result = await router.export_matrix(**args)
        assert result.headers["cache-control"] == "no-store"
        assert load_workbook(BytesIO(result.body)).active.freeze_panes == "B3"
    authorized.assert_awaited_once_with(job_id, org_id)


def test_persisted_matrix_must_equal_a_rebuild_from_sql_evidence():
    spec, columns, rows = example()
    payload = build_matrix(spec, columns, rows)
    table = {"columns": columns, "rows": rows}
    assert validate_stored_matrix(payload, spec.sql_execution_id, table, truncated=False)
    assert not validate_stored_matrix(payload, uuid.uuid4(), table, truncated=False)
    assert not validate_stored_matrix(payload, spec.sql_execution_id, table, truncated=True)
    payload["cells"][0]["values"][0] = "12345"
    assert not validate_stored_matrix(payload, spec.sql_execution_id, table, truncated=False)


def test_matrix_migration_adds_kind_and_protects_durable_history():
    import importlib.util
    from pathlib import Path

    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    from app.core.database import Base

    spec = importlib.util.spec_from_file_location(
        "matrix_migration", Path("migrations/versions/0015_matrix_artifact.py")
    )
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    for direction in ("upgrade", "downgrade"):
        output = StringIO()
        context = MigrationContext.configure(
            dialect_name="postgresql",
            opts={
                "as_sql": True,
                "output_buffer": output,
                "target_metadata": Base.metadata,
            },
        )
        with Operations.context(context):
            getattr(migration, direction)()
        sql = output.getvalue()
        assert "ADD CONSTRAINT ck_job_artifacts_valid_kind" in sql
        if direction == "upgrade":
            assert "'matrix'" in sql
        else:
            assert "RAISE EXCEPTION" in sql
