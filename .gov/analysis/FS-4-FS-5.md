# A2-FS-4-5 — `--edits-line` and `facts.py add-attempt`

Analysis only. No code, test or reference was changed by this task. Baseline read at
`f5583aa` (v1.20.2). Evidence read from the Hackathon repo, sets
`docs/features/interstice` and `docs/features/e2e-harness`. Nothing was written there.

## Diagnosis

### FS-4 — the `**Edits:**` line is still typed by hand

- `--read-line` (`scripts/audit.py:4709-4767`, `read_line()` at `:3996-4048`) prints
  `**Read:** \`f\` (N lines, blob abc1234) · …`. It measures each file as
  `data.count(b"\n")` plus `git_blob(data)[:7]`, which is exactly how check 16
  re-measures (`check_log_integrity`, `:3764-3925`).
- Check 16 reads `**Edits:**` lines with the same parser as `**Read:**`
  (`_file_records`, `:3716-3728`; the regex `LOG_FILE_RECORD_ANY`, `:3707`). An Edits
  record does two things:
  1. In the between-rounds comparison (`:3853-3871`), an `Edits:` record becomes the
     version the next round's `Read:` is compared against.
  2. In the disk comparison (`:3876-3918`), the last `Read:` or `Edits:` record of a
     file is compared against disk.

  So a wrong or missing Edits stamp causes two kinds of `DRIFT`: "edited between
  rounds" on the next round, and "last recorded … now …" today.
- Nothing prints that line. `ship.py` does build one (`scripts/ship.py:343-353`), but
  only for its own two files, with the stamp loop written a second time. Every other
  round types `wc -l` plus `git hash-object` by hand. The real logs show it:
  interstice `_log.md:530,546,554,562,569`. Every entry stamps `_facts.yml` by hand
  in the shape `(2137 lines, blob 9dfa211 — \`acceptance[AC7]\`, …)`, with a "what"
  after the em dash. That shape parses today, because the inner group is `[^()]*`.
  A "what" that contains a parenthesis breaks the match in silence: the record is
  dropped, and the line looks recorded when it is not.
- SKILL.md names `--read-line` only in the `handoff` row (`SKILL.md:52`). The
  `implement`, `verify` and `sync` rows edit files and open entries, but do not point
  at the command. `references/handoff.md:55-62` documents `--read-line` only.

### FS-5 — attempts are added to flow-style entries by hand

- The schema is in `references/evidence.md:211-231` and
  `templates/_facts.yml.tpl:420-430`:
  - `date`
  - `outcome` (`aborted_no_conditions | failed | passed`, which is `ATTEMPT_OUTCOMES`
    at `audit.py:1148`)
  - `aborted_because` (required when the outcome is aborted)
  - `env` (optional)

  Check 26 validates the list at `audit.py:1214-1268`: dict shape, ISO date, the
  outcome vocabulary, `aborted_because` when aborted, oldest first, and `approved`
  after an aborted attempt.
- Real sets use two keys the schema does not document: **`round:`** (`R57`,
  `R47-W2`) and **`note:`**. Interstice AC2, AC4, AC5, AC7, AC8, AC12, AC13 and AC14
  carry them. AC14 also carries `result: {…}` and `sheet:`. Check 26 ignores unknown
  keys, so this is a documentation gap, not a bug.
- Every interstice criterion is a **multi-line flow mapping**:
  `- { id: AC14, item: '…', status: written,\n attempts: [ { … }, { … } ] }`, with the
  inner mappings nested in flow style. An append by hand means:
  - finding the closing `}` of the last attempt, inside 300-character quoted lines;
  - adding `,\n` plus the correct column;
  - re-stamping the Edits line.

  That is the error-prone edit FS-5 targets.
- `scripts/facts.py` does not exist. The only registry writer is `ship.py`. It edits
  as text with line helpers (`block_span`, `find_key`, `set_scalar`, `yaml_scalar`,
  `Edit`, `ship.py:54-120`). Those helpers are line-oriented and cannot address a
  position inside a flow mapping.
