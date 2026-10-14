# Arquitectura

Guía para quien mantiene o extiende el sistema. Para instalarlo vea el
[README](../README.md); para producción, [PRODUCCION.md](PRODUCCION.md); el
motor de clasificación arancelaria tiene su propio documento en
[clasificacion/arquitectura.md](clasificacion/arquitectura.md).

## Principios

- **Varias organizaciones, datos aislados.** Una instalación sirve a varias
  empresas cliente (organizaciones). Cada una tiene sus datos, usuarios,
  roles y configuración (nombre, logo, colores, papel, listas de valores,
  terminología, campos propios, módulos, reglas); el aislamiento lo aplica la
  capa de datos (ver «Organizaciones»). El código no conoce empresas, ERPs ni
  países concretos.
- **El servidor decide.** Permisos, alcance de los datos, validaciones,
  cálculos y el motor de clasificación viven en el servidor; la interfaz solo
  muestra y edita. Lo que un rol no ve se quita de las respuestas antes de
  enviarlas (`RespuestaJSON` en `app/main.py`).
- **Módulos por dominio.** Cada dominio (compras, facturación, empaque,
  transporte…) tiene su paquete en el servidor y su carpeta en la interfaz,
  con la misma división.
- **Inglés como clave de texto.** Todos los textos se escriben en inglés en el
  código y se traducen al español en `es.json` (servidor e interfaz).

## Servidor (`backend/app`)

```
core/          Núcleo transversal. No importa nada de modulos/ ni de web/.
web/           Capa HTTP compartida (usuario de la petición, piezas de rutas).
modelos/       Tablas SQLAlchemy, un archivo por dominio.
esquemas/      Contratos de entrada de la API (pydantic), uno por dominio.
modulos/<d>/   Servicios del dominio + api.py (y api_*.py) con sus rutas.
instalacion/   Migraciones al arrancar, datos incluidos, primer admin, demo.
i18n/          Textos del servidor (claves.json) y su traducción (es.json).
```

Dependencias permitidas: `modulos → web → core`, `modulos → modelos/esquemas`,
y entre módulos solo a través de sus servicios (nunca de su `api.py`).

### Una petición

1. `web/dependencias.usuario_actual` valida la sesión (cookie o token).
2. `usuario_con_preferencias` deja en variables de contexto (`ContextVar`) lo
   que vale para toda la petición: la configuración de la empresa
   (`core/empresa.usar_configuracion`), sus listas de valores
   (`core/listas.usar_listas`), el idioma y las preferencias del usuario.
   Así los servicios consultan `regla(...)`, `configuracion_actual()` o
   `listas.valores(...)` sin recibirlos como argumento.
3. La ruta del módulo exige su permiso (`acceso/permisos.exigir`) y llama al
   servicio. Los errores de negocio se lanzan como `ErrorNegocio(mensaje,
   status, codigo, detalle)` y se responden como `{mensaje, codigo, detalle}`.
4. `RespuestaJSON` quita los datos que el rol no ve (`acceso/visibilidad.py`).

### Organizaciones (multiempresa)

`app/core/organizacion.py` y la migración 0047:

1. **Tablas por organización.** Las 48 tablas de negocio, configuración,
   usuarios y roles heredan `DeOrganizacion` (columna `organizacion_id`). Un
   registro nuevo toma la organización de la sesión; guardar uno de otra
   organización se rechaza.
2. **Filtro automático.** Toda consulta del ORM (listas, `db.get`,
   relaciones, UPDATE/DELETE masivos) se limita a la organización de la
   sesión (`do_orm_execute` + `with_loader_criteria`). Un id ajeno «no existe».
3. **Seguridad por fila en PostgreSQL.** Cada transacción fija
   `app.organizacion_id` y las políticas RLS (forzadas también para el dueño
   de las tablas) rechazan leer o escribir filas de otra organización, aun con
   SQL escrito a mano. Sin el valor fijado (migraciones, arranque, tareas de
   mantenimiento) no limitan.
4. **Únicos por organización.** Los códigos (proveedor, SKU, embarque, rol,
   valores de las listas…) son únicos dentro de cada organización; el correo
   del usuario es único en toda la plataforma porque identifica su
   organización al entrar.
