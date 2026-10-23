"""Seguimiento de mercancía: dónde está cada SKU, desde la OC hasta la bodega.

Una fila por cantidad en una misma etapa: el saldo de la OC por facturar, lo
facturado sin packing list, lo que está en un PL y, si ya tiene contenedor,
en qué embarque va. La holgura son los días entre la llegada al puerto (real,
estimada del embarque o, sin embarque, XF más el tránsito estándar) y la fecha
límite de arribo: la fecha en tienda menos los días que su región necesita para
llevarla a la bodega, darle ingreso y reexportarla (ver leadtimes).
"""
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, object_session

from app.core import listas
from app.core.db import plano
from app.modelos import Embarque, Factura, FacturaLinea, OrdenCompra, PLLinea, PosicionOC, Usuario
from app.modulos.acceso.permisos import proveedor_filtro, sociedad_filtro
from app.modulos.compras import liberaciones
from app.modulos.comun import tabla
from app.modulos.facturacion.cantidades import facturado_por_posicion, nombre_factura
from app.modulos.maestros import variantes
from app.modulos.seguimiento import metricas
from app.modulos.transporte import leadtimes as lt
from app.modulos.transporte.leadtimes import Estandares, _riesgo, arribo_estimado, entre, familias_de, limite_puerto

ETAPAS = [
    ("PEND_LIBERACION", "Pending release"),
    ("POR_FACTURAR", "To invoice"),
    ("FACTURADO", "Invoiced, no packing list"),
    ("EN_PL", "In packing list"),
    ("CONTENEDOR", "Assigned to container"),
    ("EN_TRANSITO", "In transit"),
    ("ARRIBADO", "Arrived"),
    ("ENTREGADO", "Delivered"),
    ("RECIBIDO", "Received"),
]
ORDEN = {"almacen", "familia", "documento", "marca", "variante", "oc", "cantidad", "etapa", "fecha_xf", "fecha_tienda", "eta",
         "holgura", "embarque", "contenedor", "recolectado_en", "proveedor"}
TODO = 100_000  # «todas las filas» al calcular sobre la lista completa


# ---- Filtros por columna (TablaDatos) -------------------------------------------
# Los tableros se calculan en memoria (no son una consulta SQL), así que no usan
# tabla.aplicar: cada columna declara cómo se lee su dato en la fila (la clave o
# una función; puede dar una lista) y se filtra con las mismas reglas de
# app/modulos/comun/tabla.py: «es alguno de estos valores» (`__vacio__` es el
# dato vacío) y las columnas se combinan con «y».
def _clave_valor(v) -> str:
    """El valor en texto, como lo manda la pantalla (JSON leído como texto)."""
    if v is None or v == "":
        return tabla.VACIO
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    if isinstance(v, date):
        return v.isoformat()
    return str(v)


def _datos_columna(col, fila: dict) -> list:
    v = col(fila) if callable(col) else fila.get(col)
    vs = list(v) if isinstance(v, (list, tuple, set)) else [v]
    return [x for x in vs if x is not None and x != ""]


def _pasa(datos: list, elegidos: set) -> bool:
    if not datos:
        return tabla.VACIO in elegidos
    return any(_clave_valor(x) in elegidos for x in datos)


def filtrar_columnas(filas: list[dict], columnas: dict, filtros: dict | None, excepto: str | None = None) -> list[dict]:
    """Las filas que pasan los filtros por columna (menos el de `excepto`); una
    columna que la lista no declara se ignora."""
    for k, vals in (filtros or {}).items():
        if k == excepto or k not in columnas:
            continue
        elegidos = set(vals)
        filas = [f for f in filas if _pasa(_datos_columna(columnas[k], f), elegidos)]
    return filas


