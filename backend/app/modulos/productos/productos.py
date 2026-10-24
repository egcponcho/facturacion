"""Productos: ficha técnica y clasificación arancelaria.

Un producto de cualquier rubro: sus variantes (artículos) y sus packs comparten
la ficha técnica, la partida SAC aprobada y el código nacional de cada país
destino; de aquí los toman la OC y la factura.

La clasificación la hace el motor único del servidor (motor_clasificacion):
la ficha, el guardado, la clasificación masiva y la aprobación pasan por él;
aquí se guarda lo que calcula, se valida lo que se aprueba y se lleva el
historial y la evidencia. Aprobar y enseñar códigos es del equipo interno; la
ficha la puede completar el proveedor.
"""
import os
import re
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session, object_session, selectinload

from app.core import dinero, listas
from app.core.archivos import MIME, TIPOS, exigir_tamano, tipo_imagen
from app.core.empresa import regla
from app.core.errores import ErrorNegocio
from app.modelos import (
    Articulo,
    ArticuloCodigo,
    ClasificacionProducto,
    ControlCapitulo,
    GrupoProducto,
    Historial,
    IncisoNacional,
    Marca,
    Pais,
    PaisArancel,
    PalabraClave,
    PartidaPais,
    Producto,
    ProductoAtributo,
    ProductoComex,
    ProductoDocumento,
    ProductoFoto,
    ProductoVersion,
    Proveedor,
    SinonimoMaterial,
    Usuario,
    ahora,
)
from app.modulos.acceso.permisos import asegurar_proveedor, exigir, proveedor_filtro, tiene
from app.modulos.clasificacion.categorias import categorias as categorias_config
from app.modulos.clasificacion.indice_arbol import dominios_ficha
from app.modulos.comex import flujo
from app.modulos.comex import servicio as comex
from app.modulos.comex.servicio import (  # noqa: F401
    APROBADOS,
    BORRADORES,
    ESTADOS,
    PENDIENTES,
    digitos,
    fmt_codigo,
    sin_marca,
)
from app.modulos.comun import adjuntos, edicion, tabla
from app.modulos.comun.edicion import ajeno as ajeno_edicion
from app.modulos.comun.historial import registrar, tocar, verificar_version
from app.modulos.comun.texto import filtro_texto
from app.modulos.documentos import aduana
from app.modulos.maestros import variantes as var_svc
from app.modulos.maestros.acuerdos import acuerdos_contexto


# Países destino y dígitos de su código nacional (Centroamérica y Panamá)
# Países destino de fábrica; en la base se pueden agregar otros y cambiar sus dígitos
def destinos(db: Session) -> list[dict]:
    """Países destino activos con su arancel (configuración del país; sin
    países cargados no hay destinos: no se inventan)."""
    filas = db.scalars(select(PaisArancel).where(PaisArancel.activo.is_(True))
                       .order_by(PaisArancel.orden, PaisArancel.iso)).all()
    return [{"iso": x.iso, "nombre": x.nombre, "digitos": x.digitos, "mcca": x.mcca, "impuesto": x.impuesto,
             "base_legal": x.base_legal} for x in filas]


# Borrador (incompleto o completo) → enviado a revisión → aprobado o devuelto (comex/servicio.py).
# Mientras es borrador, lo edita cualquiera con permiso; enviado queda
# cerrado para el proveedor hasta que se apruebe o se devuelva.
TIPOS_FOTO = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
TIPOS_DOC = {"application/pdf": ".pdf", "image/jpeg": ".jpg", "image/png": ".png"}
# Campos que una ficha técnica nunca aporta: el arancel solo sale de fuentes oficiales
NO_ARANCEL = {"hs", "hs6", "hs_code", "codigo", "code", "tariff", "tariff_code", "dai", "sac", "partida", "inciso", "impuesto", "tax",
              "regulacion", "regulation"}


# ---- Producto de cada artículo ------------------------------------------------
def producto_de(a: Articulo | None) -> Producto | None:
    """Producto que da la clasificación a un artículo: el suyo (un pack es del
    producto de sus variantes; un kit es su propio producto)."""
    return a.producto if a is not None else None


def ids_bloquean_facturas(db: Session, prov: frozenset | None = None) -> set[int]:
    """Productos sin clasificación aprobada que dejan una factura en curso sin partida."""
    from app.modulos.facturacion.bloqueos import productos_que_bloquean

    return productos_que_bloquean(db, prov)


# Códigos de artículo y de genérico: el formato lo define cada empresa
# (numérico o alfanumérico, con punto, guion, barra o guion bajo)
RE_CODIGO = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._\-/]{0,39}$")
MSG_CODIGO = "Letters and numbers (also . - _ /), up to 40 characters."


def codigo_valido(valor: str | None) -> bool:
    return bool(RE_CODIGO.match(str(valor or "").strip()))


def generico_de(a) -> str | None:
    """Código del producto de un artículo o de una fila de datos: el que trae; si no,
    el propio código del artículo (un producto sin variantes, como un químico o una
    materia prima)."""
    if a is None:
        return None
    if isinstance(a, dict):
        return str(a.get("generico") or "").strip().upper() or (str(a.get("sku") or "").strip().upper() or None)
    return a.generico or (a.sku or None)


def producto_por_generico(db: Session, gen: str | None) -> Producto | None:
    return db.scalar(select(Producto).where(Producto.codigo_generico == gen)) if gen else None


def asegurar_producto(db: Session, a: Articulo, generico: str | None = None,
                      proveedor_id: int | None = None) -> Producto:
    """Liga el artículo con el producto de su código (genérico; sin código, el del
    propio artículo) y lo crea si no existe. Las variantes y los packs del mismo
    producto comparten la ficha técnica y la clasificación."""
    gen = (generico or "").strip().upper() or (a.producto.codigo_generico if a.producto is not None else None) \
        or (a.sku or "").strip().upper()
    p = a.producto if a.producto is not None and a.producto.codigo_generico == gen else producto_por_generico(db, gen)
    if p is None:
        p = Producto(proveedor_id=proveedor_id, unidad=a.unidad if a.tipo == "SOLIDO" else None,
                     codigo_generico=gen, nombre=a.descripcion or gen)
        db.add(p)
    if proveedor_id and not p.proveedor_id:
        p.proveedor_id = proveedor_id
    if a.tipo == "SOLIDO" and not p.unidad:
        p.unidad = a.unidad
    a.producto = p
    if not p.comex.descripcion_comercial and not (p.comex.ficha or {}).get("comManual"):
        p.comex.descripcion_comercial = descripcion_comercial_simple(p)
    return p


def marca_de(p: Producto | None):
    """La marca del producto (el registro del catálogo de marcas que dice su atributo de marca)."""
    codigo = p.marca_codigo if p is not None else None
    db = object_session(p) if p is not None else None
    return db.scalar(select(Marca).where(Marca.codigo == codigo)) if codigo and db is not None else None


def nombre_producto(p: Producto) -> str:
    """Cómo se nombra el producto en mensajes: su nombre o su código."""
    return p.nombre or p.codigo_generico or str(p.id)


