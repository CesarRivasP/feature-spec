# _facts.yml — SINGLE SOURCE OF TRUTH for feature <slug>
# Every datum that appears in >1 doc lives HERE and is copied verbatim into prose.
# Companion file: docs/features/_profile.yml — one per REPO, not per feature.
#   registry = what is true about this feature. profile = how this repo finds out.
#   Every `cmd` below is rendered from `_profile.yml commands.*`, never hand-typed.
# Editing a value here → run `feature-spec sync <slug>` to propagate.
# Auditing → `feature-spec audit <slug>` checks docs against this file.
# Reconciling with reality → `feature-spec verify <slug>` checks THIS FILE against
#   observations. audit proves the docs agree with the registry; only verify
#   proves the registry is true.
#
# THE SET IS WRITTEN IN TWO STAGES. `new` writes this file + doc 01 — the decision
#   surface, the part that gets bounced until someone says yes. `implement` writes
#   docs 02 and 03 — the build, ~75% of the set's prose, authored ONCE against a
#   plan that stopped moving. Which doc belongs to which stage is `docs[].stage`
#   at the bottom of this file.

feature: <slug>
profile: <path to the _profile.yml this set was written against>   # resolved by the upward walk
title: <Human-readable feature title>
status: draft           # draft | reviewed | implementing | shipped | paused
                        # ORDERED: draft < reviewed < implementing < shipped.
                        # `paused` holds the last real stage it reached.
                        # The ordering is what gates docs[].stage below:
                        #   draft     - the decision is still open. Registry + doc 01.
                        #   reviewed  - `review` ran, its findings are dispositioned in
                        #               _log.md, and the user confirmed. `implement` may
                        #               now write docs 02 and 03. The flip to `reviewed`
                        #               IS the record of that confirmation.
                        #   implementing / shipped - code exists or has landed.
                        # `shipped` is GATED: refused while any root_cause /
                        # contributing defect is still `basis: asserted`.
                        # See references/evidence.md §Gates (G1).
owners:
  technical: <who>
  external: <who / stakeholder>       # e.g. API partner, other team, automation owner

tracking:
  issues: []            # e.g. [303]
  pr: null              # e.g. 305
  milestone: null       # e.g. v1.4.2
  branch: null
  shipped_in: null      # release tag once merged, e.g. hotfix/v1.4.1
  blocked_by: null      # external owner + their clock, if any

dates:
  drafted: YYYY-MM-DD
  revisions:
    - { tag: v2, date: YYYY-MM-DD, note: <what changed> }

# =====================================================================
# BASIS — every entry that CLAIMS SOMETHING ABOUT THE WORLD declares how
# it is known. Not optional. Full rules in references/evidence.md.
#
#   basis: measured   -> requires evidence: { how, cmd, date, value }
#   basis: asserted   -> requires falsified_by: <observation that kills it>
#   basis: decided    -> a choice, not a claim. No evidence needed.
#
# evidence.how: shell | git | device | log | provider-behavior
#   (cmd comes from _profile.yml commands.*)
#   shell  - a command. value = its output, verbatim.        <- commands.tests/lint/build
#   git    - repo/file state.                                <- commands.file_tracked/file_ignored
#   device - a NUMBERED manual procedure. value = observed.  <- commands.force_stop
#   log    - a log line. value = the decisive line, quoted.  <- commands.device_log
#   provider-behavior - what a third party ACTUALLY does. The strictest one:
#            `value` must be an observed HTTP response — status code and body —
#            never a description of the configuration. Real case: a claim about a
#            file-type filter was corrected TWICE, in opposite directions, first
#            understating the defence ("only validated client-side") and then
#            overstating it ("a tampered client cannot bypass it"). Both times the
#            error was reasoning about the provider's config instead of executing
#            the flow. A config is what you asked for; behavior is what you get.
#
# This is NOT only for numbers. Behavioral claims ("the framework focuses the
# first item") and file/git-state claims ("not committed yet") are claims too.
# They get basis: measured/how: device|git, or basis: asserted.
# There is no third option and no exemption for "obvious".
#
# A `cmd` that derives scope names ONE symbol — no regex alternation.
# `rg 'A|B'` fuses two result sets and misattributes members between them.
# =====================================================================
# example (cmd is _profile.yml commands.tests; value must contain tests_expect):
#   tests_baseline:
#     basis: measured
#     evidence: { how: shell, cmd: "<commands.tests>",
#                 date: 2026-08-03, value: "280/280 passing (28 files)" }

