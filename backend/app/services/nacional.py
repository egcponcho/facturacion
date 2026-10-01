"""Capa nacional oficial (paquete 03): códigos nacionales con versión y fuente,
regulaciones (permisos, licencias, registros…) e impuestos por país, y de qué
fuente sale cada tipo de dato por país (Country_Source_Map).

Regla del paquete: nunca mezclar el dato oficial con atributos del producto ni
con reglas del motor. Validaciones (hoja Import_Validation): el país existe y
está activo, la versión y la fuente existen, el código se guarda completo (no se
completan dígitos), cuelga de un nodo SAC/HS existente, sin duplicados de país +
versión + código, vigencia coherente, DAI numérico, cada regulación resuelve a
un código o patrón y cada impuesto tiene fuente o base legal.
"""
import json
import re
from datetime import date

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..models import (
    FuenteOficial,
    IncisoNacional,
    NodoArancel,
    PaisArancel,
    Regulacion,
    ReglaImpuesto,
    Usuario,
    VersionDataset,
)
from .common import ErrorNegocio, exigir, filtro_texto, registrar
from .oficial import _fecha, _si, _txt

TIPOS_REGULACION = ("PERMIT", "LICENSE", "REGISTRATION", "CERTIFICATE", "LABELING", "SANITARY", "PHYTOSANITARY", "TECHNICAL",
                    "QUOTA", "PROHIBITION", "OTHER")
TIPOS_IMPUESTO = ("DAI", "IVA", "ITBMS", "ISV", "ISC", "SELECTIVO", "OTRO")
AMBITOS = ("NATIONAL_CODE", "SUBHEADING", "HEADING", "CHAPTER", "PATTERN")


def _dig(v) -> str:
    return re.sub(r"\D", "", str(v or ""))


def _num(v) -> float | None:
    t = _txt(v)
    if t is None:
        return None
    try:
        return float(t.replace("%", "").replace(",", ".").strip())
    except ValueError:
        raise ValueError(f"{t} is not a number") from None


def patron_norm(v) -> str | None:
    """«*» = todos los códigos; si no, los dígitos del prefijo (6404, 6404.19, 3304*)."""
    t = (_txt(v) or "").strip()
    if t in ("*", "ALL", "all"):
        return "*"
    d = _dig(t)
    return d if len(d) >= 2 else None


def aplica(patron: str, codigo: str) -> bool:
    return patron == "*" or _dig(codigo).startswith(patron)


