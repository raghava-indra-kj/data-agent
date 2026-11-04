from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.agent import models as agent_models  # noqa: F401
from app.auth import models as auth_models  # noqa: F401
from app.audit import models as audit_models  # noqa: F401
from app.conversations import models as conversation_models  # noqa: F401
from app.core.config import get_settings
from app.data_sources import models as data_source_models  # noqa: F401
from app.core.database import Base
from app.instructions import models as instruction_models  # noqa: F401
from app.jobs import models as jobs_models  # noqa: F401
from app.knowledge import models as knowledge_models  # noqa: F401
from app.models import models as model_config_models  # noqa: F401
from app.organizations import models as org_models  # noqa: F401
from app.reporting import models as reporting_models  # noqa: F401
from app.power_bi import models as power_bi_models  # noqa: F401

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)
config.set_main_option("sqlalchemy.url", get_settings().database_url)
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:  # type: ignore[no-untyped-def]
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
