"""Datos de demostración. Se cargan solo si la base está vacía.
Uso manual: python -m app.seed"""
from datetime import date, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import (
    Almacen,
    Articulo,
    Centro,
    Embarque,
    EventoEmbarque,
    Factura,
    FacturaLinea,
    GrupoArticulo,
    GrupoCajas,
    GrupoCajasItem,
    Marca,
    OrdenCompra,
    PackingList,
    Pais,
    PaisDestino,
    PlantillaCaja,
    PLLinea,
    PosicionOC,
    Prepack,
    PrepackComponente,
    Proveedor,
    Puerto,
    Sociedad,
    UnidadCarga,
    Usuario,
)
from .security import hash_password
from .services.common import registrar

PAISES = [
    ("VN", "Vietnam"), ("CN", "China"), ("ID", "Indonesia"), ("KH", "Camboya"), ("BD", "Bangladés"),
    ("IN", "India"), ("SV", "El Salvador"), ("PA", "Panamá"), ("GT", "Guatemala"), ("HN", "Honduras"),
    ("CR", "Costa Rica"), ("NI", "Nicaragua"), ("US", "Estados Unidos"), ("MX", "México"), ("BR", "Brasil"),
]
DESTINOS = [
    ("2220", "SV", "El Salvador", "8000"), ("3200", "GT", "Guatemala", "8000"), ("3400", "HN", "Honduras", "8000"),
    ("5580", "NI", "Nicaragua", "8000"), ("5910", "PA", "Panamá", "PA01"), ("1880", "CR", "Costa Rica", "PA01"),
]
PUERTOS = [
    ("VNSGN", "Ho Chi Minh (Cat Lai)", "VN"), ("VNCMT", "Cai Mep", "VN"), ("CNYTN", "Yantian", "CN"),
    ("CNSHA", "Shanghái", "CN"), ("IDJKT", "Yakarta", "ID"), ("KHKOS", "Sihanoukville", "KH"),
    ("SVAQJ", "Acajutla", "SV"), ("PAONX", "Colón (Manzanillo)", "PA"), ("PABLB", "Balboa", "PA"),
    ("GTSTC", "Santo Tomás de Castilla", "GT"),
]
MARCAS = [("TNF", "The North Face"), ("VANS", "Vans"), ("MERR", "Merrell"), ("CAT", "Caterpillar"),
          ("HPU", "Hush Puppies"), ("ADOC", "ADOC")]
GRUPOS = [("CALZ-OUT", "Calzado outdoor", "CALZADO"), ("CALZ-CAS", "Calzado casual", "CALZADO"),
          ("CHAQ", "Chaquetas", "ROPA"), ("FLEE", "Fleece y sudaderas", "ROPA"), ("MOCH", "Mochilas", "ACCESORIO")]
# estilo, color, marca, grupo, proveedor, unidad, precio, origen, partida, descripción, casepack, tallas
ESTILOS = [
    ("NF0A5GLL", "JK3 TNF Black", "TNF", "CHAQ", "TNF", "UN", 48.50, "VN", "6201.40", "Chaqueta impermeable hombre",
     None, ["S", "M", "L", "XL", "XXL"]),
    ("NF0A5GLL", "Azul summit", "TNF", "CHAQ", "TNF", "UN", 48.50, "VN", "6201.40", "Chaqueta impermeable hombre",
     None, ["M", "L"]),
    ("NF0A7W4G", "KX7 Negro", "TNF", "CALZ-OUT", "TNF", "PAR", 62.00, "CN", "6404.11", "Calzado trail running",
     12, ["8", "9", "10", "11", "12"]),
    ("NF0A3VY2", "JK3 TNF Black", "TNF", "MOCH", "TNF", "UN", 31.20, "ID", "4202.92", "Mochila 28 L", 20, ["OS"]),
    ("NF0A5IHO", "Gris melange", "TNF", "FLEE", "TNF", "UN", 22.75, "KH", "6110.30", "Fleece medio cierre",
     None, ["S", "M", "L"]),
    ("VN000EE3", "BLK Negro", "VANS", "CALZ-CAS", "VANS", "PAR", 25.50, "VN", "6404.19", "Calzado lona clásico",
     12, ["7", "8", "9", "10", "11", "12"]),
    ("VN0A4BV4", "Blanco", "VANS", "CALZ-CAS", "VANS", "PAR", 21.00, "CN", "6404.19", "Calzado lona básico",
     12, ["7", "8", "9", "10"]),
]
CURVA_VANS = {"7": 1, "8": 2, "9": 3, "10": 3, "11": 2, "12": 1}  # 12 pares por caja master


