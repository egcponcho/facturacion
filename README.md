# Espacio del proveedor: OC → factura → lista de empaque → cajas → transporte

Un sistema donde cada proveedor (y el equipo interno) arma sus facturas a partir de las órdenes de compra, las reparte en listas de empaque y cajas, y el equipo de importaciones las asigna a unidades de carga y da seguimiento al embarque hasta la bodega.

- **Backend:** Python 3.12, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL (SQLite para desarrollo rápido).
- **Frontend:** Vue 3 + Vite, sin librerías de componentes ni de gráficas (íconos y gráficas SVG propios).
- **Una empresa por instalación:** cada instalación sirve a una sola empresa (la plataforma de varias empresas se retiró en la migración 0037). Su ficha (nombre, logo, país, idioma, moneda, zona horaria, formato de fecha), su **marca** (color de las pantallas y documentos, nombre del sistema y textos de la pantalla de ingreso), sus **documentos** (papel carta o A4, declaraciones de la factura y la lista de empaque y logo en los reportes), su **terminología** (cualquier texto del sistema reemplazado por las palabras de la empresa, en español e inglés, en pantallas y documentos) y sus reglas de negocio se guardan en la base de datos y se editan en *Configuración → Empresa*. Las cuentas de ejemplo de la pantalla de ingreso solo aparecen en la demostración (`SEED_DEMO=1`).
- **Idiomas:** la interfaz, los mensajes y los documentos (PDF/Excel) están en español e inglés. Los identificadores y comentarios del código están en español.
- **Pruebas:** 392 pruebas automatizadas (`backend/tests`); en SQLite se omite la de bloqueo de filas, que necesita PostgreSQL.

## Cómo empezar

### Opción rápida (SQLite, sin instalar base de datos)

Para desarrollo local se usa la demostración (`SEED_DEMO=1`) y la cookie sin `Secure` (`COOKIE_SEGURA=0`), porque `http://localhost` no tiene https. Con `SEED_DEMO=1` y sin `SECRET_KEY`, el servidor usa una clave al azar en cada arranque (las sesiones se cierran al reiniciar).

```bash
# Terminal 1: API en http://localhost:8000 (documentación en /docs)
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
SEED_DEMO=1 COOKIE_SEGURA=0 uvicorn app.main:app --reload
# Windows (PowerShell): $env:SEED_DEMO="1"; $env:COOKIE_SEGURA="0"; uvicorn app.main:app --reload

# Terminal 2: interfaz en http://localhost:5173 (Vite redirige /api al puerto 8000)
cd frontend
npm install
npm run dev
```

Al arrancar se aplican las migraciones y, como la base está vacía, se cargan los datos de ejemplo (la empresa *Distribuidora de Marcas*, los proveedores TNF y Vans, OCs con tallas, plantillas y un embarque con un 40HC).

Para reiniciar la demostración con sus datos de ejemplo: `SEED_DEMO=1 python -m app.instalacion.demo` (desde `backend`; se niega a correr sin `SEED_DEMO=1`).

### Docker y PostgreSQL

```bash
# Demostración (usa backend/.env.demo)
docker compose up --build

# Producción: copie backend/.env.example como backend/.env y complételo
ENV_FILE=backend/.env docker compose up -d
```

Todo corre en http://localhost:8000 (la API también sirve el frontend compilado). `backend/.env.demo` activa `SEED_DEMO=1` y `COOKIE_SEGURA=0` y no define `SECRET_KEY` (clave al azar por arranque); nunca debe usarse en producción.

### En la nube (Render, gratis)

El repositorio incluye `render.yaml`, que crea la base PostgreSQL y el servicio web desde el `Dockerfile`.

1. Entre a https://dashboard.render.com/blueprints y haga clic en **New Blueprint Instance**.
2. Conecte GitHub y elija este repositorio (rama `main`).
3. Haga clic en **Apply**. En unos minutos queda en línea en `https://facturacion-XXXX.onrender.com`.

El blueprint levanta la **demostración**: `SECRET_KEY` se genera automáticamente y los datos de ejemplo se cargan en el primer arranque (`SEED_DEMO=1`). `COOKIE_SEGURA=1` ya está definido porque Render atiende por HTTPS, y `FORWARDED_ALLOW_IPS=*` porque atiende detrás de su propio proxy. Para datos reales: `SEED_DEMO=0`, `SMS_PROVEEDOR=twilio` con sus credenciales y el primer administrador (`EMPRESA_NOMBRE`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `ADMIN_TELEFONO`); vea `docs/PRODUCCION.md`.
Límites del plan gratuito: el servicio se duerme tras 15 minutos sin uso (la primera petición tarda ~1 minuto), la base gratuita vence a los 30 días y los adjuntos viven en un disco temporal.

La misma imagen corre en Railway, Fly.io o Google Cloud Run: defina `DATABASE_URL` (se aceptan `postgres://` y `postgresql://`) y `SECRET_KEY`; el puerto viene de `PORT`.

### Usuarios de la demostración (contraseña `Supplier2026`)

| Correo | Rol | Celular registrado |
|---|---|---|
| tnf@demo.com | Proveedor The North Face | +84 28 3770 001 |
| vans@demo.com | Proveedor Vans | +86 755 2660 001 |
| interno@demo.com | Equipo de importaciones | +503 7000 0002 |
| admin@demo.com | Administrador | +503 7000 0001 |

La demostración no envía SMS reales: la pantalla de ingreso muestra el código de verificación (vea *Acceso seguro*).

## Acceso seguro

- **Ingreso en dos pasos:** correo y contraseña, y luego un **código de 6 dígitos enviado por SMS al celular registrado del usuario**. El código vence en 5 minutos, admite 5 intentos, se puede reenviar después de 30 segundos (hasta 5 envíos) y solo se guarda como hash con clave.
- **Sesiones del lado del servidor** en una cookie `httpOnly` y `SameSite=Strict` (`Secure` con `COOKIE_SEGURA=1`, el valor por defecto). Vencen a las 12 horas o tras 30 minutos de inactividad, y se revocan al cerrar sesión, al cambiar la contraseña o el celular, al desactivar al usuario o al apagar su verificación en dos pasos. El navegador nunca ve un token.
- **Bloqueo:** 5 contraseñas incorrectas bloquean la cuenta 15 minutos; se devuelve el mismo mensaje para un correo desconocido o una contraseña incorrecta. Las peticiones tienen límite por red.
- **Contraseñas:** al menos 10 caracteres, con mayúscula, minúscula, número y símbolo, sin contener el nombre de usuario del correo; cada usuario cambia la suya desde la barra superior. Una contraseña puesta o generada por el administrador es temporal (se pide cambiarla al entrar) y además desbloquea la cuenta.
- **Rutas restringidas:** cada ruta de la API exige sesión y revisa los permisos del rol (los proveedores solo ven sus propios documentos y reciben 404 para los de otros). La interfaz oculta y bloquea las páginas que un rol no puede usar. Los cambios con la cookie exigen el encabezado `X-Requested-With` (protección CSRF).
- **Encabezados de seguridad:** CSP, `X-Frame-Options: DENY`, `nosniff`, política de referrer estricta y HSTS con `COOKIE_SEGURA=1`. Peticiones mayores que `MAX_SUBIDA_MB` (25 MB por defecto) se rechazan. La documentación interactiva de la API (`/docs`) solo se publica en la demostración.
- **Usuarios y accesos** (administrador) se organiza en pestañas: **Usuarios**, **Roles y accesos**, **Proveedores** y **Flujo de clasificación**. Cada usuario tiene un rol, un celular registrado en formato internacional (`+50370001234`) y la verificación en dos pasos encendida o apagada.
- **Roles y accesos:** los roles son libres: el administrador crea cada uno con **nombre, descripción y los permisos** marcados módulo por módulo (ver, crear, editar, eliminar y las acciones propias de cada módulo: importar OCs, finalizar o reabrir facturas y listas de empaque, clasificar y aprobar fichas, gestionar embarques, ver seguimiento, editar el arancel, datos maestros, administración…), los edita en cualquier momento y los asigna a usuarios. No hay tipos de rol fijos: se crean tres roles iniciales (Administrador, Equipo interno, Proveedor) como punto de partida y se pueden editar o eliminar como cualquier otro. **Qué documentos ve un usuario depende del usuario, no del rol:** un usuario con un proveedor asignado solo ve los documentos de ese proveedor, y los permisos del rol sobre datos globales o administración no le aplican (el formulario del rol los marca *Solo usuarios internos*). Los cambios aplican de inmediato; el menú y los botones siguen los permisos y el servidor los hace cumplir. Un rol con usuarios no se puede eliminar, y el sistema nunca deja que el último administrador activo pierda el permiso de administración.
- **Flujo de clasificación:** interruptores que reparten el trabajo de la ficha técnica sin tocar los roles: *Quién llena la ficha técnica* (el proveedor, el equipo interno, si el proveedor ve la partida sugerida) y *Cómo se aprueba una ficha* (revisión antes de aprobar, cuatro ojos, aprobación por lote).

