"""Estructura física del PL: pesos acumulados, volumen exterior y validaciones."""
from app.models import (
    Articulo,
    FacturaLinea,
    GrupoCajas,
    GrupoCajasItem,
    PackingList,
    PLLinea,
    PosicionOC,
    TipoEmpaque,
)
from app.services import empaques


def _linea(peso, talla="8", estilo="X1", oc="OC1"):
    art = Articulo(sku=f"A{talla}", estilo=estilo, talla=talla, unidad="PAR", tipo="SOLIDO", peso_unitario=peso)
    fl = FacturaLinea(posicion_oc=PosicionOC(articulo=art), cantidad=0, estilo=estilo, talla=talla, oc_numero=oc,
                      codigo_sap=f"A{talla}", unidad="PAR", color="BLK")
    return PLLinea(factura_linea=fl, cantidad=0)


def _tipos():
    pack = TipoEmpaque(codigo="PACK", nombre="Pack", nivel=1, prefijo="PK", cuenta_como="INTERIOR", tara=0.1)
    caja = TipoEmpaque(codigo="CAJA", nombre="Caja", nivel=2, prefijo="C", cuenta_como="BULTO", tara=0.7,
                       largo=60, ancho=40, alto=40, peso_max=30, max_contenido=3)
    pallet = TipoEmpaque(codigo="PALLET", nombre="Pallet", nivel=3, prefijo="P", cuenta_como="SOPORTE", tara=20,
                         contiene_productos=False)
    caja.contiene = [pack]
    pallet.contiene = [caja]
    for t in (pack, caja, pallet):
        t.activo = True
        for c in ("contiene_productos", "mezcla_productos", "mezcla_tallas", "mezcla_oc"):
            if getattr(t, c) is None:
                setattr(t, c, True)
    return pack, caja, pallet


def _pl():
    """Pallet P1 → 10 cajas → 3 packs por caja → producto. Por caja: 10 kg de
    producto, 3 packs de 0.1 kg y la caja de 0.7 kg = 11 kg."""
    pack, caja, pallet = _tipos()
    pl = PackingList(numero="PL-T")
    pll = _linea(peso=1.0)
    p = GrupoCajas(num_cajas=1, tipo_empaque=pallet, tara=20, largo=120, ancho=100, alto=160)
    c = GrupoCajas(num_cajas=10, tipo_empaque=caja, tara=0.7, largo=60, ancho=40, alto=40, padre=p)
    k1 = GrupoCajas(num_cajas=20, tipo_empaque=pack, tara=0.1, padre=c)  # 2 packs de 4 pares por caja
    k1.items.append(GrupoCajasItem(pl_linea=pll, cantidad_por_caja=4))
    k2 = GrupoCajas(num_cajas=10, tipo_empaque=pack, tara=0.1, padre=c)  # 1 pack de 2 pares por caja
    k2.items.append(GrupoCajasItem(pl_linea=pll, cantidad_por_caja=2))
    pl.grupos.extend([p, c, k1, k2])
    for i, g in enumerate(pl.grupos, 1):
        g.id = i
    return pl, pll, (p, c, k1, k2)


def test_pesos_acumulados_de_abajo_hacia_arriba():
    pl, pll, (p, c, k1, k2) = _pl()
    empaques.recalcular(pl)
    assert k1.peso_neto_caja == 4 and abs(k1.peso_bruto_caja - 4.1) < 1e-9
    assert c.peso_neto_caja == 10 and abs(c.peso_bruto_caja - 11) < 1e-9  # 10 + 0.3 + 0.7
    assert p.peso_neto_caja == 100 and abs(p.peso_bruto_caja - 130) < 1e-9  # 10 × 11 + 20
    t = empaques.totales(pl)
    assert t["peso_neto"] == 100 and t["peso_bruto"] == 130
    # El volumen es el exterior del pallet, no la suma de las cajas
    assert t["cbm"] == 1.92 and t["bultos"] == 10 and t["soportes"] == 1
    # Contenido de una caja: 10 pares (8 en dos packs + 2 en uno)
    assert empaques.contenido(pl, c) == [(pll, 10)]
    assert empaques.contenido(pl, p) == [(pll, 100)]


def test_numeracion_por_tipo_y_validaciones():
    pl, _, (p, c, k1, k2) = _pl()
    empaques.recalcular(pl)
    r = empaques.numeracion(pl)
    assert empaques.rango_txt(pl, p, r) == "P1" and empaques.rango_txt(pl, c, r) == "C1–C10"
    assert empaques.rango_txt(pl, k1, r) == "PK1–PK20" and empaques.rango_txt(pl, k2, r) == "PK21–PK30"
    assert empaques.validar(pl, r) == []
    # Capacidad: la caja admite 3 packs; con 4 por caja se rechaza
    k2.num_cajas = 20
    errores = [e["mensaje"] for e in empaques.validar(pl)]
    assert any("maximum is 3" in m for m in errores)
    k2.num_cajas = 10
    # Peso máximo de la caja (30 kg)
    k1.items[0].cantidad_por_caja = 20
    empaques.recalcular(pl)
    assert any("maximum is 30 kg" in e["mensaje"] for e in empaques.validar(pl))
    # Reparto exacto y tipos permitidos: 15 cajas no se reparten en 2 pallets; una caja no va en un pack
    k1.items[0].cantidad_por_caja = 4
    p.num_cajas = 3
    assert any("split evenly" in e["mensaje"] for e in empaques.validar(pl))
    p.num_cajas = 1
    k1.padre = k2
    assert any("cannot contain" in e["mensaje"] for e in empaques.validar(pl))


def test_sin_peso_del_articulo_el_neto_se_escribe():
    pl, pll, (p, c, k1, k2) = _pl()
    pll.factura_linea.posicion_oc.articulo.peso_unitario = None
    empaques.recalcular(pl)
    assert k1.peso_neto_caja is None and c.peso_bruto_caja is None and empaques.totales(pl)["sin_peso"] == 1
    k1.neto_manual, k2.neto_manual = 4, 2
    empaques.recalcular(pl)
    assert c.peso_neto_caja == 10 and abs(p.peso_bruto_caja - 130) < 1e-9


def test_prepack_pesa_lo_que_sus_solidos():
    from app.models import Prepack, PrepackComponente

    s7 = Articulo(sku="S7", peso_unitario=0.8)
    s8 = Articulo(sku="S8", peso_unitario=0.9)
    pp = Prepack(codigo="AD09", componentes=[PrepackComponente(articulo=s7, cantidad=6),
                                              PrepackComponente(articulo=s8, cantidad=2)])
    art = Articulo(sku="PP", tipo="PREPACK", prepack=pp)
    assert empaques.peso_articulo(art) == 6.6
