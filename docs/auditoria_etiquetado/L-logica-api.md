# Auditoría L: lógica de negocio, flujo y API del etiquetado

Repositorio `/home/user/facturacion`, commit `3b9d8b5`. La auditoría fue de **solo lectura**: no se cambió ningún archivo del repositorio.

Las rutas son relativas a `backend/app/modulos/etiquetado/`, salvo que se indique otra.

Para confirmar comportamientos escribí pruebas propias, que pasaron (12 de 12). Están en `/tmp/claude-0/-home-user-facturacion/0fef4306-34be-5b68-a96c-ecdcee70a452/scratchpad/auditoria/tmp/pruebas/test_auditoria_l.py`. Usan el `conftest` del proyecto, con SQLite y datos de demostración.

Etiquetas de verificación:
- **[VERIFICADO-prueba]**: confirmado ejecutando una prueba.
- **[VERIFICADO-código]**: confirmado por lectura directa del código.
- **[SOSPECHA]**: probable, sin confirmar.

---

## 1. Flujo real, de punta a punta

| # | Paso | Dónde (archivo:línea) | Qué hace de verdad |
|---|---|---|---|
| 1 | **Elegir el origen** | `OrdenView.vue`, `OrdenesView.vue`, `ResumenEtiquetas.vue`, `EtiquetadoProducto.vue` e `ImprimirView.vue` crean el trabajo. Búsquedas: `buscadores.py:168-232` (OC por familia y PL con sus niveles). | En la OC, «cuánto saldría» viene de `GET /etiquetas/resumen` (`generacion.py:889-938`): usa **todos** los tipos activos y `dibujar=False`. |
| 2 | **Crear el trabajo** | `api.py:505-509` → `trabajos.crear` `trabajos.py:255-269` → `_limpiar` `151-207` | Comprueba el alcance de las OC, artículos y PL (`datos.py:14-35`, `generacion.py:138-145`). **No valida** `dpi`, `hoja`, `manuales`, `cantidades` ni `posiciones`. Sin `tipos`, usa los **obligatorios** del origen (`tipos_por_defecto` `244-251`). |
| 3 | **Guardar el borrador** | `trabajos.actualizar` `294-320` | Usa `version` optimista y `FOR UPDATE`. Si cambian los parámetros, el trabajo vuelve de VALIDADO a BORRADOR. |
| 4 | **Validar** | `api.py:524` → `trabajos.validar` `423-431` → `_validar` `519-619` | Arma una «parte» por OC, una para la PL o una para los artículos (`_partes` `210-241`) y llama a `generacion.planear` en cada una. |
| 4a | Registros por origen | `generacion.armar` `363-399` y `_grupos_articulo` `198-272`, `_grupos_bulto` `275-317`, `_grupos_documento` `320-350` | La regla se decide **aquí**, por registro fino, con `_Decide` (`170-190`, `reglas.Resolvedor.elegir` `reglas.py:314-349`). Decide el diseño, si la etiqueta va o no, dónde va y cuántas salen. |
| 4b | Datos y diseño | `planear` `413-538` | Cada registro pasa por estos pasos, en orden: <ul><li>`datos.valores` (`datos.py:38-58`) y después `contexto.*`.</li><li>Campos lógicos (`campos_logicos.py:62-83`).</li><li>Diseño elegido a mano (`453-460`).</li><li>Versión vigente (`_version_de` `402-410`).</li><li>Variables manuales (`492-494`).</li><li>Serie de vista previa con `proximo` (`505-511`).</li><li>Obligatorios de la familia, solo como advertencia (`512-514`).</li><li>Dibujo con `render.componer` (`515-518`).</li><li>«Ya generada» (`_previas` `541-586`).</li></ul> |
| 4c | Lector y resumen | `_muestras` `410-420`; inserción de registros `560-575`; resumen `605-613` | Lee con zxing una muestra por diseño (máximo 20). Los registros GENERADO se conservan y los demás se reemplazan. Se guarda `revisado` (la huella de lo que se imprimirá). |
| 5 | **Completar datos** (opcional) | `trabajos.completar` `441-481` | Escribe en el maestro de artículos (UPC, SKU del proveedor, peso o unidad) con `catalogos.actualizar` y vuelve a validar. |
| 6 | **Vista previa de un registro** | `trabajos.vista_previa` `1201-1226` | Vuelve a ejecutar `planear` sobre la parte completa y dibuja solo un registro. |
| 7 | **Generar** | `api.py:544-550` → `trabajos.generar` `726-799` | <ol><li>Vuelve a validar todo (`741`).</li><li>Revisa errores y la generación parcial (`742-759`).</li><li>Revisa `datos_cambiaron` (`760-774`).</li><li>Pide confirmar advertencias, con un booleano para todas (`775-779`).</li><li>Con 2000 etiquetas o más (regla `ETIQUETAS_ASINCRONO_DESDE`, valor 2000) pasa a segundo plano: EN_PROCESO, `lanzar` (`855-865`) y `_ejecutar_tomado` (`894-922`), con arriendo y latido (`633-711`).</li><li>Si no, genera en la misma petición con `_ejecutar` (`802-852`).</li></ol> |
| 7a | Persistir | `generacion.producir` `590-657` | <ul><li>Crea `GeneracionEtiquetas` y un `GeneracionItem` por registro, con la versión y la instantánea de valores.</li><li>`reservar` toma los números de serie con `FOR UPDATE` (`633-638`, `core/numeracion.py:89-100`).</li><li>Dibuja el archivo y guarda su sha256 (`650-651`). El archivo **no se guarda**.</li></ul> |
| 8 | **Descargar** | Lote: `generacion.archivo` `873-886` → `_producir` `743-779`. Trabajo (ZIP): `trabajos.archivo` `953-1046`. | Siempre vuelve a dibujar desde la instantánea, en la misma petición. Son **dos empaquetadores distintos**: el ZIP del trabajo ignora `hoja` (`1034`). Cuenta las descargas (`marcar_descarga` `865-870`). |
| 9 | **Imprimir** | `confirmar_impresion` `trabajos.py:1107-1136` | Confirmación manual: cantidad, impresora y observación. Exige una descarga previa. **No hay ZPL ni impresión directa** (grep sin resultados). |
| 10 | **Historial, anular y reimprimir** | `generacion.listar` `833-857`; `anular` `trabajos.py:1146-1174`; `reimprimir` `1177-1198` | <ul><li>Anular devuelve los registros a LISTO y desliga `trabajo_registro_id` de los ítems.</li><li>Reimprimir hace copias idénticas, por grupos o rangos, con `FOR UPDATE` del lote.</li></ul> |
| 11 | **Recuperación** | `main.py:79-89` → `trabajos.recuperar` `925-945` | Retoma los trabajos EN_PROCESO cuyo arriendo venció. Con `ETIQUETAS_MAX_INTENTOS` agotado, el trabajo queda en ERROR. |

