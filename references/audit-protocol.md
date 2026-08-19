# Audit Protocol

Mechanical consistency checks for a feature spec set. Run in order. Output = correspondence matrix + findings list. This is deterministic checking, NOT opinion — every finding cites a concrete mismatch.

## Inputs
- `_facts.yml` (source of truth — what is claimed)
- `_profile.yml` (how this repo verifies — where every `cmd` must come from)
- All docs listed in `_facts.yml docs[]`.

## Checks

### 1. Data-vs-registry (highest priority)
For every shared datum in `_facts.yml`, grep each doc for where it's cited. Assert the doc's value/wording is **identical**.
- Doc value ≠ registry value → `CONTRADICTION`.
- Datum used in ≥2 docs but missing from registry → `DRIFT` (orphan fact — promote to registry).
- Same datum spelled differently across docs (e.g. `~100s` vs `100 seconds`) → `POLISH`.

### 1b. Basis re-verification
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

### 2. Singletons unique
`dates.*`, revision tags, `tests_baseline`, version numbers must be identical in every doc that mentions them. Any variance → `CONTRADICTION`.

### 3. Contract shape
Each JSON payload/response block in prose must match `contracts.*` field-for-field (same keys, same nesting). Extra/missing/renamed field → `CONTRADICTION`. Note: a field the sender injects downstream (not in the client body) is allowed IF a doc note explains it — flag as `POLISH` if the note is missing.

### 4. Cross-refs resolve
Every "ver doc 0X §Y" / "see doc 0X" points to a doc in `docs[]` and a section that exists. Dangling ref → `DRIFT`.
- **If the set contains a split doc** (`02` + `02b`), an unqualified `§X.Y` is read as local to its own file. One that resolves in neither the local file nor anywhere → `DRIFT`; one that silently resolves to the *other* half is worse: it reads as valid but sends the executor to the wrong file → `CONTRADICTION`. Sweep with `rg -n '§[0-9]'` over both halves and require the doc prefix on every boundary-crossing ref.
- **A prefix does not distribute across a list.** `` `02` §1.5, `02` §2.6, §3.6, §4.5, §5.3 `` reads as five refs into `02`, but the last three are local. Every element of a comma-separated ref list carries its own prefix, or none of them do and they're all local. Same for a prefix that appears *after* the ref (`§3.5 de 02b`) — legible to a human, invisible to a mechanical sweep, so prefer the prefix first.
- **Refs inside changelog rows are still refs.** They're the ones that survive a doc split unqualified, because nobody re-reads a changelog when moving sections. Include changelog tables in the sweep — especially the "pending work you inherit" column, which is read as instructions.
- **Two shapes are exempt, and a sweep that flags them is producing noise:** (a) a section number quoted *as text* — a defect being described (`` fixed the cross-ref `§3.6`→`§3.5` ``) or an example — is not a ref; (b) a changelog clause that names the doc once and then enumerates what changed inside it (`` `02` gained §0.3b, §1.1, §2.5 ``) is narrative about one doc, not five navigation targets. Judge by whether a reader would *follow* the ref. Mechanical sweeps over-report here: verify each hit by eye before writing it up.

### 5. Checklist coverage
Each master-plan (doc 01) checklist item has a counterpart in doc 02 (implementation/test) and/or doc 03 (stakeholder). Item with no downstream counterpart → `DRIFT`.

### 6. Acceptance parity
Doc 02 "Definition of Done" (or, if 02 is split, whichever half holds it) == `_facts.yml acceptance[]` item-for-item. Divergence → `CONTRADICTION`.

### 7. Scope parity
Compare **only** `changes[]` (components created/modified) against each doc's "componentes que cambian" table / affected-modules enumeration. Missing/extra member → `CONTRADICTION`.
- `related_docs[]` (referenced-but-unmodified docs) do **NOT** participate in scope parity — they are context pointers, not scope. A `related_doc` appearing in a "what changes" table is itself a `CONTRADICTION` (miscategorized: it's referenced, not modified). This is the "`manual-user-creation.md` (a reference) sat next to `resend-webhook` (a real new function) in one list" bug.

### 8. Prose-orphan contracts & endpoints
Scan every doc for interface material that should live in the registry but might not:
- ` ```json ` (and ` ```http `) code-fences → each payload/response must map to a `contracts.*` entry.
- URL / endpoint shapes in prose (absolute API paths, `/webhook/...`, provider-hosted function URLs, deep-link URIs) → each must map to an `endpoints.*` entry.

Any fence or URL with no registry home → `DRIFT` (prose-orphan contract — promote to `contracts.*`/`endpoints.*` so it becomes auditable). The mechanical audit is blind to contracts that live only in prose; this check is what surfaces them instead of relying on a human catching it by eye.

### 9. Sibling-doc detection
Glob `docs/features/*<slug>*` (and adjacent files on the same theme under other names). Every match must be listed in `_facts.yml docs[]`.
- File on this feature's theme not in `docs[]` → `DRIFT`: an unregistered sibling. It's outside the source-of-truth net, so it drifts silently (real case: an `-actionables.md` said 17 where the set said 16). Resolve by integrating it into the set or registering it with `role: legacy`.

