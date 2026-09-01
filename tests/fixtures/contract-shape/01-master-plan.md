# Master Plan — contract shape

## 1. Bloques que difieren del registro

Un campo que el emisor agrega río abajo. Es válido **si una nota lo explica**, y
esa nota es lo único que el script no puede leer — por eso sale como candidato:

```json
{ "conversation_id": "c-1", "prompt": "hola", "locale": "es", "trace_id": "t-9" }
```

Un campo renombrado, que es la forma en que un contrato se rompe sin que nadie
lo note:

```json
{ "job_id": "j-1", "delivered_url": "https://cdn/x.png" }
```

Un campo que falta:

```json
{ "form_alpha": 1, "form_beta": 2 }
```

## 2. Bloques que el barrido no debe reportar

El mismo cuerpo con las claves en otro orden. Un contrato es un conjunto de
campos, no una lista ordenada:

```json
{ "echo_beta": 2, "echo_alpha": 1 }
```

La respuesta ok, que debe compararse contra `response_ok` y no contra el cuerpo
de la petición:

```json
{ "chat_status": "ok", "chat_href": "https://cdn/r.json" }
```

Un campo declarado cuyo interior el contrato no describe. Las claves anidadas no
son campos de este bloque:

```json
{ "job_id": "j-2", "output_url": { "href": "https://cdn/y.png" } }
```

Un bloque con comentarios, elipsis y una coma final: no parsea como JSON y aun
así tiene una forma:

```json
{
  "tolerant_key": "x",
  "tolerant_other": [1, 2],
  // …
}
```

Un bloque que no comparte ningún campo con ningún contrato no tiene contra qué
compararse: es un huérfano de prosa, y eso es el check 8, no este:

```json
{ "unrelated_alpha": 1, "unrelated_beta": 2 }
```

Un fence en otro lenguaje no es material de interfaz:

```ts
const payload = { "ts_shape_key": 1 };
```