---

## 2. Matriz de casos

| Caso | Estado | Cómo se resuelve hoy / qué falla |
|---|---|---|
| **OC completa** | Soportado | <ul><li>Toma todas las líneas no bloqueadas (`generacion.py:155-163`).</li><li>Varias OC: una parte y una ejecución por OC (`trabajos.py:230-241`). Tope de 200 OC (`trabajos.py:65`).</li><li>La pantalla recorta en silencio «todas las OC de la familia» a 200 (`TrabajoEtiquetasView.vue:269`; `buscadores.py:191` da hasta 1000).</li></ul> |
| **Posiciones específicas** | Soportado (con fallas) | <ul><li>`posiciones` no se normaliza: un id en texto no coincide (`trabajos.py:230,236`).</li><li>Una OC sin ninguna posición elegida se omite sin aviso (`236-238`).</li><li>Una línea bloqueada que se elige se incluye sin aviso (`generacion.py:158`).</li></ul> |
| **Por artículo o por línea** | Soportado | <ul><li>`alcance` de la regla o del tipo: LINEA, POSICION_OC, POSICION_PL, ARTICULO o PRODUCTO (`reglas.py:124-132`, `generacion.py:224-243`).</li><li>Al juntar líneas con reglas distintas avisa y usa la primera (`250-251`).</li><li>«Una por unidad» suma unidades distintas y se queda con la unidad de la primera línea (`247-262`) [VERIFICADO-código].</li></ul> |
| **Cantidad manual** | **Parcial** | <ul><li>Solo vale con un tipo o una regla `MANUAL`, o en artículos sueltos (`generacion.py:257-268`).</li><li>La pantalla deja escribir la cantidad de **cualquier** registro: «Quantity from the data; write another to change it» (`TrabajoEtiquetasView.vue:824-826`). El servidor la ignora (L-03) [VERIFICADO-prueba].</li></ul> |
| **Lotes (batch del producto)** | No | <ul><li>Solo hay variables manuales **por trabajo** (`diseno.py:375-385`, `generacion.py:492`): un valor para todos los registros.</li><li>No existe un dato de lote por línea ni por caja.</li></ul> |
| **Kits y prepacks** | Parcial | <ul><li>Tabla `articulo.componentes` (`campos.py:387-391`), `bulto.componentes` y aviso `prepack_sin_componentes` (`empaque_etiquetas.py:136`).</li><li>«Una por unidad» cuenta paquetes, no unidades: el prepack no se explota (`generacion.py:213,262`).</li></ul> |
| **OC + artículo + empaque en una etiqueta** | Parcial | <ul><li>El sujeto BULTO trae datos de OC, línea y artículo **solo** si la caja tiene un solo artículo y una sola OC (`generacion.py:300-304`).</li><li>El sujeto ARTICULO no tiene los grupos `pl` ni `bulto` (`campos.py:49-53`): no hay etiqueta de artículo con el número de su caja.</li></ul> |
| **Desde bultos de packing existentes** | Parcial | <ul><li>Origen PACKING: varios niveles y cada unidad física una vez (`generacion.py:279-288`).</li><li>Origen OC: solo el primer nivel, y toma **todas** las cajas de cada PL que toque la OC (`campos.py:592-604`) (L-04).</li><li>Una PL en borrador da etiquetas reales desde la OC (`planear` `427` solo revisa la PL del pedido).</li></ul> |
| **Diseño automático por reglas** | Soportado (con huecos) | Escalera de niveles y excepciones (`reglas.py:325-349`). Huecos: L-08, L-09, L-11, L-18 y L-19. |
| **Aviso de obligatorios antes de generar** | Parcial | <ul><li>Sí avisa: variables manuales obligatorias (`generacion.py:493-494`), campo obligatorio del diseño y código sin valor (`render.py:494,701`), campos lógicos BLOQUEAR, y «completar» para 4 datos (`trabajos.py:436-481`).</li><li>No avisa: el obligatorio de la familia solo advierte (`generacion.py:512-514`).</li><li>El resumen de la OC o PL (`dibujar=False`) no detecta los problemas de dibujo ni los manuales (L-07).</li></ul> |
| **Errores y reintentos** | Soportado (con fallas) | <ul><li>Generar de nuevo genera solo lo pendiente (`trabajos.py:745`). Estados PARCIAL y ERROR, recuperación con arriendo, generación parcial por regla.</li><li>Fallas: entradas que dan 500 (L-05).</li><li>Una parte con error de configuración bloquea el trabajo entero aun en modo parcial (L-26).</li><li>En segundo plano se vuelve a planificar sin control (L-14).</li></ul> |
| **Idempotencia** | Parcial | <ul><li>`Idempotency-Key` en crear y generar (`api.py:506,545`; `comun/historial.py:58-69`). El doble clic se frena con `FOR UPDATE` y el estado.</li><li>Reimprimir y confirmar la impresión no tienen clave; confirmar sobrescribe (L-24).</li></ul> |
| **Impresión** | Mínimo | <ul><li>Descarga y confirmación manual. No hay ZPL, cola de impresión ni impresora configurada.</li><li>Las reimpresiones no se confirman.</li></ul> |
| **Trazabilidad** | Buena (con fallas) | <ul><li>`registrar` en cada acción; versión e instantánea por ítem; sha256.</li><li>Fallas: anular rompe el enlace registro↔ítem (`trabajos.py:1161-1163`), y «ya generada» y los conteos incluyen lotes anulados (L-12).</li></ul> |

---

## 3. Inventario de endpoints de etiquetado

Son 83 rutas en `api.py`, todas bajo `/api/etiquetas`. Se buscó cada ruta en `frontend/src` (llamadas `api.*` y URLs literales), en `backend/tests` y en el resto de `backend/app`.

Abreviaturas:
- **FE**: frontend.
- **Permisos**: `ver`, `gen`, `dis`, `conf`, `fam`, `cam` y `apr` son `etiquetas.ver`, `.generar`, `.disenar`, `.configurar`, `.familias`, `.campos` y `.aprobar`.
- **«a\|b»**: basta con cualquiera de los dos permisos.

