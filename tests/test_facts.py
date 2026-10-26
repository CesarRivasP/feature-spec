#!/usr/bin/env python3
"""test_facts.py — tests for scripts/facts.py add-attempt.

Seven cases:
  1. flow_append(): flow entry append with round, env, note and quotes
  2. rerun_is_identical(): idempotent rerun prints already recorded, same blob, zero writes
  3. edits_line_reads_back(): printed Edits line satisfies check 16 without drift
  4. other_shapes(): AC2 (flow empty), AC3 (block sequence), AC4 (block absent with comment)
  5. refusals(): unknown id, string criterion, aborted without reason, passed with reason,
                 date out of order, note drift on same attempt, approved with failed
  6. status_flag(): --status executed writes status and verified_on
  7. dry_writes_nothing(): --dry prints diff and leaves file untouched

    python3 tests/test_facts.py [-v]
"""
from __future__ import annotations

import datetime
import difflib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FACTS = ROOT / "scripts" / "facts.py"
AUDIT = ROOT / "scripts" / "audit.py"
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def copy_fixture(tmp: str) -> Path:
    dst = Path(tmp) / "facts-add-attempt"
    shutil.copytree(FIXTURES / "facts-add-attempt", dst)
    shutil.copy(FIXTURES / "_profile.fixture.yml", Path(tmp) / "_profile.fixture.yml")
    return dst


def run_facts(spec: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(FACTS), "add-attempt", str(spec), *args],
        capture_output=True,
        text=True,
    )


def run_audit(spec: Path) -> list[dict]:
    res = subprocess.run(
        [sys.executable, str(AUDIT), str(spec), "--repo-root", str(spec.parent), "--json"],
        capture_output=True,
        text=True,
    )
    if res.returncode not in (0, 1):
        raise AssertionError(f"audit.py crashed\n{res.stderr}")
    return json.loads(res.stdout).get("findings", [])


def check_26_findings_for(findings: list[dict], ac_id: str) -> list[dict]:
    return [
        f for f in findings
        if "26" in str(f.get("check", "")) and f.get("where") == f"acceptance.{ac_id}"
    ]


def flow_append() -> list[str]:
    problems = []
    with tempfile.TemporaryDirectory() as tmp:
        spec = copy_fixture(tmp)
        facts_file = spec / "_facts.yml"
        before_text = facts_file.read_text(encoding="utf-8")
        before_comments = [l for l in before_text.splitlines() if "#" in l]

        out = run_facts(
            spec,
            "AC1",
            "--date",
            "2026-10-26",
            "--round",
            "R9",
            "--outcome",
            "passed",
            "--env",
            "e",
            "--note",
            "it's",
        )
        if out.returncode != 0:
            return [f"flow_append: expected exit 0, got {out.returncode}\n{out.stderr}"]

        after_text = facts_file.read_text(encoding="utf-8")
        after_comments = [l for l in after_text.splitlines() if "#" in l]

        # All original comments preserved
        for c in before_comments:
            if c not in after_comments:
                problems.append(f"flow_append: comment line was lost: {c!r}")

        # Unified diff: at most 1 removed line, and that line is a prefix of an added line
        diff = list(difflib.unified_diff(before_text.splitlines(True), after_text.splitlines(True)))
        removed = [l[1:].rstrip("\r\n") for l in diff if l.startswith("-") and not l.startswith("---")]
        added = [l[1:].rstrip("\r\n") for l in diff if l.startswith("+") and not l.startswith("+++")]
        if len(removed) > 1:
            problems.append(f"flow_append: expected at most 1 removed line in diff, got {len(removed)}: {removed}")
        elif len(removed) == 1:
            if not any(a.startswith(removed[0]) for a in added):
                problems.append(f"flow_append: removed line {removed[0]!r} is not a prefix of any added line in {added}")

        # safe_load assertions
        sys.path.insert(0, str(ROOT / "scripts"))
        import yaml
        loaded = yaml.safe_load(after_text)
        acc1 = next((e for e in loaded.get("acceptance", []) if isinstance(e, dict) and e.get("id") == "AC1"), None)
        if not acc1:
            problems.append("flow_append: AC1 missing from loaded facts")
        else:
            attempts = acc1.get("attempts", [])
            if len(attempts) != 2:
                problems.append(f"flow_append: expected 2 attempts, got {len(attempts)}")
            else:
                last_att = attempts[-1]
                expected = {
                    "date": datetime.date(2026, 10, 26),
                    "round": "R9",
                    "outcome": "passed",
                    "env": "e",
                    "note": "it's",
                }
                if last_att != expected:
                    problems.append(f"flow_append: last attempt {last_att} != expected {expected}")

        # No check-26 finding added for acceptance.AC1
        findings = run_audit(spec)
        ac1_findings = check_26_findings_for(findings, "AC1")
        if ac1_findings:
            problems.append(f"flow_append: unexpected check-26 finding for AC1: {ac1_findings}")

    return problems


