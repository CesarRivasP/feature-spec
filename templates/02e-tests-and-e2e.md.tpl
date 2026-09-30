# Pruebas + E2E — {{title}}

> Complementa a `02-implementation.md`: cómo se sabe que cada fase funciona. Parte B (unitarias / integración), Parte C (E2E manual) y la Definition of Done.
> **El preámbulo de `02-implementation.md` gobierna este archivo también** — convención de logs, notación de comandos, reglas de base. No se duplica aquí.
> Escrito por `implement` (stage 2), junto con doc 02. No lo escribe `new`.

- **Fecha:** {{dates.drafted}}
- **Baseline de tests:** {{tests_baseline}}

> Datos compartidos vienen de `_facts.yml`. Cross-refs a fases van con prefijo: `` `02` Fase 3 ``, nunca `Fase 3` a secas.
> **Este doc es ejecutable, no descriptivo.** Cada bullet nombra su archivo de test y su assert exacto. Ver `references/implementable.md` §Tests.

---

## Changelog
<!-- same tag+date spine as 01 and 02; only the entries that touch tests or acceptance -->

---

## Parte B — Plan de pruebas

### B.0 — Preámbulo de mocks
<!-- Copy this stack's mock/setup block verbatim from a REAL test in this repo; say which file it came from. -->

### B.1 — Unitarias
<!-- checklist; each bullet names its target test file path + the exact query/assertion. Parity/negation rows carry a `Falla si:` line. -->
### B.2 — Integración / contrato
<!-- assert the JSON contracts from _facts.yml contracts.* -->

**Baseline:** `{{profile.commands.tests}}` → `{{tests_baseline}}` <!-- value must contain commands.tests_expect -->

---

## Parte C — Pruebas E2E (manual)
<!-- C.1 happy path, C.2 continuity, C.3 error, C.4 timeout, C.5+ edge cases. Each step names the device/build it runs on (intake set C). -->

---

## Criterios de aceptación (Definition of Done)
<!-- MUST match acceptance[] in _facts.yml item-for-item, criteria with `status: retired` left out (audit check 6) -->
