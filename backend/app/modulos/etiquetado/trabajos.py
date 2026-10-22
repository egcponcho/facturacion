"""Trabajos de etiquetado: el asistente único de generación.

Todas las entradas (detalle de una OC, varias OC desde su lista, artículos,
una lista de empaque, el centro de etiquetado) crean un trabajo con este
servicio. Cada paso del asistente se guarda como borrador (`actualizar`), así
se puede salir y seguir después.

- Un trabajo imprime uno o varios tipos de etiqueta (colgante, precio, caja…):
  cada registro es un artículo, bulto o documento con un tipo.
- `validar` arma los registros con el mismo cálculo de la generación
  (generacion.planear: diseño de cada uno, campos lógicos, empaque, dibujo) y
  los guarda con su diseño, por qué y problemas clasificados; verifica
  leyendo los códigos de una etiqueta de muestra por diseño.
- `generar` vuelve a validar con los datos de ese momento y genera los
  registros listos con ese mismo cálculo (no lo repite): todos o, si la
  empresa lo permite y se pide, solo los listos (generación parcial).
  Cada OC (o la lista de empaque, o los artículos) es una ejecución
  (generaciones_etiqueta.trabajo_id) con su versión e instantánea exactas.
  Desde cierto tamaño se genera en segundo plano y el avance se lee de la base.
- `generar` de nuevo, tras corregir, genera solo lo que falta (reintento).
- `archivo` arma el ZIP con las carpetas y nombres configurados y un resumen.
- Generado, descargado e impreso son estados distintos: impreso solo con una
  confirmación expresa de quien imprimió (`confirmar_impresion`).
"""
from __future__ import annotations

import contextvars
import csv
import hashlib
import io
import json
import logging
import os
import re
import socket
import threading
import uuid
import zipfile
from datetime import datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.empresa import regla
from app.core.errores import ErrorNegocio
from app.core.organizacion import fijar
from app.modelos import (
    GeneracionEtiquetas,
    OrdenCompra,
    PlantillaEtiqueta,
    PosicionOC,
    TipoEtiqueta,
    TrabajoEtiquetas,
    TrabajoRegistro,
    Usuario,
    VersionPlantilla,
    ahora,
)
from app.modelos.etiquetado import ORIGENES_TRABAJO
from app.modulos.acceso import visibilidad
from app.modulos.acceso.permisos import exigir, proveedor_filtro
from app.modulos.comun.historial import registrar
from app.modulos.etiquetado import campos, datos, generacion, plantillas, render, salidas, verificacion

MAX_ORDENES = 200
MAX_ARTICULOS = 5000
MAX_CANTIDAD = 100000  # etiquetas que se pueden pedir a mano para un registro
MAX_MUESTRAS = 20  # etiquetas que se leen con el lector al validar (una por diseño, hasta este tope)
EDITABLES = ("BORRADOR", "VALIDADO", "PARCIAL", "ERROR")
# Qué se puede etiquetar desde cada origen
SUJETOS_DE = {"OC": ("ARTICULO", "BULTO", "DOCUMENTO"), "ARTICULOS": ("ARTICULO",), "PACKING": ("ARTICULO", "BULTO", "DOCUMENTO")}
CARPETAS = ("oc", "plantilla", "familia", "packing_list")
MARCADORES = ("oc", "referencia", "sku", "n", "total", "i", "plantilla", "serie", "bulto")
CONTENIDOS = ("PDF", "PNG", "SVG")
# Cómo se reparten las etiquetas en archivos dentro del ZIP (lo elige el usuario):
# una por archivo, un PDF por plantilla y versión, un PDF por carpeta (sin
# mezclar diseños: si una carpeta tiene varios, uno por diseño) o un único PDF
# (solo si todas miden lo mismo). PNG y SVG siempre van una por archivo.
AGRUPACIONES = ("etiqueta", "plantilla", "carpeta", "unico")
PARAMETROS = ("oc_ids", "posiciones", "cantidades", "articulos", "pl_id", "tipo_empaque_id", "niveles", "familia_id", "tipos", "prueba",
              "elegidas", "manuales", "formato", "hoja", "dpi", "zip", "cantidad", "nota")


# ---- Acceso -------------------------------------------------------------------------------------
def _alcance(user: Usuario):
    """Un proveedor ve solo los trabajos que creó; el equipo interno, todos los de la organización."""
    return [] if proveedor_filtro(user) is None else [TrabajoEtiquetas.creado_por == user.id]


def cargar(db: Session, user: Usuario, trabajo_id: int, bloquear: bool = False) -> TrabajoEtiquetas:
    exigir(user, "etiquetas.generar")
    c = select(TrabajoEtiquetas).where(TrabajoEtiquetas.id == trabajo_id, *_alcance(user))
    if bloquear:
        c = c.with_for_update()
    t = db.scalar(c)
    if not t:
        raise ErrorNegocio("The labeling job does not exist.", 404, "no_encontrado")
    return t


def _version(t: TrabajoEtiquetas, datos_: dict) -> None:
    v = datos_.get("version")
    if v is not None and int(v) != t.version:
        raise ErrorNegocio("Someone else changed this labeling job: reload it.", 409, "conflicto_version")


# ---- Parámetros -------------------------------------------------------------------------------
def _validar_zip(z) -> dict:
    if not z:
        return {}
    if not isinstance(z, dict):
        raise ErrorNegocio("Check the ZIP options.", 422, "validacion")
    carpetas = z.get("carpetas") or []
    if not isinstance(carpetas, list) or len(carpetas) > 3 or any(c not in CARPETAS for c in carpetas):
        raise ErrorNegocio("Choose up to 3 folder levels.", 422, "validacion", [{"campo": "zip.carpetas", "mensaje": ", ".join(CARPETAS)}])
    nombre = (z.get("nombre") or "").strip()
    if len(nombre) > 120:
        raise ErrorNegocio("The file name pattern is too long.", 422, "validacion")
    malos = [m for m in re.findall(r"\{(\w+)\}", nombre) if m not in MARCADORES]
    if malos:
        raise ErrorNegocio("The file name pattern uses unknown fields.", 422, "validacion",
                           [{"campo": "zip.nombre", "mensaje": f"Unknown: {', '.join(malos)}. Use: {', '.join(MARCADORES)}."}])
    contenido = (z.get("contenido") or "PDF").upper()
    if contenido not in CONTENIDOS:
        raise ErrorNegocio("Choose PDF, PNG or SVG files inside the ZIP.", 422, "validacion")
    agrupar = _agrupar(contenido, carpetas, z.get("agrupar"))
    sin_valor = (z.get("sin_valor") or "").strip()[:40]
    return {"carpetas": list(carpetas), "nombre": nombre, "contenido": contenido, "agrupar": agrupar,
            **({"sin_valor": sin_valor} if sin_valor else {})}


def _agrupar(contenido: str, carpetas: list, agrupar: str | None) -> str:
    """La agrupación pedida, validada contra el contenido y las carpetas. Sin
    elegir (trabajos anteriores): un PDF por carpeta si hay carpetas y uno por
    plantilla y versión si no; PNG y SVG, uno por etiqueta."""
    if not agrupar:
        return "etiqueta" if contenido != "PDF" else ("carpeta" if carpetas else "plantilla")
    if agrupar not in AGRUPACIONES:
        raise ErrorNegocio("Choose how to group the labels in files.", 422, "validacion",
                           [{"campo": "zip.agrupar", "mensaje": ", ".join(AGRUPACIONES)}])
    if contenido != "PDF" and agrupar != "etiqueta":
        raise ErrorNegocio("PNG and SVG files hold one label each.", 422, "validacion", [{"campo": "zip.agrupar", "mensaje": agrupar}])
    if agrupar == "carpeta" and not carpetas:
        raise ErrorNegocio("Choose at least one folder level to make one PDF per folder.", 422, "validacion",
                           [{"campo": "zip.carpetas", "mensaje": ", ".join(CARPETAS)}])
    if agrupar in ("plantilla", "unico") and carpetas:
        raise ErrorNegocio("Folders are used only with one file per label or one PDF per folder.", 422, "validacion",
                           [{"campo": "zip.carpetas", "mensaje": agrupar}])
    return agrupar


def _entero(v, campo: str, minimo: int = 0, maximo: int = 10**9) -> int:
    """Un entero dentro de un rango o 422 (nunca un 500 por un dato mal escrito)."""
    try:
        n = int(str(v).strip())
    except (TypeError, ValueError):
        raise ErrorNegocio("Write a whole number.", 422, "validacion", [{"campo": campo, "mensaje": str(v)[:40]}]) from None
    if not minimo <= n <= maximo:
        raise ErrorNegocio(f"Write a number from {minimo} to {maximo}.", 422, "validacion", [{"campo": campo, "mensaje": str(n)}])
    return n


def _ids(v, campo: str, maximo: int) -> list[int]:
    if v in (None, ""):
        return []
    if not isinstance(v, list) or len(v) > maximo:
        raise ErrorNegocio(f"Send up to {maximo} ids.", 422, "validacion", [{"campo": campo, "mensaje": ""}])
    return list(dict.fromkeys(_entero(x, campo, 1) for x in v))


