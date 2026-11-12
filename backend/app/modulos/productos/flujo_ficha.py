"""Flujo de la ficha técnica: guardarla (con la sugerencia del motor de
clasificación), enviarla a revisión, observarla, aprobarla (también en lote),
confirmar partidas por país, abrir una versión nueva y lo que aprende el
clasificador de cada decisión.
"""
from datetime import date, timedelta

from sqlalchemy.orm import Session, object_session

from app.core import dinero
from app.core.errores import ErrorNegocio
from app.modelos import (
    IncisoNacional,
    PartidaPais,
    Producto,
    ProductoVersion,
    Usuario,
    ahora,
)
from app.modulos.acceso.permisos import exigir, tiene
from app.modulos.comex import flujo
from app.modulos.comex.servicio import (  # noqa: F401
    APROBADOS,
    BORRADORES,
    ESTADOS,
    PENDIENTES,
    digitos,
    fmt_codigo,
    sin_marca,
)
from app.modulos.comun.historial import registrar, tocar, verificar_version
from app.modulos.productos.consulta import detalle, ver_producto
from app.modulos.productos.productos import (
    _codigo_fila,
    _guardar_partidas,
    descripcion_comercial_simple,
    marca_de,
    nombre_producto,
)

# ---- Guardar la ficha técnica ------------------------------------------------
CAMPOS_TEXTO = {"nombre": 200, "notas": 1000}  # el genérico sale del código de artículo


def _categoria_de_familia(p: Producto) -> str | None:
    """Sin categoría en su ficha, la que eligió su familia (sección de comercio exterior)."""
    from app.modulos.comex import familia

    db = object_session(p)
    return familia.categoria_de(db, p.grupo_producto_id) if db is not None and p.grupo_producto_id else None


def entrada_producto(p: Producto, extra: dict | None = None) -> dict:
    """La ficha natural del producto para el motor único (la misma para la
    pantalla, el guardado, la aprobación y el lote)."""
    f = dict(p.comex.ficha or {})
    marca = marca_de(p)
    return {"categoria": p.comex.tipo or _categoria_de_familia(p), "ficha": f, "nombre": p.nombre, "uso": f.get("uso"), "tallas": f.get("tallas"),
            "marca": marca.nombre if marca else None, "proveedor": p.proveedor.nombre if p.proveedor else None,
            "origen": p.comex.pais_origen, "generico": p.codigo_generico, "producto_id": p.id, "alertas_ok": p.comex.alertas_ok or [],
            "partidas": {x.pais: {"codigo": x.codigo, "manual": True} for x in p.partidas if x.manual}, "detectar": False, **(extra or {})}


def _valor_legible(c: dict) -> str:
    v = c.get("valor")
    if c["tipo_dato"] == "boolean":
        return "Yes" if v else "No"
    if isinstance(v, list):
        return ", ".join(next((o["etiqueta"] for o in c["opciones"] if o["codigo"] == x), str(x)) for x in v)
    return next((o["etiqueta"] for o in c["opciones"] if o["codigo"] == v), str(v))


def _fuente_motor(r: dict) -> str:
    top = (r.get("candidatos") or [{}])[0]
    origen = top.get("origen") or []
    if any(o.startswith("regla") for o in origen):
        return "regla"
    return "historial" if "historial" in origen else "texto"


