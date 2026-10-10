# `ship <slug> --tag <tag>` — the flip to `shipped`, as one command

`verify` ran, the root cause is `measured`, the release is out. What is left is a state change whose every step is known in advance — and done by hand it was **six edits across two files, a `Stage:` line, and three re-stamps** of `Edits:` because each edit to the registry invalidated the stamp before it. Half a round for a transition with nothing left to decide. The release URL and the date of publication went into a YAML comment, because `shipped_in:` was the only field there was and a comment is invisible to `sync`, `view` and every check.

```
python3 scripts/ship.py docs/features/<slug>/ --tag <release tag> \
        [--on YYYY-MM-DD] [--url <release page>] [--note TEXT] [--dry]
```

**Open the round's stub first, as any round** — `## R<n> · <date> · <agent> · ship`, `Read:` from `--read-line`, `Log read through:`. Then run the script. It does, in order:

1. **Reads the registry.** A YAML syntax error prints `_facts.yml:<line>:<col>` with the line and a caret, and nothing else runs (exit 3).
2. **Runs the gates AS IF `status:` already read `shipped`** — G1, check 14's shipped-set detectors, check 26's acceptance state. Any `CONTRADICTION` and it **refuses (exit 2), naming each entry**: a root cause still `basis: asserted`, a defect still `open` with no `outcome:` and no `owned_by:`, a criterion still `written`. Those are the edits that take a person — flipping `D1` to `status: fixed` with its evidence, writing an `outcome:`, retiring a criterion with `retired_because:` — and the script names them instead of guessing. Settle them, run it again. `audit.py <dir> --as-status shipped` previews the same list without the flip.
3. **Edits `_facts.yml` in place, as text**, so every comment survives: `status: shipped`; `tracking.shipped_in` (the tag), `shipped_on` (the date), `release_url` (when given); one `dates.revisions[]` entry **appended** — oldest first, the order check 40 reads.
4. **Edits doc 01**: the changelog entry **prepended** under `## Changelog` — newest first, the opposite order, which is where inserts went wrong three times in one set — and its `Estado:` line. A table changelog gets a row; a heading changelog gets `### <date> — v<n>: <note>`.
5. **Prints the two lines the log entry needs**, measured after the edits so they are the versions check 16 will find:

```markdown
**Stage:** implementing → shipped — shipped in `v1.4.1` on 2026-10-09, <release url>
**Edits:** `_facts.yml` (634 lines, blob 882d1ff) · `01-master-plan.md` (197 lines, blob 1c4d77a)
```

Paste them into the open entry, complete it, run `audit`. The log is the agent's and the script never writes it — the stub-first rule is what makes a half-finished flip visible, and a script that wrote the entry would write it after.

`--dry` prints the diff it would apply and writes nothing. A second run on a shipped set is refused as already shipped.

**What it does not do, on purpose.** It does not touch `defects[]`, `acceptance[]` or `changes[]` — the gate tells you which ones block and why, and each of those is a claim about the world that takes evidence, not a status flip. It does not change `docs[].stage`: that field is the status each doc was *written at*, not the set's current one, and doc 01 written at `draft` stays so. It does not ask intake set C — `verify` already did, before the measurement this flip rests on.

Fields it writes, in the template:

```yaml
tracking:
  shipped_in: v1.4.1                      # the release tag
  shipped_on: 2026-10-09                  # when it was published
  release_url: https://…/releases/v1.4.1  # where — check 28 reads shipped_in; the
                                          # other two are for sync, view and the reader
```

---

Every mode starts by reading `_log.md` from disk and opens its own entry before editing (`SKILL.md` §Modes, `references/handoff.md`). The rules every mode that writes is held to: `references/rules.md`.