def descripcion_comercial_simple(p: Producto) -> str | None:
    """Descripción comercial de factura y packing list: tipo y marca (p. ej.
    CALZADO VANS), con la plantilla de la categoría (la misma del motor)."""
    from sqlalchemy.orm import object_session

    from app.modulos.productos.descripciones import descripcion_comercial
    from app.modulos.productos.ficha import catalogo

    db = object_session(p)
    if not p.comex.tipo or db is None:
        return None
    cat = catalogo(db)
    c = cat.categorias.get(p.comex.tipo)
    if not c:
        return None
    s = cat.hechos_base(dict(p.comex.ficha or {}), p.comex.tipo, c.dominio)
    cat.normalizar(s)
    marca = marca_de(p)
    return descripcion_comercial(cat, s, c, marca.nombre if marca else None)[:300] or None


def partida_para(p: Producto | None) -> str | None:
    """Código que va en la OC y la factura: la subpartida de 6 dígitos aprobada (comex/servicio.py)."""
    return comex._ficha(p.comex).partida if p is not None else None


def clasificacion_txt(p: Producto | None) -> dict:
    """Resumen corto para mostrar junto al artículo en la OC o la factura."""
    return comex._ficha(p.comex).resumen() if p is not None else dict(comex.SIN_PRODUCTO)


# ---- Códigos nacionales en el servidor (base cargada y aprobaciones en lote) ---
def _codigo_fila(codigo) -> str:
    c = digitos(codigo)
    if len(c) > 14:  # nunca se recorta un código
        raise ErrorNegocio(f"{codigo}: a national code has at most 14 digits.", 422, "validacion")
    return c


def _guardar_partidas(p: Producto, partidas: dict | None) -> None:
    previas = {x.pais: x for x in p.partidas}
    for iso in sorted(set(previas) | {k for k in (partidas or {}) if isinstance(k, str) and len(k) == 2}):
        x = (partidas or {}).get(iso)
        if not x or not digitos(x.get("codigo")):
            if iso in previas:
                p.partidas.remove(previas[iso])
            continue
        fila = previas.get(iso) or PartidaPais(pais=iso)
        fila.codigo = _codigo_fila(x.get("codigo"))
        fila.dai = dinero.porcentaje_o_nota(x.get("dai"))[0]
        fila.estado = str(x.get("estado") or "ok")[:12]
        fila.fuente = (x.get("fuente") or None) and str(x.get("fuente"))[:12]
        fila.manual = bool(x.get("manual"))
        if not fila.manual:
            fila.sugerido = fila.codigo  # lo que eligió el motor (para comparar con el final)
        elif x.get("sugerido"):
            fila.sugerido = _codigo_fila(x.get("sugerido"))
        if x.get("motivo"):
            fila.motivo = str(x["motivo"])[:300]
        if iso not in previas:
            p.partidas.append(fila)


# ---- Lectura -------------------------------------------------------------------
def _producto(db: Session, user: Usuario, producto_id: int) -> Producto:
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
    p = _producto(db, user, producto_id)
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


# ---- Guardar la ficha técnica ------------------------------------------------
CAMPOS_TEXTO = {"nombre": 200, "notas": 1000}  # el genérico sale del código de artículo


def _categoria_de_familia(p: Producto) -> str | None:
    """Sin categoría en su ficha, la que eligió su familia (sección de comercio exterior)."""
    from app.modulos.comex import familia

    db = object_session(p)
    return familia.categoria_de(db, p.grupo_producto_id) if db is not None and p.grupo_producto_id else None


def entrada_producto(p: Producto, extra: dict | None = None) -> dict:
    """La ficha natural del producto para el motor único (la misma para la
    pantalla, el guardado, la aprobación y el lote)."""
    f = dict(p.comex.ficha or {})
    marca = marca_de(p)
    return {"categoria": p.comex.tipo or _categoria_de_familia(p), "ficha": f, "nombre": p.nombre, "uso": f.get("uso"), "tallas": f.get("tallas"),
            "marca": marca.nombre if marca else None, "proveedor": p.proveedor.nombre if p.proveedor else None,
            "origen": p.comex.pais_origen, "generico": p.codigo_generico, "producto_id": p.id, "alertas_ok": p.comex.alertas_ok or [],
            "partidas": {x.pais: {"codigo": x.codigo, "manual": True} for x in p.partidas if x.manual}, "detectar": False, **(extra or {})}


def _valor_legible(c: dict) -> str:
    v = c.get("valor")
    if c["tipo_dato"] == "boolean":
        return "Yes" if v else "No"
    if isinstance(v, list):
        return ", ".join(next((o["etiqueta"] for o in c["opciones"] if o["codigo"] == x), str(x)) for x in v)
    return next((o["etiqueta"] for o in c["opciones"] if o["codigo"] == v), str(v))


def _fuente_motor(r: dict) -> str:
    top = (r.get("candidatos") or [{}])[0]
    origen = top.get("origen") or []
    if any(o.startswith("regla") for o in origen):
        return "regla"
    return "historial" if "historial" in origen else "texto"


def _aplicar_motor(p: Producto, r: dict) -> None:
    """Guarda lo que calculó el motor único (sin aprobar nada)."""
    if r.get("categoria"):
        p.comex.tipo = r["categoria"]["codigo"][:30]
    p.comex.ficha = r["ficha"]
    hs6, sac = r.get("hs6"), r["clasificacion"]["sac"]["codigo"]
    p.comex.sugerido, p.comex.sac_sugerido = hs6, sac
    p.comex.confianza = r["confianza"]
    p.comex.fuente = _fuente_motor(r) if hs6 else None
    p.comex.perfil = (r.get("perfil") or "")[:200] or None
    legibles = [[c["etiqueta"], _valor_legible(c)] for c in r["campos"]
                if c["seccion"] in ("producto", "caracteristicas", "composicion", "nacional") and c["tipo_dato"] != "composition"
                and c.get("valor") not in (None, "", [], False)]
    p.comex.analisis = {"razones": r["razones"], "alternativas": r["alternativas"][:20], "avisos": [a["texto"] for a in r["avisos"]][:20],
                  "faltantes": [f["etiqueta"] for f in r["faltantes"]][:20], "alertas": r["alertas"][:60], "revision_por": r["revision_por"][:20],
                  "requiere_revision": r["requiere_revision"], "atributos": legibles[:60],
                  "tipo_txt": (r.get("categoria") or {}).get("nombre"), "version": r.get("version")}
    if not (p.comex.ficha or {}).get("descManual"):
        p.comex.descripcion_aduana = (r["descripciones"]["aduana"] or "")[:400] or None
    if not (p.comex.ficha or {}).get("comManual"):
        p.comex.descripcion_comercial = (r["descripciones"]["comercial"] or "")[:300] or descripcion_comercial_simple(p)
    faltan = [f["etiqueta"] for f in r["faltantes"]]
    if not p.comex.tipo:
        faltan.insert(0, "Product type")
    if not hs6:
        faltan.append("Data for the code")
    p.comex.ficha_completa = not faltan
    p.comex.faltan = [str(x)[:120] for x in faltan][:20]
    if p.comex.estado not in APROBADOS:
        _guardar_partidas(p, {x["pais"]: {"codigo": x["codigo"], "dai": x["dai"], "estado": x["estado"], "fuente": x["fuente"],
                                          "manual": x["manual"]} for x in r["clasificacion"]["paises"]})
        if p.comex.estado != "revision":
            p.comex.estado = "sugerida" if p.comex.ficha_completa and p.comex.sugerido else "borrador"


