#!/usr/bin/env python3
"""test_new.py — tests for scripts/new.py (the `new <slug>` scaffold).

Seven cases:
  1. creates_three_files(): _facts.yml, _log.md, 01-master-plan.md; audit has no CONTRADICTION
  2. refuses_existing(): exit 2 when _facts.yml exists, nothing overwritten
  3. no_profile_exit_2(): exit 2 with the intake-set-A message
  4. sibling_listed(): a pre-existing sibling is printed, never decided
  5. dry_writes_nothing(): --dry prints the plan and creates no directory
  6. prose_language_en(): English headings from the doc-pattern map; es keeps the template's
  7. profile_walk(): nearest _profile.yml wins; recorded relative to where audit resolves it

    python3 tests/test_new.py [-v]
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
NEW = ROOT / "scripts" / "new.py"
AUDIT = ROOT / "scripts" / "audit.py"
FIX = Path(__file__).resolve().parent / "fixtures" / "new-scaffold"
VERBOSE = "-v" in sys.argv


def repo(tmp: str, lang: str = "es") -> Path:
    r = Path(tmp)
    subprocess.run(["git", "init", "-q", str(r)], check=True)
    feats = r / "docs" / "features"
    feats.mkdir(parents=True)
    shutil.copy(FIX / f"profile.{lang}.yml", feats / "_profile.yml")
    return r


def run_new(r: Path, slug: str = "login", *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(NEW), f"docs/features/{slug}", "--title", "Login flow",
         "--agent", "test-agent", "--today", "2026-11-06", *extra],
        cwd=r, capture_output=True, text=True)


def creates_three_files() -> None:
    with tempfile.TemporaryDirectory() as t:
        r = repo(t)
        res = run_new(r)
        assert res.returncode == 0, res.stdout + res.stderr
        d = r / "docs" / "features" / "login"
        for n in ("_facts.yml", "_log.md", "01-master-plan.md"):
            assert (d / n).is_file(), n
        facts = yaml.safe_load((d / "_facts.yml").read_text())
        assert facts["feature"] == "login" and facts["status"] == "draft"
        assert [x["stage"] for x in facts["docs"]] == ["draft", "reviewed", "reviewed", "reviewed"]
        # repo-root relative, as every real set spells it
        assert facts["profile"] == "docs/features/_profile.yml", facts["profile"]
        log = (d / "_log.md").read_text()
        assert "## R1 · 2026-11-06 · test-agent · author" in log and "<!--" not in log
        assert "**Edits:** `_facts.yml`" in res.stdout, res.stdout
        out = subprocess.run([sys.executable, str(AUDIT), str(d), "--repo-root", str(r)],
                             capture_output=True, text=True).stdout
        assert "CONTRADICTION" not in out, out
        assert re.search(r"^audit: (0 contradictions|clean)", res.stdout, re.M), res.stdout


def refuses_existing() -> None:
    with tempfile.TemporaryDirectory() as t:
        r = repo(t)
        d = r / "docs" / "features" / "login"
        d.mkdir()
        (d / "_facts.yml").write_text("feature: login\n")
        res = run_new(r)
        assert res.returncode == 2 and "already exists" in res.stderr, res.stderr
        assert (d / "_facts.yml").read_text() == "feature: login\n"
        assert not (d / "_log.md").exists()


def no_profile_exit_2() -> None:
    with tempfile.TemporaryDirectory() as t:
        r = repo(t)
        (r / "docs" / "features" / "_profile.yml").unlink()
        res = run_new(r)
        assert res.returncode == 2, res.returncode
        assert "no _profile.yml: run intake set A (references/intake.md) first" in res.stderr
        assert not (r / "docs" / "features" / "login").exists()


def sibling_listed() -> None:
    with tempfile.TemporaryDirectory() as t:
        r = repo(t)
        (r / "docs" / "features" / "login-old.md").write_text("# old\n")
        res = run_new(r)
        assert res.returncode == 0, res.stderr
        assert "sibling: docs/features/login-old.md — decide: integrate or register role: legacy" \
            in res.stdout, res.stdout
        facts = yaml.safe_load((r / "docs/features/login/_facts.yml").read_text())
        assert all(x["file"] != "login-old.md" for x in facts["docs"])


def dry_writes_nothing() -> None:
    with tempfile.TemporaryDirectory() as t:
        r = repo(t)
        res = run_new(r, "login", "--dry")
        assert res.returncode == 0, res.stderr
        assert "_facts.yml" in res.stdout and "01-master-plan.md" in res.stdout
        assert not (r / "docs" / "features" / "login").exists()


def prose_language_en() -> None:
    with tempfile.TemporaryDirectory() as t:
        r = repo(t, "en")
        assert run_new(r).returncode == 0
        doc = (r / "docs/features/login/01-master-plan.md").read_text()
        assert "## 1. Problem" in doc and "## 7. Master checklist" in doc, doc
        assert "### 3.1 Components that change" in doc and "## 8. Risks" in doc
        assert "Checklist maestro" not in doc
        assert "# Master Plan — Login flow" in doc
    with tempfile.TemporaryDirectory() as t:
        r = repo(t, "es")
        assert run_new(r).returncode == 0
        doc = (r / "docs/features/login/01-master-plan.md").read_text()
        assert "## 7. Checklist maestro" in doc and "## 1. Problema" in doc


def profile_walk() -> None:
    with tempfile.TemporaryDirectory() as t:
        r = repo(t, "es")
        app = r / "docs" / "features" / "app"
        app.mkdir()
        shutil.copy(FIX / "profile.en.yml", app / "_profile.yml")
        res = subprocess.run(
            [sys.executable, str(NEW), "docs/features/app", "--title", "T", "--agent", "a"],
            cwd=r, capture_output=True, text=True)
        assert res.returncode == 0, res.stdout + res.stderr
        assert "prose_language: en" in res.stdout
        facts = yaml.safe_load((app / "_facts.yml").read_text())
        # a profile inside the spec dir: nearest wins, still spelled from the repo root
        assert facts["profile"] == "docs/features/app/_profile.yml", facts["profile"]
        res = subprocess.run(
            [sys.executable, str(NEW), "docs/features/other/deep", "--title", "T", "--agent", "a"],
            cwd=r, capture_output=True, text=True)
        assert res.returncode == 0, res.stdout + res.stderr
        assert "prose_language: es" in res.stdout


CASES = [creates_three_files, refuses_existing, no_profile_exit_2, sibling_listed,
         dry_writes_nothing, prose_language_en, profile_walk]


def main() -> int:
    ok = 0
    for fn in CASES:
        try:
            fn()
            ok += 1
            if VERBOSE:
                print(f"ok   {fn.__name__}")
        except AssertionError as exc:
            print(f"FAIL {fn.__name__}: {exc}")
    print(f"{ok}/{len(CASES)} checks passed")
    return 0 if ok == len(CASES) else 1


if __name__ == "__main__":
    sys.exit(main())
