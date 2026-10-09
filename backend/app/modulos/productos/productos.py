"""Productos: ficha técnica y clasificación arancelaria.

Un producto es el estilo-color de un proveedor. Sus tallas (artículos) y sus
prepacks comparten la ficha técnica, la partida SAC aprobada y el código
nacional de cada país destino; de aquí los toman la OC y la factura.

La clasificación la hace el motor único del servidor (motor_clasificacion):
la ficha, el guardado, la clasificación masiva y la aprobación pasan por él;
aquí se guarda lo que calcula, se valida lo que se aprueba y se lleva el
historial y la evidencia. Aprobar y enseñar códigos es del equipo interno; la
ficha la puede completar el proveedor.
"""
import os
import re
import uuid
from datetime import date, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.core.empresa import regla
from app.core.errores import ErrorNegocio
from app.modelos import (
    Articulo,
    ControlCapitulo,
    GrupoArticulo,
    Historial,
    IncisoNacional,
    Marca,
    Pais,
    PaisArancel,
    PalabraClave,
    PartidaPais,
    Prepack,
    Producto,
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
from app.modulos.comun.edicion import ajeno as ajeno_edicion
from app.modulos.comun.historial import registrar, tocar, verificar_version
from app.modulos.comun.texto import filtro_texto
from app.modulos.maestros.acuerdos import acuerdos_contexto
from app.modulos.productos import flujo


# Países destino y dígitos de su código nacional (Centroamérica y Panamá)
# Países destino de fábrica; en la base se pueden agregar otros y cambiar sus dígitos
def destinos(db: Session) -> list[dict]:
    """Países destino activos con su arancel (configuración del país; sin
    países cargados no hay destinos: no se inventan)."""
    filas = db.scalars(select(PaisArancel).where(PaisArancel.activo.is_(True))
                       .order_by(PaisArancel.orden, PaisArancel.iso)).all()
    return [{"iso": x.iso, "nombre": x.nombre, "digitos": x.digitos, "mcca": x.mcca, "impuesto": x.impuesto,
             "base_legal": x.base_legal} for x in filas]


def digitos_pais(db: Session) -> dict:
    return {d["iso"]: d["digitos"] for d in destinos(db)}
# Borrador (incompleto o completo) → enviado a revisión → aprobado o devuelto.
# Mientras es borrador, lo edita cualquiera con permiso; enviado queda
# cerrado para el proveedor hasta que se apruebe o se devuelva.
ESTADOS = {"borrador": "Draft", "sugerida": "Draft · complete", "revision": "In review", "aprobado": "Approved",
           "corregido": "Corrected", "observado": "Returned"}
APROBADOS = ("aprobado", "corregido")
BORRADORES = ("borrador", "sugerida", "observado")
PENDIENTES = BORRADORES + ("revision",)
TIPOS_FOTO = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
TIPOS_DOC = {"application/pdf": ".pdf", "image/jpeg": ".jpg", "image/png": ".png"}
# Campos que una ficha técnica nunca aporta: el arancel solo sale de fuentes oficiales
NO_ARANCEL = {"hs", "hs6", "hs_code", "codigo", "code", "tariff", "tariff_code", "dai", "sac", "partida", "inciso", "impuesto", "tax",
              "regulacion", "regulation"}


def digitos(s) -> str:
    return re.sub(r"\D", "", str(s or ""))


def fmt_codigo(c) -> str:
    d = digitos(c)
    if len(d) <= 4:
        return d
    o = d[:4] + "." + d[4:6]
    for i in range(6, len(d), 2):
        o += "." + d[i:i + 2]
    return o


# ---- Producto de cada artículo ------------------------------------------------
def producto_de(a: Articulo | None) -> Producto | None:
    """Producto que da la clasificación a un artículo. Un prepack no se
    clasifica: se arma con sólidos y toma la ficha de ellos."""
    if not a:
        return None
    if a.tipo == "PREPACK" and a.prepack:
        for c in a.prepack.componentes:
            if c.articulo and c.articulo.producto:
                return c.articulo.producto
    return a.producto


def ids_bloquean_facturas(db: Session, prov: int | None = None) -> set[int]:
    """Productos sin clasificación aprobada que dejan una factura en curso sin
    partida (no se puede finalizar hasta aprobarlos)."""
    from app.modelos import Factura, FacturaLinea, PosicionOC
    from app.modulos.facturacion.estados import EDITABLE_FACTURA

    consulta = (select(FacturaLinea).join(Factura).where(Factura.estado.in_(EDITABLE_FACTURA),
                                                         or_(FacturaLinea.partida_arancelaria.is_(None),
                                                             FacturaLinea.partida_arancelaria == ""))
                .options(selectinload(FacturaLinea.posicion_oc).selectinload(PosicionOC.articulo)))
    if prov:
        consulta = consulta.where(Factura.proveedor_id == prov)
    ids = set()
    for linea in db.scalars(consulta):
        prod = producto_de(linea.posicion_oc.articulo if linea.posicion_oc else None)
        if prod and not prod.aprobado:
            ids.add(prod.id)
    return ids


# Códigos de artículo y de genérico: el formato lo define cada empresa
# (numérico o alfanumérico, con punto, guion, barra o guion bajo)
RE_CODIGO = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._\-/]{0,39}$")
MSG_CODIGO = "Letters and numbers (also . - _ /), up to 40 characters."


def sin_marca(texto: str | None, marca: str | None = None) -> str | None:
    """Descripción aduanera sin la marca: la marca va en su propio campo en la
    factura y el packing list, así no se repite."""
    if not texto:
        return texto
    t = re.sub(r"[,;]?\s*\bMARCA\s+[^,;]+", "", str(texto), flags=re.I)
    for m in [x for x in {marca or ""} if x.strip()]:
        t = re.sub(rf"[,;]?\s*\b{re.escape(m.strip())}\b", "", t, flags=re.I)
    return re.sub(r"\s{2,}", " ", t).strip(" ,;") or None


def codigo_valido(valor: str | None) -> bool:
    return bool(RE_CODIGO.match(str(valor or "").strip()))


def generico_auto(estilo: str | None, color: str | None) -> str | None:
    """Genérico cuando la empresa no usa uno propio: estilo-color."""
    base = "-".join(x for x in (str(estilo or "").strip(), str(color or "").strip()) if x).upper()
    base = re.sub(r"[^A-Z0-9._\-/]+", "-", base).strip("-")
    return base[:40] or None


