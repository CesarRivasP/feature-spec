# FS-3 — `audit.py --baseline` / `--write-baseline`

Análisis para spec-fs1-6 Phase A, A4-FS-3. Solo análisis: ningún archivo de código fue tocado.
Base medida: `main` @ f5583aa (v1.20.2), tests verdes (`test_audit` 311/311).

## Diagnosis

**Problema.** `e2e-harness` (Hackathon) tiene 7 `DRIFT` preexistentes. Un cambio que añade un octavo
no se distingue de uno que no añade nada: la salida es otra lista de 7-8 líneas y el exit code es
el mismo.

**Cómo decide hoy `main()` / `report()`** (`scripts/audit.py:4549-4682`, `:4685-4835`):

- Exit code = `1 if f.count(CONTRADICTION) else 0`, igual en texto y en `--json`. **`DRIFT` y
  `POLISH` nunca cambian el exit code.** Por eso hoy es imposible detectar un DRIFT nuevo en CI.
  `2` ya significa "no se auditó" (YAML ilegible, `:4799`).
- `--open`, `--index` y `--read-line` retornan antes de correr los checks.
- Los findings son `Findings.items`: dicts `{severity, where, what, fix, check}` (`:86-95`).
  `report()` los ordena por `(severity, check, where)` antes de imprimir.
- Los candidates (`Candidates.by_check`) **no son findings**: no tienen severidad y nunca entran en
  `## Findings` ni en el verdict de severidades (docstring `:97-124`). Un baseline no los toca.
- `ship.py` importa `Findings` y crea los suyos (`scripts/ship.py:46`, `:238`). `triage.py` importa
  `audit` para leer candidates. Ninguno usa `main()`, así que los flags nuevos no los afectan.

**Por qué no basta comparar mensajes crudos: los mensajes son volátiles.** Medido sobre las salidas
reales:

| check | mensaje real (corrida actual) | qué cambia sin que cambie el problema |
|---|---|---|
| 16 | `01-master-plan.md` · `last recorded at _log.md:4 as 7 lines, blob def5678; now 7 lines, blob c2d7bb6` | `_log.md:4`→`:5` al insertar una línea en el log; `now 7 lines, blob c2d7bb6`→`now 8 lines, blob 8491f95` cada vez que se edita el doc sin registrar |
| 16 | `_log.md` · `570 lines, 106KB — past what one read can hold` (interstice) | crece con cada ronda |
| 16 | `` `R10` read `_facts.yml` at 633 lines, blob 857ce36; `R9` left it at 634 lines, blob 882d1ff — edited between rounds `` | conteos y blobs; el id de ronda `R10` **sí** es estable (el log es append-only) |
| 16 | `` 15 entries miss agent, Read:: `R1` (agent), … `` · `last named at _log.md:12 with no line count or blob` | conteo, número de línea |
| 17 | `02b-harness.md` · `579 lines — approaching the split threshold` | cada edición |
| 44 | `01-master-plan.md:73` · ``cites `defects.D4` from `docs/features/interstice/_facts.yml` (now `ValidationException — … `bedrock list-foundation-models` … 11996 bytes …`) and this paragraph does not carry that value`` | `:73` en `where` cuando se edita arriba; el valor del owner entero (≈700 caracteres, con backticks dentro) cada vez que el set hermano lo reescribe |
| 15 / 20 | `` `repo: Hackathon` but this checkout is `h-ea2e521` `` · ``declares `e2e/run.ts`, which does not exist under h-ea2e521/`` | el **nombre del directorio del checkout** va dentro del mensaje |

**Medición sobre historia real.** `git archive` de 4 refs de Hackathon (fba7e66 → ea2e521 →
a157040 → 613bfac) en directorios con el mismo nombre, `audit.py` actual sobre `e2e-harness` e
`interstice`, comparando cada ref con la anterior:

- match por mensaje crudo: **4 "nuevos" falsos** en 3 transiciones (check 16 por conteos/blobs/línea).
- match por fingerprint normalizado (prototipo de §Design): **0 falsos**, y caza los **2 nuevos
  legítimos**: `DRIFT 38 e2e/commit.ts` (e2e-harness @ea2e521) y `DRIFT 16
  docs/features/e2e-harness/_facts.yml` (interstice @ea2e521).
