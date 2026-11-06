#!/usr/bin/env python3
"""test_sync.py — scripts/sync.py propagates changed registry values, and only those.

The fixture (tests/fixtures/sync-values) holds the OLD registry plus the docs; the
test makes a throwaway git repo of it, commits, then drops `_facts.new.yml` over
`_facts.yml` — the edit sync is meant to follow. No .git is committed.

Cases:
  1. simple_replacement(): a plain value is replaced in every in-scope doc, with
     word boundaries, and the printed `**Edits:**` line is the file's real stamp
  2. dry_run_writes_nothing(): no --apply = plan only, every byte untouched
  3. legacy_derived_and_log_untouched(): listed as "not written", never edited
  4. ambiguous_reported_not_applied(): shared value, part of another datum and a
     short value are reported with their lines, left alone, exit 1
  5. decisions_listed_for_a_human(): changed decision named with its cited_in:
  6. scope_and_usage(): doc whose stage is not reached is named; no git history = exit 2
  7. stale_doc_not_written(): a doc changed between plan and write is skipped, exit 1,
     the others are written; writes are atomic (permissions kept, no temp left)
  8. base_equals_disk_warns(): REF == disk and registry clean = warning naming --from
  9. untracked_registry_exit_2(): registry not tracked = exit 2 asking for --from
  10. no_git_snapshot_flow(): set in a dir with no git: --init-base, edit, dry run
      (snapshot untouched), --apply updates doc and snapshot; no snapshot, no git = 2
  11. init_base_refuses_overwrite(): --init-base on an existing snapshot = 2, --force ok
  12. snapshot_kept_when_not_clean(): an ambiguous value left = snapshot stays
  13. from_file_and_snapshot_precedence(): --from-file works; snapshot beats HEAD;
      git-only apply does not create a snapshot

    python3 tests/test_sync.py
"""
from __future__ import annotations

import contextlib
import hashlib
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import sync as sync_mod  # noqa: E402
SYNC = ROOT / "scripts" / "sync.py"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
GIT = ["git", "-c", "user.name=t", "-c", "user.email=t@example.com",
       "-c", "commit.gpgsign=false"]


def make_repo(tmp: str, commit: bool = True) -> Path:
    """Copy the fixture into a fresh git repo; with `commit`, commit the OLD state and
    put the NEW registry on disk."""
    repo = Path(tmp)
    spec = repo / "sync-values"
    shutil.copytree(FIXTURES / "sync-values", spec)
    shutil.copy(FIXTURES / "_profile.fixture.yml", repo / "_profile.fixture.yml")
    new = spec / "_facts.new.yml"
    if commit:
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        new_text = new.read_text(encoding="utf-8")
        new.unlink()
        subprocess.run([*GIT, "add", "-A"], cwd=repo, check=True)
        subprocess.run([*GIT, "commit", "-q", "-m", "old"], cwd=repo, check=True)
        (spec / "_facts.yml").write_text(new_text, encoding="utf-8")
    return spec


def sync(spec: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SYNC), str(spec), *extra],
                          capture_output=True, text=True)


def snapshot(spec: Path) -> dict[str, bytes]:
    return {p.name: p.read_bytes() for p in sorted(spec.iterdir()) if p.is_file()}


def blob(data: bytes) -> str:
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()[:7]


