"""Datos de demostración. Se cargan solo si la base está vacía.
Uso manual: python -m app.seed"""
import json
from datetime import date, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import (
    Rol,
    Almacen,
    Articulo,
    ahora,
    Centro,
    Contacto,
    Embarque,
    EventoEmbarque,
    Factura,
    FacturaLinea,
    EscalaTalla,
    GrupoArticulo,
    GrupoCajas,
    GrupoCajasItem,
    Marca,
    OrdenCompra,
    PackingList,
    Pais,
    PlantillaCaja,
    PLLinea,
    PosicionOC,
    Prepack,
    PrepackComponente,
    Proveedor,
    Puerto,
    PasoLeadTime,
    ReglaLeadTime,
    TipoEmpaque,
    RegionLeadTime,
    Sociedad,
    TipoUnidad,
    Transportista,
    UnidadCarga,
    Usuario,
)
from .security import hash_password
from .services import empaques
from .services import reglas_lt as rlt
from .services.common import registrar
from .services.genericos import sufijo_convencional
from .services.varios import crear_roles_fabrica
from .services.productos import (
    _guardar_partidas,
    asegurar_producto,
    cargar_incisos_base,
    descripcion_comercial_simple,
    partida_para,
    partidas_simples,
)

PAISES = [
    ("VN", "Vietnam"), ("CN", "China"), ("ID", "Indonesia"), ("KH", "Cambodia"), ("BD", "Bangladesh"),
    ("IN", "India"), ("SV", "El Salvador"), ("PA", "Panama"), ("GT", "Guatemala"), ("HN", "Honduras"),
    ("CR", "Costa Rica"), ("NI", "Nicaragua"), ("US", "United States"), ("MX", "Mexico"), ("BR", "Brazil"),
]
REGION_PAIS = {**dict.fromkeys(["VN", "CN", "ID", "KH", "BD", "IN"], "ASIA"),
               **dict.fromkeys(["SV", "PA", "GT", "HN", "CR", "NI"], "CAM")}
# Sociedades de cada país: código, nombre, razón social, NIT/RUC, país, dirección, correos de facturación
SOCIEDADES = [
    ("8000", "El Salvador Operations", "Distribuidora de Marcas, S.A. de C.V.", "0614-010190-101-2", "SV",
     "Blvd. del Ejército km 7, Soyapango, San Salvador", "facturacion.sv@marcas.demo"),
    ("PA01", "Panama Operations", "Distribuidora de Marcas Panamá, S.A.", "155612345-2-2019", "PA",
     "Zona Libre de Colón, Calle 16, Colón", "facturacion.pa@marcas.demo, cxp.pa@marcas.demo"),
    ("GT01", "Guatemala Operations", "Distribuidora de Marcas Guatemala, S.A.", "7865412-3", "GT",
     "Zona 12, Ciudad de Guatemala", "facturacion.gt@marcas.demo"),
    ("HN01", "Honduras Operations", "Distribuidora de Marcas Honduras, S.A.", "08019012345678", "HN",
     "Col. Satélite, San Pedro Sula", "facturacion.hn@marcas.demo"),
    ("NI01", "Nicaragua Operations", "Distribuidora de Marcas Nicaragua, S.A.", "J0310000012345", "NI",
     "Carretera Norte km 6, Managua", "facturacion.ni@marcas.demo"),
    ("CR01", "Costa Rica Operations", "Distribuidora de Marcas Costa Rica, S.A.", "3-101-123456", "CR",
     "La Uruca, San José", "facturacion.cr@marcas.demo"),
]
# Centros asignados a cada sociedad: código, sociedad, nombre, tipo, país, puerto de llegada, correos (notify)
CENTROS = [
    ("8010", "8000", "San Salvador bonded warehouse", "BODEGA_FISCAL", "SV", "SVAQJ", "recepcion.8010@marcas.demo"),
    ("8020", "8000", "San Bartolo bonded warehouse", "ZONA_FRANCA", "SV", "SVAQJ", "recepcion.8020@marcas.demo"),
    ("2220", "8000", "El Salvador distribution center", "TIENDA", "SV", "SVAQJ", "cd.sv@marcas.demo"),
    ("PA10", "PA01", "Colon Free Zone bonded warehouse", "ZONA_FRANCA", "PA", "PAONX", "recepcion.pa10@marcas.demo"),
    ("PA20", "PA01", "Panama Pacifico bonded warehouse", "BODEGA_FISCAL", "PA", "PABLB", "recepcion.pa20@marcas.demo"),
    ("5910", "PA01", "Panama distribution center", "TIENDA", "PA", "PAONX", "cd.pa@marcas.demo"),
    ("3200", "GT01", "Guatemala distribution center", "TIENDA", "GT", "GTSTC", "cd.gt@marcas.demo"),
    ("3400", "HN01", "Honduras distribution center", "TIENDA", "HN", "HNPCR", "cd.hn@marcas.demo"),
    ("5580", "NI01", "Nicaragua distribution center", "TIENDA", "NI", "NICIO", "cd.ni@marcas.demo"),
    ("1880", "CR01", "Costa Rica distribution center", "TIENDA", "CR", "CRLIO", "cd.cr@marcas.demo"),
]
# nombre, cargo, rol, sociedad o centro, correos, teléfono
CONTACTOS = [
    ("Ana Martínez", "Accounts payable", "FACTURACION", ("sociedad", "8000"), "ana.martinez@marcas.demo", "+503 2222-1000"),
    ("Luis Pérez", "Accountant", "FACTURACION", ("sociedad", "PA01"), "luis.perez@marcas.demo", "+507 430-1000"),
    ("Carlos Rivas", "Warehouse manager", "NOTIFY", ("centro", "8010"),
     "carlos.rivas@marcas.demo, bodega8010@marcas.demo", "+503 2222-2010"),
    ("María López", "Imports", "NOTIFY", ("centro", "8020"), "maria.lopez@marcas.demo", "+503 2222-2020"),
    ("Jorge Castillo", "Customs broker", "LOGISTICA", ("centro", "8020"), "jcastillo@aduanas.demo", "+503 7777-1111"),
    ("Rosa Méndez", "Warehouse manager", "NOTIFY", ("centro", "PA10"), "rosa.mendez@marcas.demo", "+507 430-2010"),
]
PUERTOS = [
    ("VNSGN", "Ho Chi Minh (Cat Lai)", "VN"), ("VNCMT", "Cai Mep", "VN"), ("CNYTN", "Yantian", "CN"),
    ("CNSHA", "Shanghai", "CN"), ("IDJKT", "Jakarta", "ID"), ("KHKOS", "Sihanoukville", "KH"),
    ("SVAQJ", "Acajutla", "SV"), ("PAONX", "Colón (Manzanillo)", "PA"), ("PABLB", "Balboa", "PA"),
    ("GTSTC", "Santo Tomás de Castilla", "GT"), ("HNPCR", "Puerto Cortés", "HN"), ("NICIO", "Corinto", "NI"),
    ("CRLIO", "Limón (Moín)", "CR"), ("SVLUN", "La Unión", "SV"),
]
# Aeropuertos y aduanas terrestres: el embarque solo ofrece los de su modo
PUERTOS_OTROS = [
    ("SAL", "San Salvador (airport)", "SV", "AEREO"), ("PTY", "Tocumen (airport)", "PA", "AEREO"),
    ("HKG", "Hong Kong (airport)", "HK", "AEREO"), ("SGN", "Ho Chi Minh (airport)", "VN", "AEREO"),
    ("SVHAC", "La Hachadura (border)", "SV", "TERRESTRE"), ("GTPDA", "Pedro de Alvarado (border)", "GT", "TERRESTRE"),
]
# Otros puertos por los que puede llegar cada centro (además del principal)
PUERTOS_CENTRO = {
    "8010": ["SVLUN", "SAL", "SVHAC"], "8020": ["SVLUN", "SAL", "SVHAC"], "2220": ["SAL"],
    "PA10": ["PABLB", "PTY"], "PA20": ["PAONX", "PTY"], "5910": ["PTY"],
}
# Tipos de unidad por modo, con capacidad nominal (m³, kg)
TIPOS_UNIDAD = [
    ("20GP", "20' standard container", "MARITIMO", "FCL", 33, 28000, True),
    ("40GP", "40' standard container", "MARITIMO", "FCL", 67, 26500, True),
    ("40HC", "40' high cube container", "MARITIMO", "FCL", 76, 26500, True),
    ("LCL", "Consolidated cargo (LCL)", "MARITIMO", "LCL", None, None, False),
    ("AWB", "Air waybill", "AEREO", "AEREO", None, 5000, False),
    ("FTL53", "53' full truck", "TERRESTRE", "FTL", 110, 22000, True),
    ("LTL", "Road partial load", "TERRESTRE", "LTL", None, None, False),
]
# código, nombre, tipo, SCAC/IATA, país, correos, sociedades
TRANSPORTISTAS = [
    ("MAEU", "Maersk", "MARITIMO", "MAEU", "DK", "centroamerica@maersk.demo", ["8000", "PA01", "GT01", "HN01"]),
    ("COSU", "COSCO Shipping", "MARITIMO", "COSU", "CN", "ca@cosco.demo", ["8000", "PA01"]),
    ("CMDU", "CMA CGM", "MARITIMO", "CMDU", "FR", "ca@cmacgm.demo", ["PA01", "CR01", "NI01"]),
    ("AVCG", "Avianca Cargo", "AEREO", "134", "CO", "cargo@avianca.demo", ["8000", "PA01", "GT01"]),
    ("TDS", "Transportes del Sur", "TERRESTRE", None, "SV", "operaciones@tds.demo", ["8000", "GT01", "HN01"]),
]
PASSWORD_DEMO = "Supplier2026"
MARCAS = [("TNF", "The North Face"), ("VANS", "Vans"), ("MERR", "Merrell"), ("CAT", "Caterpillar"),
          ("HPU", "Hush Puppies"), ("CASA", "House brand")]
