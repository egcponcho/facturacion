"""Qué datos pide un producto: su perfil de datos.

Un producto de cualquier rubro se reconoce por lo mismo: su código, su nombre y
la unidad en que se cuenta; cada variante, por su código y los valores de los
ejes de su familia. Ese es el núcleo y lo exige siempre el sistema.

Todo lo demás (proveedor, marca, grupo, modelo, código de barras, código del
proveedor, peso, país de origen, atributos y campos propios) es opcional, y lo
vuelve obligatorio:

- la empresa, para todos sus productos: Datos maestros → Artículos → datos
  obligatorios (maestros/gobierno.py); se aplica en cada variante que se guarda;
- la familia, para los suyos: sus campos obligatorios (GrupoProducto.campos,
  heredados por el árbol). Son los mismos que el etiquetado revisa antes de
  imprimir; aquí se exigen al crear y al cambiar el producto, así no aparecen
  faltando recién al etiquetar.

De los campos de la familia solo se exigen al guardar los que se escriben en
el producto o en la variante (EDITABLES); los que salen de la ficha técnica
(composición, uso, atributos de clasificación) se completan en la ficha y los
sigue revisando el etiquetado.
"""
from sqlalchemy.orm import Session

from app.core.errores import ErrorNegocio
from app.modelos import Articulo, Producto, Usuario
from app.modulos.acceso.permisos import exigir_alguno

# El núcleo: lo que pide el sistema a cualquier producto (código, nombre, unidad)
NUCLEO = ("generico", "nombre", "unidad")

# Campos de la familia que se escriben en el producto o en la variante
EDITABLES = {
    "articulo.upc", "articulo.sku_proveedor", "articulo.peso_unitario", "articulo.estilo", "articulo.color",
    "articulo.talla", "articulo.marca", "articulo.marca_codigo", "articulo.grupo", "articulo.grupo_codigo",
    "producto.nombre", "producto.descripcion_comercial", "producto.pais_origen",
}
PREFIJOS_EDITABLES = ("articulo.atributo.", "articulo.extra.")

# El mismo dato con dos claves (código y nombre): se muestra y se exige una vez
EQUIVALENTES = {"articulo.marca": "articulo.marca_codigo", "articulo.grupo": "articulo.grupo_codigo"}


def editable(clave: str) -> bool:
    return clave in EDITABLES or clave.startswith(PREFIJOS_EDITABLES)


def grupo_de(a: Articulo):
    """El grupo de producto más preciso del artículo: el suyo, el de su producto
    (que puede ser una categoría) o el de su grupo de artículos."""
    if a.grupo_producto is not None:
        return a.grupo_producto
    if a.producto is not None and a.producto.grupo_producto is not None:
        return a.producto.grupo_producto
    return a.grupo.grupo_producto if a.grupo is not None else None


def exigidos(grupo) -> list[str]:
    """Campos que la familia (y las que la contienen) vuelve obligatorios al guardar."""
    from app.modulos.etiquetado.familias import obligatorios

    res = []
    for c in obligatorios(grupo):
        c = EQUIVALENTES.get(c, c)
        if editable(c) and c not in res:
            res.append(c)
    return res


def _faltan(valores: dict, claves: list[str]) -> list[str]:
    return [c for c in claves if valores.get(c) in (None, "")]


def _etiquetas(db: Session) -> dict[str, str]:
    from app.modulos.etiquetado import campos

    return {c.clave: c.etiqueta for c in campos.catalogo(db, "ARTICULO")}


def faltan_variante(a: Articulo) -> list[str]:
    from app.modulos.etiquetado.campos import valores_articulo

    return _faltan(valores_articulo(a), exigidos(grupo_de(a)))


def exigir_variantes(db: Session, articulos: list[Articulo]) -> None:
    """422 si alguna variante no tiene lo que su familia vuelve obligatorio."""
    if not articulos:
        return
    db.flush()
    nombres, errores = _etiquetas(db), []
    for a in articulos:
        db.refresh(a)
        faltan = faltan_variante(a)
        if faltan:
            g = grupo_de(a)
            errores.append({"campo": "perfil", "clave": a.sku, "faltan": faltan,
                            "mensaje": f"{a.sku}: the family {g.nombre if g else ''} requires "
                                       f"{', '.join(nombres.get(c, c) for c in faltan)}."})
    if errores:
        raise ErrorNegocio("Some data the product family requires is missing.", 422, "perfil_incompleto", errores)


def exigir_producto(db: Session, p: Producto) -> None:
    """422 si al producto le falta un dato propio (producto.*) que su familia vuelve obligatorio."""
    claves = [c for c in exigidos(p.grupo_producto) if c.startswith("producto.")]
    if not claves:
        return
    valores = {"producto.nombre": p.nombre, "producto.descripcion_comercial": p.descripcion_comercial,
               "producto.pais_origen": p.pais_origen}
    faltan = _faltan(valores, claves)
    if faltan:
        nombres = _etiquetas(db)
        raise ErrorNegocio("Some data the product family requires is missing.", 422, "perfil_incompleto",
                           [{"campo": c.split(".", 1)[1], "mensaje": f"The family {p.grupo_producto.nombre} requires "
                                                                     f"{nombres.get(c, c)}."} for c in faltan])


def perfil(db: Session, user: Usuario, grupo_id: int | None = None) -> dict:
    """Lo que el asistente y la ficha piden para un producto de la familia (o sin familia):
    el núcleo, lo que la empresa vuelve obligatorio y lo que vuelve obligatorio la familia."""
    from app.modelos import GrupoProducto
    from app.modulos.etiquetado.familias import obligatorios
    from app.modulos.maestros import catalogos, gobierno, variantes

    exigir_alguno(user, "catalogos.ver", "producto.ficha")
    grupo = db.get(GrupoProducto, grupo_id) if grupo_id else None
    if grupo_id and grupo is None:
        raise ErrorNegocio("The product family does not exist.", 404, "no_encontrado")
    nombres = _etiquetas(db)
    campos_art = {c["nombre"]: c["etiqueta"] for c in catalogos.CATALOGOS["articulos"]["campos"]}
    de_familia = []
    for c in obligatorios(grupo):
        c = EQUIVALENTES.get(c, c)
        if c not in {x["clave"] for x in de_familia}:
            de_familia.append({"clave": c, "etiqueta": nombres.get(c, c), "al_guardar": editable(c)})
    return {
        "nucleo": list(NUCLEO),
        "empresa": [{"campo": c, "etiqueta": campos_art.get(c, c)} for c in sorted(gobierno.obligatorios("articulos"))],
        "familia": de_familia,
        "ejes": variantes.ejes_de_grupo(grupo),
    }
