# Audit checks the script settles — [script]

The full text of every `[script]` check in `references/audit-protocol.md`, moved here verbatim in
v1.16.0. An audit does not read this file: `audit.py` runs each check and prints its failures as
findings. Read it when a finding needs explaining, disputing, or when a check is being changed —
its fixture in `tests/fixtures/` is the other half of that record.

### 10. Placeholders resolved — [script]
Scan `_facts.yml` for `—`, `TBD`, `?`, `xxx` in `owners.*`, `dates.*`, `schedule.*.owner`, `schedule.*.target`, and any tracking table in the docs.
- Placeholder in a set whose `status` is not `draft` → `DRIFT`. It's an unmade decision parked in the source of truth; it will come back as a review round trip. Resolve owners from `git shortlog -sne -- <changed paths>`, dates from the user.

### 14. Basis gates — [script]
Contract in `references/evidence.md`. These are the checks a clean consistency pass cannot make — they test the registry, not the copies of it.
- `status: shipped` with any `defects[]` entry `role: root_cause|contributing` still `basis: asserted` → `CONTRADICTION`. The set claims to know why the fix works and does not. Run `verify` before flipping the status.
  - **Unless the entry carries an `accepted:` block whose `until:` has not passed** — a recorded, dated decision to ship anyway. Then it is not a finding: the audit lists it under *Accepted risks, with their expiry*, and the verdict line counts it, so a clean run is never read as nothing-pending. Past `until:` → `CONTRADICTION` again, naming how many days late. A block missing any of `by` / `decided_on` / `until` / `because`, or a `by:` that reads like a model id, excuses nothing. Contract in `references/evidence.md` §Gates.
- `basis: asserted` with empty/absent `falsified_by:` → `DRIFT`. An unfalsifiable claim in the source of truth is the one that survives every audit and dies on device.
- `falsified_by:` naming an observation with no `log_line:` and no existing emitter → `DRIFT`. The instrumentation is spec, not an afterthought — added reactively, it costs a whole extra build/run cycle. `log_line: null` is the author declaring the emitter must be built and clears the gate; an absent key or a blank string does not.
- `alternatives[]` entry with `outcome: discarded`, `basis: asserted`, and a `depends_on` id whose `status: dead` → `CONTRADICTION`. It was discarded on a premise that no longer holds; `verify` should have reopened it.
- A `because:` / discard rationale that paraphrases another registry entry but omits `depends_on:` → `DRIFT`. The dependency exists whether or not it is written down; unwritten, the cascade cannot run.

### 14b. Accepted risks coming due — [script]
Part of check 14's G1. A live `accepted:` block is listed under *Accepted risks, with their expiry*; one whose `until:` falls within the next **14 days** is listed again, apart, under *Accepted risks due within 14 days*, and the verdict line counts them (`4 accepted risk(s) with a due date, 4 due within 14 days`). Still not a finding — a risk expiring today is still live — but the list someone has to act on this week is no longer the same list as the one due next year.

*Real case:* four risks of one research set were accepted together and all expire on 2026-10-23. Printed identically to any other live deferral, they read as handled until the morning G1 refuses all four at once.

### 17. Doc size — [script]
`wc -l` every file in `docs[]`.
- >500 lines → `POLISH`: approaching the split threshold. Split NOW, on the next top-level phase boundary, before more cross-refs are written against the current numbering.
- >600 lines → `DRIFT`: split overdue. Crossing this mid-authoring means renumbering sections and re-qualifying every cross-ref by hand, in the middle of writing. Procedure in `references/doc-pattern.md` §Splitting an oversized doc.

### 18. Anchors resolve — [script]
Check 13 verifies an edit **has** an anchor. Nothing verified that the anchor **resolves**. Every `file:line` in `_facts.yml` and in prose: (a) the path resolves from the repo root, (b) the file exists, (c) the line is within range.
- Bare filename with no path (`index.ts:18`, `config.toml:7`) → `DRIFT`. In a repo with 267 files named `index.mjs` it resolves to nothing.
- File missing, or line past end of file → `CONTRADICTION`.
- **An anchor that climbs out of the checkout (`docs/../../outside/x.ts:9`) → `DRIFT`, and nothing is opened.** A registry travels between repos and agents, so every path in it is input: joined onto the repo root, a `../` resolves outside exactly as written, and the audit then reports the line count of a file it was never pointed at. Confine before you open.
- **`_log.md` is excluded and must stay excluded.** It is append-only history recording what was true then; its anchors are never corrected. A sweep that "fixes" them is rewriting the record.