def simple_replacement() -> list[str]:
    problems = []
    with tempfile.TemporaryDirectory() as tmp:
        spec = make_repo(tmp)
        out = sync(spec, "--apply")
        # ambiguous values exist in this fixture, so exit 1 is right; the safe ones
        # must have been written anyway
        if out.returncode != 1:
            problems.append(f"apply: expected exit 1 (ambiguous left), got "
                            f"{out.returncode}\n{out.stderr}")
        plan = (spec / "01-master-plan.md").read_text(encoding="utf-8")
        impl = (spec / "02-implementation.md").read_text(encoding="utf-8")
        if plan.count("45000 ms") != 3 or "30000" in plan:
            problems.append(f"apply: 01 should carry 45000 ms three times, none 30000:\n{plan}")
        if "fifteen minutes" not in plan or "twelve minutes" in plan:
            problems.append("apply: 01 retry window not replaced")
        if "45000 ms" not in impl or "fifteen minutes" not in impl:
            problems.append(f"apply: 02 not replaced:\n{impl}")
        if not re.search(r"01-master-plan\.md: 4 replacements \(lines 3, 6\)", out.stdout):
            problems.append(f"apply: per-file count/lines line missing:\n{out.stdout}")
        edits = [ln for ln in out.stdout.splitlines() if ln.startswith("**Edits:**")]
        if len(edits) != 1:
            problems.append(f"apply: expected one **Edits:** line, got {len(edits)}")
        else:
            for name in ("01-master-plan.md", "02-implementation.md"):
                data = (spec / name).read_bytes()
                want = f"`{name}` ({data.count(b'\n')} lines, blob {blob(data)})"
                if want not in edits[0]:
                    problems.append(f"Edits line: want {want} in {edits[0]}")
            if "legacy-notes" in edits[0] or "release-notes" in edits[0]:
                problems.append("Edits line names a file that must not be written")
        again = sync(spec, "--apply")
        if "**Edits:**" in again.stdout:
            problems.append("apply twice: second run wrote again (not idempotent)")
    return problems


def dry_run_writes_nothing() -> list[str]:
    problems = []
    with tempfile.TemporaryDirectory() as tmp:
        spec = make_repo(tmp)
        before = snapshot(spec)
        out = sync(spec)
        if snapshot(spec) != before:
            problems.append("dry run changed a file")
        if "DRY RUN" not in out.stdout or "01-master-plan.md: 4 replacements" not in out.stdout:
            problems.append(f"dry run: plan not printed:\n{out.stdout}")
        if "**Edits:**" in out.stdout:
            problems.append("dry run printed an Edits line for a write that never happened")
    return problems


def legacy_derived_and_log_untouched() -> list[str]:
    problems = []
    with tempfile.TemporaryDirectory() as tmp:
        spec = make_repo(tmp)
        before = snapshot(spec)
        out = sync(spec, "--apply")
        after = snapshot(spec)
        for name in ("legacy-notes.md", "release-notes.md", "_log.md"):
            if after[name] != before[name]:
                problems.append(f"{name} was written")
        for name in ("legacy-notes.md", "release-notes.md"):
            if name not in out.stdout.split("Not written", 1)[-1]:
                problems.append(f"{name} not listed under 'Not written'")
        if "Not written" not in out.stdout:
            problems.append("no 'Not written' section")
    return problems


def ambiguous_reported_not_applied() -> list[str]:
    problems = []
    with tempfile.TemporaryDirectory() as tmp:
        spec = make_repo(tmp)
        out = sync(spec, "--apply")
        plan = (spec / "01-master-plan.md").read_text(encoding="utf-8")
        section = out.stdout.split("Ambiguous", 1)[-1]
        for path, reason in (("limits.cache_ttl", "shared by several"),
                             ("limits.cache_tier", "part of another datum"),
                             ("limits.retries", "shorter than 3")):
            if path not in section or reason not in section:
                problems.append(f"{path}: not reported as ambiguous ({reason!r})")
        if "600 seconds" not in plan or "edge cache warmup" not in plan:
            problems.append("ambiguous value was replaced anyway (600 / edge cache)")
        if "up to 5 retries" not in plan.lower():
            problems.append("short value was replaced anyway (5)")
        if "900" in plan or "edge tier" in plan:
            problems.append("a new value of an ambiguous change leaked into the doc")
    return problems


def decisions_listed_for_a_human() -> list[str]:
    problems = []
    with tempfile.TemporaryDirectory() as tmp:
        spec = make_repo(tmp)
        before = (spec / "01-master-plan.md").read_text(encoding="utf-8")
        out = sync(spec)
        if "Needs a human (sync --decision)" not in out.stdout:
            problems.append("no 'Needs a human' section")
        if "decisions.queue" not in out.stdout or "01 §2, 02 Fase 1" not in out.stdout:
            problems.append(f"decision/cited_in not listed:\n{out.stdout}")
        if "retries are in-memory" in before or "queue" in before:
            problems.append("decision prose reached a doc")
    return problems


