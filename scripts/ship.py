#!/usr/bin/env python3
"""ship.py — the flip to `status: shipped`, done once instead of six times.

    python3 scripts/ship.py docs/features/<slug>/ --tag <release tag>
                            [--on YYYY-MM-DD] [--url <release page>] [--note TEXT]
                            [--dry] [--repo-root DIR] [--today YYYY-MM-DD]

Real case: flipping one set to `shipped` was six hand edits across two files —
`status:`, `tracking.shipped_in`, the new `dates.revisions[]` entry, doc 01's
changelog and `Estado:` line, the defect that had to read `fixed` first — plus the
`Stage:` line, plus three re-stamps of `Edits:` because every edit to the registry
invalidated the previous one. Half a round, for a transition whose every step is
known in advance. The release URL and the publication date went into a YAML comment
because `shipped_in:` was the only field there was.

What this does, in order, and refuses to do out of order:

1. Reads the registry. A YAML error names its line and column and nothing else runs.
2. Runs the gates the flip is subject to — G1 and check 14's shipped-set detectors,
   check 26's acceptance state — AS IF `status:` already read `shipped`. Any
   `CONTRADICTION` and the script refuses, listing them: a root cause still
   `asserted`, a defect still `open` with no `outcome:`, a criterion never verified.
   Those are the edits that need a person; the script names them and stops.
3. Edits `_facts.yml` IN PLACE, as text, so every comment survives: `status:`,
   `tracking.shipped_in` / `shipped_on` / `release_url`, and one appended
   `dates.revisions[]` entry. Then doc 01: the changelog entry (prepended, newest
   first — the opposite order from the registry, see check 40) and its `Estado:`.
4. Prints the two log lines the round's entry needs, measured after the edits:
   `**Stage:** <from> → shipped — …` and `**Edits:**` with each file's line count
   and blob. The entry itself is the agent's — stub first, as every round.

`--dry` prints the edits as a diff and writes nothing. The log is never written: a
round opens its own stub before calling this, and completes it with the lines this
prints. Exit 0 = shipped, 2 = refused (gate or already shipped), 3 = cannot edit.
"""
from __future__ import annotations

import argparse
import datetime
import difflib
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from audit import (CHANGELOG_HEADING, CONTRADICTION, STATUS_RANK, Findings,  # noqa: E402
                   check_acceptance_state, check_basis_gates, confined, git_blob,
                   load_facts, norm, repo_root_for, revision_number,
                   version_stamp, yaml, yaml_error_report)

INDENT_RE = re.compile(r"^(\s*)")


def indent_of(line: str) -> int:
    return len(INDENT_RE.match(line).group(1))


def block_span(lines: list[str], start: int) -> int:
    """-> index one past the last line of the mapping/list that starts at `start`
    (a key line). Children are the following lines indented deeper, plus blank and
    comment lines inside them; a comment at the parent's indent ends the block."""
    base = indent_of(lines[start])
    i = start + 1
    while i < len(lines):
        stripped = lines[i].strip()
        if stripped and not stripped.startswith("#") and indent_of(lines[i]) <= base:
            break
        if stripped.startswith("#") and indent_of(lines[i]) <= base:
            break
        i += 1
    # Trailing blanks belong to whoever comes next.
    while i > start + 1 and not lines[i - 1].strip():
        i -= 1
    return i


def find_key(lines: list[str], key: str, lo: int, hi: int, indent: int | None = None
             ) -> int | None:
    pat = re.compile(rf"^(\s*){re.escape(key)}\s*:")
    for i in range(lo, hi):
        m = pat.match(lines[i])
        if m and (indent is None or len(m.group(1)) == indent):
            return i
    return None


def set_scalar(line: str, key: str, value: str) -> str:
    """Replace the value on a `key: value   # comment` line, keeping the comment."""
    m = re.match(rf"^(\s*{re.escape(key)}\s*:\s*)([^#]*?)(\s*#.*)?$", line)
    if not m:
        return line
    return f"{m.group(1)}{value}{m.group(3) or ''}"


def yaml_scalar(value: str) -> str:
    """Quote the way the registry's own convention asks: single quotes, doubled
    inside — the one shape check 1's quoting rule never flags."""
    if re.fullmatch(r"[\w./:-]+", value):
        return value
    return "'" + value.replace("'", "''") + "'"


class Edit:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.before = path.read_text(encoding="utf-8")
        self.lines = self.before.split("\n")
        self.notes: list[str] = []

    @property
    def after(self) -> str:
        return "\n".join(self.lines)

    def changed(self) -> bool:
        return self.after != self.before

    def diff(self) -> str:
        return "".join(difflib.unified_diff(
            self.before.splitlines(True), self.after.splitlines(True),
            f"a/{self.path.name}", f"b/{self.path.name}"))


