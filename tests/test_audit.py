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

    # §15 — `app:` against a spec that genuinely lives in a subdirectory. `apps/consumer`
    # exists; it is simply not the one holding this spec. foreign-profile reports the
    # same finding for a weaker reason — its spec sits at the repo root, so `parts` is
    # empty and NO value of `app:` could have governed it. Here the comparison works.
    ("sibling-app/apps/mobile",
     [("15", "apps/consumer")],
     [("15", "but this checkout is")]),
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


def matches(findings: list[dict], check: str, text: str) -> bool:
    return any(check in f["check"] and (text in f["what"] or text in f["where"])
               for f in findings)


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
          f"across {len(CASES)} fixtures")
    for f in failures:
        print(f"  FAIL {f}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