def _aplicar_motor(p: Producto, r: dict) -> None:
    """Guarda lo que calculó el motor único (sin aprobar nada)."""
    if r.get("categoria"):
        p.comex.tipo = r["categoria"]["codigo"][:30]
    p.comex.ficha = r["ficha"]
    hs6, sac = r.get("hs6"), r["clasificacion"]["sac"]["codigo"]
    p.comex.sugerido, p.comex.sac_sugerido = hs6, sac
    p.comex.confianza = r["confianza"]
    p.comex.fuente = _fuente_motor(r) if hs6 else None
    p.comex.perfil = (r.get("perfil") or "")[:200] or None
    legibles = [[c["etiqueta"], _valor_legible(c)] for c in r["campos"]
                if c["seccion"] in ("producto", "caracteristicas", "composicion", "nacional") and c["tipo_dato"] != "composition"
                and c.get("valor") not in (None, "", [], False)]
    p.comex.analisis = {"razones": r["razones"], "alternativas": r["alternativas"][:20], "avisos": [a["texto"] for a in r["avisos"]][:20],
                  "faltantes": [f["etiqueta"] for f in r["faltantes"]][:20], "alertas": r["alertas"][:60], "revision_por": r["revision_por"][:20],
                  "requiere_revision": r["requiere_revision"], "atributos": legibles[:60],
                  "tipo_txt": (r.get("categoria") or {}).get("nombre"), "version": r.get("version")}
    if not (p.comex.ficha or {}).get("descManual"):
        p.comex.descripcion_aduana = (r["descripciones"]["aduana"] or "")[:400] or None
    if not (p.comex.ficha or {}).get("comManual"):
        p.comex.descripcion_comercial = (r["descripciones"]["comercial"] or "")[:300] or descripcion_comercial_simple(p)
    faltan = [f["etiqueta"] for f in r["faltantes"]]
    if not p.comex.tipo:
        faltan.insert(0, "Product type")
    if not hs6:
        faltan.append("Data for the code")
    p.comex.ficha_completa = not faltan
    p.comex.faltan = [str(x)[:120] for x in faltan][:20]
    if p.comex.estado not in APROBADOS:
        _guardar_partidas(p, {x["pais"]: {"codigo": x["codigo"], "dai": x["dai"], "estado": x["estado"], "fuente": x["fuente"],
                                          "manual": x["manual"]} for x in r["clasificacion"]["paises"]})
        if p.comex.estado != "revision":
            p.comex.estado = "sugerida" if p.comex.ficha_completa and p.comex.sugerido else "borrador"


def clasificar_y_guardar(db: Session, p: Producto, extra: dict | None = None, catalogo=None) -> dict:
    from app.modulos.clasificacion.motor_clasificacion import clasificar_producto

    r = clasificar_producto(db, entrada_producto(p, extra), catalogo=catalogo)
    _aplicar_motor(p, r)
    return r


def guardar_ficha(db: Session, user: Usuario, producto_id: int, datos) -> dict:
    exigir(user, "producto.ficha")
    p = ver_producto(db, user, producto_id)
    verificar_version(p, datos.version, "product")
    if p.comex.estado in APROBADOS:
        raise ErrorNegocio("The technical sheet is approved. Create a new version to change it.", 409, "ficha_aprobada")
    if p.comex.estado == "revision" and not tiene(user, "producto.clasificar"):
        raise ErrorNegocio("The technical sheet was sent to review. Take it back to draft to change it.", 409, "en_revision")
    antes = {"tipo": p.comex.tipo, "ficha": p.comex.ficha, "estado": p.comex.estado}
    p.comex.tipo = (datos.tipo or None) and datos.tipo[:30]
    p.comex.ficha = datos.ficha or {}
    for campo, largo in CAMPOS_TEXTO.items():
        v = getattr(datos, campo, None)
        if v is not None:
            setattr(p if campo == "nombre" else p.comex, campo, str(v).strip()[:largo] or None)
    if datos.pais_origen is not None:
        p.comex.pais_origen = (datos.pais_origen or "").upper()[:2] or None
    if datos.pais_procedencia is not None:
        p.comex.pais_procedencia = (datos.pais_procedencia or "").upper()[:2] or None
    p.comex.alertas_ok = list(datos.alertas_ok or [])[:100]
    # Códigos nacionales escritos a mano (se validan en el motor: existen o tienen una longitud válida)
    manuales = {iso: x for iso, x in (datos.partidas or {}).items() if isinstance(x, dict) and x.get("manual") and digitos(x.get("codigo"))}
    for x in list(p.partidas):
        if x.manual and x.pais not in manuales:
            p.partidas.remove(x)
    _guardar_partidas(p, {**{x.pais: {"codigo": x.codigo, "dai": x.dai, "estado": x.estado, "fuente": x.fuente, "manual": x.manual}
                             for x in p.partidas}, **{iso: {**x, "estado": "manual"} for iso, x in manuales.items()}})
    devuelto = p.comex.estado == "observado"
    clasificar_y_guardar(db, p, {"tocados": list(datos.tocados or [])})
    if datos.descripcion_aduana is not None and (p.comex.ficha or {}).get("descManual"):
        p.comex.descripcion_aduana = datos.descripcion_aduana.strip()[:400] or None
    if datos.descripcion_comercial is not None and (p.comex.ficha or {}).get("comManual"):
        p.comex.descripcion_comercial = datos.descripcion_comercial.strip()[:300] or None
    tocar(p)
    cambios = [k for k in ("tipo", "ficha") if antes[k] != getattr(p.comex, k)]
    registrar(db, user, "producto", p.id, "ficha_guardada",
              {"cambios": cambios, "estado": [antes["estado"], p.comex.estado], "sugerido": fmt_codigo(p.comex.sugerido) or None,
               "devuelto": devuelto})
    return detalle(db, user, p.id)


