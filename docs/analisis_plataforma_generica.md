# Análisis: de sistema de importación a plataforma genérica de comercio exterior

Objetivo: que el sistema sirva a **cualquier empresa**, para **importación y
exportación** con la misma línea de trabajo (orden → factura → packing list →
embarque → recepción/entrega), con **tracking visible para ambos lados**,
**roles con alcance y delegación**, **control de edición simultánea**, sin
depender de SAP ni de una industria. Un "ERP liviano" enfocado en la cadena
documental y logística, no un ERP completo.

Este documento parte de lo que el código tiene hoy (con referencias) y
complementa la propuesta anterior (`docs/propuesta_revision_integral.md`,
Etapas 2 y 3), que sigue vigente y se integra en la hoja de ruta del final.

---

## 1. Veredicto

La base es buena para generalizar: el flujo documental está bien resuelto
(saldo de OC, factura con versiones, PL con estructura física, unidades de
carga, eventos, historial, permisos por acción, motor de clasificación
configurable). Lo que lo ata a una empresa no es la lógica sino **cinco
supuestos de diseño**:

1. **Solo hay una dirección**: siempre compramos a un proveedor que nos factura
   y nos envía. No existe cliente, pedido de venta ni embarque saliente.
2. **Solo hay un tipo de contraparte**: `Proveedor`. Transportista está aparte y
   no hay agente aduanal, forwarder ni cliente.
3. **Vocabulario y códigos de SAP y de retail de moda**: `codigo_sap`,
   liberaciones `C/P` y `300/301/304`, sociedad/centro/almacén como textos,
   XF, fecha en tienda, estilo/color/talla y marca obligatorios.
4. **El alcance de datos sale del tipo de usuario**: interno ve todo y proveedor
   ve lo suyo. No hay alcance por entidad legal, país, sitio o marca, ni
   delegación.
5. **Una sola empresa**: no hay organización; los códigos son únicos globales.

Ninguno exige reescribir. Se resuelven con migraciones compatibles, en etapas.

---

## 2. Lo que ya está bien y se conserva

| Área | Qué hay | Dónde |
|---|---|---|
| Flujo documental | OC → factura (con saldo por posición) → PL → unidad de carga → embarque → recepción | `services/ordenes.py`, `facturas.py`, `packing.py`, `transporte.py` |
| Bloqueo optimista | `version` + `verificar_version()` devuelve 409 `conflicto_version` | `services/common.py:179`; usado en factura, PL y producto |
| Idempotencia | Tabla `Idempotencia` para no duplicar operaciones reenviadas | `models.py:1784` |
| Permisos por acción | Catálogo por módulo (ver, editar, finalizar, reabrir, cancelar) y roles libres | `services/common.py:43` (`MODULOS`) |
| Seguridad de acceso | PBKDF2, bloqueo por intentos, 2 pasos por SMS, sesiones en servidor revocables | `services/acceso.py` |
| Historial | Acción, detalle, motivo, usuario y fecha por entidad | `models.Historial` |
| Configuración sin código | Familias, atributos, reglas, lead times por pasos, empaques jerárquicos, escalas de tallas | motor y catálogos |
| Experiencia | Búsqueda global, bandeja "Necesita atención", requisitos para continuar, vistas guardadas, paneles laterales | Etapa 1 y rediseño |
| Idiomas | 5 idiomas con prueba que bloquea textos sin traducir | `tests/test_i18n.py` |

---

## 3. Diagnóstico por área

### 3.1 Acoplamiento a SAP, a una industria y a esta empresa

| Hallazgo | Evidencia | Efecto |
|---|---|---|
| Campo `codigo_sap` como SKU de la posición | `PosicionOC.codigo_sap` | El nombre impone SAP en API, plantillas y exportes |
| Liberaciones con códigos de SAP | `OrdenCompra.liberacion_comercial` = `C/P`; `liberacion_logistica` = `300/301/304`; filtros y textos en Seguimiento | Otra empresa no tiene esos códigos |
| Sociedad, centro y almacén guardados como texto en los documentos | `OrdenCompra.sociedad/centro/centro_destino`, `Factura.sociedad/centro`, `Embarque.centro` (String, sin FK) | Renombrar un código rompe vínculos; no hay integridad |
| Términos de retail de moda en el núcleo | `fecha_xf`, `fecha_tienda`, `estilo/color/talla`, `casepack/inner_pack/prepack`; `Articulo.marca_id` y `grupo_id` obligatorios | Una química, una autopartista o un exportador agrícola no encajan |
| Reglas de negocio en variables de entorno | `PROVEEDOR_PUEDE_FINALIZAR` y otras en `config.py` | Iguales para todos; no se cambian desde la app |
| Permiso "Import POs from the ERP" | `oc.importar` | Supone que hay un ERP |

