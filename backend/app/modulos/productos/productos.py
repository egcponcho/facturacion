"""Productos: ficha técnica y clasificación arancelaria.

Un producto de cualquier rubro: sus variantes (artículos) y sus packs comparten
la ficha técnica, la partida SAC aprobada y el código nacional de cada país
destino; de aquí los toman la OC y la factura.

La clasificación la hace el motor único del servidor (motor_clasificacion):
la ficha, el guardado, la clasificación masiva y la aprobación pasan por él;
aquí se guarda lo que calcula, se valida lo que se aprueba y se lleva el
historial y la evidencia. Aprobar y enseñar códigos es del equipo interno; la
ficha la puede completar el proveedor.
"""
import re

from sqlalchemy import func, select
from sqlalchemy.orm import Session, object_session

from app.core import dinero, listas
from app.core.errores import ErrorNegocio
from app.modelos import (
    Articulo,
    Marca,
    Pais,
    PaisArancel,
    PalabraClave,
    PartidaPais,
    Producto,
    ProductoDocumento,
    Proveedor,
    SinonimoMaterial,
    Usuario,
)
from app.modulos.acceso.permisos import exigir, proveedor_filtro
from app.modulos.comex import servicio as comex
from app.modulos.comex.servicio import (  # noqa: F401
    APROBADOS,
    BORRADORES,
    ESTADOS,
    PENDIENTES,
    digitos,
    fmt_codigo,
    sin_marca,
)
from app.modulos.documentos import aduana
from app.modulos.maestros import variantes as var_svc


# Países destino y dígitos de su código nacional (Centroamérica y Panamá)
# Países destino de fábrica; en la base se pueden agregar otros y cambiar sus dígitos
def destinos(db: Session) -> list[dict]:
    """Países destino activos con su arancel (configuración del país; sin
    países cargados no hay destinos: no se inventan)."""
    filas = db.scalars(select(PaisArancel).where(PaisArancel.activo.is_(True))
                       .order_by(PaisArancel.orden, PaisArancel.iso)).all()
    return [{"iso": x.iso, "nombre": x.nombre, "digitos": x.digitos, "mcca": x.mcca, "impuesto": x.impuesto,
             "base_legal": x.base_legal} for x in filas]


# Borrador (incompleto o completo) → enviado a revisión → aprobado o devuelto (comex/servicio.py).
# Mientras es borrador, lo edita cualquiera con permiso; enviado queda
# cerrado para el proveedor hasta que se apruebe o se devuelva.
TIPOS_FOTO = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
TIPOS_DOC = {"application/pdf": ".pdf", "image/jpeg": ".jpg", "image/png": ".png"}
# Campos que una ficha técnica nunca aporta: el arancel solo sale de fuentes oficiales
NO_ARANCEL = {"hs", "hs6", "hs_code", "codigo", "code", "tariff", "tariff_code", "dai", "sac", "partida", "inciso", "impuesto", "tax",
              "regulacion", "regulation"}


# ---- Producto de cada artículo ------------------------------------------------
def producto_de(a: Articulo | None) -> Producto | None:
    """Producto que da la clasificación a un artículo: el suyo (un pack es del
    producto de sus variantes; un kit es su propio producto)."""
    return a.producto if a is not None else None


def ids_bloquean_facturas(db: Session, prov: frozenset | None = None) -> set[int]:
    """Productos sin clasificación aprobada que dejan una factura en curso sin partida."""
    from app.modulos.facturacion.bloqueos import productos_que_bloquean

    return productos_que_bloquean(db, prov)


# Códigos de artículo y de genérico: el formato lo define cada empresa
# (numérico o alfanumérico, con punto, guion, barra o guion bajo)
RE_CODIGO = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._\-/]{0,39}$")
MSG_CODIGO = "Letters and numbers (also . - _ /), up to 40 characters."


def codigo_valido(valor: str | None) -> bool:
    return bool(RE_CODIGO.match(str(valor or "").strip()))


def generico_de(a) -> str | None:
    """Código del producto de un artículo o de una fila de datos: el que trae; si no,
    el propio código del artículo (un producto sin variantes, como un químico o una
    materia prima)."""
    if a is None:
        return None
    if isinstance(a, dict):
        return str(a.get("generico") or "").strip().upper() or (str(a.get("sku") or "").strip().upper() or None)
    return a.generico or (a.sku or None)


def producto_por_generico(db: Session, gen: str | None) -> Producto | None:
    return db.scalar(select(Producto).where(Producto.codigo_generico == gen)) if gen else None


