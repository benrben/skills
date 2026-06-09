---
name: mcp-server-design
description: Design, build, review, and improve Model Context Protocol (MCP) servers and the tools they expose to AI agents. Use this skill whenever the user is creating an MCP server, defining or naming MCP tools, structuring tool arguments or return values, deciding which tools/resources/prompts to expose, or auditing, refactoring, or improving an existing MCP server — even if they only say things like "my MCP server feels clunky", "wrap this API for an agent", "the agent keeps calling the wrong tool", "add a tool to my server", or just mention MCP, FastMCP, or agent tool design without explicitly asking for a "redesign". Applies to any language or SDK (Python, TypeScript, FastMCP, the official MCP SDKs, etc.).
---

# Building MCP Servers That Agents Can Actually Use

## The one idea that changes everything

**An MCP server is a user interface for an AI agent — not a thin wrapper around your REST API.**

This is the single most common mistake: developers expose their existing endpoints 1:1 as MCP tools and assume that because the model is "smart," it can orchestrate them like a human developer would. It can't, not cheaply. The protocol works fine; most servers don't, because they were designed for the wrong user.

The user of your MCP server is a non-human agent operating under a tight context budget. Every tool description, every argument, every byte of every response, and every error message competes for space in that budget and influences whether the agent picks the right tool and uses it correctly. Design the server the way a good product designer designs a UI: curate the experience for the specific user.

Keep this comparison in mind — it explains *why* the principles below exist:

| Property | A human developer (REST user) | An AI agent (MCP user) |
| --- | --- | --- |
| Discovery | Cheap — reads the docs once | Expensive — the schema is re-read every request |
| Composition | Mixes and matches small endpoints freely | Each extra tool call is a slow round-trip with state kept in context |
| Flexibility | More options is more power | More options is more chances to hallucinate |

REST principles (composable, discoverable, flexible, stable) are right for human developers and wrong for agents. Same product thinking, different user.

## What MCP actually is

MCP standardizes three primitives that connect an LLM to outside systems:

- **Tools** — functions the agent can call (`slack_send_message`, `linear_list_issues`).
- **Resources** — data the agent can read (files, records).
- **Prompts** — pre-built workflows a user or agent can invoke.

Build the server once; any MCP-compatible agent can use it. Most of the design effort goes into **tools**, so most of this skill is about tools.

## What MCP is NOT

- **Not a 1:1 REST wrapper.** A good REST API is not a good MCP server.
- **Not a data-dump service.** Returning large raw payloads bloats the agent's context and degrades its reasoning. Curate what comes back.

## How to use this skill

Figure out which mode the user is in and go there. The six principles apply in all three.

1. **Designing a new server** — they're starting fresh or sketching the tool surface. → Read "The six principles," then follow "Designing a new server."
2. **Building / implementing** — they're writing tools now. → Apply "The six principles" as you write; see `references/examples.md` for before/after patterns to imitate.
3. **Reviewing / improving an existing server** — they have a server that's clunky, the agent misbehaves, or they want a refactor. → Walk `references/design-checklist.md` against their server and report findings.

If the user's intent is ambiguous (e.g. "help me with my MCP server"), ask one short question to find out which mode they're in before diving in. Don't over-interrogate — if they've given you an API, a tool list, or code, you usually have enough to start.

---

## The six principles

Each principle below has the trap to avoid, the fix, and *why* it matters for an agent. Internalize the "why" — it lets you apply these to situations the examples don't cover.

### 1. Outcomes, not operations

**Trap:** Converting REST endpoints 1:1 into tools, forcing the agent to orchestrate.
**Fix:** Design each tool around a goal the user/agent wants to achieve, and do the orchestration in your code.

Don't ship `get_user_by_email()` + `list_orders(user_id)` + `get_order_status(order_id)` and make the agent chain them across three round-trips, holding every intermediate result in context. Ship one `track_latest_order(email)` that calls all three internally and returns "Order #12345 shipped via FedEx, arriving Thursday." Same outcome, one call, no orchestration burden on the model.

*Why:* every round-trip is slow and consumes context; orchestration logic belongs in deterministic code, not in the LLM's working memory.

### 2. Flatten your arguments

**Trap:** Nested dictionaries or free-form config objects as arguments.
**Fix:** Top-level primitives and constrained types, with sensible defaults.

| ❌ Bad | ✅ Good |
| --- | --- |
| `search_orders(filters: dict)` | `search_orders(email: str, status: Literal["pending","shipped","delivered"] = "pending", limit: int = 10)` |
| Agent guesses the structure, hallucinates keys, misses required fields | Clear and typed; `Literal`/enum constrains choices; defaults remove decisions |

*Why:* an agent fills arguments from a schema. Flat, typed, constrained arguments are hard to get wrong; nested blobs invite invented keys and malformed calls. Every default you provide is one fewer decision the model can botch.

### 3. Instructions are context

**Trap:** Empty docstrings and generic, exception-style error messages.
**Fix:** Treat every string the agent sees as part of its context.

Write tool descriptions (docstrings) that state:
- **When to use it** — "Use when the user asks about order status."
- **How to format arguments** — "Email must be lowercase."
- **What comes back** — "Returns the order ID and current status."

And make **errors actionable**. Don't throw a raw exception. Return a helpful observation the agent can recover from: *"User not found. Try searching by email address instead."* The agent reads the error as an observation and self-corrects on the next turn.

*Why:* the agent has no out-of-band docs. The docstring *is* the manual, and the error message *is* the next instruction.

### 4. Curate ruthlessly

**Trap:** Exposing everything the API can do and returning everything it returns.
**Fix:** Design for discovery, not exhaustive coverage.

