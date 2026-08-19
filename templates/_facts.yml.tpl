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

feature: <slug>
profile: <path to the _profile.yml this set was written against>   # resolved by the upward walk
title: <Human-readable feature title>
status: draft           # draft | reviewed | implementing | shipped | paused
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
# evidence.how: shell | git | device | log   (cmd comes from _profile.yml commands.*)
#   shell  - a command. value = its output, verbatim.        <- commands.tests/lint/build
#   git    - repo/file state.                                <- commands.file_tracked/file_ignored
#   device - a NUMBERED manual procedure. value = observed.  <- commands.force_stop
#   log    - a log line. value = the decisive line, quoted.  <- commands.device_log
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

# --- domain facts (fill with the real shared numbers/names) ---
limits: {}              # e.g. { cloudflare: { timeout_s: 100, error: 524 } }

# Scope is TWO disjoint lists — do not mix them:
changes: []             # components CREATED or MODIFIED by this feature (bots, edge functions, modules).
                        #   ONLY these participate in scope-parity (audit check 7).
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
acceptance: []          # bullet list of Definition-of-Done items (shared across docs)

# --- cross-doc registry ---
# List the docs in this set so audit knows what to check and cross-refs can resolve.
docs:
  - { id: "01", file: 01-master-plan.md, role: master-plan }
  - { id: "02", file: 02-implementation-and-e2e.md, role: implementation }
  - { id: "03", file: 03-stakeholder-requirements.md, role: stakeholder }