- **YAML dependency: none new.** PyYAML is already required: `render.py:33-40`
  imports it with an install hint, and `audit.py` re-exports it. `registry_index()`
  (`audit.py:3956-3993`) already uses `yaml.compose_all` node marks to find entry
  spans. `rules.md` and SKILL.md forbid round-tripping the registry through a YAML
  dumper. That rules out both `yaml.safe_dump` and adding `ruamel.yaml`, which would
  also reformat the flow entries.
- **Prototype (in scratchpad, on a copy of interstice `_facts.yml`):**
  1. Compose the stream and take the last document.
  2. Find the `acceptance` item by id, then its `attempts` flow sequence.
  3. Insert `",\n" + " " * last.start_mark.column + "{ … }"` at
     `last.end_mark.index`.

  For AC14 and AC4 this produced a one-line diff (one line split, one line added).
  `safe_load(after)` equalled `safe_load(before)` with the new dict appended.
  Feasibility is confirmed on the real shape.
- **The audit gate must compare before and after, not ask for zero findings.**
  `check_acceptance_state` on the real interstice registry already reports a
  `CONTRADICTION` on AC4 and AC14 ("shipped but never verified"). That finding is
  unrelated to the attempt, so "audit clean" has to mean that no new check-26 finding
  appears for that criterion.

## Design

### FS-4 — `audit.py <dir> --edits-line FILE[=WHAT] ...`

1. **One stamp function, three callers.** Add to `audit.py`:

   ```python
   def version_stamp(name: str, data: bytes, what: str | None = None) -> str:
       """`name` (N lines, blob abc1234[ — what]) — measured as check 16 re-measures."""
   ```

   - `read_line()` builds its parts with it, with no "what". Output stays
     byte-identical, and the existing `read_line_round_trips` test guards that.
   - `ship.py:343-348` replaces its loop with `version_stamp(ed.path.name, data)`.
   - The new `edits_line()` and `facts.py` use it too.

   `version_stamp` refuses a `what` that contains `(`, `)` or a newline: it raises
   `ValueError`, and the CLI turns that into exit 2 with a message. Those three
   characters are what `LOG_FILE_RECORD_ANY`'s `[^()]*` would silently drop.
2. **File resolution.** Reuse `read_line`'s named-file branch: `confined(spec_dir)`,
   then `confined(repo_root)`. Extract it into `_resolve_named(names)` so both callers
   share it.
3. **Argument shape.** Each `FILE` argument may carry a description, written as
   `FILE=WHAT`.
   - If the whole argument resolves to a file, it is a file.
   - Otherwise it is split at the first `=`.
   - If neither works, it is "missing". The command then exits 1 with the same message
     shape as `--read-line`.

   Example: `--edits-line '_facts.yml=acceptance[AC14] attempt' 02-implementation.md`
   prints:

   ```text
   **Edits:** `_facts.yml` (2153 lines, blob b7c34b0 — acceptance[AC14] attempt) · `02-implementation.md` (…)
   ```
4. **`FILE` is required for `--edits-line`** (`nargs="+"`). This is a deliberate
   difference from `--read-line`, whose no-argument form lists the whole set. Listing
   every file under `Edits:` would claim edits that never happened, and that claim
   would then become the version check 16 compares the next round against.
   *Follow-up, not in scope:* a no-argument form listing only the files whose stamp
   differs from the last log record. It needs check 16's `recorded` loop extracted
   first.
5. **`--entry [R<n>] --agent NAME --mode ACTION`**, valid only with `--read-line`
   and/or `--edits-line`. Both line flags may now be given together. Today
   `--read-line` returns early, so the early return moves after both are handled. It
   prints:

   ```text
   ## R<n> · <today|--today> · <agent> · <mode>
   **Read:** …          (if --read-line was given)
   **Edits:** …         (if --edits-line was given)
   ```

   - **`R<n>`.** If omitted, it is the last `## R<n>` in `_log.md` plus 1, read with
     the same heading regex check 16 uses. An explicit `R<n>` that is lower than the
     last id is refused. If it equals the last id, it is allowed, because a stub and
     its completion share an id.
   - **`--mode`.** `choices=` the six actions in `handoff.md:44`: `author`, `review`,
     `implement`, `validate`, `verify`, `sync`. `--agent` is required with `--entry`.
   - **`**Log read through:**` is not printed on purpose.** That field claims what the
     agent actually read, so a script cannot fill it. Stderr says
     "add `**Log read through:** R<k>` yourself — the log's last round is R<last>".
     Check 16 keeps flagging the entry until a person or agent writes it, which is
     the forcing function the field exists for.
   - `--entry` without a line flag is an argparse error.
