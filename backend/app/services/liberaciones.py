"""Liberaciones de las órdenes de compra (comercial y logística).

Cada empresa define en Datos maestros → Estados de liberación los códigos que
manda su ERP para cada liberación, su nombre y su efecto:

- `libera`: con este estado la liberación está dada.
- `con_cambios`: estado logístico de una OC liberada que cambió después.
- `predeterminado`: el que se usa cuando el archivo no trae el dato.
- `alias`: otras palabras que acepta el importador.

Reglas del flujo (iguales para cualquier empresa):
- Se factura solo con las dos liberaciones dadas.
- Sin liberación comercial no hay liberación logística.
- Una OC con liberación logística dada que cambia pasa al estado «con cambios».
"""
import re
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import EstadoLiberacion, OrdenCompra

COMERCIAL, LOGISTICA = "COMERCIAL", "LOGISTICA"


def _norm(texto: str | None) -> str:
    return re.sub(r"[^A-Z0-9]", "", (texto or "").strip().upper())


@dataclass
class Estados:
    """Estados activos de una liberación, con sus búsquedas."""

    tipo: str
    lista: list = field(default_factory=list)

    def get(self, codigo: str | None) -> EstadoLiberacion | None:
        return next((x for x in self.lista if x.codigo == codigo), None)

    def libera(self, codigo: str | None) -> bool:
        x = self.get(codigo)
        return bool(x and x.libera)

    def nombre(self, codigo: str | None) -> str | None:
        x = self.get(codigo)
        return x.nombre if x else codigo

    def predeterminado(self) -> str | None:
        x = next((x for x in self.lista if x.predeterminado), None)
        return x.codigo if x else None

    def sin_liberar(self) -> str | None:
        """Estado que no libera (el predeterminado si no libera, si no el primero)."""
        no = [x for x in self.lista if not x.libera]
        x = next((x for x in no if x.predeterminado), no[0] if no else None)
        return x.codigo if x else None

    def con_cambios(self) -> str | None:
        x = next((x for x in self.lista if x.con_cambios), None)
        return x.codigo if x else None

    def leer(self, valor: str | None):
        """Código para un valor del archivo (código, nombre o alias); None si
        viene vacío y False si no se reconoce."""
        v = _norm(valor)
        if not v:
            return None
        for x in self.lista:
            palabras = [x.codigo, x.nombre] + [a for a in (x.alias or "").split(",")]
            if v in {_norm(p) for p in palabras if p and p.strip()}:
                return x.codigo
        return False

    def ayuda(self) -> str:
        return ", ".join(f"{x.codigo} = {x.nombre}" for x in self.lista)


def estados(db: Session, tipo: str) -> Estados:
    lista = db.scalars(select(EstadoLiberacion).where(EstadoLiberacion.tipo == tipo, EstadoLiberacion.activo.is_(True))
                       .order_by(EstadoLiberacion.orden, EstadoLiberacion.codigo)).all()
    return Estados(tipo, list(lista))


@dataclass
class Liberaciones:
    comercial: Estados
    logistica: Estados

    def liberada(self, comercial: str | None, logistica: str | None) -> bool:
        return self.comercial.libera(comercial) and self.logistica.libera(logistica)

    def logistica_final(self, comercial: str, explicita: str | None, actual: str | None, hubo_cambios: bool) -> str | None:
        """Estado logístico final. Sin liberación comercial no hay logística.
        Si el archivo trae el estado, manda el archivo; si no, se conserva el
        que tenía (o el predeterminado si es nueva) y una OC liberada que
        cambia pasa al estado «con cambios»."""
        if not self.comercial.libera(comercial):
            return self.logistica.sin_liberar()
        if explicita and self.logistica.get(explicita):
            return explicita
        cambios = self.logistica.con_cambios()
        if actual and hubo_cambios and cambios and self.logistica.libera(actual) and actual != cambios:
            return cambios
        return actual or self.logistica.predeterminado() or self.logistica.sin_liberar()

    def fechar(self, oc: OrdenCompra, hoy: date | None = None) -> None:
        """Fecha de cada liberación para medir los lead times: el día en que
        quedó dada (o la del archivo); se borra si se revierte."""
        hoy = hoy or date.today()
        if self.comercial.libera(oc.liberacion_comercial):
            oc.fecha_lib_comercial = oc.fecha_lib_comercial or hoy
        else:
            oc.fecha_lib_comercial = None
        if self.logistica.libera(oc.liberacion_logistica):
            oc.fecha_lib_logistica = oc.fecha_lib_logistica or hoy
            if oc.fecha_lib_comercial and oc.fecha_lib_logistica < oc.fecha_lib_comercial:
                oc.fecha_lib_logistica = oc.fecha_lib_comercial
        else:
            oc.fecha_lib_logistica = None


def de(db: Session) -> Liberaciones:
    return Liberaciones(estados(db, COMERCIAL), estados(db, LOGISTICA))


# Nombres de los estados de fábrica (migración 0039), para traducirlos en
# pantalla mientras la empresa no los cambie
NOMBRES_FABRICA = ("Released by commercial", "Pending commercial", "Released by logistics",
                   "Released with later changes", "Not released by logistics")
