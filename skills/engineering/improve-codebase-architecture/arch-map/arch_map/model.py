"""The living architecture model that the arch-map MCP server maintains.

Vocabulary comes straight from the /improve-codebase-architecture skill:
module · interface · depth · seam · adapter · leverage · locality.

Field meanings the network UI encodes visually:
  depth     1.0 = deep (lots of behaviour behind a small interface), 0.0 = shallow
  coverage  0..1 test coverage *at the interface* (the ring around a node)
  updated   changed since the last scan -> the pulsing "updated" halo
  suggestion an open deepening opportunity -> the strength-coloured ring + ⚠
  orphan    no inbound or outbound edges -> "not connected" (computed, see orphans())
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path


@dataclass
class Suggestion:
    id: str
    title: str
    strength: str            # "Strong" | "Worth exploring" | "Speculative"
    category: str            # dependency category at the seam (in-process, ports & adapters, ...)
    problem: str
    solution: str
    wins: list[str] = field(default_factory=list)
    decision: str = ""           # "" | "accepted" | "deferred" | "rejected"
    note: str = ""               # the reason captured when a decision is taken


@dataclass
class Module:
    id: str
    label: str
    domain: str
    depth: float
    size: float                              # relative implementation mass -> node radius
    seam: str
    iface: str = ""
    coverage: float = 0.0
    updated: bool = False
    files: list[str] = field(default_factory=list)
    dependsOn: list[str] = field(default_factory=list)
    leaksTo: list[str] = field(default_factory=list)
    tests: str = ""
    suggestion: Suggestion | None = None

    @classmethod
    def from_dict(cls, data: dict) -> "Module":
        """Build a Module from a loose dict (the CRUD tools pass JSON-ish payloads).

        Ignores computed/foreign keys (orphan, suggestion) and fills defaults for
        size/seam/depth, so a caller can pass just id/label/domain.
        """
        known = {f.name for f in fields(cls)} - {"suggestion"}
        d = {k: v for k, v in data.items() if k in known}
        for req in ("id", "label", "domain"):
            if not d.get(req):
                raise ValueError(f"module needs '{req}'")
        d.setdefault("depth", 0.5)
        d.setdefault("size", 1.0)
        d.setdefault("seam", "")
        return cls(**d)


class ArchModel:
    """In-memory architecture model. The MCP tools mutate it; the UI renders it."""

    def __init__(self, repo: str, modules: list[Module]):
        self.repo = repo
        self.modules: dict[str, Module] = {m.id: m for m in modules}

    # ---- queries ----------------------------------------------------------
    def orphans(self) -> list[str]:
        """Modules with no edge in either direction — 'not connected'."""
        connected: set[str] = set()
        for m in self.modules.values():
            edges = m.dependsOn + m.leaksTo
            if edges:
                connected.add(m.id)
                connected.update(edges)
        return [mid for mid in self.modules if mid not in connected]

    # ---- mutations the agent drives --------------------------------------
    def set_depth(self, module_id: str, score: float) -> None:
        m = self.modules[module_id]
        m.depth = max(0.0, min(1.0, score))
        m.updated = True

    def set_coverage(self, module_id: str, fraction: float) -> None:
        m = self.modules[module_id]
        m.coverage = max(0.0, min(1.0, fraction))
        m.updated = True

    def mark_updated(self, module_id: str, updated: bool = True) -> None:
        self.modules[module_id].updated = updated

    def add_suggestion(self, module_id: str, sugg: Suggestion) -> None:
        m = self.modules[module_id]
        m.suggestion = sugg
        m.updated = True

    def resolve(self, suggestion_id: str) -> None:
        for m in self.modules.values():
            if m.suggestion and m.suggestion.id == suggestion_id:
                m.suggestion = None
                m.updated = True

    def decide(self, suggestion_id: str, decision: str, note: str = "") -> None:
        """Record a decision on a suggestion (accepted/deferred/rejected) + reason."""
        for m in self.modules.values():
            if m.suggestion and m.suggestion.id == suggestion_id:
                m.suggestion.decision = decision
                m.suggestion.note = note
                m.updated = True
                return
        raise KeyError(f"no suggestion '{suggestion_id}'")

    # ---- module CRUD ------------------------------------------------------
    _EDITABLE = frozenset({
        "label", "domain", "depth", "size", "seam", "iface",
        "coverage", "updated", "files", "dependsOn", "leaksTo", "tests",
    })

    def _clamp(self, m: Module) -> None:
        m.depth = max(0.0, min(1.0, m.depth))
        m.coverage = max(0.0, min(1.0, m.coverage))

    def add_module(self, module: Module) -> None:
        if module.id in self.modules:
            raise KeyError(f"module '{module.id}' already exists")
        self._clamp(module)
        module.updated = True
        self.modules[module.id] = module

    def get_module(self, module_id: str) -> dict:
        m = self.modules[module_id]                  # KeyError if absent
        d = asdict(m)
        d["orphan"] = module_id in set(self.orphans())
        return d

    def update_module(self, module_id: str, **changes) -> None:
        m = self.modules[module_id]                  # KeyError if absent
        unknown = set(changes) - self._EDITABLE
        if unknown:
            raise ValueError(f"cannot update {sorted(unknown)}; editable: {sorted(self._EDITABLE)}")
        for k, v in changes.items():
            setattr(m, k, v)
        self._clamp(m)
        if "updated" not in changes:
            m.updated = True

    def delete_module(self, module_id: str) -> None:
        if module_id not in self.modules:
            raise KeyError(f"no module '{module_id}'")
        del self.modules[module_id]
        for m in self.modules.values():              # prune edges that pointed at it
            before = (len(m.dependsOn), len(m.leaksTo))
            m.dependsOn = [d for d in m.dependsOn if d != module_id]
            m.leaksTo = [t for t in m.leaksTo if t != module_id]
            if (len(m.dependsOn), len(m.leaksTo)) != before:
                m.updated = True

    # ---- bulk CRUD --------------------------------------------------------
    def add_modules(self, modules: list[Module]) -> None:
        ids = [m.id for m in modules]
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        clash = [i for i in ids if i in self.modules]
        if dupes:
            raise KeyError(f"duplicate ids in batch: {dupes}")
        if clash:
            raise KeyError(f"modules already exist: {clash}")
        for m in modules:
            self.add_module(m)

    def get_modules(self, module_ids: list[str]) -> list[dict]:
        orph = set(self.orphans())
        out = []
        for mid in module_ids:
            m = self.modules[mid]                    # KeyError if absent
            d = asdict(m)
            d["orphan"] = mid in orph
            out.append(d)
        return out

    def update_modules(self, updates: list[dict]) -> None:
        for u in updates:                            # validate all before applying
            mid = u.get("id")
            if not mid:
                raise ValueError("each update needs an 'id'")
            if mid not in self.modules:
                raise KeyError(f"no module '{mid}'")
        for u in updates:
            self.update_module(u["id"], **{k: v for k, v in u.items() if k != "id"})

    def delete_modules(self, module_ids: list[str]) -> None:
        missing = [i for i in module_ids if i not in self.modules]
        if missing:
            raise KeyError(f"no such modules: {missing}")
        for i in module_ids:
            self.delete_module(i)

    # ---- serialization ----------------------------------------------------
    def to_dict(self) -> dict:
        orphans = set(self.orphans())
        modules = []
        for m in self.modules.values():
            d = asdict(m)
            d["orphan"] = m.id in orphans
            modules.append(d)
        return {
            "repo": self.repo,
            "modules": modules,
            "orphans": sorted(orphans),
            "openSuggestions": sorted(
                {m.suggestion.id for m in self.modules.values() if m.suggestion}
            ),
        }

    def save(self, path: str | Path) -> None:
        """Persist atomically (write a temp file, then os.replace) so a crash or kill
        mid-write can't truncate the state file and silently drop modules/suggestions."""
        p = Path(path)
        tmp = p.with_name(f"{p.name}.{os.getpid()}.tmp")
        tmp.write_text(json.dumps(self.to_dict(), indent=2))
        os.replace(tmp, p)   # atomic on POSIX

    def to_view(self) -> dict:
        """Lightweight projection for MCP tool results / the graph: drops the heavy
        text (iface, files, tests, suggestion bodies) so the payload stays small
        enough for an agent's context. The browser UIs fetch the full model from
        /api/model; the graph only needs these fields to render."""
        orphans = set(self.orphans())
        modules = []
        for m in self.modules.values():
            s = m.suggestion
            modules.append({
                "id": m.id, "label": m.label, "domain": m.domain,
                "depth": m.depth, "coverage": m.coverage, "updated": m.updated,
                "dependsOn": m.dependsOn, "leaksTo": m.leaksTo,
                "orphan": m.id in orphans,
                "suggestion": ({"strength": s.strength} if s else None),
            })
        return {
            "repo": self.repo,
            "modules": modules,
            "orphans": sorted(orphans),
            "openSuggestions": sorted(
                {m.suggestion.id for m in self.modules.values() if m.suggestion}
            ),
        }

    @classmethod
    def from_json(cls, path: str | Path) -> "ArchModel":
        raw = json.loads(Path(path).read_text())
        modules: list[Module] = []
        for entry in raw["modules"]:
            entry = dict(entry)
            entry.pop("orphan", None)
            sugg_raw = entry.pop("suggestion", None)
            sugg = Suggestion(**sugg_raw) if sugg_raw else None
            modules.append(Module(suggestion=sugg, **entry))
        return cls(raw["repo"], modules)
