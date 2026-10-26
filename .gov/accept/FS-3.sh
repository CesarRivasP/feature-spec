#!/usr/bin/env bash
# Governor acceptance for FS-3 (from .gov/analysis/FS-3.md §Acceptance). Run from repo root.
set -u
T=$(mktemp -d); cp -R tests/fixtures/baseline-drift "$T/spec"; cp tests/fixtures/_profile.fixture.yml "$T/"
python3 scripts/audit.py "$T/spec" --repo-root "$T" --write-baseline "$T/b.json" >/dev/null || { echo "write failed"; exit 1; }
printf "\n" | cat - "$T/spec/_log.md" > "$T/l" && mv "$T/l" "$T/spec/_log.md"; echo extra >> "$T/spec/01-master-plan.md"
python3 scripts/audit.py "$T/spec" --repo-root "$T" --baseline "$T/b.json" > "$T/o0"; echo "exit=$?"; tail -1 "$T/o0" | grep -o "0 new / 2 baseline"
echo "# notes" > "$T/spec/notes.md"
python3 scripts/audit.py "$T/spec" --repo-root "$T" --baseline "$T/b.json" > "$T/o1"; echo "exit=$?"; tail -1 "$T/o1" | grep -o "1 new / 2 baseline"
sed -n "/^## Findings/,/^## /p" "$T/o1" | grep -c "^[^ #].*: DRIFT: "
rm -rf "$T"
for t in tests/test_*.py; do python3 "$t" >/dev/null || { echo "FAIL $t"; exit 1; }; done
python3 tests/test_audit.py | tail -1 | grep -oE "^([0-9]+)/\1 assertions passed" | sed 's/^[0-9]*\/[0-9]*/N\/N/'
