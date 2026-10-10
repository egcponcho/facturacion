# Informe final: etapa de producto B2B

Rama `claude/bold-lovelace-iwx2wa`. Línea base: commit `c462452` (antes de esta
etapa). El diagnóstico completo de esa línea base está en
[DIAGNOSTICO.md](DIAGNOSTICO.md); este informe resume qué se encontró, qué se
cambió, cómo se verificó y en qué estado queda el sistema frente a la meta de
producción.

## 1. Resumen

El sistema pasó de una instalación por empresa, con flujos de OC implícitos,
tablas hechas a mano en cada pantalla y tres reportes fijos, a un producto
multiempresa con:

- aislamiento de datos por organización (filtro en la capa de datos y RLS en
  PostgreSQL);
- un flujo de OC con estados, aprobación por reglas y asistente;
- datos maestros con gobierno;
- un sistema de diseño;
- tablas configurables por persona;
- tableros con indicadores que explican su fórmula;
- un generador de reportes;
- una API documentada.

La suite de pruebas pasó de 423 a 485 pruebas y corre también en PostgreSQL.
Se agregó un recorrido de humo en el navegador que se puede reproducir desde
el repositorio.

**Veredicto honesto:** listo para un **piloto controlado** (una o pocas
organizaciones, volúmenes de cientos de OCs al mes, integración con el ERP por
archivos). **No** está listo para producción a escala ni para varias empresas
con integración automática. Faltan:

- integración continua;
- tokens de integración;
- paginar en el servidor algunas listas que crecen;
- corregir los indicadores del inicio (moneda y alcance);
- deudas del modelo de datos.

La sección 6 las ordena por prioridad.

## 2. Diagnóstico original (resumen)

| Área | Lo que se encontró en `c462452` |
|---|---|
| Arquitectura | Una sola empresa por instalación. Sin máquina de estados (transiciones con `if` repartidos). API sin documentar (47 docstrings en 261 rutas) y publicada solo en la demostración. |
| Datos maestros | `Articulo` y `Producto` duplicados. Códigos como texto libre en OCs, facturas y embarques. Dos maestros de país. Formularios planos. Gobierno débil: un solo permiso, borrado físico, sin historial, proveedores editables en dos lugares. Índices faltantes. |
| Flujos de OC y logística | La OC sin estado propio ni aprobación. Formulario único sin borradores ni detalle. Recepción duplicada entre el hito y las líneas. Asignación «tentativa» muerta. |
| Interfaz | Sistema de diseño parcial (208 estilos en línea, variables sin definir). Tablas hechas a mano sin columnas configurables ni paginación en todas partes. Selectores que descargan todo. `window.confirm`. Cuatro asistentes sueltos. Tableros solo en el inicio y en Seguimiento. Tres reportes fijos. |
| Seguridad | Tres hallazgos altos: sin permiso de lectura de facturas, el arancel fuera del filtro de datos visibles y el inicio daba 403. Medios: tipos de archivo, fórmulas en Excel, alcance de alertas y búsqueda, bitácora incompleta. Bajos: hash, límites, enumeración, purga de tablas técnicas, comando de demostración. |
| Indicadores | Mezcla o descarte de monedas. Alcance incompleto. Fechas que se mueven con ediciones. Unidades mezcladas. Ningún indicador declaraba su fórmula. |
| Rendimiento | Listas sin paginar y consultas N+1 en seguimiento, el tablero y los embarques. |
| Pruebas | Faltaban pruebas de rechazo por rol, de tablero con roles propios y de tipos de archivo. Todo corre con la demostración. |
| Demostración | La auditoría de integridad leía datos de la demostración también en producción. |

## 3. Lo que se hizo

