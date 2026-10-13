"""Normalización de datos que llegan en formularios y cargas masivas.

- Texto: sin espacios sobrantes (inicio, final y dobles).
- Nombres de personas y lugares: si vienen TODO EN MAYÚSCULAS o todo en
  minúsculas se pasan a formato de nombre ("SAN SALVADOR" -> "San Salvador");
  si ya traen mayúsculas y minúsculas se respetan. Siglas y palabras con
  números o puntos (S.A., C.V., 2B) no se tocan.
- Códigos: no se cambian salvo a mayúsculas donde el campo lo pide; los ceros
  iniciales y los símbolos se conservan.
- Referencias: un valor escrito de otra manera ("the north face", "TNF ",
  "Thé North-Face") se enlaza con el registro que ya existe, comparando código
  o nombre sin acentos, mayúsculas, espacios ni signos. Así no se crean
  duplicados.
"""
import re
import unicodedata

from sqlalchemy import select
from sqlalchemy.orm import Session

MENORES = {"de", "del", "la", "las", "los", "el", "y", "e", "o", "u", "en", "a", "al", "para", "por", "con",
           "of", "the", "and", "or", "in", "on", "at", "to", "for", "da", "do", "dos", "das"}


def texto(v) -> str:
    return re.sub(r"\s+", " ", str(v or "")).strip()


def clave(v) -> str:
    """Forma comparable: sin acentos, mayúsculas ni separadores."""
    t = unicodedata.normalize("NFKD", str(v or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9]", "", t).upper()


def nombre(v) -> str:
    t = texto(v)
    letras = [c for c in t if c.isalpha()]
    if not letras or not (t.upper() == t or t.lower() == t):
        return t  # ya trae mayúsculas y minúsculas: se respeta
    palabras = []
    for i, p in enumerate(t.split(" ")):
        bajo = p.lower()
        if re.search(r"[\d.]", p) or (len(p) <= 3 and p.isupper() and t.upper() != t):
            palabras.append(p.upper() if "." in p else p)
        elif i and bajo in MENORES:
            palabras.append(bajo)
        else:
            palabras.append("-".join(x[:1].upper() + x[1:] for x in bajo.split("-")))
    return " ".join(palabras)


class Referencias:
    """Busca un registro de un catálogo por código o por nombre escrito de
    cualquier forma. `campos` son las columnas que identifican el registro."""

    def __init__(self, db: Session, modelo, campos=("codigo", "nombre")):
        self.mapa: dict[str, object] = {}
        objs = db.scalars(select(modelo)).all()
        # Primero los códigos: un nombre igual al código de otro registro no lo pisa
        for c in campos:
            for obj in objs:
                if getattr(obj, c, None):
                    self.mapa.setdefault(clave(getattr(obj, c)), obj)

    def buscar(self, valor):
        return self.mapa.get(clave(valor)) if valor not in (None, "") else None