def clasificar_y_guardar(db: Session, p: Producto, extra: dict | None = None, catalogo=None) -> dict:
    from app.modulos.clasificacion.motor_clasificacion import clasificar_producto

    r = clasificar_producto(db, entrada_producto(p, extra), catalogo=catalogo)
    _aplicar_motor(p, r)
    return r


def guardar_ficha(db: Session, user: Usuario, producto_id: int, datos) -> dict:
    exigir(user, "producto.ficha")
    p = _producto(db, user, producto_id)
    verificar_version(p, datos.version, "product")
    if p.comex.estado in APROBADOS:
        raise ErrorNegocio("The technical sheet is approved. Create a new version to change it.", 409, "ficha_aprobada")
    if p.comex.estado == "revision" and not tiene(user, "producto.clasificar"):
        raise ErrorNegocio("The technical sheet was sent to review. Take it back to draft to change it.", 409, "en_revision")
    antes = {"tipo": p.comex.tipo, "ficha": p.comex.ficha, "estado": p.comex.estado}
    p.comex.tipo = (datos.tipo or None) and datos.tipo[:30]
    p.comex.ficha = datos.ficha or {}
    for campo, largo in CAMPOS_TEXTO.items():
        v = getattr(datos, campo, None)
        if v is not None:
            setattr(p if campo == "nombre" else p.comex, campo, str(v).strip()[:largo] or None)
    if datos.pais_origen is not None:
        p.comex.pais_origen = (datos.pais_origen or "").upper()[:2] or None
    if datos.pais_procedencia is not None:
        p.comex.pais_procedencia = (datos.pais_procedencia or "").upper()[:2] or None
    p.comex.alertas_ok = list(datos.alertas_ok or [])[:100]
    # Códigos nacionales escritos a mano (se validan en el motor: existen o tienen una longitud válida)
    manuales = {iso: x for iso, x in (datos.partidas or {}).items() if isinstance(x, dict) and x.get("manual") and digitos(x.get("codigo"))}
    for x in list(p.partidas):
        if x.manual and x.pais not in manuales:
            p.partidas.remove(x)
    _guardar_partidas(p, {**{x.pais: {"codigo": x.codigo, "dai": x.dai, "estado": x.estado, "fuente": x.fuente, "manual": x.manual}
                             for x in p.partidas}, **{iso: {**x, "estado": "manual"} for iso, x in manuales.items()}})
    devuelto = p.comex.estado == "observado"
    clasificar_y_guardar(db, p, {"tocados": list(datos.tocados or [])})
    if datos.descripcion_aduana is not None and (p.comex.ficha or {}).get("descManual"):
        p.comex.descripcion_aduana = datos.descripcion_aduana.strip()[:400] or None
    if datos.descripcion_comercial is not None and (p.comex.ficha or {}).get("comManual"):
        p.comex.descripcion_comercial = datos.descripcion_comercial.strip()[:300] or None
    tocar(p)
    cambios = [k for k in ("tipo", "ficha") if antes[k] != getattr(p.comex, k)]
    registrar(db, user, "producto", p.id, "ficha_guardada",
              {"cambios": cambios, "estado": [antes["estado"], p.comex.estado], "sugerido": fmt_codigo(p.comex.sugerido) or None,
               "devuelto": devuelto})
    return detalle(db, user, p.id)


def clasificar_lote(db: Session, user: Usuario, ids: list[int]) -> dict:
    """Clasifica varios productos con el mismo motor que la ficha (lo que se
    deduce del nombre y la composición completa lo vacío; nada se pisa)."""
    from app.modulos.productos.ficha import catalogo

    exigir(user, "producto.ficha")
    cat = catalogo(db)
    hechos, omitidos = 0, []
    for pid in ids:
        p = _producto(db, user, pid)
        if p.comex.estado in APROBADOS:
            omitidos.append({"id": p.id, "mensaje": f"{nombre_producto(p)} is already approved."})
            continue
        antes = p.comex.estado
        clasificar_y_guardar(db, p, {"detectar": True}, catalogo=cat)
        tocar(p)
        registrar(db, user, "producto", p.id, "clasificado", {"estado": [antes, p.comex.estado], "sugerido": fmt_codigo(p.comex.sugerido) or None})
        hechos += 1
    return {"clasificados": hechos, "omitidos": omitidos}


