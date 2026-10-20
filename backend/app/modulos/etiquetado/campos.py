"""Campos dinámicos de las etiquetas: qué datos reales se pueden poner en una
etiqueta, de dónde sale cada uno y cómo se obtiene su valor.

Cada campo dice su origen (tabla.columna) y para qué se etiqueta existe
(artículo, bulto o documento). Un artículo siempre tiene sus datos; los de la
OC y su línea están si el artículo viene de una OC (si no, quedan vacíos). Un
bulto tiene sus datos y los de su contenido (los del artículo solo si lleva
uno solo). Un documento tiene los de la OC o de la lista de empaque. Además de los campos fijos se agregan los
atributos de variante de la empresa y sus campos propios (artículos y OC).
Ningún valor se copia a otra tabla: se leen en el momento de generar y solo
la instantánea de lo usado queda en el historial.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core import campos_propios
from app.modelos import (
    Articulo,
    AtributoVariante,
    Centro,
    FacturaLinea,
    GrupoCajas,
    OrdenCompra,
    PackingList,
    PLLinea,
    PosicionOC,
    Sociedad,
    Usuario,
)
from app.modulos.etiquetado.datos_campos import EJEMPLO, ORIGEN

GRUPOS = {
    "oc": "Purchase order",
    "linea": "Purchase order line",
    "articulo": "Item",
    "producto": "Product (style)",
    "bulto": "Package",
    "pl": "Packing list",
    "organizacion": "Organization",
    "etiqueta": "Label",
    "contexto": "Labeling job",
    "logico": "Logical fields",
}
# Grupos de datos de cada sujeto (lo que se etiqueta)
POR_SUJETO = {
    "ARTICULO": {"oc", "linea", "articulo", "producto", "organizacion", "etiqueta", "contexto", "logico"},
    "BULTO": {"bulto", "pl", "oc", "linea", "articulo", "producto", "organizacion", "etiqueta", "contexto", "logico"},
    "DOCUMENTO": {"oc", "pl", "organizacion", "etiqueta", "contexto", "logico"},
}


@dataclass(frozen=True)
class Coleccion:
    """Una lista de filas para las tablas de las etiquetas (contenido de un
    bulto, componentes de un kit…): cada fila tiene las mismas columnas."""
    clave: str
    etiqueta: str
    columnas: tuple  # ((clave, etiqueta, tipo), ...)

    @property
    def grupo(self) -> str:
        return self.clave.split(".", 1)[0]


_COL_LINEA = (("oc", "PO", "texto"), ("linea", "Line", "texto"), ("sku", "SKU", "texto"), ("upc", "UPC", "texto"),
              ("descripcion", "Description", "texto"), ("color", "Color", "texto"), ("talla", "Size", "texto"))
# Misma clave «cantidad» (los diseños guardados la usan), pero no el mismo dato:
# en la OC es lo pedido (plan); en el bulto, lo empacado en esa unidad (real)
_COL_LINEA_OC = (*_COL_LINEA, ("cantidad", "Quantity ordered", "numero"), ("unidad", "Unit", "texto"))
_COL_LINEA_BULTO = (*_COL_LINEA, ("cantidad", "Quantity packed in the package", "numero"), ("unidad", "Unit", "texto"))
_COL_COMPONENTE = (("sku", "SKU", "texto"), ("upc", "UPC", "texto"), ("descripcion", "Description", "texto"),
                   ("color", "Color", "texto"), ("talla", "Size", "texto"), ("cantidad", "Quantity", "numero"))
COLECCIONES = [
    Coleccion("bulto.lineas", "Package contents (lines)", _COL_LINEA_BULTO),
    Coleccion("bulto.componentes", "Package contents by component (prepacks and kits exploded)", _COL_COMPONENTE),
    Coleccion("articulo.componentes", "Components of the prepack or kit (per pack)", _COL_COMPONENTE),
    Coleccion("oc.lineas", "Purchase order lines (ordered quantities)", _COL_LINEA_OC),
    Coleccion("pl.lineas", "Packing list lines (packed quantities)", _COL_LINEA_BULTO),
]
MAX_FILAS = 500  # filas por colección en una etiqueta (más es un dato equivocado, no una etiqueta)


def _columnas_atributos(db: Session | None) -> tuple:
    """Columnas de los atributos de variante propios de la empresa (material, voltaje…)."""
    if db is None:
        return ()
    return tuple((f"atributo.{a.codigo}", a.nombre, "texto") for a in db.scalars(
        select(AtributoVariante).where(AtributoVariante.activo.is_(True), AtributoVariante.columna.is_(None))
        .order_by(AtributoVariante.orden, AtributoVariante.codigo)))


def colecciones(sujeto: str | None = None, db: Session | None = None) -> list[Coleccion]:
    """Las listas para las tablas, con una columna por atributo de variante de la empresa."""
    grupos = POR_SUJETO.get(sujeto) if sujeto else None
    extra = _columnas_atributos(db)
    return [Coleccion(c.clave, c.etiqueta, c.columnas + extra) if extra else c
            for c in COLECCIONES if grupos is None or c.grupo in grupos]


def dict_coleccion(c: Coleccion) -> dict:
    return {"clave": c.clave, "etiqueta": c.etiqueta, "grupo": c.grupo,
            "columnas": [{"clave": k, "etiqueta": e, "tipo": t} for k, e, t in c.columnas]}


@dataclass(frozen=True)
class Campo:
    clave: str
    etiqueta: str
    tipo: str = "texto"  # texto | numero | fecha | imagen
    dato: str | None = None  # grupo de datos reservados (acceso/visibilidad.py), p. ej. precios
    origen_propio: str | None = None  # de los campos dinámicos (atributos y campos propios)

    @property
    def origen(self) -> str:
        """tabla.columna (o cómo se calcula): de dónde sale el valor."""
        return self.origen_propio or ORIGEN.get(self.clave, "")

    @property
    def ejemplo(self):
        return EJEMPLO.get(self.clave, "—" if self.origen_propio else None)

    @property
    def grupo(self) -> str:
        return self.clave.split(".", 1)[0]


_FIJOS = [
    Campo("oc.numero", "PO number"),
    Campo("oc.fecha", "PO date", "fecha"),
    Campo("oc.proveedor_codigo", "Supplier code"),
    Campo("oc.proveedor", "Supplier"),
    Campo("oc.proveedor_razon_social", "Supplier legal name"),
    Campo("oc.sociedad", "Company code", dato="codigos_internos"),
    Campo("oc.sociedad_nombre", "Company"),
    Campo("oc.centro_destino", "Destination plant code", dato="codigos_internos"),
    Campo("oc.centro_destino_nombre", "Destination plant"),
    Campo("oc.centro", "Plant code", dato="codigos_internos"),
    Campo("oc.puerto_despacho", "Port of loading"),
    Campo("oc.pais_origen", "Country of origin (PO)"),
    Campo("oc.incoterm", "Incoterm"),
    Campo("oc.fecha_xf", "Ship date (XF)", "fecha"),
    Campo("oc.fecha_tienda", "In-store date", "fecha", dato="fechas_internas"),
    Campo("oc.condicion_pago", "Payment terms"),
    Campo("linea.posicion", "Line number"),
    Campo("linea.cantidad", "Quantity ordered", "numero"),
    Campo("linea.unidad", "Unit of measure (line)"),
    Campo("linea.precio", "Unit price", "numero", dato="precios"),
    Campo("linea.fecha_entrega", "Delivery date (line)", "fecha"),
    Campo("linea.almacen", "Warehouse (line)", dato="codigos_internos"),
    Campo("linea.casepack", "Units per case (casepack)", "numero"),
    Campo("linea.inner_pack", "Inner pack", "numero"),
    Campo("linea.prepack", "Prepack (line)"),
    Campo("linea.codigo_articulo", "Item code (as on the PO)"),
    Campo("linea.upc", "UPC (as on the PO)"),
    Campo("linea.pais_origen", "Country of origin (line)"),
    Campo("articulo.sku", "SKU"),
    Campo("articulo.sku_proveedor", "Supplier item code"),
    Campo("articulo.upc", "UPC / EAN"),
    Campo("articulo.generico", "Generic code"),
    Campo("articulo.estilo", "Style"),
    Campo("articulo.color", "Color"),
    Campo("articulo.talla", "Size"),
    Campo("articulo.descripcion", "Item description"),
    Campo("articulo.unidad", "Unit of measure"),
    Campo("articulo.tipo", "Item type (solid / prepack)"),
    Campo("articulo.peso_unitario", "Unit weight (kg)", "numero"),
    Campo("articulo.marca_codigo", "Brand code"),
    Campo("articulo.marca", "Brand"),
    Campo("articulo.grupo_codigo", "Item group code"),
    Campo("articulo.grupo", "Item group"),
    Campo("articulo.prepack", "Prepack"),
    Campo("articulo.familia_codigo", "Labeling family code"),
    Campo("articulo.familia", "Labeling family"),
    Campo("articulo.familia_ruta", "Labeling family path (codes)"),
    Campo("producto.nombre", "Product name"),
    Campo("producto.descripcion_comercial", "Commercial description"),
    Campo("producto.codigo_generico", "Product generic code"),
    Campo("producto.pais_origen", "Country of origin (product)"),
    Campo("producto.composicion", "Composition"),
    Campo("producto.uso", "Intended use"),
    Campo("bulto.numero", "Package number", "numero"),
    Campo("bulto.total", "Packages in the packing list", "numero"),
    Campo("bulto.packing_list", "Packing list"),
    Campo("bulto.factura", "Invoice number"),
    Campo("bulto.embarque", "Shipment"),
    Campo("bulto.peso_bruto", "Gross weight per package (kg)", "numero"),
    Campo("bulto.peso_neto", "Net weight per package (kg)", "numero"),
    Campo("bulto.medidas", "Package dimensions (cm)"),
    Campo("bulto.unidades", "Units in the package", "numero"),
    Campo("bulto.contenido", "Package contents"),
    Campo("bulto.tipo", "Package type"),
    Campo("bulto.tipo_codigo", "Package type code"),
    Campo("bulto.parcial", "Partial package (yes/no)", "si_no"),
    Campo("bulto.mixto", "The package holds more than one item (yes/no)", "si_no"),
    Campo("bulto.codigo", "Package code"),
    Campo("bulto.contenedor", "Contained in"),
    Campo("pl.numero", "Packing list number"),
    Campo("pl.factura", "Invoice number (packing list)"),
    Campo("pl.embarque", "Shipment (packing list)"),
    Campo("pl.bultos", "Packages in the packing list", "numero"),
    Campo("organizacion.nombre", "Organization name"),
    Campo("organizacion.razon_social", "Organization legal name"),
    Campo("organizacion.id_fiscal", "Organization tax ID"),
    Campo("organizacion.pais", "Organization country"),
    Campo("organizacion.logo", "Organization logo", "imagen"),
    Campo("etiqueta.numero", "Label number (n)", "numero"),
    Campo("etiqueta.total", "Labels in the group (of N)", "numero"),
    Campo("etiqueta.numero_lote", "Label number in the batch", "numero"),
    Campo("etiqueta.total_lote", "Labels in the batch", "numero"),
    Campo("etiqueta.fecha", "Generation date", "fecha"),
    Campo("etiqueta.serie", "Controlled label ID (numbering series)"),
    Campo("contexto.origen", "Job origin (OC, ARTICULOS, PACKING)"),
    Campo("contexto.tipo_etiqueta", "Label type"),
]


def _dinamicos(db: Session) -> list[Campo]:
    """Atributos de variante propios de la empresa y campos propios de artículos y OC."""
    res = [Campo(f"articulo.atributo.{a.codigo}", a.nombre, origen_propio=f"articulo_atributos.valor[{a.codigo}]")
           for a in db.scalars(select(AtributoVariante).where(AtributoVariante.activo.is_(True), AtributoVariante.columna.is_(None))
                               .order_by(AtributoVariante.orden, AtributoVariante.codigo))]
    for entidad, grupo in (("articulos", "articulo"), ("ordenes", "oc")):
        for d in campos_propios.definiciones(entidad):
            tipo = {"numero": "numero", "fecha": "fecha"}.get(d.get("tipo"), "texto")
            res.append(Campo(f"{grupo}.extra.{d['clave']}", d.get("etiqueta") or d["clave"], tipo,
                             origen_propio=f"{entidad}.extra[{d['clave']}]"))
    from app.modulos.etiquetado import campos_logicos

    for c in campos_logicos.activos(db):
        res.append(Campo(f"logico.{c.clave}", c.etiqueta, c.tipo,
                         origen_propio=f"campos_etiqueta[{c.clave}]: {' → '.join(c.fuentes or [])}"))
    return res


def catalogo(db: Session, sujeto: str | None = None) -> list[Campo]:
    """Campos disponibles (para lo que se etiqueta) sin los datos reservados que el usuario no ve."""
    from app.modulos.acceso import visibilidad
    from app.modulos.etiquetado import campos_logicos

    grupos = POR_SUJETO.get(sujeto) if sujeto else None
    fuera = campos_logicos.fuera_de(db, sujeto) if sujeto else set()
    return [c for c in _FIJOS + _dinamicos(db)
            if (grupos is None or c.grupo in grupos) and not (c.dato and visibilidad.oculto(c.dato)) and c.clave not in fuera]


def tipos(db: Session, sujeto: str | None = None) -> dict[str, str]:
    """Tipo de cada campo (y de cada columna de las colecciones, como «bulto.lineas.cantidad») para formatear."""
    clave = f"tipos_campos:{sujeto}"
    if clave in db.info:
        return db.info[clave]
    res = {c.clave: c.tipo for c in catalogo(db, sujeto)}
    db.info[clave] = res
    for col in colecciones(sujeto, db):
        res.update({f"{col.clave}.{k}": t for k, _, t in col.columnas})
    return res


def por_clave(db: Session) -> dict[str, Campo]:
    return {c.clave: c for c in catalogo(db)}


def personalizados() -> dict[str, dict]:
    """Nombre propio y si se oculta, por campo, de la empresa (Configuración → Etiquetado → Campos)."""
    from app.core.empresa import configuracion_actual

    return (configuracion_actual().get("etiquetado") or {}).get("campos") or {}


def dict_campo(c: Campo, propios: dict | None = None) -> dict:
    """El campo con el nombre que le da la empresa (el original queda en etiqueta_original) y si está oculto
    (no se ofrece al diseñar; los diseños que ya lo usan lo siguen imprimiendo)."""
    p = (propios or {}).get(c.clave) or {}
    return {"clave": c.clave, "etiqueta": p.get("nombre") or c.etiqueta, "etiqueta_original": c.etiqueta, "propio": bool(p.get("nombre")),
            "oculto": bool(p.get("oculto")), "grupo": c.grupo, "origen": c.origen, "tipo": c.tipo, "ejemplo": c.ejemplo}


MAX_NOMBRE_CAMPO = 60


def guardar_personalizados(db: Session, user, cambios) -> dict[str, dict]:
    """Reemplaza los nombres propios y los campos ocultos de la empresa ({clave: {nombre, oculto}})."""
    from app.core.errores import ErrorNegocio
    from app.modulos.acceso.permisos import exigir
    from app.modulos.comun.historial import registrar
    from app.modulos.empresa.organizacion import actual

    exigir(user, "etiquetas.configurar")
    if not isinstance(cambios, dict) or len(cambios) > 1000:
        raise ErrorNegocio("Check the field names.", 422, "validacion")
    claves = {c.clave for c in catalogo(db)}
    limpio = {}
    for clave, v in cambios.items():
        if clave not in claves:
            raise ErrorNegocio("A field does not exist.", 422, "validacion", [{"campo": "campos", "mensaje": str(clave)[:80]}])
        if not isinstance(v, dict):
            raise ErrorNegocio("Check the field names.", 422, "validacion", [{"campo": clave, "mensaje": ""}])
        nombre = str(v.get("nombre") or "").strip()
        if len(nombre) > MAX_NOMBRE_CAMPO:
            raise ErrorNegocio(f"A field name has up to {MAX_NOMBRE_CAMPO} characters.", 422, "validacion",
                               [{"campo": clave, "mensaje": nombre[:80]}])
        if nombre or v.get("oculto"):
            limpio[clave] = {**({"nombre": nombre} if nombre else {}), **({"oculto": True} if v.get("oculto") else {})}
    o = actual(db)
    conf = dict(o.configuracion or {})
    conf["etiquetado"] = {**(conf.get("etiquetado") or {}), "campos": limpio}
    o.configuracion = conf
    db.flush()
    registrar(db, user, "plantilla_etiqueta", 0, "campos", {"propios": sum(1 for x in limpio.values() if x.get("nombre")),
                                                             "ocultos": sum(1 for x in limpio.values() if x.get("oculto"))})
    return limpio


def ejemplos(db: Session, sujeto: str | None = None, user: Usuario | None = None) -> dict:
    """Valores para diseñar sin elegir un registro: los de un artículo real (el
    último con OC) sobre ejemplos neutros, así la vista previa se parece a lo que
    se va a imprimir. Los reales son solo de los proveedores que el usuario ve;
    sin usuario, solo los neutros."""
    from app.modulos.acceso.permisos import proveedor_filtro

    res = {c.clave: c.ejemplo for c in catalogo(db, sujeto) if c.ejemplo is not None}
    res.update({c.clave: EJEMPLO[c.clave] for c in colecciones(sujeto) if c.clave in EJEMPLO})
    if user is not None and sujeto in (None, "ARTICULO", "BULTO"):
        c = select(PosicionOC).join(OrdenCompra, OrdenCompra.id == PosicionOC.oc_id).where(PosicionOC.articulo_id.is_not(None))
        prov = proveedor_filtro(user)
        if prov is not None:
            c = c.where(OrdenCompra.proveedor_id.in_(prov))
        p = db.scalar(c.order_by(PosicionOC.id.desc()).limit(1))
        if p is not None:
            reales = {**valores_articulo(p.articulo), **valores_linea(p)}
            reales.update({k: v for k, v in valores_oc(db, p.oc).items() if k != "oc.lineas"})
            res.update({k: v for k, v in reales.items() if v not in (None, "", [])})
    return res


# ---- Valores reales ---------------------------------------------------------------------
def _txt(v):
    if v is None:
        return None
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    return v


def _composicion(ficha: dict | None) -> str | None:
    comp = (ficha or {}).get("comp")
    if isinstance(comp, dict):
        partes = [f"{k.replace('_', ' ').capitalize()}: {v}" for k, v in comp.items() if v]
        return "; ".join(partes) or None
    return str(comp) if comp else None


def valores_organizacion(db: Session) -> dict:
    from app.modulos.empresa.organizacion import actual

    o = actual(db)
    return {"organizacion.nombre": o.nombre, "organizacion.razon_social": o.razon_social,
            "organizacion.id_fiscal": o.id_fiscal, "organizacion.pais": o.pais, "organizacion.logo": o.logo}


def valores_articulo(a: Articulo) -> dict:
    p = a.producto
    v = {
        "articulo.sku": a.sku, "articulo.sku_proveedor": a.sku_proveedor, "articulo.upc": a.upc,
        "articulo.generico": a.generico, "articulo.estilo": a.estilo, "articulo.color": a.color, "articulo.talla": a.talla,
        "articulo.descripcion": a.descripcion, "articulo.unidad": a.unidad, "articulo.tipo": a.tipo,
        "articulo.peso_unitario": a.peso_unitario,
        "articulo.marca_codigo": a.marca.codigo if a.marca else None, "articulo.marca": a.marca.nombre if a.marca else None,
        "articulo.grupo_codigo": a.grupo.codigo if a.grupo else None, "articulo.grupo": a.grupo.nombre if a.grupo else None,
        "articulo.prepack": a.prepack.codigo if a.prepack else None,
        "articulo.familia_codigo": a.familia_efectiva.codigo if a.familia_efectiva else None,
        "articulo.familia": a.familia_efectiva.nombre if a.familia_efectiva else None,
        "articulo.familia_ruta": " / ".join(f.codigo for f in a.familia_efectiva.ruta()) if a.familia_efectiva else None,
        "articulo.componentes": componentes_articulo(a),
        "producto.nombre": p.nombre if p else None, "producto.descripcion_comercial": p.descripcion_comercial if p else None,
        "producto.codigo_generico": p.codigo_generico if p else None, "producto.pais_origen": p.pais_origen if p else None,
        "producto.composicion": _composicion(p.ficha) if p else None, "producto.uso": (p.ficha or {}).get("uso") if p else None,
    }
    for x in a.atributos:
        v[f"articulo.atributo.{x.atributo.codigo}"] = x.valor
    for k, val in (a.extra or {}).items():
        v[f"articulo.extra.{k}"] = _txt(val)
    return v


def _fila_articulo(a: Articulo, cantidad) -> dict:
    return {"sku": a.sku, "upc": a.upc, "descripcion": a.descripcion, "color": a.color, "talla": a.talla, "cantidad": cantidad,
            **{f"atributo.{x.atributo.codigo}": x.valor for x in a.atributos}}


def componentes_articulo(a: Articulo) -> list[dict]:
    """Los componentes de un prepack o kit con su cantidad por paquete (vacío en un sólido)."""
    if not a.prepack:
        return []
    return [_fila_articulo(c.articulo, c.cantidad) for c in a.prepack.componentes]


def valores_oc(db: Session, oc: OrdenCompra) -> dict:
    soc = db.scalar(select(Sociedad).where(Sociedad.codigo == oc.sociedad)) if oc.sociedad else None
    destino = db.scalar(select(Centro).where(Centro.codigo == oc.centro_destino)) if oc.centro_destino else None
    v = {
        "oc.numero": oc.numero, "oc.fecha": _txt(oc.fecha), "oc.proveedor_codigo": oc.proveedor.codigo,
        "oc.proveedor": oc.proveedor.nombre, "oc.proveedor_razon_social": getattr(oc.proveedor, "razon_social", None),
        "oc.sociedad": oc.sociedad, "oc.sociedad_nombre": soc.nombre if soc else None,
        "oc.centro_destino": oc.centro_destino, "oc.centro_destino_nombre": destino.nombre if destino else None,
        "oc.centro": oc.centro, "oc.puerto_despacho": oc.puerto_despacho, "oc.pais_origen": oc.pais_origen,
        "oc.incoterm": oc.incoterm, "oc.fecha_xf": _txt(oc.fecha_xf), "oc.fecha_tienda": _txt(oc.fecha_tienda),
        "oc.condicion_pago": oc.condicion_pago,
    }
    for k, val in (oc.extra or {}).items():
        v[f"oc.extra.{k}"] = _txt(val)
    v["oc.lineas"] = [_fila_linea(p, float(p.cantidad) if p.cantidad is not None else None)
                      for p in posiciones(db, oc.id)][:MAX_FILAS]
    return v


def valores_linea(p: PosicionOC) -> dict:
    from app.modulos.acceso import visibilidad

    v = {"linea.posicion": p.posicion, "linea.cantidad": float(p.cantidad) if p.cantidad is not None else None,
         "linea.unidad": p.unidad, "linea.fecha_entrega": _txt(p.fecha_entrega), "linea.almacen": p.almacen,
         "linea.casepack": p.casepack, "linea.inner_pack": p.inner_pack, "linea.prepack": p.prepack,
         "linea.codigo_articulo": p.codigo_articulo, "linea.upc": p.upc, "linea.pais_origen": p.pais_origen}
    if not visibilidad.oculto("precios"):
        v["linea.precio"] = float(p.precio) if p.precio is not None else None
    return v


def posiciones(db: Session, oc_id: int) -> list[PosicionOC]:
    return list(db.scalars(select(PosicionOC).where(PosicionOC.oc_id == oc_id).order_by(PosicionOC.id).options(
        selectinload(PosicionOC.articulo).selectinload(Articulo.producto),
        selectinload(PosicionOC.articulo).selectinload(Articulo.atributos))))


@dataclass
class Bulto:
    """Una unidad física de empaque de una lista de empaque (caja, tarima,
    inner…). Su identidad estable es (lista, grupo de cajas, índice dentro del
    grupo); `numero` es solo su número impreso (n de N)."""
    grupo_id: int
    numero: int
    total: int
    valores: dict = field(default_factory=dict)
    posiciones: list[int] = field(default_factory=list)
    pl_id: int | None = None
    tipo_empaque_id: int | None = None
    por_posicion: dict = field(default_factory=dict)  # línea de la OC → unidades en ESTE bulto (lo declarado en el PL)
    cuenta_como: str = "BULTO"  # BULTO | INTERIOR | SOPORTE (tipo de empaque)
    parcial: bool = False
    avisos: list = field(default_factory=list)  # datos que faltan para describir el contenido (nunca se inventan)
    indice: int = 1  # unidad dentro de su grupo de cajas (1…num_cajas)
    articulos: list[int] = field(default_factory=list)  # artículos distintos que lleva

    @property
    def clave(self) -> str:
        return f"pl{self.pl_id}-g{self.grupo_id}-u{self.indice}"


def _hijos(pl: PackingList) -> dict:
    res: dict = {}
    for g in pl.grupos:
        res.setdefault(g.padre_id, []).append(g)
    for lista in res.values():
        lista.sort(key=lambda g: g.id)
    return res


def _uniforme(g: GrupoCajas, hijos: dict) -> bool:
    """Todas las unidades del grupo llevan lo mismo: cada empaque interior se reparte
    en partes enteras iguales (si no, cada unidad se calcula por separado)."""
    return all(g.num_cajas and h.num_cajas % g.num_cajas == 0 and _uniforme(h, hijos) for h in hijos.get(g.id, []))


def _contenido(g: GrupoCajas, hijos: dict, k: int = 0) -> list[tuple]:
    """(línea de factura, cantidad) en la unidad k (desde 0) del empaque,
    incluido lo que llevan sus empaques interiores. Los interiores se reparten
    en unidades enteras: 10 inner en 3 cajas son 4, 3 y 3 (nunca 3,33)."""
    res = [(it.pl_linea.factura_linea, float(it.cantidad_por_caja)) for it in g.items]
    for h in hijos.get(g.id, []):
        if not g.num_cajas:
            continue
        base, extra = divmod(h.num_cajas, g.num_cajas)
        inicio = k * base + min(k, extra)
        for j in range(inicio, inicio + base + (1 if k < extra else 0)):
            res += _contenido(h, hijos, j)
    juntos: dict = {}
    for fl, q in res:
        x = juntos.setdefault(fl.id, [fl, 0.0])
        x[1] += q
    return [(fl, q) for fl, q in juntos.values()]


def _fila_linea(p: PosicionOC, q) -> dict:
    a = p.articulo
    fila = {"oc": p.oc.numero, "linea": p.posicion, "sku": p.codigo_articulo, "upc": p.upc or (a.upc if a else None),
            "descripcion": p.descripcion, "color": p.color, "talla": p.talla, "cantidad": q, "unidad": p.unidad}
    if a is not None:
        fila.update({f"atributo.{x.atributo.codigo}": x.valor for x in a.atributos})
    return fila


def _filas_contenido(items: list[tuple]) -> tuple[list[dict], list[dict], list[str]]:
    """Las líneas del bulto y su contenido por componente: un prepack o kit se
    reparte en sus componentes (cantidad del componente × paquetes). Si un
    prepack no tiene componentes definidos, no se inventa un reparto: se avisa."""
    lineas, componentes, avisos = [], {}, []
    for fl, q in items:
        p = fl.posicion_oc
        a = p.articulo
        lineas.append(_fila_linea(p, q))
        if a is not None and a.prepack is not None:
            if not a.prepack.componentes:
                avisos.append(f"The prepack {a.sku} has no components: its content by size cannot be shown.")
                continue
            for c in a.prepack.componentes:
                x = componentes.setdefault(c.articulo_id, _fila_articulo(c.articulo, 0))
                x["cantidad"] += c.cantidad * q
        else:
            clave = a.id if a is not None else f"c{p.codigo_articulo}"
            x = componentes.setdefault(clave, _fila_articulo(a, 0) if a is not None else
                                       {"sku": p.codigo_articulo, "upc": p.upc, "descripcion": p.descripcion, "color": p.color,
                                        "talla": p.talla, "cantidad": 0})
            x["cantidad"] += q
    return lineas[:MAX_FILAS], list(componentes.values())[:MAX_FILAS], avisos


def _nombre_tipo(g: GrupoCajas) -> str | None:
    return g.tipo_empaque.nombre if g.tipo_empaque else (g.plantilla_nombre or None)


def _unidades(pl: PackingList, nodos: list[GrupoCajas], hijos: dict, por_tipo: bool) -> list[Bulto]:
    """Una etiqueta por unidad de cada nodo, numeradas n de N (por tipo de
    empaque o en conjunto) con su código (C3, P1…) y el empaque que la contiene."""
    padres = {g.id: g for g in pl.grupos}
    clave = (lambda g: g.tipo_empaque_id) if por_tipo else (lambda g: None)
    total: dict = {}
    for g in nodos:
        total[clave(g)] = total.get(clave(g), 0) + g.num_cajas
    # Número de la primera unidad de cada nodo dentro de su tipo (para los códigos de los contenedores)
    inicio, cuenta = {}, {}
    for g in sorted(pl.grupos, key=lambda x: x.id):
        cuenta[g.tipo_empaque_id] = cuenta.get(g.tipo_empaque_id, 0)
        inicio[g.id] = cuenta[g.tipo_empaque_id]
        cuenta[g.tipo_empaque_id] += g.num_cajas
    emb = pl.unidad.embarque.codigo if pl.unidad and pl.unidad.embarque else None
    res: list[Bulto] = []
    n: dict = {}
    for g in nodos:
        uniforme = _uniforme(g, hijos)
        medidas = " × ".join(f"{x:g}" for x in (g.largo, g.ancho, g.alto) if x) or None
        prefijo = g.tipo_empaque.prefijo if g.tipo_empaque and g.tipo_empaque.prefijo else ""
        padre = padres.get(g.padre_id)
        armado = None
        for k in range(g.num_cajas):
            if armado is None or not uniforme:
                items = _contenido(g, hijos, k)
                lineas, componentes, avisos = _filas_contenido(items)
                por_posicion: dict = {}
                for fl, q in items:
                    por_posicion[fl.posicion_oc_id] = por_posicion.get(fl.posicion_oc_id, 0) + q
                articulos = sorted({fl.posicion_oc.articulo_id or -fl.posicion_oc_id for fl, _ in items})
                armado = (items, lineas, componentes, avisos, por_posicion, articulos,
                          "; ".join(f"{fl.posicion_oc.codigo_articulo} × {q:g}" for fl, q in items),
                          sorted({fl.posicion_oc_id for fl, _ in items}))
            items, lineas, componentes, avisos, por_posicion, articulos, contenido, pos_ids = armado
            n[clave(g)] = n.get(clave(g), 0) + 1
            numero = n[clave(g)]
            contenedor = None
            if padre is not None and padre.num_cajas:
                por_padre = max(g.num_cajas // padre.num_cajas, 1)
                ppref = padre.tipo_empaque.prefijo if padre.tipo_empaque and padre.tipo_empaque.prefijo else ""
                contenedor = f"{ppref}{inicio[padre.id] + min(k // por_padre, padre.num_cajas - 1) + 1}"
            res.append(Bulto(g.id, numero, total[clave(g)], {
                "bulto.numero": numero, "bulto.total": total[clave(g)], "bulto.packing_list": pl.numero,
                "bulto.factura": pl.factura.numero, "bulto.embarque": emb, "bulto.peso_bruto": g.peso_bruto_caja,
                "bulto.peso_neto": g.peso_neto_caja, "bulto.medidas": medidas, "bulto.unidades": sum(q for _, q in items),
                "bulto.contenido": contenido, "bulto.tipo": _nombre_tipo(g),
                "bulto.tipo_codigo": g.tipo_empaque.codigo if g.tipo_empaque else None,
                "bulto.parcial": bool(g.es_parcial), "bulto.mixto": len(articulos) > 1,
                "bulto.codigo": f"{prefijo}{inicio[g.id] + k + 1}" if prefijo else None, "bulto.contenedor": contenedor,
                "bulto.lineas": lineas, "bulto.componentes": componentes},
                pos_ids, pl.id, g.tipo_empaque_id, dict(por_posicion),
                g.tipo_empaque.cuenta_como if g.tipo_empaque else "BULTO", bool(g.es_parcial), list(avisos), k + 1, articulos))
    return res


def valores_pl(pl: PackingList) -> dict:
    """Los datos de la lista de empaque como documento (sus líneas con lo empacado)."""
    emb = pl.unidad.embarque.codigo if pl.unidad and pl.unidad.embarque else None
    hijos = _hijos(pl)
    lineas = [_fila_linea(x.factura_linea.posicion_oc, float(x.cantidad or 0)) for x in sorted(pl.lineas, key=lambda x: x.id)]
    return {"pl.numero": pl.numero, "pl.factura": pl.factura.numero, "pl.embarque": emb,
            "pl.bultos": sum(g.num_cajas for g in hijos.get(None, [])), "pl.lineas": lineas[:MAX_FILAS]}


def bultos(db: Session, oc_id: int) -> list[Bulto]:
    """Cajas de las listas de empaque no canceladas con mercancía de la OC,
    numeradas por lista de empaque (caja n de N). Solo los empaques de primer
    nivel: lo que va dentro de otro empaque no lleva etiqueta de bulto propia."""
    de_la_oc = (select(PLLinea.pl_id).join(FacturaLinea, FacturaLinea.id == PLLinea.factura_linea_id)
                .join(PosicionOC, PosicionOC.id == FacturaLinea.posicion_oc_id).where(PosicionOC.oc_id == oc_id))
    pls = list(db.scalars(select(PackingList).where(PackingList.id.in_(de_la_oc), PackingList.estado != "CANCELADO")
                          .order_by(PackingList.id)))
    res: list[Bulto] = []
    for pl in pls:
        hijos = _hijos(pl)
        res += _unidades(pl, hijos.get(None, []), hijos, por_tipo=False)
    return res


def niveles_pl(pl: PackingList) -> list[dict]:
    """Los tipos de empaque de una lista de empaque con cuántas unidades tiene cada uno."""
    res: dict = {}
    for g in pl.grupos:
        x = res.setdefault(g.tipo_empaque_id, {"tipo_empaque_id": g.tipo_empaque_id, "nombre": _nombre_tipo(g),
                                               "nivel": g.tipo_empaque.nivel if g.tipo_empaque else None,
                                               "cuenta_como": g.tipo_empaque.cuenta_como if g.tipo_empaque else "BULTO",
                                               "unidades": 0, "superior": False})
        x["unidades"] += g.num_cajas
        x["superior"] = x["superior"] or g.padre_id is None
    return sorted(res.values(), key=lambda x: (-(x["nivel"] or 0), x["nombre"] or ""))


def unidades_pl(pl: PackingList, tipo_empaque_id: int | None = None, superiores: bool = False) -> list[Bulto]:
    """Las unidades de un nivel de empaque de la lista (o las de primer nivel)."""
    hijos = _hijos(pl)
    if superiores:
        return _unidades(pl, hijos.get(None, []), hijos, por_tipo=False)
    nodos = sorted((g for g in pl.grupos if g.tipo_empaque_id == tipo_empaque_id), key=lambda g: g.id)
    return _unidades(pl, nodos, hijos, por_tipo=True)
