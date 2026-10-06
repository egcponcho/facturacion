"""Productos: ficha técnica y clasificación arancelaria.

Un producto es el estilo-color de un proveedor. Sus tallas (artículos) y sus
prepacks comparten la ficha técnica, la partida SAC aprobada y el código
nacional de cada país destino; de aquí los toman la OC y la factura.

El motor de reglas corre en el navegador (frontend/src/clasificacion/motor.js)
y manda su resultado al guardar; aquí se guarda, se valida lo que se aprueba y
se lleva el historial. Aprobar y enseñar códigos es del equipo interno; la
ficha la puede completar el proveedor.
"""
import json
import os
import re
import uuid
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy import func, insert, or_, select
from sqlalchemy.orm import Session, selectinload

from ..config import settings
from ..models import (
    Articulo,
    Centro,
    GrupoArticulo,
    Historial,
    IncisoNacional,
    Marca,
    Pais,
    PaisArancel,
    NotaSAC,
    PartidaSAC,
    PalabraClave,
    PartidaPais,
    Prepack,
    Producto,
    ProductoFoto,
    ProductoVersion,
    Proveedor,
    SinonimoMaterial,
    Usuario,
    ahora,
)
from .acuerdos import acuerdos_contexto, cargar_acuerdos
from .atributos import config_motor as atributos_cfg
from .generico import dominios_ficha
from .meta import meta as meta_motor
from .common import (
    filtro_texto,
    ErrorNegocio,
    asegurar_proveedor,
    tiene,
    exigir,
    proveedor_filtro,
    registrar,
    tocar,
    verificar_version,
)

# Países destino y dígitos de su código nacional (Centroamérica y Panamá)
# Países destino de fábrica; en la base se pueden agregar otros y cambiar sus dígitos
ACI = ("Arancel Centroamericano de Importación (Anexo A del Convenio sobre el Régimen Arancelario y Aduanero "
       "Centroamericano), SAC VII Enmienda del Sistema Armonizado — SIECA")
DESTINOS = [
    {"iso": "GT", "nombre": "Guatemala", "digitos": 10, "mcca": True, "impuesto": "VAT 12%", "base_legal": ACI},
    {"iso": "SV", "nombre": "El Salvador", "digitos": 10, "mcca": True, "impuesto": "VAT 13%", "base_legal": ACI},
    {"iso": "HN", "nombre": "Honduras", "digitos": 10, "mcca": True, "impuesto": "Sales tax 15%", "base_legal": ACI},
    {"iso": "NI", "nombre": "Nicaragua", "digitos": 12, "mcca": True, "impuesto": "VAT 15%",
     "base_legal": ACI + "; aperturas nacionales a 12 dígitos del arancel de Nicaragua"},
    {"iso": "CR", "nombre": "Costa Rica", "digitos": 12, "mcca": True, "impuesto": "VAT 13%",
     "base_legal": ACI + "; aperturas nacionales a 12 dígitos del arancel de Costa Rica"},
    {"iso": "PA", "nombre": "Panama", "digitos": 12, "mcca": False, "impuesto": "ITBMS 7%",
     "base_legal": "Arancel Nacional de Importación de la República de Panamá (nomenclatura del Sistema Armonizado)"},
]


def destinos(db: Session) -> list[dict]:
    """Países destino activos con su arancel (de la base)."""
    filas = db.scalars(select(PaisArancel).where(PaisArancel.activo.is_(True))
                       .order_by(PaisArancel.orden, PaisArancel.iso)).all()
    if not filas:
        return DESTINOS
    return [{"iso": x.iso, "nombre": x.nombre, "digitos": x.digitos, "mcca": x.mcca, "impuesto": x.impuesto,
             "base_legal": x.base_legal} for x in filas]


def digitos_pais(db: Session) -> dict:
    return {d["iso"]: d["digitos"] for d in destinos(db)}
# Borrador (incompleto o completo) → enviado a revisión → aprobado o devuelto.
# Mientras es borrador, lo edita cualquiera con permiso; enviado queda
# cerrado para el proveedor hasta que se apruebe o se devuelva.
ESTADOS = {"borrador": "Draft", "sugerida": "Draft · complete", "revision": "In review", "aprobado": "Approved",
           "corregido": "Corrected", "observado": "Returned"}
APROBADOS = ("aprobado", "corregido")
BORRADORES = ("borrador", "sugerida", "observado")
PENDIENTES = BORRADORES + ("revision",)
OBLIGATORIOS = ["tipo", "genero", "edadNac", "composicion", "origen"]
TIPOS_FOTO = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}


def digitos(s) -> str:
    return re.sub(r"\D", "", str(s or ""))


def fmt_codigo(c) -> str:
    d = digitos(c)
    if len(d) <= 4:
        return d
    o = d[:4] + "." + d[4:6]
    for i in range(6, len(d), 2):
        o += "." + d[i:i + 2]
    return o


# ---- Producto de cada artículo ------------------------------------------------
def producto_de(a: Articulo | None) -> Producto | None:
    """Producto que da la clasificación a un artículo. Un prepack no se
    clasifica: se arma con sólidos y toma la ficha de ellos."""
    if not a:
        return None
    if a.tipo == "PREPACK" and a.prepack:
        for c in a.prepack.componentes:
            if c.articulo and c.articulo.producto:
                return c.articulo.producto
    return a.producto


# Códigos de artículo y de genérico: el formato lo define cada empresa
# (numérico o alfanumérico, con punto, guion, barra o guion bajo)
RE_CODIGO = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._\-/]{0,39}$")
MSG_CODIGO = "Letters and numbers (also . - _ /), up to 40 characters."


def sin_marca(texto: str | None, marca: str | None = None) -> str | None:
    """Descripción aduanera sin la marca: la marca va en su propio campo en la
    factura y el packing list, así no se repite."""
    if not texto:
        return texto
    t = re.sub(r"[,;]?\s*\bMARCA\s+[^,;]+", "", str(texto), flags=re.I)
    for m in [x for x in {marca or ""} if x.strip()]:
        t = re.sub(rf"[,;]?\s*\b{re.escape(m.strip())}\b", "", t, flags=re.I)
    return re.sub(r"\s{2,}", " ", t).strip(" ,;") or None


def codigo_valido(valor: str | None) -> bool:
    return bool(RE_CODIGO.match(str(valor or "").strip()))


def generico_auto(estilo: str | None, color: str | None) -> str | None:
    """Genérico cuando la empresa no usa uno propio: estilo-color."""
    base = "-".join(x for x in (str(estilo or "").strip(), str(color or "").strip()) if x).upper()
    base = re.sub(r"[^A-Z0-9._\-/]+", "-", base).strip("-")
    return base[:40] or None


def generico_de(a) -> str | None:
    """Genérico (estilo-color) de un artículo o de una fila de datos."""
    if a is None:
        return None
    if isinstance(a, dict):
        return (str(a.get("generico") or "").strip().upper() or generico_auto(a.get("estilo"), a.get("color")))
    return a.generico or (a.producto.codigo_generico if a.producto else None) or generico_auto(a.estilo, a.color)


def producto_por_generico(db: Session, gen: str | None) -> Producto | None:
    return db.scalar(select(Producto).where(Producto.codigo_generico == gen)) if gen else None


