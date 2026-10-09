"""Facturas comerciales y sus líneas.
"""
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from app.esquemas.comun import Cantidad


class PosicionCantidad(BaseModel):
    posicion_id: int
    cantidad: Cantidad


class FacturaCrear(BaseModel):
    proveedor_id: int | None = None
    lineas: list[PosicionCantidad] = Field(min_length=1)
    numero: str | None = None
    fecha: date | None = None


class FacturaAgregar(BaseModel):
    version: int
    lineas: list[PosicionCantidad] = Field(min_length=1)


class FacturaCabecera(BaseModel):
    version: int
    numero: str | None = None
    fecha: date | None = None
    incoterm: str | None = None
    condiciones: str | None = None
    observaciones: str | None = None


class CambioLinea(BaseModel):
    linea_id: int
    cantidad: Cantidad | None = None
    precio_unitario: float | None = Field(default=None, ge=0)
    motivo_precio: str | None = None
    pais_origen: str | None = None
    partida_arancelaria: str | None = None
    descripcion_comercial: str | None = None


class FacturaEditarLineas(BaseModel):
    version: int
    cambios: list[CambioLinea] = Field(min_length=1)
    # error: si una reducción choca con lo asignado a PL, se pregunta
    # automatico: libera la cantidad sin caja de los PL (del más nuevo al más viejo)
    ajuste_pl: Literal["error", "automatico"] = "error"


class FacturaEliminarLineas(BaseModel):
    version: int
    linea_ids: list[int] = Field(min_length=1)
    confirmar_cascada: bool = False


class ConMotivo(BaseModel):
    version: int | None = None
    motivo: str | None = None


class Finalizar(BaseModel):
    version: int
    incluir_packing_lists: bool = False