def scope_and_usage() -> list[str]:
    problems = []
    with tempfile.TemporaryDirectory() as tmp:
        spec = make_repo(tmp)
        out = sync(spec)
        if "03-runbook.md (stage shipped)" not in out.stdout:
            problems.append("doc whose stage is not reached is not named as out of scope")
        bad = sync(spec, "--from", "no-such-ref")
        if bad.returncode != 2 or "no-such-ref" not in bad.stderr:
            problems.append(f"bad --from: expected exit 2 naming the ref, got "
                            f"{bad.returncode}: {bad.stderr!r}")
    with tempfile.TemporaryDirectory() as tmp:
        spec = make_repo(tmp)
        (spec / "_facts.yml").write_text("feature: [unclosed\n", encoding="utf-8")
        bad = sync(spec)
        if bad.returncode != 2:
            problems.append(f"broken YAML: expected exit 2, got {bad.returncode}")
    with tempfile.TemporaryDirectory() as tmp:
        spec = make_repo(tmp, commit=False)  # not a git repo at all
        (spec / "_facts.yml").write_text((spec / "_facts.new.yml").read_text(), "utf-8")
        bad = sync(spec)
        if bad.returncode != 2:
            problems.append(f"no git history: expected exit 2, got {bad.returncode}")
    with tempfile.TemporaryDirectory() as tmp:
        spec = make_repo(tmp)
        (spec / "_facts.yml").write_text(
            subprocess.run(["git", "show", "HEAD:./_facts.yml"], cwd=spec,
                           capture_output=True, text=True).stdout, encoding="utf-8")
        clean = sync(spec, "--apply")
        if clean.returncode != 0 or "0 changed values" not in clean.stdout:
            problems.append(f"unchanged registry: expected exit 0 and 0 changes, got "
                            f"{clean.returncode}\n{clean.stdout}")
    return problems


def stale_doc_not_written() -> list[str]:
    problems = []
    with tempfile.TemporaryDirectory() as tmp:
        spec = make_repo(tmp)
        plan_doc, other = spec / "01-master-plan.md", spec / "02-implementation.md"
        os.chmod(other, 0o640)
        other_before = other.read_text(encoding="utf-8")
        edited = plan_doc.read_text(encoding="utf-8") + "\nhand edit during the plan\n"

        def hook(paths):
            plan_doc.write_text(edited, encoding="utf-8")

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = sync_mod.main([str(spec), "--apply"], before_write=hook)
        out = buf.getvalue()
        if rc != 1:
            problems.append(f"stale: expected exit 1, got {rc}")
        if plan_doc.read_text(encoding="utf-8") != edited:
            problems.append("stale: the doc changed during the plan was overwritten")
        if "changed since plan" not in out.lower() or "01-master-plan.md" not in \
                out.split("Changed since plan", 1)[-1]:
            problems.append(f"stale: not reported as 'changed since plan, re-run':\n{out}")
        if other.read_text(encoding="utf-8") == other_before:
            problems.append("stale: the untouched doc was not written")
        if "45000 ms" not in other.read_text(encoding="utf-8"):
            problems.append("stale: 02 not replaced")
        edits = [ln for ln in out.splitlines() if ln.startswith("**Edits:**")]
        if len(edits) != 1 or "01-master-plan" in edits[0] or "02-implementation" not in edits[0]:
            problems.append(f"stale: Edits line must name only the written doc: {edits}")
        if other.stat().st_mode & 0o777 != 0o640:
            problems.append(f"atomic: permissions lost ({oct(other.stat().st_mode & 0o777)})")
        leftovers = [p.name for p in spec.iterdir() if p.name.endswith(".tmp")]
        if leftovers:
            problems.append(f"atomic: temp files left behind: {leftovers}")
    return problems


def base_equals_disk_warns() -> list[str]:
    problems = []
    with tempfile.TemporaryDirectory() as tmp:
        spec = make_repo(tmp)
        out = sync(spec)
        if "identical" in out.stdout:
            problems.append("warning printed although the registry has uncommitted changes")
        repo = spec.parent
        subprocess.run([*GIT, "add", "-A"], cwd=repo, check=True)
        subprocess.run([*GIT, "commit", "-q", "-m", "new"], cwd=repo, check=True)
        out = sync(spec)
        if out.returncode != 0 or "identical" not in out.stdout or "--from" not in out.stdout:
            problems.append(f"REF==disk: no warning naming --from:\n{out.stdout}")
        back = sync(spec, "--from", "HEAD~1")
        if "identical" in back.stdout or "45000" not in back.stdout:
            problems.append(f"--from HEAD~1 should plan the committed change:\n{back.stdout}")
    return problems


