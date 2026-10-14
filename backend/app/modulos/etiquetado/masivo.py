"""Generación masiva de etiquetas (docs/ETIQUETADO.md §Generación masiva).

Tres orígenes, siempre con un diseño elegido por el usuario:

- Varias órdenes de compra (por ejemplo, las que tienen artículos de una
  familia): un lote por OC, con una etiqueta por artículo distinto (aunque se
  repita en varias líneas) o una por OC, según el diseño. Se descargan juntos:
  un PDF por OC (una etiqueta por página) en un ZIP.
- Varios artículos: un lote con una etiqueta por página en un solo PDF (o las
  imágenes en un ZIP).
- Una lista de empaque: una etiqueta por cada unidad del nivel de empaque
  elegido (cajas, tarimas, inner…).

Cada lote queda en el historial con su versión e instantánea, igual que una
generación desde el asistente; los de una misma generación masiva comparten
el código `lote`.
"""
from __future__ import annotations

import io
import uuid
import zipfile

from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errores import ErrorNegocio
from app.modelos import Articulo, GeneracionEtiquetas, OrdenCompra, PosicionOC, Usuario
from app.modulos.acceso.permisos import exigir, proveedor_filtro
from app.modulos.comun.historial import registrar
from app.modulos.comun.texto import filtro_texto
from app.modulos.etiquetado import campos, familias, generacion, plantillas, salidas

TIPOS = ("ordenes", "articulos", "packing")
MAX_ORDENES = 200
MAX_ARTICULOS = 2000
UNA_POR_PAGINA = {"modo": "individual"}


# ---- Qué se puede etiquetar -------------------------------------------------------------------
def ordenes_familia(db: Session, user: Usuario, familia_id: int | None = None, q: str | None = None,
                    estado: str | None = None, page: int = 1, size: int = 50, solo_ids: bool = False) -> dict:
    """Órdenes de compra con artículos de la familia (o todas, sin familia), con
    cuántas líneas y artículos distintos de la familia tienen y si ya se
    generaron etiquetas para ellas."""
    exigir(user, "etiquetas.generar")
    lineas = select(PosicionOC.oc_id, func.count(PosicionOC.id).label("lineas"),
                    func.count(distinct(PosicionOC.articulo_id)).label("articulos")).join(Articulo, Articulo.id == PosicionOC.articulo_id)
    if familia_id:
        familias.cargar(db, familia_id)
        lineas = lineas.where(familias.familia_sql() == familia_id)
    sub = lineas.group_by(PosicionOC.oc_id).subquery()
    c = select(OrdenCompra, sub.c.lineas, sub.c.articulos).join(sub, sub.c.oc_id == OrdenCompra.id)
    prov = proveedor_filtro(user)
    if prov is not None:
        c = c.where(OrdenCompra.proveedor_id.in_(prov))
    if estado:
        c = c.where(OrdenCompra.estado == estado.upper())
    else:
        c = c.where(OrdenCompra.estado.not_in(("BORRADOR", "CANCELADA")))
    if q and q.strip():
        c = c.where(filtro_texto(q, lambda p: [OrdenCompra.numero.ilike(p)]))
    if solo_ids:
        return {"ids": [o.id for o, _, _ in db.execute(c.order_by(OrdenCompra.id).limit(MAX_ORDENES * 5))]}
    total = db.scalar(select(func.count()).select_from(c.subquery())) or 0
    filas = db.execute(c.order_by(OrdenCompra.fecha.desc().nulls_last(), OrdenCompra.id.desc())
                       .offset((page - 1) * size).limit(size)).all()
    ids = [o.id for o, _, _ in filas]
    hechas = dict(db.execute(select(GeneracionEtiquetas.oc_id, func.count()).where(
        GeneracionEtiquetas.oc_id.in_(ids), GeneracionEtiquetas.estado == "GENERADA").group_by(GeneracionEtiquetas.oc_id)).all())
    return {"total": total, "items": [{
        "id": o.id, "numero": o.numero, "proveedor": o.proveedor.nombre if o.proveedor else None, "estado": o.estado,
        "fecha": o.fecha, "lineas": lineas_, "articulos": articulos_, "generaciones": hechas.get(o.id, 0),
        "bultos": len(campos.bultos(db, o.id))} for o, lineas_, articulos_ in filas]}


