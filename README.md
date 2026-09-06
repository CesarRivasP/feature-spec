# feature-spec

An agent skill for writing **multi-doc feature specs that cannot contradict themselves** — and, more importantly, that cannot quietly ship a claim nobody ever verified.

A feature spec is rarely one file. It is a set: a master plan for the approver, an implementation doc for whoever builds it, a requirements doc for whoever owns the other side. The same facts — timeouts, contracts, endpoints, test baselines, dates — get copied into all three and drift. This skill puts every shared datum in one registry (`_facts.yml`) and makes auditing mechanical: *does any doc contradict the registry?*

Then it goes one step further, because that check has a hole in it:

> Verbatim copy guarantees the docs agree with the registry. It guarantees nothing about the registry. A false root cause copied into three docs is three consistent lies, and the audit reports `clean`.

That is not hypothetical — it is where this skill came from. A spec passed its audit, shipped, and its stated root cause turned out to be impossible. So every claim in the registry now declares **how it is known**, and a separate mode exists to ask whether the registry is actually true.

## Install

Skills live in a `.claude/skills/` directory. Per project:

```bash
git clone git@github.com:CesarRivasP/feature-spec.git
mkdir -p <your-repo>/.claude/skills
cp -R feature-spec <your-repo>/.claude/skills/
```

Or install it once for every project:

```bash
cp -R feature-spec ~/.claude/skills/
```

To pin a version instead of tracking `main`:

```bash
git clone --branch v1.7.2 --depth 1 git@github.com:CesarRivasP/feature-spec.git
```

Restart the session so the skill is picked up. No MCP servers, no package to install: the skill itself is markdown and YAML.

Two modes ship a script — `audit` and `view` — and between them they need one library:

```bash
python3 -m pip install --user pyyaml
```

Every other mode runs without it.

## Set up the profile (once per repo)

The skill keeps two files apart, deliberately:

- **`_facts.yml`** — one per feature. *What is true about this feature.*
- **`_profile.yml`** — one per repo (or per app in a monorepo). *How this repo finds out.*

Copy the starter matching your stack and fill it in:

```bash
cp .claude/skills/feature-spec/profiles/android-native.yml docs/features/_profile.yml
```

```yaml
repo: my-app                      # basename of the git root — detects a profile copied in from elsewhere
app: null                         # in a monorepo, the app this profile governs
stack: android-native
prose_language: en                # generated docs' language; numbering never changes

app_id: com.example.app
log_tag: FEATURESPEC

commands:                         # {app_id} {log_tag} {path} are substituted at use time
  tests:        "./gradlew testDebugUnitTest"
  tests_expect: "BUILD SUCCESSFUL"
  device_log:   "adb logcat -s {log_tag}:D"
  force_stop:   "adb shell am force-stop {app_id}"
  file_tracked: "git ls-files --error-unmatch {path}"

gap_sweep_layers: [android-native]
deep_review_agent: null
```

Every command the skill emits — into evidence, into a phase's verification line, into a log filter — comes from here. Nothing is invented per feature. `null` where your repo has no equivalent is correct; a *guessed* command is worse than none, because it gets copied into every doc and then executed.

**The starters are starters.** Copy them, never fill them in place — a real `app_id` written into `profiles/` leaks into every project using the skill. And **delete what you don't need**: the profiles and the `gap-sweep-<layer>.md` files are independent and disposable. An Android developer keeps `android-native.yml` and `gap-sweep-android-native.md` and removes the rest; nothing else references them.

## Modes

| mode | asks | catches |
|---|---|---|
| `new <slug>` | is this worth building? | scaffolds the registry + doc 01, after a gap sweep and a batch of intake questions |
| `review <slug>` | if this is built literally, what breaks? | rate-limit dead ends, unauthenticated writes, PII, silent fallbacks, stack-specific hazards |
| `implement <slug>` | — | writes docs 02 and 03, once the plan is confirmed |
| `audit <slug>` | do the docs agree with the registry? | contradictions, drift, orphan facts, dangling cross-refs, broken anchors |
| `verify <slug>` | **is the registry true?** | a root cause that was reasoned, never observed |
| `handoff <slug>` | who touched this, against which version? | an agent reviewing its stale context instead of the file on disk |
| `view <slug>` | what does this set actually look like? | a guessed root cause reading exactly like a measured one |

