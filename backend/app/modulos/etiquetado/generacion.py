"""Generación de etiquetas: un solo camino para todo (trabajos.py la usa).

`planear()` arma los registros de un pedido (una OC, una lista de empaque o
artículos sueltos) para cada tipo de etiqueta pedido: qué se etiqueta, cuántas
salen, qué diseño le toca (reglas.py) y qué problemas hay (datos vacíos,
códigos inválidos, textos que no caben, empaque inconsistente, ya impreso…).
`producir()` guarda la ejecución con la versión exacta y la instantánea de los
valores de cada registro y dibuja el archivo.

Los archivos no se guardan: `archivo()` los vuelve a dibujar desde la versión
y la instantánea guardadas, así una descarga posterior es idéntica aunque el
diseño o los datos hayan cambiado (la huella sha256 lo comprueba).
"""
from __future__ import annotations

import hashlib
import io
import json
import math
import zipfile
from dataclasses import dataclass, field
from datetime import date
from types import SimpleNamespace

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.empresa import regla
from app.core.errores import ErrorNegocio
from app.modelos import (
    Articulo,
    FamiliaEtiquetado,
    GeneracionEtiquetas,
    GeneracionItem,
    OrdenCompra,
    PackingList,
    PlantillaEtiqueta,
    PosicionOC,
    TipoEtiqueta,
    Usuario,
    VersionPlantilla,
)
from app.modulos.acceso.permisos import exigir, proveedor_filtro, tiene
from app.modulos.comun.historial import registrar
from app.modulos.etiquetado import campos, datos, familias, plantillas, reglas, render, salidas
from app.modulos.etiquetado import diseno as svc_diseno
from app.modulos.etiquetado import tipos as tipos_etiqueta
from app.modulos.maestros import unidades as medidas

FORMATOS = {"PDF": "application/pdf", "PNG": "image/png", "SVG": "image/svg+xml", "ZIP": "application/zip"}
ORIGENES = ("OC", "ARTICULOS", "PACKING")


@dataclass
class Grupo:
    """Etiquetas iguales salvo su número: un registro (artículo, línea, bulto o
    documento) y un tipo de etiqueta."""
    clave: str
    referencia: str
    cantidad: int
    tipo: TipoEtiqueta
    articulo: Articulo | None = None
    posicion: PosicionOC | None = None
    bulto: campos.Bulto | None = None
    oc: OrdenCompra | None = None
    pl: PackingList | None = None
    eleccion: reglas.Eleccion | None = None
    version: VersionPlantilla | None = None
    valores: dict = field(default_factory=dict)
    problemas: list = field(default_factory=list)
    procedencia: dict = field(default_factory=dict)  # campo lógico → campo del que salió su valor
    omitido: bool = False  # el tipo no es obligatorio y no hay diseño para este registro
    item: GeneracionItem | None = None  # ya generado
    unidades: float = 0.0  # unidades de las líneas que junta (para «una por unidad»)
    unidad: str | None = None
    variantes: set = field(default_factory=set)  # variantes distintas que junta (artículo genérico)

    def problema(self, nivel: str, codigo: str, mensaje: str, campo: str | None = None) -> None:
        self.problemas.append({"nivel": nivel, "codigo": codigo, "mensaje": mensaje, "elemento": None, **({"campo": campo} if campo else {})})

    @property
    def errores(self):
        return [p for p in self.problemas if p["nivel"] == "error"]

    @property
    def advertencias(self):
        return [p for p in self.problemas if p["nivel"] == "advertencia"]

    @property
    def plantilla(self) -> PlantillaEtiqueta | None:
        return self.version.plantilla if self.version else (self.eleccion.plantilla if self.eleccion else None)

    def dict(self) -> dict:
        e, p = self.eleccion, self.plantilla
        fam = self.articulo.familia_efectiva if self.articulo else None
        return {"clave": self.clave, "referencia": self.referencia, "cantidad": self.cantidad,
                "tipo_etiqueta_id": self.tipo.id, "tipo": self.tipo.nombre,
                "articulo_id": self.articulo.id if self.articulo else None,
                "posicion_id": self.posicion.id if self.posicion else None,
                "bulto": self.bulto.numero if self.bulto else None, "familia": fam.nombre if fam else None,
                "oc_id": self.oc.id if self.oc else None, "oc": self.oc.numero if self.oc else None,
                "plantilla_id": p.id if p else None, "plantilla": p.nombre if p else None,
                "version_id": self.version.id if self.version else None, "version": self.version.numero if self.version else None,
                "uso_id": e.uso.id if e and e.uso else None, "porque": e.porque if e else None, "motivo": e.motivo if e else None,
                "omitido": self.omitido, "procedencia": {k: v for k, v in self.procedencia.items() if v},
                "problemas": self.problemas}


def _entero(v, defecto: int = 1) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return defecto


def _no_contable(p: PosicionOC, cant: float, unidad: str | None) -> str | None:
    """Por qué la cantidad no admite una etiqueta por unidad (o None si la admite).
    Decide el catálogo de unidades de medida (Configuración → Listas → unidad,
    atributo «contable»): una unidad desconocida no se adivina."""
    codigo = medidas.normalizar(unidad)
    if not codigo:
        return (f"The unit {unidad or '(empty)'} of the line is not in the units of measure catalog: "
                "add it (indicating whether it is counted in whole numbers) or use lines, packages or a manual quantity.")
    if not medidas.contable(codigo):
        return (f"The line is in {unidad} ({cant:g}), a unit that is measured, not counted: "
                "it cannot be labeled per unit; use lines, packages or a manual quantity.")
    if cant != int(cant):
        return f"The line has a fractional quantity ({cant:g} {unidad}): it cannot be labeled per unit; use a manual quantity."
    return None


def _no_contable_cant(p: PosicionOC, cant: float, unidad: str | None) -> tuple[int, str | None]:
    """Etiquetas por unidad de una cantidad (de la OC o empacada) y, si no se puede, por qué."""
    motivo = _no_contable(p, cant, unidad)
    return (int(cant) if cant == int(cant) else math.ceil(cant)), motivo


def cargar_pl(db: Session, user: Usuario, pl_id: int) -> PackingList:
    from app.modulos.acceso.permisos import asegurar_proveedor

    pl = db.get(PackingList, pl_id)
    if not pl or pl.estado == "CANCELADO":
        raise ErrorNegocio("The packing list does not exist.", 404, "no_encontrado")
    asegurar_proveedor(user, pl.factura.proveedor_id, pl.factura.sociedad)
    return pl


def pl_permite_reales(pl: PackingList) -> bool:
    """Una lista de empaque que todavía puede cambiar solo da etiquetas de prueba
    (salvo que la empresa lo permita): las reales no coincidirían con las cajas."""
    return pl.estado == "FINALIZADO" or bool(regla("ETIQUETAS_PL_SIN_FINALIZAR"))