def buscar_packing(db: Session, user: Usuario, q: str | None = None, size: int = 30) -> list[dict]:
    """Listas de empaque (no canceladas) dentro del alcance del usuario, por número de lista o de factura."""
    from app.modelos import Factura, PackingList
    from app.modulos.acceso.permisos import sociedades_de

    exigir(user, "etiquetas.generar")
    c = select(PackingList).join(Factura, Factura.id == PackingList.factura_id).where(PackingList.estado != "CANCELADO")
    prov = proveedor_filtro(user)
    if prov is not None:
        c = c.where(Factura.proveedor_id.in_(prov))
    soc = sociedades_de(user)
    if soc:
        c = c.where(Factura.sociedad.in_(soc))
    if q and q.strip():
        c = c.where(filtro_texto(q, lambda p: [PackingList.numero.ilike(p), Factura.numero.ilike(p)]))
    return [{"id": pl.id, "numero": pl.numero, "factura": pl.factura.numero, "estado": pl.estado,
             "proveedor": pl.factura.proveedor.nombre if pl.factura.proveedor else None}
            for pl in db.scalars(c.order_by(PackingList.id.desc()).limit(size))]


def packing(db: Session, user: Usuario, pl_id: int) -> dict:
    """Una lista de empaque con sus niveles de empaque (cuántas unidades de cada tipo)."""
    exigir(user, "etiquetas.generar")
    pl = generacion.cargar_pl(db, user, pl_id)
    return {"id": pl.id, "numero": pl.numero, "factura": pl.factura.numero, "estado": pl.estado,
            "proveedor": pl.factura.proveedor.nombre if pl.factura.proveedor else None,
            "niveles": campos.niveles_pl(pl), "superiores": len(campos.unidades_pl(pl, superiores=True))}


# ---- Plan -----------------------------------------------------------------------------------------
def _plantilla(db: Session, pedido: dict):
    if not pedido.get("plantilla_id"):
        raise ErrorNegocio("Choose the label design.", 422, "validacion")
    p = plantillas.cargar(db, int(pedido["plantilla_id"]))
    if p.estado != "ACTIVA":
        raise ErrorNegocio("The design is archived.", 422, "validacion")
    if p.vigente is None and not pedido.get("prueba"):
        raise ErrorNegocio("The design has no approved version yet.", 422, "sin_plantilla")
    return p


def _pedidos(db: Session, user: Usuario, pedido: dict) -> tuple:
    """El diseño y un pedido de generación por cada lote que se va a producir."""
    tipo = pedido.get("tipo")
    if tipo not in TIPOS:
        raise ErrorNegocio("Choose what to label: purchase orders, items or a packing list.", 422, "validacion")
    p = _plantilla(db, pedido)
    comun = {"modalidad": p.modalidad, "plantilla_id": p.id, "prueba": bool(pedido.get("prueba")),
             "manuales": pedido.get("manuales") or {}, "hoja": UNA_POR_PAGINA}
    if tipo == "ordenes":
        if p.modalidad == "ARTICULO":
            raise ErrorNegocio("This design only has item data: choose a design for purchase orders.", 422, "modalidad")
        ids = list(dict.fromkeys(int(x) for x in pedido.get("oc_ids") or []))
        if not ids:
            raise ErrorNegocio("Choose the purchase orders.", 422, "validacion")
        if len(ids) > MAX_ORDENES:
            raise ErrorNegocio(f"Up to {MAX_ORDENES} purchase orders at a time.", 422, "validacion")
        unidad = "ORDEN" if p.modalidad == "OC" else "ARTICULO"
        return tipo, p, [{**comun, "unidad": unidad, "oc_id": i, "familia_id": pedido.get("familia_id")} for i in ids]
    if tipo == "articulos":
        if p.modalidad != "ARTICULO":
            raise ErrorNegocio("This design needs purchase order data: choose an item design.", 422, "modalidad")
        por_defecto = max(int(pedido.get("cantidad") or 1), 1)
        articulos = pedido.get("articulos") or [{"articulo_id": i} for i in pedido.get("articulo_ids") or []]
        if not articulos:
            raise ErrorNegocio("Choose the items.", 422, "validacion")
        if len(articulos) > MAX_ARTICULOS:
            raise ErrorNegocio(f"Up to {MAX_ARTICULOS} items at a time.", 422, "validacion")
        lista = [{"articulo_id": int(a["articulo_id"]), "cantidad": int(a.get("cantidad") or por_defecto)} for a in articulos]
        return tipo, p, [{**comun, "unidad": "MANUAL", "articulos": lista}]
    if p.modalidad == "ARTICULO":
        raise ErrorNegocio("A packing list label needs PO data: choose a PO design.", 422, "modalidad")
    if not pedido.get("pl_id"):
        raise ErrorNegocio("Choose the packing list.", 422, "validacion")
    return tipo, p, [{**comun, "unidad": "BULTO", "pl_id": int(pedido["pl_id"]), "tipo_empaque_id": pedido.get("tipo_empaque_id")}]