`verify` is the only one that can fail after a clean `audit`. `status: shipped` is gated on it: the set may not claim to have shipped while the defect it blames is still `basis: asserted`.

### Two stages, not one

`new` writes the registry and doc 01 — the decision surface. `implement` writes docs 02 and 03 — the build. In between, you argue about the plan.

The split is measured: across four real sets, docs 02 and 03 are **71-83%** of the prose, and they are the part invalidated wholesale when the plan changes — doc 01 gets edited, doc 02 gets rewritten. A plan gets bounced two to four times before anyone commits to it, so writing them up front pays for that prose repeatedly and, worse, keeps ~75% of the set in existence during the window where decisions are still moving. That window is where prose goes stale: one cancelled decision left **14 stale promises** across a set already written out in full, including a step telling an operator to create a monitor that had been cancelled.

`implement` refuses to run until `review` has been dispositioned, the user has confirmed (the `draft` → `reviewed` flip *is* the record), and every `changes[]` entry carries a `kind:`. For a decision already made, `new <slug> --with-build` runs both.

### Auditing a set

```bash
python3 scripts/audit.py docs/features/<slug>/
```

The protocol's checks are good; the problem was that **an agent runs the ones it remembers**. A rough version of this script, run against three sets that had each already passed a "clean" hand audit against the same protocol, found 12, 11 and 7 findings — broken anchors, a corrupted top-level key, orphan ids. None subtle.

It runs every check a program can run and prints the rest under `REQUIRES A HUMAN PASS`, so a skipped check is visible rather than silent.

Four of those checks — 3, 4, 8 and 13 — narrow the search before handing it over: the script prints a short list of **candidates** under the check they belong to. A candidate is not a finding and never appears in `## Findings`: it has no severity yet, and inventing one would make the verdict count things nobody has judged. Read the candidate list instead of re-reading the documents, and decide each one — the exception that legitimises it is usually a note the script cannot read. It never executes `evidence.cmd`: a registry is a data file that travels between repos and agents, and running commands out of one because it says they are safe is what an auditor must not do.

### Reading a set

```bash
python3 scripts/render.py docs/features/<slug>/ --open
```

One self-contained `view.html` — no network, no build step, no account. It shows what the markdown cannot: `basis:` as a chip on every claim with its evidence attached, each registry datum marked where it is cited in prose (clickable both ways), `changes[]` next to `related_docs[]`, the defect board, the correspondence matrix, and `_log.md` as a timeline. Dangling cross-refs render red; registry facts nobody ever cited are counted on the front page.

It is a derived artifact — edit the registry, re-render. Sharing it means sending the file.

## The idea that holds it together

Every registry entry that claims something about the world declares its basis:

```yaml
tests_baseline:
  basis: measured
  evidence: { how: shell, cmd: "<commands.tests>",
              date: 2026-08-03, value: "280/280 passing (28 files)" }

defects:
  - id: D3
    role: root_cause
    claim: 'row 0 never mounts because the list clamps the initial render region'
    basis: asserted
    falsified_by: 'a log line proving row 0 DID mount while focus still died'
    log_line: 'FEATURESPEC.mount id=<uid> row=0'
```

`measured` needs evidence — a command and its verbatim output. `asserted` needs a falsifier — the concrete observation that would kill the claim. `decided` is a choice, with no truth value to check.

This is not only for numbers. A behavioral claim ("the framework focuses the first item"), a file-state claim ("not committed yet"), and the reason an alternative was discarded are all claims, and all get a basis. Three of the four modes exist to keep them honest:

- an `asserted` claim with no `falsified_by` is a **finding**;
- a `falsified_by` with no log line that could produce it is a **finding** — the instrumentation is part of the spec, not something bolted on when the first device run comes back inconclusive;
- an alternative discarded by *reasoning* records what it depends on, so when a premise dies, `verify` puts that alternative back on the table instead of leaving it rejected for a reason that no longer holds.

Unknowns are fine. **Unmarked** unknowns are the defect.

## Asking instead of inventing

