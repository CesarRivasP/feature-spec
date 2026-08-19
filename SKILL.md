---
name: feature-spec
description: Create, audit, and keep-in-sync multi-doc feature specs from a single source of truth (a facts registry), so no two docs ever contradict. Use when the user wants to write a feature spec / design doc set, audit spec docs for consistency, or validate that every shared datum matches across documents.
---

# Feature Spec — spec doc sets that never contradict

A feature spec is not one file — it's a **set** (master plan + implementation/E2E + stakeholder requirements) that shares many of the same facts (dates, timeouts, contracts, endpoints, bot lists, backoff numbers…). Contradictions creep in because each fact is **copied** into 3 places and drifts.

**Core idea: one source of truth.** Every shared datum lives once in `_facts.yml`. Docs reference it. Auditing stops being "read 3 docs and compare prose" and becomes "check no doc contradicts `_facts.yml`" — mechanical and near-deterministic.

Directory layout for a feature named `<slug>`:

```
docs/features/<slug>/
  _facts.yml          # single source of truth — the ONLY place shared data is authored
  _log.md             # append-only handoff log — who edited what, against which version
  01-master-plan.md
  02-implementation-and-e2e.md
  03-stakeholder-requirements.md
```

(If the project keeps specs flat like `docs/features/<slug>-01-...md`, honor that — put `_facts.yml` as `docs/features/<slug>/_facts.yml` or `<slug>-_facts.yml`. Match the repo's existing convention; do not impose a new one.)

## Modes

**Every mode starts by reading `_log.md` from disk** (`references/handoff.md`). It records which agent last touched the set, which file versions they read, and what they decided about the previous round's findings. **It outranks your context window** — if the two disagree, your context is stale and the files must be re-read at the versions the log names. Every mode that edits appends an entry before finishing; one that does not is invisible to the next round.


### `new <slug>` — scaffold a spec set
0. **Resolve the profile.** Walk UP from the spec's own directory to the git root and take the **first** `_profile.yml` found (`<spec dir>/_profile.yml`, then `docs/features/_profile.yml`, then any parent, then the root). Nearest wins, and the resolved path is recorded in `_facts.yml profile:` so audit checks the same file the author used.
   - **A monorepo has one profile per app, not one per repo.** Variants sharing a git root have different `app_id`s; a single root profile hands them all the same one, and every `how: device` procedure then runs against the wrong install and observes nothing — a false `basis: measured`, the worst kind. Put the profile next to the app it describes.
   - Repos that keep specs flat instead of one folder per feature (see the layout note above) put it beside them as `_profile.yml`; the upward walk finds it either way. Never create a second one because the first was in an unexpected place — two profiles in one repo is the exact drift this skill exists to prevent.

   It holds how THIS app verifies things: test command and its pass line, device-log filter, app id, prose language, which gap-sweep layers apply. Every command the spec emits is sourced from it — never invented per feature, never hand-typed into prose.
   - Missing? Detect the stack (`build.gradle*`, `package.json`, `Package.swift`, `pubspec.yaml`), propose the nearest `profiles/*.yml` **filled with commands actually found in this repo** (scripts in `package.json`, Gradle tasks, the CI config), and confirm with the user before writing it. Once per repo, not once per feature.
   - No shipped profile matches → copy `profiles/_profile.yml.tpl` and fill it. `null` where the repo has no equivalent is correct; a *guessed* command is worse than none, because `evidence.cmd` carries it into every doc and the executor runs it.
   - **Anything the repo cannot tell you is a question, asked now** — one batch, each with a detected default to confirm. Protocol and the per-field question set: `references/intake.md` (intake set A).
1. **Detect pre-existing siblings first.** Glob `docs/features/*<slug>*` (and scan for docs on the same theme under other names). Any hit that isn't going to be part of the set is a decision, not a silent skip: offer to (a) integrate it into the set, or (b) register it in `docs[]` with `role: legacy` so audit tracks it. Never scaffold a parallel doc next to an unregistered one covering the same feature — that's how a drifting sibling (17 vs 16) survives.
2. Fill `templates/_facts.yml.tpl` first — this is the contract for the whole set. Confirm the facts table with the user before writing prose — **in one batch, with every open question attached** (`references/intake.md`, intake set B). Ten round trips to fill one registry is how a spec stops getting written; one batch with proposed answers is how it gets written correctly.
   - **Every claim declares its basis.** Any entry asserting something about the world carries `basis: measured` (+ `evidence: { how, cmd, date, value }`), `basis: asserted` (+ `falsified_by:`), or `basis: decided`. This is not only for numbers: **behavioral** claims ("the framework focuses the first item"), **file/git state** ("not committed yet"), and **why an alternative was discarded** are all claims and all get a basis. Measured data is RUN, never copied — a number lifted from stale prose propagates to every doc as a lie (*real case:* `280/280` written `296/296` across 5 files); a behavior lifted from intuition does the same, silently (*real case:* a root cause that passed `audit` clean and died on the first device run, after shipping). Full contract + the `verify` mode in `references/evidence.md`.
   - **One symbol per scope command.** A `cmd` that derives scope uses no regex alternation. `rg 'A|B'` fuses two result sets, so no member of the output can be attributed to one symbol. *Real case (React Native TV):* one `rg 'VerticalCarousel|VerticalPaginated'` put 3 screens under the wrong component. Two symbols, two entries.
   - **Split scope correctly.** Components you create/modify go in `changes:`; docs you only reference go in `related_docs:`. They are disjoint — never merge them into one list.
   - **No placeholders survive.** `—`, `TBD`, `?` in `owners.*`, `dates.*`, or any `schedule.*` are unfilled decisions, not formatting. Resolve them at authoring time: owner from `git shortlog -sne` on the touched paths, dates from the user. A `—` shipped in a registry becomes a round trip later.
   - **Counters name their predicate.** `attended: 2` next to `unblocked: 1` is only readable if each says what it counts. Any number that could be read two ways gets a sibling `note:`.
   - **Commands come from the profile.** `evidence.cmd`, the test baseline, the log filter and every "Verificación fase N" line are rendered from `_profile.yml commands.*` with `{app_id}`/`{log_tag}`/`{path}` substituted. A command typed straight into prose is a shared datum with no home — invisible to `sync`, and it drifts.
3. **Gap sweep BEFORE writing prose** — `references/gap-sweep.md` (base) **plus every layer in `_profile.yml gap_sweep_layers:`**. Two questions, not one:
   - *What breaks if this is built literally?* Walk `changes[]` against the base kinds (rate limits, unhandled error branches, silent provider fallbacks, PII, retention, existence leaks, "log it" steps nobody reads) and then against each stack layer.
   - *What observation would falsify each asserted defect — and does a log line exist today that produces it?* Every `basis: asserted` entry needs a `falsified_by:` and a `log_line:`. Instrumentation designed here turns the first device run into a decisive one; instrumentation added reactively costs a whole extra build/run cycle, and its lines tend to omit their emitter (see `references/implementable.md` §Diagnostic log lines).

   Every gap either lands in the registry (`limits.*`, `contracts.*.auth`, a new `changes[]` entry, an `acceptance[]` item, a `defects[].falsified_by`) or is written down as an accepted risk. **This is the single biggest source of doc rework** — a spec that passes audit can still be an unsafe thing to build, and the gaps surface as a rewrite after review instead of as registry entries before it.
4. Generate the 3 docs from the templates, sourcing every shared datum from `_facts.yml`. Never hand-type a shared number/name into a doc — copy it from the registry so the wording matches char-for-char.
   - Doc 02 follows `references/implementable.md`: paste-ready code, resolved paths, named symbols, anchors, and the repo's real test-mock preamble. Assume the builder is a smaller model with zero context on this conversation.
   - **Prose language is `_profile.yml prose_language:`.** The `.tpl` files carry the `es` rendering of the fixed headings; for `en`, translate the headings using the map in `references/doc-pattern.md` §Heading language and keep the numbering identical. The headings are what audit checks 4/5/6 navigate by, so they must be consistent across the set — but they are not required to be Spanish.
5. **Lint the registry before first `sync`.** Spellcheck the prose fields (notes, acceptance items, titles) — a typo in the registry (`accionabe`) propagates verbatim to every doc. Strings containing `"` are authored as single-quoted YAML scalars, so they match the prose byte-for-byte and don't trip acceptance parity.
6. Scaffold `_log.md` from `templates/_log.md.tpl` and append the `R1 · author` entry — what you wrote, and what you left `basis: asserted`. Skip only for a set you know will never leave this session; adding it later costs the history you already lost.
7. Run `audit <slug>` (inline) before declaring done.

### `audit <slug>` — consistency check (default: inline)
Run the mechanical checks in `references/audit-protocol.md` and emit:
- a **correspondence matrix** (each shared datum × each doc → match/miss), and
- a **findings list**, most-severe first, each tagged `CONTRADICTION` / `DRIFT` / `POLISH`.

Report the matrix + findings as terminal text. Do NOT auto-edit in `audit` mode unless the user says "fix" — surface first, patch on request.

`audit <slug> --deep` → after the inline pass, spawn a **cold reviewer subagent** (`_profile.yml deep_review_agent:` if set, else `Explore`/`general-purpose`) that re-reads the docs with NO context on how they were written and returns compressed findings. The inline pass validates against rules; the deep pass catches normalized-away assumptions the author is blind to. Merge both, dedupe, present once. Use `--deep` at the final gate, not during iteration.

### `review <slug>` — gap sweep (is this safe to build?)
Runs `references/gap-sweep.md` against an existing spec set, **plus one `references/gap-sweep-<layer>.md` per entry in `_profile.yml gap_sweep_layers:`**. The base file holds the kinds of change every codebase has; the layers hold what a stack can break that no other stack can (exported components and Doze on Android, RLS and webhook replay on a BaaS, dead D-pad focus on TV). A stack with no layer yet is a **stated blind spot** in the output, not a clean pass — write the layer, it's ~40 lines. Complements `audit`, does not replace it:

| | asks | catches |
|---|---|---|
| `audit` | do the docs agree with the registry? | contradictions, drift, orphan facts |
| `review` | if built literally, what breaks? | unhandled rate limits, open endpoints, non-idempotent writes, PII, silent fallbacks, dead-end rescue flows |

Output: findings tagged `FUNCTIONAL` / `SECURITY`, each with a concrete failure scenario (inputs/state → wrong behavior). No scenario → not a finding. Fixes land in `_facts.yml` first, then `sync`; accepted risks land in doc 01 §Riesgos with a reason.

Run it after `new`, and again whenever `changes[]` grows.

### `verify <slug>` — is the registry true?
Ask intake set C first (`references/intake.md`): who runs the procedure, on which device and **which build type**, and whether the decisive log line is readable there. A procedure written for hardware nobody has, or for a debug build when the defect is release-only, comes back inconclusive and costs the full build/install/navigate cycle anyway.

Reconcile `_facts.yml` against observations from a device run or instrumented session. Confirmed hypotheses become `basis: measured` with their `evidence:` filled; refuted ones become `status: dead` (kept, never overwritten — a dead hypothesis stops the next session re-deriving it); every `alternatives[]` entry that `depends_on` a dead id and was discarded by reasoning flips to `outcome: reopened`. Then `sync`.

`audit` asks whether the docs agree with the registry. `review` asks whether the plan is safe to build. **`verify` asks whether the registry is TRUE** — and it is the only one of the three that can fail after a clean `audit`. Run it before flipping `status: shipped`; gate G1 in `references/evidence.md` refuses that flip while a root cause is still `asserted`.

### `handoff <slug> [round]` — hand the set to another agent, or take it from one
For sets worked by more than one model: one drafts, a second reviews it cold, the first dispositions the findings. Appends a round entry to `_log.md` recording the agent, the **line count and blob hash of every file read** (`git hash-object <file>` — no commit needed, works on gitignored specs), how far back it read the log, and one disposition per prior finding: `confirmed` / `rejected` / `deferred` / `superseded`.

A rejected finding states the evidence that killed it and **stays in the log** — same reasoning as a dead hypothesis in `verify`: a rejection with evidence stops the next round re-deriving it, and a rejection without evidence is exactly what a later round should reopen. An external model with no filesystem gets its entry transcribed, and the entry says so plus what it was actually shown — a finding raised against a pasted excerpt was made without the preamble and the surrounding phases.

Format, disposition rules, and the round protocol: `references/handoff.md`.

### `sync <slug>` — propagate registry changes
When `_facts.yml` changes, find every doc occurrence of each changed datum and update it (or, if `--dry`, report the drift without editing). This is the write-side counterpart of `audit`.

## Rules that keep it honest

> **Verbatim copy guarantees consistency with the registry — including any error IN the registry.** The mechanical audit proves the docs agree with `_facts.yml`; it does NOT prove `_facts.yml` is true. So the leverage is at the INPUT to the registry: every claim must declare its `basis` and measured data must be run not copied (A), scope must be categorized `changes` vs `related_docs` (B), contracts/endpoints must be promoted out of prose (C), and sibling docs must be detected (D). Harden the entry; the copy takes care of itself.
>
> (A) is the one that reaches past the docs. Consistency and safety are both checkable *before* anything runs — truth is not. That is what `verify` is for, and why `status: shipped` is gated on it rather than on a clean audit.

- **Ask, never invent.** Anything only the user knows — a rate limit, an external owner, a Definition of Done, whether a defect is the root cause or a symptom — is asked before the prose exists, in one batch, each question carrying a default detected from the repo. An invented value is indistinguishable from a measured one once it is copied into three docs, and `audit` will call it clean. Unknowns are fine; they are carried as `null`, `[MANUAL]`, or `basis: asserted` + `falsified_by:`. **Unmarked** unknowns are the defect. Full protocol in `references/intake.md`.
- **The log outranks the context window.** A spec set outlives the session that wrote it and is often worked by several models. An agent that reviews its own context instead of the file on disk validates against a version that may be two rounds old, and nothing in its output says so. Read `_log.md` first, re-read at the versions it names, and append an entry for anything you change — recording the line count and hash of what you read is what makes "I reviewed doc 02" falsifiable instead of merely stated. `references/handoff.md`.
- **Registry is authoritative.** If a doc and `_facts.yml` disagree, the doc is wrong (unless the user says the registry is stale — then fix the registry and `sync`).
- **The registry says what is true; the profile says how this repo finds out.** Two files, two lifetimes: `_facts.yml` is per feature, `_profile.yml` is per repo. A command belongs to the profile, its output belongs to the registry. Hand-typing a command into a doc creates a third, unauditable copy — and it is the copy the executor actually runs.
- **A clean audit does not mean the registry is true.** Verbatim copy propagates the registry's errors with perfect fidelity. `basis:` is what separates measured from asserted; `verify` is the gate that resolves it. A root cause still on `basis: asserted` blocks `status: shipped`.
- **Cheap-to-verify state is never asserted.** File existence, git tracking, `.git/info/exclude` membership, whether a symbol exists — one command each. Copying a file's state from a sibling spec is the same defect as copying a test count.
- **Discard by measurement beats discard by reasoning.** An `alternatives[]` entry rejected on reasoning is `basis: asserted` and names its premises in `depends_on:`. When a premise dies, the discard is void, not merely doubtful — the rejected variant goes back on the table.
- **Scope a `verified.cmd` positively.** Allowlist the extensions/paths that can legitimately hold the thing (`-g '*.ts'`, `git ls-files`); never denylist directories. A denylist only knows the files that existed when you wrote it — the next scratch note or session transcript dropped in the repo joins the count and flips the value. If the doc pastes the command with an `Esperado: N`, the executor now reads a contaminated result as a real finding.
- **Scope is two lists.** `changes` (created/modified) drives scope-parity; `related_docs` (referenced, unmodified) never does. Don't mix them.
- **No contract in prose only.** Every JSON payload and endpoint/URL that appears in a doc must have a home in `contracts.*` / `endpoints.*`. A contract that lives only in prose is an orphan — promote it.
- **No orphan facts.** A shared datum that appears in ≥2 docs MUST live in `_facts.yml`. If audit finds one that doesn't, that's a finding: promote it to the registry.
- **Cross-refs must resolve.** Every "see doc 0X §Y" points to a real section.
- **Contracts match shape.** JSON payload/response blocks in prose match `contracts.*` in the registry field-for-field.
- **Checklist coverage.** Each master-plan checklist item has a counterpart in the implementation and/or stakeholder doc.
- **Singletons are unique.** Dates, version tags, and test baselines appear identically everywhere.
- **Consistency ≠ safety.** A clean audit says the docs agree, not that the plan is sound. `review` is a separate gate and neither one substitutes for the other.
- **Doc 02 is executable, not descriptive.** Its reader is the builder. Resolved paths, final symbol names, paste-ready code, anchors to existing lines, and `[MANUAL]` on anything a program can't do.
- **A doc past ~600 lines gets split, not summarized.** `audit` warns at 500 so the split happens on a planned boundary instead of mid-sentence with cross-refs already written against the old numbering. Cut on a top-level phase boundary into `02` + `02b-<what-it-holds>.md`, keep reading order, leave the preamble in `02` and have `02b` declare it inherits it, register both in `docs[]`, and qualify every cross-ref that now crosses the boundary (`` `02` §1.1 ``, `` `02b` §3.5 ``). Full procedure in `references/doc-pattern.md` §Splitting an oversized doc. Compressing instead of splitting destroys the resolved paths and paste-ready blocks that make doc 02 usable.

## References
- `references/doc-pattern.md` — the 3-doc pattern, section skeletons, naming, cross-ref rules.
- `references/audit-protocol.md` — the exact mechanical checks + severity taxonomy + matrix format.
- `references/gap-sweep.md` — the `review` mode checklist: does this spec add functional/security gaps? Stack layers alongside it: `gap-sweep-web-baas.md`, `gap-sweep-android-native.md`, `gap-sweep-mobile-tv.md`.
- `references/intake.md` — the questions to ask before writing anything, batched, with what may never be guessed.
- `references/handoff.md` — the append-only `_log.md`, for sets passed between agents: entry format, dispositions, and why the log beats the context window.
- `references/evidence.md` — the `basis:` / `evidence:` contract, the `verify` mode, and the gates that keep an asserted root cause from shipping.
- `references/implementable.md` — how to write doc 02 so a context-free executor can build it.
- `templates/` — `_facts.yml.tpl`, `_log.md.tpl`, and one `.tpl` per doc.
- `profiles/` — `_profile.yml.tpl` (the contract) plus starter profiles per stack. Copy one into the repo as its `_profile.yml`; **never fill one in place** — a real `app_id` or agent name written into a starter leaks into every other project using this skill.
  - The starters and the `gap-sweep-<layer>.md` files are **independent and disposable**. A repo needs only the ones matching its stacks; delete the rest, nothing else references them. Adding one for a new stack is ~20 lines (profile) and ~40 (layer), and is the normal way this skill grows.
