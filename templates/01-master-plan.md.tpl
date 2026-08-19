# Master Plan — {{title}}

> **Objetivo:** {{one-line goal — the problem eliminated / capability added}}.

- **Estado:** {{status}}
- **Fecha:** {{dates.drafted}}
- **Owner técnico:** {{owners.technical}}
- **Owner externo:** {{owners.external}}
- **Documentos relacionados:**
  - `02-implementation-and-e2e.md` — plan de implementación + pruebas E2E
  - `03-stakeholder-requirements.md` — requerimientos para {{owners.external}}

> Todo dato compartido de este doc proviene de `_facts.yml`; todo comando, de `_profile.yml`. No editar números/nombres/comandos aquí a mano — cambiarlos en el registry (o el profile) y correr `sync`.

---

## Changelog
<!-- one entry per _facts.yml dates.revisions[]; newest first -->

### {{revision.date}} — {{revision.tag}}: {{revision.note}}
<!-- what changed in this revision, one line -->

---

## 1. Problema
<!-- Current state, why it fails. Cite limits.* from registry (timeouts/errors) verbatim. -->

## 2. Solución elegida
<!-- The chosen pattern + a why-not for the main alternative. -->

## 3. Arquitectura
### 3.1 Componentes que cambian
<!-- table: component | change -->
### 3.2 Estrategia de rollout
### 3.3 Coordinación crítica (si aplica)

## 4. Especificación de datos
<!-- The HTTP/interface contracts. Each JSON block MUST match contracts.* in _facts.yml. -->

## 5. Seguridad

## 6. Costo y escalabilidad

## 7. Checklist maestro
<!-- Grouped by area. Each item should have a counterpart in doc 02/03. -->

## 8. Riesgos
<!-- table: riesgo | mitigación -->
