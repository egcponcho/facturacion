"""Lo que se imprime coincide con lo que se pidió y con los documentos:

- la cantidad escrita a mano para un registro manda sobre la calculada (en cualquier tipo, no
  solo en MANUAL), queda como advertencia y es la que se genera;
- el código de cada caja en la etiqueta (C3, P1…) es el mismo del documento de la lista de
  empaque, con el mismo prefijo y el mismo orden (auditoría del etiquetado, I-01)."""
from etiquetado_util import aprobada, generado, oc_con_articulos, problemas, tipo, trabajo, uso

from app.modelos import Factura, GrupoCajas, PackingList, TipoEmpaque
from app.modulos.empaque import empaques
from app.modulos.etiquetado import campos

SKU = [{"id": "s", "tipo": "texto", "contenido": "{{articulo.sku}}", "x": 3, "y": 3, "w": 90, "h": 10}]


def _baja(interno, t_, u):
    interno.post(f"/etiquetas/usos/{u['id']}/baja", {"motivo": "Test done"})
    version = next(x for x in interno.get("/etiquetas/tipos", params={"todos": True}).json() if x["id"] == t_["id"])["version"]
    interno.patch(f"/etiquetas/tipos/{t_['id']}", {"activo": False, "version": version})


def test_la_cantidad_escrita_manda_sobre_la_calculada(interno, admin):
    datos = oc_con_articulos(interno)
    linea = datos["lineas"][0]
    t_ = tipo(interno, "CANT_A_MANO", cantidad="POR_UNIDAD")
    u = uso(interno, t_["id"], aprobada(interno, admin, "By hand", t_["id"], SKU)["id"])
    try:
        tr = trabajo(interno, "OC", {"oc_ids": [datos["oc"]["id"]], "posiciones": [linea["id"]], "tipos": [t_["id"]]})
        (r,) = [x for x in tr["registros"] if x["tipo_etiqueta_id"] == t_["id"]]
        calculada = r["cantidad"]
        assert calculada == int(float(linea["cantidad"])) and "cantidad_a_mano" not in problemas(r)
        escrita = calculada + 3
        cambio = interno.patch(f"/etiquetas/trabajos/{tr['id']}", {"parametros": {"cantidades": {r["clave"]: escrita}},
                                                                   "version": tr["version"]})
        assert cambio.status_code == 200, cambio.text
        tr = interno.post(f"/etiquetas/trabajos/{tr['id']}/validar").json()
        (r,) = [x for x in tr["registros"] if x["tipo_etiqueta_id"] == t_["id"]]
        assert r["cantidad"] == escrita and "cantidad_a_mano" in problemas(r)
        aviso = next(p for p in r["problemas"] if p["codigo"] == "cantidad_a_mano")
        assert str(calculada) in aviso["mensaje"] and aviso["nivel"] == "advertencia"
        # Se genera lo escrito, no lo calculado
        tr = generado(interno, tr)
        assert tr["ejecuciones"][-1]["total"] == escrita
    finally:
        _baja(interno, t_, u)


def test_el_codigo_de_caja_de_la_etiqueta_es_el_del_packing_list():
    pal = TipoEmpaque(id=1, codigo="PALLET", nombre="Pallet", prefijo="P", cuenta_como="SOPORTE", nivel=3)
    caja = TipoEmpaque(id=2, codigo="CAJA", nombre="Caja", prefijo="C", cuenta_como="BULTO", nivel=2)
    bolsa = TipoEmpaque(id=3, codigo="BOLSA", nombre="Bolsa", prefijo=None, cuenta_como="BULTO", nivel=2)
    pl = PackingList(id=1, numero="PL-001")
    pl.factura = Factura(numero="F-1")
    pallet = GrupoCajas(id=10, num_cajas=1, tipo_empaque=pal, tipo_empaque_id=1)
    sueltas = GrupoCajas(id=11, num_cajas=2, tipo_empaque=caja, tipo_empaque_id=2)
    en_pallet = GrupoCajas(id=12, num_cajas=3, tipo_empaque=caja, tipo_empaque_id=2, padre=pallet, padre_id=10)
    bolsas = GrupoCajas(id=13, num_cajas=2, tipo_empaque=bolsa, tipo_empaque_id=3)
    pl.grupos = [pallet, sueltas, en_pallet, bolsas]
    # El documento numera en orden del árbol: el pallet y sus cajas primero (C1–C3), luego las sueltas (C4–C5);
    # un tipo sin prefijo usa el comienzo de su código
    rangos = empaques.numeracion(pl)
    documento = {g.id: [f"{empaques.prefijo(g)}{n}" for n in range(rangos[g.id][0], rangos[g.id][1] + 1)] for g in pl.grupos}
    assert documento == {10: ["P1"], 11: ["C4", "C5"], 12: ["C1", "C2", "C3"], 13: ["BO1", "BO2"]}
    etiquetas: dict = {}
    for nivel in (2, 3):
        for u in campos.unidades_pl(pl, nivel):
            etiquetas.setdefault(u.grupo_id, []).append(u.valores["bulto.codigo"])
    for u in campos.unidades_pl(pl, superiores=True):
        etiquetas.setdefault(u.grupo_id, [])
        if u.valores["bulto.codigo"] not in etiquetas[u.grupo_id]:
            etiquetas[u.grupo_id].append(u.valores["bulto.codigo"])
    assert etiquetas == documento
    # Las cajas del pallet dicen en qué pallet van
    assert {u.valores["bulto.contenedor"] for u in campos.unidades_pl(pl, 2) if u.grupo_id == 12} == {"P1"}


