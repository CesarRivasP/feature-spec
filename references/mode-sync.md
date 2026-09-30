# `sync <slug>` — propagate registry changes
When `_facts.yml` changes, find every doc occurrence of each changed datum and update it (or, if `--dry`, report the drift without editing). This is the write-side counterpart of `audit`.

**Only over docs whose stage the set has reached.** A datum with no occurrence in doc 02 because doc 02 does not exist yet is not drift, and reporting it as such under `--dry` buries the real findings. Resolve the stage exactly as `audit` does (`references/audit-protocol.md` §Stage gating), and say which docs were out of scope rather than staying silent about them.

**`sync <slug> --decision <key>`** lists the sections a `decisions.*` entry's `cited_in:` names, and does **not** edit them. Changing a decision is almost never a string replacement — the prose that rests on it has to be rewritten by someone who knows what replaced it. Reporting and letting a human rewrite is the correct behavior, not a limitation.

**`sync` moves data, not shape.** It finds a value and replaces it. A plan that *changed shape* — an entry that left `changes[]`, a decision that was cancelled — has no value to replace: it has prose hanging off a premise that is now false, and nothing follows that arrow. That is `implement`'s problem for doc 02's phases and `references/gap-sweep.md` §Trimming scope's for `acceptance[]` and `decisions.*`. Running `sync` and calling the set consistent is how a cancelled decision left 14 stale promises across a set that audited clean.

---

Every mode starts by reading `_log.md` from disk and opens its own entry before editing (`SKILL.md` §Modes, `references/handoff.md`). The rules every mode that writes is held to: `references/rules.md`.