### 10. Placeholders resolved
Scan `_facts.yml` for `—`, `TBD`, `?`, `xxx` in `owners.*`, `dates.*`, `schedule.*.owner`, `schedule.*.target`, and any tracking table in the docs.
- Placeholder in a set whose `status` is not `draft` → `DRIFT`. It's an unmade decision parked in the source of truth; it will come back as a review round trip. Resolve owners from `git shortlog -sne -- <changed paths>`, dates from the user.

### 11. Ambiguous counters
Any integer field whose meaning depends on a predicate (`attended`, `resolved`, `remaining`, `migrated`) must carry a `note:` or a field name that states the predicate.
- Two counters that differ (`attended: 2` / `unblocked: 1`) with no note explaining why → `DRIFT`. Left alone, each doc paraphrases it differently and the set now claims two different facts.

### 12. Staleness by age
For every `verified.date`, compare against today and against the last commit touching the measured surface.
- `verified.date` older than the most recent change to what it measures → `CONTRADICTION` (re-run `cmd`).
- `verified.date` older than 7 days on a volatile metric (prod counts, dashboard state) → `DRIFT`: re-measure before approval. Check 1b re-runs the command; this one flags the ones you'd never think to re-run because nothing looks wrong.

### 13. Doc 02 executability
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

Rationale in `references/implementable.md`. Each of these is a question the builder must stop and ask — which is the same as a round trip.

### 14. Basis gates
Contract in `references/evidence.md`. These are the checks a clean consistency pass cannot make — they test the registry, not the copies of it.
- `status: shipped` with any `defects[]` entry `role: root_cause|contributing` still `basis: asserted` → `CONTRADICTION`. The set claims to know why the fix works and does not. Run `verify` before flipping the status.
- `basis: asserted` with empty/absent `falsified_by:` → `DRIFT`. An unfalsifiable claim in the source of truth is the one that survives every audit and dies on device.
- `falsified_by:` naming an observation with no `log_line:` and no existing emitter → `DRIFT`. The instrumentation is spec, not an afterthought — added reactively, it costs a whole extra build/run cycle.
- `alternatives[]` entry with `outcome: discarded`, `basis: asserted`, and a `depends_on` id whose `status: dead` → `CONTRADICTION`. It was discarded on a premise that no longer holds; `verify` should have reopened it.
- A `because:` / discard rationale that paraphrases another registry entry but omits `depends_on:` → `DRIFT`. The dependency exists whether or not it is written down; unwritten, the cascade cannot run.

### 15. Profile coverage
- No `_profile.yml` resolvable for this repo → `DRIFT`. Every `cmd` in the set was then invented per feature, and check 1b has nothing to compare against.
- `_profile.yml gap_sweep_layers:` empty while the repo's stack has a shipped layer (`references/gap-sweep-*.md`) → `DRIFT`: `review` ran the base sweep only and its "clean" is scoped narrower than it reads.
- A command string appearing in a doc that differs from the profile's, `{}` placeholders substituted → `CONTRADICTION`. Same rule as any other shared datum; the difference is that this one gets executed.
- `commands.tests_expect` not contained in `tests_baseline.evidence.value` → `DRIFT`. The baseline was recorded from a run whose pass line doesn't match what this repo prints, so nobody re-ran it here.
- A field on `references/intake.md`'s never-guess list holding a value the repo cannot corroborate, with no sign it was confirmed → `DRIFT`. It reads as settled and was assumed.
- **`_profile.yml repo:` ≠ `basename $(git rev-parse --show-toplevel)` → `CONTRADICTION`.** The profile came from another checkout — almost always because a spec folder was copied between projects and the profile travelled with it. Every `cmd` in the set now belongs to a different repo and every one of them still runs. Same defect class as copying a test count out of a sibling spec, one level up.
- **`_profile.yml app:` naming a subdirectory that is not the one holding this spec → `CONTRADICTION`.** The `app_id` is another variant's; `how: device` evidence was gathered against the wrong install.
- **`_facts.yml profile:` pointing at a different file than the upward walk resolves today → `DRIFT`.** A second profile appeared, or the set moved. Two profiles in one repo is the drift the single-source rule exists to prevent — reconcile before anything else, since every other check reads commands through it.
- **A starter in the skill's own `profiles/` holding a concrete value where the template has `<angle brackets>`** — a real `app_id`, a real repo name, a machine-specific `deep_review_agent` — → `DRIFT`. Starters are copied, never filled; a filled one leaks one project's identity into every other project that uses this skill.

### 16. Doc size
`wc -l` every file in `docs[]`.
- >500 lines → `POLISH`: approaching the split threshold. Split NOW, on the next top-level phase boundary, before more cross-refs are written against the current numbering.
- >600 lines → `DRIFT`: split overdue. Crossing this mid-authoring means renumbering sections and re-qualifying every cross-ref by hand, in the middle of writing. Procedure in `references/doc-pattern.md` §Splitting an oversized doc.

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
