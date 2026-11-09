import json
import os
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from data_agent_mcp.application.ports.credentials import CredentialResolutionError
from data_agent_mcp.application.ports.data_sources import ConfigurationError
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
from data_agent_mcp.domain.queries import OperationError
from data_agent_mcp.infrastructure.credentials.environment import EnvironmentCredentialResolver
from data_agent_mcp.infrastructure.storage.file_lock import file_lock


class _Config(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class _Encryption(_Config):
    require_encryption: bool = True
    verify_server_certificate: bool = True


class _Connection(_Config):
    server: str
    database: str
    port: int | None = None
    encryption: _Encryption = Field(default_factory=_Encryption)
    connect_timeout_seconds: int = 15
    query_timeout_seconds: int = 30


class _Windows(_Config):
    method: Literal["windows"]


class _Password(_Config):
    method: Literal["username_password"]
    username: str | None = None
    username_reference: str | None = None
    password_reference: str

    @model_validator(mode="after")
    def validate_username_source(self):
        if (self.username is None) == (self.username_reference is None):
            raise ValueError("Provide exactly one of username or username_reference")
        return self


class _Table(_Config):
    schema_name: str
    table_name: str


class _Scope(_Config):
    allowed_schemas: list[str] = Field(min_length=1, max_length=100)
    allowed_tables: list[_Table] = Field(default_factory=list, max_length=1000)


class _Source(_Config):
    id: str
    name: str
    engine: Literal["mssql", "mysql", "postgresql"]
    connection: _Connection
    authentication: Annotated[_Windows | _Password, Field(discriminator="method")]
    access_scope: _Scope
    description: str = ""
    enabled: bool = True
    revision: int = 1

    def to_domain(self) -> DataSource:
        username_reference = None
        username = None
        if isinstance(self.authentication, _Password):
            username = self.authentication.username
            if self.authentication.username_reference is not None:
                username_reference = SecretReference(self.authentication.username_reference)
                try:
                    username = EnvironmentCredentialResolver().resolve(username_reference).value
                except CredentialResolutionError as exc:
                    raise ConfigurationError(
                        "The configured username environment variable is unavailable or invalid."
                    ) from exc
        authentication = (
            WindowsAuthentication()
            if isinstance(self.authentication, _Windows)
            else UsernamePasswordAuthentication(
                username,
                SecretReference(self.authentication.password_reference),
                username_reference=username_reference,
            )
        )
        return DataSource(
            id=UUID(self.id),
            name=self.name,
            engine=DatabaseEngine(self.engine),
            connection=ConnectionSettings(
                server=self.connection.server,
                database=self.connection.database,
                port=self.connection.port,
                encryption=EncryptionSettings(**self.connection.encryption.model_dump()),
                connect_timeout_seconds=self.connection.connect_timeout_seconds,
                query_timeout_seconds=self.connection.query_timeout_seconds,
            ),
            authentication=authentication,
            access_scope=AccessScope(
                tuple(self.access_scope.allowed_schemas),
                tuple(
                    TableIdentifier(t.schema_name, t.table_name)
                    for t in self.access_scope.allowed_tables
                ),
            ),
            description=self.description,
            enabled=self.enabled,
            revision=self.revision,
        )


class _Document(_Config):
    version: Literal[1]
    sources: list[_Source] = Field(max_length=100)

    @field_validator("version", mode="before")
    @classmethod
    def exact_version_type(cls, value):
        if type(value) is not int:
            raise ValueError("Version must be an integer")
        return value


def _unique_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ConfigurationError(
                "Duplicate JSON keys are not permitted in source configuration."
            )
        result[key] = value
    return result


class FileDataSourceRepository:
    """Read the owner's configuration on demand; never connect during loading."""

    def __init__(self, path: Path):
        self.path = path

    def get(self, source_id: UUID) -> DataSource | None:
        return next((source for source in self.list_all() if source.id == source_id), None)

    def list_all(self) -> list[DataSource]:
        try:
            with self.path.open("rb") as handle:
                # Bounded read also works when the file changes between stat and read.
                raw = handle.read(1_000_001)
            if len(raw) > 1_000_000:
                raise ConfigurationError("Source configuration exceeds the 1 MB limit.")
            document = _Document.model_validate(
                json.loads(raw.decode("utf-8-sig"), object_pairs_hook=_unique_keys)
            )
        except FileNotFoundError as exc:
            raise ConfigurationError(
                "Source configuration file was not found. Set --sources or DATA_AGENT_SOURCES_FILE."
            ) from exc
        except (OSError, UnicodeError) as exc:
            raise ConfigurationError(
                "Source configuration could not be read. Check its permissions and UTF-8 encoding."
            ) from exc
        except (json.JSONDecodeError, RecursionError) as exc:
            raise ConfigurationError("Source configuration is not valid JSON.") from exc
        except ValidationError as exc:
            # Pydantic's rendered errors can contain raw inputs. Only report schema
            # failure counts; never echo arbitrary fields or credential-like values.
            raise ConfigurationError(
                f"Source configuration does not match the schema ({exc.error_count()} validation errors). Raw values were omitted."
            ) from exc
        try:
            sources = [item.to_domain() for item in document.sources]
        except (ValueError, TypeError) as exc:
            raise ConfigurationError(
                "Source configuration has invalid domain values. Check UUIDs, scopes, endpoint settings and authentication references."
            ) from exc
        identifiers = [source.id for source in sources]
        if len(set(identifiers)) != len(identifiers):
            raise ConfigurationError("Every data source must have a unique UUID.")
        return sources

    def save(self, source: DataSource, expected_revision: int | None = None) -> DataSource:
        """Compare-and-swap under a process/file lock; atomically replace validated JSON."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with file_lock(self.path.with_suffix(".lock")):
            sources = self.list_all() if self.path.exists() else []
            existing = next((s for s in sources if s.id == source.id), None)
            if existing and expected_revision != existing.revision:
                raise OperationError(
                    "REVISION_CONFLICT", "Read the current source revision before updating it."
                )
            if not existing and expected_revision is not None:
                raise OperationError("SOURCE_NOT_FOUND", "No source exists for this revision.")
            if not existing and len(sources) >= 100:
                raise OperationError("SOURCE_LIMIT", "At most 100 data sources may be configured.")
            from dataclasses import replace

            source = replace(source, revision=existing.revision + 1 if existing else 1)
            updated = [s for s in sources if s.id != source.id] + [source]
            raw = json.dumps(
                {"version": 1, "sources": [source_configuration(s) for s in updated]}, indent=2
            )
            if len(raw.encode("utf-8")) > 1_000_000:
                raise ConfigurationError("Source configuration exceeds the 1 MB limit.")
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="w", encoding="utf-8", dir=self.path.parent, delete=False
                ) as handle:
                    temporary = handle.name
                    handle.write(raw + "\n")
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, self.path)
            finally:
                if temporary and os.path.exists(temporary):
                    os.unlink(temporary)
            return source


def source_configuration(source: DataSource) -> dict:
    authentication = {"method": source.authentication.method.value}
    if isinstance(source.authentication, UsernamePasswordAuthentication):
        authentication["password_reference"] = source.authentication.password_reference.key
        if source.authentication.username_reference is not None:
            authentication["username_reference"] = source.authentication.username_reference.key
        else:
            authentication["username"] = source.authentication.username
    return {
        "id": str(source.id),
        "name": source.name,
        "engine": source.engine.value,
        "description": source.description,
        "enabled": source.enabled,
        "revision": source.revision,
        "connection": asdict(source.connection),
        "authentication": authentication,
        "access_scope": {
            "allowed_schemas": list(source.access_scope.allowed_schemas),
            "allowed_tables": [
                {"schema_name": t.schema, "table_name": t.name}
                for t in source.access_scope.allowed_tables
            ],
        },
    }