def _momento(d: date, hora: int = 10) -> datetime:
    return datetime.combine(d, time(hora))


def _catalogos(db: Session) -> dict:
    db.add_all([Pais(codigo=c, nombre=n) for c, n in PAISES])
    s8000 = Sociedad(codigo="8000", nombre="Operaciones El Salvador", razon_social="Distribuidora de Marcas, S.A. de C.V.",
                     id_fiscal="0614-010190-101-2", pais="SV", moneda="USD", direccion="San Salvador, El Salvador")
    spa01 = Sociedad(codigo="PA01", nombre="Operaciones Panamá", razon_social="Distribuidora de Marcas Panamá, S.A.",
                     id_fiscal="155612345-2-2019", pais="PA", moneda="USD", direccion="Zona Libre de Colón, Panamá")
    db.add_all([s8000, spa01])
    db.flush()
    centros = {
        "8010": Centro(codigo="8010", sociedad_id=s8000.id, nombre="Bodega fiscal San Salvador"),
        "8020": Centro(codigo="8020", sociedad_id=s8000.id, nombre="Bodega fiscal San Bartolo", tipo="ZONA_FRANCA"),
        "PA10": Centro(codigo="PA10", sociedad_id=spa01.id, nombre="Bodega fiscal Zona Libre de Colón", tipo="ZONA_FRANCA"),
        "PA20": Centro(codigo="PA20", sociedad_id=spa01.id, nombre="Bodega fiscal Panamá Pacífico"),
    }
    db.add_all(centros.values())
    db.flush()
    db.add_all([
        Almacen(codigo="BF19", centro_id=centros["8010"].id, nombre="Almacén detalle San Salvador", tipo="DETALLE"),
        Almacen(codigo="BF20", centro_id=centros["8020"].id, nombre="Almacén mayoreo San Bartolo", tipo="MAYOREO"),
        Almacen(codigo="BF01", centro_id=centros["PA10"].id, nombre="Almacén detalle Colón", tipo="DETALLE"),
        Almacen(codigo="BF02", centro_id=centros["PA20"].id, nombre="Almacén mayoreo Panamá Pacífico", tipo="MAYOREO"),
    ])
    soc = {"8000": s8000.id, "PA01": spa01.id}
    db.add_all([PaisDestino(codigo=c, pais=p, nombre=n, sociedad_id=soc[s]) for c, p, n, s in DESTINOS])
    db.add_all([Puerto(codigo=c, nombre=n, pais=p) for c, n, p in PUERTOS])
    marcas = {c: Marca(codigo=c, nombre=n) for c, n in MARCAS}
    grupos = {c: GrupoArticulo(codigo=c, nombre=n, categoria=cat) for c, n, cat in GRUPOS}
    db.add_all([*marcas.values(), *grupos.values()])
    db.flush()
    return {"marcas": marcas, "grupos": grupos}


