"""Lectura de productos: la lista con sus filtros, columnas y vistas por estado, el
detalle de una ficha y el contexto que la pantalla necesita para llenarla.
"""
from sqlalchemy import func, select
from sqlalchemy.orm import Session, object_session, selectinload

from app.core.empresa import regla
from app.core.errores import ErrorNegocio
from app.modelos import (
    Articulo,
    ArticuloCodigo,
    ClasificacionProducto,
    ControlCapitulo,
    GrupoProducto,
    Historial,
    Marca,
    Producto,
    ProductoAtributo,
    ProductoComex,
    Proveedor,
    Usuario,
)
from app.modulos.acceso.permisos import asegurar_proveedor, exigir, proveedor_filtro, tiene
from app.modulos.clasificacion.categorias import categorias as categorias_config
from app.modulos.clasificacion.indice_arbol import dominios_ficha
from app.modulos.comex import flujo
from app.modulos.comex.servicio import (  # noqa: F401
    APROBADOS,
    BORRADORES,
    ESTADOS,
    PENDIENTES,
    digitos,
    fmt_codigo,
    sin_marca,
)
from app.modulos.comun import tabla
from app.modulos.comun.edicion import ajeno as ajeno_edicion
from app.modulos.comun.texto import filtro_texto
from app.modulos.maestros import variantes as var_svc
from app.modulos.maestros.acuerdos import acuerdos_contexto
from app.modulos.productos.productos import _doc_dict, destinos, ids_bloquean_facturas, marca_de, notas_contexto


# ---- Lectura -------------------------------------------------------------------
def ver_producto(db: Session, user: Usuario, producto_id: int) -> Producto:
    exigir(user, "producto.ver")
    p = db.get(Producto, producto_id)
    if not p:
        raise ErrorNegocio("The product does not exist.", 404, "no_encontrado")
    asegurar_proveedor(user, p.proveedor_id)
    return p


def _paises_completos(p: Producto, ds: list[dict]) -> tuple[int, int]:
    dig = {d["iso"]: d["digitos"] for d in ds}
    ok = sum(1 for x in p.partidas if x.pais in dig and x.estado in ("ok", "auto") and len(digitos(x.codigo)) >= dig[x.pais])
    return ok, len(ds)


def _resumen(p: Producto, variantes: dict, ds: list[dict], marcas: dict | None = None) -> dict:
    ok, total = _paises_completos(p, ds)
    foto = p.fotos[0].id if p.fotos else None
    t = variantes.get(p.id, {})
    marca = p.marca_codigo
    return {
        "id": p.id, "nombre": p.nombre, "codigo_generico": p.codigo_generico,
        "proveedor_id": p.proveedor_id, "proveedor": p.proveedor.nombre if p.proveedor else None,
        # Atributos del producto (marca, modelo, material…): {código: valor}
        "atributos": var_svc.ordenar_producto(object_session(p), p.valores),
        "marca": marca, "marca_nombre": (marcas or {}).get(marca) if marcas is not None else (
            m.nombre if (m := marca_de(p)) else None),
        "familia_id": p.grupo_producto_id, "familia": p.grupo_producto.nombre if p.grupo_producto else None,
        "tipo": p.comex.tipo, "estado": p.comex.estado,
        "estado_txt": ESTADOS.get(p.comex.estado, p.comex.estado),
        "codigo": fmt_codigo(p.comex.codigo) if p.comex.codigo else None, "sugerido": fmt_codigo(p.comex.sugerido) if p.comex.sugerido else None,
        "sac_codigo": fmt_codigo(p.comex.sac_codigo) if p.comex.sac_codigo else None, "sac_sugerido": fmt_codigo(p.comex.sac_sugerido) if p.comex.sac_sugerido else None,
        "propuesta": fmt_codigo(p.comex.propuesta) if p.comex.propuesta else None,
        "confianza": p.comex.confianza, "ficha_completa": p.comex.ficha_completa, "faltan": p.comex.faltan or [],
        "paises_ok": ok, "paises_total": total, "foto_id": foto, "pais_origen": p.comex.pais_origen,
        "skus": t.get("skus", 0),
        # Las variantes por atributo de la familia («Size 7–12 · Color BLACK, WHITE»), para cualquier producto
        "resumen_variantes": var_svc.resumen(object_session(p), t.get("articulos", [])),
        # Lo mismo por atributo ([{codigo, nombre, valores, texto}]), para mostrarlo como datos
        "variantes_atributos": var_svc.por_atributo(object_session(p), t.get("articulos", [])),
        "n_compuestos": t.get("compuestos", 0),
        "unidad": t.get("unidad"), "descripcion_comercial": p.comex.descripcion_comercial,
        "actualizado_en": p.actualizado_en, "version": p.version, "version_ficha": p.comex.version_ficha,
    }


