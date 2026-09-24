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
                             [--as-status STAGE] [--today YYYY-MM-DD]

It never executes `evidence.cmd` (protocol check 1b). A registry is a data file that
travels between repos and agents; running commands out of it because it claims they
are safe is the one thing an auditor must not do. Re-running evidence is a human step
and is listed as one.

The shared registry core is imported from render.py so the two cannot drift: a check
implemented twice is the exact defect this skill exists to prevent.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from render import (accepted_state, collect_claims, confined, norm,
                        status_gate, walk, yaml)
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


def profile_path(prof: str, spec_dir: Path, repo_root: Path) -> Path | None:
    """Where `profile:` is allowed to resolve, in the two shapes that are real.

    `../_profile.yml` is the documented layout — one profile in `docs/features/`
    governing every feature folder under it — so the spec dir's parent is a base in
    its own right, not an escape. Anything above those two is."""
    for base in (repo_root, spec_dir.parent):
        target = confined(base, prof)
        if target is not None and target.is_file():
            return target
    return None


class Findings:
    def __init__(self) -> None:
        self.items: list[dict] = []

    def add(self, sev: str, where: str, what: str, fix: str, check: str) -> None:
        self.items.append({"severity": sev, "where": where, "what": what,
                           "fix": fix, "check": check})

    def count(self, sev: str) -> int:
        return sum(1 for f in self.items if f["severity"] == sev)


class Candidates:
    """A candidate is NOT a finding, and the difference is the whole design.

    A finding carries a severity because the script knows what it is: an anchor
    either resolves or it does not. A candidate is a mechanical hit on a check whose
    verdict needs a document read — a JSON fence whose keys do not match any
    contract may be an orphan, may be a downstream-injected field the doc explains
    in a note two paragraphs up, or may be nothing. The script cannot tell, and
    inventing a severity so it fits in `## Findings` would make the verdict line
    count things nobody has judged yet. A report whose count lies is worse than one
    that reports less.

    So candidates are emitted UNDER the check they belong to inside `## Requires a
    human pass`, never in `## Findings`. The reader sees the check, the caveat the
    protocol attaches to it — check 4's is literally "mechanical sweeps over-report
    here: verify each hit by eye" — and the list that caveat governs, in one place
    and in that order. A separate top-level section would split the warning from the
    thing it warns about, and the whole point of the pattern is that the human reads
    a short list instead of three whole documents.

    The saving is real either way: the LLM verifies ~10 lines instead of re-reading
    the set. It only survives if the list stays short, which is why every generator
    below is tested against the false positive it must reject before the case it
    must catch.
    """

    def __init__(self) -> None:
        self.by_check: dict[str, list[dict]] = {}

    def add(self, check: str, where: str, what: str) -> None:
        self.by_check.setdefault(check, []).append({"where": where, "what": what})

    def total(self) -> int:
        return sum(len(v) for v in self.by_check.values())


# --------------------------------------------------------------------------
# loading
# --------------------------------------------------------------------------

def repo_root_for(spec_dir: Path, override: str | None) -> tuple[Path, bool]:
    """Returns the root and whether it is a REAL one. On the fallback the root is
    the spec dir itself, which is a workable base for path resolution but says
    nothing about the checkout's identity — check 15 must not read a basename off
    it and call the profile foreign."""
    if override:
        return Path(override).resolve(), True
    try:
        out = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                             cwd=spec_dir, capture_output=True, text=True, check=True)
        return Path(out.stdout.strip()), True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return spec_dir, False


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
# prose text helpers — shared by the candidate generators (checks 3, 4, 8, 13)
# --------------------------------------------------------------------------

FENCE_OPEN_RE = re.compile(r"^\s*```+\s*([A-Za-z0-9_+.-]*)\s*$")
FENCE_CLOSE_RE = re.compile(r"^\s*```+\s*$")


def iter_fences(text: str):
    """-> (opening lineno, lowercased language, body). Line numbers are 1-based and
    point at the fence marker, which is what a reader scrolls to."""
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        m = FENCE_OPEN_RE.match(lines[i])
        if not m:
            i += 1
            continue
        j = i + 1
        while j < len(lines) and not FENCE_CLOSE_RE.match(lines[j]):
            j += 1
        yield i + 1, m.group(1).lower(), "\n".join(lines[i + 1:j])
        i = j + 1


def blank_fences(text: str) -> str:
    """Fenced blocks replaced by empty lines, LINE COUNT PRESERVED so every hit
    still reports the line a reader can jump to."""
    out, inside = [], False
    for line in text.splitlines():
        if inside:
            out.append("")
            if FENCE_CLOSE_RE.match(line):
                inside = False
            continue
        if FENCE_OPEN_RE.match(line):
            inside = True
            out.append("")
            continue
        out.append(line)
    return "\n".join(out)


def blank_inline_code(text: str) -> str:
    """Inline spans blanked, length preserved. This is the guard the protocol asks
    for by name on check 4: a section number quoted AS TEXT — a defect being
    described, an example — lives in backticks, and a sweep that reads it as a
    navigation target reports the fix as the bug."""
    return re.sub(r"`[^`\n]*`", lambda m: " " * len(m.group(0)), text)


def blank_link_targets(text: str) -> str:
    """`](...)` targets blanked. A documentation URL is written as a markdown link
    with text; an endpoint the system actually calls is written bare or in
    backticks. That is the cheapest discriminator there is between the two, and
    without it every `[the fetch docs](https://developer.mozilla.org/.../API/...)`
    becomes a check 8 candidate."""
    return re.sub(r"\]\([^)\n]*\)", lambda m: " " * len(m.group(0)), text)


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


# Set machinery: never a `docs[]` member, and never a sibling either.
SET_MACHINERY_SUFFIXES = (".yml", ".yaml", ".html", ".json")


def registry_declared_paths(facts: dict, spec_dir: Path, repo_root: Path) -> set[Path]:
    """Every path the registry names anywhere, resolved both ways. A file the
    registry declares is inside the source-of-truth net whichever list holds it;
    check 9 is about the ones NO list names."""
    out = set()
    for key in ("docs", "related_docs", "changes"):
        for e in facts.get(key) or []:
            if not isinstance(e, dict):
                continue
            raw = e.get("file") or e.get("path")
            if not raw:
                continue
            for base in (spec_dir, repo_root):
                out.add((base / str(raw)).resolve())
    return out


def check_sibling_docs(facts: dict, spec_dir: Path, repo_root: Path,
                       f: Findings) -> None:
    """Check 9, the direction that did not exist: disk -> `docs[]`.

    `check_docs_on_disk` walks `docs[]` and asks whether each entry is on disk. The
    inverse — a file on this feature's theme that no `docs[]` entry names — was left
    to a human who has to think of globbing for it. Nobody does, because nothing in
    the report suggests the file might be there.

    An unregistered sibling is outside the source-of-truth net: `sync` does not
    propagate into it, no check compares it against the registry, and it drifts in
    silence. Real case: a `-actionables.md` said 17 where the set said 16.

    Two globs, both from the protocol: every `.md` in the spec dir, and every
    adjacent `*<slug>*.md` beside it. There is no judgment here — a file is named
    in the registry or it is not."""
    declared = registry_declared_paths(facts, spec_dir, repo_root)
    slugs = {spec_dir.name}
    feature = str(facts.get("feature") or "").strip()
    if feature:
        slugs.add(feature)

    found: set[Path] = {p.resolve() for p in spec_dir.glob("*.md")}
    for slug in slugs:
        found |= {p.resolve() for p in spec_dir.parent.glob(f"*{slug}*")
                  if p.is_file() and p.suffix == ".md"}

    for path in sorted(found):
        if path in declared:
            continue
        # `_facts.yml`, `_log.md`, `_profile.yml`: the set's own machinery, which is
        # never a docs[] member. Underscore is the convention that marks them.
        if path.name.startswith("_") or path.suffix in SET_MACHINERY_SUFFIXES:
            continue
        try:
            where = str(path.relative_to(spec_dir))
        except ValueError:
            where = str(path.relative_to(spec_dir.parent))
        f.add(DRIFT, where,
              "on this feature's theme but named by no `_facts.yml docs[]` entry",
              "an unregistered sibling drifts in silence — nothing compares it "
              "against the registry and `sync` never reaches it. Integrate it into "
              "the set, or register it with `role: legacy`",
              "9 disk -> docs[]")


# Hosts that exist to be an example. A sweep that reports them teaches the reader
# to skim the candidate list, which costs more than the check saves.
EXAMPLE_HOST_RE = re.compile(
    r"(?:^|//|@)(?:[\w-]+\.)*(?:example\.(?:com|org|net)|example|localhost"
    r"|127\.0\.0\.1|0\.0\.0\.0|foo\.bar|tu-dominio|your-domain|<[^>]+>)\b", re.I)

# Path shapes that read as an API surface rather than a page.
API_PATH_RE = re.compile(r"/(?:api|webhook|webhooks|functions|rest|graphql|rpc"
                         r"|v\d+)(?:[/?#]|$)", re.I)

# Provider-hosted function hosts: the URL shape check 8 was written for.
FUNCTION_HOST_RE = re.compile(
    r"\.(?:supabase\.co|vercel\.app|workers\.dev|netlify\.app|run\.app|deno\.dev"
    r"|cloudfunctions\.net|azurewebsites\.net|herokuapp\.com|fly\.dev|ngrok\.io)\b",
    re.I)

URL_RE = re.compile(
    r"[a-z][a-z0-9+.-]*://[^\s`\"'<>()\[\],]+"           # any scheme, incl. deep links
    r"|(?<![\w.~/-])/(?:api|webhook|webhooks|functions|rest|graphql|rpc|v\d+)"
    r"[\w/{}:.~-]*", re.I)

# `file://` is a local path and `chrome://` is a browser page; neither is an
# interface this set owns.
NON_ENDPOINT_SCHEMES = ("file", "chrome", "about", "data", "javascript")

JSON_KEY_RE = re.compile(r'"([A-Za-z_][\w.-]*)"\s*:')
# A fence the prose introduces BY FILENAME is that file's contents, not an
# interface two sides must agree on. Doc 02 is paste-ready by design, so a set that
# creates a project ships `package.json`, three `tsconfig*.json` and its i18n
# bundles as fences — all of them shaped exactly like a payload and none of them
# addressable by anybody.
#
# Measured: 15 of 19 real check-8 candidates were this — `**`package.json`**
# (raiz):`, `**Archivo:** `mcp-server/tsconfig.json` (nuevo)`, `**Código —
# `es.json`:**`, `` `assets/i18n/en.json`, misma clave: ``. The same ~4-in-5 noise
# rate as check 13's bare `dashboard`, and the same fix: read what the sentence
# above it says the block IS.
JSON_FILE_INTRO_RE = re.compile(r"[\w./@-]+\.json\b")
# Two shapes the filename rule cannot reach, both found by running it.
#
# A manifest the prose never names: `**Ancla:** archivo nuevo` / `**Código:**` and
# then a package.json, identifiable only by what is IN it. These key sets belong to
# well-known files and to nothing a spec set would ever call an interface.
MANIFEST_SIGNATURE_KEYS = ({"compilerOptions"}, {"devDependencies"},
                           {"peerDependencies"}, {"mcpServers"}, {"workspaces"},
                           {"name", "version", "scripts"})