Real case: in one set, five anchors were stale — `chat.ts:341`→`:342`, `InputForm.tsx:120`→`:129`, `useFileUpload.ts:45`→`:67` — every one of them moved by the author's **own later edits inside the same session**. The sibling set carried eight bare anchors. This is the single most frequent finding in this file.

### 19. Registry shape vs template — [script]
The top-level keys of `_facts.yml` ⊆ those of `templates/_facts.yml.tpl`. Unexpected key → `DRIFT` (either it belongs in the template, or an edit put entries somewhere they do not belong).

Real case: editing a registry by hand deleted the `alternatives:` key. Its four entries A1-A4 reparented in silence under `defects:`, which went from 9 to 13. **The audit passed clean** — the YAML was valid, every datum survived, and nothing noticed a third of the registry had changed category. Compare against the **union of the template**, never against a hand-written list of keys.

### 20. Declared paths exist — [script]
Check 9 detects unregistered sibling docs. Nothing verified that the paths the registry **declares** resolve. Every `changes[].file` and `related_docs[].file` exists on disk → otherwise `CONTRADICTION`.

Three exceptions, all **declared in the registry, never inferred**:
- `where: external` — the change is real but has no file here (a cron job, a dashboard setting). Real case: `file: "cron.job jobid 1 (comando SQL, no vive en el repo)"`.
- `kind: deferred` / `kind: moved_out` — decided against, so the file is absent by design.
- a `changes[]` file the set has not created yet, while `status:` is below `implementing`.

A path that resolves **outside** the repo root is a fourth outcome and not one of the three exceptions: `DRIFT`, reported as escaping rather than as missing, and never stat'd. Whether such a file exists is not this audit's business — see check 18.

### 21. Registry ids ↔ prose — [script]
Check 1 covers "datum in ≥2 docs but not in the registry". Both inverses were missing.

- **Registry entry no prose doc mentions, by id or by value → `DRIFT`.** Measured, correct, and dead: nobody reads it because no doc names it. Real case: 4 in one set, **7** in a sibling that had never been through a mechanical audit. Citation *by value* counts — nobody writes `limits.cloudflare` inline, they write `100` and `524`.
  - **Exempt: an entry kept as history** — `retracted_on:` (check 36) or an `acceptance[]` criterion with `status: retired` (check 26). They stay in the registry precisely so they are not re-derived and so old citations keep resolving; demanding that some doc still cite them would push authors back to deleting them.
- **Prose citing an id the registry does not define → `DRIFT`.**
- **Prose citing `container.id` where that id lives under a *different* container → `CONTRADICTION`.** This is check 19's failure seen from the other side, and it is the one that catches a reparenting after the fact: the entry survived, its category did not.
- **Prose citing a container the registry does not have at all → `CONTRADICTION`.**

**Cross-set references are legitimate and are excluded.** A citation qualified with the owning set — `` `docs/features/chat-document-upload/_facts.yml` defects.D6 `` or its bare slug — is not dangling. Convention: refs between sets are **always** qualified, and a local mirror id is **never** created. Real case: a `D4_ajeno` mirror was invented to make a sibling's defect locally referenceable, the owner then changed, and it had to be renamed across four files. If a set must track a sibling's entry locally, it is an entry with an explicit `owned_by:` and **the same id as in the owning set**.

### 22. Phase numbering — [script]
`rg '^### Fase [0-9]+'` over doc 02: numbers unique and without gaps. Duplicate → `CONTRADICTION`; gap → `DRIFT`.

Real case: a "Fase 8" was inserted into a doc that already had a Fase 8 and a Fase 9. Caught by re-reading headings by hand, not by the audit — and a phase number is how doc 02 is navigated and cited.

### 23. `changes[]` lifecycle — [script]
Every entry declares `kind:`. Missing → `DRIFT`: an unclassified change is an undecided one, and `implement` refuses to run on it.
- `kind: deferred` with no `reopens_when:` → `DRIFT`. **A deferral with no condition of reopening is not a deferred change: it is a change abandoned with better wording.** Also requires `deferred_because:` naming a `decisions.*` key.
- `kind: deferred` whose `reopens_when:` states no measured value → `DRIFT`. *"when traffic grows"* is an opinion and nothing reopens on an opinion. *"the daily peak passes ~200 distinct users. Today: 5"* is a condition someone can check.
- `kind: moved_out` with no `moved_to:` → `DRIFT`.
- `kind: pending` with no `transferred_from:` → `DRIFT`.