5. **Datos compartidos.** Países, acuerdos comerciales, arancel oficial y
   motor de clasificación no llevan organización. Con más de una organización
   activa solo los cambia quien administra la plataforma
   (`permisos.edita_compartidos`).
6. **Plataforma.** `usuarios.plataforma` crea organizaciones (con sus datos
   de partida: `instalacion/base_organizacion.py`), las suspende y entra a
   cualquiera para dar soporte (`sesiones.organizacion_id`); la interfaz lo
   avisa y todo queda en la bitácora de esa organización. Cada usuario ve
   siempre su propio registro, aunque trabaje en otra organización.

La organización vive en `db.info` (una sesión de base de datos por petición).
Para un proceso fuera de una petición: `organizacion.en_organizacion(id)`;
para consultas de plataforma sobre todas: `organizacion.todas(db)`.

### Mecanismos de configuración

| Mecanismo | Dónde se configura | Código |
|---|---|---|
| Reglas de negocio (tolerancias, plazos, flujos) | Configuración → Empresa → Reglas | `core/empresa.py` (`REGLAS`, `regla()`) |
| Marca, papel y declaraciones de los documentos | Configuración → Empresa | `modulos/empresa/organizacion.py`, `modulos/documentos/` |
| Listas de valores (unidades, monedas, incoterms, modos de transporte, hitos de embarque, tipos…) | Datos maestros → Listas | `core/listas.py` (fábrica y forma), `modulos/maestros/listas.py` |
| Terminología propia | Configuración → Empresa → Terminología | `organizacion._validar_textos`; interfaz `usarTextosPropios`; documentos `idioma_doc.L()` |
| Campos propios por entidad | Configuración → Empresa → Campos propios | `core/campos_propios.py`; columna `extra` (JSON) |
| Módulos activables | Configuración → Empresa → Módulos | `acceso/permisos.MODULOS_ACTIVABLES` |
| Permisos por rol e inicio por rol | Usuarios y accesos → Roles | `acceso/permisos.py`, `acceso/roles.py` |
| Alcance de datos por usuario (proveedores, sociedades, transportistas) | Usuarios y accesos → Usuario | `acceso/permisos.proveedor_filtro`, `sociedad_filtro`, `transportistas_de` |
| Datos visibles por rol | Usuarios y accesos → Roles | `acceso/visibilidad.py` |
| Perfiles de importación de OCs | Órdenes de compra → Importar | `compras/perfiles.py` |
| Reglas de aprobación y datos obligatorios de la OC | Configuración → Empresa | `empresa/organizacion.py` (`aprobaciones_oc`, `obligatorios`), `compras/flujo_oc.py` |
| Responsables y datos obligatorios de cada catálogo | Datos maestros → (catálogo) → Gobierno | `maestros/gobierno.py`; configuración `maestros` de la organización |
| Indicadores de cada módulo (cuáles y en qué orden, por persona o por rol) | Indicadores → Elegir indicadores | `seguimiento/indicadores.py` (`CATALOGO`); preferencia `indicadores` de la persona y `indicadores_rol` de la organización |
| Columnas, anchos y densidad de cada tabla | La propia tabla (menú Columnas) | `componentes/TablaDatos.vue`; preferencia `tablas` de la persona |
| Reportes guardados (operativos y analíticos, propios o compartidos) | Reportes | `reportes/guardados.py`; tabla `reportes` |

### Indicadores

Cada módulo tiene su tablero (Indicadores). Los indicadores se declaran en
`seguimiento/indicadores.py` con su fórmula, su fuente, si son una foto de hoy
o cuentan lo ocurrido en el período elegido (7, 30, 90 o 365 días, comparado
con el período anterior), su formato y el permiso que piden. Se calculan en el
servidor con el alcance de datos del usuario: un proveedor ve sus propios
números. Agregar un indicador es agregar una entrada al catálogo con su
función de cálculo y una prueba.

### Reportes

Reportes separa dos usos: los **operativos** listan registros para el trabajo
del día y los **analíticos** totalizan por grupo (conteo, suma, promedio,
mínimo y máximo). El usuario arma el reporte en la propia pantalla, pero sólo
con lo que el servidor ofrece:

- `reportes/fuentes.py` declara cada fuente (órdenes, líneas de OC, facturas,
  embarques, productos) con sus campos, su tipo, los operadores que admite y
  el grupo de datos visibles al que pertenece. Un campo de un grupo oculto
  para el rol (por ejemplo, precios) no se ofrece ni se acepta.
- `reportes/generador.py` valida la definición, la convierte en una consulta
  con el alcance de datos del usuario (proveedores, sociedades y la
  organización) y la exporta a CSV, Excel o PDF. La vista previa trae hasta
  500 filas y una exportación hasta 10 000.
- `reportes/guardados.py` guarda la definición (nunca resultados) en la tabla
  `reportes`, con RLS. Cada persona guarda los suyos; el equipo interno puede
  compartirlos con la organización. Al abrir un reporte compartido se vuelve a
  ejecutar con el alcance de quien lo abre.

Agregar una fuente o un campo es agregar su entrada en `FUENTES`; no hace
falta tocar la interfaz.

### Datos maestros y su gobierno

Cada dato maestro se mantiene en un solo lugar: Datos maestros
(`maestros/catalogos.py`). El catálogo se describe una vez (campos, tipos,
obligatorios, sección del formulario) y de esa descripción salen la tabla, los
filtros, el formulario, la carga desde Excel y la exportación. Otras pantallas
solo los consultan (p. ej. Usuarios y accesos muestra los proveedores para dar
acceso, pero no los edita).

- **Responsables:** cada catálogo puede tener los roles que lo mantienen. Sin
  responsables, lo mantiene cualquier rol con los permisos `catalogos.*`. El
  servidor lo exige al crear, editar, eliminar y cargar (`gobierno.exigir_responsable`);
  la pantalla recibe `puede` por catálogo y muestra solo lo permitido.
- **Obligatorios de la empresa:** además de los que el sistema exige, la
  administración elige qué datos de cada catálogo son obligatorios; valen en el
  formulario y en la carga masiva (`catalogos._limpiar`).
- **Historial por registro:** cada alta y cambio queda en `historial` (quién,
  cuándo, antes → después) y se ve en la ficha de solo lectura del registro.
- **Borrado:** un registro que otros registros usan por llave foránea, o cuyo
  código guardan los documentos (`gobierno.USOS_CODIGO`, `USOS_LISTA`), no se
  borra: se desactiva.
- **Cargas:** crean con `catalogos.crear`; una fila que cambia un registro que
  ya existe requiere `catalogos.editar`.
- **Compartidos:** países y acuerdos comerciales son comunes a todas las
  organizaciones; solo la plataforma los cambia.

### Base de datos y migraciones

- Las migraciones están en `backend/alembic/versions` (numeradas) y se aplican
  solas al arrancar (`instalacion/migraciones.py`). Todo cambio de modelo
  lleva su migración; `alembic check` debe responder sin cambios.
- SQLite para desarrollo y pruebas; PostgreSQL en producción (las pruebas de
  concurrencia corren con `TEST_DATABASE_URL`). Las migraciones tienen ida y
  vuelta (`downgrade`) y `tests/test_oficial.py` las recorre completas.

### Modelo de datos: reglas de integridad

- **Dinero y tasas exactos:** `Precio` NUMERIC(18,6), `Importe` (18,4) y
  `Tasa` (12,6) (`modelos/base.py`); las cuentas se hacen en Decimal con
  `core/dinero.py` (redondeo por moneda). El DAI (%) también es numérico; lo
  que el arancel no da como número («Parte II») va en `nodos_arancel.dai_nota`.
- **Numeración:** `series_documentales` + `contadores_serie` con contador
  bloqueado (`core/numeracion.py`): sin huecos ni duplicados en concurrencia.
- **Reglas en la base:** los CHECK viven en `modelos/restricciones.py`; las
  llaves por código (`(organizacion_id, codigo)` → catálogo, ISO → `paises`)
  en `modelos/referencias.py` (`REFERENCIAS`), y la coherencia de
  organización entre padre e hijo (`COHERENCIA`, llaves `…_org`, solo en la
  base). `tests/test_integridad_bd.py` verifica que existan.