- Colisiones (dos findings de una misma corrida con el mismo fingerprint): **0 de 277** findings
  sobre los 67 fixtures, 0 de 12 en los dos sets reales a HEAD.

Con dirs `h-<ref>` (nombre distinto por ref) el match crudo daba 24-25 falsos por transición, todos
del nombre del checkout en checks 15 y 20 — ver Risks, afecta a `--since`.

## Design

Dos flags y un fingerprint. Nada más en v1.

### Fingerprint

```python
# A finding's identity across runs: what it is about, never the numbers that move
# while it stays the same problem. Each rule is a real message that changed with
# no new problem behind it.
BASELINE_NORMALIZE = (
    # check 44 carries the owner's whole value, backticks included; the finding is
    # "this citation lacks it", whatever it now is
    (re.compile(r"\(now `.*`\)(?= and this paragraph)", re.S), "(now <value>)"),
    # check 16: `blob def5678` -> `blob 8491f95` on every unrecorded edit
    (re.compile(r"\b(?=[0-9a-f]*\d)[0-9a-f]{7,40}\b"), "<blob>"),
    # counts and line numbers: `570 lines, 106KB`, `_log.md:4`, `579 lines`.
    # A number glued to a letter is an id and stays: R10, D4, AC1, v1.2
    (re.compile(r"(?<![\w.])\d+(?:\.\d+)*"), "#"),
)

def finding_fingerprint(x: dict) -> str:
    where = re.sub(r":\d+$", "", x["where"])          # `01-master-plan.md:73`
    what = x["what"]
    for rx, rep in BASELINE_NORMALIZE:
        what = rx.sub(rep, what)
    key = "\x1f".join((x["severity"], x["check"].split()[0], where, what))
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]
```

- Entra: severidad (un DRIFT que pasa a CONTRADICTION es nuevo), número de check (no el nombre,
  que se puede reescribir), `where` sin `:<línea>`, `what` normalizado.
- No entra: `fix` (es consejo en prosa).
- Las reglas viven en una tabla, cada una con su caso real, como `HUMAN_PASS`. Una regla nueva
  llega con su par de mensajes en el test de normalización (abajo).

### Matching: multiconjunto

`Counter` de fingerprints del baseline contra los de la corrida. Por fingerprint, las primeras
`min(baseline, actual)` apariciones son `baseline`, el resto son `new`; lo que sobra en el baseline
es `gone`. Antes de asignar, `f.items` se ordena con la misma clave que usa `report()`; para eso se
extrae `sort_findings(f)` y lo llaman los dos, así el resultado es determinista. Hace falta contar
y no usar un set: dos findings que solo difieren en números colapsan, y si uno de ellos es nuevo
el conteo lo muestra.

### `--write-baseline FILE`

- Corre el audit completo, imprime el reporte normal y escribe FILE. Sale con `0`, o con `2` si no
  puede escribir.
- Formato JSON determinista, sin fecha ni rutas absolutas, para que reescribir sin cambios dé un
  archivo idéntico byte por byte y el diff de un PR muestre solo lo que se movió:

  ```json
  {
    "audit_baseline": 1,
    "feature": "e2e-harness",
    "findings": [
      {"fingerprint": "435061746c4b0c31", "severity": "DRIFT", "check": "44 cross-set value parity",
       "where": "01-master-plan.md:73", "what": "cites `defects.D4` from …"}
    ]
  }
  ```
  `findings` va ordenado por `(fingerprint, where)`, con `indent=2`, `ensure_ascii=False` y `\n`
  final. Se guardan `where` y `what` crudos para que una persona sepa qué aceptó; solo
  `fingerprint` participa en el match.
- Si el baseline graba algún `CONTRADICTION`, avisa por stderr: `baseline records N
  contradiction(s) — with --baseline they stop failing the run`.
- Ubicación recomendada (documentarla, no imponerla): `docs/features/<slug>/_audit-baseline.json`.
  El `_` marca maquinaria del set; check 9 solo mira `.md`, check 16 solo `_log.md`, y
  `--read-line` sin FILE no lo lista.

