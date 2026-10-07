# Revisión integral: UX/UI, arquitectura y adaptabilidad

Revisión hecha sobre el sistema actual (backend FastAPI + SQLAlchemy, 64 tablas;
frontend Vue, 20 vistas). No se propone rehacer nada ni quitar funciones: se
propone **cómo llegar a ellas** con menos ruido y **cómo desamarrar** lo que
hoy depende de una empresa, de SAP o de Centroamérica.

## 1. Lo que ya cumple los principios (se conserva)

| Área | Qué hay | Dónde |
|---|---|---|
| Búsqueda inteligente | Ignora mayúsculas, acentos y orden; varios códigos a la vez; separadores ignorados. Misma regla en servidor y navegador | `frontend/src/busqueda.js`, `common.filtro_texto` |
| Navegación | Menú principal ya reducido a Home, Orders, Invoices, Shipments, Products, Tracking + menú *Settings* | `App.vue` |
| Permisos | Roles libres con permisos por módulo; el servidor valida cada acción (`exigir`) | `services/common.py` |
| Empaque jerárquico | `TipoEmpaque` configurable (nivel, contiene, tara, dimensiones, capacidades, mezcla) y PL por estructura física | `models.TipoEmpaque`, `empaques.py` |
| Lead times | Herencia Global → Región → País → Puerto, pasos CRUD y lead time efectivo calculado | `reglas_lt.py`, `/leadtimes/efectivo` |
| Importación de OC | Vista previa antes de aplicar, columnas reconocidas por alias | `ordenes.importar_previa / importar_aplicar` |
| Auditoría | Bitácora `Historial` con 101 puntos de registro | `common.registrar` |
| Home | Lista de tareas con ruta y acción (corregir, empacar, finalizar, embarcar, aprobar fichas) | `dashboard._tareas` |
| Clasificación | Familias, categorías, preguntas y reglas como configuración; versiones del arancel; países con dígitos y aperturas configurables | módulo de aranceles |
| Preferencias | Idioma, formatos de fecha/número, tema, filas por página, página de inicio | `Usuario.preferencias` |

## 2. Diagnóstico (las 10 preguntas)

1. **Amarrado a una empresa, SAP o Centroamérica**
   - Liberación logística guardada con códigos SAP `300 / 301 / 304` y comercial `C / P`; la lógica pregunta por esos códigos (`ordenes.py`, `seguimiento.py`, `seed.py`).
   - Columna `PosicionOC.codigo_sap`; docstrings de `Sociedad` ("compañía de SAP") y `Centro` ("centro de SAP… bodega fiscal").
   - `GrupoArticulo.categoria` limitado a `CALZADO | ROPA | ACCESORIO` (`catalogos.CATEGORIAS`).
   - País base de clasificación `PAIS_BASE_CLASIF=SV` y reglas de negocio en variables de entorno (`POSICION_EN_VARIAS_FACTURAS`, `FACTURA_EN_UNA_SOLA_UNIDAD`, `PROVEEDOR_PUEDE_FINALIZAR`, `REQUERIR_DATOS_ADUANA`, `DIAS_ALERTA_BORRADOR`, `COMPATIBILIDAD_*`): iguales para cualquier empresa que use la instalación.
   - El esquema arancelario se llama SAC en pantallas y textos; `PaisArancel.modelo_arancel` ya existe pero no hay entidad "esquema".
