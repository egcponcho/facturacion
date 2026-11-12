"""Detalle de una lista de empaque como lo muestra su pantalla: líneas, árbol de
cajas y contenedores, sugerencias, validación, avisos y qué se puede hacer.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modelos import (
    Factura,
    FacturaLinea,
    GrupoCajas,
    GrupoCajasItem,
    PackingList,
    PlantillaCaja,
    PLLinea,
    PosicionOC,
    Usuario,
)
from app.modulos.acceso.permisos import es_interno, permisos_de
from app.modulos.catalogo import servicio as catalogo
from app.modulos.comun.edicion import ajeno as ajeno_edicion
from app.modulos.documentos.partes import partes
from app.modulos.empaque import empaques, recetas
from app.modulos.empaque.contenedores import _unidad_componentes, resumen_contenedores
from app.modulos.empaque.estados_pl import avisos_pl, bloqueo_cancelar, bloqueo_reabrir, validar_pl
from app.modulos.empaque.packing import _saldo_factura, cargar_pl, destinos_pl, etiqueta_caja, regla_empaque
from app.modulos.facturacion.cantidades import (
    cbm_caja,
    cubierto,
    inner_de,
    nombre_factura,
    numeracion,
    totales_pl,
)
from app.modulos.facturacion.estados import EDITABLE_PL
from app.modulos.recepcion.recepcion import de_pl as recepcion_de_pl
from app.modulos.transporte.sugerencias import sugerir_unidades


# ---- Consulta ---------------------------------------------------------------
def _sugerencias(db: Session, pl: PackingList) -> dict[int, int]:
    """Plantilla sugerida por fila: la última usada en esa fila o, si no hay,
    la última con la que el proveedor empacó el mismo producto (cajas completas)."""
    res: dict[int, int] = {}
    for g in pl.grupos:
        if g.plantilla_id:
            for it in g.items:
                res[it.pl_linea_id] = g.plantilla_id

    de_articulo = catalogo.productos_de(db, [pll.factura_linea.posicion_oc.articulo_id for pll in pl.lineas
                                             if pll.factura_linea.posicion_oc is not None])

    def producto(pll) -> int | None:
        p = pll.factura_linea.posicion_oc
        return de_articulo.get(p.articulo_id) if p is not None else None
    productos = {producto(pll) for pll in pl.lineas if pll.id not in res} - {None}
    if not productos:
        return res
    arts = catalogo.grupos_de_articulos()
    por_producto = dict(db.execute(
        select(arts.c.producto_id, GrupoCajas.plantilla_id)
        .select_from(FacturaLinea)
        .join(PosicionOC, PosicionOC.id == FacturaLinea.posicion_oc_id)
        .join(arts, arts.c.articulo_id == PosicionOC.articulo_id)
        .join(PLLinea, PLLinea.factura_linea_id == FacturaLinea.id)
        .join(GrupoCajasItem, GrupoCajasItem.pl_linea_id == PLLinea.id)
        .join(GrupoCajas, GrupoCajas.id == GrupoCajasItem.grupo_id)
        .join(PlantillaCaja, PlantillaCaja.id == GrupoCajas.plantilla_id)
        .join(Factura, Factura.id == FacturaLinea.factura_id)
        .where(Factura.proveedor_id == pl.factura.proveedor_id, arts.c.producto_id.in_(productos),
               PlantillaCaja.activa.is_(True), GrupoCajas.es_parcial.is_(False))
        .order_by(GrupoCajas.id)
    ).all())
    for pll in pl.lineas:
        if pll.id not in res and producto(pll) in por_producto:
            res[pll.id] = por_producto[producto(pll)]
    return res


def detalle_pl(db: Session, user: Usuario, pl_id: int) -> dict:
    permisos = permisos_de(user)
    from app.modulos.facturacion.facturas import info_transporte

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
            "codigo_articulo": fl.codigo_articulo,
            "codigo_barras": fl.codigo_barras,
            "variante": catalogo.texto(fl.variante),
            "valores": dict(fl.variante or {}),
            "atributos": dict(fl.atributos or {}),
            "descripcion": fl.descripcion,
            "unidad": fl.unidad,
            "peso_unitario": empaques.peso_linea(fl),
            "marca": catalogo.marca(db, fl.atributos),
            "tipo_empaque": fl.tipo_empaque,
            "casepack": fl.casepack,
            "inner_pack": inner_de(fl),
            # El inner pack se define en el PL si la OC no lo trae y aún no hay cajas
            "inner_editable": fl.tipo_empaque != catalogo.TIPO_PACK and not (fl.posicion_oc and fl.posicion_oc.inner_pack)
            and en_cajas == 0,
            "codigo_pack": fl.codigo_pack,
            "unidades_por_caja": fl.unidades_por_caja,
            "unidad_componentes": _unidad_componentes(fl),
            "centro_destino": fl.centro_destino,
            "regla": regla_empaque(fl)[0],
            # Receta de empaque de la línea (la foto que viene de la OC)
            "receta": (fl.receta_foto or {}).get("nombre"),
            "receta_resumen": recetas.resumen(fl.receta_foto),
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
                "pl_linea_id": pll.id, "codigo_articulo": fl.codigo_articulo, "variante": catalogo.texto(fl.variante),
                "atributos": dict(fl.atributos or {}), "unidad": fl.unidad, "cantidad_por_caja": n, "cantidad_total": n * g.num_cajas,
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
    edicion = ajeno_edicion(db, user, "packing_list", pl.id)
    editable = pl.estado in EDITABLE_PL and not edicion
    return {
        "edicion": edicion,
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
        "transporte": info_transporte(pl),
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
            # Visible con permiso; si la regla lo impide, el motivo va en `bloqueos`
            "reabrir": pl.estado == "FINALIZADO" and "pl.reabrir" in permisos,
            "cancelar": pl.estado != "CANCELADO" and "pl.cancelar" in permisos and (es_interno(user) or pl.estado == "BORRADOR"),
        },
        "bloqueos": {"reabrir": bloqueo_reabrir(pl), "cancelar": bloqueo_cancelar(pl, user)},
        # La recepción es del contenedor en el que viaja (docs/FLUJOS.md §3)
        "recepcion_unidad": recepcion_de_pl(db, user, pl),
    }
