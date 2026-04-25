from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from .core.config import load_config
from .core.plugin import load_tools

SERVER_NAME = "bestiary"
SERVER_INSTRUCTIONS = (
    "A catalog of MCP tools. Each registered tool exposes typed access to one "
    "external service. Read the tool descriptions before invoking."
)


def build_server() -> tuple[FastMCP, list[str]]:
    mcp = FastMCP(SERVER_NAME, instructions=SERVER_INSTRUCTIONS)
    enabled, disabled = load_config()
    loaded = load_tools(mcp, enabled=enabled, disabled=disabled)
    return mcp, loaded


def main() -> None:
    mcp, _ = build_server()
    mcp.run()


if __name__ == "__main__":
    main()
