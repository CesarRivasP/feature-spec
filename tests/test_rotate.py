#!/usr/bin/env python3
"""rotate.py executes the rotation `audit.py --rotate-plan` prints.

What has to hold: the bytes move and reassemble exactly; `--dry` writes nothing;
every refusal (archive name taken, `_log.md` changed after the plan, no open
rotation stub) exits 2 with the log untouched; a failed verification restores the
original and exits 1; a spec path with a space and `$(...)` is just a path; and the
lines it prints are measured the way check 16 re-measures them.

All of it runs on temporary copies of tests/fixtures/matrix — the fixture the
`--rotate-plan` tests in test_audit.py use.

    python3 tests/test_rotate.py [-v]
"""
from __future__ import annotations

import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
ROTATE = SCRIPTS / "rotate.py"
AUDIT = SCRIPTS / "audit.py"
FIXTURES = Path(__file__).resolve().parent / "fixtures"

sys.path.insert(0, str(SCRIPTS))
import audit  # noqa: E402
import rotate  # noqa: E402

PREAMBLE = "# Handoff log — matrix\n\nAppend-only log for matrix feature.\n"
STUB = "## R97 · 2026-10-26 · test · rotate\n"
ORIGINAL_FIRST, ORIGINAL_LAST = 37, 96


def entries(first: int = ORIGINAL_FIRST, last: int = ORIGINAL_LAST) -> str:
    out = []
    for i in range(first, last + 1):
        extra = "**Stage:** draft → reviewed\n" if i == 40 else ""
        out.append(f"## R{i} · 2026-09-30 · test · review\n**Read:** none\n"
                   f"**Log read through:** R{i - 1}\n{extra}" + "x" * 1500 + "\n\n")
    return "".join(out)


def make_spec(tmp: str, name: str = "matrix", stub: bool = True, rounds: tuple[int, int] = (37, 96)) -> Path:
    spec = Path(tmp) / name
    shutil.copytree(FIXTURES / "matrix", spec)
    (spec / "_log.md").write_text(PREAMBLE + entries(*rounds) + (STUB if stub else ""),
                                  encoding="utf-8")
    return spec


def run(spec: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(ROTATE), str(spec), "--today", "2026-10-26", *extra],
                          capture_output=True, text=True)


def stray_files(spec: Path) -> list[str]:
    return sorted(p.name for p in spec.iterdir() if p.name.endswith((".tmp", ".kept")))


def plan_of(spec: Path) -> dict:
    code, plan = audit.rotate_plan_data(audit.load_facts(spec / "_facts.yml"), spec,
                                        today=None)
    assert code == 0 and isinstance(plan, dict), plan
    return plan