# ---- Registros de cada origen ------------------------------------------------------------------
def _posiciones_oc(db: Session, oc: OrdenCompra, pedido: dict) -> list[PosicionOC]:
    posiciones = campos.posiciones(db, oc.id)
    elegidas = set(pedido.get("posiciones") or [])
    posiciones = [p for p in posiciones if p.id in elegidas] if elegidas else [p for p in posiciones if not p.bloqueada]
    if pedido.get("familia_id"):
        fid = int(pedido["familia_id"])
        posiciones = [p for p in posiciones if p.articulo and p.articulo.familia_efectiva
                      and fid in {f.id for f in p.articulo.familia_efectiva.ruta()}]
    return posiciones


def _manual(pedido: dict, clave: str, defecto: int = 0) -> int:
    return _entero((pedido.get("cantidades") or {}).get(clave), defecto)


class _Decide:
    """Resuelve la regla de cada registro fino (una línea, un artículo, un
    empaque, un documento) una sola vez: qué diseño, si la etiqueta va o no,
    dónde va y cuántas. Los valores se leen como en la generación."""

    def __init__(self, db: Session, tipos: list[TipoEtiqueta]):
        self.db = db
        self.motor = reglas.Resolvedor(db, sorted(tipos, key=lambda t: (t.orden, t.id)))
        self.org = campos.valores_organizacion(db)
        self.de_oc: dict = {}
        self.no_lleva: dict = {}  # tipo → registros a los que una regla dice que no va

    def __call__(self, t: TipoEtiqueta, articulo=None, oc=None, posicion=None, bulto=None, pl=None) -> reglas.Eleccion:
        if oc is not None and oc.id not in self.de_oc:
            self.de_oc[oc.id] = campos.valores_oc(self.db, oc)
        v = datos.valores(self.db, t.sujeto, articulo, oc, posicion, bulto, self.org, pl, self.de_oc.get(oc.id) if oc else None)
        s = reglas.Sujeto(t.sujeto, articulo=articulo, oc=oc, tipo_empaque_id=bulto.tipo_empaque_id if bulto else None, valores=v)
        e = self.motor.elegir(s, t)
        if e.no_lleva:
            self.no_lleva[t.id] = self.no_lleva.get(t.id, 0) + 1
        return e


ALCANCE_TXT = {"LINEA": "the document line", "POSICION_OC": "the PO line", "POSICION_PL": "the packing list line",
               "ARTICULO": "each variant", "PRODUCTO": "the generic item", "DOCUMENTO": "the document", "OC": "the PO",
               "PL": "the packing list", "EMPAQUE": "each package"}


def _grupos_articulo(db: Session, user: Usuario, pedido: dict, t: TipoEtiqueta, oc: OrdenCompra | None,
                     pl: PackingList | None, decide: _Decide, avisos: list) -> list[Grupo]:
    """Etiquetas de artículo. Primero cada registro fino (línea de la lista de
    empaque, posición de la OC o artículo elegido) con su regla; después se
    juntan según dónde dice la regla que va la etiqueta: la línea del
    documento, la posición de la OC, la línea de la lista de empaque, cada
    variante o el artículo genérico. Una regla «no lleva» no deja registro."""
    pref = f"t{t.id}-"
    finos = []  # (clave de la línea, referencia, artículo, posición, oc, unidades, unidad)
    if pl is not None:
        for x in sorted(pl.lineas, key=lambda x: x.id):
            p = x.factura_linea.posicion_oc
            finos.append((f"l{x.id}", f"{pl.numero} · {p.codigo_articulo}", p.articulo, p, p.oc, float(x.cantidad or 0), p.unidad))
    elif oc is not None:
        for p in _posiciones_oc(db, oc, pedido):
            finos.append((f"p{p.id}", f"{p.posicion} · {p.codigo_articulo}", p.articulo, p, oc, float(p.cantidad or 0), p.unidad))
    else:
        for x in pedido.get("articulos") or []:
            a = datos.cargar_articulo(db, user, x.get("articulo_id"))
            finos.append((f"a{a.id}", a.sku, a, None, None, float(_entero(x.get("cantidad"), 1)), a.unidad))
    res: dict[str, Grupo] = {}
    no_aplica: dict = {}
    for linea, ref, a, p, oc_, unidades, unidad in finos:
        e = decide(t, a, oc_, p, None, pl)
        if e.no_lleva:
            continue
        alcance = e.alcance
        codigo = (p.codigo_articulo if p else None) or (a.sku if a else "")
        if alcance == "LINEA":
            clave, referencia = linea, ref
        elif alcance == "POSICION_OC":
            if p is None:
                no_aplica[alcance] = no_aplica.get(alcance, 0) + 1
                continue
            clave, referencia = f"p{p.id}", f"{p.oc.numero} · {p.posicion} · {codigo}"
        elif alcance == "POSICION_PL":
            if pl is None:
                no_aplica[alcance] = no_aplica.get(alcance, 0) + 1
                continue
            clave, referencia = linea, ref
        elif alcance == "PRODUCTO" and a is not None and a.producto_id:
            prod = a.producto
            clave, referencia = f"r{a.producto_id}", " · ".join(x for x in (prod.estilo, prod.color) if x)
        else:  # ARTICULO (o PRODUCTO de un artículo sin producto: cada variante)
            clave = f"a{a.id}" if a is not None else f"c{codigo}"
            referencia = codigo
        k = pref + clave
        g = res.get(k)
        if g is None:
            g = res[k] = Grupo(k, referencia, 0, t, articulo=a, posicion=p, oc=oc_)
            g.eleccion, g.unidades, g.variantes = e, 0.0, set()
            g.unidad = unidad
        elif (g.eleccion.uso.id if g.eleccion.uso else None) != (e.uso.id if e.uso else None):
            g.problema("advertencia", "reglas_distintas", "Lines grouped here follow different rules: the first one is used.")
        g.unidades += unidades
        g.variantes.add(a.id if a is not None else codigo)
        if g.posicion is not None and p is not None and g.posicion.id != p.id:
            g.posicion = None  # varias líneas: los datos de una sola línea no aplican
    sueltos = pl is None and oc is None  # artículos elegidos: su cantidad es la que se escribió
    for g in res.values():
        cantidad = g.eleccion.cantidad
        if sueltos and cantidad in ("POR_UNIDAD", "MANUAL"):
            g.cantidad = _manual(pedido, g.clave, int(g.unidades)) if cantidad == "MANUAL" else int(g.unidades)
        elif cantidad == "POR_UNIDAD":
            g.cantidad, motivo = _no_contable_cant(g.posicion, g.unidades, g.unidad)
            if motivo:
                g.problema("error", "unidad_no_contable", motivo)
        elif cantidad == "MANUAL":
            g.cantidad = _manual(pedido, g.clave)
        else:
            g.cantidad = 1
    for alcance, n in no_aplica.items():
        avisos.append({"nivel": "advertencia", "codigo": "alcance_no_aplica", "elemento": None, "tipo_etiqueta_id": t.id,
                       "mensaje": f"{t.nombre}: {n} records go on {ALCANCE_TXT[alcance]}, which this origin does not have."})
    return list(res.values())