| Método y ruta | Permiso | Uso en el FE |
|---|---|---|
| GET `/catalogos` | ver\|gen\|dis\|conf | `etiquetas.js` |
| GET `/campos` | ver\|dis | Editor, celdas y categorías |
| PUT `/campos/propios` | conf | `NombresCampos.vue` |
| PUT `/tamanos` | conf | `TamanosEtiqueta.vue` |
| GET, POST `/tipos` · PATCH `/tipos/{id}` | ver\|gen\|conf · conf | `TiposEtiqueta.vue`, `PrimerUsoEtiquetado.vue` |
| **POST `/tipos/sugeridos`** | conf | **Sin uso.** Tampoco hay pruebas. Solo la demo llama a la función directamente (`instalacion/demo_etiquetado.py:100`). `PrimerUso` crea los tipos uno a uno con POST `/tipos`. |
| GET `/matriz` | ver\|conf | `MatrizEtiquetado`, `FamiliasYArticulos`, Asistente |
| GET `/celda` · PUT `/usos/celda` | ver\|conf · conf | `CeldaEtiquetado.vue` |
| POST `/usos/simular` | **conf\|ver** | `CeldaEtiquetado`, `EtiquetadoProducto` (lo puede llamar un proveedor: L-02) |
| POST `/usos/lote` | conf | `CeldaEtiquetado` |
| GET `/usos/valores` | **conf\|ver** | `ExcepcionFrase.vue` (L-02) |
| **GET `/usos`** | ver\|conf | **Sin uso** en el FE ni en las pruebas. Solo aparece como clave de evento en `alCambiar`. Está documentado. |
| POST `/usos` | conf | `PrimerUso`, `EtiquetadoProducto`, `ResumenEtiquetas` (excepción de OC), `TrabajoEtiquetasView` |
| **PATCH `/usos/{id}`** | conf | **Sin uso** en el FE. Solo pruebas (`test_etiquetado_motor_reglas.py:73`). |
| POST `/usos/{id}/baja` | conf | `CeldaEtiquetado`, `EtiquetadoProducto` |
| GET `/usos/migracion` | conf | `ConversionReglas.vue` |
| **GET `/usos/{id}/historial`** | ver\|conf | **Sin uso** en el FE. Solo pruebas. |
| **GET `/resolver`** | ver\|gen | **Sin uso** en el FE. Solo pruebas (7). Se solapa con `/productos/{id}` y `/resumen`. |
| GET `/productos/{id}` | ver\|conf\|gen | `EtiquetadoProducto.vue` |
| GET `/resumen` | gen | `ResumenEtiquetas.vue`, `TrabajoEtiquetasView.vue` |
| GET, POST `/campos-logicos` · PATCH, DELETE `/campos-logicos/{id}` | ver\|cam · cam | `CamposEtiqueta.vue` |
| GET, POST `/familias` · POST `/familias/desde-grupos` · `/familias/configurar` · PUT `/familias/orden` · PATCH, DELETE `/familias/{id}` | ver\|fam · fam (configurar también pide conf si hay diseños) | `FamiliasYArticulos`, `PrimerUso`, `AsistenteFamiliaView` |
| GET, POST `/categorias` · POST `/categorias/probar` · PATCH, DELETE `/categorias/{id}` · POST `/productos/categoria` | ver\|conf\|fam · fam · fam\|conf | `CategoriasFamilia`, `FamiliasYArticulos` |
| GET `/articulos` · `/grupos-articulos` · `/productos` y POST `/articulos/familia` · `/grupos-articulos/familia` · `/productos/familia` | ver\|fam · fam | `FamiliasYArticulos`, Asistente, `TrabajoEtiquetasView` |
| GET, POST `/plantillas` · GET, PATCH `/plantillas/{id}` · GET `/plantillas/{id}/bitacora` · POST `/plantillas/{id}/duplicar` · `/versiones` | ver · dis | `DisenosView`, `EditorEtiquetaView`, `VersionesEtiqueta` |
| POST `/plantillas/{id}/archivar` · `/reactivar` | apr\|dis | `DisenosView.vue:111` (ruta armada con plantilla de texto) |
| GET `/versiones/{id}` · PUT `/versiones/{id}/diseno` · POST `/versiones/{id}/{accion}` | ver · dis · dis o apr según la acción | Editor y `VersionesEtiqueta` |
| POST `/vista-previa` | ver\|dis (dis si el diseño no está guardado) | `EditorEtiquetaView`, `editor/estado.js` |
| GET `/versiones/{id}/miniatura.svg` | ver | `DisenosView`, `SelectorDiseno` y 3 más |
| POST `/imagenes` · GET `/imagenes/{id}` | dis · **ver** | `PanelElemento`, `etiquetas.js:312` (L-01) |
| GET `/fuentes/{archivo}` | ver\|dis | `etiquetas.js:143,154` |
| GET `/generaciones` · `/generaciones/{id}` · `/generaciones/{id}/archivo` | ver · ver · gen | `HistorialEtiquetas`, `TrabajoEtiquetasView` |
| GET `/ordenes` · `/packing` · `/packing/{id}` | gen | `TrabajoEtiquetasView` |
| GET, POST `/trabajos` · GET, PATCH `/trabajos/{id}` · POST `/validar` · `/completar` · `/generar` · GET `/estado` · `/archivo` · `/registros/{r}/vista-previa` | gen | `TrabajoEtiquetasView`, `ImprimirView`, `OrdenView`, `OrdenesView` |
| **POST `/trabajos/{id}/cancelar`** | gen | **Sin uso** en el FE. Solo pruebas. No hay forma de cancelar un borrador desde la pantalla. |
| POST `/generaciones/{id}/impresion` · `/anular` · `/reimprimir` | gen | `TrabajoEtiquetasView` |

Ningún otro módulo del backend llama a estas rutas, y no hay integraciones externas documentadas. Las 6 rutas sin uso en el FE sí están documentadas en `docs/ETIQUETADO.md:202-212`.

**Endpoints que se solapan, con resultados distintos** (L-07):

