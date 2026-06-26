# Craft · Error Handling

The **craft** layer is the altitude *below* `LANGUAGE.md` and `MINIMALISM.md`: how to write the implementation **behind a seam** so it reads cleanly, not just so it's deep. This doc is the error-handling slice. Drawn from *Clean Code* ch. 7. Language-agnostic — exceptions, result/option types, error values, whatever your language hands you for failure.

The pivot the rest of the suite leans on: **a module's error modes are part of its interface, not a private detail of its implementation.** `LANGUAGE.md` already defines an interface to include "error modes"; this doc is where that promise is honoured in the code behind the seam.

**Read by:** `code` (writing failure behind a fixed interface — §4–5 build it, §6 tests it), `review` (the craft pass), `design` (every interface's output already lists its error modes — §3 specifies them; this doc is how those modes are realized).

## Where this sits in the suite

- **Depth / seam** (`LANGUAGE.md`) decides *what the interface is* — and the interface **includes the error modes**. A caller must know how a module fails to use it correctly, exactly as it must know the types and the ordering.
- **Minimalism** (`MINIMALISM.md`) decides *how little* implementation sits behind it — error handling included; don't build recovery paths for failures that can't occur (YAGNI).
- **This doc** decides *how well* the failure path reads, and keeps it from leaking out of the seam into every caller.

Error handling is implementation — until it widens the interface. The moment a failure forces every caller to wrap, check, and nest, the error path *is* the interface, and a bad one. These rules keep the failure path legible behind the seam and keep its shape from rippling outward. When the right fix is a new failure dependency injected as a **port** with a test **adapter**, that's not a craft fix — it's a deepening, and it belongs to `design` (see `../DEEPENING.md` categories 3 & 4).

## The rules — each with its *why*

**Prefer exceptions (or result/option types) to returned error codes.** Signal failure with your language's error mechanism, not a status code the caller must remember to check. *Why:* a returned code forces the caller to test-and-nest at the call site immediately, tangling the failure path into the happy path; an exception or a result type lets the normal logic read straight down and the handling sit apart.

```
// smell: the caller must check, and the next caller, and the next
code = device.shutdown()
if code == OK:
    code = device.eject()
    if code == OK: ...

// craft: the happy path reads straight; failure is handled in one place
try:
    device.shutdown()
    device.eject()
catch error:
    handle(error)
```

**Write the try-catch-finally first.** When a piece of code can fail, write its `try`/`catch`/`finally` *before* the body — define the scope of the failure up front. *Why:* the `try` block is a transaction: it must leave the program in a consistent state no matter where it throws. Writing the failure scope first forces you to decide what "consistent" means before you've written anything that has to maintain it — like writing a test first (see `TESTS.md`).

**Keep the failure path from rippling across the system.** Don't let one module's error signature force a change through every caller of every caller. *Why:* this is the lesson behind Java's *checked exceptions* — generalized: when the way a module fails is welded into the type signature of everything above it, adding a new failure mode at the bottom breaks the whole chain, even code that only passes the failure through. An error mode belongs in the interface, but the *propagation* of one deep failure must not become an edit at N levels. Catch where you can act; re-raise (or wrap) where you can't — don't thread the raw signature through.

**Provide context with every error.** An error must carry what operation failed and what intent it was serving — enough to locate the source and the meaning, not just the type. *Why:* "null pointer" tells you nothing; "could not archive order 4117 while closing the billing period" tells you where to look and why it mattered. The catch site is usually too far from the failure to reconstruct that on its own — attach it where the failure happens.

**Define exception types around how the *caller* will catch them.** Classify failures by how callers will *handle* them, not by where they came from or what library raised them. *Why:* if three distinct exception types all get caught and handled identically, they were one error mode wearing three names — collapse them. The caller's catch blocks are the real taxonomy; design the types to match it, and one clean handler replaces a pile of near-duplicate ones.

```
// smell: three types, one identical response — the caller can't tell them apart usefully
try: port.open()
catch DeviceResponseError as e:    report(e)
catch ATM1212UnlockedError as e:   report(e)
catch GMXError as e:               report(e)

// craft: wrap them at the seam into the one mode the caller actually distinguishes
try: port.open()                   // adapter wraps lower failures into PortDeviceFailure
catch PortDeviceFailure as e:      report(e)
```

**Define the normal flow with a Special Case object — don't scatter special-case checks.** When the absence or exception *is* a normal case, give it an object that handles the case, so the mainline code never branches for it. *Why:* a check-for-the-weird-case sprinkled through the caller (`if (expenses != null) total += expenses.getTotal() else total += perDiem`) is the special case bleeding into every site; a Special Case object (a `PerDiemMeal` whose `getTotal()` returns the per-diem) absorbs the branch so the caller stays one straight line. This is the *Special Case* pattern: the client code does its thing, and the object it talks to handles the exceptional behaviour itself.

**Don't return null.** A method that can return null hands every caller a missing-check it will forget. *Why:* one absent `if (x != null)` is a crash waiting at runtime; returning an **empty collection**, an **option/result type**, or a **Special Case object** removes the check entirely — there is nothing to forget. Returning null is creating work (and a failure mode) for everyone above you.

```
// smell: every caller must guard, forever
items = getItems()
if items != null:
    for item in items: total += item.price

// craft: empty collection — the loop just runs zero times
for item in getItems():            // never null
    total += item.price
```

**Don't pass null.** Passing null *into* a method is worse than returning it — now the failure is on the caller's side and the method must defend against an argument that should never have existed. *Why:* there's no clean way to handle a null argument; you either crash, or litter the method with guard clauses for an input your own callers should never have produced. Forbid it at the boundary and the body stays clean.

## How you actually get there

You rarely get the failure path right first try. Write the `try`/`catch`/`finally` scope first so the transaction is defined, get the happy path working under tests, then refine the failure path: collapse exception types down to what callers actually distinguish, attach context at each throw, replace returned nulls with empty collections or Special Case objects, and pull recurring null-checks out of the callers. This is the same successive refinement the rest of craft uses (see `../DEEPENING.md`), applied to the path most code leaves ragged.

## Checklist (the `review` craft pass runs this)

- [ ] Failure signalled by exceptions / result types, not returned error codes
- [ ] The `try`/`catch`/`finally` scope defines a clean transaction (consistent state on every throw)
- [ ] No empty or swallowing `catch` — every failure is handled, re-raised, or wrapped, never silently dropped
- [ ] One deep failure's signature does not ripple through N pass-through callers
- [ ] Each error carries operation + intent (enough to locate source and meaning)
- [ ] Exception types match how the *caller* catches them; near-duplicate types collapsed
- [ ] A normal "exceptional" case is a Special Case object, not a branch repeated at every site
- [ ] Nothing returns null (empty collection / option / Special Case); nothing passes null

## Signals this feeds (spine)

`dead-code` fires on an **empty or swallowing catch** — a `catch` whose body neither handles, re-raises, nor wraps the failure is dead error-handling, and the scanner counts it. Measured by `craft_ingest` and surfaced by `archmap_scan_signals(map, family="craft")`.

The *subjective* parts above stay as this `rule` the skills apply — they are not auto-measured: whether an error carries *enough* context, and whether the exception types truly match the caller's catch blocks, are judgement calls `code` and `review` make against this doc, not metrics. One structural case escalates beyond a rule: a **recurring null-leak** — the same missing value forcing the same check across many callers — is both a `rule` to record on the map *and* a `design` candidate, because the durable fix (a Special Case object, or an interface that cannot return absence) changes the seam, not just the implementation.

## References

- `reference/errors.md` — the deep dive: the checked-exceptions argument generalized, the Special Case object worked through, wrapping third-party error APIs at the adapter, and more before/after transforms.
- Source chapter (original Java): *Clean Code* ch. 7, "Error Handling."
- Pairs with `FUNCTIONS.md` (error handling is *one thing* — isolate it in its own function) and `TESTS.md` (write the failure scope first, like a test). Where a failure dependency must be injected and faked, see `../DEEPENING.md` (categories 3 & 4) — the **port** + test **adapter** the deep module owns, which `code` builds in §4–5.
