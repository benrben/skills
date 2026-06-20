"""archmap:// read-only RESOURCES — the ONLY way an MCP client reads stored state
(spec-spine-resources). The read tools are gone; these resources took their place.

Each template reuses the SAME projection the old read tools built (the `_impl` /
read-helper functions in server.py — no projection logic is duplicated here) and
has NO side effects. Reads go through ``REGISTRY.store(map)``, which raises
``KeyError`` for an unknown map — it NEVER creates or ensures one; a missing map/id
surfaces as a recoverable ``ResourceError`` rather than a phantom empty map.

SERIALIZATION (token optimization): every structured resource returns ``_yaml(payload)``
as a STRING with ``mime_type="application/yaml"`` — YAML drops JSON's braces/quotes/
commas and uses indentation for nesting, which is markedly cheaper in tokens. The one
exception is ``archmap://{map}/doc/{id}``, which returns MARKDOWN (``text/markdown``):
a YAML frontmatter block + the raw markdown body verbatim (mermaid-fenced for diagram
docs) — returning prose verbatim avoids JSON-escaping it.

QUERY PARAMS ride as RFC 6570 query expansion on the URI template (e.g.
``archmap://{map}/model{?domain,plane,lifecycle,sort,dir,q,limit,offset}``); FastMCP
3.x parses them into the function's optional kwargs (confirmed on 3.3.1 — see the
in-memory Client probe in test_spine_resources). Semantics: domain/plane/lifecycle/
type/tag/status = exact match; q = case-insensitive substring; sort = field name;
dir = asc|desc; limit/offset = paging (total_count/has_more/next_offset ride in the
payload). ``register(mcp)`` is called once from server.py after the tools are defined.
"""
from __future__ import annotations

import yaml
from fastmcp.exceptions import ResourceError
from fastmcp.resources import ResourceContent

from . import server as srv

# MIME types for the two surfaces. YAML for every structured payload (cuts JSON's
# brace/quote/comma token overhead); Markdown for the single doc (prose verbatim,
# no JSON-escaping). FastMCP 3.x carries the template's declared mime in
# list_resource_templates, but a TEMPLATE read's content block defaults to
# text/plain unless we return an explicit ResourceContent — so we wrap every
# return in [ResourceContent(text, mime_type=...)] to pin the block's mime too.
_YAML_MIME = "application/yaml"
_MD_MIME = "text/markdown"


def _yaml(obj) -> str:
    """Serialize a payload to YAML — the generic helper every structured resource
    builds on. Block style (not flow) + insertion order preserved + unicode kept raw,
    so the output reads as indented key: value lines with no JSON syntax overhead."""
    return yaml.safe_dump(obj, default_flow_style=False, sort_keys=False,
                          allow_unicode=True)


def _yaml_block(obj):
    """A YAML resource read result: _yaml(obj) wrapped as one application/yaml
    content block so the per-read mime matches the declared template mime."""
    return [ResourceContent(_yaml(obj), mime_type=_YAML_MIME)]


def _md_block(text: str):
    """A Markdown resource read result (the doc resource): one text/markdown block."""
    return [ResourceContent(text, mime_type=_MD_MIME)]


def _recoverable(fn):
    """Run a payload builder, turning the read methods' KeyError/ValueError into a
    recoverable ResourceError (so a bad map/id is a clear, correctable message —
    never a phantom map and never a raw stack trace)."""
    try:
        return fn()
    except (KeyError, ValueError) as e:
        raise ResourceError(str(e).strip("'\"")) from e


# ---- shared query helpers ----------------------------------------------------

