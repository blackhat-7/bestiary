# bestiary

> *a catalog of creatures*

An extensible MCP server. One process, many tools, easy to extend without
forking. Anyone can add a tool — either as a published Python package, or as
a single file dropped into a config directory.

Pairs with [vivarium](https://github.com/blackhat-7/vivarium) (the place where
the agents live).

## Use as an MCP server

The simplest path is `uvx` — it installs and runs from git on first use,
caches between runs, and updates when you change the ref. No manual
install step.

**Claude Code** (`~/.claude.json`):
```json
{
  "mcpServers": {
    "bestiary": {
      "command": "uvx",
      "args": [
        "--from", "git+https://github.com/blackhat-7/bestiary.git@main",
        "bestiary", "serve"
      ]
    }
  }
}
```

**OpenCode** (`~/.config/opencode/opencode.json`):
```json
{
  "mcp": {
    "bestiary": {
      "type": "local",
      "command": [
        "uvx", "--from",
        "git+https://github.com/blackhat-7/bestiary.git@main",
        "bestiary", "serve"
      ],
      "enabled": true
    }
  }
}
```

**Claude Desktop** uses the same shape as Claude Code in
`~/Library/Application Support/Claude/claude_desktop_config.json`.

Pin to a tag (`@v0.1.0`) for stability; `@main` floats with upstream but
still uses the local cache between invocations. To force a refresh after a
push: add `--refresh-package bestiary` to the args, or run
`uv cache clean bestiary` once.

### Alternative: pre-installed binary

If you'd rather have `bestiary` on your `PATH` directly:

```bash
uv tool install git+https://github.com/blackhat-7/bestiary.git@main
# then in your MCP client config:
#   command = "bestiary", args = ["serve"]
```

Verify either approach with `bestiary list` (or
`uvx --from ... bestiary list`) — prints the names of all registered tools.

## Built-in tools

| Tool | What it does | Auth |
|---|---|---|
| `reddit` | read posts/comments/subreddits/users via Reddit's public JSON API | none |
| `arxiv`  | search arXiv, fetch paper metadata, and read paper text via the HTML rendering | none |

## Picking which tools register (context cost control)

Each registered tool's schema sits in your LLM's context every turn. To trim:

```bash
# env vars (highest priority)
BESTIARY_ENABLED=reddit bestiary serve
BESTIARY_DISABLED=weather,slack bestiary serve
```

Or `~/.config/bestiary/config.toml`:
```toml
enabled = ["reddit"]                  # registers only these
# disabled = ["weather"]              # alternative: deny-list
```

If you specify neither, every installed tool registers.

## Adding a tool

Two ways, depending on whether you want to share it.

### A. Drop a file (no packaging)

Create `~/.config/bestiary/tools/myhello.py`:

```python
def register(mcp):
    @mcp.tool()
    def hello(name: str) -> str:
        """Say hello."""
        return f"hello, {name}"
```

Restart your MCP client. Done.

### B. Publish a plugin package

Make a Python package whose `pyproject.toml` declares an entry point in
group `bestiary.tools`:

```toml
[project]
name = "bestiary-weather"
dependencies = ["bestiary", "httpx"]

[project.entry-points."bestiary.tools"]
weather = "bestiary_weather:register"
```

Implement `register(mcp)` the same way as the file-drop version. Publish to
git/PyPI; users `uv tool install --with bestiary-weather bestiary` and your
tool appears.

The built-in `reddit` tool follows this exact pattern — see
`src/bestiary/tools/reddit.py` as a reference.

### Convention: one tool, multiple operations

If your tool has several related actions, prefer a single tool with an `op`
discriminator over several separate tools. This keeps the schema budget low
in the LLM's context. The reddit tool is an example: one `reddit` tool with
`op` ∈ `{search, posts, subreddit, post, user}` instead of five tools.

## CLI

```
bestiary serve    # run the MCP server (stdio)
bestiary list     # print enabled tools
```

## License

MIT — see `LICENSE`.
