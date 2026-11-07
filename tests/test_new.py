#!/usr/bin/env python3
"""test_new.py — tests for scripts/new.py (the `new <slug>` scaffold).

Twelve cases:
  1. creates_three_files(): _facts.yml, _log.md, 01-master-plan.md; audit has no CONTRADICTION
  2. refuses_existing(): exit 2 when _facts.yml exists, nothing overwritten
  3. no_profile_exit_2(): exit 2 with the intake-set-A message
  4. sibling_listed(): a pre-existing sibling is printed, never decided
  5. dry_writes_nothing(): --dry prints the plan and creates no directory
  6. prose_language_en(): English headings from the doc-pattern map; es keeps the template's
  7. profile_walk(): nearest _profile.yml wins; recorded relative to where audit resolves it
  8. refuses_partial(): any of the three files present -> exit 2, nothing overwritten
  9. audit_exit_2(): audit exit 2 -> new.py exit 1 with audit's stderr
 10. serialization(): accents literal, yes stays a string, bad slug/title refused
 11. en_no_spanish(): en scaffold has no Spanish template line; title not translated
 12. siblings_matching(): slug-precise matching, spec.parent based (monorepo)

    python3 tests/test_new.py [-v]
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    import yaml
except ImportError:  # the plugin's bundled copy
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "_vendor"))
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


def run_raw(r: Path, rel: str, title: str = "T") -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(NEW), rel, "--title", title, "--agent", "a",
         "--today", "2026-11-06"], cwd=r, capture_output=True, text=True)


def refuses_partial() -> None:
    for name in ("_log.md", "01-master-plan.md"):
        with tempfile.TemporaryDirectory() as t:
            r = repo(t)
            d = r / "docs" / "features" / "login"
            d.mkdir()
            (d / name).write_text("mine\n")
            res = run_new(r)
            assert res.returncode == 2 and name in res.stderr, res.stderr
            assert (d / name).read_text() == "mine\n"
            assert sorted(p.name for p in d.iterdir()) == [name]


def audit_exit_2() -> None:
    import importlib.util
    with tempfile.TemporaryDirectory() as t:
        r = repo(t)
        stub = Path(t) / "stub_audit.py"
        stub.write_text("import sys\nprint('boom: broken yaml', file=sys.stderr)\nsys.exit(2)\n")
        spec = importlib.util.spec_from_file_location("new_under_test", NEW)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.AUDIT = stub
        cwd = Path.cwd()
        import os, io, contextlib
        os.chdir(r)
        try:
            err = io.StringIO()
            with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
                rc = mod.main(["docs/features/login", "--title", "T", "--agent", "a",
                               "--today", "2026-11-06"])
        finally:
            os.chdir(cwd)
        assert rc == 1, rc
        assert "boom: broken yaml" in err.getvalue(), err.getvalue()


def serialization() -> None:
    with tempfile.TemporaryDirectory() as t:
        r = repo(t)
        res = run_raw(r, "docs/features/yes", "Migración de datos")
        assert res.returncode == 0, res.stdout + res.stderr
        txt = (r / "docs/features/yes/_facts.yml").read_text()
        assert "Migración" in txt and "\\u" not in txt, txt
        facts = yaml.safe_load(txt)
        assert facts["feature"] == "yes" and facts["title"] == "Migración de datos", facts
        res = run_raw(r, "docs/features/ok", "line one\nline two")
        assert res.returncode == 2 and not (r / "docs/features/ok").exists(), res.stderr
        for bad in ("x: y", "123", "[w]", "Up"):
            res = run_raw(r, f"docs/features/{bad}")
            assert res.returncode == 2, (bad, res.stdout, res.stderr)
            assert not (r / "docs/features" / bad).exists(), bad
        res = run_raw(r, "docs/features/colon", "a: b # c")
        assert res.returncode == 0, res.stderr
        f = yaml.safe_load((r / "docs/features/colon/_facts.yml").read_text())
        assert f["title"] == "a: b # c", f


def en_no_spanish() -> None:
    with tempfile.TemporaryDirectory() as t:
        r = repo(t, "en")
        res = run_raw(r, "docs/features/login", "Riesgos de Migración")
        assert res.returncode == 0, res.stderr
        doc = (r / "docs/features/login/01-master-plan.md").read_text()
        assert "# Master Plan — Riesgos de Migración" in doc, doc[:200]
        for es in ("plan de implementación", "plan de pruebas", "requerimientos para",
                   "Todo dato compartido", "Objetivo", "Estado:", "Fecha:", "mitigación"):
            assert es not in doc, es
        assert "Every shared datum" in doc


def siblings_matching() -> None:
    with tempfile.TemporaryDirectory() as t:
        r = repo(t)
        f = r / "docs" / "features"
        for n in ("legacy", "yes", "oauth-login", "login-v1", "relogin"):
            (f / n).mkdir()
        (f / "e.md").write_text("x")
        res = run_new(r, "e")
        assert res.returncode == 0, res.stderr
        sib = [ln for ln in res.stdout.splitlines() if ln.startswith("sibling:")]
        assert len(sib) == 1 and sib[0].startswith("sibling: docs/features/e.md —"), sib
        res = run_new(r, "login")
        sib = " ".join(ln.split("—")[0] for ln in res.stdout.splitlines()
                       if ln.startswith("sibling:"))
        assert "oauth-login" in sib and "login-v1" in sib, sib
        assert "relogin" not in sib and "_profile" not in sib, sib
    with tempfile.TemporaryDirectory() as t:
        r = repo(t)
        feats = r / "apps" / "web" / "docs" / "features"
        (feats / "checkout-old").mkdir(parents=True)
        shutil.copy(FIX / "profile.es.yml", feats / "_profile.yml")
        res = run_raw(r, "apps/web/docs/features/checkout")
        assert res.returncode == 0, res.stderr
        assert "sibling: apps/web/docs/features/checkout-old" in res.stdout, res.stdout


CASES = [creates_three_files, refuses_existing, no_profile_exit_2, sibling_listed,
         dry_writes_nothing, prose_language_en, profile_walk, refuses_partial,
         audit_exit_2, serialization, en_no_spanish, siblings_matching]


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
