"""Clases de material de la composición (ClaseMaterial), como configuración.

El motor trae las clases de base (textil, cuero, plástico, metal, madera,
papel, vidrio, paja y «otro»). Aquí se agrega una clase nueva para una familia
que la necesite (p. ej. cerámica: «ceramica porcelana gres loza»), se suman
palabras a una clase de base y se dice con qué palabra va en la descripción
aduanera. Una derivación de modo «clase» lleva la clase a las opciones de un
atributo (mapa clase → opción).
"""
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import ClaseMaterial, Usuario
from .common import ErrorNegocio, exigir, registrar


def _semilla() -> dict:
    from .semilla_familias import semilla

    return semilla()


def sembrar(db: Session) -> int:
    """Las clases de base con su palabra aduanera (no pisa lo editado)."""
    existentes = {x.codigo: x for x in db.scalars(select(ClaseMaterial))}
    n = 0
    for c in _semilla().get("clases_material") or []:
        x = existentes.get(c["codigo"])
        if not x:
            db.add(ClaseMaterial(codigo=c["codigo"], nombre=c["nombre"], texto_aduana=c.get("texto_aduana"), origen="MOTOR", activo=True))
            n += 1
    db.flush()
    return n


def vocabulario_base() -> dict:
    """Palabras aduaneras por defecto de valores que no son clases (grupos de fibra)."""
    return dict(_semilla().get("vocabulario_aduana") or {})


def _dict(x: ClaseMaterial) -> dict:
    return {"id": x.id, "codigo": x.codigo, "nombre": x.nombre, "palabras": x.palabras, "texto_aduana": x.texto_aduana,
            "origen": x.origen, "activo": x.activo}


def listar(db: Session, user: Usuario) -> list[dict]:
    exigir(user, "clasificacion.ver")
    return [_dict(x) for x in db.scalars(select(ClaseMaterial).order_by(ClaseMaterial.origen, ClaseMaterial.codigo))]


def guardar(db: Session, user: Usuario, clase_id: int | None, datos: dict) -> dict:
    """Crea o edita una clase. Las palabras se validan (cada una un patrón simple
    que compila) y no pueden ser de otra clase configurada."""
    exigir(user, "clasificacion.configurar")
    x = db.get(ClaseMaterial, clase_id) if clase_id else None
    if clase_id and not x:
        raise ErrorNegocio("The material class does not exist.", 404, "no_encontrado")
    x = _aplicar(db, x, datos)
    registrar(db, user, "aranceles", x.id, "clase_material", {"codigo": x.codigo, "cambios": datos})
    return _dict(x)


def _aplicar(db: Session, x: ClaseMaterial | None, datos: dict) -> ClaseMaterial:
    from .composicion import palabras_clase

    if not x:
        cod = re.sub(r"[^a-z0-9_]+", "_", (datos.get("codigo") or datos.get("nombre") or "").strip().lower()).strip("_")[:30]
        if not cod or db.scalar(select(ClaseMaterial.id).where(ClaseMaterial.codigo == cod)):
            raise ErrorNegocio("Give the material class a code that is not in use.", 422, "validacion")
        x = ClaseMaterial(codigo=cod, origen="USUARIO", activo=True)
        db.add(x)
    for k in ("nombre", "palabras", "texto_aduana", "activo"):
        if k in datos and datos[k] is not None:
            setattr(x, k, datos[k].strip() if isinstance(datos[k], str) else datos[k])
    if not (x.nombre or "").strip():
        raise ErrorNegocio("The name is required.", 422, "validacion")
    ws = palabras_clase(x.palabras)
    for w in ws:
        if not re.fullmatch(r"[a-z0-9 ?()|]+", w):
            raise ErrorNegocio(f"«{w}» is not a word (letters, and ? for an optional letter).", 422, "configuracion_invalida")
        try:
            re.compile(w)
        except re.error as e:
            raise ErrorNegocio(f"«{w}» is not valid ({e}).", 422, "configuracion_invalida") from None
    otras = {w: y.codigo for y in db.scalars(select(ClaseMaterial).where(ClaseMaterial.id != (x.id or 0))) for w in palabras_clase(y.palabras)}
    choques = sorted(f"{w} ({otras[w]})" for w in ws if w in otras)
    if choques:
        raise ErrorNegocio(f"These words are already in another class: {', '.join(choques)}.", 422, "configuracion_invalida")
    x.palabras = " ".join(ws) or None
    db.flush()
    return x


def importar_hojas(db: Session, hojas: dict, cuenta, error) -> None:
    """Hoja Material_Classes de un paquete del motor: Class code, Name, Words,
    Customs word, Active (actualiza por código, con la misma validación)."""
    from .oficial import _si, _txt

    for f in hojas.get("Material_Classes", []):
        cod = (_txt(f.get("class_code")) or "").strip().lower()
        if not cod:
            error("Material_Classes", f["_fila"], "Class code is required.")
            continue
        x = db.scalar(select(ClaseMaterial).where(ClaseMaterial.codigo == cod))
        datos = {"codigo": cod, "nombre": _txt(f.get("name")) or (x.nombre if x else cod), "palabras": _txt(f.get("words")),
                 "texto_aduana": _txt(f.get("customs_word"))}
        if f.get("active") is not None:
            datos["activo"] = _si(f.get("active"))
        try:
            with db.begin_nested():
                _aplicar(db, x, {k: v for k, v in datos.items() if v is not None})
            cuenta("Material_Classes", x is None)
        except ErrorNegocio as e:
            error("Material_Classes", f["_fila"], str(e))