def _grupos_bulto(db: Session, pedido: dict, t: TipoEtiqueta, oc: OrdenCompra | None, pl: PackingList | None,
                  decide: _Decide | None = None) -> list[Grupo]:
    """Una etiqueta por bulto. Un bulto con un solo artículo lleva sus datos; con
    varios, los campos de artículo quedan vacíos (la tabla del contenido los muestra)."""
    if pl is not None:
        tipo = pedido.get("tipo_empaque_id")
        niveles = pedido.get("niveles") or [int(tipo) if tipo else 0]
        # Varios niveles a la vez (cajas, pallets, inners…): cada unidad física una sola vez
        unidades, vistas = [], set()
        for n in niveles:
            for u in campos.unidades_pl(pl, n or None, superiores=not n):
                if u.clave not in vistas:
                    vistas.add(u.clave)
                    unidades.append(u)
    elif oc is not None:
        unidades = campos.bultos(db, oc.id)
    else:
        return []
    # Un tipo limitado a algunos empaques (la etiqueta del pallet, la del inner…) solo sale en esos
    empaques = tipos_etiqueta.empaques_de(db, t.id)
    unidades = [u for u in unidades if tipos_etiqueta.aplica(empaques, u.tipo_empaque_id)]
    ids = {i for u in unidades for i in u.posiciones}
    posiciones = {p.id: p for p in db.scalars(select(PosicionOC).where(PosicionOC.id.in_(ids)))} if ids else {}
    res = []
    for u in unidades:
        lineas = [posiciones[i] for i in u.posiciones if i in posiciones]
        una = lineas[0] if len(lineas) == 1 else None
        ocs = {p.oc_id for p in lineas}
        oc_bulto = lineas[0].oc if len(ocs) == 1 and lineas else None
        articulo = lineas[0].articulo if len(u.articulos) == 1 and lineas else None
        codigo = u.valores.get("bulto.codigo") or f"{u.numero}/{u.total}"
        g = Grupo(f"t{t.id}-{u.clave}", f"{u.valores.get('bulto.packing_list')} · {codigo}", 1, t, articulo=articulo, posicion=una,
                  bulto=u, oc=oc_bulto)
        if not lineas:
            g.problema("advertencia", "sin_contenido", "The package has no items: the PO and item fields stay empty.")
        if decide is not None:
            g.eleccion = decide(t, articulo, oc_bulto, una, u, pl)
            if g.eleccion.no_lleva:
                continue
            if g.eleccion.cantidad == "MANUAL":
                g.cantidad = _manual(pedido, g.clave, 1)
        res.append(g)
    return res


def _grupos_documento(pedido: dict, t: TipoEtiqueta, oc: OrdenCompra | None, pl: PackingList | None,
                      decide: _Decide, avisos: list, ocs_pl: list | None = None) -> list[Grupo]:
    """Etiquetas de documento: según la regla, la del documento de origen, la de
    la OC (una por cada OC que trae la lista de empaque) o la de la lista."""
    e = decide(t, None, oc, None, None, pl)
    if e.no_lleva:
        return []
    alcance = e.alcance
    res = []
    if alcance == "PL" or (alcance == "DOCUMENTO" and pl is not None):
        if pl is None:
            avisos.append({"nivel": "advertencia", "codigo": "alcance_no_aplica", "elemento": None, "tipo_etiqueta_id": t.id,
                           "mensaje": f"{t.nombre}: it goes on the packing list, and these labels come from a PO."})
            return []
        k = f"t{t.id}-pl{pl.id}"
        g = Grupo(k, pl.numero, 1, t, pl=pl, oc=oc)
        g.eleccion = e
        res.append(g)
    else:  # la OC, o el documento de origen desde una OC
        for o in ([oc] if oc is not None else []) if pl is None else (ocs_pl or []):
            eo = e if o is oc else decide(t, None, o, None, None, pl)
            if eo.no_lleva:
                continue
            k = f"t{t.id}-oc{o.id}"
            g = Grupo(k, o.numero, 1, t, oc=o, pl=pl)
            g.eleccion = eo
            res.append(g)
    for g in res:
        if g.eleccion.cantidad == "MANUAL":
            g.cantidad = _manual(pedido, g.clave, 1)
    return res


def tipos_del_pedido(db: Session, pedido: dict) -> list[TipoEtiqueta]:
    ids = [int(x) for x in pedido.get("tipos") or []]
    if not ids:
        raise ErrorNegocio("Choose which labels to print.", 422, "validacion", [{"campo": "tipos", "mensaje": "Required."}])
    res = list(db.scalars(select(TipoEtiqueta).where(TipoEtiqueta.id.in_(ids)).order_by(TipoEtiqueta.orden, TipoEtiqueta.id)))
    if len(res) != len(set(ids)):
        raise ErrorNegocio("A label type does not exist.", 422, "validacion")
    return res


def armar(db: Session, user: Usuario, pedido: dict) -> tuple[OrdenCompra | None, PackingList | None, list[Grupo], list[dict]]:
    """Los registros del pedido para cada tipo de etiqueta (sin diseño ni datos todavía)
    y los avisos de los tipos que no aplican a ese origen."""
    origen = pedido.get("origen")
    if origen not in ORIGENES:
        raise ErrorNegocio("Choose where the labels come from: purchase orders, items or a packing list.", 422, "validacion")
    oc = datos.cargar_oc(db, user, pedido["oc_id"]) if origen == "OC" and pedido.get("oc_id") else None
    pl = cargar_pl(db, user, int(pedido["pl_id"])) if origen == "PACKING" and pedido.get("pl_id") else None
    if origen == "OC" and oc is None:
        raise ErrorNegocio("Choose the purchase order.", 422, "validacion")
    if origen == "PACKING" and pl is None:
        raise ErrorNegocio("Choose the packing list.", 422, "validacion")
    if pl is not None:
        ocs = {x.factura_linea.posicion_oc.oc_id for x in pl.lineas}
        oc = db.get(OrdenCompra, next(iter(ocs))) if len(ocs) == 1 else None
    grupos, avisos = [], []
    tipos = tipos_del_pedido(db, pedido)
    decide = _Decide(db, tipos)
    ocs_pl = sorted({x.factura_linea.posicion_oc.oc for x in pl.lineas}, key=lambda o: o.id) if pl is not None else None
    for t in tipos:
        antes = len(avisos)
        if t.sujeto == "ARTICULO":
            nuevos = _grupos_articulo(db, user, pedido, t, oc if origen == "OC" else None, pl, decide, avisos)
        elif t.sujeto == "BULTO":
            nuevos = _grupos_bulto(db, pedido, t, oc if origen == "OC" else None, pl, decide)
        else:
            nuevos = _grupos_documento(pedido, t, oc, pl, decide, avisos, ocs_pl)
        if not nuevos and decide.no_lleva.get(t.id):
            avisos.append({"nivel": "info", "codigo": "no_lleva", "elemento": None, "tipo_etiqueta_id": t.id,
                           "mensaje": f"{t.nombre}: the rules say it does not go on any of these records."})
        elif not nuevos and len(avisos) == antes:
            avisos.append({"nivel": "advertencia", "codigo": "tipo_no_aplica", "elemento": None, "tipo_etiqueta_id": t.id,
                           "mensaje": (f"{t.nombre}: there is nothing to label here (packages need a packing list, "
                                       "documents need a PO or a packing list).") if origen == "ARTICULOS" or t.sujeto != "ARTICULO"
                           else f"{t.nombre}: there are no lines to label."})
        grupos += nuevos
    return oc, pl, grupos, avisos


