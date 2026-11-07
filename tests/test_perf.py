#!/usr/bin/env python3
"""Speed, measured on a set big enough to feel it, and held to the old output.

A real 307 KB registry took audit.py 5.6 s: 119 `git show` forks, one alternation of
every datum value run over ~17.8k HTML chunks, pure-Python YAML. This test GENERATES a
set of that size (nothing big is committed): ~1500 defects, ~800 limits, 16 docs of
~5k lines citing them, and a `tracking.branch` that is not HEAD so the code is read
through git. It runs audit.py twice — `FEATURE_SPEC_SLOW=1` (the three paths as they
were) and the default — prints both wall times, and asserts the output is byte for
byte the same, text and `--json`, plus `--doc-index`. No timing assertion: a clock is
flaky, identity is not.

It also breaks a YAML on purpose and asserts the `line:col` report does not depend on
which loader ran.

    python3 tests/test_perf.py
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AUDIT = ROOT / "scripts" / "audit.py"
N_DEFECTS, N_LIMITS, N_DOCS, N_CODE = 1500, 800, 16, 100


def git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", "-c", "user.name=perf", "-c", "user.email=perf@example.com",
                    *args], cwd=cwd, check=True, capture_output=True)


def generate(repo: Path) -> Path:
    """-> the spec dir. `main` carries the spec only; `feat/perf` carries the code, and
    the checkout stays on `main`, so every anchor is read from the branch via git."""
    git(repo, "init", "-q", "-b", "main")
    spec = repo / "spec"
    spec.mkdir()
    (repo / "README.md").write_text("perf fixture\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "base")
    git(repo, "branch", "feat/perf")
    git(repo, "checkout", "-q", "feat/perf")
    src = repo / "src"
    src.mkdir()
    for i in range(N_CODE):
        body = "".join(f"export const v{i}_{n} = {i * 1000 + n};\n" for n in range(60))
        (src / f"f{i:03d}.ts").write_text(body)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "code")
    git(repo, "checkout", "-q", "main")

    lines = ["feature: perf-large", "status: implementing",
             "profile: ../_profile.fixture.yml", "defects:"]
    for d in range(N_DEFECTS):
        lines.append(
            f"  - {{ id: D{d}, role: contributing, basis: asserted, status: open,\n"
            f"      claim: 'el modulo m{d:04d} corta en {10000 + d * 7} objetos',\n"
            f"      falsified_by: 'una corrida de m{d:04d} con mas de {10000 + d * 7}' }}")
    lines.append("limits:")
    for n in range(N_LIMITS):
        lines.append(f"  l{n}: {{ max_items: {20000 + n * 3}, window: 'ventana-{n:04d}' }}")
    lines += ["acceptance:",
              "  - { id: AC1, item: 'se respeta el cap', status: approved }",
              "tracking:", "  issues: []", "  pr: null", "  milestone: null",
              "  branch: feat/perf", "docs:"]
    for k in range(N_DOCS):
        lines.append(f'  - {{ id: "{k + 1:02d}", file: {k + 1:02d}-doc.md, '
                     f'role: {"master-plan" if k == 0 else "tests"}, stage: draft }}')
    (spec / "_facts.yml").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (repo / "_profile.fixture.yml").write_text(
        (ROOT / "tests" / "fixtures" / "_profile.fixture.yml").read_text(encoding="utf-8"))

    per_doc = N_DEFECTS // N_DOCS
    for k in range(N_DOCS):
        out = [f"# Doc {k + 1:02d}", ""]
        for j in range(per_doc):
            d = k * per_doc + j
            a = (d % N_CODE)
            out += [f"## Seccion {k + 1:02d}.{j}", "",
                    f"Cubre D{d}: el modulo m{d:04d} corta en {10000 + d * 7} objetos; "
                    f"el limite ventana-{d % N_LIMITS:04d} manda ({20000 + (d % N_LIMITS) * 3}).",
                    f"Anclado en `src/f{a:03d}.ts:{1 + d % 70}` y en `src/f{(a + 1) % N_CODE:03d}.ts:10`.",
                    ""]
        (spec / f"{k + 1:02d}-doc.md").write_text("\n".join(out), encoding="utf-8")
    (spec / "_log.md").write_text("# Log\n", encoding="utf-8")
    return spec


def audit(spec: Path, repo: Path, extra: list[str], slow: bool) -> tuple[float, int, str, str]:
    env = dict(os.environ)
    env.pop("FEATURE_SPEC_SLOW", None)
    if slow:
        env["FEATURE_SPEC_SLOW"] = "1"
    t = time.perf_counter()
    r = subprocess.run([sys.executable, str(AUDIT), str(spec), "--repo-root", str(repo),
                        "--today", "2026-11-06", *extra],
                       capture_output=True, text=True, env=env)
    return time.perf_counter() - t, r.returncode, r.stdout, r.stderr


def broken_yaml_identity(failures: list[str]) -> None:
    """A malformed registry reports the same `file:line:col` under either loader."""
    with tempfile.TemporaryDirectory() as tmp:
        spec = Path(tmp) / "set"
        spec.mkdir()
        cases = {
            "flow-comma": "feature: x\ndefects:\n  - { id: D1, basis: asserted absence: true }\n",
            "indent": "feature: x\nlimits:\n  a: 1\n   b: 2\n",
            "unclosed": "feature: x\nclaim: 'never closed\nother: 1\n",
            "tab": "feature: x\nlimits:\n\ta: 1\n",
        }
        for name, text in cases.items():
            (spec / "_facts.yml").write_text(text, encoding="utf-8")
            got = [audit(spec, Path(tmp), [], slow) for slow in (True, False)]
            (_, rc_a, out_a, err_a), (_, rc_b, out_b, err_b) = got
            if (rc_a, out_a, err_a) != (rc_b, out_b, err_b) or rc_a != 2 \
                    or "not valid YAML" not in err_a:
                failures.append(f"broken YAML `{name}`: reports differ or not reported\n"
                                f"  slow:{rc_a} {err_a!r}\n  fast:{rc_b} {err_b!r}")
            else:
                print(f"  ok  broken YAML `{name}`: {err_a.splitlines()[0]}")


def main() -> int:
    failures: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp) / "repo"
        repo.mkdir()
        spec = generate(repo)
        size = (spec / "_facts.yml").stat().st_size
        doc_lines = sum(len(p.read_text().splitlines()) for p in spec.glob("[0-9]*-doc.md"))
        print(f"generated: registry {size // 1024} KB, {N_DOCS} docs, {doc_lines} lines, "
              f"{N_CODE} files on feat/perf")
        total = {True: 0.0, False: 0.0}
        for label, extra in (("text", []), ("json", ["--json"]), ("doc-index", ["--doc-index"])):
            runs = {slow: audit(spec, repo, extra, slow) for slow in (True, False)}
            for slow, (secs, _rc, _out, _err) in runs.items():
                total[slow] += secs
            (_, rc_a, out_a, err_a), (_, rc_b, out_b, err_b) = runs[True], runs[False]
            ok = (rc_a, out_a, err_a) == (rc_b, out_b, err_b) and rc_a in (0, 1) and out_a
            print(f"  {'ok ' if ok else 'FAIL'} {label:9} before {runs[True][0]:.2f}s  "
                  f"after {runs[False][0]:.2f}s  output {len(out_a)} bytes identical: {bool(ok)}")
            if not ok:
                failures.append(f"{label}: slow and fast output differ "
                                f"(rc {rc_a}/{rc_b}) {err_a[-300:]!r} {err_b[-300:]!r}")
        print(f"  total  before {total[True]:.2f}s  after {total[False]:.2f}s  "
              f"x{total[True] / max(total[False], 1e-9):.1f}")
    broken_yaml_identity(failures)
    for f in failures:
        print(f"  FAIL {f}")
    print("perf: output identical on every path" if not failures
          else f"perf: {len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