# --- decisions taken about this feature ---
# A decision is not a datum with a value to grep — it is a PREMISE that prose hangs
# off. `sync` propagates data; nothing follows a premise when it changes, so the
# prose keeps promising what was cancelled. Give each one a key and cite the key.
decisions: {}           # e.g. { scope_trimmed: { date: YYYY-MM-DD, basis: decided,
                        #          what: 'deferred the durable table; peak is 200x below
                        #                 the threshold that motivated it',
                        #          cited_in: ['01 §2.4', '02 Fase 5', '03 §3.1'] } }
                        #
                        # `cited_in:` lists the sections that REST on this decision.
                        # Changing the decision means walking that list — `sync` cannot,
                        # because it replaces values and a premise has no value to
                        # replace. Real case: a cancelled heartbeat left 14 places in
                        # prose still promising it, including a complete step in doc 03
                        # telling an operator to create a monitor that was already
                        # cancelled. Doc 03 is the one handed to a person to execute; an
                        # obsolete instruction there is not cosmetic drift, it is work
                        # done wrong.
                        # And the second-order case: one decision's death can orphan
                        # ANOTHER decision's justification. A table's deferral was
                        # justified with "for alerting we don't need it, the Crons
                        # monitor covers the absence". When the monitor was cancelled the
                        # table stayed deferred — but no longer for the written reason.

# --- domain facts (fill with the real shared numbers/names) ---
limits: {}              # e.g. { cloudflare: { timeout_s: 100, error: 524 } }

# Scope is TWO disjoint lists — do not mix them:
changes: []             # components CREATED or MODIFIED by this feature (bots, edge functions, modules).
                        #   ONLY these participate in scope-parity (audit check 7).
                        #
                        #   Every entry carries TWO orthogonal fields. The template used to
                        #   assume each change simply gets built; in practice three other
                        #   states exist, and a session that has to invent them invents them
                        #   differently each time — the exact drift this registry prevents.
                        #
                        #   kind: (lifecycle)  planned | deferred | moved_out | pending
                        #     planned    - will be built by this set. The default.
                        #     deferred   - written, decided NOT to apply now. REQUIRES
                        #                  `deferred_because:` (a decisions.* key) and
                        #                  `reopens_when:`. A deferral with no reopen
                        #                  condition is not deferred — it is abandoned
                        #                  with better wording.
                        #     moved_out  - left for another set or issue. REQUIRES `moved_to:`.
                        #     pending    - adopted from another set, not applied here yet.
                        #                  REQUIRES `transferred_from:`.
                        #   where: (location)  repo | external
                        #     repo       - `file:` is a path in this checkout. The default.
                        #     external   - the change is real but has no file here (a cron
                        #                  job, a dashboard setting, a provider config).
                        #                  Audit does not try to resolve `file:` on disk.
                        #
                        #   `implement` REFUSES to run while any entry has no `kind:` —
                        #   an unclassified change is an undecided one, and doc 02 would
                        #   be written against a scope nobody settled.
                        #   - { id: C1, file: src/x.ts, kind: planned, change: '...' }
                        #   - { id: C2, file: src/y.ts, kind: deferred, change: '...',
                        #       deferred_because: decisions.scope_trimmed,
                        #       reopens_when: 'daily peak passes ~200 distinct users. Today: 5' }
                        #   - { id: C6, file: src/z.ts, kind: moved_out, moved_to: 'issue #28 — 2026-08-28' }
                        #   - { id: C7, file: 'cron.job jobid 1', kind: planned, where: external }
                        #
                        #   A `file:` under `kind: planned, where: repo` that does not exist on
                        #   disk is only a finding once `status:` reaches `implementing` — before
                        #   that, a file this set is going to create legitimately isn't there yet.
