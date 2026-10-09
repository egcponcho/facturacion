"""Organización de la petición: datos generales, preferencias y reglas.

Cada organización (empresa cliente) guarda sus preferencias (idioma, moneda,
zona horaria…), marca, terminología, campos propios, módulos y reglas de
negocio en la base de datos, y se cambian en Configuración → Empresa; los
valores de `settings` solo son los de fábrica. Una instalación de una sola
empresa usa la organización 1.
"""
import re

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import campos_propios, organizacion
from app.core.archivos import imagen_data_url
from app.core.config import settings
from app.core.empresa import CAMPOS_COMPATIBILIDAD, REGLAS
from app.core.errores import ErrorNegocio
from app.modelos import Organizacion, Usuario
from app.modulos.acceso.permisos import MODULOS_ACTIVABLES, exigir
from app.modulos.comun.historial import registrar


def asegurar_principal(db: Session, nombre: str = "My company") -> Organizacion:
    """La organización principal existe siempre (instalación nueva o demostración)."""
    o = db.get(Organizacion, organizacion.PRINCIPAL)
    if not o:
        o = Organizacion(id=organizacion.PRINCIPAL, codigo="MAIN", nombre=nombre, configuracion={})
        db.add(o)
        db.flush()
    return o


def configuracion(db: Session) -> dict:
    """Configuración guardada de la organización de la sesión (vacía si aún no existe)."""
    o = db.get(Organizacion, organizacion.de_sesion(db) or organizacion.PRINCIPAL)
    if not o:
        return {}
    # Nombre y logo van también: los documentos y reportes los usan. Con más de
    # una organización activa, los datos compartidos solo los cambia la plataforma.
    varias = (db.scalar(select(func.count()).select_from(Organizacion).where(Organizacion.activa.is_(True))) or 0) > 1
    return {**(o.configuracion or {}), "empresa": {"id": o.id, "nombre": o.nombre, "logo": o.logo},
            "varias_organizaciones": varias}


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
        "campos_propios": {e: (conf.get("campos_propios") or {}).get(e, []) for e in campos_propios.ENTIDADES},
        "entidades_campos": [{"clave": k, "texto": v} for k, v in campos_propios.ENTIDADES.items()],
        "tipos_campos": [{"clave": k, "texto": v} for k, v in campos_propios.TIPOS.items()],
        "modulos": [{"clave": k, "texto": texto, "activo": activo} for (k, (texto, _)), activo
                    in zip(MODULOS_ACTIVABLES.items(), _modulos_de(conf).values(), strict=False)],
        "reglas": [{"clave": k, "texto": t, "valor": v} for (k, t), v in zip(REGLAS.items(), _reglas_de(o).values(), strict=False)],
        # Datos de la OC que pueden entrar en las reglas de compatibilidad
        "campos_compatibilidad": [{"clave": k, "texto": NOMBRES_CAMPO[k]} for k in CAMPOS_COMPATIBILIDAD],
        "aprobaciones_oc": conf.get("aprobaciones_oc") or [],
        "obligatorios": {"orden": (conf.get("obligatorios") or {}).get("orden") or []},
        "campos_obligables": [{"clave": k, "texto": v} for k, v in CAMPOS_OBLIGABLES_OC.items()],
    }


# Datos de la OC que la empresa puede volver obligatorios (además de los que
# el flujo siempre exige: proveedor, número, sociedad, artículos, cantidades,
# moneda, precios y fecha de despacho)
CAMPOS_OBLIGABLES_OC = {"fecha": "PO date", "incoterm": "Incoterm", "condicion_pago": "Payment terms",
                        "centro": "Receiving plant", "centro_destino": "Destination plant",
                        "puerto_despacho": "Port of loading", "pais_origen": "Country of origin",
                        "fecha_tienda": "In-store date"}
MAX_REGLAS_APROBACION = 20


