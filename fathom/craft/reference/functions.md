# Craft · Functions — deep reference

The depth behind `../FUNCTIONS.md`. Read on demand. All examples are neutral pseudocode; the originals (Java) are in *Clean Code* ch. 3.

## "Do one thing" — the extract test

The reliable test for whether a function does one thing: try to extract another function from it.

- If you can pull out a chunk and give it a name that **describes what it does at a lower level of abstraction** (not just a restatement of the code), the original was doing *more* than one thing.
- If the only name you can give the extracted chunk merely **restates its implementation** (`doTheLoopThatAddsItems`), there was nothing to extract — it was already one thing.

A second tell: a function divided into **sections** — declarations, then initialization, then the main loop, then formatting — is almost always doing several things. One-thing functions don't have sections.

## One level of abstraction, and the Stepdown Rule

Think of the program as paragraphs. Each function states something at its level and **refers to the next level down**:

```
to renderPage we build the header, build the body, build the footer
  to build the header we …
  to build the body we …
```

Reading top to bottom should feel like descending a staircase one step at a time. When a function jumps two levels (policy + raw string surgery in the same body), the reader trips. Fixing it is just extraction.

## Switch statements → polymorphism

A `switch` does N things by nature, so it can't "do one thing." The discipline:

1. Allow a `switch` to appear **once**, and only to **create** objects.
2. Hide it behind a factory that returns an interface.
3. Everywhere else, callers hold the interface and let **polymorphism** dispatch — no repeated `switch`.

```
// smell: this switch (and its twin for every new operation) is copied across the system
function pay(employee):
    switch employee.type:
        case SALARIED:  return salariedPay(employee)
        case HOURLY:    return hourlyPay(employee)
        case COMMISSION:return commissionPay(employee)

// craft: the switch appears once, in a factory; everyone else calls employee.pay()
function makeEmployee(record):           // the ONLY switch
    switch record.type:
        case SALARIED:  return new SalariedEmployee(record)
        case HOURLY:    return new HourlyEmployee(record)
        case COMMISSION:return new CommissionedEmployee(record)
```

In Fathom terms: the factory is a **seam**, the concrete employees are **adapters**, and the repeated type-dispatch is the leverage you bought.

## Function arguments, in detail

Fewer is better — each argument is a fact the reader holds and a dimension the test must cover.

- **Niladic (0)** — ideal.
- **Monadic (1)** — two honest shapes: a **question** about the argument (`fileExists(path)`) or a **transform** of it into the return (`parse(text)`). A third, weaker shape is an *event* (the argument changes system state and there's no return) — make that obvious in the name. Avoid using an output argument to return the answer.
- **Dyadic (2)** — harder; justified when the two have a natural order or cohesion (`Point(x, y)`). When they don't, readers stumble over which comes first.
- **Triadic (3)** — avoid; ordering and meaning costs rise sharply.
- **Argument objects** — three or more values that travel together are a concept missing a name: `makeCircle(x, y, radius)` → `makeCircle(center, radius)`. Wrapping isn't cheating; the group *was* an object.
- **Argument lists** — uniform variadic args count as one argument (`format(template, ...args)`).

**Verbs and keywords.** Make the call read like a sentence: a monadic call is a verb/noun pair (`write(name)`); encoding the argument names into the function name removes order-guessing (`assertExpectedEqualsActual(expected, actual)`).

**Flag arguments — always split.** `render(isSuite)` is two functions wearing one name:

```
// smell
function render(isSuite): …

// craft
function renderForSuite(): …
function renderForSingleTest(): …
```

## Side effects & Command–Query Separation

A side effect is any change a function makes that its name doesn't advertise — mutating a field, mutating an argument, touching global/static state, initializing something on the sly. These create **temporal couplings**: callers must now call things in a hidden order.

```
// smell: checkPassword() also initializes the session — a hidden side effect
function checkPassword(user, pw):
    if hash(pw) == user.hash:
        Session.initialize()      // surprise!
        return true
    return false
```

CQS: a function either changes state (command, returns nothing) or reports state (query, changes nothing) — never both. Replace the ambiguous `if (set("username","bob"))` with `if (attributeExists("username")) setAttribute("username","bob")`.

## Isolate error handling

Error handling is one thing, so a function that does it should do *nothing else*: the keyword that starts the handling is the first thing in the function, and there's nothing after the handler ends.

```
// craft: delete() expresses only "delete, and handle failure"
function delete(page):
    try:
        deletePageAndReferences(page)
    catch error:
        logError(error)

function deletePageAndReferences(page):   // the actual work, one level down
    deletePage(page)
    registry.deleteReference(page.name)
    config.deleteKey(page.key)
```

Returning error *codes* instead forces the caller to check immediately and nest — the opposite of clean. (More in `../ERRORS.md`.)

## Worked example — "extract until you drop"

A long function that builds a page with setup/teardown, mixing levels and flags, becomes a handful of one-thing functions named at descending levels:

```
function renderPageWithSetupsAndTeardowns(pageData, isSuite):
    if isTestPage(pageData):
        includeSetupAndTeardownPages(pageData, isSuite)
    return pageData.getHtml()
```

Every remaining line is at one level of abstraction; each helper (`isTestPage`, `includeSetupAndTeardownPages`, …) is itself small and does one thing. You keep extracting until you cannot extract a function with a non-restating name — *then* you've dropped to one thing.

## See also

- `../FUNCTIONS.md` — the rules + checklist (the `review` craft pass).
- `../MINIMALISM.md` — the least implementation that still passes the interface tests, *behind* the fixed seam.
- `../ERRORS.md`, `../NAMING.md` — adjacent craft.
