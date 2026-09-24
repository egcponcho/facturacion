import csv
import io
import unicodedata
from datetime import date, datetime

from openpyxl import load_workbook
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import (
    Alerta,
    Factura,
    FacturaLinea,
    ImportacionOC,
    OrdenCompra,
    PosicionOC,
    Proveedor,
    Usuario,
    ahora,
)
from .cantidades import facturado_por_posicion, facturas_por_posicion
from .common import ErrorNegocio, asegurar_proveedor, exigir, proveedor_filtro, registrar


# ---- Vista general de OCs ---------------------------------------------------
def listar_ordenes(
    db: Session,
    user: Usuario,
    proveedor_id: int | None = None,
    q: str | None = None,
    centro: str | None = None,
    solo_disponible: bool = True,
    page: int = 1,
    size: int = 25,
) -> dict:
    exigir(user, "oc.ver")
    prov = proveedor_filtro(user, proveedor_id)

    tot = (
        select(
            PosicionOC.oc_id.label("oc_id"),
            func.sum(PosicionOC.cantidad).label("cantidad"),
            func.sum(PosicionOC.cantidad * PosicionOC.precio).label("importe"),
            func.count(PosicionOC.id).label("n"),
        )
        .group_by(PosicionOC.oc_id)
        .subquery()
    )
    fac = (
        select(
            PosicionOC.oc_id.label("oc_id"),
            func.sum(FacturaLinea.cantidad).label("facturado"),
            func.sum(FacturaLinea.cantidad * PosicionOC.precio).label("importe_facturado"),
        )
        .join(FacturaLinea, FacturaLinea.posicion_oc_id == PosicionOC.id)
        .join(Factura, Factura.id == FacturaLinea.factura_id)
        .where(Factura.estado != "CANCELADA")
        .group_by(PosicionOC.oc_id)
        .subquery()
    )
    facturado = func.coalesce(fac.c.facturado, 0)
    consulta = (
        select(OrdenCompra, Proveedor.nombre, tot.c.importe, tot.c.n, func.coalesce(fac.c.importe_facturado, 0))
        .join(Proveedor, Proveedor.id == OrdenCompra.proveedor_id)
        .join(tot, tot.c.oc_id == OrdenCompra.id)
        .outerjoin(fac, fac.c.oc_id == OrdenCompra.id)
    )
    if prov:
        consulta = consulta.where(OrdenCompra.proveedor_id == prov)
    if q:
        patron = f"%{q.strip()}%"
        sub = select(PosicionOC.oc_id).where(
            or_(
                PosicionOC.estilo.ilike(patron),
                PosicionOC.codigo_sap.ilike(patron),
                PosicionOC.upc.ilike(patron),
            )
        )
        consulta = consulta.where(or_(OrdenCompra.numero.ilike(patron), OrdenCompra.id.in_(sub)))
    if centro:
        consulta = consulta.where(OrdenCompra.centro == centro)
    if solo_disponible:
        consulta = consulta.where(tot.c.cantidad - facturado > 0)

    total = db.scalar(select(func.count()).select_from(consulta.subquery())) or 0
    filas = db.execute(
        consulta.order_by(OrdenCompra.fecha.desc().nullslast(), OrdenCompra.numero)
        .offset((page - 1) * size)
        .limit(size)
    ).all()

    # Cantidades por unidad de medida: nunca se suman pares con unidades
    ids = [oc.id for oc, *_ in filas]
    por_unidad: dict[int, dict] = {i: {} for i in ids}
    if ids:
        for oc_id, unidad, cant in db.execute(
            select(PosicionOC.oc_id, PosicionOC.unidad, func.sum(PosicionOC.cantidad))
            .where(PosicionOC.oc_id.in_(ids)).group_by(PosicionOC.oc_id, PosicionOC.unidad)
        ).all():
            por_unidad[oc_id][unidad] = {"cantidad": int(cant or 0), "facturado": 0, "disponible": int(cant or 0)}
        for oc_id, unidad, cant in db.execute(
            select(PosicionOC.oc_id, PosicionOC.unidad, func.sum(FacturaLinea.cantidad))
            .join(FacturaLinea, FacturaLinea.posicion_oc_id == PosicionOC.id)
            .join(Factura, Factura.id == FacturaLinea.factura_id)
            .where(Factura.estado != "CANCELADA", PosicionOC.oc_id.in_(ids))
            .group_by(PosicionOC.oc_id, PosicionOC.unidad)
        ).all():
            d = por_unidad[oc_id][unidad]
            d["facturado"] = int(cant or 0)
            d["disponible"] = max(d["cantidad"] - d["facturado"], 0)

    items = []
    for oc, prov_nombre, importe, n, importe_fact in filas:
        importe = float(importe or 0)
        items.append(
            {
                **_cabecera_oc(oc),
                "proveedor": prov_nombre,
                "posiciones": n,
                "por_unidad": por_unidad[oc.id],
                "importe": round(importe, 2),
                "importe_facturado": round(float(importe_fact or 0), 2),
                # Avance por valor: es comparable aunque la OC mezcle pares y unidades
                "avance": round(float(importe_fact or 0) * 100 / importe, 1) if importe else 0,
            }
        )
    return {"items": items, "total": total, "page": page, "size": size}


