from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def load_profile_payload(
    *,
    profile_path: str | Path | None = None,
    profile_yaml: str | None = None,
    profile_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if profile_data is not None:
        return profile_data
    if profile_yaml is not None:
        return yaml.safe_load(profile_yaml) or {}
    if profile_path is not None:
        with Path(profile_path).open("r", encoding="utf-8") as handle:
            return yaml.safe_load(handle) or {}
    return {}


def dump_profile_payload(profile_data: dict[str, Any]) -> str:
    return yaml.safe_dump(profile_data, allow_unicode=True, sort_keys=False)
