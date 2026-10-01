import re

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import (
    Factura,
    FacturaLinea,
    GrupoCajas,
    GrupoCajasItem,
    PackingList,
    Pallet,
    PlantillaCaja,
    PLLinea,
    RecepcionLinea,
    Usuario,
    ahora,
)
from .sugerencias import sugerir_unidades
from .cantidades import (
    asignado_por_linea,
    cbm_caja,
    cubierto,
    fuera_de_inner,
    inner_de,
    limpiar_pallets,
    nombre_factura,
    numeracion,
    sin_caja,
    totales_pl,
)
from .partes import partes
from .common import (
    EDITABLE_PL,
    ESTADO_TXT,
    ErrorNegocio,
    asegurar_proveedor,
    cant_txt,
    es_interno,
    permisos_de,
    exigir,
    registrar,
    requerir_motivo,
    tocar,
    verificar_version,
)
from .facturas import cargar_factura

CAMPOS_VALOR = ("largo", "ancho", "alto", "peso_neto_caja", "peso_bruto_caja")


# ---- Carga ------------------------------------------------------------------
def cargar_pl(db: Session, user: Usuario, pl_id: int) -> PackingList:
    pl = db.get(PackingList, pl_id)
    if not pl:
        raise ErrorNegocio("The packing list does not exist.", 404, "no_encontrado")
    asegurar_proveedor(user, pl.factura.proveedor_id)
    return pl


def _editable(db: Session, user: Usuario, pl_id: int, version: int | None) -> PackingList:
    exigir(user, "pl.editar")
    pl = cargar_pl(db, user, pl_id)
    # Bloquea la factura: serializa todo movimiento de cantidades de sus PL
    cargar_factura(db, user, pl.factura_id, bloquear=True)
    db.refresh(pl)
    if pl.estado not in EDITABLE_PL:
        raise ErrorNegocio(
            f"{pl.numero} is {ESTADO_TXT[pl.estado]} and cannot be edited."
            + (" Reopen it to make changes." if pl.estado == "FINALIZADO" else ""),
            409,
            "no_editable",
        )
    verificar_version(pl, version, "packing list")
    return pl


def _linea(pl: PackingList, pl_linea_id: int) -> PLLinea:
    for pll in pl.lineas:
        if pll.id == pl_linea_id:
            return pll
    raise ErrorNegocio("One of the rows is no longer in the packing list. Reload.", 404, "no_encontrado")


def _ref(pll: PLLinea) -> str:
    fl = pll.factura_linea
    return f"{fl.codigo_sap}{' size ' + fl.talla if fl.talla else ''}"


def regla_empaque(fl) -> tuple[str, int | None]:
    """PREPACK: una curva por caja master, sin agregar ni quitar tallas.
    CASEPACK: cantidad exacta por caja del mismo estilo, color y talla.
    LIBRE: casepack no especificado; se elige la cantidad y se puede consolidar.
    Con inner pack (sólidos), toda cantidad por caja es de inner packs enteros:
    con casepack, la caja lleva casepack / inner packs; sin casepack, la caja
    lleva los inner packs que se definan."""
    if fl.tipo_empaque == "PREPACK":
        return "PREPACK", 1
    if fl.casepack:
        return "CASEPACK", fl.casepack
    return "LIBRE", None


def etiqueta_caja(g) -> dict:
    """Estándar: una sola OC, estilo, color y talla. Consolidada: varias."""
    lineas = [it.pl_linea.factura_linea for it in g.items]
    ocs = sorted({fl.oc_numero for fl in lineas})
    destinos = sorted({fl.centro_destino for fl in lineas if fl.centro_destino})
    return {"tipo": "ESTANDAR" if len(lineas) == 1 else "CONSOLIDADA", "ocs": ocs,
            "centro_destino": destinos[0] if len(destinos) == 1 else None}


def _plantilla(db: Session, pl: PackingList, plantilla_id: int) -> PlantillaCaja:
    t = db.get(PlantillaCaja, plantilla_id)
    if not t or t.proveedor_id != pl.factura.proveedor_id:
        raise ErrorNegocio("The template does not exist for this supplier.", 404, "no_encontrado")
    return t


def _siguiente_numero(pl_existentes: list[PackingList]) -> str:
    return f"PL-{len(pl_existentes) + 1:03d}"


def _saldo_factura(db: Session, factura) -> dict[int, int]:
    asignado = asignado_por_linea(db, [l.id for l in factura.lineas])
    return {l.id: l.cantidad - asignado.get(l.id, 0) for l in factura.lineas}


def _agregar_cantidad(pl: PackingList, factura_linea_id: int, cantidad: int) -> PLLinea:
    """Suma a una fila existente de la misma línea de factura o crea una."""
    for pll in pl.lineas:
        if pll.factura_linea_id == factura_linea_id:
            pll.cantidad += cantidad
            return pll
    nueva = PLLinea(factura_linea_id=factura_linea_id, cantidad=cantidad)
    pl.lineas.append(nueva)
    return nueva


def _nuevo_pl(db: Session, factura) -> PackingList:
    pl = PackingList(factura_id=factura.id, numero=_siguiente_numero(factura.packing_lists),
                     estado="BORRADOR", version=1)
    factura.packing_lists.append(pl)
    db.flush()
    return pl