def asegurar_producto(db: Session, a: Articulo, generico: str | None = None,
                      proveedor_id: int | None = None) -> Producto:
    """Liga el artículo con el producto de su código (genérico; sin código, el del
    propio artículo) y lo crea si no existe. Las variantes y los packs del mismo
    producto comparten la ficha técnica y la clasificación."""
    gen = (generico or "").strip().upper() or (a.producto.codigo_generico if a.producto is not None else None) \
        or (a.sku or "").strip().upper()
    p = a.producto if a.producto is not None and a.producto.codigo_generico == gen else producto_por_generico(db, gen)
    if p is None:
        p = Producto(proveedor_id=proveedor_id, unidad=a.unidad if a.tipo == "SOLIDO" else None,
                     codigo_generico=gen, nombre=a.descripcion or gen)
        db.add(p)
    if proveedor_id and not p.proveedor_id:
        p.proveedor_id = proveedor_id
    if a.tipo == "SOLIDO" and not p.unidad:
        p.unidad = a.unidad
    a.producto = p
    if not p.comex.descripcion_comercial and not (p.comex.ficha or {}).get("comManual"):
        p.comex.descripcion_comercial = descripcion_comercial_simple(p)
    return p


def marca_de(p: Producto | None):
    """La marca del producto (el registro del catálogo de marcas que dice su atributo de marca)."""
    codigo = p.marca_codigo if p is not None else None
    db = object_session(p) if p is not None else None
    return db.scalar(select(Marca).where(Marca.codigo == codigo)) if codigo and db is not None else None


def nombre_producto(p: Producto) -> str:
    """Cómo se nombra el producto en mensajes: su nombre o su código."""
    return p.nombre or p.codigo_generico or str(p.id)


def descripcion_comercial_simple(p: Producto) -> str | None:
    """Descripción comercial de factura y packing list: tipo y marca (p. ej.
    CALZADO VANS), con la plantilla de la categoría (la misma del motor)."""
    from sqlalchemy.orm import object_session

    from app.modulos.productos.descripciones import descripcion_comercial
    from app.modulos.productos.ficha import catalogo

    db = object_session(p)
    if not p.comex.tipo or db is None:
        return None
    cat = catalogo(db)
    c = cat.categorias.get(p.comex.tipo)
    if not c:
        return None
    s = cat.hechos_base(dict(p.comex.ficha or {}), p.comex.tipo, c.dominio)
    cat.normalizar(s)
    marca = marca_de(p)
    return descripcion_comercial(cat, s, c, marca.nombre if marca else None)[:300] or None


def partida_para(p: Producto | None) -> str | None:
    """Código que va en la OC y la factura: la subpartida de 6 dígitos aprobada (comex/servicio.py)."""
    return comex._ficha(p.comex).partida if p is not None else None


# ---- Códigos nacionales en el servidor (base cargada y aprobaciones en lote) ---
def _codigo_fila(codigo) -> str:
    c = digitos(codigo)
    if len(c) > 14:  # nunca se recorta un código
        raise ErrorNegocio(f"{codigo}: a national code has at most 14 digits.", 422, "validacion")
    return c


def _guardar_partidas(p: Producto, partidas: dict | None) -> None:
    previas = {x.pais: x for x in p.partidas}
    for iso in sorted(set(previas) | {k for k in (partidas or {}) if isinstance(k, str) and len(k) == 2}):
        x = (partidas or {}).get(iso)
        if not x or not digitos(x.get("codigo")):
            if iso in previas:
                p.partidas.remove(previas[iso])
            continue
        fila = previas.get(iso) or PartidaPais(pais=iso)
        fila.codigo = _codigo_fila(x.get("codigo"))
        fila.dai = dinero.porcentaje_o_nota(x.get("dai"))[0]
        fila.estado = str(x.get("estado") or "ok")[:12]
        fila.fuente = (x.get("fuente") or None) and str(x.get("fuente"))[:12]
        fila.manual = bool(x.get("manual"))
        if not fila.manual:
            fila.sugerido = fila.codigo  # lo que eligió el motor (para comparar con el final)
        elif x.get("sugerido"):
            fila.sugerido = _codigo_fila(x.get("sugerido"))
        if x.get("motivo"):
            fila.motivo = str(x["motivo"])[:300]
        if iso not in previas:
            p.partidas.append(fila)


# ---- Fichas técnicas (SDS, TDS, COA): evidencia técnica, no fuente arancelaria ----------
def _doc_dict(d: ProductoDocumento) -> dict:
    return {"id": d.id, "tipo": d.tipo, "tipo_txt": listas.nombre("tipo_documento", d.tipo), "nombre": d.nombre, "emisor": d.emisor,
            "fecha_documento": d.fecha_documento, "datos": d.datos or {}, "subido_en": d.subido_en}


