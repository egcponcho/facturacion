"""Recepción (diseño v3): la lista de unidades de carga por recibir y las ya recibidas.

«Por recibir» son las unidades con carga de los embarques en tránsito, en
destino o entregados que todavía no se recibieron completas; las que ya llegaron
se pueden contar ahora y las que vienen en camino se muestran con su ETA para
planear el trabajo de bodega. «Recepciones» son las unidades ya recibidas, con
sus diferencias. Todo con el alcance de embarques del usuario.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.estados import EMBARQUE
from app.modelos import Embarque, PackingList, UnidadCarga, Usuario
from app.modulos.acceso.permisos import exigir_alguno
from app.modulos.recepcion.recepcion import VER, diferencias, nombre_unidad, pls_de, totales
from app.modulos.transporte.alcance import condiciones_alcance

VISTAS = ("pendientes", "recibidas")
LIMITE = 500


def lista(db: Session, user: Usuario, vista: str = "pendientes") -> list[dict]:
    exigir_alguno(user, *VER)
    vista = vista if vista in VISTAS else "pendientes"
    con_carga = select(PackingList.id).where(PackingList.unidad_carga_id == UnidadCarga.id, PackingList.estado != "CANCELADO").exists()
    cond = [con_carga, *condiciones_alcance(db, user)]
    if vista == "pendientes":
        cond += [Embarque.estado.in_(("EN_TRANSITO", "ARRIBADO", "ENTREGADO")), UnidadCarga.recepcion_estado != "RECIBIDA"]
        orden = (Embarque.arribo_real.is_(None), Embarque.eta, UnidadCarga.id)
    else:
        cond += [UnidadCarga.recepcion_estado == "RECIBIDA"]
        orden = (UnidadCarga.recibida_en.desc(), UnidadCarga.id.desc())
    unidades = db.scalars(select(UnidadCarga).join(Embarque, Embarque.id == UnidadCarga.embarque_id).where(*cond)
                          .options(selectinload(UnidadCarga.embarque), selectinload(UnidadCarga.packing_lists))
                          .order_by(*orden).limit(LIMITE)).all()
    res = []
    for u in unidades:
        e = u.embarque
        pls = pls_de(u)
        difs = diferencias(u) if vista == "recibidas" else []
        res.append({
            "id": u.id, "nombre": nombre_unidad(u), "tipo": u.tipo, "recepcion_estado": u.recepcion_estado,
            "recibida_en": u.recibida_en, "centro": u.centro or e.centro,
            "embarque": {"id": e.id, "codigo": e.codigo, "estado": e.estado, "tipo_transporte": e.tipo_transporte},
            "eta": e.eta, "arribo_real": e.arribo_real,
            # Se puede contar cuando el embarque ya llegó (las que vienen en camino solo se planean)
            "puede_recibir": EMBARQUE.puede("recibir", e.estado),
            "proveedores": sorted({pl.factura.proveedor.nombre for pl in pls}),
            "listas": len(pls), **totales(u),
            "diferencias": len(difs),
        })
    return res