def _es_numero(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def valores_columna(filas: list[dict], columnas: dict, columna: str, q: str | None, filtros: dict | None) -> list[dict]:
    """Valores únicos de una columna con cuántas filas tienen cada uno, bajo los
    demás filtros por columna (como el filtro de Excel); `q` busca dentro de los
    valores sin acentos ni mayúsculas. El vacío va primero, luego en orden."""
    col = tabla.columna_valida(columnas, columna)
    cuenta: dict[str, dict] = {}
    for f in filtrar_columnas(filas, columnas, filtros, excepto=columna):
        unicos = {_clave_valor(v): v for v in _datos_columna(col, f)} or {tabla.VACIO: None}
        for k, v in unicos.items():
            if k in cuenta:
                cuenta[k]["n"] += 1
            else:
                cuenta[k] = {"valor": v, "n": 1}
    res = list(cuenta.values())
    if q and q.strip():
        buscado = plano(q.strip())
        res = [x for x in res if x["valor"] is not None and buscado in plano(_clave_valor(x["valor"]))]
    res.sort(key=lambda x: (x["valor"] is not None, not _es_numero(x["valor"]),
                            x["valor"] if _es_numero(x["valor"]) else 0, _clave_valor(x["valor"])))
    return res[:tabla.MAX_VALORES]




def _familia(p: PosicionOC):
    a = p.articulo
    g = a.producto.grupo_producto if a is not None and a.producto is not None else None
    return g.familia if g is not None else None


def _base(p: PosicionOC, oc: OrdenCompra, hoy: date, est: dict | None = None) -> dict:
    db = object_session(p)
    fam = _familia(p)
    return {
        "limite_puerto": limite_puerto(oc.fecha_tienda, est) if est else None,
        # La marca es el atributo del producto que apunta al catálogo de marcas (foto de la línea)
        "marca": variantes.de_catalogo(db, p.atributos, "marcas"), "sku": p.codigo_articulo,
        "atributos": variantes.de_producto_linea(p, db),
        # Valores de variante por atributo ({"COLOR": "BLACK", "CONC": "30 %"}): los filtros y
        # opciones salen de aquí, sin suponer qué atributos usa la empresa
        "variantes": (vals := variantes.de_linea(p)),
        "variante": variantes.texto(vals) or None,
        "oc_id": oc.id, "oc": oc.numero, "estado_oc": oc.estado, "posicion": p.posicion, "precio": p.precio, "moneda": oc.moneda, "almacen": p.almacen,
        "familia": fam.nombre if fam else None,
        "proveedor": oc.proveedor.nombre, "documento": None, "sociedad": oc.sociedad, "centro": oc.centro,
        "liberacion_comercial": oc.liberacion_comercial, "liberacion_logistica": oc.liberacion_logistica,
        "transportista": None, "puerto_origen": None, "puerto_destino": None,
        "unidad": p.unidad, "tipo_empaque": p.tipo_empaque, "centro_destino": oc.centro_destino,
        "fecha_xf": oc.fecha_xf, "fecha_tienda": oc.fecha_tienda,
        "dias_tienda": (oc.fecha_tienda - hoy).days if oc.fecha_tienda else None,
        "factura_id": None, "factura": None, "pl_id": None, "pl": None, "contenedor": None, "unidad_id": None, "modo": None,
        "embarque_id": None, "embarque": None, "estado_embarque": None, "asignacion": None,
        "etd": None, "eta": None, "salida_real": None, "arribo_real": None, "recolectado_en": None,
        "atraso_recoleccion": None, "holgura": None, "riesgo": None,
        "tienda_estimada": None, "dias_vs_tienda": None,
    }


def _en_tienda(fila: dict, llegada: date | None, est: dict) -> None:
    """Fecha estimada en tienda: el arribo (real, ETA o estimado con el
    tránsito de su origen) más los días de puerto, ingreso y reexportación."""
    if not llegada:
        return
    fila["tienda_estimada"] = entre(llegada, est, "arribo", "tienda")
    if fila["fecha_tienda"]:
        fila["dias_vs_tienda"] = (fila["tienda_estimada"] - fila["fecha_tienda"]).days


def filas_seguimiento(db: Session, user: Usuario, proveedor_id: int | None = None) -> list[dict]:
    """Una fila por saldo de línea de OC, por línea de lista de empaque y por
    lo facturado sin lista. Solo OC vigentes (metricas.OC_EN_SEGUIMIENTO): las
    cerradas siguen por lo ya facturado, pero su saldo deja de estar pendiente."""
    prov = proveedor_filtro(user, proveedor_id)
    hoy = date.today()
    consulta = select(PosicionOC).join(OrdenCompra).where(OrdenCompra.estado.in_(metricas.OC_EN_SEGUIMIENTO))
    if prov:
        consulta = consulta.where(OrdenCompra.proveedor_id.in_(prov))
    consulta = consulta.where(*sociedad_filtro(user, OrdenCompra.sociedad))
    posiciones = list(db.scalars(consulta).all())
    ests = Estandares(db)

    def sin_embarque(fila: dict, oc: OrdenCompra, familia: int | None = None) -> None:
        # Aún sin embarque: se estima el arribo con la XF y el tránsito estándar de su origen
        est = ests.de_oc(oc, familia)
        llegada = arribo_estimado(oc.fecha_xf, est, hoy)
        _en_tienda(fila, llegada, est)
        lim = fila["limite_puerto"]
        if lim:
            fila["holgura"] = (lim - (llegada or hoy)).days
            fila["riesgo"] = _riesgo(fila["holgura"])

    facturado = facturado_por_posicion(db, [p.id for p in posiciones])
    familia = familias_de(db, posiciones)
    filas = []
    for p in posiciones:
        saldo = p.cantidad - facturado.get(p.id, 0)
        if saldo > 0 and p.oc.estado in metricas.OC_CON_SALDO:
            fila = {**_base(p, p.oc, hoy, ests.de_oc(p.oc, familia.get(p.id))), "cantidad": saldo,
                    "etapa": "POR_FACTURAR" if p.oc.liberada else "PEND_LIBERACION"}
            sin_embarque(fila, p.oc, familia.get(p.id))
            filas.append(fila)

    cond = [Factura.estado != "CANCELADA", OrdenCompra.estado.in_(metricas.OC_EN_SEGUIMIENTO),
            *sociedad_filtro(user, Factura.sociedad)]
    if prov:
        cond.append(Factura.proveedor_id.in_(prov))
    consulta = (select(FacturaLinea).join(Factura).join(PosicionOC, PosicionOC.id == FacturaLinea.posicion_oc_id)
                .join(OrdenCompra, OrdenCompra.id == PosicionOC.oc_id).where(*cond))
    lineas_pl: dict[int, list] = {}
    for pll in db.scalars(select(PLLinea).join(FacturaLinea, FacturaLinea.id == PLLinea.factura_linea_id)
                          .join(Factura).join(PosicionOC, PosicionOC.id == FacturaLinea.posicion_oc_id)
                          .join(OrdenCompra, OrdenCompra.id == PosicionOC.oc_id).where(*cond)).all():
        lineas_pl.setdefault(pll.factura_linea_id, []).append(pll)
    lineas_factura = list(db.scalars(consulta).all())
    familia.update(familias_de(db, [fl.posicion_oc for fl in lineas_factura]))
    for fl in lineas_factura:
        p = fl.posicion_oc
        oc = p.oc
        f = fl.factura
        en_pl = 0
        for pll in lineas_pl.get(fl.id, []):
            pl = pll.pl
            if pl.estado == "CANCELADO":
                continue
            en_pl += pll.cantidad
            fila = {**_base(p, oc, hoy, ests.de_oc(oc, familia.get(p.id))), "cantidad": pll.cantidad, "factura_id": f.id,
                    "factura": nombre_factura(f), "pl_id": pl.id, "pl": pl.numero, "etapa": "EN_PL",
                    "recolectado_en": pl.recolectado_en}
            if pl.recolectado_en and oc.fecha_xf:
                fila["atraso_recoleccion"] = (pl.recolectado_en - oc.fecha_xf).days
            u = pl.unidad
            if u:
                e = u.embarque
                fila.update(contenedor=u.numero or u.etiqueta, unidad_id=u.id, modo=e.tipo_transporte,
                            embarque_id=e.id, embarque=e.codigo,
                            documento=e.documento_numero, transportista=e.transportista,
                            puerto_origen=e.puerto_origen, puerto_destino=e.puerto_destino,
                            estado_embarque=e.estado, asignacion=pl.asignacion, etd=e.etd, eta=e.eta,
                            salida_real=e.salida_real, arribo_real=e.arribo_real,
                            etapa="CONTENEDOR" if e.estado == "PLANIFICADO" else e.estado)
                llegada = e.arribo_real or e.eta or (
                    entre(e.salida_real or e.etd, ests.de_oc(oc, modo=e.tipo_transporte), "salida", "arribo")
                    if (e.salida_real or e.etd) else arribo_estimado(oc.fecha_xf, ests.de_oc(oc), hoy))
                _en_tienda(fila, llegada, ests.de_oc(oc, familia.get(p.id), e.tipo_transporte))
                if fila["limite_puerto"] and llegada:
                    fila["holgura"] = (fila["limite_puerto"] - llegada).days
                fila["riesgo"] = _riesgo(fila["holgura"])
            else:
                sin_embarque(fila, oc, familia.get(p.id))
            filas.append(fila)
        resto = fl.cantidad - en_pl
        if resto > 0:
            fila = {**_base(p, oc, hoy, ests.de_oc(oc, familia.get(p.id))), "cantidad": resto, "factura_id": f.id,
                    "factura": nombre_factura(f), "etapa": "FACTURADO"}
            sin_embarque(fila, oc, familia.get(p.id))
            filas.append(fila)
    return filas


# Filtros exactos de la vista (valor igual) y rangos de fechas (desde/hasta)
FILTROS_EXACTOS = ("oc_id", "marca", "almacen", "familia", "sku", "contenedor", "documento",
                   "etapa", "riesgo", "embarque_id", "proveedor", "sociedad", "centro", "liberacion_comercial",
                   "liberacion_logistica")
RANGOS = ("eta", "fecha_xf", "fecha_tienda")


# Filtro por atributo de variante (var_<CÓDIGO>=valor1,valor2) o de producto (atr_<CÓDIGO>=…)
PREFIJO_VARIANTE = "var_"
PREFIJO_ATRIBUTO = "atr_"


def _valores(todas: list[dict], campo: str) -> list:
    return sorted({f[campo] for f in todas if f[campo]}, key=str)


def _orden_valor(v: str):
    """Números en orden numérico (6.5 antes de 10) y el resto en orden alfabético."""
    try:
        return (0, float(str(v).replace(",", ".")), "")
    except ValueError:
        return (1, 0.0, str(v))


def _atributos_opciones(db: Session, todas: list[dict], clave: str = "variantes", nivel: str = "VARIANTE") -> list[dict]:
    """Los atributos de variante (o de producto) presentes en las filas, en el orden del
    catálogo, con sus valores: son los filtros de la pantalla."""
    nombres = variantes.nombres(db)
    vistos: dict[str, set] = {}
    for f in todas:
        for k, v in (f.get(clave) or {}).items():
            vistos.setdefault(k, set()).add(str(v))
    orden = [a.codigo for a in variantes.atributos(db, nivel)]
    claves = [k for k in orden if k in vistos] + sorted(k for k in vistos if k not in orden)
    return [{"codigo": k, "nombre": nombres.get(k, k), "valores": sorted(vistos[k], key=_orden_valor)} for k in claves]


def _liberaciones_opciones(db: Session) -> dict:
    """Los estados de liberación del catálogo (los códigos que manda el ERP de la empresa)."""
    lib = liberaciones.de(db)
    return {tipo: [{"codigo": x.codigo, "nombre": x.nombre, "libera": x.libera} for x in est.lista]
            for tipo, est in (("comercial", lib.comercial), ("logistica", lib.logistica))}


def _opciones(db: Session, todas: list[dict]) -> dict:
    embarques = sorted({(f["embarque_id"], f["embarque"]) for f in todas if f["embarque_id"]})
    return {
        "marcas": _valores(todas, "marca"),
        "atributos": _atributos_opciones(db, todas),
        "atributos_producto": _atributos_opciones(db, todas, "atributos", "PRODUCTO"),
        "liberaciones": _liberaciones_opciones(db),
        "almacenes": _valores(todas, "almacen"),
        "familias": _valores(todas, "familia"),
        "skus": _valores(todas, "sku"),
        "contenedores": _valores(todas, "contenedor"),
        "documentos": _valores(todas, "documento"),
        "proveedores": _valores(todas, "proveedor"),
        "sociedades": _valores(todas, "sociedad"),
        "centros": _valores(todas, "centro"),
        "embarques": [{"id": i, "codigo": c} for i, c in embarques],
    }


def _en(valor, filtro) -> bool:
    """Filtro de uno o varios valores (separados por comas)."""
    if isinstance(filtro, (list, tuple, set)):
        opciones = {str(x) for x in filtro}
    else:
        opciones = {x.strip() for x in str(filtro).split(",")} if "," in str(filtro) else {str(filtro)}
    return str(valor) in opciones


def _filtrar(todas: list[dict], filtros: dict) -> list[dict]:
    """Los mismos filtros para los tres tableros de mercancía, contenedores y OCs."""
    filas = todas
    for campo in FILTROS_EXACTOS:
        if campo in filtros:
            valor = filtros[campo]
            filas = [f for f in filas if _en(f[campo], valor)]
    for clave, valor in filtros.items():
        if clave.startswith(PREFIJO_VARIANTE):
            codigo = clave[len(PREFIJO_VARIANTE):]
            filas = [f for f in filas if _en((f.get("variantes") or {}).get(codigo, ""), valor)]
        elif clave.startswith(PREFIJO_ATRIBUTO):
            codigo = clave[len(PREFIJO_ATRIBUTO):]
            filas = [f for f in filas if _en((f.get("atributos") or {}).get(codigo, ""), valor)]
    if filtros.get("riesgo"):
        # El riesgo es de lo que aún no llega a bodega: lo recibido ya no está en riesgo
        filas = [f for f in filas if f["etapa"] != "RECIBIDO"]
    for campo in RANGOS:
        desde, hasta = filtros.get(f"{campo}_desde"), filtros.get(f"{campo}_hasta")
        if desde:
            filas = [f for f in filas if f[campo] and f[campo] >= desde]
        if hasta:
            filas = [f for f in filas if f[campo] and f[campo] <= hasta]
    if filtros.get("q"):
        t = filtros["q"].strip().lower()
        filas = [f for f in filas if any(t in str(f[k] or "").lower()
                                         for k in ("sku", "oc", "factura", "contenedor", "embarque", "pl",
                                                   "documento", "variante", "marca"))
                 or any(t in str(v).lower() for v in (f.get("atributos") or {}).values())]
    return filas


def seguimiento(db: Session, user: Usuario, proveedor_id: int | None = None, filtros: dict | None = None,
                orden: str | None = None, page: int = 1, size: int = 25) -> dict:
    filtros = {k: v for k, v in (filtros or {}).items() if v not in (None, "")}
    todas = filas_seguimiento(db, user, proveedor_id)
    opciones = _opciones(db, todas)
    filas = _filtrar(todas, filtros)

    # Resumen: cantidades por etapa y por marca, separadas por unidad de medida
    por_etapa = {k: {} for k, _ in ETAPAS}
    por_marca: dict[str, dict] = {}
    for f in filas:
        por_etapa[f["etapa"]][f["unidad"]] = por_etapa[f["etapa"]].get(f["unidad"], 0) + f["cantidad"]
        clave_m = (f["marca"] or "No brand", f["unidad"])
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
        "opciones": opciones,
    }


