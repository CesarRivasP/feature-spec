# FS-2 — cross-set file versions are accounted for by the owner's log

Step: spec-fs1-6 Phase A, A3-FS-2. Analysis only; no code was changed.

## Diagnosis

**Symptom.** Set B cites a file that set A owns (`docs/features/interstice/_facts.yml`,
cited by `docs/features/e2e-harness`). Every time A edits that file and logs the edit in
A's `_log.md`, B's audit reports DRIFT on it until B appends a round that copies A's new
blob. Those rounds change nothing in B. Evidence, Hackathon repo,
`docs/features/e2e-harness/_log.md`:

- R13, R15, R16: `**Edits:** none here. Carried from the app set's R59/R61/R62:
  docs/features/interstice/_facts.yml (… blob dc79fd6 / 8ff3edb / b7c34b0)`. R13 and R15
  say why: "Recorded so the cross-set blob is accounted for."
- R14 is a measurement round, but its only `Edits:` record is the same carry (blob 8035556).
- A's own log already records each of those versions. Example: interstice R62,
  `**Edits:** _facts.yml (2153 lines, blob b7c34b0 — acceptance[AC13])`.

**Reproduced** (copies in the scratchpad, `--repo-root` set to the copy):

- Cut the harness log at `## R13`, then audit e2e-harness. Result:
  `docs/features/interstice/_facts.yml: DRIFT: last recorded at _log.md:216 as 2137 lines,
  blob 9dfa211; now 2153 lines, blob b7c34b0` (check 16).
- Audit interstice on the same copy. Its `_facts.yml` gets no check 16 finding: the owner
  accounts for the version.

**Root cause.** `check_log_integrity` (`scripts/audit.py:3766`) runs two comparisons, and
both read only the audited set's own `_log.md`.

1. **Disk comparison** (`scripts/audit.py:3873-3913`). `recorded[key(name)]` keeps the last
   `Read:`/`Edits:` record of each resolved file and compares it with the bytes on disk. A
   file under a sibling set resolves through `confined(repo_root, name)` like any other
   file, so B's last carry is the only thing that can match A's current blob.
2. **Between-rounds comparison** (`scripts/audit.py:3842-3871`). Entry N's `Read:` is
   compared with the version the earlier entries left. Once B stops carrying, the next B
   round that reads A's `_facts.yml` hits this one instead: `R17 read … at <A's new blob>;
   R12 left it at <old> — edited between rounds`. It is the same false positive in a
   second place, so fixing only (1) moves the empty round from "after A edits" to "the next
   time B reads A".

Check 44 (`check_cross_set_value_parity`, `scripts/audit.py:2820`) is a separate
mechanism. It compares the values cited in B's prose with A's current entries and never
reads a log. FS-2 does not touch it. FS-2 uses the same notion of "owner": the set whose
`_facts.yml` a qualified citation resolves to (`resolve_sibling_entry`, `:2074`).

No other check 16 path is involved:
- The "no line count or blob" branch already exempts files that are not the set's own
  (`ours = target.resolve().parent == spec_dir.resolve() or … _profile.yml`).
- `_log.md` files are never compared (`target.name == "_log.md"`), so B's R1 record of
  `interstice/_log.md` is inert.

## Design

**Rule.** A file that belongs to another set is accounted for by that set's log. B reports
check 16 DRIFT on it only when neither B's last record nor the owner's last record matches
the disk.

**How the owner is identified.** It is a mechanical rule with no new field:

```python
def owning_set(target: Path, spec_dir: Path) -> Path | None:
    """The set a file belongs to, when that set is not this one and keeps a log.
    A set is a directory holding `_facts.yml` — the same thing check 44 resolves a
    qualified citation to. Without a `_log.md` the owner accounts for nothing, and
    the citing set's own record stays the only one."""
    d = target.resolve().parent
    if d == spec_dir.resolve():
        return None
    if (d / "_facts.yml").is_file() and (d / "_log.md").is_file():
        return d
    return None