def asegurar_producto(db: Session, a: Articulo) -> Producto | None:
    """Liga el artículo con el producto de su genérico (estilo-color); lo crea
    si no existe. Sólidos y prepacks del mismo genérico comparten la
    ficha técnica y la clasificación: el prepack no se clasifica aparte."""
    explicito = a.generico
    gen = generico_de(a)
    p = producto_por_generico(db, gen)
    if not p and a.tipo == "PREPACK":
        p = producto_de(a) if a.prepack else None
    if not p and a.proveedor_id and a.estilo:
        # Datos anteriores sin genérico: por proveedor, estilo y color
        p = db.scalar(select(Producto).where(Producto.proveedor_id == a.proveedor_id, Producto.estilo == a.estilo,
                                             Producto.color.is_(None) if a.color is None else Producto.color == a.color,
                                             *([or_(Producto.codigo_generico.is_(None), Producto.codigo_generico == gen)]
                                               if explicito else [])))
    if not p:
        if not a.proveedor_id or not a.estilo:
            return None
        p = Producto(proveedor_id=a.proveedor_id, estilo=a.estilo, color=a.color, marca_id=a.marca_id,
                     grupo_id=a.grupo_id, unidad=a.unidad if a.tipo == "SOLIDO" else None, ficha={}, faltan=[],
                     alertas_ok=[])
        db.add(p)
    if gen and not p.codigo_generico:
        p.codigo_generico = gen
    p.marca_id = p.marca_id or a.marca_id
    p.grupo_id = p.grupo_id or a.grupo_id
    if a.tipo == "SOLIDO" and not p.unidad:
        p.unidad = a.unidad
    db.flush()
    a.producto = p
    if not a.generico:
        a.generico = p.codigo_generico
    if not p.descripcion_comercial and not (p.ficha or {}).get("comManual"):
        p.descripcion_comercial = descripcion_comercial_simple(p)
    return p


def tipo_comercial(tipo: str | None, ficha: dict | None) -> str:
    """El tipo de producto en español para la factura (misma regla que el motor)."""
    from .meta import tipos

    f = ficha or {}
    if not tipo:
        return ""
    if tipo == "calzado":
        return "CALZADO"
    if tipo == "chaqueta":
        h = f.get("hechura")
        return "CHALECO" if h in ("chaleco", "chaleco_relleno", "reflectivo") else "SACO" if h == "blazer" else "CHAQUETA"
    if tipo == "pantalon":
        return "SHORT" if f.get("largo") == "corto" else "PANTALÓN"
    if tipo == "camiseta":
        return "POLO" if f.get("polo") else "CAMISETA"
    if tipo == "sudadera":
        return "SUÉTER" if f.get("sueter") else "SUDADERA"
    t = tipos().get(tipo) or {}
    return str(t.get("es") or t.get("corto") or tipo).split(" o ")[0].upper()


def descripcion_comercial_simple(p: Producto) -> str | None:
    """Descripción comercial de factura y packing list: tipo y marca (p. ej. CALZADO VANS)."""
    tipo = tipo_comercial(p.tipo, p.ficha)
    if not tipo:
        return None
    marca = (p.marca.nombre if p.marca else "") or ""
    return f"{tipo} {marca}".strip().upper()[:300]


def pais_de_centro(db: Session, centro: str | None) -> str | None:
    if not centro:
        return None
    return db.scalar(select(Centro.pais).where(Centro.codigo == centro))


def partida_para(p: Producto | None, pais: str | None) -> str | None:
    """Código que va en la OC y la factura: el nacional del país destino si
    está completo; si no, la partida SAC aprobada. Nada si no está aprobado."""
    if not p or not p.aprobado:
        return None
    if pais:
        x = next((x for x in p.partidas if x.pais == pais), None)
        if x and x.estado in ("ok", "auto", "sac") and len(digitos(x.codigo)) >= 8:
            return fmt_codigo(x.codigo)
    return fmt_codigo(p.codigo)


def clasificacion_txt(p: Producto | None) -> dict:
    """Resumen corto para mostrar junto al artículo en la OC o la factura."""
    if not p:
        return {"estado": None, "texto": "No product"}
    return {"estado": p.estado, "texto": ESTADOS.get(p.estado, p.estado), "producto_id": p.id,
            "codigo": fmt_codigo(p.codigo) if p.aprobado else None,
            "sugerido": fmt_codigo(p.sugerido) if p.sugerido and not p.aprobado else None}


# ---- Códigos nacionales en el servidor (base cargada y aprobaciones en lote) ---
def _valor_cond(ficha: dict, k: str):
    if k == "edadNac":
        return "bebe" if ficha.get("edad") == "bebe" else ficha.get("edadNac") or None
    return ficha.get(k)


def _evaluar_cond(cond: dict, ficha: dict) -> tuple[int, bool, list]:
    sc, choca, faltan = 0, False, []
    for k, v in (cond or {}).items():
        if k in ("cifMax", "cifMin"):
            try:
                x = float(ficha.get("valorCIF"))
            except (TypeError, ValueError):
                faltan.append("valorCIF")
                continue
            if (k == "cifMax" and x <= v) or (k == "cifMin" and x > v):
                sc += 4
            else:
                choca = True
            continue
        a = _valor_cond(ficha, k)
        if a in (None, ""):
            faltan.append(k)
            continue
        ok = (str(a) in [str(x) for x in v]) if isinstance(v, list) else (bool(a) == v if isinstance(v, bool) else str(a) == str(v))
        if ok:
            sc += 4
        else:
            choca = True
    return sc, choca, faltan


def partidas_simples(db: Session, p: Producto, codigo: str) -> dict:
    """Elige el código de cada país con las condiciones de los incisos
    conocidos. El navegador hace lo mismo con más detalle; esto sirve para la
    base de demostración y para aprobar en lote."""
    cb = digitos(codigo)
    sub = cb[:6]
    ficha = dict(p.ficha or {}, tipo=p.tipo)
    out = {}
    incisos = db.scalars(select(IncisoNacional).where(IncisoNacional.sub6 == sub, IncisoNacional.activo.is_(True))).all() \
        if len(sub) == 6 else []
    for d in destinos(db):
        iso, n = d["iso"], d["digitos"]
        if len(sub) < 6:
            out[iso] = {"codigo": "", "estado": "sin_codigo"}
            continue
        lista = [x for x in incisos if x.pais == iso]
        vivos = []
        for x in lista:
            sc, choca, faltan = _evaluar_cond(x.cond, ficha)
            if not choca:
                vivos.append((sc + (x.prio or 0) * 10, len(x.cond or {}), faltan, x))
        if not vivos:
            out[iso] = {"codigo": cb[:n] if len(cb) >= min(n, 10) and d.get("mcca") else sub,
                        "estado": "sac" if len(cb) >= min(n, 10) else ("nuevo" if lista else "sinarancel")}
            continue
        vivos.sort(key=lambda v: (-v[0], -v[1]))
        mejor = vivos[0]
        empate = [v for v in vivos if v[0] == mejor[0] and v[1] == mejor[1]]
        if mejor[2] or len(empate) > 1:
            out[iso] = {"codigo": "", "estado": "elegir"}
        else:
            x = mejor[3]
            out[iso] = {"codigo": digitos(x.codigo)[:n], "estado": "ok", "dai": x.dai or "", "fuente": x.fuente}
    return out


def _guardar_partidas(p: Producto, partidas: dict | None) -> None:
    previas = {x.pais: x for x in p.partidas}
    for iso in sorted(set(previas) | {k for k in (partidas or {}) if isinstance(k, str) and len(k) == 2}):
        x = (partidas or {}).get(iso)
        if not x or not digitos(x.get("codigo")):
            if iso in previas:
                p.partidas.remove(previas[iso])
            continue
        fila = previas.get(iso) or PartidaPais(pais=iso)
        fila.codigo = digitos(x.get("codigo"))[:14]
        fila.dai = str(x.get("dai") or "")[:10] or None
        fila.estado = str(x.get("estado") or "ok")[:12]
        fila.fuente = (x.get("fuente") or None) and str(x.get("fuente"))[:12]
        fila.manual = bool(x.get("manual"))
        if iso not in previas:
            p.partidas.append(fila)