def _por_unidad(filas: list[dict]) -> dict:
    r: dict[str, int] = {}
    for f in filas:
        r[f["unidad"]] = r.get(f["unidad"], 0) + f["cantidad"]
    return r


def _peor_riesgo(filas: list[dict]) -> str | None:
    for r in ("ATRASO", "JUSTO", "A_TIEMPO"):
        if any(f["riesgo"] == r for f in filas):
            return r
    return None


def _ordenar(items: list[dict], orden: str | None, permitidos: set) -> list[dict]:
    col, _, direccion = (orden or "").partition(":")
    if col not in permitidos:
        return items
    return sorted(items, key=lambda x: (x[col] is None, x[col] if x[col] is not None else 0),
                  reverse=direccion == "desc")


# ---- Tablero de embarques ------------------------------------------------------
# Un renglón por embarque (su BL/AWB/carta de porte), que se abre en sus
# unidades de carga (contenedores, guías aéreas o camiones) y cada unidad en
# lo que lleva por orden de compra.
ESTADOS_EMB = [("PLANIFICADO", "Planned"), ("EN_TRANSITO", "In transit"), ("ARRIBADO", "Arrived"),
               ("ENTREGADO", "Delivered"), ("RECIBIDO", "Received")]
ORDEN_EMB = {"embarque", "documento", "estado", "etd", "eta", "holgura", "ocs", "unidades", "modo"}
# Columnas de la tabla de embarques que se filtran por sus valores (las demás
# —el contenido por unidad de medida— se calculan al vuelo y no)
COLUMNAS_EMB = {
    "embarque": "embarque", "modo": "modo", "documento": "documento", "estado": "estado",
    "ruta": lambda e: f"{e['puerto_origen'] or '—'} → {e['puerto_destino'] or '—'}",
    "etd": "etd", "eta": "eta", "holgura": "riesgo", "unidades": "unidades", "ocs": "ocs",
    "proveedores": "proveedores",
}


