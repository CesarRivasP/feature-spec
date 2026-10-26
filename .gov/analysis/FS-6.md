# FS-6 — check 16's "rotate the log" POLISH is ignored

Analysis only. No code changed. Read: `scripts/audit.py` (check 16: `check_log_stage`
L3104, `check_log_integrity` L3765, size POLISH L3921–3927, `read_line` L3999,
`open_items` L4078, `main` L4685), `tests/test_audit.py` (`read_line_round_trips`,
`log_size_counts_bytes`, `open_items_lists_pending_actions`, `main`),
`references/handoff.md` §Rotating the log (L103–118), `references/audit-protocol.md`
L220, `SKILL.md` L39/L48/L52, `README.md` release rows v1.13.0–v1.20.2. Evidence, read-only:
`Hackathon/docs/features/interstice` and `Hackathon/docs/features/e2e-harness`.

Recommendation: **worth doing, as a small flag plus a fix to the written rule.** The
rule as written gives a wrong cut on the real set (see Diagnosis 2). Cost: about 150
lines in `audit.py`, 130 in the tests, 10 in the docs. Two to three hours at agy-medium.

## Diagnosis

1. **The POLISH fires and is ignored on the set it was made for.** `audit.py` on
   `interstice` today: `0 contradictions, 0 drift, 1 polish`, the polish being
   `_log.md: 570 lines, 106KB — past what one read can hold. rotate, never summarize:
   references/handoff.md §Rotating the log.` The 80KB byte limit was crossed with 21
   rounds (R42–R62) and no one rotated. This set was already rotated once by hand, in
   R42 (2026-09-27): R1–R36 went to `_log-R1-R36.md` (1040 lines, 180KB). Rotating
   costs a lot, and the finding does not say how to start. The agent has to read the
   whole log to find the cut, decide the cut, write a header, move about 90KB verbatim,
   check the bytes match, then repair what the audit says next. A POLISH that costs a
   round to act on gets deferred every round.

2. **The written cut rule fails on the real log.** `handoff.md` step 2 says to archive
   every round before the last `**Stage:**` transition (v1.20.0 made this the rule).
   On `interstice`, the only `Stage:` line in `_log.md` is R42's
   `reviewed → reviewed — carried, not a transition`. Two readings:
   - If the carried line counts as a transition, the cut is at line 177 (R42). That
     keeps 408 lines and **83,650 bytes**, so the log is still over 80KB and the POLISH
     stays. The rotation would not fix the finding it was run for.
   - If it does not count (from = to), there is no transition, and the fallback
     applies: "the last five to ten rounds". Cutting at R58 (line 521) keeps 64 lines
     and 12,941 bytes, and archives lines 15–520 (93,128 bytes).

   So the rule needs two things it does not say. A transition means `from ≠ to`. And a
   cut whose kept part is still near the limit falls back to keeping the last few
   rounds. The R42 precedent did this by hand: the real transition was R7 of 41, so
   following the rule would have kept R7–R41, and the agent kept R37–R41 instead.

3. **A second rotation is not specified.** `handoff.md` names the archive
   `_log-R1-R<k>.md`. On `interstice` the next archive starts at R37, and
   `_log-R1-R36.md` already exists. The name has to be `_log-R<first>-R<last>.md`, and
   a plan must refuse a name that is already taken.

4. **The steps that are only arithmetic are done by hand, and done by hand they went
   wrong.** R42's `Validation:` records two DRIFTs the procedure did not foresee. The
   archive was named in `Edits:` without a version, and the `Stage:` line had moved
   into the archive. The byte-for-byte check was "Verified before writing" in prose,
   with no command. Every one of these can be computed from `_log.md`, `status:` and
   the round headings. That fits `--read-line`, `--index` and `--open`, which already
   print what a program knows and exit without auditing.

5. **Round groups are the unit of a cut.** `interstice` has `R47-W3, R47-W1, R47-W2,
   R47-W4, R47-M` in a row. The heading regex `^## (R(\d+))\b` reads all of them as
   R47, and check 16 treats consecutive same-n headings as one round. A cut must never
   fall inside such a group.

`e2e-harness` (241 lines, 46KB, `status: implementing`, last transition at line 104)
is under both limits and needs no rotation. It is the control: the flag must say
"nothing to rotate" there.

## Design

**`audit.py <dir> --rotate-plan`.** It prints the cut, the archive name, the `Stage:`
line to carry and the exact shell commands, then exits without auditing. Like
`--read-line` and `--as-status`, it **never writes**. The agent runs the printed
commands, and a shell copy moves 90KB verbatim at zero output tokens. Copying the same
text through `Write` is where a rotation could lose a line.

### Function: `rotate_plan(facts, spec_dir, today) -> tuple[int, str]`

It sits next to `read_line`. It parses `_log.md` the way `check_log_integrity` does:
headings are found on the comment-stripped text, so line numbers still match the raw
file.

1. **Size gate.** If the log is within both `LOG_MAX_LINES` and `LOG_MAX_BYTES`, print
   `nothing to rotate — <n> lines, <k>KB, under 800 lines / 80KB` and exit 0. Do the
   same when there is only one round group.
