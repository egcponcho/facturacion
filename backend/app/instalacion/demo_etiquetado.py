"""Etiquetado de la demostración: cómo queda una empresa ya configurada.

- Tipos de etiqueta: colgante (obligatoria), sticker de precio, etiqueta de
  caja (obligatoria) y hoja de contenido de OC.
- Familias: las de los productos (demo.py: calzado con una subfamilia técnica,
  ropa y accesorios). El calzado y la ropa tienen su colgante; la mochila
  (accesorios) lleva un diseño propio de su producto.
- Diseños aprobados para cada tipo, uno con una versión nueva esperando
  aprobación.
- Qué diseño lleva cada cosa: diseños generales, por familia, por producto,
  una excepción por país destino, una excepción de una OC y un uso dado de baja.
- Trabajos de ejemplo desde una OC (generado), artículos sueltos (prueba),
  una lista de empaque (validado), una familia (borrador) y uno con un dato
  pendiente (para corregir en el asistente). Cada uno dice cómo se creó.

Todo se crea con los mismos servicios que usa la pantalla (validaciones,
historial y versiones incluidos).
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modelos import Articulo, Atributo, OrdenCompra, PackingList, Producto, ProductoAtributo, Usuario

# id de elemento, tipo y lo demás: el diseño se valida y completa con diseno.validar
_TEXTO = {"fuente": "sans", "tam": 9}


def _colgante(titulo: str, idioma: str = "en", temporada: bool = False) -> dict:
    elementos = [
        {"id": "marca", "tipo": "campo", "campo": "producto.marca", "x": 4, "y": 4, "w": 43, "h": 7,
         "estilo": {**_TEXTO, "tam": 12, "negrita": True}},
        {"id": "desc", "tipo": "campo", "campo": "articulo.descripcion", "x": 4, "y": 12, "w": 43, "h": 9,
         "estilo": {**_TEXTO, "tam": 8, "multilinea": True}},
        {"id": "talla", "tipo": "campo", "campo": "articulo.atributo.TALLA", "prefijo": "Size " if idioma == "en" else "Talla ",
         "x": 4, "y": 22, "w": 21, "h": 6, "estilo": {**_TEXTO, "negrita": True}},
        {"id": "color", "tipo": "campo", "campo": "articulo.atributo.COLOR", "x": 26, "y": 22, "w": 21, "h": 6, "estilo": _TEXTO},
        {"id": "oc", "tipo": "campo", "campo": "oc.numero", "prefijo": "PO ", "x": 4, "y": 29, "w": 43, "h": 5,
         "si_vacio": "ocultar", "estilo": {**_TEXTO, "tam": 7}},
        {"id": "codigo", "tipo": "codigo", "simbologia": "code128", "valor": "{{articulo.sku}}", "x": 4, "y": 36, "w": 43,
         "h": 30, "legible": True},
        {"id": "titulo", "tipo": "texto", "contenido": titulo, "x": 4, "y": 67, "w": 43, "h": 5,
         "estilo": {**_TEXTO, "tam": 6}},
    ]
    variables = []
    if temporada:
        elementos.append({"id": "temporada", "tipo": "campo", "campo": "manual.temporada", "x": 30, "y": 29, "w": 17, "h": 5,
                          "estilo": {**_TEXTO, "tam": 7, "alin": "der"}})
        variables.append({"clave": "temporada", "etiqueta": "Season", "obligatorio": True})
    return {"ancho": 50.8, "alto": 76.2, "idioma": idioma, "elementos": elementos, "variables": variables}


def _precio() -> dict:
    return {"ancho": 38.1, "alto": 25.4, "elementos": [
        {"id": "sku", "tipo": "campo", "campo": "articulo.sku", "x": 2, "y": 2, "w": 34, "h": 5, "estilo": {**_TEXTO, "tam": 7}},
        {"id": "codigo", "tipo": "codigo", "simbologia": "code128", "valor": "{{articulo.sku}}", "x": 2, "y": 8, "w": 34,
         "h": 14, "legible": True}]}


def _caja(titulo: str) -> dict:
    return {"ancho": 101.6, "alto": 152.4, "elementos": [
        {"id": "titulo", "tipo": "texto", "contenido": titulo, "x": 5, "y": 5, "w": 92, "h": 8,
         "estilo": {**_TEXTO, "tam": 14, "negrita": True}},
        {"id": "pl", "tipo": "campo", "campo": "bulto.packing_list", "prefijo": "PL ", "x": 5, "y": 15, "w": 45, "h": 7,
         "estilo": _TEXTO},
        {"id": "numero", "tipo": "texto", "contenido": "{{bulto.numero}} / {{bulto.total}}", "x": 52, "y": 15, "w": 45, "h": 7,
         "estilo": {**_TEXTO, "tam": 12, "negrita": True, "alin": "der"}},
        {"id": "oc", "tipo": "campo", "campo": "oc.numero", "prefijo": "PO ", "x": 5, "y": 23, "w": 92, "h": 7,
         "si_vacio": "ocultar", "estilo": _TEXTO},
        {"id": "contenido", "tipo": "tabla", "coleccion": "bulto.lineas", "x": 5, "y": 32, "w": 92, "h": 70, "alto_fila": 6,
         "desborde": "resumir", "estilo": {**_TEXTO, "tam": 7},
         "columnas": [{"campo": "sku", "titulo": "SKU", "ancho": 3}, {"campo": "atributo.TALLA", "titulo": "Size", "ancho": 1},
                      {"campo": "cantidad", "titulo": "Qty", "ancho": 1, "alin": "der"}], "totales": ["cantidad"]},
        {"id": "codigo", "tipo": "codigo", "simbologia": "code128",
         "valor": "{{bulto.packing_list}}-{{bulto.numero}}", "x": 5, "y": 108, "w": 92, "h": 38, "legible": True}]}


def _contenido() -> dict:
    return {"ancho": 210, "alto": 297, "elementos": [
        {"id": "titulo", "tipo": "campo", "campo": "oc.numero", "prefijo": "PO ", "x": 15, "y": 15, "w": 180, "h": 12,
         "estilo": {**_TEXTO, "tam": 18, "negrita": True}},
        {"id": "proveedor", "tipo": "campo", "campo": "oc.proveedor", "x": 15, "y": 28, "w": 180, "h": 8, "estilo": _TEXTO},
        {"id": "lineas", "tipo": "tabla", "coleccion": "oc.lineas", "x": 15, "y": 40, "w": 180, "h": 230, "alto_fila": 7,
         "desborde": "resumir", "estilo": {**_TEXTO, "tam": 8},
         "columnas": [{"campo": "linea", "titulo": "Line", "ancho": 1}, {"campo": "sku", "titulo": "SKU", "ancho": 3},
                      {"campo": "descripcion", "titulo": "Description", "ancho": 5},
                      {"campo": "cantidad", "titulo": "Qty", "ancho": 1, "alin": "der"}], "totales": ["cantidad"]}]}


def sembrar(db: Session) -> None:
    from app.modulos.etiquetado import plantillas, tipos, trabajos, usos

    interno = db.scalar(select(Usuario).where(Usuario.email == "interno@demo.com"))
    admin = db.scalar(select(Usuario).where(Usuario.email == "admin@demo.com"))
    trabajos._contexto(db, admin)

    # ---- Tipos de etiqueta ------------------------------------------------------------------
    t = {x["codigo"]: x for x in tipos.crear_sugeridos(db, admin, [s["codigo"] for s in tipos.SUGERIDOS])}

    # ---- Familias del producto (ya creadas con sus atributos y sus productos: demo._familias) ----
    calzado, ropa = _familia(db, "FOOTWEAR"), _familia(db, "APPAREL")
    mochila = db.get(Producto, _productos(db, "NF0A3VY2")[0])

    # ---- Diseños aprobados -----------------------------------------------------------------
    def diseno(nombre: str, tipo: str, contenido: dict, descripcion: str) -> dict:
        p = plantillas.crear(db, interno, {"nombre": nombre, "tipo_etiqueta_id": t[tipo]["id"], "descripcion": descripcion,
                                           "diseno": contenido})
        v = p["versiones"][0]["id"]
        plantillas.enviar(db, interno, v)
        plantillas.aprobar(db, admin, v, "Checked with a printed sample.")
        return p

    colgante_calzado = diseno("Hang tag footwear 2×3 in", "COLGANTE", _colgante("Footwear", temporada=True),
                              "Size, color and SKU barcode; the season is written when generating.")
    colgante_ropa = diseno("Hang tag apparel 2×3 in", "COLGANTE", _colgante("Apparel"), "Size, color and SKU barcode.")
    colgante_es = diseno("Hang tag bilingual 2×3 in", "COLGANTE", _colgante("Calzado · Footwear", idioma="es", temporada=True),
                         "Spanish texts and dates, required by customs in Panama.")
    precio = diseno("Price sticker 1.5×1 in", "PRECIO", _precio(), "SKU and barcode for the store price label.")
    caja = diseno("Carton label 4×6 in", "CAJA", _caja("CARTON"), "Packing list, carton n of N, contents and barcode.")
    caja_especial = diseno("Carton label special order 4×6 in", "CAJA", _caja("SPECIAL ORDER"),
                           "Same carton label with a banner for orders that ask for it.")
    contenido = diseno("PO content sheet A4", "CONTENIDO", _contenido(), "List of the PO lines, to put inside the first carton.")
    # Una versión nueva esperando aprobación (la vigente sigue siendo la 1)
    nueva = plantillas.nueva_version(db, interno, colgante_ropa["id"])
    cambiado = _colgante("Apparel · new layout")
    plantillas.guardar_diseno(db, interno, nueva["id"], plantillas.svc_diseno.validar(cambiado), nueva["version"])
    plantillas.enviar(db, interno, nueva["id"])

    # ---- Qué diseño lleva cada cosa ----------------------------------------------------------
    def uso(tipo: str, plantilla: dict, nivel: str = "GENERAL", destino_id: int | None = None, **extra) -> dict:
        return usos.crear(db, admin, {"tipo_etiqueta_id": t[tipo]["id"], "plantilla_id": plantilla["id"], "nivel": nivel,
                                      "destino_id": destino_id, **extra})

    uso("PRECIO", precio)
    uso("CAJA", caja)
    uso("CONTENIDO", contenido)
    uso("COLGANTE", colgante_calzado, "FAMILIA", calzado["id"])
    uso("COLGANTE", colgante_ropa, "FAMILIA", ropa["id"])
    uso("COLGANTE", colgante_ropa, "PRODUCTO", mochila.id)  # su familia no tiene diseño: lleva uno propio
    uso("COLGANTE", colgante_es, "FAMILIA", calzado["id"], contexto_tipo="PAIS_DESTINO", contexto_valores=["PA"],
        motivo="Customs in Panama ask for Spanish texts on the hang tag.")
    oc_especial = db.scalar(select(OrdenCompra).where(OrdenCompra.estado == "APROBADA").order_by(OrdenCompra.id.desc()))
    if oc_especial is not None:
        uso("CAJA", caja_especial, contexto_tipo="OC", oc_id=oc_especial.id,
            motivo="The buyer asked for a SPECIAL ORDER banner on every carton of this PO.")
    retirado = uso("PRECIO", precio, "FAMILIA", ropa["id"])
    usos.baja(db, admin, retirado["id"], "Apparel uses the general price sticker; the family design is no longer needed.")

    # ---- Trabajos de ejemplo -------------------------------------------------------------------
    trabajos._contexto(db, interno)
    oc = db.scalar(select(OrdenCompra).where(OrdenCompra.estado == "APROBADA").order_by(OrdenCompra.id))
    if oc is not None:
        j = trabajos.crear(db, interno, {"origen": "OC", "nombre": f"{oc.numero} · hang tags and content sheet",
                                         "parametros": {"oc_ids": [oc.id], "tipos": [t["COLGANTE"]["id"], t["CONTENIDO"]["id"]],
                                                        "manuales": {"temporada": "FW26"}}})
        _nota(db, j["id"], "Created from the purchase order with the Labels button.")
        trabajos.validar(db, interno, j["id"])
        actual = trabajos.detalle(db, interno, j["id"])
        if not actual["resumen"].get("problemas") and not any(r["estado"] == "ERROR" for r in actual["registros"]):
            trabajos.generar(db, interno, j["id"], {"aceptar_advertencias": True, "version": actual["version"]})
    sueltos = list(db.scalars(select(Articulo).where(Articulo.activo.is_(True), Articulo.tipo == "SOLIDO")
                              .order_by(Articulo.id).limit(3)))
    if sueltos:
        j = trabajos.crear(db, interno, {"origen": "ARTICULOS", "nombre": "Price stickers for the store window (test)",
                                         "parametros": {"articulos": [{"articulo_id": a.id, "cantidad": 2} for a in sueltos],
                                                        "tipos": [t["PRECIO"]["id"]], "prueba": True}})
        _nota(db, j["id"], "Created from the item list: three items, test labels before printing for real.")
        trabajos.validar(db, interno, j["id"])
        actual = trabajos.detalle(db, interno, j["id"])
        trabajos.generar(db, interno, j["id"], {"aceptar_advertencias": True, "version": actual["version"]})
    pl = db.scalar(select(PackingList).where(PackingList.estado == "FINALIZADO").order_by(PackingList.id))
    if pl is not None:
        j = trabajos.crear(db, interno, {"origen": "PACKING", "nombre": f"{pl.numero} · carton labels",
                                         "parametros": {"pl_id": pl.id, "tipos": [t["CAJA"]["id"]]}})
        _nota(db, j["id"], "Created from the packing list with the Labels button; validated, ready to generate.")
        trabajos.validar(db, interno, j["id"])
    if oc is not None:
        j = trabajos.crear(db, interno, {"origen": "OC", "nombre": "Footwear of the open POs",
                                         "parametros": {"oc_ids": [oc.id], "familia_id": calzado["id"],
                                                        "tipos": [t["COLGANTE"]["id"]]}})
        _nota(db, j["id"], "Created from the labeling module for the Footwear family; still a draft.")
    zapatos = list(db.scalars(select(Articulo).where(Articulo.producto_id.in_(_productos(db, "VN000EE3", "VN0A4BV4")),
                                                     Articulo.tipo == "SOLIDO").order_by(Articulo.id).limit(2)))
    if zapatos:
        j = trabajos.crear(db, interno, {"origen": "ARTICULOS", "nombre": "Footwear hang tags (season missing)",
                                         "parametros": {"articulos": [{"articulo_id": a.id, "cantidad": 6} for a in zapatos],
                                                        "tipos": [t["COLGANTE"]["id"]]}})
        _nota(db, j["id"], "Created from the item list; the design asks for the season, which is still empty: "
                           "fill it in the Review step.")
        trabajos.validar(db, interno, j["id"])
    db.flush()


def _familia(db: Session, codigo: str) -> dict:
    from app.modelos import GrupoFamilia

    return {"id": db.scalar(select(GrupoFamilia.id).where(GrupoFamilia.codigo == codigo))}


def _productos(db: Session, *estilos: str) -> list[int]:
    """Ids de los productos de esos estilos (su atributo de producto MODELO)."""
    return list(db.scalars(select(ProductoAtributo.producto_id).join(Atributo, Atributo.id == ProductoAtributo.atributo_id)
                           .where(Atributo.codigo == "MODELO", ProductoAtributo.valor.in_(estilos))
                           .order_by(ProductoAtributo.producto_id)))


def _nota(db: Session, trabajo_id: int, texto: str) -> None:
    from app.modelos import TrabajoEtiquetas

    t = db.get(TrabajoEtiquetas, trabajo_id)
    t.parametros = {**(t.parametros or {}), "nota": texto}