2. **Pantallas saturadas**: Órdenes (25 encabezados, 7 filtros visibles), Seguimiento (14 filtros), Packing list (1,089 líneas), Producto (1,071), Factura (747), Embarque (664).
3. **Se puede ocultar al inicio**: filtros secundarios de Órdenes y Seguimiento, columnas comerciales/logísticas según la tarea, datos técnicos del embarque y de la OC (mejor en un panel de resumen).
4. **Demasiados clics**: para consultar una OC, factura o embarque desde una tabla hay que salir de la lista y se pierden filtros y página; no hay búsqueda global (hay que saber en qué módulo está un número); los indicadores del Home llevan a la lista general, no siempre filtrada.
5. **Datos maestros mezclados con reglas**: `TipoEmpaque` (dato físico de la caja) decide si se mezclan productos o tallas; `GrupoArticulo.categoria` cumple el papel de política; el rol (`admin | interno | proveedor`) decide a la vez qué se puede hacer y qué datos se ven.
6. **Reglas fijas que deberían ser configuración**: códigos de liberación, compatibilidad entre posiciones de una factura, días de alerta, si el proveedor puede finalizar, si se exigen datos de aduana, categorías de grupo de artículos.
7. **Funciones que deberían ser transversales**: documentos (hoy `Archivo` solo para facturas y `ProductoDocumento` solo para productos), actividad/bitácora (solo la factura tiene pestaña de historial), estado vacío, panel de resumen, selector de columnas, acciones masivas con vista previa.
8. **Requieren migración**: organización y configuración por organización, estados universales de liberación + mapeo externo, documento universal, alcance de datos del rol, política de empaque, campos personalizados, perfiles de importación, módulos activos.
9. **Solo UX/UI**: búsqueda global y Ctrl+K, Home como bandeja con accesos filtrados, panel lateral de resumen, selector de columnas y vistas guardadas por usuario (en sus preferencias), bloqueos que explican cómo resolverse, estados vacíos útiles, *Settings* agrupado por secciones.
10. **Pueden romper compatibilidad**: el cambio de códigos de liberación (datos, plantillas Excel, reportes y pruebas), el renombre de `codigo_sap` (API y plantillas), el alcance de datos (permisos de usuarios actuales), la unificación de documentos (rutas de archivos). Todas se proponen con migración que convierte los datos y con alias para los archivos de carga actuales.

## 3. Propuestas

Formato: **Estado actual → Problema → Cambio → Beneficio → UX/UI → Backend/modelo → Compatibilidad → Prioridad**.

### Etapa 1 — Experiencia (sin migración de datos)

**1.1 Búsqueda global y Ctrl+K**
- Estado: búsqueda inteligente solo dentro de cada lista y select.
- Problema: hay que saber en qué módulo está un número de OC, factura, contenedor o BL.
- Cambio: buscador en la barra superior y paleta Ctrl+K. Un endpoint `/buscar` consulta OC, posiciones (SKU, UPC, estilo, color), productos, facturas, packing lists, embarques (BL/AWB), unidades de carga, proveedores, marcas y documentos, con la misma regla inteligente, respetando permisos y proveedor. La paleta también ofrece acciones (Nueva OC, Importar órdenes, Crear embarque, Abrir proveedor…).
- Beneficio: llegar a cualquier registro en un paso; usuarios expertos trabajan con teclado.
- UX: resultados agrupados por tipo, navegación con flechas, Enter abre.
- Backend: un servicio de lectura, sin tablas nuevas.
- Compatibilidad: ninguna ruptura.
- Prioridad: **Alta**.

**1.2 Home como bandeja de trabajo**
- Estado: ya hay tareas con ruta, KPIs y gráficas del periodo.
- Problema: las gráficas ocupan el primer lugar; no todos los indicadores abren la lista ya filtrada; faltan OCs próximas a XF, PL con diferencias, embarques próximos a salir o con riesgo, documentos faltantes, recepciones próximas.
- Cambio: bloque superior "Necesita atención" con contadores accionables (cada uno abre la lista con el filtro aplicado); tareas debajo; las gráficas bajan a "Resumen del periodo" (plegable).
- UX: primero lo pendiente y lo que bloquea; lo estadístico después.
- Backend: contadores nuevos en `/dashboard` (consultas sobre datos existentes) y filtros por URL en las listas que no los aceptan.
- Compatibilidad: ninguna.
- Prioridad: **Alta**.

