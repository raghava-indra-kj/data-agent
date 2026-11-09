import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from data_agent_mcp.application.ports.product import ProductStore
from data_agent_mcp.application.use_cases.catalog import (
    CatalogService,
    batch,
    failure,
    fingerprint,
    limit,
)
from data_agent_mcp.application.use_cases.knowledge import KnowledgeService
from data_agent_mcp.domain.knowledge import KnowledgeScope, utc_now
from data_agent_mcp.domain.queries import OperationError, TableRef
from data_agent_mcp.domain.settings import RuntimeSettings

logger = logging.getLogger(__name__)


class JobCoordinator:
    def __init__(self, store: ProductStore, settings: RuntimeSettings):
        self.store, self.settings = store, settings
        self._pool = ThreadPoolExecutor(
            max_workers=settings.job_workers, thread_name_prefix="data-agent-job"
        )
        self._slots = threading.BoundedSemaphore(settings.job_max_pending)
        self._started = False
        self._stopped = False

    def start(self):
        if not self._started:
            self.store.interrupt_unfinished_jobs()
            self._started = True

    def submit(self, kind, request, operation):
        if self._stopped or not self._slots.acquire(blocking=False):
            raise OperationError(
                "JOB_CAPACITY", "Background job capacity is occupied or the process is stopping."
            )
        try:
            identifier = self.store.create_job(kind, request)
        except Exception:
            self._slots.release()
            raise

        def run():
            try:
                self.store.update_job(identifier, status="running", started_at=utc_now())
                result = operation(identifier)
                statuses = [r.get("success", False) for r in result.get("results", [])]
                status = (
                    "succeeded"
                    if all(statuses)
                    else "partial_failure"
                    if any(statuses)
                    else "failed"
                )
                self.store.update_job(
                    identifier, status=status, result=result, progress=100, finished_at=utc_now()
                )
            except OperationError as exc:
                self.store.update_job(
                    identifier, status="failed", error=failure(exc), finished_at=utc_now()
                )
            except Exception:
                self.store.update_job(
                    identifier,
                    status="failed",
                    error={
                        "code": "INTERNAL_JOB_ERROR",
                        "message": "Background operation failed. Raw exception details were withheld.",
                    },
                    finished_at=utc_now(),
                )
            finally:
                self._slots.release()

        try:
            self._pool.submit(run)
        except Exception:
            self._slots.release()
            self.store.update_job(
                identifier,
                status="failed",
                error={"code": "JOB_SUBMISSION_FAILED"},
                finished_at=utc_now(),
            )
            raise OperationError(
                "JOB_SUBMISSION_FAILED", "Could not submit the background job."
            ) from None
        return {"job_id": identifier, "status": "queued"}

    def get(self, ids):
        batch(ids, self.settings.knowledge_batch_size)
        results = []
        for identifier in ids:
            UUID(identifier)
            value = self.store.get_job(identifier)
            results.append(value or {"id": identifier, "code": "JOB_NOT_FOUND"})
        return {"jobs": results}

    def stop(self):
        self._stopped = True
        self._pool.shutdown(wait=True, cancel_futures=False)


class RefreshService:
    def __init__(
        self,
        catalog: CatalogService,
        knowledge: KnowledgeService,
        jobs: JobCoordinator,
        store: ProductStore,
        settings: RuntimeSettings,
    ):
        self.catalog, self.knowledge, self.jobs, self.store, self.settings = (
            catalog,
            knowledge,
            jobs,
            store,
            settings,
        )

    def submit(self, tables, layers, sample_rows=None, columns=None):
        batch(tables, self.settings.table_batch_size)
        if (
            not layers
            or not set(layers) <= {"schema", "data_profile"}
            or len(layers) != len(set(layers))
        ):
            raise OperationError("INVALID_LAYERS", "Choose schema and/or data_profile once each.")
        # Validate every target before accepting any background work.
        for table in tables:
            self.catalog.table_source(table)
        if sample_rows is not None:
            limit(
                sample_rows,
                self.settings.profile_default_sample_rows,
                self.settings.profile_max_sample_rows,
                "sample_rows",
            )
        if columns is not None:
            batch(columns, self.settings.profile_max_columns)
            if len(set(columns)) != len(columns):
                raise OperationError("INVALID_COLUMNS", "Column names must be unique.")
        request = {
            "tables": [
                {
                    "data_source_id": t.data_source_id,
                    "schema_name": t.schema_name,
                    "table_name": t.table_name,
                }
                for t in tables
            ],
            "layers": layers,
            "sample_rows": sample_rows,
            "columns": columns,
        }

        def refresh(job_id):
            results = []
            total = len(tables) * len(layers)
            for table in tables:
                for layer in layers:
                    try:
                        value = (
                            self.catalog.schema(table, True)
                            if layer == "schema"
                            else self.catalog.profile(table, columns, sample_rows, True)
                        )
                        source, _, _ = self.catalog.table_source(table)
                        provenance = {
                            "origin": "database_metadata"
                            if layer == "schema"
                            else "bounded_database_sample",
                            "observed_at": value["observed_at"],
                            "source_revision": source.revision,
                            "source_fingerprint": fingerprint(source),
                            "sampling": layer == "data_profile",
                        }
                        saved = self.knowledge.generated(
                            f"{layer}:{table.key}",
                            f"{table.schema_name}.{table.table_name}: {layer}",
                            f"{'Structure and constraints' if layer == 'schema' else 'Observed sample values and ranges'} for {table.schema_name}.{table.table_name}.",
                            value,
                            layer,
                            KnowledgeScope(
                                "table", table.data_source_id, table.schema_name, table.table_name
                            ),
                            provenance,
                        )
                        results.append(
                            {"success": True, "table": table.key, "layer": layer, **saved}
                        )
                    except OperationError as exc:
                        results.append({"table": table.key, "layer": layer, **failure(exc)})
                    self.store.update_job(job_id, progress=int(len(results) / total * 100))
            return {"results": results, "raw_rows_persisted": False}

        return self.jobs.submit("knowledge_refresh", request, refresh)


