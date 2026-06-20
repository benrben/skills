"""Interface tests for the archmap:// READ RESOURCES + the grill_candidate PROMPT
(spec-spine-resources / spec-spine-prompts).

Reads of stored state are RESOURCE-ONLY now (the read tools were removed), so this
file is the home of the read surface: it exercises EVERY resource template and EVERY
query param (filter / q substring search / sort+dir / limit+offset paging) over a real
in-memory FastMCP ``Client(srv.mcp)`` — the full protocol, no subprocess — against the
same temp REGISTRY the `reg` fixture points the server module at. Structured resources
return YAML (parsed with ``yaml.safe_load``); the single doc returns Markdown (frontmatter
+ body). The Client API is async; each test drives it through ``asyncio.run``.

It also confirms the installed FastMCP supports RFC-6570 query-param resource templates,
and holds the no-auto-create + get_full_model-paging assertions (moved here from the old
read tools): a missing map raises and creates NO phantom map.
"""
import asyncio

import pytest
import yaml
from fastmcp import Client
from mcp.shared.exceptions import McpError

import arch_map.server as srv


def _read(c, uri):
    """Read a resource and return (text, mimeType) of the first content block."""
    async def go():
        r = await c.read_resource(uri)
        block = r[0] if isinstance(r, list) else r.contents[0]
        return block.text, block.mimeType
    return go()


def _yaml_of(result_tuple):
    return yaml.safe_load(result_tuple[0])


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture
def seeded(reg):
    """A temp map 'm' with three modules (two domains), two docs (note + diagram),
    one plan with a step, one flagged candidate — enough to drive every filter."""
    srv.modules(action="add", map="m", items=[
        {"id": "a", "label": "Alpha", "domain": "ui", "iface": "render()",
         "depth": 0.2, "plane": "actual", "lifecycle": "built"},
        {"id": "b", "label": "Beta", "domain": "core", "depth": 0.8,
         "plane": "actual", "lifecycle": "built"},
        {"id": "c", "label": "Gamma", "domain": "ui", "depth": 0.5,
         "plane": "intended", "lifecycle": "planned"},
    ])
    srv.docs(action="add", map="m", doc_id="d1", type="note", title="A note",
             summary="needle in summary", body="the body text", scope_domain="ui",
             tags=["keep"], status="accepted")
    srv.docs(action="add", map="m", doc_id="dg", type="diagram", title="Diagram",
             body="graph TD; A-->B", scope_domain="core")   # core-only, so ?domain=ui excludes it
    srv.plans(action="create", map="m", plan_id="p1", title="Plan One")
    srv.plans(action="add_steps", map="m", plan_id="p1",
              steps=[{"id": "s1", "title": "step"}])
    srv.plans(action="update", map="m", plan_id="p1", status="active")
    flag = srv.suggestions(action="flag", map="m", module="a",
                           title="deepen A", strength="Strong")
    return {"map": "m", "module": "a", "suggestion_id": flag["suggestion_id"]}


# ---- the resource/prompt catalogue ------------------------------------------

def test_lists_every_resource_template_and_prompt(seeded):
    async def go():
        async with Client(srv.mcp) as c:
            static = {str(r.uri) for r in await c.list_resources()}
            templates = {t.uriTemplate for t in await c.list_resource_templates()}
            prompts = {p.name for p in await c.list_prompts()}
        return static, templates, prompts

    static, templates, prompts = _run(go())
    assert "archmap://maps{?q}" in templates or "archmap://maps" in static
    assert {
        "archmap://{map}/model{?domain,plane,lifecycle,sort,dir,q,limit,offset}",
        "archmap://{map}/digest{?domain}",
        "archmap://{map}/board",
        "archmap://{map}/module/{id}",
        "archmap://{map}/metrics{?sort,dir,limit,offset}",
        "archmap://{map}/metrics/{module}",
        "archmap://{map}/docs{?type,tag,status,domain,q}",
        "archmap://{map}/doc/{id}",
        "archmap://{map}/plans{?status}",
        "archmap://{map}/plan/{id}",
        "archmap://{map}/worktrees{?status}",
    } <= templates
    assert "grill_candidate" in prompts


