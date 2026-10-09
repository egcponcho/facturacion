# Sistema de diseño

Reglas y piezas comunes de la interfaz. Los tokens viven en
`frontend/src/styles.css` y los componentes base en
`frontend/src/componentes/`. Una pantalla nueva se arma con estas piezas. No
se crean variantes propias de botones, pestañas, chips, tablas ni ventanas.

## Tokens

| Grupo | Tokens | Uso |
|---|---|---|
| Color | `--tinta`, `--tinta-2`, `--tinta-3`, `--papel`, `--superficie`, `--superficie-2`, `--linea`, `--linea-suave`, `--acento*`, `--ok*`, `--aviso*`, `--error*`, `--info*` | Mismos nombres en tema claro y oscuro; nunca colores fijos en las vistas. |
| Espaciado | `--e-1` (4) · `--e-2` (8) · `--e-3` (12) · `--e-4` (16) · `--e-5` (20) · `--e-6` (24) · `--e-8` (32) | Márgenes, rellenos y separaciones: múltiplos de 4 px. |
| Tipografía | `--t-xs` · `--t-sm` · `--t-md` · `--t-lg` · `--t-xl` · `--t-2xl`; `--mono` | Base de 14 px (Inter); números tabulares en tablas. |
| Forma | `--radio` (8), `--radio-panel` (12), `--radio-pildora` | Controles, paneles y etiquetas. |
| Sombra | `--sombra`, `--sombra-media`, `--sombra-flotante` | Paneles, menús y ventanas. |
| Puntos de quiebre | 600 · 720 · 900 · 1100 px | 720 px es el corte principal a celular. CSS no admite variables en `@media`: se usan estos valores y no otros. |

Utilidades en lugar de estilos en línea: `mt-0`, `mt-chico`, `mt`, `mb-2`,
`mb-3`, `mb-4`, `ms-0`, `separar`, `col-completa`, `texto-error`,
`sin-sombra`, `nowrap`, `mono`, `relleno-chico`, `fila-flex`, `oculto-visual`.
Un `style` en línea solo se justifica cuando el valor es dinámico (un ancho
calculado, un color de una serie).

## Controles

| Necesidad | Pieza | Nota |
|---|---|---|
| Acción principal / secundaria / sin borde / destructiva | `.btn.btn-primario`, `.btn`, `.btn.btn-fantasma`, `.btn.btn-peligro` | Una sola acción principal por zona. Las acciones raras van en `MasOpciones`. |
| Pestañas de primer nivel (secciones de un documento) | `.pestanas` + `.pestana[aria-selected]` | Con `role="tablist"` / `role="tab"`. |
| Pestañas de segundo nivel o elegir una vista / filtro | `.pestanas-pildora` + `.pildora`, `.segmentos` + `.segmento[aria-pressed]` | Un solo estilo para las dos. |
| Estado de un documento | `EstadoBadge` (`nucleo/estados.js`) | Textos y tonos de los estados en un solo lugar. |
| Etiqueta informativa | `.etiqueta` (`.ok`, `.aviso`, `.error`, `.info`, `.acento`) | No confundir con los chips. |
| Filtro activo (se puede quitar) | `.chips` + `.chip` con su botón × | Junto con «Limpiar filtros». |
| Lista con búsqueda | `SelectBusqueda` (con `buscar` para listas grandes: busca en el servidor) | Reemplaza a `<select>` con más de 5 opciones. |
| Fecha | `CampoFecha` | Formato del perfil; el valor siempre es `YYYY-MM-DD`. |
| Sí / no | `Interruptor` | |
| Avance | `Avance` (barra), `Pasos` (etapas de un documento) | |
| Estado vacío | `EstadoVacio` | Dice qué es, qué falta y cómo empezar. |

## Formularios

- **Ver ≠ editar.** El detalle de un registro es de solo lectura (texto, no
  campos deshabilitados) y tiene su botón «Editar». La edición en línea
  (`CeldaEditable`) es para documentos en borrador.
- **Orden de los datos.** Primero los comunes. Luego los específicos
  agrupados por tema (generales, comerciales, logística, contacto, estado).
  Al final los campos propios de la empresa.
- **Obligatorio.** Una sola marca: la clase `.req` en la etiqueta (agrega «*»)
  y `.leyenda-req` para la leyenda. Lo que la empresa vuelve obligatorio se
  marca igual y lo valida el servidor.
- **Errores.** Se muestran junto al dato (los devuelve el servidor por campo),
  no solo en un aviso flotante.

## Ventanas, paneles y asistentes

| Situación | Pieza |
|---|---|
| Confirmar una acción | `confirmar(texto, { boton, peligro })` (`stores/confirmar.js`, diálogo `Confirmacion.vue`). No se usa `window.confirm`. El botón lleva el nombre de la acción. |
| Formulario corto (hasta ~10 datos) | `Modal`, con los botones en el pie (`#pie`). |
| Proceso largo o editor (roles, empaque automático, perfiles de importación) o consultar un registro sin perder la lista | `PanelLateral`, con los botones en el pie. |
| Crear algo en varios pasos | `Asistente` («Paso N de M», barra de avance, pasos navegables, guardado de borrador, pantalla completa en el celular). |
| Documento | Su propia página (cabecera `.doc-cabeza`, pestañas, acciones). |

Nunca una ventana dentro de otra. La única excepción es la confirmación, que
es breve y cierra primero. Esc cierra solo la capa de más arriba
(`nucleo/capas.js`).

## Tablas y filtros

Ver S6 en el informe (`docs/INFORME.md`): tabla común con columnas
configurables, densidad, filtros por columna y paginación.
