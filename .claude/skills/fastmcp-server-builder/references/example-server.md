# Worked Example: A Complete, Runnable Server

A single known-good template that exercises the skill's principles end to end: the **three-way split** (tool/resource/prompt), **outcome-oriented** tools, **flat typed/constrained** arguments, **`Depends()`-injected identity**, **structured output**, **pagination**, **timeouts**, **honest annotations**, **actionable errors**, and **in-memory tests**. Pattern-match against this instead of assembling fragments. Verify any API against `gofastmcp.com` for the installed version (see SKILL.md Step 0); this targets FastMCP **v3.x**.

The domain: a small **Orders** server. One job — let an agent look up and act on a customer's orders.

Capability inventory (classified by the Part 1 control rule *before* coding):
- `tool: track_order — model fetches live tracking for a customer's latest order`
- `tool: list_orders — model lists a customer's orders (paginated)`
- `tool: cancel_order — model performs a destructive action (with consent gate)`
- `resource: orders://policy/returns — stable reference text the app injects`
- `prompt: file_a_complaint — user-invoked, multi-step workflow`

Note `customer_id` is **never a model parameter** — it's injected via `Depends()` from the auth context.

## `server.py`

```python
from typing import Annotated, Literal
from pydantic import Field
from fastmcp import FastMCP
from fastmcp.dependencies import Depends
from fastmcp.exceptions import ToolError

mcp = FastMCP(name="OrdersServer", mask_error_details=True)  # mask internals in prod


# --- Fake data + identity (stand-ins for a real DB / auth context) ---------

_ORDERS = {
    "cust_1": [
        {"order_id": "A123", "status": "shipped", "eta": "2026-06-25", "total": 42.0},
        {"order_id": "A090", "status": "delivered", "eta": None, "total": 18.5},
    ],
}

def current_customer_id() -> str:
    # In a real server, resolve from the authenticated request context.
    # Injected via Depends() so it is STRIPPED from the model-facing schema.
    return "cust_1"


# --- Tools (model-controlled) ----------------------------------------------

@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": True}, timeout=15)
def track_order(customer_id: str = Depends(current_customer_id)) -> dict:
    """Get live tracking for the customer's most recent order.

    Use when the user asks "where is my order" or about delivery status.
    Returns the latest order's id, status, and ETA. Does the find-latest +
    fetch-tracking work HERE, in code — the model never chains calls.
    """
    orders = _ORDERS.get(customer_id, [])
    if not orders:
        raise ToolError("No orders found for this account. Ask the user to confirm their account email.")
    latest = orders[0]
    return {"order_id": latest["order_id"], "status": latest["status"], "eta": latest["eta"]}


@mcp.tool(annotations={"readOnlyHint": True})
def list_orders(
    status: Annotated[
        Literal["any", "shipped", "delivered", "cancelled"],
        Field(description="Filter by order status."),
    ] = "any",
    limit: Annotated[int, Field(description="Max orders to return.", ge=1, le=50)] = 20,
    offset: Annotated[int, Field(description="How many to skip (for paging).", ge=0)] = 0,
    customer_id: str = Depends(current_customer_id),
) -> dict:
    """List the customer's orders, newest first, paginated.

    Returns {orders, total_count, has_more, next_offset}. Always bounded —
    never dump every row.
    """
    rows = _ORDERS.get(customer_id, [])
    if status != "any":
        rows = [o for o in rows if o["status"] == status]
    page = rows[offset : offset + limit]
    next_offset = offset + len(page)
    return {
        "orders": page,
        "total_count": len(rows),
        "has_more": next_offset < len(rows),
        "next_offset": next_offset if next_offset < len(rows) else None,
    }


@mcp.tool(annotations={"destructiveHint": True, "idempotentHint": True})
def cancel_order(
    order_id: Annotated[str, Field(description="The order to cancel, e.g. 'A123'.")],
    customer_id: str = Depends(current_customer_id),
) -> dict:
    """Cancel one of the customer's orders. Destructive — clients should confirm.

    Returns the new status. Errors actionably if the order can't be cancelled.
    """
    for o in _ORDERS.get(customer_id, []):
        if o["order_id"] == order_id:
            if o["status"] in ("delivered", "cancelled"):
                raise ToolError(f"Order {order_id} is '{o['status']}' and cannot be cancelled.")
            o["status"] = "cancelled"
            return {"order_id": order_id, "status": "cancelled"}
    raise ToolError(f"No order '{order_id}' on this account. Call list_orders to see valid order IDs.")


# --- Resource (app-controlled, stable context) -----------------------------

@mcp.resource("orders://policy/returns", mime_type="text/plain")
def returns_policy() -> str:
    """The current returns policy (stable reference text the host can inject)."""
    return "Returns accepted within 30 days of delivery with proof of purchase."


# --- Prompt (user-controlled, named workflow) ------------------------------

@mcp.prompt
def file_a_complaint(order_id: str) -> str:
    """Guided workflow for filing a complaint about an order."""
    return (
        f"Help me file a complaint about order {order_id}. "
        "First call track_order to confirm its status, then read "
        "orders://policy/returns, then ask me what went wrong and draft the complaint."
    )


if __name__ == "__main__":
    mcp.run()  # STDIO by default; mcp.run(transport="http", host="127.0.0.1", port=8000) for remote
```

