"""Empresas (organizaciones): aislamiento de datos y configuración.

- Filtro central: toda consulta del ORM (incluidas las cargas de relaciones y
  los UPDATE/DELETE masivos) se limita a la empresa de la petición. Así ningún
  listado, búsqueda, tablero ni exporte ve datos de otra empresa, aunque la
  ruta no lo pida.
- Configuración por empresa: datos generales, preferencias (idioma, moneda…)
  y reglas de negocio (antes variables de entorno), con su valor de fábrica.
- Quien administra la plataforma crea empresas y entra a cualquiera; los demás
  trabajan siempre en la suya.
"""
import re

from sqlalchemy import event, func, select
from sqlalchemy.orm import Session, with_loader_criteria

from ..config import settings
from ..models import DeOrganizacion, Organizacion, SesionUsuario, Usuario
from ..tenencia import REGLAS, en_organizacion, org_actual
from .common import ErrorNegocio, permisos_de, registrar


@event.listens_for(Session, "do_orm_execute")
def _solo_la_empresa(estado) -> None:
    org = org_actual()
    if org is None or estado.is_column_load or estado.execution_options.get("sin_filtro_empresa"):
        return
    if estado.is_select or estado.is_update or estado.is_delete:
        estado.statement = estado.statement.options(
            with_loader_criteria(DeOrganizacion, lambda cls: cls.organizacion_id == org, include_aliases=True))


def empresa_de(db: Session, user: Usuario, token_hash: str | None = None) -> int:
    """Empresa en la que trabaja la petición: la elegida en la sesión (solo
    quien administra la plataforma) o la del usuario."""
    if user.plataforma and token_hash:
        org = db.scalar(select(SesionUsuario.organizacion_id).where(SesionUsuario.token_hash == token_hash))
        if org:
            return org
    return user.organizacion_id


def asegurar_principal(db: Session, nombre: str = "Main company") -> Organizacion:
    """La empresa 1 existe siempre (instalación nueva o demostración)."""
    o = db.get(Organizacion, 1)
    if not o:
        o = Organizacion(id=1, codigo="MAIN", nombre=nombre, configuracion={})
        db.add(o)
        db.flush()
    return o


# ---- Configuración ------------------------------------------------------------
PREFERENCIAS = {"idioma": "en", "moneda": "USD", "zona_horaria": "America/El_Salvador", "formato_fecha": "MM/DD/YYYY"}


def _reglas_de(o: Organizacion) -> dict:
    propias = (o.configuracion or {}).get("reglas", {})
    return {k: propias.get(k, getattr(settings, k)) for k in REGLAS}


def _dict(o: Organizacion) -> dict:
    conf = o.configuracion or {}
    return {
        "id": o.id, "codigo": o.codigo, "nombre": o.nombre, "razon_social": o.razon_social, "id_fiscal": o.id_fiscal,
        "pais": o.pais, "logo": o.logo, "activa": o.activa,
        "preferencias": {**PREFERENCIAS, **conf.get("preferencias", {})},
        "reglas": [{"clave": k, "texto": t, "valor": v} for (k, t), v in zip(REGLAS.items(), _reglas_de(o).values())],
    }


def actual(db: Session) -> Organizacion:
    o = db.get(Organizacion, org_actual() or 1)
    if not o:
        raise ErrorNegocio("The company does not exist.", 404, "no_encontrado")
    return o


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


# ---- Plataforma: varias empresas ------------------------------------------------
def _exigir_plataforma(user: Usuario) -> None:
    if not user.plataforma:
        raise ErrorNegocio("Only the platform administrator can manage companies.", 403, "sin_permiso")


def listar(db: Session, user: Usuario) -> list[dict]:
    _exigir_plataforma(user)
    usuarios = dict(db.execute(select(Usuario.organizacion_id, func.count(Usuario.id))
                               .execution_options(sin_filtro_empresa=True).group_by(Usuario.organizacion_id)).all())
    return [{**_dict(o), "usuarios": usuarios.get(o.id, 0)}
            for o in db.scalars(select(Organizacion).order_by(Organizacion.nombre))]


def crear(db: Session, user: Usuario, datos: dict) -> dict:
    """Empresa nueva con su administrador inicial y sus roles de fábrica."""
    _exigir_plataforma(user)
    codigo = (datos.get("codigo") or "").strip().upper()
    nombre = (datos.get("nombre") or "").strip()
    email = (datos.get("admin_email") or "").strip().lower()
    if not re.fullmatch(r"[A-Z0-9_-]{2,20}", codigo):
        raise ErrorNegocio("The code has 2 to 20 letters, numbers, - or _.", 422, "validacion")
    if not nombre:
        raise ErrorNegocio("The company needs a name.", 422, "validacion")
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise ErrorNegocio("Enter the email of the company administrator.", 422, "validacion")
    if db.scalar(select(Organizacion).where(Organizacion.codigo == codigo)):
        raise ErrorNegocio(f"A company with code {codigo} already exists.", 409, "duplicado")
    if db.scalar(select(Usuario).where(func.lower(Usuario.email) == email).execution_options(sin_filtro_empresa=True)):
        raise ErrorNegocio("That email already has a user.", 409, "duplicado")
    o = Organizacion(codigo=codigo, nombre=nombre, razon_social=datos.get("razon_social") or None,
                     pais=(datos.get("pais") or "").upper() or None, configuracion={})
    db.add(o)
    db.flush()
    from ..security import hash_password
    from .acceso import password_temporal
    from .varios import crear_roles_fabrica

    clave = password_temporal()
    with en_organizacion(o.id):
        roles = crear_roles_fabrica(db)
        db.add(Usuario(email=email, nombre=datos.get("admin_nombre") or "Administrator", rol="admin",
                       rol_id=roles["admin"].id, password_hash=hash_password(clave), clave_temporal=True,
                       dos_pasos=False, empresa=nombre))
        db.flush()
    registrar(db, user, "organizacion", o.id, "crear_organizacion", detalle={"codigo": codigo, "admin": email})
    db.flush()
    return {**_dict(o), "admin_email": email, "clave_temporal": clave}


def entrar(db: Session, user: Usuario, token_hash: str, organizacion_id: int) -> dict:
    """Quien administra la plataforma trabaja en otra empresa (esta sesión)."""
    _exigir_plataforma(user)
    o = db.get(Organizacion, organizacion_id)
    if not o or not o.activa:
        raise ErrorNegocio("The company does not exist or is inactive.", 404, "no_encontrado")
    s = db.scalar(select(SesionUsuario).where(SesionUsuario.token_hash == token_hash))
    s.organizacion_id = None if o.id == user.organizacion_id else o.id
    db.flush()
    return {"id": o.id, "nombre": o.nombre}
