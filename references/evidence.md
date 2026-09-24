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

Those four fields say what came back. They do not say how many runs are behind it,
what varied while you were looking, or whether the run happened at all — see
§A measurement is a run, not a number for `n:`, `spread:`, `conditions:`,
`outcome: aborted_no_conditions` and `absence:`.

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

## A measurement is a run, not a number

`value:` records what came back. It does not record **how many times you looked**,
**under what conditions**, or **whether the run happened at all** — and every one of
those has produced a retraction.

Three retractions came out of the same hole: `n=1` read as a constant. One run, one
number, copied into three docs and then into a *second set*, where it arrived with no
bar on it and nothing saying there had ever been only one.

```yaml
evidence:
  how: device
  cmd: "<commands.force_stop> …"     # the numbered procedure
  date: 2026-09-15
  value: 3                           # what came back on the run being reported
  n: 5                               # runs behind it
  spread: "0..308 fallas"            # the observed RANGE, never the average alone
  conditions:                        # what you did not control and that varies
    stream_bitrate_bps: 8200000
    resolution: 1920x1080
    build: production-release-1.4.3
```

### `n:` and `spread:` — the bar around the number

`n: 1` is a legitimate measurement. **Silently** `n: 1` is not: one run reported as a
bare value is indistinguishable from a settled constant, and that is exactly how it
gets cited.

- `n:` is required on every `basis: measured` whose `how:` is a **run someone
  performed** — `device`, `log`, `sentry`. How many times a person repeated a
  procedure is never inferable from its output, so nothing downstream can recover it.
- `n: 1` with no `spread:` → the audit reports it (check 30). It is the lowest tier
  on purpose: inside its own set the number is still traceable to the one run someone
  did.
- **Cited from another set with `n: 1` → `DRIFT`.** That is where it turns into a
  constant. The citing set sees a number, a path and an id; it does not see that the
  parent measured it once. *Real case:* `limits.degradation_threshold_tiles` in a
  parent set — one run, no bar, and half a spec hanging off it.
- `n:` above 1 with no `spread:` → `DRIFT`. You observed a range and reported its
  midpoint. The range is the finding; the midpoint is a summary of it.
- `spread:` is the observed **extremes**, written as they came out —
  `"0..308 fallas"`, `"2 de 5 corridas no degradaron"`. An average with no range is
  the shape this rule exists to stop.

### `conditions:` — what you did not control

The most expensive finding in this file. Four events varied **2.3× in bitrate** (3.47
/ 6.76 / 8.01 / 8.20 Mbps) and **no number in either of the two sets recorded which
event it came from** — not the parent's threshold, not the base of the "2 tiles". Two
measurements taken under different conditions were compared as if they were the same
measurement, and the comparison decided the scope.

Which axes vary is a property of the **repo and its stack**, not of the feature, so it
lives in `_profile.yml conditions_required:` alongside the commands — the same split as
everywhere else: the profile says how this repo finds out, the registry says what came
back.

```yaml
# _profile.yml
conditions_required: [stream_bitrate_bps, resolution, build]
```

Every `device|log|sentry` measurement then carries those keys in
`evidence.conditions:`, and check 31 refuses the ones that do not. An empty
`conditions_required:` switches the check off — a repo where nothing varies says so,
it does not stay silent.

**Two entries linked by `depends_on:` whose `conditions:` disagree on a shared key is
a `CONTRADICTION`, always, with no profile involved.** The derived claim rests on a
comparison across a variable nobody held fixed.

### A run without its precondition produces no datum

The confound of one hypothesis was marked **before** the run, and the run happened
anyway. It cost a retraction and a whole device cycle. The number that came back was
not a weak measurement — it was not a measurement.

An attempted run whose precondition could not be met records the attempt and
**nothing else**:

```yaml
basis: asserted                      # unchanged. The run produced no evidence.
falsified_by: '…'
evidence:
  how: device
  date: 2026-09-15
  outcome: aborted_no_conditions
  aborted_because: 'the only event available was 720p; the claim is about 1080p'
```

- `basis:` stays `asserted`. An aborted run is not a measurement (check 32 →
  `CONTRADICTION` if it is paired with `basis: measured`).
- **There is no `value:`.** A value beside an aborted outcome is the reinterpretation
  this rule exists to forbid — check 32 reports it as a `CONTRADICTION`.
- `aborted_because:` names the precondition that was missing, in the terms of the
  claim. Required.

**It is not reinterpreted afterwards.** The temptation is to keep the number and
qualify it in prose; the qualification lives in one document and the number lives in
three. Record the abort, restore the precondition, run again.

*The behaviour already happened correctly once* — on 2026-09-15 the 1-vs-2-tiles
comparison was aborted because the only event available was 720p — **and it was
written down nowhere**, which is why it is a field now and not a habit.

### Absence of signal is not signal of absence

The four player buckets reach Sentry through `usePlayerActions.js:399 onError`. The
failure under investigation **raises no error**: it is invisible by construction, and
an empty query over it says nothing at all.

The check before concluding "this does not happen in production" is **"does the path
emit?"** — never "is there a signature?". A `measured` value that records an absence
declares it:

```yaml
evidence:
  how: log
  cmd: "<the query>"
  date: 2026-09-15
  value: '0 events matching player.error in 30d'
  absence: true                 # this value is the ABSENCE of a signal
  emits: 'usePlayerActions.js:399 onError -> Sentry'   # the path that WOULD produce it
  sample_rate: 0.2              # what fraction reaches the destination. null = unsampled
```

