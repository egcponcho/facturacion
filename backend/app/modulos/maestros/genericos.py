"""Productos («genéricos») y sus variantes, de cualquier tipo de producto.

Un producto se crea una vez con su código y sus datos maestros (marca, grupo,
proveedor, unidad, su familia; estilo y color solo si los usa) y luego se le
agregan variantes: cada una con sus valores de variante (talla, color, sabor,
presentación, concentración…) y lo propio (código, UPC, SKU del proveedor,
peso). Las variantes se escriben una por una o se combinan: todos los colores
por todas las tallas, todas las concentraciones por todos los envases.

El código de cada artículo lo define la empresa; si no se escribe, se arma con
el del producto más un código de la variante (el de su escala de valores, la
regla usual talla × 10 o el siguiente libre). La ficha técnica y la
clasificación arancelaria son del producto.
"""
import itertools
import re

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errores import ErrorNegocio
from app.modelos import (
    Articulo,
    AtributoVariante,
    EscalaTalla,
    GrupoArticulo,
    GrupoFamilia,
    Marca,
    Pais,
    Producto,
    Proveedor,
    Usuario,
)
from app.modulos.acceso.permisos import exigir
from app.modulos.comun import tabla
from app.modulos.comun.historial import registrar
from app.modulos.comun.texto import filtro_texto
from app.modulos.maestros import catalogos as cat_svc
from app.modulos.maestros import gobierno, variantes
from app.modulos.maestros import tallas as tallas_svc
from app.modulos.maestros.unidades import de_articulo, normalizar
from app.modulos.productos import perfil
from app.modulos.productos.productos import (
    MSG_CODIGO,
    asegurar_producto,
    codigo_valido,
    descripcion_comercial_simple,
    producto_por_generico,
)


def _articulos(db: Session, gen: str):
    return select(Articulo).where(Articulo.generico == gen)


def _sufijos(db: Session, gen: str) -> set[str]:
    """Códigos de talla ya usados: lo que sigue al genérico en el código de artículo."""
    return {s[len(gen):] for (s,) in db.execute(select(Articulo.sku).where(Articulo.sku.startswith(gen)))}


def sufijo_convencional(talla: str | None) -> str | None:
    """Código de talla usual: la talla numérica por 10 (7 → 070, 7.5 → 075,
    10.5 → 105, 13 → 130). Tallas de letra o prepacks no tienen uno fijo."""
    t = (talla or "").strip().replace(",", ".")
    if not re.fullmatch(r"\d{1,2}(\.\d)?", t):
        return None
    n = round(float(t) * 10)
    return f"{n:03d}" if 0 < n < 1000 and abs(float(t) * 10 - n) < 1e-9 else None


def siguiente_sufijo(db: Session, gen: str, usados: set[str] | None = None, talla: str | None = None, escala=None) -> str:
    """Código de talla para una talla nueva: el de su escala de tallas (o, sin
    escala, la regla usual talla × 10); si está usado, el siguiente libre."""
    usados = usados if usados is not None else _sufijos(db, gen)
    return tallas_svc.codigo(escala, talla, usados)


def detalle(db: Session, user: Usuario, gen: str) -> dict:
    exigir(user, "catalogos.ver")
    p = producto_por_generico(db, gen)
    if not p:
        raise ErrorNegocio(f"Product {gen} does not exist.", 404, "no_encontrado")
    arts = db.scalars(_articulos(db, gen).order_by(Articulo.sku)).all()
    return {
        "generico": gen, "producto_id": p.id, "estilo": p.estilo, "color": p.color, "marca_id": p.marca_id,
        "grupo_id": p.grupo_id, "proveedor_id": p.proveedor_id, "unidad": p.unidad, "nombre": p.nombre,
        "descripcion_comercial": p.descripcion_comercial,
        "grupo_producto_id": p.grupo_producto_id,
        "tallas": [{"id": a.id, "sku": a.sku, "sufijo": a.sku[len(gen):] if a.sku.startswith(gen) else "", "talla": a.talla, "upc": a.upc,
                    "sku_proveedor": a.sku_proveedor, "tipo": a.tipo, "activo": a.activo, "valores": a.variantes}
                   for a in arts],
        "siguiente": siguiente_sufijo(db, gen), "usados": sorted(a.sku[len(gen):] for a in arts if a.sku.startswith(gen)),
    }


