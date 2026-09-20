# Implementación — archivos de configuración no son interfaces

## Parte A — pasos

### Fase 1 — Inicialización

**Archivo:** `package.json` (nuevo)
**Ancla:** archivo nuevo.

**Código:**

```json
{
  "name": "config-fences",
  "private": true,
  "version": "0.1.0",
  "scripts": { "dev": "vite", "test": "vitest run" }
}
```

### Fase 2 — Un manifiesto que la prosa nunca nombra

**Ancla:** `archivo nuevo`

**Qué cambia:**
Configuración de compilación para poder testear ES Modules.

**Código:**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "NodeNext",
    "strict": true
  },
  "include": ["src"]
}
```

### Fase 3 — i18n, primer fence y sus continuaciones

**Código — `es.json`:**

```json
{
  "greeting": "Hola",
  "cancel": "Cancelar"
}
```

y en `"labels"`:

```json
    "pending": "Pendiente"
```

dentro de `"summary"`:

```json
      "count": "{{n}} de {{total}} completados",
      "levels": { "high": "Alta" }
```

### Fase 4 — Los controles: esto sí debe reportarse

El proveedor de facturación responde con un cuerpo que el registro no declara:

```json
{
  "invoice_id": "in_88",
  "amount_cents": 1200
}
```

Y lo entrega contra un endpoint que tampoco está declarado:
`https://abcd.supabase.co/functions/v1/billing-notify`.
