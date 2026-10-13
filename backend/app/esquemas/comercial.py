"""Peticiones del módulo comercial: terceros, documentos y pagos."""
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field


class DireccionIn(BaseModel):
    tipo: str = "FISCAL"
    linea1: str = Field(max_length=300)
    linea2: str | None = Field(None, max_length=300)
    ciudad: str | None = Field(None, max_length=100)
    region: str | None = Field(None, max_length=100)
    codigo_postal: str | None = Field(None, max_length=20)
    pais: str | None = Field(None, max_length=2)
    principal: bool = True


class MedioIn(BaseModel):
    tipo: str = "CORREO"
    valor: str = Field(max_length=200)
    uso: str | None = Field(None, max_length=20)
    principal: bool = False


class TerceroIn(BaseModel):
    codigo: str | None = Field(None, max_length=30)
    tipo_persona: str = "JURIDICA"
    nombre: str = Field(max_length=200)
    razon_social: str | None = Field(None, max_length=200)
    tipo_identificacion: str | None = Field(None, max_length=20)
    id_fiscal: str | None = Field(None, max_length=40)
    pais: str | None = Field(None, max_length=2)
    moneda: str | None = Field(None, max_length=3)
    condicion_pago: str | None = Field(None, max_length=20)
    limite_credito: Decimal | None = Field(None, ge=0)
    roles: list[str] = Field(default_factory=list)
    direcciones: list[DireccionIn] | None = None
    medios: list[MedioIn] | None = None
    activo: bool = True
    extra: dict | None = None


class TerceroPatch(TerceroIn):
    nombre: str | None = Field(None, max_length=200)
    tipo_persona: str | None = None
    roles: list[str] | None = None
    activo: bool | None = None


class LineaIn(BaseModel):
    articulo_id: int | None = None
    posicion_oc_id: int | None = None
    codigo: str | None = Field(None, max_length=40)
    descripcion: str | None = Field(None, max_length=300)
    cantidad: Decimal = Field(gt=0, max_digits=14, decimal_places=3)
    unidad: str | None = Field(None, max_length=10)
    precio_unitario: Decimal = Field(ge=0, max_digits=18, decimal_places=6)
    descuento_pct: Decimal = Field(Decimal(0), ge=0, le=100)
    impuestos: list[str] | None = None  # códigos; vacío = los predeterminados de la sociedad


class DocumentoIn(BaseModel):
    tipo: str = Field(max_length=20)  # código del tipo de documento
    sociedad: str = Field(max_length=10)
    tercero_id: int
    fecha: date | None = None
    moneda: str | None = Field(None, max_length=3)
    tipo_cambio: Decimal | None = Field(None, gt=0)
    condicion_pago: str | None = Field(None, max_length=20)
    referencia_externa: str | None = Field(None, max_length=60)
    notas: str | None = Field(None, max_length=4000)
    origen_id: int | None = None  # documento que rectifica (notas) o del que se genera
    lineas: list[LineaIn] = Field(default_factory=list, max_length=500)
    extra: dict | None = None


class DocumentoPatch(BaseModel):
    version: int | None = None
    fecha: date | None = None
    moneda: str | None = Field(None, max_length=3)
    tipo_cambio: Decimal | None = Field(None, gt=0)
    condicion_pago: str | None = Field(None, max_length=20)
    referencia_externa: str | None = Field(None, max_length=60)
    notas: str | None = Field(None, max_length=4000)
    lineas: list[LineaIn] | None = Field(None, max_length=500)
    extra: dict | None = None


class Emitir(BaseModel):
    version: int | None = None


class NotaIn(BaseModel):
    """Nota de crédito o débito sobre un documento emitido: todas sus líneas
    o las indicadas (índice de la línea y cantidad)."""
    tipo: str = Field(max_length=20)
    motivo: str = Field(min_length=1, max_length=500)
    lineas: list[dict] | None = None


class AplicacionIn(BaseModel):
    documento_id: int
    importe: Decimal = Field(gt=0, max_digits=18, decimal_places=4)
    vencimiento_id: int | None = None


class PagoIn(BaseModel):
    direccion: str  # COBRO | PAGO
    tercero_id: int
    sociedad: str = Field(max_length=10)
    fecha: date
    moneda: str = Field(max_length=3)
    tipo_cambio: Decimal | None = Field(None, gt=0)
    importe: Decimal = Field(gt=0, max_digits=18, decimal_places=4)
    metodo_pago: str | None = Field(None, max_length=20)
    referencia: str | None = Field(None, max_length=80)
    notas: str | None = Field(None, max_length=500)
    aplicaciones: list[AplicacionIn] = Field(default_factory=list, max_length=200)


class AplicarIn(BaseModel):
    aplicaciones: list[AplicacionIn] = Field(max_length=200)


class RecurrenteIn(BaseModel):
    nombre: str = Field(max_length=120)
    modelo_id: int
    frecuencia: str = "MENSUAL"
    proxima: date
    hasta: date | None = None
    emitir: bool = False
