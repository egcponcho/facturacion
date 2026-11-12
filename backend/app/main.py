import asyncio
import inspect
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.routing import APIRoute
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.core.db import SessionLocal
from app.core.errores import ErrorNegocio
from app.core.modulos import cargar as cargar_modulos
from app.core.respuestas import RespuestaJSON

# Los módulos de app/modulos/ (cada uno con su modulo.py). main.py no conoce
# ninguno por nombre: arma la API con lo que declara cada contrato.
MODULOS = cargar_modulos()


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Arranque: revisa la configuración, aplica las migraciones pendientes y
    deja lista la instalación. Demostración y producción siguen el mismo
    camino; la demostración solo agrega sus datos de ejemplo a una base vacía."""
    settings.validar()
    from app.instalacion import migraciones
    from app.instalacion.inicial import preparar_instalacion

    migraciones.actualizar()
    from app.core import cambios

    cambios.activar()  # la tabla de versiones ya existe: desde aquí se cuentan los cambios
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    with SessionLocal() as db:
        if settings.SEED_DEMO:
            from app.instalacion.demo import seed

            seed(db)
        preparar_instalacion(db)
    tareas = [asyncio.create_task(_limpieza_periodica()), asyncio.create_task(cambios.difusor.correr())]
    tareas += [asyncio.create_task(tarea()) for m in MODULOS for tarea in m.tareas]
    yield
    for tarea in tareas:
        tarea.cancel()


async def _limpieza_periodica():
    """Purga las tablas técnicas al arrancar y luego cada hora."""
    from app.instalacion.mantenimiento import INTERVALO_SEG, purgar

    def una_vez():
        with SessionLocal() as db:
            purgar(db)

    while True:
        try:
            await asyncio.to_thread(una_vez)
        except Exception:  # la limpieza nunca debe tumbar el servidor
            logging.getLogger("mantenimiento").exception("Falló la limpieza periódica")
        await asyncio.sleep(INTERVALO_SEG)


# Documentación de la API: una sección por módulo (la de su contrato) más la
# del sistema. Se publica en la demostración o con API_DOCS=1.
ETIQUETAS: list[dict] = []
for _m in sorted(MODULOS, key=lambda m: bool(m.etiqueta)):  # describe la sección el módulo que le da nombre
    if _m.rutas() and all(e["name"] != _m.seccion for e in ETIQUETAS):
        ETIQUETAS.append({"name": _m.seccion, "description": _m.descripcion})
ETIQUETAS.append({"name": "Sistema", "description": "Estado del servidor y módulos instalados."})
_docs = settings.API_DOCS
app = FastAPI(title="Supplier workspace: invoices, packing lists and transport", lifespan=lifespan,
              description="API del espacio de trabajo con proveedores. Convenciones (sesión, encabezados, errores, "
                          "paginación, idioma) en docs/API.md.",
              openapi_tags=ETIQUETAS,
              docs_url="/docs" if _docs else None, redoc_url="/redoc" if _docs else None,
              openapi_url="/openapi.json" if _docs else None, default_response_class=RespuestaJSON)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def _respuestas_condicionales(request: Request, call_next):
    """GET de la API: ETag por tablas leídas y 304 sin consultar si nada cambió (app/core/cambios.py)."""
    from app.core import cambios

    return await cambios.middleware(request, call_next)


@app.middleware("http")
async def _limite_tamano(request: Request, call_next):
    """Rechaza peticiones más grandes que MAX_SUBIDA_MB antes de leerlas."""
    largo = request.headers.get("content-length")
    if largo and largo.isdigit() and int(largo) > settings.MAX_SUBIDA_MB * 1024 * 1024:
        return JSONResponse(status_code=413, content={
            "mensaje": f"The file is too large (maximum {settings.MAX_SUBIDA_MB} MB).", "codigo": "muy_grande", "detalle": None})
    return await call_next(request)


@app.middleware("http")
async def _encabezados_seguridad(request: Request, call_next):
    """Encabezados que endurecen el navegador: sin incrustar la app en otros
    sitios, sin adivinar tipos, sin filtrar la URL y solo recursos propios."""
    resp = await call_next(request)
    h = resp.headers
    h.setdefault("X-Content-Type-Options", "nosniff")
    h.setdefault("X-Frame-Options", "DENY")
    h.setdefault("Referrer-Policy", "same-origin")
    h.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    if not request.url.path.startswith(("/docs", "/redoc")):
        h.setdefault("Content-Security-Policy",
                     "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; "
                     "font-src 'self' data:; "
                     "script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; "
                     "form-action 'self'")
    if request.url.path.startswith("/api/"):
        h.setdefault("Cache-Control", "no-store")
    if settings.COOKIE_SEGURA:
        h.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return resp


@app.exception_handler(ErrorNegocio)
async def _error_negocio(_: Request, exc: ErrorNegocio):
    return JSONResponse(status_code=exc.status,
                        content={"mensaje": exc.mensaje, "codigo": exc.codigo, "detalle": exc.detalle})


@app.exception_handler(IntegrityError)
async def _error_integridad(_: Request, exc: IntegrityError):
    texto = str(getattr(exc, "orig", exc)).lower()
    if "foreign key" in texto:  # se quiso borrar o cambiar algo que otros registros usan (p. ej. etiquetas generadas)
        return JSONResponse(status_code=409, content={
            "mensaje": "Other records use this one (for example, labels already generated): it cannot be removed or changed.",
            "codigo": "en_uso", "detalle": None})
    return JSONResponse(status_code=409, content={
        "mensaje": "The value already exists or conflicts with another record.", "codigo": "integridad", "detalle": None})


@app.exception_handler(ValidationError)
async def _error_modelo(_: Request, exc: ValidationError):
    """Datos guardados que no cumplen su forma (un parámetro viejo, por ejemplo): 422 y no un error del servidor."""
    detalle = [{"campo": ".".join(str(x) for x in e["loc"]), "mensaje": e["msg"]} for e in exc.errors()]
    return JSONResponse(status_code=422, content={
        "mensaje": "Check the data you sent.", "codigo": "datos_invalidos", "detalle": detalle})


@app.exception_handler(RequestValidationError)
async def _error_validacion(_: Request, exc: RequestValidationError):
    detalle = [{"campo": ".".join(str(x) for x in e["loc"][1:]), "mensaje": e["msg"]} for e in exc.errors()]
    return JSONResponse(status_code=422, content={
        "mensaje": "Check the data you sent.", "codigo": "datos_invalidos", "detalle": detalle})


# Rutas de cada módulo, todas bajo /api, con la sección de su contrato
RUTAS = [(router, m.seccion) for m in MODULOS for router in m.rutas()]


def _resumir(router):
    """La primera oración del docstring de cada ruta es su resumen en la
    documentación (el docstring completo queda como descripción)."""
    for ruta in router.routes:
        doc = inspect.cleandoc(getattr(ruta, "endpoint", None).__doc__ or "") if isinstance(ruta, APIRoute) else ""
        if doc and not ruta.summary:
            ruta.summary = " ".join(doc.partition("\n\n")[0].split()).partition(". ")[0].rstrip(".")


for _router, _seccion in RUTAS:
    _resumir(_router)
    app.include_router(_router, prefix="/api", tags=[_seccion])


_openapi_base = app.openapi


def _openapi():
    """Esquema OpenAPI sin repetir como descripción el resumen de una ruta
    cuyo docstring es una sola oración."""
    if app.openapi_schema is None:
        for operaciones in _openapi_base()["paths"].values():
            for op in operaciones.values():
                if " ".join(op.get("description", "").split()).rstrip(".") == op.get("summary"):
                    op.pop("description", None)
    return app.openapi_schema


app.openapi = _openapi


@app.get("/api/salud", tags=["Sistema"], summary="Estado del servidor")
def salud():
    return {"ok": True}


@app.get("/api/modulos", tags=["Sistema"], summary="Módulos instalados")
def modulos():
    """Los módulos de esta instalación, como los declara su contrato (app/modulos/<clave>/modulo.py)."""
    return [m.resumen() for m in MODULOS]


# Sirve el frontend compilado (npm run build) desde el mismo servidor
_dist = os.path.abspath(settings.FRONTEND_DIST)
if os.path.isdir(_dist):

    @app.get("/{ruta:path}", include_in_schema=False)
    def spa(ruta: str):
        archivo = os.path.abspath(os.path.join(_dist, ruta))
        if ruta and os.path.isfile(archivo) and os.path.commonpath([archivo, _dist]) == _dist:
            return FileResponse(archivo)
        return FileResponse(os.path.join(_dist, "index.html"))
