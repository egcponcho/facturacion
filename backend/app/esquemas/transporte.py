"""Transporte: embarques, unidades de carga, eventos y recolección.
"""
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


class EmbarqueIn(BaseModel):
    tipo_transporte: Literal["MARITIMO", "AEREO", "TERRESTRE"] = "MARITIMO"
    documento_numero: str | None = None
    transportista_id: int | None = None
    puerto_origen: str | None = None
    puerto_destino: str | None = None
    centro: str | None = None
    etd: date | None = None
    eta: date | None = None
    observaciones: str | None = None


class EmbarquePatch(BaseModel):
    tipo_transporte: Literal["MARITIMO", "AEREO", "TERRESTRE"] | None = None
    documento_numero: str | None = None
    transportista_id: int | None = None
    puerto_origen: str | None = None
    puerto_destino: str | None = None
    centro: str | None = None
    etd: date | None = None
    eta: date | None = None
    observaciones: str | None = None
    motivo: str | None = None


class Paletizar(BaseModel):
    version: int
    grupo_ids: list[int] = Field(min_length=1)
    pallet_id: int | None = None  # None = contenedor nuevo con estas medidas
    tipo_empaque_id: int | None = None  # tipo del contenedor nuevo (por defecto el de soporte, p. ej. pallet)
    num: int | None = Field(default=None, gt=0)  # unidades del contenedor nuevo
    largo: float | None = None
    ancho: float | None = None
    alto: float | None = None
    peso_tara: float | None = None


class Despaletizar(BaseModel):
    version: int
    grupo_ids: list[int] = []
    pallet_id: int | None = None


class PalletPatch(BaseModel):
    version: int
    largo: float | None = None
    ancho: float | None = None
    alto: float | None = None
    peso_tara: float | None = None


class UnidadIn(BaseModel):
    tipo: str
    numero: str | None = None
    sello: str | None = None


class UnidadPatch(BaseModel):
    tipo: str | None = None
    numero: str | None = None
    sello: str | None = None


class AsignarPL(BaseModel):
    pl_ids: list[int] = Field(min_length=1)
    motivo: str | None = None  # para mover una lista de otra unidad


class Recoleccion(BaseModel):
    pl_ids: list[int] = Field(min_length=1)
    fecha: date | None = None  # None = quitar la marca


class PLIds(BaseModel):
    pl_ids: list[int] = Field(min_length=1)
    motivo: str | None = None


class EventoIn(BaseModel):
    tipo: str = Field(max_length=20)  # un hito de la lista evento_embarque (se valida contra su estado)
    fecha: datetime
    ubicacion: str | None = None
    observacion: str | None = None