### 24. `evidence.cmd` is runnable verbatim — [script]
Check 1b said "`cmd` not runnable in this environment → note it". **Too soft.** A `basis: measured` whose `cmd` cannot be pasted and re-run → `CONTRADICTION`, not a footnote. Three shapes, all found passing an audit:
- a prose reference — `` cmd: "ver `limits.storage_list_max_limit.evidence.cmd`" ``
- placeholders — `cmd: "curl .../<proj>/<uuid>"`
- a description of what to do, formatted as if it were a command

Real case, and the reason the severity is `CONTRADICTION`: a defect carried `basis: measured` and was **inverted** — it asserted that two names collide when they do not, and that widening the charset *increases* collisions when it reduces them. It survived for months precisely because its `cmd` was a placeholder and could never be re-run. A false `measured` propagates to all three docs with perfect fidelity; a runnable `cmd` is the only defense against it.

Apply **only** when `evidence.how` is executable (`shell|git|sql|psql|bash|curl`). With `how: device|log|sentry` the `cmd` points at a procedure or a UI and is not a placeholder. And `%{http_code}` / `%{time_total}` are curl's own `--write-out` directives, not unfilled slots — a naive `{...}` sweep reports every measured curl probe in the set.

### 25. Declared dependencies — [script]
An entry whose `claim`/`note`/`because` names another registry id in prose but does not declare it in `depends_on:` → `DRIFT`. The arrow exists either way; undeclared, the cascade in `verify` cannot follow it.

Real case, and the twin of check 14's `alternatives[]` gate: `F2` (open) carried the note *"Lo NO MEDIDO —y lo que decide si esto importa— es qué se sirve después: **ver `F3`**"*. A later round measured `F3` and left it `dead` — a clean round, with evidence. **Nobody went back to `F2`.** Its open question already had an answer, its note still said "lo NO MEDIDO" about something measured hours earlier, and the set was marked `shipped` and passed the audit **clean**. `F2` named `F3` in prose and not in a field, so no tool could follow that arrow.

### 26. Acceptance state — [script]
Every `acceptance[]` criterion carries `status: written | executed | approved | retired`. A plain string is still valid and reads as `written`, so older sets keep auditing — but a set cannot reach `shipped` on strings alone.
- `status: shipped` with a criterion `written` or with no status → `CONTRADICTION`.
- `shipped` with a criterion `executed` but not `approved` → `DRIFT`. Someone ran it; nobody signed it off.
- `approved` with no `verified_on:` → `DRIFT`. An approval with no date cannot be checked for staleness.
- **Any other value → `DRIFT`, and `CONTRADICTION` once the set is `shipped`.** An unknown value used to match no rule and pass `shipped` in silence — a gate failing open (§Enum fields). It is not guessed into `approved` because it looks like it. *Real case:* a shipped research set carried `status: verified` on four criteria, and the audit read nothing into them.
- **`retired` does not block `shipped`.** It is the way out for a criterion that stopped being reachable or relevant — a trimmed scope, a question answered by design — without deleting it. It needs `retired_on:` and `retired_because:`; missing either → `DRIFT`, **at every stage**, because a retirement is a decision and one with no date and no reason cannot be revisited. Citations of a retired criterion still resolve (check 21) and are not a finding: saying "AC6 was retired" is exactly what a doc should be able to do. Check 6's parity leaves retired criteria out of the Definition of Done.
  *Real case:* to ship a research set, AC6, AC12 and AC13 had to leave `acceptance[]`. The only mechanism was deleting them from the registry and rewriting their mentions in docs 01 and 02 by hand, so check 21 would not report them dangling — history destroyed to satisfy a gate.
- **A set where NO criterion carries a status collapses to one finding, not N.** It predates the field, and reporting each of fifteen identical misses buries the other contradictions in the same set — the wall this file's §Stage gating exists to prevent, one level down. A set where *some* criteria carry a status and others do not is the opposite case and is reported per criterion: somebody adopted the field and skipped items, and each skipped one is a specific criterion nobody verified.

