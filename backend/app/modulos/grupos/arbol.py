"""El árbol de grupos de producto, común a quien lo usa (etiquetado, reglas de
empaque…): a qué grupo pertenece un artículo, su ruta de lo más específico a
lo más general (lo que recorren las reglas), si un código está libre, qué usa
un nodo y el mantenimiento desde Datos maestros → Grupos de producto.

Las familias y categorías del etiquetado son estos mismos nodos: sus pantallas
siguen editándolos con sus propios servicios (etiquetado/familias.py y
categorias.py), que validan con lo de aquí.
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errores import ErrorNegocio
from app.modelos import (
    Articulo,
    GeneracionItem,
    GrupoArticulo,
    GrupoCategoria,
    GrupoFamilia,
    GrupoProducto,
    Producto,
    ReglaEmpaque,
    UsoDiseno,
    Usuario,
)
from app.modelos.grupos import CLASES_GRUPO
from app.modulos.acceso.permisos import exigir_alguno
from app.modulos.comun.condiciones import cumple_condicion
from app.modulos.comun.historial import registrar

PERMISOS_VER = ("catalogos.ver", "etiquetas.familias")
PERMISOS_EDITAR = ("catalogos.editar", "etiquetas.familias")


# ---- Pertenencia y ruta ----------------------------------------------------------------------
def categoria_de(db: Session, a: Articulo | None, valores: dict, cache: dict | None = None) -> GrupoCategoria | None:
    """La categoría de un artículo: la puesta a mano en su producto o, si no, la
    primera que se reconoce por sus condiciones, empezando por la familia más
    específica y en el orden de cada familia. Una categoría sin condiciones solo
    se pone a mano."""
    if a is None or a.familia_efectiva is None:
        return None
    familias = [f.id for f in reversed(a.familia_efectiva.ruta())]
    manual = a.producto.grupo_producto if a.producto is not None else None
    if manual is not None and manual.clase == "CATEGORIA":
        # La de su producto, si es de la familia del artículo o de una superior (un artículo puede tener su propia familia)
        return manual if manual.activa and manual.padre_id in familias else None
    clave = ("cats", tuple(familias))
    if cache is None or clave not in cache:
        cats = list(db.scalars(select(GrupoCategoria).where(GrupoCategoria.padre_id.in_(familias),
                                                            GrupoCategoria.activa.is_(True))))
        cats.sort(key=lambda c: (familias.index(c.padre_id), c.orden, c.id))
        if cache is None:
            cache = {}
        cache[clave] = cats
    return next((c for c in cache[clave] if c.condiciones and all(cumple_condicion(x, valores) for x in c.condiciones)), None)


def ruta_efectiva(db: Session, a: Articulo | None, valores: dict, cache: dict | None = None) -> list[GrupoProducto]:
    """Los grupos del artículo de lo más específico a lo más general: su
    categoría (si tiene), su familia y las familias de arriba. Es lo que
    recorren las reglas de etiquetado y de empaque."""
    if a is None or a.familia_efectiva is None:
        return []
    cat = categoria_de(db, a, valores, cache)
    return ([cat] if cat is not None else []) + list(reversed(a.familia_efectiva.ruta()))


# ---- Validación común ------------------------------------------------------------------------
def codigo_ocupado(db: Session, codigo: str, excepto_id: int | None = None) -> bool:
    """Otro nodo (familia o categoría) ya tiene el código."""
    return bool(db.scalar(select(GrupoProducto.id).where(func.upper(GrupoProducto.codigo) == codigo.upper(),
                                                         GrupoProducto.id != (excepto_id or 0))))


def usos(db: Session, g: GrupoProducto) -> dict:
    """Qué apunta al nodo: asignaciones, subgrupos, reglas y etiquetas ya generadas."""
    def n(modelo, *cond) -> int:
        return db.scalar(select(func.count()).select_from(modelo).where(*cond)) or 0

    return {"articulos": n(Articulo, Articulo.grupo_producto_id == g.id),
            "grupos_articulos": n(GrupoArticulo, GrupoArticulo.grupo_producto_id == g.id),
            "productos": n(Producto, Producto.grupo_producto_id == g.id),
            "hijos": n(GrupoProducto, GrupoProducto.padre_id == g.id),
            "reglas_etiqueta": n(UsoDiseno, UsoDiseno.grupo_id == g.id, UsoDiseno.eliminado_en.is_(None)),
            "reglas_etiqueta_bajas": n(UsoDiseno, UsoDiseno.grupo_id == g.id, UsoDiseno.eliminado_en.is_not(None)),
            "reglas_empaque": n(ReglaEmpaque, ReglaEmpaque.grupo_id == g.id, ReglaEmpaque.eliminada_en.is_(None)),
            "reglas_empaque_bajas": n(ReglaEmpaque, ReglaEmpaque.grupo_id == g.id, ReglaEmpaque.eliminada_en.is_not(None)),
            "etiquetas": n(GeneracionItem, GeneracionItem.grupo_id == g.id)}


def en_uso(db: Session, g: GrupoProducto) -> bool:
    """Algo apunta al nodo (incluso una regla dada de baja o una etiqueta del historial): no se puede borrar."""
    return any(usos(db, g).values())


# ---- Datos maestros → Grupos de producto ---------------------------------------------------------
def _conteos(db: Session) -> dict:
    res: dict = {}

    def sumar(clave, filas):
        for gid, n in filas:
            if gid is not None:
                res.setdefault(gid, {})[clave] = n

    sumar("articulos", db.execute(select(Articulo.grupo_producto_id, func.count()).group_by(Articulo.grupo_producto_id)))
    sumar("grupos_articulos", db.execute(select(GrupoArticulo.grupo_producto_id, func.count())
                                         .group_by(GrupoArticulo.grupo_producto_id)))
    sumar("productos", db.execute(select(Producto.grupo_producto_id, func.count()).group_by(Producto.grupo_producto_id)))
    sumar("reglas_etiqueta", db.execute(select(UsoDiseno.grupo_id, func.count()).where(UsoDiseno.eliminado_en.is_(None))
                                        .group_by(UsoDiseno.grupo_id)))
    sumar("reglas_empaque", db.execute(select(ReglaEmpaque.grupo_id, func.count()).where(ReglaEmpaque.eliminada_en.is_(None))
                                       .group_by(ReglaEmpaque.grupo_id)))
    return res


def dict_grupo(g: GrupoProducto, conteos: dict | None = None) -> dict:
    c = (conteos or {}).get(g.id, {})
    return {"id": g.id, "clase": g.clase, "codigo": g.codigo, "nombre": g.nombre, "descripcion": g.descripcion,
            "padre_id": g.padre_id, "ruta": " / ".join(x.nombre for x in g.ruta()), "profundidad": len(g.ruta()) - 1,
            "condiciones": g.condiciones or [], "orden": g.orden, "activa": g.activa,
            "articulos": c.get("articulos", 0), "grupos_articulos": c.get("grupos_articulos", 0),
            "productos": c.get("productos", 0), "reglas_etiqueta": c.get("reglas_etiqueta", 0),
            "reglas_empaque": c.get("reglas_empaque", 0)}


def arbol(db: Session, user: Usuario, incluir_inactivos: bool = True) -> list[dict]:
    """Todos los nodos en orden de árbol (cada familia, sus categorías y luego sus subfamilias)."""
    exigir_alguno(user, *PERMISOS_VER)
    c = select(GrupoProducto).order_by(GrupoProducto.orden, GrupoProducto.nombre)
    if not incluir_inactivos:
        c = c.where(GrupoProducto.activa.is_(True))
    nodos = list(db.scalars(c))
    ids = {g.id for g in nodos}
    hijos: dict = {}
    for g in nodos:
        hijos.setdefault(g.padre_id if g.padre_id in ids else None, []).append(g)
    conteos = _conteos(db)
    res: list[dict] = []
    vistos: set = set()

    def poner(padre):
        # Primero las categorías (lo más específico de la familia), luego las subfamilias
        for g in sorted(hijos.get(padre, []), key=lambda x: (x.clase != "CATEGORIA", x.orden, x.nombre)):
            if g.id in vistos:
                continue
            vistos.add(g.id)
            res.append(dict_grupo(g, conteos))
            poner(g.id)
    poner(None)
    return res


def campos(db: Session, user: Usuario) -> dict:
    """Los datos del artículo y del producto con que se reconoce una categoría, y los operadores."""
    from app.modulos.comun.condiciones import OPERADORES_SIMPLES
    from app.modulos.etiquetado import campos as etq_campos

    exigir_alguno(user, *PERMISOS_VER)
    return {"campos": [{"clave": c.clave, "etiqueta": c.etiqueta} for c in etq_campos.catalogo(db, "ARTICULO")
                       if c.grupo in ("articulo", "producto")],
            "operadores": list(OPERADORES_SIMPLES)}


def cargar(db: Session, grupo_id: int) -> GrupoProducto:
    g = db.get(GrupoProducto, grupo_id)
    if g is None:
        raise ErrorNegocio("The product group does not exist.", 404, "no_encontrado")
    return g


def _validar(db: Session, datos: dict, actual: GrupoProducto | None) -> dict:
    from app.modulos.etiquetado import reglas

    errores, limpio = [], {}
    clase = actual.clase if actual is not None else str(datos.get("clase") or "FAMILIA").upper()
    if clase not in CLASES_GRUPO:
        errores.append({"campo": "clase", "mensaje": "Choose family or category."})
    if actual is None or "codigo" in datos:
        codigo = (datos.get("codigo") or "").strip().upper()
        if not codigo or len(codigo) > 20 or not all(ch.isalnum() or ch in "-_." for ch in codigo):
            errores.append({"campo": "codigo", "mensaje": "Enter a code of up to 20 letters, digits, - _ or ."})
        elif codigo_ocupado(db, codigo, actual.id if actual else None):
            errores.append({"campo": "codigo", "mensaje": "Another family or category has this code."})
        limpio["codigo"] = codigo
    if actual is None or "nombre" in datos:
        nombre = (datos.get("nombre") or "").strip()
        if not nombre or len(nombre) > 100:
            errores.append({"campo": "nombre", "mensaje": "Enter the name (up to 100 characters)."})
        limpio["nombre"] = nombre
    if "descripcion" in datos:
        limpio["descripcion"] = (datos.get("descripcion") or "").strip()[:300] or None
    if actual is None or "padre_id" in datos:
        padre_id = datos.get("padre_id") or None
        padre = db.get(GrupoFamilia, int(padre_id)) if padre_id else None
        if padre_id and padre is None:
            errores.append({"campo": "padre_id", "mensaje": "Choose a family as the parent."})
        elif clase == "CATEGORIA" and padre is None:
            errores.append({"campo": "padre_id", "mensaje": "A category goes inside a family."})
        elif padre is not None and actual is not None and actual in padre.ruta():
            errores.append({"campo": "padre_id", "mensaje": "A family cannot be inside itself or one of its subfamilies."})
        limpio["padre_id"] = padre.id if padre is not None else None
    if "condiciones" in datos:
        if clase != "CATEGORIA" and datos.get("condiciones"):
            errores.append({"campo": "condiciones", "mensaje": "Only a category is recognized by conditions."})
        else:
            limpio["condiciones"] = reglas.validar_condiciones(db, datos.get("condiciones") or [])
    if "orden" in datos:
        try:
            limpio["orden"] = max(int(datos["orden"]), 0)
        except (TypeError, ValueError):
            errores.append({"campo": "orden", "mensaje": "Write a whole number."})
    if "activa" in datos:
        limpio["activa"] = bool(datos["activa"])
    if errores:
        raise ErrorNegocio("Check the product group.", 422, "validacion", errores)
    return limpio


def crear(db: Session, user: Usuario, datos: dict) -> dict:
    exigir_alguno(user, *PERMISOS_EDITAR)
    limpio = _validar(db, datos, None)
    clase = GrupoCategoria if str(datos.get("clase") or "FAMILIA").upper() == "CATEGORIA" else GrupoFamilia
    if "orden" not in limpio:
        limpio["orden"] = (db.scalar(select(func.max(GrupoProducto.orden)).where(
            GrupoProducto.padre_id.is_(None) if limpio["padre_id"] is None else GrupoProducto.padre_id == limpio["padre_id"]))
            or 0) + 10
    g = clase(**{"activa": True, "condiciones": [], "campos": [], **limpio})
    db.add(g)
    db.flush()
    registrar(db, user, "grupo_producto", g.id, "crear", {"codigo": g.codigo, "clase": g.clase, "padre_id": g.padre_id})
    return dict_grupo(g, _conteos(db))


def actualizar(db: Session, user: Usuario, grupo_id: int, datos: dict) -> dict:
    exigir_alguno(user, *PERMISOS_EDITAR)
    g = cargar(db, grupo_id)
    limpio = _validar(db, datos, g)
    if g.clase == "CATEGORIA" and limpio.get("padre_id", g.padre_id) != g.padre_id and en_uso(db, g):
        raise ErrorNegocio("The category is in use (rules or products): it cannot move to another family.", 409, "en_uso")
    cambios = {k: [getattr(g, k), v] for k, v in limpio.items() if getattr(g, k) != v}
    for k, v in limpio.items():
        setattr(g, k, v)
    db.flush()
    if cambios:
        registrar(db, user, "grupo_producto", g.id, "editar", {k: v for k, v in cambios.items() if k != "condiciones"}
                  | ({"condiciones": True} if "condiciones" in cambios else {}))
    return dict_grupo(g, _conteos(db))


def eliminar(db: Session, user: Usuario, grupo_id: int) -> dict:
    """Solo un nodo sin uso; si se usa, se desactiva."""
    exigir_alguno(user, *PERMISOS_EDITAR)
    g = cargar(db, grupo_id)
    if en_uso(db, g):
        raise ErrorNegocio("The group has items, products, rules or subgroups: deactivate it instead.", 409, "en_uso")
    registrar(db, user, "grupo_producto", g.id, "eliminar", {"codigo": g.codigo, "clase": g.clase})
    db.delete(g)
    db.flush()
    return {"ok": True}
