# Implementación + Pruebas E2E — {{title}}

> Complementa a `01-master-plan.md`. Pasos de código (archivo por archivo) + plan de pruebas end-to-end.

- **Fecha:** {{dates.drafted}}
- **Baseline de tests:** {{tests_baseline}}

> Datos compartidos vienen de `_facts.yml`. Cross-refs a `01-master-plan.md §N` deben resolver a secciones reales.
> **Este doc es ejecutable, no descriptivo.** Su lector es quien construye — posiblemente un modelo más chico sin contexto de cómo se escribió. Ver `references/implementable.md`.

---

## Changelog
<!-- mirror doc 01 changelog entries that affect implementation -->

---

## Parte A — Plan de implementación
<!--
One "Fase N" per file changed, in dependency order.
Mark phases a program cannot execute: [MANUAL] / [OWNER EXTERNO].
Each phase carries all six blocks below — a missing one is a question the builder has to ask.
-->

### Fase 1 — {{component}}
**Archivo:** `path/to/file` <!-- exact; `(nuevo)` if new. No "o el componente correspondiente". -->
**Ancla:** `path/to/file:NN` — `<quoted existing line the change attaches to>` <!-- or "archivo nuevo" -->

**Qué cambia:** <!-- one paragraph -->

**Código:**
```
// paste-ready, real imports, repo's own style, this repo's language.
// Mark fragments explicitly: // … resto sin cambios
```

**Contratos que implementa:** `_facts.yml limits.X`, `contracts.Y` <!-- lets the builder self-check nothing was dropped -->

**Verificación fase 1:** `<_profile.yml commands.* + this phase's target>` → `<expected output>` <!-- never "verificar que funciona", never a command invented here -->

---

## Parte B — Plan de pruebas

### B.0 — Preámbulo de mocks
<!-- Copy this stack's mock/setup block verbatim from a REAL test in this repo; say which file it came from. -->

### B.1 — Unitarias
<!-- checklist; each bullet names its target test file path + the exact query/assertion -->
### B.2 — Integración / contrato
<!-- assert the JSON contracts from _facts.yml contracts.* -->

**Baseline:** `{{profile.commands.tests}}` → `{{tests_baseline}}` <!-- value must contain commands.tests_expect -->

---

## Parte C — Pruebas E2E (manual)
<!-- C.1 happy path, C.2 continuity, C.3 error, C.4 timeout, C.5+ edge cases -->

---

## Criterios de aceptación (Definition of Done)
<!-- MUST match acceptance[] in _facts.yml item-for-item -->
