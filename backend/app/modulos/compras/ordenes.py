import csv
import io
import re
import unicodedata
from datetime import date, datetime

from sqlalchemy import Integer, cast, func, or_, select
from sqlalchemy.orm import Session

from app.core import campos_propios, dinero, empresa, listas
from app.core.archivos import abrir_libro
from app.core.empresa import regla, tope_filas
from app.core.errores import ErrorNegocio
from app.core.estados import OC
from app.modelos import (
    Alerta,
    Almacen,
    Centro,
    Factura,
    FacturaLinea,
    ImportacionOC,
    OrdenCompra,
    Pais,
    PosicionOC,
    Proveedor,
    Puerto,
    Sociedad,
    Usuario,
    ahora,
)
from app.modelos import cant as cant_norm
from app.modulos.acceso.permisos import (
    asegurar_proveedor,
    exigir,
    exigir_alguno,
    proveedor_filtro,
    proveedores_de,
    sociedad_filtro,
    un_proveedor,
)
from app.modulos.acceso.preferencias import leer_fecha
from app.modulos.catalogo import servicio as catalogo
from app.modulos.comex import servicio as comex
from app.modulos.compras import liberaciones, perfiles
from app.modulos.comun import tabla as tabla_datos
from app.modulos.comun.historial import registrar
from app.modulos.comun.texto import filtro_texto
from app.modulos.empaque import recetas
from app.modulos.facturacion.cantidades import facturado_por_posicion, facturas_por_posicion
from app.modulos.maestros.unidades import error_cantidad
from app.modulos.maestros.unidades import normalizar as unidad_de

# Dos liberaciones de dos equipos distintos (comercial y logística). Sus
# códigos, nombres y efecto los define cada empresa en Datos maestros →
# Estados de liberación (modulos/compras/liberaciones.py).


# ---- Vista general de OCs ---------------------------------------------------
ORDEN_OC = {"numero", "fecha", "fecha_xf", "fecha_tienda", "importe", "avance", "proveedor"}


def _consulta_ordenes(db: Session, user: Usuario, proveedor_id=None, q=None, centro=None, solo_disponible=True,
                      sociedad=None, marca=None, liberacion=None, destino=None, puerto=None, almacen=None,
                      comercial=None, liberada=None, estado=None):
    """OCs visibles para el usuario con los filtros de la pantalla (sin los de
    columna), con sus totales; devuelve la consulta y las columnas que se
    filtran por valor (app/modulos/comun/tabla.py)."""
    exigir(user, "oc.ver")
    prov = proveedor_filtro(user, proveedor_id)

    tot = (
        select(
            PosicionOC.oc_id.label("oc_id"),
            func.sum(PosicionOC.cantidad).label("cantidad"),
            func.sum(dinero.importe_sql(PosicionOC.cantidad, PosicionOC.precio)).label("importe"),
            func.count(PosicionOC.id).label("n"),
        )
        .group_by(PosicionOC.oc_id)
        .subquery()
    )
    fac = (
        select(
            PosicionOC.oc_id.label("oc_id"),
            func.sum(FacturaLinea.cantidad).label("facturado"),
            func.sum(dinero.importe_sql(FacturaLinea.cantidad, PosicionOC.precio)).label("importe_facturado"),
        )
        .join(FacturaLinea, FacturaLinea.posicion_oc_id == PosicionOC.id)
        .join(Factura, Factura.id == FacturaLinea.factura_id)
        .where(Factura.estado != "CANCELADA")
        .group_by(PosicionOC.oc_id)
        .subquery()
    )
    facturado = func.coalesce(fac.c.facturado, 0)
    importe_fact = func.coalesce(fac.c.importe_facturado, 0)
    consulta = (
        select(OrdenCompra, Proveedor.nombre, tot.c.importe, tot.c.n, importe_fact)
        .join(Proveedor, Proveedor.id == OrdenCompra.proveedor_id)
        .outerjoin(tot, tot.c.oc_id == OrdenCompra.id)
        .outerjoin(fac, fac.c.oc_id == OrdenCompra.id)
    )
    if estado:
        consulta = consulta.where(OrdenCompra.estado.in_(estado.split(",")))
    if prov:
        consulta = consulta.where(OrdenCompra.proveedor_id.in_(prov))
    consulta = consulta.where(*sociedad_filtro(user, OrdenCompra.sociedad))
    if q:
        consulta = consulta.where(filtro_texto(q, lambda p: [
            OrdenCompra.numero.ilike(p),
            OrdenCompra.id.in_(select(PosicionOC.oc_id).where(or_(
                PosicionOC.codigo_articulo.ilike(p), PosicionOC.codigo_barras.ilike(p), PosicionOC.descripcion.ilike(p)))),
        ]))
    if centro:
        consulta = consulta.where(OrdenCompra.centro == centro)
    if sociedad:
        consulta = consulta.where(OrdenCompra.sociedad == sociedad)
    if destino:
        consulta = consulta.where(OrdenCompra.centro_destino == destino)
    if puerto:
        consulta = consulta.where(OrdenCompra.puerto_despacho == puerto)
    if liberacion:
        consulta = consulta.where(OrdenCompra.liberacion_logistica == liberacion)
    if comercial:
        consulta = consulta.where(OrdenCompra.liberacion_comercial == comercial)
    if liberada is not None:
        consulta = consulta.where(OrdenCompra.liberada.is_(liberada))
    if marca:
        consulta = consulta.where(OrdenCompra.id.in_(select(PosicionOC.oc_id).where(PosicionOC.articulo_id.in_(
            catalogo.ids(marca=marca)))))
    if almacen:
        consulta = consulta.where(OrdenCompra.id.in_(select(PosicionOC.oc_id).where(PosicionOC.almacen == almacen)))
    if solo_disponible:
        consulta = consulta.where(OrdenCompra.estado == "APROBADA", func.coalesce(tot.c.cantidad, 0) - facturado > 0)
    columnas = {
        "oc": OrdenCompra.numero, "estado": OrdenCompra.estado, "proveedor": Proveedor.nombre, "fecha": OrdenCompra.fecha,
        "sociedad": OrdenCompra.sociedad, "centro": OrdenCompra.centro, "destino": OrdenCompra.centro_destino,
        "puerto": OrdenCompra.puerto_despacho, "xf": OrdenCompra.fecha_xf, "tienda": OrdenCompra.fecha_tienda,
        "moneda": OrdenCompra.moneda,
        # Facturado en % entero del valor de la OC
        "avance": cast(func.coalesce(func.round(importe_fact * 100.0 / func.nullif(tot.c.importe, 0)), 0), Integer),
    }
    return consulta, columnas, tot, importe_fact


def valores_ordenes(db: Session, user: Usuario, columna: str, buscar: str | None, filtros: dict, **pantalla) -> list[dict]:
    """Valores únicos de una columna de la tabla de OCs bajo los demás filtros."""
    consulta, columnas, *_ = _consulta_ordenes(db, user, **pantalla)
    expr = tabla_datos.columna_valida(columnas, columna)
    return tabla_datos.valores(db, tabla_datos.aplicar(consulta, columnas, filtros, excepto=columna), expr, buscar,
                               contar=OrdenCompra.id)


