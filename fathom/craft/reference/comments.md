# Craft · Comments — deep reference

The depth behind `../COMMENTS.md`. Read on demand. All examples are neutral pseudocode; the originals (Java) are in *Clean Code* ch. 4.

## The premise: comments compensate for failure

Comments are not a positive good. We want them because we can't always make the code self-explanatory — so every comment is a small confession that the code didn't carry its own meaning. That reframes the whole chapter: the goal is *fewer, truer* comments, reached mostly by improving the code until the comment is unnecessary.

And comments lie. Not deliberately, but inevitably: code moves, splits, and changes; the comment beside it seldom keeps up. The further a comment drifts from the code it once described, the more likely it's now false — and a false comment is worse than no comment, because the reader believes it. The truth lives in one place only, the code, so that's where to put it.

## Comment → make it unnecessary

The first move is almost always to delete the comment by improving the code:

```
// the comment is doing the code's job
// check to see if the employee is eligible for full benefits
if (employee.flags & HOURLY_FLAG) and (employee.age > 65): …
```

A single well-named function says it with no comment, and can't fall out of date:

```
if employee.isEligibleForFullBenefits(): …
```

The same reflex covers most "explanatory" comments: a confusing expression wants a named intermediate; a confusing block wants to be an extracted function (`../FUNCTIONS.md`); an opaque variable wants a better name (`../NAMING.md`). Reach for those before reaching for a comment.

## Good comments — the survivors, with shape

These earn their place; keep them.

- **Legal.** `// Copyright (c) … released under …` — required headers. Keep them short; point to an external license rather than inlining the full text.
- **Informative.** Conveys basic info a name can't fully hold — e.g. the exact format a matcher expects. Even here, prefer moving it into a name (a `timeMatcher` constant) when you can.
- **Explanation of intent.** Records *why*, not *what*: why this sort order, why we return early in this odd case. **On the spine this is the comment that should not stay a comment** — it's design rationale, so write it as an `adr` (a decision and its rejected alternatives) or fold it into the `ceiling` doc (the deliberate limit). An inline intent comment drifts; a typed spine doc is findable and versioned.
- **Clarification.** Translates an obscure value you can't rename — e.g. a return code from a library you don't own — into a readable assertion right where it's used. Risky (it can be wrong), so reserve it for cases where you genuinely can't fix the source.
- **Warning of consequences.** `// not thread-safe — construct one per thread`, `// runs for ~hours; don't enable in CI`. Saves the next person from an expensive mistake.
- **TODO.** A planned-but-not-done note *with its reason*. Legitimate, but scan for and resolve them regularly — a codebase full of stale TODOs is just more noise.
- **Amplification.** Insists that something innocuous-looking actually matters: `// the trim is significant — a leading space changes the meaning downstream`.
- **Public-API documentation.** Doc comments on an interface intended for outside callers. **This is the comment that maps onto the seam:** the *published surface* deserves documentation; the *hidden implementation* behind it does not. Document the seam, not the guts.

## Bad comments — the catalog, with the failure mode

Most comments are these. Each entry says why it's a liability.

- **Redundant.** Restates the code and takes longer to read than the line itself. `i++ // increment i`; a doc comment that just re-spells the method signature. Adds reading cost, zero information.
- **Misleading / inaccurate.** Subtly wrong — promises something the code doesn't quite do. This is what comment-rot produces: yesterday's true comment beside today's changed code.
- **Mandated.** A policy that every function and variable *must* carry a doc comment. The result is uniform clutter that buries the rare useful comment and teaches readers to tune comments out entirely.
- **Journal / changelog.** `// 2009-03-11 — added handling for X` logs at the top of a file. Version control records this losslessly and queryably; the inline log is just rot waiting to happen.
- **Noise.** Ceremonial say-nothings: `// Default constructor`, `private day // the day of the month`. They answer no question a reader would ask. Their real harm is camouflage — a file full of noise comments trains the eye to skip *all* comments, hiding the one that matters.
- **Position markers / banners.** `// ===== Public Methods =====` dividers. A single one, used sparingly to mark a genuinely significant grouping, can help; a file striped with them becomes wallpaper the reader stops seeing.
- **Commented-out code.** The most insidious:

```
function process(items):
    for item in items:
        validate(item)
        // legacyTransform(item)        // ← nobody dares delete this
        // applyOldDiscount(item)       //    so it rots here for years
        persist(item)
```

  Others see it and assume it's there for a reason, so they leave it — and it accumulates. But version control already remembers every deleted line, so commenting code out buys *nothing* and signals decay. **Delete it.** (This is the half of the chapter a parser can catch — see the signal below.)

- **Too much information.** A comment that dumps a historical discussion, an RFC excerpt, or encoding minutiae the reader doesn't need at this spot.
- **Nonlocal information.** A comment describing something far away — a default configured in another module, behavior controlled elsewhere. When that distant thing changes, this comment goes silently wrong, and no one editing the distant code will think to look here.
- **HTML in comments.** Markup inside source comments. Comments must be readable where they live — in the editor — and angle-bracket soup defeats that.

## The decision, in worked form

When you feel the urge to write a comment, route it:

1. **Can a rename or extraction say it?** → do that instead (`../NAMING.md`, `../FUNCTIONS.md`); write no comment.
2. **Is it *why* this design is shaped this way (a constraint, a rejected option, a deliberate limit)?** → record it on the spine as an `adr` or in the `ceiling` doc (`../MINIMALISM.md`); not an inline note. `code` §9 already writes `ceiling`/`adr`.
3. **Is it a warning, an amplification, a legal header, a TODO, or doc on a public seam?** → keep it, as a comment, right at the line.
4. **Is it commented-out code, a changelog, or noise?** → delete it.

Only what survives steps 1–3 as a "keep" gets written. The point isn't to ban comments — it's that the *good* comment is rare, and most of what we'd write is better said by the code, the seam, or the spine.

## See also

- `../COMMENTS.md` — the rules + checklist (the `review` craft pass) and the `comment-smell` signal.
- `../MINIMALISM.md` — the `ceiling` doc, where the *why* belongs instead of an inline comment.
- `../NAMING.md`, `../FUNCTIONS.md` — the rename and the extraction that delete most comments before they're written.
