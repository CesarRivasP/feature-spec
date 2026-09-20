# Implementación — pasos que salen del checkout, y los que no

## Parte A — pasos

### A.1 Los que sí salen

1. En Supabase Dashboard → SQL Editor, correr la migración.
2. Copiar el Signing Secret del webhook de Resend y cargarlo en el entorno.
3. Abrir la consola de Anthropic y leer el consumo del día.

### A.2 Los que nombran la misma palabra sin salir a ningún lado

- **Dashboard:** mostrar los totales por categoría.
- Navegar a la semana siguiente en el Dashboard.
- Crear un perfil de prueba y pegar un secret falso para ver el error.
- Restaurar la red y forzar el overlay bloqueando sólo DNS.

### A.3 Los que ya declaran que salen

- [MANUAL] Apuntar el registro DNS del dominio al proveedor.
- [OWNER EXTERNO] Entregar la API key de producción por gestor de secretos.
