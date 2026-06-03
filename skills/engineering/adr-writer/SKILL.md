---
name: adr-writer
description: Author an Architecture Decision Record under docs/adr/NNNN-slug.md — pick the next number, apply the three-gate test (hard to reverse, surprising without context, the result of a real trade-off), and write a tight one-paragraph ADR. The sole writer of docs/adr/. Use when recording why an architectural choice was made or a load-bearing alternative rejected, or when a Fathom skill (fathom:deepen, fathom:plan, fathom:code) offers an ADR and hands off. Do NOT use for deciding WHETHER to deepen (that is fathom:deepen), designing intended structure (fathom:plan), editing source (fathom:code), or general design notes that fail the three-gate test — those are not ADRs.
---

# ADR Writer

Record *that* a decision was made and *why* — not fill out a template. An ADR is the durable answer to "why on earth did they do it this way?" that a future reader would otherwise have to reverse-engineer from the code. The value is in capturing the decision and its rationale; an ADR can be a single paragraph.

This skill is the **sole writer of `docs/adr/`**. Sibling Fathom skills never write ADR files themselves — they *offer* an ADR and hand the decision off here. After writing, when invoked from a Fathom skill, this skill **links the ADR back into the arch-map spine** so the map and the ADR cross-reference each other and a future architecture review sees *why* a candidate was rejected before re-suggesting it.

## When this skill runs

Two entry points:

1. **Direct.** The user asks to record an architectural decision ("write an ADR for this", "document why we chose X over Y").
2. **Hand-off from a Fathom skill.** `fathom:deepen` rejects a candidate with a load-bearing reason, `fathom:plan` settles a design-it-twice trade-off, or `fathom:code` deviates from a planned interface for a real reason — each *offers* an ADR and, if accepted, hands off to this skill with the context (and, for the Fathom skills, the `map` id and the `suggestion_id` or plan id to link back).

In both cases, apply the three-gate test first. If it fails, say so and write nothing.

## Process

### 1. Apply the three-gate test

Only write an ADR when **all three** hold:

1. **Hard to reverse** — the cost of changing your mind later is meaningful. If a decision is easy to reverse, skip it; you'll just reverse it.
2. **Surprising without context** — a future reader will look at the code and wonder "why on earth did they do it this way?". If it isn't surprising, nobody will wonder.
3. **The result of a real trade-off** — there were genuine alternatives and you picked one for specific reasons. If there was no real alternative, there is nothing to record beyond "we did the obvious thing."

What qualifies (see [./ADR-FORMAT.md](./ADR-FORMAT.md) for the full lists):

- **Architectural shape** — "the write model is event-sourced, the read model is projected into Postgres."
- **Integration patterns between contexts** — "Ordering and Billing communicate via domain events, not synchronous HTTP."
- **Technology choices that carry lock-in** — database, message bus, auth provider, deployment target. Not every library, just the ones that would take a quarter to swap out.
- **Seam and scope decisions** — "Customer data is owned by the Customer context; other contexts reference it by id only." The explicit no-s are as valuable as the yes-s.
- **Deliberate deviations from the obvious path** — "manual SQL instead of an ORM because X." Anything where a reasonable reader would assume the opposite, so the next engineer doesn't "fix" something deliberate.
- **Constraints not visible in the code** — "response times must be under 200ms because of the partner contract."
- **Rejected alternatives when the rejection is non-obvious** — if you considered the alternative and rejected it for subtle reasons, record it, or someone will propose it again in six months. This is the common shape of a Fathom hand-off: a deepening candidate or design alternative that was rejected for a load-bearing reason.

If the decision fails any gate, do not write a file. Tell the caller plainly why (e.g. "this is easy to reverse, so an ADR would just be noise") and stop. When the caller is a Fathom skill, still record the rejection reason on the spine (step 4) — the map should remember the *why* even when no ADR is warranted.

When speaking about architecture in the ADR body, use the [../deepen/LANGUAGE.md](../deepen/LANGUAGE.md) vocabulary — **module / interface / depth / seam / adapter / leverage / locality**, the **deletion test**, *the interface is the test surface*, *one adapter is a hypothetical seam, two is a real one*. Never "component", "service", "API", or "boundary".

### 2. Pick the next number

Scan `docs/adr/` for the highest existing `NNNN` and increment by one. Create the `docs/adr/` directory lazily — only when this first ADR needs it.

```
ls docs/adr/ 2>/dev/null    # find the highest NNNN-*.md; new file is that + 1
mkdir -p docs/adr           # lazily, only if it doesn't exist
```

