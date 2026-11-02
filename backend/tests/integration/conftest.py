from __future__ import annotations

import os
import subprocess
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio

pytest.importorskip("asyncpg", reason="Install project dependencies to run integration tests")
pytest.importorskip("duckdb", reason="Install Task 2 dependencies to run integration tests")

if os.getenv("RUN_INTEGRATION_TESTS") != "1":
    pytest.skip(
        "Set RUN_INTEGRATION_TESTS=1 with PostgreSQL running to execute integration tests",
        allow_module_level=True,
    )

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://dbassistant:dbassistant@localhost:12202/dbassistant"
)
os.environ.setdefault("JWT_SECRET", "integration-test-secret-that-is-long-enough-123456789")
os.environ.setdefault("DATA_DIRECTORY", "/tmp/dbassistant-task6-integration")

from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.database import close_database, get_session_factory  # noqa: E402
from app.core.listener import close_listener  # noqa: E402
from app.main import create_app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def migrated_database() -> None:
    get_settings.cache_clear()
    subprocess.run(["alembic", "upgrade", "head"], check=True)


@pytest_asyncio.fixture(autouse=True)
async def clean_state() -> AsyncIterator[None]:
    session_factory = get_session_factory()
    async with session_factory() as session:
        await session.execute(
            text(
                "TRUNCATE TABLE audit_logs, dashboard_widgets, dashboards, job_artifacts, model_executions, sql_executions, tool_executions, messages, conversation_data_sources, conversations, "
                "knowledge_annotations, knowledge_documents, knowledge_versions, knowledge_bases, model_profiles, model_connections, data_source_files, data_sources, encrypted_secrets, "
                "job_events, jobs, auth_action_tokens, auth_sessions, organization_memberships, organizations, users RESTART IDENTITY CASCADE"
            )
        )
        await session.commit()
    # Truncating jobs and job_events clears the queue too: the rows are the queue.
    import shutil
    shutil.rmtree("/tmp/dbassistant-task6-integration", ignore_errors=True)
    yield
    await close_listener()
    await close_database()
    import shutil
    shutil.rmtree("/tmp/dbassistant-task6-integration", ignore_errors=True)


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    app = create_app()
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as http:
            yield http
