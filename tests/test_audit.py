#!/usr/bin/env python3
"""Every mechanized check, against the real case that motivated it.

A check with no case is another rule in prose, which is the problem this whole
effort exists to solve. So each fixture under tests/fixtures/ reproduces a failure
that actually happened in a real spec set, and each case below states both:

  expect — findings the check MUST produce
  reject — findings it must NOT produce (the false positives that were found by
           running this against three real sets, and fixed)

    python3 tests/test_audit.py [-v]
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AUDIT = ROOT / "scripts" / "audit.py"
FIXTURES = Path(__file__).resolve().parent / "fixtures"

# (fixture, expect[(check, text)], reject[(check, text)])
CASES: list[tuple[str, list[tuple[str, str]], list[tuple[str, str]]]] = [
    # Check 45 — narrative history inside a registry entry, read twice every round.
    # Dated keys (any size) and a `note:` over 600 chars fire; outcome, correction,
    # retired_because, falsified_by and conditions, however long, and a short note
    # do not (rules.md requires that prose in the registry).
    ("registry-history",
     [("45", "outcome_2026_09_04"), ("45", "attempt-2026-09-05"),
      ("45", "`note` is 1439 chars")],
     [("45", "defects.D2"), ("45", "`outcome`"), ("45", "`correction`"),
      ("45", "`retired_because`"), ("45", "`falsified_by`"), ("45", "`conditions`"),
      ("45", "defects.D3"), ("45", "until_2026-12-01"), ("45", "first_2026_09_04"),
      ("45", "at_2026_09_04"), ("45", "measured_2026_09_04")]),

    # §1.1 — five anchors moved by the author's own later edits; eight bare ones.
    ("anchor-drift",
     [("18", "chat.ts:341"), ("18", "bare anchor")],
     []),

    # §1.1 — three anchor shapes from real sets: a route group, a scoped package,
    # and an anchor in parentheses, which the fix for the first one broke.
    ("anchor-shapes",
     [("18", "app/(tabs)/index.tsx:99` is past end")],   # resolved THROUGH the group
     [("18", "bare anchor"),                  # stopped at the paren: `index.tsx`
      ("18", "d11/pkg/Mod.java:1` — file"),   # read from `d11/`, missing
      ("18", "(src/real.ts"),                 # the prose paren swallowed
      ("18", ":2` — file missing")]),

    # §1.2 — `alternatives:` deleted by hand, A1-A4 reparented under `defects:`.
    ("reparented-keys",
     [("21", "lives under `defects:`"),          # A1 survived, its category did not
      ("21", "no `alternatives:` key at all")],  # A9 vanished with the container
     []),

    # §1.3 — a declared path that does not resolve, and the two real exceptions.
    ("declared-file",
     [("20", "src/gone.ts")],
     [("20", "cron.job"),            # where: external — no file in this repo
      ("20", "cleanup_runs.sql")]),  # kind: deferred — absent by design

    # The registry as INPUT, not instruction. Three sites joined a registry-supplied
    # path onto the repo root and opened what came back, so `docs/../../outside/x`
    # walked straight out of the checkout: check 18 reported the file's line count,
    # check 20 reported its existence, and `profile:` was read, parsed as YAML and had
    # its `repo:` value printed verbatim in a finding. Every escaping path in the
    # fixture names a file that really exists two levels up — the assertion is about
    # the boundary, not about absence.
    ("escaping-paths",
     [("18", "resolves outside"),
      ("20", "resolves outside"),
      ("15", "does not resolve")],
     [("18", "src/real.ts"),          # the in-repo control is silent, as before
      ("20", "src/real.ts"),
      ("18", "past end of file"),     # the giveaway: nothing outside was opened
      ("20", "does not exist under")]),  # refused for escaping, not for being absent

    # §1.4 — registry entries no doc mentions, and a qualified cross-set ref.
    ("orphan-and-crossset",
     [("21", "defects.D2")],
     [("21", "defects.D1"),      # cited by id
      ("21", "defects.D6")]),    # another set's id, qualified by a path

    # §1.5 — a Fase 8 inserted into a doc that already had a Fase 8.
    ("duplicate-phase",
     [("22", "duplicate phase numbers: [8]")],
     []),

    # §1.7 / check 14 — the four gates plus the cheap detector.
    ("shipped-asserted",
     [("14", "D1"),               # G1: shipped with an asserted root_cause
      ("14", "D2"),               # open in a shipped set, no owned_by, no outcome
      ("14", "A3")],              # discarded on a premise that is now dead
     []),

    # check 14 / G3 — `log_line:` absent vs. explicitly null. The message offers
    # "or `log_line: null` to say it must be built"; the guard was `not
    # e.get("log_line")`, so a defect that wrote exactly that re-drifted every run.
    # Real case: five cosmetic doc-set-hygiene defects with no possible emitter.
    ("log-line-null",
     [("14", "H1"),               # key absent — instrumentation never considered
      ("14", "H3")],              # `log_line: '   '` — a key with nothing in it
     [("14", "H2"),               # `log_line: null` — declared as must-be-built
      ("14", "H4")]),             # names the emitter

    # v1.7.1's family, one level over in audit.py: `evidence:` as a bare string
    # reached `.get("how")` in two checks and crashed the whole audit. It must
    # drift through the basis gate, not raise.
    ("evidence-string",
     [("1b/14", "evidence lacks")],
     []),

    # §3.3 — a `measured` whose cmd can never be re-run.
    ("cmd-not-runnable",
     [("24", "l1_prose_ref"), ("24", "l2_placeholder")],
     [("24", "l3_real_curl")]),  # %{http_code} is curl syntax, not a hole

    # §2.1 — a deferral with no reopen condition is abandonment with better wording.
    ("deferred-no-reopen",
     [("23", "C1"), ("23", "C3"),
      ("23", "C4")],             # a threshold with no number is an opinion
     [("23", "C2")]),            # has both required fields, with the measurement

    # §4.3 — F2 named F3 in prose, F3 died, nobody went back to F2.
    ("undeclared-depends",
     [("25", "F2")],
     [("25", "F4")]),            # declares its depends_on

    # render.py's alternation gate missed every `rg` invocation carrying flags.
    ("cmd-alternation",
     [("1b/14", "l1_alternation")],
     [("1b/14", "l2_shell_pipe")]),  # a shell pipe is not an alternation

    # §2.4 + §4.2 — the set shipped holding criteria nothing could satisfy.
    ("acceptance-unverified",
     [("26", "AC1"),          # never verified
      ("26", "AC2"),          # executed, never approved
      ("26", "AC4"),          # approved with no date
      ("26", "`status: verified` is not")],  # unknown value: used to pass silently
     [("26", "AC3")]),        # approved, dated

    # §4.3 — the open question its dead dependency already answered.
    ("dead-dependency",
     [("27", "F2")],
     [("27", "F5"),           # wrote its outcome
      ("27", "F6")]),         # its dependency is still alive

    # G1 gains a third state: a deferral with a deadline, recorded on paper.
    ("accepted-risk",
     [("1b/14", "R2"),            # the date passed — G1 refuses again
      ("1b/14", "R3"),            # `accepted:` with no `until:` excuses nothing
      ("1b/14", "R4"),            # an agent cannot accept a risk on its own behalf
      ("1b/14", "R5")],           # no `accepted:` at all — original behaviour
     [("1b/14", "R1")]),          # recorded, not yet due

    # Capitalized enums used to switch off the check that read each one. A gate
    # that fails open is worse than no gate: `status: Shipped` ranked 0, so the
    # set audited as a draft with a root cause still asserted.
    ("mixed-case",
     [("1b/14", "M1"),            # G1 through `Shipped` + `Root_Cause` + `Asserted`
      ("14", "M1"),               # open in a shipped set
      ("27", "M3"),               # cascade through `status: Dead`
      ("23", "N1")],              # reopens_when demanded through `kind: Deferred`
     [("21", "M1"),               # `Defects.M1` with a capital D still resolves
      ("26", "AC1")]),            # `status: Approved` is a valid approval

    # §1.6 — cheap-to-verify state asserted anyway.
    ("tracking-drift",
     [("28", "a-branch-that-was-never-created"),
      ("28", "no `issues:` and no `pr:`")],
     []),

    # §3.4 — a provider claim reasoned from config instead of executed.
    ("provider-behavior",
     [("29", "p1_described")],
     [("29", "p2_observed")]),   # pastes the observed status and body

    # Staging: docs 02/03 declared, not yet due, and not reported.
    ("stage-draft",
     [],
     [("9", "02-implementation"), ("9", "03-stakeholder")]),

    # Staging: the set claims `implementing` but never wrote doc 02.
    ("stage-overdue",
     [("9", "02-implementation-and-e2e.md is not on disk")],
     []),

    # Staging: a set written before `stage:` existed audits exactly as before.
    ("legacy-no-stage",
     [("9", "02-implementation-and-e2e.md is not on disk")],
     []),

    # §9, the direction that did not exist: disk -> docs[]. `check_docs_on_disk`
    # asked whether each declared doc is present; nothing asked the inverse, so a
    # file on the theme that no entry names sat outside the source-of-truth net.
    # Both rejects are the classes a naive glob turns into noise.
    ("sibling-doc/docs/features/sibling-doc",
     [("9", "sibling-doc-actionables.md"),   # inside the spec dir, unregistered
      ("9", "sibling-doc-decisions.md")],    # adjacent to it, matched by *<slug>*
     [("9", "other-feature-notes.md"),       # same directory, another feature
      ("9", "legacy-notes.md"),              # named by `related_docs[]`
      ("9", "_log.md")]),                    # set machinery, never a docs[] member

    # §9 — _inbox/ coordination files: check 9 ignores _-prefixed machinery.
    ("inbox-ignored",
     [],
     [("9", "BRIEF-1-x.md"),
      ("9", "R-1-x.md"),
      ("9", "_inbox")]),


    # §15 — a spec folder copied between projects, profile travelling along. Both
    # halves are pure string comparison and both were left to the human pass.
    ("foreign-profile",
     [("15", "some-other-checkout"),   # `repo:` names another checkout
      ("15", "apps/consumer")],        # `app:` does not govern this spec's dir
     []),

    # The same check against an unfilled starter: angle brackets are not a value.
    ("starter-profile",
     [],
     [("15", "basename of the git root"), ("15", "app subdir")]),

    # §15 — the half foreign-profile cannot cover: a profile that MATCHES. `repo:` is
    # this mini-repo's own basename, `app:` is the subdir really holding the spec.
    # Both comparisons shipped in v1.6.0 with no case proving they can come out clean,
    # and a check that only ever fires reads the same as one that always fires. The
    # first reject is also what makes renaming this fixture directory loud: the name
    # and the `repo:` value are coupled, and the day they disagree this fails.
    ("nested-profile/apps/mobile",
     [],
     [("15", "but this checkout is"), ("15", "does not govern")]),

    # §5 — three retractions, one hole: `n=1` read as a constant. `n:` is asked of
    # the three `how`s that are a run A PERSON performed; `shell` is exempt because a
    # command carries its own repeatability, and demanding it there would bury these.
    ("sample-size",
     [("30", "s1_bare_single"),          # n: 1 with no spread — the shape itself
      ("30", "s2_multi_no_spread"),      # 5 runs reported as one number
      ("30", "s3_missing_n")],           # the set records `n:` elsewhere and not here
     [("30", "s4_measured_with_bar"),    # n + the observed extremes
      ("30", "s5_shell")]),              # `how: shell` — not a run someone repeated

    # §5, the collapse: `n:` is newer than the set, so three identical misses are one
    # finding. Same rule as check 26 — reporting each of them buries the
    # contradictions beside them, which is the wall stage gating exists to prevent.
    ("sample-size-none",
     [("30", "no `evidence.n:` on any of the 3 measurements")],
     [("30", "c1_tiles"), ("30", "c2_buffer"), ("30", "c3_mount")]),

    # §5, the tier the local case is not: a single run leaving its own set. The child
    # cites the parent's `limits.degradation_threshold_tiles` — one run, no bar — and
    # from here it reads as a constant. Real case, with half a spec hanging off it.
    ("cross-set-n1/docs/features/child-rails",
     [("30", "degradation_threshold_tiles")],
     [("30", "tolerated_dropped_frames")]),   # n: 6 with its spread

    # §6 — four events varying 2.3x in bitrate and no number recording which one.
    # D3 omits two keys the profile requires; D2 rests on D1 and was measured on a
    # different event, which is the comparison that decided the scope.
    ("run-conditions",
     [("31", "D3"),                      # `conditions:` missing required keys
      ("31", "D2")],                     # depends_on D1 across a different bitrate
     [("31", "D4")]),                    # depends_on D1 under the same conditions

    # §7 — the confound was marked BEFORE the run and the run happened anyway. A1 is
    # that run written down as if it produced something; A3 is the 2026-09-15 abort,
    # done correctly — the behaviour that was right and was recorded nowhere.
    ("aborted-run",
     [("32", "A1"), ("32", "A2")],
     [("32", "A3")]),

    # §8 — absence of signal is not signal of absence. z3 is the real case stated
    # honestly (nothing emits) and it is STILL a finding, which is the point: the
    # explicit null is decisive, not an out. Same shape as check 14's `log_line`.
    ("absence-signal",
     [("33", "z1_undeclared"),           # absence-shaped value, never declared
      ("33", "z2_no_emitter"),           # declared, but "does the path emit?" unasked
      ("33", "z3_emits_null"),           # nothing emits — so it proves nothing
      ("33", "z4_no_sample_rate")],      # at 0.2, an empty result is the expectation
     [("33", "z5_complete"),
      ("33", "z6_positive"),             # a real signal is not an absence
      ("33", "z7_declared_false")]),     # `absence: false` — an observation that
                                         # only reads like an empty result

    # §2.2 — a changes[] entry depends_on a decision revised in place. C16 was never
    # reviewed since; C19 was reviewed, but before the revision — both stale. C17
    # was reviewed after; C18 depends on a decision nobody has touched — silent.
    ("changes-decision-revised",
     [("34", "C16"), ("34", "C19")],
     [("34", "C17"), ("34", "C18")]),

    # check 47 — fourteen defects of a real set stayed `open` after their fixes
    # merged. D1's only fix is built; D2 has one of two built; D3 is fixed; D4 is
    # open with an `outcome:` that says why.
    ("fixes-landed",
     [("47", "defects.D1"), ("47", "`D9`"), ("47", "not a list")],
     [("47", "defects.D2"), ("47", "defects.D3"), ("47", "defects.D4")]),

    # §15 — `app:` against a spec that genuinely lives in a subdirectory. `apps/consumer`
    # exists; it is simply not the one holding this spec. foreign-profile reports the
    # same finding for a weaker reason — its spec sits at the repo root, so `parts` is
    # empty and NO value of `app:` could have governed it. Here the comparison works.
    ("sibling-app/apps/mobile",
     [("15", "apps/consumer")],
     [("15", "but this checkout is")]),

    # check 26 — `status: retired`. AC6, AC12 and AC13 of a research set had to be
    # DELETED to let it ship, and their mentions rewritten by hand so they would not
    # dangle. Retired stays in the registry: it does not block `shipped`, its
    # citation still resolves, and nobody is required to cite it.
    ("acceptance-retired",
     [("26", "AC3")],                    # retired with no `retired_because:`
     [("26", "AC2"),                     # retired, complete — does not block shipped
      ("21", "AC2"),                     # its citation still resolves
      ("21", "AC4"),                     # never cited: history, not an orphan
      ("26", "AC1")]),                   # the approved control

    # check 35 — six defects went `measured` by naming limits inside `cmd:` as prose,
    # and the audit then demanded `n`/`spread` that already lived in those limits.
    ("derived-evidence",
     [("35", "D2"),                      # one source is `asserted`
      ("35", "D3"),                      # its source was retracted
      ("35", "D4"),                      # names an id the registry does not define
      ("35", "D5"), ("35", "D6"),        # circular
      ("35", "D8")],                     # corrected source, never acknowledged
     [("35", "D1"),                      # two measured sources: valid
      ("1b/14", "D1"),                   # and no `how`/`cmd` demanded of it
      ("30", "D1"),                      # nor an `n:` — it inherits its sources'
      ("35", "D7"),                      # corrected source, acknowledged
      ("36", "defects.D3"),              # a derived_from is check 35's, not 36's
      ("21", "purge_frees_nothing")]),   # retracted and uncited: history, not orphan

    # check 30 through check 35: a derived entry is as single-run as its weakest
    # source, and a set citing it sees none of that unless the check looks through.
    ("cross-set-derived/docs/features/child-rails",
     [("30", "weak_verdict")],           # rests on `one_run`: n: 1, no spread
     [("30", "strong_verdict")]),        # rests on n: 6 with its spread

    # check 36 — retractions, first class. The owning set: a retracted entry cited
    # as if it held is DRIFT; said in the same paragraph, or cited by the entry that
    # replaced it, it is not. The format half needs no citation at all.
    ("corrections/docs/features/tiles-research",
     [("36", "01-master-plan.md:4"),     # cites the retracted entry, says nothing
      ("36", "defects.D1"),              # same, from inside the registry
      ("36", "`retracted_on:` with no"),
      ("36", "`corrected_on:` with no"),
      ("36", "audio_is_born_late")],     # superseded by an id that does not exist
     [("36", "01-master-plan.md:6"),     # "fue retractada"
      ("36", "01-master-plan.md:8"),     # names the replacement
      ("36", "defects.D2"),              # "retractada el 2026-09-21"
      ("36", "@limits.purge_frees_proportionally"),  # the replacement itself
      ("36", "01-master-plan.md:11")]),  # corrected, not retracted: a candidate

    # check 36, the citing side, and the real case: `sports-multiview-grid` cites
    # limits of the research set that owns them, and nothing told it when one moved.
    ("corrections/docs/features/multiview-grid",
     [("36", "01-master-plan.md:4")],    # the owner retracted it
     [("36", "01-master-plan.md:6"),     # corrected: a candidate, not a finding
      ("36", "01-master-plan.md:8"),     # the replacement
      ("21", "purge_frees_nothing")]),   # qualified cross-set ref, not dangling

    # ---- the registry against the world: checks 37-43, 16's parsing half --------

    # §37 — AC2 retired, then handed out again; X1 in two containers; AC21 reused
    # from `reserved_ids:`; a reservation with no reason.
    ("ids-unique",
     [("37", "@acceptance.AC2"),
      ("37", "also used under alternatives:"),
      ("37", "reuses `AC21`"),
      ("37", "@reserved_ids.AC30")],
     [("37", "@acceptance.AC3")]),

    # §38 — a built file no `changes[]` entry names; a directory entry covering a
    # file under it; an exclusion with a reason and one without.
    ("source-tree",
     [("38", "@src/c.ts"),
      ("38", "no `because:`")],
     [("38", "@src/a.ts"),
      ("38", "@src/lib/b.ts"),
      ("38", "@src/c.test.ts"),
      ("38", "@src/gen/out.ts")]),

    # §39 — in a shipped set: built and present (control), built and gone,
    # planned and never dated, deferred and "built", a date that is prose.
    ("built-state",
     [("20", "src/gone.ts"),                 # check 20 owns the missing file here
      ("39", "@changes.C3"),
      ("39", "`kind: deferred`"),
      ("39", "is not a date"),
      ("38", "no `source_tree:`")],
     [("39", "@changes.C1"),
      ("39", "src/gone.ts` does not exist")]),   # ...so 39 does not repeat it
    ("built-status-lag",
     [("39", "`status: reviewed` while 1")],
     []),

    # §40 — an oldest-first list prepended by reflex, a newest-first changelog
    # inverted, and a changelog date the registry does not give the tag.
    ("revision-order",
     [("40", "listed after `v3` but older"),
      ("40", "lists `v2` after `v1`"),
      ("40", "`v2` dated 2026-09-09")],
     [("40", "lists `v1` after `v3`"),
      ("40", "lists `v5` after `v3`")]),      # older by date: ordered by age, not
                                              #   by position in an inverted registry

    # §41 — provisional sentences whose settling entry moved, and the ones that
    # must stay quiet: a marker dated after the last measurement, an open defect.
    ("provisional-prose",
     [("41", "@01-master-plan.md:3"),         # tests_baseline measured after
      ("41", "@01-master-plan.md:7"),         # C1 built after
      ("41", "@01-master-plan.md:9"),         # D1 dead
      ("41", "names nothing")],
     [("41", "@01-master-plan.md:5"),         # written after the last measurement
      ("41", "@01-master-plan.md:11")]),      # D2 still open, asserted

    # §43 — a validator that does not exist is a finding; the field it never
    # names is a candidate (CANDIDATE_CASES).
    ("contract-code",
     [("43", "src/refund-validate.ts")],
     []),

    # §34 defect half + §27 vocabulary.
    ("defect-cascade",
     [("34", "@changes.C1"),
      ("34", "@changes.C4"),
      ("27", "`status: resolved`")],
     [("34", "@changes.C2"),
      ("34", "@changes.C3")]),

    # §16 — the parsing half: order, required fields, recorded versions.
    ("log-integrity",
     [("16", "`R2` after R3"),
      ("16", "has no Read:"),
      ("16", "has no agent"),
      ("16", "@01-master-plan.md"),
      ("16", "no line count or blob")],
     [("16", "@02-implementation-and-e2e.md"),   # recorded blob matches the disk
      ("16", "R9"),                              # inside an HTML comment
      ("16", "`R6`")]),                          # stub + completion, one round

    # §16 — the half between rounds: R2 read a version R1 did not leave.
    ("log-between-rounds",
     [("16", "`R2` read `_facts.yml` at 11 lines, blob 2222222; `R1` left it at "
             "10 lines, blob 1111111")],
     [("16", "read `01-master-plan.md`"),        # same version both rounds
      ("16", "read `02-implementation.md`")]),   # R2's Edits: named it with no
                                                 # version — unknown, not wrong

    # §16 — disk comparison keys file records by resolved path, not literal spelling.
    # R1 records `_facts.yml` at vA; R2 edits it and records the disk version under
    # repo-relative `docs/features/log-spelling/_facts.yml`. Stale vA must not fire.
    ("log-spelling/docs/features/log-spelling",
     [],
     [("16", "DRIFT"),
      ("16", "_facts.yml")]),

    # §16 — disk comparison negative case: a third spelling whose blob genuinely
    # differs from disk still fires DRIFT.
    ("log-spelling-drift/docs/features/log-spelling-drift",
     [("16", "last recorded at _log.md:16 as 11 lines, blob 9999999; now 11 lines, blob 3ab985d")],
     []),

    # §44 — cross-set value parity: two sibling sets cite the same measurements.
    # The child cites parent's `limits.fps_per_tile`: clean with 24, DRIFT with 30,
    # DRIFT when citing an undefined key, and child's registry inherits via derived_from.
    ("cross-set-value/docs/features/child-rails",
     [("44", "01-master-plan.md:7"),            # value 30 does not match current 24
      ("44", "01-master-plan.md:10")],          # limits.nonexistent does not exist
     [("44", "01-master-plan.md:4"),            # clean: carries verbatim 24
      ("35", "rail_budget"),                    # derived_from inherits, clean for 35
      ("30", "rail_budget")]),                  # parent has n: 3 and spread, clean for 30

    # §16 — a file owned by another set (its directory holds _facts.yml and _log.md)
    # is accounted for by that set's log. Real case: a harness set had three empty
    # rounds appended only to copy its sibling app set's _facts.yml blob.
    ("cross-set-log/docs/features/citer-b",
     [("16", "owned by docs/features/owner-a, whose _log.md does not account for it"),  # 01 edited in A, unlogged
      ("16", "@docs/features/owner-c/_facts.yml")],         # owner with no log: today's rule
     [("16", "@docs/features/owner-a/_facts.yml"),          # A logged vA2; B carries nothing
      ("16", "edited between rounds")]),                     # R2 read vA2 after R1 left vA1
    ("cross-set-log/docs/features/owner-a",
     [("16", "@01-master-plan.md")],                         # the owner reports its own unlogged edit
     [("16", "@_facts.yml")]),
]

# (fixture, extra args, expect, reject) — cases that only exist under a flag.
FLAG_CASES: list[tuple[str, list[str], list[tuple[str, str]],
                       list[tuple[str, str]]]] = [
    # --as-status. A research set about to go `shipped` was previewed on a copy made
    # outside the repo, and 54 findings came back — most of them anchors "missing"
    # only because the copy was elsewhere. In place, in memory, nothing moves.
    ("as-status-preview", [],
     [],
     [("1b/14", "G1"), ("26", "AC1")]),  # at its real `reviewed`: neither fires
    ("as-status-preview", ["--as-status", "shipped"],
     [("1b/14", "G1"),                   # D1 still asserted
      ("26", "AC1")],                    # never verified
     [("16", "Stage")]),                 # the log cannot record a flip not yet made

    # --today moves G1's clock: the day after `until:` the risk is a finding again.
    ("accepted-risk-due", ["--today", "2026-10-24"],
     [("1b/14", "R1"), ("1b/14", "R3")],
     [("1b/14", "R2")]),

    # T3 — `acceptance[].attempts[]` and `closes:`.
    ("acceptance-attempts", ["--today", "2026-10-12"],
     [("26", "AC24"),                    # dangling closes: D9
      ("26", "AC25"),                    # attempts out of date order
      ("26", "AC26")],                   # approved with aborted last attempt and no verified_on
     []),
]



# (fixture, expect[(check, text)], reject[(check, text)]) — CANDIDATES, not findings.
#
# A candidate is a mechanical hit on a check whose verdict needs a document read, so
# it carries no severity and never enters `## Findings`. For these four checks the
# `reject` column is the one that matters: an over-reporting sweep costs the reader
# more tokens than the check saves, which is the opposite of why it was mechanized.
CANDIDATE_CASES: list[tuple[str, list[tuple[str, str]], list[tuple[str, str]]]] = [
    # check 49 — decisions dated after the tests doc's `regenerated_on:` that it
    # never names. DEC4 (date) and DEC6 (revised_on); DEC1 predates the doc, DEC2
    # and DEC3 are named bare and qualified, DEC5 has `untested_because:`.
    ("tests-doc-02e",
     [("49", "DEC4 (2026-10-14)"), ("49", "DEC6 (2026-10-15)"), ("49", "2 decisions")],
     [("49", "DEC1"), ("49", "DEC2"), ("49", "DEC3"), ("49", "DEC5")]),
    # check 46 — doc 02 code blocks vs the file they name. The real case: the code got
    # the guard in `finally`, the doc kept teaching the old one. Only the stale block
    # is a candidate; the equal one, the `antes:` one, the ```diff, the one with
    # comments and an elision, a block of < 3 lines, a line naming two files and
    # doc 01 (not an implementation doc) stay quiet.
    ("doc02-code-drift",
     [("46", "02-implementation.md:16"),
      ("46", "`await lock.release()`")],
     [("46", "02-implementation.md:7"),       # equal to the file
      ("46", "02-implementation.md:33"),      # `antes:` — the pre-change state
      ("46", "02-implementation.md:47"),      # ```diff
      ("46", "02-implementation.md:58"),      # comments + elision, same code
      ("46", "02-implementation.md:76"),      # 2 normalized lines
      ("46", "02-implementation.md:85"),      # two files named: ambiguous
      ("46", "01-master-plan.md")]),
    # check 36 — a CORRECTED entry is usually fixed in place, so a citation written
    # after the fix is right as it stands. Measured on two real sets: 2 of 9 such
    # citations were stale, 7 cited the corrected version. The script cannot tell
    # which side a line was written on, so it hands them over.
    ("corrections/docs/features/tiles-research",
     [("36", "same_url_is_easy")],
     [("36", "purge_frees_nothing")]),   # retracted: a finding, never a candidate
    ("corrections/docs/features/multiview-grid",
     [("36", "same_url_is_easy")],
     [("36", "purge_frees_proportionally")]),

    # §8 — the check the protocol says the mechanical audit is blind to, and the one
    # nobody runs by hand: catching it by eye means re-reading every document looking
    # for something defined by NOT being in the registry.
    ("prose-orphan",
     [("8", "invoice_id"),                    # ```json fence, no contract keys
      ("8", "/webhook/billing-callback"),     # ```http fence, no endpoints entry
      ("8", "abcd.supabase.co"),              # provider-hosted function URL
      ("8", "/api/v2/invoices"),              # bare API path in prose
      ("8", "miapp://reset-password")],       # deep-link URI
     [("8", "conversation_id"),               # keys ARE contracts.chat_request's
      ("8", "error_code"),                    # keys drifted, but the prose above
                                              #   cites the contract by id — whether
                                              #   the fields still match is check 3
      ("8", "/webhook/chat-result"),          # endpoints.external_get's own value
      ("8", "example.com"),                   # a host that exists to be an example
      ("8", "developer.mozilla.org"),         # a markdown link target: documentation
      ("8", "github.com/CesarRivasP"),        # a page URL, no API path, no function
      ("8", "ts_only_key"),                   # ```ts is not interface material
      ("8", "ts-fence.workers.dev"),          #   nor is the URL inside it
      ("8", "bash-fence.workers.dev")]),      # a curl line is the command, not the
                                              #   interface — the sweep is over PROSE

    # Checks 3 and 8 partition the same fences and neither reports the other's
    # cases. This is the seam, asserted from check 3's side in the fixture that
    # belongs to check 8: a fence ATTRIBUTED to a contract by id is check 3's even
    # when it shares no field with it, and a fence attributed to nothing has no
    # contract to be compared against and is check 8's alone.
    ("prose-orphan",
     [("3", "error_code")],
     [("3", "invoice_id")]),

    # §3 — the diff is arithmetic; the exception is not. A field the sender injects
    # downstream is legitimate IF a doc note explains it, and the script cannot read
    # the note. So the diff is a candidate and finding the note is the human's job.
    ("contract-shape",
     [("3", "trace_id"),                      # a field injected downstream
      ("3", "delivered_url"),                 # renamed: how a contract breaks quietly
      ("3", "form_gamma")],                   # a field that is simply missing
     [("3", "echo_alpha"),                    # same fields, different order
      ("3", "chat_status"),                   # diffed against response_ok, not the
                                              #   request body — comparing against the
                                              #   entry's flattened fields would report
                                              #   every response as broken
      ("3", "href"),                          # a nested key is not a field of this
                                              #   block; the contract declares the
                                              #   field, not its interior
      ("3", "tolerant_key"),                  # comments, elipsis and a trailing comma:
                                              #   it does not parse and still has a shape
      ("3", "unrelated_alpha"),               # shares nothing — check 8's, not this one
      ("3", "ts_shape_key")]),                # ```ts is not interface material

    # §4 — the check whose protocol entry says outright that mechanical sweeps
    # over-report, so every guard here exists to keep the list short enough to read.
    # The split doc is where its worst case lives: a ref that resolves in the other
    # half reads as valid and sends the executor to the wrong file.
    ("cross-refs",
     [("4", "docs[]` does not list"),          # `ver doc 04` with no 04 in docs[]
      ("4", "§9.9"),                          # resolves nowhere
      ("4", "§7.2 is unqualified"),           # resolves in the OTHER half of a split
      ("4", "§2.9 is unqualified")],          # a prefix does not distribute across a
                                              #   list: only the first ref is into `02`
     [("4", "1.5"),                           # local and present
      ("4", "7.6"),                           # qualified and present
      ("4", "3.1"),                           # `§3.1 de 02` — the prefix after the ref
      ("4", "3.6"),                           # exempt shape (a): quoted AS TEXT, a
                                              #   defect being described, not a target
      ("4", "5.5")]),                         # inside a fenced block

    # §13 — three of eight sub-bullets. The other five stay human and the protocol's
    # own enumeration says why: the last one names "judgment" outright.
    ("doc02-exec",
     [("13", "path/to/"),                     # unresolved path
      ("13", "…/c"),                          # an elided path is the same defect
      ("13", "componente correspondiente"),   # the parenthetical that defers the choice
      ("13", "etc."),                         # a step that enumerates by etc.
      ("13", "análogo a lo anterior"),
      ("13", "secreto")],                     # reaches outside the checkout, unlabelled
     [("13", "DNS"),                          # labelled `[MANUAL]` — the label IS the
                                              #   answer, not the absence of the step
      ("13", "similares"),                    # narrative, not a step: no list marker
      ("13", "and so on"),                    # inside a code fence
      ("13", "API key"),                      # an identifier in a snippet is not an
                                              #   instruction to go and get one
      ("13", "01-master-plan.md")]),          # scoped to doc 02, which is what
                                              #   stage-gates this check

    # §3 again, at the level where a descriptive key stops being descriptive. The
    # first fix attempted this by NAME and made the check worse — nine false
    # positives became thirteen different ones, reported as `extra {description}`
    # against documents that were right. Metadata sits at the entry, beside a
    # payload container; one level down the same word is a field.
    ("contract-meta",
     [("3", "missing {created_at}"),          # a real gap inside `columns`, still seen
      ("3", "missing {label}")],              # a flat entry IS the payload: no strip
     [("3", "missing {fields, note}"),        # the real case: a perfect match reported
                                              #   as a difference, because one scalar
                                              #   sibling collapsed the entry
      ("3", "auth"),                          # two descriptive siblings, not one
      ("3", "extra {label}"),                 # a real column, not metadata — this is
                                              #   the regression the by-name fix caused
      ("3", "flat_id")]),                     # present, and never stripped

    # §4 — one line, one candidate, once the line is enumerating rather than
    # pointing. A single changelog row produced 11 of one real set's 21 candidates,
    # and a two-line legend produced 4 that survived 48 review rounds untouched.
    ("ref-enumeration",
     [("4", "§4.4 resolves to no heading in `02`"),   # two refs on a line stay two:
      ("4", "§4.5 resolves to no heading in `02`"),   #   two is pointing, not listing
      ("4", "5 unresolved section refs on one line")],
     [("4", "§7.3 resolves"),                 # named inside the collapsed candidate,
                                              #   never as an item of its own
      ("4", "§3.6"),                          # exempt shape (a), quoted as text
      ("4", "§5 is unqualified"),             # the far end of `§1–§5`: one span, and
      ("4", "§8 resolves")]),                 #   its far end is nobody's destination

    # §13 — the word `dashboard` cannot carry this sub-rule alone: in the real
    # corpus it was wrong four times out of five, matching a screen the app itself
    # renders. A provider name beside it can. Unqualified hits collapse to one count
    # per document — the reader is still told, and can still grep.
    ("external-step",
     [("13", "02-implementation.md:7"),       # Supabase Dashboard — a third party's
      ("13", "02-implementation.md:8"),       #   console; Resend's signing secret
      ("13", "consola de Anthropic"),
      ("13", "4 step(s) name")],              # the collapsed count, with its lines
     [("13", "02-implementation.md:13"),      # `**Dashboard:** mostrar totales` — a
                                              #   screen, reported only inside the count
      ("13", "02-implementation.md:16"),      # blocking DNS inside a network test
      ("13", "02-implementation.md:19"),      # `[MANUAL]` — the label IS the answer
      ("13", "02-implementation.md:20")]),    # `[OWNER EXTERNO]`, same

    # §8 — doc 02 is paste-ready by design, so a set that creates a project ships
    # its `package.json`, its `tsconfig.json` and its i18n bundles as fences. Every
    # one is shaped like a payload and none is an interface anybody calls: 15 of 19
    # real candidates, then 6 more once the filename rule alone was measured. The
    # controls carry as much weight as the exemptions — a check that stops
    # reporting the real orphan has been switched off, not sharpened.
    ("config-fences",
     [("8", "amount_cents"),                  # a real prose-orphan payload, still seen
      ("8", "billing-notify"),                # a real orphan URL, still seen
      ("8", "read as file content")],         # the collapsed count, with its lines
     [("8", "config-fences"),                 # `package.json`, named two lines up
      ("8", "compilerOptions"),               # a manifest the prose never names:
                                              #   only its own keys identify it
      ("8", "Pendiente"),                     # a continuation fence: a key fragment
      ("8", "levels"),                        #   is not a payload to diff against
      ("8", "02-implementation.md:12")]),     # the first fence, by line: exempted
                                              #   inside the count, never on its own

    # §13 — the test plan is its own doc since v1.14.0, and the sweep reads it as
    # it reads `02`: an unresolved test-file path in `02e` is what the executor
    # copies. `03` names the same shape and is not the builder's input.
    ("tests-doc-02e",
     [("13", "02e-tests-and-e2e.md:6")],
     [("13", "03-stakeholder.md")]),

    # §42 — doc 01 predates what it cites; doc 02 cannot be dated at all.
    ("doc-freshness",
     [("42", "changes.C1"),
      ("42", "defects.D1"),
      ("42", "no `regenerated_on:`")],
     [("42", "changes.C2"),                   # built before the doc was
      ("42", "changes.C3")]),                 # moved after, but never cited

    # §43 — the field the validator never names; the ones it does stay quiet.
    ("contract-code",
     [("43", "`currency`")],
     [("43", "`user_id`"),
      ("43", "`amount`")]),
]


def run(fixture: str, extra: list[str] | None = None) -> list[dict]:
    """Every fixture is a hermetic mini-repo.

    `--repo-root` is the fixture's own directory, so every path check 20 resolves,
    every file check 18 globs for and every basename check 15 compares against comes
    from inside the fixture and from nothing else. Dropping the flag would point all
    three at feature-spec itself, where `scripts/` and `references/` happen to exist
    and `main` happens to be a branch — a fixture would then pass by borrowing the
    host repo's contents, which is the one failure mode a test suite cannot detect.
    A fixture that needs a path, a file or a branch to exist declares it and creates
    it inside itself.

    A name carrying a `/` splits the two roles apart: `nested-profile/apps/mobile`
    audits that spec dir with `nested-profile/` as the repo root. That is the only
    way to exercise a spec which does NOT sit at the root of its checkout — the
    normal shape in a real project, and the one check 15's `app:` half is about.
    """
    return run_json(fixture, extra)["findings"]


def run_json(fixture: str, extra: list[str] | None = None) -> dict:
    root = FIXTURES / fixture.split("/", 1)[0]
    spec = FIXTURES / fixture
    out = subprocess.run(
        [sys.executable, str(AUDIT), str(spec), "--repo-root", str(root), "--json",
         *(extra or [])],
        capture_output=True, text=True)
    if out.returncode not in (0, 1):
        raise AssertionError(f"{fixture}: audit.py crashed\n{out.stderr}")
    return json.loads(out.stdout)


def run_candidates(fixture: str) -> dict[str, list[dict]]:
    root = FIXTURES / fixture.split("/", 1)[0]
    spec = FIXTURES / fixture
    out = subprocess.run(
        [sys.executable, str(AUDIT), str(spec), "--repo-root", str(root), "--json"],
        capture_output=True, text=True)
    if out.returncode not in (0, 1):
        raise AssertionError(f"{fixture}: audit.py crashed\n{out.stderr}")
    return json.loads(out.stdout).get("candidates", {})


def run_text(fixture: str, extra: list[str] | None = None) -> str:
    root = FIXTURES / fixture.split("/", 1)[0]
    out = subprocess.run(
        [sys.executable, str(AUDIT), str(FIXTURES / fixture), "--repo-root", str(root),
         *(extra or [])], capture_output=True, text=True)
    if out.returncode not in (0, 1):
        raise AssertionError(f"{fixture}: audit.py crashed\n{out.stderr}")
    return out.stdout


def findings_group_without_loss() -> list[str]:
    """Check 16 repeated one DRIFT per old round. Text output prints N findings of
    one check and message template once, with ALL members listed; `--full` prints
    each; `--json` and the verdict count members either way."""
    errs: list[str] = []
    # unit: the header keeps values every member shares (an instruction like
    # `(<n> lines, blob <sha7>)` must not become <v>); dates stay whole tokens
    import io, contextlib
    sys.path.insert(0, str(AUDIT.parent))
    import audit as _a
    grp = [{"severity": "DRIFT", "check": 16, "where": f"d{i}.md",
            "what": f"`v{i}` dated 2026-09-0{i}, last at _log.md:{100 + i}",
            "fix": "record `(<n> lines, blob <sha7>)` for every file"} for i in (1, 2, 3)]
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        _a.print_grouped(grp)
    out = buf.getvalue()
    if "record `(<n> lines, blob <sha7>)` for every file" not in out:
        errs.append(f"grouping: a value every member shares was abstracted in the header:\n{out}")
    if "d1.md `v1` 2026-09-01 101" not in out or "2026 09" in out:
        errs.append(f"grouping: member line lost a date or a value:\n{out}")
    fx = "log-between-rounds"
    grouped, full = run_text(fx), run_text(fx, ["--full"])
    if "DRIFT \u00d73:" not in grouped:
        errs.append("grouping: three equal findings did not print one \u00d73 header")
    for member in ("01-master-plan.md", "02-implementation.md", "_facts.yml"):
        if not any(l.startswith("    ") and "\u00b7" not in l[:4] and member in l
                   and "last recorded" not in l for l in grouped.splitlines()):
            errs.append(f"grouping: member {member} missing from the member lines")
    for blob in ("3333333", "4444444", "2222222"):
        if blob not in grouped:
            errs.append(f"grouping: value {blob} was dropped (not lossless)")
    if "\u00d7" in full or full.count("last recorded at") != 3:
        errs.append("--full: findings must print one by one, ungrouped")
    if len(grouped.splitlines()) >= len(full.splitlines()):
        errs.append("grouping: grouped output is not shorter than --full")
    verdict = lambda t: t.strip().splitlines()[-1]
    if verdict(grouped) != verdict(full):
        errs.append("grouping: the summary must count members, not groups")
    # groups of 1-2 print as today
    rh = run_text("registry-history")
    if "\u00d7" in rh or rh.count("check 45") != 3:
        errs.append("grouping: findings that do not repeat must print as today")
    # --json is the same with and without --full, and carries every member
    a, b = run_json(fx), run_json(fx, ["--full"])
    if a != b:
        errs.append("--json changed with --full")
    if sum(1 for x in a["findings"] if "last recorded" in x["what"]) != 3:
        errs.append("--json lost a member")
    return errs


def matches(findings: list[dict], check: str, text: str) -> bool:
    """`@where` matches the location exactly — for an id that also appears inside
    another finding's message, where a substring match cannot tell the two apart."""
    if text.startswith("@"):
        return any(check in f["check"] and f["where"] == text[1:] for f in findings)
    return any(check in f["check"] and (text in f["what"] or text in f["where"])
               for f in findings)