| Etapa | Commit | Qué cambió |
|---|---|---|
| S0 Diagnóstico | `ecd5631` | `docs/DIAGNOSTICO.md` y `docs/FLUJOS.md`: estado de partida y flujos de negocio objetivo. |
| PostgreSQL | `c1c36a5` | Migraciones, motor de clasificación y carga oficial compatibles con PostgreSQL. La suite corre en las dos bases. |
| S1 Seguridad | `4813a61` | Permiso `factura.ver`. Arancel y clasificación filtrados por datos visibles. Archivos validados por su contenido y por partes, con control de bombas ZIP. Excel sin fórmulas. Alcance en alertas y búsqueda. Bitácora completa con visor. PBKDF2 a 600 000. Enumeración cerrada. Purga periódica. Demostración protegida. |
| S2 Multiempresa | `dade675` | `organizacion_id` en 48 tablas, filtro del ORM, RLS en PostgreSQL y módulo de plataforma (crear, suspender, entrar a dar soporte). |
| S3 Flujo de OC | `4910b1b`, `d05daf8`, `25cb948` | Estados de la OC con máquina de estados y aprobación por reglas (monto, moneda, sociedad, cuatro ojos). Asistente por pasos con borradores y validación en línea. Vista de detalle con historial y bandeja de aprobación. Cancelar, cerrar y reabrir. Recepción unida al embarque, con alerta de diferencias. Fuera la asignación tentativa. |
| S4 Datos maestros | `328cffc` | Un solo lugar por maestro. Responsables por catálogo, obligatorios configurables e historial por registro. No se borra lo que usan los documentos. La carga masiva solo actualiza con permiso de editar. Índices. |
| S5 Sistema de diseño | `b49dfc4` | Tokens de espaciado y tipografía. Controles únicos. Confirmación propia en lugar de `window.confirm`. Paneles laterales para procesos largos. Capas (Escape cierra la de arriba). `docs/DISENO.md`. |
| S6 Tablas | `e305013` | `TablaDatos`: columnas que se muestran, ocultan, reordenan y ensanchan por persona. Tres densidades. Filtro por columna. «Prioridad +» en el celular. Paginación. Maestro-detalle. |
| S7 Tableros | `b224011` | Tablero por módulo (compras, facturación, logística, productos). Cada persona o rol elige y ordena sus indicadores. Cada indicador declara fórmula, período y fuente. |
| S8 Reportes | `08d5e83` | Generador con fuentes controladas por el servidor, operativos y analíticos, vista previa, CSV, Excel y PDF, y reportes guardados y compartidos (tabla `reportes` con RLS). |
| Tablas como las de OC | `c96b2bf` | A pedido: todas las tablas con el aspecto de la tabla de órdenes de compra. Barra de filtros, chips, documento en negrita, «Columnas n/m» y paginación pegada. Usuarios, Roles, Proveedores y Organizaciones pasan a `TablaDatos`. |
| S9 API, rendimiento y pruebas | `f4f712d`, `db70040`, `6140366`, `c947e8c`, `4d2680d` | Etiqueta y resumen en las 295 operaciones, `API_DOCS` y `docs/API.md`. Sin consultas por fila en las listas de OCs y productos, con prueba que lo vigila. CSV sin fórmulas. Recorrido de humo `npm run e2e`. Dependencias de producción sin vulnerabilidades conocidas. |
| Correcciones de la verificación final | `528dac7`, `94d090e`, `64e971c`, `4d2680d` | Ver la sección 5. |

**Cómo se verificó cada etapa:**

- La suite completa en SQLite y en PostgreSQL.
- `ruff`, ESLint y la compilación de la interfaz.
- Un recorrido en el navegador con cada usuario de la demostración. En cada
  formulario se guardó, se volvió a abrir y se confirmó que el dato persistía;
  no se aceptaron prototipos ni datos simulados.

**Estado final verificado:**

- **Servidor:** 485 pruebas. En PostgreSQL pasan las 485; en SQLite pasan 483
  y se saltan 2 que solo aplican a PostgreSQL (el bloqueo de filas y la
  seguridad por fila).
- **Calidad:** `ruff`, ESLint y la compilación sin errores.
- **Navegador:** el recorrido abre 36 a 38 pantallas por usuario con los
  cuatro usuarios, en escritorio y en celular, sin errores.

## 4. Estado frente al diagnóstico

