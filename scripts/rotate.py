#!/usr/bin/env python3
"""rotate.py — executes the `_log.md` rotation that `audit.py --rotate-plan` only prints.

Pasting the plan's shell commands failed in real use (unquoted paths, v1.21.1). The
byte move is mechanical, so it is done here; completing the rotation round (`Read:`,
`Stage:`, `Archived:`, `Carried open:`) stays the agent's — this script prints the
lines that are measurements and never writes the entry.

    python3 scripts/rotate.py <spec_dir> [--dry] [--today YYYY-MM-DD]

The cut is NOT re-derived: it is `audit.rotate_plan_data`, the same plan
`--rotate-plan` prints. Exit codes: 0 rotated / dry / nothing to rotate; 1 the
written files failed verification (original restored); 2 refused, nothing written.
"""
from __future__ import annotations

import argparse
import datetime
import os
import re
import stat
import sys
import tempfile
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    import audit
except ImportError as exc:  # pragma: no cover
    sys.exit(f"cannot import audit.py, which must sit beside this file: {exc}")
import yaml  # noqa: E402


def _fsync_dir(path: Path) -> None:
    """Make a create / rename durable: the directory entry is data of the directory."""
    fd = os.open(str(path), os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _unlink(path: "str | Path") -> None:
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass


def _write_new(path: Path, data: bytes) -> None:
    """Create `path` (never overwrite) with the umask's default mode, like write_text;
    flushed to disk. A partial file is removed if the write fails."""
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
    except BaseException:
        _unlink(path)
        raise


def _stage(path: Path, data: bytes, mode: int) -> str:
    """Write `data` to a temp file beside `path`, with `mode` (mkstemp makes it 0600,
    which would silently narrow the file it replaces), flushed. -> the temp's path."""
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fchmod(fh.fileno(), mode)
            os.fsync(fh.fileno())
    except BaseException:
        _unlink(tmp)
        raise
    return tmp


def report_lines(plan: dict, archive_data: bytes, log_data: bytes) -> list[str]:
    """The lines the agent pastes into the rotation entry — measured as check 16 will."""
    name = plan["archive_name"]
    arch = audit.version_stamp(name, archive_data)
    stamp = arch[arch.index("("):]
    lines = [
        f"**Archived:** `{name}` {stamp}",
        "**Edits:** " + audit.version_stamp("_log.md", log_data) + " · " + arch,
    ]
    if plan["stage_carry"]:
        lines.append(plan["stage_carry"])
    return lines


FOLLOW_UP = "complete **Read:** and **Carried open:** (handoff.md step 3), then run audit"


def execute(spec_dir: Path, plan: dict, dry: bool = False, *,
            before_write: Callable[[Path], None] | None = None,
            before_replace: Callable[[Path], None] | None = None,
            after_write: Callable[[Path], None] | None = None) -> tuple[int, list[str]]:
    """-> (exit code, lines to print). Hooks exist for tests: `before_write` runs after
    the plan is made and before the log is re-read (a test changes `_log.md` there);
    `before_replace` after the archive is on disk and before the log is swapped;
    `after_write` after both files are written and before they are verified.

    Order: `_log.md.orig` (byte copy) -> archive (flushed, dir flushed) -> new log in a
    temp (flushed, `_log.md`'s mode) -> re-read `_log.md` and compare to the plan -> replace
    -> dir flushed -> verify -> drop `.orig`. Any failure restores from `.orig`."""
    log_path = spec_dir / "_log.md"
    archive_path = spec_dir / plan["archive_name"]
    orig_path = spec_dir / "_log.md.orig"
    archive_data = (plan["archive_header"] + plan["archived_text"]).encode("utf-8")
    new_log = plan["kept_text"].encode("utf-8")

    if not plan["rotate_open"]:
        return 2, [f"rotate.py: the last entry of _log.md is not an open rotation stub "
                   f"(`## R{plan['next_n']} · {plan['today']} · <agent> · rotate`) — open it "
                   f"BEFORE rotating (handoff.md step 1); nothing written"]
    if log_path.is_symlink():
        return 2, ["rotate.py: _log.md is a symlink; replacing it would cut the link, "
                   "not rotate its target — rotate the real file; nothing written"]
    if dry:
        return 0, ["dry run — nothing written; after a real run, paste:",
                   *report_lines(plan, archive_data, new_log), FOLLOW_UP]

    if before_write:
        before_write(spec_dir)
    if archive_path.exists():
        try:
            same = archive_path.read_bytes() == archive_data
        except OSError:
            same = False
        if same:
            return 2, [f"rotate.py: {plan['archive_name']} already holds exactly the rounds this "
                       f"rotation would move — a leftover of an interrupted run; it is safe to "
                       f"delete (`_log.md` was not replaced); nothing written"]
        return 2, [f"rotate.py: archive {plan['archive_name']} already exists; nothing written"]
    if orig_path.exists():
        return 2, [f"rotate.py: {orig_path.name} exists — the backup of an interrupted run; "
                   f"compare it with _log.md, keep the right one, delete it; nothing written"]
    for stale in [*spec_dir.glob("_log.md.*.tmp"), *spec_dir.glob(plan["archive_name"] + ".*.tmp")]:
        _unlink(stale)  # ours, left by an interrupted run
    try:
        current = log_path.read_bytes()
        mode = stat.S_IMODE(log_path.stat().st_mode)
    except OSError as exc:
        return 2, [f"rotate.py: cannot re-read _log.md: {exc}; nothing written"]
    if current != plan["raw_bytes"]:
        return 2, ["rotate.py: _log.md changed since the plan was made; nothing written — run again"]

    original = plan["raw_bytes"]
    tmp = None
    archived = False
    err = ""
    ok = False
    try:
        _write_new(orig_path, original)
        os.chmod(orig_path, mode)
        _write_new(archive_path, archive_data)
        archived = True
        _fsync_dir(spec_dir)
        tmp = _stage(log_path, new_log, mode)
        if before_replace:
            before_replace(spec_dir)
        if log_path.read_bytes() != original:  # the window since the first check is the archive write
            _unlink(tmp)
            _unlink(archive_path)
            _unlink(orig_path)
            return 2, ["rotate.py: _log.md changed while the archive was written; archive "
                       "removed, nothing else written — run again"]
        os.replace(tmp, log_path)
        tmp = None
        _fsync_dir(spec_dir)
        if after_write:
            after_write(spec_dir)
        got_arch = archive_path.read_bytes()
        got_log = log_path.read_bytes()
        header = plan["archive_header"].encode("utf-8")
        ok = got_arch.startswith(header)
        if ok:
            kept_lines = re.findall(rb"[^\n]*\n", got_log)
            pre = b"".join(kept_lines[:plan["preamble_lines"]])
            tail = b"".join(kept_lines[plan["preamble_lines"]:])
            ok = pre + got_arch[len(header):] + tail == original
    except OSError as exc:
        ok = False
        err = f" ({exc})"
    if not ok:
        if tmp:
            _unlink(tmp)
        restored = False
        try:
            tmp2 = _stage(log_path, orig_path.read_bytes(), mode)
            os.replace(tmp2, log_path)
            _fsync_dir(spec_dir)
            restored = log_path.read_bytes() == original
        except OSError as exc2:
            err += f" (restore: {exc2})"
        if restored:
            _unlink(archive_path)
            _unlink(orig_path)
            return 1, [f"rotate.py: verification failed{err} — original _log.md restored, "
                       f"archive removed"]
        return 1, [f"rotate.py: verification failed{err} — _log.md could NOT be restored; "
                   f"the original is at {orig_path}" + (f", the new archive at {archive_path}"
                                                          if archived else "")]
    _unlink(orig_path)
    return 0, [f"rotated: {plan['archive_name']} (R{plan['first_arch_n']}–R{plan['last_arch_n']}), "
               f"_log.md keeps {plan['kept_lines']} lines; paste into the rotation entry:",
               *report_lines(plan, got_arch, got_log), FOLLOW_UP]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Execute the _log.md rotation audit.py --rotate-plan describes.")
    ap.add_argument("spec_dir")
    ap.add_argument("--dry", action="store_true",
                    help="print the plan and the lines it would print; write nothing")
    ap.add_argument("--today", default=None, metavar="YYYY-MM-DD",
                    help="the date used in the stub the plan names (default: today)")
    args = ap.parse_args(argv)
    today = None
    if args.today:
        try:
            today = datetime.date.fromisoformat(args.today)
        except ValueError:
            ap.error(f"--today {args.today!r} is not a YYYY-MM-DD date")

    spec_dir = Path(args.spec_dir).resolve()
    facts_path = spec_dir / "_facts.yml"
    if not facts_path.is_file():
        print(f"rotate.py: no _facts.yml in {spec_dir} — not a feature-spec set", file=sys.stderr)
        return 2
    try:
        facts = audit.load_facts(facts_path)
    except yaml.YAMLError as exc:
        print(audit.yaml_error_report(facts_path, exc), file=sys.stderr)
        return 2

    code, plan = audit.rotate_plan_data(facts, spec_dir, today=today,
                                        allow_existing_archive=True)
    if not isinstance(plan, dict):
        if code == 0:
            print(plan)
            return 0
        print(plan.replace("--rotate-plan:", "rotate.py:", 1), file=sys.stderr)
        return 2
    if args.dry:
        code_p, text = audit.rotate_plan(facts, spec_dir, today=today)
        if code_p == 0:  # the header only: the ```sh block is for pasting, and this run replaces it
            head = text.split("```sh")[0].splitlines()
            print("\n".join(l for l in head if not l.startswith("before:")))
            print()
    code, lines = execute(spec_dir, plan, dry=args.dry)
    print("\n".join(lines), file=sys.stderr if code else sys.stdout)
    return code


if __name__ == "__main__":
    sys.exit(main())