def edit_registry(ed: Edit, status_from: str, tag: str, on: str, url: str | None,
                  note: str) -> str | None:
    """-> the new revision tag, or None when `dates.revisions[]` is not there."""
    L = ed.lines
    i = find_key(L, "status", 0, len(L), indent=0)
    if i is None:
        raise SystemExit(f"{ed.path.name}: no top-level `status:` line to edit")
    L[i] = set_scalar(L[i], "status", "shipped")
    ed.notes.append(f"status: {status_from} → shipped")

    # tracking block — create it after status if the set never had one
    t = find_key(L, "tracking", 0, len(L), indent=0)
    if t is None:
        L[i + 1:i + 1] = ["tracking:", f"  shipped_in: {yaml_scalar(tag)}"]
        t = i + 1
        ed.notes.append("tracking: (new block)")
    end = block_span(L, t)
    child_indent = next((indent_of(L[k]) for k in range(t + 1, end)
                         if L[k].strip() and not L[k].strip().startswith("#")), 2)
    pad = " " * child_indent
    fields = [("shipped_in", yaml_scalar(tag)), ("shipped_on", on)]
    if url:
        fields.append(("release_url", yaml_scalar(url)))
    anchor = t
    for key, value in fields:
        k = find_key(L, key, t + 1, end, indent=child_indent)
        if k is None:
            L.insert(anchor + 1, f"{pad}{key}: {value}")
            end += 1
            anchor += 1
        else:
            L[k] = set_scalar(L[k], key, value)
            anchor = k
        ed.notes.append(f"tracking.{key}: {value}")

    # dates.revisions[] — append, oldest first
    d = find_key(L, "dates", 0, len(L), indent=0)
    if d is None:
        return None
    dend = block_span(L, d)
    r = find_key(L, "revisions", d + 1, dend)
    if r is None:
        return None
    rend = block_span(L, r)
    item_re = re.compile(r"^(\s*)-\s")
    items = [k for k in range(r + 1, rend) if item_re.match(L[k])]
    numbers = []
    for k in range(r + 1, rend):
        m = re.search(r"\btag:\s*['\"]?([\w.]+)", L[k])
        if m and revision_number(m.group(1)) is not None:
            numbers.append(revision_number(m.group(1)))
    nxt = f"v{(max(numbers) + 1) if numbers else 1}"
    if items:
        item_pad = item_re.match(L[items[-1]]).group(1)
        insert_at = rend
    else:
        item_pad = " " * (indent_of(L[r]) + 2)
        insert_at = r + 1
        # an empty `revisions: []` becomes a list
        L[r] = re.sub(r":\s*\[\s*\].*$", ":", L[r])
    L.insert(insert_at, f"{item_pad}- {{ tag: {nxt}, date: {on}, note: {yaml_scalar(note)} }}")
    ed.notes.append(f"dates.revisions[]: + {nxt} ({on})")
    return nxt


def edit_doc01(ed: Edit, rev: str | None, on: str, note: str) -> None:
    L = ed.lines
    for k, line in enumerate(L):
        m = re.match(r"^(\s*[-*]\s*\*\*(?:Estado|Status)\s*:\*\*\s*)(\S+)(.*)$", line)
        if m:
            L[k] = f"{m.group(1)}shipped{m.group(3)}"
            ed.notes.append(f"line {k + 1}: Estado → shipped")
            break
    if rev is None:
        return
    text = ed.after
    m = CHANGELOG_HEADING.search(text)
    if not m:
        ed.notes.append("no `## Changelog` heading — add the entry by hand: "
                        f"`### {on} — {rev}: {note}`")
        return
    head = text[:m.start()].count("\n")
    k = head + 1
    # skip the template's comment and blank lines under the heading
    while k < len(L) and (not L[k].strip() or L[k].strip().startswith("<!--")):
        if L[k].strip().startswith("<!--") and "-->" not in L[k]:
            while k < len(L) and "-->" not in L[k]:
                k += 1
        k += 1
    if k < len(L) and L[k].lstrip().startswith("|"):
        # table: header row, separator, then rows newest first
        header = [c.strip().lower() for c in L[k].strip().strip("|").split("|")]
        sep = k + 1
        if sep >= len(L) or not re.match(r"^\s*\|?\s*:?-", L[sep]):
            ed.notes.append("changelog table has no separator row — add the entry by "
                            f"hand: `{rev}` · {on} · {note}")
            return
        cells = []
        for col in header:
            if re.search(r"tag|versi|version|rev", col):
                cells.append(f"`{rev}`")
            elif re.search(r"fecha|date|día|dia", col):
                cells.append(on)
            else:
                cells.append(note)
        L.insert(sep + 1, "| " + " | ".join(cells) + " |")
        ed.notes.append(f"line {sep + 2}: changelog row {rev}")
    else:
        L[k:k] = [f"### {on} — {rev}: {note}", ""]
        ed.notes.append(f"line {k + 1}: changelog entry {rev}")


