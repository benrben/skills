# Decision Framework: Tool vs Resource vs Prompt

Deep reference for classifying capabilities. Read this when a classification is genuinely unclear, or when reviewing a server design for correctness. The SKILL.md has the one-line rule; this file has the reasoning, the edge cases, worked examples, and the per-capability review checklist.

## Table of contents
- The control axis (the actual rule)
- Tool: full criteria and when reads are tools
- Resource: full criteria, direct vs template
- Prompt: full criteria
- The tension: same data, two homes
- Worked examples (classify-these)
- The "make everything a tool" anti-pattern
- Per-capability review checklist

## The control axis (the actual rule)

MCP's three primitives are distinguished by **who controls invocation**, not by what they technically do:

- **Tools are model-controlled.** The LLM decides, at runtime, whether and when to call them, based on the conversation. The host typically requires user consent before execution — which is exactly why action-bearing operations belong here.
- **Resources are application-controlled.** The host application decides how and whether to retrieve them and feed them to the model. It might inject them automatically, let the user browse and select, search them with embeddings, or pass raw bytes. The protocol mandates no specific UI.
- **Prompts are user-controlled.** The user explicitly invokes them — as a slash command, a button, a command-palette entry. They are never auto-triggered by the model.

So the decision procedure is one question: **who should decide when this runs — the model, the app, or the user?** The answer names the primitive. Everything below is elaboration.

## Tool: full criteria

Make it a **tool** when either is true:

1. **It performs an action or has side effects** — it writes, sends, books, creates, updates, deletes, or otherwise changes state. These need the human-oversight checkpoint the protocol puts around tool calls.
2. **The model must actively decide to invoke it as a reasoning step** — even if it only reads. Live/dynamic data the model fetches mid-thought (`weather_current(location)`, `search_flights(origin, dest, date)`, `lookup_order(id)`) is a tool because the *model*, not the app, decides it's relevant right now.

Technical shape: a tool is a JSON-Schema-defined function with typed inputs and (optionally) typed structured outputs. Discovery via `tools/list`, execution via `tools/call`.

**Why "read vs. write" is the wrong axis.** The official travel example exposes `searchFlights()` and `checkWeather()` as tools even though they only read — because the model must deliberately call them while reasoning about a trip. The right axis is *deliberate model invocation*. If the model should actively choose to run it, it's a tool regardless of whether it mutates anything.

## Resource: full criteria

Make it a **resource** when all of these hold:

- The data is **read-only reference context** (a schema, documentation, a knowledge base, file contents, past records, configuration).
- It's reasonable for the **host application** — not the model — to decide when to pull it in.
- You benefit from **URI-addressable, browsable, possibly subscribable** data.

Technical shape: each resource has a unique URI and a declared MIME type. Operations: `resources/list`, `resources/templates/list`, `resources/read`, `resources/subscribe`.

**Direct vs. template:**
- **Direct resource** — a fixed URI pointing at specific data: `calendar://events/2024`, `config://app`, `orders://policy/returns`.
- **Resource template** — a parameterized URI: `users://{user_id}/profile`, `travel://activities/{city}/{category}`. Templates carry metadata (title, description, expected MIME type) so they're self-documenting, and they support **parameter completion** (typing "Par" suggests "Paris"). Use a template whenever the resource is "the same kind of data, addressed by a key."

A resource template is *not* a tool just because it has parameters. The distinction is still control: a template is data the app addresses by filling in a key; a tool is an operation the model decides to invoke. `users://{user_id}/profile` (resource template) = "the app can look up any user's profile as context." `refresh_user_cache(user_id)` (tool) = "the model decides to trigger a refresh."

## Prompt: full criteria

Make it a **prompt** when all of these hold:

- There's a **repeatable, multi-step task** users will want to invoke by name.
- You want to **demonstrate the intended happy path** of combining your server's tools and resources in the right order.
- The trigger should be an **explicit user action**, not an autonomous model decision.

Technical shape: a parameterized message template. Operations: `prompts/list`, `prompts/get`. It surfaces in clients as a slash command (`/plan-vacation`), button, or menu entry.

A prompt is the *orchestration layer* you hand the user. The canonical `plan-vacation` prompt takes `destination`, `duration`, `budget`, `interests` and drives a consistent flow: read the right resources (calendar, preferences, past trips) → call the right tools in the right order (search flights → check weather → book → create event → email). It turns "the user types a vague request and hopes" into "the user invokes a tested workflow."

## The tension: same data, two homes

The hardest real decisions are cases where the *same underlying data* could be a tool or a resource. Resolve them this way:

| Prefer **Resource** when… | Prefer **Tool** when… |
|---|---|
| it's stable context the app should freely inject or let the user browse | the model must deliberately request it as a reasoning step |
| fetching is cheap and side-effect-free | fetching has cost, rate limits, or side effects worth gating behind model-decision + consent |
| the value is "background knowledge" | the value is "a live answer the model went and got" |

