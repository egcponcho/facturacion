# Diagnóstico del sistema (antes de la etapa de producto B2B)

Fotografía del repositorio en el commit `c462452`, tomada antes de los
cambios de esta etapa. Sirve de línea base para el informe final. Las rutas
son relativas a `backend/app/` o `frontend/src/`.

Tamaño: servidor ≈ 32 000 líneas de Python en 13 módulos, 85 tablas y 46
migraciones; interfaz ≈ 20 000 líneas en Vue/JS; 40 archivos de pruebas (423
pruebas en verde).

## 1. Arquitectura

**Bien resuelto**
- Capas separadas: `core` (sin dependencias hacia arriba), `web`, `modelos`,
  `esquemas`, `modulos/<dominio>` e `instalacion`. La interfaz replica los
  dominios en `modulos/<dominio>/{vistas,componentes}`.
- Configuración por empresa sin código: reglas, marca, papel, listas de
  valores, terminología, campos propios, módulos activables, roles y permisos,
  alcance de datos por usuario y datos visibles por rol.

**Problemas**
- **Una empresa por instalación.** `organizaciones` tiene una sola fila
  (`ID_EMPRESA = 1`, `modulos/empresa/organizacion.py`). Ninguna tabla tiene
  columna de organización (la migración 0036 la agregó y la 0037 la quitó).
  Para servir a varias empresas hay que desplegar una instalación por empresa.
- No hay máquina de estados: las transiciones de factura, lista de empaque y
  embarque son `if` repartidos (`facturacion/facturas.py`, `empaque/packing.py`,
  `transporte/transporte.py`).
- La documentación de la API se limita a 47 docstrings en 261 rutas, sin
  etiquetas ni resúmenes, y solo se publica en la demostración.

## 2. Datos maestros

| Hallazgo | Detalle |
|---|---|
| Duplicidad artículo / producto | `Articulo` y `Producto` repiten estilo, color, marca, grupo, proveedor y unidad, con obligatoriedad distinta (`modelos/maestros.py:321`, `modelos/productos.py:36`). |
| Copias en las líneas | `PosicionOC` y `FacturaLinea` copian datos del artículo como texto (es correcto como foto del documento, pero con largos distintos: color 60 vs 40, `pais_origen` 2 vs 3). |
| Códigos como texto libre | `ordenes_compra.sociedad/centro/moneda/incoterm/puerto`, `facturas.sociedad/centro`, `embarques.puerto_*`: sin llave foránea ni validación contra el maestro en la importación. |
| Maestros ausentes | Condiciones de pago (`facturas.condiciones` es texto libre), contactos de proveedor y de transportista (están en línea en la ficha). |
| Dos maestros de país | `paises` y `paises_arancel`, unidos solo por el código ISO. |
| Formularios planos | Los 22 catálogos se editan en una sola rejilla sin secciones (`MantenimientoView.vue`); no se separan datos generales, comerciales, logísticos y extras. |
| Gobierno | Un solo juego de permisos para todos los catálogos; borrado físico; sin historial visible por registro; proveedores editables también desde Administración sin historial ni validación del catálogo; la carga masiva actualiza registros con el permiso de crear. |
| Obligatorios por flujo | Solo existe `REQUERIR_DATOS_ADUANA`; el resto está fijo en el código. |
| Índices faltantes | `ordenes_compra.sociedad/fecha/liberada`, `facturas.sociedad/actualizado_en`, `embarques.estado/etd/transportista_id`, `historial(entidad, entidad_id)`, `alertas.resuelta/proveedor_id`, `articulos.proveedor_id`. |

## 3. Flujos de órdenes de compra y logística

- **La OC no tiene estado propio.** Solo las liberaciones del ERP
  (`liberacion_comercial`, `liberacion_logistica`) y un avance derivado al
  vuelo en `seguimiento/seguimiento.py` (SIN_COMERCIAL … RECIBIDA), sin
  «embarcada parcial» ni «recibida parcial».
- **No hay aprobación de OCs** (ni aprobador, ni montos, ni bitácora). Las
  liberaciones vienen del ERP. Solo la ficha técnica tiene aprobación con
  cuatro ojos.
- **Creación manual en un formulario único** (`OrdenFormulario.vue`): valida
  solo al enviar, no guarda borradores, tiene códigos de liberación de SAP
  fijos (`C/P/300/304`) y no permite editar la OC después ni cancelarla o
  cerrarla. No existe una pantalla de detalle de la OC ni su historial.
- **Recepción duplicada.** El evento RECEPCION del embarque y las cantidades
  recibidas por línea (`RecepcionLinea`) no se hablan; se puede registrar la
  recepción antes del arribo y las diferencias no generan nada.
- **Asignación tentativa muerta.** `asignar` siempre confirma e ignora `modo`;
  los textos de reabrir factura y lista de empaque describen un efecto que el
  servidor no aplica.

## 4. Interfaz

- **Sistema de diseño parcial.** Hay tokens de color y modo oscuro, pero no
  hay escala de espaciado, tipografía ni densidad. Hay variables usadas sin
  definir (`--sombra-alta`, `--aviso-claro`, `--mono`, `--peligro`,
  `--fondo`) y 208 estilos en línea. Conviven 6 variantes de pestañas y 4 de
  chips, 15 puntos de quiebre y clases CSS muertas. La clase `.check` rompe
  celdas en Productos y Aranceles.