### `--baseline FILE`

- Texto: `## Findings` muestra **solo los nuevos**, en el formato de siempre. Después viene
  `## Baseline findings (M, from FILE)`, una línea por finding (`where: SEVERITY: what`), recortada
  con el `_truncate_finding_line` que ya existe. **Los findings del baseline se imprimen, no se
  ocultan**: un CONTRADICTION aceptado tiene que seguir viéndose. Si `gone > 0`, una línea más:
  `K baseline finding(s) no longer reported — rewrite with --write-baseline to lock the gain in`.
- El verdict mantiene los conteos totales de severidad y añade el resumen:
  `0 contradictions, 3 drift, 0 polish · 1 new / 2 baseline` (`, 1 gone` si aplica).
- `--json`: cada finding lleva `fingerprint` siempre, tenga o no flag, y `baseline: true|false`
  solo con `--baseline`. La clave top-level `baseline` vale `null` sin flag y, con flag,
  `{"file", "new", "baseline", "gone", "gone_findings": [entradas del archivo]}`.
- Exit code con `--baseline`: **`1` si hay algún finding nuevo con severidad CONTRADICTION o
  DRIFT**, `0` en otro caso, aunque queden CONTRADICTIONs del baseline. Un POLISH nuevo se lista
  pero no falla: tampoco falla hoy, y check 17 lo dispara con solo crecer un doc. Sale con `2` si
  el archivo falta, no es JSON o no trae `audit_baseline: 1`, con un mensaje que nombra el archivo
  y dice cómo escribirlo.
- Candidates, accepted risks, matrix y pending coverage no cambian.

### Combinaciones de flags

- `--baseline` y `--write-baseline` son mutuamente excluyentes (grupo de argparse). Ratchet en dos
  pasos: `--baseline` para revisar y después `--write-baseline` para fijar.
- Cualquiera de los dos junto con `--open`, `--index` o `--read-line` da `ap.error`: esos modos no
  auditan y el flag se ignoraría sin aviso.
- `--write-baseline` con `--as-status` da `ap.error`: grabar como aceptado lo que una vista previa
  inventa sería grabar un estado que no existe. `--baseline` con `--as-status` **sí** se permite y
  muestra qué findings nuevos traería el flip.

### `--since <git-ref>` — evaluado, se difiere

Exigiría materializar otro árbol (`git worktree` o `git archive`), es decir, escribir fuera del spec
dir desde un auditor que hoy solo lee. Además se cruza con la lógica de spec-branch de los checks
18/20/38/43 (`spec_tree`). Y el nombre del directorio del checkout está dentro de los mensajes de
los checks 15 y 20, así que un árbol temporal con otro nombre genera "nuevos" falsos (medido arriba).
Para v1 basta documentar la receta, que cuesta tres comandos:

```sh
git worktree add ../<repo-name>-base <ref>     # same basename as the checkout, see Risks
python3 scripts/audit.py ../<repo-name>-base/docs/features/<slug> --write-baseline /tmp/b.json
python3 scripts/audit.py docs/features/<slug> --baseline /tmp/b.json
```

Hay que reabrirlo si la receta se usa a mano más de un par de veces.

### Funciones nuevas en `audit.py` (junto a `Findings`)

`BASELINE_NORMALIZE`, `finding_fingerprint(x)`, `sort_findings(f)`,
`load_baseline(path) -> Counter | str` (str = mensaje de error para salir con 2),
`write_baseline(f, facts, path)` y `apply_baseline(f, counter) -> (new, base, gone_entries)`, que
marca `x["baseline"]`. `report()` recibe un parámetro `baseline: dict | None` y devuelve el exit
code según la regla de arriba. Todo es stdlib; `hashlib` ya se importa localmente en `git_blob`, se
sube al top.

## Target files

Para el implementador. El único archivo de este análisis es `.gov/analysis/FS-3.md`.

- `scripts/audit.py`: helpers, flags, `report()` y exit code (§Design). Actualizar el docstring del
  módulo (la línea de uso, `:14-16`).
