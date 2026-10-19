"""Familias de etiquetado: las define cada empresa (código, nombre,
descripción, orden, activa) junto con los campos habituales de la familia y
cuáles son obligatorios. Son independientes de la clasificación arancelaria.

Una familia en uso (artículos, productos, grupos, usos de diseño o
subfamilias) no se borra: se desactiva. La familia se asigna al producto
(estilo-color: la heredan todas sus tallas), al grupo de artículos o a un SKU
concreto; la de un artículo es la suya, si no la de su producto y si no la de
su grupo.
"""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errores import ErrorNegocio
from app.modelos import (
    Articulo,
    FamiliaEtiquetado,
    GrupoArticulo,
    Marca,
    Producto,
    UsoDiseno,
    Usuario,
)
from app.modulos.acceso.permisos import exigir, exigir_alguno
from app.modulos.comun.historial import registrar
from app.modulos.comun.texto import filtro_texto
from app.modulos.etiquetado import campos as svc_campos

MAX_CAMPOS = 60


def familia_sql():
    """La familia efectiva de un artículo en SQL: la suya, la de su producto o la de su grupo."""
    del_producto = select(Producto.familia_etiquetado_id).where(Producto.id == Articulo.producto_id).scalar_subquery()
    del_grupo = select(GrupoArticulo.familia_etiquetado_id).where(GrupoArticulo.id == Articulo.grupo_id).scalar_subquery()
    return func.coalesce(Articulo.familia_etiquetado_id, del_producto, del_grupo)


def familia_producto_sql():
    """La familia efectiva de un producto en SQL: la suya o la de su grupo."""
    del_grupo = select(GrupoArticulo.familia_etiquetado_id).where(GrupoArticulo.id == Producto.grupo_id).scalar_subquery()
    return func.coalesce(Producto.familia_etiquetado_id, del_grupo)


def _dict(f: FamiliaEtiquetado, conteos: dict | None = None) -> dict:
    c = (conteos or {}).get(f.id, {})
    return {"id": f.id, "codigo": f.codigo, "nombre": f.nombre, "descripcion": f.descripcion, "campos": f.campos or [],
            "padre_id": f.padre_id, "ruta": " / ".join(x.nombre for x in f.ruta()),
            "heredados": [c for x in f.ruta()[:-1] for c in (x.campos or [])],
            "orden": f.orden, "activa": f.activa, "articulos": c.get("articulos", 0), "usos": c.get("usos", 0),
            "grupos": c.get("grupos", 0), "productos": c.get("productos", 0), "articulos_propios": c.get("propios", 0)}


def _conteos(db: Session) -> dict:
    res: dict[int, dict] = {}
    fam = familia_sql()
    for fid, n in db.execute(select(fam, func.count()).where(Articulo.activo.is_(True), fam.is_not(None)).group_by(fam)):
        res.setdefault(fid, {})["articulos"] = n
    for fid, n in db.execute(select(Articulo.familia_etiquetado_id, func.count()).where(Articulo.activo.is_(True),
                                                                                       Articulo.familia_etiquetado_id.is_not(None))
                             .group_by(Articulo.familia_etiquetado_id)):
        res.setdefault(fid, {})["propios"] = n
    for fid, n in db.execute(select(GrupoArticulo.familia_etiquetado_id, func.count())
                             .where(GrupoArticulo.familia_etiquetado_id.is_not(None)).group_by(GrupoArticulo.familia_etiquetado_id)):
        res.setdefault(fid, {})["grupos"] = n
    for fid, n in db.execute(select(Producto.familia_etiquetado_id, func.count())
                             .where(Producto.familia_etiquetado_id.is_not(None)).group_by(Producto.familia_etiquetado_id)):
        res.setdefault(fid, {})["productos"] = n
    for fid, n in db.execute(select(UsoDiseno.familia_id, func.count()).where(UsoDiseno.familia_id.is_not(None),
                                                                             UsoDiseno.eliminado_en.is_(None))
                             .group_by(UsoDiseno.familia_id)):
        res.setdefault(fid, {})["usos"] = n
    return res


