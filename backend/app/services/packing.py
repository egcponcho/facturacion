import re

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import (
    TipoEmpaque,
    Factura,
    FacturaLinea,
    GrupoCajas,
    GrupoCajasItem,
    PackingList,
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
    nombre_factura,
    numeracion,
    sin_caja,
    totales_pl,
)
from . import empaques
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

CAMPOS_VALOR = ("largo", "ancho", "alto", "tara")


# ---- Árbol físico -----------------------------------------------------------
def _quitar_nodo(pl: PackingList, g: GrupoCajas) -> None:
    """Quita un nodo y todo lo que lleva dentro."""
    for d in [*empaques.descendientes(pl, g), g]:
        if d in pl.grupos:
            pl.grupos.remove(d)


def _limpiar_vacios(pl: PackingList) -> None:
    """Quita los empaques que quedaron sin producto ni empaques dentro."""
    cambio = True
    while cambio:
        cambio = False
        for g in list(pl.grupos):
            if not g.items and not empaques.hijos(pl, g):
                pl.grupos.remove(g)
                cambio = True


def _escalar(pl: PackingList, g: GrupoCajas, nuevo: int) -> None:
    """Cambia la cantidad de unidades de un nodo y, en proporción, la de todo lo que lleva dentro."""
    viejo = g.num_cajas
    for d in empaques.descendientes(pl, g):
        d.num_cajas = d.num_cajas * nuevo // viejo
    g.num_cajas = nuevo


def _rehacer(db: Session, pl: PackingList) -> None:
    """Recalcula los pesos de toda la estructura (después de cada cambio)."""
    db.flush()
    empaques.recalcular(pl)


def _tipo(db: Session, tipo_id: int | None, plantilla: PlantillaCaja | None = None) -> TipoEmpaque | None:
    if tipo_id:
        t = db.get(TipoEmpaque, tipo_id)
        if not t or not t.activo:
            raise ErrorNegocio("The packaging type does not exist or is inactive.", 404, "no_encontrado")
        return t
    if plantilla and plantilla.tipo_empaque:
        return plantilla.tipo_empaque
    return empaques.tipo_bulto(db)


