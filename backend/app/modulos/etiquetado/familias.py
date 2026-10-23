"""Familias de etiquetado: las define cada empresa (código, nombre,
descripción, orden, activa) junto con los campos habituales de la familia y
cuáles son obligatorios. Son independientes de la clasificación arancelaria.

Una familia en uso (productos, usos de diseño o subfamilias) no se borra: se
desactiva. La familia es del producto: la comparten todas sus variantes y
sus packs.
"""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errores import ErrorNegocio
from app.modelos import (
    Articulo,
    ArticuloCodigo,
    FamiliaEtiquetado,
    Marca,
    Producto,
    ProductoAtributo,
    UsoDiseno,
    Usuario,
)
from app.modulos.acceso.permisos import exigir, exigir_alguno, exigir_interno
from app.modulos.comun.historial import registrar
from app.modulos.comun.texto import filtro_texto
from app.modulos.etiquetado import campos as svc_campos
from app.modulos.grupos import arbol

MAX_CAMPOS = 60


def familia_sql():
    """La familia de un artículo en SQL: la de su producto."""
    return select(Producto.familia_etiquetado_id).where(Producto.id == Articulo.producto_id).scalar_subquery()


def familia_producto_sql():
    """La familia de un producto en SQL (si tiene una categoría, la familia que la contiene)."""
    return Producto.familia_etiquetado_id


def _dict(f: FamiliaEtiquetado, conteos: dict | None = None) -> dict:
    c = (conteos or {}).get(f.id, {})
    return {"id": f.id, "codigo": f.codigo, "nombre": f.nombre, "descripcion": f.descripcion, "campos": f.campos or [],
            "padre_id": f.padre_id, "ruta": " / ".join(x.nombre for x in f.ruta()),
            "heredados": [c for x in f.ruta()[:-1] for c in (x.campos or [])],
            "orden": f.orden, "activa": f.activa, "articulos": c.get("articulos", 0), "usos": c.get("usos", 0),
            "productos": c.get("productos", 0)}


def _conteos(db: Session) -> dict:
    res: dict[int, dict] = {}
    # La familia es una subconsulta (sale del grupo de producto): se calcula por fila en una subconsulta
    # y se agrupa por su resultado (PostgreSQL no agrupa por una subconsulta correlacionada)
    arts = select(familia_sql().label("fid")).select_from(Articulo).where(Articulo.activo.is_(True)).subquery()
    prods = select(Producto.familia_etiquetado_id.label("fid")).select_from(Producto).subquery()
    for clave, sub in (("articulos", arts), ("productos", prods)):
        for fid, n in db.execute(select(sub.c.fid, func.count()).where(sub.c.fid.is_not(None)).group_by(sub.c.fid)):
            res.setdefault(fid, {})[clave] = n
    for fid, n in db.execute(select(UsoDiseno.grupo_id, func.count()).where(UsoDiseno.nivel == "FAMILIA",
                                                                           UsoDiseno.eliminado_en.is_(None))
                             .group_by(UsoDiseno.grupo_id)):
        res.setdefault(fid, {})["usos"] = n
    return res


def listar(db: Session, user: Usuario, activas: bool | None = None) -> list[dict]:
    exigir_interno(user, "etiquetas.ver", "etiquetas.familias")
    c = select(FamiliaEtiquetado).order_by(FamiliaEtiquetado.orden, FamiliaEtiquetado.nombre)
    if activas is not None:
        c = c.where(FamiliaEtiquetado.activa.is_(activas))
    conteos = _conteos(db)
    return [_dict(f, conteos) for f in db.scalars(c)]


def cargar(db: Session, familia_id: int) -> FamiliaEtiquetado:
    f = db.get(FamiliaEtiquetado, familia_id)
    if not f:
        raise ErrorNegocio("The labeling family does not exist.", 404, "no_encontrado")
    return f


