from __future__ import annotations

import asyncio
import json

from app.core.config import get_settings
from app.core.database import close_database, get_session_factory
from app.maintenance.service import MaintenanceService


async def main() -> None:
    settings = get_settings()
    try:
        async with get_session_factory()() as session:
            result = await MaintenanceService(session, settings).run_once()
        print(json.dumps(result, sort_keys=True))
    finally:
        await close_database()


if __name__ == "__main__":
    asyncio.run(main())
