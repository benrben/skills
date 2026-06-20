# Troubleshooting: Symptom → Cause → Fix

Read when a server built from this skill misbehaves. Organized by what you *observe*. The skill is strong on design/build; this is the debug-time companion. When a symptom looks version-specific, confirm against `gofastmcp.com` (see SKILL.md Step 0).

## Import & version

**`ImportError` / `ModuleNotFoundError: fastmcp`, or features missing that the docs describe.**
You may be on the SDK-bundled 1.0 (`from mcp.server.fastmcp import FastMCP`) or an old standalone version. Fix: `uv add fastmcp` (or `pip install -U fastmcp`), import `from fastmcp import FastMCP`, and check `fastmcp version`. Recommend **3.2.0+** (2.x has known CVEs).

**`AttributeError: 'FastMCP' object has no attribute 'get_tools'`** (or `get_resources`/`get_prompts`).
v3 renamed these to `list_tools()` etc., and they return a **list**, not a dict. Fix: `next(t for t in await mcp.list_tools() if t.name == "x")`. See the migration map in `fastmcp-cookbook.md`.

**`TypeError: mount() got an unexpected keyword argument 'prefix'`.**
v3 renamed it to `namespace=`: `main.mount(sub, namespace="sub")`.

**`TypeError: FastMCP.__init__() got an unexpected keyword argument 'host'`** (or `port`, `log_level`, `debug`, `sse_path`).
v3 dropped those constructor kwargs. Pass them to `mcp.run(transport="http", host=..., port=...)` instead.

## Tools / components not appearing

**A tool/resource/prompt doesn't show up in the client.**
Checklist: (1) Is it actually registered (decorator applied, module imported)? (2) Did a `Visibility` transform hide it — e.g. an earlier `mcp.enable(tags=..., only=True)` allowlist, or a `disable()`? (3) For mounted/proxied components, did the provider load and is the `namespace` what you expect? (4) The `LocalProvider` is queried first, so a directly-defined component **shadows** a mounted one with the same name.

**A resource or prompt is invisible, but tools work.**
The client is likely **tools-only** — many hosts expose only tools to the model. Fix: add `ResourcesAsTools(mcp)` / `PromptsAsTools(mcp)` transforms so they're reachable as `list_resources`/`read_resource`/etc. (see `architecture.md`). Design the clean three-way split, then bridge.

**Tool list changed at runtime but the client didn't notice.**
`tools/list_changed` only flows if the server declared the capability and the session is subscribed. Per-session visibility via `ctx.enable_components`/`disable_components` auto-emits it; manual provider swaps may not. Verify capability negotiation happened at `initialize`.

## Schema & validation

**Client rejects valid-looking input, or the model keeps mis-calling a tool.**
Usually the schema is the problem, not the model. (1) `*args`/`**kwargs` are unsupported — give every parameter an explicit type. (2) Pydantic-model params must arrive as JSON **objects**, not stringified JSON. (3) Tighten with `Literal`/enums and `Field(ge=, le=, pattern=)` so the model can't pick invalid values. (4) Make required-vs-optional explicit via defaults.

**`strict_input_validation=True` rejects inputs that should coerce (`"10"` → `10`).**
That flag turns off LLM-friendly coercion. Drop it (default) unless you truly need strictness.

**Return value isn't showing up as `structuredContent`.**
Primitives/collections only become structured with a **return annotation**; a bare `int` is wrapped as `{"result": ...}`. Annotate the return type (or return a dict/dataclass/Pydantic model). If you set `output_schema`, the return must match it.

## Errors & secrets

**Stack traces or internal details leaking to the model/client.**
Set `mask_error_details=True` and raise `ToolError("actionable message")` instead of letting raw exceptions through. Error text is a prompt to the model — say what to do next.

**A credential/user-id is appearing in the tool's input schema.**
It's a normal parameter; it must be injected. Use `param: T = Depends(resolver)` — `Depends()` params are stripped from the client-facing schema. Never make secrets model-visible, and never `ctx.elicit` for passwords/API keys.

## Transport & auth

**Per-component `auth=`/`require_scopes` seems ignored on a local server.**
**STDIO bypasses all component auth** — there's no OAuth concept for a subprocess. Gate in code or use OS permissions for STDIO; component auth applies to HTTP. See `security.md`.

**Remote (HTTP) server rejects everything / accepts everything unexpectedly.**
v3 auth providers **no longer auto-load from env vars** — pass `client_id`/`client_secret` explicitly. Configuring an `AuthProvider` already rejects unauthenticated requests at the transport layer (the old `require_auth` helper was removed). Confirm the provider config against `gofastmcp.com`.

**`sse` transport / `WSTransport` errors.**
`"sse"` is legacy and `WSTransport` was removed. Use Streamable HTTP (`transport="http"`) / `StreamableHttpTransport`.

## Async & testing

**`RuntimeError: event loop` / tests hang or fail intermittently.**
Use `pytest-asyncio` (or `anyio`) with a single loop scope — set `asyncio_mode = "auto"`. Don't mix sync and async test runners.

**Sync tool blocks the server / long calls freeze other requests.**
Sync tools run in a threadpool by default; if you set `run_in_thread=False` (for thread-affinity libs) it runs inline and blocks the loop — and is incompatible with `timeout=`. Prefer `async def` for I/O-bound work.

**`timeout=` doesn't interrupt a slow tool.**
Timeouts can't interrupt an inline synchronous call. Make the tool `async` (or ensure it runs in a thread) for the timeout to take effect.

## Decorator behavior

**Old code does `my_tool.name` / `my_tool.description` and now gets an AttributeError.**
v3 decorators return the **original function**, not a component object. Refactor to read metadata via `list_tools()`, or set `FASTMCP_DECORATOR_MODE=object` (deprecated escape hatch). The upside: you can call/unit-test the plain function directly.

## When none of this fits

Reproduce with the smallest possible in-memory `Client` test (see `example-server.md`), then web-search the exact error against `gofastmcp.com`. FastMCP iterates quickly — a renamed symbol is the most common root cause.
