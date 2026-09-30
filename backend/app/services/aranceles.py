"""Aranceles: los países destino con su arancel propio (dígitos y si son del
Mercado Común Centroamericano), las subpartidas SAC a 6 dígitos con su texto
y los códigos nacionales de cada país con las condiciones que los distinguen.
Todo se puede ver, editar, cargar desde Excel y exportar con los filtros."""
import re

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..models import IncisoNacional, PaisArancel, PartidaSAC, Usuario, ahora
from . import documentos, exportar
from .common import ErrorNegocio, exigir, registrar
from .meta import cond_texto, opciones_cond, valor_opcion
from .plantillas import leer, norm, plantilla, si_no

FUENTES = {"base": "Base", "aprendido": "Learned", "manual": "By hand", "archivo": "File"}


def _dig(s) -> str:
    return re.sub(r"\D", "", str(s or ""))


def _fmt(c) -> str:
    d = _dig(c)
    if len(d) <= 4:
        return d
    return ".".join([d[:4]] + [d[i:i + 2] for i in range(4, len(d), 2)])


def _lista(v) -> list[str]:
    if v in (None, ""):
        return []
    if isinstance(v, list):
        return [str(x) for x in v if str(x).strip()]
    return [x.strip() for x in str(v).split(",") if x.strip()]


# ---- Países ----------------------------------------------------------------------
def paises(db: Session, user: Usuario) -> list[dict]:
    exigir(user, "producto.ver")
    n = dict(db.execute(select(IncisoNacional.pais, func.count()).group_by(IncisoNacional.pais)).all())
    return [{"id": x.id, "iso": x.iso, "nombre": x.nombre, "digitos": x.digitos, "mcca": x.mcca, "impuesto": x.impuesto,
             "nota": x.nota, "orden": x.orden, "activo": x.activo, "codigos": n.get(x.iso, 0)}
            for x in db.scalars(select(PaisArancel).order_by(PaisArancel.orden, PaisArancel.iso))]


def guardar_pais(db: Session, user: Usuario, datos, pais_id: int | None = None) -> dict:
    exigir(user, "producto.clasificar")
    iso = (datos.iso or "").strip().upper()
    if not re.fullmatch(r"[A-Z]{2}", iso):
        raise ErrorNegocio("The country code has 2 letters (ISO), e.g. DO.", 422, "validacion")
    if not 6 <= datos.digitos <= 14:
        raise ErrorNegocio("National codes have between 6 and 14 digits.", 422, "validacion")
    otro = db.scalar(select(PaisArancel).where(PaisArancel.iso == iso))
    x = db.get(PaisArancel, pais_id) if pais_id else None
    if pais_id and not x:
        raise ErrorNegocio("The country does not exist.", 404, "no_encontrado")
    if otro and otro is not x:
        raise ErrorNegocio(f"{iso} is already loaded.", 409, "duplicado")
    if not x:
        x = PaisArancel(orden=(db.scalar(select(func.max(PaisArancel.orden))) or 0) + 1)
        db.add(x)
    antes = x.iso
    x.iso, x.nombre, x.digitos = iso, datos.nombre.strip()[:80], datos.digitos
    x.mcca, x.impuesto, x.nota, x.activo = datos.mcca, (datos.impuesto or "")[:60] or None, (datos.nota or "")[:300] or None, datos.activo
    if antes and antes != iso:
        for i in db.scalars(select(IncisoNacional).where(IncisoNacional.pais == antes)):
            i.pais = iso
    db.flush()
    registrar(db, user, "aranceles", x.id, "pais", {"iso": iso, "digitos": x.digitos})
    return {"id": x.id}


def borrar_pais(db: Session, user: Usuario, pais_id: int) -> None:
    exigir(user, "producto.clasificar")
    x = db.get(PaisArancel, pais_id)
    if not x:
        raise ErrorNegocio("The country does not exist.", 404, "no_encontrado")
    n = db.scalar(select(func.count()).select_from(IncisoNacional).where(IncisoNacional.pais == x.iso))
    if n:
        raise ErrorNegocio(f"{x.nombre} has {n} national codes. Deactivate it instead, or delete its codes first.",
                           409, "con_codigos")
    db.delete(x)


