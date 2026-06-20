# FastMCP 3.x Cookbook

Concrete, current FastMCP (Python, v3.x) code patterns. Read before writing non-trivial components. If a detail looks out of date for the user's installed version, web-search `gofastmcp.com` to confirm — FastMCP iterates quickly.

## Table of contents
- Install & version check
- Minimal server
- Tools: decorator, arguments, descriptions, validation
- Tools: hiding parameters with Depends()
- Tools: return values, structured output, output schemas, ToolResult
- Tools: media (Image/Audio/File)
- Tools: timeouts, versioning, annotations
- Tools: error handling
- Tools: async & thread affinity
- Resources & resource templates
- Prompts
- Context: access, logging, progress, state, elicitation, sampling, visibility
- Running the server (STDIO / HTTP / CLI / reload)
- Testing in-memory
- v2 → v3 migration gotchas

## Install & version check

```bash
# uv is recommended (required for the FastMCP CLI / deployment)
uv add fastmcp
# or
pip install fastmcp

fastmcp version   # prints FastMCP, MCP, Python versions
```

Imports come from the standalone package:

```python
from fastmcp import FastMCP                # the server class (v3.x)
# NOT: from mcp.server.fastmcp import FastMCP  (that's the older SDK-bundled 1.0)
```

## Minimal server

```python
from fastmcp import FastMCP

mcp = FastMCP(name="CalculatorServer")

@mcp.tool
def add(a: int, b: int) -> int:
    """Adds two integer numbers together."""
    return a + b

if __name__ == "__main__":
    mcp.run()  # STDIO; the __main__ guard lets clients launch it as a subprocess
```

FastMCP auto-derives: tool name (function name), description + per-parameter docs (docstring), input schema (type hints), and validation. The decorator returns the **original function** in v3, so `add(2, 3)` still works for tests and reuse.

## Tools: decorator, arguments, descriptions, validation

Override metadata and add tags/meta:

```python
@mcp.tool(
    name="find_products",
    description="Search the product catalog with optional category filtering.",
    tags={"catalog", "search"},
    meta={"author": "product-team"},
)
def search_products(query: str, category: str | None = None) -> list[dict]:
    ...
```

Type annotations drive the schema. Supported: scalars, `bytes`, `datetime`/`date`/`timedelta`, collections (`list[str]`, `dict[str,int]`, `set[int]`), `X | None`/`Optional`, unions, `Literal[...]`/`Enum`, `Path`, `UUID`, and Pydantic models. Parameters without defaults are **required**; with defaults are **optional**.

Three ways to describe parameters (any explicit description beats the docstring):

```python
from typing import Annotated, Literal
from pydantic import Field

# 1) Docstring Args (parsed in 3.2.4+; Google/NumPy/Sphinx styles)
@mcp.tool
def process_image(image_url: str, width: int = 800) -> dict:
    """Process an image with optional resizing.

    Args:
        image_url: URL of the image to process.
        width: Target width in pixels.
    """
    ...

# 2) Annotated shorthand for a simple description
@mcp.tool
def resize(image_url: Annotated[str, "URL of the image to process"]) -> dict: ...

# 3) Field for descriptions + validation constraints
@mcp.tool
def fmt(
    width: Annotated[int, Field(description="Target width", ge=1, le=2000)] = 800,
    out: Annotated[Literal["jpeg", "png", "webp"], Field(description="Output format")] = "jpeg",
) -> dict: ...
```

Validation modes: by default FastMCP coerces compatible inputs (`"10"` → `10`) to tolerate LLM clients. For strictness:

```python
mcp = FastMCP("StrictServer", strict_input_validation=True)  # rejects type mismatches
```

`*args`/`**kwargs` are **not** supported (the schema must be complete). Pydantic models must arrive as JSON objects (dicts), not stringified JSON.

## Tools: hiding parameters with Depends()

Inject runtime values the model must never see (user IDs, credentials, DB handles). `Depends()` parameters are stripped from the tool's input schema (2.14+):