def _tomar_saldo(db: Session, factura, lineas) -> dict[int, int]:
    saldo = _saldo_factura(db, factura)
    if lineas is None:
        tomar = {lid: s for lid, s in saldo.items() if s > 0}
        if not tomar:
            detalle = [
                {"pl_id": pl.id, "numero": pl.numero, "estado": pl.estado,
                 "cantidad": sum(x.cantidad for x in pl.lineas)}
                for pl in factura.packing_lists if pl.estado != "CANCELADO"
            ]
            raise ErrorNegocio(
                "All the goods on the invoice are already in packing lists. "
                "Open those PLs or move quantities between them.",
                409, "sin_saldo", detalle,
            )
        return tomar
    tomar: dict[int, int] = {}
    for x in lineas:
        tomar[x.factura_linea_id] = tomar.get(x.factura_linea_id, 0) + x.cantidad
    errores = []
    for lid, c in tomar.items():
        if lid not in saldo:
            errores.append({"mensaje": "One of the lines does not belong to the invoice."})
        elif c > saldo[lid]:
            errores.append({"factura_linea_id": lid, "mensaje": f"Only {saldo[lid]} remain unassigned on that line."})
        elif (msg := fuera_de_inner(next(l for l in factura.lineas if l.id == lid), c)):
            errores.append({"factura_linea_id": lid, "mensaje": msg})
    if errores:
        raise ErrorNegocio("The quantity could not be assigned.", 422, "validacion", errores)
    return tomar


# ---- Crear y agregar --------------------------------------------------------
def crear_pl(db: Session, user: Usuario, factura_id: int, lineas=None) -> dict:
    exigir(user, "pl.editar")
    f = cargar_factura(db, user, factura_id, bloquear=True)
    if f.estado == "CANCELADA":
        raise ErrorNegocio("The invoice is cancelled.", 409, "no_editable")
    tomar = _tomar_saldo(db, f, lineas)
    pl = _nuevo_pl(db, f)
    for lid, c in tomar.items():
        pl.lineas.append(PLLinea(factura_linea_id=lid, cantidad=c))
    db.flush()
    registrar(db, user, "packing_list", pl.id, "crear",
              {"filas": len(tomar), "cantidad": sum(tomar.values())}, factura_id=f.id)
    return {"id": pl.id, "numero": pl.numero}


def agregar_pendientes(db: Session, user: Usuario, pl_id: int, version: int, lineas=None) -> dict:
    pl = _editable(db, user, pl_id, version)
    tomar = _tomar_saldo(db, pl.factura, lineas)
    for lid, c in tomar.items():
        _agregar_cantidad(pl, lid, c)
    tocar(pl)
    registrar(db, user, "packing_list", pl.id, "agregar", {"cantidad": sum(tomar.values())}, factura_id=pl.factura_id)
    return {"agregado": sum(tomar.values()), "version": pl.version}


# ---- Mover y quitar ---------------------------------------------------------
def _validar_movimientos(pl: PackingList, movimientos) -> list[tuple[PLLinea, int]]:
    pares = []
    errores = []
    usados: dict[int, int] = {}
    for m in movimientos:
        pll = _linea(pl, m.pl_linea_id)
        usados[pll.id] = usados.get(pll.id, 0) + m.cantidad
        libre = sin_caja(pll)
        if usados[pll.id] > libre:
            errores.append({"pl_linea_id": pll.id, "mensaje":
                f"{_ref(pll)}: only {cant_txt(libre, pll.factura_linea.unidad)} are not in cartons. "
                "Packed goods move with “Move cartons”."})
        if (msg := fuera_de_inner(pll.factura_linea, m.cantidad)):
            errores.append({"pl_linea_id": pll.id, "mensaje": f"{_ref(pll)}: {msg}"})
        pares.append((pll, m.cantidad))
    if errores:
        raise ErrorNegocio("The quantity could not be moved.", 422, "validacion", errores)
    return pares


def _destino(db: Session, origen: PackingList, destino_pl_id: int | None) -> PackingList:
    if destino_pl_id is None:
        return _nuevo_pl(db, origen.factura)
    if destino_pl_id == origen.id:
        raise ErrorNegocio("The destination must be another packing list.", 422, "validacion")
    destino = db.get(PackingList, destino_pl_id)
    if not destino or destino.factura_id != origen.factura_id:
        raise ErrorNegocio("You can only move to another PL of the same invoice.", 422, "validacion")
    if destino.estado not in EDITABLE_PL:
        raise ErrorNegocio(f"{destino.numero} is {ESTADO_TXT[destino.estado]}; reopen it first.", 409, "no_editable")
    return destino


def mover(db: Session, user: Usuario, pl_id: int, datos) -> dict:
    origen = _editable(db, user, pl_id, datos.version)
    pares = _validar_movimientos(origen, datos.movimientos)
    destino = _destino(db, origen, datos.destino_pl_id)
    movido = []
    for pll, cantidad in pares:
        _agregar_cantidad(destino, pll.factura_linea_id, cantidad)
        pll.cantidad -= cantidad
        movido.append({"fila": _ref(pll), "cantidad": cantidad})
        if pll.cantidad == 0:
            origen.lineas.remove(pll)
    tocar(origen)
    tocar(destino)
    registrar(db, user, "packing_list", origen.id, "mover",
              {"destino": destino.numero, "movido": movido}, factura_id=origen.factura_id)
    return {"destino_id": destino.id, "destino_numero": destino.numero, "version": origen.version}


def quitar(db: Session, user: Usuario, pl_id: int, datos) -> dict:
    pl = _editable(db, user, pl_id, datos.version)
    pares = _validar_movimientos(pl, datos.movimientos)
    quitado = []
    for pll, cantidad in pares:
        pll.cantidad -= cantidad
        quitado.append({"fila": _ref(pll), "cantidad": cantidad})
        if pll.cantidad == 0:
            pl.lineas.remove(pll)
    tocar(pl)
    registrar(db, user, "packing_list", pl.id, "quitar", quitado, factura_id=pl.factura_id)
    return {"version": pl.version}


