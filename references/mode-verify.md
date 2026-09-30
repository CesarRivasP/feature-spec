# `verify <slug>` — is the registry true?
Ask intake set C first (`references/intake.md`): who runs the procedure, on which device and **which build type**, and whether the decisive log line is readable there. A procedure written for hardware nobody has, or for a debug build when the defect is release-only, comes back inconclusive and costs the full build/install/navigate cycle anyway.

**Check the preconditions BEFORE the run, and abort if one is missing.** A confound was marked before a device run and the run happened anyway; it cost a retraction and a full build/install/navigate cycle. A run whose precondition cannot be met produces `evidence.outcome: aborted_no_conditions` + `aborted_because:`, `basis:` stays `asserted`, and **there is no `value:`** — the number is not reinterpreted afterwards, because the qualification would live in one document and the number in three. The behaviour happened correctly once, on 2026-09-15, and was written down nowhere; it is a field and audit check 32 now.

Reconcile `_facts.yml` against observations from a device run or instrumented session. Confirmed hypotheses become `basis: measured` with their `evidence:` filled; refuted ones become `status: dead` (kept, never overwritten — a dead hypothesis stops the next session re-deriving it).

**A measurement is a run, not a number.** Every confirmed entry records `n:` (runs behind the value), `spread:` (the observed extremes, once `n > 1`) and `conditions:` (the axes `_profile.yml conditions_required:` names as varying here). Three retractions came out of one hole — `n=1` read as a constant — and the most expensive one came out of the other: four events varying 2.3x in bitrate, and not one number in either of two related sets recording which event produced it. `references/evidence.md` §A measurement is a run, not a number; checks 30 and 31.

**An absence is not an observation until the path is known to emit.** Concluding "this does not happen in production" from an empty query asks *"does the path emit?"*, never *"is there a signature?"* — the failure under investigation raised no error and was invisible by construction, at `sampleRate: 0.2`. A `value` recording nothing found declares `absence: true`, names `emits:` and states `sample_rate:`. Check 33.

**Then walk the cascade, in both directions.** When an id goes `dead` or changes `basis`, every entry that `depends_on` it is revisited — `defects[]` as well as `alternatives[]`:
- an `alternatives[]` entry discarded *by reasoning* on a premise that just died flips to `outcome: reopened`. The discard is void, not merely doubtful.
- **any entry still `open` writes its `outcome:`** — the answer it now has. Staying `open` is a perfectly valid resolution and is itself an outcome worth stating; *`open` with no `outcome:` after its dependency died* is the finding, because from outside the two are indistinguishable.

**`changes[]` rests on hypotheses too.** An entry deferred or shaped *because* a defect is unproven declares `depends_on: [defects.<id>]`; when that defect goes `dead`, `fixed` or `measured`, revisit the entry and set `reviewed_on:` (check 34). And a defect closes with one of `open | fixed | dead` — refuted is `dead`, confirmed is `basis: measured` until the fix lands. Any other word (`resolved`) is read by no rule, so nothing depending on it is ever revisited. *Real case:* `C11` was deferred until `D1` was verified; `D1` resolved false, the deferral became permanent, and the stakeholder doc described `D1` as open for nineteen more rounds.

*Real case:* `F2`'s note said, in prose, that what decided whether it mattered was `F3`. A later round measured `F3` and left it `dead` — a clean round, with evidence. Nobody returned to `F2`; its note still claimed "not measured" about something measured hours earlier, and the set shipped with a clean audit. The arrow existed and nothing could follow it, because it was written in prose and not in `depends_on:`. That is now check 25; this is the other half.

**Then ask whether the PLAN still has the same shape.** A refuted hypothesis does not only correct the registry — it can move the fix. If `changes[]` gained, lost, or replaced an entry, the plan you are about to `sync` is not the plan `review` swept: re-run **`review`** first, then `sync`. Skipping that edge is how a spec ships a fix that never passed a gap sweep at all. If doc 02 already exists, `sync` is not enough either — a moved entry changes the plan's *shape*, and shape is what `implement` writes; regenerate the affected phases.

*Real case (React Native TV):* a device run killed the "the value stays 0" hypothesis and the fix changed from *seed the value* to *stop a stale sample from overwriting it* — an early-return guard that did not exist when the sweep ran. Nothing re-swept it, and the guard landed **below** a sibling write of the same stale sample, leaving a second consumer still corrupted. Found in review, after implementation. See §Adding a check in `references/gap-sweep.md`.

**Before running it, check the oracle is still in the tree.** `verify` reads instrumentation, and a spec that scheduled removal at the end of its code phases has already deleted it — see `references/implementable.md` §Diagnostic log lines. Re-adding a confirmation emitter is a phase, not a patch.

`audit` asks whether the docs agree with the registry. `review` asks whether the plan is safe to build. **`verify` asks whether the registry is TRUE** — and it is the only one of the three that can fail after a clean `audit`. Run it before flipping `status: shipped`; gate G1 in `references/evidence.md` refuses that flip while a root cause is still `asserted`.

---

Every mode starts by reading `_log.md` from disk and opens its own entry before editing (`SKILL.md` §Modes, `references/handoff.md`). The rules every mode that writes is held to: `references/rules.md`.