def _paises_dict(db: Session) -> dict[str, PaisArancel]:
    return {x.iso: x for x in db.scalars(select(PaisArancel))}


# ---- Subpartidas SAC ---------------------------------------------------------------
def _q_sac(filtros: dict):
    q = select(PartidaSAC)
    if filtros.get("q"):
        t = filtros["q"].strip()
        d = _dig(t)
        q = q.where(or_(PartidaSAC.descripcion.ilike(f"%{t}%"), *( [PartidaSAC.codigo.startswith(d)] if d else [])))
    caps = _lista(filtros.get("capitulo"))
    if caps:
        q = q.where(or_(*[PartidaSAC.codigo.startswith(_dig(c)[:2]) for c in caps]))
    if filtros.get("nivel") in ("4", "6"):
        q = q.where(func.length(PartidaSAC.codigo) == int(filtros["nivel"]))
    fuentes = _lista(filtros.get("fuente"))
    if fuentes:
        q = q.where(PartidaSAC.fuente.in_(fuentes))
    return q


def listar_sac(db: Session, user: Usuario, filtros: dict, page: int, size: int) -> dict:
    exigir(user, "producto.ver")
    q = _q_sac(filtros)
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    filas = db.scalars(q.order_by(PartidaSAC.codigo).offset((page - 1) * size).limit(size)).all()
    subs = [x.codigo for x in filas if len(x.codigo) == 6]
    n = dict(db.execute(select(IncisoNacional.sub6, func.count()).where(IncisoNacional.sub6.in_(subs))
                        .group_by(IncisoNacional.sub6)).all()) if subs else {}
    caps = sorted({r[0][:2] for r in db.execute(select(PartidaSAC.codigo))})
    return {"items": [{"id": x.id, "codigo": x.codigo, "codigo_txt": _fmt(x.codigo), "descripcion": x.descripcion,
                       "nota": x.nota, "fuente": x.fuente, "activo": x.activo, "nacionales": n.get(x.codigo, 0)}
                      for x in filas], "total": total, "page": page, "size": size, "capitulos": caps}


def guardar_sac(db: Session, user: Usuario, datos, sac_id: int | None = None) -> dict:
    exigir(user, "producto.clasificar")
    cod = _dig(datos.codigo)
    if len(cod) not in (4, 6):
        raise ErrorNegocio("Use the 4-digit heading or the 6-digit subheading.", 422, "validacion")
    if not (datos.descripcion or "").strip():
        raise ErrorNegocio("Write the official description.", 422, "validacion")
    x = db.get(PartidaSAC, sac_id) if sac_id else db.scalar(select(PartidaSAC).where(PartidaSAC.codigo == cod))
    otro = db.scalar(select(PartidaSAC).where(PartidaSAC.codigo == cod))
    if otro and x is not otro:
        raise ErrorNegocio(f"{_fmt(cod)} is already loaded.", 409, "duplicado")
    if not x:
        x = PartidaSAC(codigo=cod)
        db.add(x)
    x.codigo, x.descripcion = cod, datos.descripcion.strip()[:400]
    x.nota, x.activo = (datos.nota or "")[:300] or None, datos.activo
    x.fuente = "manual" if x.fuente in (None, "base") else x.fuente
    x.actualizado_en = ahora()
    db.flush()
    return {"id": x.id}


def borrar_sac(db: Session, user: Usuario, sac_id: int) -> None:
    exigir(user, "producto.clasificar")
    x = db.get(PartidaSAC, sac_id)
    if not x:
        raise ErrorNegocio("The subheading does not exist.", 404, "no_encontrado")
    db.delete(x)