GRUPOS = [("CALZ-OUT", "Outdoor footwear", "CALZADO"), ("CALZ-CAS", "Casual footwear", "CALZADO"),
          ("CHAQ", "Jackets", "ROPA"), ("FLEE", "Fleece and sweatshirts", "ROPA"), ("MOCH", "Backpacks", "ACCESORIO")]
# estilo, color, marca, grupo, proveedor, unidad, precio, origen, partida, descripción, empaque de la OC, tallas
# El empaque (casepack, inner pack) es de la posición de la OC, no del artículo:
# aquí solo es el que usan las OCs de ejemplo.
ESTILOS = [
    ("NF0A5GLL", "JK3 TNF Black", "TNF", "CHAQ", "TNF", "UN", 48.50, "VN", "6201.40", "Men's waterproof jacket",
     None, ["S", "M", "L", "XL", "XXL"]),
    ("NF0A5GLL", "Summit blue", "TNF", "CHAQ", "TNF", "UN", 48.50, "VN", "6201.40", "Men's waterproof jacket",
     None, ["M", "L"]),
    ("NF0A7W4G", "KX7 Black", "TNF", "CALZ-OUT", "TNF", "PAR", 62.00, "CN", "6404.11", "Trail running footwear",
     (12, None), ["8", "9", "10", "11", "12"]),
    ("NF0A3VY2", "JK3 TNF Black", "TNF", "MOCH", "TNF", "UN", 31.20, "ID", "4202.92", "Backpack 28 L", (20, 5),
     ["OS"]),
    ("NF0A5IHO", "Heather grey", "TNF", "FLEE", "TNF", "UN", 22.75, "KH", "6110.30", "Half-zip fleece",
     (None, 5), ["S", "M", "L"]),
    ("VN000EE3", "BLK Black", "VANS", "CALZ-CAS", "VANS", "PAR", 25.50, "VN", "6404.19", "Classic canvas footwear",
     (12, None), ["7", "8", "9", "10", "11", "12"]),
    ("VN0A4BV4", "White", "VANS", "CALZ-CAS", "VANS", "PAR", 21.00, "CN", "6404.19", "Basic canvas footwear",
     (12, None), ["7", "8", "9", "10"]),
]
# Ficha técnica y clasificación de cada estilo-color (producto). La partida
# aprobada es la que saca el motor de clasificación con esta ficha; el código
# nacional de cada país sale de la base de incisos.
FICHAS = {
    ("NF0A5GLL", "JK3 TNF Black"): dict(
        nombre="Men's Antora rain jacket", tipo="chaqueta", estado="aprobado", codigo="620140",
        ficha={"genero": "M", "edad": "general", "edadNac": "adulto", "tejido": "plano", "hechura": "chaqueta",
               "relleno_tipo": "ninguno", "tieneForro": True, "recubierta": False, "manga": "larga",
               "uso": "Waterproof shell jacket for hiking", "tallas": "S to XXL",
               "comp": {"exterior": "100% nylon", "forro": "100% polyester"}},
        desc="CHAQUETA DE TEXTIL, DE TEJIDO PLANO, PARA HOMBRE"),
    ("NF0A5GLL", "Summit blue"): dict(
        nombre="Men's Antora rain jacket", tipo="chaqueta", estado="observado",
        ficha={"genero": "M", "edad": "general", "edadNac": "adulto", "tejido": "plano", "hechura": "chaqueta",
               "uso": "Waterproof shell jacket for hiking", "tallas": "M to L", "comp": {}},
        faltan=["Composition: outer fabric or surface"],
        observaciones="Send the shell composition. If the coating is visible on the outside it goes in 6210; "
                      "if it is a hidden membrane, in 6201."),
    ("NF0A7W4G", "KX7 Black"): dict(
        nombre="Men's Vectiv trail running shoe", tipo="calzado", estado="aprobado", codigo="640411",
        ficha={"genero": "M", "edadNac": "adulto", "estiloCalz": "tenis", "disenio": "entrenamiento", "altura": "bajo",
               "puntera": "ninguna", "impermeable": False, "suelaEspumosa": False, "uso": "Trail running shoe",
               "tallas": "8 to 12", "comp": {"corte": "80% textile, 20% synthetic", "suela": "100% rubber",
                                             "forro": "100% polyester", "plantilla": "100% EVA"}},
        desc="TENIS CON CORTE DE TEXTIL Y SUELA DE SINTÉTICO, SIN CUBRIR EL TOBILLO, PARA DEPORTE O ENTRENAMIENTO, PARA HOMBRE"),
    ("NF0A3VY2", "JK3 TNF Black"): dict(
        nombre="Borealis backpack 28 L", tipo="mochila", estado="aprobado", codigo="420292",
        ficha={"genero": "U", "edadNac": "adulto", "tieneForro": True, "claseBolso": "mochila", "uso": "Daypack",
               "tallas": "One size", "comp": {"exterior": "100% polyester", "forro": "100% polyester"}},
        desc="MOCHILA CON SUPERFICIE EXTERIOR DE TEXTIL"),
    ("NF0A5IHO", "Heather grey"): dict(
        nombre="Glacier half-zip fleece", tipo="sudadera", estado="aprobado", codigo="611030",
        ficha={"genero": "U", "edad": "general", "edadNac": "adulto", "tejido": "punto", "hechuraSud": "pullover",
               "manga": "larga", "capucha": False, "sueter": False, "uso": "Mid layer fleece", "tallas": "S to L",
               "comp": {"exterior": "100% polyester"}},
        desc="SUDADERA DE TEXTIL, DE PUNTO, UNISEX"),
    ("VN000EE3", "BLK Black"): dict(
        nombre="Old Skool", tipo="calzado", estado="aprobado", codigo="640419",
        ficha={"genero": "U", "edadNac": "adulto", "estiloCalz": "tenis", "disenio": "casual", "altura": "bajo",
               "puntera": "ninguna", "impermeable": False, "suelaEspumosa": False, "uso": "Casual skate-style sneaker",
               "tallas": "7 to 12", "comp": {"corte": "65% canvas, 35% suede", "suela": "100% rubber",
                                             "forro": "100% cotton", "plantilla": "100% EVA"}},
        desc="TENIS CON CORTE DE TEXTIL Y SUELA DE SINTÉTICO, SIN CUBRIR EL TOBILLO, UNISEX"),
    ("VN0A4BV4", "White"): dict(
        nombre="Authentic", tipo="calzado", estado="sugerida", sugerido="640419",
        ficha={"genero": "U", "edadNac": "adulto", "estiloCalz": "tenis", "disenio": "casual", "altura": "bajo",
               "puntera": "ninguna", "impermeable": False, "suelaEspumosa": False, "uso": "Casual canvas sneaker",
               "tallas": "7 to 10", "comp": {"corte": "100% canvas", "suela": "100% rubber", "forro": "100% cotton",
                                             "plantilla": "100% EVA"}},
        desc="TENIS CON CORTE DE TEXTIL Y SUELA DE SINTÉTICO, SIN CUBRIR EL TOBILLO, UNISEX"),
}
PERFILES = {"chaqueta": "chaqueta|plano|M|-|-|sintetica|-|chaqueta", "mochila": "mochila|textil",
            "sudadera": "sudadera|punto|F|-|-|sintetica|-|pullover"}