def embarques(db: Session, user: Usuario, proveedor_id: int | None = None, filtros: dict | None = None,
              orden: str | None = None, page: int = 1, size: int = 25, columnas: dict | None = None) -> dict:
    """Embarques con sus unidades de carga; `columnas` son los filtros por
    columna de la tabla (no cambian los indicadores ni las gráficas)."""
    items, todas, filas = _items_embarques(db, user, proveedor_id, filtros)
    hoy = date.today()
    por_estado = {k: 0 for k, _ in ESTADOS_EMB}
    for it in items:
        por_estado[it["estado"]] = por_estado.get(it["estado"], 0) + 1
    semanas = []
    for n in range(8):
        ini = hoy + timedelta(days=7 * n)
        fin = ini + timedelta(days=6)
        semanas.append({"desde": ini, "hasta": fin, "embarques": sum(
            1 for it in items if it["eta"] and not it["arribado"] and ini <= it["eta"] <= fin)})
    kpis = {
        "embarques": len(items),
        "unidades": sum(it["unidades"] for it in items),
        # Mismas definiciones que Inicio e Indicadores (metricas.py)
        "en_camino": sum(1 for it in items if it["estado"] == "EN_TRANSITO"),
        "llegan_7_dias": sum(1 for it in items if it["estado"] == "EN_TRANSITO" and it["dias_eta"] is not None
                             and 0 <= it["dias_eta"] <= 7),
        "atrasados": sum(1 for it in items if it["riesgo"] == "ATRASO" and it["estado"] != "RECIBIDO"),
        "por_modo": {m: sum(1 for it in items if it["modo"] == m) for m in listas.codigos("modo_transporte")},
        "por_unidad": _por_unidad(filas),
    }
    items = filtrar_columnas(items, COLUMNAS_EMB, columnas)
    items = _ordenar(sorted(items, key=lambda x: (x["eta"] is None, x["eta"] or hoy)), orden, ORDEN_EMB)
    return {
        "items": items[(page - 1) * size: page * size], "total": len(items), "page": page, "size": size,
        "kpis": kpis, "por_estado": [{"clave": k, "nombre": n, "total": por_estado[k]} for k, n in ESTADOS_EMB],
        "llegadas": semanas, "opciones": _opciones(db, todas),
    }


def valores_embarques(db: Session, user: Usuario, columna: str, q: str | None, columnas: dict,
                      proveedor_id: int | None = None, filtros: dict | None = None) -> list[dict]:
    """Valores únicos de una columna de la tabla de embarques (con los filtros de la pantalla)."""
    tabla.columna_valida(COLUMNAS_EMB, columna)
    items, _, _ = _items_embarques(db, user, proveedor_id, filtros)
    return valores_columna(items, COLUMNAS_EMB, columna, q, columnas)