```python
from fastmcp.dependencies import Depends

def get_user_id() -> str:
    return "user_123"  # resolved at runtime (e.g. from auth context)

@mcp.tool
def get_user_details(user_id: str = Depends(get_user_id)) -> str:
    # The model never supplies user_id; the server injects it.
    return f"Details for {user_id}"
```

This is the correct way to keep auth/identity out of the model's hands — never make a credential a normal parameter.

## Tools: return values, structured output, output schemas, ToolResult

Return-type annotations generate an **output schema** and enable `structuredContent` (MCP 2025-06-18):

- **Object-like returns** (`dict`, dataclass, Pydantic model) → always become structured content, even without an explicit schema.
- **Primitives/collections** (`int`, `str`, `list`) → become structured content only with a return annotation; a bare `int` is wrapped as `{"result": 8}` (JSON Schema roots must be objects).
- **All returns** also become human-readable content blocks for backward compatibility.

```python
from dataclasses import dataclass

@dataclass
class Person:
    name: str
    age: int

@mcp.tool
def get_user(user_id: str) -> Person:  # schema auto-generated from Person
    return Person(name="Alice", age=30)
```

Override the schema or take full control:

```python
from fastmcp.tools.tool import ToolResult
from mcp.types import TextContent

@mcp.tool
def advanced() -> ToolResult:
    return ToolResult(
        content=[TextContent(type="text", text="Human-readable summary")],
        structured_content={"data": "value", "count": 42},
        meta={"execution_time_ms": 145},   # runtime metadata (≠ the @mcp.tool meta=)
    )
```

`output_schema` must be an object type; if you set one, the tool must return matching structured output. For custom serialization (YAML, Markdown), return `ToolResult` with your serialized `content` and the raw `structured_content`.

## Tools: media (Image/Audio/File)

```python
from fastmcp.utilities.types import Image, Audio, File

@mcp.tool
def get_chart() -> Image:
    return Image(path="chart.png")          # MIME inferred from extension
    # or Image(data=raw_bytes, format="png")
```

Auto-conversion happens when returned directly or inside a list. Inside a dict, convert manually: `Image(...).to_image_content()`.

## Tools: timeouts, versioning, annotations

```python
# Timeout (3.0): MCP error to client if exceeded. Can't interrupt inline sync calls.
@mcp.tool(timeout=30)
def slow_query(q: str) -> list[dict]: ...

# Versioning (3.0): highest version exposed by default; clients may request a specific one
@mcp.tool(version="1.0")
def add(x: int, y: int) -> int: return x + y

@mcp.tool(version="2.0")
def add(x: int, y: int, z: int = 0) -> int: return x + y + z

# Annotations: advisory hints — make them HONEST (clients may distrust them)
@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": True})
def search_web(query: str) -> list[dict]: ...

@mcp.tool(annotations={"destructiveHint": True, "idempotentHint": False})
def delete_record(record_id: str) -> dict: ...
```

## Tools: error handling

```python
from fastmcp.exceptions import ToolError

@mcp.tool
def divide(a: float, b: float) -> float:
    if b == 0:
        # Error text the MODEL reads — make it actionable, not a stack trace.
        raise ToolError("Cannot divide by zero. Provide a non-zero 'b'.")
    return a / b
```

Ordinary Python exceptions also work. In production, hide internals:

```python
mcp = FastMCP("Prod", mask_error_details=True)
```

## Tools: async & thread affinity

```python
import httpx

@mcp.tool
async def fetch(url: str) -> str:          # prefer async for I/O-bound work
    async with httpx.AsyncClient() as c:
        return (await c.get(url)).text

# Sync tools run in a threadpool by default so they don't block the loop.
# For thread-affinity libs (Windows COM, tkinter, some GPU bindings):
@mcp.tool(run_in_thread=False)             # runs inline; blocks loop; incompatible with timeout=
def list_windows() -> list[str]: ...
```

## Resources & resource templates

One decorator; FastMCP registers a **static resource** for a fixed URI, or a **template** when the URI has `{placeholders}` or the function takes args:

