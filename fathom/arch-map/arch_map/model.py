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


# The six task-board columns ARE the Fathom skill cycle — a card flows left->right
# through them: todo -> understand (fathom:understand) -> plan (fathom:design) ->
# in-progress (fathom:code) -> review (fathom:review) -> done. Legacy maps stored
# 'blocked' as a status; it is NOT a column — board() projects it onto the `blocked`
# flag, so old data renders with no migration.
WORKSTEP_STAGES = ("todo", "understand", "plan", "in-progress", "review", "done")


@dataclass
class WorkStep:
    id: str
    title: str
    status: str = "todo"           # the board column / skill-cycle stage (WORKSTEP_STAGES);
                                   # legacy 'blocked' still loads -> projected to `blocked`
    targets: list[str] = field(default_factory=list)      # module ids this step builds/deepens
    interface: str = ""                                   # the interface (test surface) to build to
    dependsOnSteps: list[str] = field(default_factory=list)
    adapters: list[str] = field(default_factory=list)     # DEEPENING.md category + which adapters
    note: str = ""
    priority: str = "normal"       # low | normal | high | urgent — ordering within a board column
    agent: str = ""                # the handler this task is assigned to — the board's swimlane row
    worktree: str = ""             # id of the Worktree this task is isolated in (per-task branch)
    blocked: bool = False          # orthogonal flag — a card can be blocked in any column


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
class Worktree:
    """A git worktree: an isolated branch + checkout where ONE task (a WorkStep) is
    built by an agent, in parallel with the others. The spine RECORDS it (the studio
    board shows the branch + which agent is working it); worktrees.py does the real
    `git worktree` work. Per-task isolation is the parallel-development unit — a card
    on the board carries its worktree id, so the work, the branch, and the agent
    travel together through the skill cycle."""
    id: str
    branch: str
    path: str = ""                 # filesystem path of the worktree checkout
    base: str = ""                 # the ref/sha the branch forked from (review diffs against this)
    status: str = "active"         # active | merged | removed
    planId: str = ""               # the Plan this task belongs to
    stepId: str = ""               # the WorkStep this worktree isolates
    agent: str = ""                # the handler running in this worktree (the board swimlane)
    head: str = ""                 # last-known HEAD sha of the branch
    created: str = ""
    note: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> "Worktree":
        d = _only_known(cls, data)
        for req in ("id", "branch"):
            if not d.get(req):
                raise ValueError(f"worktree needs '{req}'")
        return cls(**d)


@dataclass
class Module:
    id: str
    label: str
    domain: str
    depth: float
    size: float                              # relative implementation mass (1.0 == median module); measured from LOC by archmap_ingest; weights whatif merges + fires bulky-impl. Non-visual: node size is a constant, depth drives node fill colour.
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
    churn: float = 0.0          # commit frequency 0..1 (set by fathom:map via git log)
    tags: list[str] = field(default_factory=list)   # free-text labels; the anti-rot lever for query-scoped docs
    craft: dict = field(default_factory=dict)        # line-level craft facts (maxFnLen/maxArgs/maxNesting/methodCount/magicNumbers/commentedOutBlocks) from craft_ingest; feeds the craft signal family
    depthProxy: float = 0.0                          # measured leverage proxy (impl/iface, median-normalized) from measure.py; compared against the judged depth
    cohesion: float = 1.0                            # internal file interconnectedness (measure.py)
    ifaceSize: int = 0                               # public/exported symbol count, the seam width (measure.py)

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


# ---- docs: scoped architecture documents (doc-registry) ---------------------
# Docs live ONLY on the spine — there is no docs/ file mirror. The type set spans
# the engineer cycle: knowledge (glossary/note/risk/runbook/postmortem), a visual
# (diagram, a Mermaid body), decisions (rfc -> adr), the design->code contract
# (spec), and build/style (rule/ceiling). See ../fathom/DOC-TYPES.md.
_DOC_TYPES = frozenset({
    "adr", "note", "rule", "rfc", "glossary",          # original five
    "spec", "ceiling", "risk", "runbook", "postmortem", "diagram",  # v2 additions
})
_SCOPE_KINDS = frozenset({"system", "explicit", "domain", "query"})


