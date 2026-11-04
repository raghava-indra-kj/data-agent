from __future__ import annotations

import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.agent import router as router_module
from app.core.config import Settings
from app.core.errors import AppError


class FakeArtifactRepository:
    artifact = None

    def __init__(self, _session) -> None:
        pass

    async def get_artifact_for_job(self, _job_id, _artifact_id):
        return self.artifact


@pytest.mark.asyncio
async def test_html_artifact_route_serves_public_preview_with_browser_limits(
    tmp_path, monkeypatch
) -> None:
    job_id = uuid.uuid4()
    artifact_id = uuid.uuid4()
    target = tmp_path / "html-artifacts" / job_id.hex / artifact_id.hex / "index.html"
    target.parent.mkdir(parents=True)
    target.write_text("<html><body>Report</body></html>", encoding="utf-8")
    FakeArtifactRepository.artifact = SimpleNamespace(
        kind="html",
        payload={"schema_version": 1, "file_name": "index.html", "size_bytes": 32},
    )
    monkeypatch.setattr(router_module, "AgentExecutionRepository", FakeArtifactRepository)

    response = await router_module.get_html_artifact(
        job_id,
        artifact_id,
        session=SimpleNamespace(get=AsyncMock(return_value=None)),
        settings=Settings(app_env="test", data_directory=tmp_path),
    )

    assert Path(response.path) == target
    assert response.media_type == "text/html; charset=utf-8"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "default-src 'none'" in response.headers["content-security-policy"]


@pytest.mark.asyncio
async def test_html_artifact_route_returns_not_found_for_other_artifact_kinds(
    tmp_path, monkeypatch
) -> None:
    FakeArtifactRepository.artifact = SimpleNamespace(kind="table", payload={})
    monkeypatch.setattr(router_module, "AgentExecutionRepository", FakeArtifactRepository)

    with pytest.raises(AppError) as error:
        await router_module.get_html_artifact(
            uuid.uuid4(),
            uuid.uuid4(),
            session=SimpleNamespace(get=AsyncMock(return_value=None)),
            settings=Settings(app_env="test", data_directory=tmp_path),
        )
    assert error.value.status_code == 404
