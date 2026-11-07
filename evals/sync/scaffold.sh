#!/usr/bin/env bash
# Prepares the run's workspace (the current directory): a git repo holding the fixture
# set under docs/features/. Fixtures come from this plugin's tests/fixtures/.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
fixtures="$here/../../tests/fixtures"
test -d "$fixtures" || { echo "fixtures not found at $fixtures" >&2; exit 1; }
mkdir -p docs/features
cp -R "$fixtures/sync-values" docs/features/sync-values
cp "$fixtures/_profile.fixture.yml" docs/features/_profile.fixture.yml
rm docs/features/sync-values/_facts.new.yml
git init -q
git add -A
git -c user.email=eval@example.invalid -c user.name=eval commit -qm "fixture"
# Most real sets keep _facts.yml out of git: the base is the snapshot `sync.py --init-base`
# wrote when the docs last matched the registry. Then the user edits the registry.
cp docs/features/sync-values/_facts.yml docs/features/sync-values/_facts.synced.yml
cp "$fixtures/sync-values/_facts.new.yml" docs/features/sync-values/_facts.yml
