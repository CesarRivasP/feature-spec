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
]


def run(fixture: str) -> list[dict]:
    d = FIXTURES / fixture
    out = subprocess.run(
        [sys.executable, str(AUDIT), str(d), "--repo-root", str(d), "--json"],
        capture_output=True, text=True)
    if out.returncode not in (0, 1):
        raise AssertionError(f"{fixture}: audit.py crashed\n{out.stderr}")
    return json.loads(out.stdout)["findings"]


def matches(findings: list[dict], check: str, text: str) -> bool:
    return any(check in f["check"] and (text in f["what"] or text in f["where"])
               for f in findings)


def main() -> int:
    verbose = "-v" in sys.argv
    failures, total = [], 0
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
