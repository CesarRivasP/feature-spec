# `review <slug>` — gap sweep (is this safe to build?)
Runs `references/gap-sweep.md` against an existing spec set, **plus one `references/gap-sweep-<layer>.md` per entry in `_profile.yml gap_sweep_layers:`**. The base file holds the kinds of change every codebase has; the layers hold what a stack can break that no other stack can (exported components and Doze on Android, RLS and webhook replay on a BaaS, dead D-pad focus on TV). A stack with no layer yet is a **stated blind spot** in the output, not a clean pass — write the layer, it's ~40 lines. Complements `audit`, does not replace it:

| | asks | catches |
|---|---|---|
| `audit` | do the docs agree with the registry? | contradictions, drift, orphan facts |
| `review` | if built literally, what breaks? | unhandled rate limits, open endpoints, non-idempotent writes, PII, silent fallbacks, dead-end rescue flows |

Output: findings tagged `FUNCTIONAL` / `SECURITY`, each with a concrete failure scenario (inputs/state → wrong behavior). No scenario → not a finding. Fixes land in `_facts.yml` first, then `sync`; accepted risks land in doc 01 §Riesgos with a reason.

Run it after `new`, and again whenever `changes[]` grows.

It also asks the question that is not about safety at all: **is this worth building now, at this scale?** For every `changes[]` entry answering a limit of scale — the real measured value today, the threshold, and the distance between them. Orders of magnitude apart makes the entry a candidate for `kind: deferred` with its `reopens_when:`. *Real case:* the measurement showed the fix was ~200x ahead of the need; the set was cut in half and what remained was observability, not scalability. **The measurement is mandatory** — without the number it is one opinion against another.

**`review` is the gate between stage 1 and stage 2.** Its findings are dispositioned, the user confirms, `status:` flips to `reviewed`, and only then does `implement` write docs 02 and 03. Running it while doc 02 does not exist yet is the point, not a limitation: a finding that lands in `changes[]` here costs a registry edit, and the same finding after 02 exists costs the phase that was written around it.

---

Every mode starts by reading `_log.md` from disk and opens its own entry before editing (`SKILL.md` §Modes, `references/handoff.md`). The rules every mode that writes is held to: `references/rules.md`.