def _articulos(db: Session, cat: dict, proveedores: dict) -> dict:
    """Maestro de artículos: un SKU por estilo-color-talla y un prepack (curva)."""
    arts = {}
    siguiente = 1_000_000_100
    for estilo, color, marca, grupo, prov, unidad, precio, origen, partida, desc, casepack, tallas in ESTILOS:
        for talla in tallas:
            sku = f"{siguiente:018d}"
            siguiente += 10
            a = Articulo(sku=sku, upc=f"0196{siguiente % 10**8:08d}", estilo=estilo, color=color, talla=talla,
                         descripcion=desc, marca_id=cat["marcas"][marca].id, grupo_id=cat["grupos"][grupo].id,
                         proveedor_id=proveedores[prov].id, unidad=unidad, tipo="SOLIDO", casepack=casepack,
                         partida_arancelaria=partida, pais_origen=origen)
            a.precio_demo = precio
            arts[(estilo, color, talla)] = a
    db.add_all(arts.values())
    db.flush()
    curva = Prepack(codigo="VN-EE3-CRV01", descripcion="Curva VN000EE3 BLK tallas 7-12 (12 pares)")
    for talla, cant in CURVA_VANS.items():
        curva.componentes.append(PrepackComponente(articulo_id=arts[("VN000EE3", "BLK Negro", talla)].id, cantidad=cant))
    db.add(curva)
    db.flush()
    pp = Articulo(sku=f"{siguiente:018d}", estilo="VN000EE3", color="BLK Negro", talla="CRV01",
                  descripcion="Calzado lona clásico, prepack curva 7-12", marca_id=cat["marcas"]["VANS"].id,
                  grupo_id=cat["grupos"]["CALZ-CAS"].id, proveedor_id=proveedores["VANS"].id, unidad="CJ",
                  tipo="PREPACK", prepack_id=curva.id, partida_arancelaria="6404.19", pais_origen="VN")
    pp.precio_demo = 25.50 * 12
    db.add(pp)
    db.flush()
    arts[("VN000EE3", "BLK Negro", "CRV01")] = pp
    return arts


def _oc(db, prov, arts, numero, fecha, lineas, sociedad="8000", centro="8010", almacen="BF19", destino="2220",
        puerto="VNSGN", origen="VN", xf=None, xf_nueva=None, tienda=None, comercial="C", logistica="300"):
    """lineas: [(estilo, color, [(talla, cantidad), ...])]; posiciones de 10 en 10."""
    oc = OrdenCompra(proveedor_id=prov.id, numero=numero, sociedad=sociedad, centro=centro, almacen=almacen,
                     pais_destino=destino, moneda="USD", incoterm="FOB", fecha=fecha, puerto_despacho=puerto,
                     pais_origen=origen, pais_procedencia=origen, fecha_xf_original=xf, fecha_xf=xf_nueva or xf,
                     fecha_tienda=tienda, liberacion_comercial=comercial, liberacion_logistica=logistica,
                     liberada=comercial == "C")
    db.add(oc)
    pos = 10
    for estilo, color, tallas in lineas:
        for talla, cantidad in tallas:
            a = arts[(estilo, color, talla)]
            oc.posiciones.append(PosicionOC(
                posicion=str(pos), articulo_id=a.id, codigo_sap=a.sku, upc=a.upc, estilo=a.estilo, color=a.color,
                talla=a.talla, descripcion=a.descripcion, marca=a.marca.codigo, grupo=a.grupo.codigo,
                categoria=a.grupo.categoria, tipo_empaque=a.tipo, casepack=a.casepack,
                prepack=a.prepack.codigo if a.prepack else None,
                unidades_por_caja=a.prepack.total if a.prepack else None, cantidad=cantidad, unidad=a.unidad,
                precio=a.precio_demo, fecha_entrega=xf, pais_origen=a.pais_origen,
                partida_arancelaria=a.partida_arancelaria,
            ))
            pos += 10
    db.flush()
    return oc


def _factura_historica(db, usuario, oc, numero, fecha, plantillas, unidad=None, recolectado=None):
    """Factura ya cerrada: todas las posiciones de la OC, un PL finalizado con
    sus cajas y, si se indica, confirmado en una unidad de carga."""
    ts = _momento(fecha)
    f = Factura(proveedor_id=oc.proveedor_id, numero=numero, fecha=fecha, moneda=oc.moneda, incoterm=oc.incoterm,
                sociedad=oc.sociedad, centro=oc.centro, pais_destino=oc.pais_destino, estado="FINALIZADA",
                version=1, creado_por=usuario.id, creado_en=ts - timedelta(days=2), actualizado_en=ts,
                finalizado_en=ts)
    pl = PackingList(numero="PL-001", estado="FINALIZADO", version=1, creado_en=ts, actualizado_en=ts,
                     unidad=unidad, asignacion="CONFIRMADA" if unidad else None, recolectado_en=recolectado)
    f.packing_lists.append(pl)
    for p in oc.posiciones:
        linea = FacturaLinea(posicion_oc=p, cantidad=p.cantidad, precio_unitario=p.precio, precio_oc=p.precio,
                             oc_numero=oc.numero, posicion=p.posicion, codigo_sap=p.codigo_sap, upc=p.upc,
                             estilo=p.estilo, color=p.color, talla=p.talla, descripcion=p.descripcion,
                             unidad=p.unidad, marca=p.marca, categoria=p.categoria, tipo_empaque=p.tipo_empaque,
                             casepack=p.casepack, pais_destino=oc.pais_destino, pais_origen=p.pais_origen,
                             partida_arancelaria=p.partida_arancelaria, descripcion_comercial=p.descripcion)
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


