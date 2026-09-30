# Audit Protocol

Mechanical consistency checks for a feature spec set. Run in order. Output = correspondence matrix + findings list. This is deterministic checking, NOT opinion — every finding cites a concrete mismatch.

## Run the script first

```
python3 scripts/audit.py docs/features/<slug>/
```

**Then** do the judgment pass over what it lists as `REQUIRES A HUMAN PASS`. In that order, and not the other way round.

The reason is measured, not stylistic. These checks are good and an agent runs *the ones it remembers* — in a long session, a few. A rough script with ~10 of them mechanized, run against three sets that had each already passed a "clean" audit done by hand against this same file, found **12, 11 and 7 findings**. None were subtle: broken anchors, a corrupted top-level key, orphan ids. A check that depends on recall is a check that fires when it is least needed.

Each check below is marked with who runs it:

- **[script]** — `audit.py` runs it. Do not re-do it by hand. Listed at the end of §Checks by number only; the full text lives in `references/audit-checks-script.md`, read when one of its findings needs explaining.
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

### Previewing a stage before flipping it — `--as-status <stage>`

`python3 scripts/audit.py docs/features/<slug>/ --as-status shipped` audits the set as if
`status:` already read `shipped`: every gate that keys on the status (G1, checks 10, 14,
20, 26, 28, and the stage scope above) runs at that rank. The override lives in memory
and the file is not touched; the header says `audited AS`, so the output cannot be
mistaken for the real state. Check 16's `Stage:` comparison is the one thing skipped —
the transition has not happened, and reporting that the log does not record it would be
a finding the preview itself manufactured.

*Real case:* a research set about to be flipped to `shipped` was audited on a copy made
outside the repo to see what the flip would cost. **54** findings came back, most of them
anchors reported missing only because the copy lived elsewhere — noise that had to be
told apart from the nine asserted defects, three open questions and twelve unverified
criteria that were real. In place, every anchor still resolves and only the flip's own
cost shows.

`--today YYYY-MM-DD` does the same for the calendar: it is the date `accepted.until:` is
measured against, so `--today` the day after an expiry shows the G1 refusal that is
coming, before it comes.

## Checks

### 1. Data-vs-registry (highest priority) — [human]
For every shared datum in `_facts.yml`, find where each doc cites it. Assert the doc's value/wording is **identical**.

**Start from the matrix the script printed, not from a grep per datum.** A counted cell is a verbatim citation — identical by construction. The work is the `·` cells: for each, either the doc has no reason to cite the datum, or it cites it in other words, and only the second is a finding. Two things the count cannot see: a fenced block is not counted, and a short value (`100`, `2026`) also matches where it means something else.
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
`dates.*`, revision tags, `tests_baseline`, version numbers must be identical in every doc that mentions them. Any variance → `CONTRADICTION`. The date each changelog gives a revision tag, and the order of those entries, is check 40's and mechanical; the rest stays here.

### 3. Contract shape — [script + human]
Each JSON payload/response block in prose must match `contracts.*` field-for-field (same keys, same nesting). Extra/missing/renamed field → `CONTRADICTION`. Note: a field the sender injects downstream (not in the client body) is allowed IF a doc note explains it — flag as `POLISH` if the note is missing.