```python
# Static resource
@mcp.resource("config://app", mime_type="application/json")
def app_config() -> dict:               # dict/list/BaseModel auto-serialize to JSON
    return {"theme": "dark", "version": "1.0"}

# Resource template (RFC 6570; also supports query params like {?category,limit})
@mcp.resource("users://{user_id}/profile")
def user_profile(user_id: str) -> str:
    """Get a user's profile by ID."""
    return f'{{"id": "{user_id}", "name": "User"}}'

# Binary resource
@mcp.resource("data://logo", mime_type="image/png")
def logo() -> bytes:
    return open("logo.png", "rb").read()   # Base64-encoded BlobResourceContents
```

Return types: `str` (→ `text/plain` by default), `bytes` (→ `application/octet-stream`; set a real `mime_type`), serializable objects (→ `application/json`), or a `ResourceResult` for multiple items / per-item MIME types / metadata. Decorator args: `uri` (required), `name`, `title`, `description`, `icons`, `mime_type`, `tags`, `annotations`, `meta`, `version`.

## Prompts

```python
from fastmcp.prompts import Message

# Returns a single user message
@mcp.prompt
def review(code: str) -> str:
    """Generate a standard code-review request."""
    return f"Please review this code for bugs and style:\n\n{code}"

# Returns a multi-turn seed (roles default to "user"; accepts plain strings)
@mcp.prompt
def debug(error: str) -> list[Message]:
    """Start a debugging session."""
    return [
        Message(f"I'm seeing this error:\n\n{error}"),
        Message("I'll help debug that. What were you doing when it happened?", role="assistant"),
    ]
```

v3 requires typed `Message` objects or plain strings — **not** raw `{"role": ..., "content": ...}` dicts (v2 silently coerced those; v3 rejects them). The old `mcp.types.PromptMessage` is replaced by `fastmcp.prompts.Message`.

## Context: access, logging, progress, state, elicitation, sampling, visibility

Add a `Context` parameter (or use the explicit `CurrentContext()` dependency) to any tool/resource/prompt; it's automatically excluded from the client-facing schema.

```python
from fastmcp import Context
# Explicit DI form the docs call preferred:
# from fastmcp.dependencies import CurrentContext
# async def tool(..., ctx: Context = CurrentContext()): ...

@mcp.tool
async def process(items: list[str], ctx: Context) -> dict:
    # Logging → structured notifications the client can show
    await ctx.info(f"Processing {len(items)} items")
    await ctx.debug("verbose detail")     # also: warning, error

    # Progress → drives progress UI on long ops
    for i, item in enumerate(items):
        await ctx.report_progress(progress=i, total=len(items))

    # Session state → persists ACROSS calls within a session (async in 3.0; 1-day TTL)
    count = await ctx.get_state("count") or 0
    await ctx.set_state("count", count + len(items))

    return {"processed": len(items), "session_total": count + len(items)}
```

**Elicitation** — pause to request structured input (MCP 2025-06-18). Never request secrets:

```python
from typing import Literal

@mcp.tool
async def book(ctx: Context) -> str:
    res = await ctx.elicit("Window or aisle?", response_type=Literal["window", "aisle"])
    if res.action == "accept":            # action ∈ accept / decline / cancel
        return f"Booked a {res.data} seat."
    return "Booking cancelled."
```

`response_type` can be a scalar, a `Literal`/enum (constrained options), or a Pydantic model (a small form).

**Sampling** — ask the *client's* LLM to do reasoning, so your server stays model-free:

```python
@mcp.tool
async def summarize(text: str, ctx: Context) -> str:
    resp = await ctx.sample(f"Summarize in one sentence:\n\n{text}", temperature=0.3)
    return resp.text
```

**Per-session visibility** — unlock/hide components for just this session (auto-emits `list_changed`):

```python
@mcp.tool(tags={"premium"})
def premium_report(data: str) -> str: ...

@mcp.tool
async def unlock_premium(ctx: Context) -> str:
    await ctx.enable_components(tags={"premium"})   # this session only
    return "Premium unlocked."
# Globally hidden; sessions opt in:
mcp.disable(tags={"premium"})
```

