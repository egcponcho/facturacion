# Paso a producción

Todo lo que hay que cambiar o definir para usar el sistema con datos reales.
El código ya está listo para producción: la demostración y la instalación
real siguen el mismo camino (mismas migraciones, misma seguridad). La única
diferencia es `SEED_DEMO=1`, que carga datos de ejemplo en una base vacía.

## 1. Lo que hay que definir (obligatorio)

| Variable | Qué poner | Por qué |
|---|---|---|
| `DATABASE_URL` | URL de PostgreSQL (`postgresql+psycopg://usuario:clave@servidor:5432/base`) | SQLite solo sirve para pruebas locales |
| `SECRET_KEY` | Clave al azar de 32 caracteres o más: `python -c "import secrets; print(secrets.token_urlsafe(48))"` | Firma las sesiones y los códigos SMS. **Sin ella el servidor no arranca.** Guárdela en el gestor de secretos de la plataforma, nunca en el repositorio |
| `SEED_DEMO` | `0` (o no definirla) | Con `1` se cargan datos de ejemplo, el código de verificación aparece en pantalla y el ingreso ofrece las cuentas de ejemplo |
| `SMS_PROVEEDOR` | `twilio` | Con `consola` el código de verificación solo queda en el registro del servidor |
| `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM` | Credenciales de Twilio | Envío del código por SMS |
| `CORS_ORIGINS` | URL pública de la aplicación (`https://facturacion.miempresa.com`) | Solo ese origen puede llamar a la API con la sesión |
| `EMPRESA_NOMBRE` | Nombre de la empresa | Solo en el primer arranque |
| `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `ADMIN_TELEFONO` | Primer administrador: correo, contraseña inicial (cumple la política: 10+ caracteres, mayúscula, minúscula, número y símbolo, sin el nombre del correo) y celular `+50370000000` | Solo si la base no tiene usuarios. La contraseña es temporal: el sistema pide cambiarla al entrar. **Bórrelas después del primer arranque** |

Plantilla con todas las variables comentadas: `backend/.env.example`.

## 2. Lo que conviene revisar

| Variable | Valor por defecto | Cuándo cambiarla |
|---|---|---|
| `COOKIE_SEGURA` | `1` | Déjela en `1`: la sesión solo viaja por https. `0` solo en desarrollo local sin https |
| `FORWARDED_ALLOW_IPS` | `127.0.0.1` | `*` cuando el contenedor solo es accesible a través del proxy de la plataforma (Render, Cloud Run, un balanceador). Así el bloqueo por intentos usa la IP real del usuario |
| `UPLOAD_DIR` | `/data/archivos` en Docker | Debe ser un **disco persistente con respaldo** (facturas, fichas técnicas, fotos) |
| `MAX_SUBIDA_MB` | `25` | Tamaño máximo de cualquier archivo que se sube (facturas, fotos, fichas técnicas, cargas) |
| `SESION_HORAS` / `SESION_INACTIVIDAD_MIN` | `12` / `30` | Política de sesiones de la empresa |
| `INTENTOS_MAX` / `BLOQUEO_MIN` | `5` / `15` | Política de bloqueo por contraseña |
| `DOS_PASOS` | `1` | Déjela activa |
| `ANTHROPIC_API_KEY` | vacía | Opcional: opinión del especialista con Claude en la clasificación |

## 3. Lo que NO va en variables de entorno

Se configura dentro de la aplicación y se guarda en la base de datos:

- **Empresa** (Configuración → Empresa): nombre, logo, país, idioma, moneda,
  zona horaria, formato de fecha y reglas de negocio (si el proveedor puede
  finalizar, si una posición puede ir en varias facturas, días de alerta…).
- **Marca y documentos** (Configuración → Empresa): color, nombre del sistema,
  textos de la pantalla de ingreso, papel de los PDF (carta o A4) y las
  declaraciones legales de la factura y la lista de empaque.
- **Terminología** (Configuración → Empresa): reemplaza cualquier texto del
  sistema por las palabras de la empresa, en español e inglés.
- **Usuarios, roles y permisos** (Usuarios y accesos), incluidos los datos
  que cada rol puede ver.
- **Datos maestros**: proveedores, marcas, sociedades, centros, almacenes,
  puertos, países, tipos de empaque, transportistas, lead times y las listas de
  valores (unidades de medida, monedas, incoterms, modos de transporte, tipos…).
- **Clasificación arancelaria**: arancel, países, familias de producto y reglas.

Las variables `POSICION_EN_VARIAS_FACTURAS`, `PROVEEDOR_PUEDE_FINALIZAR`, etc.
solo son el valor de fábrica mientras la empresa no los cambie en pantalla.

## 4. Primer arranque

1. Cree la base PostgreSQL vacía.
2. Defina las variables de la sección 1.
3. Arranque el contenedor (`Dockerfile`). Al iniciar:
   - se aplican todas las migraciones (`backend/alembic`);
   - se cargan el motor de clasificación y los datos oficiales del arancel;
   - se crean la empresa, los roles de fábrica y el primer administrador.
4. Entre con `ADMIN_EMAIL` y la contraseña inicial; el sistema pide una nueva.
5. Quite `ADMIN_PASSWORD` de las variables.
6. En Configuración → Empresa complete los datos, el logo y las reglas.
7. Cargue los datos maestros (Datos maestros → Cargar) y los usuarios.

Crear o restablecer un administrador en cualquier momento (escribe una
contraseña temporal en pantalla):

```bash
python -m app.instalacion.inicial admin@miempresa.com +50370000000
```

## 5. Actualizaciones

Cada nueva versión aplica sus migraciones al arrancar; nunca borra datos.
Antes de actualizar:

1. Respaldo de la base y de `UPLOAD_DIR` con `ops/respaldo.sh` (ver §8).
2. Despliegue la versión nueva.
3. Revise el registro del arranque: una migración que no puede aplicarse
   detiene el arranque sin cambiar nada (por ejemplo, la 0037 se detiene si
   la base tuviera datos de más de una empresa).

## 6. Seguridad ya incluida (no requiere cambios)

- Contraseñas con PBKDF2-SHA256 (600 000 iteraciones; los hashes anteriores
  se actualizan solos al iniciar sesión), política de contraseñas, bloqueo
  por intentos (que no revela qué cuentas existen) y verificación en dos
  pasos por SMS.
- Sesión en cookie `httpOnly`, `Secure` y `SameSite=Strict`, con vencimiento
  por inactividad; protección contra peticiones de otros sitios (CSRF).
- Encabezados de seguridad (CSP, HSTS con `COOKIE_SEGURA=1`, `X-Frame-Options`, `nosniff`).
- Permisos por rol revisados en el servidor en cada petición; el proveedor
  solo ve lo suyo.
- Archivos subidos: límite de tamaño aunque la petición no lo declare, tipo
  decidido por el contenido (no por la extensión), imágenes validadas y
  Excel revisado contra bombas de descompresión antes de abrirlo.
- Exportaciones a Excel sin fórmulas ejecutables (un dato que empieza con «=»
  queda como texto).
- Bitácora de los cambios críticos (documentos, aprobaciones, datos maestros,
  usuarios, roles y configuración), consultable en Usuarios y accesos →
  Bitácora.
- Documentación interactiva de la API (`/docs`) apagada fuera de la demostración.
- El contenedor corre sin privilegios de administrador.

## 7. Organizaciones (multiempresa)

- La instalación arranca con una organización (la de `EMPRESA_NOMBRE`) y su
  primer administrador, que también administra la plataforma.
- Configuración → Plataforma → Organizaciones: crear una organización (con
  su primer administrador y contraseña temporal), suspenderla (sus usuarios
  dejan de entrar) o entrar a ella para dar soporte.
- El usuario de PostgreSQL de la aplicación **no debe ser superusuario**: un
  superusuario se salta las políticas de seguridad por fila (RLS) que aíslan
  a las organizaciones. Basta con que sea dueño de la base.
- Con más de una organización activa, el arancel oficial, el motor de
  clasificación, los países y los acuerdos comerciales (datos compartidos)
  solo los cambia la administración de la plataforma.

## 8. Operación

- **Salud**: `GET /api/salud` (para el monitoreo de la plataforma).
- **Respaldo diario** de la base y de `UPLOAD_DIR` con `ops/respaldo.sh`
  (carpeta con fecha, huella SHA-256 de cada parte y borrado de los respaldos
  de más de `RETENCION_DIAS`, 14 por defecto). Guarde la carpeta de respaldos
  fuera del servidor (otro disco, otra región o un almacenamiento de objetos).

  Necesita `pg_dump`/`pg_restore` de PostgreSQL 16 donde corra. Desde una
  copia del repositorio en el servidor:

  ```bash
  # cron, todas las noches a las 2:00
  0 2 * * * cd /opt/facturacion && DATABASE_URL=postgresql://... UPLOAD_DIR=/data/archivos DESTINO=/respaldos ops/respaldo.sh
  ```

  Con `docker compose`, en un contenedor de PostgreSQL unido a la red del
  proyecto y al volumen de archivos:

  ```bash
  docker run --rm --network facturacion_default -v facturacion_archivos:/data/archivos \
    -v /respaldos:/respaldos -v "$PWD/ops":/ops postgres:16 env \
    DATABASE_URL=postgresql://facturas:$POSTGRES_PASSWORD@db/facturas UPLOAD_DIR=/data/archivos \
    DESTINO=/respaldos bash /ops/respaldo.sh
  ```

- **Recuperación** con `ops/restaurar.sh <carpeta>`: verifica las huellas,
  pide `CONFIRMAR=si`, reemplaza la base en una sola transacción y devuelve
  los archivos. Detenga la aplicación antes y arránquela después (aplica las
  migraciones que falten). Con un respaldo diario se pierde como máximo un
  día de trabajo (RPO); restaurar toma minutos (RTO), según el tamaño de la
  base. **Pruebe una restauración** en un servidor aparte al menos una vez
  por trimestre.
- **Limpieza automática**: cada hora el servidor borra las claves de
  idempotencia de más de un día, las sesiones vencidas hace más de 30 días,
  los códigos de dos pasos vencidos y los permisos de edición vencidos.
- **Un solo proceso** por contenedor (el límite de intentos por IP está en
  memoria); para más carga, más contenedores detrás del balanceador.
- **Registro**: el arranque avisa si `COOKIE_SEGURA=0` o `SMS_PROVEEDOR=consola`.

## 9. Demostración

- Render: `render.yaml` levanta la demostración (`SEED_DEMO=1`).
- Docker local: `docker compose up` (usa `backend/.env.demo`). Para producción:
  `ENV_FILE=backend/.env docker compose up -d`.
- Reiniciar la demostración con sus datos de ejemplo: `SEED_DEMO=1 python -m app.instalacion.demo`
  (solo borra una base marcada como de demostración o vacía; una base con
  datos reales se rechaza)
  (se niega a correr sin `SEED_DEMO=1`).