def listar(db: Session, user: Usuario, activas: bool | None = None) -> list[dict]:
    exigir_alguno(user, "etiquetas.ver", "etiquetas.familias")
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
            otra = db.scalar(select(FamiliaEtiquetado.id).where(FamiliaEtiquetado.codigo == codigo))
            if otra and (actual is None or otra != actual.id):
                errores.append({"campo": "codigo", "mensaje": "Another labeling family has this code."})
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
    en_uso = (db.scalar(select(func.count()).select_from(Articulo).where(Articulo.familia_etiquetado_id == f.id))
              or db.scalar(select(func.count()).select_from(GrupoArticulo).where(GrupoArticulo.familia_etiquetado_id == f.id))
              or db.scalar(select(func.count()).select_from(Producto).where(Producto.familia_etiquetado_id == f.id))
              or db.scalar(select(func.count()).select_from(UsoDiseno).where(UsoDiseno.familia_id == f.id))
              or db.scalar(select(func.count()).select_from(FamiliaEtiquetado).where(FamiliaEtiquetado.padre_id == f.id)))
    if en_uso:
        raise ErrorNegocio("The family has items, products, designs or subfamilies: deactivate it instead.", 409, "en_uso")
    registrar(db, user, "familia_etiquetado", f.id, "eliminar", {"codigo": f.codigo})
    db.delete(f)
    db.flush()
    return {"ok": True}


# ---- Familia de cada artículo -----------------------------------------------------------------
def _consulta_articulos(user: Usuario, q=None, familia=None, marca_id=None, grupo_id=None, producto_id=None):
    from app.modulos.acceso.permisos import proveedor_filtro

    c = select(Articulo).where(Articulo.activo.is_(True))
    prov = proveedor_filtro(user)
    if prov is not None:
        c = c.where(Articulo.proveedor_id.in_(prov))
    if familia == "sin":
        c = c.where(familia_sql().is_(None))
    elif familia:
        c = c.where(familia_sql() == int(familia))
    if marca_id:
        c = c.where(Articulo.marca_id == marca_id)
    if grupo_id:
        c = c.where(Articulo.grupo_id == grupo_id)
    if producto_id:
        c = c.where(Articulo.producto_id == producto_id)
    if q and q.strip():
        c = c.where(filtro_texto(q, lambda p: [x.ilike(p) for x in (Articulo.sku, Articulo.estilo, Articulo.descripcion,
                                                                       Articulo.color, Articulo.upc)]))
    return c


def articulos(db: Session, user: Usuario, q=None, familia=None, marca_id=None, grupo_id=None, producto_id=None,
              page: int = 1, size: int = 50, ids: list[int] | None = None, solo_ids: bool = False) -> dict:
    exigir_alguno(user, "etiquetas.ver", "etiquetas.familias")
    c = _consulta_articulos(user, q, familia, marca_id, grupo_id, producto_id)
    if ids:
        c = c.where(Articulo.id.in_(ids))
    if solo_ids:
        return {"ids": list(db.scalars(c.with_only_columns(Articulo.id).order_by(Articulo.id).limit(5000)))}
    total = db.scalar(select(func.count()).select_from(c.subquery())) or 0
    filas = db.scalars(c.order_by(Articulo.estilo, Articulo.color, Articulo.talla, Articulo.id)
                       .offset((page - 1) * size).limit(size)).all()
    nombres = {m.id: m.nombre for m in db.scalars(select(Marca))}
    grupos = {g.id: g for g in db.scalars(select(GrupoArticulo))}
    familias = {f.id: f for f in db.scalars(select(FamiliaEtiquetado))}
    de_producto = dict(db.execute(select(Producto.id, Producto.familia_etiquetado_id).where(
        Producto.id.in_({a.producto_id for a in filas if a.producto_id}))).all()) if filas else {}

    def fila(a: Articulo) -> dict:
        g = grupos.get(a.grupo_id)
        fp = de_producto.get(a.producto_id)
        fg = g.familia_etiquetado_id if g else None
        efectiva = a.familia_etiquetado_id or fp or fg
        origen = "ARTICULO" if a.familia_etiquetado_id else ("PRODUCTO" if fp else ("GRUPO" if fg else None))
        return {"id": a.id, "sku": a.sku, "estilo": a.estilo, "color": a.color, "talla": a.talla, "descripcion": a.descripcion,
                "marca": nombres.get(a.marca_id), "grupo_id": a.grupo_id, "grupo": g.nombre if g else None,
                "producto_id": a.producto_id, "familia_propia_id": a.familia_etiquetado_id,
                "familia_id": efectiva, "familia": familias[efectiva].nombre if efectiva in familias else None,
                "familia_origen": origen}
    return {"total": total, "items": [fila(a) for a in filas]}