- **«¿Qué diseño lleva?»**: `/resolver`, `/productos/{id}`, `/usos/simular`, `/resumen` y `/trabajos/{id}/validar`. Son cinco caminos, cada uno con un conjunto de valores distinto.
- **Archivos**: `/generaciones/{id}/archivo`, `/trabajos/{id}/archivo` y `/generaciones/{id}/reimprimir` usan dos empaquetadores distintos.
- **Vistas previas**: `/vista-previa` no incluye los campos lógicos ni `contexto.*`. `/trabajos/…/vista-previa` sí los incluye. `miniatura.svg` usa datos reales de otro proveedor.
- **Escritura de usos**: hay cinco caminos. Son POST `/usos` (con `reemplazar`), PUT `/usos/celda`, POST `/usos/lote`, PATCH `/usos/{id}` y `/familias/configurar`.

---

## 4. Separación de responsabilidades

### Situación actual (qué hace cada archivo)

| Archivo (líneas) | Mezcla |
|---|---|
| `trabajos.py` (1226) | <ul><li>Parámetros y CRUD (65-333).</li><li>Consulta (336-401).</li><li>Validación y resumen (404-619).</li><li>**Escritura en el maestro de artículos** (434-481).</li><li>**Ejecución duradera**: arriendo, hilos y recuperación (622-945).</li><li>**Empaquetado ZIP** (948-1103).</li><li>**Impresión, anulación y reimpresión** (1106-1198).</li><li>Vista previa (1201-1226).</li></ul> |
| `generacion.py` (938) | <ul><li>Modelo `Grupo` (54-106).</li><li>**Selección de datos de origen y reglas** (116-399).</li><li>Planificación (402-586).</li><li>Persistencia y series (589-695).</li><li>**Dibujo y empaquetado** (698-786).</li><li>**Historial y descargas** (789-886).</li><li>**Resumen de pantalla** (889-938).</li></ul> |
| `campos.py` (626) | <ul><li>Catálogo de campos (36-330).</li><li>Extracción de valores (333-430).</li><li>**Estructura física de la PL**: `Bulto`, `_unidades`, `bultos` y `unidades_pl` (432-626). Es integración con empaque.</li></ul> |
| `usos.py` (956) | <ul><li>CRUD y celda (59-646).</li><li>Simulación (648-727).</li><li>Matriz y cobertura (730-877).</li><li>Ficha del producto y `resolver` (880-956), con su **propio** armado de valores.</li></ul> |
| `reglas.py` | Motor. Bien acotado, pero reexporta funciones privadas de `comun/condiciones.py` (`reglas.py:54-75`). |
| `datos.py` · `previa.py` · `buscadores.py` | Valores y carga con alcance · vistas previas · búsquedas del asistente. |
| `plantillas.py` (519) | Diseños, versiones, flujo de aprobación, imágenes y tamaños. Es razonable. |

### Propuesta

Solo se mueven funciones; no se agrega ninguna capa nueva.

1. **Partir `trabajos.py`**:
   - Queda en `trabajos.py` (~600 líneas): parámetros, CRUD, validar, generar y completar.
   - `ejecucion.py` (~250): arriendo, latido, `lanzar`, `recuperar`, `_ejecutar` y `_ejecutar_tomado`.
   - `lotes.py` (~300): `confirmar_impresion`, `anular` y `reimprimir`, más `cargar`, `listar`, `dict_generacion`, `archivo`, `marcar_descarga` y `no_anulada`, que hoy están en `generacion.py`.
2. **Un solo empaquetador**: `paquetes.py` (~300), con `_lienzos`, `_producir`, `_manifiesto`, el ZIP del trabajo, `_archivos_pdf`, `_resumen`, `_csv` y un único `_seguro`. La reimpresión, el lote y el trabajo lo usan con las mismas reglas (hoja, dpi, nombres).
3. **Partir `generacion.py`**:
   - `registros.py` (~400), con «qué se etiqueta desde cada origen»: `Grupo`, `_posiciones_oc`, `_grupos_*`, `armar`, `_Decide`, `tipos_del_pedido`, `cargar_pl` y `pl_permite_reales`.
   - Queda en `generacion.py` (~350): `planear`, `producir`, `_previas`, la serie y la clasificación de problemas.
   - `resumen` reutiliza `trabajos.tipos_por_defecto`, para que la OC y el trabajo coincidan.
4. **Partir `campos.py`**:
   - El catálogo queda en `campos.py`.
   - Las funciones `valores_*` pasan a `datos.py`, que ya ensambla los valores.
   - `Bulto` y las unidades de la PL pasan a `bultos.py`, la frontera con el módulo de empaque.
5. **Partir `usos.py`**:
   - `usos.py`: CRUD, celda y lote.
   - `cobertura.py`: matriz, `simular`, `de_producto` y `resolver`. Debe armar los valores **con la misma función que la generación**, lo que corrige L-07.
6. **Orden recomendado**:
   - Primero los movimientos puros (1, 3 y 4). Solo cambian imports, así que el riesgo es bajo.
   - Después unificar el empaquetador (2) y el armado de valores (5). El riesgo es medio y conviene cubrirlo con las pruebas de salida existentes y una prueba de sha256.

### Genericidad: qué está bien fijo y qué no

**Está bien que sean fijos**, porque cada valor es una rama de código distinta o una lista cerrada por seguridad:
- `SUJETOS`, `ORIGENES_TRABAJO`, `SUJETOS_DE`, `ESTADOS_*`, `ACCIONES`, `CANTIDADES_REGLA` y `FORMATOS`.
- Los operadores de condición, una lista cerrada (`comun/condiciones.py:14-17`).
- `CATEGORIAS` de problemas.
- `NIVELES_DE`: la escalera SKU → PRODUCTO → CATEGORIA → FAMILIA → GENERAL.

**Deberían derivarse o configurarse**:
- **Patrones en `api.py`** que repiten constantes del modelo: `30`, `98`, `104`, `129` y `172`. Deben derivarse de `NIVELES_DE`, `CONTEXTOS` y `SUJETOS`.
- **Constantes y ayudas duplicadas**:
  - `generacion.ORIGENES` frente a `ORIGENES_TRABAJO`.
  - Dos `FORMATOS`.
  - `MAX_ORDENES` (`trabajos.py:65`, `buscadores.py:165`).
  - `_seguro` (`generacion.py:720`, `trabajos.py:949`).
  - El ayudante `poner` del ZIP, dos veces.
  - `_usuario`, tres veces.