The file is `docs/adr/NNNN-slug.md` — four-digit zero-padded number, a short kebab-case slug from the title (e.g. `docs/adr/0007-keep-ordering-and-billing-decoupled.md`). Hold onto the exact path; step 4 references it back into the spine.

### 3. Write a tight ADR

Follow [./ADR-FORMAT.md](./ADR-FORMAT.md). The template is deliberately minimal:

```md
# {Short title of the decision}

{1-3 sentences: the context, what was decided, and why. Name the alternative
that was rejected and the specific reason it lost.}
```

That's the whole thing. The value is in recording *that* a decision was made and *why* — not in section-filling.

**Optional sections — include only when they add genuine value** (most ADRs need none):

- **Status** frontmatter (`proposed | accepted | deprecated | superseded by ADR-NNNN`) — when decisions get revisited.
- **Considered Options** — only when the rejected alternatives are worth remembering in detail.
- **Consequences** — only when non-obvious downstream effects need calling out.

Keep it readable cold: a future explorer should grasp the surprise and the trade-off in one pass. For a rejected deepening, name what made it tempting and the load-bearing reason it was still wrong — e.g. *"a port at the inventory seam would deepen order-service for testing, but the vendor is true-external with one integration and a contract-test sandbox already covers it, so a second adapter would be pure indirection (one adapter is a hypothetical seam). Revisit only if a second provider is onboarded."*

### 4. Link the ADR back into the spine (Fathom hand-offs only)

When invoked from a Fathom skill, close the loop so the map and the ADR cross-reference each other. The caller supplies the `map` id and the thing the ADR is about. Bootstrap the map id the same way the Fathom skills do — `list_maps()` to find it if you weren't handed it — and thread it through every call.

- **From `fathom:deepen` (a rejected candidate).** Record the verdict on the candidate's suggestion with the ADR path in the note:

  ```
  decide(map, suggestion_id, "rejected", note="<one-line reason> — see docs/adr/NNNN-slug.md")
  ```

  Use `decide`, **never `resolve`**. `decide(... "rejected" ...)` keeps the verdict and the note on the candidate — the durable "don't re-suggest this" record a future scan sees. `resolve(map, suggestion_id)` clears the candidate and discards the reason, which would re-open the door to re-suggesting the same deepening. (`decision` is exactly `"accepted"` | `"deferred"` | `"rejected"`, or `""` to re-open.) If the rejection came out of a grilling loop, the closing call carries the ADR directly: `grilling_done(map, suggestion_id, "rejected", note=reason, adr="docs/adr/NNNN-slug.md")`.

- **From `fathom:plan` (a design-it-twice trade-off).** Reference the ADR path from the plan's intent so the chosen design records why the rejected alternative lost: `update_plan(map, plan_id, intent="… chosen over <alt>; see docs/adr/NNNN-slug.md")` (or carry the reference in the plan when it is created). For a work step that deviates from the obvious build, note the ADR on that step.

- **From `fathom:code` (a deliberate deviation while building).** When the implementation departs from a planned interface for a recorded reason, note the ADR path on the relevant work step (`set_step_status` / the step's `note`) or on the module's interface text so the deviation isn't later "fixed."

arch-map has no ADR awareness of its own — the link is free text in the note / intent, so always include the full `docs/adr/NNNN-slug.md` path verbatim. The candidate keeps a rejected verdict badge that points a future explorer at the rationale.

### 5. Confirm and hand back

Report the exact path of the ADR you wrote (`docs/adr/NNNN-slug.md`) and, for a Fathom hand-off, confirm the spine link is recorded. Hand control back to the calling skill; do not continue grilling, planning, or editing source — those are the siblings' jobs.

## Boundaries

- **This skill writes `docs/adr/` and nothing else.** It does not edit source (that is `fathom:code`), decide *whether* to deepen (`fathom:deepen`), design intended structure (`fathom:plan`), or build/keep-honest the actual-plane map (`fathom:map`). It picks a number, applies the three-gate test, writes the ADR, and links it back into the spine.
- **The Fathom siblings never write ADR files** — they offer an ADR and hand off here. If you find yourself drafting an ADR from inside another skill, stop and route through this one so numbering stays sequential and `docs/adr/` has a single writer.
- **No ADR for a decision that fails a gate.** Easy-to-reverse, unsurprising, or no-real-alternative decisions are noise; record the reason on the spine if a Fathom skill asked, but write no file.