def _cabecera_oc(oc: OrdenCompra) -> dict:
    return {
        "id": oc.id,
        "numero": oc.numero,
        "proveedor_id": oc.proveedor_id,
        "sociedad": oc.sociedad,
        "centro": oc.centro,
        "pais_destino": oc.pais_destino,
        "moneda": oc.moneda,
        "incoterm": oc.incoterm,
        "fecha": oc.fecha,
        "liberada": oc.liberada,
    }


def posiciones_oc(db: Session, user: Usuario, oc_id: int) -> dict:
    exigir(user, "oc.ver")
    oc = db.get(OrdenCompra, oc_id)
    if not oc:
        raise ErrorNegocio("La orden de compra no existe.", 404, "no_encontrado")
    asegurar_proveedor(user, oc.proveedor_id)
    ids = [p.id for p in oc.posiciones]
    facturado = facturado_por_posicion(db, ids)
    facturas = facturas_por_posicion(db, ids)
    posiciones = []
    for p in oc.posiciones:
        fact = facturado.get(p.id, 0)
        fs = facturas.get(p.id, [])
        estado, motivo, restringida = estado_posicion(oc, p, fact, fs)
        posiciones.append(
            {
                "id": p.id,
                "posicion": p.posicion,
                "codigo_sap": p.codigo_sap,
                "upc": p.upc,
                "estilo": p.estilo,
                "color": p.color,
                "talla": p.talla,
                "descripcion": p.descripcion,
                "cantidad": p.cantidad,
                "unidad": p.unidad,
                "precio": p.precio,
                "fecha_entrega": p.fecha_entrega,
                "pais_origen": p.pais_origen,
                "partida_arancelaria": p.partida_arancelaria,
                "facturado": fact,
                "disponible": max(p.cantidad - fact, 0),
                "facturas": fs,
                "estado": estado,
                "motivo": motivo,
                "solo_factura_id": restringida,
            }
        )
    prov = db.get(Proveedor, oc.proveedor_id)
    return {"oc": {**_cabecera_oc(oc), "proveedor": prov.nombre}, "posiciones": posiciones}


def estado_posicion(oc, p, facturado: int, facturas: list[dict]):
    """Devuelve (estado, motivo, factura a la que queda restringido el saldo)."""
    disponible = p.cantidad - facturado
    if not oc.liberada:
        return "NO_DISPONIBLE", "La OC no está liberada.", None
    if p.bloqueada:
        return "NO_DISPONIBLE", p.motivo_bloqueo or "Posición bloqueada.", None
    if disponible <= 0:
        return "FACTURADA", None, None
    if facturado > 0:
        if not settings.POSICION_EN_VARIAS_FACTURAS and facturas:
            f = facturas[0]
            return "PARCIAL", f"El saldo solo puede agregarse a {f['nombre']}.", f["id"]
        return "PARCIAL", None, None
    return "DISPONIBLE", None, None


