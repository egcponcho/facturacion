"""Seguimiento de mercancía: dónde está cada SKU, desde la OC hasta la bodega.

Una fila por cantidad en una misma etapa: el saldo de la OC por facturar, lo
facturado sin packing list, lo que está en un PL y, si ya tiene contenedor,
en qué embarque va. Con la fecha requerida en tienda se calcula la holgura
(días entre la llegada y la fecha en tienda) para ver a tiempo lo que se atrasa.
"""
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Factura, FacturaLinea, OrdenCompra, PLLinea, PosicionOC, Usuario
from .cantidades import facturado_por_posicion, nombre_factura
from .common import proveedor_filtro

ETAPAS = [
    ("PEND_LIBERACION", "Pendiente de liberación"),
    ("POR_FACTURAR", "Por facturar"),
    ("FACTURADO", "Facturado sin packing list"),
    ("EN_PL", "En packing list"),
    ("CONTENEDOR", "Asignado a contenedor"),
    ("EN_TRANSITO", "En tránsito"),
    ("ARRIBADO", "Arribado"),
    ("ENTREGADO", "Entregado"),
    ("RECIBIDO", "Recibido"),
]
ORDEN = {"marca", "estilo", "color", "talla", "oc", "cantidad", "etapa", "fecha_xf", "fecha_tienda", "eta",
         "holgura", "embarque", "contenedor", "recolectado_en", "proveedor"}


def _riesgo(holgura: int | None) -> str | None:
    if holgura is None:
        return None
    if holgura < 0:
        return "ATRASO"
    if holgura < 7:
        return "JUSTO"
    return "A_TIEMPO"


def _base(p: PosicionOC, oc: OrdenCompra, hoy: date) -> dict:
    return {
        "marca": p.marca, "estilo": p.estilo, "color": p.color, "talla": p.talla, "sku": p.codigo_sap,
        "oc_id": oc.id, "oc": oc.numero, "posicion": p.posicion, "proveedor": oc.proveedor.nombre,
        "unidad": p.unidad, "tipo_empaque": p.tipo_empaque, "pais_destino": oc.pais_destino,
        "fecha_xf": oc.fecha_xf, "fecha_tienda": oc.fecha_tienda,
        "dias_tienda": (oc.fecha_tienda - hoy).days if oc.fecha_tienda else None,
        "factura_id": None, "factura": None, "pl_id": None, "pl": None, "contenedor": None,
        "embarque_id": None, "embarque": None, "estado_embarque": None, "asignacion": None,
        "etd": None, "eta": None, "salida_real": None, "arribo_real": None, "recolectado_en": None,
        "atraso_recoleccion": None, "holgura": None, "riesgo": None,
    }


def filas_seguimiento(db: Session, user: Usuario, proveedor_id: int | None = None) -> list[dict]:
    prov = proveedor_filtro(user, proveedor_id)
    hoy = date.today()
    consulta = select(PosicionOC).join(OrdenCompra)
    if prov:
        consulta = consulta.where(OrdenCompra.proveedor_id == prov)
    posiciones = list(db.scalars(consulta).all())
    facturado = facturado_por_posicion(db, [p.id for p in posiciones])
    filas = []
    for p in posiciones:
        saldo = p.cantidad - facturado.get(p.id, 0)
        if saldo > 0:
            filas.append({**_base(p, p.oc, hoy), "cantidad": saldo,
                          "etapa": "POR_FACTURAR" if p.oc.liberada else "PEND_LIBERACION"})

    consulta = select(FacturaLinea).join(Factura).where(Factura.estado != "CANCELADA")
    if prov:
        consulta = consulta.where(Factura.proveedor_id == prov)
    for fl in db.scalars(consulta).all():
        p = fl.posicion_oc
        oc = p.oc
        f = fl.factura
        en_pl = 0
        for pll in db.scalars(select(PLLinea).where(PLLinea.factura_linea_id == fl.id)).all():
            pl = pll.pl
            if pl.estado == "CANCELADO":
                continue
            en_pl += pll.cantidad
            fila = {**_base(p, oc, hoy), "cantidad": pll.cantidad, "factura_id": f.id,
                    "factura": nombre_factura(f), "pl_id": pl.id, "pl": pl.numero, "etapa": "EN_PL",
                    "recolectado_en": pl.recolectado_en}
            if pl.recolectado_en and oc.fecha_xf:
                fila["atraso_recoleccion"] = (pl.recolectado_en - oc.fecha_xf).days
            u = pl.unidad
            if u:
                e = u.embarque
                fila.update(contenedor=u.numero or u.etiqueta, embarque_id=e.id, embarque=e.codigo,
                            estado_embarque=e.estado, asignacion=pl.asignacion, etd=e.etd, eta=e.eta,
                            salida_real=e.salida_real, arribo_real=e.arribo_real,
                            etapa="CONTENEDOR" if e.estado == "PLANIFICADO" else e.estado)
                llegada = e.arribo_real or e.eta
                if oc.fecha_tienda and llegada:
                    fila["holgura"] = (oc.fecha_tienda - llegada).days
            elif oc.fecha_tienda:
                # Sin embarque aún: la holgura es lo que queda hasta la fecha en tienda
                fila["holgura"] = (oc.fecha_tienda - hoy).days
            fila["riesgo"] = _riesgo(fila["holgura"])
            filas.append(fila)
        resto = fl.cantidad - en_pl
        if resto > 0:
            fila = {**_base(p, oc, hoy), "cantidad": resto, "factura_id": f.id, "factura": nombre_factura(f),
                    "etapa": "FACTURADO"}
            if oc.fecha_tienda:
                fila["holgura"] = (oc.fecha_tienda - hoy).days
                fila["riesgo"] = _riesgo(fila["holgura"])
            filas.append(fila)
    return filas