En total hay **83 referencias** a códigos o nombres de SAP en el backend y
**19 archivos** (backend y frontend) que usan `codigo_sap` o
`liberacion_logistica`.

### 3.2 Solo importación

- `Factura.proveedor_id` es obligatorio: toda factura la emite un proveedor
  hacia nosotros.
- `OrdenCompra` es la única orden; no hay pedido de venta (orden del cliente).
- `Embarque` no tiene dirección (entrante o saliente), y su `centro` es
  siempre el destino.
- Los PDF de factura y PL ponen al proveedor como emisor y a la sociedad como
  "Bill to". Para exportar se invierte: nosotros emitimos y el cliente es el
  destinatario.
- `RecepcionLinea` registra entradas; no hay contraparte de salida (entrega o
  prueba de entrega).

### 3.3 Tracking de un solo lado

- El permiso `transporte.gestionar` es solo interno y no puede darse a un
  proveedor (`common.py`, `MODULOS`). El proveedor solo ve la unidad de carga
  de sus PL.
- No existe el cliente como usuario, así que en exportación nadie del otro lado
  puede ver su embarque.
- Los eventos se cargan a mano y todos los ven igual; no hay eventos visibles
  solo para algunos participantes, ni avisos por suscripción.

### 3.4 Roles y usuarios

- `Rol.tipo` (`admin | interno | proveedor`) y `Usuario.rol` (texto) duplican
  la información; `alcance()` decide los datos visibles según exista o no
  `proveedor_id` (`common.py:107`).
- Solo hay tres alcances posibles: todo, todo con administración, o un
  proveedor. No se puede limitar a un usuario a "El Salvador", "marca TNF" o
  "sitio 8010".
- Administrar usuarios es todo o nada (permiso `admin`). Un proveedor no puede
  dar acceso a su propio personal.
- **No hay delegación**: si alguien sale de vacaciones, su trabajo queda
  detenido o se le da a otro un rol más amplio de lo necesario.

### 3.5 Edición simultánea

- El bloqueo optimista existe pero solo en **factura, PL y producto** (10
  usos de `verificar_version`). **OC, embarque, unidad de carga, catálogos,
  roles y usuarios** no tienen `version`: gana la última escritura y se
  pierden cambios sin aviso.
- En el frontend, solo `PackingListView.vue` reacciona a `conflicto_version`.
  En las demás pantallas el 409 aparece como un error genérico.
- No hay aviso previo de que otra persona está editando el mismo registro: el
  conflicto se descubre al guardar.
- Algunas operaciones dependen de un saldo (facturar contra la OC, asignar PL a
  una unidad con capacidad). Con dos usuarios a la vez deben hacerse con
  bloqueo de fila dentro de la transacción. En PostgreSQL eso es
  `SELECT … FOR UPDATE`; SQLite no lo soporta.

### 3.6 Una sola empresa

- No hay tabla de organización. Hay códigos únicos globales
  (`Proveedor.codigo`, `Sociedad.codigo`, `Articulo.sku`, `Embarque.codigo`),
  así que dos empresas en la misma base chocarían.
- Nombre, logo, formatos, numeraciones y terminología no son configurables
  por empresa (la propuesta anterior ya lo planteó en 2.1).

### 3.7 Tamaño del sistema

El módulo de clasificación arancelaria (motor, árbol oficial, notas, reglas)
es grande: unas 3 500 líneas solo en `motor_clasificacion`, `aranceles`,
`ficha` y `atributos`. Es valioso, pero no toda empresa lo necesita. Debe
poder **apagarse como módulo** sin afectar la cadena documental.

---

## 4. Modelo propuesto: un ERP liviano de comercio exterior

### 4.1 Organización (empresa) y su configuración

`organizacion` con nombre, logo, idioma, zona horaria, moneda base, formatos,
numeraciones, terminología, módulos activos y reglas (las que hoy son
variables de entorno). Todas las tablas de negocio llevan `organizacion_id`.
Los códigos únicos pasan a ser únicos **por organización**, y un filtro
central en el servidor impide ver datos de otra.

### 4.2 Socios de negocio con roles