def cand_matches(candidates: dict[str, list[dict]], check: str, text: str) -> bool:
    return any(text in c["what"] or text in c["where"]
               for c in candidates.get(check, []))


def candidates_stay_out_of_findings() -> list[str]:
    """The contract the whole design rests on, asserted across every fixture.

    A candidate has no severity — the script does not know yet whether it is a
    CONTRADICTION, a DRIFT or nothing at all. Putting one in `## Findings` means
    inventing a severity, and then the verdict line counts something nobody has
    judged. `N contradictions, M drift` has to mean what it says or the report is
    worth less than no report.

    The second half is the omission bug one level down: a candidate group whose
    check is missing from `HUMAN_PASS` would be computed and then never printed
    beside the check it belongs to. Every generator's key must be a listed check.
    """
    sys.path.insert(0, str(ROOT / "scripts"))
    from audit import HUMAN_PASS  # noqa: E402

    listed = {num for num, _, _, _ in HUMAN_PASS}
    problems = []
    for fixture, _, _ in CASES + CANDIDATE_CASES:
        for check in run_candidates(fixture):
            if check not in listed:
                problems.append(
                    f"{fixture}: candidates emitted under check {check}, which "
                    "HUMAN_PASS does not list — they are computed and never printed")
        for finding in run(fixture):
            if finding["check"].split()[0] in ("3", "4", "8", "13"):
                problems.append(
                    f"{fixture}: check {finding['check']} produced a FINDING "
                    f"({finding['where']}); these four generate candidates, and a "
                    "candidate with an invented severity makes the verdict lie")
    return problems


