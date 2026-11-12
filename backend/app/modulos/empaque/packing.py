
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errores import ErrorNegocio
from app.core.numeracion import mayor_sufijo
from app.modelos import (
    Factura,
    GrupoCajas,
    GrupoCajasItem,
    PackingList,
    PlantillaCaja,
    PLLinea,
    TipoEmpaque,
    Usuario,
)
from app.modulos.acceso.permisos import asegurar_proveedor, exigir, exigir_alguno
from app.modulos.catalogo import servicio as catalogo
from app.modulos.comun.formato import cant_txt
from app.modulos.comun.historial import registrar, tocar, verificar_version
from app.modulos.empaque import empaques
from app.modulos.facturacion.cantidades import (
    asignado_por_linea,
    error_en_linea,
    inner_de,
    sin_caja,
)
from app.modulos.facturacion.estados import EDITABLE_PL, ESTADO_TXT
from app.modulos.facturacion.facturas import cargar_factura

CAMPOS_VALOR = ("largo", "ancho", "alto", "tara")


# ---- Árbol físico -----------------------------------------------------------
def quitar_nodo(pl: PackingList, g: GrupoCajas) -> None:
    """Quita un nodo y todo lo que lleva dentro."""
    for d in [*empaques.descendientes(pl, g), g]:
        if d in pl.grupos:
            pl.grupos.remove(d)


def limpiar_vacios(pl: PackingList) -> None:
    """Quita los empaques que quedaron sin producto ni empaques dentro."""
    cambio = True
    while cambio:
        cambio = False
        for g in list(pl.grupos):
            if not g.items and not empaques.hijos(pl, g):
                pl.grupos.remove(g)
                cambio = True


def escalar(pl: PackingList, g: GrupoCajas, nuevo: int) -> None:
    """Cambia la cantidad de unidades de un nodo y, en proporción, la de todo lo que lleva dentro."""
    viejo = g.num_cajas
    for d in empaques.descendientes(pl, g):
        d.num_cajas = d.num_cajas * nuevo // viejo
    g.num_cajas = nuevo


def rehacer(db: Session, pl: PackingList) -> None:
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
    de_receta = _tipos_receta(db, items[0][0].factura_linea) if len(items) == 1 else (None, None)
    tipo = tipo or (plantilla.tipo_empaque if plantilla and plantilla.tipo_empaque else None) or de_receta[0] \
        or _tipo(db, None, plantilla)
    base = plantilla or tipo
    g = GrupoCajas(num_cajas=num, tipo_empaque=tipo,
                   largo=getattr(base, "largo", None), ancho=getattr(base, "ancho", None),
                   alto=getattr(base, "alto", None), tara=getattr(base, "tara", None),
                   plantilla_id=plantilla.id if plantilla else None,
                   plantilla_nombre=plantilla.nombre if plantilla else None)
    for k, v in extra.items():
        setattr(g, k, v)
    pl.grupos.append(g)
    # El empaque interior lo dice la receta de la línea; sin receta, el que el tipo puede contener
    interior = de_receta[1] if de_receta[0] is tipo and de_receta[1] is not None else empaques.tipo_interior(tipo)
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


def _tipos_receta(db: Session, fl) -> tuple[TipoEmpaque | None, TipoEmpaque | None]:
    """(bulto, interior) según la receta de la línea: el primer nivel que cuenta
    como bulto y el nivel justo dentro de él."""
    niveles = (fl.receta_foto or {}).get("niveles") or []
    i = next((k for k, n in enumerate(niveles) if n.get("cuenta_como") == "BULTO"), None)
    if i is None:
        return None, None
    bulto = db.get(TipoEmpaque, niveles[i]["tipo_empaque_id"])
    interior = db.get(TipoEmpaque, niveles[i - 1]["tipo_empaque_id"]) if i > 0 else None
    return (bulto if bulto and bulto.activo else None), (interior if interior and interior.activo else None)


def bultos_propios(pl: PackingList, pll: PLLinea) -> list[GrupoCajas]:
    """Bultos que llevan solo esta fila (se pueden volver a empacar)."""
    res = []
    for it in pll.items:
        b = empaques.nodo_bulto(it.grupo)
        if b not in res and all(x is pll for x, _ in empaques.contenido(pl, b)):
            res.append(b)
    return res


# ---- Carga ------------------------------------------------------------------
def cargar_pl(db: Session, user: Usuario, pl_id: int) -> PackingList:
    # La bodega necesita la lista para registrar la recepción aunque no vea facturas
    exigir_alguno(user, "factura.ver", "recepcion.registrar")
    pl = db.get(PackingList, pl_id)
    if not pl:
        raise ErrorNegocio("The packing list does not exist.", 404, "no_encontrado")
    asegurar_proveedor(user, pl.factura.proveedor_id, pl.factura.sociedad)
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
    variante = catalogo.texto(fl.variante)
    return f"{fl.codigo_articulo}{' · ' + variante if variante else ''}"


def regla_empaque(fl) -> tuple[str, int | None]:
    """PREPACK: una curva por caja master, sin agregar ni quitar tallas.
    CASEPACK: cantidad exacta por caja del mismo estilo, color y talla.
    LIBRE: casepack no especificado; se elige la cantidad y se puede consolidar.
    Con inner pack (sólidos), toda cantidad por caja es de inner packs enteros:
    con casepack, la caja lleva casepack / inner packs; sin casepack, la caja
    lleva los inner packs que se definan."""
    if fl.tipo_empaque == catalogo.TIPO_PACK:
        return "PREPACK", 1
    if fl.casepack:
        return "CASEPACK", fl.casepack
    return "LIBRE", None


def etiqueta_caja(g, pl: PackingList | None = None) -> dict:
    """Estándar: una sola línea (una OC y un artículo). Consolidada: varias."""
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
    """PL-001, PL-002…: uno más que el mayor de la factura (contarlos repetía
    un número tras cancelar o renombrar uno) y nunca uno que ya exista."""
    usados = {(x.numero or "").upper() for x in pl_existentes}
    n = mayor_sufijo([x.numero for x in pl_existentes], "PL-") + 1
    while f"PL-{n:03d}" in usados:
        n += 1
    return f"PL-{n:03d}"


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
    # La factura bloqueada: dos PL creados a la vez no toman el mismo número
    db.execute(select(Factura.id).where(Factura.id == factura.id).with_for_update())
    db.refresh(factura, ["packing_lists"])
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
        elif (msg := error_en_linea(next(l for l in factura.lineas if l.id == lid), c)):
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
        if (msg := error_en_linea(pll.factura_linea, m.cantidad)):
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
            escalar(origen, g, g.num_cajas - mg.num_cajas)
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
    limpiar_vacios(origen)
    rehacer(db, origen)
    rehacer(db, destino)
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


def destinos_pl(db: Session, pl: PackingList) -> list[dict]:
    """Lo que lleva el PL por país (centro) de destino: las cajas no mezclan
    destinos, así que el proveedor empaca y rotula por destino."""
    from app.modelos import Centro

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
