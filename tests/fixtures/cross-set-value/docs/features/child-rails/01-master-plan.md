# Master Plan — child rails

## 1. Paridad limpia
El rendimiento base viene de `docs/features/parent-tiles/_facts.yml limits.fps_per_tile` y rinde 24 fps por tile.

## 2. Deriva de valor
La configuracion asume `docs/features/parent-tiles/_facts.yml limits.fps_per_tile` pero presupuesta 30 fps por tile.

## 3. Clave inexistente
La reserva consulta `docs/features/parent-tiles/_facts.yml limits.nonexistent` para dimensionar el buffer.