def mover_cajas(db: Session, user: Usuario, pl_id: int, datos) -> dict:
    origen = _editable(db, user, pl_id, datos.version)
    grupos = {g.id: g for g in origen.grupos}
    for mg in datos.grupos:
        g = grupos.get(mg.grupo_id)
        if not g:
            raise ErrorNegocio("One of the cartons is no longer in the packing list. Reload.", 404, "no_encontrado")
        if mg.num_cajas > g.num_cajas:
            raise ErrorNegocio(f"That group only has {g.num_cajas} cartons.", 422, "validacion")
    destino = _destino(db, origen, datos.destino_pl_id)
    total_cajas = 0
    for mg in datos.grupos:
        g = grupos[mg.grupo_id]
        if mg.num_cajas < g.num_cajas:
            g.num_cajas -= mg.num_cajas
            mover_g = _clonar_grupo(g, mg.num_cajas)
            origen.grupos.append(mover_g)
            db.flush()
        else:
            mover_g = g
        for it in list(mover_g.items):
            src = it.pl_linea
            cantidad = it.cantidad_por_caja * mover_g.num_cajas
            src.cantidad -= cantidad
            dest_linea = _agregar_cantidad(destino, src.factura_linea_id, cantidad)
            it.pl_linea = dest_linea
            if src.cantidad == 0:
                origen.lineas.remove(src)
        mover_g.pl = destino
        mover_g.pallet = None
        total_cajas += mover_g.num_cajas
    limpiar_pallets(origen)
    tocar(origen)
    tocar(destino)
    registrar(db, user, "packing_list", origen.id, "mover_cajas",
              {"destino": destino.numero, "cajas": total_cajas}, factura_id=origen.factura_id)
    return {"destino_id": destino.id, "destino_numero": destino.numero, "version": origen.version}


def _clonar_grupo(g: GrupoCajas, num_cajas: int) -> GrupoCajas:
    nuevo = GrupoCajas(
        num_cajas=num_cajas,
        **{c: getattr(g, c) for c in CAMPOS_VALOR},
        plantilla_id=g.plantilla_id,
        plantilla_nombre=g.plantilla_nombre,
        es_parcial=g.es_parcial,
        peso_estimado=g.peso_estimado,
        observacion=g.observacion,
    )
    for it in g.items:
        nuevo.items.append(GrupoCajasItem(pl_linea=it.pl_linea, cantidad_por_caja=it.cantidad_por_caja))
    return nuevo


# ---- Pallets -----------------------------------------------------------------
def resumen_pallets(pl: PackingList) -> list[dict]:
    rangos = numeracion(pl)
    res = []
    for p in sorted(pl.pallets, key=lambda x: x.numero):
        grupos = [g for g in pl.grupos if g.pallet is p]
        cajas = sum(g.num_cajas for g in grupos)
        bruto = sum((g.peso_bruto_caja or 0) * g.num_cajas for g in grupos) + (p.peso_tara or 0)
        res.append({
            "id": p.id, "numero": p.numero, "largo": p.largo, "ancho": p.ancho, "alto": p.alto,
            "peso_tara": p.peso_tara, "cajas": cajas, "peso_bruto": round(bruto, 3),
            "cbm": round(p.largo * p.ancho * p.alto / 1_000_000, 4),
            "rangos": [f"{rangos[g.id][0]}" if rangos[g.id][0] == rangos[g.id][1]
                       else f"{rangos[g.id][0]}–{rangos[g.id][1]}" for g in grupos if g.id in rangos],
        })
    return res


def paletizar(db: Session, user: Usuario, pl_id: int, datos) -> dict:
    """Pone grupos de cajas en un pallet nuevo (con sus medidas) o en uno
    existente. Un grupo va completo a un solo pallet."""
    pl = _editable(db, user, pl_id, datos.version)
    grupos = {g.id: g for g in pl.grupos}
    faltan = [i for i in datos.grupo_ids if i not in grupos]
    if faltan or not datos.grupo_ids:
        raise ErrorNegocio("Choose cartons from this packing list.", 422, "validacion")
    if datos.pallet_id:
        pallet = next((p for p in pl.pallets if p.id == datos.pallet_id), None)
        if not pallet:
            raise ErrorNegocio("The pallet does not exist in this packing list.", 404, "no_encontrado")
    else:
        errores = [{"campo": c, "mensaje": f"Pallet {t} is required and must be greater than zero."}
                   for c, t in (("largo", "length"), ("ancho", "width"), ("alto", "height"))
                   if not getattr(datos, c) or getattr(datos, c) <= 0]
        if errores:
            raise ErrorNegocio("The pallet dimensions are missing.", 422, "validacion", errores)
        pallet = Pallet(numero=len(pl.pallets) + 1, largo=datos.largo, ancho=datos.ancho, alto=datos.alto,
                        peso_tara=datos.peso_tara or 0)
        pl.pallets.append(pallet)
    for i in datos.grupo_ids:
        grupos[i].pallet = pallet
    db.flush()
    limpiar_pallets(pl)
    tocar(pl)
    registrar(db, user, "packing_list", pl.id, "paletizar",
              {"pallet": pallet.numero, "cajas": sum(grupos[i].num_cajas for i in datos.grupo_ids)},
              factura_id=pl.factura_id)
    return {"pallet_id": pallet.id, "numero": pallet.numero, "version": pl.version}


def despaletizar(db: Session, user: Usuario, pl_id: int, datos) -> dict:
    """Saca cajas de su pallet (o vacía un pallet completo)."""
    pl = _editable(db, user, pl_id, datos.version)
    for g in pl.grupos:
        if g.id in datos.grupo_ids or (datos.pallet_id and g.pallet_id == datos.pallet_id):
            g.pallet = None
    db.flush()
    limpiar_pallets(pl)
    tocar(pl)
    registrar(db, user, "packing_list", pl.id, "despaletizar", None, factura_id=pl.factura_id)
    return {"version": pl.version}