def _limpiar(db: Session, user: Usuario, origen: str, p: dict) -> dict:
    """Parámetros del trabajo validados (lo que exista se comprueba dentro del alcance del usuario)."""
    from pydantic import ValidationError

    from app.modulos.etiquetado import diseno as svc_diseno

    res = {k: p[k] for k in PARAMETROS if k in p}
    if "oc_ids" in res:
        ids = _ids(res["oc_ids"], "oc_ids", MAX_ORDENES)
        for i in ids:
            datos.cargar_oc(db, user, i)
        res["oc_ids"] = ids
    if "posiciones" in res:
        res["posiciones"] = _ids(res["posiciones"], "posiciones", MAX_ARTICULOS)
    if "articulos" in res:
        lista = res["articulos"] or []
        if not isinstance(lista, list) or len(lista) > MAX_ARTICULOS:
            raise ErrorNegocio(f"Up to {MAX_ARTICULOS} items per labeling job.", 422, "validacion")
        limpia = []
        for a in lista:
            if not isinstance(a, dict) or "articulo_id" not in a:
                raise ErrorNegocio("Choose the items.", 422, "validacion", [{"campo": "articulos", "mensaje": ""}])
            art = datos.cargar_articulo(db, user, _entero(a["articulo_id"], "articulos", 1))
            n = a.get("cantidad", res.get("cantidad") or 1)
            limpia.append({"articulo_id": art.id, "cantidad": _entero(n, "cantidad", 0, MAX_CANTIDAD)})
        res["articulos"] = limpia
    if "cantidad" in res and res["cantidad"] not in (None, ""):
        res["cantidad"] = _entero(res["cantidad"], "cantidad", 0, MAX_CANTIDAD)
    if "cantidades" in res:
        c = res["cantidades"] or {}
        if not isinstance(c, dict) or len(c) > MAX_ARTICULOS:
            raise ErrorNegocio("Check the quantities.", 422, "validacion", [{"campo": "cantidades", "mensaje": ""}])
        res["cantidades"] = {str(k)[:200]: _entero(v, "cantidades", 0, MAX_CANTIDAD) for k, v in c.items() if v not in (None, "")}
    if "manuales" in res:
        m = res["manuales"] or {}
        if not isinstance(m, dict) or len(m) > 100:
            raise ErrorNegocio("Check the values to write.", 422, "validacion", [{"campo": "manuales", "mensaje": ""}])
        res["manuales"] = {str(k)[:60]: (None if v is None else str(v)[:500]) for k, v in m.items()}
    if res.get("pl_id"):
        res["pl_id"] = _entero(res["pl_id"], "pl_id", 1)
        generacion.cargar_pl(db, user, res["pl_id"])
    if res.get("familia_id") not in (None, ""):
        res["familia_id"] = _entero(res["familia_id"], "familia_id", 1)
    if res.get("tipo_empaque_id") not in (None, ""):
        res["tipo_empaque_id"] = _entero(res["tipo_empaque_id"], "tipo_empaque_id", 1)
    if "niveles" in res:
        # Qué empaques de la lista llevan etiqueta, varios a la vez: 0 = los exteriores, o tipos de empaque
        niveles = res["niveles"] or []
        if not isinstance(niveles, list) or len(niveles) > 20 or not all(str(x).isdigit() for x in niveles):
            raise ErrorNegocio("Choose the package levels.", 422, "validacion")
        res["niveles"] = list(dict.fromkeys(int(x) for x in niveles)) or None
    if "tipos" in res:
        ids = _ids(res["tipos"], "tipos", 200)
        tipos_ = {t.id: t for t in db.scalars(select(TipoEtiqueta).where(TipoEtiqueta.id.in_(ids)))}
        if len(tipos_) != len(ids):
            raise ErrorNegocio("A label type does not exist.", 422, "validacion")
        fuera = [t.nombre for t in tipos_.values() if t.sujeto not in SUJETOS_DE[origen]]
        if fuera:
            raise ErrorNegocio("These labels cannot be printed from here.", 422, "validacion",
                               [{"campo": "tipos", "mensaje": ", ".join(fuera)}])
        res["tipos"] = ids
    if "elegidas" in res:
        elegidas = {}
        if not isinstance(res["elegidas"] or {}, dict):
            raise ErrorNegocio("Check the chosen designs.", 422, "validacion")
        for k, v in (res["elegidas"] or {}).items():
            if v in (None, ""):
                continue
            p = plantillas.cargar(db, _entero(v, "elegidas", 1))
            if p.estado != "ACTIVA":
                raise ErrorNegocio("The design is archived.", 422, "validacion")
            elegidas[str(k)[:200]] = p.id
        res["elegidas"] = elegidas
    if "hoja" in res and res["hoja"] is not None:
        try:
            res["hoja"] = svc_diseno.Hoja.model_validate(res["hoja"]).model_dump()
        except ValidationError:
            raise ErrorNegocio("Check the sheet layout.", 422, "validacion", [{"campo": "hoja", "mensaje": ""}]) from None
    if "dpi" in res and res["dpi"] not in (None, ""):
        res["dpi"] = _entero(res["dpi"], "dpi", 72, 1200)
    if "prueba" in res:
        res["prueba"] = bool(res["prueba"])
    if "nota" in res:
        res["nota"] = (str(res["nota"] or "")).strip()[:300] or None
    if "zip" in res:
        res["zip"] = _validar_zip(res["zip"])
    if "formato" in res and (str(res["formato"] or "PDF")).upper() not in generacion.FORMATOS:
        raise ErrorNegocio("Choose PDF, PNG, SVG or ZIP.", 422, "validacion")
    return res


def _partes(db: Session, t: TrabajoEtiquetas) -> list[tuple[str, dict]]:
    """Un pedido de generación por OC (o uno de artículos o de la lista de empaque) con el prefijo de sus registros."""
    p = t.parametros or {}
    comun = {"origen": t.origen, "tipos": p.get("tipos") or [], "manuales": p.get("manuales") or {},
             "familia_id": p.get("familia_id"), "hoja": p.get("hoja"), "dpi": p.get("dpi"), "zip": p.get("zip"),
             "prueba": bool(p.get("prueba")), "cantidades": {}}
    elegidas = {str(k): v for k, v in (p.get("elegidas") or {}).items()}
    cantidades = {str(k): v for k, v in (p.get("cantidades") or {}).items()}

    def de(prefijo: str, mapa: dict) -> dict:
        return {k.split(":", 1)[1]: v for k, v in mapa.items() if k.startswith(prefijo + ":")}

    if t.origen == "ARTICULOS":
        return [("art", {**comun, "articulos": p.get("articulos") or [], "elegidas": de("art", elegidas),
                         "cantidades": de("art", cantidades)})]
    if t.origen == "PACKING":
        prefijo = f"pl{p.get('pl_id')}"
        return [(prefijo, {**comun, "pl_id": p.get("pl_id"), "tipo_empaque_id": p.get("tipo_empaque_id"),
                           "niveles": p.get("niveles"),
                           "elegidas": de(prefijo, elegidas), "cantidades": de(prefijo, cantidades)})]
    elegidas_pos = set(p.get("posiciones") or [])
    res = []
    for oc_id in p.get("oc_ids") or []:
        prefijo = f"oc{oc_id}"
        pedido = {**comun, "oc_id": oc_id, "elegidas": de(prefijo, elegidas), "cantidades": de(prefijo, cantidades)}
        if elegidas_pos:
            de_oc = [i for i in db.scalars(select(PosicionOC.id).where(PosicionOC.oc_id == oc_id)) if i in elegidas_pos]
            if not de_oc:
                continue  # ninguna línea elegida de esta OC
            pedido["posiciones"] = de_oc
        res.append((prefijo, pedido))
    return res


def tipos_por_defecto(db: Session, origen: str) -> list[int]:
    """Los tipos que se imprimen si no se eligen: los obligatorios que aplican al
    origen (o todos los activos que aplican, si ninguno es obligatorio)."""
    activos = list(db.scalars(select(TipoEtiqueta).where(TipoEtiqueta.activo.is_(True),
                                                         TipoEtiqueta.sujeto.in_(SUJETOS_DE[origen]))
                              .order_by(TipoEtiqueta.orden, TipoEtiqueta.id)))
    obligatorios = [t.id for t in activos if t.obligatoria]
    return obligatorios or [t.id for t in activos]


# ---- Alta y borradores -----------------------------------------------------------------------------
def crear(db: Session, user: Usuario, datos_: dict) -> dict:
    exigir(user, "etiquetas.generar")
    origen = (datos_.get("origen") or "").upper()
    if origen not in ORIGENES_TRABAJO:
        raise ErrorNegocio("Choose where the labels come from: purchase orders, items or a packing list.", 422, "validacion")
    parametros = _limpiar(db, user, origen, datos_.get("parametros") or {})
    if not parametros.get("tipos"):
        parametros["tipos"] = tipos_por_defecto(db, origen)
    nombre = (datos_.get("nombre") or "").strip()[:120] or _nombre(db, origen, parametros)
    t = TrabajoEtiquetas(nombre=nombre, origen=origen, estado="BORRADOR", paso=int(datos_.get("paso") or 0),
                         parametros=parametros, resumen={}, creado_por=user.id, version=1)
    db.add(t)
    db.flush()
    registrar(db, user, "trabajo_etiquetas", t.id, "crear", {"origen": origen, "nombre": nombre})
    return detalle(db, user, t.id)


