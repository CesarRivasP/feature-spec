#!/usr/bin/env python3
"""Render a feature-spec doc set to a single self-contained HTML view.

The HTML is a DERIVED artifact. Never edit it; edit `_facts.yml` / the docs and
re-render. It surfaces what the markdown cannot show on its own:

  - `basis:` (measured / asserted / decided) as chips, with evidence attached
  - provenance: which registry key each datum in prose came from, both ways
  - `changes[]` vs `related_docs[]` kept visually disjoint
  - `defects[]` / `alternatives[]` as a board, with `depends_on` navigable
  - a correspondence matrix (datum x doc), computed at render time
  - `_log.md` as a timeline with colored dispositions
  - cross-refs (`01 §4`) as real links; dangling ones flagged red

Usage:
    python3 render.py <spec-dir> [-o out.html] [--open] [--serve [PORT]] [--lan]

Contract: references/render.md
"""

from __future__ import annotations

import argparse
import datetime
import html
import json
import os
import re
import sys
import webbrowser
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    sys.exit(
        "render.py needs PyYAML to read _facts.yml.\n"
        "  pip install pyyaml   (or: python3 -m pip install --user pyyaml)\n"
        "No fallback parser on purpose: a silently mis-parsed registry is the exact\n"
        "failure this skill exists to prevent."
    )

# ---------------------------------------------------------------------------
# markdown -> html (subset: what the templates actually emit)
# ---------------------------------------------------------------------------

_COMMENT = re.compile(r"<!--.*?-->", re.S)
_FENCE = re.compile(r"^\s*```+\s*([\w+-]*)\s*$")
_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_HR = re.compile(r"^\s*(?:-{3,}|\*{3,}|_{3,})\s*$")
_LI = re.compile(r"^(\s*)(?:([-*+])|(\d+)[.)])\s+(.*)$")
_TASK = re.compile(r"^\[([ xX])\]\s+(.*)$")
_TABLE_SEP = re.compile(r"^\s*\|?[\s:|-]*-[\s:|-]*\|?\s*$")


def _slug(text: str) -> str:
    s = re.sub(r"<[^>]+>", "", text)
    s = re.sub(r"[^\w\s.-]", "", s, flags=re.U).strip().lower()
    s = re.sub(r"[\s_]+", "-", s)
    return s.strip("-") or "s"


def _inline(text: str) -> str:
    """Escape, then apply inline markdown. Code spans are protected first."""
    spans: list[str] = []

    def stash(m: re.Match) -> str:
        spans.append(m.group(1))
        return f"\x00{len(spans) - 1}\x00"

    text = re.sub(r"`([^`]+)`", stash, text)
    text = html.escape(text, quote=False)
    text = re.sub(r"!\[([^\]]*)\]\(([^)\s]+)\)", r'<img alt="\1" src="\2">', text)
    text = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", r'<a href="\2">\1</a>', text)
    text = re.sub(r"\*\*(?=\S)(.+?)(?<=\S)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<![\w*])\*(?=\S)([^*]+?)(?<=\S)\*(?![\w*])", r"<em>\1</em>", text)
    text = re.sub(r"(?<![\w_])_(?=\S)([^_]+?)(?<=\S)_(?![\w_])", r"<em>\1</em>", text)

    def pop(m: re.Match) -> str:
        return "<code>" + html.escape(spans[int(m.group(1))], quote=False) + "</code>"

    return re.sub(r"\x00(\d+)\x00", pop, text)


