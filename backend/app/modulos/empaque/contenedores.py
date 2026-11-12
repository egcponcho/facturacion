"""Contenedores de una lista de empaque: pallets u otro empaque que lleva empaques.
Paletizar y despaletizar, definir el inner pack de una línea, renombrar y editar
un contenedor.
"""
import re

from sqlalchemy import func, select
from sqlalchemy.orm import Session, object_session

from app.core.errores import ErrorNegocio
from app.modelos import (
    Factura,
    GrupoCajas,
    PackingList,
    PLLinea,
    Usuario,
)
from app.modulos.catalogo import servicio as catalogo
from app.modulos.comun.historial import registrar, tocar
from app.modulos.empaque import empaques, recetas
from app.modulos.empaque.packing import _editable, _tipo, limpiar_vacios, rehacer
from app.modulos.facturacion.cantidades import (
    cubierto,
    numeracion,
)


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
    limpiar_vacios(pl)
    rehacer(db, pl)
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
    limpiar_vacios(pl)
    rehacer(db, pl)
    tocar(pl)
    registrar(db, user, "packing_list", pl.id, "despaletizar", None, factura_id=pl.factura_id)
    return {"version": pl.version}


def _unidad_componentes(fl) -> str | None:
    """Unidad de las variantes que forman un pack o kit (pares, unidades…)."""
    p = fl.posicion_oc
    art = catalogo.articulo(object_session(fl), p.articulo_id) if p is not None and p.articulo_id else None
    return art.componentes[0].unidad if art is not None and art.componentes else None


def definir_inner(db: Session, user: Usuario, pl_id: int, pl_linea_id: int, datos) -> dict:
    """Inner pack definido al armar el PL: la OC normalmente trae solo el
    casepack (variantes simples) o el contenido (packs y kits); el inner pack se decide aquí."""
    pl = _editable(db, user, pl_id, datos.version)
    pll = next((x for x in pl.lineas if x.id == pl_linea_id), None)
    if not pll:
        raise ErrorNegocio("One of the rows is no longer in the packing list. Reload.", 404, "no_encontrado")
    fl = pll.factura_linea
    n = datos.inner_pack or None
    if fl.tipo_empaque == catalogo.TIPO_PACK:
        raise ErrorNegocio("A pack or kit carton is defined by its contents; it has no inner pack.", 422, "validacion")
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
    # La receta de la línea sigue al casepack y al inner pack (empaque/recetas.py)
    r = recetas.receta_para_datos(db, fl.casepack, n) if fl.casepack else None
    fl.receta_id, fl.receta_foto = (r.id, recetas.foto(r)) if r is not None else (None, None)
    tocar(pl)
    registrar(db, user, "packing_list", pl.id, "inner_pack", {"linea": fl.codigo_articulo, "inner_pack": n})
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
    rehacer(db, pl)
    tocar(pl)
    return {"version": pl.version}


