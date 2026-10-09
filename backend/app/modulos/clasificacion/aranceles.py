"""Aranceles: los países destino con su arancel propio (dígitos y si son del
Mercado Común Centroamericano), las subpartidas SAC a 6 dígitos con su texto
y los códigos nacionales de cada país con las condiciones que los distinguen.
Todo se puede ver, editar, cargar desde Excel y exportar con los filtros."""
import re

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.empresa import regla
from app.core.errores import ErrorNegocio
from app.modelos import IncisoNacional, NodoArancel, NotaSAC, PaisArancel, Usuario, ahora
from app.modulos.acceso.permisos import exigir
from app.modulos.clasificacion import overrides
from app.modulos.clasificacion.meta import cond_texto, opciones_cond, valor_opcion
from app.modulos.comun.historial import registrar
from app.modulos.documentos import documentos, exportar
from app.modulos.documentos.plantillas import leer, norm, plantilla, si_no

# Origen de un dato de la consulta: el publicado o el ajuste propio de la empresa encima
FUENTES = {"oficial": "Official (published source)", "custom": "Company override over the official"}


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
    from app.modelos import FuenteOficial

    fuentes = {f.id: f.codigo for f in db.scalars(select(FuenteOficial))}
    return [{"id": x.id, "iso": x.iso, "nombre": x.nombre, "digitos": x.digitos, "mcca": x.mcca, "impuesto": x.impuesto,
             "nota": x.nota, "base_legal": x.base_legal, "orden": x.orden, "activo": x.activo, "codigos": n.get(x.iso, 0),
             "longitudes": x.longitudes_validas() if x.longitudes else [], "longitudes_validas": x.longitudes_validas(),
             "nivel_base": x.nivel_base, "modelo_arancel": x.modelo_arancel, "contexto": x.contexto,
             "fuente": fuentes.get(x.fuente_id), **_estado_oficial(x, n.get(x.iso, 0))}
            for x in db.scalars(select(PaisArancel).order_by(PaisArancel.orden, PaisArancel.iso))]


def _estado_oficial(x: PaisArancel, lineas: int) -> dict:
    """Qué tan respaldado está el arancel del país por una fuente oficial
    (nunca se rellena con datos de la empresa)."""
    if not x.fuente_id:
        return {"datos_oficiales": "PENDING_VERIFICATION", "datos_oficiales_txt": "Pending official source verification"}
    if not lineas:
        return {"datos_oficiales": "NO_NATIONAL_DATA", "datos_oficiales_txt": "Official national tariff data not available"}
    return {"datos_oficiales": "OK", "datos_oficiales_txt": "Official national lines loaded"}


def guardar_pais(db: Session, user: Usuario, datos, pais_id: int | None = None) -> dict:
    exigir(user, "aranceles.editar")
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
    x.base_legal = (datos.base_legal or "").strip()[:300] or None
    campos = datos.model_fields_set
    if "longitudes" in campos:
        lons = sorted(set(datos.longitudes or []))
        if any(not 6 <= n <= 14 for n in lons):
            raise ErrorNegocio("Each valid length has between 6 and 14 digits.", 422, "validacion")
        if lons and datos.digitos not in lons:
            raise ErrorNegocio("The usual number of digits must be one of the valid lengths.", 422, "validacion")
        x.longitudes = ",".join(str(n) for n in lons) or None
    for k in ("nivel_base", "modelo_arancel", "contexto"):
        if k in campos:
            setattr(x, k, (getattr(datos, k) or "").strip() or None)
    if "fuente" in campos:
        from app.modelos import FuenteOficial

        f = db.scalar(select(FuenteOficial).where(FuenteOficial.codigo == datos.fuente)) if datos.fuente else None
        if datos.fuente and not f:
            raise ErrorNegocio(f"The official source {datos.fuente} does not exist.", 422, "validacion")
        x.fuente_id = f.id if f else None
    if antes and antes != iso:
        for i in db.scalars(select(IncisoNacional).where(IncisoNacional.pais == antes)):
            i.pais = iso
    db.flush()
    registrar(db, user, "aranceles", x.id, "pais", {"iso": iso, "digitos": x.digitos})
    return {"id": x.id}


def borrar_pais(db: Session, user: Usuario, pais_id: int) -> None:
    exigir(user, "aranceles.editar")
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


# ---- Partidas y subpartidas: el árbol oficial + la capa custom ---------------------------
# El texto oficial sale del árbol arancelario de la versión vigente (NodoArancel)
# y no se edita: lo propio (descripción interna, nota) es un override con motivo.
def _version_sac(db: Session):
    from app.modulos.clasificacion.motor_clasificacion import resolver_version_vigente

    return resolver_version_vigente(db, "REGIONAL")


def textos_sac(db: Session, codigos) -> dict[str, str]:
    """Texto de partidas/subpartidas: el oficial, o el custom si lo hay."""
    v = _version_sac(db)
    codigos = list({c for c in codigos if c})
    if not v or not codigos:
        return {}
    out = dict(db.execute(select(NodoArancel.codigo_norm, NodoArancel.descripcion).where(
        NodoArancel.version_id == v.id, NodoArancel.pais.is_(None), NodoArancel.codigo_norm.in_(codigos))).all())
    for cod, ov in overrides.vigentes(db, "NODO", codigos).items():
        if ov.get("descripcion"):
            out[cod] = ov["descripcion"]
    return out


