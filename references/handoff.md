# Handoff — passing a spec set between agents without re-deriving it

A spec set is often worked by more than one model: one drafts, a second reviews it cold, the first validates which of the second's findings hold. The failure is not that an agent misses an edit. It is that **an agent reviews its own context window instead of the file on disk** — a picture that may predate the last two rounds — and then confirms or rejects a finding against a version that no longer exists. Nothing in the output says so. The review reads exactly as authoritative as one done correctly.

`_log.md` is the append-only record of who touched what, against which version, and what they decided about the previous round's findings. It lives beside `_facts.yml` and is **never** synced into the docs — the registry is the state, the log is how the state got there.

## The rule that does the work

> **The log is read from disk before anything else, and it outranks the context window.**
> If your context disagrees with the log, your context is stale. Re-read the files the log names.

Everything else here exists to make that rule checkable.

## Entry format

One `##` block per round, appended at the end of the file. Never edit or delete a *previous* entry — the current round's own entry is opened as a stub before the work and completed after it, which is the one case where an entry is written in two passes.

**The stub goes in first.** `SKILL.md` used to say each mode "appends an entry before finishing", and that is backwards: the round that most needs a record is the one that does not reach the end. Open with the agent, the versions read, and what you are about to do; fill in findings, edits and dispositions when you finish.

```markdown
## R3 · 2026-08-19 · claude-opus-5 · validate
**Read:** 02-implementation-and-e2e.md (487 lines, blob 3f9a12c) · _facts.yml (129 lines, blob 8b2e004)
**Log read through:** R2
**Dispositions:**
- R2-F1 `doc02 §3.2 rate limit absent from registry` → **confirmed**. `limits.resend` was missing; added.
- R2-F2 `D3 root cause is wrong` → **rejected**. Ran `<commands.tests>` on 2026-08-19: `280/280 passing`.
  The premise it rested on holds. Kept as R2-F2-dead so R4 does not re-raise it.
- R2-F3 `acceptance item 4 unverifiable` → **deferred**. Needs a device nobody has; D5 stays `basis: asserted`.
**Edits:** `_facts.yml limits.resend` (new) · `02` §3.2 (rate-limit branch)
**Still open:** D5 `basis: asserted` — no hardware. G1 blocks `status: shipped`.
```

Required fields. A missing one is an audit finding, not a style choice:

| field | what it is | why it is required |
|---|---|---|
| round id | `R<n>`, monotonic | findings are addressed as `R<n>-F<m>` across rounds |
| date | `YYYY-MM-DD` | staleness checks |
| agent | model or tool identity, self-reported | `basis: decided` — nobody can verify it, but a wrong one is traceable |
| action | `author` · `review` · `implement` · `validate` · `verify` · `sync` | says what kind of claim the entry makes |
| **Stage** | `<from> → <to>`, **required on any entry that changes `status:`** | a stage transition is a decision with consequences — it puts docs into scope for audit and unlocks `implement`. Recorded nowhere else, it is indistinguishable from a typo in the registry |
| **Read** | every file opened, with **line count and blob hash** | the only field that proves which version was reviewed |
| **Log read through** | the last round id this agent actually read | catches an agent that skipped the middle of the history |
| Dispositions | one line per prior finding | see below |
| Edits | files + sections changed | what the next round must re-read |
| Still open | anything unresolved, and what it blocks | stops the next round rediscovering it |

## Getting the hash

```bash
git hash-object <file>        # blob sha, needs no commit and no staging
shasum -a 256 <file> | cut -c1-7   # fallback outside a git repo
```

Record the first 7 characters plus `wc -l`. Both, not either: the line count is readable at a glance and catches most edits; the hash catches an edit that preserves line count, which is the one a reviewer would otherwise miss.

`git hash-object` works on uncommitted and even gitignored files, so this holds for spec sets that are deliberately never committed.

## Dispositions

Every finding raised in round N gets exactly one disposition in round N+1. Silence is not a disposition — an unaddressed finding is what makes round N+2 raise it again.

- **confirmed** — it holds. Say what changed in the registry, and `sync`.
- **rejected** — it does not hold. **State the evidence that killed it**, in the same shape the registry demands: a command and its output, or an observation. "I disagree" is not a disposition; it is the finding surviving in disguise. The rejected finding stays in the log as `R<n>-F<m>-dead`.
- **deferred** — cannot be settled now. Name what would settle it and what it blocks. This is the honest outcome when the evidence needs hardware, a stakeholder, or a release build nobody can produce today.
- **superseded** — a later edit made it moot. Name the edit.

Rejected findings are kept for the same reason `verify` keeps dead hypotheses: a rejection with its evidence attached stops the next agent re-deriving it from scratch, and a rejection *without* evidence is exactly the thing a later round should re-open.

## Transcribed entries

An external model with no filesystem — a chat window a human pastes into — cannot write its own entry. Whoever transcribes it says so:

```markdown
## R2 · 2026-08-19 · gpt-5 (via: transcribed by claude-opus-5) · review
**Source:** pasted excerpt — `02` §3 only, not the full file
**Read:** [as pasted — no hash available]
```

