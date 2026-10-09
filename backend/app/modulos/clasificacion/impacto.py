"""Reglas conectadas con los artículos.

- simular: antes de guardar una regla (nueva o editada), qué artículos de su
  ámbito cambiarían de subpartida. La regla se aplica dentro de un punto de
  guardado que se deshace: nada queda guardado.
- desde_producto: el borrador de una regla a partir de una decisión de
  aduanas sobre un artículo (su categoría, sus respuestas y la subpartida
  aprobada), para que la próxima vez el motor la sugiera solo.
"""
from sqlalchemy import select

from app.core.errores import ErrorNegocio
from app.modelos import CategoriaProducto, Producto, ReglaClasificacion, Usuario
from app.modulos.acceso.permisos import exigir
from app.modulos.productos.productos import APROBADOS, _producto, entrada_producto, fmt_codigo

LIMITE = 120  # artículos que se vuelven a clasificar en una simulación (los más recientes)


def _en_ambito(db, tipo: str, codigo: str):
    q = select(Producto)
    if tipo == "CATEGORY":
        q = q.where(Producto.tipo == codigo)
    elif tipo == "DOMAIN":
        cats = db.scalars(select(CategoriaProducto.codigo).where(CategoriaProducto.dominio == codigo)).all()
        q = q.where(Producto.tipo.in_(cats or [""]))
    elif tipo in ("CHAPTER", "HEADING", "SUBHEADING"):
        q = q.where((Producto.codigo.like(f"{codigo}%")) | (Producto.sugerido.like(f"{codigo}%")))
    return q.order_by(Producto.actualizado_en.desc())


def _hs6(db, productos, cat) -> dict[int, str | None]:
    from app.modulos.clasificacion.motor_clasificacion import clasificar_producto

    return {p.id: clasificar_producto(db, entrada_producto(p), catalogo=cat, paises=False)["hs6"] for p in productos}


def simular(db, user: Usuario, datos: dict, regla_id: int | None = None) -> dict:
    """Clasifica los artículos del ámbito sin y con el cambio, y dice cuáles cambian."""
    from app.modulos.clasificacion import reglas
    from app.modulos.productos.ficha import catalogo

    exigir(user, "clasificacion.configurar")
    actual = db.get(ReglaClasificacion, regla_id) if regla_id else None
    if regla_id and not actual:
        raise ErrorNegocio("The rule does not exist.", 404, "no_encontrado")
    tipo = (datos.get("tipo_ambito") or (actual.tipo_ambito if actual else "SYSTEM")).upper()
    codigo = datos.get("codigo_ambito") or (actual.codigo_ambito if actual else "ALL")
    q = _en_ambito(db, tipo, codigo)
    total = len(db.scalars(q.with_only_columns(Producto.id)).all())
    productos = db.scalars(q.limit(LIMITE)).all()
    cat = catalogo(db)
    antes = _hs6(db, productos, cat)
    punto = db.begin_nested()
    try:
        if actual:
            reglas.guardar(db, user, actual.id, datos)
        else:
            reglas.crear(db, user, datos)
        db.flush()
        despues = _hs6(db, productos, cat)
    finally:
        punto.rollback()
    cambian = [{"id": p.id, "estilo": p.estilo, "color": p.color, "estado": p.estado, "aprobado": fmt_codigo(p.codigo) if p.codigo else None,
                "antes": fmt_codigo(antes[p.id]) if antes[p.id] else None, "despues": fmt_codigo(despues[p.id]) if despues[p.id] else None}
               for p in productos if antes[p.id] != despues[p.id]]
    return {"en_ambito": total, "evaluados": len(productos), "cambian": cambian,
            "aprobados_distintos": sum(1 for x in cambian if x["aprobado"] and x["despues"] != x["aprobado"])}


def desde_producto(db, user: Usuario, producto_id: int) -> dict:
    """Borrador de regla: «en esta categoría, con estas respuestas → esta subpartida»."""
    from app.modulos.productos.ficha import catalogo

    exigir(user, "clasificacion.configurar")
    p = _producto(db, user, producto_id)
    hs6 = "".join(ch for ch in str(p.codigo or "") if ch.isdigit())[:6]
    if p.estado not in APROBADOS or len(hs6) < 6 or not p.tipo:
        raise ErrorNegocio("Only an approved item with a category can become a rule.", 422, "validacion")
    cat = catalogo(db)
    ficha = p.ficha or {}
    condiciones = []
    for a in cat.atributos:
        v = ficha.get(a.codigo)
        if a.tipo_dato not in ("select", "boolean") or not a.usado_clasificacion or v in (None, "", []):
            continue
        if a.booleano and v is False:
            continue
        condiciones.append({"grupo": 1, "campo": a.codigo, "operador": "EQUAL", "valor": v, "negado": False})
    c = cat.categorias.get(p.tipo)
    return {"tipo_regla": "HARD_CONSTRAINT", "tipo_ambito": "CATEGORY", "codigo_ambito": p.tipo, "prioridad": 600,
            "efecto": f"{c.nombre if c else p.tipo} → {fmt_codigo(hs6)} ({p.estilo})"[:500],
            "accion": {"tipo": "RESTRICT", "codigos": [hs6]}, "condiciones": condiciones[:8]}