def _q_sac(db: Session, filtros: dict):
    v = _version_sac(db)
    q = select(NodoArancel).where(NodoArancel.version_id == (v.id if v else -1), NodoArancel.pais.is_(None),
                                  NodoArancel.nivel.in_(("PARTIDA", "SUBPARTIDA")))
    if filtros.get("q"):
        t = filtros["q"].strip()
        d = _dig(t)
        q = q.where(or_(NodoArancel.descripcion.ilike(f"%{t}%"), *([NodoArancel.codigo_norm.startswith(d)] if d else [])))
    caps = _lista(filtros.get("capitulo"))
    if caps:
        q = q.where(or_(*[NodoArancel.codigo_norm.startswith(_dig(c)[:2]) for c in caps]))
    if filtros.get("nivel") in ("4", "6"):
        q = q.where(NodoArancel.nivel == ("PARTIDA" if filtros["nivel"] == "4" else "SUBPARTIDA"))
    if "custom" in _lista(filtros.get("fuente")):
        con = list(overrides.vigentes(db, "NODO"))
        q = q.where(NodoArancel.codigo_norm.in_(con or ["-"]))
    return q


def listar_sac(db: Session, user: Usuario, filtros: dict, page: int, size: int) -> dict:
    exigir(user, "producto.ver")
    q = _q_sac(db, filtros)
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    filas = db.scalars(q.order_by(NodoArancel.codigo_norm).offset((page - 1) * size).limit(size)).all()
    subs = [x.codigo_norm for x in filas if len(x.codigo_norm) == 6]
    n = dict(db.execute(select(IncisoNacional.sub6, func.count()).where(IncisoNacional.sub6.in_(subs))
                        .group_by(IncisoNacional.sub6)).all()) if subs else {}
    ovs = overrides.vigentes(db, "NODO", [x.codigo_norm for x in filas])
    caps = [c for (c,) in db.execute(select(NodoArancel.codigo_norm).where(NodoArancel.nivel == "CAPITULO").order_by(NodoArancel.codigo_norm))]
    items = []
    for x in filas:
        ov = ovs.get(x.codigo_norm, {})
        items.append({"id": x.id, "codigo": x.codigo_norm, "codigo_txt": _fmt(x.codigo_norm), "descripcion": ov.get("descripcion") or x.descripcion,
                      "descripcion_oficial": x.descripcion, "nota": ov.get("nota"), "fuente": "custom" if ov else "oficial",
                      "custom": bool(ov), "activo": x.activo, "nacionales": n.get(x.codigo_norm, 0)})
    return {"items": items, "total": total, "page": page, "size": size, "capitulos": caps}


def guardar_sac(db: Session, user: Usuario, datos, sac_id: int | None = None) -> dict:
    """Descripción interna o nota propia de una partida/subpartida oficial (override)."""
    exigir(user, "aranceles.editar")
    cod = _dig(datos.codigo)
    v = _version_sac(db)
    x = db.get(NodoArancel, sac_id) if sac_id else db.scalar(select(NodoArancel).where(
        NodoArancel.version_id == (v.id if v else -1), NodoArancel.pais.is_(None), NodoArancel.codigo_norm == cod))
    if not x or x.nivel not in ("PARTIDA", "SUBPARTIDA"):
        raise ErrorNegocio("Headings and subheadings come from the official tariff: load a new version to add codes. "
                           "Here you can only add an internal description or note.", 422, "no_oficial")
    motivo = getattr(datos, "motivo", None)
    overrides.poner(db, user, "NODO", x.codigo_norm, "descripcion", (datos.descripcion or "").strip()[:400] or None, x.descripcion, motivo)
    overrides.poner(db, user, "NODO", x.codigo_norm, "nota", (datos.nota or "").strip()[:300] or None, None, motivo)
    return {"id": x.id}


def borrar_sac(db: Session, user: Usuario, sac_id: int) -> None:
    """Quita lo custom: vuelve al texto oficial (el oficial no se borra)."""
    exigir(user, "aranceles.editar")
    x = db.get(NodoArancel, sac_id)
    if not x:
        raise ErrorNegocio("The subheading does not exist.", 404, "no_encontrado")
    overrides.quitar(db, user, "NODO", x.codigo_norm)


# ---- Condiciones que aplican a un código nacional ----------------------------------------------
# Qué datos de la ficha pueden abrir un inciso nacional en un capítulo: los
# atributos (de las condiciones) que aplican a ese capítulo, a sus categorías o
# a sus dominios según el catálogo. El valor CIF lo usan algunos países en
# cualquier capítulo.
def _conds_capitulo(db: Session, cap: str, oc: dict) -> list[str]:
    from app.modulos.productos.ficha import catalogo

    cat = catalogo(db)
    cats = {c.codigo for c in cat.categorias.values() if cap in (c.capitulos or [])}
    doms = {c.dominio for c in cat.categorias.values() if c.codigo in cats and c.dominio}
    def menciona(cond) -> bool:  # una condición «categoria IN [...]» de las categorías del capítulo
        return any(c.get("campo") == "categoria" and set(c.get("valor") if isinstance(c.get("valor"), list) else [c.get("valor")]) & cats
                   for c in (cond or []) if isinstance(c, dict))

    out = []
    for a in cat.atributos:
        if a.codigo not in oc:
            continue
        por_ambito = any((x.tipo == "CHAPTER" and x.codigo == cap) or (x.tipo == "CATEGORY" and x.codigo in cats)
                         or (x.tipo == "DOMAIN" and x.codigo in doms) or (x.tipo == "SYSTEM" and a.seccion == "nacional") for x in a.ambitos)
        # Un dato nacional sin ámbitos: aplica a las categorías que nombran sus patrones de detección
        por_patron = a.seccion == "nacional" and any(menciona(p.get("cuando")) for o in a.opciones for p in o.patrones) \
            or a.seccion == "nacional" and any(menciona(p.get("cuando")) for p in a.patrones)
        if por_ambito or por_patron:
            out.append(a.codigo)
    return out