Two real cases, and the second is why this is a check and not a paragraph.

An E2E step was executed and approved and the fact lived **only** in prose inside a log entry. Later entries kept saying it was pending. Nobody lied — there was nowhere to write it, and the log is append-only, so the last mention wins even when it is the oldest.

Then: a heartbeat was discarded — the substitute covering "the cron stopped running" — and the decision was recorded correctly in `_log.md`. `acceptance[]` kept **two criteria nothing could satisfy**, one annotated *"this is THE test of the set: it is the only path by which anyone finds out the cron stopped"*. The set was marked `shipped` that way, and **the audit passed clean**, because no check compared `acceptance[]` against reality. Verified afterwards: the monitor query returned `{"monitors":[]}` and the merged code sends no check-in.

**The log is narrative; `acceptance[]` is contract.** Recording a decision in one is not propagating it to the other. And note the recurrence: the rule against this was already written, in prose, in `references/gap-sweep.md`, two days before it happened again in the same set.

> **Never name a date field `on:`.** YAML 1.1 reads `on`/`off`/`yes`/`no` as booleans, so `on: 2026-08-30` lands under the key `True` and every lookup for `"on"` misses. The field is `verified_on:`. This was found by a test, not by review.

### 27. Dead-dependency cascade — [script]
Check 14 reopens a *discarded* `alternatives[]` entry whose premise died. This is the other half, and the more common one: an entry with a `depends_on` target now `status: dead`, still `open`, with no `outcome:` → `DRIFT`.

Real case: `F2` depended on `F3`. A later round measured `F3` and left it `dead` — a clean round, with evidence and a cleaned-up probe. **Nobody returned to `F2`.** Its open question already had an answer and its note still said *"lo NO MEDIDO"* about something measured hours earlier. The set was marked `shipped` and passed the audit clean, because no check looks at whether an entry's note is still true.

Remaining `open` is a perfectly valid resolution — `F2` stayed open as an accepted risk. **`open` with no `outcome:` after its dependency died is the finding**, because the two are indistinguishable from the outside.

- **A `defects[]` `status:` outside `open | fixed | dead` → `DRIFT`.** This check reads `dead` and check 34 reads `dead` / `fixed`; any other word closes the entry where no rule can see it, which is §Enum fields one level down. A refuted hypothesis is `dead`. A confirmed one is `basis: measured` and stays `open` until its fix lands, then `fixed`.
  *Real case:* six defects of one set closed as `status: resolved` — two of them **false**, one with a whole component deferred on it. Not one dependant was revisited, and the set audited clean for fourteen rounds.

### 29. Provider behavior is observed, not described — [script]
`evidence.how: provider-behavior` claims what a third party actually does. Its `value` must be an **observed HTTP response** — status code and body. A `value` recording no status code → `CONTRADICTION`.

Real case: a claim about a file-type filter was corrected **twice, in opposite directions** — first understating the defence (*"only validated client-side"*), then overstating it (*"a tampered client cannot bypass it"*). Both times the error was reasoning about the provider's **configuration** instead of executing the flow. A configuration is what you asked for; behavior is what you get. `references/gap-sweep-web-baas.md` already warned about this class; the registry had no way to mark it.

### 30. Sample size and spread — [script]
Contract in `references/evidence.md` §A measurement is a run, not a number. `value:` says what came back; nothing in the four-field shape says **how many times you looked**.

- **`basis: measured` with `how: device|log|sentry` and no `n:` → `DRIFT`.** Those three are a run a person performed, and how many times they repeated it is not recoverable from the output. `shell` and `git` are exempt: a command's output carries its own repeatability, and demanding `n:` on every `git ls-files` would bury the cases that matter.
  - **A set where NO evidence carries `n:` collapses to one finding**, exactly as check 26 does for `acceptance[].status`. The field is newer than the set; reporting fifteen identical misses buries the contradictions beside them. A set where *some* measurements carry it and others do not is the opposite case and is reported per entry — somebody adopted the field and skipped runs.
