#!/usr/bin/env python3
"""render.py's own security boundary, against the two findings Socket raised.

Both are real: `_inline()` built `<a href="...">` from a captured URL with no
scheme check and quotes left unescaped, and `docs[].file` was joined onto
`spec_dir` with no bound, its content READ and embedded in the page. `audit.py`
only ever checks whether a registry path *exists*; `render.py` opens what it
names, which makes an escaping path there a disclosure primitive, not a
false-existence oracle. Each fixture reproduces the real shape of the finding.

    python3 tests/test_render.py [-v]
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RENDER = ROOT / "scripts" / "render.py"
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def render(fixture: str) -> str:
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "view.html"
        proc = subprocess.run(
            [sys.executable, str(RENDER), str(FIXTURES / fixture), "-o", str(out)],
            capture_output=True, text=True)
        if proc.returncode != 0:
            raise AssertionError(f"{fixture}: render.py crashed\n{proc.stderr}")
        return out.read_text(encoding="utf-8")


def check_xss_link() -> list[str]:
    """A `javascript:` link is defused to `#`; a real `https:` link is untouched."""
    html = render("render-xss-link")
    failures = []
    if 'href="javascript:' in html:
        failures.append("render-xss-link: a javascript: URI reached the rendered "
                         "href unchanged")
    if '<a href="#"' not in html:
        failures.append("render-xss-link: the defused link did not render as href=\"#\"")
    if '<a href="https://developer.mozilla.org/es/"' not in html:
        failures.append("render-xss-link: a legitimate https: link was also blocked "
                         "— the allowlist is too narrow")
    return failures


def check_escaping_doc() -> list[str]:
    """`docs[].file` pointing outside `spec_dir` must not be opened at all."""
    html = render("render-escaping-doc")
    failures = []
    if "def build_page" in html:
        failures.append("render-escaping-doc: the content of a file outside the "
                         "spec dir was read and embedded in the page")
    if "resolves outside the spec dir" not in html:
        failures.append("render-escaping-doc: no visible warning for the refused "
                         "docs[] entry — a skipped read must not be silent")
    return failures


def main() -> int:
    verbose = "-v" in sys.argv[1:]
    failures: list[str] = []
    n = 0
    for fn in (check_xss_link, check_escaping_doc):
        f = fn()
        n += 1
        if verbose:
            print(f"{fn.__name__}: {'FAIL' if f else 'ok'}")
        failures += f

    if failures:
        print(f"\n{len(failures)} failure(s):")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"\n{n}/{n} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
