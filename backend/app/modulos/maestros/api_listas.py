"""Ruta de las listas de valores de la empresa (para los formularios y filtros)."""
from fastapi import APIRouter

from app.core import listas
from app.web.rutas import User

router = APIRouter()


@router.get("/listas")
def valores_listas(user: User):
    """Valores activos de cada lista (ya cargados para la petición)."""
    return {k: listas.valores(k) for k in listas.LISTAS}
