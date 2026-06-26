# Craft · Comments

The **craft** layer is the altitude *below* `LANGUAGE.md` and `MINIMALISM.md`: how to write the implementation **behind a seam** so it reads cleanly. A comment is, at best, a necessary evil — an admission that the code couldn't say it itself — and at worst an outright lie. Drawn from *Clean Code* ch. 4. Language-agnostic.

**Read by:** `code` (deciding whether a comment earns its place, or whether the *why* belongs in a spine doc — pairs with `MINIMALISM.md`), `review` (the craft pass).

## Where this sits in the suite

- **Depth / seam** (`LANGUAGE.md`) decides *what the interface is*; a public interface earns a documentation comment, the implementation behind it rarely does.
- **Minimalism** (`MINIMALISM.md`) decides *how little* implementation sits behind the seam — and the `ceiling` doc is where the *why* of that little is recorded.
- **This doc** decides which of the remaining comments survive, and which the code should have said instead.

The central Fathom move: **on the spine, the `ceiling` doc (`MINIMALISM.md`) and the `adr` / `spec` docs replace the explanatory comment.** When you reach for a comment to explain *why* a design is the way it is — a constraint, a rejected alternative, a deliberate limit — record it as a *typed spine doc*, not an inline note that drifts out of sight and out of date. `code` §9 already records `ceiling` and `adr` for exactly this. An inline comment is for things that must live *at the line*; everything that's really design rationale belongs on the spine, where it's findable and versioned.

## The rules — each with its *why*

**Don't comment bad code — rewrite it.** A comment that explains a confusing block is a missed opportunity to make the block clear. Before writing one, try to make it unnecessary. *Why:* expressive code beats a comment because the code can't lie about what it does — the comment can, and eventually will.

```
// smell — comment compensates for a cryptic condition
// check if employee is eligible for full benefits
if (emp.flags & HOURLY) and (emp.age > 65): …
// craft — the code says it; the comment is deleted
if emp.isEligibleForFullBenefits(): …
```

**Comments rot; code drifts away from them.** Code changes and comments seldom follow. The older a comment, the further from its code, the more likely it's wrong. *Why:* an inaccurate comment is far worse than none — readers trust it, then it misleads them. Only the code tells the truth, so the truth belongs in the code.

**Good comments are the few that earn their place.** Some comments are necessary or beneficial; keep these:

- **Legal** — copyright/license headers a standard or employer requires.
- **Informative** — basic info a name can't fully carry (the format a regex matches), *if* it can't be moved into a better name.
- **Explanation of intent** — *why* this decision, not what the code does (why this ordering, why this fallback). *On the spine, this is exactly what becomes an `adr` or the `ceiling` doc — prefer that over an inline note.*
- **Clarification** — translating an obscure argument or return into something readable when you can't change it (e.g. a value from a library you don't own).
- **Warning of consequences** — "this test runs for hours, don't enable casually," "not thread-safe."
- **TODO** — a note that something's not done yet, with the reason; scan and clear these regularly so they don't pile up.
- **Amplification** — flagging that something seemingly trivial is in fact important ("trim matters here — a leading space changes the parse").
- **Public-API documentation** — doc comments on an interface meant to be used by others. *This is the comment that maps directly onto the seam — the published surface deserves it; the hidden implementation does not.*

**Bad comments are most comments — delete them.** Each of these is noise or a liability:

- **Redundant** — restates exactly what the code already says; takes longer to read than the line it describes (`i++; // increment i`).
- **Misleading / inaccurate** — subtly wrong, so the reader is led astray. The drift in rule two produces these.
- **Mandated** — a rule that *every* function/variable carry a doc comment fills the file with clutter and trains readers to ignore comments wholesale.
- **Journal / changelog** — "2008-04-12 changed X" entries at the top of a file; version control already holds this, perfectly.
- **Noise** — say-nothing ceremony: `// Default constructor`, `// the day of the month`. They answer no question; the reader's eye skips them, which means they hide the rare comment that matters.
- **Position markers / banners** — `////// Actions //////` rows. Used rarely they can group, but a file full of them is wallpaper the reader stops seeing.
- **Commented-out code** — the worst kind. Others fear to delete it ("it's there for a reason"), so it rots in place. *Why:* version control remembers deleted code, so commenting it out buys nothing and signals decay — delete it. *(This is measurable — see the `comment-smell` signal below.)*
- **Too much information** — a comment that dumps a historical discussion or RFC details a reader doesn't need here.
- **Nonlocal information** — a comment that describes something far from it (a default set elsewhere); when that distant thing changes, this comment silently goes wrong.
- **HTML in comments** — markup inside source comments is unreadable in the one place comments should be readable: the editor.

## How you actually get there

The first reflex when you want a comment is to ask whether a rename or an extraction would say it instead (`../NAMING.md`, `../FUNCTIONS.md`) — most "explanatory" comments are really a function begging for a name. The second reflex, when the thing you want to explain is *why* a design is shaped this way, is to ask whether it belongs on the spine as an `adr` or in the `ceiling` doc rather than at the line. Only what survives both questions — something that must live exactly here and can't be a name, an extraction, or a spine doc — gets written as a comment.

## Checklist (the `review` craft pass runs this)

- [ ] No comment compensating for code that could be made clear (rename/extract first)
- [ ] No commented-out code — deleted, since version control remembers it
- [ ] No redundant, noise, journal/changelog, or banner comments
- [ ] Every surviving comment is one of the *good* kinds (legal / intent / warning / TODO / amplification / API doc)
- [ ] *Why*-rationale recorded as an `adr` or in the `ceiling` doc, not as an inline note
- [ ] Public interfaces (seams) carry doc comments; hidden implementation does not
- [ ] No comment describing something nonlocal that can silently drift wrong
- [ ] TODOs are current and have a reason; stale ones cleared

## Signals this feeds (spine)

`comment-smell` — the *mechanically detectable* bad comments: **commented-out code** (source statements sitting inside a comment) and **noise comments** (say-nothing boilerplate like `// Default constructor`). These a parser can flag, so they're measured by `craft_ingest` and surfaced by `archmap_scan_signals(map, family="craft")`. Everything else here is *subjective* — whether a comment is redundant, misleading, or whether a *why* should have been an `adr` — and stays as this rule the `review` craft pass applies, judged by a human. The constructive half (record the *why* as a typed spine doc) is enforced by `code`/`design` writing `adr`/`ceiling`, not by a comment metric.

## References

- `reference/comments.md` — the deep dive: the full good/bad catalog with before/after, the commented-out-code argument in full, and the "comment → rename / extract / spine doc" decision in worked form.
- Source chapter (original Java): *Clean Code* ch. 4, "Comments."
- Pairs with `MINIMALISM.md` (the `ceiling` doc holds the *why*), `../NAMING.md` and `../FUNCTIONS.md` (a name or an extraction usually deletes the comment).