## Running the server (STDIO / HTTP / CLI / reload)

```python
if __name__ == "__main__":
    mcp.run()                                   # STDIO (default) — local/desktop hosts
    # mcp.run(transport="http", host="127.0.0.1", port=8000)   # Streamable HTTP (remote)
```

`transport="http"` is the current remote transport (Streamable HTTP). `"sse"` is legacy. CLI:

```bash
fastmcp run server.py                          # run (STDIO)
fastmcp run server.py --transport http --port 8080
fastmcp run server.py --reload                 # 3.0 hot-reload dev loop (stateless mode)
fastmcp run server.py --reload --reload-dir ./src
fastmcp dev server.py                           # launch with the MCP Inspector
fastmcp install stdio server.py                 # emit a uv-run command string for clients
```

## Testing in-memory

Pass the server straight into a `Client` — real MCP protocol, no subprocess or network. Fast and deterministic. Target sub-second tests.

```python
import pytest
from fastmcp import FastMCP, Client

@pytest.fixture
def server():
    mcp = FastMCP("TestServer")

    @mcp.tool
    def greet(name: str) -> str:
        return f"Hello, {name}!"

    return mcp

async def test_greet(server):
    async with Client(server) as client:
        result = await client.call_tool("greet", {"name": "World"})
        # Access deserialized value via .data; structured via .structured_content;
        # raw blocks via .content (e.g. result.content[0].text)
        assert result.data == "Hello, World!"

async def test_schema(server):
    tools = await server.list_tools()        # v3: list_tools() (v2 was get_tools())
    greet = next(t for t in tools if t.name == "greet")
    assert "name" in greet.inputSchema["properties"]
```

Notes: pytest async fixtures/tests can hit event-loop issues — use `pytest-asyncio` (or `anyio`) and a single loop scope. Because v3 decorators return the original function, you can also unit-test the plain function directly. Mocks/fixtures work normally since everything runs in-process.

## v2 → v3 detection & migration map

**First, detect which line you're on** (see SKILL.md Step 0). Tells that you're looking at **v2.x** code that needs migration:

| You see (v2) | v3 equivalent |
|---|---|
| `server.get_tools()` returning a **dict** (`tools["x"]`) | `server.list_tools()` returning a **list** (`next(t for t in tools if t.name=="x")`) — also `get_resources`/`get_prompts`/`get_resource_templates` → `list_*` |
| `main.mount(sub, prefix="sub")` | `main.mount(sub, namespace="sub")` |
| `FastMCP(host=, port=, log_level=, debug=, sse_path=...)` | those kwargs removed — pass transport options to `mcp.run(transport="http", host=..., port=...)` |
| decorated result used as a component object (`.name`/`.description`) | decorators **return the original function**; set `FASTMCP_DECORATOR_MODE=object` (deprecated escape hatch) or refactor |
| prompts returning raw `{"role":..., "content":...}` dicts | `fastmcp.prompts.Message` objects or plain strings (raw dicts no longer coerced) |
| `enabled=` on a decorator | server-level `mcp.enable()` / `mcp.disable()` (see `architecture.md`) |
| `WSTransport` | `StreamableHttpTransport` |
| auth provider auto-loading `client_id`/`client_secret` from env | pass them explicitly (e.g. from `os.environ`) |
| tool meta under `_fastmcp` | `fastmcp` (metadata always included now) |
| `FASTMCP_SHOW_CLI_BANNER` | `FASTMCP_SHOW_SERVER_BANNER` |

**Security note:** FastMCP 2.x has known unpatched CVEs — when the user can choose, recommend **3.2.0+**. If the user is pinned to v2 and cannot upgrade, write v2-correct code (the older `get_*`/`prefix=` forms) rather than v3 APIs, and say so explicitly.

Always confirm a renamed symbol against `gofastmcp.com` before generating code if there's any doubt — this list captures the common cases, not every change.