def _maestros(db: Session, user: Usuario, datos, errores: list) -> tuple:
    """Familia, marca, grupo y proveedor del producto. Son opcionales: los exige la
    empresa (datos obligatorios de los artículos) o, al guardar las variantes, la familia."""
    familia = db.get(GrupoFamilia, datos.grupo_producto_id) if getattr(datos, "grupo_producto_id", None) else None
    if getattr(datos, "grupo_producto_id", None) and familia is None:
        errores.append({"campo": "grupo_producto_id", "mensaje": "Choose a product family."})
    if normalizar(datos.unidad) not in de_articulo():
        errores.append({"campo": "unidad", "mensaje": f"The unit is one of {', '.join(de_articulo())}."})
    # Un proveedor solo crea y cambia sus propios productos
    proveedor_id = user.proveedor_id or datos.proveedor_id
    elegidos = {"marca_id": (Marca, datos.marca_id), "grupo_id": (GrupoArticulo, datos.grupo_id),
                "proveedor_id": (Proveedor, proveedor_id)}
    exigidos = gobierno.obligatorios("articulos")
    valores = {}
    for campo, (modelo, ident) in elegidos.items():
        valores[campo] = db.get(modelo, ident) if ident else None
        if ident and valores[campo] is None:
            errores.append({"campo": campo, "mensaje": "Choose a value from the list."})
        elif not ident and campo in exigidos:
            errores.append({"campo": campo, "mensaje": "Your company requires this data for every product."})
    marca, prov = valores["marca_id"], valores["proveedor_id"]
    if marca and prov and marca.id not in {m.id for m in prov.marcas}:
        # Solo las marcas autorizadas al proveedor (Datos maestros → Proveedores)
        errores.append({"campo": "marca_id", "mensaje": f"{marca.codigo} is not a brand of {prov.nombre}."})
    return familia, marca, valores["grupo_id"], prov


def _id(x) -> int | None:
    return x.id if x is not None else None


def crear(db: Session, user: Usuario, datos) -> dict:
    """Producto nuevo con su núcleo (código, nombre, unidad), lo opcional que traiga y, si vienen, sus variantes."""
    exigir(user, "catalogos.crear")
    gobierno.exigir_responsable(db, user, "articulos")
    gen = (datos.generico or "").strip().upper()
    errores = []
    if not codigo_valido(gen):
        errores.append({"campo": "generico", "mensaje": f"Product code: {MSG_CODIGO}"})
    elif producto_por_generico(db, gen) or db.scalar(_articulos(db, gen).limit(1)):
        errores.append({"campo": "generico", "mensaje": f"Product {gen} already exists: add variants to it instead."})
    estilo, color = (datos.estilo or "").strip().upper() or None, (datos.color or "").strip() or None
    familia, marca, grupo, prov = _maestros(db, user, datos, errores)
    pais = (getattr(datos, "pais_origen", None) or "").strip().upper() or None
    if pais and not db.scalar(select(Pais.id).where(Pais.codigo == pais)):
        errores.append({"campo": "pais_origen", "mensaje": f"Country {pais} is not in the countries catalog."})
    if errores:
        raise ErrorNegocio("Check the product.", 422, "validacion", errores)
    # Sin nombre, el código: un producto siempre se puede nombrar en listas y documentos
    nombre = (datos.nombre or "").strip()[:200] or gen
    descripcion = (getattr(datos, "descripcion_comercial", None) or "").strip()[:300] or None
    p = Producto(codigo_generico=gen, proveedor_id=_id(prov), estilo=estilo, color=color, marca_id=_id(marca),
                 grupo_id=_id(grupo), unidad=normalizar(datos.unidad), nombre=nombre, pais_origen=pais,
                 grupo_producto_id=familia.id if familia else None, ficha={"comManual": True} if descripcion else {},
                 faltan=[], alertas_ok=[])
    db.add(p)
    try:
        db.flush()
    except IntegrityError:
        raise ErrorNegocio(f"Product {gen} already exists.", 409, "duplicado") from None
    # Escrita, se conserva; si no, se arma con la ficha
    p.descripcion_comercial = descripcion or descripcion_comercial_simple(p)
    perfil.exigir_producto(db, p)
    registrar(db, user, "genericos", p.id, "crear", {"generico": gen, "estilo": estilo, "color": color})
    combinar = getattr(datos, "combinar", None) or {}
    creadas = (agregar_tallas(db, user, gen, datos.tallas or [], getattr(datos, "escala_id", None), combinar)
               if datos.tallas or combinar else [])
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