def _nombre(db: Session, origen: str, p: dict) -> str:
    """Un nombre que se reconoce en la lista: los documentos o artículos y la fecha (sin palabras de un idioma)."""
    from app.core.empresa import hoy

    fecha = f"{hoy():%Y-%m-%d}"

    def varios(nombres: list[str], total: int) -> str:
        return ", ".join(nombres[:2]) + (f" (+{total - 2})" if total > 2 else "")

    if origen == "OC":
        ids = p.get("oc_ids") or []
        return f"{varios([db.get(OrdenCompra, i).numero for i in ids[:2]], len(ids))} · {fecha}"
    if origen == "PACKING" and p.get("pl_id"):
        from app.modelos import PackingList

        return f"{db.get(PackingList, p['pl_id']).numero} · {fecha}"
    from app.modelos import Articulo

    arts = p.get("articulos") or []
    return f"{varios([db.get(Articulo, a['articulo_id']).sku for a in arts[:2]], len(arts))} · {fecha}"


def actualizar(db: Session, user: Usuario, trabajo_id: int, datos_: dict) -> dict:
    """Guarda el borrador (parámetros y paso del asistente). Cambiar los
    parámetros invalida la validación anterior."""
    t = cargar(db, user, trabajo_id, bloquear=True)
    _version(t, datos_)
    de_descarga = {"zip", "formato"}  # cómo se descarga: se cambia aunque ya esté generado
    if t.estado not in EDITABLES and set(datos_.get("parametros") or {}) - de_descarga:
        raise ErrorNegocio("This labeling job can no longer be changed.", 409, "estado")
    if "nombre" in datos_:
        t.nombre = (datos_.get("nombre") or "").strip()[:120] or t.nombre
    if "paso" in datos_:
        t.paso = max(int(datos_["paso"] or 0), 0)
    if "parametros" in datos_:
        nuevos = {**(t.parametros or {}), **_limpiar(db, user, t.origen, datos_["parametros"] or {})}
        for k, v in (datos_["parametros"] or {}).items():
            if v is None:
                nuevos.pop(k, None)
        if nuevos != (t.parametros or {}):
            cambia_registros = {k for k in set(nuevos) | set(t.parametros or {})
                                if nuevos.get(k) != (t.parametros or {}).get(k)} - de_descarga
            t.parametros = nuevos
            if t.estado == "VALIDADO" and cambia_registros:
                t.estado = "BORRADOR"
    t.version += 1
    t.actualizado_en = ahora()
    db.flush()
    return detalle(db, user, t.id)


def cancelar(db: Session, user: Usuario, trabajo_id: int) -> dict:
    t = cargar(db, user, trabajo_id, bloquear=True)
    if t.estado == "EN_PROCESO":
        raise ErrorNegocio("The labels are being generated: wait until it finishes.", 409, "estado")
    if t.estado in ("GENERADO",):
        raise ErrorNegocio("The labeling job was already generated.", 409, "estado")
    t.estado = "CANCELADO"
    t.version += 1
    registrar(db, user, "trabajo_etiquetas", t.id, "cancelar", {})
    db.flush()
    return detalle(db, user, t.id)


# ---- Consulta -------------------------------------------------------------------------------------
def _usuario(db: Session, uid: int | None) -> str | None:
    u = db.get(Usuario, uid) if uid else None
    return (u.nombre or u.email) if u else None


def dict_trabajo(db: Session, t: TrabajoEtiquetas) -> dict:
    return {"id": t.id, "nombre": t.nombre, "origen": t.origen, "estado": t.estado, "paso": t.paso, "total": t.total,
            "progreso": t.progreso, "error": t.error, "version": t.version, "creado_por": _usuario(db, t.creado_por),
            "creado_en": t.creado_en, "actualizado_en": t.actualizado_en, "validado_en": t.validado_en,
            "generado_en": t.generado_en, "conteo": (t.resumen or {}).get("conteo", {})}


def _dict_registro(r: TrabajoRegistro, plantillas_: dict, versiones: dict, tipos_: dict) -> dict:
    return {"id": r.id, "clave": r.clave, "referencia": r.referencia, "oc_id": r.oc_id, "posicion_id": r.posicion_id,
            "articulo_id": r.articulo_id, "pl_id": r.pl_id, "tipo_etiqueta_id": r.tipo_etiqueta_id,
            "tipo": tipos_.get(r.tipo_etiqueta_id), "plantilla_id": r.plantilla_id,
            "plantilla": plantillas_.get(r.plantilla_id), "version_id": r.version_id, "version": versiones.get(r.version_id),
            "uso_id": r.uso_id, "cantidad": r.cantidad, "estado": r.estado, "problemas": r.problemas or [],
            "motivo": r.motivo, "generacion_id": r.generacion_id}


def dict_ejecucion(db: Session, g: GeneracionEtiquetas) -> dict:
    oc = db.get(OrdenCompra, g.oc_id) if g.oc_id else None
    return {"id": g.id, "oc": oc.numero if oc else None, "total": g.total, "formato": g.formato, "estado": g.estado,
            "sha256": g.sha256, "creada_en": g.creada_en, "creada_por": _usuario(db, g.creada_por),
            "descargas": g.descargas or 0, "descargada_en": g.descargada_en, "impresa_en": g.impresa_en,
            "impresa_por": _usuario(db, g.impresa_por), "impresion": g.impresion,
            "anulada_en": g.anulada_en, "anulada_por": _usuario(db, g.anulada_por), "motivo_anulacion": g.motivo_anulacion,
            "reimpresiones": [{**x, "por": _usuario(db, x.get("por"))} for x in (g.reimpresiones or [])],
            "grupos": [{"id": it.id, "referencia": it.referencia, "cantidad": it.cantidad} for it in g.items],
            "situacion": "ANULADA" if g.anulada_en else "IMPRESA" if g.impresa_en else ("DESCARGADA" if g.descargas else "GENERADA")}


def detalle(db: Session, user: Usuario, trabajo_id: int) -> dict:
    t = cargar(db, user, trabajo_id)
    ids_p = {r.plantilla_id for r in t.registros if r.plantilla_id}
    ids_v = {r.version_id for r in t.registros if r.version_id}
    plantillas_ = {p.id: p.nombre for p in db.scalars(select(PlantillaEtiqueta).where(PlantillaEtiqueta.id.in_(ids_p)))} if ids_p else {}
    versiones = {v.id: v.numero for v in db.scalars(select(VersionPlantilla).where(VersionPlantilla.id.in_(ids_v)))} if ids_v else {}
    tipos_ = dict(db.execute(select(TipoEtiqueta.id, TipoEtiqueta.nombre)).all())
    ejecuciones = db.scalars(select(GeneracionEtiquetas).where(GeneracionEtiquetas.trabajo_id == t.id)
                             .order_by(GeneracionEtiquetas.id))
    return {**dict_trabajo(db, t), "parametros": t.parametros or {}, "resumen": t.resumen or {},
            "registros": [_dict_registro(r, plantillas_, versiones, tipos_) for r in t.registros],
            "ejecuciones": [dict_ejecucion(db, g) for g in ejecuciones],
            "permite_parcial": bool(regla("ETIQUETAS_GENERACION_PARCIAL")),
            "asincrono_desde": int(regla("ETIQUETAS_ASINCRONO_DESDE"))}


def estado(db: Session, user: Usuario, trabajo_id: int) -> dict:
    """Lo que el asistente consulta mientras se genera en segundo plano."""
    return dict_trabajo(db, cargar(db, user, trabajo_id))


def listar(db: Session, user: Usuario, estado_: str | None = None, q: str | None = None, page: int = 1, size: int = 25) -> dict:
    exigir(user, "etiquetas.generar")
    c = select(TrabajoEtiquetas).where(*_alcance(user))
    if estado_:
        c = c.where(TrabajoEtiquetas.estado.in_([x.strip().upper() for x in estado_.split(",") if x.strip()]))
    if q:
        c = c.where(TrabajoEtiquetas.nombre.ilike(f"%{q.strip()}%"))
    total = db.scalar(select(func.count()).select_from(c.subquery())) or 0
    filas = db.scalars(c.order_by(TrabajoEtiquetas.actualizado_en.desc(), TrabajoEtiquetas.id.desc())
                       .offset((page - 1) * size).limit(size))
    return {"total": total, "items": [dict_trabajo(db, t) for t in filas]}


# ---- Validación ------------------------------------------------------------------------------------
def _estado_registro(problemas: list) -> str:
    niveles = {p["nivel"] for p in problemas}
    return "ERROR" if "error" in niveles else ("ADVERTENCIA" if "advertencia" in niveles else "LISTO")


def _muestras(db: Session, grupos: list, vistas: set) -> None:
    """Lee con el lector los códigos de una etiqueta por diseño (hasta MAX_MUESTRAS en el trabajo)."""
    for g in grupos:
        if len(vistas) >= MAX_MUESTRAS or g.version is None or g.version.id in vistas or g.errores:
            continue
        vistas.add(g.version.id)
        valores = {**g.valores, "etiqueta.numero": 1, "etiqueta.total": g.cantidad, "etiqueta.numero_lote": 1,
                   "etiqueta.total_lote": 1}
        tipos = campos.tipos(db, g.tipo.sujeto)
        lz = render.componer(g.version.diseno, valores, tipos, plantillas.imagen_adjunta(db))
        g.problemas += verificacion.verificar(lz, g.version.diseno, valores, tipos)


