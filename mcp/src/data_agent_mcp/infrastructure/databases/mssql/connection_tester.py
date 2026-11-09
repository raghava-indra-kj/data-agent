import re
import sys
from collections.abc import Callable
from time import perf_counter
from typing import Any

import pyodbc

from data_agent_mcp.application.ports.credentials import ResolvedSecret
from data_agent_mcp.application.ports.database import (
    ConnectionDiagnostics,
    ConnectionStage,
    ConnectionTestResult,
)
from data_agent_mcp.domain.data_sources.models import (
    DatabaseEngine,
    DataSource,
    UsernamePasswordAuthentication,
    WindowsAuthentication,
)

DRIVER = "ODBC Driver 18 for SQL Server"
PROBE_SQL = "SELECT CAST(SERVERPROPERTY('ServerName') AS nvarchar(256)), DB_NAME(), CAST(1 AS int)"


def _odbc_value(value: str) -> str:
    # Braced values with doubled closing braces prevent attribute injection,
    # including passwords and database names containing semicolons or braces.
    return "{" + value.replace("}", "}}") + "}"


def _connection_string(source: DataSource, password: ResolvedSecret | None) -> str:
    settings = source.connection
    endpoint = settings.server
    if settings.port is not None:
        endpoint = endpoint if endpoint.lower().startswith("tcp:") else "tcp:" + endpoint
        endpoint += f",{settings.port}"
    attributes = [
        ("DRIVER", DRIVER),
        ("SERVER", endpoint),
        ("DATABASE", settings.database),
        ("Encrypt", "yes" if settings.encryption.require_encryption else "no"),
        (
            "TrustServerCertificate",
            "no" if settings.encryption.verify_server_certificate else "yes",
        ),
        ("APP", "Data Agent MCP Connection Test"),
    ]
    if isinstance(source.authentication, WindowsAuthentication):
        attributes.append(("Trusted_Connection", "yes"))
    else:
        if password is None:
            raise ValueError("Resolved password is required for SQL authentication")
        attributes.extend(
            [
                ("Trusted_Connection", "no"),
                ("UID", source.authentication.username),
                ("PWD", password.value),
            ]
        )
    return ";".join(f"{key}={_odbc_value(value)}" for key, value in attributes) + ";"


def _sanitize(message: str, source: DataSource, password: ResolvedSecret | None) -> str:
    if password:
        values = sorted({password.value, password.value.replace("}", "}}")}, key=len, reverse=True)
        if len(password.value) < 4 and any(value in message for value in values):
            return "Driver details withheld because they could contain a short password. SQLSTATE and error number are provided separately."
        for value in values:
            message = message.replace(value, "[redacted]")
    if isinstance(source.authentication, UsernamePasswordAuthentication):
        message = re.sub(
            r"(?<!\w)" + re.escape(source.authentication.username) + r"(?!\w)",
            "[redacted]",
            message,
            flags=re.IGNORECASE,
        )
    message = re.sub(r"(?i)((?:user|login)\s+)'[^']*'", r"\1'[redacted]'", message)
    # Known password values were already removed, including escaped ODBC forms.
    message = re.sub(
        r"(?i)\b(PWD|PASSWORD|UID|USER ID)\s*=\s*(?:\{(?:[^}]|}})*\}|[^;\r\n]*)",
        r"\1=[redacted]",
        message,
    )
    return message[:4000]


def _driver_diagnostics(
    exc: Exception, stage: ConnectionStage, source: DataSource, password: ResolvedSecret | None
) -> ConnectionDiagnostics:
    raw = str(exc)
    sqlstate = next((str(arg) for arg in exc.args if re.fullmatch(r"[A-Z0-9]{5}", str(arg))), None)
    if sqlstate is None:
        match = re.search(r"\[([A-Z0-9]{5})\]", raw)
        sqlstate = match[1] if match else None
    codes = re.findall(r"\((\d{1,10})\)", raw)
    number = int(codes[-1]) if codes else None
    category = "database"
    message = "The database driver reported an error."
    if sqlstate == "28000" or number == 18456:
        category, message = (
            "authentication",
            "The database rejected the login. The server may require its error log to identify the precise reason.",
        )
    elif sqlstate in {"HYT00", "HYT01"}:
        category, message = "timeout", "The operation exceeded its configured timeout."
    elif any(word in raw.lower() for word in ("certificate", "ssl", "tls")):
        category, message = (
            "encryption",
            "The driver could not establish the configured encrypted connection.",
        )
    elif sqlstate and sqlstate.startswith("08"):
        category, message = (
            "connection",
            "The driver could not establish or maintain a connection to the configured server.",
        )
    elif number == 4060:
        category, message = "database_access", "The login could not open the configured database."
    return ConnectionDiagnostics(
        code=f"MSSQL_{category.upper()}_FAILED",
        stage=stage,
        category=category,
        message=message,
        driver_message=_sanitize(raw, source, password),
        sqlstate=sqlstate,
        error_number=number,
    )


