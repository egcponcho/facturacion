"""Productos («genéricos») y sus variantes, de cualquier tipo de producto.

Un producto se crea una vez con su núcleo (código, nombre, unidad), su familia,
su proveedor si se compra, y sus atributos de producto (marca, modelo,
material…: los que la empresa defina). Luego se le agregan variantes: cada una
con sus valores de variante (talla, color, sabor, presentación,
concentración…) y lo propio (código de artículo, código de barras, código del
proveedor, peso). Las variantes se escriben una por una o se combinan: todos
los colores por todas las tallas, todas las concentraciones por todos los
envases.

El código de cada artículo lo define la empresa; si no se escribe, se arma con
el del producto más un código de la variante (el de su escala de valores o el
siguiente libre). La ficha técnica y la clasificación arancelaria son del
producto.
"""
import itertools
import re

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errores import ErrorNegocio
from app.modelos import (
    Articulo,
    ArticuloCodigo,
    EscalaValores,
    GrupoFamilia,
    Marca,
    Pais,
    Producto,
    ProductoAtributo,
    ProductoComex,
    Proveedor,
    Usuario,
)
from app.modulos.acceso.permisos import exigir
from app.modulos.comun import tabla
from app.modulos.comun.historial import registrar
from app.modulos.comun.texto import filtro_texto
from app.modulos.maestros import atributos as atr_svc
from app.modulos.maestros import escalas, gobierno, variantes
from app.modulos.maestros.unidades import de_articulo, normalizar
from app.modulos.productos import perfil
from app.modulos.productos.productos import (
    MSG_CODIGO,
    codigo_valido,
    descripcion_comercial_simple,
    producto_por_generico,
)


def _sufijos(db: Session, gen: str) -> set[str]:
    """Códigos de variante ya usados: lo que sigue al código del producto en el código de artículo."""
    return {s[len(gen):] for (s,) in db.execute(select(Articulo.sku).where(Articulo.sku.startswith(gen)))}


def siguiente_sufijo(db: Session, gen: str, usados: set[str] | None = None, valor: str | None = None, escala=None) -> str:
    """Código de una variante nueva: el de su valor en la escala (o, sin escala, la regla de
    la empresa); si está usado, el siguiente libre."""
    usados = usados if usados is not None else _sufijos(db, gen)
    return escalas.codigo(escala, valor, usados)


def _variante(db: Session, a: Articulo, gen: str) -> dict:
    return {"id": a.id, "sku": a.sku, "sufijo": a.sku[len(gen):] if a.sku.startswith(gen) else "",
            "codigo_barras": a.codigo_barras, "codigo_proveedor": a.codigo_proveedor, "codigo_pack": a.codigo_pack,
            "peso_unitario": a.peso_unitario, "tipo": a.tipo, "activo": a.activo,
            "valores": variantes.de_articulo(db, a), "variante": variantes.texto(variantes.de_articulo(db, a)) or None}


def detalle(db: Session, user: Usuario, gen: str) -> dict:
    exigir(user, "catalogos.ver")
    p = producto_por_generico(db, gen)
    if not p:
        raise ErrorNegocio(f"Product {gen} does not exist.", 404, "no_encontrado")
    arts = sorted(p.articulos, key=lambda a: a.sku)
    return {
        "generico": gen, "producto_id": p.id, "proveedor_id": p.proveedor_id, "unidad": p.unidad, "nombre": p.nombre,
        "descripcion_comercial": p.comex.descripcion_comercial, "grupo_producto_id": p.grupo_producto_id,
        "atributos": variantes.ordenar_producto(db, p.valores),
        "variantes": [_variante(db, a, gen) for a in arts],
        "siguiente": siguiente_sufijo(db, gen), "usados": sorted(a.sku[len(gen):] for a in arts if a.sku.startswith(gen)),
    }


