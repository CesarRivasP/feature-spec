#!/usr/bin/env python3
"""ship.py — the flip to `shipped`, against the set it was written for.

Six hand edits, a `Stage:` line and three re-stamps was what one real flip cost.
What has to hold: the gates refuse before anything is written, and name the entry
that blocks; the edits land where the audit then reads them (check 40 reads the
revision in both orders, check 28 reads `shipped_in:`, check 16 reads the `Stage:`
line printed for the log); comments survive; `--dry` writes nothing.

    python3 tests/test_ship.py
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SHIP = ROOT / "scripts" / "ship.py"
AUDIT = ROOT / "scripts" / "audit.py"
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def copy_fixture(tmp: str) -> Path:
    dst = Path(tmp) / "ship-ready"
    shutil.copytree(FIXTURES / "ship-ready", dst)
    shutil.copy(FIXTURES / "_profile.fixture.yml", Path(tmp) / "_profile.fixture.yml")
    return dst


def ship(spec: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SHIP), str(spec), "--repo-root",
                           str(spec.parent), *extra], capture_output=True, text=True)


def audit(spec: Path) -> list[dict]:
    out = subprocess.run([sys.executable, str(AUDIT), str(spec), "--repo-root",
                          str(spec.parent), "--json"], capture_output=True, text=True)
    if out.returncode not in (0, 1):
        raise AssertionError(f"audit.py crashed\n{out.stderr}")
    return json.loads(out.stdout)["findings"]


def has(findings: list[dict], check: str, text: str) -> bool:
    return any(check in f["check"] and (text in f["what"] or text in f["where"])
               for f in findings)


def flip_lands_where_the_audit_reads() -> list[str]:
    problems = []
    with tempfile.TemporaryDirectory() as tmp:
        spec = copy_fixture(tmp)
        out = ship(spec, "--tag", "v1.4.1", "--on", "2026-10-09",
                   "--url", "https://example.com/releases/v1.4.1")
        if out.returncode != 0:
            return [f"ship: expected exit 0, got {out.returncode}\n{out.stderr}"]
        facts = (spec / "_facts.yml").read_text(encoding="utf-8")
        for needle, why in (
            ("status: shipped          # ORDERED", "status flipped, its comment kept"),
            ("  shipped_in: v1.4.1      # release tag once merged", "shipped_in set, comment kept"),
            ("  shipped_on: 2026-10-09", "shipped_on written beside shipped_in"),
            ("  release_url: https://example.com/releases/v1.4.1", "release_url written"),
            ("    - { tag: v3, date: 2026-10-09, note: 'shipped in v1.4.1' }",
             "revision v3 appended"),
            ("  pr: 14                # the PR", "untouched lines untouched"),
        ):
            if needle not in facts:
                problems.append(f"ship: {why} — `{needle}` not in _facts.yml:\n{facts}")
        if facts.index("tag: v2") > facts.index("tag: v3"):
            problems.append("ship: the revision must be APPENDED — dates.revisions[] is "
                            "oldest first")
        doc = (spec / "01-master-plan.md").read_text(encoding="utf-8")
        if "- **Estado:** shipped" not in doc:
            problems.append("ship: doc 01's Estado line did not flip")
        if "### 2026-10-09 — v3: shipped in v1.4.1" not in doc:
            problems.append(f"ship: doc 01 has no changelog entry for v3:\n{doc}")
        elif doc.index("v3: shipped") > doc.index("v2: revisado"):
            problems.append("ship: the changelog entry must be PREPENDED — docs run "
                            "newest first")
        stage = re.search(r"^\*\*Stage:\*\* implementing → shipped — .*v1\.4\.1.*$",
                          out.stdout, re.M)
        if not stage:
            problems.append(f"ship: must print the `**Stage:**` line for the log, got:\n"
                            f"{out.stdout}")
        edits = re.search(r"^\*\*Edits:\*\* (.*)$", out.stdout, re.M)
        if not edits or "`_facts.yml` (" not in edits.group(1) \
                or "`01-master-plan.md` (" not in edits.group(1):
            problems.append("ship: must print an `**Edits:**` line stamping both files")
        else:
            # the stamps must be what check 16 will measure
            data = (spec / "_facts.yml").read_bytes()
            m = re.search(r"`_facts\.yml` \((\d+) lines, blob ([0-9a-f]{7})\)",
                          edits.group(1))
            if not m or int(m.group(1)) != data.count(b"\n"):
                problems.append("ship: the `_facts.yml` stamp does not match the file "
                                "written")

        findings = audit(spec)
        for check, text in (("40", "v3"), ("28", "shipped_in"), ("1b/14", "G1"),
                            ("14", "D1"), ("26", "AC1")):
            if has(findings, check, text):
                problems.append(f"ship: after the flip, check {check} still reports "
                                f"{text!r} — the edit did not land where it is read")
        if not has(findings, "16", "ends at `implementing`"):
            problems.append("ship: the log was not written (correct) so check 16 must "
                            "ask for the Stage line — it did not")
    return problems


def dry_run_writes_nothing() -> list[str]:
    with tempfile.TemporaryDirectory() as tmp:
        spec = copy_fixture(tmp)
        before = {p.name: p.read_bytes() for p in spec.iterdir()}
        out = ship(spec, "--tag", "v1.4.1", "--on", "2026-10-09", "--dry")
        after = {p.name: p.read_bytes() for p in spec.iterdir()}
    problems = []
    if before != after:
        problems.append("ship --dry: a file changed")
    if out.returncode != 0 or "+status: shipped" not in out.stdout:
        problems.append(f"ship --dry: must print the diff it would apply, got exit "
                        f"{out.returncode}:\n{out.stdout}{out.stderr}")
    return problems


def gates_refuse_and_name_the_entry() -> list[str]:
    problems = []
    cases = (
        ("basis: measured, status: fixed", "basis: asserted, status: open,\n      "
         "falsified_by: 'nada', log_line: null", "D1", "G1 refuses an asserted root cause"),
        ("status: approved, verified_on: 2026-09-20", "status: written", "AC1",
         "check 26 refuses an unverified criterion"),
    )
    for old, new, who, why in cases:
        with tempfile.TemporaryDirectory() as tmp:
            spec = copy_fixture(tmp)
            facts = spec / "_facts.yml"
            text = facts.read_text(encoding="utf-8")
            if old not in text:
                problems.append(f"ship gate: fixture no longer has `{old}`")
                continue
            facts.write_text(text.replace(old, new, 1), encoding="utf-8")
            before = facts.read_bytes()
            out = ship(spec, "--tag", "v1.4.1", "--on", "2026-10-09")
            if out.returncode != 2:
                problems.append(f"ship gate: {why} — expected exit 2, got "
                                f"{out.returncode}\n{out.stdout}{out.stderr}")
            if who not in out.stderr:
                problems.append(f"ship gate: {why} — the refusal must name {who}:\n"
                                f"{out.stderr}")
            if facts.read_bytes() != before:
                problems.append(f"ship gate: {why} — refused, yet the registry changed")
    with tempfile.TemporaryDirectory() as tmp:
        spec = copy_fixture(tmp)
        ship(spec, "--tag", "v1.4.1", "--on", "2026-10-09")
        out = ship(spec, "--tag", "v1.4.2", "--on", "2026-10-10")
        if out.returncode != 2 or "already" not in out.stderr:
            problems.append("ship: a second flip must be refused as already shipped")
    return problems


def registry_paths_stay_inside() -> list[str]:
    """The registry is input. `docs[].file` names what this script WRITES to, so a
    `../` there is an arbitrary file write — refused before anything is touched,
    the registry included."""
    with tempfile.TemporaryDirectory() as tmp:
        spec = copy_fixture(tmp)
        outside = Path(tmp) / "outside.md"
        outside.write_text("# not yours\n\n## Changelog\n", encoding="utf-8")
        facts = spec / "_facts.yml"
        text = facts.read_text(encoding="utf-8")
        facts.write_text(text.replace("file: 01-master-plan.md", "file: ../outside.md"),
                         encoding="utf-8")
        before = {p.name: p.read_bytes() for p in spec.iterdir()}
        before_outside = outside.read_bytes()
        out = ship(spec, "--tag", "v1.4.1", "--on", "2026-10-09")
        after = {p.name: p.read_bytes() for p in spec.iterdir()}
        outside_touched = outside.read_bytes() != before_outside
    problems = []
    if out.returncode != 3 or "outside" not in out.stderr:
        problems.append(f"ship: an escaping docs[].file must be refused with exit 3, got "
                        f"{out.returncode}: {out.stderr[:200]!r}")
    if outside_touched:
        problems.append("ship: wrote outside the spec dir")
    if before != after:
        problems.append("ship: refused the doc path but still edited the registry")
    return problems


def main() -> int:
    failures = []
    checks = (flip_lands_where_the_audit_reads, dry_run_writes_nothing,
              gates_refuse_and_name_the_entry, registry_paths_stay_inside)
    for check in checks:
        failures += check()
    print(f"\n{len(checks) - bool(failures)}/{len(checks)} checks passed"
          if failures else f"\n{len(checks)}/{len(checks)} checks passed")
    for f in failures:
        print(f"  FAIL {f}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
