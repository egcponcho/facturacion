"""Compara la numeración de cajas del packing list (empaque) con la de las etiquetas (etiquetado), en memoria."""
import os, sys, tempfile
d = tempfile.mkdtemp()
os.environ.setdefault("DATABASE_URL", f"sqlite:///{d}/x.db")
sys.path.insert(0, "/home/user/facturacion/backend")
from app.modelos import PackingList, GrupoCajas, TipoEmpaque, Factura
from app.modulos.empaque import empaques
from app.modulos.etiquetado import campos

pal = TipoEmpaque(id=1, codigo="PALLET", nombre="Pallet", prefijo="P", cuenta_como="SOPORTE", nivel=3)
caj = TipoEmpaque(id=2, codigo="CAJA", nombre="Caja", prefijo="C", cuenta_como="BULTO", nivel=2)
sin = TipoEmpaque(id=3, codigo="BOLSA", nombre="Bolsa", prefijo=None, cuenta_como="BULTO", nivel=2)
pl = PackingList(id=1, numero="PL-001")
pl.factura = Factura(numero="F-1")
g10 = GrupoCajas(id=10, num_cajas=1, tipo_empaque=pal, tipo_empaque_id=1)
g11 = GrupoCajas(id=11, num_cajas=2, tipo_empaque=caj, tipo_empaque_id=2)
g12 = GrupoCajas(id=12, num_cajas=3, tipo_empaque=caj, tipo_empaque_id=2)
g13 = GrupoCajas(id=13, num_cajas=2, tipo_empaque=sin, tipo_empaque_id=3)
g12.padre = g10; g12.padre_id = 10
pl.grupos = [g10, g11, g12, g13]
r = empaques.numeracion(pl)
print("EMPAQUE (documento PL):", {g.id: empaques.rango_txt(pl, g, r) for g in pl.grupos})
print("EMPAQUE totales.bultos:", empaques.totales(pl)["bultos"])
for nivel in (2, 3):
    us = campos.unidades_pl(pl, nivel)
    print(f"ETIQUETADO nivel tipo {nivel}:", [(u.grupo_id, u.valores["bulto.codigo"], f"{u.numero}/{u.total}") for u in us])
us = campos.unidades_pl(pl, superiores=True)
print("ETIQUETADO superiores:", [(u.grupo_id, u.valores["bulto.codigo"], f"{u.numero}/{u.total}") for u in us])
print("ETIQUETADO pl.bultos:", campos.valores_pl(pl)["pl.bultos"])