Una sola entidad `socio` (business partner) con uno o varios roles:
**proveedor, cliente, transportista, forwarder, agente aduanal, notify,
consignatario**. `Proveedor` y `Transportista` migran a `socio` y se conservan
como vistas filtradas. Los contactos y las direcciones cuelgan del socio.
Además, un socio puede tener **usuarios propios**: el portal del proveedor de
hoy se generaliza a portal de socio.

### 4.3 La misma línea para importar y exportar

Un solo juego de documentos con un campo **`flujo`**: `IMPORT | EXPORT`, y
`DOMESTIC` a futuro.

| Paso | Importación (hoy) | Exportación (nuevo) | Entidad común |
|---|---|---|---|
| Orden | OC a un proveedor | Pedido de un cliente | `orden` (tipo `COMPRA` o `VENTA`) con posiciones y saldo |
| Factura comercial | Emite el proveedor, la recibimos | Emitimos nosotros al cliente | `factura` con `emisor` y `receptor` (socios o entidad legal propia) |
| Packing list | Lo arma el proveedor | Lo armamos nosotros (o nuestro almacén) | `packing_list` sin cambios |
| Embarque | Entrante: llega a nuestro sitio | Saliente: sale de nuestro sitio | `embarque` con `direccion` y origen/destino como sitio o dirección del socio |
| Cierre | Recepción en almacén | Entrega o prueba de entrega al cliente | `recepcion` / `entrega` |

El motor de saldo, versiones, finalización, reapertura, PDF, Excel y la
búsqueda se reutilizan tal cual; solo cambian **quién emite**, **quién
recibe** y los textos. Los PDF toman emisor y receptor del documento en vez
de suponer "proveedor → sociedad".

### 4.4 Entidades organizativas reales

`Sociedad`, `Centro` y `Almacén` se presentan como **Entidad legal**,
**Sitio** y **Ubicación de almacén** (los nombres los configura la
organización). Los documentos pasan de guardar el código como texto a guardar
la llave foránea, con migración que resuelve los códigos actuales.

### 4.5 Artículo genérico

- `estilo/color/talla` pasan a ser **atributos de variante** configurables por
  familia (ya existe el motor de atributos y las escalas de tallas). Para moda
  se siembran estilo, color y talla; una química usaría concentración y
  presentación.
- `marca` y `grupo` pasan a ser opcionales.
- `codigo_sap` pasa a `codigo_articulo`, con alias en API, plantillas e
  importador.

### 4.6 Fechas y estados universales

- Fechas clave con nombre configurable: XF pasa a **"Fecha lista para
  despacho"** (ready date) y fecha en tienda a **"Fecha requerida"** (required
  date). Los cálculos de riesgo y holgura no cambian.
- Liberaciones: estado interno `PENDIENTE | LIBERADA | LIBERADA_CON_CAMBIOS |
  BLOQUEADA`, más una tabla de **mapeo de códigos externos** (sistema, dominio,
  código → estado). SAP queda como un mapeo sembrado (`300`, `301`, `304`,
  `C`, `P`), igual que cualquier otro ERP.

### 4.7 Tracking bidireccional

- **Participantes del embarque**: proveedor o cliente, forwarder, agente
  aduanal, transportista. Cada uno ve el embarque desde su portal según su
  rol, con sus documentos y eventos.
- **Visibilidad por evento**: interno, todos los participantes o solo algunos
  roles. Por ejemplo, una nota de aduana interna no la ve el cliente.
- **Hitos configurables por modo y flujo**. Exportación agrega, por ejemplo,
  "Booking confirmado", "Cut-off", "Despacho de exportación" y "Entregado al
  cliente".
- **Quién registra**: el forwarder o el agente pueden cargar eventos desde su
  portal; queda la autoría y el origen (usuario, importación o integración).
- **Suscripciones y avisos** por correo a los participantes cuando cambia la
  ETA o hay un evento clave.
- A futuro, un conector a APIs de navieras o aerolíneas. Es opcional y no
  forma parte del núcleo.

---

## 5. Roles, alcance y delegación

### 5.1 Tres piezas separadas

| Pieza | Qué es | Ejemplo |
|---|---|---|
| **Permiso** | Una acción concreta | `factura.finalizar`, `embarque.ver`, `usuarios.invitar` |
| **Rol** | Un conjunto de permisos con nombre | "Coordinador logístico", "Facturador del proveedor" |
| **Asignación** | Usuario + rol + **alcance** + vigencia | Ana: Coordinador logístico, alcance "Entidad legal SV", sin fecha fin |

