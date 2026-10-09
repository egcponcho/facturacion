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
  concurrencia corren con `TEST_DATABASE_URL`).

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
cd frontend && npm run lint && npm run build
```

- `backend/ruff.toml`: errores, sintaxis, orden de imports y errores frecuentes (bugbear).
- `frontend/eslint.config.js`: reglas esenciales de Vue, variables sin uso o sin definir.