def _as_int(v, default: int = 0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _q_match(text: str, q: str) -> bool:
    """Case-insensitive substring test (the `q` free-text search semantics)."""
    return q.lower() in (text or "").lower()


def _sort_rows(rows: list[dict], sort: str, direction: str) -> list[dict]:
    """Stable sort `rows` by field `sort` (asc|desc). A blank field leaves order
    untouched; missing values sort as the empty string / 0 so it never raises."""
    if not sort:
        return rows
    rev = (direction or "asc").lower() == "desc"

    def key(r):
        v = r.get(sort)
        return (v is None, v if v is not None else "")
    return sorted(rows, key=key, reverse=rev)


def _page(rows: list[dict], limit, offset) -> dict:
    """Apply limit/offset paging, returning the page + the metadata block
    (total_count/has_more/next_offset) the contract pins."""
    total = len(rows)
    off = max(0, _as_int(offset, 0))
    lim = _as_int(limit, 0)
    page = rows[off:off + lim] if lim and lim > 0 else rows[off:]
    end = off + lim if (lim and lim > 0) else total
    return {"rows": page, "total_count": total,
            "has_more": end < total,
            "next_offset": end if end < total else None}


# ---- registration ------------------------------------------------------------

def register(mcp) -> None:
    """Register the archmap:// read-only resource templates on `mcp`. Called once
    from server.py after `mcp` and the read helpers are defined."""

    # ---- maps ----------------------------------------------------------------
    @mcp.resource("archmap://maps{?q}", mime_type=_YAML_MIME)
    def maps(q: str = ""):
        """Every architecture map (id, repo label, module/proposal counts). `q`
        filters on id/repo (case-insensitive substring)."""
        def run():
            out = srv.list_maps(limit=0, offset=0)   # limit<=0 -> the whole list
            ms = out["maps"]
            if q:
                ms = [m for m in ms if _q_match(m.get("id", ""), q)
                      or _q_match(m.get("repo", ""), q)]
            return _yaml_block({"maps": ms, "default": out["default"],
                                "total_count": len(ms),
                                "has_more": False, "next_offset": None})
        return _recoverable(run)

    # ---- model (the modules list, filterable/sortable/pageable) --------------
    @mcp.resource(
        "archmap://{map}/model{?domain,plane,lifecycle,sort,dir,q,limit,offset}",
        mime_type=_YAML_MIME)
    def model(map: str, domain: str = "", plane: str = "", lifecycle: str = "",
              sort: str = "", dir: str = "asc", q: str = "",
              limit: int = 0, offset: int = 0):
        """A map's full model. The modules list takes optional filters: domain/plane/
        lifecycle (exact match), q (substring over id/label/iface), sort+dir, and
        limit/offset paging (paging metadata rides in the payload)."""
        def run():
            full = srv.get_full_model(map)            # raises KeyError -> no phantom map
            mods = full.get("modules") or []
            if domain:
                mods = [m for m in mods if m.get("domain") == domain]
            if plane:
                mods = [m for m in mods if m.get("plane") == plane]
            if lifecycle:
                mods = [m for m in mods if m.get("lifecycle") == lifecycle]
            if q:
                mods = [m for m in mods if _q_match(m.get("id", ""), q)
                        or _q_match(m.get("label", ""), q)
                        or _q_match(m.get("iface", ""), q)]
            mods = _sort_rows(mods, sort, dir)
            paged = _page(mods, limit, offset)
            full["modules"] = paged["rows"]
            full["total_count"] = paged["total_count"]
            full["has_more"] = paged["has_more"]
            full["next_offset"] = paged["next_offset"]
            return _yaml_block(full)
        return _recoverable(run)

    # ---- digest --------------------------------------------------------------
    @mcp.resource("archmap://{map}/digest{?domain}", mime_type=_YAML_MIME)
    def digest(map: str, domain: str = ""):
        """A map's digest (counts, orphans, open suggestions, worst-health modules).
        Pass `domain` to get the full module records for just that domain."""
        return _recoverable(lambda: _yaml_block(srv.show_map(map, domain=domain)))

    # ---- board ---------------------------------------------------------------
    @mcp.resource("archmap://{map}/board", mime_type=_YAML_MIME)
    def board(map: str):
        """A map's task board — the SAME projection the studio board renders."""
        return _recoverable(lambda: _yaml_block(srv.board(map)))

    # ---- one module ----------------------------------------------------------
    @mcp.resource("archmap://{map}/module/{id}", mime_type=_YAML_MIME)
    def module(map: str, id: str):
        """One module's full record."""
        return _recoverable(lambda: _yaml_block(srv.get_module(map, id)))

    # ---- metrics: all (sort/page) -------------------------------------------
    @mcp.resource("archmap://{map}/metrics{?sort,dir,limit,offset}",
                  mime_type=_YAML_MIME)
    def metrics_all(map: str, sort: str = "", dir: str = "asc",
                    limit: int = 0, offset: int = 0):
        """Every module's computed graph metrics, keyed by id. sort+dir order by a
        metric field; limit/offset page (paging metadata rides in the payload)."""
        def run():
            out = srv.get_metrics(map, module=None, limit=0, offset=0)
            metrics = out["metrics"]                  # {id: {fanIn, ...}}
            rows = [{"id": mid, **vals} for mid, vals in metrics.items()]
            rows = _sort_rows(rows, sort, dir)
            paged = _page(rows, limit, offset)
            return _yaml_block({"map": map, "metrics": paged["rows"],
                                "total_count": paged["total_count"],
                                "has_more": paged["has_more"],
                                "next_offset": paged["next_offset"]})
        return _recoverable(run)

    # ---- metrics: one module -------------------------------------------------
    @mcp.resource("archmap://{map}/metrics/{module}", mime_type=_YAML_MIME)
    def metrics_one(map: str, module: str):
        """One module's computed graph metrics."""
        return _recoverable(lambda: _yaml_block(srv.get_metrics(map, module=module)))

    # ---- docs list -----------------------------------------------------------
    @mcp.resource("archmap://{map}/docs{?type,tag,status,domain,q}",
                  mime_type=_YAML_MIME)
    def docs(map: str, type: str = "", tag: str = "", status: str = "",
             domain: str = "", q: str = ""):
        """Doc SUMMARIES (no bodies). Filters: type/status (exact), tag (membership),
        domain (the doc's resolved scope contains a module of that domain), q
        (substring over title/summary)."""
        def run():
            full = srv.list_docs(map, include_membership=False, limit=0, offset=0)
            rows = full["docs"]
            if type:
                rows = [d for d in rows if d.get("type") == type]
            if status:
                rows = [d for d in rows if d.get("status") == status]
            if tag:
                rows = [d for d in rows if tag in (d.get("tags") or [])]
            if domain:
                mdl = srv.get_full_model(map)
                in_dom = {m["id"] for m in (mdl.get("modules") or [])
                          if m.get("domain") == domain}
                membership = mdl.get("docMembership") or {}
                dom_docs = {did for mid in in_dom for did in (membership.get(mid) or [])}
                rows = [d for d in rows if d.get("id") in dom_docs]
            if q:
                rows = [d for d in rows if _q_match(d.get("title", ""), q)
                        or _q_match(d.get("summary", ""), q)]
            return _yaml_block({"map": map, "docs": rows, "total_count": len(rows),
                                "has_more": False, "next_offset": None})
        return _recoverable(run)

    # ---- one doc (MARKDOWN) --------------------------------------------------
    _FRONTMATTER_KEYS = ("id", "type", "title", "status", "tags", "scope",
                         "supersedes", "adrRef", "author", "created", "updated")

    @mcp.resource("archmap://{map}/doc/{id}", mime_type=_MD_MIME)
    def doc(map: str, id: str):
        """One doc as MARKDOWN: a YAML frontmatter block (id/type/title/status/tags/
        scope/supersedes/adrRef/author/created/updated) + the raw markdown body
        verbatim. A `diagram` doc's body is wrapped in a fenced mermaid block."""
        def run():
            d = srv.get_doc(map, id)
            meta = {k: d.get(k) for k in _FRONTMATTER_KEYS if k in d}
            body = d.get("body") or ""
            if d.get("type") == "diagram":
                body = "```mermaid\n" + body + ("" if body.endswith("\n") else "\n") + "```"
            return _md_block("---\n" + _yaml(meta) + "---\n\n" + body)
        return _recoverable(run)

    # ---- plans list ----------------------------------------------------------
    @mcp.resource("archmap://{map}/plans{?status}", mime_type=_YAML_MIME)
    def plans(map: str, status: str = ""):
        """The plans list (id/title/status/step+module counts). `status` filters
        exactly (draft|active|done|abandoned)."""
        return _recoverable(lambda: _yaml_block(srv.list_plans(map, status=status)))

    # ---- one plan ------------------------------------------------------------
    @mcp.resource("archmap://{map}/plan/{id}", mime_type=_YAML_MIME)
    def plan(map: str, id: str):
        """One plan's full record (its steps included)."""
        return _recoverable(lambda: _yaml_block(srv.get_plan(map, id)))

    # ---- worktrees list ------------------------------------------------------
    @mcp.resource("archmap://{map}/worktrees{?status}", mime_type=_YAML_MIME)
    def worktrees(map: str, status: str = ""):
        """The spine worktrees (the STORED state) + the live git worktree list.
        `status` filters the spine worktrees exactly (active|merged|removed)."""
        return _recoverable(lambda: _yaml_block(srv.list_worktrees(map, status=status)))
