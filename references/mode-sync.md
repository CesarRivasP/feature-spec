# `sync <slug>` — propagate registry changes
When `_facts.yml` changes, find every doc occurrence of each changed datum and update it — `scripts/sync.py` does the data half (dry run by default, `--apply` to write). This is the write-side counterpart of `audit`.

**Start by running the command, not by reading the docs.** `python3 scripts/sync.py docs/features/<slug>/` (dry run: prints the plan, writes nothing), read the plan, then `--apply`. It takes old values from the base below and new ones from disk, replaces each changed value in the in-scope docs with the word boundaries the provenance view uses, and prints the `**Edits:**` line for the round's entry. Exit 1 = ambiguous values were left unapplied, or a doc changed since the plan.

**The old registry comes from the first base that exists, and the first output line names it (`base: …`):**
1. `--from-file PATH` — a file holding the old `_facts.yml`.
2. `--from REF` — explicit git ref (`git show REF:_facts.yml`). If the change is already committed, `HEAD` equals the disk and there is nothing to compare: the script says so (`the registry at HEAD is identical…`); re-run with `--from <ref before the change>` (e.g. `HEAD~1`).
3. `_facts.synced.yml` beside `_facts.yml`, if present: a byte copy of the registry as of the last clean sync. It makes `sync` work where `_facts.yml` is out of git (`.git/info/exclude`) or there is no repo at all. The `_` prefix makes `audit` treat it as set machinery.
4. git `HEAD`, if `_facts.yml` is tracked and not ignored (uncommitted edits are fine). With no snapshot and no `--from-file` this is the behavior sync always had.
None of them: exit 2, naming `--init-base` and `--from-file`.

**`--init-base`** writes `_facts.synced.yml` as a byte copy of the current `_facts.yml`, prints its path and exits 0 (no diff, nothing else written). It refuses to overwrite an existing snapshot (exit 2) unless `--force`. Run it **only when the docs are known to match the registry**: a snapshot taken over stale docs hides that drift from `sync` (`audit` still finds it).

**The snapshot is updated by `--apply`, and only by a fully clean run:** exit 0, no ambiguous value left, no doc skipped as changed-since-plan. Otherwise the old snapshot stays (the run says so) and the unapplied changes show again next run. A dry run never writes it. If the base was git and no snapshot exists, none is created. In a git-tracked set the snapshot is optional; whether to commit it is the repo's choice.

**The script does not write a doc that changed during the plan.** Before `--apply` writes each doc it re-reads it and compares it byte for byte with what the plan was built from; a doc that differs is skipped and listed as *Changed since plan, NOT written, re-run* (exit 1) while the others are written. Writes are atomic (temp file + `os.replace`, permissions kept). Re-run `sync` to plan again over the current text. **What is left for you** is only what it reports and will not decide: the *Ambiguous* values (shared by several paths, part of another datum, under 3 characters, or without a new value), the *Needs a human (sync --decision)* decisions, and the *Not written* legacy/derived docs. Resolve those by hand, then re-run `audit`.

**Only over docs whose stage the set has reached.** A datum with no occurrence in doc 02 because doc 02 does not exist yet is not drift, and reporting it as such in the dry run buries the real findings. Resolve the stage exactly as `audit` does (`references/audit-protocol.md` §Stage gating), and say which docs were out of scope rather than staying silent about them.

**`role: legacy` and `role: derived` docs are never written into.** A legacy doc predates the set; a derived one (PR body, release notes, runbook) is generated from it and regenerated whole, not patched value by value. Both are registered so check 9 sees them; neither is a `sync` target. Report a datum they carry that drifted, as a line, and leave the edit to whoever regenerates them.

**`sync <slug> --decision <key>`** lists the sections a `decisions.*` entry's `cited_in:` names, and does **not** edit them. Changing a decision is almost never a string replacement — the prose that rests on it has to be rewritten by someone who knows what replaced it. Reporting and letting a human rewrite is the correct behavior, not a limitation.

**`sync` moves data, not shape.** It finds a value and replaces it. A plan that *changed shape* — an entry that left `changes[]`, a decision that was cancelled — has no value to replace: it has prose hanging off a premise that is now false, and nothing follows that arrow. That is `implement`'s problem for doc 02's phases and `references/gap-sweep.md` §Trimming scope's for `acceptance[]` and `decisions.*`. Running `sync` and calling the set consistent is how a cancelled decision left 14 stale promises across a set that audited clean.

---

Every mode starts by reading `_log.md` from disk and opens its own entry before editing (`SKILL.md` §Modes, `references/handoff.md`). Stub with `python3 scripts/audit.py docs/features/<slug>/ --entry --agent <name> --mode sync --read-line [FILE ...]` and close with `--edits-line FILE ...` when edits complete. The rules every mode that writes is held to: `references/rules.md`.
