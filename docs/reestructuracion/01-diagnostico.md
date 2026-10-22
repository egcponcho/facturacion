# Reestructuración · Fase 1: inventario y diagnóstico

**Fecha:** 22/10/2026 · **Base:** rama `claude/bold-lovelace-iwx2wa`, commit `535abcb` (sobre `main` `a295d81`).

Este documento parte de la auditoría anterior ([`../AUDITORIA_INTEGRAL.md`](../AUDITORIA_INTEGRAL.md), 13/10/2026) y verifica qué sigue vigente. No la repite: cita sus códigos cuando un hallazgo ya estaba allí. Cada hallazgo tiene un código (`G-` genérico, `D-` datos, `I-` integración, `M-` módulos, `U-` interfaz, `L-` limpieza, `S-` seguridad) que usan las fases siguientes y el informe final.

## 1. Inventario

| Elemento | Cantidad | Dónde |
|---|---|---|
| Rutas de la API | 427 | `backend/app/modulos/*/api*.py` |
| Tablas | 121 | `backend/app/modelos/*.py` |
| Migraciones | 87 (cabeza `0087`) | `backend/alembic/versions` |
| Líneas de Python | ≈ 50 900 | `backend/app` |
| Líneas de Vue y JS (sin traducciones) | ≈ 34 400 | `frontend/src` |
| Pantallas | 39 vistas y 136 componentes | `frontend/src` |
| Archivos de prueba de servidor | 79 (717 pruebas, 4 omitidas) | `backend/tests` |
| Pruebas de navegador | 2 (recorrido y etiquetado) | `frontend/e2e` |
| Textos traducidos | ≈ 6 700 claves × 5 idiomas | `frontend/src/i18n`, `backend/app/i18n` |

**Arquitectura actual.**

- Servidor FastAPI en capas: `api*.py` (rutas) → servicios del módulo (reglas y permisos) → modelos SQLAlchemy.
- Multiempresa por `organizacion_id`, con filtro automático (`core/organizacion.py`) y RLS en PostgreSQL.
- Alembic se ejecuta en cada arranque.
- Interfaz en Vue 3 con un módulo por carpeta.
- Navegación por módulos, definida en `frontend/src/nucleo/modulos.js`, desde el commit anterior.

## 2. Lo que ya está bien y se conserva

- **Autorización en el servidor.** Cada servicio llama a `exigir(user, permiso)` (`modulos/acceso/permisos.py:202`). Se revisaron muestras de clasificación, arancel y productos y todas validan. La interfaz solo oculta.
- **Integridad por código.**
  - Los documentos guardan el código de sociedad, centro, moneda… con una llave foránea compuesta `(organizacion_id, codigo)` (`modelos/referencias.py`).
  - La coherencia de organización entre padre e hijo se garantiza con llaves `_org`, verificadas por `tests/test_integridad_bd.py`.
- **Catálogos configurables.** Ya son datos y no código:
  - atributos de variante, familias con sus ejes y escalas;
  - tipos de empaque, recetas y reglas de empaque;
  - estados de liberación con sus códigos del ERP;
  - etiquetas de estado de documentos (`EstadoDocumento`), campos propios, roles, monedas, unidades e incoterms;
  - series de numeración, módulos activables y tableros por rol.
- **Idempotencia y concurrencia.** Encabezado `Idempotency-Key` (`ejecutar(…, clave, …)`), edición exclusiva y versiones de datos con ETag.
- **Tableros por módulo.** Ya existen tableros de indicadores de compras, facturación, logística y productos, con periodos, metas y selección por rol (`modulos/seguimiento/indicadores.py:43`).

## 3. Hallazgos

### 3.1 Dependencias de una empresa, un rubro o un ERP (genérico)