def asignar_articulos(db: Session, user: Usuario, familia_id: int | None, ids: list[int] | None = None,
                      filtro: dict | None = None) -> dict:
    """Pone (o quita, con familia vacía) la familia de los artículos elegidos o
    de todos los que cumplen un filtro de la lista."""
    exigir(user, "etiquetas.familias")
    if familia_id is not None and not cargar(db, familia_id).activa:
        raise ErrorNegocio("The labeling family is inactive.", 422, "validacion")
    if ids:
        c = _consulta_articulos(user).where(Articulo.id.in_(ids))
    elif filtro is not None:
        permitidos = {"q", "familia", "marca_id", "grupo_id", "producto_id"}
        c = _consulta_articulos(user, **{k: v for k, v in filtro.items() if k in permitidos})
    else:
        raise ErrorNegocio("Choose the items.", 422, "validacion")
    elegidos = list(db.scalars(c))
    if ids and len(elegidos) != len(set(ids)):
        raise ErrorNegocio("Some items do not exist or are out of your scope.", 404, "no_encontrado")
    cambiados = [a for a in elegidos if a.familia_etiquetado_id != familia_id]
    for a in cambiados:
        a.familia_etiquetado_id = familia_id
    db.flush()
    if cambiados:
        registrar(db, user, "familia_etiquetado", familia_id or 0, "asignar_articulos",
                  {"familia_id": familia_id, "articulos": len(cambiados),
                   "skus": [a.sku for a in cambiados[:50]]})
    return {"cambiados": len(cambiados), "elegidos": len(elegidos)}


def obligatorios(familia: FamiliaEtiquetado | None) -> list[str]:
    """Campos obligatorios de la familia y de las familias que la contienen."""
    res = []
    for f in familia.ruta() if familia else []:
        res += [c["campo"] for c in f.campos or [] if c.get("obligatorio") and c["campo"] not in res]
    return res


def faltantes(db: Session, familia: FamiliaEtiquetado | None, valores: dict) -> list[str]:
    """Campos obligatorios de la familia (incluidos los heredados) que el artículo no tiene."""
    return [c for c in obligatorios(familia) if valores.get(c) in (None, "")]



