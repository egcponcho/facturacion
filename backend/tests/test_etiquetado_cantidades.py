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
