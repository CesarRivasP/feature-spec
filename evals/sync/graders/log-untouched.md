---
type: regex
pattern: 'The timeout was 30000 ms when this round closed'
match: contains
target: {source: file, path: docs/features/sync-values/_log.md}
---
A past log entry is history: sync never rewrites it.
