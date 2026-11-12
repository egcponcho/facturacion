# Operación logística: OC → factura → empaque → embarque → bodega

Sistema para la operación de compras e importaciones de una empresa. Lo usan el equipo interno y los proveedores:

1. Las órdenes de compra llegan del ERP o se crean en un asistente.
2. Cada proveedor arma sus facturas a partir de las líneas de las OC y las reparte en listas de empaque y cajas.
3. Importaciones asigna esas listas a unidades de carga y sigue el embarque hasta la recepción en bodega.

El sistema no trae nada propio de un rubro ni de un país. Los productos, sus variantes, los empaques, las listas de valores, las reglas y los textos se configuran desde la aplicación, y cada empresa apaga los módulos que no usa.

- **Servidor:** Python 3.12, FastAPI, SQLAlchemy 2 y Alembic. Usa PostgreSQL en producción y SQLite para desarrollo y pruebas.
- **Interfaz:** Vue 3 y Vite, sin librerías de componentes ni de gráficas.
- **Varias empresas:** una instalación sirve a varias organizaciones con sus datos aislados. El aislamiento se hace en la capa de datos y, en PostgreSQL, también con seguridad por fila.
- **Idiomas:** la interfaz, los mensajes y los documentos (PDF y Excel) están en español e inglés. El código y sus comentarios están en español.

## Cómo empezar

### En su computadora (SQLite, sin instalar una base de datos)

```bash
# Terminal 1: API en http://localhost:8000 (documentación en /docs)
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
SEED_DEMO=1 COOKIE_SEGURA=0 uvicorn app.main:app --reload
# Windows (PowerShell): $env:SEED_DEMO="1"; $env:COOKIE_SEGURA="0"; uvicorn app.main:app --reload

# Terminal 2: interfaz en http://localhost:5173 (Vite pasa /api al puerto 8000)
cd frontend
npm install
npm run dev
```

Al arrancar se aplican las migraciones. Si la base está vacía, se cargan los datos de demostración (`SEED_DEMO=1`). `COOKIE_SEGURA=0` hace falta porque `http://localhost` no usa https. Sin `SECRET_KEY`, la demostración usa una clave al azar en cada arranque, así que las sesiones se cierran al reiniciar el servidor.

Para volver a los datos de ejemplo: `SEED_DEMO=1 python -m app.instalacion.demo` (desde `backend`).

### Con Docker y PostgreSQL

```bash
docker compose up --build                     # demostración (backend/.env.demo)
ENV_FILE=backend/.env docker compose up -d    # producción: copie backend/.env.example a backend/.env y complételo
```

Todo queda en http://localhost:8000: la API también sirve la interfaz compilada.

### En la nube (Render)

`render.yaml` crea la base PostgreSQL y el servicio web desde el `Dockerfile`, y despliega la rama `main`. En Render, entre a **Blueprints → New Blueprint Instance**, elija este repositorio y aplique. El blueprint levanta la demostración. Para datos reales, siga [docs/PRODUCCION.md](docs/PRODUCCION.md).

La misma imagen corre en Railway, Fly.io o Cloud Run. Basta con definir `DATABASE_URL` y `SECRET_KEY`; el puerto se toma de `PORT`.

### Cuentas de la demostración

La contraseña de todas es `Supplier2026`. La demostración no envía SMS: el código de verificación aparece en la pantalla de ingreso.

| Correo | Rol |
|---|---|
| admin@demo.com | Administrador |
| interno@demo.com | Equipo de importaciones |
| tnf@demo.com | Proveedor |
| vans@demo.com | Proveedor |

## Documentación

| Documento | Para qué |
|---|---|
| [docs/FUNCIONES.md](docs/FUNCIONES.md) | Qué hace el sistema, pantalla por pantalla: acceso, roles, OC, facturas, empaque, embarques, reglas configurables |
| [docs/FLUJOS.md](docs/FLUJOS.md) | Estados y pasos de la OC, la factura, la lista de empaque, el embarque y la recepción |
| [docs/ARQUITECTURA.md](docs/ARQUITECTURA.md) | Cómo está hecho: capas, contrato de módulos, registros, multiempresa, configuración, cómo agregar un módulo |
| [docs/MODULOS.md](docs/MODULOS.md) | Cada módulo, su API y de qué otros depende (se genera desde el código) |
| [docs/API.md](docs/API.md) | Convenciones de la API: sesión, encabezados, errores, listas y filtros |
| [docs/PRODUCCION.md](docs/PRODUCCION.md) | Variables de entorno, primer arranque, actualizaciones, respaldos y seguridad |
| [docs/INTEGRACIONES.md](docs/INTEGRACIONES.md) | Conectar un ERP u otro sistema |
| [docs/PRODUCTO_GENERICO.md](docs/PRODUCTO_GENERICO.md), [docs/GRUPOS_PRODUCTO.md](docs/GRUPOS_PRODUCTO.md), [docs/EMPAQUE_RECETAS.md](docs/EMPAQUE_RECETAS.md) | Productos y variantes de cualquier tipo, el árbol de familias y las recetas y reglas de empaque |
| [docs/ETIQUETADO.md](docs/ETIQUETADO.md), [docs/clasificacion/](docs/clasificacion/arquitectura.md) | Manual de los módulos de etiquetado y clasificación arancelaria |
| [docs/DISENO.md](docs/DISENO.md), [design-system/facturacion/MASTER.md](design-system/facturacion/MASTER.md) | Piezas de la interfaz y su estilo |

## Estructura

```
backend/
  app/main.py        arma la API con el contrato de cada módulo
  app/core/          núcleo: configuración, base de datos, contrato de módulos, registros, reglas, listas
  app/modelos/       tablas (SQLAlchemy), un archivo por dominio
  app/modulos/<m>/   un módulo: modulo.py (su contrato), servicios y api.py
  app/instalacion/   migraciones al arrancar, datos incluidos, primer administrador, demostración
  alembic/           migraciones de la base
  scripts/           extracción de textos y generación de docs/MODULOS.md
  tests/             pruebas (pytest)
frontend/src/
  nucleo/            cliente de la API, formatos, marca, lista de módulos del menú
  componentes/       piezas compartidas: tablas, filtros, íconos, gráficas
  estilos/           hojas de estilo por tema (tokens.css primero)
  modulos/<m>/       vistas/ (pantallas) y componentes/ de cada módulo
ops/                 respaldo y restauración
```

[docs/ARQUITECTURA.md](docs/ARQUITECTURA.md) explica cada parte y las reglas entre ellas.

## Pruebas y calidad

```bash
cd backend
pytest                       # todas las pruebas, en SQLite
ruff check . && alembic check   # alembic check compara los modelos con la base de DATABASE_URL, ya migrada
TEST_DATABASE_URL=postgresql+psycopg://usuario:clave@localhost/pruebas pytest   # en PostgreSQL (incluye seguridad por fila y concurrencia)

cd frontend
npm run lint && npm run build
npm run e2e                  # con la demostración corriendo: abre todas las pantallas en el navegador
```

Algunas pruebas cuidan que el código siga ordenado. `test_dependencias.py` revisa qué puede importar cada parte. `test_documentacion.py` revisa que `docs/MODULOS.md` esté al día y que existan los documentos citados en el código. `test_i18n.py` revisa que todos los textos estén traducidos.

Después de cambiar textos, extraiga las claves y agregue las traducciones en `es.json`:

```bash
cd backend && python scripts/i18n_extraer.py
cd frontend && node scripts/i18n-extraer.mjs
```