# Prepacks: estilo, color, prepack ID (es la "talla" del artículo prepack), curva
PREPACKS = [
    ("VN000EE3", "BLK Black", "AB12", {"7": 1, "8": 2, "9": 3, "10": 3, "11": 2, "12": 1}),  # 12 pares
    ("VN0A4BV4", "White", "CD08", {"7": 2, "8": 2, "9": 2, "10": 2}),  # 8 pares
]


# Catálogo de pasos de lead time (cada empresa crea los suyos) y el hito medido que representan
PASOS_LT = [
    ("BOOKING", "Booking", None), ("LIB", "Logistics release", "lib_logistica"),
    ("PROD", "Production finished", None), ("CARGA", "Cargo ready", None), ("XF", "XF (ex-factory)", "xf"),
    ("ETD", "ETD (departure)", "salida"), ("ETA", "ETA (port arrival)", "arribo"), ("ADUANA", "Customs clearance", None),
    ("BODEGA", "Warehouse delivery", "entrega"), ("INGRESO", "Warehouse entry", "ingreso"),
    ("TIENDA", "Available in store", "tienda"),
]


def _p(paso, ref="", dias=0, habiles=False, modo=""):
    return {"paso": paso, "ref": ref, "dias": dias, "habiles": habiles, "modo": modo, "quitar": False}


