"""Empresa de la instalación: datos generales, preferencias y reglas.

Cada instalación sirve a una sola empresa (registro 1 de `organizaciones`).
Sus preferencias (idioma, moneda, zona horaria…) y reglas de negocio se
guardan en la base de datos y se cambian en Configuración → Empresa; los
valores de `settings` solo son los de fábrica para una instalación nueva.
"""
import re

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.empresa import CAMPOS_COMPATIBILIDAD, REGLAS
from app.core.errores import ErrorNegocio
from app.modelos import Organizacion, Usuario
from app.modulos.acceso.permisos import permisos_de
from app.modulos.comun.historial import registrar

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
    # Nombre y logo van también: los documentos y reportes los usan
    return {**(o.configuracion or {}), "empresa": {"nombre": o.nombre, "logo": o.logo}} if o else {}


# ---- Configuración ------------------------------------------------------------
PREFERENCIAS = {"idioma": "es", "moneda": "USD", "zona_horaria": "UTC", "formato_fecha": "MM/DD/YYYY"}
# Marca: color de la interfaz y de los documentos, nombre del sistema y textos
# de la pantalla de ingreso. Un texto vacío usa el de fábrica (traducido).
MARCA = {"color": "", "titulo": "", "ingreso_titulo": "", "ingreso_texto": "", "ingreso_ayuda": ""}
# Documentos (PDF): tamaño del papel, declaraciones legales de la factura y de
# la lista de empaque y si los reportes llevan el logo de la empresa.
DOCUMENTOS = {"papel": "LETTER", "declaracion_factura": "", "declaracion_packing": "", "logo_en_reportes": True}
PAPELES = ("LETTER", "A4")
# Textos propios: la empresa reemplaza cualquier texto del sistema (pantallas y
# documentos) por su propia terminología, en cada idioma: {"es": {original: texto}}
IDIOMAS_TEXTOS = ("es", "en")
MAX_TEXTOS = 300
LARGOS = {"titulo": 60, "ingreso_titulo": 120, "ingreso_texto": 300, "ingreso_ayuda": 160,
          "declaracion_factura": 1000, "declaracion_packing": 1000}


def _reglas_de(o: Organizacion) -> dict:
    propias = (o.configuracion or {}).get("reglas", {})
    return {k: propias.get(k, getattr(settings, k)) for k in REGLAS}


def _dict(o: Organizacion) -> dict:
    conf = o.configuracion or {}
    return {
        "codigo": o.codigo, "nombre": o.nombre, "razon_social": o.razon_social, "id_fiscal": o.id_fiscal,
        "pais": o.pais, "logo": o.logo,
        "preferencias": {**PREFERENCIAS, **conf.get("preferencias", {})},
        "marca": {**MARCA, **conf.get("marca", {})},
        "documentos": {**DOCUMENTOS, **conf.get("documentos", {})},
        "textos": _textos_de(conf),
        "reglas": [{"clave": k, "texto": t, "valor": v} for (k, t), v in zip(REGLAS.items(), _reglas_de(o).values())],
        # Datos de la OC que pueden entrar en las reglas de compatibilidad
        "campos_compatibilidad": [{"clave": k, "texto": NOMBRES_CAMPO[k]} for k in CAMPOS_COMPATIBILIDAD],
    }


NOMBRES_CAMPO = {"sociedad": "Company", "centro": "Plant", "centro_destino": "Destination plant", "moneda": "Currency",
                 "incoterm": "Incoterm", "puerto_despacho": "Port of loading", "pais_origen": "Country of origin"}


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
    elif isinstance(base, list):
        if not isinstance(valor, list) or any(v not in CAMPOS_COMPATIBILIDAD for v in valor):
            raise ErrorNegocio("Choose PO data from the list.", 422, "validacion")
        valor = [v for v in CAMPOS_COMPATIBILIDAD if v in valor]
    elif clave == "PAIS_BASE_CLASIF":
        if valor in (None, ""):
            return ""
        if not isinstance(valor, str) or not re.fullmatch(r"[A-Za-z]{2}", valor):
            raise ErrorNegocio("Enter the two-letter country code.", 422, "validacion")
        valor = valor.upper()
    return valor


def _textos_de(conf: dict) -> dict:
    return {i: dict((conf.get("textos") or {}).get(i) or {}) for i in IDIOMAS_TEXTOS}