def rerun_is_identical() -> list[str]:
    problems = []
    with tempfile.TemporaryDirectory() as tmp:
        spec = copy_fixture(tmp)
        facts_file = spec / "_facts.yml"

        # First run
        out1 = run_facts(
            spec,
            "AC1",
            "--date",
            "2026-10-26",
            "--round",
            "R9",
            "--outcome",
            "passed",
            "--env",
            "e",
            "--note",
            "it's",
        )
        if out1.returncode != 0:
            return [f"rerun: run 1 failed with {out1.returncode}\n{out1.stderr}"]

        bytes1 = facts_file.read_bytes()
        m1 = re.search(r"^\*\*Edits:\*\* `_facts\.yml` \(\d+ lines, blob ([0-9a-f]{7})", out1.stdout, re.M)
        if not m1:
            problems.append(f"rerun: run 1 did not print valid Edits line:\n{out1.stdout}")

        # Second run (exact same arguments)
        out2 = run_facts(
            spec,
            "AC1",
            "--date",
            "2026-10-26",
            "--round",
            "R9",
            "--outcome",
            "passed",
            "--env",
            "e",
            "--note",
            "it's",
        )
        if out2.returncode != 0:
            problems.append(f"rerun: run 2 failed with {out2.returncode}\n{out2.stderr}")

        if "already recorded: acceptance[AC1].attempts[1]" not in out2.stdout:
            problems.append(f"rerun: run 2 did not print 'already recorded', got:\n{out2.stdout}")

        bytes2 = facts_file.read_bytes()
        if bytes1 != bytes2:
            problems.append("rerun: file bytes changed between first and second runs")

        m2 = re.search(r"^\*\*Edits:\*\* `_facts\.yml` \(\d+ lines, blob ([0-9a-f]{7})", out2.stdout, re.M)
        if not m2:
            problems.append(f"rerun: run 2 did not print valid Edits line:\n{out2.stdout}")
        elif m1 and m1.group(1) != m2.group(1):
            problems.append(f"rerun: blob changed between runs: {m1.group(1)} vs {m2.group(1)}")

    return problems


def edits_line_reads_back() -> list[str]:
    problems = []
    with tempfile.TemporaryDirectory() as tmp:
        spec = copy_fixture(tmp)
        out = run_facts(spec, "AC1", "--date", "2026-10-26", "--outcome", "passed")
        if out.returncode != 0:
            return [f"edits_line_reads_back: facts.py failed: {out.stderr}"]

        m = re.search(r"^(\*\*Edits:\*\* .*)$", out.stdout, re.M)
        if not m:
            return [f"edits_line_reads_back: no **Edits:** line in stdout:\n{out.stdout}"]
        edits_line = m.group(1)

        # Update _log.md to paste the new Edits line in a new round entry
        plan_stamp = re.search(r"(`01-master-plan\.md` [^)\n]+\))", (spec / "_log.md").read_text(encoding="utf-8"))
        p_stamp = f" · {plan_stamp.group(1)}" if plan_stamp else ""
        new_entry = (
            "\n## R2 · 2026-10-26 · claude-opus-5 · verify\n"
            "**Read:** `01-master-plan.md`\n"
            "**Log read through:** R1\n"
            f"{edits_line}{p_stamp}\n"
        )
        log_file = spec / "_log.md"
        log_file.write_text(log_file.read_text(encoding="utf-8") + new_entry, encoding="utf-8")

        # Check that check 16 has no "last recorded" finding for _facts.yml
        findings = run_audit(spec)
        check16_drift = [
            f for f in findings
            if "16" in str(f.get("check", ""))
            and "_facts.yml" in str(f.get("where", "")) + str(f.get("what", ""))
            and "last recorded" in str(f.get("what", ""))
        ]
        if check16_drift:
            problems.append(f"edits_line_reads_back: check 16 flagged drift after pasting edits line: {check16_drift}")

    return problems


