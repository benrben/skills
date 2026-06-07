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
    srv.create_map(map="m", repo="M")
    srv.add_module(map="m", id="a", label="A", domain="d")
    srv.flag_deepening(map="m", module="a", title="Deepen A", strength="Strong",
                       category="in-process", problem="p", solution="s", wins=["w"])
    return "m", "a-strong"          # sid = f"{module}-{strength}".lower().replace(" ","-")


def _only_suggestion(map, module):
    return srv.get_module(map=map, module=module)["suggestions"][0]


def test_flag_deepening_derives_id_and_attaches(deepmap):
    mp, sid = deepmap
    s = _only_suggestion(mp, "a")
    assert s["id"] == sid
    assert s["strength"] == "Strong"
    assert s["status"] == "open"
    assert s["decision"] == ""


def test_flag_deepening_id_slugs_multiword_strength(reg):
    srv.add_module(map="m", id="a", label="A", domain="d")
    srv.flag_deepening(map="m", module="a", title="T", strength="Worth exploring",
                       category="ports & adapters", problem="p", solution="s", wins=[])
    assert _only_suggestion("m", "a")["id"] == "a-worth-exploring"


def test_decide_records_verdict(deepmap):
    mp, sid = deepmap
    srv.decide(map=mp, suggestion_id=sid, decision="deferred", note="later")
    s = _only_suggestion(mp, "a")
    assert s["decision"] == "deferred"
    assert s["note"] == "later"


def test_start_grilling_requests_and_returns_prompt(deepmap):
    mp, sid = deepmap
    prompt = srv.start_grilling(map=mp, module="a")
    assert isinstance(prompt, str) and "grilling" in prompt.lower()
    queued = srv.grilling_queue(map=mp)["queued"]
    assert [q["suggestion_id"] for q in queued] == [sid]


def test_mark_grilling_sets_status(deepmap):
    mp, sid = deepmap
    srv.mark_grilling(map=mp, suggestion_id=sid)
    assert _only_suggestion(mp, "a")["status"] == "grilling"


def test_grilling_done_couples_grilled_and_decision(deepmap):
    mp, sid = deepmap
    srv.grilling_done(map=mp, suggestion_id=sid, decision="accepted", note="ship it")
    s = _only_suggestion(mp, "a")
    assert s["status"] == "grilled"
    assert s["decision"] == "accepted"
    assert s["note"] == "ship it"