def validar(db: Session, user: Usuario, trabajo_id: int) -> dict:
    t = cargar(db, user, trabajo_id, bloquear=True)
    if t.estado in ("EN_PROCESO", "CANCELADO"):
        raise ErrorNegocio("This labeling job cannot be validated now.", 409, "estado")
    _validar(db, user, t)
    t.version += 1
    db.flush()
    registrar(db, user, "trabajo_etiquetas", t.id, "validar", {"total": t.total, "conteo": t.resumen.get("conteo")})
    return detalle(db, user, t.id)


# Datos del artículo que se pueden completar desde el trabajo (campo del maestro de artículos).
# Los que identifican al artículo (SKU, valores de variante) no: se corrigen en su ficha.
COMPLETABLES = {"articulo.codigo_barras": "codigo_barras", "articulo.codigo_proveedor": "codigo_proveedor",
                "articulo.peso_unitario": "peso_unitario", "articulo.unidad": "unidad"}
MAX_COMPLETAR = 200


def completar(db: Session, user: Usuario, trabajo_id: int, campo: str, valores: dict) -> dict:
    """Escribe en el maestro de artículos el dato que falta ({articulo_id: valor}: cada artículo el suyo), con
    las mismas validaciones, permisos e historial que Datos maestros, y vuelve a revisar el trabajo."""
    from app.modulos.maestros import catalogos

    t = cargar(db, user, trabajo_id, bloquear=True)
    if t.estado in ("EN_PROCESO", "CANCELADO", "GENERADO"):
        raise ErrorNegocio("This labeling job cannot be changed now.", 409, "estado")
    columna = COMPLETABLES.get(campo)
    if not columna:
        raise ErrorNegocio("This datum cannot be completed from here: change it where it comes from.", 422, "validacion",
                           [{"campo": "campo", "mensaje": str(campo)[:80]}])
    if not isinstance(valores, dict) or not valores or len(valores) > MAX_COMPLETAR:
        raise ErrorNegocio(f"Write the value of each item (up to {MAX_COMPLETAR}).", 422, "validacion")
    # Solo artículos de este trabajo a los que les falta ese dato
    faltan = {r.articulo_id for r in t.registros
              if r.articulo_id and r.estado != "GENERADO" and any(p.get("campo") == campo for p in r.problemas or [])}
    try:
        pedidos = {int(k): v for k, v in valores.items()}
    except (TypeError, ValueError):
        raise ErrorNegocio("Check the items.", 422, "validacion") from None
    fuera = sorted(set(pedidos) - faltan)
    if fuera:
        raise ErrorNegocio("Some items are not in this job or do not lack this datum.", 422, "validacion",
                           [{"campo": "valores", "mensaje": ", ".join(map(str, fuera[:10]))}])
    for aid, valor in sorted(pedidos.items()):
        if valor in (None, ""):
            continue
        try:
            catalogos.actualizar(db, user, "articulos", aid, {columna: valor})
        except ErrorNegocio as e:  # qué artículo, en el detalle (el mensaje se traduce tal cual)
            from app.modelos import Articulo

            a = db.get(Articulo, aid)
            raise ErrorNegocio(e.mensaje, e.status, e.codigo,
                               [*(e.detalle if isinstance(e.detalle, list) else []), {"campo": "articulo", "mensaje": a.sku if a else str(aid)}]) from None
    _validar(db, user, t)
    t.version += 1
    db.flush()
    registrar(db, user, "trabajo_etiquetas", t.id, "completar", {"campo": campo, "articulos": len(pedidos)})
    return detalle(db, user, t.id)


# Lo que se revisó de cada registro: los valores que lee su diseño. No cuentan los que cambian
# solos en cada revisión (fecha y número de la etiqueta, serie, contexto del trabajo).
VOLATILES = ("etiqueta.", "contexto.")


def _revisado(g) -> dict | None:
    if g.version is None:
        return None
    datos = {}
    for c in sorted(generacion.svc_diseno.campos_usados(g.version.diseno)):
        if c.startswith(VOLATILES):
            continue
        v = g.valores.get(c)
        if isinstance(v, (list, dict)):  # una tabla (contenido de la caja…): su huella
            v = "#" + hashlib.sha256(json.dumps(v, sort_keys=True, default=str).encode()).hexdigest()[:16]
        elif v is not None:
            v = str(v)[:200]
        datos[c] = v
    return {"version_id": g.version.id, "cantidad": max(g.cantidad, 0), "datos": datos}


def diferencias(antes: dict | None, ahora: dict | None) -> list[dict]:
    """Qué cambió en lo que se va a imprimir desde la revisión: [{campo, antes, ahora}]."""
    if not antes or not ahora:
        return []
    res = []
    if antes.get("version_id") != ahora.get("version_id"):
        res.append({"campo": "diseno", "antes": antes.get("version_id"), "ahora": ahora.get("version_id")})
    if antes.get("cantidad") != ahora.get("cantidad"):
        res.append({"campo": "cantidad", "antes": antes.get("cantidad"), "ahora": ahora.get("cantidad")})
    a, b = antes.get("datos") or {}, ahora.get("datos") or {}
    res += [{"campo": c, "antes": a.get(c), "ahora": b.get(c)} for c in sorted(set(a) | set(b)) if a.get(c) != b.get(c)]
    return res


def _validar(db: Session, user: Usuario, t: TrabajoEtiquetas) -> dict:
    """Arma los registros del trabajo con su diseño, por qué y problemas. Los ya
    generados se conservan como tales (no se vuelven a generar). Devuelve los
    grupos de cada parte para generarlos sin volver a calcular."""
    anteriores = {r.clave: r for r in t.registros}
    generales, nuevos, vistas, grupos_por_parte, variables = [], {}, set(), {}, {}
    bultos_vistos: set = set()  # (tipo, bulto) ya en otra parte del trabajo
    partes = _partes(db, t)
    if not partes:
        generales.append({"nivel": "error", "codigo": "sin_registros", "categoria": "configuracion",
                          "mensaje": "Choose what to label."})
    for prefijo, pedido in partes:
        try:
            r = generacion.planear(db, user, pedido)
        except ErrorNegocio as e:
            oc = db.get(OrdenCompra, pedido["oc_id"]) if pedido.get("oc_id") else None
            generales.append({"nivel": "error", "codigo": e.codigo, "categoria": "configuracion", "parte": prefijo,
                              "mensaje": f"{f'PO {oc.numero}: ' if oc else ''}{e.mensaje}"})
            continue
        generales += [{**x, "parte": prefijo} for x in r["problemas"]]
        # Una caja con líneas de varias OCs del trabajo aparece en la parte de cada OC: es una
        # sola caja física y lleva una sola etiqueta (la primera parte la genera)
        grupos = []
        for g in r["_grupos"]:
            if g.bulto is not None:
                identidad = (g.tipo.id, g.bulto.clave)
                if identidad in bultos_vistos:
                    generales.append({"nivel": "info", "codigo": "bulto_compartido", "categoria": "empaque", "parte": prefijo,
                                      "mensaje": f"{g.referencia}: the package also holds lines of another PO of this job; "
                                                 "it gets one label."})
                    continue
                bultos_vistos.add(identidad)
            grupos.append(g)
        _muestras(db, grupos, vistas)
        grupos_por_parte[prefijo] = grupos
        for g in grupos:
            generacion._clasificar(g.problemas)
            for v in (g.version.diseno.get("variables") or []) if g.version else []:
                variables.setdefault(v["clave"], v)
            clave = f"{prefijo}:{g.clave}"
            if len(clave) > 80 or clave in nuevos:
                # Una clave repetida perdería etiquetas sin avisar: nunca se acepta
                raise RuntimeError(f"Clave de registro repetida o demasiado larga: {clave}")
            e = g.eleccion
            p = g.plantilla
            referencia = f"{r['oc']} · {g.referencia}" if t.origen == "OC" and len(partes) > 1 and r.get("oc") else g.referencia
            nuevos[clave] = {"clave": clave, "referencia": referencia[:160], "tipo_etiqueta_id": g.tipo.id,
                             "oc_id": g.oc.id if g.oc else r["oc_id"], "posicion_id": g.posicion.id if g.posicion else None,
                             "articulo_id": g.articulo.id if g.articulo else None, "pl_id": pedido.get("pl_id"),
                             "plantilla_id": p.id if p else None, "version_id": g.version.id if g.version else None,
                             "uso_id": e.uso.id if e and e.uso and getattr(e.uso, "id", None) else None,
                             "cantidad": max(g.cantidad, 0),
                             "estado": "OMITIDO" if g.omitido else _estado_registro(g.problemas), "problemas": g.problemas[:50],
                             "motivo": (e.motivo or "")[:300] if e else None, "revisado": _revisado(g)}
    # Registros: se conservan los generados; los demás se reemplazan
    for clave, r in anteriores.items():
        if r.estado == "GENERADO":
            nuevos.pop(clave, None)
        elif clave not in nuevos:
            db.delete(r)
    db.flush()
    orden = len(anteriores)
    for i, (clave, x) in enumerate(nuevos.items()):
        r = anteriores.get(clave)
        if r is None or r.estado == "GENERADO":
            r = TrabajoRegistro(trabajo_id=t.id, orden=orden + i, clave=clave)
            db.add(r)
        for k, v in x.items():
            setattr(r, k, v)
    db.flush()
    db.refresh(t)
    total = sum(r.cantidad for r in t.registros if r.estado in ("LISTO", "ADVERTENCIA"))
    if (total + sum(r.cantidad for r in t.registros if r.estado == "GENERADO") > int(regla("ETIQUETAS_MAXIMO_TRABAJO"))
            and not any(x.get("codigo") == "lote_grande" for x in generales)):
        generales.append({"nivel": "error", "codigo": "lote_grande", "categoria": "cantidad",
                          "mensaje": f"The job has more than {regla('ETIQUETAS_MAXIMO_TRABAJO')} labels: split it."})
    conteo = {"registros": len(t.registros)}
    for r in t.registros:
        conteo[r.estado] = conteo.get(r.estado, 0) + 1
    categorias: dict = {}
    for r in t.registros:
        for p in r.problemas or []:
            clave = f"{p.get('categoria', 'diseno')}:{p['nivel']}"
            categorias[clave] = categorias.get(clave, 0) + 1
    disenos: dict = {}
    for r in t.registros:
        if r.plantilla_id and r.estado != "OMITIDO":
            x = disenos.setdefault((r.tipo_etiqueta_id, r.plantilla_id), 0)
            disenos[(r.tipo_etiqueta_id, r.plantilla_id)] = x + r.cantidad
    tipos_ = dict(db.execute(select(TipoEtiqueta.id, TipoEtiqueta.nombre)).all())
    por_tipo: dict = {}
    for r in t.registros:
        x = por_tipo.setdefault(r.tipo_etiqueta_id, {"tipo_etiqueta_id": r.tipo_etiqueta_id, "tipo": tipos_.get(r.tipo_etiqueta_id),
                                                     "registros": 0, "etiquetas": 0, "omitidos": 0, "errores": 0})
        if r.estado == "OMITIDO":
            x["omitidos"] += 1
            continue
        x["registros"] += 1
        x["etiquetas"] += r.cantidad
        x["errores"] += int(r.estado == "ERROR")
    t.resumen = {"problemas": [x for x in generales if x["nivel"] == "error"],
                 "avisos": [x for x in generales if x["nivel"] != "error"], "conteo": conteo, "categorias": categorias,
                 "disenos": [{"tipo_etiqueta_id": tid, "tipo": tipos_.get(tid), "plantilla_id": k,
                              "plantilla": db.get(PlantillaEtiqueta, k).nombre, "etiquetas": v}
                             for (tid, k), v in sorted(disenos.items())],
                 "tipos": list(por_tipo.values()),
                 "verificacion": "lector" if verificacion.disponible() else "sin_lector",
                 "variables": list(variables.values()),
                 "ejecuciones": (t.resumen or {}).get("ejecuciones", [])}
    t.total = total
    t.validado_en = ahora()
    if t.estado in ("BORRADOR", "VALIDADO", "ERROR"):
        t.estado = "VALIDADO"
    t.error = None
    return grupos_por_parte