# A continuation: the second and later fences of one file, shown as key fragments
# (`"greeting": "Hola"`) under prose like `y en "labels":`. A fragment is
# not a payload — nothing can be diffed against it field-for-field, which is the
# only thing check 3 and check 8 do with a fence. The protocol already grants this
# to the human ("a fence can legitimately show a fragment"); this makes it
# mechanical, so the human never sees the four that come after the first.
JSON_DOCUMENT_START_RE = re.compile(r"^\s*[{\[]")
HTTP_REQUEST_LINE_RE = re.compile(
    r"^\s*(?:GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\s+(\S+)", re.M)


# Keys that describe a contract instead of being fields OF it. They are the
# registry's own vocabulary and can never appear in a payload, so folding them into
# the field set makes a correct fence look wrong.
#
# Motivating case, and the reason this is a constant and not a judgment call: a
# `{ fields: [a, b, c], note: "..." }` entry against a prose fence of exactly
# `{a, b, c}` — a perfect match — was reported as `missing {fields, note}`. One
# scalar `note:` sibling was enough, because the shape test below asks whether
# EVERY value is a container. The skill tells authors to write `note:` siblings
# everywhere, so the convention and the check were in direct contradiction.
#
# The name alone does not settle it, and a first attempt that assumed it did made
# the check WORSE: a plain descriptive word can also be a real column of one
# contract's payload and metadata beside another's `fields:`. Stripping by name
# everywhere turned nine false positives into thirteen different ones, reported
# as an extra field against documents that were right.
#
# What settles it is the LEVEL. Descriptive keys sit at the entry, as siblings of a
# payload container; inside a payload every key is a field. So the strip happens at
# the entry and nowhere below it — and only when the entry actually declares a
# payload container, since a flat `{id, description}` entry IS the payload and has
# no metadata level to strip.
CONTRACT_META = {"note", "notes", "description", "desc", "example", "examples",
                 "source", "owner", "owned_by", "cited_in", "auth", "basis",
                 "evidence"}
PAYLOAD_KEYS = {"fields", "columns", "request_body", "response_ok", "response_err",
                "request", "response", "payload", "body", "schema", "rows"}


def strip_contract_meta(node):
    """Entry-level descriptive keys of one `contracts.*` entry. Never called below
    the entry: one level down, the same word is a field name."""
    if not isinstance(node, dict):
        return node
    if not {str(k).strip().lower() for k in node} & PAYLOAD_KEYS:
        return node        # a flat payload: every key is a field
    return {k: v for k, v in node.items()
            if str(k).strip().lower() not in CONTRACT_META}


def contract_field_names(node) -> set[str]:
    """Every field NAME reachable under one `contracts.*` entry.

    Both template shapes name fields differently: `request_body: [field_a, field_b]`
    names them as list values, `response_ok: { field: type }` names them as keys. A
    scalar sitting under a dict key is the field's TYPE, never its name — folding
    those in would grow the name set until every fence matched something and the
    check reported nothing. Entry-level metadata is stripped by the caller, never
    here: at this depth the node may already be a payload, where `description` is a
    field and not a description."""
    names: set[str] = set()
    if isinstance(node, dict):
        for key, val in node.items():
            names.add(str(key))
            if isinstance(val, (dict, list)):
                names |= contract_field_names(val)
    elif isinstance(node, list):
        for val in node:
            if isinstance(val, str):
                names.add(val.strip())
            elif isinstance(val, (dict, list)):
                names |= contract_field_names(val)
    return names


def registry_container_entries(facts: dict, container: str) -> dict[str, object]:
    node = facts.get(container)
    if isinstance(node, dict):
        return {str(k): v for k, v in node.items()}
    if isinstance(node, list):
        return {str(e["id"]): e for e in node
                if isinstance(e, dict) and e.get("id")}
    return {}


def contract_keysets(facts: dict) -> dict[str, set[str]]:
    return {name: contract_field_names(strip_contract_meta(body))
            for name, body in registry_container_entries(facts, "contracts").items()}


def endpoint_strings(facts: dict) -> set[str]:
    """Every string an `endpoints.*` entry offers to be recognised by: its key, and
    every scalar under it. `endpoints: { external_get: /webhook/chat-result }` is
    the template's own example, so the value is often the path itself."""
    out: set[str] = set()
    for name, body in registry_container_entries(facts, "endpoints").items():
        out.add(name)
        for _, sub in walk(body) if isinstance(body, (dict, list)) else []:
            if isinstance(sub, str) and sub.strip():
                out.add(sub.strip())
        if isinstance(body, str) and body.strip():
            out.add(body.strip())
    return {v for v in out if len(v) >= 3}


def top_level_json_keys(body: str) -> set[str]:
    """Keys at brace depth 1 of a fenced block.

    `json.loads` is not usable here: spec fences carry `…`, trailing commas and `//`
    notes, and a block that fails to parse is not a block with no fields. Brackets do
    not count toward depth, so `[{...}]` still yields the object's own keys, and a
    nested `{"data": {"id": 1}}` yields `data` alone — a contract that declares the
    field but not its interior would otherwise report `id` as an extra field on every
    payload that has one."""
    keys: set[str] = set()
    depth, i, n = 0, 0, len(body)
    while i < n:
        ch = body[i]
        if ch == '"':
            j = i + 1
            while j < n and body[j] != '"':
                j += 2 if body[j] == "\\" else 1
            token = body[i + 1:j]
            k = j + 1
            while k < n and body[k] in " \t\r\n":
                k += 1
            if depth == 1 and k < n and body[k] == ":":
                keys.add(token)
            i = j + 1
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        i += 1
    return keys


def contract_blocks(facts: dict) -> list[tuple[str, set[str]]]:
    """-> [(`contracts.chat_request.request_body`, {field, ...}), ...].

    A contract entry holds several payloads — request body, ok response, error
    response — and a fence shows ONE of them. Comparing against the entry's flattened
    field set would report every response field as missing from every request fence,
    which is a wall of noise on a correct document. So each payload is indexed
    separately and a fence is diffed against the one it actually resembles.

    A dict whose values are all containers is a set of payloads; anything else is a
    payload whose keys are field names. Both are the template's own shapes.

    Descriptive keys are stripped BEFORE that test, not only from the field set. A
    single `note:` next to `fields:` makes "every value is a container" false, so
    the entry stops being read as a set of payloads and collapses into one — which
    is how `{fields: [...], note: "..."}` came to be diffed as a payload with the
    literal fields `fields` and `note`."""
    out: list[tuple[str, set[str]]] = []

    def visit(label: str, node) -> None:
        if isinstance(node, dict) and node and all(
                isinstance(v, (dict, list)) for v in node.values()):
            for key, val in node.items():
                visit(f"{label}.{key}", val)
            return
        fields = contract_field_names(node)
        if fields:
            out.append((label, fields))

    for name, body in registry_container_entries(facts, "contracts").items():
        visit(f"contracts.{name}", strip_contract_meta(body))
    return out


# Check 13's three regex-able sub-bullets. The other five stay human, and the
# enumeration names the reason: a step that needs "judgment" cannot be detected by
# a pattern that looks for the word.
UNRESOLVED_PATH_RE = re.compile(
    r"\bpath/to/|\bruta/a/|(?<![\w/])\.\.\./[\w.-]|…/[\w.-]|"
    r"\((?:o|or) el (?:componente|archivo|módulo|hook|servicio) correspondiente\)|"
    r"\((?:or the )?(?:corresponding|appropriate) (?:component|file|module)\)", re.I)
VAGUE_ENUM_RE = re.compile(
    r"\betc\.|\bet ?cétera\b|\by similares\b|\by (?:los )?demás\b|"
    r"\banálogo a lo anterior\b|\bídem para\b|\bidem para\b|\band so on\b|"
    r"\bsimilar to the above\b", re.I)
# A step that reaches outside the checkout. The label is what tells the builder to
# stop rather than invent, and its absence is the finding.
EXTERNAL_STEP_RE = re.compile(
    r"\bdashboard\b|\bpanel de (?:control|administraci[oó]n)\b|\bDNS\b|"
    r"\bsecreto\b|\bsecret\b|\bAPI key\b|\bclave de API\b|\bconsola de \w+\b|"
    r"\bregistrar el dominio\b|\bcertificado (?:SSL|TLS)\b", re.I)
EXTERNAL_LABEL_RE = re.compile(r"\[MANUAL\]|\[OWNER EXTERNO\]|\[EXTERNAL OWNER\]")
# What separates "the Supabase dashboard" from "the Dashboard", which in most of
# these apps is a screen the app itself renders. Measured over 25 real candidates:
# 19 fired on the word `dashboard` and only 5 of the 25 named a provider — the rest
# were in-app navigation ("Navegar a la semana siguiente en el Dashboard"), a
# deliberately FAKE secret in a test ("Pegar un secret falso"), and blocking DNS
# inside a network test. A keyword cannot tell a third party's console from a route
# in this codebase; a provider name next to it can.
EXTERNAL_PROVIDER_RE = re.compile(
    r"\b(?:supabase|resend|anthropic|openai|vercel|cloudflare|sentry|stripe|github|"
    r"gitlab|firebase|aws|amazon|azure|gcp|google|expo|netlify|heroku|twilio|auth0|"
    r"clerk|posthog|datadog|mailgun|sendgrid|namecheap|godaddy|route ?53)\b|"
    r"\bconsola de \w+|\bconsole\b|\bpanel de \w+|https?://", re.I)
# "in a step". A sentence of narrative that happens to end in "etc." is not an
# instruction anybody executes, and reporting it is how a candidate list stops
# being read.
STEP_LINE_RE = re.compile(r"^\s*(?:[-*+]\s|\d+[.)]\s|\|)")