# Reglas por nivel: cada una define solo lo que cambia frente al nivel superior
REGLAS_LT = [
    ("GLOBAL", None, "Global standard", [
        _p("BOOKING", "XF", -20), _p("LIB", "XF", -15), _p("PROD", "XF", -5), _p("CARGA", "XF", -2), _p("XF"),
        _p("ETD", "XF", 3), _p("ETA", "ETD", 14), _p("ADUANA", "ETA", 2, True), _p("BODEGA", "ADUANA", 1),
        _p("INGRESO", "BODEGA", 2, True), _p("TIENDA", "INGRESO", 4)]),
    ("REGION", "ASIA", "Asia", [
        _p("LIB", "XF", -21), _p("ETA", "ETD", 35), _p("ETA", "ETD", 5, modo="AEREO"), _p("TIENDA", "INGRESO", 5)]),
    ("REGION", "CAM", "Central America", [
        _p("ETA", "ETD", 5), _p("ADUANA", "ETA", 1, True), _p("TIENDA", "INGRESO", 3)]),
    ("PAIS", "VN", "Vietnam", [_p("LIB", "XF", -15)]),
    ("PUERTO", "VNSGN", "Cat Lai", [_p("LIB", "XF", -12)]),
]


def _momento(d: date, hora: int = 10) -> datetime:
    return datetime.combine(d, time(hora))


def _catalogos(db: Session) -> dict:
    db.add_all([
        RegionLeadTime(codigo="ASIA", nombre="Asia"),
        RegionLeadTime(codigo="CAM", nombre="Central America"),
        RegionLeadTime(codigo="OTROS", nombre="Other origins", predeterminada=True),
    ])
    db.add_all([PasoLeadTime(codigo=c, nombre=n, hito=h) for c, n, h in PASOS_LT])
    db.add_all([ReglaLeadTime(nivel=nv, nombre=nm, pasos=json.dumps({"pasos": ps, "orden": None}),
                              **({rlt.CAMPO_NIVEL[nv]: amb} if nv in rlt.CAMPO_NIVEL else {}))
                for nv, amb, nm, ps in REGLAS_LT])
    db.add_all([Pais(codigo=c, nombre=n, region=REGION_PAIS.get(c)) for c, n in PAISES])
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
        Almacen(codigo="BF19", sociedad_id=socs["8000"].id, nombre="Retail", tipo="DETALLE"),
        Almacen(codigo="BF20", sociedad_id=socs["8000"].id, nombre="Wholesale", tipo="MAYOREO"),
        Almacen(codigo="BF18", sociedad_id=socs["8000"].id, nombre="Virtual in transit", tipo="VIRTUAL"),
        Almacen(codigo="BF01", sociedad_id=socs["PA01"].id, nombre="Retail", tipo="DETALLE"),
        Almacen(codigo="BF02", sociedad_id=socs["PA01"].id, nombre="Wholesale", tipo="MAYOREO"),
    ])
    for nombre, cargo, rol, (tipo, codigo), correos, tel in CONTACTOS:
        db.add(Contacto(nombre=nombre, cargo=cargo, rol=rol, correos=correos, telefono=tel,
                        sociedad_id=socs[codigo].id if tipo == "sociedad" else None,
                        centro_id=centros[codigo].id if tipo == "centro" else None))
    puertos = {c: Puerto(codigo=c, nombre=n, pais=p, tipo="MARITIMO") for c, n, p in PUERTOS}
    puertos.update({c: Puerto(codigo=c, nombre=n, pais=p, tipo=t) for c, n, p, t in PUERTOS_OTROS})
    db.add_all(puertos.values())
    for c, lista in PUERTOS_CENTRO.items():
        centros[c].puertos = [puertos[x] for x in lista]
    db.add_all([TipoUnidad(codigo=c, nombre=n, modo=m, modalidad=md, capacidad_cbm=cbm, capacidad_kg=kg,
                           requiere_sello=sello) for c, n, m, md, cbm, kg, sello in TIPOS_UNIDAD])
    db.add_all([Transportista(codigo=c, nombre=n, tipo=t, codigo_internacional=ci, pais=pais, correos=correos,
                              sociedades=[socs[x] for x in lista]) for c, n, t, ci, pais, correos, lista in TRANSPORTISTAS])
    marcas = {c: Marca(codigo=c, nombre=n) for c, n in MARCAS}
    grupos = {c: GrupoArticulo(codigo=c, nombre=n, categoria=cat) for c, n, cat in GRUPOS}
    # Escalas de tallas reutilizables (ejemplos; cada empresa crea las suyas)
    db.add_all([
        EscalaTalla(codigo="US-CALZ", nombre="US footwear (half sizes)", categoria="CALZADO", regla="MULTIPLICAR", factor=10,
                    longitud=3, tallas="5-12.5, 13"),
        EscalaTalla(codigo="US-CALZ-ENT", nombre="US footwear (whole sizes)", categoria="CALZADO", regla="MULTIPLICAR", factor=10,
                    longitud=3, tallas="6-13"),
        EscalaTalla(codigo="LETRAS", nombre="Apparel letters", categoria="ROPA", regla="CONSECUTIVO", longitud=3,
                    tallas="XXS, XS, S, M, L, XL, XXL, XXXL"),
        EscalaTalla(codigo="CINTURA", nombre="Waist (inches)", categoria="ROPA", regla="TALLA", tallas="28, 29, 30, 31, 32, 33, 34, 36, 38, 40"),
        EscalaTalla(codigo="UNICA", nombre="One size", categoria="ACCESORIO", regla="CONSECUTIVO", longitud=3, tallas="OS=000"),
    ])
    db.add_all([*marcas.values(), *grupos.values()])
    db.flush()
    return {"marcas": marcas, "grupos": grupos, "sociedades": socs}


# Peso neto de una unidad por grupo (kg); el empaque suma su propia tara
PESO_GRUPO = {"CALZ-OUT": 0.9, "CALZ-CAS": 0.8, "CHAQ": 0.9, "FLEE": 0.5, "MOCH": 0.8}
# Tipos de empaque de ejemplo: cada empresa define los suyos
TIPOS_EMPAQUE = [
    # código, nombre, nivel, prefijo, cuenta como, medidas, tara, peso máx., lleva producto
    ("INNER", "Inner pack", 1, "PK", "INTERIOR", None, 0.05, None, True),
    ("CAJA", "Master carton", 2, "C", "BULTO", (60, 40, 40), 0.7, 30, True),
    ("PALLET", "Pallet", 3, "P", "SOPORTE", (120, 100, 15), 20, 1000, False),
]


