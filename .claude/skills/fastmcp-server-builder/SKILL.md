---
name: fastmcp-server-builder
description: >-
  Design, build, structure, review, and harden Model Context Protocol (MCP)
  servers using FastMCP (the Python framework at gofastmcp.com, currently v3.x).
  Use this whenever the user is building or architecting an MCP server, writing
  tools/resources/prompts, deciding whether a capability should be a tool vs a
  resource vs a prompt, exposing an API or data source to an LLM/agent,
  composing or proxying MCP servers, adding auth or pagination or testing to a
  server, or asking "how do I expose X to Claude/an agent." Trigger even when
  the user says "MCP server," "FastMCP," "@mcp.tool," "expose this to an agent,"
  or describes the goal without naming MCP (e.g. "let the model call my API,"
  "give the assistant access to my database"). Prefer this skill over improvising
  from memory, because FastMCP 3.0 changed the architecture substantially and the
  decision framework below prevents the most common design mistakes.
---

# FastMCP Server Builder

Build MCP servers that agents can actually use well. This skill encodes two things that are easy to get wrong: **(1) deciding what each capability should be** (tool vs resource vs prompt) and **(2) writing it correctly in current FastMCP** (v3.x), with the architecture, security, and testing practices that separate a usable server from a token-wasting one.

The single most important idea: **the model never sees your code.** It sees the names, descriptions, schemas, and errors you expose. Design every component for the reader who *is* the model.

## When NOT to use this skill (scope)

This skill is for **building MCP servers in Python with FastMCP**. It does **not** cover: writing MCP *clients* (consuming a server); the unrelated **TypeScript** project also named `fastmcp`; the SDK-bundled `mcp.server.fastmcp` 1.0 lineage; or general (non-MCP) Python API design. If the task is one of those, say so and don't stretch this skill to fit.

## Before you start: orient