# ---- Aprobar, devolver y versiones -------------------------------------------
def _aprobar(db: Session, user: Usuario, p: Producto, codigo: str | None, partidas: dict | None, lote: bool = False) -> None:
    """Aprueba con el motor único: el código se vuelve a validar contra el árbol
    de la versión vigente y contra las reglas; cada país con su línea nacional
    de la versión vigente del país. Guarda la evidencia completa."""
    from app.modulos.clasificacion.motor_clasificacion import clasificar_producto

    oficial = digitos(codigo or p.comex.propuesta or p.comex.sac_sugerido or p.comex.sugerido)
    if len(oficial) < 6:
        raise ErrorNegocio(f"{nombre_producto(p)}: there is no HS code to approve.", 422, "sin_partida")
    if len(oficial) > 14:
        raise ErrorNegocio("The HS code is too long.", 422, "validacion")
    # Cada línea nacional que indica quien aprueba es una elección: el motor la valida
    elegidas = {iso: x for iso, x in (partidas or {}).items() if isinstance(x, dict) and digitos(x.get("codigo"))}
    if partidas is None:
        elegidas = {x.pais: {"codigo": x.codigo, "manual": True, "sugerido": x.sugerido, "motivo": x.motivo} for x in p.partidas if x.manual}
    r = clasificar_producto(db, entrada_producto(p, {"codigo_final": oficial,
                                                     "partidas": {iso: {"codigo": digitos(x["codigo"])} for iso, x in elegidas.items()}}))
    errores = [a["msg"] for a in r["alertas"] if a["nivel"] == "error" and a.get("origen") in ("codigo", "capitulo")]
    if any(a.get("origen") == "capitulo" and a["nivel"] == "error" for a in r["alertas"]):
        raise ErrorNegocio(f"{nombre_producto(p)}: " + " ".join(errores), 422, "capitulo_no_habilitado")
    if len(oficial) > 6 and r["sac"] != oficial:
        raise ErrorNegocio(f"{fmt_codigo(oficial)} is not an official SAC line of the tariff in force. "
                           "The product keeps its HS6 and each country chooses its own national line.", 422, "no_es_linea_sac")
    if errores:
        raise ErrorNegocio(f"{nombre_producto(p)}: " + " ".join(errores), 422, "codigo_invalido")
    paises = r["clasificacion"]["paises"]
    invalidos = [x for x in paises if x["estado"] == "invalido"]
    if invalidos:
        raise ErrorNegocio("; ".join(f"{x['pais']}: {x['error']}" for x in invalidos), 422, "codigo_nacional_invalido")
    # Con incertidumbre el caso queda pendiente: nunca se aprueba solo. En lote no se aprueba lo que pide revisión
    if lote and (r["requiere_revision"] or r["confianza"] == "low"):
        raise ErrorNegocio(f"{nombre_producto(p)}: needs a specialist review (" + "; ".join(r["revision_por"][:2] or ["low legal confidence"]) + ").",
                           422, "requiere_revision")
    # Las líneas nacionales son referencia (la OC y la factura llevan la subpartida de 6 dígitos):
    # aprobar no las exige. Una que solo el historial prefiere o que falta elegir queda pendiente
    # de confirmar por una persona (confirmar_partida), nunca se da por confirmada.
    sug = digitos(p.comex.sugerido)
    p.comex.estado = "aprobado" if not sug or sug[:6] == oficial[:6] else "corregido"
    p.comex.codigo = oficial[:6]
    p.comex.sac_codigo = oficial if len(oficial) > 6 else r["sac"]
    p.comex.propuesta = None
    p.comex.version_arancel_id = r["version"]["id"] if r.get("version") else None
    ahora_ = ahora()
    p.comex.evidencia = {**r["evidencia"], "aprobacion": {"fecha": ahora_.isoformat(), "usuario": user.nombre if user else None, "hs6": p.comex.codigo,
                                                    "sac": p.comex.sac_codigo, "sugerido": sug or None, "confianza": r["confianza"],
                                                    "requiere_revision": r["requiere_revision"], "revision_por": r["revision_por"],
                                                    "razones": r["razones"], "alternativas": r["alternativas"][:10]},
                   "paises": [{k: x.get(k) for k in ("pais", "estado", "codigo", "dai", "inciso_id", "regla", "version", "fuente", "fuente_oficial",
                                                     "manual", "descripcion", "overrides", "historial", "sin_datos_oficiales", "error")}
                              for x in paises]}
    _guardar_partidas(p, {x["pais"]: {"codigo": x["codigo"], "dai": x["dai"], "estado": x["estado"], "fuente": x["fuente"],
                                      "manual": x["manual"] or bool((elegidas.get(x["pais"]) or {}).get("manual")),
                                      "sugerido": (elegidas.get(x["pais"]) or {}).get("sugerido") or x["sugerido"],
                                      "motivo": (elegidas.get(x["pais"]) or {}).get("motivo")} for x in paises})
    db.flush()
    por_pais = {x["pais"]: x for x in paises}
    for fila in p.partidas:
        x = por_pais.get(fila.pais) or {}
        fila.inciso_id = x.get("inciso_id")
        fila.version_id = (x.get("version") or {}).get("id") if x.get("inciso_id") else None
        inc = db.get(IncisoNacional, x["inciso_id"]) if x.get("inciso_id") else None
        fila.fuente_id = inc.fuente_id if inc else None
        fila.evidencia = {"linea_oficial": bool(inc and inc.fuente == "oficial"), "fuente_dato": x.get("fuente"), "regla": x.get("regla"),
                          "version": x.get("version"), "overrides": x.get("overrides"),
                          "impuestos": [{k: i.get(k) for k in ("codigo", "tipo", "tasa", "base_calculo", "base_legal", "fuente")} for i in x.get("impuestos") or []],
                          "regulaciones": [{k: g.get(k) for k in ("codigo", "tipo", "nombre", "autoridad", "base_legal")} for g in x.get("regulaciones") or []]}
        confirmada = x.get("estado") == "ok"
        fila.aprobado_por_id, fila.aprobado_en = ((user.id if user else None), ahora_) if confirmada else (None, None)
    p.comex.revisado_por_id = user.id if user else None
    p.comex.revisado_en = ahora_
    # La decisión queda como conocimiento de la empresa (nunca como dato oficial):
    # el HS6 con la categoría y, por país, la línea oficial con los datos que la eligieron
    from app.modulos.clasificacion.conocimiento import registrar_decision

    origen = "APROBACION" if p.comex.estado == "aprobado" else "CORRECCION"
    hechos = r.get("hechos") or {}
    registrar_decision(db, pais=None, codigo=p.comex.sac_codigo or p.comex.codigo, condiciones={}, origen=origen, categoria=p.comex.tipo, producto_id=p.id, usuario=user)
    for x in paises:
        if x.get("estado") == "ok" and x.get("inciso_id") and x.get("codigo"):  # solo lo confirmado es conocimiento
            claves = {k for o in x.get("opciones") or [] for k in (o.get("cond") or {})} | set(x.get("faltan") or [])
            registrar_decision(db, pais=x["pais"], codigo=x["codigo"], condiciones={k: hechos.get(k) for k in claves if hechos.get(k) is not None},
                               origen=origen, categoria=p.comex.tipo, producto_id=p.id, usuario=user)
    tocar(p)
    registrar(db, user, "producto", p.id, "aprobado" if p.comex.estado == "aprobado" else "corregido",
              {"codigo": fmt_codigo(oficial), "sugerido": fmt_codigo(sug) or None,
               "paises": {x["pais"]: fmt_codigo(x["codigo"]) for x in paises if x.get("codigo")}})


def _pais_aprobado(db: Session, user: Usuario, producto_id: int, pais: str, codigo: str | None = None):
    from app.modulos.clasificacion.motor_clasificacion import clasificar_producto

    p = _producto(db, user, producto_id)
    if p.comex.estado not in APROBADOS or not p.comex.codigo:
        raise ErrorNegocio("Approve the product first: the national codes hang from its approved subheading.", 422, "no_aprobado")
    extra = {"codigo_final": p.comex.sac_codigo or p.comex.codigo}
    if codigo is not None:
        extra["partidas"] = {pais: {"codigo": digitos(codigo)}}
    r = clasificar_producto(db, entrada_producto(p, extra))
    x = next((y for y in r["clasificacion"]["paises"] if y["pais"] == pais), None)
    if not x:
        raise ErrorNegocio(f"{pais} is not an active destination country.", 404, "no_encontrado")
    return p, r, x


def opciones_partida(db: Session, user: Usuario, producto_id: int, pais: str) -> dict:
    """Las líneas oficiales vigentes del país para la subpartida aprobada (para confirmar una)."""
    _, _, x = _pais_aprobado(db, user, producto_id, pais.upper())
    return {"pais": x["pais"], "estado": x["estado"], "codigo": x["codigo"], "error": x["error"], "digitos": x["digitos"],
            "opciones": [{"codigo": o["codigo"], "descripcion": o["descripcion"], "cond_txt": o.get("cond_txt"), "dai": o["dai"]} for o in x["opciones"]]}