Cada hallazgo de `DIAGNOSTICO.md` se revisó contra el código actual con
evidencia (archivo y línea, prueba o migración). De **59 hallazgos**: **30
resueltos**, **20 parciales**, **8 abiertos** y 1 sin evidencia concluyente
(las tres formas de «modo vista» en formularios).

**Resueltos (lo principal):**

- **Multiempresa:** aislamiento de datos por organización.
- **Seguridad:** los tres hallazgos altos y casi todos los medios y bajos.
- **Flujo de OC:** estado propio, aprobación, recepción y asignación.
- **Datos maestros:** formularios con secciones, historial, proveedores en un
  solo lugar, permiso para actualizar en la carga masiva, índices.
- **Pruebas:** rechazo al leer facturas, tablero con roles propios, tipos de
  archivo.
- **Demostración:** sus datos ya no se leen fuera de ella.
- **API documentada.**

**Parciales y abiertos (lo que queda):**

| Área | Hallazgo | Estado | Lo que falta |
|---|---|---|---|
| Arquitectura | Máquina de estados | Parcial | Existe `core/estados.py` para OC, factura, PL y embarque y se exige en las acciones principales. Siguen asignaciones con literales, los indicadores `puede` armados con `if`, la edición del embarque y los hitos fuera de la máquina, y `finalizar_pl` no la consulta. |
| Datos maestros | Duplicidad `Articulo` / `Producto` | Abierto | Siguen repitiendo estilo, color, marca, grupo, proveedor y unidad, con obligatoriedad distinta. |
| Datos maestros | Copias con largos distintos | Parcial | El color ya no se corta al facturar (`0051`). `pais_origen` sigue con 2 caracteres en OC y producto y 3 en posición y línea de factura (no falla, pero no es uniforme). |
| Datos maestros | Códigos como texto libre | Parcial | La importación y el asistente validan contra los maestros. No hay llaves foráneas. |
| Datos maestros | Condiciones de pago y contactos | Parcial | Las condiciones de pago son una lista de valores en la OC, pero la factura sigue con texto libre. Los contactos de proveedor y transportista siguen dentro de su ficha. |
| Datos maestros | Dos maestros de país | Abierto | `paises` y `paises_arancel`. |
| Datos maestros | Borrado físico | Parcial | Se bloquea si el dato está en uso, pero no hay borrado lógico. |
| Datos maestros | Obligatorios por flujo | Parcial | Configurables en la OC y en cada catálogo. La importación de OCs no los aplica. Factura, PL y embarque siguen fijos. |
| Flujos | Avance de la OC | Parcial | Hay dos cálculos: el del flujo de la OC (con parciales) y el de Seguimiento (sin parciales y sumando unidades distintas). |
| Flujos | Editar una OC aprobada | Parcial | Solo se edita en borrador o rechazada; un cambio a una OC aprobada requiere cancelarla o reabrirla. |
| Interfaz | Sistema de diseño | Parcial | Quedan 101 estilos en línea (eran 208), cuatro variantes de pestañas y seis de chips. |
| Interfaz | Tablas | Parcial | Todas se ven igual. `TablaDatos` está en 5 vistas (7 tablas), pero hay 73 tablas hechas a mano con las mismas clases. No hay desplazamiento virtual. |
| Interfaz | Autocompletado del servidor | Parcial | Solo los artículos del asistente de OC; proveedores, centros y puertos se descargan completos. |
| Interfaz | Modales y asistentes | Parcial | «Nuevo embarque» sigue en una ventana. El asistente común solo lo usa la OC; el de familias y la bienvenida tienen pasos propios. |
| Interfaz | Tableros | Resuelto con matiz | Los paneles de la página de inicio siguen configurándose por rol, no por persona. |
| Seguridad | Límite de intentos | Parcial | Purga las direcciones viejas, pero vive en la memoria de cada proceso: con varios procesos el límite se multiplica. |
| Indicadores | Monedas | Parcial | El inicio descarta las monedas que no son la principal y suma monedas distintas por proveedor. Los tableros nuevos usan la moneda base y lo dicen, sin conversión. |
| Indicadores | Alcance | Parcial | Los tableros nuevos respetan sociedad y transportista. En el inicio, contenedores, «salen» y llegadas no lo hacen (solo cuentan, no muestran datos). |
| Indicadores | Fechas que se mueven | Abierto | «Listas finalizadas» usa `actualizado_en` y «productos clasificados» usa `revisado_en`: no hay fecha de finalización. |
| Indicadores | Unidades mezcladas | Parcial | Seguimiento y el campo «cantidad» del generador suman pares y unidades. |
| Rendimiento | Listas sin paginar | Abierto | `/embarques`, `/usuarios`, `/proveedores`, `/roles` y las notas, regulaciones e impuestos del arancel devuelven todo. Embarques, Usuarios y Roles paginan en el navegador. |
| Rendimiento | Consultas N+1 | Parcial | Las listas principales ya no crecen por fila y una prueba lo vigila. Quedan el inicio (carga todas las facturas con sus líneas), `resumen_unidad` por cada unidad al listar embarques y una consulta por línea en el detalle de seguimiento. |
| Pruebas | Rechazo por rol al reabrir o cancelar y transporte por proveedor | Abierto | No hay pruebas que esperen 403 en esas acciones. |
| Pruebas | Todo corre con la demostración | Abierto | Las pruebas parten de los datos de ejemplo; no hay un juego que arranque de una instalación vacía. |

