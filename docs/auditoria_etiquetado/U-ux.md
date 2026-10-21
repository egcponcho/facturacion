# U · Pantallas, navegación y flujos del etiquetado (main 3b9d8b5). Solo lectura

Alcance: `frontend/src/modulos/etiquetado/**`, `router.js`, `App.vue` y los puntos de entrada en OC, lista de OC, packing list, producto, grupos de producto y recetas de empaque. Se levantó la demo en un puerto aparte (8781, base propia) y se recorrieron los flujos a 1440 px y 390 px. El servidor se detuvo al final y el repositorio quedó sin cambios.
Capturas: `/tmp/claude-0/-home-user-facturacion/0fef4306-34be-5b68-a96c-ecdcee70a452/scratchpad/auditoria/cap/` (en el texto se citan como `cap/<nombre>.png`).
No se repiten los fallos de lógica, datos ni API de L, D, C e I. Si un síntoma de pantalla viene de ellos, se cita (p. ej. L-03, L-07, L-12).

---

## 1. Inventario de pantallas y accesos

| # | Pantalla / pieza | Ruta o lugar | Se llega desde |
|---|---|---|---|
| P1 | **Imprimir**: lista de trabajos y «Nuevo trabajo» | `/etiquetas` (`ImprimirView.vue`) | Menú «Etiquetas» (`App.vue:41`); X y «Volver a Etiquetas» del asistente |
| P2 | **Asistente de trabajo** en 3 pasos (Qué imprimir · Revisar · Generar) | `/etiquetas/trabajos/nuevo`, `/:id` (`TrabajoEtiquetasView.vue`, 1 092 líneas) | P1; panel de OC/PL; barra de líneas de la OC; barra de la lista de OC; producto; redirecciones `/etiquetas/masiva` y `/generar` (`router.js:43-46`) |
| P2a | Panel «Vista previa» del registro | PanelLateral en P2 (`:963`) | Ojo de cada fila; botón de cabecera |
| P2b | Modales «Anular ejecución» y «Marcar como impresas» | P2 (`:977`, `:990`) | Fila de la ejecución en Generar |
| P2c | Formularios en línea: «Elegir diseño» (con «Guardarlo como diseño de…»), «Completar el dato», «Reimprimir» | P2 (`:756-768`, `:774-786`, `:924-951`) | Problemas en Revisar; fila de la ejecución |
| P3 | **Diseños**: tarjetas por tipo | `/etiquetas/disenos` (`DisenosView.vue`) | Pestaña de la cabecera común (`CabezaEtiquetado.vue:112-116`); paso 3 de Configuración; `SelectorDiseno` «Crear uno» |
| P3a | Modales «Nuevo diseño» y «Duplicar» | P3 (`:175`, `:211`) | Botón de cabecera o de cada tipo; `?nuevo=<tipo>` |
| P4 | **Editor de diseño** (lienzo; riel con Campos, Capas, Vista previa y Versiones; propiedades) | `/etiquetas/disenos/:id` (`EditorEtiquetaView.vue`) | Tarjeta de P3 |
| P4a | Versiones y aprobación (aprobar, rechazar, retirar, usar, archivar, comparar, bitácora) | Panel del riel (`VersionesEtiqueta.vue`) + Modal + PanelLateral de comparación | Riel «Versiones», menú «…», aviso «Ver versiones» |
| P4b | Modales «Datos del diseño» y «Atajos» | P4 (`:394`, `:409`) | Menú «…» |
| P5 | **Configuración**: guía de 6 pasos | `/etiquetas/configuracion?paso=` (`ConfiguracionEtiquetadoView.vue`) | Pestaña; enlaces «Resolver», «ver», «Configurarlos» |
| P5.1 | Tipos de etiqueta + Tamaños | paso `tipos` (`TiposEtiqueta.vue`, `TamanosEtiqueta.vue`) | — |
| P5.2 | Familias y artículos (árbol, ficha, categorías, asignar en lote, editar en la página) | paso `familias` (`FamiliasYArticulos.vue`, `CategoriasFamilia.vue`, `FormFamilia.vue`) | — |
| P5.3 | Diseños por tipo (atajos a P3) | paso `disenos` | — |
| P5.4 | **Qué diseño va en qué** (matriz) → celda en la página | paso `matriz` (`MatrizEtiquetado.vue` → `CeldaEtiquetado.vue`) | También desde la ficha de familia (P5.2) |
| P5.5 | Nombres de campos + campos lógicos | paso `campos` | — |
| P5.6 | Revisar e historial (conversión de reglas + **lotes generados**) | paso `revisar` (`ConversionReglas.vue`, `HistorialEtiquetas.vue`) | «Etiquetas generadas» del producto |
| P5a | Primer uso (asistente de 3 pasos en la página) | P1 sin tipos; P5.1 sin tipos (`PrimerUsoEtiquetado.vue`) | — |
| P6 | **Asistente de familia** (4 pasos, borrador personal) | `/etiquetas/configuracion/familia/:id` (`AsistenteFamiliaView.vue`) | P5.2 «Nueva familia», «Configurar paso a paso», «Nueva subfamilia» |
| E1 | Botón «Etiquetas» → **panel de resumen** (`ResumenEtiquetas.vue`) con «Imprimir etiquetas» y «Diseño especial para esta OC…» | Detalle OC (`OrdenView.vue:190, 361`) | — |
| E2 | Selección de líneas → «Etiquetas de estas líneas» (va directo a P2) | Detalle OC (`OrdenView.vue:29-30, 271, 300-302`) | — |
| E3 | Selección de OC → «Etiquetas» (va directo a P2) | Lista de OC (`OrdenesView.vue:596`) | — |
| E4 | Botón «Etiquetas» → el mismo panel (sin diseño especial) | Packing list (`PackingListView.vue:569, 1167`) | — |
| E5 | Pestaña «Etiquetas» del producto (`EtiquetadoProducto.vue`): familia, diseño por tipo y por qué, «Usar otro diseño», «Cambiar familia» (Modal), «Imprimir», «Etiquetas generadas» | `/productos/:id?vista=etiquetas` (`ProductoView.vue:705`) | Enlace del producto en P5.2 |
| X1 | **Grupos de producto**: el mismo árbol de familias y categorías, con otro editor (PanelLateral) | `/grupos-producto`, en Configuración → Datos maestros (`App.vue:56`) | Solo desde el menú de ajustes |
| X2 | Recetas y reglas de empaque (usan `EditorCondiciones` y `buscadores.js` del etiquetado) | `/empaque/recetas` | Menú de ajustes |