- **`ORDEN_CONTEXTO`** (`reglas.py:52`): fija la precedencia entre clases de excepción. La `prioridad` solo ordena dentro de una misma clase (L-19).
- **`COMPLETABLES`** (`trabajos.py:436`): 4 columnas fijas. Debería ser una marca «editable desde el etiquetado» en el catálogo de campos.
- **`CARPETAS` y `MARCADORES` del ZIP** (`trabajos.py:71-72`), junto con los nombres de campo fijos en `archivo` (`993-1006`: `articulo.sku`, `linea.codigo_articulo`, `bulto.codigo`, `articulo.familia` y `bulto.packing_list`). Debería usar las columnas del ítem (`articulo_id`, `pl_id`, `grupo_id`) o cualquier campo de la instantánea.
- **Estados copiados de otros módulos**:
  - `OC_ABIERTAS` (`usos.py:50`).
  - `("BORRADOR","CANCELADA")` (`buscadores.py:187`).
  - `"FINALIZADO"` (`generacion.py:151`).
  - `"CANCELADO"` de la PL (`campos.py:598`).

  Deberían leerse del flujo del módulo dueño.
- **Límites en código** sin aviso de recorte: `MAX_ARTICULOS`, `MAX_MUESTRAS`, `MAX_COMPLETAR`, `MAX_SIMULACION`, `MAX_FILAS` y `MAX_PRIORIDAD`. Deberían pasar a configuración y avisar cuando recortan.
- **Textos de negocio en el código** (separadores `" · "`, `labels-`, `-reprint`, `summary.json` frente a `lote.json`, `ALCANCE_TXT`): la interfaz los traduce, pero hay mensajes compuestos que no (L-25).

---

## 5. Hallazgos

### Impacto alto

**L-01 · [VERIFICADO-prueba] Un proveedor lee cualquier imagen subida a la organización (IDOR)**
- **Problema**: `GET /etiquetas/imagenes/{id}` solo exige `etiquetas.ver` y lee cualquier `Adjunto` con tipo `image/*`. No mira la carpeta ni el dueño.
- **Evidencia**:
  - `plantillas.py:250-261` y `513-519`.
  - Los adjuntos se comparten con las fotos y los documentos de producto y con los archivos de factura (`productos.py:1010,1071`, `facturas.py:1007`).
  - Prueba: el interno subió una foto a un producto de Vans. TNF recibió 200 en `/etiquetas/imagenes/1` y 404 en `/productos/6`.
- **Impacto**: Alto. Expone fotos y escaneos de otros proveedores.
- **Solución**:
  - Leer solo los adjuntos creados para el etiquetado: carpeta `etiquetas/` o una tabla de imágenes de etiqueta.
  - Aplicar en `imagen_adjunta` la misma restricción para el dibujo.
- **Riesgo**: Bajo. Un diseño que haya usado una foto de producto dejaría de verla; conviene revisarlo antes.

**L-02 · [VERIFICADO-prueba] Con `etiquetas.ver`, el proveedor ve configuración y datos ajenos**
- **Problema**: Varias lecturas usan `exigir_alguno(..., "etiquetas.ver")` sin filtrar por proveedor.
- **Evidencia** (respuestas obtenidas con el usuario de TNF):
  - `GET /usos/valores?contexto=PROVEEDOR` devuelve todos los proveedores, incluido Vans (`usos.py:436,450-452`).
  - `GET /usos` devuelve todas las reglas, con números de OC ajenas (`usos.py:121`).
  - `POST /usos/simular` devolvió 28 SKU de toda la empresa y recorre hasta 20 000 artículos (`usos.py:679,690`).
  - `GET /matriz` y `GET /celda` también responden.
  - La vista previa con datos de ejemplo y la miniatura usan la **última línea de OC de la empresa** (`campos.py:317-329`, `previa.py:106,116`): Vans recibió el SKU de TNF, y `linea.precio` se incluye si el diseño lo imprime.
- **Impacto**: Alto: fuga entre proveedores y una consulta pesada al alcance del proveedor.
- **Solución**:
  - `simular`, `usos`, `valores`, `matriz` y `celda` deben exigir `conf` o un permiso interno.
  - `ejemplos` debe filtrar por `proveedor_filtro(user)` o usar solo valores neutros.
- **Riesgo**: Bajo. Ninguna pantalla del proveedor necesita estas rutas (verificarlo en `PerfilView` y `OrdenView`).

**L-03 · [VERIFICADO-prueba] La cantidad escrita en la pantalla se ignora**
- **Problema**: La tabla de revisión deja escribir la cantidad de todo registro y guarda `cantidades[clave]`. El servidor solo la usa con `MANUAL`, o con `POR_UNIDAD` en artículos sueltos.
- **Evidencia**:
  - Pantalla: `TrabajoEtiquetasView.vue:824-827`, `392`.
  - Servidor: `generacion.py:257-268`.
  - Prueba: el registro `oc4:t5-p17` con 7 escritas siguió con `cantidad=1` y `parametros.cantidades={…:7}`.
- **Impacto**: Alto. Se imprime una cantidad distinta de la que el usuario cree, sin ningún aviso.
- **Solución** (decidir una):
  - Aplicar la cantidad escrita a cualquier registro, como un ajuste manual registrado.
  - O bloquear el campo en la interfaz y avisar en el servidor cuando la cantidad escrita no aplica.
- **Riesgo**: Medio. Cambia cantidades de trabajos ya guardados con cantidades escritas; hay que migrarlos o avisar.

**L-04 · [VERIFICADO-código] Bultos desde la OC con una PL consolidada: cajas ajenas y duplicadas; una PL en borrador da reales**
- **Problema**: `campos.bultos(oc_id)` toma todas las cajas de primer nivel de cada PL que tenga alguna línea de la OC. No filtra por OC.
- **Evidencia**:
  - `campos.py:592-604` y `generacion.py:289-290`.
  - En un trabajo con las OC A y B, cada caja sale en `oc{A}:` y en `oc{B}:`.
  - `planear` solo revisa `pl_permite_reales` para la PL del pedido (`generacion.py:427`).
  - Coincide con GN-01 de la revisión anterior.
- **Impacto**: Alto. Dos etiquetas para la misma caja física (y dos SSCC o series).
- **Solución**:
  - Filtrar las unidades cuyo `por_posicion` incluya líneas de la OC.
  - Si la caja es mixta entre OC, sacarla una sola vez por trabajo.
  - Aplicar `pl_permite_reales` a cada PL de origen.
