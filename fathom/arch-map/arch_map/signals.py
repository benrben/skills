"""Structural + craft SIGNAL registry — the SINGLE source of truth for what fires,
its family, and the human why/how (extracted from server.py per the server-cleanup
plan / adr-surface-register-inversion).

A leaf: pure functions over a module object + its computed metrics dict. No
REGISTRY, no Store, no I/O — so the studio, the scan_signals tool, the /api/model
route, the tests, and skills/design/scripts/whatif_craft.py all read THIS list
instead of re-encoding the thresholds. server.py imports the names back, so
``arch_map.server.SIGNAL_REGISTRY`` / ``_compute_signals`` resolve unchanged.
"""
from __future__ import annotations


def _craft(m):
    return getattr(m, "craft", None) or {}


_T = {"maxFnLen": 50, "maxArgs": 4, "maxNesting": 4, "methodCount": 12, "magicNumbers": 3,
      "commentedOut": 1, "size": 2.0, "depthGap": 0.3}   # craft thresholds — tunable per project


# Declarative signal registry — the SINGLE source of truth for what fires, its family,
# and the human why/how. _compute_signals iterates it; archmap_signal_registry exposes
# it so the studio + docs render from THIS list instead of re-encoding the thresholds.
SIGNAL_REGISTRY = [
    ("danger-zone", "architecture", lambda m, mx: mx["churn"] >= 0.4 and m.coverage < 0.4,
     "high churn + low coverage (highest risk)", "add tests before the next change lands"),
    ("critical-path-untested", "architecture", lambda m, mx: mx["blastRadius"] >= 10 and m.coverage < 0.6,
     "wide blast radius + low coverage", "cover the interface; a break here ripples far"),
    ("circular-dep", "architecture", lambda m, mx: mx["inCycle"],
     "part of a dependency cycle", "break the cycle behind a seam so the parts test alone"),
    ("needs-refactor", "architecture", lambda m, mx: mx["fanOut"] >= 6 and m.depth < 0.5,
     "high fan-out + low depth", "consolidate behind a deeper interface"),
    ("god-module", "architecture", lambda m, mx: mx["fanIn"] >= 8 and mx["fanOut"] >= 6,
     "high fan-in AND fan-out", "split responsibilities; it does too much for too many"),
    ("bottleneck", "architecture", lambda m, mx: mx["fanIn"] >= 8 and m.depth < 0.4,
     "high fan-in + low depth", "deepen; many depend on a shallow interface"),
    ("test-first", "architecture", lambda m, mx: mx["blastRadius"] >= 5 and m.coverage < 0.3,
     "wide blast radius + very low coverage", "write interface tests first, here"),
    ("unstable-api", "architecture", lambda m, mx: mx["instability"] > 0.7 and mx["fanIn"] >= 3,
     "fragile yet depended-upon", "stabilize behind a thin, unchanging contract"),
    ("split-candidate", "architecture", lambda m, mx: mx["fanOut"] >= 5 and mx["coupling"] >= 3,
     "high fan-out across domains", "split along the domain seam"),
    ("bulky-impl", "architecture", lambda m, mx: m.size >= 2.0 and m.depth < 0.5,
     "large implementation mass for little depth (MINIMALISM.md)", "climb the ladder behind the seam"),
    ("leaky-seam", "architecture", lambda m, mx: bool(m.leaksTo),
     "has seam violations (leaksTo)", "route the access through the interface"),
    ("long-function", "craft", lambda m, mx: _craft(m).get("maxFnLen", 0) >= _T["maxFnLen"],
     "a function exceeds ~50 lines", "extract named steps until each reads at one level"),
    ("too-many-args", "craft", lambda m, mx: _craft(m).get("maxArgs", 0) >= _T["maxArgs"],
     "a function takes >= 4 arguments", "wrap related arguments in an object"),
    ("deep-nesting", "craft", lambda m, mx: _craft(m).get("maxNesting", 0) >= _T["maxNesting"],
     "nesting >= 4 levels deep", "extract the inner blocks into named functions"),
    ("large-class", "craft", lambda m, mx: m.size >= _T["size"] and _craft(m).get("methodCount", 0) >= _T["methodCount"],
     "a large module with many methods", "split by responsibility (SRP)"),
    ("untested-interface", "craft", lambda m, mx: m.depth >= 0.6 and m.coverage < 0.5,
     "a deep module whose interface is thinly covered", "the interface is the test surface; cover it"),
    ("magic-number", "craft", lambda m, mx: _craft(m).get("magicNumbers", 0) >= _T["magicNumbers"],
     "unnamed numeric literals", "replace with named constants"),
    ("comment-smell", "craft", lambda m, mx: _craft(m).get("commentedOutBlocks", 0) >= _T["commentedOut"],
     "commented-out code / noise", "delete it; version control remembers"),
    ("depth-overstated", "architecture",
     lambda m, mx: getattr(m, "depthProxy", 0) > 0 and (m.depth - m.depthProxy) >= _T["depthGap"],
     "judged depth far above the measured leverage proxy (honesty check)",
     "re-run the deletion test; the interface may be wider than it looks"),
]
_CRAFT_SIGNALS = {sid for sid, fam, *_ in SIGNAL_REGISTRY if fam == "craft"}


def _compute_signals(m, mx: dict) -> list[str]:
    """The signal ids that fire for a module + its metrics, from SIGNAL_REGISTRY."""
    return [sid for sid, fam, fn, why, how in SIGNAL_REGISTRY if fn(m, mx)]