COND_SIEMPRE = ["cifMax", "cifMin"]


def condiciones_aplicables(db: Session, user: Usuario, pais: str | None, codigo: str | None) -> dict:
    """Condiciones que conviene pedir para un código nacional: las que ya usa
    ese país en la misma subpartida, las que usan los demás países y las que
    distinguen las aperturas nacionales de su capítulo."""
    exigir(user, "producto.ver")
    cod = _dig(codigo)
    sub6, cap = cod[:6], cod[:2]
    oc = opciones_cond(db)
    if len(sub6) < 6:
        return {"aplican": list(oc), "del_pais": [], "de_otros": [], "hermanos": [], "subpartida": None}
    pais = (pais or "").upper()
    del_pais, de_otros, hermanos = {}, {}, []
    for x in db.scalars(select(IncisoNacional).where(IncisoNacional.sub6 == sub6, IncisoNacional.activo.is_(True))
                        .order_by(IncisoNacional.pais, IncisoNacional.codigo)):
        destino = del_pais if x.pais == pais else de_otros
        for k in (x.cond or {}):
            destino[k] = destino.get(k, 0) + 1
        if x.pais == pais:
            hermanos.append({"codigo": x.codigo, "codigo_txt": _fmt(x.codigo), "cond_txt": cond_texto(db, x.cond or {}) or "Any product",
                             "descripcion": x.descripcion, "dai": x.dai})
    en_cap = {k for x in db.scalars(select(IncisoNacional).where(IncisoNacional.sub6.startswith(cap))) for k in (x.cond or {})}
    orden = list(del_pais) + [k for k in de_otros if k not in del_pais] + \
        [k for k in _conds_capitulo(db, cap, oc) + sorted(en_cap) if k not in del_pais and k not in de_otros]
    aplican = [k for k in dict.fromkeys(orden + COND_SIEMPRE) if k in oc]
    return {"aplican": aplican, "del_pais": list(del_pais), "de_otros": list(de_otros), "hermanos": hermanos,
            "subpartida": {"codigo": _fmt(sub6), "descripcion": textos_sac(db, [sub6]).get(sub6)}}


# ---- Notas legales del SAC ---------------------------------------------------------------
AMBITOS = {"reglas": "General rules", "seccion": "Section note", "capitulo": "Chapter note", "subpartida": "Subheading note",
           "complementaria": "Central American complementary note", "explicativa": "Explanatory note (HS)"}


# Las notas cargadas con el sistema (texto oficial y guía del clasificador) no se
# editan en sitio: lo propio va como override. Solo OFFICIAL_* es texto legal.
CARGADAS_NOTA = NotaSAC.OFICIALES + ("CLASSIFIER_GUIDANCE",)


def _verdad(v) -> bool:
    return str(v).lower() in ("true", "1", "yes")


def _fila_nota(n: NotaSAC, ov: dict | None = None) -> dict:
    ov = ov or {}
    return {"id": n.id, "ambito": n.ambito, "ambito_txt": AMBITOS.get(n.ambito, n.ambito), "codigo": n.codigo,
            "numero": n.numero, "texto": ov.get("texto") or n.texto, "texto_oficial": n.texto if ov.get("texto") else None,
            "capitulos": n.capitulos or [], "claves": n.claves or [], "tipo_fuente": n.tipo_fuente,
            "tipo_txt": NotaSAC.TIPOS.get(n.tipo_fuente, n.tipo_fuente), "oficial": n.oficial, "custom": bool(ov),
            "activo": _verdad(ov["activo"]) if "activo" in ov else n.activo, "version_id": n.version_id,
            "vigente_desde": n.vigente_desde, "vigente_hasta": n.vigente_hasta}


def notas_vigentes(db: Session) -> list[dict]:
    """Notas activas con la capa custom aplicada (para el motor y el soporte)."""
    notas = db.scalars(select(NotaSAC).order_by(NotaSAC.id)).all()
    ovs = overrides.vigentes(db, "NOTA")
    return [f for f in (_fila_nota(n, ovs.get(str(n.id))) for n in notas) if f["activo"]]


def listar_notas(db: Session, user: Usuario, filtros: dict) -> dict:
    exigir(user, "producto.ver")
    ovs = overrides.vigentes(db, "NOTA")
    notas = [_fila_nota(n, ovs.get(str(n.id))) for n in db.scalars(select(NotaSAC).order_by(NotaSAC.id))]
    caps = _lista(filtros.get("capitulo"))
    if caps:
        notas = [n for n in notas if not n["capitulos"] or set(caps) & set(n["capitulos"])]
    if filtros.get("q"):
        t = filtros["q"].strip().lower()
        notas = [n for n in notas if t in n["texto"].lower() or t in n["codigo"].lower() or t in n["numero"].lower()]
    return {"items": notas, "total": len(notas), "ambitos": AMBITOS}