- **Riesgo**: Medio. Cambia los números «n de N» de las cajas en una OC.

**L-05 · [VERIFICADO-prueba] Parámetros sin validar: errores 500 y riesgo de memoria**
- **Problema**: `_limpiar` copia `dpi`, `hoja`, `manuales`, `cantidades` y `posiciones` sin revisarlos, y convierte con `int()` sin capturar el error.
- **Evidencia** (la prueba propagó cada excepción):

  | Entrada | Excepción | Dónde |
  |---|---|---|
  | `oc_ids:["abc"]` | `ValueError` | `trabajos.py:155` |
  | `articulos:[{}]` | `KeyError` | `trabajos.py:167` |
  | `elegidas:{"x":"abc"}` | `ValueError` | `trabajos.py:194` |
  | `dpi:"abc"` (se acepta al crear) | `TypeError` al generar | `salidas.py:306` |
  | `hoja:{columnas:0}` (se acepta al crear) | `pydantic.ValidationError` al generar | `generacion.py:604` |
  | `dpi:5000` | Se guarda tal cual. Un PNG de 100 mm a 5000 dpi tiene unos 20 000 px por lado. | — |

  - También `familia=abc` en `/etiquetas/articulos` (`familias.py:217`).
  - `main.py:197-215` solo traduce `ErrorNegocio`, `IntegrityError` y `RequestValidationError`.
- **Impacto**: Alto: errores 500 que la interfaz no traduce, y riesgo de agotar la memoria.
- **Solución**:
  - Validar en `_limpiar`: `Hoja.model_validate`, `dpi` en 72-1200, enteros con un 422, tamaño de `manuales` y `cantidades`.
  - Agregar un manejador para `pydantic.ValidationError` que responda 422.
- **Riesgo**: Bajo.

**L-06 · [VERIFICADO-código] Sin tope real de trabajo; validación y descargas en la misma petición**
- **Problema**: Los topes son 200 OC, 5000 artículos y 50 000 etiquetas, pero el de etiquetas se revisa **después** de planificar y dibujar cada registro. Validar, revalidar en `generar` y descargar son siempre síncronos.
- **Evidencia**:
  - `trabajos.py:156-164`, `577-580` y `741`.
  - `trabajos.archivo` vuelve a dibujar hasta 50 000 etiquetas (y PNG al dpi pedido) en memoria (`953-1046`).
  - Con `formato=ZIP`, `_producir` dibuja PDF, PNG y SVG de todo el lote, y el sha256 se calcula sobre un archivo que se descarta (`generacion.py:650-651,769-778`).
  - Sin `cantidades`, el tope de la generación síncrona es 1999 etiquetas.
- **Impacto**: Alto en disponibilidad (tiempos agotados, memoria). Un proveedor también puede provocarlo.
- **Solución**:
  - Tope de registros antes de planificar.
  - Validación y descarga grandes en segundo plano, con el mismo arriendo de la generación.
  - Guardar el archivo generado, o su lista de páginas, en lugar de volver a dibujarlo.
  - Calcular el sha256 sobre lo que se entrega.
- **Riesgo**: Medio.

### Impacto medio

**L-07 · [VERIFICADO-prueba + código] La misma pregunta da respuestas distintas según la pantalla**
- **Evidencia**:
  - **Ficha del producto frente al trabajo**: `de_producto` evalúa con `Sujeto(articulo=a)` y `valores={}` (`usos.py:909`). Prueba: con una excepción `articulo.sku = X`, la ficha dijo «AUD design» y `/resolver` y el trabajo dijeron «AUD exception».
  - **Resumen de la OC frente al trabajo**: el resumen usa todos los tipos activos (`generacion.py:897`) y el trabajo los obligatorios (`trabajos.py:244-251`). Prueba: el resumen dio Hang tag 40, Price 40, Carton 0, PO sheet 1 y Aud_L 2; el trabajo, `tipos=[1,3]`. Además el resumen no dibuja (`dibujar=False`), así que no ve campos obligatorios, códigos sin valor, manuales ni la serie.
  - **Vista previa del editor**: no aplica campos lógicos ni `contexto.*` (`previa.py:102-103`). La generación sí (`generacion.py:450-452`).
  - **Matriz frente al motor**: la matriz solo muestra familias activas y arma su propia herencia (`usos.py:760-821`). `familia_efectiva` no mira `activa` (`modelos/maestros.py:498-506`).
- **Impacto**: Medio. El usuario confía en la pantalla equivocada.
- **Solución**: Una sola función «valores del registro y elección» (en `cobertura.py`), usada por la ficha, `resolver`, la simulación y la generación. El resumen debe usar `tipos_por_defecto` y marcar «sin revisar dibujo».
- **Riesgo**: Medio.

**L-08 · [VERIFICADO-código] Condiciones sobre `contexto.*` y `logico.*` se aceptan pero nunca se cumplen en la regla**
- **Evidencia**:
  - La regla se decide en `_Decide` con `datos.valores` (`generacion.py:185-187`).
  - `contexto.*` y los campos lógicos se agregan después (`450-452`).
  - `validar_condiciones` acepta todo el catálogo (`reglas.py:91`).
- **Impacto**: Medio. Hay reglas guardadas que no funcionan.
- **Solución**: Decidir con los valores completos, o rechazar esos campos en las condiciones de reglas y categorías.
- **Riesgo**: Bajo.

**L-09 · [VERIFICADO-prueba] Se puede asignar un diseño sin versión aprobada; bloquea en lugar de caer al nivel siguiente**
- **Evidencia**:
  - `_limpiar` de usos solo exige `estado=ACTIVA` (`usos.py:261-265`).
  - El motor lo elige (`reglas.py:216-219`).
  - `planear` da el error «no approved version» (`generacion.py:485-489`).
  - La matriz lo cuenta como cubierto (`usos.py:827`).
  - Prueba: los 2 registros quedaron en ERROR.
- **Impacto**: Medio. Un diseñador asigna un borrador y detiene la producción de toda una familia.
- **Solución**:
  - Al guardar la celda, avisar o impedir el cambio sin versión vigente.
  - En la matriz, marcar «sin versión aprobada».
- **Riesgo**: Bajo.

**L-10 · [VERIFICADO-prueba] El proveedor puede imponer cualquier diseño activo del tipo**
- **Evidencia**:
  - `parametros.elegidas` se acepta sin permiso ni motivo (`trabajos.py:189-198`, `generacion.py:453-460`).
  - La interfaz solo lo ofrece para registros sin diseño (`TrabajoEtiquetasView.vue:753-756`).
  - Prueba: TNF cambió «AUD design» por «AUD design B» y el registro quedó LISTO.