def _unidad_componentes(fl) -> str | None:
    """Unidad de los sólidos que forman un prepack (pares o unidades)."""
    art = fl.posicion_oc.articulo if fl.posicion_oc else None
    if not art or not art.prepack or not art.prepack.componentes:
        return None
    return art.prepack.componentes[0].articulo.unidad


def definir_inner(db: Session, user: Usuario, pl_id: int, pl_linea_id: int, datos) -> dict:
    """Inner pack definido al armar el PL: la OC normalmente trae solo el
    casepack (sólidos) o la curva (prepacks); el inner pack se decide aquí."""
    pl = _editable(db, user, pl_id, datos.version)
    pll = next((x for x in pl.lineas if x.id == pl_linea_id), None)
    if not pll:
        raise ErrorNegocio("One of the rows is no longer in the packing list. Reload.", 404, "no_encontrado")
    fl = pll.factura_linea
    n = datos.inner_pack or None
    if fl.tipo_empaque == "PREPACK":
        raise ErrorNegocio("A prepack carton is defined by its size run; it has no inner pack.", 422, "validacion")
    if fl.posicion_oc and fl.posicion_oc.inner_pack:
        raise ErrorNegocio(f"The PO defines the inner pack ({fl.posicion_oc.inner_pack}); it cannot change here.", 422, "validacion")
    partes = db.scalars(select(PLLinea).where(PLLinea.factura_linea_id == fl.id)).all()
    if any(cubierto(x) for x in partes):
        raise ErrorNegocio("Unpack this line first to change its inner pack.", 409, "con_cajas")
    if n:
        if fl.casepack and fl.casepack % n:
            raise ErrorNegocio(f"The casepack ({fl.casepack}) must be a multiple of the inner pack ({n}).", 422, "validacion")
        malas = [x.cantidad for x in partes if x.cantidad % n] + ([fl.cantidad] if fl.cantidad % n else [])
        if malas:
            raise ErrorNegocio(f"The quantity ({malas[0]}) must be a multiple of the inner pack ({n}): "
                               "all inner packs carry the same quantity.", 422, "validacion")
    fl.inner_pack = n
    tocar(pl)
    registrar(db, user, "packing_list", pl.id, "inner_pack", {"linea": fl.codigo_sap, "inner_pack": n})
    return {"version": pl.version}


def renombrar(db: Session, user: Usuario, pl_id: int, datos) -> dict:
    """Número propio del packing list (el del proveedor). Único entre los PL
    vigentes del mismo proveedor."""
    pl = _editable(db, user, pl_id, datos.version)
    numero = re.sub(r"\s+", " ", datos.numero).strip()
    if not numero:
        raise ErrorNegocio("Enter the packing list number.", 422, "validacion")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9\s._\-/#]{0,39}", numero):
        raise ErrorNegocio("Use letters, numbers and . _ - / # (up to 40 characters).", 422, "validacion")
    repetido = db.scalar(select(PackingList.id).join(Factura, Factura.id == PackingList.factura_id).where(
        Factura.proveedor_id == pl.factura.proveedor_id, PackingList.id != pl.id, PackingList.estado != "CANCELADO",
        func.lower(PackingList.numero) == numero.lower()).limit(1))
    if repetido:
        raise ErrorNegocio(f"Packing list {numero} already exists for this supplier.", 409, "duplicado")
    anterior, pl.numero = pl.numero, numero
    tocar(pl)
    registrar(db, user, "packing_list", pl.id, "numero", {"anterior": anterior, "numero": numero}, factura_id=pl.factura_id)
    return {"numero": pl.numero, "version": pl.version}


def editar_pallet(db: Session, user: Usuario, pl_id: int, pallet_id: int, datos) -> dict:
    pl = _editable(db, user, pl_id, datos.version)
    pallet = next((p for p in pl.pallets if p.id == pallet_id), None)
    if not pallet:
        raise ErrorNegocio("The pallet does not exist in this packing list.", 404, "no_encontrado")
    for c in ("largo", "ancho", "alto", "peso_tara"):
        v = getattr(datos, c)
        if v is not None:
            if v < 0 or (c != "peso_tara" and v == 0):
                raise ErrorNegocio("Pallet dimensions must be greater than zero.", 422, "validacion")
            setattr(pallet, c, v)
    tocar(pl)
    return {"version": pl.version}


# ---- Plantillas y cajas -----------------------------------------------------
def _valores_plantilla(t: PlantillaCaja, cantidad: int | None = None) -> dict:
    """Valores por caja copiados de la plantilla. Para una caja parcial el peso
    se estima (neto proporcional; bruto = neto + empaque) y queda por confirmar."""
    valores = {"largo": t.largo, "ancho": t.ancho, "alto": t.alto,
               "peso_neto_caja": t.peso_neto, "peso_bruto_caja": t.peso_bruto}
    if cantidad is None or cantidad == t.cantidad_por_caja:
        return valores
    neto = round(t.peso_neto * cantidad / t.cantidad_por_caja, 3) if t.peso_neto else None
    if t.tara is not None and neto is not None:
        bruto = round(neto + t.tara, 3)
    elif t.peso_bruto and t.peso_neto is not None and neto is not None:
        bruto = round(neto + (t.peso_bruto - t.peso_neto), 3)
    elif t.peso_bruto:
        bruto = round(t.peso_bruto * cantidad / t.cantidad_por_caja, 3)
    else:
        bruto = None
    valores.update(peso_neto_caja=neto, peso_bruto_caja=bruto)
    return valores


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
            propio = sum(it.cantidad_por_caja * it.grupo.num_cajas for it in pll.items if len(it.grupo.items) == 1)
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


