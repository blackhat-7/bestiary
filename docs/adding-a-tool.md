# Adding a tool

A tool is anything that exposes a `register(mcp)` function. Inside, you call
`@mcp.tool()` (or `mcp.tool()(fn)`) on one or more functions. FastMCP picks
up the docstring, type hints, and defaults to build the JSON schema; you
don't write schema by hand.

## File-drop (quickest)

Drop a single `.py` file into `~/.config/bestiary/tools/`:

```python
# ~/.config/bestiary/tools/dice.py
import secrets
from typing import Literal

def register(mcp):
    @mcp.tool()
    def dice(sides: Literal[4, 6, 8, 10, 12, 20] = 6, count: int = 1) -> list[int]:
        """Roll dice."""
        return [secrets.randbelow(sides) + 1 for _ in range(count)]
```

Restart whichever MCP client uses `bestiary`. Done. No `pip install`, no
restart of `bestiary` itself (it's stdio — restart of the *client* is what
re-spawns the server).

The directory is configurable: `BESTIARY_PLUGIN_DIR=/some/path`.

## Packaged plugin (shareable)

Make a normal Python package. The only special thing is one entry point:

```toml
# pyproject.toml of your plugin
[project]
name = "bestiary-myplugin"
version = "0.1.0"
dependencies = ["bestiary", "<your deps>"]

[project.entry-points."bestiary.tools"]
myplugin = "bestiary_myplugin:register"
```

```python
# src/bestiary_myplugin/__init__.py
def register(mcp):
    @mcp.tool()
    def my_tool(x: int) -> int:
        """Doubles x."""
        return x * 2
```

Install it alongside bestiary: `uv tool install --with bestiary-myplugin bestiary`.
Your entry point is discovered automatically.

## Conventions

**Multiple ops in one tool.** If you'd otherwise expose `foo_search`,
`foo_get`, `foo_list`, prefer one tool `foo(op: Literal["search","get","list"], ...)`.
Each tool's full JSON schema sits in the LLM's context every turn — five tools
cost ~5× the tokens of one dispatch tool. The reddit tool is the canonical
example.

**Type hints over runtime checks (where possible).** FastMCP turns
`Literal[...]`, `int`, `str | None` into a precise JSON schema for the model.
Reach for the `validation` helpers in `bestiary.core.validation` for things
the type system can't express (length limits, character classes, value
ranges).

**Errors.** Raise `bestiary.core.errors.ValidationError` for bad inputs;
`bestiary.core.errors.ApiError` for upstream failures. FastMCP turns those
into structured tool errors.

**No secrets in source.** If your tool needs an API key, read it from the
environment (`os.environ["FOO_TOKEN"]`). Document the variable in your
plugin's README. The MCP client config decides where the env var comes from.