- **A descriptive key is not a field, and the LEVEL is what says so.** `note:`, `auth:`, `description:` sitting beside `fields:` / `columns:` / `request_body:` describe the entry; the same word one level down, inside a payload, is a field. The script strips them at the entry and nowhere below it, and only when the entry declares a payload container at all — an entry with no container *is* the payload, so nothing in it may be stripped. Motivating case: `{ fields: [a, b, c], note: "..." }` against a prose fence of exactly those three fields — a **perfect match** — was reported as `missing {fields, note}`, because one scalar sibling made "every value is a container" false and collapsed the entry into a single payload. Stripping by NAME instead of by level is the trap: it turns nine false positives into thirteen different ones (a real column, on another contract, sharing the same word as the first contract's metadata).
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
- **A line naming three or more unresolved refs is enumerating, not pointing → one collapsed candidate**, which names them all so the clause can be dismissed in one read. Same idiom and same reason as checks 26 and 30: reporting eleven hits from one sentence buries every other finding in the set. *Real case:* a single changelog row (`CHANGELOG.md:14`) produced **11 of that set's 21 candidates**. Two refs on a line stay two — two is pointing.
- **`§1–§5` is one span, not two refs.** Only its first member is checked; its far end is nobody's destination. *Real case:* `> Las referencias a §1–§5 apuntan a 01, las de §6–§8 a 01b` — a **legend** declaring how to read the rest of the document. It produced four candidates and rode through 48 review rounds untouched, which is the closest thing to a recorded human verdict of *not a finding* this corpus offers.
- **Two shapes are exempt, and a sweep that flags them is producing noise:** (a) a section number quoted *as text* — a defect being described (`` fixed the cross-ref `§3.6`→`§3.5` ``) or an example — is not a ref; (b) a changelog clause that names the doc once and then enumerates what changed inside it (`` `02` gained §0.3b, §1.1, §2.5 ``) is narrative about one doc, not five navigation targets. Judge by whether a reader would *follow* the ref. Mechanical sweeps over-report here: verify each hit by eye before writing it up.

### 5. Checklist coverage — [human] *stage-gated (needs 02 or 03)*
Each master-plan (doc 01) checklist item has a counterpart in doc 02 (implementation), doc 02e (test / E2E) and/or doc 03 (stakeholder). Item with no downstream counterpart → `DRIFT`.
- **When neither 02 nor 03 is in scope yet, this check does not go quiet — it inverts.** Emit every doc 01 checklist item under `pending downstream coverage`, as a list, not a finding. That list is the input `implement` must cover; without it the items are simply unread until someone rediscovers them, which is how a checklist item becomes a shipped gap. Not covering one later IS the `DRIFT`.

### 6. Acceptance parity — [human] *stage-gated (needs 02)*
The "Definition of Done" — doc 02e, or whichever doc holds it in a set written before `02e` existed — == `_facts.yml acceptance[]` item-for-item, criteria with `status: retired` left out. Divergence → `CONTRADICTION`.
- Before 02 exists, `acceptance[]` has no copy to diverge from and there is nothing to compare. It is still authored, still audited by every registry-level check, and still the contract — it is the *parity* that waits, not the criteria.

### 7. Scope parity — [human]
Compare **only** `changes[]` (components created/modified) against each doc's "componentes que cambian" table / affected-modules enumeration. Missing/extra member → `CONTRADICTION`. This compares the registry with the documents; whether the registry matches the **tree** is check 38's, and mechanical.
- `related_docs[]` (referenced-but-unmodified docs) do **NOT** participate in scope parity — they are context pointers, not scope. A `related_doc` appearing in a "what changes" table is itself a `CONTRADICTION` (miscategorized: it's referenced, not modified). This is the "`manual-user-creation.md` (a reference) sat next to `resend-webhook` (a real new function) in one list" bug.

### 8. Prose-orphan contracts & endpoints — [script + human]
Scan every doc for interface material that should live in the registry but might not:
- ` ```json ` (and ` ```http `) code-fences → each payload/response must map to a `contracts.*` entry.
- URL / endpoint shapes in prose (absolute API paths, `/webhook/...`, provider-hosted function URLs, deep-link URIs) → each must map to an `endpoints.*` entry.

Any fence or URL with no registry home → `DRIFT` (prose-orphan contract — promote to `contracts.*`/`endpoints.*` so it becomes auditable). The mechanical audit is blind to contracts that live only in prose; this check is what surfaces them instead of relying on a human catching it by eye.

- **[script]** — the script emits **candidates**, not findings, under this check in `REQUIRES A HUMAN PASS`. It flags a ```json fence whose keys intersect no `contracts.*` entry and whose preceding lines cite no contract by id; a ```http fence whose request target matches no `endpoints.*`; and an API-shaped URL, provider-function host, bare `/webhook/…` path or non-http deep-link URI in prose with no `endpoints.*` home.
- **[human]** — the verdict on each candidate. A fence can legitimately show a fragment, an error body, or a third party's payload this set only reads; a URL can be a provider's documented callback that belongs in nobody's registry. Deciding needs the paragraph around it.
- **A ```json fence that is a FILE's contents is not interface material.** Doc 02 is paste-ready by design, so a set that creates a project ships `package.json`, `tsconfig*.json`, MCP configs and its i18n bundles as fences — every one shaped exactly like a payload, none of them addressable by anybody. Three signals, all structural, and they collapse into one count per document rather than disappearing: the nearest prose names a `.json` file (`` **Archivo:** `mcp-server/tsconfig.json` (nuevo) ``, `` **Código — `es.json`:** ``); the fence's own keys carry a manifest signature (`compilerOptions`, `devDependencies`, `mcpServers`, `name`+`version`+`scripts`) for a file the prose never names; or the body does not open with `{` or `[` — a key fragment, which is the second and later fence of one file and cannot be diffed field-for-field against anything. Measured: **15 of 19** real candidates were the first signal, and 6 more the other two. What survives is what should: a payload with no registry home, and a URL that needs the paragraph around it.
- **Four shapes are excluded by design, and a sweep that reports them is producing noise:** example hosts (`example.com`, `localhost`, `<placeholder>`), markdown link targets — a documentation link is written `[text](url)` while an endpoint this system calls is written bare or in backticks — fences in any other language, and URLs *inside* fenced blocks. The sweep is scoped to **prose**: a `curl` line in a ```bash fence is the command, not the interface.

### 9. Sibling-doc detection — [script + human]
Glob `docs/features/*<slug>*` (and adjacent files on the same theme under other names). Every match must be listed in `_facts.yml docs[]`.
- **[script]** — the two globs are mechanical and the script runs them: every `.md` in the spec dir, and every adjacent `*<slug>*.md` beside it. A match named by no `docs[]`, `related_docs[]` or `changes[]` entry is a finding, not a candidate — a file is in the registry or it is not, and there is no judgment in between. Set machinery (`_facts.yml`, `_log.md`, `_profile.yml`) is never a `docs[]` member and is exempt.
- **[human]** — the residue: a file on this feature's theme whose *name* shares nothing with the slug. No glob reaches it.
- File on this feature's theme not in `docs[]` → `DRIFT`: an unregistered sibling. It's outside the source-of-truth net, so it drifts silently (real case: an `-actionables.md` said 17 where the set said 16). Resolve by integrating it into the set or registering it with `role: legacy`.
- **The other direction, gated by stage:** a `docs[]` entry whose `stage:` the set has reached but whose file is not on disk → `DRIFT`. A set at `status: implementing` with no doc 02 is claiming a stage it never wrote. An entry whose stage is *not* reached and whose file is absent is correct and silent — see §Stage gating.

### 11. Ambiguous counters — [human]
Any integer field whose meaning depends on a predicate (`attended`, `resolved`, `remaining`, `migrated`) must carry a `note:` or a field name that states the predicate.
- Two counters that differ (`attended: 2` / `unblocked: 1`) with no note explaining why → `DRIFT`. Left alone, each doc paraphrases it differently and the set now claims two different facts.

### 12. Staleness by age — [human]
For every `evidence.date` — and, in a set still on the legacy shape this file accepts above, every `verified.date` — compare against today and against the last commit touching the measured surface.
- `evidence.date` older than the most recent change to what it measures → `CONTRADICTION` (re-run `cmd`).
- `evidence.date` older than 7 days on a volatile metric (prod counts, dashboard state) → `DRIFT`: re-measure before approval. Check 1b re-runs the command; this one flags the ones you'd never think to re-run because nothing looks wrong.

This dates evidence. Prose that went stale while its evidence stayed fresh is checks 41 and 42.

### 13. Doc 02 executability — [script + human] *stage-gated (needs 02)*
Parte A (doc 02) is the input to the builder and Parte B (doc 02e) the input to whoever proves it; every doc whose id starts with `02` is scanned. Scan for:
- unresolved paths — `(o el componente correspondiente)`, `path/to/`, `…/algo` → `DRIFT`
- named-but-undefined symbols — a constant/toast/env var referenced without its file, exported name, and literal value → `DRIFT`
- edits with no anchor — "agregar X en Y" with no `file:line` or quoted neighboring line → `DRIFT`
- `etc.` / `y similares` / "análogo a lo anterior" in a step → `DRIFT` (enumerate)
- a test bullet with no target file path, or a test plan with no mock preamble copied from a real test in this repo → `DRIFT`
- a B.1 row worded as parity ("idéntico en ambos casos") or negation ("nunca dispara") with no `Falla si:` mutation stated → `DRIFT` (unverifiable — the null scenario passes by construction)
- a B.1 row whose assert subject is a service/util symbol but whose target file is a page-level test → `DRIFT` (layer mismatch — reaching it only through the UI collapses it into whichever row already exercises that click)
- a new persisted store with no full schema + access-control mechanism written out, in this stack's terms → `DRIFT` (see `references/implementable.md` §Schema / migrations)
- a step needing a dashboard/DNS/secret/judgment not labeled `[MANUAL]` / `[OWNER EXTERNO]` → `DRIFT`

- **The external-step sweep requires a named provider, or it collapses.** `dashboard` alone cannot carry this rule: measured over 25 real candidates, 19 fired on that word and only **5 of the 25** named a provider — the rest were in-app navigation (`Navegar a la semana siguiente en el Dashboard`), a deliberately **fake** secret in a test, and blocking DNS inside a network test. A hit beside a provider name, a `consola de …` or a URL stays a candidate with its line; the unqualified ones become **one count per document**, naming their lines. Collapsed, never dropped — the reader is still told they exist and can grep. The cost is a real external step that names no provider, which now arrives inside the count instead of on its own line; that is the trade this check makes everywhere, and a wall of four-in-five noise is what stops the list being read at all.

**[script]** — three of those eight are regex-able and come out as **candidates**: unresolved paths (`path/to/`, `…/algo`, `(o el componente correspondiente)`), vague enumeration (`etc.`, `y similares`, `análogo a lo anterior`) and a step naming a dashboard/DNS/secret with no `[MANUAL]` label. The enumeration sweeps only lines shaped like a step — narrative that ends in "etc." is not an instruction anybody executes — and skip fenced blocks, since an identifier in a snippet is not an instruction to go and get one. The path sweep does read fences: a `path/to/` inside a paste-ready snippet is the defect at its worst, because that is the text the builder copies.

**[human]** — the other five, and the protocol's own enumeration says why. Symbols named but not defined, edits with no anchor, B.1 rows worded as parity or negation, a persisted store's schema, and *"a step that needs a dashboard/DNS/secret/**judgment**"* — the last names judgment outright, and the four before it each ask whether something ELSEWHERE supplies what the step assumes, which is what a line-oriented sweep is structurally unable to ask.

Rationale in `references/implementable.md`. Each of these is a question the builder must stop and ask — which is the same as a round trip.

### 15. Profile coverage — [script + human]
- No `_profile.yml` resolvable for this repo → `DRIFT`. Every `cmd` in the set was then invented per feature, and check 1b has nothing to compare against.
- `_profile.yml gap_sweep_layers:` empty while the repo's stack has a shipped layer (`references/gap-sweep-*.md`) → `DRIFT`: `review` ran the base sweep only and its "clean" is scoped narrower than it reads.
- A command string appearing in a doc that differs from the profile's, `{}` placeholders substituted → `CONTRADICTION`. Same rule as any other shared datum; the difference is that this one gets executed.
- `commands.tests_expect` not contained in `tests_baseline.evidence.value` → `DRIFT`. The baseline was recorded from a run whose pass line doesn't match what this repo prints, so nobody re-ran it here.
- A field on `references/intake.md`'s never-guess list holding a value the repo cannot corroborate, with no sign it was confirmed → `DRIFT`. It reads as settled and was assumed.
- **`_profile.yml repo:` ≠ `basename $(git rev-parse --show-toplevel)` → `CONTRADICTION`.** **[script]** — The profile came from another checkout — almost always because a spec folder was copied between projects and the profile travelled with it. Every `cmd` in the set now belongs to a different repo and every one of them still runs. Same defect class as copying a test count out of a sibling spec, one level up.
- **`_profile.yml app:` naming a subdirectory that is not the one holding this spec → `CONTRADICTION`.** **[script]** — The `app_id` is another variant's; `how: device` evidence was gathered against the wrong install.
- **`_facts.yml profile:` resolving outside the repo root — or outside the directory holding the feature folders, which is where `../_profile.yml` legitimately lands — → `CONTRADICTION`, and the file is not read.** A profile is opened, parsed as YAML and quoted back in findings, so a `profile:` is the one registry path that discloses content rather than just existence.
- **`_facts.yml profile:` pointing at a different file than the upward walk resolves today → `DRIFT`.** A second profile appeared, or the set moved. Two profiles in one repo is the drift the single-source rule exists to prevent — reconcile before anything else, since every other check reads commands through it.
- **A starter in the skill's own `profiles/` holding a concrete value where the template has `<angle brackets>`** — a real `app_id`, a real repo name, a machine-specific `deep_review_agent` — → `DRIFT`. Starters are copied, never filled; a filled one leaks one project's identity into every other project that uses this skill.

### 16. Handoff log — [script + human]
Contract in `references/handoff.md`. Only applies once `_log.md` exists — a single-agent set never needs one, and its absence is not a finding.

**[script]** settles every bullet below except the two about dispositions — round order, the three required fields, the `Stage:` line, the log's size, and each file's version. Only `**Read:**` and `**Edits:**` lines are read for versions, and HTML comments (the template's commented example) are skipped.
- **A file's current `wc -l` + `git hash-object` differ from what the last entry naming it recorded → `DRIFT`.** Someone edited without appending. The next round is about to review a version no entry describes, and every disposition it writes will be against the wrong text. The blob is computed the way git computes it, so a gitignored spec needs no git at all.
  *Real case, and why this left the human list:* the command that opened a round's stub failed with a shell error (`unmatched "`); its author read the next line of output instead and worked a whole round with nothing on disk. It surfaced only at the end, when the closing edit found no anchor. From the next round it is exactly this finding.
- **A set's own file (`_facts.yml`, a doc, the profile) last named in `Read:` / `Edits:` with no line count and no blob → `DRIFT`.** `_facts.yml (v17)` names a revision the log cannot check against the disk. A code file named in `Edits:` is exempt — its version is git's business.
- **`_log.md` past 800 lines or 80KB → `POLISH`.** Whichever comes first: a log written in long paragraphs is 103KB at 701 lines, and lines alone left it silent. The log outranks the context window only while it fits in one. Rotate it — `references/handoff.md` §Rotating the log — never summarize it.
- **A finding carried two or more rounds with no disposition → `DRIFT`.** Silence is how a finding gets rediscovered every round and settled in none.
- **A disposition of `rejected` with no command output or observation behind it → `DRIFT`.** "I disagree" is the finding surviving in disguise; a rejection is a claim and takes the same basis as any other.
- **An entry missing `agent`, `Read:`, or `Log read through:` → `DRIFT`.** Without them the entry cannot be checked against anything, which is the only thing it was for.
- **`_facts.yml status:` differs from the last `**Stage:**` line the log records, and no entry explains the change → `DRIFT`.** A stage transition puts docs into audit scope and unlocks `implement`; unrecorded, it is indistinguishable from a typo in the registry. A set whose log has no `Stage:` line at all and sits at `draft` is fine — nothing transitioned yet.
- **`Log read through:` naming a round earlier than the previous entry → `POLISH`**, and note it in the findings: that round skipped history and its dispositions may re-litigate settled items.
- **A transcribed entry with no `Source:` line → `DRIFT`.** A finding raised against a pasted excerpt and one raised against the full file are not the same claim.
- Round ids non-monotonic, or two entries with the same id → `CONTRADICTION`. Findings are addressed as `R<n>-F<m>`; ambiguous ids break every reference to them. **Exempt: two consecutive headings with one id** — a stub and its completion appended rather than edited in place (`— STUB` / `— CERRADA`), which is the stub rule's own shape. Their fields are read across both.
- More than three entries missing required fields collapse into **one** finding naming them all: a log that stopped recording `Read:` did so for a stretch of rounds, and fifteen identical findings bury the rest of the report.
- **[human]**, and only these two: a finding carried two rounds with no disposition, and a `rejected` with no output behind it. Both are readings of what a disposition says.

### 28. Tracking vs reality — [script + human]
`tracking.*` is where "cheap-to-verify state is never asserted" is broken most often.
- `tracking.branch` naming a branch that does not exist in this checkout → `DRIFT`. One command settles it.
- `status: implementing|shipped` with `issues: []` and `pr: null` → `DRIFT`. The work is trackable somewhere by now; an empty block in a shipped set is a field nobody went back to fill.
- `tracking.issues[]` / `pr` / `milestone` existing on GitHub and being coherent with `status:` → **[human]**, deliberately. `gh issue view` / `gh pr view` are network calls, and an auditor that reaches the network is a different kind of tool.

Real case: `branch` said `main` while the real branch was the feature one. It was corrected. After the merge it was wrong the other way. `issues: []` stayed empty in three sets long after the issues existed.

### 36. Retractions and corrections — [script + human]
Two shapes that were already in use by hand, and that nothing read:

```yaml
retracted_on: 2026-09-21          # the entry no longer holds. Kept, never deleted —
retracted_by: limits.<replacement> #   a deleted entry gets re-derived. Or, with no
                                   #   replacement: retracted_because: '<why>'
corrected_on: 2026-09-23          # the entry holds, amended — usually in place
corrected_by: limits.<evidence>   # optional: what forced the correction
correction: '<what changed, one sentence a citing set can quote>'
```

- **Format.** `retracted_on:` with neither `retracted_by:` nor `retracted_because:` → `DRIFT`. `corrected_on:` with no `correction:` → `DRIFT`. A `retracted_by:` / `corrected_by:` naming an id this registry does not define → `DRIFT`.
- **[script] A citation of a RETRACTED entry that does not mention it → `DRIFT`.** Read in this set's docs and registry (`container.id`), and in another set's entries cited the qualified way (`` `docs/features/<slug>/_facts.yml` container.id ``, loaded exactly as check 30 does). *Mentions* means the citing paragraph — a table row counts as its own paragraph — or the citing registry entry names the replacement or says the word (`retract…`, `correg…`, `supersed…`, `reemplaz…`). The retracted entry itself and the one that replaced it are exempt; `_log.md` is history and is not read; a `derived_from:` is check 35's.
- **[human] A citation of a CORRECTED entry that does not mention it → candidate.** A corrected entry is usually fixed in place: a sentence written *after* the fix cites the right thing and has no reason to mention the history, and nothing in a markdown line says when it was written. Read each candidate against `correction:`.

The citing set learns about the owner's correction the next time the **citing set** is audited — the audit does not sweep every other set in the repo for citations of the one being audited. That direction has no bound and no owner; this one runs whenever the citing set is touched, which is when its prose is about to be relied on.

*Real case:* `sports-multiview-grid` cites limits of the research set that measured them. When the research corrected one — the sign of a comparison was backwards — nothing told the grid. The candidate/finding split is measured, not assumed: on the two real sets holding such citations, the two in the research set were notes written before the correction and framed exactly the way it inverted; the seven in the other set cited an entry rewritten and renamed in place, one of them in a paragraph that says outright that the first reading was wrong.


### 42. Prose older than what it cites — [script + human]
A doc regenerated on a date is right about the registry **as of** that date. `docs[].regenerated_on:` records it.
- **[script]** — for each doc with the field, every registry entry it cites (by id, or `container.key`) that moved afterwards — any of check 41's dates — comes out as a **candidate**, most recent first. A doc with no `regenerated_on:` in an `implementing` / `shipped` set is a candidate too: it cannot be dated at all.
- **[human]** — most sentences citing a moved entry are still true: a component that got built is still the component the doc describes. Read each listed citation against the entry as it is now; then bump `regenerated_on:`.

*Real case:* the stakeholder doc — the one handed to an external reviewer — went **31 rounds** untouched and carried **five false claims**, one contradicting a measurement in its own registry. Check 12 dates `evidence.date`; nothing dated prose.

### 43. Contract vs the code that validates it — [script + human]
Check 3 compares `contracts.*` with prose. Nothing compared it with the code that reads the payload at runtime — so a field could be added to the registry and to seven documents and still be missing from the validator, the first symptom an `undefined` three phases from the cause.

`contracts.<id>.validated_in: <path>` names that code. It is entry-level metadata, stripped before check 3 diffs anything.
- **`validated_in:` that does not resolve to a file → `CONTRADICTION`.**
- **[script]** — each payload field the file never names, as a word, is a **candidate**. A grep, never an execution (§Run the script first).
- **[human]** — a validator that loops over a list built elsewhere names no field and is still right. The durable bridge is a **contract parity test** in the repo, which reads `contracts.*` from the registry on every run: `references/implementable.md` §Contract parity.

### Checks the script settles on its own — [script]

Listed here by number and name only. **Do not run them by hand and do not read their
rationale to run an audit** — `audit.py` runs every one and prints what fails as a finding
with its fix. The full text of each — what it catches, the real case behind it, the false
positives it must not raise — is `references/audit-checks-script.md`, read when a finding
from one of them needs explaining, disputing or changing, and not otherwise.

| check | name |
|---|---|
| 10 | Placeholders resolved |
| 14 | Basis gates |
| 14b | Accepted risks coming due |
| 17 | Doc size |
| 18 | Anchors resolve |
| 19 | Registry shape vs template |
| 20 | Declared paths exist |
| 21 | Registry ids ↔ prose |
| 22 | Phase numbering |
| 23 | `changes[]` lifecycle |
| 24 | `evidence.cmd` is runnable verbatim |
| 25 | Declared dependencies |
| 26 | Acceptance state |
| 27 | Dead-dependency cascade |
| 29 | Provider behavior is observed, not described |
| 30 | Sample size and spread |
| 31 | Conditions of the run |
| 32 | A run without its precondition produced no datum |
| 33 | Absence of signal is not signal of absence |
| 34 | `changes[]` dependency on a revised decision or a settled hypothesis |
| 35 | Derived evidence |
| 37 | Registry ids unique |
| 38 | Source tree vs `changes[]` |
| 39 | `changes[]` built state |
| 40 | Revision order |
| 41 | Provisional prose |

## Enum fields are read lowercased — always

Every enum-valued field in the registry (`status` — the set's, a defect's, a criterion's —, `basis`, `role`, `kind`, `where`, `outcome`, `stage`, `evidence.how`, `acceptance[].status`, including `retired`) is compared against lowercase literals throughout this file. **Normalize before comparing, or the check fails open.**

This is not cosmetic. `status: Shipped` ranked as unknown, which ranks as `draft` — so a shipped set audited as a draft: G1 clean, checks 5, 6, 13 and 26 all skipped, with a root cause still `basis: asserted`. `role: Root_Cause` blinded G1 on its own. `kind: Deferred` never had its `reopens_when:` demanded. **A gate that fails open is worse than no gate**, because its silence reads as a pass.

The same rule applies one level down, to prose matching: an entry written `el cron borra…` and quoted in a doc as `El cron borra…` **is** being read. Reporting it as an orphan claims nobody reads it, which is a different and wrong claim. Whether it was copied verbatim is check 1's question, and a human one.

## Normalization before comparing
Before flagging any string mismatch (checks 1, 2, 6, 7): strip surrounding YAML quoting, collapse runs of whitespace, normalize typographic quotes/dashes to ASCII, and **unescape markdown table syntax — `\|` is a literal `|`**. A registry gate `data?.length === 0 || !selectedId` appears in a doc's table as `data?.length === 0 \|\| !selectedId`; comparing raw reports it as absent from every doc and sends you hunting an orphan fact that was never orphaned. The audit's own tooling is a source of false positives — when a datum looks missing from a doc that obviously should cite it, check the escaping before writing the finding. A registry entry authored as `"Botón 'Reenviar…'"` and prose reading `Botón "Reenviar…"` is a **quoting artifact, not a finding** — the fix is to re-author that registry entry as a single-quoted YAML scalar, not to edit the prose. Report those separately as `POLISH: quoting`, never as `CONTRADICTION`.

## Severity taxonomy
- **CONTRADICTION** — two sources assert different facts. Must fix before approval.
- **DRIFT** — structural gap: orphan fact, dangling ref, uncovered checklist item. Fix soon.
- **POLISH** — cosmetic/wording inconsistency; no factual conflict. Optional.

## Output format

**Correspondence matrix** — `audit.py` prints it under `## Correspondence matrix`: rows = registry datums cited verbatim in at least one doc, columns = docs, cell = how many times, `·` = never. **Do not rebuild it.** Report its count line, and then only the rows check 1 changed — cell = ✅ (counted) / ⚠️ (cited in other words) / ✗ (cited with another value) / — (n/a):

| Dato | 01 | 02 | 03 | Match |
|---|---|---|---|---|
| limits.cloudflare (100s/524) | ✅ | — | ⚠️ `100 seconds` | ⚠️ |

A set where check 1 changed nothing reports the count line and no table. `--no-matrix` leaves the table out of a re-run after a fix; `--json` carries it as `matrix`.

**Findings** — most-severe first, one line each:
`doc0X §sec: <TAG>: <what mismatches>. <fix>.`

End with a one-line verdict: `N contradictions, M drift, K polish` or `clean — all shared data corresponds`.

## Deep pass (`--deep`)
After the inline checks, spawn a cold reviewer subagent with ONLY: the doc files + this protocol + `_facts.yml`. It must not see the authoring conversation. Ask it for findings in the same format. Merge with inline findings, dedupe by (doc, section, claim), present once. Rationale: inline validates against rules; the cold reader catches assumptions the author normalized away.
