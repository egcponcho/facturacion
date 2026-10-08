"""Preferencias de cada usuario: idioma, formatos de fecha, hora y números,
tema y filas por página. Por defecto: inglés y fecha MM/DD/YYYY.

El formato elegido se usa en todo lo que genera el servidor para ese usuario
(PDF, Excel, plantillas de carga) y para leer las fechas de los archivos que
sube. Durante cada petición las preferencias del usuario quedan en una
variable de contexto, así los generadores no necesitan recibirlas.
"""
import re
from contextvars import ContextVar
from datetime import date, datetime

from sqlalchemy.orm import Session

from ..models import Usuario
from .common import ErrorNegocio, registrar

IDIOMAS = ("es", "en")
# Formato visible -> strftime
FORMATOS_FECHA = {
    "MM/DD/YYYY": "%m/%d/%Y",
    "DD/MM/YYYY": "%d/%m/%Y",
    "YYYY-MM-DD": "%Y-%m-%d",
    "DD-MMM-YYYY": "%d-%b-%Y",
    "MMM DD, YYYY": "%b %d, %Y",
}
# Separador de miles y decimal
FORMATOS_NUMERO = {"1,234.56": (",", "."), "1.234,56": (".", ","), "1 234,56": (" ", ","), "1'234.56": ("'", ".")}
FORMATOS_HORA = ("12", "24")
TEMAS = ("sistema", "claro", "oscuro")
FILAS = (10, 25, 50, 100)
INICIOS = ("/", "/ordenes", "/facturas", "/transporte", "/productos", "/seguimiento")

DEFECTO = {"idioma": "en", "idioma_documentos": None, "formato_fecha": "MM/DD/YYYY", "formato_hora": "12", "formato_numero": "1,234.56",
           "tema": "sistema", "filas": 25, "inicio": "/"}

_actual: ContextVar[dict] = ContextVar("preferencias", default=DEFECTO)


def de(u: Usuario | None) -> dict:
    """Preferencias de la persona: las suyas, si no las de la empresa
    (Configuración → Empresa) y si no las de fábrica."""
    from ..empresa import configuracion_actual

    empresa = {k: v for k, v in (configuracion_actual().get("preferencias") or {}).items() if k in ("idioma", "formato_fecha")}
    pref = {**DEFECTO, **empresa, **((u.preferencias or {}) if u else {})}
    if pref.get("idioma") not in IDIOMAS:
        pref["idioma"] = DEFECTO["idioma"]
    return pref


def usar(u: Usuario | None) -> None:
    _actual.set(de(u))


def actual() -> dict:
    return _actual.get()


def _strf(pref: dict | None = None) -> str:
    return FORMATOS_FECHA.get((pref or actual())["formato_fecha"], FORMATOS_FECHA["MM/DD/YYYY"])


def fecha_txt(d) -> str:
    """Fecha en el formato del usuario ('' si no hay)."""
    if not d:
        return ""
    if isinstance(d, str):
        try:
            d = datetime.fromisoformat(d)
        except ValueError:
            return d
    return d.strftime(_strf())


def hora_txt(d: datetime) -> str:
    return d.strftime("%I:%M %p" if actual()["formato_hora"] == "12" else "%H:%M")


def fecha_hora_txt(d) -> str:
    if not d:
        return ""
    if isinstance(d, str):
        d = datetime.fromisoformat(d)
    if not isinstance(d, datetime):
        return fecha_txt(d)
    return f"{fecha_txt(d)} {hora_txt(d)}"


def leer_fecha(valor) -> date | None:
    """Fecha de un archivo subido: ISO, o el formato del usuario; si no, los
    demás formatos (con el orden día/mes del usuario para no confundirlos)."""
    if valor in (None, ""):
        return None
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    texto = re.sub(r"\s+", " ", str(valor).strip())
    propio = _strf()
    dia_primero = propio.startswith("%d")
    formatos = ["%Y-%m-%d", propio, "%Y%m%d"]
    for sep in "/-.":
        par = [f"%m{sep}%d{sep}%Y", f"%d{sep}%m{sep}%Y"]
        formatos += par[::-1] if dia_primero else par
    formatos += ["%d-%b-%Y", "%b %d, %Y", "%d %b %Y"]
    for formato in dict.fromkeys(formatos):
        try:
            return datetime.strptime(texto if "%b" in formato else texto[:10], formato).date()
        except ValueError:
            continue
    raise ValueError(f"invalid date: {valor} (use {actual()['formato_fecha']})")


def opciones() -> dict:
    return {"idiomas": list(IDIOMAS), "formatos_fecha": list(FORMATOS_FECHA), "formatos_numero": list(FORMATOS_NUMERO),
            "formatos_hora": list(FORMATOS_HORA), "temas": list(TEMAS), "filas": list(FILAS), "inicios": list(INICIOS)}