## 5. Problemas encontrados en la verificación final

**Corregidos:**

- **Las pruebas no aplicaban los filtros escritos en la ruta.** Con httpx 0.28,
  `params` reemplaza la consulta de la URL: muchas pruebas pedían
  `/ordenes?estado=X` y el servidor recibía `/ordenes?idioma=en`. Se corrigió
  el cliente de pruebas y la suite completa sigue en verde con los filtros
  aplicados (`64e971c`).
- **Pruebas que fallaban según la hora.** Un hito a las 08:00 de hoy hacía que
  la recepción fallara entre las 00:00 y las 08:00 UTC (`94d090e`).
- **Falso «cambios sin guardar»** en la ficha de producto cuando el motor
  normalizaba la ficha al abrirla (`528dac7`).
- **Consultas por fila** en las listas de OCs y productos (`db70040`).
- **Inyección de fórmulas en el CSV** del generador (`6140366`).
- **Una línea nacional sin fuente se podía duplicar** al editarla (`6140366`).
- **Facturar una posición con un color de más de 40 caracteres fallaba** en
  PostgreSQL (`4d2680d`, migración 0051).
- **Vulnerabilidad alta en una dependencia de producción** de la interfaz
  (`source-map-js`, `c947e8c`).

**Abiertos (nuevos, no estaban en el diagnóstico):**

- **El generador de reportes** permite sumar `valor` entre monedas y
  `cantidad` entre unidades distintas.
- **Estado «tentativo» muerto:** quedan restos en Seguimiento
  (`seguimiento.py`, `SeguimientoDocumentos.vue`).
- **RLS sin organización fijada:** la política deja pasar todo si la conexión
  no fija la organización. Es así por diseño, para las tareas de la
  instalación; el filtro del ORM sigue activo.
- **Tablas puente sin organización:** `proveedor_marcas`,
  `proveedor_sociedades`, `centro_puertos` y `transportista_sociedades` no
  tienen organización ni RLS. Dependen de que sus dos extremos sí la tengan.
- **Pantalla de ingreso:** muestra la marca de la organización 1.
- **Dos vulnerabilidades moderadas** en dependencias de desarrollo
  (`eslint-plugin-vue`); corregirlas pide un cambio de versión mayor.

## 6. Evaluación frente a la meta de producción