def _version_de(db: Session, plantilla: PlantillaEtiqueta, prueba: bool) -> VersionPlantilla | None:
    """La versión aprobada vigente. En una prueba, la última versión que no fue
    rechazada ni archivada (un diseño rechazado nunca se imprime, ni de prueba)."""
    if not prueba:
        return db.get(VersionPlantilla, plantilla.version_vigente_id) if plantilla.version_vigente_id else None
    validas = db.scalars(select(VersionPlantilla).where(VersionPlantilla.plantilla_id == plantilla.id,
                                                        VersionPlantilla.estado.in_(("BORRADOR", "PENDIENTE", "APROBADA")))
                         .order_by(VersionPlantilla.numero.desc()).limit(1)).first()
    return validas


def planear(db: Session, user: Usuario, pedido: dict, dibujar: bool = True, solo: set[str] | None = None) -> dict:
    """Qué se va a generar: los registros con su diseño y versión, cuántas
    etiquetas y qué problemas hay. Sin `dibujar`, solo cuenta y elige el diseño
    (para los resúmenes). `solo`: las claves que interesan (vista previa de un registro)."""
    from app.core.numeracion import proximo
    from app.modulos.etiquetado import campos_logicos, empaque_etiquetas

    exigir(user, "etiquetas.generar")
    prueba = bool(pedido.get("prueba"))
    # En prueba, las versiones sin aprobar solo las usa quien diseña; los demás prueban con las aprobadas
    borradores = tiene(user, "etiquetas.disenar")
    oc, pl, grupos, generales = armar(db, user, pedido)
    if solo is not None:
        grupos = [g for g in grupos if g.clave in solo]
    if pl is not None and not prueba and not pl_permite_reales(pl):
        generales.append({"nivel": "error", "codigo": "pl_sin_finalizar", "elemento": None,
                          "mensaje": f"The packing list {pl.numero} is not finalized yet: its packages can still change. "
                                     "Generate test labels or finalize it first."})
    elegidas = {str(k): v for k, v in (pedido.get("elegidas") or {}).items()}
    escritos = {str(k): v for k, v in (pedido.get("manuales") or {}).items()}
    organizacion = campos.valores_organizacion(db)
    motor = reglas.Resolvedor(db, sorted({g.tipo.id: g.tipo for g in grupos}.values(), key=lambda t: (t.orden, t.id)))
    de_oc: dict = {}
    serie = None
    validar_empaque = bool(regla("ETIQUETAS_VALIDAR_EMPAQUE"))
    posiciones = {g.posicion.id: g.posicion for g in grupos if g.posicion is not None}
    faltan = {pid for g in grupos if g.bulto for pid in g.bulto.por_posicion} - set(posiciones)
    if faltan:
        posiciones.update({p.id: p for p in db.scalars(select(PosicionOC).where(PosicionOC.id.in_(faltan)))})
    for g in grupos:
        if g.cantidad < 1:
            g.problema("error", "cantidad", "Enter how many labels (1 or more).")
        if g.oc is not None and g.oc.id not in de_oc:
            de_oc[g.oc.id] = campos.valores_oc(db, g.oc)
        sujeto = g.tipo.sujeto
        g.valores = datos.valores(db, sujeto, g.articulo, g.oc, g.posicion, g.bulto, organizacion, g.pl,
                                  de_oc.get(g.oc.id) if g.oc is not None else None)
        g.valores.update({"contexto.origen": pedido.get("origen"), "contexto.tipo_etiqueta": g.tipo.nombre})
        logicos, g.procedencia, de_fuentes = campos_logicos.resolver(db, sujeto, g.valores)
        g.valores.update(logicos)
        forzada = elegidas.get(g.clave)
        if forzada:
            p = db.get(PlantillaEtiqueta, int(forzada))
            if p is None or p.tipo_etiqueta_id != g.tipo.id or p.estado != "ACTIVA":
                g.problema("error", "sin_plantilla", "The chosen design is not of this label type or is archived.")
                continue
            uso = SimpleNamespace(plantilla=p, id=None, motivo=None, accion="USAR", alcance=None, cantidad=None, prioridad=0)
            g.eleccion = reglas.Eleccion(g.tipo, uso, {"clase": "elegida"})
        elif g.eleccion is not None:
            pass  # la regla ya se resolvió al armar los registros (decidió dónde va y cuántas)
        else:
            s = reglas.Sujeto(sujeto, articulo=g.articulo, oc=g.oc, tipo_empaque_id=g.bulto.tipo_empaque_id if g.bulto else None,
                              valores=g.valores)
            g.eleccion = motor.elegir(s, g.tipo)
        e = g.eleccion
        if e.plantilla is None:
            if g.tipo.obligatoria:
                g.problema("error", "sin_plantilla", f"No design of {g.tipo.nombre} applies to this record.")
            else:
                g.omitido = True
                g.problema("info", "sin_plantilla", f"{g.tipo.nombre} does not apply to this record (no design is assigned).")
            continue
        g.problemas += de_fuentes
        if e.porque.get("empate"):
            otros = ", ".join(x["plantilla"] for x in e.porque["empate"])
            g.problema("advertencia", "excepciones_empatadas",
                       f"Other exceptions of the same place also apply ({otros}): the oldest one is used. "
                       "Make their conditions exclusive.")
        if not dibujar:
            if e.plantilla.version_vigente_id is None and not (prueba and borradores):
                g.problema("error", "sin_plantilla", "The design has no approved version.")
            continue
        g.version = _version_de(db, e.plantilla, prueba and borradores)
        if g.version is None:
            g.problema("error", "sin_plantilla", "The design has no approved version." if not (prueba and borradores)
                       else "The design has no version that can be tested (they are rejected or archived).")
            continue
        if g.posicion is not None and g.articulo is None:
            g.problema("advertencia", "sin_articulo", "The PO line is not linked to an item of the master data: only the line data is printed.")
        g.valores.update(svc_diseno.valores_manuales(g.version.diseno, escritos))
        for falta in svc_diseno.manuales_faltantes(g.version.diseno, g.valores):
            g.problema("error", "manual_obligatorio", f"Write the value of {falta} before generating.")
        usados = svc_diseno.campos_usados(g.version.diseno)
        if g.oc is None and any(c.startswith(("oc.", "linea.")) for c in usados):
            g.problema("advertencia", "sin_oc", "The design prints purchase order data and these labels come without a PO: "
                                                "those fields stay empty.")
        if g.bulto is not None and g.articulo is None and any(c.startswith(("articulo.", "producto.")) for c in usados) \
                and len(g.bulto.articulos) > 1:
            g.problema("advertencia", "contenido_mixto", "The package holds several items: the item fields stay empty "
                                                         "(use the table of the package contents).")
        if g.bulto is not None and validar_empaque:
            g.problemas += empaque_etiquetas.revisar(g.bulto, posiciones)
        if "etiqueta.serie" in usados:
            serie = serie or _serie_etiquetas(db)
            if serie is None:
                g.problema("error", "sin_serie", "The design uses the controlled label ID and there is no active numbering "
                                                 "series for labels (Settings → Numbering, object «etiqueta»).")
            else:
                g.valores["etiqueta.serie"] = proximo(db, serie)
        fam = g.articulo.familia_efectiva if g.articulo else None
        for faltante in familias.faltantes(db, fam, g.valores):
            g.problema("advertencia", "dato_familia", f"The family {fam.nombre} expects {faltante}, which is empty.", campo=faltante)
        lz = render.componer(g.version.diseno, {**g.valores, "etiqueta.numero": 1, "etiqueta.total": g.cantidad,
                                               "etiqueta.numero_lote": 1, "etiqueta.total_lote": 1}, campos.tipos(db, sujeto),
                             plantillas.imagen_adjunta(db))
        g.problemas += lz.problemas
    if dibujar:
        previas = _previas(db, grupos)
        for g in grupos:
            if g.clave in previas:
                p = previas[g.clave]
                g.problema("advertencia", "ya_generada",
                           f"Labels for this were already generated on {p['fecha']:%Y-%m-%d} by {p['usuario']} ({p['cantidad']}).")
    for g in grupos:
        _clasificar(g.problemas)
    _clasificar(generales)
    total = sum(g.cantidad for g in grupos if g.cantidad > 0 and not g.omitido)
    errores = sum(len(g.errores) for g in grupos) + len([p for p in generales if p["nivel"] == "error"])
    variables = {}
    for g in grupos:
        for v in (g.version.diseno.get("variables") or []) if g.version else []:
            variables.setdefault(v["clave"], v)
    return {"variables": list(variables.values()), "oc_id": oc.id if oc else None, "oc": oc.numero if oc else None,
            "pl_id": pl.id if pl else None, "prueba": prueba, "total": total, "grupos": [g.dict() for g in grupos],
            "problemas": generales, "errores": errores, "advertencias": sum(len(g.advertencias) for g in grupos),
            "puede_generar": errores == 0 and total > 0, "_grupos": grupos}


