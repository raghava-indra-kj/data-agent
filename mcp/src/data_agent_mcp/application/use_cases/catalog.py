import concurrent.futures
import hashlib
import json
from collections import Counter
from dataclasses import asdict
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from uuid import UUID

from data_agent_mcp.application.ports.credentials import (
    CredentialResolutionError,
    CredentialResolver,
)
from data_agent_mcp.application.ports.data_sources import DataSourceRepository
from data_agent_mcp.application.ports.product import DatabaseReader, ProductStore
from data_agent_mcp.domain.data_sources.models import (
    DatabaseEngine,
    DataSource,
    TableIdentifier,
    UsernamePasswordAuthentication,
)
from data_agent_mcp.domain.queries import OperationError
from data_agent_mcp.domain.settings import RuntimeSettings


def failure(exc: OperationError) -> dict:
    return {"success": False, "code": exc.code, "message": str(exc), "diagnostics": exc.diagnostics}


def limit(value: int | None, default: int, ceiling: int, name: str) -> int:
    chosen = default if value is None else value
    if type(chosen) is not int or not 1 <= chosen <= ceiling:
        raise OperationError(
            "INVALID_LIMIT", f"{name} must be between 1 and the configured ceiling {ceiling}."
        )
    return chosen


def batch(values: list, maximum: int):
    if not values or len(values) > maximum:
        raise OperationError(
            "INVALID_BATCH", f"Supply between 1 and {maximum} items, as configured by the owner."
        )


def fingerprint(source: DataSource) -> str:
    return hashlib.sha256(
        json.dumps(asdict(source), default=str, sort_keys=True).encode()
    ).hexdigest()


def age_seconds(timestamp: str) -> float:
    return (datetime.now(UTC) - datetime.fromisoformat(timestamp)).total_seconds()


class SourceService:
    def __init__(
        self,
        repository: DataSourceRepository,
        credentials: CredentialResolver,
        readers: dict[DatabaseEngine, DatabaseReader],
        settings: RuntimeSettings,
    ):
        self.repository, self.credentials, self.readers, self.settings = (
            repository,
            credentials,
            readers,
            settings,
        )

    def resolve(self, identifier: str):
        try:
            source = self.repository.get(UUID(identifier))
        except ValueError:
            raise OperationError("INVALID_SOURCE_ID", "Source ID must be a UUID.") from None
        if not source:
            raise OperationError("SOURCE_NOT_FOUND", "No source with this ID is configured.")
        if not source.enabled:
            raise OperationError("SOURCE_DISABLED", "This data source is disabled.")
        reader = self.readers.get(source.engine)
        if reader is None:
            raise OperationError("UNSUPPORTED_ENGINE", "This release implements MSSQL only.")
        try:
            password = (
                self.credentials.resolve(source.authentication.password_reference)
                if isinstance(source.authentication, UsernamePasswordAuthentication)
                else None
            )
        except CredentialResolutionError:
            raise OperationError(
                "CREDENTIAL_UNAVAILABLE", "The configured password reference could not be resolved."
            ) from None
        return source, password, reader

    def accessible_ids(self, include_disabled=False):
        return [
            str(s.id)
            for s in self.repository.list_all()
            if (include_disabled or s.enabled) and s.engine in self.readers
        ]

    def permitted_scope(self, scope, include_disabled=False):
        if scope.level == "global":
            return True
        source = next(
            (s for s in self.repository.list_all() if str(s.id) == scope.data_source_id), None
        )
        return bool(
            source
            and (include_disabled or source.enabled)
            and (
                scope.level == "source"
                or source.access_scope.permits(TableIdentifier(scope.schema_name, scope.table_name))
            )
        )

    @staticmethod
    def summary(source):
        return {
            "id": str(source.id),
            "name": source.name,
            "description": source.description,
            "engine": source.engine.value,
            "enabled": source.enabled,
            "revision": source.revision,
            "authentication_method": source.authentication.method.value,
            "server": source.connection.server,
            "database": source.connection.database,
            "allowed_schemas": list(source.access_scope.allowed_schemas),
            "allowed_tables": [
                {"schema_name": t.schema, "table_name": t.name}
                for t in source.access_scope.allowed_tables
            ],
        }

    def list(self, search="", include_disabled=False, offset=0, page_size=None):
        size = limit(
            page_size, self.settings.page_default_size, self.settings.page_max_size, "page_size"
        )
        if offset < 0:
            raise OperationError("INVALID_OFFSET", "Offset must be non-negative.")
        values = [
            s
            for s in self.repository.list_all()
            if (include_disabled or s.enabled)
            and (
                not search
                or search.casefold()
                in (s.name + " " + s.description + " " + s.connection.database).casefold()
            )
        ]
        values.sort(key=lambda s: (s.name, str(s.id)))
        return {
            "sources": [self.summary(s) for s in values[offset : offset + size]],
            "total": len(values),
            "next_offset": offset + size if offset + size < len(values) else None,
            "limits": asdict(self.settings),
        }

    def configure(self, source, expected_revision):
        if source.engine != DatabaseEngine.MSSQL:
            raise OperationError(
                "UNSUPPORTED_ENGINE", "MySQL and PostgreSQL adapters are not implemented yet."
            )
        saved = self.repository.save(source, expected_revision)
        return {"source": self.summary(saved), "connected": False}