def confirmar_partida(db: Session, user: Usuario, producto_id: int, pais: str, codigo: str) -> dict:
    """Una persona confirma la línea nacional de un país de un producto ya
    aprobado: el motor la valida contra el arancel vigente del país (solo una
    línea oficial de la subpartida aprobada) y queda como decisión de la empresa."""
    from app.modulos.clasificacion.conocimiento import registrar_decision

    exigir(user, "producto.clasificar")
    pais = pais.upper()
    if not digitos(codigo):
        raise ErrorNegocio("Write or choose the national code.", 422, "validacion")
    p, r, x = _pais_aprobado(db, user, producto_id, pais, codigo)
    if x["estado"] != "ok" or not x.get("inciso_id"):
        raise ErrorNegocio(x.get("error") or f"{fmt_codigo(codigo)} is not an official national line of {pais} for this subheading.",
                           422, "codigo_nacional_invalido", [{"codigo": o["codigo"], "descripcion": o["descripcion"]} for o in x["opciones"]])
    fila = next((y for y in p.partidas if y.pais == pais), None)
    antes = fila.codigo if fila else None
    if not fila:
        fila = PartidaPais(pais=pais)
        p.partidas.append(fila)
    fila.sugerido = fila.sugerido or x.get("sugerido") or fila.codigo
    fila.codigo, fila.dai, fila.estado, fila.fuente, fila.manual = _codigo_fila(x["codigo"]), dinero.porcentaje_o_nota(x.get("dai"))[0], "ok", \
        (x.get("fuente") or None) and str(x["fuente"])[:12], True
    inc = db.get(IncisoNacional, x["inciso_id"])
    fila.inciso_id, fila.version_id = x["inciso_id"], (x.get("version") or {}).get("id")
    fila.fuente_id = inc.fuente_id if inc else None
    fila.evidencia = {"linea_oficial": bool(inc and inc.fuente == "oficial"), "fuente_dato": x.get("fuente"), "regla": x.get("regla"),
                      "version": x.get("version"), "confirmada_despues": True}
    fila.aprobado_por_id, fila.aprobado_en = user.id, ahora()
    hechos = r.get("hechos") or {}
    claves = {k for o in x.get("opciones") or [] for k in (o.get("cond") or {})} | set(x.get("faltan") or [])
    registrar_decision(db, pais=pais, codigo=x["codigo"], condiciones={k: hechos.get(k) for k in claves if hechos.get(k) is not None},
                       origen="APROBACION", categoria=p.comex.tipo, producto_id=p.id, usuario=user)
    tocar(p)
    registrar(db, user, "producto", p.id, "partida_confirmada", {"pais": pais, "codigo": [fmt_codigo(antes) or None, fmt_codigo(x["codigo"])]})
    return detalle(db, user, p.id)


def aprobar(db: Session, user: Usuario, producto_id: int, datos) -> dict:
    exigir(user, "producto.clasificar")
    p = _producto(db, user, producto_id)
    verificar_version(p, datos.version, "product")
    flujo.exigir_aprobacion(db, user, p)
    if not p.comex.ficha_completa and not datos.forzar:
        raise ErrorNegocio("The technical sheet is incomplete: " + ", ".join(p.comex.faltan[:4]) + ".", 422, "ficha_incompleta",
                           [{"mensaje": x} for x in p.comex.faltan])
    _aprobar(db, user, p, datos.codigo, datos.partidas)
    return detalle(db, user, p.id)


def aprobar_lote(db: Session, user: Usuario, ids: list[int]) -> dict:
    """Aprueba la partida sugerida de varios productos con su ficha completa.
    Cada uno se aprueba o no por su cuenta; se informa cuáles no."""
    exigir(user, "producto.clasificar")
    if not flujo.activo(db, "aprobacion_lote"):
        raise ErrorNegocio("Bulk approval is turned off: approve each sheet on its own page.", 422, "lote_apagado")
    ok, errores = 0, []
    for pid in ids:
        p = _producto(db, user, pid)
        if p.comex.estado in APROBADOS:
            continue
        if p.comex.estado not in ("sugerida", "revision") or not p.comex.ficha_completa:
            errores.append({"id": p.id, "mensaje": f"{nombre_producto(p)}: the sheet is not complete."})
            continue
        try:
            with db.begin_nested():
                flujo.exigir_aprobacion(db, user, p)
                # Solo cuentan como elección las líneas que una persona eligió; las sugeridas se vuelven a validar
                _aprobar(db, user, p, None, None, lote=True)
            ok += 1
        except ErrorNegocio as e:
            errores.append({"id": p.id, "mensaje": e.mensaje})
    return {"aprobados": ok, "errores": errores}


def observar(db: Session, user: Usuario, producto_id: int, datos) -> dict:
    """Observaciones del especialista; con `devolver`, la ficha vuelve al
    proveedor para que la corrija."""
    exigir(user, "producto.clasificar")
    p = _producto(db, user, producto_id)
    verificar_version(p, datos.version, "product")
    p.comex.observaciones = (datos.observaciones or "").strip()[:2000] or None
    p.comex.resolucion = (datos.resolucion or "").strip()[:200] or None
    if datos.devolver:
        if p.comex.estado in APROBADOS:
            raise ErrorNegocio("An approved sheet cannot be returned; create a new version.", 409, "ficha_aprobada")
        if not p.comex.observaciones:
            raise ErrorNegocio("Write what the supplier has to fix.", 422, "motivo_requerido")
        p.comex.estado = "observado"
    tocar(p)
    registrar(db, user, "producto", p.id, "devuelto" if datos.devolver else "observacion",
              {"observaciones": p.comex.observaciones, "resolucion": p.comex.resolucion})
    return detalle(db, user, p.id)


def enviar_revision(db: Session, user: Usuario, ids: list[int]) -> dict:
    """Envía fichas en borrador a revisión: deben estar completas y con partida."""
    exigir(user, "producto.ficha")
    ok, errores = 0, []
    for pid in ids:
        p = _producto(db, user, pid)
        nombre = nombre_producto(p)
        if p.comex.estado not in BORRADORES:
            errores.append({"id": p.id, "mensaje": f"{nombre} is {ESTADOS.get(p.comex.estado, p.comex.estado).lower()}."})
            continue
        if not p.comex.ficha_completa or not p.comex.sugerido:
            falta = ", ".join((p.comex.faltan or [])[:4]) or "the HS code"
            errores.append({"id": p.id, "mensaje": f"{nombre}: complete the sheet first ({falta})."})
            continue
        antes = p.comex.estado
        p.comex.estado = "revision"
        tocar(p)
        registrar(db, user, "producto", p.id, "enviado", {"estado": [antes, p.comex.estado]})
        ok += 1
    if len(ids) == 1 and errores:
        raise ErrorNegocio(errores[0]["mensaje"], 422, "no_enviado", errores)
    return {"enviados": ok, "errores": errores}


def retirar_revision(db: Session, user: Usuario, producto_id: int) -> dict:
    """Vuelve a borrador una ficha enviada (para corregirla antes de que la revisen)."""
    exigir(user, "producto.ficha")
    p = _producto(db, user, producto_id)
    if p.comex.estado != "revision":
        raise ErrorNegocio("Only a sheet in review can go back to draft.", 409, "estado")
    p.comex.estado = "sugerida" if p.comex.ficha_completa and p.comex.sugerido else "borrador"
    tocar(p)
    registrar(db, user, "producto", p.id, "retirado", {"estado": ["revision", p.comex.estado]})
    return detalle(db, user, p.id)


