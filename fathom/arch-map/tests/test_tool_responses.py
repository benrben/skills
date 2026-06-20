"""Interface tests for the s4 'better tool responses for agents' pass (server.py):

  * archmap_get_full_model paging + include= section filter (no args == today's model)
  * reads no longer auto-create a phantom map (show_map / get_full_model / board)
  * mutation acks carry the created entity / derived id (modules add, suggestions flag)
  * verify_edges / drift paging metadata

These lock the NEW optional surface; the HARD INVARIANT (no renamed/changed existing
params) is covered by test_tool_surface + test_http_backend.
"""
import pytest

import arch_map.server as srv


# ---- get_full_model: no args == today's whole model -------------------------

def test_get_full_model_unbounded_returns_every_section(reg):
    srv.modules(action="add", map="m", items=[
        {"id": "a", "label": "A", "domain": "d"},
        {"id": "b", "label": "B", "domain": "d"},
    ])
    full = srv.get_full_model(map="m")
    assert full["map"] == "m"
    # the whole-model keys are all present and nothing is paged/dropped
    assert {"modules", "plans", "docs", "board", "docMembership",
            "worktrees", "orphans", "openSuggestions"} <= set(full)
    assert len(full["modules"]) == 2
    assert "truncated" not in full and "next_offset" not in full


# ---- get_full_model: module paging ------------------------------------------

def test_get_full_model_pages_modules(reg):
    srv.modules(action="add", map="m", items=[
        {"id": mid, "label": mid.upper(), "domain": "d"} for mid in ("a", "b", "c")
    ])
    first = srv.get_full_model(map="m", module_limit=2, module_offset=0)
    assert len(first["modules"]) == 2
    assert first["total_modules"] == 3
    assert first["truncated"] is True
    assert first["next_offset"] == 2
    last = srv.get_full_model(map="m", module_limit=2, module_offset=2)
    assert len(last["modules"]) == 1
    assert last["truncated"] is False
    assert last["next_offset"] is None


# ---- get_full_model: include= section filter --------------------------------

def test_get_full_model_include_drops_unrequested_sections(reg):
    srv.modules(action="add", map="m", id="a", label="A", domain="d")
    out = srv.get_full_model(map="m", include=["modules"])
    assert "modules" in out
    # board + docMembership + worktrees are dropped when not requested
    assert "board" not in out and "docMembership" not in out and "worktrees" not in out
    # plans/docs dropped too
    assert "plans" not in out and "docs" not in out
    # docs keeps docMembership; board keeps worktrees
    with_docs = srv.get_full_model(map="m", include=["docs"])
    assert "docs" in with_docs and "docMembership" in with_docs
    with_board = srv.get_full_model(map="m", include=["board"])
    assert "board" in with_board and "worktrees" in with_board


# ---- reads never auto-create a phantom map ----------------------------------

def test_show_map_on_unknown_id_raises_and_does_not_create(reg):
    with pytest.raises(KeyError) as e:
        srv.show_map(map="ghost")
    assert "archmap_show_map(map='ghost')" in str(e.value)
    # the phantom map was NOT created on disk
    assert not reg.exists("ghost")
    assert reg.list() == []


def test_get_full_model_and_board_on_unknown_id_do_not_create(reg):
    with pytest.raises(KeyError):
        srv.get_full_model(map="ghost")
    with pytest.raises(KeyError):
        srv.board(map="ghost")
    assert not reg.exists("ghost")
    assert reg.list() == []


# ---- mutation acks carry the created entity / derived id --------------------

def test_modules_add_ack_returns_created_record(reg):
    ack = srv.modules(action="add", map="m", id="a", label="A", domain="d", depth=0.7)
    assert ack["ok"] is True
    assert ack["created"]["id"] == "a"
    assert ack["created"]["depth"] == 0.7


def test_modules_bulk_add_ack_returns_created_ids(reg):
    ack = srv.modules(action="add", map="m", items=[
        {"id": "a", "label": "A", "domain": "d"},
        {"id": "b", "label": "B", "domain": "d"},
    ])
    assert ack["createdIds"] == ["a", "b"]


def test_suggestions_flag_ack_returns_derived_suggestion_id(reg):
    srv.modules(action="add", map="m", id="a", label="A", domain="d")
    ack = srv.suggestions(action="flag", map="m", module="a", title="Deepen A",
                          strength="Strong", category="in-process",
                          problem="p", solution="s", wins=["w"])
    assert ack["suggestion_id"] == "a-strong"            # f"{module}-{strength}" slugged
    # and it round-trips: the derived id can decide/dismiss the candidate
    srv.suggestions(action="decide", map="m", suggestion_id=ack["suggestion_id"],
                    decision="accepted", note="ok")
    assert srv.get_module(map="m", id="a")["suggestions"][0]["decision"] == "accepted"


# ---- verify_edges / drift paging metadata -----------------------------------

def _git(root, *args):
    import subprocess
    subprocess.run(["git", "-C", str(root),
                    "-c", "user.name=t", "-c", "user.email=t@t",
                    "-c", "commit.gpgsign=false", *args],
                   check=True, capture_output=True, text=True)


def test_verify_edges_pages_edge_lists(reg, tmp_path):
    root = tmp_path / "repo"
    (root / "src").mkdir(parents=True)
    _git(root, "init", "-q", "-b", "main")
    # three importers all reaching one target -> three undeclared edges
    for name in ("a", "b", "c"):
        (root / "src" / f"{name}.py").write_text("import src.t\n")
    (root / "src" / "t.py").write_text("x = 1\n")
    _git(root, "add", ".")
    _git(root, "commit", "-q", "-m", "c1")
    srv.create_project(name="V", map_id="v")
    srv.modules(action="add", map="v", items=[
        {"id": "a", "label": "A", "domain": "d", "files": ["src/a.py"]},
        {"id": "b", "label": "B", "domain": "d", "files": ["src/b.py"]},
        {"id": "c", "label": "C", "domain": "d", "files": ["src/c.py"]},
        {"id": "t", "label": "T", "domain": "d", "files": ["src/t.py"]},
    ])
    full = srv.verify_edges(map="v", root=str(root))
    assert len(full["undeclaredEdges"]) == 3
    assert "total_count" not in full                      # no paging when limit=0
    page = srv.verify_edges(map="v", root=str(root), limit=2, offset=0)
    assert len(page["undeclaredEdges"]) == 2
    assert page["total_count"] == 3
    assert page["has_more"] is True
    assert page["next_offset"] == 2
