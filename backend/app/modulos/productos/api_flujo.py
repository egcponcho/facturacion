"""Rutas del flujo de clasificación (quién hace qué con la ficha técnica).
"""
from fastapi import APIRouter

from app.modulos.productos import flujo
from app.web.rutas import Clave, Db, User, ejecutar

router = APIRouter()


@router.get("/flujo-clasificacion")
def flujo_clasificacion(db: Db, user: User):
    return flujo.leer(db, user)


@router.put("/flujo-clasificacion")
def guardar_flujo_clasificacion(datos: dict[str, bool], db: Db, user: User, clave: Clave = None):
    return ejecutar(db, user, clave, lambda: flujo.guardar(db, user, datos))