Para enviar SMS reales defina `SMS_PROVEEDOR=twilio` con `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN` y `TWILIO_FROM`. Con el proveedor `consola` (el valor por defecto) el mensaje va al registro del servidor, y solo en modo demostración (`SEED_DEMO=1`) el código también se muestra en pantalla.

## Módulos y campos propios

- **Módulos** (*Configuración → Empresa → Módulos*): la empresa apaga lo que no usa — embarques y recepción, clasificación arancelaria (arancel y familias de producto), seguimiento y lead times. Sus permisos dejan de darse a todos, así desaparecen las pantallas y el servidor rechaza sus rutas; al encenderlo vuelve todo, sin perder datos.
- **Campos propios** (*Configuración → Empresa → Campos propios*): datos que la empresa agrega a artículos, proveedores, sociedades, centros, marcas, transportistas, órdenes de compra y facturas, de tipo texto, número, fecha, sí/no u opción, opcionales u obligatorios. En los datos maestros aparecen en el formulario, la tabla y la carga por Excel; las OC los leen del archivo de carga por su nombre (o con un perfil de importación); en la factura se editan en la cabecera, salen en el PDF y el Excel y, si son obligatorios, se piden para finalizar. Se guardan en la columna `extra` de cada registro (`backend/app/core/campos_propios.py`).

## Página de inicio por rol

Cada rol elige qué paneles ve en su página de inicio (*Usuarios y accesos → Rol → Página de inicio*): indicadores, lo que necesita atención, próximos pasos, embarques, unidades de carga en planificación, alertas de importación, desempeño y por proveedor.

## Alcance de los datos por usuario

Además del rol, cada usuario tiene un **alcance** (*Usuarios y accesos → Usuario → Rol y alcance de los datos*). Vacío = sin límite:

- **Proveedores:** un usuario de proveedor siempre ve su proveedor y, además, los que represente (p. ej. un agente con varios proveedores; elige cuál ver en el encabezado). Un usuario interno puede quedar limitado a algunos proveedores.
- **Sociedades:** solo las OC, facturas, listas de empaque, seguimiento y embarques (por el centro de destino) de esas sociedades; p. ej. el equipo de un país.
- **Transportistas:** un agente de carga o transportista (con un rol que solo tenga los permisos de transporte) ve únicamente los embarques de sus transportistas.

El servidor aplica el alcance en cada consulta (`backend/app/modulos/acceso/permisos.py`); un documento fuera del alcance responde como si no existiera.

## Datos visibles por rol

Además de los permisos, cada rol puede ocultar grupos de datos en *Usuarios y accesos → Rol → «Datos que ve este rol»*. Los grupos están definidos en `backend/app/modulos/acceso/visibilidad.py`:

| Grupo | Qué oculta |
|---|---|
| `precios` | Precios unitarios, valor de la OC, importes de factura y valor facturado |
| `codigos_internos` | Códigos de sociedad, centro, centro de destino y almacén |
| `fechas_internas` | Fecha requerida en tienda, llegada estimada a tienda, holgura y riesgo de atraso |
| `liberaciones` | Códigos y fechas de las liberaciones comercial y logística (el usuario sigue viendo si una OC se puede facturar) |
| `impuestos` | Arancel (DAI), impuestos y regulaciones de importación de cada país de destino |
| `contactos` | Nombres, correos y teléfonos de las personas de la empresa en cada centro y sociedad |

- Ocultar no es solo de la pantalla: el servidor quita esos campos de las respuestas de las pantallas de trabajo (órdenes, facturas, listas de empaque, embarques, seguimiento, productos, tablero, búsqueda) y las columnas de los reportes en Excel/PDF. Los documentos oficiales (factura comercial y lista de empaque) siempre salen completos porque son documentos legales.
- El rol de fábrica de proveedor oculta por defecto `fechas_internas`, `liberaciones` e `impuestos` (se puede cambiar). Los administradores siempre ven todo.
- Además, cada persona elige qué columnas ver con el botón **Columnas** en *Órdenes*, *Seguimiento* y las líneas de la factura; la elección se guarda en su perfil. Solo se ofrecen las columnas que su rol permite.

## Recorrido de 5 minutos

Los datos de la demostración ya tienen historia: facturas de meses anteriores, un contenedor recibido, otro en tránsito y una factura lista para embarcar.

1. Inicie sesión como **tnf@demo.com** (un clic en “The North Face” y luego ingrese el código que se muestra). **Inicio** muestra lo que falta por facturar, empacar y finalizar, dónde está la mercancía y los embarques en camino.
2. En *Órdenes*, en la OC 4400003845 haga clic en **Factura** (o ábrala y cambie “Por facturar” para tomar solo una parte; se pueden combinar varias OCs con **Facturar juntas**). Revise y haga clic en **Crear factura**.
3. En la factura, los pasos de arriba dicen qué falta. Haga clic en **Empacar pendientes**: crea la lista de empaque con todo y la abre.
4. En *Por empacar*, haga clic en **Empaque automático**. Las líneas con casepack se empacan con esa cantidad exacta por caja, las líneas con inner pack en inner packs completos y el resto con la plantilla sugerida. El sobrante que no llena una caja va a una caja parcial con peso estimado (o queda sin empacar).
5. En *Revisar*, verifique el contenido **por destino** y las **unidades de carga sugeridas**, haga clic en **Confirmar estimaciones** y **Finalizar lista de empaque**. De vuelta en la factura, ingrese número y fecha y haga clic en **Finalizar**.
6. Inicie sesión como **interno@demo.com**, abra *Embarques* → EMB-0003, elija 40HC #1 y haga clic en **Asignar carga**: el panel sugiere las unidades de carga para el volumen y el peso seleccionados. Solo se ofrecen facturas y listas de empaque finalizadas. Luego registre la **Salida** con **Registrar evento**.
7. Abra **Productos** (como interno@demo.com). *Lista para aprobar* tiene el Vans Authentic White: el panel de clasificación muestra la partida sugerida 6404.19, el porqué y el código nacional de cada país de destino. Haga clic en **Aprobar**. Desde ese momento sus líneas de OC muestran 6404.19.90.00 (El Salvador) y las facturas la toman automáticamente. Como tnf@demo.com, la chaqueta *Summit blue* fue devuelta con observaciones: complete la composición de la tela exterior y guárdela; vuelve a revisión.
8. *Seguimiento* muestra cada OC (y, al abrirla, cada SKU por etapa) y cada embarque con sus unidades, con la holgura frente a la fecha en tienda. Todo se descarga en PDF o Excel. *Datos maestros* reúne todos los catálogos.

## Datos del artículo vs. datos de la línea de OC

| Artículo (dato maestro, *Datos maestros → Artículos*) | Línea de OC (dato de compra, viene en el archivo de la OC) |
|---|---|
| SKU, estilo, color, talla / ID del prepack, descripción | Número de OC y línea, sociedad, centro, almacén |
| Marca, grupo (categoría → regla de empaque), proveedor | Centro de destino (país), puerto de carga, países de origen y de procedencia |
| Tipo (sólido o prepack), unidad de medida (PAR, UN, CJ) | Cantidad, precio unitario, moneda, incoterm |
| Código de artículo (alfanumérico libre) y SKU del proveedor | Fechas XF, fecha en tienda, liberación comercial y logística |
| UPC | |
| Desglose del prepack (curva de tallas por caja master) | **Casepack** para sólidos (opcional; el inner pack normalmente se define después, en la lista de empaque) |

El artículo no tiene casepack: se define en cada línea de OC, porque el mismo artículo se puede comprar en empaques distintos. En *Órdenes* la tabla de líneas agrupa las columnas como “Artículo · datos maestros” y “Línea de OC · datos de compra”, y el equipo interno puede editar el casepack y el inner pack de una línea mientras no esté facturada.

La partida arancelaria, el país de origen, el tipo de producto y la descripción no se escriben en el artículo: vienen de la **ficha técnica del producto** (siguiente sección), compartida por todas sus tallas. El grupo del artículo define la regla de empaque; no define el tipo de producto. Las categorías de los grupos (y de las escalas de tallas) son un catálogo: *Datos maestros → Categorías de artículo* (de fábrica: calzado, ropa, accesorios y otro).

## Productos: ficha técnica y clasificación arancelaria

El **código de artículo** es libre: cualquier código numérico o alfanumérico de hasta 40 caracteres (letras, dígitos, `.`, `_`, `-`, `/`), sin largo ni prefijo fijo. Cada artículo pertenece a un **genérico** (el estilo-color, hasta 40 caracteres); cuando el archivo o el formulario no lo trae, se deriva como `STYLE-COLOR`. Un **producto** es un genérico: sus tallas y prepacks comparten una ficha técnica y una clasificación. Un genérico se crea una vez con sus datos maestros (*Datos maestros → Artículos → Nuevo genérico*) y después solo se agregan tallas, cada una con su propio código de artículo (escrito completo, o genérico + código de talla), UPC y SKU del proveedor. Las tallas se pueden ingresar como rangos con saltos (p. ej. `7-10, 12, 14`). *Datos maestros → Artículos* muestra por defecto una fila por genérico (**Compacta**), expandible a sus tallas y prepacks; **Lista** muestra una fila por código de artículo. Un prepack tiene su propio código y conserva el genérico de sus sólidos.