def guardar_nota(db: Session, user: Usuario, datos, nota_id: int | None = None) -> dict:
    """Nota propia (custom) o override de una oficial: el texto oficial nunca se reemplaza."""
    exigir(user, "aranceles.editar")
    if datos.ambito not in AMBITOS:
        raise ErrorNegocio("Choose the kind of note.", 422, "validacion")
    if not (datos.texto or "").strip() or not (datos.codigo or "").strip():
        raise ErrorNegocio("Write the section or chapter and the text of the note.", 422, "validacion")
    n = db.get(NotaSAC, nota_id) if nota_id else None
    if nota_id and not n:
        raise ErrorNegocio("The note does not exist.", 404, "no_encontrado")
    if n and n.tipo_fuente in CARGADAS_NOTA:
        motivo = getattr(datos, "motivo", None)
        overrides.poner(db, user, "NOTA", str(n.id), "texto", datos.texto.strip(), n.texto, motivo)
        overrides.poner(db, user, "NOTA", str(n.id), "activo", str(bool(datos.activo)).lower(), str(n.activo).lower(), motivo)
        return _fila_nota(n, overrides.vigentes(db, "NOTA", [n.id]).get(str(n.id)))
    if not n:
        n = NotaSAC(tipo_fuente="INTERNAL_GUIDANCE")  # nota propia: guía interna, nunca texto legal
        db.add(n)
    caps = sorted({c.strip().zfill(2) for c in datos.capitulos if c.strip().isdigit()})
    n.ambito, n.codigo, n.numero = datos.ambito, datos.codigo.strip().upper()[:10], (datos.numero or "").strip()[:20]
    n.texto, n.capitulos, n.activo = datos.texto.strip(), caps, datos.activo
    n.actualizado_en = ahora()
    db.flush()
    return _fila_nota(n)


def borrar_nota(db: Session, user: Usuario, nota_id: int, motivo: str | None = None) -> None:
    """Una nota propia se borra; una oficial solo se desactiva con un override."""
    exigir(user, "aranceles.editar")
    n = db.get(NotaSAC, nota_id)
    if not n:
        raise ErrorNegocio("The note does not exist.", 404, "no_encontrado")
    if n.tipo_fuente in CARGADAS_NOTA:
        overrides.poner(db, user, "NOTA", str(n.id), "activo", "false", str(n.activo).lower(), motivo or "Deactivated by the user")
        return
    db.delete(n)


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
    fuentes = _lista(filtros.get("fuente"))  # códigos de fuente oficial
    if fuentes:
        from app.modelos import FuenteOficial

        q = q.where(IncisoNacional.fuente_id.in_(select(FuenteOficial.id).where(FuenteOficial.codigo.in_(fuentes))))
    if filtros.get("activo") in ("true", "false"):
        q = q.where(IncisoNacional.activo.is_(filtros["activo"] == "true"))
    return q


def _fila_inciso(x: IncisoNacional, sac: dict) -> dict:
    from sqlalchemy.orm import object_session

    return {"id": x.id, "pais": x.pais, "codigo": x.codigo, "codigo_txt": _fmt(x.codigo), "sub6": x.sub6,
            "sac": sac.get(x.sub6), "descripcion": x.descripcion, "dai": x.dai, "cond": x.cond or {},
            "cond_txt": cond_texto(object_session(x), x.cond), "prio": x.prio, "nota": x.nota, "fuente": x.fuente,
            "fuente_txt": FUENTES.get(x.fuente, x.fuente), "activo": x.activo, **_procedencia_txt(object_session(x), x)}


def _procedencia_txt(db: Session, x) -> dict:
    """Fuente oficial y versión de un dato oficial (para mostrar de dónde sale)."""
    from app.modelos import FuenteOficial, VersionDataset

    f = db.get(FuenteOficial, x.fuente_id) if x.fuente_id else None
    v = db.get(VersionDataset, x.version_id) if x.version_id else None
    return {"fuente_oficial": f.codigo if f else None, "autoridad": f.autoridad if f else None, "version": v.codigo if v else None}


def listar_incisos(db: Session, user: Usuario, filtros: dict, page: int, size: int, orden: str | None) -> dict:
    exigir(user, "producto.ver")
    q = _q_incisos(filtros)
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    col, _, dirn = (orden or "codigo:asc").partition(":")
    campo = {"pais": IncisoNacional.pais, "codigo": IncisoNacional.codigo, "fuente": IncisoNacional.fuente,
             "dai": IncisoNacional.dai}.get(col, IncisoNacional.codigo)
    filas = db.scalars(q.order_by(campo.desc() if dirn == "desc" else campo.asc(), IncisoNacional.pais, IncisoNacional.id)
                       .offset((page - 1) * size).limit(size)).all()
    sac = textos_sac(db, {x.sub6 for x in filas}) if filas else {}
    por_pais = dict(db.execute(select(IncisoNacional.pais, func.count()).group_by(IncisoNacional.pais)).all())
    from app.modulos.clasificacion import overrides

    ovs = overrides.vigentes(db, "INCISO", [x.id for x in filas]) if filas else {}
    items = []
    for x in filas:
        d = _fila_inciso(x, sac)
        # Línea oficial: no se edita; lo propio de la empresa va como override (descripción, nota, activo)
        d["oficial"] = _es_oficial(x)
        d["override"] = ovs.get(str(x.id)) or None
        if d["override"]:
            d["descripcion_oficial"] = x.descripcion
            d["descripcion"] = d["override"].get("descripcion") or x.descripcion
        items.append(d)
    return {"items": items, "total": total, "page": page, "size": size, "por_pais": por_pais}


