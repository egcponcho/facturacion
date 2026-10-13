"""Perfiles de importación de OCs (Cargar órdenes de compra → Perfiles).

Cada ERP exporta sus columnas con otros nombres, en otra fila o con otro
formato de fecha. Un perfil dice cómo leer ese archivo: el nombre de la
columna de cada dato del sistema (tiene prioridad sobre los nombres que el
sistema reconoce solo), la fila de los encabezados, el formato de las fechas
y los valores por defecto de lo que el archivo no trae.
"""
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.errores import ErrorNegocio
from app.modelos import PerfilImportacion, Usuario
from app.modulos.acceso.permisos import exigir
from app.modulos.acceso.preferencias import FORMATOS_FECHA
from app.modulos.comun.historial import registrar

# Datos del archivo de OCs, en el orden de la plantilla
ETIQUETAS = {
    "proveedor": "Supplier code", "oc": "PO number", "posicion": "PO line", "sociedad": "Company", "centro": "Plant",
    "almacen": "Storage location", "centro_destino": "Destination plant", "moneda": "Currency", "incoterm": "Incoterm",
    "fecha_oc": "PO date", "puerto_despacho": "Port of loading", "pais_origen": "Country of origin",
    "pais_procedencia": "Country of shipment", "fecha_xf_original": "Original XF date",
    "fecha_xf": "XF date", "fecha_tienda": "In-store date", "liberacion_comercial": "Commercial release",
    "liberacion_logistica": "Logistics release", "fecha_lib_comercial": "Commercial release date",
    "fecha_lib_logistica": "Logistics release date", "codigo_sap": "Item code", "cantidad": "Quantity",
    "unidad": "Unit", "precio": "Unit price", "casepack": "Casepack", "inner_pack": "Inner pack",
    "fecha_entrega": "Delivery date",
}
# Lo que identifica una línea no puede tener un valor por defecto
SIN_DEFECTO = {"proveedor", "oc", "posicion", "codigo_sap", "cantidad"}


def campos() -> list[dict]:
    """Datos que un perfil puede mapear, con los nombres que el sistema ya reconoce."""
    from app.core.campos_propios import definiciones
    from app.modulos.compras.ordenes import ALIAS, REQUERIDOS

    return [{"campo": c, "etiqueta": ETIQUETAS[c], "requerido": c in REQUERIDOS, "reconocidos": ALIAS[c],
             "fecha": c.startswith("fecha"), "admite_defecto": c not in SIN_DEFECTO} for c in ALIAS] + [
        # Campos propios de las OCs (Configuración → Empresa → Campos propios)
        {"campo": f"extra.{c['clave']}", "etiqueta": c["etiqueta"], "requerido": False, "reconocidos": [c["clave"]],
         "fecha": c["tipo"] == "fecha", "admite_defecto": True} for c in definiciones("ordenes")]


def _dict(p: PerfilImportacion) -> dict:
    return {"id": p.id, "codigo": p.codigo, "nombre": p.nombre, "columnas": p.columnas or {}, "valores": p.valores or {},
            "fila_encabezado": p.fila_encabezado, "formato_fecha": p.formato_fecha, "predeterminado": p.predeterminado,
            "activo": p.activo}


def listar(db: Session, user: Usuario) -> dict:
    exigir(user, "oc.importar")
    perfiles = db.scalars(select(PerfilImportacion).order_by(PerfilImportacion.nombre)).all()
    return {"perfiles": [_dict(p) for p in perfiles], "campos": campos(), "formatos_fecha": list(FORMATOS_FECHA)}


def _texto(v, largo: int) -> str:
    return str(v or "").strip()[:largo]