def check_doc02_executability(facts: dict, prose: dict[str, str],
                              in_scope: list[dict], c: Candidates) -> None:
    """Check 13, the three of its eight sub-bullets a regex can reach.

    The other five stay entirely human and the protocol's own enumeration says why:
    a symbol named but never defined, an edit with no anchor, a B.1 row worded as
    parity or negation, a persisted store with no schema, and "a step that needs a
    dashboard, DNS, a secret or **judgment**". The last one names judgment outright,
    and the four before it are each a question about whether something ELSEWHERE
    supplies what the step assumes — which is the thing a line-oriented sweep is
    structurally unable to ask.

    What is left is three shapes and their line numbers:

      unresolved paths   `path/to/`, `…/algo`, `(o el componente correspondiente)`
      vague enumeration  `etc.`, `y similares`, `análogo a lo anterior`
      external step      dashboard / DNS / secret with no `[MANUAL]` label

    Scoped to doc 02, which is what the check is about and what stage-gates it.

    The path sweep reads fenced blocks too — a `path/to/` inside a paste-ready
    snippet is the defect at its worst, since that is the text the builder copies.
    The other two do not: `etc.` in a code comment is not a step, and a `secret`
    identifier in a snippet is a variable name, not an instruction to go get one."""
    for entry in in_scope:
        if not entry["id"].startswith("02") or entry["file"] not in prose:
            continue
        doc = entry["file"]
        text = prose[doc]
        unqualified: list[tuple[int, str]] = []
        for lineno, line in enumerate(text.splitlines(), 1):
            hit = UNRESOLVED_PATH_RE.search(line)
            if hit:
                c.add("13", f"{doc}:{lineno}",
                      f"unresolved path: {hit.group(0).strip()!r}")
        for lineno, line in enumerate(blank_fences(text).splitlines(), 1):
            if not STEP_LINE_RE.match(line):
                continue
            hit = VAGUE_ENUM_RE.search(line)
            if hit:
                c.add("13", f"{doc}:{lineno}",
                      f"a step that enumerates by {hit.group(0).strip()!r} — the "
                      "builder has to guess the rest")
            hit = EXTERNAL_STEP_RE.search(line)
            if hit and not EXTERNAL_LABEL_RE.search(line):
                if EXTERNAL_PROVIDER_RE.search(line):
                    c.add("13", f"{doc}:{lineno}",
                          f"step reaches outside the checkout "
                          f"({hit.group(0).strip()!r}) with no `[MANUAL]` / "
                          "`[OWNER EXTERNO]` label")
                else:
                    unqualified.append((lineno, hit.group(0).strip().lower()))

        # Collapsed, not dropped. The word alone is too weak to name a line with —
        # in this corpus it was wrong four times out of five — but staying silent
        # about it would rebuild the failure `HUMAN_PASS` exists to close, one level
        # down. So the count is stated and the reader decides whether to grep.
        if unqualified:
            words = ", ".join(sorted({w for _, w in unqualified}))
            c.add("13", doc,
                  f"{len(unqualified)} step(s) name {words} with no provider and no "
                  "`[MANUAL]` label — listed as a count because the word alone does "
                  "not distinguish a third party's console from a screen this app "
                  f"renders (lines {', '.join(str(n) for n, _ in unqualified)})")


DOC_ID_SPAN_RE = re.compile(r"^0\d[a-z]?$")
SECTION_REF_RE = re.compile(r"§\s*(\d+(?:\.\d+)*[a-z]?)")
# `§1–§5` is ONE span, not two navigation targets. A reader following it opens a
# range; a sweep that reads it as two refs reports its far end as dangling.
#
# Real case: `> Las referencias a §1–§5 apuntan a `01`, las de §6–§8 a `01b`` — a
# LEGEND declaring how to read the references in the rest of the document. It
# produced four candidates and survived 48 review rounds untouched, which is as
# close to a human verdict of "not a finding" as this corpus offers.
SECTION_RANGE_RE = re.compile(
    r"§\s*\d+(?:\.\d+)*[a-z]?\s*[–—−-]\s*§?\s*\d+(?:\.\d+)*[a-z]?")
# Above this many refs on one line, the line is enumerating rather than pointing.
# Same idiom, and the same reason, as checks 26 and 30: reporting fifteen hits from
# one sentence buries every other finding in the set. Real case: a single changelog
# row (`CHANGELOG.md:14`) produced 11 of that set's 21 candidates, and the protocol
# already names its shape exempt — "a changelog clause that names the doc once and
# then enumerates what changed inside it".
REF_ENUMERATION_MIN = 3
SECTION_HEADING_RE = re.compile(r"^#{1,6}\s*(?:§\s*)?(\d+(?:\.\d+)*[a-z]?)\b", re.M)
DOC_MENTION_RE = re.compile(r"\b(?:doc|documento)\s+(0\d[a-z]?)\b", re.I)
DOC_ID_TOKEN_RE = re.compile(r"(?<![\w.])(0\d[a-z]?)(?![\w.])")
# `§3.5 de 02b` — legible to a reader, invisible to a naive sweep. The protocol
# prefers the prefix first and says so; reading it here is what keeps the
# preference from turning into a wall of false candidates.
TRAILING_DOC_RE = re.compile(r"^\s*(?:de|of|en|in|del)\s+(0\d[a-z]?)\b", re.I)


def blank_inline_code_for_refs(text: str) -> str:
    """Inline spans blanked EXCEPT a bare doc id.

    This is check 4's whole false-positive class (a): a section number quoted as
    text — a defect being described (`` fixed the cross-ref `§3.6`→`§3.5` ``) or an
    example — is not a navigation target, and a sweep that reads it as one reports
    the fix as the bug. But the protocol's own notation writes a doc prefix in
    backticks too (`` `02` §1.5 ``), so blanking every span would strip the prefix
    and silently reread every boundary-crossing ref as local — which turns the worst
    finding this check has (a ref that resolves in the WRONG file) into silence."""
    def sub(m: re.Match) -> str:
        body = m.group(0)[1:-1].strip()
        return f" {body} " if DOC_ID_SPAN_RE.match(body) else " " * len(m.group(0))
    return re.sub(r"`[^`\n]*`", sub, text)


def section_numbers(text: str) -> set[str]:
    return set(SECTION_HEADING_RE.findall(text))


def check_cross_refs(facts: dict, prose: dict[str, str], in_scope: list[dict],
                     c: Candidates) -> None:
    """Check 4, as a candidate generator — and the one where the protocol's warning
    is loudest: *"Mechanical sweeps over-report here: verify each hit by eye."*
    Candidates, never findings, and every guard below exists to keep the list short
    enough that anyone still reads it.

    Two false-positive classes are named in the protocol. (a) — a section number
    quoted as text — IS mechanizable and is stripped here along with fenced blocks.
    (b) — a changelog clause that names a doc once and then enumerates what changed
    inside it (`` `02` gained §0.3b, §1.1, §2.5 ``) — is **not**: it is narrative
    about one document, not five navigation targets, and telling the two apart means
    reading the sentence. So no attempt is made to filter it; a reader who sees the
    clause dismisses the whole group in one glance, which is cheaper than a rule
    that guesses wrong in both directions.

    Prefix binding follows the protocol exactly: a prefix does NOT distribute across
    a list, so a doc id binds only to the `§` it immediately precedes (or follows,
    in the `§3.5 de 02b` shape). Every other ref on that line is local to its own
    file — which is what makes the split-doc case detectable at all."""
    by_id = {d["id"]: d for d in in_scope}
    declared = {str(e.get("id")) for e in facts.get("docs") or []
                if isinstance(e, dict) and e.get("id")}
    sections = {d["id"]: section_numbers(prose[d["file"]])
                for d in in_scope if d["file"] in prose}
    file_to_id = {d["file"]: d["id"] for d in in_scope}

    for doc, text in prose.items():
        local_id = file_to_id.get(doc)
        swept = blank_inline_code_for_refs(blank_fences(text))
        for lineno, line in enumerate(swept.splitlines(), 1):
            for target in set(DOC_MENTION_RE.findall(line)):
                if target not in declared:
                    c.add("4", f"{doc}:{lineno}",
                          f"names doc `{target}`, which `_facts.yml docs[]` does "
                          f"not list")

            ids = [(m.start(), m.end(), m.group(1))
                   for m in DOC_ID_TOKEN_RE.finditer(line)]
            # Everything but the first member of each `§N–§M` span: one range is
            # one reference, and its far end is not a target anybody navigates to.
            spanned: set[int] = set()
            for rng in SECTION_RANGE_RE.finditer(line):
                inner = [mm.start() for mm in
                         SECTION_REF_RE.finditer(line, rng.start(), rng.end())]
                spanned.update(inner[1:])
            line_cands: list[str] = []
            for m in SECTION_REF_RE.finditer(line):
                if m.start() in spanned:
                    continue
                num = m.group(1)
                prefix = next((tok for start, end, tok in ids
                               if end <= m.start()
                               and not line[end:m.start()].strip()), None)
                if prefix is None:
                    after = TRAILING_DOC_RE.match(line[m.end():])
                    prefix = after.group(1) if after else None
                target = prefix or local_id
                if target is None:
                    continue
                if target not in declared:
                    line_cands.append(
                        f"`{target}` §{num} — `docs[]` lists no doc `{target}`")
                    continue
                if target not in sections:
                    continue        # the doc is declared but not on disk (check 9)
                if num in sections[target]:
                    continue
                elsewhere = sorted(k for k, v in sections.items()
                                   if k != target and num in v)
                if elsewhere and prefix is None:
                    # The shape the protocol calls worse than dangling: it reads as
                    # valid and sends the executor to the wrong file.
                    line_cands.append(
                        f"§{num} is unqualified, so it reads as local to "
                        f"`{target}`, where no such section exists — it resolves "
                        f"in {', '.join('`%s`' % e for e in elsewhere)} instead")
                else:
                    line_cands.append(
                        f"§{num} resolves to no heading in `{target}`"
                        + (" (its own file)" if prefix is None else ""))

            # One line, one candidate, once it is enumerating rather than pointing.
            # The refs are still named — the reader needs them to judge the clause —
            # but they arrive as one item to dismiss instead of eleven to read.
            if len(line_cands) >= REF_ENUMERATION_MIN:
                refs = ", ".join(f"§{m.group(1)}"
                                 for m in SECTION_REF_RE.finditer(line)
                                 if m.start() not in spanned)
                c.add("4", f"{doc}:{lineno}",
                      f"{len(line_cands)} unresolved section refs on one line "
                      f"({refs}) — collapsed: a line naming this many is enumerating "
                      "what changed inside a document, not pointing at it. Dismiss "
                      "the clause or read the individual refs in place")
            else:
                for what in line_cands:
                    c.add("4", f"{doc}:{lineno}", what)


def check_contract_shape(facts: dict, prose: dict[str, str], c: Candidates) -> None:
    """Check 3, as a candidate generator.

    Comparing a fence's key set against `contracts.*` is arithmetic. What is NOT
    mechanizable is the documented exception: a field the sender injects downstream,
    outside the client body, is legitimate **if a doc note explains it** — and the
    script cannot read the note. So the diff is a candidate and the note is the
    human's to find.

    The partition with check 8 is exact and neither check reports the other's cases:
    a fence sharing no field with any payload has no contract to be compared against
    and belongs to check 8 (prose-orphan); a fence that shares fields but not all of
    them belongs here; a fence that matches one payload exactly is silent in both. A
    fence the prose cites by contract id is judged here even when it shares nothing —
    it was ATTRIBUTED to that contract, which is a stronger claim than resembling it.
    """
    blocks = contract_blocks(facts)
    if not blocks:
        return
    known = set(registry_container_entries(facts, "contracts"))
    for doc, text in prose.items():
        lines = text.splitlines()
        for lineno, lang, body in iter_fences(text):
            if lang != "json":
                continue
            keys = top_level_json_keys(body)
            if not keys:
                continue
            context = "\n".join(lines[max(0, lineno - 9):lineno])
            cited = set(re.findall(r"contracts\.([A-Za-z0-9_]+)", context)) & known
            pool = ([b for b in blocks if b[0].split(".")[1] in cited]
                    if cited else blocks)
            label, fields = max(
                pool, key=lambda b: (len(keys & b[1]), -len(keys ^ b[1])))
            if not cited and not keys & fields:
                continue        # nothing to compare against — check 8's territory
            extra, missing = sorted(keys - fields), sorted(fields - keys)
            if not extra and not missing:
                continue
            detail = ", ".join(
                p for p in ("extra {%s}" % ", ".join(extra) if extra else "",
                            "missing {%s}" % ", ".join(missing) if missing else "")
                if p)
            c.add("3", f"{doc}:{lineno}", f"```json vs `{label}`: {detail}")