**1.3 Bloqueos que explican cómo resolverse**
- Estado: `validar_factura` y `validar_pl` ya devuelven la lista de pendientes.
- Problema: en varias pantallas el botón queda deshabilitado o el error llega como mensaje suelto.
- Cambio: componente "Requisitos para continuar" (✓/✕ con enlace a lo que falta) en Finalizar factura, Finalizar PL, Embarcar y Aprobar producto.
- Backend: cada pendiente lleva `ruta` cuando aplica.
- Compatibilidad: ninguna. Prioridad: **Alta**.

**1.4 Panel lateral de resumen**
- Problema: consultar una OC, factura, embarque o producto desde una tabla obliga a salir y perder filtros, página y orden.
- Cambio: componente `Drawer` reutilizable con resumen, estado, pendientes, actividad reciente y acciones rápidas, más "Abrir detalle completo".
- Backend: endpoints `/resumen` livianos por entidad (o reuso de los detalles existentes).
- Prioridad: **Media-alta**.

**1.5 Columnas, filtros y vistas guardadas**
- Estado: tablas con columnas fijas; algunas ocultan columnas en celular.
- Cambio: selector de columnas por tabla con vistas predefinidas (Operativa / Comercial / Logística / Completa) y vistas propias (filtros + columnas + orden) guardadas en las preferencias del usuario. Filtros frecuentes visibles y "Más filtros" para el resto, con opción de fijar.
- Backend: sin tablas nuevas en esta etapa (JSON de preferencias). Las vistas **compartidas** necesitan tabla (Etapa 2).
- Prioridad: **Media-alta** (Órdenes y Seguimiento primero).

**1.6 Estados vacíos útiles y modales/asistentes**
- Cambio: componente `EstadoVacio` (qué es, qué se necesita, acción principal) en las listas principales. Revisar modales con formularios largos (genérico, OC) y pasarlos a página o asistente por pasos cuando corresponda.
- Prioridad: **Media**.

**1.7 Settings agrupado**
- Cambio: el menú *Settings* pasa a secciones (Organización, Datos maestros, Logística, Comercio y cumplimiento, Datos y sistema), mostrando solo lo permitido.
- Prioridad: **Media** (rápido).

### Etapa 2 — Adaptabilidad (migraciones pequeñas, compatibles)

**2.1 Organización y su configuración**
- Estado: no existe; la configuración de negocio está en variables de entorno y el nombre de la empresa en `Usuario.empresa`.
- Cambio: tabla `organizacion` (una por ahora) con nombre, logo, idioma, zona horaria, formatos, moneda base, sistema de unidades, país principal, terminología, numeraciones, módulos activos y reglas predeterminadas (las que hoy son variables de entorno, que quedan como valor inicial). Pantalla *Settings → Organization*. Las tablas de configuración ganan `organizacion_id` progresivamente (empezando por las nuevas).
- Beneficio: base para varias empresas sin mezclar datos ni reglas.
- Compatibilidad: migración crea la organización con los valores actuales; nada cambia de comportamiento.
- Prioridad: **Alta** (es la base de 2.2–2.5).

**2.2 Estados universales y mapeo de códigos externos**
- Estado: `liberacion_logistica` guarda `300/301/304`; `liberacion_comercial` guarda `C/P`.
- Cambio: estado interno `PENDING | RELEASED | RELEASED_WITH_CHANGES | BLOCKED` y tabla `mapeo_codigo_externo` (sistema, dominio, código externo → valor interno). SAP queda como un mapeo sembrado (`300 → RELEASED`, `301 → RELEASED_WITH_CHANGES`, `304 → PENDING`). Mismo patrón para cualquier código de ERP.
- Compatibilidad: migración convierte los valores; el importador sigue aceptando `300/301/304` vía mapeo. Riesgo: reportes y pruebas que leen el código; se actualizan.
- Prioridad: **Alta**.