def _campos(db: Session, campos) -> list[dict]:
    """[{campo, obligatorio}] con campos del artículo o del producto que existan."""
    if campos is None:
        return []
    if not isinstance(campos, list) or len(campos) > MAX_CAMPOS:
        raise ErrorNegocio(f"At most {MAX_CAMPOS} fields per family.", 422, "validacion")
    validos = {c.clave for c in svc_campos.catalogo(db, "ARTICULO") if c.grupo in ("articulo", "producto")}
    limpio, vistos = [], set()
    for x in campos:
        clave = (x or {}).get("campo") if isinstance(x, dict) else None
        if clave not in validos:
            raise ErrorNegocio(f"Unknown item field: {clave}.", 422, "validacion",
                               [{"campo": "campos", "mensaje": f"Unknown item field: {clave}."}])
        if clave in vistos:
            continue
        vistos.add(clave)
        limpio.append({"campo": clave, "obligatorio": bool(x.get("obligatorio"))})
    return limpio


def _validar(db: Session, datos: dict, actual: FamiliaEtiquetado | None) -> dict:
    errores, limpio = [], {}
    if "codigo" in datos or actual is None:
        codigo = (datos.get("codigo") or "").strip().upper()
        if not codigo or len(codigo) > 20 or not all(ch.isalnum() or ch in "-_." for ch in codigo):
            errores.append({"campo": "codigo", "mensaje": "Enter a code of up to 20 letters, digits, - _ or ."})
        else:
            if arbol.codigo_ocupado(db, codigo, actual.id if actual else None):
                errores.append({"campo": "codigo", "mensaje": "Another family or category has this code."})
            limpio["codigo"] = codigo
    if "nombre" in datos or actual is None:
        nombre = (datos.get("nombre") or "").strip()
        if not nombre or len(nombre) > 100:
            errores.append({"campo": "nombre", "mensaje": "Enter the name (up to 100 characters)."})
        limpio["nombre"] = nombre
    if "descripcion" in datos:
        limpio["descripcion"] = ((datos.get("descripcion") or "").strip() or None)
        if limpio["descripcion"] and len(limpio["descripcion"]) > 300:
            errores.append({"campo": "descripcion", "mensaje": "At most 300 characters."})
    if "orden" in datos:
        if not isinstance(datos["orden"], int) or isinstance(datos["orden"], bool) or datos["orden"] < 0:
            errores.append({"campo": "orden", "mensaje": "Enter a whole number, 0 or more."})
        limpio["orden"] = datos["orden"]
    if "activa" in datos:
        limpio["activa"] = bool(datos["activa"])
    if "campos" in datos:
        limpio["campos"] = _campos(db, datos["campos"])
    if "padre_id" in datos:
        padre_id = datos.get("padre_id") or None
        if padre_id is not None:
            padre = db.get(FamiliaEtiquetado, padre_id)
            if padre is None:
                errores.append({"campo": "padre_id", "mensaje": "The parent family does not exist."})
            elif actual is not None and actual in padre.ruta():
                errores.append({"campo": "padre_id", "mensaje": "A family cannot be inside itself or one of its subfamilies."})
        limpio["padre_id"] = padre_id
    if errores:
        raise ErrorNegocio("Check the labeling family.", 422, "validacion", errores)
    return limpio


def crear(db: Session, user: Usuario, datos: dict) -> dict:
    exigir(user, "etiquetas.familias")
    limpio = _validar(db, datos, None)
    if "orden" not in limpio:
        limpio["orden"] = (db.scalar(select(func.max(FamiliaEtiquetado.orden))) or 0) + 10
    f = FamiliaEtiquetado(**{"activa": True, "campos": [], **limpio})
    db.add(f)
    db.flush()
    registrar(db, user, "familia_etiquetado", f.id, "crear", {"codigo": f.codigo})
    return _dict(f, _conteos(db))


def actualizar(db: Session, user: Usuario, familia_id: int, datos: dict) -> dict:
    exigir(user, "etiquetas.familias")
    f = cargar(db, familia_id)
    limpio = _validar(db, datos, f)
    antes = _dict(f)
    for k, v in limpio.items():
        setattr(f, k, v)
    db.flush()
    cambios = {k: [antes[k], v] for k, v in _dict(f).items() if k in limpio and antes.get(k) != v}
    if cambios:
        registrar(db, user, "familia_etiquetado", f.id, "editar", cambios)
    return _dict(f, _conteos(db))


