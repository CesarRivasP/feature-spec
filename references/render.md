# Render — the HTML view of a spec set

`view <slug>` renders a spec set to **one self-contained HTML file**. It is a
**derived artifact**: never edited, never committed as a source of truth,
regenerated on every change. The markdown files and `_facts.yml` remain the
only things anyone authors.

    python3 scripts/render.py docs/features/<slug>/            # -> <slug>/view.html
    python3 scripts/render.py docs/features/<slug>/ --open
    python3 scripts/render.py docs/features/<slug>/ --serve 8000

## Why it exists

The set already carries structure that markdown cannot show:

| in the files | invisible when read as markdown | what the view does |
|---|---|---|
| `basis:` on a registry entry | doc 01 §1 reads the same whether the root cause was **measured** or **guessed** | colored chip on every claim, with `evidence.cmd/date/value` or `falsified_by` attached |
| a number copied from the registry into prose | you cannot tell prose from registry by looking | the value is marked; click jumps to its key, click the key highlights every citation |
| `changes[]` vs `related_docs[]` | two YAML lists that look alike | rendered side by side, labelled by whether they are scope |
| `defects[] / alternatives[]` | a flat list with `depends_on` ids | a board by status, `depends_on` navigable |
| the `audit` correspondence matrix | terminal output, gone when the scroll ends | a table in the page, recomputed on every render |
| `_log.md` | a wall of `##` blocks | a timeline, dispositions colored confirmed / rejected / deferred |

Nothing here replaces `audit`. The matrix and the dangling-ref flags are the
**same mechanical comparisons**, shown instead of reported — a second surface on
the same facts, not a second opinion.

## What it reads

- `_facts.yml` — required. Absent → the directory is not a spec set, hard error.
- every file in `docs[]` that exists on disk, **and a note naming the ones that do
  not exist yet because their `stage:` has not been reached**. A stage-1 set holds
  the registry and doc 01 only; without that line it is indistinguishable from a set
  someone abandoned halfway. Same contract as `references/audit-protocol.md`
  §Stage gating: a doc whose stage is not reached and which is absent is correct,
  not missing — and correct is not the same as silent. A `docs[]` entry with no
  `stage:` reads as `draft`, so sets written before staging render exactly as before.
- every file in `docs[]` that exists on disk. No `docs[]` → falls back to
  `[0-9][0-9]*.md` in the directory, so a half-scaffolded set still renders.
- `_log.md` — optional; absent, the Log view says so rather than hiding it.
- `_profile.yml` — resolved with the **same upward walk `new` uses** (nearest
  wins, stop at the git root). Its `commands.*` are shown in the Registry view,
  so the commands the docs quote can be compared against their source.

## Invariants

1. **Registry ids are canonical.** Overview / Claims / Defects re-render the
   same registry nodes; only the Registry view carries the `fact-*` ids, the
   others carry `data-fid`. Two copies of one id would make provenance land on
   whichever happened to render first.
2. **Provenance never touches `<pre>`.** Paste-ready code in doc 02 is quoted
   verbatim from the repo. Marking inside it would suggest the registry owns a
   line of source that it does not.
3. **Cross-refs resolve against real headings.** Doc ids come from `docs[]`,
   never `\d{2}` — a date like `2026-08-11` would otherwise read as a prefix
   `08`. The prefix is matched **across tags**, because `` `01` §3.2 `` puts the
   prefix inside a `<code>` element. A ref that resolves nowhere renders red and
   is counted on the Overview; it does **not** silently disappear.
4. **A prefix does not distribute.** `` `01` §3.2 y §2 `` links §3.2 into doc 01
   and §2 into the current doc — the rule from
   `references/audit-protocol.md` §4, applied literally.
5. **Commented-out markdown never renders.** `<!-- … -->` is stripped before
   parsing, so the example rounds shipped inside `templates/_log.md.tpl` never
   appear as real history.
6. **Orphan datums are shown, not hidden.** A registry value with zero citations
   across every doc is either missing from the docs or dead weight in the
   registry. The matrix marks the row and the Overview counts it.

## Gates surfaced on the Overview

Read straight from `references/evidence.md`, no new rules:

- **G1** — `status: shipped` while a `root_cause` / `contributing` defect is
  still `basis: asserted`.
- `basis: measured` whose `evidence` is missing `how` / `cmd` / `date` / `value`.
- `basis: asserted` with no `falsified_by:`.
- an `evidence.cmd` using regex alternation (`rg 'A|B'`) — fused result sets
  cannot be attributed per symbol.
- an `evidence.cmd` scoped by denylist (`-g '!…'`, `--exclude-dir`) — files added
  later enter the result set silently.

## Sharing it

The output is one file with the CSS and JS inlined, no network requests. That is
the sharing unit: send `view.html` to the external owner of doc 03 and it opens
offline, with no account and no link that expires.

`--serve` binds `127.0.0.1` by default. `--serve --lan` binds `0.0.0.0` and
prints a warning: a spec set routinely names endpoints, env var names and
internal paths, so putting it on the network is a decision, not a convenience.

## Dependencies

PyYAML, and nothing else. There is **no fallback YAML parser on purpose**: a
registry parsed slightly wrong is exactly the failure this skill exists to
prevent, and a hard error naming the install line costs less than a view that
quietly drops a `basis:`.
