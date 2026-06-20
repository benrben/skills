"""reconcile-ledger — anchors, drift, and history for one arch map.

One concept does all the work: the **anchor**, a recorded reconcile event
{sha, ts, per-module snapshot of health/depth/coverage/domain}. Drift is
"what changed since the last anchor"; history is "the series of anchors".

Pure functions over an ArchModel — no I/O, no locks, no clocks. Persistence
rides the caller's Store: run record_anchor inside Store's locked mutate and
the anchor saves with the same atomic write as the rest of the map (the model
carries `anchors` as an opaque list). GitFacts is INJECTED, never imported —
anything with changed_files(since_sha) qualifies; tests use a tiny stub or a
real git-facts over a throwaway repo.

Invariants (the test surface):
  - anchors are kept oldest -> newest; append order is the authoritative order
    (timestamps are caller-supplied labels, never a sort key)
  - re-recording at the SAME sha replaces the newest anchor (no spam)
  - at most max_anchors kept (ring buffer, oldest dropped)
  - drift/staleness never raise; degraded outcomes carry a truthful `reason`
  - every return value is a JSON-ready copy: mutating it never alters the model
"""
from __future__ import annotations

import json
from datetime import datetime

ANCHOR_V = 1
METRICS = ("health", "depth", "coverage")

_NEVER = "never anchored — run a reconcile to set a baseline"


def _norm(p: str) -> str:
    p = str(p).replace("\\", "/")
    return p[2:] if p.startswith("./") else p


def _copy(x):
    return json.loads(json.dumps(x))


def _valid_anchors(model) -> list[dict]:
    """Tolerant reader: entries missing sha/ts/modules are skipped, the rest survive."""
    return [a for a in getattr(model, "anchors", [])
            if isinstance(a, dict) and a.get("sha") and a.get("ts")
            and isinstance(a.get("modules"), dict)]


# ---- RECORD ------------------------------------------------------------------
def record_anchor(model, head_sha: str, timestamp: str, max_anchors: int = 200) -> dict:
    """Snapshot every module (health via compute_metrics, depth/coverage/domain off
    the module) and append one anchor. Mutates `model` in place — the caller MUST
    run this inside Store's locked mutate for it to persist. ValueError on empty
    sha / non-ISO timestamp / max_anchors < 1, with the model untouched."""
    if not head_sha or not isinstance(head_sha, str):
        raise ValueError("record_anchor needs a non-empty head_sha")
    try:
        datetime.fromisoformat(str(timestamp))
    except (TypeError, ValueError):
        raise ValueError(f"timestamp {timestamp!r} is not ISO-8601") from None
    if max_anchors < 1:
        raise ValueError("max_anchors must be >= 1")
    metrics = model.compute_metrics()
    snap = {mid: {"health": metrics[mid]["health"], "depth": m.depth,
                  "coverage": m.coverage, "domain": m.domain}
            for mid, m in model.modules.items()}
    entry = {"v": ANCHOR_V, "sha": head_sha, "ts": str(timestamp),
             "moduleCount": len(snap), "modules": snap}
    anchors = list(getattr(model, "anchors", []))
    if anchors and isinstance(anchors[-1], dict) and anchors[-1].get("sha") == head_sha:
        anchors[-1] = entry          # re-reconcile at the same HEAD updates, never spams
    else:
        anchors.append(entry)
    model.anchors = anchors[-max_anchors:]
    return _copy(entry)


# ---- DRIFT -------------------------------------------------------------------
def modules_touched(model, paths) -> dict[str, list[str]]:
    """Pure file -> module attribution (the fathom:review one-liner). Delegates to
    the model's ownership rule: a path belongs to module m iff it equals an entry
    of m.files or sits under a directory entry. Unmatched paths silently vanish."""
    return model.owners_of([_norm(p) for p in paths])


def _degraded(reason: str, summary: str) -> dict:
    return {"anchored": False, "sinceSha": "", "sinceTs": "", "changedFiles": [],
            "modulesTouched": {}, "unmappedFiles": [], "summary": summary,
            "reason": reason}


