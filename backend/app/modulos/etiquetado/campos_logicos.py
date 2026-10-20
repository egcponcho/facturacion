"""Campos lógicos de las etiquetas: un dato que puede salir de varias fuentes.

Cada empresa define sus campos lógicos (UPC, país de origen, código del
cliente…) con la lista ordenada de campos del catálogo de los que se toma el
valor: el primero que tenga un valor gana. La política dice qué hacer si otra
fuente trae un valor distinto:

- PRIMERA: se usa el primero sin avisar.
- ADVERTIR: se usa el primero y queda una advertencia que hay que aceptar.
- BLOQUEAR: no se genera hasta que las fuentes coincidan.

La instantánea de cada generación guarda de qué fuente salió el valor
(`_procedencia`). Las fuentes son solo campos del catálogo: nunca una
expresión ni código.
"""
from __future__ import annotations

import re
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errores import ErrorNegocio
from app.modelos import CampoEtiqueta, Usuario, VersionPlantilla
from app.modelos.etiquetado import POLITICAS_CAMPO, SUJETOS, TIPOS_CAMPO
from app.modulos.acceso.permisos import exigir, exigir_interno
from app.modulos.comun.historial import registrar

CLAVE = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
MAX_FUENTES = 10
_CACHE = "campos_logicos"


def activos(db: Session) -> list[CampoEtiqueta]:
    """Los campos lógicos activos (una consulta por sesión: se leen en cada etiqueta)."""
    if _CACHE not in db.info:
        db.info[_CACHE] = list(db.scalars(select(CampoEtiqueta).where(CampoEtiqueta.activo.is_(True)).order_by(CampoEtiqueta.clave)))
    return db.info[_CACHE]


def _olvidar(db: Session) -> None:
    db.info.pop(_CACHE, None)


def fuera_de(db: Session, sujeto: str) -> set[str]:
    """Campos lógicos que no existen para lo que se etiqueta."""
    return {f"logico.{c.clave}" for c in activos(db) if c.sujetos and sujeto not in c.sujetos}


def _igual(a, b) -> bool:
    try:
        return float(a) == float(b)
    except (TypeError, ValueError):
        return str(a).strip().lower() == str(b).strip().lower()


def _vacio(v) -> bool:
    return v is None or (isinstance(v, str) and not v.strip())


def resolver(db: Session, sujeto: str, valores: dict) -> tuple[dict, dict, list[dict]]:
    """Valores de los campos lógicos, de qué fuente salió cada uno y los
    problemas por fuentes con valores distintos."""
    res, procedencia, problemas = {}, {}, []
    for c in activos(db):
        if c.sujetos and sujeto not in c.sujetos:
            continue
        clave = f"logico.{c.clave}"
        elegido, fuente = None, None
        for f in c.fuentes or []:
            v = valores.get(f)
            if _vacio(v):
                continue
            if fuente is None:
                elegido, fuente = v, f
            elif not _igual(v, elegido) and c.politica != "PRIMERA":
                nivel = "error" if c.politica == "BLOQUEAR" else "advertencia"
                problemas.append({"nivel": nivel, "codigo": "fuentes_distintas", "elemento": None, "campo": clave,
                                  "mensaje": f"{c.etiqueta}: {fuente} says «{elegido}» but {f} says «{v}»."})
        res[clave] = elegido
        procedencia[clave] = fuente
    return res, procedencia, problemas


# ---- Administración -----------------------------------------------------------------------
def dict_campo(db: Session, c: CampoEtiqueta) -> dict:
    return {"id": c.id, "clave": c.clave, "campo": f"logico.{c.clave}", "etiqueta": c.etiqueta, "descripcion": c.descripcion,
            "tipo": c.tipo, "fuentes": c.fuentes or [], "politica": c.politica, "sujetos": c.sujetos or [],
            "activo": c.activo, "version": c.version, "en_uso": _en_uso(db, c.clave)}


def _en_uso(db: Session, clave: str) -> int:
    """Versiones de diseño que leen el campo."""
    patron = f"logico.{clave}"
    return sum(1 for d in db.scalars(select(VersionPlantilla.diseno)) if patron in str(d))


def listar(db: Session, user: Usuario) -> list[dict]:
    exigir_interno(user, "etiquetas.ver", "etiquetas.campos")
    return [dict_campo(db, c) for c in db.scalars(select(CampoEtiqueta).order_by(CampoEtiqueta.clave))]


def _cargar(db: Session, campo_id: int) -> CampoEtiqueta:
    c = db.get(CampoEtiqueta, campo_id)
    if not c:
        raise ErrorNegocio("The logical field does not exist.", 404, "no_encontrado")
    return c


