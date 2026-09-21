#!/usr/bin/env python3
"""triage.py — rank audit.py's candidates so the human pass reads ten lines, not three documents.

`audit.py` settles every check a program can settle and hands the rest over. Four of
those — 3, 4, 8 and 13 — do not hand over a whole document: they narrow first and emit
**candidates**, mechanical hits whose verdict needs the paragraph around them. The
protocol's own warning on check 4 is the reason: *"Mechanical sweeps over-report here:
verify each hit by eye."*

That narrowing works and it stops one step short. A candidate list with a real finding
and nine exempt shapes still costs a document read to sort out, and the exempt shapes
are named in the protocol in prose: a section number quoted AS TEXT, a changelog clause
enumerating what changed inside one doc, a fence showing a third party's payload, a URL
that is a provider's documented callback. Each is one bounded semantic question over the
surrounding prose — which is what a System One model answers in a batch.

So this script asks one Noul per candidate, batched per document, and sorts the list:

    keep        p >= --keep       likely real; the human reads these first
    uncertain   in between        the judgment call stays a judgment call
    suppressed  p <= --drop       likely one of the protocol's exempt shapes

**A probability is triage, never a verdict.** Nothing here writes a finding, assigns a
severity, or edits a document. `audit.py` owns `## Findings` and every one of them cites
a concrete mismatch; this script only changes the ORDER in which a person reads the
candidates, and suppressed candidates are printed too — a list nobody is told to read is
the failure `HUMAN_PASS` exists to close, and hiding one behind a threshold would rebuild
it one level down.

    python3 scripts/triage.py docs/features/<slug>/ [--checks 4,8] [--json]
    python3 scripts/triage.py --check-setup <spec dir>     what is installed, and the gap

Ranking needs two things — the `typesafe-sdk` package and an API key — and their
absence is a supported state, not an error. Both are checked up front and reported
together, so a machine missing both is told both once instead of round the loop
twice; the run then falls back to the candidates unranked, with one actionable line
per gap. `--no-model` takes that path deliberately, `--require-model` exits 2
instead of taking it, and a failure from the service mid-run falls back the same
way, because the candidates were computed before the call.

**The fallback is a complete answer, not a degraded one.** `audit.py` produces these
candidates offline; ranking only reorders them. What is lost with no key is reading
order — not a check, not a finding, not coverage. Offline is this skill's baseline:
`audit.py` is python3 + PyYAML and `view.html` opens with no network. The model is a
layer over that and never a dependency of it.

What stays in code, permanently: counting, arithmetic, dates, path resolution, line
ranges. Jev 1.13's documented rough edges are exactly those, and `audit.py` already
settles all of them. The split is clean because the model is only ever asked the one
thing a regex cannot ask — whether a reader would *follow* this ref, whether this fence
describes an interface THIS system owns.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    import audit
except ImportError as exc:  # pragma: no cover
    sys.exit(f"cannot import audit.py, which must sit beside this file: {exc}")

KEY_FILE = Path.home() / ".config" / "typesafe" / "api_key"
SKILL_DIR = Path.home() / ".claude" / "skills" / "typesafe-ai"
DEFAULT_KEEP, DEFAULT_DROP = 0.70, 0.30

# Only the candidate generators. A finding is already settled and is none of this
# script's business — re-ranking one would be claiming a severity the script computed
# is negotiable, which it is not.
GENERATORS = {
    "3": lambda facts, prose, in_scope, c: audit.check_contract_shape(facts, prose, c),
    "4": audit.check_cross_refs,
    "8": lambda facts, prose, in_scope, c: audit.check_prose_orphans(facts, prose, c),
    "13": audit.check_doc02_executability,
}


# --------------------------------------------------------------------------
# questions
# --------------------------------------------------------------------------
#
# Every question below is phrased so that **yes means the candidate is a real
# problem**. One direction, throughout: a high probability always means "read this
# one", and no reader or threshold has to remember which way a given check points.
#
# The `criteria.false` text is not decoration — it is where the protocol's exempt
# shapes are stated, in the words the protocol uses. Jev answers the words it is
# given (its documented literalness), so an exemption that lives only in
# audit-protocol.md is an exemption the model has never heard of.

def question_4(line: str, what: str) -> dict:
    return {
        "instructions": {
            "the_line": line,
            "what_the_sweep_found": what,
            "question": "In the document, is this section reference a navigation "
                        "target a reader is being told to go and read?",
        },
        "criteria": {
            "true": "The sentence points the reader somewhere: 'see §3.5', 'per `02` "
                    "§1.1', a table cell naming where something is defined. Following "
                    "the reference is the point of the sentence, so a reference that "
                    "resolves to nothing sends the reader nowhere.",
            "false": "The section number is quoted as text rather than used as a "
                     "pointer: a defect being described ('fixed the cross-ref "
                     "§3.6→§3.5'), an example, or a changelog clause that names one "
                     "document and then enumerates what changed inside it ('`02` "
                     "gained §0.3b, §1.1, §2.5') — narrative about one document, not "
                     "several navigation targets.",
        },
    }


def question_8_fence(line: str, what: str) -> dict:
    return {
        "instructions": {
            "found_at": line,
            "what_the_sweep_found": what,
            "question": "Does this JSON or HTTP block describe an interface that the "
                        "system this document specifies implements, sends, or calls — "
                        "so that both sides must agree on its exact shape?",
        },
        "criteria": {
            "true": "The block is the request body, response, or endpoint contract of "
                    "something this system owns or calls, shown so that an "
                    "implementer matches it field for field.",
            "false": "The block is illustrative rather than contractual: a fragment, an "
                     "error body shown to explain a behaviour, a third party's payload "
                     "this system only reads and does not define, a configuration "
                     "sample, or a data shape internal to one function.",
        },
    }


def question_8_url(line: str, what: str) -> dict:
    return {
        "instructions": {
            "found_at": line,
            "what_the_sweep_found": what,
            "question": "Is this URL an endpoint that the system this document "
                        "specifies calls or exposes?",
        },
        "criteria": {
            "true": "The system sends requests to it, or receives them at it, as part "
                    "of the behaviour being specified.",
            "false": "It is a link rather than an interface: documentation, a "
                     "provider's console or dashboard page, an example, or a third "
                     "party's documented callback URL that belongs in nobody's "
                     "registry.",
        },
    }


def question_3(line: str, what: str) -> dict:
    return {
        "instructions": {
            "found_at": line,
            "what_the_sweep_found": what,
            "question": "The key sets differ between this JSON block and the contract "
                        "it was compared against. Is that difference unexplained?",
        },
        "criteria": {
            "true": "Nothing near the block accounts for the extra or missing fields — "
                    "a reader matching the block against the contract would not know "
                    "which one to trust.",
            "false": "A note near the block explains the difference — most often a "
                     "field the sender injects downstream, outside the client body, or "
                     "a block that deliberately shows only part of the payload and "
                     "says so.",
        },
    }


def question_13(line: str, what: str) -> dict:
    return {
        "instructions": {
            "found_at": line,
            "what_the_sweep_found": what,
            "question": "Doc 02 is read by a builder with no context on how this spec "
                        "was written. Would this line force that builder to stop and "
                        "ask someone a question before they could carry it out?",
        },
        "criteria": {
            "true": "The step leaves something for the reader to resolve: a path that "
                    "is not a real path, an enumeration left open ('etc.', 'y "
                    "similares'), or an action needing a dashboard, secret or decision "
                    "with no `[MANUAL]` / `[OWNER EXTERNO]` label.",
            "false": "The text is not an instruction anybody executes — narrative, a "
                     "description of something that already happened, or an example — "
                     "or the thing that looks unresolved is defined elsewhere in the "
                     "same document and the step is carryable as written.",
        },
    }


def build_question(check: str, line_text: str, what: str) -> dict:
    if check == "4":
        return question_4(line_text, what)
    if check == "3":
        return question_3(line_text, what)
    if check == "13":
        return question_13(line_text, what)
    if check == "8":
        return (question_8_fence if "fence" in what else question_8_url)(
            line_text, what)
    raise KeyError(check)


# --------------------------------------------------------------------------
# collecting
# --------------------------------------------------------------------------

def collect(spec_dir: Path, repo_root_arg: str | None, checks: list[str]):
    """Run ONLY the candidate generators, through audit.py itself.

    Imported, not re-implemented and not shelled out to: the candidate text a reader
    sees here is the same object audit.py printed, by construction. audit.py and
    render.py already share their registry walk for that reason — a check implemented
    twice is the defect this skill exists to prevent, and a candidate *described*
    twice is the same defect wearing a different hat."""
    facts_path = spec_dir / "_facts.yml"
    if not facts_path.is_file():
        sys.exit(f"no _facts.yml in {spec_dir} — not a feature-spec set.")
    facts = audit.load_facts(facts_path)
    repo_root, _ = audit.repo_root_for(spec_dir, repo_root_arg)

    _, in_scope, _ = audit.resolve_stage(facts, spec_dir)
    prose = {d["file"]: d["path"].read_text(encoding="utf-8")
             for d in in_scope if d["exists"]}
    if not prose:
        for path in sorted(spec_dir.glob("[0-9][0-9]*.md")):
            prose[path.name] = path.read_text(encoding="utf-8")

    c = audit.Candidates()
    for check in checks:
        GENERATORS[check](facts, prose, in_scope, c)
    return facts, prose, c


def line_at(text: str, lineno: int) -> str:
    """The candidate's own line, quoted verbatim.

    Deliberately quoted rather than referenced by number. Jev is documented as
    unreliable at counting, so asking it to find line 42 of a document is asking it
    for the one thing it is known to get wrong — and it would fail silently, by
    answering about the wrong line with a confident probability."""
    lines = text.splitlines()
    return lines[lineno - 1].strip() if 0 < lineno <= len(lines) else ""


# --------------------------------------------------------------------------
# asking
# --------------------------------------------------------------------------

class Setup:
    """What is installed, what is configured, and what to do about the gap.

    Checked in one place and reported in full, rather than discovered one
    ImportError at a time: a user missing both pieces should be told both, once,
    not sent round the loop twice. Nothing here reads the key's VALUE into a
    message — only whether it was found and which source it came from."""

    def __init__(self) -> None:
        self.key, self.key_source = self._find_key()
        self.sdk = self._find_sdk()
        self.skill = SKILL_DIR.is_dir()

    @staticmethod
    def _find_key() -> tuple[str | None, str | None]:
        env = os.environ.get("TYPESAFE_API_KEY", "").strip()
        if env:
            return env, "$TYPESAFE_API_KEY"
        if KEY_FILE.is_file():
            stored = KEY_FILE.read_text(encoding="utf-8").strip()
            if stored:
                return stored, str(KEY_FILE)
        return None, None

    @staticmethod
    def _find_sdk() -> bool:
        try:
            import typesafe_sdk  # noqa: F401
        except ImportError:
            return False
        return True

    @property
    def ready(self) -> bool:
        return self.sdk and bool(self.key)

    def missing(self) -> list[str]:
        gaps = []
        if not self.sdk:
            gaps.append("the `typesafe-sdk` package")
        if not self.key:
            gaps.append("a TypeSafe API key")
        return gaps

    def how_to_fix(self) -> list[str]:
        """One actionable line per gap. Written for a person, not a log."""
        steps = []
        if not self.sdk:
            steps.append("install the SDK:  pip install typesafe-sdk")
        if not self.key:
            steps.append(
                "set a key, WITHOUT pasting it into a command (it would land in "
                "your shell history and in this session's transcript). Type it at "
                "the prompt instead:\n"
                '        read -s "?TypeSafe API key: " k && '
                "printf '\\nexport TYPESAFE_API_KEY=%q\\n' \"$k\" >> ~/.zshenv "
                "&& unset k\n"
                f"      or store it in {KEY_FILE} with mode 600.\n"
                "      Never inside this repo: the skill is published.\n"
                "      Key from the TypeSafe console — see "
                "https://docs.typesafe.ai/sdk/python.md")
        if not self.skill and (not self.sdk or not self.key):
            steps.append(
                "optional — the `typesafe-ai` skill is not installed at "
                f"{SKILL_DIR}. Not needed to run this script; it is what teaches "
                "an agent to design the questions.")
        return steps


def rank(prose: dict[str, str], cands, checks: list[str], key: str,
         model: str | None, timeout: float):
    """One call per document: the document is the state, the candidates are the
    questions.

    This is the shape the parallel-questions cookbook measures — a workload where one
    large document dominates every request, so sending it once with N questions rather
    than N times with one is where the saving is. Independent questions cannot see one
    another's answers, which is what makes them safe to batch: no candidate's verdict
    can be contaminated by the candidate above it."""
    from typesafe_sdk import Noul, TypeSafeClient

    by_doc: dict[str, list[dict]] = {}
    for check in checks:
        for cand in cands.by_check.get(check, ()):
            doc, _, raw_line = cand["where"].rpartition(":")
            if doc not in prose:
                continue
            lineno = int(raw_line) if raw_line.isdigit() else 0
            by_doc.setdefault(doc, []).append(
                {"check": check, "where": cand["where"], "what": cand["what"],
                 "line": lineno, "text": line_at(prose[doc], lineno)})

    ranked: list[dict] = []
    tokens = 0
    started = time.monotonic()
    with TypeSafeClient(api_key=key, timeout=timeout) as client:
        for doc, items in by_doc.items():
            questions = {
                f"q{i}": Noul(**build_question(it["check"], it["text"], it["what"]))
                for i, it in enumerate(items)
            }
            state = {"document_name": doc, "document_text": prose[doc]}
            resp = client.system_one(state=state, questions=questions, model=model)
            tokens += ((resp.usage.input_tokens or 0)
                       + (resp.usage.output_tokens or 0))
            for i, it in enumerate(items):
                answer = resp.answers.get(f"q{i}")
                it["p"] = float(answer.noul) if answer is not None else None
                ranked.append(it)
    return ranked, tokens, time.monotonic() - started, len(by_doc)


# --------------------------------------------------------------------------
# output
# --------------------------------------------------------------------------

def bucket(p: float | None, keep: float, drop: float) -> str:
    if p is None:
        return "uncertain"
    if p >= keep:
        return "keep"
    if p <= drop:
        return "suppressed"
    return "uncertain"


def passthrough(cands, checks: list[str], why: str,
                steps: list[str] | None = None) -> int:
    """The fallback, and it is a complete answer rather than a degraded one.

    Ranking reorders a list; it never produced it. `audit.py` computes these
    candidates offline and they are the same candidates either way, so what is
    lost here is the reading order — not a check, not a finding, not coverage.
    Saying so plainly matters: a fallback that reads like a failure gets treated
    as one, and the offline path is this skill's baseline."""
    print("# triage — candidates, unranked\n")
    print(f"{why}\n")
    if steps:
        print("To enable ranking:\n")
        for i, step in enumerate(steps, 1):
            print(f"  {i}. {step}")
        print()
    print("Nothing is missing from the list below — `audit.py` computed it offline "
          "and ranking only reorders it. Candidates in its order:\n")
    total = 0
    for check in checks:
        items = cands.by_check.get(check, ())
        if not items:
            continue
        print(f"  check {check}")
        for cand in items:
            total += 1
            print(f"      · {cand['where']}: {cand['what']}")
        print()
    if not total:
        print("  (no candidates)")
    return 0