def rotates_and_reassembles() -> list[str]:
    problems = []
    with tempfile.TemporaryDirectory() as tmp:
        spec = make_spec(tmp)
        original = (spec / "_log.md").read_bytes()
        res = run(spec)
        if res.returncode != 0:
            return [f"rotates_and_reassembles: exit {res.returncode}: {res.stderr}"]
        archives = sorted(spec.glob("_log-R*.md"))
        if len(archives) != 1:
            return [f"rotates_and_reassembles: expected one archive, found {archives}"]
        arch = archives[0]
        kept = (spec / "_log.md").read_bytes()
        arch_b = arch.read_bytes()
        pre_lines = re.findall(rb"[^\n]*\n", kept)
        body = b"".join(re.findall(rb"[^\n]*\n", arch_b)[8:])
        if b"".join(pre_lines[:3]) + body + b"".join(pre_lines[3:]) != original:
            problems.append("rotates_and_reassembles: preamble + archive body + kept != original bytes")
        if not kept.endswith(STUB.encode()):
            problems.append("rotates_and_reassembles: the open stub is not the end of the kept log")
        if stray_files(spec):
            problems.append(f"rotates_and_reassembles: leftover files {stray_files(spec)}")
        if "_log-R37-R92.md" != arch.name:
            problems.append(f"rotates_and_reassembles: archive name {arch.name}")
        # same cut as --rotate-plan, which is the plan the doc still points at
        plan_txt = subprocess.run([sys.executable, str(AUDIT), str(spec), "--repo-root", str(spec),
                                   "--rotate-plan"], capture_output=True, text=True)
        # (the log is rotated now: plan refuses or says nothing to rotate — never a new cut)
        if "```sh" in plan_txt.stdout:
            problems.append("rotates_and_reassembles: a second plan still wants to rotate")

        out = res.stdout
        n = arch_b.count(b"\n")
        sha = audit.git_blob(arch_b)[:7]
        if f"**Archived:** `{arch.name}` ({n} lines, blob {sha})" not in out:
            problems.append(f"rotates_and_reassembles: Archived line missing/wrong:\n{out}")
        want_edits = ("**Edits:** " + audit.version_stamp("_log.md", kept) + " · "
                      + audit.version_stamp(arch.name, arch_b))
        if want_edits not in out:
            problems.append(f"rotates_and_reassembles: Edits line missing/wrong:\n{out}")
        if "**Stage:** reviewed → reviewed — carried" not in out:
            problems.append("rotates_and_reassembles: carried Stage line not printed")
        if "complete **Read:** and **Carried open:** (handoff.md step 3), then run audit" not in out:
            problems.append("rotates_and_reassembles: closing instruction missing")
        # measured like --read-line measures
        rl = subprocess.run([sys.executable, str(AUDIT), str(spec), "--repo-root", str(spec),
                             "--read-line", arch.name], capture_output=True, text=True).stdout
        if f"({n} lines, blob {sha}" not in rl:
            problems.append(f"rotates_and_reassembles: stamp differs from --read-line: {rl}")
        # it writes none of the entry's fields
        for field in ("**Read:**", "**Carried open:**"):
            if kept.decode().count(field + " ") and field in kept.decode().split(STUB)[-1]:
                problems.append(f"rotates_and_reassembles: wrote {field} into the entry")
        if kept.decode().split(STUB)[-1] != "":
            problems.append("rotates_and_reassembles: text added after the stub")
        # audit no longer reports the size
        rep = json.loads(subprocess.run([sys.executable, str(AUDIT), str(spec), "--repo-root",
                                         str(spec), "--json"], capture_output=True, text=True).stdout)
        if any("past what one read" in f.get("what", "") for f in rep["findings"]):
            problems.append("rotates_and_reassembles: audit still reports log size")
    return problems


def dry_writes_nothing() -> list[str]:
    problems = []
    with tempfile.TemporaryDirectory() as tmp:
        spec = make_spec(tmp)
        before = {p.name: p.read_bytes() for p in spec.iterdir() if p.is_file()}
        res = run(spec, "--dry")
        after = {p.name: p.read_bytes() for p in spec.iterdir() if p.is_file()}
        if res.returncode != 0:
            problems.append(f"dry_writes_nothing: exit {res.returncode}: {res.stderr}")
        if before != after:
            problems.append("dry_writes_nothing: --dry changed the directory")
        if "_log-R37-R92.md" not in res.stdout or "**Archived:**" not in res.stdout:
            problems.append(f"dry_writes_nothing: plan / lines not printed:\n{res.stdout}")
    return problems


def archive_exists_refused() -> list[str]:
    problems = []
    with tempfile.TemporaryDirectory() as tmp:
        spec = make_spec(tmp)
        (spec / "_log-R37-R92.md").write_text("existing", encoding="utf-8")
        before = (spec / "_log.md").read_bytes()
        res = run(spec)
        if res.returncode != 2:
            problems.append(f"archive_exists_refused: expected 2, got {res.returncode}")
        if "_log-R37-R92.md" not in res.stderr:
            problems.append("archive_exists_refused: message does not name the archive")
        if (spec / "_log.md").read_bytes() != before:
            problems.append("archive_exists_refused: _log.md changed")
        if (spec / "_log-R37-R92.md").read_text() != "existing":
            problems.append("archive_exists_refused: the existing archive was overwritten")
    return problems