def listar_ordenes(
    db: Session,
    user: Usuario,
    proveedor_id: int | None = None,
    q: str | None = None,
    centro: str | None = None,
    solo_disponible: bool = True,
    page: int = 1,
    size: int = 25,
    sociedad: str | None = None,
    marca: str | None = None,
    liberacion: str | None = None,
    destino: str | None = None,
    puerto: str | None = None,
    orden: str | None = None,
    almacen: str | None = None,
    comercial: str | None = None,
    liberada: bool | None = None,
    estado: str | None = None,
    filtros: dict | None = None,
) -> dict:
    lib = liberaciones.de(db)
    consulta, columnas, tot, importe_fact = _consulta_ordenes(
        db, user, proveedor_id, q, centro, solo_disponible, sociedad, marca, liberacion, destino, puerto, almacen,
        comercial, liberada, estado)
    consulta = tabla_datos.aplicar(consulta, columnas, filtros or {})

    col, _, direccion = (orden or "").partition(":")
    expr = {
        "numero": OrdenCompra.numero, "fecha": OrdenCompra.fecha, "fecha_xf": OrdenCompra.fecha_xf,
        "fecha_tienda": OrdenCompra.fecha_tienda, "importe": tot.c.importe, "proveedor": Proveedor.nombre,
        "avance": importe_fact * 1.0 / func.nullif(tot.c.importe, 0),
    }.get(col)
    if expr is not None:
        consulta = consulta.order_by(expr.desc().nullslast() if direccion == "desc" else expr.asc().nullslast(),
                                     OrdenCompra.numero)
    else:
        consulta = consulta.order_by(OrdenCompra.fecha.desc().nullslast(), OrdenCompra.numero)

    total = db.scalar(select(func.count()).select_from(consulta.subquery())) or 0
    filas = db.execute(consulta.offset((page - 1) * size).limit(size)).all()

    # Cantidades por unidad de medida: nunca se suman pares con unidades
    ids = [oc.id for oc, *_ in filas]
    por_unidad: dict[int, dict] = {i: {} for i in ids}
    marcas: dict[int, set] = {i: set() for i in ids}
    almacenes: dict[int, set] = {i: set() for i in ids}
    if ids:
        for oc_id, alm in db.execute(
            select(PosicionOC.oc_id, PosicionOC.almacen).where(PosicionOC.oc_id.in_(ids)).distinct()
        ).all():
            if alm:
                almacenes[oc_id].add(alm)
        for oc_id, unidad, atributos, cant in db.execute(
            select(PosicionOC.oc_id, PosicionOC.unidad, PosicionOC.atributos, PosicionOC.cantidad)
            .where(PosicionOC.oc_id.in_(ids))
        ).all():
            d = por_unidad[oc_id].setdefault(unidad, {"cantidad": 0, "facturado": 0, "disponible": 0})
            d["cantidad"] = cant_norm(d["cantidad"] + (cant or 0))
            d["disponible"] = cant_norm(d["disponible"] + (cant or 0))
            # La marca de la línea: el atributo de producto que apunta al catálogo de marcas
            if marca_oc := catalogo.marca(db, atributos):
                marcas[oc_id].add(marca_oc)
        for oc_id, unidad, cant in db.execute(
            select(PosicionOC.oc_id, PosicionOC.unidad, func.sum(FacturaLinea.cantidad))
            .join(FacturaLinea, FacturaLinea.posicion_oc_id == PosicionOC.id)
            .join(Factura, Factura.id == FacturaLinea.factura_id)
            .where(Factura.estado != "CANCELADA", PosicionOC.oc_id.in_(ids))
            .group_by(PosicionOC.oc_id, PosicionOC.unidad)
        ).all():
            d = por_unidad[oc_id][unidad]
            d["facturado"] = cant_norm(cant or 0)
            d["disponible"] = max(d["cantidad"] - d["facturado"], 0)

    hoy = date.today()
    centros = {c.codigo: c for c in db.scalars(select(Centro))}
    from app.modulos.transporte.leadtimes import tiendas_estimadas
    est_tienda = tiendas_estimadas(db, [oc for oc, *_ in filas])
    items = []
    for oc, prov_nombre, importe, n, importe_f in filas:
        destino = centros.get(oc.centro_destino)
        importe = dinero.decimal(importe)
        importe_f = dinero.decimal(importe_f)
        items.append(
            {
                **_cabecera_oc(oc, lib),
                "proveedor": prov_nombre,
                "posiciones": n or 0,
                "marcas": sorted(marcas[oc.id]),
                # Una OC puede repartir sus posiciones entre varios almacenes
                "almacenes": sorted(almacenes[oc.id]),
                "por_unidad": por_unidad[oc.id],
                "importe": dinero.numero(dinero.redondear(importe, oc.moneda)),
                "importe_facturado": dinero.numero(dinero.redondear(importe_f, oc.moneda)),
                # Avance por valor: es comparable aunque la OC mezcle pares y unidades
                "avance": float(round(importe_f * 100 / importe, 1)) if importe else 0,
                "dias_tienda": (oc.fecha_tienda - hoy).days if oc.fecha_tienda else None,
                # Con los lead times de su origen: cuándo estaría en tienda
                **est_tienda.get(oc.id, {}),
                # El centro de destino dice a qué país llega al final
                "destino_nombre": destino.nombre if destino else None,
                "pais_destino": destino.pais if destino else None,
            }
        )
    return {"items": items, "total": total, "page": page, "size": size}


def filtros_ordenes(db: Session, user: Usuario, proveedor_id: int | None = None) -> dict:
    """Valores presentes en las OCs visibles, para armar filtros dinámicos."""
    exigir(user, "oc.ver")
    prov = proveedor_filtro(user, proveedor_id)
    base = select(OrdenCompra)
    if prov:
        base = base.where(OrdenCompra.proveedor_id.in_(prov))
    base = base.where(*sociedad_filtro(user, OrdenCompra.sociedad))
    sub = base.subquery()

    def distintos(col):
        return sorted({v for (v,) in db.execute(select(col).select_from(sub).distinct()) if v})

    def de_posiciones(col):
        return sorted({v for (v,) in db.execute(
            select(col).where(PosicionOC.oc_id.in_(select(sub.c.id))).distinct()) if v})

    marcas = catalogo.marcas_de(db, select(PosicionOC.articulo_id).where(PosicionOC.oc_id.in_(select(sub.c.id))))
    lib = liberaciones.de(db)
    return {
        "sociedades": distintos(sub.c.sociedad),
        "centros": distintos(sub.c.centro),
        "almacenes": de_posiciones(PosicionOC.almacen),
        "destinos": [{"codigo": d.codigo, "nombre": f"{d.nombre} ({d.pais})"} for d in db.scalars(
            select(Centro).where(Centro.codigo.in_(distintos(sub.c.centro_destino))).order_by(Centro.codigo))],
        "puertos": [{"codigo": p.codigo, "nombre": p.nombre} for p in db.scalars(
            select(Puerto).where(Puerto.codigo.in_(distintos(sub.c.puerto_despacho))))],
        "marcas": marcas,
        "liberaciones": [{"codigo": x.codigo, "nombre": x.nombre, "libera": x.libera} for x in lib.logistica.lista],
        "comerciales": [{"codigo": x.codigo, "nombre": x.nombre, "libera": x.libera} for x in lib.comercial.lista],
    }


def _cabecera_oc(oc: OrdenCompra, lib: liberaciones.Liberaciones) -> dict:
    return {
        "id": oc.id,
        "numero": oc.numero,
        "proveedor_id": oc.proveedor_id,
        "sociedad": oc.sociedad,
        "centro": oc.centro,
        "centro_destino": oc.centro_destino,
        "moneda": oc.moneda,
        "incoterm": oc.incoterm,
        "fecha": oc.fecha,
        "puerto_despacho": oc.puerto_despacho,
        "pais_origen": oc.pais_origen,
        "pais_procedencia": oc.pais_procedencia,
        "fecha_xf_original": oc.fecha_xf_original,
        "fecha_xf": oc.fecha_xf,
        "fecha_tienda": oc.fecha_tienda,
        "liberacion_comercial": oc.liberacion_comercial,
        "liberacion_logistica": oc.liberacion_logistica,
        "fecha_lib_comercial": oc.fecha_lib_comercial,
        "fecha_lib_logistica": oc.fecha_lib_logistica,
        "extra": oc.extra or {},
        "liberacion_txt": lib.logistica.nombre(oc.liberacion_logistica),
        "comercial_txt": lib.comercial.nombre(oc.liberacion_comercial),
        # Liberación dada, pero la OC cambió después (para avisarlo en pantalla)
        "con_cambios": bool((x := lib.logistica.get(oc.liberacion_logistica)) and x.con_cambios),
        "liberada": oc.liberada,
        "estado": oc.estado,
        "estado_txt": OC.texto(oc.estado),
        "origen": oc.origen,
        "condicion_pago": oc.condicion_pago,
        "condicion_pago_txt": listas.nombre("condicion_pago", oc.condicion_pago) if oc.condicion_pago else None,
        "version": oc.version,
    }


