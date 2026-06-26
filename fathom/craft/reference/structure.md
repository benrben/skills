# Craft · Structure — deep reference

The depth behind `../STRUCTURE.md`. Read on demand. All examples are neutral pseudocode; the originals (Java — a Cartesian point, a fuel gauge, a SQL-builder class, an EJB bank) are in *Clean Code* ch. 6, 8, 10, 11, 12. Where the original uses SQL, sockets, or a framework container, this reference describes the idea in prose and keeps the pseudocode abstract — the structural lesson never depends on the transport.

## Data abstraction — hiding is about abstraction, not accessors

Two interfaces for the same data. The first announces its storage; the second hides it.

```
// exposes representation — caller now depends on "stored as x and y"
interface Point: getX(); getY(); setX(v); setY(v)

// hides representation — could be rectangular, polar, or neither; caller can't tell
interface Point:
    getX(); getY()                 // read either coordinate independently …
    setCartesian(x, y)             // … but set them together, as one atomic move
    getR(); getTheta()
    setPolar(r, theta)
```

The second interface also *enforces a policy* (you may read a coordinate alone, but you must set both together) — that policy is behaviour the interface hides. That is **depth**: the caller learns a small, meaningful surface and the storage stays free to change. Wrapping each private field in a trivial getter/setter buys none of this — it is the exposed version with a function-shaped lid.

## Data/object anti-symmetry — the two are opposites

The same problem (areas of shapes) written both ways shows the trade exactly.

```
// DATA + PROCEDURES: shapes are dumb records; one function knows them all
type Square = { side }
type Circle = { radius }
function area(shape):
    switch typeof shape:
        case Square: return shape.side * shape.side
        case Circle: return PI * shape.radius * shape.radius
// add a new OPERATION (perimeter): add one function, touch no shape.  EASY
// add a new TYPE (Triangle):        edit area() and every other operation. HARD

// OBJECTS: each shape owns its behaviour; no central function
class Square:  area() = side * side
class Circle:  area() = PI * radius * radius
// add a new TYPE (Triangle):        add one class, touch nothing else.    EASY
// add a new OPERATION (perimeter):  add a method to every shape class.    HARD
```

The two "easy"s and two "hard"s are mirror images. Choose the side whose *easy* matches the change you expect. A **hybrid** — fields exposed *and* significant behaviour — gets both "hard"s and no "easy"; it is the worst of both worlds, and a sign the author wasn't sure whether they needed protection from new functions or from new types.

In Fathom: this choice sets what the seam makes cheap, so it is an `../INTERFACE-DESIGN.md` decision, not a detail. Naming the expected axis of change *is* the design.

## The Law of Demeter and the train wreck

A train wreck is a chain of getters that walks the object graph:

```
// the caller knows the whole map: context → options → directory → path
outputDir = ctxt.getOptions().getScratchDir().getAbsolutePath()
```

Splitting it across lines doesn't fix it — the function still knows every link, so any structural change to that path breaks it. The real fix is **tell, don't ask**: figure out *why* you wanted the value (here: to make a scratch file), and ask the nearest object to do that, hiding its own internals.

```
// craft: ctxt hides options/dir/path entirely; the chain is gone
stream = ctxt.createScratchFileStream(fileName)
```

Mapping to the spine: the chain is module A reaching *through* B's interface into B's internals — a **`leaksTo`** edge, which fires the **`leaky-seam`** signal. The Demeter fix is to *deepen the intermediate module* so callers cross its interface instead of bypassing it. The leak closes because the knowledge moved behind the seam where it belongs.

Caveat worth keeping: Demeter is about **objects**. If `ctxt`, options, and dir are genuinely public **data structures** (no behaviour to hide), navigating them violates nothing — the "violation" dissolves into the object-vs-data choice. The smell is real only when the things in the chain are supposed to be hiding their innards.

## Boundaries — the wrapper IS a port, the satisfier IS an adapter