- **`n: 1` with no `spread:` → `POLISH`.** The lowest tier, on purpose: inside its own set the number is still traceable to the one run someone did. The taxonomy below has three names and this is the one that fits — it is a *warning*, and the tier above is reserved for the case where the single run leaves the set.
- **`n:` above 1 with no `spread:` → `DRIFT`.** You observed a range and reported its midpoint. The range is the finding; an average with no bar is the shape this check exists to stop.
- **A prose citation of ANOTHER set's entry whose `n:` is 1 → `DRIFT`.** Cross-set refs are qualified by the owning registry's path (check 21), so the script resolves that path, loads the sibling, and reads the entry's `n:`. This is the tier the local case is not: the citing set sees a number, a path and an id — it does not see that the parent measured it once, and from here the number reads as a constant.

Real case, and the reason this is four rules and not one: **three retractions, one hole.** `n=1` read as a constant. `limits.degradation_threshold_tiles` in a parent set was a single run with no bar, cited by a second set, with half a spec hanging off it.

### 31. Conditions of the run — [script]
The most expensive finding in `references/evidence.md`, and the one nothing could have caught: four events varied **2.3× in bitrate** (3.47 / 6.76 / 8.01 / 8.20 Mbps) and **no number in either of two related sets recorded which event produced it** — not the parent's threshold, not the base of the "2 tiles". They were compared anyway, and the comparison decided the scope.

Which axes vary is a property of the repo and its stack, not of the feature, so the required keys live in **`_profile.yml conditions_required:`** — the same split as the commands: the profile says how this repo finds out, the registry says what came back.

- **`basis: measured`, `how: device|log|sentry`, and `evidence.conditions:` missing a key the profile requires → `DRIFT`**, naming the key. An empty `conditions_required:` switches the check off; that is a repo saying nothing varies here, out loud, rather than staying silent.
- **Two entries linked by `depends_on:` whose `conditions:` disagree on a shared key → `CONTRADICTION`.** No profile involved and never switchable off: the derived claim rests on a comparison across a variable nobody held fixed. This is the real case above, stated mechanically.

### 32. A run without its precondition produced no datum — [script]
A confound was marked **before** a device run and the run happened anyway. It cost a retraction and a full build/install/navigate cycle. The number that came back was not a weak measurement — it was not a measurement, and the damage was done when it got reinterpreted afterwards instead of discarded.

An attempted run whose precondition could not be met records `evidence.outcome: aborted_no_conditions` and nothing else.

- **`evidence.outcome:` starting `aborted` with `basis: measured` → `CONTRADICTION`.** An aborted run is not a measurement. `basis:` stays `asserted` and `falsified_by:` stays where it was.
- **An aborted `outcome:` alongside a `value:` → `CONTRADICTION`.** That value is the reinterpretation this check exists to forbid. The temptation is to keep the number and qualify it in prose; the qualification lives in one document and the number lives in three.
- **An aborted `outcome:` with no `aborted_because:` → `DRIFT`.** Name the precondition that was missing, in the terms of the claim.

The behaviour already happened correctly once — on 2026-09-15 a 1-vs-2-tiles comparison was aborted because the only event available was 720p — **and it was written down nowhere.** That is why it is a field and a check rather than a habit.

### 33. Absence of signal is not signal of absence — [script]
Four player buckets reach Sentry through `usePlayerActions.js:399 onError`. The failure under investigation **raises no error**: it is invisible by construction, and an empty query over it says nothing whatsoever. The check before concluding "this does not happen in production" is **"does the path emit?"**, never "is there a signature?".

- **`basis: measured` whose `value` is shaped like an absence — `0 events`, `no results`, `[]`, `{"monitors":[]}` — with no `absence:` declared → `DRIFT`.** *Real case:* that exact `{"monitors":[]}` is check 26's, read as data by a person and by nothing else.
- **`absence: true` with no `emits:` key → `DRIFT`.** The question was never asked.
- **`absence: true` with `emits: null` → `DRIFT`,** and this one is the finding rather than the nuisance: nothing emits the signal, so its absence is not evidence of non-occurrence, and the entry must drop to `basis: asserted`. Same pattern as check 14's `log_line: null` — an explicit null is a declaration, and here the declaration is decisive.
- **`absence: true` with no `sample_rate:` → `DRIFT`.** At `sample_rate: 0.2`, four of five occurrences were never going to appear and an empty result is the expected output of a system that *is* failing. `null` means unsampled and clears it.

The same rule from the other side — before the spec is built rather than after the query is run — is `references/gap-sweep.md` §Concluding from silence.