- **Contacto normalizado:** terceros, `direcciones` y `medios_contacto` (un
  correo o teléfono por fila); proveedores y transportistas son extensiones
  de su tercero.
- **Núcleo de facturación genérico** (`modelos/comercial.py`): tipos de
  documento, series, impuestos, condiciones de pago con cuotas, documentos
  con líneas e impuestos por línea, vencimientos, relaciones (NC/ND), pagos y
  aplicaciones. Una factura de proveedor finalizada se registra como
  documento recibido.
- **Configuración en tablas, no en JSON:** campos propios
  (`definiciones_campo`, con índice opcional en PostgreSQL sobre
  `extra->>'clave'`), estados por documento (`estados_documento`: etiqueta,
  color y orden; los códigos son fijos en `core/estados.py`), reglas de
  aprobación de OC, alcance de usuarios (tablas de asociación).
- **Taxonomía:** línea comercial (`categorias_articulo.dominio`) → dominio de
  clasificación → categoría de producto. `paises_arancel` es extensión 1:1 del
  país ISO.
- **Producto:** la ficha y el resultado aprobado en `productos`; el trabajo de
  clasificar en `clasificaciones_producto` (1:1). `Producto` expone esos datos
  como propiedades híbridas.
- **Variantes y kits:** talla y color son columnas del artículo; los demás
  atributos (`atributos_variante`) guardan su valor en `articulo_atributos`.
  Un prepack es CURVA (tallas de un estilo-color) o KIT (cualquier artículo).
- **Archivos fuera de la base:** `adjuntos` guarda nombre, clave, tipo,
  tamaño y SHA-256; el contenido vive en `UPLOAD_DIR` (`core/almacen.py`),
  también el de los paquetes oficiales y las previas de importación.
- **Listas estructuradas:** pasos de lead time y tallas de una escala son
  JSON; los países de un acuerdo comercial, tablas de asociación con `paises`.
  Los sinónimos de búsqueda (`sinonimos_busqueda`, texto oficial) y de
  material (`clasif_sinonimos`, a un material) siguen separados: significan
  cosas distintas.
- **Tablas que crecen:** la limpieza horaria (`instalacion/mantenimiento.py`)
  borra por fecha indexada sesiones, desafíos, idempotencia y permisos de
  edición; el historial se conserva salvo que `HISTORIAL_ANOS` fije una
  retención. Con mucho volumen en PostgreSQL, el historial se puede
  particionar por rango de `fecha` (la tabla no tiene llaves que lo impidan:
  nadie la referencia).

## Interfaz (`frontend/src`)

```
nucleo/        Cliente de la API, formatos, listas de valores, marca, unidades, directivas.
componentes/   Piezas compartidas (tablas, filtros, modales, íconos, gráficas).
composables/   Lógica reutilizable de pantallas (tablas, columnas, edición exclusiva, rutas).
stores/        Estado global: sesión (permisos, alcance, campos propios), preferencias, tema, avisos.
i18n/          es.json, glosario.json, claves.json y la función t()/tr().
modulos/<d>/   vistas/ (pantallas enrutadas) y componentes/ propios del dominio.
```

La interfaz pide al iniciar `/auth/me` (usuario, permisos, alcance,
configuración pública de la empresa) y `/listas`; con eso muestra u oculta
menús, columnas y campos. Nunca confía en ello para la seguridad: el servidor
vuelve a revisar cada petición.

### Datos guardados y avisos de cambios

Las pantallas no vuelven a consultar lo que no cambió:

1. **Servidor** (`app/core/cambios.py`):
   - Cada alta, cambio o baja confirmada sube la versión de su tabla en `versiones_datos`, por organización y en la misma transacción. Se detecta en el SQL que llega al motor, así que cubre el ORM, las actualizaciones masivas y el SQL directo. Si la transacción se revierte, no sube nada.
   - Cada `GET` anota las tablas que leyó y responde con una ETag. Si se vuelve a pedir lo mismo y nada cambió, responde 304 sin consultar.
   - Un solo lector por proceso revisa las versiones cada `CAMBIOS_INTERVALO_SEG` (2 s), y solo mientras haya navegadores conectados. Avisa por `/api/cambios` a cada organización solo lo suyo y lo compartido.
