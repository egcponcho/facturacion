"""Cajas de una lista de empaque: empacar con plantillas o según la receta de cada
línea (con vista previa), crear, editar y eliminar cajas, y guardar una caja como
plantilla.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errores import ErrorNegocio
from app.modelos import (
    GrupoCajas,
    GrupoCajasItem,
    PackingList,
    PlantillaCaja,
    PLLinea,
    TipoEmpaque,
    Usuario,
)
from app.modulos.acceso.permisos import exigir
from app.modulos.comun.historial import registrar, tocar
from app.modulos.empaque import empaques
from app.modulos.empaque.packing import (
    CAMPOS_VALOR,
    _editable,
    _linea,
    _nodo,
    _plantilla,
    _ref,
    _tipo,
    bultos_propios,
    cargar_pl,
    escalar,
    limpiar_vacios,
    quitar_nodo,
    regla_empaque,
    rehacer,
)
from app.modulos.facturacion.cantidades import (
    cubierto,
    inner_de,
    sin_caja,
)
from app.modulos.maestros.unidades import error_cantidad


# ---- Plantillas y cajas -----------------------------------------------------
def _valores_plantilla(t: PlantillaCaja, cantidad: int | None = None) -> dict:
    """Medidas y tara de la plantilla. El peso no se copia: el neto sale del
    peso de cada artículo y el bruto le suma la tara de cada nivel."""
    return {"largo": t.largo, "ancho": t.ancho, "alto": t.alto, "tara": t.tara}


def _propuesta(db: Session, pl: PackingList, filas, reemplazar: bool) -> list[dict]:
    """Qué cajas saldrían de cada fila. Con casepack o prepack la cantidad por
    caja la da el artículo; la plantilla solo aporta medidas y pesos."""
    plantillas: dict[int, PlantillaCaja] = {}
    vistas = set()
    res = []
    for fila in filas:
        pll = _linea(pl, fila.pl_linea_id)
        if pll.id in vistas:
            raise ErrorNegocio("A row appears twice in the packing.", 422, "validacion")
        vistas.add(pll.id)
        t = None
        if fila.plantilla_id:
            if fila.plantilla_id not in plantillas:
                plantillas[fila.plantilla_id] = _plantilla(db, pl, fila.plantilla_id)
            t = plantillas[fila.plantilla_id]
        fl = pll.factura_linea
        regla, por_caja = regla_empaque(fl)
        unidad = fl.unidad
        if reemplazar:
            # Lo que está en cajas de una sola fila se volvería a empacar
            propio = sum(n * b.num_cajas for b in bultos_propios(pl, pll) for _, n in empaques.contenido(pl, b))
            libre = sin_caja(pll) + propio
        else:
            libre = sin_caja(pll)
        f = {"pl_linea_id": pll.id, "ref": _ref(pll), "unidad": unidad, "sin_caja": libre, "regla": regla,
             "plantilla_id": t.id if t else None, "plantilla": t.nombre if t else None}
        if regla == "LIBRE":
            por_caja = t.cantidad_por_caja if t else None
        f["cantidad_por_caja"] = por_caja
        if regla == "LIBRE" and not t:
            f["omitida"] = "Choose a template: the PO line has no casepack."
        elif regla == "LIBRE" and unidad != t.unidad:
            f["omitida"] = "The unit does not match the template."
        elif regla == "LIBRE" and inner_de(fl) and por_caja % inner_de(fl):
            f["omitida"] = (f"The template holds {por_caja} per carton, which is not a whole number of inner packs "
                            f"of {inner_de(fl)}. Choose a template that is a multiple of {inner_de(fl)}.")
        elif t and not t.activa:
            f["omitida"] = "The template is inactive."
        elif libre == 0:
            f["omitida"] = "It is already packed."
        else:
            f["cajas"] = libre // por_caja
            f["empacado"] = f["cajas"] * por_caja
            f["sobrante"] = libre % por_caja
        res.append(f)
    return res


def _resumen_propuesta(filas: list[dict]) -> dict:
    validas = [f for f in filas if "omitida" not in f]
    return {
        "filas": len(validas),
        "cajas_completas": sum(f["cajas"] for f in validas),
        "empacado": sum(f["empacado"] for f in validas),
        "filas_con_sobrante": sum(1 for f in validas if f["sobrante"]),
        "sobrante_total": sum(f["sobrante"] for f in validas),
        "omitidas": len(filas) - len(validas),
    }


def empaque_previa(db: Session, user: Usuario, pl_id: int, datos) -> dict:
    pl = cargar_pl(db, user, pl_id)
    filas = _propuesta(db, pl, datos.filas, datos.reemplazar)
    return {"filas": filas, "resumen": _resumen_propuesta(filas), "version": pl.version}


def _desempacar_propio(pl: PackingList, pll: PLLinea) -> None:
    for b in bultos_propios(pl, pll):
        quitar_nodo(pl, b)
    limpiar_vacios(pl)


def aplicar_empaque(db: Session, user: Usuario, pl_id: int, datos) -> dict:
    """Crea las cajas completas de cada fila con su plantilla. El sobrante que no
    completa una caja queda en una caja parcial (peso estimado) o sin caja."""
    pl = _editable(db, user, pl_id, datos.version)
    if datos.reemplazar:
        for fila in datos.filas:
            _desempacar_propio(pl, _linea(pl, fila.pl_linea_id))
        db.flush()
        for pll in pl.lineas:
            db.expire(pll, ["items"])
    filas = _propuesta(db, pl, datos.filas, False)
    resumen = _resumen_propuesta(filas)
    if not resumen["filas"]:
        raise ErrorNegocio("There is nothing to pack with those templates.", 422, "sin_pendiente",
                           [{"mensaje": f"{f['ref']}: {f['omitida']}"} for f in filas])
    for f in filas:
        if "omitida" in f:
            continue
        pll = _linea(pl, f["pl_linea_id"])
        t = db.get(PlantillaCaja, f["plantilla_id"]) if f["plantilla_id"] else None
        por_caja = f["cantidad_por_caja"]
        if f["cajas"]:
            _nodo(db, pl, f["cajas"], [(pll, por_caja)], t)
        if f["sobrante"] and datos.sobrante == "caja_parcial":
            g = _nodo(db, pl, 1, [(pll, f["sobrante"])], t, es_parcial=True)
            if f["regla"] == "CASEPACK":
                g.observacion = f"Partial carton: {f['sobrante']} of {por_caja} of the casepack."
    rehacer(db, pl)
    tocar(pl)
    registrar(db, user, "packing_list", pl.id, "aplicar_plantilla",
              {"plantillas": sorted({f["plantilla"] or "casepack" for f in filas if "omitida" not in f}),
               "sobrante": datos.sobrante, **resumen}, factura_id=pl.factura_id)
    return {"resumen": resumen, "version": pl.version}


# ---- Empacar según la receta ------------------------------------------------
# Cada fila se empaca con los niveles de su receta (la foto que trae la línea de
# factura desde la OC): N unidades completas del nivel más externo con todo lo
# de adentro y, con lo que sobra, una unidad parcial que lleva lo que cabe en
# los niveles de abajo. Así un pallet de 40 cajas de 2 inners de 12 se arma en
# un paso, y el resto queda en un pallet parcial con sus cajas y, si hace
# falta, una caja o un inner parcial (o sin caja, según `sobrante`).
def _niveles_receta(fl, con_opcionales: bool) -> list[dict]:
    niveles = (fl.receta_foto or {}).get("niveles") or []
    niveles = [n for n in niveles if con_opcionales or not n.get("opcional")]
    unidades, res = 1, []
    for n in niveles:  # unidades acumuladas de los niveles que quedan
        unidades *= n["cantidad"]
        res.append({**n, "unidades": unidades})
    return res


def _armar_receta(niveles: list[dict], cantidad: int, crear, padre=None, sobrante: str = "caja_parcial") -> int:
    """Arma `cantidad` unidades del artículo con los niveles (del más interno al
    más externo) llamando a `crear(nivel, num, padre, por_unidad, parcial)`.
    Devuelve lo que queda sin empacar."""
    externo = niveles[-1]
    completos, resto = divmod(cantidad, externo["unidades"])
    if completos:
        nodo, num = padre, completos
        for i in range(len(niveles) - 1, -1, -1):
            if i < len(niveles) - 1:
                num *= niveles[i + 1]["cantidad"]
            nodo = crear(niveles[i], num, nodo, niveles[i]["cantidad"] if i == 0 else None, False)
    if not resto:
        return 0
    if len(niveles) == 1:
        if sobrante != "caja_parcial":
            return resto
        crear(externo, 1, padre, resto, True)
        return 0
    parcial = crear(externo, 1, padre, None, True)
    return _armar_receta(niveles[:-1], resto, crear, parcial, sobrante)


def _contar_receta(niveles: list[dict], cantidad: int, sobrante: str) -> tuple[list[dict], int]:
    """Cuántas unidades de cada nivel saldrían (completas y parciales), sin guardar."""
    nodos: list[dict] = []

    def crear(nivel, num, padre, por_unidad, parcial):
        n = {"nivel": nivel, "num": num, "padre": padre, "items": por_unidad, "parcial": parcial}
        nodos.append(n)
        return n

    queda = _armar_receta(niveles, cantidad, crear, None, sobrante)
    vivos = [n for n in nodos if n["items"] is not None]  # sin los parciales que quedaron vacíos
    con_algo = {id(x) for n in vivos for x in _cadena(n)}
    cuenta: dict[int, dict] = {}
    for n in nodos:
        if id(n) not in con_algo:
            continue
        c = cuenta.setdefault(n["nivel"]["orden"], {"orden": n["nivel"]["orden"], "nombre": n["nivel"]["nombre"],
                                                    "completas": 0, "parciales": 0})
        c["parciales" if n["parcial"] else "completas"] += n["num"]
    return sorted(cuenta.values(), key=lambda x: -x["orden"]), queda


def _cadena(n: dict) -> list[dict]:
    res = []
    while n is not None:
        res.append(n)
        n = n["padre"]
    return res


def _filas_receta(pl: PackingList, datos) -> list[PLLinea]:
    if datos.pl_linea_ids:
        return [_linea(pl, i) for i in dict.fromkeys(datos.pl_linea_ids)]
    return [pll for pll in pl.lineas if pll.factura_linea.receta_foto]


def _previa_receta(pl: PackingList, datos, sobrante: str = "caja_parcial") -> list[dict]:
    res = []
    for pll in _filas_receta(pl, datos):
        fl = pll.factura_linea
        niveles = _niveles_receta(fl, datos.con_opcionales)
        libre = sin_caja(pll)
        if datos.reemplazar:
            libre += sum(n * b.num_cajas for b in bultos_propios(pl, pll) for _, n in empaques.contenido(pl, b))
        f = {"pl_linea_id": pll.id, "ref": _ref(pll), "unidad": fl.unidad, "sin_caja": libre,
             "receta": (fl.receta_foto or {}).get("nombre"), "niveles": [], "queda": 0}
        if not niveles:
            f["omitida"] = "The PO line has no packing recipe."
        elif libre == 0:
            f["omitida"] = "It is already packed."
        elif libre != int(libre):
            f["omitida"] = "A recipe packs whole units; this row has a fraction."
        else:
            f["niveles"], f["queda"] = _contar_receta(niveles, int(libre), sobrante)
        res.append(f)
    return res


def empaque_receta_previa(db: Session, user: Usuario, pl_id: int, datos) -> dict:
    """Qué armaría «Empacar según la receta» en cada fila; no guarda."""
    pl = cargar_pl(db, user, pl_id)
    filas = _previa_receta(pl, datos)
    return {"filas": filas, "version": pl.version, "por_tipo": _total_niveles(filas)}


def _total_niveles(filas: list[dict]) -> list[dict]:
    total: dict[str, dict] = {}
    for f in filas:
        for n in f["niveles"]:
            t = total.setdefault(n["nombre"], {"nombre": n["nombre"], "completas": 0, "parciales": 0})
            t["completas"] += n["completas"]
            t["parciales"] += n["parciales"]
    return list(total.values())


def aplicar_empaque_receta(db: Session, user: Usuario, pl_id: int, datos) -> dict:
    """Arma en un paso el árbol completo de cada fila según su receta."""
    pl = _editable(db, user, pl_id, datos.version)
    if datos.reemplazar:
        for pll in _filas_receta(pl, datos):
            if pll.factura_linea.receta_foto:
                _desempacar_propio(pl, pll)
        db.flush()
        for pll in pl.lineas:
            db.expire(pll, ["items"])
    filas = [f for f in _previa_receta(pl, datos.model_copy(update={"reemplazar": False}), datos.sobrante)
             if "omitida" not in f]
    if not filas:
        raise ErrorNegocio("There is nothing to pack with a recipe.", 422, "sin_pendiente")
    tipos = {t.id: t for t in db.scalars(select(TipoEmpaque))}
    for f in filas:
        pll = _linea(pl, f["pl_linea_id"])

        def crear(nivel, num, padre, por_unidad, parcial, pll=pll):
            t = tipos.get(nivel["tipo_empaque_id"])
            g = GrupoCajas(num_cajas=num, tipo_empaque=t, padre=padre, es_parcial=parcial,
                           largo=nivel.get("largo"), ancho=nivel.get("ancho"),
                           # El alto de un soporte armado (pallet con su carga) se mide
                           alto=None if nivel.get("cuenta_como") == "SOPORTE" else nivel.get("alto"),
                           tara=nivel.get("tara"))
            if por_unidad is not None:
                g.items.append(GrupoCajasItem(pl_linea=pll, cantidad_por_caja=por_unidad))
            pl.grupos.append(g)
            return g

        _armar_receta(_niveles_receta(pll.factura_linea, datos.con_opcionales), int(f["sin_caja"]), crear, None,
                      datos.sobrante)
    limpiar_vacios(pl)
    rehacer(db, pl)
    tocar(pl)
    total = _total_niveles(filas)
    registrar(db, user, "packing_list", pl.id, "empacar_receta",
              {"filas": len(filas), "niveles": total, "sobrante": datos.sobrante}, factura_id=pl.factura_id)
    return {"filas": len(filas), "por_tipo": total, "version": pl.version}


def crear_caja(db: Session, user: Usuario, pl_id: int, datos) -> dict:
    pl = _editable(db, user, pl_id, datos.version)
    t = _plantilla(db, pl, datos.plantilla_id) if datos.plantilla_id else None
    vistos = set()
    errores = []
    unidades = set()
    for item in datos.items:
        pll = _linea(pl, item.pl_linea_id)
        if pll.id in vistos:
            raise ErrorNegocio("A row appears twice in the carton.", 422, "validacion")
        vistos.add(pll.id)
        unidades.add(pll.factura_linea.unidad)
        if (msg := error_cantidad(item.cantidad_por_caja, pll.factura_linea.unidad)):
            errores.append({"pl_linea_id": pll.id, "mensaje": f"{_ref(pll)}: {msg}"})
            continue
        necesario = item.cantidad_por_caja * datos.num_cajas
        if necesario > sin_caja(pll):
            errores.append({"pl_linea_id": pll.id, "mensaje":
                f"{_ref(pll)}: you need {necesario} and only {sin_caja(pll)} are not in cartons."})
    if errores:
        raise ErrorNegocio("The carton does not fit in what is pending.", 422, "validacion", errores)
    errores = _reglas_caja(pl, datos.items, datos.num_cajas)
    if errores:
        raise ErrorNegocio("The carton does not follow the packing rules.", 422, "regla_empaque", errores)
    por_caja = sum(i.cantidad_por_caja for i in datos.items)
    explicitos = datos.model_dump(exclude_unset=True)
    tipo = _tipo(db, explicitos.get("tipo_empaque_id"), t)
    g = _nodo(db, pl, datos.num_cajas, [(_linea(pl, i.pl_linea_id), i.cantidad_por_caja) for i in datos.items], t, tipo,
              es_parcial=bool(t) and por_caja < t.cantidad_por_caja, observacion=explicitos.get("observacion"))
    for c in CAMPOS_VALOR:
        if c in explicitos:
            setattr(g, c, explicitos[c])
    if explicitos.get("peso_neto_caja") is not None:
        g.neto_manual = explicitos["peso_neto_caja"]
    rehacer(db, pl)
    tocar(pl)
    registrar(db, user, "packing_list", pl.id, "crear_caja",
              {"cajas": datos.num_cajas, "mixta": len(datos.items) > 1}, factura_id=pl.factura_id)
    return {"version": pl.version}


def _reglas_caja(pl: PackingList, items, num_cajas: int) -> list[dict]:
    lineas = [(_linea(pl, i.pl_linea_id), i.cantidad_por_caja) for i in items]
    errores = []
    destinos = {pll.factura_linea.centro_destino for pll, _ in lineas}
    if len(destinos) > 1:
        errores.append({"mensaje": "A carton cannot mix goods for different destination countries ("
                        + ", ".join(sorted(d or "no destination" for d in destinos)) + ")."})
    for pll, cant in lineas:
        regla, por_caja = regla_empaque(pll.factura_linea)
        ref = _ref(pll)
        n = inner_de(pll.factura_linea)
        if n and cant % n:
            errores.append({"mensaje": f"{ref}: each carton carries whole inner packs of {n}; {cant} per carton "
                            f"is not a multiple of {n}."})
            continue
        if regla == "LIBRE":
            continue
        if len(lineas) > 1:
            errores.append({"mensaje": f"{ref}: {'a pack or kit' if regla == 'PREPACK' else 'an item with casepack'} "
                            "goes alone in its carton; it is not mixed with other items."})
            continue
        if regla == "PREPACK" and cant != 1:
            errores.append({"mensaje": f"{ref}: each master carton carries exactly one pack "
                                       f"{pll.factura_linea.codigo_pack or pll.factura_linea.codigo_articulo}."})
        if regla == "CASEPACK" and cant != por_caja:
            resto = sin_caja(pll)
            if not (num_cajas == 1 and cant == resto and cant < por_caja):
                errores.append({"mensaje": f"{ref}: the casepack is {por_caja}; it cannot be increased or reduced. "
                                "Only the final remainder may go in a partial carton."})
    return errores


def editar_cajas(db: Session, user: Usuario, pl_id: int, datos) -> dict:
    pl = _editable(db, user, pl_id, datos.version)
    grupos = {g.id: g for g in pl.grupos}
    seleccion = []
    for gid in datos.grupo_ids:
        if gid not in grupos:
            raise ErrorNegocio("One of the cartons is no longer in the packing list. Reload.", 404, "no_encontrado")
        seleccion.append(grupos[gid])
    campos = datos.model_dump(exclude_unset=True)
    t = _plantilla(db, pl, datos.desde_plantilla_id) if datos.desde_plantilla_id else None
    errores = []
    tipo = _tipo(db, campos["tipo_empaque_id"]) if campos.get("tipo_empaque_id") else None
    for g in seleccion:
        if t:
            for c, v in _valores_plantilla(t).items():
                setattr(g, c, v)
            g.plantilla_id, g.plantilla_nombre = t.id, t.nombre
            if t.tipo_empaque:
                g.tipo_empaque = t.tipo_empaque
        if tipo:
            g.tipo_empaque = tipo
            for c in ("largo", "ancho", "alto", "tara"):
                if getattr(tipo, c) is not None and c not in campos:
                    setattr(g, c, getattr(tipo, c))
        for c in CAMPOS_VALOR:
            if c in campos:
                setattr(g, c, campos[c])
        if "peso_neto_caja" in campos:
            # Neto escrito a mano: solo cuenta si falta el peso de algún artículo
            g.neto_manual = campos["peso_neto_caja"]
            g.peso_estimado = False
        if "observacion" in campos:
            g.observacion = (campos["observacion"] or "").strip() or None
        if datos.num_cajas and datos.num_cajas != g.num_cajas:
            for pll, n in empaques.contenido(pl, g):
                otros = cubierto(pll) - n * g.num_cajas
                if otros + n * datos.num_cajas > pll.cantidad:
                    errores.append({"grupo_id": g.id, "mensaje":
                        f"{_ref(pll)}: not enough quantity for {datos.num_cajas} cartons."})
            if any(d.num_cajas * datos.num_cajas % g.num_cajas for d in empaques.descendientes(pl, g)):
                errores.append({"grupo_id": g.id, "mensaje": "What it carries inside cannot be split evenly "
                                f"into {datos.num_cajas} units."})
            else:
                escalar(pl, g, datos.num_cajas)
    rehacer(db, pl)
    if datos.confirmar_pesos:
        for g in seleccion:
            if g.peso_neto_caja is None:
                errores.append({"grupo_id": g.id, "mensaje": "Some cartons have no weight; enter it before confirming."})
            g.peso_estimado = False
    if errores:
        raise ErrorNegocio("Some cartons could not be updated.", 422, "validacion", errores)
    tocar(pl)
    registrar(db, user, "packing_list", pl.id, "editar_cajas",
              {"grupos": len(seleccion), "campos": [k for k in campos if k not in ("version", "grupo_ids")]},
              factura_id=pl.factura_id)
    return {"version": pl.version}


def eliminar_cajas(db: Session, user: Usuario, pl_id: int, datos) -> dict:
    pl = _editable(db, user, pl_id, datos.version)
    grupos = {g.id: g for g in pl.grupos}
    total = 0
    afectadas = set()
    for gid in datos.grupo_ids:
        g = grupos.get(gid)
        if not g:
            raise ErrorNegocio("One of the cartons is no longer in the packing list. Reload.", 404, "no_encontrado")
        if g not in pl.grupos:
            continue  # ya salió con su contenedor
        total += g.num_cajas
        afectadas.update(pll for pll, _ in empaques.contenido(pl, g))
        quitar_nodo(pl, g)
    limpiar_vacios(pl)
    db.flush()
    for pll in afectadas:
        db.expire(pll, ["items"])
    rehacer(db, pl)
    tocar(pl)
    registrar(db, user, "packing_list", pl.id, "desempacar", {"cajas": total}, factura_id=pl.factura_id)
    return {"version": pl.version}


def guardar_como_plantilla(db: Session, user: Usuario, pl_id: int, grupo_id: int, nombre: str) -> dict:
    exigir(user, "plantilla.editar")
    pl = cargar_pl(db, user, pl_id)
    g = next((x for x in pl.grupos if x.id == grupo_id), None)
    if not g:
        raise ErrorNegocio("The carton does not exist.", 404, "no_encontrado")
    cont = empaques.contenido(pl, g)
    if len(cont) != 1:
        raise ErrorNegocio("Only a single-product carton can be saved as a template.", 422, "validacion")
    nombre = nombre.strip()
    existe = db.scalar(select(PlantillaCaja.id).where(
        PlantillaCaja.proveedor_id == pl.factura.proveedor_id, PlantillaCaja.nombre == nombre))
    if existe:
        raise ErrorNegocio(f"A template named “{nombre}” already exists.", 409, "duplicado")
    pll, n = cont[0]
    t = PlantillaCaja(
        proveedor_id=pl.factura.proveedor_id, nombre=nombre, cantidad_por_caja=int(n),
        unidad=pll.factura_linea.unidad, largo=g.largo, ancho=g.ancho, alto=g.alto,
        tara=g.tara, tipo_empaque=g.tipo_empaque, activa=True,
    )
    db.add(t)
    db.flush()
    registrar(db, user, "plantilla_caja", t.id, "crear", {"nombre": t.nombre, "desde_pl": pl_id})
    return {"id": t.id, "nombre": t.nombre}