def posiciones_oc(db: Session, user: Usuario, oc_id: int) -> dict:
    exigir(user, "oc.ver")
    oc = db.get(OrdenCompra, oc_id)
    if not oc:
        raise ErrorNegocio("The purchase order does not exist.", 404, "no_encontrado")
    asegurar_proveedor(user, oc.proveedor_id, oc.sociedad)
    ids = [p.id for p in oc.posiciones]
    facturado = facturado_por_posicion(db, ids)
    facturas = facturas_por_posicion(db, ids)
    # La partida sale de la clasificación del producto, con el código del país destino
    posiciones = []
    fichas = comex.de_articulos(db, [p.articulo_id for p in oc.posiciones])
    for p in oc.posiciones:
        ficha = fichas.get(p.articulo_id)
        fact = facturado.get(p.id, 0)
        fs = facturas.get(p.id, [])
        estado, motivo, restringida = estado_posicion(oc, p, fact, fs)
        posiciones.append(
            {
                "id": p.id,
                "posicion": p.posicion,
                "almacen": p.almacen,
                "codigo_articulo": p.codigo_articulo,
                "codigo_barras": p.codigo_barras,
                "variante": catalogo.texto(p.variante),
                "valores": dict(p.variante or {}),
                "atributos": dict(p.atributos or {}),
                "descripcion": p.descripcion,
                "marca": catalogo.marca(db, p.atributos),
                "tipo_empaque": p.tipo_empaque,
                "casepack": p.casepack,
                "inner_pack": p.inner_pack,
                "codigo_pack": p.codigo_pack,
                "unidades_por_caja": p.unidades_por_caja,
                "cantidad": p.cantidad,
                "unidad": p.unidad,
                "precio": p.precio,
                "importe": dinero.numero(dinero.importe(p.cantidad, p.precio, oc.moneda)) if p.precio is not None else None,
                "fecha_entrega": p.fecha_entrega,
                "pais_origen": p.pais_origen,
                "partida_arancelaria": ficha.partida if ficha else None,  # 6 dígitos: el destino es solo proyectado
                "clasificacion": ficha.resumen() if ficha else dict(comex.SIN_PRODUCTO),
                "facturado": fact,
                "disponible": max(p.cantidad - fact, 0),
                "facturas": fs,
                "estado": estado,
                "motivo": motivo,
                "solo_factura_id": restringida,
                "receta": recetas.dict_posicion(p),
            }
        )
    prov = db.get(Proveedor, oc.proveedor_id)
    destino = db.scalar(select(Centro).where(Centro.codigo == oc.centro_destino))
    from app.modulos.transporte.leadtimes import tiendas_estimadas
    return {"oc": {**_cabecera_oc(oc, liberaciones.de(db)), "proveedor": prov.nombre, **tiendas_estimadas(db, [oc]).get(oc.id, {}),
                   "centro_destino_nombre": destino.nombre if destino else None,
                   "pais_destino": destino.pais if destino else None},
            "posiciones": posiciones}


def empaque_posicion(db: Session, user: Usuario, oc_id: int, posicion_id: int, casepack: int | None,
                     inner_pack: int | None) -> dict:
    """Casepack e inner pack de una posición (condición de la compra). Se
    cambian mientras no haya nada facturado de esa posición."""
    exigir(user, "oc.empaque")
    p = db.get(PosicionOC, posicion_id)
    if not p or p.oc_id != oc_id:
        raise ErrorNegocio("The purchase order line does not exist.", 404, "no_encontrado")
    errores = validar_empaque(p.tipo_empaque, casepack, inner_pack, p.cantidad)
    if errores:
        raise ErrorNegocio("Check the packing of the line.", 422, "validacion",
                           [{"campo": "inner_pack", "mensaje": e} for e in errores])
    if facturado_por_posicion(db, [p.id]).get(p.id, 0):
        raise ErrorNegocio("This line is already invoiced: its packing can no longer change.", 409, "facturada")
    antes = {"casepack": p.casepack, "inner_pack": p.inner_pack}
    p.casepack, p.inner_pack = casepack, inner_pack
    # La receta sigue al casepack escrito (o, sin casepack, a las reglas)
    if casepack is None and inner_pack is None:
        recetas.poner(p, None, None)
    recetas.asignar(db, p, p.oc, trae_empaque=casepack is not None)
    registrar(db, user, "orden", p.oc_id, "empaque",
              {"posicion": p.posicion, **{k: [antes[k], v] for k, v in (("casepack", casepack),
                                                                           ("inner_pack", inner_pack))
                                          if antes[k] != v}})
    return {"id": p.id, "casepack": p.casepack, "inner_pack": p.inner_pack, "receta": recetas.dict_posicion(p)}


def estado_posicion(oc, p, facturado: int, facturas: list[dict]):
    """Devuelve (estado, motivo, factura a la que queda restringido el saldo)."""
    disponible = p.cantidad - facturado
    if not OC.puede("facturar", oc.estado):
        return "NO_DISPONIBLE", f"The PO is {OC.texto(oc.estado)}: it cannot be invoiced.", None
    if not oc.liberada:
        return "NO_DISPONIBLE", "The PO is not released yet: it cannot be invoiced.", None
    if p.bloqueada:
        return "NO_DISPONIBLE", p.motivo_bloqueo or "Line blocked.", None
    if disponible <= 0:
        return "FACTURADA", None, None
    if facturado > 0:
        if not regla("POSICION_EN_VARIAS_FACTURAS") and facturas:
            f = facturas[0]
            return "PARCIAL", f"The balance can only be added to {f['nombre']}.", f["id"]
        return "PARCIAL", None, None
    return "DISPONIBLE", None, None


# ---- Importación ------------------------------------------------------------
# Nombres de columna que el sistema reconoce sin perfil (genéricos, en inglés y
# español). El primero es el de la plantilla. Los nombres propios del ERP de la
# empresa van en un perfil de importación (perfiles.py).
ALIAS = {
    "proveedor": ["supplier", "vendor", "supplier_code", "proveedor", "codigo_proveedor", "proveedor_codigo"],
    "oc": ["po", "po_number", "purchase_order", "oc", "orden", "orden_compra", "numero_oc"],
    "posicion": ["po_line", "line", "item", "posicion", "pos", "linea"],
    "sociedad": ["company", "company_code", "sociedad", "compania"],
    "centro": ["plant", "bonded_warehouse", "centro", "bodega", "bodega_fiscal"],
    "almacen": ["storage_location", "sloc", "almacen"],
    "centro_destino": ["destination", "destination_center", "destination_country", "centro_destino", "pais_destino",
                       "destino", "codigo_destino"],
    "moneda": ["currency", "moneda"],
    "incoterm": ["incoterm"],
    "fecha_oc": ["po_date", "fecha_oc", "fecha"],
    "puerto_despacho": ["port_of_loading", "pol", "port", "puerto_despacho", "puerto", "puerto_embarque"],
    "pais_origen": ["country_of_origin", "coo", "origin", "pais_origen", "origen"],
    "pais_procedencia": ["country_of_shipment", "provenance", "pais_procedencia", "procedencia"],
    "fecha_xf_original": ["xf_date_original", "original_xf_date", "fecha_xf_original", "xf_original"],
    "fecha_xf": ["xf_date", "xf", "updated_xf_date", "fecha_xf", "fecha_xf_actualizada", "xf_actualizada"],
    "fecha_tienda": ["in_store_date", "store_date", "fecha_tienda", "fecha_requerida_tienda", "fecha_requerida"],
    "liberacion_comercial": ["commercial_release", "liberacion_comercial", "lib_comercial", "liberada",
                             "estado_liberacion"],
    "liberacion_logistica": ["logistics_release", "liberacion_logistica", "lib_logistica"],
    "fecha_lib_comercial": ["commercial_release_date", "fecha_liberacion_comercial", "fecha_lib_comercial"],
    "fecha_lib_logistica": ["logistics_release_date", "fecha_liberacion_logistica", "fecha_lib_logistica"],
    "codigo_articulo": ["sku", "item_code", "material", "codigo", "codigo_sap", "articulo"],
    "cantidad": ["quantity", "qty", "cantidad"],
    "unidad": ["uom", "unit", "um", "unidad"],
    "precio": ["unit_price", "price", "precio", "precio_unitario"],
    "casepack": ["casepack", "case_pack"],
    "inner_pack": ["inner_pack", "inner", "innerpack", "inner_casepack", "pack"],
    "fecha_entrega": ["delivery_date", "fecha_entrega", "entrega"],
}
# Lo mínimo para registrar una OC; el resto es opcional y lo que falte para
# facturar (empresa, moneda, precio) se pide al facturar
REQUERIDOS = ["proveedor", "oc", "posicion", "codigo_articulo", "cantidad"]
NOMBRE_CAMPO = {"proveedor": "supplier", "oc": "PO number", "posicion": "PO line", "codigo_articulo": "item code",
                "cantidad": "quantity"}
