---
name: sync
tags: [sync]
runs: 1
max_turns: 25
timeout_seconds: 600
allowed_tools: [Skill, Bash, Read, Grep, Glob, Edit, Write]
---
I just changed some values in `docs/features/sync-values/_facts.yml` (the last sync left its snapshot in `_facts.synced.yml`). Propagate the changes into the spec docs of that set, following the feature-spec skill. Tell me what you changed and anything you left for me to decide.