# ---- Lectura -------------------------------------------------------------------
def _producto(db: Session, user: Usuario, producto_id: int) -> Producto:
    exigir(user, "producto.ver")
    p = db.get(Producto, producto_id)
    if not p:
        raise ErrorNegocio("The product does not exist.", 404, "no_encontrado")
    asegurar_proveedor(user, p.proveedor_id)
    return p


def _paises_completos(p: Producto, ds: list[dict]) -> tuple[int, int]:
    dig = {d["iso"]: d["digitos"] for d in ds}
    ok = sum(1 for x in p.partidas if x.pais in dig and x.estado in ("ok", "auto") and len(digitos(x.codigo)) >= dig[x.pais])
    return ok, len(ds)


def _resumen(p: Producto, tallas: dict, ds: list[dict]) -> dict:
    ok, total = _paises_completos(p, ds)
    foto = p.fotos[0].id if p.fotos else None
    t = tallas.get(p.id, {})
    return {
        "id": p.id, "estilo": p.estilo, "color": p.color, "nombre": p.nombre, "codigo_generico": p.codigo_generico,
        "proveedor_id": p.proveedor_id, "proveedor": p.proveedor.nombre if p.proveedor else None,
        "marca": p.marca.codigo if p.marca else None, "marca_nombre": p.marca.nombre if p.marca else None,
        "grupo": p.grupo.codigo if p.grupo else None, "tipo": p.tipo, "estado": p.estado,
        "estado_txt": ESTADOS.get(p.estado, p.estado),
        "codigo": fmt_codigo(p.codigo) if p.codigo else None, "sugerido": fmt_codigo(p.sugerido) if p.sugerido else None,
        "propuesta": fmt_codigo(p.propuesta) if p.propuesta else None,
        "confianza": p.confianza, "ficha_completa": p.ficha_completa, "faltan": p.faltan or [],
        "paises_ok": ok, "paises_total": total, "foto_id": foto, "pais_origen": p.pais_origen,
        "tallas": t.get("tallas", []), "rango_tallas": rango_tallas(t.get("tallas", [])), "skus": t.get("skus", 0),
        "n_prepacks": t.get("prepacks", 0),
        "unidad": t.get("unidad"), "descripcion_comercial": p.descripcion_comercial,
        "actualizado_en": p.actualizado_en, "version": p.version, "version_ficha": p.version_ficha,
    }


ORDEN_LETRAS = ["XXXS", "XXS", "XS", "S", "M", "L", "XL", "XXL", "XXXL", "4XL", "5XL"]
EQUIV_LETRAS = {"2XS": "XXS", "3XS": "XXXS", "2XL": "XXL", "3XL": "XXXL", "XXXXL": "4XL"}


def rango_tallas(tallas: list[str]) -> str:
    """Tallas en texto corto: tramos seguidos como "7 to 10" y los saltos
    separados por comas ("7 to 9, 11"); igual con S, M, L…"""
    ts = [str(t).strip().upper() for t in tallas if str(t or "").strip()]
    if not ts:
        return ""

    def tramos(valores: list, paso, texto) -> str:
        grupos, actual = [], [valores[0]]
        for v in valores[1:]:
            if abs((v - actual[-1]) - paso) < 1e-9:
                actual.append(v)
            else:
                grupos.append(actual)
                actual = [v]
        grupos.append(actual)
        out = []
        for g in grupos:
            if len(g) >= 3:
                out.append(f"{texto(g[0])}–{texto(g[-1])}")
            else:
                out += [texto(x) for x in g]
        return ", ".join(out)

    try:
        nums = sorted({float(t.replace(",", ".")) for t in ts})
        paso = 0.5 if any(not n.is_integer() for n in nums) else 1
        return tramos(nums, paso, lambda n: str(int(n)) if n.is_integer() else str(n))
    except ValueError:
        pass
    letras = [EQUIV_LETRAS.get(t, t) for t in ts]
    if all(t in ORDEN_LETRAS for t in letras):
        idx = sorted({ORDEN_LETRAS.index(t) for t in letras})
        return tramos(idx, 1, lambda i: ORDEN_LETRAS[i])
    return ", ".join(dict.fromkeys(ts))


def _tallas(db: Session, ids: list[int]) -> dict:
    out: dict[int, dict] = {}
    if not ids:
        return out
    for a in db.scalars(select(Articulo).where(Articulo.producto_id.in_(ids)).order_by(Articulo.id)):
        d = out.setdefault(a.producto_id, {"tallas": [], "skus": 0, "prepacks": 0, "unidad": None})
        if a.tipo == "PREPACK":
            d["prepacks"] += 1
            continue
        d["skus"] += 1
        if a.tipo == "SOLIDO" and a.talla:
            d["tallas"].append(a.talla)
        d["unidad"] = d["unidad"] or (a.unidad if a.tipo == "SOLIDO" else None)
    return out


ORDEN = {"estilo": Producto.estilo, "estado": Producto.estado, "actualizado": Producto.actualizado_en,
         "codigo": Producto.codigo, "tipo": Producto.tipo}


def listar(db: Session, user: Usuario, filtros: dict, page: int, size: int, orden: str | None) -> dict:
    exigir(user, "producto.ver")
    prov = proveedor_filtro(user, filtros.get("proveedor_id"))
    base = select(Producto)
    if prov:
        base = base.where(Producto.proveedor_id == prov)
    if filtros.get("marca_id"):
        ids = [int(x) for x in str(filtros["marca_id"]).split(",") if x.strip().isdigit()]
        base = base.where(Producto.marca_id.in_(ids))
    if filtros.get("grupo_id"):
        base = base.where(Producto.grupo_id == filtros["grupo_id"])
    if filtros.get("tipo"):
        base = base.where(Producto.tipo.in_(str(filtros["tipo"]).split(",")))
    if filtros.get("q"):
        base = base.where(filtro_texto(filtros["q"], lambda p: [
            Producto.estilo.ilike(p), Producto.color.ilike(p), Producto.nombre.ilike(p), Producto.codigo_generico.ilike(p),
            Producto.codigo.ilike(p.replace(".", "")),
            Producto.id.in_(select(Articulo.producto_id).where(or_(Articulo.sku.ilike(p), Articulo.upc.ilike(p))))]))
    # Indicadores por estado con los mismos filtros (menos el de estado)
    sub = base.subquery()
    conteo = {e: n for e, n in db.execute(select(sub.c.estado, func.count()).group_by(sub.c.estado)).all()}
    estado = filtros.get("estado")
    if estado == "pendientes":
        base = base.where(Producto.estado.in_(PENDIENTES))
    elif estado == "borradores":
        base = base.where(Producto.estado.in_(BORRADORES))
    elif estado == "aprobados":
        base = base.where(Producto.estado.in_(APROBADOS))
    elif estado:
        base = base.where(Producto.estado == estado)
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    col, _, direccion = (orden or "actualizado:desc").partition(":")
    campo = ORDEN.get(col, Producto.actualizado_en)
    base = base.order_by(campo.desc() if direccion == "desc" else campo.asc(), Producto.id)
    filas = db.scalars(base.options(selectinload(Producto.partidas), selectinload(Producto.fotos))
                       .offset((page - 1) * size).limit(size)).all()
    tallas = _tallas(db, [p.id for p in filas])
    kpis = {
        "total": sum(conteo.values()),
        "pendientes": sum(conteo.get(e, 0) for e in PENDIENTES),
        "borrador": conteo.get("borrador", 0), "sugerida": conteo.get("sugerida", 0),
        "revision": conteo.get("revision", 0), "borradores": sum(conteo.get(e, 0) for e in BORRADORES),
        "observado": conteo.get("observado", 0),
        "aprobados": sum(conteo.get(e, 0) for e in APROBADOS),
    }
    ds = destinos(db)
    return {"items": [_resumen(p, tallas, ds) for p in filas], "total": total, "page": page, "size": size, "kpis": kpis}