A broad third-party type (say a library's map/collection type, or an external service client) handed around your system is a liability: it offers callers more than you want, and couples every call site to that library. Wrap it.

```
// smell: the raw foreign type travels everywhere; every holder has full power,
//        and a change to the library's interface is N edits across the system
foreignMap : ThirdPartyMap<Sensor>          // passed to many callers

// craft: one module owns the foreign type; the rest of the system sees YOUR interface
class Sensors:                               // ← this is a PORT (your interface)
    private store : ThirdPartyMap<Sensor>    // the foreign type is hidden inside
    getById(id) -> Sensor: return store.lookup(id)
    // no method returns or accepts the raw foreign type
```

`Sensors` is the **port**; a class that satisfies it is an **adapter**. The two `DEEPENING.md` boundary categories differ only in what's behind the port:

- **Category 4 — true external** (a provider you don't control). Production adapter talks to the real service; **test adapter is a mock**. The deep module owns the logic; the external call is injected.
- **Category 3 — remote but owned** (your own service across a network). Production adapter uses the transport; test adapter is in-memory. Same shape, different ownership.

Seam discipline (`LANGUAGE.md`): a port with only a production adapter is a **hypothetical** seam — indirection, not leverage — until a second adapter (usually the test one) makes it real. Don't define the port for a single implementation.

**Learning tests** pin the dependency's behaviour cheaply: you write tests that call the third-party API the way you intend to use it, capturing what you learned. When the dependency releases a new version, re-running them tells you instantly whether your adapter's assumptions still hold. And when the far side of a boundary doesn't exist yet, **define the interface you wish you had** and bridge to reality with an adapter later — your code stays readable and you gain a seam for testing with a fake meanwhile.

## Classes — small by responsibility, then cohesion, then organized for change

**Responsibility, not lines.** A class with one focused job is small even if it has many methods; a class with two jobs is too big even at five methods. The name test catches it: a class you can only name with a weasel word (`Manager`, `Processor`, `Super`), or can't describe in ~25 words without "and"/"or"/"but", is holding more than one responsibility.

**Cohesion → the deletion test.** When a class's fields fall into clusters that different methods use, the clusters are separate classes fused together. Split them.

```
// before: two field-clusters, two method-clusters, one class — low cohesion
class GameState:
    fields: board, mineCount, flagsLeft         // ← play cluster
    fields: timerStart, elapsed, isPaused        // ← clock cluster
    reveal(), flag()         touch only play cluster
    tick(), pause(), resume() touch only clock cluster

// after: each class maximally cohesive; the seam between them is now explicit
class Board: board, mineCount, flagsLeft;  reveal(); flag()
class Clock: timerStart, elapsed, isPaused; tick(); pause(); resume()
```

Cohesion is the Fathom **deletion test**: delete `Board` and a real lump of concentrated game logic goes with it; delete the fused `GameState` and it scatters into the two things it was loosely holding. Low cohesion at large size is the **`large-class`** signal. (Note the chain reaction from `FUNCTIONS.md`: breaking a big function into small ones tends to *promote* shared locals into fields, which lowers cohesion, which reveals the class that wanted out. Splitting functions and splitting classes are the same refinement.)

**OCP — open for extension, closed for modification.** A class that must be *opened* to add each new variant puts every existing variant at risk. Restructure so each variant is its own small unit behind a shared abstraction; a new variant is then a new unit, and nothing that already works changes.

```
// before: one class, opened and re-tested for every new statement kind
class QueryBuilder:
    build(kind, ...):
        switch kind: case CREATE: ...; case SELECT: ...; case INSERT: ...
        // adding UPDATE means editing this class — risk to CREATE/SELECT/INSERT

// after: a closed set; adding a kind drops in a new class, edits nothing existing
abstract class Query:  abstract generate()
class CreateQuery extends Query: generate() = ...
class SelectQuery extends Query: generate() = ...
class InsertQuery extends Query: generate() = ...
// later: class UpdateQuery extends Query  ← new file, no other code touched
```

*(Clean Code's version is a SQL-string builder; the structural point is independent of SQL — read `generate()` as "produce the variant-specific output." The lesson is the closed set, not the strings.)*

**DIP — depend on abstractions.** A class that depends on a volatile concrete (an external price feed, a clock, a device) is hard to test and hostile to substitution. Depend on an injected interface instead.

```
// before: hard-wired to a volatile concrete — test answer changes every minute
class Portfolio:
    value(): price = ExternalPriceFeed.lookup(symbol); ...

// after: depends on an abstraction, supplied from outside (DIP + injection)
interface PriceSource:  priceOf(symbol) -> Money
class Portfolio(source: PriceSource):           // injected
    value(): price = source.priceOf(symbol); ...
// test injects a fixed stand-in: priceOf("MSFT") -> 100, assert total == 500
// production injects the real feed
```

DIP is the principle, **injection** is the mechanism, **two adapters** (the fixed test source + the real feed) is the evidence the seam is real.

## Systems — separate construction from use

The smell is construction logic smeared through runtime code:

```
// smell: lazy-init hard-wires this object to one concrete dependency, makes the
//        null-path a test burden, and scatters wiring across the whole app
getService():
    if service == null: service = new ConcreteService(...)   // which is right? always?
    return service
```

Pull all construction to one side — a `main`-side composition step or a factory — and let the application receive fully-built collaborators. Every dependency arrow then points *toward* the application, away from construction; the app never knows how its parts were made.

```
// craft: the application is handed its dependencies; it does no wiring
function main():
    source  = choosePriceSource(config)       // construction lives here
    app     = Application(source)              // …and is injected in
    app.run()                                  // runtime logic only, downstream
```

This is `DEEPENING.md`'s **injection**: a deep module takes its ports and adapters from outside rather than reaching for them. And it keeps the architecture able to **grow** — a naively-simple-but-decoupled wiring ships today and accretes depth where load later demands it, the system-scale version of `MINIMALISM.md`'s marked ceiling. *(Clean Code contrasts a heavyweight container that forces construction concerns into every business object against plain injected objects; the framework specifics are incidental — the move is "construction on one side, use on the other.")*

## Emergence — the four rules, and why the order is load-bearing

```
1. Runs all the tests      → review/code gate + TESTS.md   (interface is the test surface)
2. No duplication          → the `duplication` signal      (the one Fathom measures)
3. Expresses intent        → NAMING.md + FUNCTIONS.md      (rule, checked by a human)
4. Minimal classes/methods → MINIMALISM.md                 (lowest priority of the four)
```

Tests come first because rules 2–4 are *refactoring*, and refactoring is only safe when a test net catches a slip. Dedupe before expressiveness because a duplicated concept can't be named in one place until it *is* one place. Minimize last, and never against the three above — and never by fragmenting a deep module into shallow pieces (`MINIMALISM.md`'s second forbidden erosion). Removing duplication and consuming a deep module instead of re-rolling it are the same move seen from two angles.

## Concurrency — structure only (described, never coded here)

Concurrency bugs live in *timing*, not in the text of a line, so pseudocode would mislead — these are stated in prose, as `../STRUCTURE.md` does:

- **Separate thread-management from thread-ignorant logic** (SRP). The ignorant part — most of the system — then tests as plain single-threaded code.
- **Limit and protect shared mutable data.** Fewer mutation sites means fewer guards to forget and fewer suspects for a non-repeatable failure.
- **Prefer copies / independent threads.** A thread that shares nothing has nothing to synchronize wrong; copy cost usually beats a missed lock.
- **Know the classic models** — producer–consumer, readers–writers, dining-philosophers. Naming the shape you're in tells you which hazard (deadlock, livelock, starvation) to defend against.

Mostly a `rule` + this reference; not a measured signal.

## See also

- `../STRUCTURE.md` — the rules + checklist (the `review` craft pass); the signal/[design]-candidate split.
- `../DEEPENING.md` — categories 3 & 4 (boundaries = ports/adapters) and injection (DI) in operational form.
- `../INTERFACE-DESIGN.md` — object-vs-data and seam placement when designing the interface twice.
- `../MINIMALISM.md` — how little behind the seam; minimal classes without fragmenting a deep module.
- `../SMELLS.md` — the structural heuristics (G6, G14, G34, G36) that become deepening candidates.
- Adjacent craft: `../ERRORS.md` (error modes ∈ interface), `../TESTS.md`, `../FUNCTIONS.md` (a god function is a missing module).
