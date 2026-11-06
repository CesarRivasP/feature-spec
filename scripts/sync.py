#!/usr/bin/env python3
"""sync.py — propagate changed registry values into the docs, as a command.

    python3 scripts/sync.py docs/features/<slug>/ [--from REF | --from-file PATH]
                            [--apply] [--repo-root DIR]
    python3 scripts/sync.py docs/features/<slug>/ --init-base [--force]

`sync` moves data, not shape (`references/mode-sync.md`). The data half is
mechanical, so it is a script and not an agent reading every doc:

1. Old values come from the first base that exists: `--from-file PATH`, `--from REF`
   (`git show`), `_facts.yml`'s snapshot `_facts.synced.yml` beside it, or git HEAD when
   `_facts.yml` is tracked and not ignored. The first output line names the base used.
   `--init-base` writes the snapshot (a byte copy of the registry). New values come
   from the file on disk. Both go through `render.collect_datums` / `render.walk`
   — the same notion of "a datum cited in prose" the provenance view and the audit use.
2. Every registry path whose value changed has its old value searched in the docs
   whose stage the set has reached (`audit.resolve_stage`), with the word boundaries
   of `render.build_datum_regex`, and replaced by the new one. One pass over all
   values, so `A -> B` and `B -> C` never chain.
3. Nothing is guessed. An old value is NOT replaced, and is reported instead, when it
   is shared by several registry paths, is a word-bounded part of another datum, is
   shorter than 3 characters, or has no new value. Exit 1 if any such value actually
   occurs in a doc.
4. `role: legacy` / `role: derived` docs and `_log.md` are never written; a changed
   value they still carry is listed as "not written". A `decisions.*` entry whose
   content changed is never touched — it is listed with its `cited_in:` for a human.

Without `--apply` it is a dry run: the plan is printed, nothing is written. Edits are
text edits on the doc files (same pattern as `ship.py`), never a YAML dump.

`--apply` writes safely: each doc is re-read just before it is written and compared
byte for byte with what the plan was built from; a doc that changed in between is NOT
written ("changed since plan, re-run", exit 1) while the others are. Each write goes to
a temp file in the same directory and is moved over the doc with `os.replace`, keeping
the doc's permissions.

After `--apply` the snapshot, if there is one, is overwritten with the current
registry ONLY when the run was fully clean (exit 0); otherwise it is kept, so the
unapplied changes stay visible next run. A dry run never writes it.

Exit 0 = ok (applied or nothing to do), 1 = ambiguous values left unapplied or a doc
changed since the plan, 2 = usage / git / YAML error.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import tempfile
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import render  # noqa: E402
from audit import (confined, load_facts, norm, repo_root_for,  # noqa: E402
                   resolve_stage, version_stamp, yaml, yaml_error_report)
from ship import Edit  # noqa: E402

UNWRITABLE_ROLES = {"legacy", "derived"}
NEVER_WRITTEN = {"_log.md", "_facts.yml", "_facts.synced.yml"}
SNAPSHOT = "_facts.synced.yml"
MIN_LEN = 3


def git_ok(spec_dir: Path, *cmd: str) -> bool:
    try:
        return subprocess.run(["git", *cmd], cwd=spec_dir, capture_output=True
                              ).returncode == 0
    except FileNotFoundError:
        return False


def write_atomic(path: Path, text: str | bytes) -> None:
    """Temp file in the same directory + os.replace, keeping the doc's permissions."""
    data = text if isinstance(text, bytes) else text.encode("utf-8")
    mode = path.stat().st_mode & 0o7777 if path.exists() else 0o644
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def parse_old(text: str, label: str) -> tuple[dict | None, str]:
    try:
        loaded = yaml.safe_load(text) or {}
    except yaml.YAMLError:
        try:
            docs = [d for d in yaml.safe_load_all(text) if isinstance(d, dict)]
        except yaml.YAMLError as exc:
            return None, f"_facts.yml at {label} is not valid YAML — {exc}"
        loaded = docs[-1] if docs else {}
    if not isinstance(loaded, dict):
        return None, f"_facts.yml at {label} is not a mapping"
    return loaded, ""


