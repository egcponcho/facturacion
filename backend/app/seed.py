"""Datos de demostración. Se cargan solo si la base está vacía.
Uso manual: python -m app.seed"""
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import (
    Embarque,
    OrdenCompra,
    PlantillaCaja,
    PosicionOC,
    Proveedor,
    UnidadCarga,
    Usuario,
)
from .security import hash_password


def _oc(db, prov, numero, centro, fecha, grupos):
    oc = OrdenCompra(proveedor_id=prov.id, numero=numero, sociedad="8000", centro=centro,
                     pais_destino="PA", moneda="USD", incoterm="FOB", fecha=fecha, liberada=True)
    db.add(oc)
    pos = 10
    for estilo, color, unidad, precio, origen, partida, desc, tallas in grupos:
        for talla, cantidad in tallas:
            sap = f"{int(numero[-4:]) * 1000 + pos:018d}"
            oc.posiciones.append(PosicionOC(
                posicion=f"{pos:05d}", codigo_sap=sap, upc=f"0196{int(sap) % 10**8:08d}",
                estilo=estilo, color=color, talla=talla, descripcion=desc, cantidad=cantidad,
                unidad=unidad, precio=precio, fecha_entrega=fecha + timedelta(days=45),
                pais_origen=origen, partida_arancelaria=partida,
            ))
            pos += 10
    return oc


def seed(db: Session) -> None:
    if db.scalar(select(func.count(Usuario.id))):
        return
    tnf = Proveedor(codigo="TNF", nombre="The North Face")
    vans = Proveedor(codigo="VANS", nombre="Vans")
    db.add_all([tnf, vans])
    db.flush()
    pw = hash_password("demo123")
    db.add_all([
        Usuario(email="admin@demo.com", nombre="Administrador", rol="admin", password_hash=pw),
        Usuario(email="interno@demo.com", nombre="Equipo de importaciones", rol="interno", password_hash=pw),
        Usuario(email="tnf@demo.com", nombre="Proveedor TNF", rol="proveedor", proveedor_id=tnf.id, password_hash=pw),
        Usuario(email="vans@demo.com", nombre="Proveedor Vans", rol="proveedor", proveedor_id=vans.id, password_hash=pw),
    ])
    hoy = date.today()
    _oc(db, tnf, "4500012345", "PA10", hoy - timedelta(days=20), [
        ("NF0A5GLL", "JK3 TNF Black", "UN", 48.50, "VN", "6201.40", "Chaqueta impermeable hombre",
         [("S", 40), ("M", 60), ("L", 60), ("XL", 27), ("XXL", 20)]),
        ("NF0A7W4G", "KX7 Negro", "PAR", 62.00, "CN", "6404.11", "Calzado trail running",
         [("8", 24), ("9", 36), ("10", 50), ("11", 36), ("12", 12)]),
    ])
    _oc(db, tnf, "4500012346", "PA10", hoy - timedelta(days=12), [
        ("NF0A3VY2", "JK3 TNF Black", "UN", 31.20, "ID", "4202.92", "Mochila 28 L",
         [("OS", 120)]),
        ("NF0A5IHO", "Gris melange", "UN", 22.75, "KH", "6110.30", "Fleece medio cierre",
         [("S", 30), ("M", 30), ("L", 30)]),
    ])
    _oc(db, tnf, "4500012350", "PA20", hoy - timedelta(days=8), [
        ("NF0A5GLL", "Azul summit", "UN", 48.50, "VN", "6201.40", "Chaqueta impermeable hombre",
         [("M", 30), ("L", 30)]),
    ])
    _oc(db, vans, "4500020001", "PA10", hoy - timedelta(days=15), [
        ("VN000EE3", "BLK Negro", "PAR", 25.50, "VN", "6404.19", "Calzado lona clásico",
         [("7", 36), ("8", 48), ("9", 60), ("10", 48), ("11", 24)]),
    ])
    _oc(db, vans, "4500020002", "PA10", hoy - timedelta(days=5), [
        ("VN0A4BV4", "Blanco", "PAR", 21.00, "CN", "6404.19", "Calzado lona básico",
         [("7", 24), ("8", 24), ("9", 24), ("10", 24)]),
    ])
    db.add_all([
        PlantillaCaja(proveedor_id=tnf.id, nombre="Caja chaqueta 10 un", cantidad_por_caja=10, unidad="UN",
                      largo=60, ancho=40, alto=40, peso_neto=9.0, peso_bruto=10.2, tara=1.2),
        PlantillaCaja(proveedor_id=tnf.id, nombre="Caja calzado 12 pares", cantidad_por_caja=12, unidad="PAR",
                      largo=55, ancho=35, alto=33, peso_neto=10.8, peso_bruto=12.3, tara=1.5),
        PlantillaCaja(proveedor_id=tnf.id, nombre="Caja mochila 20 un", cantidad_por_caja=20, unidad="UN",
                      largo=70, ancho=50, alto=45, peso_neto=16.0, peso_bruto=17.5, tara=1.5),
        PlantillaCaja(proveedor_id=vans.id, nombre="Master 12 pares", cantidad_por_caja=12, unidad="PAR",
                      largo=60, ancho=38, alto=35, peso_neto=9.6, peso_bruto=11.0, tara=1.4),
        PlantillaCaja(proveedor_id=vans.id, nombre="Master 10 pares", cantidad_por_caja=10, unidad="PAR",
                      largo=55, ancho=38, alto=32, peso_neto=8.0, peso_bruto=9.2, tara=1.2),
    ])
    e = Embarque(codigo="EMB-0001", tipo_transporte="MARITIMO", modalidad="FCL", transportista="Naviera demo",
                 puerto_origen="Cai Mep (VN)", puerto_destino="Colón (PA)",
                 etd=hoy + timedelta(days=12), eta=hoy + timedelta(days=42))
    e.unidades.append(UnidadCarga(tipo="40HC", etiqueta="40HC #1"))
    db.add(e)
    db.commit()


if __name__ == "__main__":
    from .db import Base, SessionLocal, engine

    Base.metadata.create_all(engine)
    with SessionLocal() as s:
        seed(s)
    print("Datos de demostración cargados.")
