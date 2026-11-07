---
type: regex
pattern: 'feature:\s*"?export-csv"?'
match: contains
target: {source: file, path: docs/features/export-csv/_facts.yml}
---
The registry exists with the right slug.
