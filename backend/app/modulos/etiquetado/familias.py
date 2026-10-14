"""Familias de etiquetado: las define cada empresa (código, nombre,
descripción, orden, activa) junto con los campos habituales de la familia y
cuáles son obligatorios. Son independientes de la clasificación arancelaria.

Una familia en uso (artículos, plantillas o asignaciones) no se borra: se
desactiva. La familia de cada artículo se asigna aquí, de uno en uno o en
bloque, sin una segunda ficha de producto.
"""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errores import ErrorNegocio
from app.modelos import (
    Articulo,
    AsignacionEtiqueta,
    FamiliaEtiquetado,
    GrupoArticulo,
    Marca,
    PlantillaEtiqueta,
    Usuario,
)
from app.modulos.acceso.permisos import exigir, exigir_alguno
from app.modulos.comun.historial import registrar
from app.modulos.comun.texto import filtro_texto
from app.modulos.etiquetado import campos as svc_campos

MAX_CAMPOS = 60


def familia_sql():
    """La familia efectiva de un artículo en SQL: la suya propia o la de su grupo."""
    del_grupo = select(GrupoArticulo.familia_etiquetado_id).where(GrupoArticulo.id == Articulo.grupo_id).scalar_subquery()
    return func.coalesce(Articulo.familia_etiquetado_id, del_grupo)


def _dict(f: FamiliaEtiquetado, conteos: dict | None = None) -> dict:
    c = (conteos or {}).get(f.id, {})
    return {"id": f.id, "codigo": f.codigo, "nombre": f.nombre, "descripcion": f.descripcion, "campos": f.campos or [],
            "orden": f.orden, "activa": f.activa, "articulos": c.get("articulos", 0), "plantillas": c.get("plantillas", 0),
            "grupos": c.get("grupos", 0), "articulos_propios": c.get("propios", 0)}


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
    for fid, n in db.execute(select(PlantillaEtiqueta.familia_id, func.count()).where(PlantillaEtiqueta.familia_id.is_not(None))
                             .group_by(PlantillaEtiqueta.familia_id)):
        res.setdefault(fid, {})["plantillas"] = n
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
              or db.scalar(select(func.count()).select_from(PlantillaEtiqueta).where(PlantillaEtiqueta.familia_id == f.id))
              or db.scalar(select(func.count()).select_from(AsignacionEtiqueta).where(AsignacionEtiqueta.familia_id == f.id)))
    if en_uso:
        raise ErrorNegocio("The family has items, designs or assignments: deactivate it instead.", 409, "en_uso")
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

    def fila(a: Articulo) -> dict:
        g = grupos.get(a.grupo_id)
        efectiva = a.familia_etiquetado_id or (g.familia_etiquetado_id if g else None)
        return {"id": a.id, "sku": a.sku, "estilo": a.estilo, "color": a.color, "talla": a.talla, "descripcion": a.descripcion,
                "marca": nombres.get(a.marca_id), "grupo_id": a.grupo_id, "grupo": g.nombre if g else None,
                "producto_id": a.producto_id, "familia_propia_id": a.familia_etiquetado_id,
                "familia_id": efectiva, "familia": familias[efectiva].nombre if efectiva in familias else None,
                "familia_origen": "ARTICULO" if a.familia_etiquetado_id else ("GRUPO" if efectiva else None)}
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


def faltantes(db: Session, familia: FamiliaEtiquetado | None, valores: dict) -> list[str]:
    """Campos obligatorios de la familia que el artículo no tiene."""
    if not familia:
        return []
    return [c["campo"] for c in familia.campos or [] if c.get("obligatorio") and valores.get(c["campo"]) in (None, "")]



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