CAMPOS_CABECERA = ["sociedad", "centro", "centro_destino", "moneda", "incoterm", "fecha", "puerto_despacho",
                   "pais_origen", "pais_procedencia", "fecha_xf_original", "fecha_xf", "fecha_tienda",
                   "liberacion_comercial"]
CAMPOS_POSICION = [
    "almacen", "articulo_id", "codigo_articulo", "codigo_barras", "descripcion",
    "tipo_empaque", "casepack", "inner_pack", "codigo_pack", "unidades_por_caja", "cantidad", "unidad", "precio", "fecha_entrega",
    "pais_origen",
]


def _norm(texto: str) -> str:
    t = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode().lower()
    return "_".join("".join(c if c.isalnum() else " " for c in t).split())


def _texto(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    if isinstance(v, datetime):
        return v.date().isoformat()
    if isinstance(v, date):
        return v.isoformat()
    return str(v).strip()


def _leer_archivo(nombre: str, contenido: bytes, perfil=None) -> list[dict]:
    """Filas del archivo como {campo: texto}. Con un perfil de importación, sus
    nombres de columna mandan, los encabezados van en su fila, las fechas se
    leen con su formato y lo que falta toma sus valores por defecto."""
    inicio = (perfil.fila_encabezado if perfil else 1) - 1
    if nombre.lower().endswith((".xlsx", ".xlsm")):
        wb = abrir_libro(contenido, read_only=True, data_only=True)
        ws = wb.active
        filas = list(ws.iter_rows(values_only=True))[inicio:]
        if not filas:
            return []
        encabezados = [_texto(h) for h in filas[0]]
        datos = [[_texto(v) for v in fila] for fila in filas[1:]]
    else:
        texto = contenido.decode("utf-8-sig", errors="replace")
        muestra = texto[:2000]
        delimitador = ";" if muestra.count(";") > muestra.count(",") else ","
        lector = list(csv.reader(io.StringIO(texto), delimiter=delimitador))[inicio:]
        if not lector:
            return []
        encabezados = lector[0]
        datos = [[v.strip() for v in fila] for fila in lector[1:]]

    propios = {c: [_norm(x) for x in str(v).split(",") if x.strip()] for c, v in ((perfil.columnas or {}) if perfil else {}).items()}
    normalizados = [_norm(h) for h in encabezados]
    # Campos propios de las OCs: se reconocen por su nombre o su clave
    extra = {f"extra.{c['clave']}": [_norm(c["etiqueta"]), _norm(c["clave"])] for c in campos_propios.definiciones("ordenes")}
    mapa = {}
    for fuente in (propios, ALIAS, extra):  # primero los nombres del perfil
        for campo, nombres in fuente.items():
            i = next((i for i, n in enumerate(normalizados) if n in nombres), None)
            if campo not in mapa and i is not None:
                mapa[campo] = i
    defectos = (perfil.valores or {}) if perfil else {}
    faltan = [c for c in REQUERIDOS if c not in mapa]
    if faltan:
        nombres = [((perfil.columnas or {}).get(c) if perfil else None) or ALIAS[c][0] for c in faltan]
        raise ErrorNegocio(
            "The file is missing required columns: " + ", ".join(nombres) + ".",
            422,
            "columnas_faltantes",
            {"faltan": faltan, "encontradas": encabezados},
        )
    filas_dict = []
    for n_fila, fila in enumerate(datos, start=inicio + 2):
        if not any(fila):
            continue
        registro = {campo: (fila[i] if i < len(fila) else "") for campo, i in mapa.items()}
        for campo, valor in defectos.items():
            if not registro.get(campo):
                registro[campo] = valor
        if perfil and perfil.formato_fecha:
            for campo in registro:
                if campo.startswith("fecha") and registro[campo]:
                    registro[campo] = perfiles.fecha_iso(registro[campo], perfil.formato_fecha)
        registro["_fila"] = n_fila
        filas_dict.append(registro)
    return filas_dict


def _fecha(valor: str) -> date | None:
    # ISO o el formato de fecha del usuario (con su orden día/mes para no confundirlos)
    return leer_fecha(valor)


class Maestros:
    """Catálogos precargados para validar un archivo completo sin consultas por fila."""

    def __init__(self, db: Session):
        self.lib = liberaciones.de(db)
        self.proveedores = {p.codigo: p for p in db.scalars(select(Proveedor))}
        self.sociedades = {s.codigo: s for s in db.scalars(select(Sociedad))}
        self.centros = {c.codigo: c for c in db.scalars(select(Centro))}
        self.almacenes = {a.codigo: a for a in db.scalars(select(Almacen))}
        self.puertos = {p.codigo: p for p in db.scalars(select(Puerto))}
        self.paises = {p.codigo for p in db.scalars(select(Pais))}
        self.articulos: dict[str, catalogo.FichaArticulo | None] = {}
        self._db = db
        # Códigos escritos de otra forma (minúsculas, espacios, por nombre) -> código real
        from app.modulos.comun.normalizar import Referencias

        self.refs = {"proveedor": Referencias(db, Proveedor), "sociedad": Referencias(db, Sociedad),
                     "centro": Referencias(db, Centro), "almacen": Referencias(db, Almacen),
                     "puerto": Referencias(db, Puerto), "pais": Referencias(db, Pais)}

    def canon(self, tabla: str, valor):
        obj = self.refs[tabla].buscar(valor)
        return obj.codigo if obj else valor

    def articulo(self, codigo: str) -> catalogo.FichaArticulo | None:
        if codigo not in self.articulos:
            self.articulos[codigo] = catalogo.por_codigo(self._db, codigo)
        return self.articulos[codigo]


PAIS_TXT = {"pais_origen": "country of origin", "pais_procedencia": "country of shipment"}


def _normalizar(registro: dict, m: Maestros) -> tuple[dict, list[str]]:
    """Convierte los textos de una fila en valores tipados y la valida contra
    los datos maestros. Los códigos se mantienen como texto."""
    errores = []
    r = {k: (v or "").strip() for k, v in registro.items() if k != "_fila"}
    for campo in REQUERIDOS:
        if not r.get(campo):
            errores.append(f"Missing: {NOMBRE_CAMPO[campo]}.")
    d = {
        "proveedor": r.get("proveedor", "").upper(),
        "oc": r.get("oc", ""),
        "posicion": r.get("posicion", "").lstrip("0") or r.get("posicion", ""),
        "sociedad": r.get("sociedad", "").upper(),
        "centro": (r.get("centro") or "").upper() or None,
        "almacen": (r.get("almacen") or "").upper() or None,
        "centro_destino": r.get("centro_destino") or None,
        "moneda": (r.get("moneda") or "").upper(),
        "incoterm": (r.get("incoterm") or "").upper() or None,
        "puerto_despacho": (r.get("puerto_despacho") or "").upper() or None,
        "pais_origen": (r.get("pais_origen") or "").upper() or None,
        "pais_procedencia": (r.get("pais_procedencia") or r.get("pais_origen") or "").upper() or None,
        "liberacion_comercial": (r.get("liberacion_comercial") or "").strip() or None,
        "liberacion_logistica_archivo": (r.get("liberacion_logistica") or "").strip() or None,
        "codigo_articulo": r.get("codigo_articulo", ""),
    }
    com = m.lib.comercial.leer(d["liberacion_comercial"])
    if com is False:
        errores.append(f"Invalid commercial release {d['liberacion_comercial']} (use {m.lib.comercial.ayuda()}).")
        com = None
    d["liberacion_comercial"] = com or m.lib.comercial.predeterminado()
    log = m.lib.logistica.leer(d["liberacion_logistica_archivo"])
    d["liberacion_logistica_archivo"] = log
    if log is False:
        errores.append(f"Invalid logistics release {r.get('liberacion_logistica')} (use {m.lib.logistica.ayuda()}).")
        log = d["liberacion_logistica_archivo"] = None
    elif log and m.lib.logistica.libera(log) and not m.lib.comercial.libera(d["liberacion_comercial"]):
        errores.append(f"Logistics cannot release ({log}) without commercial release.")
    if d["oc"] and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._\-/]{0,39}", d["oc"]):
        errores.append(f"PO {d['oc']}: letters and numbers (also . - _ /), up to 40 characters.")
    if d["posicion"] and not re.fullmatch(r"[A-Za-z0-9]{1,10}", d["posicion"]):
        errores.append(f"Line {d['posicion']}: letters and numbers, up to 10 characters.")
    try:
        cant = float(r.get("cantidad", "").replace(",", "")) if r.get("cantidad") else None
        if cant is not None and cant < 0:
            raise ValueError
        d["cantidad"] = cant_norm(cant)
    except ValueError:
        errores.append(f"Invalid quantity: {r.get('cantidad')}.")
        d["cantidad"] = None
    try:
        d["precio"] = float(r.get("precio", "").replace(",", "")) if r.get("precio") else None
        if d["precio"] is not None and d["precio"] < 0:
            raise ValueError
    except ValueError:
        errores.append(f"Invalid price: {r.get('precio')}.")
        d["precio"] = None
    # Empaque de la compra: viene en la posición de la OC, no en el artículo
    for campo, texto in (("casepack", "Casepack"), ("inner_pack", "Inner pack")):
        try:
            d[campo] = int(float(r[campo])) if r.get(campo) else None
            if d[campo] is not None and d[campo] < 1:
                raise ValueError
        except ValueError:
            errores.append(f"Invalid {texto.lower()}: {r.get(campo)}.")
            d[campo] = None
    unidad = unidad_de(r.get("unidad"))
    if r.get("unidad") and not unidad:
        errores.append(f"Unknown unit: {r.get('unidad')} (use PAR, UN or CJ).")
    d["unidad"] = unidad
    for campo, destino in (("fecha_oc", "fecha"), ("fecha_entrega", "fecha_entrega"),
                           ("fecha_xf_original", "fecha_xf_original"), ("fecha_xf", "fecha_xf"),
                           ("fecha_tienda", "fecha_tienda"), ("fecha_lib_comercial", "fecha_lib_comercial"),
                           ("fecha_lib_logistica", "fecha_lib_logistica")):
        try:
            d[destino] = _fecha(r.get(campo, ""))
        except ValueError as e:
            errores.append(str(e).capitalize() + ".")
            d[destino] = None
    if d["precio"] is not None and not d["moneda"]:
        errores.append("Enter the currency of the price.")
    if d["cantidad"] == 0:
        errores.append("The quantity must be greater than zero.")
    d["moneda"] = d["moneda"] or None
    d["sociedad"] = d["sociedad"] or None
    d["fecha_xf_original"] = d["fecha_xf_original"] or d["fecha_xf"]
    d["fecha_xf"] = d["fecha_xf"] or d["fecha_xf_original"]
    try:
        d["extra"] = campos_propios.limpiar("ordenes", {k[6:]: v for k, v in r.items() if k.startswith("extra.")})
    except ErrorNegocio as e:
        errores += [x["mensaje"] for x in e.detalle or []]
        d["extra"] = {}

    if m is None:
        return d, errores
    for campo, tabla in (("proveedor", "proveedor"), ("sociedad", "sociedad"), ("centro", "centro"), ("almacen", "almacen"),
                         ("centro_destino", "centro"), ("puerto_despacho", "puerto"), ("pais_origen", "pais"),
                         ("pais_procedencia", "pais")):
        if d.get(campo):
            d[campo] = m.canon(tabla, d[campo])
    # Datos maestros. Todo queda encadenado: el proveedor trabaja con la
    # sociedad; centro, almacén y centro destino son de esa sociedad; el
    # artículo y su marca son del proveedor. Sin sociedad, se toma la del
    # centro o almacén indicado.
    if not d["sociedad"]:
        for campo, tabla in (("centro", m.centros), ("almacen", m.almacenes), ("centro_destino", m.centros)):
            x = tabla.get(d[campo]) if d[campo] else None
            if x and x.sociedad:
                d["sociedad"] = x.sociedad.codigo
                break
    soc = m.sociedades.get(d["sociedad"])
    if d["sociedad"] and not soc:
        errores.append(f"Company {d['sociedad']} does not exist.")
    cen = m.centros.get(d["centro"]) if d["centro"] else None
    if d["centro"] and not cen:
        errores.append(f"Plant {d['centro']} does not exist.")
    elif cen and soc and cen.sociedad_id != soc.id:
        errores.append(f"Plant {d['centro']} does not belong to company {d['sociedad']}.")
    if d["almacen"]:
        alm = m.almacenes.get(d["almacen"])
        if not alm:
            errores.append(f"Storage location {d['almacen']} does not exist.")
        elif soc and alm.sociedad_id != soc.id:
            errores.append(f"Storage location {d['almacen']} does not belong to company {d['sociedad']}.")
    prov = m.proveedores.get(d["proveedor"])
    if prov and not prov.activo:
        errores.append(f"Supplier {prov.nombre} is inactive.")
    if prov and soc and soc.id not in {x.id for x in prov.sociedades}:
        errores.append(f"Supplier {prov.nombre} does not work with company {d['sociedad']}. "
                       "Assign the company to the supplier in master data first.")
    destino = m.centros.get(d["centro_destino"]) if d["centro_destino"] else None
    if d["centro_destino"] and not destino:
        errores.append(f"Destination center {d['centro_destino']} is not registered in master data.")
    elif destino and soc and destino.sociedad_id != soc.id:
        errores.append(f"Destination center {d['centro_destino']} does not belong to company {d['sociedad']}.")
    if d["puerto_despacho"] and d["puerto_despacho"] not in m.puertos:
        errores.append(f"Port {d['puerto_despacho']} is not registered.")
    # Moneda e incoterm: de las listas de la empresa (Datos maestros → Listas de valores)
    if d["moneda"] and d["moneda"] not in listas.codigos("moneda"):
        errores.append(f"Currency {d['moneda']} is not in the list of currencies.")
    if d["incoterm"] and d["incoterm"] not in listas.codigos("incoterm"):
        errores.append(f"Incoterm {d['incoterm']} is not in the list of Incoterms.")
    for campo in ("pais_origen", "pais_procedencia"):
        if d[campo] and d[campo] not in m.paises:
            errores.append(f"Country {d[campo]} ({PAIS_TXT[campo]}) is not registered.")
    art = m.articulo(d["codigo_articulo"]) if d["codigo_articulo"] else None
    if d["codigo_articulo"] and not art:
        errores.append(f"SKU {d['codigo_articulo']} does not exist in the item master. Load it first.")
    elif art:
        prov = m.proveedores.get(d["proveedor"])
        if prov and art.proveedor_id and art.proveedor_id != prov.id:
            errores.append(f"SKU {art.codigo} belongs to another supplier, not {prov.nombre}.")
        elif prov and art.marca and art.marca not in {x.codigo for x in prov.marcas}:
            errores.append(f"Brand {art.marca} of SKU {art.codigo} is not a brand of {prov.nombre}.")
        if not art.activo:
            errores.append(f"SKU {art.codigo} is inactive in the item master.")
        if d["unidad"] and d["unidad"] != art.unidad:
            errores.append(f"Unit {d['unidad']} does not match the item master ({art.unidad}).")
        d.update(
            articulo_id=art.id, codigo_barras=art.codigo_barras, descripcion=art.descripcion,
            tipo_empaque=art.tipo, unidad=art.unidad, codigo_pack=art.codigo_pack,
            unidades_por_caja=art.total_componentes if art.es_pack else None,
        )
        errores += validar_empaque(art.tipo, d["casepack"], d["inner_pack"], d["cantidad"])
        if d["cantidad"] and (msg := error_cantidad(d["cantidad"], art.unidad)):
            errores.append(msg)
        ficha = comex.de_articulos(m._db, [art.id]).get(art.id)
        d["pais_origen_pos"] = (ficha.pais_origen if ficha else None) or d["pais_origen"]
    return d, errores