### 34. `changes[]` dependency on a revised decision or a settled hypothesis — [script]
Check 27 cascades from a `defects[]`/`alternatives[]` entry's `depends_on` target going `status: dead`. A `changes[]` entry can rest on a premise the same way, but `decisions.*` has no `dead` state — the registry's own convention is to edit `what:` **in place** rather than mint a new key, so a `changes[]` entry pointing at a path that premise no longer supports has nothing to cascade from.

`decisions.*` may carry `revised_on:` — set when `what:` is edited after the fact, instead of silently mutated. A `changes[]` entry may declare `depends_on: [decisions.<key>]` and `reviewed_on:`, the date a person last confirmed the entry still holds.

- **A `changes[]` entry's `depends_on` names a `decisions.*` key carrying `revised_on:`, and the entry has no `reviewed_on:`, or one older than `revised_on:` → `DRIFT`.** The premise moved and nobody came back to check whether the entry still points where it should.

*Real case:* a `changes[]` entry kept pointing at a directory a later decision had retired. Nothing in the registry connected the two — the decision's `what:` was simply edited — so the stale entry rode through `implement` unchallenged.

**The same arrow, from a hypothesis.** `depends_on:` on a `changes[]` entry may name a `defects[]` / `alternatives[]` id — `defects.D1` or bare `D1` — for an entry deferred or shaped *because* something is unproven.
- **The target is now `dead`, `fixed` or `basis: measured`, and the entry has no `reviewed_on:`, or one older than the target's latest date (`evidence.date` and the other `*_on:` fields) → `DRIFT`.** The premise has an answer; a deferral waiting on it may have just become permanent, or due.

*Real case:* `C11` was deferred until `D1` was verified. `D1` resolved **false** and the deferral turned from provisional into permanent. No check asked, and the stakeholder doc kept describing `D1` as an open hypothesis for nineteen more rounds.

### 35. Derived evidence — [script]
Contract in `references/evidence.md` §Derived evidence. `evidence: { derived_from: [limits.x, limits.y], date, value }` is a conclusion read off measurements already in the registry, not a run of its own. It needs no `how:` or `cmd:`, and it inherits its sources' `n:`, `spread:` and `conditions:` instead of repeating them — checks 30 and 31 skip it locally, and check 30's cross-set tier looks through it to the runs it rests on.

It counts as `measured` only while every source does:
- **A source that does not exist, or is not written `<container>.<id>` → `CONTRADICTION`.**
- **A source that is `asserted`, `decided`, or has no `basis:` → `CONTRADICTION`.** The derived value claims a certainty its inputs do not have — the same severity as a `measured` whose `cmd` cannot be re-run (check 24).
- **A source that is retracted (check 36) → `CONTRADICTION`.**
- **A `derived_from` chain that leads back to itself → `CONTRADICTION`.** At least one link has to be a run somebody performed.
- **A source that is corrected, and the entry does not mention the correction → `DRIFT`.**

*Real case:* six defects of one research set went `measured` by naming the limits that answered them inside `cmd:`, as prose (`cmd: limits.a + limits.b`). Check 30 then asked each of them for the `n:` and `spread:` that already lived in those limits, and the authors copied them — two copies of one bar, and the second one never updated when the first was.

### 37. Registry ids unique — [script]
An id names one entry for the life of the set.
- **Two entries of one list container (`defects`, `alternatives`, `acceptance`, `changes`) with the same `id:` → `CONTRADICTION`.** A retired or retracted entry stays in its list on purpose (checks 26, 36), so handing its id to a new entry is exactly this.
- **One id under two of those containers → `CONTRADICTION`.** A bare `depends_on: [X1]` can no longer say which it means.
- **`reserved_ids:` — an id held for an entry deleted before `status: retired` existed.** Reused → `CONTRADICTION`; reserved with no reason → `DRIFT`.

*Real case:* `AC21` and `AC22` were written in R3 and removed in R5, with a decision saying they return **verbatim** if it reopens. In R21 the same ids went to two new criteria. Caught reading a doc, not by the audit — and had the decision reopened, a recovered criterion would silently have meant something else. Worse than a gap in the numbering.

### 38. Source tree vs `changes[]` — [script]
Check 7 compares `changes[]` against the **documents**, by hand; check 20 asks whether each declared file **exists**. Nothing compared the disk against the registry, in the direction that matters once code is written: a file that exists and that the registry does not know.

