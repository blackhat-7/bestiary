from __future__ import annotations

import importlib.util
import os
import sys
from importlib.metadata import entry_points
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

ENTRY_POINT_GROUP = "bestiary.tools"
DEFAULT_PLUGIN_DIR = "~/.config/bestiary/tools"


def _should_register(name: str, enabled: set[str] | None, disabled: set[str]) -> bool:
    if name in disabled:
        return False
    if enabled is not None and name not in enabled:
        return False
    return True


def load_tools(
    mcp: "FastMCP", *, enabled: set[str] | None, disabled: set[str]
) -> list[str]:
    """Discover and register enabled tools. Returns ordered names of those loaded.

    Two sources, evaluated in order:
      1. Entry points in group `bestiary.tools` — built-ins and pip-installed plugins.
      2. *.py files in $BESTIARY_PLUGIN_DIR (default ~/.config/bestiary/tools/) —
         each must expose `register(mcp)`. Lets users add ad-hoc tools without
         packaging.
    """
    loaded: list[str] = []

    for ep in entry_points(group=ENTRY_POINT_GROUP):
        if ep.name in loaded or not _should_register(ep.name, enabled, disabled):
            continue
        ep.load()(mcp)
        loaded.append(ep.name)

    plugin_dir = Path(
        os.environ.get("BESTIARY_PLUGIN_DIR", DEFAULT_PLUGIN_DIR)
    ).expanduser()
    if plugin_dir.is_dir():
        for path in sorted(plugin_dir.glob("*.py")):
            name = path.stem
            if name.startswith("_") or name in loaded:
                continue
            if not _should_register(name, enabled, disabled):
                continue
            module_name = f"bestiary._local.{name}"
            spec = importlib.util.spec_from_file_location(module_name, path)
            if spec is None or spec.loader is None:
                continue
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
            register = getattr(module, "register", None)
            if callable(register):
                register(mcp)
                loaded.append(name)

    return loaded
