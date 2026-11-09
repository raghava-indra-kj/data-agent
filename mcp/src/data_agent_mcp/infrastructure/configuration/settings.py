import json
import os
from dataclasses import fields
from pathlib import Path

from data_agent_mcp.domain.queries import OperationError
from data_agent_mcp.domain.settings import RuntimeSettings


def load_settings(path: Path) -> RuntimeSettings:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig")) if path.exists() else {}
        names = {field.name for field in fields(RuntimeSettings)}
        if not isinstance(data, dict) or not set(data) <= names:
            raise ValueError("Unknown settings")
        for name in names:
            environment_key = "DATA_AGENT_" + name.upper()
            if environment_key in os.environ:
                data[name] = int(os.environ[environment_key])
        return RuntimeSettings(**data)
    except (ValueError, TypeError, OSError):
        raise OperationError(
            "INVALID_SETTINGS",
            "Settings must be valid JSON containing recognized positive integer limits. Check default/ceiling relationships and DATA_AGENT_* overrides.",
        ) from None