def _cond_limpia(db: Session, cond: dict | None) -> dict:
    oc = opciones_cond(db)
    out = {}
    for k, v in (cond or {}).items():
        if k not in oc or v in (None, "", []):
            continue
        d = oc[k]
        if d["tipo"] == "numero":
            try:
                out[k] = float(v)
            except (TypeError, ValueError):
                raise ErrorNegocio(f"{d['label']}: write a number.", 422, "validacion") from None
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
    exigir(user, "aranceles.editar")
    ps = _paises_dict(db)
    pais = (datos.pais or "").upper()
    if pais not in ps:
        raise ErrorNegocio("Choose a country loaded in the tariff schedule.", 422, "validacion")
    cod = _dig(datos.codigo)
    if msg := ps[pais].error_longitud(cod):
        raise ErrorNegocio(msg, 422, "validacion")
    x = db.get(IncisoNacional, inciso_id) if inciso_id else None
    if inciso_id and not x:
        raise ErrorNegocio("The code does not exist.", 404, "no_encontrado")
    if x and _es_oficial(x):
        # El dato oficial no se edita: lo propio va en la capa custom (override con
        # motivo) y en la regla de selección (condiciones y prioridad)
        if pais != x.pais or cod != x.codigo or (datos.dai or "").replace("%", "").strip() not in ("", x.dai or ""):
            raise ErrorNegocio("Official national codes cannot change their country, code or duty; load a new version instead.", 422, "oficial")
        cambios = {"descripcion": (datos.descripcion or "").strip()[:300] or None, "nota": (datos.nota or "")[:300] or None, "activo": datos.activo}
        guardar_override_inciso(db, user, x, cambios, datos.motivo)
        cond = _cond_limpia(db, datos.cond)
        if cond != (x.cond or {}) or (datos.prio or 0) != (x.prio or 0):
            x.cond = cond
            x.prio = datos.prio or 0
            if x.regla:
                x.regla.tipo_fuente = "MANUAL"  # la empresa cambió cómo se elige: regla propia
        db.flush()
        return {"id": x.id}
    # Una línea nueva es un dato oficial: se escribe desde una publicación, con su
    # fuente y su versión (no hay líneas «propias» de la empresa)
    fuente, version = _procedencia(db, getattr(datos, "fuente", None), getattr(datos, "version", None), pais)
    v_ok = _version_de_pais(version, ps[pais])
    if not v_ok:
        raise ErrorNegocio(f"Version {version.codigo} is not a tariff version of {pais} or of the regional SAC.", 422, "validacion")
    _version_editable(version)
    desde, hasta = _vigencia(version, getattr(datos, "vigente_desde", None))
    if not _en_arbol(db, cod):
        raise ErrorNegocio(f"{_fmt(cod)} does not hang from a subheading of the official tariff tree.", 422, "codigo_inexistente")
    x = IncisoNacional(pais=pais, codigo=cod, sub6=cod[:6], fuente="oficial", fuente_id=fuente.id, version_id=version.id,
                       vigente_desde=desde, vigente_hasta=hasta, url=fuente.url, creado_por=user.id)
    db.add(x)
    x.descripcion = (datos.descripcion or "").strip()[:300] or None
    x.dai = (datos.dai or "").replace("%", "").strip()[:10] or None
    x.cond = _cond_limpia(db, datos.cond)
    if x.regla:
        x.regla.tipo_fuente = "MANUAL"  # condiciones puestas por la empresa: capa propia, nunca legal
    x.prio, x.nota, x.activo = datos.prio or 0, (datos.nota or "")[:300] or None, datos.activo
    db.flush()
    registrar(db, user, "aranceles", x.id, "codigo_nacional", {"pais": pais, "codigo": _fmt(cod)})
    return {"id": x.id}


def _es_oficial(x: IncisoNacional) -> bool:
    return x.fuente == "oficial" or x.version_id is not None


def _procedencia(db: Session, fuente_cod: str | None, version_cod: str | None, pais: str | None = None):
    """Fuente oficial y versión de una carga de líneas: obligatorias."""
    from app.modelos import FuenteOficial, VersionDataset

    if not fuente_cod or not version_cod:
        raise ErrorNegocio("National tariff lines are official data: give the official source and the version they come from.",
                           422, "sin_procedencia")
    f = db.scalar(select(FuenteOficial).where(FuenteOficial.codigo == fuente_cod.strip()))
    v = db.scalar(select(VersionDataset).where(VersionDataset.codigo == version_cod.strip()))
    if not f:
        raise ErrorNegocio(f"The official source {fuente_cod} does not exist.", 422, "validacion")
    if not v:
        raise ErrorNegocio(f"The version {version_cod} does not exist.", 422, "validacion")
    from app.modulos.clasificacion.oficial import problemas_fuente, problemas_version

    faltas = list(dict.fromkeys(problemas_fuente(f) + problemas_version(v)))
    if faltas:
        raise ErrorNegocio("Official data needs a traceable source: " + " ".join(faltas), 422, "fuente_no_trazable",
                           [{"mensaje": m} for m in faltas])
    return f, v


def _vigencia(v, desde) -> tuple:
    """La vigencia de una línea: la que se indica o la de su versión; nunca se supone."""
    desde = desde or v.vigente_desde
    if not desde:
        raise ErrorNegocio(f"Version {v.codigo} has no validity date: give the date the lines are valid from (as published).",
                           422, "sin_vigencia")
    return desde, v.vigente_hasta


def _version_de_pais(v, p) -> bool:
    return (v.ambito or "").upper() in (p.iso, "REGIONAL")


