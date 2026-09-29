"""Cuerpos de las peticiones. Las respuestas se arman como dicts en los servicios."""
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

Cant = Field(gt=0)


# ---- Auth / admin -----------------------------------------------------------
class LoginIn(BaseModel):
    email: str = Field(max_length=200)
    password: str = Field(max_length=200)


class DesafioIn(BaseModel):
    desafio: str = Field(max_length=100)


class VerificarIn(DesafioIn):
    codigo: str = Field(max_length=10)


class PasswordIn(BaseModel):
    actual: str = Field(max_length=200)
    nueva: str = Field(max_length=200)


class ProveedorIn(BaseModel):
    codigo: str = Field(min_length=1, max_length=30)
    nombre: str = Field(min_length=1, max_length=200)
    activo: bool = True


class ProveedorPatch(BaseModel):
    nombre: str | None = None
    activo: bool | None = None


class UsuarioIn(BaseModel):
    email: str
    nombre: str
    rol: Literal["admin", "interno", "proveedor"]
    proveedor_id: int | None = None
    password: str = Field(max_length=200)
    telefono: str | None = None
    dos_pasos: bool = True


class UsuarioPatch(BaseModel):
    nombre: str | None = None
    rol: Literal["admin", "interno", "proveedor"] | None = None
    proveedor_id: int | None = None
    password: str | None = Field(default=None, max_length=200)
    activo: bool | None = None
    telefono: str | None = None
    dos_pasos: bool | None = None


# ---- Facturas ---------------------------------------------------------------
class PosicionCantidad(BaseModel):
    posicion_id: int
    cantidad: int = Cant


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
    cantidad: int | None = Field(default=None, gt=0)
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


# ---- Packing lists ----------------------------------------------------------
class LineaFacturaCantidad(BaseModel):
    factura_linea_id: int
    cantidad: int = Cant


class PLCrear(BaseModel):
    lineas: list[LineaFacturaCantidad] | None = None  # None = todos los pendientes


class PLAgregar(BaseModel):
    version: int
    lineas: list[LineaFacturaCantidad] | None = None


class MovCantidad(BaseModel):
    pl_linea_id: int
    cantidad: int = Cant


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
    peso_neto_caja: float | None = Field(default=None, ge=0)
    peso_bruto_caja: float | None = Field(default=None, ge=0)
    observacion: str | None = None


class ItemCaja(BaseModel):
    pl_linea_id: int
    cantidad_por_caja: int = Cant


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


class EliminarCajas(BaseModel):
    version: int
    grupo_ids: list[int] = Field(min_length=1)


class GuardarPlantilla(BaseModel):
    nombre: str = Field(min_length=1, max_length=100)


class RecepcionItem(BaseModel):
    pl_linea_id: int
    cantidad_recibida: int = Field(ge=0)
    cantidad_danada: int = Field(default=0, ge=0)
    observacion: str | None = None


class RecepcionIn(BaseModel):
    lineas: list[RecepcionItem] = Field(min_length=1)


# ---- Plantillas -------------------------------------------------------------
class PlantillaIn(BaseModel):
    proveedor_id: int | None = None
    nombre: str = Field(min_length=1, max_length=100)
    cantidad_por_caja: int = Cant
    unidad: Literal["PAR", "UN", "CJ"] = "PAR"
    largo: float | None = Field(default=None, ge=0)
    ancho: float | None = Field(default=None, ge=0)
    alto: float | None = Field(default=None, ge=0)
    peso_neto: float | None = Field(default=None, ge=0)
    peso_bruto: float | None = Field(default=None, ge=0)
    tara: float | None = Field(default=None, ge=0)


class PlantillaPatch(BaseModel):
    nombre: str | None = None
    cantidad_por_caja: int | None = Field(default=None, gt=0)
    unidad: Literal["PAR", "UN", "CJ"] | None = None
    largo: float | None = Field(default=None, ge=0)
    ancho: float | None = Field(default=None, ge=0)
    alto: float | None = Field(default=None, ge=0)
    peso_neto: float | None = Field(default=None, ge=0)
    peso_bruto: float | None = Field(default=None, ge=0)
    tara: float | None = Field(default=None, ge=0)
    activa: bool | None = None


# ---- Transporte -------------------------------------------------------------
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
    pallet_id: int | None = None  # None = pallet nuevo con estas medidas
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
    # AUTO: confirma los que ya están listos (factura y PL finalizados) y deja
    # tentativos los demás
    modo: Literal["TENTATIVA", "CONFIRMADA", "AUTO"] = "TENTATIVA"
    motivo: str | None = None


class Recoleccion(BaseModel):
    pl_ids: list[int] = Field(min_length=1)
    fecha: date | None = None  # None = quitar la marca


class PLIds(BaseModel):
    pl_ids: list[int] = Field(min_length=1)
    motivo: str | None = None


class EventoIn(BaseModel):
    tipo: Literal[
        "RECOLECCION", "SALIDA", "TRANSITO", "ARRIBO", "LIBERACION", "ENTREGA", "RECEPCION", "OTRO"
    ]
    fecha: datetime
    ubicacion: str | None = None
    observacion: str | None = None