# ---- Carga ------------------------------------------------------------------------
def importar_hojas(db: Session, hojas: dict, cuenta, error) -> None:
    fuentes = {x.codigo: x for x in db.scalars(select(FuenteOficial))}
    versiones = {x.codigo: x for x in db.scalars(select(VersionDataset))}
    paises = {x.iso: x for x in db.scalars(select(PaisArancel))}

    def comun(hoja, f, *, version_obligatoria=False):
        """País, versión, fuente y vigencia; devuelve None si hay error."""
        iso = (_txt(f.get("country")) or "").upper()
        if iso not in paises or not paises[iso].activo:
            error(hoja, f["_fila"], f"Country {iso or '(empty)'} does not exist or is not active.")
            return None
        ver = _txt(f.get("version"))
        if (ver or version_obligatoria) and ver not in versiones:
            error(hoja, f["_fila"], f"Version {ver or '(empty)'} does not exist. Load it in Versions first.")
            return None
        src = _txt(f.get("source_id"))
        if src and src not in fuentes:
            error(hoja, f["_fila"], f"Source {src} does not exist.")
            return None
        try:
            desde, hasta = _fecha(f.get("valid_from")), _fecha(f.get("valid_to"))
        except ValueError as e:
            error(hoja, f["_fila"], str(e))
            return None
        if desde and hasta and hasta < desde:
            error(hoja, f["_fila"], "Valid to must be on or after valid from.")
            return None
        return {"pais": iso, "version": versiones.get(ver), "fuente": fuentes.get(src), "desde": desde, "hasta": hasta}

    # Fuentes por país y tipo de dato
    for f in hojas.get("Country_Source_Map", []):
        iso = (_txt(f.get("country")) or "").upper()
        if iso not in paises:
            error("Country_Source_Map", f["_fila"], f"Country {iso or '(empty)'} does not exist.")
            continue
        p = paises[iso]
        malas = [s for s in (_txt(f.get(k)) for k in ("national_code_source", "regulation_source", "tax_source")) if s and s not in fuentes]
        if malas:
            error("Country_Source_Map", f["_fila"], f"Source {malas[0]} does not exist.")
            continue
        if s := _txt(f.get("national_code_source")):
            p.fuente_id = fuentes[s].id
        if s := _txt(f.get("regulation_source")):
            p.fuente_regulaciones_id = fuentes[s].id
        if s := _txt(f.get("tax_source")):
            p.fuente_impuestos_id = fuentes[s].id
        p.ingesta, p.autenticacion_fuente = _txt(f.get("preferred_ingestion")), _txt(f.get("auth"))
        p.estado_fuente = _txt(f.get("current_status"))
        cuenta("Country_Source_Map", False)

    # Códigos nacionales oficiales
    vistos = set()
    for f in hojas.get("National_Codes", []):
        c = comun("National_Codes", f, version_obligatoria=True)
        if not c:
            continue
        cod = _dig(f.get("full_display_code"))
        if not cod:
            error("National_Codes", f["_fila"], "The full code is required (missing digits are never inferred).")
            continue
        if msg := paises[c["pais"]].error_longitud(cod):
            error("National_Codes", f["_fila"], msg)
            continue
        base = _dig(f.get("base_sac_code")) or _dig(f.get("base_hs6"))
        if base and not cod.startswith(base):
            error("National_Codes", f["_fila"], f"The code {cod} does not start with its base code {base}.")
            continue
        # Cuelga del nodo SAC/HS más profundo que sea prefijo de su base (mínimo la subpartida)
        ref = base or cod
        prefijos = [ref[:n] for n in range(len(ref), 5, -1)]
        if not db.scalar(select(NodoArancel.id).where(NodoArancel.codigo_norm.in_(prefijos), NodoArancel.pais.is_(None)).limit(1)):
            error("National_Codes", f["_fila"], f"The base SAC/HS code {ref[:6]} does not exist in the tariff tree.")
            continue
        clave = (c["pais"], c["version"].id, cod)
        if clave in vistos:
            error("National_Codes", f["_fila"], f"Duplicate country + version + code: {c['pais']} {cod}.")
            continue
        vistos.add(clave)
        try:
            dai = _num(f.get("dai"))
        except ValueError:
            error("National_Codes", f["_fila"], "DAI must be a numeric percentage.")
            continue
        x = db.scalar(select(IncisoNacional).where(IncisoNacional.pais == c["pais"], IncisoNacional.codigo == cod,
                                                   or_(IncisoNacional.version_id == c["version"].id, IncisoNacional.version_id.is_(None)),
                                                   IncisoNacional.fuente.in_(("oficial", "archivo", "base")))
                      .order_by(IncisoNacional.version_id.is_(None)))
        nuevo = x is None
        x = x or IncisoNacional(pais=c["pais"], codigo=cod, sub6=cod[:6])
        x.fuente = "oficial"
        x.codigo_oficial = _txt(f.get("national_code_id"))
        x.codigo_base = base or None
        x.version_id, x.fuente_id = c["version"].id, c["fuente"].id if c["fuente"] else None
        x.vigente_desde, x.vigente_hasta = c["desde"], c["hasta"]
        x.descripcion = (_txt(f.get("official_description")) or x.descripcion or "")[:300] or None
        if dai is not None:
            x.dai = f"{dai:g}"
        x.url, x.nota = _txt(f.get("source_url")), _txt(f.get("internal_note")) or x.nota
        estado = (_txt(f.get("status")) or "").upper()
        x.activo = _si(f.get("active")) if f.get("active") is not None else estado not in ("ARCHIVED", "INACTIVE")
        db.add(x)
        cuenta("National_Codes", nuevo)

    # Regulaciones
    for f in hojas.get("Regulations", []):
        cod = _txt(f.get("regulation_id"))
        if not cod:
            error("Regulations", f["_fila"], "Regulation ID is required.")
            continue
        c = comun("Regulations", f)
        if not c:
            continue
        patron = patron_norm(f.get("code_pattern"))
        tipo = (_txt(f.get("regulation_type")) or "OTHER").upper()
        if not patron:
            error("Regulations", f["_fila"], "Each regulation needs a code or pattern (e.g. 3304*, 6404.19 or * for all).")
            continue
        if tipo not in TIPOS_REGULACION:
            error("Regulations", f["_fila"], f"Regulation type must be one of {', '.join(TIPOS_REGULACION)}.")
            continue
        try:
            cond = json.loads(_txt(f.get("condition_json")) or "null")
        except json.JSONDecodeError:
            error("Regulations", f["_fila"], "Condition JSON is not valid JSON.")
            continue
        if not _txt(f.get("requirement_name")):
            error("Regulations", f["_fila"], "Requirement name is required.")
            continue
        x = db.scalar(select(Regulacion).where(Regulacion.codigo == cod))
        nuevo = x is None
        x = x or Regulacion(codigo=cod)
        amb = (_txt(f.get("scope_type")) or "PATTERN").upper()
        x.pais, x.tipo_ambito, x.patron, x.tipo = c["pais"], amb if amb in AMBITOS else "PATTERN", patron, tipo
        x.version_id = c["version"].id if c["version"] else None
        x.nombre, x.autoridad = _txt(f.get("requirement_name"))[:300], _txt(f.get("authority"))
        x.codigo_permiso = _txt(f.get("permit_license_code"))
        x.obligatorio = _si(f.get("mandatory")) if f.get("mandatory") is not None else True
        x.condicion = cond if isinstance(cond, dict) else None
        x.base_legal, x.url, x.nota = _txt(f.get("legal_basis")), _txt(f.get("source_url")), _txt(f.get("notes"))
        x.activo = _si(f.get("active")) if f.get("active") is not None else True
        x.vigente_desde, x.vigente_hasta = c["desde"], c["hasta"]
        x.fuente_id = c["fuente"].id if c["fuente"] else None
        db.add(x)
        cuenta("Regulations", nuevo)

    # Impuestos
    for f in hojas.get("Taxes", []):
        cod = _txt(f.get("tax_rule_id"))
        if not cod:
            error("Taxes", f["_fila"], "Tax rule ID is required.")
            continue
        c = comun("Taxes", f)
        if not c:
            continue
        tipo = (_txt(f.get("tax_type")) or "").upper()
        patron = patron_norm(f.get("code_pattern")) or ("*" if not _txt(f.get("code_pattern")) else None)
        if tipo not in TIPOS_IMPUESTO or not patron:
            error("Taxes", f["_fila"], f"Tax type ({', '.join(TIPOS_IMPUESTO)}) and a valid code pattern are required.")
            continue
        base_legal = _txt(f.get("legal_basis_notes"))
        if not c["fuente"] and not base_legal:
            error("Taxes", f["_fila"], "Every tax rule needs an official source or its legal basis.")
            continue
        try:
            tasa, desde, hasta = _num(f.get("rate")), _num(f.get("threshold_from")), _num(f.get("threshold_to"))
        except ValueError as e:
            error("Taxes", f["_fila"], f"Rate and thresholds must be numbers: {e}.")
            continue
        x = db.scalar(select(ReglaImpuesto).where(ReglaImpuesto.codigo == cod))
        nuevo = x is None
        x = x or ReglaImpuesto(codigo=cod)
        x.pais, x.patron, x.tipo, x.tasa = c["pais"], patron, tipo, tasa
        x.version_id = c["version"].id if c["version"] else None
        x.base_calculo, x.umbral_desde, x.umbral_hasta = _txt(f.get("basis")), desde, hasta
        x.formula, x.base_legal, x.url = _txt(f.get("formula_rule")), base_legal, _txt(f.get("source_url"))
        x.activo = _si(f.get("active")) if f.get("active") is not None else True
        x.vigente_desde, x.vigente_hasta = c["desde"], c["hasta"]
        x.fuente_id = c["fuente"].id if c["fuente"] else None
        db.add(x)
        cuenta("Taxes", nuevo)
    db.flush()