def _items_embarques(db: Session, user: Usuario, proveedor_id: int | None, filtros: dict | None) -> tuple[list, list, list]:
    """Un renglón por embarque con los filtros de la pantalla: (embarques, todas
    las filas de mercancía, las filas que quedaron con los filtros)."""
    from app.modulos.transporte.transporte import _tipo, modalidad_embarque

    filtros = {k: v for k, v in (filtros or {}).items() if v not in (None, "")}
    todas = filas_seguimiento(db, user, proveedor_id)
    # Alcance de transporte (centros de sus sociedades y transportistas), como en Embarques
    prov = proveedor_filtro(user, proveedor_id)
    en_alcance = {e.id: e for e in db.scalars(metricas.embarques(db, user, prov, Embarque.estado != "CANCELADO"))}
    filas = [f for f in _filtrar(todas, filtros) if f["embarque_id"] in en_alcance]
    if filtros.get("estado"):
        filas = [f for f in filas if _en(f["estado_embarque"], filtros["estado"])]
    if filtros.get("modo"):
        filas = [f for f in filas if _en(f["modo"], filtros["modo"])]
    por_emb: dict[int, list] = {}
    for f in filas:
        por_emb.setdefault(f["embarque_id"], []).append(f)
    # Sin filtros de mercancía, también los embarques que aún no llevan carga
    de_mercancia = set(filtros) - {"estado", "modo"}
    if not de_mercancia and not prov:
        for e in en_alcance.values():
            if (not filtros.get("estado") or _en(e.estado, filtros["estado"])) and \
                    (not filtros.get("modo") or _en(e.tipo_transporte, filtros["modo"])):
                por_emb.setdefault(e.id, [])
    hoy = date.today()
    items = []
    for emb_id, fs in por_emb.items():
        e = en_alcance[emb_id]
        llegada = e.arribo_real or e.eta
        holguras = [f["holgura"] for f in fs if f["holgura"] is not None]
        unidades = []
        for u in sorted(e.unidades, key=lambda x: x.id):
            nombre = u.numero or u.etiqueta
            uf = [f for f in fs if f["unidad_id"] == u.id]
            if not uf:
                continue
            t = _tipo(db, u.tipo)
            uh = [f["holgura"] for f in uf if f["holgura"] is not None]
            unidades.append({
                "unidad_id": u.id, "contenedor": nombre, "tipo": u.tipo, "tipo_nombre": t.nombre if t else u.tipo,
                "modalidad": t.modalidad if t else None, "sello": u.sello, "ocs": len({f["oc"] for f in uf}),
                "marcas": sorted({f["marca"] for f in uf if f["marca"]}), "por_unidad": _por_unidad(uf),
                "holgura": min(uh) if uh else None, "riesgo": _peor_riesgo(uf),
                "facturas": sorted({f["factura"] for f in uf if f["factura"]}),
            })
        items.append({
            "embarque_id": e.id, "embarque": e.codigo, "documento": e.documento_numero, "estado": e.estado,
            "modo": e.tipo_transporte, "modalidad": modalidad_embarque(e), "transportista": e.transportista,
            "puerto_origen": e.puerto_origen, "puerto_destino": e.puerto_destino, "centro": e.centro,
            "etd": e.salida_real or e.etd, "eta": llegada, "arribado": bool(e.arribo_real),
            "dias_eta": (llegada - hoy).days if llegada else None,
            "holgura": min(holguras) if holguras else None, "riesgo": _peor_riesgo(fs),
            "marcas": sorted({f["marca"] for f in fs if f["marca"]}), "ocs": len({f["oc"] for f in fs}),
            "proveedores": sorted({f["proveedor"] for f in fs}), "unidades": len(unidades),
            "detalle_unidades": unidades, "por_unidad": _por_unidad(fs),
        })
    return items, todas, filas


def explosion_unidad(db: Session, user: Usuario, unidad_id: int, proveedor_id: int | None = None,
                     filtros: dict | None = None) -> dict:
    """Todo lo que viaja en una unidad de carga, agrupado por orden de compra."""
    filtros = {k: v for k, v in (filtros or {}).items() if v not in (None, "")}
    filas = [f for f in _filtrar(filas_seguimiento(db, user, proveedor_id), filtros) if f["unidad_id"] == unidad_id]
    ocs: dict[int, dict] = {}
    for f in filas:
        o = ocs.setdefault(f["oc_id"], {
            "oc_id": f["oc_id"], "oc": f["oc"], "proveedor": f["proveedor"], "sociedad": f["sociedad"],
            "centro": f["centro"], "centro_destino": f["centro_destino"], "fecha_tienda": f["fecha_tienda"],
            "fecha_xf": f["fecha_xf"], "lineas": []})
        o["lineas"].append({k: f[k] for k in ("posicion", "sku", "marca", "familia", "atributos", "variante",
                                              "almacen", "cantidad", "unidad", "tipo_empaque", "factura",
                                              "factura_id", "pl", "pl_id", "holgura", "riesgo")})
    res = []
    for o in ocs.values():
        o["lineas"].sort(key=lambda x: str(x["posicion"]).zfill(6))
        o["por_unidad"] = _por_unidad(o["lineas"])
        holguras = [x["holgura"] for x in o["lineas"] if x["holgura"] is not None]
        o["holgura"] = min(holguras) if holguras else None
        o["riesgo"] = _peor_riesgo(o["lineas"])
        res.append(o)
    return {"unidad_id": unidad_id, "ocs": sorted(res, key=lambda x: x["oc"]), "por_unidad": _por_unidad(filas)}


# ---- Tablero de órdenes de compra -------------------------------------------
ESTADOS_OC = [
    ("SIN_COMERCIAL", "No commercial release"),
    ("SIN_LOGISTICA", "No logistics release"),
    ("POR_FACTURAR", "Released, not invoiced"),
    ("PARCIAL", "Partly invoiced"),
    ("FACTURADA", "Invoiced, in progress"),
    ("EN_CAMINO", "On the way"),
    ("RECIBIDA", "Received"),
]
GRUPO_ETAPA = {"PEND_LIBERACION": "por_facturar", "POR_FACTURAR": "por_facturar", "FACTURADO": "facturado",
               "EN_PL": "facturado", "CONTENEDOR": "en_contenedor", "EN_TRANSITO": "en_camino",
               "ARRIBADO": "en_camino", "ENTREGADO": "en_camino", "RECIBIDO": "recibido"}
ORDEN_OCS = {"oc", "proveedor", "estado", "fecha_xf", "fecha_tienda", "tienda_estimada", "dias_vs_tienda", "avance", "total", "por_facturar",
             "holgura", "centro"}


def _estado_oc(o: dict, lib) -> str:
    if not lib.comercial.libera(o["liberacion_comercial"]):
        return "SIN_COMERCIAL"
    if not lib.logistica.libera(o["liberacion_logistica"]):
        return "SIN_LOGISTICA"
    c = o["cantidades"]
    if c["recibido"] == o["total"]:
        return "RECIBIDA"
    if c["por_facturar"] == o["total"]:
        return "POR_FACTURAR"
    if c["por_facturar"] > 0:
        return "PARCIAL"
    if c["en_camino"] + c["recibido"] == o["total"]:
        return "EN_CAMINO"
    return "FACTURADA"


# Columnas de la tabla de OCs que se filtran por sus valores (el avance, en % entero)
COLUMNAS_OCS = {
    "oc": "oc", "proveedor": "proveedor", "centro": lambda o: f"{o['sociedad']} · {o['centro']}",
    "liberaciones": lambda o: f"{o['comercial_txt'] or '—'} · {o['liberacion_txt'] or '—'}",
    "estado": "estado", "avance": lambda o: None if o["avance"] is None else round(o["avance"]), "por_facturar": "por_facturar",
    "fecha_xf": "fecha_xf", "fecha_tienda": "fecha_tienda", "tienda_estimada": "tienda_estimada",
    "holgura": "riesgo", "embarques": "embarques",
}