def report(ranked: list[dict], tokens: int, elapsed: float, calls: int,
           keep: float, drop: float, as_json: bool) -> int:
    for it in ranked:
        it["bucket"] = bucket(it.get("p"), keep, drop)
    ranked.sort(key=lambda it: -(it.get("p") if it.get("p") is not None else 0.5))

    if as_json:
        print(json.dumps({"thresholds": {"keep": keep, "drop": drop},
                          "usage": {"tokens": tokens, "seconds": round(elapsed, 2),
                                    "calls": calls},
                          "candidates": ranked}, indent=2, ensure_ascii=False))
        return 0

    groups = {b: [it for it in ranked if it["bucket"] == b]
              for b in ("keep", "uncertain", "suppressed")}
    print("# triage — candidates ranked, never judged\n")
    print(f"{len(ranked)} candidates · {calls} call(s) · {tokens} tokens · "
          f"{elapsed:.1f}s\n")

    headings = {
        "keep": ("keep — likely real", "Read these first."),
        "uncertain": ("uncertain — your judgment",
                      "The model is between thresholds. These are the ones it has "
                      "nothing useful to say about."),
        "suppressed": ("suppressed — likely one of the protocol's exempt shapes",
                       "Listed, not dropped. A threshold that hides a candidate "
                       "rebuilds the silent-skip failure one level down."),
    }
    for name in ("keep", "uncertain", "suppressed"):
        items = groups[name]
        title, blurb = headings[name]
        print(f"## {title} ({len(items)})\n")
        if not items:
            print("  (none)\n")
            continue
        print(f"{blurb}\n")
        for it in items:
            p = "  ?  " if it.get("p") is None else f"{it['p']:.2f}"
            print(f"  [{p}] check {it['check']:<3} {it['where']}: {it['what']}")
        print()

    print("A probability is triage, not a verdict. Severity, and the concrete "
          "mismatch a finding must cite, stay with `audit.py` and the human pass.")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("spec_dir")
    ap.add_argument("--repo-root", default=None,
                    help="anchor/file resolution root (default: git toplevel)")
    ap.add_argument("--checks", default="4,8",
                    help="candidate checks to rank (default: 4,8)")
    ap.add_argument("--keep", type=float, default=DEFAULT_KEEP)
    ap.add_argument("--drop", type=float, default=DEFAULT_DROP)
    ap.add_argument("--model", default=None)
    ap.add_argument("--timeout", type=float, default=60.0)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--no-model", action="store_true",
                    help="skip ranking even when the SDK and key are present — "
                         "the offline path, chosen rather than fallen into")
    ap.add_argument("--require-model", action="store_true",
                    help="exit non-zero instead of falling back, for a caller that "
                         "needs to know ranking did not happen")
    ap.add_argument("--check-setup", action="store_true",
                    help="report what is installed and configured, then exit")
    args = ap.parse_args(argv)

    if args.check_setup:
        setup = Setup()
        print("typesafe-sdk installed :", "yes" if setup.sdk else "no")
        print("API key found          :",
              setup.key_source if setup.key else "no")
        print("typesafe-ai skill      :",
              str(SKILL_DIR) if setup.skill else "not installed (optional)")
        print("\nranking:", "available" if setup.ready else "unavailable")
        for i, step in enumerate(setup.how_to_fix(), 1):
            print(f"  {i}. {step}")
        return 0 if setup.ready else 1

    checks = [c.strip() for c in args.checks.split(",") if c.strip()]
    unknown = [c for c in checks if c not in GENERATORS]
    if unknown:
        sys.exit(f"no candidate generator for check(s): {', '.join(unknown)}. "
                 f"Known: {', '.join(GENERATORS)}")
    if not args.drop <= args.keep:
        sys.exit("--drop must not exceed --keep")

    spec_dir = Path(args.spec_dir).resolve()
    _, prose, cands = collect(spec_dir, args.repo_root, checks)

    if args.no_model:
        return passthrough(cands, checks,
                           "Ranking skipped: `--no-model` was passed. Nothing was "
                           "sent anywhere.")

    setup = Setup()
    if not setup.ready:
        gaps = " and ".join(setup.missing())
        why = (f"Ranking unavailable — this machine is missing {gaps}. "
               "`audit.py` runs offline and so does the human pass, so the "
               "candidates below are complete.")
        if args.require_model:
            sys.stderr.write(f"Ranking unavailable — this machine is missing "
                             f"{gaps}, and `--require-model` was passed.\n\n")
            for i, step in enumerate(setup.how_to_fix(), 1):
                sys.stderr.write(f"  {i}. {step}\n")
            return 2
        return passthrough(cands, checks, why, setup.how_to_fix())

    # A key that is present is not a key that works, and a network that resolves is
    # not a network that answers. Everything past this point is someone else's
    # service, so a failure there falls back to the offline list rather than
    # killing the audit — the candidates were already computed before the call.
    from typesafe_sdk import TypeSafeError
    try:
        ranked, tokens, elapsed, calls = rank(
            prose, cands, checks, setup.key, args.model, args.timeout)
    except TypeSafeError as exc:
        why = (f"Ranking failed and was skipped: {type(exc).__name__}: {exc}. "
               "The candidates below are complete — they were computed offline "
               "before the call.")
        if args.require_model:
            sys.stderr.write(why + "\n")
            return 2
        return passthrough(cands, checks, why)
    return report(ranked, tokens, elapsed, calls, args.keep, args.drop, args.json)


if __name__ == "__main__":
    raise SystemExit(main())
