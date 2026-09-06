# Audit Protocol

Mechanical consistency checks for a feature spec set. Run in order. Output = correspondence matrix + findings list. This is deterministic checking, NOT opinion — every finding cites a concrete mismatch.

## Run the script first

```
python3 scripts/audit.py docs/features/<slug>/
```

**Then** do the judgment pass over what it lists as `REQUIRES A HUMAN PASS`. In that order, and not the other way round.

The reason is measured, not stylistic. These checks are good and an agent runs *the ones it remembers* — in a long session, a few. A rough script with ~10 of them mechanized, run against three sets that had each already passed a "clean" audit done by hand against this same file, found **12, 11 and 7 findings**. None were subtle: broken anchors, a corrupted top-level key, orphan ids. A check that depends on recall is a check that fires when it is least needed.

Each check below is marked with who runs it:

- **[script]** — `audit.py` runs it. Do not re-do it by hand.
- **[human]** — needs judgment (wording, normalization, whether a reader would *follow* a ref) and is listed in the script's output so it cannot be quietly skipped.
- **[script + human]** — the script finds candidates, a person confirms them.

A `[script + human]` check is **still listed under `REQUIRES A HUMAN PASS`**. Narrowing
the search is not finishing it, and a candidate list nobody is told to read is a list
nobody reads. `tests/test_audit.py` derives the required listing from *both* tags, so
retagging a check here without giving it an entry in `HUMAN_PASS` fails the suite —
which is the v1.6.0 omission bug (checks 2, 5, 8, 11 and 12 tagged, unmechanized and
unlisted, so skipped in silence on every run) rebuilt out of its own fix.

One check is deliberately **not** automated: **1b's re-run of `evidence.cmd`**. A registry is a data file that travels between repos and agents; a tool that executes commands out of it because it claims they are safe is a tool that can be handed a malicious registry. Re-running evidence is a human step and the script says so.

## Inputs
- `_log.md` (**read first** — who last edited, against which versions; outranks context)
- `_facts.yml` (source of truth — what is claimed)
- `_profile.yml` (how this repo verifies — where every `cmd` must come from)
- All docs listed in `_facts.yml docs[]` **whose `stage:` the set has reached** (below).

## Stage gating — resolve this BEFORE running any check

A set is written in two stages: `new` produces the registry and doc 01, `implement`
produces docs 02 and 03 once the plan is confirmed. Auditing a stage-1 set with the
full check list reports a wall of DRIFT against files nobody was supposed to write
yet, which trains the reader to skim the findings — the failure this protocol exists
to prevent, one level up.

Resolve, in order:

1. `STATUS = _facts.yml status:`, ranked `draft(0) < reviewed(1) < implementing(2) < shipped(3)`.
   `paused` takes the rank of the last stage the set actually reached (`_log.md` says which);
   unknown or absent → `draft`.
2. For each `docs[]` entry, `STAGE = entry.stage` (absent → `draft`). **A set with no
   `stage:` anywhere audits exactly as it did before staging existed** — that is what
   makes the field safe to adopt one set at a time.
3. A doc is **in scope** when `rank(STAGE) <= rank(STATUS)`.

Then:

- **Out of scope and absent from disk → not a finding, and not silence either.** Say so
  in the verdict line: `stage draft — docs 02, 03 not due yet`. A reader must be able to
  tell "clean" from "clean so far", the same rule as a missing gap-sweep layer.
- **In scope and absent from disk → `DRIFT`.** The set claims a status it has not written
  the docs for.
- **Out of scope but present on disk → run every check against it anyway**, and flag the
  mismatch as `POLISH`: someone wrote ahead of the stage, or `status:` was rolled back
  and the doc was not. Never skip a file that exists — the checks are what catch the
  version that got written against the old plan.

Checks **5**, **6** and **13** read docs 02/03 and are the ones this gating switches off.
Every other check runs at every stage: they read the registry and doc 01, which exist
from the first minute.

## Checks