Lo que falta en el inventario: el inicio no muestra ninguna tarea de etiquetado (versiones por aprobar, trabajos con errores, ejecuciones sin confirmar; `seguimiento/dashboard.py:188-258` no tiene tipos de etiquetas). Tampoco hay ruta de historial (`/etiquetas/historial` cae en `/`), ni historial filtrado desde la OC o la PL, ni acción de etiquetas en la selección de cajas de la PL (`PackingListView.vue:804-816`).

---

## 2. Recorridos actuales con conteo (demo, admin)

Cuenta: 1 clic o 1 elección = 1 acción. «Módulo» = cambio de sección del menú principal.

**(a) Etiquetas de una OC completa** · OC 4400003904 · `cap/1440-oc-panel-etiquetas.png` → `trabajo-revisar` → `trabajo-generar-ok` → `trabajo-generado-ok`
Órdenes (1) → OC (2) → «Etiquetas» (3) → «Imprimir etiquetas» (4). Se crea el trabajo y se entra en Revisar. Ahí aparece «Escriba el valor de Season»: el panel no lo avisó y hay que escribirlo (5). Luego «Siguiente» (6), «Generar 49 etiquetas» (7), «Descargar el ZIP» (8), «Marcar como impresas» (9), casilla (10) y «Confirmar» (11). La X lleva a `/etiquetas`, no a la OC: volver cuesta 3 acciones más.
**Total: 11 acciones (14 con el regreso), 4 pantallas (lista OC, OC con panel, asistente en 2 pasos, modal) y 2 cambios de módulo (Órdenes → Etiquetas → Órdenes).** Al volver, el panel solo dice «Ya generadas: 49» y su botón principal sigue siendo «Imprimir etiquetas», que crea otro trabajo (`cap/1440-oc-panel-tras-generar.png`).

**(b) Solo algunas líneas** · OC 4400003851 · `cap/1440-trabajo-posiciones.png`
Órdenes (1) → OC (2) → marcar N líneas (N) → «Etiquetas de estas líneas» (3+N). No hay panel de resumen. Luego Siguiente, Generar y Descargar (6+N), y confirmar impresión (+3).
**Total: 9+N acciones, 3 pantallas, 2 cambios de módulo.** Los tipos de etiqueta del trabajo cambian según la entrada: desde el panel salen los tipos con etiquetas (colgante, precio, hoja); desde las líneas, solo los obligatorios (colgante y caja). Ver U-03.

**(c) Bultos de un packing list** · PL-001 · `cap/1440-pl-panel-etiquetas.png`, `trabajo-pl-que.png`
Facturas (1) → factura (2) → PL (3) → «Etiquetas» (4) → «Imprimir etiquetas» (5) → Revisar. Por defecto solo se etiquetan los «Bultos exteriores». Para incluir master carton o inner pack hay que volver al paso 1 (6), marcar el nivel (7) y pulsar Siguiente (8). Después Siguiente (9), Generar (10) y Descargar (11).
**Total: 8 acciones (11 con niveles), 3 pantallas, 2 cambios de módulo.** No se pueden elegir cajas concretas.