def nueva_version(db: Session, user: Usuario, producto_id: int, datos) -> dict:
    """Cierra la ficha vigente con su partida y abre una copia para editar."""
    exigir(user, "producto.ficha")
    p = _producto(db, user, producto_id)
    verificar_version(p, datos.version, "product")
    desde = datos.desde or date.today()
    inicio = p.comex.vigente_desde or (p.creado_en.date() if p.creado_en else desde)
    if desde <= inicio and p.versiones:
        raise ErrorNegocio("The new version must start after the current one.", 422, "validacion")
    db.add(ProductoVersion(
        producto=p, version=p.comex.version_ficha, desde=inicio, hasta=desde - timedelta(days=1), motivo=(datos.motivo or "")[:300] or None,
        # Autosuficiente para auditoría: ficha, clasificación, versión arancelaria,
        # evidencia (reglas con su foto, hechos, notas, overrides) y países con su línea
        datos={"tipo": p.comex.tipo, "ficha": p.comex.ficha, "nombre": p.nombre, "codigo": p.comex.codigo, "sac_codigo": p.comex.sac_codigo, "sugerido": p.comex.sugerido,
               "sac_sugerido": p.comex.sac_sugerido, "estado": p.comex.estado, "descripcion_aduana": p.comex.descripcion_aduana,
               "descripcion_comercial": p.comex.descripcion_comercial, "pais_origen": p.comex.pais_origen, "pais_procedencia": p.comex.pais_procedencia,
               "analisis": p.comex.analisis, "confianza": p.comex.confianza, "fuente": p.comex.fuente, "perfil": p.comex.perfil,
               "version_arancel": ({"id": p.comex.version_arancel_id, **((p.comex.evidencia or {}).get("version") or {})} if p.comex.version_arancel_id else None),
               "evidencia": p.comex.evidencia, "observaciones": p.comex.observaciones, "resolucion": p.comex.resolucion,
               "partidas": {x.pais: {"codigo": x.codigo, "dai": x.dai, "estado": x.estado, "fuente": x.fuente, "manual": x.manual,
                                     "sugerido": x.sugerido, "motivo": x.motivo, "inciso_id": x.inciso_id, "version_id": x.version_id,
                                     "evidencia": x.evidencia, "aprobado_en": x.aprobado_en.isoformat() if x.aprobado_en else None}
                            for x in p.partidas},
               "revisado_por": p.comex.revisado_por.nombre if p.comex.revisado_por else None,
               "revisado_en": p.comex.revisado_en.isoformat() if p.comex.revisado_en else None},
        cerrado_por=user.id))
    p.comex.version_ficha += 1
    p.comex.vigente_desde = desde
    p.comex.estado = "borrador"
    p.comex.codigo = None
    p.comex.revisado_por_id = None
    p.comex.revisado_en = None
    p.partidas.clear()
    tocar(p)
    registrar(db, user, "producto", p.id, "nueva_version",
              {"version": p.comex.version_ficha, "desde": desde.isoformat()}, motivo=datos.motivo)
    return detalle(db, user, p.id)


def guardar_opinion(db: Session, user: Usuario, producto_id: int, opinion: dict) -> None:
    p = _producto(db, user, producto_id)
    p.comex.opinion_ia = opinion


# ---- Fotos ---------------------------------------------------------------------
def subir_foto(db: Session, user: Usuario, producto_id: int, nombre: str, tipo: str, contenido: bytes) -> dict:
    exigir(user, "producto.ficha")
    p = _producto(db, user, producto_id)
    exigir_tamano(contenido)
    # El tipo sale del contenido, no de lo que declara el navegador
    tipo = MIME.get(tipo_imagen(contenido) or "")
    if tipo not in TIPOS_FOTO:
        raise ErrorNegocio("Upload a JPG, PNG or WebP image.", 422, "validacion")
    if len(p.fotos) >= 8:
        raise ErrorNegocio("A product can have up to 8 photos.", 422, "validacion")
    seguro = adjuntos.nombre_seguro(nombre, "photo")
    adj = adjuntos.crear(db, user, seguro, contenido, os.path.join("productos", str(p.id)), TIPOS_FOTO[tipo], tipo)
    f = ProductoFoto(adjunto=adj)
    p.fotos.append(f)
    db.flush()
    registrar(db, user, "producto", p.id, "foto_agregada", {"foto": seguro})
    return {"id": f.id, "nombre": f.nombre}


def borrar_foto(db: Session, user: Usuario, producto_id: int, foto_id: int) -> None:
    exigir(user, "producto.ficha")
    p = _producto(db, user, producto_id)
    f = next((x for x in p.fotos if x.id == foto_id), None)
    if not f:
        raise ErrorNegocio("The photo does not exist.", 404, "no_encontrado")
    nombre = f.nombre
    p.fotos.remove(f)
    adjuntos.quitar(db, f)
    registrar(db, user, "producto", p.id, "foto_quitada", {"foto": nombre})


def obtener_foto(db: Session, user: Usuario, foto_id: int) -> ProductoFoto:
    f = db.get(ProductoFoto, foto_id)
    if not f:
        raise ErrorNegocio("The photo does not exist.", 404, "no_encontrado")
    _producto(db, user, f.producto_id)
    return f


# ---- Fichas técnicas (SDS, TDS, COA): evidencia técnica, no fuente arancelaria ----------
def _doc_dict(d: ProductoDocumento) -> dict:
    return {"id": d.id, "tipo": d.tipo, "tipo_txt": listas.nombre("tipo_documento", d.tipo), "nombre": d.nombre, "emisor": d.emisor,
            "fecha_documento": d.fecha_documento, "datos": d.datos or {}, "subido_en": d.subido_en}


def subir_documento(db: Session, user: Usuario, producto_id: int, tipo: str, nombre: str, mime: str, contenido: bytes,
                    datos: dict | None = None, emisor: str | None = None, fecha=None) -> dict:
    """Adjunta una SDS, TDS o COA. Sus datos técnicos (CAS, composición, estado
    físico, densidad, pH…) completan los hechos de la ficha que estén vacíos;
    nunca aportan un código, DAI, impuesto ni regulación."""
    from app.modulos.productos.ficha import catalogo

    exigir(user, "producto.ficha")
    p = _producto(db, user, producto_id)
    tipo = (tipo or "").upper()
    if tipo not in listas.codigos("tipo_documento"):
        raise ErrorNegocio(f"Choose the kind of document: {', '.join(listas.codigos('tipo_documento'))}.", 422, "validacion")
    exigir_tamano(contenido)
    mime = MIME.get("pdf" if TIPOS["pdf"][1](contenido) else tipo_imagen(contenido) or "")
    if mime not in TIPOS_DOC:
        raise ErrorNegocio("Upload a PDF or an image of the document.", 422, "validacion")
    datos = {str(k).strip(): v for k, v in (datos or {}).items() if v not in (None, "", [])}
    arancel = sorted(k for k in datos if k.lower() in NO_ARANCEL)
    if arancel:
        raise ErrorNegocio(f"{tipo} documents are technical evidence, not a tariff source: {', '.join(arancel)} cannot be taken from them.",
                           422, "no_es_fuente_arancelaria")
    cat = catalogo(db)
    datos = {cat.canonico(k): v for k, v in datos.items()}  # un alias (CAS de otro paquete…) llega a su atributo
    desconocidos = sorted(k for k in datos if k not in cat.por_codigo)
    if desconocidos:
        raise ErrorNegocio(f"These are not attributes of the technical sheet: {', '.join(desconocidos)}.", 422, "validacion")
    seguro = adjuntos.nombre_seguro(nombre, "document")
    adj = adjuntos.crear(db, user, seguro, contenido, os.path.join("productos", str(p.id), "documentos"), TIPOS_DOC[mime], mime)
    d = ProductoDocumento(tipo=tipo, adjunto=adj, datos=datos, emisor=(emisor or "").strip()[:200] or None,
                          fecha_documento=fecha)
    p.documentos.append(d)
    db.flush()
    registrar(db, user, "producto", p.id, "documento_agregado", {"tipo": tipo, "documento": seguro, "datos": sorted(datos)})
    return _doc_dict(d)


def borrar_documento(db: Session, user: Usuario, producto_id: int, doc_id: int) -> None:
    exigir(user, "producto.ficha")
    p = _producto(db, user, producto_id)
    d = next((x for x in p.documentos if x.id == doc_id), None)
    if not d:
        raise ErrorNegocio("The document does not exist.", 404, "no_encontrado")
    tipo, nombre = d.tipo, d.nombre
    p.documentos.remove(d)
    adjuntos.quitar(db, d)
    registrar(db, user, "producto", p.id, "documento_quitado", {"tipo": tipo, "documento": nombre})