def untracked_registry_exit_2() -> list[str]:
    problems = []
    with tempfile.TemporaryDirectory() as tmp:
        spec = make_repo(tmp)
        repo = spec.parent
        subprocess.run([*GIT, "rm", "--cached", "-q", "sync-values/_facts.yml"],
                       cwd=repo, check=True)
        subprocess.run([*GIT, "commit", "-q", "-m", "untrack"], cwd=repo, check=True)
        out = sync(spec)
        if out.returncode != 2 or "--from" not in out.stderr or "not tracked" not in out.stderr:
            problems.append(f"untracked registry: want exit 2 asking for --from, got "
                            f"{out.returncode}: {out.stderr!r}")
    return problems


OLD_FACTS = """feature: tiny
status: implementing
profile: ../_profile.fixture.yml
limits:
  timeout_ms: 45000
  retries: 6
docs:
  - { id: "01", file: 01-plan.md, role: master-plan, stage: draft }
"""
TINY_DOC = "# Plan\n\nTimeout is 45000 ms.\n\nWe allow up to 6 retries.\n"


def make_tiny(tmp: str) -> Path:
    """A set in a directory with NO git at all."""
    root = Path(tmp)
    shutil.copy(FIXTURES / "_profile.fixture.yml", root / "_profile.fixture.yml")
    spec = root / "tiny"
    spec.mkdir()
    (spec / "_facts.yml").write_text(OLD_FACTS, encoding="utf-8")
    (spec / "01-plan.md").write_text(TINY_DOC, encoding="utf-8")
    return spec


def no_git_snapshot_flow() -> list[str]:
    problems = []
    with tempfile.TemporaryDirectory() as tmp:
        spec = make_tiny(tmp)
        out = sync(spec)
        if (out.returncode != 2 or "--init-base" not in out.stderr
                or "--from-file" not in out.stderr):
            problems.append(f"no base: want exit 2 naming --init-base and --from-file, "
                            f"got {out.returncode}: {out.stderr!r}")
        out = sync(spec, "--init-base")
        snap = spec / "_facts.synced.yml"
        if out.returncode != 0 or not snap.is_file() or str(snap) not in out.stdout:
            problems.append(f"--init-base: want exit 0, path printed, file written: "
                            f"{out.returncode} {out.stdout!r} {out.stderr!r}")
        elif snap.read_bytes() != (spec / "_facts.yml").read_bytes():
            problems.append("--init-base: snapshot is not a byte copy")
        (spec / "_facts.yml").write_text(OLD_FACTS.replace("45000", "60000"),
                                         encoding="utf-8")
        before = snapshot(spec)
        out = sync(spec)
        first = out.stdout.splitlines()[0] if out.stdout else ""
        if "_facts.synced.yml" not in first:
            problems.append(f"dry run: first line should name the snapshot base: {first!r}")
        if out.returncode != 0 or "45000" not in out.stdout or "1 replacement" not in out.stdout:
            problems.append(f"dry run: plan missing: {out.returncode} {out.stdout!r}")
        if snapshot(spec) != before:
            problems.append("dry run wrote something")
        out = sync(spec, "--apply")
        doc = (spec / "01-plan.md").read_text(encoding="utf-8")
        if out.returncode != 0 or "60000 ms" not in doc or "45000" in doc:
            problems.append(f"apply: doc not updated: {out.returncode} {out.stderr!r}")
        if snap.read_bytes() != (spec / "_facts.yml").read_bytes():
            problems.append("apply: snapshot not updated to the current registry")
        again = sync(spec, "--apply")
        if "0 changed values" not in again.stdout:
            problems.append(f"second run should find nothing: {again.stdout!r}")
        if list(spec.glob(".*.tmp")):
            problems.append("a temp file was left behind")
    return problems