class MssqlConnectionTester:
    """Single fixed SELECT probe. No business data queries, writes or automatic retries."""

    def __init__(
        self,
        connect: Callable[..., Any] | None = None,
        drivers: Callable[[], list[str]] | None = None,
        platform: str | None = None,
    ):
        self._connect = pyodbc.connect if connect is None else connect
        self._drivers = pyodbc.drivers if drivers is None else drivers
        self._platform = sys.platform if platform is None else platform

    def test(self, source: DataSource, password: ResolvedSecret | None) -> ConnectionTestResult:
        started = perf_counter()
        stage = ConnectionStage.DRIVER
        connection = cursor = None
        diagnostics = None
        actual_server = actual_database = None
        success = False
        try:
            if source.engine != DatabaseEngine.MSSQL:
                diagnostics = ConnectionDiagnostics(
                    "UNSUPPORTED_ENGINE",
                    stage,
                    "configuration",
                    "This adapter supports MSSQL only.",
                )
            elif (
                isinstance(source.authentication, WindowsAuthentication)
                and self._platform != "win32"
            ):
                diagnostics = ConnectionDiagnostics(
                    "WINDOWS_AUTH_UNAVAILABLE",
                    stage,
                    "authentication",
                    "Windows authentication requires a Windows service host in this release. Linux Kerberos is not implemented.",
                )
            elif (
                isinstance(source.authentication, UsernamePasswordAuthentication)
                and password is None
            ):
                diagnostics = ConnectionDiagnostics(
                    "CREDENTIAL_UNAVAILABLE",
                    ConnectionStage.CREDENTIALS,
                    "credentials",
                    "No resolved SQL password was supplied.",
                )
            elif DRIVER not in self._drivers():
                diagnostics = ConnectionDiagnostics(
                    "ODBC_DRIVER_NOT_FOUND",
                    stage,
                    "driver",
                    f"Install {DRIVER} matching your Python architecture.",
                )
            else:
                stage = ConnectionStage.CONNECT
                connection = self._connect(
                    _connection_string(source, password),
                    timeout=source.connection.connect_timeout_seconds,
                    autocommit=True,
                )
                stage = ConnectionStage.VERIFY
                connection.timeout = source.connection.query_timeout_seconds
                cursor = connection.cursor()
                row = cursor.execute(PROBE_SQL).fetchone()
                if row is None or len(row) != 3 or row[2] != 1 or not row[0] or not row[1]:
                    diagnostics = ConnectionDiagnostics(
                        "CONNECTION_PROBE_INVALID",
                        stage,
                        "verification",
                        "The server did not return the expected connection probe result.",
                    )
                else:
                    actual_server, actual_database = str(row[0]), str(row[1])
                    if actual_database.casefold() != source.connection.database.casefold():
                        diagnostics = ConnectionDiagnostics(
                            "DATABASE_MISMATCH",
                            stage,
                            "verification",
                            "The connected database differs from the configured database.",
                        )
                    else:
                        success = True
        except pyodbc.Error as exc:
            diagnostics = _driver_diagnostics(exc, stage, source, password)
        except Exception:
            diagnostics = ConnectionDiagnostics(
                "CONNECTION_TEST_INTERNAL_ERROR",
                stage,
                "internal",
                "An unexpected connection test error occurred. Raw exception details were withheld.",
            )
        finally:
            # pyodbc context managers do not close connections. Close explicitly,
            # and preserve the primary failure if cleanup also fails.
            for resource in (cursor, connection):
                if resource is not None:
                    try:
                        resource.close()
                    except Exception as exc:
                        if diagnostics is None:
                            if isinstance(exc, pyodbc.Error):
                                diagnostics = _driver_diagnostics(
                                    exc, ConnectionStage.CLEANUP, source, password
                                )
                            else:
                                diagnostics = ConnectionDiagnostics(
                                    "CONNECTION_CLEANUP_FAILED",
                                    ConnectionStage.CLEANUP,
                                    "cleanup",
                                    "The probe completed, but a database resource could not be closed cleanly.",
                                )
                            success = False
        return ConnectionTestResult(
            success=success,
            data_source_id=str(source.id),
            source_name=source.name,
            engine=source.engine.value,
            authentication_method=source.authentication.method.value,
            configured_server=source.connection.server,
            configured_database=source.connection.database,
            actual_server=actual_server,
            actual_database=actual_database,
            duration_ms=round((perf_counter() - started) * 1000, 2),
            diagnostics=diagnostics,
        )