# ---- Códigos nacionales ----------------------------------------------------------------
def _q_incisos(filtros: dict):
    q = select(IncisoNacional)
    ps = [p.upper() for p in _lista(filtros.get("pais"))]
    if ps:
        q = q.where(IncisoNacional.pais.in_(ps))
    if filtros.get("q"):
        t = filtros["q"].strip()
        d = _dig(t)
        q = q.where(or_(IncisoNacional.descripcion.ilike(f"%{t}%"), IncisoNacional.nota.ilike(f"%{t}%"),
                        *([IncisoNacional.codigo.startswith(d)] if d else [])))
    caps = _lista(filtros.get("capitulo"))
    if caps:
        q = q.where(or_(*[IncisoNacional.sub6.startswith(_dig(c)[:2]) for c in caps]))
    fuentes = _lista(filtros.get("fuente"))
    if fuentes:
        q = q.where(IncisoNacional.fuente.in_(fuentes))
    if filtros.get("activo") in ("true", "false"):
        q = q.where(IncisoNacional.activo.is_(filtros["activo"] == "true"))
    return q


def _fila_inciso(x: IncisoNacional, sac: dict) -> dict:
    return {"id": x.id, "pais": x.pais, "codigo": x.codigo, "codigo_txt": _fmt(x.codigo), "sub6": x.sub6,
            "sac": sac.get(x.sub6), "descripcion": x.descripcion, "dai": x.dai, "cond": x.cond or {},
            "cond_txt": cond_texto(x.cond), "prio": x.prio, "nota": x.nota, "fuente": x.fuente,
            "fuente_txt": FUENTES.get(x.fuente, x.fuente), "activo": x.activo}


def listar_incisos(db: Session, user: Usuario, filtros: dict, page: int, size: int, orden: str | None) -> dict:
    exigir(user, "producto.ver")
    q = _q_incisos(filtros)
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    col, _, dirn = (orden or "codigo:asc").partition(":")
    campo = {"pais": IncisoNacional.pais, "codigo": IncisoNacional.codigo, "fuente": IncisoNacional.fuente,
             "dai": IncisoNacional.dai}.get(col, IncisoNacional.codigo)
    filas = db.scalars(q.order_by(campo.desc() if dirn == "desc" else campo.asc(), IncisoNacional.pais, IncisoNacional.id)
                       .offset((page - 1) * size).limit(size)).all()
    sac = dict(db.execute(select(PartidaSAC.codigo, PartidaSAC.descripcion)
                          .where(PartidaSAC.codigo.in_({x.sub6 for x in filas}))).all()) if filas else {}
    por_pais = dict(db.execute(select(IncisoNacional.pais, func.count()).group_by(IncisoNacional.pais)).all())
    return {"items": [_fila_inciso(x, sac) for x in filas], "total": total, "page": page, "size": size,
            "por_pais": por_pais}


def _cond_limpia(cond: dict | None) -> dict:
    oc = opciones_cond()
    out = {}
    for k, v in (cond or {}).items():
        if k not in oc or v in (None, "", []):
            continue
        d = oc[k]
        if d["tipo"] == "numero":
            try:
                out[k] = float(v)
            except (TypeError, ValueError):
                raise ErrorNegocio(f"{d['label']}: write a number.", 422, "validacion")
        elif d["tipo"] == "sino":
            out[k] = bool(v) if isinstance(v, bool) else bool(si_no(v))
        else:
            vals = v if isinstance(v, list) else [v]
            malos = [x for x in vals if x not in d["ops"]]
            if malos:
                raise ErrorNegocio(f"{d['label']}: “{malos[0]}” is not a valid value.", 422, "validacion")
            out[k] = vals if len(vals) > 1 else vals[0]
    return out


def guardar_inciso(db: Session, user: Usuario, datos, inciso_id: int | None = None) -> dict:
    exigir(user, "producto.clasificar")
    ps = _paises_dict(db)
    pais = (datos.pais or "").upper()
    if pais not in ps:
        raise ErrorNegocio("Choose a country loaded in the tariff schedule.", 422, "validacion")
    cod = _dig(datos.codigo)
    n = ps[pais].digitos
    if len(cod) != n:
        raise ErrorNegocio(f"{ps[pais].nombre} uses {n}-digit codes; you entered {len(cod)}.", 422, "validacion")
    x = db.get(IncisoNacional, inciso_id) if inciso_id else None
    if inciso_id and not x:
        raise ErrorNegocio("The code does not exist.", 404, "no_encontrado")
    if not x:
        x = IncisoNacional(fuente="manual", creado_por=user.id)
        db.add(x)
    x.pais, x.codigo, x.sub6 = pais, cod, cod[:6]
    x.descripcion = (datos.descripcion or "").strip()[:300] or None
    x.dai = (datos.dai or "").replace("%", "").strip()[:10] or None
    x.cond = _cond_limpia(datos.cond)
    x.prio, x.nota, x.activo = datos.prio or 0, (datos.nota or "")[:300] or None, datos.activo
    db.flush()
    registrar(db, user, "aranceles", x.id, "codigo_nacional", {"pais": pais, "codigo": _fmt(cod)})
    return {"id": x.id}