def _nucleo(db: Session, user: Usuario, datos, errores: list) -> tuple:
    """Familia, unidad y proveedor del producto. La familia y el proveedor son opcionales:
    los exige la empresa (datos obligatorios) o, al guardar las variantes, la familia."""
    familia = db.get(GrupoFamilia, datos.grupo_producto_id) if getattr(datos, "grupo_producto_id", None) else None
    if getattr(datos, "grupo_producto_id", None) and familia is None:
        errores.append({"campo": "grupo_producto_id", "mensaje": "Choose a product family."})
    if normalizar(datos.unidad) not in de_articulo():
        errores.append({"campo": "unidad", "mensaje": f"The unit is one of {', '.join(de_articulo())}."})
    # Un proveedor solo crea y cambia sus propios productos
    proveedor_id = user.proveedor_id or datos.proveedor_id
    prov = db.get(Proveedor, proveedor_id) if proveedor_id else None
    if proveedor_id and prov is None:
        errores.append({"campo": "proveedor_id", "mensaje": "Choose a value from the list."})
    elif not proveedor_id and "proveedor_id" in gobierno.obligatorios("articulos"):
        errores.append({"campo": "proveedor_id", "mensaje": "Your company requires this data for every product."})
    return familia, prov


def _atributos(db: Session, p: Producto | None, datos, prov: Proveedor | None, grupo, errores: list, nuevo: bool) -> dict:
    """Los atributos de producto que vienen, validados (que valgan en la familia `grupo` y, con
    proveedor, que la marca sea suya) y con los que la empresa exige."""
    valores, errs = atr_svc.validar(db, "PRODUCTO", getattr(datos, "atributos", None) or {}, prov.id if prov else None,
                                    grupo=grupo)
    errores += errs
    finales = {**({} if nuevo or p is None else p.valores), **valores}
    errores += atr_svc.exigir_empresa(db, "PRODUCTO", finales, grupo=grupo)
    return valores


def crear(db: Session, user: Usuario, datos) -> dict:
    """Producto nuevo con su núcleo (código, nombre, unidad), lo opcional que traiga y, si vienen, sus variantes."""
    exigir(user, "catalogos.crear")
    gobierno.exigir_responsable(db, user, "articulos")
    gen = (datos.generico or "").strip().upper()
    errores = []
    if not codigo_valido(gen):
        errores.append({"campo": "generico", "mensaje": f"Product code: {MSG_CODIGO}"})
    elif producto_por_generico(db, gen):
        errores.append({"campo": "generico", "mensaje": f"Product {gen} already exists: add variants to it instead."})
    familia, prov = _nucleo(db, user, datos, errores)
    valores = _atributos(db, None, datos, prov, familia, errores, nuevo=True)
    pais = (getattr(datos, "pais_origen", None) or "").strip().upper() or None
    if pais and not db.scalar(select(Pais.id).where(Pais.codigo == pais)):
        errores.append({"campo": "pais_origen", "mensaje": f"Country {pais} is not in the countries catalog."})
    if errores:
        raise ErrorNegocio("Check the product.", 422, "validacion", errores)
    # Sin nombre, el código: un producto siempre se puede nombrar en listas y documentos
    nombre = (datos.nombre or "").strip()[:200] or gen
    descripcion = (getattr(datos, "descripcion_comercial", None) or "").strip()[:300] or None
    p = Producto(codigo_generico=gen, proveedor_id=prov.id if prov else None, unidad=normalizar(datos.unidad), nombre=nombre,
                 grupo_producto_id=familia.id if familia else None)
    p.comex.pais_origen = pais
    p.comex.ficha = {"comManual": True} if descripcion else {}
    db.add(p)
    atr_svc.poner(db, p, valores)
    try:
        db.flush()
    except IntegrityError:
        raise ErrorNegocio(f"Product {gen} already exists.", 409, "duplicado") from None
    # Escrita, se conserva; si no, se arma con la ficha
    p.comex.descripcion_comercial = descripcion or descripcion_comercial_simple(p)
    perfil.exigir_producto(db, p)
    registrar(db, user, "genericos", p.id, "crear", {"generico": gen, "atributos": {k: v for k, v in valores.items() if v}})
    combinar = getattr(datos, "combinar", None) or {}
    creadas = (agregar_variantes(db, user, gen, datos.variantes or [], getattr(datos, "escala_id", None), combinar)
               if datos.variantes or combinar else [])
    return {**detalle(db, user, gen), "creadas": len(creadas)}