**(d) Configurar qué diseño lleva una familia** · `cap/1440-config-defecto.png`, `config-matriz.png`, `matriz-celda.png`
Etiquetas (1) → Configuración (2). En la demo la guía abre «Familias» porque hay 1 artículo sin familia (`ConfiguracionEtiquetadoView.vue:110`). Luego el paso «Qué diseño va en qué» (3), la celda familia × tipo (4), el diseño (5-6) y Guardar (7).
**Total: 7 acciones, 1 pantalla con 3 estados.** Hay otros caminos con otra interfaz: la ficha de familia (P5.2), el paso 3 del asistente de familia (P6), el producto (E5), el panel de la OC (E1) y Revisar (P2c). Ver U-06. Si la familia no existe, se crea en X1 (otro menú) o en P6 (4 pasos, unas 12 acciones).

**(e) Crear y aprobar un diseño** · `cap/1440-disenos-nuevo-modal.png`, `editor-versiones.png`
Diseñador: Etiquetas (1) → Diseños (2) → «Nuevo diseño» (3) → tipo, nombre y medidas (4-6) → «Crear y abrir el editor» (7) → diseñar → Guardar (8) → «Enviar a aprobación» (9).
Aprobador: no le llega ningún aviso. Etiquetas (1) → Diseños (2) → filtro «Con una versión pendiente» (3) → abrir (4) → «Ver versiones» (5) → «Aprobar» (6) → confirmar (7).
Para usarlo: Configuración → paso → celda → diseño → Guardar (+6).
**Total: unas 22 acciones entre 2 personas y 3 secciones.**

---

## 3. Hallazgos

Formato: id · etiqueta · impacto — problema. **Evidencia** · **Solución** · **Riesgo**.

### Navegación y duplicidad

**U-01 · [VERIFICADO] · Alto — Cada entrada crea un trabajo nuevo. No se reconoce el trabajo abierto del mismo origen y no se puede descartar.**
**Evidencia:** `TrabajoEtiquetasView.vue:156-163` crea el trabajo al montar y `ResumenEtiquetas.vue:40-43` siempre navega a `nuevo`. En la demo, 3 entradas dieron 3 trabajos nuevos (`cap/1440-imprimir-despues.png`). `POST /etiquetas/trabajos/{id}/cancelar` existe (`api.py:559`) y ninguna pantalla lo usa. La lista no tiene columna de acciones (`ImprimirView.vue:82-98`). Tras generar, el panel de la OC ofrece imprimir otra vez.
**Solución:** el panel y los atajos consultan los trabajos abiertos del mismo origen y ofrecen «Continuar el trabajo X» o «Descargar lo generado» antes de «Nuevo». Agregar «Descartar» en la lista y en el asistente.
**Riesgo:** bajo. Hace falta un filtro por origen en `GET /etiquetas/trabajos` (relacionado con L-13).

**U-02 · [VERIFICADO] · Alto — Tres historiales con nombres distintos para la misma cosa, y el principal está dentro de «Configuración».**
**Evidencia:**
- Lista de trabajos en Imprimir (P1).
- «Ejecuciones e impresión» dentro de cada trabajo: descargar, marcar impresas, reimprimir, anular (`TrabajoEtiquetasView.vue:900-955`).
- «Lote #N» en Configuración → paso 6, que solo descarga (`HistorialEtiquetas.vue:29, 101, 124-127`).

Ejecución y lote son la misma entidad (`/etiquetas/generaciones`). No hay ruta propia (`/etiquetas/historial` → `/`). «Etiquetas generadas» del producto abre el paso 6 sin filtrar por artículo (`EtiquetadoProducto.vue:315`), aunque el componente lee `?articulo_id`/`?oc_id` (`HistorialEtiquetas.vue:23-24`).
**Solución:** una sección «Historial» con una sola tabla de ejecuciones y todas sus acciones (reutilizar la tabla del paso Generar). Que acepte filtros por OC, PL y artículo, y que los atajos lleguen a ella filtrados.
**Riesgo:** bajo. Es mover componentes y unificar el nombre («Ejecución»).

**U-03 · [VERIFICADO] · Alto — La misma OC da otro conjunto de etiquetas según por dónde se entre.**
**Evidencia:** el panel pasa `tipos` = tipos con etiquetas > 0 (`ResumenEtiquetas.vue:42`). «Etiquetas de estas líneas» (`OrdenView.vue:29`) y la lista de OC (`OrdenesView.vue:596`) no pasan tipos y se aplica `porDefecto()` = solo los obligatorios (`TrabajoEtiquetasView.vue:154, 199-203`). Capturas: `cap/1440-trabajo-revisar.png` muestra 3 pestañas de tipo; `cap/1440-trabajo-posiciones.png`, 1 pestaña y el aviso «Etiqueta de caja: aquí no hay nada». Coincide con L-07.
**Solución:** un solo cálculo de tipos por defecto, en el servidor o en el asistente, para todas las entradas. Ver la propuesta de los atajos en §4.
**Riesgo:** bajo.