def borrar_incisos(db: Session, user: Usuario, ids: list[int]) -> dict:
    exigir(user, "producto.clasificar")
    n = 0
    for x in db.scalars(select(IncisoNacional).where(IncisoNacional.id.in_(ids))):
        db.delete(x)
        n += 1
    registrar(db, user, "aranceles", 0, "borrar_codigos", {"n": n})
    return {"borrados": n}


# ---- Cargas desde Excel ------------------------------------------------------------------
def _columnas_cond() -> list[tuple[str, dict]]:
    return list(opciones_cond().items())


def _alias_incisos() -> dict[str, str]:
    a = {"country": "pais", "pais": "pais", "iso": "pais", "code": "codigo", "national_code": "codigo", "codigo": "codigo",
         "inciso": "codigo", "description": "descripcion", "descripcion": "descripcion", "duty": "dai", "duty_dai": "dai",
         "dai": "dai", "duty_dai_percent": "dai", "priority": "prio", "prioridad": "prio", "note": "nota", "nota": "nota",
         "active": "activo"}
    for k, d in _columnas_cond():
        a[norm(d["label"])] = "c_" + k
        a[norm(k)] = "c_" + k
    return a


def plantilla_incisos(db: Session, pais: str | None = None) -> bytes:
    ps = _paises_dict(db)
    cols = [
        {"nombre": "Country", "req": True, "opciones": sorted(ps), "ayuda": "ISO code of a country in the tariff schedule.", "ancho": 10},
        {"nombre": "Code", "req": True, "ayuda": "National code with all its digits (dots optional): "
         + ", ".join(f"{x.iso} {x.digitos}" for x in ps.values()) + ".", "ancho": 18},
        {"nombre": "Description", "ayuda": "Official text of the national code (optional).", "ancho": 45},
        {"nombre": "Duty (DAI %)", "ayuda": "Import duty rate, e.g. 15.", "ancho": 12},
        {"nombre": "Priority", "ayuda": "Higher wins when several codes fit the same product (0 by default).", "ancho": 10},
        {"nombre": "Note", "ancho": 30},
    ]
    for k, d in _columnas_cond():
        ayuda = "Condition that selects this code. Leave empty if it does not matter."
        if d["tipo"] == "sino":
            cols.append({"nombre": d["label"], "opciones": ["Yes", "No"], "ayuda": ayuda})
        elif d["tipo"] == "numero":
            cols.append({"nombre": d["label"], "ayuda": ayuda + " Number in US$."})
        else:
            cols.append({"nombre": d["label"], "opciones": list(d["ops"].values()),
                         "ayuda": ayuda + " Several values separated by commas."})
    iso = (pais or "SV").upper()
    n = ps[iso].digitos if iso in ps else 10
    ej = [[iso, "6404.19.90" + "0" * max(0, n - 8), "Los demás", "15", 0, "", "Adult"] + [""] * (len(cols) - 7)]
    return plantilla("National tariff codes", cols, ej, [
        "One row per national code. The code must have the digits of its country.",
        "The condition columns say when a product takes this code (gender, age, CIF value, footwear style…). "
        "The engine picks the code whose conditions match the technical sheet.",
        "A row with the same country, code and conditions updates the existing code.",
    ])