**Alcance** (qué registros): organización completa, o una lista de entidades
legales, sitios, países, marcas o socios. Un usuario puede tener varias
asignaciones; sus permisos efectivos son la unión, y cada permiso se evalúa
dentro de su alcance.

Una sola función en el servidor decide: `puede(usuario, permiso, registro)`.
Reemplaza a `proveedor_filtro`, `asegurar_proveedor` y `alcance()`, y se
aplica también a la búsqueda global, los tableros y los exportes.

Migración sin cambio de comportamiento:
- `admin` e `interno` pasan a alcance de organización.
- `proveedor` pasa a alcance del socio `proveedor_id`.

### 5.2 Delegación dentro de los propios permisos

Caso: Ana sale de vacaciones y quiere que Luis apruebe facturas de El Salvador
por dos semanas.

- **Quién**: cualquier usuario con el permiso `delegar` (que se da por rol).
- **Qué puede delegar**: solo un **subconjunto de sus permisos** y **dentro de
  su alcance**. La pantalla solo ofrece lo que Ana tiene; el servidor lo
  vuelve a validar.
- **Recalculado siempre**: lo que Luis puede hacer como delegado es lo
  delegado, intersecado con lo que Ana tiene **hoy**. Si Ana pierde un
  permiso, Luis lo pierde también sin que nadie lo toque.
- **Vigencia**: fecha de inicio y fin obligatorias (o "hasta revocar", si la
  organización lo permite), además de un motivo.
- **Límites**:
  - No se delegan `admin`, `delegar` ni la administración de usuarios.
  - No se re-delega.
  - Un usuario de proveedor solo delega a usuarios de su mismo proveedor.
  - La organización puede exigir aprobación de un administrador.
- **Trazabilidad**: cada acción queda como "Luis, en nombre de Ana". Ana ve un
  registro de lo que se hizo con su delegación.
- **Revocable** en cualquier momento, por Ana o por un administrador. A ambos
  les llegan avisos al iniciar, vencer o revocar.

### 5.3 Administración repartida

- `usuarios.invitar`: invitar usuarios **al mismo alcance o a uno menor**, con
  roles cuyos permisos sean un subconjunto de los propios. Esto permite que el
  responsable de un proveedor administre a su propio equipo sin pedirle nada
  al equipo interno.
- `usuarios.administrar` (completo) queda para administradores.
- Regla general: **nadie puede dar más de lo que tiene** (ni permisos ni
  alcance), ni por rol, ni por invitación, ni por delegación.

---

## 6. Edición simultánea

Tres niveles complementarios.

**Nivel 1: bloqueo optimista en todo lo editable (obligatorio)**
- Un mixin `Versionado` (columna `version`) en OC, embarque, unidad de carga,
  socios, catálogos, roles y usuarios, además de factura, PL y producto, que ya
  lo tienen.
- Toda edición envía la versión que se leyó. Si no coincide, el servidor
  responde 409 `conflicto_version` (ya existe).
- Un componente común en el frontend ofrece *Ver qué cambió*, *Recargar* o
  *Copiar mis cambios*. Así ninguna pantalla pierde datos en silencio.

**Nivel 2: aviso de "en edición" (bloqueo suave)**
- Tabla `edicion_activa` (entidad, id, usuario, desde, expira). Al entrar a
  editar se toma; se renueva cada 30 s mientras la pantalla está abierta y
  vence a los 2 minutos sin señal.
- Los demás ven un aviso: *"María está editando esta factura desde las 10:42.
  Puedes verla en solo lectura."* También tienen la opción de pedirle que la
  libere.
- Un administrador puede forzar la liberación (queda en el historial).
- Aplica a documentos de edición larga: factura en borrador, PL, OC, embarque
  y ficha de producto. No aplica a acciones rápidas.

**Nivel 3: bloqueo por estado y por saldo**
- Lo finalizado no se edita; reabrir requiere permiso. Esto ya existe y se
  extiende a OC y embarque cerrados.
- Las operaciones que consumen un saldo se ejecutan con bloqueo de fila en la
  transacción (`SELECT … FOR UPDATE` en PostgreSQL). Son, por ejemplo,
  facturar contra la OC, asignar un PL a una unidad o confirmar recepción. La
  idempotencia existente evita duplicados por doble clic o reenvío.
- Producción debe ir en PostgreSQL; SQLite queda solo para demo y pruebas.