@dataclass
class Scope:
    """What a Doc applies to — a closed union over four kinds. `system` covers the
    whole map; `explicit` a pinned id list; `domain` every module in one domain
    (containment == same domain); `query` a live predicate (AND over the keys
    present). Serializes to/from a plain dict so it rides in JSON unchanged."""
    kind: str = "system"
    ids: list[str] = field(default_factory=list)       # explicit
    domain: str = ""                                    # domain
    predicate: dict = field(default_factory=dict)       # query

    @classmethod
    def from_dict(cls, data: dict | None) -> "Scope":
        if not data:
            return cls(kind="system")
        kind = data.get("kind") or "system"
        if kind not in _SCOPE_KINDS:
            raise ValueError(f"invalid scope kind '{kind}'; expected one of {sorted(_SCOPE_KINDS)}")
        return cls(kind=kind,
                   ids=list(data.get("ids") or []),
                   domain=data.get("domain") or "",
                   predicate=dict(data.get("predicate") or {}))


@dataclass
class Doc:
    """A scoped architecture document, spine-only (no file mirror). A TOP-LEVEL
    entity (like Plan), NOT nested per-module, so one doc can scope to many
    modules, a domain, or the whole system. `resolvedModuleIds` / `drift` /
    `scopeLabel` are COMPUTED at serialization (see resolve) — never stored.
    See ../fathom/DOC-TYPES.md for the type set and per-type lifecycle."""
    id: str
    type: str                                           # one of _DOC_TYPES (DOC-TYPES.md)
    title: str
    summary: str = ""                                   # one-line TL;DR (information scent)
    body: str = ""                                      # markdown
    status: str = ""                                    # per-type lifecycle
    scope: Scope = field(default_factory=Scope)
    tags: list[str] = field(default_factory=list)
    author: str = ""
    created: str = ""
    updated: str = ""
    supersedes: list[str] = field(default_factory=list)   # doc -> doc links
    adrRef: str = ""                                     # id of the adr-type doc that records this decision

    @classmethod
    def from_dict(cls, data: dict) -> "Doc":
        """Build a Doc from a loose dict: drop computed keys, validate id/type/title,
        check the type against the known set, and reify the nested Scope."""
        managed = {"resolvedModuleIds", "drift", "scopeLabel", "supersededBy"}
        d = _only_known(cls, {k: v for k, v in data.items() if k not in managed})
        for req in ("id", "type", "title"):
            if not d.get(req):
                raise ValueError(f"doc needs '{req}'")
        if d["type"] not in _DOC_TYPES:
            raise ValueError(f"invalid doc type '{d['type']}'; expected one of {sorted(_DOC_TYPES)}")
        d["scope"] = Scope.from_dict(d.get("scope"))
        return cls(**d)


# ---- doc-scope-resolver: turn a Scope into the module ids it applies to -------
@dataclass
class Resolution:
    """The answer for one Scope against the live model. `ids` are sorted and exist
    in the model; `missing` is drift (explicit ids no longer present). Both are
    values, never exceptions, so a rotted doc can't break serialization."""
    ids: list[str]
    missing: list[str]
    count: int
    label: str
    kind: str
    empty: bool


class MembershipIndex:
    """Inverted index module-id -> [doc-id], built once by resolve_all so the UI can
    badge a node with an O(1) lookup instead of re-resolving every doc per node."""
    def __init__(self, by_module: dict[str, list[str]]):
        self._by = by_module

    def docsForModule(self, module_id: str) -> list[str]:
        return list(self._by.get(module_id, ()))

    def isMember(self, module_id: str, doc_id: str) -> bool:
        return doc_id in self._by.get(module_id, ())

    def as_dict(self) -> dict[str, list[str]]:
        return {k: list(v) for k, v in self._by.items()}


def _match_query(m: "Module", has_open_candidate: bool, pred: dict) -> bool:
    """Closed predicate interpreter — AND over the keys present; an unknown key is
    ignored (tolerant). Kept SEPARATE from resolve so a SelectorPort could be
    extracted later without touching the resolver core."""
    if "domain" in pred and m.domain != pred["domain"]:
        return False
    if "plane" in pred and m.plane != pred["plane"]:
        return False
    if "lifecycle" in pred and m.lifecycle != pred["lifecycle"]:
        return False
    if "depthGte" in pred and not (m.depth >= pred["depthGte"]):
        return False
    if "depthLte" in pred and not (m.depth <= pred["depthLte"]):
        return False
    if "coverageLte" in pred and not (m.coverage <= pred["coverageLte"]):
        return False
    if "hasLeak" in pred and bool(m.leaksTo) != bool(pred["hasLeak"]):
        return False
    if "hasOpenCandidate" in pred and has_open_candidate != bool(pred["hasOpenCandidate"]):
        return False
    if "tag" in pred and pred["tag"] not in (m.tags or []):
        return False
    return True