def _atributos_txt(db: Session, p: Producto) -> list[dict]:
    """[{codigo, nombre, valor}] de los atributos del producto, en su orden."""
    nombres = var_svc.nombres(db)
    marca = marca_de(p)
    cat = {a.codigo: a.catalogo for a in var_svc.atributos(db, "PRODUCTO")}
    return [{"codigo": k, "nombre": nombres.get(k, k),
             "valor": marca.nombre if cat.get(k) == "marcas" and marca and marca.codigo == v else v}
            for k, v in var_svc.ordenar_producto(db, p.valores).items()]


def _atributos_familia(db: Session, p: Producto) -> list[dict]:
    """[{codigo, nombre, tipo, unidad, valor, general, fuera}] de los atributos de producto que lleva su
    familia, con el valor del producto (vacío si no lo tiene) y, al final, los que tiene y su familia
    ya no lleva (`fuera`)."""
    txt = {a["codigo"]: a["valor"] for a in _atributos_txt(db, p)}
    aplican = var_svc.de_grupo(db, p.grupo_producto, "PRODUCTO")
    res = [{"codigo": a.codigo, "nombre": a.nombre, "tipo": a.tipo, "unidad": a.unidad, "valor": txt.get(a.codigo),
            "general": a.general, "fuera": False} for a in aplican]
    vistos = {a.codigo for a in aplican}
    nombres = var_svc.nombres(db)
    res += [{"codigo": k, "nombre": nombres.get(k, k), "tipo": None, "unidad": None, "valor": v, "general": False, "fuera": True}
            for k, v in txt.items() if k not in vistos]
    return res


def _variantes(db: Session, ids: list[int]) -> dict:
    out: dict[int, dict] = {}
    if not ids:
        return out
    for a in db.scalars(select(Articulo).where(Articulo.producto_id.in_(ids)).order_by(Articulo.id)):
        d = out.setdefault(a.producto_id, {"skus": 0, "compuestos": 0, "unidad": None, "articulos": []})
        d["articulos"].append(a)
        if a.tipo == "PREPACK":
            d["compuestos"] += 1
            continue
        d["skus"] += 1
        d["unidad"] = d["unidad"] or a.unidad
    return out


ORDEN = {"estado": ProductoComex.estado, "actualizado": Producto.actualizado_en,
         "codigo": ProductoComex.codigo, "tipo": ProductoComex.tipo,
         # Columnas de la tabla de productos (TablaDatos)
         # El producto se reconoce por su nombre (o su código, si no tiene)
         "producto": func.coalesce(Producto.nombre, Producto.codigo_generico), "proveedor": Proveedor.nombre,
         "generico": Producto.codigo_generico, "origen": ProductoComex.pais_origen, "familia": GrupoProducto.nombre}

# Columnas de la tabla de productos que se filtran por sus valores (app/modulos/comun/tabla.py).
# El código es el aprobado o, mientras no lo hay, el sugerido (como se ve en la lista).
COLUMNAS_PRODUCTOS = {
    "producto": func.coalesce(Producto.nombre, Producto.codigo_generico), "generico": Producto.codigo_generico,
    "proveedor": Proveedor.nombre, "tipo": ProductoComex.tipo, "codigo": func.coalesce(ProductoComex.codigo, ProductoComex.sugerido),
    "estado": ProductoComex.estado, "origen": ProductoComex.pais_origen,
}


def _columnas_productos(db: Session, user: Usuario) -> dict:
    """Columnas filtrables para el usuario: las fijas, la familia y una por atributo de
    producto («atr.<código>»: marca, modelo, material… los que defina la empresa).
    Quien no ve la sugerencia del motor filtra el código solo por el aprobado."""
    res = {**COLUMNAS_PRODUCTOS, "familia": GrupoProducto.nombre}
    for a in var_svc.atributos(db, "PRODUCTO"):
        res[f"atr.{a.codigo}"] = tabla.Relacion(ProductoAtributo.valor, ProductoAtributo.producto_id, Producto.id,
                                                donde=ProductoAtributo.atributo_id == a.id)
    if not flujo.ve_sugerencia(db, user):
        res["codigo"] = ProductoComex.codigo
    return res


