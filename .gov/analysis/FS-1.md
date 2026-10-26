# FS-1 — check 15 `repo:` gives a false CONTRADICTION inside a git worktree

Analysis only. Step ref: spec-fs1-6 Phase A, A1-FS-1. Baseline at f5583aa (v1.20.2):
`for t in tests/test_*.py; do python3 $t || exit 1; done` green, test_audit 311/311.

## Diagnosis

`check_profile_identity` (`scripts/audit.py:3028`) compares the profile's `repo:` with
`repo_root.name` (`scripts/audit.py:3055-3058`). `repo_root` comes from
`repo_root_for` (`scripts/audit.py:137`) = `git rev-parse --show-toplevel`, which in a
linked worktree is the **worktree folder**, not the repository. The folder name of a
worktree is arbitrary (`git worktree add ../fresh-clone-assets`), so a profile written
in the main checkout (`repo: Hackathon`, as `references/intake.md:35` instructs) reads
as foreign in every worktree of the same repo.

Reproduced on a synthetic copy of the evidence shape (repo `Hackathon`, profile
`repo: Hackathon` at `docs/features/`, nothing else changed):

| checkout | today | wanted |
|---|---|---|
| `Hackathon/` (main worktree) | clean | clean |
| `fresh-clone-assets/` (`git worktree add` of Hackathon) | `CONTRADICTION: repo: Hackathon but this checkout is fresh-clone-assets` | clean |
| `copied-elsewhere/` (`cp -R` of Hackathon, own `.git`) | CONTRADICTION | CONTRADICTION (still a different checkout) |

Evidence repo (`/Users/admin/Documents/work/build_future/Hackathon`, read only): sets
`docs/features/interstice` and `docs/features/e2e-harness` both declare
`profile: docs/features/_profile.yml`, which holds `repo: Hackathon`. Audited from the
main checkout today: no check-15 finding. The `fresh-clone-assets` worktree from the
report no longer exists (`git worktree list` shows only main), so the repro above stands
in for it.

Two facts that constrain the fix:

1. **`origin` is not the identity.** Hackathon's remote is `.../Interstice.git` while the
   folder and the profile both say `Hackathon`. Using the remote name would turn every
   existing, correct profile written by `intake.md`'s rule into a CONTRADICTION. Rejected.
2. **The test harness passes `--repo-root <fixture dir>`**, a directory *inside*
   feature-spec's own git repo but not its toplevel (`tests/test_audit.py:680-705`).
   Asking git for identity from there returns feature-spec (or this worktree's folder
   name), which would break `nested-profile` (its `repo:` is the fixture folder name) and
   every check-15 fixture. Git identity may only be used when `repo_root` **is** a git
   toplevel; otherwise the folder name is all there is — the same reasoning
   `repo_root_for`'s `root_is_real` already encodes.

Also checked (`also_check`): `repo_root.name` at `scripts/audit.py:1667`, `:1674`, `:1725`
is **display only** — the label in "resolves outside X/" and "does not exist under X/"
(checks 18 and 20). It compares nothing, and in a worktree the folder name is the correct
label: the paths really do resolve under that folder. No false finding there; leave them
unchanged. `scripts/audit.py:3058` is the only comparison.

## Design

Accept **either** name: the checkout's folder (today's rule, unchanged) **or**, when the
checkout is a linked worktree, the main worktree's name. Strictly additive — everything
that passes today still passes; the only new silence is "linked worktree of a repo whose
main checkout carries the declared name". A copied folder has its own `.git`, is its own
main worktree, and stays a CONTRADICTION.

New helper in `scripts/audit.py`, next to `_git` (`:1601`) or right above
`check_profile_identity`:

```python
def worktree_main_name(repo_root: Path) -> str | None:
    """The main checkout's folder name when `repo_root` is a LINKED worktree, else None.

    `git rev-parse --show-toplevel` in a worktree is the worktree's own folder, and
    that name is whatever `git worktree add` was given. The repository's name lives in
    the shared git dir. Only asked of a real toplevel: the test harness points
    `--repo-root` at fixture dirs inside feature-spec, where git would answer for
    feature-spec instead."""
    top = _git(repo_root, "rev-parse", "--show-toplevel")
    if top is None or Path(top).resolve() != repo_root.resolve():
        return None
    git_dir = _git(repo_root, "rev-parse", "--git-dir")
    common = _git(repo_root, "rev-parse", "--git-common-dir")
    if not git_dir or not common:
        return None
    # both may come back relative to cwd (`.git` in a main checkout)
    gd, cd = (repo_root / git_dir).resolve(), (repo_root / common).resolve()
    if gd == cd:
        return None                      # main checkout, plain clone, or a copy
    return cd.parent.name if cd.name == ".git" else cd.name.removesuffix(".git")
```

- `--git-common-dir` is resolved against `repo_root` instead of using
  `--path-format=absolute`, so it works on git < 2.31 too.
- `cd.name == ".git"` → normal repo, name is its parent folder. A bare repo with worktrees
  (`Hackathon.git/`) → `Hackathon`.
- `.resolve()` on both sides handles macOS `/var` → `/private/var` in temp dirs.

Change in `check_profile_identity` (`scripts/audit.py:3055-3063`): call the helper only
when the folder name already disagrees, so the happy path pays zero subprocesses:

