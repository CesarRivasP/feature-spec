# Implementación — {{title}}

> Complementa a `01-master-plan.md`. Pasos de código, archivo por archivo. El plan de pruebas, las E2E y la Definition of Done viven en `02e-tests-and-e2e.md`.
> Escrito por `implement` (stage 2) — después de que `review` corrió, sus hallazgos quedaron dispositionados, y el usuario confirmó con el flip a `status: reviewed`. No lo escribe `new`.

- **Fecha:** {{dates.drafted}}
- **Baseline de tests:** {{tests_baseline}}

> Datos compartidos vienen de `_facts.yml`. Cross-refs a `01-master-plan.md §N` deben resolver a secciones reales.
> **Este doc es ejecutable, no descriptivo.** Su lector es quien construye — posiblemente un modelo más chico sin contexto de cómo se escribió. Ver `references/implementable.md`.
> El preámbulo de este archivo gobierna también a `02e-tests-and-e2e.md`: convención de logs, notación de comandos, reglas de base.

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

**Verificación fase 1:** `<_profile.yml commands.* + this phase's target>` → `<expected output>` <!-- never "verificar que funciona", never a command invented here. Point at the `02e` section that says how this phase is known to work. -->

---

## Continúa en `02e-tests-and-e2e.md`
<!-- Parte B (unitarias / integración), Parte C (E2E manual) y la Definition of Done. A doc that ends without this line reads as truncated. -->
