---
name: audit
tags: [audit]
runs: 1
max_turns: 25
timeout_seconds: 600
allowed_tools: [Skill, Bash, Read, Grep, Glob]
---
Audit the feature spec in `docs/features/open-items/` with the feature-spec skill. Tell me what is still open in that set and where in the docs each open item is discussed. Do not edit anything.
