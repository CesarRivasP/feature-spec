# Master Plan — prose-orphan contracts and endpoints

## 1. Lo que el registro sí conoce

El cuerpo de la petición viaja tal cual. Ninguna línea cercana nombra el contrato
por su id: lo único que ubica este bloque es que sus campos son los del registro.

```json
{ "conversation_id": "c-1", "prompt": "hola", "locale": "es" }
```

### 1.1 Campos que el emisor agrega río abajo

La respuesta de error cuelga de `contracts.chat_request` y sus campos no están en
el registro, porque los agrega el emisor después de salir del cliente. Esta nota
es la que decide si es válido, y el script no puede leerla: el bloque queda
ubicado por la cita, no por sus campos.

```json
{ "error_code": "RATE_LIMITED", "retry_after_s": 30 }
```

El callback entrante es `endpoints.external_get`.
El bot llega por `/webhook/chat-result` y no por otra ruta.

## 2. Lo que solo vive en prosa

El proveedor de facturación responde con un cuerpo que el registro no declara:

```json
{ "invoice_id": "in_88", "amount_cents": 1200, "currency": "eur" }
```

Y lo entrega contra un endpoint que tampoco está declarado:

```http
POST /webhook/billing-callback HTTP/1.1
Content-Type: application/json
```

La función de notificación vive en `https://abcd.supabase.co/functions/v1/notify`.
El panel consulta `/api/v2/invoices` cada cinco minutos.
El correo de recuperación abre `miapp://reset-password?token=abc123`.

## 3. Lo que el barrido no debe reportar

Un host de ejemplo: `https://example.com/api/anything`.
Un enlace de documentación: [MDN fetch](https://developer.mozilla.org/en-US/docs/Web/API/fetch).
El repositorio: https://github.com/CesarRivasP/feature-spec

Un fence en otro lenguaje no es material de interfaz:

```ts
const body = { "ts_only_key": 1 };
await fetch("https://ts-fence.workers.dev/api/x", { body });
```

Y una URL dentro de un fence es el comando, no la interfaz:

```bash
curl -sS https://bash-fence.workers.dev/api/health
```