```

- It covers the owner's registry and its docs: `interstice/02e-tests-and-done.md`, which B
  also records, has the same problem.
- `docs/features/_profile.yml` has no owning set, because `docs/features/` holds no
  `_facts.yml`. It keeps today's behaviour.
- Sets are flat directories, so a file's parent directory is enough. Walking up would let
  a code file under a set-like tree pick an owner by accident.
- An owner with no `_log.md` keeps today's behaviour. B's own record is the only one, and
  carrying stays the way to account for the file.

**Factoring, no behaviour change.**

- Lift `key()` out of `check_log_integrity` as `_record_key(name, spec_dir, repo_root)`.
- Lift the `recorded` loop (`:3877-3889`) as
  `_last_records(text, spec_dir, repo_root) -> dict[key, (raw_name, line, blob, nlines)]`,
  taking the log text with HTML comments already blanked.
- B's own pass calls both helpers with B's directory. The owner pass calls them with the
  owner's directory, so `_facts.yml` in A's log resolves to A's registry, not B's.
- Cache the owner's records per directory inside one call (`owners: dict[Path, dict]`).
- Read only the owner's current `_log.md`, never its archives. The rotation contract
  (`references/handoff.md` §Rotating the log, item 1) makes the first entry after a
  rotation `Read:` every file of the set, so the latest version is always in the current
  log.

**Disk comparison** (`:3890-3913`). When B's last record mismatches the disk and
`owner := owning_set(target, spec_dir)` is not None:

- If the owner's last record of the same resolved file matches the disk (the same
  `nlines` and blob-prefix test), report nothing.
- Otherwise report DRIFT on the same `where`, with a message that names the owner:
  `last recorded at _log.md:<ln> as <n> lines, blob <b>; now <n> lines, blob <b7>;
  owned by <owner rel>, whose _log.md does not account for it either (last there: <fmt>)`.
  Use `(not named there)` when A's log never recorded the file.
  Hint: `the owning set edited it without a round — audit <owner rel> and append the round
  there; this set needs no entry for it`.
- With no owner, keep today's message unchanged. Existing fixtures assert on it
  (`log-spelling-drift`).

**Between-rounds comparison** (`:3855-3869`). Skip the comparison for a file whose
`owning_set` is not None. Still update `known[...]` so that nothing else changes.

- Why skip: this comparison exists to catch an edit made in this set between two of its
  rounds. An edit by the owner between B's rounds is the owner's round, and the owner's
  log checks it.
- What still catches a bad version: the disk comparison above (with the owner fallback)
  catches one that is current, and the owner's own audit catches it on A's side.
- Rejected alternative: accept the read when its version matches any record in the
  owner's log. That needs the owner's archives (`_log-R*.md`) for old versions, which
  means more parsing for a case nothing has hit.

**Decision on "drift in A (and in B?)".** B reports it too, with the owner named:

- A set is audited alone. If B stayed clean while the file it cites matches no log, B
  would audit clean against an unaccounted input. That is the fix_idea's
  "DRIFT only if the owner's log does not explain the current blob either".
- Nothing is duplicated within one report: A's audit reports the file as its own (today's
  message), and B's audit reports it as owned by A.

**Docs.**

- `references/audit-protocol.md` §16, first bullet: add one sentence. A file owned by
  another set (its directory holds `_facts.yml` and `_log.md`) is matched against that
  set's log as well, and only the version neither log accounts for is DRIFT. The
  between-rounds bullet skips such files.
- `references/handoff.md:101`: add the same sentence, plus the convention it retires:
  "never append a round only to carry another set's blob". Cite the real case: e2e-harness
  R13, R15 and R16 were empty rounds.
- Add a `README.md` release row and bump the version in the clone line. This is a patch:
  a false positive in an existing check is removed. The Governor decides whether it ships
  alone or with Phase A.

No new flag and no new check number: this narrows check 16.

## Target files

The implementer edits:

- `scripts/audit.py`: `owning_set`, `_record_key`, `_last_records`, and the two branches of
  `check_log_integrity`.
- `tests/test_audit.py`: two `CASES` rows (see Acceptance).
- `tests/fixtures/cross-set-log/`: a new fixture. It is a mini-repo with
  `_profile.fixture.yml` and three sets under `docs/features/`:
  - `owner-a/` — `_facts.yml`, `01-master-plan.md`, `_log.md`
  - `citer-b/` — `_facts.yml`, `01-master-plan.md`, `_log.md`
  - `owner-c/` — `_facts.yml` only, no log
- `references/audit-protocol.md` (§16), `references/handoff.md` (around line 101).
- `README.md` (release row and clone line).

Not touched: `SKILL.md` (its table does not describe check 16's internals), `render.py`,
`templates/`, `profiles/`, `agents/`.

**Fixture contents.** Blobs are `git hash-object` of the final bytes. Write every file
first and stamp the logs last. A comment edited in `_facts.yml` changes its blob.

- **`owner-a/_log.md`**
  - R1 `Edits:` `_facts.yml` (vA1), `01-master-plan.md` (vM1).
  - R2 `Edits:` `_facts.yml` (vA2, which is the disk version).
  - On disk `01-master-plan.md` is vM2. It was edited after R1 and no round logged it:
    this is the "edit A without logging" case.
- **`citer-b/_log.md`**
  - R1 `Read:` `docs/features/owner-a/_facts.yml` (vA1),
    `docs/features/owner-a/01-master-plan.md` (vM1), `docs/features/owner-c/_facts.yml`
    (a stale version vC0), and B's own files at their disk versions.
  - R2 `Read:` `docs/features/owner-a/_facts.yml` (vA2), which differs from what R1 left.
    This is the between-rounds case.
  - No round carries vA2 into an `Edits:` line.
- **`owner-c/_facts.yml`** is on disk at vC1, not vC0. Owner C has no `_log.md`.

## Acceptance

The implementer makes this exit 0, and it prints the three lines shown below:

```sh
for t in tests/test_*.py; do python3 $t || exit 1; done \
 && python3 tests/test_audit.py | tail -1 | rg -P '^(\d+)/\1 assertions passed' \
 && S=$(mktemp -d) && mkdir -p $S/docs/features \
 && cp -R /Users/admin/Documents/work/build_future/Hackathon/docs/features/{e2e-harness,interstice,_profile.yml} $S/docs/features/ \
 && python3 - $S <<'EOF'