- `absence: true` requires `emits:`. **`emits: null` — nothing emits this signal —
  clears the key and is reported as a `DRIFT` anyway**, because an absence with no
  emitter is not evidence of non-occurrence and must drop to `basis: asserted`. That
  is the finding, not an annoyance: it is the case above.
- `sample_rate:` is required alongside it. At `0.2`, four out of five occurrences were
  never going to appear, and an empty result is the expected output of a system that
  *is* failing.
- A `measured` value shaped like an absence — `0 events`, `no results`, `[]`,
  `{"monitors":[]}` — with no `absence:` declared is check 33's `DRIFT`. *Real case:*
  `{"monitors":[]}` was read as data by a person and by nothing else; see check 26.

Same rule from the other side in `references/gap-sweep.md` §Concluding from silence.

## Derived evidence — a conclusion read off measurements already here

Not every `measured` is a run. Often the entry that settles a defect is the *reading*
of two or three limits that were each measured properly: "the bottleneck is CPU per
frame" is what `limits.frames_single_url` and `limits.frames_multi_url` say side by
side. Writing that as a run means inventing a `how:` and a `cmd:`, and then check 30
asks for an `n:` and a `spread:` — which already live in the limits.

```yaml
evidence:
  derived_from: [limits.frames_single_url, limits.frames_multi_url]
  date: 2026-09-23
  value: '32,1 contra 50,3 fps por tile con las mismas palancas'
```

- No `how:`, no `cmd:`. What there is to re-run is the sources' commands.
- **It inherits `n:`, `spread:` and `conditions:`** from its sources and does not repeat
  them. A copied bar is a second copy of one datum, and the second copy is never the one
  updated. A set citing a derived entry sees through it: if it rests on a single,
  spread-less run, check 30 says so, naming the run.
- **It is `measured` only while every source is.** A source that is `asserted`,
  `decided`, retracted, missing, or a chain that leads back to itself → `CONTRADICTION`
  (check 35). A source that was corrected → `DRIFT` unless the entry says the derivation
  survived the correction.

*Real case:* six defects of one research set went `measured` by naming the limits that
answered them inside `cmd:` as prose — `cmd: limits.a + limits.b`. The audit then asked
each for the `n:` and `spread:` those limits already carried, and they were copied by
hand.

## Retractions and corrections — never delete, never edit in silence

An entry that turns out wrong is the most instructive thing in the registry, for the
same reason a dead hypothesis is: deleted, it gets re-derived. Two shapes, depending on
whether it still holds:

```yaml
# it no longer holds
retracted_on: 2026-09-21
retracted_by: limits.purge_frees_proportionally   # what replaced it — or, if nothing:
# retracted_because: 'the probe ran with the cache half full; the zero was circumstantial'

# it holds, amended
corrected_on: 2026-09-23
corrected_by: limits.multi_url_arm_reaches_50fps_per_tile   # optional: what forced it
correction: 'the sign was backwards: the same url x4 is the HARD arm, not the easy one'
```

- Keep `basis:`, `evidence:` and the original text. The retraction or correction is
  written **beside** them, not over them.
- `correction:` is one sentence a citing set can quote. The long story goes in `note:`.
- **A citation that rests on a retracted entry without saying so is `DRIFT`** — in this
  set and in any set that cites it qualified (check 36). Say it in the same paragraph:
  name the replacement, or use the word.
- **A citation of a corrected entry is a candidate, not a finding.** A correction is
  usually made in place, so a sentence written after it is right as it stands; only a
  person reading it against `correction:` can tell which side it was written on.

*Real case:* `sports-multiview-grid` cites limits of the research set that measured
them. When the research corrected one, nothing told the grid.

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

  **Unless the decision to ship anyway is written down, with a date it expires.**
  There is a legitimate case G1 had no room for: the team knows the cause is
  unproven, ships the trimmed scope deliberately, and schedules the measurement.
  That is a real decision and it belongs in the registry:

  ```yaml
  accepted:
    by: <a person>            # never an agent
    decided_on: YYYY-MM-DD
    until: YYYY-MM-DD         # when the measurement is due
    because: '<why shipping now is the right call>'
  ```

  With a live `until:` the gate stands down and the audit **lists** the deferral
  and its expiry — not a finding, not silence. Within **14 days** of `until:` it is
  listed again, apart, as coming due, so the measurement gets scheduled instead of
  improvised the morning G1 bites (*real case:* four risks of one set, accepted
  together, all expiring on 2026-10-23). Past `until:`, G1 refuses again and
  names how late it is. `audit.py --today <date>` shows what it will say on a given
  day. Missing a field, or a `by:` that reads like a model id,
  and the block excuses nothing.

  It is a **deferral with a deadline, not an exemption** — the same rule the
  registry already applies to `changes[]`, where a postponement with no reopen
  condition is abandonment with better wording.

  *Real case, and the reason this exists:* a set shipped with its root cause
  asserted on purpose. The decision was recorded — in a `_log.md` round, and in an
  agent's memory. **Neither is read by the audit, the next agent, or the view**, so
  from outside "we looked and chose to wait" was indistinguishable from "nobody
  looked", and the same violation was re-derived days later by a different session.
  The log is narrative and a memory is private; the registry is contract, and only
  the registry has an expiry a program can check.
- **G2** `basis: asserted` with empty or absent `falsified_by:` → `DRIFT`.
- **G3** `falsified_by:` naming an observation with no `log_line:` that produces
  it (and no existing emitter) → `DRIFT`: the instrumentation is part of the
  spec, not something to bolt on when you get stuck. `log_line: null` is the
  author declaring the emitter must be built — that clears the gate. An absent
  key (nobody considered it) or a blank string does not.
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