def obtener_documento(db: Session, user: Usuario, doc_id: int) -> ProductoDocumento:
    d = db.get(ProductoDocumento, doc_id)
    if not d:
        raise ErrorNegocio("The document does not exist.", 404, "no_encontrado")
    _producto(db, user, d.producto_id)
    return d


# ---- Lo que aprende el clasificador ----------------------------------------------
def ensenar_inciso(db: Session, user: Usuario, datos) -> dict:
    """Recordar una línea nacional para productos parecidos: conocimiento de la
    empresa (no crea ni modifica líneas oficiales)."""
    from app.modulos.clasificacion import conocimiento

    return conocimiento.ensenar(db, user, datos.pais, datos.codigo, datos.cond, datos.nota)


def ensenar_palabra(db: Session, user: Usuario, datos) -> dict:
    exigir(user, "producto.clasificar")
    frase = (datos.frase or "").strip().lower()[:100]
    if len(frase) < 3 or not datos.tipo:
        raise ErrorNegocio("Enter a phrase of at least 3 characters and its product type.", 422, "validacion")
    x = db.scalar(select(PalabraClave).where(func.lower(PalabraClave.frase) == frase,
                                             PalabraClave.marca.is_(None) if not datos.marca else PalabraClave.marca == datos.marca))
    if not x:
        x = PalabraClave(frase=frase, creado_por=user.id)
        db.add(x)
    x.tipo = datos.tipo[:30]
    x.marca = (datos.marca or None) and datos.marca[:100]
    x.atributos = {k: v for k, v in (datos.atributos or {}).items() if v not in (None, "")}
    db.flush()
    return {"id": x.id}


def ensenar_sinonimo(db: Session, user: Usuario, datos) -> dict:
    exigir(user, "producto.ficha")
    palabra = (datos.palabra or "").strip().lower()[:60]
    if len(palabra) < 3 or not datos.equivale:
        raise ErrorNegocio("Enter the word and what it means.", 422, "validacion")
    x = db.scalar(select(SinonimoMaterial).where(SinonimoMaterial.palabra == palabra))
    if not x:
        x = SinonimoMaterial(palabra=palabra, creado_por=user.id)
        db.add(x)
    x.equivale = datos.equivale[:30]
    db.flush()
    return {"id": x.id}


# ---- Base de códigos nacionales -------------------------------------------------
def notas_contexto(db: Session) -> list[dict]:
    """Notas activas con la capa custom aplicada (el texto oficial no se edita)."""
    from app.modulos.clasificacion.aranceles import notas_vigentes

    return [{k: n[k] for k in ("id", "ambito", "codigo", "numero", "texto", "capitulos", "claves", "oficial", "tipo_fuente")}
            for n in notas_vigentes(db)]


def notas_de(db: Session, codigo: str | None) -> list:
    """Notas legales que aplican a una subpartida: las reglas generales, las de
    su sección y las de su capítulo."""
    from types import SimpleNamespace

    from app.modulos.clasificacion.aranceles import notas_vigentes

    cap = (codigo or "")[:2]
    return [SimpleNamespace(**n) for n in notas_vigentes(db) if not n["capitulos"] or cap in n["capitulos"]]


# ---- Proveedores y catálogos para la pantalla -------------------------------------
def opciones(db: Session, user: Usuario) -> dict:
    exigir(user, "producto.ver")
    prov = proveedor_filtro(user)
    provs = db.scalars(select(Proveedor).where(Proveedor.activo.is_(True)).order_by(Proveedor.nombre)).all()
    return {
        "proveedores": [{"id": x.id, "nombre": x.nombre} for x in provs if not prov or x.id in prov],
        "marcas": [{"id": m.id, "codigo": m.codigo, "nombre": m.nombre} for m in db.scalars(select(Marca).order_by(Marca.codigo))],
        # Los atributos de producto de la empresa: una columna de la lista por cada uno
        "atributos": [{"codigo": a.codigo, "nombre": a.nombre, "catalogo": a.catalogo} for a in var_svc.atributos(db, "PRODUCTO")],
        "estados": ESTADOS,
        "paises": [{"codigo": x.codigo, "nombre": x.nombre} for x in db.scalars(select(Pais).order_by(Pais.nombre))],
    }


def etiquetas_ficha(db: Session) -> dict:
    """Etiquetas del catálogo para mostrar una ficha en documentos (atributos,
    opciones, partes de la composición, categorías) y el orden de los países:
    los documentos no traen nombres fijos de ninguna familia."""
    from app.modulos.productos.ficha import catalogo

    cat = catalogo(db)
    return {"campos": {a.codigo: a.etiqueta for a in cat.atributos},
            "valores": {a.codigo: {o.codigo: o.etiqueta for o in a.opciones} for a in cat.atributos if a.opciones},
            "partes": {a.codigo[5:]: a.etiqueta for a in cat.atributos if a.codigo.startswith("comp.")},
            "tipos": {c.codigo: c.nombre_corto or c.nombre for c in cat.categorias.values()},
            "paises": [p.iso for p in db.scalars(select(PaisArancel).order_by(PaisArancel.orden, PaisArancel.iso))],
            "aduana": aduana.nombres(db)}


def ficha_de_version(db: Session, user: Usuario, producto_id: int, version: int | None = None) -> dict:
    """La ficha vigente o, con `version`, la copia cerrada de una versión anterior."""
    d = {**detalle(db, user, producto_id), "etiquetas": etiquetas_ficha(db)}
    if not version or version == d["version_ficha"]:
        return d
    p = _producto(db, user, producto_id)
    v = next((x for x in p.versiones if x.version == version), None)
    if not v:
        raise ErrorNegocio(f"Version {version} does not exist.", 404, "no_encontrado")
    x = v.datos or {}
    partidas = x.get("partidas") or {}
    d = {**d, "version_ficha": v.version, "tipo": x.get("tipo"), "ficha": x.get("ficha") or {},
            "codigo": fmt_codigo(x.get("codigo")) if x.get("codigo") else None,
            "sugerido": fmt_codigo(x.get("sugerido")) if x.get("sugerido") else None,
            "estado": x.get("estado"), "estado_txt": ESTADOS.get(x.get("estado"), x.get("estado")),
            "descripcion_aduana": x.get("descripcion_aduana"), "descripcion_comercial": x.get("descripcion_comercial"),
            "pais_origen": x.get("pais_origen"), "analisis": x.get("analisis") or {}, "confianza": x.get("confianza"),
            "partidas": {k: (c if isinstance(c, dict) else {"codigo": c}) for k, c in partidas.items()},
            "revisado_por": x.get("revisado_por"), "revisado_en": x.get("revisado_en"), "observaciones": None,
            "vigencia": {"desde": v.desde, "hasta": v.hasta, "motivo": v.motivo}, "historica": True}
    if not flujo.ve_sugerencia(db, user) and x.get("estado") not in APROBADOS:
        flujo.ocultar_resumen(d)
    return d


def ver_version(db: Session, user: Usuario, producto_id: int, version: int) -> dict:
    from app.modulos.documentos import documentos
    d = ficha_de_version(db, user, producto_id, version)
    return {"version": d["version_ficha"], "vigencia": d.get("vigencia"), "estado_txt": d.get("estado_txt"),
            **documentos.secciones_ficha(d)}


