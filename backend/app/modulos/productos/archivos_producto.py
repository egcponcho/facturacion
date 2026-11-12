"""Fotos y fichas técnicas (SDS, TDS, COA) de un producto: subir, borrar y descargar.
"""
import os

from sqlalchemy.orm import Session

from app.core import listas
from app.core.archivos import MIME, TIPOS, exigir_tamano, tipo_imagen
from app.core.errores import ErrorNegocio
from app.modelos import (
    ProductoDocumento,
    ProductoFoto,
    Usuario,
)
from app.modulos.acceso.permisos import exigir
from app.modulos.comex.servicio import (  # noqa: F401
    APROBADOS,
    BORRADORES,
    ESTADOS,
    PENDIENTES,
    digitos,
    fmt_codigo,
    sin_marca,
)
from app.modulos.comun import adjuntos
from app.modulos.comun.historial import registrar
from app.modulos.productos.consulta import ver_producto
from app.modulos.productos.productos import NO_ARANCEL, TIPOS_DOC, TIPOS_FOTO, _doc_dict


# ---- Fotos ---------------------------------------------------------------------
def subir_foto(db: Session, user: Usuario, producto_id: int, nombre: str, tipo: str, contenido: bytes) -> dict:
    exigir(user, "producto.ficha")
    p = ver_producto(db, user, producto_id)
    exigir_tamano(contenido)
    # El tipo sale del contenido, no de lo que declara el navegador
    tipo = MIME.get(tipo_imagen(contenido) or "")
    if tipo not in TIPOS_FOTO:
        raise ErrorNegocio("Upload a JPG, PNG or WebP image.", 422, "validacion")
    if len(p.fotos) >= 8:
        raise ErrorNegocio("A product can have up to 8 photos.", 422, "validacion")
    seguro = adjuntos.nombre_seguro(nombre, "photo")
    adj = adjuntos.crear(db, user, seguro, contenido, os.path.join("productos", str(p.id)), TIPOS_FOTO[tipo], tipo)
    f = ProductoFoto(adjunto=adj)
    p.fotos.append(f)
    db.flush()
    registrar(db, user, "producto", p.id, "foto_agregada", {"foto": seguro})
    return {"id": f.id, "nombre": f.nombre}


def borrar_foto(db: Session, user: Usuario, producto_id: int, foto_id: int) -> None:
    exigir(user, "producto.ficha")
    p = ver_producto(db, user, producto_id)
    f = next((x for x in p.fotos if x.id == foto_id), None)
    if not f:
        raise ErrorNegocio("The photo does not exist.", 404, "no_encontrado")
    nombre = f.nombre
    p.fotos.remove(f)
    adjuntos.quitar(db, f)
    registrar(db, user, "producto", p.id, "foto_quitada", {"foto": nombre})


def obtener_foto(db: Session, user: Usuario, foto_id: int) -> ProductoFoto:
    f = db.get(ProductoFoto, foto_id)
    if not f:
        raise ErrorNegocio("The photo does not exist.", 404, "no_encontrado")
    ver_producto(db, user, f.producto_id)
    return f




def subir_documento(db: Session, user: Usuario, producto_id: int, tipo: str, nombre: str, mime: str, contenido: bytes,
                    datos: dict | None = None, emisor: str | None = None, fecha=None) -> dict:
    """Adjunta una SDS, TDS o COA. Sus datos técnicos (CAS, composición, estado
    físico, densidad, pH…) completan los hechos de la ficha que estén vacíos;
    nunca aportan un código, DAI, impuesto ni regulación."""
    from app.modulos.productos.ficha import catalogo

    exigir(user, "producto.ficha")
    p = ver_producto(db, user, producto_id)
    tipo = (tipo or "").upper()
    if tipo not in listas.codigos("tipo_documento"):
        raise ErrorNegocio(f"Choose the kind of document: {', '.join(listas.codigos('tipo_documento'))}.", 422, "validacion")
    exigir_tamano(contenido)
    mime = MIME.get("pdf" if TIPOS["pdf"][1](contenido) else tipo_imagen(contenido) or "")
    if mime not in TIPOS_DOC:
        raise ErrorNegocio("Upload a PDF or an image of the document.", 422, "validacion")
    datos = {str(k).strip(): v for k, v in (datos or {}).items() if v not in (None, "", [])}
    arancel = sorted(k for k in datos if k.lower() in NO_ARANCEL)
    if arancel:
        raise ErrorNegocio(f"{tipo} documents are technical evidence, not a tariff source: {', '.join(arancel)} cannot be taken from them.",
                           422, "no_es_fuente_arancelaria")
    cat = catalogo(db)
    datos = {cat.canonico(k): v for k, v in datos.items()}  # un alias (CAS de otro paquete…) llega a su atributo
    desconocidos = sorted(k for k in datos if k not in cat.por_codigo)
    if desconocidos:
        raise ErrorNegocio(f"These are not attributes of the technical sheet: {', '.join(desconocidos)}.", 422, "validacion")
    seguro = adjuntos.nombre_seguro(nombre, "document")
    adj = adjuntos.crear(db, user, seguro, contenido, os.path.join("productos", str(p.id), "documentos"), TIPOS_DOC[mime], mime)
    d = ProductoDocumento(tipo=tipo, adjunto=adj, datos=datos, emisor=(emisor or "").strip()[:200] or None,
                          fecha_documento=fecha)
    p.documentos.append(d)
    db.flush()
    registrar(db, user, "producto", p.id, "documento_agregado", {"tipo": tipo, "documento": seguro, "datos": sorted(datos)})
    return _doc_dict(d)


def borrar_documento(db: Session, user: Usuario, producto_id: int, doc_id: int) -> None:
    exigir(user, "producto.ficha")
    p = ver_producto(db, user, producto_id)
    d = next((x for x in p.documentos if x.id == doc_id), None)
    if not d:
        raise ErrorNegocio("The document does not exist.", 404, "no_encontrado")
    tipo, nombre = d.tipo, d.nombre
    p.documentos.remove(d)
    adjuntos.quitar(db, d)
    registrar(db, user, "producto", p.id, "documento_quitado", {"tipo": tipo, "documento": nombre})


def obtener_documento(db: Session, user: Usuario, doc_id: int) -> ProductoDocumento:
    d = db.get(ProductoDocumento, doc_id)
    if not d:
        raise ErrorNegocio("The document does not exist.", 404, "no_encontrado")
    ver_producto(db, user, d.producto_id)
    return d