# ---- Grupos de artículos de cada familia ----------------------------------------------------
def grupos(db: Session, user: Usuario, q: str | None = None, familia: str | None = None) -> list[dict]:
    """Los grupos de artículos con su familia de etiquetado y cuántos artículos activos tienen."""
    exigir_alguno(user, "etiquetas.ver", "etiquetas.familias")
    c = select(GrupoArticulo).where(GrupoArticulo.activo.is_(True)).order_by(GrupoArticulo.nombre)
    if familia == "sin":
        c = c.where(GrupoArticulo.familia_etiquetado_id.is_(None))
    elif familia:
        c = c.where(GrupoArticulo.familia_etiquetado_id == int(familia))
    if q and q.strip():
        c = c.where(filtro_texto(q, lambda p: [GrupoArticulo.codigo.ilike(p), GrupoArticulo.nombre.ilike(p)]))
    cuentas = dict(db.execute(select(Articulo.grupo_id, func.count()).where(Articulo.activo.is_(True)).group_by(Articulo.grupo_id)).all())
    propios = dict(db.execute(select(Articulo.grupo_id, func.count()).where(Articulo.activo.is_(True),
                                                                           Articulo.familia_etiquetado_id.is_not(None))
                              .group_by(Articulo.grupo_id)).all())
    familias = {f.id: f.nombre for f in db.scalars(select(FamiliaEtiquetado))}
    return [{"id": g.id, "codigo": g.codigo, "nombre": g.nombre, "categoria": g.categoria, "familia_id": g.familia_etiquetado_id,
             "familia": familias.get(g.familia_etiquetado_id), "articulos": cuentas.get(g.id, 0),
             "con_familia_propia": propios.get(g.id, 0)} for g in db.scalars(c)]


def asignar_grupos(db: Session, user: Usuario, familia_id: int | None, grupo_ids: list[int]) -> dict:
    """Pone (o quita, con familia vacía) la familia de varios grupos a la vez.
    Un grupo pertenece a una sola familia: si tenía otra, cambia. Los artículos
    con familia propia la conservan."""
    exigir(user, "etiquetas.familias")
    if not grupo_ids:
        raise ErrorNegocio("Choose the item groups.", 422, "validacion")
    if familia_id is not None and not cargar(db, familia_id).activa:
        raise ErrorNegocio("The labeling family is inactive.", 422, "validacion")
    elegidos = list(db.scalars(select(GrupoArticulo).where(GrupoArticulo.id.in_(set(grupo_ids)))))
    if len(elegidos) != len(set(grupo_ids)):
        raise ErrorNegocio("Some item groups do not exist.", 404, "no_encontrado")
    cambiados = [g for g in elegidos if g.familia_etiquetado_id != familia_id]
    movidos = [g for g in cambiados if g.familia_etiquetado_id is not None and familia_id is not None]
    for g in cambiados:
        g.familia_etiquetado_id = familia_id
    db.flush()
    if cambiados:
        registrar(db, user, "familia_etiquetado", familia_id or 0, "asignar_grupos",
                  {"familia_id": familia_id, "grupos": [g.codigo for g in cambiados[:100]], "movidos": len(movidos)})
    return {"cambiados": len(cambiados), "movidos": len(movidos), "elegidos": len(elegidos)}


def desde_grupos(db: Session, user: Usuario) -> dict:
    """Primer uso: una familia por cada grupo de artículos activo sin familia (mismo código y nombre),
    y el grupo queda en ella. Los grupos que ya tienen familia no cambian."""
    exigir(user, "etiquetas.familias")
    grupos_ = list(db.scalars(select(GrupoArticulo).where(GrupoArticulo.activo.is_(True),
                                                          GrupoArticulo.familia_etiquetado_id.is_(None)).order_by(GrupoArticulo.codigo)))
    existentes = {c for c in db.scalars(select(FamiliaEtiquetado.codigo))}
    orden = db.scalar(select(func.max(FamiliaEtiquetado.orden))) or 0
    creadas = []
    for g in grupos_:
        codigo = "".join(ch for ch in g.codigo.upper() if ch.isalnum() or ch in "-_.")[:20] or f"G{g.id}"
        base, n = codigo, 2
        while codigo in existentes:
            codigo = f"{base[:17]}-{n}"
            n += 1
        orden += 10
        f = FamiliaEtiquetado(codigo=codigo, nombre=g.nombre[:100], orden=orden, activa=True, campos=[])
        db.add(f)
        db.flush()
        g.familia_etiquetado_id = f.id
        existentes.add(codigo)
        creadas.append(f)
    db.flush()
    if creadas:
        registrar(db, user, "familia_etiquetado", 0, "desde_grupos", {"familias": [f.codigo for f in creadas[:200]]})
    return {"creadas": len(creadas), "familias": listar(db, user)}


