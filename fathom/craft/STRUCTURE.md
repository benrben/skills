# Craft · Structure

The **craft** layer is the altitude *below* `LANGUAGE.md` and `MINIMALISM.md` — but **structure** is the layer where craft reaches *up* and hands off to architecture. Everything else in `craft/` shapes the code behind a fixed seam; structure is about **where the seams go**: how data hides, where a boundary is wrapped, when a class has one responsibility, how a system is wired, and what "simple design" means once it's all assembled. Drawn from *Clean Code* ch. 6, 8, 10, 11, 12 (+ a short take on ch. 13). Language-agnostic — the moves are object/data, boundary, class, system, design, thread, whatever your language calls them.

**Read by:** `design` (the primary reader — shaping modules and interfaces: SRP/cohesion = depth, boundaries = seams, DI = injection), `code` (when a function turns out to be a missing module — pairs with `MINIMALISM.md`), `review` (the craft pass, when a smell is structural rather than local).

## Where this sits in the suite

- **Depth / seam** (`LANGUAGE.md`) is the vocabulary; **structure** is the craft that *produces* depth and *places* seams.
- **Minimalism** (`MINIMALISM.md`) decides how little sits behind a seam; structure decides whether the seam is in the right place at all.
- **Deepening** (`DEEPENING.md`) and **Interface Design** (`INTERFACE-DESIGN.md`) are the suite's structural moves; this doc is the *Clean Code* roots they grow from.
- The other craft docs (`FUNCTIONS`, `NAMING`, `ERRORS`, `TESTS`, `COMMENTS`) clean the implementation; **structure is the one craft doc that changes the boundary** — so its fixes are usually `design` candidates, not local edits.

When a structural problem here can't be fixed without moving the seam — a god class, a leaking boundary, a wired-in dependency — it is **not** a craft tidy-up. Hand it to `design`, which has `DEEPENING.md` and `INTERFACE-DESIGN.md` for exactly this.

## Objects & data (ch. 6) — hide implementation, and know which kind you have

**Hide implementation through abstraction, not accessors.** A module hides its data when its interface lets callers manipulate the *essence* of the data without knowing its form — not when it wraps every field in a getter/setter. *Why:* `getFuelTankCapacity()` + `getGallons()` exposes that fuel is stored as two raw numbers; `getPercentFuelRemaining()` hides the representation entirely, so it can change without breaking a caller. Pushing private variables out through accessors is exposure wearing a function's clothes — this is the heart of **depth** (`LANGUAGE.md`): leverage at the interface, not a thin skin over fields.

```
// shallow — the interface IS the representation; callers depend on the storage
interface Vehicle: getTankCapacityInLitres(); getLitresRemaining()
// deep — the representation is hidden; the caller learns one fact, not the storage
interface Vehicle: getPercentFuelRemaining()
```

**Know whether you have an object or a data structure — they are opposites.** Objects hide data and expose behaviour; data structures expose data and have no meaningful behaviour. *Why:* the choice decides what stays cheap to change. Procedural code over data structures makes it easy to add new *operations* (touch one place) but hard to add new *types* (touch every operation); object-oriented code makes it easy to add new *types* (one new class) but hard to add new *operations* (touch every class). Pick the side whose "easy" matches the change you expect — and don't build a **hybrid** (half data, half behaviour) that is hard to extend in *both* directions. In Fathom terms, the object/data choice is an `INTERFACE-DESIGN.md` decision: it sets what the seam makes cheap.

**Obey the Law of Demeter — talk to friends, not strangers.** A method should only call methods on: its own object, objects it created, objects passed to it, and objects it holds directly — not on objects *returned* by those. *Why:* a chain like `ctxt.getOptions().getScratchDir().getAbsolutePath()` (a **train wreck**) means one function knows the whole navigation map — context holds options, options hold a directory, a directory has a path. Change any link and every chain breaks. The fix is to *tell, don't ask*: ask `ctxt` to do the thing you wanted the path for (`ctxt.createScratchFileStream(name)`), so it hides its own internals.