def importar_incisos(db: Session, user: Usuario, nombre: str, contenido: bytes, pais: str | None = None,
                     reemplazar: bool = False) -> dict:
    exigir(user, "producto.clasificar")
    ps = _paises_dict(db)
    filas = leer(nombre, contenido, _alias_incisos())
    oc = opciones_cond()
    errores, validas = [], []
    for f in filas:
        iso = (f.get("pais") or pais or "").strip().upper()
        if iso not in ps and f.get("pais"):
            iso = next((k for k, x in ps.items() if norm(x.nombre) == norm(f["pais"])), iso)
        if iso not in ps:
            errores.append({"fila": f["_fila"], "mensaje": f"Country “{f.get('pais') or ''}” is not in the tariff schedule."})
            continue
        cod = _dig(f.get("codigo"))
        if len(cod) != ps[iso].digitos:
            errores.append({"fila": f["_fila"], "mensaje": f"{iso} uses {ps[iso].digitos} digits; the code has {len(cod)}."})
            continue
        cond, mal = {}, None
        for k, d in oc.items():
            v = (f.get("c_" + k) or "").strip()
            if not v:
                continue
            if d["tipo"] == "numero":
                try:
                    cond[k] = float(v.replace(",", "."))
                except ValueError:
                    mal = f"{d['label']}: “{v}” is not a number."
            elif d["tipo"] == "sino":
                b = si_no(v)
                if b is None:
                    mal = f"{d['label']}: write Yes or No."
                else:
                    cond[k] = b
            else:
                vals = [valor_opcion(d["ops"], x) for x in v.split(",") if x.strip()]
                if None in vals:
                    mal = f"{d['label']}: “{v}” is not a valid value."
                else:
                    cond[k] = vals if len(vals) > 1 else vals[0]
        if mal:
            errores.append({"fila": f["_fila"], "mensaje": mal})
            continue
        try:
            prio = int(float(f.get("prio") or 0))
        except ValueError:
            prio = 0
        validas.append((iso, cod, cond, f, prio))
    creados = actualizados = borrados = 0
    if reemplazar and validas:
        for iso in {v[0] for v in validas}:
            for x in db.scalars(select(IncisoNacional).where(IncisoNacional.pais == iso)):
                db.delete(x)
                borrados += 1
        db.flush()
    existentes = {} if reemplazar else {
        (x.pais, x.codigo, repr(sorted((x.cond or {}).items()))): x
        for x in db.scalars(select(IncisoNacional).where(IncisoNacional.pais.in_({v[0] for v in validas})))}
    for iso, cod, cond, f, prio in validas:
        clave = (iso, cod, repr(sorted(cond.items())))
        x = existentes.get(clave)
        if x:
            actualizados += 1
        else:
            x = IncisoNacional(pais=iso, codigo=cod, sub6=cod[:6], cond=cond, fuente="archivo", creado_por=user.id)
            db.add(x)
            existentes[clave] = x
            creados += 1
        if f.get("descripcion"):
            x.descripcion = f["descripcion"][:300]
        if f.get("dai"):
            x.dai = f["dai"].replace("%", "").strip()[:10]
        if f.get("nota"):
            x.nota = f["nota"][:300]
        x.prio = prio
        x.activo = True
    registrar(db, user, "aranceles", 0, "importar_codigos",
              {"creados": creados, "actualizados": actualizados, "borrados": borrados, "errores": len(errores)})
    return {"creados": creados, "actualizados": actualizados, "borrados": borrados, "errores": errores[:200]}


def plantilla_sac() -> bytes:
    return plantilla("SAC subheadings", [
        {"nombre": "Code", "req": True, "ayuda": "4-digit heading or 6-digit subheading (dots optional).", "ancho": 12},
        {"nombre": "Description", "req": True, "ayuda": "Official text in Spanish, as in the SAC.", "ancho": 70},
        {"nombre": "Note", "ancho": 40},
    ], [["6404.19", "Los demás calzados con suela de caucho o plástico y parte superior de materia textil", ""]],
        ["One row per heading or subheading. A code already loaded is updated with the new text."])