2. **Refusals (exit 1, one line each, no commands printed):**
   - the round ids decrease (check 16 already calls this a CONTRADICTION, and the
     archive name assumes they increase);
   - the file does not end in `\n` (BSD `sed` would add one, and `cmp` would fail);
   - the archive name already exists;
   - the slug contains `'` (the header is printed in single quotes).
3. **Groups.** Consecutive headings with the same numeric `n` form one group, and only
   a group's first heading line is a cut candidate. The preamble is the lines before
   the first heading.
4. **Cut rule.** Two new constants: `ROTATE_KEEP_ROUNDS = 5`, and a keep budget of
   `LOG_MAX_LINES // 2` lines and `LOG_MAX_BYTES // 2` bytes.
   - A *real transition* is a line matching `check_log_stage`'s regex where
     `from.strip('`') != to.strip('`')`.
   - If there is a real transition outside the first group, and keeping that group to
     the end plus the preamble fits the budget, cut at that group. This is
     `handoff.md`'s rule, unchanged.
   - Otherwise, keep the last `min(ROTATE_KEEP_ROUNDS, groups − 1)` groups. This is
     `handoff.md`'s own fallback, made deterministic at 5, which matches the R42
     precedent. The plan says which branch it took and why. For example, the
     transition at R40 would keep 85KB, which is over 40KB.
5. **Stage carry.** If `status` is not `draft` and no `**Stage:**` line is left in the
   kept part, print the line the rotate entry must carry:
   `` **Stage:** <status> → <status> — carried, not a transition; the last real one (`<from> → <to>`, R<n>) is in <archive> ``.
   Without it, `check_log_stage` raises "records no `Stage:` transition", which was the
   second DRIFT R42 hit.
6. **Names.** The archive is `_log-R<first archived n>-R<last archived n>.md`. The
   rotation round is the last group if its heading carries `· rotate`. Otherwise the
   plan prints the stub to open: `## R<last+1> · <today> · <agent> · rotate`. Use
   `--today` when given, as `--open` does.
7. **Output.** A short header block, then one fenced `sh` block, then the after-steps:

   ```
   # rotate plan — _log.md (570 lines, 106KB, blob <sha7>)
   cut:     line 521, before `## R58 · …` — last 5 rounds kept (no Stage transition in _log.md; R42's is carried)
   archive: _log-R37-R57.md — R37–R57, lines 15–520, 93KB
   keep:    lines 1–14 + 521–570 — 64 lines, 13KB
   round:   open the stub first: `## R63 · 2026-10-26 · <agent> · rotate`
   stage:   carry `**Stage:** reviewed → reviewed — carried, …` in the rotate entry
   before:  `audit.py <dir> --open` — its open findings are the `Carried open:` index
   ```
   ```sh
   cd <spec dir> && \
   test "$(head -n 520 _log.md | git hash-object --stdin | cut -c1-7)" = <sha7 of lines 1–520> && \
   { printf '%s\n' '# Handoff log — <slug> — archive R37–R57' '' '<3 fixed header lines>' '' '---' ''; sed -n '15,520p' _log.md; } > _log-R37-R57.md && \
   { sed -n '1,14p' _log.md; sed -n '521,$p' _log.md; } > _log.md.kept && \
   { sed -n '1,14p' _log.md.kept; sed '1,8d' _log-R37-R57.md; sed '1,14d' _log.md.kept; } | cmp - _log.md && \
   mv _log.md.kept _log.md && echo rotated
   ```
   ```
   after:   `audit.py <dir> --read-line _log-R37-R57.md` → the record for `Archived:` and `Edits:`; then the audit
   ```
   The commands form one `&&` chain, with no `set -e`, so pasting them into a
   persistent shell cannot kill it. The `test` guard checks that the lines above the
   cut have not changed since the plan was printed. Appending, such as opening the
   stub, is allowed, because `'521,$p'` reads to the end of the file at run time. The
   `cmp` step is the byte-for-byte check from `handoff.md`, run against the live
   original **before** `_log.md` is replaced. With an empty preamble, the
   `sed -n '1,0p'` parts are left out.
8. **Wiring.** Add `ap.add_argument("--rotate-plan", action="store_true", …)` and an
   early-exit branch in `main()` after `--read-line`. Add `[--rotate-plan]` to the
   module docstring's usage line. The check-16 POLISH remediation becomes:
   `` rotate, never summarize: `audit.py <dir> --rotate-plan` prints the cut, the archive and the commands — references/handoff.md §Rotating the log ``.
   That change is the actual fix for "ignored": the finding now names its first
   command. `--json` for the plan is out of scope.

### Docs (implementer)

- `references/handoff.md` §Rotating the log, step 2: name the flag. Say that a
  transition means `from ≠ to`, that a cut keeping more than half the limit falls back
  to the last 5 rounds, and that the archive is `_log-R<first>-R<k>.md` (not `R1`) for
  a second rotation.
- `references/audit-protocol.md` L220: add the flag beside the section link.
- `SKILL.md` handoff row (L52): add `--rotate-plan` when check 16 says rotate.
- `README.md`: a release row (minor, v1.21.0) and the clone tag on L32, per the
  repo's release convention.

## Target files

- `scripts/audit.py`: `ROTATE_KEEP_ROUNDS`, `rotate_plan()`, the argparse flag and
  `main()` branch, the usage docstring, and the POLISH text at L3926.
- `tests/test_audit.py`: two new functions registered in `main()`, plus one more
  assertion inside `log_size_counts_bytes`.
- `references/handoff.md`: §Rotating the log, step 2.
- `references/audit-protocol.md`: L220.
- `SKILL.md`: handoff row, one phrase.
- `README.md`: release row and clone tag.

No new fixture directory. Both tests generate their log in a temp copy of
`tests/fixtures/matrix` (which has `status: reviewed`), as `log_size_counts_bytes`
already does. A committed 90KB fixture would weigh more than the test.

## Acceptance

The command the implementer makes pass:

```sh
for t in tests/test_*.py; do python3 "$t" || exit 1; done && python3 tests/test_audit.py | rg -o '^\d+/\d+ assertions passed'
```

Expected last line: `313/313 assertions passed`. The baseline is 311/311, and the two
new functions add one assertion each. `test_render.py`, `test_ship.py` and
`test_triage.py` stay green.

Tests to add in `tests/test_audit.py`:

1. **`rotate_plan_round_trips()`.** A synthetic log: a 3-line preamble, rounds
   R37–R96 at about 1.5KB each (about 90KB, under 800 lines), and
   `**Stage:** draft → reviewed` in R40. The fifth-from-last group, R92, is written as
   two headings `## R92-W1 …` / `## R92-W2 …`.
   - The plan names `_log-R37-R91.md`, cuts at the `## R92-W1` line (never `R92-W2`),
     reports the fallback branch, and prints the `reviewed → reviewed` carry line.
   - Run the fenced `sh` block with `sh -c` in the temp dir. Then, in Python,
     preamble + archive minus its header + kept rounds must equal the original bytes.
   - The audit `--json` no longer contains "past what one read". After the test
     appends a rotate entry (the `--read-line` output for the archive,
     `Log read through: R96`, the printed `Stage:` line), check 16 does not report
     "records no `Stage:`".
   - **Stale plan:** print a plan, insert one line above the cut, run the commands.
     They must fail at `test`, leave `_log.md` byte-identical, and create neither the
     archive nor `_log.md.kept`.
   - **Name taken:** create `_log-R37-R91.md` first. The plan must exit non-zero, name
     the file, and print no commands.