def clasificar_lote(db: Session, user: Usuario, ids: list[int]) -> dict:
    """Clasifica varios productos con el mismo motor que la ficha (lo que se
    deduce del nombre y la composición completa lo vacío; nada se pisa)."""
    from app.modulos.productos.ficha import catalogo

    exigir(user, "producto.ficha")
    cat = catalogo(db)
    hechos, omitidos = 0, []
    for pid in ids:
        p = ver_producto(db, user, pid)
        if p.comex.estado in APROBADOS:
            omitidos.append({"id": p.id, "mensaje": f"{nombre_producto(p)} is already approved."})
            continue
        antes = p.comex.estado
        clasificar_y_guardar(db, p, {"detectar": True}, catalogo=cat)
        tocar(p)
        registrar(db, user, "producto", p.id, "clasificado", {"estado": [antes, p.comex.estado], "sugerido": fmt_codigo(p.comex.sugerido) or None})
        hechos += 1
    return {"clasificados": hechos, "omitidos": omitidos}


# ---- Aprobar, devolver y versiones -------------------------------------------
def _aprobar(db: Session, user: Usuario, p: Producto, codigo: str | None, partidas: dict | None, lote: bool = False) -> None:
    """Aprueba con el motor único: el código se vuelve a validar contra el árbol
    de la versión vigente y contra las reglas; cada país con su línea nacional
    de la versión vigente del país. Guarda la evidencia completa."""
    from app.modulos.clasificacion.motor_clasificacion import clasificar_producto

    oficial = digitos(codigo or p.comex.propuesta or p.comex.sac_sugerido or p.comex.sugerido)
    if len(oficial) < 6:
        raise ErrorNegocio(f"{nombre_producto(p)}: there is no HS code to approve.", 422, "sin_partida")
    if len(oficial) > 14:
        raise ErrorNegocio("The HS code is too long.", 422, "validacion")
    # Cada línea nacional que indica quien aprueba es una elección: el motor la valida
    elegidas = {iso: x for iso, x in (partidas or {}).items() if isinstance(x, dict) and digitos(x.get("codigo"))}
    if partidas is None:
        elegidas = {x.pais: {"codigo": x.codigo, "manual": True, "sugerido": x.sugerido, "motivo": x.motivo} for x in p.partidas if x.manual}
    r = clasificar_producto(db, entrada_producto(p, {"codigo_final": oficial,
                                                     "partidas": {iso: {"codigo": digitos(x["codigo"])} for iso, x in elegidas.items()}}))
    errores = [a["msg"] for a in r["alertas"] if a["nivel"] == "error" and a.get("origen") in ("codigo", "capitulo")]
    if any(a.get("origen") == "capitulo" and a["nivel"] == "error" for a in r["alertas"]):
        raise ErrorNegocio(f"{nombre_producto(p)}: " + " ".join(errores), 422, "capitulo_no_habilitado")
    if len(oficial) > 6 and r["sac"] != oficial:
        raise ErrorNegocio(f"{fmt_codigo(oficial)} is not an official SAC line of the tariff in force. "
                           "The product keeps its HS6 and each country chooses its own national line.", 422, "no_es_linea_sac")
    if errores:
        raise ErrorNegocio(f"{nombre_producto(p)}: " + " ".join(errores), 422, "codigo_invalido")
    paises = r["clasificacion"]["paises"]
    invalidos = [x for x in paises if x["estado"] == "invalido"]
    if invalidos:
        raise ErrorNegocio("; ".join(f"{x['pais']}: {x['error']}" for x in invalidos), 422, "codigo_nacional_invalido")
    # Con incertidumbre el caso queda pendiente: nunca se aprueba solo. En lote no se aprueba lo que pide revisión
    if lote and (r["requiere_revision"] or r["confianza"] == "low"):
        raise ErrorNegocio(f"{nombre_producto(p)}: needs a specialist review (" + "; ".join(r["revision_por"][:2] or ["low legal confidence"]) + ").",
                           422, "requiere_revision")
    # Las líneas nacionales son referencia (la OC y la factura llevan la subpartida de 6 dígitos):
    # aprobar no las exige. Una que solo el historial prefiere o que falta elegir queda pendiente
    # de confirmar por una persona (confirmar_partida), nunca se da por confirmada.
    sug = digitos(p.comex.sugerido)
    p.comex.estado = "aprobado" if not sug or sug[:6] == oficial[:6] else "corregido"
    p.comex.codigo = oficial[:6]
    p.comex.sac_codigo = oficial if len(oficial) > 6 else r["sac"]
    p.comex.propuesta = None
    p.comex.version_arancel_id = r["version"]["id"] if r.get("version") else None
    ahora_ = ahora()
    p.comex.evidencia = {**r["evidencia"], "aprobacion": {"fecha": ahora_.isoformat(), "usuario": user.nombre if user else None, "hs6": p.comex.codigo,
                                                    "sac": p.comex.sac_codigo, "sugerido": sug or None, "confianza": r["confianza"],
                                                    "requiere_revision": r["requiere_revision"], "revision_por": r["revision_por"],
                                                    "razones": r["razones"], "alternativas": r["alternativas"][:10]},
                   "paises": [{k: x.get(k) for k in ("pais", "estado", "codigo", "dai", "inciso_id", "regla", "version", "fuente", "fuente_oficial",
                                                     "manual", "descripcion", "overrides", "historial", "sin_datos_oficiales", "error")}
                              for x in paises]}
    _guardar_partidas(p, {x["pais"]: {"codigo": x["codigo"], "dai": x["dai"], "estado": x["estado"], "fuente": x["fuente"],
                                      "manual": x["manual"] or bool((elegidas.get(x["pais"]) or {}).get("manual")),
                                      "sugerido": (elegidas.get(x["pais"]) or {}).get("sugerido") or x["sugerido"],
                                      "motivo": (elegidas.get(x["pais"]) or {}).get("motivo")} for x in paises})
    db.flush()
    por_pais = {x["pais"]: x for x in paises}
    for fila in p.partidas:
        x = por_pais.get(fila.pais) or {}
        fila.inciso_id = x.get("inciso_id")
        fila.version_id = (x.get("version") or {}).get("id") if x.get("inciso_id") else None
        inc = db.get(IncisoNacional, x["inciso_id"]) if x.get("inciso_id") else None
        fila.fuente_id = inc.fuente_id if inc else None
        fila.evidencia = {"linea_oficial": bool(inc and inc.fuente == "oficial"), "fuente_dato": x.get("fuente"), "regla": x.get("regla"),
                          "version": x.get("version"), "overrides": x.get("overrides"),
                          "impuestos": [{k: i.get(k) for k in ("codigo", "tipo", "tasa", "base_calculo", "base_legal", "fuente")} for i in x.get("impuestos") or []],
                          "regulaciones": [{k: g.get(k) for k in ("codigo", "tipo", "nombre", "autoridad", "base_legal")} for g in x.get("regulaciones") or []]}
        confirmada = x.get("estado") == "ok"
        fila.aprobado_por_id, fila.aprobado_en = ((user.id if user else None), ahora_) if confirmada else (None, None)
    p.comex.revisado_por_id = user.id if user else None
    p.comex.revisado_en = ahora_
    # La decisión queda como conocimiento de la empresa (nunca como dato oficial):
    # el HS6 con la categoría y, por país, la línea oficial con los datos que la eligieron
    from app.modulos.clasificacion.conocimiento import registrar_decision

    origen = "APROBACION" if p.comex.estado == "aprobado" else "CORRECCION"
    hechos = r.get("hechos") or {}
    registrar_decision(db, pais=None, codigo=p.comex.sac_codigo or p.comex.codigo, condiciones={}, origen=origen, categoria=p.comex.tipo, producto_id=p.id, usuario=user)
    for x in paises:
        if x.get("estado") == "ok" and x.get("inciso_id") and x.get("codigo"):  # solo lo confirmado es conocimiento
            claves = {k for o in x.get("opciones") or [] for k in (o.get("cond") or {})} | set(x.get("faltan") or [])
            registrar_decision(db, pais=x["pais"], codigo=x["codigo"], condiciones={k: hechos.get(k) for k in claves if hechos.get(k) is not None},
                               origen=origen, categoria=p.comex.tipo, producto_id=p.id, usuario=user)
    tocar(p)
    registrar(db, user, "producto", p.id, "aprobado" if p.comex.estado == "aprobado" else "corregido",
              {"codigo": fmt_codigo(oficial), "sugerido": fmt_codigo(sug) or None,
               "paises": {x["pais"]: fmt_codigo(x["codigo"]) for x in paises if x.get("codigo")}})


