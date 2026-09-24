import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.exc import IntegrityError

from .config import settings
from .db import Base, SessionLocal, engine
from .routers import auth_admin, facturas, ordenes, packing, transporte, varios
from .services.common import ErrorNegocio


@asynccontextmanager
async def lifespan(_: FastAPI):
    # En producción usa migraciones (Alembic) en lugar de create_all
    Base.metadata.create_all(engine)
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    if settings.SEED_DEMO:
        from .seed import seed

        with SessionLocal() as db:
            seed(db)
    yield


app = FastAPI(title="Workspace de proveedor: facturas, packing lists y transporte", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(ErrorNegocio)
async def _error_negocio(_: Request, exc: ErrorNegocio):
    return JSONResponse(status_code=exc.status,
                        content={"mensaje": exc.mensaje, "codigo": exc.codigo, "detalle": exc.detalle})


@app.exception_handler(IntegrityError)
async def _error_integridad(_: Request, exc: IntegrityError):
    return JSONResponse(status_code=409, content={
        "mensaje": "El dato ya existe o choca con otro registro (por ejemplo, un número de factura repetido).",
        "codigo": "integridad", "detalle": None})


@app.exception_handler(RequestValidationError)
async def _error_validacion(_: Request, exc: RequestValidationError):
    detalle = [{"campo": ".".join(str(x) for x in e["loc"][1:]), "mensaje": e["msg"]} for e in exc.errors()]
    return JSONResponse(status_code=422, content={
        "mensaje": "Revisa los datos enviados.", "codigo": "datos_invalidos", "detalle": detalle})


for r in (auth_admin, ordenes, facturas, packing, transporte, varios):
    app.include_router(r.router, prefix="/api")


@app.get("/api/salud")
def salud():
    return {"ok": True}


# Sirve el frontend compilado (npm run build) desde el mismo servidor
_dist = os.path.abspath(settings.FRONTEND_DIST)
if os.path.isdir(_dist):

    @app.get("/{ruta:path}", include_in_schema=False)
    def spa(ruta: str):
        archivo = os.path.join(_dist, ruta)
        if ruta and os.path.isfile(archivo) and os.path.abspath(archivo).startswith(_dist):
            return FileResponse(archivo)
        return FileResponse(os.path.join(_dist, "index.html"))
