"""Interface tests for the **Map Registry** module (server.py).

A directory of named, file-backed maps. The interface a caller must know: map
ids are validated against a slug regex and resolved under root (so a request can
never escape the maps directory); create/ensure/store/delete/rename/list/resolve
manage the lifecycle. Local-substitutable (filesystem) — tested against tmp_path,
with legacy migration disabled so the real repo's state never leaks in.
"""
import json

import pytest

import arch_map.server as srv
import arch_map.map_registry as mr
from arch_map.server import MapRegistry, Store, _slug


@pytest.fixture
def reg(tmp_path, monkeypatch):
    # Disable the one-shot legacy-state migration so an empty tmp registry stays
    # empty regardless of the real repo's files.
    monkeypatch.setattr(mr, "LEGACY_STATE", tmp_path / "no-legacy.json")
    return MapRegistry(tmp_path / "maps")


# ---- slug -------------------------------------------------------------------

def test_slug_joins_alnum_runs_with_dashes():
    assert _slug("Mr. Meeseeks") == "mr-meeseeks"

def test_slug_empty_falls_back_to_default():
    assert _slug("") == "default"
    assert _slug("!!!") == "default"


# ---- path validation + traversal safety ------------------------------------

def test_path_accepts_valid_id(reg):
    p = reg.path("my-map_1.2")
    assert p.name == "my-map_1.2.json"
    assert reg.root in p.parents

@pytest.mark.parametrize("bad", ["UPPER", "has/slash", "../escape", ".hidden", ""])
def test_path_rejects_invalid_or_traversal_ids(reg, bad):
    with pytest.raises(ValueError):
        reg.path(bad)


# ---- create / exists / store -----------------------------------------------

def test_create_makes_a_map_with_repo_label(reg):
    store = reg.create("alpha", repo="Alpha")
    assert isinstance(store, Store)
    assert reg.exists("alpha")
    assert store.to_dict()["repo"] == "Alpha"

def test_create_duplicate_raises(reg):
    reg.create("alpha")
    with pytest.raises(KeyError):
        reg.create("alpha")

def test_exists_false_for_absent_and_invalid(reg):
    assert reg.exists("ghost") is False
    assert reg.exists("Bad/Id") is False      # invalid id -> swallowed -> False

def test_store_missing_raises(reg):
    with pytest.raises(KeyError):
        reg.store("ghost")

def test_ensure_creates_then_returns_existing(reg):
    s1 = reg.ensure("beta", repo="Beta")
    assert reg.exists("beta")
    s2 = reg.ensure("beta")                   # second call must not recreate
    assert s2.to_dict()["repo"] == "Beta"     # original label preserved


# ---- delete -----------------------------------------------------------------

def test_delete_removes_map_and_lock(reg, tmp_path):
    reg.create("gamma")
    lock = reg.path("gamma").with_name("gamma.json.lock")
    lock.write_text("")                        # simulate a leftover lock
    reg.delete("gamma")
    assert not reg.exists("gamma")
    assert not lock.exists()

def test_delete_missing_raises(reg):
    with pytest.raises(KeyError):
        reg.delete("ghost")


# ---- rename -----------------------------------------------------------------

def test_rename_moves_file(reg):
    reg.create("old", repo="Old")
    reg.rename("old", "new")
    assert not reg.exists("old")
    assert reg.exists("new")

def test_rename_same_id_relabels_repo(reg):
    reg.create("keep", repo="Old")
    reg.rename("keep", "keep", repo="NewLabel")
    assert reg.store("keep").to_dict()["repo"] == "NewLabel"

def test_rename_missing_source_raises(reg):
    with pytest.raises(KeyError):
        reg.rename("ghost", "new")

def test_rename_onto_existing_target_raises(reg):
    reg.create("a")
    reg.create("b")
    with pytest.raises(KeyError):
        reg.rename("a", "b")


# ---- list / default_id ------------------------------------------------------

def test_list_summarizes_maps(reg):
    reg.create("one", repo="One")
    reg.create("two", repo="Two")
    summaries = {s["id"]: s for s in reg.list()}
    assert set(summaries) == {"one", "two"}
    assert summaries["one"]["repo"] == "One"
    assert summaries["one"]["modules"] == 0

def test_list_flags_broken_maps(reg):
    reg.create("good")
    (reg.root / "broken.json").write_text("not valid json {")
    broken = next(s for s in reg.list() if s["id"] == "broken")
    assert broken.get("broken") is True

def test_default_id_empty_then_first(reg):
    assert reg.default_id() == "default"      # nothing yet
    reg.create("zeta")
    assert reg.default_id() == "zeta"


# ---- resolve ----------------------------------------------------------------

def test_resolve_explicit_existing_id(reg):
    reg.create("alpha")
    assert isinstance(reg.resolve("alpha"), Store)

def test_resolve_explicit_missing_raises(reg):
    with pytest.raises(KeyError):
        reg.resolve("ghost")

def test_resolve_none_bootstraps_default(reg):
    store = reg.resolve(None)                  # no id, empty registry
    assert isinstance(store, Store)
    assert reg.exists("default")


# ---- _migrate_legacy ---------------------------------------------------------

def test_migrate_legacy_moves_data_to_default_map(tmp_path, monkeypatch):
    legacy = tmp_path / "arch_state.json"
    legacy.write_text(json.dumps({
        "repo": "MyRepo",
        "modules": [{"id": "a", "label": "A", "domain": "d", "depth": 0.5, "size": 1.0, "seam": ""}],
    }), encoding="utf-8")
    monkeypatch.setattr(mr, "LEGACY_STATE", legacy)
    reg = MapRegistry(tmp_path / "maps")
    assert reg.exists("myrepo"), "migrated map should exist under the slugged repo name"
    ids = {m["id"] for m in reg.store("myrepo").to_dict()["modules"]}
    assert ids == {"a"}
    assert legacy.exists()   # non-destructive copy; original preserved


# ---- migration + traversal + rename edge cases --------------------------------

def test_legacy_migration_with_corrupt_json_falls_back_to_default(tmp_path, monkeypatch):
    legacy = tmp_path / "arch_state.json"
    legacy.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(mr, "LEGACY_STATE", legacy)
    r = MapRegistry(tmp_path / "maps")
    assert (r.root / "default.json").exists()      # unparseable repo name -> 'default'

def test_path_rejects_symlink_escaping_root(reg, tmp_path):
    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    (reg.root / "evil.json").symlink_to(outside)
    with pytest.raises(ValueError, match="invalid map id"):
        reg.path("evil")                           # resolves outside root -> refused

def test_rename_removes_old_map_and_its_lock(reg):
    reg.create("old", "Old")
    lock = reg.root / "old.json.lock"
    lock.write_text("", encoding="utf-8")
    reg.rename("old", "new")
    assert not (reg.root / "old.json").exists()
    assert not lock.exists()
    assert (reg.root / "new.json").exists()
