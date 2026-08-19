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

## Cross-cutting sweeps

- **Bulk mutation on user records.** Any update/delete across a user collection must be specified with an explicit key list, never a bare predicate (`WHERE x IS NULL`, `filter { it.foo == null }`). The predicate that matches 16 records today matches 400 next month.
- **Secrets in the doc set.** Names of env vars / keystore entries belong in the registry; values never. If the spec asks a third party to hand over a secret, it must name the channel — and rule out the insecure one by name.
- **Untrusted text.** Data pulled from user-controlled fields (emails, names, uploads, stored rows, intent extras) and shown to an operator or an LLM is untrusted. Say so where it's read.
- **New dependency on an external owner.** Anything the team cannot execute alone gets `blocked_by:` in the registry, an owner, and a date that reflects *their* clock. Otherwise the plan quietly assumes a stranger's cooperation.

## Recording the result

Findings that are fixed → the fix lands in `_facts.yml` first (as `limits.*`, `contracts.*.auth`, a new `changes[]` entry, an `acceptance[]` item), then `sync`. A gap closed only in prose is invisible to the next audit.

Findings that are accepted → one line in doc 01 §Riesgos, with the reason. An accepted risk is a decision; an unmentioned one is an oversight.