def test_fastmcp_supports_query_param_resource_templates(seeded):
    """CONFIRM: FastMCP parses RFC-6570 query expansion into the resource fn's kwargs.
    Reading with ?domain=ui must yield ONLY the ui modules; reading WITHOUT it yields
    all — proving the query param actually drove the function (not ignored)."""
    async def go():
        async with Client(srv.mcp) as c:
            with_q = _yaml_of(await _read(c, "archmap://m/model?domain=ui"))
            no_q = _yaml_of(await _read(c, "archmap://m/model"))
        return with_q, no_q

    with_q, no_q = _run(go())
    assert {m["id"] for m in with_q["modules"]} == {"a", "c"}
    assert {m["id"] for m in no_q["modules"]} == {"a", "b", "c"}


# ---- every resource returns YAML (doc returns Markdown) ----------------------

def test_every_structured_resource_is_yaml(seeded):
    uris = ["archmap://maps", "archmap://m/model", "archmap://m/digest",
            "archmap://m/board", "archmap://m/module/a", "archmap://m/metrics",
            "archmap://m/metrics/a", "archmap://m/docs", "archmap://m/plans",
            "archmap://m/plan/p1", "archmap://m/worktrees"]

    async def go():
        async with Client(srv.mcp) as c:
            out = {}
            for u in uris:
                text, mime = await _read(c, u)
                out[u] = (mime, yaml.safe_load(text))   # must parse as YAML
        return out

    out = _run(go())
    for u, (mime, payload) in out.items():
        assert mime == "application/yaml", u
        assert isinstance(payload, dict), u


def test_doc_resource_returns_markdown(seeded):
    async def go():
        async with Client(srv.mcp) as c:
            note = await _read(c, "archmap://m/doc/d1")
            diagram = await _read(c, "archmap://m/doc/dg")
        return note, diagram

    (note_text, note_mime), (diag_text, diag_mime) = _run(go())
    assert note_mime == "text/markdown"
    assert note_text.startswith("---\n")                  # YAML frontmatter block
    front = note_text.split("---\n")[1]                   # between the two fences
    meta = yaml.safe_load(front)
    assert meta["id"] == "d1" and meta["type"] == "note" and meta["title"] == "A note"
    assert "the body text" in note_text                   # body verbatim, after frontmatter
    # a diagram doc's body is wrapped in a fenced mermaid block
    assert diag_mime == "text/markdown"
    assert "```mermaid" in diag_text and "graph TD; A-->B" in diag_text


# ---- model resource: filter / q / sort+dir / paging --------------------------

def test_model_resource_filters_q_sort_and_pages(seeded):
    async def go():
        async with Client(srv.mcp) as c:
            by_plane = _yaml_of(await _read(c, "archmap://m/model?plane=intended"))
            by_life = _yaml_of(await _read(c, "archmap://m/model?lifecycle=built"))
            q = _yaml_of(await _read(c, "archmap://m/model?q=render"))      # iface match
            q_label = _yaml_of(await _read(c, "archmap://m/model?q=beta"))  # label match
            srt = _yaml_of(await _read(c, "archmap://m/model?sort=depth&dir=desc"))
            page0 = _yaml_of(await _read(c, "archmap://m/model?sort=depth&dir=desc&limit=1&offset=0"))
            page1 = _yaml_of(await _read(c, "archmap://m/model?sort=depth&dir=desc&limit=1&offset=1"))
        return by_plane, by_life, q, q_label, srt, page0, page1

    by_plane, by_life, q, q_label, srt, page0, page1 = _run(go())
    assert {m["id"] for m in by_plane["modules"]} == {"c"}             # exact match
    assert {m["id"] for m in by_life["modules"]} == {"a", "b"}
    assert {m["id"] for m in q["modules"]} == {"a"}                    # q -> iface substring
    assert {m["id"] for m in q_label["modules"]} == {"b"}             # q -> label substring (case-insens)
    assert [m["id"] for m in srt["modules"]] == ["b", "c", "a"]       # depth desc: 0.8,0.5,0.2
    # paging metadata rides in the payload
    assert [m["id"] for m in page0["modules"]] == ["b"]
    assert page0["total_count"] == 3 and page0["has_more"] is True and page0["next_offset"] == 1
    assert [m["id"] for m in page1["modules"]] == ["c"]
    assert page1["has_more"] is True and page1["next_offset"] == 2


# ---- maps resource: q search -------------------------------------------------