import sys; p = sys.argv[1] + '/docs/features/e2e-harness/_log.md'
t = open(p).read(); open(p, 'w').write(t[:t.index('## R13 ')])
EOF
(python3 scripts/audit.py $S/docs/features/e2e-harness --repo-root $S | rg -c 'interstice/_facts.yml: DRIFT: last recorded' || echo 0)
(python3 scripts/audit.py $S/docs/features/interstice  --repo-root $S | rg -c '^_facts.yml: DRIFT: last recorded'            || echo 0)
```

Expected output:

```
317/317 assertions passed across 69 fixtures
0
0
```

- **Line 1.** The baseline is 311/311 across 67 fixtures, and the six assertions below
  bring it to 317 across 69. If the suite counts fixtures differently, the gate is the
  regex: every assertion passes. Before the fix, line 2 printed `1` (verified in this
  analysis on scratchpad copies).
- **Line 2.** The real case: e2e-harness, with R13–R16 removed, no longer needs them.
- **Line 3.** The owner still accounts for its own file.

Tests to add in `tests/test_audit.py` `CASES` (`(check, text)`; `@` means an exact
`where`):

```python
    # §16 — a file owned by another set (its directory holds _facts.yml and _log.md)
    # is accounted for by that set's log. Real case: e2e-harness R13/R15/R16 were empty
    # rounds appended only to copy interstice's _facts.yml blob.
    ("cross-set-log/docs/features/citer-b",
     [("16", "owned by docs/features/owner-a, whose _log.md does not account for it"),  # 01 edited in A, unlogged
      ("16", "@docs/features/owner-c/_facts.yml")],         # owner with no log: today's rule
     [("16", "@docs/features/owner-a/_facts.yml"),          # A logged vA2; B carries nothing
      ("16", "edited between rounds")]),                     # R2 read vA2 after R1 left vA1
    ("cross-set-log/docs/features/owner-a",
     [("16", "@01-master-plan.md")],                         # the owner reports its own unlogged edit
     [("16", "@_facts.yml")]),
```

- The owner-c expectation must also check that the old message is kept. Assert that its
  `what` does not contain `owned by`. Either add that as a reject on the exact text, or
  reword the expect to `last recorded at _log.md:` and keep the owner-a expect specific.
- `owned by <owner rel>` is the owner directory relative to `repo_root`
  (`docs/features/owner-a`), the same spelling the citation uses.
- Run `python3 tests/test_audit.py` against the fixture before the code change. Exactly
  three assertions must fail, all in the citer-b row:
  - the `owned by` expect, because that message does not exist yet;
  - the `@docs/features/owner-a/_facts.yml` reject, because B's R1 record is stale;
  - the `edited between rounds` reject.

  The owner-c expect and the whole owner-a row must already pass. If anything else fails,
  the fixture is wrong, not the code.

## Risks

- **Owner by directory, not by citation.** The rule treats any file in a sibling set's
  directory as owned, whether or not B cites it with a qualified ref. That is intended, and
  B's R1 already recorded `interstice/02e-tests-and-done.md`. The cost: B can no longer
  claim through its own log that it edited A's file. If B edits A's file (e2e-harness R5
  did, and wrote A's log entry R45), the edit is accounted for only if A's log records it.
  That matches `references/handoff.md` §Delegating a defect to a set of its own, where the
  owner's log is the record.
- **Skipping between-rounds weakens one signal.** If A is edited without a log entry
  between two B rounds and A's log is then fixed, B never sees the gap. A's own audit saw
  it while it was current. Acceptable: the gap is A's to account for.
- **Owner log too big or unparseable.** Reading A's `_log.md` adds one file read per owner
  per audit. interstice's log is 106KB, which is parsed by regex, not loaded as YAML. A
  read error (`OSError`, `UnicodeDecodeError`) must fall back to today's behaviour (B's
  record only), not crash. Add a `try` around the read.
- **Confinement.** The owner's directory comes from a target that already passed
  `confined(base, name)`, and the owner's records resolve through
  `_record_key(name, owner_dir, repo_root)`, which uses the same `confined`. Nothing
  outside the checkout is opened.
- **Message compatibility.** The message is unchanged for the no-owner case,
  so `log-spelling-drift` (`last recorded at _log.md:16 as …`) keeps passing. The owned
  case only appends text after `; now …`, so a `rg 'DRIFT: last recorded'` keeps matching.
- **Existing sets that carry blobs** stay clean: B's own record still matching the disk is
  the first test, so the change removes findings and adds none for them.

## Tier

agy-medium — one function in one file and one hand-stamped fixture; the logic is small, but
the blob-stamped fixture and the two comparison branches need care, which agy-low would
skip.
