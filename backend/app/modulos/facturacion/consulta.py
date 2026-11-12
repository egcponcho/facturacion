"""Lectura de facturas: la lista con sus filtros y vistas, el detalle de una
factura (con su distribución en listas de empaque y su transporte), su
historial y sus archivos.
"""
import os
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import dinero
from app.core.archivos import DOCUMENTOS, MIME_DOCUMENTO, exigir_tamano, tipo_de
from app.core.empresa import regla
from app.core.errores import ErrorNegocio
from app.modelos import (
    Archivo,
    Factura,
    FacturaLinea,
    Historial,
    PackingList,
    PLLinea,
    Proveedor,
    Usuario,
    ahora,
)
from app.modelos import cant as cant_norm
from app.modulos.acceso.permisos import (
    es_interno,
    exigir,
    permisos_de,
    proveedor_filtro,
    sociedad_filtro,
)
from app.modulos.catalogo import servicio as catalogo
from app.modulos.comun import adjuntos, tabla
from app.modulos.comun.edicion import ajeno as ajeno_edicion
from app.modulos.comun.historial import registrar
from app.modulos.comun.texto import filtro_texto
from app.modulos.documentos.partes import partes
from app.modulos.facturacion.cantidades import (
    cubierto,
    nombre_factura,
    totales_pl,
)
from app.modulos.facturacion.estados import EDITABLE_FACTURA, EDITABLE_PL, fecha_devengo
from app.modulos.facturacion.facturas import cargar_factura, completar_aduana, validar_factura


# ---- Consultas --------------------------------------------------------------
def resumen_distribucion(db: Session, factura_ids) -> dict[int, dict]:
    ids = list(set(factura_ids))
    if not ids:
        return {}
    res = {i: {"facturado": 0, "asignado": 0, "pls": 0, "pls_finalizados": 0, "pls_confirmados": 0,
               "importe": 0, "lineas": 0} for i in ids}
    for fid, cant, n in db.execute(
        select(FacturaLinea.factura_id, func.sum(FacturaLinea.cantidad), func.count(FacturaLinea.id))
        .where(FacturaLinea.factura_id.in_(ids)).group_by(FacturaLinea.factura_id)
    ).all():
        res[fid].update(facturado=cant_norm(cant or 0), lineas=n)
    # Importe: suma de las líneas redondeadas a la moneda (igual que el detalle y el PDF)
    importes: dict[int, list] = {}
    monedas = dict(db.execute(select(Factura.id, Factura.moneda).where(Factura.id.in_(ids))).all())
    for fid, c, p in db.execute(select(FacturaLinea.factura_id, FacturaLinea.cantidad, FacturaLinea.precio_unitario)
                                .where(FacturaLinea.factura_id.in_(ids))).all():
        importes.setdefault(fid, []).append((c, p))
    for fid, ls in importes.items():
        res[fid]["importe"] = dinero.numero(dinero.total(ls, monedas.get(fid)))
    for fid, cant in db.execute(
        select(PackingList.factura_id, func.sum(PLLinea.cantidad))
        .join(PLLinea, PLLinea.pl_id == PackingList.id)
        .where(PackingList.factura_id.in_(ids), PackingList.estado != "CANCELADO")
        .group_by(PackingList.factura_id)
    ).all():
        res[fid]["asignado"] = cant_norm(cant or 0)
    for pl in db.scalars(
        select(PackingList).where(PackingList.factura_id.in_(ids), PackingList.estado != "CANCELADO")
    ).all():
        r = res[pl.factura_id]
        r["pls"] += 1
        r["pls_finalizados"] += pl.estado == "FINALIZADO"
        r["pls_confirmados"] += pl.asignacion == "CONFIRMADA"
    return res


def _lista_para_transporte(f: Factura, r: dict) -> bool:
    return (
        f.estado == "FINALIZADA"
        and r["facturado"] > 0
        and r["asignado"] == r["facturado"]
        and r["pls"] > 0
        and r["pls"] == r["pls_finalizados"]
    )


# Columnas de la tabla de facturas que se filtran por sus valores (app/web/tabla.py)
COLUMNAS_FACTURAS = {
    "nombre": Factura.numero, "proveedor": Proveedor.nombre, "estado": Factura.estado, "fecha": Factura.fecha,
    "moneda": Factura.moneda, "sociedad": Factura.sociedad, "centro": Factura.centro,
}