`changes[]` is what `review` sweeps and what `implement` writes phases against. A file outside it is outside both.

`source_tree: { globs: [...], exclude: [{ glob, because }] }` declares, positively, the part of the tree this set owns — in a repo shared by several features, "every file" is not this set's scope. A `changes[].file` that is a directory covers every file under it.
- **A file matched by `globs:`, not excluded, that no `changes[].file` names or contains → `DRIFT`.**
- **An exclusion with no `because:` → `DRIFT`.** An exclusion is a scope decision; one with no reason quietly grows to cover whatever is inconvenient.
- **A glob that climbs out of the checkout → `DRIFT`**, and nothing outside is read.
- **No `source_tree:` in an `implementing` / `shipped` set with `kind: planned` entries → `POLISH`.**

Runs from `implementing` on, or earlier once `source_tree:` is declared or any entry carries `built_on:` (check 39).

*Real case:* ten components — built, tested, deployed to the device — — had no entry for **fifteen rounds**, while every audit came back `0 contradictions, 0 drift`. The set was consistent with itself and wrong about the world. The gap sweep could not have found a hazard in any of them in that window, because nothing told it the file existed.

### 39. `changes[]` built state — [script]
`kind:` is intent — planned, deferred, moved out. It says nothing about whether the thing exists. `built_on: YYYY-MM-DD` does.
- **`status: shipped` and a `kind: planned` entry with no `built_on:` → `DRIFT`.** Collapsed to one finding when no entry carries the field at all, as check 26 does for a set that predates it.
- **`built_on:` on a `deferred` / `moved_out` entry → `DRIFT`.** Either the lifecycle moved and `kind:` should say so, or the date is wrong.
- **`built_on:` that is not a date → `DRIFT`.**
- **`built_on:` while `status:` is below `implementing` → `DRIFT`.** The set forgot to flip, and every check gated on `implementing` — 20, 38 — is asleep. Below `implementing`, a `built_on:` whose file is missing is also reported here, since check 20 does not run yet.

*Real case:* after thirty rounds a real registry could not answer *"what is done?"*. Its author invented `built:`, missed it on two entries that were built, and a report counted **18 components where there were 20**. The same set stayed at `status: reviewed` through all thirty rounds of building.

### 40. Revision order — [script]
`dates.revisions[]` is **oldest first**. Every doc's changelog is **newest first**. The two are opposite by design, and that opposition is the trap: the natural anchor for inserting a revision is the most recent tag, and prepending there is right in a doc and inverts the registry — or the reverse.
- **Two revisions with one tag → `CONTRADICTION`.**
- **A revision listed after one it is older than (by date, or by the number in `v<n>`) → `DRIFT`.**
- **A doc's `## Changelog` listing a registry tag after one it is not older than → `DRIFT`.** Both shapes are read: `### <date> — <tag>` headings and `| <tag> | <date> |` table rows.
- **A changelog entry dating a tag differently from the registry → `CONTRADICTION`.** This is the half of check 2 a program can settle.

*Real case:* inverted **three times** in one set, each caught by reading and none by a check.

### 41. Provisional prose — [script]
`sync` propagates **values**. A sentence that was true when written — *"the repository contains no application code"*, *"no test has run here"* — has no value to propagate. It stays on the page, true-looking, for as long as nobody rereads it.

A sentence written against a state its author knows will change says so, inline: `[PROVISIONAL: <registry ref> YYYY-MM-DD]`. The ref is the entry whose change will make it false (`tests_baseline`, `changes.C1`, `defects.D3`); the date is when the sentence was written.
- **The ref moved after that date — `built_on:`, `evidence.date`, `revised_on:`, `corrected_on:`, `retired_on:`, `verified_on:`, `reviewed_on:` → `DRIFT`.**
- **The ref is settled outright — `dead`, `fixed`, `approved`, `retired`, retracted → `DRIFT`**, dated or not. Undated, `basis: measured` or a `built_on:` also settle it.
- **The ref names nothing in the registry → `DRIFT`.**

Fenced blocks are not read: a marker inside a code sample is an example.

*Real case:* the mock preamble of a test doc opened with *"the repository contains no application code"* and *"no test has run here"* for **fifteen rounds**, while 133 tests existed, and described a fake with a signature the interface no longer had. `references/implementable.md` allowed writing it against an empty repo and did not ask for it to be marked.