**2.3 Terminología configurable**
- Cambio: términos visibles (Purchase Order, Legal entity, Facility, Storage location, Item, Shipment…) se resuelven por organización y se aplican sobre el mecanismo de traducción existente. Internamente: `Sociedad = Legal entity`, `Centro = Facility`, `Almacén = Storage location`; se quitan las referencias a SAP de modelos y textos; `codigo_sap` se presenta como "Item code" (columna renombrada con alias en API y plantillas).
- Prioridad: **Media-alta**.

**2.4 Rol separado del alcance de datos**
- Estado: `Rol.tipo` (`admin | interno | proveedor`) decide permisos de fábrica **y** qué datos se ven.
- Cambio: `Rol.alcance` (`ORGANIZATION | SUPPLIER | LEGAL_ENTITY | COUNTRY | BRAND`) y valores del alcance por usuario; `proveedor_filtro` y `asegurar_proveedor` pasan a un único filtro de alcance validado en el servidor.
- Compatibilidad: migración: `admin/interno → ORGANIZATION`, `proveedor → SUPPLIER = su proveedor`. Comportamiento idéntico.
- Prioridad: **Media-alta**.

**2.5 Módulos activables**
- Cambio: lista de módulos activos en la organización; un módulo apagado no aparece en menús, Home ni búsqueda, y sus rutas devuelven 404 en el servidor.
- Prioridad: **Media**.

**2.6 Documento universal**
- Estado: `Archivo` (facturas) y `ProductoDocumento` (productos) separados.
- Cambio: tabla `documento` (entidad, id, tipo configurable, archivo, emisor, fecha, datos extraídos) y tipos configurables (Commercial Invoice, Packing List, B/L, AWB, Certificate of Origin, Inspection, Photos, Other). Componente único de adjuntos por entidad. Los pasos del flujo podrán exigir tipos.
- Compatibilidad: migración copia los registros existentes sin mover archivos.
- Prioridad: **Media**.

**2.7 Actividad transversal**
- Estado: `Historial` registra mucho, pero solo la factura lo muestra.
- Cambio: añadir `origen` (usuario, importación, integración, automatización) y antes/después estructurado; endpoint `/actividad/{entidad}/{id}` y pestaña *Actividad* en OC, factura, PL, producto, embarque y proveedor.
- Prioridad: **Media**.

### Etapa 3 — Modelo funcional

**3.1 Política de empaque separada**
- Estado: el tipo de caja decide mezcla de productos y tallas; el grupo de artículos tiene categoría fija.
- Cambio: entidad `politica_empaque` (mezclar SKU, mezclar tallas, fraccionar inner pack, casepack exacto, requiere prepack, lote, serial, vencimiento) asignable a grupo de artículos, proveedor o artículo. `TipoEmpaque` queda con lo físico (tara, dimensiones, capacidades, qué contiene, si cuenta como bulto). `GrupoArticulo.categoria` pasa a texto libre/configurable.
- Compatibilidad: migración crea políticas a partir de los indicadores actuales de cada tipo de empaque. Prioridad: **Media**.

**3.2 Importador universal con mapeo**
- Estado: OC con vista previa y alias fijos; artículos y catálogos con plantilla rígida.
- Cambio: subir → detectar columnas → mapear → validar → vista previa (válidas, advertencias, errores, nuevas, a actualizar, duplicados, campos desconocidos) → importar; perfiles de mapeo guardados (p. ej. "SAP Export – Empresa ABC"). Se reutiliza la vista previa existente.
- Prioridad: **Media-alta** (alto impacto al incorporar empresas nuevas).

**3.3 Campos personalizados**
- Cambio: definición por organización (tipo, entidad, obligatorio, visible, editable, editable por proveedor, filtrable, en Excel, en PDF) y valores en una columna JSON por entidad. Solo la arquitectura y la pantalla de definición; sin llenar el sistema de campos.
- Prioridad: **Media-baja**.

**3.4 Workflow configurable (sencillo)**
- Cambio: pasos por organización (nombre, orden, obligatorio, responsable/permiso, condiciones de inicio y fin expresadas con el validador de condiciones existente, documentos requeridos, SLA ligado a un paso de lead time). El flujo actual queda como predeterminado.
- Prioridad: **Media-baja** (depende de 2.1, 2.6 y 1.3).