def plan(db: Session, user: Usuario, pedido: dict) -> dict:
    """Qué se va a generar en cada lote, con sus problemas, sin generar nada."""
    exigir(user, "etiquetas.generar")
    tipo, p, pedidos = _pedidos(db, user, pedido)
    partes = []
    for x in pedidos:
        try:
            r = generacion.plan(db, user, x)
        except ErrorNegocio as e:
            oc = db.get(OrdenCompra, x["oc_id"]) if x.get("oc_id") else None
            partes.append({"oc_id": x.get("oc_id"), "oc": oc.numero if oc else None, "total": 0, "errores": 1, "advertencias": 0,
                           "problemas": [{"nivel": "error", "mensaje": e.mensaje}], "grupos": [], "_pedido": x})
            continue
        problemas = [{"nivel": q["nivel"], "mensaje": q["mensaje"], "referencia": g["referencia"]}
                     for g in r["grupos"] for q in g["problemas"]] + [{**q, "referencia": None} for q in r["problemas"]]
        partes.append({"oc_id": r["oc_id"], "oc": r["oc"], "total": r["total"], "errores": r["errores"],
                       "advertencias": r["advertencias"], "problemas": problemas[:100],
                       "grupos": [{"referencia": g["referencia"], "cantidad": g["cantidad"], "familia": g["familia"],
                                   "version": g["version"], "articulo_id": g["articulo_id"], "posicion_id": g["posicion_id"],
                                   "oc_id": g.get("oc_id") or r["oc_id"], "bulto": g["bulto"]} for g in r["grupos"][:500]],
                       "_pedido": x})
    total = sum(x["total"] for x in partes if not x["errores"])
    errores = sum(x["errores"] for x in partes)
    general = []
    if total > settings.ETIQUETAS_MAXIMO_LOTE * max(len(partes), 1):
        general.append({"nivel": "error", "mensaje": "Too many labels for one generation: choose fewer orders or items."})
    v = p.vigente if not pedido.get("prueba") else (p.versiones[-1] if p.versiones else None)
    return {"tipo": tipo, "plantilla": {"id": p.id, "nombre": p.nombre, "modalidad": p.modalidad,
                                        "version": v.numero if v else None, "version_id": v.id if v else None,
                                        "ancho_mm": v.ancho_mm if v else None, "alto_mm": v.alto_mm if v else None,
                                        "variables": (v.diseno.get("variables") or []) if v else []},
            "partes": partes, "total": total, "errores": errores, "problemas": general,
            "con_errores": sum(1 for x in partes if x["errores"]), "advertencias": sum(x["advertencias"] for x in partes),
            "puede_generar": total > 0 and not general and (errores == 0 or len(partes) > sum(1 for x in partes if x["errores"]))}


def _publico(r: dict) -> dict:
    return {**{k: v for k, v in r.items() if k != "partes"},
            "partes": [{k: v for k, v in x.items() if not k.startswith("_")} for x in r["partes"]]}


def ver_plan(db: Session, user: Usuario, pedido: dict) -> dict:
    return _publico(plan(db, user, pedido))