def ordenes(db: Session, user: Usuario, proveedor_id: int | None = None, filtros: dict | None = None,
            orden: str | None = None, page: int = 1, size: int = 25, columnas: dict | None = None) -> dict:
    """Seguimiento de las OCs: liberaciones, cuánto está por facturar, en
    contenedor, en camino y recibido, con la holgura a la fecha en tienda.
    `columnas` son los filtros por columna de la tabla (no cambian los
    indicadores ni el resumen por estado)."""
    items, todas = _items_ordenes(db, user, proveedor_id, filtros)
    resumen = {k: 0 for k, _ in ESTADOS_OC}
    for o in items:
        resumen[o["estado"]] += 1
    kpis = {
        "ocs": len(items),
        "liberadas": sum(1 for o in items if o["estado"] not in ("SIN_COMERCIAL", "SIN_LOGISTICA")),
        "sin_liberar": sum(1 for o in items if o["estado"] in ("SIN_COMERCIAL", "SIN_LOGISTICA")),
        "xf_vencida": sum(1 for o in items if o["xf_vencida"]),
        "atraso": sum(1 for o in items if o["llega_tarde"]),
        # Promedio del % facturado de cada OC (por valor): no suma monedas ni unidades
        "avance": round(sum(con) / len(con), 1) if (con := [o["avance"] for o in items if o["avance"] is not None]) else None,
    }
    items = filtrar_columnas(items, COLUMNAS_OCS, columnas)
    items = _ordenar(sorted(items, key=lambda x: x["oc"]), orden or "fecha_xf:asc", ORDEN_OCS)
    return {
        "items": items[(page - 1) * size: page * size], "total": len(items), "page": page, "size": size,
        "kpis": kpis, "estados": [{"clave": k, "nombre": n, "total": resumen[k]} for k, n in ESTADOS_OC],
        "opciones": _opciones(db, todas),
    }


def valores_ordenes(db: Session, user: Usuario, columna: str, q: str | None, columnas: dict,
                    proveedor_id: int | None = None, filtros: dict | None = None) -> list[dict]:
    """Valores únicos de una columna de la tabla de OCs (con los filtros de la pantalla)."""
    tabla.columna_valida(COLUMNAS_OCS, columna)
    items, _ = _items_ordenes(db, user, proveedor_id, filtros)
    return valores_columna(items, COLUMNAS_OCS, columna, q, columnas)


def _avance_oc(o: dict) -> tuple[float | None, dict]:
    """% facturado de una OC y el peso de cada tramo de la barra. Por valor (una
    OC tiene una sola moneda); sin precios, por cantidad solo si toda la OC usa
    la misma unidad de medida (nunca se suman pares con unidades)."""
    if o["con_precio"] and o["valor"]:
        base, partes = o["valor"], o["valores"]
    elif len(o["por_unidad"]) == 1 and o["total"]:
        base, partes = o["total"], o["cantidades"]
    else:
        return None, {}
    tramos = {k: round(v * 100 / base, 2) for k, v in partes.items()}
    return round(100 - tramos["por_facturar"], 1), tramos


def _items_ordenes(db: Session, user: Usuario, proveedor_id: int | None, filtros: dict | None) -> tuple[list, list]:
    """Una fila por OC con los filtros de la pantalla: (OCs, todas las filas de mercancía)."""
    filtros = {k: v for k, v in (filtros or {}).items() if v not in (None, "")}
    todas = filas_seguimiento(db, user, proveedor_id)
    filas = _filtrar(todas, filtros)
    hoy = date.today()
    por_oc: dict[int, dict] = {}
    for f in filas:
        o = por_oc.setdefault(f["oc_id"], {
            "oc_id": f["oc_id"], "oc": f["oc"], "proveedor": f["proveedor"], "sociedad": f["sociedad"],
            "centro": f["centro"], "centro_destino": f["centro_destino"],
            "liberacion_comercial": f["liberacion_comercial"], "liberacion_logistica": f["liberacion_logistica"],
            "fecha_xf": f["fecha_xf"], "fecha_tienda": f["fecha_tienda"], "dias_tienda": f["dias_tienda"],
            "moneda": f["moneda"], "marcas": set(), "unidades": set(), "embarques": set(), "total": 0, "holguras": [],
            "tiendas": [], "por_unidad": {}, "valor": 0.0, "con_precio": True,
            "cantidades": {"por_facturar": 0, "facturado": 0, "en_contenedor": 0, "en_camino": 0, "recibido": 0},
            "valores": {"por_facturar": 0.0, "facturado": 0.0, "en_contenedor": 0.0, "en_camino": 0.0, "recibido": 0.0}})
        grupo = GRUPO_ETAPA[f["etapa"]]
        o["total"] += f["cantidad"]
        o["cantidades"][grupo] += f["cantidad"]
        u = o["por_unidad"].setdefault(f["unidad"], {"cantidad": 0, "por_facturar": 0})
        u["cantidad"] += f["cantidad"]
        if grupo == "por_facturar":
            u["por_facturar"] += f["cantidad"]
        if f["precio"] is None:
            o["con_precio"] = False
        else:
            v = float(f["cantidad"]) * float(f["precio"])
            o["valor"] += v
            o["valores"][grupo] += v
        if f["marca"]:
            o["marcas"].add(f["marca"])
        o["unidades"].add(f["unidad"])
        if f["embarque"]:
            o["embarques"].add(f["embarque"])
        if f["holgura"] is not None:
            o["holguras"].append(f["holgura"])
        if f["tienda_estimada"] and f["etapa"] != "RECIBIDO":
            o["tiendas"].append(f["tienda_estimada"])
    items = []
    lib = liberaciones.de(db)
    tarde = metricas.oc_llegada_tarde(filas)
    for o in por_oc.values():
        o["estado"] = _estado_oc(o, lib)
        o["comercial_txt"] = lib.comercial.nombre(o["liberacion_comercial"])
        o["liberacion_txt"] = lib.logistica.nombre(o["liberacion_logistica"])
        o["comercial_ok"] = lib.comercial.libera(o["liberacion_comercial"])
        o["logistica_ok"] = lib.logistica.libera(o["liberacion_logistica"])
        o["por_facturar"] = o["cantidades"]["por_facturar"]
        o["avance"], o["tramos"] = _avance_oc(o)
        o["holgura"] = min(o.pop("holguras")) if o["holguras"] else None
        tiendas = o.pop("tiendas")
        o["tienda_estimada"] = max(tiendas) if tiendas else None  # cuando llega lo último que falta
        o["dias_vs_tienda"] = (o["tienda_estimada"] - o["fecha_tienda"]).days if o["tienda_estimada"] and o["fecha_tienda"] else None
        o["riesgo"] = _riesgo(o["holgura"])
        o["llega_tarde"] = o["oc_id"] in tarde
        o["xf_vencida"] = bool(o["fecha_xf"] and o["fecha_xf"] < hoy and o["por_facturar"] > 0)
        o["marcas"] = sorted(o["marcas"])
        o["unidades"] = sorted(o["unidades"])
        o["embarques"] = sorted(o["embarques"])
        items.append(o)
    for campo in ("estado", "liberacion_comercial", "liberacion_logistica", "sociedad", "centro", "proveedor"):
        if campo in filtros:
            items = [o for o in items if _en(o[campo], filtros[campo])]
    if filtros.get("xf_vencida") in ("1", "true", True):
        items = [o for o in items if o["xf_vencida"]]
    return items, todas


