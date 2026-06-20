# Fathom

> **Dev/legacy reference only — not loaded by the installed plugin.** Claude Code does not read root context files; this lives here for contributors. The canonical architecture vocabulary is [fathom/LANGUAGE.md](fathom/LANGUAGE.md).

The Fathom Claude Code plugin: a suite of skills that model, design, and deepen codebase architecture around a shared, persistent arch-map. This file names the concepts the suite itself is built from (the architecture vocabulary — module, depth, seam — lives in [fathom/LANGUAGE.md](fathom/LANGUAGE.md)).

## Language

**Skill**:
A prompt module discovered by Claude Code via `skills/<name>/SKILL.md`; its interface is the trigger description, its implementation is the process body.
_Avoid_: command, prompt, agent

**Suite**:
The five Fathom skills (map, understand, design, code, review) acting on one shared spine, each owning a distinct slice.
_Avoid_: toolkit, framework

**Spine**:
The arch-map MCP server — the shared, file-backed model of named maps that every skill reads and writes through MCP tools.
_Avoid_: backend, database, state server

**Map**:
One named, persistent architecture model on the spine (one JSON file per project under `maps/`), addressed by its `map` id in every tool call.
_Avoid_: graph, project file

**Slice**:
The portion of the spine a single skill is allowed to write (e.g. actual-plane module facts for fathom:map, candidates plus intended-plane modules and Plans for fathom:design).
_Avoid_: scope, permission

**Substrate**:
The shared briefing docs under `fathom/` (LANGUAGE, DEEPENING, formats); referenced by every skill, discovered by none — it has no SKILL.md on purpose.
_Avoid_: shared library, common docs

**Candidate**:
A proposed deepening attached to a module on the spine, owned by fathom:design and carried through the grilling lifecycle (open → requested → grilling → grilled → done).
_Avoid_: suggestion (the tool name, not the concept), proposal, ticket

**Grilling**:
The adversarial examination of one chosen candidate until it is accepted, deferred, or rejected.
_Avoid_: review, refinement

**Plane**:
Whether a module on the map records what exists (`actual`) or what is designed to exist (`intended`); fathom:map writes only the former, fathom:design only the latter.
_Avoid_: layer, status

**Studio**:
The browser/MCP-App UI for a map (graph canvas, rail panels, doc browser, and the task board), served by the spine over HTTP or inlined into an MCP-App host.
_Avoid_: dashboard, frontend, viewer

**Task board** (Board):
The skill-cycle Kanban projection of a map's WorkSteps — columns are the cycle (todo · understand · plan · in-progress · review · done, each owned by a skill), rows are agents, cards are tasks. Spine state (`model.board`) rendered in the studio; swaps with the graph. See [fathom/BOARD.md](fathom/BOARD.md).
_Avoid_: kanban (the shape, not the name), tracker, backlog tool

**Task**:
A WorkStep seen as a board card — it carries a cycle column (`status`), a `priority`, an assigned `agent` (its swimlane), and its own `worktree`; sequenced by fathom:design, built by fathom:code, gated by fathom:review.
_Avoid_: ticket, issue, story

**Worktree**:
A task's isolated git branch + checkout (one `git worktree` per WorkStep) where an agent builds it in parallel without colliding in the shared tree; recorded on the spine, provisioned for real by `worktrees.py`, surfaced on the board.
_Avoid_: branch (one part of it), sandbox, clone

**Halo**:
The "changed since last scan" marker (`updated`) on a module; cleared by fathom:map once the module's record matches reality again.
_Avoid_: dirty flag

**Anchor**:
A recorded reconcile event on a map — the git HEAD sha, a timestamp, and a per-module snapshot of health/depth/coverage — owned by the reconcile ledger; the baseline that drift and history are computed against.
_Avoid_: snapshot, checkpoint, baseline