def validar_empaque(tipo: str, casepack: int | None, inner_pack: int | None, cantidad: int | None) -> list[str]:
    """Reglas del empaque de una posición:
    - un pack o kit ya es una caja definida (su contenido): no lleva casepack ni inner pack;
    - con casepack e inner pack, el casepack es múltiplo del inner pack;
    - con inner pack, la cantidad de la posición es múltiplo del inner pack
      (todos los inner packs llevan la misma cantidad)."""
    errores = []
    if tipo == catalogo.TIPO_PACK:
        if casepack or inner_pack:
            errores.append("A pack or kit is already a defined carton (its contents): it takes no casepack or inner pack.")
        return errores
    if casepack and inner_pack and casepack % inner_pack:
        errores.append(f"The casepack ({casepack}) must be a multiple of the inner pack ({inner_pack}).")
    if inner_pack and cantidad and cantidad % inner_pack:
        errores.append(f"The quantity ({cantidad}) must be a multiple of the inner pack ({inner_pack}): "
                       "all inner packs carry the same quantity.")
    return errores


def _valores_posicion(d: dict) -> dict:
    v = {c: d.get(c) for c in CAMPOS_POSICION}
    v["pais_origen"] = d.get("pais_origen_pos") or d.get("pais_origen")
    return v


def _clasificar(db: Session, filas: list[dict], propia: int | None = None) -> list[dict]:
    """Clasifica cada fila (nuevo, cambio, sin cambio, conflicto, error).
    `propia`: la OC que el asistente está enviando (su borrador sí se aplica)."""
    m = Maestros(db)
    vistos: set = set()
    cabeceras: dict = {}
    resultado = []
    normalizadas = [(r, *_normalizar(r, m)) for r in filas]

    claves_oc = {(d["proveedor"], d["oc"]) for _, d, _ in normalizadas}
    ocs_existentes = {}
    for codigo, numero in claves_oc:
        prov = m.proveedores.get(codigo)
        if prov:
            oc = db.scalar(select(OrdenCompra).where(OrdenCompra.proveedor_id == prov.id, OrdenCompra.numero == numero))
            if oc:
                ocs_existentes[(codigo, numero)] = oc
    ids_pos = [p.id for oc in ocs_existentes.values() for p in oc.posiciones]
    facturado = facturado_por_posicion(db, ids_pos)

    for registro, d, errores in normalizadas:
        clave = f"{d['proveedor']} / PO {d['oc']} / line {d['posicion']}"
        salida = {"fila": registro.get("_fila"), "clave": clave, "datos": registro,
                  "mensajes": list(errores), "cambios": {}}
        if d["proveedor"] and d["proveedor"] not in m.proveedores:
            salida["mensajes"].append(f"Supplier {d['proveedor']} does not exist.")
        k = (d["proveedor"], d["oc"], d["posicion"])
        if k in vistos:
            salida["mensajes"].append("Line repeated within the file.")
        vistos.add(k)
        cab = {c: d.get(c) for c in CAMPOS_CABECERA} | {"extra": d.get("extra") or {}}
        previa = cabeceras.setdefault((d["proveedor"], d["oc"]), cab)
        if previa != cab:
            salida["mensajes"].append("The header data does not match other rows of the same PO.")
        if salida["mensajes"]:
            salida["estado"] = "error"
            resultado.append(salida)
            continue

        oc = ocs_existentes.get((d["proveedor"], d["oc"]))
        if oc and oc.id != propia and not OC.puede("importar", oc.estado):
            salida["estado"] = "conflicto"
            salida["mensajes"].append(f"The PO is {OC.texto(oc.estado)} in the platform: a file cannot change it.")
            resultado.append(salida)
            continue
        pos = next((p for p in oc.posiciones if p.posicion == d["posicion"]), None) if oc else None
        if not pos:
            salida["estado"] = "nuevo"
            resultado.append(salida)
            continue

        cambios = {}
        for c in CAMPOS_CABECERA:
            anterior = getattr(oc, c)
            if anterior != d.get(c):
                cambios[c] = {"antes": anterior, "despues": d.get(c)}
        for k, v in (d.get("extra") or {}).items():
            if (oc.extra or {}).get(k) != v:
                cambios[f"extra.{k}"] = {"antes": (oc.extra or {}).get(k), "despues": v}
        for c, nuevo in _valores_posicion(d).items():
            if c == "articulo_id":
                continue
            anterior = getattr(pos, c)
            igual = abs(anterior - nuevo) < 1e-9 if isinstance(anterior, float) and nuevo is not None else anterior == nuevo
            if not igual:
                cambios[c] = {"antes": anterior, "despues": nuevo}
        salida["cambios"] = cambios
        fact = facturado.get(pos.id, 0)
        if not cambios:
            salida["estado"] = "sin_cambio"
        elif fact and d["cantidad"] is not None and d["cantidad"] < fact:
            salida["estado"] = "conflicto"
            salida["mensajes"].append(f"The new quantity ({d['cantidad']}) is less than what is already invoiced ({fact}).")
        elif fact and any(c in cambios for c in ("sociedad", "moneda", "centro", "unidad", "codigo_articulo")):
            salida["estado"] = "conflicto"
            salida["mensajes"].append(
                "Key data (company, currency, plant, SKU or unit) changes on an already invoiced line.")
        elif fact and any(c in cambios for c in ("casepack", "inner_pack")):
            salida["estado"] = "conflicto"
            salida["mensajes"].append("The casepack or inner pack changes on a line that is already invoiced.")
        else:
            salida["estado"] = "cambio"
        resultado.append(salida)
    return resultado