### 1. Data-vs-registry (highest priority) — [human]
For every shared datum in `_facts.yml`, grep each doc for where it's cited. Assert the doc's value/wording is **identical**.
- Doc value ≠ registry value → `CONTRADICTION`.
- Datum used in ≥2 docs but missing from registry → `DRIFT` (orphan fact — promote to registry).
- Same datum spelled differently across docs (e.g. `~100s` vs `100 seconds`) → `POLISH`.

### 1b. Basis re-verification — [script + human]
For every entry carrying `basis: measured`, **re-run `evidence.cmd`** (`how: shell|git`) and diff its output against `evidence.value`. For `how: device|log` — not re-runnable inline — check `evidence.date` for staleness instead.
- Live output ≠ `evidence.value` → `CONTRADICTION` (registry is stale — re-measure, update, `sync`). This catches the "296/296 copied everywhere but reality is 280/280" class before it reaches the docs.
- **Any world-claim with no `basis:` at all → `DRIFT`.** This covers more than numbers: a *behavioral* claim ("D-pad UP lands on grid index 0"), a *file/git-state* claim ("sin commitear"), and a *discard rationale* are all claims. It was asserted, not measured. Demand a basis.
- **`basis: asserted` on a cheap-to-verify state → `DRIFT`.** File existence, git tracking, `.git/info/exclude` membership, whether a symbol exists — one command each. Copying a file's state out of a sibling spec is the same defect as copying a test count. Real case: "Sin commitear" was lifted from a spec written 8 days earlier; both files were tracked.
- **`evidence.cmd` using regex alternation to derive scope → `DRIFT`.** `rg 'A|B'` fuses two result sets, so no member of the output can be attributed to one symbol. *Real case (React Native TV):* a single `rg 'VerticalCarousel|VerticalPaginated'` put 3 screens under the wrong component in `changes[]`. Split into one entry per symbol.
- `cmd` not runnable in this environment → note it and flag `evidence.date` as staleness risk if older than the last relevant change.
- **A `cmd` scoped by denylist is itself a finding** → `DRIFT`, even when its value still matches today. `rg … -g '!docs'` / `--exclude-dir` enumerate what to ignore, so every file added later — a session transcript at the repo root, a scratch note, a sibling spec — silently enters the result set. Demand positive scope: allowlist the extensions or paths that can legitimately contain the thing (`-g '*.ts' -g '*.tsx'`), or pipe through `git ls-files`. Real case: `rg -ln 'ErrorBoundary' -g '!node_modules' -g '!docs' | wc -l` was registered as `0`, later returned `1` by matching an LLM transcript in the repo root — and the doc that pasted the command said `Esperado: 0`, so the executor reads `1` as "an ErrorBoundary exists" and the premise of two hypotheses inverts.
- **A `cmd` pasted into a doc is the same datum as the registry's.** Grep the docs for the command string; a doc copy that drifted from `evidence.cmd` → `CONTRADICTION`. Fix both together.
- **`evidence.cmd` that is not derivable from `_profile.yml commands.*` → `DRIFT`.** A command authored inline is a shared datum with no home: `sync` can't propagate it, the next spec re-invents a slightly different one, and nothing detects the divergence. Either it belongs in the profile (add it) or it is a one-off whose `cmd` states so explicitly. Exception: ad-hoc `rg`/`git` invocations that derive a *specific* fact — those are per-claim by nature and stay in the registry.
- Legacy `verified: { cmd, date, value }` with no `basis:` → `POLISH`: rename to `basis: measured` + `evidence:`. Accepted for now; it is the same shape under the old name.

Full contract in `references/evidence.md`.

### 2. Singletons unique — [human]
`dates.*`, revision tags, `tests_baseline`, version numbers must be identical in every doc that mentions them. Any variance → `CONTRADICTION`.