- **Impacto**: Medio. Salta las reglas corporativas.
- **Solución**: Aceptar `elegidas` solo para registros sin diseño, o exigir `etiquetas.configurar` y un motivo registrado.
- **Riesgo**: Bajo.

**L-11 · [VERIFICADO-código] Excepciones de OC, destino, sociedad y proveedor no aplican en bultos mixtos ni en PL de varias OC**
- **Evidencia**:
  - `oc_bulto=None` si la caja mezcla OC (`generacion.py:302-303`).
  - `contexto()` no usa el proveedor de la PL (`pl.factura.proveedor_id`) (`reglas.py:266-272`).
  - `_Decide` no pasa `proveedor_id` (`generacion.py:186`).
- **Impacto**: Medio.
- **Solución**: Pasar `proveedor_id` y sociedad desde la factura de la PL. Si las OC de una caja comparten destino, usarlo.
- **Riesgo**: Bajo.

**L-12 · [VERIFICADO-prueba] «Ya generada» y los conteos incluyen lotes anulados**
- **Evidencia**:
  - `_previas`, `resumen` y `buscadores` filtran solo `estado=="GENERADA"` (`generacion.py:553,933-934`, `buscadores.py:196-197`).
  - `anular` no cambia `estado` (`trabajos.py:1159`).
  - Prueba: después de anular apareció `ya_generada`, y `ya_generadas=1`.
- **Impacto**: Medio. Avisos falsos, y la gente se acostumbra a aceptarlos.
- **Solución**: Agregar `anulada_en IS NULL` en los tres lugares.
- **Riesgo**: Bajo.

**L-13 · [VERIFICADO-prueba] `aceptar_advertencias` acepta todas las advertencias a ciegas; dos trabajos de la misma línea generan sin bloqueo**
- **Evidencia**:
  - Es un booleano (`trabajos.py:777`). Los avisos que aparecen entre revisar y generar, como `ya_generada`, se aceptan sin verse.
  - No hay bloqueo entre trabajos.
  - Prueba: A y B, sobre la misma posición, respondieron 200 los dos.
- **Impacto**: Medio. Etiquetas reales duplicadas.
- **Solución**:
  - Aceptar una huella de las advertencias vistas, como ya se hace con `datos_cambiaron`.
  - Bloqueo opcional por línea u OC con la regla «impedir duplicados».
- **Riesgo**: Bajo.

**L-14 · [VERIFICADO-código] En segundo plano se genera con datos nuevos y se marcan GENERADO registros sin ítem**
- **Evidencia**:
  - `_ejecutar` vuelve a planificar sin `datos_cambiaron` (`trabajos.py:822`).
  - Después marca todos los registros `mias` aunque no estén en `lista` (`823-829`).
- **Impacto**: Medio. La trazabilidad no coincide con lo impreso.
- **Solución**: Marcar solo los grupos producidos. Comparar `revisado` y, si cambió, dejar el registro pendiente con un aviso.
- **Riesgo**: Bajo.

**L-15 · [VERIFICADO-código] El alcance por sociedad se ignora en trabajos, generaciones y búsqueda de OC**
- **Evidencia**:
  - `trabajos._alcance` y `generacion._alcance` solo miran `proveedor_filtro` (`trabajos.py:84-86`, `generacion.py:790-795`).
  - `ordenes_familia` no aplica `sociedades_de` (`buscadores.py:181-183`); `buscar_packing` sí (`214-216`).
  - Un interno limitado a una sociedad ve, descarga, anula y reimprime trabajos de otra.
- **Impacto**: Medio. Solo afecta a organizaciones que usan límites por sociedad.
- **Solución**: Filtrar por la sociedad de las OC o PL de las ejecuciones, o guardar `sociedad` en el trabajo.
- **Riesgo**: Bajo.

**L-16 · [VERIFICADO-código] Series: la prueba consume números y el bloqueo se retiene mientras se dibuja**
- **Evidencia**:
  - `reservar` se llama aunque `estado=PRUEBA` (`generacion.py:613,633-638`).
  - El `FOR UPDATE` del contador dura hasta el `commit`, después de `_producir` (`650`). Toda generación síncrona de la organización que use la serie queda en fila.
  - Anular deja huecos, pero eso está documentado.
- **Impacto**: Medio.
- **Solución**: No reservar en prueba (usar una vista previa). Reservar al final, o confirmar la reserva en una transacción corta.
- **Riesgo**: Medio, porque toca la numeración.

**L-17 · [VERIFICADO-código] Cálculos repetidos y consultas N+1**
- **Evidencia**:
  - **Dos `Resolvedor` por parte**: el de `planear` (`generacion.py:434`) es casi código muerto, porque `armar` siempre deja `g.eleccion` (`461-466`).
  - **`datos.valores` repetido**: incluye `valores_articulo`, con relaciones perezosas. Se calcula una vez por tipo y línea en `_Decide` (`182-186`, llamado en `220-221` por cada tipo) más una vez en `planear` (`448`). Con 3 tipos, son 4 veces por línea.
  - **`valores_oc` dos veces** por OC (`184`, `446`).
  - **`generar` vuelve a validar todo**, con dibujo y lector, después de validar (`trabajos.py:741`).
  - **Vista previa de un registro**: planifica la parte entera (`1213`).
  - **`campos.bultos` por cada OC** de la página del buscador (`buscadores.py:201`).
  - **`detalle` devuelve todos los registros y ejecuciones** (cada una con sus ítems) en cada PATCH, validar o generar (`trabajos.py:370-383`).
  - **Carga de artículos uno por uno** en el origen ARTICULOS: hasta 5000 `db.get` (`trabajos.py:166-167`, `generacion.py:215-216`).
  - **Matriz y categorías**: `_articulos_por_categoria` carga todos los artículos (`usos.py:849-858`).
- **Impacto**: Medio.
- **Solución**:
  - Calcular los valores una vez por línea y compartirlos entre tipos.
  - Quitar el segundo `Resolvedor`.
  - `generar` reutiliza la validación si `validado_en` es posterior al último cambio.
  - Paginar los registros en `detalle`.
- **Riesgo**: Bajo a medio.

