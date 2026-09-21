#!/usr/bin/env python3
"""triage.py's offline half — the part that must hold when nothing is installed.

The script's whole argument is that ranking is a layer and never a dependency:
`audit.py` computes the candidates offline, `triage.py` only reorders them, and a
machine with no SDK and no key still gets a complete list. That argument is only
worth the paragraph it is written in if the offline path is the tested one, so
every check below runs with ranking unavailable and no call is ever made.

Two claims carry the design and each gets a fixture:

  - `collect()` IMPORTS audit.py rather than re-deriving anything, so the candidate
    text here is the same object audit.py printed. A candidate described twice is
    the defect this skill exists to prevent, wearing a different hat — so the test
    is string identity against audit.py's own output, not a count.
  - nothing is hidden. `suppressed` is a heading, not a filter, and the fallback
    prints every candidate audit.py found. A threshold that drops one rebuilds the
    silent-skip failure `REQUIRES A HUMAN PASS` exists to close, one level down.

    python3 tests/test_triage.py [-v]
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
AUDIT = SCRIPTS / "audit.py"
TRIAGE = SCRIPTS / "triage.py"
FIXTURES = Path(__file__).resolve().parent / "fixtures"

sys.path.insert(0, str(SCRIPTS))
import triage  # noqa: E402

# One fixture per candidate generator, each the fixture that check already owns.
BY_CHECK = {
    "3": "contract-shape",
    "4": "cross-refs",
    "8": "prose-orphan",
    "13": "doc02-exec",
}

CANDIDATE_LINE = re.compile(r"^\s+·\s(?P<where>.+?): (?P<what>.+)$")
CHECK_HEADING = re.compile(r"^  check (?P<check>\S+)\s")


def run(script: Path, args: list[str], offline: bool = True) -> subprocess.CompletedProcess:
    """Run a script with ranking forced unavailable.

    HOME is redirected so `Setup` looks for the key file under an empty directory
    instead of the developer's own — a test whose result depends on whether the
    machine running it happens to have a key configured is not a test."""
    env = dict(os.environ)
    if offline:
        env.pop("TYPESAFE_API_KEY", None)
        env["HOME"] = tempfile.mkdtemp()
    return subprocess.run([sys.executable, str(script), *args],
                          capture_output=True, text=True, env=env)


def audit_candidates(fixture: str) -> dict[str, list[tuple[str, str]]]:
    """audit.py's own candidate lines, grouped under the check that printed them.

    Parsed out of the report rather than imported, deliberately: importing the
    generators here would compare triage.py against itself and prove nothing.
    What the reader sees in the audit is the thing triage.py must not change."""
    proc = run(AUDIT, [str(FIXTURES / fixture)])
    by_check: dict[str, list[tuple[str, str]]] = {}
    current = None
    for line in proc.stdout.splitlines():
        heading = CHECK_HEADING.match(line)
        if heading:
            current = heading["check"]
            continue
        m = CANDIDATE_LINE.match(line)
        if m and current:
            by_check.setdefault(current, []).append((m["where"], m["what"]))
    return by_check


def check_collect_matches_audit() -> list[str]:
    """`collect()` reports audit.py's candidates verbatim, not its own reading.

    Compared as SEQUENCES, both ways: a candidate audit.py printed and collect()
    missed is a check silently narrowed, and one collect() invented is a candidate
    no auditor reading the report would ever see. Order is part of it — the
    fallback's whole promise is that it prints the list in audit.py's order."""
    failures = []
    for check, fixture in BY_CHECK.items():
        _, _, cands = triage.collect(FIXTURES / fixture, None, [check])
        mine = [(c["where"], c["what"]) for c in cands.by_check.get(check, ())]
        theirs = audit_candidates(fixture).get(check, [])
        if not theirs:
            failures.append(f"check {check} ({fixture}): audit.py printed no "
                            f"candidates — the fixture no longer exercises it")
            continue
        if mine != theirs:
            missing = [c for c in theirs if c not in mine]
            extra = [c for c in mine if c not in theirs]
            detail = (f"missing {missing}" if missing else "") + \
                     (f" invented {extra}" if extra else "")
            failures.append(f"check {check} ({fixture}): collect() and audit.py "
                            f"disagree — {detail or 'same set, different order'}")
    return failures


def check_nothing_is_hidden() -> list[str]:
    """The fallback prints every candidate audit.py found, for every check."""
    failures = []
    for check, fixture in BY_CHECK.items():
        _, _, cands = triage.collect(FIXTURES / fixture, None, [check])
        expected = [c["where"] for c in cands.by_check.get(check, ())]
        proc = run(TRIAGE, ["--no-model", "--checks", check, str(FIXTURES / fixture)])
        for where in expected:
            if where not in proc.stdout:
                failures.append(f"check {check} ({fixture}): candidate {where} was "
                                f"computed but never printed — the fallback "
                                f"dropped one")
        if "Nothing is missing from the list below" not in proc.stdout:
            failures.append(f"check {check} ({fixture}): the fallback did not say "
                            f"the list is complete, so it reads as degraded")
    return failures


def check_bucket_boundaries() -> list[str]:
    """`keep` and `drop` are inclusive, and an unanswered candidate is uncertain.

    The boundaries matter because the buckets are not symmetric in consequence:
    a candidate that slides out of `keep` loses its place at the top of the list,
    and one that slides into `suppressed` is the one a reader skips last."""
    keep, drop = triage.DEFAULT_KEEP, triage.DEFAULT_DROP
    cases = [
        (1.0, "keep"), (keep, "keep"), (keep - 0.001, "uncertain"),
        (0.5, "uncertain"),
        (drop + 0.001, "uncertain"), (drop, "suppressed"), (0.0, "suppressed"),
        (None, "uncertain"),
    ]
    failures = []
    for p, want in cases:
        got = triage.bucket(p, keep, drop)
        if got != want:
            failures.append(f"bucket({p}) is {got!r}, expected {want!r}")
    return failures


def check_exit_codes_are_distinguishable() -> list[str]:
    """0, 1 and 2 mean three different things and a caller must be able to tell.

    A CI step that treats any non-zero as one case cannot distinguish "this
    machine has no ranking" from "I asked for ranking and did not get it"."""
    fixture = str(FIXTURES / BY_CHECK["4"])
    failures = []

    probe = run(TRIAGE, ["--check-setup", fixture])
    if probe.returncode != 1:
        failures.append(f"--check-setup with ranking unavailable exited "
                        f"{probe.returncode}, expected 1")
    for gap in ("typesafe-sdk", "API key"):
        if gap not in probe.stdout:
            failures.append(f"--check-setup did not report the {gap} gap — a user "
                            f"missing both must be told both, once")

    required = run(TRIAGE, ["--require-model", fixture])
    if required.returncode != 2:
        failures.append(f"--require-model with ranking unavailable exited "
                        f"{required.returncode}, expected 2")
    if required.stdout.strip():
        failures.append("--require-model printed a candidate list on stdout — it "
                        "refused to fall back, so there is nothing to print")

    offline = run(TRIAGE, ["--no-model", fixture])
    if offline.returncode != 0:
        failures.append(f"--no-model exited {offline.returncode}, expected 0 — the "
                        f"offline path is a supported state, not an error")
    if "Nothing was sent anywhere" not in offline.stdout:
        failures.append("--no-model did not say that nothing was sent anywhere")
    return failures