The other half of the same problem: anything only you know — a rate limit, an external owner, a Definition of Done, whether a defect is the root cause or a symptom — gets **asked**, in one batch, before any prose exists. Each question ships a default detected from the repo, so you confirm rather than supply. And nothing is asked that a command could answer: owners come from `git shortlog`, test counts from running the tests, file state from `git ls-files`.

An invented value is indistinguishable from a measured one once it is copied into three docs, and the audit will call it clean.

## Passing a set between agents

A common workflow is to have one model draft the plan, a second review it cold, and the first disposition which of the second's findings actually hold. The failure there is not a missed edit — it is an agent **reviewing its own context window instead of the file on disk**, a picture that may predate the last two rounds, and confirming or rejecting a finding against a version that no longer exists. Nothing in its output says so.

`_log.md` is an append-only record, one entry per round:

```markdown
## R3 · 2026-08-19 · claude-opus-5 · validate
**Read:** 02-implementation-and-e2e.md (487 lines, blob 3f9a12c) · _facts.yml (129 lines, blob 8b2e004)
**Log read through:** R2
**Dispositions:**
- R2-F1 `doc02 §3.2 rate limit absent from registry` → **confirmed**. `limits.resend` was missing; added.
- R2-F2 `D3 root cause is wrong` → **rejected**. Ran the test command on 2026-08-19: `280/280 passing`.
  Kept as R2-F2-dead so R4 does not re-raise it.
**Edits:** `_facts.yml limits.resend` (new) · `02` §3.2
**Still open:** D5 `basis: asserted` — no hardware. G1 blocks `status: shipped`.
```

> **The log is read from disk before anything else, and it outranks the context window.**
> If your context disagrees with the log, your context is stale.

The field that does the work is `Read:` — line count **and** blob hash of every file opened, via `git hash-object`, which needs no commit or staging and works on spec sets that are deliberately never committed. It turns "I reviewed doc 02" from an unfalsifiable statement into one anyone can check in a single command, which is the standard every other claim in this skill is already held to. An audit check compares the recorded hash against the file: a mismatch means someone edited without logging, and the next round is about to review a version no entry describes.

Rejected findings stay in the log with the evidence that killed them, for the same reason `verify` keeps dead hypotheses. A rejection with no command output behind it is a finding surviving in disguise, and is itself a finding. An external model with no filesystem gets its entry transcribed, and the entry says so plus what it was actually shown — a finding raised against a pasted excerpt was made without the preamble and the surrounding phases.

It does not remove the bias of a model validating a critique of its own work. It makes it visible: across a few features you can read the ratio directly.

## Extending it

Two extension points, both plain files:

- **A profile** (~20 lines) teaches the skill how a new stack verifies things.
- **A gap-sweep layer** (~40 lines) teaches it what that stack can uniquely break — exported components and background limits on Android, RLS and webhook replay on a BaaS, dead D-pad focus on TV.

A stack with no layer yet is reported as a **stated blind spot**, never as a clean sweep.

## Files

```
SKILL.md                              entry point: modes, rules
references/
  intake.md                           what to ask before writing anything
  handoff.md                          the append-only _log.md for sets passed between agents
  evidence.md                         the basis/evidence contract, the verify mode, the gates
  audit-protocol.md                   17 mechanical checks + severity taxonomy
  gap-sweep.md                        the review checklist (base, stack-agnostic)
  gap-sweep-android-native.md         layer: manifest, intents, permissions, Doze, R8, Room
  gap-sweep-web-baas.md               layer: webhooks, RLS, edge functions
  gap-sweep-mobile-tv.md              layer: D-pad focus, low-end memory, playback lifecycle
  doc-pattern.md                      the 3-doc pattern, splitting, heading language
  implementable.md                    how to write doc 02 for a context-free executor
  render.md                           what the HTML view reads, its invariants, the gates it surfaces
scripts/
  audit.py                            the mechanized checks; shares its registry core with render.py
  render.py                           the renderer: spec set -> one self-contained view.html
tests/                                one fixture per check, each reproducing the failure it exists for
templates/                            _facts.yml.tpl, _log.md.tpl + one .tpl per doc
profiles/                             _profile.yml.tpl + starters per stack
```

## A note on pairing this with `caveman`

