#!/usr/bin/env python3
"""facts.py — append attempts to acceptance criteria, and update status in-place.

    python3 scripts/facts.py add-attempt docs/features/<slug>/ <AC-id> \\
        --date YYYY-MM-DD --outcome {aborted_no_conditions,failed,passed} \\
        [--round R<n>] [--env TEXT] [--note TEXT] [--aborted-because TEXT] \\
        [--status {executed,approved}] [--dry] [--repo-root DIR]

Exit codes:
  0 = attempt recorded or already recorded
  2 = refused (validation error, out of order, hand edit required, or audit finding)
  3 = cannot edit (corrupt YAML, unsupported shape, or round-trip mismatch)
"""
from __future__ import annotations

import argparse
import copy
import datetime
import difflib
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from audit import (  # noqa: E402
    ATTEMPT_OUTCOMES,
    STATUS_RANK,
    Findings,
    check_acceptance_state,
    load_facts,
    norm,
    to_date,
    version_stamp,
    yaml,
    yaml_error_report,
)
from ship import Edit, yaml_scalar  # noqa: E402

ROUND_RE = re.compile(r"^R\d+([-\w]*)$")
ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _node_lines(key: Any, value: Any, lines: list[str]) -> tuple[int, int]:
    """1-based inclusive line span of one entry, from the key (or list item) to the
    last line its value occupies."""
    start = (key or value).start_mark.line + 1
    m = value.end_mark
    end = m.line + (1 if m.line < len(lines) and lines[m.line][:m.column].strip() else 0)
    while end > start and (not lines[end - 1].strip() or lines[end - 1].lstrip().startswith("#")):
        end -= 1
    return start, max(start, end)


def has_unsupported_shapes(node: Any) -> bool:
    """Refuse non-standard tags."""
    tag = getattr(node, "tag", None)
    if tag and not tag.startswith("tag:yaml.org,2002:"):
        return True
    if isinstance(node, yaml.MappingNode):
        for k, v in node.value:
            if has_unsupported_shapes(k) or has_unsupported_shapes(v):
                return True
    elif isinstance(node, yaml.SequenceNode):
        for item in node.value:
            if has_unsupported_shapes(item):
                return True
    return False


def format_flow_attempt(
    date: str,
    round_val: str | None,
    outcome: str,
    aborted_because: str | None,
    env: str | None,
    note: str | None,
) -> str:
    parts = [f"date: {date}"]
    if round_val:
        parts.append(f"round: {round_val}")
    parts.append(f"outcome: {outcome}")
    if aborted_because:
        parts.append(f"aborted_because: {yaml_scalar(aborted_because)}")
    if env:
        parts.append(f"env: {yaml_scalar(env)}")
    if note:
        parts.append(f"note: {yaml_scalar(note)}")
    return "{ " + ", ".join(parts) + " }"


def apply_status(text: str, item_node: yaml.MappingNode, status: str, date: str) -> str:
    status_pair = next(
        ((k, v) for k, v in item_node.value if isinstance(k, yaml.ScalarNode) and k.value == "status"),
        None,
    )
    if not status_pair:
        raise ValueError("no `status:` field on criterion")
    status_k, status_v = status_pair

    ver_pair = next(
        ((k, v) for k, v in item_node.value if isinstance(k, yaml.ScalarNode) and k.value == "verified_on"),
        None,
    )

    if ver_pair is not None:
        ver_k, ver_v = ver_pair
        edits = [
            (status_v.start_mark.index, status_v.end_mark.index, status),
            (ver_v.start_mark.index, ver_v.end_mark.index, date),
        ]
        edits.sort(key=lambda x: x[0], reverse=True)
        for s, e, r in edits:
            text = text[:s] + r + text[e:]
        return text
    else:
        if item_node.flow_style:
            rep = f"{status}, verified_on: {date}"
            return text[:status_v.start_mark.index] + rep + text[status_v.end_mark.index:]
        else:
            text = text[:status_v.start_mark.index] + status + text[status_v.end_mark.index:]
            lines = text.split("\n")
            col = status_k.start_mark.column
            line_idx = status_k.start_mark.line
            lines.insert(line_idx + 1, " " * col + f"verified_on: {date}")
            return "\n".join(lines)