def human_pass_is_complete() -> list[str]:
    """The omission bug, made unrepeatable.

    Checks 2, 5, 8, 11 and 12 were tagged `[human]` in the protocol, absent from the
    script, and absent from `HUMAN_PASS` — so they were not run and not listed, i.e.
    silently skipped, which is the one failure this script exists to prevent. A
    check leaves `HUMAN_PASS` only by being mechanized and losing its `[human]` tag
    in the protocol, and this test is what forces those two edits to happen together.

    The regex reads BOTH tags, and that is the whole point. It used to read `[human]`
    alone, so retagging a check to `[script + human]` — the correct move the moment a
    script starts generating its candidates — silently released it from this test and
    let it drop out of `HUMAN_PASS` with nothing failing. That is the v1.6.0 bug
    rebuilt out of the fix for it. `[script + human]` means the script narrows the
    search and a person still has to look; it does not mean the check is done, so it
    STAYS listed. Checks 9, 15 and 16 were already tagged that way and already
    missing, which is what this widening surfaced.
    """
    sys.path.insert(0, str(ROOT / "scripts"))
    from audit import HUMAN_PASS  # noqa: E402

    protocol = (ROOT / "references" / "audit-protocol.md").read_text(encoding="utf-8")
    tagged = set(re.findall(
        r"^### ([\w.]+)\..* — \[(?:human|script \+ human)\]", protocol, re.M))
    listed = {num for num, _, _, _ in HUMAN_PASS}
    return [f"protocol tags check {n} for a human pass but HUMAN_PASS does not list "
            "it — it is neither run nor printed" for n in sorted(tagged - listed)]


def ship_ready_is_counted() -> list[str]:
    """31 rounds of `implementing`, then 23 blockers at once at ship time. The count
    rides on every verdict line of an `implementing` set, from the same gates
    `ship.py` refuses on, and leaves when the preview already lists them."""
    problems = []
    data = run_json("ship-ready")
    if data.get("ship_ready") != {"blockers": 0, "unbuilt": 0}:
        problems.append(f"ship-ready: expected 0 blockers, got {data.get('ship_ready')}")
    with tempfile.TemporaryDirectory() as tmp:
        spec = Path(tmp) / "ship-ready"
        shutil.copytree(FIXTURES / "ship-ready", spec)
        shutil.copy(FIXTURES / "_profile.fixture.yml", Path(tmp) / "_profile.fixture.yml")
        facts = spec / "_facts.yml"
        text = facts.read_text(encoding="utf-8")
        text = text.replace("status: approved, verified_on: 2026-09-20", "status: written")
        text = text.replace("docs:\n", "changes:\n  - { id: C1, file: src/a.ts, kind: "
                            "planned, change: 'a' }\ndocs:\n")
        facts.write_text(text, encoding="utf-8")
        out = subprocess.run([sys.executable, str(AUDIT), str(spec), "--repo-root",
                              str(spec)], capture_output=True, text=True).stdout
        verdict = out.strip().splitlines()[-1]
        if "ship-ready: 1 blocker + 1 planned without `built_on:`" not in verdict:
            problems.append(f"ship-ready: verdict line lacks the count: {verdict!r}")
        prev = subprocess.run([sys.executable, str(AUDIT), str(spec), "--repo-root",
                               str(spec), "--as-status", "shipped"],
                              capture_output=True, text=True).stdout
        if "ship-ready:" in prev:
            problems.append("ship-ready: --as-status shipped must not repeat the count")
        opened = subprocess.run([sys.executable, str(AUDIT), str(spec), "--repo-root",
                                 str(spec), "--open"], capture_output=True, text=True).stdout
        if "ship-ready: 1 blocker" not in opened.splitlines()[0]:
            problems.append("ship-ready: --open status line lacks the count")
    if run_json("fixes-landed").get("ship_ready") is not None:
        problems.append("ship-ready: printed for a set below `implementing`")
    return problems


def next_tag_follows_the_registry() -> list[str]:
    """An agent wrote `v6` in a changelog while the registry was at `v7`; check 40
    caught it a round later. `--next-tag` answers before the write."""
    problems = []
    for fixture, want in (("ship-ready", "v3"), ("fixes-landed", "v1")):
        out = subprocess.run([sys.executable, str(AUDIT), str(FIXTURES / fixture),
                              "--next-tag"], capture_output=True, text=True)
        if out.returncode != 0 or out.stdout.strip() != want:
            problems.append(f"--next-tag on {fixture}: expected {want}, got "
                            f"{out.stdout.strip()!r} {out.stderr!r}")
    return problems


def accepted_risks_come_due() -> list[str]:
    """Four risks of one research set were accepted together and all expire on
    2026-10-23. Printed like a risk due next year, they read as handled until G1
    refuses all four on the same morning. The ones inside the window are counted
    apart — and a risk expiring TODAY is still live, not yet a finding."""
    data = run_json("accepted-risk-due", ["--today", "2026-10-12"])
    left = {r["id"]: r["days_left"] for r in data.get("accepted_risks", [])}
    problems = []
    if left != {"R1": 11, "R2": 80, "R3": 0}:
        problems.append(f"accepted-risk-due: days_left per risk is {left}, expected "
                        "R1 11, R2 80, R3 0 — R3 expires today and is still live")
    out = subprocess.run(
        [sys.executable, str(AUDIT), str(FIXTURES / "accepted-risk-due"),
         "--repo-root", str(FIXTURES / "accepted-risk-due"), "--today", "2026-10-12"],
        capture_output=True, text=True).stdout
    due = out.split("## Accepted risks due within", 1)[-1].split("##", 1)[0]
    if "defects.R1" not in due or "defects.R3" not in due or "defects.R2" in due:
        problems.append("accepted-risk-due: the coming-due section must list R1 and R3 "
                        "and not R2")
    if "2 due within 14 days" not in out:
        problems.append("accepted-risk-due: the verdict line does not count the 2 "
                        "risks coming due")
    return problems


def acceptance_attempts_recorded() -> list[str]:
    """T3 — AC23 closes D1 and has an aborted attempt recorded. The report prints
    the attempt count and last attempt under D1, and json exports closing_criteria."""
    problems = []
    data = run_json("acceptance-attempts", ["--today", "2026-10-12"])
    risks = data.get("accepted_risks", [])
    r1 = next((r for r in risks if r["id"] == "D1"), None)
    if not r1:
        problems.append("acceptance-attempts: defects.D1 not found in accepted_risks")
    elif not r1.get("closing_criteria"):
        problems.append("acceptance-attempts: defects.D1 has no closing_criteria in JSON")
    else:
        crit = r1["closing_criteria"][0]
        if crit["id"] != "AC23" or crit["attempts_count"] != 1:
            problems.append(f"acceptance-attempts: expected AC23 with 1 attempt, got {crit}")

    out = subprocess.run(
        [sys.executable, str(AUDIT), str(FIXTURES / "acceptance-attempts"),
         "--repo-root", str(FIXTURES / "acceptance-attempts"), "--today", "2026-10-12"],
        capture_output=True, text=True).stdout

    expected_line = "AC23: 1 attempt, last 2026-10-12 aborted_no_conditions — no live event available in the window"
    if expected_line not in out:
        problems.append(f"acceptance-attempts: expected {expected_line!r} in stdout, got:\n{out}")

    return problems