def _nodo(db: Session, pl: PackingList, num: int, items: list[tuple], plantilla: PlantillaCaja | None = None,
          tipo: TipoEmpaque | None = None, **extra) -> GrupoCajas:
    """Crea N unidades de empaque con su producto. Medidas y tara salen de la
    plantilla o, si no hay, del tipo de empaque. Si las líneas tienen inner pack
    y el tipo admite un empaque interno con producto, se arman los inner packs
    como empaques físicos dentro de cada caja (con su propia tara)."""
    tipo = tipo or _tipo(db, None, plantilla)
    base = plantilla or tipo
    g = GrupoCajas(num_cajas=num, tipo_empaque=tipo,
                   largo=getattr(base, "largo", None), ancho=getattr(base, "ancho", None),
                   alto=getattr(base, "alto", None), tara=getattr(base, "tara", None),
                   plantilla_id=plantilla.id if plantilla else None,
                   plantilla_nombre=plantilla.nombre if plantilla else None)
    for k, v in extra.items():
        setattr(g, k, v)
    pl.grupos.append(g)
    interior = empaques.tipo_interior(tipo)
    for pll, cant in items:
        n = inner_de(pll.factura_linea)
        if interior and n and cant % n == 0:
            h = GrupoCajas(num_cajas=num * (cant // n), tipo_empaque=interior, padre=g, largo=interior.largo,
                           ancho=interior.ancho, alto=interior.alto, tara=interior.tara,
                           plantilla_id=g.plantilla_id, plantilla_nombre=g.plantilla_nombre)
            h.items.append(GrupoCajasItem(pl_linea=pll, cantidad_por_caja=n))
            pl.grupos.append(h)
        else:
            g.items.append(GrupoCajasItem(pl_linea=pll, cantidad_por_caja=cant))
    return g


def _bultos_propios(pl: PackingList, pll: PLLinea) -> list[GrupoCajas]:
    """Bultos que llevan solo esta fila (se pueden volver a empacar)."""
    res = []
    for it in pll.items:
        b = empaques.nodo_bulto(it.grupo)
        if b not in res and all(x is pll for x, _ in empaques.contenido(pl, b)):
            res.append(b)
    return res


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


def etiqueta_caja(g, pl: PackingList | None = None) -> dict:
    """Estándar: una sola OC, estilo, color y talla. Consolidada: varias."""
    lineas = [x.factura_linea for x, _ in empaques.contenido(pl or g.pl, g)]
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
            mover_g = _clonar_grupo(origen, g, mg.num_cajas)
            _escalar(origen, g, g.num_cajas - mg.num_cajas)
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
        for d in empaques.descendientes(origen, mover_g):
            for it in list(d.items):
                src = it.pl_linea
                cantidad = it.cantidad_por_caja * d.num_cajas
                src.cantidad -= cantidad
                it.pl_linea = _agregar_cantidad(destino, src.factura_linea_id, cantidad)
                if src.cantidad == 0:
                    origen.lineas.remove(src)
            d.pl = destino
        mover_g.pl = destino
        mover_g.padre = None
        total_cajas += mover_g.num_cajas
    _limpiar_vacios(origen)
    _rehacer(db, origen)
    _rehacer(db, destino)
    tocar(origen)
    tocar(destino)
    registrar(db, user, "packing_list", origen.id, "mover_cajas",
              {"destino": destino.numero, "cajas": total_cajas}, factura_id=origen.factura_id)
    return {"destino_id": destino.id, "destino_numero": destino.numero, "version": origen.version}


def _clonar_grupo(pl: PackingList, g: GrupoCajas, num_cajas: int, padre: GrupoCajas | None = None) -> GrupoCajas:
    """Copia `num_cajas` unidades de un nodo con todo lo que lleva dentro."""
    nuevo = GrupoCajas(
        num_cajas=num_cajas,
        **{c: getattr(g, c) for c in CAMPOS_VALOR},
        tipo_empaque=g.tipo_empaque, neto_manual=g.neto_manual,
        plantilla_id=g.plantilla_id,
        plantilla_nombre=g.plantilla_nombre,
        es_parcial=g.es_parcial,
        peso_estimado=g.peso_estimado,
        observacion=g.observacion,
        padre=padre,
    )
    for it in g.items:
        nuevo.items.append(GrupoCajasItem(pl_linea=it.pl_linea, cantidad_por_caja=it.cantidad_por_caja))
    pl.grupos.append(nuevo)
    for h in empaques.hijos(pl, g):
        if h is not nuevo:
            _clonar_grupo(pl, h, h.num_cajas * num_cajas // g.num_cajas, nuevo)
    return nuevo


# ---- Contenedores (pallets u otro empaque que lleva empaques) ---------------
def resumen_contenedores(pl: PackingList, rangos=None) -> list[dict]:
    """Empaques que llevan otros empaques dentro (pallets, cajas con inner…),
    con lo que contienen, su tara y su peso bruto acumulado."""
    rangos = rangos or numeracion(pl)
    res = []
    for g in empaques._orden_arbol(pl):
        hs = empaques.hijos(pl, g)
        if not hs or (empaques.cuenta_como(g) == "BULTO"
                      and all(empaques.cuenta_como(h) == "INTERIOR" for h in hs)):
            continue
        cbm = empaques.volumen(g)
        res.append({
            "id": g.id, "tipo": empaques.nombre_tipo(g), "tipo_id": g.tipo_empaque_id,
            "etiqueta": empaques.rango_txt(pl, g, rangos), "num": g.num_cajas,
            "numero": rangos[g.id][0],
            "largo": g.largo, "ancho": g.ancho, "alto": g.alto, "peso_tara": g.tara, "tara": g.tara,
            "contenido": [{"id": h.id, "tipo": empaques.nombre_tipo(h), "etiqueta": empaques.rango_txt(pl, h, rangos),
                           "por_unidad": empaques.por_padre(g, h), "total": h.num_cajas} for h in hs],
            "cajas": sum(h.num_cajas for h in hs),
            "peso_bruto": round((g.peso_bruto_caja or 0) * g.num_cajas, 3),
            "cbm": round(cbm * g.num_cajas, 4) if cbm else None,
            "rangos": [empaques.rango_txt(pl, h, rangos) for h in hs],
        })
    return res


resumen_pallets = resumen_contenedores


def paletizar(db: Session, user: Usuario, pl_id: int, datos) -> dict:
    """Pone empaques dentro de un contenedor nuevo (pallet u otro tipo, con sus
    medidas) o de uno existente. Cada grupo va completo y se reparte por igual
    entre las unidades del contenedor."""
    pl = _editable(db, user, pl_id, datos.version)
    grupos = {g.id: g for g in pl.grupos}
    faltan = [i for i in datos.grupo_ids if i not in grupos]
    if faltan or not datos.grupo_ids:
        raise ErrorNegocio("Choose cartons from this packing list.", 422, "validacion")
    if datos.pallet_id:
        cont = grupos.get(datos.pallet_id)
        if not cont:
            raise ErrorNegocio("The pallet does not exist in this packing list.", 404, "no_encontrado")
    else:
        tipo = _tipo(db, datos.tipo_empaque_id) if datos.tipo_empaque_id else empaques.tipo_soporte(db)
        # Largo y ancho pueden venir del tipo; el alto de un soporte armado (pallet
        # con su carga) siempre se mide
        medidas = {c: getattr(datos, c) or (getattr(tipo, c) if tipo and not (
            c == "alto" and tipo.cuenta_como == "SOPORTE") else None) for c in ("largo", "ancho", "alto")}
        errores = [{"campo": c, "mensaje": f"Pallet {t} is required and must be greater than zero."}
                   for c, t in (("largo", "length"), ("ancho", "width"), ("alto", "height"))
                   if not medidas[c] or medidas[c] <= 0]
        if errores:
            raise ErrorNegocio("The pallet dimensions are missing.", 422, "validacion", errores)
        tara = datos.peso_tara if datos.peso_tara is not None else (tipo.tara if tipo else 0)
        cont = GrupoCajas(num_cajas=datos.num or 1, tipo_empaque=tipo, tara=tara, **medidas)
        pl.grupos.append(cont)
    errores = []
    for i in datos.grupo_ids:
        g = grupos[i]
        if g is cont or cont in empaques.ancestros(g) or g in empaques.ancestros(cont):
            errores.append({"grupo_id": i, "mensaje": "A packaging cannot go inside itself."})
        elif g.num_cajas % cont.num_cajas:
            errores.append({"grupo_id": i, "mensaje": f"{g.num_cajas} units cannot be split evenly into {cont.num_cajas}."})
        elif cont.tipo_empaque and g.tipo_empaque and g.tipo_empaque not in cont.tipo_empaque.contiene:
            errores.append({"grupo_id": i, "mensaje": f"A {cont.tipo_empaque.nombre.lower()} cannot contain a "
                            f"{g.tipo_empaque.nombre.lower()}. Check the packaging types."})
    if errores:
        if not datos.pallet_id:
            pl.grupos.remove(cont)
        raise ErrorNegocio("Those cartons cannot go in that packaging.", 422, "validacion", errores)
    for i in datos.grupo_ids:
        grupos[i].padre = cont
    _limpiar_vacios(pl)
    _rehacer(db, pl)
    tocar(pl)
    numero = numeracion(pl)[cont.id][0]
    registrar(db, user, "packing_list", pl.id, "paletizar",
              {"pallet": numero, "cajas": sum(grupos[i].num_cajas for i in datos.grupo_ids)},
              factura_id=pl.factura_id)
    return {"pallet_id": cont.id, "numero": numero, "version": pl.version}


def despaletizar(db: Session, user: Usuario, pl_id: int, datos) -> dict:
    """Saca empaques de su contenedor (o vacía un contenedor completo). Los
    contenedores que quedan vacíos se quitan."""
    pl = _editable(db, user, pl_id, datos.version)
    for g in pl.grupos:
        if g.id in datos.grupo_ids or (datos.pallet_id and g.padre_id == datos.pallet_id):
            g.padre = None
    _limpiar_vacios(pl)
    _rehacer(db, pl)
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
    cont = next((g for g in pl.grupos if g.id == pallet_id), None)
    if not cont:
        raise ErrorNegocio("The pallet does not exist in this packing list.", 404, "no_encontrado")
    for c in ("largo", "ancho", "alto", "peso_tara"):
        v = getattr(datos, c)
        if v is not None:
            if v < 0 or (c != "peso_tara" and v == 0):
                raise ErrorNegocio("Pallet dimensions must be greater than zero.", 422, "validacion")
            setattr(cont, "tara" if c == "peso_tara" else c, v)
    _rehacer(db, pl)
    tocar(pl)
    return {"version": pl.version}


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
            propio = sum(n * b.num_cajas for b in _bultos_propios(pl, pll) for _, n in empaques.contenido(pl, b))
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
    for b in _bultos_propios(pl, pll):
        _quitar_nodo(pl, b)
    _limpiar_vacios(pl)


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
    _rehacer(db, pl)
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
    explicitos = datos.model_dump(exclude_unset=True)
    tipo = _tipo(db, explicitos.get("tipo_empaque_id"), t)
    g = _nodo(db, pl, datos.num_cajas, [(_linea(pl, i.pl_linea_id), i.cantidad_por_caja) for i in datos.items], t, tipo,
              es_parcial=bool(t) and por_caja < t.cantidad_por_caja, observacion=explicitos.get("observacion"))
    for c in CAMPOS_VALOR:
        if c in explicitos:
            setattr(g, c, explicitos[c])
    if explicitos.get("peso_neto_caja") is not None:
        g.neto_manual = explicitos["peso_neto_caja"]
    _rehacer(db, pl)
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
                _escalar(pl, g, datos.num_cajas)
    _rehacer(db, pl)
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
        _quitar_nodo(pl, g)
    _limpiar_vacios(pl)
    db.flush()
    for pll in afectadas:
        db.expire(pll, ["items"])
    _rehacer(db, pl)
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
        if empaques.cuenta_como(g) != "BULTO":
            continue
        destinos = {x.factura_linea.centro_destino for x, _ in empaques.contenido(pl, g)}
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
        etiqueta = f"{empaques.nombre_tipo(g)} {empaques.rango_txt(pl, g, rangos)}"
        # Medidas exteriores: las necesita el bulto y lo que no va dentro de otro empaque
        if g.padre is None or empaques.cuenta_como(g) == "BULTO":
            faltan = [n for n, v in (("largo", g.largo), ("ancho", g.ancho), ("alto", g.alto)) if not v]
            if faltan:
                errores.append({"grupo_id": g.id, "mensaje": f"{etiqueta}: dimensions missing ({', '.join(MEDIDA_TXT[x] for x in faltan)})."})
        if g.items and not g.peso_neto_caja:
            sin = sorted({it.pl_linea.factura_linea.codigo_sap for it in g.items
                          if empaques.peso_linea(it.pl_linea.factura_linea) is None})
            errores.append({"grupo_id": g.id, "codigo": "sin_peso", "mensaje":
                            f"{etiqueta}: net weight missing. Set the unit weight of item {', '.join(sin)} "
                            "or enter the net weight." if sin else f"{etiqueta}: net weight missing."})
        for it in g.items:
            n = inner_de(it.pl_linea.factura_linea)
            if n and it.cantidad_por_caja % n:
                errores.append({"grupo_id": g.id, "mensaje": f"{etiqueta}: {_ref(it.pl_linea)} carries "
                                f"{it.cantidad_por_caja} per carton, not whole inner packs of {n}."})
        if g.peso_estimado and not empaques.calculado(g):
            errores.append({"grupo_id": g.id, "codigo": "peso_estimado",
                            "mensaje": f"{etiqueta}: the weight is estimated; confirm or correct it."})
    errores.extend(empaques.validar(pl, rangos))
    return errores


def avisos_pl(pl: PackingList) -> list[dict]:
    """Situaciones permitidas que conviene revisar (no impiden finalizar)."""
    avisos = []
    rangos = numeracion(pl)
    for g in pl.grupos:
        if empaques.cuenta_como(g) != "BULTO":
            continue
        cont = empaques.contenido(pl, g)
        if len(cont) != 1:
            continue
        pll, n = cont[0]
        regla, por_caja = regla_empaque(pll.factura_linea)
        if regla == "CASEPACK" and n != por_caja:
            avisos.append({"grupo_id": g.id, "mensaje":
                f"Carton {empaques.rango_txt(pl, g, rangos)}: partial ({n:g} of {por_caja} of the casepack). "
                "Confirm it with the Commercial Brand Manager."})
    sin_peso = sorted({pll.factura_linea.codigo_sap for pll in pl.lineas if empaques.peso_linea(pll.factura_linea) is None})
    if sin_peso:
        lista = ", ".join(sin_peso[:8]) + ("…" if len(sin_peso) > 8 else "")
        avisos.append({"codigo": "sin_peso_articulo",
                       "mensaje": f"Items without unit weight: {lista}. Their net weight is entered by hand."})
    return avisos


def finalizar_pl(db: Session, user: Usuario, pl_id: int, version: int) -> dict:
    exigir(user, "pl.finalizar")
    pl = _editable(db, user, pl_id, version)
    if pl.factura.estado == "CANCELADA":
        raise ErrorNegocio("The invoice is cancelled.", 409, "no_editable")
    _rehacer(db, pl)
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
    if pl.estado in EDITABLE_PL:
        empaques.recalcular(pl)  # el peso de los artículos pudo cambiar
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
            "peso_unitario": empaques.peso_linea(fl),
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
    for g in empaques._orden_arbol(pl):
        d, h = rangos[g.id]
        cbm = cbm_caja(g)

        def item(pll, n, g=g):
            fl = pll.factura_linea
            return {
                "pl_linea_id": pll.id, "codigo_sap": fl.codigo_sap, "estilo": fl.estilo, "color": fl.color,
                "talla": fl.talla, "unidad": fl.unidad, "cantidad_por_caja": n, "cantidad_total": n * g.num_cajas,
                "peso_unitario": empaques.peso_linea(fl), "inner_pack": inner_de(fl),
                "inner_packs_por_caja": (n // inner_de(fl) if inner_de(fl) else None),
            }

        hs = empaques.hijos(pl, g)
        grupos.append({
            "id": g.id,
            "desde": d,
            "hasta": h,
            "etiqueta_rango": empaques.rango_txt(pl, g, rangos),
            "num_cajas": g.num_cajas,
            "tipo_empaque_id": g.tipo_empaque_id,
            "tipo": empaques.nombre_tipo(g),
            "cuenta_como": empaques.cuenta_como(g),
            "nivel": len(empaques.ancestros(g)),
            "padre_id": g.padre_id,
            "padre": empaques.rango_txt(pl, g.padre, rangos) if g.padre else None,
            "por_padre": empaques.por_padre(g.padre, g) if g.padre else None,
            "hijos": [{"id": x.id, "tipo": empaques.nombre_tipo(x), "etiqueta": empaques.rango_txt(pl, x, rangos),
                       "por_unidad": empaques.por_padre(g, x)} for x in hs],
            "items": [item(it.pl_linea, it.cantidad_por_caja) for it in g.items],
            "contenido": [item(pll, n) for pll, n in empaques.contenido(pl, g)],
            "mixta": len(empaques.contenido(pl, g)) > 1,
            "largo": g.largo,
            "ancho": g.ancho,
            "alto": g.alto,
            "tara": g.tara,
            "neto_manual": g.neto_manual,
            "peso_calculado": empaques.calculado(g),
            "peso_neto_caja": g.peso_neto_caja,
            "peso_bruto_caja": g.peso_bruto_caja,
            "cbm_caja": round(cbm, 4) if cbm else None,
            "cbm_total": round(cbm * g.num_cajas, 4) if cbm and g.padre is None else None,
            "peso_neto_total": round(g.peso_neto_caja * g.num_cajas, 3) if g.peso_neto_caja else None,
            "peso_bruto_total": round(g.peso_bruto_caja * g.num_cajas, 3) if g.peso_bruto_caja else None,
            "plantilla_id": g.plantilla_id,
            "plantilla_nombre": g.plantilla_nombre,
            "es_parcial": g.es_parcial,
            "peso_estimado": g.peso_estimado and not empaques.calculado(g),
            "observacion": g.observacion,
            "etiqueta": etiqueta_caja(g, pl),
            # Compatibilidad: el soporte (pallet) en el que va
            "pallet_id": next((a.id for a in empaques.ancestros(g) if empaques.cuenta_como(a) == "SOPORTE"), None),
            "pallet": next((empaques.rango_txt(pl, a, rangos) for a in empaques.ancestros(g)
                            if empaques.cuenta_como(a) == "SOPORTE"), None),
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
        "pallets": resumen_contenedores(pl, rangos),
        "tipos_empaque": [empaques.tipo_dict(t) for t in empaques.tipos_activos(db)],
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
             "largo": t.largo, "ancho": t.ancho, "alto": t.alto, "tara": t.tara, "tipo_empaque_id": t.tipo_empaque_id}
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