def _pais_aprobado(db: Session, user: Usuario, producto_id: int, pais: str, codigo: str | None = None):
    from app.modulos.clasificacion.motor_clasificacion import clasificar_producto

    p = ver_producto(db, user, producto_id)
    if p.comex.estado not in APROBADOS or not p.comex.codigo:
        raise ErrorNegocio("Approve the product first: the national codes hang from its approved subheading.", 422, "no_aprobado")
    extra = {"codigo_final": p.comex.sac_codigo or p.comex.codigo}
    if codigo is not None:
        extra["partidas"] = {pais: {"codigo": digitos(codigo)}}
    r = clasificar_producto(db, entrada_producto(p, extra))
    x = next((y for y in r["clasificacion"]["paises"] if y["pais"] == pais), None)
    if not x:
        raise ErrorNegocio(f"{pais} is not an active destination country.", 404, "no_encontrado")
    return p, r, x


def opciones_partida(db: Session, user: Usuario, producto_id: int, pais: str) -> dict:
    """Las líneas oficiales vigentes del país para la subpartida aprobada (para confirmar una)."""
    _, _, x = _pais_aprobado(db, user, producto_id, pais.upper())
    return {"pais": x["pais"], "estado": x["estado"], "codigo": x["codigo"], "error": x["error"], "digitos": x["digitos"],
            "opciones": [{"codigo": o["codigo"], "descripcion": o["descripcion"], "cond_txt": o.get("cond_txt"), "dai": o["dai"]} for o in x["opciones"]]}


