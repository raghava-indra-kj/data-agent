from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path

from app.agent.deep_agent import SYSTEM_PROMPT
from app.core.config import Settings
from app.maintenance.service import MaintenanceService
from app.reporting.jobs import _chart_args
from app.reporting.schemas import DashboardCreate, DashboardWidgetCreate


def test_task6_dashboard_contracts_and_chart_config() -> None:
    dashboard = DashboardCreate(title="  Executive KPIs  ")
    assert dashboard.title == "Executive KPIs"
    request = DashboardWidgetCreate(
        source_job_id="00000000-0000-0000-0000-000000000001",
        source_sql_execution_id="00000000-0000-0000-0000-000000000002",
        widget_type="line",
        visualization_config={
            "x_field": "month",
            "series": [{"field": "revenue", "label": "Revenue"}],
        },
    )
    parsed = _chart_args(
        request.widget_type,
        "Monthly revenue",
        request.source_sql_execution_id,
        request.visualization_config,
    )
    assert parsed.chart_type == "line"
    assert parsed.x_field == "month"
    assert parsed.series[0].field == "revenue"


def test_task6_uses_current_deepagents_without_todo_assumption() -> None:
    pyproject = Path("pyproject.toml").read_text()
    assert 'deepagents>=0.7.3,<0.8' in pyproject
    assert "planning capability provided by the Deep Agents harness" not in SYSTEM_PROMPT
    assert "multiple steps and multiple SQL queries" in SYSTEM_PROMPT


def test_agent_prompt_assigns_one_owner_to_each_result_set() -> None:
    assert "Choose One Owner for Each Result Set" in SYSTEM_PROMPT
    assert "A result set must have exactly one" in SYSTEM_PROMPT
    assert "primary presentation owner" in SYSTEM_PROMPT
    assert "Never present equivalent rows twice" in SYSTEM_PROMPT
    assert "Multiple tables are allowed" in SYSTEM_PROMPT
    assert "genuinely different" in SYSTEM_PROMPT
    assert 'display="hidden"' in SYSTEM_PROMPT


def test_maintenance_removes_only_old_temp_duckdb_files(tmp_path: Path) -> None:
    old = tmp_path / "old.tmp.duckdb"
    recent = tmp_path / "recent.tmp.duckdb"
    durable = tmp_path / "database.duckdb"
    for path in (old, recent, durable):
        path.write_text("x")
    old_time = time.time() - 48 * 3600
    os.utime(old, (old_time, old_time))

    settings = Settings(data_directory=tmp_path, temporary_file_retention_hours=24)
    service = MaintenanceService(session=None, settings=settings)  # type: ignore[arg-type]
    assert service.cleanup_temporary_files() == 1
    assert not old.exists()
    assert recent.exists()
    assert durable.exists()


def test_worker_concurrency_setting_is_bounded() -> None:
    settings = Settings(worker_concurrency=6)
    assert settings.worker_concurrency == 6
    assert settings.max_active_jobs_per_user > 0
    assert settings.max_active_jobs_per_organization >= settings.max_active_jobs_per_user
