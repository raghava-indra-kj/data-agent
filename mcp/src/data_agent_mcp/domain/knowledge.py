"""Knowledge identities and scope rules; no storage or MCP dependencies."""

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


class KnowledgeKind(StrEnum):
    SCHEMA = "schema"
    DATA_PROFILE = "data_profile"
    BUSINESS = "business"


@dataclass(frozen=True)
class KnowledgeScope:
    level: str = "global"
    data_source_id: str | None = None
    schema_name: str | None = None
    table_name: str | None = None

    def __post_init__(self):
        if self.level not in {"global", "source", "table"}:
            raise ValueError("Scope must be global, source or table")
        if self.level == "global":
            if any((self.data_source_id, self.schema_name, self.table_name)):
                raise ValueError("Global scope cannot contain source/table identifiers")
        else:
            if not self.data_source_id:
                raise ValueError("Source and table scopes require a source UUID")
            UUID(self.data_source_id)
            if self.level == "source" and (self.schema_name or self.table_name):
                raise ValueError("Source scope cannot contain a table")
            if self.level == "table" and not (self.schema_name and self.table_name):
                raise ValueError("Table scope requires schema and table names")


@dataclass(frozen=True)
class KnowledgeDocument:
    id: str
    title: str
    description: str
    content: str
    kind: KnowledgeKind
    scope: KnowledgeScope
    enabled: bool
    version: int
    updated_at: str
    provenance: dict
    generated_key: str | None = None