# ---- Base de códigos nacionales -------------------------------------------------
def notas_contexto(db: Session) -> list[dict]:
    """Notas activas con la capa custom aplicada (el texto oficial no se edita)."""
    from app.modulos.clasificacion.aranceles import notas_vigentes

    return [{k: n[k] for k in ("id", "ambito", "codigo", "numero", "texto", "capitulos", "claves", "oficial", "tipo_fuente")}
            for n in notas_vigentes(db)]


def notas_de(db: Session, codigo: str | None) -> list:
    """Notas legales que aplican a una subpartida: las reglas generales, las de
    su sección y las de su capítulo."""
    from types import SimpleNamespace

    from app.modulos.clasificacion.aranceles import notas_vigentes

    cap = (codigo or "")[:2]
    return [SimpleNamespace(**n) for n in notas_vigentes(db) if not n["capitulos"] or cap in n["capitulos"]]


# ---- Proveedores y catálogos para la pantalla -------------------------------------
def opciones(db: Session, user: Usuario) -> dict:
    exigir(user, "producto.ver")
    prov = proveedor_filtro(user)
    provs = db.scalars(select(Proveedor).where(Proveedor.activo.is_(True)).order_by(Proveedor.nombre)).all()
    return {
        "proveedores": [{"id": x.id, "nombre": x.nombre} for x in provs if not prov or x.id in prov],
        "marcas": [{"id": m.id, "codigo": m.codigo, "nombre": m.nombre} for m in db.scalars(select(Marca).order_by(Marca.codigo))],
        # Los atributos de producto de la empresa: una columna de la lista por cada uno
        "atributos": [{"codigo": a.codigo, "nombre": a.nombre, "catalogo": a.catalogo} for a in var_svc.atributos(db, "PRODUCTO")],
        "estados": ESTADOS,
        "paises": [{"codigo": x.codigo, "nombre": x.nombre} for x in db.scalars(select(Pais).order_by(Pais.nombre))],
    }


def etiquetas_ficha(db: Session) -> dict:
    """Etiquetas del catálogo para mostrar una ficha en documentos (atributos,
    opciones, partes de la composición, categorías) y el orden de los países:
    los documentos no traen nombres fijos de ninguna familia."""
    from app.modulos.productos.ficha import catalogo

    cat = catalogo(db)
    return {"campos": {a.codigo: a.etiqueta for a in cat.atributos},
            "valores": {a.codigo: {o.codigo: o.etiqueta for o in a.opciones} for a in cat.atributos if a.opciones},
            "partes": {a.codigo[5:]: a.etiqueta for a in cat.atributos if a.codigo.startswith("comp.")},
            "tipos": {c.codigo: c.nombre_corto or c.nombre for c in cat.categorias.values()},
            "paises": [p.iso for p in db.scalars(select(PaisArancel).order_by(PaisArancel.orden, PaisArancel.iso))],
            "aduana": aduana.nombres(db)}


# ---- Lo que aprende el clasificador ----------------------------------------------
def ensenar_inciso(db: Session, user: Usuario, datos) -> dict:
    """Recordar una línea nacional para productos parecidos: conocimiento de la
    empresa (no crea ni modifica líneas oficiales)."""
    from app.modulos.clasificacion import conocimiento

    return conocimiento.ensenar(db, user, datos.pais, datos.codigo, datos.cond, datos.nota)


def ensenar_palabra(db: Session, user: Usuario, datos) -> dict:
    exigir(user, "producto.clasificar")
    frase = (datos.frase or "").strip().lower()[:100]
    if len(frase) < 3 or not datos.tipo:
        raise ErrorNegocio("Enter a phrase of at least 3 characters and its product type.", 422, "validacion")
    x = db.scalar(select(PalabraClave).where(func.lower(PalabraClave.frase) == frase,
                                             PalabraClave.marca.is_(None) if not datos.marca else PalabraClave.marca == datos.marca))
    if not x:
        x = PalabraClave(frase=frase, creado_por=user.id)
        db.add(x)
    x.tipo = datos.tipo[:30]
    x.marca = (datos.marca or None) and datos.marca[:100]
    x.atributos = {k: v for k, v in (datos.atributos or {}).items() if v not in (None, "")}
    db.flush()
    return {"id": x.id}


def ensenar_sinonimo(db: Session, user: Usuario, datos) -> dict:
    exigir(user, "producto.ficha")
    palabra = (datos.palabra or "").strip().lower()[:60]
    if len(palabra) < 3 or not datos.equivale:
        raise ErrorNegocio("Enter the word and what it means.", 422, "validacion")
    x = db.scalar(select(SinonimoMaterial).where(SinonimoMaterial.palabra == palabra))
    if not x:
        x = SinonimoMaterial(palabra=palabra, creado_por=user.id)
        db.add(x)
    x.equivale = datos.equivale[:30]
    db.flush()
    return {"id": x.id}