def rama_de_grupos(db: Session, grupo_ids) -> set[int]:
    """Los grupos elegidos y todos sus descendientes (filtrar por una familia incluye sus subfamilias y categorías)."""
    from app.modelos import GrupoProducto

    elegidos = {int(x) for x in str(grupo_ids).split(",") if str(x).strip().isdigit()}
    hijos: dict = {}
    for gid, padre in db.execute(select(GrupoProducto.id, GrupoProducto.padre_id)).all():
        hijos.setdefault(padre, []).append(gid)
    res, pendientes = set(), list(elegidos)
    while pendientes:
        g = pendientes.pop()
        if g not in res:
            res.add(g)
            pendientes.extend(hijos.get(g, []))
    return res


def _consulta_productos(db: Session, user: Usuario, filtros: dict):
    """Productos visibles para el usuario con la búsqueda, la familia y la categoría
    elegidas (sin la vista de estado ni los filtros por columna: ahí van los atributos).
    Devuelve la consulta y el alcance de proveedores."""
    exigir(user, "producto.ver")
    prov = proveedor_filtro(user, filtros.get("proveedor_id"))
    base = (select(Producto).join(ProductoComex, ProductoComex.producto_id == Producto.id)
            .outerjoin(Proveedor, Proveedor.id == Producto.proveedor_id)
            .outerjoin(GrupoProducto, GrupoProducto.id == Producto.grupo_producto_id))
    if prov:
        base = base.where(Producto.proveedor_id.in_(prov))
    if filtros.get("tipo"):
        base = base.where(ProductoComex.tipo.in_(str(filtros["tipo"]).split(",")))
    if filtros.get("familia"):
        base = base.where(Producto.grupo_producto_id.in_(rama_de_grupos(db, filtros["familia"])))
    if filtros.get("q"):
        base = base.where(filtro_texto(filtros["q"], lambda p: [
            Producto.nombre.ilike(p), Producto.codigo_generico.ilike(p), ProductoComex.codigo.ilike(p.replace(".", "")),
            Producto.id.in_(select(ProductoAtributo.producto_id).where(ProductoAtributo.valor.ilike(p))),
            Producto.id.in_(select(Articulo.producto_id).where(Articulo.sku.ilike(p))),
            Producto.id.in_(select(Articulo.producto_id).join(ArticuloCodigo).where(ArticuloCodigo.valor.ilike(p)))]))
    return base, prov


def _vista_estado(db: Session, user: Usuario, base, estado: str | None, prov, bloquean: set[int] | None = None):
    """La consulta con la vista de estado de la bandeja: un estado o un grupo
    (pendientes, borradores, aprobados, baja confianza, los que bloquean facturas)."""
    if estado == "bloquean":
        return base.where(Producto.id.in_(bloquean if bloquean is not None else ids_bloquean_facturas(db, prov)))
    if estado == "pendientes":
        return base.where(ProductoComex.estado.in_(PENDIENTES))
    if estado == "borradores":
        return base.where(ProductoComex.estado.in_(BORRADORES))
    if estado == "aprobados":
        return base.where(ProductoComex.estado.in_(APROBADOS))
    # Baja confianza: no aplica si el proveedor no ve la sugerencia
    if estado == "baja_confianza" and flujo.ve_sugerencia(db, user):
        return base.where(ProductoComex.estado.in_(PENDIENTES), ProductoComex.confianza == "low")
    if estado:
        return base.where(ProductoComex.estado == estado)
    return base


def valores_productos(db: Session, user: Usuario, columna: str, q: str | None, por_columna: dict, filtros: dict) -> list[dict]:
    """Valores únicos de una columna de la tabla de productos bajo los demás filtros."""
    columnas = _columnas_productos(db, user)
    expr = tabla.columna_valida(columnas, columna)
    base, prov = _consulta_productos(db, user, filtros)
    consulta = tabla.aplicar(_vista_estado(db, user, base, filtros.get("estado"), prov), columnas, por_columna, excepto=columna)
    return tabla.valores(db, consulta, expr, q, contar=Producto.id)