def confirmar_partida(db: Session, user: Usuario, producto_id: int, pais: str, codigo: str) -> dict:
    """Una persona confirma la línea nacional de un país de un producto ya
    aprobado: el motor la valida contra el arancel vigente del país (solo una
    línea oficial de la subpartida aprobada) y queda como decisión de la empresa."""
    from app.modulos.clasificacion.conocimiento import registrar_decision

    exigir(user, "producto.clasificar")
    pais = pais.upper()
    if not digitos(codigo):
        raise ErrorNegocio("Write or choose the national code.", 422, "validacion")
    p, r, x = _pais_aprobado(db, user, producto_id, pais, codigo)
    if x["estado"] != "ok" or not x.get("inciso_id"):
        raise ErrorNegocio(x.get("error") or f"{fmt_codigo(codigo)} is not an official national line of {pais} for this subheading.",
                           422, "codigo_nacional_invalido", [{"codigo": o["codigo"], "descripcion": o["descripcion"]} for o in x["opciones"]])
    fila = next((y for y in p.partidas if y.pais == pais), None)
    antes = fila.codigo if fila else None
    if not fila:
        fila = PartidaPais(pais=pais)
        p.partidas.append(fila)
    fila.sugerido = fila.sugerido or x.get("sugerido") or fila.codigo
    fila.codigo, fila.dai, fila.estado, fila.fuente, fila.manual = _codigo_fila(x["codigo"]), dinero.porcentaje_o_nota(x.get("dai"))[0], "ok", \
        (x.get("fuente") or None) and str(x["fuente"])[:12], True
    inc = db.get(IncisoNacional, x["inciso_id"])
    fila.inciso_id, fila.version_id = x["inciso_id"], (x.get("version") or {}).get("id")
    fila.fuente_id = inc.fuente_id if inc else None
    fila.evidencia = {"linea_oficial": bool(inc and inc.fuente == "oficial"), "fuente_dato": x.get("fuente"), "regla": x.get("regla"),
                      "version": x.get("version"), "confirmada_despues": True}
    fila.aprobado_por_id, fila.aprobado_en = user.id, ahora()
    hechos = r.get("hechos") or {}
    claves = {k for o in x.get("opciones") or [] for k in (o.get("cond") or {})} | set(x.get("faltan") or [])
    registrar_decision(db, pais=pais, codigo=x["codigo"], condiciones={k: hechos.get(k) for k in claves if hechos.get(k) is not None},
                       origen="APROBACION", categoria=p.comex.tipo, producto_id=p.id, usuario=user)
    tocar(p)
    registrar(db, user, "producto", p.id, "partida_confirmada", {"pais": pais, "codigo": [fmt_codigo(antes) or None, fmt_codigo(x["codigo"])]})
    return detalle(db, user, p.id)


