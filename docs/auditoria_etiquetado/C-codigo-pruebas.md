# Auditoría C · Código sin uso, duplicado, provisional y pruebas del etiquetado (y lo que toca de empaque, compras y grupos)

Repositorio `/home/user/facturacion`, commit `3b9d8b5` (main). Solo lectura: no se modificó ningún archivo del repositorio. Los scripts y salidas temporales están en `scratchpad/auditoria/tmp/`.

**Método.**
- Referencias cruzadas por AST de cada definición de nivel superior (`tmp/xref2.py`): mismo archivo, `from x import`, `modulo.nombre`, en app, demo, tests, scripts y alembic.
- `vulture` (instalado solo en el scratchpad) y `ruff` (estilo y complejidad).
- Rutas de la API contra `frontend/src`, `e2e`, pruebas y docs (`tmp/rutas.py`), revisando además las URL armadas dinámicamente.
- ESLint en el frontend y extracción de i18n replicada en el scratchpad.
- Pruebas reales con pytest, también bajo `TZ=America/Guatemala`.
- Comparación ejecutada del evaluador de condiciones y del formateador en JS y en Python.
- Los reportes previos (`revision/nuevo-*.md`, sobre `6b930db`) se usaron como pista; todo lo de aquí se volvió a verificar.

Etiquetas usadas: **[VERIFICADO]** (comprobado con grep, ejecución o lectura completa del camino) y **[SOSPECHA]** (probable, sin reproducirlo).

---

## 0. Resumen

| Área | Hallazgos clave |
|---|---|
| Sin uso | 1 función muerta real (`trabajos._soltar`), 1 helper duplicado sin uso (`render.vacio`), 1 wrapper sin uso (`campos.por_clave`, `condiciones.cumple`), constantes sin lectura (6), 9 re-exportaciones inútiles en `reglas.py`, 3 endpoints sin pantalla (`/tipos/sugeridos`, `/trabajos/{id}/cancelar`, `/usos/{id}/historial`) y 861 traducciones huérfanas en `es.json` (~229 de etiquetado y empaque). No hay componentes Vue ni archivos huérfanos: ESLint y `ruff` quedan limpios. |
| Duplicados | **Tres CRUD** sobre la misma tabla `grupos_producto`, con validaciones distintas. **Dos evaluadores** de condiciones (JS y Python) que discrepan en 5 de 8 casos probados. **Dos formateadores** de números que redondean distinto. Hay 5 maneras de calcular la familia efectiva y 3 «conteos» con semánticas distintas. Además: dos empaquetadores ZIP (uno respeta la hoja y el otro no), dos `_seguro`, dos `_alcance`, y la conversión casepack→receta duplicada entre la app y la migración 0082. |
| Provisional | No hay TODO, FIXME ni XXX. La compatibilidad con 0081 está muy extendida: 2 modelos congelados, 2 alias, 3 sinónimos, 2 propiedades híbridas, 7 columnas `*_anterior_id`/`familia_id` y 2 `legado_*`. Hay 25 funciones de 60 líneas o más, 11 de ellas de más de 100. |
| Dependencias | `pdfplumber` se usa en 6 archivos de prueba y **no está en `requirements-dev.txt`**: en un entorno limpio las pruebas fallan al importar. `Pillow` se importa en 4 módulos y llega solo de forma transitiva (por reportlab). `zxing-cpp`, `uharfbuzz` y `fonttools` son exclusivos del etiquetado. |
| Pruebas | **114 pasan y 1 se omite en 161,7 s.** Una prueba depende de la zona horaria y **falla con `TZ=America/Guatemala`** [VERIFICADO]. Hay 8 `pytest.skip` que dependen de la demo y aserciones tautológicas. No hay pruebas unitarias de frontend ni CI, y el e2e de Playwright no se pudo ejecutar porque no hay Chromium. |

---

## 1. Código sin uso (con verificación)

