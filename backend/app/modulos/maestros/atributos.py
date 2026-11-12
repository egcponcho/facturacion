"""Atributos de producto y de variante: qué valor lleva cada uno y cómo se guarda.

La empresa define sus atributos (Datos maestros → Atributos): los del PRODUCTO
(marca, modelo, material, número ONU…) los comparten todas sus variantes; los
de la VARIANTE (talla, color, sabor, presentación, concentración…) distinguen
a cada una. Cada atributo dice qué valor lleva:

- texto: libre;
- numero: un número (en su unidad: 220 V, 500 ml);
- opcion: una de sus opciones;
- fecha: AAAA-MM-DD;
- bool: sí / no;
- catalogo: el código de un registro de un catálogo (la marca apunta a
  «marcas»); con proveedor, solo las marcas autorizadas a ese proveedor.

Cada atributo vale en sus familias (y en sus subfamilias y categorías) o, si es
general, en todas: un producto solo lleva los atributos que valen en su familia
(maestros/variantes.py). Un cambio que dejaría valores guardados fuera de su
familia (quitar una familia al atributo, mover el producto o una subfamilia)
se rechaza y dice qué productos lo impiden.

Ningún código de atributo está fijo en el sistema: la marca se reconoce por su
catálogo, no por llamarse MARCA.
"""
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errores import ErrorNegocio
from app.modelos import Atributo, Marca, Producto, ProductoAtributo

TIPOS = [["texto", "Text"], ["numero", "Number"], ["opcion", "One of the options"], ["fecha", "Date"],
         ["bool", "Yes / no"], ["catalogo", "A record of a catalog"]]
NIVELES = [["PRODUCTO", "Product (shared by its variants)"], ["VARIANTE", "Variant (tells variants apart)"]]
CATALOGOS = [["marcas", "Brands"]]
SI, NO = ("si", "sí", "yes", "true", "1", "x"), ("no", "false", "0")


def opciones(d) -> list[str]:
    texto = d.get("opciones") if isinstance(d, dict) else d.opciones
    return [x.strip() for x in (texto or "").split(",") if x.strip()]


def _dato(d, k):
    return d.get(k) if isinstance(d, dict) else getattr(d, k, None)


def valor(db: Session | None, d, v, proveedor_id: int | None = None) -> tuple[str | None, str | None]:
    """(valor normalizado, error) de un valor según el tipo de su atributo."""
    tipo = _dato(d, "tipo") or "texto"
    v = str(v).strip()
    if tipo == "numero":
        try:
            n = float(v.replace(",", "."))
        except ValueError:
            return None, f"{v} is not a number."
        return (str(int(n)) if n.is_integer() else f"{n:g}"), None
    if tipo == "opcion":
        validas = opciones(d)
        elegida = next((o for o in validas if o.lower() == v.lower()), None)
        if elegida is None:
            return None, f"{v} is not one of the options ({', '.join(validas)})."
        return elegida, None
    if tipo == "fecha":
        try:
            return date.fromisoformat(v[:10]).isoformat(), None
        except ValueError:
            return None, f"{v} is not a date (YYYY-MM-DD)."
    if tipo == "bool":
        if v.lower() in SI:
            return "true", None
        if v.lower() in NO:
            return "false", None
        return None, f"{v} is not yes or no."
    if tipo == "catalogo" and _dato(d, "catalogo") == "marcas" and db is not None:
        m = db.scalar(select(Marca).where(Marca.codigo == v.upper())) or \
            db.scalar(select(Marca).where(Marca.nombre.ilike(v)))
        if m is None:
            return None, f"{v} is not in the brands catalog."
        if proveedor_id:
            from app.modelos import Proveedor

            prov = db.get(Proveedor, proveedor_id)
            if prov and m.id not in {x.id for x in prov.marcas}:
                return None, (f"{m.codigo} is not a brand of {prov.nombre}." if prov.marcas
                              else f"{prov.nombre} has no brands yet: assign them in Suppliers first.")
        return m.codigo, None
    return v[:200], None


def de_nivel(db: Session, nivel: str, activos: bool = True) -> dict[str, Atributo]:
    q = select(Atributo).where(Atributo.nivel == nivel)
    if activos:
        q = q.where(Atributo.activo.is_(True))
    return {a.codigo: a for a in db.scalars(q.order_by(Atributo.orden, Atributo.codigo))}


def _familia_txt(grupo) -> str:
    return f"the family {grupo.nombre}" if grupo is not None else "products without a family"


def validar(db: Session, nivel: str, valores: dict | None, proveedor_id: int | None = None,
            campo: str = "atributos", *, grupo) -> tuple[dict, list[dict]]:
    """Valores normalizados de los atributos de ese nivel y los errores (códigos que no existen,
    que no valen en la familia `grupo` del producto o valores que no valen). Un valor vacío
    quita el atributo."""
    from app.modulos.maestros import variantes

    atrs = de_nivel(db, nivel)
    res, errores = {}, []
    for k, v in (valores or {}).items():
        k = str(k).strip().upper()
        if v in (None, "") or str(v).strip() == "":
            res[k] = None
            continue
        if k not in atrs:
            que = "product" if nivel == "PRODUCTO" else "variant"
            errores.append({"campo": f"{campo}.{k}", "mensaje": f"{k} is not a {que} attribute."})
            continue
        if not variantes.aplica(atrs[k], grupo):
            errores.append({"campo": f"{campo}.{k}", "mensaje": f"{atrs[k].nombre} does not apply to {_familia_txt(grupo)}."})
            continue
        res[k], msg = valor(db, atrs[k], v, proveedor_id)
        if msg:
            errores.append({"campo": f"{campo}.{k}", "mensaje": f"{atrs[k].nombre}: {msg}"})
    return res, errores