def apply_attempt(
    text: str,
    item_node: yaml.MappingNode,
    date: str,
    round_val: str | None,
    outcome: str,
    aborted_because: str | None,
    env: str | None,
    note: str | None,
) -> str:
    flow_str = format_flow_attempt(date, round_val, outcome, aborted_because, env, note)
    att_pair = next(
        ((k, v) for k, v in item_node.value if isinstance(k, yaml.ScalarNode) and k.value == "attempts"),
        None,
    )

    if item_node.flow_style:
        if att_pair is not None:
            att_k, att_v = att_pair
            if not isinstance(att_v, yaml.SequenceNode):
                raise ValueError("`attempts:` must be a sequence")
            if att_v.flow_style:
                if att_v.value:
                    last = att_v.value[-1]
                    insert_text = ",\n" + " " * last.start_mark.column + flow_str
                    return text[:last.end_mark.index] + insert_text + text[last.end_mark.index:]
                else:
                    return (
                        text[:att_v.start_mark.index + 1]
                        + " "
                        + flow_str
                        + " "
                        + text[att_v.end_mark.index - 1:]
                    )
            else:
                raise ValueError("block attempts inside flow item is unsupported; edit by hand")
        else:
            first_k = item_node.value[0][0]
            last_v = item_node.value[-1][1]
            insert_text = ",\n" + " " * first_k.start_mark.column + f"attempts: [ {flow_str} ]"
            return text[:last_v.end_mark.index] + insert_text + text[last_v.end_mark.index:]
    else:
        # block item
        if att_pair is not None:
            att_k, att_v = att_pair
            if not isinstance(att_v, yaml.SequenceNode):
                raise ValueError("`attempts:` must be a sequence")
            if att_v.flow_style:
                if att_v.value:
                    last = att_v.value[-1]
                    insert_text = ",\n" + " " * last.start_mark.column + flow_str
                    return text[:last.end_mark.index] + insert_text + text[last.end_mark.index:]
                else:
                    return (
                        text[:att_v.start_mark.index + 1]
                        + " "
                        + flow_str
                        + " "
                        + text[att_v.end_mark.index - 1:]
                    )
            else:
                lines = text.split("\n")
                start_l, end_l = _node_lines(att_k, att_v, lines)
                if att_v.value:
                    last_item = att_v.value[-1]
                    m = re.match(r"^(\s*)-\s*", lines[last_item.start_mark.line])
                    dash_indent = m.group(1) if m else " " * (last_item.start_mark.column - 2)
                    sub_indent = " " * last_item.start_mark.column
                else:
                    dash_indent = " " * (att_k.start_mark.column + 2)
                    sub_indent = " " * (att_k.start_mark.column + 4)

                block_lines = [f"{dash_indent}- date: {date}"]
                if round_val:
                    block_lines.append(f"{sub_indent}round: {round_val}")
                block_lines.append(f"{sub_indent}outcome: {outcome}")
                if aborted_because:
                    block_lines.append(f"{sub_indent}aborted_because: {yaml_scalar(aborted_because)}")
                if env:
                    block_lines.append(f"{sub_indent}env: {yaml_scalar(env)}")
                if note:
                    block_lines.append(f"{sub_indent}note: {yaml_scalar(note)}")

                lines[end_l:end_l] = block_lines
                return "\n".join(lines)
        else:
            lines = text.split("\n")
            first_k = item_node.value[0][0]
            last_v = item_node.value[-1][1]
            start_l, end_l = _node_lines(first_k, last_v, lines)
            key_indent = " " * first_k.start_mark.column
            dash_indent = key_indent + "  "
            sub_indent = dash_indent + "  "

            block_lines = [
                f"{key_indent}attempts:",
                f"{dash_indent}- date: {date}",
            ]
            if round_val:
                block_lines.append(f"{sub_indent}round: {round_val}")
            block_lines.append(f"{sub_indent}outcome: {outcome}")
            if aborted_because:
                block_lines.append(f"{sub_indent}aborted_because: {yaml_scalar(aborted_because)}")
            if env:
                block_lines.append(f"{sub_indent}env: {yaml_scalar(env)}")
            if note:
                block_lines.append(f"{sub_indent}note: {yaml_scalar(note)}")

            lines[end_l:end_l] = block_lines
            return "\n".join(lines)