def _historial(db: Session, p: Producto) -> list[dict]:
    filas = db.scalars(select(Historial).where(Historial.entidad == "producto", Historial.entidad_id == p.id)
                       .order_by(Historial.fecha.desc()).limit(80)).all()
    return [{"fecha": h.fecha, "accion": h.accion, "detalle": h.detalle, "motivo": h.motivo,
             "usuario": h.usuario.nombre if h.usuario else None} for h in filas]


def detalle(db: Session, user: Usuario, producto_id: int) -> dict:
    db.flush()  # la sesión no hace autoflush: que se vea lo recién guardado
    p = _producto(db, user, producto_id)
    arts = db.scalars(select(Articulo).where(Articulo.producto_id == p.id).order_by(Articulo.tipo.desc(), Articulo.id)).all()
    pps = db.scalars(select(Prepack).where(Prepack.estilo == p.estilo, Prepack.color == p.color)).all()
    sku_pp = {a.prepack_id: a for a in arts if a.prepack_id}
    ds = destinos(db)
    dig = {d["iso"]: d["digitos"] for d in ds}
    r = _resumen(p, _tallas(db, [p.id]), ds)
    r.update({
        "ficha": p.ficha or {}, "descripcion_aduana": p.descripcion_aduana, "pais_procedencia": p.pais_procedencia,
        "marca_id": p.marca_id, "grupo_id": p.grupo_id,
        "analisis": p.analisis or {}, "alertas_ok": p.alertas_ok or [], "observaciones": p.observaciones,
        "resolucion": p.resolucion, "notas": p.notas, "opinion_ia": p.opinion_ia,
        "revisado_por": p.revisado_por.nombre if p.revisado_por else None, "revisado_en": p.revisado_en,
        "vigente_desde": p.vigente_desde, "creado_en": p.creado_en,
        "partidas": {x.pais: {"codigo": x.codigo, "dai": x.dai or "", "estado": x.estado, "fuente": x.fuente,
                              "manual": x.manual, "digitos": dig.get(x.pais, 10)} for x in p.partidas},
        "fotos": [{"id": f.id, "nombre": f.nombre} for f in p.fotos],
        "versiones": [{"version": v.version, "desde": v.desde, "hasta": v.hasta, "motivo": v.motivo,
                       "codigo": fmt_codigo(v.datos.get("codigo")) if v.datos.get("codigo") else None,
                       "estado": v.datos.get("estado"), "tipo": v.datos.get("tipo"), "cerrado_en": v.cerrado_en}
                      for v in reversed(p.versiones)],
        "articulos": [{"id": a.id, "sku": a.sku, "sku_proveedor": a.sku_proveedor, "upc": a.upc, "talla": a.talla, "unidad": a.unidad, "tipo": a.tipo,
                       "descripcion": a.descripcion, "activo": a.activo, "prepack_id": a.prepack_id} for a in arts],
        "prepacks": [{"id": x.id, "codigo": x.codigo, "descripcion": x.descripcion, "total": x.total,
                      "sku": sku_pp[x.id].sku if x.id in sku_pp else None,
                      "componentes": [{"talla": c.articulo.talla, "sku": c.articulo.sku, "cantidad": c.cantidad}
                                      for c in x.componentes]} for x in pps],
        "historial": _historial(db, p),
        "puede_aprobar": tiene(user, "producto.clasificar"),
    })
    return r


def _inciso_ctx(x: IncisoNacional) -> dict:
    return {"id": x.id, "pais": x.pais, "codigo": x.codigo, "cond": x.cond or {}, "prio": x.prio,
            "dai": x.dai or "", "descripcion": x.descripcion, "nota": x.nota, "fuente": x.fuente}


def contexto(db: Session, user: Usuario, proveedor_id: int | None = None) -> dict:
    """Lo que el motor necesita en el navegador: destinos, historial de
    clasificaciones, códigos nacionales y lo aprendido."""
    exigir(user, "producto.ver")
    prov = proveedor_filtro(user, proveedor_id)
    q = select(Producto).where(Producto.estado.in_(APROBADOS), Producto.codigo.is_not(None))
    if prov:
        q = q.where(Producto.proveedor_id == prov)
    recs = []
    for p in db.scalars(q.order_by(Producto.actualizado_en.desc()).limit(3000)):
        f = p.ficha or {}
        recs.append({"id": p.id, "estilo": p.estilo, "color": p.color, "generico": p.codigo_generico,
                     "tipo": p.tipo, "perfil": p.perfil, "codigo": p.codigo, "desc": p.nombre or p.descripcion_aduana,
                     "descArchivo": p.nombre, "marca": p.marca.nombre if p.marca else None, "comp": f.get("comp") or {},
                     "estiloCalz": f.get("estiloCalz"), "estado": p.estado,
                     "tsMod": int(p.actualizado_en.timestamp() * 1000) if p.actualizado_en else 0})
    incisos = [_inciso_ctx(x) for x in db.scalars(select(IncisoNacional).where(IncisoNacional.activo.is_(True)))]
    marcas = [{"nombre": m.nombre, "codigo": m.codigo, "activa": m.activa} for m in db.scalars(select(Marca))]
    provs = []
    for pr in db.scalars(select(Proveedor)):
        if prov and pr.id != prov:
            continue
        provs.append({"nombre": pr.nombre, "marcas": [m.nombre for m in pr.marcas]})
    return {
        "destinos": destinos(db), "pais_base": settings.PAIS_BASE_CLASIF, "obligatorios": OBLIGATORIOS,
        "recs": recs, "incisos": incisos,
        "notas_sac": notas_contexto(db), "acuerdos": acuerdos_contexto(db),
        "sac": [{"codigo": x.codigo, "descripcion": x.descripcion}
                for x in db.scalars(select(PartidaSAC).where(PartidaSAC.fuente.not_in(("base", "oficial")), PartidaSAC.activo.is_(True)))], "marcas": marcas, "proveedores": provs,
        "palabras": [{"id": x.id, "frase": x.frase, "tipo": x.tipo, "marca": x.marca, **(x.atributos or {})}
                     for x in db.scalars(select(PalabraClave))],
        "sinonimos": [{"palabra": x.palabra, "equivale": x.equivale} for x in db.scalars(select(SinonimoMaterial))],
        "puede_aprobar": tiene(user, "producto.clasificar"),
        "atributos": atributos_cfg(db),
        "dominios_genericos": dominios_ficha(db),
    }


# ---- Guardar la ficha técnica ------------------------------------------------
CAMPOS_TEXTO = {"nombre": 200, "notas": 1000}  # el genérico sale del código de artículo


