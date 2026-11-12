"""Mantenimiento de datos maestros desde un solo lugar.

Cada catálogo se describe una vez (campos, tipos, obligatorios, filtros) y
el mismo código sirve para listar, filtrar, ordenar, crear, editar y
eliminar. La interfaz usa esa misma descripción para dibujar formularios y
tablas, así que agregar un campo aquí lo agrega en pantalla.
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import listas
from app.core.campos_propios import definiciones as campos_propios_def
from app.core.errores import ErrorNegocio
from app.modelos import (
    Articulo,
    Atributo,
    Contacto,
    Usuario,
)
from app.modulos.acceso.permisos import exigir
from app.modulos.maestros import atributos as atr_svc
from app.modulos.maestros import gobierno
from app.modulos.maestros.campos_catalogo import c
from app.modulos.maestros.definiciones import CATALOGOS, ORDEN_CATALOGOS


def catalogo_de(tipo: str) -> dict:
    if tipo not in CATALOGOS:
        raise ErrorNegocio("The catalog does not exist.", 404, "no_encontrado")
    return CATALOGOS[tipo]


def exigir_editable(tipo: str) -> None:
    """Un catálogo de solo consulta (se mantiene en otro módulo) no se cambia aquí."""
    if catalogo_de(tipo).get("solo_lectura"):
        raise ErrorNegocio("This catalog is maintained in its own module.", 409, "solo_lectura")


def texto_registro(obj) -> str:
    """Texto corto para mostrar un registro referido."""
    if isinstance(obj, Contacto):
        return obj.nombre
    for a, b in (("codigo", "nombre"), ("sku", "descripcion"), ("codigo", "descripcion")):
        if hasattr(obj, a):
            extra = getattr(obj, b, None)
            return f"{getattr(obj, a)} · {extra}" if extra else str(getattr(obj, a))
    return str(obj.id)


def opciones_campo(campo: dict) -> list[list[str]]:
    """Opciones de un campo: las de su lista de valores o las fijas."""
    if campo.get("lista"):
        return listas.opciones(campo["lista"]) + campo.get("opciones_extra", [])
    return campo.get("opciones", [])


def tipo_de(cat: dict) -> str:
    return next(k for k, v in CATALOGOS.items() if v is cat)


def campos_variante(cat: dict) -> list[dict]:
    """Atributos de variante de la empresa (talla, color, voltaje…) como campos
    «atr.<código>» del artículo; se guardan en articulo_atributos."""
    from app.core.empresa import configuracion_actual

    if cat["modelo"] is not Articulo:
        return []
    res = []
    for x in configuracion_actual().get("atributos") or []:
        if x.get("nivel") != "VARIANTE":
            continue
        tipo = x.get("tipo") or "texto"
        extra = ({"opciones": [[o, o] for o in atr_svc.opciones(x)]} if tipo == "opcion"
                 else {"ayuda": f"Number in {x['unidad']}."} if tipo == "numero" and x.get("unidad") else {})
        res.append(c(f"atr.{x['codigo']}", x["nombre"], "opcion" if tipo == "opcion" else "texto", max=60, propio=True,
                     seccion="variante", filtro=True, **extra))
    return res


def campos_propios(cat: dict) -> list[dict]:
    """Campos propios de la empresa para este catálogo (core/campos_propios.py),
    como campos «extra.<clave>» que se guardan en la columna extra."""
    if not hasattr(cat["modelo"], "extra"):
        return []
    return [c(f"extra.{x['clave']}", x["etiqueta"], x["tipo"], x["obligatorio"], propio=True,
              **({"opciones": [[o, o] for o in x["opciones"]]} if x["tipo"] == "opcion" else {}))
            for x in campos_propios_def(tipo_de(cat))]


# Sección de cada dato en el formulario (primero lo común, al final lo propio
# de la empresa). Un dato que no está aquí va en «general».
SECCION_CAMPO = {
    **dict.fromkeys(("proveedor_id", "marcas", "sociedades", "sociedad_id", "centro_id", "moneda", "unidad"), "comercial"),
    **dict.fromkeys(("pais", "puerto", "puertos", "region", "peso_unitario"), "logistica"),
    **dict.fromkeys(("direccion", "contacto", "correos", "telefono", "cargo", "rol"), "contacto"),
    **dict.fromkeys(("activo", "activa", "predeterminada", "predeterminado"), "estado"),
}


def es_obligatorio(cat: dict, campo: dict) -> bool:
    """Obligatorio por el sistema o porque la empresa lo pide (gobierno)."""
    return campo["obligatorio"] or campo["nombre"] in gobierno.obligatorios(tipo_de(cat))


def campos_con_opciones(cat: dict) -> list[dict]:
    """Campos del catálogo con las opciones de las listas de la empresa, su
    sección, si la empresa los volvió obligatorios y los campos propios."""
    extra = gobierno.obligatorios(tipo_de(cat))
    campos = []
    for x in cat["campos"]:
        y = {**x, "seccion": x.get("seccion") or SECCION_CAMPO.get(x["nombre"], "general")}
        if x["tipo"] in ("opcion", "opciones"):
            y["opciones"] = opciones_campo(x)
        if x["nombre"] in extra:
            y["obligatorio"] = True
            y["obligatorio_empresa"] = True
        campos.append(y)
    return campos + campos_variante(cat) + [{**x, "seccion": "propios"} for x in campos_propios(cat)]


def meta(db: Session, user: Usuario) -> list[dict]:
    exigir(user, "catalogos.ver")
    return [{"tipo": t, "titulo": CATALOGOS[t]["titulo"], "singular": CATALOGOS[t]["singular"],
             "ayuda": CATALOGOS[t].get("ayuda"), "campos": campos_con_opciones(CATALOGOS[t]),
             "extras": CATALOGOS[t].get("extras", []),
             "total": db.scalar(select(func.count()).select_from(CATALOGOS[t]["modelo"])) or 0,
             "puede": gobierno.puede(user, t),
             "gobierno": gobierno.resumen(db, t, _campos_gobierno(db, t))}
            for t in ORDEN_CATALOGOS]


def _campos_gobierno(db: Session, tipo: str) -> list[dict]:
    """Datos que la empresa puede volver obligatorios: los del catálogo y, en artículos, cada
    atributo de producto o de variante («atributo.<código>»)."""
    campos = CATALOGOS[tipo]["campos"]
    if tipo != "articulos":
        return campos
    return campos + [{"nombre": f"atributo.{a.codigo}", "etiqueta": a.nombre, "tipo": "texto", "obligatorio": False}
                     for a in db.scalars(select(Atributo).where(Atributo.activo.is_(True))
                                         .order_by(Atributo.nivel, Atributo.orden, Atributo.codigo))]


def guardar_gobierno(db: Session, user: Usuario, tipo: str, datos: dict) -> dict:
    """Responsables y datos obligatorios del catálogo (administración)."""
    catalogo_de(tipo)
    return gobierno.guardar(db, user, tipo, _campos_gobierno(db, tipo), datos)


def historial(db: Session, user: Usuario, tipo: str, obj_id: int) -> list[dict]:
    """Cambios de un registro: quién, cuándo y qué cambió (gobierno del dato)."""
    from app.modelos import Historial

    exigir(user, "catalogos.ver")
    cat = catalogo_de(tipo)
    if not db.get(cat["modelo"], obj_id):
        raise ErrorNegocio(f"The {cat['singular']} does not exist.", 404, "no_encontrado")
    filas = db.scalars(select(Historial).where(Historial.entidad == tipo, Historial.entidad_id == obj_id)
                       .order_by(Historial.fecha.desc(), Historial.id.desc()).limit(200)).all()
    res = []
    for h in filas:
        if h.accion == "eliminar":  # lo anterior es de un registro borrado que tuvo el mismo id
            break
        res.append({"id": h.id, "fecha": h.fecha, "accion": h.accion, "detalle": h.detalle, "motivo": h.motivo,
                    "usuario": h.usuario.nombre if h.usuario else None})
    return res