- **Ficha técnica**: tipo de producto, género, para quién es, uso, rango de tallas, país de origen, composición por parte (tela exterior, forro, corte, suela…), las características que cambian el código (solo se preguntan esas), fotos y la descripción aduanal en español (armada desde la ficha o escrita a mano): completa —qué es el producto, sus partes (corte y suela), altura, tela, relleno, uso y para quién es— pero con cada material dicho solo por su categoría: **CUERO, TEXTIL o SINTÉTICO** (caucho, plásticos y cuero artificial), sin porcentajes ni fibras y sin la marca (tiene su propio campo), p. ej. *TENIS CON CORTE DE TEXTIL Y SUELA DE SINTÉTICO, SIN CUBRIR EL TOBILLO, PARA DEPORTE O ENTRENAMIENTO, UNISEX*.
- **Motor de clasificación**: corre en el servidor (vea *Un solo motor de clasificación*) mientras se edita la ficha. Aplica las reglas del Sistema Armonizado 2022 (RGI, notas de sección y de capítulo) para ropa, calzado, bolsos y accesorios, aprende de lo ya aprobado y devuelve la subpartida SAC de 6 dígitos, su confianza, el razonamiento, alternativas e inconsistencias por revisar.
- **Códigos nacionales por destino**: solo existen líneas publicadas por una fuente oficial (con fuente, versión y vigencia); la empresa nunca las crea. GT, SV y HN aplican el SAC regional a 10 dígitos, así que sus líneas son las líneas oficiales del ACI. NI, CR y PA muestran *Datos arancelarios nacionales oficiales no disponibles* hasta que se cargue su arancel nacional con su fuente y versión. Las clasificaciones anteriores de la empresa (`historial_clasificacion`) solo ayudan a elegir entre líneas oficiales (*preferida por el historial de su empresa*). Cuando un país abre más la subpartida, la ficha pide solo ese dato. El equipo interno escribe el código nacional directamente en la tabla *Por destino* (se aplica al salir del campo, revisando los dígitos y la subpartida), puede volver al código automático y **recordarlo** para productos similares. Los productos similares muestran su genérico. La ficha ya no pide el rango de tallas: sale de las tallas del genérico. Cada material escrito en la composición muestra cómo cuenta para el arancel (cuero, textil, caucho o plástico, sintético): se reconocen nombres comerciales como synthetic suede, PU leather, leatherette, cowhide, nubuk, phylon, flyknit o corduroy, y se pueden enseñar palabras desconocidas. El panel de clasificación muestra la subpartida SAC de 6 dígitos y las **notas legales del SAC** que aplican (reglas generales, notas de sección, de capítulo y de subpartida); se editan en *Arancel → Notas legales* y la opinión del especialista también las lee. La base es el **texto oficial del SAC** tomado del Arancel Centroamericano de Importación de la SIECA (VII Enmienda, versión 6, agosto de 2025): 518 notas (las seis Reglas Generales, notas de sección, notas de capítulo, notas de subpartida y las notas complementarias centroamericanas de cada capítulo). El panel lista primero las notas que cita el motor y las que tocan la ficha (bebé, unisex, recubierto, cuero, deporte…). Las notas se pueden editar, cargar desde Excel y exportar. Al agregar o editar un código nacional, el formulario muestra solo las condiciones que abren su subpartida: las que ese país ya usa ahí, las que usan otros países y las que abren códigos nacionales en su capítulo, además de cómo divide ese país la subpartida hoy (todas se pueden mostrar igual). Guatemala, El Salvador y Honduras (10 dígitos) vienen con las líneas arancelarias oficiales del ACI (SIECA, VII Enmienda, versión 6) para los capítulos que clasifica el motor, con su DAI; las condiciones que el clasificador deduce de su texto (puntera metálica, que cubre el tobillo o la rodilla, cubrecalzado, para hombre/mujer/bebé, sombreros) son reglas del motor, nunca parte de la línea oficial. La lista completa de partidas y subpartidas del SAC (6,607) se carga con su texto oficial. Nicaragua, Costa Rica (12 dígitos) y Panamá (arancel propio) no tienen líneas nacionales hasta que se carguen sus aranceles oficiales con *Cargar códigos* (fuente y versión obligatorias). Vea `docs/clasificacion/arquitectura.md` para las tres capas (datos oficiales, motor de clasificación, conocimiento de la empresa). `backend/scripts/sieca` reconstruye estos archivos desde una nueva versión del ACI.
- **Cualquier producto**: químicos, materias primas o cualquier otra cosa usan la misma ficha con las categorías genéricas (*Químico*, *Materia prima*, *Otro*) o cualquier categoría creada en la configuración. Los candidatos salen del texto arancelario oficial de los capítulos habilitados, y el resultado sigue siendo una sugerencia que confirma un especialista.
- **Base legal**: cada país de destino tiene su base legal (el Arancel Centroamericano de Importación para los países del MCCA, con las aperturas nacionales a 12 dígitos de Nicaragua y Costa Rica; el Arancel Nacional de Importación de Panamá). Se edita en *Arancel → Países* y se muestra bajo los códigos nacionales de cada ficha.
- **Notas explicativas**: el panel de notas también lista las notas explicativas de la partida. Trae resúmenes propios y cortos para las partidas de los capítulos 42, 61, 62, 64 y 65, marcados como tales; el texto oficial de las Notas Explicativas de la OMA tiene derechos de autor y no se incluye, pero se puede cargar (tipo *Nota explicativa (SA)*, código de partida) desde la carga de notas.
- **Acuerdos comerciales por origen**: la pestaña *Acuerdos comerciales* de cada producto muestra, para cada país de destino y según su país de origen, si un acuerdo comercial cubre ese origen y qué prueba de origen (certificado de origen, EUR.1, FAUCA…) hay que presentar para obtener la preferencia; sin ella aplica el DAI completo. Trae una base de referencia de los acuerdos vigentes para Centroamérica y Panamá (MCCA, DR-CAFTA, acuerdos de asociación con la UE y el Reino Unido, México, Corea, China–Costa Rica, China–Nicaragua, Taiwán–Guatemala, Colombia, Chile, Perú, Canadá, Singapur, República Dominicana, AELC, Israel–Panamá), mantenida en *Datos maestros → Acuerdos comerciales* (códigos ISO de origen y destino, prueba de origen, notas). Contrástela con las fuentes oficiales antes de confiar en ella.
- **Flujo**: una ficha es un **borrador** que cualquiera con acceso (el proveedor o el equipo interno) puede editar y guardar cuantas veces haga falta. Cuando está completa, se **envía a revisión** (una por una o en bloque desde la lista); desde ese momento el proveedor no puede cambiarla salvo que la regrese a borrador. El equipo interno la **aprueba** (o elige otro código) o la **devuelve** con observaciones, y vuelve a borrador. Las fichas aprobadas quedan bloqueadas; un cambio abre una **nueva versión**, y las anteriores quedan en la pestaña *Versiones*, donde cada una se puede ver tal como estaba (datos, composición, descripción aduanal, partida y códigos nacionales) y descargar en PDF o Excel. Quién llena y cómo se aprueba se ajusta en *Usuarios y accesos → Flujo de clasificación*.
- **Dónde se usa**: cada línea de OC muestra el código de su país de destino; las líneas de factura toman el código, el origen y la descripción aduanal de la ficha aprobada (no se escriben en la factura). Una factura no se puede finalizar mientras un producto no esté clasificado; el mensaje enlaza a su ficha.
- **Opinión del especialista (opcional)**: con `ANTHROPIC_API_KEY`, el equipo interno puede pedirle a Claude una segunda opinión con la ficha y hasta dos fotos. Nunca aprueba nada.
- **Dos descripciones**, ambas armadas desde la ficha y editables: la aduanal en español y una comercial sencilla —tipo de producto y marca, p. ej. *CALZADO VANS* o *CHAQUETA THE NORTH FACE*— que se usa en la factura y la lista de empaque.
- **Los prepacks no se clasifican**: se arman con sólidos y toman el producto y la partida de sus sólidos.
- La ficha se descarga en **PDF o Excel** (el Excel agrega una hoja para la composición, los códigos nacionales y las tallas). El reporte de la lista de productos se descarga en Excel o PDF con la composición, la descripción aduanal y el código nacional guardado para cada país de destino; el Excel además tiene una fila por parte de la composición y una por código de país.

**Soporte de clasificación.** La página del producto tiene un panel *Soporte de clasificación* ligado a la subpartida de la ficha y a los códigos nacionales de destino: **Notas legales** (reglas y notas del SAC que aplican), **notas explicativas** y **Base legal** (las líneas arancelarias nacionales con sus condiciones). Es material de referencia para la clasificación y la revisión, no una adaptación automática de la ficha a todo el SAC.

## Arancel y familias de producto

*Arancel* (en *Productos* o en *Configuración → Comercio y cumplimiento*) tiene un menú lateral que separa los datos oficiales de lo que sabe la empresa; la configuración del motor está aparte, en *Familias de producto*. Las tres capas (vea `docs/clasificacion/arquitectura.md`) no se mezclan:

**Datos oficiales** (*Arancel*)
- **Fuentes y versiones** de cada conjunto de datos.
- **Árbol arancelario**: el SAC 2025 v6 oficial (99 capítulos, 1,012 partidas, 5,595 subpartidas, 7,517 líneas arancelarias con su DAI; las 519 líneas cuyo DAI el ACI envía a la Parte II, que difiere por país, no guardan una tasa única), versionado con fuente y checksum. Búsqueda por código o por palabras; cada nodo muestra sus notas legales y, por país, los códigos nacionales, impuestos y regulaciones.
- **Países**: el esquema de códigos y la fuente de cada tipo de dato.
- **Incisos nacionales** de cada país con su arancel, versión, fuente y vigencia. El largo del código se configura por país (8 a 14 dígitos cuando no hay esquema definido).
- **Partidas y subpartidas del SAC** y **Notas legales**, editables.
- **Impuestos**: IVA/ITBMS/ISV, selectivos… con tasa, base, umbrales y base legal. Gana el patrón más específico de cada tipo.
- **Regulaciones**: permisos, licencias, registros, etiquetado… para un código o un patrón (p. ej. `3304`).
- **Capítulos**: qué capítulos usa el clasificador (activo, habilitado, candidato automático, solo manual, archivado), en bloque.
- **Importación de datos**: los tres paquetes oficiales (01 catálogos, 02 motor dinámico, 03 códigos nacionales, regulaciones e impuestos) se cargan por etapas:
  1. Suba el archivo a una vista previa. Se valida el archivo y se muestra cada registro nuevo, cambiado o reemplazado (antes → después), los errores y las advertencias.
  2. Publique para aplicarlo, o descártelo. Si los datos cambiaron desde la vista previa, se le pide revisarla de nuevo.

  Las cargas nunca borran lo publicado.
- **Integridad de los datos arancelarios**.

**Conocimiento de la empresa** (*Arancel → Historial, decisiones y palabras clave*, bajo `/api/conocimiento/…`): historial de clasificación, decisiones manuales y correcciones, palabras clave y sinónimos aprendidos. El motor devuelve `legal_confidence` (solo reglas y texto oficial) y `historical_confidence` (solo historial de la empresa); el historial solo ordena los candidatos que permiten los datos oficiales.

**Motor de clasificación** (*Familias de producto*; configuración, no dato oficial, también bajo `/api/clasificacion/configuracion/…`), en este orden:
- **1 · Familias y categorías**: dominios (químicos, materias primas, calzado, ropa, accesorios) y sus capítulos. Un dominio solo ordena preguntas y candidatos; nunca fuerza ni excluye un capítulo.
- **2 · Preguntas**: los atributos que pide la ficha del producto, con sus opciones (sinónimos, orden, activo) y dónde aplican (sistema, dominio, capítulo, partida, subpartida o categoría de producto; preguntar, obligatorio o no preguntar). La ficha toma de aquí las etiquetas, las opciones desactivadas y las preguntas apagadas.
- **3 · Reglas**: las reglas del sistema (solo capítulos habilitados, notas legales por encima de la similitud de texto, preguntar solo lo que distingue, revisión de especialista cuando hay ambigüedad…) y las reglas de selección nacional, que son las condiciones del producto que eligen cada código nacional, separadas del código oficial.
- **Listas de referencia**: clases de material, vocabulario de búsqueda y traducciones.

**Un motor para todos los dominios**: `POST /api/clasificacion/sesion` clasifica calzado, ropa, químicos y materias primas por igual (texto, dominio, categoria, ficha, respuestas, paises, version). Calzado, ropa, accesorios, químicos y materias primas están escritos a partir de las Notas Explicativas del SA en `backend/app/data/motor/familias/*.json` (generados por `backend/scripts/familias/construir.py`, que comprueba cada regla y caso de prueba contra el árbol oficial): categorías, preguntas con la nota que las justifica, reglas `R-NE-*` y casos de prueba. Los productos pueden adjuntar documentos **SDS / TDS / COA** (pestaña *Documentos técnicos*): sus datos (CAS, composición, estado físico, densidad, pH…) completan hechos vacíos de la ficha y nunca son fuente arancelaria.

### Un solo motor de clasificación (servidor)

Hay **un solo motor de clasificación**, en Python (`backend/app/modulos/clasificacion/motor_clasificacion.py`). La ficha del producto, el guardado, la clasificación en bloque, las cargas, la aprobación y la opinión del especialista lo llaman; el navegador solo muestra y edita (no tiene lógica de clasificación).

- **Ficha natural → hechos.** La interfaz envía la ficha tal como se escribió (categoría, composición por parte, género, edad, uso…). El servidor la normaliza (`ficha.py`): lee las composiciones (`composicion.py`), deriva hechos (fibra predominante, material del corte y de la suela…), aplica implicaciones y bloqueos de opciones, detecta lo que dicen el nombre y el uso, y conserva lo que eligió la persona.
- **Todas las categorías funcionan igual**, calzado y ropa incluidos. Las categorías (`CategoriaProducto`), atributos, opciones, dependencias y ámbitos son datos. Cree un dominio, una categoría, sus atributos, opciones, ámbitos, reglas y códigos nacionales en *Familias de producto* y *Arancel*, y sus productos se clasifican sin cambios de código.
- **Ámbitos (SHOW / REQUIRE / HIDE).** Gana el ámbito más específico: categoría > dominio > subpartida > partida > capítulo > sistema. Los empates se resuelven por prioridad, luego HIDE > REQUIRE > SHOW, luego el más reciente.
- **Reglas.** Un número mayor significa mayor precedencia. Hay tres capas: legal (notas legales, arancel nacional), sistema y empresa. Una regla de la empresa nunca rompe una restricción legal (`blocked_by_legal`). Una regla que choca con otra superior queda `overridden_by`.
  - RESTRICT y EXCLUDE reducen los códigos permitidos.
  - BOOST solo sube códigos permitidos.
  - ASK pide datos.
  - REVIEW y WARN envían el producto a revisión.

  Cada regla tiene un número de revisión y una firma. Una regla legal debe citar su nota legal, y la interfaz muestra *Evidencia legal* aparte de *Regla del sistema* y *Regla de la empresa*. Los códigos de las reglas se revisan contra el árbol de la versión vigente.
- **Versiones.** La versión vigente se resuelve por fecha y ámbito (regional o por país). La misma entrada con la misma fecha reproduce una clasificación pasada. Las líneas nacionales solo salen de la versión vigente del país y dentro de su propia vigencia; las líneas oficiales nunca se editan, y los cambios de la empresa son sobrescrituras con motivo.
- **Códigos nacionales.** Cada país tiene sus largos válidos (`10, 12`…). Un código se valida contra ellos y nunca se trunca. Un código de la empresa solo se acepta con un largo válido y dentro de la subpartida.
- **Evidencia.** Cada respuesta lleva la versión, las entradas, los hechos derivados, las reglas (evaluadas, aplicadas, sobrescritas), las notas legales, el SA6, el SAC, los códigos nacionales, la confianza, las alternativas, los motivos de revisión y las sobrescrituras. La aprobación la guarda en el producto y en cada versión.
- **El historial** solo impulsa códigos que las reglas permiten.

Un código de un capítulo no habilitado no se puede aprobar.

El esquema de la base de datos se maneja con Alembic (`backend/alembic`). Las migraciones pendientes se aplican al arrancar (igual en demostración y en producción). Una prueba revisa que las migraciones coincidan con los modelos.

## Cargas masivas y exportaciones

- **Artículos por genérico, con su ficha técnica** (*Datos maestros → Artículos* o *Productos*): una plantilla de Excel con dos hojas. *Genéricos*: una fila por genérico con sus datos maestros (estilo, color, marca, grupo, proveedor, unidad) y las columnas de la ficha (categoría, género, edad, uso, tallas, origen, composición por parte y las características que cambian el código). *Tallas*: una fila por talla con su código de talla (o el siguiente libre), UPC y SKU del proveedor. Después de la carga, el motor completa cada genérico y sugiere su partida automáticamente. También se acepta una sola hoja con una fila por código de artículo. Cada ventana de carga tiene una **Vista previa** de la plantilla (hojas, columnas, obligatorias, filas de ejemplo y qué va en cada columna) además de la descarga en Excel.
- **Cada catálogo de datos maestros** (marcas, grupos, categorías de artículo, estados de liberación, proveedores, sociedades, centros, contactos, almacenes, transportistas, tipos de unidad, países, puertos…) tiene su propia plantilla de Excel, carga (crea o actualiza por código) y exportación a Excel/PDF con los filtros de la pantalla.
- **Los reportes** siguen los filtros elegidos en pantalla; los filtros de dimensión aceptan uno o varios valores. No incluyen las columnas que el rol tiene ocultas (vea *Datos visibles por rol*).

## Periodos del tablero

El panel *Desempeño* del tablero muestra lo que pasó en el periodo (valor facturado, listas de empaque finalizadas, embarques que llegan, productos clasificados) y la gráfica del valor facturado para el periodo elegido —el mes en curso por defecto— con opciones rápidas (esta semana, este mes, el mes pasado, este trimestre, este año, 12 meses, personalizado). La gráfica agrupa por día, semana o mes según el largo del periodo, y se puede filtrar por marca.