class CatalogService:
    def __init__(self, sources: SourceService, store: ProductStore, settings: RuntimeSettings):
        self.sources, self.store, self.settings = sources, store, settings

    def list_tables(self, source_ids, search="", offset=0, page_size=None):
        batch(source_ids, self.settings.source_batch_size)
        size = limit(
            page_size, self.settings.page_default_size, self.settings.page_max_size, "page_size"
        )
        if offset < 0 or len(search) > 200:
            raise OperationError(
                "INVALID_FILTER", "Use a non-negative offset and a short table search."
            )
        results = []
        for identifier in source_ids:
            try:
                source, password, reader = self.sources.resolve(identifier)
                result = reader.list_tables(source, password, search, offset, size)
                results.append({"success": True, "data_source_id": identifier, **result})
            except OperationError as exc:
                results.append({"data_source_id": identifier, **failure(exc)})
        return {"results": results}

    def table_source(self, table):
        source, password, reader = self.sources.resolve(table.data_source_id)
        if not source.permits(TableIdentifier(table.schema_name, table.table_name)):
            raise OperationError(
                "TABLE_NOT_ALLOWED", "The requested table is outside the configured access scope."
            )
        return source, password, reader

    def schema(self, table, refresh=False):
        source, password, reader = self.table_source(table)
        key = "schema:" + table.key
        mark = fingerprint(source)
        cached = self.store.get_profile(key, mark)
        if (
            cached
            and not refresh
            and age_seconds(cached["observed_at"]) < self.settings.schema_cache_seconds
        ):
            return dict(cached, from_cache=True)
        value = reader.schema(source, password, table)
        self.store.put_profile(key, mark, value)
        return dict(value, from_cache=False)

    def schemas(self, tables, refresh=False):
        batch(tables, self.settings.table_batch_size)
        results = []
        for table in tables:
            try:
                results.append({"success": True, **self.schema(table, refresh)})
            except OperationError as exc:
                results.append({**asdict(table), **failure(exc)})
        return {"results": results}

    def profile(self, table, columns=None, sample_rows=None, refresh=False):
        source, password, reader = self.table_source(table)
        requested = limit(
            sample_rows,
            self.settings.profile_default_sample_rows,
            self.settings.profile_max_sample_rows,
            "sample_rows",
        )
        schema = self.schema(table)
        candidates = {
            c["name"]: c
            for c in schema["columns"]
            if c["type"].lower()
            not in {
                "image",
                "text",
                "ntext",
                "xml",
                "geography",
                "geometry",
                "hierarchyid",
                "varbinary",
                "binary",
            }
            and c["max_length_bytes"] != -1
        }
        selected = columns or list(candidates)[: self.settings.profile_max_columns]
        batch(selected, self.settings.profile_max_columns)
        if len(set(selected)) != len(selected) or any(c not in candidates for c in selected):
            raise OperationError(
                "INVALID_COLUMNS", "Use unique supported, non-LOB columns from the table schema."
            )
        mark = (
            fingerprint(source)
            + ":"
            + hashlib.sha256(
                json.dumps([selected, requested, schema["columns"]], sort_keys=True).encode()
            ).hexdigest()
        )
        key = (
            "profile:"
            + table.key
            + ":"
            + hashlib.sha256(json.dumps([selected, requested]).encode()).hexdigest()
        )
        cached = self.store.get_profile(key, mark)
        if cached and not refresh:
            return dict(
                cached,
                from_cache=True,
                stale=age_seconds(cached["observed_at"]) > self.settings.profile_cache_seconds,
            )
        sample = reader.sample(source, password, table, selected, requested)
        summaries = []
        numeric = {
            "tinyint",
            "smallint",
            "int",
            "bigint",
            "decimal",
            "numeric",
            "money",
            "smallmoney",
            "real",
            "float",
        }
        dates = {"date", "datetime", "datetime2", "smalldatetime", "datetimeoffset", "time"}
        for index, name in enumerate(selected):
            values = [row[index] for row in sample["rows"]]
            present = [v for v in values if v is not None]
            representations = [json.dumps(v, sort_keys=True, ensure_ascii=False) for v in present]
            counts = Counter(representations)
            top = [
                {
                    "value": json.loads(v)
                    if len(v) <= self.settings.profile_value_max_characters
                    else v[: self.settings.profile_value_max_characters],
                    "sample_count": count,
                    "value_truncated": len(v) > self.settings.profile_value_max_characters,
                }
                for v, count in counts.most_common(self.settings.profile_top_values)
            ]
            minimum, maximum = None, None
            type_name = candidates[name]["type"].lower()
            if present and type_name in numeric:
                try:
                    numbers = [Decimal(str(v)) for v in present]
                    numbers = [v for v in numbers if v.is_finite()]
                    if numbers:
                        minimum, maximum = str(min(numbers)), str(max(numbers))
                except (ValueError, InvalidOperation):
                    pass
            elif present and type_name in dates:
                minimum, maximum = min(str(v) for v in present), max(str(v) for v in present)
            summaries.append(
                {
                    "column": name,
                    "type": type_name,
                    "sample_null_count": len(values) - len(present),
                    "sample_distinct_count": len(counts),
                    "observed_top_values": top,
                    "observed_min": minimum,
                    "observed_max": maximum,
                    "complete_enum": False,
                }
            )
        value = {
            **asdict(table),
            "columns": summaries,
            "sample_rows": sample["sample_rows"],
            "sample_limit": requested,
            "sampling_method": sample["sampling_method"],
            "truncated": sample["truncated"],
            "observed_at": sample["observed_at"],
            "scope": "sample only; counts, categories and ranges do not describe every row",
            "schema_column_count": len(schema["columns"]),
            "profiled_column_count": len(selected),
        }
        self.store.put_profile(key, mark, value)
        return dict(value, from_cache=False, stale=False)

    def profiles(self, tables, columns=None, sample_rows=None, refresh=False):
        batch(tables, self.settings.table_batch_size)
        results = []
        for table in tables:
            try:
                results.append(
                    {"success": True, **self.profile(table, columns, sample_rows, refresh)}
                )
            except OperationError as exc:
                results.append({**asdict(table), **failure(exc)})
        return {"results": results}