class ScheduleService:
    """Persisted interval schedules; they run only while this MCP process is alive."""

    def __init__(self, store: ProductStore, refresh: RefreshService, settings: RuntimeSettings):
        self.store, self.refresh, self.settings = store, refresh, settings
        self._stop = threading.Event()
        self._thread = None
        self._lock = threading.Lock()

    def list(self, offset=0, page_size=None):
        size = limit(
            page_size, self.settings.page_default_size, self.settings.page_max_size, "page_size"
        )
        if offset < 0:
            raise OperationError("INVALID_OFFSET", "Offset must be non-negative.")
        schedules = self.store.list_schedules()
        return {
            "schedules": schedules[offset : offset + size],
            "total": len(schedules),
            "next_offset": offset + size if offset + size < len(schedules) else None,
            "runs_only_while_server_is_running": True,
        }

    def configure(
        self,
        name,
        tables,
        layers,
        interval_seconds,
        enabled=True,
        identifier=None,
        expected_version=None,
        sample_rows=None,
        columns=None,
    ):
        batch(tables, self.settings.table_batch_size)
        if (
            not name.strip()
            or len(name) > 200
            or interval_seconds < self.settings.schedule_min_interval_seconds
        ):
            raise OperationError(
                "INVALID_SCHEDULE",
                f"Provide a name and an interval of at least {self.settings.schedule_min_interval_seconds} seconds.",
            )
        if (
            not layers
            or not set(layers) <= {"schema", "data_profile"}
            or len(set(layers)) != len(layers)
        ):
            raise OperationError("INVALID_LAYERS", "Choose schema and/or data_profile once each.")
        # Disabling a schedule must remain possible after its source stops working.
        if enabled:
            for table in tables:
                self.refresh.catalog.table_source(table)
        if sample_rows is not None:
            limit(
                sample_rows,
                self.settings.profile_default_sample_rows,
                self.settings.profile_max_sample_rows,
                "sample_rows",
            )
        if columns is not None:
            batch(columns, self.settings.profile_max_columns)
            if len(set(columns)) != len(columns):
                raise OperationError("INVALID_COLUMNS", "Column names must be unique.")
        identifier = identifier or str(uuid4())
        UUID(identifier)
        value = {
            "id": identifier,
            "name": name,
            "tables": [
                {
                    "data_source_id": t.data_source_id,
                    "schema_name": t.schema_name,
                    "table_name": t.table_name,
                }
                for t in tables
            ],
            "layers": layers,
            "interval_seconds": interval_seconds,
            "enabled": enabled,
            "sample_rows": sample_rows,
            "columns": columns,
            "next_run_at": (datetime.now(UTC) + timedelta(seconds=interval_seconds)).isoformat(),
            "last_job_id": None,
            "last_error": None,
        }
        with self._lock:
            current = next((s for s in self.store.list_schedules() if s["id"] == identifier), None)
            if current:
                value["last_job_id"] = current.get("last_job_id")
                value["last_error"] = current.get("last_error")
            saved = self.store.save_schedule(value, expected_version)
        return {"schedule": saved, "runs_only_while_server_is_running": True}

    def tick(self):
        with self._lock:
            for schedule in self.store.list_schedules():
                if not schedule["enabled"] or datetime.fromisoformat(
                    schedule["next_run_at"]
                ) > datetime.now(UTC):
                    continue
                previous = (
                    self.store.get_job(schedule["last_job_id"])
                    if schedule.get("last_job_id")
                    else None
                )
                if previous and previous["status"] in {"queued", "running"}:
                    continue
                try:
                    result = self.refresh.submit(
                        [TableRef(**t) for t in schedule["tables"]],
                        schedule["layers"],
                        schedule.get("sample_rows"),
                        schedule.get("columns"),
                    )
                    schedule.update(last_job_id=result["job_id"], last_error=None)
                except OperationError as exc:
                    schedule["last_error"] = failure(exc)
                schedule["next_run_at"] = (
                    datetime.now(UTC) + timedelta(seconds=schedule["interval_seconds"])
                ).isoformat()
                self.store.save_schedule(schedule, schedule["version"])

    def start(self):
        if self._thread:
            return

        def loop():
            while not self._stop.wait(self.settings.scheduler_poll_seconds):
                try:
                    self.tick()
                except Exception:
                    logger.error("Schedule processing failed; raw exception details withheld.")

        self._thread = threading.Thread(target=loop, name="data-agent-scheduler", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join()
