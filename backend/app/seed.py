"""Datos de demostración. Se cargan solo si la base está vacía.
Uso manual: python -m app.seed"""
from datetime import date, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import (
    Embarque,
    EventoEmbarque,
    Factura,
    FacturaLinea,
    GrupoCajas,
    GrupoCajasItem,
    OrdenCompra,
    PackingList,
    PlantillaCaja,
    PLLinea,
    PosicionOC,
    Proveedor,
    UnidadCarga,
    Usuario,
)
from .security import hash_password
from .services.common import registrar


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


def _momento(d: date, hora: int = 10) -> datetime:
    return datetime.combine(d, time(hora))


def _factura_historica(db, usuario, oc, numero, fecha, plantillas, unidad=None):
    """Factura ya cerrada: todas las posiciones de la OC, un PL finalizado con
    sus cajas y, si se indica, confirmado en una unidad de carga."""
    ts = _momento(fecha)
    f = Factura(proveedor_id=oc.proveedor_id, numero=numero, fecha=fecha, moneda=oc.moneda, incoterm=oc.incoterm,
                sociedad=oc.sociedad, centro=oc.centro, pais_destino=oc.pais_destino, estado="FINALIZADA",
                version=1, creado_por=usuario.id, creado_en=ts - timedelta(days=2), actualizado_en=ts,
                finalizado_en=ts)
    pl = PackingList(numero="PL-001", estado="FINALIZADO", version=1, creado_en=ts, actualizado_en=ts,
                     unidad=unidad, asignacion="CONFIRMADA" if unidad else None)
    f.packing_lists.append(pl)
    for p in oc.posiciones:
        linea = FacturaLinea(posicion_oc=p, cantidad=p.cantidad, precio_unitario=p.precio, precio_oc=p.precio,
                             oc_numero=oc.numero, posicion=p.posicion, codigo_sap=p.codigo_sap, upc=p.upc,
                             estilo=p.estilo, color=p.color, talla=p.talla, descripcion=p.descripcion,
                             unidad=p.unidad, pais_origen=p.pais_origen, partida_arancelaria=p.partida_arancelaria,
                             descripcion_comercial=p.descripcion)
        f.lineas.append(linea)
        pll = PLLinea(factura_linea=linea, cantidad=p.cantidad)
        pl.lineas.append(pll)
        t = plantillas[p.estilo]
        g = GrupoCajas(num_cajas=p.cantidad // t.cantidad_por_caja, largo=t.largo, ancho=t.ancho, alto=t.alto,
                       peso_neto_caja=t.peso_neto, peso_bruto_caja=t.peso_bruto, plantilla_id=t.id,
                       plantilla_nombre=t.nombre)
        g.items.append(GrupoCajasItem(pl_linea=pll, cantidad_por_caja=t.cantidad_por_caja))
        pl.grupos.append(g)
    db.add(f)
    db.flush()
    registrar(db, usuario, "factura", f.id, "crear", {"lineas": len(f.lineas), "ocs": [oc.numero]}, factura_id=f.id)
    registrar(db, usuario, "packing_list", pl.id, "aplicar_plantilla", {"plantillas": sorted(
        {plantillas[p.estilo].nombre for p in oc.posiciones})}, factura_id=f.id)
    registrar(db, usuario, "factura", f.id, "finalizar", {"con_pl": [pl.numero]}, factura_id=f.id)
    return f