## Reglas de empaque

Todas las opciones de empaque que necesita el proveedor están disponibles y el servidor las hace cumplir:

- **Sólido con casepack:** cada caja lleva exactamente el casepack, mismo estilo, color y talla; las tallas nunca se mezclan. Solo la última caja puede ser parcial, y se marca para confirmarla con el Commercial Brand Manager.
- **Prepack:** un surtido por caja master, con distribución de tallas fija; el prepack ya es una caja definida, así que no lleva casepack ni inner pack.
- **Sólido sin casepack (ropa, accesorios):** la cantidad por caja viene de una plantilla o se ingresa libremente, y las cajas se pueden mezclar.
- **Inner packs:** cuando la línea de OC tiene inner pack, todos sus inner packs llevan la misma cantidad de unidades o pares, y toda cantidad (línea de OC, línea de factura, movimiento de la lista de empaque, contenido de la caja, plantillas que usa el empaque automático) debe ser un número entero de inner packs. Con casepack, el casepack debe ser múltiplo del inner pack (p. ej. casepack 20 = 4 inner packs de 5); sin casepack, las cajas se empacan en múltiplos del inner pack. Cada inner pack lleva una etiqueta que identifica el producto y la cantidad total que contiene, y cada unidad o par dentro conserva su etiqueta individual; la lista de empaque muestra los inner packs por caja.
- **Por país de destino:** una caja nunca mezcla mercancía para centros de destino distintos. La lista de empaque muestra qué va a cada destino (cantidades y cajas) para que el proveedor empaque y etiquete cada uno por separado; el documento muestra el destino final, o “según caja” cuando hay varios.
- **Etiqueta:** *estándar* si la caja lleva una sola OC, estilo, color y talla; *consolidada* en otro caso.
- **Pallets:** las cajas se pueden paletizar (medidas del pallet y tara); el volumen usa las medidas del pallet y el peso bruto suma la tara.

### Sugerencia de unidades de carga

A partir del volumen (m³) y el peso bruto de la lista de empaque, el sistema sugiere unidades de carga con el catálogo *Tipos de unidad*:

Cada modo de transporte (*Listas de valores*) dice cómo se calcula:

- **Por volumen** (de fábrica: marítimo y terrestre): unidades completas a cerca del 85 % del volumen útil (las cajas nunca llenan el 100 %), consolidado (LCL, LTL) cuando el volumen no justifica una unidad completa, o unidades completas más una más pequeña o un consolidado para el resto.
- **Por peso cobrable** (de fábrica: aéreo): una guía por el mayor entre el peso real y el volumen por el factor del modo (167 kg por m³).

La opción recomendada (menos unidades completas, luego menos capacidad sobrante) se muestra en la lista de empaque y al asignar carga a un embarque.

## Datos maestros

Un solo lugar con crear, editar, eliminar y filtros con búsqueda para: **sociedades**, sus **centros**, **contactos**, **almacenes**, **países**, **puertos**, **marcas**, **grupos de artículos**, **categorías de artículo**, **escalas de tallas**, **proveedores**, **artículos**, **prepacks**, **tipos de empaque**, **transportistas**, **tipos de unidad**, **estados de liberación**, **acuerdos comerciales**, **regiones**, **pasos de lead time**, **reglas de lead time** y **listas de valores**. Los registros en uso no se pueden eliminar.

- **Proveedores:** código, nombre, razón social, NIT, país, dirección y contacto (aparecen como exportador en la factura y la lista de empaque). Cada proveedor tiene **sus marcas**, **las sociedades con las que trabaja** y sus propios **artículos**; la marca de un artículo debe ser una de las de su proveedor.
- **Transportistas:** código (SCAC o IATA), nombre, tipo (un modo de transporte o multimodal) y las sociedades con las que trabajan.
- **Tipos de unidad:** modo, **servicio** (una modalidad de ese modo: FCL, LCL, aéreo, FTL, LTL…), capacidad en m³ y kg y si exige marchamo.
- **Puertos:** puerto marítimo, aeropuerto o frontera terrestre. Un **centro** tiene un puerto principal de llegada y otros puertos de llegada.
- **Sociedades y centros:** la sociedad de la OC es la **facturada**; su centro es el **notify party** con su país y puerto de llegada. El **centro de destino** de la OC (p. ej. 2220) dice a qué país llega finalmente la mercancía.
- **Artículos:** código de artículo (numérico o alfanumérico), genérico (opcional), estilo, color y talla (opcional), marca, grupo y **unidad de medida**. Los sólidos se crean aquí, a mano o con `plantilla_articulos.csv`.
- **Prepacks:** un artículo con su propio código de producto, un **ID del prepack** (su talla, p. ej. `AB12`) y un **desglose** fijo armado solo con sólidos del mismo estilo y color. El desglose se puede ver en todas partes pero nunca cambiar. Carga masiva con `plantilla_prepacks.csv`.
- **Categorías de artículo:** el catálogo de categorías de los grupos de artículos y de las escalas de tallas (de fábrica: `CALZADO`, `ROPA`, `ACCESORIO`, `OTRO`).
- **Estados de liberación:** los códigos que manda el ERP de la empresa para la liberación comercial y la logística (vea *Órdenes de compra*).
- **Listas de valores:** los valores que ofrecen los formularios y que se aceptan en los archivos, sin nada fijo en el código: **unidades de medida** (nombre, plural, otros nombres en los archivos y si se cuentan en enteros), **monedas** (símbolo, decimales y monto en letras en inglés y español), **incoterms**, **modos de transporte** (cómo se sugieren sus unidades de carga: por volumen o por peso cobrable con su factor; ícono y cómo se llaman su documento, sus puertos, sus transportistas y sus unidades), **modalidades de transporte** (de qué modo son y si son consolidadas, como LCL y LTL) y los tipos de **centro**, **almacén**, **contacto**, **impuesto** y **documento técnico**. Los valores de fábrica son los de una instalación nueva; los de sistema (la caja de prepack `CJ`) se pueden renombrar, pero no borrar ni desactivar. Definición: `backend/app/core/listas.py`.

## Órdenes de compra

- Número de OC libre (hasta 40 caracteres) y número de línea libre (alfanumérico, hasta 10).
- **Obligatorio vs. opcional:** solo proveedor, número de OC, línea, artículo y cantidad son obligatorios. Sociedad (facturar a), moneda y precio se pueden completar después; son obligatorios **para facturar**, y mientras tanto los cálculos de valor los muestran como pendientes. Un precio exige moneda; una cantidad debe ser mayor que 0.
- **Empaque en la OC:** un prepack trae su curva de tallas; un sólido puede traer su casepack. El inner pack normalmente se define después en la lista de empaque (columna *Por inner pack*, editable mientras la línea no tenga cajas y la OC no lo haya definido).
- El **SKU** de cada línea debe existir en el maestro de artículos y pertenecer al proveedor de la OC, y el proveedor debe trabajar con la sociedad de la OC.
- **Almacén por línea:** la misma OC puede enviar cada línea a un almacén distinto de la misma sociedad.
- **Liberaciones (dos equipos):** cada OC tiene una liberación **comercial** y una **logística**. Sus estados son datos, no código: se definen en *Datos maestros → Estados de liberación* con los códigos que manda el ERP de la empresa, cada uno con su nombre y sus marcas: `libera` (con este estado la liberación está dada), `con_cambios` (estado logístico de una OC liberada que cambió después), `predeterminado` (el que se usa cuando el archivo no trae el dato) y `alias` (otras palabras que acepta el importador). Los estados de fábrica son los de SAP (comercial `C` liberada / `P` pendiente; logística `300` liberada, `301` liberada con cambios posteriores, `304` no liberada), pero cada empresa los cambia por los suyos. Las reglas del flujo son las mismas para cualquier empresa: solo se factura con las dos liberaciones dadas, sin liberación comercial no hay liberación logística y una OC con liberación logística dada que cambia pasa al estado «con cambios».
- **Fechas de liberación:** cada liberación guarda su fecha (de `commercial_release_date` / `logistics_release_date` del archivo, o el día en que quedó liberada) para medir los lead times. Logística debe liberar una OC cierto número de días **antes de su XF**, según las reglas de lead time de su origen (vea *Lead times*; en la demostración, 21 días para Asia y 15 en general).

### Crear e importar OCs

*Cargar órdenes de compra* tiene dos modos con la **misma estructura y validaciones**: **formulario** (encabezado más tarjetas de línea; la lista de artículos se filtra por proveedor y la unidad se adapta al artículo) y **archivo**. En *Importar OCs* (equipo interno) suba el Excel o CSV exportado del ERP. Una vista previa muestra lo nuevo, lo cambiado, lo que no cambia, los conflictos y los errores; nada se guarda hasta confirmar. Los conflictos (p. ej. una cantidad menor que lo facturado, o un cambio de casepack/inner pack en una línea facturada) no se aplican y aparecen como alertas.