| Código | Hallazgo | Evidencia | Acción |
|---|---|---|---|
| G-01 | Filtros de seguimiento fijos a **estilo, color y talla** (rubro calzado y ropa). Un químico o una materia prima no tiene filtros útiles. | `modulos/seguimiento/seguimiento.py:37,231,245-255`; `SeguimientoView.vue:42,169-181` | Filtrar por los atributos de variante del catálogo |
| G-02 | **Códigos de SAP fijos** en el filtro de liberación logística (300/301/304) y comercial (C/P), aunque el servidor ya los lee del catálogo. Ya estaba como G-01 en la auditoría anterior; sigue sin corregir. | `SeguimientoView.vue:174-178` | Opciones desde el catálogo `estados_liberacion` |
| G-03 | Tablero de embarques con la columna «Estilo · color» y ficha del producto con «Tallas» y «Código de talla». | `TableroEmbarques.vue:65`; `ProductoView.vue:587,671` | Texto de la variante armado con sus atributos |
| G-04 | Textos aduaneros de Centroamérica fijos en los PDF: «HS code (SAC)», «Tax ID (NIT / RUC)», «Duty (DAI)». | `modulos/documentos/documentos.py:458,563,754,824`; `productos/productos.py:1331` | Nombre de la nomenclatura, del arancel y de la identificación fiscal por país |
| G-05 | Valores fijos de una implantación: unidad de prepack `"CJ"` y moneda por defecto `"USD"`. | `maestros/unidades.py:12`; `empresa/organizacion.py:48` | Marca en el catálogo de unidades; moneda de la organización |
| G-06 | Comentarios y ayudas que presuponen SAP («Sociedad legal (compañía de SAP)», «Centro de SAP»). | `modelos/maestros.py:89,112,395`; `maestros/catalogos.py:410` | Redacción neutral |
| G-07 | Columnas fijas `estilo`, `color` y `talla` en `articulos`, `posiciones_oc`, `factura_lineas` y `prepacks`, junto al modelo genérico (`articulo_atributos` y `variante` JSON). Dos fuentes para lo mismo (ver D-02). | `modelos/maestros.py:482-484,451-452` | Lectura genérica en servicios y vistas; las columnas quedan como compatibilidad hasta migrar |
| G-08 | La base de una empresa concreta citada en un script. | `backend/scripts/sieca/LEEME.md:17` («base ADOC») | Redacción neutral |

### 3.2 Base de datos

| Código | Hallazgo | Evidencia | Acción |
|---|---|---|---|
| D-01 | **Seis taxonomías para agrupar productos.** Hay dos tablas de etiquetado «anteriores» que siguen con llave foránea desde `articulos`, `productos`, `grupos_articulos` y `usos_diseno`. Tres pantallas usan la palabra «familia» para conceptos distintos. Las seis son: <ul><li>`grupos_producto` (familia y categoría)</li><li>`grupos_articulos` (empaque y comercial)</li><li>`categorias_articulo` (texto)</li><li>dominios y categorías de clasificación (`categorias_producto`)</li><li>`familias_etiquetado` (anterior)</li><li>`categorias_etiquetado` (anterior)</li></ul> | `modelos/grupos.py`, `modelos/maestros.py:419-436,499-503`, `modelos/referencias.py` (COHERENCIA) | **Decisión del usuario** (fase 2, alternativas) |
| D-02 | Variante guardada dos veces: en columnas fijas y en `articulo_atributos`; en las líneas, en columnas y en `variante` JSON. | `documentos.py:124,131` lee una o la otra | Una sola lectura (`variantes.texto`) en servicios |
| D-03 | Referencias por código **sin llave foránea**: `unidades_medida.base` (autorreferencia) y `atributos_variante.unidad`. | `modelos/maestros.py:337,575`; no figuran en `REFERENCIAS` | Agregar a `REFERENCIAS` con migración que limpie los huérfanos |
| D-04 | **Terceros a medias.** `terceros` y `tercero_roles` existen, pero `proveedores.tercero_id` y `transportistas.tercero_id` son opcionales, y sociedades y centros no los usan. | `modelos/comercial.py:45-95`; `modelos/maestros.py:72`; `modelos/transporte.py:53` | **Decisión del usuario** |
| D-05 | Datos de rollback de la migración `0081` (tablas `*_etiquetado` anteriores y columnas `*_anterior_id`). Se mantuvieron para volver atrás. | `modelos/maestros.py:431,502` | Se retiran junto con D-01 |

### 3.3 Integración con ERP

| Código | Hallazgo | Evidencia |
|---|---|---|
| I-01 | **No hay capa de integración.** Lo único que existe es la importación de OCs desde un archivo con perfiles de columnas (`perfiles_importacion`) y la carga de datos maestros por Excel (`maestros/cargas.py`). | `modulos/compras/perfiles.py`, `modelos/compras.py:177-203` |
| I-02 | Sin **referencias externas**: un registro no guarda su identificador en el ERP. La deduplicación de la importación de OCs se hace por número de OC y por huella del archivo (`clave_filas`), no por sistema de origen. | `modelos/compras.py:201` |
| I-03 | Sin **bitácora de integración** común: cada importación guarda su `resultado` JSON propio. | `ImportacionOC.resultado` |
| I-04 | Sin **exportación** hacia el ERP (facturas, recepciones), salvo PDF y Excel para personas. | — |

Ningún ERP tiene adaptador implementado ni probado. No se debe afirmar compatibilidad con SAP, Oracle, Dynamics u Odoo.

### 3.4 Módulos y navegación