def check_every_generator_has_a_question() -> list[str]:
    """Each check reaches a question, and check 8's two shapes do not collide.

    Every question is phrased so that TRUE means the candidate is a real problem.
    One direction throughout is what lets a single pair of thresholds serve all
    four checks; a question that inverted would rank its worst candidates last."""
    failures = []
    cases = [("3", "fence keys"), ("4", "dangling ref"),
             ("8", "prose fence"), ("8", "bare url"), ("13", "open enumeration")]
    for check, what in cases:
        try:
            q = triage.build_question(check, "a line of prose", what)
        except KeyError:
            failures.append(f"check {check} ({what}) has no question")
            continue
        if not q.get("instructions", {}).get("question"):
            failures.append(f"check {check} ({what}): question text is empty")
        for verdict in ("true", "false"):
            if not q.get("criteria", {}).get(verdict):
                failures.append(f"check {check} ({what}): criteria.{verdict} is "
                                f"empty — the exempt shapes live there, and a "
                                f"model is only told what it is given")

    # Compared on the question text alone. The whole dict differs either way —
    # it embeds the candidate's own `what` — so comparing dicts would pass even
    # if both shapes were routed to the same question.
    fence = triage.build_question("8", "x", "prose fence")["instructions"]
    url = triage.build_question("8", "x", "bare url")["instructions"]
    if fence["question"] == url["question"]:
        failures.append("check 8's fence and URL candidates get the same question "
                        "— they are different shapes with different exemptions, "
                        "and the URL exemption names shapes a fence never has")

    if set(triage.GENERATORS) != {"3", "4", "8", "13"}:
        failures.append(f"GENERATORS drifted to {sorted(triage.GENERATORS)} — a new "
                        f"generator needs a question and a fixture here")
    try:
        triage.build_question("99", "x", "y")
        failures.append("build_question accepted an unknown check instead of "
                        "raising — an unranked candidate would rank as 0.5")
    except KeyError:
        pass
    return failures