- `tests/test_audit.py`: tests nuevos (§Acceptance), registrados en `main()`.
- `tests/fixtures/baseline-drift/`: fixture nuevo. Copia de `as-status-preview` (`_facts.yml`,
  `_log.md`, `01-master-plan.md`) con `feature: baseline-drift`, `profile: _profile.fixture.yml` y
  cabecera comentada con el caso real (los 7 DRIFT de e2e-harness). Auditado con el
  `_profile.fixture.yml` al lado y `--repo-root` en el padre, da **exactamente 2 DRIFT de check 16
  y ningún otro finding** (verificado a mano: `0 contradictions, 2 drift, 0 polish`).
- `references/mode-audit.md`: un párrafo para `--baseline` / `--write-baseline`, la regla de exit
  code y la receta de `--since`.
- `references/audit-protocol.md`: si lista los flags del script, una línea.
- `SKILL.md`: en la fila `audit` de la tabla de modos, mencionar `--baseline FILE` para sets con
  DRIFT preexistente.
- `README.md`: fila de release con versión **v1.21.0** (minor: flags nuevos, sin cambio de
  comportamiento sin flags) y bump del `git clone --branch`.

## Acceptance

Comando exacto que el implementador tiene que hacer pasar desde la raíz del repo:

```sh
bash -c 'set -u; T=$(mktemp -d); cp -R tests/fixtures/baseline-drift "$T/spec"; cp tests/fixtures/_profile.fixture.yml "$T/"
python3 scripts/audit.py "$T/spec" --repo-root "$T" --write-baseline "$T/b.json" >/dev/null || { echo "write failed"; exit 1; }
printf "\n" | cat - "$T/spec/_log.md" > "$T/l" && mv "$T/l" "$T/spec/_log.md"; echo extra >> "$T/spec/01-master-plan.md"
python3 scripts/audit.py "$T/spec" --repo-root "$T" --baseline "$T/b.json" > "$T/o0"; echo "exit=$?"; tail -1 "$T/o0" | grep -o "0 new / 2 baseline"
echo "# notes" > "$T/spec/notes.md"
python3 scripts/audit.py "$T/spec" --repo-root "$T" --baseline "$T/b.json" > "$T/o1"; echo "exit=$?"; tail -1 "$T/o1" | grep -o "1 new / 2 baseline"
sed -n "/^## Findings/,/^## /p" "$T/o1" | grep -c "^[^ #].*: DRIFT: "
rm -rf "$T"' && for t in tests/test_*.py; do python3 "$t" >/dev/null || exit 1; done && python3 tests/test_audit.py | grep -o "^[0-9]*/[0-9]* assertions passed"
```

Salida esperada (N > 311 e igual en los dos lados):

```
exit=0
0 new / 2 baseline
exit=1
1 new / 2 baseline
1
N/N assertions passed
```

Las líneas 1-2 prueban la normalización: tras correr el log una línea y editar el doc, los dos DRIFT
de check 16 siguen contando como baseline. Las líneas 3-4 son el criterio de FS-3. La línea 5
comprueba que `## Findings` lista solo el nuevo (`notes.md`, check 9).

### Tests a añadir en `tests/test_audit.py`

1. **`baseline_counts_only_new()`** (end-to-end en tempdir, mismo patrón que `log_size_counts_bytes`):
   - precondición: el fixture da exactamente 2 findings, ambos check 16 DRIFT;
   - `--write-baseline` sale con 0 y el archivo tiene 2 entradas; reescribirlo da bytes idénticos;
   - shift volátil (línea antepuesta al log, línea añadida al doc) con `--baseline`: sale con 0,
     verdict `0 new / 2 baseline`;
   - `notes.md` añadido: sale con 1, verdict `1 new / 2 baseline`, y en `--json`
     `baseline == {new: 1, baseline: 2, gone: 0, …}` con un solo finding `baseline: false`, check 9;
   - `gone`: baseline reescrito con los 3 findings y luego se borra `notes.md`: sale con 0, verdict
     `0 new / 2 baseline, 1 gone`.