# ---- Importación ------------------------------------------------------------
ALIAS = {
    "proveedor": ["proveedor", "codigo_proveedor", "proveedor_codigo", "vendor"],
    "oc": ["oc", "orden", "orden_compra", "numero_oc", "po"],
    "posicion": ["posicion", "pos", "item", "linea"],
    "sociedad": ["sociedad", "company", "compania"],
    "centro": ["centro", "plant", "bodega"],
    "pais_destino": ["pais_destino", "destino"],
    "moneda": ["moneda", "currency"],
    "incoterm": ["incoterm"],
    "fecha_oc": ["fecha_oc", "fecha"],
    "codigo_sap": ["codigo_sap", "sap", "material", "codigo"],
    "upc": ["upc", "ean"],
    "estilo": ["estilo", "style"],
    "color": ["color"],
    "talla": ["talla", "size"],
    "descripcion": ["descripcion", "description"],
    "cantidad": ["cantidad", "qty", "quantity"],
    "unidad": ["unidad", "um", "uom"],
    "precio": ["precio", "precio_unitario", "price"],
    "fecha_entrega": ["fecha_entrega", "entrega"],
    "pais_origen": ["pais_origen", "origen", "coo"],
    "partida_arancelaria": ["partida_arancelaria", "partida", "hs_code", "hts"],
    "liberada": ["liberada", "estado_liberacion"],
}
REQUERIDOS = ["proveedor", "oc", "posicion", "codigo_sap", "cantidad", "unidad", "precio", "moneda", "sociedad"]
CAMPOS_CABECERA = ["sociedad", "centro", "pais_destino", "moneda", "incoterm", "fecha", "liberada"]
CAMPOS_POSICION = [
    "codigo_sap", "upc", "estilo", "color", "talla", "descripcion", "cantidad", "unidad",
    "precio", "fecha_entrega", "pais_origen", "partida_arancelaria",
]
UNIDADES = {"PAR": "PAR", "PR": "PAR", "PARES": "PAR", "PRS": "PAR",
            "UN": "UN", "UND": "UN", "UNIDAD": "UN", "UNIDADES": "UN", "EA": "UN", "PC": "UN", "PZA": "UN"}


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


def _leer_archivo(nombre: str, contenido: bytes) -> list[dict]:
    if nombre.lower().endswith((".xlsx", ".xlsm")):
        wb = load_workbook(io.BytesIO(contenido), read_only=True, data_only=True)
        ws = wb.active
        filas = list(ws.iter_rows(values_only=True))
        if not filas:
            return []
        encabezados = [_texto(h) for h in filas[0]]
        datos = [[_texto(v) for v in fila] for fila in filas[1:]]
    else:
        texto = contenido.decode("utf-8-sig", errors="replace")
        muestra = texto[:2000]
        delimitador = ";" if muestra.count(";") > muestra.count(",") else ","
        lector = list(csv.reader(io.StringIO(texto), delimiter=delimitador))
        if not lector:
            return []
        encabezados = lector[0]
        datos = [[v.strip() for v in fila] for fila in lector[1:]]

    mapa = {}
    for i, h in enumerate(encabezados):
        n = _norm(h)
        for campo, alias in ALIAS.items():
            if n in alias and campo not in mapa:
                mapa[campo] = i
    faltan = [c for c in REQUERIDOS if c not in mapa]
    if faltan:
        raise ErrorNegocio(
            "Al archivo le faltan columnas obligatorias: " + ", ".join(faltan) + ".",
            422,
            "columnas_faltantes",
            {"faltan": faltan, "encontradas": encabezados},
        )
    filas_dict = []
    for n_fila, fila in enumerate(datos, start=2):
        if not any(fila):
            continue
        registro = {campo: (fila[i] if i < len(fila) else "") for campo, i in mapa.items()}
        registro["_fila"] = n_fila
        filas_dict.append(registro)
    return filas_dict


def _fecha(valor: str) -> date | None:
    if not valor:
        return None
    for formato in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(valor[:10], formato).date()
        except ValueError:
            continue
    raise ValueError(f"fecha no válida: {valor}")


