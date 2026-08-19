# Intake — the questions that must be answered before a spec can be written

A spec is only as true as its inputs. The failure mode is not asking too much; it is **inventing a plausible answer** for something only the user knows, which then propagates verbatim into three docs and reads as fact. `audit` cannot catch it — the copies agree perfectly.

So: anything the repo cannot tell you, and that a wrong value would carry into the output, is a **question**, asked before the prose exists.

## Rules

1. **Ask in one batch, not a drip.** Collect every open question for the current phase, then ask them together. Ten round trips to write one registry is the thing that makes people stop using the skill. Use a structured multiple-choice prompt when the answer space is closed (language, status, which layers apply) — in Claude Code that is `AskUserQuestion`; free text only when the answer space genuinely is open.

2. **Every question ships a detected default.** Read the repo first, then ask the user to *confirm*, not to *supply*: "CI runs `./gradlew testDebugUnitTest` — is that the baseline command?" beats "what is your test command?". A question with no proposed answer is work you pushed onto the user that you could have done.

3. **Never ask what a command can answer.** Owners come from `git shortlog -sne -- <paths>`. Test counts come from running the test command. File state comes from `git ls-files`. Asking for something sitting in the repo trains the user to skim your questions, and then they skim the one that mattered.

4. **These may never be guessed.** No detected default is good enough to skip confirmation:
   - `commands.tests` + `commands.tests_expect` — a wrong pass-line silently green-lights every phase verification.
   - `app_id` — device procedures run against the wrong install and observe nothing.
   - `prose_language` — determined once, then locked; retranslating a set later rewrites every cross-ref.
   - `gap_sweep_layers` — decides which whole class of hazard gets swept. Unasked, the sweep's "clean" is scoped narrower than it reads.
   - `owners.external` and any `blocked_by` — a plan that assumes a stranger's cooperation.
   - Whether a defect is `root_cause` or `contributing` — gate G1 hangs on it.

5. **"I don't know" is a valid answer, and it has a shape.** It becomes `null` in the profile, `[MANUAL]` in the doc, or `basis: asserted` + `falsified_by:` in the registry. It never becomes a plausible-looking value. A `null` is auditable; an invention is not.

6. **Answers land in a file, not in the conversation.** Profile answers → `_profile.yml`. Feature answers → `_facts.yml`. An answer that lives only in the chat is lost the moment the session ends, and the next session re-asks it.

## Intake set A — the profile (once per repo, in `new` step 0)

Skip entirely if the upward walk from the spec directory finds a `_profile.yml` (see `SKILL.md` `new` step 0). Only ask about `null` fields when a spec actually needs them.

If the walk finds one but it sits **further up than the app you are speccing** — a monorepo root profile while you are inside one variant — that is a question, not a default: confirm whether this app shares it or needs its own. Inheriting the wrong `app_id` is silent.

| field | detect from | ask as |
|---|---|---|
| `repo` | `basename $(git rev-parse --show-toplevel)` | fill it, no question needed — but it must be **written**, it is what detects a profile copied in from elsewhere |
| `app` | is this git root holding more than one app/variant? | ask only if it is. Wrong answer = every device procedure runs against the wrong install |
| `stack` | `build.gradle*` / `package.json` / `Package.swift` / `pubspec.yaml` | confirm the matched `profiles/*.yml`, or "none of these" |
| `prose_language` | language of existing docs in `docs/` | confirm |
| `commands.tests` + `tests_expect` | CI config, `package.json scripts`, Gradle tasks, Makefile | confirm — then **run it** and show the real output line |
| `app_id` | `applicationId` in Gradle, `PRODUCT_BUNDLE_IDENTIFIER`, `app.json` | confirm; `null` if there is no device target |
| `log_tag` | existing log calls in the repo | propose one; it only has to be greppable |
| `device_log` / `force_stop` | the stack's standard | confirm, or `null` → those evidence kinds become `[MANUAL]` |
| `gap_sweep_layers` | the stack | offer the shipped layers as a multi-select; "none apply" is an answer and gets stated in `review` output as a blind spot |
| `deep_review_agent` | available subagents | offer, default `null` |

## Intake set B — the feature (once per spec, in `new` step 2)

Ask alongside the facts table, in the same batch.

| field | detect from | ask as |
|---|---|---|
| `title`, one-line goal | the user's request | confirm the wording that will head all three docs |
| `owners.technical` | `git shortlog -sne -- <touched paths>` | confirm the top name |
| `owners.external` | — | **ask**. "Nobody external" is an answer; a blank is not |
| `dates.drafted` | today | confirm |
| `tracking.issues` / `milestone` | `gh issue list` if a remote exists | confirm or "none yet" |
| `status` | `draft` | confirm |
| `changes[]` vs `related_docs[]` | grep per symbol (one symbol per command) | show the derived split and ask what is missing — this is where scope errors are cheapest to catch |
| `acceptance[]` | the user's request | **ask**. Definition of Done is not derivable from code |
| `limits.*` | provider docs if named | ask for the numbers; a rate limit nobody stated is the most common `review` finding |
| each `defects[].role` | — | ask, per defect. Symptom vs root cause is a judgment, and G1 gates shipping on it |

## Intake set C — before `verify`

`verify` needs an observation, and an observation needs someone with the hardware. Ask before designing the procedure, not after:

- **Who runs it, on what device/build?** A procedure written for a device nobody has is a spec that stalls. If the answer is "nobody right now", the defects stay `basis: asserted` — which is correct and honest — and `status: shipped` stays blocked by G1.
- **Which build type?** Some defect classes (obfuscation, minification, signing, release-only config) only exist in release builds. A procedure that says "run the app" is under-specified where it matters most.
- **Can the decisive log line be read on that device?** If the profile has `device_log: null`, the observation has to be visible some other way — name it now, or the run comes back inconclusive.

## What a finished intake looks like

No `—`, `TBD`, or `?` anywhere in `_facts.yml` (audit check 10), no invented command in `_profile.yml` (check 15), and every remaining unknown carried explicitly as `null`, `[MANUAL]`, or `basis: asserted` + `falsified_by:`. Unknowns are allowed. **Unmarked** unknowns are the defect.