def init_base_refuses_overwrite() -> list[str]:
    problems = []
    with tempfile.TemporaryDirectory() as tmp:
        spec = make_tiny(tmp)
        sync(spec, "--init-base")
        (spec / "_facts.yml").write_text(OLD_FACTS.replace("45000", "60000"),
                                         encoding="utf-8")
        snap = spec / "_facts.synced.yml"
        old_bytes = snap.read_bytes()
        out = sync(spec, "--init-base")
        if out.returncode != 2 or snap.read_bytes() != old_bytes:
            problems.append(f"--init-base on existing: want exit 2, untouched: "
                            f"{out.returncode} {out.stderr!r}")
        out = sync(spec, "--init-base", "--force")
        if out.returncode != 0 or snap.read_bytes() != (spec / "_facts.yml").read_bytes():
            problems.append(f"--force: want exit 0 and a fresh copy: {out.returncode}")
    return problems


def snapshot_kept_when_not_clean() -> list[str]:
    problems = []
    with tempfile.TemporaryDirectory() as tmp:
        spec = make_tiny(tmp)
        sync(spec, "--init-base")
        snap = spec / "_facts.synced.yml"
        old_bytes = snap.read_bytes()
        # 6 -> 7 is shorter than 3 characters: ambiguous, and the doc carries it
        (spec / "_facts.yml").write_text(
            OLD_FACTS.replace("45000", "60000").replace("retries: 6", "retries: 7"),
            encoding="utf-8")
        out = sync(spec, "--apply")
        doc = (spec / "01-plan.md").read_text(encoding="utf-8")
        if out.returncode != 1 or "Ambiguous" not in out.stdout:
            problems.append(f"want exit 1 with an ambiguous value: {out.returncode}")
        if "60000 ms" not in doc:
            problems.append("the safe value should still be written")
        if snap.read_bytes() != old_bytes or "kept" not in out.stdout:
            problems.append("snapshot must stay and the run must say so")
        again = sync(spec)
        if "limits.retries" not in again.stdout:
            problems.append(f"next run should still show the unapplied change: "
                            f"{again.stdout!r}")
    return problems


def from_file_and_snapshot_precedence() -> list[str]:
    problems = []
    with tempfile.TemporaryDirectory() as tmp:
        spec = make_tiny(tmp)
        old = Path(tmp) / "old-facts.yml"
        old.write_text(OLD_FACTS, encoding="utf-8")
        (spec / "_facts.yml").write_text(OLD_FACTS.replace("45000", "60000"),
                                         encoding="utf-8")
        out = sync(spec, "--from-file", str(old))
        first = out.stdout.splitlines()[0] if out.stdout else ""
        if out.returncode != 0 or "file" not in first or "1 replacement" not in out.stdout:
            problems.append(f"--from-file: {out.returncode} {out.stdout!r} {out.stderr!r}")
        if sync(spec, "--from-file", str(Path(tmp) / "nope.yml")).returncode != 2:
            problems.append("--from-file on a missing file should exit 2")
    with tempfile.TemporaryDirectory() as tmp:
        spec = make_repo(tmp)  # HEAD = old, disk = new
        out = sync(spec)
        if "base: git HEAD" not in out.stdout:
            problems.append(f"git without snapshot must keep using HEAD: {out.stdout[:80]!r}")
        applied = sync(spec, "--apply")
        if (spec / "_facts.synced.yml").exists():
            problems.append("git-only apply must not create a snapshot")
        del applied
    with tempfile.TemporaryDirectory() as tmp:
        spec = make_repo(tmp)
        shutil.copy(spec / "_facts.yml", spec / "_facts.synced.yml")  # snapshot = disk
        out = sync(spec)
        first = out.stdout.splitlines()[0] if out.stdout else ""
        if "_facts.synced.yml" not in first or "0 changed values" not in out.stdout:
            problems.append(f"snapshot should win over HEAD: {out.stdout[:200]!r}")
    return problems


def main() -> int:
    failures = []
    checks = (simple_replacement, dry_run_writes_nothing,
              legacy_derived_and_log_untouched, ambiguous_reported_not_applied,
              decisions_listed_for_a_human, scope_and_usage,
              stale_doc_not_written, base_equals_disk_warns,
              untracked_registry_exit_2, no_git_snapshot_flow,
              init_base_refuses_overwrite, snapshot_kept_when_not_clean,
              from_file_and_snapshot_precedence)
    for check in checks:
        failures += check()
    print(f"\n{len(checks) - bool(failures)}/{len(checks)} checks passed"
          if failures else f"\n{len(checks)}/{len(checks)} checks passed")
    for f in failures:
        print(f"  FAIL {f}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