class QueryService:
    def __init__(self, sources: SourceService, settings: RuntimeSettings):
        self.sources, self.settings = sources, settings

    def _execute_single(self, request, per_query_budget):
        try:
            source, password, reader = self.sources.resolve(request["data_source_id"])
            max_rows = limit(
                request.get("max_rows"),
                self.settings.query_default_max_rows,
                self.settings.query_max_rows,
                "max_rows",
            )
            timeout = limit(
                request.get("timeout_seconds"),
                min(
                    self.settings.query_timeout_seconds, source.connection.query_timeout_seconds
                ),
                min(
                    self.settings.query_timeout_seconds, source.connection.query_timeout_seconds
                ),
                "timeout_seconds",
            )
            result = reader.query(
                source,
                password,
                request["sql"],
                request.get("parameters", []),
                max_rows,
                per_query_budget,
                timeout,
            )
            return {"success": True, **result}
        except OperationError as exc:
            return {"data_source_id": request["data_source_id"], **failure(exc)}

    def execute(self, requests):
        batch(requests, self.settings.query_batch_size)
        # Leave room for the MCP envelope and success fields surrounding each result.
        per_query_budget = max(
            1, (self.settings.response_max_bytes - 128 - 32 * len(requests)) // len(requests)
        )
        if len(requests) <= 1 or self.settings.database_concurrency <= 1:
            return {
                "results": [
                    self._execute_single(request, per_query_budget) for request in requests
                ]
            }

        workers = min(len(requests), self.settings.database_concurrency)
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [
                executor.submit(self._execute_single, request, per_query_budget)
                for request in requests
            ]
            results = [f.result() for f in futures]
        return {"results": results}
