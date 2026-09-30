---
name: feature-spec
description: Create, audit, and keep-in-sync multi-doc feature specs from a single source of truth (a facts registry), so no two docs ever contradict. Use when the user wants to write a feature spec / design doc set, audit spec docs for consistency, or validate that every shared datum matches across documents.
---

# Feature Spec — spec doc sets that never contradict

A feature spec is not one file — it's a **set** (master plan + implementation + tests/E2E + stakeholder requirements) that shares many of the same facts (dates, timeouts, contracts, endpoints, bot lists, backoff numbers…). Contradictions creep in because each fact is **copied** into 3 places and drifts.

**Core idea: one source of truth.** Every shared datum lives once in `_facts.yml`. Docs reference it. Auditing stops being "read 3 docs and compare prose" and becomes "check no doc contradicts `_facts.yml`" — mechanical and near-deterministic.

Directory layout for a feature named `<slug>`:

```
docs/features/<slug>/
  _facts.yml          # single source of truth — the ONLY place shared data is authored
  _log.md             # append-only handoff log — who edited what, against which version
  01-master-plan.md   # stage 1 — `new`.       the decision: is this worth building?
  02-implementation.md           # stage 2 — `implement`. the build, once the answer is yes
  02e-tests-and-e2e.md           # stage 2 — `implement`. how each phase is known to work, and the Definition of Done
  03-stakeholder-requirements.md # stage 2 — `implement`.
```

**Docs 02, 02e and 03 are not written by `new`.** They are ~75% of the set's prose and the
only part that must be rewritten whole every time the plan moves — and a plan gets
bounced two, three, four times before anyone commits to it. `new` writes the registry
and doc 01, which is everything you need to *decide*; `implement` writes the rest once
the decision is made. Which doc belongs to which stage is `docs[].stage` in the
registry, and audit reads it before running a single check.