def _scope_label(kind: str, scope: "Scope", count: int, missing: int) -> str:
    noun = "module" if count == 1 else "modules"
    if kind == "system":
        base = f"Whole system — {count} {noun}"
    elif kind == "domain":
        base = f"Domain: {scope.domain} — {count} {noun}"
    elif kind == "explicit":
        base = f"Explicit — {count} {noun}"
    elif kind == "query":
        base = f"Query — {count} {noun}"
    else:
        base = f"{count} {noun}"
    if missing:
        base += f" ({missing} missing)"
    return base


def _open_candidate_ids(model) -> set[str]:
    return {m.id for m in model.modules.values()
            if any(_OPEN(s) for s in m.suggestions)}


def _resolve(scope: "Scope", model, all_ids: list[str], open_ids: set[str]) -> Resolution:
    kind = getattr(scope, "kind", "system")
    mods = model.modules
    missing: list[str] = []
    if kind == "system":
        ids = list(all_ids)
    elif kind == "explicit":
        want = scope.ids or []
        ids = sorted({i for i in want if i in mods})
        missing = sorted({i for i in want if i not in mods})
    elif kind == "domain":
        ids = sorted(mid for mid, m in mods.items() if m.domain == scope.domain)
    elif kind == "query":
        pred = scope.predicate or {}
        ids = sorted(mid for mid, m in mods.items()
                     if _match_query(m, mid in open_ids, pred))
    else:                                    # unknown kind -> empty (errors are data)
        ids = []
    count = len(ids)
    return Resolution(ids=ids, missing=missing, count=count,
                      label=_scope_label(kind, scope, count, len(missing)),
                      kind=kind, empty=count == 0)


def resolve(scope: "Scope", model) -> Resolution:
    """Resolve one Scope against the model. Pure; ids sorted + deterministic. This
    is the UI-lens entry point (and what get_doc bakes)."""
    return _resolve(scope, model, sorted(model.modules.keys()), _open_candidate_ids(model))


def resolve_all(docs, model) -> dict:
    """Batch-resolve every doc in ONE pass (shared keyset + open-candidate set) and
    build the inverted MembershipIndex — the server-projection entry point. A doc
    whose scope blows up soft-fails to an empty Resolution, so one bad doc can never
    sink the whole projection."""
    all_ids = sorted(model.modules.keys())
    open_ids = _open_candidate_ids(model)
    by_doc: dict[str, Resolution] = {}
    by_module: dict[str, list[str]] = {}
    for doc in docs:
        try:
            r = _resolve(doc.scope, model, all_ids, open_ids)
        except Exception:                    # malformed scope -> soft-fail this one doc
            r = Resolution(ids=[], missing=[], count=0, label="⚠ invalid scope",
                           kind=getattr(doc.scope, "kind", "?"), empty=True)
        by_doc[doc.id] = r
        for mid in r.ids:
            by_module.setdefault(mid, []).append(doc.id)
    for mid in by_module:
        by_module[mid].sort()
    return {"byDoc": by_doc, "membership": MembershipIndex(by_module)}


