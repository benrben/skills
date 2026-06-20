"""Interface tests for the **dispatch** RCE surface (dispatch.py).

The whole point of pulling this out of server.py: the agent-button command and its
guard are now auditable in isolation. The interface a caller must know — the
same-origin guard's exact accept/reject rule, the per-kind tool allowlist baked into
the `claude -p` argv (acceptEdits, deny rm/push/network, MCP pinned to loopback), and
the stream-line condenser. Pure functions; no server, no subprocess spawned.
"""
import json

import pytest

from arch_map.dispatch import _dispatch_line, _dispatch_same_origin, build_dispatch_argv


class _Req:
    """Minimal stand-in for a Starlette request: just case-exact header lookups."""
    def __init__(self, **headers):
        self.headers = headers


# ---- same-origin CSRF guard -------------------------------------------------

def test_same_origin_allows_header_less_caller():
    assert _dispatch_same_origin(_Req()) is True          # curl / tests / same-origin XHR

@pytest.mark.parametrize("site", ["same-origin", "same-site", "none"])
def test_same_origin_allows_known_sec_fetch_sites(site):
    assert _dispatch_same_origin(_Req(**{"sec-fetch-site": site})) is True

def test_same_origin_refuses_cross_site_fetch():
    assert _dispatch_same_origin(_Req(**{"sec-fetch-site": "cross-site"})) is False

def test_same_origin_refuses_foreign_origin_host_mismatch():
    req = _Req(origin="http://evil.example", host="127.0.0.1:8800")
    assert _dispatch_same_origin(req) is False

def test_same_origin_allows_matching_origin_host():
    req = _Req(origin="http://127.0.0.1:8800", host="127.0.0.1:8800")
    assert _dispatch_same_origin(req) is True


# ---- the claude -p argv: the locked-down RCE surface ------------------------

def test_argv_is_acceptEdits_not_bypass_with_deny_rules():
    argv = build_dispatch_argv("/usr/bin/claude", "do it", "fix", "/repo", "8800")
    assert argv[0] == "/usr/bin/claude" and argv[1] == "-p" and argv[2] == "do it"
    assert "--permission-mode" in argv and argv[argv.index("--permission-mode") + 1] == "acceptEdits"
    deny = argv[argv.index("--disallowedTools") + 1]
    assert "Bash(rm *)" in deny and "Bash(git push *)" in deny and "WebFetch" in deny

def test_argv_allowlist_is_per_kind():
    fix = build_dispatch_argv("c", "p", "fix", "/r", "8800")
    grill = build_dispatch_argv("c", "p", "grill", "/r", "8800")
    assert "Edit" in fix[fix.index("--allowedTools") + 1]            # fix may edit source
    assert "Edit" not in grill[grill.index("--allowedTools") + 1]    # grill is read-only

def test_argv_unknown_kind_falls_back_to_read_only():
    argv = build_dispatch_argv("c", "p", "mystery", "/r", "8800")
    assert argv[argv.index("--allowedTools") + 1] == "Read,mcp__arch-map__*"

def test_argv_pins_mcp_to_loopback_on_the_given_port():
    argv = build_dispatch_argv("c", "p", "fix", "/r", "9001")
    cfg = json.loads(argv[argv.index("--mcp-config") + 1])
    assert cfg["mcpServers"]["arch-map"]["url"] == "http://127.0.0.1:9001/mcp"


# ---- stream-line condenser --------------------------------------------------

def test_line_init_and_result():
    assert _dispatch_line(json.dumps({"type": "system", "subtype": "init"})) == "agent started"
    assert _dispatch_line(json.dumps({"type": "result"})) == "finished"

def test_line_tool_use_names_its_target():
    ev = {"type": "assistant", "message": {"content": [
        {"type": "tool_use", "name": "Edit", "input": {"file_path": "a.py"}}]}}
    assert _dispatch_line(json.dumps(ev)) == "Edit a.py"

def test_line_text_is_truncated():
    ev = {"type": "assistant", "message": {"content": [{"type": "text", "text": "x" * 200}]}}
    assert len(_dispatch_line(json.dumps(ev))) == 140

def test_line_junk_is_empty():
    assert _dispatch_line("not json") == ""
    assert _dispatch_line(json.dumps({"type": "whatever"})) == ""