def log_changed_since_plan() -> list[str]:
    """No sleeps: the change is injected between the plan and the write."""
    problems = []
    with tempfile.TemporaryDirectory() as tmp:
        spec = make_spec(tmp)
        plan = plan_of(spec)

        def edit(d: Path) -> None:
            with (d / "_log.md").open("a", encoding="utf-8") as fh:
                fh.write("late line\n")

        code, lines = rotate.execute(spec, plan, before_write=edit)
        if code != 2:
            problems.append(f"log_changed_since_plan: expected 2, got {code}: {lines}")
        if not (spec / "_log.md").read_bytes().endswith(b"late line\n"):
            problems.append("log_changed_since_plan: the concurrent edit was lost")
        if (spec / plan["archive_name"]).exists() or stray_files(spec):
            problems.append("log_changed_since_plan: something was written")
    return problems


def no_open_stub_refused() -> list[str]:
    problems = []
    with tempfile.TemporaryDirectory() as tmp:
        spec = make_spec(tmp, stub=False)
        before = (spec / "_log.md").read_bytes()
        res = run(spec)
        if res.returncode != 2:
            problems.append(f"no_open_stub_refused: expected 2, got {res.returncode}: {res.stderr}")
        if "stub" not in res.stderr:
            problems.append("no_open_stub_refused: message does not say why")
        if (spec / "_log.md").read_bytes() != before or list(spec.glob("_log-R*.md")):
            problems.append("no_open_stub_refused: something was written")
        # the dry run refuses the same way: it would print lines for a rotation that cannot run
        if run(spec, "--dry").returncode != 2:
            problems.append("no_open_stub_refused: --dry did not refuse")
    return problems


def unsafe_path_is_just_a_path() -> list[str]:
    problems = []
    with tempfile.TemporaryDirectory() as tmp:
        spec = make_spec(str(Path(tmp)), name="has space $(touch PWNED)")
        original = (spec / "_log.md").read_bytes()
        res = run(spec)
        if res.returncode != 0:
            problems.append(f"unsafe_path: exit {res.returncode}: {res.stderr[:200]}")
        if any(Path(tmp).rglob("PWNED")):
            problems.append("unsafe_path: `$(…)` in the path was executed")
        arch = next(spec.glob("_log-R*.md"), None)
        if arch is None:
            problems.append("unsafe_path: no archive written")
        else:
            kept = re.findall(rb"[^\n]*\n", (spec / "_log.md").read_bytes())
            body = re.findall(rb"[^\n]*\n", arch.read_bytes())[8:]
            if b"".join(kept[:3] + body + kept[3:]) != original:
                problems.append("unsafe_path: reassembly != original bytes")
    return problems


def nothing_to_rotate_exits_0() -> list[str]:
    problems = []
    with tempfile.TemporaryDirectory() as tmp:
        spec = make_spec(tmp, rounds=(37, 56))
        before = (spec / "_log.md").read_bytes()
        res = run(spec)
        if res.returncode != 0:
            problems.append(f"nothing_to_rotate: expected 0, got {res.returncode}: {res.stderr}")
        if "nothing to rotate" not in res.stdout:
            problems.append(f"nothing_to_rotate: no reason printed: {res.stdout!r}")
        if (spec / "_log.md").read_bytes() != before or list(spec.glob("_log-R*.md")):
            problems.append("nothing_to_rotate: something was written")
        # no log at all
        (spec / "_log.md").unlink()
        if run(spec).returncode != 0:
            problems.append("nothing_to_rotate: missing _log.md should also exit 0")
    return problems


def failed_verification_restores() -> list[str]:
    problems = []
    with tempfile.TemporaryDirectory() as tmp:
        spec = make_spec(tmp)
        plan = plan_of(spec)
        original = (spec / "_log.md").read_bytes()

        def corrupt(d: Path) -> None:
            a = d / plan["archive_name"]
            a.write_bytes(a.read_bytes()[:-5])  # a lost tail

        code, lines = rotate.execute(spec, plan, after_write=corrupt)
        if code != 1:
            problems.append(f"failed_verification: expected 1, got {code}: {lines}")
        if (spec / "_log.md").read_bytes() != original:
            problems.append("failed_verification: _log.md was not restored")
        if (spec / plan["archive_name"]).exists() or stray_files(spec):
            problems.append("failed_verification: archive / temp files left behind")
    return problems