def _aplicar_resultado(p: Producto, r: dict | None) -> None:
    """Guarda lo que calculó el motor (sin aprobar nada)."""
    if not r:
        return
    if hasattr(r, "model_dump"):
        r = r.model_dump()
    sug = digitos(r.get("sugerido"))
    p.sugerido = sug[:14] if len(sug) >= 6 else None
    p.confianza = (r.get("confianza") or None) and str(r["confianza"])[:10]
    p.fuente = (r.get("fuente") or None) and str(r["fuente"])[:12]
    p.perfil = (r.get("perfil") or None) and str(r["perfil"])[:200]
    p.analisis = {k: r.get(k) for k in ("razones", "fundamento", "alternativas", "avisos", "faltantes", "alertas",
                                        "razones_regla", "codigo_regla", "atributos", "tipo_txt") if r.get(k) is not None}
    if r.get("descripcion_aduana") is not None and not (p.ficha or {}).get("descManual"):
        p.descripcion_aduana = str(r["descripcion_aduana"])[:400] or None
    if not (p.ficha or {}).get("comManual"):
        p.descripcion_comercial = (str(r.get("descripcion_comercial") or "")[:300] or None) or descripcion_comercial_simple(p)
    p.ficha_completa = bool(r.get("completa"))
    p.faltan = [str(x)[:120] for x in (r.get("faltan") or [])][:20]
    if p.estado not in APROBADOS:
        _guardar_partidas(p, r.get("partidas"))
        if p.estado != "revision":
            p.estado = "sugerida" if p.ficha_completa and p.sugerido else "borrador"


def guardar_ficha(db: Session, user: Usuario, producto_id: int, datos) -> dict:
    exigir(user, "producto.ficha")
    p = _producto(db, user, producto_id)
    verificar_version(p, datos.version, "product")
    if p.estado in APROBADOS:
        raise ErrorNegocio("The technical sheet is approved. Create a new version to change it.", 409, "ficha_aprobada")
    if p.estado == "revision" and not tiene(user, "producto.clasificar"):
        raise ErrorNegocio("The technical sheet was sent to review. Take it back to draft to change it.", 409, "en_revision")
    antes = {"tipo": p.tipo, "ficha": p.ficha, "estado": p.estado}
    p.tipo = (datos.tipo or None) and datos.tipo[:30]
    p.ficha = datos.ficha or {}
    for campo, largo in CAMPOS_TEXTO.items():
        v = getattr(datos, campo, None)
        if v is not None:
            setattr(p, campo, str(v).strip()[:largo] or None)
    if datos.pais_origen is not None:
        p.pais_origen = (datos.pais_origen or "").upper()[:2] or None
    if datos.pais_procedencia is not None:
        p.pais_procedencia = (datos.pais_procedencia or "").upper()[:2] or None
    if datos.descripcion_aduana is not None and (p.ficha or {}).get("descManual"):
        p.descripcion_aduana = datos.descripcion_aduana.strip()[:400] or None
    if datos.descripcion_comercial is not None and (p.ficha or {}).get("comManual"):
        p.descripcion_comercial = datos.descripcion_comercial.strip()[:300] or None
    p.alertas_ok = list(datos.alertas_ok or [])[:100]
    devuelto = p.estado == "observado"
    _aplicar_resultado(p, datos.resultado)
    tocar(p)
    cambios = [k for k in ("tipo", "ficha") if antes[k] != getattr(p, k)]
    registrar(db, user, "producto", p.id, "ficha_guardada",
              {"cambios": cambios, "estado": [antes["estado"], p.estado], "sugerido": fmt_codigo(p.sugerido) or None,
               "devuelto": devuelto})
    return detalle(db, user, p.id)


def clasificar_lote(db: Session, user: Usuario, items: list) -> dict:
    """Guarda el resultado del motor para varios productos (sin tocar su ficha)."""
    exigir(user, "producto.ficha")
    hechos, omitidos = 0, []
    for it in items:
        p = _producto(db, user, it.id)
        if p.estado in APROBADOS:
            omitidos.append({"id": p.id, "mensaje": f"{p.estilo} is already approved."})
            continue
        antes = p.estado
        if it.ficha is not None:
            # Solo completa: lo que la ficha ya tenía no cambia
            p.ficha = {**it.ficha, **{k: v for k, v in (p.ficha or {}).items() if v not in (None, "", [], {})}}
            if it.ficha.get("comp"):
                p.ficha["comp"] = {**it.ficha["comp"], **((p.ficha or {}).get("comp") or {})}
        if it.tipo and not p.tipo:
            p.tipo = it.tipo[:30]
        _aplicar_resultado(p, it.resultado)
        tocar(p)
        registrar(db, user, "producto", p.id, "clasificado", {"estado": [antes, p.estado],
                                                              "sugerido": fmt_codigo(p.sugerido) or None})
        hechos += 1
    return {"clasificados": hechos, "omitidos": omitidos}


# ---- Aprobar, devolver y versiones -------------------------------------------
def _aprobar(db: Session, user: Usuario, p: Producto, codigo: str | None, partidas: dict | None) -> None:
    oficial = digitos(codigo or p.propuesta or p.sugerido)
    if len(oficial) < 6:
        raise ErrorNegocio(f"{p.estilo}: there is no HS code to approve.", 422, "sin_partida")
    if len(oficial) > 14:
        raise ErrorNegocio("The HS code is too long.", 422, "validacion")
    parts = partidas if partidas is not None else partidas_simples(db, p, oficial)
    pend = [iso for iso, x in (parts or {}).items() if x.get("estado") == "elegir" and not digitos(x.get("codigo"))]
    if pend:
        raise ErrorNegocio(f"{p.estilo}: choose the national code for " + ", ".join(pend) + ".", 422, "faltan_paises",
                           [{"pais": iso} for iso in pend])
    for iso, x in (parts or {}).items():
        c = digitos(x.get("codigo"))
        if c and not c.startswith(oficial[:6]):
            raise ErrorNegocio(f"The code for {iso} must start with {fmt_codigo(oficial[:6])}.", 422, "validacion")
    sug = digitos(p.sugerido)
    p.estado = "aprobado" if not sug or sug[:6] == oficial[:6] else "corregido"
    p.codigo = oficial[:14]
    p.propuesta = None
    _guardar_partidas(p, parts)
    p.revisado_por_id = user.id
    p.revisado_en = ahora()
    tocar(p)
    registrar(db, user, "producto", p.id, "aprobado" if p.estado == "aprobado" else "corregido",
              {"codigo": fmt_codigo(oficial), "sugerido": fmt_codigo(sug) or None,
               "paises": {iso: fmt_codigo(x.get("codigo")) for iso, x in (parts or {}).items() if x.get("codigo")}})


def aprobar(db: Session, user: Usuario, producto_id: int, datos) -> dict:
    exigir(user, "producto.clasificar")
    p = _producto(db, user, producto_id)
    verificar_version(p, datos.version, "product")
    if not p.ficha_completa and not datos.forzar:
        raise ErrorNegocio("The technical sheet is incomplete: " + ", ".join(p.faltan[:4]) + ".", 422, "ficha_incompleta",
                           [{"mensaje": x} for x in p.faltan])
    _aprobar(db, user, p, datos.codigo, datos.partidas)
    return detalle(db, user, p.id)


def aprobar_lote(db: Session, user: Usuario, ids: list[int]) -> dict:
    """Aprueba la partida sugerida de varios productos con su ficha completa.
    Cada uno se aprueba o no por su cuenta; se informa cuáles no."""
    exigir(user, "producto.clasificar")
    ok, errores = 0, []
    for pid in ids:
        p = _producto(db, user, pid)
        if p.estado in APROBADOS:
            continue
        if p.estado not in ("sugerida", "revision") or not p.ficha_completa:
            errores.append({"id": p.id, "mensaje": f"{p.estilo} {p.color or ''}: the sheet is not complete.".replace(" :", ":")})
            continue
        try:
            with db.begin_nested():
                partidas = {x.pais: {"codigo": x.codigo, "dai": x.dai, "estado": x.estado, "fuente": x.fuente,
                                     "manual": x.manual} for x in p.partidas} or None
                _aprobar(db, user, p, None, partidas)
            ok += 1
        except ErrorNegocio as e:
            errores.append({"id": p.id, "mensaje": e.mensaje})
    return {"aprobados": ok, "errores": errores}


