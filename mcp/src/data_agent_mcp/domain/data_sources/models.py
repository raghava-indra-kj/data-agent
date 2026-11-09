"""Data-source domain types, independent of frameworks, drivers and secret stores.

Engine names describe configuration, not adapter availability. Only MSSQL will
have an implementation initially; the application must reject unavailable adapters.
Secrets are resolved through an application port and never stored in these models.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import StrEnum
from uuid import UUID, uuid4


def _text(value: str, label: str, max_length: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    if len(value) > max_length or any(ord(character) < 32 for character in value):
        raise ValueError(
            f"{label} must be at most {max_length} characters without control characters"
        )
    return value


def _boolean(value: bool, label: str) -> None:
    if not isinstance(value, bool):
        raise ValueError(f"{label} must be a boolean")


class DatabaseEngine(StrEnum):
    MSSQL = "mssql"
    MYSQL = "mysql"
    POSTGRESQL = "postgresql"


class AuthenticationMethod(StrEnum):
    WINDOWS = "windows"
    USERNAME_PASSWORD = "username_password"


@dataclass(frozen=True, slots=True)
class SecretReference:
    """Opaque lookup key for a secret provider; this is not the password itself."""

    key: str = field(repr=False)

    def __post_init__(self) -> None:
        _text(self.key, "Secret reference", 512)


@dataclass(frozen=True, slots=True)
class WindowsAuthentication:
    """Use the Windows identity of the process opening the database connection."""

    method: AuthenticationMethod = field(default=AuthenticationMethod.WINDOWS, init=False)


@dataclass(frozen=True, slots=True)
class UsernamePasswordAuthentication:
    username: str = field(repr=False)
    password_reference: SecretReference = field(repr=False)
    username_reference: SecretReference | None = field(default=None, repr=False, kw_only=True)
    method: AuthenticationMethod = field(default=AuthenticationMethod.USERNAME_PASSWORD, init=False)

    def __post_init__(self) -> None:
        _text(self.username, "Username", 256)
        if not isinstance(self.password_reference, SecretReference):
            raise ValueError("Password must be supplied as a SecretReference")
        if self.username_reference is not None and not isinstance(
            self.username_reference, SecretReference
        ):
            raise ValueError("Username reference must be a SecretReference")


type Authentication = WindowsAuthentication | UsernamePasswordAuthentication


@dataclass(frozen=True, slots=True)
class EncryptionSettings:
    """Transport requirements; adapters map these to engine-specific options."""

    require_encryption: bool = True
    verify_server_certificate: bool = True

    def __post_init__(self) -> None:
        _boolean(self.require_encryption, "Require encryption")
        _boolean(self.verify_server_certificate, "Verify server certificate")
        if self.verify_server_certificate and not self.require_encryption:
            raise ValueError("Certificate verification requires encryption")


@dataclass(frozen=True, slots=True)
class ConnectionSettings:
    """Dynamic endpoint settings. Connection-string construction belongs to adapters."""

    server: str
    database: str
    port: int | None = None
    encryption: EncryptionSettings = field(default_factory=EncryptionSettings)
    connect_timeout_seconds: int = 15
    query_timeout_seconds: int = 30

    def __post_init__(self) -> None:
        _text(self.server, "Server", 255)
        _text(self.database, "Database", 256)
        if "://" in self.server or any(character in self.server for character in ";{}=,"):
            raise ValueError("Server must be a host or host\\instance; configure port separately")
        if self.server != self.server.strip():
            raise ValueError("Server must not contain leading or trailing whitespace")
        if self.port is not None and (type(self.port) is not int or not 1 <= self.port <= 65535):
            raise ValueError("Port must be an integer between 1 and 65535")
        if not isinstance(self.encryption, EncryptionSettings):
            raise ValueError("Encryption must be EncryptionSettings")
        for label, value, maximum in (
            ("Connect timeout", self.connect_timeout_seconds, 120),
            ("Query timeout", self.query_timeout_seconds, 600),
        ):
            if type(value) is not int or not 1 <= value <= maximum:
                raise ValueError(f"{label} must be an integer between 1 and {maximum} seconds")


@dataclass(frozen=True, slots=True)
class TableIdentifier:
    schema: str
    name: str

    def __post_init__(self) -> None:
        _text(self.schema, "Schema", 256)
        _text(self.name, "Table", 256)


@dataclass(frozen=True, slots=True)
class AccessScope:
    """Explicit schema boundary, optionally narrowed to selected tables.

    An empty table selection permits all tables within the selected schemas.
    Names use exact matching; adapters must resolve database identifiers against
    catalog metadata rather than assume a database's case/collation rules.
    This policy supplements database permissions, not replaces them.
    """

    allowed_schemas: tuple[str, ...]
    allowed_tables: tuple[TableIdentifier, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.allowed_schemas, tuple) or not self.allowed_schemas:
            raise ValueError("Select at least one schema using an immutable tuple")
        for schema in self.allowed_schemas:
            _text(schema, "Allowed schema", 256)
        if len(set(self.allowed_schemas)) != len(self.allowed_schemas):
            raise ValueError("Allowed schemas must be unique")
        if not isinstance(self.allowed_tables, tuple):
            raise ValueError("Allowed tables must be an immutable tuple")
        for table in self.allowed_tables:
            if not isinstance(table, TableIdentifier):
                raise ValueError("Allowed tables must contain TableIdentifier values")
            if table.schema not in self.allowed_schemas:
                raise ValueError("An allowed table must belong to an allowed schema")
        if len(set(self.allowed_tables)) != len(self.allowed_tables):
            raise ValueError("Allowed tables must be unique")

    def permits(self, table: TableIdentifier) -> bool:
        if not isinstance(table, TableIdentifier):
            raise ValueError("Table must be a TableIdentifier")
        return table.schema in self.allowed_schemas and (
            not self.allowed_tables or table in self.allowed_tables
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class DataSource:
    """Aggregate root for a named source and its access configuration.

    Changes preserve identity and advance the revision. Application services use
    the revision for optimistic concurrency and configuration-cache invalidation.
    Authentication capability checks belong to the selected database adapter.
    """

    name: str
    engine: DatabaseEngine
    connection: ConnectionSettings
    authentication: Authentication
    access_scope: AccessScope
    id: UUID = field(default_factory=uuid4)
    description: str = ""
    enabled: bool = True
    revision: int = 1

    def __post_init__(self) -> None:
        _text(self.name, "Source name", 150)
        if not isinstance(self.id, UUID):
            raise ValueError("Source ID must be a UUID")
        if not isinstance(self.engine, DatabaseEngine):
            raise ValueError("Engine must be a DatabaseEngine")
        if not isinstance(self.connection, ConnectionSettings):
            raise ValueError("Connection must be ConnectionSettings")
        if not isinstance(
            self.authentication, (WindowsAuthentication, UsernamePasswordAuthentication)
        ):
            raise ValueError("Select Windows or username/password authentication")
        if not isinstance(self.access_scope, AccessScope):
            raise ValueError("Access scope must be AccessScope")
        if not isinstance(self.description, str) or len(self.description) > 2000:
            raise ValueError("Description must be text of at most 2000 characters")
        _boolean(self.enabled, "Enabled")
        if type(self.revision) is not int or self.revision < 1:
            raise ValueError("Revision must be a positive integer")

    def permits(self, table: TableIdentifier) -> bool:
        return self.enabled and self.access_scope.permits(table)

    def reconfigure(
        self,
        *,
        connection: ConnectionSettings,
        authentication: Authentication,
        access_scope: AccessScope,
    ) -> DataSource:
        if (connection, authentication, access_scope) == (
            self.connection,
            self.authentication,
            self.access_scope,
        ):
            return self
        return replace(
            self,
            connection=connection,
            authentication=authentication,
            access_scope=access_scope,
            revision=self.revision + 1,
        )

    def set_enabled(self, enabled: bool) -> DataSource:
        _boolean(enabled, "Enabled")
        if enabled == self.enabled:
            return self
        return replace(self, enabled=enabled, revision=self.revision + 1)

    def describe(self, *, name: str, description: str) -> DataSource:
        if (name, description) == (self.name, self.description):
            return self
        return replace(self, name=name, description=description, revision=self.revision + 1)
