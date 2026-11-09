"""An intentionally restricted SQL dialect for read-only database tools."""

from dataclasses import dataclass


class OperationError(Exception):
    """Safe application error. Raw driver/provider errors must be sanitized first."""

    def __init__(self, code: str, message: str, diagnostics: dict | None = None):
        super().__init__(message)
        self.code = code
        self.diagnostics = diagnostics


@dataclass(frozen=True)
class TableRef:
    data_source_id: str
    schema_name: str
    table_name: str

    @property
    def key(self) -> str:
        return f"{self.data_source_id}:{self.schema_name}:{self.table_name}"