def check_prose_orphans(facts: dict, prose: dict[str, str], c: Candidates) -> None:
    """Check 8, as a candidate generator.

    The protocol says it plainly: "The mechanical audit is blind to contracts that
    live only in prose; this check is what surfaces them instead of relying on a
    human catching it by eye." It is also the check nobody runs, because catching it
    by eye means re-reading every document looking for something that is defined by
    NOT being in the registry — the one thing you cannot grep for directly.

    So the script greps for the inverse and hands over the short list. Two sweeps:

      fences  — every ```json / ```http block whose keys match no `contracts.*`
                entry and whose surrounding lines cite no contract by id.
      URLs    — every API-shaped URL, provider-function host, bare `/webhook/...`
                path or non-http deep-link URI with no `endpoints.*` home.

    Neither is a finding. A fence can legitimately show a fragment, an error body,
    or a third party's payload this set only reads; a URL can be a provider's
    documented callback that belongs in nobody's registry. Judging that needs the
    paragraph around it, so the script narrows and the human decides.

    Four false-positive classes are designed out, because a sweep that over-reports
    costs the reader more tokens than the check saves: example hosts, markdown link
    targets (a documentation link is written `[text](url)`; an endpoint this system
    calls is written bare or in backticks), fences in any other language, and URLs
    inside fenced blocks — the protocol scopes this sweep to PROSE, and a `curl`
    line in a bash fence is the command, not the interface."""
    keysets = contract_keysets(facts)
    all_contract_names = set(keysets)
    endpoints = endpoint_strings(facts)

    for doc, text in prose.items():
        lines = text.splitlines()
        file_fences: list[tuple[int, str]] = []

        for lineno, lang, body in iter_fences(text):
            if lang not in ("json", "http"):
                continue
            # A fence the prose attributes by id is homed whatever its keys say;
            # whether the fields still MATCH is check 3's question, not this one.
            context = "\n".join(lines[max(0, lineno - 9):lineno])
            cited = {n for n in re.findall(r"contracts\.([A-Za-z0-9_]+)", context)}
            if cited & all_contract_names or re.search(r"contracts\.\*", context):
                continue

            if lang == "http":
                target = HTTP_REQUEST_LINE_RE.search(body)
                url = target.group(1) if target else ""
                if url and any(e in url or url in e for e in endpoints):
                    continue
                if re.search(r"endpoints\.[A-Za-z0-9_]+", context):
                    continue
                c.add("8", f"{doc}:{lineno}",
                      "```http fence with no `endpoints.*` home"
                      + (f" ({url})" if url else ""))
                continue

            keys = set(JSON_KEY_RE.findall(body))
            if not keys:
                continue        # a bare array or scalar names no fields to compare
            if any(keys & names for names in keysets.values()):
                continue
            # The sentence that introduces the block says what it is. Only the
            # nearest lines count: a `.json` path mentioned a paragraph earlier is
            # about something else, and widening the window is how an exemption
            # starts swallowing the findings it was meant to sit beside.
            intro_lines = [l for l in lines[max(0, lineno - 7):lineno - 1]
                           if l.strip()][-4:]
            named = JSON_FILE_INTRO_RE.search(" ".join(intro_lines))
            if named:
                file_fences.append((lineno, f"`{named.group(0)}`"))
                continue
            if any(sig <= keys for sig in MANIFEST_SIGNATURE_KEYS):
                file_fences.append((lineno, "an unnamed manifest"))
                continue
            if not JSON_DOCUMENT_START_RE.match(body):
                file_fences.append((lineno, "a key fragment"))
                continue
            shown = ", ".join(sorted(keys)[:6])
            c.add("8", f"{doc}:{lineno}",
                  f"```json fence whose keys share nothing with any `contracts.*` "
                  f"entry: {{{shown}}}")

        # Collapsed, not dropped — the same rule as check 13's unqualified steps.
        # The signal here is stronger (a named file is not a guess), but a reader
        # who disagrees has to be able to see that the exemption fired at all.
        if file_fences:
            why = ", ".join(sorted({r for _, r in file_fences}))
            c.add("8", doc,
                  f"{len(file_fences)} ```json fence(s) read as file content rather "
                  f"than interface material — {why} — so not listed individually "
                  f"(lines {', '.join(str(n) for n, _ in file_fences)})")

        swept = blank_link_targets(blank_fences(text))
        for lineno, line in enumerate(swept.splitlines(), 1):
            if re.search(r"endpoints\.[A-Za-z0-9_]+", line):
                continue
            for raw in URL_RE.findall(line):
                url = raw.rstrip(".,;:!?)»\"'`")
                scheme = url.split("://", 1)[0].lower() if "://" in url else ""
                if scheme in NON_ENDPOINT_SCHEMES:
                    continue
                if EXAMPLE_HOST_RE.search(url):
                    continue
                if scheme in ("http", "https") and not (
                        API_PATH_RE.search(url) or FUNCTION_HOST_RE.search(url)):
                    continue        # a page or a documentation link, not an endpoint
                if any(e in url or url in e for e in endpoints):
                    continue
                c.add("8", f"{doc}:{lineno}",
                      f"URL/endpoint shape in prose with no `endpoints.*` home: {url}")


def check_basis_gates(facts: dict, f: Findings,
                      today: datetime.date | None = None) -> None:
    """Check 1b + check 14. The first half is render.py's status_gate (shared, so the
    two tools cannot disagree); the four gates and the shipped/open detector are here."""
    claims = collect_claims(facts)
    for w in status_gate(facts, claims, today):
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
            # Absence and explicit null are not the same declaration. `log_line:
            # null` is the author saying "the emitter has to be built" — the exact
            # out this message offers; the key being absent is the author never
            # having thought about instrumentation. A blank string (`""` / `"  "`)
            # is a key put down with nothing in it, and still drifts.
            ll = e.get("log_line")
            no_emitter = ("log_line" not in e
                          or (isinstance(ll, str) and not ll.strip()))
            if (key == "defects" and norm(e.get("basis")) == "asserted"
                    and e.get("falsified_by") and no_emitter):
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
                        "verified_on": e.get("verified_on"),
                        "retired_on": e.get("retired_on"),
                        "retired_because": e.get("retired_because")})
        else:
            out.append({"id": f"[{i}]", "item": str(e), "status": "", "verified_on": None,
                        "retired_on": None, "retired_because": None})
    return out


def check_acceptance_state(facts: dict, status_rank: int, f: Findings) -> None:
    """§2.4 + §4.2. `acceptance[]` is the contract; `_log.md` is narrative. A set
    was marked `shipped` holding two criteria nothing could satisfy — one of them
    annotated "this is THE test of the set" — because the decision that killed them
    was recorded in the log and never propagated to the contract. The audit passed
    clean: no check compared acceptance[] against reality. This is that check.

    `status: retired` is the way out that does not destroy the record. Before it
    existed the only way to stop a dead criterion from blocking `shipped` was to
    delete it, and deleting it broke every citation of it. Real case: retiring AC6,
    AC12 and AC13 of one research set meant removing them from the registry and
    rewriting their mentions in docs 01 and 02 by hand, so they would not dangle."""
    items = normalize_acceptance(facts)
    # Checked at every stage: a retirement is a decision, and a decision with no
    # date and no reason is the kind nobody can revisit.
    for e in items:
        if e["status"] != "retired":
            continue
        missing = [k for k in ("retired_on", "retired_because") if not e[k]]
        if missing:
            f.add(DRIFT, f"acceptance.{e['id']}",
                  f"`status: retired` with no {' / '.join(f'`{k}:`' for k in missing)}",
                  "a retirement is a decision: when, and why the criterion stopped "
                  "being reachable or relevant — otherwise it reads as a criterion "
                  "somebody gave up on",
                  "26 acceptance state")
    items = [e for e in items if e["status"] != "retired"]
    if status_rank < STATUS_RANK["shipped"]:
        return
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


def check_changes_decision_cascade(facts: dict, f: Findings) -> None:
    """§2.2. A `changes[]` entry can rest on a `decisions.*` premise the same way a
    `defects[]` entry rests on another id — but a decision has no `status: dead` to
    cascade from, because the registry's own convention is to edit `what:` in place
    rather than mint a new key. `revised_on:` is the signal that mutation happened;
    a `changes[]` entry that named the decision in `depends_on:` and was never
    `reviewed_on:` since is check 27's blind spot, one field over.

    Real case: a changes[] entry kept pointing at a directory a later decision had
    retired. Nothing in the registry connected the two, so it rode through
    `implement` unchallenged."""
    decisions = facts.get("decisions")
    decisions = decisions if isinstance(decisions, dict) else {}
    for idx, e in enumerate(facts.get("changes") or []):
        if not isinstance(e, dict):
            continue
        cid = str(e.get("id") or e.get("file") or f"[{idx}]")
        reviewed = e.get("reviewed_on")
        for dep in e.get("depends_on") or []:
            key = str(dep)
            key = key.split(".", 1)[1] if key.startswith("decisions.") else key
            dec = decisions.get(key)
            if not isinstance(dec, dict):
                continue
            revised = dec.get("revised_on")
            if not revised:
                continue
            if not reviewed or str(reviewed) < str(revised):
                stale = ("no `reviewed_on:`" if not reviewed
                         else f"`reviewed_on: {reviewed}`, before the revision")
                f.add(DRIFT, f"changes.{cid}",
                      f"depends on `decisions.{key}`, revised {revised}, with {stale}",
                      "confirm `file:` and `kind:` still hold against the revised "
                      f"decision, then set `reviewed_on: {revised}` or later",
                      "34 changes[] dependency on a revised decision")


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
            target = confined(repo_root, str(raw))
            if target is None:
                f.add(DRIFT, f"{key}.{e.get('id', raw)}",
                      f"declares `{raw}`, which resolves outside {repo_root.name}/",
                      "a registry path is opened by whoever audits the set — keep it "
                      "inside the checkout, or mark it `where: external`",
                      "20 declared paths exist")
                continue
            if target.exists():
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
            if "/" in path_str:
                target = confined(repo_root, path_str)
                if target is None:
                    f.add(DRIFT, src,
                          f"anchor `{path_str}:{line}` resolves outside "
                          f"{repo_root.name}/",
                          "anchors resolve from the repo root and stay under it; a "
                          "`../` here points the audit at a file outside the checkout",
                          "18 anchors resolve")
                    continue
            else:
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
        if is_history(registry_entry(facts, container, name)):
            continue  # kept on purpose so it is not re-derived; nobody has to cite it
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
        ev = node.get("evidence")
        ev = ev if isinstance(ev, dict) else {}  # a string here is drift, not a crash
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
        ev = node.get("evidence")
        ev = ev if isinstance(ev, dict) else {}  # a string here is drift, not a crash
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


# --------------------------------------------------------------------------
# a measurement is a run, not a number (checks 30-33)
# --------------------------------------------------------------------------