def matrix_is_counted() -> list[str]:
    """The correspondence matrix used to be the agent's to build — a grep per datum
    per doc, then the table typed out — while `render.py` already counted the same
    cells for the view. It is printed from that count now.

    What has to hold: a fence is not prose, an enum word is not a citation, and a
    datum no doc writes out is a number in the footer, not a row of dots. And the
    table stays above the verdict — the verdict is the last line a caller reads."""
    matrix = run_json("matrix")["matrix"]
    rows = {r["value"]: r["counts"] for r in matrix["rows"]}
    problems = []
    if matrix["docs"] != ["01", "02", "03"]:
        problems.append(f"matrix: columns are {matrix['docs']}, expected the doc ids")
    if rows.get("100s") != [2, 0, 1]:
        problems.append(f"matrix: `100s` counted {rows.get('100s')}, expected twice "
                        "in 01, never in 02, once in 03")
    for value, why in (("resend-webhook", "it appears only inside a fence"),
                       ("planned", "`kind:` is an enum, not a datum"),
                       ("repo", "`where:` is an enum, not a datum"),
                       ("el proxy corta antes que el origen", "no doc writes it out")):
        if value in rows:
            problems.append(f"matrix: `{value}` has a row — {why}")
    if matrix["uncited"] < 1:
        problems.append("matrix: the uncited count lost the note no doc writes out")

    spec = str(FIXTURES / "matrix")
    text = subprocess.run([sys.executable, str(AUDIT), spec, "--repo-root", spec],
                          capture_output=True, text=True).stdout
    if "| 100s | limits.cloudflare.timeout | 2 | · | 1 |" not in text:
        problems.append("matrix: the text report does not print the `100s` row")
    if "datums cited" in text.strip().splitlines()[-1]:
        problems.append("matrix: the table is printed after the verdict line")
    if run_json("matrix", ["--no-matrix"])["matrix"] is not None:
        problems.append("matrix: --no-matrix still computed it")
    return problems


def git(cwd: Path, *args: str) -> str:
    out = subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
                         cwd=cwd, capture_output=True, text=True)
    if out.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed: {out.stderr}")
    return out.stdout.strip()


# the real case (16) plus the review of v1.26: reordered code, a plain comment that
# starts with 'before', a file named old-*, CSS custom properties
STALE46 = ["02-implementation.md:16", "02-implementation.md:142", "02-implementation.md:150", "02-implementation.md:168", "02-implementation.md:185"]


def doc02_code_drift_modes() -> list[str]:
    """Check 46 needs the registry's status and the branch the set names: a draft set
    does not run it, and a block is compared with the tree at `tracking.branch`, not
    with a checkout that has moved on."""
    problems = []
    src = FIXTURES / "doc02-code-drift"

    def n46(spec: Path, root: Path) -> list[str]:
        out = subprocess.run([sys.executable, str(AUDIT), str(spec), "--repo-root",
                              str(root), "--json"], capture_output=True, text=True)
        if out.returncode not in (0, 1):
            raise AssertionError(out.stderr)
        return [c["where"] for c in json.loads(out.stdout).get("candidates", {}).get("46", [])]

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "repo"
        spec = root / "docs" / "features" / "drift"
        shutil.copytree(src / "src", root / "src")
        shutil.copytree(src, spec, ignore=shutil.ignore_patterns("src"))
        shutil.copy(FIXTURES / "_profile.fixture.yml", spec / "_profile.fixture.yml")
        facts = spec / "_facts.yml"
        base = facts.read_text(encoding="utf-8").replace("../_profile", "_profile")
        facts.write_text(base, encoding="utf-8")
        if n46(spec, root) != STALE46:
            problems.append(f"implementing: expected only the stale block, got {n46(spec, root)}")
        facts.write_text(base.replace("status: implementing", "status: draft"),
                         encoding="utf-8")
        if n46(spec, root):
            problems.append("draft: check 46 ran before the set is implementing")

        # the branch the set names wins over the checkout
        facts.write_text(base + "tracking:\n  branch: feat/x\n", encoding="utf-8")
        git(root, "init", "-q", "-b", "main")
        git(root, "add", "."); git(root, "commit", "-q", "-m", "init")
        git(root, "branch", "feat/x")
        worker = root / "src" / "worker.ts"
        worker.write_text(worker.read_text(encoding="utf-8").replace(
            "const doubled = x * 2", "const doubled = x * 3"), encoding="utf-8")
        git(root, "commit", "-q", "-am", "main moves on")
        got = n46(spec, root)
        if got != STALE46:
            problems.append(f"branch: block compared with the checkout, not feat/x: {got}")
    return problems


def planned_landed_and_later_phases() -> list[str]:
    """Check 48: 19 `kind: planned` entries of a real set merged and kept no
    `built_on:` through `implementing`. A planned file with commits since
    `dates.drafted` is a candidate; one with none is not. And #54: once the set
    dates what it builds, an undated planned file of a later phase is not yet a
    missing file — until `shipped`, and never in a set that dates nothing."""
    problems = []
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "repo"
        (root / "src").mkdir(parents=True)
        git(root, "init", "-q", "-b", "main")
        (root / "src" / "old.ts").write_text("old\n")
        (root / "src" / "quiet.ts").write_text("quiet\n")
        git(root, "add", ".")
        old = "2026-01-01T00:00:00"
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit",
                        "-q", "-m", "init"], cwd=root, check=True,
                       env={**os.environ, "GIT_AUTHOR_DATE": old,
                            "GIT_COMMITTER_DATE": old})
        (root / "src" / "touched.ts").write_text("new\n")
        (root / "src" / "built.ts").write_text("new\n")
        git(root, "add", ".")
        git(root, "commit", "-q", "-m", "work")
        spec = root / "docs" / "features" / "landed"
        spec.mkdir(parents=True)
        shutil.copy(FIXTURES / "_profile.fixture.yml", spec / "_profile.fixture.yml")
        (spec / "01-master-plan.md").write_text("# plan\n")

        def facts(status: str, dated: bool = True, base: str | None = None) -> dict:
            built = ", built_on: 2026-10-01" if dated else ""
            track = f"tracking: {{ base_sha: '{base}' }}\n" if base else ""
            (spec / "_facts.yml").write_text(
                f"feature: landed\nstatus: {status}\nprofile: _profile.fixture.yml\n"
                + track +
                "dates: { drafted: 2026-06-01 }\n"
                "changes:\n"
                f"  - {{ id: C1, file: src/built.ts, kind: planned, change: 'a'{built} }}\n"
                "  - { id: C2, file: src/touched.ts, kind: planned, change: 'b' }\n"
                "  - { id: C3, file: src/quiet.ts, kind: planned, change: 'c' }\n"
                "  - { id: C4, file: src/later.ts, kind: planned, change: 'd' }\n"
                "docs:\n  - { id: \"01\", file: 01-master-plan.md, role: master-plan, "
                "stage: draft }\n")
            out = subprocess.run([sys.executable, str(AUDIT), str(spec), "--json"],
                                 capture_output=True, text=True)
            if out.returncode not in (0, 1):
                raise AssertionError(f"landed: audit.py crashed\n{out.stderr}")
            return json.loads(out.stdout)

        data = facts("implementing")
        c48 = " ".join(c["what"] for c in data["candidates"].get("48", []))
        if "C2 (`src/touched.ts`)" not in c48:
            problems.append(f"landed: check 48 missed the touched planned file: {c48!r}")
        if "C3" in c48 or "C1" in c48 or "C4" in c48:
            problems.append(f"landed: check 48 listed a quiet, dated or absent file: {c48!r}")
        if matches(data["findings"], "48", ""):
            problems.append("landed: check 48 must be a candidate, never a finding")
        if matches(data["findings"], "20", "src/later.ts"):
            problems.append("landed: check 20 fired on an undated later-phase file "
                            "while `implementing` (#54)")
        if not matches(facts("shipped")["findings"], "20", "src/later.ts"):
            problems.append("landed: check 20 must still fire on a missing file at shipped")
        if not matches(facts("implementing", dated=False)["findings"], "20", "src/later.ts"):
            problems.append("landed: a set that dates nothing keeps check 20 as before")
        if facts("reviewed")["candidates"].get("48"):
            problems.append("landed: check 48 ran below `implementing`")
        # `base_sha:` is registry input: an option-shaped value never reaches git
        evil = Path(tmp) / "evil.txt"
        data = facts("implementing", base=f"--output={evil}")
        if evil.exists():
            problems.append("landed: `tracking.base_sha:` reached git as an option")
        if "since 2026-06-01" not in " ".join(c["what"] for c in data["candidates"].get("48", [])):
            problems.append("landed: an invalid `base_sha:` must fall back to `dates.drafted`")
        sha = git(root, "rev-parse", "HEAD~1")
        c48 = " ".join(c["what"] for c in facts("implementing", base=sha)["candidates"].get("48", []))
        if f"since `{sha[:7]}`" not in c48 or "C2" not in c48:
            problems.append(f"landed: a valid `base_sha:` must bound the range: {c48!r}")
    return problems


def paths_resolve_on_the_spec_branch() -> list[str]:
    """Checks 18 and 20 resolve paths against the branch the registry names, not
    the checkout. Real case: a set audited from a `multiview` checkout reported a
    test file "does not exist" for a whole session; it existed on `tracking.branch`.

    Three states, one repo: on another branch the file is read from the ref and the
    report says so; on the same commit the working tree is used and nothing is
    printed; once `shipped`, the tag wins over the branch."""
    problems = []
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "repo"
        root.mkdir()
        git(root, "init", "-q", "-b", "main")
        (root / "README.md").write_text("# repo\n")
        git(root, "add", "."); git(root, "commit", "-q", "-m", "init")
        git(root, "checkout", "-q", "-b", "feat/x")
        (root / "src").mkdir()
        (root / "src" / "on-branch.ts").write_text("\n".join(f"l{i}" for i in range(20)) + "\n")
        (root / "src" / "extra.ts").write_text("export const amount = 1\n")
        git(root, "add", "."); git(root, "commit", "-q", "-m", "feat")
        git(root, "tag", "v1.0.0")
        git(root, "checkout", "-q", "main")
        spec = root / "docs" / "features" / "branchy"
        spec.mkdir(parents=True)
        shutil.copy(FIXTURES / "_profile.fixture.yml", spec / "_profile.fixture.yml")
        (spec / "01-master-plan.md").write_text(
            "# plan\n\nver `src/on-branch.ts:10` y `src/on-branch.ts:50`.\n")

        def facts(status: str, branch: str, tag: str | None = None) -> None:
            (spec / "_facts.yml").write_text(
                f"feature: branchy\nstatus: {status}\nprofile: _profile.fixture.yml\n"
                f"tracking: {{ branch: {branch}, pr: 1, shipped_in: {tag or 'null'} }}\n"
                "source_tree: { globs: ['src/**/*.ts'] }\n"
                "contracts:\n  pay: { fields: [amount, currency], basis: decided, "
                "validated_in: src/extra.ts }\n"
                "changes:\n  - { id: C1, file: src/on-branch.ts, kind: planned, "
                "where: repo, change: 'x', built_on: 2026-10-01 }\n"
                "docs:\n  - { id: \"01\", file: 01-master-plan.md, role: master-plan, "
                "stage: draft }\n")

        def run_here() -> dict:
            out = subprocess.run([sys.executable, str(AUDIT), str(spec), "--json"],
                                 capture_output=True, text=True)
            if out.returncode not in (0, 1):
                raise AssertionError(f"branchy: audit.py crashed\n{out.stderr}")
            return json.loads(out.stdout)

        facts("implementing", "feat/x")
        data = run_here()
        fs = data["findings"]
        if matches(fs, "20", "src/on-branch.ts"):
            problems.append("branchy: check 20 reported a file that exists on "
                            "`tracking.branch` as missing — it read the checkout")
        if matches(fs, "18", ":10` — file missing"):
            problems.append("branchy: check 18 reported `src/on-branch.ts:10` missing "
                            "— it read the checkout, not the branch")
        if not matches(fs, "18", ":50` is past end of file (20 lines at `feat/x@"):
            problems.append("branchy: check 18 must count lines on the branch and say "
                            f"which ref it read — got {[f['what'] for f in fs if '18' in f['check']]}")
        if not data.get("tree") or data["tree"]["checkout"].split("@")[0] != "main" \
                or not data["tree"]["spec"].startswith("feat/x@"):
            problems.append(f"branchy: the report must name checkout and spec branch, "
                            f"got {data.get('tree')}")
        # 38: the globs run over the branch — `src/extra.ts` is there and unregistered,
        # `src/on-branch.ts` is there and registered.
        if not matches(fs, "38", "@src/extra.ts"):
            problems.append("branchy: check 38 must glob `source_tree:` on the spec "
                            f"branch and report `src/extra.ts` — got "
                            f"{[f['where'] for f in fs if '38' in f['check']]}")
        if matches(fs, "38", "@src/on-branch.ts"):
            problems.append("branchy: check 38 reported a registered file")
        # 43: `validated_in` resolves on the branch; the grep runs over the branch's
        # content, so `currency` (absent there) is a candidate and `amount` is not.
        if matches(fs, "43", "does not resolve"):
            problems.append("branchy: check 43 read the checkout — `src/extra.ts` "
                            "exists on the spec branch")
        c43 = " ".join(x["what"] for x in data.get("candidates", {}).get("43", []))
        if "`currency`" not in c43 or "`amount`" in c43:
            problems.append(f"branchy: check 43 must grep the branch's file content, "
                            f"got candidates {c43!r}")

        # 39: `built_on:` below `implementing` checks the file exists — on the branch.
        facts("reviewed", "feat/x")
        fs = run_here()["findings"]
        if matches(fs, "39", "does not exist"):
            problems.append("branchy: check 39 said a built file does not exist — it "
                            "read the checkout, not the branch")

        facts("implementing", "main")
        data = run_here()
        if data.get("tree") is not None:
            problems.append("branchy: on the same commit the working tree is the tree, "
                            "and no header line is printed")
        if not matches(data["findings"], "20", "src/on-branch.ts"):
            problems.append("branchy: on `main` the file really is missing — check 20 "
                            "must still say so")

        facts("shipped", "main", "v1.0.0")
        data = run_here()
        if not data.get("tree") or not data["tree"]["spec"].startswith("v1.0.0@"):
            problems.append(f"branchy: once shipped, `shipped_in` is the ref, got "
                            f"{data.get('tree')}")
        if matches(data["findings"], "20", "src/on-branch.ts"):
            problems.append("branchy: the file exists at the tag; check 20 read the "
                            "checkout")
    return problems


def profile_identity_survives_worktrees() -> list[str]:
    """Check 15 compares `repo:` against the checkout's basename. In a linked
    worktree, the checkout is named for the worktree, not the repo, which raised a
    false CONTRADICTION. Resolving the main checkout's name keeps worktrees clean,
    flags genuine foreign profiles with both names, and still fires when a repo is
    copied to a new directory."""
    problems = []
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)
        repo = tmp / "app-repo"
        repo.mkdir()
        git(repo, "init", "-q", "-b", "main")
        (repo / "README.md").write_text("# app-repo\n")

        docs_feat = repo / "docs" / "features"
        docs_feat.mkdir(parents=True)
        prof = docs_feat / "_profile.yml"
        prof.write_text("repo: app-repo\ncommands:\n  tests: pytest\n")

        spec = docs_feat / "x"
        spec.mkdir()
        (spec / "_facts.yml").write_text(
            "feature: x\n"
            "status: draft\n"
            "profile: _profile.yml\n"
            "defects: []\n"
            "acceptance: []\n"
            "docs:\n"
            "  - { id: \"01\", file: 01-master-plan.md, role: master-plan, stage: draft }\n"
        )
        (spec / "01-master-plan.md").write_text("# Master Plan\n\nSome plan.\n")

        git(repo, "add", ".")
        git(repo, "commit", "-q", "-m", "init")

        def run_spec(target_spec: Path) -> list[dict]:
            out = subprocess.run([sys.executable, str(AUDIT), str(target_spec), "--json"],
                                 capture_output=True, text=True)
            if out.returncode not in (0, 1):
                raise AssertionError(f"worktree test: audit.py crashed\n{out.stderr}")
            return json.loads(out.stdout).get("findings", [])

        # 1. Main checkout: sin finding 15 'but this checkout is'
        fs1 = run_spec(spec)
        if matches(fs1, "15", "but this checkout is"):
            problems.append("worktree: main checkout unexpectedly reported check 15 'but this checkout is'")

        # 2. Linked worktree: sin ese finding
        git(repo, "worktree", "add", "-b", "wt", str(tmp / "fresh-clone-assets"))
        wt_spec = tmp / "fresh-clone-assets" / "docs" / "features" / "x"
        fs2 = run_spec(wt_spec)
        if matches(fs2, "15", "but this checkout is"):
            problems.append("worktree: linked worktree falsely reported check 15 'but this checkout is'")

        # 3. Copytree a tmp/copied-elsewhere -> finding 15 con 'but this checkout is `copied-elsewhere`'
        shutil.copytree(repo, tmp / "copied-elsewhere")
        cp_spec = tmp / "copied-elsewhere" / "docs" / "features" / "x"
        fs3 = run_spec(cp_spec)
        if not matches(fs3, "15", "but this checkout is `copied-elsewhere`"):
            problems.append("worktree: copytree to copied-elsewhere did not report check 15 with 'but this checkout is `copied-elsewhere`'")

        # 4. En worktree profile repo: some-other-checkout -> finding con '(a worktree of `app-repo`)'
        wt_prof = tmp / "fresh-clone-assets" / "docs" / "features" / "_profile.yml"
        wt_prof.write_text("repo: some-other-checkout\ncommands:\n  tests: pytest\n")
        fs4 = run_spec(wt_spec)
        if not matches(fs4, "15", "(a worktree of `app-repo`)"):
            problems.append("worktree: profile mismatch in worktree did not report '(a worktree of `app-repo`)'")

    return problems


