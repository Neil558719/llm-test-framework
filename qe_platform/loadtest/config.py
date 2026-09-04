from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import yaml

from .models import LoadTestConfig


_ALLOWED = {field.name for field in LoadTestConfig.__dataclass_fields__.values()}


def load_config(path: str | Path) -> LoadTestConfig:
    try:
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(f"cannot load load-test config: {exc}") from exc
    if not isinstance(raw, Mapping):
        raise ValueError("load-test config must be a YAML mapping")
    unknown = sorted(set(raw) - _ALLOWED)
    if unknown:
        raise ValueError(f"unknown load-test config fields: {', '.join(unknown)}")
    headers = raw.get("headers", {})
    if not isinstance(headers, Mapping) or not all(isinstance(key, str) and isinstance(value, str) for key, value in headers.items()):
        raise ValueError("headers must be a string mapping")
    values: dict[str, Any] = dict(raw)
    if "duration_seconds" in values and "requests" not in values:
        values["requests"] = None
    values["headers"] = dict(headers)
    try:
        return LoadTestConfig(**values)
    except TypeError as exc:
        raise ValueError(f"invalid load-test config: {exc}") from exc