| Dimensión | Estado | Comentario |
|---|---|---|
| Funcionalidad de los flujos | Buena | OC → factura → lista de empaque → embarque → recepción funciona de punta a punta y se verificó en el navegador. Cada formulario guarda y recupera sus datos. |
| Seguridad | Buena | Permisos por pantalla, acción y dato; aislamiento por organización; archivos validados; bitácora. Falta el límite de intentos compartido entre procesos. |
| Multiempresa | Buena con reservas | Aislamiento probado en las dos bases. Quedan las tablas puente y la marca de la pantalla de ingreso. |
| Datos | Aceptable | Gobierno y validación en la entrada. Deuda de modelo: artículo y producto duplicados, códigos sin llave foránea, dos maestros de país. |
| Escala | Insuficiente para volúmenes grandes | Las listas principales paginan en el servidor y no hacen consultas por fila. Embarques, usuarios, roles y listas del arancel devuelven todo, y el inicio carga todas las facturas. Bien hasta miles de registros; no probado con cientos de miles. |
| Indicadores | Aceptable en los tableros; débil en el inicio | Los tableros declaran fórmula y fuente. El inicio descarta monedas e ignora parte del alcance. |
| Interfaz | Buena | Sistema de diseño, tablas como las de OC en todas las pantallas, celular y modo oscuro revisados. Queda deuda de estilos en línea y variantes. |
| Pruebas | Buena en el servidor; básica en la interfaz | 485 pruebas en dos bases, más las de documentación de la API y de rendimiento. En la interfaz solo hay un recorrido de humo (navegación, sin enviar formularios); no hay pruebas unitarias de componentes. |
| Operación | Insuficiente | No hay integración continua: las pruebas, el lint y el recorrido se corren a mano. Hay guía de producción (`PRODUCCION.md`), pero no monitoreo, métricas ni alertas de operación. |
| Integración | Insuficiente | La API está documentada, pero no hay tokens de integración de larga vida para un ERP: la integración es por archivos o con la sesión de un usuario. |

**Qué falta, en orden:**

1. **Integración continua** que corra `ruff`, la suite en SQLite y en
   PostgreSQL, ESLint, la compilación y `npm run e2e` en cada cambio.
2. **Indicadores del inicio:** moneda (agrupar o convertir en lugar de
   descartar) y alcance por sociedad y transportista.
3. **Paginación en el servidor** de embarques, usuarios, roles y listas del
   arancel, y el inicio sin cargar todas las facturas.
4. **Tokens de integración** con permisos acotados para el ERP.
5. **Límite de intentos compartido** (base o Redis) para varios procesos.
6. **Pruebas de rechazo por rol** en reabrir y cancelar y en transporte por
   proveedor, y pruebas de interfaz que envíen los formularios clave.
7. **Deuda de modelo:** unificar artículo y producto, llaves foráneas para los
   códigos, un maestro de país, fecha de finalización de la lista de empaque.
8. **Deuda de interfaz:** estilos en línea, variantes de pestañas y chips, el
   asistente común en los demás asistentes y el autocompletado del servidor en
   proveedores, centros y puertos.

## 7. Archivos creados, modificados y eliminados

Diferencia entre `c462452` y el final de esta etapa (`git diff --name-status
c462452..HEAD`), agrupada por área.

En total, 208 archivos: 53 creados (incluido este informe), 154 modificados y 1 eliminado
(`OrdenFormulario.vue`, reemplazado por el asistente de la OC).

### Creados (53)

**Servidor (backend)** (17)

- `backend/app/core/estados.py`
- `backend/app/core/organizacion.py`
- `backend/app/instalacion/base_organizacion.py`
- `backend/app/instalacion/mantenimiento.py`
- `backend/app/modulos/compras/api_flujo.py`
- `backend/app/modulos/compras/flujo_oc.py`
- `backend/app/modulos/comun/auditoria.py`
- `backend/app/modulos/maestros/gobierno.py`
- `backend/app/modulos/plataforma/__init__.py`
- `backend/app/modulos/plataforma/api.py`
- `backend/app/modulos/plataforma/organizaciones.py`
- `backend/app/modulos/reportes/__init__.py`
- `backend/app/modulos/reportes/api.py`
- `backend/app/modulos/reportes/fuentes.py`
- `backend/app/modulos/reportes/generador.py`
- `backend/app/modulos/reportes/guardados.py`
- `backend/app/modulos/seguimiento/indicadores.py`

