# Handoff log — open-items

## R1 · 2026-10-01 · claude-opus-5 · author
**Read:** `_facts.yml` (43 lines, blob ab1d3e5) · `01-master-plan.md` (5 lines, blob a597091)
**Log read through:** —
**Dispositions:** —
**Edits:** `_facts.yml`, `01-master-plan.md`
**Still open:** —

## R2 · 2026-10-02 · gpt-5 · review
**Read:** `_facts.yml` (43 lines, blob ab1d3e5) · `01-master-plan.md` (5 lines, blob a597091)
**Log read through:** R1
**Findings:**
- R2-F1 doc01 §1 rate limit absent from registry — requests drop under surge
- R2-F2 D3 root cause is wrong — network drop happens on client side
- R2-F3 acceptance item AC2 unverifiable without mock server — needs staging env
**Edits:** none
**Still open:** R2-F1, R2-F2, R2-F3

## R3 · 2026-10-03 · claude-opus-5 · validate
**Read:** `_facts.yml` (43 lines, blob ab1d3e5) · `01-master-plan.md` (5 lines, blob a597091)
**Log read through:** R2
**Dispositions:**
- R2-F1 → **confirmed**. Added missing rate limit handling in facts.
- R2-F2 → **rejected**. Ran tests on 2026-10-03: all passing. Kept as R2-F2-dead so R4 does not re-raise it.
- R2-F3 → **deferred como riesgo aceptado**. Needs mock server on staging cluster.
**Edits:** `_facts.yml`
**Still open:** R2-F3

## R4 · 2026-10-04 · gpt-5 · review
**Read:** `_facts.yml` (43 lines, blob ab1d3e5) · `01-master-plan.md` (5 lines, blob a597091)
**Log read through:** R3
**Findings:**
- R4-F1 memory leak in token bucket under high concurrency — bucket table never prunes
- R4-F2 connection reset on keep-alive timeout — socket closed prematurely
- R4-F3 missing cache-control header in preflight response — OPTIONS cached indefinitely
**Dispositions:** R4-F2, R4-F3 → **confirmed**. Fixed keep-alive and headers in server config.
**Edits:** none
**Still open:** R2-F3, R4-F1
