"""Metadata and bounded SELECT access. No connections are opened at construction."""

import base64
import json
import sys
import threading
from contextlib import contextmanager
from datetime import date, datetime, time
from decimal import Decimal
from time import perf_counter
from uuid import UUID

import pyodbc

from data_agent_mcp.application.ports.database import ConnectionStage
from data_agent_mcp.application.sql_policy import validate_select
from data_agent_mcp.domain.data_sources.models import TableIdentifier, WindowsAuthentication
from data_agent_mcp.domain.knowledge import utc_now
from data_agent_mcp.domain.queries import OperationError
from data_agent_mcp.domain.settings import RuntimeSettings
from data_agent_mcp.infrastructure.databases.mssql.connection_tester import (
    DRIVER,
    _connection_string,
    _driver_diagnostics,
)


def quote(value: str) -> str:
    return "[" + value.replace("]", "]]") + "]"


def json_value(value):
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        import math

        return value if math.isfinite(value) else str(value)
    if isinstance(value, (Decimal, UUID, date, datetime, time)):
        return str(value)
    if isinstance(value, bytes):
        return {"encoding": "base64", "value": base64.b64encode(value).decode("ascii")}
    return str(value)


class MssqlDatabaseReader:
    def __init__(self, connect=None, drivers=None, platform=None, settings=None):
        self.settings = settings or RuntimeSettings()
        self._connect = connect or pyodbc.connect
        self._drivers = drivers or pyodbc.drivers
        self._platform = platform or sys.platform
        self._slots = threading.BoundedSemaphore(self.settings.database_concurrency)

    @contextmanager
    def _session(self, source, password, timeout=None):
        if isinstance(source.authentication, WindowsAuthentication) and self._platform != "win32":
            raise OperationError(
                "WINDOWS_AUTH_REQUIRES_WINDOWS",
                "Windows authentication requires a Windows server process.",
            )
        if DRIVER not in self._drivers():
            raise OperationError("ODBC_DRIVER_NOT_FOUND", f"Install {DRIVER}.")
        if not self._slots.acquire(timeout=self.settings.database_slot_wait_seconds):
            raise OperationError(
                "DATABASE_BUSY", "Database concurrency capacity is occupied. Try again later."
            )
        connection, cursor = None, None
        stage = ConnectionStage.CONNECT
        try:
            connection = self._connect(
                _connection_string(source, password),
                timeout=source.connection.connect_timeout_seconds,
                autocommit=True,
            )
            connection.timeout = min(
                timeout or self.settings.query_timeout_seconds,
                source.connection.query_timeout_seconds,
            )
            cursor = connection.cursor()
            stage = ConnectionStage.VERIFY
            cursor.execute(
                f"SET LOCK_TIMEOUT {self.settings.lock_timeout_milliseconds}; SET DEADLOCK_PRIORITY LOW;"
            )
            cursor.execute("SELECT DB_NAME()")
            actual = cursor.fetchone()
            if not actual or str(actual[0]).casefold() != source.connection.database.casefold():
                raise OperationError(
                    "DATABASE_MISMATCH",
                    "The connected database differs from the configured database.",
                )
            yield cursor
        except pyodbc.Error as exc:
            from dataclasses import asdict

            diagnostic = asdict(_driver_diagnostics(exc, stage, source, password))
            diagnostic["stage"] = (
                "opening database connection"
                if stage == ConnectionStage.CONNECT
                else "executing read-only operation"
            )
            raise OperationError(diagnostic["code"], diagnostic["message"], diagnostic) from None
        finally:
            for resource in (cursor, connection):
                if resource:
                    try:
                        resource.close()
                    except Exception:
                        pass
            self._slots.release()

    @staticmethod
    def _table(source, table):
        if str(source.id) != table.data_source_id or not source.permits(
            TableIdentifier(table.schema_name, table.table_name)
        ):
            raise OperationError(
                "TABLE_NOT_ALLOWED", "This table is outside the configured source access scope."
            )

    @staticmethod
    def _scope_sql(source):
        if source.access_scope.allowed_tables:
            pairs = source.access_scope.allowed_tables
            return "(" + " OR ".join("(s.name=? AND t.name=?)" for _ in pairs) + ")", [
                v for p in pairs for v in (p.schema, p.name)
            ]
        schemas = source.access_scope.allowed_schemas
        return "s.name IN (" + ",".join("?" for _ in schemas) + ")", list(schemas)

    def list_tables(self, source, password, search, offset, limit):
        scope, params = self._scope_sql(source)
        with self._session(source, password) as cursor:
            cursor.execute(
                """SELECT s.name,t.name,t.object_id,CAST(ep.value AS nvarchar(2000)),
 COUNT(*) OVER() FROM sys.tables t JOIN sys.schemas s ON s.schema_id=t.schema_id
 LEFT JOIN sys.extended_properties ep ON ep.major_id=t.object_id AND ep.minor_id=0 AND ep.name='MS_Description'
 WHERE t.is_ms_shipped=0 AND """
                + scope
                + " AND (?='' OR t.name LIKE ? ESCAPE '~') ORDER BY s.name,t.name OFFSET ? ROWS FETCH NEXT ? ROWS ONLY",
                *params,
                search,
                "%"
                + search.replace("~", "~~").replace("%", "~%").replace("_", "~_").replace("[", "~[")
                + "%",
                offset,
                limit,
            )
            rows = cursor.fetchmany(limit)
            tables = []
            for row in rows:
                preview = self.settings.column_preview_size
                cursor.execute(
                    f"SELECT TOP ({preview + 1}) name FROM sys.columns WHERE object_id=? ORDER BY column_id",
                    row[2],
                )
                columns = [r[0] for r in cursor.fetchmany(preview + 1)]
                tables.append(
                    {
                        "data_source_id": str(source.id),
                        "schema_name": row[0],
                        "table_name": row[1],
                        "description": row[3] or "",
                        "columns": columns[:preview],
                        "columns_truncated": len(columns) > preview,
                    }
                )
            return {
                "tables": tables,
                "total": int(rows[0][4]) if rows else None,
                "next_offset": offset + limit if len(rows) == limit else None,
            }

    def schema(self, source, password, table):
        self._table(source, table)
        with self._session(source, password) as cursor:
            cursor.execute(
                "SELECT t.object_id FROM sys.tables t JOIN sys.schemas s ON s.schema_id=t.schema_id WHERE s.name=? AND t.name=? AND t.is_ms_shipped=0",
                table.schema_name,
                table.table_name,
            )
            row = cursor.fetchone()
            if not row:
                raise OperationError(
                    "TABLE_NOT_FOUND", "The table does not exist or is not visible to this login."
                )
            oid = row[0]
            cursor.execute(
                """SELECT c.name,ty.name,c.max_length,c.precision,c.scale,c.is_nullable,c.is_identity,c.is_computed,
 CAST(ep.value AS nvarchar(2000)),dc.definition
 FROM sys.columns c JOIN sys.types ty ON ty.user_type_id=c.user_type_id
 LEFT JOIN sys.extended_properties ep ON ep.major_id=c.object_id AND ep.minor_id=c.column_id AND ep.name='MS_Description'
 LEFT JOIN sys.default_constraints dc ON dc.object_id=c.default_object_id
 WHERE c.object_id=? ORDER BY c.column_id""",
                oid,
            )
            column_rows = cursor.fetchmany(self.settings.schema_max_columns + 1)
            columns = [
                {
                    "name": r[0],
                    "type": r[1],
                    "max_length_bytes": r[2],
                    "precision": r[3],
                    "scale": r[4],
                    "nullable": bool(r[5]),
                    "identity": bool(r[6]),
                    "computed": bool(r[7]),
                    "description": r[8] or "",
                    "default": r[9],
                }
                for r in column_rows[: self.settings.schema_max_columns]
            ]
            cursor.execute(
                """SELECT i.name,i.is_primary_key,i.is_unique,c.name,ic.key_ordinal,ic.is_included_column
 FROM sys.indexes i JOIN sys.index_columns ic ON ic.object_id=i.object_id AND ic.index_id=i.index_id
 JOIN sys.columns c ON c.object_id=ic.object_id AND c.column_id=ic.column_id
 WHERE i.object_id=? AND i.is_hypothetical=0 ORDER BY i.index_id,ic.index_column_id""",
                oid,
            )
            index_rows = cursor.fetchmany(self.settings.schema_max_indexes + 1)
            indexes = [
                {
                    "name": r[0],
                    "primary_key": bool(r[1]),
                    "unique": bool(r[2]),
                    "column": r[3],
                    "ordinal": r[4],
                    "included": bool(r[5]),
                }
                for r in index_rows[: self.settings.schema_max_indexes]
            ]
            cursor.execute(
                """SELECT fk.name,pc.name,rs.name,rt.name,rc.name FROM sys.foreign_keys fk
 JOIN sys.foreign_key_columns fc ON fc.constraint_object_id=fk.object_id
 JOIN sys.columns pc ON pc.object_id=fc.parent_object_id AND pc.column_id=fc.parent_column_id
 JOIN sys.tables rt ON rt.object_id=fc.referenced_object_id JOIN sys.schemas rs ON rs.schema_id=rt.schema_id
 JOIN sys.columns rc ON rc.object_id=fc.referenced_object_id AND rc.column_id=fc.referenced_column_id
 WHERE fk.parent_object_id=?""",
                oid,
            )
            relationship_rows = cursor.fetchmany(self.settings.schema_max_relationships + 1)
            relationships = [
                {
                    "name": r[0],
                    "column": r[1],
                    "referenced_schema": r[2],
                    "referenced_table": r[3],
                    "referenced_column": r[4],
                    "target_allowed": source.permits(TableIdentifier(r[2], r[3])),
                }
                for r in relationship_rows[: self.settings.schema_max_relationships]
            ]
            cursor.execute(
                "SELECT name,definition,is_disabled,is_not_trusted FROM sys.check_constraints WHERE parent_object_id=?",
                oid,
            )
            check_rows = cursor.fetchmany(self.settings.schema_max_constraints + 1)
            checks = [
                {
                    "name": r[0],
                    "definition": r[1],
                    "disabled": bool(r[2]),
                    "not_trusted": bool(r[3]),
                }
                for r in check_rows[: self.settings.schema_max_constraints]
            ]
            return {
                "data_source_id": str(source.id),
                "schema_name": table.schema_name,
                "table_name": table.table_name,
                "columns": columns,
                "indexes": indexes,
                "relationships": relationships,
                "check_constraints": checks,
                "truncated": {
                    "columns": len(column_rows) > self.settings.schema_max_columns,
                    "indexes": len(index_rows) > self.settings.schema_max_indexes,
                    "relationships": len(relationship_rows)
                    > self.settings.schema_max_relationships,
                    "check_constraints": len(check_rows) > self.settings.schema_max_constraints,
                },
                "observed_at": utc_now(),
            }

    def sample(self, source, password, table, columns, sample_rows):
        self._table(source, table)
        sql = (
            "SELECT TOP ("
            + str(sample_rows)
            + ") "
            + ",".join(quote(c) for c in columns)
            + " FROM "
            + quote(table.schema_name)
            + "."
            + quote(table.table_name)
        )
        with self._session(source, password) as cursor:
            cursor.execute(sql)
            rows, used, truncated = [], 0, False
            for _ in range(sample_rows):
                row = cursor.fetchone()
                if row is None:
                    break
                # Do not retain raw rows beyond this operation or unbounded LOBs.
                converted = [json_value(v) for v in row]
                size = len(json.dumps(converted, ensure_ascii=False).encode("utf-8"))
                if (
                    size > self.settings.profile_row_max_bytes
                    or used + size > self.settings.profile_sample_max_bytes
                ):
                    truncated = True
                    break
                used += size
                rows.append(converted)
            return {
                "columns": columns,
                "rows": rows,
                "sample_rows": len(rows),
                "sample_limit": sample_rows,
                "truncated": truncated,
                "sampling_method": "bounded TOP rows without random ordering; not representative of the full table",
                "observed_at": utc_now(),
            }

    def query(self, source, password, sql, parameters, max_rows, max_bytes, timeout_seconds):
        started = perf_counter()
        bounded = validate_select(
            sql, source, parameters, max_rows, self.settings.sql_max_characters
        )
        with self._session(source, password, timeout_seconds) as cursor:
            # Bound large text/binary values inside SQL Server before driver materialization.
            cursor.execute(f"SET TEXTSIZE {self.settings.query_cell_max_bytes}")
            cursor.execute(bounded, *parameters)
            columns = [
                {
                    "name": c[0],
                    "python_type": getattr(c[1], "__name__", str(c[1])),
                    "precision": c[4],
                    "scale": c[5],
                    "nullable": c[6],
                }
                for c in cursor.description or []
            ]
            result = {
                "data_source_id": str(source.id),
                "database": source.connection.database,
                "columns": columns,
                "rows": [],
                "row_count": 0,
                "truncated": False,
                "truncation_reason": None,
                "duration_ms": 0.0,
                "result_bytes": 0,
                "cell_max_bytes": self.settings.query_cell_max_bytes,
                "large_values_may_be_truncated": True,
            }
            rows, used, truncated, reason = (
                [],
                len(json.dumps(result, ensure_ascii=False).encode("utf-8")) + 128,
                False,
                None,
            )
            if used > max_bytes:
                raise OperationError(
                    "RESPONSE_SIZE_LIMIT",
                    "Column metadata exceeds the query response budget. Select fewer columns or raise response_max_bytes.",
                )
            for _ in range(max_rows + 1):
                row = cursor.fetchone()
                if row is None:
                    break
                if len(rows) >= max_rows:
                    truncated, reason = True, "row_limit"
                    break
                values = [json_value(v) for v in row]
                size = len(json.dumps(values, ensure_ascii=False).encode("utf-8")) + 2
                if used + size > max_bytes:
                    truncated, reason = True, "response_size_limit"
                    break
                used += size
                rows.append(values)
            if truncated:
                cursor.cancel()
            result.update(
                rows=rows,
                row_count=len(rows),
                truncated=truncated,
                truncation_reason=reason,
                duration_ms=round((perf_counter() - started) * 1000, 2),
            )
            result["result_bytes"] = len(json.dumps(result, ensure_ascii=False).encode("utf-8"))
            return result