**Migraciones (backend/alembic)** (6)

- `backend/alembic/versions/0046_indices_y_permiso_factura_ver.py`
- `backend/alembic/versions/0047_multiempresa.py`
- `backend/alembic/versions/0048_flujo_oc.py`
- `backend/alembic/versions/0049_sin_asignacion_tentativa.py`
- `backend/alembic/versions/0050_reportes_guardados.py`
- `backend/alembic/versions/0051_color_de_linea_de_factura.py`

**Pruebas del servidor (backend/tests)** (10)

- `backend/tests/test_api_docs.py`
- `backend/tests/test_copias_de_lineas.py`
- `backend/tests/test_endurecimiento.py`
- `backend/tests/test_flujo_oc.py`
- `backend/tests/test_gobierno_maestros.py`
- `backend/tests/test_indicadores.py`
- `backend/tests/test_organizaciones.py`
- `backend/tests/test_recepcion.py`
- `backend/tests/test_rendimiento.py`
- `backend/tests/test_reportes.py`

**Interfaz (frontend)** (12)

- `frontend/src/componentes/Asistente.vue`
- `frontend/src/componentes/Confirmacion.vue`
- `frontend/src/componentes/TablaDatos.vue`
- `frontend/src/modulos/acceso/componentes/PanelBitacora.vue`
- `frontend/src/modulos/compras/vistas/OrdenAsistenteView.vue`
- `frontend/src/modulos/compras/vistas/OrdenView.vue`
- `frontend/src/modulos/plataforma/vistas/OrganizacionesView.vue`
- `frontend/src/modulos/seguimiento/vistas/ReportesView.vue`
- `frontend/src/modulos/seguimiento/vistas/TableroView.vue`
- `frontend/src/nucleo/capas.js`
- `frontend/src/nucleo/estados.js`
- `frontend/src/stores/confirmar.js`

**Pruebas de la interfaz (frontend/e2e)** (1)

- `frontend/e2e/recorrido.mjs`

**Documentación (docs)** (5)

- `docs/API.md`
- `docs/DIAGNOSTICO.md`
- `docs/DISENO.md`
- `docs/FLUJOS.md`
- `docs/INFORME.md`

**Raíz del repositorio** (2)

- `ops/respaldo.sh`
- `ops/restaurar.sh`

### Modificados (154)

**Servidor (backend)** (69)