def _consulta_facturas(db: Session, user: Usuario, proveedor_id, estado, q, vista):
    """Facturas visibles para el usuario con la búsqueda, el estado y la vista
    elegidos (sin los filtros por columna)."""
    exigir(user, "factura.ver")
    prov = proveedor_filtro(user, proveedor_id)
    consulta = select(Factura).join(Proveedor, Proveedor.id == Factura.proveedor_id)
    if prov:
        consulta = consulta.where(Factura.proveedor_id.in_(prov))
    consulta = consulta.where(*sociedad_filtro(user, Factura.sociedad))
    if estado:
        consulta = consulta.where(Factura.estado == estado)
    if q:
        consulta = consulta.where(filtro_texto(q, lambda p: [
            Factura.numero.ilike(p), Factura.id.in_(select(FacturaLinea.factura_id).where(FacturaLinea.oc_numero.ilike(p)))]))
    if vista == "editables":
        consulta = consulta.where(Factura.estado.in_(EDITABLE_FACTURA))
    elif vista == "pl_incompletos":
        consulta = consulta.where(Factura.id.in_(
            select(PackingList.factura_id).where(PackingList.estado.in_(EDITABLE_PL))))
    elif vista == "pl_sin_unidad":
        consulta = consulta.where(Factura.id.in_(
            select(PackingList.factura_id).where(PackingList.estado == "FINALIZADO",
                                                 PackingList.unidad_carga_id.is_(None))))
    elif vista == "borradores_antiguos":
        limite = ahora() - timedelta(days=regla("DIAS_ALERTA_BORRADOR"))
        consulta = consulta.where(Factura.estado == "BORRADOR", Factura.creado_en < limite)
    elif vista == "lista_transporte":
        consulta = consulta.where(Factura.estado == "FINALIZADA")
    return consulta


def valores_facturas(db: Session, user: Usuario, columna: str, q: str | None, filtros: dict,
                     proveedor_id=None, estado=None, busqueda=None, vista=None) -> list[dict]:
    """Valores únicos de una columna de la tabla de facturas bajo los demás filtros."""
    expr = tabla.columna_valida(COLUMNAS_FACTURAS, columna)
    consulta = tabla.aplicar(_consulta_facturas(db, user, proveedor_id, estado, busqueda, vista), COLUMNAS_FACTURAS, filtros, excepto=columna)
    return tabla.valores(db, consulta, expr, q, contar=Factura.id)


def listar_facturas(
    db: Session,
    user: Usuario,
    proveedor_id: int | None = None,
    estado: str | None = None,
    q: str | None = None,
    vista: str | None = None,
    page: int = 1,
    size: int = 25,
    orden: str | None = None,
    filtros: dict | None = None,
    desde: date | None = None,
    hasta: date | None = None,
) -> dict:
    consulta = tabla.aplicar(_consulta_facturas(db, user, proveedor_id, estado, q, vista), COLUMNAS_FACTURAS, filtros or {})
    if desde or hasta:
        # Período por fecha de devengo: la misma que usan Inicio e Indicadores
        consulta = consulta.where(*([fecha_devengo() >= desde] if desde else []), *([fecha_devengo() <= hasta] if hasta else []))
    col, _, direccion = (orden or "").partition(":")
    expr = {"nombre": Factura.numero, "fecha": Factura.fecha, "estado": Factura.estado,
            "proveedor": Proveedor.nombre, "actualizado": Factura.actualizado_en}.get(col)
    if expr is not None:
        consulta = consulta.order_by(expr.desc().nullslast() if direccion == "desc" else expr.asc().nullslast(), Factura.id)
    else:
        consulta = consulta.order_by(Factura.actualizado_en.desc())

    if vista == "lista_transporte":
        todas = list(db.scalars(consulta).all())
        res = resumen_distribucion(db, [f.id for f in todas])
        todas = [f for f in todas if _lista_para_transporte(f, res[f.id]) and res[f.id]["pls_confirmados"] < res[f.id]["pls"]]
        total = len(todas)
        facturas = todas[(page - 1) * size: page * size]
    else:
        total = db.scalar(select(func.count()).select_from(consulta.subquery())) or 0
        facturas = list(db.scalars(consulta.offset((page - 1) * size).limit(size)).all())
        res = resumen_distribucion(db, [f.id for f in facturas])

    items = []
    for f in facturas:
        r = res[f.id]
        items.append({
            "id": f.id,
            "nombre": nombre_factura(f),
            "numero": f.numero,
            "proveedor_id": f.proveedor_id,
            "proveedor": f.proveedor.nombre,
            "fecha": f.fecha,
            "estado": f.estado,
            "moneda": f.moneda,
            "centro": f.centro,
            "sociedad": f.sociedad,
            "importe": r["importe"],
            "lineas": r["lineas"],
            "facturado": r["facturado"],
            "asignado": r["asignado"],
            "pls": r["pls"],
            "pls_finalizados": r["pls_finalizados"],
            "pls_confirmados": r["pls_confirmados"],
            "lista_transporte": _lista_para_transporte(f, r),
            "creado_en": f.creado_en,
            "actualizado_en": f.actualizado_en,
        })
    return {"items": items, "total": total, "page": page, "size": size}


