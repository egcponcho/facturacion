"""Tipos de etiqueta de la empresa (colgante, precio, caja master, contenido
de OC…): qué se etiqueta, cuántas salen y si todo sujeto debe llevar una.

Los define cada empresa: nada de esto está fijo en el código. El sujeto de un
tipo no cambia cuando ya tiene diseños (sus diseños usan los datos de ese
sujeto); el resto se edita libremente.
"""
from __future__ import annotations

import re
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errores import ErrorNegocio
from app.modelos import PlantillaEtiqueta, TipoEmpaque, TipoEtiqueta, TipoEtiquetaEmpaque, UsoDiseno, Usuario
from app.modelos.etiquetado import CANTIDADES_DE, SUJETOS
from app.modulos.acceso.permisos import exigir, exigir_alguno
from app.modulos.comun.historial import registrar

CODIGO = re.compile(r"^[A-Z0-9][A-Z0-9_-]{0,29}$")
# Plantillas del asistente de primer uso (la interfaz las ofrece; la empresa elige y renombra)
SUGERIDOS = [
    {"codigo": "COLGANTE", "nombre": "Hang tag", "sujeto": "ARTICULO", "cantidad": "POR_UNIDAD", "obligatoria": True},
    {"codigo": "PRECIO", "nombre": "Price sticker", "sujeto": "ARTICULO", "cantidad": "POR_UNIDAD", "obligatoria": False},
    {"codigo": "CAJA", "nombre": "Carton label", "sujeto": "BULTO", "cantidad": "POR_BULTO", "obligatoria": True},
    {"codigo": "CONTENIDO", "nombre": "PO content sheet", "sujeto": "DOCUMENTO", "cantidad": "POR_DOCUMENTO",
     "obligatoria": False},
]


def empaques_de(db: Session, tipo_id: int) -> list[int]:
    """Tipos de empaque a los que se aplica un tipo de etiqueta de bulto ([] = a todos)."""
    return sorted(db.scalars(select(TipoEtiquetaEmpaque.tipo_empaque_id).where(TipoEtiquetaEmpaque.tipo_etiqueta_id == tipo_id)))


def aplica(empaques: list[int] | set[int], tipo_empaque_id: int | None) -> bool:
    """¿Este tipo de etiqueta va en un empaque de ese tipo? Sin restricción, en todos."""
    return not empaques or tipo_empaque_id in empaques


def dict_tipo(db: Session, t: TipoEtiqueta) -> dict:
    disenos = db.scalar(select(func.count()).select_from(PlantillaEtiqueta).where(
        PlantillaEtiqueta.tipo_etiqueta_id == t.id, PlantillaEtiqueta.estado == "ACTIVA")) or 0
    usos = db.scalar(select(func.count()).select_from(UsoDiseno).where(
        UsoDiseno.tipo_etiqueta_id == t.id, UsoDiseno.eliminado_en.is_(None))) or 0
    return {"id": t.id, "codigo": t.codigo, "nombre": t.nombre, "descripcion": t.descripcion, "sujeto": t.sujeto,
            "cantidad": t.cantidad, "obligatoria": t.obligatoria, "orden": t.orden, "activo": t.activo, "version": t.version,
            "disenos": disenos, "usos": usos, "empaques": empaques_de(db, t.id) if t.sujeto == "BULTO" else []}


def cargar(db: Session, tipo_id: int) -> TipoEtiqueta:
    t = db.get(TipoEtiqueta, tipo_id)
    if not t:
        raise ErrorNegocio("The label type does not exist.", 404, "no_encontrado")
    return t


def listar(db: Session, user: Usuario, activos: bool | None = True) -> list[dict]:
    exigir_alguno(user, "etiquetas.ver", "etiquetas.generar", "etiquetas.configurar")
    c = select(TipoEtiqueta).order_by(TipoEtiqueta.orden, TipoEtiqueta.id)
    if activos is not None:
        c = c.where(TipoEtiqueta.activo.is_(activos))
    return [dict_tipo(db, t) for t in db.scalars(c)]