- **Tablas a mano.** No hay un componente de tabla: cada vista arma su
  `<table>`. No hay filtros por columna, reordenar o redimensionar columnas,
  modos de densidad, desplazamiento virtual ni «prioridad +» en móvil. Solo 3
  tablas permiten elegir columnas. En la carga de un embarque se pierden las
  filas después de la 50 porque no hay paginación.
- **Selectores.** `SelectBusqueda` filtra en el navegador: proveedores,
  artículos, centros y puertos se descargan completos. No hay autocompletado
  del servidor.
- **Filtros.** No hay un componente de barra de filtros. Los chips de filtros
  activos, «Limpiar» y las vistas guardadas existen solo en Órdenes y
  Seguimiento; los estados vacíos con consejos, solo en 3 pantallas.
- **Modales.** Hay procesos largos en modales: empaque automático (1000 px),
  perfiles de importación, editor de roles y nuevo embarque. `window.confirm`
  se usa en 9 lugares, con pies de modal inconsistentes.
- **Asistentes.** No hay un componente: hay 4 implementaciones sueltas de
  pasos.
- **Formularios.** Hay 3 formas de «modo vista» (texto, `fieldset disabled`,
  `disabled` por campo) y dos sistemas de marca de obligatorio.
- **Tableros.** Solo el inicio y Seguimiento tienen tablero; Compras y
  Logística no. Los paneles se configuran por rol, no por usuario, y no se
  pueden ordenar.
- **Reportes.** Hay 3 reportes fijos (OC, embarques, documentos) en PDF o
  Excel. No hay CSV, ni generador, ni reportes guardados. Órdenes, Facturas y
  Embarques no se pueden exportar.

## 5. Seguridad

| Severidad | Hallazgo |
|---|---|
| Alta | No existe permiso de lectura de facturas ni listas de empaque: cualquier rol interno (incluido uno solo de transporte o de catálogos) lee todas las facturas, sus archivos y sus exportaciones. |
| Alta | `/aranceles/*` y `/clasificacion/*` no pasan por el filtro de datos visibles: el proveedor ve impuestos que su rol oculta (`/aranceles/requisitos`). |
| Alta | La página de inicio responde 403 a cualquier rol interno sin `alertas.ver` (`seguimiento/dashboard.py:508`). |
| Media | Archivos de factura de cualquier tipo; fotos y documentos validados solo por el `content_type` del cliente; logo sin validar formato; límite de tamaño solo por `content-length`. |
| Media | Exportaciones a Excel sin neutralizar fórmulas (`=`, `+`, `-`, `@`). |
| Media | Resolver alertas sin revisar el alcance del proveedor; la búsqueda global ignora el alcance por sociedad. |
| Media | Sin bitácora para usuarios, proveedores, borrado de roles, creación manual de OC, resolución de alertas y plantillas de caja; sin visor global de auditoría. |
| Baja | PBKDF2 con 200 000 iteraciones (OWASP recomienda 600 000); límites por IP en memoria sin tope; respuestas distintas para cuenta bloqueada o sin teléfono (enumeración). |
| Baja | La ruta de la SPA compara el prefijo sin separador; `idempotencia`, `sesiones` y `desafios_dos_pasos` crecen sin purga. |
| Baja | `python -m app.instalacion.demo` borra el esquema de cualquier base a la que apunte `DATABASE_URL`. |

## 6. Indicadores y reportes

- «Facturado» y «por facturar» toman solo la moneda principal y descartan las
  demás sin avisar; `por_proveedor` suma montos de monedas distintas.
- Los contenedores, envíos y «salen» del tablero ignoran el alcance por
  sociedad y transportista.
- «Listas finalizadas» usa `actualizado_en`, así que una edición posterior
  mueve el dato de periodo. «Productos clasificados» usa `revisado_en`, que
  cambia con correcciones.
- El avance de seguimiento suma cantidades en unidades distintas.
- Ningún indicador declara su fórmula, periodo o fuente en la interfaz.

## 7. Rendimiento

- Listas sin paginar: `/embarques`, `/usuarios`, `/proveedores`, `/roles`,
  notas, regulaciones, impuestos y conocimiento del arancel.
- Consultas N+1 en seguimiento (una consulta por línea de factura), en el
  tablero (todas las facturas con líneas y listas perezosas) y en
  `resumen_unidad`. No se usa `selectinload` en facturación, empaque,
  transporte ni seguimiento.

## 8. Pruebas

Cubren el flujo de punta a punta, acceso seguro, roles, alcance, visibilidad,
idiomas y el motor de clasificación. Faltan:
- pruebas de rechazo por rol (leer facturas, reabrir, cancelar, transporte
  por proveedor);
- pruebas de tablero con roles personalizados;
- pruebas de tipos de archivo.

Todas corren con la demostración activa.

## 9. Datos de prueba frente a datos reales

El camino de producción no carga la demostración. Hay una fuga: la auditoría
de integridad lee `data/demo/historial_empresa_demo.json` también en
producción (`clasificacion/integridad.py:37`).
