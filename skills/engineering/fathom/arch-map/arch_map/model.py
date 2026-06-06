"""The living architecture model that the arch-map MCP server maintains — the
shared "spine" the Fathom skills (map / deepen / plan / code / understand) read
and write.

Vocabulary comes straight from the deep-module principle:
module · interface · depth · seam · adapter · leverage · locality.

Two planes live in one model so a design can be staged beside reality:
  plane='actual'    what the code IS (seeded/reconciled by fathom:map, realized by fathom:code)
  plane='intended'  what fathom:plan WANTS — not-yet-built modules + intended edges

Field meanings the network UI encodes visually:
  depth      1.0 = deep (lots of behaviour behind a small interface), 0.0 = shallow
  coverage   0..1 test coverage *at the interface* (the ring around a node)
  updated    changed since the last reconcile -> the "updated" halo
  lifecycle  planned -> building -> built (a module's build state, set by fathom:code)
  suggestions open deepening opportunities -> the strength-coloured ring + ⚠ (a QUEUE,
             not one slot: a module can carry several candidates over its life)
  orphan     no edge in any direction -> "not connected" (computed, see orphans())
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path


def _only_known(cls, data: dict) -> dict:
    """Keep just the keys that are real fields of dataclass `cls` — so loading a
    map written by a newer/older schema (or carrying computed keys like 'orphan')
    never explodes on an unexpected kwarg."""
    names = {f.name for f in fields(cls)}
    return {k: v for k, v in data.items() if k in names}


@dataclass
class Suggestion:
    id: str
    title: str
    strength: str            # "Strong" | "Worth exploring" | "Speculative"
    category: str            # dependency category at the seam (in-process, ports & adapters, ...)
    problem: str
    solution: str
    wins: list[str] = field(default_factory=list)
    decision: str = ""           # "" | "accepted" | "deferred" | "rejected"  (the verdict)
    note: str = ""               # the reason captured when a decision is taken
    status: str = "open"         # open -> requested -> grilling -> grilled -> done (lifecycle)
    adrRef: str = ""             # docs/adr/NNNN-slug.md once a decision is recorded
    planId: str = ""             # the Plan an accepted candidate was promoted into


# A candidate is "open" (shows in the proposal queue) until it's been triaged
# AND closed out. Decided-but-kept suggestions persist as the durable record.
_OPEN = lambda s: s.decision == "" and s.status != "done"


@dataclass
class WorkStep:
    id: str
    title: str
    status: str = "todo"                                  # todo | in-progress | done | blocked
    targets: list[str] = field(default_factory=list)      # module ids this step builds/deepens
    interface: str = ""                                   # the interface (test surface) to build to
    dependsOnSteps: list[str] = field(default_factory=list)
    adapters: list[str] = field(default_factory=list)     # DEEPENING.md category + which adapters
    note: str = ""


@dataclass
class Plan:
    id: str
    title: str
    domain: str = ""
    intent: str = ""                                      # 1-3 sentences of the intended deep structure
    status: str = "draft"                                 # draft | active | done | abandoned
    moduleIds: list[str] = field(default_factory=list)    # the intended modules it introduces
    adrRefs: list[str] = field(default_factory=list)
    steps: list[WorkStep] = field(default_factory=list)   # ordered build steps fathom:code executes


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
    plane: str = "actual"                    # "actual" (what IS) | "intended" (what plan WANTS)
    lifecycle: str = "built"                 # "planned" -> "building" -> "built"
    files: list[str] = field(default_factory=list)
    dependsOn: list[str] = field(default_factory=list)       # actual dependency edges
    leaksTo: list[str] = field(default_factory=list)         # actual seam violations (actual-plane only)
    intendsToDependOn: list[str] = field(default_factory=list)  # intended edges (plane='intended')
    supersedes: list[str] = field(default_factory=list)      # actual module(s) an intended one will replace
    tests: str = ""
    suggestions: list[Suggestion] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> "Module":
        """Build a Module from a loose dict (the CRUD tools pass JSON-ish payloads).

        Ignores computed/managed keys (orphan, supersededBy, suggestions) and fills
        defaults, so a caller can pass just id/label/domain.
        """
        managed = {"suggestions", "suggestion", "orphan", "supersededBy"}
        d = _only_known(cls, {k: v for k, v in data.items() if k not in managed})
        for req in ("id", "label", "domain"):
            if not d.get(req):
                raise ValueError(f"module needs '{req}'")
        d.setdefault("depth", 0.5)
        d.setdefault("size", 1.0)
        d.setdefault("seam", "")
        return cls(**d)


class ArchModel:
    """In-memory architecture model. The MCP tools mutate it; the UI renders it."""

    def __init__(self, repo: str, modules: list[Module], plans: list[Plan] | None = None):
        self.repo = repo
        self.modules: dict[str, Module] = {m.id: m for m in modules}
        self.plans: dict[str, Plan] = {p.id: p for p in (plans or [])}

    # ---- queries ----------------------------------------------------------
    def orphans(self) -> list[str]:
        """Modules with no edge in ANY direction — 'not connected'. Plane-aware:
        intended modules connect via intendsToDependOn / supersedes, so they aren't
        flagged just for lacking real dependsOn edges."""
        connected: set[str] = set()
        for m in self.modules.values():
            edges = m.dependsOn + m.leaksTo + m.intendsToDependOn + m.supersedes
            if edges:
                connected.add(m.id)
                connected.update(edges)
        return [mid for mid in self.modules if mid not in connected]

    def _superseded_by(self) -> dict[str, list[str]]:
        """Reverse of supersedes: actual module id -> intended module ids replacing it."""
        rev: dict[str, list[str]] = {}
        for m in self.modules.values():
            for target in m.supersedes:
                rev.setdefault(target, []).append(m.id)
        return rev

    # ---- module metrics ---------------------------------------------------
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

    def set_plane(self, module_id: str, plane: str) -> None:
        self.modules[module_id].plane = plane
        self.modules[module_id].updated = True

    def set_lifecycle(self, module_id: str, lifecycle: str) -> None:
        self.modules[module_id].lifecycle = lifecycle
        self.modules[module_id].updated = True

    def realize_module(self, module_id: str, depth: float | None = None,
                       coverage: float | None = None, files: list[str] | None = None) -> None:
        """fathom:code flips an intended/planned module to a real built one (atomically
        on the map): plane->actual, lifecycle->built, and optionally the achieved
        depth/coverage/files now that source exists."""
        m = self.modules[module_id]
        m.plane = "actual"
        m.lifecycle = "built"
        if depth is not None:
            m.depth = max(0.0, min(1.0, depth))
        if coverage is not None:
            m.coverage = max(0.0, min(1.0, coverage))
        if files is not None:
            m.files = files
        m.updated = True

    # ---- suggestions (a per-module queue) --------------------------------
    def _find_suggestion(self, suggestion_id: str) -> tuple[Module, Suggestion]:
        for m in self.modules.values():
            for s in m.suggestions:
                if s.id == suggestion_id:
                    return m, s
        raise KeyError(f"no suggestion '{suggestion_id}'")

    def add_suggestion(self, module_id: str, sugg: Suggestion) -> None:
        """Attach a deepening candidate. Re-flagging the same id REPLACES it in place;
        otherwise it's appended — a module accrues a queue of candidates over time."""
        m = self.modules[module_id]
        for i, existing in enumerate(m.suggestions):
            if existing.id == sugg.id:
                m.suggestions[i] = sugg
                break
        else:
            m.suggestions.append(sugg)
        m.updated = True

    def resolve(self, suggestion_id: str) -> None:
        """Close a candidate out (executed or dismissed). Does NOT delete it — the
        suggestion persists with status='done' so the record (and any decision/ADR
        link) survives for future explorers. KeyError if unknown."""
        m, s = self._find_suggestion(suggestion_id)
        s.status = "done"
        m.updated = True

    def decide(self, suggestion_id: str, decision: str, note: str = "",
               adr: str = "", expect_status: str | None = None) -> None:
        """Record a verdict (accepted/deferred/rejected, or '' to re-open) + reason on
        a candidate; the candidate stays attached. `expect_status` is an optimistic
        guard — raise if the candidate moved under the caller (e.g. a browser reject
        racing an agent's grill verdict). KeyError if unknown."""
        m, s = self._find_suggestion(suggestion_id)
        if expect_status is not None and s.status != expect_status:
            raise ValueError(
                f"suggestion '{suggestion_id}' is '{s.status}', not '{expect_status}' "
                f"— re-read before deciding")
        s.decision = decision
        s.note = note
        if adr:
            s.adrRef = adr
        m.updated = True

    # ---- grilling lifecycle (open -> requested -> grilling -> grilled) ----
    def request_grilling(self, suggestion_id: str) -> None:
        """Flag a candidate for grilling (e.g. the studio's 'Grill this candidate'
        button, or fathom:deepen queuing one). Idempotent: won't yank a candidate
        already mid-grill back to 'requested'."""
        m, s = self._find_suggestion(suggestion_id)
        if s.status in ("open", "", "done", "grilled"):
            s.status = "requested"
        m.updated = True

    def mark_grilling(self, suggestion_id: str) -> None:
        m, s = self._find_suggestion(suggestion_id)
        s.status = "grilling"
        m.updated = True

    def mark_grilled(self, suggestion_id: str) -> None:
        m, s = self._find_suggestion(suggestion_id)
        s.status = "grilled"
        m.updated = True

    def queued_for_grilling(self) -> list[dict]:
        """Candidates a UI flagged for grilling that no agent has picked up yet —
        what a terminal-only fathom:deepen polls to find work queued elsewhere."""
        out = []
        for m in self.modules.values():
            for s in m.suggestions:
                if s.status == "requested":
                    out.append({"module": m.id, "suggestion_id": s.id,
                                "title": s.title, "strength": s.strength})
        return out

    # ---- module CRUD ------------------------------------------------------
    _EDITABLE = frozenset({
        "label", "domain", "depth", "size", "seam", "iface", "coverage", "updated",
        "plane", "lifecycle", "files", "dependsOn", "leaksTo", "intendsToDependOn",
        "supersedes", "tests",
    })
    _EDGE_FIELDS = ("dependsOn", "leaksTo", "intendsToDependOn", "supersedes")

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
        d["supersededBy"] = self._superseded_by().get(module_id, [])
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
        for m in self.modules.values():              # prune every edge type that pointed at it
            changed = False
            for fld in self._EDGE_FIELDS:
                pruned = [x for x in getattr(m, fld) if x != module_id]
                if len(pruned) != len(getattr(m, fld)):
                    setattr(m, fld, pruned)
                    changed = True
            if changed:
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
        rev = self._superseded_by()
        out = []
        for mid in module_ids:
            m = self.modules[mid]                    # KeyError if absent
            d = asdict(m)
            d["orphan"] = mid in orph
            d["supersededBy"] = rev.get(mid, [])
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

    # ---- plans + work steps (fathom:plan creates, fathom:code executes) ---
    def create_plan(self, plan: Plan) -> None:
        if plan.id in self.plans:
            raise KeyError(f"plan '{plan.id}' already exists")
        self.plans[plan.id] = plan

    def get_plan(self, plan_id: str) -> dict:
        return asdict(self.plans[plan_id])           # KeyError if absent

    _PLAN_EDITABLE = frozenset({"title", "domain", "intent", "status", "moduleIds", "adrRefs"})

    def update_plan(self, plan_id: str, **changes) -> None:
        p = self.plans[plan_id]                      # KeyError if absent
        unknown = set(changes) - self._PLAN_EDITABLE
        if unknown:
            raise ValueError(f"cannot update {sorted(unknown)}; editable: {sorted(self._PLAN_EDITABLE)}")
        for k, v in changes.items():
            setattr(p, k, v)

    def add_work_steps(self, plan_id: str, steps: list[WorkStep]) -> None:
        p = self.plans[plan_id]                      # KeyError if absent
        have = {s.id for s in p.steps}
        clash = [s.id for s in steps if s.id in have]
        if clash:
            raise KeyError(f"steps already exist in plan '{plan_id}': {clash}")
        p.steps.extend(steps)

    def set_step_status(self, plan_id: str, step_id: str, status: str) -> None:
        p = self.plans[plan_id]                      # KeyError if absent
        for s in p.steps:
            if s.id == step_id:
                s.status = status
                return
        raise KeyError(f"no step '{step_id}' in plan '{plan_id}'")

    def delete_plan(self, plan_id: str) -> None:
        if plan_id not in self.plans:
            raise KeyError(f"no plan '{plan_id}'")
        del self.plans[plan_id]

    # ---- serialization ----------------------------------------------------
    def _open_suggestion_ids(self) -> list[str]:
        return sorted(s.id for m in self.modules.values() for s in m.suggestions if _OPEN(s))

    def to_dict(self) -> dict:
        orphans = set(self.orphans())
        rev = self._superseded_by()
        modules = []
        for m in self.modules.values():
            d = asdict(m)
            d["orphan"] = m.id in orphans
            d["supersededBy"] = rev.get(m.id, [])
            # Back-compat convenience for any consumer still reading a single
            # suggestion: surface the first OPEN candidate (or None).
            first_open = next((asdict(s) for s in m.suggestions if _OPEN(s)), None)
            d["suggestion"] = first_open
            modules.append(d)
        return {
            "repo": self.repo,
            "modules": modules,
            "plans": [asdict(p) for p in self.plans.values()],
            "orphans": sorted(orphans),
            "openSuggestions": self._open_suggestion_ids(),
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
            sugg = [{"id": s.id, "strength": s.strength, "status": s.status,
                     "decision": s.decision} for s in m.suggestions]
            first_open = next((s for s in sugg if s["decision"] == "" and s["status"] != "done"), None)
            modules.append({
                "id": m.id, "label": m.label, "domain": m.domain,
                "depth": m.depth, "coverage": m.coverage, "updated": m.updated,
                "plane": m.plane, "lifecycle": m.lifecycle,
                "dependsOn": m.dependsOn, "leaksTo": m.leaksTo,
                "intendsToDependOn": m.intendsToDependOn, "supersedes": m.supersedes,
                "orphan": m.id in orphans,
                "suggestions": sugg,
                # back-compat: the single open candidate's strength, as before
                "suggestion": ({"strength": first_open["strength"]} if first_open else None),
            })
        return {
            "repo": self.repo,
            "modules": modules,
            "plans": [{"id": p.id, "title": p.title, "status": p.status,
                       "steps": len(p.steps), "modules": len(p.moduleIds)}
                      for p in self.plans.values()],
            "orphans": sorted(orphans),
            "openSuggestions": self._open_suggestion_ids(),
        }

    @classmethod
    def from_json(cls, path: str | Path) -> "ArchModel":
        raw = json.loads(Path(path).read_text())
        modules: list[Module] = []
        for entry in raw["modules"]:
            entry = dict(entry)
            for computed in ("orphan", "supersededBy"):
                entry.pop(computed, None)
            sugg_list = entry.pop("suggestions", None)
            single = entry.pop("suggestion", None)          # pre-queue format (one slot)
            if sugg_list is None:
                sugg_list = [single] if single else []
            suggestions = [Suggestion(**_only_known(Suggestion, s)) for s in sugg_list if s]
            mod = Module(**_only_known(Module, entry))
            mod.suggestions = suggestions
            modules.append(mod)
        plans: list[Plan] = []
        for p in raw.get("plans", []):
            steps = [WorkStep(**_only_known(WorkStep, s)) for s in p.get("steps", [])]
            plan = Plan(**_only_known(Plan, {k: v for k, v in p.items() if k != "steps"}))
            plan.steps = steps
            plans.append(plan)
        return cls(raw["repo"], modules, plans)