def exportar_ficha(db: Session, user: Usuario, producto_id: int, formato: str = "pdf",
                   version: int | None = None) -> tuple[bytes, str]:
    from app.modulos.acceso import visibilidad
    from app.modulos.documentos import documentos, exportar
    d = visibilidad.quitar(ficha_de_version(db, user, producto_id, version))  # sin lo que el rol no ve
    nombre = f"ficha_{re.sub(r'[^A-Za-z0-9._-]+', '_', d['codigo_generico'] or str(d['id']))}" + (
        f"_v{d['version_ficha']}" if version else "")
    if formato == "xlsx":
        return exportar.exportar_ficha(d, documentos.secciones_ficha(d)), nombre
    return documentos.pdf_ficha_producto(d), nombre


def exportar_lista(db: Session, user: Usuario, filtros: dict, orden: str | None, formato: str,
                   por_columna: dict | None = None) -> bytes:
    """Reporte de productos con su composición, descripción aduanal y el
    código nacional guardado para cada país destino (con los filtros de la
    lista, también los de cada columna)."""
    from app.modulos.documentos import documentos, exportar
    r = listar(db, user, filtros, 1, 100_000, orden, por_columna)
    k = r["kpis"]
    indicadores = [("Products", f"{k['total']:,}"), ("Drafts", f"{k['borradores']:,}"), ("In review", f"{k['revision']:,}"),
                   ("Returned", f"{k['observado']:,}"), ("Approved", f"{k['aprobados']:,}")]
    ids = [p["id"] for p in r["items"]]
    prods = {p.id: p for p in db.scalars(select(Producto).where(Producto.id.in_(ids))
                                         .options(selectinload(Producto.partidas)))} if ids else {}
    paises = [d["iso"] for d in destinos(db)]
    nombre_parte = etiquetas_ficha(db)["partes"]

    def comp(p: Producto | None) -> str:
        c = ((p.comex.ficha or {}).get("comp") or {}) if p else {}
        return " · ".join(f"{nombre_parte.get(k) or documentos._legible(k)}: {v}" for k, v in c.items() if v) if isinstance(c, dict) else ""

    def codigos(p: Producto | None) -> dict:
        return {x.pais: fmt_codigo(x.codigo) for x in (p.partidas if p else []) if x.codigo}

    nombres = {"q": "Search", "estado": "Status", "tipo": "Type", "proveedor_id": "Supplier", "familia": "Family",
               "producto": "Product", "generico": "Product code", "proveedor": "Supplier", "codigo": "HS code",
               "origen": "Origin"}
    nombres.update({f"atr.{k}": v for k, v in var_svc.nombres(db).items()})
    columnas_validas = _columnas_productos(db, user)
    de_columnas = [(c, ", ".join("—" if x == tabla.VACIO else x for x in v))
                   for c, v in (por_columna or {}).items() if c in columnas_validas]
    texto = " · ".join(f"{nombres.get(c, c)}: {v}" for c, v in [*filtros.items(), *de_columnas] if v not in (None, ""))
    texto = f"Filters: {texto}" if texto else "No filters"
    titulo, sub = "Products and tariff classification", "Technical sheets, composition, HS codes and national codes by destination"
    if formato == "pdf":
        columnas = [("Product code", 1, False), ("Name", 2.1, False), ("Supplier", 1, False), ("Type", 0.8, False),
                    ("Status", 0.8, False), ("HS code", 0.8, False), ("Origin", 0.5, False), ("Composition", 2.6, False)] \
            + [(iso, 1, False) for iso in paises]
        filas = []
        for p in r["items"]:
            cods = codigos(prods.get(p["id"]))
            filas.append([p["codigo_generico"] or "—", p["nombre"] or "—", p["proveedor"] or "—", p["tipo"] or "—", p["estado_txt"],
                          p["codigo"] or "—", p["pais_origen"] or "—", comp(prods.get(p["id"])) or "—"]
                         + [cods.get(iso, "—") for iso in paises])
        return documentos.pdf_reporte(titulo, sub, texto, indicadores, columnas, [[str(v) for v in f] for f in filas])
    columnas = [("Product code", 1, False), ("Name", 1.8, False), ("Attributes", 2.4, False), ("Supplier", 1.2, False), ("Type", 0.9, False), ("Status", 0.9, False), ("Version", 0.6, True), ("HS code", 0.9, False),
                ("Suggested", 0.9, False), ("Origin", 0.6, False), ("Customs description", 4, False),
                ("Commercial description", 1.8, False), ("Composition", 4, False)] \
        + [(f"Code {iso}", 1.4, False) for iso in paises] + [("SKUs", 0.5, True)]
    filas, partes, codigos_filas = [], [], []
    for p in r["items"]:
        pr = prods.get(p["id"])
        cods = codigos(pr)
        filas.append([p["codigo_generico"] or "—", p["nombre"] or "—", var_svc.texto(p["atributos"]) or "—", p["proveedor"] or "—",
                      p["tipo"] or "—", p["estado_txt"], pr.comex.version_ficha if pr else 1, p["codigo"] or "—",
                      p["sugerido"] or "—", p["pais_origen"] or "—", (pr.comex.descripcion_aduana if pr else None) or "—",
                      p.get("descripcion_comercial") or "—", comp(pr) or "—"]
                     + [cods.get(iso, "—") for iso in paises] + [p["skus"]])
        c = ((pr.comex.ficha or {}).get("comp") or {}) if pr else {}
        for parte, materiales in (c.items() if isinstance(c, dict) else []):
            if materiales:
                partes.append([p["codigo_generico"] or "—", p["nombre"] or "—", nombre_parte.get(parte) or documentos._legible(parte),
                               str(materiales)])
        for x in (pr.partidas if pr else []):
            codigos_filas.append([p["codigo_generico"] or "—", p["nombre"] or "—", x.pais, fmt_codigo(x.codigo) or "—",
                                  f"{x.dai}%" if x.dai not in (None, "") else "—", documentos.ESTADO_PARTIDA.get(x.estado, x.estado or "—"),
                                  "By hand" if x.manual else (x.fuente or "—").capitalize()])
    hojas = [
        {"titulo": "Composition", "columnas": [("Product code", 1, False), ("Name", 2.4, False),
                                               ("Part", 1.6, False), ("Materials", 5, False)], "filas": partes},
        {"titulo": "National codes", "columnas": [("Product code", 1, False), ("Name", 2.4, False),
                                                  ("Country", 0.7, False), ("Code", 1.6, False),
                                                  (aduana.titulo_derecho(aduana.nombres(db)), 0.9, False),
                                                  ("Status", 0.9, False), ("Source", 0.9, False)], "filas": codigos_filas},
    ]
    return exportar.exportar_reporte(titulo, sub, texto, indicadores, columnas, filas, hojas)


# La ficha del producto se edita en exclusiva (comun/edicion.py): el producto y sus partes
edicion.registrar_documento(
    "producto", Producto,
    {Producto: lambda db, o: o.id, PartidaPais: lambda db, o: o.producto_id, ProductoFoto: lambda db, o: o.producto_id,
     ProductoDocumento: lambda db, o: o.producto_id},
    lambda db, user, producto_id: _producto(db, user, producto_id))