class MarkdownRenderer:
    """Block-level renderer. Collects headings so cross-refs can resolve."""

    def __init__(self, prefix: str = ""):
        self.prefix = prefix
        self.headings: list[dict] = []
        self._ids: dict[str, int] = {}

    def render(self, src: str) -> str:
        src = _COMMENT.sub("", src)
        lines = src.replace("\r\n", "\n").split("\n")
        out: list[str] = []
        i = 0
        n = len(lines)
        while i < n:
            line = lines[i]

            if not line.strip():
                i += 1
                continue

            m = _FENCE.match(line)
            if m:
                lang = m.group(1)
                i += 1
                body: list[str] = []
                while i < n and not _FENCE.match(lines[i]):
                    body.append(lines[i])
                    i += 1
                i += 1  # closing fence
                cls = f' class="language-{lang}"' if lang else ""
                out.append(
                    f"<pre><code{cls}>"
                    + html.escape("\n".join(body), quote=False)
                    + "</code></pre>"
                )
                continue

            m = _HEADING.match(line)
            if m:
                level = len(m.group(1))
                text = m.group(2)
                hid = f"{self.prefix}{_slug(text)}"
                if hid in self._ids:
                    self._ids[hid] += 1
                    hid = f"{hid}-{self._ids[hid]}"
                else:
                    self._ids[hid] = 1
                num = re.match(r"^(?:Fase\s+)?([A-Z]?\d+(?:\.\d+)*)\b", re.sub(r"[`*]", "", text))
                self.headings.append(
                    {
                        "id": hid,
                        "level": level,
                        "text": re.sub(r"[`*]", "", text),
                        "number": num.group(1) if num else None,
                    }
                )
                out.append(f'<h{level} id="{hid}">{_inline(text)}</h{level}>')
                i += 1
                continue

            if _HR.match(line):
                out.append("<hr>")
                i += 1
                continue

            if line.lstrip().startswith(">"):
                block: list[str] = []
                while i < n and (lines[i].lstrip().startswith(">") or lines[i].strip()):
                    if not lines[i].lstrip().startswith(">") and not block:
                        break
                    if not lines[i].lstrip().startswith(">"):
                        break
                    block.append(re.sub(r"^\s*>\s?", "", lines[i]))
                    i += 1
                inner = MarkdownRenderer(self.prefix + "q-").render("\n".join(block))
                out.append(f"<blockquote>{inner}</blockquote>")
                continue

            if line.strip().startswith("|") and i + 1 < n and _TABLE_SEP.match(lines[i + 1]):
                out.append(self._table(lines, i))
                while i < n and lines[i].strip().startswith("|"):
                    i += 1
                continue

            if _LI.match(line):
                blockend = i
                while blockend < n and (
                    _LI.match(lines[blockend])
                    or (lines[blockend].startswith(("  ", "\t")) and lines[blockend].strip())
                ):
                    blockend += 1
                out.append(self._list(lines[i:blockend]))
                i = blockend
                continue

            para: list[str] = []
            while i < n and lines[i].strip() and not _LI.match(lines[i]) \
                    and not _HEADING.match(lines[i]) and not _HR.match(lines[i]) \
                    and not _FENCE.match(lines[i]) and not lines[i].lstrip().startswith(">") \
                    and not lines[i].strip().startswith("|"):
                para.append(lines[i].strip())
                i += 1
            if para:
                out.append("<p>" + _inline(" ".join(para)) + "</p>")

        return "\n".join(out)

    def _table(self, lines: list[str], start: int) -> str:
        def cells(row: str) -> list[str]:
            row = row.strip()
            if row.startswith("|"):
                row = row[1:]
            if row.endswith("|"):
                row = row[:-1]
            return [c.strip() for c in re.split(r"(?<!\\)\|", row)]

        head = cells(lines[start])
        body_rows = []
        j = start + 2
        while j < len(lines) and lines[j].strip().startswith("|"):
            body_rows.append(cells(lines[j]))
            j += 1
        out = ["<div class='tablewrap'><table><thead><tr>"]
        out += [f"<th>{_inline(c)}</th>" for c in head]
        out.append("</tr></thead><tbody>")
        for row in body_rows:
            out.append("<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in row) + "</tr>")
        out.append("</tbody></table></div>")
        return "".join(out)

    def _list(self, block: list[str]) -> str:
        items: list[tuple[int, bool, str, str]] = []  # indent, ordered, marker, text
        for raw in block:
            m = _LI.match(raw)
            if m:
                indent = len(m.group(1).expandtabs(4))
                items.append((indent, m.group(3) is not None, m.group(4), ""))
            elif items:
                indent, ordered, text, extra = items[-1]
                items[-1] = (indent, ordered, text + " " + raw.strip(), extra)
        return self._emit(items, 0, 0)[0]

    def _emit(self, items: list[tuple], idx: int, depth: int) -> tuple[str, int]:
        if idx >= len(items):
            return "", idx
        base_indent, ordered, _, _ = items[idx]
        tag = "ol" if ordered else "ul"
        out = [f"<{tag}>"]
        i = idx
        while i < len(items):
            indent, is_ord, text, _ = items[i]
            if indent < base_indent:
                break
            if indent > base_indent:
                sub, i = self._emit(items, i, depth + 1)
                out.append(sub)
                continue
            t = _TASK.match(text.strip())
            if t:
                done = t.group(1).lower() == "x"
                mark = "checked" if done else ""
                cls = "task done" if done else "task"
                out.append(
                    f'<li class="{cls}"><input type="checkbox" disabled {mark}>'
                    f"<span>{_inline(t.group(2))}</span></li>"
                )
            else:
                out.append(f"<li>{_inline(text)}</li>")
            i += 1
        out.append(f"</{tag}>")
        return "".join(out), i


# ---------------------------------------------------------------------------
# registry walking
# ---------------------------------------------------------------------------

BASIS_ORDER = {"measured": 0, "asserted": 1, "decided": 2}

# values that carry no information as prose datums
STOP_VALUES = {
    "draft", "reviewed", "implementing", "shipped", "paused", "null", "none",
    "true", "false", "open", "fixed", "dead", "chosen", "discarded", "reopened",
    "shell", "git", "device", "log", "measured", "asserted", "decided",
    "root_cause", "contributing", "symptom", "cosmetic", "master-plan",
    "implementation", "stakeholder", "legacy", "yyyy-mm-dd",
    # contract field TYPES are schema, not values copied into prose
    "string", "number", "boolean", "integer", "float", "object", "array",
}
# registry paths that describe the set itself rather than a datum cited in prose
STOP_PATH_PREFIXES = ("docs[", "feature", "profile")
# keys whose scalar is structural, not a shared datum cited in prose
STOP_KEY_TAILS = {"basis", "how", "status", "role", "outcome", "id", "tag"}


def walk(node, path: str = ""):
    """Yield (dotted_path, value) for every node, containers included."""
    yield path, node
    if isinstance(node, dict):
        for k, v in node.items():
            yield from walk(v, f"{path}.{k}" if path else str(k))
    elif isinstance(node, list):
        for idx, v in enumerate(node):
            yield from walk(v, f"{path}[{idx}]")


def collect_claims(facts: dict) -> list[dict]:
    """Every node carrying a `basis:`, in registry order."""
    claims = []
    for path, node in walk(facts):
        if isinstance(node, dict) and "basis" in node:
            claims.append(
                {
                    "path": path,
                    "basis": str(node.get("basis")),
                    "evidence": node.get("evidence") or {},
                    "falsified_by": node.get("falsified_by"),
                    "label": node.get("claim") or node.get("name") or node.get("file") or path,
                    "node": node,
                }
            )
    claims.sort(key=lambda c: (BASIS_ORDER.get(c["basis"], 9), c["path"]))
    return claims


def collect_datums(facts: dict) -> dict[str, list[str]]:
    """Scalars worth tracing into prose: {value_string: [registry paths]}."""
    datums: dict[str, list[str]] = {}
    for path, node in walk(facts):
        if isinstance(node, (dict, list)) or node is None or isinstance(node, bool):
            continue
        tail = path.rsplit(".", 1)[-1].split("[")[0]
        if tail in STOP_KEY_TAILS:
            continue
        if isinstance(node, (int, float)):
            if abs(node) < 10:
                continue
            value = str(node)
        else:
            value = str(node).strip()
            if len(value) < 4:
                continue
            if value.lower() in STOP_VALUES:
                continue
            if value.startswith("<") and value.endswith(">"):
                continue  # unfilled template placeholder
            if re.fullmatch(r"[<{\[].*", value) and "YYYY" in value:
                continue
        datums.setdefault(value, []).append(path)
    return datums


AGENT_RE = re.compile(r"claude|gpt|gemini|llama|opus|sonnet|haiku|o[0-9]|agent|bot",
                      re.I)
ACCEPTED_FIELDS = ("by", "decided_on", "until", "because")


def _date(value) -> datetime.date | None:
    if isinstance(value, datetime.date):
        return value
    try:
        return datetime.date.fromisoformat(str(value).strip())
    except (ValueError, TypeError):
        return None


def accepted_state(entry: dict, today: datetime.date | None = None) -> tuple[str, str]:
    """How an `accepted:` block stands right now.

    -> ("none"|"live"|"expired"|"malformed", detail)

    G1 refuses `shipped` while a root cause is asserted, and that is right. What it
    had no room for is the legitimate case: the team knows the cause is unproven,
    ships the trimmed scope anyway, and schedules the measurement. Without a field
    that decision goes into a log entry or an agent's memory, and neither is read by
    the audit, the next agent, or this view — so "we looked and chose to wait" is
    indistinguishable from "nobody looked".

    It is a deferral with a deadline, not an exemption: `until:` expires, and past it
    G1 refuses again. That expiry is what a memory cannot do."""
    acc = entry.get("accepted")
    if not isinstance(acc, dict):
        return "none", ""
    missing = [k for k in ACCEPTED_FIELDS if not acc.get(k)]
    if missing:
        return "malformed", f"`accepted:` lacks {', '.join(missing)}"
    if AGENT_RE.search(str(acc["by"])):
        return "malformed", (f"`accepted.by: {acc['by']}` looks like an agent — a risk "
                             "is accepted by a person, on their own behalf")
    until = _date(acc["until"])
    if until is None:
        return "malformed", f"`accepted.until: {acc['until']}` is not a YYYY-MM-DD date"
    today = today or datetime.date.today()
    if until < today:
        return "expired", f"accepted until {until}, which passed {(today - until).days} days ago"
    return "live", f"accepted by {acc['by']} until {until}"


def status_gate(facts: dict, claims: list[dict]) -> list[str]:
    """Gate G1 (references/evidence.md): `shipped` while a cause is asserted."""
    warnings = []
    if str(facts.get("status", "")).strip() == "shipped":
        for d in facts.get("defects") or []:
            if isinstance(d, dict) and d.get("role") in ("root_cause", "contributing") \
                    and str(d.get("basis")) == "asserted" and d.get("status") != "dead":
                state, detail = accepted_state(d)
                if state == "live":
                    continue  # a deferral with a deadline, recorded and not yet due
                suffix = {
                    "none": " and no `accepted:` block records a decision to ship anyway",
                    "expired": f" — {detail}",
                    "malformed": f" — {detail}",
                }[state]
                warnings.append(
                    f"G1: status is `shipped` but defect {d.get('id', '?')} "
                    f"({d.get('role')}) is still `basis: asserted`{suffix}."
                )
    for c in claims:
        if c["basis"] == "measured":
            ev = c["evidence"]
            missing = [k for k in ("how", "cmd", "date", "value") if not ev.get(k)]
            if missing:
                warnings.append(
                    f"`{c['path']}` is `measured` but evidence lacks: {', '.join(missing)}."
                )
            cmd = str(ev.get("cmd", ""))
            if re.search(r"\brg\b[^'\"\n]*(['\"])[^'\"\n]*\|[^'\"\n]*\1", cmd):
                warnings.append(
                    f"`{c['path']}` evidence.cmd uses regex alternation — "
                    "fused result sets cannot be attributed per symbol."
                )
            if re.search(r"-g\s+'!|--exclude-dir", cmd):
                warnings.append(
                    f"`{c['path']}` evidence.cmd is scoped by denylist — "
                    "files added later silently enter the result set."
                )
        elif c["basis"] == "asserted" and not c["falsified_by"]:
            warnings.append(f"`{c['path']}` is `asserted` with no `falsified_by:`.")
    return warnings


# ---------------------------------------------------------------------------
# provenance: mark registry datums inside rendered doc HTML
# ---------------------------------------------------------------------------

_TAG_SPLIT = re.compile(r"(<[^>]+>)")


def build_datum_regex(datums: dict[str, list[str]]) -> re.Pattern | None:
    if not datums:
        return None
    ordered = sorted(datums, key=len, reverse=True)
    parts = []
    for value in ordered:
        pat = re.escape(value)
        if re.match(r"\w", value):
            pat = r"(?<!\w)" + pat
        if re.search(r"\w$", value):
            pat = pat + r"(?!\w)"
        parts.append(pat)
    return re.compile("|".join(parts))


def mark_provenance(doc_html: str, datums: dict[str, list[str]],
                    rx: re.Pattern | None, hits: dict[str, int]) -> str:
    """Wrap registry-sourced values in prose. Skips <pre> blocks."""
    if rx is None:
        return doc_html
    out: list[str] = []
    in_pre = 0
    for chunk in _TAG_SPLIT.split(doc_html):
        if chunk.startswith("<"):
            low = chunk.lower()
            if low.startswith("<pre"):
                in_pre += 1
            elif low.startswith("</pre"):
                in_pre = max(0, in_pre - 1)
            out.append(chunk)
            continue
        if in_pre or not chunk.strip():
            out.append(chunk)
            continue

        def repl(m: re.Match) -> str:
            raw = m.group(0)
            paths = datums.get(raw) or datums.get(html.unescape(raw))
            if not paths:
                return raw
            hits[raw] = hits.get(raw, 0) + 1
            ids = " ".join(fact_id(p) for p in paths)
            title = html.escape("_facts.yml " + ", ".join(paths), quote=True)
            return (f'<mark class="fact" data-targets="{ids}" '
                    f'title="{title}" tabindex="0">{raw}</mark>')

        out.append(rx.sub(repl, chunk))
    return "".join(out)


def fact_id(path: str) -> str:
    return "fact-" + re.sub(r"[^\w]+", "-", path).strip("-")


_CANON = True


def set_canonical(value: bool) -> None:
    """The Registry view renders the whole registry and owns the `fact-*` ids.
    Overview / Claims / Defects render the same nodes again — they must not
    duplicate the ids, or provenance lands on whichever copy came first."""
    global _CANON
    _CANON = value


def id_attr(path: str) -> str:
    ident = fact_id(path)
    return f' id="{ident}"' if _CANON else f' data-fid="{ident}"'



# ---------------------------------------------------------------------------
# cross-refs: `01 §4` -> real anchors; dangling ones flagged
# ---------------------------------------------------------------------------

def _ref_regex(doc_ids: list[str]) -> re.Pattern:
    """`01` §3.2 — the doc prefix is almost always inside backticks, so the
    gap between it and the § may contain tags. Doc ids come from `docs[]`, never
    `\\d{2}`: a date like 2026-08-11 would otherwise read as a prefix `08`."""
    ids = "|".join(re.escape(d) for d in doc_ids) or r"\d{2}"
    return re.compile(
        r"(?:(?P<doc>\b(?:" + ids + r")\b)"
        r"(?:</?[a-zA-Z][^>]*>|[^\u00a7<]){0,12})?"
        r"\u00a7\s*(?P<sec>[A-Z]?\d+(?:\.\d+)*)")


def _blocked_spans(doc_html: str) -> list[tuple[int, int]]:
    """Positions where a § must be left alone: inside <pre>, or inside a tag."""
    spans = [m.span() for m in re.finditer(r"<pre\b.*?</pre>", doc_html, re.S | re.I)]
    spans += [m.span() for m in re.finditer(r"<[^>]+>", doc_html)]
    return spans


def link_crossrefs(doc_html: str, this_doc: str,
                   sections: dict[str, dict[str, str]], dangling: list[str],
                   doc_ids: list[str]) -> str:
    rx = _ref_regex(doc_ids)
    blocked = _blocked_spans(doc_html)

    def is_blocked(pos: int) -> bool:
        return any(a <= pos < b for a, b in blocked)

    out: list[str] = []
    cursor = 0
    for m in rx.finditer(doc_html):
        sign = doc_html.find("\u00a7", m.start(), m.end())
        if sign < 0 or is_blocked(sign) or m.start() < cursor:
            continue
        target_doc = m.group("doc") or this_doc
        sec = m.group("sec")
        anchor = sections.get(target_doc, {}).get(sec)
        label = doc_html[sign:m.end()]
        out.append(doc_html[cursor:sign])
        if anchor:
            out.append(f'<a class="xref" href="#{anchor}" data-doc="{target_doc}">{label}</a>')
        else:
            dangling.append(f"doc {this_doc}: `{label.strip()}` no resuelve en doc {target_doc}")
            out.append(f'<span class="xref dangling" title="no existe la secci\u00f3n {sec} '
                       f'en el doc {target_doc}">{label}</span>')
        cursor = m.end()
    out.append(doc_html[cursor:])
    return "".join(out)


# ---------------------------------------------------------------------------
# _log.md -> timeline
# ---------------------------------------------------------------------------

_ROUND = re.compile(r"^##\s+(?P<id>R\d+)\s*·\s*(?P<rest>.*)$")
_FIELD = re.compile(r"^\*\*(?P<key>[^:*]+):\*\*\s*(?P<val>.*)$")
_DISPOSITION = re.compile(r"\*\*(confirmed|rejected|deferred)\*\*", re.I)


def parse_log(text: str) -> list[dict]:
    """Rounds in file order. Commented-out template examples are stripped first,
    so the scaffold's illustrative R2/R3 never appear as real history."""
    text = _COMMENT.sub("", text)
    rounds: list[dict] = []
    current: dict | None = None
    for line in text.replace("\r\n", "\n").split("\n"):
        m = _ROUND.match(line)
        if m:
            bits = [b.strip() for b in m.group("rest").split("·")]
            current = {
                "id": m.group("id"),
                "date": bits[0] if bits else "",
                "who": bits[1] if len(bits) > 1 else "",
                "kind": bits[2] if len(bits) > 2 else "",
                "fields": [],
                "body": [],
            }
            rounds.append(current)
            continue
        if current is None:
            continue
        f = _FIELD.match(line.strip())
        if f:
            current["fields"].append((f.group("key").strip(), f.group("val").strip()))
        elif line.strip():
            current["body"].append(line)
    for r in rounds:
        dispositions, used = [], []
        for raw in r["body"]:
            d = _DISPOSITION.search(raw)
            if d and raw.strip().startswith("-"):
                dispositions.append((d.group(1).lower(), raw.strip().lstrip("- ")))
                used.append(raw)
        r["dispositions"] = dispositions
        r["disposition_lines"] = used
    return rounds


# ---------------------------------------------------------------------------
# registry -> html
# ---------------------------------------------------------------------------

def basis_chip(basis: str) -> str:
    b = html.escape(str(basis), quote=False)
    return f'<span class="chip basis-{b}">{b}</span>'


def evidence_block(ev: dict, path: str) -> str:
    """Every field carries the id of its registry path, so a datum highlighted in
    prose can land on the exact `evidence.value` it was copied from."""
    if not ev:
        return ""
    rows = []
    keys = [k for k in ("how", "cmd", "date", "value") if ev.get(k) is not None]
    keys += [k for k in ev if k not in ("how", "cmd", "date", "value")]
    for key in keys:
        val = html.escape(str(ev[key]), quote=False)
        cls = "mono" if key in ("cmd", "value") else ""
        eid = id_attr(f"{path}.evidence.{key}")
        rows.append(f'<div class="ev-row"><span class="ev-k">{html.escape(str(key))}</span>'
                    f'<span class="ev-v {cls}"{eid}>{val}</span></div>')
    return '<div class="evidence">' + "".join(rows) + "</div>"


def render_value(node, path: str, depth: int = 0) -> str:
    """Generic registry renderer. Any node with `basis:` gets the claim treatment."""
    if isinstance(node, dict):
        if "basis" in node:
            head_key = next((k for k in ("claim", "name", "file") if node.get(k)), None)
            head = node.get(head_key) if head_key else ""
            parts = [f'<div class="claim"{id_attr(path)} '
                     f'data-path="{html.escape(path, True)}">']
            parts.append('<div class="claim-head">')
            parts.append(basis_chip(node["basis"]))
            for key in ("id", "role", "status", "outcome"):
                if node.get(key):
                    parts.append(
                        f'<span class="chip tag tag-{_slug(str(node[key]))}"'
                        f'{id_attr(f"{path}.{key}")}>'
                        f"{html.escape(str(node[key]), quote=False)}</span>")
            if head:
                parts.append(f'<span class="claim-text"'
                             f'{id_attr(f"{path}.{head_key}")}>'
                             f"{_inline(str(head))}</span>")
            parts.append(f'<span class="path mono">{html.escape(path)}</span>')
            parts.append("</div>")
            parts.append(evidence_block(node.get("evidence") or {}, path))
            if node.get("falsified_by"):
                parts.append(
                    '<div class="falsified"><span class="ev-k">falsified_by</span>'
                    f'<span class="ev-v"{id_attr(f"{path}.falsified_by")}>'
                    f'{_inline(str(node["falsified_by"]))}</span></div>')
            rest = {k: v for k, v in node.items()
                    if k not in ("basis", "evidence", "falsified_by", head_key, "id",
                                 "role", "status", "outcome")}
            if rest:
                parts.append(render_value(rest, path, depth + 1))
            parts.append("</div>")
            return "".join(parts)
        if not node:
            return '<span class="empty">— vacío</span>'
        rows = []
        for k, v in node.items():
            child = f"{path}.{k}" if path else str(k)
            rows.append(
                f'<div class="kv{" deep" if depth >= 2 else ""}" '
                f'data-fid="{fact_id(child)}">'
                f'<div class="k">{html.escape(str(k), quote=False)}</div>'
                f'<div class="v">{render_value(v, child, depth + 1)}</div></div>')
        return '<div class="map">' + "".join(rows) + "</div>"

    if isinstance(node, list):
        if not node:
            return '<span class="empty">— vacío</span>'
        if all(not isinstance(x, (dict, list)) for x in node):
            chips = "".join(
                f'<span class="chip val"{id_attr(f"{path}[{i}]")}>'
                f"{html.escape(str(x), quote=False)}</span>"
                for i, x in enumerate(node))
            return f'<div class="chips">{chips}</div>'
        items = "".join(
            f'<div class="item">{render_value(x, f"{path}[{i}]", depth + 1)}</div>'
            for i, x in enumerate(node))
        return f'<div class="items">{items}</div>'

    if node is None:
        return '<span class="empty">null</span>'
    text = ("true" if node else "false") if isinstance(node, bool) else str(node)
    cls = "scalar mono" if re.search(r"[/\\`${}()]|^\S+ -", text) else "scalar"
    return f'<span class="{cls}"{id_attr(path)}>{html.escape(text, quote=False)}</span>'


CSS = """
*,*::before,*::after{box-sizing:border-box}
:root{
  --bg:#fbfaf8; --bg-2:#ffffff; --bg-3:#f2f0ec; --fg:#1d1c1a; --fg-2:#5c5953;
  --fg-3:#8b877f; --line:#e2ded7; --line-2:#cdc8bf; --accent:#8a5a2b;
  --accent-soft:#f3e6d6; --measured:#2f6d43; --measured-bg:#e4f1e7;
  --asserted:#9a6206; --asserted-bg:#fbeeda; --decided:#4a5a6b; --decided-bg:#e8edf2;
  --danger:#a32f2f; --danger-bg:#fbe6e4; --mark:#fdf0c9; --mark-line:#e0c369;
  --radius:8px; --mono:ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,monospace;
  --sans:ui-sans-serif,-apple-system,"Segoe UI",Inter,system-ui,sans-serif;
}
@media (prefers-color-scheme:dark){
  :root:not([data-theme="light"]){
    --bg:#16151a; --bg-2:#1d1c22; --bg-3:#26242c; --fg:#eceaf0; --fg-2:#b3aec0;
    --fg-3:#847f92; --line:#312f3a; --line-2:#413e4c; --accent:#d9a066;
    --accent-soft:#3a2c1c; --measured:#79c894; --measured-bg:#1c3324;
    --asserted:#e0aa5a; --asserted-bg:#3a2c14; --decided:#9db4cb; --decided-bg:#202a34;
    --danger:#f08a80; --danger-bg:#3a1d1c; --mark:#3d3418; --mark-line:#8a763a;
  }
}
:root[data-theme="dark"]{
  --bg:#16151a; --bg-2:#1d1c22; --bg-3:#26242c; --fg:#eceaf0; --fg-2:#b3aec0;
  --fg-3:#847f92; --line:#312f3a; --line-2:#413e4c; --accent:#d9a066;
  --accent-soft:#3a2c1c; --measured:#79c894; --measured-bg:#1c3324;
  --asserted:#e0aa5a; --asserted-bg:#3a2c14; --decided:#9db4cb; --decided-bg:#202a34;
  --danger:#f08a80; --danger-bg:#3a1d1c; --mark:#3d3418; --mark-line:#8a763a;
}
html{scroll-behavior:smooth}
body{margin:0;background:var(--bg);color:var(--fg);font-family:var(--sans);
  font-size:15px;line-height:1.65;-webkit-font-smoothing:antialiased}
.layout{display:grid;grid-template-columns:250px minmax(0,1fr);gap:0;min-height:100vh;
  background:linear-gradient(to right,var(--bg-2) 0 250px,var(--bg) 250px)}
aside{position:sticky;top:0;height:100vh;overflow-y:auto;background:var(--bg-2);
  border-right:1px solid var(--line);padding:18px 14px 40px}
.brand{font-size:12px;letter-spacing:.09em;text-transform:uppercase;color:var(--fg-3);
  margin-bottom:2px}
.title{font-size:17px;font-weight:650;line-height:1.3;margin:0 0 14px}
.status-row{display:flex;flex-wrap:wrap;gap:5px;margin-bottom:16px}
nav a{display:block;padding:6px 9px;border-radius:6px;color:var(--fg-2);
  text-decoration:none;font-size:13.5px;cursor:pointer}
nav a:hover{background:var(--bg-3);color:var(--fg)}
nav a.active{background:var(--accent-soft);color:var(--fg);font-weight:600}
nav .group{font-size:11px;text-transform:uppercase;letter-spacing:.08em;
  color:var(--fg-3);margin:16px 0 5px 9px}
nav .toc{margin:2px 0 4px 14px;border-left:1px solid var(--line);padding-left:6px}
nav .toc a{font-size:12.5px;padding:3px 8px;color:var(--fg-3)}
nav .toc a.lvl3{padding-left:20px}
main{padding:28px 34px 120px;max-width:1000px;min-width:0}
section.view{display:none} section.view.active{display:block}
h1,h2,h3,h4{line-height:1.25;font-weight:650;scroll-margin-top:20px}
h1{font-size:26px;margin:0 0 6px} h2{font-size:20px;margin:34px 0 10px;
  padding-bottom:6px;border-bottom:1px solid var(--line)}
h3{font-size:16.5px;margin:24px 0 8px} h4{font-size:15px;margin:18px 0 6px;color:var(--fg-2)}
p{margin:0 0 12px} a{color:var(--accent)}
code{font-family:var(--mono);font-size:.87em;background:var(--bg-3);
  padding:1.5px 5px;border-radius:4px;border:1px solid var(--line)}
pre{background:var(--bg-3);border:1px solid var(--line);border-radius:var(--radius);
  padding:13px 15px;overflow-x:auto;margin:0 0 14px}
pre code{background:none;border:0;padding:0;font-size:12.8px;line-height:1.55}
blockquote{margin:0 0 14px;padding:10px 14px;border-left:3px solid var(--accent);
  background:var(--accent-soft);border-radius:0 var(--radius) var(--radius) 0}
blockquote p:last-child{margin-bottom:0}
hr{border:0;border-top:1px solid var(--line);margin:26px 0}
.tablewrap{overflow-x:auto;margin:0 0 16px;border:1px solid var(--line);
  border-radius:var(--radius)}
table{border-collapse:collapse;width:100%;font-size:14px}
th,td{text-align:left;padding:8px 12px;border-bottom:1px solid var(--line);
  vertical-align:top}
th{background:var(--bg-3);font-weight:600;font-size:12.5px;letter-spacing:.02em}
tr:last-child td{border-bottom:0}
ul,ol{margin:0 0 13px;padding-left:22px} li{margin:3px 0}
li.task{list-style:none;margin-left:-20px;display:flex;gap:8px;align-items:flex-start}
li.task input{margin-top:5px} li.task.done span{color:var(--fg-3);
  text-decoration:line-through}
.chip{display:inline-flex;align-items:center;gap:4px;font-size:11.5px;
  font-weight:600;padding:2px 8px;border-radius:999px;border:1px solid transparent;
  font-family:var(--mono);letter-spacing:.01em}
.basis-measured{color:var(--measured);background:var(--measured-bg);
  border-color:color-mix(in srgb,var(--measured) 35%,transparent)}
.basis-asserted{color:var(--asserted);background:var(--asserted-bg);
  border-color:color-mix(in srgb,var(--asserted) 35%,transparent)}
.basis-decided{color:var(--decided);background:var(--decided-bg);
  border-color:color-mix(in srgb,var(--decided) 35%,transparent)}
a.chip.tag{text-decoration:none}
.chip.tag{background:var(--bg-3);color:var(--fg-2);border-color:var(--line-2)}
.chip.tag.dangling{color:var(--danger);background:var(--danger-bg);
  border-color:color-mix(in srgb,var(--danger) 40%,transparent);cursor:help}
.chip.tag-root-cause{background:var(--danger-bg);color:var(--danger);
  border-color:color-mix(in srgb,var(--danger) 35%,transparent)}
.chip.val{background:var(--bg-3);color:var(--fg);border-color:var(--line);
  font-weight:500}
.chips{display:flex;flex-wrap:wrap;gap:5px}
mark.fact{background:var(--mark);color:inherit;padding:0 2px;border-radius:3px;
  box-shadow:inset 0 -1.5px 0 var(--mark-line);cursor:pointer}
mark.fact:hover,mark.fact.lit{background:var(--accent-soft);
  box-shadow:inset 0 -1.5px 0 var(--accent)}
.xref{font-family:var(--mono);font-size:.9em}
.xref.dangling{color:var(--danger);background:var(--danger-bg);
  border-bottom:1px dashed var(--danger);cursor:help}
.card{background:var(--bg-2);border:1px solid var(--line);
  border-radius:var(--radius);padding:14px 16px;margin:0 0 14px}
.card>h3:first-child{margin-top:0}
.map{display:flex;flex-direction:column;gap:7px}
.kv{display:grid;grid-template-columns:minmax(88px,26%) minmax(0,1fr);gap:12px;
  padding:5px 0;border-top:1px solid var(--line);min-width:0}
.kv.deep,.col .kv{grid-template-columns:minmax(0,1fr);gap:0}
.kv.deep .k,.col .kv .k,.claim .kv .k{font-size:11.5px;text-transform:uppercase;
  letter-spacing:.05em}
.claim .kv:not(.deep){grid-template-columns:88px minmax(0,1fr);gap:10px}
.kv:first-child{border-top:0}
.k{font-family:var(--mono);font-size:12.5px;color:var(--fg-2);word-break:break-word}
.v{min-width:0}
.items{display:flex;flex-direction:column;gap:9px}
.item{border-left:2px solid var(--line-2);padding-left:11px}
.scalar.mono{font-family:var(--mono);font-size:12.8px}
.empty{color:var(--fg-3);font-style:italic;font-size:13px}
.claim{border:1px solid var(--line);border-radius:var(--radius);
  background:var(--bg-2);padding:10px 12px}
.claim-head{display:flex;flex-wrap:wrap;gap:7px;align-items:baseline}
.claim-text{flex:1 1 240px;font-weight:500}
.path{font-size:11.5px;color:var(--fg-3);font-family:var(--mono)}
.evidence{margin-top:8px;border-top:1px dashed var(--line-2);padding-top:7px;
  display:flex;flex-direction:column;gap:3px}
.ev-row,.falsified{display:grid;grid-template-columns:88px minmax(0,1fr);gap:10px;
  font-size:12.8px}
.falsified{margin-top:8px;border-top:1px dashed var(--line-2);padding-top:7px}
.ev-k{color:var(--fg-3);font-family:var(--mono);font-size:11.5px;text-transform:uppercase;
  letter-spacing:.05em}
.ev-v{min-width:0;overflow-wrap:anywhere} .ev-v.mono{font-family:var(--mono);font-size:12.4px}
.grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:14px;
  align-items:start}
.board{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:14px}
.col h3{margin:0 0 9px;font-size:13px;text-transform:uppercase;letter-spacing:.07em;
  color:var(--fg-3)}
.flash{animation:flash 1.4s ease-out}
@keyframes flash{0%{background:var(--accent-soft);box-shadow:0 0 0 4px var(--accent-soft)}
  100%{background:transparent;box-shadow:0 0 0 4px transparent}}
.timeline{position:relative;padding-left:22px}
.timeline::before{content:"";position:absolute;left:5px;top:6px;bottom:6px;
  width:2px;background:var(--line)}
.round{position:relative;margin:0 0 16px}
.round::before{content:"";position:absolute;left:-21px;top:9px;width:10px;height:10px;
  border-radius:50%;background:var(--accent);border:2px solid var(--bg)}
.round-head{display:flex;flex-wrap:wrap;gap:8px;align-items:baseline;margin-bottom:6px}
.round-id{font-family:var(--mono);font-weight:700}
.round-meta{color:var(--fg-3);font-size:12.5px}
.round .ev-row{grid-template-columns:112px minmax(0,1fr)}
.round-body{margin-top:8px;border-top:1px dashed var(--line-2);padding-top:7px;font-size:13.5px}
.round-body p:last-child,.round-body ul:last-child{margin-bottom:0}
.disp{display:grid;grid-template-columns:112px minmax(0,1fr);gap:10px;font-size:13px;
  padding:4px 0;border-top:1px solid var(--line)}
.d-confirmed{color:var(--measured)} .d-rejected{color:var(--danger)}
.d-deferred{color:var(--asserted)}
.warn{border-left:3px solid var(--danger);background:var(--danger-bg);
  padding:10px 14px;border-radius:0 var(--radius) var(--radius) 0;margin:0 0 12px;
  font-size:13.5px}
.warn ul{margin:6px 0 0}
.note{border-left:3px solid var(--asserted);background:var(--asserted-bg);
  padding:10px 14px;border-radius:0 var(--radius) var(--radius) 0;margin:0 0 12px;
  font-size:13.5px}
.stat-row{display:flex;flex-wrap:wrap;gap:10px;margin:0 0 18px}
.stat{flex:1 1 130px;background:var(--bg-2);border:1px solid var(--line);
  border-radius:var(--radius);padding:11px 14px}
.stat .n{font-size:23px;font-weight:650;line-height:1.1;font-family:var(--mono)}
.stat .l{font-size:11.5px;text-transform:uppercase;letter-spacing:.07em;color:var(--fg-3)}
.matrix td.hit{color:var(--measured);font-weight:600;text-align:center}
.matrix td.miss{color:var(--fg-3);text-align:center}
.matrix td.orphan{color:var(--asserted);text-align:center;font-weight:600}
.matrix td.val{font-family:var(--mono);font-size:12.3px;max-width:340px;
  overflow-wrap:anywhere}
.toolbar{display:flex;gap:8px;align-items:center;margin-bottom:14px;flex-wrap:wrap}
button.tbtn{font:inherit;font-size:12.5px;padding:4px 11px;border-radius:999px;
  border:1px solid var(--line-2);background:var(--bg-2);color:var(--fg-2);cursor:pointer}
button.tbtn:hover{background:var(--bg-3);color:var(--fg)}
button.tbtn.on{background:var(--accent-soft);color:var(--fg);border-color:var(--accent)}
.theme-toggle{position:fixed;right:16px;bottom:16px;z-index:10}
.footnote{color:var(--fg-3);font-size:12.5px;margin-top:26px;border-top:1px solid var(--line);
  padding-top:12px}
@media (max-width:860px){
  .layout{grid-template-columns:1fr;background:var(--bg)}
  aside{position:static;height:auto;border-right:0;
    border-bottom:1px solid var(--line)} main{padding:20px 18px 80px}
  .kv{grid-template-columns:1fr;gap:2px}
}
"""

JS = """
(function(){
  var nav=document.querySelectorAll('nav a[data-view]');
  var top=document.querySelectorAll('nav > a[data-view]');
  function show(id,anchor){
    document.querySelectorAll('section.view').forEach(function(s){
      s.classList.toggle('active',s.id===id);});
    top.forEach(function(a){a.classList.toggle('active',a.dataset.view===id);});
    document.querySelectorAll('nav .toc').forEach(function(t){
      t.style.display=(t.dataset.view===id)?'':'none';});
    if(anchor){var el=document.getElementById(anchor);
      if(el){el.scrollIntoView({block:'start'});flash(el);}}
    else{window.scrollTo(0,0);}
  }
  function flash(el){el.classList.remove('flash');void el.offsetWidth;
    el.classList.add('flash');}
  function sectionOf(el){var s=el.closest('section.view');return s?s.id:null;}
  nav.forEach(function(a){a.addEventListener('click',function(e){
    e.preventDefault();show(a.dataset.view,a.dataset.anchor||null);});});

  document.addEventListener('click',function(e){
    var m=e.target.closest('mark.fact');
    if(m){var first=(m.dataset.targets||'').split(' ')[0];
      var el=document.getElementById(first);
      if(el){var sec=sectionOf(el);if(sec)show(sec,first);else{el.scrollIntoView();flash(el);}}
      return;}
    var x=e.target.closest('a.xref');
    if(x){e.preventDefault();var id=x.getAttribute('href').slice(1);
      var t=document.getElementById(id);
      if(t){var sec2=sectionOf(t);if(sec2)show(sec2,id);else{t.scrollIntoView();flash(t);}}
      return;}
    var claim=e.target.closest('[data-fid],[id^="fact-"]');
    var fid=claim&&(claim.dataset.fid||claim.id);
    if(fid){
      var lit=document.querySelectorAll('mark.fact');var found=null;
      lit.forEach(function(mk){
        var on=(mk.dataset.targets||'').split(' ').indexOf(fid)>=0;
        mk.classList.toggle('lit',on);if(on&&!found)found=mk;});
      if(found){var s3=sectionOf(found);if(s3)show(s3);found.scrollIntoView({block:'center'});
        flash(found);}
    }
  });

  var root=document.documentElement;
  var dark=window.matchMedia('(prefers-color-scheme: dark)').matches;
  if(root.getAttribute('data-theme'))dark=root.getAttribute('data-theme')==='dark';
  document.getElementById('theme').addEventListener('click',function(){
    dark=!dark;root.setAttribute('data-theme',dark?'dark':'light');});

  document.querySelectorAll('button[data-filter]').forEach(function(b){
    b.addEventListener('click',function(){
      var f=b.dataset.filter;var on=!b.classList.contains('on');
      b.parentElement.querySelectorAll('button[data-filter]').forEach(function(o){
        o.classList.remove('on');});
      if(on)b.classList.add('on');
      document.querySelectorAll('#claims .claim').forEach(function(c){
        c.style.display=(!on||f==='all'||c.querySelector('.basis-'+f))?'':'none';});});
  });
  var initial=document.querySelector('section.view').id,anchor=null;
  if(location.hash.length>1){
    var t0=document.getElementById(decodeURIComponent(location.hash.slice(1)));
    if(t0){var s0=sectionOf(t0);if(s0){initial=s0;anchor=t0.id;}}
  }
  show(initial,anchor);
})();
"""


# ---------------------------------------------------------------------------
# page assembly
# ---------------------------------------------------------------------------

def find_profile(spec_dir: Path) -> Path | None:
    """Same upward walk `new` uses: nearest `_profile.yml` wins."""
    here = spec_dir.resolve()
    for d in [here, *here.parents]:
        candidate = d / "_profile.yml"
        if candidate.is_file():
            return candidate
        if (d / ".git").exists():
            break
    return None


def stat(n, label: str, tone: str = "") -> str:
    style = f' style="color:var(--{tone})"' if tone else ""
    return (f'<div class="stat"><div class="n"{style}>{n}</div>'
            f'<div class="l">{html.escape(label)}</div></div>')


STATUS_RANK = {"draft": 0, "reviewed": 1, "implementing": 2, "shipped": 3}


def deferred_docs(facts: dict, spec_dir: Path) -> list[dict]:
    """`docs[]` entries whose `stage:` the set has not reached and which are not on
    disk. They are not missing — `implement` has not run yet — so the view says so
    rather than silently rendering a set that looks like it holds one document.
    Same contract as references/audit-protocol.md §Stage gating."""
    rank = STATUS_RANK.get(str(facts.get("status") or "draft").strip(), 0)
    out = []
    for entry in facts.get("docs") or []:
        if not isinstance(entry, dict):
            continue
        stage = str(entry.get("stage") or "draft")
        path = spec_dir / str(entry.get("file", ""))
        if STATUS_RANK.get(stage, 0) > rank and not path.is_file():
            out.append({"id": str(entry.get("id") or "?"),
                        "file": str(entry.get("file", "")), "stage": stage})
    return out


def build_overview(facts: dict, claims: list[dict], warnings: list[str],
                   dangling: list[str], orphans: list[str], docs: list[dict],
                   pending: list[dict] | None = None) -> str:
    counts = {b: sum(1 for c in claims if c["basis"] == b)
              for b in ("measured", "asserted", "decided")}
    parts = [f'<h1>{_inline(str(facts.get("title") or facts.get("feature", "spec")))}</h1>']
    parts.append(
        f'<p class="path mono">docs/features/{html.escape(str(facts.get("feature", "")))}'
        f' &middot; status: <strong>{html.escape(str(facts.get("status", "?")))}</strong></p>')

    parts.append('<div class="stat-row">')
    parts.append(stat(counts["measured"], "measured", "measured"))
    parts.append(stat(counts["asserted"], "asserted", "asserted"))
    parts.append(stat(counts["decided"], "decided", "decided"))
    parts.append(stat(len(docs), "docs"))
    if pending:
        parts.append(stat(len(pending), "docs pendientes"))
    parts.append(stat(len(dangling), "cross-refs rotos",
                      "danger" if dangling else ""))
    parts.append(stat(len(orphans), "datos sin citar",
                      "asserted" if orphans else ""))
    parts.append("</div>")

    if pending:
        listed = " &middot; ".join(
            f'<code>{html.escape(d["file"])}</code> (stage {html.escape(d["stage"])})'
            for d in pending)
        parts.append(
            '<div class="note"><strong>Etapa 1 &mdash; faltan documentos a '
            f'prop\u00f3sito.</strong> {listed}. Los escribe <code>implement</code>, '
            'una vez confirmado el plan. Sin esta l\u00ednea, un set incompleto y un '
            'set en etapa 1 se ven igual.</div>')

    if warnings:
        parts.append('<div class="warn"><strong>Gates / evidencia</strong><ul>'
                     + "".join(f"<li>{_inline(w)}</li>" for w in warnings) + "</ul></div>")
    if dangling:
        parts.append('<div class="warn"><strong>Cross-refs que no resuelven</strong><ul>'
                     + "".join(f"<li>{_inline(d)}</li>" for d in dangling) + "</ul></div>")

    parts.append('<div class="grid2">')
    for key, title in (("owners", "Owners"), ("tracking", "Tracking"), ("dates", "Fechas")):
        if facts.get(key) is not None:
            parts.append(f'<div class="card"><h3>{title}</h3>'
                         + render_value(facts[key], key) + "</div>")
    parts.append("</div>")

    # changes vs related_docs — kept visually disjoint on purpose
    parts.append('<div class="grid2">')
    parts.append('<div class="card"><h3>changes[] <span class="path">creados / modificados '
                 '· participan en scope-parity</span></h3>'
                 + render_value(facts.get("changes") or [], "changes") + "</div>")
    parts.append('<div class="card"><h3>related_docs[] <span class="path">solo referenciados '
                 '· NO son scope</span></h3>'
                 + render_value(facts.get("related_docs") or [], "related_docs") + "</div>")
    parts.append("</div>")

    if facts.get("acceptance"):
        parts.append('<div class="card"><h3>acceptance[] — Definition of Done</h3>'
                     + render_value(facts["acceptance"], "acceptance") + "</div>")
    return "".join(parts)


def build_claims(claims: list[dict]) -> str:
    parts = ['<h1>Claims &amp; evidencia</h1>',
             '<p>Cada entrada del registry que afirma algo sobre el mundo, con su '
             '<code>basis:</code>. <code>measured</code> trae el comando, la fecha y el '
             'output verbatim; <code>asserted</code> trae qué observación lo mataría.</p>',
             '<div class="toolbar">',
             '<button class="tbtn" data-filter="all">todos</button>',
             '<button class="tbtn" data-filter="measured">measured</button>',
             '<button class="tbtn" data-filter="asserted">asserted</button>',
             '<button class="tbtn" data-filter="decided">decided</button>',
             '</div><div id="claims">']
    if not claims:
        parts.append('<p class="empty">El registry no declara ningún <code>basis:</code>.</p>')
    for c in claims:
        parts.append(render_value(c["node"], c["path"]))
    parts.append("</div>")
    return "".join(parts)


def build_defects(facts: dict) -> str:
    defects = facts.get("defects") or []
    alts = facts.get("alternatives") or []
    parts = ['<h1>Defectos y alternativas</h1>']
    if not defects and not alts:
        return "".join(parts) + '<p class="empty">Sin <code>defects[]</code> ni <code>alternatives[]</code>.</p>'

    if defects:
        parts.append('<div class="board">')
        for status in ("open", "fixed", "dead"):
            group = [d for d in defects if isinstance(d, dict)
                     and str(d.get("status", "open")) == status]
            parts.append(f'<div class="col"><h3>{status} ({len(group)})</h3>')
            if not group:
                parts.append('<p class="empty">—</p>')
            for d in group:
                idx = defects.index(d)
                did = _slug(str(d.get("id") or idx))
                parts.append(f'<div id="def-{did}">'
                             + render_value(d, f"defects[{idx}]") + "</div>")
            parts.append("</div>")
        parts.append("</div>")

    if alts:
        parts.append("<h2>alternatives[]</h2>")
        parts.append('<p>Descartar por razonamiento es una afirmación: lleva '
                     '<code>basis</code> y <code>falsified_by</code>. '
                     '<code>depends_on</code> apunta a los ids del registry sobre los que '
                     'descansa — si uno muere, <code>verify</code> reabre la entrada.</p>')
        by_id = {str(d["id"]): "def-" + _slug(str(d["id"]))
                 for d in defects if isinstance(d, dict) and d.get("id")}
        for i, a in enumerate(alts):
            deps = a.get("depends_on") if isinstance(a, dict) else None
            body = {k: v for k, v in a.items() if k != "depends_on"} if deps else a
            block = render_value(body, f"alternatives[{i}]")
            if deps:
                links = "".join(
                    (f'<a class="chip tag" href="#{by_id[str(x)]}">{html.escape(str(x))}</a>'
                     if str(x) in by_id
                     else f'<span class="chip tag dangling" '
                          f'title="no existe un defects[] con id {html.escape(str(x), True)}">'
                          f'{html.escape(str(x))}</span>')
                    for x in deps)
                block += (f'<div class="ev-row"><span class="ev-k">depends_on</span>'
                          f'<span class="ev-v"><span class="chips">{links}</span></span></div>')
            parts.append(f'<div class="card">{block}</div>')
    return "".join(parts)


def build_matrix(datums: dict[str, list[str]], per_doc: dict[str, dict[str, int]],
                 docs: list[dict]) -> tuple[str, list[str]]:
    rows = []
    orphans = []
    for value in sorted(datums, key=lambda v: (-sum(per_doc[d["id"]].get(v, 0) for d in docs), v)):
        total = sum(per_doc[d["id"]].get(value, 0) for d in docs)
        if total == 0:
            orphans.append(value)
        cells = []
        for d in docs:
            n = per_doc[d["id"]].get(value, 0)
            cls = "hit" if n else ("orphan" if total == 0 else "miss")
            cells.append(f'<td class="{cls}">{n if n else "·"}</td>')
        paths = ", ".join(datums[value])
        rows.append(
            f'<tr><td class="val">{html.escape(value, quote=False)}</td>'
            f'<td class="k">{html.escape(paths)}</td>' + "".join(cells) + "</tr>")

    head = "".join(f'<th>{html.escape(str(d["id"]))}</th>' for d in docs)
    table = (
        '<div class="tablewrap"><table class="matrix"><thead><tr>'
        '<th>dato (registry)</th><th>clave</th>' + head + "</tr></thead><tbody>"
        + "".join(rows) + "</tbody></table></div>")
    intro = (
        "<h1>Matriz de correspondencia</h1>"
        "<p>Cada dato compartido del registry &times; cada doc. La cuenta es de citas "
        "textuales en prosa (los bloques <code>&lt;pre&gt;</code> no cuentan). "
        "Una fila entera en <span class='orphan' style='color:var(--asserted)'>·</span> es un "
        "dato declarado y nunca citado: o falta en los docs, o sobra en el registry.</p>")
    if orphans:
        intro += ('<div class="warn"><strong>' + str(len(orphans)) +
                  " dato(s) del registry sin una sola cita en prosa.</strong></div>")
    return intro + table, orphans


def build_log(rounds: list[dict], raw: str | None) -> str:
    parts = ['<h1>Handoff log</h1>']
    if raw is None:
        return "".join(parts) + ('<p class="empty">No hay <code>_log.md</code>. '
                                 'Sin él, la próxima ronda re-deriva lo que esta ya descartó.</p>')
    parts.append('<p>Append-only, más nueva abajo. <strong>Manda sobre el context window '
                 'de cualquier agente.</strong></p>')
    if not rounds:
        parts.append('<p class="empty">El log existe pero no tiene rondas <code>##</code>.</p>')
    parts.append('<div class="timeline">')
    for r in rounds:
        parts.append('<div class="round"><div class="round-head">'
                     f'<span class="round-id">{html.escape(r["id"])}</span>'
                     f'<span class="chip tag">{html.escape(r["kind"] or "?")}</span>'
                     f'<span class="round-meta">{html.escape(r["date"])} · '
                     f'{html.escape(r["who"])}</span></div>')
        parts.append('<div class="card">')
        for key, val in r["fields"]:
            parts.append(f'<div class="ev-row"><span class="ev-k">{html.escape(key)}</span>'
                         f'<span class="ev-v">{_inline(val)}</span></div>')
        for kind, text in r["dispositions"]:
            parts.append(f'<div class="disp"><span class="ev-k d-{kind}">{kind}</span>'
                         f'<span class="ev-v">{_inline(text)}</span></div>')
        rest = [ln for ln in r["body"] if ln not in r["disposition_lines"]]
        if any(ln.strip() for ln in rest):
            parts.append('<div class="round-body">'
                         + MarkdownRenderer(prefix=f"log-{_slug(r['id'])}-").render(
                             "\n".join(rest)) + "</div>")
        parts.append("</div></div>")
    parts.append("</div>")
    return "".join(parts)


def build_page(spec_dir: Path) -> str:
    facts_path = spec_dir / "_facts.yml"
    if not facts_path.is_file():
        sys.exit(f"no _facts.yml in {spec_dir} — not a feature-spec set.")
    facts = yaml.safe_load(facts_path.read_text(encoding="utf-8")) or {}

    doc_entries = facts.get("docs") or []
    docs: list[dict] = []
    for entry in doc_entries:
        if not isinstance(entry, dict):
            continue
        path = spec_dir / str(entry.get("file", ""))
        if path.is_file():
            docs.append({"id": str(entry.get("id") or path.stem[:2]),
                         "file": path.name, "role": str(entry.get("role", "")),
                         "text": path.read_text(encoding="utf-8")})
    if not docs:  # registry has no docs[] — fall back to the numbered files on disk
        for path in sorted(spec_dir.glob("[0-9][0-9]*.md")):
            docs.append({"id": path.stem[:2], "file": path.name, "role": "",
                         "text": path.read_text(encoding="utf-8")})

    claims = collect_claims(facts)
    warnings = status_gate(facts, claims)
    datums = {v: p for v, p in collect_datums(facts).items()
              if not all(x.startswith(STOP_PATH_PREFIXES) for x in p)}
    rx = build_datum_regex(datums)

    # pass 1: markdown -> html, collecting headings for cross-ref resolution
    sections: dict[str, dict[str, str]] = {}
    for d in docs:
        renderer = MarkdownRenderer(prefix=f"d{d['id']}-")
        d["html"] = renderer.render(d["text"])
        d["headings"] = renderer.headings
        sections[d["id"]] = {h["number"]: h["id"] for h in renderer.headings if h["number"]}

    # pass 2: cross-refs, then provenance (order matters — refs may contain datums)
    dangling: list[str] = []
    per_doc: dict[str, dict[str, int]] = {}
    doc_ids = [x["id"] for x in docs]
    for d in docs:
        d["html"] = link_crossrefs(d["html"], d["id"], sections, dangling, doc_ids)
        hits: dict[str, int] = {}
        d["html"] = mark_provenance(d["html"], datums, rx, hits)
        per_doc[d["id"]] = hits

    matrix_html, orphans = build_matrix(datums, per_doc, docs)

    log_path = spec_dir / "_log.md"
    raw_log = log_path.read_text(encoding="utf-8") if log_path.is_file() else None
    rounds = parse_log(raw_log) if raw_log else []

    profile_path = find_profile(spec_dir)
    profile = {}
    if profile_path:
        try:
            profile = yaml.safe_load(profile_path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            profile = {}

    # ---- sections. Registry is rendered last-but-canonical: it owns the ids.
    set_canonical(False)
    views: list[tuple[str, str, str]] = []  # id, nav label, html
    views.append(("v-overview", "Resumen",
                  build_overview(facts, claims, warnings, dangling, orphans, docs,
                                 deferred_docs(facts, spec_dir))))
    for d in docs:
        label = f"{d['id']} · {d['role'] or d['file']}"
        views.append((f"v-doc-{d['id']}", label, d["html"]))
    views.append(("v-claims", "Claims &amp; evidencia", build_claims(claims)))
    views.append(("v-defects", "Defectos", build_defects(facts)))
    views.append(("v-matrix", "Matriz", matrix_html))
    views.append(("v-log", "Log", build_log(rounds, raw_log)))

    set_canonical(True)
    registry_html = ["<h1>Registry — <code>_facts.yml</code></h1>",
                     "<p>Fuente única de verdad. Click en cualquier valor resalta dónde se "
                     "cita en la prosa.</p>"]
    if profile_path:
        registry_html.append(
            f'<div class="card"><h3><code>_profile.yml</code> '
            f'<span class="path">{html.escape(str(profile_path))}</span></h3>'
            + render_value(profile.get("commands") or profile, "profile.commands") + "</div>")
    for key in facts:
        registry_html.append(f'<div class="card"><h3 id="sec-{_slug(str(key))}">'
                             f'<code>{html.escape(str(key))}</code></h3>'
                             + render_value(facts[key], str(key)) + "</div>")
    views.append(("v-registry", "Registry", "".join(registry_html)))

    # ---- nav
    nav = ['<div class="brand">feature-spec</div>',
           f'<p class="title">{html.escape(str(facts.get("title") or facts.get("feature", "")))}</p>',
           '<div class="status-row">',
           f'<span class="chip tag">{html.escape(str(facts.get("status", "?")))}</span>',
           f'<span class="chip basis-measured">{sum(1 for c in claims if c["basis"] == "measured")} measured</span>',
           f'<span class="chip basis-asserted">{sum(1 for c in claims if c["basis"] == "asserted")} asserted</span>',
           "</div><nav>"]
    nav.append('<div class="group">vista</div>')
    nav.append('<a data-view="v-overview">Resumen</a>')
    nav.append('<div class="group">documentos</div>')
    for d in docs:
        nav.append(f'<a data-view="v-doc-{d["id"]}">{html.escape(d["id"])} · '
                   f'{html.escape(d["role"] or d["file"])}</a>')
        toc = [f'<div class="toc" data-view="v-doc-{d["id"]}">']
        for h in d["headings"]:
            if h["level"] not in (2, 3):
                continue
            cls = "lvl3" if h["level"] == 3 else ""
            toc.append(f'<a class="{cls}" data-view="v-doc-{d["id"]}" '
                       f'data-anchor="{h["id"]}">{html.escape(h["text"])}</a>')
        toc.append("</div>")
        if len(toc) > 2:
            nav.append("".join(toc))
    nav.append('<div class="group">análisis</div>')
    for vid, label in (("v-claims", "Claims &amp; evidencia"), ("v-defects", "Defectos"),
                       ("v-matrix", "Matriz"), ("v-log", "Log"), ("v-registry", "Registry")):
        nav.append(f'<a data-view="{vid}">{label}</a>')
    nav.append("</nav>")

    body = "".join(
        f'<section class="view" id="{vid}">{content}</section>' for vid, _, content in views)

    title = html.escape(str(facts.get("title") or facts.get("feature", "Feature spec")))
    return f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<style>{CSS}</style></head>
<body><div class="layout"><aside>{"".join(nav)}</aside><main>{body}
<p class="footnote">Vista generada por <code>feature-spec view</code> desde
<code>_facts.yml</code> y los docs. Artefacto derivado — no editar: editar el registry
y volver a renderizar.</p></main></div>
<button class="tbtn theme-toggle" id="theme">tema</button>
<script>{JS}</script></body></html>"""


# ---------------------------------------------------------------------------
# cli
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("spec_dir", type=Path, help="docs/features/<slug>/")
    ap.add_argument("-o", "--out", type=Path, default=None,
                    help="output file (default: <spec-dir>/view.html)")
    ap.add_argument("--open", action="store_true", dest="open_",
                    help="open the result in the default browser")
    ap.add_argument("--serve", nargs="?", const=8000, type=int, metavar="PORT",
                    help="serve the spec dir over HTTP after rendering")
    ap.add_argument("--lan", action="store_true",
                    help="with --serve, bind 0.0.0.0 instead of 127.0.0.1 "
                         "(exposes the spec on your network)")
    args = ap.parse_args(argv)

    spec_dir = args.spec_dir.resolve()
    if not spec_dir.is_dir():
        sys.exit(f"not a directory: {spec_dir}")
    out = (args.out or spec_dir / "view.html").resolve()
    out.write_text(build_page(spec_dir), encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size // 1024} KB, self-contained)")

    if args.open_ and not args.serve:
        webbrowser.open(out.as_uri())
    if args.serve:
        import functools
        from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

        host = "0.0.0.0" if args.lan else "127.0.0.1"
        handler = functools.partial(SimpleHTTPRequestHandler, directory=str(out.parent))
        url = f"http://{'localhost' if not args.lan else host}:{args.serve}/{out.name}"
        if args.lan:
            print("WARNING: --lan binds 0.0.0.0 — this spec is reachable by anyone "
                  "on your network. Ctrl-C to stop.")
        print(f"serving {url}")
        if args.open_:
            webbrowser.open(url)
        try:
            ThreadingHTTPServer((host, args.serve), handler).serve_forever()
        except KeyboardInterrupt:
            print("\nstopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
