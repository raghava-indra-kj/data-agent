from __future__ import annotations

import asyncio
import logging
import sys

from app.agent import models as agent_models  # noqa: F401
from app.agent.checkpoints import close_checkpointer, open_checkpointer
from app.agent.jobs import register_agent_handlers
from app.auth import models as auth_models  # noqa: F401
from app.audit import models as audit_models  # noqa: F401
from app.conversations import models as conversation_models  # noqa: F401
from app.core.config import get_settings
from app.core.database import close_database
from app.core.logging import configure_logging
from app.core.listener import close_listener
from app.data_sources import models as data_source_models  # noqa: F401
from app.data_sources.jobs import register_data_source_handlers
from app.jobs import models as job_models  # noqa: F401
from app.jobs.handlers import registry
from app.knowledge import models as knowledge_models  # noqa: F401
from app.knowledge.jobs import register_knowledge_handlers
from app.models import models as model_config_models  # noqa: F401
from app.organizations import models as organization_models  # noqa: F401
from app.power_bi import models as power_bi_models  # noqa: F401
from app.reporting import models as reporting_models  # noqa: F401
from app.reporting.jobs import register_reporting_handlers
from app.jobs.worker import Worker


async def main() -> None:
    settings = get_settings()
    configure_logging(settings)
    register_data_source_handlers(registry)
    register_knowledge_handlers(registry)
    register_agent_handlers(registry)
    register_reporting_handlers(registry)
    try:
        await open_checkpointer(settings)
    except Exception:
        # Analyses still run; clarifying questions then end the turn instead of pausing it.
        logging.getLogger(__name__).exception("checkpointer_unavailable")
    worker = Worker(settings, registry)
    try:
        await worker.run()
    finally:
        await close_checkpointer()
        await close_listener()
        await close_database()


if __name__ == "__main__":
    # psycopg's async driver (used by the LangGraph checkpointer) needs a selector event loop;
    # Windows defaults to the proactor loop. Nothing in the worker needs asyncio subprocesses.
    loop_factory = asyncio.SelectorEventLoop if sys.platform == "win32" else None
    asyncio.run(main(), loop_factory=loop_factory)