# ---- Familia de cada producto (estilo-color) ----------------------------------------------------
def productos(db: Session, user: Usuario, q: str | None = None, familia: str | None = None, page: int = 1,
              size: int = 50) -> dict:
    """Productos con su familia de etiquetado (la propia o la de su grupo) y cuántas tallas tienen."""
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
        c = c.where(filtro_texto(q, lambda p: [Producto.estilo.ilike(p), Producto.color.ilike(p), Producto.nombre.ilike(p),
                                               Producto.codigo_generico.ilike(p)]))
    total = db.scalar(select(func.count()).select_from(c.subquery())) or 0
    filas = db.scalars(c.order_by(Producto.estilo, Producto.color, Producto.id).offset((page - 1) * size).limit(size)).all()
    tallas = dict(db.execute(select(Articulo.producto_id, func.count()).where(
        Articulo.producto_id.in_([p.id for p in filas]), Articulo.activo.is_(True)).group_by(Articulo.producto_id)).all()) if filas else {}
    grupos_ = {g.id: g for g in db.scalars(select(GrupoArticulo))}
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
        fg = grupos_[p.grupo_id].familia_etiquetado_id if p.grupo_id in grupos_ else None
        efectiva = p.familia_etiquetado_id or fg
        res.append({"id": p.id, "estilo": p.estilo, "color": p.color, "nombre": p.nombre, "codigo_generico": p.codigo_generico,
                    "grupo": grupos_[p.grupo_id].nombre if p.grupo_id in grupos_ else None, "tallas": tallas.get(p.id, 0),
                    "familia_propia_id": p.familia_etiquetado_id, "familia_id": efectiva, "familia": familias_.get(efectiva),
                    "familia_origen": "PRODUCTO" if p.familia_etiquetado_id else ("GRUPO" if fg else None),
                    "categoria_id": cat.id if cat else None, "categoria": cat.nombre if cat else None,
                    "categoria_propia_id": p.categoria_etiquetado_id,
                    "categoria_origen": ("MANUAL" if cat and cat.id == p.categoria_etiquetado_id else "CONDICIONES") if cat else None,
                    "categoria_parcial": parcial, "categorias": [c.nombre for c in distintas.values()]})
    return {"total": total, "items": res}


def asignar_productos(db: Session, user: Usuario, familia_id: int | None, ids: list[int]) -> dict:
    """Pone (o quita, con familia vacía) la familia de varios productos: la heredan
    sus tallas que no tienen una propia."""
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
                  {"familia_id": familia_id, "productos": [f"{p.estilo} {p.color or ''}".strip() for p in cambiados[:50]]})
    return {"cambiados": len(cambiados), "elegidos": len(elegidos)}


def configurar(db: Session, user: Usuario, datos: dict) -> dict:
    """Termina el asistente de una familia en una sola operación (todo o nada):
    sus datos (`familia`, con `id` si ya existe), lo que entra en ella
    (`productos`, `grupos`, `articulos`: ids) y su diseño normal por tipo de
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
    hecho = {"productos": 0, "grupos": 0, "articulos": 0, "disenos": 0}
    listas = {k: [int(x) for x in (datos.get(k) or [])] for k in ("productos", "grupos", "articulos")}
    if any(listas.values()) and not cargar(db, fid).activa:
        raise ErrorNegocio("The labeling family is inactive.", 422, "validacion")
    if listas["productos"]:
        hecho["productos"] = asignar_productos(db, user, fid, listas["productos"])["cambiados"]
    if listas["grupos"]:
        hecho["grupos"] = asignar_grupos(db, user, fid, listas["grupos"])["cambiados"]
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
