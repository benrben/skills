"""Named, file-backed maps — the MapRegistry seam.

Extracted from server.py per adr-split-spine-hub. A directory of maps/<id>.json
files: resolve a slug-validated map id to a Store, list/create/delete/rename maps,
and fold a pre-multi-map arch_state.json in once. The safety promise: map ids are
slugs ([a-z0-9._-], no '/', no leading dot) and every resolved path is re-checked
to stay under the maps root, so a request can never read or write outside it.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .model import ArchModel
from .store import Store

HERE = Path(__file__).parent
# Pre-multi-map single state file, folded into maps/<repo>.json once on first run.
# Module-level so a test can monkeypatch it to disable the one-shot migration.
LEGACY_STATE = HERE.parent / "arch_state.json"

_MAP_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")


def _slug(s: str) -> str:
    """Turn a free-text map name into a clean id: lowercase, alphanumeric runs
    joined by single dashes ('Mr. Meeseeks' -> 'mr-meeseeks')."""
    s = re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")
    return s or "default"


class MapRegistry:
    """A directory of named, file-backed maps (maps/<id>.json). Resolves a map id
    to a Store, lists summaries for the switcher, and creates/deletes maps. Map
    ids are slugs ([a-z0-9._-], no '/' and no leading dot) so a request can never
    read or write outside the maps directory."""

    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self._migrate_legacy()

    def _migrate_legacy(self) -> None:
        # Fold a pre-existing single arch_state.json into maps/<repo>.json once, so
        # existing data shows up as a named map. Non-destructive (copy; keep original).
        if LEGACY_STATE.exists() and not any(self.root.glob("*.json")):
            try:
                mid = _slug(json.loads(LEGACY_STATE.read_text()).get("repo") or "default")
            except Exception:
                mid = "default"
            (self.root / f"{mid}.json").write_text(LEGACY_STATE.read_text(encoding="utf-8"), encoding="utf-8")

    def path(self, map_id: str) -> Path:
        if not _MAP_ID_RE.match(map_id or ""):
            raise ValueError(f"invalid map id '{map_id}' (use lowercase a-z, 0-9, . _ -)")
        p = (self.root / f"{map_id}.json").resolve()
        if self.root not in p.parents:           # belt-and-suspenders vs traversal
            raise ValueError(f"invalid map id '{map_id}'")
        return p

    def exists(self, map_id: str) -> bool:
        try:
            return self.path(map_id).exists()
        except ValueError:
            return False

    def store(self, map_id: str) -> Store:
        p = self.path(map_id)
        if not p.exists():
            raise KeyError(f"no map '{map_id}' (create it with create_project, "
                           f"or call list_maps to see existing map ids)")
        return Store(p)

    def create(self, map_id: str, repo: str = "") -> Store:
        p = self.path(map_id)
        if p.exists():
            raise KeyError(f"map '{map_id}' already exists")
        ArchModel(repo or map_id, []).save(p)
        return Store(p)

    def ensure(self, map_id: str, repo: str = "") -> Store:
        """Get the map, creating an empty one if it doesn't exist yet."""
        try:
            return self.store(map_id)
        except KeyError:
            return self.create(map_id, repo)

    def delete(self, map_id: str) -> None:
        p = self.path(map_id)
        if not p.exists():
            raise KeyError(f"no map '{map_id}'")
        p.unlink()
        lock = p.with_name(p.name + ".lock")
        if lock.exists():
            lock.unlink()

    def rename(self, old_id: str, new_id: str, repo: str | None = None) -> Store:
        """Rename a map (move maps/<old>.json -> <new>.json) and/or relabel its
        repo. Pass new_id == old_id to only change the repo label."""
        src = self.path(old_id)
        if not src.exists():
            raise KeyError(f"no map '{old_id}'")
        dst = self.path(new_id)
        if dst.exists() and dst != src:
            raise KeyError(f"map '{new_id}' already exists")
        data = json.loads(src.read_text())
        if repo is not None:
            data["repo"] = repo
        dst.write_text(json.dumps(data, indent=2), encoding="utf-8")
        if dst != src:
            src.unlink()
            lock = src.with_name(src.name + ".lock")
            if lock.exists():
                lock.unlink()
        return Store(dst)

    def list(self) -> list[dict]:
        out = []
        for f in sorted(self.root.glob("*.json")):
            try:
                v = ArchModel.from_json(f).to_view()
                out.append({"id": f.stem, "repo": v["repo"], "modules": len(v["modules"]),
                            "openSuggestions": len(v["openSuggestions"]), "orphans": len(v["orphans"])})
            except Exception:
                out.append({"id": f.stem, "repo": "", "modules": 0,
                            "openSuggestions": 0, "orphans": 0, "broken": True})
        return out

    def default_id(self) -> str:
        files = sorted(self.root.glob("*.json"))
        return files[0].stem if files else "default"

    def resolve(self, map_id: str | None) -> Store:
        """HTTP convenience: an explicit id must exist; no id falls back to the
        default map (bootstrapping an empty one on a fresh install)."""
        if map_id:
            return self.store(map_id)            # raises KeyError -> 404/400
        mid = self.default_id()
        return self.store(mid) if self.exists(mid) else self.create(mid)