def _previas(db: Session, grupos: list[Grupo]) -> dict:
    """Etiquetas reales ya generadas del mismo tipo para el mismo registro (línea,
    bulto o documento): avisa antes de imprimir dos veces sin querer. Un bulto
    se reconoce por su identidad (lista, grupo de cajas, unidad), no por su texto."""
    posiciones = {g.posicion.id for g in grupos if g.posicion is not None and g.bulto is None}
    pls = {g.bulto.pl_id for g in grupos if g.bulto is not None} | {g.pl.id for g in grupos if g.pl is not None and g.bulto is None}
    ocs = {g.oc.id for g in grupos if g.tipo.sujeto == "DOCUMENTO" and g.oc is not None and g.pl is None}
    if not (posiciones or pls or ocs):
        return {}
    c = (select(GeneracionItem, GeneracionEtiquetas.creada_en, GeneracionEtiquetas.creada_por, GeneracionEtiquetas.oc_id,
                GeneracionEtiquetas.pl_id)
         .join(GeneracionEtiquetas, GeneracionEtiquetas.id == GeneracionItem.generacion_id)
         .where(GeneracionEtiquetas.estado == "GENERADA",
                (GeneracionItem.posicion_id.in_(posiciones)) | (GeneracionItem.pl_id.in_(pls))
                | (GeneracionEtiquetas.oc_id.in_(ocs)) | (GeneracionEtiquetas.pl_id.in_(pls)))
         .order_by(GeneracionEtiquetas.creada_en.desc()))
    hechos: dict = {}
    for it, fecha, uid, oc_id, pl_id in db.execute(c):
        if it.grupo_cajas_id is not None:
            clave = ("B", it.tipo_etiqueta_id, it.pl_id, it.grupo_cajas_id, it.bulto_indice)
        elif it.posicion_id is not None:
            clave = ("P", it.tipo_etiqueta_id, it.posicion_id)
        elif it.articulo_id is None:
            clave = ("D", it.tipo_etiqueta_id, oc_id, pl_id)
        else:
            continue
        hechos.setdefault(clave, (fecha, uid, it.cantidad))
    usuarios: dict = {}
    res = {}
    for g in grupos:
        t = g.tipo.id
        if g.bulto is not None:
            clave = ("B", t, g.bulto.pl_id, g.bulto.grupo_id, g.bulto.indice)
        elif g.posicion is not None:
            clave = ("P", t, g.posicion.id)
        elif g.tipo.sujeto == "DOCUMENTO":
            clave = ("D", t, g.oc.id if g.oc and g.pl is None else None, g.pl.id if g.pl else None)
        else:
            continue
        if clave in hechos:
            fecha, uid, cant = hechos[clave]
            if uid not in usuarios:
                u = db.get(Usuario, uid) if uid else None
                usuarios[uid] = (u.nombre or u.email) if u else "—"
            res[g.clave] = {"fecha": fecha, "usuario": usuarios[uid], "cantidad": cant}
    return res


