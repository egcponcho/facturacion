# Auditoría integral y plan de mejora

**Fecha:** 22/10/2026.
**Rama:** `claude/bold-lovelace-iwx2wa`.
**Commit de partida:** `c10ad69`. Al empezar, la rama era igual a `origin` y no había cambios pendientes.

Este documento sigue el formato pedido en sus doce secciones.

- **Base.** Parte de lo verificado antes: [`01-diagnostico.md`](01-diagnostico.md), [`03-informe.md`](03-informe.md), la auditoría del etiquetado ([`../ETIQUETADO_AUDITORIA.md`](../ETIQUETADO_AUDITORIA.md) y sus anexos) y [`../AUDITORIA_INTEGRAL.md`](../AUDITORIA_INTEGRAL.md). No repite esos documentos: contrasta lo que dicen con el código actual.
- **Estados de cada hallazgo:**
  - **confirmado**: reproducido en el código o en una prueba.
  - **corregido**: cambiado y probado. La prueba falla sin el cambio.
  - **verificado**: se comprobó que ya funciona bien.
  - **pendiente**: no se hizo, con el motivo.
  - **bloqueado**: necesita una decisión o un entorno que aquí no hay.

---

## 1. Estado del repositorio

| Dato | Valor |
|---|---|
| Rama | `claude/bold-lovelace-iwx2wa`, igual a `origin` |
| Commit revisado al empezar | `c10ad69` |
| Diferencia con `main` (`a295d81`) | La rama va 23 commits por delante y 0 por detrás. `main` no tiene trabajo más reciente. |
| Cambios pendientes al empezar | Ninguno |

**Commits de esta auditoría:**

| Commit | Qué corrige |
|---|---|
| `a3798ef` | Etiquetado: código de caja del packing list, cantidad escrita a mano y lotes anulados |
| `8a0f476` | Integraciones: referencias sin reasignación silenciosa, estructura detectada y filas rechazadas |
| `2644393` | Cargas masivas: tope configurable de filas por archivo |
| `9fa64ec` | Etiquetado: una caja con líneas de varias OCs lleva una sola etiqueta |

## 2. Arquitectura actual

| Capa | Tecnología | Detalle |
|---|---|---|
| Servidor | Python 3.11, FastAPI, SQLAlchemy 2 y Alembic | <ul><li>443 operaciones en `/api`.</li><li>134 tablas.</li><li>90 migraciones; Alembic se ejecuta al arrancar.</li></ul> |
| Interfaz | Vue 3.5 y Vite 6 | <ul><li>41 vistas y 179 componentes `.vue`.</li><li>Un módulo por carpeta.</li><li>Menú por módulos en `nucleo/modulos.js`.</li></ul> |
| Datos | PostgreSQL en producción, SQLite en pruebas y en la demostración | <ul><li>Multiempresa por `organizacion_id`, con filtro automático (`core/organizacion.py`).</li><li>RLS en PostgreSQL.</li><li>Llaves compuestas `(id, organizacion_id)` (`modelos/referencias.py`).</li></ul> |
| Autorización | En el servidor | `exigir(user, permiso)` en cada servicio. La interfaz solo oculta. |
| Pruebas | pytest y Playwright | <ul><li>82 archivos de pytest (`backend/tests`).</li><li>2 recorridos de navegador (`frontend/e2e`).</li><li>Lint con ruff y eslint.</li></ul> |

**Relaciones del flujo principal:**

- OC → posiciones → factura y sus líneas, que guardan una copia de los datos de la OC.
- Lista de empaque (PL) → líneas de PL → grupos de cajas (árbol: pallet, caja, inner).
- Embarque y unidad de carga → recepción.
- Etiquetado: tipos, diseños con versiones, usos (reglas) y trabajos.
  - Un trabajo se arma con partes por OC o PL, se planea, se genera en lotes con ítems e instantánea, y se puede reimprimir o anular.
  - Lee la OC, el artículo y la PL en vivo, y compara lo revisado con lo que va a generar.