def other_shapes() -> list[str]:
    problems = []
    import yaml

    # AC2: flow entry without attempts
    with tempfile.TemporaryDirectory() as tmp:
        spec = copy_fixture(tmp)
        before_text = (spec / "_facts.yml").read_text(encoding="utf-8")
        before_comments = [l for l in before_text.splitlines() if "#" in l]

        out = run_facts(spec, "AC2", "--date", "2026-10-26", "--outcome", "passed")
        if out.returncode != 0:
            problems.append(f"other_shapes AC2: exit {out.returncode}\n{out.stderr}")
        else:
            after_text = (spec / "_facts.yml").read_text(encoding="utf-8")
            for c in before_comments:
                if c not in after_text.splitlines():
                    problems.append(f"other_shapes AC2: lost comment {c!r}")
            loaded = yaml.safe_load(after_text)
            ac2 = next((e for e in loaded.get("acceptance", []) if isinstance(e, dict) and e.get("id") == "AC2"), None)
            if not ac2 or len(ac2.get("attempts", [])) != 1:
                problems.append(f"other_shapes AC2: expected 1 attempt, got {ac2}")
            findings = run_audit(spec)
            if check_26_findings_for(findings, "AC2"):
                problems.append(f"other_shapes AC2: unexpected check 26 findings: {check_26_findings_for(findings, 'AC2')}")

    # AC3: block entry with block attempts
    with tempfile.TemporaryDirectory() as tmp:
        spec = copy_fixture(tmp)
        before_text = (spec / "_facts.yml").read_text(encoding="utf-8")
        before_comments = [l for l in before_text.splitlines() if "#" in l]

        out = run_facts(spec, "AC3", "--date", "2026-10-26", "--round", "R10", "--outcome", "passed")
        if out.returncode != 0:
            problems.append(f"other_shapes AC3: exit {out.returncode}\n{out.stderr}")
        else:
            after_text = (spec / "_facts.yml").read_text(encoding="utf-8")
            for c in before_comments:
                if c not in after_text.splitlines():
                    problems.append(f"other_shapes AC3: lost comment {c!r}")
            loaded = yaml.safe_load(after_text)
            ac3 = next((e for e in loaded.get("acceptance", []) if isinstance(e, dict) and e.get("id") == "AC3"), None)
            if not ac3 or len(ac3.get("attempts", [])) != 2:
                problems.append(f"other_shapes AC3: expected 2 attempts, got {ac3}")
            findings = run_audit(spec)
            if check_26_findings_for(findings, "AC3"):
                problems.append(f"other_shapes AC3: unexpected check 26 findings: {check_26_findings_for(findings, 'AC3')}")

    # AC4: block entry with no attempts and trailing comment after status:
    with tempfile.TemporaryDirectory() as tmp:
        spec = copy_fixture(tmp)
        before_text = (spec / "_facts.yml").read_text(encoding="utf-8")
        before_comments = [l for l in before_text.splitlines() if "#" in l]

        out = run_facts(spec, "AC4", "--date", "2026-10-26", "--outcome", "passed")
        if out.returncode != 0:
            problems.append(f"other_shapes AC4: exit {out.returncode}\n{out.stderr}")
        else:
            after_text = (spec / "_facts.yml").read_text(encoding="utf-8")
            if "status: written # trailing comment after status" not in after_text:
                problems.append("other_shapes AC4: trailing comment after status was not preserved")
            for c in before_comments:
                if c not in after_text.splitlines():
                    problems.append(f"other_shapes AC4: lost comment {c!r}")
            loaded = yaml.safe_load(after_text)
            ac4 = next((e for e in loaded.get("acceptance", []) if isinstance(e, dict) and e.get("id") == "AC4"), None)
            if not ac4 or len(ac4.get("attempts", [])) != 1:
                problems.append(f"other_shapes AC4: expected 1 attempt, got {ac4}")
            findings = run_audit(spec)
            if check_26_findings_for(findings, "AC4"):
                problems.append(f"other_shapes AC4: unexpected check 26 findings: {check_26_findings_for(findings, 'AC4')}")

    return problems