def ordenar(db: Session, user: Usuario, ids: list[int]) -> list[dict]:
    """El orden en que se listan (el de la lista recibida)."""
    exigir(user, "etiquetas.familias")
    familias = {f.id: f for f in db.scalars(select(FamiliaEtiquetado))}
    if set(ids) != set(familias):
        raise ErrorNegocio("Send every labeling family once.", 422, "validacion")
    for i, fid in enumerate(ids, start=1):
        familias[fid].orden = i * 10
    db.flush()
    registrar(db, user, "familia_etiquetado", 0, "ordenar", {"orden": ids})
    return listar(db, user)


def eliminar(db: Session, user: Usuario, familia_id: int) -> dict:
    """Solo una familia sin uso; si se usa, se desactiva."""
    exigir(user, "etiquetas.familias")
    f = cargar(db, familia_id)
    if arbol.en_uso(db, f):
        raise ErrorNegocio("The family has items, products, designs or subfamilies: deactivate it instead.", 409, "en_uso")
    registrar(db, user, "familia_etiquetado", f.id, "eliminar", {"codigo": f.codigo})
    db.delete(f)
    db.flush()
    return {"ok": True}


# ---- Familia de cada artículo (la de su producto) ------------------------------------------
def _consulta_articulos(user: Usuario, q=None, familia=None, producto_id=None):
    from app.modulos.acceso.permisos import proveedor_filtro

    c = select(Articulo).where(Articulo.activo.is_(True))
    prov = proveedor_filtro(user)
    if prov is not None:
        c = c.where(Articulo.producto_id.in_(select(Producto.id).where(Producto.proveedor_id.in_(prov))))
    if familia == "sin":
        c = c.where(familia_sql().is_(None))
    elif familia:
        c = c.where(familia_sql() == int(familia))
    if producto_id:
        c = c.where(Articulo.producto_id == producto_id)
    if q and q.strip():
        c = c.where(filtro_texto(q, lambda p: [
            Articulo.sku.ilike(p), Articulo.descripcion.ilike(p),
            Articulo.id.in_(select(ArticuloCodigo.articulo_id).where(ArticuloCodigo.valor.ilike(p))),
            Articulo.producto_id.in_(select(Producto.id).where(Producto.nombre.ilike(p) | Producto.codigo_generico.ilike(p)))]))
    return c


def articulos(db: Session, user: Usuario, q=None, familia=None, producto_id=None,
              page: int = 1, size: int = 50, ids: list[int] | None = None, solo_ids: bool = False) -> dict:
    from app.modulos.maestros import variantes

    exigir_alguno(user, "etiquetas.ver", "etiquetas.familias")
    c = _consulta_articulos(user, q, familia, producto_id)
    if ids:
        c = c.where(Articulo.id.in_(ids))
    if solo_ids:
        return {"ids": list(db.scalars(c.with_only_columns(Articulo.id).order_by(Articulo.id).limit(5000)))}
    total = db.scalar(select(func.count()).select_from(c.subquery())) or 0
    filas = db.scalars(c.order_by(Articulo.sku, Articulo.id).offset((page - 1) * size).limit(size)).all()
    marcas = {m.codigo: m.nombre for m in db.scalars(select(Marca))}

    def fila(a: Articulo) -> dict:
        p = a.producto
        fam = p.grupo_producto.familia if p is not None and p.grupo_producto is not None else None
        return {"id": a.id, "sku": a.sku, "variante": variantes.texto(variantes.de_articulo(db, a)) or None,
                "descripcion": a.descripcion, "producto": p.nombre if p else None, "generico": a.generico,
                "marca": marcas.get(p.marca_codigo) if p else None, "producto_id": a.producto_id,
                "familia_id": fam.id if fam else None, "familia": fam.nombre if fam else None,
                "familia_origen": "PRODUCTO" if fam else None}
    return {"total": total, "items": [fila(a) for a in filas]}