def agregar_tallas(db: Session, user: Usuario, gen: str, tallas: list, escala_id: int | None = None,
                   combinar: dict | None = None) -> list[int]:
    """Variantes nuevas de un producto: heredan sus datos maestros y llevan sus
    valores de variante (escritos uno por uno o combinados)."""
    exigir(user, "catalogos.crear")
    gobierno.exigir_responsable(db, user, "articulos")
    p = producto_por_generico(db, gen)
    if not p:
        raise ErrorNegocio(f"Product {gen} does not exist.", 404, "no_encontrado")
    atributos = {a.codigo: a for a in db.scalars(select(AtributoVariante).where(AtributoVariante.activo.is_(True)))}
    sistema = {a.columna: a.codigo for a in atributos.values() if a.columna}
    filas = [({str(k).strip().upper(): str(v).strip() for k, v in (t.valores or {}).items() if str(v or "").strip()}
              | ({sistema.get("talla", "TALLA"): t.talla.strip().upper()} if t.talla and t.talla.strip() else {}), t)
             for t in tallas]
    filas += [(valores, None) for valores in combinaciones(combinar or {})]
    if not filas:
        raise ErrorNegocio("Write the variants or the values to combine.", 422, "validacion")
    if len(filas) > MAX_VARIANTES:
        raise ErrorNegocio(f"At most {MAX_VARIANTES} variants at a time.", 422, "validacion")
    usados = _sufijos(db, gen)
    escala = db.get(EscalaTalla, escala_id) if escala_id else None
    ya = {frozenset((k, str(v).upper()) for k, v in a.variantes.items())
          for a in db.scalars(_articulos(db, gen).where(Articulo.tipo == "SOLIDO"))}
    cat = cat_svc.CATALOGOS["articulos"]
    ids, errores = [], []
    for i, (valores, t) in enumerate(filas):
        # Un producto que fija su color lo da a todas sus variantes
        if p.color and sistema.get("color") and sistema["color"] not in valores:
            valores[sistema["color"]] = p.color
        texto = " · ".join(valores.values()) or "—"
        desconocidos = [k for k in valores if k not in atributos]
        if desconocidos:
            errores.append({"campo": f"tallas.{i}", "mensaje": f"Row {i + 1}: {desconocidos[0]} is not a variant attribute."})
            continue
        clave = frozenset((k, v.upper()) for k, v in valores.items())
        if clave in ya:
            errores.append({"campo": f"tallas.{i}", "mensaje": f"Variant {texto} already exists in product {gen}."})
            continue
        suf = ((t.sufijo if t else None) or "").strip().upper()
        sku = ((getattr(t, "sku", None) if t else None) or "").strip().upper()
        if sku:
            if not codigo_valido(sku) or db.scalar(select(Articulo.id).where(Articulo.sku == sku)):
                errores.append({"campo": f"tallas.{i}", "mensaje": f"Row {i + 1}: item code {sku} is taken or not valid."})
                continue
        else:
            if suf and (not re.fullmatch(r"[A-Z0-9._\-/]{1,20}", suf) or suf in usados):
                errores.append({"campo": f"tallas.{i}", "mensaje": f"Row {i + 1}: code {suf} is taken or not valid."})
                continue
            # El código sale del valor del atributo de la escala (o de la talla, con la regla usual)
            del_codigo = valores.get(escala.atributo or "TALLA") if escala else valores.get(sistema.get("talla", "TALLA"))
            suf = suf or siguiente_sufijo(db, gen, usados, del_codigo or "", escala if del_codigo else None)
            usados.add(suf)
            sku = gen + suf
        ya.add(clave)
        datos = {"sku": sku, "generico": gen, "sku_proveedor": ((t.sku_proveedor if t else None) or "").strip() or None,
                 "upc": ((t.upc if t else None) or "").strip() or None, "estilo": p.estilo,
                 "color": valores.get(sistema.get("color", "")), "talla": valores.get(sistema.get("talla", "")),
                 "marca_id": p.marca_id, "grupo_id": p.grupo_id, "proveedor_id": p.proveedor_id, "tipo": "SOLIDO",
                 "unidad": p.unidad or de_articulo()[0], "peso_unitario": getattr(t, "peso_unitario", None) if t else None,
                 **{f"atr.{k}": v for k, v in valores.items() if k not in sistema.values()}}
        try:
            limpio = cat_svc._limpiar(db, cat, {k: v for k, v in datos.items() if v is not None}, parcial=False)
        except ErrorNegocio as e:
            errores += [{"campo": f"tallas.{i}", "mensaje": f"Variant {texto}: {d['mensaje']}"} for d in e.detalle or []]
            continue
        variantes = limpio.pop("variantes", None)
        a = Articulo(**limpio, activo=True)
        db.add(a)
        if variantes:
            a.variantes = variantes
        db.flush()
        asegurar_producto(db, a)
        ids.append(a.id)
    if errores:
        raise ErrorNegocio("Some variants could not be added.", 422, "validacion", errores)
    perfil.exigir_variantes(db, [db.get(Articulo, i) for i in ids])
    registrar(db, user, "genericos", p.id, "tallas", {"generico": gen, "variantes": [" · ".join(v.values()) for v, _ in filas]})
    return ids