Examples of the same data both ways:
- **DB schema:** `db://schema` (resource — stable context) vs. `get_schema()` (tool — model deliberately requests, or it's expensive to compute).
- **User profile:** `users://{id}/profile` (resource template — app looks it up as context) vs. `fetch_user(id)` (tool — model decides to go get it).
- **Docs:** `docs://api/{page}` (resource — browsable reference) vs. `search_docs(query)` (tool — model-driven search, which is genuinely an action).

Note that **search is almost always a tool**, even though it reads, because it's a model-driven operation with a query the model composes.

## Worked examples (classify these)

For each, the control question and the answer:

1. **"Send a Slack message."** Model decides + side effect → **Tool** (`slack_send_message`).
2. **"The org's brand guidelines."** Stable reference the app injects → **Resource** (`brand://guidelines`).
3. **"What's the weather in Paris right now?"** Model deliberately fetches live data → **Tool** (`weather_current`).
4. **"Draft a quarterly business review."** User invokes a named multi-step workflow → **Prompt** (`/qbr-draft`).
5. **"Look up customer #4821's account."** Could go either way: as browsable context → **Resource template** (`customers://{id}`); as a model-driven fetch → **Tool** (`get_customer`). Pick by whether the host injects it or the model goes and gets it.
6. **"The current returns policy."** Stable text the app injects → **Resource**.
7. **"Find orders matching a query."** Model-composed search → **Tool** (`search_orders`).
8. **"Cancel an order."** Side effect → **Tool** (`cancel_order`), with `destructiveHint=True`.
9. **"Onboard a new hire" (collect info, create accounts, schedule training).** User-invoked orchestration → **Prompt** that drives the underlying tools/resources.
10. **"The JSON schema clients should validate against."** Stable context → **Resource** (`schema://orders`).

## The "make everything a tool" anti-pattern

Because tools are the only primitive every host supports, there's gravity toward making everything a tool. Resist it for design clarity — and bridge for compatibility instead:

- Keep the clean three-way split in your design. It makes the server self-documenting and matches how rich clients present capabilities (resources to browse, prompts as commands, tools as actions).
- If your actual clients are tools-only, don't collapse resources into tools by hand. Add the **`ResourcesAsTools`** and **`PromptsAsTools`** transforms (see `architecture.md`), which auto-generate `list_resources`/`read_resource`/`list_prompts`/`get_prompt` tools. You keep the clean model *and* work with limited clients.
- The exception: if something is *genuinely* a model-driven action, it was a tool all along — don't force it into a resource for purity.

## Per-capability review checklist

Run this for every capability before shipping.

**Step 1 — Control owner.** Model → Tool. App → Resource. User → Prompt. If you can't answer cleanly, you haven't defined the capability well yet.

**Step 2 — If a Tool:**
- [ ] Outcome-oriented: one call accomplishes one goal; multi-step work is done in code, not by chaining.
- [ ] Flat, typed, constrained arguments (`Literal`/enums, `Field` constraints); required vs. optional explicit via defaults.
- [ ] Service-prefixed, action-oriented `name`; human-readable `title`.
- [ ] Docstring instructs the model: when to use, what it returns, how to format.
- [ ] Actionable error messages (the model can self-correct); internals masked in production.
- [ ] Accurate `readOnlyHint`/`destructiveHint`/`idempotentHint`/`openWorldHint`.
- [ ] Pagination (`limit` + `has_more`/`next_offset`/`total_count`) if it returns lists.
- [ ] `timeout=` if it can hang.
- [ ] Structured output (annotated return type) if consumed programmatically.
- [ ] Credentials/IDs injected via `Depends()`, not model-visible parameters.

**Step 3 — If a Resource:**
- [ ] Genuinely read-only context (no side effects).
- [ ] Clear URI scheme and correct MIME type.
- [ ] A template (parameters + completion) if it's "same data, addressed by a key."
- [ ] Something the app should browse/inject, not something the model must deliberately fetch (else it's a tool).
- [ ] Reachable by your clients — add `ResourcesAsTools` if they're tools-only.

**Step 4 — If a Prompt:**
- [ ] Repeatable, user-invoked, multi-step workflow.
- [ ] Names and orders the tools/resources it orchestrates.
- [ ] Well-described parameters.
- [ ] Returns `Message` objects or plain strings (not raw dicts — v3 requirement).

**Step 5 — Server level:**
- [ ] One server, one job.
- [ ] 5–15 curated tools; unused ones deleted.
- [ ] Personas split via tags/visibility.
- [ ] `list_changed` notifications wired for any dynamic component sets.
- [ ] Right transport: STDIO local / Streamable HTTP remote.

**Step 6 — Security.** `security.md` is the source of truth — run its secure-by-default checklist rather than relying on a summary here. The one-line reminder: no token passthrough, least-privilege scopes, per-client consent (CIMD), SSRF blocked, CSPRNG session IDs bound to user, per-component `auth` (STDIO bypasses it), never elicit secrets.

**Step 7 — Observability & tests:** in-memory `Client` tests (sub-second); OpenTelemetry tracing; masked errors; rate limiting; `--reload` dev loop.
