"""Traducciones de los textos del catálogo (preguntas, opciones, categorías,
familias, clases de material).

La configuración se escribe en inglés —como las claves de la interfaz— y cada
texto se traduce aquí a los idiomas de la interfaz. El frontend las suma a su
diccionario al iniciar sesión, así todo lo que muestra con tx() sale traducido
sin que cada servicio tenga que saber del idioma.
"""
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..datos import MOTOR
from ..models import (
    AtributoDef,
    AtributoOpcion,
    CategoriaProducto,
    ClaseMaterial,
    DominioClasificacion,
    TraduccionCatalogo,
    Usuario,
)
from .common import ErrorNegocio, exigir, registrar

IDIOMAS = ("es",)  # el catálogo se escribe en inglés y se traduce al español
ARCHIVO = "traducciones_catalogo.json"


def textos(db: Session) -> list[str]:
    """Todos los textos del catálogo que se muestran a las personas."""
    consultas = [select(AtributoDef.etiqueta).where(AtributoDef.activo.is_(True)), select(AtributoDef.descripcion),
                 select(AtributoOpcion.etiqueta), select(CategoriaProducto.nombre), select(CategoriaProducto.nombre_corto),
                 select(CategoriaProducto.grupo), select(DominioClasificacion.nombre), select(DominioClasificacion.descripcion),
                 select(ClaseMaterial.nombre)]
    out = set()
    for q in consultas:
        out.update(x.strip() for x in db.scalars(q) if x and x.strip())
    return sorted(out, key=str.lower)


def catalogo(db: Session, idioma: str) -> dict[str, str]:
    """{texto en inglés: traducción} de un idioma (lo que suma el frontend)."""
    if idioma not in IDIOMAS:
        return {}
    return {x.texto: x.traduccion for x in db.scalars(select(TraduccionCatalogo).where(TraduccionCatalogo.idioma == idioma))}


def listar(db: Session, user: Usuario, idioma: str, q: str | None = None, pendientes: bool = False) -> dict:
    exigir(user, "clasificacion.ver")
    if idioma not in IDIOMAS:
        raise ErrorNegocio(f"Language {idioma} is not one of {', '.join(IDIOMAS)}.", 422, "validacion")
    hechas = catalogo(db, idioma)
    filas = [{"texto": x, "traduccion": hechas.get(x)} for x in textos(db)]
    total, faltan = len(filas), sum(1 for f in filas if not f["traduccion"])
    if q:
        b = q.strip().lower()
        filas = [f for f in filas if b in f["texto"].lower() or b in (f["traduccion"] or "").lower()]
    if pendientes:
        filas = [f for f in filas if not f["traduccion"]]
    return {"idioma": idioma, "total": total, "faltan": faltan, "items": filas[:500]}


def guardar(db: Session, user: Usuario, idioma: str, texto: str, traduccion: str | None) -> dict:
    exigir(user, "clasificacion.configurar")
    if idioma not in IDIOMAS:
        raise ErrorNegocio(f"Language {idioma} is not one of {', '.join(IDIOMAS)}.", 422, "validacion")
    texto = (texto or "").strip()
    if not texto:
        raise ErrorNegocio("The text to translate is required.", 422, "validacion")
    x = db.scalar(select(TraduccionCatalogo).where(TraduccionCatalogo.texto == texto, TraduccionCatalogo.idioma == idioma))
    traduccion = (traduccion or "").strip()[:400]
    if not traduccion:
        if x:
            db.delete(x)
    elif x:
        x.traduccion, x.origen = traduccion, "USUARIO"
    else:
        db.add(TraduccionCatalogo(texto=texto[:400], idioma=idioma, traduccion=traduccion, origen="USUARIO"))
    registrar(db, user, "traduccion", 0, "guardada", {"idioma": idioma, "texto": texto, "traduccion": traduccion or None})
    db.flush()
    return {"texto": texto, "traduccion": traduccion or None}


def sembrar(db: Session) -> int:
    """Las traducciones de base del catálogo incluido (no pisan las editadas)."""
    archivo = MOTOR / ARCHIVO
    if not archivo.exists():
        return 0
    base = json.loads(archivo.read_text(encoding="utf-8"))
    existentes = {(x.texto, x.idioma) for x in db.scalars(select(TraduccionCatalogo))}
    n = 0
    for texto, por_idioma in base.items():
        for idioma, traduccion in por_idioma.items():
            if idioma in IDIOMAS and traduccion and (texto, idioma) not in existentes:
                db.add(TraduccionCatalogo(texto=texto, idioma=idioma, traduccion=traduccion, origen="MOTOR"))
                n += 1
    db.flush()
    return n