def asignar_articulos(db: Session, user: Usuario, familia_id: int | None, ids: list[int] | None = None,
                      filtro: dict | None = None) -> dict:
    """La familia es del producto: pone (o quita, con familia vacía) la familia de los productos
    de los artículos elegidos o de todos los que cumplen un filtro de la lista."""
    exigir(user, "etiquetas.familias")
    if familia_id is not None and not cargar(db, familia_id).activa:
        raise ErrorNegocio("The labeling family is inactive.", 422, "validacion")
    if ids:
        c = _consulta_articulos(user).where(Articulo.id.in_(ids))
    elif filtro is not None:
        permitidos = {"q", "familia", "producto_id"}
        c = _consulta_articulos(user, **{k: v for k, v in filtro.items() if k in permitidos})
    else:
        raise ErrorNegocio("Choose the items.", 422, "validacion")
    elegidos = list(db.scalars(c))
    if ids and len(elegidos) != len(set(ids)):
        raise ErrorNegocio("Some items do not exist or are out of your scope.", 404, "no_encontrado")
    productos_ = {a.producto_id for a in elegidos}
    r = asignar_productos(db, user, familia_id, sorted(productos_)) if productos_ else {"cambiados": 0}
    return {"cambiados": r["cambiados"], "elegidos": len(elegidos), "productos": len(productos_)}


def obligatorios(familia: FamiliaEtiquetado | None) -> list[str]:
    """Campos obligatorios de la familia y de las familias que la contienen."""
    res = []
    for f in familia.ruta() if familia else []:
        res += [c["campo"] for c in f.campos or [] if c.get("obligatorio") and c["campo"] not in res]
    return res


def faltantes(db: Session, familia: FamiliaEtiquetado | None, valores: dict) -> list[str]:
    """Campos obligatorios de la familia (incluidos los heredados) que el artículo no tiene."""
    return [c for c in obligatorios(familia) if valores.get(c) in (None, "")]



# ---- Familia de cada producto (estilo-color) ----------------------------------------------------
def productos(db: Session, user: Usuario, q: str | None = None, familia: str | None = None, page: int = 1,
              size: int = 50) -> dict:
    """Productos con su familia y cuántas variantes tienen."""
    from app.modulos.acceso.permisos import proveedor_filtro

    exigir_alguno(user, "etiquetas.ver", "etiquetas.familias")
    c = select(Producto)
    prov = proveedor_filtro(user)
    if prov is not None:
        c = c.where(Producto.proveedor_id.in_(prov))
    if familia == "sin":
        c = c.where(familia_producto_sql().is_(None))
    elif familia:
        c = c.where(familia_producto_sql() == int(familia))
    if q and q.strip():
        c = c.where(filtro_texto(q, lambda p: [
            Producto.nombre.ilike(p), Producto.codigo_generico.ilike(p),
            Producto.id.in_(select(ProductoAtributo.producto_id).where(ProductoAtributo.valor.ilike(p)))]))
    total = db.scalar(select(func.count()).select_from(c.subquery())) or 0
    filas = db.scalars(c.order_by(Producto.codigo_generico, Producto.id).offset((page - 1) * size).limit(size)).all()
    tallas = dict(db.execute(select(Articulo.producto_id, func.count()).where(
        Articulo.producto_id.in_([p.id for p in filas]), Articulo.activo.is_(True)).group_by(Articulo.producto_id)).all()) if filas else {}
    familias_ = {f.id: f.nombre for f in db.scalars(select(FamiliaEtiquetado))}
    # La categoría de etiquetado de sus tallas: la puesta a mano o la que reconocen las condiciones
    from app.modulos.etiquetado import campos, reglas

    cats_de: dict = {}
    cache: dict = {}
    for a in db.scalars(select(Articulo).where(Articulo.producto_id.in_([p.id for p in filas]), Articulo.activo.is_(True))
                        .order_by(Articulo.id)) if filas else []:
        cats_de.setdefault(a.producto_id, []).append(reglas.categoria_de(db, a, campos.valores_articulo(a), cache))
    res = []
    for p in filas:
        distintas = {c.id: c for c in cats_de.get(p.id, []) if c is not None}
        cat = next(iter(distintas.values())) if len(distintas) == 1 else None
        parcial = len(distintas) > 1 or (cat is not None and None in cats_de.get(p.id, []))
        efectiva = p.familia_etiquetado_id
        res.append({"id": p.id, "nombre": p.nombre, "codigo_generico": p.codigo_generico, "atributos": p.valores,
                    "variantes": tallas.get(p.id, 0),
                    "familia_propia_id": efectiva, "familia_id": efectiva, "familia": familias_.get(efectiva),
                    "familia_origen": "PRODUCTO" if efectiva else None,
                    "categoria_id": cat.id if cat else None, "categoria": cat.nombre if cat else None,
                    "categoria_propia_id": p.categoria_etiquetado_id,
                    "categoria_origen": ("MANUAL" if cat and cat.id == p.categoria_etiquetado_id else "CONDICIONES") if cat else None,
                    "categoria_parcial": parcial, "categorias": [c.nombre for c in distintas.values()]})
    return {"total": total, "items": res}


