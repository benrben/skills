# The task board & worktrees — the cycle made trackable

The Fathom suite is one engineer cycle — **map → understand → design → code**, with **review** gating. The **task board** makes that cycle *trackable*: every Plan's WorkSteps become cards on a Kanban whose **columns are the skills themselves**, and each card can be built in its own **git worktree** — an isolated branch — so several tasks (and the agents on them) run in parallel without colliding.

The board and worktrees are **not a sixth skill**. They are spine state (`Plan` / `WorkStep` / `Worktree` on the `arch-map` model) plus a studio surface, driven *by the five skills you already have*. A card flows left→right through the cycle; its **agent** (the swimlane row) and its **worktree** (the branch badge) travel with it.

## The columns are the cycle

| Column | The skill that owns it | What "the card is here" means |
|---|---|---|
| **todo** | — | sequenced by `design`, not yet started (the backlog) |
| **understand** | [`understand`](../skills/understand/SKILL.md) | being comprehended before it's touched (read-only tour scoped to the task's targets) |
| **plan** | [`design`](../skills/design/SKILL.md) | structure being decided — candidate grilled / interface designed |
| **in-progress** | [`code`](../skills/code/SKILL.md) | being built, **inside its worktree**, to the interface (the test surface) |
| **review** | [`review`](../skills/review/SKILL.md) | the worktree branch being gated against the map before it merges |
| **done** | — | merged; the worktree synced/removed |

`blocked` is **not a column** — it's an orthogonal flag (a red badge) a card carries in whatever column it sits. (Legacy maps that stored `status="blocked"` project onto the `todo` column with the flag set, so nothing migrates.)

## Cards, rows, worktrees

- **Card = a `WorkStep`.** Its `status` is the column; `priority` (low·normal·high·urgent) orders it; `targets` are the modules it builds; `interface` is the test surface; `worktree` links its isolated branch.
- **Row = an agent.** `WorkStep.agent` is a free-text handler label — a subagent type (`Explore`), a skill (`fathom:code`), a workflow agent (`workflow:build-s2`), a person, or `unassigned`. Grouping by it makes *every agent's work trackable in one place*; a live dispatch marks its card running (⚙).
- **Worktree = a task's isolated branch.** One `git worktree` per task gives its agent a private checkout so parallel builds never collide in the shared tree. `Worktree` records `branch · path · base · status (active|merged|removed)` and back-references its step.

## The worktree lifecycle (who runs each git step)

```
design ──create──▶  code ──build in it──▶  review ──diff its branch──▶  (merge)  ──▶  map ──sync──▶ done
        worktrees(create)   cwd = worktree     git diff base...branch                  worktrees(sync)
        per task            advance in-progress  advance review/done                     mark merged/removed
```

- **create** — `archmap_worktrees(map, action="create", branch=…, plan_id=…, step_id=…)` provisions `git worktree add -b <branch>` (real, guarded) and records it, linking the card. `attach` records an existing branch instead.
- **build in it** — the build agent runs with `cwd` = the worktree path; every edit lands on that branch. From the studio, the card's **▶ run** button dispatches a headless agent into the worktree.
- **diff its branch** — review reads `git diff <base>...<branch>` (and `archmap_drift(since_sha=<base>)`) against the map.
- **sync** — `archmap_worktrees(map, action="sync")` reconciles the spine against `git worktree list` (refresh HEAD, mark vanished/merged `removed`). `remove`/`prune` tidy up.

## The tool surface

- `archmap_board(map)` — the projection: `{columns, counts, lanes:[{agent, cards}], cards, worktrees}`. The read every skill uses to *see and track* the work.
- `archmap_plans(map, action="set_step_status", step_status=<column>)` — move a card across the cycle.
- `archmap_plans(map, action="set_step", priority=…, agent=…, worktree=…, blocked=…)` — assign / prioritise / block without moving columns. `add_steps` also takes `priority` / `agent` / `worktree`.
- `archmap_worktrees(map, action=list|create|remove|prune|attach|sync, …)` — manage the per-task branches.

## The studio surface

In the browser studio (and any UI-capable MCP host) the header carries a **Graph ↔ Board** toggle (`b`). The board shows the six cycle columns × agent swimlanes; **drag a card** between columns to move its stage (and onto a lane to assign its agent), set priority/block, and per card **＋ worktree** / **▶ run** (dispatch an agent into the worktree) / **✕ wt**. Live runs show ⚙ on the card for every open tab. It is the same spine the terminal agent drives — a move in the browser shows up for the agent and vice-versa.

## Guards

Real `git worktree` work and the in-worktree agent dispatch reuse the `/api/dispatch` philosophy: a same-origin check on the loopback server, and an opt-in env flag.

- `ARCH_MAP_ALLOW_WORKTREE` — real provisioning is **ON** by default; set `0`/`false`/`no`/`off` and `create`/`remove` degrade to a copy-paste `git worktree` **command** (the spine record is still made, so the board stays accurate).
- `ARCH_MAP_WORKTREE_DIR` — where checkouts live; defaults to a `.fathom-worktrees/` sibling of the repo (kept out of the main working tree).