class ArchModel:
    """In-memory architecture model. The MCP tools mutate it; the UI renders it."""

    def __init__(self, repo: str, modules: list[Module], plans: list[Plan] | None = None,
                 docs: list[Doc] | None = None, worktrees: list[Worktree] | None = None):
        self.repo = repo
        self.modules: dict[str, Module] = {m.id: m for m in modules}
        self.plans: dict[str, Plan] = {p.id: p for p in (plans or [])}
        self.docs: dict[str, Doc] = {d.id: d for d in (docs or [])}
        # Worktrees: per-task isolated branches (one per WorkStep). The board shows them.
        self.worktrees: dict[str, Worktree] = {w.id: w for w in (worktrees or [])}
        # Reconcile anchors (ledger.py owns their shape). The model carries them
        # as opaque dicts so they ride to_dict/save/from_json with everything else.
        self.anchors: list[dict] = []

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

    def owners_of(self, paths: list[str]) -> dict[str, list[str]]:
        """Map repo-relative paths to the modules that own them. The ownership rule
        (the contract, not the algorithm): a path belongs to module m iff it equals
        an entry of m.files, or sits under a directory entry of m.files. A path may
        belong to several modules; paths owned by none are silently omitted. Keys
        sorted, file lists sorted + deduplicated. Pure and deterministic."""
        def norm(p: str) -> str:
            p = str(p).replace("\\", "/")
            return p[2:] if p.startswith("./") else p
        wanted = [norm(p) for p in paths]
        out: dict[str, list[str]] = {}
        for mid in sorted(self.modules):
            entries = [norm(e).rstrip("/") for e in self.modules[mid].files if e]
            owned = sorted({p for p in wanted
                            if any(p == e or p.startswith(e + "/") for e in entries)})
            if owned:
                out[mid] = owned
        return out

    # ---- computed graph metrics (all read-only, derived from edges) ----------
    def _fan_in(self) -> dict[str, int]:
        """Number of modules that directly depend on each module."""
        fi: dict[str, int] = {mid: 0 for mid in self.modules}
        for m in self.modules.values():
            for dep in m.dependsOn:
                if dep in fi:
                    fi[dep] += 1
        return fi

    def _blast_radius(self, fan_in_map: dict[str, int] | None = None) -> dict[str, int]:
        """Transitive fan-in: how many modules are (transitively) affected if this one changes."""
        # Build reverse adjacency once
        rev: dict[str, set[str]] = {mid: set() for mid in self.modules}
        for m in self.modules.values():
            for dep in m.dependsOn:
                if dep in rev:
                    rev[dep].add(m.id)
        # BFS from each node
        result: dict[str, int] = {}
        for start in self.modules:
            visited: set[str] = set()
            queue = list(rev[start])
            while queue:
                node = queue.pop()
                if node not in visited:
                    visited.add(node)
                    queue.extend(rev.get(node, set()) - visited)
            result[start] = len(visited)
        return result

    def _find_cycles(self) -> set[str]:
        """Module ids that are part of a dependency cycle (DFS with colour marking)."""
        WHITE, GRAY, BLACK = 0, 1, 2
        color = {mid: WHITE for mid in self.modules}
        in_cycle: set[str] = set()
        stack: list[str] = []

        def dfs(node: str) -> None:
            color[node] = GRAY
            stack.append(node)
            for dep in self.modules[node].dependsOn:
                if dep not in color:
                    continue
                if color[dep] == GRAY:
                    # back edge — everything from dep to here is on a cycle.
                    # GRAY means "on the stack", so index() is safe; keep
                    # scanning the remaining deps (a node can sit on several
                    # cycles) and always fall through to the pop below.
                    in_cycle.update(stack[stack.index(dep):])
                elif color[dep] == WHITE:
                    dfs(dep)
            stack.pop()
            color[node] = BLACK

        for mid in list(self.modules):
            if color[mid] == WHITE:
                dfs(mid)
        return in_cycle

    def compute_metrics(self) -> dict[str, dict]:
        """Return a dict of mid -> metrics for every module. Called once per render."""
        fi = self._fan_in()
        br = self._blast_radius(fi)
        cycles = self._find_cycles()
        result: dict[str, dict] = {}
        for m in self.modules.values():
            fo = len(m.dependsOn)
            fan_in = fi[m.id]
            total = fan_in + fo
            instability = round(fo / total, 3) if total else 0.5
            cross = sum(1 for dep in m.dependsOn
                        if dep in self.modules and self.modules[dep].domain != m.domain)
            # health: depth 40% + coverage 40% - leaks 20% - churn penalty 10%
            health = round(
                min(100, max(0,
                    m.depth * 40 + m.coverage * 40
                    - len(m.leaksTo) * 10
                    - m.churn * 10
                )),
            )
            result[m.id] = {
                "fanIn":       fan_in,
                "fanOut":      fo,
                "instability": instability,   # 0=stable, 1=fragile
                "blastRadius": br[m.id],
                "coupling":    cross,          # cross-domain dep count
                "inCycle":     m.id in cycles,
                "health":      health,         # 0-100 composite
                "churn":       m.churn,
            }
        return result

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
        "label", "domain", "depth", "size", "seam", "iface", "coverage", "churn",
        "updated", "plane", "lifecycle", "files", "dependsOn", "leaksTo",
        "intendsToDependOn", "supersedes", "tests", "tags",
    })
    _EDGE_FIELDS = ("dependsOn", "leaksTo", "intendsToDependOn", "supersedes")

    def _clamp(self, m: Module) -> None:
        m.depth = max(0.0, min(1.0, m.depth))
        m.coverage = max(0.0, min(1.0, m.coverage))
        m.churn = max(0.0, min(1.0, m.churn))

    def add_module(self, module: Module) -> None:
        if module.id in self.modules:
            raise KeyError(f"module '{module.id}' already exists")
        self._clamp(module)
        module.updated = True
        self.modules[module.id] = module

    def get_module(self, module_id: str) -> dict:
        if module_id not in self.modules:
            raise KeyError(f"no module '{module_id}'. Call show_map to list module "
                           f"ids, or modules(action='add') to create it.")
        m = self.modules[module_id]
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
        if plan_id not in self.plans:
            raise KeyError(f"no plan '{plan_id}'. Call get_full_model to see this "
                           f"map's plans, or plans(action='create') to create one.")
        return asdict(self.plans[plan_id])

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

    def _find_step(self, plan_id: str, step_id: str) -> WorkStep:
        p = self.plans[plan_id]                      # KeyError if absent
        for s in p.steps:
            if s.id == step_id:
                return s
        raise KeyError(f"no step '{step_id}' in plan '{plan_id}'")

    def set_step_status(self, plan_id: str, step_id: str, status: str) -> None:
        self._find_step(plan_id, step_id).status = status

    _STEP_FIELD_EDITABLE = frozenset({"status", "priority", "agent", "worktree", "blocked",
                                      "title", "interface", "note", "targets", "adapters",
                                      "dependsOnSteps"})

    def set_step_fields(self, plan_id: str, step_id: str, **changes) -> None:
        """Patch a WorkStep's board fields (agent/priority/worktree/blocked/status/...)
        in place — the board's assign / prioritise / block / move controls. Rejects
        keys outside the editable whitelist (id is immutable) with ValueError."""
        unknown = set(changes) - self._STEP_FIELD_EDITABLE
        if unknown:
            raise ValueError(f"cannot update step {sorted(unknown)}; "
                             f"editable: {sorted(self._STEP_FIELD_EDITABLE)}")
        s = self._find_step(plan_id, step_id)        # KeyError if absent
        for k, v in changes.items():
            setattr(s, k, v)

    def delete_plan(self, plan_id: str) -> None:
        if plan_id not in self.plans:
            raise KeyError(f"no plan '{plan_id}'")
        del self.plans[plan_id]

    # ---- worktrees (per-task isolated branches; worktrees.py does the git) -----
    # The spine RECORDS worktrees; the studio board renders them and worktrees.py
    # runs the real `git worktree`. fathom:design creates one per task, fathom:code
    # builds in it, fathom:review diffs its branch, fathom:map syncs them.
    _WT_EDITABLE = frozenset({"branch", "path", "base", "status", "planId", "stepId",
                              "agent", "head", "created", "note"})

    def add_worktree(self, wt: Worktree) -> None:
        if wt.id in self.worktrees:
            raise KeyError(f"worktree '{wt.id}' already exists")
        self.worktrees[wt.id] = wt
        # keep the owning step's back-reference in sync, so a card knows its worktree
        if wt.planId and wt.stepId:
            try:
                self._find_step(wt.planId, wt.stepId).worktree = wt.id
            except KeyError:
                pass

    def get_worktree(self, wt_id: str) -> dict:
        if wt_id not in self.worktrees:
            raise KeyError(f"no worktree '{wt_id}'. Call worktrees(action='list') to "
                           f"list them, or worktrees(action='create') to make one.")
        return asdict(self.worktrees[wt_id])

    def update_worktree(self, wt_id: str, **changes) -> None:
        w = self.worktrees[wt_id]                    # KeyError if absent
        unknown = set(changes) - self._WT_EDITABLE
        if unknown:
            raise ValueError(f"cannot update {sorted(unknown)}; editable: {sorted(self._WT_EDITABLE)}")
        for k, v in changes.items():
            setattr(w, k, v)
        if w.planId and w.stepId:
            try:
                self._find_step(w.planId, w.stepId).worktree = w.id
            except KeyError:
                pass

    def delete_worktree(self, wt_id: str) -> None:
        if wt_id not in self.worktrees:
            raise KeyError(f"no worktree '{wt_id}'")
        w = self.worktrees.pop(wt_id)
        # drop the back-reference from any step that pointed at it
        for p in self.plans.values():
            for s in p.steps:
                if s.worktree == wt_id:
                    s.worktree = ""

    def link_step_worktree(self, plan_id: str, step_id: str, wt_id: str) -> None:
        """Attach an existing worktree to a step (and the step's back-reference)."""
        if wt_id not in self.worktrees:
            raise KeyError(f"no worktree '{wt_id}'")
        s = self._find_step(plan_id, step_id)        # KeyError if absent
        s.worktree = wt_id
        w = self.worktrees[wt_id]
        w.planId, w.stepId = plan_id, step_id

    # ---- the board: the skill-cycle Kanban projection -------------------------
    def board(self, running: set | None = None) -> dict:
        """Project every WorkStep into the task board: columns are the skill cycle
        (WORKSTEP_STAGES), rows are agents (swimlanes). Pure read, one pass over
        plans[*].steps. `running` is the set of (planId, stepId) an agent is actively
        dispatched on (the ⚙ live marker); it is data, never stored. A step whose
        status is the legacy 'blocked' lands in the `todo` column with blocked=True,
        so old maps need no migration."""
        running = running or set()
        cards: list[dict] = []
        lanes: dict[str, list[dict]] = {}
        for p in self.plans.values():
            for s in p.steps:
                column = s.status if s.status in WORKSTEP_STAGES else "todo"
                wt = self.worktrees.get(s.worktree) if s.worktree else None
                agent = s.agent or "unassigned"
                card = {
                    "planId": p.id, "planTitle": p.title,
                    "stepId": s.id, "title": s.title,
                    "column": column,
                    "blocked": bool(s.blocked) or s.status == "blocked",
                    "priority": s.priority or "normal",
                    "agent": agent,
                    "targets": list(s.targets or []),
                    "interface": s.interface or "",
                    "dependsOnSteps": list(s.dependsOnSteps or []),
                    "running": (p.id, s.id) in running,
                    "worktree": ({"id": wt.id, "branch": wt.branch, "path": wt.path,
                                  "status": wt.status, "base": wt.base, "agent": wt.agent}
                                 if wt else None),
                }
                cards.append(card)
                lanes.setdefault(agent, []).append(card)
        # priority ordering within a column/lane: urgent -> high -> normal -> low
        rank = {"urgent": 0, "high": 1, "normal": 2, "low": 3}
        cards.sort(key=lambda c: (rank.get(c["priority"], 2), c["planId"], c["stepId"]))
        counts = {stage: 0 for stage in WORKSTEP_STAGES}
        for c in cards:
            counts[c["column"]] += 1
        lane_list = [{"agent": a, "cards": sorted(cs, key=lambda c: (rank.get(c["priority"], 2), c["stepId"]))}
                     for a, cs in sorted(lanes.items(), key=lambda kv: (kv[0] == "unassigned", kv[0]))]
        return {
            "columns": list(WORKSTEP_STAGES),
            "counts": counts,
            "lanes": lane_list,
            "cards": cards,
            "worktrees": [asdict(w) for w in self.worktrees.values()],
        }

    # ---- docs (fathom skills + the UI author; the resolver computes scope) -
    _DOC_EDITABLE = frozenset({
        "type", "title", "summary", "body", "status", "scope", "tags",
        "author", "created", "updated", "supersedes", "adrRef",
    })

    def add_doc(self, doc: Doc) -> None:
        if doc.id in self.docs:
            raise KeyError(f"doc '{doc.id}' already exists")
        self.docs[doc.id] = doc

    def get_doc(self, doc_id: str) -> dict:
        if doc_id not in self.docs:
            raise KeyError(f"no doc '{doc_id}'. Call docs(action='list') to see this "
                           f"map's docs, or docs(action='add') to create one.")
        d = self.docs[doc_id]
        out = asdict(d)
        r = resolve(d.scope, self)
        out["resolvedModuleIds"] = r.ids
        out["drift"] = r.missing
        out["scopeLabel"] = r.label
        return out

    def get_docs(self, doc_ids: list[str]) -> list[dict]:
        return [self.get_doc(i) for i in doc_ids]

    def update_doc(self, doc_id: str, **changes) -> None:
        d = self.docs[doc_id]                        # KeyError if absent
        unknown = set(changes) - self._DOC_EDITABLE
        if unknown:
            raise ValueError(f"cannot update {sorted(unknown)}; editable: {sorted(self._DOC_EDITABLE)}")
        if "type" in changes and changes["type"] not in _DOC_TYPES:
            raise ValueError(f"invalid doc type '{changes['type']}'; expected one of {sorted(_DOC_TYPES)}")
        if "scope" in changes and isinstance(changes["scope"], dict):
            changes["scope"] = Scope.from_dict(changes["scope"])
        for k, v in changes.items():
            setattr(d, k, v)

    def delete_doc(self, doc_id: str) -> None:
        if doc_id not in self.docs:
            raise KeyError(f"no doc '{doc_id}'")
        del self.docs[doc_id]

    # ---- serialization ----------------------------------------------------
    def _open_suggestion_ids(self) -> list[str]:
        return sorted(s.id for m in self.modules.values() for s in m.suggestions if _OPEN(s))

    def to_dict(self) -> dict:
        orphans = set(self.orphans())
        rev = self._superseded_by()
        metrics = self.compute_metrics()
        modules = []
        for m in self.modules.values():
            d = asdict(m)
            d["orphan"] = m.id in orphans
            d["supersededBy"] = rev.get(m.id, [])
            d["metrics"] = metrics[m.id]
            # Back-compat convenience for any consumer still reading a single
            # suggestion: surface the first OPEN candidate (or None).
            first_open = next((asdict(s) for s in m.suggestions if _OPEN(s)), None)
            d["suggestion"] = first_open
            modules.append(d)
        # Bake each doc's resolved scope (parallel to embedding compute_metrics per
        # module) so /api/model, get_model, and the inline studio all get it for free.
        res = resolve_all(list(self.docs.values()), self)
        docs = []
        for doc in self.docs.values():
            dd = asdict(doc)
            r = res["byDoc"][doc.id]
            dd["resolvedModuleIds"] = r.ids
            dd["drift"] = r.missing
            dd["scopeLabel"] = r.label
            docs.append(dd)
        return {
            "repo": self.repo,
            "modules": modules,
            "plans": [asdict(p) for p in self.plans.values()],
            "docs": docs,
            "docMembership": res["membership"].as_dict(),
            "worktrees": [asdict(w) for w in self.worktrees.values()],
            "board": self.board(),
            "orphans": sorted(orphans),
            "openSuggestions": self._open_suggestion_ids(),
            "anchors": self.anchors,
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
        metrics = self.compute_metrics()
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
                "metrics": metrics[m.id],
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
            "docs": [{"id": d.id, "type": d.type, "title": d.title,
                      "status": d.status, "scopeKind": d.scope.kind}
                     for d in self.docs.values()],
            "worktrees": [{"id": w.id, "branch": w.branch, "status": w.status,
                           "stepId": w.stepId, "agent": w.agent}
                          for w in self.worktrees.values()],
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
        docs: list[Doc] = []
        for entry in raw.get("docs", []):               # absent on pre-docs maps -> []
            entry = dict(entry)
            for computed in ("resolvedModuleIds", "drift", "scopeLabel", "supersededBy"):
                entry.pop(computed, None)
            scope = Scope.from_dict(entry.pop("scope", None))
            doc = Doc(**_only_known(Doc, entry))
            doc.scope = scope
            docs.append(doc)
        worktrees: list[Worktree] = []
        for entry in raw.get("worktrees", []):          # absent on pre-worktree maps -> []
            worktrees.append(Worktree(**_only_known(Worktree, entry)))
        model = cls(raw["repo"], modules, plans, docs, worktrees)
        # tolerant reader: non-dict anchor entries are dropped, the rest survive
        model.anchors = [a for a in raw.get("anchors", []) if isinstance(a, dict)]
        return model