MAX_VARIANTES = 500


def combinaciones(combinar: dict[str, list[str]]) -> list[dict]:
    """Todas las combinaciones de los valores, en el orden dado ({"COLOR": [A, B], "TALLA": [7, 8]}
    → A·7, A·8, B·7, B·8)."""
    ejes = [(str(k).strip().upper(), [str(v).strip() for v in vs if str(v).strip()]) for k, vs in (combinar or {}).items()]
    ejes = [(k, vs) for k, vs in ejes if k and vs]
    if not ejes:
        return []
    total = 1
    for _, vs in ejes:
        total *= len(vs)
    if total > MAX_VARIANTES:
        raise ErrorNegocio(f"That is {total} variants: at most {MAX_VARIANTES} at a time.", 422, "validacion")
    return [dict(zip([k for k, _ in ejes], combo, strict=True)) for combo in itertools.product(*[vs for _, vs in ejes])]


def nueva_variante(db: Session, p: Producto, sku: str, valores: dict, codigo_barras: str | None = None,
                   codigo_proveedor: str | None = None, peso_unitario: float | None = None, unidad: str | None = None) -> Articulo:
    """Una variante simple del producto, con sus valores y sus códigos (ya validados)."""
    a = Articulo(sku=sku, producto=p, unidad=unidad or p.unidad or de_articulo()[0], peso_unitario=peso_unitario,
                 tipo="SOLIDO", activo=True, organizacion_id=p.organizacion_id)
    db.add(a)
    a.variantes = valores
    a.poner_codigo("BARRAS", codigo_barras)
    a.poner_codigo("PROVEEDOR", codigo_proveedor, p.proveedor_id)
    return a


def validar_codigos(db: Session, codigo_barras: str | None, codigo_proveedor: str | None) -> list[str]:
    """Largo de los códigos y que el código de barras sea solo dígitos (GTIN/EAN/UPC) o un código propio."""
    errores = []
    if codigo_barras and (len(codigo_barras) > 40 or not re.fullmatch(r"[A-Za-z0-9\-.]+", codigo_barras)):
        errores.append(f"barcode {codigo_barras} is not valid (letters and numbers, up to 40).")
    if codigo_proveedor and len(codigo_proveedor) > 60:
        errores.append("the supplier code has 60 characters at most.")
    return errores


