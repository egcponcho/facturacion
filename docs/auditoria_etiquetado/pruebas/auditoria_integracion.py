"""Pruebas de auditoría (solo lectura del repositorio; datos en la base temporal de pruebas)."""
import sys
sys.path.insert(0, "/home/user/facturacion/backend/tests")
sys.path.insert(0, "/home/user/facturacion/backend")
from conftest import client, interno, admin  # noqa: F401,E402  (fixtures)
from etiquetado_util import aprobada, tipo, uso  # noqa: E402

import pytest  # noqa: E402
from sqlalchemy import select  # noqa: E402
from sqlalchemy.exc import IntegrityError  # noqa: E402

from app.core.db import SessionLocal  # noqa: E402
from app.core.organizacion import en_organizacion  # noqa: E402

EL = [{"id": "s", "tipo": "campo", "campo": "articulo.sku", "x": 2, "y": 2, "w": 50, "h": 8}]
ELB = [{"id": "s", "tipo": "campo", "campo": "bulto.packing_list", "x": 2, "y": 2, "w": 50, "h": 8}]
ESTADO = {}


def _datos():
    """OC A (sólido + prepack del mismo producto), OC B (sólido), factura y PL en BORRADOR con una caja mixta A+B."""
    from app.modelos import (Articulo, Factura, FacturaLinea, GrupoCajas, GrupoCajasItem, OrdenCompra, PackingList, PLLinea,
                             PosicionOC, TipoEmpaque)
    with SessionLocal() as db, en_organizacion(1):
        pre = db.scalar(select(Articulo).where(Articulo.tipo == "PREPACK", Articulo.producto_id.is_not(None)).limit(1))
        sol = db.scalar(select(Articulo).where(Articulo.tipo == "SOLIDO", Articulo.producto_id == pre.producto_id).limit(1))
        caja = db.scalar(select(TipoEmpaque).where(TipoEmpaque.cuenta_como == "BULTO", TipoEmpaque.activo.is_(True)).limit(1))
        base = db.scalar(select(OrdenCompra).where(OrdenCompra.proveedor_id == pre.proveedor_id).limit(1))
        ocs = []
        for n in ("AUD-A", "AUD-B"):
            oc = OrdenCompra(proveedor_id=pre.proveedor_id, numero=n, sociedad=base.sociedad, centro=base.centro,
                             centro_destino=base.centro_destino, moneda=base.moneda, liberacion_comercial=base.liberacion_comercial,
                             liberacion_logistica=base.liberacion_logistica, estado="APROBADA")
            db.add(oc)
            db.flush()
            ocs.append(oc)
        a, b = ocs
        ps = [PosicionOC(oc_id=a.id, posicion="10", articulo_id=sol.id, codigo_articulo=sol.sku, cantidad=24, unidad="PAR"),
              PosicionOC(oc_id=a.id, posicion="20", articulo_id=pre.id, codigo_articulo=pre.sku, cantidad=3, unidad="CJ",
                         tipo_empaque="PREPACK"),
              PosicionOC(oc_id=b.id, posicion="10", articulo_id=sol.id, codigo_articulo=sol.sku, cantidad=12, unidad="PAR")]
        db.add_all(ps)
        db.flush()
        f = Factura(proveedor_id=pre.proveedor_id, moneda=base.moneda or "USD", sociedad=base.sociedad or "1000", estado="BORRADOR")
        db.add(f)
        db.flush()
        fls = []
        for p, oc in ((ps[0], a), (ps[2], b)):
            fl = FacturaLinea(factura_id=f.id, posicion_oc_id=p.id, cantidad=p.cantidad, precio_unitario=1, precio_oc=1,
                              oc_numero=oc.numero, posicion=p.posicion, codigo_articulo=p.codigo_articulo, unidad=p.unidad)
            db.add(fl)
            fls.append(fl)
        db.flush()
        pl = PackingList(factura_id=f.id, numero="PL-AUD", estado="BORRADOR")
        db.add(pl)
        db.flush()
        plls = [PLLinea(pl_id=pl.id, factura_linea_id=fl.id, cantidad=fl.cantidad) for fl in fls]
        db.add_all(plls)
        db.flush()
        g = GrupoCajas(pl_id=pl.id, num_cajas=2, tipo_empaque_id=caja.id)
        db.add(g)
        db.flush()
        db.add_all([GrupoCajasItem(grupo_id=g.id, pl_linea_id=plls[0].id, cantidad_por_caja=12),
                    GrupoCajasItem(grupo_id=g.id, pl_linea_id=plls[1].id, cantidad_por_caja=6)])
        db.commit()
        return {"oc_a": a.id, "oc_b": b.id, "pos": [p.id for p in ps], "pl": pl.id}


@pytest.fixture(scope="module")
def d(interno, admin):
    x = _datos()
    t_prod = interno.post("/etiquetas/tipos", {"codigo": "AUD_PROD", "nombre": "Aud prod", "sujeto": "ARTICULO",
                                               "cantidad": "POR_UNIDAD", "alcance": "PRODUCTO"})
    assert t_prod.status_code == 200, t_prod.text
    t_lin = tipo(interno, "AUD_LIN", cantidad="POR_UNIDAD")
    t_caja = tipo(interno, "AUD_CAJA", sujeto="BULTO", cantidad="POR_BULTO")
    for t, el in ((t_prod.json(), EL), (t_lin, EL), (t_caja, ELB)):
        uso(interno, t["id"], aprobada(interno, admin, f"Aud {t['codigo']}", t["id"], el)["id"])
    return {**x, "t_prod": t_prod.json()["id"], "t_lin": t_lin["id"], "t_caja": t_caja["id"]}