### 3. Contract shape — [script + human]
Each JSON payload/response block in prose must match `contracts.*` field-for-field (same keys, same nesting). Extra/missing/renamed field → `CONTRADICTION`. Note: a field the sender injects downstream (not in the client body) is allowed IF a doc note explains it — flag as `POLISH` if the note is missing.

- **[script]** — the key-set diff is arithmetic and comes out as **candidates**. A contract entry holds several payloads (`request_body`, `response_ok`, `response_err`) and a fence shows one of them, so a fence is diffed against the payload it resembles; comparing against the entry's flattened field set would report every response field as missing from every request fence. Only brace-depth-1 keys count — a contract that declares a field but not its interior must not have every nested key reported as extra.
- **[human]** — the exception, which is the reason this is a candidate and not a finding: a field the sender injects downstream is legitimate **if a doc note explains it**, and the script cannot read the note. Find the note, or write the `POLISH`.
- **The seam with check 8 is exact, and neither check reports the other's cases:** a fence sharing no field with any payload has no contract to be compared against and is check 8's (prose-orphan); a fence sharing some but not all is this check's; a fence matching one payload exactly is silent in both. A fence the prose cites by `contracts.<id>` is judged here even when it shares nothing — being *attributed* to a contract is a stronger claim than resembling one.

### 4. Cross-refs resolve — [script + human]
Every "ver doc 0X §Y" / "see doc 0X" points to a doc in `docs[]` and a section that exists. Dangling ref → `DRIFT`.

