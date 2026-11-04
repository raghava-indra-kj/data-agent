from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Import ORM models so Alembic/application metadata is complete.
from app.agent import models as agent_models  # noqa: F401
from app.agent.router import router as agent_router
from app.auth import models as auth_models  # noqa: F401
from app.audit import models as audit_models  # noqa: F401
from app.audit.router import router as audit_router
from app.auth.router import router as auth_router
from app.conversations import models as conversation_models  # noqa: F401
from app.conversations.router import router as conversations_router
from app.data_sources import models as data_source_models  # noqa: F401
from app.data_sources.router import router as data_sources_router
from app.core.config import get_settings
from app.core.database import close_database
from app.core.errors import install_exception_handlers
from app.core.logging import configure_logging
from app.core.listener import close_listener, get_listener
from app.core.request_id import RequestIdMiddleware
from app.health import router as health_router
from app.exports.router import router as exports_router
from app.instructions import models as instruction_models  # noqa: F401
from app.instructions.router import router as instructions_router
from app.jobs import models as job_models  # noqa: F401
from app.knowledge import models as knowledge_models  # noqa: F401
from app.knowledge.router import router as knowledge_router
from app.jobs.router import router as jobs_router
from app.models import models as model_config_models  # noqa: F401
from app.models.router import router as models_router
from app.organizations import models as organization_models  # noqa: F401
from app.organizations.router import router as organizations_router
from app.operations.router import router as operations_router
from app.reporting import models as reporting_models  # noqa: F401
from app.reporting.router import router as reporting_router
from app.power_bi import models as power_bi_models  # noqa: F401
from app.power_bi.router import router as power_bi_router


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        # One connection per process feeds every live job-event stream.
        await get_listener().start()
        yield
        await close_listener()
        await close_database()

    app = FastAPI(title=settings.app_name, version="0.6.0", lifespan=lifespan)
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    install_exception_handlers(app)
    app.include_router(health_router)
    app.include_router(auth_router, prefix=settings.api_v1_prefix)
    app.include_router(organizations_router, prefix=settings.api_v1_prefix)
    app.include_router(power_bi_router, prefix=settings.api_v1_prefix)
    app.include_router(data_sources_router, prefix=settings.api_v1_prefix)
    app.include_router(instructions_router, prefix=settings.api_v1_prefix)
    app.include_router(models_router, prefix=settings.api_v1_prefix)
    app.include_router(knowledge_router, prefix=settings.api_v1_prefix)
    app.include_router(conversations_router, prefix=settings.api_v1_prefix)
    app.include_router(jobs_router, prefix=settings.api_v1_prefix)
    app.include_router(agent_router, prefix=settings.api_v1_prefix)
    app.include_router(exports_router, prefix=settings.api_v1_prefix)
    app.include_router(reporting_router, prefix=settings.api_v1_prefix)
    app.include_router(audit_router, prefix=settings.api_v1_prefix)
    app.include_router(operations_router, prefix=settings.api_v1_prefix)
    return app


app = create_app()