# ---- Producir --------------------------------------------------------------------------------
def producir(db: Session, user: Usuario, grupos: list[Grupo], pedido: dict) -> dict:
    """Guarda la ejecución (los registros listos de una parte del trabajo) con la
    versión exacta y la instantánea de cada registro, y dibuja su archivo."""
    formato = (pedido.get("formato") or "PDF").upper()
    if formato not in FORMATOS:
        raise ErrorNegocio("Choose PDF, PNG, SVG or ZIP.", 422, "validacion")
    if not grupos:
        raise ErrorNegocio("Nothing can be generated.", 422, "etiquetas_con_errores")
    malos = [g for g in grupos if g.errores or g.version is None or g.omitido]
    if malos:
        raise ErrorNegocio("Some labels cannot be generated: fix the errors first.", 422, "etiquetas_con_errores",
                           [{"campo": g.referencia, "mensaje": x["mensaje"]} for g in malos for x in g.errores][:50])
    hoja = pedido.get("hoja")
    if hoja is not None:
        hoja = svc_diseno.Hoja.model_validate(hoja).model_dump()
        if hoja["modo"] == "hoja":
            no_caben = sorted({f"{g.version.diseno['ancho']:g}×{g.version.diseno['alto']:g} mm" for g in grupos
                               if not salidas.cabe(hoja, g.version.diseno["ancho"], g.version.diseno["alto"])})
            if no_caben:
                raise ErrorNegocio("Some labels do not fit on the sheet with these columns, rows and margins.", 422, "validacion",
                                   [{"campo": "hoja", "mensaje": x} for x in no_caben])
    advertencias = [{"referencia": g.referencia, "mensaje": x["mensaje"]} for g in grupos for x in g.problemas
                    if x["nivel"] == "advertencia"]
    prueba = bool(pedido.get("prueba")) or any(g.version.estado != "APROBADA" for g in grupos)
    g0 = GeneracionEtiquetas(oc_id=pedido.get("oc_id"), pl_id=pedido.get("pl_id"), lote=pedido.get("lote"), formato=formato,
                             trabajo_id=pedido.get("_trabajo_id"), estado="PRUEBA" if prueba else "GENERADA",
                             total=sum(g.cantidad for g in grupos), creada_por=user.id, advertencias=advertencias[:200],
                             parametros={"hoja": hoja, "dpi": pedido.get("dpi"), "manuales": pedido.get("manuales"),
                                         "tipos": pedido.get("tipos"), "zip": pedido.get("zip")})
    if any("organizacion.logo" in svc_diseno.campos_usados(g.version.diseno) for g in grupos):
        g0.parametros = {**g0.parametros, "logo": campos.valores_organizacion(db).get("organizacion.logo")}
    db.add(g0)
    db.flush()
    serie = None
    registros = pedido.get("_registros") or {}
    for g in grupos:
        usados = svc_diseno.campos_usados(g.version.diseno) | {"etiqueta.fecha"}
        fam = g.articulo.familia_efectiva.id if g.articulo and g.articulo.familia_efectiva else None
        valores = {k: g.valores.get(k) for k in sorted(usados) if k != "organizacion.logo"
                   and (not k.startswith("etiqueta.") or k == "etiqueta.fecha")}
        procedencia = {k: v for k, v in g.procedencia.items() if k in usados and v}
        if procedencia:
            valores["_procedencia"] = procedencia
        if "etiqueta.serie" in usados:
            from app.core.numeracion import reservar

            serie = serie or _serie_etiquetas(db)
            inicio, prefijo = reservar(db, serie, g.cantidad)
            valores["_serie"] = {"serie": serie.codigo, "prefijo": prefijo, "digitos": serie.digitos, "inicio": inicio}
        it = GeneracionItem(generacion_id=g0.id, plantilla_id=g.version.plantilla_id, version_id=g.version.id,
                            tipo_etiqueta_id=g.tipo.id, trabajo_registro_id=registros.get(g.clave),
                            articulo_id=g.articulo.id if g.articulo else None, posicion_id=g.posicion.id if g.posicion else None,
                            pl_id=g.bulto.pl_id if g.bulto else None, grupo_cajas_id=g.bulto.grupo_id if g.bulto else None,
                            bulto_indice=g.bulto.indice if g.bulto else None,
                            grupo_id=fam, referencia=g.referencia[:120], cantidad=g.cantidad, valores=valores,
                            motivo=(g.eleccion.motivo or "")[:200] if g.eleccion else None)
        db.add(it)
        g.item = it
    db.flush()
    db.refresh(g0)
    contenido, nombre, _ = _producir(db, g0, formato)
    g0.archivo, g0.sha256 = nombre, hashlib.sha256(contenido).hexdigest()
    db.flush()
    oc = db.get(OrdenCompra, g0.oc_id) if g0.oc_id else None
    registrar(db, user, "generacion_etiquetas", g0.id, "generar",
              {"oc": oc.numero if oc else None, "total": g0.total, "formato": formato, "estado": g0.estado, "trabajo": g0.trabajo_id,
               "versiones": sorted({f"{g.version.plantilla.nombre} v{g.version.numero}" for g in grupos})})
    return dict_generacion(db, g0)


# Categoría de cada problema (lo que ve quien genera para decidir qué corregir)
CATEGORIAS = {
    "dato_obligatorio": "dato_obligatorio", "manual_obligatorio": "dato_obligatorio", "campo_obligatorio": "dato_obligatorio",
    "codigo_sin_valor": "dato_obligatorio", "tabla_vacia": "dato_opcional", "campo_vacio": "dato_opcional",
    "imagen_faltante": "dato_opcional", "sin_articulo": "dato_opcional", "sin_lista_empaque": "dato_opcional",
    "total_incompleto": "dato_opcional",
    "fuentes_distintas": "conflicto",
    "sin_plantilla": "configuracion", "familia": "configuracion", "sin_serie": "configuracion",
    "contenido_mixto": "empaque", "sin_oc": "dato_opcional", "dato_familia": "dato_opcional",
    "tipo_no_aplica": "configuracion", "pl_sin_finalizar": "empaque", "sin_contenido": "empaque", "casepack_distinto": "inconsistencia",
    "inner_incompleto": "inconsistencia", "prepack_sin_componentes": "inconsistencia", "unidad_no_contable": "empaque",
    "bulto_parcial": "empaque",
    "ya_generada": "excepcion", "diseno_forzado": "excepcion", "cantidad": "cantidad", "lote_grande": "cantidad",
    "codigo_invalido": "codigo", "codigo_contraste": "codigo", "codigo_pequeno": "codigo", "codigo_bajo": "codigo",
    "codigo_ilegible": "codigo",
}


def _clasificar(problemas: list[dict]) -> list[dict]:
    for p in problemas:
        p.setdefault("categoria", CATEGORIAS.get(p.get("codigo"), "diseno"))
    return problemas


def _serie_etiquetas(db: Session):
    from app.core.numeracion import serie_de

    return serie_de(db, "etiqueta")


def numero_serie(valores: dict, n: int) -> str | None:
    """El identificador controlado de la etiqueta n del grupo (reservado al generar)."""
    s = valores.get("_serie")
    if not s:
        return None
    return f"{s['prefijo']}{s['inicio'] + n - 1:0{s['digitos']}d}"


def _lienzos(db: Session, gen: GeneracionEtiquetas) -> list[tuple[render.Lienzo, str]]:
    """Las etiquetas del lote dibujadas desde las versiones y valores guardados."""
    tipos = campos.tipos(db)
    imagenes = plantillas.imagen_adjunta(db)
    res = []
    n_lote = 0
    for it in gen.items:
        v = db.get(VersionPlantilla, it.version_id)
        valores = dict(it.valores or {})
        if "organizacion.logo" in svc_diseno.campos_usados(v.diseno):
            valores["organizacion.logo"] = (gen.parametros or {}).get("logo")
        for n in range(1, it.cantidad + 1):
            n_lote += 1
            serie = numero_serie(valores, n)
            lz = render.componer(v.diseno, {**valores, "etiqueta.numero": n, "etiqueta.total": it.cantidad,
                                            "etiqueta.numero_lote": n_lote, "etiqueta.total_lote": gen.total,
                                            **({"etiqueta.serie": serie} if serie else {})},
                                 tipos, imagenes, prueba=gen.estado == "PRUEBA")
            res.append((lz, f"{it.referencia or it.id}-{n}", it, n))
    return res


