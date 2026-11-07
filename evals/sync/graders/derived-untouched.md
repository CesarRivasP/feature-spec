---
type: regex
pattern: 'Handler timeout: 30000 ms'
match: contains
target: {source: file, path: docs/features/sync-values/release-notes.md}
---
A role: derived doc (release notes) is regenerated whole, never patched by sync.