- `backend/.env.example`
- `backend/app/core/archivos.py`
- `backend/app/core/config.py`
- `backend/app/core/empresa.py`
- `backend/app/core/listas.py`
- `backend/app/core/seguridad.py`
- `backend/app/esquemas/__init__.py`
- `backend/app/esquemas/acceso.py`
- `backend/app/esquemas/transporte.py`
- `backend/app/instalacion/demo.py`
- `backend/app/main.py`
- `backend/app/modelos/__init__.py`
- `backend/app/modelos/acceso.py`
- `backend/app/modelos/clasificacion.py`
- `backend/app/modelos/compras.py`
- `backend/app/modelos/empaque.py`
- `backend/app/modelos/empresa.py`
- `backend/app/modelos/facturacion.py`
- `backend/app/modelos/maestros.py`
- `backend/app/modelos/productos.py`
- `backend/app/modelos/sistema.py`
- `backend/app/modelos/transporte.py`
- `backend/app/modulos/acceso/api.py`
- `backend/app/modulos/acceso/autenticacion.py`
- `backend/app/modulos/acceso/limites.py`
- `backend/app/modulos/acceso/permisos.py`
- `backend/app/modulos/acceso/preferencias.py`
- `backend/app/modulos/acceso/proveedores.py`
- `backend/app/modulos/acceso/roles.py`
- `backend/app/modulos/acceso/usuarios.py`
- `backend/app/modulos/acceso/visibilidad.py`
- `backend/app/modulos/clasificacion/api.py`
- `backend/app/modulos/clasificacion/api_conocimiento.py`
- `backend/app/modulos/clasificacion/aranceles.py`
- `backend/app/modulos/clasificacion/integridad.py`
- `backend/app/modulos/clasificacion/lotes.py`
- `backend/app/modulos/clasificacion/motor_clasificacion.py`
- `backend/app/modulos/clasificacion/oficial.py`
- `backend/app/modulos/compras/api.py`
- `backend/app/modulos/compras/ordenes.py`
- `backend/app/modulos/comun/api.py`
- `backend/app/modulos/documentos/exportar.py`
- `backend/app/modulos/documentos/plantillas.py`
- `backend/app/modulos/empaque/api.py`
- `backend/app/modulos/empaque/api_plantillas.py`
- `backend/app/modulos/empaque/packing.py`
- `backend/app/modulos/empaque/plantillas_caja.py`
- `backend/app/modulos/empresa/api.py`
- `backend/app/modulos/empresa/organizacion.py`
- `backend/app/modulos/facturacion/api.py`
- `backend/app/modulos/facturacion/estados.py`
- `backend/app/modulos/facturacion/facturas.py`
- `backend/app/modulos/maestros/api.py`
- `backend/app/modulos/maestros/cargas.py`
- `backend/app/modulos/maestros/catalogos.py`
- `backend/app/modulos/maestros/genericos.py`
- `backend/app/modulos/productos/api.py`
- `backend/app/modulos/productos/api_flujo.py`
- `backend/app/modulos/productos/productos.py`
- `backend/app/modulos/seguimiento/alertas.py`
- `backend/app/modulos/seguimiento/api.py`
- `backend/app/modulos/seguimiento/buscar.py`
- `backend/app/modulos/seguimiento/dashboard.py`
- `backend/app/modulos/transporte/api.py`
- `backend/app/modulos/transporte/leadtimes.py`
- `backend/app/modulos/transporte/transporte.py`
- `backend/app/web/dependencias.py`
- `backend/app/web/rutas.py`
- `backend/scripts/i18n_extraer.py`

**Migraciones (backend/alembic)** (2)

- `backend/alembic/versions/0008_hs6_producto_y_clasificacion_por_pais.py`
- `backend/alembic/versions/0010_capa_custom.py`

**Pruebas del servidor (backend/tests)** (8)

- `backend/tests/conftest.py`
- `backend/tests/test_capas_arancel.py`
- `backend/tests/test_edicion.py`
- `backend/tests/test_empresa.py`
- `backend/tests/test_flujo.py`
- `backend/tests/test_hitos.py`
- `backend/tests/test_marca.py`
- `backend/tests/test_perfil.py`

**Interfaz (frontend)** (66)