related_docs: []        # docs/guides REFERENCED but NOT modified (e.g. manual-user-creation.md).
                        #   context pointers only — never scope-parity members.
                        #   A related_doc's STATE is a claim: "sin commitear" needs
                        #   basis: measured / how: git. NEVER copy it from a sibling spec.
                        #   - { file: x.md, tracked: false, basis: measured,
                        #       evidence: { how: git, cmd: "<commands.file_tracked> x.md",
                        #                   date: YYYY-MM-DD,
                        #                   value: "error: pathspec 'x.md' did not match any file(s)" } }

# --- defects / hypotheses under investigation ---
defects: []
  # - id: D3
  #   role: root_cause        # root_cause | contributing | symptom | cosmetic
  #   claim: 'row 0 never mounts because _initialRenderRegion clamps'
  #   basis: asserted         # asserted until a device/log run confirms it
  #   falsified_by: 'a log line proving row 0 DID mount while focus still died'
  #   log_line: '<TAG>.mount id=<uid> row=0' # emitter that produces it; null = must be built
  #   status: open            # open | fixed | dead
  #   # An entry that STAYS open needs to say why, or a cold reader — and audit —
  #   # reads it as unfinished work this set forgot about:
  #   outcome: null           # the answer this entry now has. Required once a
  #                           #   depends_on target dies or changes basis: the
  #                           #   question got answered elsewhere and nobody came
  #                           #   back. Staying `open` as an accepted risk is
  #                           #   valid; staying open with no `outcome:` is not.
  #   owned_by: null          # where the fix lives, if it is not this set. A defect
  #                           #   this set FOUND but another set FIXES stays `open`
  #                           #   on purpose — closing it would be a lie — but
  #                           #   without this field it reads as pending work here.
  #   note_ownership: null    # why it is still open in THIS set
  #
  #   # SHIPPING WITH THIS STILL ASSERTED, ON PURPOSE. Gate G1 refuses `shipped`
  #   # while a root_cause/contributing defect is `basis: asserted` — and that is
  #   # right, but there is a legitimate case it had no room for: the team knows
  #   # the cause is unproven, ships the trimmed scope anyway, and schedules the
  #   # measurement. Without a field for it, that decision goes into a log entry
  #   # or an agent's memory, and NEITHER is read by the audit, the next agent, or
  #   # the view. From outside, "we looked and chose to wait" is indistinguishable
  #   # from "nobody looked".
  #   #
  #   # This is a DEFERRAL WITH A DEADLINE, not an exemption. Same rule the
  #   # registry already applies to `changes[]`: a postponement with no reopen
  #   # condition is abandonment with better wording. All four fields required.
  #   accepted:
  #     by: <a person>        # never an agent. An agent cannot accept a risk on
  #                           #   its own behalf; the audit rejects a model id here.
  #     decided_on: YYYY-MM-DD
  #     until: YYYY-MM-DD     # the date the measurement is due. It EXPIRES: past
  #                           #   this, G1 refuses `shipped` again and names the
  #                           #   date. That expiry is the whole point — it is
  #                           #   what a memory or a log entry cannot do.
  #     because: 'ships the trimmed scope; the >1000-object run needs production
  #               volume that does not exist yet'
  #   # (never name a date field `on:` — YAML 1.1 reads it as the boolean True)
  #   # once measured:
  #   #   basis: measured
  #   #   evidence: { how: log, cmd: "<commands.device_log>", date: YYYY-MM-DD,
  #   #               value: '<TAG>.mount id=listA row=0' }