def agregar_variantes(db: Session, user: Usuario, gen: str, filas_in: list, escala_id: int | None = None,
                      combinar: dict | None = None) -> list[int]:
    """Variantes nuevas de un producto: llevan sus valores de variante (escritos uno por uno o combinados)."""
    exigir(user, "catalogos.crear")
    gobierno.exigir_responsable(db, user, "articulos")
    p = producto_por_generico(db, gen)
    if not p:
        raise ErrorNegocio(f"Product {gen} does not exist.", 404, "no_encontrado")
    filas = [({str(k).strip().upper(): str(v).strip() for k, v in (t.valores or {}).items() if str(v or "").strip()}, t)
             for t in filas_in]
    filas += [(valores, None) for valores in combinaciones(combinar or {})]
    if not filas:
        raise ErrorNegocio("Write the variants or the values to combine.", 422, "validacion")
    if len(filas) > MAX_VARIANTES:
        raise ErrorNegocio(f"At most {MAX_VARIANTES} variants at a time.", 422, "validacion")
    usados = _sufijos(db, gen)
    escala = db.get(EscalaValores, escala_id) if escala_id else None
    ejes = variantes.ejes_de_grupo(db, p.grupo_producto)
    ya = {frozenset((k, str(v).upper()) for k, v in a.variantes.items()) for a in p.articulos if a.tipo == "SOLIDO"}
    ids, nuevas, errores = [], [], []
    for i, (crudos, t) in enumerate(filas):
        valores, errs = atr_svc.validar(db, "VARIANTE", crudos, campo=f"variantes.{i}", grupo=p.grupo_producto)
        valores = {k: v for k, v in valores.items() if v}
        texto = " · ".join(valores.values()) or "—"
        if errs:
            errores += [{**e, "mensaje": f"Row {i + 1}: {e['mensaje']}"} for e in errs]
            continue
        clave = frozenset((k, v.upper()) for k, v in valores.items())
        if clave in ya:
            errores.append({"campo": f"variantes.{i}", "mensaje": f"Variant {texto} already exists in product {gen}."})
            continue
        suf = ((t.sufijo if t else None) or "").strip().upper()
        sku = ((getattr(t, "sku", None) if t else None) or "").strip().upper()
        if sku:
            if not codigo_valido(sku) or db.scalar(select(Articulo.id).where(Articulo.sku == sku)):
                errores.append({"campo": f"variantes.{i}", "mensaje": f"Row {i + 1}: item code {sku} is taken or not valid."})
                continue
        else:
            if suf and (not re.fullmatch(r"[A-Z0-9._\-/]{1,20}", suf) or suf in usados):
                errores.append({"campo": f"variantes.{i}", "mensaje": f"Row {i + 1}: code {suf} is taken or not valid."})
                continue
            # El código sale del valor del atributo de la escala (o del último eje de la familia, con la regla de la empresa)
            base = valores.get(escala.atributo) if escala else next((valores[e] for e in reversed(ejes) if e in valores), "")
            suf = suf or siguiente_sufijo(db, gen, usados, base or "", escala if base else None)
            usados.add(suf)
            sku = gen + suf
        barras = ((t.codigo_barras if t else None) or "").strip() or None
        prov = ((t.codigo_proveedor if t else None) or "").strip() or None
        malos = validar_codigos(db, barras, prov)
        if malos:
            errores += [{"campo": f"variantes.{i}", "mensaje": f"Variant {texto}: {m}"} for m in malos]
            continue
        ya.add(clave)
        nuevas.append(nueva_variante(db, p, sku, valores, barras, prov, getattr(t, "peso_unitario", None) if t else None))
    if errores:
        raise ErrorNegocio("Some variants could not be added.", 422, "validacion", errores)
    try:
        db.flush()
    except IntegrityError:
        raise ErrorNegocio("An item code is already taken.", 409, "duplicado") from None
    ids = [a.id for a in nuevas]
    errores = [e for a in nuevas for e in _exigidos_empresa(db, a)]
    if errores:
        raise ErrorNegocio("Some data your company requires is missing.", 422, "validacion", errores)
    perfil.exigir_variantes(db, nuevas)
    registrar(db, user, "genericos", p.id, "variantes", {"generico": gen, "variantes": [" · ".join(v.values()) for v, _ in filas]})
    return ids


def _exigidos_empresa(db: Session, a: Articulo) -> list[dict]:
    """Lo que la empresa exige a cada variante: sus códigos, su peso y sus atributos de variante."""
    exigidos = gobierno.obligatorios("articulos")
    valores = {"codigo_barras": a.codigo_barras, "codigo_proveedor": a.codigo_proveedor, "peso_unitario": a.peso_unitario}
    errores = [{"campo": c, "mensaje": f"{a.sku}: your company requires this data for every item."}
               for c in ("codigo_barras", "codigo_proveedor", "peso_unitario") if c in exigidos and valores[c] in (None, "")]
    if a.tipo == "SOLIDO":
        errores += [{**e, "mensaje": f"{a.sku}: {e['mensaje']}"}
                    for e in atr_svc.exigir_empresa(db, "VARIANTE", a.variantes, grupo=a.familia_efectiva)]
    return errores


def _de_comex(campo: str):
    """Un dato de la ficha de comercio exterior del producto, para ordenar y filtrar la lista."""
    c = getattr(ProductoComex, campo)
    return select(c).where(ProductoComex.producto_id == Producto.id).correlate_except(ProductoComex).scalar_subquery()


# Orden y filtro por columna (app/modulos/comun/tabla.py) de la vista por producto. Los atributos
# del producto («atr.<código>») y los valores de sus variantes se filtran por sus filas.
ORDEN = {"generico": Producto.codigo_generico, "nombre": Producto.nombre,
         "proveedor_id": select(Proveedor.nombre).where(Proveedor.id == Producto.proveedor_id).scalar_subquery(),
         "unidad": Producto.unidad, "descripcion_comercial": _de_comex("descripcion_comercial"), "codigo": _de_comex("codigo"),
         "estado": _de_comex("estado")}
