"""La sección de comercio exterior de la familia: la categoría aduanera con que
empiezan las fichas de sus productos («¿qué es el producto?»: calzado, prenda,
químico…). Vacía: la de la familia que la contiene. La categoría es del
conocimiento del arancel (categorias_producto); la familia solo la elige."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errores import ErrorNegocio
from app.modelos import CategoriaProducto, FamiliaComex, ProductoComex, Usuario
from app.modulos.catalogo import servicio as catalogo
from app.modulos.catalogo.secciones import SeccionFamilia, registrar_seccion_familia
from app.modulos.comun.historial import registrar

CACHE = "comex_categorias_familia"


def categorias_por_familia(db: Session) -> dict[int, str]:
    """{nodo del árbol: categoría aduanera efectiva}: la suya o la de la familia más cercana que la tenga
    (se calcula una vez por sesión: el lote clasifica muchos productos seguidos)."""
    if CACHE in db.info:
        return db.info[CACHE]
    propias = dict(db.execute(select(FamiliaComex.familia_id, FamiliaComex.categoria)
                              .where(FamiliaComex.categoria.is_not(None))).all())
    res = {}
    for fid, f in catalogo.familias(db).items():
        cat = next((propias[x] for x in reversed(f.ruta_ids) if x in propias), None)
        if cat:
            res[fid] = cat
    db.info[CACHE] = res
    return res


def categoria_de(db: Session, grupo_id: int | None) -> str | None:
    """La categoría aduanera con que empieza la ficha de un producto de esa familia (o categoría)."""
    return categorias_por_familia(db).get(grupo_id) if grupo_id else None


def _leer(db: Session, familia_id: int) -> dict:
    fila = db.get(FamiliaComex, familia_id)
    efectiva = categoria_de(db, familia_id)
    nombres = dict(db.execute(select(CategoriaProducto.codigo, CategoriaProducto.nombre)).all())
    ids = catalogo.ids_productos(familia_exacta_id=familia_id)
    sin = db.scalar(select(func.count()).select_from(ProductoComex).where(
        ProductoComex.producto_id.in_(ids), ProductoComex.tipo.is_(None))) or 0
    return {"categoria": fila.categoria if fila else None, "efectiva": efectiva, "efectiva_nombre": nombres.get(efectiva),
            "heredada": bool(efectiva) and not (fila and fila.categoria), "productos_sin_categoria": sin,
            "categorias": [{"codigo": c, "nombre": n} for c, n in db.execute(
                select(CategoriaProducto.codigo, CategoriaProducto.nombre).where(CategoriaProducto.activo.is_(True))
                .order_by(CategoriaProducto.orden, CategoriaProducto.nombre))]}


def _guardar(db: Session, user: Usuario, familia_id: int, datos: dict) -> dict:
    if catalogo.nodo(db, familia_id) is None:
        raise ErrorNegocio("The family does not exist.", 404, "no_encontrado")
    v = (datos.get("categoria") or "").strip() or None
    if v and not db.scalar(select(CategoriaProducto.id).where(CategoriaProducto.codigo == v, CategoriaProducto.activo.is_(True))):
        raise ErrorNegocio("Check the customs category.", 422, "validacion",
                           [{"campo": "categoria", "mensaje": "Choose a value from the list."}])
    fila = db.get(FamiliaComex, familia_id)
    antes = fila.categoria if fila else None
    if fila is None:
        fila = FamiliaComex(familia_id=familia_id)
        db.add(fila)
    fila.categoria = v
    db.flush()
    db.info.pop(CACHE, None)
    if antes != v:
        registrar(db, user, "grupo_producto", familia_id, "comercio_exterior", {"categoria": [antes, v]})
    return _leer(db, familia_id)


registrar_seccion_familia(SeccionFamilia(
    clave="comex", nombre="Foreign trade", orden=20, leer=_leer, guardar=_guardar,
    permisos_ver=("clasificacion.ver",), permisos_editar=("clasificacion.configurar",)))