- Integraciones: adaptador, mapeo versionado, ejecución con huella y referencias externas.
  - Aplican mediante los servicios del núcleo (`ordenes._clasificar` y `aplicar_importacion`).

**Facturación y procesos financieros (4.5).** En esta rama existen:

- facturas comerciales, con su revisión y finalización;
- condiciones de pago (`CondicionPago`), solo como catálogo.

**No existen** pagos, vencimientos, notas de crédito o débito, cuentas por pagar ni conciliaciones: no hay modelos ni rutas. Esos puntos no se auditaron porque no hay qué auditar. `backend/app/modulos/comercial/` solo contiene un `__pycache__` local, sin archivos en git.

## 3. Hallazgos confirmados

| Id | Archivo | Problema | Impacto | Evidencia |
|---|---|---|---|---|
| H-01 | `integraciones/servicio.py` `_referenciar` | Buscaba la referencia por registro interno y, si no la encontraba, **por código externo**, y luego sobrescribía `interno_id` y `codigo_externo`. | Un código externo que ya apuntaba a la OC A pasaba **en silencio** a la OC B. Si los dos vínculos chocaban, la llave única daba un error del servidor. | Lectura del código y prueba `test_una_referencia_externa_no_se_reasigna_en_silencio` |
| H-02 | `etiquetado/campos._unidades` | El código de caja de la etiqueta se numeraba por tipo de empaque en **orden de id**, y sin prefijo quedaba vacío. El packing list numera por prefijo en el **orden del árbol**. | La caja rotulada «C1» no era la «C1» del packing list (auditoría del etiquetado, I-01). | `docs/auditoria_etiquetado/pruebas/numeracion_cajas.py`: etiqueta C1–C2 frente a PL C4–C5 |
| H-03 | `etiquetado/generacion.py` | La cantidad escrita a mano solo se usaba en tipos MANUAL. En «una por unidad» o «una por línea» se reemplazaba **sin aviso**, aunque la pantalla la mostraba como escrita a mano. | Se imprimía una cantidad distinta de la pedida (L-03). | Prueba de la auditoría: se escribió 5 y se generaron 24 |
| H-04 | `etiquetado/generacion._previas`, el resumen y `buscadores.py` | Un lote **anulado** seguía contando como «ya generado»: el aviso, el resumen de la OC y la lista de OCs (D-12, GN-05). | Tras anular, la persona veía un aviso falso de impresión doble y cifras infladas. | Prueba de la auditoría y `test_etiquetado_anular` ampliada |
| H-05 | `etiquetado/trabajos._validar` | En un trabajo con varias OCs, una caja mixta aparecía en la parte de **cada** OC. | 2 cajas físicas daban 4 etiquetas, sin ningún aviso. | Prueba de la auditoría y `test_una_caja_compartida_por_dos_ocs_lleva_una_sola_etiqueta` |
| H-06 | `integraciones/servicio.entrada_aplicar` | Se podía aplicar una ejecución **sin ninguna fila válida**. Su huella quedaba como «aplicada», y al corregir el mapeo el mismo archivo se rechazaba como ya aplicado. | No se podía reprocesar un archivo después de corregir el mapeo. | Captura de la pantalla («aplicadas: 0») y `test_estructura_y_filas_rechazadas` |
| H-07 | `compras/ordenes.importar_previa` y `integraciones/servicio.entrada_previa` | Ningún importador limitaba las filas, solo el tamaño en MB. | Un archivo válido podía traer cientos de miles de filas, procesarse en una sola petición y guardarse completo. | Lectura del código y `test_tope_de_filas_por_archivo` |
| H-08 | `IntegracionesView.vue` | La lista de errores usaba el token `--peligro`, que no existe. | Los errores no se veían en rojo. | Revisión de `styles.css` |

## 4. Riesgos pendientes de verificar