def listar(db: Session, user: Usuario, filtros: dict, page: int, size: int, orden: str | None,
           por_columna: dict | None = None) -> dict:
    """Productos de la página con sus indicadores por estado; `por_columna` son
    los filtros por columna de la tabla ({columna: [valores]})."""
    base, prov = _consulta_productos(db, user, filtros)
    base = tabla.aplicar(base, _columnas_productos(db, user), por_columna or {})
    # Indicadores por estado con los mismos filtros (menos el de estado)
    sub = base.add_columns(ProductoComex.estado.label("estado")).subquery()
    conteo = {e: n for e, n in db.execute(select(sub.c.estado, func.count()).group_by(sub.c.estado)).all()}
    # Baja confianza legal: lo que el especialista debe mirar primero (no aplica si el proveedor no ve la sugerencia)
    baja = (db.scalar(select(func.count()).select_from(sub)
                      .join(ClasificacionProducto, ClasificacionProducto.producto_id == sub.c.id)
                      .where(sub.c.estado.in_(PENDIENTES), ClasificacionProducto.confianza == "low"))
            if flujo.ve_sugerencia(db, user) else None)
    bloquean = ids_bloquean_facturas(db, prov)
    base = _vista_estado(db, user, base, filtros.get("estado"), prov, bloquean)
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    col, _, direccion = (orden or "actualizado:desc").partition(":")
    campo = ORDEN.get(col, Producto.actualizado_en)
    base = base.order_by(campo.desc() if direccion == "desc" else campo.asc(), Producto.id)
    # Proveedor y atributos de toda la página en una consulta cada uno (no uno por producto)
    filas = db.scalars(base.options(selectinload(Producto.partidas), selectinload(Producto.fotos),
                                    selectinload(Producto.proveedor), selectinload(Producto.atributos),
                                    selectinload(Producto.grupo_producto))
                       .offset((page - 1) * size).limit(size)).all()
    variantes = _variantes(db, [p.id for p in filas])
    marcas = {m.codigo: m.nombre for m in db.scalars(select(Marca))}
    kpis = {
        "total": sum(conteo.values()),
        "pendientes": sum(conteo.get(e, 0) for e in PENDIENTES),
        "borrador": conteo.get("borrador", 0), "sugerida": conteo.get("sugerida", 0),
        "revision": conteo.get("revision", 0), "borradores": sum(conteo.get(e, 0) for e in BORRADORES),
        "observado": conteo.get("observado", 0),
        "aprobados": sum(conteo.get(e, 0) for e in APROBADOS), "baja_confianza": baja,
        "bloquean": len(bloquean),
    }
    ds = destinos(db)
    items = [_resumen(p, variantes, ds, marcas) for p in filas]
    # Para mostrar: el texto del código (árbol oficial o su override) y el nombre corto de la categoría
    from app.modulos.clasificacion.aranceles import textos_sac
    from app.modulos.productos.ficha import catalogo

    textos = textos_sac(db, list({digitos(p.comex.codigo or p.comex.sugerido)[:6] for p in filas if p.comex.codigo or p.comex.sugerido}))
    cats = catalogo(db).categorias
    for x, p in zip(items, filas, strict=False):
        x["codigo_desc"] = textos.get(digitos(p.comex.codigo or p.comex.sugerido or "")[:6])
        c = cats.get(p.comex.tipo or "")
        x["tipo_txt"] = (c.nombre_corto or c.nombre) if c else p.comex.tipo
        if not flujo.ve_sugerencia(db, user) and not p.comex.aprobado:
            flujo.ocultar_resumen(x)
    return {"items": items, "total": total, "page": page, "size": size, "kpis": kpis}


def _historial(db: Session, p: Producto) -> list[dict]:
    filas = db.scalars(select(Historial).where(Historial.entidad == "producto", Historial.entidad_id == p.id)
                       .order_by(Historial.fecha.desc()).limit(80)).all()
    return [{"fecha": h.fecha, "accion": h.accion, "detalle": h.detalle, "motivo": h.motivo,
             "usuario": h.usuario.nombre if h.usuario else None} for h in filas]