def impuestos_generales(db: Session) -> int:
    """Demostración: el impuesto general a la importación de cada país (lo que
    ya dice el país, p. ej. «VAT 12%») como regla con su fuente de impuestos."""
    n = 0
    tipos = {"VAT": "IVA", "SALES": "ISV", "ITBMS": "ITBMS"}
    for p in db.scalars(select(PaisArancel)):
        m = re.match(r"\s*([A-Za-z]+)[^\d]*([\d.]+)\s*%", p.impuesto or "")
        cod = f"TAX-{p.iso}-GENERAL"
        if not m or db.scalar(select(ReglaImpuesto.id).where(ReglaImpuesto.codigo == cod)):
            continue
        db.add(ReglaImpuesto(codigo=cod, pais=p.iso, patron="*", tipo=tipos.get(m.group(1).upper(), "OTRO"), tasa=float(m.group(2)),
                             base_calculo="CIF + DAI", fuente_id=p.fuente_impuestos_id or p.fuente_id,
                             base_legal=f"General import rate ({p.impuesto}). Verify against the country's official tax source."))
        n += 1
    db.flush()
    return n


# ---- Consulta ---------------------------------------------------------------------
def _fuente(db: Session, fid: int | None) -> str | None:
    return db.scalar(select(FuenteOficial.codigo).where(FuenteOficial.id == fid)) if fid else None


