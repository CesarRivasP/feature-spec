# Implementable doc 02 — writing for an executor that has no context

Doc 02 is not a summary of the plan. It is the **input to whoever builds it** — increasingly a smaller model or a fresh session with none of the authoring conversation. Anything that reads as a hint instead of an instruction becomes an improvisation.

The test for every line in Parte A: *could someone who has never seen this repo carry it out without asking a question?* If not, it is underspecified.

## The five things that force a question

1. **A path with an escape hatch.** `src/pages/ForgotPassword/index.tsx` (o el componente correspondiente) — resolve it now. Open the directory, name the file, delete the parenthetical.
2. **A name that isn't the final name.** "agregar constante de toast de éxito" → give the identifier, the exported symbol, the file, and the literal string value. Executors invent names, and invented names don't match the tests written in Parte B.
3. **A change with no anchor.** "Agregar un botón en Login" → say where: after which JSX element, inside which conditional, above which existing block. Cite `file.tsx:NN` of the code it goes next to (line numbers drift — quote the anchor line's text too, so it survives).
4. **A behavior with no state.** New UI that depends on data the component doesn't have yet needs the state declared: which `useState`, what type, set where, reset where.
5. **An "etc."/"y similar"/"analogous to".** Enumerate. An executor cannot expand your etc. correctly.

## Structure of a phase

Each `Fase N` carries, in this order:

- **Archivo:** exact path. If new, say `(nuevo)`.
- **Anchor:** the existing code it attaches to — path:line plus the quoted line, or "archivo nuevo, contenido completo abajo".
- **Qué cambia:** prose, one paragraph max.
- **Código:** a fenced block that is *paste-ready*, not illustrative. Real imports, real symbol names from this repo, matching the surrounding style. Mark clearly if a block is a fragment (`// … resto sin cambios`) versus a whole file.
- **Contratos que toca:** which `_facts.yml` keys this phase implements (`limits.rate_limit_resend`, `contracts.X.auth`). This is what lets an executor verify it hasn't dropped a requirement.
- **Verificación fase N:** a command to run or an observable assertion, with the expected output. The command comes from `_profile.yml commands.*` (scoped to this phase's target), the expected output from `commands.tests_expect` or the phase's own assertion — e.g. `<commands.tests> <this phase's test target>` → `<tests_expect>`. Not "verificar que funciona", and never a command invented for this doc.

## Code blocks

- **Existing style wins.** Before writing a snippet, read a sibling file and match: error handling idiom (`.then(({error}) => …)` vs `try/catch`), logging calls, import ordering, whether comments are English or Spanish. A snippet in a foreign style gets pasted verbatim and looks like a graft.
- **Show the current code when you're modifying it.** A "before" of 3-5 real lines plus the "after" removes all ambiguity about where the edit lands. Diff-shaped beats prose-shaped.
- **No pseudocode in Parte A.** If the exact code isn't knowable yet, that's a design hole to close, not a detail to defer.
- **Wire every constant end to end.** A new message string appears in: the constants file that defines it, the map that exposes it, the call site that triggers it, the test that asserts it. If the doc names it once, the executor wires it once and three of the four places stay broken.

## Diagnostic log lines

Instrumentation added to prove or kill a hypothesis is part of the spec, not scaffolding. Doc 02 specifies it like any other code. A device run costs a build, an install, a navigation and an observation — a run whose output cannot settle the question is a run you paid for and learned nothing from.

- **Every line identifies its emitter unambiguously.** Two instances of the same component, or two components of the same family, print the same varying field and become indistinguishable in the log. Include a stable component id or instance uid, not just the field you care about: `<TAG>.mount id=listA row=0`. *Real case (React Native TV):* two different rails both printed `row=0`, and which one emitted it had to be inferred from an unrelated side field — the run answered nothing.
- **Doc 02 shows one sample line per emitter, side by side**, demonstrating they are distinguishable at a glance. If two samples differ only in a value that can legitimately coincide, the tag is not sufficient.
- **Name the filter.** The exact filter that surfaces only these lines and nothing else — `_profile.yml commands.device_log`, with `{log_tag}` substituted. If the profile has `device_log: null`, the spec says where the output is read instead, and that step is `[MANUAL]`.
- **Each line maps to a `defects[].falsified_by`.** A diagnostic line that falsifies nothing is noise; a `falsified_by` with no line behind it is a hypothesis you cannot test. Both directions are audit findings (check 14).
- **Removal is a phase.** `[TEMPORARY INSTRUMENTATION — remove before merge]` in the block itself, plus an explicit removal step in the last phase.

## Tests

Parte B lists *what* to assert; the executor needs *how* this repo asserts it.

- Name the test file path (existing or new) per bullet.
- Include the repo's mock/setup preamble verbatim once — whatever this stack's is (`vi.mock` + `importOriginal` + setup file; `@Before` + MockK/Mockito rules + test runner annotation; a fake DI module). Copy it from a real test in the repo and say which file you copied it from. Inventing a preamble that doesn't match the repo's produces a test that cannot run.
- Name the queries/matchers the repo uses (`screen.getByRole("button", { name: "…" })`, `onView(withId(...))`, `composeTestRule.onNodeWithTag(...)`), so the executor's component exposes the identifier the test looks for. Test and component must be specified together or they won't meet.
- State the exact baseline command and its expected line, both from the profile: `<commands.tests>` → a line containing `<commands.tests_expect>`, with the count from `_facts.yml tests_baseline`.
- **Parity and negative assertions need a `Falla si:` line.** "Idéntico en ambos casos" / "nunca dispara X" is the easiest shape to false-green — the null scenario (mock the same response twice, assert one branch) passes by construction whether or not the code actually discriminates. State the concrete mutation that must turn the test red: which branch to break, which value to change. If you can't name one, the assertion isn't verifying the thing it claims to.
- **Match the assert's layer to the test file's layer.** An assertion about a service/util symbol ("`AuthClient.resendConfirmation` returns cleanly") belongs in that service's test file. Pointing it at a page-level test file forces the executor through the UI to reach it — which collapses it into whatever other row already exercises that same click, producing two tests for one fact.

## Schema / migrations

Applies to any persisted store this stack has — a SQL table, a Room entity, a preferences file, a cache format.

- **The full schema, written out**: fields, types, constraints, and the unique index/key that backs any stated idempotency or dedupe key. Not a description of it.
- **Access control written out**, in this stack's terms — SQL RLS policies (`ENABLE ROW LEVEL SECURITY` plus every policy), Android file/encryption choice, backup flags. "deny-all + service_role" / "we'll encrypt it" is a requirement, not an implementation.
- **The migration from the previous shape**, including what happens to data written by the currently-installed version. A destructive fallback is a stated accepted risk, never a default.
- Say where the file goes and what the repo's naming convention for migrations is.

## What still belongs to a human

Be explicit about the boundary. Steps that need a dashboard, a DNS record, a secret, or a judgment call are labeled `[MANUAL]` / `[OWNER EXTERNO]` right in the phase heading, so an autonomous executor stops there instead of hallucinating a way through.
