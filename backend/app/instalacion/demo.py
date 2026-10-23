"""Datos de demostración. Se cargan solo si la base está vacía.
Uso manual: python -m app.instalacion.demo"""
from datetime import date, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.seguridad import hash_password
from app.modelos import (
    Almacen,
    Articulo,
    Atributo,
    Centro,
    Contacto,
    Embarque,
    EscalaValores,
    EventoEmbarque,
    Factura,
    FacturaLinea,
    GrupoCajas,
    GrupoCajasItem,
    Marca,
    Meta,
    OrdenCompra,
    PackingList,
    Pais,
    PasoLeadTime,
    PlantillaCaja,
    PLLinea,
    PosicionOC,
    Producto,
    Proveedor,
    Puerto,
    RecepcionLinea,
    RecepcionMovimiento,
    RecepcionRegistro,
    RegionLeadTime,
    ReglaLeadTime,
    Rol,
    Sociedad,
    TipoEmpaque,
    TipoUnidad,
    Transportista,
    UnidadCarga,
    Usuario,
    ahora,
)
from app.modulos.acceso.roles import crear_roles_fabrica, crear_roles_sugeridos
from app.modulos.comun.historial import registrar
from app.modulos.empaque import empaques
from app.modulos.maestros import escalas
from app.modulos.productos.productos import (
    _aprobar,
    clasificar_y_guardar,
    descripcion_comercial_simple,
    partida_para,
)
from app.modulos.transporte import reglas_lt as rlt

