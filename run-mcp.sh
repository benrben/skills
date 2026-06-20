#!/usr/bin/env bash
# Run the arch-map MCP server (fathom/arch-map).
#
#   ./run-mcp.sh          stdio MCP server — what an MCP host launches
#   ./run-mcp.sh web      browser studio at http://127.0.0.1:8800/
#
# Register with Claude Code:
#   claude mcp add arch-map -- /Users/benreich/skills/run-mcp.sh
set -euo pipefail

ARCH_MAP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/fathom/arch-map"

if [[ "${1:-}" == "web" ]]; then
  exec uv run --directory "$ARCH_MAP_DIR" python -m arch_map.web
fi

exec uv run --directory "$ARCH_MAP_DIR" arch-map