- `frontend/package-lock.json`
- `frontend/package.json`
- `frontend/src/App.vue`
- `frontend/src/componentes/AvisoEdicion.vue`
- `frontend/src/componentes/BusquedaGlobal.vue`
- `frontend/src/componentes/CargaMasiva.vue`
- `frontend/src/componentes/EstadoBadge.vue`
- `frontend/src/componentes/EstadoTiempo.vue`
- `frontend/src/componentes/ExplosionPrepack.vue`
- `frontend/src/componentes/Modal.vue`
- `frontend/src/componentes/Paginacion.vue`
- `frontend/src/componentes/PanelLateral.vue`
- `frontend/src/componentes/SelectBusqueda.vue`
- `frontend/src/componentes/SelectorColumnas.vue`
- `frontend/src/modulos/acceso/componentes/ClaveSegura.vue`
- `frontend/src/modulos/acceso/vistas/AdminView.vue`
- `frontend/src/modulos/acceso/vistas/BienvenidaView.vue`
- `frontend/src/modulos/acceso/vistas/PerfilView.vue`
- `frontend/src/modulos/clasificacion/componentes/AsistenteFamilia.vue`
- `frontend/src/modulos/clasificacion/componentes/EditorJson.vue`
- `frontend/src/modulos/clasificacion/componentes/PanelAtributos.vue`
- `frontend/src/modulos/clasificacion/componentes/PanelBusqueda.vue`
- `frontend/src/modulos/clasificacion/componentes/PanelConocimiento.vue`
- `frontend/src/modulos/clasificacion/componentes/PanelDominios.vue`
- `frontend/src/modulos/clasificacion/componentes/PanelFuentes.vue`
- `frontend/src/modulos/clasificacion/componentes/PanelImportacion.vue`
- `frontend/src/modulos/clasificacion/componentes/PanelImpuestos.vue`
- `frontend/src/modulos/clasificacion/componentes/PanelMateriales.vue`
- `frontend/src/modulos/clasificacion/componentes/PanelReglas.vue`
- `frontend/src/modulos/clasificacion/componentes/PanelRegulaciones.vue`
- `frontend/src/modulos/clasificacion/componentes/PanelTraducciones.vue`
- `frontend/src/modulos/clasificacion/vistas/ArancelesView.vue`
- `frontend/src/modulos/clasificacion/vistas/FamiliasView.vue`
- `frontend/src/modulos/compras/componentes/PerfilesImportacion.vue`
- `frontend/src/modulos/compras/vistas/ImportarView.vue`
- `frontend/src/modulos/compras/vistas/OrdenesView.vue`
- `frontend/src/modulos/empaque/componentes/ArbolEmpaque.vue`
- `frontend/src/modulos/empaque/componentes/DestinosYUnidades.vue`
- `frontend/src/modulos/empaque/vistas/PackingListView.vue`
- `frontend/src/modulos/empresa/vistas/EmpresaView.vue`
- `frontend/src/modulos/facturacion/vistas/FacturaView.vue`
- `frontend/src/modulos/facturacion/vistas/FacturasView.vue`
- `frontend/src/modulos/inicio/vistas/DashboardView.vue`
- `frontend/src/modulos/maestros/componentes/ArticulosGenericos.vue`
- `frontend/src/modulos/maestros/componentes/EditorReglaLT.vue`
- `frontend/src/modulos/maestros/vistas/MantenimientoView.vue`
- `frontend/src/modulos/productos/componentes/ficha/AcuerdosOrigen.vue`
- `frontend/src/modulos/productos/componentes/ficha/CampoFicha.vue`
- `frontend/src/modulos/productos/componentes/ficha/ComposicionParte.vue`
- `frontend/src/modulos/productos/componentes/ficha/DocumentosTecnicos.vue`
- `frontend/src/modulos/productos/componentes/ficha/FichaTecnica.vue`
- `frontend/src/modulos/productos/vistas/ProductoView.vue`
- `frontend/src/modulos/productos/vistas/ProductosView.vue`
- `frontend/src/modulos/seguimiento/componentes/SeguimientoDocumentos.vue`
- `frontend/src/modulos/seguimiento/componentes/TableroEmbarques.vue`
- `frontend/src/modulos/seguimiento/componentes/TableroLeadTimes.vue`
- `frontend/src/modulos/seguimiento/componentes/TableroOrdenes.vue`
- `frontend/src/modulos/seguimiento/vistas/SeguimientoView.vue`
- `frontend/src/modulos/transporte/componentes/ResumenEmbarque.vue`
- `frontend/src/modulos/transporte/vistas/EmbarqueView.vue`
- `frontend/src/modulos/transporte/vistas/EmbarquesView.vue`
- `frontend/src/modulos/transporte/vistas/LeadTimeView.vue`
- `frontend/src/nucleo/api.js`
- `frontend/src/router.js`
- `frontend/src/stores/sesion.js`
- `frontend/src/styles.css`

**Textos y traducciones** (6)

- `backend/app/i18n/claves.json`
- `backend/app/i18n/es.json`
- `frontend/src/i18n/claves.json`
- `frontend/src/i18n/es.json`
- `frontend/src/i18n/glosario.json`
- `frontend/src/i18n/servidor.json`

**Documentación (docs)** (2)

- `docs/ARQUITECTURA.md`
- `docs/PRODUCCION.md`

**Raíz del repositorio** (1)

- `README.md`

### Eliminados (1)

**Interfaz (frontend)** (1)

- `frontend/src/modulos/compras/componentes/OrdenFormulario.vue`