# ---- Generación -------------------------------------------------------------------------------------
# ---- Ejecución duradera ---------------------------------------------------------------------------
# Un trabajo que se genera en segundo plano queda EN_PROCESO y arrendado a un
# ejecutor (proceso + hilo) hasta `arriendo_hasta`. El ejecutor renueva el
# arriendo (latido) mientras trabaja y lo comprueba en la misma transacción en
# que confirma cada parte: si lo perdió (otro lo tomó porque venció), deshace
# esa parte. Cualquier instancia retoma un trabajo cuyo arriendo venció (el que
# lo tenía se detuvo) o que nunca se tomó (el proceso cayó antes de empezar).
# La base es la que decide: la toma es un UPDATE condicional y un registro solo
# puede producir un ítem de generación (restricción única), así una carrera
# nunca duplica etiquetas.
INSTANCIA = f"{socket.gethostname()}:{os.getpid()}"
T = TrabajoEtiquetas.__table__


class ArriendoPerdido(Exception):
    """Otro ejecutor tomó el trabajo: este deja de escribir."""


def _ahora() -> datetime:
    return ahora()


def _arriendo() -> timedelta:
    return timedelta(seconds=max(int(settings.ETIQUETAS_ARRIENDO_SEG), 5))


def _abandonado():
    """Condición SQL de un trabajo EN_PROCESO que nadie está ejecutando."""
    ahora = _ahora()
    return (T.c.estado == "EN_PROCESO") & (
        (T.c.arriendo_hasta < ahora) | (T.c.arriendo_hasta.is_(None) & (T.c.actualizado_en < ahora - _arriendo())))


def _tomar(db: Session, trabajo_id: int) -> str | None:
    """Arrienda el trabajo a este ejecutor si nadie lo tiene (o el arriendo
    venció). Devuelve la ficha del ejecutor, o None si otro lo tiene."""
    ficha = f"{INSTANCIA}:{uuid.uuid4().hex[:12]}"
    ahora = _ahora()
    libre = (T.c.estado == "EN_PROCESO") & (T.c.ejecutor.is_(None) | (T.c.arriendo_hasta < ahora))
    r = db.execute(update(T).where(T.c.id == trabajo_id, libre)
                   .values(ejecutor=ficha, arriendo_hasta=ahora + _arriendo(), latido_en=ahora, intentos=T.c.intentos + 1))
    db.commit()
    return ficha if r.rowcount == 1 else None


def _renovar(db: Session, trabajo_id: int, ficha: str) -> bool:
    """Renueva el arriendo; False si este ejecutor ya no lo tiene."""
    ahora = _ahora()
    r = db.execute(update(T).where(T.c.id == trabajo_id, T.c.ejecutor == ficha, T.c.estado == "EN_PROCESO")
                   .values(arriendo_hasta=ahora + _arriendo(), latido_en=ahora))
    return r.rowcount == 1


class _Latido:
    """Renueva el arriendo desde otro hilo mientras se dibuja una parte larga."""

    def __init__(self, trabajo_id: int, ficha: str):
        self.trabajo_id, self.ficha = trabajo_id, ficha
        self.alto = threading.Event()
        self.perdido = threading.Event()
        self.hilo = threading.Thread(target=self._latir, daemon=True, name=f"latido-{trabajo_id}")

    def _latir(self) -> None:
        from app.core.db import SessionLocal

        cada = max(_arriendo().total_seconds() / 4, 1)
        while not self.alto.wait(cada):
            try:
                with SessionLocal() as db:
                    if not _renovar(db, self.trabajo_id, self.ficha):
                        self.perdido.set()
                        return
                    db.commit()
            except Exception:  # noqa: BLE001 - un latido fallido no detiene la generación; el siguiente reintenta
                logging.getLogger("etiquetado").exception("No se pudo renovar el arriendo del trabajo %s", self.trabajo_id)

    def __enter__(self):
        self.hilo.start()
        return self

    def __exit__(self, *_):
        self.alto.set()
        self.hilo.join(timeout=5)


def _interrumpido(db: Session, t: TrabajoEtiquetas) -> bool:
    """El trabajo figura EN_PROCESO pero nadie lo ejecuta: lo libera (en una
    sola sentencia, por si otro proceso lo toma a la vez) para seguir."""
    hechos = any(r.estado == "GENERADO" for r in t.registros)
    r = db.execute(update(T).where(T.c.id == t.id, _abandonado()).values(
        estado="PARCIAL" if hechos else "VALIDADO", ejecutor=None, arriendo_hasta=None,
        error="The previous generation was interrupted; the pending records can be generated again."))
    if r.rowcount == 1:
        db.refresh(t)
        return True
    return False