Columnas obligatorias: `supplier, po, po_line, sku, quantity`. Opcionales: `unit_price, currency, company, plant, destination, storage_location, incoterm, po_date, port_of_loading, country_of_origin, country_of_shipment, xf_date_original, xf_date, in_store_date, commercial_release, logistics_release, commercial_release_date, logistics_release_date, delivery_date, uom, casepack, inner_pack`. Se siguen aceptando los nombres de columna anteriores en español y alias comunes (`vendor`, `material`, `qty`…). Las liberaciones se leen por código, nombre o alias del estado. **Plantilla de ejemplo** descarga una plantilla de Excel generada para el usuario, con sus fechas de ejemplo en el formato de fecha del usuario.

**Perfiles de importación.** Si el ERP de la empresa exporta sus columnas con otros nombres, en otra fila o con otro formato de fecha, un perfil (*Cargar órdenes de compra → Perfiles*) dice cómo leer ese archivo: el nombre de la columna de cada dato (varios separados por coma; tienen prioridad sobre los nombres estándar), la fila de los encabezados, el formato de las fechas y valores por defecto para lo que el archivo no trae (p. ej. la moneda o el incoterm). Al cargar se elige el perfil; el perfil predeterminado se usa sin elegirlo. Los nombres propios de un ERP no están en el código: una instalación que ya tenía OCs al actualizar recibe un perfil *Previous column names* con los nombres que se aceptaban antes (`sap_code`, `codigo_sap`, `sap`).

Los códigos se guardan como texto para conservar los ceros a la izquierda; dé formato de texto a esas columnas en Excel antes de exportar.

## Consistencia de los datos

Los datos maestros y los documentos quedan encadenados, tanto en el archivo de OC como en el formulario de OC:

- Un proveedor solo trabaja con **sus sociedades** (*Datos maestros → Proveedores*): una OC para otra sociedad se rechaza, y el formulario solo ofrece esas sociedades y, de ellas, sus centros, almacenes y centros de destino. Sin sociedad, la OC toma la de su centro, almacén o centro de destino.
- Centro, almacén y centro de destino deben pertenecer a la sociedad de la OC; el artículo debe pertenecer al proveedor de la OC y su marca debe ser una de las marcas del proveedor; se rechazan proveedores y artículos inactivos.
- La marca de un artículo debe ser una de las marcas de su proveedor; un artículo en OCs no puede cambiar de proveedor; un proveedor no puede perder una sociedad o una marca que ya usa; un centro o almacén usado en OCs no puede cambiar de sociedad; el centro de un contacto debe pertenecer a su sociedad.
- Una factura solo toma líneas de un proveedor y de OCs compatibles según las reglas de compatibilidad de la empresa (vea *Reglas configurables*); un embarque llega a un solo centro y su transportista debe trabajar con esa sociedad.

## Número de la lista de empaque

Cada lista de empaque recibe `PL-001`, `PL-002`… por defecto, y el proveedor puede escribir **su propio número** (hasta 40 caracteres: letras, números y `. _ - / #`) en el encabezado de la lista de empaque mientras esté en borrador o en corrección. Debe ser único entre las listas de empaque activas del proveedor.

## Embarques

**Estado frente a la fecha en tienda.** Cada unidad de carga y cada embarque estiman su fecha en tienda a partir del arribo real, o la ETA, o la salida (real o ETD) más el tránsito, más los pasos posteriores al arribo del lead time de su origen y los días extra del grupo de producto (*Datos maestros → Grupos de artículos → Días extra después del arribo*, p. ej. para productos que necesitan etiquetado o inspección). Se compara con la fecha en tienda más temprana de sus OCs: **A tiempo**, **En riesgo** (holgura menor que la regla *Holgura mínima (días) antes de la fecha requerida para estar en tiempo* de *Configuración → Empresa*, 7 días de fábrica) o **Atrasado**. Un embarque toma el peor estado de sus unidades.

- **Todo sigue el modo:** un embarque marítimo solo ofrece puertos marítimos, navieras y contenedores; aéreo, aeropuertos, aerolíneas y guías aéreas; terrestre, fronteras, transportistas terrestres y camiones. El **servicio es de cada unidad**, así que un embarque marítimo puede ser FCL, LCL o mixto.
- **Solo viajan documentos finalizados:** una unidad de carga solo acepta listas de empaque finalizadas cuya factura esté finalizada; el panel de asignación lista solo esas. Reabrir una factura o una lista de empaque que está en una unidad planificada la quita de la unidad (se vuelve a agregar al finalizarla); después de la salida ya no se pueden reabrir.
- Mientras está **planificado**, se pueden agregar, mover o quitar unidades y carga. A la **salida** se cierra la carga.
- Los eventos siguen el orden de estados (recolección → salida → tránsito → arribo → liberación → entrega → recepción); sin fechas futuras ni anteriores al último evento.
- La carga no puede superar la capacidad nominal de una unidad. Cada embarque llega a un solo centro.

**Hitos del embarque.** Los eventos que se registran en un embarque están en *Datos maestros → Listas de valores → Hitos del embarque*. Los de sistema (recolección, salida, tránsito, arribo, liberación aduanal, entrega, recepción y otro) hacen avanzar el embarque y conservan sus reglas: se pueden renombrar, pero no cambiar sus estados ni borrar. La empresa agrega sus propios hitos (p. ej. inspección en puerto) y elige en qué estados del embarque se registran; un hito propio no cambia el estado.

## Lead times

Los lead times son reglas configurables con herencia por nivel geográfico (`backend/app/modulos/transporte/reglas_lt.py`):

- **Pasos de lead time** (*Datos maestros*): el catálogo de pasos que puede usar un lead time (booking, liberación, XF, ETD, ETA, aduana, bodega, ingreso, tienda…). Un paso se puede ligar a una fecha que el sistema mide para comparar el plan con lo real.
- **Reglas de lead time** (*Datos maestros*): Global → Región → País → Puerto. Cada regla define solo lo que cambia (pasos que agrega, sobrescribe o quita, y el orden): cada paso es su paso de referencia más N días (naturales o hábiles), opcionalmente solo para un modo de transporte; lo demás se hereda del nivel superior. Las **regiones** agrupan países de origen, y a cada país se le asigna su región en *Países*.
- *Configuración → Logística → Lead times* muestra el **lead time efectivo** de una región, país o puerto después de la herencia, con el nivel del que viene cada paso.

## Seguimiento

Para el equipo interno: el rol de proveedor no lo incluye (se puede otorgar en su rol).

Cuatro tableros. Los dos primeros comparten filtros (marca, grupo, estilo, color, talla, SKU, almacén, etapa, unidad de carga, BL/AWB, embarque, proveedor, sociedad, centro, riesgo de llegada tardía y rangos de ETA, XF y fecha en tienda), cada uno descargable en **PDF o Excel**:

- **Órdenes de compra:** liberaciones, estado, avance, XF vencida y holgura frente a la fecha límite en puerto; cada OC se abre en su **detalle por SKU**.
- **Embarques y unidades de carga:** una fila por embarque y documento de transporte, que se abre en unidades y en lo que lleva cada unidad por OC.
- **Facturación y listas de empaque:** en qué paso está cada documento y qué falta.
- **Lead times:** promedio de días de cada etapa **por país de origen** (OC creada → liberación comercial → liberación logística → producción y recolección → salida → tránsito al puerto de destino → puerto a bodega → ingreso a bodega), el porcentaje de liberaciones logísticas a tiempo frente a su meta antes de la XF, la recolección frente a la XF y la holgura en puerto. Cada OC se abre en sus **hitos**, cada uno con su meta, su fecha real o estimada y cuántos días de adelanto o atraso tiene. Filtros: periodo (OCs creadas; últimos 12 meses por defecto), origen, región y proveedor.

**Fecha estimada en tienda.** Cada OC, fila de seguimiento y fila de lead time muestra cuándo estaría la mercancía en tienda con el lead time de su origen: el arribo real, la ETA o, sin embarque, la XF (u hoy, si ya pasó) más el tránsito estándar; luego los pasos de puerto a bodega, ingreso y reexportación. Al lado, cuántos días de adelanto o atraso tiene frente a la fecha en tienda solicitada. Para una OC es la fecha de la última mercancía que falta por llegar.

**Adelanto o atraso.** La fecha en tienda no se compara con el arribo al puerto: después del puerto la mercancía todavía tiene que llegar a la bodega, ingresar y reexportarse a la tienda. Por eso cada OC tiene una **fecha límite en puerto** = fecha en tienda − los días de puerto a bodega, ingreso y reexportación de su lead time (más los días extra del grupo de producto), y el arribo (real, la ETA del embarque o, sin embarque, la XF más el tránsito estándar) se compara con ella: atrasado si es posterior, justo si quedan menos de 7 días de holgura. La reexportación aún no se registra en el sistema; solo se reserva su tiempo.

## Factura comercial y lista de empaque (PDF y Excel)

Cada factura y lista de empaque se descarga en **PDF** (lista para imprimir y firmar) o **Excel**, siguiendo los requisitos aduaneros centroamericanos (CAUCA/RECAUCA y DUCA):