def _tipos_empaque(db: Session) -> dict:
    tipos = {}
    for cod, nom, nivel, pre, cuenta, medidas, tara, maximo, producto in TIPOS_EMPAQUE:
        largo, ancho, alto = medidas or (None, None, None)
        tipos[cod] = TipoEmpaque(codigo=cod, nombre=nom, nivel=nivel, prefijo=pre, cuenta_como=cuenta, largo=largo,
                                 ancho=ancho, alto=alto, tara=tara, peso_max=maximo, contiene_productos=producto,
                                 identificador="SSCC" if cuenta != "INTERIOR" else None)
    tipos["CAJA"].contiene = [tipos["INNER"]]
    tipos["PALLET"].contiene = [tipos["CAJA"]]
    db.add_all(tipos.values())
    db.flush()
    return tipos


def _articulos(db: Session, cat: dict, proveedores: dict) -> dict:
    """Maestro de artículos: sólidos (con casepack en calzado, sin casepack en
    ropa) con un número de artículo por estilo-color-talla, y prepacks cuya
    talla es su prepack ID."""
    arts = {}
    # Datos de ejemplo: el código de artículo de esta empresa demo es el genérico
    # (estilo-color) más un código de talla; cada empresa usa su propio formato
    genericos = {}
    for n, (estilo, color, marca, grupo, prov, unidad, precio, origen, partida, desc, empaque, tallas) in enumerate(ESTILOS):
        gen = str(30095120 + n)
        genericos[(estilo, color)] = [gen, set()]
        for talla in tallas:
            # Calzado: la talla por 10 (7 → 070, 10 → 100); letras: 001, 002…
            suf = sufijo_convencional(talla) or next(f"{i:03d}" for i in range(1, 1000)
                                                     if f"{i:03d}" not in genericos[(estilo, color)][1])
            genericos[(estilo, color)][1].add(suf)
            sku = f"{gen}{suf}"
            a = Articulo(sku=sku, generico=gen, sku_proveedor=_sku_proveedor(estilo, color, talla), upc=f"0196{int(sku) % 10**8:08d}",
                         estilo=estilo, color=color, talla=talla,
                         descripcion=desc, marca_id=cat["marcas"][marca].id, grupo_id=cat["grupos"][grupo].id,
                         proveedor_id=proveedores[prov].id, unidad=unidad, tipo="SOLIDO",
                         peso_unitario=PESO_GRUPO.get(grupo))
            a.precio_demo = precio
            a.origen_demo = origen
            a.partida_demo = partida
            a.empaque_demo = empaque or (None, None)
            arts[(estilo, color, talla)] = a
    db.add_all(arts.values())
    db.flush()
    for estilo, color, codigo, curva in PREPACKS:
        base = arts[(estilo, color, next(iter(curva)))]
        pp = Prepack(codigo=codigo, estilo=estilo, color=color,
                     descripcion=f"Assortment {estilo} {color} sizes {'-'.join(curva)} ({sum(curva.values())} pairs)")
        for talla, cant in curva.items():
            pp.componentes.append(PrepackComponente(articulo_id=arts[(estilo, color, talla)].id, cantidad=cant))
        db.add(pp)
        db.flush()
        gen = genericos[(estilo, color)]
        suf = next(f"{i:03d}" for i in range(1, 1000) if f"{i:03d}" not in gen[1])
        gen[1].add(suf)
        a = Articulo(sku=f"{gen[0]}{suf}", generico=gen[0], sku_proveedor=_sku_proveedor(estilo, color, codigo), estilo=estilo,
                     color=color, talla=codigo,
                     descripcion=f"{base.descripcion}, prepack {codigo}", marca_id=base.marca_id,
                     grupo_id=base.grupo_id, proveedor_id=base.proveedor_id, unidad="CJ", tipo="PREPACK",
                     prepack_id=pp.id)
        a.origen_demo = base.origen_demo
        a.partida_demo = base.partida_demo
        a.precio_demo = base.precio_demo * sum(curva.values())
        a.empaque_demo = (None, None)
        db.add(a)
        db.flush()
        arts[(estilo, color, codigo)] = a
    _productos(db, arts)
    return arts


def _sku_proveedor(estilo: str, color: str, talla: str) -> str:
    """SKU del proveedor: estilo + código de color + talla (distinto del código de artículo)."""
    primera = (color or "").split()[0] if color else ""
    cod = primera.upper() if len(primera) <= 3 else primera[:3].upper()
    return f"{estilo}{cod}-{talla}".replace(" ", "")


def _productos(db, arts) -> None:
    """Cada estilo-color es un producto con su ficha técnica y su clasificación."""
    from .models import Usuario as U

    interno = db.scalar(select(U).where(U.rol == "interno"))
    for a in arts.values():
        asegurar_producto(db, a)
    db.flush()
    for (estilo, color), x in FICHAS.items():
        a = next(v for k, v in arts.items() if k[0] == estilo and k[1] == color)
        p = a.producto
        p.nombre, p.tipo, p.ficha = x["nombre"], x["tipo"], x["ficha"]
        p.pais_origen = p.pais_procedencia = a.origen_demo
        p.descripcion_aduana = x.get("desc")
        p.faltan = x.get("faltan", [])
        p.ficha_completa = not p.faltan
        p.observaciones = x.get("observaciones")
        p.vigente_desde = date.today() - timedelta(days=200)
        p.descripcion_comercial = descripcion_comercial_simple(p)
        f = x["ficha"]
        p.perfil = PERFILES.get(p.tipo) or (
            f"calzado|{f.get('estiloCalz')}|textil|caucho|{f.get('altura')}|{f.get('disenio')}|-|-" if p.tipo == "calzado" else None)
        if x.get("codigo"):
            p.sugerido = p.codigo = x["codigo"]
            p.confianza, p.fuente, p.estado = "high", "regla", "aprobado"
            p.revisado_por_id = interno.id if interno else None
            p.revisado_en = ahora() - timedelta(days=150)
            _guardar_partidas(p, partidas_simples(db, p, p.codigo))
        else:
            p.sugerido = x.get("sugerido")
            p.estado = x["estado"]
            p.confianza = "high" if p.sugerido else None
            if p.sugerido:
                _guardar_partidas(p, partidas_simples(db, p, p.sugerido))