# ---- Seguimiento de facturación y empaque ------------------------------------
# Una fila por packing list (o por factura que aún no tiene PL): en qué paso
# del documento va, qué le falta y si ya tiene contenedor.
ETAPAS_DOC = [
    ("FACTURA_ABIERTA", "Invoice without packing list"),
    ("EMPACANDO", "Packing"),
    ("POR_FINALIZAR_PL", "Packed, to finalize"),
    ("POR_FINALIZAR_FACTURA", "PL ready, invoice open"),
    ("LISTO_EMBARQUE", "Ready to ship"),
    ("TENTATIVO", "Tentative in container"),
    ("EN_CONTENEDOR", "Confirmed in container"),
    ("EN_CAMINO", "On the way"),
    ("RECIBIDO", "Received"),
]
ORDEN_DOC = {"factura", "fecha", "proveedor", "estado_factura", "estado_pl", "etapa", "avance", "cajas",
             "peso_bruto", "cbm", "embarque", "dias", "pendientes", "centro", "actualizado"}


def _etapa_doc(f, pl, avance: float) -> str:
    if pl is None:
        return "FACTURA_ABIERTA"
    if pl.unidad:
        e = pl.unidad.embarque
        if e.estado == "RECIBIDO":
            return "RECIBIDO"
        if e.estado != "PLANIFICADO":
            return "EN_CAMINO"
        return "EN_CONTENEDOR" if pl.asignacion == "CONFIRMADA" else "TENTATIVO"
    if pl.estado != "FINALIZADO":
        return "EMPACANDO" if avance < 100 else "POR_FINALIZAR_PL"
    return "LISTO_EMBARQUE" if f.estado == "FINALIZADA" else "POR_FINALIZAR_FACTURA"


# Columnas de la tabla de documentos que se filtran por sus valores (el avance, en % entero)
COLUMNAS_DOC = {
    "factura": "factura", "proveedor": "proveedor", "centro": lambda f: f"{f['sociedad']} · {f['centro'] or '—'}",
    "estado_factura": "estado_factura", "estado_pl": "estado_pl", "avance": lambda f: round(f["avance"]) if f["pl_id"] else None,
    "cajas": "cajas", "pendientes": "pendientes", "etapa": "etapa", "embarque": "contenedor", "dias": "dias",
}


def seguimiento_documentos(db: Session, user: Usuario, proveedor_id: int | None = None, filtros: dict | None = None,
                           orden: str | None = None, page: int = 1, size: int = 25, columnas: dict | None = None) -> dict:
    """Una fila por packing list (o por factura sin PL) con su paso; `columnas`
    son los filtros por columna de la tabla (no cambian los indicadores)."""
    filas, opciones = _filas_documentos(db, user, proveedor_id, filtros)
    resumen = {k: 0 for k, _ in ETAPAS_DOC}
    for f in filas:
        resumen[f["etapa"]] += 1
    facturas = {f["factura_id"]: f for f in filas}.values()
    kpis = {
        "facturas": len(facturas),
        "facturas_abiertas": sum(1 for f in facturas if f["estado_factura"] in ("BORRADOR", "EN_CORRECCION")),
        "pls": sum(1 for f in filas if f["pl_id"]),
        "empacando": resumen["EMPACANDO"] + resumen["POR_FINALIZAR_PL"],
        "listos": resumen["LISTO_EMBARQUE"],
        "con_pendientes": sum(1 for f in filas if f["pendientes"] or f["pendientes_factura"]),
        "cajas": sum(f["cajas"] for f in filas), "pallets": sum(f["pallets"] for f in filas),
        "peso_bruto": round(sum(f["peso_bruto"] for f in filas), 1), "cbm": round(sum(f["cbm"] for f in filas), 2),
        "importe": {m: round(sum(f["importe"] for f in facturas if f["moneda"] == m), 2)
                    for m in {f["moneda"] for f in facturas}},
    }
    filas = filtrar_columnas(filas, COLUMNAS_DOC, columnas)
    col, _, direccion = (orden or "").partition(":")
    if col in ORDEN_DOC:
        indice = {k: i for i, (k, _) in enumerate(ETAPAS_DOC)}
        clave = (lambda f: indice[f["etapa"]]) if col == "etapa" else (lambda f: (f[col] is None, f[col] or 0))
        filas = sorted(filas, key=clave, reverse=direccion == "desc")
    total = len(filas)
    return {
        "items": filas[(page - 1) * size: page * size],
        "total": total, "page": page, "size": size,
        "etapas": [{"clave": k, "nombre": n, "total": resumen[k]} for k, n in ETAPAS_DOC],
        "kpis": kpis,
        "opciones": {**opciones, "embarques": [{"id": i, "codigo": c} for i, c in opciones["embarques"]]},
    }


def valores_documentos(db: Session, user: Usuario, columna: str, q: str | None, columnas: dict,
                       proveedor_id: int | None = None, filtros: dict | None = None) -> list[dict]:
    """Valores únicos de una columna de la tabla de documentos (con los filtros de la pantalla)."""
    tabla.columna_valida(COLUMNAS_DOC, columna)
    filas, _ = _filas_documentos(db, user, proveedor_id, filtros)
    return valores_columna(filas, COLUMNAS_DOC, columna, q, columnas)


