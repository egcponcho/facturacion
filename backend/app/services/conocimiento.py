"""Conocimiento de la empresa (capa COMPANY KNOWLEDGE).

Lo que la empresa aprendió al clasificar: códigos usados con los datos del
producto que los eligieron (aprobaciones, correcciones, lo enseñado desde la
ficha, historiales importados), palabras clave y sinónimos. Solo es una señal
para ordenar candidatos que el motor ya permite (historical_confidence).

Nunca crea una línea arancelaria, un DAI, un impuesto ni una regulación, ni
modifica un dato oficial: un código solo se registra si existe como línea
oficial vigente (o en el árbol oficial, para HS6/SAC).
"""
import json
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import HistorialClasificacion, IncisoNacional, PaisArancel, PalabraClave, Usuario
from .common import ErrorNegocio, exigir, registrar

DEMO = Path(__file__).resolve().parent.parent / "data" / "demo" / "historial_empresa_demo.json"
# Nombres de modelos de la empresa de ejemplo («old skool» es un tenis): palabras clave
# de la empresa, no patrones del motor (otra empresa tendrá los suyos)
DEMO_PALABRAS = Path(__file__).resolve().parent.parent / "data" / "demo" / "palabras_empresa_demo.json"
ORIGENES = ("APROBACION", "CORRECCION", "ENSENADO", "IMPORTADO")


def _dig(v) -> str:
    return "".join(ch for ch in str(v or "") if ch.isdigit())


def registrar_decision(db: Session, *, pais: str | None, codigo: str, condiciones: dict | None, origen: str, categoria: str | None = None,
                       producto_id: int | None = None, usuario: Usuario | None = None, nota: str | None = None, conteo: int = 1) -> HistorialClasificacion:
    """Suma una decisión al historial (la misma combinación se acumula)."""
    cod = _dig(codigo)
    cond = {k: v for k, v in (condiciones or {}).items() if v not in (None, "", [])}
    x = db.scalar(select(HistorialClasificacion).where(HistorialClasificacion.pais == pais, HistorialClasificacion.codigo == cod,
                                                       HistorialClasificacion.origen == origen, HistorialClasificacion.categoria == categoria,
                                                       HistorialClasificacion.producto_id == producto_id))
    if x and (x.condiciones or {}) == cond:
        x.conteo = (x.conteo or 0) + conteo
        return x
    x = HistorialClasificacion(pais=pais, codigo=cod, sub6=cod[:6], condiciones=cond, origen=origen, categoria=categoria, conteo=conteo,
                               producto_id=producto_id, creado_por=usuario.id if usuario else None, nota=(nota or "")[:300] or None)
    db.add(x)
    return x


def ensenar(db: Session, user: Usuario, pais: str, codigo: str, cond: dict | None, nota: str | None = None) -> dict:
    """«Recordar para productos parecidos» desde la ficha: la preferencia queda
    como conocimiento de la empresa. El código debe ser una línea oficial
    vigente del país; no se crea ni se modifica ninguna línea."""
    exigir(user, "producto.clasificar")
    iso = (pais or "").upper()
    if not db.scalar(select(PaisArancel.id).where(PaisArancel.iso == iso, PaisArancel.activo.is_(True))):
        raise ErrorNegocio("Choose a destination country.", 422, "validacion")
    cod = _dig(codigo)
    if not db.scalar(select(IncisoNacional.id).where(IncisoNacional.pais == iso, IncisoNacional.codigo == cod,
                                                      IncisoNacional.fuente == "oficial", IncisoNacional.activo.is_(True))):
        raise ErrorNegocio(f"{cod} is not an official national line of {iso}: the company history cannot create tariff lines.",
                           422, "no_es_linea_oficial")
    x = registrar_decision(db, pais=iso, codigo=cod, condiciones=cond, origen="ENSENADO", usuario=user, nota=nota)
    db.flush()
    registrar(db, user, "conocimiento", x.id, "ensenado", {"pais": iso, "codigo": cod, "condiciones": x.condiciones})
    return {"id": x.id}


def listar(db: Session, user: Usuario, pais: str | None = None, q: str | None = None, page: int = 1, size: int = 50) -> dict:
    exigir(user, "producto.ver")
    consulta = select(HistorialClasificacion)
    if pais:
        consulta = consulta.where(HistorialClasificacion.pais == pais.upper())
    if q:
        consulta = consulta.where(HistorialClasificacion.codigo.startswith(_dig(q) or q))
    total = db.scalar(select(func.count()).select_from(consulta.subquery())) or 0
    filas = db.scalars(consulta.order_by(HistorialClasificacion.conteo.desc(), HistorialClasificacion.id).offset((page - 1) * size).limit(size))
    oficiales = {(i, c) for i, c in db.execute(select(IncisoNacional.pais, IncisoNacional.codigo).where(IncisoNacional.fuente == "oficial"))}
    return {"total": total, "items": [{"id": x.id, "pais": x.pais, "codigo": x.codigo, "categoria": x.categoria, "condiciones": x.condiciones,
                                       "origen": x.origen, "conteo": x.conteo, "nota": x.nota, "producto_id": x.producto_id,
                                       # Un código del historial que hoy no es línea oficial no se puede usar
                                       "linea_oficial": (x.pais, x.codigo) in oficiales if x.pais else None}
                                      for x in filas]}


def cargar_historial_demo(db: Session) -> int:
    """Demostración: el historial de clasificaciones de la empresa de ejemplo
    (códigos usados por país con las condiciones de sus artículos)."""
    if db.scalar(select(func.count()).select_from(HistorialClasificacion).where(HistorialClasificacion.origen == "IMPORTADO")):
        return 0
    n = 0
    for x in json.loads(DEMO.read_text(encoding="utf-8")):
        registrar_decision(db, pais=x["pais"], codigo=x["codigo"], condiciones=x.get("cond") or {}, origen="IMPORTADO",
                           conteo=max(int(x.get("articulos") or 0), 1), nota="Demo company classification history")
        n += 1
    db.flush()
    return n


def cargar_palabras_demo(db: Session) -> int:
    """Demostración: palabras clave de la empresa de ejemplo (nombres de sus
    modelos). Solo interpretan el nombre del producto; nunca crean códigos."""
    if db.scalar(select(func.count()).select_from(PalabraClave)):
        return 0
    filas = json.loads(DEMO_PALABRAS.read_text(encoding="utf-8"))
    for x in filas:
        db.add(PalabraClave(frase=x["frase"], tipo=x["tipo"], marca=x.get("marca"), atributos=x.get("atributos") or {}))
    db.flush()
    return len(filas)