(If the project keeps specs flat like `docs/features/<slug>-01-...md`, honor that — put `_facts.yml` as `docs/features/<slug>/_facts.yml` or `<slug>-_facts.yml`. Match the repo's existing convention; do not impose a new one.)

## Modes

`new` → (bounce the plan with the user) → `review` → user confirms (`status: reviewed`)
→ `implement` → `verify` → `shipped`. `audit` and `sync` run at any point; `handoff`
runs whenever the set changes hands.

**Every mode starts by reading `_log.md` from disk** (`references/handoff.md`). It records which agent last touched the set, which file versions they read, and what they decided about the previous round's findings. **It outranks your context window** — if the two disagree, your context is stale and the files must be re-read at the versions the log names. **Every mode that edits opens its entry BEFORE editing and completes it after** — a stub naming the agent, the versions read, and what it is about to do; the findings, edits and dispositions filled in when the round ends. Not the other way round: a round that dies halfway then leaves a trace instead of silence. *Real case:* a delegated subagent wrote all four documents and hit a session limit before writing its entry — from outside it looked like it had produced nothing, and the next round spent its time reconstructing work that was already on disk. A round that finishes completes its own entry; a round that does not is exactly the one that needed the stub. **Then read the stub back** (`tail -n 8 _log.md`) before the first edit: a stub whose command failed in silence leaves exactly the silence it exists to prevent. *Real case:* a stub command died on `unmatched "`, its author read the next line of output instead, and a whole round ran with nothing on disk.

**Each mode is one file, read before running it.** The table says what the mode does and what it refuses; the file says how. Nothing in this table is enough to run a mode.

| mode | does | refuses / never | file |
|---|---|---|---|
| `new <slug>` | resolves the profile (walk up, nearest wins), detects siblings, fills `_facts.yml` with every claim carrying a `basis:`, runs the gap sweep, writes doc 01 only, scaffolds `_log.md` at step 2, runs `audit`. `--with-build` chains `implement` for a decision already made | never writes docs 02/02e/03; never invents a command, an owner or a value — asks in one batch (`references/intake.md`) | `references/mode-new.md` |
| `review <slug>` | gap sweep: base + one layer per `_profile.yml gap_sweep_layers:`. Findings `FUNCTIONAL` / `SECURITY`, each with a failure scenario. Asks whether it is worth building at this scale, with the number | no scenario, no finding; a stack with no layer is a stated blind spot, not a pass | `references/mode-review.md`, `references/parallel.md` |
| `implement <slug>` | writes `02-implementation.md`, `02e-tests-and-e2e.md`, `03-stakeholder-requirements.md`; stub in `_log.md` before generating; covers every *pending downstream coverage* item; stamps `regenerated_on:`; runs `audit` | **refuses** unless `review` ran with every finding dispositioned, the user flipped `status: reviewed`, and every `changes[]` entry has a `kind:` | `references/mode-implement.md` |
| `audit <slug>` | `--index` for the registry's line spans, `python3 scripts/audit.py docs/features/<slug>/`, then the judgment pass over `REQUIRES A HUMAN PASS` and the candidates. Emits the matrix rows it changed + findings `CONTRADICTION` / `DRIFT` / `POLISH`. `--deep` adds a cold reviewer | never edits unless told "fix"; the script never executes `evidence.cmd` | `references/mode-audit.md` |
| `verify <slug>` | reconciles the registry against a device run: confirmed → `measured` with `n:`/`spread:`/`conditions:`, refuted → `dead`; walks `depends_on` both ways; re-runs `review` if `changes[]` changed shape | aborts before the run if a precondition is missing (`aborted_no_conditions`); G1 blocks `shipped` on an asserted root cause | `references/mode-verify.md` |
| `sync <slug>` | propagates changed registry values into the docs in scope (`--dry` reports); `--decision <key>` lists `cited_in:` sections | moves data, never shape — a cancelled decision or a moved `changes[]` entry is `implement`'s | `references/mode-sync.md` |
| `handoff <slug> [round]` | appends the round entry: agent, `Read:` with line count + blob per file (`audit.py --read-line`), `Log read through:`, one disposition per prior finding | a rejection without evidence; a `reviewed` flip inferred from conversation | `references/mode-handoff.md` |
| `view <slug>` | `python3 scripts/render.py docs/features/<slug>/` → one self-contained `view.html` | never edited, never a source | `references/mode-view.md` |

## Rules that keep it honest

The full list is `references/rules.md` — every mode that writes is held to it, and it moved out of this file verbatim, not summarized. The ones that decide most rounds:

- **Verbatim copy guarantees consistency with the registry, including any error IN it.** Harden the input: every claim declares `basis:`, measured data is run not copied, `changes` vs `related_docs` are disjoint, contracts live in `contracts.*` not prose.
- **Ask, never invent.** Unknowns travel as `null`, `[MANUAL]` or `basis: asserted` + `falsified_by:`. An unmarked unknown is the defect.
- **The log outranks the context window.** Read it first, re-read at the versions it names, open your entry before editing.
- **`_facts.yml` is edited as text, never round-tripped through a YAML dumper.** Exact string replacement with `assert count == 1`; `safe_load` to read. A vault-ingested registry may be a two-document stream: `safe_load_all()`, last document.
- **Registry is authoritative; the profile says how this repo finds out.** A command belongs to the profile, its output to the registry.
- **A clean audit does not mean the registry is true.** `verify` is the gate; shipping with a cause still asserted is allowed once, in writing, with an expiry (`defects[].accepted`).
- **Wrong entries are retracted or corrected, never deleted; an id is never recycled.**
- **Prose is written once, against a plan that stopped moving.** Docs 02/02e/03 exist only after `review` and the user's confirmation.

## References
- `references/parallel.md` — splitting a mode across subagents by tier (`strong` / `mid` / `cheap`), the runners (`claude`, `agy`, `inline`), and the rules that keep one writer per file. `agents/spec-*.md` — the three read-only tier definitions to copy into `.claude/agents/`.
- `references/mode-<name>.md` — one per mode, the full procedure; `references/rules.md` — the rules every writing mode is held to.
- `references/doc-pattern.md` — the 4-doc pattern, section skeletons, naming, cross-ref rules.
- `references/audit-protocol.md` — the checks that need a human pass, the index of the ones the script settles, severity taxonomy, matrix format. `references/audit-checks-script.md` — the full text of every `[script]` check, read only when one of its findings needs explaining.
- `references/gap-sweep.md` — the `review` mode checklist: does this spec add functional/security gaps? Stack layers alongside it: `gap-sweep-web-baas.md`, `gap-sweep-android-native.md`, `gap-sweep-mobile-tv.md`, `gap-sweep-payments-onprem.md`, `gap-sweep-web-3d-client.md`.
- `references/intake.md` — the questions to ask before writing anything, batched, with what may never be guessed.
- `references/handoff.md` — the append-only `_log.md`, for sets passed between agents: entry format, dispositions, and why the log beats the context window.
- `references/evidence.md` — the `basis:` / `evidence:` contract, the `verify` mode, and the gates that keep an asserted root cause from shipping.
- `references/implementable.md` — how to write doc 02 so a context-free executor can build it.
- `references/render.md` — the `view` mode: what the HTML render reads, the invariants it holds, and the gates it surfaces.
- `scripts/render.py` — the renderer itself. Deterministic and standalone: no model writes the HTML, so the view cannot drift from the files it renders.
- `scripts/audit.py` — the mechanized half of the audit protocol. Shares its registry walk and basis gates with `render.py` by importing them, so the two cannot drift: a check implemented twice is the defect this skill exists to prevent.
- `scripts/triage.py` — optional ranking over the candidates from checks 3, 4, 8 and 13, sorted into `keep` / `uncertain` / `suppressed`. Imports `audit.py` for the candidates themselves, so it can only reorder what the offline run already found; with no SDK or key it prints the same list, unranked.
- `tests/` — one fixture per mechanized check, each reproducing the real failure that motivated it, plus the false positives that must stay unreported. `python3 tests/test_audit.py`. `python3 tests/test_render.py` covers `render.py`'s own security boundary: a URL scheme allowlist on rendered links/images, and confinement on every registry path it reads content from. `python3 tests/test_triage.py` covers `triage.py`'s offline half — the one that has to hold when nothing is installed: that `collect()` reproduces `audit.py`'s candidate list exactly, in both directions, so it can only reorder what the offline run found; that the fallback prints every candidate rather than filtering one; and that 0, 1 and 2 stay distinguishable for a caller. Ranking itself is not exercised — a test that needs a key is a test that does not run.
- `templates/` — `_facts.yml.tpl`, `_log.md.tpl`, and one `.tpl` per doc.
- `profiles/` — `_profile.yml.tpl` (the contract) plus starter profiles per stack. Copy one into the repo as its `_profile.yml`; **never fill one in place** — a real `app_id` or agent name written into a starter leaks into every other project using this skill.
  - The starters and the `gap-sweep-<layer>.md` files are **independent and disposable**. A repo needs only the ones matching its stacks; delete the rest, nothing else references them. Adding one for a new stack is ~20 lines (profile) and ~40 (layer), and is the normal way this skill grows.