# --- fix alternatives considered ---
alternatives: []
  # - id: A2
  #   name: suppress-when-invalid
  #   outcome: discarded      # chosen | discarded | reopened
  #   because: 'clamping to the last valid index is enough'
  #   basis: asserted         # asserted = discarded by REASONING, not measurement
  #   depends_on: [D3]        # registry ids this rationale rests on.
  #                           #   If any dies, `verify` REOPENS this entry.
  #   falsified_by: 'evidence that any index > 0 rearms the deferred scroll'

worst_case: {}          # e.g. { case: nueva-manera, chars: 24000, gen_s: 150 }

# --- HTTP / interface contracts (prose JSON blocks must match these) ---
contracts:
  # request_body: [field_a, field_b, ...]
  # response_ok:  { field: type }
  # response_err: { field: type }

endpoints: {}           # e.g. { edge_proxy: chat-result, external_get: /webhook/chat-result }
env_vars: []            # names only, never values. e.g. [RESULT_URL, RESULT_TOKEN]

# --- verification anchors ---
# tests_baseline is MEASURED — use the basis/evidence shape, never a hand-typed string.
tests_baseline:
  basis: measured
  evidence: { how: shell, cmd: "<test runner cmd>", date: "<YYYY-MM-DD>",
              value: "<n/n passing (m files)>" }
acceptance: []          # Definition-of-Done items (shared across docs).
                        #   Authored by `new`, in STAGE 1: "what would make this done" is an
                        #   INPUT to deciding whether to build it, not an output of building.
                        #   Only its rendering as doc 02's Definition of Done waits for
                        #   `implement`. Until then this list is the only home the criteria
                        #   have — which is why they carry their own state rather than
                        #   depending on a doc that does not exist yet.
                        #
                        #   EACH CRITERION CARRIES ITS OWN STATE. A plain string is still
                        #   accepted and reads as `status: written`, so existing sets do not
                        #   break — but a set cannot reach `shipped` on strings alone.
                        #     status: written  - the criterion exists. Nothing was run.
                        #     status: executed - it was run. Record when, and what happened.
                        #     status: approved - it was run AND it passed.
                        #   - { id: AC1, item: 'el cron deja rastro de cada corrida',
                        #       status: approved, verified_on: YYYY-MM-DD,
                        #       evidence: 'la corrida de las 06:00 quedó registrada' }
                        #
                        #   Why the field exists: an E2E step was executed and approved and
                        #   the fact lived ONLY in prose inside a log entry. Later entries
                        #   kept saying it was pending. Nobody lied — there was nowhere to
                        #   write it, and the log is append-only, so the last mention wins
                        #   even when it is the oldest.
                        #
                        #   And the harder case it exists to stop: a set was marked `shipped`
                        #   holding two criteria that NOTHING could satisfy, one of them
                        #   annotated "this is THE test of the set". The decision that killed
                        #   them was recorded correctly in _log.md — but the log is narrative
                        #   and acceptance[] is contract. The audit passed clean because no
                        #   check compared acceptance[] against reality. Now one does.

# --- cross-doc registry ---
# List the docs in this set so audit knows what to check and cross-refs can resolve.
#
# `stage:` is the `status:` this doc is written AT. A doc whose stage the set has
# not reached is NOT expected on disk, and audit skips the checks that read it
# (5 checklist coverage, 6 acceptance parity, 13 doc-02 executability) instead of
# reporting a pile of DRIFT against a file nobody was supposed to write yet.
# Stage reached and the file is missing → that IS a finding.
#
# A doc with no `stage:` is read as `draft`. Sets written before staging keep
# auditing exactly as they did.
#
# Never add an `exists:` field here. File presence is cheap to verify, so it is
# read from disk — asserting it is the same defect as copying a test count.
docs:
  - { id: "01", file: 01-master-plan.md, role: master-plan, stage: draft }
  - { id: "02", file: 02-implementation-and-e2e.md, role: implementation, stage: reviewed }
  - { id: "03", file: 03-stakeholder-requirements.md, role: stakeholder, stage: reviewed }
