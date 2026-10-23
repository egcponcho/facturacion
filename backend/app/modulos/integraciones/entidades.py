"""Entidades que se intercambian con un sistema externo.

Cada entidad declara sus campos internos (los nombres del sistema, nunca los
de un ERP) y cómo se aplica o se arma, siempre por los servicios del núcleo:
una OC que entra por una integración pasa por las mismas validaciones,
deduplicación y reglas de liberación que la que se carga a mano.

- ENTRADA `ordenes_compra`: filas de líneas de OC → vista previa
  (ordenes._clasificar) y aplicación (ordenes.aplicar_importacion). Su
  referencia externa es «proveedor/número de OC».
- SALIDA `facturas`: una fila por línea de factura finalizada. Su referencia
  externa es el número de la factura; con «solo nuevas» no se reenvía una
  factura que ya salió por esa integración.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.errores import ErrorNegocio
from app.modelos import Factura, ImportacionOC, Usuario
from app.modulos.catalogo import servicio as catalogo_svc


# ---- Órdenes de compra (entrada) ------------------------------------------------
def campos_ordenes() -> list[dict]:
    from app.modulos.compras import perfiles

    return [{"campo": c["campo"], "etiqueta": c["etiqueta"], "requerido": c["requerido"], "fecha": c["fecha"]}
            for c in perfiles.campos()]


def previa_ordenes(db: Session, user: Usuario, filas: list[dict], archivo: str) -> dict:
    """Clasifica las filas como la carga de OCs (nuevo, cambio, sin cambio,
    conflicto, error) sin aplicar nada. Devuelve la importación creada."""
    from app.modulos.compras import ordenes

    imp = ImportacionOC(usuario_id=user.id, nombre_archivo=archivo[:300], filas=filas)
    db.add(imp)
    db.flush()
    clasificadas = ordenes._clasificar(db, filas)
    return {"importacion_oc_id": imp.id, "resumen": ordenes._resumen(clasificadas),
            "filas": [{k: v for k, v in c.items() if k != "datos"} for c in clasificadas]}


def aplicar_ordenes(db: Session, user: Usuario, importacion_oc_id: int) -> dict:
    from app.modulos.compras import ordenes

    imp = db.get(ImportacionOC, importacion_oc_id)
    if imp is None:
        raise ErrorNegocio("The import does not exist.", 404, "no_encontrado")
    res = ordenes.aplicar_importacion(db, user, imp)
    referencias = [(oc["id"], f"{oc['proveedor']}/{oc['numero']}") for oc in res.get("ocs", [])]
    return {**res, "referencias": referencias}


# ---- Facturas (salida) ----------------------------------------------------------
CAMPOS_FACTURAS = [
    ("factura", "Invoice number"), ("fecha", "Invoice date"), ("proveedor", "Supplier code"), ("sociedad", "Company"),
    ("centro", "Plant"), ("moneda", "Currency"), ("incoterm", "Incoterm"), ("oc", "PO number"), ("posicion", "PO line"),
    ("codigo_articulo", "Item code"), ("codigo_barras", "Barcode"), ("descripcion", "Description"), ("variante", "Variant"),
    ("cantidad", "Quantity"), ("unidad", "Unit"), ("precio", "Unit price"), ("importe", "Amount"),
    ("partida", "HS code"), ("pais_origen", "Country of origin"),
]


def campos_facturas() -> list[dict]:
    return [{"campo": c, "etiqueta": e, "requerido": False, "fecha": c == "fecha"} for c, e in CAMPOS_FACTURAS]


def filas_facturas(db: Session, excluir_ids: set[int], desde=None) -> tuple[list[dict], list[tuple[int, str]]]:
    """Las líneas de las facturas finalizadas (menos las excluidas), con su
    referencia (id, número) para registrar qué se envió."""
    consulta = (select(Factura).where(Factura.estado == "FINALIZADA").options(selectinload(Factura.lineas))
                .order_by(Factura.finalizado_en, Factura.id))
    if desde:
        consulta = consulta.where(Factura.fecha >= desde)
    filas, enviadas = [], []
    for f in db.scalars(consulta):
        if f.id in excluir_ids:
            continue
        enviadas.append((f.id, f.numero or f"#{f.id}"))
        for li in f.lineas:
            filas.append({
                "factura": f.numero, "fecha": f.fecha.isoformat() if f.fecha else None,
                "proveedor": f.proveedor.codigo if f.proveedor else None, "sociedad": f.sociedad, "centro": f.centro,
                "moneda": f.moneda, "incoterm": f.incoterm, "oc": li.oc_numero, "posicion": li.posicion,
                "codigo_articulo": li.codigo_articulo, "codigo_barras": li.codigo_barras, "descripcion": li.descripcion,
                "variante": catalogo_svc.texto(catalogo_svc.ordenar(db, li.variante)),
                "cantidad": li.cantidad, "unidad": li.unidad, "precio": li.precio_unitario,
                "importe": round(float(li.cantidad) * float(li.precio_unitario), 2),
                "partida": li.partida_arancelaria, "pais_origen": li.pais_origen,
            })
    return filas, enviadas


# entidad → (direcciones, campos internos, permiso del núcleo que además exige)
ENTIDADES = {
    "ordenes_compra": {"direcciones": ("ENTRADA",), "campos": campos_ordenes, "permiso": "oc.importar",
                       "nombre": "Purchase orders"},
    "facturas": {"direcciones": ("SALIDA",), "campos": campos_facturas, "permiso": "factura.ver",
                 "nombre": "Invoices"},
}


def de(entidad: str, direccion: str) -> dict:
    e = ENTIDADES.get(entidad)
    if e is None or direccion not in e["direcciones"]:
        raise ErrorNegocio(f"The entity {entidad} cannot be exchanged in direction {direccion}.", 422, "validacion")
    return e


def catalogo() -> list[dict]:
    return [{"entidad": k, "nombre": v["nombre"], "direcciones": list(v["direcciones"]), "campos": v["campos"]()}
            for k, v in ENTIDADES.items()]
