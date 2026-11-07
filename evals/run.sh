#!/usr/bin/env bash
# Run feature-spec's eval suite: each case with the plugin and without it (baseline).
#   evals/run.sh                 # 1 run per case (cheap: check the suite still passes)
#   evals/run.sh --runs 3        # before a release: compare against the previous one
#   evals/run.sh --case sync     # one case (only one --case is honoured)
# Each run is a full Claude Code session on YOUR login: with a claude.ai plan it uses your
# plan's quota (the "$" in the report is an estimate); with an API key it is billed.
# Results go outside the plugin (evals/ is inside the plugin's skill path).
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
out="${FEATURE_SPEC_EVAL_OUT:-${TMPDIR:-/tmp}/feature-spec-evals/$(date +%Y%m%d-%H%M%S)}"
mkdir -p "$out"
exec claude plugin eval "$root" --scaffold \
  --allow-tools Bash Read Grep Glob Edit Write \
  --runs 1 -j 2 --max-cost-usd 10 --threshold 0 --no-publish \
  --output-dir "$out" --json "$out/result.json" "$@"
