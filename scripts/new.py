#!/usr/bin/env python3
"""new.py — the deterministic half of `new <slug>` (references/mode-new.md).

    python3 scripts/new.py docs/features/<slug> --title TEXT --agent NAME
                           [--dry] [--today YYYY-MM-DD]

Writes `_facts.yml` (minimal), `_log.md` (R1 stub) and `01-master-plan.md` for a
feature that has none. Resolving the profile (step 0), the skeleton (2), the doc 01
headings (4) and the log (6) are mechanical; the siblings decision, the intake
questions, the gap sweep and the prose stay with the agent. Siblings are listed,
never decided.

Refuses (exit 2) when `<dir>/_facts.yml` exists, or when no `_profile.yml` is found
walking up to the git root. Stdlib + PyYAML only.
"""
from __future__ import annotations

import argparse
import datetime
import os
import re
import subprocess
import sys
from pathlib import Path

import yaml

SKILL = Path(__file__).resolve().parent.parent
TEMPLATES = SKILL / "templates"
AUDIT = SKILL / "scripts" / "audit.py"
DOC_PATTERN = SKILL / "references" / "doc-pattern.md"

DOCS = [
    ("01", "01-master-plan.md", "master-plan", "draft"),
    ("02", "02-implementation.md", "implementation", "reviewed"),
    ("02e", "02e-tests-and-e2e.md", "tests", "reviewed"),
    ("03", "03-stakeholder-requirements.md", "stakeholder", "reviewed"),
]


def git_root(start: Path) -> Path | None:
    for p in [start, *start.parents]:
        if (p / ".git").exists():
            return p
    return None


def find_profile(spec: Path, root: Path) -> Path | None:
    """First _profile.yml walking UP from the spec dir to the git root."""
    d = spec
    while True:
        cand = d / "_profile.yml"
        if cand.is_file():
            return cand
        if d == root or d.parent == d:
            return None
        d = d.parent


def profile_ref(profile: Path, spec: Path, root: Path) -> str | None:
    """`profile:` as the registry must spell it. Relative to the spec dir when audit
    (check 15) resolves it from there; else relative to the spec dir's parent or to
    the repo root, the two other bases audit's `profile_path` accepts."""
    sys.path.insert(0, str(SKILL / "scripts"))
    from audit import profile_path
    for base in (spec, spec.parent, root):
        cand = Path(os.path.relpath(profile, base)).as_posix()
        got = profile_path(cand, spec, root)
        if got is not None and got.resolve() == profile.resolve():
            return cand
    return None


def siblings(spec: Path, root: Path, slug: str) -> list[Path]:
    feats = root / "docs" / "features"
    if not feats.is_dir():
        return []
    found = {p for p in feats.glob(f"*{slug}*")}
    found |= {p for p in feats.glob(f"{slug}-*.md")}
    return sorted(p for p in found if p.resolve() != spec.resolve())


def heading_map() -> dict[str, str]:
    """es -> en pairs from the table in doc-pattern.md §Heading language."""
    text = DOC_PATTERN.read_text(encoding="utf-8")
    m = re.search(r"^## Heading language\n(.*?)(?=^## )", text, re.M | re.S)
    out: dict[str, str] = {}
    for line in (m.group(1) if m else "").splitlines():
        if not line.startswith("|") or set(line) <= set("|- "):
            continue
        cells = [c.strip().strip("`") for c in line.strip().strip("|").split("|")]
        if len(cells) == 2 and cells[0] != "es":
            out[cells[0]] = cells[1]
    return out


# Template fragments that are not in the map table but are fixed words of doc 01.
EN_EXTRA = [
    ("**Objetivo:**", "**Goal:**"),
    ("**Estado:**", "**Status:**"),
    ("**Fecha:**", "**Date:**"),
    ("**Owner técnico:**", "**Technical owner:**"),
    ("**Owner externo:**", "**External owner:**"),
    ("**Documentos relacionados:**", "**Related documents:**"),
    ("## 1. Problema", "## 1. Problem"),
    ("## 2. Solución elegida", "## 2. Chosen solution"),
    ("## 3. Arquitectura", "## 3. Architecture"),
    ("### 3.2 Estrategia de rollout", "### 3.2 Rollout strategy"),
    ("### 3.3 Coordinación crítica (si aplica)", "### 3.3 Critical coordination (if any)"),
    ("## 4. Especificación de datos", "## 4. Data specification"),
    ("## 5. Seguridad", "## 5. Security"),
    ("## 6. Costo y escalabilidad", "## 6. Cost and scalability"),
]


def render_doc01(tpl: str, lang: str, title: str, slug: str, today: str) -> str:
    text = (tpl.replace("{{title}}", title)
               .replace("{{status}}", "draft")
               .replace("{{dates.drafted}}", today)
               .replace("{{revision.date}}", today)
               .replace("{{revision.tag}}", "v1")
               .replace("{{revision.note}}", "scaffold by new.py"))
    if lang == "en":
        pairs = list(heading_map().items()) + EN_EXTRA
        for es, en in sorted(pairs, key=lambda p: -len(p[0])):
            text = text.replace(es, en)
    return text


