# `audit <slug>` — consistency check (default: inline)
**Resolve the stage first** (`references/audit-protocol.md` §Stage gating): `status:` ranks `draft < reviewed < implementing < shipped`, each `docs[]` entry declares the `stage:` it is written at, and checks 5, 6 and 13 only run once their doc is in scope. A doc that is out of scope but exists on disk is checked anyway. A set with no `stage:` fields anywhere audits exactly as it did before staging existed.

**Read the registry by index, not whole.** `python3 scripts/audit.py docs/features/<slug>/ --index` prints every top-level key and every entry with its line span and its enum labels (`kind`, `role`, `basis`, `status`); read the entries a finding or a check points at by offset. A 142KB registry indexes in 6KB, a 307KB one in 11KB. Read the file whole only when the round means to.

**Run the script, then the judgment pass — in that order.**

```
python3 scripts/audit.py docs/features/<slug>/
```

`--as-status <stage>` previews a flip before making it: the set is audited as if `status:` already read `<stage>`, in memory and in place — the file is not touched, and every anchor still resolves against the real tree. *Real case:* a set about to go `shipped` was previewed on a copy made outside the repo, and 54 findings came back, most of them anchors "missing" only because the copy was elsewhere. `--today YYYY-MM-DD` moves the date `accepted.until:` is measured against.

It runs every check a program can run and prints the rest under `REQUIRES A HUMAN PASS`, so a skipped check is visible instead of silent. This is not a convenience: the protocol's checks are good and **an agent runs the ones it remembers**, which in a long session is a few. A rough version of this script with ~10 checks mechanized, run against three sets that had each already passed a "clean" hand audit against the same protocol, found **12, 11 and 7 findings** — broken anchors, a corrupted top-level key, orphan ids. None subtle. A check that depends on recall fires least often exactly when the session is long enough to need it.

Several of those checks — 3, 4, 8, 13, 36, 42 and 43 — narrow the search before handing it over: the script prints a short list of **candidates** under the check they belong to. A candidate is not a finding and never appears in `## Findings`: it has no severity yet, and inventing one would make the verdict count things nobody has judged. Read the candidate list instead of re-reading the documents, and decide each one — the exception that legitimises it is usually a note the script cannot read.

Optional, over exactly those candidates: `python3 scripts/triage.py docs/features/<slug>/ [--checks 4,8] [--json]` ranks them and sorts the list into `keep` / `uncertain` / `suppressed` (`--checks` defaults to `4,8`; `3` and `13` are opt-in; `--keep` 0.70 and `--drop` 0.30 are the thresholds). It changes reading order and nothing else — it writes no finding, assigns no severity, edits no document, and suppressed candidates are still printed, because a list nobody is told to read rebuilds the silent-skip failure one level down. Ranking needs the `typesafe-sdk` package and an API key, and their absence is a supported state, not an error: the run falls back to the candidates unranked, `--no-model` takes that path deliberately and `--require-model` exits 2 instead of taking it. That fallback is a complete answer — `audit.py` is python3 + PyYAML and computes the candidates offline before any call is made, so what is lost with no key is reading order, not a check. `--check-setup` reports what is installed and the gap, exiting 1 when ranking is unavailable — a probe, distinct from `--require-model`'s 2, which means a real run declined to fall back. The model is a layer over the offline baseline and never a dependency of it. Three more flags exist for the caller rather than the reader: `--repo-root` is `audit.py`'s own (anchor and file resolution root, default the git toplevel, and it must match what the audit ran with or the candidates resolve against a different tree), `--model` pins the ranking model instead of taking the SDK's default, and `--timeout` (60s) bounds each request — there is one request per in-scope document, not one per candidate, so it does not scale with the candidate count.

It deliberately never executes `evidence.cmd` (check 1b). A registry is a data file that travels between repos and agents; running commands out of one because it says they are safe is the thing an auditor must not do. Re-running evidence is a human step and the script lists it as one.

Then do the judgment pass and emit:
- the **correspondence matrix** — the script prints it (each registry datum × each doc, as a count of verbatim citations); **never rebuild it by hand**. A number settles that cell's wording; a `·` is where check 1 looks. Report the script's count line plus only the rows the judgment pass changed (`⚠️` cited in other words, `✗` cited with another value) — the full table is already in the script's output and in `view`. `--no-matrix` leaves it out on a re-run after a fix.
- a **findings list**, most-severe first, each tagged `CONTRADICTION` / `DRIFT` / `POLISH`.

Report those rows + the findings as terminal text. Do NOT auto-edit in `audit` mode unless the user says "fix" — surface first, patch on request.

`audit <slug> --deep` → after the inline pass, spawn a **cold reviewer subagent** (`_profile.yml deep_review_agent:` if set, else `Explore`/`general-purpose`) that re-reads the docs with NO context on how they were written and returns compressed findings. The inline pass validates against rules; the deep pass catches normalized-away assumptions the author is blind to. Merge both, dedupe, present once. Use `--deep` at the final gate, not during iteration.

---

Every mode starts by reading `_log.md` from disk and opens its own entry before editing (`SKILL.md` §Modes, `references/handoff.md`). The rules every mode that writes is held to: `references/rules.md`.