def check_line_at_never_guesses() -> list[str]:
    """Out of range returns nothing rather than the wrong line.

    The candidate's line is quoted verbatim precisely because counting is the one
    thing the model is documented to get wrong. A helper that silently returned a
    neighbouring line would put that failure back, confidently."""
    text = "first\nsecond\nthird\n"
    failures = []
    for lineno, want in ((1, "first"), (3, "third"), (0, ""), (-1, ""), (4, "")):
        got = triage.line_at(text, lineno)
        if got != want:
            failures.append(f"line_at(..., {lineno}) is {got!r}, expected {want!r}")
    if triage.line_at("  indented  \n", 1) != "indented":
        failures.append("line_at did not strip the quoted line")
    return failures


def check_rejects_a_non_set() -> list[str]:
    """A directory with no `_facts.yml` is refused, not ranked as empty."""
    with tempfile.TemporaryDirectory() as tmp:
        proc = run(TRIAGE, ["--no-model", tmp])
    failures = []
    if proc.returncode == 0:
        failures.append("a directory with no _facts.yml exited 0 — an empty "
                        "candidate list reads as a clean set")
    if "not a feature-spec set" not in (proc.stderr + proc.stdout):
        failures.append("a directory with no _facts.yml gave no reason")
    return failures


def check_unknown_check_is_refused() -> list[str]:
    """`--checks 99` names no generator and must not silently rank nothing."""
    proc = run(TRIAGE, ["--no-model", "--checks", "99",
                        str(FIXTURES / BY_CHECK["4"])])
    failures = []
    if proc.returncode == 0:
        failures.append("--checks 99 exited 0 — a typo would report a clean set")
    if "no candidate generator" not in (proc.stderr + proc.stdout):
        failures.append("--checks 99 did not name the checks that do exist")

    bad = run(TRIAGE, ["--no-model", "--keep", "0.2", "--drop", "0.8",
                       str(FIXTURES / BY_CHECK["4"])])
    if bad.returncode == 0:
        failures.append("--drop above --keep exited 0 — every candidate would fall "
                        "in two buckets at once")
    return failures


CHECKS = (
    check_collect_matches_audit,
    check_nothing_is_hidden,
    check_bucket_boundaries,
    check_exit_codes_are_distinguishable,
    check_every_generator_has_a_question,
    check_line_at_never_guesses,
    check_rejects_a_non_set,
    check_unknown_check_is_refused,
)


def main() -> int:
    verbose = "-v" in sys.argv[1:]
    failures: list[str] = []
    for fn in CHECKS:
        # A check that raises is a failure, not the end of the run. The suite
        # reporting seven results and a traceback would hide whatever the other
        # checks had to say — the same silent-skip shape the script exists to close.
        try:
            f = fn()
        except Exception as exc:  # noqa: BLE001
            f = [f"{fn.__name__} raised {type(exc).__name__}: {exc}"]
        if verbose:
            print(f"{fn.__name__}: {'FAIL' if f else 'ok'}")
        failures += f

    if failures:
        print(f"\n{len(failures)} failure(s):")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"\n{len(CHECKS)}/{len(CHECKS)} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