def observar(db: Session, user: Usuario, producto_id: int, datos) -> dict:
    """Observaciones del especialista; con `devolver`, la ficha vuelve al
    proveedor para que la corrija."""
    exigir(user, "producto.clasificar")
    p = _producto(db, user, producto_id)
    verificar_version(p, datos.version, "product")
    p.observaciones = (datos.observaciones or "").strip()[:2000] or None
    p.resolucion = (datos.resolucion or "").strip()[:200] or None
    if datos.devolver:
        if p.estado in APROBADOS:
            raise ErrorNegocio("An approved sheet cannot be returned; create a new version.", 409, "ficha_aprobada")
        if not p.observaciones:
            raise ErrorNegocio("Write what the supplier has to fix.", 422, "motivo_requerido")
        p.estado = "observado"
    tocar(p)
    registrar(db, user, "producto", p.id, "devuelto" if datos.devolver else "observacion",
              {"observaciones": p.observaciones, "resolucion": p.resolucion})
    return detalle(db, user, p.id)


def enviar_revision(db: Session, user: Usuario, ids: list[int]) -> dict:
    """Envía fichas en borrador a revisión: deben estar completas y con partida."""
    exigir(user, "producto.ficha")
    ok, errores = 0, []
    for pid in ids:
        p = _producto(db, user, pid)
        nombre = f"{p.estilo} {p.color or ''}".strip()
        if p.estado not in BORRADORES:
            errores.append({"id": p.id, "mensaje": f"{nombre} is {ESTADOS.get(p.estado, p.estado).lower()}."})
            continue
        if not p.ficha_completa or not p.sugerido:
            falta = ", ".join((p.faltan or [])[:4]) or "the HS code"
            errores.append({"id": p.id, "mensaje": f"{nombre}: complete the sheet first ({falta})."})
            continue
        antes = p.estado
        p.estado = "revision"
        tocar(p)
        registrar(db, user, "producto", p.id, "enviado", {"estado": [antes, p.estado]})
        ok += 1
    if len(ids) == 1 and errores:
        raise ErrorNegocio(errores[0]["mensaje"], 422, "no_enviado", errores)
    return {"enviados": ok, "errores": errores}


def retirar_revision(db: Session, user: Usuario, producto_id: int) -> dict:
    """Vuelve a borrador una ficha enviada (para corregirla antes de que la revisen)."""
    exigir(user, "producto.ficha")
    p = _producto(db, user, producto_id)
    if p.estado != "revision":
        raise ErrorNegocio("Only a sheet in review can go back to draft.", 409, "estado")
    p.estado = "sugerida" if p.ficha_completa and p.sugerido else "borrador"
    tocar(p)
    registrar(db, user, "producto", p.id, "retirado", {"estado": ["revision", p.estado]})
    return detalle(db, user, p.id)


def nueva_version(db: Session, user: Usuario, producto_id: int, datos) -> dict:
    """Cierra la ficha vigente con su partida y abre una copia para editar."""
    exigir(user, "producto.ficha")
    p = _producto(db, user, producto_id)
    verificar_version(p, datos.version, "product")
    desde = datos.desde or date.today()
    inicio = p.vigente_desde or (p.creado_en.date() if p.creado_en else desde)
    if desde <= inicio and p.versiones:
        raise ErrorNegocio("The new version must start after the current one.", 422, "validacion")
    db.add(ProductoVersion(
        producto=p, version=p.version_ficha, desde=inicio, hasta=desde - timedelta(days=1), motivo=(datos.motivo or "")[:300] or None,
        datos={"tipo": p.tipo, "ficha": p.ficha, "codigo": p.codigo, "sugerido": p.sugerido, "estado": p.estado,
               "descripcion_aduana": p.descripcion_aduana, "descripcion_comercial": p.descripcion_comercial,
               "pais_origen": p.pais_origen, "analisis": p.analisis, "confianza": p.confianza,
               "partidas": {x.pais: {"codigo": x.codigo, "dai": x.dai, "estado": x.estado, "fuente": x.fuente,
                                     "manual": x.manual} for x in p.partidas},
               "revisado_por": p.revisado_por.nombre if p.revisado_por else None,
               "revisado_en": p.revisado_en.isoformat() if p.revisado_en else None},
        cerrado_por=user.id))
    p.version_ficha += 1
    p.vigente_desde = desde
    p.estado = "borrador"
    p.codigo = None
    p.revisado_por = None
    p.revisado_en = None
    p.partidas.clear()
    tocar(p)
    registrar(db, user, "producto", p.id, "nueva_version",
              {"version": p.version_ficha, "desde": desde.isoformat()}, motivo=datos.motivo)
    return detalle(db, user, p.id)


def guardar_opinion(db: Session, user: Usuario, producto_id: int, opinion: dict) -> None:
    p = _producto(db, user, producto_id)
    p.opinion_ia = opinion


# ---- Fotos ---------------------------------------------------------------------
def subir_foto(db: Session, user: Usuario, producto_id: int, nombre: str, tipo: str, contenido: bytes) -> dict:
    exigir(user, "producto.ficha")
    p = _producto(db, user, producto_id)
    if tipo not in TIPOS_FOTO:
        raise ErrorNegocio("Upload a JPG, PNG or WebP image.", 422, "validacion")
    if len(contenido) > 8 * 1024 * 1024:
        raise ErrorNegocio("The photo exceeds 8 MB.", 413, "archivo_grande")
    if len(p.fotos) >= 8:
        raise ErrorNegocio("A product can have up to 8 photos.", 422, "validacion")
    carpeta = os.path.join(settings.UPLOAD_DIR, "productos", str(p.id))
    os.makedirs(carpeta, exist_ok=True)
    ruta = os.path.join(carpeta, uuid.uuid4().hex + TIPOS_FOTO[tipo])
    with open(ruta, "wb") as fh:
        fh.write(contenido)
    seguro = "".join(c for c in os.path.basename(nombre or "photo") if c.isalnum() or c in "._- ")[:200] or "photo"
    f = ProductoFoto(nombre=seguro, ruta=ruta, tipo_mime=tipo, tamano=len(contenido), subido_por=user.id)
    p.fotos.append(f)
    db.flush()
    registrar(db, user, "producto", p.id, "foto_agregada", {"foto": seguro})
    return {"id": f.id, "nombre": f.nombre}


def borrar_foto(db: Session, user: Usuario, producto_id: int, foto_id: int) -> None:
    exigir(user, "producto.ficha")
    p = _producto(db, user, producto_id)
    f = next((x for x in p.fotos if x.id == foto_id), None)
    if not f:
        raise ErrorNegocio("The photo does not exist.", 404, "no_encontrado")
    p.fotos.remove(f)
    try:
        os.remove(f.ruta)
    except OSError:
        pass
    registrar(db, user, "producto", p.id, "foto_quitada", {"foto": f.nombre})


def obtener_foto(db: Session, user: Usuario, foto_id: int) -> ProductoFoto:
    f = db.get(ProductoFoto, foto_id)
    if not f:
        raise ErrorNegocio("The photo does not exist.", 404, "no_encontrado")
    _producto(db, user, f.producto_id)
    return f