def _validar_textos(textos) -> dict:
    """{idioma: {texto original en inglés: texto propio}}, sin vacíos."""
    if not isinstance(textos, dict) or set(textos) - set(IDIOMAS_TEXTOS):
        raise ErrorNegocio(f"Own texts go by language ({', '.join(IDIOMAS_TEXTOS)}).", 422, "validacion")
    limpio = {}
    for idioma, mapa in textos.items():
        if not isinstance(mapa, dict) or len(mapa) > MAX_TEXTOS:
            raise ErrorNegocio(f"At most {MAX_TEXTOS} own texts per language.", 422, "validacion")
        limpio[idioma] = {}
        for original, propio in mapa.items():
            original, propio = str(original or "").strip(), str(propio or "").strip()
            if not original or not propio:
                continue
            if len(original) > 600 or len(propio) > 600:
                raise ErrorNegocio("An own text is too long (600 characters maximum).", 422, "validacion")
            if sorted(re.findall(r"\{\d\}", original)) != sorted(re.findall(r"\{\d\}", propio)):
                raise ErrorNegocio(f"«{propio}» must keep the same placeholders as «{original}».", 422, "validacion")
            limpio[idioma][original] = propio
    return limpio


def _validar_seccion(base: dict, valores: dict) -> dict:
    """Marca o documentos: solo las claves conocidas, con su tipo y largo."""
    limpio = {}
    for k, v in valores.items():
        if k not in base:
            continue
        if isinstance(base[k], bool):
            if not isinstance(v, bool):
                raise ErrorNegocio("This option is yes or no.", 422, "validacion")
        else:
            v = str(v or "").strip()
            if k == "color" and v and not re.fullmatch(r"#[0-9a-fA-F]{6}", v):
                raise ErrorNegocio("Enter the color as #RRGGBB, for example #3355E0.", 422, "validacion")
            if k == "papel" and v not in PAPELES:
                raise ErrorNegocio(f"The paper size must be one of {', '.join(PAPELES)}.", 422, "validacion")
            if k in LARGOS and len(v) > LARGOS[k]:
                raise ErrorNegocio(f"The text is too long ({LARGOS[k]} characters maximum).", 422, "validacion")
        limpio[k] = v
    return limpio


def publico(db: Session) -> dict:
    """Lo que la pantalla de ingreso muestra antes de iniciar sesión: nombre,
    logo, marca y, solo en la demostración, las cuentas de ejemplo."""
    o = db.get(Organizacion, ID_EMPRESA)
    conf = (o.configuracion or {}) if o else {}
    res = {"nombre": o.nombre if o else None, "logo": o.logo if o else None, "marca": {**MARCA, **conf.get("marca", {})},
           "textos": _textos_de(conf), "demo": None}
    if settings.SEED_DEMO:
        from app.instalacion.demo import CUENTAS_DEMO, PASSWORD_DEMO

        res["demo"] = {"password": PASSWORD_DEMO, "cuentas": CUENTAS_DEMO}
    return res


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
    if "marca" in datos:
        conf["marca"] = _validar_seccion(MARCA, {**conf.get("marca", {}), **(datos["marca"] or {})})
    if "documentos" in datos:
        conf["documentos"] = _validar_seccion(DOCUMENTOS, {**conf.get("documentos", {}), **(datos["documentos"] or {})})
    if "textos" in datos:
        conf["textos"] = _validar_textos(datos["textos"] or {})
    if "reglas" in datos:
        reglas = dict(conf.get("reglas", {}))
        for clave, valor in datos["reglas"].items():
            if clave not in REGLAS:
                raise ErrorNegocio("Unknown rule.", 422, "validacion")
            reglas[clave] = _validar_regla(clave, valor)
        efectiva = {k: reglas.get(k, getattr(settings, k)) for k in ("COMPATIBILIDAD_BLOQUEANTE", "COMPATIBILIDAD_ADVERTENCIA")}
        dobles = set(efectiva["COMPATIBILIDAD_BLOQUEANTE"]) & set(efectiva["COMPATIBILIDAD_ADVERTENCIA"])
        if dobles:
            raise ErrorNegocio("The same PO data cannot block and only warn.", 422, "validacion")
        conf["reglas"] = reglas
    o.configuracion = conf
    registrar(db, user, "organizacion", o.id, "editar_organizacion",
              detalle={"antes": {k: antes[k] for k in ("nombre", "preferencias", "marca", "documentos")},
                       "reglas": conf.get("reglas", {})})
    db.flush()
    return _dict(o)