def _resumen(clasificadas: list[dict]) -> dict:
    res = {"nuevo": 0, "cambio": 0, "sin_cambio": 0, "conflicto": 0, "error": 0}
    for c in clasificadas:
        res[c["estado"]] += 1
    res["total"] = len(clasificadas)
    return res


def importar_previa(db: Session, user: Usuario, nombre: str, contenido: bytes, perfil_id: int | None = None) -> dict:
    exigir(user, "oc.importar")
    filas = _leer_archivo(nombre, contenido, perfiles.elegido(db, perfil_id))
    if not filas:
        raise ErrorNegocio("The file has no rows with data.", 422, "archivo_vacio")
    tope_filas(len(filas))
    clasificadas = _clasificar(db, filas)
    imp = ImportacionOC(usuario_id=user.id, nombre_archivo=nombre, filas=filas)
    db.add(imp)
    db.flush()
    return {
        "importacion_id": imp.id,
        "archivo": nombre,
        "resumen": _resumen(clasificadas),
        "filas": [{k: v for k, v in c.items() if k != "datos"} for c in clasificadas],
    }


def importar_aplicar(db: Session, user: Usuario, importacion_id: int) -> dict:
    exigir(user, "oc.importar")
    imp = db.get(ImportacionOC, importacion_id)
    if not imp:
        raise ErrorNegocio("The import does not exist.", 404, "no_encontrado")
    return aplicar_importacion(db, user, imp)


