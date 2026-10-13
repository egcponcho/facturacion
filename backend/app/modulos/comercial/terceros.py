"""Terceros: clientes, proveedores, transportistas y agentes con una sola
identidad fiscal, sus direcciones y sus medios de contacto.

Un proveedor o un transportista de los datos maestros es la extensión de su
tercero (tercero_id): sus datos de compra o de transporte viven en su tabla y
su identidad, dirección y contacto, en el tercero.
"""
import re

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.errores import ErrorNegocio
from app.modelos import Direccion, MedioContacto, Pais, Tercero, TerceroRol, Usuario
from app.modelos.comercial import ROLES_TERCERO
from app.modulos.acceso.permisos import exigir_alguno
from app.modulos.comun import tabla
from app.modulos.comun.historial import registrar
from app.modulos.comun.texto import filtro_texto

CORREO = re.compile(r"^[^@\s,;]+@[^@\s,;]+\.[^@\s,;]+$")
TIPOS_DIRECCION = ("FISCAL", "ENTREGA", "RECOGIDA", "OTRA")
TIPOS_MEDIO = ("CORREO", "TELEFONO", "MOVIL", "WEB", "OTRO")


def correos(medios) -> list[str]:
    """Correos de una lista de medios de contacto, el principal primero."""
    return [m.valor for m in sorted(medios, key=lambda m: not m.principal) if m.tipo == "CORREO"]


def direccion_fiscal(t: Tercero) -> Direccion | None:
    return next((d for d in sorted(t.direcciones, key=lambda d: (d.tipo != "FISCAL", not d.principal))), None)


def dict_tercero(t: Tercero, completo: bool = False) -> dict:
    d = {"id": t.id, "codigo": t.codigo, "tipo_persona": t.tipo_persona, "nombre": t.nombre, "razon_social": t.razon_social,
         "tipo_identificacion": t.tipo_identificacion, "id_fiscal": t.id_fiscal, "pais": t.pais, "moneda": t.moneda,
         "condicion_pago": t.condicion_pago, "limite_credito": t.limite_credito, "activo": t.activo,
         "roles": sorted(r.rol for r in t.roles), "correo": next(iter(correos(t.medios)), None),
         "direccion": (direccion_fiscal(t).texto() if direccion_fiscal(t) else None)}
    if completo:
        d["direcciones"] = [{"id": x.id, "tipo": x.tipo, "linea1": x.linea1, "linea2": x.linea2, "ciudad": x.ciudad,
                             "region": x.region, "codigo_postal": x.codigo_postal, "pais": x.pais,
                             "principal": x.principal} for x in t.direcciones]
        d["medios"] = [{"id": x.id, "tipo": x.tipo, "valor": x.valor, "uso": x.uso, "principal": x.principal}
                       for x in t.medios]
        d["extra"] = t.extra or {}
    return d


COLUMNAS = {"codigo": Tercero.codigo, "nombre": Tercero.nombre, "pais": Tercero.pais, "moneda": Tercero.moneda,
            "condicion_pago": Tercero.condicion_pago, "activo": Tercero.activo, "id_fiscal": Tercero.id_fiscal,
            "roles": tabla.Relacion(TerceroRol.rol, TerceroRol.tercero_id, Tercero.id)}


def _consulta(user: Usuario, q: str | None, rol: str | None):
    exigir_alguno(user, "comercial.ver", "catalogos.ver")
    c = select(Tercero)
    if rol:
        c = c.where(Tercero.id.in_(select(TerceroRol.tercero_id).where(TerceroRol.rol == rol.upper())))
    if q and q.strip():
        c = c.where(filtro_texto(q, Tercero.codigo, Tercero.nombre, Tercero.razon_social, Tercero.id_fiscal))
    return c


def listar(db: Session, user: Usuario, q=None, rol=None, page=1, size=25, orden=None, filtros=None) -> dict:
    c = tabla.aplicar(_consulta(user, q, rol), COLUMNAS, filtros or {})
    total = db.scalar(select(func.count()).select_from(c.subquery())) or 0
    col, _, dirc = (orden or "").partition(":")
    expr = COLUMNAS.get(col) if col != "roles" else None
    c = c.order_by((expr.desc() if dirc == "desc" else expr.asc()) if expr is not None else Tercero.nombre, Tercero.id)
    filas = db.scalars(c.offset((page - 1) * size).limit(size)).all()
    return {"items": [dict_tercero(t) for t in filas], "total": total}


