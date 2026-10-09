import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.core.db import SessionLocal
from app.core.errores import ErrorNegocio
from app.modulos.acceso import api as acceso_api
from app.modulos.acceso import visibilidad
from app.modulos.clasificacion import api as clasificacion_api
from app.modulos.clasificacion import api_conocimiento as clasificacion_api_conocimiento
from app.modulos.compras import api as compras_api
from app.modulos.compras import api_flujo as compras_api_flujo
from app.modulos.comun import api as comun_api
from app.modulos.empaque import api as empaque_api
from app.modulos.empaque import api_plantillas as empaque_api_plantillas
from app.modulos.empresa import api as empresa_api
from app.modulos.facturacion import api as facturacion_api
from app.modulos.maestros import api as maestros_api
from app.modulos.maestros import api_listas as maestros_api_listas
from app.modulos.plataforma import api as plataforma_api
from app.modulos.productos import api as productos_api
from app.modulos.productos import api_flujo as productos_api_flujo
from app.modulos.seguimiento import api as seguimiento_api
from app.modulos.transporte import api as transporte_api
from app.modulos.transporte import api_leadtimes as transporte_api_leadtimes


class RespuestaJSON(JSONResponse):
    """Respuesta de la API: quita los datos que el rol del usuario no ve
    (modulos/acceso/visibilidad.py) antes de enviarlos."""

    def render(self, content) -> bytes:
        return super().render(visibilidad.quitar(content))


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Arranque: revisa la configuración, aplica las migraciones pendientes y
    deja lista la instalación. Demostración y producción siguen el mismo
    camino; la demostración solo agrega sus datos de ejemplo a una base vacía."""
    settings.validar()
    from app.instalacion import migraciones
    from app.instalacion.inicial import preparar_instalacion

    migraciones.actualizar()
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    with SessionLocal() as db:
        if settings.SEED_DEMO:
            from app.instalacion.demo import seed

            seed(db)
        preparar_instalacion(db)
    tarea = asyncio.create_task(_limpieza_periodica())
    yield
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


# La documentación interactiva de la API solo en la demostración: en
# producción no se publica el mapa de rutas.
_docs = settings.SEED_DEMO
app = FastAPI(title="Supplier workspace: invoices, packing lists and transport", lifespan=lifespan,
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
                     "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline' "
                     "https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; "
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
    return JSONResponse(status_code=409, content={
        "mensaje": "The value already exists or conflicts with another record (for example, a repeated invoice number).",
        "codigo": "integridad", "detalle": None})


@app.exception_handler(RequestValidationError)
async def _error_validacion(_: Request, exc: RequestValidationError):
    detalle = [{"campo": ".".join(str(x) for x in e["loc"][1:]), "mensaje": e["msg"]} for e in exc.errors()]
    return JSONResponse(status_code=422, content={
        "mensaje": "Check the data you sent.", "codigo": "datos_invalidos", "detalle": detalle})


# Rutas de cada módulo, todas bajo /api. El orden se conserva: una ruta fija
# (p. ej. /seguimiento/exportar) va antes que una con parámetro del mismo prefijo.
RUTAS = (
    clasificacion_api, acceso_api, productos_api_flujo, empresa_api, maestros_api, clasificacion_api_conocimiento,
    compras_api, compras_api_flujo, facturacion_api, empaque_api, productos_api, transporte_api, comun_api, seguimiento_api,
    transporte_api_leadtimes, empaque_api_plantillas, maestros_api_listas, plataforma_api,
)
for modulo in RUTAS:
    app.include_router(modulo.router, prefix="/api")


@app.get("/api/salud")
def salud():
    return {"ok": True}


# Sirve el frontend compilado (npm run build) desde el mismo servidor
_dist = os.path.abspath(settings.FRONTEND_DIST)
if os.path.isdir(_dist):

    @app.get("/{ruta:path}", include_in_schema=False)
    def spa(ruta: str):
        archivo = os.path.abspath(os.path.join(_dist, ruta))
        if ruta and os.path.isfile(archivo) and os.path.commonpath([archivo, _dist]) == _dist:
            return FileResponse(archivo)
        return FileResponse(os.path.join(_dist, "index.html"))
