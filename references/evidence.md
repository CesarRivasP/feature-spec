# Evidence — separating what we measured from what we asserted

Verbatim copy from `_facts.yml` guarantees the docs agree with the registry. It
guarantees nothing about the registry. A false root cause copied into three docs
is three consistent lies, and `audit` reports `clean`.

`basis:` is the type system for that. Every entry that claims something about the
world carries exactly one.

## The three values

### `basis: measured`
Someone observed it. Requires:

    evidence: { how: <shell|git|device|log>, cmd: <command or procedure>,
                date: YYYY-MM-DD, value: <what came back, verbatim> }

`value` is the OUTPUT, not a paraphrase of it. For `how: log`, quote the decisive
line character-for-character — a paraphrased log line is an assertion wearing a
measurement's clothes.

### `basis: asserted`
We reasoned it. Requires `falsified_by:` — the concrete observation that would
kill the claim. Not "if it turns out to be wrong". A log line, a command's
output, a screen state.

If you cannot name what would falsify it, it is not a claim, it is a feeling.
Delete it or turn it into a question.

### `basis: decided`
Not a truth-claim: owner, target date, chosen constant name, accepted risk.
Nothing to measure, nothing to falsify. This value exists so decisions don't get
mislabeled `measured` and dilute the signal.

## What counts as `cmd` for each `how`

Commands are **sourced from `_profile.yml commands.*`**, not invented here. The
profile is per repo, the registry is per feature: the command belongs to the
profile, its output belongs to the registry. If the repo has no equivalent for
a `how`, the profile says `null` and that evidence is labelled `[MANUAL]` —
never a plausible-looking command nobody has run.

- **shell** — a command that runs here (`commands.tests`, `commands.lint`,
  `commands.build`). One symbol per entry (rule 3 below).
- **git** — file/repo state: `commands.file_tracked`, `commands.file_ignored`,
  `test -e <path>`, `rg -n '<path>' .git/info/exclude`.
- **device** — a NUMBERED procedure a human repeats, ending in an observation.
  Step 1 is `commands.force_stop`; the log filter is `commands.device_log`:

  ```
  1. <commands.force_stop>            # e.g. adb shell am force-stop {app_id}
  2. launch, wait for the home screen
  3. navigate to the screen under test — every input spelled out, in order
  4. perform the single action being measured
  5. observe: <the one thing that settles the question>
  ```

  Plus the observation in `value`. "It works" is not an observation. Neither is
  a screenshot when the claim is about internal state that a screenshot cannot
  show (native focus, cache contents, which component mounted).
- **log** — the log line, quoted, with the filter that surfaced it
  (`commands.device_log`).

## Rules

1. **Behavioral claims are claims.** "the framework puts focus on the first
   item" is exactly as falsifiable as "280 tests pass" and exactly as damaging
   when wrong. The `verified`-shape rule was written for numbers; it applies
   unchanged to behavior, with `how: device`. *Shape:* a claim about what a
   framework does by default, derived from reading its docs or its source
   rather than from watching it. *Real case (React Native TV):*
   `autofocus_grabs_first_focusable` was asserted, never measured, and false —
   focus went to a different rail and the user needed two extra presses.

2. **Cheap-to-verify state may never be `asserted`.** File existence, git
   tracking, gitignore / `.git/info/exclude` membership, whether a symbol exists —
   all are one command. `basis: asserted` on any of them is a finding, not a
   judgment call. Real case: "Sin commitear" was copied verbatim out of a sibling
   spec written 8 days earlier; both files were tracked.

3. **A scope-deriving `cmd` names ONE symbol.** No regex alternation.
   `rg 'VerticalCarousel|VerticalPaginated'` fuses two result sets into one list
   and every downstream attribution is a coin flip — real case: 3 screens filed
   under the wrong component. Need two symbols, write two entries with two
   commands. Same reasoning as the positive-scope rule: a `cmd` whose output
   cannot be attributed back to a single cause is not evidence.

4. **`depends_on` makes reasoning auditable.** Any `because:` / discard rationale
   derived from ANOTHER registry entry lists that entry's id in `depends_on:`.
   This is what lets `verify` reopen it mechanically when the premise dies,
   instead of relying on someone remembering why they rejected it.

5. **`asserted` is not shameful — unlabeled `asserted` is.** Specs are written
   before the evidence exists. The failure is not hypothesizing; it is a
   hypothesis sitting in the registry with the same visual weight as a
   measurement until the day it ships.

## Gates

- **G1** `status: shipped` is refused while any `defects[]` entry with
  `role: root_cause` or `role: contributing` is `basis: asserted`. The fix may
  well work; the registry has not earned the right to say why.
- **G2** `basis: asserted` with empty or absent `falsified_by:` → `DRIFT`.
- **G3** `falsified_by:` naming an observation with no `log_line:` that produces
  it (and no existing emitter) → `DRIFT`: the instrumentation is part of the
  spec, not something to bolt on when you get stuck.
- **G4** `basis: measured` with `evidence.date` predating the last commit to what
  it measures → `CONTRADICTION` (re-measure).

## `verify` — reconciling the registry with reality

Run after a device run or instrumented session. For each observation:

1. Match it to `defects[]` / `alternatives[]` entries by `falsified_by:`.
2. Confirmed → `basis: measured`, fill `evidence:`.
3. **Refuted → set `status: dead`** and record what actually happened as a new
   entry. Do not silently edit the old `claim:` — a dead hypothesis is the most
   useful thing in the registry, because it stops the next session re-deriving it.
4. **Cascade.** For every dead id `X`: every entry with `X` in `depends_on:` and
   `basis: asserted` flips to `outcome: reopened`. It was rejected on a premise
   that no longer holds; it is back on the table until re-argued against the new
   evidence. *Real case (React Native TV):* an alternative was discarded by
   reasoning derived from hypothesis D3; D3 died on device, and the discarded
   variant turned out to be the only structurally possible fix — the chosen one
   could not work at all, for a reason the device run made obvious and no amount
   of reading had.
5. `sync` the registry into the docs.

`verify` answers a question neither other mode does:

| | asks |
|---|---|
| `audit` | do the docs agree with the registry? |
| `review` | if built literally, what breaks? |
| `verify` | is the registry TRUE? |

It is the only one of the three that can fail after a clean `audit`.