6. **Docs, by the implementer** (all protected for this analysis):
   - `SKILL.md`, rows `implement`, `verify` and `sync`: add "stub with
     `audit.py --entry --read-line`, close with `--edits-line`".
   - `SKILL.md`, row `handoff`: mention `--edits-line` next to `--read-line`.
   - `references/handoff.md` §Getting the hash: add the `--edits-line` and `--entry`
     usage, plus the `(`/`)` rule.
   - `references/mode-implement.md`, `mode-verify.md`, `mode-sync.md`: one sentence
     each, where they open and close the entry.
   - The `audit.py` docstring usage block (`:14-16`).
   - The README version table: **v1.21.0** (a new flag and a new script, so a minor
     bump).

### FS-5 — `scripts/facts.py add-attempt <dir> <AC-id> ...`

1. **CLI**, as subcommands (`argparse` subparsers) so later registry writers can join:

   ```text
   python3 scripts/facts.py add-attempt docs/features/<slug>/ AC14 \
       --date YYYY-MM-DD --outcome {aborted_no_conditions,failed,passed} \
       [--round R<n>] [--env TEXT] [--note TEXT] [--aborted-because TEXT] \
       [--status {executed,approved}] [--dry] [--repo-root DIR]
   ```

   **Delta from the packet: `--aborted-because`.** The brief lists
   `--date --round --outcome --env --note [--status]`. Check 26 requires
   `aborted_because:` when the outcome is aborted, so validating against the schema
   needs a field to fill it. `--note` is not reused for it, because real entries keep
   `note` and `aborted_because` apart (interstice AC12, AC13). The flag is required
   if and only if `--outcome` starts with `aborted`; in every other case it is
   refused.
2. **Validation before any edit.** All of these exit 2 and write nothing:
   - **Registry:** a YAML error in `_facts.yml` → `yaml_error_report`, exit 3.
   - **Criterion:**
     - `<AC-id>` matches no `acceptance[]` dict, or matches more than one;
     - the criterion is a plain string (no id to address; tell the user to convert it
       to `{ id:, item: }`).
   - **Flags:**
     - `--date` is not ISO;
     - `--round` does not match `^R\d+([-\w]*)$`;
     - `--status approved` is given with any outcome other than `passed`;
     - `--status` is given with `--outcome aborted_no_conditions`.
   - **Order:** `--date` is older than the last attempt's date. The list is
     append-only and oldest first; check 26 would flag it, so refuse up front.
3. **Idempotent.** The new attempt is the dict of the fields given, in key order
   `date, round, outcome, aborted_because, env, note`, which is the order real entries
   use.
   - If an existing attempt equals it as parsed data, nothing is written. The command
     exits 0, prints `already recorded: acceptance[AC14].attempts[i]`, and prints the
     Edits line of the file as it is.
   - If an existing attempt has the same `(date, round, outcome)` but different
     fields, the command exits 2 with "attempts are append-only; a correction is a
     hand edit". This avoids silently adding a near-duplicate.
4. **Editing as text, with node marks.** Compose `_facts.yml` and take the last
   document, which handles vault two-document streams the same way `load_facts` and
   `registry_index` do. Find the `acceptance` node, then the item whose `id` scalar
   matches. Exactly four shapes are handled:

   | entry | `attempts` | insertion |
   |---|---|---|
   | flow `{…}` | flow `[…]`, non-empty | after last item's `end_mark.index`: `",\n" + " "*last.start_mark.column + FLOW` |
   | flow `{…}` | flow `[]` empty | inside the brackets: `" " + FLOW + " "` |
   | flow `{…}` | absent | after last value's `end_mark.index`: `",\n" + " "*first_key.start_mark.column + "attempts: [ " + FLOW + " ]"` |
   | block | block `- …`, or absent | new lines after the sequence or the mapping's last line (via `_node_lines`-style span), `- date: …` one key per line at the sibling indent; `attempts:` key first when absent |
   | block | flow `[…]` | same as row 1 |

   - **Formatting.** `FLOW` is `{ date: 2026-10-26, round: R63, outcome: passed,
     env: '…', note: '…' }`, with scalars quoted by `ship.yaml_scalar`: single quotes,
     inner quotes doubled. That is the convention check 1 never flags. Dates and enum
     words stay bare.
   - **Unknown shapes** are refused with exit 3, "edit by hand". That covers anchors
     or aliases on the entry, and tags.
   - **Comments** outside the inserted span are untouched by construction.
