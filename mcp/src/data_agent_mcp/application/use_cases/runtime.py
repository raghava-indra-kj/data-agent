import json
from dataclasses import dataclass

from data_agent_mcp.application.ports.credentials import CredentialResolutionError
from data_agent_mcp.application.ports.data_sources import ConfigurationError
from data_agent_mcp.application.ports.product import RuntimeLease
from data_agent_mcp.application.use_cases.catalog import (
    CatalogService,
    QueryService,
    SourceService,
    failure,
)
from data_agent_mcp.application.use_cases.knowledge import KnowledgeService
from data_agent_mcp.application.use_cases.refresh import (
    JobCoordinator,
    RefreshService,
    ScheduleService,
)
from data_agent_mcp.domain.queries import OperationError
from data_agent_mcp.domain.settings import RuntimeSettings


@dataclass
class PluginServices:
    settings: RuntimeSettings
    sources: SourceService
    catalog: CatalogService
    knowledge: KnowledgeService
    queries: QueryService
    jobs: JobCoordinator
    refresh: RefreshService
    schedules: ScheduleService
    lease: RuntimeLease | None = None

    def invoke(self, operation, *args, _mutation=False, **kwargs):
        try:
            result = {"success": True, **operation(*args, **kwargs)}
        except OperationError as exc:
            result = failure(exc)
        except ConfigurationError as exc:
            result = failure(OperationError("INVALID_CONFIGURATION", str(exc)))
        except CredentialResolutionError as exc:
            result = failure(OperationError("CREDENTIAL_UNAVAILABLE", str(exc)))
        except (ValueError, TypeError):
            result = failure(
                OperationError(
                    "INVALID_ARGUMENTS",
                    "Arguments failed domain validation. Check UUIDs, required fields, scopes and configured limits.",
                )
            )
        except Exception:
            result = failure(
                OperationError(
                    "INTERNAL_ERROR",
                    "The operation failed unexpectedly. Raw exception details were withheld.",
                )
            )
        return self._bounded(result, _mutation)

    def _bounded(self, result, mutation):
        def size(value):
            return len(json.dumps(value, ensure_ascii=False, default=str).encode("utf-8"))

        if size(result) <= self.settings.response_max_bytes:
            return result
        if not result.get("success"):
            return {
                "success": False,
                "code": result.get("code", "OPERATION_FAILED"),
                "message": "Error details exceed the configured response budget. Increase response_max_bytes.",
                "response_truncated": True,
            }
        if not mutation:
            return {
                "success": False,
                "code": "RESPONSE_SIZE_LIMIT",
                "message": "Request fewer items or increase response_max_bytes.",
            }
        # A committed write must not look like a failed operation or lose its identity.
        keys = {"id", "job_id", "version", "revision", "enabled", "status", "success", "code"}
        items = result.get(
            "results",
            [result.get("source") or result.get("knowledge") or result.get("schedule") or result],
        )
        receipt = {
            "success": True,
            "response_truncated": True,
            "message": "Operation completed. Retrieve full state with list/get tools.",
            "receipts": [],
        }
        for item in items:
            value = {key: value for key, value in item.items() if key in keys}
            receipt["receipts"].append(value)
            if size(receipt) > self.settings.response_max_bytes:
                receipt["receipts"].pop()
                break
        return receipt

    def start(self):
        has_lease = False
        if self.lease:
            try:
                self.lease.acquire()
                has_lease = True
            except OperationError as error:
                if error.code == "SERVER_ALREADY_RUNNING":
                    has_lease = False
                else:
                    raise
        if has_lease:
            try:
                self.jobs.start()
                self.schedules.start()
            except Exception:
                if self.lease:
                    self.lease.release()
                raise

    def stop(self):
        try:
            self.schedules.stop()
            self.jobs.stop()
        finally:
            if self.lease:
                self.lease.release()