def aplicar_importacion(db: Session, user: Usuario, imp: ImportacionOC, propia: int | None = None,
                        formulario: bool = False) -> dict:
    """Aplica las filas de una carga (archivo, formulario o asistente). Las OCs
    nuevas entran aprobadas (vienen del ERP) salvo que la empresa pida aprobarlas
    también aquí; cada OC creada o cambiada deja sus cambios en su historial."""
    from app.modulos.compras import flujo_oc

    if imp.estado == "APLICADA":
        return {"ya_aplicada": True, **(imp.resultado or {})}
    # Se vuelve a clasificar: los datos pudieron cambiar desde la vista previa
    clasificadas = _clasificar(db, imp.filas, propia)
    m = Maestros(db)
    aplicadas = 0
    motor = None  # reglas de empaque, cargadas una vez
    ocs_tocadas: dict[int, dict] = {}
    for c in clasificadas:
        if c["estado"] == "conflicto":
            d, _ = _normalizar(c["datos"], m)
            prov = m.proveedores.get(d["proveedor"])
            db.add(Alerta(proveedor_id=prov.id if prov else None, tipo="conflicto_oc",
                          mensaje=f"{c['clave']}: " + " ".join(c["mensajes"]),
                          referencia={"importacion_id": imp.id, "fila": c["fila"]}))
        if c["estado"] not in ("nuevo", "cambio"):
            continue
        d, _ = _normalizar(c["datos"], m)
        prov = m.proveedores[d["proveedor"]]
        oc = db.scalar(select(OrdenCompra).where(OrdenCompra.proveedor_id == prov.id, OrdenCompra.numero == d["oc"]))
        nueva = oc is None
        if nueva:
            # Sin liberación logística hasta decidirla al final (abajo)
            oc = OrdenCompra(proveedor_id=prov.id, numero=d["oc"], liberacion_logistica=m.lib.logistica.sin_liberar() or "",
                             estado="APROBADA", origen="ERP", creada_por=user.id if user else None)
            db.add(oc)
        info = ocs_tocadas.setdefault(id(oc), {
            "oc": oc, "cambios": False, "explicita": d["liberacion_logistica_archivo"],
            "actual": None if nueva else oc.liberacion_logistica, "nueva": nueva, "lineas": 0, "detalle": {}})
        info["cambios"] = info["cambios"] or (c["estado"] == "cambio")
        info["lineas"] += 1
        for campo, cambio in (c.get("cambios") or {}).items():
            info["detalle"].setdefault(f"{d['posicion']}.{campo}" if campo in CAMPOS_POSICION + ["cantidad", "precio", "unidad"]
                                       else campo, cambio)
        for campo in CAMPOS_CABECERA:
            setattr(oc, campo, d.get(campo))
        if d.get("extra"):
            oc.extra = {**(oc.extra or {}), **d["extra"]}
        # Fechas de liberación: las del archivo si vienen; si no, el día en que se liberó
        for campo in ("fecha_lib_comercial", "fecha_lib_logistica"):
            if d.get(campo):
                setattr(oc, campo, d[campo])
        oc.actualizado_en = ahora()
        db.flush()
        pos = db.scalar(select(PosicionOC).where(PosicionOC.oc_id == oc.id, PosicionOC.posicion == d["posicion"]))
        if not pos:
            pos = PosicionOC(oc_id=oc.id, posicion=d["posicion"])
            db.add(pos)
        for campo, valor in _valores_posicion(d).items():
            setattr(pos, campo, valor)
        motor = motor or recetas.Motor(db)
        recetas.asignar(db, pos, oc, motor, trae_empaque=d.get("casepack") is not None)
        aplicadas += 1
    for info in ocs_tocadas.values():
        oc = info["oc"]
        oc.liberacion_logistica = m.lib.logistica_final(oc.liberacion_comercial, info["explicita"], info["actual"],
                                                        info["cambios"])
        oc.liberada = m.lib.liberada(oc.liberacion_comercial, oc.liberacion_logistica)
        m.lib.fechar(oc)
        if oc.id == propia or formulario:
            continue  # el asistente o el formulario deciden su estado y su historial
        db.flush()
        if info["nueva"] and regla("APROBAR_OC_IMPORTADAS"):
            flujo_oc.iniciar_aprobacion(db, user, oc)
        detalle = {"archivo": imp.nombre_archivo, "lineas": info["lineas"]}
        if not info["nueva"] and info["detalle"]:
            detalle["cambios"] = dict(list(info["detalle"].items())[:60])
        registrar(db, user, "orden", oc.id, "importada" if info["nueva"] else "actualizada", detalle)
    # Las OCs creadas o cambiadas: la capa de integración guarda su referencia externa
    ocs = [{"id": i["oc"].id, "numero": i["oc"].numero, "proveedor": i["oc"].proveedor.codigo, "nueva": i["nueva"]}
           for i in ocs_tocadas.values() if i["oc"].id is not None]
    resultado = {"resumen": _resumen(clasificadas), "aplicadas": aplicadas, "ocs": ocs}
    imp.estado = "APLICADA"
    imp.resultado = resultado
    registrar(db, user, "importacion_oc", imp.id, "aplicar", resultado)
    return resultado


# ---- Alta desde el formulario ------------------------------------------------------
# El formulario arma las mismas filas que un archivo de carga: una por línea con
# los datos de la cabecera; se validan y se guardan con el mismo proceso.
CAMPOS_FORM_CAB = ("proveedor", "oc", "sociedad", "centro", "centro_destino", "moneda", "incoterm", "fecha_oc",
                   "puerto_despacho", "pais_origen", "pais_procedencia", "fecha_xf", "fecha_tienda",
                   "liberacion_comercial", "liberacion_logistica")
CAMPOS_FORM_LINEA = ("posicion", "codigo_articulo", "cantidad", "precio", "unidad", "casepack", "inner_pack", "almacen",
                     "fecha_entrega")


def crear_oc(db: Session, user: Usuario, datos: dict) -> dict:
    """Orden de compra creada en la plataforma de una sola vez (sin borrador):
    misma estructura y mismas validaciones que la carga masiva, y pasa por las
    reglas de aprobación como la del asistente."""
    from app.modulos.compras import flujo_oc

    exigir(user, "oc.editar")
    cab = {k: _texto(v) for k, v in (datos.get("cabecera") or {}).items() if k in CAMPOS_FORM_CAB}
    permitidos = proveedores_de(user)
    if permitidos is not None:  # solo OCs de los proveedores de su alcance
        prov = db.scalar(select(Proveedor).where(Proveedor.codigo == str(cab.get("proveedor") or "").upper()))
        if not prov or prov.id not in permitidos:
            unico = un_proveedor(permitidos)
            prov = db.get(Proveedor, unico) if unico else None
        cab["proveedor"] = prov.codigo if prov else ""
    lineas = [x for x in (datos.get("lineas") or []) if any(_texto(v) for v in x.values())]
    if not lineas:
        raise ErrorNegocio("Add at least one line.", 422, "validacion", [{"campo": "lineas", "mensaje": "Add at least one line."}])
    filas = []
    for i, linea in enumerate(lineas, start=1):
        fila = {**cab, **{k: _texto(v) for k, v in linea.items() if k in CAMPOS_FORM_LINEA}, "_fila": i}
        fila["posicion"] = fila.get("posicion") or str(i * 10)
        filas.append(fila)
    m = Maestros(db)
    prov = m.proveedores.get((cab.get("proveedor") or "").upper())
    if prov and cab.get("oc") and db.scalar(select(OrdenCompra.id).where(
            OrdenCompra.proveedor_id == prov.id, OrdenCompra.numero == cab["oc"])):
        raise ErrorNegocio(f"PO {cab['oc']} already exists for this supplier.", 409, "duplicado",
                           [{"campo": "oc", "mensaje": f"PO {cab['oc']} already exists for this supplier."}])
    clasificadas = _clasificar(db, filas)
    malas = [c for c in clasificadas if c["estado"] in ("error", "conflicto")]
    if malas:
        # Lo que falla en todas las líneas es de la cabecera; lo demás, de su línea
        comunes = set.intersection(*(set(c["mensajes"]) for c in clasificadas)) if len(malas) == len(clasificadas) else set()
        errores = [{"campo": "cabecera", "mensaje": x} for x in sorted(comunes)]
        for c in malas:
            errores += [{"campo": f"lineas.{c['fila'] - 1}", "mensaje": f"Line {c['fila']}: {x}"}
                        for x in c["mensajes"] if x not in comunes]
        raise ErrorNegocio("Check the purchase order.", 422, "validacion", errores)
    imp = ImportacionOC(usuario_id=user.id, nombre_archivo="(form)", filas=filas)
    db.add(imp)
    db.flush()
    resultado = aplicar_importacion(db, user, imp, formulario=True)
    oc = db.scalar(select(OrdenCompra).where(OrdenCompra.proveedor_id == m.proveedores[cab["proveedor"].upper()].id,
                                             OrdenCompra.numero == cab["oc"]))
    oc.origen = "PLATAFORMA"
    flujo_oc.iniciar_aprobacion(db, user, oc)
    registrar(db, user, "orden", oc.id, "enviada", {"numero": oc.numero, "lineas": resultado["aplicadas"], "origen": "formulario",
                                                     "estado": oc.estado})
    return {"oc_id": oc.id, "numero": oc.numero, "lineas": resultado["aplicadas"]}