def drift(model, git, since_sha: str | None = None) -> dict:
    """Full drift report since the last anchor (or an explicit `since_sha` baseline —
    the review-style question). NEVER raises; the same key set in every outcome.
    Degraded outcomes set anchored=False and a truthful `reason`."""
    anchors = _valid_anchors(model)
    if since_sha:
        base = since_sha
        base_ts = next((a["ts"] for a in reversed(anchors) if a["sha"] == since_sha), "")
    elif anchors:
        base, base_ts = anchors[-1]["sha"], anchors[-1]["ts"]
    else:
        return _degraded("no anchors", _NEVER)
    short = base[:7]
    if git is None:
        return _degraded("no git repo", f"anchored at {short} — git unavailable")
    try:
        changed = sorted({_norm(p) for p in git.changed_files(base)})
    except Exception as e:                       # any git failure degrades, visibly
        return _degraded(f"git error: {e}", f"anchored at {short} — git unavailable")
    touched = modules_touched(model, changed)
    owned = {f for fs in touched.values() for f in fs}
    if changed:
        summary = (f"{len(changed)} files changed, "
                   f"{len(touched)} modules touched since {short}")
    else:
        summary = f"clean — no changes since {short}"
    return _copy({"anchored": True, "sinceSha": base, "sinceTs": base_ts,
                  "changedFiles": changed, "modulesTouched": touched,
                  "unmappedFiles": [f for f in changed if f not in owned],
                  "summary": summary, "reason": ""})


def staleness_line(model, git) -> str:
    """THE digest one-liner. Total function: never raises, always one non-empty
    line. Four shapes: never-anchored | clean | N-files-M-modules | git-unavailable."""
    try:
        return drift(model, git)["summary"]
    except Exception:                            # belt-and-suspenders for the digest path
        return _NEVER


# ---- HISTORY -----------------------------------------------------------------
def last_anchor(model) -> dict | None:
    """Copy of the newest valid anchor, or None when never anchored. Never raises."""
    anchors = _valid_anchors(model)
    return _copy(anchors[-1]) if anchors else None


def history(model, module_id: str = "", domain: str = "",
            metrics: tuple = METRICS) -> dict:
    """Trend series across all anchors, oldest -> newest. Series lists are
    index-aligned with `anchors` (None where a module/domain was absent at that
    anchor). Zero anchors -> empty-not-error. With anchors present, an unknown
    module_id/domain raises ValueError, as does passing both filters or an
    unknown metric name."""
    if module_id and domain:
        raise ValueError("history takes module_id OR domain, not both")
    bad = [x for x in metrics if x not in METRICS]
    if bad:
        raise ValueError(f"unknown metric(s) {bad}; valid: {list(METRICS)}")
    anchors = _valid_anchors(model)
    if not anchors:
        return {"anchors": [], "series": {}}
    heads = [{"sha": a["sha"], "ts": a["ts"],
              "moduleCount": a.get("moduleCount", len(a["modules"]))} for a in anchors]
    series: dict[str, dict[str, list]] = {}
    if domain:
        if not any(s.get("domain") == domain
                   for a in anchors for s in a["modules"].values()):
            raise ValueError(f"domain '{domain}' appears in no anchor")
        per = {met: [] for met in metrics}
        for a in anchors:
            members = [s for s in a["modules"].values() if s.get("domain") == domain]
            for met in metrics:
                vals = [s.get(met) for s in members
                        if isinstance(s.get(met), (int, float))]
                per[met].append(round(sum(vals) / len(vals), 3) if vals else None)
        series[domain] = per
    else:
        if module_id and not any(module_id in a["modules"] for a in anchors):
            raise ValueError(f"module '{module_id}' appears in no anchor")
        keys = ([module_id] if module_id
                else sorted({mid for a in anchors for mid in a["modules"]}))
        for k in keys:
            per = {met: [] for met in metrics}
            for a in anchors:
                s = a["modules"].get(k)
                for met in metrics:
                    per[met].append(s.get(met) if s else None)
            series[k] = per
    return _copy({"anchors": heads, "series": series})