def _historial_demo(db, hoy, tnf, vans, usuarios, plantillas):
    """Meses anteriores ya facturados y embarcados, para que el tablero tenga
    historia: un contenedor recibido, otro en tránsito y una factura lista
    para embarcar."""
    recibido = Embarque(codigo="EMB-0001", tipo_transporte="MARITIMO", modalidad="FCL", transportista="Naviera demo",
                        documento_numero="MAEU 221877310", puerto_origen="Cai Mep (VN)", puerto_destino="Colón (PA)",
                        etd=hoy - timedelta(days=88), eta=hoy - timedelta(days=58),
                        salida_real=hoy - timedelta(days=87), arribo_real=hoy - timedelta(days=57), estado="RECIBIDO")
    c1 = UnidadCarga(tipo="40HC", etiqueta="40HC #1", numero="MSKU 481220-7", sello="ML-99812")
    recibido.unidades.append(c1)
    for tipo, dias in (("SALIDA", 87), ("ARRIBO", 57), ("ENTREGA", 55), ("RECEPCION", 54)):
        recibido.eventos.append(EventoEmbarque(tipo=tipo, fecha=_momento(hoy - timedelta(days=dias), 9),
                                               ubicacion="Colón (PA)" if tipo != "SALIDA" else "Cai Mep (VN)"))
    transito = Embarque(codigo="EMB-0002", tipo_transporte="MARITIMO", modalidad="FCL", transportista="Naviera demo",
                        documento_numero="COSU 640018225", puerto_origen="Yantian (CN)", puerto_destino="Colón (PA)",
                        etd=hoy - timedelta(days=19), eta=hoy + timedelta(days=9),
                        salida_real=hoy - timedelta(days=18), estado="EN_TRANSITO")
    c2 = UnidadCarga(tipo="40GP", etiqueta="40GP #1", numero="TGHU 772104-3", sello="CS-10442")
    transito.unidades.append(c2)
    transito.eventos.append(EventoEmbarque(tipo="SALIDA", fecha=_momento(hoy - timedelta(days=18), 7),
                                           ubicacion="Yantian (CN)"))
    transito.eventos.append(EventoEmbarque(tipo="TRANSITO", fecha=_momento(hoy - timedelta(days=6), 12),
                                           ubicacion="Canal de Panamá, lado Pacífico",
                                           observacion="Sin novedad"))
    db.add_all([recibido, transito])

    u_tnf, u_vans = usuarios
    ocs = [
        (tnf, "4500011870", 140, [("NF0A5GLL", "JK3 TNF Black", "UN", 48.50, "VN", "6201.40",
                                    "Chaqueta impermeable hombre", [("M", 50), ("L", 50)])], "TNF-2026-0418", 128, c1),
        (tnf, "4500011902", 115, [("NF0A3VY2", "JK3 TNF Black", "UN", 31.20, "ID", "4202.92", "Mochila 28 L",
                                    [("OS", 80)])], "TNF-2026-0502", 100, c1),
        (vans, "4500019950", 110, [("VN000EE3", "BLK Negro", "PAR", 25.50, "VN", "6404.19", "Calzado lona clásico",
                                     [("8", 60)])], "VN-88120", 95, c1),
        (tnf, "4500011944", 85, [("NF0A7W4G", "KX7 Negro", "PAR", 62.00, "CN", "6404.11", "Calzado trail running",
                                   [("9", 36), ("10", 48)])], "TNF-2026-0611", 70, c2),
        (vans, "4500019988", 50, [("VN000EE3", "BLK Negro", "PAR", 25.50, "VN", "6404.19", "Calzado lona clásico",
                                    [("9", 72)])], "VN-88177", 35, c2),
        (tnf, "4500011990", 20, [("NF0A5IHO", "Gris melange", "UN", 22.75, "KH", "6110.30",
                                   "Fleece medio cierre", [("S", 30), ("M", 30)])], "TNF-2026-0915", 6, None),
    ]
    for prov, numero, dias_oc, grupos, factura, dias_factura, unidad in ocs:
        oc = _oc(db, prov, numero, "PA10", hoy - timedelta(days=dias_oc), grupos)
        usuario = u_tnf if prov is tnf else u_vans
        f = _factura_historica(db, usuario, oc, factura, hoy - timedelta(days=dias_factura), plantillas, unidad)
        if unidad:
            registrar(db, usuario, "packing_list", f.packing_lists[0].id, "asignar_unidad",
                      {"unidad": unidad.numero, "embarque": unidad.embarque.codigo, "modo": "CONFIRMADA"},
                      factura_id=f.id)


def seed(db: Session) -> None:
    if db.scalar(select(func.count(Usuario.id))):
        return
    tnf = Proveedor(codigo="TNF", nombre="The North Face")
    vans = Proveedor(codigo="VANS", nombre="Vans")
    db.add_all([tnf, vans])
    db.flush()
    pw = hash_password("demo123")
    u_tnf = Usuario(email="tnf@demo.com", nombre="Proveedor TNF", rol="proveedor", proveedor_id=tnf.id,
                    password_hash=pw)
    u_vans = Usuario(email="vans@demo.com", nombre="Proveedor Vans", rol="proveedor", proveedor_id=vans.id,
                     password_hash=pw)
    db.add_all([
        Usuario(email="admin@demo.com", nombre="Administrador", rol="admin", password_hash=pw),
        Usuario(email="interno@demo.com", nombre="Equipo de importaciones", rol="interno", password_hash=pw),
        u_tnf,
        u_vans,
    ])
    db.flush()
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
    chaqueta = PlantillaCaja(proveedor_id=tnf.id, nombre="Caja chaqueta 10 un", cantidad_por_caja=10, unidad="UN",
                             largo=60, ancho=40, alto=40, peso_neto=9.0, peso_bruto=10.2, tara=1.2)
    calzado = PlantillaCaja(proveedor_id=tnf.id, nombre="Caja calzado 12 pares", cantidad_por_caja=12, unidad="PAR",
                            largo=55, ancho=35, alto=33, peso_neto=10.8, peso_bruto=12.3, tara=1.5)
    mochila = PlantillaCaja(proveedor_id=tnf.id, nombre="Caja mochila 20 un", cantidad_por_caja=20, unidad="UN",
                            largo=70, ancho=50, alto=45, peso_neto=16.0, peso_bruto=17.5, tara=1.5)
    fleece = PlantillaCaja(proveedor_id=tnf.id, nombre="Caja fleece 15 un", cantidad_por_caja=15, unidad="UN",
                           largo=60, ancho=40, alto=35, peso_neto=7.5, peso_bruto=8.6, tara=1.1)
    master12 = PlantillaCaja(proveedor_id=vans.id, nombre="Master 12 pares", cantidad_por_caja=12, unidad="PAR",
                             largo=60, ancho=38, alto=35, peso_neto=9.6, peso_bruto=11.0, tara=1.4)
    master10 = PlantillaCaja(proveedor_id=vans.id, nombre="Master 10 pares", cantidad_por_caja=10, unidad="PAR",
                             largo=55, ancho=38, alto=32, peso_neto=8.0, peso_bruto=9.2, tara=1.2)
    db.add_all([chaqueta, calzado, mochila, fleece, master12, master10])
    db.flush()
    _historial_demo(db, hoy, tnf, vans, (u_tnf, u_vans), {
        "NF0A5GLL": chaqueta, "NF0A3VY2": mochila, "NF0A7W4G": calzado, "NF0A5IHO": fleece, "VN000EE3": master12})
    e = Embarque(codigo="EMB-0003", tipo_transporte="MARITIMO", modalidad="FCL", transportista="Naviera demo",
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