In Fathom this is the **`leaky-seam`** signal made concrete. A train wreck is a module reaching *through* another module's interface into its internals — exactly a `leaksTo` edge. The Demeter fix (a tell-don't-ask method that hides the chain) is *deepening the intermediate module* so the leak closes. (Caveat: Demeter applies to *objects*; if every link is genuinely a public data structure, navigating it isn't a violation — which is itself the object-vs-data choice resurfacing.)

## Boundaries (ch. 8) — wrap third-party code so a raw type never leaks

**Never let a third-party type travel through your system.** Wrap a foreign interface (a library map type, an external client, an SDK object) inside one module of yours, and pass *your* type around — not theirs. *Why:* a broad third-party interface gives callers more power than you want (any holder of a raw map can `clear()` it) and couples every call site to that library, so the day its interface changes you have N edits, not one. Keeping it behind your own interface means the boundary "is able to evolve with very little impact on the rest of the application."

This is **`DEEPENING.md` categories 3 and 4** in their birthplace. The wrapper *is* a **port**; the thing that satisfies it *is* an **adapter**:

- **True external** you don't control (a payments or messaging provider) — DEEPENING category 4: define the port at the seam, inject a real adapter in production and a **mock** adapter in tests.
- **Remote but owned** (your own service across a network) — DEEPENING category 3: same shape, an in-memory adapter for tests and a transport adapter for production.

Remember the seam discipline: **two adapters make a real seam, one makes a hypothetical one** (`LANGUAGE.md`). A boundary you control with exactly one (production) implementation is just indirection until the test adapter justifies the port.

**Use learning tests to pin a dependency's behaviour.** Instead of learning a third-party API *inside* production code, write small tests that exercise it the way you intend to use it. *Why:* you had to learn the API anyway, so the tests cost nothing — and they keep paying: when a new version of the dependency ships, the learning tests tell you immediately whether its behaviour still matches what your adapter assumes. A clean boundary is *defined* by these tests.

**Define the interface you wish you had, even when the other side doesn't exist yet.** When code on the far side of a boundary is unknown or unbuilt, write your own interface for what you want, and bridge to reality with an adapter once it lands. *Why:* it keeps your code readable and focused on its own job, and it gives you a **seam** for testing with a fake in the meantime — the boundary stops being a blocker.

## Classes (ch. 10) — small by *responsibility*, organized for change

**Small means few responsibilities, not few lines.** A class is too big when it has more than one *reason to change* — even a five-method class is too big if those methods answer to two different forces. *Why:* "lines" is the wrong ruler at this altitude; a class with one focused job is a tool in a labelled drawer, while a class with several is a junk drawer you must wade through. Tell: if you can't name the class without a vague word (`Manager`, `Processor`, `Super`) or describe it in ~25 words without "and"/"or"/"but", it holds too much.

**Single Responsibility — one reason to change.** A module should have exactly one axis along which a future requirement will force it to change. *Why:* two reasons to change in one class means a change driven by reason A risks breaking the code that serves reason B, and the two get retested together forever. Splitting them (e.g. version-tracking out of GUI-management) yields units that change independently — and one of them is often reusable on its own. SRP is the `design` reading of this whole doc: a responsibility *is* what a deep module hides.

**Cohesion is `depth` plus the deletion test.** A class is cohesive when its methods and variables hang together as a whole — most methods touch most fields. *Why:* when functions cluster around a shared subset of variables, "there is at least one other class trying to get out." Cohesion is exactly the Fathom **deletion test** (`LANGUAGE.md`): a cohesive class, deleted, takes a real lump of concentrated complexity with it; an incohesive one scatters into the pieces it was loosely holding. Low cohesion + large size is precisely the **`large-class`** signal — split it until each piece is cohesive.

```
// incohesive — two clusters of fields that don't touch; two classes wearing one name
class Report:
    fields: rows, pageWidth, columnGap         // ← formatting cluster
    fields: dbHost, retries, lastSyncTime       // ← fetching cluster
    methods: render(), paginate() use only the first cluster
             fetch(), reconnect() use only the second
// cohesive — one responsibility each; the seam between them is now explicit
class ReportFormatter: rows, pageWidth, columnGap; render(); paginate()
class ReportSource:    dbHost, retries, lastSyncTime; fetch(); reconnect()
```

**Organize for change: open for extension, closed for modification (OCP).** Structure a class so a new feature is a *new* derivative, not an edit to existing code. *Why:* opening a working class to add a case risks every other case in it; if each statement-kind is its own small class behind a shared abstraction, adding one more is dropping in a new class and changing nothing that already works. The spur to do this is real change arriving — don't pre-split a class that is logically complete and stable. *(Clean Code grounds this in a SQL-builder class that splits per statement type; the principle is language- and domain-neutral — substitute any class that has grown one `if`-per-variant.)*

**Isolate from change: depend on abstractions (DIP).** A class that depends on a volatile concrete detail (an external price feed, a clock, a device) should depend instead on an *interface* that the detail implements, injected in. *Why:* depending on the concrete thing makes the class hard to test (the answer changes every five minutes) and hostile to substitution; depending on an abstraction lets a test supply a fixed stand-in and lets production swap implementations freely. DIP is the *principle*; **dependency injection** (next section) is the *mechanism*; **two adapters** is the *evidence* the seam is real.

## Systems (ch. 11) — separate construction from use, keep room to grow

**Separate constructing the system from using it.** The startup process that builds objects and wires dependencies together is a distinct concern from the runtime logic that uses them — don't interleave them. *Why:* lazy-init idioms (`if x is null: x = new ...`) scattered through the code hard-wire each object to one concrete dependency, make those paths a testing burden, and spread the wiring strategy across the whole app with no single place to change it. Move construction to one place (a `main`-side composition step or a factory) so the application receives fully-built collaborators and never knows how they were made — all dependency arrows point *toward* the application, away from construction.

**Inject dependencies (DI / IoC).** A module should not instantiate its own dependencies; it should receive them (via constructor or setter) from an authoritative wiring layer. *Why:* an object that builds its own dependencies has taken on a second responsibility (its own construction) and bound itself to one implementation; passing that job to a wiring layer inverts the control, restores SRP, and makes every dependency a seam a test can fill. This is the **injection** move named in `DEEPENING.md` — the same mechanism by which a deep module takes its ports and adapters from outside rather than reaching for them.

**Keep the architecture able to grow.** You cannot get a system's architecture "right the first time"; a cleanly separated system can grow from simple to sophisticated as real stories arrive. *Why:* software, unlike a building, can be radically restructured later *if* its concerns are decoupled — so a "naively simple but nicely decoupled" architecture that ships today beats a big design up front that resists the change you'll actually need. Use the simplest thing that works at each level, and let depth accrete where load demands it. (This is `MINIMALISM.md`'s marked-ceiling idea at system scale: build the simple thing, record where it will need to grow.)

## Emergence (ch. 12) — the four rules of simple design, mapped to their homes

A design is "simple," in priority order, when it: **(1)** runs all the tests, **(2)** contains no duplication, **(3)** expresses the intent of the author, **(4)** minimizes the number of classes and methods. Each rule already has a home elsewhere in Fathom — simple design is the thread that ties the suite together:

1. **Runs all the tests** → the **`review` / `code` gate** and `TESTS.md`. A design you can't verify isn't simple, it's unverified. Testability *pushes* toward small, single-responsibility, loosely-coupled modules — the same place depth pushes. **The interface is the test surface** (`LANGUAGE.md`).
2. **No duplication** → the **`duplication` signal**. Duplication is "the primary enemy of a well-designed system"; folding it into one place is the same move as consuming a deep module instead of re-rolling it (`MINIMALISM.md`'s ladder). This is the one rule Fathom *measures* (`archmap_scan_signals`).
3. **Expresses intent** → `NAMING.md` and `FUNCTIONS.md`. Good names, small functions, standard pattern nomenclature, expressive tests — the craft of being read. Enforced as a `rule`, by a human (taste isn't faked as a metric).
4. **Minimal classes/methods** → `MINIMALISM.md`. The *lowest-priority* rule: keep counts low — but never at the cost of the three above, and never by fragmenting a deep module into shallow pieces (`MINIMALISM.md`'s second forbidden erosion). "Fewest files" means *don't split a deep module*, never *split a deep module to make pieces small*.

The ordering matters: tests first, then dedupe, then express, then minimize. Refactoring (rules 2–4) is safe only *because* rule 1 holds.

## Concurrency (ch. 13) — a short structural note

Concurrency is mostly a **`rule`** and a reference, not a measured signal — but it has a few load-bearing structural moves. (All described in prose; concurrency code is exactly the kind Fathom keeps out of pseudocode, because the bug is in the timing, not the text.)

**Keep concurrency code separate (SRP again).** Thread-management code has its own lifecycle and its own failure modes; isolate it from thread-ignorant logic so each can be understood and tested alone. *Why:* mixing the two means every concurrency bug is tangled with application logic, and the thread-ignorant part — which is most of the system — can't be tested as plain single-threaded code.

**Limit and protect shared mutable data.** Severely restrict how many places can touch shared state, and guard the critical sections that remain. *Why:* every additional place that mutates shared data is another place to forget a guard, another duplication of guarding effort, and another suspect when a non-repeatable bug appears.

**Prefer copies and independent threads.** Avoid sharing in the first place — give each thread its own copy or its own unshared subset of the work, and merge results at the end. *Why:* a thread that shares nothing behaves like the only thread in the world, with no synchronization to get wrong; the cost of copying is usually less than the cost of a missed lock.

**Know the classic models.** Producer–consumer, readers–writers, and dining-philosophers cover most real concurrency problems; learn them so you recognize the shape you're in. *Why:* deadlock, livelock, and starvation are properties of these shapes — naming the shape tells you which hazard to defend against.

## How you actually get there

Structure is the product of refinement, not first drafts — and at this altitude the refinement *moves the seam*, so it is `design`'s job, executed under tests. Get the behaviour working and covered, then: extract the class that's trying to get out, wrap the boundary, inject the dependency, split on the responsibility — each step green before the next. The famous worked examples in *Clean Code* (a one-function prime printer becoming three cohesive classes; a SQL builder becoming a closed set per statement type) were all done as "a myriad of tiny changes," each verified, never a rewrite. When a structural fix changes an interface, that's the signal it belongs to `design` with `DEEPENING.md` / `INTERFACE-DESIGN.md`, not to a local craft pass.

## Checklist (the `review` craft pass runs this)

- [ ] Data is hidden behind abstraction, not pushed out through accessors (depth, not a field-skin)
- [ ] Object vs data structure chosen deliberately; no hard-to-extend hybrids
- [ ] No train wrecks — Law of Demeter holds (tell, don't ask); no reaching through a module's interface (`leaksTo`)
- [ ] Third-party / external types are wrapped behind your own interface; not passed around raw
- [ ] Real seams have two adapters (prod + test); single-adapter "seams" flagged as mere indirection
- [ ] Classes small by *responsibility* — one reason to change; nameable without weasel words / in ~25 words
- [ ] Cohesive — methods cluster on shared fields; low-cohesion-plus-large-size split (`large-class`)
- [ ] New features extend rather than modify (OCP); volatile concretes depended on via injected abstractions (DIP)
- [ ] Construction separated from use; dependencies injected, not self-instantiated
- [ ] Concurrency code isolated; shared mutable state minimized and guarded

## Signals this feeds (spine)

`large-class` (low cohesion at large size — a class doing several things), `leaky-seam` (a `leaksTo` edge: a train wreck / Demeter violation / reaching through a boundary), and `bulky-impl` (large implementation mass for little depth — a shallow module that should be deepened or delegated; see `MINIMALISM.md`) — surfaced by `archmap_scan_signals`. The simple-design rules feed signals owned elsewhere: rule 2 → `duplication`; rules 3–4 → `NAMING`/`FUNCTIONS`/`MINIMALISM`. The **structural** smells from ch. 17 (G6 wrong level of abstraction, G14 feature envy, G34 functions descend one level, G36 transitive navigation) live in `SMELLS.md` tagged **[design]** — they become deepening candidates, because the fix re-cuts the seam. The *subjective* structural judgements (is this really one responsibility? is this hybrid justified?) stay as this rule the skills apply, checked by a human — Fathom does not fake structural taste as a metric.

## References

- `reference/structure.md` — the deep dive: data/object anti-symmetry worked both directions, the Demeter train-wreck → tell-don't-ask transform, the boundary-wrapper-as-port pattern, the cohesion split, OCP/DIP before-and-after, and the construction-vs-use wiring sketch.
- Source chapters (original Java): *Clean Code* ch. 6 "Objects and Data Structures," ch. 8 "Boundaries," ch. 10 "Classes," ch. 11 "Systems," ch. 12 "Emergence," ch. 13 "Concurrency."
- Hands off to: `../DEEPENING.md` (categories 3 & 4 = boundaries; injection = DI), `../INTERFACE-DESIGN.md` (object-vs-data and seam placement), `../MINIMALISM.md` (how little behind the seam; minimal classes). Adjacent craft: `ERRORS.md` (error modes are part of the interface), `TESTS.md` (the interface is the test surface).
