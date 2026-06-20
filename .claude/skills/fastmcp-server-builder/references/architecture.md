# FastMCP 3.0 Architecture, Composition & Production

Read this when a server grows beyond a single file of hand-written tools: composing multiple servers, converting an OpenAPI spec, proxying a remote server, per-session tool visibility, versioning across a codebase, background tasks, telemetry, or choosing transports. The SKILL.md has the one-paragraph summary; this is the working detail.

## Table of contents
- The three primitives: Components, Providers, Transforms
- Providers (Local, FileSystem, Skills, OpenAPI, Proxy, FastMCP, custom)
- Transforms (Namespace, ToolTransform, VersionFilter, Visibility, ResourcesAsTools)
- Composition: mounting and proxying
- Visibility & personas
- Component versioning
- Session-scoped state & distributed backends
- Middleware vs transforms (the dividing line)
- Production features (timeouts, pagination, telemetry, background tasks)
- Transports, lifecycle & capability negotiation

## The three primitives: Components, Providers, Transforms

FastMCP 3.0 reduces the framework to three composable ideas. Internalize these and the advanced features stop being separate things to memorize.

- **Components** are the atoms — tools, resources, prompts. They have names, schemas, metadata, behavior. They're what clients interact with.
- **Providers** answer **"where do components come from?"** A provider can *list* components and *get one by name*. Decorated functions, a directory of files, a remote server, an OpenAPI spec — all providers. A FastMCP server is itself a provider, so servers nest arbitrarily.
- **Transforms** are middleware for the **component pipeline** — they intercept components flowing from providers to clients and modify what passes through. They compose (stack them) and apply at two levels.

Runtime flow on `list_tools` (same shape for `get_tool`, `call_tool`, `read_resource`, etc.):
1. The server collects components from all its **Providers**.
2. Each provider runs its own **provider-level** transform chain.
3. The server runs its **server-level** transform chain on the aggregated result.
4. The final list goes to the client.

The payoff: features that were huge bespoke subsystems in v2 are now just primitive combinations. "Mounting" = a FastMCPProvider + a Namespace transform. "Proxying" = a ProxyProvider. "Per-user tools" = a Visibility transform applied per-session. New providers/transforms automatically work with everything else.

## Providers

Attach via the constructor (`FastMCP("X", providers=[...])`) or `mcp.add_provider(...)`.

**LocalProvider** — the classic experience. Everything you register with `@mcp.tool`/`@mcp.resource`/`@mcp.prompt` lives here, and it's **always queried first**, so directly-defined components take precedence over mounted/proxied ones. In 3.0 it's explicit and reusable:

```python
from fastmcp.server.providers import LocalProvider

provider = LocalProvider()

@provider.tool
def greet(name: str) -> str:
    return f"Hello, {name}!"

server1 = FastMCP("S1", providers=[provider])  # attach the same provider to many servers
server2 = FastMCP("S2", providers=[provider])
```

**FileSystemProvider** — a decoupled way to organize a server. Write self-contained component files using the standalone decorators, then point the provider at the directory. No coupling between tool files and the server.

```
mcp/
├── server.py
└── components/
    ├── tools/      (each file: from fastmcp.tools import tool; @tool def ...)
    ├── resources/  (from fastmcp.resources import resource; @resource("uri") ...)
    └── prompts/    (from fastmcp.prompts import prompt; @prompt def ...)
```

```python
from fastmcp import FastMCP
from fastmcp.server.providers import FileSystemProvider

mcp = FastMCP("server", providers=[FileSystemProvider("mcp/components", reload=True)])
# reload=True re-scans on every request → edits take effect without a restart
```

**SkillsProvider** — exposes agent "skill" folders as MCP resources so any client can discover/download them (`skill://{name}/SKILL.md`, `skill://{name}/_manifest`, `skill://{name}/{path}`). Vendor variants with locked default paths: `ClaudeSkillsProvider`, `CursorSkillsProvider`, `VSCodeSkillsProvider`, `CodexSkillsProvider`.

```python
from pathlib import Path
from fastmcp.server.providers.skills import SkillsDirectoryProvider
mcp.add_provider(SkillsDirectoryProvider(roots=Path.home() / ".claude" / "skills"))
```

**OpenAPIProvider** — converts an OpenAPI spec to tools (all endpoints become tools by default). Restructured as a provider in 3.0 so it composes with everything. **Always pair with `ToolTransform`** to rename and curate the auto-generated tools, rather than dumping a raw API into the model's context:

```python
import httpx
from fastmcp.server.providers.openapi import OpenAPIProvider

client = httpx.AsyncClient(base_url="https://api.example.com")  # set timeout here in v3
provider = OpenAPIProvider(openapi_spec=spec, client=client)
mcp = FastMCP("API Server", providers=[provider])
```