def _historial_demo(db, hoy, tnf, vans, usuarios, plantillas, arts):
    """Meses anteriores ya facturados y embarcados, para que el tablero tenga
    historia: un contenedor recibido, otro en tránsito y una factura lista
    para embarcar."""
    recibido = Embarque(codigo="EMB-0001", tipo_transporte="MARITIMO", modalidad="FCL", transportista="Maersk",
                        documento_numero="MAEU 221877310", puerto_origen="Cai Mep (VN)", puerto_destino="Acajutla (SV)",
                        etd=hoy - timedelta(days=88), eta=hoy - timedelta(days=58),
                        salida_real=hoy - timedelta(days=87), arribo_real=hoy - timedelta(days=57), estado="RECIBIDO")
    c1 = UnidadCarga(tipo="40HC", etiqueta="40HC #1", numero="MSKU 481220-7", sello="ML-99812")
    recibido.unidades.append(c1)
    for tipo, dias, lugar in (("RECOLECCION", 90, "Bodega del proveedor"), ("SALIDA", 87, "Cai Mep (VN)"),
                              ("ARRIBO", 57, "Acajutla (SV)"), ("ENTREGA", 55, "Bodega fiscal 8010"),
                              ("RECEPCION", 54, "Bodega fiscal 8010")):
        recibido.eventos.append(EventoEmbarque(tipo=tipo, fecha=_momento(hoy - timedelta(days=dias), 9), ubicacion=lugar))
    transito = Embarque(codigo="EMB-0002", tipo_transporte="MARITIMO", modalidad="FCL", transportista="COSCO",
                        documento_numero="COSU 640018225", puerto_origen="Yantian (CN)", puerto_destino="Acajutla (SV)",
                        etd=hoy - timedelta(days=19), eta=hoy + timedelta(days=9),
                        salida_real=hoy - timedelta(days=18), estado="EN_TRANSITO")
    c2 = UnidadCarga(tipo="40GP", etiqueta="40GP #1", numero="TGHU 772104-3", sello="CS-10442")
    transito.unidades.append(c2)
    transito.eventos.append(EventoEmbarque(tipo="RECOLECCION", fecha=_momento(hoy - timedelta(days=21), 8),
                                           ubicacion="Bodega del proveedor"))
    transito.eventos.append(EventoEmbarque(tipo="SALIDA", fecha=_momento(hoy - timedelta(days=18), 7),
                                           ubicacion="Yantian (CN)"))
    transito.eventos.append(EventoEmbarque(tipo="TRANSITO", fecha=_momento(hoy - timedelta(days=6), 12),
                                           ubicacion="Canal de Panamá, lado Pacífico", observacion="Sin novedad"))
    db.add_all([recibido, transito])

    u_tnf, u_vans = usuarios
    d = lambda n: hoy - timedelta(days=n)  # noqa: E731
    historicas = [
        (tnf, "4400003701", 140, [("NF0A5GLL", "JK3 TNF Black", [("M", 50), ("L", 50)])], "TNF-2026-0418", 128, c1, 90),
        (tnf, "4400003702", 115, [("NF0A3VY2", "JK3 TNF Black", [("OS", 80)])], "TNF-2026-0502", 100, c1, 90),
        (vans, "4400003751", 110, [("VN000EE3", "BLK Negro", [("8", 60)])], "VN-88120", 95, c1, 90),
        (tnf, "4400003703", 85, [("NF0A7W4G", "KX7 Negro", [("9", 36), ("10", 48)])], "TNF-2026-0611", 70, c2, 21),
        (vans, "4400003752", 50, [("VN000EE3", "BLK Negro", [("9", 72)])], "VN-88177", 35, c2, 21),
        (tnf, "4400003704", 20, [("NF0A5IHO", "Gris melange", [("S", 30), ("M", 30)])], "TNF-2026-0915", 6, None, None),
    ]
    for prov, numero, dias_oc, lineas, factura, dias_factura, unidad, recoleccion in historicas:
        oc = _oc(db, prov, arts, numero, d(dias_oc), lineas, xf=d(dias_factura - 2), tienda=d(dias_factura - 60),
                 puerto="CNYTN" if unidad is c2 else "VNCMT")
        usuario = u_tnf if prov is tnf else u_vans
        f = _factura_historica(db, usuario, oc, factura, d(dias_factura), plantillas, unidad,
                               d(recoleccion) if recoleccion else None)
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
    cat = _catalogos(db)
    arts = _articulos(db, cat, {"TNF": tnf, "VANS": vans})
    hoy = date.today()
    d = lambda n: hoy + timedelta(days=n)  # noqa: E731

    _oc(db, tnf, arts, "4400003845", d(-20), [
        ("NF0A5GLL", "JK3 TNF Black", [("S", 40), ("M", 60), ("L", 60), ("XL", 27), ("XXL", 20)]),
        ("NF0A7W4G", "KX7 Negro", [("8", 24), ("9", 36), ("10", 50), ("11", 36), ("12", 12)]),
    ], xf=d(10), xf_nueva=d(14), tienda=d(75))
    _oc(db, tnf, arts, "4400003846", d(-12), [
        ("NF0A3VY2", "JK3 TNF Black", [("OS", 120)]),
        ("NF0A5IHO", "Gris melange", [("S", 30), ("M", 30), ("L", 30)]),
    ], puerto="CNYTN", origen="ID", xf=d(18), tienda=d(80))
    _oc(db, tnf, arts, "4400003850", d(-8), [("NF0A5GLL", "Azul summit", [("M", 30), ("L", 30)])],
        sociedad="PA01", centro="PA10", almacen="BF01", destino="5910", puerto="VNCMT", xf=d(20), tienda=d(70))
    _oc(db, tnf, arts, "4400003851", d(-2), [("NF0A5IHO", "Gris melange", [("S", 20), ("M", 20)])],
        origen="KH", puerto="KHKOS", xf=d(35), tienda=d(100), comercial="P", logistica="304")
    _oc(db, vans, arts, "4400003901", d(-15), [
        ("VN000EE3", "BLK Negro", [("7", 36), ("8", 48), ("9", 60), ("10", 48), ("11", 24)]),
    ], centro="8020", almacen="BF20", xf=d(12), tienda=d(60))
    _oc(db, vans, arts, "4400003902", d(-5), [("VN0A4BV4", "Blanco", [("7", 24), ("8", 24), ("9", 24), ("10", 24)])],
        centro="8020", almacen="BF20", puerto="CNSHA", origen="CN", xf=d(25), xf_nueva=d(22), tienda=d(90),
        logistica="301")
    _oc(db, vans, arts, "4400003903", d(-4), [("VN000EE3", "BLK Negro", [("CRV01", 10)])],
        centro="8020", almacen="BF20", destino="3200", xf=d(15), tienda=d(65))
    _oc(db, vans, arts, "4400003904", d(-1), [("VN0A4BV4", "Blanco", [("8", 24)])],
        centro="8020", almacen="BF20", puerto="CNSHA", origen="CN", xf=d(40), tienda=d(110), comercial="P",
        logistica="304")

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
    prepack = PlantillaCaja(proveedor_id=vans.id, nombre="Master prepack (1 curva)", cantidad_por_caja=1, unidad="CJ",
                            largo=60, ancho=38, alto=35, peso_neto=9.6, peso_bruto=11.0, tara=1.4)
    db.add_all([chaqueta, calzado, mochila, fleece, master12, master10, prepack])
    db.flush()
    _historial_demo(db, hoy, tnf, vans, (u_tnf, u_vans), {
        "NF0A5GLL": chaqueta, "NF0A3VY2": mochila, "NF0A7W4G": calzado, "NF0A5IHO": fleece, "VN000EE3": master12},
        arts)
    e = Embarque(codigo="EMB-0003", tipo_transporte="MARITIMO", modalidad="FCL", transportista="Maersk",
                 puerto_origen="Ho Chi Minh (VN)", puerto_destino="Acajutla (SV)",
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