2. **`baseline_normalization_pairs()`**: tabla de pares con los mensajes reales de §Diagnosis,
   llamando a `audit.finding_fingerprint` directamente.
   - deben coincidir: check 16 `_log.md:4 … 7 lines, blob def5678; now 7 lines, blob c2d7bb6` vs
     `_log.md:5 … now 8 lines, blob 8491f95`; `570 lines, 106KB` vs `701 lines, 103KB`; check 44
     con dos valores `(now `…`)` distintos (uno con backticks internos, el de `defects.D4`); `where`
     `01-master-plan.md:73` vs `:80`.
   - no deben coincidir: `` `R10` read … `` vs `` `R11` read … ``; `defects.D4` vs `defects.D5`;
     mismo texto con DRIFT vs CONTRADICTION; mismo texto con otro archivo en `where`.
3. **`baseline_fingerprints_do_not_collide()`**: en cada fixture de `CASES`, ningún par de findings
   de una misma corrida comparte fingerprint (medido hoy: 0 de 277). Es la guarda contra una regla
   de normalización demasiado codiciosa, igual que `candidates_stay_out_of_findings` vigila su
   contrato sobre todos los fixtures.
4. **`baseline_flag_errors()`**: `--baseline` con archivo inexistente sale con 2 y stderr nombra el
   archivo; JSON sin `audit_baseline` sale con 2; `--baseline` junto a `--write-baseline` sale con 2
   (argparse); `--write-baseline` junto a `--as-status shipped` sale con 2; `--baseline` junto a
   `--open` sale con 2.
5. Sin flags, cada finding de `--json` lleva `fingerprint` y la clave `baseline` es `null`. El exit
   code no cambia: los 311 asserts existentes siguen verdes sin tocarlos.

## Risks

- **La normalización es el riesgo principal.** Si es muy laxa, un problema nuevo con la misma forma
  que uno arreglado en la misma corrida se cancela con él (el conteo no cambia). Si es muy estricta,
  vuelve el ruido que FS-3 quiere quitar. El diseño acepta lo primero, que exige arreglar uno y
  romper otro idéntico salvo números en el mismo commit, a cambio de quitar lo segundo, medido en 4
  falsos de 4 transiciones reales. Lo controlan los tests 2 y 3: cada regla con su par real y
  ninguna colisión entre fixtures.
- **Se borran todos los números sueltos, no solo los conteos.** Un `where` o un `what` que solo
  difiere en un número no pegado a una letra (`AC-3` vs `AC-4`, `[8]` vs `[8, 9]`) cae en el mismo
  fingerprint. Hoy da 0 colisiones; si aparece una, el test 3 la muestra y se resuelve con una regla
  más estrecha en la tabla, no quitando la regla general.
- **El nombre del checkout va en los mensajes de los checks 15 y 20.** Un baseline grabado en un
  checkout `foo` y usado en `foo-2` marca esos findings como nuevos. Hay que documentarlo en
  mode-audit y en la receta de `--since` (mismo basename). Arreglarlo en esos dos mensajes es otro
  issue.
- **Un baseline puede silenciar un CONTRADICTION** (deja de fallar el run). Mitigaciones: aviso por
  stderr al grabarlo, findings del baseline siempre impresos y verdict con los totales. La decisión
  de shippear con un CONTRADICTION ya tiene su sitio (`defects[].accepted` con expiry), y la doc lo
  tiene que decir: el baseline es para heredar DRIFT, no para esquivar G1. `ship.py` no lee
  baselines, así que el gate de ship no cambia.
- **Mensajes reescritos en versiones futuras de `audit.py`** invalidan las entradas afectadas: salen
  como `gone` + `new`. Es lo que se espera de `audit_baseline: 1`; el release note de ese cambio
  tiene que decir "regenerar baselines".
- El `check` del baseline usa solo el número (`"16"`), así que renombrar un check no lo invalida;
  renumerarlo sí.

## Tier

**agy-medium**: ~120 líneas en un archivo de script, más un fixture copiado y 5 tests con todos los
mensajes, reglas y escenarios ya medidos en este análisis; no hay decisiones de diseño abiertas.
