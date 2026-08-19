# _profile.yml — how THIS repo verifies things.
#
# ONE per repo, not one per feature. Lives at `docs/features/_profile.yml`
# (or wherever the repo keeps its specs). Resolved in `new` step 0, BEFORE
# any doc is scaffolded.
#
# Purpose: every command the skill emits — into `evidence.cmd`, into a
# "Verificación fase N" line, into a log filter — comes from here instead of
# being invented per spec. A command typed by hand into prose is invisible to
# `sync` and drifts; a command sourced from the profile is one datum with one
# home, same discipline as `_facts.yml`.
#
# The registry answers "what is true about this feature".
# The profile answers "how does this repo find out".

# --- identity: which checkout this profile describes ---
repo: <basename of the git root>   # `basename $(git rev-parse --show-toplevel)`
app: null                  # in a monorepo, the app/variant subdir this profile governs. null = whole repo.

stack: <label>             # free label — e.g. android-native, rn-tv, web-baas, ios-swiftui
prose_language: es         # es | en — language of the generated docs' prose AND headings

# --- identifiers used inside commands ---
app_id: <com.example.app>  # package / bundle id, for device commands
log_tag: <TAG>             # tag every diagnostic log line carries (see references/implementable.md)

# --- commands. {app_id} {log_tag} {path} are substituted at use time. ---
# Each one is a real, runnable string. If the repo has no equivalent, write
# `null` — the skill then labels that evidence `[MANUAL]` instead of faking a cmd.
commands:
  tests:        "<test runner cmd>"      # e.g. ./gradlew testDebugUnitTest
  tests_expect: "<line proving pass>"    # e.g. BUILD SUCCESSFUL   — what tests_baseline.value must contain
  lint:         null
  build:        null
  device_log:   null                     # e.g. adb logcat -s {log_tag}:D
  force_stop:   null                     # e.g. adb shell am force-stop {app_id}
  file_tracked: "git ls-files --error-unmatch {path}"
  file_ignored: "git check-ignore -v {path}"

# --- which gap-sweep layers apply on top of the base sweep ---
# Each name resolves to references/gap-sweep-<name>.md. Empty = base sweep only.
gap_sweep_layers: []       # e.g. [android-native] or [web-baas, mobile-tv]

# --- optional: subagent for `audit --deep`. null = Explore / general-purpose. ---
deep_review_agent: null
