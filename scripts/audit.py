#!/usr/bin/env python3
"""audit.py — the mechanizable half of references/audit-protocol.md.

The protocol holds 17 checks in prose and they are good. The problem is not their
content: an agent runs the checks it remembers, and in a long session it remembers a
few. A rough version of this script, with ~10 checks, found 12 / 11 / 7 findings in
three sets that had each already passed a "clean" audit done by hand against the same
protocol. None were subtle: broken anchors, a corrupted top-level key, orphan ids.

So: this script runs every check a program can run, and prints the ones it cannot as
`REQUIRES A HUMAN PASS` rather than pretending they passed. The `audit` mode is this
script FIRST, then the judgment pass over what it lists — in that order.

    python3 scripts/audit.py docs/features/<slug>/ [--repo-root DIR] [--json]

It never executes `evidence.cmd` (protocol check 1b). A registry is a data file that
travels between repos and agents; running commands out of it because it claims they
are safe is the one thing an auditor must not do. Re-running evidence is a human step
and is listed as one.

The shared registry core is imported from render.py so the two cannot drift: a check
implemented twice is the exact defect this skill exists to prevent.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from render import (accepted_state, collect_claims, norm, status_gate,
                        walk, yaml)
except ImportError as exc:  # pragma: no cover
    sys.exit(
        f"cannot import the shared registry core from render.py: {exc}\n"
        "audit.py and render.py deliberately share one implementation of the "
        "registry walk and the basis gates. Both must be present in scripts/."
    )

SKILL_DIR = Path(__file__).resolve().parent.parent
TEMPLATE = SKILL_DIR / "templates" / "_facts.yml.tpl"

CONTRADICTION, DRIFT, POLISH = "CONTRADICTION", "DRIFT", "POLISH"
STATUS_RANK = {"draft": 0, "reviewed": 1, "implementing": 2, "shipped": 3}

ID_CONTAINERS = ("defects", "alternatives", "limits", "contracts",
                 "acceptance", "changes", "decisions", "endpoints")
# Containers whose entries are legitimately never named in prose by key.
ORPHAN_EXEMPT = ("decisions",)
EXECUTABLE_HOW = {"shell", "git", "sql", "psql", "bash", "curl", "rg"}
TEXT_FIELDS = ("claim", "note", "because", "name", "change", "reopens_when",
               "note_ownership", "falsified_by", "what")
ANCHOR_RE = re.compile(r"(?<![\w/.])([A-Za-z0-9_./-]+\.[A-Za-z0-9]{1,6}):(\d+)\b")
PROSE_CMD_STARTERS = re.compile(
    r"^\s*(ver|vease|véase|see|check|revisar|consultar|mismo|idem|igual)\b", re.I)


class Findings:
    def __init__(self) -> None:
        self.items: list[dict] = []

    def add(self, sev: str, where: str, what: str, fix: str, check: str) -> None:
        self.items.append({"severity": sev, "where": where, "what": what,
                           "fix": fix, "check": check})

    def count(self, sev: str) -> int:
        return sum(1 for f in self.items if f["severity"] == sev)


# --------------------------------------------------------------------------
# loading
# --------------------------------------------------------------------------

def repo_root_for(spec_dir: Path, override: str | None) -> Path:
    if override:
        return Path(override).resolve()
    try:
        out = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                             cwd=spec_dir, capture_output=True, text=True, check=True)
        return Path(out.stdout.strip())
    except (subprocess.CalledProcessError, FileNotFoundError):
        return spec_dir


def load_facts(path: Path) -> dict:
    """Vault ingestion prepends frontmatter, making the file a TWO-document YAML
    stream; safe_load raises ComposerError on it. Take the last document."""
    text = path.read_text(encoding="utf-8")
    try:
        return yaml.safe_load(text) or {}
    except yaml.YAMLError:
        docs = [d for d in yaml.safe_load_all(text) if isinstance(d, dict)]
        if not docs:
            raise
        return docs[-1]


def template_keys() -> set[str]:
    if not TEMPLATE.is_file():
        return set()
    return set(yaml.safe_load(TEMPLATE.read_text(encoding="utf-8")) or {})


# --------------------------------------------------------------------------
# stage gating (protocol §Stage gating)
# --------------------------------------------------------------------------

def resolve_stage(facts: dict, spec_dir: Path) -> tuple[int, list[dict], list[dict]]:
    """-> (status rank, docs in scope, docs deferred to a later stage)."""
    status = norm(facts.get("status")) or "draft"
    rank = STATUS_RANK.get(status, 0)
    in_scope, deferred = [], []
    for entry in facts.get("docs") or []:
        if not isinstance(entry, dict):
            continue
        path = spec_dir / str(entry.get("file", ""))
        item = {"id": str(entry.get("id") or "?"), "file": str(entry.get("file", "")),
                "stage": norm(entry.get("stage")) or "draft", "path": path,
                "exists": path.is_file()}
        # In scope when its stage is reached, OR when the file exists anyway:
        # never skip a file that is on disk — that is the copy written against
        # the old plan, and it is exactly what the checks are for.
        if STATUS_RANK.get(item["stage"], 0) <= rank or item["exists"]:
            in_scope.append(item)
        else:
            deferred.append(item)
    return rank, in_scope, deferred


# --------------------------------------------------------------------------
# checks
# --------------------------------------------------------------------------

def check_top_level_keys(facts: dict, f: Findings) -> None:
    """§1.2. Editing the registry by hand deleted `alternatives:` and silently
    reparented A1-A4 under `defects:`, which went from 9 to 13 entries. The YAML
    was valid, every datum survived, and the audit passed clean."""
    expected = template_keys()
    if not expected:
        return
    extra = sorted(set(facts) - expected)
    if extra:
        f.add(DRIFT, "_facts.yml", f"top-level keys not in the template: {extra}",
              "either they belong in templates/_facts.yml.tpl (add them) or an edit "
              "reparented entries under the wrong key",
              "19 registry shape vs template")


def check_docs_on_disk(in_scope: list[dict], deferred: list[dict], f: Findings) -> None:
    for d in in_scope:
        if not d["exists"]:
            f.add(DRIFT, f"docs[] {d['id']}",
                  f"stage `{d['stage']}` is reached but {d['file']} is not on disk",
                  "write it, or lower `status:` to the stage the set is really at",
                  "9 docs[] -> disk")
    for d in deferred:
        if d["exists"]:
            f.add(POLISH, f"docs[] {d['id']}",
                  f"{d['file']} exists but its stage `{d['stage']}` is not reached yet",
                  "someone wrote ahead of the stage, or `status:` was rolled back and "
                  "the doc was not; it is checked anyway",
                  "9 docs[] -> disk")


def check_basis_gates(facts: dict, f: Findings) -> None:
    """Check 1b + check 14. The first half is render.py's status_gate (shared, so the
    two tools cannot disagree); the four gates and the shipped/open detector are here."""
    claims = collect_claims(facts)
    for w in status_gate(facts, claims):
        sev = CONTRADICTION if w.startswith("G1:") else DRIFT
        w = re.sub(r"`([^`]+)`",
                   lambda m: "`%s`" % pretty_path(facts, m.group(1)), w, count=1)
        f.add(sev, "_facts.yml", w.rstrip("."), "see references/evidence.md",
              "1b/14 basis")

    status = norm(facts.get("status"))
    by_id = {}
    for key in ("defects", "alternatives"):
        for e in facts.get(key) or []:
            if isinstance(e, dict) and e.get("id"):
                by_id[str(e["id"])] = (key, e)

    for key in ("defects", "alternatives"):
        for e in facts.get(key) or []:
            if not isinstance(e, dict):
                continue
            eid = str(e.get("id", "?"))
            where = f"{key}.{eid}"

            if norm(e.get("basis")) == "asserted" and not e.get("falsified_by"):
                pass  # already reported by status_gate
            if (key == "defects" and norm(e.get("basis")) == "asserted"
                    and e.get("falsified_by") and not e.get("log_line")):
                f.add(DRIFT, where,
                      "`falsified_by:` names an observation with no `log_line:`",
                      "name the emitter that produces it, or `log_line: null` to say "
                      "it must be built — instrumentation is spec, not an afterthought",
                      "14 basis gates")

            if (key == "alternatives" and norm(e.get("outcome")) == "discarded"
                    and norm(e.get("basis")) == "asserted"):
                for dep in e.get("depends_on") or []:
                    target = by_id.get(str(dep), (None, {}))[1]
                    if norm(target.get("status")) == "dead":
                        f.add(CONTRADICTION, where,
                              f"discarded on `{dep}`, whose status is now `dead`",
                              "the premise died, so the discard is void — `verify` "
                              "should have flipped this to `outcome: reopened`",
                              "14 basis gates")

            # The cheap detector for the failure the four gates above still miss.
            if (status == "shipped" and norm(e.get("status")) == "open"
                    and not e.get("owned_by") and not e.get("outcome")):
                f.add(CONTRADICTION, where,
                      "still `open` in a set marked `shipped`, with no `owned_by:` "
                      "and no `outcome:`",
                      "a question the set declared closed without answering: point "
                      "`owned_by:` at where the fix lives, or write the `outcome:` — "
                      "staying open as an accepted risk is valid, staying SILENT is not",
                      "14 basis gates")


def check_declared_dependencies(facts: dict, f: Findings) -> None:
    """§4.3. An entry whose prose names another id but does not declare it in
    `depends_on:`. That arrow exists either way; undeclared, the cascade cannot run.
    Real case: F2's note said "what decides whether this matters is F3" in prose, F3
    was later measured and died, and nobody went back to F2."""
    known = set()
    for key in ("defects", "alternatives"):
        for e in facts.get(key) or []:
            if isinstance(e, dict) and e.get("id"):
                known.add(str(e["id"]))
    for key in ("defects", "alternatives"):
        for e in facts.get(key) or []:
            if not isinstance(e, dict):
                continue
            eid = str(e.get("id", "?"))
            declared = {str(x) for x in (e.get("depends_on") or [])}
            text = " ".join(str(e.get(fld, "")) for fld in TEXT_FIELDS)
            known_lower = {k.lower(): k for k in known}
            declared_lower = {d.lower() for d in declared}
            for other in re.findall(r"`([A-Za-z]\d+)`", text):
                if (other.lower() in known_lower and other.lower() != eid.lower()
                        and other.lower() not in declared_lower):
                    f.add(DRIFT, f"{key}.{eid}",
                          f"names `{other}` in its prose but does not declare it in "
                          "`depends_on:`",
                          f"add `depends_on: [{other}]` — when {other} dies or changes "
                          "basis, nothing can find this entry to revisit it",
                          "25 declared dependencies")


def check_changes_vocabulary(facts: dict, f: Findings) -> None:
    """§2.1. A deferral with no reopen condition is not deferred, it is abandoned."""
    required = {"deferred": ("reopens_when", "deferred_because"),
                "moved_out": ("moved_to",),
                "pending": ("transferred_from",)}
    for idx, e in enumerate(facts.get("changes") or []):
        if not isinstance(e, dict):
            continue
        cid = str(e.get("id") or e.get("file") or f"[{idx}]")
        kind = norm(e.get("kind")) or None
        if kind is None:
            f.add(DRIFT, f"changes.{cid}", "no `kind:`",
                  "planned | deferred | moved_out | pending — an unclassified change "
                  "is an undecided one, and `implement` refuses to run on it",
                  "23 changes[] lifecycle")
            continue
        # "the daily peak passes ~200 distinct users. Today: 5" is a condition.
        # "when traffic grows" is an opinion, and reopening on an opinion never
        # happens. Without the number the discussion is one view against another.
        if kind == "deferred" and e.get("reopens_when") \
                and not re.search(r"\d", str(e["reopens_when"])):
            f.add(DRIFT, f"changes.{cid}",
                  "`reopens_when:` states no measured value",
                  "name the number that reopens it and today's number beside it — "
                  "a threshold with no measurement is an opinion, and nothing "
                  "reopens on an opinion",
                  "23 changes[] lifecycle")
        for field in required.get(kind, ()):
            if not e.get(field):
                f.add(DRIFT, f"changes.{cid}",
                      f"`kind: {kind}` with no `{field}:`",
                      "a deferral with no reopen condition is a change abandoned with "
                      "better wording" if field == "reopens_when"
                      else f"state `{field}:`",
                      "23 changes[] lifecycle")


def normalize_acceptance(facts: dict) -> list[dict]:
    """A plain string is still a valid criterion and reads as `status: written`,
    so sets written before the field existed keep auditing."""
    out = []
    for i, e in enumerate(facts.get("acceptance") or []):
        if isinstance(e, dict):
            out.append({"id": str(e.get("id") or f"[{i}]"),
                        "item": str(e.get("item") or e.get("claim") or ""),
                        "status": norm(e.get("status")),
                        "verified_on": e.get("verified_on")})
        else:
            out.append({"id": f"[{i}]", "item": str(e), "status": "", "verified_on": None})
    return out


def check_acceptance_state(facts: dict, status_rank: int, f: Findings) -> None:
    """§2.4 + §4.2. `acceptance[]` is the contract; `_log.md` is narrative. A set
    was marked `shipped` holding two criteria nothing could satisfy — one of them
    annotated "this is THE test of the set" — because the decision that killed them
    was recorded in the log and never propagated to the contract. The audit passed
    clean: no check compared acceptance[] against reality. This is that check."""
    if status_rank < STATUS_RANK["shipped"]:
        return
    items = normalize_acceptance(facts)
    if not items:
        return

    # A set that predates the field has NO criterion carrying a status. Reporting
    # each one is a wall of identical findings that buries the other contradictions
    # in the same set — the failure this protocol names one level up. Collapse it
    # into one, and say plainly that it is an adoption gap.
    # A set where SOME criteria carry a status and others do not is a different
    # thing entirely: somebody adopted the field and skipped items. Report those
    # one by one, because each is a specific criterion nobody verified.
    if all(e["status"] == "" for e in items):
        f.add(CONTRADICTION, "acceptance[]",
              f"the set is `shipped` and none of its {len(items)} criteria carry a "
              "`status:` — nothing records whether any of them was ever verified",
              "adopt `status: written|executed|approved` per criterion and fill it "
              "from what actually ran. Until then the set's own contract cannot say "
              "whether it was met, which is how one shipped holding two criteria "
              "nothing could satisfy",
              "26 acceptance state")
        return

    for e in items:
        label = f"acceptance.{e['id']}"
        detail = f": {e['item'][:60]!r}" if e["item"] else ""
        if e["status"] in ("", "written"):
            f.add(CONTRADICTION, label,
                  f"the set is `shipped` but this criterion was never verified"
                  f" (status {e['status'] or 'absent'}){detail}",
                  "run it and record `status: executed|approved` with its date — or, "
                  "if a trimmed scope made it unreachable, rewrite it against the "
                  "substitute mechanism or delete it and write down the accepted risk",
                  "26 acceptance state")
        elif e["status"] == "executed":
            f.add(DRIFT, label,
                  f"`shipped` with this criterion executed but not approved{detail}",
                  "someone ran it; nobody signed it off",
                  "26 acceptance state")
        elif e["status"] == "approved" and not e["verified_on"]:
            f.add(DRIFT, label, "`approved` with no date",
                  "`verified_on:` — an approval with no date cannot be checked for "
                  "staleness. (Never name this field `on:`: YAML 1.1 reads it as "
                  "the boolean True and the value silently lands under a key "
                  "nothing reads.)",
                  "26 acceptance state")


def check_dead_dependency_cascade(facts: dict, f: Findings) -> None:
    """§4.3. `verify` already reopens a discarded `alternatives[]` entry whose
    premise died. The other half — and the more common one — was missing: an entry
    whose open question was ANSWERED by the death of its dependency, which nobody
    goes back to.

    F2 depended on F3. A later round measured F3 and left it `dead` — a clean round,
    with evidence. Nobody returned to F2: its note still said "lo NO MEDIDO" about
    something measured hours earlier. The set shipped and the audit passed clean.
    Staying `open` is a perfectly valid answer; staying open with no `outcome:` is
    a question the set declared closed without answering."""
    entries = {}
    for key in ("defects", "alternatives"):
        for e in facts.get(key) or []:
            if isinstance(e, dict) and e.get("id"):
                entries[str(e["id"])] = (key, e)
    for eid, (key, e) in entries.items():
        if norm(e.get("status")) != "open" or e.get("outcome"):
            continue
        for dep in e.get("depends_on") or []:
            target = entries.get(str(dep), (None, {}))[1]
            if norm(target.get("status")) == "dead":
                f.add(DRIFT, f"{key}.{eid}",
                      f"still `open` with no `outcome:`, but `{dep}` — which it "
                      "depends on — is now `dead`",
                      f"the question this entry was waiting on has an answer: write "
                      f"the `outcome:` it now has. Remaining open as an accepted risk "
                      f"is fine, and is itself an outcome worth stating",
                      "27 dead-dependency cascade")
                break


def check_file_existence(facts: dict, repo_root: Path, status_rank: int,
                         f: Findings) -> None:
    """§1.3. Registry-declared paths must resolve. Two documented exceptions:
    `where: external` (a cron job, a dashboard setting — no file here), and a
    `changes[]` file the set has not created yet, which is only a finding once the
    set claims to be implementing."""
    for key in ("changes", "related_docs"):
        for e in facts.get(key) or []:
            if not isinstance(e, dict):
                continue
            raw = e.get("file") or e.get("path")
            if not raw:
                continue
            if norm(e.get("where")) == "external":
                continue
            if key == "changes" and norm(e.get("kind")) in ("deferred", "moved_out"):
                continue  # decided not to build it — the file is absent by design
            if key == "changes" and status_rank < STATUS_RANK["implementing"]:
                continue  # a file this set will create legitimately isn't there yet
            if (repo_root / str(raw)).exists():
                continue
            f.add(CONTRADICTION, f"{key}.{e.get('id', raw)}",
                  f"declares `{raw}`, which does not exist under {repo_root.name}/",
                  "fix the path, or mark it `where: external` if it has no file in "
                  "this repo",
                  "20 declared paths exist")


def check_anchors(facts: dict, prose: dict[str, str], repo_root: Path,
                  f: Findings) -> None:
    """§1.1, the most frequent finding of all. Check 13 verifies an edit HAS an
    anchor; nothing verified that the anchor RESOLVES. In one set, five anchors had
    been moved by the author's own later edits inside the same session, and a sibling
    set carried eight bare `index.ts:18` with no path at all.

    `_log.md` is excluded: it is append-only history recording what was true then,
    and its anchors are never corrected."""
    sources = {"_facts.yml": yaml.safe_dump(facts, allow_unicode=True)}
    sources.update(prose)
    for src, text in sources.items():
        if src == "_log.md":
            continue
        for path_str, line_str in set(ANCHOR_RE.findall(text)):
            line = int(line_str)
            target = repo_root / path_str
            if "/" not in path_str:
                matches = list(repo_root.rglob(path_str))
                if len(matches) != 1:
                    f.add(DRIFT, src,
                          f"bare anchor `{path_str}:{line}` with no path "
                          f"({len(matches)} files carry that name)",
                          "anchors resolve from the repo root — write the full path",
                          "18 anchors resolve")
                    continue
                target = matches[0]
            if not target.is_file():
                f.add(CONTRADICTION, src, f"anchor `{path_str}:{line}` — file missing",
                      "the file moved or was renamed; re-anchor",
                      "18 anchors resolve")
                continue
            total = sum(1 for _ in target.open(encoding="utf-8", errors="ignore"))
            if line > total:
                f.add(CONTRADICTION, src,
                      f"anchor `{path_str}:{line}` is past end of file ({total} lines)",
                      "a later edit moved it — re-anchor against the current tree",
                      "18 anchors resolve")


def registry_ids(facts: dict) -> dict[str, str]:
    ids: dict[str, str] = {}
    for key in ID_CONTAINERS:
        node = facts.get(key)
        if isinstance(node, dict):
            ids.update({str(k): key for k in node})
        elif isinstance(node, list):
            for e in node:
                if isinstance(e, dict) and e.get("id"):
                    ids[str(e["id"])] = key
    return ids


def entry_values(facts: dict, container: str, name: str) -> list[str]:
    """Every scalar under one registry entry that is distinctive enough to look for
    in prose. Short values and pure structure are skipped: matching on `open` or `3`
    would make the orphan check pass for everything."""
    node = facts.get(container)
    entry = None
    if isinstance(node, dict):
        entry = node.get(name)
    elif isinstance(node, list):
        entry = next((e for e in node
                      if isinstance(e, dict) and str(e.get("id")) == name), None)
    if entry is None:
        return []
    out = []
    for path, sub in walk(entry):
        if isinstance(sub, (dict, list)) or sub is None or isinstance(sub, bool):
            continue
        tail = path.rsplit(".", 1)[-1].split("[")[0]
        if tail in ("id", "basis", "status", "role", "kind", "where", "outcome", "how"):
            continue
        # Same thresholds render.py uses to decide what is worth tracing into
        # prose: numbers below 10 and very short strings match everywhere.
        if isinstance(sub, (int, float)):
            if abs(sub) >= 10:
                out.append(str(sub))
        elif len(str(sub).strip()) >= 4:
            out.append(str(sub).strip())
    return out


def check_orphan_and_dangling_ids(facts: dict, prose: dict[str, str],
                                  f: Findings) -> None:
    """§1.4 (registry -> prose) and §2.2 (prose -> registry).

    Cross-set references are legitimate and are excluded: a line that qualifies the
    citation with the owning set's slug (`` `chat-document-upload` defects.D4 ``) is
    not a dangling ref. A local mirror id is never the answer — that is how a `D4_ajeno`
    had to be renamed across four files when the owner changed."""
    ids = registry_ids(facts)
    by_lower = {k.lower(): v for k, v in ids.items()}
    slug = str(facts.get("feature") or "")
    body = "\n".join(prose.values())

    for name, container in sorted(ids.items()):
        if container in ORPHAN_EXEMPT:
            continue  # a decision is cited by consequence, not by key (report §3.5)
        if re.search(rf"(?<!\w){re.escape(name)}\b", body, re.I):
            continue
        # Cited by VALUE counts as cited. An orphan is an entry no doc mentions at
        # all — "measured, correct and dead". A `limits.cloudflare` whose 100 and 524
        # are quoted in prose is being read; nobody writes `limits.cloudflare` inline.
        # Case-insensitive: an entry whose text appears in prose with a different
        # capitalisation IS being read. Whether it was copied verbatim is check 1's
        # question and a human one; reporting it as an orphan says nobody reads it,
        # which is a different and wrong claim.
        low = body.lower()
        if any(v.lower() in low for v in entry_values(facts, container, name)):
            continue
        f.add(DRIFT, f"{container}.{name}",
              "never cited in any prose doc, by id or by value",
              "measured, correct and dead — cite it where it belongs, or drop it",
              "21 registry ids <-> prose")

    containers = "|".join(ID_CONTAINERS)
    for doc, text in prose.items():
        for lineno, line in enumerate(text.splitlines(), 1):
            # A qualified cross-set citation names the OWNING set on the same line,
            # either as a bare slug or — more often — as a path to its registry:
            #   Sale de `docs/features/chat-document-upload/_facts.yml defects.D6`
            # Those are legitimate (§2.2) and a mirror id is never the answer.
            quoted = re.findall(r"`([^`]+)`", line)
            if any(re.search(r"[a-z0-9]+-[a-z0-9-]{3,}", q)
                   and slug not in q for q in quoted):
                continue
            for container, name in re.findall(
                    rf"\b({containers})\.([A-Za-z0-9_]+)", line, re.I):
                container, name = norm(container), name
                owner = by_lower.get(name.lower())
                if owner == container:
                    continue
                if owner is not None:
                    f.add(CONTRADICTION, f"{doc}:{lineno}",
                          f"cites `{container}.{name}`, but `{name}` lives under "
                          f"`{owner}:` in the registry",
                          "an edit reparented it: the entry survived, its category "
                          "did not, and every check downstream reads it as the wrong "
                          "kind of thing",
                          "21 registry ids <-> prose")
                    continue
                if container not in facts:
                    f.add(CONTRADICTION, f"{doc}:{lineno}",
                          f"cites `{container}.{name}` but the registry has no "
                          f"`{container}:` key at all",
                          "the whole container is gone — an edit almost certainly "
                          "reparented its entries under a neighbouring key; compare "
                          "against the template before anything else",
                          "21 registry ids <-> prose")
                else:
                    f.add(DRIFT, f"{doc}:{lineno}",
                          f"cites `{container}.{name}`, which the registry does not "
                          "define",
                          "fix the id, or qualify it with the owning set's slug if it "
                          "belongs to a sibling set",
                          "21 registry ids <-> prose")


def check_phase_numbering(prose: dict[str, str], f: Findings) -> None:
    """§1.5. A "Fase 8" was inserted into a doc that already had a Fase 8 and a
    Fase 9. Caught by re-reading headings by hand, not by the audit."""
    for doc, text in prose.items():
        nums = [int(n) for n in re.findall(r"^#{2,4}\s+Fase\s+(\d+)", text, re.M)]
        if not nums:
            continue
        dupes = sorted({n for n in nums if nums.count(n) > 1})
        if dupes:
            f.add(CONTRADICTION, doc, f"duplicate phase numbers: {dupes}",
                  "renumber — a phase number is how doc 02 is navigated and cited",
                  "22 phase numbering")
        gaps = sorted(set(range(min(nums), max(nums) + 1)) - set(nums))
        if gaps:
            f.add(DRIFT, doc, f"missing phase numbers: {gaps}",
                  "a phase was removed without renumbering, or one is missing",
                  "22 phase numbering")


def pretty_path(facts: dict, path: str) -> str:
    """`defects[2]` -> `defects.D5`. A finding you cannot locate is half a finding,
    and a list index shifts the moment anyone inserts an entry above it."""
    def sub(m):
        container, idx = m.group(1), int(m.group(2))
        node = facts.get(container)
        if isinstance(node, list) and idx < len(node):
            entry = node[idx]
            if isinstance(entry, dict) and entry.get("id"):
                return f"{container}.{entry['id']}"
        return m.group(0)
    return re.sub(r"\b(\w+)\[(\d+)\]", sub, path)


def check_evidence_cmd_runnable(facts: dict, f: Findings) -> None:
    """§3.3. The protocol said "cmd not runnable here -> note it". Too soft. A defect
    carried `basis: measured` and was INVERTED — it claimed two names collide when they
    do not — and survived for months because its `cmd` was a placeholder that could
    never be re-run. A `measured` that cannot be re-executed verbatim is the only kind
    of lie that propagates to all three docs with perfect fidelity."""
    for path, node in walk(facts):
        if not (isinstance(node, dict) and norm(node.get("basis")) == "measured"):
            continue
        ev = node.get("evidence") or {}
        how = norm(ev.get("how"))
        cmd = str(ev.get("cmd", "") or "")
        if how not in EXECUTABLE_HOW or not cmd:
            continue  # `how: device|log|sentry` points at a UI or a procedure
        if PROSE_CMD_STARTERS.match(cmd) or "`" in cmd:
            f.add(CONTRADICTION, pretty_path(facts, path) or "_facts.yml",
                  f"`basis: measured` whose cmd is a prose reference, not a command: "
                  f"{cmd.strip()[:60]!r}",
                  "write the command that reproduces the value, or drop to "
                  "`basis: asserted` with a `falsified_by:`",
                  "24 cmd runnable verbatim")
            continue
        # `%{http_code}` / `%{time_total}` are curl --write-out directives, not
        # unfilled slots: a naive `{...}` sweep reports every measured curl probe.
        # Only _profile.yml's own substitution keys count as placeholders.
        holes = re.findall(
            r"<[a-z_][a-z_0-9]*>|(?<!%)\{(?:app_id|log_tag|path|slug)\}"
            r"|\bTBD\b|\bXXX\b", cmd)
        if holes:
            f.add(CONTRADICTION, pretty_path(facts, path) or "_facts.yml",
                  f"`basis: measured` whose cmd still has placeholders {holes}: "
                  f"{cmd.strip()[:60]!r}",
                  "substitute them from _profile.yml — a cmd nobody can paste is a "
                  "measurement nobody can repeat",
                  "24 cmd runnable verbatim")


def check_tracking(facts: dict, repo_root: Path, f: Findings) -> None:
    """§1.6. The skill's own rule is "cheap-to-verify state is never asserted", and
    `tracking.*` is the field that breaks it most often: `branch` said `main` while
    the real branch was the feature one, was corrected, and went wrong the other way
    after the merge. `issues: []` stayed empty in three sets after the issues existed.

    Only `branch` is settled here, and only when there IS a repo to settle it against:
    a set read out of a vault has no checkout, and reporting "not a branch" for
    "there is no repo here" is a different claim than the one the check makes.
    `issues`/`pr`/`milestone` live on GitHub, and an auditor that makes network calls
    is a different kind of tool — they are listed as a human pass instead."""
    tracking = facts.get("tracking")
    if not isinstance(tracking, dict):
        return
    branch = tracking.get("branch")
    in_repo = subprocess.run(["git", "rev-parse", "--git-dir"], cwd=repo_root,
                             capture_output=True, text=True).returncode == 0
    if branch and in_repo:
        ok = subprocess.run(["git", "rev-parse", "--verify", "--quiet",
                             f"refs/heads/{branch}"],
                            cwd=repo_root, capture_output=True, text=True)
        if ok.returncode != 0:
            f.add(DRIFT, "tracking.branch",
                  f"`{branch}` is not a branch in this checkout",
                  "one command settles it (`git rev-parse --verify`), so asserting it "
                  "is the same defect as copying a test count",
                  "28 tracking vs reality")
    status = norm(facts.get("status"))
    if status in ("implementing", "shipped") and not (tracking.get("issues") or
                                                      tracking.get("pr")):
        f.add(DRIFT, "tracking",
              f"`status: {status}` with no `issues:` and no `pr:`",
              "the work exists somewhere trackable by now; an empty tracking block "
              "in a shipped set is a field nobody went back to fill",
              "28 tracking vs reality")


def check_provider_behavior(facts: dict, f: Findings) -> None:
    """§3.4. `how: provider-behavior` claims what a third party ACTUALLY does, and
    the only acceptable value is an observed response — a status code and a body.
    A claim about a file-type filter was corrected twice in opposite directions
    because both times it reasoned about the provider's configuration instead of
    executing the flow."""
    for path, node in walk(facts):
        if not (isinstance(node, dict) and norm(node.get("basis")) == "measured"):
            continue
        ev = node.get("evidence") or {}
        if norm(ev.get("how")) != "provider-behavior":
            continue
        value = str(ev.get("value") or "")
        if not re.search(r"\b[1-5]\d{2}\b", value):
            f.add(CONTRADICTION, pretty_path(facts, path) or "_facts.yml",
                  "`how: provider-behavior` whose `value` records no observed HTTP "
                  f"status: {value[:60]!r}",
                  "run the flow and paste the response — status code and body. A "
                  "configuration is what you asked for; behavior is what you get, and "
                  "reasoning about the first is how this claim got corrected twice in "
                  "opposite directions",
                  "29 provider behavior is observed")


def live_accepted_risks(facts: dict) -> list[tuple[str, str, str]]:
    """Deferrals with a deadline that has not arrived. Not findings — but not
    silence either: the audit names them and their expiry, which is the whole
    reason the field exists rather than a note in a log entry."""
    out = []
    for d in facts.get("defects") or []:
        if not isinstance(d, dict):
            continue
        state, detail = accepted_state(d)
        if state == "live":
            because = str((d.get("accepted") or {}).get("because", "")).strip()
            out.append((str(d.get("id", "?")), detail, because))
    return out


def check_placeholders(facts: dict, f: Findings) -> None:
    """Check 10."""
    if norm(facts.get("status")) in ("", "draft"):
        return
    for key in ("owners", "dates", "schedule"):
        node = facts.get(key)
        if not isinstance(node, dict):
            continue
        for sub, val in node.items():
            if str(val).strip() in ("—", "-", "TBD", "?", "xxx", "None", ""):
                f.add(DRIFT, f"{key}.{sub}", f"placeholder {val!r} in a non-draft set",
                      "resolve owners from `git shortlog -sne -- <paths>`, dates from "
                      "the user",
                      "10 placeholders")


def check_doc_size(in_scope: list[dict], f: Findings) -> None:
    """Check 17."""
    for d in in_scope:
        if not d["exists"]:
            continue
        n = sum(1 for _ in d["path"].open(encoding="utf-8", errors="ignore"))
        if n > 600:
            f.add(DRIFT, d["file"], f"{n} lines — split overdue (>600)",
                  "references/doc-pattern.md §Splitting an oversized doc",
                  "17 doc size")
        elif n > 500:
            f.add(POLISH, d["file"], f"{n} lines — approaching the split threshold",
                  "split now, on the next top-level phase boundary, before more "
                  "cross-refs are written against the current numbering",
                  "17 doc size")


def check_profile_and_log(facts: dict, spec_dir: Path, repo_root: Path,
                          f: Findings) -> None:
    """Checks 15 and 16, the parts a program can settle without git plumbing."""
    prof = facts.get("profile")
    if not prof:
        f.add(DRIFT, "_facts.yml", "no `profile:`",
              "every cmd in the set was then invented per feature, and check 1b has "
              "nothing to compare against",
              "15 profile coverage")
    elif not (repo_root / str(prof)).is_file() and not (spec_dir / str(prof)).is_file():
        f.add(CONTRADICTION, "_facts.yml", f"`profile: {prof}` does not resolve",
              "the set moved, or the profile came from another checkout",
              "15 profile coverage")
    if not (spec_dir / "_log.md").is_file():
        f.add(POLISH, "_log.md", "no handoff log",
              "fine for a set that never leaves this session; adding it later costs "
              "the history you already lost",
              "16 handoff log")


def check_log_stage(facts: dict, spec_dir: Path, f: Findings) -> None:
    """Check 16, staging half: a status change with no `Stage:` line recording it."""
    log = spec_dir / "_log.md"
    if not log.is_file():
        return
    status = norm(facts.get("status")) or "draft"
    if status == "draft":
        return
    stages = re.findall(r"^\*\*Stage:\*\*\s*(\S+)\s*(?:→|->)\s*(\S+)",
                        log.read_text(encoding="utf-8"), re.M)
    if not stages:
        f.add(DRIFT, "_log.md", f"`status: {status}` but the log records no `Stage:` "
              "transition",
              "a stage transition puts docs into audit scope and unlocks `implement`; "
              "unrecorded, it is indistinguishable from a typo in the registry",
              "16 handoff log")
    elif stages[-1][1].strip("`") != status:
        f.add(DRIFT, "_log.md",
              f"last recorded transition ends at `{stages[-1][1]}` but `status:` is "
              f"`{status}`",
              "append the entry that performed the change",
              "16 handoff log")


# --------------------------------------------------------------------------
# output
# --------------------------------------------------------------------------

HUMAN_PASS = [
    ("1", "data-vs-registry wording", "every shared datum's exact wording in each doc "
     "— normalization (quoting, escaped pipes) makes this a judgment call"),
    ("1b", "re-run `evidence.cmd`", "deliberately NOT automated: this script does not "
     "execute commands out of a registry. Re-run them yourself and diff against "
     "`evidence.value`"),
    ("3", "contract shape", "JSON blocks in prose vs `contracts.*`, field for field"),
    ("4", "cross-refs resolve", "mechanical sweeps over-report here; the protocol "
     "lists two exempt shapes. Verify each hit by eye"),
    ("6", "acceptance parity", "doc 02's Definition of Done vs `acceptance[]`"),
    ("7", "scope parity", "`changes[]` vs each doc's affected-components table"),
    ("13", "doc 02 executability", "resolved paths, named symbols, paste-ready code, "
     "`[MANUAL]` labels"),
    ("28", "`tracking.issues` / `pr` / `milestone` on GitHub", "deliberately NOT "
     "automated: an auditor that makes network calls is a different kind of tool. "
     "`gh issue view` / `gh pr view` and check the state matches `status:`"),
    ("3.5", "`decisions.*` cited_in", "when a decision changes, walk its `cited_in:` "
     "sections by hand — `sync` replaces values and a premise has no value to replace"),
]


def report(f: Findings, facts: dict, in_scope, deferred, prose, as_json: bool) -> int:
    order = {CONTRADICTION: 0, DRIFT: 1, POLISH: 2}
    f.items.sort(key=lambda x: (order[x["severity"]], x["check"], x["where"]))

    if as_json:
        print(json.dumps({"status": facts.get("status"), "findings": f.items,
                          "deferred_docs": [d["file"] for d in deferred]},
                         indent=2, ensure_ascii=False))
        return 1 if f.count(CONTRADICTION) else 0

    status = str(facts.get("status") or "draft")
    print(f"# audit — {facts.get('feature', '?')}  (status: {status})\n")
    scoped = ", ".join(d["file"] for d in in_scope if d["exists"]) or "none"
    print(f"docs in scope: {scoped}")
    if deferred:
        print("not due yet: " + ", ".join(
            f"{d['file']} (stage {d['stage']})" for d in deferred))
    print()

    if f.items:
        print("## Findings\n")
        for x in f.items:
            print(f"{x['where']}: {x['severity']}: {x['what']}. {x['fix']}.")
            print(f"    └ check {x['check']}")
        print()

    # Check 5, inverted: before docs 02/03 exist there is nothing to cover them
    # WITH, so the items are listed as the input `implement` has to satisfy.
    if not any(d["id"] in ("02", "03") and d["exists"] for d in in_scope):
        items = []
        for doc, text in prose.items():
            items += re.findall(r"^\s*[-*]\s*\[[ x]\]\s*(.+)$", text, re.M)
        if items:
            print("## Pending downstream coverage (check 5)\n")
            print("Doc 01 checklist items with no counterpart yet — this is the input "
                  "`implement` must cover, not a finding:\n")
            for i in items:
                print(f"  - {i.strip()}")
            print()

    risks = live_accepted_risks(facts)
    if risks:
        print("## Accepted risks, with their expiry\n")
        print("Recorded decisions to ship with a cause still asserted. Not findings "
              "— until the date passes, and then G1 refuses again:\n")
        for rid, detail, because in risks:
            print(f"  defects.{rid} — {detail}")
            if because:
                print(f"      {because}")
        print()

    print("## Requires a human pass\n")
    for num, name, why in HUMAN_PASS:
        print(f"  check {num:<3} {name} — {why}")
    print()

    c, d, p = f.count(CONTRADICTION), f.count(DRIFT), f.count(POLISH)
    verdict = (f"{c} contradictions, {d} drift, {p} polish" if f.items
               else "clean — every mechanized check passed")
    if deferred:
        verdict += f" · stage {status}: {len(deferred)} doc(s) not due yet"
    if risks:
        verdict += f" · {len(risks)} accepted risk(s) with a due date"
    print(verdict)
    return 1 if c else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("spec_dir")
    ap.add_argument("--repo-root", default=None,
                    help="anchor/file resolution root (default: git toplevel)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    spec_dir = Path(args.spec_dir).resolve()
    facts_path = spec_dir / "_facts.yml"
    if not facts_path.is_file():
        sys.exit(f"no _facts.yml in {spec_dir} — not a feature-spec set.")
    facts = load_facts(facts_path)
    repo_root = repo_root_for(spec_dir, args.repo_root)

    rank, in_scope, deferred = resolve_stage(facts, spec_dir)
    prose = {d["file"]: d["path"].read_text(encoding="utf-8")
             for d in in_scope if d["exists"]}
    if not prose:
        for path in sorted(spec_dir.glob("[0-9][0-9]*.md")):
            prose[path.name] = path.read_text(encoding="utf-8")

    f = Findings()
    check_top_level_keys(facts, f)
    check_docs_on_disk(in_scope, deferred, f)
    check_basis_gates(facts, f)
    check_declared_dependencies(facts, f)
    check_changes_vocabulary(facts, f)
    check_acceptance_state(facts, rank, f)
    check_dead_dependency_cascade(facts, f)
    check_file_existence(facts, repo_root, rank, f)
    check_anchors(facts, prose, repo_root, f)
    check_orphan_and_dangling_ids(facts, prose, f)
    check_phase_numbering(prose, f)
    check_evidence_cmd_runnable(facts, f)
    check_placeholders(facts, f)
    check_tracking(facts, repo_root, f)
    check_provider_behavior(facts, f)
    check_doc_size(in_scope, f)
    check_profile_and_log(facts, spec_dir, repo_root, f)
    check_log_stage(facts, spec_dir, f)

    return report(f, facts, in_scope, deferred, prose, args.json)


if __name__ == "__main__":
    raise SystemExit(main())
