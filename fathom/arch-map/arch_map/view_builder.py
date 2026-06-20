"""The on-brand ad-hoc view builder — model dict + spec in, draw payload out.

Extracted from server.py per adr-split-spine-hub. A pure transform with no I/O and
no Store: parse a freeform view spec into a typed TableSpec/BarSpec, filter the
model's modules by a predicate keyword, and build the {kind, columns, rows | metric,
bars} payload that archmap_render_view (and the /view page) draw verbatim. Numbers
are scaled to 0..100 for display here. Test surface: a fixed model dict + a spec ->
the exact payload.
"""
from __future__ import annotations

from dataclasses import dataclass, field

_STRENGTH_KEY = {"Strong": "strong", "Worth exploring": "worth", "Speculative": "speculative"}
_VIEW_COLS = ("id", "label", "domain", "depth", "coverage", "tests", "files", "suggestion")


def _has_tests(prose) -> bool:
    """The `tests` field is prose; "none — browser-only" is a recorded FACT of no
    tests, not a test reference, so it must not render as a checkmark."""
    t = (prose or "").strip()
    return bool(t) and not t.lower().startswith(("none", "n/a", "no "))

_VALID_METRICS = frozenset({"depth", "coverage"})
_VALID_GROUP_BY = frozenset({"module", "domain"})
_VALID_AGG = frozenset({"avg", "count"})


@dataclass
class TableSpec:
    of: str = "all"
    columns: list = field(default_factory=lambda: ["id", "domain", "depth", "coverage"])
    sortBy: str | None = None
    sortDir: str = "asc"
    title: str = ""


@dataclass
class BarSpec:
    metric: str = "depth"
    groupBy: str = "module"
    agg: str = "avg"
    of: str = "all"
    title: str = ""


def _parse_view_spec(spec: dict) -> TableSpec | BarSpec:
    """Parse a freeform spec dict into a typed TableSpec or BarSpec.
    Resolves aliases (filter->of, group->groupBy, sort->sortBy).
    Raises ValueError on invalid kind, metric, groupBy, or agg.
    """
    raw = spec or {}
    kind = (raw.get("kind") or "table").lower()
    if kind not in ("table", "bar"):
        raise ValueError(f"invalid view kind {kind!r}; expected 'table' or 'bar'")
    of = raw.get("of") or raw.get("filter") or "all"
    title = raw.get("title") or ""
    if kind == "bar":
        metric = (raw.get("metric") or "depth").lower()
        if metric not in _VALID_METRICS:
            raise ValueError(f"invalid metric {metric!r}; expected one of {sorted(_VALID_METRICS)}")
        groupBy = (raw.get("groupBy") or raw.get("group") or "module").lower()
        if groupBy not in _VALID_GROUP_BY:
            raise ValueError(f"invalid groupBy {groupBy!r}; expected one of {sorted(_VALID_GROUP_BY)}")
        agg = (raw.get("agg") or "avg").lower()
        if agg not in _VALID_AGG:
            raise ValueError(f"invalid agg {agg!r}; expected one of {sorted(_VALID_AGG)}")
        return BarSpec(metric=metric, groupBy=groupBy, agg=agg, of=of, title=title)
    sortRaw = raw.get("sortBy") or raw.get("sort")
    if isinstance(sortRaw, dict):
        sortDir = sortRaw.get("dir", "asc")
        sortBy = sortRaw.get("by")
    else:
        sortBy = sortRaw
        sortDir = raw.get("sortDir", "asc")
    columns = list(raw.get("columns") or ["id", "domain", "depth", "coverage"])
    return TableSpec(of=of, columns=columns, sortBy=sortBy, sortDir=sortDir, title=title)


def _view_filter(modules: list[dict], of: str, model: dict) -> list[dict]:
    """Select modules by a simple predicate keyword (or a domain name)."""
    of = (of or "all").lower()
    orphans = set(model.get("orphans", []))

    def keep(m: dict) -> bool:
        d, c = (m.get("depth") or 0), (m.get("coverage") or 0)
        if of in ("", "all"): return True
        if of in ("orphans", "orphan", "not-connected"): return m["id"] in orphans
        if of == "leaks": return bool(m.get("leaksTo"))
        if of in ("suggestions", "proposals", "open"): return bool(m.get("suggestion"))
        if of == "updated": return bool(m.get("updated"))
        if of in ("low-coverage", "low"): return c < 0.4
        if of == "shallow": return d < 0.34
        if of == "mid": return 0.34 <= d < 0.67
        if of == "deep": return d >= 0.67
        return m.get("domain") == of           # otherwise treat as a domain name
    return [m for m in modules if keep(m)]


def _build_view(model: dict, spec: TableSpec | BarSpec) -> dict:
    """Turn a typed view spec + a full model into a prepared view payload the
    renderer draws verbatim (numbers already scaled to 0..100 for display)."""
    of = spec.of
    sel = _view_filter(model.get("modules", []), of, model)
    label = "all modules" if str(of).lower() in ("", "all") else of
    kind = "bar" if isinstance(spec, BarSpec) else "table"
    out = {"kind": kind, "title": spec.title or f"{kind} · {label}",
           "repo": model.get("repo", ""), "count": len(sel)}

    if isinstance(spec, BarSpec):
        out["metric"], out["groupBy"] = spec.metric, spec.groupBy
        if spec.groupBy == "domain":
            buckets: dict[str, list[float]] = {}
            for m in sel:
                buckets.setdefault(m.get("domain", "—"), []).append(m.get(spec.metric) or 0)
            if spec.agg == "count":
                mx = max((len(v) for v in buckets.values()), default=1) or 1
                bars = [{"label": d, "value": str(len(v)), "pct": round(len(v) / mx * 100)} for d, v in buckets.items()]
            else:
                bars = [{"label": d, "value": f"{round(sum(v) / len(v) * 100)}%", "pct": round(sum(v) / len(v) * 100)} for d, v in buckets.items()]
        else:
            bars = [{"label": m["id"], "value": f"{round((m.get(spec.metric) or 0) * 100)}%", "pct": round((m.get(spec.metric) or 0) * 100)} for m in sel]
        bars.sort(key=lambda b: b["pct"], reverse=True)
        out["bars"] = bars
    else:
        cols = [c for c in spec.columns if c in _VIEW_COLS]
        cols = cols or ["id", "domain", "depth", "coverage"]
        rows = []
        for m in sel:
            row = {}
            for c in cols:
                if c in ("depth", "coverage"): row[c] = round((m.get(c) or 0) * 100)
                elif c == "suggestion":
                    s = m.get("suggestion")
                    row[c] = {"strength": _STRENGTH_KEY.get(s["strength"], "speculative"), "label": s["strength"]} if s else None
                elif c == "files": row[c] = len(m.get("files") or [])
                elif c == "tests": row[c] = "✓" if _has_tests(m.get("tests")) else ""
                else: row[c] = m.get(c)
            rows.append(row)
        if spec.sortBy in cols:
            rows.sort(key=lambda r: (r.get(spec.sortBy) is None, r.get(spec.sortBy)), reverse=(spec.sortDir == "desc"))
        out["columns"], out["rows"] = cols, rows
    return out
