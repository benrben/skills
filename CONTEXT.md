# Fathom

The Fathom Claude Code plugin: a suite of skills that model, design, and deepen codebase architecture around a shared, persistent arch-map. This file names the concepts the suite itself is built from (the architecture vocabulary — module, depth, seam — lives in [skills/fathom/LANGUAGE.md](skills/fathom/LANGUAGE.md)).

## Language

**Skill**:
A prompt module discovered by Claude Code via `skills/<name>/SKILL.md`; its interface is the trigger description, its implementation is the process body.
_Avoid_: command, prompt, agent

**Suite**:
The six Fathom skills (map, understand, deepen, plan, code, adr-writer) acting on one shared spine, each owning a distinct slice.
_Avoid_: toolkit, framework

**Spine**:
The arch-map MCP server — the shared, file-backed model of named maps that every skill reads and writes through MCP tools.
_Avoid_: backend, database, state server

**Map**:
One named, persistent architecture model on the spine (one JSON file per project under `maps/`), addressed by its `map` id in every tool call.
_Avoid_: graph, project file

**Slice**:
The portion of the spine a single skill is allowed to write (e.g. actual-plane module facts for fathom:map, candidates for fathom:deepen, intended-plane modules and Plans for fathom:plan).
_Avoid_: scope, permission

**Substrate**:
The shared briefing docs under `skills/fathom/` (LANGUAGE, DEEPENING, formats); referenced by every skill, discovered by none — it has no SKILL.md on purpose.
_Avoid_: shared library, common docs

**Candidate**:
A proposed deepening attached to a module on the spine, owned by fathom:deepen and carried through the grilling lifecycle (open → requested → grilling → grilled → done).
_Avoid_: suggestion (the tool name, not the concept), proposal, ticket

**Grilling**:
The adversarial examination of one chosen candidate until it is accepted, deferred, or rejected.
_Avoid_: review, refinement

**Plane**:
Whether a module on the map records what exists (`actual`) or what is designed to exist (`intended`); fathom:map writes only the former, fathom:plan only the latter.
_Avoid_: layer, status

**Studio**:
The browser/MCP-App UI for a map (graph canvas, rail panels, doc browser), served by the spine over HTTP or inlined into an MCP-App host.
_Avoid_: dashboard, frontend, viewer

**Halo**:
The "changed since last scan" marker (`updated`) on a module; cleared by fathom:map once the module's record matches reality again.
_Avoid_: dirty flag

**Anchor**:
A recorded reconcile event on a map — the git HEAD sha, a timestamp, and a per-module snapshot of health/depth/coverage — owned by the reconcile ledger; the baseline that drift and history are computed against.
_Avoid_: snapshot, checkpoint, baseline
