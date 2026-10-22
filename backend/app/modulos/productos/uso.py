"""Dónde se usa un producto y cómo se empaca (pestañas «Uso» y «Empaque» de la ficha).

- Uso: las OCs, facturas y embarques en que aparecen sus variantes, con el
  alcance del usuario (un proveedor solo ve lo suyo) y solo las secciones de
  los módulos que su rol puede ver.
- Empaque: las reglas de empaque que pueden aplicarle (de la empresa, de una
  de sus familias, del producto o de una variante), con sus condiciones, y
  las recetas con que realmente se pidió en sus posiciones de OC. La regla
  que gana en cada OC depende de los datos de esa OC (destino, origen…): aquí
  se listan todas las candidatas, en el orden en que compiten.
"""
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.modelos import (
    Embarque,
    FacturaLinea,
    OrdenCompra,
    PackingList,
    PLLinea,
    PosicionOC,
    RecetaEmpaque,
    UnidadCarga,
    Usuario,
)
from app.modulos.acceso.permisos import exigir, proveedor_filtro, sociedad_filtro, tiene
from app.modulos.facturacion.cantidades import nombre_factura
from app.modulos.productos.productos import _producto

MAX_FILAS = 50  # por sección; el total se informa aparte


def uso(db: Session, user: Usuario, producto_id: int) -> dict:
    p = _producto(db, user, producto_id)
    ids_art = [a.id for a in p.articulos]
    res: dict = {"ordenes": None, "facturas": None, "embarques": None}
    if not ids_art:
        return {k: {"items": [], "total": 0} for k in res}
    consulta = (select(PosicionOC).join(OrdenCompra).where(PosicionOC.articulo_id.in_(ids_art))
                .options(selectinload(PosicionOC.oc)))
    prov = proveedor_filtro(user, None)
    if prov:
        consulta = consulta.where(OrdenCompra.proveedor_id.in_(prov))
    consulta = consulta.where(*sociedad_filtro(user, OrdenCompra.sociedad))
    posiciones = list(db.scalars(consulta))
    pos_ids = [x.id for x in posiciones]

    if tiene(user, "oc.ver"):
        por_oc: dict[int, dict] = {}
        for x in posiciones:
            o = por_oc.setdefault(x.oc_id, {"id": x.oc_id, "numero": x.oc.numero, "estado": x.oc.estado,
                                            "fecha_tienda": x.oc.fecha_tienda, "lineas": 0, "cantidad": defaultdict(float)})
            o["lineas"] += 1
            o["cantidad"][x.unidad] += float(x.cantidad)
        filas = sorted(por_oc.values(), key=lambda o: o["numero"], reverse=True)
        res["ordenes"] = {"items": [{**o, "cantidad": dict(o["cantidad"])} for o in filas[:MAX_FILAS]], "total": len(filas)}

    lineas_fac = list(db.scalars(select(FacturaLinea).where(FacturaLinea.posicion_oc_id.in_(pos_ids))
                                 .options(selectinload(FacturaLinea.factura)))) if pos_ids else []
    if tiene(user, "factura.ver"):
        por_fac: dict[int, dict] = {}
        for li in lineas_fac:
            f = li.factura
            d = por_fac.setdefault(f.id, {"id": f.id, "numero": nombre_factura(f), "estado": f.estado, "fecha": f.fecha,
                                          "cantidad": defaultdict(float)})
            d["cantidad"][li.unidad] += float(li.cantidad)
        filas = sorted(por_fac.values(), key=lambda d: (d["fecha"] is None, str(d["fecha"])), reverse=True)
        res["facturas"] = {"items": [{**d, "cantidad": dict(d["cantidad"])} for d in filas[:MAX_FILAS]], "total": len(filas)}

    if tiene(user, "transporte.gestionar") or tiene(user, "seguimiento.ver"):
        emb: dict[int, dict] = {}
        if lineas_fac:
            q = (select(Embarque, PLLinea.cantidad, FacturaLinea.unidad)
                 .join(UnidadCarga, UnidadCarga.embarque_id == Embarque.id)
                 .join(PackingList, PackingList.unidad_carga_id == UnidadCarga.id)
                 .join(PLLinea, PLLinea.pl_id == PackingList.id)
                 .join(FacturaLinea, FacturaLinea.id == PLLinea.factura_linea_id)
                 .where(PLLinea.factura_linea_id.in_([li.id for li in lineas_fac]), PackingList.estado != "CANCELADO"))
            for e, cantidad, unidad in db.execute(q):
                d = emb.setdefault(e.id, {"id": e.id, "codigo": e.codigo, "estado": e.estado, "eta": e.eta,
                                          "cantidad": defaultdict(float)})
                d["cantidad"][unidad] += float(cantidad)
        filas = sorted(emb.values(), key=lambda d: (d["eta"] is None, str(d["eta"])), reverse=True)
        res["embarques"] = {"items": [{**d, "cantidad": dict(d["cantidad"])} for d in filas[:MAX_FILAS]], "total": len(filas)}
    return res


def empaque(db: Session, user: Usuario, producto_id: int) -> dict:
    from app.modulos.empaque import recetas

    p = _producto(db, user, producto_id)
    exigir(user, "catalogos.ver")  # las reglas de empaque son configuración interna
    motor = recetas.Motor(db)
    candidatas = []
    for r in motor.reglas:
        pesos = [motor._peso(r, a) for a in p.articulos]
        pesos = [x for x in pesos if x is not None]
        if not pesos:
            continue
        candidatas.append({"regla_id": r.id, "destino": recetas.nombre_destino(r), "receta_id": r.receta_id,
                           "receta": r.receta.nombre, "resumen": recetas.resumen(recetas.foto(r.receta)),
                           "condiciones": recetas.texto_condiciones(r.condiciones), "orden": r.orden,
                           "especificidad": max(pesos)[0], "vigente_desde": r.vigente_desde, "vigente_hasta": r.vigente_hasta})
    # Como compiten: la más específica primero; con condiciones antes que sin ellas; luego el orden
    candidatas.sort(key=lambda c: (-c["especificidad"], 0 if c["condiciones"] else 1, c["orden"], c["regla_id"]))
    usadas: dict[str, dict] = {}
    ids_art = [a.id for a in p.articulos]
    if ids_art:
        consulta = select(PosicionOC).join(OrdenCompra).where(PosicionOC.articulo_id.in_(ids_art), PosicionOC.receta_id.is_not(None))
        prov = proveedor_filtro(user, None)
        if prov:
            consulta = consulta.where(OrdenCompra.proveedor_id.in_(prov))
        posiciones = list(db.scalars(consulta))
        nombres = dict(db.execute(select(RecetaEmpaque.id, RecetaEmpaque.nombre).where(
            RecetaEmpaque.id.in_({x.receta_id for x in posiciones}))).all()) if posiciones else {}
        for x in posiciones:
            nombre = nombres.get(x.receta_id, str(x.receta_id))
            u = usadas.setdefault(nombre, {"receta_id": x.receta_id, "receta": nombre,
                                                    "resumen": recetas.resumen(x.receta_foto), "posiciones": 0,
                                                    "origenes": set()})
            u["posiciones"] += 1
            if x.receta_origen:
                u["origenes"].add(x.receta_origen)
    return {"reglas": candidatas,
            "en_uso": [{**u, "origenes": sorted(u["origenes"])} for u in sorted(usadas.values(), key=lambda u: -u["posiciones"])]}
