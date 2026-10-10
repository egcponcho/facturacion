"""Rutas de la plataforma: organizaciones."""
from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.modulos.plataforma import organizaciones as svc
from app.web.rutas import Clave, Db, User, ejecutar

router = APIRouter()


class OrganizacionIn(BaseModel):
    codigo: str = Field(max_length=20)
    nombre: str = Field(max_length=200)
    pais: str | None = Field(default=None, max_length=2)
    admin_email: str = Field(max_length=200)
    admin_nombre: str | None = Field(default=None, max_length=200)
    admin_telefono: str | None = Field(default=None, max_length=30)


class OrganizacionPatch(BaseModel):
    nombre: str | None = Field(default=None, max_length=200)
    activa: bool | None = None


class Entrar(BaseModel):
    organizacion_id: int | None = None


@router.get("/plataforma/organizaciones")
def listar(db: Db, user: User):
    """Organizaciones de la plataforma con su número de usuarios. Solo administración de plataforma."""
    return svc.listar(db, user)


@router.post("/plataforma/organizaciones")
def crear(datos: OrganizacionIn, db: Db, user: User, clave: Clave = None):
    """Crea una organización con sus datos de partida y su primer administrador, con clave temporal."""
    return ejecutar(db, user, clave, lambda: svc.crear(db, user, datos))


@router.patch("/plataforma/organizaciones/{organizacion_id}")
def actualizar(organizacion_id: int, datos: OrganizacionPatch, db: Db, user: User, clave: Clave = None):
    """Renombra, suspende o reactiva una organización. Solo administración de plataforma."""
    return ejecutar(db, user, clave, lambda: svc.actualizar(db, user, organizacion_id, datos))


@router.post("/plataforma/entrar")
def entrar(datos: Entrar, request: Request, db: Db, user: User):
    """Trabajar en otra organización (o volver a la propia)."""
    r = svc.entrar(db, user, request.state.token, datos.organizacion_id)
    db.commit()
    return r
