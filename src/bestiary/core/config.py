from __future__ import annotations

import os
import tomllib
from pathlib import Path

CONFIG_PATHS: tuple[Path, ...] = (
    Path("~/.config/bestiary/config.toml").expanduser(),
    Path(".bestiary.toml"),
)


def _split_csv(value: str) -> set[str]:
    return {item.strip() for item in value.split(",") if item.strip()}


def load_config() -> tuple[set[str] | None, set[str]]:
    """Resolve (enabled, disabled) tool sets.

    Env vars BESTIARY_ENABLED / BESTIARY_DISABLED win over config files.
    enabled=None means "register everything installed" — the default.
    """
    env_enabled = os.environ.get("BESTIARY_ENABLED")
    env_disabled = os.environ.get("BESTIARY_DISABLED")
    if env_enabled is not None or env_disabled is not None:
        enabled = _split_csv(env_enabled) if env_enabled is not None else None
        disabled = _split_csv(env_disabled) if env_disabled is not None else set()
        return enabled, disabled

    for path in CONFIG_PATHS:
        if not path.is_file():
            continue
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        enabled: set[str] | None = None
        disabled: set[str] = set()
        if isinstance(data.get("enabled"), list):
            enabled = {str(name) for name in data["enabled"]}
        if isinstance(data.get("disabled"), list):
            disabled = {str(name) for name in data["disabled"]}
        return enabled, disabled

    return None, set()