def detalle(db: Session, user: Usuario, producto_id: int) -> dict:
    db.flush()  # la sesión no hace autoflush: que se vea lo recién guardado
    p = ver_producto(db, user, producto_id)
    arts = db.scalars(select(Articulo).where(Articulo.producto_id == p.id).order_by(Articulo.tipo.desc(), Articulo.id)).all()
    ds = destinos(db)
    dig = {d["iso"]: d["digitos"] for d in ds}
    r = _resumen(p, _variantes(db, [p.id]), ds)
    r.update({
        "ficha": p.comex.ficha or {}, "descripcion_aduana": p.comex.descripcion_aduana, "pais_procedencia": p.comex.pais_procedencia,
        "grupo_producto_id": p.grupo_producto_id,
        "familia": p.grupo_producto.nombre if p.grupo_producto is not None else None,
        # Los atributos del producto para mostrar: su nombre y su valor (de un catálogo, el nombre del registro)
        "atributos_txt": _atributos_txt(db, p),
        # Los atributos que lleva su familia (con valor o sin él) y los ejes de sus variantes con sus valores
        "atributos_familia": _atributos_familia(db, p),
        "ejes": var_svc.por_atributo(db, arts, var_svc.ejes_de_grupo(db, p.grupo_producto)),
        "analisis": p.comex.analisis or {}, "alertas_ok": p.comex.alertas_ok or [], "observaciones": p.comex.observaciones,
        "resolucion": p.comex.resolucion, "notas": p.comex.notas, "opinion_ia": p.comex.opinion_ia,
        "revisado_por": p.comex.revisado_por.nombre if p.comex.revisado_por else None, "revisado_en": p.comex.revisado_en,
        "vigente_desde": p.comex.vigente_desde, "creado_en": p.creado_en,
        "evidencia": p.comex.evidencia,
        "partidas": {x.pais: {"codigo": x.codigo, "dai": "" if x.dai is None else x.dai, "estado": x.estado, "fuente": x.fuente,
                              "sugerido": x.sugerido, "motivo": x.motivo, "inciso_id": x.inciso_id, "evidencia": x.evidencia,
                              "aprobado_en": x.aprobado_en,
                              "manual": x.manual, "digitos": dig.get(x.pais, 10)} for x in p.partidas},
        "fotos": [{"id": f.id, "nombre": f.nombre} for f in p.fotos],
        "documentos": [_doc_dict(d) for d in p.documentos],
        "versiones": [{"version": v.version, "desde": v.desde, "hasta": v.hasta, "motivo": v.motivo,
                       "codigo": fmt_codigo(v.datos.get("codigo")) if v.datos.get("codigo") else None,
                       "estado": v.datos.get("estado"), "tipo": v.datos.get("tipo"), "cerrado_en": v.cerrado_en}
                      for v in reversed(p.versiones)],
        "articulos": [{"id": a.id, "sku": a.sku, "codigo_proveedor": a.codigo_proveedor, "codigo_barras": a.codigo_barras,
                       "codigos": [{"tipo": c.tipo, "valor": c.valor, "proveedor_id": c.proveedor_id} for c in a.codigos],
                       "codigo_pack": a.codigo_pack, "unidad": a.unidad, "tipo": a.tipo, "peso_unitario": a.peso_unitario,
                       "descripcion": a.descripcion, "activo": a.activo,
                       "valores": var_svc.de_articulo(db, a), "variante": var_svc.texto(var_svc.de_articulo(db, a)) or None}
                      for a in arts],
        # Packs y kits: su contenido (variantes y cantidades)
        "compuestos": [{"id": a.id, "sku": a.sku, "codigo": a.codigo_pack, "descripcion": a.descripcion,
                        "total": a.total_componentes, "kit": a.es_kit,
                        "componentes": [{"sku": c.componente.sku, "cantidad": c.cantidad,
                                         "valores": var_svc.de_articulo(db, c.componente),
                                         "variante": var_svc.texto(var_svc.de_articulo(db, c.componente)) or None}
                                        for c in a.componentes]} for a in arts if a.tipo == "PREPACK"],
        "historial": _historial(db, p),
        "puede_aprobar": tiene(user, "producto.clasificar"),
        "enviado_por_mi": flujo.quien_envio(db, p.id) == user.id,
        "edicion": ajeno_edicion(db, user, "producto", p.id),
    })
    if not flujo.ve_sugerencia(db, user) and not p.comex.aprobado:
        flujo.ocultar_resumen(r)
    return r


def contexto(db: Session, user: Usuario, proveedor_id: int | None = None) -> dict:
    """Lo que la pantalla necesita para mostrar (no para clasificar: eso lo hace
    el motor del servidor en /clasificacion/sesion): destinos, categorías,
    capítulos, notas legales de apoyo y acuerdos comerciales."""
    exigir(user, "producto.ver")
    return {
        "destinos": destinos(db), "pais_base": regla("PAIS_BASE_CLASIF"),
        "notas_sac": notas_contexto(db), "acuerdos": acuerdos_contexto(db),
        "puede_aprobar": tiene(user, "producto.clasificar"),
        "dominios": dominios_ficha(db),
        "categorias": categorias_config(db),
        # Control de capítulos (R-SYS-001): solo los habilitados se eligen automáticamente
        "capitulos": [{"capitulo": c.capitulo, "titulo": c.titulo, "habilitado": bool(c.activo and c.clasificacion and not c.archivado),
                       "solo_manual": c.solo_manual} for c in db.scalars(select(ControlCapitulo))],
    }


