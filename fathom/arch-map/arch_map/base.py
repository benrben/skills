"""Shared server base — the runtime substrate every tool, route, and read helper
sits on (extracted from server.py per the server-cleanup plan /
adr-surface-register-inversion).

It owns the things server.py used to keep as module-level state and that the
read-projection leaf (reads.py) and the grill prompt also need:

  * the file-backed map REGISTRY (one JSON per project under MAPS_DIR),
  * the _guard/_fail error envelope every tool/read wraps its work in,
  * the ephemeral per-process run-set (_BOARD_RUNNING / _running_keys) the board
    projection overlays as the ⚙ live marker,
  * the repo-root + safe `git worktree list` helpers.

Nothing here imports server, so reads.py / prompts.py import REGISTRY (and the
helpers) DOWNWARD instead of reaching up into server — which is what breaks the
server<->resources and server<->prompts import cycles. server.py imports every
name back, so srv.REGISTRY / srv._guard / srv._running_keys resolve unchanged.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from .map_registry import MapRegistry
from .git_facts import NotARepo, UnknownSha
from .worktrees import WorktreeError

if TYPE_CHECKING:                       # type-only import keeps this a leaf
    from .worktrees import Worktrees

HERE = Path(__file__).parent

# Persistent map storage. Honors $ARCH_MAP_DATA_DIR (the plugin's .mcp.json sets this
# to ${CLAUDE_PLUGIN_DATA}) so user maps survive plugin updates and read-only install
# trees; falls back to maps/ beside the package for local dev. Created on first use.
_DATA_DIR = os.environ.get("ARCH_MAP_DATA_DIR")
MAPS_DIR = ((Path(_DATA_DIR).expanduser() / "maps") if _DATA_DIR else (HERE.parent / "maps")).resolve()
MAPS_DIR.mkdir(parents=True, exist_ok=True)

REGISTRY = MapRegistry(MAPS_DIR)


# Every string an agent reads is an instruction: when a dispatcher fails, the error
# must carry the call context, the atomicity guarantee, and a next step — not a bare
# KeyError. Writes go through Store (load -> mutate -> save under one lock), so a
# failed write means NOTHING was persisted.
def _guard(call: str, write: bool, hint: str, fn):
    try:
        return fn()
    except (KeyError, ValueError) as e:            # expected — keep the type, add context
        msg = e.args[0] if e.args else str(e)
        raise type(e)(_fail(call, str(msg), write, hint)) from e
    except Exception as e:  # unexpected — still reach the agent with context
        raise ValueError(_fail(call, f"{type(e).__name__}: {e}", write, hint)) from e


def _fail(call: str, msg: str, write: bool, hint: str) -> str:
    atomic = " Nothing was written — writes are all-or-nothing." if write else ""
    return f"{call} failed: {msg}.{atomic}" + (f" {hint}" if hint else "")


# Ephemeral per-process run state: which board task an agent is live in. The board
# projection overlays this as the ⚙ marker; api_dispatch mutates it. Never persisted.
_BOARD_RUNNING: set = set()        # (map, planId, stepId) — a task agent is live in its worktree


def _running_keys(map_id: str) -> set:
    """The (planId, stepId) pairs a task agent is actively dispatched on, for `map`
    — the board's ⚙ live marker. Ephemeral per-process state, never persisted."""
    return {(p, s) for (m, p, s) in _BOARD_RUNNING if m == map_id}


def _repo_root(root: str) -> str:
    return root or os.getcwd()


def _safe_git_worktrees(wm: "Worktrees") -> list[dict]:
    """`git worktree list`, or [] when there's no repo/git — sync/list never error
    just because the server isn't running inside a git work tree."""
    try:
        return wm.list()
    except (NotARepo, UnknownSha, WorktreeError):
        return []