This skill was written and iterated on while running [`caveman`](https://github.com/mattpocock/skills) — an output-style skill that strips articles, hedging and pleasantries from the agent's replies. Recommended, with one boundary that matters.

**Where it helps: the conversation.** Three of the four modes produce *reports* — an audit's findings list, a gap sweep's one-line-per-gap output, a verify reconciliation. Those formats are already specified as terse and scenario-first: `doc0X §sec: TAG: what mismatches. fix.` and *no failure scenario, not a finding*. A compressed reply style pushes in the same direction, and the effect is real when a `--deep` audit comes back with twenty findings: what you read is the mismatch and the fix, not the framing around them.

**Where it must not reach: the artifacts.** The docs, the registry, and the intake questions are not conversation. Doc 02 is written for an executor with no context, where a dropped article in a numbered device procedure is exactly the ambiguity this skill spends a whole reference file forbidding. Registry prose — `claim:`, `falsified_by:`, `acceptance[]` — is copied verbatim into three documents, so compression there propagates and then gets audited as a shared datum. `caveman`'s own rules already carve this out (it disables itself for multi-step sequences where fragment order risks a misread); the point is to notice that a generated spec is *always* that case. **Terse in the terminal, complete in the files.**

**What it does not do: improve the analysis.** It is an output style. It changes how findings are worded, not whether they were found — a compressed wrong answer is still wrong, and reads more confident. Stating otherwise in this particular README would be the exact defect the skill exists to catch: a pleasant, plausible claim that nobody measured. Use `caveman` because the reports are easier to read, which is a real benefit and enough of one.

## If your repo syncs `docs/features/` somewhere

Changing the layout convention is a change with downstream consumers, and they fail quietly.

This skill moved from flat specs (`docs/features/<slug>-01-….md`) to one directory per feature (`docs/features/<slug>/…`). A repo using it had a vault-sync manifest matching `docs/features/*_facts.yml` — after the migration that pattern matched **zero files**. Nobody noticed, because the `.md` files travelled under a different pattern, so the sync reported success while every registry stayed behind. The result would have been three documents per feature citing values from a source of truth that was not there: it looks complete and is not.

If anything outside this repo reads `docs/features/`, check its patterns when you adopt or change the layout.

## Releases

| version | what it added |
|---|---|
| [**v1.7.2**](https://github.com/CesarRivasP/feature-spec/releases/tag/v1.7.2) | check 14's `log_line` gate offered an out its own guard rejected. The DRIFT message says "or `log_line: null` to say it must be built", but the guard was `not e.get("log_line")` and `None` is falsy — so a defect that wrote exactly `log_line: null`, the declaration the message asks for, re-drifted every run, silenceable only by inventing an emitter. The guard now separates *key absent* (nobody considered instrumentation → DRIFT) from *`log_line: null`* (declared as must-be-built → clean), while a blank string still drifts. Same falsy-fallback family as v1.7.1, and the two `node.get("evidence") or {}` sites left in `audit.py` — which crashed the whole audit on a string `evidence:` — were coerced the same way ([#13](https://github.com/CesarRivasP/feature-spec/issues/13)) |
| [v1.7.1](https://github.com/CesarRivasP/feature-spec/releases/tag/v1.7.1) | `evidence:` written as a string instead of the `{ how, cmd, date, value }` mapping crashed `audit`'s render with `AttributeError: 'str' object has no attribute 'get'`. `node.get("evidence") or {}` only falls back on a falsy value, so a non-empty string passed through to two call sites that call `.get()` on it. A malformed `evidence` is the exact drift the render gate exists to report — it now emits `measured but evidence lacks: how, cmd, date, value` instead of raising ([#12](https://github.com/CesarRivasP/feature-spec/issues/12)) |
| [v1.7.0](https://github.com/CesarRivasP/feature-spec/releases/tag/v1.7.0) | a `[human]` check made the LLM re-read three whole documents to answer a question a grep can narrow to ten lines. Checks 3, 4, 8 and 13 now emit **candidates** — a third kind of output, printed under their check in `REQUIRES A HUMAN PASS`, never in `## Findings`, because a candidate has no severity yet and inventing one makes the verdict count things nobody has judged. Each stops where judgment starts: check 3 diffs key sets but cannot read the note that legitimises an injected field, check 4 strips the exempt shape it can and leaves the one it cannot, check 13 takes three of its eight sub-bullets and leaves the five that ask what happens elsewhere. There are more rejects than expects in the suite, which is the point: a sweep that over-reports costs more tokens than the check saves. Check 9 gained the direction that did not exist — a file on the feature's theme that no `docs[]` entry names, outside the source-of-truth net and drifting in silence |
| [v1.6.0](https://github.com/CesarRivasP/feature-spec/releases/tag/v1.6.0) | checks 2, 5, 8, 11 and 12 were tagged `[human]`, never mechanized, and never listed under `REQUIRES A HUMAN PASS` — so they were not run and not printed, which is the one failure the script exists to prevent. A test now derives the list from the protocol and fails when a tagged check is missing from it. Check 15 gained its two pure-comparison halves: a `_profile.yml` whose `repo:` names another checkout, or whose `app:` does not govern the directory holding the spec — the spec folder copied between projects, every `cmd` in it now belonging to a different repo and every one of them still running |
| [v1.5.1](https://github.com/CesarRivasP/feature-spec/releases/tag/v1.5.1) | every enum field is read lowercased. `status: Shipped` used to rank as unknown — which ranks as `draft` — so a shipped set audited as a draft: G1 clean and four checks skipped, with a root cause still asserted. A gate that fails open is worse than no gate |
| [v1.5.0](https://github.com/CesarRivasP/feature-spec/releases/tag/v1.5.0) | shipping with a root cause still asserted is allowed **once, in writing, with an expiry date** — `defects[].accepted: { by, decided_on, until, because }`. Deciding to ship the trimmed scope and measure later is a real call; recording it in a log entry or an agent's memory is not, because neither can be checked against a date |
| [v1.4.2](https://github.com/CesarRivasP/feature-spec/releases/tag/v1.4.2) | the `_log.md` entry is **opened before the work and completed after**, not appended at the end — the round that most needs a record is the one that never reaches the end. A delegated agent wrote four documents and hit a session limit before writing its entry; from outside it had produced nothing |
| [v1.4.1](https://github.com/CesarRivasP/feature-spec/releases/tag/v1.4.1) | the `view` says which documents are **not due yet** rather than staying silent — a stage-1 set rendered as "1 docs" is indistinguishable from a set someone abandoned halfway, and correct is not the same as silent |
| [v1.4.0](https://github.com/CesarRivasP/feature-spec/releases/tag/v1.4.0) | the set is written in **two stages** — `new` writes the registry and doc 01, `implement` writes docs 02 and 03 once the plan is confirmed. Those two are 71-83% of a set's prose and the only part rewritten whole when the plan moves, and a plan gets bounced two to four times before anyone commits to it. Plus `scripts/audit.py`: the protocol mechanized, because an agent runs the checks it *remembers* — twelve new checks, each shipped with the real failure that motivated it as a test |
| [v1.3.0](https://github.com/CesarRivasP/feature-spec/releases/tag/v1.3.0) | `view` — a spec set rendered to one self-contained `view.html`: `basis:` as a chip on every claim with its evidence attached, each registry datum marked where it is cited in prose, the defect board with `depends_on` navigable, and the `evidence.md` gates on the front page. In markdown a guessed root cause and a measured one read identically; here they do not |
| [v1.2.1](https://github.com/CesarRivasP/feature-spec/releases/tag/v1.2.1) | instrumentation removal is ordered after the last **run** that reads it, not after the last code phase — a `[MANUAL]` confirmation run comes later, and a spec that deletes its own oracle pushes the next step toward eyeballing pixels |
| [v1.2.0](https://github.com/CesarRivasP/feature-spec/releases/tag/v1.2.0) | a gap-sweep kind for **adding** a check, not only removing one — an early return partitions its function and everything above it keeps running on the input the guard rejects; plus `verify` routing back through `review` when a refuted hypothesis moves the fix |
| [v1.1.0](https://github.com/CesarRivasP/feature-spec/releases/tag/v1.1.0) | `_log.md` — the append-only handoff log, so a set worked by several models is reviewed against the file on disk rather than a stale context window |
| [v1.0.0](https://github.com/CesarRivasP/feature-spec/releases/tag/v1.0.0) | first public release — the registry, the four modes, the `basis:` contract, `_profile.yml`, intake, gap-sweep layers |

## License

MIT — see [LICENSE](LICENSE).