def yaml_errors_name_their_position() -> list[str]:
    """A missing comma after `absence: true` inside a flow mapping came back as a
    raw `ComposerError`. The 36 checks never ran, and nothing said where to look.
    Now: `_facts.yml:<line>:<col>`, the line, a caret, and a distinct exit code."""
    with tempfile.TemporaryDirectory() as tmp:
        spec = Path(tmp) / "broken"
        shutil.copytree(FIXTURES / "absence-signal", spec)
        facts = spec / "_facts.yml"
        text = facts.read_text(encoding="utf-8")
        broken = text.replace("absence: true, sample_rate: 0.2 }",
                              "absence: true sample_rate: 0.2 }", 1)
        if broken == text:
            return ["yaml-error: the fixture no longer has the line this test breaks"]
        facts.write_text(broken, encoding="utf-8")
        out = subprocess.run([sys.executable, str(AUDIT), str(spec), "--repo-root",
                              str(spec)], capture_output=True, text=True)
    problems = []
    if out.returncode == 0 or out.returncode == 1:
        problems.append(f"yaml-error: a syntax error must exit with its own code, "
                        f"got {out.returncode}")
    where = re.search(r"_facts\.yml:(\d+):(\d+): not valid YAML", out.stderr)
    broken_at = next(i for i, l in enumerate(broken.splitlines(), 1)
                     if "absence: true sample_rate" in l)
    if not where:
        problems.append(f"yaml-error: stderr must start `_facts.yml:<line>:<col>: not "
                        f"valid YAML`, got {out.stderr[:200]!r}")
    elif int(where.group(1)) != broken_at:
        problems.append(f"yaml-error: reported line {where.group(1)}, the broken line "
                        f"is {broken_at}")
    if "^" not in out.stderr:
        problems.append("yaml-error: the offending line is printed with a caret")
    return problems


def read_line_round_trips() -> list[str]:
    """`--read-line` prints the `**Read:**` line of a log entry. The only thing that
    makes it worth having is that check 16 reads it back: a line in a shape the
    check's parser skips would record nothing, and would look exactly like a line
    that recorded everything. So the line goes into a log, the audit stays silent,
    and then one file moves and the audit must say which."""
    problems = []
    with tempfile.TemporaryDirectory() as tmp:
        spec = Path(tmp) / "matrix"
        shutil.copytree(FIXTURES / "matrix", spec)
        base = [sys.executable, str(AUDIT), str(spec), "--repo-root", str(spec)]

        out = subprocess.run(base + ["--read-line"], capture_output=True, text=True)
        line = out.stdout.strip()
        named = ("_facts.yml", "01-master-plan.md", "02-implementation.md",
                 "03-stakeholder.md", "_profile.fixture.yml")
        if out.returncode != 0 or not line.startswith("**Read:** ") \
                or any(f"`{n}` (" not in line for n in named):
            return [f"read-line: expected one `**Read:**` line naming {named}, got "
                    f"{out.stdout!r} {out.stderr!r}"]
        if "opened" not in out.stderr:
            problems.append("read-line: listing the whole set must say, on stderr, "
                            "that `Read:` claims only what was opened")

        (spec / "_log.md").write_text(
            f"## R1 · 2026-09-30 · test · author\n{line}\n"
            "**Log read through:** — (first entry)\n", encoding="utf-8")

        def stale() -> set[str]:
            data = json.loads(subprocess.run(base + ["--json"], capture_output=True,
                                             text=True).stdout)
            return {f["where"] for f in data["findings"]
                    if f["check"].startswith("16") and "last recorded" in f["what"]}

        if stale():
            problems.append(f"read-line: check 16 rejects the line it was handed, "
                            f"for {sorted(stale())}")
        for name in ("01-master-plan.md", "_profile.fixture.yml"):
            with (spec / name).open("a", encoding="utf-8") as fh:
                fh.write("una línea más\n")
        if stale() != {"01-master-plan.md", "_profile.fixture.yml"}:
            problems.append("read-line: two recorded files moved and check 16 reports "
                            f"{sorted(stale())} — the line was written in a shape the "
                            "check does not read")

        one = subprocess.run(base + ["--read-line", "03-stakeholder.md"],
                             capture_output=True, text=True)
        if one.stdout.count("blob ") != 1 or "03-stakeholder.md" not in one.stdout \
                or one.stderr:
            problems.append(f"read-line: naming one file must stamp that file and "
                            f"nothing else, got {one.stdout!r} {one.stderr!r}")
        gone = subprocess.run(base + ["--read-line", "nope.md"],
                              capture_output=True, text=True)
        if gone.returncode == 0 or gone.stdout:
            problems.append("read-line: a file that does not exist was stamped, or "
                            "skipped without failing")
    return problems


def edits_line_round_trips() -> list[str]:
    """`--edits-line` prints the `**Edits:**` line of a log entry. Check 16 reads it
    back: an Edits record becomes the version compared against disk (no "last recorded"
    drift) and against the next round's Read: (no "edited between rounds" drift)."""
    problems = []
    with tempfile.TemporaryDirectory() as tmp:
        spec = Path(tmp) / "matrix"
        shutil.copytree(FIXTURES / "matrix", spec)
        base = [sys.executable, str(AUDIT), str(spec), "--repo-root", str(spec)]

        out = subprocess.run(base + ["--read-line"], capture_output=True, text=True)
        line = out.stdout.strip()
        (spec / "_log.md").write_text(
            f"## R1 · 2026-09-30 · test · author\n{line}\n"
            "**Log read through:** — (first entry)\n", encoding="utf-8")

        with (spec / "01-master-plan.md").open("a", encoding="utf-8") as fh:
            fh.write("una línea más\n")

        ed = subprocess.run(base + ["--edits-line", "01-master-plan.md=one line"],
                            capture_output=True, text=True)
        if ed.returncode != 0 or not ed.stdout.startswith("**Edits:** "):
            problems.append(f"edits-line: expected `**Edits:**` line, got {ed.stdout!r} {ed.stderr!r}")
        ed_line = ed.stdout.strip()

        with (spec / "_log.md").open("a", encoding="utf-8") as fh:
            fh.write(f"{ed_line}\n")

        def check16_findings() -> list[dict]:
            data = json.loads(subprocess.run(base + ["--json"], capture_output=True,
                                             text=True).stdout)
            return [f for f in data["findings"] if f["check"].startswith("16")]

        # (a) Check 16 has no "last recorded" finding for 01-master-plan.md
        last_rec = {f["where"] for f in check16_findings() if "last recorded" in f["what"]}
        if "01-master-plan.md" in last_rec:
            problems.append("edits-line: (a) check 16 reports last recorded drift for 01-master-plan.md")

        # (b) After R2 with --read-line 01-master-plan.md is appended, no "edited between rounds" finding
        r2_out = subprocess.run(base + ["--read-line", "01-master-plan.md"],
                                capture_output=True, text=True).stdout.strip()
        with (spec / "_log.md").open("a", encoding="utf-8") as fh:
            fh.write(f"## R2 · 2026-10-01 · test · implement\n{r2_out}\n"
                     "**Log read through:** R1\n")

        between_rounds = {f["where"] for f in check16_findings() if "edited between rounds" in f["what"]}
        if "01-master-plan.md" in between_rounds:
            problems.append("edits-line: (b) check 16 reports edited between rounds for 01-master-plan.md")

        # (c) After one more line is appended to the file, check 16 reports exactly 01-master-plan.md
        with (spec / "01-master-plan.md").open("a", encoding="utf-8") as fh:
            fh.write("segunda línea extra\n")

        stale_after = {f["where"] for f in check16_findings() if "last recorded" in f["what"]}
        if stale_after != {"01-master-plan.md"}:
            problems.append(f"edits-line: (c) expected last recorded drift for only 01-master-plan.md, got {sorted(stale_after)}")

        # 5. Edge cases:
        paren = subprocess.run(base + ["--edits-line", "01-master-plan.md=has (paren)"],
                               capture_output=True, text=True)
        if paren.returncode == 0 or paren.stdout:
            problems.append("edits-line: description with parens must exit non-zero with nothing on stdout")

        nope = subprocess.run(base + ["--edits-line", "nope.md"],
                              capture_output=True, text=True)
        if nope.returncode == 0 or nope.stdout:
            problems.append("edits-line: missing file must exit non-zero with nothing on stdout")

        no_arg = subprocess.run(base + ["--edits-line"],
                                capture_output=True, text=True)
        if no_arg.returncode == 0:
            problems.append("edits-line: missing argument must fail (argparse error)")

    return problems


def entry_stub_shape() -> list[str]:
    """`--entry` prints a stub heading for a round entry, requiring --agent and --mode,
    and combining with --read-line and/or --edits-line. It prompts for Log read through
    on stderr without printing it on stdout."""
    problems = []
    with tempfile.TemporaryDirectory() as tmp:
        spec = Path(tmp) / "matrix"
        shutil.copytree(FIXTURES / "matrix", spec)
        base = [sys.executable, str(AUDIT), str(spec), "--repo-root", str(spec)]

        (spec / "_log.md").write_text(
            "## R1 · 2026-09-30 · test · author\n"
            "**Read:** `_facts.yml` (16 lines, blob fbfa5a3)\n"
            "**Log read through:** — (first entry)\n", encoding="utf-8")

        res = subprocess.run(base + ["--entry", "--agent", "t", "--mode", "implement",
                                     "--read-line", "_facts.yml", "--today", "2026-10-26"],
                             capture_output=True, text=True)
        if res.returncode != 0:
            problems.append(f"entry_stub_shape: expected exit 0, got {res.returncode}")
        lines = [ln for ln in res.stdout.splitlines() if ln.strip()]
        if len(lines) != 2:
            problems.append(f"entry_stub_shape: expected exactly two lines, got {lines!r}")
        else:
            if lines[0] != "## R2 · 2026-10-26 · t · implement":
                problems.append(f"entry_stub_shape: unexpected heading: {lines[0]!r}")
            if not lines[1].startswith("**Read:** "):
                problems.append(f"entry_stub_shape: unexpected read line: {lines[1]!r}")

        if "Log read through" not in res.stderr:
            problems.append(f"entry_stub_shape: stderr must mention 'Log read through', got {res.stderr!r}")

        r0 = subprocess.run(base + ["--entry", "R0", "--agent", "t", "--mode", "implement",
                                    "--read-line", "_facts.yml"],
                            capture_output=True, text=True)
        if r0.returncode == 0:
            problems.append("entry_stub_shape: --entry R0 on log at R1 must exit non-zero")

        bogus = subprocess.run(base + ["--entry", "--agent", "t", "--mode", "bogus",
                                      "--read-line", "_facts.yml"],
                               capture_output=True, text=True)
        if bogus.returncode == 0:
            problems.append("entry_stub_shape: --mode bogus must fail (argparse error)")

        no_line = subprocess.run(base + ["--entry", "--agent", "t", "--mode", "implement"],
                                 capture_output=True, text=True)
        if no_line.returncode == 0:
            problems.append("entry_stub_shape: --entry with neither line flag must fail")

    return problems


def log_size_counts_bytes() -> list[str]:
    """Check 16's size threshold, in both units. A log of long entries hit 103KB at
    701 lines — about 26k tokens — and the line threshold alone let it through. The
    control is the same text cut under both limits: it must stay quiet."""
    problems = []
    entry = ("## R{n} · 2026-09-30 · test · review\n**Read:** none\n"
             "**Log read through:** R{p}\n" + "x" * 1500 + "\n\n")
    for rounds, expect in ((60, True), (20, False)):
        with tempfile.TemporaryDirectory() as tmp:
            spec = Path(tmp) / "matrix"
            shutil.copytree(FIXTURES / "matrix", spec)
            (spec / "_log.md").write_text(
                "".join(entry.format(n=i, p=i - 1) for i in range(1, rounds + 1)),
                encoding="utf-8")
            data = json.loads(subprocess.run(
                [sys.executable, str(AUDIT), str(spec), "--repo-root", str(spec),
                 "--json"], capture_output=True, text=True).stdout)
            hit = any(f["check"].startswith("16") and "past what one read" in f["what"]
                      for f in data["findings"])
            if hit != expect:
                problems.append(f"log size: {rounds} rounds of 1.5KB "
                                f"({'over' if expect else 'under'} 80KB, under 800 lines) "
                                f"{'not ' if expect else ''}reported")
            if expect and hit:
                f16 = next(f for f in data["findings"] if f["check"].startswith("16") and "past what one read" in f["what"])
                if "--rotate-plan" not in f16.get("fix", ""):
                    problems.append("log size: POLISH remediation does not name --rotate-plan")
    return problems


def doc_index_spans_and_cites() -> list[str]:
    """`--doc-index` is only worth having if a span read by offset returns exactly
    the section. Each span below was counted by hand against the fixture: a fence
    holding `# no es heading`, a ~~~ fence, an HTML comment holding a heading, three
    nested levels and a preamble."""
    fx = str(FIXTURES / "doc-index")

    def call(*extra: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(AUDIT), fx, "--doc-index", *extra],
                              capture_output=True, text=True)

    problems = []
    out = call("--json")
    if out.returncode != 0:
        return [f"doc-index: --json exited {out.returncode}: {out.stderr[:200]}"]
    data = json.loads(out.stdout)
    files = [d["file"] for d in data["docs"]]
    if files != ["01-plan.md", "02-notes.md"]:
        problems.append(f"doc-index: docs {files}, expected the two that exist, no _log.md")
    plan = next(d for d in data["docs"] if d["file"] == "01-plan.md")
    got = [(s["level"], s["title"], s["start"], s["end"], s["cites"])
           for s in plan["sections"]]
    want = [(0, "(preamble)", 1, 2, []), (1, "Plan", 3, 34, []),
            (2, "Alcance", 7, 31, ["limits.gateway"]),
            (3, "Detalle", 11, 31, ["acceptance.AC5"]),
            (4, "Fondo", 20, 31, []), (2, "Cierre", 32, 34, [])]
    if got != want:
        problems.append(f"doc-index: sections {got}, expected {want}")
    # D2 is one letter and one digit: a `maybe`, not a cite; 125 is three digits: no cite
    got_own = [(s["title"], s["own_end"], s["maybe"]) for s in plan["sections"]]
    want_own = [("(preamble)", 2, []), ("Plan", 6, []), ("Alcance", 10, []),
                ("Detalle", 19, ["defects.D2"]), ("Fondo", 31, []), ("Cierre", 34, [])]
    if got_own != want_own:
        problems.append(f"doc-index: own_end/maybe {got_own}, expected {want_own}")
    if plan["lines"] != 34:
        problems.append(f"doc-index: 01-plan.md lines {plan['lines']}, expected 34")
    notes = next(d for d in data["docs"] if d["file"] == "02-notes.md")
    if notes["role"] != "legacy":
        problems.append(f"doc-index: role {notes['role']!r}, expected legacy")
    text = call().stdout
    for needle in ("# doc-index — doc-index", "## 01-plan.md (34 lines, blob ",
                   "role: legacy", "L11-31", "    cites: acceptance.AC5", "    maybe: defects.D2",
                   "skipped: 03-missing.md (missing)",
                   "offset = a, limit = b - a + 1."):
        if needle not in text:
            problems.append(f"doc-index: text output lacks {needle!r}")
    cites = json.loads(call("--cites", "defects.D2", "limits.gateway", "--json").stdout)["cites"]
    if [(r["file"], r["start"], r["own_end"], r["end"], r.get("maybe", False))
            for r in cites["defects.D2"]] != \
            [("01-plan.md", 11, 19, 31, True), ("02-notes.md", 1, 5, 5, False)]:
        problems.append(f"doc-index: --cites defects.D2 gave {cites['defects.D2']}")
    if "  01-plan.md L7-10 § Alcance (section L7-31)\n" not in \
            call("--cites", "limits.gateway").stdout:
        problems.append("doc-index: --cites text line missing the own span")
    if "  01-plan.md L11-19 § Detalle (section L11-31) (maybe)" not in \
            call("--cites", "defects.D2").stdout:
        problems.append("doc-index: --cites did not mark a maybe hit")
    if "  02-notes.md L1-5 § Notas\n" not in call("--cites", "defects.D2").stdout:
        problems.append("doc-index: a section whose own span is the whole section got a suffix")
    top = json.loads(call("--cites", "limits", "--json").stdout)["cites"]["limits"]
    if [(r["file"], r["start"], r["own_end"]) for r in top] != [("01-plan.md", 7, 10)]:
        problems.append(f"doc-index: --cites limits did not aggregate its children: {top}")
    scalar = call("--cites", "status")
    if scalar.returncode != 2 or "not an entry" not in scalar.stderr:
        problems.append(f"doc-index: --cites on a scalar exit {scalar.returncode}, expected 2")
    skipped = json.loads(call("--json").stdout)["skipped"]
    if skipped != [{"file": "03-missing.md", "reason": "missing"}]:
        problems.append(f"doc-index: skipped {skipped}")
    # a value two entries share names neither: real case, a date in 23 fields made every
    # changelog section cite the same 13 decisions
    for shared in ("limits.retention", "limits.archive"):
        if "not cited in any doc" not in call("--cites", shared).stdout:
            problems.append(f"doc-index: a value shared by two entries was cited as {shared}")
    bad = call("--cites", "defects.D9")
    if bad.returncode != 2 or "defects.D9" not in bad.stderr:
        problems.append(f"doc-index: unknown key exit {bad.returncode}, expected 2")
    for flag in (["--index"], ["--get", "defects.D2"], ["--open"], ["--rotate-plan"],
                 ["--entry", "--agent", "a", "--mode", "author", "--read-line"]):
        r = call(*flag)
        if r.returncode != 2:
            problems.append(f"doc-index: with {flag[0]} exit {r.returncode}, expected 2")
    if subprocess.run([sys.executable, str(AUDIT), fx, "--cites", "defects.D2"],
                      capture_output=True, text=True).returncode != 2:
        problems.append("doc-index: --cites without --doc-index did not exit 2")
    return problems