def asignar_productos(db: Session, user: Usuario, familia_id: int | None, ids: list[int]) -> dict:
    """Pone (o quita, con familia vacía) la familia de varios productos: la comparten sus variantes."""
    from app.modulos.acceso.permisos import proveedor_filtro

    exigir(user, "etiquetas.familias")
    if not ids:
        raise ErrorNegocio("Choose the products.", 422, "validacion")
    if familia_id is not None and not cargar(db, familia_id).activa:
        raise ErrorNegocio("The labeling family is inactive.", 422, "validacion")
    c = select(Producto).where(Producto.id.in_(set(ids)))
    prov = proveedor_filtro(user)
    if prov is not None:
        c = c.where(Producto.proveedor_id.in_(prov))
    elegidos = list(db.scalars(c))
    if len(elegidos) != len(set(ids)):
        raise ErrorNegocio("Some products do not exist or are out of your scope.", 404, "no_encontrado")
    cambiados = [p for p in elegidos if p.familia_etiquetado_id != familia_id]
    for p in cambiados:
        p.familia_etiquetado_id = familia_id
    db.flush()
    if cambiados:
        registrar(db, user, "familia_etiquetado", familia_id or 0, "asignar_productos",
                  {"familia_id": familia_id, "productos": [p.codigo_generico or p.nombre for p in cambiados[:50]]})
    return {"cambiados": len(cambiados), "elegidos": len(elegidos)}


def configurar(db: Session, user: Usuario, datos: dict) -> dict:
    """Termina el asistente de una familia en una sola operación (todo o nada):
    sus datos (`familia`, con `id` si ya existe), lo que entra en ella
    (`productos`, `articulos`: ids; un artículo lleva a su producto) y su diseño normal por tipo de
    etiqueta (`disenos`: [{tipo_etiqueta_id, plantilla_id}], plantilla_id
    vacío = hereda). Mientras el asistente está a medias nada de esto cambia."""
    from app.modulos.etiquetado import usos as svc_usos

    exigir(user, "etiquetas.familias")
    fam = datos.get("familia") or {}
    if not isinstance(fam, dict):
        raise ErrorNegocio("Check the labeling family.", 422, "validacion")
    cuerpo = {k: fam[k] for k in ("codigo", "nombre", "padre_id", "descripcion", "activa", "campos") if k in fam}
    r = actualizar(db, user, int(fam["id"]), cuerpo) if fam.get("id") else crear(db, user, cuerpo)
    fid = r["id"]
    hecho = {"productos": 0, "articulos": 0, "disenos": 0}
    listas = {k: [int(x) for x in (datos.get(k) or [])] for k in ("productos", "articulos")}
    if any(listas.values()) and not cargar(db, fid).activa:
        raise ErrorNegocio("The labeling family is inactive.", 422, "validacion")
    if listas["productos"]:
        hecho["productos"] = asignar_productos(db, user, fid, listas["productos"])["cambiados"]
    if listas["articulos"]:
        hecho["articulos"] = asignar_articulos(db, user, fid, listas["articulos"])["cambiados"]
    disenos = datos.get("disenos") or []
    if disenos:
        exigir(user, "etiquetas.configurar")
    for d in disenos:
        tipo_id = int((d or {}).get("tipo_etiqueta_id") or 0)
        antes = next((u for u in svc_usos._usos_celda(db, svc_usos.celda_de(tipo_id, "FAMILIA", fid))
                      if u.contexto_tipo == "NINGUNO"), None)
        nuevo = d.get("plantilla_id") or None
        if (antes.plantilla_id if antes else None) == nuevo:
            continue
        svc_usos.guardar_celda(db, user, {"tipo_etiqueta_id": tipo_id, "nivel": "FAMILIA", "destino_id": fid,
                                          "normal": {"plantilla_id": nuevo} if nuevo else None,
                                          "motivo_cambio": "Family set up step by step"})
        hecho["disenos"] += 1
    return {"familia": _dict(cargar(db, fid), _conteos(db)), "hecho": hecho}