def info_transporte(pl: PackingList) -> dict | None:
    u = pl.unidad
    if not u:
        return None
    e = u.embarque
    return {
        "unidad_id": u.id,
        "unidad": u.numero or u.etiqueta,
        "tipo": u.tipo,
        "asignacion": pl.asignacion,
        "embarque_id": e.id,
        "embarque": e.codigo,
        "documento": e.documento_numero,
        "estado": e.estado,
        "etd": e.etd,
        "eta": e.eta,
        "salida_real": e.salida_real,
        "arribo_real": e.arribo_real,
        "ultimo_evento": (
            {"tipo": e.eventos[-1].tipo, "fecha": e.eventos[-1].fecha, "ubicacion": e.eventos[-1].ubicacion}
            if e.eventos else None
        ),
    }


def detalle_factura(db: Session, user: Usuario, factura_id: int) -> dict:
    f = cargar_factura(db, user, factura_id)
    if f.estado in ("BORRADOR", "EN_CORRECCION"):
        # Productos aprobados después de facturar: la partida ya se ve (se guarda al finalizar)
        completar_aduana(db, f)
    pls_activos = [pl for pl in f.packing_lists if pl.estado != "CANCELADO"]
    en_pl: dict[int, int] = {}
    empacado: dict[int, int] = {}
    for pl in pls_activos:
        for pll in pl.lineas:
            en_pl[pll.factura_linea_id] = en_pl.get(pll.factura_linea_id, 0) + pll.cantidad
            empacado[pll.factura_linea_id] = empacado.get(pll.factura_linea_id, 0) + cubierto(pll)

    lineas = []
    por_unidad: dict[str, dict] = {}
    importe = dinero.CERO
    producto_de = catalogo.productos_de(db, [l.posicion_oc.articulo_id for l in f.lineas])
    for l in f.lineas:
        a = en_pl.get(l.id, 0)
        e = empacado.get(l.id, 0)
        total = dinero.importe(l.cantidad, l.precio_unitario, f.moneda)
        importe += total
        u = por_unidad.setdefault(l.unidad, {"facturado": 0, "en_pl": 0, "empacado": 0})
        u["facturado"] += l.cantidad
        u["en_pl"] += a
        u["empacado"] += e
        lineas.append({
            "id": l.id,
            "posicion_oc_id": l.posicion_oc_id,
            "oc_numero": l.oc_numero,
            "almacen": l.almacen,
            "posicion": l.posicion,
            "codigo_articulo": l.codigo_articulo,
            "codigo_barras": l.codigo_barras,
            "variante": catalogo.texto(l.variante),
            "valores": dict(l.variante or {}),
            "atributos": dict(l.atributos or {}),
            "descripcion": l.descripcion,
            "unidad": l.unidad,
            "marca": catalogo.marca(db, l.atributos),
            "tipo_empaque": l.tipo_empaque,
            "casepack": l.casepack,
            "inner_pack": l.inner_pack,
            "codigo_pack": l.codigo_pack,
            "unidades_por_caja": l.unidades_por_caja,
            "cantidad": l.cantidad,
            "cantidad_oc": l.posicion_oc.cantidad,
            "precio_unitario": l.precio_unitario,
            "precio_oc": l.precio_oc,
            "motivo_precio": l.motivo_precio,
            "importe": dinero.numero(total),
            "pais_origen": l.pais_origen,
            "partida_arancelaria": l.partida_arancelaria,
            "producto_id": producto_de.get(l.posicion_oc.articulo_id),
            "descripcion_comercial": l.descripcion_comercial,
            "en_pl": a,
            "sin_asignar": l.cantidad - a,
            "empacado": e,
            "pendiente_empaque": a - e,
        })

    r = resumen_distribucion(db, [f.id])[f.id]
    edicion = ajeno_edicion(db, user, "factura", f.id)
    editable = f.estado in EDITABLE_FACTURA and not edicion
    permisos = permisos_de(user)
    permisos_finalizar = "factura.finalizar" in permisos
    return {
        "edicion": edicion,
        "id": f.id,
        "nombre": nombre_factura(f),
        "numero": f.numero,
        "fecha": f.fecha,
        "estado": f.estado,
        "version": f.version,
        "proveedor_id": f.proveedor_id,
        "proveedor": f.proveedor.nombre,
        "moneda": f.moneda,
        "incoterm": f.incoterm,
        "sociedad": f.sociedad,
        "centro": f.centro,
        "centro_destino": f.centro_destino,
        **partes(db, f.sociedad, f.centro, f.centro_destino),
        "condiciones": f.condiciones,
        "observaciones": f.observaciones,
        "extra": f.extra or {},
        "creado_en": f.creado_en,
        "actualizado_en": f.actualizado_en,
        "finalizado_en": f.finalizado_en,
        "lineas": lineas,
        "totales": {"importe": dinero.numero(importe), "por_unidad": por_unidad},
        "lista_transporte": _lista_para_transporte(f, r),
        "pendientes": validar_factura(db, f) if editable else [],
        "packing_lists": [
            {
                "id": pl.id,
                "numero": pl.numero,
                "estado": pl.estado,
                "version": pl.version,
                "totales": totales_pl(pl),
                "transporte": info_transporte(pl),
            }
            for pl in f.packing_lists
        ],
        "puede": {
            "editar": editable,
            "finalizar": editable and permisos_finalizar,
            "reabrir": f.estado == "FINALIZADA" and "factura.reabrir" in permisos,
            "cancelar": f.estado != "CANCELADA" and "factura.cancelar" in permisos and (es_interno(user) or f.estado == "BORRADOR"),
            "crear_pl": f.estado != "CANCELADA" and any(l["sin_asignar"] > 0 for l in lineas),
        },
    }