- **[script]** — the sweep runs and emits **candidates**: it strips fenced blocks and inline spans (except a bare doc id, which is this file's own prefix notation) before comparing, binds a prefix only to the `§` it touches — a prefix does not distribute — reads the `§3.5 de 02b` shape, and resolves each ref against the target's headings. The unqualified ref that resolves in the *other* half of a split doc is called out as such, because it reads as valid and sends the executor to the wrong file.
- **[human]** — every hit, by eye. See the two exempt shapes below: (a) is stripped mechanically, **(b) is not and cannot be** — telling a changelog clause from five navigation targets means reading the sentence.
- **If the set contains a split doc** (`02` + `02b`), an unqualified `§X.Y` is read as local to its own file. One that resolves in neither the local file nor anywhere → `DRIFT`; one that silently resolves to the *other* half is worse: it reads as valid but sends the executor to the wrong file → `CONTRADICTION`. Sweep with `rg -n '§[0-9]'` over both halves and require the doc prefix on every boundary-crossing ref.
- **A prefix does not distribute across a list.** `` `02` §1.5, `02` §2.6, §3.6, §4.5, §5.3 `` reads as five refs into `02`, but the last three are local. Every element of a comma-separated ref list carries its own prefix, or none of them do and they're all local. Same for a prefix that appears *after* the ref (`§3.5 de 02b`) — legible to a human, invisible to a mechanical sweep, so prefer the prefix first.
- **Refs inside changelog rows are still refs.** They're the ones that survive a doc split unqualified, because nobody re-reads a changelog when moving sections. Include changelog tables in the sweep — especially the "pending work you inherit" column, which is read as instructions.
- **Two shapes are exempt, and a sweep that flags them is producing noise:** (a) a section number quoted *as text* — a defect being described (`` fixed the cross-ref `§3.6`→`§3.5` ``) or an example — is not a ref; (b) a changelog clause that names the doc once and then enumerates what changed inside it (`` `02` gained §0.3b, §1.1, §2.5 ``) is narrative about one doc, not five navigation targets. Judge by whether a reader would *follow* the ref. Mechanical sweeps over-report here: verify each hit by eye before writing it up.

### 5. Checklist coverage — [human] *stage-gated (needs 02 or 03)*
Each master-plan (doc 01) checklist item has a counterpart in doc 02 (implementation/test) and/or doc 03 (stakeholder). Item with no downstream counterpart → `DRIFT`.
- **When neither 02 nor 03 is in scope yet, this check does not go quiet — it inverts.** Emit every doc 01 checklist item under `pending downstream coverage`, as a list, not a finding. That list is the input `implement` must cover; without it the items are simply unread until someone rediscovers them, which is how a checklist item becomes a shipped gap. Not covering one later IS the `DRIFT`.

### 6. Acceptance parity — [human] *stage-gated (needs 02)*
Doc 02 "Definition of Done" (or, if 02 is split, whichever half holds it) == `_facts.yml acceptance[]` item-for-item. Divergence → `CONTRADICTION`.
- Before 02 exists, `acceptance[]` has no copy to diverge from and there is nothing to compare. It is still authored, still audited by every registry-level check, and still the contract — it is the *parity* that waits, not the criteria.

### 7. Scope parity — [human]
Compare **only** `changes[]` (components created/modified) against each doc's "componentes que cambian" table / affected-modules enumeration. Missing/extra member → `CONTRADICTION`.
- `related_docs[]` (referenced-but-unmodified docs) do **NOT** participate in scope parity — they are context pointers, not scope. A `related_doc` appearing in a "what changes" table is itself a `CONTRADICTION` (miscategorized: it's referenced, not modified). This is the "`manual-user-creation.md` (a reference) sat next to `resend-webhook` (a real new function) in one list" bug.

### 8. Prose-orphan contracts & endpoints — [script + human]
Scan every doc for interface material that should live in the registry but might not:
- ` ```json ` (and ` ```http `) code-fences → each payload/response must map to a `contracts.*` entry.
- URL / endpoint shapes in prose (absolute API paths, `/webhook/...`, provider-hosted function URLs, deep-link URIs) → each must map to an `endpoints.*` entry.

Any fence or URL with no registry home → `DRIFT` (prose-orphan contract — promote to `contracts.*`/`endpoints.*` so it becomes auditable). The mechanical audit is blind to contracts that live only in prose; this check is what surfaces them instead of relying on a human catching it by eye.

- **[script]** — the script emits **candidates**, not findings, under this check in `REQUIRES A HUMAN PASS`. It flags a ```json fence whose keys intersect no `contracts.*` entry and whose preceding lines cite no contract by id; a ```http fence whose request target matches no `endpoints.*`; and an API-shaped URL, provider-function host, bare `/webhook/…` path or non-http deep-link URI in prose with no `endpoints.*` home.
- **[human]** — the verdict on each candidate. A fence can legitimately show a fragment, an error body, or a third party's payload this set only reads; a URL can be a provider's documented callback that belongs in nobody's registry. Deciding needs the paragraph around it.
- **Four shapes are excluded by design, and a sweep that reports them is producing noise:** example hosts (`example.com`, `localhost`, `<placeholder>`), markdown link targets — a documentation link is written `[text](url)` while an endpoint this system calls is written bare or in backticks — fences in any other language, and URLs *inside* fenced blocks. The sweep is scoped to **prose**: a `curl` line in a ```bash fence is the command, not the interface.

### 9. Sibling-doc detection — [script + human]
Glob `docs/features/*<slug>*` (and adjacent files on the same theme under other names). Every match must be listed in `_facts.yml docs[]`.
- **[script]** — the two globs are mechanical and the script runs them: every `.md` in the spec dir, and every adjacent `*<slug>*.md` beside it. A match named by no `docs[]`, `related_docs[]` or `changes[]` entry is a finding, not a candidate — a file is in the registry or it is not, and there is no judgment in between. Set machinery (`_facts.yml`, `_log.md`, `_profile.yml`) is never a `docs[]` member and is exempt.
- **[human]** — the residue: a file on this feature's theme whose *name* shares nothing with the slug. No glob reaches it.
- File on this feature's theme not in `docs[]` → `DRIFT`: an unregistered sibling. It's outside the source-of-truth net, so it drifts silently (real case: an `-actionables.md` said 17 where the set said 16). Resolve by integrating it into the set or registering it with `role: legacy`.
- **The other direction, gated by stage:** a `docs[]` entry whose `stage:` the set has reached but whose file is not on disk → `DRIFT`. A set at `status: implementing` with no doc 02 is claiming a stage it never wrote. An entry whose stage is *not* reached and whose file is absent is correct and silent — see §Stage gating.

### 10. Placeholders resolved — [script]
Scan `_facts.yml` for `—`, `TBD`, `?`, `xxx` in `owners.*`, `dates.*`, `schedule.*.owner`, `schedule.*.target`, and any tracking table in the docs.
- Placeholder in a set whose `status` is not `draft` → `DRIFT`. It's an unmade decision parked in the source of truth; it will come back as a review round trip. Resolve owners from `git shortlog -sne -- <changed paths>`, dates from the user.

### 11. Ambiguous counters — [human]
Any integer field whose meaning depends on a predicate (`attended`, `resolved`, `remaining`, `migrated`) must carry a `note:` or a field name that states the predicate.
- Two counters that differ (`attended: 2` / `unblocked: 1`) with no note explaining why → `DRIFT`. Left alone, each doc paraphrases it differently and the set now claims two different facts.

### 12. Staleness by age — [human]
For every `evidence.date` — and, in a set still on the legacy shape this file accepts above, every `verified.date` — compare against today and against the last commit touching the measured surface.
- `evidence.date` older than the most recent change to what it measures → `CONTRADICTION` (re-run `cmd`).
- `evidence.date` older than 7 days on a volatile metric (prod counts, dashboard state) → `DRIFT`: re-measure before approval. Check 1b re-runs the command; this one flags the ones you'd never think to re-run because nothing looks wrong.

### 13. Doc 02 executability — [script + human] *stage-gated (needs 02)*
Parte A is the input to the builder. Scan it for:
- unresolved paths — `(o el componente correspondiente)`, `path/to/`, `…/algo` → `DRIFT`
- named-but-undefined symbols — a constant/toast/env var referenced without its file, exported name, and literal value → `DRIFT`
- edits with no anchor — "agregar X en Y" with no `file:line` or quoted neighboring line → `DRIFT`
- `etc.` / `y similares` / "análogo a lo anterior" in a step → `DRIFT` (enumerate)
- a test bullet with no target file path, or a test plan with no mock preamble copied from a real test in this repo → `DRIFT`
- a B.1 row worded as parity ("idéntico en ambos casos") or negation ("nunca dispara") with no `Falla si:` mutation stated → `DRIFT` (unverifiable — the null scenario passes by construction)
- a B.1 row whose assert subject is a service/util symbol but whose target file is a page-level test → `DRIFT` (layer mismatch — reaching it only through the UI collapses it into whichever row already exercises that click)
- a new persisted store with no full schema + access-control mechanism written out, in this stack's terms → `DRIFT` (see `references/implementable.md` §Schema / migrations)
- a step needing a dashboard/DNS/secret/judgment not labeled `[MANUAL]` / `[OWNER EXTERNO]` → `DRIFT`

**[script]** — three of those eight are regex-able and come out as **candidates**: unresolved paths (`path/to/`, `…/algo`, `(o el componente correspondiente)`), vague enumeration (`etc.`, `y similares`, `análogo a lo anterior`) and a step naming a dashboard/DNS/secret with no `[MANUAL]` label. The enumeration sweeps only lines shaped like a step — narrative that ends in "etc." is not an instruction anybody executes — and skip fenced blocks, since an identifier in a snippet is not an instruction to go and get one. The path sweep does read fences: a `path/to/` inside a paste-ready snippet is the defect at its worst, because that is the text the builder copies.

**[human]** — the other five, and the protocol's own enumeration says why. Symbols named but not defined, edits with no anchor, B.1 rows worded as parity or negation, a persisted store's schema, and *"a step that needs a dashboard/DNS/secret/**judgment**"* — the last names judgment outright, and the four before it each ask whether something ELSEWHERE supplies what the step assumes, which is what a line-oriented sweep is structurally unable to ask.

Rationale in `references/implementable.md`. Each of these is a question the builder must stop and ask — which is the same as a round trip.

### 14. Basis gates — [script]
Contract in `references/evidence.md`. These are the checks a clean consistency pass cannot make — they test the registry, not the copies of it.
- `status: shipped` with any `defects[]` entry `role: root_cause|contributing` still `basis: asserted` → `CONTRADICTION`. The set claims to know why the fix works and does not. Run `verify` before flipping the status.
  - **Unless the entry carries an `accepted:` block whose `until:` has not passed** — a recorded, dated decision to ship anyway. Then it is not a finding: the audit lists it under *Accepted risks, with their expiry*, and the verdict line counts it, so a clean run is never read as nothing-pending. Past `until:` → `CONTRADICTION` again, naming how many days late. A block missing any of `by` / `decided_on` / `until` / `because`, or a `by:` that reads like a model id, excuses nothing. Contract in `references/evidence.md` §Gates.
- `basis: asserted` with empty/absent `falsified_by:` → `DRIFT`. An unfalsifiable claim in the source of truth is the one that survives every audit and dies on device.
- `falsified_by:` naming an observation with no `log_line:` and no existing emitter → `DRIFT`. The instrumentation is spec, not an afterthought — added reactively, it costs a whole extra build/run cycle. `log_line: null` is the author declaring the emitter must be built and clears the gate; an absent key or a blank string does not.
- `alternatives[]` entry with `outcome: discarded`, `basis: asserted`, and a `depends_on` id whose `status: dead` → `CONTRADICTION`. It was discarded on a premise that no longer holds; `verify` should have reopened it.
- A `because:` / discard rationale that paraphrases another registry entry but omits `depends_on:` → `DRIFT`. The dependency exists whether or not it is written down; unwritten, the cascade cannot run.

### 15. Profile coverage — [script + human]
- No `_profile.yml` resolvable for this repo → `DRIFT`. Every `cmd` in the set was then invented per feature, and check 1b has nothing to compare against.
- `_profile.yml gap_sweep_layers:` empty while the repo's stack has a shipped layer (`references/gap-sweep-*.md`) → `DRIFT`: `review` ran the base sweep only and its "clean" is scoped narrower than it reads.
- A command string appearing in a doc that differs from the profile's, `{}` placeholders substituted → `CONTRADICTION`. Same rule as any other shared datum; the difference is that this one gets executed.
- `commands.tests_expect` not contained in `tests_baseline.evidence.value` → `DRIFT`. The baseline was recorded from a run whose pass line doesn't match what this repo prints, so nobody re-ran it here.
- A field on `references/intake.md`'s never-guess list holding a value the repo cannot corroborate, with no sign it was confirmed → `DRIFT`. It reads as settled and was assumed.
- **`_profile.yml repo:` ≠ `basename $(git rev-parse --show-toplevel)` → `CONTRADICTION`.** **[script]** — The profile came from another checkout — almost always because a spec folder was copied between projects and the profile travelled with it. Every `cmd` in the set now belongs to a different repo and every one of them still runs. Same defect class as copying a test count out of a sibling spec, one level up.
- **`_profile.yml app:` naming a subdirectory that is not the one holding this spec → `CONTRADICTION`.** **[script]** — The `app_id` is another variant's; `how: device` evidence was gathered against the wrong install.
- **`_facts.yml profile:` pointing at a different file than the upward walk resolves today → `DRIFT`.** A second profile appeared, or the set moved. Two profiles in one repo is the drift the single-source rule exists to prevent — reconcile before anything else, since every other check reads commands through it.
- **A starter in the skill's own `profiles/` holding a concrete value where the template has `<angle brackets>`** — a real `app_id`, a real repo name, a machine-specific `deep_review_agent` — → `DRIFT`. Starters are copied, never filled; a filled one leaks one project's identity into every other project that uses this skill.

### 16. Handoff log — [script + human]
Contract in `references/handoff.md`. Only applies once `_log.md` exists — a single-agent set never needs one, and its absence is not a finding.
- **A file's current `wc -l` + `git hash-object` differ from what the last entry naming it recorded → `DRIFT`.** Someone edited without appending. The next round is about to review a version no entry describes, and every disposition it writes will be against the wrong text.
- **A finding carried two or more rounds with no disposition → `DRIFT`.** Silence is how a finding gets rediscovered every round and settled in none.
- **A disposition of `rejected` with no command output or observation behind it → `DRIFT`.** "I disagree" is the finding surviving in disguise; a rejection is a claim and takes the same basis as any other.
- **An entry missing `agent`, `Read:`, or `Log read through:` → `DRIFT`.** Without them the entry cannot be checked against anything, which is the only thing it was for.
- **`_facts.yml status:` differs from the last `**Stage:**` line the log records, and no entry explains the change → `DRIFT`.** A stage transition puts docs into audit scope and unlocks `implement`; unrecorded, it is indistinguishable from a typo in the registry. A set whose log has no `Stage:` line at all and sits at `draft` is fine — nothing transitioned yet.
- **`Log read through:` naming a round earlier than the previous entry → `POLISH`**, and note it in the findings: that round skipped history and its dispositions may re-litigate settled items.
- **A transcribed entry with no `Source:` line → `DRIFT`.** A finding raised against a pasted excerpt and one raised against the full file are not the same claim.
- Round ids non-monotonic, or two entries with the same id → `CONTRADICTION`. Findings are addressed as `R<n>-F<m>`; ambiguous ids break every reference to them.

### 17. Doc size — [script]
`wc -l` every file in `docs[]`.
- >500 lines → `POLISH`: approaching the split threshold. Split NOW, on the next top-level phase boundary, before more cross-refs are written against the current numbering.
- >600 lines → `DRIFT`: split overdue. Crossing this mid-authoring means renumbering sections and re-qualifying every cross-ref by hand, in the middle of writing. Procedure in `references/doc-pattern.md` §Splitting an oversized doc.

### 18. Anchors resolve — [script]
Check 13 verifies an edit **has** an anchor. Nothing verified that the anchor **resolves**. Every `file:line` in `_facts.yml` and in prose: (a) the path resolves from the repo root, (b) the file exists, (c) the line is within range.
- Bare filename with no path (`index.ts:18`, `config.toml:7`) → `DRIFT`. In a repo with 267 files named `index.mjs` it resolves to nothing.
- File missing, or line past end of file → `CONTRADICTION`.
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

### 21. Registry ids ↔ prose — [script]
Check 1 covers "datum in ≥2 docs but not in the registry". Both inverses were missing.

- **Registry entry no prose doc mentions, by id or by value → `DRIFT`.** Measured, correct, and dead: nobody reads it because no doc names it. Real case: 4 in one set, **7** in a sibling that had never been through a mechanical audit. Citation *by value* counts — nobody writes `limits.cloudflare` inline, they write `100` and `524`.
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
Every `acceptance[]` criterion carries `status: written | executed | approved`. A plain string is still valid and reads as `written`, so older sets keep auditing — but a set cannot reach `shipped` on strings alone.
- `status: shipped` with a criterion `written` or with no status → `CONTRADICTION`.
- `shipped` with a criterion `executed` but not `approved` → `DRIFT`. Someone ran it; nobody signed it off.
- `approved` with no `verified_on:` → `DRIFT`. An approval with no date cannot be checked for staleness.
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

### 28. Tracking vs reality — [script + human]
`tracking.*` is where "cheap-to-verify state is never asserted" is broken most often.
- `tracking.branch` naming a branch that does not exist in this checkout → `DRIFT`. One command settles it.
- `status: implementing|shipped` with `issues: []` and `pr: null` → `DRIFT`. The work is trackable somewhere by now; an empty block in a shipped set is a field nobody went back to fill.
- `tracking.issues[]` / `pr` / `milestone` existing on GitHub and being coherent with `status:` → **[human]**, deliberately. `gh issue view` / `gh pr view` are network calls, and an auditor that reaches the network is a different kind of tool.

Real case: `branch` said `main` while the real branch was the feature one. It was corrected. After the merge it was wrong the other way. `issues: []` stayed empty in three sets long after the issues existed.

### 29. Provider behavior is observed, not described — [script]
`evidence.how: provider-behavior` claims what a third party actually does. Its `value` must be an **observed HTTP response** — status code and body. A `value` recording no status code → `CONTRADICTION`.

Real case: a claim about a file-type filter was corrected **twice, in opposite directions** — first understating the defence (*"only validated client-side"*), then overstating it (*"a tampered client cannot bypass it"*). Both times the error was reasoning about the provider's **configuration** instead of executing the flow. A configuration is what you asked for; behavior is what you get. `references/gap-sweep-web-baas.md` already warned about this class; the registry had no way to mark it.

## Enum fields are read lowercased — always

Every enum-valued field in the registry (`status`, `basis`, `role`, `kind`, `where`, `outcome`, `stage`, `evidence.how`, `acceptance[].status`) is compared against lowercase literals throughout this file. **Normalize before comparing, or the check fails open.**

This is not cosmetic. `status: Shipped` ranked as unknown, which ranks as `draft` — so a shipped set audited as a draft: G1 clean, checks 5, 6, 13 and 26 all skipped, with a root cause still `basis: asserted`. `role: Root_Cause` blinded G1 on its own. `kind: Deferred` never had its `reopens_when:` demanded. **A gate that fails open is worse than no gate**, because its silence reads as a pass.

The same rule applies one level down, to prose matching: an entry written `el cron borra…` and quoted in a doc as `El cron borra…` **is** being read. Reporting it as an orphan claims nobody reads it, which is a different and wrong claim. Whether it was copied verbatim is check 1's question, and a human one.

## Normalization before comparing
Before flagging any string mismatch (checks 1, 2, 6, 7): strip surrounding YAML quoting, collapse runs of whitespace, normalize typographic quotes/dashes to ASCII, and **unescape markdown table syntax — `\|` is a literal `|`**. A registry gate `data?.length === 0 || !selectedId` appears in a doc's table as `data?.length === 0 \|\| !selectedId`; comparing raw reports it as absent from every doc and sends you hunting an orphan fact that was never orphaned. The audit's own tooling is a source of false positives — when a datum looks missing from a doc that obviously should cite it, check the escaping before writing the finding. A registry entry authored as `"Botón 'Reenviar…'"` and prose reading `Botón "Reenviar…"` is a **quoting artifact, not a finding** — the fix is to re-author that registry entry as a single-quoted YAML scalar, not to edit the prose. Report those separately as `POLISH: quoting`, never as `CONTRADICTION`.

## Severity taxonomy
- **CONTRADICTION** — two sources assert different facts. Must fix before approval.
- **DRIFT** — structural gap: orphan fact, dangling ref, uncovered checklist item. Fix soon.
- **POLISH** — cosmetic/wording inconsistency; no factual conflict. Optional.

## Output format

**Correspondence matrix** — rows = shared data, columns = docs, cell = ✅ / ⚠️ / ✗ / — (n/a):

| Dato | 01 | 02 | 03 | Match |
|---|---|---|---|---|
| limits.cloudflare (100s/524) | ✅ | — | ✅ | ✅ |

**Findings** — most-severe first, one line each:
`doc0X §sec: <TAG>: <what mismatches>. <fix>.`

End with a one-line verdict: `N contradictions, M drift, K polish` or `clean — all shared data corresponds`.

## Deep pass (`--deep`)
After the inline checks, spawn a cold reviewer subagent with ONLY: the doc files + this protocol + `_facts.yml`. It must not see the authoring conversation. Ask it for findings in the same format. Merge with inline findings, dedupe by (doc, section, claim), present once. Rationale: inline validates against rules; the cold reader catches assumptions the author normalized away.