**ProxyProvider** — sources components from a remote MCP server (powers `create_proxy()`):

```python
from fastmcp.server import create_proxy
server = create_proxy("http://remote-server/mcp")
```

**FastMCPProvider** — sources components from another FastMCP instance (powers `mount()`).

**Custom providers** — the extension point. Subclass `Provider` and implement `list_tools`/`get_tool` (+ resource/prompt equivalents):

```python
from fastmcp.server.providers import Provider
from fastmcp.tools import Tool

class DatabaseProvider(Provider):
    async def list_tools(self):
        rows = await db.fetch("SELECT name, description FROM tools")
        return [Tool(name=r["name"], description=r["description"]) for r in rows]
    async def get_tool(self, name):
        r = await db.fetchrow("SELECT name, description FROM tools WHERE name = ?", name)
        return Tool(name=r["name"], description=r["description"]) if r else None

mcp = FastMCP("DB Server", providers=[DatabaseProvider()])
```

## Transforms

`provider.add_transform(...)` (provider-level, that provider only) or `server.add_transform(...)` (server-level, everything). Built-ins:

**Namespace** — prefix names (`tool` → `api_tool`) and URI path segments; essential to avoid collisions when composing.

```python
from fastmcp.server.transforms import Namespace
provider.add_transform(Namespace("api"))
```

**ToolTransform** — reshape tools wholesale (rename, rewrite descriptions, rename/retype args, add tags). The killer use is optimizing tools you *don't* control (OpenAPI- or proxy-sourced) for your agent:

```python
from fastmcp.server.transforms import ToolTransform
from fastmcp.tools.tool_transform import ToolTransformConfig

provider.add_transform(ToolTransform({
    "verbose_auto_generated_name": ToolTransformConfig(
        name="short_name",
        description="A better description aimed at the agent.",
        tags={"catalog"},
    ),
}))
```

(For tools you *do* control, `Tool.from_tool(...)` applies the same edits immediately at registration.)

**VersionFilter** — expose only components in a version range, so v1 and v2 run from one codebase:

```python
from fastmcp.server.transforms import VersionFilter
api_v1 = FastMCP("API v1", providers=[components]); api_v1.add_transform(VersionFilter(version_lt="2.0"))
api_v2 = FastMCP("API v2", providers=[components]); api_v2.add_transform(VersionFilter(version_gte="2.0"))
```

**Visibility** — show/hide by tag, name, or version (powers `enable()`/`disable()`; see next section).

**ResourcesAsTools / PromptsAsTools** — generate `list_resources`/`read_resource` (and prompt equivalents) tools so **tools-only clients** can reach your resources/prompts:

```python
from fastmcp.server.transforms import ResourcesAsTools, PromptsAsTools
mcp.add_transform(ResourcesAsTools(mcp))
mcp.add_transform(PromptsAsTools(mcp))
```

**Custom transforms** — subclass `Transform`; `list_*` ops receive the sequence and return a transformed one, `get_*` ops use a `call_next` middleware pattern:

```python
from collections.abc import Sequence
from fastmcp.server.transforms import Transform, GetToolNext
from fastmcp.tools import Tool

class TagFilter(Transform):
    def __init__(self, required: set[str]): self.required = required
    async def list_tools(self, tools: Sequence[Tool]) -> Sequence[Tool]:
        return [t for t in tools if t.tags & self.required]
    async def get_tool(self, name: str, call_next: GetToolNext) -> Tool | None:
        t = await call_next(name)
        return t if t and t.tags & self.required else None
```

## Composition: mounting and proxying

```python
# Mount a sub-server under a namespace (greet → sub_greet). = FastMCPProvider + Namespace.
main = FastMCP("Main"); sub = FastMCP("Sub")
@sub.tool
def greet(name: str) -> str: return f"Hello, {name}!"
main.mount(sub, namespace="sub")   # v3 renamed the v2 `prefix=` kwarg to `namespace=`; verify on gofastmcp.com

# Proxy a remote server and expose its components as local. = ProxyProvider.
from fastmcp.server import create_proxy
gateway = create_proxy("http://remote/mcp")
```

Compose freely: proxy a remote server, filter its tools by tag, rename them, and restrict to authenticated users = a ProxyProvider + a few Transforms + auth middleware. Each piece is independent and testable.

## Visibility & personas

Each `enable()`/`disable()` adds a Visibility transform. Default is **blocklist** (all visible except disabled); allowlist with `only=True`.

```python
mcp.disable(names={"dangerous_tool"}, components=["tool"])  # hide by name
mcp.disable(tags={"admin"})                                  # hide by tag
mcp.enable(tags={"public"}, only=True)                       # allowlist: only public

# Later transform wins:
mcp.disable(tags={"internal"})
mcp.enable(names={"safe_tool"})   # safe_tool visible despite the internal tag
```