**L-18 · [VERIFICADO-código] La categoría se guarda en memoria por artículo aunque sus condiciones lean datos de la OC o la línea**
- **Evidencia**: `Resolvedor.categoria` guarda por `a.id` (`reglas.py:244-256`), pero las condiciones admiten `oc.*` y `linea.*` (`categorias.py:92`, `reglas.py:91`).
- **Impacto**: Medio-bajo. En una PL de varias OC, la primera línea decide la categoría de todas.
- **Solución**: Limitar las condiciones de categoría a `articulo.*` y `producto.*`.
- **Riesgo**: Bajo.

**L-19 · [VERIFICADO-código] La precedencia entre clases de excepción es fija y silenciosa; el docstring está desactualizado**
- **Evidencia**:
  - Orden: CENTRO > PAIS > SOCIEDAD > PROVEEDOR > CONDICION (`reglas.py:52,236`).
  - `prioridad` solo ordena dentro de una misma clase.
  - `_empate` solo avisa dentro de la misma clase (`305-312`).
  - El docstring dice «No hay prioridades numéricas ni empates» (`20-24`).
- **Impacto**: Medio-bajo. Cuando se cruzan excepciones de distintas clases, nadie se entera.
- **Solución**: Avisar cuando coinciden excepciones de distintas clases, y que la prioridad ordene entre clases (o documentarlo). Corregir el docstring.
- **Riesgo**: Bajo.

**L-20 · [VERIFICADO-código] Dos empaquetadores con reglas distintas**
- **Evidencia**:
  - `generacion._producir` usa la hoja, `lote.json`, `png/` y `svg/` (`743-779`).
  - `trabajos.archivo` fuerza `{"modo":"individual"}` y usa `summary.*` (`1034-1042`).
- **Impacto**: Medio. Una hoja A4 de 3×8 sale bien en un lote y en el ZIP del trabajo sale una etiqueta por página.
- **Solución**: Unificar en `paquetes.py` (ver la sección 4).
- **Riesgo**: Medio.

**L-26 · [VERIFICADO-código] Un error de configuración en una parte bloquea todo el trabajo, aun en modo parcial**
- **Evidencia**: El `ErrorNegocio` de una parte se agrega a `generales` (`trabajos.py:531-536`) y `generar` corta con cualquier problema general (`742-744`), antes de mirar `parcial`.
- **Impacto**: Medio. Con 200 OC, una sola mal configurada frena las 199 restantes.
- **Solución**: Tratar los errores de una parte como errores de esa parte. Con generación parcial, omitirla.
- **Riesgo**: Bajo.

### Impacto bajo

**L-21 · [VERIFICADO-código] Endpoints sin uso**
- **Evidencia**:
  - Sin uso en ningún lado: POST `/tipos/sugeridos`.
  - Sin uso en el FE ni en las pruebas: GET `/usos`.
  - Solo en pruebas: PATCH `/usos/{id}`, GET `/usos/{id}/historial`, GET `/resolver` y POST `/trabajos/{id}/cancelar`. Este último hace que no se puedan cancelar borradores desde la pantalla, así que `ImprimirView` acumula borradores.
- **Solución**: Retirar `/tipos/sugeridos` y GET `/usos`, o usarlos. Agregar «Cancelar» en `ImprimirView`. Dejar `/resolver` como API documentada solo si comparte el armado de L-07.
- **Riesgo**: Bajo.

**L-22 · [VERIFICADO-código] Constantes y ayudas duplicadas; patrones de `api.py` que repiten el modelo**
- **Evidencia**: Lista completa en la sección 4, «Genericidad». Además, `reglas.py` reexporta funciones privadas de `condiciones`.
- **Solución**: Una sola fuente para cada valor.
- **Riesgo**: Bajo.

**L-23 · [VERIFICADO-código] Huecos funcionales**
- **Evidencia**:
  - No hay lote por línea ni por caja; las variables manuales son por trabajo.
  - El prepack no se explota a unidades.
  - Una etiqueta de artículo no lleva datos de su caja.
  - «Una por unidad» suma unidades distintas al juntar líneas.
  - Ver la matriz de la sección 2.
- **Solución**: Decisión de producto: variables manuales por registro y un grupo `bulto` opcional para el sujeto ARTICULO.
- **Riesgo**: Medio.

**L-24 · [VERIFICADO-código] Impresión y reimpresión poco controladas**
- **Evidencia**:
  - `confirmar_impresion` se puede repetir y sobrescribe `impresion` (`trabajos.py:1131-1133`).
  - Las reimpresiones no se confirman.
  - `reimprimir` no usa `ejecutar` ni idempotencia (`api.py:585-590`).
  - `marcar_descarga` no bloquea, así que puede perder cuentas (`generacion.py:869`).
  - Inconsistencia de alcance: el proveedor solo ve los trabajos que creó (`trabajos.py:86`), pero reimprime y confirma lotes de los internos de sus OC (`generacion.py:794-795`).
- **Solución**: Historial de confirmaciones, confirmación por reimpresión, y un criterio de alcance único.
- **Riesgo**: Bajo.

**L-25 · [VERIFICADO-código] Mensajes que no se traducen y 500 por clave repetida**
- **Evidencia**:
  - `"PO {n}: " + mensaje` (`trabajos.py:535`): «PO {0}: {1}» no existe en `i18n/servidor.json`.
  - La lista de diferencias se une con `"; "` (`772-774`).
  - `RuntimeError` en español por clave repetida o larga, que da 500 (`546-548`).
  - Los errores de segundo plano quedan en `t.error` como texto libre (`918`).
- **Solución**:
  - Devolver `detalle` estructurado con `parte` y `oc` en lugar de concatenar.
  - Usar `ErrorNegocio` con código en lugar de `RuntimeError`.
- **Riesgo**: Bajo.

### Concurrencia: qué funciona bien

- **Mismo trabajo**: `FOR UPDATE` en `cargar(bloquear=True)` (`trabajos.py:89-97`), más el estado EN_PROCESO y el arriendo con la toma por UPDATE condicional (`656-665`). Dos usuarios generando el mismo trabajo quedan en fila; el segundo recibe `ya_generado`.
- **Reimpresión simultánea**: `refresh(with_for_update)` numera bien (`1190-1191`).
- **Celda de usos**: firma más `FOR UPDATE` (`usos.py:601-603`).

Lo que falla está en L-13 (entre trabajos), L-16 (la serie retenida durante el dibujo) y L-24 (contadores sin bloqueo).