**U-04 · [VERIFICADO] · Alto — Las familias se crean y editan en 4 lugares con capacidades distintas, y hay 3 conceptos llamados «familia».**
**Evidencia:**
- X1 `/grupos-producto` (PanelLateral, condiciones, sin campos ni «Probar»).
- P5.2: formulario en la página con campos (`FamiliasYArticulos.vue:211-231`) y categorías con «Probar» (`CategoriasFamilia.vue`).
- P6, el asistente.
- E5, «Cambiar familia» en un Modal.

Además, el menú tiene «Product families» de clasificación arancelaria (`App.vue:59`) junto a «Product groups → familias» (`App.vue:56`). El texto vacío de X1 manda a «Labels → Families» (`GruposProductoView.vue:153`).
**Solución:** un solo dueño del árbol y de los miembros: Grupos de producto (es compartido con empaque). El etiquetado solo muestra el árbol con sus etiquetas y enlaza para editar. Renombrar la clasificación como «Familias arancelarias».
**Riesgo:** medio. Los permisos `etiquetas.familias` y `catalogos.editar` ya conviven en X1 (`GruposProductoView.vue:21`). Ver D-15 e I-17.

**U-05 · [VERIFICADO] · Medio — Desde la lista de OC solo se pueden etiquetar las OC con saldo por facturar.**
**Evidencia:** la selección de la lista usa `:puede-seleccionar="tieneSaldo"` (`OrdenesView.vue:63, 445`), un criterio de facturación. La OC 4400003904 («Aprobada, sin liberar») no se puede elegir en la lista, pero sí etiquetar desde su detalle.
**Solución:** para etiquetas, que la selección no dependa del saldo, o usar el selector de OC del asistente.
**Riesgo:** bajo.

**U-06 · [VERIFICADO] · Alto — «Qué diseño lleva» se cambia en 6 lugares con 5 interfaces y garantías distintas.**
**Evidencia:**

| Lugar | Interfaz | Simula el efecto | Excepciones |
|---|---|---|---|
| Celda de la matriz (`CeldaEtiquetado.vue`) | completa | sí (`EfectoCambio`) | sí |
| Ficha de familia | la misma celda | sí | sí |
| Asistente de familia (`AsistenteFamiliaView.vue:279-283`) | `Seleccion` propio, solo aprobados (`:52`) | no | no |
| Producto (`EtiquetadoProducto.vue:216-229`) | propia | solo sin tallas | no |
| Panel de la OC (`ResumenEtiquetas.vue:53-64`) | propia, motivo obligatorio | no | — |
| Revisar del trabajo (`TrabajoEtiquetasView.vue:433-452`) | casilla «guardar como regla» | no | — |

**Solución:** una sola edición de regla, la celda, que se abre como PanelLateral con el contexto precargado (familia, producto, OC o lugar). Los demás puntos enlazan a ella. Revisar conserva «solo este trabajo».
**Riesgo:** medio. Las excepciones de OC pasarían a la celda (hoy solo se crean en E1; `CeldaEtiquetado.vue:256` no deja editarlas).

**U-07 · [VERIFICADO] · Medio — Los enlaces entre pantallas pierden el contexto.**
**Evidencia:**
- «Resolver» del panel → `/etiquetas/configuracion` sin paso ni tipo (`ResumenEtiquetas.vue:99`). Abre el primer paso «que falta», que en la demo es Familias.
- «ver» en el diseño → mismo destino (`DisenosView.vue:162`).
- «Crear uno» de `SelectorDiseno.vue:50` → `/etiquetas/disenos` sin `?nuevo=<tipo>`.
- La X o «Volver a Etiquetas» del trabajo → `/etiquetas`, no al origen (`TrabajoEtiquetasView.vue:191`).

**Solución:** pasar siempre el contexto (`?paso=matriz&tipo=…&familia=…`, `?nuevo=tipo`, `?volver=`).
**Riesgo:** bajo.

**U-08 · [VERIFICADO] · Medio — La guía de 6 pasos se impone a quien solo quiere cambiar una regla.**
**Evidencia:** sin `?paso`, Configuración abre el primer paso «que falta» (`ConfiguracionEtiquetadoView.vue:110-114`): Familias por 1 artículo sin familia (`cap/1440-config-defecto.png`). La guía dice «Qué diseño va en qué · Todo tiene diseño» mientras la matriz advierte que la etiqueta colgante obligatoria no tiene diseño general (`cap/1440-config-matriz.png`).
**Solución:** la guía se convierte en una lista «Puesta en marcha» que solo aparece mientras falte algo. Configuración y Reglas abren siempre su propia pantalla.
**Riesgo:** bajo.

