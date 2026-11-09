from dataclasses import dataclass, field
from typing import Protocol

from data_agent_mcp.domain.data_sources.models import SecretReference


class CredentialResolutionError(Exception):
    """A secret could not be resolved without exposing its contents."""


@dataclass(frozen=True, slots=True)
class ResolvedSecret:
    value: str = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not self.value or "\x00" in self.value:
            raise CredentialResolutionError(
                "Password must be non-empty and contain no NUL characters"
            )


class CredentialResolver(Protocol):
    def resolve(self, reference: SecretReference) -> ResolvedSecret: ...