FOTO = re.compile(r"^data:image/(png|jpeg|webp);base64,[A-Za-z0-9+/=]+$")


def guardar_foto(db: Session, user: Usuario, foto: str | None) -> dict:
    """Foto de perfil: una imagen pequeña (la pantalla la reduce antes de enviarla)."""
    if foto and not FOTO.match(foto):
        raise ErrorNegocio("Use a PNG, JPEG or WebP image.", 422, "validacion")
    user.foto = foto or None
    registrar(db, user, "usuario", user.id, "foto", {"foto": bool(foto)})
    return {"foto": user.foto}


def guardar(db: Session, user: Usuario, datos) -> dict:
    """El usuario edita su nombre y sus preferencias (no su correo, rol ni proveedor)."""
    campos = datos.model_dump(exclude_unset=True)
    errores = []
    if "nombre" in campos:
        nombre = re.sub(r"\s+", " ", campos.pop("nombre") or "").strip()
        if len(nombre) < 2:
            errores.append({"campo": "nombre", "mensaje": "Enter your name."})
        else:
            user.nombre = nombre
    validos = {"idioma": IDIOMAS, "idioma_documentos": IDIOMAS, "formato_fecha": tuple(FORMATOS_FECHA), "formato_numero": tuple(FORMATOS_NUMERO),
               "formato_hora": FORMATOS_HORA, "tema": TEMAS, "filas": FILAS, "inicio": INICIOS}
    # Se guarda lo que la persona eligió; None vuelve al valor de la empresa o de fábrica
    propias = dict(user.preferencias or {})
    for k, v in campos.items():
        if v is None:
            propias.pop(k, None)
        elif v not in validos[k]:
            errores.append({"campo": k, "mensaje": "Choose one of the options."})
        else:
            propias[k] = v
    if errores:
        raise ErrorNegocio("Check the data.", 422, "validacion", errores)
    user.preferencias = propias
    usar(user)
    registrar(db, user, "usuario", user.id, "perfil", {"preferencias": user.preferencias})
    return {"nombre": user.nombre, "preferencias": de(user)}


# ---- Vistas guardadas ---------------------------------------------------------
# Cada pantalla con filtros (seguimiento, órdenes…) guarda vistas con nombre:
# los filtros, la pestaña y el orden que la persona usa a menudo. Son
# preferencias suyas (no se comparten todavía).
PANTALLAS_VISTA = ("seguimiento", "ordenes", "facturas", "productos", "embarques")
MAX_VISTAS = 20


def guardar_vistas(db: Session, user: Usuario, pantalla: str, vistas: list) -> dict:
    if pantalla not in PANTALLAS_VISTA:
        raise ErrorNegocio("This screen does not keep saved views.", 404, "no_encontrado")
    limpias, nombres = [], set()
    for v in (vistas or [])[:MAX_VISTAS]:
        nombre = re.sub(r"\s+", " ", str((v or {}).get("nombre") or "")).strip()[:60]
        query = (v or {}).get("query") or {}
        if not nombre or not isinstance(query, dict):
            raise ErrorNegocio("Each view needs a name.", 422, "validacion")
        if nombre.lower() in nombres:
            raise ErrorNegocio(f"There is already a view called {nombre}.", 422, "validacion")
        nombres.add(nombre.lower())
        limpias.append({"nombre": nombre, "query": {str(k)[:40]: str(x)[:300] for k, x in list(query.items())[:40]
                                                       if x not in (None, "")}})
    pref = dict(user.preferencias or {})
    todas = dict(pref.get("vistas") or {})
    todas[pantalla] = limpias
    pref["vistas"] = {k: x for k, x in todas.items() if x}
    user.preferencias = pref
    usar(user)
    return {"vistas": pref["vistas"]}


# ---- Columnas de cada tabla ------------------------------------------------------
# Qué columnas ve la persona en cada tabla (dentro de lo que su rol permite).
# Sin preferencia, la tabla muestra su vista inicial corta.
TABLAS = ("ordenes", "seguimiento", "facturas", "productos", "embarques", "factura_lineas", "pl_cajas")


def guardar_columnas(db: Session, user: Usuario, tabla: str, columnas: list | None) -> dict:
    if tabla not in TABLAS:
        raise ErrorNegocio("This table has no column settings.", 404, "no_encontrado")
    pref = dict(user.preferencias or {})
    todas = dict(pref.get("columnas") or {})
    if columnas is None:
        todas.pop(tabla, None)  # vuelve a la vista inicial
    else:
        todas[tabla] = [re.sub(r"[^a-z0-9_]", "", str(c).lower())[:40] for c in columnas[:60] if c]
    pref["columnas"] = todas
    user.preferencias = pref
    usar(user)
    return {"columnas": todas}