def entry_lines_pass_check_16() -> list[str]:
    """The printed lines, pasted into a completed rotation entry, leave check 16 with
    no Stage or Archived finding — the point of printing them measured."""
    problems = []
    with tempfile.TemporaryDirectory() as tmp:
        spec = make_spec(tmp)
        res = run(spec)
        pasted = [l for l in res.stdout.splitlines() if l.startswith("**")]
        rl = subprocess.run([sys.executable, str(AUDIT), str(spec), "--repo-root", str(spec),
                             "--read-line"], capture_output=True, text=True).stdout.strip()
        with (spec / "_log.md").open("a", encoding="utf-8") as fh:
            fh.write(rl + "\n**Log read through:** R96\n" + "\n".join(pasted) + "\n")
        rep = json.loads(subprocess.run([sys.executable, str(AUDIT), str(spec), "--repo-root",
                                         str(spec), "--json"], capture_output=True, text=True).stdout)
        bad = [f for f in rep["findings"]
               if f["check"].startswith("16") and ("Stage:" in f.get("what", "")
                                                   or "_log-R37-R92" in f.get("what", ""))]
        if bad:
            problems.append(f"entry_lines_pass_check_16: {bad[:2]}")
    return problems


def modes_are_kept() -> list[str]:
    """mkstemp makes 0600: the rotated log must keep the original's mode, the archive
    gets the umask default (what write_text gives)."""
    problems = []
    with tempfile.TemporaryDirectory() as tmp:
        spec = make_spec(tmp)
        (spec / "_log.md").chmod(0o644)
        res = run(spec)
        if res.returncode != 0:
            return [f"modes_are_kept: exit {res.returncode}: {res.stderr}"]
        got = stat.S_IMODE((spec / "_log.md").stat().st_mode)
        if got != 0o644:
            problems.append(f"modes_are_kept: _log.md is {oct(got)}, was 0o644")
        umask = os.umask(0)
        os.umask(umask)
        arch = next(spec.glob("_log-R*.md"))
        got_a = stat.S_IMODE(arch.stat().st_mode)
        if got_a != 0o666 & ~umask:
            problems.append(f"modes_are_kept: archive is {oct(got_a)}, umask default is {oct(0o666 & ~umask)}")
        if (spec / "_log.md.orig").exists():
            problems.append("modes_are_kept: _log.md.orig left after a good run")
    return problems


def symlink_log_refused() -> list[str]:
    problems = []
    with tempfile.TemporaryDirectory() as tmp:
        spec = make_spec(tmp)
        real = Path(tmp) / "real_log.md"
        shutil.move(str(spec / "_log.md"), real)
        (spec / "_log.md").symlink_to(real)
        before = real.read_bytes()
        res = run(spec)
        if res.returncode != 2 or "symlink" not in res.stderr:
            problems.append(f"symlink_log_refused: expected 2 + 'symlink', got {res.returncode}: {res.stderr}")
        if not (spec / "_log.md").is_symlink() or real.read_bytes() != before:
            problems.append("symlink_log_refused: the link or its target changed")
        if list(spec.glob("_log-R*.md")) or stray_files(spec):
            problems.append("symlink_log_refused: something was written")
    return problems


def log_changed_during_archive_write() -> list[str]:
    """The compare happens again right before the replace, not only before the archive."""
    problems = []
    with tempfile.TemporaryDirectory() as tmp:
        spec = make_spec(tmp)
        plan = plan_of(spec)

        def edit(d: Path) -> None:
            with (d / "_log.md").open("a", encoding="utf-8") as fh:
                fh.write("late line\n")

        code, lines = rotate.execute(spec, plan, before_replace=edit)
        if code != 2:
            problems.append(f"log_changed_during_archive_write: expected 2, got {code}: {lines}")
        if not (spec / "_log.md").read_bytes().endswith(b"late line\n"):
            problems.append("log_changed_during_archive_write: the concurrent edit was lost")
        if (spec / plan["archive_name"]).exists() or stray_files(spec) or (spec / "_log.md.orig").exists():
            problems.append("log_changed_during_archive_write: archive / temp / .orig left behind")
    return problems


