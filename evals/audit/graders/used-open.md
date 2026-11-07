---
type: tool_used
tool: Bash
input_match: '"command"\s*:\s*"(?:[^"\\]|\\.)*audit\.py(?:[^"\\]|\\.)*--open'
min: 1
---
The agent asked the script for the open items (--open) instead of reading the log and registry whole.
