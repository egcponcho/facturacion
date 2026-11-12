from datetime import date

from sqlalchemy import Integer, cast, func, or_, select
from sqlalchemy.orm import Session

from app.core import dinero, listas
from app.core.empresa import regla
from app.core.errores import ErrorNegocio
from app.core.estados import OC
from app.modelos import (
    Centro,
    Factura,
    FacturaLinea,
    OrdenCompra,
    PosicionOC,
    Proveedor,
    Puerto,
    Usuario,
)
from app.modelos import cant as cant_norm
from app.modulos.acceso.permisos import (
    asegurar_proveedor,
    exigir,
    proveedor_filtro,
    sociedad_filtro,
)
from app.modulos.catalogo import servicio as catalogo
from app.modulos.comex import servicio as comex
from app.modulos.compras import liberaciones
from app.modulos.comun import tabla as tabla_datos
from app.modulos.comun.historial import registrar
from app.modulos.comun.texto import filtro_texto
from app.modulos.empaque import recetas
from app.modulos.facturacion.cantidades import facturado_por_posicion, facturas_por_posicion

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


