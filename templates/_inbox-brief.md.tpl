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

The following table of contents and line spans from `python3 scripts/audit.py {{spec_dir}} --index` define the relevant registry sections for your task (or, for a handful of entries, their exact text from `--get KEY ...`):

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

## Return Contract

Per `references/parallel.md` §Return contract: the delivery file holds EVERY finding, none dropped or merged by you. Put a `SUMMARY` block at its top, and return only that summary as your message: at most 40 lines — counts by type, ids plus one line of the most severe findings, `delivery: {{delivery_path}}`, and `overflow: <N> more in the delivery` if the summary lists fewer than all.

A finding without a `scenario:` will be dropped at merge.
If you find no gaps for the scope you reviewed, write:
`clean for {{checklist_file}}`
and name the kinds/scenarios covered.
