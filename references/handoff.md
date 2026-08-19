# Handoff — passing a spec set between agents without re-deriving it

A spec set is often worked by more than one model: one drafts, a second reviews it cold, the first validates which of the second's findings hold. The failure is not that an agent misses an edit. It is that **an agent reviews its own context window instead of the file on disk** — a picture that may predate the last two rounds — and then confirms or rejects a finding against a version that no longer exists. Nothing in the output says so. The review reads exactly as authoritative as one done correctly.

`_log.md` is the append-only record of who touched what, against which version, and what they decided about the previous round's findings. It lives beside `_facts.yml` and is **never** synced into the docs — the registry is the state, the log is how the state got there.

## The rule that does the work

> **The log is read from disk before anything else, and it outranks the context window.**
> If your context disagrees with the log, your context is stale. Re-read the files the log names.

Everything else here exists to make that rule checkable.

## Entry format

One `##` block per round, appended at the end. Never edit or delete a previous entry.

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
| action | `author` · `review` · `validate` · `verify` · `sync` | says what kind of claim the entry makes |
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

**A round that edits without appending an entry is invisible**, and the next round reviews a file matching no entry in the log. Audit check 17 catches it after the fact; appending as you go is what prevents it.

## What this does not fix

The validating round is often the same model that authored the plan, judging a critique of its own work. The log does not remove that bias — it makes it **visible**. Across a few features you can read the ratio directly: an agent that rejects most external findings, with thin evidence lines, is telling you something about the gate, not about the findings. Check the ratio before trusting the validate round as an approval.

Nor does the log make an entry true. `agent:` is self-reported, `Read:` can be fabricated by an agent that never opened the file. What it does is make both **falsifiable**: a hash that doesn't match the file is a mismatch anyone can check in one command, and that is the whole standard this skill holds every other claim to.
