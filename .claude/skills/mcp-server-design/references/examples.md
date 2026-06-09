# Before / After: Worked MCP Server Designs

Concrete redesigns showing the six principles in action. Pattern-match your own server against the closest example. Code is illustrative (function-signature level, like the source article) and language/SDK-agnostic — the principles transfer to TypeScript, FastMCP, the official SDKs, etc. Verify exact SDK syntax against current docs when you write real code.

Principle key: **P1** outcomes · **P2** flat args · **P3** instructions/errors · **P4** curate · **P5** naming · **P6** pagination.

---

## Example 1 — Order tracking (the canonical case)

**Goal the user has:** "Where's my order?"

### ❌ Before — endpoints exposed as tools

```python
get_user_by_email(email: str) -> dict
list_orders(user_id: str) -> list
get_order_status(order_id: str) -> dict
```

The agent must: load three tool descriptions, call `get_user_by_email`, hold the `user_id`, call `list_orders`, pick an order, hold the `order_id`, call `get_order_status`, then assemble an answer — three round-trips with every intermediate result sitting in context. (Violates P1, and the names are generic — P5.)

### ✅ After — one outcome-oriented tool

```python
def track_latest_order(email: str) -> dict:
    """Get the status of a user's most recent order.

    Use when the user asks where their order is or about delivery status.
    `email` must be lowercase. Returns a human-readable status summary,
    the order ID, carrier, and estimated arrival.
    """
    # internally: resolve user -> list orders -> get status, then summarize
    # returns e.g.:
    # {"summary": "Order #12345 shipped via FedEx, arriving Thursday",
    #  "order_id": "12345", "carrier": "FedEx", "eta": "2026-01-23"}
```

One call, the orchestration hidden in code, a resolved outcome returned. Applies **P1** (outcome), **P3** (docstring says when/how/what), **P5** (specific name), and **P4** (curated return, no raw dump).

---

## Example 2 — Gmail (reading, sending, drafting)

**Goals the user has:** find an email, read one, send one, save a draft.

### ❌ Before — the raw API, 1:1

```python
# Reading one email takes 2 tools + understanding nested types
messages_list(query: str, max_results: int) -> {"messages": [{"id": str, "threadId": str}], "nextPageToken": str}
messages_get(message_id: str, format: str) -> {"id": str, "snippet": str, "payload": {"headers": list, "body": {"data": str}}}

# Sending requires base64-encoding a MIME message by hand
messages_send(message: {"raw": str}) -> {"id": str, "threadId": str}   # raw = base64url RFC 2822

# Drafts wrap a nested message object
drafts_create(draft: {"message": {"raw": str}}) -> {"id": str, "message": {"id": str}}
```

Problems: the agent must construct `{"raw": base64(...)}` and dig values out of `payload.body.data`; arguments are nested; names are generic. (Violates P1, P2, P3, P5.)

### ✅ After — agent-first design

```python
def gmail_search(query: str, limit: int = 10) -> list:
    """Search the user's Gmail. Returns a list of matching messages with
    id, subject, sender, date, and a short snippet. Use to find emails
    before reading or replying."""
    # -> [{"id": ..., "subject": ..., "sender": ..., "date": ..., "snippet": ...}, ...]

def gmail_read(message_id: str) -> dict:
    """Read the full content of one email by id. Returns subject, sender,
    body (plain text), and a list of attachment names."""
    # -> {"subject": ..., "sender": ..., "body": ..., "attachments": [...]}

def gmail_send(to: list[str], subject: str, body: str, reply_to_id: str = None) -> dict:
    """Send an email. `to` is a list of recipient addresses. Pass
    `reply_to_id` to reply within an existing thread. Returns success
    and the new message id."""
    # server handles MIME/base64 internally
    # -> {"success": True, "message_id": ...}
```

What changed: **P2** — flat primitives (`to`, `subject`, `body`) replace nested `{"raw": ...}`; the server does the encoding. **P4** — `gmail_read` returns a clean `body`, not a nested `payload`. **P5** — `gmail_*` names. **P3** — docstrings explain when/how/what. Add **P6** to `gmail_search` if result sets get large (`has_more`, `next_offset`, `total_count`).

---

## Example 3 — Generalized: an issue tracker (illustrative)

A made-up "Acme" issue tracker, to show the principles on a fresh surface. Suppose the upstream API has ~20 endpoints (projects, issues, comments, labels, users, webhooks, ...).

### ❌ Before — everything exposed, generically named

```python
get(resource: str, id: str) -> dict           # one mega-tool, agent guesses `resource`
list(resource: str, filters: dict) -> list     # nested filters
create_issue(payload: dict) -> dict             # nested payload, generic name
update(resource: str, id: str, payload: dict)   # nested, generic
delete(resource: str, id: str) -> dict          # destructive, unlabeled
# ...15 more
```

Violates nearly everything: P1 (no outcomes), P2 (nested `filters`/`payload`, stringly-typed `resource`), P4 (too many tools, one mega-tool), P5 (generic names), and the destructive `delete` isn't flagged (hygiene).

### ✅ After — curated, outcome-oriented, persona-split

Scope to the **developer persona** and the jobs they actually do (file a bug, find my issues, comment, change status). Park admin/webhook management in a separate `acme-admin` server (**P4** split by persona).

```python
def acme_create_issue(
    project_key: str,
    title: str,
    description: str = "",
    priority: Literal["low", "medium", "high", "urgent"] = "medium",
    assignee_email: str = None,
) -> dict:
    """Create an issue in a project. `project_key` is the short key like
    'ACME'. Returns the new issue key and URL. Use when the user wants to
    file a bug or task."""
    # -> {"issue_key": "ACME-142", "url": ...}

def acme_list_my_issues(
    assignee_email: str,
    status: Literal["open", "in_progress", "done", "all"] = "open",
    limit: int = 25,
    offset: int = 0,
) -> dict:
    """List issues assigned to a user, newest first. Returns issues plus
    pagination metadata."""
    # -> {"issues": [{"issue_key": ..., "title": ..., "status": ..., "priority": ...}, ...],
    #     "has_more": True, "next_offset": 25, "total_count": 88}

def acme_add_comment(issue_key: str, comment: str) -> dict:
    """Add a comment to an issue. Returns success and the comment id."""
    # -> {"success": True, "comment_id": ...}

def acme_set_status(
    issue_key: str,
    status: Literal["open", "in_progress", "done"],
) -> dict:
    """Change an issue's status. Returns the issue key and its new status."""
    # -> {"issue_key": "ACME-142", "status": "in_progress"}
```

What changed: **P1** outcome-shaped tools for real jobs; **P2** flat args with `Literal` enums and defaults; **P4** four focused tools instead of twenty, admin split off; **P5** `acme_*` action names; **P6** pagination on the list tool; **P3** docstrings throughout. A destructive delete, if needed, would be a clearly-named, clearly-described `acme_delete_issue(issue_key)` — and you'd question whether the agent needs it at all.

---

## Reading the diffs

Across all three, the same moves recur:

1. **Collapse** call chains into one outcome tool, hiding orchestration in code (P1).
2. **Unwrap** nested arguments into flat, typed, defaulted primitives; never make the agent serialize (P2).
3. **Trim** returns to the fields that matter and **paginate** lists (P4, P6).
4. **Rename** generically-named tools to `service_action_resource` (P5).
5. **Document** when/how/what in every docstring and make errors recoverable (P3).

If your redesign doesn't make at least a couple of these moves, look again — most real servers need all of them.
