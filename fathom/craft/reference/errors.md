# Craft · Error Handling — deep reference

The depth behind `../ERRORS.md`. Read on demand. All examples are neutral pseudocode; the originals (Java) are in *Clean Code* ch. 7.

## Why exceptions over error codes — the call-site cost

A returned error code is a fact the caller must check *now*, before doing anything else, at every call site. That check is what tangles the failure path into the happy path:

```
// codes: the logic disappears under the checking
if handle = openDevice(DEV1); handle != INVALID:
    type = getDeviceType(handle)
    if type != UNKNOWN:
        if closeDevice(handle) != OK:
            log("close failed")
    else:
        log("unknown type")
else:
    log("open failed")
```

Switching to exceptions lets the **algorithm** and the **error handling** become two separate things — each readable on its own:

```
try:
    handle = openDevice(DEV1)      // throws on failure
    process(getDeviceType(handle))
    closeDevice(handle)
catch DeviceError as e:
    log(e)                         // all failure, one place
```

This is the same move `../FUNCTIONS.md` makes when it says *isolate error handling* — error handling is one thing, so the function that does it should do nothing else.

## Write the try-catch-finally first

Treat the `try` block as a **transaction**: whatever happens inside, the program is left consistent. Writing the scope first forces that decision up front, before there's any body to maintain it — the same discipline as writing a test first (`../TESTS.md`).

```
// 1. start from the failure scope and what "consistent" means
function retrieveSection(name):
    try:
        return parse(load(name))
    catch error:
        return EmptySection()      // consistent state on failure, decided first

// 2. then fill in load()/parse() under tests; the contract is already fixed
```

If you write the body first and bolt the `try` on after, you tend to discover too late that a throw halfway through leaves something half-written. Start from the boundary of failure.

## The checked-exceptions lesson, generalized

Java's *checked exceptions* force every method to declare in its signature the failures it can propagate. That sounds like honesty — error modes in the interface — but it has a cost the rest of the suite must heed:

> When a low-level method adds a new failure mode, **every method between it and the catch site** must change its signature too — even methods that do nothing but pass the failure through. One change at the bottom ripples through N pass-through levels.

Generalized, language-independent rule: an error mode belongs in the **interface** (a caller must know how you fail), but the *propagation* of one deep failure must not become an edit at every level above it. The reconciliation:

- **Catch where you can act.** Handle the failure at the level that can actually do something about it.
- **Wrap where you can't.** At a seam, translate lower failures into the one mode this layer exposes (next section), so the raw signature stops there instead of threading upward.
- A module's *own* error modes are part of its interface; another module's failures it merely relays are not — don't widen your interface to re-declare them.

In Fathom terms: the place you wrap is a **seam**; the wrapper is the **adapter**; what you stop from rippling is the leverage you bought.

## Wrap third-party error APIs at the adapter

A library you call may throw a dozen exception types. Catching all dozen at your call site couples you to its taxonomy and repeats that coupling everywhere you call it. Wrap it once, at the **adapter**:

```
// craft: one adapter owns the third-party's failure vocabulary
class LocalPort:                   // adapter around the vendor ACMEPort
    function open():
        try:
            inner.open()
        catch DeviceResponseError as e:   raise PortDeviceFailure(e)
        catch ATM1212UnlockedError as e:  raise PortDeviceFailure(e)
        catch GMXError as e:              raise PortDeviceFailure(e)
```

Now every caller catches the **one** `PortDeviceFailure` it actually distinguishes, and the vendor's twelve types live in exactly one place. This is *define exception types around how the caller catches them* and *wrap a boundary* at once — and it is precisely the **port + adapter** shape a true-external dependency takes (`../DEEPENING.md` category 4): the deep module owns the logic and exposes one clean failure mode; the adapter absorbs the messy one.

## The Special Case object

When the exceptional case is actually a *normal* case, don't make the caller branch for it — give it an object that behaves correctly, so the mainline never sees a special case at all. This is Fowler's **Special Case** pattern.

```
// smell: the special case bleeds into the caller
total = base
expenses = employee.getMeals()
if expenses != null:                    // every caller repeats this
    total += expenses.getTotal()
else:
    total += perDiemDefault

// craft: the object handles its own special case
total = base + employee.getMeals().getTotal()
//   getMeals() always returns a MealExpenses;
//   the per-diem case is a PerDiemMeals whose getTotal() returns the per-diem
class PerDiemMeals:
    function getTotal(): return perDiemDefault
```

The caller went from a branch repeated at every site to one straight line. The branch didn't vanish — it moved *inside* the seam, paid once, exactly like burying a switch behind a factory in `../FUNCTIONS.md`.

## Don't return null — three replacements

Returning null hands every caller a check it will eventually forget; the missing check is a runtime crash. Pick the replacement by what's absent:

- **A collection → return it empty.** The caller's loop runs zero times; no guard needed.
- **A single value that may be absent → return an option/result type**, so absence is in the type and the compiler/reader can't ignore it.
- **A value with sensible default behaviour → return a Special Case object** (above).

```
// smell
employees = getEmployees()
if employees != null:
    for e in employees: pay(e)

// craft: getEmployees() returns an empty list, never null
for e in getEmployees():
    pay(e)
```

When a *language API forces* null on you (a lookup that returns null on miss), wrap it so the null stops at the wrapper — return the empty/option/special-case form outward.

## Don't pass null

Passing null *in* is worse: the failure is now upstream of the method, and there is no clean defence inside it. Guard clauses (`if (a == null) throw …`) only convert a silent crash into a louder one; assertions document intent but don't make the call legal. The real fix is upstream — **forbid null at the boundary** so the body never has to consider it. A method whose callers never pass null needs no null-handling, and that absent code is the cleanest code.

## A recurring null-leak is a design candidate, not just a rule

One forgotten null-check is a bug. The *same* missing value forcing the *same* check across many callers is structural: the interface lets absence escape, and every caller pays. That escalates past a `rule`:

- Record the convention as a `rule` on the map (the subjective "return empty / special-case here" guidance), **and**
- Raise a `design` candidate — because the durable fix (a Special Case object, or an interface that cannot return absence) **changes the seam**, not just the implementation behind it. The deletion test applies: if pushing the absence-handling inside the module makes the checks vanish from N callers, the module was the wrong shape.

## See also

- `../ERRORS.md` — the rules + checklist (the `review` craft pass).
- `../FUNCTIONS.md` — *isolate error handling*: handling is one thing, so its function does only that.
- `../TESTS.md` — write the failure scope first, the way you write a test first.
- `../DEEPENING.md` — categories 3 & 4: the **port** + test **adapter** a failure dependency takes, which `code` builds in §4–5 and asserts at the interface in §6.
