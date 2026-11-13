"""Inicio de cada persona (diseño v3): qué bloques ve y la gráfica de compras.

El Inicio muestra primero «Mi bandeja» (lo que hay que hacer), cuatro
indicadores elegidos (indicadores.py, módulo «inicio») y una sola gráfica:
comprado contra recibido por mes. Cada persona agrega o quita bloques del
tablero ejecutivo en «Personalizar panel»; lo que elige se guarda en sus
preferencias (`inicio_bloques`). El rol puede además ocultar paneles
(Usuarios y acceso → Rol → Inicio); un bloque oculto por el rol no aparece
aunque la persona lo elija.
"""
from collections import defaultdict
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import dinero
from app.core.errores import ErrorNegocio
from app.modelos import Factura, FacturaLinea, OrdenCompra, PLLinea, PosicionOC, RecepcionLinea, Usuario
from app.modulos.acceso.permisos import exigir, proveedor_filtro, sociedad_filtro
from app.modulos.seguimiento import metricas

# Bloques del Inicio, en el orden en que se dibujan. Los tres primeros vienen puestos.
BLOQUES = ("bandeja", "indicadores", "grafico", "envios", "proveedores", "flujo", "contenedores", "alertas")
DE_FABRICA = ["bandeja", "indicadores", "grafico"]
MESES = (3, 6, 12)


def bloques(user: Usuario) -> list[str]:
    """Los bloques que la persona eligió (o los de fábrica), en el orden de BLOQUES."""
    propios = (user.preferencias or {}).get("inicio_bloques")
    elegidos = set(propios) if isinstance(propios, list) else set(DE_FABRICA)
    return [b for b in BLOQUES if b in elegidos]


def guardar_bloques(db: Session, user: Usuario, lista) -> dict:
    """Guarda los bloques del Inicio de la persona; null vuelve a los de fábrica."""
    from app.modulos.acceso.preferencias import usar

    pref = dict(user.preferencias or {})
    if lista is None:
        pref.pop("inicio_bloques", None)
    else:
        if not isinstance(lista, list) or set(lista) - set(BLOQUES):
            raise ErrorNegocio("Unknown block.", 422, "validacion")
        pref["inicio_bloques"] = [b for b in BLOQUES if b in set(lista)]
    user.preferencias = pref
    usar(user)
    return {"bloques": bloques(user)}


def _mes(d) -> str:
    d = d.date() if isinstance(d, datetime) else d
    return f"{d.year:04d}-{d.month:02d}"


def _meses_hasta(hoy: date, n: int) -> list[str]:
    """Los últimos n meses (aaaa-mm), del más viejo al actual."""
    res = []
    y, m = hoy.year, hoy.month
    for _ in range(n):
        res.append(f"{y:04d}-{m:02d}")
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    return list(reversed(res))


def compras_recepcion(db: Session, user: Usuario, meses: int = 12) -> dict:
    """Comprado contra recibido por mes, en la moneda de la empresa.

    - Comprado: cantidad × precio de las líneas de las OC aprobadas o cerradas, por mes de emisión.
    - Recibido: lo recibido en bodega × precio de la línea de la factura comercial, por mes de la recepción.
    Las otras monedas no se suman: se informan aparte (`otras`)."""
    from app.modulos.acceso import visibilidad

    exigir(user, "oc.ver")
    if visibilidad.oculto("precios"):
        raise ErrorNegocio("Your role does not see prices.", 403, "sin_permiso")
    meses = meses if meses in MESES else 12
    claves = _meses_hasta(date.today(), meses)
    desde = date(int(claves[0][:4]), int(claves[0][5:]), 1)
    from app.modulos.compras.importacion import moneda_base

    base = moneda_base()
    prov = proveedor_filtro(user)
    comprado: dict[str, dict] = defaultdict(lambda: defaultdict(lambda: dinero.CERO))
    recibido: dict[str, dict] = defaultdict(lambda: defaultdict(lambda: dinero.CERO))

    cond_oc = [OrdenCompra.estado.in_(("APROBADA", "CERRADA")), OrdenCompra.fecha >= desde,
               *sociedad_filtro(user, OrdenCompra.sociedad)]
    if prov is not None:
        cond_oc.append(OrdenCompra.proveedor_id.in_(prov))
    for fecha, moneda, cant, precio in db.execute(
            select(OrdenCompra.fecha, OrdenCompra.moneda, PosicionOC.cantidad, PosicionOC.precio)
            .join(PosicionOC, PosicionOC.oc_id == OrdenCompra.id).where(*cond_oc)):
        if moneda and precio is not None:
            comprado[_mes(fecha)][moneda] += dinero.importe(cant, precio, moneda)

    cond_rec = [RecepcionLinea.fecha >= datetime.combine(desde, datetime.min.time()), *sociedad_filtro(user, Factura.sociedad)]
    if prov is not None:
        cond_rec.append(Factura.proveedor_id.in_(prov))
    for fecha, moneda, cant, precio in db.execute(
            select(RecepcionLinea.fecha, Factura.moneda, RecepcionLinea.cantidad_recibida, FacturaLinea.precio_unitario)
            .join(PLLinea, PLLinea.id == RecepcionLinea.pl_linea_id)
            .join(FacturaLinea, FacturaLinea.id == PLLinea.factura_linea_id)
            .join(Factura, Factura.id == FacturaLinea.factura_id).where(*cond_rec)):
        if moneda and precio is not None:
            recibido[_mes(fecha)][moneda] += dinero.importe(cant, precio, moneda)

    def en_base(por_mes, k):
        return dinero.numero(dinero.redondear(por_mes[k].get(base, dinero.CERO), base)) if k in por_mes else 0

    otras: dict[str, object] = defaultdict(lambda: dinero.CERO)
    for por_mes in (comprado, recibido):
        for por_moneda in por_mes.values():
            for mon, v in por_moneda.items():
                if mon != base:
                    otras[mon] += v
    return {
        "moneda": base, "meses": meses,
        "serie": [{"mes": k, "comprado": en_base(comprado, k), "recibido": en_base(recibido, k)} for k in claves],
        "otras": metricas.otras_monedas(dict(otras), base),
    }