def _valores_regla(t: PlantillaCaja | None, fl, por_caja: int) -> tuple[dict, bool]:
    """Medidas y pesos para una caja con `por_caja` unidades. Devuelve también
    si el peso es estimado (la plantilla no corresponde exactamente)."""
    if not t:
        return {}, False
    if t.unidad == fl.unidad:
        exacta = por_caja == t.cantidad_por_caja
        return _valores_plantilla(t, None if exacta else por_caja), not exacta
    # Unidad distinta (p. ej. plantilla en pares para un prepack): medidas sí,
    # pesos copiados como referencia y marcados para confirmar
    return _valores_plantilla(t), True


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
    for it in list(pll.items):
        g = it.grupo
        if len(g.items) == 1:
            pl.grupos.remove(g)


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
        fl = pll.factura_linea
        t = db.get(PlantillaCaja, f["plantilla_id"]) if f["plantilla_id"] else None
        por_caja = f["cantidad_por_caja"]
        nombre = {"plantilla_id": t.id if t else None, "plantilla_nombre": t.nombre if t else None}
        if f["cajas"]:
            valores, estimado = _valores_regla(t, fl, por_caja)
            g = GrupoCajas(num_cajas=f["cajas"], peso_estimado=estimado, **nombre, **valores)
            g.items.append(GrupoCajasItem(pl_linea=pll, cantidad_por_caja=por_caja))
            pl.grupos.append(g)
        if f["sobrante"] and datos.sobrante == "caja_parcial":
            valores, _ = _valores_regla(t, fl, f["sobrante"])
            g = GrupoCajas(num_cajas=1, es_parcial=True, peso_estimado=bool(t), **nombre, **valores)
            if f["regla"] == "CASEPACK":
                g.observacion = f"Partial carton: {f['sobrante']} of {por_caja} of the casepack."
            g.items.append(GrupoCajasItem(pl_linea=pll, cantidad_por_caja=f["sobrante"]))
            pl.grupos.append(g)
    tocar(pl)
    registrar(db, user, "packing_list", pl.id, "aplicar_plantilla",
              {"plantillas": sorted({f["plantilla"] or "casepack" for f in filas if "omitida" not in f}),
               "sobrante": datos.sobrante, **resumen}, factura_id=pl.factura_id)
    return {"resumen": resumen, "version": pl.version}


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
    valores = _valores_plantilla(t, por_caja) if t else {}
    explicitos = datos.model_dump(exclude_unset=True)
    for c in CAMPOS_VALOR:
        if c in explicitos:
            valores[c] = explicitos[c]
    estimado = bool(t) and por_caja != t.cantidad_por_caja and not {"peso_neto_caja", "peso_bruto_caja"} <= set(explicitos)
    g = GrupoCajas(
        num_cajas=datos.num_cajas,
        plantilla_id=t.id if t else None,
        plantilla_nombre=t.nombre if t else None,
        es_parcial=bool(t) and por_caja < t.cantidad_por_caja,
        peso_estimado=estimado,
        observacion=explicitos.get("observacion"),
        **valores,
    )
    for item in datos.items:
        g.items.append(GrupoCajasItem(pl_linea=_linea(pl, item.pl_linea_id), cantidad_por_caja=item.cantidad_por_caja))
    pl.grupos.append(g)
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
            errores.append({"mensaje": f"{ref}: {'a prepack' if regla == 'PREPACK' else 'a solid with casepack'} "
                            "goes alone in its carton; it is not mixed with other styles, colors or sizes."})
            continue
        if regla == "PREPACK" and cant != 1:
            errores.append({"mensaje": f"{ref}: each master carton carries exactly one {pll.factura_linea.prepack} assortment."})
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
    for g in seleccion:
        if t:
            por_caja = sum(it.cantidad_por_caja for it in g.items)
            for c, v in _valores_plantilla(t, por_caja).items():
                setattr(g, c, v)
            g.plantilla_id, g.plantilla_nombre = t.id, t.nombre
            g.peso_estimado = por_caja != t.cantidad_por_caja
        for c in CAMPOS_VALOR:
            if c in campos:
                setattr(g, c, campos[c])
                if c.startswith("peso"):
                    g.peso_estimado = False
        if "observacion" in campos:
            g.observacion = (campos["observacion"] or "").strip() or None
        if datos.num_cajas and datos.num_cajas != g.num_cajas:
            for it in g.items:
                otros = cubierto(it.pl_linea) - it.cantidad_por_caja * g.num_cajas
                if otros + it.cantidad_por_caja * datos.num_cajas > it.pl_linea.cantidad:
                    errores.append({"grupo_id": g.id, "mensaje":
                        f"{_ref(it.pl_linea)}: not enough quantity for {datos.num_cajas} cartons."})
            g.num_cajas = datos.num_cajas
        if datos.confirmar_pesos:
            if g.peso_neto_caja is None or g.peso_bruto_caja is None:
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
        total += g.num_cajas
        afectadas.update(it.pl_linea for it in g.items)
        pl.grupos.remove(g)
    limpiar_pallets(pl)
    db.flush()
    for pll in afectadas:
        db.expire(pll, ["items"])
    tocar(pl)
    registrar(db, user, "packing_list", pl.id, "desempacar", {"cajas": total}, factura_id=pl.factura_id)
    return {"version": pl.version}


def guardar_como_plantilla(db: Session, user: Usuario, pl_id: int, grupo_id: int, nombre: str) -> dict:
    exigir(user, "plantilla.editar")
    pl = cargar_pl(db, user, pl_id)
    g = next((x for x in pl.grupos if x.id == grupo_id), None)
    if not g:
        raise ErrorNegocio("The carton does not exist.", 404, "no_encontrado")
    if len(g.items) != 1:
        raise ErrorNegocio("Only a single-product carton can be saved as a template.", 422, "validacion")
    nombre = nombre.strip()
    existe = db.scalar(select(PlantillaCaja.id).where(
        PlantillaCaja.proveedor_id == pl.factura.proveedor_id, PlantillaCaja.nombre == nombre))
    if existe:
        raise ErrorNegocio(f"A template named “{nombre}” already exists.", 409, "duplicado")
    it = g.items[0]
    t = PlantillaCaja(
        proveedor_id=pl.factura.proveedor_id, nombre=nombre, cantidad_por_caja=it.cantidad_por_caja,
        unidad=it.pl_linea.factura_linea.unidad, largo=g.largo, ancho=g.ancho, alto=g.alto,
        peso_neto=g.peso_neto_caja, peso_bruto=g.peso_bruto_caja, activa=True,
    )
    db.add(t)
    db.flush()
    return {"id": t.id, "nombre": t.nombre}