| Código | Hallazgo | Evidencia |
|---|---|---|
| M-01 | Los **tableros por módulo** viven en Análisis (`/tableros/compras`, `/tableros/facturacion`, `/tableros/logistica`). Compras, Facturación y Logística no tienen su propia portada. | `nucleo/modulos.js`; `router.js:68` |
| M-02 | Productos tiene dos resúmenes: la portada operativa (`/productos`, commit anterior) y el tablero de indicadores (`/tableros/productos`). | — |
| M-03 | La ficha del producto no muestra dónde se usa (OCs, facturas, embarques, existencias) ni su receta de empaque efectiva. | `ProductoView.vue` (0 referencias a recetas) |
| M-04 | Configuración repartida en Empresa, Plataforma, Usuarios y accesos, y la configuración de cada módulo, sin una portada común. | `router.js` |

### 3.5 Interfaz

| Código | Hallazgo | Evidencia |
|---|---|---|
| U-01 | **Sin escala tipográfica.** 365 tamaños de letra escritos a mano en las vistas y ningún token de tamaño. | `grep font-size` en `*.vue` |
| U-02 | Colores escritos a mano fuera de los tokens (6). | `EmpresaView.vue`, `LeadTimeView.vue`, `PerfilView.vue`, `PanelIntegridad.vue`, `ProductoView.vue` |
| U-03 | Ventanas emergentes en exceso en los documentos: lista de empaque 11, factura 7, administración 7, embarque 6. Ya estaba como U-03 en la auditoría anterior. | `PackingListView.vue`, `FacturaView.vue`, `AdminView.vue`, `EmbarqueView.vue` |
| U-04 | Vistas demasiado grandes para mantenerlas: <ul><li>`PackingListView.vue`: 1 172 líneas</li><li>`ProductoView.vue`: 1 124</li><li>`TrabajoEtiquetasView.vue`: 1 093</li><li>`MantenimientoView.vue`: 851</li></ul> | — |
| U-05 | La pantalla de catálogos dice «Datos maestros» aunque ya está dentro de cada módulo. | `MantenimientoView.vue` |

### 3.6 Código sin uso (verificado de nuevo)

Se buscaron las referencias en `backend/app`, `backend/scripts`, `backend/tests`, `backend/alembic` y `frontend/src`:

- **4 archivos de interfaz sin ningún import:** `componentes/ThOrden.vue`, `componentes/SelectorColumnas.vue`, `composables/useTabla.js` y `composables/useColumnas.js`. Este último solo lo importa `SelectorColumnas.vue`.
- **11 funciones de servidor sin ninguna referencia:**
  - `clasificacion/atributos.py` `config_motor`
  - `clasificacion/oficial.py` `exigir_trazable`
  - `documentos/letras.py` `numero_en_letras`
  - `maestros/acuerdos.py` `acuerdos_para`
  - `productos/ficha.py` `Catalogo.desde_json`
  - `productos/productos.py` `digitos_pais` y `_inciso_ctx`
  - `seguimiento/dashboard.py` `_meses` y `_fecha_factura`
  - `seguimiento/metricas.py` `oc_poca_holgura`
  - `transporte/leadtimes.py` `dias_post_arribo`

`numero_en_letras` se conserva: la auditoría anterior advirtió que sirve para el monto en letras. `estado_tiempo` tiene 13 coincidencias, pero son claves de diccionario; se revisa aparte.

### 3.7 Idioma del código

- Los identificadores, comentarios y documentación ya están en español.
- **Los textos de interfaz y los mensajes de error usan el inglés como clave de traducción** (`t('Products')`, `ErrorNegocio("Unknown module.")`), y el español se muestra desde `es.json`.
  - Fue una decisión anterior para soportar cinco idiomas (inglés, español, chino, hindi y árabe).
  - Cambiar la lengua de origen al español toca unas 6 700 claves en dos catálogos y cinco idiomas. Se deja como **excepción técnica justificada**: lo que ve el usuario sí está en español.
- La alternativa (fuente en español) se describe en la fase 2.

### 3.8 Seguridad y confiabilidad

- No se encontraron rutas de escritura sin autorización en las muestras revisadas.
- La prueba de navegador del asistente de etiquetas encontró una petición no autorizada del proveedor; se corrigió en `d525407`.
- Pendientes de la auditoría anterior que siguen abiertos:
  - dependencias sin versión fija (`requirements.txt` con `>=`);
  - falta integración continua.

## 4. Riesgos

- **D-01 y D-04** exigen migrar datos de producción. Sin una decisión, se mantienen y no se construye nada nuevo encima de las tablas anteriores.
- **G-07 y D-02**: retirar las columnas fijas antes de que todo lea el modelo genérico rompería documentos e importaciones. Primero se cambia la lectura y luego, en otra migración, se retiran las columnas.
