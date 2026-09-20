# Master Plan — contract metadata is not a field

## 1. El caso motivador: coincidencia perfecta reportada como diferencia

`contracts.queue_job` declara sus campos bajo `fields:` y lleva un `note:`
hermano. El fence de abajo tiene exactamente esos tres campos y nada más.

```json
{
  "job_type": "generate_report",
  "payload": {},
  "dedupe_key": "sha256(owner_id + job_type + payload)"
}
```

Dos claves descriptivas en vez de una, para que el barrido no dependa de que sea
solo `note:`.

```json
{
  "job_id": "j-1",
  "result_url": "https://storage.example.com/r/j-1.txt"
}
```

## 2. Dentro de un payload, `label` es un campo

`contracts.order_row.columns` tiene tres columnas y una de ellas se llama
`label`. Un fence que la trae **no** tiene un campo de más; le falta
`created_at`.

```json
{ "id": "11111111-2222-3333-4444-555555555555", "label": "pagar el alquiler" }
```

## 3. Una entrada sin contenedor de payload ES el payload

`contracts.flat_entry` no declara `fields:` ni `columns:`: sus propias claves
son los campos. Nada en ella puede filtrarse, así que la ausencia de `label`
aquí sí es una diferencia real.

```json
{ "flat_id": "66666666-7777-8888-9999-000000000000" }
```