def seguimiento(db: Session, user: Usuario, proveedor_id: int | None = None, q: str | None = None,
                marca: str | None = None, estilo: str | None = None, color: str | None = None,
                talla: str | None = None, etapa: str | None = None, riesgo: str | None = None,
                embarque_id: int | None = None, orden: str | None = None, page: int = 1, size: int = 25) -> dict:
    todas = filas_seguimiento(db, user, proveedor_id)
    opciones = {
        "marcas": sorted({f["marca"] for f in todas if f["marca"]}),
        "estilos": sorted({f["estilo"] for f in todas if f["estilo"]}),
        "colores": sorted({f["color"] for f in todas if f["color"]}),
        "tallas": sorted({f["talla"] for f in todas if f["talla"]}, key=lambda t: (not t.isdigit(), t.zfill(4))),
        "embarques": sorted({(f["embarque_id"], f["embarque"]) for f in todas if f["embarque_id"]}),
    }
    filas = todas
    for campo, valor in (("marca", marca), ("estilo", estilo), ("color", color), ("talla", talla),
                         ("etapa", etapa), ("riesgo", riesgo), ("embarque_id", embarque_id)):
        if valor not in (None, ""):
            filas = [f for f in filas if f[campo] == valor]
    if q:
        t = q.strip().lower()
        filas = [f for f in filas if any(t in str(f[k] or "").lower()
                                         for k in ("sku", "oc", "factura", "contenedor", "embarque", "estilo", "pl"))]

    # Resumen: cantidades por etapa y por marca, separadas por unidad de medida
    por_etapa = {k: {} for k, _ in ETAPAS}
    por_marca: dict[str, dict] = {}
    for f in filas:
        por_etapa[f["etapa"]][f["unidad"]] = por_etapa[f["etapa"]].get(f["unidad"], 0) + f["cantidad"]
        clave_m = (f["marca"] or "Sin marca", f["unidad"])
        m = por_marca.setdefault(clave_m, {"marca": clave_m[0], "unidad": f["unidad"], "atraso": 0, "total": 0,
                                           "etapas": {}})
        m["total"] += f["cantidad"]
        m["etapas"][f["etapa"]] = m["etapas"].get(f["etapa"], 0) + f["cantidad"]
        m["atraso"] += f["riesgo"] == "ATRASO"

    col, _, direccion = (orden or "").partition(":")
    if col in ORDEN:
        indice = {k: i for i, (k, _) in enumerate(ETAPAS)}
        clave = (lambda f: indice[f["etapa"]]) if col == "etapa" else (lambda f: (f[col] is None, f[col] or 0))
        filas = sorted(filas, key=clave, reverse=direccion == "desc")
    total = len(filas)
    return {
        "items": filas[(page - 1) * size: page * size],
        "total": total,
        "page": page,
        "size": size,
        "etapas": [{"clave": k, "nombre": n, "por_unidad": por_etapa[k]} for k, n in ETAPAS],
        "por_marca": sorted(por_marca.values(), key=lambda m: (m["marca"], m["unidad"])),
        "opciones": {**opciones, "embarques": [{"id": i, "codigo": c} for i, c in opciones["embarques"]]},
    }