2. **Interfaz** (`nucleo/api.js`, `nucleo/cambios.js`):
   - Cada respuesta se guarda en la pestaña con sus tablas.
   - Mientras el canal esté abierto y no avise de un cambio en esas tablas, se usa lo guardado **sin hacer la petición**. Si no, se pide con `If-None-Match` y el servidor responde 304 si nada cambió.
   - Un cambio propio (POST, PATCH, PUT o DELETE), un corte del canal o el cambio de día hacen revalidar todo. Al cerrar sesión se borra lo guardado.
   - Dos pedidos iguales al mismo tiempo comparten una sola petición.
   - Las listas (OC, facturas, embarques, productos, inicio, existencias, trabajos e historial de etiquetas) usan `alCambiar(recargar, rutas)`: se vuelven a pedir solas cuando otro usuario cambia algo suyo, y si la pestaña no está a la vista, al volver.

**Límites:**

- Cambios hechos fuera de la aplicación (SQL directo en la base sin pasar por su motor, otra aplicación) no suben versiones. Después de una carga así, `UPDATE versiones_datos SET version = version + 1;` hace que todos vuelvan a pedir sus datos (reiniciar el servidor no basta).
- Las tablas técnicas que cambian solas (`sesiones`, `desafios_dos_pasos`, `idempotencia`, `ediciones`) y la columna `usuarios.ultimo_acceso` no cuentan.
- Una respuesta que dependa del reloj con más detalle que el día debe ir en `SIN_ETAG` de `cambios.py`. Hoy solo la edición exclusiva.

## Cómo agregar…

**Un módulo de dominio**
1. `backend/app/modulos/<dominio>/` con sus servicios y `api.py`
   (`router = APIRouter()`); regístrelo en `RUTAS` de `app/main.py`.
2. Modelos en `app/modelos/<dominio>.py` (reexportados en `__init__.py`) y la
   migración con `alembic revision --autogenerate`. Una tabla de datos de la
   empresa hereda `DeOrganizacion` (y en PostgreSQL su migración le agrega la
   política RLS, como la 0047); una tabla de referencia compartida no.
3. Permisos en `acceso/permisos.MODULOS`; si la empresa puede apagarlo,
   agréguelo a `MODULOS_ACTIVABLES`.
4. Pantallas en `frontend/src/modulos/<dominio>/vistas/` y sus rutas en
   `router.js` con el permiso que exigen.
5. Pruebas en `backend/tests/test_<dominio>.py`.

**Una lista de valores**: agréguela a `LISTAS` en `core/listas.py` con sus
valores de fábrica; aparece en Datos maestros → Listas y se usa con
`listas.valores("<lista>")` (servidor) o `valores('<lista>')` (interfaz).

**Un texto**: escríbalo en inglés con `t('…')` (interfaz) o como mensaje de
`ErrorNegocio` (servidor), ejecute los extractores y tradúzcalo en `es.json`
respetando `glosario.json`. `test_i18n.py` falla si falta alguno.

## Calidad

```bash
cd backend && ruff check app tests && pytest && alembic check
TEST_DATABASE_URL=postgresql+psycopg://usuario:clave@localhost/pruebas pytest   # la misma suite en PostgreSQL (RLS incluida)
cd frontend && npm run lint && npm run build
npm run e2e   # con la demostración corriendo: recorre todas las pantallas en el navegador
```

- `backend/ruff.toml`: errores, sintaxis, orden de imports y errores frecuentes (bugbear).
- `frontend/eslint.config.js`: reglas esenciales de Vue, variables sin uso o sin definir.
- `tests/test_api_docs.py`: cada ruta con docstring, etiqueta de su módulo y resumen (docs/API.md).
- `tests/test_rendimiento.py`: las listas principales no hacen una consulta por fila (se comparan
  con 1 y con 25 filas).
- `frontend/e2e/recorrido.mjs` (`npm run e2e`): entra con cada usuario de la demostración, abre
  todas las pantallas y un documento de cada tipo en escritorio y en celular, y falla con un error
  de JavaScript, de consola (incluido un aviso de «cambios sin guardar» sin edición) o una
  respuesta 4xx/5xx de la API. Usa el Chromium de Playwright o el de `E2E_CHROMIUM`.