def _seguro(nombre: str) -> str:
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in nombre)[:80]


def seleccionar(gen: GeneracionEtiquetas, seleccion: list | None) -> dict[int, tuple[int, int]] | None:
    """Los grupos y rangos de un lote ({item_id: (desde, hasta)}) a partir de [{item_id, desde, hasta}];
    None es todo el lote. Un grupo que no es del lote o un rango fuera de sus etiquetas no se acepta."""
    if not seleccion:
        return None
    items = {it.id: it for it in gen.items}
    res: dict[int, tuple[int, int]] = {}
    for x in seleccion:
        try:
            it = items[int(x.get("item_id"))]
            desde, hasta = int(x.get("desde") or 1), int(x.get("hasta") or it.cantidad)
        except (KeyError, TypeError, ValueError, AttributeError):
            raise ErrorNegocio("Choose groups of this batch.", 422, "validacion") from None
        if not 1 <= desde <= hasta <= it.cantidad:
            raise ErrorNegocio(f"{it.referencia or it.id}: choose labels from 1 to {it.cantidad}.", 422, "validacion")
        res[it.id] = (desde, hasta)
    return res


def _producir(db: Session, gen: GeneracionEtiquetas, formato: str, seleccion: dict | None = None,
              sufijo: str = "") -> tuple[bytes, str, str]:
    lienzos = _lienzos(db, gen)
    if seleccion is not None:  # algunos grupos o rangos (reimpresión): las mismas etiquetas, con sus mismos números
        lienzos = [x for x in lienzos if x[2].id in seleccion and seleccion[x[2].id][0] <= x[3] <= seleccion[x[2].id][1]]
    base = _seguro(f"labels-{gen.id}" + (f"-{db.get(OrdenCompra, gen.oc_id).numero}" if gen.oc_id else "") + sufijo)
    hoja = (gen.parametros or {}).get("hoja")
    if hoja is None:
        v = db.get(VersionPlantilla, gen.items[0].version_id) if gen.items else None
        mismas = len({(lz.ancho, lz.alto) for lz, *_ in lienzos}) == 1
        hoja = v.diseno.get("hoja") if v and mismas else None
    dpi = (gen.parametros or {}).get("dpi")
    if formato == "PDF":
        return salidas.pdf([lz for lz, *_ in lienzos], hoja, base), f"{base}.pdf", FORMATOS["PDF"]
    if formato in ("PNG", "SVG") and len(lienzos) == 1:
        lz = lienzos[0][0]
        datos_ = salidas.png(lz, dpi) if formato == "PNG" else salidas.svg(lz).encode()
        return datos_, f"{base}.{formato.lower()}", FORMATOS[formato]
    buf = io.BytesIO()
    fecha = gen.creada_en.timetuple()[:6]  # la fecha del lote en cada archivo: el mismo lote da el mismo ZIP

    def poner(z, nombre: str, datos_: bytes | str):
        info = zipfile.ZipInfo(nombre, date_time=fecha)
        info.compress_type = zipfile.ZIP_DEFLATED
        z.writestr(info, datos_)

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        if formato in ("ZIP", "PDF"):
            poner(z, f"{base}.pdf", salidas.pdf([lz for lz, *_ in lienzos], hoja, base))
        for i, (lz, nombre, *_) in enumerate(lienzos, start=1):
            archivo = f"{i:05d}-{_seguro(nombre)}"
            if formato in ("PNG", "ZIP"):
                poner(z, f"png/{archivo}.png", salidas.png(lz, dpi))
            if formato in ("SVG", "ZIP"):
                poner(z, f"svg/{archivo}.svg", salidas.svg(lz))
        poner(z, "lote.json", json.dumps(_manifiesto(db, gen), ensure_ascii=False, indent=1, default=str))
    return buf.getvalue(), f"{base}.zip", FORMATOS["ZIP"]


def _manifiesto(db: Session, gen: GeneracionEtiquetas) -> dict:
    return {"generacion": gen.id, "fecha": gen.creada_en, "estado": gen.estado, "total": gen.total,
            "items": [{"referencia": it.referencia, "cantidad": it.cantidad, "plantilla_id": it.plantilla_id,
                       "version_id": it.version_id, "version": db.get(VersionPlantilla, it.version_id).numero, "valores": it.valores}
                      for it in gen.items]}


# ---- Historial ---------------------------------------------------------------------------------
def _alcance(user: Usuario):
    prov = proveedor_filtro(user)
    if prov is None:
        return []
    return [(GeneracionEtiquetas.creada_por == user.id)
            | GeneracionEtiquetas.oc_id.in_(select(OrdenCompra.id).where(OrdenCompra.proveedor_id.in_(prov)))]


def cargar(db: Session, user: Usuario, generacion_id: int) -> GeneracionEtiquetas:
    exigir(user, "etiquetas.ver")
    g = db.scalar(select(GeneracionEtiquetas).where(GeneracionEtiquetas.id == generacion_id, *_alcance(user)))
    if not g:
        raise ErrorNegocio("The label batch does not exist.", 404, "no_encontrado")
    return g


def dict_generacion(db: Session, g: GeneracionEtiquetas, completo: bool = False) -> dict:
    u = db.get(Usuario, g.creada_por) if g.creada_por else None
    oc = db.get(OrdenCompra, g.oc_id) if g.oc_id else None
    versiones = {}
    for it in g.items:
        v = db.get(VersionPlantilla, it.version_id)
        versiones[it.version_id] = {"plantilla_id": it.plantilla_id, "plantilla": v.plantilla.nombre, "version_id": v.id,
                                    "version": v.numero}
    pl = db.get(PackingList, g.pl_id) if g.pl_id else None
    tipos_ = sorted({it.tipo_etiqueta_id for it in g.items if it.tipo_etiqueta_id})
    nombres = dict(db.execute(select(TipoEtiqueta.id, TipoEtiqueta.nombre).where(TipoEtiqueta.id.in_(tipos_))).all()) if tipos_ else {}
    r = {"id": g.id, "oc_id": g.oc_id, "oc": oc.numero if oc else None, "pl_id": g.pl_id, "packing_list": pl.numero if pl else None,
         "lote": g.lote, "tipos": [nombres.get(i) for i in tipos_],
         "formato": g.formato, "estado": g.estado, "total": g.total, "archivo": g.archivo, "sha256": g.sha256,
         "creada_por": (u.nombre or u.email) if u else None, "creada_en": g.creada_en, "versiones": list(versiones.values()),
         "grupos": len(g.items), "advertencias": g.advertencias or [],
         "anulada_en": g.anulada_en, "motivo_anulacion": g.motivo_anulacion, "reimpresiones": len(g.reimpresiones or [])}
    if completo:
        familias_ = {f.id: f.nombre for f in db.scalars(select(FamiliaEtiquetado))}
        r["items"] = [{"id": it.id, "referencia": it.referencia, "cantidad": it.cantidad, "articulo_id": it.articulo_id,
                       "posicion_id": it.posicion_id, "familia": familias_.get(it.grupo_id),
                       "tipo": nombres.get(it.tipo_etiqueta_id),
                       "plantilla": versiones[it.version_id]["plantilla"], "version": versiones[it.version_id]["version"],
                       "motivo": it.motivo, "valores": it.valores} for it in g.items]
    return r


