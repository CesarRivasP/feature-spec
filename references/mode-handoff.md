# `handoff <slug> [round]` — hand the set to another agent, or take it from one
For sets worked by more than one model: one drafts, a second reviews it cold, the first dispositions the findings. Appends a round entry to `_log.md` recording the agent, the **line count and blob hash of every file read** (`python3 scripts/audit.py <dir> --read-line [FILE ...]` prints the whole `**Read:**` line; `git hash-object <file>` is the same by hand — no commit needed, works on gitignored specs), how far back it read the log, and one disposition per prior finding: `confirmed` / `rejected` / `deferred` / `superseded`.

A rejected finding states the evidence that killed it and **stays in the log** — same reasoning as a dead hypothesis in `verify`: a rejection with evidence stops the next round re-deriving it, and a rejection without evidence is exactly what a later round should reopen. An external model with no filesystem gets its entry transcribed, and the entry says so plus what it was actually shown — a finding raised against a pasted excerpt was made without the preamble and the surrounding phases.

**Delegating a defect to a set of its own** — *"this is a front of its own, let another agent build it a set"* — is a five-step checklist in `references/handoff.md` §Delegating, not a mode. It was used three times in five days, and the expensive half of it is judgment: which of the registry travels with the defect, and what gets re-derived. The vocabulary it needs (`owned_by:`, `moved_to:`, `kind: moved_out`) is in the registry; promote it to a mode if it starts being used often.

Format, disposition rules, and the round protocol: `references/handoff.md`.

---

Every mode starts by reading `_log.md` from disk and opens its own entry before editing (`SKILL.md` §Modes, `references/handoff.md`). The rules every mode that writes is held to: `references/rules.md`.
