# Implementación — doc 02 executability

## Parte A — pasos

- Editar `path/to/component.tsx` y agregar el toast de confirmación.
- Ajustar `…/config.ts` con el flag nuevo.
- Reemplazar el hook en `src/hooks/useX.ts` (o el componente correspondiente).
- Registrar los eventos click, submit, etc.
- Copiar el secreto de Resend desde el dashboard y pegarlo en el entorno.
3. Repetir para el resto de las rutas, análogo a lo anterior.

## Parte B — lo que el barrido no debe reportar

- [MANUAL] Apuntar el registro DNS del dominio al proveedor.
- Editar `src/app/page.tsx` y exportar el componente.

El alcance cubre el router, el layout y el store, y similares. Esto es narrativa
sobre la fase, no un paso que alguien ejecuta, y reportarlo es como una lista de
candidatos deja de leerse.

Un bloque citado como ejemplo de lo que un paso NO debe parecer. Tiene la forma
exacta de un paso, marcador de lista incluido, y aun así está dentro de un fence:

```md
- Copiar la API key desde el dashboard del proveedor, and so on.
```