def build_facts(slug: str, title: str, profile_rel: str, today: str, template_header: str) -> str:
    docs = "\n".join(
        f'  - {{ id: "{i}", file: {f}, role: {r}, stage: {s} }}' for i, f, r, s in DOCS)
    return (
        f"{template_header}\n\n"
        f"feature: {slug}\n"
        f"profile: {profile_rel}\n"
        f"title: {yaml.safe_dump(title, default_flow_style=True, width=10**6).splitlines()[0]}\n"
        f"status: draft\n\n"
        f"owners:\n  technical: null\n  external: null\n\n"
        f"dates:\n  drafted: {today}\n  revisions:\n"
        f"    - {{ tag: v1, date: {today}, note: scaffold by new.py }}\n\n"
        f"docs:\n{docs}\n"
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Scaffold _facts.yml, _log.md and doc 01.")
    ap.add_argument("spec_dir")
    ap.add_argument("--title", required=True)
    ap.add_argument("--agent", required=True)
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--today", default=None, metavar="YYYY-MM-DD")
    args = ap.parse_args(argv)

    spec = Path(args.spec_dir).resolve()
    slug = spec.name
    today = args.today or datetime.date.today().isoformat()
    try:
        datetime.date.fromisoformat(today)
    except ValueError:
        print(f"--today: not a YYYY-MM-DD date: {today}", file=sys.stderr)
        return 2

    if (spec / "_facts.yml").exists():
        print(f"refused: {spec / '_facts.yml'} already exists", file=sys.stderr)
        return 2
    root = git_root(spec)
    if root is None:
        print("refused: not inside a git repository", file=sys.stderr)
        return 2
    profile = find_profile(spec, root)
    if profile is None:
        print("no _profile.yml: run intake set A (references/intake.md) first",
              file=sys.stderr)
        return 2
    prof = yaml.safe_load(profile.read_text(encoding="utf-8")) or {}
    lang = str(prof.get("prose_language") or "es").strip().lower()
    profile_rel = profile_ref(profile, spec, root)
    if profile_rel is None:
        print(f"refused: {profile} is not reachable by audit check 15 from {spec}",
              file=sys.stderr)
        return 2

    sibs = siblings(spec, root, slug)

    tpl_facts = (TEMPLATES / "_facts.yml.tpl").read_text(encoding="utf-8")
    header = tpl_facts.splitlines()[0].replace("<slug>", slug)
    facts = build_facts(slug, args.title, profile_rel, today, header)
    log = (TEMPLATES / "_log.md.tpl").read_text(encoding="utf-8")
    log = log.split("<!--", 1)[0].rstrip() + "\n"
    log = log.replace("{{feature}}", slug)
    log = re.sub(r"^## R1 .*$", f"## R1 · {today} · {args.agent} · author", log, flags=re.M)
    log = re.sub(r"^\*\*Read:\*\*.*$", "**Read:** nothing yet", log, count=1, flags=re.M)
    log = re.sub(r"^\*\*Edits:\*\*.*$", "**Edits:** scaffold by new.py", log, count=1, flags=re.M)
    log = re.sub(r"^\*\*Still open:\*\*.*$",
                 "**Still open:** everything `basis: asserted`; doc 01 prose, gap sweep",
                 log, count=1, flags=re.M)
    doc01 = render_doc01((TEMPLATES / "01-master-plan.md.tpl").read_text(encoding="utf-8"),
                         lang, args.title, slug, today)

    files = {"_facts.yml": facts, "_log.md": log, "01-master-plan.md": doc01}

    for s in sibs:
        print(f"sibling: {s.relative_to(root)} — decide: integrate or register "
              f"role: legacy (mode-new.md step 1)")
    print(f"profile: {profile_rel} (prose_language: {lang})")

    if args.dry:
        print(f"dry run — would write in {spec}:")
        for name, body in files.items():
            print(f"  {name} ({body.count(chr(10))} lines)")
        return 0

    spec.mkdir(parents=True, exist_ok=True)
    for name, body in files.items():
        (spec / name).write_text(body, encoding="utf-8")
    print(f"wrote in {spec}:")
    for name in files:
        print(f"  {name}")

    res = subprocess.run([sys.executable, str(AUDIT), str(spec), "--repo-root", str(root)],
                         capture_output=True, text=True)
    lines = [ln for ln in res.stdout.splitlines() if ln.strip()]
    summary = next((ln for ln in reversed(lines)
                    if re.search(r"\d+ contradictions|^clean — ", ln)), None)
    print(f"audit: {summary or '(no summary line; exit %d)' % res.returncode}")
    if re.match(r"[1-9]\d* contradictions", summary or ""):
        print(res.stdout, file=sys.stderr)
        return 1
    ed = subprocess.run([sys.executable, str(AUDIT), str(spec), "--repo-root", str(root),
                         "--edits-line", *[f"{n}=scaffold" for n in files]],
                        capture_output=True, text=True)
    out = [ln for ln in ed.stdout.splitlines() if ln.startswith("**Edits:**")]
    print(out[0] if out else ed.stdout.strip() or ed.stderr.strip())
    return 0


if __name__ == "__main__":
    sys.exit(main())
