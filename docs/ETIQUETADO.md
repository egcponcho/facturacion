# Módulo de etiquetado

Diseño, versionado, aprobación y generación de etiquetas con datos reales de
artículos, órdenes de compra y bultos. Este documento describe la arquitectura;
se completa al final del desarrollo con endpoints, pruebas y limitaciones.

## Principios

- **Sin duplicar datos maestros.** Una etiqueta referencia el origen de sus
  datos (artículo, línea de OC, OC, bulto); nunca copia la ficha del producto.
  El artículo solo gana una referencia a su familia de etiquetado.
- **Familia de etiquetado ≠ clasificación arancelaria.** Son catálogos y
  reglas separados; ninguno se usa como sustituto del otro.
- **Un solo motor de dibujo en el servidor.** El mismo diseño produce PDF,
  SVG y PNG con las mismas fuentes (Liberation, incluidas en
  `backend/app/data/fuentes`, licencia SIL OFL 1.1) y las mismas medidas; el
  editor del navegador usa esas fuentes y la vista previa exacta la dibuja el
  servidor.
- **Versiones inmutables una vez aprobadas.** Cada generación guarda la
  versión exacta y una instantánea de los valores usados: volver a descargar
  una etiqueta histórica produce el mismo resultado aunque el diseño o los
  datos cambien después.

## Entidades

| Tabla | Para qué |
|---|---|
| `familias_etiquetado` | Familias propias de la empresa (código, nombre, descripción, orden, activa) y sus campos habituales u obligatorios. |
| `articulos.familia_etiquetado_id` | La familia de cada artículo (variante). |
| `plantillas_etiqueta` | Nombre estable, modalidad de datos (artículo, OC, OC + artículo), unidad por defecto (orden, línea, unidad, bulto…), familia para la que se diseñó y la versión vigente aprobada. |
| `versiones_plantilla` | Versión numerada: diseño completo (JSON validado: medidas, elementos y estilos), estado (borrador, pendiente, aprobada, rechazada, archivada), autor, revisor, fechas, comentarios y resumen de cambios. |
| `asignaciones_etiqueta` | Dónde se aplica una plantilla: general de la organización, familia, producto (estilo), artículo o excepción de una OC; con «predeterminada» para desempatar. |
| `generaciones_etiqueta` / `generacion_items` | Lote generado: quién, cuándo, OC, formato, criterio de cantidad, total; por ítem, plantilla y versión exactas, artículo, línea, familia, cantidad y la instantánea de valores. |

Los elementos del diseño no tienen tabla propia: son una lista tipada dentro
de la versión, validada por el servidor (texto, campo, imagen, código, línea,
rectángulo, elipse).

Todas las tablas son de la organización (aislamiento por RLS en PostgreSQL y
criterio de organización en el ORM).

## Prioridad de plantillas

Para una modalidad y un artículo (o una OC):

1. Excepción asignada a la OC (solo si alguien con permiso la configuró).
2. Asignada al artículo (variante).
3. Asignada al producto (estilo: todas sus variantes).
4. Predeterminada de la familia de etiquetado del artículo.
5. General de la organización.

Solo cuentan plantillas activas con una versión aprobada vigente. En el primer
nivel con candidatas: una sola → se usa; varias → la marcada como
predeterminada; si no hay una inequívoca, el usuario elige. Siempre se informa
el nombre, la familia, la versión y el motivo de la selección.

## Permisos

`etiquetas.ver`, `etiquetas.disenar`, `etiquetas.aprobar`, `etiquetas.asignar`,
`etiquetas.generar`, `etiquetas.familias`. Un proveedor puede generar las
etiquetas de sus propias OC; diseñar, aprobar y asignar es del equipo interno.
El módulo se puede apagar como los demás (Configuración → Empresa → Módulos).