def generar(db: Session, user: Usuario, trabajo_id: int, opciones: dict) -> dict:
    t = cargar(db, user, trabajo_id, bloquear=True)
    _version(t, opciones)
    if t.estado == "EN_PROCESO":
        _interrumpido(db, t)
    if t.estado == "EN_PROCESO":
        raise ErrorNegocio("The labels are already being generated.", 409, "estado")
    if t.estado == "CANCELADO":
        raise ErrorNegocio("The labeling job was cancelled.", 409, "estado")
    # Lo revisado de cada registro pendiente, para avisar si lo que se va a imprimir cambió desde entonces
    previos = {r.clave: r.revisado for r in t.registros if r.estado not in ("GENERADO", "OMITIDO") and r.revisado}
    # Lo que el usuario cambió en el trabajo después de revisarlo (cantidades a mano, más posiciones o tipos) es su
    # decisión, no un cambio de los datos: no se avisa
    a_mano = {str(k) for k in ((t.parametros or {}).get("cantidades") or {})}
    parametros_cambiados = t.estado == "BORRADOR"
    grupos = _validar(db, user, t)
    if t.resumen["problemas"]:
        raise ErrorNegocio("The labeling job has errors: fix them first.", 422, "etiquetas_con_errores",
                           [{"campo": "trabajo", "mensaje": p["mensaje"]} for p in t.resumen["problemas"]][:50])
    pendientes = [r for r in t.registros if r.estado not in ("GENERADO", "OMITIDO")]
    generables = [r for r in pendientes if r.estado in ("LISTO", "ADVERTENCIA") and r.cantidad > 0]
    con_error = [r for r in pendientes if r.estado == "ERROR"]
    if not pendientes:
        if any(r.estado == "GENERADO" for r in t.registros):
            raise ErrorNegocio("Everything in this labeling job was already generated.", 409, "ya_generado")
        raise ErrorNegocio("There is nothing to generate in this labeling job.", 422, "etiquetas_con_errores")
    parcial = bool(opciones.get("parcial"))
    if con_error and not (parcial and regla("ETIQUETAS_GENERACION_PARCIAL")):
        raise ErrorNegocio("Some records have errors: fix them or generate only the ready ones." if regla("ETIQUETAS_GENERACION_PARCIAL")
                           else "Some records have errors: fix them.", 422, "etiquetas_con_errores",
                           [{"campo": r.referencia, "mensaje": p["mensaje"]} for r in con_error for p in r.problemas
                            if p["nivel"] == "error"][:50])
    if not generables:
        raise ErrorNegocio("No record is ready to generate.", 422, "etiquetas_con_errores")
    if previos and not opciones.get("aceptar_cambios"):
        cambios = []
        for r in generables:
            if r.clave not in previos:
                d = [] if parametros_cambiados else [{"campo": "registro", "antes": None, "ahora": r.referencia}]
            else:
                d = [x for x in diferencias(previos[r.clave], r.revisado) if not (x["campo"] == "cantidad" and r.clave in a_mano)]
            if d:
                cambios.append((r, d))
        if cambios:
            raise ErrorNegocio("The data changed since the job was reviewed: check it again before generating.", 409,
                               "datos_cambiaron",
                               [{"campo": r.referencia, "mensaje": "; ".join(f"{x['campo']}: {x['antes'] if x['antes'] is not None else '—'}"
                                                                            f" → {x['ahora'] if x['ahora'] is not None else '—'}" for x in d)[:300]}
                                for r, d in cambios][:50])
    advertencias = [{"campo": r.referencia, "mensaje": p["mensaje"]} for r in generables for p in r.problemas
                    if p["nivel"] == "advertencia"]
    if advertencias and not opciones.get("aceptar_advertencias"):
        raise ErrorNegocio("There are warnings: review them and confirm to generate anyway.", 409, "confirmar_advertencias",
                           advertencias[:50])
    formato = (opciones.get("formato") or (t.parametros or {}).get("formato") or "PDF").upper()
    if formato not in generacion.FORMATOS:
        raise ErrorNegocio("Choose PDF, PNG, SVG or ZIP.", 422, "validacion")
    claves = [r.clave for r in generables]
    total = sum(r.cantidad for r in generables)
    t.resumen = {**t.resumen, "pedido": {"claves": claves, "formato": formato, "por": user.id, "token": str(uuid.uuid4()),
                                         "aceptadas": len(advertencias), "omitidos": [r.clave for r in con_error]}}
    t.progreso, t.error = 0, None
    t.version += 1
    if total >= int(regla("ETIQUETAS_ASINCRONO_DESDE")):
        # Queda EN_PROCESO sin ejecutor: lo toma este proceso al confirmar la petición
        # (lanzar) o, si este cae antes, cualquier instancia al recuperar.
        t.estado, t.ejecutor, t.arriendo_hasta = "EN_PROCESO", None, None
        t.actualizado_en = _ahora()
        db.flush()
        registrar(db, user, "trabajo_etiquetas", t.id, "generar", {"total": total, "segundo_plano": True})
        return {**detalle(db, user, t.id), "asincrono": True}
    _ejecutar(db, user, t, claves, formato, grupos=grupos)
    registrar(db, user, "trabajo_etiquetas", t.id, "generar", {"total": total, "estado": t.estado})
    return {**detalle(db, user, t.id), "asincrono": False}


def _ejecutar(db: Session, user: Usuario, t: TrabajoEtiquetas, claves: list[str], formato: str, ficha: str | None = None,
              latido: _Latido | None = None, grupos: dict | None = None) -> None:
    """Una ejecución por parte con sus registros pendientes. Con `grupos` (los
    de la validación recién hecha en esta misma petición) no se vuelve a
    calcular nada; en segundo plano se calcula una vez por parte. Con ficha
    (segundo plano) cada parte se confirma por separado, después de comprobar
    en la misma transacción que el arriendo sigue siendo de este ejecutor."""
    por_clave = {r.clave: r for r in t.registros}
    lote = str(uuid.uuid4())
    hechas = []
    for prefijo, pedido in _partes(db, t):
        mias = [c for c in claves if c.startswith(prefijo + ":") and c in por_clave and por_clave[c].estado != "GENERADO"]
        if not mias:
            continue
        if latido is not None and latido.perdido.is_set():
            raise ArriendoPerdido()
        internas = {c.split(":", 1)[1]: por_clave[c].id for c in mias}
        if grupos is not None and prefijo in grupos:
            lista = grupos[prefijo]
        else:
            lista = generacion.planear(db, user, pedido, solo=set(internas))["_grupos"]
        lista = [g for g in lista if g.clave in internas]
        gen = generacion.producir(db, user, lista, {**pedido, "formato": formato, "lote": lote, "_registros": internas,
                                                     "_trabajo_id": t.id, "pl_id": pedido.get("pl_id"),
                                                     "oc_id": pedido.get("oc_id")})
        for c in mias:
            r = por_clave[c]
            r.estado, r.generacion_id = "GENERADO", gen["id"]
        t.progreso += gen["total"]
        t.actualizado_en = _ahora()
        hechas.append({"id": gen["id"], "oc": gen["oc"], "total": gen["total"]})
        db.flush()
        if ficha is not None:
            if not _renovar(db, t.id, ficha):
                raise ArriendoPerdido()
            db.commit()
    quedan = [r for r in t.registros if r.estado not in ("GENERADO", "OMITIDO")]
    t.estado = "PARCIAL" if quedan else "GENERADO"
    t.total = sum(r.cantidad for r in quedan if r.estado in ("LISTO", "ADVERTENCIA"))
    conteo = {"registros": len(t.registros)}
    for r in t.registros:
        conteo[r.estado] = conteo.get(r.estado, 0) + 1
    t.generado_en = _ahora()
    t.resumen = {**(t.resumen or {}), "conteo": conteo, "ejecuciones": (t.resumen or {}).get("ejecuciones", []) + hechas}
    t.version += 1
    if ficha is not None:
        # El cierre también se confirma solo si el arriendo sigue siendo de este ejecutor
        if not _renovar(db, t.id, ficha):
            raise ArriendoPerdido()
        t.ejecutor, t.arriendo_hasta = None, None
    db.flush()


def lanzar(trabajo_id: int, usuario_id: int | None = None, organizacion_id: int | None = None) -> bool:
    """Toma el trabajo y lo genera en un hilo de este proceso (después de
    confirmar la petición). Si otro ejecutor ya lo tiene, no hace nada."""
    from app.core.db import SessionLocal

    with SessionLocal() as db:
        ficha = _tomar(db, trabajo_id)
    if ficha is None:
        return False
    threading.Thread(target=ejecutar_tomado, args=(trabajo_id, ficha), daemon=True, name=f"etiquetas-{trabajo_id}").start()
    return True


def _contexto(db: Session, user: Usuario) -> None:
    """Lo que una petición deja listo y un proceso sin petición tiene que fijar:
    organización, reglas y listas de la empresa, preferencias y datos ocultos."""
    from app.core.empresa import usar_configuracion
    from app.core.listas import usar_listas
    from app.modulos.acceso import preferencias, visibilidad
    from app.modulos.empresa.organizacion import configuracion
    from app.modulos.maestros.listas import cargar as cargar_listas

    fijar(db, user.organizacion_id, user.id)
    usar_configuracion(configuracion(db))
    usar_listas(cargar_listas(db))
    preferencias.usar(user)
    visibilidad.usar(user)


def ejecutar_tomado(trabajo_id: int, ficha: str) -> None:
    """Genera lo pendiente de un trabajo que este ejecutor tiene arrendado.
    Cada parte queda confirmada al terminar; un error deja el trabajo PARCIAL
    (o ERROR si no se generó nada) con el motivo, y se suelta el arriendo."""
    from app.core.db import SessionLocal

    ctx = contextvars.copy_context()
    ctx.run(_ejecutar_tomado, trabajo_id, ficha, SessionLocal)


def _ejecutar_tomado(trabajo_id: int, ficha: str, SessionLocal) -> None:  # noqa: N803
    db = SessionLocal()
    try:
        fila = db.execute(select(T.c.organizacion_id, T.c.resumen, T.c.ejecutor).where(T.c.id == trabajo_id)).one_or_none()
        if fila is None or fila.ejecutor != ficha:
            return
        pedido = (fila.resumen or {}).get("pedido") or {}
        user = db.get(Usuario, pedido.get("por")) if pedido.get("por") else None
        if user is None or not user.activo:
            raise ErrorNegocio("The user who started the generation no longer exists or is inactive.", 409, "estado")
        _contexto(db, user)
        t = db.get(TrabajoEtiquetas, trabajo_id)
        with _Latido(trabajo_id, ficha) as latido:
            _ejecutar(db, user, t, pedido.get("claves") or [], pedido.get("formato") or "PDF", ficha, latido)
            db.commit()
    except ArriendoPerdido:
        db.rollback()  # otro ejecutor sigue con el trabajo: no se toca nada más
        logging.getLogger("etiquetado").warning("El trabajo %s pasó a otro ejecutor", trabajo_id)
    except Exception as e:  # noqa: BLE001 - el error queda en el trabajo para quien lo generó
        db.rollback()
        hechos = db.scalar(select(func.count()).select_from(TrabajoRegistro).where(
            TrabajoRegistro.trabajo_id == trabajo_id, TrabajoRegistro.estado == "GENERADO")) or 0
        db.execute(update(T).where(T.c.id == trabajo_id, T.c.ejecutor == ficha).values(
            estado="PARCIAL" if hechos else "ERROR", ejecutor=None, arriendo_hasta=None, actualizado_en=_ahora(),
            error=(getattr(e, "mensaje", None) or str(e) or type(e).__name__)[:2000]))
        db.commit()
        logging.getLogger("etiquetado").exception("Falló la generación del trabajo %s", trabajo_id)
    finally:
        db.close()