**3.5 Automatizaciones Evento → Condición → Acción**
- Cambio: tabla de reglas con eventos emitidos por los servicios (cambio de ETA, PL finalizado, XF a N días), condiciones con el mismo formato `{campo, operador, valor}` y acciones iniciales (crear alerta, marcar riesgo, notificar). Las alertas actuales se generan desde ahí.
- Prioridad: **Baja** (base extensible).

**3.6 Esquema arancelario**
- Cambio: entidad `esquema_arancelario` (SAC hoy; HTSUS, CN/TARIC, TIGIE a futuro) con los países que lo usan; `PaisArancel.modelo_arancel` apunta a ella; los textos dejan de decir "SAC" donde se refieren al esquema; `PAIS_BASE_CLASIF` pasa a la organización.
- Prioridad: **Baja-media** (el modelo ya es configurable por país).

**3.7 Integraciones**
- Cambio: capa de conectores (Excel/CSV, SFTP, API; ERP a futuro) que solo traduce hacia el modelo interno usando los perfiles de 3.2 y el mapeo de 2.2.
- Prioridad: **Baja** (después de 2.2 y 3.2).

**3.8 Acciones masivas con vista previa**
- Estado: hay selección y aprobación en lote en productos y el carrito de posiciones de OC.
- Cambio: patrón común Seleccionar → Acción → Vista previa del impacto → Confirmar → Resultado, empezando por: cambiar XF/fecha en tienda de posiciones, asignar PL a unidad de carga, aprobar/devolver productos, resolver alertas.
- Prioridad: **Media**.

## 4. Orden de implementación

| Etapa | Contenido | Migración |
|---|---|---|
| 1a | Búsqueda global + Ctrl+K | No |
| 1b | Home "Necesita atención" con accesos filtrados | No |
| 1c | Requisitos para continuar (factura, PL, embarque, producto) y estados vacíos | No |
| 1d | Panel lateral de resumen; columnas y vistas guardadas (Órdenes, Seguimiento); Settings agrupado | No |
| 2a | Organización + configuración (variables de entorno → organización) + módulos activos | Sí, compatible |
| 2b | Estados universales + mapeo de códigos externos; terminología; quitar SAP del modelo | Sí, con conversión |
| 2c | Rol vs alcance de datos | Sí, compatible |
| 2d | Documento universal y actividad transversal | Sí, copia |
| 3 | Política de empaque, importador con mapeo, campos personalizados, workflow, automatizaciones, esquema arancelario, integraciones | Sí |

La Etapa 1 se implementa de inmediato. Las Etapas 2 y 3 cambian el modelo y
se implementan una por una, con migración, pruebas y sin quitar funciones.

## 5. Avance

| Etapa | Estado | Qué quedó |
|---|---|---|
| 1a | Hecha | `/buscar` agrupado por tipo con permisos y proveedor; buscador en la barra y paleta Ctrl+K / ⌘K / «/» con acciones rápidas |
| 1b | Hecha | «Necesita atención» en el Home con accesos ya filtrados; vista «Bloquean facturas» en Productos; resumen estadístico plegado |
| 1c | Hecha | Componente `Requisitos` (finalizar factura con acciones), motivos visibles en embarque y aprobación de producto; componente `EstadoVacio` en facturas, embarques y productos |
| 1d | Hecha | `PanelLateral` con resumen de factura y de embarque; vistas guardadas por usuario en Seguimiento y Órdenes (`/perfil/vistas/{pantalla}`); *Settings* agrupado por secciones |
| Pendiente de la Etapa 1 | — | Selector de columnas (Operativa / Comercial / Logística / Completa) en Órdenes; vistas compartidas (necesitan tabla, Etapa 2) |
| 2 y 3 | Por aprobar | Cambian el modelo de datos; se implementan una por una con migración |