COLUMNAS = {"generico": Producto.codigo_generico, "nombre": Producto.nombre, "proveedor_id": Producto.proveedor_id,
            "unidad": Producto.unidad, "descripcion_comercial": _de_comex("descripcion_comercial"), "codigo": _de_comex("codigo"),
            "estado": _de_comex("estado")}


def columnas(db: Session) -> dict:
    """Las columnas fijas más una por atributo de producto y una por atributo de variante."""
    from app.modelos import ArticuloAtributo

    res = dict(COLUMNAS)
    for a in variantes.atributos(db, "PRODUCTO"):
        res[f"atr.{a.codigo}"] = tabla.Relacion(ProductoAtributo.valor, ProductoAtributo.producto_id, Producto.id,
                                                donde=ProductoAtributo.atributo_id == a.id)
    for a in variantes.atributos(db):
        res[f"var.{a.codigo}"] = tabla.Relacion(
            ArticuloAtributo.valor, select(Articulo.producto_id).where(Articulo.id == ArticuloAtributo.articulo_id)
            .scalar_subquery(), Producto.id, donde=ArticuloAtributo.atributo_id == a.id)
    return res


def _consulta(db: Session, user: Usuario, filtros: dict):
    """Productos visibles con la búsqueda y los filtros de la pantalla (sin los
    filtros por columna ni el orden)."""
    from app.modulos.acceso.permisos import proveedor_filtro

    exigir(user, "catalogos.ver")
    q = select(Producto).where(Producto.codigo_generico.is_not(None))
    prov = proveedor_filtro(user, filtros.get("proveedor_id"))
    if prov:
        q = q.where(Producto.proveedor_id.in_(prov))
    if filtros.get("familia"):
        from app.modulos.productos.productos import rama_de_grupos

        q = q.where(Producto.grupo_producto_id.in_(rama_de_grupos(db, filtros["familia"])))
    if filtros.get("unidad"):
        q = q.where(Producto.unidad == filtros["unidad"])
    if filtros.get("q"):
        q = q.where(filtro_texto(filtros["q"], lambda t: [
            Producto.codigo_generico.ilike(t), Producto.nombre.ilike(t),
            Producto.id.in_(select(ProductoAtributo.producto_id).where(ProductoAtributo.valor.ilike(t))),
            Producto.id.in_(select(Articulo.producto_id).where(Articulo.sku.ilike(t))),
            Producto.id.in_(select(Articulo.producto_id).join(ArticuloCodigo).where(ArticuloCodigo.valor.ilike(t)))]))
    return q


def valores(db: Session, user: Usuario, columna: str, buscar: str | None, filtros_columna: dict, filtros: dict) -> list[dict]:
    """Valores únicos de una columna de la vista por producto bajo los demás filtros."""
    cols = columnas(db)
    expr = tabla.columna_valida(cols, columna)
    q = tabla.aplicar(_consulta(db, user, filtros), cols, filtros_columna, excepto=columna)
    return tabla.valores(db, q, expr, buscar, contar=Producto.id)