- Aim for **5–15 tools per server**.
- **One server, one job.**
- **Delete unused tools.**
- **Split by persona** (e.g. an admin server vs. a user server) instead of one bloated surface.
- Trim responses to the fields the agent needs — no data dumps.

*Why:* every tool and every field competes in the context window. A lean, well-scoped surface lets the agent find the right tool fast and get an actionable answer.

### 5. Name tools for discovery

**Trap:** Generic names like `create_issue` or `send_message`.
**Fix:** Service-prefixed, action-oriented names: `{service}_{action}_{resource}`.

Examples: `slack_send_message`, `linear_list_issues`, `sentry_get_error_details`. Your server runs alongside others; if GitHub and Jira both expose `create_issue`, the agent guesses. (Some clients auto-prefix with the server name — but don't rely on it; name defensively.)

*Why:* the name is the agent's first and cheapest discovery signal. Specific names disambiguate; generic names collide.

### 6. Paginate large results

**Trap:** Returning hundreds of records in one shot.
**Fix:** Paginate with metadata.

- Respect a `limit` parameter (default ~20–50).
- Return `has_more`, `next_offset`, and `total_count`.
- Never load all results into memory.

*Why:* large result sets blow the context budget and bury the signal. Pagination metadata lets the agent decide whether and how to fetch more.

---

## Designing a new server

Work outcome-first, top-down:

1. **Name the jobs.** List the concrete goals a user would pull this server in for ("track an order," "triage an error," "draft a reply"). These become your tools — not the underlying endpoints.
2. **Map each job to one outcome-oriented tool** (Principle 1). Push multi-step orchestration into the implementation. Resist one-tool-per-endpoint.
3. **Design each tool's signature** with flat, typed, constrained, defaulted arguments (Principle 2) and a service-prefixed name (Principle 5).
4. **Design each tool's return value**: the minimal curated fields the agent needs (Principle 4); add pagination metadata wherever a list can grow (Principle 6).
5. **Write the docstrings and error messages** as agent instructions — when to use, how to format, what to expect, how to recover (Principle 3).
6. **Count your tools.** If you're past ~15, or the server is doing more than one job, split by persona or scope (Principle 4).
7. **Decide tools vs. resources vs. prompts.** Actions the agent performs → tools. Data it reads → resources. Reusable multi-step workflows → prompts.
8. **Sanity-check against the checklist** in `references/design-checklist.md` before you call it done.

See `references/examples.md` for full before/after designs (order tracking, Gmail, and a generalized API) you can pattern-match against.

When you write or scaffold actual code, keep the principles visible in the implementation, and verify current SDK syntax against the official docs — the MCP SDKs and FastMCP evolve, so don't assume a specific decorator or API shape from memory. If exact, current SDK syntax matters for the task, search for the latest documentation rather than relying on training data.

## Reviewing / improving an existing server

When the complaint is vague ("it's clunky," "the agent keeps failing," "it's slow"), the cause is almost always one or more of the six principles being violated. To audit:

1. Get the tool list, signatures, and a sample of responses (and error behavior, if available).
2. Walk `references/design-checklist.md` item by item.
3. Report findings grouped by principle, each with the specific offending tool/argument/response and a concrete rewrite — not just "this is bad," but the exact better signature or shape.
4. Prioritize: the highest-leverage fixes are usually collapsing multi-call workflows into outcome tools (Principle 1) and trimming bloated responses (Principle 4), because both directly reclaim context and round-trips.

Common smells and their fixes:
- *Agent makes 3–4 calls for one user goal* → collapse into an outcome tool (P1).
- *Agent hallucinates argument keys or sends malformed input* → flatten and constrain arguments (P2).
- *Agent picks the wrong tool* → improve names (P5) and docstrings (P3); consider whether there are too many tools (P4).
- *Agent gets stuck after a failure* → replace exceptions with actionable error strings (P3).
- *Responses are huge / context fills up* → curate fields and paginate (P4, P6).

---

## Skills vs. MCP: complementary, not competing

You may be asked which to use. They solve different parts of the problem and pair well:

- **MCP** gives the agent a **structured interface**: typed parameters, validated inputs, typed responses. Best when a team exposes its own service for agents to call.
- **Skills** package **instructions, metadata, and resources** (loaded progressively) that teach the agent *when and how* to combine tools for a workflow. Skills can also ship scripts that run via `bash`, giving MCP-like capability without defining tool schemas — at the cost of more discovery and steps.

Neither is strictly better; it depends on the use case. In company contexts, MCP servers shine for exposing services, and skills complement them by encoding the workflows that combine those tools. Use both.

---

## Quick reference card

1. **Outcomes, not operations** — one tool per goal; orchestrate in code.
2. **Flatten arguments** — primitives, enums, defaults; no nested config blobs.
3. **Instructions are context** — docstrings say when/how/what; errors are recoverable observations.
4. **Curate ruthlessly** — 5–15 tools, one job, trim responses, split by persona.
5. **Name for discovery** — `{service}_{action}_{resource}`.
6. **Paginate** — `limit` + `has_more` / `next_offset` / `total_count`.

> You are not building infrastructure. You are building an interface for AI agents. Build it like one.

---

## Source and further reading

This skill distills Philipp Schmid, "MCP is Not the Problem, It's your Server: Best Practices for Building MCP Servers" (philschmid.de, Jan 2026). For deeper dives the article points to Block's MCP Playbook (high-quality server design), GitHub's guide to secure and scalable remote MCP servers, and FastMCP's AI Engineering Summit talk. Consult those for security/auth, transport, and deployment specifics, which this skill only touches on lightly.