**U-09 · [VERIFICADO] · Medio — Aprobar diseños no se puede descubrir.**
**Evidencia:** no hay tarea en el inicio. Aprobar solo existe en el panel Versiones del editor (`VersionesEtiqueta.vue:28`). El aviso de la versión pendiente habla de «retirarla para seguir editando» (`EditorEtiquetaView.vue:231`). La cabecera muestra «Lista para imprimir» en verde con la versión pendiente (`EditorEtiquetaView.vue:324-328`, `cap/1440-editor-versiones.png`). Al aprobar no se ofrece asignar el diseño.
**Solución:**
- Bandeja «Por aprobar» con cuenta en Diseños y tarea en el inicio.
- Aviso para el aprobador con «Aprobar / Rechazar».
- Cambiar el texto del chip a «Sin errores de datos».
- Después de aprobar, ofrecer «Asignar a…» (abre la celda).

**Riesgo:** bajo.

### Formularios, estados y mensajes

**U-10 · [VERIFICADO] · Medio — El panel de resumen no anticipa lo que bloquea en Revisar.**
**Evidencia:** el panel de la OC no dice que falta el dato manual «Season» (`cap/1440-oc-panel-etiquetas.png`), y Revisar lo marca como error (`cap/1440-trabajo-revisar.png`). Revisar muestra «El campo manual.temporada está vacío» (clave técnica) y «1 problemas». En la PL, los niveles de empaque solo están en el paso 1, que se salta (`TrabajoEtiquetasView.vue:731-740`).
**Solución:** que el panel liste «datos que pedirá el diseño» y los niveles. Mostrar los nombres de los campos, no las claves.
**Riesgo:** bajo.

**U-11 · [VERIFICADO] · Medio — Generar mezcla dos acciones primarias y tres desplegables de formato.**
**Evidencia:** «Generar N» y «Volver a Etiquetas» son primarios a la vez (`TrabajoEtiquetasView.vue:888`, `Asistente.vue:62`). «Guardar borrador» sigue después de generar (`:623`, falta `:con-borrador="false"`). Hay tres desplegables antes de generar: archivo de cada ejecución, contenido del ZIP y repartir (`:850-867`; `cap/1440-trabajo-generar-ok.png`). «Marcar como impresas» está deshabilitado y el motivo solo aparece en `title` (`:915-917`). Un aviso tapa «Siguiente» (`cap/1440-trabajo-generar.png`).
**Solución:** un solo primario por estado. Formato con el valor de la empresa y las opciones del ZIP plegadas en «Opciones de archivo». El motivo, visible. Los avisos, fuera de la barra de acciones.
**Riesgo:** bajo.

**U-12 · [VERIFICADO] · Medio — La misma palabra significa números distintos.**
**Evidencia:** la columna «Etiquetas» de la lista cuenta solo las LISTO/ADVERTENCIA (`trabajos.py:577`): 25. La cabecera del mismo trabajo dice 49 (`cap/1440-imprimir-despues.png` frente a `trabajo-revisar.png`). Hay plurales rotos («1 problemas», «1 ejecuciones», «1 diseños», «1 excepciones»).
**Solución:** separar «listas / total», con plurales por regla.
**Riesgo:** bajo.

**U-13 · [VERIFICADO] · Medio — Las tablas muestran códigos en crudo.**
**Evidencia:** `TablaDatos.vue:543` pinta `fila[c.clave]` e ignora `textoValor`, que solo usa en los filtros (`:249-253`). En Imprimir se ve Origen «PACKING/OC/ARTICULOS» y Actualizado «2026-10-20T02:36:37.109770» (`cap/1440-imprimir.png`; `ImprimirView.vue:58, 62`).
**Solución:** que la celda use `textoValor` por defecto.
**Riesgo:** bajo. El cambio afecta a todas las tablas: revisar las columnas que ya tienen slot.

**U-14 · [VERIFICADO] · Bajo — Acciones repetidas o con poco peso.**
**Evidencia:** la celda tiene dos pares Cancelar/Guardar (`CeldaEtiquetado.vue:218-221, 284-287`) y el «Siguiente» de la guía queda primario mientras se edita una celda; salir de ella pierde los cambios sin avisar (no hay guarda). En las tarjetas de Diseños, «Archivar» tiene el mismo peso que «Editar». El modal «Nuevo diseño» propone 100×50 mm para una etiqueta colgante de 2×3 in y repite la medida («100 × 50 mm (100.0 × 50.0 mm)»; `cap/1440-disenos-nuevo-modal.png`). El texto vacío de la matriz habla de una «pestaña Tipos de etiqueta» que ya no existe (`MatrizEtiquetado.vue:104`).
**Solución:** un solo pie de acciones, ocultar la guía mientras se edita, confirmar antes de salir, «Archivar» en el menú «…», y la medida sugerida según el tipo.
**Riesgo:** bajo.