def aprobar(db: Session, user: Usuario, producto_id: int, datos) -> dict:
    exigir(user, "producto.clasificar")
    p = ver_producto(db, user, producto_id)
    verificar_version(p, datos.version, "product")
    flujo.exigir_aprobacion(db, user, p)
    if not p.comex.ficha_completa and not datos.forzar:
        raise ErrorNegocio("The technical sheet is incomplete: " + ", ".join(p.comex.faltan[:4]) + ".", 422, "ficha_incompleta",
                           [{"mensaje": x} for x in p.comex.faltan])
    _aprobar(db, user, p, datos.codigo, datos.partidas)
    return detalle(db, user, p.id)


def aprobar_lote(db: Session, user: Usuario, ids: list[int]) -> dict:
    """Aprueba la partida sugerida de varios productos con su ficha completa.
    Cada uno se aprueba o no por su cuenta; se informa cuáles no."""
    exigir(user, "producto.clasificar")
    if not flujo.activo(db, "aprobacion_lote"):
        raise ErrorNegocio("Bulk approval is turned off: approve each sheet on its own page.", 422, "lote_apagado")
    ok, errores = 0, []
    for pid in ids:
        p = ver_producto(db, user, pid)
        if p.comex.estado in APROBADOS:
            continue
        if p.comex.estado not in ("sugerida", "revision") or not p.comex.ficha_completa:
            errores.append({"id": p.id, "mensaje": f"{nombre_producto(p)}: the sheet is not complete."})
            continue
        try:
            with db.begin_nested():
                flujo.exigir_aprobacion(db, user, p)
                # Solo cuentan como elección las líneas que una persona eligió; las sugeridas se vuelven a validar
                _aprobar(db, user, p, None, None, lote=True)
            ok += 1
        except ErrorNegocio as e:
            errores.append({"id": p.id, "mensaje": e.mensaje})
    return {"aprobados": ok, "errores": errores}


def observar(db: Session, user: Usuario, producto_id: int, datos) -> dict:
    """Observaciones del especialista; con `devolver`, la ficha vuelve al
    proveedor para que la corrija."""
    exigir(user, "producto.clasificar")
    p = ver_producto(db, user, producto_id)
    verificar_version(p, datos.version, "product")
    p.comex.observaciones = (datos.observaciones or "").strip()[:2000] or None
    p.comex.resolucion = (datos.resolucion or "").strip()[:200] or None
    if datos.devolver:
        if p.comex.estado in APROBADOS:
            raise ErrorNegocio("An approved sheet cannot be returned; create a new version.", 409, "ficha_aprobada")
        if not p.comex.observaciones:
            raise ErrorNegocio("Write what the supplier has to fix.", 422, "motivo_requerido")
        p.comex.estado = "observado"
    tocar(p)
    registrar(db, user, "producto", p.id, "devuelto" if datos.devolver else "observacion",
              {"observaciones": p.comex.observaciones, "resolucion": p.comex.resolucion})
    return detalle(db, user, p.id)


def enviar_revision(db: Session, user: Usuario, ids: list[int]) -> dict:
    """Envía fichas en borrador a revisión: deben estar completas y con partida."""
    exigir(user, "producto.ficha")
    ok, errores = 0, []
    for pid in ids:
        p = ver_producto(db, user, pid)
        nombre = nombre_producto(p)
        if p.comex.estado not in BORRADORES:
            errores.append({"id": p.id, "mensaje": f"{nombre} is {ESTADOS.get(p.comex.estado, p.comex.estado).lower()}."})
            continue
        if not p.comex.ficha_completa or not p.comex.sugerido:
            falta = ", ".join((p.comex.faltan or [])[:4]) or "the HS code"
            errores.append({"id": p.id, "mensaje": f"{nombre}: complete the sheet first ({falta})."})
            continue
        antes = p.comex.estado
        p.comex.estado = "revision"
        tocar(p)
        registrar(db, user, "producto", p.id, "enviado", {"estado": [antes, p.comex.estado]})
        ok += 1
    if len(ids) == 1 and errores:
        raise ErrorNegocio(errores[0]["mensaje"], 422, "no_enviado", errores)
    return {"enviados": ok, "errores": errores}