def _validar(db: Session, datos: dict, actual: PerfilImportacion | None) -> dict:
    validos = {c["campo"] for c in campos()}
    limpio, errores = {}, []
    if "codigo" in datos or not actual:
        codigo = _texto(datos.get("codigo"), 20).upper()
        if not codigo:
            errores.append({"campo": "codigo", "mensaje": "Code is required."})
        elif db.scalar(select(PerfilImportacion.id).where(PerfilImportacion.codigo == codigo,
                                                         PerfilImportacion.id != (actual.id if actual else 0))):
            errores.append({"campo": "codigo", "mensaje": "There is already a profile with that code."})
        limpio["codigo"] = codigo
    if "nombre" in datos or not actual:
        limpio["nombre"] = _texto(datos.get("nombre"), 80)
        if not limpio["nombre"]:
            errores.append({"campo": "nombre", "mensaje": "Name is required."})
    if "columnas" in datos:
        cols = datos["columnas"] or {}
        if not isinstance(cols, dict) or set(cols) - validos:
            errores.append({"campo": "columnas", "mensaje": "Map only the data of the PO file."})
        else:
            limpio["columnas"] = {k: _texto(v, 200) for k, v in cols.items() if _texto(v, 200)}
    if "valores" in datos:
        vals = datos["valores"] or {}
        if not isinstance(vals, dict) or set(vals) - (validos - SIN_DEFECTO):
            errores.append({"campo": "valores", "mensaje": "The supplier, PO, line, item and quantity cannot have a default value."})
        else:
            limpio["valores"] = {k: _texto(v, 100) for k, v in vals.items() if _texto(v, 100)}
    if "fila_encabezado" in datos:
        fila = datos["fila_encabezado"]
        if not isinstance(fila, int) or isinstance(fila, bool) or not 1 <= fila <= 50:
            errores.append({"campo": "fila_encabezado", "mensaje": "The header row is a number from 1 to 50."})
        else:
            limpio["fila_encabezado"] = fila
    if "formato_fecha" in datos:
        formato = datos["formato_fecha"] or None
        if formato and formato not in FORMATOS_FECHA:
            errores.append({"campo": "formato_fecha", "mensaje": f"The date format must be one of {', '.join(FORMATOS_FECHA)}."})
        limpio["formato_fecha"] = formato
    for k in ("predeterminado", "activo"):
        if k in datos:
            limpio[k] = bool(datos[k])
    if errores:
        raise ErrorNegocio("Check the import profile.", 422, "validacion", errores)
    return limpio


def _unico_predeterminado(db: Session, p: PerfilImportacion) -> None:
    if p.predeterminado:
        db.execute(update(PerfilImportacion).where(PerfilImportacion.id != p.id).values(predeterminado=False))


def crear(db: Session, user: Usuario, datos: dict) -> dict:
    exigir(user, "oc.importar")
    p = PerfilImportacion(**{"columnas": {}, "valores": {}, "fila_encabezado": 1, **_validar(db, datos, None)})
    db.add(p)
    db.flush()
    _unico_predeterminado(db, p)
    registrar(db, user, "perfil_importacion", p.id, "crear", {"codigo": p.codigo})
    return _dict(p)


def _perfil(db: Session, perfil_id: int) -> PerfilImportacion:
    p = db.get(PerfilImportacion, perfil_id)
    if not p:
        raise ErrorNegocio("The import profile does not exist.", 404, "no_encontrado")
    return p


def actualizar(db: Session, user: Usuario, perfil_id: int, datos: dict) -> dict:
    exigir(user, "oc.importar")
    p = _perfil(db, perfil_id)
    for k, v in _validar(db, datos, p).items():
        setattr(p, k, v)
    db.flush()
    _unico_predeterminado(db, p)
    registrar(db, user, "perfil_importacion", p.id, "editar", {"codigo": p.codigo})
    return _dict(p)


def eliminar(db: Session, user: Usuario, perfil_id: int) -> dict:
    exigir(user, "oc.importar")
    p = _perfil(db, perfil_id)
    db.delete(p)
    registrar(db, user, "perfil_importacion", perfil_id, "eliminar", {"codigo": p.codigo})
    return {"ok": True}


def elegido(db: Session, perfil_id: int | None) -> PerfilImportacion | None:
    """El perfil pedido, o el predeterminado activo (o ninguno)."""
    if perfil_id:
        p = _perfil(db, perfil_id)
        if not p.activo:
            raise ErrorNegocio("The import profile is inactive.", 422, "validacion")
        return p
    return db.scalar(select(PerfilImportacion).where(PerfilImportacion.predeterminado.is_(True),
                                                     PerfilImportacion.activo.is_(True)))


def fecha_iso(valor: str, formato: str) -> str:
    """Una fecha escrita en el formato del perfil, en ISO (o tal cual si no lo cumple)."""
    try:
        return datetime.strptime(valor.strip(), FORMATOS_FECHA[formato]).date().isoformat()
    except (ValueError, KeyError):
        return valor