def _normalizar(registro: dict) -> tuple[dict, list[str]]:
    """Convierte los textos de una fila en valores tipados. Los códigos se
    mantienen como texto para conservar ceros iniciales."""
    errores = []
    r = {k: (v or "").strip() for k, v in registro.items() if k != "_fila"}
    for campo in REQUERIDOS:
        if not r.get(campo):
            errores.append(f"Falta {campo}.")
    datos = {
        "proveedor": r.get("proveedor", ""),
        "oc": r.get("oc", ""),
        "posicion": r.get("posicion", ""),
        "sociedad": r.get("sociedad", ""),
        "centro": r.get("centro") or None,
        "pais_destino": (r.get("pais_destino") or "").upper() or None,
        "moneda": (r.get("moneda") or "").upper(),
        "incoterm": (r.get("incoterm") or "").upper() or None,
        "codigo_sap": r.get("codigo_sap", ""),
        "upc": r.get("upc") or None,
        "estilo": r.get("estilo") or None,
        "color": r.get("color") or None,
        "talla": r.get("talla") or None,
        "descripcion": r.get("descripcion") or None,
        "pais_origen": (r.get("pais_origen") or "").upper() or None,
        "partida_arancelaria": r.get("partida_arancelaria") or None,
        "liberada": (r.get("liberada") or "si").lower() not in ("no", "0", "false", "bloqueada", "n"),
    }
    try:
        cant = float(r.get("cantidad", "").replace(",", "")) if r.get("cantidad") else None
        if cant is not None and (cant < 0 or not cant.is_integer()):
            raise ValueError
        datos["cantidad"] = int(cant) if cant is not None else None
    except ValueError:
        errores.append(f"Cantidad no válida: {r.get('cantidad')}.")
        datos["cantidad"] = None
    try:
        datos["precio"] = float(r.get("precio", "").replace(",", "")) if r.get("precio") else None
        if datos["precio"] is not None and datos["precio"] < 0:
            raise ValueError
    except ValueError:
        errores.append(f"Precio no válido: {r.get('precio')}.")
        datos["precio"] = None
    unidad = UNIDADES.get((r.get("unidad") or "").upper())
    if r.get("unidad") and not unidad:
        errores.append(f"Unidad no reconocida: {r.get('unidad')} (usa PAR o UN).")
    datos["unidad"] = unidad
    for campo, destino in (("fecha_oc", "fecha"), ("fecha_entrega", "fecha_entrega")):
        try:
            datos[destino] = _fecha(r.get(campo, ""))
        except ValueError as e:
            errores.append(str(e).capitalize() + ".")
            datos[destino] = None
    return datos, errores


def _clasificar(db: Session, filas: list[dict]) -> list[dict]:
    proveedores = {p.codigo: p for p in db.scalars(select(Proveedor)).all()}
    vistos: set = set()
    cabeceras: dict = {}
    resultado = []
    normalizadas = []
    for registro in filas:
        datos, errores = _normalizar(registro)
        normalizadas.append((registro, datos, errores))

    # Posiciones existentes involucradas
    claves_oc = {(d["proveedor"], d["oc"]) for _, d, _ in normalizadas}
    ocs_existentes = {}
    for codigo, numero in claves_oc:
        prov = proveedores.get(codigo)
        if prov:
            oc = db.scalar(
                select(OrdenCompra).where(
                    OrdenCompra.proveedor_id == prov.id, OrdenCompra.numero == numero
                )
            )
            if oc:
                ocs_existentes[(codigo, numero)] = oc
    ids_pos = [p.id for oc in ocs_existentes.values() for p in oc.posiciones]
    facturado = facturado_por_posicion(db, ids_pos)

    for registro, d, errores in normalizadas:
        clave = f"{d['proveedor']} / OC {d['oc']} / pos. {d['posicion']}"
        salida = {"fila": registro.get("_fila"), "clave": clave, "datos": registro,
                  "mensajes": list(errores), "cambios": {}}
        prov = proveedores.get(d["proveedor"])
        if d["proveedor"] and not prov:
            salida["mensajes"].append(f"El proveedor {d['proveedor']} no existe.")
        k = (d["proveedor"], d["oc"], d["posicion"])
        if k in vistos:
            salida["mensajes"].append("Posición repetida dentro del archivo.")
        vistos.add(k)
        cab = {c: d[c] for c in CAMPOS_CABECERA}
        previa = cabeceras.setdefault((d["proveedor"], d["oc"]), cab)
        if previa != cab:
            salida["mensajes"].append("Los datos de cabecera no coinciden con otras filas de la misma OC.")
        if salida["mensajes"]:
            salida["estado"] = "error"
            resultado.append(salida)
            continue

        oc = ocs_existentes.get((d["proveedor"], d["oc"]))
        pos = next((p for p in oc.posiciones if p.posicion == d["posicion"]), None) if oc else None
        if not pos:
            salida["estado"] = "nuevo"
            resultado.append(salida)
            continue

        cambios = {}
        for c in CAMPOS_CABECERA:
            anterior = getattr(oc, c)
            if anterior != d[c]:
                cambios[c] = {"antes": anterior, "despues": d[c]}
        for c in CAMPOS_POSICION:
            anterior = getattr(pos, c)
            nuevo = d[c]
            if isinstance(anterior, float) and nuevo is not None:
                igual = abs(anterior - nuevo) < 1e-9
            else:
                igual = anterior == nuevo
            if not igual:
                cambios[c] = {"antes": anterior, "despues": nuevo}
        salida["cambios"] = cambios
        fact = facturado.get(pos.id, 0)
        if not cambios:
            salida["estado"] = "sin_cambio"
        elif fact and d["cantidad"] is not None and d["cantidad"] < fact:
            salida["estado"] = "conflicto"
            salida["mensajes"].append(
                f"La nueva cantidad ({d['cantidad']}) es menor que lo ya facturado ({fact})."
            )
        elif fact and any(c in cambios for c in ("sociedad", "moneda", "centro", "unidad")):
            salida["estado"] = "conflicto"
            salida["mensajes"].append(
                "Cambian datos clave (sociedad, moneda, centro o unidad) de una posición ya facturada."
            )
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


