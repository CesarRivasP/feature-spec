#!/usr/bin/env bash
# Prepares the run's workspace (the current directory): a git repo holding the fixture
# set under docs/features/. Fixtures come from this plugin's tests/fixtures/.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
fixtures="$here/../../tests/fixtures"
test -d "$fixtures" || { echo "fixtures not found at $fixtures" >&2; exit 1; }
mkdir -p docs/features
cp -R "$fixtures/log-integrity" docs/features/log-integrity
cp "$fixtures/_profile.fixture.yml" docs/features/_profile.fixture.yml
git init -q
git add -A
git -c user.email=eval@example.invalid -c user.name=eval commit -qm "fixture"