PAISES = [
    ("VN", "Vietnam"), ("CN", "China"), ("ID", "Indonesia"), ("KH", "Cambodia"), ("BD", "Bangladesh"),
    ("IN", "India"), ("SV", "El Salvador"), ("PA", "Panama"), ("GT", "Guatemala"), ("HN", "Honduras"),
    ("CR", "Costa Rica"), ("NI", "Nicaragua"), ("US", "United States"), ("MX", "Mexico"), ("BR", "Brazil"),
    ("HK", "Hong Kong"), ("CO", "Colombia"), ("DK", "Denmark"), ("FR", "France"),
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
# Cuentas que la pantalla de ingreso ofrece en la demostración (correo, rol, nombre)
CUENTAS_DEMO = [["tnf@demo.com", "Supplier", "The North Face"], ["vans@demo.com", "Supplier", "Vans"],
                ["interno@demo.com", "Imports", "Internal team"], ["admin@demo.com", "Administrator", "Full access"]]
MARCAS = [("TNF", "The North Face"), ("VANS", "Vans"), ("MERR", "Merrell"), ("CAT", "Caterpillar"),
          ("HPU", "Hush Puppies"), ("CASA", "House brand")]
# La regla de código de variante de la empresa de ejemplo (Configuración de productos)
REGLA_CODIGO = {"regla": "MULTIPLICAR", "factor": 10, "longitud": 3}
# Familias de producto de la empresa de ejemplo: código, nombre, familia padre, descripción
FAMILIAS = [
    ("FOOTWEAR", "Footwear", None, "Shoes and sandals: hang tag with size and color."),
    ("FOOTWEAR-TECH", "Technical footwear", "FOOTWEAR", "Trail and running footwear (inherits the footwear designs)."),
    ("APPAREL", "Apparel", None, "Jackets and fleece."),
    ("ACCESSORIES", "Bags and accessories", None, "Backpacks and bags: by color, without sizes."),
]
# Atributos de esta empresa de ejemplo (cada empresa define los suyos en Datos maestros → Atributos):
# código, nombre, nivel, tipo, catálogo, opciones, orden y sus familias (None = todas). La marca es la
# que apunta al catálogo de marcas. Cada familia lleva solo los suyos: el calzado, su material del
# corte y su talla; los accesorios, su capacidad y su color, sin talla.
ATRIBUTOS = [
    ("MARCA", "Brand", "PRODUCTO", "catalogo", "marcas", None, 1, None),
    ("MODELO", "Style", "PRODUCTO", "texto", None, None, 2, None),
    ("GENERO", "Gender", "PRODUCTO", "opcion", None, "Men, Women, Unisex, Kids", 3, ["FOOTWEAR", "APPAREL"]),
    ("CORTE", "Upper material", "PRODUCTO", "opcion", None, "Textile, Leather, Synthetic, Mixed", 4, ["FOOTWEAR"]),
    ("CAPACIDAD", "Capacity (liters)", "PRODUCTO", "numero", None, None, 5, ["ACCESSORIES"]),
    ("COLOR", "Color", "VARIANTE", "texto", None, None, 1, ["FOOTWEAR", "APPAREL", "ACCESSORIES"]),
    ("TALLA", "Size", "VARIANTE", "texto", None, None, 2, ["FOOTWEAR", "APPAREL"]),
]
# Cada fila es un producto (un estilo, con su familia y sus atributos propios) y cada valor, una variante
# (color y talla, o solo color en los accesorios): estilo, color, marca, peso neto por unidad (kg),
# proveedor, unidad, precio, origen, partida, descripción, empaque de la OC, tallas (None: sin talla),
# familia y atributos de su familia. El empaque (casepack, inner pack) es de la posición de la OC, no
# del artículo: aquí solo es el que usan las OCs de ejemplo.
ESTILOS = [
    ("NF0A5GLL", "JK3 TNF Black", "TNF", 0.9, "TNF", "UN", 48.50, "VN", "6201.40", "Men's waterproof jacket",
     None, ["S", "M", "L", "XL", "XXL"], "APPAREL", {"GENERO": "Men"}),
    ("NF0A84KD", "Summit blue", "TNF", 0.9, "TNF", "UN", 48.50, "VN", "6201.40", "Women's waterproof jacket",
     None, ["M", "L"], "APPAREL", {"GENERO": "Women"}),
    ("NF0A7W4G", "KX7 Black", "TNF", 0.9, "TNF", "PAR", 62.00, "CN", "6404.11", "Trail running footwear",
     (12, None), ["8", "9", "10", "11", "12"], "FOOTWEAR-TECH", {"GENERO": "Men", "CORTE": "Textile"}),
    ("NF0A3VY2", "JK3 TNF Black", "TNF", 0.8, "TNF", "UN", 31.20, "ID", "4202.92", "Backpack 28 L", (20, 5),
     None, "ACCESSORIES", {"CAPACIDAD": "28"}),
    ("NF0A5IHO", "Heather grey", "TNF", 0.5, "TNF", "UN", 22.75, "KH", "6110.30", "Half-zip fleece",
     (None, 5), ["S", "M", "L"], "APPAREL", {"GENERO": "Unisex"}),
    ("VN000EE3", "BLK Black", "VANS", 0.8, "VANS", "PAR", 25.50, "VN", "6404.19", "Classic canvas footwear",
     (12, None), ["7", "8", "9", "10", "11", "12"], "FOOTWEAR", {"GENERO": "Unisex", "CORTE": "Mixed"}),
    ("VN0A4BV4", "White", "VANS", 0.8, "VANS", "PAR", 21.00, "CN", "6404.19", "Basic canvas footwear",
     (12, None), ["7", "8", "9", "10"], "FOOTWEAR", {"GENERO": "Unisex", "CORTE": "Textile"}),
]
# Ficha técnica y clasificación de cada estilo-color (producto). La partida
# aprobada es la que saca el motor de clasificación con esta ficha; el código
# nacional de cada país sale de la base de incisos.
FICHAS = {
    ("NF0A5GLL", "JK3 TNF Black"): dict(
        nombre="Men's Antora rain jacket", tipo="chaqueta", estado="aprobado", codigo="620140",
        ficha={"genero": "M", "edad": "adulto", "materia_base": "textil", "tejido": "plano", "recubierta": False,
               "uso": "Waterproof shell jacket for hiking", "tallas": "S to XXL",
               "comp": {"exterior": "100% nylon", "forro": "100% polyester"}},
        desc="CHAQUETA DE TEXTIL, DE TEJIDO PLANO, PARA HOMBRE"),
    ("NF0A84KD", "Summit blue"): dict(
        nombre="Women's Antora rain jacket", tipo="chaqueta", estado="observado",
        ficha={"genero": "F", "edad": "adulto", "materia_base": "textil", "tejido": "plano",
               "uso": "Waterproof shell jacket for hiking", "tallas": "M to L", "comp": {}},
        faltan=["Composition: outer fabric or surface"],
        observaciones="Send the shell composition. If the coating is visible on the outside it goes in 6210; "
                      "if it is a hidden membrane, in 6201."),
    ("NF0A7W4G", "KX7 Black"): dict(
        nombre="Men's Vectiv trail running shoe", tipo="calzado", estado="aprobado", codigo="640411",
        ficha={"genero": "M", "edad": "adulto", "estilo_calzado": "tenis", "uso_deportivo": "entrenamiento", "uso": "Trail running shoe",
               "tallas": "8 to 12", "comp": {"corte": "80% textile, 20% synthetic", "suela": "100% rubber",
                                             "forro": "100% polyester", "plantilla": "100% EVA"}},
        desc="TENIS CON CORTE DE TEXTIL Y SUELA DE SINTÉTICO, SIN CUBRIR EL TOBILLO, PARA DEPORTE O ENTRENAMIENTO, PARA HOMBRE"),
    ("NF0A3VY2", "JK3 TNF Black"): dict(
        nombre="Borealis backpack 28 L", tipo="mochila", estado="aprobado", codigo="420292",
        ficha={"uso": "Daypack",
               "tallas": "One size", "comp": {"exterior": "100% polyester", "forro": "100% polyester"}},
        desc="MOCHILA CON SUPERFICIE EXTERIOR DE TEXTIL"),
    ("NF0A5IHO", "Heather grey"): dict(
        nombre="Glacier half-zip fleece", tipo="sueter", estado="aprobado", codigo="611030",
        ficha={"genero": "U", "edad": "adulto", "materia_base": "textil", "tejido": "punto", "recubierta": False, "uso": "Mid layer fleece", "tallas": "S to L",
               "comp": {"exterior": "100% polyester"}},
        desc="SUDADERA DE TEXTIL, DE PUNTO, UNISEX"),
    ("VN000EE3", "BLK Black"): dict(
        nombre="Old Skool", tipo="calzado", estado="aprobado", codigo="640419",
        ficha={"genero": "U", "edad": "adulto", "estilo_calzado": "tenis", "uso_deportivo": "no", "uso": "Casual skate-style sneaker",
               "tallas": "7 to 12", "comp": {"corte": "65% canvas, 35% suede", "suela": "100% rubber",
                                             "forro": "100% cotton", "plantilla": "100% EVA"}},
        desc="TENIS CON CORTE DE TEXTIL Y SUELA DE SINTÉTICO, SIN CUBRIR EL TOBILLO, UNISEX"),
    ("VN0A4BV4", "White"): dict(
        nombre="Authentic", tipo="calzado", estado="sugerida", sugerido="640419",
        ficha={"genero": "U", "edad": "adulto", "estilo_calzado": "tenis", "uso_deportivo": "no", "uso": "Casual canvas sneaker",
               "tallas": "7 to 10", "comp": {"corte": "100% canvas", "suela": "100% rubber", "forro": "100% cotton",
                                             "plantilla": "100% EVA"}},
        desc="TENIS CON CORTE DE TEXTIL Y SUELA DE SINTÉTICO, SIN CUBRIR EL TOBILLO, UNISEX"),
}

# Packs (surtidos de tallas del mismo producto): estilo, color, código del pack, contenido por talla
PREPACKS = [
    ("VN000EE3", "BLK Black", "AB12", {"7": 1, "8": 2, "9": 3, "10": 3, "11": 2, "12": 1}),  # 12 pares
    ("VN0A4BV4", "White", "CD08", {"7": 2, "8": 2, "9": 2, "10": 2}),  # 8 pares
]


# Catálogo de pasos de lead time (cada empresa crea los suyos) y el hito medido que representan
PASOS_LT = [
    ("BOOKING", "Booking", None), ("LIB", "Logistics release", "lib_logistica"),
    ("PROD", "Production finished", None), ("CARGA", "Cargo ready", None), ("XF", "XF (ex-factory)", "xf"),
    ("ETD", "ETD (departure)", "salida"), ("DOCS", "Document review and delivery", "documentos"),
    ("ETA", "ETA (port arrival)", "arribo"), ("ADUANA", "Customs clearance", None),
    ("BODEGA", "Warehouse delivery", "entrega"), ("INGRESO", "Warehouse entry", "ingreso"),
    ("TIENDA", "Available in store", "tienda"),
]


def _seis(partida: str | None) -> str | None:
    """La factura lleva la subpartida de 6 dígitos: el destino es solo proyectado."""
    d = "".join(c for c in partida or "" if c.isdigit())
    return f"{d[:4]}.{d[4:6]}" if len(d) >= 6 else None


def _p(paso, ref="", dias=0, habiles=False, modo=""):
    return {"paso": paso, "ref": ref, "dias": dias, "habiles": habiles, "modo": modo, "quitar": False}


# Reglas por nivel: cada una define solo lo que cambia frente al nivel superior
REGLAS_LT = [
    ("GLOBAL", None, "Global standard", [
        _p("BOOKING", "XF", -20), _p("LIB", "XF", -15), _p("PROD", "XF", -5), _p("CARGA", "XF", -2), _p("XF"),
        _p("ETD", "XF", 3), _p("DOCS", "ETA", -3), _p("ETA", "ETD", 14), _p("ADUANA", "ETA", 2, True), _p("BODEGA", "ADUANA", 1),
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
    # Cada paso dice qué documento lo cumple: el de su fecha medida, o la OC si es de planificación
    db.add_all([PasoLeadTime(codigo=c, nombre=n, hito=h, documento=rlt.DOCUMENTO_HITO.get(h or "")
                             or ("EMBARQUE" if c == "ADUANA" else "OC")) for c, n, h in PASOS_LT])
    # Los países vienen de la lista ISO de la plataforma; la demo les da su región de lead time
    existentes = {p.codigo: p for p in db.scalars(select(Pais))}
    for c, n in PAISES:
        p = existentes.get(c) or Pais(codigo=c, nombre=n, activo=True)
        p.region = REGION_PAIS.get(c)
        db.add(p)
    # Los catálogos antes que lo que guarda sus códigos (llaves foráneas por código)
    puertos = {c: Puerto(codigo=c, nombre=n, pais=p, tipo="MARITIMO") for c, n, p in PUERTOS}
    puertos.update({c: Puerto(codigo=c, nombre=n, pais=p, tipo=t) for c, n, p, t in PUERTOS_OTROS})
    db.add_all(puertos.values())
    db.flush()
    db.add_all([ReglaLeadTime(nivel=nv, nombre=nm, pasos={"pasos": ps, "orden": None},
                              **({rlt.CAMPO_NIVEL[nv]: amb} if nv in rlt.CAMPO_NIVEL else {}))
                for nv, amb, nm, ps in REGLAS_LT])
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
    for c, lista in PUERTOS_CENTRO.items():
        centros[c].puertos = [puertos[x] for x in lista]
    db.add_all([TipoUnidad(codigo=c, nombre=n, modo=m, modalidad=md, capacidad_cbm=cbm, capacidad_kg=kg,
                           requiere_sello=sello) for c, n, m, md, cbm, kg, sello in TIPOS_UNIDAD])
    db.add_all([Transportista(codigo=c, nombre=n, tipo=t, codigo_internacional=ci, pais=pais, correos=correos,
                              sociedades=[socs[x] for x in lista]) for c, n, t, ci, pais, correos, lista in TRANSPORTISTAS])
    marcas = {c: Marca(codigo=c, nombre=n) for c, n in MARCAS}
    # Una base instalada ya puede traer TALLA y COLOR (migraciones anteriores): se completan, no se repiten.
    # Sus familias se les asignan al crear las familias (_familias).
    existentes = {x.codigo: x for x in db.scalars(select(Atributo))}
    for c, n, nv, t, cat, ops, o, fams in ATRIBUTOS:
        x = existentes.get(c) or Atributo(codigo=c)
        x.nombre, x.nivel, x.tipo, x.catalogo, x.opciones, x.orden, x.activo = n, nv, t, cat, ops, o, True
        x.general = fams is None
        db.add(x)
    # Escalas de tallas reutilizables (ejemplos; cada empresa crea las suyas)
    db.add_all([
        EscalaValores(codigo="US-CALZ", nombre="US footwear (half sizes)", atributo="TALLA", regla="MULTIPLICAR", factor=10,
                      longitud=3, valores="5-12.5, 13"),
        EscalaValores(codigo="US-CALZ-ENT", nombre="US footwear (whole sizes)", atributo="TALLA", regla="MULTIPLICAR",
                      factor=10, longitud=3, valores="6-13"),
        EscalaValores(codigo="LETRAS", nombre="Apparel letters", atributo="TALLA", regla="CONSECUTIVO", longitud=3,
                      valores="XXS, XS, S, M, L, XL, XXL, XXXL"),
        EscalaValores(codigo="CINTURA", nombre="Waist (inches)", atributo="TALLA", regla="VALOR",
                      valores="28, 29, 30, 31, 32, 33, 34, 36, 38, 40"),
        EscalaValores(codigo="UNICA", nombre="One size", atributo="TALLA", regla="CONSECUTIVO", longitud=3, valores="OS=000"),
    ])
    db.add_all(marcas.values())
    db.flush()
    return {"marcas": marcas, "sociedades": socs}

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


def _familias(db: Session, admin: Usuario) -> dict:
    """Las familias de producto con sus atributos, con el mismo servicio de la pantalla
    (Productos → Familias): cada una dice qué atributos llevan sus productos."""
    from app.modulos.grupos import arbol

    ids = {}
    for codigo, nombre, padre, descripcion in FAMILIAS:
        propios = [a[0] for a in ATRIBUTOS if a[7] and codigo in a[7]]
        g = arbol.crear(db, admin, {"clase": "FAMILIA", "codigo": codigo, "nombre": nombre, "descripcion": descripcion,
                                    "padre_id": ids.get(padre), "atributos": propios})
        ids[codigo] = g["id"]
    return ids


def _articulos(db: Session, cat: dict, proveedores: dict, admin: Usuario, familias: dict) -> dict:
    """Productos y variantes con los mismos servicios que la pantalla (Productos → Nuevo producto y
    Nuevo pack o kit): cada estilo es un producto de su familia con su marca, su estilo y los
    atributos propios de su familia; cada color y talla (o solo el color, en los accesorios) es una
    variante simple con su código de barras y el del proveedor. Los packs son compuestos del mismo
    producto con su contenido."""
    from app.esquemas.productos import GenericoIn, VarianteIn
    from app.modulos.maestros import catalogos, genericos

    arts = {}
    # Datos de ejemplo: el código de artículo de esta empresa demo es el del producto más el código
    # del valor (la regla de la empresa: talla × 10; sin número, consecutivo); cada empresa usa el suyo
    productos, usados = {}, {}
    for n, (estilo, color, marca, peso, prov, unidad, precio, origen, partida, desc, empaque, tallas, familia,
            propios) in enumerate(ESTILOS):
        gen = str(30095120 + n)
        filas, claves = [], []
        for talla in tallas or [None]:
            suf = escalas.codigo(None, talla or color, usados.setdefault(gen, set()), REGLA_CODIGO)
            usados[gen].add(suf)
            sku = f"{gen}{suf}"
            filas.append(VarianteIn(valores={"COLOR": color, **({"TALLA": talla} if talla else {})}, sku=sku,
                                    codigo_barras=f"0196{int(sku) % 10**8:08d}", peso_unitario=peso,
                                    codigo_proveedor=_sku_proveedor(estilo, color, talla or "")))
            claves.append((estilo, color, talla or color))
        genericos.crear(db, admin, GenericoIn(
            generico=gen, unidad=unidad, nombre=desc, proveedor_id=proveedores[prov].id, grupo_producto_id=familias[familia],
            atributos={"MARCA": cat["marcas"][marca].codigo, "MODELO": estilo, **propios}, variantes=filas))
        p = db.scalar(select(Producto).where(Producto.codigo_generico == gen))
        productos[(estilo, color)] = p
        por_sku = {a.sku: a for a in p.articulos}
        for clave, fila in zip(claves, filas, strict=True):
            a = por_sku[fila.sku]
            a.precio_demo, a.origen_demo, a.partida_demo, a.empaque_demo = precio, origen, partida, empaque or (None, None)
            arts[clave] = a
    for estilo, color, codigo, curva in PREPACKS:
        p, base = productos[(estilo, color)], arts[(estilo, color, next(iter(curva)))]
        gen = p.codigo_generico
        suf = escalas.codigo(None, codigo, usados[gen], REGLA_CODIGO)
        usados[gen].add(suf)
        catalogos.crear_compuesto(db, admin, {
            "sku": f"{gen}{suf}", "codigo": codigo, "tipo": "PACK", "unidad": "CJ",
            "componentes": [{"articulo_id": arts[(estilo, color, t)].id, "cantidad": c} for t, c in curva.items()]})
        a = db.scalar(select(Articulo).where(Articulo.sku == f"{gen}{suf}"))
        a.poner_codigo("PROVEEDOR", _sku_proveedor(estilo, color, codigo), p.proveedor_id)
        a.origen_demo = base.origen_demo
        a.partida_demo = base.partida_demo
        a.precio_demo = base.precio_demo * sum(curva.values())
        a.empaque_demo = (None, None)
        arts[(estilo, color, codigo)] = a
    db.flush()
    _productos(db, productos, arts)
    return arts


def _sku_proveedor(estilo: str, color: str, talla: str) -> str:
    """SKU del proveedor: estilo + código de color + talla (distinto del código de artículo)."""
    primera = (color or "").split()[0] if color else ""
    cod = primera.upper() if len(primera) <= 3 else primera[:3].upper()
    return f"{estilo}{cod}-{talla}".replace(" ", "")


def _productos(db, productos, arts) -> None:
    """La ficha técnica y la clasificación de cada producto."""
    from app.modelos import Usuario as U

    interno = db.scalar(select(U).where(U.email == "interno@demo.com"))
    for (estilo, color), x in FICHAS.items():
        a = next(v for k, v in arts.items() if k[0] == estilo and k[1] == color)
        p = productos[(estilo, color)]
        p.nombre, p.tipo, p.ficha = x["nombre"], x["tipo"], x["ficha"]
        p.pais_origen = p.pais_procedencia = a.origen_demo
        p.descripcion_aduana = x.get("desc")
        p.faltan = x.get("faltan", [])
        p.ficha_completa = not p.faltan
        p.observaciones = x.get("observaciones")
        p.vigente_desde = date.today() - timedelta(days=200)
        p.descripcion_comercial = descripcion_comercial_simple(p)
        # La clasificación sale del motor único, como en la pantalla
        p.estado = x["estado"] if x["estado"] != "aprobado" else "sugerida"
        db.flush()
        clasificar_y_guardar(db, p)
        if x["estado"] == "observado":
            p.estado = "observado"
        if x.get("codigo"):
            _aprobar(db, interno, p, x["codigo"], None)
            p.revisado_en = ahora() - timedelta(days=150)


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
                posicion=str(pos), almacen=alm[0] if alm else almacen, articulo=a, codigo_articulo=a.sku,
                codigo_barras=a.codigo_barras, descripcion=a.descripcion, tipo_empaque=a.tipo,
                casepack=a.empaque_demo[0], inner_pack=a.empaque_demo[1], codigo_pack=a.codigo_pack,
                unidades_por_caja=a.total_componentes if a.tipo == "PREPACK" else None, cantidad=cantidad, unidad=a.unidad,
                precio=a.precio_demo, fecha_entrega=xf, pais_origen=a.origen_demo,
            ))
            pos += 10
    db.flush()
    return oc


def _estilo(posicion) -> str:
    """El estilo (atributo de producto MODELO) de la posición, como lo guardó su foto."""
    return (posicion.atributos or {}).get("MODELO") or posicion.articulo.producto.valor("MODELO")


def _factura_historica(db, usuario, oc, numero, fecha, plantillas, unidad=None, recolectado=None, pallet=False):
    """Factura ya cerrada: todas las posiciones de la OC, un PL finalizado con
    sus cajas y, si se indica, confirmado en una unidad de carga."""
    ts = _momento(fecha)
    f = Factura(proveedor_id=oc.proveedor_id, numero=numero, fecha=fecha, moneda=oc.moneda, incoterm=oc.incoterm,
                sociedad=oc.sociedad, centro=oc.centro, centro_destino=oc.centro_destino, estado="FINALIZADA",
                version=1, creado_por=usuario.id, creado_en=ts - timedelta(days=2), actualizado_en=ts,
                finalizado_en=ts)
    pl = PackingList(numero="PL-001", estado="FINALIZADO", version=1, creado_en=ts, actualizado_en=ts, finalizado_en=ts,
                     unidad=unidad, asignacion="CONFIRMADA" if unidad else None, recolectado_en=recolectado)
    f.packing_lists.append(pl)
    for p in oc.posiciones:
        linea = FacturaLinea(posicion_oc=p, cantidad=p.cantidad, precio_unitario=p.precio, precio_oc=p.precio,
                             oc_numero=oc.numero, almacen=p.almacen, posicion=p.posicion, codigo_articulo=p.codigo_articulo,
                             codigo_barras=p.codigo_barras, descripcion=p.descripcion, unidad=p.unidad,
                             atributos=p.atributos, variante=p.variante, tipo_empaque=p.tipo_empaque, codigo_pack=p.codigo_pack,
                             unidades_por_caja=p.unidades_por_caja,
                             casepack=p.casepack, inner_pack=p.inner_pack, centro_destino=oc.centro_destino, pais_origen=p.pais_origen,
                             partida_arancelaria=partida_para(p.articulo.producto) or _seis(p.articulo.partida_demo),
                             descripcion_comercial=p.articulo.producto.descripcion_aduana or p.descripcion)
        f.lineas.append(linea)
        pll = PLLinea(factura_linea=linea, cantidad=p.cantidad)
        pl.lineas.append(pll)
        t = plantillas[_estilo(p)]
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
        {plantillas[_estilo(p)].nombre for p in oc.posiciones})}, factura_id=f.id)
    registrar(db, usuario, "factura", f.id, "finalizar", {"con_pl": [pl.numero]}, factura_id=f.id)
    return f