def poner(db: Session, p: Producto, valores: dict) -> dict:
    """Guarda en el producto los valores (ya validados) de sus atributos: un valor vacío
    quita el atributo. Devuelve {código: [antes, después]} de lo que cambió."""
    atrs = de_nivel(db, "PRODUCTO", activos=False)
    actuales = {x.atributo.codigo: x for x in p.atributos}
    cambios = {}
    for k, v in valores.items():
        x = actuales.get(k)
        if v in (None, ""):
            if x is not None:
                cambios[k] = [x.valor, None]
                p.atributos.remove(x)
            continue
        if x is None:
            p.atributos.append(ProductoAtributo(atributo=atrs[k], valor=v, organizacion_id=p.organizacion_id))
            cambios[k] = [None, v]
        elif x.valor != v:
            cambios[k] = [x.valor, v]
            x.valor = v
    return cambios


def exigidos_empresa(db: Session, nivel: str, grupo=None, todos: bool = False) -> list[str]:
    """Atributos de ese nivel que la empresa vuelve obligatorios para todos sus productos: los
    que valen en la familia `grupo` (con `todos`, sin mirar la familia)."""
    from app.modulos.maestros import gobierno, variantes

    codigos = de_nivel(db, nivel)
    return [c[9:] for c in sorted(gobierno.obligatorios("articulos"))
            if c.startswith("atributo.") and c[9:] in codigos and (todos or variantes.aplica(codigos[c[9:]], grupo))]


def exigir_empresa(db: Session, nivel: str, valores: dict, campo: str = "atributos", *, grupo) -> list[dict]:
    """Errores por los atributos que la empresa exige, valen en la familia y faltan."""
    atrs = de_nivel(db, nivel)
    return [{"campo": f"{campo}.{c}", "mensaje": f"Your company requires {atrs[c].nombre} for every product."}
            for c in exigidos_empresa(db, nivel, grupo) if valores.get(c) in (None, "")]


def fuera_de_familia(db: Session, p: Producto, grupo, quitados: set[str] = frozenset()) -> list[dict]:
    """Errores por los valores del producto y de sus variantes que no valdrían en la familia `grupo`
    (sin contar los atributos de producto que se están quitando)."""
    from app.modulos.maestros import variantes

    malos = {x.atributo.nombre for x in p.atributos
             if x.atributo.codigo not in quitados and not variantes.aplica(x.atributo, grupo)}
    malos |= {x.atributo.nombre for a in p.articulos for x in a.atributos if not variantes.aplica(x.atributo, grupo)}
    return [{"campo": "grupo_producto_id", "mensaje": f"The product has {n}, which does not apply to {_familia_txt(grupo)}: "
             "clear it first or add that family to the attribute."} for n in sorted(malos)]


def sin_alcance(db: Session, atrs: list[Atributo] | None = None, campo: str = "familias") -> list[dict]:
    """Errores por los valores ya guardados que quedarían fuera de las familias de su atributo
    (se llama después de cambiar las familias de un atributo o el árbol, antes de confirmar)."""
    from app.modelos import Articulo, ArticuloAtributo, GrupoProducto

    db.flush()
    if atrs is None:
        atrs = list(db.scalars(select(Atributo).where(Atributo.general.is_(False))))
    padres = dict(db.execute(select(GrupoProducto.id, GrupoProducto.padre_id)).all())

    def dentro(gid, permitidas) -> bool:
        vistos = set()
        while gid is not None and gid not in vistos:
            if gid in permitidas:
                return True
            vistos.add(gid)
            gid = padres.get(gid)
        return False

    errores = []
    for a in atrs:
        if a.general:
            continue
        permitidas = {f.id for f in a.familias}
        usados = db.execute(
            select(Producto.codigo_generico, Producto.grupo_producto_id).where(Producto.id.in_(
                select(ProductoAtributo.producto_id).where(ProductoAtributo.atributo_id == a.id)
                .union(select(Articulo.producto_id).join(ArticuloAtributo, ArticuloAtributo.articulo_id == Articulo.id)
                       .where(ArticuloAtributo.atributo_id == a.id))))).all()
        fuera = sorted(c or "?" for c, gid in usados if not dentro(gid, permitidas))
        if fuera:
            errores.append({"campo": campo, "mensaje": (
                f"{a.nombre} has values in {len(fuera)} product(s) of other families ({', '.join(fuera[:5])}"
                f"{'…' if len(fuera) > 5 else ''}): keep their families or clear those values first.")})
    return errores


def exigir(errores: list[dict], mensaje: str = "Check the product.") -> None:
    if errores:
        raise ErrorNegocio(mensaje, 422, "validacion", errores)
