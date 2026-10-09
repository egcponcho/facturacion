"""Listas de empaque, su estructura física y cajas y plantillas de caja.
"""
from typing import Literal

from pydantic import BaseModel, Field

from app.esquemas.comun import Cant, Cantidad, CantidadCero


class LineaFacturaCantidad(BaseModel):
    factura_linea_id: int
    cantidad: Cantidad


class PLCrear(BaseModel):
    lineas: list[LineaFacturaCantidad] | None = None  # None = todos los pendientes


class PLAgregar(BaseModel):
    version: int
    lineas: list[LineaFacturaCantidad] | None = None


class MovCantidad(BaseModel):
    pl_linea_id: int
    cantidad: Cantidad


class PLMover(BaseModel):
    version: int
    movimientos: list[MovCantidad] = Field(min_length=1)
    destino_pl_id: int | None = None  # None = nuevo PL


class PLQuitar(BaseModel):
    version: int
    movimientos: list[MovCantidad] = Field(min_length=1)


class MovCajas(BaseModel):
    grupo_id: int
    num_cajas: int = Cant


class PLMoverCajas(BaseModel):
    version: int
    grupos: list[MovCajas] = Field(min_length=1)
    destino_pl_id: int | None = None


class FilaEmpaque(BaseModel):
    pl_linea_id: int
    # Opcional si la fila tiene casepack o es prepack: la cantidad por caja la
    # da el artículo y la plantilla solo aporta medidas y pesos.
    plantilla_id: int | None = None


class EmpaquePrevia(BaseModel):
    """Empaque automático: cada fila con su propia plantilla."""
    filas: list[FilaEmpaque] = Field(min_length=1)
    reemplazar: bool = False


class EmpaqueAplicar(EmpaquePrevia):
    version: int
    sobrante: Literal["caja_parcial", "sin_caja"] = "caja_parcial"


class ValoresCaja(BaseModel):
    largo: float | None = Field(default=None, ge=0)
    ancho: float | None = Field(default=None, ge=0)
    alto: float | None = Field(default=None, ge=0)
    tara: float | None = Field(default=None, ge=0)  # kg de una unidad de empaque vacía
    # Neto por unidad escrito a mano: solo se usa si falta el peso de algún artículo
    peso_neto_caja: float | None = Field(default=None, ge=0)
    tipo_empaque_id: int | None = None
    observacion: str | None = None


class ItemCaja(BaseModel):
    pl_linea_id: int
    cantidad_por_caja: Cantidad


class CajaManual(ValoresCaja):
    version: int
    items: list[ItemCaja] = Field(min_length=1)
    num_cajas: int = Cant
    plantilla_id: int | None = None


class EditarCajas(ValoresCaja):
    version: int
    grupo_ids: list[int] = Field(min_length=1)
    num_cajas: int | None = Field(default=None, gt=0)
    desde_plantilla_id: int | None = None
    confirmar_pesos: bool = False


class PLNumeroIn(BaseModel):
    version: int | None = None
    numero: str = Field(min_length=1, max_length=40)


class InnerPackIn(BaseModel):
    version: int | None = None
    inner_pack: int | None = Field(None, ge=1, le=100000)  # vacío: sin inner pack


class EliminarCajas(BaseModel):
    version: int
    grupo_ids: list[int] = Field(min_length=1)


class GuardarPlantilla(BaseModel):
    nombre: str = Field(min_length=1, max_length=100)


class RecepcionItem(BaseModel):
    pl_linea_id: int
    cantidad_recibida: CantidadCero
    cantidad_danada: CantidadCero = 0
    observacion: str | None = None


class RecepcionIn(BaseModel):
    lineas: list[RecepcionItem] = Field(min_length=1)


class PlantillaIn(BaseModel):
    proveedor_id: int | None = None
    nombre: str = Field(min_length=1, max_length=100)
    cantidad_por_caja: Cantidad
    unidad: str = Field("PAR", max_length=5)  # una de modulos/maestros/unidades.py (se valida al guardar)
    largo: float | None = Field(default=None, ge=0)
    ancho: float | None = Field(default=None, ge=0)
    alto: float | None = Field(default=None, ge=0)
    tara: float | None = Field(default=None, ge=0)  # solo el empaque: el neto sale del peso de los artículos
    tipo_empaque_id: int | None = None


class PlantillaPatch(BaseModel):
    nombre: str | None = None
    cantidad_por_caja: Cantidad | None = None
    unidad: str | None = Field(None, max_length=5)
    largo: float | None = Field(default=None, ge=0)
    ancho: float | None = Field(default=None, ge=0)
    alto: float | None = Field(default=None, ge=0)
    tara: float | None = Field(default=None, ge=0)
    tipo_empaque_id: int | None = None
    activa: bool | None = None