ORDEN = {"generico": Producto.codigo_generico, "estilo": Producto.estilo, "color": Producto.color,
         "marca_id": select(Marca.codigo).where(Marca.id == Producto.marca_id).scalar_subquery(),
         "grupo_id": select(GrupoArticulo.codigo).where(GrupoArticulo.id == Producto.grupo_id).scalar_subquery(),
         "proveedor_id": select(Proveedor.nombre).where(Proveedor.id == Producto.proveedor_id).scalar_subquery(),
         "unidad": Producto.unidad, "descripcion_comercial": Producto.descripcion_comercial, "codigo": Producto.codigo,
         "estado": Producto.estado}
# Filtro por columna (app/modulos/comun/tabla.py): marca, grupo y proveedor por
# su id (la pantalla muestra su nombre); las tallas, por las de sus artículos
COLUMNAS = {"generico": Producto.codigo_generico, "estilo": Producto.estilo, "color": Producto.color,
            "marca_id": Producto.marca_id, "grupo_id": Producto.grupo_id, "proveedor_id": Producto.proveedor_id,
            "unidad": Producto.unidad, "descripcion_comercial": Producto.descripcion_comercial, "codigo": Producto.codigo,
            "estado": Producto.estado, "tallas": tabla.Relacion(Articulo.talla, Articulo.producto_id, Producto.id)}


def _consulta(db: Session, user: Usuario, filtros: dict):
    """Genéricos visibles con la búsqueda y los filtros de la pantalla (sin los
    filtros por columna ni el orden)."""
    from sqlalchemy import or_

    from app.modulos.acceso.permisos import proveedor_filtro

    exigir(user, "catalogos.ver")
    q = select(Producto).where(Producto.codigo_generico.is_not(None))
    prov = proveedor_filtro(user, filtros.get("proveedor_id"))
    if prov:
        q = q.where(Producto.proveedor_id.in_(prov))
    for campo in ("marca_id", "grupo_id"):
        if filtros.get(campo):
            q = q.where(getattr(Producto, campo).in_([int(x) for x in str(filtros[campo]).split(",") if x.strip().isdigit()]))
    if filtros.get("unidad"):
        q = q.where(Producto.unidad == filtros["unidad"])
    if filtros.get("q"):
        q = q.where(filtro_texto(filtros["q"], lambda t: [
            Producto.codigo_generico.ilike(t), Producto.estilo.ilike(t), Producto.color.ilike(t),
            Producto.id.in_(select(Articulo.producto_id).where(or_(Articulo.sku.ilike(t), Articulo.upc.ilike(t), Articulo.sku_proveedor.ilike(t))))]))
    return q


def valores(db: Session, user: Usuario, columna: str, buscar: str | None, filtros_columna: dict, filtros: dict) -> list[dict]:
    """Valores únicos de una columna de la vista por genérico bajo los demás filtros."""
    expr = tabla.columna_valida(COLUMNAS, columna)
    q = tabla.aplicar(_consulta(db, user, filtros), COLUMNAS, filtros_columna, excepto=columna)
    return tabla.valores(db, q, expr, buscar, contar=Producto.id)


