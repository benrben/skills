"""Interface tests for the archmap:// READ RESOURCES + the grill_candidate PROMPT
(spec-spine-resources / spec-spine-prompts).

Exercised over a real in-memory FastMCP ``Client(srv.mcp)`` — the full protocol,
no subprocess — against the same temp REGISTRY the `reg` fixture points the server
module at. The Client API is async; each test drives it through ``asyncio.run`` so
no async-test plugin is needed. Asserts:
  * the client lists every new resource/template and the grill_candidate prompt;
  * reading archmap://{map}/digest equals archmap_show_map for a seeded map;
  * reading a MISSING map raises and does NOT create a phantom map (no side effect).
"""
import asyncio
import json

import pytest
from fastmcp import Client
from mcp.shared.exceptions import McpError

import arch_map.server as srv


def _json(result):
    """The JSON payload from a read_resource result (FastMCP returns content blocks)."""
    block = result[0] if isinstance(result, list) else result.contents[0]
    return json.loads(block.text)


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture
def seeded(reg):
    """A temp map 'm' with one module + one flagged candidate, via the real tools."""
    srv.modules(action="add", map="m", id="a", label="A", domain="d")
    flag = srv.suggestions(action="flag", map="m", module="a",
                           title="deepen A", strength="Strong")
    return {"map": "m", "module": "a", "suggestion_id": flag["suggestion_id"]}


def test_lists_new_resources_and_prompt(seeded):
    async def go():
        async with Client(srv.mcp) as c:
            static = {str(r.uri) for r in await c.list_resources()}
            templates = {t.uriTemplate for t in await c.list_resource_templates()}
            prompts = {p.name for p in await c.list_prompts()}
        return static, templates, prompts

    static, templates, prompts = _run(go())
    assert "archmap://maps" in static
    assert {
        "archmap://{map}/model",
        "archmap://{map}/digest",
        "archmap://{map}/board",
        "archmap://{map}/module/{id}",
        "archmap://{map}/doc/{id}",
        "archmap://{map}/metrics/{module}",
    } <= templates
    assert "grill_candidate" in prompts


def test_grill_candidate_prompt_advertises_params(seeded):
    async def go():
        async with Client(srv.mcp) as c:
            return next(p for p in await c.list_prompts() if p.name == "grill_candidate")

    prompt = _run(go())
    args = {a.name for a in (prompt.arguments or [])}
    assert {"map", "suggestion_id"} <= args


def test_digest_resource_equals_show_map_tool(seeded):
    async def go():
        async with Client(srv.mcp) as c:
            return _json(await c.read_resource(f"archmap://{seeded['map']}/digest"))

    assert _run(go()) == srv.show_map(map=seeded["map"])


def test_model_and_module_resources_equal_tools(seeded):
    async def go():
        async with Client(srv.mcp) as c:
            model = _json(await c.read_resource(f"archmap://{seeded['map']}/model"))
            module = _json(
                await c.read_resource(f"archmap://{seeded['map']}/module/{seeded['module']}"))
            return model, module

    model, module = _run(go())
    assert model == srv.get_full_model(map=seeded["map"])
    assert module == srv.modules(action="get", map=seeded["map"], id=seeded["module"])


def test_maps_resource_lists_seeded_map(seeded):
    async def go():
        async with Client(srv.mcp) as c:
            return _json(await c.read_resource("archmap://maps"))

    payload = _run(go())
    assert seeded["map"] in {m["id"] for m in payload["maps"]}
    assert payload["total_count"] >= 1


def test_grill_candidate_prompt_matches_grilling_start(seeded):
    """The prompt renders the SAME walkthrough text the tool builds (one source)."""
    tool_text = srv.grilling(action="start", map=seeded["map"],
                             module=seeded["module"])["prompt"]

    async def go():
        async with Client(srv.mcp) as c:
            return await c.get_prompt(
                "grill_candidate",
                {"map": seeded["map"], "suggestion_id": seeded["suggestion_id"]})

    rendered = _run(go())
    assert rendered.messages[0].content.text == tool_text


def test_missing_map_raises_and_creates_nothing(reg):
    async def go():
        async with Client(srv.mcp) as c:
            await c.read_resource("archmap://ghost/digest")

    with pytest.raises(McpError):            # ResourceError surfaces as a client error
        _run(go())
    assert not reg.exists("ghost")           # the read created NO phantom map


def test_grill_candidate_missing_suggestion_raises(reg):
    srv.modules(action="add", map="m", id="a", label="A", domain="d")

    async def go():
        async with Client(srv.mcp) as c:
            await c.get_prompt("grill_candidate", {"map": "m", "suggestion_id": "nope"})

    with pytest.raises(McpError):
        _run(go())
