"""The canonical /deepen grilling walkthrough text — the SINGLE source of truth
shared by the archmap_grilling(start) tool, the /api/grill route, and the
grill_candidate prompt (extracted from server.py per the server-cleanup plan /
adr-surface-register-inversion).

A pure leaf: it formats text from an already-resolved Module + Suggestion (and,
for the keyed variants, reads them off a Store passed in). No `mcp`, no import of
server — so server.py imports these names back (namespace unchanged) and
prompts.py imports the builder DOWNWARD instead of reaching up into server,
breaking the server<->prompts import cycle.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:                       # type-only — keeps this a runtime-pure leaf
    from .model import Module
    from .store import Store


CANON_GRILL_PROMPT = (
    "Enter the /deepen grilling loop for {head} (map '{map}', module '{module}'"
    "{sid}, depth {depth:.2f}, coverage {cov:.0%}). Call grilling(action='mark') as you "
    "begin, then grilling(action='finish', decision=accepted|deferred|rejected, note, adr) "
    "to close it; "
    "offer an ADR on a load-bearing rejection."
)


def _first_open(m: "Module"):
    """The module's first still-open candidate (undecided, not closed), or None."""
    return next((s for s in m.suggestions if s.decision == "" and s.status != "done"), None)


def _grill_text(map: str, m: "Module", s) -> str:
    """The canonical /deepen walkthrough text for one module + (optional) candidate.
    Single source of truth shared by the archmap_grilling(start) tool, the
    archmap:// flow, and the grill_candidate prompt — given the already-resolved
    module and suggestion so each caller resolves them however it keys (module-first
    for the tool, suggestion-first for the prompt)."""
    head = s.title if s else f"the {m.label} module"
    sid = f", suggestion '{s.id}'" if s else ""
    return CANON_GRILL_PROMPT.format(head=head, map=map, module=m.id, sid=sid,
                                     depth=m.depth, cov=m.coverage)


def _grill_prompt(store: "Store", map: str, module: str) -> str:
    m = store.modules[module]
    return _grill_text(map, m, _first_open(m))


def _grill_prompt_for_suggestion(store: "Store", map: str, suggestion_id: str) -> str:
    """Build the SAME walkthrough text the archmap_grilling(start) tool builds, but
    keyed by suggestion id (raises KeyError if the suggestion — and thus its map —
    does not exist; never creates anything)."""
    m, s = store._load()._find_suggestion(suggestion_id)
    return _grill_text(map, m, s)