def _historial_demo(db, hoy, tnf, vans, usuarios, plantillas, arts):
    """Meses anteriores ya facturados y embarcados, para que el tablero tenga
    historia: un contenedor recibido, otro en tránsito y una factura lista
    para embarcar."""
    recibido = Embarque(codigo="EMB-0001", tipo_transporte="MARITIMO", transportista="Maersk",
                        documento_numero="MAEU 221877310", puerto_origen="VNCMT", puerto_destino="SVAQJ", centro="8010",
                        etd=hoy - timedelta(days=88), eta=hoy - timedelta(days=58),
                        salida_real=hoy - timedelta(days=87), arribo_real=hoy - timedelta(days=57), estado="RECIBIDO",
                        eta_comprometida=hoy - timedelta(days=58))
    c1 = UnidadCarga(tipo="40HC", etiqueta="40HC #1", numero="MSKU 481220-7", sello="ML-99812")
    recibido.unidades.append(c1)
    for tipo, dias, lugar in (("RECOLECCION", 90, "Supplier warehouse"), ("SALIDA", 87, "Cai Mep (VN)"),
                              ("DOCUMENTOS", 62, "Customs broker, San Salvador"), ("ARRIBO", 57, "Acajutla (SV)"), ("ENTREGA", 55, "Bonded warehouse 8010"),
                              ("RECEPCION", 54, "Bonded warehouse 8010")):
        recibido.eventos.append(EventoEmbarque(tipo=tipo, fecha=_momento(hoy - timedelta(days=dias), 9), ubicacion=lugar))
    transito = Embarque(codigo="EMB-0002", tipo_transporte="MARITIMO", transportista="COSCO Shipping",
                        documento_numero="COSU 640018225", puerto_origen="CNYTN", puerto_destino="SVAQJ", centro="8010",
                        etd=hoy - timedelta(days=19), eta=hoy + timedelta(days=9),
                        salida_real=hoy - timedelta(days=18), estado="EN_TRANSITO",
                        eta_comprometida=hoy + timedelta(days=7))  # la ETA se movió 2 días en ruta
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
        (tnf, "4400003702", 115, [("NF0A3VY2", "JK3 TNF Black", [("JK3 TNF Black", 80)])], "TNF-2026-0502", 100, c1, 90),
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
    from app.modulos.empresa.organizacion import asegurar_principal

    empresa = asegurar_principal(db)
    # Marca la base como de demostración: solo una base así se puede reiniciar
    db.merge(Meta(clave="demo", valor="1"))
    empresa.nombre, empresa.pais = "Distribuidora de Marcas", "SV"
    # La empresa de ejemplo completa sus partidas con el código nacional de El Salvador
    # Sus códigos de variante sin escala: el valor × 10 en 3 dígitos (talla 7.5 → 075)
    empresa.configuracion = {"reglas": {"PAIS_BASE_CLASIF": "SV"},
                             "preferencias": {"idioma": "es", "moneda": "USD", "zona_horaria": "America/El_Salvador"},
                             "productos": {"codigo_variante": REGLA_CODIGO}}
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
    crear_roles_sugeridos(db)
    db.add(Rol(nombre="Supplier (view only)", tipo="proveedor", sistema=False,
               descripcion="Sees its POs and technical sheets; cannot invoice or edit.",
               permisos=["oc.ver", "producto.ver"]))
    pw = hash_password(PASSWORD_DEMO)
    u_tnf = Usuario(email="tnf@demo.com", nombre="TNF supplier", rol="proveedor", rol_id=roles["proveedor"].id,
                    proveedor_id=tnf.id, password_hash=pw, telefono="+84283770001",
                    cargo="Export coordinator", area="Logistics")
    u_vans = Usuario(email="vans@demo.com", nombre="Vans supplier", rol="proveedor", rol_id=roles["proveedor"].id,
                     proveedor_id=vans.id, password_hash=pw, telefono="+867552660001",
                     cargo="Shipping specialist", area="Export operations")
    db.add_all([
        Usuario(email="admin@demo.com", nombre="Administrator", rol="admin", rol_id=roles["admin"].id, password_hash=pw,
                telefono="+50370000001", cargo="Systems administrator", area="IT",
                plataforma=True),
        Usuario(email="interno@demo.com", nombre="Import team", rol="interno", rol_id=roles["interno"].id, password_hash=pw,
                telefono="+50370000002", cargo="Imports analyst", area="Imports and customs"),
        u_tnf,
        u_vans,
    ])
    db.flush()
    cat = _catalogos(db)
    # ---- Capa OFFICIAL TARIFF DATA: fuentes, versiones y países del paquete oficial 01,
    # árbol del ACI (SIECA), notas legales y líneas regionales. Nada sale de la empresa.
    from app.instalacion import cargas

    cargas.cargar_base(db)  # motor y datos oficiales incluidos (lo mismo que con datos reales)
    cargas.cargar_demo(db)  # la empresa de demostración: países, historial, palabras clave, acuerdos
    db.commit()  # el motor lee el árbol (índice en memoria) con su propia sesión
    # Cada proveedor maneja sus marcas y trabaja con sus sociedades
    tnf.marcas = [cat["marcas"]["TNF"]]
    vans.marcas = [cat["marcas"]["VANS"]]
    tnf.sociedades = [cat["sociedades"]["8000"], cat["sociedades"]["PA01"]]
    vans.sociedades = [cat["sociedades"]["8000"], cat["sociedades"]["PA01"]]
    db.flush()
    admin = db.scalar(select(Usuario).where(Usuario.email == "admin@demo.com"))
    familias = _familias(db, admin)
    # Los productos se crean con la configuración de la empresa (su regla de código de variante)
    from app.core.empresa import usar_configuracion

    usar_configuracion(empresa.configuracion)
    try:
        arts = _articulos(db, cat, {"TNF": tnf, "VANS": vans}, admin, familias)
    finally:
        usar_configuracion(None)
    tipos = _tipos_empaque(db)
    hoy = date.today()
    d = lambda n: hoy + timedelta(days=n)  # noqa: E731

    _oc(db, tnf, arts, "4400003845", d(-20), [
        ("NF0A5GLL", "JK3 TNF Black", [("S", 40), ("M", 60), ("L", 60), ("XL", 27), ("XXL", 20)]),
        ("NF0A7W4G", "KX7 Black", [("8", 24), ("9", 36), ("10", 50), ("11", 36), ("12", 12)], "BF20"),
    ], xf=d(10), xf_nueva=d(14), tienda=d(75))
    _oc(db, tnf, arts, "4400003846", d(-12), [
        ("NF0A3VY2", "JK3 TNF Black", [("JK3 TNF Black", 120)]),
        ("NF0A5IHO", "Heather grey", [("S", 30), ("M", 30), ("L", 30)]),
    ], puerto="CNYTN", origen="ID", xf=d(18), tienda=d(80))
    _oc(db, tnf, arts, "4400003850", d(-8), [("NF0A84KD", "Summit blue", [("M", 30), ("L", 30)])],
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
    # Un embarque recibido tiene la recepción de cada contenedor: un conteo
    # completo en la bodega fiscal del embarque, con la fecha del hito
    for emb in db.scalars(select(Embarque).where(Embarque.estado == "RECIBIDO")):
        hitos = {ev.tipo: ev.fecha.date() for ev in emb.eventos}
        fecha = hitos.get("RECEPCION") or emb.arribo_real or hoy
        for u in emb.unidades:
            lineas = [ln for pl in u.packing_lists if pl.estado != "CANCELADO" for ln in pl.lineas]
            if not lineas:
                continue
            reg = RecepcionRegistro(unidad_carga_id=u.id, centro=emb.centro, fecha=fecha, tipo="CONTEO",
                                    observacion="Received without differences")
            for ln in lineas:
                reg.movimientos.append(RecepcionMovimiento(pl_linea_id=ln.id, cantidad=ln.cantidad, danada=0))
                if not ln.recepcion:
                    ln.recepcion = RecepcionLinea(cantidad_recibida=ln.cantidad, cantidad_danada=0,
                                                  fecha=datetime.combine(fecha, time()))
            db.add(reg)
            u.centro, u.recepcion_estado, u.recibida_en = emb.centro, "RECIBIDA", fecha
            u.entregada_en = hitos.get("ENTREGA") or fecha
            u.liberada_en = hitos.get("LIBERACION")
    _terceros_demo(db)
    from app.modulos.empaque.recetas import convertir_existentes

    convertir_existentes(db)  # recetas de empaque desde el casepack de las OC, como la migración 0081
    from app.instalacion.demo_etiquetado import sembrar as sembrar_etiquetado

    sembrar_etiquetado(db)
    db.commit()


def _terceros_demo(db: Session) -> None:
    """La identidad (tercero) de cada proveedor y transportista."""
    from app.modulos.maestros.terceros import asegurar

    for p in db.scalars(select(Proveedor)):
        asegurar(db, p, "PROVEEDOR")
    for t in db.scalars(select(Transportista)):
        asegurar(db, t, "TRANSPORTISTA")


def reiniciar_demo() -> None:
    """Borra la base de la demostración y la vuelve a crear con sus datos.
    Solo con SEED_DEMO=1: nunca toca una base de producción."""
    from sqlalchemy import inspect, text

    from app.core.config import settings
    from app.core.db import SessionLocal, engine
    from app.instalacion import migraciones

    if not settings.SEED_DEMO:
        raise SystemExit("Solo se reinicia una base de demostración (SEED_DEMO=1).")
    tablas = inspect(engine).get_table_names()
    if "usuarios" in tablas:
        with engine.connect() as con:
            hay_datos = con.execute(text("SELECT 1 FROM usuarios LIMIT 1")).first()
            es_demo = "meta" in tablas and con.execute(text("SELECT 1 FROM meta WHERE clave = 'demo'")).first()
        if hay_datos and not es_demo:
            raise SystemExit("La base tiene datos y no es de demostración: no se borra. Revise DATABASE_URL.")
    with engine.begin() as con:
        if engine.dialect.name == "postgresql":
            con.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
        else:
            con.execute(text("PRAGMA foreign_keys=OFF"))
            for t in inspect(engine).get_table_names():
                con.execute(text(f'DROP TABLE IF EXISTS "{t}"'))
            con.execute(text("PRAGMA foreign_keys=ON"))
    migraciones.actualizar()
    with SessionLocal() as s:
        seed(s)


if __name__ == "__main__":
    # python -m app.instalacion.demo  → reinicia la demostración (SEED_DEMO=1)
    reiniciar_demo()
