import os
import re
from collections.abc import Mapping

from data_agent_mcp.application.ports.credentials import CredentialResolutionError, ResolvedSecret
from data_agent_mcp.domain.data_sources.models import SecretReference


class EnvironmentCredentialResolver:
    def __init__(self, environment: Mapping[str, str] | None = None):
        self._environment = os.environ if environment is None else environment

    def resolve(self, reference: SecretReference) -> ResolvedSecret:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,127}", reference.key):
            raise CredentialResolutionError(
                "Password reference must be an environment variable name."
            )
        value = self._environment.get(reference.key)
        if not value and os.name == "nt" and self._environment is os.environ:
            try:
                import winreg

                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment") as key:
                    user_val, _ = winreg.QueryValueEx(key, reference.key)
                    if user_val:
                        value = str(user_val)
            except OSError:
                pass
        if not value:
            raise CredentialResolutionError(
                "The configured password environment variable is missing or empty. Set it in the process launching the server."
            )
        return ResolvedSecret(value)
