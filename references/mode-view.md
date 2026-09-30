# `view <slug>` — render the set as one HTML page
`python3 scripts/render.py docs/features/<slug>/ [--open] [--serve [PORT]]` → `<slug>/view.html`, a single self-contained file (CSS/JS inlined, no network).

The view is a **derived artifact**: never edit it, never treat it as a source — edit `_facts.yml` or the docs and re-render. What it adds over reading the markdown is the structure the markdown cannot show: `basis:` as a chip on every claim with its evidence attached, each registry datum marked where it is cited in prose (click either direction), `changes[]` vs `related_docs[]` side by side, `defects[]`/`alternatives[]` as a board with `depends_on` navigable, the `audit` correspondence matrix as a table, and `_log.md` as a timeline with colored dispositions.

It **shows** the same mechanical comparisons `audit` reports — dangling cross-refs, registry datums never cited in prose, and the `references/evidence.md` gates (G1, `measured` with incomplete evidence, `asserted` with no `falsified_by`, `cmd` with regex alternation or a denylist scope). It does not replace `audit`: a view is read by a person, a finding list is acted on.

Needs PyYAML and nothing else; there is no fallback parser, because a registry parsed slightly wrong is the exact failure this skill exists to prevent.

Sharing: the file itself is the unit — send `view.html` to the external owner of doc 03 and it opens offline, with no account and no expiring link. `--serve` binds `127.0.0.1`; `--serve --lan` binds `0.0.0.0` and says so, because a spec set names endpoints, env var names and internal paths.

Contract and invariants: `references/render.md`.

---

Every mode starts by reading `_log.md` from disk and opens its own entry before editing (`SKILL.md` §Modes, `references/handoff.md`). The rules every mode that writes is held to: `references/rules.md`.