def _version_editable(v) -> None:
    """Una versión publicada no cambia: sus líneas llegan por la carga oficial
    por etapas (previa → diferencias → publicar). A mano o desde Excel solo se
    escriben líneas de una versión en borrador o dinámica."""
    if (v.estado or "").upper() not in ("BORRADOR", "DINAMICA"):
        raise ErrorNegocio(f"Version {v.codigo} is published and does not change. Load the new lines in a draft version, "
                           "or through the official staged upload.", 422, "version_publicada")


def _en_arbol(db: Session, cod: str) -> bool:
    """La línea cuelga de una subpartida del árbol oficial vigente."""
    from app.modulos.clasificacion.motor_clasificacion import codigo_existe

    return bool(cod) and len(cod) >= 6 and codigo_existe(db, cod[:6])


def guardar_override_inciso(db: Session, user: Usuario, x: IncisoNacional, cambios: dict, motivo: str | None,
                            desde=None, hasta=None) -> dict:
    """Personaliza una línea nacional oficial sin tocarla: descripción interna,
    nota o apagarla para la empresa, con motivo, usuario, fecha y vigencia."""
    oficial = {"descripcion": x.descripcion, "nota": x.nota, "activo": "true" if x.activo else "false"}
    for campo, valor in cambios.items():
        if valor is None and campo == "activo":
            continue
        v = ("true" if valor else "false") if campo == "activo" else valor
        if campo != "activo" and valor is None:
            continue
        overrides.poner(db, user, "INCISO", str(x.id), campo, v, oficial[campo], motivo, desde, hasta)
    db.flush()
    return {"id": x.id, "overrides": overrides.vigentes(db, "INCISO", [x.id]).get(str(x.id), {}),
            "historial": overrides.historial(db, "INCISO", str(x.id))}


def quitar_override_inciso(db: Session, user: Usuario, inciso_id: int) -> dict:
    exigir(user, "aranceles.editar")
    if not db.get(IncisoNacional, inciso_id):
        raise ErrorNegocio("The code does not exist.", 404, "no_encontrado")
    return {"quitados": overrides.quitar(db, user, "INCISO", str(inciso_id))}


def borrar_incisos(db: Session, user: Usuario, ids: list[int]) -> dict:
    """Las líneas oficiales de una versión publicada no se borran (se apagan
    para la empresa con un override); solo las de una versión en borrador."""
    from app.modelos import VersionDataset

    exigir(user, "aranceles.editar")
    xs = db.scalars(select(IncisoNacional).where(IncisoNacional.id.in_(ids))).all()
    borrador = {v.id for v in db.scalars(select(VersionDataset).where(VersionDataset.estado == "BORRADOR"))}
    if any(x.version_id not in borrador for x in xs):
        raise ErrorNegocio("Official national codes are not deleted: turn them off for your company with an override.", 422, "oficial")
    for x in xs:
        db.delete(x)
    registrar(db, user, "aranceles", 0, "borrar_codigos", {"n": len(xs)})
    return {"borrados": len(xs)}


# ---- Cargas desde Excel ------------------------------------------------------------------
def _columnas_cond(db: Session) -> list[tuple[str, dict]]:
    """Columnas de condición de la plantilla: una por dato, con nombre único."""
    out, vistos = [], {}
    for k, d in opciones_cond(db).items():
        n = vistos[d["label"]] = vistos.get(d["label"], 0) + 1
        out.append((k, {**d, "label": d["label"] if n == 1 else f"{d['label']} ({k})"}))
    return out


def _alias_incisos(db: Session) -> dict[str, str]:
    a = {"country": "pais", "pais": "pais", "iso": "pais", "code": "codigo", "national_code": "codigo", "codigo": "codigo",
         "inciso": "codigo", "description": "descripcion", "descripcion": "descripcion", "duty": "dai", "duty_dai": "dai",
         "dai": "dai", "duty_dai_percent": "dai", "priority": "prio", "prioridad": "prio", "note": "nota", "nota": "nota",
         "active": "activo"}
    for k, d in _columnas_cond(db):
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
    for _k, d in _columnas_cond(db):
        ayuda = "Condition that selects this code. Leave empty if it does not matter."
        if d["tipo"] == "sino":
            cols.append({"nombre": d["label"], "opciones": ["Yes", "No"], "ayuda": ayuda})
        elif d["tipo"] == "numero":
            cols.append({"nombre": d["label"], "ayuda": ayuda + " Number in US$."})
        else:
            cols.append({"nombre": d["label"], "opciones": list(d["ops"].values()),
                         "ayuda": ayuda + " Several values separated by commas."})
    iso = (pais or regla("PAIS_BASE_CLASIF") or next(iter(ps), "")).upper()  # el país base de la empresa
    n = ps[iso].digitos if iso in ps else 10
    ej = [[iso, "6404.19.90" + "0" * max(0, n - 8), "Los demás", "15", 0, "", "Adult"] + [""] * (len(cols) - 7)]
    return plantilla("National tariff codes", cols, ej, [
        "One row per national code, with all its digits (8 to 14, or the lengths set for its country).",
        "The condition columns say when a product takes this code (gender, age, CIF value, footwear style…). "
        "The engine picks the code whose conditions match the technical sheet.",
        "A row with the same country, code and conditions updates the existing code.",
    ])


