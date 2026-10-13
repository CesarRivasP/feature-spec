# BRIEF: {{task}} · {{tier}}

> **Spec dir:** `{{spec_dir}}`
> **Profile:** `{{profile_path}}`
> **Checklist:** `{{checklist_path}}`

## Context & Boundaries

You are a read-only worker reviewing this feature specification.
By contract (rule 1), you edit nothing in the set: do NOT edit `_facts.yml`, `_log.md`, or any file in `docs/`.
Return your findings as an inbox delivery file at:
`{{delivery_path}}`

## Registry Spans

The following table of contents and line spans from `python3 scripts/audit.py {{spec_dir}} --index` define the relevant registry sections for your task:

```
{{registry_spans}}
```

## Output Shape

Format your findings exactly as required by `references/parallel.md` §Output shape:

```
<FUNCTIONAL|SECURITY> · <changes[] id | registry path> · <one-line gap>
  scenario: <inputs/state> → <wrong behavior>
  fix: <registry entry to add or change> | accepted risk: <why>
```

A finding without a `scenario:` will be dropped at merge.
If you find no gaps for the scope you reviewed, write:
`clean for {{checklist_file}}`
and name the kinds/scenarios covered.
