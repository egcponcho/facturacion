"""Qué datos pide un producto: su perfil de datos.

Un producto de cualquier rubro se reconoce por lo mismo: su código, su nombre y
la unidad en que se cuenta; cada variante, por su código y los valores de los
ejes de su familia. Ese es el núcleo y lo exige siempre el sistema.

Todo lo demás (familia, proveedor, atributos de producto como la marca o el
modelo, atributos de variante, código de barras, código del proveedor, peso,
país de origen) es opcional, y lo vuelve obligatorio:

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
    "articulo.codigo_barras", "articulo.codigo_proveedor", "articulo.peso_unitario",
    "producto.nombre", "producto.descripcion_comercial", "producto.pais_origen",
}
PREFIJOS_EDITABLES = ("articulo.atributo.", "producto.dato.")
# El nombre de la marca sale del atributo de producto que apunta al catálogo de marcas
EQUIVALENTES = {"producto.marca": None}


def editable(clave: str) -> bool:
    return clave in EDITABLES or clave.startswith(PREFIJOS_EDITABLES)


def grupo_de(a: Articulo):
    """El grupo de producto del artículo: el de su producto (una familia o una categoría)."""
    return a.producto.grupo_producto if a.producto is not None else None


def _equivalente(db: Session | None, c: str) -> str:
    """«producto.marca» se exige como el atributo de marca del producto (el que apunta a «marcas»)."""
    if c in EQUIVALENTES and db is not None:
        from app.modulos.maestros import variantes

        marca = next((a.codigo for a in variantes.atributos(db, "PRODUCTO") if a.catalogo == "marcas"), None)
        return f"producto.dato.{marca}" if marca else c
    return c


def obligatorios(grupo) -> list[str]:
    """Campos obligatorios del nodo y de las familias que lo contienen."""
    res: list[str] = []
    for g in grupo.ruta() if grupo is not None else []:
        res += [c["campo"] for c in g.campos or [] if c.get("obligatorio") and c["campo"] not in res]
    return res


def exigidos(grupo, db: Session | None = None) -> list[str]:
    """Campos que la familia (y las que la contienen) vuelve obligatorios al guardar."""
    res = []
    for c in obligatorios(grupo):
        c = _equivalente(db, c)
        if editable(c) and c not in res:
            res.append(c)
    return res


def _faltan(valores: dict, claves: list[str]) -> list[str]:
    return [c for c in claves if valores.get(c) in (None, "")]


def _etiquetas(db: Session) -> dict[str, str]:
    from app.modulos.etiquetado import campos

    return {c.clave: c.etiqueta for c in campos.catalogo(db, "ARTICULO")}


def faltan_variante(a: Articulo) -> list[str]:
    from sqlalchemy.orm import object_session

    from app.modulos.catalogo import servicio as catalogo
    from app.modulos.etiquetado.campos import valores_articulo

    db = object_session(a)
    claves = exigidos(grupo_de(a), db)
    if a.tipo == "PREPACK":  # un pack o kit no tiene valores de variante propios
        claves = [c for c in claves if not c.startswith("articulo.atributo.")]
    return _faltan(valores_articulo(db, catalogo.ficha_de_modelo(db, a)), claves)


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
    claves = [c for c in exigidos(p.grupo_producto, db) if c.startswith("producto.")]
    if not claves:
        return
    valores = {"producto.nombre": p.nombre, "producto.descripcion_comercial": p.descripcion_comercial,
               "producto.pais_origen": p.pais_origen, **{f"producto.dato.{k}": v for k, v in p.valores.items()}}
    faltan = _faltan(valores, claves)
    if faltan:
        nombres = _etiquetas(db)
        raise ErrorNegocio("Some data the product family requires is missing.", 422, "perfil_incompleto",
                           [{"campo": c.split(".", 1)[1].replace("dato.", "atributos.", 1),
                             "mensaje": f"The family {p.grupo_producto.nombre} requires {nombres.get(c, c)}."} for c in faltan])


def perfil(db: Session, user: Usuario, grupo_id: int | None = None) -> dict:
    """Lo que el asistente y la ficha piden para un producto de la familia (o sin familia):
    el núcleo, lo que la empresa vuelve obligatorio y lo que vuelve obligatorio la familia."""
    from app.modelos import GrupoProducto
    from app.modulos.maestros import catalogos, gobierno, variantes

    exigir_alguno(user, "catalogos.ver", "producto.ficha")
    grupo = db.get(GrupoProducto, grupo_id) if grupo_id else None
    if grupo_id and grupo is None:
        raise ErrorNegocio("The product family does not exist.", 404, "no_encontrado")
    nombres = _etiquetas(db)
    campos_art = {c["nombre"]: c["etiqueta"] for c in catalogos.CATALOGOS["articulos"]["campos"]}
    de_familia = []
    for c in obligatorios(grupo):
        c = _equivalente(db, c)
        if c not in {x["clave"] for x in de_familia}:
            de_familia.append({"clave": c, "etiqueta": nombres.get(c, c), "al_guardar": editable(c)})
    nombres_atr = variantes.nombres(db)
    aplican = {a.codigo for n in ("PRODUCTO", "VARIANTE") for a in variantes.de_grupo(db, grupo, n)}
    return {
        "nucleo": list(NUCLEO),
        "empresa": [{"campo": c, "etiqueta": nombres_atr.get(c[9:], c) if c.startswith("atributo.") else campos_art.get(c, c)}
                    for c in sorted(gobierno.obligatorios("articulos")) if not c.startswith("atributo.") or c[9:] in aplican],
        "familia": de_familia,
        # Los atributos de variante de la familia (con ellos se distinguen sus variantes) y sus
        # atributos de producto (el formulario muestra uno por atributo): solo los que valen en ella
        "ejes": variantes.ejes_de_grupo(db, grupo),
        "atributos": [{"codigo": a.codigo, "nombre": a.nombre, "tipo": a.tipo, "catalogo": a.catalogo,
                       "opciones": [o.strip() for o in (a.opciones or "").split(",") if o.strip()], "unidad": a.unidad}
                      for a in variantes.de_grupo(db, grupo, "PRODUCTO")],
    }