def test_maps_resource_lists_and_q_filters(seeded):
    srv.create_project(name="Other", map_id="other", repo="Other Repo")

    async def go():
        async with Client(srv.mcp) as c:
            allm = _yaml_of(await _read(c, "archmap://maps"))
            only = _yaml_of(await _read(c, "archmap://maps?q=other"))
        return allm, only

    allm, only = _run(go())
    assert {"m", "other"} <= {x["id"] for x in allm["maps"]}
    assert allm["total_count"] >= 2
    assert {x["id"] for x in only["maps"]} == {"other"}               # q on id/repo


# ---- digest resource: filter -------------------------------------------------

def test_digest_resource_and_domain_filter(seeded):
    async def go():
        async with Client(srv.mcp) as c:
            digest = _yaml_of(await _read(c, "archmap://m/digest"))
            ui = _yaml_of(await _read(c, "archmap://m/digest?domain=ui"))
        return digest, ui

    digest, ui = _run(go())
    assert digest == srv.show_map(map="m")                            # same projection
    assert {mod["id"] for mod in ui["modules"]} == {"a", "c"}         # domain records


# ---- module + board resources ------------------------------------------------

def test_module_and_board_resources(seeded):
    async def go():
        async with Client(srv.mcp) as c:
            module = _yaml_of(await _read(c, "archmap://m/module/a"))
            board = _yaml_of(await _read(c, "archmap://m/board"))
        return module, board

    module, board = _run(go())
    assert module == srv.get_module(map="m", id="a")
    assert board == srv.board(map="m")
    assert "todo" in board["columns"] and board["counts"]["todo"] == 1


# ---- metrics resources: one + all (sort/page) --------------------------------

def test_metrics_resources_one_and_all_with_sort_and_page(seeded):
    async def go():
        async with Client(srv.mcp) as c:
            one = _yaml_of(await _read(c, "archmap://m/metrics/a"))
            allm = _yaml_of(await _read(c, "archmap://m/metrics?sort=id&dir=asc"))
            page = _yaml_of(await _read(c, "archmap://m/metrics?sort=id&dir=asc&limit=2&offset=0"))
        return one, allm, page

    one, allm, page = _run(go())
    assert one["module"] == "a" and "health" in one["metrics"]
    ids = [row["id"] for row in allm["metrics"]]
    assert ids == ["a", "b", "c"]                                     # sort=id asc
    assert allm["total_count"] == 3
    assert [row["id"] for row in page["metrics"]] == ["a", "b"]
    assert page["has_more"] is True and page["next_offset"] == 2


# ---- docs resource: type / status / tag / domain / q filters -----------------

def test_docs_resource_filters(seeded):
    async def go():
        async with Client(srv.mcp) as c:
            all_docs = _yaml_of(await _read(c, "archmap://m/docs"))
            by_type = _yaml_of(await _read(c, "archmap://m/docs?type=note"))
            by_status = _yaml_of(await _read(c, "archmap://m/docs?status=accepted"))
            by_tag = _yaml_of(await _read(c, "archmap://m/docs?tag=keep"))
            by_domain = _yaml_of(await _read(c, "archmap://m/docs?domain=ui"))
            by_q = _yaml_of(await _read(c, "archmap://m/docs?q=needle"))
        return all_docs, by_type, by_status, by_tag, by_domain, by_q

    all_docs, by_type, by_status, by_tag, by_domain, by_q = _run(go())
    assert {d["id"] for d in all_docs["docs"]} == {"d1", "dg"}
    assert {d["id"] for d in by_type["docs"]} == {"d1"}               # type exact
    assert {d["id"] for d in by_status["docs"]} == {"d1"}             # status exact
    assert {d["id"] for d in by_tag["docs"]} == {"d1"}               # tag membership
    assert {d["id"] for d in by_domain["docs"]} == {"d1"}            # scope contains a ui module
    assert {d["id"] for d in by_q["docs"]} == {"d1"}                 # q over title/summary


# ---- plans + worktrees resources: status filter ------------------------------