# ---- Lo que aprende el clasificador ----------------------------------------------
def ensenar_inciso(db: Session, user: Usuario, datos) -> dict:
    exigir(user, "producto.clasificar")
    pais = (datos.pais or "").upper()
    p_ = db.scalar(select(PaisArancel).where(PaisArancel.iso == pais, PaisArancel.activo.is_(True)))
    if not p_:
        raise ErrorNegocio("Choose a destination country.", 422, "validacion")
    cod = digitos(datos.codigo)
    if msg := p_.error_longitud(cod):
        raise ErrorNegocio(msg, 422, "validacion")
    cond = {k: v for k, v in (datos.cond or {}).items() if v not in (None, "")}
    ya = db.scalar(select(IncisoNacional).where(IncisoNacional.pais == pais, IncisoNacional.codigo == cod))
    if ya and (ya.cond or {}) == cond:
        ya.dai = (datos.dai or ya.dai or None)
        return {"id": ya.id}
    x = IncisoNacional(pais=pais, codigo=cod, sub6=cod[:6], cond=cond, dai=(datos.dai or "").replace("%", "")[:10] or None,
                       nota=(datos.nota or "")[:300] or None, fuente="aprendido", creado_por=user.id)
    db.add(x)
    db.flush()
    return {"id": x.id}


def borrar_inciso(db: Session, user: Usuario, inciso_id: int) -> None:
    exigir(user, "producto.clasificar")
    x = db.get(IncisoNacional, inciso_id)
    if not x:
        raise ErrorNegocio("The national code does not exist.", 404, "no_encontrado")
    db.delete(x)


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


# ---- Base de códigos nacionales -------------------------------------------------
def notas_contexto(db: Session) -> list[dict]:
    return [{"id": n.id, "ambito": n.ambito, "codigo": n.codigo, "numero": n.numero, "texto": n.texto,
             "capitulos": n.capitulos or [], "claves": n.claves or []}
            for n in db.scalars(select(NotaSAC).where(NotaSAC.activo.is_(True)).order_by(NotaSAC.id))]


def notas_de(db: Session, codigo: str | None) -> list:
    """Notas legales que aplican a una subpartida: las reglas generales, las de
    su sección y las de su capítulo."""
    cap = (codigo or "")[:2]
    return [n for n in db.scalars(select(NotaSAC).where(NotaSAC.activo.is_(True)).order_by(NotaSAC.id))
            if not n.capitulos or cap in (n.capitulos or [])]


def cargar_incisos_base(db: Session) -> int:
    """Países destino, el SAC oficial (Arancel Centroamericano de Importación,
    VII Enmienda, SIECA) con sus partidas, subpartidas y notas legales, y los
    códigos nacionales: los incisos del ACI con su DAI para los países que usan
    los 10 dígitos del SAC y la base de artículos de la empresa para el resto."""
    for i, d in enumerate(DESTINOS):
        db.add(PaisArancel(iso=d["iso"], nombre=d["nombre"], digitos=d["digitos"], mcca=d["mcca"],
                           impuesto=d["impuesto"], base_legal=d.get("base_legal"), orden=i))
    carpeta = Path(__file__).resolve().parent.parent / "data"
    leer = lambda nombre: json.loads((carpeta / nombre).read_text(encoding="utf-8"))  # noqa: E731
    oficiales = {x["codigo"] for x in leer("sac_oficial.json")}
    for x in leer("sac_oficial.json"):
        db.add(PartidaSAC(codigo=x["codigo"], descripcion=x["descripcion"][:400], fuente="oficial"))
    for x in leer("sac_base.json"):
        if x["codigo"] not in oficiales:
            db.add(PartidaSAC(codigo=x["codigo"], descripcion=x["descripcion"][:400], fuente="base"))
    for x in leer("sac_notas.json"):
        db.add(NotaSAC(ambito=x["ambito"], codigo=x["codigo"], numero=x["numero"], texto=x["texto"],
                       capitulos=x.get("capitulos") or [], claves=x.get("claves") or [], fuente="oficial"))
    # Notas explicativas: resúmenes propios por partida (el texto oficial de la
    # OMA tiene derechos de autor; se puede cargar el propio desde Excel)
    for x in leer("sac_explicativas.json"):
        db.add(NotaSAC(ambito=x["ambito"], codigo=x["codigo"], numero=x["numero"], texto=x["texto"],
                       capitulos=x.get("capitulos") or [], claves=x.get("claves") or [], fuente="resumen"))
    # Incisos del ACI (10 dígitos) de los capítulos que clasifica el motor, para
    # los países del SAC a 10 dígitos; los demás se cargan desde Aranceles
    capitulos = set(meta_motor()["capitulos"])
    aci = {x["codigo"]: x for x in leer("aci_incisos.json") if x["codigo"][:2] in capitulos}
    base = leer("incisos_base.json")
    diez = [d["iso"] for d in DESTINOS if d["digitos"] == 10 and d["mcca"]]
    cond_base = {(x["pais"], x["codigo"]): x for x in base}
    filas = []
    for pais in diez:
        for cod, x in aci.items():
            b = cond_base.get((pais, cod))
            filas.append({"pais": pais, "codigo": cod, "sub6": cod[:6], "cond": (b or {}).get("cond") or x["cond"],
                          "prio": (b or {}).get("prio") or 0, "dai": x["dai_txt"] or "", "descripcion": x["descripcion"][:300],
                          "fuente": "oficial", "nota": "ACI SIECA VII Enmienda, versión 6 (agosto 2025)", "activo": True})
    for x in base:
        if x["pais"] in diez and x["codigo"] in aci:
            continue
        filas.append({"pais": x["pais"], "codigo": x["codigo"], "sub6": x["codigo"][:6], "cond": x.get("cond") or {},
                      "prio": x.get("prio") or 0, "dai": None, "descripcion": None, "fuente": "base",
                      "nota": f"Company item base ({x.get('articulos', 0)} items)", "activo": True})
    db.flush()
    # Inserción masiva de los códigos (son miles); las condiciones que eligen
    # cada código van aparte, como reglas de selección nacional
    sin = [{k: v for k, v in f.items() if k not in ("cond", "prio")} for f in filas if not (f["cond"] or f["prio"])]
    db.execute(insert(IncisoNacional), sin)
    for f in filas:
        if f["cond"] or f["prio"]:
            db.add(IncisoNacional(**f))
    db.flush()
    cargar_acuerdos(db)
    return len(filas)


# ---- Proveedores y catálogos para la pantalla -------------------------------------
def opciones(db: Session, user: Usuario) -> dict:
    exigir(user, "producto.ver")
    prov = proveedor_filtro(user)
    provs = db.scalars(select(Proveedor).where(Proveedor.activo.is_(True)).order_by(Proveedor.nombre)).all()
    return {
        "proveedores": [{"id": x.id, "nombre": x.nombre} for x in provs if not prov or x.id == prov],
        "marcas": [{"id": m.id, "codigo": m.codigo, "nombre": m.nombre} for m in db.scalars(select(Marca).order_by(Marca.codigo))],
        "grupos": [{"id": g.id, "codigo": g.codigo, "nombre": g.nombre} for g in db.scalars(select(GrupoArticulo).order_by(GrupoArticulo.codigo))],
        "estados": ESTADOS,
        "paises": [{"codigo": x.codigo, "nombre": x.nombre} for x in db.scalars(select(Pais).order_by(Pais.nombre))],
    }


