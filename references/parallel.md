# Parallel — splitting a mode across subagents by tier

A mode that is several independent reads, each answered from the registry, does not have
to run them one after another. `review` is the first: the base sweep and every stack layer
read the same registry, answer different questions, and never read each other's output.

This is **opt-in per repo** (`_profile.yml parallel:`). With no `parallel:` key, or on a
harness with no way to start a subagent, every mode runs serially exactly as before, and
the log entry says it did.

## The unit is a tier, not a model

Work is sorted by what it demands, and each kind goes to a tier:

| kind | what it asks | tier |
|---|---|---|
| **judgment** | decide something no file states: what breaks, what order, where to anchor | `strong` |
| **derivation** | read the repo or registry and produce something checkable | `mid` |
| **transcription** | copy from the registry into a shape | `cheap` |

The profile maps each tier to whatever the runner can start. The skill never names a model;
a profile that does not age with every release is the point.

| task | kind | tier |
|---|---|---|
| orchestrator — stub, brief, merge, log | judgment | runs in the main session |
| `review` base sweep (`gap-sweep.md`) + the scale question | judgment | `strong` |
| `review` one stack layer (`gap-sweep-<layer>.md`) | bounded judgment | `mid` |
| `audit --deep` cold reader | judgment | `deep_review`, a different model from the author on purpose |
| disposition of findings (`validate`) | judgment | main session, never delegated — `references/handoff.md` §What this does not fix |

`implement` is not parallel yet. When it is, `02` and its halves are `strong`, `02e` Parte B
is `mid`, `02e` Parte C + DoD and `03` are `cheap`: the phases are judgment against a real
tree, the test plan is derivation from it, and the rest is transcription from `acceptance[]`
and `contracts.*` that `audit.py` checks item by item.

## What it buys, measured

One real set, `review` with two layers (`web-baas`, `payments-onprem`), both ways on
2026-09-30, `n: 1`:

| | wall clock | tokens | findings | only this run found |
|---|---|---|---|---|
| parallel — base `strong` (opus), 2 layers `mid` (sonnet) | **101 s** | 217k | 32 raw, ~24 after dedupe | ~4 — timeouts per hop, poller pacing, a separate listener for the public path, a persisted release timer |
| serial — one `strong` (opus) reading all three files | 158 s | **97k** | 19, already merged | ~9 — multi-row trigger, amount precision, the physical dispatch gate, untrusted payer text rendered to an operator, `TRUNCATE` around the append-only rule |

So: **~36% less waiting, ~2.2x the tokens, and different coverage, not more.** Each subagent
re-reads the registry and its docs, which is where the tokens go. The serial reader, holding
all three checklists at once, found the cross-cutting gaps; the narrow layer readers found the
infrastructure ones. The union beat either. One run on one set is `n: 1` — the rule this skill
holds every measurement to applies here too: read it as a direction, not a constant.

That is why it stays opt-in. Turn it on when waiting is the cost that matters; leave it off
when tokens are.

## Rules

1. **One writer per file.** A subagent writes nothing. It returns its output; the main
   session writes every file. `_facts.yml` and `_log.md` are never touched by a subagent.
2. **A subagent does not fix the registry.** A gap it finds — a missing rate limit, an
   ambiguous criterion — comes back as a finding. Two subagents each "fixing" it is two truths.
3. **The stub names every subagent before any is started** — its tier, the model the runner
   resolved it to, and what it is asked for. A subagent that dies leaves a named hole instead
   of silence; that is the real case behind the stub rule (`references/handoff.md`).
4. **The brief comes from disk, never from the conversation.** It is all the subagent knows.
   It holds: the spec dir path, the profile path, the checklist file it runs, the registry
   spans it needs (`audit.py <dir> --index`), and the output shape below. Nothing about how
   the set was written — that is exactly the bias a fresh reader exists to avoid.
5. **Merge, then gate.** The main session dedupes by (`changes[]` id or doc §, failure
   scenario), keeps the more specific scenario when two overlap, and tags each finding with
   the check file that raised it. For `implement`, `audit.py` is the merge gate.
6. **Escalate once.** A subagent whose output fails the gate — no scenario, a finding
   against an entry that does not exist, an audit finding in the doc it wrote — is re-run one
   tier up with the failure in its brief. If `strong` fails too, the problem is the registry
   or the plan, and it is reported as such.

## Output shape — every `review` subagent

```
<FUNCTIONAL|SECURITY> · <changes[] id | registry path> · <one-line gap>
  scenario: <inputs/state> → <wrong behavior>
  fix: <registry entry to add or change> | accepted risk: <why>
```

A line with no `scenario:` is dropped at merge, as the serial sweep drops it. A subagent that
finds nothing says `clean for <file>` and names the kinds it covered — the same rule as a
missing layer, one level down.

## Runners

`_profile.yml parallel.runner` names how a tier becomes a running subagent.

### `claude` — Claude Code, the default

Subagents through the session's own subagent tool: background, notified on completion, same
checkout, no second login. A tier is either a bare model (`opus`, `sonnet`, `haiku`, `fable`)
or the name of an agent definition. Effort is not a per-call parameter in Claude Code — it
comes from the definition's frontmatter — so the skill ships three, read-only on purpose:

```
agents/spec-strong.md   model: opus    effort: high
agents/spec-mid.md      model: sonnet  effort: medium
agents/spec-cheap.md    model: haiku   effort: low
```

Copy them to the repo's `.claude/agents/` (a session restart loads them). A tier naming an
agent that is not installed falls back to that agent's model at default effort, and the
log entry says so. `tools: Read, Grep, Glob` — no `Write`, no `Edit`, no `Bash`: rule 1 is
held by the permissions, not only by the brief.

### `agy` — Antigravity CLI

One process per subagent in print mode, started by the main session:

```bash
agy -p "<brief>" --model <tier model> --output-format json --print-timeout 900s
```

In AGY the effort is part of the model id — `gemini-3.8-flash-low`, `-medium`, `-high` —
so a tier is just an id. The subagent's answer is `response` in the JSON; `usage` goes in the
log entry. Measured 2026-09-30: `-low` 7 s and `-high` 13 s for a one-line prompt, and
**~13k input tokens per call** before the brief — the CLI's own system prompt. That floor is
why a subagent is not worth starting for a task smaller than a checklist file.

Not yet verified, and not assumed: whether print mode reads the checkout with no write
permission granted. Until it is, the `agy` runner passes the files the brief names inline.

### `inline` — no subagents

Every task runs in the main session, in order. The fallback for any runner that cannot start,
and the behaviour of a profile with no `parallel:` key.

## What the log records

The stub lists each subagent: `<task> → <tier> → <resolved model/agent> (<runner>)`. The
completed entry adds, per subagent, `returned | escalated to <tier> | failed`, and its token
count when the runner reports one. A round that fell back to `inline` says why.