def doc_index_synthetic_bugs() -> list[str]:
    """Review fixes of `--doc-index`, each on a doc the test writes: every case below
    gave the wrong answer before its fix."""
    problems: list[str] = []
    facts = """feature: syn
status: draft
profile: ../_profile.fixture.yml
defects:
  - { id: D1, role: contributing, basis: asserted, status: open, claim: 'uno', falsified_by: 'x' }
  - { id: D24, role: contributing, basis: asserted, status: open, claim: 'dos', falsified_by: 'y' }
limits:
  cf: { timeout_s: 100, error: 524, code: 4242 }
  gateway: { max_urls: 125 }
docs:
%s
"""
    docs = {
        # b1: a `<!--` inside inline code is not a comment; b8: closing hashes need a space
        "a.md": "# A\nUsa `<!--` aqui.\n## B\n## C#\n## D ##\r\n  <!--\n## oculto\n-->\n## E\n",
        # b2/b3: short ids and small or glued numbers cite nothing
        "b.md": "# B\nCloudflare D1 y D24 y 100% y 1.524 y 524.\n",
        # b7: a BOM must not hide the first heading; b6: no trailing newline
        "c.md": "\ufeff# Primero\nlinea\n## Segundo",
    }
    with tempfile.TemporaryDirectory() as tmp:
        shutil.copy(FIXTURES / "_profile.fixture.yml", Path(tmp) / "_profile.fixture.yml")
        spec = Path(tmp) / "syn"
        spec.mkdir()
        for n, body in docs.items():
            (spec / n).write_bytes(body.encode("utf-8"))
        entries = ["  - { id: '1', file: a.md, role: master-plan, stage: draft }",
                   "  - { id: '2', file: ./a.md, role: master-plan, stage: draft }",
                   "  - { id: '3', file: b.md, role: legacy, stage: draft }",
                   "  - { id: '4', file: c.md, role: legacy, stage: draft }",
                   "  - { id: '5', file: ../outside.md, role: legacy, stage: draft }",
                   "  - { id: '6', file: sub, role: legacy, stage: draft }"]
        (spec / "sub").mkdir()
        (spec / "_facts.yml").write_text(facts % "\n".join(entries), encoding="utf-8")
        r = subprocess.run([sys.executable, str(AUDIT), str(spec), "--doc-index", "--json"],
                           capture_output=True, text=True)
        if r.returncode != 0:
            return [f"doc-index synthetic: exit {r.returncode}: {r.stderr[:200]}"]
        data = json.loads(r.stdout)
        by = {d["file"]: d for d in data["docs"]}
        if [d["file"] for d in data["docs"]] != ["a.md", "b.md", "c.md"]:
            problems.append(f"doc-index: a file listed twice was not deduped: {list(by)}")
        titles = [s["title"] for s in by["a.md"]["sections"]]
        if titles != ["A", "B", "C#", "D", "E"]:
            problems.append(f"doc-index: headings {titles}, expected A B C# D E")
        b_sec = by["b.md"]["sections"][0]
        # D24 (longer id) still cites; D1 is a maybe; `100%`, `1.524`, `524.` cite limits.cf not
        if b_sec["cites"] != ["defects.D24"] or b_sec["maybe"] != ["defects.D1"]:
            problems.append(f"doc-index: b.md cites {b_sec['cites']} maybe {b_sec['maybe']}")
        if by["c.md"]["lines"] != 2 or [s["title"] for s in by["c.md"]["sections"]] \
                != ["Primero", "Segundo"]:
            problems.append(f"doc-index: c.md lines {by['c.md']['lines']} / BOM headings")
        reasons = {(x["file"], x["reason"]) for x in data["skipped"]}
        if reasons != {("../outside.md", "outside the set"), ("sub", "not a file")}:
            problems.append(f"doc-index: skipped {data['skipped']}")
        # b3 positive control: a 4-digit value standing alone still cites
        (spec / "b.md").write_text("# B\nEl codigo 4242 y 4242.\nOtro: 4242\n", encoding="utf-8")
        r2 = subprocess.run([sys.executable, str(AUDIT), str(spec), "--doc-index", "--json"],
                            capture_output=True, text=True)
        sec = next(d for d in json.loads(r2.stdout)["docs"] if d["file"] == "b.md")["sections"][0]
        if sec["cites"] != ["limits.cf"]:
            problems.append(f"doc-index: a 4-digit value did not cite: {sec['cites']}")
        # a sentence's own period or comma is not a decimal point: real case, `timeout
        # 30000.` cited nothing after the glued-number fix; `1.4242` and `4242,5` still don't
        for body, want in (("# B\nEl timeout es 4242.\n", ["limits.cf"]),
                           ("# B\nCodigo 4242, luego nada\n", ["limits.cf"]),
                           ("# B\nVersion 1.4242 y 4242,5 y 4242.5\n", [])):
            (spec / "b.md").write_text(body, encoding="utf-8")
            r3 = subprocess.run([sys.executable, str(AUDIT), str(spec), "--doc-index", "--json"],
                                capture_output=True, text=True)
            got = next(d for d in json.loads(r3.stdout)["docs"]
                       if d["file"] == "b.md")["sections"][0]["cites"]
            if got != want:
                problems.append(f"doc-index: {body.splitlines()[1]!r} cited {got}, expected {want}")
    return problems


def registry_index_spans() -> list[str]:
    """`--index` is only worth having if a span read by offset returns exactly the
    entry: not the comment above it, not the blank after it, not the next entry's
    first line. Each span below was counted by hand against the fixture."""
    out = subprocess.run([sys.executable, str(AUDIT), str(FIXTURES / "registry-index"),
                          "--index"], capture_output=True, text=True)
    rows = {m.group(3): (int(m.group(1)), int(m.group(2)), m.group(4).strip())
            for m in re.finditer(r"^\s*L(\d+)-(\d+)\s+(\S+)(.*)$", out.stdout, re.M)}
    want = {"defects": (9, 20), "defects.D1": (10, 14), "defects.D2": (17, 20),
            "limits": (21, 25), "limits.cloudflare": (22, 22), "limits.resend": (23, 25),
            "docs": (26, 27)}
    problems = [f"index: `{k}` spans {rows.get(k, ('missing',))[:2]}, expected {v}"
                for k, v in want.items() if rows.get(k, (0, 0))[:2] != v]
    if "prose" in rows.get("defects.D2", (0, 0, ""))[2]:
        problems.append("index: a prose `outcome:` was printed as a label")
    if rows.get("defects.D1", (0, 0, ""))[2] != "root_cause · asserted":
        problems.append(f"index: D1 labelled {rows.get('defects.D1')}, expected "
                        "`root_cause · asserted`")
    return problems


def compact_output_and_get() -> list[str]:
    """`--open` is whole unless `--compact` (one clipped line per item); the human-pass
    block prints checks with candidates in full and every other check as one
    `check <id> <name>` line, `--full` restoring the descriptions; `--get` returns exact registry
    text for the keys named, and exits 2 on a key that is not there."""
    problems = []
    fx = str(FIXTURES / "open-items")
    base = [sys.executable, str(AUDIT), fx, "--repo-root", fx, "--today", "2026-10-15"]
    full = subprocess.run(base + ["--open"], capture_output=True, text=True).stdout
    compact = subprocess.run(base + ["--open", "--compact"], capture_output=True, text=True).stdout
    if any(len(l.strip()) > 80 for l in compact.splitlines() if l.strip().startswith("- R4")):
        problems.append("compact: an --open --compact finding line is longer than 80 characters")
    if "…" not in compact or "bucket table never prunes" in compact:
        problems.append("compact: --open --compact did not clip R4-F1's text with '…'")
    if "bucket table never prunes" not in full or "…" in full:
        problems.append("compact: plain --open did not print the whole text")
    if len(full) <= len(compact):
        problems.append("compact: --open is not longer than --open --compact")
    bad_c = subprocess.run(base[:-2] + ["--compact"], capture_output=True, text=True)
    if bad_c.returncode != 2 or "--compact" not in bad_c.stderr:
        problems.append(f"compact: --compact without --open must exit 2, got {bad_c.returncode}")
    for h in ("## Findings without a disposition", "## Defects open",
              "## Where the scripts are"):
        if h not in compact:
            problems.append(f"compact: --open lost the heading {h!r}")

    shape = [sys.executable, str(AUDIT), str(FIXTURES / "contract-shape"), "--no-matrix"]
    hp = subprocess.run(shape, capture_output=True, text=True).stdout
    hp_full = subprocess.run(shape + ["--full"], capture_output=True, text=True).stdout
    if "  check 3   contract shape" not in hp or "  check 8   prose-orphan" not in hp:
        problems.append("compact: a check with candidates must print in full")
    sys.path.insert(0, str(ROOT / "scripts"))
    from audit import HUMAN_PASS  # noqa: E402
    for num, name, _, _ in HUMAN_PASS:
        if f"  check {num:<3} {name}" in hp_full and f"  check {num:<3} {name}" not in hp:
            problems.append(f"compact: check {num} appears in --full but lost its name by default")
    if "  check 1b  re-run" not in hp:
        problems.append("compact: check 1b has no one-line entry")
    if "also by hand" in hp_full:
        problems.append("compact: stale 'also by hand' line")
    if "  check 1b  re-run `evidence.cmd` — " in hp or "  check 1   data-vs-registry wording —" in hp:
        problems.append("compact: a check without candidates printed its description")
    if "  check 1b  re-run `evidence.cmd` — " not in hp_full:
        problems.append("compact: --full did not print the whole human-pass block")

    ri = str(FIXTURES / "registry-index")
    got = subprocess.run([sys.executable, str(AUDIT), ri, "--get", "defects.D2",
                          "limits.resend"], capture_output=True, text=True)
    text = (FIXTURES / "registry-index" / "_facts.yml").read_text(encoding="utf-8").split("\n")
    want = ("# defects.D2 L17-20\n" + "\n".join(text[16:20]) + "\n"
            "# limits.resend L23-25\n" + "\n".join(text[22:25]) + "\n")
    if got.returncode != 0 or got.stdout != want:
        problems.append(f"get: output differs from the registry lines: {got.stdout!r}")
    bad = subprocess.run([sys.executable, str(AUDIT), ri, "--get", "defects.D1", "nope.x"],
                         capture_output=True, text=True)
    if bad.returncode != 2 or "nope.x" not in bad.stderr or bad.stdout:
        problems.append(f"get: missing key must exit 2 on stderr, got {bad.returncode}")
    return problems


def open_items_lists_pending_actions() -> list[str]:
    """`--open` derives what still demands action mechanically without running an audit:
    findings without dispositions, open defects with days left on accepted risks,
    acceptance criteria not yet signed, deferred changes, and runnable commands.
    Asserts both the human-readable text and the --json keys and contents."""
    problems = []
    today = "2026-10-15"
    base = [sys.executable, str(AUDIT), str(FIXTURES / "open-items"),
            "--repo-root", str(FIXTURES / "open-items"), "--today", today]

    out_text = subprocess.run(base + ["--open"], capture_output=True, text=True)
    if out_text.returncode != 0:
        problems.append(f"open-items: --open exited {out_text.returncode}: {out_text.stderr}")
    text = out_text.stdout

    if "R4-F1" not in text or "R2-F1" in text or "R2-F2" in text or "R4-F2" in text or "R4-F3" in text:
        problems.append("open-items: text output must list exactly R4-F1 as open finding")
    if "R2-F3: como riesgo aceptado. Needs mock server" not in text or "**" in text.split("## Defects open")[0]:
        problems.append("open-items: text output must list R2-F3 under deferred findings with no '**' in waiting_on")
    if "defects.D1" not in text or "10 days left" not in text or "defects.D2" in text:
        problems.append("open-items: text output must list open defect D1 with 10 days left and not fixed D2")
    if "acceptance.AC2" not in text or "acceptance.AC1" in text:
        problems.append("open-items: text output must list written criterion AC2 and not approved AC1")
    risks_block = text.split("## Accepted risks due")[1].split("## Acceptance criteria")[0]
    if "AC2: 1 attempt, last 2026-10-12 aborted_no_conditions — sin servidor mock en staging" not in risks_block:
        problems.append("open-items: the risk D1 must list AC2's blocked attempt under it, as the audit does")
    if "acceptance.AC2 — status: written · closes D1 · 1 attempt ·" not in text:
        problems.append("open-items: the unsigned criterion AC2 must say it closes D1 and carries 1 attempt")
    if "changes.C1" not in text:
        problems.append("open-items: text output must list deferred change C1")

    out_json = subprocess.run(base + ["--open", "--json"], capture_output=True, text=True)
    if out_json.returncode != 0:
        problems.append(f"open-items: --open --json exited {out_json.returncode}: {out_json.stderr}")
    else:
        try:
            data = json.loads(out_json.stdout)
            want_keys = {"status", "tracking", "findings_open", "findings_deferred",
                         "defects_open", "accepted_risks_due", "acceptance_unsigned",
                         "changes_deferred", "ship_ready", "scripts"}
            if set(data.keys()) != want_keys:
                problems.append(f"open-items: --json keys {sorted(data.keys())} != {sorted(want_keys)}")
            if [f["id"] for f in data.get("findings_open", [])] != ["R4-F1"]:
                problems.append(f"open-items: --json findings_open != ['R4-F1']: {data.get('findings_open')}")
            deferred_items = data.get("findings_deferred", [])
            if [f["id"] for f in deferred_items] != ["R2-F3"]:
                problems.append(f"open-items: --json findings_deferred != ['R2-F3']: {deferred_items}")
            elif "**" in deferred_items[0].get("waiting_on", ""):
                problems.append(f"open-items: --json R2-F3 waiting_on carries '**': {deferred_items[0].get('waiting_on')}")
            if [d["id"] for d in data.get("defects_open", [])] != ["D1"]:
                problems.append(f"open-items: --json defects_open != ['D1']: {data.get('defects_open')}")
            if [r["id"] for r in data.get("accepted_risks_due", [])] != ["D1"]:
                problems.append(f"open-items: --json accepted_risks_due != ['D1']: {data.get('accepted_risks_due')}")
            elif [c["id"] for c in data["accepted_risks_due"][0].get("closing_criteria", [])] != ["AC2"]:
                problems.append(f"open-items: --json accepted_risks_due[0].closing_criteria != ['AC2']: {data['accepted_risks_due'][0]}")
            if [a["id"] for a in data.get("acceptance_unsigned", [])] != ["AC2"]:
                problems.append(f"open-items: --json acceptance_unsigned != ['AC2']: {data.get('acceptance_unsigned')}")
            if [c["id"] for c in data.get("changes_deferred", [])] != ["C1"]:
                problems.append(f"open-items: --json changes_deferred != ['C1']: {data.get('changes_deferred')}")
        except json.JSONDecodeError as exc:
            problems.append(f"open-items: --json did not return valid JSON: {exc}")
        else:
            d1 = (data.get("defects_open") or [{}])[0].get("sections")
            if not d1 or len(d1) != 5 or set(d1[0]) != {"file", "start", "own_end", "end", "title", "maybe"}:
                problems.append(f"open-items: --json defects_open[0].sections: {d1}")
            elif (d1[1]["file"], d1[1]["start"], d1[1]["own_end"], d1[1]["title"]) != ("02-detail.md", 3, 6, "Reintentos"):
                problems.append(f"open-items: --json D1 second section wrong: {d1[1]}")
            ac2 = (data.get("acceptance_unsigned") or [{}])[0].get("sections")
            if not ac2 or [r["title"] for r in ac2][-1] != "Cierre del riesgo":
                problems.append(f"open-items: --json AC2 sections: {ac2}")
            if (data.get("changes_deferred") or [{}])[0].get("sections") != []:
                problems.append("open-items: --json uncited C1 must have sections: []")

    # `in:` lines: first 3 sections, then (+N more); uncited says so
    if "      in: 01-master-plan.md L1-4; 02-detail.md L3-6, L11-14 (+2 more)" not in text:
        problems.append("open-items: D1 must list 3 sections then '(+2 more)' on an 'in:' line")
    if "      in: 01-master-plan.md L1-4; 02-detail.md L7-10" not in text:
        problems.append("open-items: AC2 'in:' line missing or wrong")
    if "changes.C1" in text and "      in: not cited in any doc" not in text:
        problems.append("open-items: uncited C1 must say 'in: not cited in any doc'")
    if "R4-F1" in text and any("in:" in l for l in text.splitlines() if "R4-F1" in l or "R2-F3" in l):
        problems.append("open-items: findings must not carry an 'in:' line")

    out_c = subprocess.run(base + ["--open", "--compact"], capture_output=True, text=True)
    if out_c.returncode != 0 or "      in:" in out_c.stdout:
        problems.append("open-items: --compact must have no 'in:' lines")
    elif ("· 5 sections" not in out_c.stdout or "· 2 sections" not in out_c.stdout
          or not any(l.startswith("  changes.C1 (src/cache.ts) — reopens when: cuando")
                     and l.endswith("· not cited") for l in out_c.stdout.splitlines())):
        problems.append(f"open-items: --compact counts wrong:\n{out_c.stdout}")
    # the 80 covers the whole item line (id, status, text, suffix), not only the text:
    # real case, acceptance lines came out at 123 characters
    long_items = [l for l in out_c.stdout.splitlines()
                  if l.startswith("  ") and " · " in l and len(l) > 80]
    if long_items:
        problems.append(f"open-items: --compact item lines over 80: {long_items}")

    return problems