This is how you split personas (admin vs. user) and keep tool counts lean per client. Server-level changes affect all sessions; for per-session control use the `Context` methods (`ctx.enable_components` / `disable_components` / `reset_visibility`, see cookbook) — FastMCP auto-emits `list_changed` notifications to affected sessions.

## Component versioning

Register multiple versions of the same logical component; the highest (PEP 440 semantics, `1.10 > 1.9 > 1.2`; `v` prefix normalized) is exposed by default.

```python
@mcp.tool(version="1.0")
def add(x: int, y: int) -> int: return x + y
@mcp.tool(version="2.0")
def add(x: int, y: int, z: int = 0) -> int: return x + y + z
```

Listing exposes all versions in `meta["fastmcp"]["versions"]`. The FastMCP client can call a specific version: `await client.call_tool("add", {...}, version="1.0")`. Generic clients pass it via `_meta`:

```json
{"x": 1, "y": 2, "_meta": {"fastmcp": {"version": "1.0"}}}
```

## Session-scoped state & distributed backends

State persists across tool calls within a session (3.0), keyed by session ID, async API, 1-day TTL:

```python
@mcp.tool
async def increment(ctx: Context) -> int:
    n = await ctx.get_state("counter") or 0
    await ctx.set_state("counter", n + 1)
    return n + 1
```

For horizontally-scaled HTTP deployments, plug in a distributed store (uses `pykeyvalue`):

```python
from key_value.aio.stores.redis import RedisStore
mcp = FastMCP("server", session_state_store=RedisStore(...))
```

For stateless HTTP (no persistent connection), FastMCP honors the `mcp-session-id` header most clients send and creates a virtual session if a backend is configured.

## Middleware vs transforms (the dividing line)

FastMCP keeps request **middleware** for cross-cutting concerns that act *as requests execute* — auth, logging, rate limiting, error handling. It intercepts tool calls, resource reads, etc.

```python
from fastmcp.server.middleware import AuthMiddleware
from fastmcp.server.auth import require_scopes
mcp = FastMCP(middleware=[AuthMiddleware(auth=require_scopes("read"))])
```

**The guideline:** transforms shape *what components exist*; middleware handles *how requests execute*. Don't use middleware to invent components dynamically (the v2 hack) — that's what providers and transforms are for.

## Production features

- **Timeouts** — `@mcp.tool(timeout=30)` returns an MCP error if exceeded (can't interrupt inline sync calls).
- **Pagination** — always bound list-returning tools: a `limit` (default 20–50) plus `has_more`/`next_offset`/`total_count`. For huge catalogs, a "search transform" can replace a static listing with on-demand discovery so the model isn't carrying the whole catalog.
- **OpenTelemetry tracing** (3.0, native) — configure an OTLP exporter and every tool call, resource read, and prompt render becomes a span (attributes: component key, provider type, session ID, auth context). Client spans propagate W3C trace context.
  ```python
  from opentelemetry import trace
  from opentelemetry.sdk.trace import TracerProvider
  from opentelemetry.sdk.trace.export import BatchSpanProcessor
  from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
  tp = TracerProvider(); tp.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
  trace.set_tracer_provider(tp)  # then use FastMCP normally
  ```
- **Background tasks (SEP-1686)** — FastMCP implements the long-running-task spec extension via Docket integration (persistent queues on SQLite/Postgres). Use for work that outlives a request; elicitation and sampling work in both foreground and background modes.
- **Rate limiting & error masking** — `FastMCP("Prod", rate_limit="100/hour", mask_error_details=True)`.
- **Hot reload** — `fastmcp run server.py --reload` watches source (incl. JS/TS/HTML/CSS/config/media for MCP Apps frontends) and restarts; uses stateless mode.

## Transports, lifecycle & capability negotiation

- **STDIO** (default) — server is a local subprocess over stdin/stdout, one client; the client spawns and manages the process. Ideal for desktop hosts and local tools. **STDIO bypasses all component auth** (no OAuth concept).
- **Streamable HTTP** (`transport="http"`) — server at a URL, many clients, standard HTTP auth, session management, resumability. The current remote transport (replaced HTTP+SSE in MCP `2025-03-26`; `"sse"` is legacy). Apply the security gates in `security.md` before deploying.

MCP today is **stateful**: `initialize` handshake → capability negotiation (which primitives + notifications each side supports) → `notifications/initialized` → operation. Capability negotiation is why, e.g., `tools/list_changed` only flows if the server declared `"listChanged": true`. The MCP `2026-07-28` release candidate (not yet final as of mid-2026) introduces a **stateless** core so remote servers can run behind a plain round-robin load balancer without sticky sessions or a shared session store — build against the stateful model today while keeping handlers stateless where you can, to ease that transition.