def _validar_aprobaciones(db: Session, reglas) -> list[dict]:
    """Reglas de aprobación de OCs: desde qué monto, en qué moneda (y
    sociedad, opcional) aprueba qué rol."""
    from app.core import listas
    from app.modelos import Rol

    if not isinstance(reglas, list) or len(reglas) > MAX_REGLAS_APROBACION:
        raise ErrorNegocio(f"Up to {MAX_REGLAS_APROBACION} approval rules.", 422, "validacion")
    limpias = []
    for i, r in enumerate(reglas, start=1):
        r = r if isinstance(r, dict) else {}
        nombre = str(r.get("nombre") or "").strip()[:80]
        moneda = str(r.get("moneda") or "").strip().upper()
        try:
            monto = float(r.get("monto_minimo") or 0)
        except (TypeError, ValueError):
            monto = -1
        rol = db.get(Rol, int(r["rol_id"])) if str(r.get("rol_id") or "").isdigit() else None
        if not nombre or monto < 0 or moneda not in listas.codigos("moneda") or not rol or not rol.activo:
            raise ErrorNegocio(f"Approval rule {i}: it needs a name, a minimum amount (0 or more), a currency of the list "
                               "and an active role that approves.", 422, "validacion")
        limpias.append({"nombre": nombre, "monto_minimo": monto, "moneda": moneda,
                        "sociedad": str(r.get("sociedad") or "").strip().upper()[:10] or None, "rol_id": rol.id})
    return sorted(limpias, key=lambda r: r["monto_minimo"])


NOMBRES_CAMPO = {"sociedad": "Company", "centro": "Plant", "centro_destino": "Destination plant", "moneda": "Currency",
                 "incoterm": "Incoterm", "puerto_despacho": "Port of loading", "pais_origen": "Country of origin"}


def actual(db: Session) -> Organizacion:
    org = organizacion.de_sesion(db)
    return db.get(Organizacion, org) if org else asegurar_principal(db)


def detalle(db: Session, user: Usuario) -> dict:
    exigir(user, "admin")
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


def _modulos_de(conf: dict) -> dict[str, bool]:
    return {k: (conf.get("modulos") or {}).get(k, True) is not False for k in MODULOS_ACTIVABLES}


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
    o = db.get(Organizacion, organizacion.PRINCIPAL)
    conf = (o.configuracion or {}) if o else {}
    res = {"nombre": o.nombre if o else None, "logo": o.logo if o else None, "marca": {**MARCA, **conf.get("marca", {})},
           "textos": _textos_de(conf), "demo": None}
    if settings.SEED_DEMO:
        from app.instalacion.demo import CUENTAS_DEMO, PASSWORD_DEMO

        res["demo"] = {"password": PASSWORD_DEMO, "cuentas": CUENTAS_DEMO}
    return res


def actualizar(db: Session, user: Usuario, datos: dict) -> dict:
    """Datos generales, preferencias y reglas de la empresa (administración)."""
    exigir(user, "admin")
    o = actual(db)
    antes = _dict(o)
    for campo in ("nombre", "razon_social", "id_fiscal", "pais", "logo"):
        if campo in datos:
            valor = datos[campo] or None
            if campo == "nombre" and not valor:
                raise ErrorNegocio("The company needs a name.", 422, "validacion")
            if campo == "logo" and valor:
                imagen_data_url(valor, 300 * 1024)
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
    if "campos_propios" in datos:
        conf["campos_propios"] = campos_propios.validar_definiciones(datos["campos_propios"] or {})
    if "modulos" in datos:
        modulos = datos["modulos"] or {}
        if not isinstance(modulos, dict) or set(modulos) - set(MODULOS_ACTIVABLES) \
                or any(not isinstance(v, bool) for v in modulos.values()):
            raise ErrorNegocio("Choose the modules to turn on or off.", 422, "validacion")
        conf["modulos"] = {**_modulos_de(conf), **modulos}
    if "aprobaciones_oc" in datos:
        conf["aprobaciones_oc"] = _validar_aprobaciones(db, datos["aprobaciones_oc"] or [])
    if "obligatorios" in datos:
        orden = (datos["obligatorios"] or {}).get("orden") or []
        if not isinstance(orden, list) or set(orden) - set(CAMPOS_OBLIGABLES_OC):
            raise ErrorNegocio("Choose the PO data that becomes required.", 422, "validacion")
        conf["obligatorios"] = {"orden": [c for c in CAMPOS_OBLIGABLES_OC if c in orden]}
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
              detalle={"antes": {k: antes[k] for k in ("nombre", "preferencias", "marca", "documentos", "aprobaciones_oc",
                                                       "obligatorios")},
                       "reglas": conf.get("reglas", {})})
    db.flush()
    return _dict(o)