def listar(db: Session, user: Usuario, filtros: dict, orden: str | None, page: int, size: int,
           filtros_columna: dict | None = None) -> dict:
    """Vista compacta de artículos: un renglón por genérico con sus datos y
    sus tallas; se despliega para ver cada artículo."""
    from sqlalchemy import func

    from app.modulos.productos.productos import ESTADOS, fmt_codigo, rango_tallas

    q = tabla.aplicar(_consulta(db, user, filtros), COLUMNAS, filtros_columna or {})
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    col, _, d = (orden or "generico:asc").partition(":")
    c = ORDEN.get(col, Producto.codigo_generico)
    filas = db.scalars(q.order_by(c.desc() if d == "desc" else c.asc(), Producto.id).offset((page - 1) * size).limit(size)).all()
    arts: dict[int, list] = {}
    if filas:
        for a in db.scalars(select(Articulo).where(Articulo.producto_id.in_([p.id for p in filas])).order_by(Articulo.sku)):
            arts.setdefault(a.producto_id, []).append(a)
    items = []
    for p in filas:
        ls = arts.get(p.id, [])
        solidos = [a for a in ls if a.tipo == "SOLIDO"]
        items.append({
            "generico": p.codigo_generico, "producto_id": p.id, "estilo": p.estilo, "color": p.color,
            "marca_id": p.marca_id, "marca": p.marca.codigo if p.marca else None, "marca_nombre": p.marca.nombre if p.marca else None,
            "grupo_id": p.grupo_id, "grupo": p.grupo.codigo if p.grupo else None,
            "proveedor_id": p.proveedor_id, "proveedor": p.proveedor.nombre if p.proveedor else None,
            "unidad": p.unidad, "tallas": [a.talla for a in solidos], "rango_tallas": rango_tallas([a.talla for a in solidos]),
            "resumen_variantes": variantes.resumen(db, solidos),
            "n_tallas": len(solidos), "n_prepacks": len(ls) - len(solidos), "activos": sum(1 for a in ls if a.activo),
            "descripcion_comercial": p.descripcion_comercial, "estado": p.estado, "estado_txt": ESTADOS.get(p.estado, p.estado),
            "codigo": fmt_codigo(p.codigo) if p.codigo else None,
        })
    return {"items": items, "total": total, "page": page, "size": size}


def editar(db: Session, user: Usuario, gen: str, datos) -> dict:
    """Cambia los datos maestros del producto y los pasa a todas sus variantes."""
    exigir(user, "catalogos.editar")
    gobierno.exigir_responsable(db, user, "articulos")
    p = producto_por_generico(db, gen)
    if not p:
        raise ErrorNegocio(f"Product {gen} does not exist.", 404, "no_encontrado")
    arts = db.scalars(_articulos(db, gen)).all()
    estilo = (datos.estilo or "").strip().upper() or None
    color = (datos.color or "").strip() or None
    errores = []
    if (estilo != p.estilo or color != p.color) and any(a.tipo == "PREPACK" for a in arts):
        errores.append({"campo": "estilo", "mensaje": "The product has packs or kits: its model and fixed values cannot change."})
    familia, marca, grupo, prov = _maestros(db, user, datos, errores)
    if errores:
        raise ErrorNegocio("Check the product.", 422, "validacion", errores)
    antes = {"estilo": p.estilo, "color": p.color, "marca_id": p.marca_id, "grupo_id": p.grupo_id,
             "proveedor_id": p.proveedor_id, "unidad": p.unidad}
    unidad = normalizar(datos.unidad)
    p.estilo, p.color, p.unidad = estilo, color, unidad
    p.marca_id, p.grupo_id, p.proveedor_id = _id(marca), _id(grupo), _id(prov)
    if getattr(datos, "nombre", None) is not None:
        p.nombre = datos.nombre.strip()[:200] or p.codigo_generico
    if familia is not None:
        p.grupo_producto_id = familia.id
    for a in arts:
        a.marca_id, a.grupo_id, a.proveedor_id = p.marca_id, p.grupo_id, p.proveedor_id
        if a.tipo == "SOLIDO":
            a.estilo, a.unidad = estilo, unidad
            if color:  # un color del producto es el de todas sus variantes
                a.color = color
    db.flush()
    if not (p.ficha or {}).get("comManual"):
        db.refresh(p)
        p.descripcion_comercial = descripcion_comercial_simple(p)
    perfil.exigir_producto(db, p)
    perfil.exigir_variantes(db, [a for a in arts if a.activo])
    registrar(db, user, "genericos", p.id, "editar", {"generico": gen, "antes": antes})
    return detalle(db, user, gen)