# The three `how` values that denote a run A PERSON PERFORMED. `shell` and `git` are
# deliberately out: a command carries its own repeatability, and demanding a run count
# on every `git ls-files` would bury the cases where the count is the whole question.
VARIABLE_HOW = {"device", "log", "sentry"}
ABSENCE_HOW = VARIABLE_HOW | {"provider-behavior"}

# A value that reports nothing was found. The shapes seen in real registries, plus
# the two the Spanish-language sets produce. `{"monitors":[]}` is check 26's real
# case, read as data by a person and by nothing else.
ABSENCE_RE = re.compile(
    r"\b(?:0|no|zero|sin|ning[uú]n[ao]?)\s+"
    r"(?:events?|results?|rows?|hits?|matches|entries|eventos|resultados|filas|"
    r"coincidencias|registros)\b"
    r"|\bnot found\b|\bno matches\b|\bempty\b"
    r"|:\s*\[\s*\]\s*[}\]]|^\s*\[\s*\]\s*$", re.I)

CROSS_SET_RE = re.compile(
    r"([\w./-]*_facts\.yml)`?[\s`]*\b(%s)\.([A-Za-z0-9_]+)"
    % "|".join(ID_CONTAINERS), re.I)


def measured_runs(facts: dict):
    """Every `basis: measured` node whose `how:` is a run someone performed.

    An ABORTED run is not one of them. Its precondition could not be met, so it
    produced no datum — asking it for a sample size or a set of conditions is asking
    a run that did not happen how many times it happened. Check 32 is the one with
    something to say about those, and it says the whole of it."""
    for path, node in walk(facts):
        if not (isinstance(node, dict) and norm(node.get("basis")) == "measured"):
            continue
        ev = node.get("evidence")
        ev = ev if isinstance(ev, dict) else {}  # a string here is the basis gate's
        if norm(ev.get("outcome")).startswith("aborted"):
            continue
        if ev.get("derived_from"):
            continue        # not a run: its n/spread/conditions are its sources' (35)
        if norm(ev.get("how")) in VARIABLE_HOW:
            yield path, node, ev


def registry_entry(facts: dict, container: str, name: str):
    node = facts.get(container)
    if isinstance(node, dict):
        return node.get(name)
    if isinstance(node, list):
        return next((e for e in node
                     if isinstance(e, dict) and str(e.get("id")) == name), None)
    return None


def load_profile(facts: dict, spec_dir: Path, repo_root: Path) -> dict:
    prof = facts.get("profile")
    if not prof:
        return {}
    path = next((b / str(prof) for b in (repo_root, spec_dir)
                 if (b / str(prof)).is_file()), None)
    if path is None:
        return {}
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return {}       # the profile's shape is check 19's business, not this one
    return loaded if isinstance(loaded, dict) else {}


def check_sample_size(facts: dict, prose: dict[str, str], spec_dir: Path,
                      repo_root: Path, f: Findings) -> None:
    """Check 30. `value:` says what came back. Nothing in the four-field shape says
    how many times you looked, and three retractions came out of that one hole:
    `n=1` read as a constant. `limits.degradation_threshold_tiles` in a parent set
    was one run with no bar, cited by a second set, with half a spec hanging off it.
    """
    runs = list(measured_runs(facts))
    counted = [r for r in runs if r[2].get("n") is not None]

    if runs and not counted:
        # Same collapse as check 26: the field is newer than the set, and reporting
        # fifteen identical misses buries the contradictions beside them. A set where
        # SOME runs carry `n:` is the opposite case and is reported per entry.
        f.add(DRIFT, "_facts.yml",
              "no `evidence.n:` on " + (
                  "the only measurement" if len(runs) == 1
                  else f"any of the {len(runs)} measurements") +
              " taken from a run (`how: device|log|sentry`)",
              "how many times a person repeated a procedure is not recoverable from "
              "its output — record it once per entry, `n: 1` included",
              "30 sample size and spread")
    else:
        for path, node, ev in runs:
            where = pretty_path(facts, path) or "_facts.yml"
            if ev.get("n") is None:
                f.add(DRIFT, where,
                      "`basis: measured` from a run with no `evidence.n:`, in a set "
                      "that records it elsewhere",
                      "somebody adopted the field and skipped this run; write the "
                      "count, `n: 1` included",
                      "30 sample size and spread")
                continue
            try:
                n = int(str(ev["n"]).strip())
            except ValueError:
                f.add(DRIFT, where,
                      f"`evidence.n: {ev['n']!r}` is not a run count",
                      "an integer — the number of times the procedure was performed",
                      "30 sample size and spread")
                continue
            if ev.get("spread"):
                continue
            if n <= 1:
                f.add(POLISH, where,
                      "`n: 1` with no `spread:` — one run reported as a bare value",
                      "legitimate as a measurement, unreadable as one: add `spread:` "
                      "(even `'single run, range unknown'`) so the next set does not "
                      "read it as a constant",
                      "30 sample size and spread")
            else:
                f.add(DRIFT, where,
                      f"`n: {n}` with no `spread:` — {n} runs reported as one number",
                      "you observed a range and reported its midpoint; write the "
                      "observed extremes, verbatim (`'0..308 fallas'`)",
                      "30 sample size and spread")

    own = (spec_dir / "_facts.yml").resolve()
    for doc, text in prose.items():
        for lineno, line in enumerate(text.splitlines(), 1):
            for rel, container, name in CROSS_SET_RE.findall(line):
                path = next((b / rel for b in (repo_root, spec_dir, spec_dir.parent)
                             if (b / rel).is_file()), None)
                if path is None or path.resolve() == own:
                    continue
                try:
                    sibling = load_facts(path)
                except (yaml.YAMLError, OSError):
                    continue
                entry = registry_entry(sibling, norm(container), name)
                if not isinstance(entry, dict):
                    continue
                single = single_runs_behind(sibling, entry)
                if not single:
                    continue
                via = ("" if single == [f"{norm(container)}.{name}"]
                       else f" (derived from {', '.join(f'`{r}`' for r in single)})")
                f.add(DRIFT, f"{doc}:{lineno}",
                      f"cites `{container}.{name}` from `{rel}`, which was measured "
                      f"once (`n: 1`) with no `spread:`{via}",
                      "this is where one run becomes a constant: the citing set sees "
                      "a number, a path and an id, and not that the owner looked once "
                      "— re-measure in the owning set, or carry the caveat here",
                      "30 sample size and spread")


def check_run_conditions(facts: dict, spec_dir: Path, repo_root: Path,
                         f: Findings) -> None:
    """Check 31. Four events varied 2.3x in bitrate (3.47 / 6.76 / 8.01 / 8.20 Mbps)
    and no number in either of two related sets recorded which event produced it.
    They were compared anyway, and the comparison decided the scope.

    Which axes vary is a property of the repo, so the required keys come from
    `_profile.yml conditions_required:` — the same split as the commands. The
    depends_on half needs no profile and is never switchable off."""
    required = load_profile(facts, spec_dir, repo_root).get("conditions_required")
    required = [str(k) for k in required] if isinstance(required, list) else []

    for path, node, ev in measured_runs(facts):
        cond = ev.get("conditions")
        cond = cond if isinstance(cond, dict) else {}
        missing = [k for k in required
                   if cond.get(k) is None or str(cond.get(k)).strip() == ""]
        if missing:
            f.add(DRIFT, pretty_path(facts, path) or "_facts.yml",
                  "`evidence.conditions:` does not record "
                  f"{', '.join(f'`{k}`' for k in missing)}",
                  "the profile names these as varying in this repo, so the run did "
                  "not control them and the value cannot be compared against another "
                  "run without them",
                  "31 conditions of the run")

    by_id: dict[str, tuple[str, dict]] = {}
    for path, node in walk(facts):
        if isinstance(node, dict) and node.get("id"):
            by_id.setdefault(str(node["id"]), (path, node))

    for path, node in walk(facts):
        if not (isinstance(node, dict) and node.get("depends_on")):
            continue
        ev = node.get("evidence")
        mine = ev.get("conditions") if isinstance(ev, dict) else None
        if not isinstance(mine, dict):
            continue
        for dep in node.get("depends_on") or []:
            target = by_id.get(str(dep), (None, {}))[1]
            tev = target.get("evidence") if isinstance(target, dict) else None
            theirs = tev.get("conditions") if isinstance(tev, dict) else None
            if not isinstance(theirs, dict):
                continue
            clash = [k for k in mine
                     if k in theirs
                     and str(mine[k]).strip() != str(theirs[k]).strip()]
            if clash:
                f.add(CONTRADICTION, pretty_path(facts, path) or "_facts.yml",
                      f"rests on `{dep}`, measured under different "
                      f"{', '.join(f'`{k}`' for k in clash)} "
                      f"({', '.join(f'{k}: {mine[k]} vs {theirs[k]}' for k in clash)})",
                      "the derived claim compares two runs across a variable nobody "
                      "held fixed — re-measure both under one set of conditions, or "
                      "state which one the conclusion is scoped to",
                      "31 conditions of the run")


def check_aborted_runs(facts: dict, f: Findings) -> None:
    """Check 32. A confound was marked BEFORE a device run and the run happened
    anyway; it cost a retraction and a full build/install/navigate cycle. The number
    that came back was not a weak measurement — it was not a measurement, and the
    damage was done when it got reinterpreted instead of discarded."""
    for path, node in walk(facts):
        if not isinstance(node, dict):
            continue
        ev = node.get("evidence")
        ev = ev if isinstance(ev, dict) else {}
        if not norm(ev.get("outcome")).startswith("aborted"):
            continue
        where = pretty_path(facts, path) or "_facts.yml"
        if norm(node.get("basis")) == "measured":
            f.add(CONTRADICTION, where,
                  f"`basis: measured` on a run recorded as `{ev['outcome']}`",
                  "an aborted run is not a measurement — `basis:` stays `asserted` "
                  "and `falsified_by:` stays where it was",
                  "32 aborted run produced no datum")
        if ev.get("value") is not None and str(ev.get("value")).strip():
            f.add(CONTRADICTION, where,
                  f"a run recorded as `{ev['outcome']}` still carries a `value:`: "
                  f"{str(ev['value']).strip()[:60]!r}",
                  "the precondition was missing, so that number answers a different "
                  "question — delete it. Qualifying it in prose puts the caveat in "
                  "one document and the number in three",
                  "32 aborted run produced no datum")
        if not ev.get("aborted_because"):
            f.add(DRIFT, where,
                  f"`{ev['outcome']}` with no `aborted_because:`",
                  "name the precondition that could not be met, in the terms of the "
                  "claim — otherwise the next session re-runs it the same way",
                  "32 aborted run produced no datum")