**U-15 · [VERIFICADO] · Bajo — Enlace a una pantalla que el rol no puede abrir.**
**Evidencia:** P1 enlaza cada trabajo a todos (`ImprimirView.vue:90`), pero la ruta exige `etiquetas.generar` (`router.js:42`). Con solo `etiquetas.ver`, el clic devuelve al inicio con «No tienes acceso».
**Solución:** vista de solo lectura del trabajo, o el nombre sin enlace.
**Riesgo:** bajo. Ver L-02.

**U-16 · [VERIFICADO] · Bajo — En el menú, «Productos» y «Etiquetas» comparten el mismo icono (`App.vue:40-41`), y también «Arancel» (`:60`).**
**Solución:** un icono propio para cada uno.
**Riesgo:** nulo.

### Accesibilidad y 390 px

**U-17 · [VERIFICADO] · Medio — Hay filas que solo se abren con el ratón.**
**Evidencia:** `TablaDatos.vue:532-533` (`<tr @click>` sin `tabindex` ni teclado). Editar un tipo de etiqueta solo es posible con clic en la fila (`TiposEtiqueta.vue:161-162`, sin botón), y lo mismo el detalle de un lote (`HistorialEtiquetas.vue:77-78`). En la demo, las filas tienen `tabindex=null`.
**Solución:** filas enfocables con Enter, o un botón «Abrir» o «Editar» en la columna de acciones.
**Riesgo:** bajo.

**U-18 · [VERIFICADO] · Medio — Fallos de presentación a 390 px.**
**Evidencia:**
- La matriz desborda 58 px en horizontal por el botón «Siguiente: Nombres y origen de los campos» (medido; `cap/390-config-matriz.png`).
- En Revisar no se ven la cantidad ni la vista previa sin desplazar la tabla dentro de la tarjeta (tabla de 743 px; `cap/390-trabajo-revisar.png`).
- En Imprimir, el estado se corta («Revisa…», `cap/390-imprimir.png`).
- La pestaña «Etiquetas» del producto queda oculta al final de la tira, incluso a 1440 (`cap/1440-producto-etiquetas.png`, `390-producto.png`).
- Hay controles de 26-30 px (cerrar del asistente 30×30; `btn-chico` de 30 px de alto en «Nuevo diseño» y «Filtros»).

**Solución:**
- Botones de la guía que hagan salto de línea o con texto corto.
- Revisar en tarjetas (el modo móvil de TablaDatos).
- Estado como columna de prioridad 1.
- Pestaña «Etiquetas» antes de «Versiones».
- 44 px como mínimo en táctil.

**Riesgo:** bajo.

**U-19 · [SOSPECHA] · Bajo — El contraste del texto de ayuda gris claro sobre fondo gris (`--tinta-3`) en las tarjetas de la guía y en «Por qué» de Revisar parece inferior a 4.5:1 en las capturas.**
**Solución:** medir con los tokens y subir a `--tinta-2`.
**Riesgo:** nulo.

### Consistencia visual y reutilización

**U-20 · [VERIFICADO] · Medio — Controles hechos a mano que duplican los comunes y se ven distintos.**
**Evidencia:**
- `.segmentos-txt` en Revisar (`TrabajoEtiquetasView.vue:806, 1074-1076`) en lugar de `Segmentos.vue`.
- `.pildora` redefinida con otra forma en la matriz (`MatrizEtiquetado.vue:166-168`). Compárense «Artículos/Bultos/Documentos» en `cap/1440-config-matriz.png` con «Productos/Artículos/Grupos» en `config-familias.png`.
- `.chip` global sobrescrita (`TrabajoEtiquetasView.vue:1020`).
- Barra de avance propia (`:873-876`) en lugar de `Avance.vue`.
- Pasos propios en P5 (`.guia-*`) y P6 (`.af-pasos`, `AsistenteFamiliaView.vue:262-268`) en lugar de `Asistente.vue`/`Pasos.vue`.

**Solución:** ver §5.
**Riesgo:** bajo.