def destinos_pl(db: Session, pl: PackingList) -> list[dict]:
    """Lo que lleva el PL por país (centro) de destino: las cajas no mezclan
    destinos, así que el proveedor empaca y rotula por destino."""
    from ..models import Centro

    por: dict[str | None, dict] = {}
    for pll in pl.lineas:
        fl = pll.factura_linea
        d = por.setdefault(fl.centro_destino, {"centro_destino": fl.centro_destino, "por_unidad": {}, "cajas": 0})
        d["por_unidad"][fl.unidad] = d["por_unidad"].get(fl.unidad, 0) + pll.cantidad
    for g in pl.grupos:
        destinos = {it.pl_linea.factura_linea.centro_destino for it in g.items}
        if len(destinos) == 1:
            por[destinos.pop()]["cajas"] += g.num_cajas
    for d in por.values():
        c = db.scalar(select(Centro).where(Centro.codigo == d["centro_destino"])) if d["centro_destino"] else None
        d["nombre"] = c.nombre if c else None
        d["pais"] = c.pais if c else None
    return sorted(por.values(), key=lambda x: x["centro_destino"] or "")


# ---- Estados ----------------------------------------------------------------
MEDIDA_TXT = {"largo": "length", "ancho": "width", "alto": "height"}


def validar_pl(pl: PackingList) -> list[dict]:
    errores = []
    if not pl.lineas:
        errores.append({"mensaje": "The packing list has no contents."})
    pendientes: dict[str, list] = {}
    for pll in pl.lineas:
        libre = sin_caja(pll)
        if libre > 0:
            d = pendientes.setdefault(pll.factura_linea.unidad, [0, 0])
            d[0] += libre
            d[1] += 1
    for unidad, (cantidad, filas) in pendientes.items():
        errores.append({"codigo": "sin_caja", "mensaje":
            f"{cant_txt(cantidad, unidad)} not in cartons (rows: {filas})."})
    rangos = numeracion(pl)
    for g in pl.grupos:
        d, h = rangos[g.id]
        etiqueta = f"Carton {d}" if d == h else f"Cartons {d}–{h}"
        faltan = [n for n, v in (("largo", g.largo), ("ancho", g.ancho), ("alto", g.alto)) if not v]
        if faltan:
            errores.append({"grupo_id": g.id, "mensaje": f"{etiqueta}: dimensions missing ({', '.join(MEDIDA_TXT[x] for x in faltan)})."})
        if not g.peso_neto_caja or not g.peso_bruto_caja:
            errores.append({"grupo_id": g.id, "mensaje": f"{etiqueta}: net or gross weight missing."})
        elif g.peso_bruto_caja < g.peso_neto_caja:
            errores.append({"grupo_id": g.id, "mensaje": f"{etiqueta}: gross weight is less than net weight."})
        for it in g.items:
            n = inner_de(it.pl_linea.factura_linea)
            if n and it.cantidad_por_caja % n:
                errores.append({"grupo_id": g.id, "mensaje": f"{etiqueta}: {_ref(it.pl_linea)} carries "
                                f"{it.cantidad_por_caja} per carton, not whole inner packs of {n}."})
        if g.peso_estimado:
            errores.append({"grupo_id": g.id, "codigo": "peso_estimado",
                            "mensaje": f"{etiqueta}: the weight is estimated; confirm or correct it."})
    return errores


def avisos_pl(pl: PackingList) -> list[dict]:
    """Situaciones permitidas que conviene revisar (no impiden finalizar)."""
    avisos = []
    rangos = numeracion(pl)
    for g in pl.grupos:
        if len(g.items) != 1:
            continue
        it = g.items[0]
        regla, por_caja = regla_empaque(it.pl_linea.factura_linea)
        if regla == "CASEPACK" and it.cantidad_por_caja != por_caja:
            d, h = rangos[g.id]
            avisos.append({"grupo_id": g.id, "mensaje":
                f"Carton {d if d == h else f'{d}–{h}'}: partial ({it.cantidad_por_caja} of {por_caja} of the casepack). "
                "Confirm it with the Commercial Brand Manager."})
    return avisos


def finalizar_pl(db: Session, user: Usuario, pl_id: int, version: int) -> dict:
    exigir(user, "pl.finalizar")
    pl = _editable(db, user, pl_id, version)
    if pl.factura.estado == "CANCELADA":
        raise ErrorNegocio("The invoice is cancelled.", 409, "no_editable")
    errores = validar_pl(pl)
    if errores:
        raise ErrorNegocio("Some data is missing before finalizing.", 422, "pendientes", errores)
    pl.estado = "FINALIZADO"
    tocar(pl)
    registrar(db, user, "packing_list", pl.id, "finalizar", None, factura_id=pl.factura_id)
    return {"estado": pl.estado, "version": pl.version}


