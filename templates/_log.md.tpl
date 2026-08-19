# Handoff log — {{feature}}

Append-only. One `##` block per round, newest at the BOTTOM. Never edit or delete
a previous entry — a rejected finding with its evidence attached is what stops the
next round re-deriving it.

**Read this file from disk before anything else. It outranks your context window.**
If your context disagrees with the log, your context is stale: re-read the files
the last entry names, at the versions it names.

Hashes: `git hash-object <file>` (no commit or staging needed, works on
gitignored files) — first 7 chars, plus `wc -l`. Both. Full contract and the
disposition rules in `references/handoff.md`.

---

## R1 · YYYY-MM-DD · <model or tool identity> · author
**Read:** <file> (<n> lines, blob <sha7>) · <file> (<n> lines, blob <sha7>)
**Log read through:** — (first entry)
**Dispositions:** — (nothing prior)
**Edits:** <file + section>, <file + section>
**Still open:** <what is `basis: asserted`, what it blocks, what would settle it>

<!--
## R2 · YYYY-MM-DD · <model> (via: transcribed by <who>) · review
**Source:** pasted excerpt — <what was pasted> | full file
**Read:** <file> (<n> lines, blob <sha7>)   | [as pasted — no hash available]
**Log read through:** R1
**Findings:**
- R2-F1 `<doc §sec>: <what is wrong>` — <concrete failure scenario>
- R2-F2 `<doc §sec>: <what is wrong>` — <concrete failure scenario>
**Edits:** none (review changes nothing)
**Still open:** <carried forward>

## R3 · YYYY-MM-DD · <model> · validate
**Read:** <every file re-opened, with lines + blob>
**Log read through:** R2
**Dispositions:**
- R2-F1 → **confirmed**. <what changed in the registry>
- R2-F2 → **rejected**. <the command and its output, or the observation, that killed it>
          Kept as R2-F2-dead.
- R2-F3 → **deferred**. <what would settle it, and what it blocks>
**Edits:** <files + sections>
**Still open:** <what remains, and which gate it holds>
-->