**U-21 · [VERIFICADO] · Medio — Hay 5 tablas `<table>` propias en el asistente: líneas `:674`, artículos `:701`, registros `:813`, ejecuciones `:902` y reimpresión `:937`.** Las de registros y ejecuciones necesitan búsqueda, filtro, selección, paginación y modo móvil, que TablaDatos ya tiene. El detalle del lote (`HistorialEtiquetas.vue:111`) y los campos de familia (`FormFamilia.vue:51`) también son tablas propias.
**Solución:** pasar registros, ejecuciones y líneas a TablaDatos (slots de celda, `seleccionable`, `vista-previa`).
**Riesgo:** medio. La edición de cantidad en la celda debe seguir funcionando (ojo con L-03: hoy la cantidad escrita se ignora).

**U-22 · [VERIFICADO] · Bajo — Hay utilidades genéricas dentro del módulo de etiquetado.** Empaque y grupos importan `buscadores.js`, `EditorCondiciones.vue` y `OPERADORES`/`SIN_VALOR` del etiquetado (`ReglasEmpaque.vue:12-14`, `ConstructorReceta.vue:9`, `ProbarEmpaque.vue:7`, `GruposProductoView.vue:11-12`). Empaque tiene «Probar» y el etiquetado no tiene un equivalente aparte, aunque usa el mismo árbol. Son dos modelos mentales: la lista ordenada de empaque y la matriz de etiquetas (ver I-09).
**Solución:** mover estas utilidades a `componentes/` y `nucleo/`. Agregar «Probar» en Reglas con el mismo patrón que empaque.
**Riesgo:** bajo.

**U-23 · [VERIFICADO] · Bajo — La PL no deja etiquetar cajas concretas.** La barra de selección de cajas no tiene «Etiquetas de estas cajas» (`PackingListView.vue:804-816`), mientras la OC sí tiene su equivalente para líneas.
**Solución:** agregar el atajo con `bultos=` en el asistente.
**Riesgo:** medio. Hace falta soporte en el servidor; ver I-02 e I-07 sobre la identidad del bulto.

---

## 4. Propuesta: módulo central «Etiquetas»

Una sola entrada en el menú, con 5 secciones en la cabecera común (`CabezaEtiquetado`). No hacen falta pantallas nuevas: se reubica lo que ya existe.

| Sección | Ruta | Contenido | Sale de |
|---|---|---|---|
| **Imprimir** | `/etiquetas` | Bandeja de trabajos (Por continuar · Con errores · Generados sin confirmar impresión · Todos), con Origen legible y enlace al documento. En cada fila: Continuar / Descargar / Descartar. Botón «Nuevo trabajo». El asistente de 3 pasos se mantiene | P1 y P2 |
| **Historial** | `/etiquetas/historial?oc=&pl=&articulo=` | Una tabla de **ejecuciones** con descargar, marcar impresas, reimprimir y anular (el mismo componente que hoy está en Generar). Filtros por OC, PL, artículo, fecha y estado | P5.6 «lotes» + tabla de ejecuciones de P2 |
| **Diseños** | `/etiquetas/disenos` | Tarjetas por tipo + pestaña **Por aprobar** con cuenta; editor sin cambios. Aviso con «Aprobar» para quien tiene permiso; después de aprobar, «Asignar a…» | P3 y P4 |
| **Reglas** | `/etiquetas/reglas?tipo=&familia=&producto=&oc=` | La matriz como pantalla principal. La **celda** se abre en PanelLateral y es la única edición de reglas: normal, excepciones (incluida «para una OC»), propios de producto y talla, simulación. **Probar**: elegir una OC, PL o artículo y ver qué diseño sale en cada registro y por qué. El árbol de familias es de solo lectura, con «Editar en Grupos de producto» | P5.4, ficha de etiquetas de P5.2, E1 diseño especial, formulario propio de E5 |
| **Configuración** | `/etiquetas/configuracion` | Tipos (con «Va en») · Tamaños · Campos y nombres · Conversión de reglas antiguas · lista «Puesta en marcha» (solo si falta algo) · Primer uso | P5.1, P5.5, P5a; la guía de 6 pasos pasa a lista |

**Grupos de producto (X1)** queda como dueño único del árbol, las categorías (con «Probar» de `CategoriasFamilia`) y los **miembros**: la tabla de productos, artículos y grupos con asignación en lote, que hoy está en P5.2. El asistente de familia P6 se lanza desde ahí («Nueva familia guiada»), usa `Asistente.vue` y su paso de diseños usa `SelectorDiseno` y enlaza a Reglas.

**Atajos contextuales.** No llevan lógica propia: todos abren el flujo central con el contexto precargado.