| Riesgo | Por qué falta verificarlo |
|---|---|
| **RLS de PostgreSQL de la migración 0090** | No hay un servidor PostgreSQL en este entorno. Las pruebas usan SQLite. El aislamiento por organización sí se probó en el servicio (sección 9 y `test_otra_empresa_no_ve_las_integraciones`). |
| **Identidad del bulto tras reempacar** (auditoría del etiquetado, D-04) | Al rehacer los grupos de una PL ya etiquetada, los ítems generados pierden `grupo_cajas_id` (se pone en nulo) y el trabajo nuevo no avisa que la PL ya tuvo etiquetas. Confirmado en la prueba de la auditoría. Hace falta una decisión: ¿bloquear el reempaque de una PL con etiquetas reales, o avisar y anular las anteriores? |
| **Prepacks y kits con «una por unidad»** (I-04) | Una línea de prepack cuenta paquetes, no las unidades que contiene. Si la etiqueta va por paquete o por cada unidad del paquete es una regla de negocio por definir. |
| **Otros hallazgos medios y bajos** de `docs/auditoria_etiquetado/` (D-05 … D-25, L-xx, U-xx) | No se volvieron a comprobar uno por uno en esta etapa. Se comprobaron los de seguridad y cantidades (sección 8). |

## 5. Cambios implementados

| Archivo | Cambio |
|---|---|
| `backend/app/modulos/integraciones/servicio.py` | <ul><li>`_referenciar` devuelve las referencias hechas y los conflictos.</li><li>Las altas van en un *savepoint*: un choque de llave única por concurrencia es un conflicto, no un error del servidor.</li><li>`_errores_de_conflictos` explica cada conflicto.</li><li>`desvincular`, con motivo y registro en el historial.</li><li>`estructura` detecta las columnas del archivo.</li><li>Los rechazos guardan la fila original, hasta 200.</li><li>`rechazadas` genera el CSV de filas rechazadas.</li><li>`_aplicada`: la huella cuenta solo con la misma versión del mapeo.</li><li>Sin filas aplicables, no se aplica.</li><li>Tope de filas.</li></ul> |
| `backend/app/modulos/integraciones/api.py` | Rutas nuevas: <ul><li>`POST /integraciones/{id}/referencias/{ref}/desvincular`</li><li>`GET /integraciones/ejecuciones/{id}/rechazadas`</li></ul> |
| `backend/app/modulos/documentos/idioma_doc.py` | `armado()` traduce un mensaje ya armado por su plantilla y deja literales las partes variables (columnas, códigos). |
| `backend/app/modulos/etiquetado/campos.py` | El código de caja y el del contenedor salen de `empaques.numeracion` y `empaques.prefijo`. |
| `backend/app/modulos/etiquetado/generacion.py` | <ul><li>`_escritas`: la cantidad escrita a mano manda en cualquier tipo y deja la advertencia `cantidad_a_mano`.</li><li>Los lotes anulados no cuentan como ya generados.</li></ul> |
| `backend/app/modulos/etiquetado/trabajos.py` | Una caja compartida entre las OCs de un trabajo se etiqueta una sola vez, con el aviso `bulto_compartido`. |
| `backend/app/modulos/etiquetado/buscadores.py` | El conteo de lotes por OC excluye los anulados. |
| `backend/app/core/config.py` y `core/empresa.py` | Nueva regla `IMPORTACION_MAX_FILAS` (20 000 de fábrica) y su comprobación `tope_filas`. |
| `backend/app/modulos/compras/ordenes.py` | La carga de OCs aplica el tope de filas. |
| `frontend/.../integraciones/componentes/ErroresEjecucion.vue` (nuevo) y `IntegracionesView.vue` | Ver la sección 6. |

## 6. Mejoras de interfaz

Todas en la pantalla **Configuración → Integraciones**:

- **Estructura detectada en la vista previa.** Cada campo del sistema muestra la columna que se busca y si está. Los obligatorios que faltan salen en rojo; los opcionales ausentes se resumen en una línea, y también las columnas del archivo que no se usan.
- **Resultado de la aplicación.** Queda a la vista con su estado, su resumen y sus errores, en lugar de desaparecer en un aviso.
- **Errores en un componente propio** (`ErroresEjecucion`), el mismo en la vista previa, el resultado y la bitácora:
  - cada error dice la fila del archivo o el código externo;
  - el conflicto de un código ya vinculado ofrece **Desvincular** en el mismo lugar, con el motivo en línea y sin ventana emergente;
  - el botón **Descargar filas rechazadas** baja un CSV con las columnas originales y el motivo.
- **Bitácora.** Cada ejecución con errores tiene «Errores (n)», que despliega el detalle. El resumen se reparte en varias líneas en lugar de salirse de la tabla.
- **Mapeo.** Las columnas del último archivo leído se ofrecen como sugerencias (`datalist`) al escribir el nombre externo.
- **Botones que dicen lo que hacen.** «Aplicar las filas válidas» cuando hay rechazos. Si nada es aplicable, no hay botón: un texto dice qué corregir.
- **Mensajes con datos literales.** Las columnas del archivo salen entre comillas («Qty») y no se traducen.

Se revisó en el navegador (1400 px, administrador) con un archivo al que le faltaba la columna de cantidad. Las capturas mostraron la estructura, el error, la descarga y el resultado aplicado.

## 7. Integraciones y mapeo masivo: antes y después

| Aspecto | Antes | Después |
|---|---|---|
| Código externo ya vinculado a otro registro | Se reasignaba en silencio | Conflicto en la bitácora; se desvincula con motivo |
| El registro ya tiene otro código | Se reemplazaba en silencio | Conflicto |
| Dos ejecuciones simultáneas | Error del servidor por la llave única | Conflicto (la llave única de la base es la garantía) |
| Estructura del archivo | No se mostraba | Columnas, campo por campo, obligatorios faltantes y columnas sin usar |
| Filas rechazadas | Solo las 20 primeras en pantalla | Todas en la bitácora (hasta 200) y en CSV con columnas originales y motivo, en el idioma del documento |
| Rechazos del núcleo (error o conflicto) | Solo en la vista previa | También en la ejecución y en el CSV |
| Aplicar sin filas válidas | Permitido; bloqueaba volver a cargar el archivo | Rechazado (422) |
| Mismo archivo con el mapeo corregido | Rechazado como ya aplicado | Se acepta; con el mismo mapeo sigue rechazado |
| Tamaño de la carga | Solo MB | MB y filas (`IMPORTACION_MAX_FILAS`) |
| Versión del mapeo en cada ejecución | Ya existía (`mapeo_id`) | Sin cambios |

**Separación de conceptos.** El mapeo de campos (columna externa → campo interno) y la equivalencia de valores (códigos) ya estaban separados en `IntegracionMapeo.campos` y `.codigos`, y se mantienen así.

**Mensajes en inglés (5.6).**

- El servidor responde con la clave en inglés y la interfaz la muestra traducida (`servidor.json` y `tx`). Es la decisión vigente de idioma (`02-arquitectura.md` §6.3).
- Los mensajes citados en la petición («The integration is inactive», «The content has no rows with data», «Unknown date format») **ya se ven en español** en la interfaz.
- Lo que faltaba era el CSV descargado, que ahora se traduce con `armado()`.

## 8. Etiquetado, empaque y packing list

**Contraste con la auditoría anterior.** Se volvieron a correr sus 17 pruebas sobre el código actual. Imprimen el comportamiento en lugar de afirmarlo, así que se leyó cada salida:

