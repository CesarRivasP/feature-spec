# Master Plan — cmd not runnable
## 1. Problema
El filtro tolera 100 keys, el bucket devuelve 400 con el MIME compuesto, y la
mediana de `.list()` es 0.32 s desde fuera de la región.