def _validar(db: Session, datos: dict, actual: TipoEtiqueta | None) -> dict:
    errores, limpio = [], {}
    if actual is None or "codigo" in datos:
        codigo = (datos.get("codigo") or "").strip().upper()
        if not CODIGO.match(codigo):
            errores.append({"campo": "codigo", "mensaje": "Use capital letters, digits, - and _ (up to 30)."})
        elif db.scalar(select(TipoEtiqueta.id).where(TipoEtiqueta.codigo == codigo,
                                                      TipoEtiqueta.id != (actual.id if actual else 0))):
            errores.append({"campo": "codigo", "mensaje": "Another label type has this code."})
        limpio["codigo"] = codigo
    if actual is None or "nombre" in datos:
        nombre = (datos.get("nombre") or "").strip()
        if not nombre or len(nombre) > 120:
            errores.append({"campo": "nombre", "mensaje": "Enter the name (up to 120 characters)."})
        limpio["nombre"] = nombre
    if "descripcion" in datos:
        limpio["descripcion"] = (datos.get("descripcion") or "").strip()[:300] or None
    sujeto = actual.sujeto if actual else None
    if actual is None or "sujeto" in datos:
        sujeto = (datos.get("sujeto") or "").upper()
        if sujeto not in SUJETOS:
            errores.append({"campo": "sujeto", "mensaje": "Choose what is labeled: an item, a package or a document."})
        elif actual is not None and sujeto != actual.sujeto and db.scalar(select(PlantillaEtiqueta.id).where(
                PlantillaEtiqueta.tipo_etiqueta_id == actual.id)):
            errores.append({"campo": "sujeto", "mensaje": "The type already has designs: what it labels cannot change."})
        limpio["sujeto"] = sujeto
    if actual is None or "cantidad" in datos or "sujeto" in datos:
        cantidad = (datos.get("cantidad") or (actual.cantidad if actual else "") or "").upper()
        if sujeto in CANTIDADES_DE and cantidad not in CANTIDADES_DE[sujeto]:
            errores.append({"campo": "cantidad", "mensaje": "Choose how many labels come out of each record."})
        limpio["cantidad"] = cantidad
    for k in ("obligatoria", "activo"):
        if k in datos:
            limpio[k] = bool(datos[k])
    if "orden" in datos:
        try:
            limpio["orden"] = max(int(datos["orden"]), 0)
        except (TypeError, ValueError):
            errores.append({"campo": "orden", "mensaje": "Write a whole number."})
    if "empaques" in datos:
        ids = datos.get("empaques") or []
        if sujeto != "BULTO" and ids:
            errores.append({"campo": "empaques", "mensaje": "Only package labels are limited to some package types."})
        elif not isinstance(ids, list) or not all(str(x).isdigit() for x in ids):
            errores.append({"campo": "empaques", "mensaje": "Choose the package types."})
        else:
            ids = sorted({int(x) for x in ids})
            existen = set(db.scalars(select(TipoEmpaque.id).where(TipoEmpaque.id.in_(ids)))) if ids else set()
            if existen != set(ids):
                errores.append({"campo": "empaques", "mensaje": "A package type does not exist."})
            elif actual is not None and ids:
                # Un diseño puesto en un nivel que deja de aplicar quedaría sin uso: se quita primero
                fuera = db.scalars(select(TipoEmpaque.nombre).join(UsoDiseno, UsoDiseno.tipo_empaque_id == TipoEmpaque.id).where(
                    UsoDiseno.tipo_etiqueta_id == actual.id, UsoDiseno.eliminado_en.is_(None),
                    UsoDiseno.tipo_empaque_id.not_in(ids)).distinct()).all()
                if fuera:
                    errores.append({"campo": "empaques", "mensaje": "These package types have a design of this label: "
                                    f"{', '.join(fuera)}. Remove it in «Which design goes on what» first."})
            limpio["empaques"] = ids
    if errores:
        raise ErrorNegocio("Check the label type.", 422, "validacion", errores)
    return limpio


def _poner_empaques(db: Session, t: TipoEtiqueta, ids: list[int]) -> bool:
    antes = empaques_de(db, t.id)
    if antes == ids:
        return False
    for x in db.scalars(select(TipoEtiquetaEmpaque).where(TipoEtiquetaEmpaque.tipo_etiqueta_id == t.id)):
        db.delete(x)
    db.flush()
    for i in ids:
        db.add(TipoEtiquetaEmpaque(tipo_etiqueta_id=t.id, tipo_empaque_id=i))
    db.flush()
    return True


def crear(db: Session, user: Usuario, datos: dict) -> dict:
    exigir(user, "etiquetas.configurar")
    limpio = _validar(db, datos, None)
    if "orden" not in limpio:
        limpio["orden"] = (db.scalar(select(func.max(TipoEtiqueta.orden))) or 0) + 1
    empaques = limpio.pop("empaques", [])
    t = TipoEtiqueta(**{"obligatoria": False, "activo": True, **limpio}, creado_por=user.id, version=1)
    db.add(t)
    db.flush()
    _poner_empaques(db, t, empaques)
    registrar(db, user, "tipo_etiqueta", t.id, "crear", {"codigo": t.codigo, "sujeto": t.sujeto, "cantidad": t.cantidad})
    return dict_tipo(db, t)


def actualizar(db: Session, user: Usuario, tipo_id: int, datos: dict) -> dict:
    exigir(user, "etiquetas.configurar")
    t = cargar(db, tipo_id)
    if datos.get("version") is not None and int(datos["version"]) != t.version:
        raise ErrorNegocio("Someone else changed this label type: reload it before saving.", 409, "conflicto_version")
    limpio = _validar(db, datos, t)
    empaques = limpio.pop("empaques", None)
    if limpio.get("sujeto", t.sujeto) != "BULTO":
        empaques = []
    cambios = {k: [getattr(t, k), v] for k, v in limpio.items() if getattr(t, k) != v}
    antes = empaques_de(db, t.id)
    if empaques is not None and _poner_empaques(db, t, empaques):
        cambios["empaques"] = [antes, empaques]
    for k, v in limpio.items():
        setattr(t, k, v)
    t.version += 1
    t.actualizado_por, t.actualizado_en = user.id, datetime.now()
    db.flush()
    if cambios:
        registrar(db, user, "tipo_etiqueta", t.id, "editar", cambios)
    return dict_tipo(db, t)


def crear_sugeridos(db: Session, user: Usuario, codigos: list[str]) -> list[dict]:
    """Primer uso: crea los tipos elegidos de la lista sugerida (los que ya existen se dejan)."""
    exigir(user, "etiquetas.configurar")
    res = []
    for s in SUGERIDOS:
        if s["codigo"] in codigos and not db.scalar(select(TipoEtiqueta.id).where(TipoEtiqueta.codigo == s["codigo"])):
            res.append(crear(db, user, s))
    return res