def reabrir_pl(db: Session, user: Usuario, pl_id: int, motivo: str | None) -> dict:
    exigir(user, "pl.reabrir")
    motivo = requerir_motivo(motivo, "reopen the packing list")
    pl = cargar_pl(db, user, pl_id)
    if pl.estado != "FINALIZADO":
        raise ErrorNegocio("Only finalized packing lists can be reopened.", 409, "no_editable")
    if pl.unidad and pl.unidad.embarque.estado != "PLANIFICADO":
        raise ErrorNegocio(f"{pl.numero} is already traveling on {pl.unidad.embarque.codigo}; it cannot be reopened.", 409,
                           "embarque_cerrado")
    nota = None
    if pl.unidad:
        # Solo lo finalizado va en un embarque: al reabrirlo sale de la unidad de carga
        nota = f"Removed from {pl.unidad.numero or pl.unidad.etiqueta}. Add it again once finalized."
        pl.unidad_carga_id, pl.asignacion, pl.recolectado_en = None, None, None
    pl.estado = "EN_CORRECCION"
    tocar(pl)
    registrar(db, user, "packing_list", pl.id, "reabrir", {"nota": nota} if nota else None, motivo,
              factura_id=pl.factura_id)
    return {"estado": pl.estado, "nota": nota}


def cancelar_pl(db: Session, user: Usuario, pl_id: int, motivo: str | None) -> dict:
    exigir(user, "pl.cancelar")
    pl = cargar_pl(db, user, pl_id)
    if pl.estado == "CANCELADO":
        raise ErrorNegocio("The packing list is already cancelled.", 409, "no_editable")
    if user.rol == "proveedor" and pl.estado != "BORRADOR":
        raise ErrorNegocio("You can only cancel draft packing lists.", 403, "sin_permiso")
    if pl.asignacion == "CONFIRMADA":
        raise ErrorNegocio("First remove the PL from its load unit.", 409, "pl_en_transporte")
    if pl.estado != "BORRADOR":
        motivo = requerir_motivo(motivo, "cancel the packing list")
    pl.estado = "CANCELADO"
    pl.unidad_carga_id = None
    pl.asignacion = None
    tocar(pl)
    registrar(db, user, "packing_list", pl.id, "cancelar", None, motivo, factura_id=pl.factura_id)
    return {"estado": pl.estado}


# ---- Recepción --------------------------------------------------------------
def registrar_recepcion(db: Session, user: Usuario, pl_id: int, datos) -> dict:
    exigir(user, "recepcion.registrar")
    pl = cargar_pl(db, user, pl_id)
    if pl.estado != "FINALIZADO":
        raise ErrorNegocio("Receipt is only recorded for finalized packing lists.", 409, "no_editable")
    diferencias = []
    for item in datos.lineas:
        pll = _linea(pl, item.pl_linea_id)
        rec = pll.recepcion
        if not rec:
            rec = RecepcionLinea(pl_linea=pll, cantidad_recibida=0)
        rec.cantidad_recibida = item.cantidad_recibida
        rec.cantidad_danada = item.cantidad_danada
        rec.observacion = (item.observacion or "").strip() or None
        rec.usuario_id = user.id
        rec.fecha = ahora()
        if item.cantidad_recibida != pll.cantidad or item.cantidad_danada:
            diferencias.append({"fila": _ref(pll), "esperado": pll.cantidad,
                                "recibido": item.cantidad_recibida, "danado": item.cantidad_danada})
    registrar(db, user, "packing_list", pl.id, "recepcion", {"diferencias": diferencias}, factura_id=pl.factura_id)
    return {"diferencias": diferencias}


# ---- Consulta ---------------------------------------------------------------
def _sugerencias(db: Session, pl: PackingList) -> dict[int, int]:
    """Plantilla sugerida por fila: la última usada en esa fila o, si no hay,
    la última con la que el proveedor empacó el mismo estilo (cajas completas)."""
    res: dict[int, int] = {}
    for g in pl.grupos:
        if g.plantilla_id:
            for it in g.items:
                res[it.pl_linea_id] = g.plantilla_id
    estilos = {pll.factura_linea.estilo for pll in pl.lineas if pll.id not in res and pll.factura_linea.estilo}
    if not estilos:
        return res
    por_estilo = dict(db.execute(
        select(FacturaLinea.estilo, GrupoCajas.plantilla_id)
        .join(PLLinea, PLLinea.factura_linea_id == FacturaLinea.id)
        .join(GrupoCajasItem, GrupoCajasItem.pl_linea_id == PLLinea.id)
        .join(GrupoCajas, GrupoCajas.id == GrupoCajasItem.grupo_id)
        .join(PlantillaCaja, PlantillaCaja.id == GrupoCajas.plantilla_id)
        .join(Factura, Factura.id == FacturaLinea.factura_id)
        .where(Factura.proveedor_id == pl.factura.proveedor_id, FacturaLinea.estilo.in_(estilos),
               PlantillaCaja.activa.is_(True), GrupoCajas.es_parcial.is_(False))
        .order_by(GrupoCajas.id)
    ).all())
    for pll in pl.lineas:
        if pll.id not in res and pll.factura_linea.estilo in por_estilo:
            res[pll.id] = por_estilo[pll.factura_linea.estilo]
    return res


