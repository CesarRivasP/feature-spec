# Doc Pattern — the 3-doc feature spec set

## Why three docs
Each serves a distinct reader; splitting keeps each focused and lets the audit check that they agree.

| Doc | Reader | Answers |
|---|---|---|
| `01-master-plan` | internal team + approver | What/why, architecture, data contracts, security, cost, risks, master checklist |
| `02-implementation-and-e2e` | the engineer building it | File-by-file steps, verification per phase, unit/integration/E2E tests, Definition of Done |
| `03-stakeholder-requirements` | the external owner (partner/other team) | Only what THEY must build/validate, the interface they receive, their checklist, joint test steps |

## Naming
- Folder per feature: `docs/features/<slug>/` with `_facts.yml` + `NN-role.md`.
- OR flat (if the repo does it): `docs/features/<slug>-NN-role.md` + `<slug>-_facts.yml`.
- `NN` is zero-padded order (01, 02, 03). `<slug>` is kebab-case, stable, shared across the set.
- A doc that outgrows itself keeps its number and gains a letter: `02b-<what-it-holds>.md`. The letter says
  "continuation of 02", not "new role" — see *Splitting an oversized doc*.
- Match the repo's existing convention — detect it, don't impose.

## Splitting an oversized doc

Doc 02 is the one that grows: every phase adds code blocks, oracles, and revert lists. Past **~600 lines**
(or once a reader can't hold the phase list in their head) it stops being executable — the executor
loads 900 lines to run one phase, and edits start landing in the wrong half.

**Split it. Do not summarize it.** Compression loses exactly the resolved paths and paste-ready blocks
that make doc 02 worth reading.

Rules for the split:

1. **Cut on a top-level boundary** (a `## Fase N` heading), never mid-phase. Aim for a roughly even
   line split; prefer the boundary that keeps the setup/instrumentation phase with the first phases
   that consume it.
2. **Keep reading order.** `02` holds the earlier phases, `02b` the later ones. Don't reorder sections
   into "harness vs playbooks" — the executor reads front to back.
3. **The preamble does not move and is not duplicated.** `02` keeps the mandatory preamble (tools,
   logging convention, ground rules); `02b` opens with a `>` block stating that the preamble of `02`
   governs it too, plus the same branch/version/test-baseline header lines.
4. **Cross-refs across the boundary carry the doc prefix.** Inside a file, `§3.5` means "this file".
   Crossing over is always written `` `02` §1.1 `` / `` `02b` §3.5 ``. Sweep both halves after the cut:
   `rg -n '§[0-9]' <files>` and qualify every ref that now points at the other file. An unqualified
   dangling `§` is a `CONTRADICTION` at audit time — cross-refs must resolve (audit check 4).
   - The prefix goes **before** the ref, and **on every element of a list**. `` `02` §1.5, `02` §2.6, §3.6 ``
     reads as three refs into `02`; if `§3.6` is local, it needs its own prefix. A prefix trailing the
     ref (`§3.5 de 02b`) is legible to a human and invisible to the sweep.
   - **Sweep the changelog tables too.** They quote section numbers constantly and nobody thinks to
     re-read them while moving sections, so they're where unqualified refs survive the split.
5. **`02` ends with a pointer section** naming what moved and where, so nobody concludes the doc was
   truncated.
6. **Register both in `_facts.yml docs[]`** with `role: implementation` and a `note:` saying which
   sections each holds. Downstream invariants that name a section (e.g. "the revert list of 02 §6.1")
   must be re-pointed at the half that now owns it — in `_facts.yml`, in doc 01, and in any project
   memory.
7. **Each half gets its own changelog table**, sharing the tag+date spine of the set. The split itself
   is a changelog entry stating that no technical content changed.

The same rules apply to any doc in the set; 02 is just the one that hits the threshold first.

## Section skeletons
See the `.tpl` files. Fixed top-level sections per doc make audit check #5 (checklist coverage) and #4 (cross-refs) tractable — keep the numbered headings stable.

## Heading language

The `.tpl` files carry the `es` rendering. `_profile.yml prose_language:` decides which one a repo generates; **the numbering and the order never change**, only the words. Audit navigates by number, so a set is auditable in either language — but must not mix them.

| es | en |
|---|---|
| `Parte A — Plan de implementación` | `Part A — Implementation plan` |
| `Parte B — Plan de pruebas` | `Part B — Test plan` |
| `Parte C — Pruebas E2E (manual)` | `Part C — E2E tests (manual)` |
| `Fase N — <component>` | `Phase N — <component>` |
| `Archivo:` / `Ancla:` / `Qué cambia:` | `File:` / `Anchor:` / `What changes:` |
| `Código:` / `Contratos que implementa:` | `Code:` / `Contracts implemented:` |
| `Verificación fase N:` | `Phase N verification:` |
| `Criterios de aceptación (Definition of Done)` | `Acceptance criteria (Definition of Done)` |
| `Componentes que cambian` | `Components that change` |
| `Riesgos` | `Risks` |
| `Checklist maestro` | `Master checklist` |

A set already written in one language does not get retranslated because the profile changed — that rewrites every cross-ref and every registry string for zero gain. The profile governs new sets.

## Cross-reference rules
- Reference sibling docs by filename + section: `` `02-implementation-and-e2e.md` Fase 3 `` or `01-master-plan.md §4.1`.
- When a doc intentionally differs from the naive expectation (e.g. a field present in the wire contract but absent from the client body because it's injected downstream), add an explicit `>` note explaining it AND cross-ref the doc that owns the full contract. This turns a would-be CONTRADICTION into a documented, reconciled fact.

## Single-source-of-truth discipline
- Author every shared datum ONCE in `_facts.yml`; copy verbatim into prose.
- Prose may add narrative/context around a datum, but the datum's value and spelling come from the registry.
- Prose-only detail (rationale, examples) that appears in a single doc need not be in the registry — only cross-doc shared facts do.
- **A "componentes que cambian" table lists `changes[]` only** — components created/modified. Docs you merely reference belong in `related_docs[]` and must NOT appear in that table (audit check 7 treats a `related_doc` in a change table as a `CONTRADICTION`).
- **Every JSON payload and endpoint/URL in prose must trace to `contracts.*` / `endpoints.*`.** Don't leave a contract living only in prose — the mechanical audit can't see it (audit check 8).
- On change: edit `_facts.yml` → `feature-spec sync <slug>` → `feature-spec audit <slug>`.

## Markdown hygiene
- No stray `---` immediately under a heading with nothing between — put the section's first line (or an HTML comment) before the rule, so a bare heading isn't followed by a horizontal rule that reads as an empty section. Lint the generated docs before handing off.

## Changelog discipline
- The set shares a changelog spine (from `_facts.yml dates.revisions[]`). Each doc's changelog shows the entries relevant to it, newest first, using the SAME tag+date. Divergent tags/dates are a `CONTRADICTION`.