def importar_incisos(db: Session, user: Usuario, nombre: str, contenido: bytes, pais: str | None = None,
                     reemplazar: bool = False, fuente: str | None = None, version: str | None = None, vigente_desde=None) -> dict:
    """Carga de líneas nacionales desde la publicación oficial de un país: toda
    la carga lleva su fuente y su versión. «Reemplazar» solo quita las líneas
    de esa misma versión (las otras versiones no se tocan)."""
    exigir(user, "aranceles.editar")
    f_ofi, v_ofi = _procedencia(db, fuente, version)
    _version_editable(v_ofi)
    desde, hasta = _vigencia(v_ofi, vigente_desde)
    ps = _paises_dict(db)
    filas = leer(nombre, contenido, _alias_incisos(db))
    oc = opciones_cond(db)
    errores, validas = [], []
    for f in filas:
        iso = (f.get("pais") or pais or "").strip().upper()
        if iso not in ps and f.get("pais"):
            iso = next((k for k, x in ps.items() if norm(x.nombre) == norm(f["pais"])), iso)
        if iso not in ps:
            errores.append({"fila": f["_fila"], "mensaje": f"Country “{f.get('pais') or ''}” is not in the tariff schedule."})
            continue
        if not _version_de_pais(v_ofi, ps[iso]):
            errores.append({"fila": f["_fila"], "mensaje": f"Version {v_ofi.codigo} is not a tariff version of {iso}."})
            continue
        cod = _dig(f.get("codigo"))
        if msg := ps[iso].error_longitud(cod):
            errores.append({"fila": f["_fila"], "mensaje": f"{iso}: {msg}"})
            continue
        if not _en_arbol(db, cod):
            errores.append({"fila": f["_fila"], "mensaje": f"{_fmt(cod)} does not hang from a subheading of the official tariff tree."})
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
            for x in db.scalars(select(IncisoNacional).where(IncisoNacional.pais == iso, IncisoNacional.version_id == v_ofi.id)):
                db.delete(x)
                borrados += 1
        db.flush()
    # Una línea es única por país, código y versión: la misma fila actualiza
    existentes = {} if reemplazar else {
        (x.pais, x.codigo): x
        for x in db.scalars(select(IncisoNacional).where(IncisoNacional.pais.in_({v[0] for v in validas}),
                                                         IncisoNacional.version_id == v_ofi.id))}
    for iso, cod, cond, f, prio in validas:
        clave = (iso, cod)
        x = existentes.get(clave)
        if x:
            actualizados += 1
        else:
            x = IncisoNacional(pais=iso, codigo=cod, sub6=cod[:6], cond=cond, fuente="oficial", fuente_id=f_ofi.id, version_id=v_ofi.id,
                               vigente_desde=desde, vigente_hasta=hasta, url=f_ofi.url, creado_por=user.id)
            db.add(x)
            existentes[clave] = x
            creados += 1
        if f.get("descripcion"):
            x.descripcion = f["descripcion"][:300]
        if f.get("dai"):
            x.dai = f["dai"].replace("%", "").strip()[:10]
        if f.get("nota"):
            x.nota = f["nota"][:300]
        x.cond = cond
        x.prio = prio
        if x.regla:
            x.regla.tipo_fuente = "MANUAL"  # condiciones de la carga: configuración de la empresa, no texto legal
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
    """Descripciones internas por archivo: se guardan como capa custom sobre el
    árbol oficial (el texto oficial solo cambia con una versión nueva)."""
    exigir(user, "aranceles.editar")
    filas = leer(nombre, contenido, {"code": "codigo", "codigo": "codigo", "description": "descripcion",
                                     "descripcion": "descripcion", "note": "nota", "nota": "nota"})
    v = _version_sac(db)
    oficiales = dict(db.execute(select(NodoArancel.codigo_norm, NodoArancel.descripcion).where(
        NodoArancel.version_id == (v.id if v else -1), NodoArancel.pais.is_(None), NodoArancel.nivel.in_(("PARTIDA", "SUBPARTIDA")))).all())
    creados = actualizados = 0
    errores = []
    for f in filas:
        cod = _dig(f.get("codigo"))
        if len(cod) not in (4, 6) or not (f.get("descripcion") or "").strip():
            errores.append({"fila": f["_fila"], "mensaje": "Code with 4 or 6 digits and description are required."})
            continue
        if cod not in oficiales:
            errores.append({"fila": f["_fila"], "mensaje": f"{_fmt(cod)} is not in the official tariff in force."})
            continue
        motivo = f"Uploaded file {nombre}"[:300]
        if overrides.poner(db, user, "NODO", cod, "descripcion", f["descripcion"].strip()[:400], oficiales[cod], motivo):
            actualizados += 1
        if (f.get("nota") or "").strip():
            overrides.poner(db, user, "NODO", cod, "nota", f["nota"].strip()[:300], None, motivo)
    registrar(db, user, "aranceles", 0, "importar_sac", {"creados": creados, "actualizados": actualizados})
    return {"creados": creados, "actualizados": actualizados, "errores": errores[:200]}


AMBITO_ALIAS = {"reglas": "reglas", "general rules": "reglas", "general rule": "reglas", "rgi": "reglas", "regla": "reglas",
                "seccion": "seccion", "section": "seccion", "section note": "seccion", "capitulo": "capitulo",
                "chapter": "capitulo", "chapter note": "capitulo", "subpartida": "subpartida", "subheading": "subpartida",
                "subheading note": "subpartida", "complementaria": "complementaria",
                "central american complementary note": "complementaria", "ncc": "complementaria"}


