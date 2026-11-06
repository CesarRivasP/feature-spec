# DELIVERY: {{task}} · {{worker_agent}}/{{worker_model}}

**Worker:** {{worker_agent}} · {{worker_model}} (orca)
**Read:** {{read_line}}

## SUMMARY

<!-- At most 40 lines; the full findings are below, none dropped. -->
counts: FUNCTIONAL {{n_functional}} · SECURITY {{n_security}}
most severe:
{{summary_lines}}
delivery: {{delivery_path}}
overflow: {{n_overflow}} more in the delivery
<!-- omit the overflow line when the summary lists every finding -->

## Findings

{{findings}}