def recuperar() -> list[int]:
    """Retoma los trabajos EN_PROCESO que nadie ejecuta (el proceso que los
    tenía se detuvo o cayó antes de empezar). Un trabajo que agotó sus intentos
    queda en ERROR para que alguien lo revise. Devuelve los retomados."""
    from app.core.db import SessionLocal

    retomados = []
    with SessionLocal() as db:  # sin organización: ve los trabajos de todas (también con RLS)
        ids = list(db.scalars(select(T.c.id).where(_abandonado()).order_by(T.c.id).limit(50)))
        for tid in ids:
            agotado = db.execute(update(T).where(T.c.id == tid, _abandonado(), T.c.intentos >= settings.ETIQUETAS_MAX_INTENTOS)
                                 .values(estado="ERROR", ejecutor=None, arriendo_hasta=None, actualizado_en=_ahora(),
                                         error="The generation failed several times in a row; check the job and generate again."))
            db.commit()
            if agotado.rowcount:
                continue
            ficha = _tomar(db, tid)
            if ficha:
                ejecutar_tomado(tid, ficha)
                retomados.append(tid)
    return retomados


# ---- Archivos ----------------------------------------------------------------------------------------
def _seguro(texto: str) -> str:
    return "".join(c if c.isalnum() or c in "-_. " else "_" for c in str(texto or "")).strip()[:80] or "_"


@visibilidad.con_datos_completos
def archivo(db: Session, user: Usuario, trabajo_id: int, contenido: str | None = None) -> tuple[bytes, str]:
    """El ZIP del trabajo: las etiquetas de todas sus ejecuciones dibujadas de
    nuevo desde sus versiones e instantáneas, en las carpetas y con los nombres
    configurados (sin repetir nombres) y un resumen de la ejecución."""
    t = cargar(db, user, trabajo_id)
    gens = list(db.scalars(select(GeneracionEtiquetas).where(GeneracionEtiquetas.trabajo_id == t.id,
                                                             GeneracionEtiquetas.anulada_en.is_(None)).order_by(GeneracionEtiquetas.id)))
    if not gens:
        raise ErrorNegocio("Nothing has been generated in this labeling job yet.", 404, "no_encontrado")
    z_conf = {**{"carpetas": [], "nombre": "", "contenido": "PDF"}, **((t.parametros or {}).get("zip") or {})}
    if contenido and contenido.upper() != z_conf["contenido"]:
        z_conf["contenido"], z_conf["agrupar"] = contenido.upper(), None  # otro contenido: su agrupación por defecto
    if z_conf["contenido"] not in CONTENIDOS:
        raise ErrorNegocio("Choose PDF, PNG or SVG files inside the ZIP.", 422, "validacion")
    z_conf["agrupar"] = _agrupar(z_conf["contenido"], z_conf["carpetas"], z_conf.get("agrupar"))
    plantillas_ = {}
    versiones_: dict = {}
    ocs: dict = {}
    etiquetas = []  # (carpeta, nombre, lienzo)
    i = 0
    for g in gens:
        oc_gen = db.get(OrdenCompra, g.oc_id) if g.oc_id else None
        pl = None
        if g.pl_id:
            from app.modelos import PackingList

            pl = db.get(PackingList, g.pl_id)
        for lz, _ref, it, n in generacion._lienzos(db, g):
            i += 1
            if it.plantilla_id not in plantillas_:
                plantillas_[it.plantilla_id] = db.get(PlantillaEtiqueta, it.plantilla_id).nombre
            if it.version_id not in versiones_:
                versiones_[it.version_id] = db.get(VersionPlantilla, it.version_id).numero
            oc = oc_gen
            if oc is None and it.posicion_id:
                if it.posicion_id not in ocs:
                    ocs[it.posicion_id] = db.get(PosicionOC, it.posicion_id).oc
                oc = ocs[it.posicion_id]
            v = it.valores or {}
            marcas = {"oc": oc.numero if oc else "", "referencia": it.referencia or "", "n": n, "total": it.cantidad, "i": i,
                      "sku": v.get("articulo.sku") or v.get("linea.codigo_articulo") or "",
                      "plantilla": plantillas_[it.plantilla_id], "serie": generacion.numero_serie(v, n) or "",
                      "bulto": v.get("bulto.codigo") or v.get("bulto.numero") or ""}
            carpeta = []
            sin = z_conf.get("sin_valor") or "_"
            for c in z_conf["carpetas"]:
                if c == "oc":
                    carpeta.append(marcas["oc"] or sin)
                elif c == "plantilla":
                    carpeta.append(marcas["plantilla"])
                elif c == "familia":
                    carpeta.append(v.get("articulo.familia") or sin)
                elif c == "packing_list":
                    carpeta.append(pl.numero if pl else (v.get("bulto.packing_list") or sin))
            patron = z_conf["nombre"] or "{i}-{referencia}-{n}"
            nombre = patron
            for k, x in marcas.items():
                nombre = nombre.replace("{" + k + "}", str(x))
            diseno_ = f"{plantillas_[it.plantilla_id]}-v{versiones_[it.version_id]}"
            etiquetas.append(("/".join(_seguro(x) for x in carpeta), _seguro(nombre), lz, diseno_))
        generacion.marcar_descarga(g)
    buf = io.BytesIO()
    fecha = gens[0].creada_en.timetuple()[:6]
    usados: set = set()

    def unico(ruta: str) -> str:
        base, punto, ext = ruta.rpartition(".")
        k, res = 1, ruta
        while res.lower() in usados:
            k += 1
            res = f"{base}-{k}.{ext}" if punto else f"{ruta}-{k}"
        usados.add(res.lower())
        return res

    def poner(z, nombre: str, datos_: bytes | str):
        info = zipfile.ZipInfo(nombre, date_time=fecha)
        info.compress_type = zipfile.ZIP_DEFLATED
        z.writestr(info, datos_)

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for ruta, lienzos in _archivos_pdf(etiquetas, z_conf["agrupar"], t.nombre) if z_conf["contenido"] == "PDF" else ():
            poner(z, unico(ruta), salidas.pdf(lienzos, {"modo": "individual"}, t.nombre))
        if z_conf["contenido"] != "PDF":
            ext = z_conf["contenido"].lower()
            for carpeta, nombre, lz, _d in etiquetas:
                datos_ = salidas.png(lz, (t.parametros or {}).get("dpi")) if ext == "png" else salidas.svg(lz)
                poner(z, unico(f"{carpeta}/{nombre}.{ext}" if carpeta else f"{nombre}.{ext}"), datos_)
        resumen = _resumen(db, t, gens)
        poner(z, unico("summary.json"), json.dumps(resumen, ensure_ascii=False, indent=1, default=str))
        poner(z, unico("summary.csv"), _csv(resumen["registros"]))
    registrar(db, user, "trabajo_etiquetas", t.id, "descargar",
              {"contenido": z_conf["contenido"], "agrupar": z_conf["agrupar"], "etiquetas": len(etiquetas)})
    db.flush()
    return buf.getvalue(), f"{_seguro(t.nombre).replace(' ', '_')}.zip"


def _archivos_pdf(etiquetas: list[tuple], agrupar: str, titulo: str) -> list[tuple[str, list]]:
    """(ruta, lienzos) de cada PDF del ZIP según la agrupación elegida. Ningún
    PDF mezcla diseños salvo el único, que se pide expresamente y exige que
    todas las etiquetas midan lo mismo (una impresora de etiquetas no cambia
    de rollo a mitad del archivo)."""
    if agrupar == "etiqueta":
        return [(f"{c}/{n}.pdf" if c else f"{n}.pdf", [lz]) for c, n, lz, _d in etiquetas]
    if agrupar == "unico":
        medidas = sorted({(lz.ancho, lz.alto) for _c, _n, lz, _d in etiquetas})
        if len(medidas) > 1:
            raise ErrorNegocio("The labels have different sizes: a single PDF would mix them. Choose one PDF per design.", 422,
                               "validacion", [{"campo": "zip.agrupar", "mensaje": ", ".join(f"{a:g}×{b:g} mm" for a, b in medidas)}])
        return [(f"{_seguro(titulo)}.pdf", [lz for _c, _n, lz, _d in etiquetas])]
    grupos: dict = {}
    for c, _n, lz, d in etiquetas:
        grupos.setdefault((c if agrupar == "carpeta" else "", d), []).append(lz)
    disenos_por_carpeta: dict = {}
    for c, d in grupos:
        disenos_por_carpeta.setdefault(c, set()).add(d)
    res = []
    for (c, d), lienzos in grupos.items():
        if agrupar == "plantilla":
            res.append((f"{_seguro(d)}.pdf", lienzos))
        else:
            base = c.rsplit("/", 1)[-1]
            nombre = base if len(disenos_por_carpeta[c]) == 1 else f"{base}-{_seguro(d)}"
            res.append((f"{c}/{nombre}.pdf", lienzos))
    return res