def importar_sac(db: Session, user: Usuario, nombre: str, contenido: bytes) -> dict:
    exigir(user, "producto.clasificar")
    filas = leer(nombre, contenido, {"code": "codigo", "codigo": "codigo", "description": "descripcion",
                                     "descripcion": "descripcion", "note": "nota", "nota": "nota"})
    actuales = {x.codigo: x for x in db.scalars(select(PartidaSAC))}
    creados = actualizados = 0
    errores = []
    for f in filas:
        cod = _dig(f.get("codigo"))
        if len(cod) not in (4, 6) or not (f.get("descripcion") or "").strip():
            errores.append({"fila": f["_fila"], "mensaje": "Code with 4 or 6 digits and description are required."})
            continue
        x = actuales.get(cod)
        if x:
            actualizados += 1
        else:
            x = actuales[cod] = PartidaSAC(codigo=cod)
            db.add(x)
            creados += 1
        x.descripcion = f["descripcion"].strip()[:400]
        x.nota = (f.get("nota") or "")[:300] or x.nota
        x.fuente = "archivo"
        x.actualizado_en = ahora()
    registrar(db, user, "aranceles", 0, "importar_sac", {"creados": creados, "actualizados": actualizados})
    return {"creados": creados, "actualizados": actualizados, "errores": errores[:200]}


# ---- Exportar con los filtros de la pantalla ------------------------------------------------
def _filtros_txt(filtros: dict, nombres: dict) -> str:
    partes = [f"{nombres.get(k, k)}: {v}" for k, v in filtros.items() if v not in (None, "")]
    return "Filters: " + " · ".join(partes) if partes else "No filters"


def exportar_incisos(db: Session, user: Usuario, filtros: dict, orden: str | None, formato: str) -> bytes:
    r = listar_incisos(db, user, filtros, 1, 200_000, orden)
    columnas = [("Country", 0.6, False), ("Code", 1.2, False), ("SAC subheading", 2.4, False), ("Description", 2.2, False),
                ("Duty %", 0.6, True), ("Conditions", 2.4, False), ("Priority", 0.6, True), ("Source", 0.8, False),
                ("Active", 0.6, False)]
    filas = [[x["pais"], x["codigo_txt"], x["sac"] or "—", x["descripcion"] or "—", x["dai"] or "—", x["cond_txt"],
              x["prio"], x["fuente_txt"], "Yes" if x["activo"] else "No"] for x in r["items"]]
    ind = [("Codes", f"{r['total']:,}")] + [(k, f"{v:,}") for k, v in sorted(r["por_pais"].items())][:5]
    texto = _filtros_txt(filtros, {"pais": "Country", "q": "Search", "capitulo": "Chapter", "fuente": "Source"})
    titulo, sub = "National tariff codes", "Codes by destination country with the conditions that select them"
    if formato == "pdf":
        return documentos.pdf_reporte(titulo, sub, texto, ind, columnas, [[str(v) for v in f] for f in filas])
    return exportar.exportar_reporte(titulo, sub, texto, ind, columnas, filas)


def exportar_sac(db: Session, user: Usuario, filtros: dict, formato: str) -> bytes:
    r = listar_sac(db, user, filtros, 1, 100_000)
    columnas = [("Code", 0.8, False), ("Description", 5, False), ("National codes", 0.9, True), ("Source", 0.7, False)]
    filas = [[x["codigo_txt"], x["descripcion"], x["nacionales"], FUENTES.get(x["fuente"], x["fuente"])] for x in r["items"]]
    texto = _filtros_txt(filtros, {"q": "Search", "capitulo": "Chapter", "nivel": "Level", "fuente": "Source"})
    titulo, sub = "SAC headings and subheadings", "Central American Tariff System (HS 2022)"
    if formato == "pdf":
        return documentos.pdf_reporte(titulo, sub, texto, [("Codes", f"{r['total']:,}")], columnas,
                                      [[str(v) for v in f] for f in filas])
    return exportar.exportar_reporte(titulo, sub, texto, [("Codes", f"{r['total']:,}")], columnas, filas)


def opciones(db: Session, user: Usuario) -> dict:
    exigir(user, "producto.ver")
    return {"condiciones": {k: {"label": d["label"], "tipo": d["tipo"], "ops": d["ops"]} for k, d in opciones_cond().items()},
            "fuentes": FUENTES}