5. **`--status`** sets the entry's `status:` value by replacing the slice of its
   value node, so a trailing comment survives. With `executed` or `approved` it also
   writes `verified_on: <--date>`:
   - if the key exists, its value slice is replaced;
   - if it does not, it is inserted after the `status` value, as `, verified_on: D`
     in a flow entry or as a sibling line in a block entry.

   This is what `evidence.md:229` says the author does by hand, so it stays opt-in.
6. **Post-edit gates, in memory, before writing:**
   - **Round trip.** `safe_load(new_text)` must equal `safe_load(old_text)` with the
     attempt appended and the `--status`/`verified_on` change applied, compared as
     whole documents. Any other difference aborts with exit 3 and writes nothing.
     This is the text-edit counterpart of `assert count == 1` in `rules.md`.
   - **Audit.** Run `check_acceptance_state` (imported from `audit.py`, as `ship.py`
     does) on the old and new facts. Every finding whose `where` is
     `acceptance.<id>` and is new after the edit is printed, and the command exits 2
     unwritten. Findings that already existed (AC4/AC14's "shipped but never
     verified") are not the edit's doing.
7. **Output, as in `ship.py`.** A one-line summary, then the `--dry` diff or the
   write, then:

   ```text
   **Edits:** `_facts.yml` (N lines, blob abc1234 — acceptance[AC14] attempt 2026-10-26)
   ```

   This comes from `audit.version_stamp` over the bytes written, which is the FS-4
   function. The log is never written, same rule as `ship.py`.
   **Exit codes:** 0 written or already recorded, 2 refused, 3 cannot edit.
8. **Shared helpers.** `facts.py` imports `Edit` and `yaml_scalar` from `ship.py`.
   Both depend only on the standard library, and importing them avoids a second copy.
   It also imports `load_facts`, `yaml_error_report`, `ATTEMPT_OUTCOMES`, `to_date`,
   `check_acceptance_state`, `Findings` and `version_stamp` from `audit.py`.
9. **Docs, by the implementer:**
   - `references/evidence.md` §Attempts and `templates/_facts.yml.tpl:426-430`: add
     `round:` (optional, the round that ran it) and `note:` (optional, free text) to
     the documented schema, and name `facts.py add-attempt` as the way to append.
   - `references/mode-verify.md:6`: one sentence naming the command.
   - SKILL.md `verify` row: "`facts.py add-attempt`" next to `acceptance[].attempts[]`.
   - SKILL.md References list: one bullet for `scripts/facts.py`, and one test-file
     sentence for `tests/test_facts.py`.

## Target files

The implementer edits these. None was edited by this analysis.

| file | change |
|---|---|
| `scripts/audit.py` | add `version_stamp()` and `_resolve_named()`; `read_line()` uses both; add `edits_line()`; `main()` adds `--edits-line` (`nargs="+"`), `--entry` (`nargs="?"`, `const=""`), `--agent`, `--mode`, and lets `--read-line` and `--edits-line` combine; docstring usage |
| `scripts/ship.py` | stamp loop at `:343-348` calls `audit.version_stamp`; output unchanged |
| `scripts/facts.py` | **new**: `add-attempt` subcommand as designed above |
| `tests/test_audit.py` | `edits_line_round_trips()`, `entry_stub_shape()`; register both in `main()` |
| `tests/test_facts.py` | **new**, same style as `test_ship.py` (functions returning a problem list, a `main()` with a count) |
| `tests/fixtures/facts-add-attempt/` | **new**: `_facts.yml` (see Acceptance), `01-master-plan.md`, `_log.md` |
| `SKILL.md` | rows `implement` / `verify` / `sync` / `handoff`, References bullets |
| `references/handoff.md` | §Getting the hash: `--edits-line`, `--entry`, the parenthesis rule |
| `references/evidence.md` | §Attempts: `round:`, `note:`, the command |
| `references/mode-verify.md`, `mode-implement.md`, `mode-sync.md` | one sentence each |
| `templates/_facts.yml.tpl` | `round:` / `note:` comment lines in the AC23 example |
| `README.md` | v1.21.0 row; script list if it names `ship.py` |

## Acceptance

**Command the implementer makes pass** (from the repo root; all must exit 0):

```sh
for t in tests/test_*.py; do python3 "$t" || exit 1; done \
  && python3 tests/test_facts.py -v \
  && python3 scripts/audit.py tests/fixtures/facts-add-attempt --repo-root tests/fixtures --edits-line '_facts.yml=x' | rg -q '^\*\*Edits:\*\* `_facts.yml` \([0-9]+ lines, blob [0-9a-f]{7} — x\)$'
```

The expected `test_audit` count rises from 311 to at least 313. `test_ship.py` stays
green unchanged, which proves the stamp refactor kept the output byte for byte.

### Tests to add — `tests/test_audit.py`

1. **`edits_line_round_trips()`**, modelled on `read_line_round_trips`, on a temporary
   copy of `fixtures/matrix`:
   1. Write the log:
      ```text
      ## R1 · … · test · author
      <--read-line output>
      **Log read through:** — (first entry)
      ```
   2. Append one line to `01-master-plan.md`.
   3. Run `--edits-line '01-master-plan.md=one line'` and append its output to the R1
      entry.
   4. Assert:
      - **(a)** check 16 has no "last recorded" finding for `01-master-plan.md`. This
        is the packet's acceptance: pasting the output of `--edits-line f` leaves
        check 16 without drift for `f`.
      - **(b)** After `R2` with `--read-line 01-master-plan.md` is appended, there is
        no "edited between rounds" finding. The Edits record became the version R2 is
        compared against.
      - **(c)** After one more line is appended to the file, check 16 reports exactly
        `01-master-plan.md`. The line was written in a shape the check reads.
   5. Edge cases:
      - `--edits-line 'f=has (paren)'` exits non-zero with nothing on stdout;
      - `--edits-line nope.md` exits non-zero;
      - `--edits-line` with no argument is an argparse error.
2. **`entry_stub_shape()`**, on the same copy:
   - `--entry --agent t --mode implement --read-line _facts.yml` prints exactly two
     lines: `## R<last+1> · <--today> · t · implement` and a `**Read:**` line.
   - Stderr mentions `Log read through`.
   - `--entry R0` on a log at R1 exits non-zero.
   - `--mode bogus` is an argparse error.
   - `--entry` with neither line flag is an error.

### Tests to add — `tests/test_facts.py`

The fixture `tests/fixtures/facts-add-attempt/_facts.yml` must audit with no check-26
finding and no check-16 finding. It contains:

| id | shape |
|---|---|
| `AC1` | multi-line flow entry with `attempts: [ { … note: '…' } ]` and a 2-line quoted `note`; copied in shape from interstice AC4 |
| `AC2` | flow entry with no `attempts` |
| `AC3` | block entry with block `attempts:` |
| `AC4` | block entry with no `attempts` and a trailing comment after `status:` |
| `AC5` | plain-string criterion |
| — | a `# comment` line between AC1 and AC2 |
| `D1` | defect with `accepted:`, `closes`-linked from AC1 |

Each case runs on a `tempfile` copy:

1. **`flow_append()`**: `add-attempt AC1 --date <after last> --round R9 --outcome
   passed --env e --note "it's"`.
   - Exit 0.
   - `safe_load` shows `attempts` length plus 1, and the last attempt equals
     `{date, round: R9, outcome: passed, env: e, note: "it's"}`.
   - Every other key is equal.
   - Every `#` line of the original is still present.
   - The unified diff has at most 1 removed line, and that line is a prefix of an
     added line.
   - `audit.py --json` adds no check-26 finding for `acceptance.AC1`.
2. **`rerun_is_identical()`**: the same command twice.
   - The second run exits 0 and prints `already recorded`.
   - The file bytes are identical after the first and second runs.
   - Both runs print the same Edits blob.
3. **`edits_line_reads_back()`**: paste the printed `**Edits:**` into a fixture
   `_log.md` entry. `audit.py --json` shows no check-16 "last recorded" finding for
   `_facts.yml`. This proves FS-5 uses FS-4's function.
4. **`other_shapes()`**: run on AC2, AC3 and AC4. Each passes the same round-trip,
   comment and check-26 assertions as case 1. AC4's trailing comment survives.
5. **`refusals()`**: each of these exits 2 and leaves the file unchanged, compared as
   bytes:
   - unknown id;
   - `AC5` (string);
   - aborted with no `--aborted-because`;
   - `--aborted-because` given with `passed`;
   - date older than the last attempt;
   - same `date`/`round`/`outcome` but a different `--note`;
   - `--status approved --outcome failed`.
6. **`status_flag()`**: `--status executed` on AC2 writes `status: executed` and
   `verified_on: <date>`, and no new check-26 finding appears.
7. **`dry_writes_nothing()`**: `--dry` prints a diff and leaves the bytes unchanged.

### Real-set check before release

Per the project memory, a worker's diff is checked on real sets. Read-only on the
evidence repo; copies only:

```sh
H=/Users/admin/Documents/work/build_future/Hackathon/docs/features
T=$(mktemp -d) && cp -R "$H/interstice" "$H/e2e-harness" "$T/"
python3 scripts/facts.py add-attempt "$T/interstice" AC14 --date 2026-10-26 --round R99 --outcome aborted_no_conditions --aborted-because 'probe' --dry
python3 scripts/facts.py add-attempt "$T/e2e-harness" AC3 --date 2026-10-26 --outcome failed --note 'probe' --dry
python3 scripts/audit.py "$T/interstice" --repo-root "$H/../.." --edits-line '_facts.yml=probe'
```

The expected result is a one-hunk diff for each, and a stamp equal to
`git hash-object` of the copy.

## Risks

- **Mark offsets on unusual registries.**
  - `Mark.index` counts characters of the decoded string, so the edit must slice the
    same `str` that was composed, never bytes. A BOM or CRLF registry still works,
    because the text is sliced as read.
  - The vault two-document stream works with the last document only. Its marks index
    into the whole stream, which is correct for slicing.
  - Mitigation: the whole-document round-trip equality gate refuses anything that
    does not land exactly.
- **Text that "parses but reads differently".** A `FLOW` value with a `: ` or `#` is
  quoted by `yaml_scalar`. A value containing a newline from the shell is refused (CLI
  validation) rather than folded.
- **Contract change on `--read-line` / `--edits-line` combined.** `--read-line` has
  `nargs="*"`, so `--read-line --edits-line f` is read correctly by argparse. Writing
  `--read-line f --entry` after it is also fine. The early `return` moves, and
  `read_line_round_trips` must stay green unchanged.
- **The `--entry` id clashes with a concurrent writer.** Two sessions computing
  `last + 1` at the same time pick the same id. Check 16 already reports a repeated id
  as `CONTRADICTION`, so the clash is caught, not prevented. This is out of scope,
  documented in one line.
- **Schema growth.** Documenting `round:` and `note:` blesses what real sets already
  write. Check 26 does not validate them, which is fine: `round` is free text by
  design (`R47-W2`). If check 26 should later cross-check `round:` against `_log.md`
  ids, that is a separate issue.
- **`--status` widens the blast radius.** It is the only part that edits an existing
  value rather than appending. It is opt-in, and covered by the same round-trip gate.
  If review wants a smaller first PR, `--status` can be cut without changing the rest.
- **Packet deltas** (design choices, not spec contradictions; they do not need
  `needs_spec_change`):
  - `--aborted-because` is added, because the schema requires that field;
  - `--edits-line` requires `FILE`, because a no-argument form would claim false
    edits;
  - `--entry` does not print `Log read through:`, because the field is a claim only
    the reader can make.

## Tier

**agy-high**. The change spans two features across `audit.py`, `ship.py`, a new
`facts.py` and the docs. The node-mark text editing has four shapes, and its
whole-document equality gate must be exact. That needs judgment about edge cases
(flow nesting, comments, two-document streams) that a medium tier tends to
simplify away.
