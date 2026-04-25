from __future__ import annotations

import argparse

from .server import build_server


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="bestiary",
        description="MCP server with pluggable tools.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("serve", help="run the MCP server over stdio")
    sub.add_parser("list", help="print tools registered for this configuration")
    args = parser.parse_args(argv)

    if args.cmd == "serve":
        mcp, _ = build_server()
        mcp.run()
        return 0

    if args.cmd == "list":
        _, loaded = build_server()
        for name in loaded:
            print(name)
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
