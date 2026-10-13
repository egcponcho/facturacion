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
| Lista de opciones | `Seleccion` (escrita como un `<select>` con sus `<option>`) o `SelectBusqueda` (con `buscar` para listas grandes: busca en el servidor) | No se usa `<select>` nativo: se vería distinto. `@change` recibe el valor, no el evento. |
| Fecha | `CampoFecha` | Formato del perfil; el valor siempre es `YYYY-MM-DD`. No se usa `type="date"`. |
| Archivo | `CargaArchivo` (zona grande para cargas; `compacta` en formularios y barras) o `BotonArchivo` (un botón que abre el selector: logo, fotos, paquetes) | No se usa `<input type="file">` a la vista. |
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
- **Campos.** Un solo estilo para todos (`styles.css`, «Botones y campos»):
  mismo alto, borde, letra y foco que las listas. `.entrada.chica` para una
  barra o fila de edición. Los anchos fijos van con clases (`.ancho-xs` …
  `.ancho-xl`, `.max-*`), no con `style`; el espaciado con las utilidades
  (`.mt`, `.mb-*`, `.gap-*`, `.empuja-fin`…). Una pantalla no redefine
  `.campo`, `.entrada` ni el tamaño de un `select`.
- **Cuadrículas de captura** (líneas de un documento, cuotas, componentes de
  un kit): `.tabla-marco.tabla-captura` con `table.tabla` y `v-tarjetas`;
  `.alto-limitado` si puede crecer mucho. Celdas editables `.celda`
  (`.con-borde` si siempre se ven como campo).

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

Todas las tablas siguen el modelo de la tabla de **órdenes de compra**:

- **Barra de filtros** (`.filtros` con `v-filtros`), en este orden: el
  buscador (`.buscador`), las vistas guardadas, los demás filtros (segmentos
  de estado o vista, selectores), «Más filtros» si hay muchos y el botón
  «Columnas» con la cuenta de las visibles (`6/9`). En el celular solo queda el
  buscador y el resto se abre con «Filtros».
- **Chips** de los filtros activos debajo de la barra, cada uno con su ✕, y
  «Limpiar filtros».
- **Tabla** en `.tabla-marco.tabla-fija` (encabezado fijo al bajar) con
  `table.tabla` y `v-tarjetas` (en el celular cada fila es una tarjeta con el
  nombre de cada columna). La primera columna es el documento:
  `router-link.enlace-doc > strong.codigo` (negrita, sin subrayar, se subraya
  al pasar), su estado (`EstadoBadge`) y debajo una línea gris (`.sub`) con
  fecha, cantidad de líneas o marca. Las referencias a otros documentos dentro
  de la fila son `.enlace` (azul, sin subrayar). Montos y cantidades a la
  derecha (`.num`). Las acciones de la fila al final, apiladas
  (`.acciones-apiladas`), con la principal en `btn-primario`.
- **Maestro-detalle:** `TablaDatos expandible` con la ranura `detalle`. La
  tabla pone la flecha y envuelve el detalle en `DetalleAnidado` (sangría,
  guía a la izquierda y fondo propio): la pantalla no agrega contenedores ni
  márgenes. Una `TablaDatos` dentro del detalle se dibuja sola como tabla
  anidada (compacta, sin vistas guardadas ni densidad, «Columnas» discreto y
  paginación solo si hace falta). Un segundo nivel dentro del detalle usa
  también `DetalleAnidado`.
- **Pie:** `Paginacion` pegada a la tabla, con «1–25 de 80 registros», las
  páginas y las filas por página.
- **Carga y vacío:** `FilasEsqueleto` mientras carga; sin resultados, el motivo
  y «Limpiar filtros»; vacía de verdad, `EstadoVacio` con lo que hace falta
  para empezar.
- La acción principal de la pantalla («Nueva OC», «Nuevo usuario») va en la
  cabecera de la página, no en un panel encima de la tabla. Una tabla de lista
  no va dentro de otra tarjeta.
- Las listas grandes de un selector buscan en el servidor (`SelectBusqueda`
  con `buscar`).

`TablaDatos` arma todo eso de una vez y es la forma de toda lista o tabla que
muestre registros (Facturas es la referencia):

- **Ranuras de la barra:** `barra` (el buscador, va primero), `filtros` (los
  filtros principales, a la vista, después de las vistas guardadas) y
  `mas-filtros` (los secundarios, plegados en «Más filtros»; `masFiltrosActivos`
  pone la cuenta en el botón y lo abre si hay alguno puesto). Los filtros de la
  pantalla que se quitan desde los chips llegan con `chipsExternos` y los
  eventos `quitar-externo` / `limpiar-externos`.
- **Filtro de cada columna, como en Excel:** el embudo del encabezado abre la
  lista de los **valores únicos** de la columna con cuántas filas tiene cada
  uno, con buscador, «(Seleccionar todo)» y «(Vacío)»; se marcan uno o varios.
  Los valores se calculan bajo los demás filtros (el de la propia columna no
  limita su lista). Una columna con códigos usa `opciones` para mostrar su
  nombre; `textoValor` da formato (fechas, montos); `filtro: false` la deja sin
  filtro (columnas calculadas: barras, montos sumados al vuelo, acciones).
- **Encabezados:** ordenan con un clic (asc → desc → sin orden).
- **Densidad a la vista:** compacta, normal o amplia en la barra (tres íconos).
- **Columnas:** se muestran, se ocultan, se reordenan (menú «Columnas») y se
  ensanchan arrastrando el borde del encabezado. Las que el rol no ve (`grupo`)
  no aparecen. Todo se guarda por persona y por tabla (`PUT /perfil/tablas/{tabla}`).
- **Vistas guardadas:** guardan filtros de la pantalla (`externos`), filtros de
  cada columna, orden, columnas visibles y densidad con un nombre, por persona.
- **Celular («prioridad +»):** cada columna tiene prioridad 1, 2 o 3. Bajo
  720 px quedan las de prioridad 1 y bajo 900 px las de 1 y 2. El resto se ve
  al expandir la fila.
- **Datos:** `modo="local"` ordena, filtra y pagina en el navegador (listas
  acotadas que llegan completas). `modo="servidor"` emite `consulta` (orden,
  filtros de columna, página y tamaño) y pide los valores de cada columna con
  `valores(columna, buscar, otros filtros)`: la pantalla los pide al servidor
  (`f` y `/valores`, ver docs/API.md). Siempre se pagina (25 filas por defecto),
  así que ninguna pantalla dibuja miles de filas.
- **Detalle:** `expandible` y la ranura `detalle` (puede llevar otra
  `TablaDatos` con `:vistas-guardadas="false"`); `fila-clicable` + evento `fila`
  para abrir un `PanelLateral`.
- **Celdas editables:** una lista de registros con celdas que se editan (clases
  de material, plantillas de cartón) también es `TablaDatos`: la celda lleva su
  `input.celda`, que se ve como campo (borde suave) mientras se puede editar.

**Excepciones** (no son `TablaDatos`, pero llevan `.tabla-marco` + `table.tabla`
y campos con estilo): los **editores** donde se escribe en casi todas las celdas
y se guarda todo junto (campos propios, terminología y aprobaciones de la
empresa, mapeo de un perfil de importación, tallas de un genérico, desglose al
crear un prepack, asistentes de empaque, códigos por destino de la ficha); el
**árbol arancelario**, que es un árbol (su búsqueda sí pagina); y las tarjetas
de configuración (familias de producto, países, indicadores).