def _oc(db, prov, arts, numero, fecha, lineas, sociedad="8000", centro="8010", almacen="BF19", destino="2220",
        puerto="VNSGN", origen="VN", xf=None, xf_nueva=None, tienda=None, comercial="C", logistica="300",
        lib_antes=24):
    """lineas: [(estilo, color, [(talla, cantidad), ...], almacén opcional)]; posiciones de 10 en 10.
    lib_antes: días antes de la XF en que logística liberó la OC (Asia pide 21).
    Cada posición puede ir a un almacén distinto dentro de la misma sociedad y centro."""
    oc = OrdenCompra(proveedor_id=prov.id, numero=numero, sociedad=sociedad, centro=centro,
                     centro_destino=destino, moneda="USD", incoterm="FOB", fecha=fecha, puerto_despacho=puerto,
                     pais_origen=origen, pais_procedencia=origen, fecha_xf_original=xf, fecha_xf=xf_nueva or xf,
                     fecha_tienda=tienda, liberacion_comercial=comercial, liberacion_logistica=logistica,
                     liberada=comercial == "C" and logistica in ("300", "301"))
    if comercial == "C":
        oc.fecha_lib_comercial = min(fecha + timedelta(days=3), date.today())
        if logistica in ("300", "301") and oc.fecha_xf:
            oc.fecha_lib_logistica = min(max(oc.fecha_xf - timedelta(days=lib_antes), oc.fecha_lib_comercial), date.today())
    db.add(oc)
    pos = 10
    for estilo, color, tallas, *alm in lineas:
        for talla, cantidad in tallas:
            a = arts[(estilo, color, talla)]
            oc.posiciones.append(PosicionOC(
                posicion=str(pos), almacen=alm[0] if alm else almacen, articulo_id=a.id, codigo_sap=a.sku, upc=a.upc, estilo=a.estilo, color=a.color,
                talla=a.talla, descripcion=a.descripcion, marca=a.marca.codigo, grupo=a.grupo.codigo,
                categoria=a.grupo.categoria, tipo_empaque=a.tipo, casepack=a.empaque_demo[0], inner_pack=a.empaque_demo[1],
                prepack=a.prepack.codigo if a.prepack else None,
                unidades_por_caja=a.prepack.total if a.prepack else None, cantidad=cantidad, unidad=a.unidad,
                precio=a.precio_demo, fecha_entrega=xf, pais_origen=a.origen_demo,
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
                             casepack=p.casepack, inner_pack=p.inner_pack, centro_destino=oc.centro_destino, pais_origen=p.pais_origen,
                             partida_arancelaria=partida_para(p.articulo.producto, "SV") or p.articulo.partida_demo,
                             descripcion_comercial=p.articulo.producto.descripcion_aduana or p.descripcion)
        f.lineas.append(linea)
        pll = PLLinea(factura_linea=linea, cantidad=p.cantidad)
        pl.lineas.append(pll)
        t = plantillas[p.estilo]
        g = GrupoCajas(num_cajas=p.cantidad // t.cantidad_por_caja, largo=t.largo, ancho=t.ancho, alto=t.alto,
                       tara=t.tara, tipo_empaque=t.tipo_empaque, plantilla_id=t.id, plantilla_nombre=t.nombre)
        pl.grupos.append(g)
        n = p.inner_pack if p.tipo_empaque != "PREPACK" else None
        if n and t.cantidad_por_caja % n == 0 and t.tipo_empaque:
            # Inner packs físicos dentro de cada caja, con su tara
            inner = empaques.tipo_interior(t.tipo_empaque)
            h = GrupoCajas(num_cajas=g.num_cajas * t.cantidad_por_caja // n, tipo_empaque=inner, padre=g, tara=inner.tara)
            h.items.append(GrupoCajasItem(pl_linea=pll, cantidad_por_caja=n))
            pl.grupos.append(h)
        else:
            g.items.append(GrupoCajasItem(pl_linea=pll, cantidad_por_caja=t.cantidad_por_caja))
    if pallet:
        # Todo el PL en un pallet estándar: el pallet armado mide 160 cm de alto
        tipo = db.scalar(select(TipoEmpaque).where(TipoEmpaque.codigo == "PALLET"))
        tarima = GrupoCajas(num_cajas=1, tipo_empaque=tipo, largo=120, ancho=100, alto=160, tara=tipo.tara)
        for g in [x for x in pl.grupos if x.padre is None]:
            g.padre = tarima
        pl.grupos.append(tarima)
    db.add(f)
    db.flush()
    empaques.recalcular(pl)
    registrar(db, usuario, "factura", f.id, "crear", {"lineas": len(f.lineas), "ocs": [oc.numero]}, factura_id=f.id)
    registrar(db, usuario, "packing_list", pl.id, "aplicar_plantilla", {"plantillas": sorted(
        {plantillas[p.estilo].nombre for p in oc.posiciones})}, factura_id=f.id)
    registrar(db, usuario, "factura", f.id, "finalizar", {"con_pl": [pl.numero]}, factura_id=f.id)
    return f


def _historial_demo(db, hoy, tnf, vans, usuarios, plantillas, arts):
    """Meses anteriores ya facturados y embarcados, para que el tablero tenga
    historia: un contenedor recibido, otro en tránsito y una factura lista
    para embarcar."""
    recibido = Embarque(codigo="EMB-0001", tipo_transporte="MARITIMO", transportista="Maersk",
                        documento_numero="MAEU 221877310", puerto_origen="VNCMT", puerto_destino="SVAQJ", centro="8010",
                        etd=hoy - timedelta(days=88), eta=hoy - timedelta(days=58),
                        salida_real=hoy - timedelta(days=87), arribo_real=hoy - timedelta(days=57), estado="RECIBIDO")
    c1 = UnidadCarga(tipo="40HC", etiqueta="40HC #1", numero="MSKU 481220-7", sello="ML-99812")
    recibido.unidades.append(c1)
    for tipo, dias, lugar in (("RECOLECCION", 90, "Supplier warehouse"), ("SALIDA", 87, "Cai Mep (VN)"),
                              ("ARRIBO", 57, "Acajutla (SV)"), ("ENTREGA", 55, "Bonded warehouse 8010"),
                              ("RECEPCION", 54, "Bonded warehouse 8010")):
        recibido.eventos.append(EventoEmbarque(tipo=tipo, fecha=_momento(hoy - timedelta(days=dias), 9), ubicacion=lugar))
    transito = Embarque(codigo="EMB-0002", tipo_transporte="MARITIMO", transportista="COSCO Shipping",
                        documento_numero="COSU 640018225", puerto_origen="CNYTN", puerto_destino="SVAQJ", centro="8010",
                        etd=hoy - timedelta(days=19), eta=hoy + timedelta(days=9),
                        salida_real=hoy - timedelta(days=18), estado="EN_TRANSITO")
    c2 = UnidadCarga(tipo="40GP", etiqueta="40GP #1", numero="TGHU 772104-3", sello="CS-10442")
    transito.unidades.append(c2)
    transito.eventos.append(EventoEmbarque(tipo="RECOLECCION", fecha=_momento(hoy - timedelta(days=21), 8),
                                           ubicacion="Supplier warehouse"))
    transito.eventos.append(EventoEmbarque(tipo="SALIDA", fecha=_momento(hoy - timedelta(days=18), 7),
                                           ubicacion="Yantian (CN)"))
    transito.eventos.append(EventoEmbarque(tipo="TRANSITO", fecha=_momento(hoy - timedelta(days=6), 12),
                                           ubicacion="Panama Canal, Pacific side", observacion="No issues"))
    db.add_all([recibido, transito])

    u_tnf, u_vans = usuarios
    d = lambda n: hoy - timedelta(days=n)  # noqa: E731
    historicas = [
        (tnf, "4400003701", 140, [("NF0A5GLL", "JK3 TNF Black", [("M", 50), ("L", 50)])], "TNF-2026-0418", 128, c1, 90),
        (tnf, "4400003702", 115, [("NF0A3VY2", "JK3 TNF Black", [("OS", 80)])], "TNF-2026-0502", 100, c1, 90),
        (vans, "4400003751", 110, [("VN000EE3", "BLK Black", [("8", 60)])], "VN-88120", 95, c1, 90),
        (tnf, "4400003703", 85, [("NF0A7W4G", "KX7 Black", [("9", 36), ("10", 48)])], "TNF-2026-0611", 70, c2, 21),
        (vans, "4400003752", 50, [("VN000EE3", "BLK Black", [("9", 72)])], "VN-88177", 35, c2, 21),
        (tnf, "4400003704", 20, [("NF0A5IHO", "Heather grey", [("S", 30), ("M", 30)])], "TNF-2026-0915", 6, None, None),
    ]
    for prov, numero, dias_oc, lineas, factura, dias_factura, unidad, recoleccion in historicas:
        # Algunas liberaciones logísticas tarde (Asia pide 21 días antes de la XF)
        lib_antes = {"4400003702": 16, "4400003752": 12, "4400003703": 23}.get(numero, 26)
        # XF poco antes de la recolección; OC creada ~80 días antes de la XF; fecha en tienda
        # según la llegada de su contenedor (unas a tiempo, una tarde)
        xf = d(recoleccion + 2) if recoleccion else d(dias_factura - 2)
        tienda = {"4400003701": d(40), "4400003702": d(50), "4400003751": d(35), "4400003703": d(-25),
                  "4400003752": d(-35)}.get(numero, d(dias_factura - 60))
        oc = _oc(db, prov, arts, numero, min(d(dias_oc), xf - timedelta(days=80)), lineas, xf=xf, tienda=tienda,
                 puerto="CNYTN" if unidad is c2 else "VNCMT", origen="CN" if unidad is c2 else "VN", lib_antes=lib_antes)
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
    tnf = Proveedor(codigo="TNF", nombre="The North Face", razon_social="VF Outdoor Asia Sourcing Ltd.",
                    id_fiscal="HK-51902231", pais="VN", direccion="Lot C-5, Tan Thuan EPZ, Ho Chi Minh, Vietnam",
                    contacto="Linh Nguyen", correos="export.tnf@vf.demo", telefono="+84 28 3770 1234")
    vans = Proveedor(codigo="VANS", nombre="Vans", razon_social="Vans Footwear Sourcing Co.",
                     id_fiscal="CN-91440300", pais="CN", direccion="Nanshan District, Shenzhen, China",
                     contacto="Wei Chen", correos="export.vans@vans.demo", telefono="+86 755 2660 8899")
    db.add_all([tnf, vans])
    db.flush()
    # Roles de fábrica y uno de ejemplo; todos con celular y verificación en dos pasos
    roles = crear_roles_fabrica(db)
    db.add(Rol(nombre="Supplier (view only)", tipo="proveedor", sistema=False,
               descripcion="Sees its POs and technical sheets; cannot invoice or edit.",
               permisos=["oc.ver", "producto.ver"]))
    pw = hash_password(PASSWORD_DEMO)
    u_tnf = Usuario(email="tnf@demo.com", nombre="TNF supplier", rol="proveedor", rol_id=roles["proveedor"].id,
                    proveedor_id=tnf.id, password_hash=pw, telefono="+84283770001",
                    cargo="Export coordinator", area="Logistics", empresa="The North Face (VF Asia)")
    u_vans = Usuario(email="vans@demo.com", nombre="Vans supplier", rol="proveedor", rol_id=roles["proveedor"].id,
                     proveedor_id=vans.id, password_hash=pw, telefono="+867552660001",
                     cargo="Shipping specialist", area="Export operations", empresa="Vans (VF China)")
    db.add_all([
        Usuario(email="admin@demo.com", nombre="Administrator", rol="admin", rol_id=roles["admin"].id, password_hash=pw,
                telefono="+50370000001", cargo="Systems administrator", area="IT", empresa="Distribuidora de Marcas"),
        Usuario(email="interno@demo.com", nombre="Import team", rol="interno", rol_id=roles["interno"].id, password_hash=pw,
                telefono="+50370000002", cargo="Imports analyst", area="Imports and customs", empresa="Distribuidora de Marcas"),
        u_tnf,
        u_vans,
    ])
    db.flush()
    cat = _catalogos(db)
    cargar_incisos_base(db)
    # Cada proveedor maneja sus marcas y trabaja con sus sociedades
    tnf.marcas = [cat["marcas"]["TNF"]]
    vans.marcas = [cat["marcas"]["VANS"]]
    tnf.sociedades = [cat["sociedades"]["8000"], cat["sociedades"]["PA01"]]
    vans.sociedades = [cat["sociedades"]["8000"], cat["sociedades"]["PA01"]]
    db.flush()
    arts = _articulos(db, cat, {"TNF": tnf, "VANS": vans})
    tipos = _tipos_empaque(db)
    hoy = date.today()
    d = lambda n: hoy + timedelta(days=n)  # noqa: E731

    _oc(db, tnf, arts, "4400003845", d(-20), [
        ("NF0A5GLL", "JK3 TNF Black", [("S", 40), ("M", 60), ("L", 60), ("XL", 27), ("XXL", 20)]),
        ("NF0A7W4G", "KX7 Black", [("8", 24), ("9", 36), ("10", 50), ("11", 36), ("12", 12)], "BF20"),
    ], xf=d(10), xf_nueva=d(14), tienda=d(75))
    _oc(db, tnf, arts, "4400003846", d(-12), [
        ("NF0A3VY2", "JK3 TNF Black", [("OS", 120)]),
        ("NF0A5IHO", "Heather grey", [("S", 30), ("M", 30), ("L", 30)]),
    ], puerto="CNYTN", origen="ID", xf=d(18), tienda=d(80))
    _oc(db, tnf, arts, "4400003850", d(-8), [("NF0A5GLL", "Summit blue", [("M", 30), ("L", 30)])],
        sociedad="PA01", centro="PA10", almacen="BF01", destino="5910", puerto="SVAQJ", origen="SV", xf=d(20),
        tienda=d(70), lib_antes=18)
    _oc(db, tnf, arts, "4400003851", d(-2), [("NF0A5IHO", "Heather grey", [("S", 20), ("M", 20)])],
        origen="KH", puerto="KHKOS", xf=d(35), tienda=d(100), comercial="P", logistica="304")
    _oc(db, vans, arts, "4400003901", d(-15), [
        ("VN000EE3", "BLK Black", [("7", 36), ("8", 48), ("9", 60)], "BF19"),
        ("VN000EE3", "BLK Black", [("10", 48), ("11", 24)]),
    ], centro="8020", almacen="BF20", xf=d(12), tienda=d(60), lib_antes=10)
    _oc(db, vans, arts, "4400003902", d(-5), [("VN0A4BV4", "White", [("7", 24), ("8", 24), ("9", 24), ("10", 24)])],
        centro="8020", almacen="BF20", puerto="CNSHA", origen="CN", xf=d(25), xf_nueva=d(22), tienda=d(90),
        logistica="301")
    _oc(db, vans, arts, "4400003903", d(-4), [("VN000EE3", "BLK Black", [("AB12", 10)]),
                                              ("VN0A4BV4", "White", [("CD08", 6)])],
        centro="8020", almacen="BF20", destino="3200", xf=d(15), tienda=d(65))
    _oc(db, vans, arts, "4400003904", d(-1), [("VN0A4BV4", "White", [("8", 24)])],
        centro="8020", almacen="BF20", puerto="CNSHA", origen="CN", xf=d(40), tienda=d(110), comercial="P",
        logistica="304")

    chaqueta = PlantillaCaja(proveedor_id=tnf.id, nombre="Jacket carton 10 units", cantidad_por_caja=10, unidad="UN",
                             largo=60, ancho=40, alto=40, tara=1.2, tipo_empaque=tipos["CAJA"])
    calzado = PlantillaCaja(proveedor_id=tnf.id, nombre="Footwear carton 12 pairs", cantidad_por_caja=12, unidad="PAR",
                            largo=55, ancho=35, alto=33, tara=1.5, tipo_empaque=tipos["CAJA"])
    mochila = PlantillaCaja(proveedor_id=tnf.id, nombre="Backpack carton 20 units", cantidad_por_caja=20, unidad="UN",
                            largo=70, ancho=50, alto=45, tara=1.5, tipo_empaque=tipos["CAJA"])
    fleece = PlantillaCaja(proveedor_id=tnf.id, nombre="Fleece carton 15 units", cantidad_por_caja=15, unidad="UN",
                           largo=60, ancho=40, alto=35, tara=1.1, tipo_empaque=tipos["CAJA"])
    master12 = PlantillaCaja(proveedor_id=vans.id, nombre="Master 12 pairs", cantidad_por_caja=12, unidad="PAR",
                             largo=60, ancho=38, alto=35, tara=1.4, tipo_empaque=tipos["CAJA"])
    master10 = PlantillaCaja(proveedor_id=vans.id, nombre="Master 10 pairs", cantidad_por_caja=10, unidad="PAR",
                             largo=55, ancho=38, alto=32, tara=1.2, tipo_empaque=tipos["CAJA"])
    prepack = PlantillaCaja(proveedor_id=vans.id, nombre="Master prepack (1 assortment)", cantidad_por_caja=1, unidad="CJ",
                            largo=60, ancho=38, alto=35, tara=1.4, tipo_empaque=tipos["CAJA"])
    db.add_all([chaqueta, calzado, mochila, fleece, master12, master10, prepack])
    db.flush()
    _historial_demo(db, hoy, tnf, vans, (u_tnf, u_vans), {
        "NF0A5GLL": chaqueta, "NF0A3VY2": mochila, "NF0A7W4G": calzado, "NF0A5IHO": fleece, "VN000EE3": master12},
        arts)
    e = Embarque(codigo="EMB-0003", tipo_transporte="MARITIMO", transportista="Maersk",
                 puerto_origen="VNSGN", puerto_destino="SVAQJ",
                 etd=hoy + timedelta(days=12), eta=hoy + timedelta(days=42))
    e.unidades.append(UnidadCarga(tipo="40HC", etiqueta="40HC #1"))
    # Embarque mixto: un contenedor completo (FCL) y carga consolidada (LCL)
    e.unidades.append(UnidadCarga(tipo="LCL", etiqueta="LCL #1"))
    db.add(e)
    db.flush()
    trans = {t.nombre: t.id for t in db.scalars(select(Transportista))}
    for emb in db.scalars(select(Embarque)):
        emb.transportista_id = trans.get(emb.transportista)
    db.commit()


if __name__ == "__main__":
    from .db import Base, SessionLocal, engine

    Base.metadata.create_all(engine)
    with SessionLocal() as s:
        seed(s)
    print("Demo data loaded.")