---

## 7. Lo que NO conviene construir (para no volverse un ERP grande)

- Contabilidad, cuentas por pagar o cobrar, impuestos contables.
- Inventario completo (costeo, conteos, MRP), producción o nómina.
- Precios, listas de precios y CRM de ventas.

El sistema debe **integrarse** con el ERP o la contabilidad de cada empresa
(importar órdenes, exportar facturas, recepciones y costos de embarque) usando
el importador con mapeo y la tabla de códigos externos. No debe reemplazarlos.

---

## 8. Hoja de ruta

Cada etapa se publica por separado, con migración compatible, pruebas y sin
quitar funciones. Tamaño relativo: S pequeño, M mediano, L grande.

| # | Etapa | Contenido | Depende de | Tamaño | Prioridad |
|---|---|---|---|---|---|
| G1 | **Concurrencia** | Mixin `Versionado` en todo lo editable, 409 común en el frontend, bloqueo de fila en saldos, aviso "en edición" | — | M | **Alta** (riesgo hoy) |
| G2 | **Organización** | Tabla y configuración por empresa, variables de entorno a la app, módulos activables, unicidad por organización | — | M | **Alta** |
| G3 | **Sin SAP** | Estados universales y mapeo de códigos externos, `codigo_sap` a `codigo_articulo`, terminología configurable, fechas con nombre configurable | G2 | M | **Alta** |
| G4 | **Accesos** | Permiso, rol y asignación con alcance; función única `puede()`; invitación limitada; **delegación** | G2 | L | **Alta** |
| G5 | **Socios** | `socio` con roles (proveedor, cliente, forwarder, agente, transportista); portal de socio | G2, G4 | M | Media-alta |
| G6 | **Exportación** | `flujo` IMPORT/EXPORT; pedido de venta; factura con emisor y receptor; embarque con dirección; entrega; PDF según dirección | G5 | L | Media-alta |
| G7 | **Tracking compartido** | Participantes por embarque, visibilidad por evento, hitos por flujo, eventos desde el portal, avisos | G5, G6 | M | Media |
| G8 | **Organización física** | Entidad legal, sitio y ubicación como llaves foráneas en los documentos | G2 | M | Media |
| G9 | **Artículo genérico** | Variantes por atributos; marca y grupo opcionales | G3 | M | Media |
| G10 | Lo pendiente de la propuesta anterior | Documento universal, actividad transversal, importador con mapeo, campos personalizados, workflow simple, automatizaciones | G2–G4 | L | Media-baja |

Orden recomendado: **G1 → G2 → G3 → G4**. Con eso el sistema ya es seguro con
varios usuarios, configurable por empresa, sin SAP y con accesos y delegación.
Después vienen **G5 → G6 → G7** para exportación con tracking de ambos lados,
y por último G8–G10.

---

## 9. Riesgos y cómo se controlan

| Riesgo | Control |
|---|---|
| Migraciones que renombran campos (`codigo_sap`, liberaciones) rompen integraciones o plantillas | Alias en la API y el importador durante un periodo; pruebas de regresión con los archivos de carga actuales |
| Errores en el filtro de alcance exponen datos | Una sola función `puede()` con pruebas por alcance (organización, entidad, socio, delegado) y pruebas de "no ve" en listados, búsqueda, tableros y exportes |
| La delegación se usa para escalar privilegios | Intersección recalculada siempre, sin re-delegación, permisos no delegables, vencimiento obligatorio y auditoría |
| El aviso "en edición" deja registros trabados | Vencimiento automático y liberación forzada por administrador |
| El sistema crece demasiado | Módulos activables y la lista de "no construir" de la sección 7 |

---

## 10. Decisiones que necesito de ti

1. **¿Varias empresas en una misma instalación** (multiempresa real), o una
   instalación por empresa? Cambia cuánto aislamiento hace falta en G2.
2. **Exportación: ¿quién arma el PL**, nuestro almacén o un tercero (operador
   logístico)? Define si el operador necesita portal en G5 y G6.
3. **Delegación**: ¿la aprueba un administrador o basta con que el delegante
   la cree? ¿Se permite "hasta revocar" o siempre con fecha fin?
4. **Edición simultánea**: ¿basta con aviso y solo lectura para los demás, o
   algunos documentos deben quedar trabados de forma estricta mientras alguien
   los edita?
5. **¿Arrancamos con G1** (concurrencia, el único riesgo que existe hoy) y
   seguimos en el orden propuesto?
