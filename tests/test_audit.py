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
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AUDIT = ROOT / "scripts" / "audit.py"
FIXTURES = Path(__file__).resolve().parent / "fixtures"

# (fixture, expect[(check, text)], reject[(check, text)])
CASES: list[tuple[str, list[tuple[str, str]], list[tuple[str, str]]]] = [
    # §1.1 — five anchors moved by the author's own later edits; eight bare ones.
    ("anchor-drift",
     [("18", "chat.ts:341"), ("18", "bare anchor")],
     []),

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
      ("26", "AC4")],         # approved with no date
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
      ("33", "z6_positive")]),           # a real signal is not an absence

    # §2.2 — a changes[] entry depends_on a decision revised in place. C16 was never
    # reviewed since; C19 was reviewed, but before the revision — both stale. C17
    # was reviewed after; C18 depends on a decision nobody has touched — silent.
    ("changes-decision-revised",
     [("34", "C16"), ("34", "C19")],
     [("34", "C17"), ("34", "C18")]),

    # §15 — `app:` against a spec that genuinely lives in a subdirectory. `apps/consumer`
    # exists; it is simply not the one holding this spec. foreign-profile reports the
    # same finding for a weaker reason — its spec sits at the repo root, so `parts` is
    # empty and NO value of `app:` could have governed it. Here the comparison works.
    ("sibling-app/apps/mobile",
     [("15", "apps/consumer")],
     [("15", "but this checkout is")]),
]


# (fixture, expect[(check, text)], reject[(check, text)]) — CANDIDATES, not findings.
#
# A candidate is a mechanical hit on a check whose verdict needs a document read, so
# it carries no severity and never enters `## Findings`. For these four checks the
# `reject` column is the one that matters: an over-reporting sweep costs the reader
# more tokens than the check saves, which is the opposite of why it was mechanized.
CANDIDATE_CASES: list[tuple[str, list[tuple[str, str]], list[tuple[str, str]]]] = [
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
]


def run(fixture: str) -> list[dict]:
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
    root = FIXTURES / fixture.split("/", 1)[0]
    spec = FIXTURES / fixture
    out = subprocess.run(
        [sys.executable, str(AUDIT), str(spec), "--repo-root", str(root), "--json"],
        capture_output=True, text=True)
    if out.returncode not in (0, 1):
        raise AssertionError(f"{fixture}: audit.py crashed\n{out.stderr}")
    return json.loads(out.stdout)["findings"]


def run_candidates(fixture: str) -> dict[str, list[dict]]:
    root = FIXTURES / fixture.split("/", 1)[0]
    spec = FIXTURES / fixture
    out = subprocess.run(
        [sys.executable, str(AUDIT), str(spec), "--repo-root", str(root), "--json"],
        capture_output=True, text=True)
    if out.returncode not in (0, 1):
        raise AssertionError(f"{fixture}: audit.py crashed\n{out.stderr}")
    return json.loads(out.stdout).get("candidates", {})


def matches(findings: list[dict], check: str, text: str) -> bool:
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


def main() -> int:
    verbose = "-v" in sys.argv
    failures, total = [], 0

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
          f"across {len(CASES) + len(CANDIDATE_CASES)} fixtures")
    for f in failures:
        print(f"  FAIL {f}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
