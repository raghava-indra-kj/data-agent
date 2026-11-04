from __future__ import annotations

import logging
import time
from datetime import timedelta
from pathlib import Path

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.checkpoints import delete_job_checkpoints
from app.auth.models import AuthActionToken, AuthSession
from app.core.config import Settings
from app.core.time import utc_now
from app.jobs.service import JobService
from app.power_bi.models import MicrosoftAuthTransaction
from app.secrets.models import EncryptedSecret

logger = logging.getLogger(__name__)


class MaintenanceService:
    """Explicit cleanup/recovery entry point suitable for cron/systemd/Kubernetes later."""

    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings

    async def run_once(self) -> dict[str, int]:
        auth_rows = await self.cleanup_expired_auth()
        stale_jobs = await self.requeue_abandoned_jobs()
        expired = await self.expire_unanswered_questions()
        temp_files = self.cleanup_temporary_files()
        return {
            "expired_auth_rows_deleted": auth_rows,
            "abandoned_jobs_requeued": stale_jobs,
            "unanswered_questions_expired": expired,
            "temporary_files_deleted": temp_files,
        }

    async def cleanup_expired_auth(self) -> int:
        cutoff = utc_now() - timedelta(days=self.settings.auth_expired_retention_days)
        sessions = await self.session.execute(
            delete(AuthSession).where(AuthSession.expires_at < cutoff)
        )
        tokens = await self.session.execute(
            delete(AuthActionToken).where(AuthActionToken.expires_at < cutoff)
        )
        expired_power_bi = list(await self.session.scalars(
            delete(MicrosoftAuthTransaction)
            .where(MicrosoftAuthTransaction.expires_at < utc_now())
            .returning(MicrosoftAuthTransaction.secret_id)
        ))
        if expired_power_bi:
            await self.session.execute(delete(EncryptedSecret).where(
                EncryptedSecret.id.in_(expired_power_bi),
                EncryptedSecret.purpose == "power_bi_oauth_transaction",
            ))
        await self.session.commit()
        return int(sessions.rowcount or 0) + int(tokens.rowcount or 0) + len(expired_power_bi)  # type: ignore[attr-defined]

    async def requeue_abandoned_jobs(self) -> int:
        before = utc_now() - timedelta(seconds=self.settings.stale_job_grace_seconds)
        return await JobService(self.session, self.settings).recover_abandoned_jobs(
            before=before, limit=100
        )

    async def expire_unanswered_questions(self) -> int:
        expired = await JobService(self.session, self.settings).expire_waiting_jobs()
        await delete_job_checkpoints(self.session, expired)
        return len(expired)

    def cleanup_temporary_files(self) -> int:
        root = self.settings.data_directory.expanduser().resolve()
        if not root.exists():
            return 0
        cutoff = time.time() - self.settings.temporary_file_retention_hours * 3600
        removed = 0
        for path in root.rglob("*.tmp.duckdb"):
            try:
                if path.is_file() and path.stat().st_mtime < cutoff:
                    path.unlink(missing_ok=True)
                    removed += 1
            except OSError:
                logger.warning("temporary_file_cleanup_failed", extra={"path": str(path)})
        return removed