def importar_previa(db: Session, user: Usuario, nombre: str, contenido: bytes) -> dict:
    exigir(user, "oc.importar")
    filas = _leer_archivo(nombre, contenido)
    if not filas:
        raise ErrorNegocio("El archivo no tiene filas con datos.", 422, "archivo_vacio")
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
        raise ErrorNegocio("La importación no existe.", 404, "no_encontrado")
    if imp.estado == "APLICADA":
        return {"ya_aplicada": True, **(imp.resultado or {})}
    # Se vuelve a clasificar: los datos pudieron cambiar desde la vista previa
    clasificadas = _clasificar(db, imp.filas)
    proveedores = {p.codigo: p for p in db.scalars(select(Proveedor)).all()}
    aplicadas = 0
    for c in clasificadas:
        if c["estado"] == "conflicto":
            d, _ = _normalizar(c["datos"])
            prov = proveedores.get(d["proveedor"])
            db.add(
                Alerta(
                    proveedor_id=prov.id if prov else None,
                    tipo="conflicto_oc",
                    mensaje=f"{c['clave']}: " + " ".join(c["mensajes"]),
                    referencia={"importacion_id": imp.id, "fila": c["fila"]},
                )
            )
        if c["estado"] not in ("nuevo", "cambio"):
            continue
        d, _ = _normalizar(c["datos"])
        prov = proveedores[d["proveedor"]]
        oc = db.scalar(
            select(OrdenCompra).where(OrdenCompra.proveedor_id == prov.id, OrdenCompra.numero == d["oc"])
        )
        if not oc:
            oc = OrdenCompra(proveedor_id=prov.id, numero=d["oc"])
            db.add(oc)
        for campo in CAMPOS_CABECERA:
            setattr(oc, campo, d[campo])
        oc.actualizado_en = ahora()
        db.flush()
        pos = db.scalar(
            select(PosicionOC).where(PosicionOC.oc_id == oc.id, PosicionOC.posicion == d["posicion"])
        )
        if not pos:
            pos = PosicionOC(oc_id=oc.id, posicion=d["posicion"])
            db.add(pos)
        for campo in CAMPOS_POSICION:
            setattr(pos, campo, d[campo])
        aplicadas += 1
    resultado = {"resumen": _resumen(clasificadas), "aplicadas": aplicadas}
    imp.estado = "APLICADA"
    imp.resultado = resultado
    registrar(db, user, "importacion_oc", imp.id, "aplicar", resultado)
    return resultado