def _resumen(db: Session, t: TrabajoEtiquetas, gens: list[GeneracionEtiquetas]) -> dict:
    versiones = {}
    for g in gens:
        for it in g.items:
            if it.version_id not in versiones:
                v = db.get(VersionPlantilla, it.version_id)
                versiones[it.version_id] = f"{v.plantilla.nombre} v{v.numero}"
    return {"trabajo": {"id": t.id, "nombre": t.nombre, "origen": t.origen, "estado": t.estado, "generado_en": t.generado_en},
            "ejecuciones": [{"id": g.id, "total": g.total, "sha256": g.sha256, "creada_en": g.creada_en} for g in gens],
            "etiquetas": sum(g.total for g in gens),
            "registros": [{"clave": r.clave, "referencia": r.referencia, "estado": r.estado, "cantidad": r.cantidad,
                           "diseno": versiones.get(r.version_id) or "", "ejecucion": r.generacion_id or "",
                           "errores": sum(1 for p in r.problemas or [] if p["nivel"] == "error"),
                           "advertencias": sum(1 for p in r.problemas or [] if p["nivel"] == "advertencia"),
                           "problemas": "; ".join(p["mensaje"] for p in (r.problemas or [])[:5])}
                          for r in t.registros]}


def _csv(filas: list[dict]) -> str:
    out = io.StringIO()
    if filas:
        w = csv.DictWriter(out, fieldnames=list(filas[0].keys()))
        w.writeheader()
        w.writerows(filas)
    return out.getvalue()


# ---- Impresión ------------------------------------------------------------------------------------------
def confirmar_impresion(db: Session, user: Usuario, generacion_id: int, datos_: dict) -> dict:
    """Impreso solo con la confirmación expresa de quien imprimió: cuántas
    etiquetas salieron (todas o, si no, por qué), en qué impresora. El archivo
    tiene que haberse descargado antes."""
    exigir(user, "etiquetas.generar")
    g = generacion.cargar(db, user, generacion_id)
    if not datos_.get("confirmo"):
        raise ErrorNegocio("Confirm that the labels were printed.", 422, "validacion", [{"campo": "confirmo", "mensaje": "Required."}])
    if not g.descargas:
        raise ErrorNegocio("Download the labels before confirming they were printed.", 409, "sin_descarga")
    generacion.no_anulada(g)
    if g.estado == "PRUEBA":
        raise ErrorNegocio("Test labels are not printed for use.", 409, "prueba")
    try:
        cantidad = int(datos_.get("cantidad"))
    except (TypeError, ValueError):
        cantidad = -1
    if not 1 <= cantidad <= g.total:
        raise ErrorNegocio(f"Write how many labels were printed (1 to {g.total}).", 422, "validacion",
                           [{"campo": "cantidad", "mensaje": f"1 to {g.total}."}])
    observacion = (datos_.get("observacion") or "").strip()[:300] or None
    if cantidad != g.total and not observacion:
        raise ErrorNegocio("Explain why not all the labels were printed.", 422, "validacion",
                           [{"campo": "observacion", "mensaje": "Required."}])
    g.impresa_en, g.impresa_por = ahora(), user.id
    g.impresion = {"cantidad": cantidad, "total": g.total, "impresora": (datos_.get("impresora") or "").strip()[:100] or None,
                   "observacion": observacion}
    db.flush()
    registrar(db, user, "generacion_etiquetas", g.id, "imprimir", g.impresion, observacion)
    return dict_ejecucion(db, g)


def _motivo(datos_: dict) -> str:
    motivo = (datos_.get("motivo") or "").strip()[:300]
    if len(motivo) < 3:
        raise ErrorNegocio("Write the reason.", 422, "validacion", [{"campo": "motivo", "mensaje": "Required."}])
    return motivo


def anular(db: Session, user: Usuario, generacion_id: int, datos_: dict) -> dict:
    """Anula una ejecución con su motivo (etiquetas dañadas, datos equivocados…): ya no se descarga ni se
    confirma como impresa, sale del ZIP del trabajo y sus registros vuelven a quedar pendientes para
    generarlos de nuevo (al hacerlo se revisan otra vez sus datos). Sus números de serie quedan usados."""
    exigir(user, "etiquetas.generar")
    g = generacion.cargar(db, user, generacion_id)
    motivo = _motivo(datos_)
    t = cargar(db, user, g.trabajo_id, bloquear=True) if g.trabajo_id else None
    db.refresh(g, with_for_update=True)
    if g.anulada_en:
        raise ErrorNegocio("This label batch was already voided.", 409, "anulada")
    if t is not None and t.estado == "EN_PROCESO":
        raise ErrorNegocio("The labels are being generated: wait until it finishes.", 409, "estado")
    g.anulada_en, g.anulada_por, g.motivo_anulacion = ahora(), user.id, motivo
    if t is not None:
        ids = [it.trabajo_registro_id for it in g.items if it.trabajo_registro_id]
        for it in g.items:  # el registro puede volver a generarse (la llave única lo impedía)
            it.trabajo_registro_id = None
        db.flush()
        for r in t.registros:
            if r.id in ids or r.generacion_id == g.id:
                r.estado, r.generacion_id = "LISTO", None
        if t.estado in ("GENERADO", "PARCIAL", "ERROR"):
            t.estado = "PARCIAL" if any(r.estado == "GENERADO" for r in t.registros) else "VALIDADO"
        t.version += 1
        t.actualizado_en = ahora()
    db.flush()
    registrar(db, user, "generacion_etiquetas", g.id, "anular", {"trabajo_id": g.trabajo_id, "total": g.total}, motivo)
    return dict_ejecucion(db, g)


@visibilidad.con_datos_completos
def reimprimir(db: Session, user: Usuario, generacion_id: int, datos_: dict) -> tuple[bytes, str, str]:
    """Copias idénticas de las etiquetas de un lote (todas o algunos grupos y rangos), con sus mismos
    números y series, dibujadas de nuevo desde la versión y los valores guardados; queda en el historial
    del lote quién, cuándo, cuántas y por qué."""
    exigir(user, "etiquetas.generar")
    g = generacion.cargar(db, user, generacion_id)
    generacion.no_anulada(g)
    motivo = _motivo(datos_)
    formato = (datos_.get("formato") or g.formato).upper()
    if formato not in generacion.FORMATOS:
        raise ErrorNegocio("Choose PDF, PNG, SVG or ZIP.", 422, "validacion")
    seleccion = generacion.seleccionar(g, datos_.get("seleccion"))
    total = g.total if seleccion is None else sum(b - a + 1 for a, b in seleccion.values())
    db.refresh(g, with_for_update=True)
    n = len(g.reimpresiones or []) + 1
    contenido, nombre, mime = generacion._producir(db, g, formato, seleccion, sufijo=f"-reprint{n}")
    g.reimpresiones = [*(g.reimpresiones or []), {
        "n": n, "en": ahora().isoformat(timespec="seconds"), "por": user.id, "motivo": motivo, "formato": formato,
        "total": total, "seleccion": [{"item_id": k, "desde": a, "hasta": b} for k, (a, b) in seleccion.items()] if seleccion else None}]
    db.flush()
    registrar(db, user, "generacion_etiquetas", g.id, "reimprimir", {"n": n, "total": total, "formato": formato}, motivo)
    return contenido, nombre, mime


def vista_previa(db: Session, user: Usuario, trabajo_id: int, registro_id: int) -> dict:
    """Un registro del trabajo dibujado por el servidor con sus datos reales,
    con los mismos valores, diseño y versión que tendrá al generarse (solo se
    calcula ese registro)."""
    t = cargar(db, user, trabajo_id)
    r = next((x for x in t.registros if x.id == registro_id), None)
    if r is None:
        raise ErrorNegocio("The record does not exist in this labeling job.", 404, "no_encontrado")
    prefijo, interna = r.clave.split(":", 1)
    pedido = next((p for k, p in _partes(db, t) if k == prefijo), None)
    if pedido is None:
        raise ErrorNegocio("The record is no longer part of this labeling job: validate it again.", 409, "estado")
    plan = generacion.planear(db, user, pedido, solo={interna})
    g = next((x for x in plan["_grupos"] if x.clave == interna), None)
    if g is None or g.version is None:
        raise ErrorNegocio("This record has no design to preview.", 422, "sin_plantilla")
    valores = {**g.valores, "etiqueta.numero": 1, "etiqueta.total": g.cantidad, "etiqueta.numero_lote": 1, "etiqueta.total_lote": 1}
    lz = render.componer(g.version.diseno, valores, campos.tipos(db, g.tipo.sujeto), plantillas.imagen_adjunta(db),
                         prueba=g.version.estado != "APROBADA")
    usados = sorted(c for c in g.valores if c in generacion.svc_diseno.campos_usados(g.version.diseno))
    return {"svg": salidas.svg(lz), "ancho": lz.ancho, "alto": lz.alto, "problemas": generacion._clasificar(g.problemas),
            "tipo": g.tipo.nombre, "plantilla": g.version.plantilla.nombre, "version": g.version.numero,
            "motivo": g.eleccion.motivo if g.eleccion else None, "porque": g.eleccion.porque if g.eleccion else None,
            "valores": {k: (f"[{len(g.valores[k])}]" if isinstance(g.valores[k], list) else g.valores[k]) for k in usados
                        if k != "organizacion.logo"},
            "procedencia": {k: v for k, v in g.procedencia.items() if v}}