def detalle_pl(db: Session, user: Usuario, pl_id: int) -> dict:
    permisos = permisos_de(user)
    from .facturas import _info_transporte

    pl = cargar_pl(db, user, pl_id)
    f = pl.factura
    rangos = numeracion(pl)
    ultima_plantilla = _sugerencias(db, pl)

    lineas = []
    for pll in sorted(pl.lineas, key=lambda x: (x.factura_linea_id, x.id)):
        fl = pll.factura_linea
        en_cajas = cubierto(pll)
        libre = pll.cantidad - en_cajas
        en_parcial = sum(it.cantidad_por_caja * it.grupo.num_cajas for it in pll.items if it.grupo.es_parcial)
        lineas.append({
            "id": pll.id,
            "factura_linea_id": fl.id,
            "oc_numero": fl.oc_numero,
            "almacen": fl.almacen,
            "posicion": fl.posicion,
            "codigo_sap": fl.codigo_sap,
            "upc": fl.upc,
            "estilo": fl.estilo,
            "color": fl.color,
            "talla": fl.talla,
            "descripcion": fl.descripcion,
            "unidad": fl.unidad,
            "marca": fl.marca,
            "tipo_empaque": fl.tipo_empaque,
            "casepack": fl.casepack,
            "inner_pack": inner_de(fl),
            # El inner pack se define en el PL si la OC no lo trae y aún no hay cajas
            "inner_editable": fl.tipo_empaque != "PREPACK" and not (fl.posicion_oc and fl.posicion_oc.inner_pack)
            and en_cajas == 0,
            "prepack": fl.prepack,
            "unidades_por_caja": fl.unidades_por_caja,
            "unidad_componentes": _unidad_componentes(fl),
            "centro_destino": fl.centro_destino,
            "regla": regla_empaque(fl)[0],
            "cantidad": pll.cantidad,
            "en_cajas": en_cajas,
            "en_parcial": en_parcial,
            "sin_caja": libre,
            "estado_empaque": "COMPLETO" if libre == 0 else ("PARCIAL" if en_cajas else "SIN_CAJA"),
            "plantilla_sugerida_id": ultima_plantilla.get(pll.id),
            "recepcion": (
                {"cantidad_recibida": pll.recepcion.cantidad_recibida,
                 "cantidad_danada": pll.recepcion.cantidad_danada,
                 "observacion": pll.recepcion.observacion}
                if pll.recepcion else None
            ),
        })

    grupos = []
    for g in pl.grupos:
        d, h = rangos[g.id]
        cbm = cbm_caja(g)
        items = [{
            "pl_linea_id": it.pl_linea_id,
            "codigo_sap": it.pl_linea.factura_linea.codigo_sap,
            "estilo": it.pl_linea.factura_linea.estilo,
            "color": it.pl_linea.factura_linea.color,
            "talla": it.pl_linea.factura_linea.talla,
            "unidad": it.pl_linea.factura_linea.unidad,
            "cantidad_por_caja": it.cantidad_por_caja,
            "cantidad_total": it.cantidad_por_caja * g.num_cajas,
            "inner_pack": inner_de(it.pl_linea.factura_linea),
            "inner_packs_por_caja": (it.cantidad_por_caja // inner_de(it.pl_linea.factura_linea)
                                     if inner_de(it.pl_linea.factura_linea) else None),
        } for it in g.items]
        grupos.append({
            "id": g.id,
            "desde": d,
            "hasta": h,
            "num_cajas": g.num_cajas,
            "items": items,
            "mixta": len(items) > 1,
            "largo": g.largo,
            "ancho": g.ancho,
            "alto": g.alto,
            "peso_neto_caja": g.peso_neto_caja,
            "peso_bruto_caja": g.peso_bruto_caja,
            "cbm_caja": round(cbm, 4) if cbm else None,
            "cbm_total": round(cbm * g.num_cajas, 4) if cbm else None,
            "peso_neto_total": round(g.peso_neto_caja * g.num_cajas, 3) if g.peso_neto_caja else None,
            "peso_bruto_total": round(g.peso_bruto_caja * g.num_cajas, 3) if g.peso_bruto_caja else None,
            "plantilla_id": g.plantilla_id,
            "plantilla_nombre": g.plantilla_nombre,
            "es_parcial": g.es_parcial,
            "peso_estimado": g.peso_estimado,
            "observacion": g.observacion,
            "etiqueta": etiqueta_caja(g),
            "pallet_id": g.pallet_id,
            "pallet": g.pallet.numero if g.pallet else None,
        })

    saldo = _saldo_factura(db, f)
    editable = pl.estado in EDITABLE_PL
    return {
        "id": pl.id,
        "numero": pl.numero,
        "estado": pl.estado,
        "version": pl.version,
        "factura": {"id": f.id, "nombre": nombre_factura(f), "estado": f.estado,
                    "proveedor_id": f.proveedor_id, "proveedor": f.proveedor.nombre},
        "lineas": lineas,
        "grupos": grupos,
        "pallets": resumen_pallets(pl),
        "partes": partes(db, f.sociedad, f.centro, f.centro_destino),
        "totales": totales_pl(pl),
        "destinos": destinos_pl(db, pl),
        "sugerencia_unidades": sugerir_unidades(db, totales_pl(pl)["cbm"], totales_pl(pl)["peso_bruto"]),
        "validaciones": validar_pl(pl) if editable else [],
        "avisos": avisos_pl(pl),
        "recolectado_en": pl.recolectado_en,
        "saldo_factura": sum(s for s in saldo.values() if s > 0),
        "otros_pl": [
            {"id": x.id, "numero": x.numero, "estado": x.estado}
            for x in f.packing_lists if x.id != pl.id and x.estado in EDITABLE_PL
        ],
        "transporte": _info_transporte(pl),
        "plantillas": [
            {"id": t.id, "nombre": t.nombre, "cantidad_por_caja": t.cantidad_por_caja, "unidad": t.unidad,
             "largo": t.largo, "ancho": t.ancho, "alto": t.alto, "peso_neto": t.peso_neto,
             "peso_bruto": t.peso_bruto}
            for t in db.scalars(select(PlantillaCaja).where(
                PlantillaCaja.proveedor_id == f.proveedor_id, PlantillaCaja.activa.is_(True))
                .order_by(PlantillaCaja.nombre)).all()
        ] if editable else [],
        "puede": {
            "editar": editable,
            "finalizar": editable and "pl.finalizar" in permisos,
            "reabrir": pl.estado == "FINALIZADO" and "pl.reabrir" in permisos,
            "cancelar": pl.estado != "CANCELADO" and "pl.cancelar" in permisos and (es_interno(user) or pl.estado == "BORRADOR"),
            "recepcion": pl.estado == "FINALIZADO" and "recepcion.registrar" in permisos,
        },
    }