def generico_de(a) -> str | None:
    """Genérico (estilo-color) de un artículo o de una fila de datos."""
    if a is None:
        return None
    if isinstance(a, dict):
        return (str(a.get("generico") or "").strip().upper() or generico_auto(a.get("estilo"), a.get("color")))
    return a.generico or (a.producto.codigo_generico if a.producto else None) or generico_auto(a.estilo, a.color)


def producto_por_generico(db: Session, gen: str | None) -> Producto | None:
    return db.scalar(select(Producto).where(Producto.codigo_generico == gen)) if gen else None


def asegurar_producto(db: Session, a: Articulo) -> Producto | None:
    """Liga el artículo con el producto de su genérico (estilo-color); lo crea
    si no existe. Sólidos y prepacks del mismo genérico comparten la
    ficha técnica y la clasificación: el prepack no se clasifica aparte."""
    explicito = a.generico
    gen = generico_de(a)
    p = producto_por_generico(db, gen)
    if not p and a.tipo == "PREPACK":
        p = producto_de(a) if a.prepack else None
    if not p and a.proveedor_id and a.estilo:
        # Datos anteriores sin genérico: por proveedor, estilo y color
        p = db.scalar(select(Producto).where(Producto.proveedor_id == a.proveedor_id, Producto.estilo == a.estilo,
                                             Producto.color.is_(None) if a.color is None else Producto.color == a.color,
                                             *([or_(Producto.codigo_generico.is_(None), Producto.codigo_generico == gen)]
                                               if explicito else [])))
    if not p:
        if not a.proveedor_id or not a.estilo:
            return None
        p = Producto(proveedor_id=a.proveedor_id, estilo=a.estilo, color=a.color, marca_id=a.marca_id,
                     grupo_id=a.grupo_id, unidad=a.unidad if a.tipo == "SOLIDO" else None, ficha={}, faltan=[],
                     alertas_ok=[])
        db.add(p)
    if gen and not p.codigo_generico:
        p.codigo_generico = gen
    p.marca_id = p.marca_id or a.marca_id
    p.grupo_id = p.grupo_id or a.grupo_id
    if a.tipo == "SOLIDO" and not p.unidad:
        p.unidad = a.unidad
    db.flush()
    a.producto = p
    if not a.generico:
        a.generico = p.codigo_generico
    if not p.descripcion_comercial and not (p.ficha or {}).get("comManual"):
        p.descripcion_comercial = descripcion_comercial_simple(p)
    return p


def descripcion_comercial_simple(p: Producto) -> str | None:
    """Descripción comercial de factura y packing list: tipo y marca (p. ej.
    CALZADO VANS), con la plantilla de la categoría (la misma del motor)."""
    from sqlalchemy.orm import object_session

    from app.modulos.productos.descripciones import descripcion_comercial
    from app.modulos.productos.ficha import catalogo

    db = object_session(p)
    if not p.tipo or db is None:
        return None
    cat = catalogo(db)
    c = cat.categorias.get(p.tipo)
    if not c:
        return None
    s = cat.hechos_base(dict(p.ficha or {}), p.tipo, c.dominio)
    cat.normalizar(s)
    return descripcion_comercial(cat, s, c, p.marca.nombre if p.marca else None)[:300] or None


def partida_para(p: Producto | None) -> str | None:
    """Código que va en la OC y la factura: la subpartida de 6 dígitos (SA)
    aprobada. El país destino de la OC es solo una proyección de a dónde irá
    la mercancía, no el destino real, así que nunca se usa la línea nacional
    de un país ni el SAC regional."""
    if not p or not p.aprobado:
        return None
    d = digitos(p.codigo)
    return fmt_codigo(d[:6]) if len(d) >= 6 else None


def clasificacion_txt(p: Producto | None) -> dict:
    """Resumen corto para mostrar junto al artículo en la OC o la factura."""
    if not p:
        return {"estado": None, "texto": "No product"}
    return {"estado": p.estado, "texto": ESTADOS.get(p.estado, p.estado), "producto_id": p.id,
            "codigo": fmt_codigo(p.codigo) if p.aprobado else None,
            "sugerido": fmt_codigo(p.sugerido) if p.sugerido and not p.aprobado else None}


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
        fila.dai = str(x.get("dai") or "")[:10] or None
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


def _resumen(p: Producto, tallas: dict, ds: list[dict]) -> dict:
    ok, total = _paises_completos(p, ds)
    foto = p.fotos[0].id if p.fotos else None
    t = tallas.get(p.id, {})
    return {
        "id": p.id, "estilo": p.estilo, "color": p.color, "nombre": p.nombre, "codigo_generico": p.codigo_generico,
        "proveedor_id": p.proveedor_id, "proveedor": p.proveedor.nombre if p.proveedor else None,
        "marca": p.marca.codigo if p.marca else None, "marca_nombre": p.marca.nombre if p.marca else None,
        "grupo": p.grupo.codigo if p.grupo else None, "tipo": p.tipo, "estado": p.estado,
        "estado_txt": ESTADOS.get(p.estado, p.estado),
        "codigo": fmt_codigo(p.codigo) if p.codigo else None, "sugerido": fmt_codigo(p.sugerido) if p.sugerido else None,
        "sac_codigo": fmt_codigo(p.sac_codigo) if p.sac_codigo else None, "sac_sugerido": fmt_codigo(p.sac_sugerido) if p.sac_sugerido else None,
        "propuesta": fmt_codigo(p.propuesta) if p.propuesta else None,
        "confianza": p.confianza, "ficha_completa": p.ficha_completa, "faltan": p.faltan or [],
        "paises_ok": ok, "paises_total": total, "foto_id": foto, "pais_origen": p.pais_origen,
        "tallas": t.get("tallas", []), "rango_tallas": rango_tallas(t.get("tallas", [])), "skus": t.get("skus", 0),
        "n_prepacks": t.get("prepacks", 0),
        "unidad": t.get("unidad"), "descripcion_comercial": p.descripcion_comercial,
        "actualizado_en": p.actualizado_en, "version": p.version, "version_ficha": p.version_ficha,
    }