def _validar(db: Session, datos: dict, actual: CampoEtiqueta | None) -> dict:
    from app.modulos.etiquetado import campos

    errores, limpio = [], {}
    if actual is None or "clave" in datos:
        clave = (datos.get("clave") or "").strip().lower()
        if not CLAVE.match(clave):
            errores.append({"campo": "clave", "mensaje": "Use lowercase letters, digits and _ (starting with a letter, up to 40)."})
        elif db.scalar(select(CampoEtiqueta.id).where(CampoEtiqueta.clave == clave, CampoEtiqueta.id != (actual.id if actual else 0))):
            errores.append({"campo": "clave", "mensaje": "Another logical field has this key."})
        limpio["clave"] = clave
    if actual is None or "etiqueta" in datos:
        etiqueta = (datos.get("etiqueta") or "").strip()
        if not etiqueta or len(etiqueta) > 80:
            errores.append({"campo": "etiqueta", "mensaje": "Enter the name (up to 80 characters)."})
        limpio["etiqueta"] = etiqueta
    if "descripcion" in datos:
        limpio["descripcion"] = (datos.get("descripcion") or "").strip()[:300] or None
    if actual is None or "tipo" in datos:
        tipo = datos.get("tipo") or "texto"
        if tipo not in TIPOS_CAMPO:
            errores.append({"campo": "tipo", "mensaje": "Choose text, number or date."})
        limpio["tipo"] = tipo
    if actual is None or "politica" in datos:
        politica = (datos.get("politica") or "PRIMERA").upper()
        if politica not in POLITICAS_CAMPO:
            errores.append({"campo": "politica", "mensaje": "Choose what to do when the sources disagree."})
        limpio["politica"] = politica
    if actual is None or "sujetos" in datos:
        sujetos = datos.get("sujetos") or []
        if not isinstance(sujetos, list) or any(m not in SUJETOS for m in sujetos):
            errores.append({"campo": "sujetos", "mensaje": "Choose items, packages or documents."})
        limpio["sujetos"] = sorted(set(sujetos)) if isinstance(sujetos, list) else []
    if actual is None or "fuentes" in datos:
        fuentes = datos.get("fuentes") or []
        validas = {c.clave for c in campos.catalogo(db) if c.grupo not in ("logico", "etiqueta")}
        if not isinstance(fuentes, list) or not 1 <= len(fuentes) <= MAX_FUENTES:
            errores.append({"campo": "fuentes", "mensaje": f"Choose between 1 and {MAX_FUENTES} sources, in order."})
        else:
            malas = [f for f in fuentes if f not in validas]
            if malas:
                errores.append({"campo": "fuentes", "mensaje": f"Unknown source fields: {', '.join(map(str, malas))}."})
            if len(set(fuentes)) != len(fuentes):
                errores.append({"campo": "fuentes", "mensaje": "Each source only once."})
        limpio["fuentes"] = list(fuentes) if isinstance(fuentes, list) else []
    if "activo" in datos:
        limpio["activo"] = bool(datos["activo"])
    if errores:
        raise ErrorNegocio("Check the logical field.", 422, "validacion", errores)
    return limpio


def crear(db: Session, user: Usuario, datos: dict) -> dict:
    exigir(user, "etiquetas.campos")
    c = CampoEtiqueta(**{"activo": True, **_validar(db, datos, None)}, creado_por=user.id, version=1)
    db.add(c)
    db.flush()
    _olvidar(db)
    registrar(db, user, "campo_etiqueta", c.id, "crear", {"clave": c.clave, "fuentes": c.fuentes, "politica": c.politica})
    return dict_campo(db, c)


def actualizar(db: Session, user: Usuario, campo_id: int, datos: dict) -> dict:
    exigir(user, "etiquetas.campos")
    c = _cargar(db, campo_id)
    if datos.get("version") is not None and int(datos["version"]) != c.version:
        raise ErrorNegocio("Someone else changed this field: reload it before saving.", 409, "conflicto_version")
    limpio = _validar(db, datos, c)
    if "clave" in limpio and limpio["clave"] != c.clave and _en_uso(db, c.clave):
        raise ErrorNegocio("Designs use this key: it cannot change.", 409, "en_uso")
    antes = dict_campo(db, c)
    for k, v in limpio.items():
        setattr(c, k, v)
    c.version += 1
    c.actualizado_en = datetime.now()
    db.flush()
    _olvidar(db)
    registrar(db, user, "campo_etiqueta", c.id, "editar",
              {k: [antes.get(k), v] for k, v in limpio.items() if antes.get(k) != v})
    return dict_campo(db, c)


def eliminar(db: Session, user: Usuario, campo_id: int) -> dict:
    """Solo un campo que ningún diseño usa; si se usa, se desactiva."""
    exigir(user, "etiquetas.campos")
    c = _cargar(db, campo_id)
    if _en_uso(db, c.clave):
        raise ErrorNegocio("Designs use this field: deactivate it instead.", 409, "en_uso")
    registrar(db, user, "campo_etiqueta", c.id, "eliminar", {"clave": c.clave})
    db.delete(c)
    db.flush()
    _olvidar(db)
    return {"ok": True}
