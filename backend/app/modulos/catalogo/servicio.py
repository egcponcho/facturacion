"""Lo que los demás módulos leen del catálogo.

Compras, facturación, empaque, etiquetado, seguimiento, reportes… no tocan las
tablas del catálogo: piden aquí fichas ya armadas (datos simples, no objetos de
la base) y, para filtrar en SQL, consultas que devuelven ids de artículo. Así
el catálogo puede cambiar por dentro sin que nada se desintegre: lo verifica
tests/test_arquitectura.py.

Las fichas se piden en lote (`articulos(db, ids)`) cuando se recorren líneas:
una consulta para todas, no una por línea. Además, cada sesión recuerda las
fichas que ya armó y las olvida en cuanto algo del catálogo cambia.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Select, and_, event, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.modelos import (
    Articulo,
    ArticuloAtributo,
    ArticuloCodigo,
    ArticuloComponente,
    Atributo,
    GrupoProducto,
    Producto,
    ProductoAtributo,
)
from app.modulos.catalogo import valores as val

# Tipos de artículo: una variante (lo que distinguen sus valores) o un pack o kit (una caja con su contenido)
TIPO_VARIANTE = "SOLIDO"
TIPO_PACK = "PREPACK"
TIPOS = (TIPO_VARIANTE, TIPO_PACK)


# ---- Fichas -----------------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class FichaFamilia:
    """Una familia del árbol: su ruta va de la raíz a ella (ids, códigos y nombres)."""

    id: int
    codigo: str
    nombre: str
    ruta_ids: tuple[int, ...]
    ruta_codigos: tuple[str, ...]
    ruta_nombres: tuple[str, ...]
    activa: bool = True
    es_categoria: bool = False  # un nodo que se reconoce por condiciones dentro de su familia
    orden: int = 0  # entre sus hermanos

    @property
    def texto_ruta(self) -> str:
        return " / ".join(self.ruta_nombres)

    @property
    def padre_id(self) -> int | None:
        return self.ruta_ids[-2] if len(self.ruta_ids) > 1 else None


@dataclass(frozen=True, slots=True)
class Componente:
    """Una variante dentro de un pack o un kit, con cuántas unidades lleva."""

    articulo_id: int
    codigo: str
    cantidad: int
    producto_id: int
    valores: dict
    unidad: str | None = None
    peso: float | None = None
    codigo_barras: str | None = None
    descripcion: str | None = None


@dataclass(frozen=True, slots=True)
class FichaArticulo:
    """Un artículo (variante, pack o kit) con lo de su producto que necesita quien lo usa."""

    id: int
    codigo: str
    tipo: str
    activo: bool
    unidad: str
    peso: float | None
    descripcion: str | None
    producto_id: int
    producto_codigo: str | None
    producto_nombre: str | None
    proveedor_id: int | None
    grupo_id: int | None  # el nodo del árbol puesto en su producto (familia o categoría)
    familia: FichaFamilia | None  # la familia de su producto
    valores: dict  # sus valores de variante, en el orden de los atributos
    datos: dict  # los atributos de su producto (marca, modelo…), en orden
    marca: str | None  # código de la marca (el atributo de producto que apunta al catálogo de marcas)
    codigo_barras: str | None
    codigo_proveedor: str | None
    codigo_pack: str | None
    componentes: tuple[Componente, ...] = ()

    @property
    def es_pack(self) -> bool:
        return self.tipo == TIPO_PACK

    @property
    def total_componentes(self) -> int:
        return sum(c.cantidad for c in self.componentes)

    @property
    def es_kit(self) -> bool:
        """Un kit junta variantes de varios productos; un pack, variantes de su propio producto."""
        return any(c.producto_id != self.producto_id for c in self.componentes)

    @property
    def peso_neto(self) -> float | None:
        """Peso de una unidad: el suyo o, en un pack o kit sin peso propio, la suma de su contenido."""
        if self.peso:
            return self.peso
        if self.es_pack and self.componentes and all(c.peso for c in self.componentes):
            return round(sum(c.cantidad * c.peso for c in self.componentes), 4)
        return None

    @property
    def texto_variante(self) -> str | None:
        """«BLACK · 9.5» o, en un pack, «pack AB12»."""
        if self.es_pack:
            return f"pack {self.codigo_pack}" if self.codigo_pack else None
        return val.texto(self.valores) or None


@dataclass(frozen=True, slots=True)
class FichaProducto:
    id: int
    codigo: str | None
    nombre: str | None
    unidad: str | None
    proveedor_id: int | None
    grupo_id: int | None
    familia: FichaFamilia | None
    datos: dict
    marca: str | None
    actualizado_en: datetime | None = None

    @property
    def nombre_o_codigo(self) -> str:
        return self.nombre or self.codigo or str(self.id)


# ---- Familias ---------------------------------------------------------------------------------
def _ficha_familia(g: GrupoProducto | None) -> FichaFamilia | None:
    if g is None:
        return None
    ruta = g.ruta()
    return FichaFamilia(id=g.id, codigo=g.codigo, nombre=g.nombre, ruta_ids=tuple(x.id for x in ruta),
                        ruta_codigos=tuple(x.codigo for x in ruta), ruta_nombres=tuple(x.nombre for x in ruta),
                        activa=g.activa, es_categoria=g.clase == "CATEGORIA", orden=g.orden or 0)


def familia(db: Session, familia_id: int | None) -> FichaFamilia | None:
    return _ficha_familia(db.get(GrupoProducto, familia_id)) if familia_id else None


def familias(db: Session) -> dict[int, FichaFamilia]:
    """Todos los nodos del árbol (familias y categorías), por id."""
    return {g.id: _ficha_familia(g) for g in db.scalars(select(GrupoProducto))}


def nodo(db: Session, nodo_id: int | None) -> FichaFamilia | None:
    """Un nodo del árbol (una familia o una categoría), tal cual."""
    return _ficha_familia(db.get(GrupoProducto, nodo_id)) if nodo_id else None


def nodo_por_codigo(db: Session, codigo: str | None) -> FichaFamilia | None:
    """El nodo (familia o categoría) con ese código, sin distinguir mayúsculas."""
    if not codigo or not str(codigo).strip():
        return None
    return _ficha_familia(db.scalar(select(GrupoProducto).where(func.upper(GrupoProducto.codigo) == str(codigo).strip().upper())))


def familia_de_grupos(db: Session) -> dict[int, FichaFamilia]:
    """{nodo: la familia que le corresponde} (una categoría da la familia que la contiene)."""
    return {g.id: f for g in db.scalars(select(GrupoProducto)) if (f := _ficha_familia(g.familia)) is not None}


def grupos_de_articulos():
    """Subconsulta (articulo_id, producto_id, grupo_id) para unir con tablas de otros módulos:
    `join(sub, sub.c.articulo_id == Tabla.articulo_id)`. grupo_id es el nodo del árbol de su producto."""
    return (select(Articulo.id.label("articulo_id"), Articulo.producto_id.label("producto_id"),
                   Producto.grupo_producto_id.label("grupo_id"))
            .join(Producto, Producto.id == Articulo.producto_id).subquery())


def grupos(db: Session, articulo_ids: Iterable[int | None]) -> dict[int, int | None]:
    """{artículo: nodo del árbol de su producto} en una consulta."""
    lista = sorted({i for i in articulo_ids if i})
    if not lista:
        return {}
    sub = grupos_de_articulos()
    return dict(db.execute(select(sub.c.articulo_id, sub.c.grupo_id).where(sub.c.articulo_id.in_(lista))).all())


def productos_de(db: Session, articulo_ids: Iterable[int | None]) -> dict[int, int]:
    """{artículo: su producto} en una consulta."""
    lista = sorted({i for i in articulo_ids if i})
    if not lista:
        return {}
    return dict(db.execute(select(Articulo.id, Articulo.producto_id).where(Articulo.id.in_(lista))).all())


def valores_condiciones(db: Session, ficha: FichaArticulo, cache: dict | None = None) -> dict:
    """Los datos del artículo y de su producto con que se reconoce una categoría (y que las reglas de
    otros módulos pueden comparar): «articulo.sku», «articulo.atributo.TALLA», «producto.dato.MARCA»…
    `cache` guarda los nombres de marca ya leídos (al recorrer muchos artículos)."""
    from app.modelos import Marca

    marcas = cache.setdefault("marcas", {}) if cache is not None else {}
    if ficha.marca and ficha.marca not in marcas:
        marcas[ficha.marca] = db.scalar(select(Marca.nombre).where(Marca.codigo == ficha.marca))
    marca = marcas.get(ficha.marca) if ficha.marca else None
    fam = ficha.familia
    return {
        "articulo.sku": ficha.codigo, "articulo.codigo_proveedor": ficha.codigo_proveedor,
        "articulo.codigo_barras": ficha.codigo_barras, "articulo.generico": ficha.producto_codigo,
        "articulo.variante": val.texto(ficha.valores) or None, "articulo.descripcion": ficha.descripcion,
        "articulo.unidad": ficha.unidad, "articulo.tipo": ficha.tipo, "articulo.peso_unitario": ficha.peso,
        "articulo.codigo_pack": ficha.codigo_pack,
        "articulo.familia_codigo": fam.codigo if fam else None, "articulo.familia": fam.nombre if fam else None,
        "articulo.familia_ruta": " / ".join(fam.ruta_codigos) if fam else None,
        "producto.nombre": ficha.producto_nombre, "producto.codigo_generico": ficha.producto_codigo, "producto.marca": marca,
        **{f"articulo.atributo.{k}": v for k, v in ficha.valores.items()},
        **{f"producto.dato.{k}": v for k, v in ficha.datos.items()},
    }


def categoria(db: Session, ficha: FichaArticulo | None, cache: dict | None = None) -> FichaFamilia | None:
    """La categoría del artículo: la puesta a mano en su producto o la primera de su familia (de la
    más específica a la más general) que se reconoce por sus condiciones sobre `valores_condiciones`."""
    if ficha is None or ficha.familia is None:
        return None
    from app.modulos.catalogo import familias as arbol

    if cache is None:
        cache = {}
    return _ficha_familia(arbol.categoria_de(db, db.get(Articulo, ficha.id), valores_condiciones(db, ficha, cache), cache))


def ruta_reglas(db: Session, ficha: FichaArticulo | None, cache: dict | None = None) -> list[int]:
    """Los nodos del árbol que recorren las reglas de empaque y de etiquetado para el artículo,
    de lo más específico a lo más general: su categoría (puesta a mano o reconocida por sus
    condiciones sobre `valores_condiciones`), su familia y las familias que la contienen."""
    if ficha is None:
        return []
    from app.modulos.catalogo import familias as arbol

    if cache is None:
        cache = {}
    a = db.get(Articulo, ficha.id)
    return [g.id for g in arbol.ruta_efectiva(db, a, valores_condiciones(db, ficha, cache), cache)]


def en_familia(ficha: FichaArticulo | None, familia_id: int) -> bool:
    """El artículo es de la familia o de una de sus subfamilias."""
    return ficha is not None and ficha.familia is not None and familia_id in ficha.familia.ruta_ids


# ---- Artículos --------------------------------------------------------------------------------
def _opciones():
    return (selectinload(Articulo.producto).selectinload(Producto.atributos),
            selectinload(Articulo.producto).selectinload(Producto.grupo_producto),
            selectinload(Articulo.atributos), selectinload(Articulo.codigos),
            selectinload(Articulo.componentes).selectinload(ArticuloComponente.componente)
            .selectinload(Articulo.atributos))


def _descripcion(a: Articulo) -> str | None:
    """La suya o la del producto con los valores de la variante (en un pack, su identificador)."""
    if a.descripcion:
        return a.descripcion
    prod = a.producto
    base = (prod.descripcion_comercial or prod.nombre) if prod else None
    valores = " · ".join(str(v) for v in a.variantes.values() if v not in (None, ""))
    if a.tipo == TIPO_PACK and a.codigo_pack:
        valores = f"pack {a.codigo_pack}"
    return ", ".join(x for x in (base, valores) if x) or None


def _ficha(db: Session, a: Articulo) -> FichaArticulo:
    p = a.producto
    datos = val.ordenar(db, p.valores if p is not None else {}, "PRODUCTO")
    g = p.grupo_producto if p is not None else None
    return FichaArticulo(
        id=a.id, codigo=a.sku, tipo=a.tipo, activo=a.activo, unidad=a.unidad, peso=a.peso_unitario,
        descripcion=_descripcion(a), producto_id=a.producto_id,
        producto_codigo=p.codigo_generico if p else None, producto_nombre=p.nombre if p else None,
        proveedor_id=p.proveedor_id if p else None, grupo_id=g.id if g is not None else None,
        familia=_ficha_familia(g.familia if g is not None else None),
        valores=val.ordenar(db, a.variantes), datos=datos, marca=val.de_catalogo(db, datos, "marcas"),
        codigo_barras=a.codigo_barras, codigo_proveedor=a.codigo_proveedor, codigo_pack=a.codigo_pack,
        componentes=tuple(Componente(articulo_id=c.componente_id, codigo=c.componente.sku, cantidad=c.cantidad,
                                     producto_id=c.componente.producto_id, valores=val.ordenar(db, c.componente.variantes),
                                     unidad=c.componente.unidad, peso=c.componente.peso_unitario,
                                     codigo_barras=c.componente.codigo_barras, descripcion=c.componente.descripcion)
                          for c in a.componentes))


def ficha_de_modelo(db: Session, a: Articulo) -> FichaArticulo:
    """La ficha de un artículo ya cargado (o recién creado, sin guardar). Solo para el catálogo por dentro."""
    return _ficha(db, a)


# Fichas ya armadas en la sesión: se olvidan cuando cambia cualquier tabla del catálogo
_CLAVE = "catalogo_fichas"
_MODELOS = (Articulo, ArticuloAtributo, ArticuloCodigo, ArticuloComponente, Atributo, GrupoProducto, Producto, ProductoAtributo)


def _recordadas(db: Session) -> dict:
    """Las fichas recordadas; si la sesión tiene cambios del catálogo sin guardar, ninguna."""
    if _CLAVE in db.info and any(isinstance(o, _MODELOS) for o in (*db.new, *db.dirty, *db.deleted)):
        db.info.pop(_CLAVE, None)
    return db.info.setdefault(_CLAVE, {})


@event.listens_for(Session, "after_flush")
def _olvidar_si_cambia(db: Session, _contexto) -> None:
    if _CLAVE in db.info and any(isinstance(o, _MODELOS) for o in (*db.new, *db.dirty, *db.deleted)):
        db.info.pop(_CLAVE, None)


@event.listens_for(Session, "after_rollback")
def _olvidar_al_deshacer(db: Session) -> None:
    db.info.pop(_CLAVE, None)


def articulos(db: Session, ids: Iterable[int | None]) -> dict[int, FichaArticulo]:
    """{id: ficha} de esos artículos (los que no existen no aparecen)."""
    ids = sorted({i for i in ids if i})
    if not ids:
        return {}
    memo = _recordadas(db)
    faltan = [i for i in ids if i not in memo]
    if faltan:
        cargados = {a.id: _ficha(db, a) for a in db.scalars(select(Articulo).where(Articulo.id.in_(faltan)).options(*_opciones()))}
        memo.update({i: cargados.get(i) for i in faltan})
    return {i: memo[i] for i in ids if memo.get(i) is not None}


def articulo(db: Session, articulo_id: int | None) -> FichaArticulo | None:
    return articulos(db, [articulo_id]).get(articulo_id) if articulo_id else None


def por_codigos(db: Session, codigos: Iterable[str | None]) -> dict[str, FichaArticulo]:
    """{código: ficha} de los artículos con esos códigos (exactos)."""
    codigos = sorted({str(c).strip() for c in codigos if c and str(c).strip()})
    if not codigos:
        return {}
    return {a.sku: _ficha(db, a) for a in db.scalars(select(Articulo).where(Articulo.sku.in_(codigos)).options(*_opciones()))}


def por_codigo(db: Session, codigo: str | None) -> FichaArticulo | None:
    c = str(codigo or "").strip()
    return por_codigos(db, [c]).get(c) if c else None


def de_producto(db: Session, producto_id: int, solo_activos: bool = False) -> list[FichaArticulo]:
    """Los artículos de un producto (variantes y packs), en orden de código."""
    c = select(Articulo).where(Articulo.producto_id == producto_id)
    if solo_activos:
        c = c.where(Articulo.activo.is_(True))
    return [_ficha(db, a) for a in db.scalars(c.options(*_opciones()).order_by(Articulo.sku))]


def articulos_de(db: Session, *, familia_id: int | None = None, producto_id: int | None = None,
                 solo_activos: bool = True, limite: int | None = None) -> list[FichaArticulo]:
    """Los artículos de una familia (con sus subfamilias y categorías) o de un producto, en orden de id."""
    c = ids(familia_id=familia_id, producto_id=producto_id, solo_activos=solo_activos).order_by(Articulo.id)
    lista = list(db.scalars(c.limit(limite) if limite else c))
    fichas = articulos(db, lista)
    return [fichas[i] for i in lista if i in fichas]


def contar_por_familia(db: Session, solo_activos: bool = True) -> dict[int | None, int]:
    """{familia: cuántos artículos} por la familia de su producto (None: sin familia)."""
    fam = familia_de_grupos(db)
    filas = select(Producto.grupo_producto_id, func.count()).join(Articulo, Articulo.producto_id == Producto.id)
    if solo_activos:
        filas = filas.where(Articulo.activo.is_(True))
    res: dict[int | None, int] = {}
    for gid, n in db.execute(filas.group_by(Producto.grupo_producto_id)):
        f = fam.get(gid)
        res[f.id if f else None] = res.get(f.id if f else None, 0) + n
    return res


def contar_de_producto(db: Session, producto_id: int, solo_activos: bool = True) -> int:
    c = select(func.count()).select_from(Articulo).where(Articulo.producto_id == producto_id)
    return db.scalar(c.where(Articulo.activo.is_(True)) if solo_activos else c) or 0


def buscar(db: Session, texto: str | None = None, proveedor_id: int | None = None, solo_activos: bool = True,
           limite: int = 300) -> list[FichaArticulo]:
    """Artículos cuyo código, código de barras o del proveedor, valor de variante o producto
    (código o nombre) contienen el texto; en orden de producto y código."""
    c = ids(proveedor_id=proveedor_id, texto=texto, solo_activos=solo_activos)
    consulta = (select(Articulo).join(Producto, Producto.id == Articulo.producto_id).where(Articulo.id.in_(c))
                .options(*_opciones()).order_by(Producto.codigo_generico, Articulo.sku).limit(limite))
    return [_ficha(db, a) for a in db.scalars(consulta)]


# ---- Consultas de ids para filtrar en SQL ------------------------------------------------------
def ids(*, marca: str | None = None, marcas: Iterable[str] | None = None, proveedor_id: int | None = None,
        proveedores: Iterable[int] | None = None, familia_id: int | None = None, producto_id: int | None = None,
        valores: dict[str, Iterable[str]] | None = None, texto: str | None = None, solo_activos: bool = False,
        tipo: str | None = None, familia_exacta_id: int | None = None, sin_familia: bool = False) -> Select:
    """`select(id)` de los artículos que cumplen todos los filtros dados. Se usa como
    `Tabla.articulo_id.in_(catalogo.ids(...))`. Los valores de variante se comparan sin
    distinguir mayúsculas; la familia incluye sus subfamilias y categorías; el texto sigue la
    regla de búsqueda de las listas (sin acentos ni mayúsculas, términos en cualquier orden)."""
    c = select(Articulo.id)
    if solo_activos:
        c = c.where(Articulo.activo.is_(True))
    if tipo:
        c = c.where(Articulo.tipo == tipo)
    if producto_id is not None:
        c = c.where(Articulo.producto_id == producto_id)
    if proveedor_id is not None or proveedores is not None:
        lista = [proveedor_id] if proveedor_id is not None else list(proveedores or [])
        c = c.where(Articulo.producto_id.in_(select(Producto.id).where(Producto.proveedor_id.in_(lista))))
    lista_marcas = [marca] if marca else list(marcas or [])
    if lista_marcas:
        c = c.where(Articulo.producto_id.in_(
            select(ProductoAtributo.producto_id).join(Atributo, Atributo.id == ProductoAtributo.atributo_id)
            .where(Atributo.catalogo == "marcas", ProductoAtributo.valor.in_(lista_marcas))))
    if familia_id is not None:
        c = c.where(Articulo.producto_id.in_(select(Producto.id).where(Producto.grupo_producto_id.in_(_subarbol(familia_id)))))
    if familia_exacta_id is not None or sin_familia:
        c = c.where(Articulo.producto_id.in_(ids_productos(familia_exacta_id=familia_exacta_id, sin_familia=sin_familia)))
    for codigo, vs in (valores or {}).items():
        vs = [str(v).upper() for v in vs if v not in (None, "")]
        if vs:
            c = c.where(Articulo.id.in_(
                select(ArticuloAtributo.articulo_id).join(Atributo, Atributo.id == ArticuloAtributo.atributo_id)
                .where(Atributo.codigo == codigo, func.upper(ArticuloAtributo.valor).in_(vs))))
    if texto and texto.strip():
        from app.modulos.comun.texto import filtro_texto

        cond = filtro_texto(texto, lambda t: [
            Articulo.sku.ilike(t),
            Articulo.producto_id.in_(select(Producto.id).where(or_(Producto.nombre.ilike(t), Producto.codigo_generico.ilike(t)))),
            Articulo.id.in_(select(ArticuloCodigo.articulo_id).where(ArticuloCodigo.valor.ilike(t))),
            Articulo.id.in_(select(ArticuloAtributo.articulo_id).where(ArticuloAtributo.valor.ilike(t)))])
        if cond is not None:
            c = c.where(cond)
    return c


def _subarbol(familia_id: int) -> Select:
    """`select(id)` del nodo y de todos los que cuelgan de él."""
    nodos = select(GrupoProducto.id).where(GrupoProducto.id == familia_id).cte("subarbol", recursive=True)
    nodos = nodos.union_all(select(GrupoProducto.id).join(nodos, GrupoProducto.padre_id == nodos.c.id))
    return select(nodos.c.id)


def marcas_de(db: Session, articulo_ids: Select | Iterable[int]) -> list[str]:
    """Los códigos de marca distintos de esos artículos, en orden."""
    return sorted({m for (m,) in db.execute(
        select(ProductoAtributo.valor).join(Atributo, Atributo.id == ProductoAtributo.atributo_id)
        .join(Articulo, Articulo.producto_id == ProductoAtributo.producto_id)
        .where(Atributo.catalogo == "marcas", Articulo.id.in_(articulo_ids)).distinct()) if m})


# ---- Productos --------------------------------------------------------------------------------
def _ficha_producto(db: Session, p: Producto) -> FichaProducto:
    datos = val.ordenar(db, p.valores, "PRODUCTO")
    g = p.grupo_producto
    return FichaProducto(id=p.id, codigo=p.codigo_generico, nombre=p.nombre, unidad=p.unidad, proveedor_id=p.proveedor_id,
                         grupo_id=g.id if g is not None else None, familia=_ficha_familia(g.familia if g is not None else None),
                         datos=datos, marca=val.de_catalogo(db, datos, "marcas"), actualizado_en=p.actualizado_en)


def productos(db: Session, ids_: Iterable[int | None]) -> dict[int, FichaProducto]:
    lista = sorted({i for i in ids_ if i})
    if not lista:
        return {}
    return {p.id: _ficha_producto(db, p) for p in db.scalars(
        select(Producto).where(Producto.id.in_(lista)).options(selectinload(Producto.atributos),
                                                                selectinload(Producto.grupo_producto)))}


def producto(db: Session, producto_id: int | None) -> FichaProducto | None:
    return productos(db, [producto_id]).get(producto_id) if producto_id else None


def producto_por_codigo(db: Session, codigo: str | None) -> FichaProducto | None:
    pid = db.scalar(select(Producto.id).where(Producto.codigo_generico == str(codigo).strip())) if codigo else None
    return producto(db, pid)


def ids_productos_texto(q: str | None, proveedores: Iterable[int] | None = None) -> Select:
    """`select(id)` de los productos cuyo nombre, código o valores de atributo, o el código de uno de
    sus artículos (o su código de barras o del proveedor), coinciden con el texto (la regla de
    búsqueda de las listas: sin acentos ni mayúsculas, términos en cualquier orden)."""
    from app.modulos.comun.texto import filtro_texto

    def columnas(p):
        de_articulos = select(Articulo.producto_id).where(or_(
            Articulo.sku.ilike(p), Articulo.id.in_(select(ArticuloCodigo.articulo_id).where(ArticuloCodigo.valor.ilike(p)))))
        return [Producto.nombre.ilike(p), Producto.codigo_generico.ilike(p),
                Producto.id.in_(select(ProductoAtributo.producto_id).where(ProductoAtributo.valor.ilike(p))),
                Producto.id.in_(de_articulos)]

    c = select(Producto.id)
    cond = filtro_texto(q, columnas)
    if cond is not None:
        c = c.where(cond)
    if proveedores is not None:
        c = c.where(Producto.proveedor_id.in_(list(proveedores)))
    return c


def ids_productos_con_articulos(articulo_ids: Select | Iterable[int]) -> Select:
    """`select(producto_id)` de los productos de esos artículos."""
    return select(Articulo.producto_id).where(Articulo.id.in_(articulo_ids)).distinct()


def ids_productos(*, texto: str | None = None, proveedores: Iterable[int] | None = None,
                  familia_exacta_id: int | None = None, sin_familia: bool = False) -> Select:
    """`select(id)` de productos por texto, proveedores y familia: la suya exacta (o una categoría
    de ella), no las subfamilias; `sin_familia`, los que no tienen."""
    c = ids_productos_texto(texto, proveedores)
    if familia_exacta_id is not None:
        c = c.where(Producto.grupo_producto_id.in_(select(GrupoProducto.id).where(or_(
            GrupoProducto.id == familia_exacta_id,
            and_(GrupoProducto.padre_id == familia_exacta_id, GrupoProducto.clase == "CATEGORIA")))))
    if sin_familia:
        c = c.where(Producto.grupo_producto_id.is_(None))
    return c


def ids_entre(filtro: Select, ids_: Iterable[int]) -> Select:
    """El filtro de artículos, solo entre esos ids."""
    return filtro.where(Articulo.id.in_(list(ids_)))


def lista_ids(db: Session, filtro: Select, limite: int) -> list[int]:
    """Los ids de artículos del filtro, en orden, hasta el límite."""
    return list(db.scalars(filtro.order_by(Articulo.id).limit(limite)))


def pagina_articulos(db: Session, filtro: Select, page: int = 1, size: int = 50) -> tuple[int, list[FichaArticulo]]:
    """(cuántos, una página de fichas en orden de código) de un filtro de `ids()`."""
    total = db.scalar(select(func.count()).select_from(filtro.subquery())) or 0
    lista = list(db.scalars(filtro.order_by(Articulo.sku, Articulo.id).offset((max(page, 1) - 1) * size).limit(size)))
    fichas = articulos(db, lista)
    return total, [fichas[i] for i in lista if i in fichas]


def pagina_productos(db: Session, filtro: Select, page: int = 1, size: int = 50) -> tuple[int, list[FichaProducto]]:
    """(cuántos, una página de fichas en orden de código) de un filtro de `ids_productos()`."""
    total = db.scalar(select(func.count()).select_from(filtro.subquery())) or 0
    lista = list(db.scalars(select(Producto.id).where(Producto.id.in_(filtro))
                            .order_by(Producto.codigo_generico, Producto.id).offset((max(page, 1) - 1) * size).limit(size)))
    fichas = productos(db, lista)
    return total, [fichas[i] for i in lista if i in fichas]


def contar_productos_por_familia(db: Session) -> dict[int | None, int]:
    """{familia: cuántos productos} (None: sin familia)."""
    fam = familia_de_grupos(db)
    res: dict[int | None, int] = {}
    for gid, n in db.execute(select(Producto.grupo_producto_id, func.count()).group_by(Producto.grupo_producto_id)):
        f = fam.get(gid)
        res[f.id if f else None] = res.get(f.id if f else None, 0) + n
    return res


def contar_articulos_por_producto(db: Session, producto_ids: Iterable[int], solo_activos: bool = True) -> dict[int, int]:
    lista = sorted(set(producto_ids))
    if not lista:
        return {}
    c = select(Articulo.producto_id, func.count()).where(Articulo.producto_id.in_(lista))
    if solo_activos:
        c = c.where(Articulo.activo.is_(True))
    return dict(db.execute(c.group_by(Articulo.producto_id)).all())


# ---- Expresiones SQL para reportes -------------------------------------------------------------
def columnas_producto() -> dict:
    """Las columnas del producto que un reporte puede usar como tabla base: id, codigo, nombre,
    proveedor_id, grupo_id. La tabla es `columnas_producto()["id"].table`."""
    return {"id": Producto.id, "codigo": Producto.codigo_generico, "nombre": Producto.nombre,
            "proveedor_id": Producto.proveedor_id, "grupo_id": Producto.grupo_producto_id}


def sql_producto_de(articulo_id):
    """Expresión: el producto del artículo cuyo id es `articulo_id` (una columna de otra tabla)."""
    return select(Articulo.producto_id).where(Articulo.id == articulo_id).scalar_subquery()


def sql_marca(producto_id):
    """Expresión: el código de marca del producto (su atributo que apunta al catálogo de marcas)."""
    return (select(ProductoAtributo.valor).join(Atributo, Atributo.id == ProductoAtributo.atributo_id)
            .where(ProductoAtributo.producto_id == producto_id, Atributo.catalogo == "marcas").limit(1).scalar_subquery())


def sql_familia(producto_id):
    """Expresión: el nombre del nodo del árbol (familia o categoría) del producto."""
    return (select(GrupoProducto.nombre).join(Producto, Producto.grupo_producto_id == GrupoProducto.id)
            .where(Producto.id == producto_id).scalar_subquery())


# ---- Datos maestros que el catálogo usa -------------------------------------------------------
def usa_registro_de(db: Session, catalogo_: str, codigo: str) -> bool:
    """Algún producto o artículo tiene ese registro (p. ej. esa marca) en un atributo de tipo catálogo."""
    return any(db.scalar(select(t.id).join(Atributo, Atributo.id == t.atributo_id)
                         .where(Atributo.catalogo == catalogo_, t.valor == codigo).limit(1)) is not None
               for t in (ProductoAtributo, ArticuloAtributo))


def usa_unidad(db: Session, unidad: str) -> bool:
    """Algún artículo usa esa unidad de medida."""
    return db.scalar(select(Articulo.id).where(Articulo.unidad == unidad).limit(1)) is not None


def regla_codigo_variante():
    """Las reglas para formar el código de cada valor de variante (configuración de la empresa):
    (REGLAS, REGLA_FABRICA, validar)."""
    from app.modulos.maestros import escalas

    return escalas.REGLAS, escalas.REGLA_FABRICA, escalas.validar_regla


# ---- Atributos y valores ----------------------------------------------------------------------
def atributos(db: Session, nivel: str = "VARIANTE") -> list[dict]:
    """Los atributos activos de ese nivel en su orden: [{codigo, nombre, nivel, tipo, catalogo, unidad, opciones}]."""
    return [{"codigo": a.codigo, "nombre": a.nombre, "nivel": nivel, "tipo": a.tipo or "texto", "catalogo": a.catalogo,
             "unidad": a.unidad, "opciones": [o.strip() for o in (a.opciones or "").split(",") if o.strip()]}
            for a in val.atributos(db, nivel)]


def nombres_atributos(db: Session) -> dict[str, str]:
    return val.nombres(db)


def ordenar(db: Session | None, valores: dict | None, nivel: str = "VARIANTE") -> dict:
    """Los valores en el orden de los atributos de ese nivel."""
    return val.ordenar(db, valores, nivel)


def texto(valores: dict | None) -> str | None:
    """«BLACK · 9.5» (o None)."""
    return val.texto(valores) or None


def marca(db: Session | None, datos: dict | None) -> str | None:
    """La marca dentro de los atributos de producto (guardados en una línea, por ejemplo)."""
    return val.de_catalogo(db, datos, "marcas")


def valores_distintos(db: Session, articulo_ids: Select | Iterable[int]) -> dict[str, list[str]]:
    """{atributo de variante: valores distintos en su orden} de esos artículos."""
    res: dict[str, list] = {}
    for codigo, valor in db.execute(
            select(Atributo.codigo, ArticuloAtributo.valor).join(Atributo, Atributo.id == ArticuloAtributo.atributo_id)
            .where(ArticuloAtributo.articulo_id.in_(articulo_ids)).distinct()):
        res.setdefault(codigo, []).append(valor)
    orden = val.orden_de_valores(db)
    return {k: val.ordenados(res[k], orden.get(k)) for k in val.ordenar(db, res)}


# ---- Vocabulario de las condiciones de una categoría ---------------------------------------------
_CAMPOS_CONDICION = {
    "articulo.sku": "SKU", "articulo.codigo_proveedor": "Supplier item code", "articulo.codigo_barras": "Barcode (GTIN, EAN, UPC)",
    "articulo.generico": "Product code", "articulo.variante": "Variant (its values)", "articulo.descripcion": "Item description",
    "articulo.unidad": "Unit of measure", "articulo.tipo": "Item type (simple / pack or kit)",
    "articulo.peso_unitario": "Unit weight (kg)", "articulo.codigo_pack": "Pack ID",
    "articulo.familia_codigo": "Product family code", "articulo.familia": "Product family",
    "articulo.familia_ruta": "Product family path (codes)", "producto.nombre": "Product name",
    "producto.codigo_generico": "Product code (product)", "producto.marca": "Brand",
}


def campos_condiciones(db: Session) -> list[dict]:
    """Los datos con que se reconoce una categoría (las claves de `valores_condiciones`): los del
    artículo, los de su producto y un campo por cada atributo de variante y de producto."""
    res = [{"clave": k, "etiqueta": e} for k, e in _CAMPOS_CONDICION.items()]
    res += [{"clave": f"articulo.atributo.{a.codigo}", "etiqueta": a.nombre} for a in val.atributos(db, "VARIANTE")]
    res += [{"clave": f"producto.dato.{a.codigo}", "etiqueta": a.nombre} for a in val.atributos(db, "PRODUCTO")]
    return res