def baseline_counts_only_new() -> list[str]:
    problems = []
    with tempfile.TemporaryDirectory() as tmp:
        t_path = Path(tmp)
        spec = t_path / "spec"
        shutil.copytree(FIXTURES / "baseline-drift", spec)
        shutil.copy(FIXTURES / "_profile.fixture.yml", t_path / "_profile.fixture.yml")
        b_json = t_path / "b.json"

        out = subprocess.run([sys.executable, str(AUDIT), str(spec), "--repo-root", str(t_path), "--json"],
                             capture_output=True, text=True)
        if out.returncode != 0:
            problems.append(f"baseline precondition: expected exit 0, got {out.returncode}")
        try:
            data = json.loads(out.stdout)
            findings = data.get("findings", [])
            if len(findings) != 2:
                problems.append(f"baseline precondition: expected 2 findings, got {len(findings)}")
            elif not all(f["severity"] == "DRIFT" and f["check"].startswith("16") for f in findings):
                problems.append("baseline precondition: expected both findings to be check 16 DRIFT")
        except json.JSONDecodeError as exc:
            problems.append(f"baseline precondition: invalid json: {exc}")

        w1 = subprocess.run([sys.executable, str(AUDIT), str(spec), "--repo-root", str(t_path),
                             "--write-baseline", str(b_json)], capture_output=True, text=True)
        if w1.returncode != 0:
            problems.append(f"--write-baseline exited {w1.returncode}: {w1.stderr}")
        content1 = b_json.read_bytes()
        try:
            b_data = json.loads(content1)
            if len(b_data.get("findings", [])) != 2:
                problems.append(f"--write-baseline expected 2 entries, got {len(b_data.get('findings', []))}")
        except json.JSONDecodeError as exc:
            problems.append(f"--write-baseline file not valid JSON: {exc}")

        w2 = subprocess.run([sys.executable, str(AUDIT), str(spec), "--repo-root", str(t_path),
                             "--write-baseline", str(b_json)], capture_output=True, text=True)
        if w2.returncode != 0:
            problems.append(f"--write-baseline rewrite exited {w2.returncode}: {w2.stderr}")
        content2 = b_json.read_bytes()
        if content1 != content2:
            problems.append("--write-baseline rewrite did not yield identical bytes")

        log_file = spec / "_log.md"
        log_file.write_text("\n" + log_file.read_text(encoding="utf-8"), encoding="utf-8")
        doc_file = spec / "01-master-plan.md"
        doc_file.write_text(doc_file.read_text(encoding="utf-8") + "extra\n", encoding="utf-8")

        r0 = subprocess.run([sys.executable, str(AUDIT), str(spec), "--repo-root", str(t_path),
                             "--baseline", str(b_json)], capture_output=True, text=True)
        if r0.returncode != 0:
            problems.append(f"--baseline volatile shift exited {r0.returncode}: {r0.stderr}")
        last_line = r0.stdout.strip().splitlines()[-1] if r0.stdout.strip() else ""
        if "0 new / 2 baseline" not in last_line:
            problems.append(f"--baseline volatile shift verdict expected '0 new / 2 baseline', got {last_line!r}")

        notes_file = spec / "notes.md"
        notes_file.write_text("# notes\n", encoding="utf-8")

        r1 = subprocess.run([sys.executable, str(AUDIT), str(spec), "--repo-root", str(t_path),
                             "--baseline", str(b_json)], capture_output=True, text=True)
        if r1.returncode != 1:
            problems.append(f"--baseline with notes.md expected exit 1, got {r1.returncode}")
        last_line1 = r1.stdout.strip().splitlines()[-1] if r1.stdout.strip() else ""
        if "1 new / 2 baseline" not in last_line1:
            problems.append(f"--baseline with notes.md verdict expected '1 new / 2 baseline', got {last_line1!r}")

        r1_json = subprocess.run([sys.executable, str(AUDIT), str(spec), "--repo-root", str(t_path),
                                  "--baseline", str(b_json), "--json"], capture_output=True, text=True)
        if r1_json.returncode != 1:
            problems.append(f"--baseline --json with notes.md expected exit 1, got {r1_json.returncode}")
        try:
            j1 = json.loads(r1_json.stdout)
            b_info = j1.get("baseline", {})
            if b_info.get("new") != 1 or b_info.get("baseline") != 2 or b_info.get("gone") != 0:
                problems.append(f"--baseline --json expected new=1, baseline=2, gone=0, got {b_info}")
            new_f = [f for f in j1.get("findings", []) if f.get("baseline") is False]
            if len(new_f) != 1 or not new_f[0]["check"].startswith("9"):
                problems.append(f"--baseline --json expected 1 new finding with check 9, got {new_f}")
        except json.JSONDecodeError as exc:
            problems.append(f"--baseline --json invalid json: {exc}")

        w3 = subprocess.run([sys.executable, str(AUDIT), str(spec), "--repo-root", str(t_path),
                             "--write-baseline", str(b_json)], capture_output=True, text=True)
        if w3.returncode != 0:
            problems.append(f"--write-baseline with 3 findings exited {w3.returncode}: {w3.stderr}")
        notes_file.unlink()

        r2 = subprocess.run([sys.executable, str(AUDIT), str(spec), "--repo-root", str(t_path),
                             "--baseline", str(b_json)], capture_output=True, text=True)
        if r2.returncode != 0:
            problems.append(f"--baseline after removing notes.md expected exit 0, got {r2.returncode}")
        last_line2 = r2.stdout.strip().splitlines()[-1] if r2.stdout.strip() else ""
        if "0 new / 2 baseline, 1 gone" not in last_line2:
            problems.append(f"--baseline after removing notes.md expected '0 new / 2 baseline, 1 gone', got {last_line2!r}")

    return problems


def baseline_normalization_pairs() -> list[str]:
    sys.path.insert(0, str(ROOT / "scripts"))
    import audit

    problems = []
    # Must match:
    f1a = {"severity": "DRIFT", "check": "16 handoff log integrity", "where": "01-master-plan.md",
           "what": "last recorded at _log.md:4 as 7 lines, blob def5678; now 7 lines, blob c2d7bb6"}
    f1b = {"severity": "DRIFT", "check": "16 handoff log integrity", "where": "01-master-plan.md",
           "what": "last recorded at _log.md:5 as 7 lines, blob def5678; now 8 lines, blob 8491f95"}
    if audit.finding_fingerprint(f1a) != audit.finding_fingerprint(f1b):
        problems.append("normalization: check 16 line/blob variance should have matched")

    f2a = {"severity": "DRIFT", "check": "16 handoff log integrity", "where": "_log.md",
           "what": "570 lines, 106KB — past what one read can hold"}
    f2b = {"severity": "DRIFT", "check": "16 handoff log integrity", "where": "_log.md",
           "what": "701 lines, 103KB — past what one read can hold"}
    if audit.finding_fingerprint(f2a) != audit.finding_fingerprint(f2b):
        problems.append("normalization: check 16 log size variance should have matched")

    f3a = {"severity": "DRIFT", "check": "44 cross-set value parity", "where": "01-master-plan.md:73",
           "what": "cites `defects.D4` from `docs/features/app-set/_facts.yml` (now `ValidationException — … `list-models` … 11996 bytes …`) and this paragraph does not carry that value"}
    f3b = {"severity": "DRIFT", "check": "44 cross-set value parity", "where": "01-master-plan.md:80",
           "what": "cites `defects.D4` from `docs/features/app-set/_facts.yml` (now `other value without backticks`) and this paragraph does not carry that value"}
    if audit.finding_fingerprint(f3a) != audit.finding_fingerprint(f3b):
        problems.append("normalization: check 44 value and line variance should have matched")

    f4a = {"severity": "POLISH", "check": "17 doc size", "where": "01-master-plan.md:73", "what": "something"}
    f4b = {"severity": "POLISH", "check": "17 doc size", "where": "01-master-plan.md:80", "what": "something"}
    if audit.finding_fingerprint(f4a) != audit.finding_fingerprint(f4b):
        problems.append("normalization: line number in where should have matched")

    # Must NOT match:
    f5a = {"severity": "DRIFT", "check": "16 handoff log integrity", "where": "_log.md",
           "what": "`R10` read `_facts.yml` at 633 lines, blob 857ce36; `R9` left it at 634 lines, blob 882d1ff — edited between rounds"}
    f5b = {"severity": "DRIFT", "check": "16 handoff log integrity", "where": "_log.md",
           "what": "`R11` read `_facts.yml` at 633 lines, blob 857ce36; `R9` left it at 634 lines, blob 882d1ff — edited between rounds"}
    if audit.finding_fingerprint(f5a) == audit.finding_fingerprint(f5b):
        problems.append("normalization: R10 vs R11 round ids should NOT match")

    f6a = {"severity": "DRIFT", "check": "44 cross-set value parity", "where": "01-master-plan.md",
           "what": "cites `defects.D4` from `docs/features/app-set/_facts.yml` (now `val`) and this paragraph does not carry that value"}
    f6b = {"severity": "DRIFT", "check": "44 cross-set value parity", "where": "01-master-plan.md",
           "what": "cites `defects.D5` from `docs/features/app-set/_facts.yml` (now `val`) and this paragraph does not carry that value"}
    if audit.finding_fingerprint(f6a) == audit.finding_fingerprint(f6b):
        problems.append("normalization: defects.D4 vs defects.D5 should NOT match")

    f7a = {"severity": "DRIFT", "check": "18 anchor", "where": "01.md", "what": "text"}
    f7b = {"severity": "CONTRADICTION", "check": "18 anchor", "where": "01.md", "what": "text"}
    if audit.finding_fingerprint(f7a) == audit.finding_fingerprint(f7b):
        problems.append("normalization: DRIFT vs CONTRADICTION should NOT match")

    f8a = {"severity": "DRIFT", "check": "18 anchor", "where": "01-master-plan.md", "what": "text"}
    f8b = {"severity": "DRIFT", "check": "18 anchor", "where": "02-architecture.md", "what": "text"}
    if audit.finding_fingerprint(f8a) == audit.finding_fingerprint(f8b):
        problems.append("normalization: different files in where should NOT match")

    return problems


def baseline_fingerprints_do_not_collide() -> list[str]:
    sys.path.insert(0, str(ROOT / "scripts"))
    import audit

    problems = []
    for fixture, _, _ in CASES:
        findings = run(fixture)
        fps = [audit.finding_fingerprint(f) for f in findings]
        if len(fps) != len(set(fps)):
            seen = {}
            for f in findings:
                fp = audit.finding_fingerprint(f)
                if fp in seen:
                    problems.append(
                        f"{fixture}: fingerprint collision between {seen[fp]['where']}: {seen[fp]['what'][:40]!r} "
                        f"and {f['where']}: {f['what'][:40]!r}")
                seen[fp] = f
    return problems


def baseline_flag_errors() -> list[str]:
    problems = []
    fix = FIXTURES / "matrix"

    nonexistent = str(fix / "does_not_exist_baseline.json")
    r1 = subprocess.run([sys.executable, str(AUDIT), str(fix), "--baseline", nonexistent],
                        capture_output=True, text=True)
    if r1.returncode != 2:
        problems.append(f"--baseline nonexistent file expected exit 2, got {r1.returncode}")
    if nonexistent not in r1.stderr:
        problems.append(f"--baseline nonexistent file stderr did not name file: {r1.stderr}")

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tf:
        tf.write(json.dumps({"findings": []}))
        tf_name = tf.name
    try:
        r2 = subprocess.run([sys.executable, str(AUDIT), str(fix), "--baseline", tf_name],
                            capture_output=True, text=True)
        if r2.returncode != 2:
            problems.append(f"--baseline JSON without audit_baseline expected exit 2, got {r2.returncode}")
    finally:
        Path(tf_name).unlink(missing_ok=True)

    r3 = subprocess.run([sys.executable, str(AUDIT), str(fix), "--baseline", "b.json", "--write-baseline", "w.json"],
                        capture_output=True, text=True)
    if r3.returncode != 2:
        problems.append(f"--baseline with --write-baseline expected exit 2, got {r3.returncode}")

    r4 = subprocess.run([sys.executable, str(AUDIT), str(fix), "--write-baseline", "w.json", "--as-status", "shipped"],
                        capture_output=True, text=True)
    if r4.returncode != 2:
        problems.append(f"--write-baseline with --as-status shipped expected exit 2, got {r4.returncode}")

    r5 = subprocess.run([sys.executable, str(AUDIT), str(fix), "--baseline", "b.json", "--open"],
                        capture_output=True, text=True)
    if r5.returncode != 2:
        problems.append(f"--baseline with --open expected exit 2, got {r5.returncode}")

    r6 = subprocess.run([sys.executable, str(AUDIT), str(fix), "--baseline", "b.json", "--rotate-plan"],
                        capture_output=True, text=True)
    if r6.returncode != 2:
        problems.append(f"--baseline with --rotate-plan expected exit 2, got {r6.returncode}")

    return problems


def baseline_default_json_shape() -> list[str]:
    problems = []
    out = subprocess.run([sys.executable, str(AUDIT), str(FIXTURES / "anchor-drift"), "--json"],
                         capture_output=True, text=True)
    try:
        data = json.loads(out.stdout)
        if data.get("baseline") is not None:
            problems.append(f"--json without flags: expected baseline is null, got {data.get('baseline')}")
        findings = data.get("findings", [])
        if not findings:
            problems.append("--json without flags: anchor-drift expected findings")
        for f in findings:
            if "fingerprint" not in f or not isinstance(f["fingerprint"], str) or len(f["fingerprint"]) != 16:
                problems.append(f"--json without flags: finding missing 16-char fingerprint: {f}")
            if "baseline" in f:
                problems.append(f"--json without flags: finding unexpectedly has baseline key: {f}")
    except json.JSONDecodeError as exc:
        problems.append(f"--json without flags invalid json: {exc}")
    return problems