```python
    if declared and not STARTER_PLACEHOLDER.match(declared) \
            and declared != repo_root.name:
        main = worktree_main_name(repo_root)
        if declared != main:
            here = f"`{repo_root.name}`" + (f" (a worktree of `{main}`)" if main else "")
            f.add(CONTRADICTION, prof,
                  f"`repo: {declared}` but this checkout is {here}",
                  ...unchanged fix text..., "15 profile coverage")
```

The message keeps the substring `but this checkout is` that four fixture rejects
(`tests/test_audit.py:226`, `:293`, plus `foreign-profile`) match on. No new flag, no new
check number, no change to `repo_root_for`, to checks 18/20, or to the `app:` half
(which reads paths relative to `repo_root` and is already worktree-correct).

Docs (the implementer's, not this task's): `references/audit-protocol.md:206` states the
rule as "`repo:` ≠ `basename $(git rev-parse --show-toplevel)`"; append "— or, in a linked
worktree, the main checkout's name". `references/intake.md:35` and the `profiles/*.yml`
starters (`repo: <basename of the git root>`) stay as they are: the value to *write* is
still the main checkout's basename. Version bump/README release row per the repo's usual
release flow (v1.20.3, fix).

## Target files

- `scripts/audit.py` — new `worktree_main_name`; the `repo:` comparison in
  `check_profile_identity` (`:3055-3063`). Nothing else.
- `tests/test_audit.py` — one new function test, registered in `main()` next to
  `paths_resolve_on_the_spec_branch` (`:1232`).
- `references/audit-protocol.md` — line 206, one clause.
- `README.md` — release row + clone tag, only if the governor ships this as v1.20.3.

No new fixture directory under `tests/fixtures/`: a worktree cannot be committed as a
fixture (it needs a real `.git` and `git worktree add`), so the case is built in a temp
dir the way `paths_resolve_on_the_spec_branch` (`tests/test_audit.py:899`) already does.
The existing check-15 fixtures (`foreign-profile`, `starter-profile`, `nested-profile`,
`sibling-app`) keep covering the non-toplevel fallback unchanged.

## Acceptance

Command the implementer makes pass (from the repo root):

```sh
for t in tests/test_*.py; do python3 $t || exit 1; done && python3 tests/test_audit.py | tail -1
```

Expected: every suite green, last line `315/315 assertions passed across 67 fixtures`
if the new test is counted as the four assertions below (`total += 4`); `312/312` if it
is registered as one `total += 1` like its neighbours. Either is fine — the count just has
to match what the test registers, with zero failures.

Test to add in `tests/test_audit.py` — `profile_identity_survives_worktrees()`, built in
`tempfile.TemporaryDirectory()` with the existing `git()` helper:

1. `git init -q -b main <tmp>/Hackathon`; write `docs/features/_profile.yml` with
   `repo: Hackathon` (no `app:`), and a minimal set `docs/features/x/` (`_facts.yml` with
   `profile: docs/features/_profile.yml`, one `01-master-plan.md` doc — copy the shape of
   `tests/fixtures/foreign-profile/`); `git add . && git commit`.
2. `git worktree add -q -b wt <tmp>/fresh-clone-assets`.
3. Run `audit.py <spec> --json` **without** `--repo-root` (so `repo_root_for` uses git,
   the real path) and assert:
   - main checkout `Hackathon/docs/features/x` → **no** `15` finding containing
     `but this checkout is` (control: today's behaviour preserved);
   - worktree `fresh-clone-assets/docs/features/x` → **no** such finding (the fix);
   - `shutil.copytree(Hackathon, <tmp>/copied-elsewhere)` (own `.git`, not a worktree) →
     **a** `15` finding containing ``but this checkout is `copied-elsewhere` `` (the
     copy-detection the check exists for still fires);
   - in the worktree, rewrite the profile to `repo: some-other-checkout` → **a** `15`
     finding containing ``(a worktree of `Hackathon`)`` (a worktree does not silence a
     genuinely foreign profile, and the message names both).

Ship gate for the governor (same as this task's baseline):
`for t in tests/test_*.py; do python3 $t || exit 1; done` green, and
`git diff --stat` touching only the target files above.

## Risks

- **Fixture regression** if the toplevel guard is dropped: every `--repo-root <fixture>`
  run would resolve git identity to feature-spec / the worktree folder and
  `nested-profile` would start reporting `but this checkout is`. The existing reject at
  `tests/test_audit.py:226` catches it — keep the guard.
- **Loosening**: a spec copied *into a worktree* of a repo whose main checkout happens to
  share the declared name is now silent. That is the same repository, so it is not the
  defect check 15 hunts.
- **Odd layouts**: submodule worktrees and `--separate-git-dir` clones give a common dir
  not named `.git`; the helper then returns that dir's name, which may not match, and the
  result is today's CONTRADICTION — no new false negative, no worse than now.
- **Cost**: at most 3 extra `git rev-parse` calls, only on a mismatch. Zero on the
  happy path.
- **Test env**: the new test needs `git worktree` (git ≥ 2.5) and writes only to a temp
  dir; it must not run git against feature-spec itself.

## Tier

agy-medium — one helper plus one comparison in a single function, a temp-dir test cloned
from an existing pattern, and the one trap (the toplevel guard) is spelled out above.