def _dos_ocs_en_las_mismas_cajas():
    """Dos OCs del mismo proveedor cuyas líneas van juntas en un grupo de 2 cajas de una lista de empaque."""
    from sqlalchemy import select

    from app.core.db import SessionLocal
    from app.core.organizacion import en_organizacion
    from app.modelos import Articulo, FacturaLinea, GrupoCajasItem, OrdenCompra, PLLinea, PosicionOC

    with SessionLocal() as db, en_organizacion(1):
        art = db.scalar(select(Articulo).where(Articulo.tipo == "SOLIDO", Articulo.proveedor_id.is_not(None)).limit(1))
        base = db.scalar(select(OrdenCompra).where(OrdenCompra.proveedor_id == art.proveedor_id).limit(1))
        ocs, lineas = [], []
        for numero in ("CAJA-COMP-A", "CAJA-COMP-B"):
            oc = OrdenCompra(proveedor_id=art.proveedor_id, numero=numero, sociedad=base.sociedad, centro=base.centro,
                             centro_destino=base.centro_destino, moneda=base.moneda, estado="APROBADA",
                             liberacion_comercial=base.liberacion_comercial, liberacion_logistica=base.liberacion_logistica)
            db.add(oc)
            db.flush()
            p = PosicionOC(oc_id=oc.id, posicion="10", articulo_id=art.id, codigo_articulo=art.sku, cantidad=12, unidad="PAR")
            db.add(p)
            db.flush()
            ocs.append(oc.id)
            lineas.append((oc, p))
        f = Factura(proveedor_id=art.proveedor_id, moneda=base.moneda or "USD", sociedad=base.sociedad or "1000", estado="BORRADOR")
        db.add(f)
        db.flush()
        pl = PackingList(factura_id=f.id, numero="PL-COMP", estado="BORRADOR")
        db.add(pl)
        db.flush()
        g = GrupoCajas(pl_id=pl.id, num_cajas=2, tipo_empaque_id=db.scalar(select(TipoEmpaque.id).where(
            TipoEmpaque.cuenta_como == "BULTO", TipoEmpaque.activo.is_(True)).limit(1)))
        db.add(g)
        db.flush()
        for oc, p in lineas:
            fl = FacturaLinea(factura_id=f.id, posicion_oc_id=p.id, cantidad=12, precio_unitario=1, precio_oc=1,
                              oc_numero=oc.numero, posicion=p.posicion, codigo_articulo=p.codigo_articulo, unidad=p.unidad)
            db.add(fl)
            db.flush()
            pll = PLLinea(pl_id=pl.id, factura_linea_id=fl.id, cantidad=12)
            db.add(pll)
            db.flush()
            db.add(GrupoCajasItem(grupo_id=g.id, pl_linea_id=pll.id, cantidad_por_caja=6))
        db.commit()
        return ocs


def test_una_caja_compartida_por_dos_ocs_lleva_una_sola_etiqueta(interno, admin):
    ocs = _dos_ocs_en_las_mismas_cajas()
    t_ = tipo(interno, "CAJA_COMP", sujeto="BULTO", cantidad="POR_BULTO")
    u = uso(interno, t_["id"], aprobada(interno, admin, "Shared box", t_["id"],
                                        [{"id": "p", "tipo": "campo", "campo": "bulto.codigo", "x": 2, "y": 2, "w": 50, "h": 8}])["id"])
    try:
        tr = trabajo(interno, "OC", {"oc_ids": ocs, "tipos": [t_["id"]], "prueba": True})
        cajas = [r for r in tr["registros"] if r["tipo_etiqueta_id"] == t_["id"]]
        # Dos cajas físicas: dos etiquetas, aunque cada una lleve líneas de las dos OCs
        assert len(cajas) == 2 and sum(r["cantidad"] for r in cajas) == 2, [r["clave"] for r in cajas]
        avisos = tr["resumen"].get("problemas", []) + tr["resumen"].get("avisos", [])
        assert sum(1 for p in avisos if p.get("codigo") == "bulto_compartido") == 2
    finally:
        _baja(interno, t_, u)