ORDEN_LETRAS = ["XXXS", "XXS", "XS", "S", "M", "L", "XL", "XXL", "XXXL", "4XL", "5XL"]
EQUIV_LETRAS = {"2XS": "XXS", "3XS": "XXXS", "2XL": "XXL", "3XL": "XXXL", "XXXXL": "4XL"}


def rango_tallas(tallas: list[str]) -> str:
    """Tallas en texto corto: tramos seguidos como "7 to 10" y los saltos
    separados por comas ("7 to 9, 11"); igual con S, M, L…"""
    ts = [str(t).strip().upper() for t in tallas if str(t or "").strip()]
    if not ts:
        return ""

    def tramos(valores: list, paso, texto) -> str:
        grupos, actual = [], [valores[0]]
        for v in valores[1:]:
            if abs((v - actual[-1]) - paso) < 1e-9:
                actual.append(v)
            else:
                grupos.append(actual)
                actual = [v]
        grupos.append(actual)
        out = []
        for g in grupos:
            if len(g) >= 3:
                out.append(f"{texto(g[0])}–{texto(g[-1])}")
            else:
                out += [texto(x) for x in g]
        return ", ".join(out)

    try:
        nums = sorted({float(t.replace(",", ".")) for t in ts})
        paso = 0.5 if any(not n.is_integer() for n in nums) else 1
        return tramos(nums, paso, lambda n: str(int(n)) if n.is_integer() else str(n))
    except ValueError:
        pass
    letras = [EQUIV_LETRAS.get(t, t) for t in ts]
    if all(t in ORDEN_LETRAS for t in letras):
        idx = sorted({ORDEN_LETRAS.index(t) for t in letras})
        return tramos(idx, 1, lambda i: ORDEN_LETRAS[i])
    return ", ".join(dict.fromkeys(ts))


def _tallas(db: Session, ids: list[int]) -> dict:
    out: dict[int, dict] = {}
    if not ids:
        return out
    for a in db.scalars(select(Articulo).where(Articulo.producto_id.in_(ids)).order_by(Articulo.id)):
        d = out.setdefault(a.producto_id, {"tallas": [], "skus": 0, "prepacks": 0, "unidad": None})
        if a.tipo == "PREPACK":
            d["prepacks"] += 1
            continue
        d["skus"] += 1
        if a.tipo == "SOLIDO" and a.talla:
            d["tallas"].append(a.talla)
        d["unidad"] = d["unidad"] or (a.unidad if a.tipo == "SOLIDO" else None)
    return out


ORDEN = {"estilo": Producto.estilo, "estado": Producto.estado, "actualizado": Producto.actualizado_en,
         "codigo": Producto.codigo, "tipo": Producto.tipo}


def listar(db: Session, user: Usuario, filtros: dict, page: int, size: int, orden: str | None) -> dict:
    exigir(user, "producto.ver")
    prov = proveedor_filtro(user, filtros.get("proveedor_id"))
    base = select(Producto)
    if prov:
        base = base.where(Producto.proveedor_id == prov)
    if filtros.get("marca_id"):
        ids = [int(x) for x in str(filtros["marca_id"]).split(",") if x.strip().isdigit()]
        base = base.where(Producto.marca_id.in_(ids))
    if filtros.get("grupo_id"):
        base = base.where(Producto.grupo_id == filtros["grupo_id"])
    if filtros.get("tipo"):
        base = base.where(Producto.tipo.in_(str(filtros["tipo"]).split(",")))
    if filtros.get("q"):
        base = base.where(filtro_texto(filtros["q"], lambda p: [
            Producto.estilo.ilike(p), Producto.color.ilike(p), Producto.nombre.ilike(p), Producto.codigo_generico.ilike(p),
            Producto.codigo.ilike(p.replace(".", "")),
            Producto.id.in_(select(Articulo.producto_id).where(or_(Articulo.sku.ilike(p), Articulo.upc.ilike(p))))]))
    # Indicadores por estado con los mismos filtros (menos el de estado)
    sub = base.subquery()
    conteo = {e: n for e, n in db.execute(select(sub.c.estado, func.count()).group_by(sub.c.estado)).all()}
    # Baja confianza legal: lo que el especialista debe mirar primero (no aplica si el proveedor no ve la sugerencia)
    baja = (db.scalar(select(func.count()).where(sub.c.estado.in_(PENDIENTES), sub.c.confianza == "low"))
            if flujo.ve_sugerencia(db, user) else None)
    estado = filtros.get("estado")
    bloquean = ids_bloquean_facturas(db, prov)
    if estado == "bloquean":
        base = base.where(Producto.id.in_(bloquean))
    elif estado == "pendientes":
        base = base.where(Producto.estado.in_(PENDIENTES))
    elif estado == "borradores":
        base = base.where(Producto.estado.in_(BORRADORES))
    elif estado == "aprobados":
        base = base.where(Producto.estado.in_(APROBADOS))
    elif estado == "baja_confianza" and baja is not None:
        base = base.where(Producto.estado.in_(PENDIENTES), Producto.confianza == "low")
    elif estado:
        base = base.where(Producto.estado == estado)
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    col, _, direccion = (orden or "actualizado:desc").partition(":")
    campo = ORDEN.get(col, Producto.actualizado_en)
    base = base.order_by(campo.desc() if direccion == "desc" else campo.asc(), Producto.id)
    filas = db.scalars(base.options(selectinload(Producto.partidas), selectinload(Producto.fotos))
                       .offset((page - 1) * size).limit(size)).all()
    tallas = _tallas(db, [p.id for p in filas])
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
    items = [_resumen(p, tallas, ds) for p in filas]
    # Para mostrar: el texto del código (árbol oficial o su override) y el nombre corto de la categoría
    from app.modulos.clasificacion.aranceles import textos_sac
    from app.modulos.productos.ficha import catalogo

    textos = textos_sac(db, list({digitos(p.codigo or p.sugerido)[:6] for p in filas if p.codigo or p.sugerido}))
    cats = catalogo(db).categorias
    for x, p in zip(items, filas):
        x["codigo_desc"] = textos.get(digitos(p.codigo or p.sugerido or "")[:6])
        c = cats.get(p.tipo or "")
        x["tipo_txt"] = (c.nombre_corto or c.nombre) if c else p.tipo
        if not flujo.ve_sugerencia(db, user) and not p.aprobado:
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
    pps = db.scalars(select(Prepack).where(Prepack.estilo == p.estilo, Prepack.color == p.color)).all()
    sku_pp = {a.prepack_id: a for a in arts if a.prepack_id}
    ds = destinos(db)
    dig = {d["iso"]: d["digitos"] for d in ds}
    r = _resumen(p, _tallas(db, [p.id]), ds)
    r.update({
        "ficha": p.ficha or {}, "descripcion_aduana": p.descripcion_aduana, "pais_procedencia": p.pais_procedencia,
        "marca_id": p.marca_id, "grupo_id": p.grupo_id,
        "analisis": p.analisis or {}, "alertas_ok": p.alertas_ok or [], "observaciones": p.observaciones,
        "resolucion": p.resolucion, "notas": p.notas, "opinion_ia": p.opinion_ia,
        "revisado_por": p.revisado_por.nombre if p.revisado_por else None, "revisado_en": p.revisado_en,
        "vigente_desde": p.vigente_desde, "creado_en": p.creado_en,
        "evidencia": p.evidencia,
        "partidas": {x.pais: {"codigo": x.codigo, "dai": x.dai or "", "estado": x.estado, "fuente": x.fuente,
                              "sugerido": x.sugerido, "motivo": x.motivo, "inciso_id": x.inciso_id, "evidencia": x.evidencia,
                              "aprobado_en": x.aprobado_en,
                              "manual": x.manual, "digitos": dig.get(x.pais, 10)} for x in p.partidas},
        "fotos": [{"id": f.id, "nombre": f.nombre} for f in p.fotos],
        "documentos": [_doc_dict(d) for d in p.documentos],
        "versiones": [{"version": v.version, "desde": v.desde, "hasta": v.hasta, "motivo": v.motivo,
                       "codigo": fmt_codigo(v.datos.get("codigo")) if v.datos.get("codigo") else None,
                       "estado": v.datos.get("estado"), "tipo": v.datos.get("tipo"), "cerrado_en": v.cerrado_en}
                      for v in reversed(p.versiones)],
        "articulos": [{"id": a.id, "sku": a.sku, "sku_proveedor": a.sku_proveedor, "upc": a.upc, "talla": a.talla, "unidad": a.unidad, "tipo": a.tipo,
                       "descripcion": a.descripcion, "activo": a.activo, "prepack_id": a.prepack_id} for a in arts],
        "prepacks": [{"id": x.id, "codigo": x.codigo, "descripcion": x.descripcion, "total": x.total,
                      "sku": sku_pp[x.id].sku if x.id in sku_pp else None,
                      "componentes": [{"talla": c.articulo.talla, "sku": c.articulo.sku, "cantidad": c.cantidad}
                                      for c in x.componentes]} for x in pps],
        "historial": _historial(db, p),
        "puede_aprobar": tiene(user, "producto.clasificar"),
        "enviado_por_mi": flujo.quien_envio(db, p.id) == user.id,
        "edicion": ajeno_edicion(db, user, "producto", p.id),
    })
    if not flujo.ve_sugerencia(db, user) and not p.aprobado:
        flujo.ocultar_resumen(r)
    return r