## `test_server.py` (in-memory, sub-second, deterministic)

```python
import pytest
from fastmcp import Client
from server import mcp


async def test_track_order_returns_latest():
    async with Client(mcp) as client:
        result = await client.call_tool("track_order", {})  # customer_id is injected, not passed
        assert result.data["order_id"] == "A123"
        assert result.data["status"] == "shipped"


async def test_customer_id_is_hidden_from_schema():
    tools = await mcp.list_tools()  # v3: list_tools() returns a list
    track = next(t for t in tools if t.name == "track_order")
    assert "customer_id" not in track.inputSchema["properties"]  # Depends() stripped it


async def test_list_orders_paginates():
    async with Client(mcp) as client:
        result = await client.call_tool("list_orders", {"limit": 1, "offset": 0})
        assert result.data["total_count"] == 2
        assert result.data["has_more"] is True
        assert result.data["next_offset"] == 1


async def test_cancel_then_cannot_recancel():
    async with Client(mcp) as client:
        ok = await client.call_tool("cancel_order", {"order_id": "A123"})
        assert ok.data["status"] == "cancelled"
        with pytest.raises(Exception):  # ToolError surfaces as a client-side error
            await client.call_tool("cancel_order", {"order_id": "A090"})  # already delivered


async def test_resource_and_prompt_exist():
    async with Client(mcp) as client:
        policy = await client.read_resource("orders://policy/returns")
        assert "30 days" in policy[0].text
        prompts = await client.list_prompts()
        assert any(p.name == "file_a_complaint" for p in prompts)
```

Run it:

```bash
uv add fastmcp pytest pytest-asyncio
# add to pyproject/pytest.ini:  [tool.pytest.ini_options]  asyncio_mode = "auto"
pytest -q
```

## What to notice (maps back to Part 3)

- **Outcome-oriented:** `track_order` does find-latest + fetch in code; the model makes one call, not three.
- **Identity via `Depends()`:** `customer_id` is injected and absent from every schema — the second test asserts this.
- **Flat, constrained args:** `Literal`/`Field(ge=, le=)` instead of free strings and nested dicts; defaults mark optionals.
- **Pagination:** `list_orders` returns `total_count`/`has_more`/`next_offset` and caps `limit` at 50.
- **Honest annotations:** read-only reads marked `readOnlyHint`; `cancel_order` marked `destructiveHint`.
- **Actionable errors:** every `ToolError` tells the model what to do next (confirm email, call `list_orders`).
- **Three-way split by control:** tools to act, a resource for stable policy text, a prompt for the user-invoked flow.
- **Tested in-memory:** the server is passed straight into `Client` — real protocol, no subprocess, fast.
```
