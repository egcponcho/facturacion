"""Empresa de la instalación: datos generales, preferencias y reglas.

Cada instalación sirve a una sola empresa (registro 1 de `organizaciones`).
Sus preferencias (idioma, moneda, zona horaria…) y reglas de negocio se
guardan en la base de datos y se cambian en Configuración → Empresa; los
valores de `settings` solo son los de fábrica para una instalación nueva.
"""
import re

from sqlalchemy.orm import Session

from ..config import settings
from ..empresa import REGLAS
from ..models import Organizacion, Usuario
from .common import ErrorNegocio, permisos_de, registrar

ID_EMPRESA = 1


def asegurar_principal(db: Session, nombre: str = "My company") -> Organizacion:
    """La empresa existe siempre (instalación nueva o demostración)."""
    o = db.get(Organizacion, ID_EMPRESA)
    if not o:
        o = Organizacion(id=ID_EMPRESA, codigo="MAIN", nombre=nombre, configuracion={})
        db.add(o)
        db.flush()
    return o


def configuracion(db: Session) -> dict:
    """Configuración guardada de la empresa (vacía si aún no existe)."""
    o = db.get(Organizacion, ID_EMPRESA)
    return dict(o.configuracion or {}) if o else {}


# ---- Configuración ------------------------------------------------------------
PREFERENCIAS = {"idioma": "en", "moneda": "USD", "zona_horaria": "UTC", "formato_fecha": "MM/DD/YYYY"}


def _reglas_de(o: Organizacion) -> dict:
    propias = (o.configuracion or {}).get("reglas", {})
    return {k: propias.get(k, getattr(settings, k)) for k in REGLAS}


def _dict(o: Organizacion) -> dict:
    conf = o.configuracion or {}
    return {
        "codigo": o.codigo, "nombre": o.nombre, "razon_social": o.razon_social, "id_fiscal": o.id_fiscal,
        "pais": o.pais, "logo": o.logo,
        "preferencias": {**PREFERENCIAS, **conf.get("preferencias", {})},
        "reglas": [{"clave": k, "texto": t, "valor": v} for (k, t), v in zip(REGLAS.items(), _reglas_de(o).values())],
    }


def actual(db: Session) -> Organizacion:
    return asegurar_principal(db)


def detalle(db: Session, user: Usuario) -> dict:
    return _dict(actual(db))


def _validar_regla(clave: str, valor):
    base = getattr(settings, clave)
    if isinstance(base, bool):
        if not isinstance(valor, bool):
            raise ErrorNegocio("This rule is yes or no.", 422, "validacion")
    elif isinstance(base, int):
        if not isinstance(valor, int) or isinstance(valor, bool) or not 0 <= valor <= 365:
            raise ErrorNegocio("Enter a whole number of days between 0 and 365.", 422, "validacion")
    elif clave == "PAIS_BASE_CLASIF":
        if not isinstance(valor, str) or not re.fullmatch(r"[A-Za-z]{2}", valor):
            raise ErrorNegocio("Enter the two-letter country code.", 422, "validacion")
        valor = valor.upper()
    return valor


def actualizar(db: Session, user: Usuario, datos: dict) -> dict:
    """Datos generales, preferencias y reglas de la empresa (administración)."""
    if "admin" not in permisos_de(user):
        raise ErrorNegocio("Only an administrator can change the company settings.", 403, "sin_permiso")
    o = actual(db)
    antes = _dict(o)
    for campo in ("nombre", "razon_social", "id_fiscal", "pais", "logo"):
        if campo in datos:
            valor = datos[campo] or None
            if campo == "nombre" and not valor:
                raise ErrorNegocio("The company needs a name.", 422, "validacion")
            if campo == "logo" and valor and len(valor) > 400_000:
                raise ErrorNegocio("The logo is too large. Use an image under 300 KB.", 422, "validacion")
            setattr(o, campo, valor)
    conf = dict(o.configuracion or {})
    if "preferencias" in datos:
        conf["preferencias"] = {k: v for k, v in {**conf.get("preferencias", {}), **datos["preferencias"]}.items()
                                if k in PREFERENCIAS}
    if "reglas" in datos:
        reglas = dict(conf.get("reglas", {}))
        for clave, valor in datos["reglas"].items():
            if clave not in REGLAS:
                raise ErrorNegocio("Unknown rule.", 422, "validacion")
            reglas[clave] = _validar_regla(clave, valor)
        conf["reglas"] = reglas
    o.configuracion = conf
    registrar(db, user, "organizacion", o.id, "editar_organizacion",
              detalle={"antes": {k: antes[k] for k in ("nombre", "preferencias")}, "reglas": conf.get("reglas", {})})
    db.flush()
    return _dict(o)