def _filas_documentos(db: Session, user: Usuario, proveedor_id: int | None, filtros: dict | None) -> tuple[list, dict]:
    """Las filas de documentos con los filtros de la pantalla y las opciones de los filtros."""
    from app.modulos.empaque.packing import validar_pl
    from app.modulos.facturacion.cantidades import totales_pl
    from app.modulos.facturacion.estados import EDITABLE_PL
    from app.modulos.facturacion.facturas import validar_factura

    filtros = {k: v for k, v in (filtros or {}).items() if v not in (None, "")}
    prov = proveedor_filtro(user, proveedor_id)
    consulta = select(Factura).where(Factura.estado != "CANCELADA").order_by(Factura.id)
    if prov:
        consulta = consulta.where(Factura.proveedor_id.in_(prov))
    consulta = consulta.where(*sociedad_filtro(user, Factura.sociedad))
    hoy = date.today()
    filas = []
    for f in db.scalars(consulta).all():
        ocs = sorted({l.oc_numero for l in f.lineas})
        importe = round(sum(l.cantidad * l.precio_unitario for l in f.lineas), 2)
        base = {
            "factura_id": f.id, "factura": nombre_factura(f), "fecha": f.fecha, "proveedor": f.proveedor.nombre,
            "sociedad": f.sociedad, "centro": f.centro, "centro_destino": f.centro_destino, "ocs": ocs,
            "estado_factura": f.estado, "importe": importe, "moneda": f.moneda,
            "dias": (hoy - f.creado_en.date()).days if f.creado_en else None,
            "pendientes_factura": len(validar_factura(db, f)) if f.estado in ("BORRADOR", "EN_CORRECCION") else 0,
        }
        pls = [pl for pl in f.packing_lists if pl.estado != "CANCELADO"]
        for pl in pls or [None]:
            fila = {**base, "pl_id": None, "pl": None, "estado_pl": None, "avance": 0, "cajas": 0, "pallets": 0,
                    "peso_bruto": 0, "cbm": 0, "pendientes": 0, "contenedor": None, "embarque_id": None,
                    "embarque": None, "estado_embarque": None, "asignacion": None, "recolectado_en": None,
                    "eta": None, "actualizado": f.actualizado_en}
            avance = 0.0
            if pl:
                t = totales_pl(pl)
                total = sum(u["cantidad"] for u in t["por_unidad"].values())
                avance = round(sum(u["en_cajas"] for u in t["por_unidad"].values()) * 100 / total, 1) if total else 0
                fila.update(pl_id=pl.id, pl=pl.numero, estado_pl=pl.estado, avance=avance, cajas=t["cajas"],
                            pallets=t["pallets"], peso_bruto=t["peso_bruto"], cbm=t["cbm"],
                            pendientes=len(validar_pl(pl)) if pl.estado in EDITABLE_PL else 0,
                            recolectado_en=pl.recolectado_en, asignacion=pl.asignacion,
                            actualizado=max(pl.actualizado_en, f.actualizado_en))
                if pl.unidad:
                    e = pl.unidad.embarque
                    fila.update(contenedor=pl.unidad.numero or pl.unidad.etiqueta, embarque_id=e.id,
                                embarque=e.codigo, estado_embarque=e.estado, eta=e.arribo_real or e.eta)
            fila["etapa"] = _etapa_doc(f, pl, avance)
            filas.append(fila)

    opciones = {
        "proveedores": _valores(filas, "proveedor"),
        "sociedades": _valores(filas, "sociedad"),
        "centros": _valores(filas, "centro"),
        "embarques": sorted({(f["embarque_id"], f["embarque"]) for f in filas if f["embarque_id"]}),
    }
    for campo in ("etapa", "estado_factura", "estado_pl", "sociedad", "centro", "embarque_id", "proveedor"):
        if campo in filtros:
            filas = [f for f in filas if _en(f[campo], filtros[campo])]
    if filtros.get("con_pendientes") in ("1", "true", True):
        filas = [f for f in filas if f["pendientes"] or f["pendientes_factura"]]
    if filtros.get("q"):
        t = filtros["q"].strip().lower()
        filas = [f for f in filas if t in f["factura"].lower() or t in (f["pl"] or "").lower()
                 or any(t in oc for oc in f["ocs"]) or t in (f["contenedor"] or "").lower()]
    return filas, opciones


# ---- Lead times: la lista de OCs con filtros por columna ---------------------------
# El cálculo es de transporte/leadtimes.py; aquí solo se filtra por columna la
# lista de OCs (los indicadores y los promedios por origen no cambian).
COLUMNAS_LT = {
    "oc": "oc", "proveedor": "proveedor", "origen": "origen_nombre",
    "lib": lambda i: (("a_tiempo" if i["lib_a_tiempo"] else "tarde") if i["lib_dias_antes_xf"] is not None
                      else "vencida" if i["lib_vencida"] else "pendiente"),
    "fecha_xf": "fecha_xf", "arribo": "arribo", "limite_puerto": "limite_puerto", "fecha_tienda": "fecha_tienda",
    "tienda_estimada": "tienda_estimada", "holgura": "riesgo",
}


def leadtimes(db: Session, user: Usuario, proveedor_id: int | None = None, filtros: dict | None = None,
              orden: str | None = None, page: int = 1, size: int = 25, columnas: dict | None = None) -> dict:
    """Lead times por origen y la lista de OCs, paginada después de los filtros por columna."""
    r = lt.leadtimes(db, user, proveedor_id, filtros, orden, 1, TODO)
    items = filtrar_columnas(r["items"], COLUMNAS_LT, columnas)
    return {**r, "items": items[(page - 1) * size: page * size], "total": len(items), "page": page, "size": size}


def valores_leadtimes(db: Session, user: Usuario, columna: str, q: str | None, columnas: dict,
                      proveedor_id: int | None = None, filtros: dict | None = None) -> list[dict]:
    """Valores únicos de una columna de la lista de OCs de lead times."""
    tabla.columna_valida(COLUMNAS_LT, columna)
    items = lt.leadtimes(db, user, proveedor_id, filtros, None, 1, TODO)["items"]
    return valores_columna(items, COLUMNAS_LT, columna, q, columnas)