def check_absence_of_signal(facts: dict, f: Findings) -> None:
    """Check 33. Four player buckets reach Sentry through
    `usePlayerActions.js:399 onError`. The failure under investigation raises no
    error: it is invisible by construction, and an empty query over it says nothing.
    The check before "this does not happen in production" is "does the path emit?",
    never "is there a signature?"."""
    for path, node in walk(facts):
        if not (isinstance(node, dict) and norm(node.get("basis")) == "measured"):
            continue
        ev = node.get("evidence")
        ev = ev if isinstance(ev, dict) else {}
        if norm(ev.get("how")) not in ABSENCE_HOW:
            continue        # a git/shell absence is deterministic — check 1b's
        where = pretty_path(facts, path) or "_facts.yml"
        declared = str(ev.get("absence") or "").strip().lower() in ("true", "yes", "1")

        if not declared:
            value = str(ev.get("value") or "")
            if value and ABSENCE_RE.search(value):
                f.add(DRIFT, where,
                      f"`value` records an absence of signal — {value.strip()[:60]!r} "
                      "— with no `absence:` declared",
                      "an empty result is not evidence of non-occurrence until the "
                      "path is known to emit: `absence: true`, `emits:` (the "
                      "`file:line` that would have produced it) and `sample_rate:`",
                      "33 absence of signal")
            continue

        if "emits" not in ev:
            f.add(DRIFT, where,
                  "`absence: true` with no `emits:`",
                  "name the `file:line` that would have produced the signal — the "
                  "question is \"does the path emit?\", and this entry never asked it",
                  "33 absence of signal")
        elif ev.get("emits") is None:
            # An explicit null is a declaration, same as check 14's `log_line: null`
            # — and here the declaration is the decisive finding, not the out.
            f.add(DRIFT, where,
                  "`absence: true` with `emits: null` — nothing emits this signal",
                  "its absence is therefore not evidence of non-occurrence: drop to "
                  "`basis: asserted`, or make the emitter a `changes[]` entry and "
                  "measure after it ships",
                  "33 absence of signal")
        if "sample_rate" not in ev:
            f.add(DRIFT, where,
                  "`absence: true` with no `sample_rate:`",
                  "at `0.2`, four of five occurrences never appear and an empty "
                  "result is the expected output of a system that IS failing; "
                  "`null` means unsampled and settles it",
                  "33 absence of signal")

# --------------------------------------------------------------------------
# derived evidence, retractions and corrections (checks 35, 36)
# --------------------------------------------------------------------------

def parse_ref(ref) -> tuple[str, str] | None:
    """`limits.x` -> ("limits", "x"). Only the registry's own containers qualify: a
    bare `x` could be anything, and guessing its container is how a citation ends
    up resolving to the wrong entry."""
    m = re.fullmatch(r"\s*(%s)\.([A-Za-z0-9_]+)\s*" % "|".join(ID_CONTAINERS),
                     str(ref), re.I)
    return (norm(m.group(1)), m.group(2)) if m else None


def as_list(value) -> list:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def single_runs_behind(facts: dict, entry: dict, seen: set | None = None,
                       label: str = "") -> list[str]:
    """The `n: 1`, spread-less runs a value ultimately rests on.

    A measured entry answers for itself. A derived one inherits its sources' bar —
    that is the whole point of deriving instead of re-typing `n` and `spread` — so
    it is exactly as single-run as the weakest thing it names."""
    ev = entry.get("evidence")
    ev = ev if isinstance(ev, dict) else {}
    refs = as_list(ev.get("derived_from"))
    if not refs:
        return ([label or "?"] if str(ev.get("n") or "").strip() == "1"
                and not ev.get("spread") else [])
    seen = seen if seen is not None else set()
    out: list[str] = []
    for ref in refs:
        parsed = parse_ref(ref)
        if not parsed or parsed in seen:
            continue
        seen.add(parsed)
        parent = registry_entry(facts, *parsed)
        if isinstance(parent, dict):
            out += single_runs_behind(facts, parent, seen, ".".join(parsed))
    return out


def is_retracted(entry) -> bool:
    return isinstance(entry, dict) and bool(entry.get("retracted_on"))


def is_corrected(entry) -> bool:
    return isinstance(entry, dict) and bool(entry.get("corrected_on"))


def is_history(entry) -> bool:
    """Kept on purpose and allowed to go uncited: a retracted entry stays so it is
    not re-derived, a retired criterion stays so its citations keep resolving."""
    return is_retracted(entry) or (isinstance(entry, dict)
                                   and norm(entry.get("status")) == "retired")


# What "mentions the correction" means mechanically: the citing paragraph or entry
# says so in words, or names the entry that superseded the one it cites. Both
# languages the real sets are written in.
CORRECTION_WORD_RE = re.compile(
    r"\bretract\w*|\bretract[oó]\w*|\bcorreg\w*|\bcorrecci[oó]n\w*|\bcorrected\b|"
    r"\bcorrection\w*|\bsupersed\w*|\breemplaz\w*|\bno longer holds\b|"
    r"\bya no (?:vale|rige|es cierto)\b", re.I)


def superseding_refs(entry: dict) -> list[str]:
    return [str(r) for key in ("retracted_by", "corrected_by")
            for r in as_list(entry.get(key)) if r]


def mentions_correction(text: str, entry: dict) -> bool:
    if CORRECTION_WORD_RE.search(text):
        return True
    for ref in superseding_refs(entry):
        name = ref.rsplit(".", 1)[-1]
        if ref in text or re.search(rf"(?<![\w]){re.escape(name)}(?![\w])", text):
            return True
    return False


def correction_state(entry: dict) -> str:
    if is_retracted(entry):
        by = ", ".join(superseding_refs(entry)) or "no replacement"
        return f"retracted on {entry['retracted_on']} ({by})"
    return f"corrected on {entry['corrected_on']}" + (
        f" ({', '.join(superseding_refs(entry))})" if superseding_refs(entry) else "")


def check_derived_evidence(facts: dict, f: Findings) -> None:
    """Check 35. `evidence: { derived_from: [limits.x, limits.y], date, value }`.

    A conclusion read off measurements that already live in the registry is not a
    new run, and forcing it into the run shape made authors copy `n:` and `spread:`
    from the entries it rested on — two copies of one bar, the drift this skill
    exists to stop. Real case: six defects of one research set went `measured` by
    naming limits inside `cmd:` as prose, and the audit then demanded `n`/`spread`
    that already lived in those limits.

    It counts as `measured` only while everything it names does. A source that is
    `asserted`, `decided`, retracted or missing makes the derived value a claim the
    registry cannot back — CONTRADICTION, the same severity as a `measured` whose
    `cmd` cannot be re-run (check 24). A corrected source is DRIFT unless the entry
    says it took the correction into account."""
    graph: dict[str, list[tuple[str, str]]] = {}
    for path, node in walk(facts):
        if not isinstance(node, dict):
            continue
        ev = node.get("evidence")
        if not isinstance(ev, dict) or not ev.get("derived_from"):
            continue
        where = pretty_path(facts, path) or "_facts.yml"
        text = yaml.safe_dump(node, allow_unicode=True)
        edges = []
        for ref in as_list(ev.get("derived_from")):
            parsed = parse_ref(ref)
            target = registry_entry(facts, *parsed) if parsed else None
            if not isinstance(target, dict):
                f.add(CONTRADICTION, where,
                      f"`derived_from` names `{ref}`, which this registry does not "
                      "define" + ("" if parsed else " (write it `<container>.<id>`)"),
                      "a derived value is only as real as its sources — fix the "
                      "reference, or drop to `basis: asserted`",
                      "35 derived evidence")
                continue
            edges.append(parsed)
            label = ".".join(parsed)
            if is_retracted(target):
                f.add(CONTRADICTION, where,
                      f"derived from `{label}`, {correction_state(target)}",
                      "a retracted measurement backs nothing: re-derive from what "
                      "replaced it, or drop to `basis: asserted`",
                      "35 derived evidence")
            elif norm(target.get("basis")) != "measured":
                f.add(CONTRADICTION, where,
                      f"derived from `{label}`, which is `basis: "
                      f"{norm(target.get('basis')) or 'absent'}`",
                      "derived evidence counts as `measured` only while every source "
                      "is — measure the source, or drop this to `basis: asserted`",
                      "35 derived evidence")
            elif is_corrected(target) and not mentions_correction(text, target):
                f.add(DRIFT, where,
                      f"derived from `{label}`, {correction_state(target)}, and "
                      "the entry does not mention the correction",
                      "re-read the source against its `correction:` and say in this "
                      "entry that the derivation still holds",
                      "35 derived evidence")
        graph[path] = edges

    # A derivation that reaches itself rests on nothing measured at all.
    def reaches(start: tuple[str, str], goal: tuple[str, str], seen: set) -> bool:
        if start == goal:
            return True
        if start in seen:
            return False
        seen.add(start)
        entry = registry_entry(facts, *start)
        ev = entry.get("evidence") if isinstance(entry, dict) else None
        refs = as_list(ev.get("derived_from")) if isinstance(ev, dict) else []
        return any(reaches(p, goal, seen) for p in map(parse_ref, refs) if p)

    for container in ID_CONTAINERS:
        for name, entry in registry_container_entries(facts, container).items():
            ev = entry.get("evidence") if isinstance(entry, dict) else None
            if not (isinstance(ev, dict) and ev.get("derived_from")):
                continue
            me = (container, name)
            if any(reaches(p, me, set())
                   for p in map(parse_ref, as_list(ev["derived_from"])) if p):
                f.add(CONTRADICTION, f"{container}.{name}",
                      "`derived_from` is circular — following it leads back here",
                      "at least one link in the chain has to be a run somebody "
                      "performed",
                      "35 derived evidence")


def registry_scopes(facts: dict):
    """-> (label, entry, text without derived_from). One scope per registry entry:
    a correction mentioned anywhere in the citing entry counts, the same way a
    paragraph is the unit in prose."""
    for key, node in facts.items():
        if key in ID_CONTAINERS:
            for name, entry in registry_container_entries(facts, key).items():
                yield f"{key}.{name}", entry, scope_text(entry)
        elif isinstance(node, (dict, list)):
            yield str(key), node, scope_text(node)


def scope_text(node) -> str:
    parts = []
    for path, sub in walk(node):
        if ".derived_from" in f".{path}" or isinstance(sub, (dict, list)) or sub is None:
            continue
        parts.append(str(sub))
    return "\n".join(parts)


def prose_paragraphs(text: str):
    """-> (first line number, [(line number, line)]). A paragraph is a run of
    non-blank lines; a table row is its own paragraph, because one row mentioning a
    retraction says nothing about the row below it."""
    block: list[tuple[int, str]] = []
    for lineno, line in enumerate(blank_fences(text).splitlines(), 1):
        if not line.strip():
            if block:
                yield block
            block = []
        elif line.lstrip().startswith("|"):
            if block:
                yield block
            yield [(lineno, line)]
            block = []
        else:
            block.append((lineno, line))
    if block:
        yield block