def gate(facts: dict, today: datetime.date | None) -> list[dict]:
    preview = dict(facts)
    preview["status"] = "shipped"
    f = Findings()
    check_basis_gates(preview, f, today)
    check_acceptance_state(preview, STATUS_RANK["shipped"], f)
    return [x for x in f.items if x["severity"] == CONTRADICTION]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("spec_dir")
    ap.add_argument("--tag", required=True, help="the release tag, e.g. v1.4.1")
    ap.add_argument("--on", default=None, metavar="YYYY-MM-DD",
                    help="publication date (default: today)")
    ap.add_argument("--url", default=None, help="the release page")
    ap.add_argument("--note", default=None,
                    help="the revision note (default: `shipped in <tag>`)")
    ap.add_argument("--dry", action="store_true", help="print the diff, write nothing")
    ap.add_argument("--repo-root", default=None)
    ap.add_argument("--today", default=None, metavar="YYYY-MM-DD",
                    help="the date G1's `accepted.until:` is measured against")
    args = ap.parse_args(argv)

    def date_arg(value: str | None, flag: str) -> datetime.date | None:
        if value is None:
            return None
        try:
            return datetime.date.fromisoformat(value)
        except ValueError:
            ap.error(f"{flag} {value!r} is not a YYYY-MM-DD date")

    today = date_arg(args.today, "--today")
    on = (date_arg(args.on, "--on") or datetime.date.today()).isoformat()
    note = args.note or f"shipped in {args.tag}"

    spec_dir = Path(args.spec_dir).resolve()
    facts_path = spec_dir / "_facts.yml"
    if not facts_path.is_file():
        print(f"no _facts.yml in {spec_dir} — not a feature-spec set.", file=sys.stderr)
        return 3
    try:
        facts = load_facts(facts_path)
    except yaml.YAMLError as exc:
        print(yaml_error_report(facts_path, exc), file=sys.stderr)
        return 3
    repo_root, _ = repo_root_for(spec_dir, args.repo_root)

    status_from = norm(facts.get("status")) or "draft"
    if status_from == "shipped":
        tracking = facts.get("tracking") if isinstance(facts.get("tracking"), dict) else {}
        print(f"refused — already `status: shipped`"
              + (f" in `{tracking['shipped_in']}`" if tracking.get("shipped_in") else "")
              + ". Nothing to flip.", file=sys.stderr)
        return 2

    blocking = gate(facts, today)
    if blocking:
        print(f"refused — `shipped` is gated, and {len(blocking)} CONTRADICTION"
              f"{'s' if len(blocking) > 1 else ''} would fire the moment it flips:\n",
              file=sys.stderr)
        for x in blocking:
            print(f"  {x['where']}: {x['what']}. {x['fix']}.\n      └ check {x['check']}",
                  file=sys.stderr)
        print("\nSettle them in the registry — `status: fixed` with its evidence, an "
              "`outcome:`, a verified or retired criterion — then run this again. "
              "`audit.py <dir> --as-status shipped` previews the same list.",
              file=sys.stderr)
        return 2

    registry = Edit(facts_path)
    rev = edit_registry(registry, status_from, args.tag, on, args.url, note)
    edits = [registry]
    doc01 = next((e for e in facts.get("docs") or [] if isinstance(e, dict)
                  and (norm(e.get("role")) == "master-plan" or str(e.get("id")) == "01")),
                 None)
    # The registry is input: `docs[].file` is joined onto the spec dir and refused
    # if it leaves it — this script WRITES to that path, so the boundary matters
    # more here than in the checks that only read.
    doc01_path = confined(spec_dir, str(doc01.get("file", ""))) if doc01 else None
    if doc01 and doc01_path is None:
        print(f"refused — docs[] `{doc01.get('file')}` resolves outside the spec dir; "
              "nothing written", file=sys.stderr)
        return 3
    if doc01_path is not None and doc01_path.is_file():
        d = Edit(doc01_path)
        edit_doc01(d, rev, on, note)
        edits.append(d)
    if rev is None:
        registry.notes.append("no `dates.revisions:` list — add the revision by hand")

    print(f"# ship — {facts.get('feature', spec_dir.name)}: {status_from} → shipped in "
          f"`{args.tag}` ({on}){' — DRY RUN, nothing written' if args.dry else ''}\n")
    for ed in edits:
        print(f"{ed.path.name}:")
        for n in ed.notes:
            print(f"  - {n}")
    print()
    if args.dry:
        for ed in edits:
            if ed.changed():
                print(ed.diff())
    else:
        for ed in edits:
            if ed.changed():
                ed.path.write_text(ed.after, encoding="utf-8")

    stamps = []
    for ed in edits:
        if not ed.changed():
            continue
        stamps.append(version_stamp(ed.path.name, ed.after.encode("utf-8")))
    print("Paste into the round's entry in `_log.md` — the stub is already open, "
          "this completes it:\n")
    print(f"**Stage:** {status_from} → shipped — shipped in `{args.tag}` on {on}"
          + (f", {args.url}" if args.url else ""))
    print("**Edits:** " + " · ".join(stamps))
    print("\nThen `python3 scripts/audit.py " + str(spec_dir) + "` — the Stage line "
          "above is what check 16 reads.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