def refusals() -> list[str]:
    problems = []

    cases = [
        # (name, [args], expected_error_fragment)
        ("unknown id", ["NONEXISTENT", "--date", "2026-10-26", "--outcome", "passed"], "no criterion with id"),
        ("AC5 string criterion", ["AC5", "--date", "2026-10-26", "--outcome", "passed"], "plain string"),
        ("aborted with no aborted-because", ["AC1", "--date", "2026-10-26", "--outcome", "aborted_no_conditions"], "--aborted-because is required"),
        ("aborted-because given with passed", ["AC1", "--date", "2026-10-26", "--outcome", "passed", "--aborted-because", "probe"], "only valid when outcome is aborted"),
        ("date older than last attempt", ["AC1", "--date", "2026-01-01", "--outcome", "passed"], "older than last attempt"),
        ("status approved with failed outcome", ["AC1", "--date", "2026-10-26", "--outcome", "failed", "--status", "approved"], "requires --outcome passed"),
    ]

    for name, extra_args, err_frag in cases:
        with tempfile.TemporaryDirectory() as tmp:
            spec = copy_fixture(tmp)
            before_bytes = (spec / "_facts.yml").read_bytes()

            out = run_facts(spec, *extra_args)
            if out.returncode != 2:
                problems.append(f"refusals ({name}): expected exit 2, got {out.returncode}\nstdout: {out.stdout}\nstderr: {out.stderr}")
            if err_frag not in out.stderr:
                problems.append(f"refusals ({name}): expected {err_frag!r} in stderr, got:\n{out.stderr}")
            after_bytes = (spec / "_facts.yml").read_bytes()
            if before_bytes != after_bytes:
                problems.append(f"refusals ({name}): file bytes were modified despite exit 2")

    # Same date/round/outcome but different note
    with tempfile.TemporaryDirectory() as tmp:
        spec = copy_fixture(tmp)
        run_facts(spec, "AC1", "--date", "2026-10-26", "--round", "R9", "--outcome", "passed", "--note", "original")
        before_bytes = (spec / "_facts.yml").read_bytes()

        out = run_facts(spec, "AC1", "--date", "2026-10-26", "--round", "R9", "--outcome", "passed", "--note", "different")
        if out.returncode != 2:
            problems.append(f"refusals (note conflict): expected exit 2, got {out.returncode}\n{out.stderr}")
        if "append-only" not in out.stderr:
            problems.append(f"refusals (note conflict): expected 'append-only' in stderr, got:\n{out.stderr}")
        after_bytes = (spec / "_facts.yml").read_bytes()
        if before_bytes != after_bytes:
            problems.append("refusals (note conflict): file bytes modified despite exit 2")

    return problems


def status_flag() -> list[str]:
    problems = []
    import yaml

    with tempfile.TemporaryDirectory() as tmp:
        spec = copy_fixture(tmp)
        out = run_facts(spec, "AC2", "--date", "2026-10-26", "--outcome", "passed", "--status", "executed")
        if out.returncode != 0:
            return [f"status_flag: expected exit 0, got {out.returncode}\n{out.stderr}"]

        facts_text = (spec / "_facts.yml").read_text(encoding="utf-8")
        if "status: executed" not in facts_text or "verified_on: 2026-10-26" not in facts_text:
            problems.append(f"status_flag: status: executed or verified_on not written into facts text:\n{facts_text}")

        loaded = yaml.safe_load(facts_text)
        ac2 = next((e for e in loaded.get("acceptance", []) if isinstance(e, dict) and e.get("id") == "AC2"), None)
        if not ac2:
            problems.append("status_flag: AC2 missing from loaded facts")
        else:
            if ac2.get("status") != "executed":
                problems.append(f"status_flag: expected status 'executed', got {ac2.get('status')!r}")
            if ac2.get("verified_on") != datetime.date(2026, 10, 26):
                problems.append(f"status_flag: expected verified_on 2026-10-26, got {ac2.get('verified_on')!r}")

        findings = run_audit(spec)
        ac2_findings = check_26_findings_for(findings, "AC2")
        if ac2_findings:
            problems.append(f"status_flag: unexpected check-26 finding for AC2: {ac2_findings}")

    return problems


def dry_writes_nothing() -> list[str]:
    problems = []
    with tempfile.TemporaryDirectory() as tmp:
        spec = copy_fixture(tmp)
        before_bytes = (spec / "_facts.yml").read_bytes()

        out = run_facts(spec, "AC1", "--date", "2026-10-26", "--outcome", "passed", "--dry")
        if out.returncode != 0:
            return [f"dry_writes_nothing: expected exit 0, got {out.returncode}\n{out.stderr}"]

        if "--- a/_facts.yml" not in out.stdout or "+++ b/_facts.yml" not in out.stdout:
            problems.append(f"dry_writes_nothing: expected diff in stdout, got:\n{out.stdout}")

        after_bytes = (spec / "_facts.yml").read_bytes()
        if before_bytes != after_bytes:
            problems.append("dry_writes_nothing: file was modified during --dry run")

    return problems


def main() -> int:
    verbose = "-v" in sys.argv[1:]
    failures: list[str] = []
    checks = (
        ("flow_append", flow_append),
        ("rerun_is_identical", rerun_is_identical),
        ("edits_line_reads_back", edits_line_reads_back),
        ("other_shapes", other_shapes),
        ("refusals", refusals),
        ("status_flag", status_flag),
        ("dry_writes_nothing", dry_writes_nothing),
    )

    passed_count = 0
    for name, check_fn in checks:
        probs = check_fn()
        if probs:
            failures.extend(probs)
            if verbose:
                print(f"FAIL {name}")
                for p in probs:
                    print(f"  {p}")
        else:
            passed_count += 1
            if verbose:
                print(f"PASS {name}")

    total = len(checks)
    print(f"\n{passed_count}/{total} checks passed")
    if failures and not verbose:
        for f in failures:
            print(f"  FAIL {f}")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