def check_corrections(facts: dict, prose: dict[str, str], spec_dir: Path,
                      repo_root: Path, f: Findings, c: Candidates) -> None:
    """Check 36. `retracted_on` / `retracted_by` and `corrected_on` / `corrected_by` /
    `correction` were already in use, by hand, and nothing read them. So an entry
    could be retracted in its own registry while every sentence resting on it — in
    this set or in another one — went on quoting it as if it held.

    Real case: `sports-multiview-grid` cites limits of the research set that owns
    them. When the research corrected one, nothing told the grid.

    Citations are read where a program can see them: `container.id` in this set's
    docs and registry, and `` `docs/features/<slug>/_facts.yml` container.id `` for
    another set's entries — resolved by loading that registry, exactly as check 30
    does. A citation is fine when its paragraph (prose) or entry (registry) names
    the replacement or says the word; `_log.md` is history and is never read.

    The two states do not get the same verdict, and running it on the real sets is
    what decided that. A RETRACTED entry no longer holds, so a sentence resting on
    it without saying so is wrong whenever it was written — DRIFT. A CORRECTED entry
    is usually corrected in place: its value is fixed, and a sentence written after
    the fix cites the right thing without any reason to mention the history. Nothing
    in a markdown line says when it was written. Measured on two real sets: of nine
    such citations, the two in the research set were notes written before the
    correction and framed exactly the way it inverted; the seven in the other set
    cited an entry rewritten and renamed in place, one of them in a paragraph that
    says outright "the first reading was wrong". So a corrected citation is a
    candidate, and a person decides which side of the correction it was written on."""
    own_ids = registry_ids(facts)

    # Format: the fields that make a retraction or correction legible later.
    for label, entry, _ in registry_scopes(facts):
        if not isinstance(entry, dict):
            continue
        if is_retracted(entry) and not (entry.get("retracted_by")
                                        or entry.get("retracted_because")):
            f.add(DRIFT, label, "`retracted_on:` with no `retracted_by:` and no "
                  "`retracted_because:`",
                  "name the entry that replaced it, or say why it was wrong — a bare "
                  "date tells the next reader that something happened, not what",
                  "36 retractions and corrections")
        if is_corrected(entry) and not entry.get("correction"):
            f.add(DRIFT, label, "`corrected_on:` with no `correction:`",
                  "state what changed, in one sentence a citing set can quote",
                  "36 retractions and corrections")
        for ref in superseding_refs(entry):
            parsed = parse_ref(ref)
            if parsed and registry_entry(facts, *parsed) is None:
                f.add(DRIFT, label, f"superseded by `{ref}`, which this registry "
                      "does not define",
                      "fix the reference — a reader following it lands nowhere",
                      "36 retractions and corrections")

    siblings: dict[Path, dict | None] = {}
    own = (spec_dir / "_facts.yml").resolve()

    def sibling_entry(rel: str, container: str, name: str):
        path = next((b / rel for b in (repo_root, spec_dir, spec_dir.parent)
                     if (b / rel).is_file()), None)
        if path is None or path.resolve() == own:
            return None
        key = path.resolve()
        if key not in siblings:
            try:
                siblings[key] = load_facts(path)
            except (yaml.YAMLError, OSError):
                siblings[key] = None
        sib = siblings[key]
        return registry_entry(sib, norm(container), name) if sib else None

    containers = "|".join(ID_CONTAINERS)
    local_re = re.compile(rf"\b({containers})\.([A-Za-z0-9_]+)", re.I)

    def citations(text: str):
        """-> [(label, target entry, origin)] for every retracted/corrected cite."""
        out, spans = [], []
        for m in CROSS_SET_RE.finditer(text):
            spans.append((m.start(), m.end()))
            rel, container, name = m.groups()
            target = sibling_entry(rel, container, name)
            if is_retracted(target) or is_corrected(target):
                out.append((f"{norm(container)}.{name}", target, rel))
        for m in local_re.finditer(text):
            if any(a <= m.start() < b for a, b in spans):
                continue
            container, name = norm(m.group(1)), m.group(2)
            if own_ids.get(name) != container:
                continue
            target = registry_entry(facts, container, name)
            if is_retracted(target) or is_corrected(target):
                out.append((f"{container}.{name}", target, None))
        return out

    def report_one(where: str, label: str, target: dict, origin: str | None) -> None:
        src = f" in `{origin}`" if origin else ""
        if not is_retracted(target):
            c.add("36", where,
                  f"cites `{label}`{src}, {correction_state(target)}, and does not "
                  "mention it — written before the correction, or against the "
                  "corrected version?")
            return
        f.add(DRIFT, where,
              f"cites `{label}`{src}, {correction_state(target)}, without mentioning "
              "it",
              "say it in the same paragraph — the replacement's id or the word — "
              "or stop resting on it; a citation that reads as if the entry still "
              "held is how a correction fails to reach the sets built on it",
              "36 retractions and corrections")

    for label, entry, text in registry_scopes(facts):
        seen = set()
        for cited, target, origin in citations(text):
            if origin is None and (cited == label
                                   or label in superseding_refs(target)):
                continue    # the entry itself, or the one that replaced it
            if cited in seen or mentions_correction(text, target):
                continue
            seen.add(cited)
            report_one(label, cited, target, origin)

    for doc, body in prose.items():
        if doc == "_log.md":
            continue
        for block in prose_paragraphs(body):
            text = "\n".join(line for _, line in block)
            seen = set()
            for cited, target, origin in citations(text):
                if cited in seen or mentions_correction(text, target):
                    continue
                seen.add(cited)
                lineno = next((n for n, line in block if cited in line
                               or cited.split(".", 1)[1] in line), block[0][0])
                report_one(f"{doc}:{lineno}", cited, target, origin)


# How far ahead an `accepted.until:` is announced as coming due. Two weeks is the
# lead a measurement needs to be scheduled rather than improvised the day G1 bites.
EXPIRY_WARNING_DAYS = 14


def live_accepted_risks(facts: dict, today: datetime.date | None = None
                        ) -> list[tuple[str, str, str, int | None]]:
    """Deferrals with a deadline that has not arrived. Not findings — but not
    silence either: the audit names them and their expiry, which is the whole
    reason the field exists rather than a note in a log entry.

    -> (id, detail, because, days left). Days left is what lets the report separate
    the ones coming due: a list of four risks all printed the same way reads as
    "handled" until the morning G1 refuses all four at once. Real case: four risks
    of one research set, accepted together, all expire on 2026-10-23."""
    today = today or datetime.date.today()
    out = []
    for d in facts.get("defects") or []:
        if not isinstance(d, dict):
            continue
        state, detail = accepted_state(d, today)
        if state == "live":
            acc = d.get("accepted") or {}
            because = str(acc.get("because", "")).strip()
            until = acc.get("until")
            if not isinstance(until, datetime.date):
                try:
                    until = datetime.date.fromisoformat(str(until).strip())
                except ValueError:
                    until = None
            left = (until - today).days if until else None
            out.append((str(d.get("id", "?")), detail, because, left))
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


STARTER_PLACEHOLDER = re.compile(r"^<.*>$")


def check_profile_identity(prof: str, spec_dir: Path, repo_root: Path,
                           root_is_real: bool, f: Findings) -> None:
    """Check 15, the two halves that are pure string comparison.

    A profile carries the identity of the checkout it was written for, and a spec
    folder copied between projects brings the profile along. Every `cmd` in the set
    then belongs to a different repo — and every one of them still runs, which is
    why this is a CONTRADICTION and not a note. Same defect class as copying a test
    count out of a sibling spec, one level up.

    An `<angle bracket>` value is an unfilled starter, not a mismatch; check 15's
    last bullet is the one that cares about those, and it cares in the other
    direction (a starter holding a CONCRETE value leaks one project into every
    other)."""
    path = profile_path(prof, spec_dir, repo_root)
    if path is None or not root_is_real:
        # No git root resolved, so `basename` has nothing to say about which
        # checkout this is and a comparison would invent a finding.
        return
    try:
        profile = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return          # the profile's shape is check 19's business, not this one
    if not isinstance(profile, dict):
        return

    declared = str(profile.get("repo") or "").strip()
    if declared and not STARTER_PLACEHOLDER.match(declared) \
            and declared != repo_root.name:
        f.add(CONTRADICTION, prof,
              f"`repo: {declared}` but this checkout is `{repo_root.name}`",
              "the profile came from another checkout — almost always a spec folder "
              "copied between projects with the profile travelling along. Every `cmd` "
              "in the set now belongs to a different repo and every one of them still "
              "runs",
              "15 profile coverage")

    app = str(profile.get("app") or "").strip()
    if not app or STARTER_PLACEHOLDER.match(app):
        return
    try:
        parts = spec_dir.resolve().relative_to(repo_root.resolve()).parts
    except ValueError:
        return          # the spec is not under the repo root; check 20's territory
    if not all(p in parts for p in Path(app).parts):
        f.add(CONTRADICTION, prof,
              f"`app: {app}` does not govern the directory holding this spec "
              f"({'/'.join(parts) or '.'})",
              "the `app_id` is another variant's, so every `how: device` claim in the "
              "set was gathered against the wrong install",
              "15 profile coverage")


def check_profile_and_log(facts: dict, spec_dir: Path, repo_root: Path,
                          root_is_real: bool, f: Findings) -> None:
    """Checks 15 and 16, the parts a program can settle without git plumbing."""
    prof = facts.get("profile")
    if not prof:
        f.add(DRIFT, "_facts.yml", "no `profile:`",
              "every cmd in the set was then invented per feature, and check 1b has "
              "nothing to compare against",
              "15 profile coverage")
    elif profile_path(str(prof), spec_dir, repo_root) is None:
        f.add(CONTRADICTION, "_facts.yml", f"`profile: {prof}` does not resolve",
              "the set moved, the profile came from another checkout, or the path "
              "climbs out of the repo — a profile is read and parsed, so it stays in",
              "15 profile coverage")
    else:
        check_profile_identity(str(prof), spec_dir, repo_root, root_is_real, f)
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