def moneda_base() -> str | None:
    """Moneda de la empresa (Configuración → Empresa) o la primera de la lista."""
    from app.core.empresa import configuracion_actual

    return (configuracion_actual().get("preferencias") or {}).get("moneda") or next(iter(listas.codigos("moneda")), None)


def plantilla_oc(db: Session, user: Usuario) -> bytes:
    """Plantilla de carga de OC en Excel, con las fechas de ejemplo en el
    formato del usuario (el mismo con el que se leerán)."""
    from datetime import timedelta

    from app.modulos.acceso.preferencias import actual, fecha_txt
    from app.modulos.documentos.plantillas import plantilla

    hoy = date.today()
    fechas = {"fecha_oc": hoy, "fecha_xf_original": hoy + timedelta(days=45), "fecha_xf": hoy + timedelta(days=50),
              "fecha_tienda": hoy + timedelta(days=100), "fecha_lib_comercial": None, "fecha_lib_logistica": None,
              "fecha_entrega": None}
    ayudas = {"proveedor": "Supplier code.", "oc": "PO number (letters and numbers, up to 40).", "posicion": "Line number.",
              "codigo_articulo": "Item code from the item master.", "cantidad": "Quantity in the item unit.",
              "sociedad": "Company (bill to). Optional; needed to invoice.", "moneda": "Needed if there is a price.",
              "precio": "Optional; needed to invoice.", "casepack": "Solids: exact quantity per carton (optional).",
              "inner_pack": "Usually defined later in the packing list.",
              "liberacion_comercial": "",
              "liberacion_logistica": ""}
    # Códigos de liberación de la empresa (Datos maestros → Estados de liberación)
    lib = liberaciones.de(db)
    ayudas["liberacion_comercial"] = f"{lib.comercial.ayuda()} (or the words)."
    ayudas["liberacion_logistica"] = f"{lib.logistica.ayuda()} (or the words)."
    formato = actual()["formato_fecha"]
    columnas = []
    for campo, alias in ALIAS.items():
        ayuda = ayudas.get(campo, "")
        if campo.startswith("fecha"):
            ayuda = (ayuda + " " if ayuda else "") + f"Date as {formato} (your profile setting) or YYYY-MM-DD."
        columnas.append({"nombre": alias[0], "req": campo in REQUERIDOS, "ayuda": ayuda})
    base = {"proveedor": "SUPPLIER", "oc": "PO-0001", "sociedad": "",
            "moneda": moneda_base() or "", "incoterm": next(iter(listas.codigos("incoterm")), ""),
            "liberacion_comercial": lib.comercial.predeterminado() or "",
            "liberacion_logistica": next((x.codigo for x in lib.logistica.lista if x.libera and not x.con_cambios), ""), "unidad": "", "precio": 10.5, "casepack": 12}
    ejemplos = []
    for linea, cant in ((10, 48), (20, 36)):
        fila = {**base, "posicion": linea, "codigo_articulo": "ITEM-CODE", "cantidad": cant,
                **{k: fecha_txt(v) for k, v in fechas.items() if v}}
        ejemplos.append([fila.get(c, "") for c in ALIAS])
    return plantilla("Purchase orders", columnas, ejemplos, [
        "One row per PO line; the header data (supplier, PO, company…) is repeated on each line.",
        "Columns with * are required. Company, currency and price can be completed later; they are needed to invoice.",
        f"Dates: {formato} — the format chosen in your profile — or YYYY-MM-DD. Excel date cells are also read.",
    ])


def opciones_formulario(db: Session, user: Usuario) -> dict:
    """Listas para el formulario y el asistente de OC (códigos, como en el archivo de carga)."""
    exigir_alguno(user, "oc.editar", "oc.importar")
    provs = db.scalars(select(Proveedor).where(Proveedor.activo.is_(True),
                                               *([Proveedor.id.in_(proveedores_de(user))] if proveedores_de(user) is not None else []))
                       .order_by(Proveedor.nombre)).all()
    op = lambda xs, f=lambda x: x.nombre: [{"valor": x.codigo, "texto": f"{x.codigo} · {f(x)}"} for x in xs]  # noqa: E731
    # Las monedas de la lista y las que ya traen las OCs (de antes de la lista)
    usadas = {m for (m,) in db.execute(select(OrdenCompra.moneda).distinct()) if m}
    monedas = listas.codigos("moneda") + sorted(usadas - set(listas.codigos("moneda")))
    return {
        # Cada proveedor lleva sus sociedades: el formulario solo ofrece esas
        "proveedores": [{**o, "sociedades": [x.codigo for x in p.sociedades]} for o, p in zip(op(provs), provs, strict=False)],
        "sociedades": op(db.scalars(select(Sociedad).order_by(Sociedad.codigo))),
        "centros": [{"valor": c.codigo, "texto": f"{c.codigo} · {c.nombre}", "sociedad": c.sociedad.codigo if c.sociedad else None}
                    for c in db.scalars(select(Centro).order_by(Centro.codigo))],
        "almacenes": [{"valor": a.codigo, "texto": f"{a.codigo} · {a.nombre}", "sociedad": a.sociedad.codigo if a.sociedad else None}
                      for a in db.scalars(select(Almacen).order_by(Almacen.codigo))],
        "puertos": op(db.scalars(select(Puerto).order_by(Puerto.codigo))),
        "paises": op(db.scalars(select(Pais).order_by(Pais.nombre))),
        "monedas": [{"valor": m, "texto": f"{m} · {listas.nombre('moneda', m)}" if listas.valor("moneda", m) else m}
                    for m in monedas],
        "incoterms": [{"valor": x["codigo"], "texto": f"{x['codigo']} · {x['nombre']}"} for x in listas.valores("incoterm")],
        "condiciones_pago": [{"valor": x["codigo"], "texto": x["nombre"]} for x in listas.valores("condicion_pago")],
        "unidades": [{"valor": x["codigo"], "texto": x["nombre"]} for x in listas.valores("unidad")],
        "moneda_base": moneda_base(),
        "obligatorios": sorted((empresa.configuracion_actual().get("obligatorios") or {}).get("orden") or []),
    }


def articulos_formulario(db: Session, user: Usuario, proveedor: str, q: str = "") -> list[dict]:
    """Artículos activos del proveedor para las líneas de la OC."""
    exigir_alguno(user, "oc.editar", "oc.importar")
    prov = db.scalar(select(Proveedor).where(Proveedor.codigo == (proveedor or "").upper()))
    if not prov or (proveedores_de(user) is not None and prov.id not in proveedores_de(user)):
        return []
    arts = catalogo.buscar(db, q, proveedor_id=prov.id, solo_activos=True, limite=300)
    fichas = comex.de_articulos(db, [a.id for a in arts])  # el origen es del producto (ficha técnica)

    def opcion(a: catalogo.FichaArticulo, ficha: comex.FichaComex | None) -> dict:
        return {"valor": a.codigo, "texto": " · ".join(x for x in (a.codigo, catalogo.texto(a.valores)) if x),
                "unidad": a.unidad, "tipo": a.tipo, "sub": a.descripcion, "pais_origen": ficha.pais_origen if ficha else None}

    return [opcion(a, fichas.get(a.id)) for a in arts]