def _trabajo(api, origen, par):
    r = api.post("/etiquetas/trabajos", {"origen": origen, "parametros": par})
    assert r.status_code == 200, r.text
    v = api.post(f"/etiquetas/trabajos/{r.json()['id']}/validar")
    assert v.status_code == 200, v.text
    return v.json()


def test_cantidades_prepack_y_producto(interno, d):
    t = _trabajo(interno, "OC", {"oc_ids": [d["oc_a"]], "tipos": [d["t_prod"], d["t_lin"]]})
    regs = [(r["tipo_etiqueta_id"] == d["t_prod"] and "PROD" or "LIN", r["referencia"], r["cantidad"], r["estado"]) for r in t["registros"]]
    print("\nREGISTROS OC A:", regs)
    ESTADO["prod"] = regs


def test_bultos_duplicados_multi_oc_y_pl_borrador(interno, d):
    t = _trabajo(interno, "OC", {"oc_ids": [d["oc_a"], d["oc_b"]], "tipos": [d["t_caja"]], "prueba": False})
    regs = [(r["clave"], r["estado"], [p["codigo"] for p in r["problemas"]]) for r in t["registros"]]
    print("\nREGISTROS bultos (2 cajas físicas):", regs)
    print("PROBLEMAS generales:", t["resumen"].get("problemas"), t["resumen"].get("avisos"))
    t2 = _trabajo(interno, "PACKING", {"pl_id": d["pl"], "tipos": [d["t_caja"]], "prueba": False})
    print("DESDE PL borrador:", t2["resumen"].get("problemas"))
    ESTADO["trabajo_oc"] = t["id"]


def test_borrar_posicion_con_registro(interno, d):
    from app.modelos import PosicionOC
    with SessionLocal() as db, en_organizacion(1):
        p = db.get(PosicionOC, d["pos"][1])  # la del prepack (sin factura)
        db.delete(p)
        try:
            db.flush()
            print("\nBORRAR POSICION: se borró sin error")
        except IntegrityError as e:
            print("\nBORRAR POSICION: IntegrityError", str(e.orig)[:120])
        db.rollback()


def test_cantidad_a_mano_en_tipo_por_unidad(interno, d):
    t = _trabajo(interno, "OC", {"oc_ids": [d["oc_a"]], "tipos": [d["t_lin"]]})
    r0 = t["registros"][0]
    v = interno.patch(f"/etiquetas/trabajos/{t['id']}", {"parametros": {"cantidades": {r0["clave"]: 5}}, "version": t["version"]})
    assert v.status_code == 200, v.text
    v = interno.post(f"/etiquetas/trabajos/{t['id']}/validar").json()
    r1 = next(r for r in v["registros"] if r["clave"] == r0["clave"])
    print(f"\nCANTIDAD A MANO (POR_UNIDAD): antes={r0['cantidad']} escrita=5 después de validar={r1['cantidad']} total={v['total']}")


def test_reempacar_despues_de_generar(interno, d):
    from app.modelos import GeneracionItem, GrupoCajas, GrupoCajasItem, PackingList
    with SessionLocal() as db, en_organizacion(1):
        pl = db.get(PackingList, d["pl"])
        pl.estado = "FINALIZADO"
        db.commit()
    t = _trabajo(interno, "PACKING", {"pl_id": d["pl"], "tipos": [d["t_caja"]]})
    g = interno.post(f"/etiquetas/trabajos/{t['id']}/generar", {"aceptar_advertencias": True})
    assert g.status_code == 200, g.text
    gen_id = g.json()["ejecuciones"][0]["id"]
    # Reempacar: se quita la caja y se crea otra igual (lo que hace la pantalla al rehacer el árbol)
    with SessionLocal() as db, en_organizacion(1):
        pl = db.get(PackingList, d["pl"])
        viejo = pl.grupos[0]
        items = [(it.pl_linea_id, it.cantidad_por_caja) for it in viejo.items]
        tipo_id = viejo.tipo_empaque_id
        pl.grupos.remove(viejo)
        db.flush()
        nuevo = GrupoCajas(pl_id=pl.id, num_cajas=2, tipo_empaque_id=tipo_id)
        db.add(nuevo)
        db.flush()
        db.add_all([GrupoCajasItem(grupo_id=nuevo.id, pl_linea_id=a, cantidad_por_caja=b) for a, b in items])
        db.commit()
        its = db.scalars(select(GeneracionItem).where(GeneracionItem.generacion_id == gen_id)).all()
        print("\nITEMS generados tras reempacar (grupo_cajas_id, bulto_indice, posicion_id):",
              [(i.grupo_cajas_id, i.bulto_indice, i.posicion_id) for i in its])
    t2 = _trabajo(interno, "PACKING", {"pl_id": d["pl"], "tipos": [d["t_caja"]]})
    print("NUEVO TRABAJO tras reempacar:", [(r["clave"], [p["codigo"] for p in r["problemas"]]) for r in t2["registros"]])
