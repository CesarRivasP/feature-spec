# Gap Sweep — does this spec, implemented literally, add new gaps?

The mechanical audit proves the docs agree with `_facts.yml`. It does **not** prove the spec is a safe thing to build. A spec can be 100% self-consistent and still ship a rate-limit dead end, an unauthenticated write path, and PII in a new store.

This sweep asks a different question: **an implementer follows this spec to the letter and changes nothing else — what breaks?**

Run it at the end of `new`, and as `review <slug>`. Every finding is either fixed in the registry+docs or written down as an accepted risk with a reason. Silence is not an answer.

## How to run it

For each entry in `changes[]`, classify it by kind (below) and answer that kind's questions. A question you cannot answer from the spec **is the finding** — the spec is underspecified at exactly that point, which is where the implementer will improvise.

**Then run the stack layers.** This file holds the kinds that exist in every codebase. Stack-specific hazards live in `references/gap-sweep-<layer>.md`, and which layers apply is `gap_sweep_layers:` in the repo's `_profile.yml`:

| layer | file | covers |
|---|---|---|
| `web-baas` | `gap-sweep-web-baas.md` | webhook receivers, RLS, SQL migrations, edge functions |
| `android-native` | `gap-sweep-android-native.md` | exported components, intents, permissions, background limits, R8, Room |
| `mobile-tv` | `gap-sweep-mobile-tv.md` | D-pad focus, remote input, low-end device memory |

No layer for this stack yet? Run the base sweep and say so in the output — a missing layer is a known blind spot, not a clean result. Writing one is ~40 lines and is the highest-leverage thing a new repo adds to this skill.

Output: one line per gap, `FUNCTIONAL` or `SECURITY`, with the failure scenario spelled out (inputs/state → wrong behavior). No scenario = not a finding, drop it.

**A clean sweep is clean *for the kinds that exist*, and says so.** The same rule as a missing layer, one level down: the kinds below are the ones this file has grown so far, not a closed taxonomy of how software breaks. A `changes[]` entry that fits none of them gets swept on its own terms and the output names it as unclassified. Reporting a bare "clean" over a change no kind covers is the failure this sentence exists to prevent — write the kind instead, it is ~10 lines.

## By kind of change

### Any call to a third-party API or auth provider
- **Rate limit?** What is it, numerically? What does the 2nd call inside the window return? Is that return value handled by an explicit branch, or does it fall into the generic-error path? A retry affordance that errors on retry is worse than no affordance — it's a dead end in the rescue flow.
- **Error branches enumerated?** List every error code the call can return that the UI must treat differently. Any code not in the list falls to generic — is that acceptable for each?
- **Silent fallback?** Does the provider have a config that, when wrong, produces *no error* (allowlists, default redirects, default regions)? Those never show up in logs. They must be verified by executing the flow, and the doc must say so.
- **Idempotency?** Can the user double-submit? Can the provider retry/redeliver? What is the dedupe key?
- **Offline / no network?** The call fails with no status code at all. Which branch catches that, and what does the user see?

### New persisted data (table, store, cache, file, preference)
- **PII?** Any field holding an email, phone, name, address, IP, device id. If yes: does it *need* to be plaintext? Prefer a hash plus a documented resolution path for the moment you actually need the value.
- **Retention?** Anything that grows per-event needs a stated fate, even if the fate is "keep forever, small".
- **Who can read it?** Name the access-control mechanism explicitly. "It's local" / "it's internal" is not a mechanism — see the layer file for what it means on this stack.
- **Migration from the previous shape?** An existing install has the old data. What happens to it on first launch of the new version — migrated, ignored, or crash?

### New UI affordance
- **Does it exist in the failure state it serves?** Trace: which error, which screen, which condition renders it.
- **What does the user see on each outcome?** Every branch of the underlying call maps to one visible state. A branch with no UI is a user staring at nothing.
- **Does it leak existence?** For anything keyed by email/username, the response and the timing must be identical whether or not the account exists.

### New "log it" / observability step
- **Who reads it, and when?** A log line nobody opens does not close a frente. If the whole point is that a failure currently passes silently, the destination must be something a person or a query actually reaches.
- **Does it log the untrusted value itself?** User-controlled text in a log destination that renders markup, or that an LLM later reads, is an injection surface.

### Deleting / relaxing a check
- What was the check protecting against? Is that threat now handled elsewhere, or accepted? Say which.

### Adding a check — a guard, an early return, a `return`/`continue`/`break`
The inverse of the kind above, and it fails differently. An early return **partitions the function**: everything *above* it keeps running on the very input you just declared untrustworthy. The diff looks like one line; the blast radius is every statement that precedes it.

