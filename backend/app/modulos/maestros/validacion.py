"""Validación de lo que se guarda en un catálogo de datos maestros: cada campo según
su tipo, las dependencias entre campos y las reglas propias de artículos,
atributos y reglas de lead time.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.campos_propios import limpiar as limpiar_propios
from app.core.errores import ErrorNegocio
from app.modelos import (
    Almacen,
    Articulo,
    ArticuloAtributo,
    ArticuloComponente,
    Atributo,
    Centro,
    Contacto,
    EscalaValores,
    EstadoLiberacion,
    OrdenCompra,
    PasoLeadTime,
    PosicionOC,
    Producto,
    ProductoAtributo,
    Proveedor,
    ReglaLeadTime,
    ValorLista,
)
from app.modulos.comun.normalizar import Referencias
from app.modulos.comun.normalizar import nombre as nombre_fmt
from app.modulos.comun.normalizar import texto as texto_fmt
from app.modulos.maestros import atributos as atr_svc
from app.modulos.maestros import unidades
from app.modulos.maestros.catalogos import es_obligatorio, opciones_campo, tipo_de
from app.modulos.maestros.definiciones import CATALOGOS, CORREO
from app.modulos.productos.productos import (
    generico_de,
)
from app.modulos.transporte import reglas_lt as rlt


def _valor_dato(db: Session, catalogo: str, valor, clave: str):
    """Dato `clave` de la opción elegida (id o código) de un catálogo."""
    modelo = CATALOGOS[catalogo]["modelo"]
    obj = db.get(modelo, valor) if isinstance(valor, int) else db.scalar(select(modelo).where(modelo.codigo == valor))
    if not obj:
        return None
    if hasattr(obj, clave):
        v = getattr(obj, clave)
        return [y.id for y in v] if isinstance(v, list) else v
    # Relación inversa: qué registros de `clave` (otro catálogo) incluyen esta opción
    for x in CATALOGOS.get(clave, {}).get("campos", []):
        if x["tipo"] == "multi" and x.get("catalogo") == catalogo:
            m = CATALOGOS[clave]["modelo"]
            return [o.id for o in db.scalars(select(m)).all() if obj in getattr(o, x["nombre"])]
    return None


def _dependencias(db: Session, cat: dict, final: dict) -> list[dict]:
    """Valida los campos dependientes declarados en el catálogo."""
    errores = []
    for x in cat["campos"]:
        dep = x.get("depende")
        v, base = final.get(x["nombre"]), final.get((dep or {}).get("campo"))
        if not dep or v in (None, "", []) or base in (None, ""):
            continue
        for elegido in (v if isinstance(v, list) else [v]):
            ident = elegido.id if hasattr(elegido, "id") else elegido
            dato = _valor_dato(db, x["catalogo"], ident, dep["clave"])
            ok = (base in dato) if isinstance(dato, list) else (dato == base)
            if not ok:
                nombre_base = next((y["etiqueta"] for y in cat["campos"] if y["nombre"] == dep["campo"]), dep["campo"])
                errores.append({"campo": x["nombre"], "mensaje":
                                f"{x['etiqueta']}: the option chosen does not belong to the selected {nombre_base.lower()}."})
                break
    return errores


def limpiar_datos(db: Session, cat: dict, datos: dict, parcial: bool, actual=None) -> dict:
    import re

    errores = []
    limpio = {}
    for campo in cat["campos"]:
        n = campo["nombre"]
        if campo.get("solo_lectura"):
            continue
        obligatorio = es_obligatorio(cat, campo)
        if n not in datos:
            if not parcial and obligatorio:
                errores.append({"campo": n, "mensaje": f"{campo['etiqueta']} is required."})
            continue
        v = datos[n]
        if campo["tipo"] == "regla_lt":
            regla, errs = rlt.validar(db, v)
            if errs:
                errores.extend({"campo": n, "mensaje": e} for e in errs)
            else:
                limpio[n] = regla
            continue
        if isinstance(v, str):
            v = nombre_fmt(v) if campo.get("formato") == "nombre" else texto_fmt(v)
            if campo.get("mayus"):
                v = v.upper()
        if v in ("", None) or (campo["tipo"] == "multi" and v == [] and not obligatorio):
            if campo["tipo"] == "multi":
                if obligatorio:
                    errores.append({"campo": n, "mensaje": f"{campo['etiqueta']}: choose at least one."})
                else:
                    limpio[n] = []
                continue
            v = None
        if v is None:
            if obligatorio:
                errores.append({"campo": n, "mensaje": f"{campo['etiqueta']} is required."})
            limpio[n] = False if campo["tipo"] == "bool" else None
            continue
        t = campo["tipo"]
        try:
            if t == "entero":
                v = int(v)
                if campo.get("minimo") is not None and v < campo["minimo"]:
                    raise ValueError
            elif t == "numero":
                v = float(v)
                if campo.get("minimo") is not None and v < campo["minimo"]:
                    raise ValueError
            elif t == "fecha":
                from datetime import date as _fecha

                v = v if isinstance(v, _fecha) else _fecha.fromisoformat(str(v)[:10])
            elif t == "bool":
                v = v if isinstance(v, bool) else str(v).lower() in ("1", "true", "si", "sí")
            elif t == "ref":
                v = int(v)
                if not db.get(CATALOGOS[campo["catalogo"]]["modelo"], v):
                    raise ValueError
            elif t == "codigo":
                # El código o el nombre, escrito de cualquier forma, se enlaza con el registro
                modelo = CATALOGOS[campo["catalogo"]]["modelo"]
                obj = db.scalar(select(modelo).where(modelo.codigo == str(v).upper())) or \
                    Referencias(db, modelo).buscar(v)
                if not obj:
                    errores.append({"campo": n, "mensaje": f"{campo['etiqueta']}: {v} is not in the catalog."})
                    continue
                v = obj.codigo
            elif t == "opciones":
                elegidas = v if isinstance(v, list) else [x.strip() for x in str(v).split(",") if x.strip()]
                validas = [o[0] for o in opciones_campo(campo)]
                if any(x not in validas for x in elegidas):
                    raise ValueError
                v = ",".join(x for x in validas if x in elegidas) or None
            elif t == "opcion" and v not in [o[0] for o in opciones_campo(campo)] \
                    and not (actual and v == getattr(actual, n)):  # un valor ya guardado que se desactivó
                raise ValueError
            elif t == "multi":
                ids = v if isinstance(v, list) else [x for x in str(v).split(",") if x.strip()]
                modelo = CATALOGOS[campo["catalogo"]]["modelo"]
                objs = list(db.scalars(select(modelo).where(modelo.id.in_([int(x) for x in ids])))) if ids else []
                if len(objs) != len(set(int(x) for x in ids)):
                    raise ValueError
                if obligatorio and not objs:
                    errores.append({"campo": n, "mensaje": f"{campo['etiqueta']}: choose at least one."})
                    continue
                v = objs
            elif t == "correos":
                lista = [x.strip().lower() for x in re.split(r"[,;\s]+", str(v)) if x.strip()]
                malos = [x for x in lista if not re.match(CORREO, x)]
                if malos:
                    errores.append({"campo": n, "mensaje": f"Invalid email: {', '.join(malos)}."})
                    continue
                v = ", ".join(dict.fromkeys(lista))
            else:
                v = str(v)
        except (TypeError, ValueError):
            errores.append({"campo": n, "mensaje": f"{campo['etiqueta']}: invalid value."})
            continue
        if campo.get("max") and isinstance(v, str) and len(v) > campo["max"]:
            errores.append({"campo": n, "mensaje": f"{campo['etiqueta']}: {campo['max']} characters maximum."})
            continue
        if campo.get("patron") and isinstance(v, str) and not re.match(campo["patron"], v):
            errores.append({"campo": n, "mensaje": f"{campo['etiqueta']}: {campo.get('mensaje_patron', 'invalid format')}"})
            continue
        limpio[n] = v

    if cat["modelo"] is Atributo:
        d = {**({k: getattr(actual, k) for k in ("codigo", "nivel", "tipo", "opciones", "catalogo", "unidad", "general",
                                                  "familias")} if actual else {}), **limpio}
        errores += _validar_atributo(db, d, actual)
        if (d.get("tipo") or "texto") != "catalogo":
            limpio["catalogo"] = None
        # Vale en todas las familias o en las elegidas: nunca en ninguna
        if d.get("general"):
            if d.get("familias"):
                limpio["familias"] = []
        elif not d.get("familias"):
            errores.append({"campo": "familias", "mensaje": "Choose the families it applies to, or mark it for all families."})

    # Atributos de variante: uno por atributo, con el tipo de valor de cada uno
    if cat["modelo"] is Articulo:
        crudos = {k[4:]: v for k, v in datos.items() if k.startswith("atr.")}
        if crudos:
            gen = str(datos.get("generico") or "").strip().upper()
            prod = db.scalar(select(Producto).where(Producto.codigo_generico == gen)) if gen else None
            grupo = prod.grupo_producto if prod is not None else actual.familia_efectiva if actual is not None else None
            valores, errs = atr_svc.validar(db, "VARIANTE", crudos, campo="atr", grupo=grupo)
            errores += [{**e, "campo": e["campo"].replace("atr.", "atr.", 1)} for e in errs]
            if not errs:
                limpio["variantes"] = {k: v for k, v in {**(actual.variantes if actual else {}), **valores}.items() if v}

    # Campos propios: se validan con su tipo y se guardan juntos en extra
    propios = {k[6:]: v for k, v in datos.items() if k.startswith("extra.")}
    if hasattr(cat["modelo"], "extra") and (propios or not parcial):
        try:
            limpio["extra"] = limpiar_propios(tipo_de(cat), propios, actual.extra if actual else None, parcial)
        except ErrorNegocio as e:
            errores += e.detalle or []
    final = {**({c["nombre"]: getattr(actual, c["nombre"]) for c in cat["campos"]} if actual else {}), **limpio}
    if cat["modelo"] is PasoLeadTime:
        # Un paso con fecha medida pertenece al documento que la registra
        propio = rlt.DOCUMENTO_HITO.get(final.get("hito") or "")
        if propio and not final.get("documento"):
            limpio["documento"] = final["documento"] = propio
        elif propio and final.get("documento") != propio:
            errores.append({"campo": "documento", "mensaje": "That measured date is recorded on another document: "
                            f"{dict(rlt.DOCUMENTOS)[propio].lower()}."})
    if cat["modelo"] is Articulo:
        errores += _validar_articulo(db, final, limpio, actual)
    if cat["modelo"] is Proveedor and actual and "marcas" in limpio:
        quedan = {m.codigo for m in limpio["marcas"]}
        usadas = set(db.scalars(select(ProductoAtributo.valor).join(Atributo).join(Producto).where(
            Atributo.catalogo == "marcas", Producto.proveedor_id == actual.id).distinct()))
        if usadas - quedan:
            errores.append({"campo": "marcas", "mensaje":
                            f"The supplier has products of {', '.join(sorted(usadas - quedan))}: those brands cannot be removed."})
    if cat["modelo"] is Proveedor and actual and "sociedades" in limpio:
        quedan = {x.codigo for x in limpio["sociedades"]}
        usadas = {c for (c,) in db.execute(select(OrdenCompra.sociedad).where(
            OrdenCompra.proveedor_id == actual.id, OrdenCompra.sociedad.is_not(None)).distinct())}
        if usadas - quedan:
            errores.append({"campo": "sociedades", "mensaje":
                            f"The supplier has purchase orders with {', '.join(sorted(usadas - quedan))}: "
                            "those companies cannot be removed."})
    if cat["modelo"] is ReglaLeadTime:
        errores += _validar_regla_lt(db, final, actual, limpio)
    if cat["modelo"] is EstadoLiberacion:
        otros = [x for x in db.scalars(select(EstadoLiberacion).where(EstadoLiberacion.tipo == final.get("tipo")))
                 if not actual or x.id != actual.id]
        if final.get("predeterminado") and any(x.predeterminado for x in otros):
            errores.append({"campo": "predeterminado", "mensaje": "There is already a default status for this release."})
        if final.get("con_cambios") and (final.get("tipo") != "LOGISTICA" or not final.get("libera")):
            errores.append({"campo": "con_cambios", "mensaje": "Only a released logistics status can be the one with later changes."})
        if final.get("con_cambios") and any(x.con_cambios for x in otros):
            errores.append({"campo": "con_cambios", "mensaje": "There is already a status for released POs with later changes."})
        if actual and "codigo" in limpio and limpio["codigo"] != actual.codigo:
            col = OrdenCompra.liberacion_comercial if actual.tipo == "COMERCIAL" else OrdenCompra.liberacion_logistica
            if db.scalar(select(OrdenCompra.id).where(col == actual.codigo).limit(1)):
                errores.append({"campo": "codigo", "mensaje": "Purchase orders use this code: it cannot change."})
    if cat["modelo"] is ValorLista or cat.get("lista"):
        from app.modulos.maestros.listas import validar as validar_valor

        errores += validar_valor(db, final, actual, limpio, cat.get("lista"))
    if cat["modelo"] is EscalaValores:
        from app.modulos.maestros.escalas import validar as validar_escala

        if final.get("valores"):
            errores += [{"campo": "valores", "mensaje": m} for m in validar_escala(final["valores"])]
        if final.get("regla") == "MULTIPLICAR" and not final.get("factor"):
            errores.append({"campo": "factor", "mensaje": "Enter the factor for the rule Value × factor."})
        if final.get("atributo") and not db.scalar(select(Atributo.id).where(Atributo.codigo == final["atributo"],
                                                                            Atributo.nivel == "VARIANTE")):
            errores.append({"campo": "atributo", "mensaje": "Choose a variant attribute."})
    if cat["modelo"] is Contacto and not final.get("sociedad_id") and not final.get("centro_id"):
        errores.append({"campo": "sociedad_id", "mensaje": "Enter the contact's company or plant."})
    if cat["modelo"] in (Centro, Almacen) and actual and "sociedad_id" in limpio and limpio["sociedad_id"] != actual.sociedad_id:
        campo_oc = OrdenCompra.centro_destino if cat["modelo"] is Centro else None
        en_uso = db.scalar(select(OrdenCompra.id).where(
            (OrdenCompra.centro == actual.codigo) | (campo_oc == actual.codigo) if campo_oc is not None
            else OrdenCompra.id.in_(select(PosicionOC.oc_id).where(PosicionOC.almacen == actual.codigo))).limit(1))
        if en_uso:
            errores.append({"campo": "sociedad_id", "mensaje": "It is used on purchase orders: its company cannot change."})
    ya = {e.get("campo") for e in errores}
    errores += [e for e in _dependencias(db, cat, final) if e["campo"] not in ya]
    if errores:
        raise ErrorNegocio("Check the data.", 422, "validacion", errores)
    return limpio




def _validar_articulo(db: Session, final: dict, limpio: dict, actual: Articulo | None) -> list[dict]:
    """Reglas del artículo en el catálogo: un compuesto (pack o kit) se crea con su contenido
    en su propia acción y ya no cambia lo que lo enlaza; una variante que está en un compuesto
    no cambia su unidad ni sus valores; dos variantes de un producto no repiten valores."""
    from app.modulos.maestros.genericos import validar_codigos

    errores = []
    if final.get("tipo") == "PREPACK" and not (actual and actual.tipo == "PREPACK"):
        errores.append({"campo": "tipo", "mensaje": "Packs and kits are created with their own action, with their item "
                                                    "code and contents."})
    elif actual and actual.tipo == "PREPACK":
        fijos = [c for c in ("tipo", "unidad", "generico") if c in limpio and limpio[c] != getattr(actual, c)]
        if fijos:
            errores.append({"campo": fijos[0], "mensaje": "A pack or kit and its contents cannot change (product, unit and "
                                                          "type). Create a new one."})
    elif final.get("tipo") == "SOLIDO":
        if actual and db.scalar(select(ArticuloComponente.id).where(ArticuloComponente.componente_id == actual.id).limit(1)):
            if ("unidad" in limpio and limpio["unidad"] != actual.unidad) or \
                    ("variantes" in limpio and limpio["variantes"] != actual.variantes):
                errores.append({"campo": "unidad", "mensaje": "This item is part of a pack or kit: its unit and its "
                                                              "variant values cannot change."})
        if final.get("unidad") in unidades.de_compuestos():
            errores.append({"campo": "unidad", "mensaje": "That unit is only for packs and kits."})
    if actual and "generico" in limpio and limpio["generico"] and limpio["generico"] != actual.generico \
            and db.scalar(select(PosicionOC.id).where(PosicionOC.articulo_id == actual.id).limit(1)):
        errores.append({"campo": "generico", "mensaje": "The item is on purchase orders: its product cannot change."})
    errores += [{"campo": "codigo_barras", "mensaje": m} for m in validar_codigos(db, final.get("codigo_barras"),
                                                                                 final.get("codigo_proveedor"))]
    gen = generico_de(final)
    if gen and final.get("tipo") == "SOLIDO":
        errores += _variante_repetida(db, gen, limpio, actual)
    return errores


def _variante_repetida(db: Session, gen: str, limpio: dict, actual) -> list[dict]:
    """Dos variantes de un mismo producto no pueden tener los mismos valores de variante."""
    valores = {k: str(v) for k, v in (limpio.get("variantes") if "variantes" in limpio
                                      else (actual.variantes if actual else {})).items() if v not in (None, "")}
    if not valores:
        return []
    otras = db.scalars(select(Articulo).join(Producto).where(Producto.codigo_generico == gen, Articulo.tipo == "SOLIDO",
                                                             *([Articulo.id != actual.id] if actual else [])))
    for o in otras:
        if {k: str(v) for k, v in o.variantes.items() if v not in (None, "")} == valores:
            return [{"campo": "sku", "mensaje": f"{o.sku} is already the variant {' · '.join(valores.values())} of product {gen}."}]
    return []


def atributo_en_uso(db: Session, atributo_id: int) -> bool:
    return bool(db.scalar(select(ArticuloAtributo.id).where(ArticuloAtributo.atributo_id == atributo_id).limit(1))
                or db.scalar(select(ProductoAtributo.id).where(ProductoAtributo.atributo_id == atributo_id).limit(1)))


def _validar_atributo(db: Session, d: dict, actual) -> list[dict]:
    """Un atributo de opciones necesita sus opciones; uno de catálogo, su catálogo; la unidad es de
    los números. Uno en uso no cambia su código ni su nivel, y cambia su tipo solo si los valores
    guardados siguen valiendo."""
    tipo = d.get("tipo") or "texto"
    if tipo == "opcion" and not atr_svc.opciones(d):
        return [{"campo": "opciones", "mensaje": "Write the options, separated by commas."}]
    if tipo == "catalogo" and not d.get("catalogo"):
        return [{"campo": "catalogo", "mensaje": "Choose the catalog its values come from."}]
    if d.get("unidad") and tipo != "numero":
        return [{"campo": "unidad", "mensaje": "Only numbers have a unit."}]
    if actual is None or not atributo_en_uso(db, actual.id):
        return []
    if d.get("codigo") != actual.codigo:
        return [{"campo": "codigo", "mensaje": "Products already use this attribute: its code cannot change."}]
    if d.get("nivel") != actual.nivel:
        return [{"campo": "nivel", "mensaje": "Products already use this attribute: its level cannot change."}]
    usados = list(db.scalars(select(ArticuloAtributo.valor).where(ArticuloAtributo.atributo_id == actual.id)
                             .distinct().limit(500))) + \
        list(db.scalars(select(ProductoAtributo.valor).where(ProductoAtributo.atributo_id == actual.id).distinct().limit(500)))
    malos = [v for v in usados if atr_svc.valor(db, d, v)[1]]
    if malos:
        return [{"campo": "tipo" if tipo != "opcion" else "opciones",
                 "mensaje": f"Products already have values that do not fit ({', '.join(malos[:5])}): change them first."}]
    return []


def _validar_regla_lt(db: Session, final: dict, actual, limpio: dict) -> list[dict]:
    """Una regla por ámbito, con su ámbito según el nivel, y la cadena que
    resulta (con lo heredado) debe ser válida."""
    errores = []
    nivel = final.get("nivel")
    campo = rlt.CAMPO_NIVEL.get(nivel)
    for otro in rlt.CAMPO_NIVEL.values():
        if otro != campo:
            final[otro] = limpio[otro] = None
    ambito = final.get(campo) if campo else None
    if campo and not ambito:
        return [{"campo": campo, "mensaje": "Choose the scope of this level."}]
    filtro = [ReglaLeadTime.nivel == nivel] + ([getattr(ReglaLeadTime, campo) == ambito] if campo else [])
    otra = db.scalar(select(ReglaLeadTime.id).where(*filtro, ReglaLeadTime.id != (actual.id if actual else 0)))
    if otra:
        errores.append({"campo": campo or "nivel", "mensaje": "There is already a rule for that scope; edit it."})
    regla = rlt.cargar(final.get("pasos"))
    kw = {campo: ambito} if campo else {}
    res = rlt.efectivo(db, **kw, con_regla=(nivel, ambito, regla))
    errores += [{"campo": "pasos", "mensaje": m} for m in res["errores"]]
    return errores