def leftover_archive_is_named() -> list[str]:
    """An archive equal to header + moved bytes is an interrupted run: say it is safe
    to delete. A different one is just 'exists'. Stale temp files of ours are cleaned."""
    problems = []
    with tempfile.TemporaryDirectory() as tmp:
        spec = make_spec(tmp)
        plan = plan_of(spec)
        arch = spec / plan["archive_name"]
        arch.write_bytes((plan["archive_header"] + plan["archived_text"]).encode("utf-8"))
        before = (spec / "_log.md").read_bytes()
        res = run(spec)
        if res.returncode != 2 or "leftover" not in res.stderr or "safe to delete" not in res.stderr:
            problems.append(f"leftover_archive_is_named: no leftover message ({res.returncode}): {res.stderr}")
        if (spec / "_log.md").read_bytes() != before:
            problems.append("leftover_archive_is_named: _log.md changed")
        arch.write_bytes(b"other")
        res = run(spec)
        if "leftover" in res.stderr or res.returncode != 2:
            problems.append(f"leftover_archive_is_named: a different archive was called a leftover: {res.stderr}")
        arch.unlink()
        (spec / "_log.md.abc123.tmp").write_bytes(b"junk")
        (spec / (plan["archive_name"] + ".zz.tmp")).write_bytes(b"junk")
        res = run(spec)
        if res.returncode != 0 or stray_files(spec):
            problems.append(f"leftover_archive_is_named: stale tmp files kept ({res.returncode}): {stray_files(spec)}")
    return problems


def oserror_restores_from_orig() -> list[str]:
    problems = []
    with tempfile.TemporaryDirectory() as tmp:
        spec = make_spec(tmp)
        plan = plan_of(spec)
        original = (spec / "_log.md").read_bytes()

        def boom(d: Path) -> None:
            raise OSError("disk went away")

        code, lines = rotate.execute(spec, plan, after_write=boom)
        if code != 1 or "disk went away" not in " ".join(lines):
            problems.append(f"oserror_restores_from_orig: expected 1 + the error, got {code}: {lines}")
        if (spec / "_log.md").read_bytes() != original:
            problems.append("oserror_restores_from_orig: _log.md was not restored")
        if (spec / plan["archive_name"]).exists() or stray_files(spec):
            problems.append("oserror_restores_from_orig: archive / temp left behind")
        # a leftover backup of an earlier run is never overwritten
        (spec / "_log.md.orig").write_bytes(b"precious")
        res = run(spec)
        if res.returncode != 2 or "_log.md.orig" not in res.stderr or (spec / "_log.md.orig").read_bytes() != b"precious":
            problems.append(f"oserror_restores_from_orig: existing .orig not protected ({res.returncode}): {res.stderr}")
    return problems


def dry_prints_no_shell_block() -> list[str]:
    problems = []
    with tempfile.TemporaryDirectory() as tmp:
        spec = make_spec(tmp)
        out = run(spec, "--dry").stdout
        if "```" in out or "sed -n" in out:
            problems.append(f"dry_prints_no_shell_block: the sh block was printed:\n{out}")
        for word in ("cut:", "archive:", "keep:", "round:", "stage:", "**Archived:**"):
            if word not in out:
                problems.append(f"dry_prints_no_shell_block: {word!r} missing")
    return problems


CHECKS = [
    rotates_and_reassembles, dry_writes_nothing, archive_exists_refused,
    log_changed_since_plan, no_open_stub_refused, unsafe_path_is_just_a_path,
    nothing_to_rotate_exits_0, failed_verification_restores, entry_lines_pass_check_16,
    modes_are_kept, symlink_log_refused, log_changed_during_archive_write,
    leftover_archive_is_named, oserror_restores_from_orig, dry_prints_no_shell_block,
]


def main() -> int:
    verbose = "-v" in sys.argv[1:]
    failures: list[str] = []
    for fn in CHECKS:
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