def valores(db: Session, user: Usuario, columna: str, buscar=None, filtros=None, q=None, rol=None) -> list[dict]:
    expr = tabla.columna_valida(COLUMNAS, columna)
    c = tabla.aplicar(_consulta(user, q, rol), COLUMNAS, filtros or {}, excepto=columna)
    return tabla.valores(db, c, expr, buscar)


def cargar(db: Session, tercero_id: int) -> Tercero:
    t = db.get(Tercero, tercero_id)
    if not t:
        raise ErrorNegocio("The business partner does not exist.", 404, "no_encontrado")
    return t


def detalle(db: Session, user: Usuario, tercero_id: int) -> dict:
    exigir_alguno(user, "comercial.ver", "catalogos.ver")
    return dict_tercero(cargar(db, tercero_id), completo=True)


def _codigo_libre(db: Session, base: str, propio_id: int | None = None) -> str:
    base = re.sub(r"[^A-Z0-9._\-]", "", (base or "").upper())[:26] or "T"
    codigo, n = base, 1
    while (x := db.scalar(select(Tercero.id).where(Tercero.codigo == codigo))) and x != propio_id:
        n += 1
        codigo = f"{base}-{n}"
    return codigo


def _validar(db: Session, datos: dict, actual: Tercero | None) -> list[dict]:
    errores = []
    if "nombre" in datos and not (datos["nombre"] or "").strip():
        errores.append({"campo": "nombre", "mensaje": "Enter the name."})
    if datos.get("tipo_persona") not in (None, "JURIDICA", "NATURAL"):
        errores.append({"campo": "tipo_persona", "mensaje": "Choose legal entity or natural person."})
    if datos.get("pais") and not db.scalar(select(Pais.id).where(Pais.codigo == datos["pais"].upper())):
        errores.append({"campo": "pais", "mensaje": "The country is not in the catalog."})
    for r in datos.get("roles") or []:
        if r not in ROLES_TERCERO:
            errores.append({"campo": "roles", "mensaje": f"Unknown role {r}."})
    if datos.get("id_fiscal"):
        otro = db.scalar(select(Tercero).where(func.upper(Tercero.id_fiscal) == datos["id_fiscal"].upper(),
                                               Tercero.pais.is_(None) if not datos.get("pais") else Tercero.pais == datos["pais"]))
        if otro and (not actual or otro.id != actual.id):
            errores.append({"campo": "id_fiscal", "mensaje": f"{otro.nombre} ({otro.codigo}) already has this tax ID."})
    for i, d in enumerate(datos.get("direcciones") or []):
        if d["tipo"] not in TIPOS_DIRECCION or not (d["linea1"] or "").strip():
            errores.append({"campo": f"direcciones.{i}", "mensaje": "Each address needs its type and first line."})
    for i, m in enumerate(datos.get("medios") or []):
        if m["tipo"] not in TIPOS_MEDIO or not (m["valor"] or "").strip():
            errores.append({"campo": f"medios.{i}", "mensaje": "Each contact channel needs its type and value."})
        elif m["tipo"] == "CORREO" and not CORREO.match(m["valor"].strip()):
            errores.append({"campo": f"medios.{i}", "mensaje": f"{m['valor']} is not a valid email."})
    return errores


def _aplicar(db: Session, t: Tercero, datos: dict) -> None:
    obligatorios = ("tipo_persona", "nombre", "activo", "extra")
    for k in (*obligatorios, "razon_social", "tipo_identificacion", "id_fiscal", "pais", "moneda", "condicion_pago",
              "limite_credito"):
        if k not in datos or (datos[k] is None and k in obligatorios):
            continue
        v = datos[k]
        if isinstance(v, str):
            v = v.strip() or None
            if v and k in ("pais", "moneda", "condicion_pago", "id_fiscal"):
                v = v.upper()
        setattr(t, k, v)
    if datos.get("roles") is not None:
        actuales = {r.rol: r for r in t.roles}
        for rol in set(actuales) - set(datos["roles"]):
            t.roles.remove(actuales[rol])
        for rol in set(datos["roles"]) - set(actuales):
            t.roles.append(TerceroRol(rol=rol))
    if datos.get("direcciones") is not None:
        t.direcciones.clear()
        for d in datos["direcciones"]:
            t.direcciones.append(Direccion(**{**d, "pais": (d.get("pais") or "").upper() or None}))
    if datos.get("medios") is not None:
        t.medios.clear()
        for m in datos["medios"]:
            t.medios.append(MedioContacto(**{**m, "valor": m["valor"].strip()}))


