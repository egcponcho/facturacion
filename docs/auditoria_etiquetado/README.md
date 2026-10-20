# Anexos de la auditoría del etiquetado

El documento principal es [`../ETIQUETADO_AUDITORIA.md`](../ETIQUETADO_AUDITORIA.md).
Aquí está la evidencia de cada área, tal como la entregó cada revisión, sobre
`main` en el commit `3b9d8b5`.

| Archivo | Área |
|---|---|
| `L-logica-api.md` | Flujo, reglas de negocio, API, permisos y rendimiento |
| `D-datos.md` | Modelo de datos, integridad, historial y migraciones |
| `I-integraciones.md` | OC, artículos, empaque, packing list, prepacks y unidades |
| `C-codigo-pruebas.md` | Código sin uso, duplicados, dependencias y pruebas |
| `U-ux.md` | Pantallas, recorridos, navegación y propuesta del módulo central |
| `pruebas/` | Pruebas de la auditoría (ver más abajo) |

## Pruebas de la auditoría

- `auditoria_l.py`: 12 pruebas de lógica, API y permisos.
- `auditoria_integracion.py`: pruebas de integración con el empaque.
- `numeracion_cajas.py`: numeración de cajas, en memoria.

Se renombraron sin el prefijo `test_` para que la suite normal no las recoja.
Para correrlas hay que copiarlas a `backend/tests/` con ese prefijo. Usan el
`conftest` y los datos de la demo.

## Notas de lectura

- **Identificadores repetidos:** en `C-codigo-pruebas.md`, la sección 2 numera los
  duplicados D-01 … D-12. El documento principal los cita como **CD-01 … CD-12**
  para no confundirlos con los hallazgos del anexo D.
- **Rutas del área de trabajo:** las rutas `/tmp/…/scratchpad/…` que aparecen en
  los anexos eran del área de trabajo de la sesión. Las pruebas están ahora en
  `pruebas/`.
- **Capturas:** las capturas citadas como `cap/…` no se guardaron en el repositorio
  (pesan unos 7 MB).
