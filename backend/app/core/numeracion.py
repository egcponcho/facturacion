"""Numeración segura de documentos.

`siguiente()` asigna el próximo número de una serie dentro de la transacción
en curso: bloquea la fila del contador (SELECT … FOR UPDATE en PostgreSQL;
SQLite admite un solo escritor a la vez), lo incrementa y devuelve el número
con su formato. Si la transacción se revierte, el número no se consume.
Cada documento numerado tiene además una restricción única en la base, la
última defensa contra un duplicado.
"""
from __future__ import annotations

import re
from datetime import date

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errores import ErrorNegocio
from app.modelos.numeracion import ContadorSerie, SerieDocumental


def formato(serie: SerieDocumental, n: int, fecha: date) -> str:
    prefijo = (serie.prefijo or "").replace("{año}", f"{fecha.year:04d}").replace("{year}", f"{fecha.year:04d}")
    return f"{prefijo}{n:0{serie.digitos}d}"


def serie_de(db: Session, objeto: str, *, sociedad_id: int | None = None,
             fecha: date | None = None) -> SerieDocumental | None:
    """La serie activa y vigente de ese objeto: primero la de la sociedad,
    luego la general; entre varias, la predeterminada."""
    fecha = fecha or date.today()
    candidatas = [s for s in db.scalars(select(SerieDocumental).where(
        SerieDocumental.objeto == objeto, SerieDocumental.activo.is_(True)).order_by(SerieDocumental.id))
        if (s.vigente_desde is None or s.vigente_desde <= fecha) and (s.vigente_hasta is None or s.vigente_hasta >= fecha)
        and s.sociedad_id in (None, sociedad_id)]
    candidatas.sort(key=lambda s: (s.sociedad_id is None, not s.predeterminada, s.id))
    return candidatas[0] if candidatas else None


def asegurar_serie(db: Session, objeto: str, codigo: str, nombre: str, prefijo: str, digitos: int = 4,
                   inicial=None) -> SerieDocumental:
    """La serie general de un objeto; si la empresa no tiene una, se crea con
    estos valores y su contador arranca después del mayor número ya usado
    (`inicial()`)."""
    s = serie_de(db, objeto)
    if s:
        return s
    s = SerieDocumental(codigo=codigo, nombre=nombre, objeto=objeto, prefijo=prefijo, digitos=digitos)
    try:
        with db.begin_nested():
            db.add(s)
            db.flush()
            db.add(ContadorSerie(serie_id=s.id, periodo="", siguiente=max(int(inicial() if inicial else 1), 1)))
            db.flush()
    except IntegrityError:  # otra petición la creó al mismo tiempo
        s = serie_de(db, objeto)
    return s


def _contador(db: Session, serie: SerieDocumental, periodo: str) -> ContadorSerie:
    consulta = (select(ContadorSerie).where(ContadorSerie.serie_id == serie.id, ContadorSerie.periodo == periodo)
                .with_for_update())
    c = db.scalar(consulta)
    if c:
        return c
    try:
        with db.begin_nested():
            c = ContadorSerie(serie_id=serie.id, periodo=periodo, siguiente=1)
            db.add(c)
            db.flush()
        return db.scalar(consulta)
    except IntegrityError:
        return db.scalar(consulta)


def siguiente(db: Session, serie: SerieDocumental, fecha: date | None = None) -> str:
    """Reserva y devuelve el próximo número de la serie."""
    fecha = fecha or date.today()
    if not serie.activo:
        raise ErrorNegocio(f"The numbering series {serie.codigo} is inactive.", 409, "serie_inactiva")
    c = _contador(db, serie, f"{fecha.year:04d}" if serie.reinicio == "ANUAL" else "")
    n = c.siguiente
    c.siguiente = n + 1
    db.flush()
    return formato(serie, n, fecha)


def reservar(db: Session, serie: SerieDocumental, cantidad: int, fecha: date | None = None) -> tuple[int, str]:
    """Reserva `cantidad` números seguidos de la serie (identificadores de
    etiquetas): devuelve el primero y el prefijo ya resuelto. Nadie más recibe
    esos números aunque genere al mismo tiempo."""
    fecha = fecha or date.today()
    if not serie.activo:
        raise ErrorNegocio(f"The numbering series {serie.codigo} is inactive.", 409, "serie_inactiva")
    c = _contador(db, serie, f"{fecha.year:04d}" if serie.reinicio == "ANUAL" else "")
    n = c.siguiente
    c.siguiente = n + max(int(cantidad), 0)
    db.flush()
    return n, formato(serie, 0, fecha)[: -serie.digitos] if serie.digitos else formato(serie, 0, fecha)


def proximo(db: Session, serie: SerieDocumental, fecha: date | None = None) -> str:
    """El número que tocaría ahora, sin reservarlo (vista previa)."""
    fecha = fecha or date.today()
    periodo = f"{fecha.year:04d}" if serie.reinicio == "ANUAL" else ""
    c = db.scalar(select(ContadorSerie).where(ContadorSerie.serie_id == serie.id, ContadorSerie.periodo == periodo))
    return formato(serie, c.siguiente if c else 1, fecha)


def mayor_sufijo(codigos, prefijo: str) -> int:
    """Mayor número que sigue al prefijo en una lista de códigos (EMB-0012 → 12)."""
    patron = re.compile(re.escape(prefijo) + r"(\d+)$")
    return max((int(m.group(1)) for c in codigos if c and (m := patron.match(c))), default=0)
