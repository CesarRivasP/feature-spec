---
type: regex
pattern: '^## R1\b'
flags: m
match: contains
target: {source: file, path: docs/features/export-csv/_log.md}
---
_log.md starts with the R1 entry.