2. **`rotate_plan_cut_rule()`.**
   - The same log with the transition moved to R90: the plan cuts at R90 (the kept
     part is about 10KB, within budget) and prints no carry line.
   - A 20-round log under both limits: exit 0, `nothing to rotate`, no `sh` block.
3. **Inside `log_size_counts_bytes`:** the POLISH's remediation contains
   `--rotate-plan`.

Manual check on the real set (read-only, a snapshot as of `_log.md` at 570 lines /
106,069 bytes): run `python3 scripts/audit.py <Hackathon>/docs/features/interstice
--rotate-plan --repo-root <Hackathon>`. It should cut at line 521 (R58) with archive
`_log-R37-R57.md`, keep 64 lines / 13KB, and carry `reviewed → reviewed`. Run the
printed commands in a `cp -R` copy under the scratchpad and get `rotated`. On
`e2e-harness` it should say `nothing to rotate`.

## Risks

- **This changes the rule.** v1.20.0 just made "before the last `Stage:` transition"
  the cut. The budget fallback and `from ≠ to` refine it, and the reviewer should
  agree with Diagnosis 2 before merging. If they do not, the flag still works with the
  rule as written, but on `interstice` the result stays over the limit.
- **`sed` portability.** Only `sed -n 'a,bp'` and `sed '1,Nd'` are used, which behave
  the same in BSD and GNU sed. A missing final newline is refused up front, not left to
  fail at `cmp`.
- **The plan goes stale between printing and running.** An edit in place above the cut
  is caught by the prefix-blob `test`. An append below it is allowed on purpose.
- **Comments.** A `<!-- … -->` holding a `## R` line is skipped, as check 16 skips it.
  The commands copy raw bytes, so the comment travels with its round.
- **Archived open findings.** `--open` reads `_log.md` only. A finding archived without
  being carried disappears from `--open`. The plan's `before:` line points at the
  existing `Carried open:` procedure. It does not automate it, because whether a
  finding was re-judged is a judgment call.
- **Scope creep.** Writing the files from Python (`--rotate`) is the tempting next
  step. It breaks the rule that the auditor never writes. Leave it out.

## Tier

agy-medium: one self-contained, read-only function in an existing pattern
(`--read-line`/`--open`). The byte-exact part is checked by `cmp` in the generated
commands and by a round-trip test, so a mistake fails loudly instead of losing a line.