- **Partes:** exportador/vendedor, importador/facturar a (sociedad con NIT) y consignatario/notify party.
- **Condiciones:** número y fecha, incoterm, moneda, condiciones de pago, países de origen y procedencia, transporte, puertos, transportista y BL/AWB, contenedores y marchamos. Los encabezados no listan órdenes de compra ni centros de destino (serían demasiado largos); **cada línea muestra su OC y línea**.
- **Detalle:** OC y línea, código y UPC, descripción comercial, **partida arancelaria (SAC)**, origen, cantidad, unidad, precio y total. En la lista de empaque, por grupo de cajas: rango y número de cajas, contenido por caja, **inner packs**, medidas, pesos neto y bruto, m³, pallet y tipo de etiqueta.
- **Totales:** cantidad por unidad, bultos, pesos, volumen, valor, **monto en letras** (“SAY: FOUR THOUSAND … US DOLLARS AND 00/100” en inglés, “SON: …” en español), marcas de embarque y la declaración firmada del exportador.
- Hasta que se finaliza, el PDF lleva la marca de agua **BORRADOR · NO OFICIAL** (*DRAFT · NOT OFFICIAL* en inglés); cada página muestra “Página X de Y”.
- Salen completos aunque el rol del usuario oculte datos: son documentos legales.
- El idioma del documento es el que la persona eligió en su perfil (vea *Idiomas*).

## Reglas principales

**Todo se maneja por cantidades, con la misma fórmula en cada nivel:** disponible = cantidad del nivel superior − lo asignado en documentos activos.

| Nivel | Se asigna | Se libera al |
|---|---|---|
| Línea de OC → factura | cantidad parcial o total | quitar la línea, reducir la cantidad o anular la factura |
| Línea de factura → lista de empaque | parcial o total, en una o varias listas | quitarla de la lista, reducirla en la factura o anular la lista |
| Fila de la lista → cajas | cajas completas, parciales o mixtas | desempacar |

- **Reducir en la factura** algo que ya está en una lista de empaque: el sistema muestra qué listas lo tienen y libera lo que no está en cajas. Lo empacado nunca se toca automáticamente.
- **Empaque automático:** un paso para toda la lista, cada fila con su propia plantilla, siguiendo las reglas de casepack e inner pack.
- **Las plantillas** solo llenan datos; cada caja conserva sus propios valores.
- **Cajas parciales:** medidas de la plantilla, peso neto proporcional y bruto = neto + tara, marcadas como estimadas hasta confirmarlas.
- **Los cambios en bloque** son todo o nada: si una fila falla, no se aplica ninguna y se explica la fila que falló.
- **Estados:** Borrador → Finalizada; reabrir la pasa a “En corrección” y pide un motivo.
- **Concurrencia:** bloqueo de filas al tomar saldo, una versión por documento (una edición desactualizada se rechaza), claves de idempotencia y un historial de cada cambio con usuario, antes/después y motivo.

## Reglas configurables

Las reglas de negocio se configuran **en la aplicación**, en *Configuración → Empresa → Reglas de negocio* (solo administradores), y se guardan en la base de datos. La lista está en `REGLAS` de `backend/app/core/empresa.py` y se validan y guardan en `backend/app/modulos/empresa/organizacion.py`. Las variables de entorno del mismo nombre (`backend/app/core/config.py`) solo son los **valores de fábrica** de una instalación nueva, mientras la empresa no los cambie en pantalla.

| Regla | De fábrica | Qué hace |
|---|---|---|
| `PROVEEDOR_PUEDE_FINALIZAR` | sí | Los proveedores pueden finalizar sus facturas y listas de empaque. Reabrir siempre es interno. |
| `POSICION_EN_VARIAS_FACTURAS` | no | No: una línea de OC vive en **una sola factura activa** (el saldo solo se agrega a esa factura); sí: el saldo puede ir a otra factura. |
| `FACTURA_EN_UNA_SOLA_UNIDAD` | no | Todas las listas de empaque de una factura deben ir en la misma unidad de carga. |
| `REQUERIR_DATOS_ADUANA` | sí | Para finalizar se exigen país de origen y partida arancelaria por línea. |
| `DIAS_ALERTA_BORRADOR` | `7` | Días después de los cuales un borrador que sigue reservando cantidades aparece como alerta. |
| `DIAS_MARGEN_RIESGO` | `7` | Holgura mínima (días) frente a la fecha en tienda para estar a tiempo; con menos queda en riesgo. |
| `DIAS_AVISO_TIENDA` | `30` | Días antes de la fecha en tienda a partir de los que una OC se resalta en *Órdenes*. |
| `PAIS_BASE_CLASIF` | vacío | País (código de dos letras) cuyo código nacional completa la partida sugerida. La demostración usa `SV`. |
| `COMPATIBILIDAD_BLOQUEANTE` | sociedad, moneda, centro | Datos de la OC que **no se pueden mezclar** en una factura (bloquean). |
| `COMPATIBILIDAD_ADVERTENCIA` | incoterm, centro de destino | Datos de la OC que **solo avisan** si se mezclan en una factura. |

Las reglas de compatibilidad se eligen entre sociedad, centro, centro de destino, moneda, incoterm, puerto de carga y país de origen; un mismo dato no puede bloquear y solo avisar a la vez. En la misma pantalla se editan la ficha de la empresa (nombre, razón social, NIT, país, logo) y sus preferencias (idioma predeterminado, moneda base, zona horaria y formato de fecha).

### Variables de entorno

Solo lo que depende del servidor (vea `backend/app/core/config.py` y `backend/.env.example`):

| Variable | Por defecto | Qué hace |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./facturas_pl.db` | Base de datos. En producción, PostgreSQL (se aceptan `postgres://`, `postgresql://` y `postgresql+psycopg://`). |
| `SECRET_KEY` | — | **Obligatoria**: clave al azar de 32 caracteres o más. Sin ella (o más corta) el servidor no arranca; solo la demostración genera una al azar por arranque. |
| `SEED_DEMO` | `0` | Con `1`, carga los datos de ejemplo en una base vacía, muestra el código de verificación en pantalla y publica `/docs`. Nunca en producción. |
| `COOKIE_SEGURA` | `1` | La cookie de sesión solo viaja por https (y se envía HSTS). `0` solo en desarrollo local sin https. |
| `CORS_ORIGINS` | `http://localhost:5173` | Orígenes que pueden llamar a la API con la sesión, separados por coma. |
| `DOS_PASOS` | `1` | Verificación en dos pasos por SMS para los usuarios que la tienen encendida. |
| `SESION_HORAS` / `SESION_INACTIVIDAD_MIN` | `12` / `30` | Duración de la sesión y cierre por inactividad. |
| `INTENTOS_MAX` / `BLOQUEO_MIN` | `5` / `15` | Intentos fallidos antes del bloqueo y minutos de bloqueo. |
| `CODIGO_VALIDEZ_MIN` / `CODIGO_REENVIO_SEG` | `5` / `30` | Validez del código y espera antes de reenviarlo. |
| `SMS_PROVEEDOR` | `consola` | `consola` (registro del servidor) o `twilio` (con `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM`). |
| `EMPRESA_NOMBRE`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `ADMIN_TELEFONO` | — | Instalación nueva: nombre de la empresa y primer administrador (solo si la base no tiene usuarios; la contraseña es temporal). |
| `UPLOAD_DIR` | `./archivos` (`/data/archivos` en Docker) | Carpeta de adjuntos; en producción, un disco persistente con respaldo. |
| `MAX_SUBIDA_MB` | `25` | Tamaño máximo de una petición (archivos que se suben), en MB. |
| `ANTHROPIC_API_KEY` / `CLAUDE_MODELO` | — | Activa la opinión opcional del especialista en *Productos*. |
| `FORWARDED_ALLOW_IPS` | `127.0.0.1` | Del `Dockerfile`: `*` cuando el contenedor solo es accesible por el proxy de la plataforma, para que el bloqueo por intentos use la IP real. |
| `PORT` | `8000` | Puerto del contenedor (lo define la plataforma en la nube). |

`POSICION_EN_VARIAS_FACTURAS`, `FACTURA_EN_UNA_SOLA_UNIDAD`, `PROVEEDOR_PUEDE_FINALIZAR`, `REQUERIR_DATOS_ADUANA`, `DIAS_ALERTA_BORRADOR` y `PAIS_BASE_CLASIF` también se pueden definir como variables, pero solo como valores de fábrica (vea arriba).

**Base de datos:** demostración y producción aplican las mismas migraciones de Alembic al arrancar y nunca se borra nada. `SEED_DEMO=1` solo agrega datos de ejemplo a una base vacía; `SEED_DEMO=1 python -m app.instalacion.demo` reinicia la demostración. `python -m app.instalacion.inicial correo celular` (desde `backend`) crea o restablece un administrador y escribe en pantalla una contraseña temporal.

## Diseño adaptable

La interfaz se adapta a monitores grandes, laptops, tabletas y teléfonos en lugar de solo encogerse:

- **Filtros:** en el teléfono la búsqueda queda visible y los demás filtros y acciones secundarias se abren desde un botón **Filtros** que muestra cuántos están activos (`v-filtros`).
- **Tablas:** en tabletas se ocultan las columnas marcadas como secundarias (`<th class="col-sec">`); en el teléfono cada fila se vuelve una **tarjeta** con el nombre de la columna junto a cada valor (`v-tarjetas`).
- **Encabezado:** en el teléfono el idioma, el tema, la contraseña y el cierre de sesión pasan al menú.
- **Más opciones:** en el teléfono las acciones secundarias (descargas PDF y Excel, cargas, reabrir, anular…) van en un menú **Más opciones**, dejando visible la acción principal. *Datos maestros* muestra en el escritorio los catálogos de uso diario como pestañas y el resto en **Más catálogos**; en el teléfono, un selector de catálogo.
- **Contextual:** no se muestran los filtros con un solo valor posible (una sociedad, una marca…).

## Mi perfil y preferencias

Cada usuario abre *Mi perfil* desde su nombre en el encabezado (o el menú en el teléfono) para:

- **Datos básicos:** editar su nombre; ver su correo, rol, proveedor y celular registrado (el celular lo cambia el administrador).
- **Contraseña:** cambiarla (sus otras sesiones se cierran).
- **Preferencias**, guardadas en el perfil y aplicadas en cada dispositivo:
  - **Idioma** de la pantalla (por defecto, el idioma predeterminado de la empresa).
  - **Idioma de los documentos** (PDF y Excel que descarga: facturas, listas de empaque, fichas técnicas y reportes): *Igual que la pantalla*, español o inglés.
  - **Formato de fecha** (por defecto, el de la empresa; de fábrica **MM/DD/YYYY**; también DD/MM/YYYY, YYYY-MM-DD, DD-MMM-YYYY, MMM DD, YYYY). Se usa **en todas partes**: listas y documentos en pantalla, los **campos de fecha** (escritos en ese formato o elegidos en el calendario), los archivos **PDF y Excel** que el servidor genera para el usuario, la **plantilla de carga de OCs** (sus fechas de ejemplo vienen en ese formato) y la **lectura de los archivos que sube** (una fecha como 05/10/2026 se lee con el orden día/mes del usuario; las fechas ISO y las celdas de fecha de Excel siempre se aceptan).
  - **Formato de hora** (12 o 24 horas) y **formato de números** (1,234.56 · 1.234,56 · 1 234,56 · 1'234.56).
  - **Tema** (claro, oscuro o el del sistema), **filas por página** en las tablas y **página de inicio** después de iniciar sesión.
  - Las **columnas** elegidas en *Órdenes*, *Seguimiento* y las líneas de la factura.

## Idiomas

La interfaz está en **español e inglés**. El idioma por defecto es el predeterminado de la empresa (*Configuración → Empresa*); antes de iniciar sesión se usa el del navegador. Cada usuario elige su idioma en *Mi perfil* (o con el selector del encabezado) y queda en su perfil, así que lo sigue en cualquier dispositivo.

- El texto en inglés es la clave; la traducción al español está en `frontend/src/i18n/es.json`. Las traducciones están adaptadas al negocio, no son literales: `frontend/src/i18n/glosario.json` fija el término aprobado para cada concepto (p. ej. *Type* → *Tipo*, nunca *Chico*) y lista las traducciones literales que no se aceptan.
- `backend/tests/test_i18n.py` revisa el español: todos los textos presentes, los mismos marcadores `{0}`, sin textos sin traducir, los términos del glosario respetados, y `claves.json` y `backend/app/i18n/es.json` al día con el código.
- Después de cambiar textos, extraiga las claves: primero los mensajes del servidor con `python scripts/i18n_extraer.py` (desde `backend`, escribe `app/i18n/claves.json`) y luego los de la interfaz con `node scripts/i18n-extraer.mjs` (desde `frontend`, escribe `src/i18n/claves.json` y `backend/app/i18n/es.json`); después agregue las traducciones nuevas en `es.json`.
- **Documentos (PDF/Excel):** cada persona elige en su perfil el idioma de sus documentos; una descarga también puede forzarlo con `?idioma=es|en`. Los documentos usan `backend/app/modulos/documentos/idioma_doc.py` y la traducción de `backend/app/i18n/es.json`. Los montos en letras siguen las reglas de cada idioma (`backend/app/modulos/documentos/letras.py`), no una traducción.
- Los textos oficiales quedan como se publicaron: las descripciones del SAC y la descripción aduanal están en español.

## Pruebas

```bash
cd backend
pytest                                   # SQLite
TEST_DATABASE_URL=postgresql+psycopg://user:password@localhost/tests pytest   # PostgreSQL (incluye concurrencia)
```

Las pruebas usan la demostración (`SEED_DEMO=1`, `COOKIE_SEGURA=0`) en una base temporal; con `TEST_DATABASE_URL` la base PostgreSQL de pruebas se vacía al empezar.

Revisiones de calidad antes de subir cambios:

```bash
cd backend && ruff check app tests && alembic check   # estilo y errores frecuentes; modelo y migraciones al día
cd frontend && npm run lint && npm run build          # ESLint (Vue) y compilación
```

## Estructura

Las capas, los mecanismos de configuración y cómo agregar un módulo, una lista de valores o un texto están en **[docs/ARQUITECTURA.md](docs/ARQUITECTURA.md)**.

```
backend/app/
  main.py            aplicación FastAPI: middlewares, errores y registro de las rutas de cada módulo
  core/              núcleo transversal (no depende de los módulos): config.py (variables de entorno), db.py,
                     seguridad.py, empresa.py (reglas de negocio REGLAS), errores.py
  web/               capa HTTP compartida: dependencias.py (usuario de la petición) y rutas.py (piezas comunes de las rutas)
  modelos/           modelo de datos (SQLAlchemy), un archivo por dominio
  esquemas/          contratos de entrada de la API (pydantic), un archivo por dominio
  modulos/           un paquete por dominio, cada uno con sus servicios y su api.py (rutas bajo /api):
    comun/           historial, idempotencia, búsqueda de texto, normalización, edición exclusiva
    acceso/          inicio de sesión en dos pasos, usuarios, roles y permisos, proveedores, preferencias, datos visibles por rol
    empresa/         ficha y reglas de la empresa
    maestros/        catálogos, genéricos y tallas, unidades de medida, acuerdos comerciales, cargas masivas
    compras/         órdenes de compra y liberaciones
    facturacion/     facturas y cantidades por nivel
    empaque/         listas de empaque, estructura física, plantillas de caja
    transporte/      embarques, unidades de carga, recolección, lead times
    seguimiento/     tablero, búsqueda global, seguimiento, alertas y reportes
    productos/       ficha técnica, flujo de clasificación y descripciones
    clasificacion/   arancel oficial, motor de clasificación, atributos, reglas, familias, conocimiento
    documentos/      PDF y Excel (factura, lista de empaque, plantillas), montos en letras, idioma del documento
  instalacion/       arranque de una instalación: migraciones.py, datos incluidos, primer administrador (inicial.py),
                     demostración (demo.py)
  i18n/              textos del servidor (claves.json) y su traducción al español (es.json)
  data/              datos oficiales del arancel, motor de clasificación (familias) y datos de la demostración
backend/alembic/     migraciones de la base de datos
backend/tests/       flujo completo, motor de clasificación (de punta a punta, fixtures de paridad en tests/paridad), reglas de empaque,
                     acceso seguro, visibilidad por rol, idiomas, producción y concurrencia
frontend/src/
  main.js, App.vue, router.js, styles.css   arranque, marco de la aplicación, rutas y estilos
  nucleo/            cliente de la API (api.js), formatos (utils.js), búsqueda, unidades de medida, directivas
  componentes/       interfaz compartida: íconos, modales, tablas (paginación, orden, columnas), filtros, selectores,
                     estados, gráficas SVG, barra de acciones en bloque, cargas de archivos, búsqueda global
  composables/       tablas, columnas por usuario, edición exclusiva, rutas
  stores/            sesión, selección para facturar, preferencias, tema, avisos
  i18n/              es.json, glosario.json y claves.json
  modulos/<dominio>/ vistas/ (pantallas) y componentes/ propios de cada dominio:
    acceso/          ingreso, bienvenida, Mi perfil, Usuarios y accesos
    empresa/         Configuración → Empresa
    inicio/          tablero de inicio
    compras/         órdenes de compra y su carga
    facturacion/     facturas
    empaque/         listas de empaque y plantillas de empaque
    transporte/      embarques y lead times
    seguimiento/     seguimiento de mercancía
    productos/       productos y ficha técnica
    clasificacion/   arancel, familias de producto y llamadas al motor (sin lógica de clasificación)
    maestros/        datos maestros, genéricos y reglas de lead time
```

## Antes de pasar a producción

Vea **[docs/PRODUCCION.md](docs/PRODUCCION.md)**: variables obligatorias (`DATABASE_URL`, `SECRET_KEY`, `SEED_DEMO=0`, SMS con Twilio, `CORS_ORIGINS` y el primer administrador con `EMPRESA_NOMBRE`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `ADMIN_TELEFONO`), lo que se configura dentro de la aplicación, el primer arranque, actualizaciones y respaldos. La plantilla con todas las variables comentadas es `backend/.env.example`.
