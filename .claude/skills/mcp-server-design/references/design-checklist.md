# MCP Server Design & Review Checklist

Use this to audit an existing server or sanity-check a new design before shipping. Walk each item, mark it pass / fail / N-A, and for every failure write the specific offending tool, argument, or response **plus the concrete rewrite**. Findings are only useful when they're actionable.

The checklist is organized by the six principles, then general hygiene. Items are roughly ordered by leverage — the early ones reclaim the most context and round-trips.

---

## 1. Outcomes, not operations

- [ ] Each tool maps to a **goal a user/agent actually has**, not to an internal endpoint.
- [ ] No common user goal requires the agent to **chain 2+ tools** that the server could have combined. (Trace the top 3–5 user goals through the tool list; count the calls.)
- [ ] Multi-step orchestration lives in **server code**, not in the agent's context.
- [ ] Tools return a **resolved outcome** ("shipped via FedEx, arriving Thursday"), not raw intermediate data the agent must further process.

*Highest-leverage fix:* collapse multi-call workflows into single outcome tools.

## 2. Flatten your arguments

- [ ] Arguments are **top-level primitives** (str, int, bool, etc.) — no nested dicts or free-form config objects.
- [ ] Constrained choices use **`Literal`/enum**, not free strings.
- [ ] Sensible **defaults** are provided so the agent makes fewer decisions.
- [ ] Required vs. optional is unambiguous; there are no "guess the structure" parameters.
- [ ] No argument requires the agent to **encode/serialize** something by hand (e.g. base64 MIME, JSON-in-a-string). The server does that.

## 3. Instructions are context

- [ ] Every tool has a **non-empty docstring/description**.
- [ ] Each docstring states **when to use** the tool.
- [ ] Each docstring states **how to format arguments** (units, casing, formats, constraints).
- [ ] Each docstring states **what the tool returns**.
- [ ] Errors return **actionable strings the agent can recover from**, not raw exceptions/stack traces. (e.g. "User not found. Try searching by email instead.")
- [ ] Error messages suggest the **next step** where possible.

## 4. Curate ruthlessly

- [ ] The server exposes roughly **5–15 tools** (more is a smell).
- [ ] The server has **one clear job**; unrelated capabilities are split out.
- [ ] **Unused / redundant tools are removed.**
- [ ] Distinct personas (e.g. admin vs. user) are **split into separate servers/scopes** rather than one bloated surface.
- [ ] Responses contain **only the fields the agent needs** — no dumping the full upstream payload.
- [ ] No tool returns large raw blobs the agent must parse to find the relevant bit.

## 5. Name tools for discovery

- [ ] Tool names follow **`{service}_{action}_{resource}`** (or a consistent, specific scheme).
- [ ] No **generic names** (`create_issue`, `send_message`, `search`, `get`) that could collide with other servers.
- [ ] Names are **action-oriented** and self-explanatory at a glance.
- [ ] Naming is **consistent** across the whole server (same verbs for same actions).

## 6. Paginate large results

- [ ] Every list-returning tool accepts a **`limit`** (default ~20–50).
- [ ] List responses include **`has_more`**, **`next_offset`** (or cursor), and **`total_count`**.
- [ ] The server **never loads all results into memory** to return them at once.
- [ ] The agent can tell from the response whether and how to fetch more.

---

## General hygiene (lightly covered by the source; verify against current docs)

These go beyond the six core principles. The source article focuses on agent-facing interface design; for depth on security, transport, and deployment, consult Block's MCP Playbook and GitHub's guide to secure remote MCP servers.

### Primitive selection
- [ ] **Actions** the agent performs are **tools**; **data** it reads is exposed as **resources**; reusable **multi-step workflows** are **prompts**. They aren't all forced into tools.

### Tool surface quality
- [ ] Tool descriptions are written for a **non-human reader** — no assumed external docs.
- [ ] Return shapes are **consistent** across tools (same field names for the same concepts).
- [ ] Idempotency and side-effects are clear from the name/description (a tool that sends an email reads like one).

### Reliability & safety
- [ ] Destructive or irreversible tools are **clearly named and described** as such.
- [ ] Inputs are **validated** server-side; bad input yields an actionable error, not a crash.
- [ ] Secrets/credentials are **never** passed as tool arguments by the agent or returned in responses.
- [ ] Auth, rate limits, and transport are handled appropriately for the deployment (local vs. remote). *(Out of scope for the source article — see the linked security guides.)*

### Implementation
- [ ] Code uses **current SDK syntax** (verify against official MCP SDK / FastMCP docs — APIs change; don't trust memory for exact decorators/signatures).
- [ ] The server is **testable**: each tool can be exercised in isolation with representative inputs and its response inspected.

---

## How to report an audit

For each failure, produce a row like:

- **Principle:** 2 — Flatten your arguments
- **Where:** `search_orders(filters: dict)`
- **Problem:** Agent must guess the structure of `filters`; it hallucinates keys and omits required fields.
- **Fix:** `search_orders(email: str, status: Literal["pending","shipped","delivered"] = "pending", limit: int = 10)`

Group findings by principle, lead with the highest-leverage fixes (usually P1 collapsing call chains and P4 trimming responses), and end with a short prioritized to-do list so the user knows what to change first.