| id | Estado | Elemento | Evidencia | Formas de referencia revisadas | Acción | Riesgo |
|---|---|---|---|---|---|---|
| C-01 | [VERIFICADO] | `trabajos._soltar()` | `backend/app/modulos/etiquetado/trabajos.py:676-678` | Ninguna llamada en app, tests ni scripts. `git log -S"_soltar("` muestra que nació en `0bf08ad` sin llamadas. El arriendo se suelta en línea en 3 sitios (`trabajos.py:849`, `:916-918`, `recuperar` `:937`). | **Eliminar**, o usarla en esos 3 sitios para no repetir el `UPDATE`. Lo segundo es preferible. | Nulo |
| C-02 | [VERIFICADO] | `render.vacio()` | `render.py:108` | Sin `render.vacio` ni import de `vacio` en ningún lado (vulture y grep). Existen además otras 3 copias: `campos_logicos._vacio` `:58`, `comun/condiciones._vacio` `:159` (esta trata `[]` como vacío) y `vacio` en `etiquetas.js:426`. | **Eliminar** la de render y unificar en `condiciones._vacio` (ver C-14). | Nulo |
| C-03 | [VERIFICADO] | `campos.por_clave()` | `campos.py:262` | El único `por_clave` en uso es una variable local de `trabajos.py:809`. | **Eliminar** | Nulo |
| C-04 | [VERIFICADO] | `comun.condiciones.cumple()` | `condiciones.py:217` | Nadie la llama: etiquetado, categorías y recetas usan `all(cumple_condicion…)` cada uno por su cuenta (`categorias.py:163`, `arbol.py:58`). | **Conservar y usar** en esos sitios (refactorizar), o eliminar. | Nulo |
| C-05 | [VERIFICADO] | Constantes sin lectura: `ESTADOS_TRABAJO`, `ESTADOS_REGISTRO` (`modelos/etiquetado.py:73-74`), `SIMBOLOGIAS` y `TRANSFORMACIONES` (`diseno.py:27,96`), `DESTINOS_REGLA_EMPAQUE` y `ORIGENES_RECETA` (`modelos/empaque.py:235-236`), `PESO_DESTINO` (`recetas.py:57`), `CUENTA` e `IDENTIFICADORES` (`empaques.py:29-30`), el alias `resumen_pallets` (`packing.py:475`) | — | `diseno.py` repite las listas como `Literal[...]` en `:104` y `:164`; los estados de trabajo y registro no tienen `CheckConstraint`. | **Refactorizar.** Las de etiquetado deben ser la fuente: `Literal[*SIMBOLOGIAS]` y `CheckConstraint(_en("estado", ESTADOS_TRABAJO))` con una migración. Las de empaque y el alias se eliminan. | Bajo. El `CheckConstraint` necesita revisar los datos. |
| C-06 | [VERIFICADO] | `__all__` y re-importaciones en `reglas.py:51-75` | — | De los 16 nombres re-exportados desde `comun/condiciones`, solo se usan `LISTAS`, `NUMERICOS`, `cumple_condicion` (`render.py:183`), `OPERADORES` y `OPERADORES_SIMPLES` (`api.py:42-43`), `validar_patron` (`diseno.py:77`, tests) y `limpiar` (local). `MAX_*`, `SIN_VALOR`, `_numero`, `_patron_cumple`, `_texto` y `_vacio` no los lee nadie a través de `reglas`. | **Refactorizar:** importar directo de `comun.condiciones` y dejar de re-exportar privados (`_x`). | Bajo |
| C-07 | [VERIFICADO] | `reglas.categoria_de()` | `reglas.py:183-188` | Es un pase directo a `grupos.arbol.categoria_de`, con import diferido. Lo usan `categorias.py:56,166`, `familias.py:406` y `usos.py:469`. | **Refactorizar:** llamar a `arbol.categoria_de`. | Nulo |
| C-08 | [VERIFICADO] | `POST /etiquetas/tipos/sugeridos` → `tipos.crear_sugeridos` | `api.py:84-87`, `tipos.py:196-203` | Sin uso en `frontend/src` ni `e2e`, sin pruebas y sin docs. `PrimerUsoEtiquetado.vue:50-53` crea los mismos tipos con N `POST /etiquetas/tipos`, sin atomicidad y con los nombres traducidos (MN-21 sigue vigente). | **Eliminar**, o **refactorizar** para que reciba nombres y lo use la pantalla. Lo segundo es preferible porque hoy un fallo a mitad deja tipos sueltos. | Bajo |
| C-09 | [VERIFICADO] | `POST /etiquetas/trabajos/{id}/cancelar` → `trabajos.cancelar` | `api.py:559`, `trabajos.py:323` | Sin llamada en el frontend (grep de `cancelar` y de plantillas `/trabajos/${…}/`). Solo lo usan las pruebas `test_etiquetado_trabajos.py:252` y `_durable.py:307`. | **Conservar y exponerlo** en el asistente (cancelar un borrador o un EN_PROCESO), o documentarlo como API. | — |
| C-10 | [VERIFICADO] | `GET /etiquetas/usos/{id}/historial` → `usos.historial` | `api.py:165`, `usos.py:140` | Sin pantalla. Lo usan `test_etiquetado_reglas.py:105` y `_aislamiento.py:43`, y aparece en docs. | **Conservar y exponerlo** en `CeldaEtiquetado` (la regla no muestra su historia), o marcarlo como API. | — |
| C-11 | [VERIFICADO] | `GET /etiquetas/resolver` | `api.py:171` | Sin pantalla. Lo usan 7 archivos de prueba, `e2e/etiquetado.mjs` y docs. | **Conservar** como API de diagnóstico; las pruebas dependen de él. | — |
| C-12 | [VERIFICADO] | `usos.TEXTOS_0076` | `usos.py:152` | No tiene lectura en ejecución, pero existe para que `backend/scripts/i18n_extraer.py` (que analiza las cadenas por AST) extraiga los textos de la migración 0076. | **Conservar**, con un comentario que lo diga en el propio extractor. | — |
| C-13 | [VERIFICADO] | `recetas.convertir_existentes()` | `recetas.py:369` | Solo la llama la demo (`demo.py:736-738`). El comentario de la demo dice «como la migración **0081**», pero la migración correcta es la **0082**. | **Conservar** y corregir el comentario (ver D-09). | — |
| C-14 | [VERIFICADO] | Traducciones huérfanas | `frontend/src/i18n/es.json` | Al replicar `scripts/i18n-extraer.mjs` en el scratchpad, `claves.json` sale al día (6602 = 6602), pero `es.json` tiene **7463 entradas, 861 sin clave**; unas 229 parecen de etiquetado o empaque («Another labeling family has this code.», «Bulk label generation», «Batch #{0} ready»…). `test_i18n.py:36` solo comprueba las que faltan, no las que sobran. Lista en `tmp/huerfanas.json`. | **Eliminar** las huérfanas y agregar a `test_i18n` la comprobación de sobrantes. | Nulo |
| C-15 | [VERIFICADO] | Exports de `etiquetas.js` que solo se usan dentro del archivo: `medidaTexto`, `CAMPO`, `sustituir` | — | No los importa nadie de fuera. | **Refactorizar:** quitar el `export`. | Nulo |
| C-16 | [VERIFICADO] | Comentario obsoleto | `config.py:127` | Dice «tope de etiquetas por lote» junto a `ETIQUETAS_CUATRO_OJOS`, pero `ETIQUETAS_MAXIMO_LOTE` se retiró (GN-15). Además, el comentario de `CAMBIOS_INTERVALO_SEG` corta en dos el bloque de las variables del arriendo (`:138-144`). Todas las `ETIQUETAS_*` se usan; `PL_SIN_FINALIZAR` y `VALIDAR_EMPAQUE` no tienen ninguna prueba. | **Refactorizar** el comentario. | Nulo |
| C-17 | [VERIFICADO] | `.pyc` de módulos borrados (`masivo`, `asignaciones`) | `backend/app/modulos/etiquetado/__pycache__/` | Los fuentes ya no existen; son restos locales que git no versiona. | **Eliminar** localmente. | Nulo |

**Verificado como en uso, aunque lo parezca:**
- Todos los componentes y archivos `.vue`/`.js` de `etiquetado`, `empaque` y `grupos` se importan o están en el router.
- `archivar`, `reactivar`, `miniatura.svg`, `fuentes/{archivo}` e `imagenes/{id}` se usan desde URL armadas en `DisenosView.vue:111`, `VersionesEtiqueta.vue:139` y `etiquetas.js:143,312`.
- Las `ETIQUETAS_*` de `config.py`, la tarea periódica `_recuperar_etiquetas` (`main.py:72-89`) y el canal de cambios (genérico por tabla, sin referencias propias) están en uso.

Las rutas de `/packing-lists/*` que no aparecen en el frontend (`/quitar`, `/cancelar`, `/exportar`, `/cajas/eliminar`, `/cajas/{g}/plantilla`) quedan fuera de esta área; se listan en `tmp/rutas.py` para que las revise el auditor de empaque.

---

## 2. Duplicados

| id | Estado | Problema | Evidencia | Impacto | Acción |
|---|---|---|---|---|---|
| D-01 | [VERIFICADO] | **Tres servicios CRUD sobre `grupos_producto`**, con validaciones que se contradicen (detalle debajo de la tabla). | `grupos/arbol.py:166-262` (`_validar`, `crear`, `actualizar`, `eliminar`), `etiquetado/familias.py:114-204`, `etiquetado/categorias.py:71-146` | El mismo nodo se valida distinto según la pantalla y su historial queda partido. | **Refactorizar:** un solo servicio (`arbol`) y que familias y categorías solo adapten. |
| D-02 | [VERIFICADO] | **Tres «conteos» de un nodo con semánticas distintas.** | `arbol._conteos` cuenta solo las asignaciones directas (`arbol.py:96-111`); `familias._conteos` cuenta la familia efectiva heredada (`familias.py:56-76`); `categorias.conteos` evalúa en Python las condiciones de **hasta 20 000 artículos** en cada `listar`, `crear` y `actualizar` (`categorias.py:43-60`, `MAX_PRUEBA`). | «Grupos de producto» y «Etiquetado → Familias» muestran números distintos para el mismo nodo. Hay coste O(artículos) en cada guardado de categoría, y el resultado se trunca en silencio por encima de 20 000. | **Refactorizar:** conteo en SQL, o en caché invalidada por versión de tabla. |
| D-03 | [VERIFICADO] | **Cinco cálculos de la «familia efectiva».** | `Articulo.familia_efectiva` en Python (`maestros.py:498`); `familias.familia_sql()` como COALESCE en SQL (`familias.py:34`); `familias.articulos().fila()` con diccionarios (`familias.py:248-252`); `usos.familia_producto` (`usos.py:493`); `familias.familia_producto_sql` (`:41`). Además, `Articulo.familia_origen` (`maestros.py:509`). Para el grupo, `familia_efectiva` usa `grupo.grupo_producto` sin `.familia`, y para el producto usa `.familia`. | Cualquier cambio de la regla de herencia hay que hacerlo en 5 sitios. No hay ninguna prueba que compare el SQL con el Python. | **Refactorizar** a una sola definición (SQL + Python) y añadir una prueba de paridad. |
| D-04 | [VERIFICADO] | **Escalera de niveles duplicada.** | `reglas.Resolvedor` arma sus niveles (`reglas.py:275-293`: categoría y luego `familia_efectiva.ruta()`), mientras que `grupos.arbol.ruta_efectiva` (`arbol.py:61`) hace lo mismo para las recetas (`recetas.py:598`). | Las reglas de etiqueta y las de empaque pueden divergir. | **Refactorizar:** el resolvedor debe usar `ruta_efectiva`. |
| D-05 | [VERIFICADO, ejecutado] | **Dos evaluadores de condiciones**: `etiquetas.js:460 cumple()`, para la vista del editor (`ElementoSvg.vue:19`), y `comun/condiciones.py:168 cumple_condicion()`, para el PDF. Con 8 casos (`tmp/cond/`) discrepan en 5 (detalle debajo de la tabla). | — | El editor muestra u oculta elementos «Mostrar solo si» distinto de lo que se imprime. | **Refactorizar:** pedir la decisión al servidor (la vista previa ya la dibuja él) o portar la semántica y añadir una prueba de paridad con casos compartidos en JSON. |
| D-06 | [VERIFICADO, ejecutado] | **Dos formateadores** (`render.formatear` `:135` y `etiquetas.js:427`), dos `fecha_con_patron`, dos tablas `MESES` y `SI_NO`, dos `sustituir`. | Con `{'tipo': 'numero', 'decimales': 0}`: 2,5 → Python `"2"` / JS `"3"`; 0,5 → `"0"` / `"1"`. Python redondea al par y JS hacia arriba. Los dos imprimen `"-0"` para −0,4. | El editor muestra un número distinto del impreso. `-0` es un error en ambos. | **Refactorizar:** redondeo explícito (`Decimal` ROUND_HALF_UP en el servidor), tablas compartidas desde `/etiquetas/catalogos` y una prueba de paridad. |
| D-07 | [VERIFICADO] | **Dos empaquetadores de archivos.** | `generacion._producir` (`generacion.py:743-779`) respeta `hoja` y `dpi`; `trabajos.archivo` (`trabajos.py:953-1046`) fuerza `{"modo": "individual"}`. `poner()` del ZIP está copiada, y `_seguro` existe dos veces con reglas distintas (`generacion.py:720` sin espacios y sin respaldo, que puede devolver `""`; `trabajos.py:949` con espacios, `strip` y `"_"`). A eso se suma `adjuntos.nombre_seguro`. | El mismo lote sale en hojas de varias etiquetas desde el historial y en una por página desde el trabajo (G-07). | **Refactorizar** a un solo empaquetador. |
| D-08 | [VERIFICADO] | Dos `_alcance(user)` para el proveedor con reglas distintas: el trabajo exige `creado_por`, la generación acepta `creada_por` o la OC del proveedor. | `trabajos.py:84`, `generacion.py:790` | Un proveedor ve una ejecución de su OC creada por el equipo interno, pero no su trabajo. Puede ser intencional; no está documentado. | **Conservar y documentar**, o unificar en `acceso.visibilidad`. |
| D-09 | [VERIFICADO] | **casepack → receta en dos implementaciones** (detalle debajo de la tabla). | `recetas.convertir_existentes` (ORM, `recetas.py:369`, usada por la demo) y `0082._convertir` (SQL, `0082_recetas_de_empaque.py:175-236`). | La demo no reproduce lo que hace la migración en producción, y la prueba `test_la_demo_convierte_el_casepack_en_recetas` no detecta la diferencia. | **Conservar** la migración congelada; probar la migración con datos que expongan la diferencia de `factura_lineas`. |
| D-10 | [VERIFICADO] | **Dos fuentes de «lo planificado» en el empaque.** | `empaque_etiquetas.revisar` (`:29-35`) compara contra `PosicionOC.casepack/inner_pack`; desde 0082 la verdad es `receta_foto` con N niveles, y `casepack` solo se deriva de ella (`recetas.derivar` `:93`, `poner` `:667`). | Con una receta de 3 niveles (inner → caja → pallet) solo se revisan dos. Un PL armado con la receta puede dar una advertencia `casepack_distinto` falsa si la OC trae otro casepack ([SOSPECHA] en este segundo punto). | **Refactorizar:** revisar contra la foto de la receta. |
| D-11 | [VERIFICADO] | **Validaciones frontend/backend desalineadas.** Los formularios de familia y categoría (`FormFamilia.vue:38`, `CategoriasFamilia.vue:132`, `GruposProductoView.vue:189`) no tienen `pattern`, y el backend aplica dos reglas distintas (D-01). Los tipos y campos lógicos sí coinciden (`TiposEtiqueta.vue:125` y `tipos.py:22`; `CamposEtiqueta.vue:95` y `campos_logicos.py:30`). | — | — | **Refactorizar** con la regla de `arbol`, idéntica en el `pattern`. |
| D-12 | [VERIFICADO] | **Primer uso duplicado:** la pantalla hace N llamadas no atómicas (C-08) mientras existe un servicio atómico sin usar. | — | — | Ver C-08. |

**D-01, contradicciones de validación entre los tres servicios:**
- **Código.** `familias` y `arbol` usan `str.isalnum()` (Unicode), mientras que `categorias` usa `^[A-Z0-9][A-Z0-9_.-]{0,19}$`. Comprobado: `"NIÑO"` es válido como familia o en Grupos y se rechaza como categoría. Una categoría creada en «Grupos de producto» con «Ñ» no se puede volver a guardar desde Etiquetado.
- **Orden.** `familias` exige un `int` ≥ 0; `arbol` y `categorias` aceptan `"5"` y recortan a 0 los negativos.
- **Descripción.** `familias` da 422 por encima de 300 caracteres; las otras dos truncan en silencio.
- **Padre.** `arbol` hace `int(padre_id)` sin `try` y `familias` hace `db.get` sin convertir. [SOSPECHA] Un valor no numérico da 500 en Grupos.
- **Historial.** Para el mismo nodo se registra como `"familia_etiquetado"`/`"categoria_etiquetado"` o como `"grupo_producto"`, así que el historial de un nodo queda partido en dos entidades.
- **Permisos.** `familias` y `categorias` exigen `etiquetas.familias`; `arbol` admite `catalogos.editar` o `etiquetas.familias`. Quien tiene `catalogos.editar` edita las familias de etiquetado sin el permiso de etiquetado.

**D-05, casos en que discrepan los evaluadores:**

| Caso | Python (impresión) | JS (editor) |
|---|---|---|
| `igual "10"` contra `"10.0"` | true | false |
| `vacio` sobre `[]` | true | false |
| `mayor 0` sobre `true` | false | true |
| `coincide "(a+)+b"` | false (rechaza el patrón inseguro) | true; además el navegador evalúa sin protección contra ReDoS |
| `en ["1"]` sobre `1.0` | false | true |

**D-09, diferencias entre las dos implementaciones de casepack → receta:**
- La migración actualiza **todas** las `factura_lineas` de la organización con ese casepack e inner, aunque no sean de la posición. La app solo toca las líneas de cada posición.
- La migración reutiliza la receta por código aunque la hayan editado; la app crea otro código.

---

## 3. Código provisional, compatibilidad y funciones largas

**C-18 [VERIFICADO] · Compatibilidad con 0081 extendida por los modelos.** No hay TODO, FIXME, XXX ni «temporal» en el área. La deuda de compatibilidad es la siguiente:
- **Modelos congelados:** `FamiliaEtiquetadoAnterior` y `CategoriaEtiquetadoAnterior` (`modelos/etiquetado.py:94-166`). Según su docstring, «nada la lee ni la escribe». Siguen en `modelos/__init__.py:75-78,149-152` y en `referencias.py:80-96`.
- **Alias:** `FamiliaEtiquetado = GrupoFamilia` y `CategoriaEtiquetado = GrupoCategoria` (`modelos/etiquetado.py:114-115`), usados en 6 módulos.
- **Sinónimos:** `familia_etiquetado_id`/`familia_etiquetado` en `GrupoArticulo` (`maestros.py:419-420`) y en `Articulo` (`:494-495`), y `GrupoCategoria.familia_id = synonym("padre_id")` (`grupos.py:88`).
- **Propiedades híbridas con setter de lógica propia:** `Producto.familia_etiquetado_id` y `categoria_etiquetado_id` (`productos.py:111-160`). Una «familia» que puede guardar una categoría es la semántica más difícil de mantener.
- **Columnas congeladas:** 7 `*_anterior_id` con nombre físico viejo (`usos_diseno.familia_id`/`categoria_id`, `generacion_items.familia_id`, `productos.familia_etiquetado_id`/`categoria_etiquetado_id`, `articulos` y `grupos_articulos.familia_etiquetado_id`). Hay además `legado_familia_id`/`legado_categoria_id` (`grupos.py:55-56`). Las FK hacia tablas congeladas siguen activas.
- **Riesgo.** Mantener las tablas «solo para volver atrás» hace que cada cambio de esquema tenga que conservar la reversibilidad de 0081.

**Acción.** Fijar una fecha de corte. Antes de ella:
1. Renombrar en el código los alias y sinónimos a `grupo_*`; son unos 60 usos según el grep de §1.
2. Mover la lógica de las propiedades híbridas a `grupos.arbol`.

Después del corte, una migración 0083 que borre las tablas y columnas congeladas y declare que 0081 no se revierte.

**Dependencias verificadas que se deben conservar:** `test_grupos_producto.py:107-207` usa las tablas congeladas para probar el *downgrade*, y la migración 0081 las lee. Si se eliminan, esas pruebas pasan a cubrir el corte.

**C-19 [VERIFICADO] · Funciones largas (≥ 80 líneas; las de 60-79 están en `tmp/largas.py`).**

| Líneas | Función | Comentario |
|---|---|---|
| 213 | `alembic/0076…:130 upgrade` | Migración congelada: **conservar** |
| 201 | `alembic/0070…:58 upgrade` | Migración congelada: **conservar** |
| 163 | `empaque/packing.py:1264 detalle_pl` | Refactorizar (armado de respuesta y cálculos) |
| 156 | `alembic/0073…:76 upgrade` | Migración congelada: conservar |
| 128 | `alembic/0082…:45 upgrade` | Migración congelada: conservar |
| 126 | `etiquetado/generacion.py:413 planear` | Complejidad ciclomática 30 (ruff C901): **refactorizar** en armar, elegir versión, revisar y dibujar |
| 122 | `alembic/0076…:453 downgrade` | Migración congelada: conservar |
| 120 | `empaque/estructura_pl.py:55 importar_estructura` | Refactorizar |
| 111 | `instalacion/demo_etiquetado.py:92 sembrar` | Aceptable (guion de datos) |
| 110 | `etiquetado/render.py:772 _tabla` | Complejidad 28: refactorizar |
| 106 | `etiquetado/usos.py:741 matriz` | Complejidad 24: refactorizar |
| 101 | `etiquetado/trabajos.py:519 _validar` | Refactorizar |
| 100 | `alembic/0076…:351 _convertir_reglas` | Migración congelada: conservar |
| 94 | `etiquetado/trabajos.py:953 archivo` | Complejidad 23. Se unifica con D-07. |

En el frontend: `TrabajoEtiquetasView.vue` (1092 líneas, 619 de script), `PackingListView.vue` (1172, 554 de script) y `LienzoEtiqueta.vue` (393 de script). **Refactorizar** en composables: estado del asistente, generación y descarga.

---

## 4. Dependencias

| id | Estado | Hallazgo | Acción |
|---|---|---|---|
| C-20 | [VERIFICADO] | **`pdfplumber` no está declarado.** Lo importan `tests/etiquetado_util.py:6`, `test_etiquetado_generacion.py:10`, `_origenes.py:9`, `_render.py:7` y `_trabajos.py:18`. `pip install --dry-run --ignore-installed -r requirements-dev.txt` resuelve 51 paquetes, sin `pdfplumber` (`tmp/reporte_dev.json`). En un entorno limpio, 6 archivos de prueba fallan al recolectarse. Solo pasan aquí porque el paquete ya estaba instalado. | Añadir `pdfplumber>=0.11` a `requirements-dev.txt`. |
| C-21 | [VERIFICADO] | **`Pillow` es implícita.** Se importa en `render.py:437,447`, `salidas.py:257,294,303`, `plantillas.py:491` y `verificacion.py:54`, pero no está en `requirements.txt`: llega como dependencia de reportlab. `salidas` usa `ImageFont` con escrituras complejas, lo que depende de libraqm (DN-08). | Declarar `pillow>=10` (y documentar libraqm). |
| C-22 | [VERIFICADO] | Exclusivas del etiquetado: `zxing-cpp` (`codigos.py:58`, `verificacion.py`), `uharfbuzz` (`escritura.py`) y `fonttools` (`escritura.py`, `salidas.py`). `reportlab` la comparte `documentos/documentos.py`; `anthropic` es de clasificación y `openpyxl`, de documentos. No hay paquetes declarados sin uso. En el frontend solo están `vue` y `vue-router`; `playwright` solo se usa en `e2e/`. | Conservar. Si el etiquetado pasa a ser opcional, moverlas a un extra `[etiquetado]`. |

---

## 5. Inventario de pruebas, resultado real y huecos

### 5.1 Ejecución

**Suite del área:** `python -m pytest -q tests/test_etiquetado_*.py tests/test_grupos_producto.py tests/test_empaque_recetas.py tests/test_empaques.py`.
- Resultado: **114 pasan, 1 se omite y 0 fallan, en 161,74 s** (2 min 54 s reales).
- La omitida es `test_etiquetado_durable.py:323` («RLS solo existe en PostgreSQL»); no hay `TEST_DATABASE_URL`.
- Lo más lento:
  - creación y siembra de la base: 28,0 s;
  - pruebas de migración: 0076 27,6 s, 0081 24,6 s y 0082 23,2 s (≈ 47 % del tiempo);
  - `test_lote_grande_y_tope`: 6,9 s.

**Archivos por separado** (cada uno en su propia base): ver §5.5.

**Con otra zona horaria:** `TZ=America/Guatemala pytest tests/test_etiquetado_durable.py -k "reinicio or perdio or intentos"` da **1 fallo y 3 pasan**: `test_reinicio_otra_instancia_retoma_y_no_roba_un_arriendo_vigente` (`:196`, `assert … 7 not in [7, 8, 9]`). Ver T-01.

**Frontend:**
- `npx eslint src/modulos/{etiquetado,empaque,grupos}`: sin errores.
- `node --check e2e/etiquetado.mjs`: sintaxis correcta.
- El **e2e no se pudo ejecutar**: no hay Chromium y `npx playwright install chromium` falla en la descarga (red). No hay vitest ni pruebas unitarias de componentes, ni CI (no existe `.github/`), así que nadie ejecuta los e2e de forma automática.

**Totales:** 91 pruebas en `test_etiquetado_*`, más 5 en grupos, 9 en recetas y 4 en empaques.

### 5.2 Qué cubre cada archivo

| Archivo | Pruebas | Cubre | No cubre |
|---|---|---|---|
| `test_etiquetado_aislamiento` | 2 | Otra empresa no ve ni usa nada; FK compuestas | Vista previa de ejemplo con datos de otro proveedor (GN-02/MN-01) |
| `_anular` | 2 | Anular deja pendientes; reimprimir por rangos con motivo | Reimprimir de forma idempotente (GN-20); que anular no deje un «ya generada» vivo (GN-05) |
| `_configurable` | 3 | Nombres propios y ocultos; completar un dato maestro; «datos_cambiaron» con 409 | Que valores manuales o el diseño elegido no disparen 409 (GN-07); huella > 200 caracteres |
| `_contenido` | 6 | Campos lógicos y política; tablas, totales y desborde; serie; **prepack/KIT** con componentes y sin ellos | Política BLOQUEAR con un campo que el diseño no usa (GN-09); `contenedor` con reparto no exacto (GN-08) |
| `_durable` | 9 | Toma atómica, arriendo perdido, sin duplicados, reintentos simultáneos, aislamiento, RLS (solo PG, aquí omitida) | Corre solo en UTC (T-01); cancelar un EN_PROCESO; pool de ejecutores |
| `_familias` | 7 | CRUD, asignación, herencia producto→talla, asistente atómico | Paridad SQL/Python de la familia (D-03); validaciones divergentes (D-01) |
| `_generacion` | 12 | Por línea, unidad y manual; ZIP; hoja que no cabe; **sin diseño aprobado**; **versión sin aprobar = PRUEBA**; unidades no contables o nuevas; reproducción de un lote histórico; tope; proveedor | **Cantidades decimales, cero o nulas** en `POR_LINEA`/`MANUAL`; mezcla de prueba y real (GN-13); `dpi`/`hoja` inválidos (GN-06) |
| `_integracion` | 3 | Generar no modifica OC, PL ni recepción; pedido ≠ empacado; ver ≠ descargar | La parte de PL es condicional y acepta 422 (T-04) |
| `_motor_reglas` | 4 | Categorías, «no lleva», dónde va, prioridad | Condiciones sobre `logico.*`/`contexto.*` (GN-03) |
| `_origenes` | 6 | OC de una familia (artículo repetido en dos líneas → una etiqueta); artículos sueltos; PL por nivel; campos al generar; bultos de PL distintas | **OC con dos PL** y **PL consolidada A+B** (GN-01); `POR_UNIDAD` sumando unidades distintas (GN-10) |
| `_plantillas` | 7 | Ciclo de versiones, cuatro ojos, duplicar, cuál gana, vista previa, imágenes | Archivar un diseño en uso cambia lo impreso (MN-08) |
| `_reglas` | 5 | Escalera, celda con firma (409), matriz, tipos, patrones seguros | Permiso del proveedor en la matriz (T-03) |
| `_render` | 12 | Medidas reales en PDF, PNG y SVG; lectura de códigos con zxing; texto y escrituras complejas; hoja; giro | GS1 con FNC1 y dígito verificador (DN-01/02); ITF-14 legible (DN-03) |
| `_resolucion_casos` | 5 | Empate de excepciones, solapes, vigencias, familia inactiva, informe 0076 | Varias reglas que coinciden en celdas distintas con `prioridad` y `NO_LLEVA` a la vez |
| `_trabajos` | 8 | Varias OC con borrador, parcial y reintento; mismo servicio para todas las entradas; segundo plano; migración 0076; retomar; PDF único o con medidas distintas | Fallo de una parte en segundo plano sin detener las demás (G-04) |
| `test_grupos_producto` | 5 | Árbol compartido; regla de empaque por categoría; aislamiento; migración 0081 con vuelta atrás | El mismo nodo editado desde las dos pantallas (D-01) |
| `test_empaque_recetas` | 9 | Receta de N niveles; reglas; OC sin casepack; migración 0082; armar el PL según la receta | Impacto real de dar de baja una regla (aserción tautológica, T-02); etiquetas de bulto con una receta de 3 niveles (D-10) |

### 5.3 Escenarios críticos pedidos: estado de cobertura

| Escenario | Estado |
|---|---|
| OC con varias posiciones del mismo artículo | **Parcial**: solo en el modo «una por artículo» de una familia (`_origenes.py:67`). Falta `POR_UNIDAD` con la suma, el alcance `LINEA` frente a `POSICION_OC` y unidades distintas (GN-10). |
| Artículo en varias OC | **Parcial**: `_origenes` (registros por OC). Falta el mismo artículo en dos OC del mismo trabajo con `alcance=ARTICULO` y `PRODUCTO`. |
| Prepacks y kits con curvas | **Cubierto en el contenido del bulto** (`_contenido.py:234-300`). Falta la etiqueta de artículo de un prepack `POR_UNIDAD` (¿curvas o pares?) y la CURVA con tallas. |
| Packing incompleto o inexistente | **Parcial**: `sin_contenido` y PL en borrador (`_origenes`). Falta la OC sin PL en origen OC por bulto, la PL consolidada y el bulto parcial con la receta. |
| Datos maestros modificados después de generar | **Cubierto**: reproducción histórica y 409 «datos_cambiaron». Falta el segundo plano (GN-04). |
| Cantidades nulas, cero o decimales | **Hueco.** Solo la unidad no contable o fraccional en `POR_UNIDAD`. No se prueba `MANUAL` = 0 o negativo, `cantidad` nula en la línea, ni decimales en el bulto o el PL. `test_cantidades_decimales.py` no toca el etiquetado (grep sin coincidencias). |
| Reglas que coinciden con varios diseños | **Cubierto** dentro de una celda (empate). **Hueco** con prioridad entre clases y con `NO_LLEVA`. |
| Diseños sin aprobar o sin versión vigente | **Cubierto** (`_generacion` 2 pruebas). Falta archivar la vigente (MN-08). |
| Fallos de generación o impresión | **Parcial**: error en una parte e intentos agotados. Falta fallo de escritura del archivo, ZIP grande y confirmar una impresión con una cantidad distinta. |
| Permisos de proveedor | **Parcial**, y con aserciones débiles (T-03). Falta que el proveedor no vea datos ajenos en la vista previa de ejemplo ni en las miniaturas (GN-02) ni enumere proveedores (MN-04). |
| Operaciones simultáneas | **Cubierto** en la ejecución durable y la celda (409). Falta: dos usuarios con el mismo borrador de trabajo, `reimpresiones` concurrentes (MN-25) y edición de grupos desde dos pantallas. |
| Consistencia etiqueta ↔ registros originales | **Parcial**: la instantánea se reproduce y no se modifican los originales. Falta: **GN-01**, dos etiquetas para la misma caja física en un trabajo de varias OC. |
| Pruebas de frontend | **Ninguna automática.** Solo `e2e/etiquetado.mjs` y `recorrido.mjs`, manuales, con la demo levantada y sin CI. No hay prueba de paridad JS↔Python (D-05, D-06). |

### 5.4 Pruebas débiles, acopladas o desactualizadas

| id | Estado | Problema | Evidencia | Acción |
|---|---|---|---|---|
| T-01 | [VERIFICADO, ejecutado] | **Depende de la zona horaria.** Las pruebas escriben arriendos con `datetime.now()` (hora local), y el servicio compara en UTC (`trabajos._ahora` → `modelos/base.ahora()` UTC). En UTC−6 el arriendo «vigente» ya venció, y la prueba falla. En UTC+N fallaría `_vencer`. | `test_etiquetado_durable.py:83,185,193`; también `test_etiquetado_trabajos.py:388,392` | Usar `app.modelos.base.ahora()` en las pruebas y agregar una corrida con `TZ` distinto. |
| T-02 | [VERIFICADO] | Aserción tautológica `imp["revisadas"] >= 0 and imp["cambian"] >= 0`. | `test_empaque_recetas.py:118` | Afirmar los números esperados (la regla del SKU afecta a N posiciones). |
| T-03 | [VERIFICADO] | `tnf.get("/etiquetas/matriz").status_code in (200, 403)` acepta cualquiera de los dos, justo donde hay un problema de visibilidad abierto (MN-04). | `test_etiquetado_reglas.py:177` | Decidir el contrato y afirmar un solo código y el contenido filtrado. |
| T-04 | [VERIFICADO] | La parte de PL solo corre `if pls:` y acepta `status_code in (200, 422)`. Puede no probar nada y sigue pasando. | `test_etiquetado_integracion.py:61-67`; también `_configurable.py:112` (`in (200, 409)`) | Usar fixtures propias de PL y un resultado único. |
| T-05 | [VERIFICADO] | **8 `pytest.skip` que dependen de la demo** («no packing lists with packages», «two POs with items are needed»…). Si la demo cambia, las pruebas se omiten en silencio en lugar de fallar. | `etiquetado_util.py:94`; `_trabajos.py:46,240`; `_origenes.py:133,275`; `_durable.py:50`; `_contenido.py:239` | Fixtures que creen su OC, PL, tarima, caja mixta y PL consolidada (como en G-§e.1). Un `skip` debería ser un `fail`. |
| T-06 | [VERIFICADO] | Acopladas a datos fijos de la demo: los números de OC `"4400003901..03"`, el proveedor «The North Face» y los códigos sugeridos `COLGANTE`/`CAJA`. | `test_grupos_producto.py:61`; `test_etiquetado_origenes.py:66`; `test_etiquetado_reglas.py:184` | Leer de fixtures o de la API, sin literales. |
| T-07 | [VERIFICADO] | **Estado compartido entre pruebas.** Una sola base por sesión; las pruebas reemplazan diseños `GENERAL` (`"reemplazar": True` en `etiquetado_util.uso`), cambian familias de grupos de la demo y las restauran en el `finally` o el *teardown* del fixture. Si una falla a mitad, contamina a las siguientes. | `etiquetado_util.py:38`; `test_etiquetado_origenes.py:41-51` | Transacción o *savepoint* por prueba, o base por módulo. Por separado, cada archivo sí pasa (§5.5). |
| T-08 | [VERIFICADO] | Pruebas de concurrencia con aserciones laxas: `resultados.count("ok") >= 1`. La invariante (sin duplicados) sí se afirma después, así que es aceptable, pero no se afirma qué recibieron los perdedores. | `test_etiquetado_durable.py:276` | Afirmar `== 1` «ok» y que los demás reciben `en_proceso`/409. |
| T-09 | [VERIFICADO] | `test_la_base_rechaza_filas_que_cruzan_empresas` no tiene `assert`; usa `pytest.raises`, lo cual es válido. En SQLite solo prueba la FK compuesta, no RLS. | `test_etiquetado_aislamiento.py:66-80` | Ejecutar la suite también en PostgreSQL (`TEST_DATABASE_URL`) en CI. |
| T-10 | [VERIFICADO] | Pruebas de migración caras (≈ 75 s de 162 s) dentro de la suite rápida. | `--durations` | Marcarlas con `@pytest.mark.migracion` y ejecutarlas aparte o en *nightly*. |
| T-11 | [SOSPECHA] | `test_la_demo_convierte_el_casepack_en_recetas` afirma que la demo hace lo mismo que la 0082, pero las dos implementaciones difieren (D-09) y la prueba no lo detecta. | `test_empaque_recetas.py` | Ver D-09. |

### 5.5 Archivos ejecutados por separado

Cada archivo se corrió solo, con su propia base SQLite y 6 en paralelo. **Todos pasan; no hay dependencia del orden entre archivos.**

| Archivo | Resultado | Tiempo |
|---|---|---|
| `test_empaque_recetas` | 9 pasan | 92,7 s |
| `test_etiquetado_aislamiento` | 2 pasan | 46,4 s |
| `_anular` | 2 pasan | 47,8 s |
| `_configurable` | 3 pasan | 47,1 s |
| `_contenido` | 6 pasan | 54,0 s |
| `_durable` | 8 pasan, 1 omitida | 51,7 s |
| `_familias` | 7 pasan | 43,2 s |
| `_generacion` | 12 pasan | 64,9 s |
| `_integracion` | 3 pasan | 45,7 s |
| `_motor_reglas` | 4 pasan | 48,7 s |
| `_origenes` | 6 pasan | 48,7 s |
| `_plantillas` | 7 pasan | 45,0 s |
| `_reglas` | 5 pasan | 43,6 s |
| `_render` | 18 pasan (12 funciones, algunas parametrizadas; no usa la demo) | 4,6 s |
| `_resolucion_casos` | 5 pasan | 37,1 s |
| `_trabajos` | 8 pasan | 67,8 s |
| `test_grupos_producto` | 5 pasan | 61,0 s |

Casi todo el tiempo de cada archivo (≈ 30-40 s) es crear y sembrar la base de la demo. Esto confirma que las pruebas dependen de la demo (T-05, T-06): solo `_render` es independiente.

---

## 6. Plan de pruebas propuesto

Las prioridades 1 a 3 corrigen la base de las pruebas; las demás cierran los huecos de §5.3.

**0. Infraestructura (antes que nada).**
- Añadir `pdfplumber` a `requirements-dev.txt` (C-20).
- CI con dos trabajos: SQLite con `TZ=America/Guatemala` (T-01) y PostgreSQL (RLS, T-09).
- Marcador `migracion` (T-10).
- Fixture `escenario_empaque` que cree:
  - OC-A y OC-B del mismo proveedor, con el mismo artículo en 2 posiciones y en las dos OC;
  - PL-1 de solo A, PL-2 de A y B consolidada, y PL-3 en borrador;
  - inner 3 dentro de una caja de 10 (reparto no exacto), tarima con 2 cajas y caja mixta;
  - prepack CURVA (2-2-1) y KIT;
  - una línea en kg con 2,5, una en PAR con 0 y otra con la cantidad nula.

  Con esa fixture desaparecen los 8 `skip` (T-05).

**1. Unitarias (rápidas, sin demo).**
- `comun.condiciones`: tabla de casos compartida en `tests/datos/condiciones.json`, que se ejecuta también contra `etiquetas.js` (D-05).
- `render.formatear` frente a `etiquetas.formatear` con los mismos casos: 2,5, 0,5, −0,4, fechas y regional (D-06).
- `grupos.arbol._validar` como única validación: «NIÑO», orden `"5"`/−1, descripción de 301 caracteres y padre `"x"` (D-01).
- `recetas.derivar` con recetas de 1, 2 y 3 niveles; `empaque_etiquetas.revisar` contra la foto (D-10).
- Paridad de `familia_sql()` con `Articulo.familia_efectiva` en 4 casos: propia, producto, grupo y categoría a mano (D-03).

**2. Integración (servicios con base).**
- `test_oc_con_dos_pl_y_pl_consolidada_sin_cajas_ajenas_ni_dobles` (GN-01): un trabajo de OC-A y OC-B desde PL-2 genera exactamente las cajas físicas una vez.
- `test_misma_articulo_varias_posiciones_por_unidad_suma_y_alcance`: alcance `LINEA`, `POSICION_OC` y `ARTICULO`, con totales exactos; unidades distintas → error (GN-10).
- `test_cantidades_cero_nulas_decimales`: `MANUAL`=0 → 422 o registro omitido; cantidad nula en la línea → error claro; 2,5 kg `POR_LINEA` → 1, y `POR_UNIDAD` → error.
- `test_prepack_curva_por_unidad`: decidir si se etiqueta por curva o por par y afirmarlo.
- `test_reglas_varias_coinciden_prioridad_y_no_lleva`: familia `USAR` p=0, categoría `NO_LLEVA` p=5 y excepción de proveedor; resultado exacto.
- `test_archivar_vigente_cambia_lo_impreso_y_avisa` (MN-08).
- `test_segundo_plano_datos_cambiaron_y_registro_borrado` (GN-04) y `test_parte_con_error_no_detiene_las_demas` (G-04).
- `test_zip_trabajo_y_lote_iguales_con_hoja` (D-07 / G-07).
- `test_demo_y_migracion_0082_dan_las_mismas_recetas` sobre el mismo conjunto (D-09).

**3. API y permisos.**
- Proveedor: la matriz da 403 o se filtra (T-03); las miniaturas y la vista previa de ejemplo no muestran OC ajenas (GN-02); `/etiquetas/resolver` y `/usos/simular` quedan acotados (MN-04).
- `dpi`/`hoja` inválidos → 422 (GN-06); clave de idempotencia repetida en `reimprimir` (GN-20).
- Mismo nodo editado por `/grupos-producto` y `/etiquetas/familias`: mismas reglas e historial unificado (D-01).
- `catalogos.editar` sin `etiquetas.familias` no cambia la configuración de etiquetado (o se decide que sí, y se documenta).
- Concurrencia: dos `PATCH /etiquetas/trabajos/{id}` con la misma `version` → uno 409; dos `reimprimir` a la vez → las dos quedan en `reimpresiones` (MN-25).

**4. Interfaz.**
- Vitest + @vue/test-utils (sin red) para `etiquetas.js`: paridad D-05 y D-06 y `condicionesLimpias`.
- Para `TrabajoEtiquetasView`: paso guardado, 0 líneas ≠ toda la OC (UN-12) y bloqueo de «Siguiente» con errores.
- Para `PrimerUsoEtiquetado`: un fallo a mitad no deja tipos sueltos (C-08).
- Para `CeldaEtiquetado`: guardado atómico (UN-01/03).
- Playwright `e2e/etiquetado.mjs` en CI con la demo, a 1440 px y a 390 px (UN-05/06), con Chromium preinstalado en la imagen.

**5. Regresión.**
- Una prueba por hallazgo corregido, con el id (GN-xx, MN-xx, D-xx) en el nombre o el docstring.
- *Snapshot* de huella sha256 de 3 lotes de referencia (artículo, bulto y documento) que avisa si cambia el dibujo.
- Prueba de consultas con techo (contador de sentencias) para `categorias.listar` (D-02), `familias.articulos`, `planear` de 100 líneas y `matriz`.
- `test_i18n`: falla con claves sobrantes en `es.json` (C-14).

---

### Rutas relevantes

- Informe: `/tmp/claude-0/-home-user-facturacion/0fef4306-34be-5b68-a96c-ecdcee70a452/scratchpad/auditoria/C-codigo-pruebas.md`
- Scripts y salidas: `/tmp/claude-0/-home-user-facturacion/0fef4306-34be-5b68-a96c-ecdcee70a452/scratchpad/auditoria/tmp/`
  - referencias cruzadas: `xref2.py`, `rutas.py`, `largas.py`;
  - paridad JS/Python: `cond/`;
  - traducciones huérfanas: `huerfanas.json`;
  - resolución de dependencias: `reporte_dev.json`;
  - corrida completa: `pytest_etiq.txt`;
  - corridas aisladas: `individual3/`.