| Hallazgo anterior | Estado hoy |
|---|---|
| Parámetros sin validar al crear un trabajo (dpi, hoja, ids) | **verificado**: responde 422 |
| El proveedor ve la configuración (usos, matriz, celda, simular) | **verificado**: responde 403 |
| El proveedor lee imágenes de otro proveedor (L-01) | **verificado**: responde 404 |
| Vista previa con una OC ajena | **verificado**: responde 404 |
| Diseño sin versión aprobada | **verificado**: error `sin_plantilla`, no se cae |
| Código de caja distinto del packing list (I-01) | **corregido** (H-02) |
| Cantidad escrita a mano ignorada (L-03) | **corregido** (H-03) |
| Lote anulado cuenta como generado (D-12, GN-05) | **corregido** (H-04) |
| Caja compartida duplicada entre OCs | **corregido** (H-05) |
| Borrar una línea de OC con etiquetas | **verificado**: la llave foránea lo impide y la API responde 409 `en_uso` |
| Identidad del bulto al reempacar (D-04) | **pendiente**, necesita una decisión (sección 4) |

**Procedencia de los datos.** Ya estaba definida y no cambió:

- Una etiqueta pendiente lee en vivo la OC, el artículo y la PL.
- La generación compara lo revisado y responde 409 `datos_cambiaron` si algo cambió.
- El lote guarda una instantánea de los valores impresos.

**Separación entre etiqueta y empaque.** Ahora el código de caja sale de la misma función que el documento. Una etiqueta no cambia cantidades de empaque: no escribe en el empaque.

## 9. Seguridad y datos

| Punto | Estado |
|---|---|
| Aislamiento de integraciones por organización | **verificado** con una prueba nueva. Otra empresa no ve la integración, sus ejecuciones, sus filas rechazadas, sus referencias ni sus mapeos, y no puede ejecutarla (404). |
| Permisos nuevos | <ul><li>Desvincular exige `integraciones.configurar`.</li><li>Descargar rechazadas exige `integraciones.ver`.</li><li>Probado con un usuario sin permiso (403).</li></ul> |
| Unicidad de referencias externas | Garantizada por las llaves únicas de la base (`uq_referencias_externas_codigo` y `_interno`, migración 0090), no solo por la consulta previa. |
| Datos guardados de los archivos | <ul><li>Solo las filas rechazadas, con un tope de 200 por ejecución.</li><li>Las válidas ya se guardaban (`filas`) para aplicar.</li><li>No se guarda el archivo completo.</li></ul> |
| Migraciones | **Ninguna nueva.** Los cambios no tocan el esquema. |

## 10. Pruebas ejecutadas

| Comando | Resultado |
|---|---|
| `pytest tests/test_etiquetado_*.py tests/test_empaque*.py tests/test_flujo.py` | 156 pasan y 1 omitida, tras H-02 a H-04 |
| `pytest tests/test_etiquetado_*.py` | 112 pasan y 1 omitida, tras H-05 |
| `pytest tests/test_integraciones.py tests/test_perfiles_importacion.py` | 15 pasan |
| Pruebas nuevas **sin** la corrección | Fallan las 4 de etiquetado (H-02 a H-05). Las de integraciones dependen de rutas y funciones nuevas. |
| `ruff check app tests`, `eslint src`, `vite build`, extracción de idiomas y `test_i18n` | Sin errores (verificación estricta antes de cada commit) |
| Suite completa del servidor | _Se completa en la sección 10.1._ |
| Recorridos del navegador | _Se completa en la sección 10.1._ |

**Limitación.** No hay pruebas sobre PostgreSQL en este entorno.

### 10.1 Validación final

_Se agrega al terminar la corrida final._

## 11. Código eliminado o consolidado

- **Sin eliminaciones** en esta etapa.
- **Consolidado:**
  - la numeración de cajas del etiquetado usa la del empaque, una sola función para los dos módulos;
  - la lista de errores de ejecución es un solo componente para tres lugares;
  - los rechazos del mapeo y del núcleo quedan en una sola lista por ejecución.

## 12. Pendientes priorizados

