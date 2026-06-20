# Doc Types

The arch-map spine carries **docs** alongside the module graph. Docs are **spine-only** — there is no `docs/` file mirror. Every doc is one `archmap_docs` record: a `type`, a `title`, a `summary`, a markdown `body`, a `status`, a `scope` (which modules it covers), `tags`, `supersedes`, and `adrRef` (the id of an `adr` doc this records, when relevant). The vocabulary in [LANGUAGE.md](LANGUAGE.md) governs the prose — **module / interface / depth / seam / adapter / leverage / locality**, never "component," "service," "API," or "boundary."

Docs are scoped, not free-floating: a `scope` of `system` covers the whole map, `domain` every module in a domain, `explicit` a pinned id list, `query` a live predicate. A scoped doc shows on its modules' nodes in the studio, so it travels with the structure it describes.

## The eleven types, by where they sit in the cycle

| Type | Holds | Writer | Lifecycle (`status`) |
|------|-------|--------|----------------------|
| **glossary** | the project's domain vocabulary / terms (the canonical home; supersedes any CONTEXT.md file) | `map` | living |
| **note** | a free observation worth keeping | `map` | living |
| **risk** | a hazard + its mitigation + what would make it bite | `map` · `review` | `open → mitigated → closed` |
| **runbook** | how to build / run / test / deploy / operate a module or the system | `map` · `code` | living |
| **postmortem** | what broke, the root cause, the durable lesson | `map` · `review` | living |
| **diagram** | a **Mermaid** picture of structure or flow (sequence, data-flow, state machine, topology) the node-graph can't show | `map` (actual) · `design` (intended) | `draft → active → superseded` |
| **rfc** | a proposal still **open** ("should we?") | `design` | `open → (accepted ⇒ becomes an adr) | rejected` |
| **adr** | a decision **made**: the choice, the rationale, the rejected alternative | `design` (decides) · `map` (discovers one in the code) | `proposed → accepted → superseded` |
| **spec** | a module's interface contract: types, invariants, errors, ordering, config, acceptance | `design` | `draft → active → superseded` |
| **rule** | a standing convention the project follows | `map` · `design` | `active → retired` |
| **ceiling** | a deliberate simplification + the exact condition under which it should be deepened | `code` · `design` | `active → (trigger met ⇒ a design candidate)` |

**Who reads what:** `understand` reads all of them on a tour; `code` reads `spec`/`adr`/`glossary`/`rule`/`ceiling` before building; `review` reads `adr`/`spec`/`risk` for the modules a diff touches; `design` reads `adr`/`rule` as constraints.

`map` is the doc **registrar** — it keeps the set complete and accurate, and owns the knowledge/visual types. `design` writes the decision and contract types for decisions it makes. `code` writes `ceiling` (and an `adr` for a load-bearing deviation). `review` may record a `risk` or `postmortem`. The body format is markdown for every type **except `diagram`, whose body is Mermaid source** (the studio renders it; the raw source is the fallback).

## The decision lifecycle: rfc → adr

A contested decision starts as an **rfc** (the open question). `design` grills it; when it lands, the rfc is superseded by an **adr** (the decision). A decision already baked into the code is recorded straight as an **adr** by `map`. Point the modules a decision affects at the adr via their `adrRef` (the adr's doc id).

## The three gates — when to write an `adr`

Write an `adr` only when **all three** hold. Otherwise a plain `note` (or nothing) is right.

1. **Hard to reverse** — the cost of changing your mind later is meaningful. Easy to reverse → skip it; you'll just reverse it.
2. **Surprising without context** — a future reader will look at the code and wonder "why on earth did they do it this way?" Not surprising → nobody will wonder.
3. **The result of a real trade-off** — there were genuine alternatives and you picked one for specific reasons. No real alternative → nothing to record beyond "we did the obvious thing."

### What qualifies

- **Architectural shape** — "the write model is event-sourced, the read model is projected into Postgres."
- **Integration patterns between contexts** — "Ordering and Billing communicate via domain events, not synchronous HTTP."
- **Technology choices that carry lock-in** — database, message bus, auth provider, deployment target. Not every library, just the ones that would take a quarter to swap out.
- **Seam and scope decisions** — "Customer data is owned by the Customer context; other contexts reference it by id only." The explicit no-s are as valuable as the yes-s.
- **Deliberate deviations from the obvious path** — "manual SQL instead of an ORM because X," so the next engineer doesn't "fix" something deliberate.
- **Constraints not visible in the code** — "response times must be under 200ms because of the partner contract."
- **Rejected alternatives when the rejection is non-obvious** — record it, or someone proposes it again in six months. This is the common shape of a rejected deepening candidate.

### The `adr` body

Deliberately minimal — the value is recording *that* a decision was made and *why*, not section-filling:

```md
{1-3 sentences: the context, what was decided, and why. Name the alternative
that was rejected and the specific reason it lost.}
```

Add `status` / a "Consequences" line / "Considered Options" only when they earn their place; most adr docs need none.

## Writing a doc

```
archmap_docs(map, action="add", doc_id="<kebab id>", type="<type>",
             title="...", summary="...", body="...",
             scope_kind="domain", scope_domain="orders")   # or system / explicit + scope_ids / query
```

Refresh in place with `action="update"`; link a replacement with `supersedes=[old_id]`. Keep scopes tight so each doc rides with the modules it describes.