def crear(db: Session, user: Usuario, datos) -> dict:
    exigir_alguno(user, "comercial.editar", "catalogos.crear")
    d = datos.model_dump()
    errores = _validar(db, d, None)
    if errores:
        raise ErrorNegocio("Check the business partner.", 422, "validacion", errores)
    t = Tercero(codigo=_codigo_libre(db, d.get("codigo") or d["nombre"]), nombre=d["nombre"].strip())
    db.add(t)
    _aplicar(db, t, d)
    db.flush()
    registrar(db, user, "tercero", t.id, "crear", {"codigo": t.codigo, "roles": d.get("roles")})
    return dict_tercero(t, completo=True)


def actualizar(db: Session, user: Usuario, tercero_id: int, datos) -> dict:
    exigir_alguno(user, "comercial.editar", "catalogos.editar")
    t = cargar(db, tercero_id)
    d = datos.model_dump(exclude_unset=True)
    errores = _validar(db, d, t)
    if d.get("roles") is not None:
        from app.modelos import Proveedor, Transportista

        if "PROVEEDOR" not in d["roles"] and db.scalar(select(Proveedor.id).where(Proveedor.tercero_id == t.id)):
            errores.append({"campo": "roles", "mensaje": "It is a supplier in master data: it keeps the supplier role."})
        if "TRANSPORTISTA" not in d["roles"] and db.scalar(select(Transportista.id).where(Transportista.tercero_id == t.id)):
            errores.append({"campo": "roles", "mensaje": "It is a carrier in master data: it keeps the carrier role."})
    if "codigo" in d and d["codigo"] and d["codigo"].upper() != t.codigo:
        if db.scalar(select(Tercero.id).where(Tercero.codigo == d["codigo"].upper())):
            errores.append({"campo": "codigo", "mensaje": "Another business partner has this code."})
        else:
            t.codigo = d["codigo"].upper()
    if errores:
        raise ErrorNegocio("Check the business partner.", 422, "validacion", errores)
    antes = dict_tercero(t)
    _aplicar(db, t, d)
    db.flush()
    sincronizar_extensiones(db, t)
    cambios = {k: [antes[k], v] for k, v in dict_tercero(t).items() if antes.get(k) != v}
    if cambios:
        registrar(db, user, "tercero", t.id, "editar", cambios)
    return dict_tercero(t, completo=True)


# ---- Proveedores y transportistas de los datos maestros ----------------------------------------
def asegurar(db: Session, obj, rol: str) -> Tercero:
    """El tercero de un proveedor o transportista (se crea si no tiene) con su rol."""
    t = db.get(Tercero, obj.tercero_id) if obj.tercero_id else None
    if t is None and getattr(obj, "id_fiscal", None):
        t = db.scalar(select(Tercero).where(func.upper(Tercero.id_fiscal) == obj.id_fiscal.upper(),
                                            or_(Tercero.pais == obj.pais, Tercero.pais.is_(None) & (obj.pais is None))))
    if t is None:
        t = Tercero(codigo=_codigo_libre(db, obj.codigo), nombre=obj.nombre, activo=True)
        db.add(t)
    t.nombre = obj.nombre
    for k in ("razon_social", "id_fiscal", "pais"):
        if getattr(obj, k, None):
            setattr(t, k, getattr(obj, k))
    if not t.tiene_rol(rol):
        t.roles.append(TerceroRol(rol=rol))
    db.flush()
    obj.tercero_id = t.id
    return t


def sincronizar_extensiones(db: Session, t: Tercero) -> None:
    """La identidad editada en el tercero llega a su proveedor y transportista."""
    from app.modelos import Proveedor, Transportista

    for modelo in (Proveedor, Transportista):
        for obj in db.scalars(select(modelo).where(modelo.tercero_id == t.id)):
            obj.nombre = t.nombre
            for k in ("razon_social", "id_fiscal", "pais"):
                if hasattr(obj, k):
                    setattr(obj, k, getattr(t, k))