def _reg_dict(db, x: Regulacion) -> dict:
    d = {c: getattr(x, c) for c in ("id", "codigo", "pais", "tipo_ambito", "patron", "tipo", "nombre", "autoridad", "codigo_permiso",
                                     "obligatorio", "condicion", "base_legal", "activo", "vigente_desde", "vigente_hasta", "url", "nota")}
    d["fuente"] = _fuente(db, x.fuente_id)
    return d


def _imp_dict(db, x: ReglaImpuesto) -> dict:
    d = {c: getattr(x, c) for c in ("id", "codigo", "pais", "patron", "tipo", "tasa", "base_calculo", "umbral_desde", "umbral_hasta",
                                     "formula", "activo", "vigente_desde", "vigente_hasta", "url", "base_legal")}
    d["fuente"] = _fuente(db, x.fuente_id)
    return d


def regulaciones(db: Session, user: Usuario, q: str | None = None, pais: str | None = None) -> dict:
    exigir(user, "aranceles.ver")
    c = select(Regulacion)
    if pais:
        c = c.where(Regulacion.pais == pais.upper())
    if q:
        d = _dig(q)
        c = c.where(or_(filtro_texto(q, lambda p: [Regulacion.codigo.ilike(p), Regulacion.nombre.ilike(p), Regulacion.autoridad.ilike(p),
                                                   Regulacion.tipo.ilike(p), Regulacion.base_legal.ilike(p)]),
                        *([Regulacion.patron.startswith(d[:2])] if len(d) >= 2 else [])))
    return {"items": [_reg_dict(db, x) for x in db.scalars(c.order_by(Regulacion.pais, Regulacion.patron, Regulacion.codigo))],
            "tipos": TIPOS_REGULACION}


def impuestos(db: Session, user: Usuario, q: str | None = None, pais: str | None = None) -> dict:
    exigir(user, "aranceles.ver")
    c = select(ReglaImpuesto)
    if pais:
        c = c.where(ReglaImpuesto.pais == pais.upper())
    if q:
        c = c.where(filtro_texto(q, lambda p: [ReglaImpuesto.codigo.ilike(p), ReglaImpuesto.tipo.ilike(p), ReglaImpuesto.patron.ilike(p),
                                               ReglaImpuesto.base_legal.ilike(p), ReglaImpuesto.base_calculo.ilike(p)]))
    return {"items": [_imp_dict(db, x) for x in db.scalars(c.order_by(ReglaImpuesto.pais, ReglaImpuesto.tipo, ReglaImpuesto.patron))],
            "tipos": TIPOS_IMPUESTO}


def _vigente(x, hoy: date) -> bool:
    return x.activo and (not x.vigente_desde or x.vigente_desde <= hoy) and (not x.vigente_hasta or x.vigente_hasta >= hoy)


def requisitos(db: Session, pais: str, codigo: str, dai: str | None = None, hoy: date | None = None) -> dict:
    """Lo que aplica a un código en un país hoy: el DAI del código, el impuesto
    más específico de cada tipo (el patrón más largo gana) y las regulaciones."""
    hoy = hoy or date.today()
    cod = _dig(codigo)
    imp: dict[str, ReglaImpuesto] = {}
    for x in db.scalars(select(ReglaImpuesto).where(ReglaImpuesto.pais == pais)):
        if _vigente(x, hoy) and aplica(x.patron, cod):
            previo = imp.get(x.tipo)
            if not previo or (0 if x.patron == "*" else len(x.patron)) > (0 if previo.patron == "*" else len(previo.patron)):
                imp[x.tipo] = x
    regs = [_reg_dict(db, x) for x in db.scalars(select(Regulacion).where(Regulacion.pais == pais).order_by(Regulacion.tipo))
            if _vigente(x, hoy) and aplica(x.patron, cod)]
    return {"pais": pais, "codigo": cod, "dai": dai, "impuestos": [_imp_dict(db, x) for x in imp.values()], "regulaciones": regs}