| Prioridad | Hallazgo | Evidencia en el repositorio | Cambio realizado o propuesto | Prueba | Estado |
|---|---|---|---|---|---|
| Crítica | Reasignación silenciosa de referencias externas | `integraciones/servicio.py` `_referenciar` | Conflicto explícito, desvincular con motivo, unicidad en la base | `test_una_referencia_externa_no_se_reasigna_en_silencio`, `test_la_unicidad_la_garantiza_la_base`, `test_desvincular_pide_permiso_y_motivo` | corregido |
| Alta | Código de caja de la etiqueta distinto del packing list | `etiquetado/campos.py` `_unidades` | Usa `empaques.numeracion` y `empaques.prefijo` | `test_el_codigo_de_caja_de_la_etiqueta_es_el_del_packing_list` | corregido |
| Alta | Cantidad escrita a mano ignorada | `etiquetado/generacion.py` | `_escritas` con la advertencia `cantidad_a_mano` | `test_la_cantidad_escrita_manda_sobre_la_calculada` | corregido |
| Alta | Caja compartida entre OCs etiquetada dos veces | `etiquetado/trabajos.py` `_validar` | Una etiqueta por caja física, aviso `bulto_compartido` | `test_una_caja_compartida_por_dos_ocs_lleva_una_sola_etiqueta` | corregido |
| Media | Lote anulado cuenta como generado | `generacion._previas`, el resumen y `buscadores.py` | Se excluye `anulada_en` | `test_anular_deja_los_registros_pendientes_y_se_genera_de_nuevo` | corregido |
| Media | Aplicar sin filas válidas bloquea la corrección | `integraciones/servicio.py` | 422 sin filas aplicables; huella por versión del mapeo | `test_estructura_y_filas_rechazadas` | corregido |
| Media | Cargas masivas sin tope de filas | `ordenes.importar_previa`, `servicio.entrada_previa` | Regla `IMPORTACION_MAX_FILAS` | `test_tope_de_filas_por_archivo` | corregido |
| Media | Estructura del archivo y filas rechazadas descargables | `integraciones/servicio.py`, `IntegracionesView.vue` | `estructura`, `rechazadas`, pantalla | `test_estructura_y_filas_rechazadas` y revisión en el navegador | corregido |
| Baja | Token de color inexistente en la lista de errores | `IntegracionesView.vue` | Usa `--error` | revisión visual | corregido |
| Media | Identidad del bulto al reempacar una PL ya etiquetada | `GeneracionItem.grupo_cajas_id` (SET NULL); auditoría D-04 | Decidir entre bloquear el reempaque con etiquetas reales o avisar y anular | prueba de la auditoría | bloqueado, necesita decisión |
| Media | Etiquetas «una por unidad» en prepacks y kits | `generacion._grupos_articulo`; auditoría I-04 | Definir si se etiqueta el paquete o cada unidad | — | bloqueado, necesita decisión |
| Media | RLS de 0090 sin probar en PostgreSQL | `alembic/versions/0090_…py` | Correr `test_integridad_bd` y el aislamiento con `DATABASE_URL` de PostgreSQL | — | pendiente, sin PostgreSQL aquí |
| Media | Pantalla de trabajo contextual OC → empaque → etiquetas → PL (6.2) | Ya hay entradas desde OC, PL y producto (`ETIQUETADO_AUDITORIA.md` §1.1) | Propuesta U-xx de la auditoría del etiquetado; diseño por acordar | — | pendiente |
| Baja | Dos criterios con el mismo nombre de «importe facturado» | `ordenes.py:86` (precio de la OC, avance) frente a `indicadores.py` (precio de la factura) | Renombrar en la lista de OC a «avance por valor» | — | pendiente (C-01/A-03 de la auditoría anterior) |
| Baja | Ventanas emergentes largas y vistas grandes (U-03, U-04) | `PackingListView.vue`, `ProductoView.vue`… | Paneles por etapas, dividir en componentes | — | pendiente |
| — | Decisiones de datos D-01, D-04 e idioma de origen | `02-arquitectura.md` §6 | Esperan tu elección | — | bloqueado, necesita decisión |