| Dónde | Atajo | Abre |
|---|---|---|
| Detalle de OC | «Etiquetas» → panel de resumen (se conserva como paso previo único). Muestra lo que sale, lo que falta (incluidos datos manuales), **trabajos abiertos o generados de esta OC** (Continuar / Descargar) y «Ver historial de esta OC» | `/etiquetas/trabajos/nuevo?origen=OC&oc=` · `/etiquetas/historial?oc=` · «Cambiar diseño» → `/etiquetas/reglas?oc=` |
| Líneas de la OC | «Etiquetas de estas líneas» → el **mismo panel** con `posiciones` y los mismos tipos | igual |
| Lista de OC | «Etiquetas» con una selección que no dependa del saldo | `nuevo?origen=OC&ocs=` |
| Packing list | «Etiquetas» → mismo panel, con los niveles de empaque visibles. En la selección de cajas, «Etiquetas de estas cajas» | `nuevo?origen=PACKING&pl=&niveles=` |
| Producto | Pestaña de solo lectura «qué lleva y por qué» + «Imprimir» + «Cambiar diseño» (abre la celda con `producto=`) + «Etiquetas generadas» (Historial filtrado) | Reglas e Historial |
| Inicio | Tareas: versiones por aprobar, trabajos con errores, ejecuciones sin confirmar | Diseños › Por aprobar, Imprimir |

**Se eliminan o fusionan:**
- El formulario «Diseño especial para esta OC» de E1 y el formulario «propio» de E5 → la celda de Reglas.
- El Modal «Cambiar familia» de E5 y el formulario de familia en P5.2 → Grupos de producto (miembros).
- La guía de 6 pasos → lista de puesta en marcha.
- El historial de lotes en Configuración → Historial.
- Los selectores de diseño propios → `SelectorDiseno`.
- Las redirecciones `/etiquetas/masiva` y `/generar`, cuando ya no haya enlaces viejos.
- «Lote» y «Ejecución» → un solo nombre.

**Flujos guiados recomendados:**
1. **Imprimir desde el contexto:** panel (sale, falta, ya hay) → Revisar (primero los datos manuales y los problemas, con arreglo en el lugar) → Generar (un primario, formato predeterminado) → Descargar → Confirmar impresión → **volver al origen**. Objetivo para (a): 7 acciones y 0 cambios de módulo para volver.
2. **Sin diseño en Revisar:** «Elegir diseño» → «solo este trabajo», o «guardar como regla», que abre la celda en un panel con el efecto simulado.
3. **Diseño nuevo:** el tipo viene del contexto → editor → enviar → el aprobador recibe la tarea → aprueba en el aviso → «Asignar a…» (celda de Reglas).
4. **Familia nueva:** Grupos de producto → asistente (datos → miembros → diseños opcionales) → Reglas filtrado por la familia.
5. **Puesta en marcha:** primer uso → lista con lo que falta. Desaparece al completarse.

---

## 5. Componentes a reutilizar

| Hoy (propio) | Usar | Dónde |
|---|---|---|
| `<table>` de registros, ejecuciones, líneas, artículos y reimpresión | `TablaDatos` (slots, `seleccionable`, vista móvil) + `BarraSeleccion` (ya usada) | `TrabajoEtiquetasView.vue:674, 701, 813, 902, 937`; `HistorialEtiquetas.vue:111` |
| `.segmentos-txt`, `.pildora` local, `.tj-seg` | `Segmentos` / `.pestanas-pildora` globales | `TrabajoEtiquetasView.vue:652-657, 806`; `MatrizEtiquetado.vue:88-90, 166-168` |
| Tarjetas de opción (`.tj-origen`, `.tj-seg`, opciones de empaque en la PL) | Extraer un componente común `TarjetasOpcion` | P2 paso 1 y `PackingListView.vue:649-656` |
| `.tj-avance` | `Avance` | `TrabajoEtiquetasView.vue:873-876` |
| Pasos de la guía y de `af-pasos` | `Asistente` (P6, con borrador) / `Pasos` (lista de puesta en marcha) | `ConfiguracionEtiquetadoView.vue:151-165`, `AsistenteFamiliaView.vue:262-268` |
| Celda en la página o Modal para reglas y familia | `PanelLateral` con `CeldaEtiquetado` dentro | E1, E5, P2c, P5.2 |
| `Seleccion` de diseños | `SelectorDiseno` | `AsistenteFamiliaView.vue:279-283` |
| `type="date"` en el historial | `CampoFecha` (ya lo usa empaque) | `HistorialEtiquetas.vue:80-81` |
| Estados vacíos solo con texto | `EstadoVacio` con acción | `ImprimirView.vue:97`, `HistorialEtiquetas.vue:98`, `DisenosView.vue:141` |
| `.chip` sobrescrita | `.chip` global | `TrabajoEtiquetasView.vue:1020` |
| `buscadores.js`, `EditorCondiciones`, `OPERADORES` en etiquetado | Moverlos a `nucleo/` y `componentes/` | empaque y grupos los importan |
| Arreglos dentro de `TablaDatos` | Usar `textoValor` en la celda; filas enfocables | `TablaDatos.vue:532-543` |