def listar(db: Session, user: Usuario, filtros: dict, orden: str | None, page: int, size: int,
           filtros_columna: dict | None = None) -> dict:
    """Vista compacta de artículos: un renglón por producto con sus atributos y el
    resumen de sus variantes; se despliega para ver cada variante."""
    from app.modulos.productos.productos import ESTADOS, fmt_codigo

    q = tabla.aplicar(_consulta(db, user, filtros), columnas(db), filtros_columna or {})
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    col, _, d = (orden or "generico:asc").partition(":")
    c = ORDEN.get(col, Producto.codigo_generico)
    filas = db.scalars(q.order_by(c.desc() if d == "desc" else c.asc(), Producto.id).offset((page - 1) * size).limit(size)).all()
    arts: dict[int, list] = {}
    if filas:
        for a in db.scalars(select(Articulo).where(Articulo.producto_id.in_([p.id for p in filas])).order_by(Articulo.sku)):
            arts.setdefault(a.producto_id, []).append(a)
    marcas = {m.codigo: m.nombre for m in db.scalars(select(Marca))}
    items = []
    for p in filas:
        ls = arts.get(p.id, [])
        simples = [a for a in ls if a.tipo == "SOLIDO"]
        items.append({
            "generico": p.codigo_generico, "producto_id": p.id, "nombre": p.nombre,
            "atributos": variantes.ordenar_producto(db, p.valores),
            "marca": p.marca_codigo, "marca_nombre": marcas.get(p.marca_codigo),
            "proveedor_id": p.proveedor_id, "proveedor": p.proveedor.nombre if p.proveedor else None,
            "grupo_producto_id": p.grupo_producto_id, "unidad": p.unidad,
            "resumen_variantes": variantes.resumen(db, simples), "variantes_atributos": variantes.por_atributo(db, simples),
            "n_variantes": len(simples), "n_compuestos": len(ls) - len(simples), "activos": sum(1 for a in ls if a.activo),
            "descripcion_comercial": p.comex.descripcion_comercial, "estado": p.comex.estado,
            "estado_txt": ESTADOS.get(p.comex.estado, p.comex.estado),
            "codigo": fmt_codigo(p.comex.codigo) if p.comex.codigo else None,
        })
    return {"items": items, "total": total, "page": page, "size": size}


def editar(db: Session, user: Usuario, gen: str, datos) -> dict:
    """Cambia el núcleo y los atributos del producto (los comparten todas sus variantes)."""
    exigir(user, "catalogos.editar")
    gobierno.exigir_responsable(db, user, "articulos")
    p = producto_por_generico(db, gen)
    if not p:
        raise ErrorNegocio(f"Product {gen} does not exist.", 404, "no_encontrado")
    errores = []
    familia, prov = _nucleo(db, user, datos, errores)
    if prov is not None and p.proveedor_id and prov.id != p.proveedor_id and _en_ordenes(db, p):
        errores.append({"campo": "proveedor_id", "mensaje": "The product is on purchase orders: its supplier cannot change."})
    grupo = familia if familia is not None else p.grupo_producto
    valores = _atributos(db, p, datos, prov, grupo, errores, nuevo=False)
    if familia is not None and familia.id != p.grupo_producto_id:
        # Lo que ya tiene el producto (y lo que no se está quitando) debe valer en la familia nueva
        errores += atr_svc.fuera_de_familia(db, p, familia, quitados={k for k, v in valores.items() if v in (None, "")})
    if errores:
        raise ErrorNegocio("Check the product.", 422, "validacion", errores)
    antes = {"proveedor_id": p.proveedor_id, "unidad": p.unidad, "grupo_producto_id": p.grupo_producto_id}
    p.unidad = normalizar(datos.unidad)
    p.proveedor_id = prov.id if prov else None
    if getattr(datos, "nombre", None) is not None:
        p.nombre = datos.nombre.strip()[:200] or p.codigo_generico
    if familia is not None:
        p.grupo_producto_id = familia.id
    cambios = atr_svc.poner(db, p, valores)
    for a in p.articulos:
        if a.tipo == "SOLIDO":
            a.unidad = p.unidad
    db.flush()
    if not (p.comex.ficha or {}).get("comManual"):
        db.refresh(p)
        p.comex.descripcion_comercial = descripcion_comercial_simple(p)
    perfil.exigir_producto(db, p)
    perfil.exigir_variantes(db, [a for a in p.articulos if a.activo])
    registrar(db, user, "genericos", p.id, "editar", {"generico": gen, "antes": antes, "atributos": cambios})
    return detalle(db, user, gen)


def _en_ordenes(db: Session, p: Producto) -> bool:
    from app.modelos import PosicionOC

    return bool(db.scalar(select(PosicionOC.id).join(Articulo, Articulo.id == PosicionOC.articulo_id)
                          .where(Articulo.producto_id == p.id).limit(1)))
