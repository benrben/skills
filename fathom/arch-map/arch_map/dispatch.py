"""The headless dispatch engine — the studio's agent-button RCE surface, isolated.

Extracted from server.py per adr-split-spine-hub. The security-relevant surface in
ONE module so it can be audited and unit-tested without booting the server: the
same-origin CSRF guard, the per-kind tool allowlist, the exact `claude -p` argv
(acceptEdits NOT bypass + hard deny rules + the arch-map MCP pinned to loopback),
and the stream-line condenser. The thin /api/dispatch route in server.py wires the
store + REGISTRY + the single-writer guard to these. Test surface: the guard
truth-table, the argv (allowlist / deny rules / permission-mode), and line parsing.
"""
from __future__ import annotations

import json
from urllib.parse import urlparse

_DISPATCH_TOOLS = {                    # per-kind tool allowlist; only fix/realize edit
    "fix":     "Read,Edit,Bash(git *),mcp__arch-map__*",
    "realize": "Read,Edit,Bash(git *),mcp__arch-map__*",
    "grill":   "Read,mcp__arch-map__*",
    "rescan":  "Read,mcp__arch-map__*",
    "triage":  "Read,mcp__arch-map__*",
}


def _dispatch_line(line: str) -> str:
    """Condense one stream-json event into a short human progress line (or '')."""
    try:
        ev = json.loads(line)
    except ValueError:
        return ""
    t = ev.get("type")
    if t == "system" and ev.get("subtype") == "init":
        return "agent started"
    if t == "assistant":
        for b in (ev.get("message", {}).get("content") or []):
            if b.get("type") == "tool_use":
                inp = b.get("input") or {}
                target = inp.get("file_path") or inp.get("command") or inp.get("id") or inp.get("pattern") or ""
                return (f"{b.get('name', 'tool')} {target}").strip()
            if b.get("type") == "text" and (b.get("text") or "").strip():
                return b["text"].strip()[:140]
    if t == "result":
        return "finished"
    return ""


def _dispatch_same_origin(request) -> bool:
    """CSRF guard: only the studio's own page may trigger a dispatch. Reject explicit
    cross-site fetches (Sec-Fetch-Site) and Origin/Host mismatches. Header-less callers
    (curl, tests, same-origin XHR) are allowed — the point is to block a foreign web
    page from POSTing to the loopback agent button."""
    site = request.headers.get("sec-fetch-site")
    if site and site not in ("same-origin", "same-site", "none"):
        return False
    origin = request.headers.get("origin")
    if origin:
        if urlparse(origin).netloc != request.headers.get("host", ""):
            return False
    return True


def build_dispatch_argv(claude: str, prompt: str, kind: str, cwd: str, port: str) -> list[str]:
    """The exact `claude -p` command for a dispatch — the RCE surface in one place.
    acceptEdits (NOT bypass), a per-kind allowlist, hard deny rules (no rm / git push /
    network), and the arch-map MCP pinned to 127.0.0.1. Audit and lock the agent here."""
    mcp_cfg = json.dumps({"mcpServers": {"arch-map": {"type": "http", "url": f"http://127.0.0.1:{port}/mcp"}}})
    return [
        claude, "-p", prompt,
        "--add-dir", cwd,
        "--permission-mode", "acceptEdits",
        "--allowedTools", _DISPATCH_TOOLS.get(kind, "Read,mcp__arch-map__*"),
        "--disallowedTools", "Bash(rm *),Bash(git push *),WebFetch,WebSearch",
        "--mcp-config", mcp_cfg,
        "--output-format", "stream-json", "--verbose",
        "--append-system-prompt",
        ("You are running headless from an arch-map studio button. Make the smallest "
         "change that satisfies the request, then reconcile the modules you touched on "
         "the arch-map spine via the arch-map MCP tools. Do not commit, push, or touch "
         "files outside the repo."),
    ]