Two facts that drive everything (verify specifics with `references/fastmcp-cookbook.md`, and web-search if the user's version differs):

- **FastMCP (Python)** is `from fastmcp import FastMCP` (gofastmcp.com, v3.x). The SDK-bundled lineage `from mcp.server.fastmcp import FastMCP` is the older 1.0 and lacks v2/v3 features. There is also an *unrelated* TypeScript project named `fastmcp` — this skill is Python only.
- **FastMCP 3.0** rebuilt the framework around **Components → Providers → Transforms**. The MCP spec's current stable revision is `2025-11-25`; later revisions may exist. If a detail might have changed, web-search `gofastmcp.com` rather than guessing.

### Step 0 — Verify the environment before writing code (do not skip)

FastMCP iterates fast and 3.0 broke many 2.x APIs, so **ground the API before generating any code**:

1. **Check the installed version:** `fastmcp version` (or `python -c "import fastmcp; print(fastmcp.__version__)"`).
2. **Detect the major line** from what you see in the user's code or environment:
   - `from fastmcp import FastMCP` + `mcp.list_tools()` + decorators return the original function → **v3.x** (this skill's default).
   - `server.get_tools()` returning a dict, `mount(server, prefix=...)`, decorators returning component objects, or `FastMCP(host=, port=, log_level=...)` kwargs → **v2.x** (see the v2→v3 map in `references/fastmcp-cookbook.md` and migrate, or write v2-correct code if the user can't upgrade).
   - `from mcp.server.fastmcp import FastMCP` → **1.0 SDK-bundled**; recommend installing standalone `fastmcp` for v2/v3 features.
3. **Confirm one signature you're about to use** against `gofastmcp.com` (or the installed source) if there's any doubt — a single check prevents teaching a renamed API. Note: 2.x has known CVEs; recommend **3.2.0+** when the user is choosing a version.

If the user already has server code, read it first, detect the version, and work from what's there. If they're starting fresh on v3, follow the workflow at the bottom and pattern-match against `references/example-server.md`.

## Part 1 — The decision rule (apply this first, every time)

For any capability, ask **who controls when it runs**:

| If… | It's a | Because |
|---|---|---|
| the **model** should decide when to invoke it | **Tool** | model-controlled; actions and model-driven fetches |
| the **application** should inject it as background context | **Resource** | app-controlled; read-only data the host pulls in |
| the **user** should explicitly invoke it as a named workflow | **Prompt** | user-controlled; slash-command-style templates |

> **One-line rule:** Side-effect or model-decided action → **Tool**. Passive context the app injects → **Resource**. User-invoked named workflow → **Prompt**.

Sharp edges that decide most real cases:

- **It's not "read vs. write."** A read is still a **tool** if the model must *actively decide to fetch it mid-reasoning* (e.g. `weather_current(city)`, `search_flights(...)`). It's a **resource** only if it's stable context the host can browse or auto-inject (a schema, a doc, config).
- **Same data, two homes.** "Get the DB schema" → `db://schema` (resource) if it's stable context the app injects; `get_schema()` (tool) if the model must deliberately request it or fetching has cost. Default to resource for stable context, tool for model-driven steps.
- **Tools-only clients are common.** Many hosts expose *only tools* to the model. If your consumers are tools-only, a resource/prompt is invisible unless you also add the `ResourcesAsTools` / `PromptsAsTools` transforms. Design the clean three-way split, then degrade for tools-only.
- **The same domain usually wants all three.** A database server: **tools** to query, a **resource** for the schema, a **prompt** with few-shot examples. Split by control, not by domain.

When the choice is genuinely unclear, ask the control question out loud (model/app/user) and commit — don't make everything a tool by default. For deeper reasoning and worked examples, read `references/decision-framework.md`.

## Part 2 — Write it correctly in FastMCP (the essentials)

Minimal server — the whole surface is three decorators:

```python
from fastmcp import FastMCP

mcp = FastMCP(name="OrdersServer")

@mcp.tool
def track_order(email: str) -> dict:
    """Find a customer's most recent order and return its tracking status.

    Args:
        email: The customer's account email address.
    """
    # Do the multi-step work HERE, in code — not by making the model chain calls.
    ...
    return {"order_id": "A123", "status": "shipped", "eta": "2026-06-25"}

@mcp.resource("orders://policy/returns")
def returns_policy() -> str:
    """The current returns policy (stable reference text)."""
    return "Returns accepted within 30 days..."

@mcp.prompt
def file_a_complaint(order_id: str) -> str:
    """Guided workflow for filing a complaint about an order."""
    return f"Help me file a complaint about order {order_id}. Ask me for..."

if __name__ == "__main__":
    mcp.run()  # STDIO by default; mcp.run(transport="http") for remote
```

FastMCP infers the tool name from the function, the description and per-parameter docs from the docstring (`Args:`), and the input schema from type hints. Write Python, not protocol boilerplate. Full API (annotations, structured output, `ToolResult`, timeouts, versioning, `Depends()`, Context/elicitation/sampling, resources & templates, prompts, running, testing) is in `references/fastmcp-cookbook.md` — **read it before writing non-trivial components.**

## Part 3 — Best practices that separate good servers from bad (enforce these)

Each competes for the model's limited context and attention; treat them as requirements, not suggestions.

1. **Outcome-oriented tools, not REST 1:1.** The #1 mistake is mirroring API endpoints. Collapse multi-step work into one tool and do the orchestration in code. `track_order(email)` that internally finds the user → lists orders → fetches tracking beats three atomic tools the model must chain. Chained calls are slow, token-heavy, and error-prone.
2. **One server, one job; 5–15 tools; curate ruthlessly.** Delete unused tools. Split personas (admin vs. user) with tag-based visibility (`mcp.enable(tags={"public"}, only=True)`). Too many tools degrades the model's selection accuracy.
3. **Name for disambiguation:** `{service}_{action}_{resource}` → `slack_send_message`, `linear_list_issues`. The `name` is the unique key; `title` is the display label.
4. **Flatten and constrain arguments.** Top-level primitives over nested dicts; `Literal[...]`/enums over free strings; clear per-parameter descriptions; defaults map to optional. Use `Field(ge=, le=, pattern=, ...)` for constraints.
5. **Every description and error is a prompt to the model.** Docstrings say *when to use, what comes back, how to format*. Errors are actionable observations the model can self-correct from — never raw stack traces. In production set `mask_error_details=True`.
6. **Paginate and bound everything.** Default `limit` 20–50; return `has_more`/`next_offset`/`total_count`; never dump hundreds of rows. Add a `timeout=` to tools that can hang.
7. **Return structured output** (annotate return types) whenever the result is consumed programmatically, so clients get deserializable `structuredContent`, not text to parse.
8. **Hide secrets from the model.** Inject `user_id`, credentials, DB handles with `Depends()` — they're stripped from the schema. Never make them tool parameters.
9. **Annotations must be honest.** `readOnlyHint`/`destructiveHint`/`idempotentHint`/`openWorldHint` are advisory hints clients may distrust; make them reflect real behavior.
10. **Test in-memory from day one.** Pass the server straight into a `Client` — real protocol, no subprocess/network, fast and deterministic.

Security is non-negotiable and has its own file, which is the **single source of truth** for it — don't rely on the abbreviated headlines elsewhere in this skill. **Before exposing auth, external fetches, sessions, or a remote deployment, read `references/security.md`.** In one line: no token passthrough; least-privilege/incremental scopes; per-client OAuth consent (CIMD over DCR); block SSRF; CSPRNG session IDs bound to user; never elicit secrets; **STDIO bypasses all component auth**.

## Part 4 — Architecture & composition (when the server grows)

For multi-server systems, OpenAPI conversion, proxying a remote server, per-session tool visibility, versioning, background tasks, or telemetry, read `references/architecture.md`. The core idea: in FastMCP 3.0, **Providers** answer "where do components come from?" (Local, FileSystem, OpenAPI, Proxy, FastMCP, custom) and **Transforms** are middleware over the component pipeline (Namespace, ToolTransform, VersionFilter, Visibility, ResourcesAsTools). Mounting = a FastMCPProvider + a Namespace transform; proxying = a ProxyProvider. **Transforms shape *what components exist*; request middleware handles *how requests execute*** — don't conflate them.

## Workflow: building a server from scratch

0. **Verify the environment** (Step 0 above): confirm the FastMCP version and detect the major line before writing any code.
1. **Clarify the job.** What single outcome does this server serve, and who are the clients (tools-only host? full MCP client?)? Keep one server to one job.
2. **Inventory capabilities and classify each** with the Part 1 control rule. Write the list as `tool/resource/prompt: name — purpose` before writing code. Resist making everything a tool.
3. **Design tools outcome-first.** For each, decide the one outcome, the flat typed arguments, the return shape (structured?), pagination, timeout, and which inputs are `Depends()`-injected.
4. **Write components** following `references/fastmcp-cookbook.md`. Use docstrings as model-facing instructions.
5. **Add security** per `references/security.md` if there's auth, external fetching, sessions, or remote deployment.
6. **Write in-memory tests** (cookbook has the pattern). Target sub-second tests; assert on schemas and tool results.
7. **Choose transport and run.** STDIO for local/desktop; `transport="http"` for remote (then apply the auth gates). Use `fastmcp run server.py --reload` for the dev loop.
8. **Review against Part 3** and the checklist in `references/decision-framework.md` before calling it done.

If something doesn't work as expected at any step, see `references/troubleshooting.md`.

## Reference files

- `references/example-server.md` — A complete, runnable server (tools + resource + prompt + `Depends()` + pagination + in-memory test) you can pattern-match against. Read when starting fresh or when you want a known-good template instead of assembling fragments.
- `references/decision-framework.md` — Deep tool/resource/prompt reasoning, worked examples, and the full per-capability checklist. Read when a classification is unclear or when reviewing a design.
- `references/fastmcp-cookbook.md` — Comprehensive FastMCP 3.x code: tools (annotations, structured output, ToolResult, timeouts, versioning, Depends), resources & templates, prompts, Context (elicitation/sampling/progress/logging/state), running, testing, and the v2→v3 migration map. Read before writing non-trivial components.
- `references/architecture.md` — Providers, transforms, composition/mounting/proxying, OpenAPI conversion, per-session visibility, background tasks, telemetry, transports. Read when the server spans multiple sources or needs production features.
- `references/security.md` — The MCP threat model and FastMCP's auth tools: token passthrough, confused deputy/CIMD, SSRF, session hijacking, local compromise, scope minimization, per-component auth. Read before adding auth or deploying remotely.
- `references/troubleshooting.md` — Symptom-keyed fixes for common failures (tool not appearing, schema rejecting input, resources invisible to tools-only clients, STDIO/HTTP auth confusion, async/event-loop errors, v2/v3 mismatches). Read when something built from this skill misbehaves.