def ficha_de_version(db: Session, user: Usuario, producto_id: int, version: int | None = None) -> dict:
    """La ficha vigente o, con `version`, la copia cerrada de una versión anterior."""
    d = detalle(db, user, producto_id)
    if not version or version == d["version_ficha"]:
        return d
    p = _producto(db, user, producto_id)
    v = next((x for x in p.versiones if x.version == version), None)
    if not v:
        raise ErrorNegocio(f"Version {version} does not exist.", 404, "no_encontrado")
    x = v.datos or {}
    partidas = x.get("partidas") or {}
    return {**d, "version_ficha": v.version, "tipo": x.get("tipo"), "ficha": x.get("ficha") or {},
            "codigo": fmt_codigo(x.get("codigo")) if x.get("codigo") else None,
            "sugerido": fmt_codigo(x.get("sugerido")) if x.get("sugerido") else None,
            "estado": x.get("estado"), "estado_txt": ESTADOS.get(x.get("estado"), x.get("estado")),
            "descripcion_aduana": x.get("descripcion_aduana"), "descripcion_comercial": x.get("descripcion_comercial"),
            "pais_origen": x.get("pais_origen"), "analisis": x.get("analisis") or {}, "confianza": x.get("confianza"),
            "partidas": {k: (c if isinstance(c, dict) else {"codigo": c}) for k, c in partidas.items()},
            "revisado_por": x.get("revisado_por"), "revisado_en": x.get("revisado_en"), "observaciones": None,
            "vigencia": {"desde": v.desde, "hasta": v.hasta, "motivo": v.motivo}, "historica": True}


def ver_version(db: Session, user: Usuario, producto_id: int, version: int) -> dict:
    from . import documentos
    d = ficha_de_version(db, user, producto_id, version)
    return {"version": d["version_ficha"], "vigencia": d.get("vigencia"), "estado_txt": d.get("estado_txt"),
            **documentos.secciones_ficha(d)}


def exportar_ficha(db: Session, user: Usuario, producto_id: int, formato: str = "pdf",
                   version: int | None = None) -> tuple[bytes, str]:
    from . import documentos, exportar
    d = ficha_de_version(db, user, producto_id, version)
    nombre = f"ficha_{d['estilo']}_{digitos(d['color'])[:6] or d['id']}" + (f"_v{d['version_ficha']}" if version else "")
    if formato == "xlsx":
        return exportar.exportar_ficha(d, documentos.secciones_ficha(d)), nombre
    return documentos.pdf_ficha_producto(d), nombre


def exportar_lista(db: Session, user: Usuario, filtros: dict, orden: str | None, formato: str) -> bytes:
    """Reporte de productos con su composición, descripción aduanal y el
    código nacional guardado para cada país destino."""
    from . import documentos, exportar
    r = listar(db, user, filtros, 1, 100_000, orden)
    k = r["kpis"]
    indicadores = [("Products", f"{k['total']:,}"), ("Drafts", f"{k['borradores']:,}"), ("In review", f"{k['revision']:,}"),
                   ("Returned", f"{k['observado']:,}"), ("Approved", f"{k['aprobados']:,}")]
    ids = [p["id"] for p in r["items"]]
    prods = {p.id: p for p in db.scalars(select(Producto).where(Producto.id.in_(ids))
                                         .options(selectinload(Producto.partidas)))} if ids else {}
    paises = [d["iso"] for d in destinos(db)]

    def comp(p: Producto | None) -> str:
        c = ((p.ficha or {}).get("comp") or {}) if p else {}
        return " · ".join(f"{documentos.PARTES.get(k, k.capitalize())}: {v}" for k, v in c.items() if v) if isinstance(c, dict) else ""

    def codigos(p: Producto | None) -> dict:
        return {x.pais: fmt_codigo(x.codigo) for x in (p.partidas if p else []) if x.codigo}

    nombres = {"q": "Search", "estado": "Status", "tipo": "Type", "proveedor_id": "Supplier", "marca_id": "Brand"}
    texto = " · ".join(f"{nombres.get(c, c)}: {v}" for c, v in filtros.items() if v not in (None, ""))
    texto = f"Filters: {texto}" if texto else "No filters"
    titulo, sub = "Products and tariff classification", "Technical sheets, composition, HS codes and national codes by destination"
    if formato == "pdf":
        columnas = [("Generic", 1, False), ("Style", 1, False), ("Color", 1.1, False), ("Supplier", 1, False), ("Type", 0.8, False),
                    ("Status", 0.8, False), ("HS code", 0.8, False), ("Origin", 0.5, False), ("Composition", 2.6, False)] \
            + [(iso, 1, False) for iso in paises]
        filas = []
        for p in r["items"]:
            cods = codigos(prods.get(p["id"]))
            filas.append([p["codigo_generico"] or "—", p["estilo"], p["color"], p["proveedor"] or "—", p["tipo"] or "—", p["estado_txt"],
                          p["codigo"] or "—", p["pais_origen"] or "—", comp(prods.get(p["id"])) or "—"]
                         + [cods.get(iso, "—") for iso in paises])
        return documentos.pdf_reporte(titulo, sub, texto, indicadores, columnas, [[str(v) for v in f] for f in filas])
    columnas = [("Generic", 1, False), ("Style", 1.1, False), ("Color", 1.3, False), ("Name", 1.8, False), ("Supplier", 1.2, False),
                ("Brand", 0.7, False), ("Type", 0.9, False), ("Status", 0.9, False), ("Version", 0.6, True), ("HS code", 0.9, False),
                ("Suggested", 0.9, False), ("Origin", 0.6, False), ("Customs description", 4, False),
                ("Commercial description", 1.8, False), ("Composition", 4, False)] \
        + [(f"Code {iso}", 1.4, False) for iso in paises] + [("SKUs", 0.5, True)]
    filas, partes, codigos_filas = [], [], []
    for p in r["items"]:
        pr = prods.get(p["id"])
        cods = codigos(pr)
        filas.append([p["codigo_generico"] or "—", p["estilo"], p["color"], p["nombre"] or "—", p["proveedor"] or "—",
                      p["marca"] or "—", p["tipo"] or "—", p["estado_txt"], pr.version_ficha if pr else 1, p["codigo"] or "—",
                      p["sugerido"] or "—", p["pais_origen"] or "—", (pr.descripcion_aduana if pr else None) or "—",
                      p.get("descripcion_comercial") or "—", comp(pr) or "—"]
                     + [cods.get(iso, "—") for iso in paises] + [p["skus"]])
        c = ((pr.ficha or {}).get("comp") or {}) if pr else {}
        for parte, materiales in (c.items() if isinstance(c, dict) else []):
            if materiales:
                partes.append([p["codigo_generico"] or "—", p["estilo"], p["color"], documentos.PARTES.get(parte, parte.capitalize()),
                               str(materiales)])
        for x in (pr.partidas if pr else []):
            codigos_filas.append([p["codigo_generico"] or "—", p["estilo"], p["color"], x.pais, fmt_codigo(x.codigo) or "—",
                                  f"{x.dai}%" if x.dai not in (None, "") else "—", documentos.ESTADO_PARTIDA.get(x.estado, x.estado or "—"),
                                  "By hand" if x.manual else (x.fuente or "—").capitalize()])
    hojas = [
        {"titulo": "Composition", "columnas": [("Generic", 1, False), ("Style", 1.1, False), ("Color", 1.3, False),
                                               ("Part", 1.6, False), ("Materials", 5, False)], "filas": partes},
        {"titulo": "National codes", "columnas": [("Generic", 1, False), ("Style", 1.1, False), ("Color", 1.3, False),
                                                  ("Country", 0.7, False), ("Code", 1.6, False), ("Duty (DAI)", 0.9, False),
                                                  ("Status", 0.9, False), ("Source", 0.9, False)], "filas": codigos_filas},
    ]
    return exportar.exportar_reporte(titulo, sub, texto, indicadores, columnas, filas, hojas)
