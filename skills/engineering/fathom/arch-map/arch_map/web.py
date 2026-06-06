"""Run arch-map over HTTP and serve the browser *studio* app.

    python -m arch_map.web          # -> http://127.0.0.1:8800/

Same FastMCP server as the stdio entrypoint (same tools + the same file-backed
MODEL), plus the routes the studio uses: `/` (the unified studio page),
`/assets/*` (its CSS/JS), `/api/model` (the full model), and `/api/act` (every
triage/edit). Actions the user takes in the browser POST to /api/act and are
saved to arch_state.json under a lock, so they survive a restart and show up for
the agent and any other open surface.
"""
from __future__ import annotations

import os

from .server import mcp

HOST = os.environ.get("ARCH_MAP_HOST", "127.0.0.1")
PORT = int(os.environ.get("ARCH_MAP_PORT", "8800"))


def main() -> None:
    mcp.run(transport="http", host=HOST, port=PORT)


if __name__ == "__main__":
    main()