def load_old(spec_dir: Path, ref: str) -> tuple[dict | None, str]:
    """-> (facts at REF, error). `./` makes git resolve the path against the cwd."""
    try:
        out = subprocess.run(["git", "show", f"{ref}:./_facts.yml"], cwd=spec_dir,
                             capture_output=True, text=True)
    except FileNotFoundError:
        return None, "git is not installed"
    if out.returncode != 0:
        why = out.stderr.strip().splitlines()[-1] if out.stderr.strip() else "git show failed"
        return None, f"cannot read _facts.yml at {ref}: {why}"
    return parse_old(out.stdout, ref)


def load_file(path: Path) -> tuple[dict | None, str]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return None, f"cannot read {path}: {exc}"
    return parse_old(text, str(path))


def git_tracked(spec_dir: Path) -> bool:
    return (git_ok(spec_dir, "ls-files", "--error-unmatch", "--", "_facts.yml")
            and not git_ok(spec_dir, "check-ignore", "-q", "--", "_facts.yml"))


def scalar_text(node) -> str | None:
    if node is None or isinstance(node, (bool, dict, list)):
        return None
    return str(node).strip()


def value_map(facts: dict) -> dict[str, str]:
    """{path: value} for every datum `render.collect_datums` keeps."""
    return {p: v for v, paths in render.collect_datums(facts).items() for p in paths}


def changed_values(old: dict, new: dict) -> list[dict]:
    """Every scalar registry path whose value differs between REF and disk."""
    old_map, new_map = value_map(old), value_map(new)
    new_nodes = dict(render.walk(new))
    old_nodes = dict(render.walk(old))
    paths = list(old_map)
    # Short values never become datums; they still drift, and must be reported.
    for path, node in old_nodes.items():
        tail = path.rsplit(".", 1)[-1].split("[")[0]
        text = scalar_text(node)
        if (path in old_map or text is None or tail in render.STOP_KEY_TAILS
                or text.lower() in render.STOP_VALUES or len(text) >= MIN_LEN):
            continue
        paths.append(path)
    out = []
    for path in paths:
        if path.startswith("decisions.") or path.startswith(render.STOP_PATH_PREFIXES):
            continue
        old_v = old_map.get(path) or scalar_text(old_nodes.get(path))
        new_v = new_map.get(path)
        if new_v is None:
            new_v = scalar_text(new_nodes.get(path))
        if not old_v or old_v == new_v:
            continue
        out.append({"path": path, "old": old_v, "new": new_v})
    return out


def decisions_changed(old: dict, new: dict) -> list[dict]:
    od = old.get("decisions") if isinstance(old.get("decisions"), dict) else {}
    nd = new.get("decisions") if isinstance(new.get("decisions"), dict) else {}
    out = []
    for key in list(nd) + [k for k in od if k not in nd]:
        if od.get(key) == nd.get(key):
            continue
        entry = nd.get(key) if key in nd else od.get(key)
        cited = entry.get("cited_in") if isinstance(entry, dict) else None
        state = "added" if key not in od else "removed" if key not in nd else "changed"
        out.append({"key": key, "state": state,
                    "cited_in": [str(c) for c in cited] if isinstance(cited, list) else []})
    return out


def classify(changes: list[dict], old: dict, new: dict
             ) -> tuple[dict[str, str], list[dict]]:
    """-> ({old value: new value} safe to replace, ambiguous changes with a reason)."""
    old_datums = render.collect_datums(old)
    all_values = set(old_datums) | set(render.collect_datums(new))
    safe: dict[str, str] = {}
    ambiguous: list[dict] = []
    for ch in changes:
        old_v, new_v = ch["old"], ch["new"]
        reason = None
        if new_v is None or new_v == "":
            reason = "no new value in the registry (removed or not a scalar)"
        elif len(old_v) < MIN_LEN:
            reason = f"old value is shorter than {MIN_LEN} characters"
        elif len(old_datums.get(old_v, [ch["path"]])) > 1:
            reason = ("old value is shared by several registry paths: "
                      + ", ".join(old_datums[old_v]))
        else:
            rx = render.build_datum_regex({old_v: []})
            other = next((v for v in sorted(all_values) if v != old_v and rx.search(v)),
                         None)
            if other is not None:
                reason = f"old value is part of another datum ({other!r})"
        if reason:
            ambiguous.append({**ch, "reason": reason})
        elif old_v in safe and safe[old_v] != new_v:
            ambiguous.append({**ch, "reason": "same old value maps to two new values"})
        else:
            safe[old_v] = new_v
    return safe, ambiguous


