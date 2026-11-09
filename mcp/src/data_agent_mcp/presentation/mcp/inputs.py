"""Explicit MCP contracts; passwords and connection strings are excluded."""

from typing import Annotated, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from data_agent_mcp.domain.data_sources.models import (
    AccessScope,
    ConnectionSettings,
    DatabaseEngine,
    DataSource,
    EncryptionSettings,
    SecretReference,
    TableIdentifier,
    UsernamePasswordAuthentication,
    WindowsAuthentication,
)
from data_agent_mcp.domain.knowledge import KnowledgeScope
from data_agent_mcp.domain.queries import TableRef


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TableSelection(Input):
    data_source_id: str
    schema_name: str
    table_name: str

    def to_domain(self):
        return TableRef(str(UUID(self.data_source_id)), self.schema_name, self.table_name)


class TableScope(Input):
    schema_name: str
    table_name: str


class SourceAccessScope(Input):
    allowed_schemas: list[str]
    allowed_tables: list[TableScope] = Field(default_factory=list)


class SourceEncryption(Input):
    require_encryption: bool = True
    verify_server_certificate: bool = True


class SourceConnection(Input):
    server: str
    database: str
    port: int | None = None
    encryption: SourceEncryption = Field(default_factory=SourceEncryption)
    connect_timeout_seconds: int = 15
    query_timeout_seconds: int = 30


class WindowsAuth(Input):
    method: Literal["windows"]


class SqlAuth(Input):
    method: Literal["username_password"]
    username: str
    password_reference: str = Field(
        description="Environment-variable name containing the password; never the password itself",
        pattern=r"^[A-Za-z_][A-Za-z0-9_]*$",
    )


class SourceConfiguration(Input):
    name: str
    connection: SourceConnection
    authentication: Annotated[WindowsAuth | SqlAuth, Field(discriminator="method")]
    access_scope: SourceAccessScope
    engine: Literal["mssql", "mysql", "postgresql"] = "mssql"
    id: str | None = None
    description: str = ""
    enabled: bool = True

    def to_domain(self):
        auth = (
            WindowsAuthentication()
            if isinstance(self.authentication, WindowsAuth)
            else UsernamePasswordAuthentication(
                self.authentication.username,
                SecretReference(self.authentication.password_reference),
            )
        )
        c = self.connection
        return DataSource(
            id=UUID(self.id) if self.id else uuid4(),
            name=self.name,
            engine=DatabaseEngine(self.engine),
            connection=ConnectionSettings(
                c.server,
                c.database,
                c.port,
                EncryptionSettings(**c.encryption.model_dump()),
                c.connect_timeout_seconds,
                c.query_timeout_seconds,
            ),
            authentication=auth,
            access_scope=AccessScope(
                tuple(self.access_scope.allowed_schemas),
                tuple(
                    TableIdentifier(t.schema_name, t.table_name)
                    for t in self.access_scope.allowed_tables
                ),
            ),
            description=self.description,
            enabled=self.enabled,
        )


class ScopeInput(Input):
    level: Literal["global", "source", "table"] = "global"
    data_source_id: str | None = None
    schema_name: str | None = None
    table_name: str | None = None

    def to_domain(self):
        return KnowledgeScope(
            self.level,
            str(UUID(self.data_source_id)) if self.data_source_id else None,
            self.schema_name,
            self.table_name,
        )


class KnowledgeUpdate(Input):
    id: str
    enabled: bool
    expected_version: int = Field(ge=1)


class ReadonlyQuery(Input):
    data_source_id: str
    sql: str = Field(
        description="One SELECT with schema-qualified tables. Aggregate/filter in SQL Server. No SELECT INTO, writes, external functions or cross-database references. Do not combine multiple statements in one string with semicolons; supply multiple query objects in the 'queries' array instead."
    )
    parameters: list[str | int | float | bool | None] = Field(
        default_factory=list, description="Scalar values for positional ? placeholders"
    )
    max_rows: int | None = Field(
        default=None,
        ge=1,
        description="Optional limit at or below the owner's configured query_max_rows",
    )
    timeout_seconds: int | None = Field(default=None, ge=1)
