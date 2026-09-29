"""Datos de demostración. Se cargan solo si la base está vacía.
Uso manual: python -m app.seed"""
from datetime import date, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import (
    Almacen,
    Articulo,
    Centro,
    Contacto,
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
    Pallet,
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
# Sociedades de cada país: código, nombre, razón social, NIT/RUC, país, dirección, correos de facturación
SOCIEDADES = [
    ("8000", "Operaciones El Salvador", "Distribuidora de Marcas, S.A. de C.V.", "0614-010190-101-2", "SV",
     "Blvd. del Ejército km 7, Soyapango, San Salvador", "facturacion.sv@marcas.demo"),
    ("PA01", "Operaciones Panamá", "Distribuidora de Marcas Panamá, S.A.", "155612345-2-2019", "PA",
     "Zona Libre de Colón, Calle 16, Colón", "facturacion.pa@marcas.demo, cxp.pa@marcas.demo"),
    ("GT01", "Operaciones Guatemala", "Distribuidora de Marcas Guatemala, S.A.", "7865412-3", "GT",
     "Zona 12, Ciudad de Guatemala", "facturacion.gt@marcas.demo"),
    ("HN01", "Operaciones Honduras", "Distribuidora de Marcas Honduras, S.A.", "08019012345678", "HN",
     "Col. Satélite, San Pedro Sula", "facturacion.hn@marcas.demo"),
    ("NI01", "Operaciones Nicaragua", "Distribuidora de Marcas Nicaragua, S.A.", "J0310000012345", "NI",
     "Carretera Norte km 6, Managua", "facturacion.ni@marcas.demo"),
    ("CR01", "Operaciones Costa Rica", "Distribuidora de Marcas Costa Rica, S.A.", "3-101-123456", "CR",
     "La Uruca, San José", "facturacion.cr@marcas.demo"),
]
# Centros asignados a cada sociedad: código, sociedad, nombre, tipo, país, puerto de llegada, correos (notify)
CENTROS = [
    ("8010", "8000", "Bodega fiscal San Salvador", "BODEGA_FISCAL", "SV", "SVAQJ", "recepcion.8010@marcas.demo"),
    ("8020", "8000", "Bodega fiscal San Bartolo", "ZONA_FRANCA", "SV", "SVAQJ", "recepcion.8020@marcas.demo"),
    ("2220", "8000", "Centro de distribución El Salvador", "TIENDA", "SV", "SVAQJ", "cd.sv@marcas.demo"),
    ("PA10", "PA01", "Bodega fiscal Zona Libre de Colón", "ZONA_FRANCA", "PA", "PAONX", "recepcion.pa10@marcas.demo"),
    ("PA20", "PA01", "Bodega fiscal Panamá Pacífico", "BODEGA_FISCAL", "PA", "PABLB", "recepcion.pa20@marcas.demo"),
    ("5910", "PA01", "Centro de distribución Panamá", "TIENDA", "PA", "PAONX", "cd.pa@marcas.demo"),
    ("3200", "GT01", "Centro de distribución Guatemala", "TIENDA", "GT", "GTSTC", "cd.gt@marcas.demo"),
    ("3400", "HN01", "Centro de distribución Honduras", "TIENDA", "HN", "HNPCR", "cd.hn@marcas.demo"),
    ("5580", "NI01", "Centro de distribución Nicaragua", "TIENDA", "NI", "NICIO", "cd.ni@marcas.demo"),
    ("1880", "CR01", "Centro de distribución Costa Rica", "TIENDA", "CR", "CRLIO", "cd.cr@marcas.demo"),
]
# nombre, cargo, rol, sociedad o centro, correos, teléfono
CONTACTOS = [
    ("Ana Martínez", "Cuentas por pagar", "FACTURACION", ("sociedad", "8000"), "ana.martinez@marcas.demo", "+503 2222-1000"),
    ("Luis Pérez", "Contador", "FACTURACION", ("sociedad", "PA01"), "luis.perez@marcas.demo", "+507 430-1000"),
    ("Carlos Rivas", "Jefe de bodega", "NOTIFY", ("centro", "8010"),
     "carlos.rivas@marcas.demo, bodega8010@marcas.demo", "+503 2222-2010"),
    ("María López", "Importaciones", "NOTIFY", ("centro", "8020"), "maria.lopez@marcas.demo", "+503 2222-2020"),
    ("Jorge Castillo", "Agente aduanal", "LOGISTICA", ("centro", "8020"), "jcastillo@aduanas.demo", "+503 7777-1111"),
    ("Rosa Méndez", "Jefa de bodega", "NOTIFY", ("centro", "PA10"), "rosa.mendez@marcas.demo", "+507 430-2010"),
]
PUERTOS = [
    ("VNSGN", "Ho Chi Minh (Cat Lai)", "VN"), ("VNCMT", "Cai Mep", "VN"), ("CNYTN", "Yantian", "CN"),
    ("CNSHA", "Shanghái", "CN"), ("IDJKT", "Yakarta", "ID"), ("KHKOS", "Sihanoukville", "KH"),
    ("SVAQJ", "Acajutla", "SV"), ("PAONX", "Colón (Manzanillo)", "PA"), ("PABLB", "Balboa", "PA"),
    ("GTSTC", "Santo Tomás de Castilla", "GT"), ("HNPCR", "Puerto Cortés", "HN"), ("NICIO", "Corinto", "NI"),
    ("CRLIO", "Limón (Moín)", "CR"),
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
# Prepacks: estilo, color, prepack ID (es la "talla" del artículo prepack), curva
PREPACKS = [
    ("VN000EE3", "BLK Negro", "AB12", {"7": 1, "8": 2, "9": 3, "10": 3, "11": 2, "12": 1}),  # 12 pares
    ("VN0A4BV4", "Blanco", "CD08", {"7": 2, "8": 2, "9": 2, "10": 2}),  # 8 pares
]


def _momento(d: date, hora: int = 10) -> datetime:
    return datetime.combine(d, time(hora))


def _catalogos(db: Session) -> dict:
    db.add_all([Pais(codigo=c, nombre=n) for c, n in PAISES])
    socs = {c: Sociedad(codigo=c, nombre=n, razon_social=r, id_fiscal=nit, pais=pais, moneda="USD", direccion=dir_,
                        correos=correos)
            for c, n, r, nit, pais, dir_, correos in SOCIEDADES}
    db.add_all(socs.values())
    db.flush()
    centros = {c: Centro(codigo=c, sociedad_id=socs[s_].id, nombre=n, tipo=t, pais=pais, puerto=puerto, correos=correos,
                         direccion=f"{n}, {pais}")
               for c, s_, n, t, pais, puerto, correos in CENTROS}
    db.add_all(centros.values())
    db.flush()
    # Almacenes: separación del inventario en el sistema, no lugares físicos
    db.add_all([
        Almacen(codigo="BF19", sociedad_id=socs["8000"].id, nombre="Detalle", tipo="DETALLE"),
        Almacen(codigo="BF20", sociedad_id=socs["8000"].id, nombre="Mayoreo", tipo="MAYOREO"),
        Almacen(codigo="BF18", sociedad_id=socs["8000"].id, nombre="Virtual en tránsito", tipo="VIRTUAL"),
        Almacen(codigo="BF01", sociedad_id=socs["PA01"].id, nombre="Detalle", tipo="DETALLE"),
        Almacen(codigo="BF02", sociedad_id=socs["PA01"].id, nombre="Mayoreo", tipo="MAYOREO"),
    ])
    for nombre, cargo, rol, (tipo, codigo), correos, tel in CONTACTOS:
        db.add(Contacto(nombre=nombre, cargo=cargo, rol=rol, correos=correos, telefono=tel,
                        sociedad_id=socs[codigo].id if tipo == "sociedad" else None,
                        centro_id=centros[codigo].id if tipo == "centro" else None))
    db.add_all([Puerto(codigo=c, nombre=n, pais=p) for c, n, p in PUERTOS])
    marcas = {c: Marca(codigo=c, nombre=n) for c, n in MARCAS}
    grupos = {c: GrupoArticulo(codigo=c, nombre=n, categoria=cat) for c, n, cat in GRUPOS}
    db.add_all([*marcas.values(), *grupos.values()])
    db.flush()
    return {"marcas": marcas, "grupos": grupos}


def _articulos(db: Session, cat: dict, proveedores: dict) -> dict:
    """Maestro de artículos: sólidos (con casepack en calzado, sin casepack en
    ropa) con un número de artículo por estilo-color-talla, y prepacks cuya
    talla es su prepack ID."""
    arts = {}
    siguiente = 30095120001
    for estilo, color, marca, grupo, prov, unidad, precio, origen, partida, desc, casepack, tallas in ESTILOS:
        for talla in tallas:
            sku = str(siguiente)
            siguiente += 1
            a = Articulo(sku=sku, upc=f"0196{siguiente % 10**8:08d}", estilo=estilo, color=color, talla=talla,
                         descripcion=desc, marca_id=cat["marcas"][marca].id, grupo_id=cat["grupos"][grupo].id,
                         proveedor_id=proveedores[prov].id, unidad=unidad, tipo="SOLIDO", casepack=casepack,
                         partida_arancelaria=partida, pais_origen=origen)
            a.precio_demo = precio
            arts[(estilo, color, talla)] = a
    db.add_all(arts.values())
    db.flush()
    for estilo, color, codigo, curva in PREPACKS:
        base = arts[(estilo, color, next(iter(curva)))]
        pp = Prepack(codigo=codigo, estilo=estilo, color=color,
                     descripcion=f"Curva {estilo} {color} tallas {'-'.join(curva)} ({sum(curva.values())} pares)")
        for talla, cant in curva.items():
            pp.componentes.append(PrepackComponente(articulo_id=arts[(estilo, color, talla)].id, cantidad=cant))
        db.add(pp)
        db.flush()
        a = Articulo(sku=str(siguiente), estilo=estilo, color=color, talla=codigo,
                     descripcion=f"{base.descripcion}, prepack {codigo}", marca_id=base.marca_id,
                     grupo_id=base.grupo_id, proveedor_id=base.proveedor_id, unidad="CJ", tipo="PREPACK",
                     prepack_id=pp.id, partida_arancelaria=base.partida_arancelaria, pais_origen=base.pais_origen)
        siguiente += 1
        a.precio_demo = base.precio_demo * sum(curva.values())
        db.add(a)
        db.flush()
        arts[(estilo, color, codigo)] = a
    return arts


def _oc(db, prov, arts, numero, fecha, lineas, sociedad="8000", centro="8010", almacen="BF19", destino="2220",
        puerto="VNSGN", origen="VN", xf=None, xf_nueva=None, tienda=None, comercial="C", logistica="300"):
    """lineas: [(estilo, color, [(talla, cantidad), ...], almacén opcional)]; posiciones de 10 en 10.
    Cada posición puede ir a un almacén distinto dentro de la misma sociedad y centro."""
    oc = OrdenCompra(proveedor_id=prov.id, numero=numero, sociedad=sociedad, centro=centro,
                     centro_destino=destino, moneda="USD", incoterm="FOB", fecha=fecha, puerto_despacho=puerto,
                     pais_origen=origen, pais_procedencia=origen, fecha_xf_original=xf, fecha_xf=xf_nueva or xf,
                     fecha_tienda=tienda, liberacion_comercial=comercial, liberacion_logistica=logistica,
                     liberada=comercial == "C" and logistica in ("300", "301"))
    db.add(oc)
    pos = 10
    for estilo, color, tallas, *alm in lineas:
        for talla, cantidad in tallas:
            a = arts[(estilo, color, talla)]
            oc.posiciones.append(PosicionOC(
                posicion=str(pos), almacen=alm[0] if alm else almacen, articulo_id=a.id, codigo_sap=a.sku, upc=a.upc, estilo=a.estilo, color=a.color,
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


def _factura_historica(db, usuario, oc, numero, fecha, plantillas, unidad=None, recolectado=None, pallet=False):
    """Factura ya cerrada: todas las posiciones de la OC, un PL finalizado con
    sus cajas y, si se indica, confirmado en una unidad de carga."""
    ts = _momento(fecha)
    f = Factura(proveedor_id=oc.proveedor_id, numero=numero, fecha=fecha, moneda=oc.moneda, incoterm=oc.incoterm,
                sociedad=oc.sociedad, centro=oc.centro, centro_destino=oc.centro_destino, estado="FINALIZADA",
                version=1, creado_por=usuario.id, creado_en=ts - timedelta(days=2), actualizado_en=ts,
                finalizado_en=ts)
    pl = PackingList(numero="PL-001", estado="FINALIZADO", version=1, creado_en=ts, actualizado_en=ts,
                     unidad=unidad, asignacion="CONFIRMADA" if unidad else None, recolectado_en=recolectado)
    f.packing_lists.append(pl)
    for p in oc.posiciones:
        linea = FacturaLinea(posicion_oc=p, cantidad=p.cantidad, precio_unitario=p.precio, precio_oc=p.precio,
                             oc_numero=oc.numero, almacen=p.almacen, posicion=p.posicion, codigo_sap=p.codigo_sap, upc=p.upc,
                             estilo=p.estilo, color=p.color, talla=p.talla, descripcion=p.descripcion,
                             unidad=p.unidad, marca=p.marca, categoria=p.categoria, tipo_empaque=p.tipo_empaque,
                             casepack=p.casepack, centro_destino=oc.centro_destino, pais_origen=p.pais_origen,
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
    if pallet:
        # Todo el PL en un pallet estándar
        tarima = Pallet(numero=1, largo=120, ancho=100, alto=160, peso_tara=25)
        pl.pallets.append(tarima)
        for g in pl.grupos:
            g.pallet = tarima
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
                        documento_numero="MAEU 221877310", puerto_origen="VNCMT", puerto_destino="SVAQJ", centro="8010",
                        etd=hoy - timedelta(days=88), eta=hoy - timedelta(days=58),
                        salida_real=hoy - timedelta(days=87), arribo_real=hoy - timedelta(days=57), estado="RECIBIDO")
    c1 = UnidadCarga(tipo="40HC", etiqueta="40HC #1", numero="MSKU 481220-7", sello="ML-99812")
    recibido.unidades.append(c1)
    for tipo, dias, lugar in (("RECOLECCION", 90, "Bodega del proveedor"), ("SALIDA", 87, "Cai Mep (VN)"),
                              ("ARRIBO", 57, "Acajutla (SV)"), ("ENTREGA", 55, "Bodega fiscal 8010"),
                              ("RECEPCION", 54, "Bodega fiscal 8010")):
        recibido.eventos.append(EventoEmbarque(tipo=tipo, fecha=_momento(hoy - timedelta(days=dias), 9), ubicacion=lugar))
    transito = Embarque(codigo="EMB-0002", tipo_transporte="MARITIMO", modalidad="FCL", transportista="COSCO",
                        documento_numero="COSU 640018225", puerto_origen="CNYTN", puerto_destino="SVAQJ", centro="8010",
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
                               d(recoleccion) if recoleccion else None, pallet=factura == "VN-88177")
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
        ("NF0A7W4G", "KX7 Negro", [("8", 24), ("9", 36), ("10", 50), ("11", 36), ("12", 12)], "BF20"),
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
        ("VN000EE3", "BLK Negro", [("7", 36), ("8", 48), ("9", 60)], "BF19"),
        ("VN000EE3", "BLK Negro", [("10", 48), ("11", 24)]),
    ], centro="8020", almacen="BF20", xf=d(12), tienda=d(60))
    _oc(db, vans, arts, "4400003902", d(-5), [("VN0A4BV4", "Blanco", [("7", 24), ("8", 24), ("9", 24), ("10", 24)])],
        centro="8020", almacen="BF20", puerto="CNSHA", origen="CN", xf=d(25), xf_nueva=d(22), tienda=d(90),
        logistica="301")
    _oc(db, vans, arts, "4400003903", d(-4), [("VN000EE3", "BLK Negro", [("AB12", 10)]),
                                              ("VN0A4BV4", "Blanco", [("CD08", 6)])],
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
                 puerto_origen="VNSGN", puerto_destino="SVAQJ",
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
