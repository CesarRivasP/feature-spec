# Master Plan — absence of signal

## 1. Consultas
No aparece ningun evento de player en 30 dias (`limits.z1_undeclared`); la falla no
llega a Sentry (`limits.z2_no_emitter`) porque ningun path emite esta falla
(`limits.z3_emits_null`). El bucket 4 no registro fallas (`limits.z4_no_sample_rate`)
y el bucket 2 tampoco (`limits.z5_complete`), con
`src/hooks/usePlayerActions.js:399` como unico emisor y `sampleRate: 0.2`; en otra
ventana el bucket 4 registro 312 fallas (`limits.z6_positive`).