# Every `[human]` and `[script + human]` check the script cannot settle, with the
# doc that has to exist for the comparison to be possible at all. A check missing
# from this list is not "passed" — it is skipped, silently, which is the single
# failure this script exists to prevent. Adding a check here is not optional.
#
# gate: None → always listed. "02" / "02|03" → listed only once that doc is on
# disk, because before it exists there is nothing to compare the registry against
# and telling a human to compare is telling them to do impossible work.
HUMAN_PASS = [
    ("1", "data-vs-registry wording", "every shared datum's exact wording in each doc "
     "— normalization (quoting, escaped pipes) makes this a judgment call", None),
    ("1b", "re-run `evidence.cmd`", "deliberately NOT automated: this script does not "
     "execute commands out of a registry. Re-run them yourself and diff against "
     "`evidence.value`", None),
    ("2", "singletons unique", "`dates.*`, revision tags, `tests_baseline`, version "
     "numbers must read identically in every doc that mentions them — any variance "
     "is a CONTRADICTION", None),
    ("3", "contract shape", "the candidates below are key-set diffs against "
     "`contracts.*`, which is arithmetic. The exception is not: a field the sender "
     "injects downstream is legitimate IF a doc note explains it, and the script "
     "cannot read the note. Find it, or write the POLISH", None),
    ("3.5", "`decisions.*` cited_in", "when a decision changes, walk its `cited_in:` "
     "sections by hand — `sync` replaces values and a premise has no value to replace",
     None),
    ("4", "cross-refs resolve", "mechanical sweeps over-report here; the protocol "
     "lists two exempt shapes and only the first — a section number quoted AS TEXT "
     "— is stripped below. The second, a changelog clause naming a doc once and "
     "then enumerating what changed inside it, cannot be. Verify each hit by eye",
     None),
    ("5", "checklist coverage", "each doc 01 checklist item has a counterpart in doc "
     "02 (implementation/test) and/or doc 03 (stakeholder)", "02|03"),
    ("6", "acceptance parity", "doc 02's Definition of Done vs `acceptance[]`, "
     "criteria with `status: retired` left out", "02"),
    ("7", "scope parity", "`changes[]` vs each doc's affected-components table. "
     "`related_docs[]` do NOT participate — one appearing in a \"what changes\" table "
     "is itself a CONTRADICTION", None),
    ("8", "prose-orphan contracts & endpoints", "the candidates below are ```json / "
     "```http fences and URL shapes in prose with no `contracts.*` / `endpoints.*` "
     "home. Each needs the paragraph around it: a fence can legitimately show a "
     "fragment or a third party's payload this set only reads, and a URL can be a "
     "provider's documented callback that belongs in nobody's registry", None),
    ("9", "sibling docs under other names", "the script globs `*<slug>*` and every "
     "`.md` in the spec dir; a file on this feature's theme whose NAME shares nothing "
     "with the slug is invisible to that and is the half left here", None),
    ("11", "ambiguous counters", "an integer whose meaning depends on a predicate "
     "(`attended`, `resolved`, `remaining`) needs a `note:` or a field name stating "
     "it; two counters that differ with neither is DRIFT", None),
    ("12", "staleness by age", "`evidence.date` (legacy `verified.date`) older than "
     "the last commit touching what it measures, or older than 7 days on a volatile "
     "metric. Check 1b re-runs the command; this one flags the ones you would never "
     "think to re-run because nothing looks wrong", None),
    ("13", "doc 02 executability", "the candidates below are the three regex-able "
     "sub-bullets. The other five are yours and none is mechanizable: a symbol named "
     "but never defined, an edit with no anchor, a B.1 row worded as parity or "
     "negation with no `Falla si:` mutation, a persisted store with no schema, and a "
     "step that needs judgment", "02"),
    ("15", "profile coverage, the halves that are not string comparison",
     "`gap_sweep_layers:` empty while this stack has a shipped layer; "
     "`commands.tests_expect` not contained in `tests_baseline.evidence.value`; a "
     "command pasted into a doc that differs from the profile's with `{}` "
     "substituted; an `references/intake.md` never-guess field the repo cannot "
     "corroborate; `profile:` pointing somewhere the upward walk does not resolve "
     "today. The script settles `repo:` and `app:` and nothing else", None),
    ("16", "handoff log integrity", "only once `_log.md` exists. The script settles "
     "the `Stage:` line against `status:`; a person still checks that each file's "
     "current `wc -l` + `git hash-object` match what the last entry naming it "
     "recorded, that no finding is carried two rounds with no disposition, that a "
     "`rejected` disposition cites output, and that round ids are monotonic", None),
    ("28", "`tracking.issues` / `pr` / `milestone` on GitHub", "deliberately NOT "
     "automated: an auditor that makes network calls is a different kind of tool. "
     "`gh issue view` / `gh pr view` and check the state matches `status:`", None),
    ("36", "citations of a corrected entry", "the candidates below cite an entry "
     "carrying `corrected_on:` with no mention of the correction nearby. A corrected "
     "entry is usually fixed in place, so a sentence written AFTER the fix is right "
     "as it stands; one written before it may rest on exactly what was corrected. "
     "Nothing in the text says which — read it against `correction:`. Citations of "
     "a RETRACTED entry are findings, not candidates", None),
]


def report(f: Findings, cands: Candidates, facts: dict, in_scope, deferred,
           prose, as_json: bool, declared_status: str | None = None,
           audited_as: str | None = None,
           today: datetime.date | None = None) -> int:
    order = {CONTRADICTION: 0, DRIFT: 1, POLISH: 2}
    f.items.sort(key=lambda x: (order[x["severity"]], x["check"], x["where"]))

    if as_json:
        print(json.dumps({"status": declared_status or facts.get("status"),
                          "audited_as": audited_as, "findings": f.items,
                          "accepted_risks": [
                              {"id": r[0], "detail": r[1], "days_left": r[3]}
                              for r in live_accepted_risks(facts, today)],
                          "candidates": cands.by_check,
                          "deferred_docs": [d["file"] for d in deferred]},
                         indent=2, ensure_ascii=False))
        return 1 if f.count(CONTRADICTION) else 0

    status = str(facts.get("status") or "draft")
    shown = (f"status: {declared_status}, audited AS `{audited_as}` — preview, the "
             "file was not touched" if audited_as else f"status: {status}")
    print(f"# audit — {facts.get('feature', '?')}  ({shown})\n")
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

    have = {d["id"] for d in in_scope if d["exists"]}

    # Check 5, inverted: before docs 02/03 exist there is nothing to cover them
    # WITH, so the items are listed as the input `implement` has to satisfy.
    if not have & {"02", "03"}:
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

    risks = live_accepted_risks(facts, today)
    due = [r for r in risks if r[3] is not None and r[3] <= EXPIRY_WARNING_DAYS]
    if risks:
        print("## Accepted risks, with their expiry\n")
        print("Recorded decisions to ship with a cause still asserted. Not findings "
              "— until the date passes, and then G1 refuses again:\n")
        for rid, detail, because, left in risks:
            print(f"  defects.{rid} — {detail}")
            if because:
                print(f"      {because}")
        print()
    if due:
        # Apart from the list above on purpose: the ones that are about to turn
        # back into CONTRADICTIONs are the ones somebody has to act on this week.
        print(f"## Accepted risks due within {EXPIRY_WARNING_DAYS} days\n")
        print("Still not findings. Each becomes a G1 CONTRADICTION the day after "
              "its `until:` — schedule the measurement, or extend `until:` with a "
              "reason a person signs:\n")
        for rid, detail, _, left in sorted(due, key=lambda r: r[3]):
            when = ("today" if left == 0 else "tomorrow" if left == 1
                    else f"in {left} days")
            print(f"  defects.{rid} — expires {when} ({detail})")
        print()

    print("## Requires a human pass\n")
    emitted = set()
    for num, name, why, gate in HUMAN_PASS:
        if gate and not have & set(gate.split("|")):
            continue
        print(f"  check {num:<3} {name} — {why}")
        for cand in cands.by_check.get(num, ()):
            emitted.add(num)
            print(f"      · {cand['where']}: {cand['what']}")
    # A candidate group whose check is gated off, or absent from HUMAN_PASS
    # altogether, would otherwise be computed and silently dropped — the exact
    # failure mode HUMAN_PASS exists to close, one level down.
    for num, items in sorted(cands.by_check.items()):
        if num in emitted or not items:
            continue
        print(f"  check {num:<3} candidates (check not listed above)")
        for cand in items:
            print(f"      · {cand['where']}: {cand['what']}")
    print()

    c, d, p = f.count(CONTRADICTION), f.count(DRIFT), f.count(POLISH)
    verdict = (f"{c} contradictions, {d} drift, {p} polish" if f.items
               else "clean — every mechanized check passed")
    if deferred:
        verdict += f" · stage {status}: {len(deferred)} doc(s) not due yet"
    if risks:
        verdict += f" · {len(risks)} accepted risk(s) with a due date"
    if due:
        verdict += f", {len(due)} due within {EXPIRY_WARNING_DAYS} days"
    if cands.total():
        # Counted apart from the findings on purpose. A candidate has no severity
        # yet, so folding it into the verdict would make the count assert something
        # nobody has judged — but leaving it out entirely reads as "nothing to look
        # at", which is the other half of the same lie.
        verdict += (f" · {cands.total()} candidate(s) for the human pass, in "
                    f"{len(cands.by_check)} check(s)")
    print(verdict)
    return 1 if c else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("spec_dir")
    ap.add_argument("--repo-root", default=None,
                    help="anchor/file resolution root (default: git toplevel)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--as-status", choices=sorted(STATUS_RANK, key=STATUS_RANK.get),
                    default=None,
                    help="audit the set as if `status:` already read STAGE — in "
                         "memory, the file is not touched")
    ap.add_argument("--today", default=None, metavar="YYYY-MM-DD",
                    help="the date `accepted.until:` is measured against "
                         "(default: the real today)")
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
        sys.exit(f"no _facts.yml in {spec_dir} — not a feature-spec set.")
    facts = load_facts(facts_path)
    declared_status = str(facts.get("status") or "draft")
    if args.as_status:
        # A shallow copy, never a write: the point is to see what a flip would
        # surface BEFORE making it, in place, so every anchor still resolves against
        # the real tree. Real case: a research set about to go `shipped` was audited
        # on a copy made outside the repo to preview the flip, and 54 findings came
        # back — most of them anchors "missing" only because the copy was elsewhere.
        facts = dict(facts)
        facts["status"] = args.as_status
    repo_root, root_is_real = repo_root_for(spec_dir, args.repo_root)

    rank, in_scope, deferred = resolve_stage(facts, spec_dir)
    prose = {d["file"]: d["path"].read_text(encoding="utf-8")
             for d in in_scope if d["exists"]}
    if not prose:
        for path in sorted(spec_dir.glob("[0-9][0-9]*.md")):
            prose[path.name] = path.read_text(encoding="utf-8")

    f, c = Findings(), Candidates()
    check_top_level_keys(facts, f)
    check_docs_on_disk(in_scope, deferred, f)
    check_sibling_docs(facts, spec_dir, repo_root, f)
    check_basis_gates(facts, f, today)
    check_declared_dependencies(facts, f)
    check_changes_vocabulary(facts, f)
    check_acceptance_state(facts, rank, f)
    check_dead_dependency_cascade(facts, f)
    check_changes_decision_cascade(facts, f)
    check_file_existence(facts, repo_root, rank, f)
    check_anchors(facts, prose, repo_root, f)
    check_orphan_and_dangling_ids(facts, prose, f)
    check_phase_numbering(prose, f)
    check_evidence_cmd_runnable(facts, f)
    check_placeholders(facts, f)
    check_tracking(facts, repo_root, f)
    check_provider_behavior(facts, f)
    check_sample_size(facts, prose, spec_dir, repo_root, f)
    check_run_conditions(facts, spec_dir, repo_root, f)
    check_aborted_runs(facts, f)
    check_absence_of_signal(facts, f)
    check_derived_evidence(facts, f)
    check_corrections(facts, prose, spec_dir, repo_root, f, c)
    check_doc_size(in_scope, f)
    check_profile_and_log(facts, spec_dir, repo_root, root_is_real, f)
    if not args.as_status or norm(args.as_status) == norm(declared_status):
        # Under --as-status the transition has not happened, so the log cannot
        # record it yet; reporting that would be the one finding the preview itself
        # manufactures.
        check_log_stage(facts, spec_dir, f)
    check_prose_orphans(facts, prose, c)
    check_contract_shape(facts, prose, c)
    check_cross_refs(facts, prose, in_scope, c)
    check_doc02_executability(facts, prose, in_scope, c)

    audited_as = (args.as_status if args.as_status
                  and norm(args.as_status) != norm(declared_status) else None)
    return report(f, c, facts, in_scope, deferred, prose, args.json,
                  declared_status=declared_status, audited_as=audited_as, today=today)


if __name__ == "__main__":
    raise SystemExit(main())
