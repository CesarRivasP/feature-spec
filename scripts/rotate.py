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


def _atomic_write(path: Path, data: bytes) -> None:
    """Temp file in the same dir, then os.replace — a reader sees old or new, never half."""
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


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
            after_write: Callable[[Path], None] | None = None) -> tuple[int, list[str]]:
    """-> (exit code, lines to print). `before_write` runs after the plan is made and
    before the log is re-read (a test changes `_log.md` there); `after_write` runs
    after both files are written and before they are verified."""
    log_path = spec_dir / "_log.md"
    archive_path = spec_dir / plan["archive_name"]
    archive_data = (plan["archive_header"] + plan["archived_text"]).encode("utf-8")
    new_log = plan["kept_text"].encode("utf-8")

    if not plan["rotate_open"]:
        return 2, [f"rotate.py: the last entry of _log.md is not an open rotation stub "
                   f"(`## R{plan['next_n']} · {plan['today']} · <agent> · rotate`) — open it "
                   f"BEFORE rotating (handoff.md step 1); nothing written"]
    if dry:
        return 0, ["dry run — nothing written; after a real run, paste:",
                   *report_lines(plan, archive_data, new_log), FOLLOW_UP]

    if before_write:
        before_write(spec_dir)
    if archive_path.exists():
        return 2, [f"rotate.py: archive {plan['archive_name']} already exists; nothing written"]
    try:
        current = log_path.read_bytes()
    except OSError as exc:
        return 2, [f"rotate.py: cannot re-read _log.md: {exc}; nothing written"]
    if current != plan["raw_bytes"]:
        return 2, ["rotate.py: _log.md changed since the plan was made; nothing written — run again"]

    original = plan["raw_bytes"]
    try:
        _atomic_write(archive_path, archive_data)
        _atomic_write(log_path, new_log)
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
    else:
        err = ""
    if not ok:
        _atomic_write(log_path, original)
        try:
            archive_path.unlink()
        except FileNotFoundError:
            pass
        return 1, [f"rotate.py: verification failed{err} — original _log.md restored, "
                   f"archive removed"]
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

    code, plan = audit.rotate_plan_data(facts, spec_dir, today=today)
    if not isinstance(plan, dict):
        if code == 0:
            print(plan)
            return 0
        print(plan.replace("--rotate-plan:", "rotate.py:", 1), file=sys.stderr)
        return 2
    if args.dry:
        code_p, text = audit.rotate_plan(facts, spec_dir, today=today)
        print(text)
        print()
    code, lines = execute(spec_dir, plan, dry=args.dry)
    print("\n".join(lines), file=sys.stderr if code else sys.stdout)
    return code


if __name__ == "__main__":
    sys.exit(main())