def rotate_plan_round_trips() -> list[str]:
    """`--rotate-plan` prints the cut, archive name, stage carry and exact shell
    commands to rotate _log.md without losing a byte or summarizing."""
    problems = []
    with tempfile.TemporaryDirectory() as tmp:
        spec = Path(tmp) / "matrix"
        shutil.copytree(FIXTURES / "matrix", spec)
        base = [sys.executable, str(AUDIT), str(spec), "--repo-root", str(spec)]

        preamble = (
            "# Handoff log — matrix\n\n"
            "Append-only log for matrix feature.\n"
        )
        assert preamble.count("\n") == 3

        entries = []
        for i in range(37, 92):
            extra = "**Stage:** draft → reviewed\n" if i == 40 else ""
            entries.append(
                f"## R{i} · 2026-09-30 · test · review\n"
                f"**Read:** none\n"
                f"**Log read through:** R{i - 1}\n"
                f"{extra}"
                + "x" * 1500 + "\n\n"
            )
        # R92 as two headings
        entries.append(
            "## R92-W1 · 2026-09-30 · test · review\n"
            "**Read:** none\n"
            "**Log read through:** R91\n"
            + "x" * 750 + "\n\n"
        )
        entries.append(
            "## R92-W2 · 2026-09-30 · test · review\n"
            "**Read:** none\n"
            "**Log read through:** R91\n"
            + "x" * 750 + "\n\n"
        )
        for i in range(93, 97):
            entries.append(
                f"## R{i} · 2026-09-30 · test · review\n"
                f"**Read:** none\n"
                f"**Log read through:** R{i - 1}\n"
                + "x" * 1500 + "\n\n"
            )

        orig_log = preamble + "".join(entries)
        (spec / "_log.md").write_text(orig_log, encoding="utf-8")

        # 1. Run --rotate-plan
        plan_res = subprocess.run(base + ["--rotate-plan", "--today", "2026-10-26"],
                                  capture_output=True, text=True)
        if plan_res.returncode != 0:
            problems.append(f"rotate_plan_round_trips: expected exit 0, got {plan_res.returncode}: {plan_res.stderr}")
            return problems
        plan_out = plan_res.stdout

        if "_log-R37-R91.md" not in plan_out:
            problems.append("rotate_plan_round_trips: plan did not name _log-R37-R91.md")
        if "before `## R92-W1" not in plan_out:
            problems.append("rotate_plan_round_trips: plan cut did not cut before ## R92-W1")
        if "## R92-W2" in plan_out:
            problems.append("rotate_plan_round_trips: plan cut wrongly named R92-W2")
        if "last 5 rounds kept" not in plan_out:
            problems.append("rotate_plan_round_trips: plan did not report fallback branch")
        if "**Stage:** reviewed → reviewed — carried" not in plan_out:
            problems.append("rotate_plan_round_trips: plan did not print reviewed -> reviewed carry line")

        # Extract fenced sh block
        m_sh = re.search(r"```sh\n(.*?)\n```", plan_out, re.S)
        if not m_sh:
            problems.append("rotate_plan_round_trips: no ```sh fenced block found in output")
            return problems
        sh_cmd = m_sh.group(1)

        # 2. Run sh commands in temp dir
        sh_res = subprocess.run(["sh", "-c", sh_cmd], capture_output=True, text=True)
        if sh_res.returncode != 0 or "rotated" not in sh_res.stdout:
            problems.append(f"rotate_plan_round_trips: sh execution failed (rc={sh_res.returncode}): {sh_res.stdout} {sh_res.stderr}")

        archive_file = spec / "_log-R37-R91.md"
        if not archive_file.is_file():
            problems.append("rotate_plan_round_trips: archive file was not created")
        else:
            arch_lines = archive_file.read_text(encoding="utf-8").splitlines(keepends=True)
            arch_body = "".join(arch_lines[8:])
            kept_text = (spec / "_log.md").read_text(encoding="utf-8")
            kept_lines = kept_text.splitlines(keepends=True)
            kept_preamble = "".join(kept_lines[:3])
            kept_rounds = "".join(kept_lines[3:])
            reconstructed = kept_preamble + arch_body + kept_rounds
            if reconstructed != orig_log:
                problems.append("rotate_plan_round_trips: preamble + archive body + kept rounds != original log")

        # 3. Audit check
        audit_res = subprocess.run(base + ["--json"], capture_output=True, text=True)
        audit_data = json.loads(audit_res.stdout)
        if any("past what one read" in f.get("what", "") for f in audit_data["findings"]):
            problems.append("rotate_plan_round_trips: audit still reports log size after rotation")

        # Append rotate entry
        rl_res = subprocess.run(base + ["--read-line", "_log-R37-R91.md"],
                                capture_output=True, text=True).stdout.strip()
        m_stage = re.search(r"(\*\*Stage:\*\* [^\n`]+)", plan_out)
        stage_line = m_stage.group(1) if m_stage else ""
        rotate_entry = (
            f"\n## R97 · 2026-10-26 · test · rotate\n"
            f"{rl_res}\n"
            f"**Log read through:** R96\n"
            f"{stage_line}\n"
            f"**Archived:** `_log-R37-R91.md`\n"
            f"**Edits:** `_log-R37-R91.md`\n"
        )
        with (spec / "_log.md").open("a", encoding="utf-8") as f:
            f.write(rotate_entry)

        audit_res2 = subprocess.run(base + ["--json"], capture_output=True, text=True)
        audit_data2 = json.loads(audit_res2.stdout)
        stage_drifts = [f for f in audit_data2["findings"] if f["check"].startswith("16") and "Stage:" in f.get("what", "")]
        if stage_drifts:
            problems.append(f"rotate_plan_round_trips: check 16 reports Stage findings after rotate entry: {stage_drifts}")

        # 4. Stale plan test
        (spec / "_log.md").write_text(orig_log, encoding="utf-8")
        if archive_file.exists():
            archive_file.unlink()
        (spec / "_log.md.kept").unlink(missing_ok=True)

        stale_log = preamble + "inserted line\n" + "".join(entries)
        (spec / "_log.md").write_text(stale_log, encoding="utf-8")

        stale_res = subprocess.run(["sh", "-c", sh_cmd], capture_output=True, text=True)
        if stale_res.returncode == 0:
            problems.append("rotate_plan_round_trips: stale plan commands should have failed")
        if (spec / "_log.md").read_text(encoding="utf-8") != stale_log:
            problems.append("rotate_plan_round_trips: stale plan commands modified _log.md")
        if archive_file.exists():
            problems.append("rotate_plan_round_trips: stale plan commands created archive file")
        if (spec / "_log.md.kept").exists():
            problems.append("rotate_plan_round_trips: stale plan commands created _log.md.kept")

        # 5. Name taken test
        (spec / "_log.md").write_text(orig_log, encoding="utf-8")
        archive_file.write_text("existing content", encoding="utf-8")
        taken_res = subprocess.run(base + ["--rotate-plan"], capture_output=True, text=True)
        if taken_res.returncode == 0:
            problems.append("rotate_plan_round_trips: plan should fail when archive name is taken")
        if "_log-R37-R91.md" not in (taken_res.stdout + taken_res.stderr):
            problems.append("rotate_plan_round_trips: error message did not name taken archive file")
        if "```sh" in taken_res.stdout or "```sh" in taken_res.stderr:
            problems.append("rotate_plan_round_trips: commands should not be printed when archive name is taken")

    return problems


def rotate_plan_quotes_paths() -> list[str]:
    """The printed `sh` block is pasted into a shell, so the spec dir must be quoted.
    Real case: iCloud vault paths carry spaces (`Mobile Documents`), and a folder
    name holding `$(…)` would run when the plan is pasted (security review of v1.21.0)."""
    problems = []
    with tempfile.TemporaryDirectory() as tmp:
        spec = Path(tmp) / "has space $(touch PWNED)" / "matrix"
        shutil.copytree(FIXTURES / "matrix", spec)
        entries = "".join(
            f"## R{i} · 2026-09-30 · test · review\n**Read:** none\n"
            f"**Log read through:** R{i - 1}\n" + "x" * 1500 + "\n\n"
            for i in range(37, 97))
        log = spec / "_log.md"
        log.write_text("# Handoff log — matrix\n\nAppend-only log.\n" + entries,
                       encoding="utf-8")
        original = log.read_bytes()
        res = subprocess.run([sys.executable, str(AUDIT), str(spec), "--repo-root",
                              str(spec), "--rotate-plan"], capture_output=True, text=True)
        block = re.search(r"^```sh\n(.*?)^```$", res.stdout, re.S | re.M)
        if res.returncode != 0 or not block:
            return [f"rotate_plan_quotes_paths: no plan (exit {res.returncode}): {res.stderr[:200]}"]
        run_ = subprocess.run(["sh", "-c", block.group(1)], capture_output=True,
                              text=True, cwd=tmp)
        if "rotated" not in run_.stdout:
            problems.append(f"rotate_plan_quotes_paths: commands failed: {run_.stderr[:200]}")
        if any(Path(tmp).rglob("PWNED")):
            problems.append("rotate_plan_quotes_paths: `$(…)` in the path was executed")
        archive = next(spec.glob("_log-R*.md"), None)
        if archive is None:
            problems.append("rotate_plan_quotes_paths: no archive written")
        else:
            kept = log.read_bytes().splitlines(keepends=True)
            body = archive.read_bytes().splitlines(keepends=True)[8:]
            if b"".join(kept[:3] + body + kept[3:]) != original:
                problems.append("rotate_plan_quotes_paths: reassembly != original bytes")
    return problems


def rotate_plan_cut_rule() -> list[str]:
    """`--rotate-plan` cut rule: keeps from last real Stage transition when it fits
    the budget, and exits 0 with nothing to rotate when under both limits."""
    problems = []
    with tempfile.TemporaryDirectory() as tmp:
        spec = Path(tmp) / "matrix"
        shutil.copytree(FIXTURES / "matrix", spec)
        base = [sys.executable, str(AUDIT), str(spec), "--repo-root", str(spec)]

        preamble = (
            "# Handoff log — matrix\n\n"
            "Append-only log for matrix feature.\n"
        )
        entries = []
        for i in range(37, 97):
            extra = "**Stage:** draft → reviewed\n" if i == 90 else ""
            entries.append(
                f"## R{i} · 2026-09-30 · test · review\n"
                f"**Read:** none\n"
                f"**Log read through:** R{i - 1}\n"
                f"{extra}"
                + "x" * 1500 + "\n\n"
            )

        (spec / "_log.md").write_text(preamble + "".join(entries), encoding="utf-8")

        res = subprocess.run(base + ["--rotate-plan"], capture_output=True, text=True)
        if res.returncode != 0:
            problems.append(f"rotate_plan_cut_rule: expected exit 0, got {res.returncode}: {res.stderr}")
        else:
            out = res.stdout
            if "before `## R90" not in out:
                problems.append(f"rotate_plan_cut_rule: plan did not cut at R90: {out[:200]}")
            if "_log-R37-R89.md" not in out:
                problems.append(f"rotate_plan_cut_rule: plan archive name != _log-R37-R89.md: {out[:200]}")
            if "stage:   carry" in out:
                problems.append("rotate_plan_cut_rule: plan should not print carry line when transition is kept")

        # 20-round log under limits
        under_entries = [
            f"## R{i} · 2026-09-30 · test · review\n"
            f"**Read:** none\n"
            f"**Log read through:** R{i - 1}\n"
            + "x" * 1500 + "\n\n"
            for i in range(1, 21)
        ]
        (spec / "_log.md").write_text(preamble + "".join(under_entries), encoding="utf-8")
        under_res = subprocess.run(base + ["--rotate-plan"], capture_output=True, text=True)
        if under_res.returncode != 0:
            problems.append(f"rotate_plan_cut_rule: under limits expected exit 0, got {under_res.returncode}")
        if "nothing to rotate" not in under_res.stdout:
            problems.append(f"rotate_plan_cut_rule: expected 'nothing to rotate', got: {under_res.stdout}")
        if "```sh" in under_res.stdout:
            problems.append("rotate_plan_cut_rule: under limits should have no sh block")

    return problems


def rotate_stub_nested_comments_open_in() -> list[str]:
    """Review fixes: the rotate stub must END in `· rotate` (an ordinary round that
    mentions the word is not one); nested `<!-- … <!-- … --> … -->` in the log's
    preamble hide their example headings; `--open`'s `in:` line lists sure cites before
    short-id guesses, and `--compact` counts sure ones, then `+ M maybe`."""
    problems = []
    with tempfile.TemporaryDirectory() as tmp:
        spec = Path(tmp) / "matrix"
        shutil.copytree(FIXTURES / "matrix", spec)
        base = [sys.executable, str(AUDIT), str(spec), "--repo-root", str(spec), "--rotate-plan"]
        entries = "".join(
            f"## R{i} · 2026-09-30 · test · review\n**Read:** none\n"
            f"**Log read through:** R{i - 1}\n" + "x" * 1500 + "\n\n" for i in range(37, 97))
        pre = "# Handoff log — matrix\n\nAppend-only log.\n"
        log = spec / "_log.md"

        def plan(text: str) -> str:
            log.write_text(text, encoding="utf-8")
            return subprocess.run(base + ["--today", "2026-10-26"], capture_output=True, text=True).stdout

        for head, want in (("## R97 · 2026-10-26 · test · rotate\n", True),
                           ("## R97 · 2026-10-26 · test · rotate — opened by hand\n", True),
                           ("## R97 · 2026-10-26 · test · review of the rotate flow\n", False),
                           ("## R97 · 2026-10-26 · test · rotate-check\n", False)):
            got = "rotate round already open" in plan(pre + entries + head)
            if got != want:
                problems.append(f"rotate-stub: {head.strip()!r} open={got}, want {want}")

        nested = ("<!--\n## R2 · example\n<!-- inner -->\n## R3 · example\n-->\n")
        out = plan(pre + nested + entries + "## R97 · 2026-10-26 · test · rotate\n")
        m = re.search(r"^archive: (\S+)", out, re.M)
        if not m or not m.group(1).startswith("_log-R37-"):
            problems.append(f"nested-comments: example heading counted as a round: {m and m.group(1)}")
        flat = pre + "<!--\n## R2 · example\n-->\n" + entries + "## R97 · 2026-10-26 · test · rotate\n"
        if plan(flat) != plan(flat):
            problems.append("nested-comments: output not stable")

    with tempfile.TemporaryDirectory() as tmp:
        spec = Path(tmp) / "open-items"
        shutil.copytree(FIXTURES / "open-items", spec)
        d = spec / "02-detail.md"
        d.write_text(d.read_text(encoding="utf-8").replace(
            "## Reintentos", "## Previo\n\nCloudflare D1 y nada mas.\n\n## Reintentos", 1), encoding="utf-8")
        f = spec / "_facts.yml"
        ft = f.read_text(encoding="utf-8")
        if "el fallback de red reintenta una sola vez" not in ft:
            problems.append("open-in: fixture AC2 item changed")
        f.write_text(ft.replace("el fallback de red reintenta una sola vez", "palabra " * 20), encoding="utf-8")
        cmd = [sys.executable, str(AUDIT), str(spec), "--repo-root", str(spec), "--today", "2026-10-15", "--open"]
        full = subprocess.run(cmd, capture_output=True, text=True).stdout
        d1 = next((l for l in full.splitlines() if l.startswith("      in: 01-master-plan.md")), "")
        if "(maybe)" in d1 or "(+3 more)" not in d1:
            problems.append(f"open-in: D1 line shows a maybe ahead of sure cites: {d1!r}")
        comp = subprocess.run(cmd + ["--compact"], capture_output=True, text=True).stdout
        if "· 5 sections + 1 maybe" not in comp:
            problems.append(f"open-in: compact does not count sure + maybe:\n{comp}")
        ac = next((l for l in comp.splitlines() if "acceptance.AC2" in l), "")
        tail = ac.split("1 attempt · ", 1)[-1]
        if len(tail) > 80 or "…" not in tail or not tail.endswith("sections"):
            problems.append(f"open-in: compact item text + suffix is {len(tail)} chars (>80) or unclipped: {tail!r}")
    return problems


def main() -> int:
    verbose = "-v" in sys.argv
    failures, total = [], 0
    total += 1
    failures += findings_group_without_loss()
    total += 1
    failures += baseline_counts_only_new()
    total += 1
    failures += baseline_normalization_pairs()
    total += 1
    failures += baseline_fingerprints_do_not_collide()
    total += 1
    failures += baseline_flag_errors()
    total += 1
    failures += baseline_default_json_shape()
    total += 1
    failures += open_items_lists_pending_actions()
    total += 1
    failures += compact_output_and_get()
    total += 1
    failures += registry_index_spans()
    total += 1
    failures += doc_index_spans_and_cites()
    failures += doc_index_synthetic_bugs()
    total += 1
    failures += log_size_counts_bytes()

    total += 1
    failures += accepted_risks_come_due()
    total += 1
    failures += ship_ready_is_counted()
    total += 1
    failures += next_tag_follows_the_registry()
    total += 1
    failures += acceptance_attempts_recorded()
    total += 1
    failures += matrix_is_counted()

    total += 1
    failures += read_line_round_trips()
    total += 1
    failures += edits_line_round_trips()
    total += 1
    failures += entry_stub_shape()
    total += 1
    failures += rotate_plan_round_trips()
    total += 1
    failures += rotate_plan_cut_rule()
    total += 1
    failures += rotate_stub_nested_comments_open_in()
    total += 1
    failures += rotate_plan_quotes_paths()
    total += 1
    failures += paths_resolve_on_the_spec_branch()
    total += 1
    failures += planned_landed_and_later_phases()
    total += 1
    failures += doc02_code_drift_modes()
    total += 1
    failures += profile_identity_survives_worktrees()
    total += 1
    failures += yaml_errors_name_their_position()
    for fixture, extra, expect, reject in FLAG_CASES:
        findings = run(fixture, extra)
        for check, text in expect:
            total += 1
            if not matches(findings, check, text):
                failures.append(f"{fixture} {' '.join(extra)}: check {check} did NOT "
                                f"report {text!r}")
        for check, text in reject:
            total += 1
            if matches(findings, check, text):
                failures.append(f"{fixture} {' '.join(extra)}: check {check} wrongly "
                                f"reported {text!r}")

    total += 1
    failures += human_pass_is_complete()
    total += 1
    failures += candidates_stay_out_of_findings()

    for fixture, expect, reject in CANDIDATE_CASES:
        candidates = run_candidates(fixture)
        for check, text in expect:
            total += 1
            if not cand_matches(candidates, check, text):
                failures.append(
                    f"{fixture}: check {check} did NOT offer {text!r} as a candidate")
        for check, text in reject:
            total += 1
            if cand_matches(candidates, check, text):
                failures.append(
                    f"{fixture}: check {check} wrongly offered {text!r} as a "
                    "candidate (known false positive — an over-reporting sweep "
                    "costs more tokens than the check saves)")
        if verbose:
            print(f"--- {fixture} (candidates)")
            for check, items in sorted(candidates.items()):
                for c in items:
                    print(f"      [{check}] {c['where']}: {c['what'][:80]}")

    for fixture, expect, reject in CASES:
        findings = run(fixture)
        for check, text in expect:
            total += 1
            if not matches(findings, check, text):
                failures.append(f"{fixture}: check {check} did NOT report {text!r}")
        for check, text in reject:
            total += 1
            if matches(findings, check, text):
                failures.append(
                    f"{fixture}: check {check} wrongly reported {text!r} "
                    "(known false positive)")
        if verbose:
            print(f"--- {fixture} ({len(findings)} findings)")
            for f in findings:
                print(f"      [{f['check']}] {f['where']}: {f['what'][:80]}")

    print(f"\n{total - len(failures)}/{total} assertions passed "
          f"across {len({c[0] for c in CASES + CANDIDATE_CASES + FLAG_CASES})} "
          "fixtures")
    for f in failures:
        print(f"  FAIL {f}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