def test_plans_resource_and_status_filter(seeded):
    async def go():
        async with Client(srv.mcp) as c:
            allp = _yaml_of(await _read(c, "archmap://m/plans"))
            active = _yaml_of(await _read(c, "archmap://m/plans?status=active"))
            none = _yaml_of(await _read(c, "archmap://m/plans?status=draft"))
            one = _yaml_of(await _read(c, "archmap://m/plan/p1"))
        return allp, active, none, one

    allp, active, none, one = _run(go())
    assert {p["id"] for p in allp["plans"]} == {"p1"}
    assert {p["id"] for p in active["plans"]} == {"p1"}
    assert none["plans"] == []                                        # status exact
    assert one["id"] == "p1" and one["steps"][0]["id"] == "s1"       # full plan record


def test_worktrees_resource_and_status_filter(reg):
    srv.plans(action="create", map="m", plan_id="p1", title="P")
    srv.plans(action="add_steps", map="m", plan_id="p1", steps=[{"id": "s1", "title": "S"}])
    srv.worktrees(action="attach", map="m", branch="feat/x", plan_id="p1", step_id="s1")

    async def go():
        async with Client(srv.mcp) as c:
            allw = _yaml_of(await _read(c, "archmap://m/worktrees"))
            active = _yaml_of(await _read(c, "archmap://m/worktrees?status=active"))
            removed = _yaml_of(await _read(c, "archmap://m/worktrees?status=removed"))
        return allw, active, removed

    allw, active, removed = _run(go())
    assert {w["branch"] for w in allw["worktrees"]} == {"feat/x"}
    assert {w["branch"] for w in active["worktrees"]} == {"feat/x"}   # attached -> active
    assert removed["worktrees"] == []                                 # status exact


# ---- the prompt --------------------------------------------------------------

def test_grill_candidate_prompt_advertises_params_and_matches_tool(seeded):
    tool_text = srv.grilling(action="start", map=seeded["map"],
                             module=seeded["module"])["prompt"]

    async def go():
        async with Client(srv.mcp) as c:
            prompt = next(p for p in await c.list_prompts() if p.name == "grill_candidate")
            rendered = await c.get_prompt(
                "grill_candidate",
                {"map": seeded["map"], "suggestion_id": seeded["suggestion_id"]})
        return prompt, rendered

    prompt, rendered = _run(go())
    assert {"map", "suggestion_id"} <= {a.name for a in (prompt.arguments or [])}
    assert rendered.messages[0].content.text == tool_text


# ---- no phantom maps: a missing map/id raises and creates nothing -------------

def test_missing_map_raises_and_creates_no_phantom(reg):
    """The show_map / get_full_model / board no-auto-create rule, now enforced at the
    RESOURCE boundary: a read of an unknown map surfaces a recoverable error and the
    registry stays empty (no phantom map on disk)."""
    async def go():
        async with Client(srv.mcp) as c:
            for uri in ("archmap://ghost/digest", "archmap://ghost/model",
                        "archmap://ghost/board", "archmap://ghost/module/x",
                        "archmap://ghost/plan/p", "archmap://ghost/doc/d"):
                with pytest.raises(McpError):            # ResourceError -> client error
                    await c.read_resource(uri)
    _run(go())
    assert not reg.exists("ghost")                       # the reads created NO phantom map
    assert reg.list() == []


def test_get_full_model_paging_via_model_resource(reg):
    """get_full_model module-paging (moved off the old read tool) — now driven through
    the model resource's limit/offset query params."""
    srv.modules(action="add", map="m", items=[
        {"id": mid, "label": mid.upper(), "domain": "d"} for mid in ("a", "b", "c")
    ])

    async def go():
        async with Client(srv.mcp) as c:
            first = _yaml_of(await _read(c, "archmap://m/model?sort=id&limit=2&offset=0"))
            last = _yaml_of(await _read(c, "archmap://m/model?sort=id&limit=2&offset=2"))
        return first, last

    first, last = _run(go())
    assert [m["id"] for m in first["modules"]] == ["a", "b"]
    assert first["total_count"] == 3 and first["has_more"] is True and first["next_offset"] == 2
    assert [m["id"] for m in last["modules"]] == ["c"]
    assert last["has_more"] is False and last["next_offset"] is None


def test_grill_candidate_missing_suggestion_raises(reg):
    srv.modules(action="add", map="m", id="a", label="A", domain="d")

    async def go():
        async with Client(srv.mcp) as c:
            await c.get_prompt("grill_candidate", {"map": "m", "suggestion_id": "nope"})

    with pytest.raises(McpError):
        _run(go())