This matters more than it looks. A finding raised against a pasted excerpt was made without the preamble, the cross-refs, or the phases around it. Round N+1 must weigh it as such — several "missing" things are usually present in the part that was never pasted. An entry that hides its provenance turns that into a real finding and costs a round.

When the transcription is a full file the human pasted verbatim, hash the local file and say `source: full file`.

## The rounds

The shape generalizes; three is just the common case.

1. **`author`** — drafts or edits the set. Logs what it wrote and what it left `asserted`.
2. **`review`** — reads cold and raises findings. Ideally a different model, or at minimum a session with no authoring context. Raises `R<n>-F<m>` items; changes nothing.
3. **`validate`** — dispositions every finding from the review with evidence, edits the registry, `sync`s.

Repeat from 2 as needed. `verify` (device/instrumented observation) is its own action and can enter at any point; it is the only one that can turn an `asserted` claim into a `measured` one.

**A round that edits without appending an entry is invisible**, and the next round reviews a file matching no entry in the log. Audit check 16 catches it after the fact; appending as you go is what prevents it.

## Delegating a defect to a set of its own

`handoff` covers agent → agent on an **existing** set. It does not cover *"this defect is a front of its own, let another agent build it a set"* — done three times in one session, invented from scratch each time, and once left half-finished by an agent that died with nothing recording what it had produced.

This is **not a mode.** It was used three times in five days, and the expensive half — deciding what of the registry travels with the defect and what is re-derived — is judgment, not mechanics. What it needed was a checklist, and the vocabulary it needs (`owned_by:`, `moved_to:`, `kind: moved_out`) now exists in the registry. If it turns out to be used often, promote it.

Five pieces, in order:

1. **Write the log stub first**, in the *originating* set, before anything else exists — `action: delegate`, the defect id, the agent you are handing to. A delegation that dies partway then leaves a trace instead of silence.
2. **The brief.** From the registry, not from memory: the defect itself, its related `limits.*`, the constraints, and — the part that pays for itself — **what has already been measured**, so the new set does not re-measure it. Anything omitted here gets re-derived, usually differently.
3. **Mark the originating entry.** `kind: moved_out` + `moved_to:` for a `changes[]` entry; for a defect the originating set still tracks, `owned_by:` + `note_ownership:` and it stays `open` on purpose — closing it would be a lie.
4. **The issue**, so the work has an address outside both registries.
5. **The backlink.** The new set carries `owned_by:` pointing back, with **the same id as in the owning set**. Never a mirror id: a `D4_ajeno` invented to make a sibling's defect locally referenceable had to be renamed across four files the moment the owner changed.

Cross-set citations are always **qualified** — `` `docs/features/<slug>/_facts.yml` defects.D4 `` — which is also what keeps audit check 21 from reading them as dangling.

## Stage transitions

The set is written in two stages (`SKILL.md` §Modes): `new` writes the registry and doc 01, `implement` writes docs 02 and 03 once the plan is confirmed. The flip of `status:` from `draft` to `reviewed` **is** the user's confirmation — there is no other record of it, so the entry that performs the flip states it:

```markdown
## R4 · 2026-08-31 · claude-opus-5 · implement
**Read:** _facts.yml (204 lines, blob 8b2e004) · 01-master-plan.md (197 lines, blob 1c4d77a)
**Log read through:** R3
**Stage:** draft → reviewed — user confirmed after R3 dispositions; `review` findings all settled.
**Dispositions:** R3-F1 → **confirmed**. C4 flipped to `kind: deferred` + `reopens_when:`.
**Edits:** `02-implementation-and-e2e.md` (new, 640 lines) · `03-stakeholder-requirements.md` (new, 158 lines)
**Still open:** —
```

Two rules that are not obvious:

- **The stub goes in before the generation, not after.** `implement` produces the two largest files in the set; a round that dies partway through leaves ~1000 lines on disk that no entry accounts for. *Real case:* a delegated subagent wrote all four documents and died on a session limit before writing its entry — from outside, it looked like it had produced nothing, and the next round spent its time reconstructing what had already been done. Write the stub (agent, versions read, what you are about to do), generate, then complete the entry.
- **An agent never writes the `reviewed` flip on its own reading of the conversation.** Confirmation is obtained, not inferred. An entry recording a transition the user did not make is worse than no entry: it reads as settled, and every later round trusts it.

## What this does not fix

The validating round is often the same model that authored the plan, judging a critique of its own work. The log does not remove that bias — it makes it **visible**. Across a few features you can read the ratio directly: an agent that rejects most external findings, with thin evidence lines, is telling you something about the gate, not about the findings. Check the ratio before trusting the validate round as an approval.

Nor does the log make an entry true. `agent:` is self-reported, `Read:` can be fabricated by an agent that never opened the file. What it does is make both **falsifiable**: a hash that doesn't match the file is a mismatch anyone can check in one command, and that is the whole standard this skill holds every other claim to.