def _inciso_ctx(x: IncisoNacional) -> dict:
    return {"id": x.id, "pais": x.pais, "codigo": x.codigo, "cond": x.cond or {}, "prio": x.prio,
            "dai": x.dai or "", "descripcion": x.descripcion, "nota": x.nota, "fuente": x.fuente}


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


def entrada_producto(p: Producto, extra: dict | None = None) -> dict:
    """La ficha natural del producto para el motor único (la misma para la
    pantalla, el guardado, la aprobación y el lote)."""
    f = dict(p.ficha or {})
    return {"categoria": p.tipo, "ficha": f, "estilo": p.estilo, "nombre": p.nombre, "uso": f.get("uso"), "tallas": f.get("tallas"),
            "marca": p.marca.nombre if p.marca else None, "proveedor": p.proveedor.nombre if p.proveedor else None,
            "origen": p.pais_origen, "generico": p.codigo_generico, "producto_id": p.id, "alertas_ok": p.alertas_ok or [],
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
        p.tipo = r["categoria"]["codigo"][:30]
    p.ficha = r["ficha"]
    hs6, sac = r.get("hs6"), r["clasificacion"]["sac"]["codigo"]
    p.sugerido, p.sac_sugerido = hs6, sac
    p.confianza = r["confianza"]
    p.fuente = _fuente_motor(r) if hs6 else None
    p.perfil = (r.get("perfil") or "")[:200] or None
    legibles = [[c["etiqueta"], _valor_legible(c)] for c in r["campos"]
                if c["seccion"] in ("producto", "caracteristicas", "composicion", "nacional") and c["tipo_dato"] != "composition"
                and c.get("valor") not in (None, "", [], False)]
    p.analisis = {"razones": r["razones"], "alternativas": r["alternativas"][:20], "avisos": [a["texto"] for a in r["avisos"]][:20],
                  "faltantes": [f["etiqueta"] for f in r["faltantes"]][:20], "alertas": r["alertas"][:60], "revision_por": r["revision_por"][:20],
                  "requiere_revision": r["requiere_revision"], "atributos": legibles[:60],
                  "tipo_txt": (r.get("categoria") or {}).get("nombre"), "version": r.get("version")}
    if not (p.ficha or {}).get("descManual"):
        p.descripcion_aduana = (r["descripciones"]["aduana"] or "")[:400] or None
    if not (p.ficha or {}).get("comManual"):
        p.descripcion_comercial = (r["descripciones"]["comercial"] or "")[:300] or descripcion_comercial_simple(p)
    faltan = [f["etiqueta"] for f in r["faltantes"]]
    if not p.tipo:
        faltan.insert(0, "Product type")
    if not hs6:
        faltan.append("Data for the code")
    p.ficha_completa = not faltan
    p.faltan = [str(x)[:120] for x in faltan][:20]
    if p.estado not in APROBADOS:
        _guardar_partidas(p, {x["pais"]: {"codigo": x["codigo"], "dai": x["dai"], "estado": x["estado"], "fuente": x["fuente"],
                                          "manual": x["manual"]} for x in r["clasificacion"]["paises"]})
        if p.estado != "revision":
            p.estado = "sugerida" if p.ficha_completa and p.sugerido else "borrador"


def clasificar_y_guardar(db: Session, p: Producto, extra: dict | None = None, catalogo=None) -> dict:
    from app.modulos.clasificacion.motor_clasificacion import clasificar_producto

    r = clasificar_producto(db, entrada_producto(p, extra), catalogo=catalogo)
    _aplicar_motor(p, r)
    return r


def guardar_ficha(db: Session, user: Usuario, producto_id: int, datos) -> dict:
    exigir(user, "producto.ficha")
    p = _producto(db, user, producto_id)
    verificar_version(p, datos.version, "product")
    if p.estado in APROBADOS:
        raise ErrorNegocio("The technical sheet is approved. Create a new version to change it.", 409, "ficha_aprobada")
    if p.estado == "revision" and not tiene(user, "producto.clasificar"):
        raise ErrorNegocio("The technical sheet was sent to review. Take it back to draft to change it.", 409, "en_revision")
    antes = {"tipo": p.tipo, "ficha": p.ficha, "estado": p.estado}
    p.tipo = (datos.tipo or None) and datos.tipo[:30]
    p.ficha = datos.ficha or {}
    for campo, largo in CAMPOS_TEXTO.items():
        v = getattr(datos, campo, None)
        if v is not None:
            setattr(p, campo, str(v).strip()[:largo] or None)
    if datos.pais_origen is not None:
        p.pais_origen = (datos.pais_origen or "").upper()[:2] or None
    if datos.pais_procedencia is not None:
        p.pais_procedencia = (datos.pais_procedencia or "").upper()[:2] or None
    p.alertas_ok = list(datos.alertas_ok or [])[:100]
    # Códigos nacionales escritos a mano (se validan en el motor: existen o tienen una longitud válida)
    manuales = {iso: x for iso, x in (datos.partidas or {}).items() if isinstance(x, dict) and x.get("manual") and digitos(x.get("codigo"))}
    for x in list(p.partidas):
        if x.manual and x.pais not in manuales:
            p.partidas.remove(x)
    _guardar_partidas(p, {**{x.pais: {"codigo": x.codigo, "dai": x.dai, "estado": x.estado, "fuente": x.fuente, "manual": x.manual}
                             for x in p.partidas}, **{iso: {**x, "estado": "manual"} for iso, x in manuales.items()}})
    devuelto = p.estado == "observado"
    clasificar_y_guardar(db, p, {"tocados": list(datos.tocados or [])})
    if datos.descripcion_aduana is not None and (p.ficha or {}).get("descManual"):
        p.descripcion_aduana = datos.descripcion_aduana.strip()[:400] or None
    if datos.descripcion_comercial is not None and (p.ficha or {}).get("comManual"):
        p.descripcion_comercial = datos.descripcion_comercial.strip()[:300] or None
    tocar(p)
    cambios = [k for k in ("tipo", "ficha") if antes[k] != getattr(p, k)]
    registrar(db, user, "producto", p.id, "ficha_guardada",
              {"cambios": cambios, "estado": [antes["estado"], p.estado], "sugerido": fmt_codigo(p.sugerido) or None,
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
        if p.estado in APROBADOS:
            omitidos.append({"id": p.id, "mensaje": f"{p.estilo} is already approved."})
            continue
        antes = p.estado
        clasificar_y_guardar(db, p, {"detectar": True}, catalogo=cat)
        tocar(p)
        registrar(db, user, "producto", p.id, "clasificado", {"estado": [antes, p.estado], "sugerido": fmt_codigo(p.sugerido) or None})
        hechos += 1
    return {"clasificados": hechos, "omitidos": omitidos}


# ---- Aprobar, devolver y versiones -------------------------------------------
def _aprobar(db: Session, user: Usuario, p: Producto, codigo: str | None, partidas: dict | None, lote: bool = False) -> None:
    """Aprueba con el motor único: el código se vuelve a validar contra el árbol
    de la versión vigente y contra las reglas; cada país con su línea nacional
    de la versión vigente del país. Guarda la evidencia completa."""
    from app.modulos.clasificacion.motor_clasificacion import clasificar_producto

    oficial = digitos(codigo or p.propuesta or p.sac_sugerido or p.sugerido)
    if len(oficial) < 6:
        raise ErrorNegocio(f"{p.estilo}: there is no HS code to approve.", 422, "sin_partida")
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
        raise ErrorNegocio(f"{p.estilo}: " + " ".join(errores), 422, "capitulo_no_habilitado")
    if len(oficial) > 6 and r["sac"] != oficial:
        raise ErrorNegocio(f"{fmt_codigo(oficial)} is not an official SAC line of the tariff in force. "
                           "The product keeps its HS6 and each country chooses its own national line.", 422, "no_es_linea_sac")
    if errores:
        raise ErrorNegocio(f"{p.estilo}: " + " ".join(errores), 422, "codigo_invalido")
    paises = r["clasificacion"]["paises"]
    invalidos = [x for x in paises if x["estado"] == "invalido"]
    if invalidos:
        raise ErrorNegocio("; ".join(f"{x['pais']}: {x['error']}" for x in invalidos), 422, "codigo_nacional_invalido")
    # Con incertidumbre el caso queda pendiente: nunca se aprueba solo. En lote no se aprueba lo que pide revisión
    if lote and (r["requiere_revision"] or r["confianza"] == "low"):
        raise ErrorNegocio(f"{p.estilo}: needs a specialist review (" + "; ".join(r["revision_por"][:2] or ["low legal confidence"]) + ").",
                           422, "requiere_revision")
    # Las líneas nacionales son referencia (la OC y la factura llevan la subpartida de 6 dígitos):
    # aprobar no las exige. Una que solo el historial prefiere o que falta elegir queda pendiente
    # de confirmar por una persona (confirmar_partida), nunca se da por confirmada.
    sug = digitos(p.sugerido)
    p.estado = "aprobado" if not sug or sug[:6] == oficial[:6] else "corregido"
    p.codigo = oficial[:6]
    p.sac_codigo = oficial if len(oficial) > 6 else r["sac"]
    p.propuesta = None
    p.version_arancel_id = r["version"]["id"] if r.get("version") else None
    ahora_ = ahora()
    p.evidencia = {**r["evidencia"], "aprobacion": {"fecha": ahora_.isoformat(), "usuario": user.nombre if user else None, "hs6": p.codigo,
                                                    "sac": p.sac_codigo, "sugerido": sug or None, "confianza": r["confianza"],
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
    p.revisado_por_id = user.id if user else None
    p.revisado_en = ahora_
    # La decisión queda como conocimiento de la empresa (nunca como dato oficial):
    # el HS6 con la categoría y, por país, la línea oficial con los datos que la eligieron
    from app.modulos.clasificacion.conocimiento import registrar_decision

    origen = "APROBACION" if p.estado == "aprobado" else "CORRECCION"
    hechos = r.get("hechos") or {}
    registrar_decision(db, pais=None, codigo=p.sac_codigo or p.codigo, condiciones={}, origen=origen, categoria=p.tipo, producto_id=p.id, usuario=user)
    for x in paises:
        if x.get("estado") == "ok" and x.get("inciso_id") and x.get("codigo"):  # solo lo confirmado es conocimiento
            claves = {k for o in x.get("opciones") or [] for k in (o.get("cond") or {})} | set(x.get("faltan") or [])
            registrar_decision(db, pais=x["pais"], codigo=x["codigo"], condiciones={k: hechos.get(k) for k in claves if hechos.get(k) is not None},
                               origen=origen, categoria=p.tipo, producto_id=p.id, usuario=user)
    tocar(p)
    registrar(db, user, "producto", p.id, "aprobado" if p.estado == "aprobado" else "corregido",
              {"codigo": fmt_codigo(oficial), "sugerido": fmt_codigo(sug) or None,
               "paises": {x["pais"]: fmt_codigo(x["codigo"]) for x in paises if x.get("codigo")}})


def _pais_aprobado(db: Session, user: Usuario, producto_id: int, pais: str, codigo: str | None = None):
    from app.modulos.clasificacion.motor_clasificacion import clasificar_producto

    p = _producto(db, user, producto_id)
    if p.estado not in APROBADOS or not p.codigo:
        raise ErrorNegocio("Approve the product first: the national codes hang from its approved subheading.", 422, "no_aprobado")
    extra = {"codigo_final": p.sac_codigo or p.codigo}
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
    fila.codigo, fila.dai, fila.estado, fila.fuente, fila.manual = _codigo_fila(x["codigo"]), str(x.get("dai") or "")[:10] or None, "ok", \
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
                       origen="APROBACION", categoria=p.tipo, producto_id=p.id, usuario=user)
    tocar(p)
    registrar(db, user, "producto", p.id, "partida_confirmada", {"pais": pais, "codigo": [fmt_codigo(antes) or None, fmt_codigo(x["codigo"])]})
    return detalle(db, user, p.id)


def aprobar(db: Session, user: Usuario, producto_id: int, datos) -> dict:
    exigir(user, "producto.clasificar")
    p = _producto(db, user, producto_id)
    verificar_version(p, datos.version, "product")
    flujo.exigir_aprobacion(db, user, p)
    if not p.ficha_completa and not datos.forzar:
        raise ErrorNegocio("The technical sheet is incomplete: " + ", ".join(p.faltan[:4]) + ".", 422, "ficha_incompleta",
                           [{"mensaje": x} for x in p.faltan])
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
        if p.estado in APROBADOS:
            continue
        if p.estado not in ("sugerida", "revision") or not p.ficha_completa:
            errores.append({"id": p.id, "mensaje": f"{p.estilo} {p.color or ''}: the sheet is not complete.".replace(" :", ":")})
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
    p.observaciones = (datos.observaciones or "").strip()[:2000] or None
    p.resolucion = (datos.resolucion or "").strip()[:200] or None
    if datos.devolver:
        if p.estado in APROBADOS:
            raise ErrorNegocio("An approved sheet cannot be returned; create a new version.", 409, "ficha_aprobada")
        if not p.observaciones:
            raise ErrorNegocio("Write what the supplier has to fix.", 422, "motivo_requerido")
        p.estado = "observado"
    tocar(p)
    registrar(db, user, "producto", p.id, "devuelto" if datos.devolver else "observacion",
              {"observaciones": p.observaciones, "resolucion": p.resolucion})
    return detalle(db, user, p.id)


def enviar_revision(db: Session, user: Usuario, ids: list[int]) -> dict:
    """Envía fichas en borrador a revisión: deben estar completas y con partida."""
    exigir(user, "producto.ficha")
    ok, errores = 0, []
    for pid in ids:
        p = _producto(db, user, pid)
        nombre = f"{p.estilo} {p.color or ''}".strip()
        if p.estado not in BORRADORES:
            errores.append({"id": p.id, "mensaje": f"{nombre} is {ESTADOS.get(p.estado, p.estado).lower()}."})
            continue
        if not p.ficha_completa or not p.sugerido:
            falta = ", ".join((p.faltan or [])[:4]) or "the HS code"
            errores.append({"id": p.id, "mensaje": f"{nombre}: complete the sheet first ({falta})."})
            continue
        antes = p.estado
        p.estado = "revision"
        tocar(p)
        registrar(db, user, "producto", p.id, "enviado", {"estado": [antes, p.estado]})
        ok += 1
    if len(ids) == 1 and errores:
        raise ErrorNegocio(errores[0]["mensaje"], 422, "no_enviado", errores)
    return {"enviados": ok, "errores": errores}


def retirar_revision(db: Session, user: Usuario, producto_id: int) -> dict:
    """Vuelve a borrador una ficha enviada (para corregirla antes de que la revisen)."""
    exigir(user, "producto.ficha")
    p = _producto(db, user, producto_id)
    if p.estado != "revision":
        raise ErrorNegocio("Only a sheet in review can go back to draft.", 409, "estado")
    p.estado = "sugerida" if p.ficha_completa and p.sugerido else "borrador"
    tocar(p)
    registrar(db, user, "producto", p.id, "retirado", {"estado": ["revision", p.estado]})
    return detalle(db, user, p.id)


def nueva_version(db: Session, user: Usuario, producto_id: int, datos) -> dict:
    """Cierra la ficha vigente con su partida y abre una copia para editar."""
    exigir(user, "producto.ficha")
    p = _producto(db, user, producto_id)
    verificar_version(p, datos.version, "product")
    desde = datos.desde or date.today()
    inicio = p.vigente_desde or (p.creado_en.date() if p.creado_en else desde)
    if desde <= inicio and p.versiones:
        raise ErrorNegocio("The new version must start after the current one.", 422, "validacion")
    db.add(ProductoVersion(
        producto=p, version=p.version_ficha, desde=inicio, hasta=desde - timedelta(days=1), motivo=(datos.motivo or "")[:300] or None,
        # Autosuficiente para auditoría: ficha, clasificación, versión arancelaria,
        # evidencia (reglas con su foto, hechos, notas, overrides) y países con su línea
        datos={"tipo": p.tipo, "ficha": p.ficha, "nombre": p.nombre, "codigo": p.codigo, "sac_codigo": p.sac_codigo, "sugerido": p.sugerido,
               "sac_sugerido": p.sac_sugerido, "estado": p.estado, "descripcion_aduana": p.descripcion_aduana,
               "descripcion_comercial": p.descripcion_comercial, "pais_origen": p.pais_origen, "pais_procedencia": p.pais_procedencia,
               "analisis": p.analisis, "confianza": p.confianza, "fuente": p.fuente, "perfil": p.perfil,
               "version_arancel": ({"id": p.version_arancel_id, **((p.evidencia or {}).get("version") or {})} if p.version_arancel_id else None),
               "evidencia": p.evidencia, "observaciones": p.observaciones, "resolucion": p.resolucion,
               "partidas": {x.pais: {"codigo": x.codigo, "dai": x.dai, "estado": x.estado, "fuente": x.fuente, "manual": x.manual,
                                     "sugerido": x.sugerido, "motivo": x.motivo, "inciso_id": x.inciso_id, "version_id": x.version_id,
                                     "evidencia": x.evidencia, "aprobado_en": x.aprobado_en.isoformat() if x.aprobado_en else None}
                            for x in p.partidas},
               "revisado_por": p.revisado_por.nombre if p.revisado_por else None,
               "revisado_en": p.revisado_en.isoformat() if p.revisado_en else None},
        cerrado_por=user.id))
    p.version_ficha += 1
    p.vigente_desde = desde
    p.estado = "borrador"
    p.codigo = None
    p.revisado_por = None
    p.revisado_en = None
    p.partidas.clear()
    tocar(p)
    registrar(db, user, "producto", p.id, "nueva_version",
              {"version": p.version_ficha, "desde": desde.isoformat()}, motivo=datos.motivo)
    return detalle(db, user, p.id)


def guardar_opinion(db: Session, user: Usuario, producto_id: int, opinion: dict) -> None:
    p = _producto(db, user, producto_id)
    p.opinion_ia = opinion


# ---- Fotos ---------------------------------------------------------------------
def subir_foto(db: Session, user: Usuario, producto_id: int, nombre: str, tipo: str, contenido: bytes) -> dict:
    exigir(user, "producto.ficha")
    p = _producto(db, user, producto_id)
    if tipo not in TIPOS_FOTO:
        raise ErrorNegocio("Upload a JPG, PNG or WebP image.", 422, "validacion")
    if len(contenido) > 8 * 1024 * 1024:
        raise ErrorNegocio("The photo exceeds 8 MB.", 413, "archivo_grande")
    if len(p.fotos) >= 8:
        raise ErrorNegocio("A product can have up to 8 photos.", 422, "validacion")
    carpeta = os.path.join(settings.UPLOAD_DIR, "productos", str(p.id))
    os.makedirs(carpeta, exist_ok=True)
    ruta = os.path.join(carpeta, uuid.uuid4().hex + TIPOS_FOTO[tipo])
    with open(ruta, "wb") as fh:
        fh.write(contenido)
    seguro = "".join(c for c in os.path.basename(nombre or "photo") if c.isalnum() or c in "._- ")[:200] or "photo"
    f = ProductoFoto(nombre=seguro, ruta=ruta, tipo_mime=tipo, tamano=len(contenido), subido_por=user.id)
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
    p.fotos.remove(f)
    try:
        os.remove(f.ruta)
    except OSError:
        pass
    registrar(db, user, "producto", p.id, "foto_quitada", {"foto": f.nombre})


def obtener_foto(db: Session, user: Usuario, foto_id: int) -> ProductoFoto:
    f = db.get(ProductoFoto, foto_id)
    if not f:
        raise ErrorNegocio("The photo does not exist.", 404, "no_encontrado")
    _producto(db, user, f.producto_id)
    return f


# ---- Fichas técnicas (SDS, TDS, COA): evidencia técnica, no fuente arancelaria ----------
def _doc_dict(d: ProductoDocumento) -> dict:
    return {"id": d.id, "tipo": d.tipo, "tipo_txt": ProductoDocumento.TIPOS.get(d.tipo, d.tipo), "nombre": d.nombre, "emisor": d.emisor,
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
    if tipo not in ProductoDocumento.TIPOS:
        raise ErrorNegocio("Choose the kind of document: SDS, TDS or COA.", 422, "validacion")
    if mime not in TIPOS_DOC:
        raise ErrorNegocio("Upload a PDF or an image of the document.", 422, "validacion")
    if len(contenido) > 15 * 1024 * 1024:
        raise ErrorNegocio("The document exceeds 15 MB.", 413, "archivo_grande")
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
    carpeta = os.path.join(settings.UPLOAD_DIR, "productos", str(p.id), "documentos")
    os.makedirs(carpeta, exist_ok=True)
    ruta = os.path.join(carpeta, uuid.uuid4().hex + TIPOS_DOC[mime])
    with open(ruta, "wb") as fh:
        fh.write(contenido)
    seguro = "".join(c for c in os.path.basename(nombre or "document") if c.isalnum() or c in "._- ")[:200] or "document"
    d = ProductoDocumento(tipo=tipo, nombre=seguro, ruta=ruta, tipo_mime=mime, tamano=len(contenido), datos=datos,
                          emisor=(emisor or "").strip()[:200] or None, fecha_documento=fecha, subido_por=user.id)
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
    p.documentos.remove(d)
    try:
        os.remove(d.ruta)
    except OSError:
        pass
    registrar(db, user, "producto", p.id, "documento_quitado", {"tipo": d.tipo, "documento": d.nombre})


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
        "proveedores": [{"id": x.id, "nombre": x.nombre} for x in provs if not prov or x.id == prov],
        "marcas": [{"id": m.id, "codigo": m.codigo, "nombre": m.nombre} for m in db.scalars(select(Marca).order_by(Marca.codigo))],
        "grupos": [{"id": g.id, "codigo": g.codigo, "nombre": g.nombre} for g in db.scalars(select(GrupoArticulo).order_by(GrupoArticulo.codigo))],
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
            "paises": [p.iso for p in db.scalars(select(PaisArancel).order_by(PaisArancel.orden, PaisArancel.iso))]}


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
    nombre = f"ficha_{d['estilo']}_{digitos(d['color'])[:6] or d['id']}" + (f"_v{d['version_ficha']}" if version else "")
    if formato == "xlsx":
        return exportar.exportar_ficha(d, documentos.secciones_ficha(d)), nombre
    return documentos.pdf_ficha_producto(d), nombre


def exportar_lista(db: Session, user: Usuario, filtros: dict, orden: str | None, formato: str) -> bytes:
    """Reporte de productos con su composición, descripción aduanal y el
    código nacional guardado para cada país destino."""
    from app.modulos.documentos import documentos, exportar
    r = listar(db, user, filtros, 1, 100_000, orden)
    k = r["kpis"]
    indicadores = [("Products", f"{k['total']:,}"), ("Drafts", f"{k['borradores']:,}"), ("In review", f"{k['revision']:,}"),
                   ("Returned", f"{k['observado']:,}"), ("Approved", f"{k['aprobados']:,}")]
    ids = [p["id"] for p in r["items"]]
    prods = {p.id: p for p in db.scalars(select(Producto).where(Producto.id.in_(ids))
                                         .options(selectinload(Producto.partidas)))} if ids else {}
    paises = [d["iso"] for d in destinos(db)]
    nombre_parte = etiquetas_ficha(db)["partes"]

    def comp(p: Producto | None) -> str:
        c = ((p.ficha or {}).get("comp") or {}) if p else {}
        return " · ".join(f"{nombre_parte.get(k) or documentos._legible(k)}: {v}" for k, v in c.items() if v) if isinstance(c, dict) else ""

    def codigos(p: Producto | None) -> dict:
        return {x.pais: fmt_codigo(x.codigo) for x in (p.partidas if p else []) if x.codigo}

    nombres = {"q": "Search", "estado": "Status", "tipo": "Type", "proveedor_id": "Supplier", "marca_id": "Brand"}
    texto = " · ".join(f"{nombres.get(c, c)}: {v}" for c, v in filtros.items() if v not in (None, ""))
    texto = f"Filters: {texto}" if texto else "No filters"
    titulo, sub = "Products and tariff classification", "Technical sheets, composition, HS codes and national codes by destination"
    if formato == "pdf":
        columnas = [("Generic", 1, False), ("Style", 1, False), ("Color", 1.1, False), ("Supplier", 1, False), ("Type", 0.8, False),
                    ("Status", 0.8, False), ("HS code", 0.8, False), ("Origin", 0.5, False), ("Composition", 2.6, False)] \
            + [(iso, 1, False) for iso in paises]
        filas = []
        for p in r["items"]:
            cods = codigos(prods.get(p["id"]))
            filas.append([p["codigo_generico"] or "—", p["estilo"], p["color"], p["proveedor"] or "—", p["tipo"] or "—", p["estado_txt"],
                          p["codigo"] or "—", p["pais_origen"] or "—", comp(prods.get(p["id"])) or "—"]
                         + [cods.get(iso, "—") for iso in paises])
        return documentos.pdf_reporte(titulo, sub, texto, indicadores, columnas, [[str(v) for v in f] for f in filas])
    columnas = [("Generic", 1, False), ("Style", 1.1, False), ("Color", 1.3, False), ("Name", 1.8, False), ("Supplier", 1.2, False),
                ("Brand", 0.7, False), ("Type", 0.9, False), ("Status", 0.9, False), ("Version", 0.6, True), ("HS code", 0.9, False),
                ("Suggested", 0.9, False), ("Origin", 0.6, False), ("Customs description", 4, False),
                ("Commercial description", 1.8, False), ("Composition", 4, False)] \
        + [(f"Code {iso}", 1.4, False) for iso in paises] + [("SKUs", 0.5, True)]
    filas, partes, codigos_filas = [], [], []
    for p in r["items"]:
        pr = prods.get(p["id"])
        cods = codigos(pr)
        filas.append([p["codigo_generico"] or "—", p["estilo"], p["color"], p["nombre"] or "—", p["proveedor"] or "—",
                      p["marca"] or "—", p["tipo"] or "—", p["estado_txt"], pr.version_ficha if pr else 1, p["codigo"] or "—",
                      p["sugerido"] or "—", p["pais_origen"] or "—", (pr.descripcion_aduana if pr else None) or "—",
                      p.get("descripcion_comercial") or "—", comp(pr) or "—"]
                     + [cods.get(iso, "—") for iso in paises] + [p["skus"]])
        c = ((pr.ficha or {}).get("comp") or {}) if pr else {}
        for parte, materiales in (c.items() if isinstance(c, dict) else []):
            if materiales:
                partes.append([p["codigo_generico"] or "—", p["estilo"], p["color"], nombre_parte.get(parte) or documentos._legible(parte),
                               str(materiales)])
        for x in (pr.partidas if pr else []):
            codigos_filas.append([p["codigo_generico"] or "—", p["estilo"], p["color"], x.pais, fmt_codigo(x.codigo) or "—",
                                  f"{x.dai}%" if x.dai not in (None, "") else "—", documentos.ESTADO_PARTIDA.get(x.estado, x.estado or "—"),
                                  "By hand" if x.manual else (x.fuente or "—").capitalize()])
    hojas = [
        {"titulo": "Composition", "columnas": [("Generic", 1, False), ("Style", 1.1, False), ("Color", 1.3, False),
                                               ("Part", 1.6, False), ("Materials", 5, False)], "filas": partes},
        {"titulo": "National codes", "columnas": [("Generic", 1, False), ("Style", 1.1, False), ("Color", 1.3, False),
                                                  ("Country", 0.7, False), ("Code", 1.6, False), ("Duty (DAI)", 0.9, False),
                                                  ("Status", 0.9, False), ("Source", 0.9, False)], "filas": codigos_filas},
    ]
    return exportar.exportar_reporte(titulo, sub, texto, indicadores, columnas, filas, hojas)
