"""Generación de etiquetas desde una OC (o desde artículos), su historial y
la reproducción exacta de un lote anterior.

Flujo: `plan()` arma los grupos (orden, línea, unidad, bulto o cantidad
manual), elige la plantilla de cada uno por prioridad, cuenta las etiquetas y
revisa cada grupo con sus datos reales (campos obligatorios de la familia,
campos vacíos, códigos inválidos, textos que no caben…). `generar()` repite
el plan, se detiene ante un error y pide aceptar expresamente las
advertencias; luego guarda el lote con la versión exacta y la instantánea de
los valores de cada grupo y produce el archivo.

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

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errores import ErrorNegocio
from app.modelos import (
    Articulo,
    FamiliaEtiquetado,
    GeneracionEtiquetas,
    GeneracionItem,
    OrdenCompra,
    PlantillaEtiqueta,
    PosicionOC,
    Usuario,
    VersionPlantilla,
)
from app.modulos.acceso.permisos import exigir, proveedor_filtro
from app.modulos.comun.historial import registrar
from app.modulos.etiquetado import asignaciones, campos, datos, familias, plantillas, render, salidas
from app.modulos.etiquetado import diseno as svc_diseno

# Unidades que se miden en piezas: se puede imprimir una etiqueta por unidad
UNIDADES_CONTABLES = {"UN", "PAR", "PZ", "PZA", "CJ", "PK", "PAQ", "JGO", "SET", "DOC", "EA", "PCS"}
FORMATOS = {"PDF": "application/pdf", "PNG": "image/png", "SVG": "image/svg+xml", "ZIP": "application/zip"}


@dataclass
class Grupo:
    """Etiquetas iguales salvo su número: un origen y una plantilla."""
    clave: str
    referencia: str
    cantidad: int
    articulo: Articulo | None = None
    posicion: PosicionOC | None = None
    bulto: campos.Bulto | None = None
    eleccion: asignaciones.Eleccion | None = None
    version: VersionPlantilla | None = None
    valores: dict = field(default_factory=dict)
    problemas: list = field(default_factory=list)

    def problema(self, nivel: str, codigo: str, mensaje: str) -> None:
        self.problemas.append({"nivel": nivel, "codigo": codigo, "mensaje": mensaje, "elemento": None})

    @property
    def errores(self):
        return [p for p in self.problemas if p["nivel"] == "error"]

    @property
    def advertencias(self):
        return [p for p in self.problemas if p["nivel"] == "advertencia"]

    def dict(self) -> dict:
        e = self.eleccion
        p = self.version.plantilla if self.version else (e.plantilla if e else None)
        fam = self.articulo.familia_efectiva if self.articulo else None
        return {"clave": self.clave, "referencia": self.referencia, "cantidad": self.cantidad,
                "articulo_id": self.articulo.id if self.articulo else None,
                "posicion_id": self.posicion.id if self.posicion else None,
                "bulto": self.bulto.numero if self.bulto else None, "familia": fam.nombre if fam else None,
                "plantilla_id": p.id if p else None, "plantilla": p.nombre if p else None,
                "version_id": self.version.id if self.version else None, "version": self.version.numero if self.version else None,
                "version_estado": self.version.estado if self.version else None,
                "nivel": e.nivel if e else None, "motivo": e.motivo if e else None,
                "candidatas": [{"plantilla_id": c.id, "plantilla": c.nombre} for c in e.candidatas] if e else [],
                "problemas": self.problemas}


def _cantidad_manual(v, defecto: int = 1) -> int:
    try:
        n = int(v)
    except (TypeError, ValueError):
        return defecto
    return n


def _grupos(db: Session, user: Usuario, pedido: dict) -> tuple[OrdenCompra | None, str, str, list[Grupo]]:
    modalidad = (pedido.get("modalidad") or "").upper()
    unidad = (pedido.get("unidad") or "").upper()
    if modalidad not in campos.POR_MODALIDAD:
        raise ErrorNegocio("Choose the data mode.", 422, "validacion")
    if unidad not in plantillas.UNIDADES_VALIDAS[modalidad]:
        raise ErrorNegocio("That label unit does not apply to this data mode.", 422, "validacion")
    manuales = {str(k): v for k, v in (pedido.get("cantidades") or {}).items()}
    oc = datos.cargar_oc(db, user, pedido["oc_id"]) if pedido.get("oc_id") else None
    if modalidad != "ARTICULO" and oc is None:
        raise ErrorNegocio("Choose the purchase order.", 422, "validacion")
    grupos: list[Grupo] = []
    if modalidad == "ARTICULO":
        for x in pedido.get("articulos") or []:
            a = datos.cargar_articulo(db, user, x.get("articulo_id"))
            grupos.append(Grupo(f"a{a.id}", a.sku, _cantidad_manual(x.get("cantidad")), articulo=a))
        if not grupos:
            raise ErrorNegocio("Choose the items to label.", 422, "validacion")
        return oc, modalidad, unidad, grupos
    if modalidad == "OC" and unidad in ("ORDEN", "MANUAL"):
        n = _cantidad_manual(manuales.get("oc", pedido.get("cantidad", 1)))
        return oc, modalidad, unidad, [Grupo("oc", oc.numero, n)]
    if unidad == "BULTO":
        lista = campos.bultos(db, oc.id)
        if not lista:
            raise ErrorNegocio("The PO has no packing lists with packages yet: label by order or by line.", 422, "sin_bultos")
        if modalidad == "OC":
            return oc, modalidad, unidad, [Grupo(f"b{b.numero}", f"{b.valores['bulto.packing_list']} · {b.numero}/{b.total}", 1, bulto=b)
                                           for b in lista]
    posiciones = campos.posiciones(db, oc.id)
    elegidas = set(pedido.get("posiciones") or [])
    if elegidas:
        posiciones = [p for p in posiciones if p.id in elegidas]
    else:
        posiciones = [p for p in posiciones if not p.bloqueada]
    if not posiciones:
        raise ErrorNegocio("Choose the PO lines to label.", 422, "validacion")
    if unidad == "BULTO":
        por_posicion = {p.id: p for p in posiciones}
        for b in campos.bultos(db, oc.id):
            for pid in b.posiciones:
                if pid in por_posicion:
                    p = por_posicion[pid]
                    grupos.append(Grupo(f"b{b.numero}-p{p.id}", f"{p.posicion} · {p.codigo_articulo} · {b.numero}/{b.total}", 1,
                                        articulo=p.articulo, posicion=p, bulto=b))
        return oc, modalidad, unidad, grupos
    for p in posiciones:
        ref = f"{p.posicion} · {p.codigo_articulo}"
        if unidad == "LINEA":
            n = 1
        elif unidad == "MANUAL":
            n = _cantidad_manual(manuales.get(str(p.id)), 0)
        else:  # UNIDAD
            cant = float(p.cantidad or 0)
            n = int(cant) if cant == int(cant) else math.ceil(cant)
        g = Grupo(f"p{p.id}", ref, n, articulo=p.articulo, posicion=p)
        if unidad == "UNIDAD" and ((p.unidad or "").upper() not in UNIDADES_CONTABLES or float(p.cantidad or 0) != int(p.cantidad or 0)):
            g.problema("error", "unidad_no_contable",
                       f"The line is in {p.unidad} ({float(p.cantidad or 0):g}): it cannot be labeled per unit; use lines, packages or a manual quantity.")
        grupos.append(g)
    return oc, modalidad, unidad, grupos


def _version_de(db: Session, plantilla: PlantillaEtiqueta, prueba: bool) -> VersionPlantilla | None:
    """La vigente aprobada; en una prueba, la última versión (aunque sea un borrador)."""
    if prueba:
        return plantilla.versiones[-1] if plantilla.versiones else None
    return plantilla.vigente


def plan(db: Session, user: Usuario, pedido: dict) -> dict:
    """Qué se va a generar, con qué plantilla y versión, cuántas etiquetas y qué problemas hay."""
    exigir(user, "etiquetas.generar")
    prueba = bool(pedido.get("prueba"))
    if prueba:
        exigir(user, "etiquetas.disenar")
    oc, modalidad, unidad, grupos = _grupos(db, user, pedido)
    forzada = plantillas.cargar(db, pedido["plantilla_id"]) if pedido.get("plantilla_id") else None
    if forzada and (forzada.modalidad != modalidad or forzada.estado != "ACTIVA"):
        raise ErrorNegocio("The chosen design is of another data mode or is archived.", 422, "validacion")
    elegidas = {str(k): v for k, v in (pedido.get("elegidas") or {}).items()}
    organizacion = campos.valores_organizacion(db)
    tipos = {c.clave: c.tipo for c in campos.catalogo(db, modalidad)}
    previas = _previas(db, oc, grupos)
    for g in grupos:
        if g.cantidad < 1:
            g.problema("error", "cantidad", "Enter how many labels (1 or more).")
        if forzada:
            g.eleccion = asignaciones.Eleccion(plantilla=forzada, nivel="ELEGIDA", motivo="Chosen by the user for this batch.")
        else:
            clave_eleccion = f"a{g.articulo.id}" if g.articulo else "oc"
            g.eleccion = asignaciones.resolver(db, modalidad, g.articulo, oc, elegidas.get(clave_eleccion))
        e = g.eleccion
        if e.plantilla is None:
            if e.ambigua:
                g.problema("error", "elegir_plantilla", "Several designs apply with the same priority: choose one.")
            else:
                pendientes = ", ".join(p.nombre for p in e.sin_aprobar)
                g.problema("error", "sin_plantilla", f"No approved design applies{f' (pending approval: {pendientes})' if pendientes else ''}.")
            continue
        g.version = _version_de(db, e.plantilla, prueba)
        if g.version is None:
            g.problema("error", "sin_plantilla", "The design has no approved version.")
            continue
        for aviso in e.avisos:
            g.problema("advertencia", "familia", aviso)
        if g.posicion is not None and g.articulo is None:
            g.problema("advertencia", "sin_articulo", "The PO line is not linked to an item of the master data: only the line data is printed.")
        g.valores = datos.valores(db, modalidad, g.articulo, oc, g.posicion, g.bulto, organizacion)
        fam = g.articulo.familia_efectiva if g.articulo else None
        for faltante in familias.faltantes(db, fam, g.valores):
            g.problema("error", "dato_obligatorio", f"The family {fam.nombre} requires {faltante}, which is empty.")
        lz = render.componer(g.version.diseno, {**g.valores, "etiqueta.numero": 1, "etiqueta.total": g.cantidad,
                                               "etiqueta.numero_lote": 1, "etiqueta.total_lote": 1}, tipos,
                             plantillas.imagen_adjunta(db))
        g.problemas += lz.problemas
        if g.clave in previas:
            p = previas[g.clave]
            g.problema("advertencia", "ya_generada",
                       f"Labels for this were already generated on {p['fecha']:%Y-%m-%d} by {p['usuario']} ({p['cantidad']}).")
    total = sum(g.cantidad for g in grupos if g.cantidad > 0)
    general = []
    if total > settings.ETIQUETAS_MAXIMO_LOTE:
        general.append({"nivel": "error", "codigo": "lote_grande", "elemento": None,
                        "mensaje": f"{total} labels exceed the limit of {settings.ETIQUETAS_MAXIMO_LOTE} per batch: split the batch."})
    errores = sum(len(g.errores) for g in grupos) + len([p for p in general if p["nivel"] == "error"])
    return {"oc_id": oc.id if oc else None, "oc": oc.numero if oc else None, "modalidad": modalidad, "unidad": unidad,
            "prueba": prueba, "total": total, "grupos": [g.dict() for g in grupos], "problemas": general,
            "errores": errores, "advertencias": sum(len(g.advertencias) for g in grupos),
            "puede_generar": errores == 0 and total > 0, "_grupos": grupos}


def _previas(db: Session, oc: OrdenCompra | None, grupos: list[Grupo]) -> dict:
    """Etiquetas ya generadas (no de prueba) para los mismos orígenes: evita duplicar sin querer."""
    if oc is None:
        return {}
    res = {}
    filas = db.execute(select(GeneracionItem.posicion_id, GeneracionItem.referencia, GeneracionEtiquetas.creada_en,
                              GeneracionEtiquetas.creada_por, GeneracionItem.cantidad, GeneracionEtiquetas.unidad)
                       .join(GeneracionEtiquetas, GeneracionEtiquetas.id == GeneracionItem.generacion_id)
                       .where(GeneracionEtiquetas.oc_id == oc.id, GeneracionEtiquetas.estado == "GENERADA")
                       .order_by(GeneracionEtiquetas.creada_en.desc()))
    usuarios = {}
    for pid, ref, fecha, uid, cant, unidad in filas:
        for g in grupos:
            mismo = (g.posicion is not None and g.posicion.id == pid and g.bulto is None and unidad != "BULTO") or \
                    (g.bulto is not None and g.referencia == ref) or (g.clave == "oc" and unidad in ("ORDEN", "MANUAL") and pid is None)
            if mismo and g.clave not in res:
                if uid not in usuarios:
                    u = db.get(Usuario, uid) if uid else None
                    usuarios[uid] = (u.nombre or u.email) if u else "—"
                res[g.clave] = {"fecha": fecha, "usuario": usuarios[uid], "cantidad": cant}
    return res


# ---- Generar ---------------------------------------------------------------------------------
def _publico(r: dict) -> dict:
    return {k: v for k, v in r.items() if not k.startswith("_")}


def generar(db: Session, user: Usuario, pedido: dict) -> dict:
    formato = (pedido.get("formato") or "PDF").upper()
    if formato not in FORMATOS:
        raise ErrorNegocio("Choose PDF, PNG, SVG or ZIP.", 422, "validacion")
    p = plan(db, user, pedido)
    if p["errores"]:
        raise ErrorNegocio("Some labels cannot be generated: fix the errors first.", 422, "etiquetas_con_errores",
                           [{"campo": g["referencia"], "mensaje": x["mensaje"]} for g in p["grupos"] for x in g["problemas"]
                            if x["nivel"] == "error"][:50] + [{"campo": "lote", "mensaje": x["mensaje"]} for x in p["problemas"]])
    advertencias = [{"referencia": g["referencia"], "mensaje": x["mensaje"]} for g in p["grupos"] for x in g["problemas"]
                    if x["nivel"] == "advertencia"]
    if advertencias and not pedido.get("aceptar_advertencias"):
        raise ErrorNegocio("There are warnings: review them and confirm to generate anyway.", 409, "confirmar_advertencias",
                           [{"campo": a["referencia"], "mensaje": a["mensaje"]} for a in advertencias[:50]])
    grupos: list[Grupo] = p["_grupos"]
    hoja = pedido.get("hoja")
    if hoja is not None:
        hoja = svc_diseno.Hoja.model_validate(hoja).model_dump()
    g0 = GeneracionEtiquetas(oc_id=p["oc_id"], modalidad=p["modalidad"], unidad=p["unidad"], formato=formato,
                             estado="PRUEBA" if p["prueba"] else "GENERADA", total=p["total"], creada_por=user.id,
                             advertencias=advertencias[:200],
                             parametros={"posiciones": pedido.get("posiciones"), "cantidades": pedido.get("cantidades"),
                                         "plantilla_id": pedido.get("plantilla_id"), "elegidas": pedido.get("elegidas"),
                                         "hoja": hoja, "dpi": pedido.get("dpi")})
    # El logo de la organización se guarda una vez por lote (si algún diseño lo usa), no en cada etiqueta
    if any("organizacion.logo" in svc_diseno.campos_usados(g.version.diseno) for g in grupos):
        g0.parametros = {**g0.parametros, "logo": campos.valores_organizacion(db).get("organizacion.logo")}
    db.add(g0)
    db.flush()
    for g in grupos:
        usados = svc_diseno.campos_usados(g.version.diseno) | {"etiqueta.fecha"}
        fam = g.articulo.familia_efectiva.id if g.articulo and g.articulo.familia_efectiva else None
        db.add(GeneracionItem(generacion_id=g0.id, plantilla_id=g.version.plantilla_id, version_id=g.version.id,
                              articulo_id=g.articulo.id if g.articulo else None, posicion_id=g.posicion.id if g.posicion else None,
                              familia_id=fam, referencia=g.referencia[:120], cantidad=g.cantidad,
                              valores={k: g.valores.get(k) for k in sorted(usados) if k != "organizacion.logo"
                                       and (not k.startswith("etiqueta.") or k == "etiqueta.fecha")},
                              motivo=(g.eleccion.motivo or "")[:200] if g.eleccion else None))
    db.flush()
    db.refresh(g0)
    contenido, nombre, _ = _producir(db, g0, formato)
    g0.archivo, g0.sha256 = nombre, hashlib.sha256(contenido).hexdigest()
    db.flush()
    registrar(db, user, "generacion_etiquetas", g0.id, "generar",
              {"oc": p["oc"], "total": g0.total, "formato": formato, "estado": g0.estado,
               "versiones": sorted({f"{g.version.plantilla.nombre} v{g.version.numero}" for g in grupos})})
    return dict_generacion(db, g0, completo=True)


def _lienzos(db: Session, gen: GeneracionEtiquetas) -> list[tuple[render.Lienzo, str]]:
    """Las etiquetas del lote dibujadas desde las versiones y valores guardados."""
    tipos = {c.clave: c.tipo for c in campos.catalogo(db, gen.modalidad)}
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
            lz = render.componer(v.diseno, {**valores, "etiqueta.numero": n, "etiqueta.total": it.cantidad,
                                            "etiqueta.numero_lote": n_lote, "etiqueta.total_lote": gen.total},
                                 tipos, imagenes, prueba=gen.estado == "PRUEBA")
            res.append((lz, f"{it.referencia or it.id}-{n}"))
    return res


def _seguro(nombre: str) -> str:
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in nombre)[:80]


def _producir(db: Session, gen: GeneracionEtiquetas, formato: str) -> tuple[bytes, str, str]:
    lienzos = _lienzos(db, gen)
    base = _seguro(f"labels-{gen.id}" + (f"-{db.get(OrdenCompra, gen.oc_id).numero}" if gen.oc_id else ""))
    hoja = (gen.parametros or {}).get("hoja")
    if hoja is None:
        v = db.get(VersionPlantilla, gen.items[0].version_id) if gen.items else None
        mismas = len({(lz.ancho, lz.alto) for lz, _ in lienzos}) == 1
        hoja = v.diseno.get("hoja") if v and mismas else None
    dpi = (gen.parametros or {}).get("dpi")
    if formato == "PDF":
        return salidas.pdf([lz for lz, _ in lienzos], hoja, base), f"{base}.pdf", FORMATOS["PDF"]
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
            poner(z, f"{base}.pdf", salidas.pdf([lz for lz, _ in lienzos], hoja, base))
        for i, (lz, nombre) in enumerate(lienzos, start=1):
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
    r = {"id": g.id, "oc_id": g.oc_id, "oc": oc.numero if oc else None, "modalidad": g.modalidad, "unidad": g.unidad,
         "formato": g.formato, "estado": g.estado, "total": g.total, "archivo": g.archivo, "sha256": g.sha256,
         "creada_por": (u.nombre or u.email) if u else None, "creada_en": g.creada_en, "versiones": list(versiones.values()),
         "grupos": len(g.items), "advertencias": g.advertencias or []}
    if completo:
        familias_ = {f.id: f.nombre for f in db.scalars(select(FamiliaEtiquetado))}
        r["items"] = [{"id": it.id, "referencia": it.referencia, "cantidad": it.cantidad, "articulo_id": it.articulo_id,
                       "posicion_id": it.posicion_id, "familia": familias_.get(it.familia_id),
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
    for col, v in (("articulo_id", articulo_id), ("familia_id", familia_id), ("plantilla_id", plantilla_id), ("version_id", version_id)):
        if v:
            c = c.where(GeneracionEtiquetas.id.in_(select(GeneracionItem.generacion_id).where(getattr(GeneracionItem, col) == v)))
    total = db.scalar(select(func.count()).select_from(c.subquery())) or 0
    filas = db.scalars(c.order_by(GeneracionEtiquetas.creada_en.desc(), GeneracionEtiquetas.id.desc())
                       .offset((page - 1) * size).limit(size)).all()
    return {"total": total, "items": [dict_generacion(db, g) for g in filas]}


def archivo(db: Session, user: Usuario, generacion_id: int, formato: str | None = None) -> tuple[bytes, str, str, bool]:
    """El archivo del lote, dibujado de nuevo desde su versión e instantánea; y si es idéntico al original."""
    g = cargar(db, user, generacion_id)
    formato = (formato or g.formato).upper()
    if formato not in FORMATOS:
        raise ErrorNegocio("Choose PDF, PNG, SVG or ZIP.", 422, "validacion")
    contenido, nombre, mime = _producir(db, g, formato)
    identico = formato == g.formato and hashlib.sha256(contenido).hexdigest() == g.sha256
    registrar(db, user, "generacion_etiquetas", g.id, "descargar", {"formato": formato, "identico": identico})
    return contenido, nombre, mime, identico


def resumen_oc(db: Session, user: Usuario, oc_id: int) -> dict:
    """Lo que el asistente muestra de una OC: sus líneas con artículo, familia y
    diseño que se usaría, sus bultos y las etiquetas ya generadas."""
    exigir(user, "etiquetas.generar")
    oc = datos.cargar_oc(db, user, oc_id)
    lineas = []
    for p in campos.posiciones(db, oc.id):
        a = p.articulo
        eleccion = asignaciones.resolver(db, "OC_ARTICULO", a, oc)
        lineas.append({"id": p.id, "posicion": p.posicion, "codigo": p.codigo_articulo, "descripcion": p.descripcion,
                       "talla": p.talla, "color": p.color, "cantidad": float(p.cantidad or 0), "unidad": p.unidad,
                       "bloqueada": p.bloqueada, "articulo_id": a.id if a else None,
                       "familia": a.familia_efectiva.nombre if a and a.familia_efectiva else None,
                       "plantilla": eleccion.dict()})
    generadas = db.scalar(select(func.count()).select_from(GeneracionEtiquetas).where(
        GeneracionEtiquetas.oc_id == oc.id, GeneracionEtiquetas.estado == "GENERADA")) or 0
    return {"oc": {"id": oc.id, "numero": oc.numero, "proveedor": oc.proveedor.nombre, "estado": oc.estado},
            "lineas": lineas, "bultos": len(campos.bultos(db, oc.id)), "generaciones": generadas,
            "plantilla_oc": asignaciones.resolver(db, "OC", None, oc).dict()}