# ---- Generar --------------------------------------------------------------------------------------
def generar(db: Session, user: Usuario, pedido: dict) -> dict:
    """Genera un lote por OC (o uno solo) con una etiqueta por página. Con
    errores no genera, salvo que se pida omitir las OC que los tienen; con
    advertencias pide confirmarlas."""
    formato = (pedido.get("formato") or "PDF").upper()
    if formato not in ("PDF", "PNG"):
        raise ErrorNegocio("Choose PDF or PNG.", 422, "validacion")
    r = plan(db, user, pedido)
    if r["problemas"]:
        raise ErrorNegocio(r["problemas"][0]["mensaje"], 422, "validacion")
    con_errores = [x for x in r["partes"] if x["errores"]]
    if con_errores and not pedido.get("omitir_con_errores"):
        raise ErrorNegocio("Some labels cannot be generated: fix the errors or skip those orders.", 422, "etiquetas_con_errores",
                           [{"campo": x["oc"] or (q.get("referencia") or ""), "mensaje": q["mensaje"]}
                            for x in con_errores for q in x["problemas"] if q["nivel"] == "error"][:50])
    validas = [x for x in r["partes"] if not x["errores"]]
    if not validas:
        raise ErrorNegocio("Nothing can be generated.", 422, "etiquetas_con_errores")
    advertencias = [q for x in validas for q in x["problemas"] if q["nivel"] == "advertencia"]
    if advertencias and not pedido.get("aceptar_advertencias"):
        raise ErrorNegocio("There are warnings: review them and confirm to generate anyway.", 409, "confirmar_advertencias",
                           [{"campo": q.get("referencia") or "", "mensaje": q["mensaje"]} for q in advertencias[:50]])
    lote = str(uuid.uuid4())
    hechas = [generacion.generar(db, user, {**x["_pedido"], "formato": formato, "lote": lote, "aceptar_advertencias": True})
              for x in validas]
    registrar(db, user, "generacion_etiquetas", hechas[0]["id"], "generar_masivo",
              {"lote": lote, "tipo": r["tipo"], "plantilla": r["plantilla"]["nombre"], "lotes": len(hechas),
               "total": sum(h["total"] for h in hechas), "omitidas": [x["oc"] for x in con_errores][:50]})
    return {"lote": lote, "tipo": r["tipo"], "formato": formato, "total": sum(h["total"] for h in hechas),
            "generaciones": [{"id": h["id"], "oc": h["oc"], "total": h["total"]} for h in hechas],
            "omitidas": [{"oc": x["oc"], "problemas": x["problemas"][:5]} for x in con_errores]}


def archivo(db: Session, user: Usuario, lote: str, formato: str | None = None) -> tuple[bytes, str, str]:
    """Los archivos de una generación masiva: con un solo lote, su PDF (o su
    ZIP de imágenes); con varios, un ZIP con un PDF (o una carpeta de imágenes)
    por OC. Se dibujan de nuevo desde las versiones e instantáneas guardadas."""
    exigir(user, "etiquetas.ver")
    gens = list(db.scalars(select(GeneracionEtiquetas).where(GeneracionEtiquetas.lote == lote, *generacion._alcance(user))
                           .order_by(GeneracionEtiquetas.id)))
    if not gens:
        raise ErrorNegocio("The label batch does not exist.", 404, "no_encontrado")
    formato = (formato or gens[0].formato).upper()
    if formato not in ("PDF", "PNG"):
        raise ErrorNegocio("Choose PDF or PNG.", 422, "validacion")
    if len(gens) == 1:
        contenido, nombre, mime, _ = generacion.archivo(db, user, gens[0].id, formato)
        return contenido, nombre, mime
    buf = io.BytesIO()
    fecha = gens[0].creada_en.timetuple()[:6]
    usados: set = set()

    def poner(z, nombre: str, datos_: bytes):
        info = zipfile.ZipInfo(nombre, date_time=fecha)
        info.compress_type = zipfile.ZIP_DEFLATED
        z.writestr(info, datos_)

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for g in gens:
            base = generacion._seguro(db.get(OrdenCompra, g.oc_id).numero if g.oc_id else f"lote-{g.id}")
            while base in usados:
                base += f"-{g.id}"
            usados.add(base)
            lienzos = generacion._lienzos(db, g)
            if formato == "PDF":
                poner(z, f"{base}.pdf", salidas.pdf([lz for lz, _ in lienzos], UNA_POR_PAGINA, base))
            else:
                dpi = (g.parametros or {}).get("dpi")
                for i, (lz, nombre) in enumerate(lienzos, start=1):
                    poner(z, f"{base}/{i:05d}-{generacion._seguro(nombre)}.png", salidas.png(lz, dpi))
    registrar(db, user, "generacion_etiquetas", gens[0].id, "descargar_masivo", {"lote": lote, "formato": formato, "lotes": len(gens)})
    return buf.getvalue(), f"labels-{lote[:8]}.zip", "application/zip"