# ---- Edición (nunca se borra lo publicado: se desactiva) ------------------------------
def guardar_regulacion(db: Session, user: Usuario, reg_id: int | None, datos: dict) -> dict:
    exigir(user, "aranceles.editar")
    x = db.get(Regulacion, reg_id) if reg_id else None
    if reg_id and not x:
        raise ErrorNegocio("The regulation does not exist.", 404, "no_encontrado")
    if not x:
        x = Regulacion(codigo=(datos.get("codigo") or "").strip() or f"REG-{(datos.get('pais') or '').upper()}-"
                       f"{(db.scalar(select(func.count()).select_from(Regulacion)) or 0) + 1:04d}")
        if db.scalar(select(Regulacion.id).where(Regulacion.codigo == x.codigo)):
            raise ErrorNegocio("That regulation ID is already in use.", 422, "validacion")
    _aplicar(db, x, datos, ("tipo", "nombre", "autoridad", "codigo_permiso", "obligatorio", "base_legal", "activo", "url", "nota",
                            "vigente_desde", "vigente_hasta"))
    if not x.nombre or x.tipo not in TIPOS_REGULACION:
        raise ErrorNegocio(f"Name and a regulation type ({', '.join(TIPOS_REGULACION)}) are required.", 422, "validacion")
    db.add(x)
    db.flush()
    registrar(db, user, "aranceles", x.id, "regulacion", {"codigo": x.codigo, "pais": x.pais, "patron": x.patron})
    return _reg_dict(db, x)


def guardar_impuesto(db: Session, user: Usuario, imp_id: int | None, datos: dict) -> dict:
    exigir(user, "aranceles.editar")
    x = db.get(ReglaImpuesto, imp_id) if imp_id else None
    if imp_id and not x:
        raise ErrorNegocio("The tax rule does not exist.", 404, "no_encontrado")
    if not x:
        x = ReglaImpuesto(codigo=(datos.get("codigo") or "").strip() or f"TAX-{(datos.get('pais') or '').upper()}-"
                          f"{(db.scalar(select(func.count()).select_from(ReglaImpuesto)) or 0) + 1:04d}")
        if db.scalar(select(ReglaImpuesto.id).where(ReglaImpuesto.codigo == x.codigo)):
            raise ErrorNegocio("That tax rule ID is already in use.", 422, "validacion")
    _aplicar(db, x, datos, ("tipo", "tasa", "base_calculo", "umbral_desde", "umbral_hasta", "formula", "base_legal", "activo", "url",
                            "vigente_desde", "vigente_hasta"))
    if x.tipo not in TIPOS_IMPUESTO:
        raise ErrorNegocio(f"Tax type must be one of {', '.join(TIPOS_IMPUESTO)}.", 422, "validacion")
    if not x.fuente_id and not (x.base_legal or "").strip():
        raise ErrorNegocio("Every tax rule needs an official source or its legal basis.", 422, "validacion")
    db.add(x)
    db.flush()
    registrar(db, user, "aranceles", x.id, "impuesto", {"codigo": x.codigo, "pais": x.pais, "tasa": x.tasa})
    return _imp_dict(db, x)


def _aplicar(db: Session, x, datos: dict, campos: tuple) -> None:
    if "pais" in datos and datos["pais"]:
        p = db.scalar(select(PaisArancel).where(PaisArancel.iso == datos["pais"].upper()))
        if not p:
            raise ErrorNegocio("Choose a country loaded in the tariff schedule.", 422, "validacion")
        x.pais = p.iso
        if not getattr(x, "fuente_id", None):
            x.fuente_id = p.fuente_regulaciones_id if isinstance(x, Regulacion) else p.fuente_impuestos_id
    if not x.pais:
        raise ErrorNegocio("Choose a country loaded in the tariff schedule.", 422, "validacion")
    if "patron" in datos:
        pt = patron_norm(datos["patron"])
        if not pt:
            raise ErrorNegocio("Use a code or pattern of at least 2 digits (e.g. 64, 6404.19) or * for all codes.", 422, "validacion")
        x.patron = pt
    for k in campos:
        if k in datos:
            setattr(x, k, datos[k].upper() if k == "tipo" and isinstance(datos[k], str) else datos[k])
    if x.vigente_desde and x.vigente_hasta and x.vigente_hasta < x.vigente_desde:
        raise ErrorNegocio("Valid to must be on or after valid from.", 422, "validacion")