def historial_factura(db: Session, user: Usuario, factura_id: int) -> list[dict]:
    cargar_factura(db, user, factura_id)
    filas = db.scalars(
        select(Historial).where(Historial.raiz_tipo == "factura", Historial.raiz_id == factura_id).order_by(Historial.fecha.desc(), Historial.id.desc())
    ).all()
    return [
        {
            "id": h.id,
            "fecha": h.fecha,
            "entidad": h.entidad,
            "entidad_id": h.entidad_id,
            "accion": h.accion,
            "detalle": h.detalle,
            "motivo": h.motivo,
            "usuario": h.usuario.nombre if h.usuario else None,
        }
        for h in filas
    ]


# ---- Archivos ---------------------------------------------------------------
TIPOS_ARCHIVO = ("FACTURA_OFICIAL", "OTRO")


def subir_archivo(db: Session, user: Usuario, factura_id: int, nombre: str, contenido: bytes, tipo: str) -> dict:
    exigir(user, "factura.editar")
    f = cargar_factura(db, user, factura_id)
    if f.estado == "CANCELADA":
        raise ErrorNegocio("Files cannot be attached to a cancelled invoice.", 409, "no_editable")
    exigir_tamano(contenido)
    clase = tipo_de(nombre, contenido, DOCUMENTOS)
    if tipo not in TIPOS_ARCHIVO:
        raise ErrorNegocio("Choose whether the file is the official invoice or another document.", 422, "validacion")
    seguro = adjuntos.nombre_seguro(nombre, "archivo")
    adj = adjuntos.crear(db, user, seguro, contenido, os.path.join("facturas", str(f.id)), os.path.splitext(seguro)[1].lower(),
                         MIME_DOCUMENTO.get(clase, "application/octet-stream"))
    a = Archivo(factura_id=f.id, tipo=tipo, adjunto=adj)
    db.add(a)
    db.flush()
    registrar(db, user, "factura", f.id, "adjuntar_archivo", {"archivo": seguro, "tipo": tipo}, factura_id=f.id)
    return {"id": a.id}


def listar_archivos(db: Session, user: Usuario, factura_id: int) -> list[dict]:
    cargar_factura(db, user, factura_id)
    return [
        {"id": a.id, "tipo": a.tipo, "nombre": a.nombre, "tamano": a.tamano, "subido_en": a.subido_en}
        for a in db.scalars(select(Archivo).where(Archivo.factura_id == factura_id).order_by(Archivo.id)).all()
    ]


def obtener_archivo(db: Session, user: Usuario, archivo_id: int) -> Archivo:
    a = db.get(Archivo, archivo_id)
    if not a:
        raise ErrorNegocio("The file does not exist.", 404, "no_encontrado")
    cargar_factura(db, user, a.factura_id)
    return a