def plantilla_notas() -> bytes:
    return plantilla("SAC legal notes", [
        {"nombre": "Kind", "req": True, "opciones": list(AMBITOS.values()), "ancho": 16},
        {"nombre": "Section or chapter", "req": True, "ayuda": "RGI for the general rules, XI for a section, 64 for a chapter.", "ancho": 14},
        {"nombre": "Number", "ayuda": "Number of the note, e.g. 4, 2 A), Subp. 1.", "ancho": 12},
        {"nombre": "Text", "req": True, "ayuda": "Official text of the note, as published in the SAC.", "ancho": 90},
        {"nombre": "Applies to chapters", "ayuda": "Chapters separated by commas (empty = all).", "ancho": 20},
        {"nombre": "Active", "opciones": ["Yes", "No"], "ancho": 8},
    ], [["Chapter note", "64", "4", "Salvo lo dispuesto en la Nota 3 de este Capítulo: a) la materia de la parte superior …", "64", "Yes"]],
        ["One row per note. A note with the same kind, section or chapter and number is replaced with the new text.",
         "Use it to load the official text of the SAC in force."])


def importar_notas(db: Session, user: Usuario, nombre: str, contenido: bytes) -> dict:
    exigir(user, "aranceles.editar")
    filas = leer(nombre, contenido, {"kind": "ambito", "tipo": "ambito", "section_or_chapter": "codigo", "chapter": "codigo",
                                     "codigo": "codigo", "number": "numero", "numero": "numero", "text": "texto",
                                     "texto": "texto", "applies_to_chapters": "capitulos", "capitulos": "capitulos",
                                     "active": "activo", "activo": "activo"})
    actuales = {(x.ambito, x.codigo, x.numero): x for x in db.scalars(select(NotaSAC))}
    creados = actualizados = 0
    errores = []
    for f in filas:
        amb = AMBITO_ALIAS.get(norm(f.get("ambito") or "").replace("_", " "))
        cod, num, txt = (f.get("codigo") or "").strip().upper(), (f.get("numero") or "").strip(), (f.get("texto") or "").strip()
        if not amb or not cod or not txt:
            errores.append({"fila": f["_fila"], "mensaje": "Kind, section or chapter and text are required."})
            continue
        x = actuales.get((amb, cod, num))
        if x and x.tipo_fuente in CARGADAS_NOTA:
            # Nota oficial: el texto del archivo queda como capa custom (el oficial no se pisa)
            if overrides.poner(db, user, "NOTA", str(x.id), "texto", txt, x.texto, f"Uploaded file {nombre}"[:300]):
                actualizados += 1
            continue
        if x:
            actualizados += 1
        else:
            x = actuales[(amb, cod, num)] = NotaSAC(ambito=amb, codigo=cod[:10], numero=num[:20])
            db.add(x)
            creados += 1
        x.texto = txt
        caps = [c.strip().zfill(2) for c in str(f.get("capitulos") or "").split(",") if c.strip().isdigit()]
        x.capitulos = caps or ([cod.zfill(2)] if cod.isdigit() else x.capitulos or [])
        x.activo = si_no(f.get("activo")) is not False
        x.tipo_fuente = "INTERNAL_GUIDANCE"  # un archivo sin fuente oficial es guía interna
        x.actualizado_en = ahora()
    registrar(db, user, "aranceles", 0, "importar_notas", {"creados": creados, "actualizados": actualizados})
    return {"creados": creados, "actualizados": actualizados, "errores": errores[:200]}


def exportar_notas(db: Session, user: Usuario, filtros: dict, formato: str) -> bytes:
    r = listar_notas(db, user, filtros)
    columnas = [("Kind", 1, False), ("Section or chapter", 0.8, False), ("Number", 0.7, False), ("Text", 6, False),
                ("Applies to chapters", 1, False)]
    filas = [[x["ambito_txt"], x["codigo"], x["numero"], x["texto"], ", ".join(x["capitulos"]) or "All"] for x in r["items"]]
    texto = _filtros_txt(filtros, {"q": "Search", "capitulo": "Chapter"})
    titulo, sub = "SAC legal notes", "General rules, section, chapter and subheading notes"
    if formato == "pdf":
        return documentos.pdf_reporte(titulo, sub, texto, [("Notes", f"{r['total']:,}")], columnas,
                                      [[str(v) for v in f] for f in filas])
    return exportar.exportar_reporte(titulo, sub, texto, [("Notes", f"{r['total']:,}")], columnas, filas)


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
              x["prio"], " · ".join(v for v in (x["fuente_oficial"], x["version"]) if v) or "—", "Yes" if x["activo"] else "No"] for x in r["items"]]
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
    return {"condiciones": {k: {"label": d["label"], "tipo": d["tipo"], "ops": d["ops"]} for k, d in opciones_cond(db).items()},
            "fuentes": FUENTES, "fuentes_oficiales": _fuentes_oficiales(db), "versiones_oficiales": _versiones_oficiales(db)}


def _fuentes_oficiales(db: Session) -> list[dict]:
    from app.modelos import FuenteOficial

    return [{"codigo": f.codigo, "texto": f"{f.codigo} · {f.autoridad}", "ambito": f.ambito}
            for f in db.scalars(select(FuenteOficial).order_by(FuenteOficial.codigo))]


def _versiones_oficiales(db: Session) -> list[dict]:
    """Versiones a las que puede pertenecer una línea nacional (con su fuente)."""
    from app.modelos import VersionDataset

    return [{"codigo": v.codigo, "ambito": v.ambito, "estado": v.estado, "fuente": v.fuente.codigo if v.fuente else None,
             "texto": f"{v.codigo} · {v.etiqueta or v.dataset}", "vigente_desde": v.vigente_desde}
            for v in db.scalars(select(VersionDataset).order_by(VersionDataset.codigo)) if v.ambito]