def occurrences(text: str, values: list[str]) -> dict[str, list[int]]:
    """{value: [1-based line numbers]} with the word boundaries of the provenance view."""
    found: dict[str, list[int]] = {}
    for value in values:
        rx = render.build_datum_regex({value: []})
        for n, line in enumerate(text.split("\n"), 1):
            if rx.search(line):
                found.setdefault(value, []).append(n)
    return found


def fmt_lines(lines: list[int]) -> str:
    return ", ".join(str(n) for n in lines)


def main(argv: list[str] | None = None, before_write=None) -> int:
    """`before_write(paths)` is a test seam: called after the plan is built and before
    the stale re-read, so a test can change a doc in between without sleeping."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("spec_dir")
    ap.add_argument("--from", dest="ref", default=None, metavar="REF",
                    help="git ref holding the OLD _facts.yml (explicit)")
    ap.add_argument("--from-file", default=None, metavar="PATH",
                    help="file holding the OLD _facts.yml")
    ap.add_argument("--init-base", action="store_true",
                    help=f"write {SNAPSHOT} as a byte copy of _facts.yml and exit")
    ap.add_argument("--force", action="store_true",
                    help="with --init-base: overwrite an existing snapshot")
    ap.add_argument("--apply", action="store_true",
                    help="write the replacements (default: dry run, print the plan)")
    ap.add_argument("--repo-root", default=None)
    args = ap.parse_args(argv)

    spec_dir = Path(args.spec_dir).resolve()
    facts_path = spec_dir / "_facts.yml"
    if not facts_path.is_file():
        print(f"no _facts.yml in {spec_dir} — not a feature-spec set.", file=sys.stderr)
        return 2
    try:
        new = load_facts(facts_path)
    except yaml.YAMLError as exc:
        print(yaml_error_report(facts_path, exc), file=sys.stderr)
        return 2
    snap_path = spec_dir / SNAPSHOT
    if args.init_base:
        if snap_path.exists() and not args.force:
            print(f"{snap_path} already exists — pass --force to overwrite it.",
                  file=sys.stderr)
            return 2
        write_atomic(snap_path, facts_path.read_bytes())
        print(snap_path)
        return 0
    if args.ref is not None and args.from_file is not None:
        print("pass --from or --from-file, not both.", file=sys.stderr)
        return 2
    if args.from_file is not None:
        base = f"file {args.from_file}"
        old, err = load_file(Path(args.from_file))
    elif args.ref is not None:
        base = f"git {args.ref}"
        old, err = load_old(spec_dir, args.ref)
    elif snap_path.is_file():
        base = f"snapshot {SNAPSHOT}"
        old, err = load_file(snap_path)
    elif git_tracked(spec_dir):
        base = "git HEAD"
        old, err = load_old(spec_dir, "HEAD")
    else:
        old, err = None, ("no base to compare with: _facts.yml is not tracked by git "
                          "(or is ignored) and there is no " + SNAPSHOT + ". Run "
                          "--init-base (only when the docs match the registry), pass "
                          "--from-file PATH, or pass --from <ref> naming a ref where "
                          "it exists")
    if old is None:
        print(err, file=sys.stderr)
        return 2
    ref_label = base
    print(f"base: {base}")
    repo_root_for(spec_dir, args.repo_root)  # same root resolution as the other modes

    changes = changed_values(old, new)
    base_same = old == new and base.startswith("git ") and git_ok(
        spec_dir, "diff", "--quiet", "HEAD", "--", "_facts.yml")
    decisions = decisions_changed(old, new)
    safe, ambiguous = classify(changes, old, new)

    _, in_scope, deferred = resolve_stage(new, spec_dir)
    roles = {str(e.get("file", "")): norm(e.get("role"))
             for e in new.get("docs") or [] if isinstance(e, dict)}
    writable, not_written = [], []
    for d in in_scope:
        path = confined(spec_dir, d["file"])
        if path is None or not path.is_file() or path.name in NEVER_WRITTEN:
            continue
        (not_written if roles.get(d["file"]) in UNWRITABLE_ROLES else writable
         ).append((d, path))

    mode = "applied" if args.apply else "DRY RUN, nothing written"
    print(f"# sync — {new.get('feature', spec_dir.name)}: {len(changes)} changed "
          f"value{'s' if len(changes) != 1 else ''} since {ref_label} ({mode})\n")
    for ch in changes:
        print(f"  {ch['path']}: {ch['old']!r} → {ch['new']!r}")
    if changes:
        print()
    elif base_same:
        print(f"WARNING: the registry at {args.ref or "HEAD"} is identical to the one on disk, "
              "and _facts.yml has no uncommitted changes. If the change was already "
              "committed, pass --from <previous ref> (e.g. --from HEAD~1).\n")

    edits: list[tuple[Edit, int, list[int]]] = []
    plan_bytes: dict[Path, bytes] = {}
    rx = render.build_datum_regex({v: [] for v in safe})
    for d, path in writable:
        raw = path.read_bytes()
        ed = Edit(path)
        count, hit_lines = 0, []
        for i, line in enumerate(ed.lines):
            replaced, n = (rx.subn(lambda m: safe[m.group(0)], line) if rx else (line, 0))
            if n:
                ed.lines[i] = replaced
                count += n
                hit_lines.append(i + 1)
        if count:
            edits.append((ed, count, hit_lines))
            plan_bytes[path] = raw
            print(f"{path.name}: {count} replacement{'s' if count != 1 else ''} "
                  f"(lines {fmt_lines(hit_lines)})")
        else:
            print(f"{path.name}: 0 replacements")

    # ambiguous values that actually bite somewhere
    scanned = [(p, p.read_text(encoding="utf-8")) for _, p in writable + not_written]
    bites = []
    for amb in ambiguous:
        where = [(p.name, occ[amb["old"]]) for p, text in scanned
                 if (occ := occurrences(text, [amb["old"]]))]
        if where:
            bites.append((amb, where))
    if bites:
        print("\nAmbiguous — NOT replaced, resolve by hand:")
        for amb, where in bites:
            print(f"  {amb['path']}: {amb['old']!r} → {amb['new']!r} — {amb['reason']}")
            for name, lines in where:
                print(f"      {name} lines {fmt_lines(lines)}")

    unwritten = []
    for d, path in not_written:
        occ = occurrences(path.read_text(encoding="utf-8"),
                          sorted({c["old"] for c in changes if len(c["old"]) >= 1}))
        if occ:
            unwritten.append((d, occ))
    if unwritten:
        print("\nNot written (role: legacy / derived — regenerate, don't patch):")
        for d, occ in unwritten:
            print(f"  {d['file']} ({roles.get(d['file'])}): "
                  + "; ".join(f"{v!r} at lines {fmt_lines(ls)}" for v, ls in occ.items()))

    if decisions:
        print("\nNeeds a human (sync --decision):")
        for dec in decisions:
            cited = ", ".join(dec["cited_in"]) if dec["cited_in"] else "no cited_in:"
            print(f"  decisions.{dec['key']} ({dec['state']}) — cited_in: {cited}")

    if deferred:
        print("\nOut of scope (stage not reached, file not on disk): "
              + ", ".join(f"{d['file']} (stage {d['stage']})" for d in deferred))

    stale: list[str] = []
    if args.apply:
        if before_write is not None:
            before_write([ed.path for ed, _, _ in edits])
        written = []
        for ed, _, _ in edits:
            try:
                unchanged = ed.path.read_bytes() == plan_bytes[ed.path]
            except OSError:
                unchanged = False
            if not unchanged:
                stale.append(ed.path.name)
                continue
            write_atomic(ed.path, ed.after)
            written.append(ed)
        if stale:
            print("\nChanged since plan, NOT written, re-run: " + ", ".join(stale))
        if written:
            print("\n**Edits:** " + " · ".join(
                version_stamp(ed.path.name, ed.after.encode("utf-8")) for ed in written))
        else:
            print("\nNothing written.")
        if snap_path.is_file() or base.startswith("snapshot"):
            if bites or stale:
                print(f"\n{SNAPSHOT} kept as is: the run was not clean, so the "
                      "unapplied changes show again next run.")
            else:
                write_atomic(snap_path, facts_path.read_bytes())
                print(f"\n{SNAPSHOT} updated to the current registry.")
    elif edits:
        print("\nDry run — re-run with --apply to write "
              + ", ".join(f"{ed.path.name} ({n})" for ed, n, _ in edits) + ".")
    return 1 if bites or stale else 0


if __name__ == "__main__":
    raise SystemExit(main())