- **What executes ABOVE the new return, on the same input?** Read the whole function, not the hunk. List every statement between the function's entry and the guard.
- **Which of those WRITE state?** Assignments to refs, shared values, module state, stores, out-params. Each one is now writing a value the guard exists to reject.
- **Who READS that state?** A write nobody reads is fine. A write feeding a second consumer means the guard fixed one symptom and left its sibling — often *worse* than before, because the two consumers now disagree on screen where they used to be consistently wrong.
- **What ELSE does the guard skip?** A `return` placed before a call skips *everything that call does*, not just the part you cared about. Enumerate the callee's side effects and say, for each, whether skipping it is intended.
- **Can the guard's condition get stuck?** A guard on a flag cleared by a *later* event freezes everything it protects if that event never arrives. State the stuck case and either bound it or accept it in writing.

A one-line answer to all five is fine. Not answering them is the finding.

## Cross-cutting sweeps

- **Bulk mutation on user records.** Any update/delete across a user collection must be specified with an explicit key list, never a bare predicate (`WHERE x IS NULL`, `filter { it.foo == null }`). The predicate that matches 16 records today matches 400 next month.
- **Secrets in the doc set.** Names of env vars / keystore entries belong in the registry; values never. If the spec asks a third party to hand over a secret, it must name the channel — and rule out the insecure one by name.
- **Untrusted text.** Data pulled from user-controlled fields (emails, names, uploads, stored rows, intent extras) and shown to an operator or an LLM is untrusted. Say so where it's read.
- **Every consumer of the corrupted datum.** A defect corrupts a *value*, not a file. Before accepting a fix, name every place that value is written and every place it is read — then say which of them the fix covers. `changes[]` is organised by file and will not ask this for you. `references/implementable.md` §Wire every constant end to end encodes the same "N sites, you touched 1" failure for new constants; this is that rule generalised to the data an existing defect flows through. Two shared values fed by one event, a store read by two screens, a ref consumed by three handlers — each is a place the fix either reaches or silently does not.
- **New dependency on an external owner.** Anything the team cannot execute alone gets `blocked_by:` in the registry, an owner, and a date that reflects *their* clock. Otherwise the plan quietly assumes a stranger's cooperation.

## Trimming scope — what a deferral silently breaks

Cutting a `changes[]` entry down to `kind: deferred` or `kind: moved_out` is not a subtraction. It is the same event as a refuted hypothesis in `verify`, from the other direction: something the rest of the set was resting on stopped being true, and nothing follows that arrow on its own.

When an entry leaves the build, re-walk two lists before moving on:

- **`acceptance[]`** — every criterion that depended on the deferred entry. Each one is either (a) rewritten against the substitute mechanism, or (b) deleted, with the accepted risk written down. **A criterion that survives a trim without review is one nobody will be able to meet.** *Real case:* deferring a durable table nearly killed the set's own objective — the alert condition was "zero runs recorded in the last 3h", which needs durable rows; an error event does not fire when a cron simply stops running, because the code that would emit it does not run either. Caught by chance, re-reading the condition.
- **`decisions.*`** — every decision whose stated rationale named the deferred entry. **A decision that dies can orphan the justification of another decision.** *Real case:* a table's deferral had been justified with "for alerting we don't need it, the Crons monitor covers the absence". When the monitor was later cancelled, the table stayed deferred — but no longer for the reason written next to it. The registry still read as settled.

This rule **reincidió two days after it was written**, in the same set, which is why it is also a mechanical check rather than only a paragraph here: a cancelled heartbeat left two acceptance criteria nothing could satisfy — one of them annotated *"this is THE test of the set"* — and the set was marked `status: shipped` with a clean audit, because no check compared `acceptance[]` against reality. Registering the decision in `_log.md` is **not** the same as propagating it: the log is narrative, `acceptance[]` is contract.

Deferring before doc 02 exists is the cheap case and the reason `implement` is a separate stage — a trimmed entry costs a registry edit instead of a rewritten phase. Deferring after 02 exists means regenerating the phases that were written around it; `sync` cannot do this, because it propagates values and a trim changes shape.

## Recording the result

Findings that are fixed → the fix lands in `_facts.yml` first (as `limits.*`, `contracts.*.auth`, a new `changes[]` entry, an `acceptance[]` item), then `sync`. A gap closed only in prose is invisible to the next audit.

Findings that are accepted → one line in doc 01 §Riesgos, with the reason. An accepted risk is a decision; an unmentioned one is an oversight.
