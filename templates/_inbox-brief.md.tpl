# BRIEF: {{task}} · {{tier}}

> **Spec dir:** `{{spec_dir}}`
> **Profile:** `{{profile_path}}`
> **Checklist:** `{{checklist_path}}`

## Context & Boundaries

You are a read-only worker reviewing this feature specification.
By contract (rule 1), you edit nothing in the set: do NOT edit `_facts.yml`, `_log.md`, or any file in `docs/`.
Your runner is `{{runner}}`. Follow ONLY the paragraph for your runner; ignore the other.

**Runner `claude` (you cannot write files):** return EVERY finding as text in your reply: no
summary, no `overflow` line, no `delivery:` line. Your reply is the delivery and the main
session merges it whole.

**Runner `orca` or `agy` (the delivery is a file):** the full delivery is
`{{delivery_path}}`, with a `SUMMARY` block at its top and EVERY finding below it. As `orca` you
write that file yourself (the only file you write). As `agy` you write nothing: put the same
SUMMARY + findings in your reply and the main session redirects the CLI's JSON to that path.

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

Per `references/parallel.md` §Return contract, by runner:

- **`claude`:** your whole reply is the delivery: every finding, as text, in the output shape. No summary, no overflow line — a pointer to a file you cannot write loses the findings.
- **`orca` / `agy`:** the delivery holds EVERY finding, none dropped or merged by you, under a `SUMMARY` block of at most 40 lines — counts by type, ids plus one line of the most severe findings, `delivery: {{delivery_path}}`, and `overflow: <N> more in the delivery` if the summary lists fewer than all. As `orca`, return only the SUMMARY as your message; as `agy`, the full reply is the delivery.

A finding without a `scenario:` will be dropped at merge.
If you find no gaps for the scope you reviewed, write:
`clean for {{checklist_file}}`
and name the kinds/scenarios covered.