def retirar_revision(db: Session, user: Usuario, producto_id: int) -> dict:
    """Vuelve a borrador una ficha enviada (para corregirla antes de que la revisen)."""
    exigir(user, "producto.ficha")
    p = ver_producto(db, user, producto_id)
    if p.comex.estado != "revision":
        raise ErrorNegocio("Only a sheet in review can go back to draft.", 409, "estado")
    p.comex.estado = "sugerida" if p.comex.ficha_completa and p.comex.sugerido else "borrador"
    tocar(p)
    registrar(db, user, "producto", p.id, "retirado", {"estado": ["revision", p.comex.estado]})
    return detalle(db, user, p.id)


def nueva_version(db: Session, user: Usuario, producto_id: int, datos) -> dict:
    """Cierra la ficha vigente con su partida y abre una copia para editar."""
    exigir(user, "producto.ficha")
    p = ver_producto(db, user, producto_id)
    verificar_version(p, datos.version, "product")
    desde = datos.desde or date.today()
    inicio = p.comex.vigente_desde or (p.creado_en.date() if p.creado_en else desde)
    if desde <= inicio and p.versiones:
        raise ErrorNegocio("The new version must start after the current one.", 422, "validacion")
    db.add(ProductoVersion(
        producto=p, version=p.comex.version_ficha, desde=inicio, hasta=desde - timedelta(days=1), motivo=(datos.motivo or "")[:300] or None,
        # Autosuficiente para auditoría: ficha, clasificación, versión arancelaria,
        # evidencia (reglas con su foto, hechos, notas, overrides) y países con su línea
        datos={"tipo": p.comex.tipo, "ficha": p.comex.ficha, "nombre": p.nombre, "codigo": p.comex.codigo, "sac_codigo": p.comex.sac_codigo, "sugerido": p.comex.sugerido,
               "sac_sugerido": p.comex.sac_sugerido, "estado": p.comex.estado, "descripcion_aduana": p.comex.descripcion_aduana,
               "descripcion_comercial": p.comex.descripcion_comercial, "pais_origen": p.comex.pais_origen, "pais_procedencia": p.comex.pais_procedencia,
               "analisis": p.comex.analisis, "confianza": p.comex.confianza, "fuente": p.comex.fuente, "perfil": p.comex.perfil,
               "version_arancel": ({"id": p.comex.version_arancel_id, **((p.comex.evidencia or {}).get("version") or {})} if p.comex.version_arancel_id else None),
               "evidencia": p.comex.evidencia, "observaciones": p.comex.observaciones, "resolucion": p.comex.resolucion,
               "partidas": {x.pais: {"codigo": x.codigo, "dai": x.dai, "estado": x.estado, "fuente": x.fuente, "manual": x.manual,
                                     "sugerido": x.sugerido, "motivo": x.motivo, "inciso_id": x.inciso_id, "version_id": x.version_id,
                                     "evidencia": x.evidencia, "aprobado_en": x.aprobado_en.isoformat() if x.aprobado_en else None}
                            for x in p.partidas},
               "revisado_por": p.comex.revisado_por.nombre if p.comex.revisado_por else None,
               "revisado_en": p.comex.revisado_en.isoformat() if p.comex.revisado_en else None},
        cerrado_por=user.id))
    p.comex.version_ficha += 1
    p.comex.vigente_desde = desde
    p.comex.estado = "borrador"
    p.comex.codigo = None
    p.comex.revisado_por_id = None
    p.comex.revisado_en = None
    p.partidas.clear()
    tocar(p)
    registrar(db, user, "producto", p.id, "nueva_version",
              {"version": p.comex.version_ficha, "desde": desde.isoformat()}, motivo=datos.motivo)
    return detalle(db, user, p.id)


def guardar_opinion(db: Session, user: Usuario, producto_id: int, opinion: dict) -> None:
    p = ver_producto(db, user, producto_id)
    p.comex.opinion_ia = opinion