def listar(db: Session, user: Usuario, desde: date | None = None, hasta: date | None = None, usuario_id: int | None = None,
           oc_id: int | None = None, articulo_id: int | None = None, familia_id: int | None = None,
           plantilla_id: int | None = None, version_id: int | None = None, estado: str | None = None,
           page: int = 1, size: int = 25) -> dict:
    exigir(user, "etiquetas.ver")
    from datetime import datetime, timedelta

    c = select(GeneracionEtiquetas).where(*_alcance(user))
    if desde:
        c = c.where(GeneracionEtiquetas.creada_en >= datetime.combine(desde, datetime.min.time()))
    if hasta:
        c = c.where(GeneracionEtiquetas.creada_en < datetime.combine(hasta + timedelta(days=1), datetime.min.time()))
    if usuario_id:
        c = c.where(GeneracionEtiquetas.creada_por == usuario_id)
    if oc_id:
        c = c.where(GeneracionEtiquetas.oc_id == oc_id)
    if estado:
        c = c.where(GeneracionEtiquetas.estado == estado.upper())
    for col, v in (("articulo_id", articulo_id), ("grupo_id", familia_id), ("plantilla_id", plantilla_id), ("version_id", version_id)):
        if v:
            c = c.where(GeneracionEtiquetas.id.in_(select(GeneracionItem.generacion_id).where(getattr(GeneracionItem, col) == v)))
    total = db.scalar(select(func.count()).select_from(c.subquery())) or 0
    filas = db.scalars(c.order_by(GeneracionEtiquetas.creada_en.desc(), GeneracionEtiquetas.id.desc())
                       .offset((page - 1) * size).limit(size)).all()
    return {"total": total, "items": [dict_generacion(db, g) for g in filas]}


def no_anulada(g: GeneracionEtiquetas) -> None:
    if g.anulada_en:
        raise ErrorNegocio("This label batch was voided: it can no longer be downloaded or printed.", 409, "anulada")


def marcar_descarga(g: GeneracionEtiquetas) -> None:
    """Descargado no es impreso: solo cuenta las descargas."""
    from app.modelos import ahora

    g.descargas = (g.descargas or 0) + 1
    g.descargada_en = ahora()


def archivo(db: Session, user: Usuario, generacion_id: int, formato: str | None = None) -> tuple[bytes, str, str, bool]:
    """El archivo del lote, dibujado de nuevo desde su versión e instantánea; y si es idéntico al original.
    Descargar es de quien genera (ver solo deja consultar el historial)."""
    exigir(user, "etiquetas.generar")
    g = cargar(db, user, generacion_id)
    no_anulada(g)
    formato = (formato or g.formato).upper()
    if formato not in FORMATOS:
        raise ErrorNegocio("Choose PDF, PNG, SVG or ZIP.", 422, "validacion")
    contenido, nombre, mime = _producir(db, g, formato)
    identico = formato == g.formato and hashlib.sha256(contenido).hexdigest() == g.sha256
    marcar_descarga(g)
    registrar(db, user, "generacion_etiquetas", g.id, "descargar", {"formato": formato, "identico": identico})
    return contenido, nombre, mime, identico


def resumen(db: Session, user: Usuario, origen: str, id_: int) -> dict:
    """Lo que se imprimiría desde una OC o una lista de empaque (o un producto),
    por tipo de etiqueta: cuántas, con qué diseños y qué falta. No dibuja nada."""
    from app.modelos import TrabajoEtiquetas  # noqa: F401
    from app.modulos.etiquetado.tipos import dict_tipo

    exigir(user, "etiquetas.generar")
    origen = origen.upper()
    tipos_ = list(db.scalars(select(TipoEtiqueta).where(TipoEtiqueta.activo.is_(True)).order_by(TipoEtiqueta.orden, TipoEtiqueta.id)))
    if origen == "PRODUCTO":
        arts = list(db.scalars(select(Articulo.id).where(Articulo.producto_id == id_, Articulo.activo.is_(True))))
        pedido = {"origen": "ARTICULOS", "articulos": [{"articulo_id": a, "cantidad": 1} for a in arts]}
        tipos_ = [t for t in tipos_ if t.sujeto == "ARTICULO"]
    elif origen == "OC":
        pedido = {"origen": "OC", "oc_id": id_}
    elif origen == "PACKING":
        pedido = {"origen": "PACKING", "pl_id": id_}
    else:
        raise ErrorNegocio("Unknown origin.", 422, "validacion")
    if not tipos_:
        return {"tipos": [], "total": 0, "problemas": [], "etiquetas_reales": True}
    plan = planear(db, user, {**pedido, "tipos": [t.id for t in tipos_]}, dibujar=False)
    por_tipo = {t.id: {"tipo": dict_tipo(db, t), "etiquetas": 0, "registros": 0, "omitidos": 0, "disenos": {}, "problemas": []}
                for t in tipos_}
    for g in plan["_grupos"]:
        x = por_tipo[g.tipo.id]
        if g.omitido:
            x["omitidos"] += 1
            continue
        x["registros"] += 1
        x["etiquetas"] += max(g.cantidad, 0)
        p = g.plantilla
        if p is not None:
            d = x["disenos"].setdefault(p.id, {"plantilla_id": p.id, "plantilla": p.nombre, "etiquetas": 0,
                                               "aprobada": bool(p.version_vigente_id)})
            d["etiquetas"] += max(g.cantidad, 0)
        for prob in g.errores:
            x["problemas"].append({"referencia": g.referencia, "articulo_id": g.articulo.id if g.articulo else None,
                                   "familia_id": g.articulo.familia_efectiva.id if g.articulo and g.articulo.familia_efectiva else None,
                                   "codigo": prob["codigo"], "mensaje": prob["mensaje"]})
    pl = db.get(PackingList, id_) if origen == "PACKING" else None
    generadas = 0
    if origen in ("OC", "PACKING"):
        col = GeneracionEtiquetas.oc_id if origen == "OC" else GeneracionEtiquetas.pl_id
        generadas = db.scalar(select(func.coalesce(func.sum(GeneracionEtiquetas.total), 0)).where(
            col == id_, GeneracionEtiquetas.estado == "GENERADA")) or 0
    return {"tipos": [{**x, "disenos": list(x["disenos"].values()), "problemas": x["problemas"][:50],
                       "con_problemas": len(x["problemas"])} for x in por_tipo.values()],
            "total": plan["total"], "problemas": plan["problemas"], "ya_generadas": generadas,
            "etiquetas_reales": pl_permite_reales(pl) if pl is not None else True}
