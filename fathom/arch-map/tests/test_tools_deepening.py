"""Interface tests for the **MCP Tools — Candidates + Grilling** slice (server.py).

The candidates + grilling write-slice fathom:deepen owns. More than a
pass-through: suggestion ids are auto-derived from module+strength, start_grilling
emits the grill prompt and persists 'requested', and grilling_done couples
mark_grilled + decide.
"""
import pytest

import arch_map.server as srv


@pytest.fixture
def deepmap(reg):
    srv.create_project(name="M", map_id="m", repo="M")
    srv.modules(action="add", map="m", id="a", label="A", domain="d")
    srv.suggestions(action="flag", map="m", module="a", title="Deepen A", strength="Strong",
                       category="in-process", problem="p", solution="s", wins=["w"])
    return "m", "a-strong"          # sid = f"{module}-{strength}".lower().replace(" ","-")


def _only_suggestion(map, module):
    # reads are resource-only; srv.get_module is the read helper behind
    # archmap://{map}/module/{id}.
    return srv.get_module(map=map, id=module)["suggestions"][0]


def test_flag_deepening_derives_id_and_attaches(deepmap):
    mp, sid = deepmap
    s = _only_suggestion(mp, "a")
    assert s["id"] == sid
    assert s["strength"] == "Strong"
    assert s["status"] == "open"
    assert s["decision"] == ""


def test_flag_deepening_id_slugs_multiword_strength(reg):
    srv.modules(action="add", map="m", id="a", label="A", domain="d")
    srv.suggestions(action="flag", map="m", module="a", title="T", strength="Worth exploring",
                       category="ports & adapters", problem="p", solution="s", wins=[])
    assert _only_suggestion("m", "a")["id"] == "a-worth-exploring"


def test_decide_records_verdict(deepmap):
    mp, sid = deepmap
    srv.suggestions(action="decide", map=mp, suggestion_id=sid, decision="deferred", note="later")
    s = _only_suggestion(mp, "a")
    assert s["decision"] == "deferred"
    assert s["note"] == "later"


def test_start_grilling_requests_and_returns_prompt(deepmap):
    mp, sid = deepmap
    out = srv.grilling(action="start", map=mp, module="a")
    assert out["map"] == mp and out["module"] == "a"
    assert out["suggestion_id"] == sid
    assert "grilling" in out["prompt"].lower()
    queued = srv.grilling(action="queue", map=mp)["queued"]
    assert [q["suggestion_id"] for q in queued] == [sid]


def test_mark_grilling_sets_status(deepmap):
    mp, sid = deepmap
    srv.grilling(action="mark", map=mp, suggestion_id=sid)
    assert _only_suggestion(mp, "a")["status"] == "grilling"


def test_grilling_done_couples_grilled_and_decision(deepmap):
    mp, sid = deepmap
    srv.grilling(action="finish", map=mp, suggestion_id=sid, decision="accepted", note="ship it")
    s = _only_suggestion(mp, "a")
    assert s["status"] == "grilled"
    assert s["decision"] == "accepted"
    assert s["note"] == "ship it"


# ---- grilling argument contract ------------------------------------------------

def test_grilling_start_requires_module(deepmap):
    mp, _ = deepmap
    with pytest.raises(ValueError, match="needs module"):
        srv.grilling(action="start", map=mp)

def test_grilling_mark_requires_suggestion_id(deepmap):
    mp, _ = deepmap
    with pytest.raises(ValueError, match="needs suggestion_id"):
        srv.grilling(action="mark", map=mp)

def test_grilling_start_without_open_candidate_still_returns_prompt(reg):
    srv.create_project(name="M", map_id="m", repo="M")
    srv.modules(action="add", map="m", id="b", label="B", domain="d")
    out = srv.grilling(action="start", map="m", module="b")
    assert out["suggestion_id"] is None            # nothing to flag as requested
    assert "B" in out["prompt"]                    # prompt still names the module