def add_attempt_cmd(args: argparse.Namespace) -> int:
    spec_dir = Path(args.spec_dir).resolve()
    if spec_dir.is_file():
        facts_path = spec_dir
        spec_dir = facts_path.parent
    else:
        facts_path = spec_dir / "_facts.yml"

    if not facts_path.is_file():
        print(f"no _facts.yml in {spec_dir} — not a feature-spec set.", file=sys.stderr)
        return 3

    try:
        facts = load_facts(facts_path)
    except yaml.YAMLError as exc:
        print(yaml_error_report(facts_path, exc), file=sys.stderr)
        return 3

    # 1. Flag validations
    if not ISO_DATE_RE.match(args.date):
        print(f"refused — date `{args.date}` is not valid ISO date (YYYY-MM-DD)", file=sys.stderr)
        return 2
    try:
        datetime.date.fromisoformat(args.date)
    except ValueError:
        print(f"refused — date `{args.date}` is not a calendar date", file=sys.stderr)
        return 2

    if args.round and not ROUND_RE.match(args.round):
        print(f"refused — round `{args.round}` does not match ^R\\d+([-\\w]*)$", file=sys.stderr)
        return 2

    is_aborted = args.outcome.startswith("aborted")
    if is_aborted and not args.aborted_because:
        print("refused — --aborted-because is required when outcome is aborted", file=sys.stderr)
        return 2
    if not is_aborted and args.aborted_because:
        print("refused — --aborted-because is only valid when outcome is aborted", file=sys.stderr)
        return 2

    if args.status:
        if is_aborted:
            print("refused — --status cannot be set when outcome is aborted", file=sys.stderr)
            return 2
        if args.status == "approved" and args.outcome != "passed":
            print("refused — --status approved requires --outcome passed", file=sys.stderr)
            return 2

    for val, name in [
        (args.note, "--note"),
        (args.env, "--env"),
        (args.aborted_because, "--aborted-because"),
    ]:
        if val and ("\n" in val or "\r" in val):
            print(f"refused — {name} cannot contain newlines", file=sys.stderr)
            return 2

    # 2. Criterion matching
    acceptance_list = facts.get("acceptance") or []
    if not isinstance(acceptance_list, list):
        print("refused — acceptance is not a list; edit by hand", file=sys.stderr)
        return 2

    matched_dicts = [
        item for item in acceptance_list
        if isinstance(item, dict) and str(item.get("id")) == args.ac_id
    ]

    if len(matched_dicts) > 1:
        print(f"refused — multiple criteria with id `{args.ac_id}` in acceptance[]", file=sys.stderr)
        return 2

    if not matched_dicts:
        # Check if matched a string criterion
        for item in acceptance_list:
            if not isinstance(item, dict):
                s = str(item)
                if re.match(rf"^{re.escape(args.ac_id)}\b", s) or s.startswith(args.ac_id):
                    print(
                        f"refused — criterion `{args.ac_id}` is a plain string; convert to {{ id: {args.ac_id}, item: ... }} to address it",
                        file=sys.stderr,
                    )
                    return 2
        print(f"refused — no criterion with id `{args.ac_id}` in acceptance[]", file=sys.stderr)
        return 2

    target_dict = matched_dicts[0]

    # 3. Order validation
    attempts_existing = target_dict.get("attempts") or []
    if isinstance(attempts_existing, list) and attempts_existing:
        last_d = None
        for a in reversed(attempts_existing):
            if isinstance(a, dict) and a.get("date"):
                last_d = to_date(a.get("date"))
                if last_d:
                    break
        new_d = to_date(args.date)
        if last_d and new_d and new_d < last_d:
            print(
                f"refused — date `{args.date}` is older than last attempt `{last_d}` (attempts are oldest first)",
                file=sys.stderr,
            )
            return 2

    # 4. Idempotency check
    new_attempt_data = {
        "date": to_date(args.date),
        "round": args.round or None,
        "outcome": args.outcome,
        "aborted_because": args.aborted_because or None,
        "env": args.env or None,
        "note": args.note or None,
    }

    for idx, existing in enumerate(attempts_existing):
        if not isinstance(existing, dict):
            continue
        ex_d = to_date(existing.get("date"))
        ex_rnd = existing.get("round") or None
        ex_out = norm(existing.get("outcome"))
        if ex_d == new_attempt_data["date"] and ex_rnd == new_attempt_data["round"] and ex_out == new_attempt_data["outcome"]:
            # Same (date, round, outcome)
            ex_aborted = existing.get("aborted_because") or None
            ex_env = existing.get("env") or None
            ex_note = existing.get("note") or None
            if (
                ex_aborted == new_attempt_data["aborted_because"]
                and ex_env == new_attempt_data["env"]
                and ex_note == new_attempt_data["note"]
            ):
                print(f"already recorded: acceptance[{args.ac_id}].attempts[{idx}]")
                stamp = version_stamp(
                    facts_path.name,
                    facts_path.read_bytes(),
                    f"acceptance[{args.ac_id}] attempt {args.date}",
                )
                print(f"**Edits:** {stamp}")
                return 0
            else:
                print(
                    "refused — attempts are append-only; a correction is a hand edit",
                    file=sys.stderr,
                )
                return 2

    # 5. Editing as text with node marks
    original_text = facts_path.read_text(encoding="utf-8")
    try:
        docs = list(yaml.compose_all(original_text))
    except yaml.YAMLError as exc:
        print(yaml_error_report(facts_path, exc), file=sys.stderr)
        return 3

    if not docs:
        print("cannot edit empty document", file=sys.stderr)
        return 3

    root = docs[-1]
    if not isinstance(root, yaml.MappingNode):
        print("cannot edit: root is not a mapping", file=sys.stderr)
        return 3

    if has_unsupported_shapes(root):
        print("refused — entry or document has anchors, aliases, or custom tags; edit by hand", file=sys.stderr)
        return 3

    # Locate criterion node
    acc_node_pair = next(
        ((k, v) for k, v in root.value if isinstance(k, yaml.ScalarNode) and k.value == "acceptance"),
        None,
    )
    if not acc_node_pair or not isinstance(acc_node_pair[1], yaml.SequenceNode):
        print("cannot edit: `acceptance` sequence not found", file=sys.stderr)
        return 3

    def find_item_node(doc_root: yaml.MappingNode) -> yaml.MappingNode | None:
        p = next(
            ((k, v) for k, v in doc_root.value if isinstance(k, yaml.ScalarNode) and k.value == "acceptance"),
            None,
        )
        if not p or not isinstance(p[1], yaml.SequenceNode):
            return None
        for item in p[1].value:
            if isinstance(item, yaml.MappingNode):
                for ik, iv in item.value:
                    if isinstance(ik, yaml.ScalarNode) and ik.value == "id" and isinstance(iv, yaml.ScalarNode) and iv.value == args.ac_id:
                        return item
        return None

    item_node = find_item_node(root)
    if not item_node:
        print(f"cannot find node for acceptance criterion `{args.ac_id}`", file=sys.stderr)
        return 3

    entry_text = original_text[item_node.start_mark.index : item_node.end_mark.index]
    if re.search(r"(?:^|\s)[&*][A-Za-z0-9_-]+", entry_text):
        print("refused — entry has anchors or aliases; edit by hand", file=sys.stderr)
        return 3

    working_text = original_text

    # Apply --status if requested
    if args.status:
        try:
            working_text = apply_status(working_text, item_node, args.status, args.date)
        except Exception as exc:
            print(f"cannot apply status: {exc}; edit by hand", file=sys.stderr)
            return 3

        # Re-compose to get updated marks for the attempt insertion
        try:
            docs = list(yaml.compose_all(working_text))
        except yaml.YAMLError as exc:
            print(yaml_error_report(facts_path, exc), file=sys.stderr)
            return 3
        root = docs[-1]
        item_node = find_item_node(root)
        if not item_node:
            print(f"cannot find node after status update for `{args.ac_id}`", file=sys.stderr)
            return 3

    # Apply attempt
    try:
        new_text = apply_attempt(
            working_text,
            item_node,
            args.date,
            args.round,
            args.outcome,
            args.aborted_because,
            args.env,
            args.note,
        )
    except Exception as exc:
        print(f"cannot insert attempt: {exc}; edit by hand", file=sys.stderr)
        return 3

    # 6. Post-edit gates in memory
    # 6a. Round trip
    try:
        new_docs = list(yaml.safe_load_all(new_text))
        old_docs = list(yaml.safe_load_all(original_text))
    except yaml.YAMLError as exc:
        print(f"refused — round-trip check failed (YAML syntax error): {exc}", file=sys.stderr)
        return 3

    if len(new_docs) != len(old_docs):
        print("refused — round-trip check failed: document count changed", file=sys.stderr)
        return 3

    # Check documents before last
    if new_docs[:-1] != old_docs[:-1]:
        print("refused — round-trip check failed: frontmatter documents modified", file=sys.stderr)
        return 3

    expected_doc = copy.deepcopy(old_docs[-1])
    target_exp = next(
        (e for e in (expected_doc.get("acceptance") or []) if isinstance(e, dict) and str(e.get("id")) == args.ac_id),
        None,
    )
    if not target_exp:
        print("refused — round-trip check failed: target criterion missing from expected", file=sys.stderr)
        return 3

    if args.status:
        target_exp["status"] = args.status
        target_exp["verified_on"] = datetime.date.fromisoformat(args.date)

    if "attempts" not in target_exp or target_exp["attempts"] is None:
        target_exp["attempts"] = []

    exp_att: dict[str, Any] = {"date": datetime.date.fromisoformat(args.date)}
    if args.round:
        exp_att["round"] = args.round
    exp_att["outcome"] = args.outcome
    if args.aborted_because:
        exp_att["aborted_because"] = args.aborted_because
    if args.env:
        exp_att["env"] = args.env
    if args.note:
        exp_att["note"] = args.note

    target_exp["attempts"].append(exp_att)

    if new_docs[-1] != expected_doc:
        print("refused — round-trip check failed: parsed content does not match expected", file=sys.stderr)
        return 3

    # 6b. Audit gate
    old_facts = old_docs[-1]
    new_facts = new_docs[-1]

    f_old = Findings()
    rank_old = STATUS_RANK.get(norm(old_facts.get("status")) or "draft", 0)
    check_acceptance_state(old_facts, rank_old, f_old)
    old_findings_ac = {
        (f["what"], f["check"])
        for f in f_old.items
        if f.get("where") == f"acceptance.{args.ac_id}"
    }

    f_new = Findings()
    rank_new = STATUS_RANK.get(norm(new_facts.get("status")) or "draft", 0)
    check_acceptance_state(new_facts, rank_new, f_new)
    new_findings_ac = [
        f for f in f_new.items
        if f.get("where") == f"acceptance.{args.ac_id}"
        and (f["what"], f["check"]) not in old_findings_ac
    ]

    if new_findings_ac:
        print("refused — check 26 acceptance state would fire after this edit:\n", file=sys.stderr)
        for x in new_findings_ac:
            print(f"  {x['where']}: {x['what']}. {x['fix']}.\n      └ check {x['check']}", file=sys.stderr)
        return 2

    # 7. Output / write
    ed = Edit(facts_path)
    ed.lines = new_text.split("\n")

    summary = (
        f"# facts add-attempt — {facts.get('feature', spec_dir.name)}: "
        f"acceptance[{args.ac_id}] attempt {args.date} ({args.outcome})"
        f"{' — DRY RUN, nothing written' if args.dry else ''}\n"
    )
    print(summary)

    if args.dry:
        if ed.changed():
            print(ed.diff())
        stamp = version_stamp(facts_path.name, ed.after.encode("utf-8"), f"acceptance[{args.ac_id}] attempt {args.date}")
        print(f"**Edits:** {stamp}")
    else:
        if ed.changed():
            facts_path.write_text(ed.after, encoding="utf-8")
        stamp = version_stamp(facts_path.name, facts_path.read_bytes(), f"acceptance[{args.ac_id}] attempt {args.date}")
        print(f"**Edits:** {stamp}")

    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="facts.py — registry writer subcommands",
        prog="facts.py",
    )
    sub = ap.add_subparsers(dest="subcommand", required=True)

    att = sub.add_parser(
        "add-attempt",
        help="Append an attempt to an acceptance criterion in _facts.yml",
    )
    att.add_argument("spec_dir", help="Path to spec directory (or _facts.yml)")
    att.add_argument("ac_id", help="Criterion id (e.g. AC14)")
    att.add_argument("--date", required=True, help="Attempt date YYYY-MM-DD")
    att.add_argument(
        "--outcome",
        required=True,
        choices=sorted(ATTEMPT_OUTCOMES),
        help="Outcome: aborted_no_conditions | failed | passed",
    )
    att.add_argument("--round", help="Round id (e.g. R57)")
    att.add_argument("--env", help="Environment description")
    att.add_argument("--note", help="Free-text note")
    att.add_argument("--aborted-because", help="Precondition that was missing (required if outcome is aborted)")
    att.add_argument(
        "--status",
        choices=["executed", "approved"],
        help="Update criterion status and set verified_on: date",
    )
    att.add_argument("--dry", action="store_true", help="Print diff and exit without writing")
    att.add_argument("--repo-root", type=Path, help="Repo root for resolution")

    args = ap.parse_args(argv)
    if args.subcommand == "add-attempt":
        return add_attempt_cmd(args)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
