"""Mantenimiento de datos maestros desde un solo lugar.

Cada catálogo se describe una vez (campos, tipos, obligatorios, filtros) y
el mismo código sirve para listar, filtrar, ordenar, crear, editar y
eliminar. La interfaz usa esa misma descripción para dibujar formularios y
tablas, así que agregar un campo aquí lo agrega en pantalla.
"""
import csv
import io

from openpyxl import load_workbook
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import (
    Almacen,
    Articulo,
    Centro,
    Contacto,
    GrupoArticulo,
    Marca,
    Pais,
    Prepack,
    PrepackComponente,
    Proveedor,
    Puerto,
    Sociedad,
    TipoUnidad,
    Transportista,
    Usuario,
)
from .common import ErrorNegocio, exigir, registrar

UNIDADES = [["PAR", "Pares"], ["UN", "Unidades"], ["CJ", "Cajas (prepack)"]]
CATEGORIAS = [["CALZADO", "Calzado"], ["ROPA", "Ropa"], ["ACCESORIO", "Accesorios"]]


def c(nombre, etiqueta, tipo="texto", obligatorio=False, **extra):
    return {"nombre": nombre, "etiqueta": etiqueta, "tipo": tipo, "obligatorio": obligatorio, **extra}


# tipo: texto | entero | numero | bool | opcion (opciones) | ref (catalogo: guarda el id)
#       | codigo (catalogo: guarda el código, p. ej. país ISO) | correos
#       | multi (catalogo: varios registros, p. ej. las marcas de un proveedor)
MODOS = [["MARITIMO", "Marítimo"], ["AEREO", "Aéreo"], ["TERRESTRE", "Terrestre"]]
CATALOGOS = {
    "sociedades": {
        "modelo": Sociedad, "titulo": "Sociedades", "singular": "sociedad",
        "ayuda": "Compañías a las que se factura (sociedad de la OC). Cada una tiene sus centros asignados.",
        "campos": [
            c("codigo", "Código", obligatorio=True, max=10, mayus=True),
            c("nombre", "Nombre", obligatorio=True),
            c("razon_social", "Razón social"),
            c("id_fiscal", "NIT / RUC"),
            c("pais", "País", "codigo", catalogo="paises", filtro=True),
            c("moneda", "Moneda", obligatorio=True, max=3, mayus=True),
            c("direccion", "Dirección"),
            c("correos", "Correos de facturación", "correos", ayuda="Uno o varios, separados por coma."),
            c("activa", "Activa", "bool", filtro=True),
        ],
        "extras": [{"nombre": "centros_txt", "etiqueta": "Centros", "catalogo": "centros", "filtro": "sociedad_id"},
                   {"nombre": "contactos", "etiqueta": "Contactos", "catalogo": "contactos", "filtro": "sociedad_id"}],
        "buscar": ["codigo", "nombre", "razon_social", "id_fiscal"],
    },
    "centros": {
        "modelo": Centro, "titulo": "Centros", "singular": "centro",
        "ayuda": "Centros asignados a cada sociedad. Es el notify party del embarque y, como centro de destino "
                 "de la OC (p. ej. 2220), dice a qué país llega la mercancía. Su puerto es el de llegada.",
        "campos": [
            c("codigo", "Código", obligatorio=True, max=10, mayus=True),
            c("sociedad_id", "Sociedad", "ref", obligatorio=True, catalogo="sociedades", filtro=True),
            c("nombre", "Nombre", obligatorio=True),
            c("pais", "País", "codigo", obligatorio=True, catalogo="paises", filtro=True),
            c("puerto", "Puerto de llegada", "codigo", catalogo="puertos", filtro=True),
            c("tipo", "Tipo", "opcion", obligatorio=True,
              opciones=[["BODEGA_FISCAL", "Bodega fiscal"], ["ZONA_FRANCA", "Zona franca"], ["LOCAL", "Bodega local"],
                        ["TIENDA", "Tienda / CD"]]),
            c("puertos", "Otros puertos de llegada", "multi", catalogo="puertos",
              ayuda="Además del principal. El embarque sugiere el principal y permite cambiar entre estos."),
            c("direccion", "Dirección"),
            c("correos", "Correos (notify)", "correos", ayuda="Uno o varios, separados por coma."),
            c("activo", "Activo", "bool", filtro=True),
        ],
        "extras": [{"nombre": "contactos", "etiqueta": "Contactos", "catalogo": "contactos", "filtro": "centro_id"}],
        "buscar": ["codigo", "nombre"],
    },
    "almacenes": {
        "modelo": Almacen, "titulo": "Almacenes", "singular": "almacén",
        "ayuda": "Separación del inventario en el sistema (virtual, detalle, mayoreo); no es un lugar físico. "
                 "Cada posición de la OC indica el suyo.",
        "campos": [
            c("codigo", "Código", obligatorio=True, max=10, mayus=True),
            c("sociedad_id", "Sociedad", "ref", obligatorio=True, catalogo="sociedades", filtro=True),
            c("nombre", "Nombre", obligatorio=True),
            c("tipo", "Tipo", "opcion", obligatorio=True, filtro=True,
              opciones=[["VIRTUAL", "Virtual"], ["DETALLE", "Detalle"], ["MAYOREO", "Mayoreo"]]),
            c("activo", "Activo", "bool", filtro=True),
        ],
        "buscar": ["codigo", "nombre"],
    },
    "contactos": {
        "modelo": Contacto, "titulo": "Contactos", "singular": "contacto",
        "ayuda": "Personas de contacto de una sociedad (facturación) o de un centro (notify party). "
                 "Salen en la factura y el packing list.",
        "campos": [
            c("nombre", "Nombre", obligatorio=True),
            c("cargo", "Cargo"),
            c("rol", "Rol", "opcion", obligatorio=True, filtro=True,
              opciones=[["FACTURACION", "Facturación"], ["NOTIFY", "Notify party"], ["LOGISTICA", "Logística"]]),
            c("sociedad_id", "Sociedad", "ref", catalogo="sociedades", filtro=True),
            c("centro_id", "Centro", "ref", catalogo="centros", filtro=True),
            c("correos", "Correos", "correos", obligatorio=True, ayuda="Uno o varios, separados por coma."),
            c("telefono", "Teléfono"),
            c("activo", "Activo", "bool", filtro=True),
        ],
        "buscar": ["nombre", "cargo", "correos"],
    },
    "paises": {
        "modelo": Pais, "titulo": "Países", "singular": "país",
        "ayuda": "Países de origen y procedencia (ISO de 2 letras).",
        "campos": [
            c("codigo", "Código ISO", obligatorio=True, max=2, mayus=True, patron=r"^[A-Z]{2}$",
              mensaje_patron="Usa el código ISO de 2 letras."),
            c("nombre", "Nombre", obligatorio=True),
            c("activo", "Activo", "bool", filtro=True),
        ],
        "buscar": ["codigo", "nombre"],
    },
    "puertos": {
        "modelo": Puerto, "titulo": "Puertos", "singular": "puerto",
        "ayuda": "Puertos y aeropuertos de despacho (UN/LOCODE).",
        "campos": [
            c("codigo", "Código", obligatorio=True, max=10, mayus=True),
            c("nombre", "Nombre", obligatorio=True),
            c("pais", "País", "codigo", obligatorio=True, catalogo="paises", filtro=True),
            c("tipo", "Tipo", "opcion", obligatorio=True, filtro=True,
              opciones=[["MARITIMO", "Marítimo"], ["AEREO", "Aéreo"], ["TERRESTRE", "Terrestre"]]),
            c("activo", "Activo", "bool", filtro=True),
        ],
        "buscar": ["codigo", "nombre"],
    },
    "marcas": {
        "modelo": Marca, "titulo": "Marcas", "singular": "marca",
        "campos": [
            c("codigo", "Código", obligatorio=True, max=10, mayus=True),
            c("nombre", "Nombre", obligatorio=True),
            c("activa", "Activa", "bool", filtro=True),
        ],
        "buscar": ["codigo", "nombre"],
    },
    "grupos": {
        "modelo": GrupoArticulo, "titulo": "Grupos de artículos", "singular": "grupo",
        "ayuda": "Cada artículo pertenece a un solo grupo. La categoría define la regla de empaque.",
        "campos": [
            c("codigo", "Código", obligatorio=True, max=15, mayus=True),
            c("nombre", "Nombre", obligatorio=True),
            c("categoria", "Categoría", "opcion", obligatorio=True, opciones=CATEGORIAS, filtro=True),
            c("activo", "Activo", "bool", filtro=True),
        ],
        "extras": [{"nombre": "articulos", "etiqueta": "Artículos", "catalogo": "articulos", "filtro": "grupo_id"}],
        "buscar": ["codigo", "nombre"],
    },
    "proveedores": {
        "modelo": Proveedor, "titulo": "Proveedores", "singular": "proveedor",
        "ayuda": "Exportadores. Cada uno maneja sus propias marcas y artículos y trabaja con las sociedades asignadas.",
        "campos": [
            c("codigo", "Código", obligatorio=True, max=30, mayus=True),
            c("nombre", "Nombre", obligatorio=True),
            c("razon_social", "Razón social"),
            c("id_fiscal", "Identificación fiscal"),
            c("pais", "País", "codigo", catalogo="paises", filtro=True),
            c("direccion", "Dirección"),
            c("contacto", "Contacto"),
            c("correos", "Correos", "correos", ayuda="Uno o varios, separados por coma."),
            c("telefono", "Teléfono"),
            c("marcas", "Marcas que maneja", "multi", catalogo="marcas", filtro=True),
            c("sociedades", "Sociedades con las que trabaja", "multi", catalogo="sociedades", filtro=True),
            c("activo", "Activo", "bool", filtro=True),
        ],
        "extras": [{"nombre": "articulos", "etiqueta": "Artículos", "catalogo": "articulos", "filtro": "proveedor_id"}],
        "buscar": ["codigo", "nombre", "razon_social"],
    },
    "transportistas": {
        "modelo": Transportista, "titulo": "Transportistas", "singular": "transportista",
        "ayuda": "Navieras, aerolíneas y transporte terrestre registrados, con las sociedades para las que trabajan.",
        "campos": [
            c("codigo", "Código", obligatorio=True, max=20, mayus=True),
            c("nombre", "Nombre", obligatorio=True),
            c("tipo", "Tipo", "opcion", obligatorio=True, filtro=True, opciones=MODOS + [["MULTIMODAL", "Multimodal"]]),
            c("codigo_internacional", "SCAC / IATA", max=10, mayus=True,
              ayuda="SCAC de la naviera o prefijo IATA de la aerolínea."),
            c("id_fiscal", "Identificación fiscal"),
            c("pais", "País", "codigo", catalogo="paises"),
            c("contacto", "Contacto"),
            c("correos", "Correos", "correos"),
            c("telefono", "Teléfono"),
            c("sociedades", "Sociedades con las que trabaja", "multi", catalogo="sociedades", obligatorio=True,
              filtro=True),
            c("activo", "Activo", "bool", filtro=True),
        ],
        "buscar": ["codigo", "nombre", "codigo_internacional"],
    },
    "tipos_unidad": {
        "modelo": TipoUnidad, "titulo": "Tipos de unidad", "singular": "tipo de unidad",
        "ayuda": "Unidades de carga por modo de transporte con su capacidad. El embarque solo ofrece las de su modo; "
                 "la modalidad (FCL, LCL…) es de cada unidad, así un embarque puede ser mixto.",
        "campos": [
            c("codigo", "Código", obligatorio=True, max=10, mayus=True),
            c("nombre", "Nombre", obligatorio=True),
            c("modo", "Modo de transporte", "opcion", obligatorio=True, filtro=True, opciones=MODOS),
            c("modalidad", "Modalidad", "opcion", obligatorio=True, filtro=True,
              opciones=[["FCL", "FCL · contenedor completo"], ["LCL", "LCL · carga consolidada"],
                        ["AEREO", "Carga aérea"], ["FTL", "FTL · camión completo"], ["LTL", "LTL · carga parcial"]]),
            c("capacidad_cbm", "Volumen máximo (m³)", "numero", minimo=0),
            c("capacidad_kg", "Peso máximo (kg)", "numero", minimo=0),
            c("requiere_sello", "Requiere sello", "bool"),
            c("activo", "Activo", "bool", filtro=True),
        ],
        "buscar": ["codigo", "nombre"],
    },
    "articulos": {
        "modelo": Articulo, "titulo": "Artículos", "singular": "artículo",
        "ayuda": "Dato maestro de cada artículo con su unidad de medida. Aquí se crean los sólidos (con o sin "
                 "casepack); los prepacks se crean en la pestaña Prepacks junto con su explosión.",
        "campos": [
            c("sku", "Número de artículo (SKU)", obligatorio=True, max=18, patron=r"^\d{6,18}$",
              mensaje_patron="Solo dígitos, por ejemplo 30095120001."),
            c("estilo", "Estilo", obligatorio=True, mayus=True),
            c("color", "Color", obligatorio=True),
            c("talla", "Talla / prepack ID", obligatorio=True, mayus=True,
              ayuda="En un prepack es su prepack ID, p. ej. AB12."),
            c("descripcion", "Descripción"),
            c("marca_id", "Marca", "ref", obligatorio=True, catalogo="marcas", filtro=True),
            c("grupo_id", "Grupo", "ref", obligatorio=True, catalogo="grupos", filtro=True),
            c("proveedor_id", "Proveedor", "ref", obligatorio=True, catalogo="proveedores", filtro=True,
              ayuda="Cada proveedor maneja sus artículos; la marca debe ser una de las suyas."),
            c("tipo", "Tipo", "opcion", obligatorio=True, filtro=True,
              opciones=[["SOLIDO", "Sólido"], ["PREPACK", "Prepack"]]),
            c("unidad", "Unidad", "opcion", obligatorio=True, opciones=UNIDADES, filtro=True),
            c("casepack", "Casepack", "entero", minimo=1,
              ayuda="Cantidad exacta por caja definida por el Commercial Brand Manager. Vacío = libre."),
            c("upc", "UPC"),
            c("partida_arancelaria", "Partida arancelaria"),
            c("pais_origen", "País de origen", "codigo", catalogo="paises"),
            c("activo", "Activo", "bool", filtro=True),
        ],
        "buscar": ["sku", "estilo", "color", "upc", "descripcion"],
    },
    "prepacks": {
        "modelo": Prepack, "titulo": "Prepacks (curvas)", "singular": "prepack",
        "ayuda": "Un prepack es un artículo con su propio código de producto. Su curva (explosión) reparte "
                 "tallas y cantidades por caja master con sólidos del mismo estilo y color, y su prepack ID "
                 "(usualmente 2 letras y 2 números, p. ej. AB12) es su talla. La explosión se ve pero no se modifica.",
        "campos": [
            c("codigo", "Prepack ID", obligatorio=True, max=10, mayus=True, patron=r"^[A-Z0-9]{2,10}$",
              mensaje_patron="Solo letras y números, p. ej. AB12."),
            c("estilo", "Estilo", obligatorio=True, mayus=True, filtro=True),
            c("color", "Color", obligatorio=True),
            c("descripcion", "Descripción"),
            c("activo", "Activo", "bool", filtro=True),
        ],
        "buscar": ["codigo", "estilo", "color", "descripcion"],
    },
}
ORDEN_CATALOGOS = ["articulos", "prepacks", "marcas", "grupos", "proveedores", "sociedades", "centros",
                   "contactos", "almacenes", "transportistas", "tipos_unidad", "paises", "puertos"]
CORREO = r"^[^@\s,;]+@[^@\s,;]+\.[^@\s,;]+$"


def _cat(tipo: str) -> dict:
    if tipo not in CATALOGOS:
        raise ErrorNegocio("El catálogo no existe.", 404, "no_encontrado")
    return CATALOGOS[tipo]


def _mostrar(obj) -> str:
    """Texto corto para mostrar un registro referido."""
    if isinstance(obj, Prepack):
        return f"{obj.codigo} · {obj.estilo} {obj.color or ''}".strip()
    if isinstance(obj, Contacto):
        return obj.nombre
    for a, b in (("codigo", "nombre"), ("sku", "estilo"), ("codigo", "descripcion")):
        if hasattr(obj, a):
            extra = getattr(obj, b, None)
            return f"{getattr(obj, a)} · {extra}" if extra else str(getattr(obj, a))
    return str(obj.id)


def meta(db: Session, user: Usuario) -> list[dict]:
    exigir(user, "catalogos.ver")
    return [{"tipo": t, "titulo": CATALOGOS[t]["titulo"], "singular": CATALOGOS[t]["singular"],
             "ayuda": CATALOGOS[t].get("ayuda"), "campos": CATALOGOS[t]["campos"],
             "extras": CATALOGOS[t].get("extras", []),
             "total": db.scalar(select(func.count()).select_from(CATALOGOS[t]["modelo"])) or 0}
            for t in ORDEN_CATALOGOS]


def _fila(cat: dict, obj, refs: dict) -> dict:
    fila = {"id": obj.id}
    for campo in cat["campos"]:
        v = getattr(obj, campo["nombre"])
        if campo["tipo"] == "multi":
            fila[campo["nombre"]] = [x.id for x in v]
            fila[campo["nombre"] + "_txt"] = ", ".join(x.codigo for x in v) or None
            continue
        fila[campo["nombre"]] = v
        if campo["tipo"] == "ref" and v:
            fila[campo["nombre"] + "_txt"] = refs.get((campo["catalogo"], v))
    if isinstance(obj, Prepack):
        fila["total"] = obj.total
        fila["componentes"] = len(obj.componentes)
        fila["sku"] = refs.get(("_sku_prepack", obj.id))
    # Relaciones hijas: centros de la sociedad, artículos del grupo, contactos
    if isinstance(obj, Sociedad):
        fila["centros_txt"] = ", ".join(c.codigo for c in obj.centros) or None
    for ex in cat.get("extras", []):
        if ex["nombre"] != "centros_txt":
            fila[ex["nombre"]] = refs.get(("_" + ex["nombre"], obj.id), 0)
    return fila


def _refs(db: Session, cat: dict, objs: list) -> dict:
    refs = {}
    ids_obj = [o.id for o in objs]
    if cat["modelo"] is Prepack and ids_obj:
        for pid, sku in db.execute(select(Articulo.prepack_id, Articulo.sku).where(Articulo.prepack_id.in_(ids_obj))):
            refs[("_sku_prepack", pid)] = sku
    for ex in cat.get("extras", []):
        if ex["nombre"] == "centros_txt" or not ids_obj:
            continue
        hijo = CATALOGOS[ex["catalogo"]]["modelo"]
        col = getattr(hijo, ex["filtro"])
        for padre, n in db.execute(select(col, func.count()).where(col.in_(ids_obj)).group_by(col)):
            refs[("_" + ex["nombre"], padre)] = n
    for campo in cat["campos"]:
        if campo["tipo"] != "ref":
            continue
        ids = {getattr(o, campo["nombre"]) for o in objs} - {None}
        if not ids:
            continue
        modelo = CATALOGOS[campo["catalogo"]]["modelo"]
        for r in db.scalars(select(modelo).where(modelo.id.in_(ids))).all():
            refs[(campo["catalogo"], r.id)] = _mostrar(r)
    return refs


def listar(db: Session, user: Usuario, tipo: str, q: str | None, filtros: dict, orden: str | None,
           page: int, size: int) -> dict:
    exigir(user, "catalogos.ver")
    cat = _cat(tipo)
    modelo = cat["modelo"]
    consulta = select(modelo)
    if q:
        patron = f"%{q.strip()}%"
        consulta = consulta.where(or_(*[getattr(modelo, b).ilike(patron) for b in cat["buscar"]]))
    nombres = {x["nombre"]: x for x in cat["campos"]}
    for k, v in filtros.items():
        if k not in nombres or v in (None, ""):
            continue
        campo = nombres[k]
        if campo["tipo"] == "multi":
            consulta = consulta.where(getattr(modelo, k).any(id=int(v)))
            continue
        if campo["tipo"] == "bool":
            v = str(v).lower() in ("1", "true", "si", "sí")
        elif campo["tipo"] in ("ref", "entero"):
            v = int(v)
        consulta = consulta.where(getattr(modelo, k) == v)
    col, _, direccion = (orden or "").partition(":")
    if col in nombres and nombres[col]["tipo"] != "multi":
        expr = getattr(modelo, col)
        consulta = consulta.order_by(expr.desc() if direccion == "desc" else expr.asc(), modelo.id)
    else:
        consulta = consulta.order_by(modelo.id)
    total = db.scalar(select(func.count()).select_from(consulta.subquery())) or 0
    objs = list(db.scalars(consulta.offset((page - 1) * size).limit(size)).all())
    refs = _refs(db, cat, objs)
    return {"items": [_fila(cat, o, refs) for o in objs], "total": total, "page": page, "size": size}


def opciones(db: Session, user: Usuario, tipo: str) -> list[dict]:
    """Lista corta (id, código, texto) para selects y filtros."""
    exigir(user, "catalogos.ver")
    cat = _cat(tipo)
    modelo = cat["modelo"]
    objs = db.scalars(select(modelo).order_by(modelo.id)).all()
    clave = "sku" if tipo == "articulos" else "codigo"
    return [{"id": o.id, "codigo": getattr(o, clave), "texto": _mostrar(o)} for o in objs]


def _limpiar(db: Session, cat: dict, datos: dict, parcial: bool, actual=None) -> dict:
    import re

    errores = []
    limpio = {}
    for campo in cat["campos"]:
        n = campo["nombre"]
        if n not in datos:
            if not parcial and campo["obligatorio"]:
                errores.append({"campo": n, "mensaje": f"{campo['etiqueta']} es obligatorio."})
            continue
        v = datos[n]
        if isinstance(v, str):
            v = v.strip()
            if campo.get("mayus"):
                v = v.upper()
        if v in ("", None) or (campo["tipo"] == "multi" and v == [] and not campo["obligatorio"]):
            if campo["tipo"] == "multi":
                if campo["obligatorio"]:
                    errores.append({"campo": n, "mensaje": f"{campo['etiqueta']}: elige al menos uno."})
                else:
                    limpio[n] = []
                continue
            v = None
        if v is None:
            if campo["obligatorio"]:
                errores.append({"campo": n, "mensaje": f"{campo['etiqueta']} es obligatorio."})
            limpio[n] = False if campo["tipo"] == "bool" else None
            continue
        t = campo["tipo"]
        try:
            if t == "entero":
                v = int(v)
                if campo.get("minimo") is not None and v < campo["minimo"]:
                    raise ValueError
            elif t == "numero":
                v = float(v)
            elif t == "bool":
                v = v if isinstance(v, bool) else str(v).lower() in ("1", "true", "si", "sí")
            elif t == "ref":
                v = int(v)
                if not db.get(CATALOGOS[campo["catalogo"]]["modelo"], v):
                    raise ValueError
            elif t == "codigo":
                v = str(v).upper()
                modelo = CATALOGOS[campo["catalogo"]]["modelo"]
                if not db.scalar(select(modelo.id).where(modelo.codigo == v)):
                    errores.append({"campo": n, "mensaje": f"{campo['etiqueta']}: {v} no está en el catálogo."})
                    continue
            elif t == "opcion" and v not in [o[0] for o in campo["opciones"]]:
                raise ValueError
            elif t == "multi":
                ids = v if isinstance(v, list) else [x for x in str(v).split(",") if x.strip()]
                modelo = CATALOGOS[campo["catalogo"]]["modelo"]
                objs = list(db.scalars(select(modelo).where(modelo.id.in_([int(x) for x in ids])))) if ids else []
                if len(objs) != len(set(int(x) for x in ids)):
                    raise ValueError
                if campo["obligatorio"] and not objs:
                    errores.append({"campo": n, "mensaje": f"{campo['etiqueta']}: elige al menos uno."})
                    continue
                v = objs
            elif t == "correos":
                lista = [x.strip().lower() for x in re.split(r"[,;\s]+", str(v)) if x.strip()]
                malos = [x for x in lista if not re.match(CORREO, x)]
                if malos:
                    errores.append({"campo": n, "mensaje": f"Correo no válido: {', '.join(malos)}."})
                    continue
                v = ", ".join(dict.fromkeys(lista))
            else:
                v = str(v)
        except (TypeError, ValueError):
            errores.append({"campo": n, "mensaje": f"{campo['etiqueta']}: valor no válido."})
            continue
        if campo.get("max") and isinstance(v, str) and len(v) > campo["max"]:
            errores.append({"campo": n, "mensaje": f"{campo['etiqueta']}: máximo {campo['max']} caracteres."})
            continue
        if campo.get("patron") and isinstance(v, str) and not re.match(campo["patron"], v):
            errores.append({"campo": n, "mensaje": f"{campo['etiqueta']}: {campo.get('mensaje_patron', 'formato no válido')}"})
            continue
        limpio[n] = v

    final = {**({c["nombre"]: getattr(actual, c["nombre"]) for c in cat["campos"]} if actual else {}), **limpio}
    # Reglas propias de los artículos: el prepack se enlaza por estilo, color
    # y prepack ID (la talla); debe existir su curva
    if cat["modelo"] is Articulo:
        if final.get("tipo") == "PREPACK" and not (actual and actual.tipo == "PREPACK"):
            errores.append({"campo": "tipo", "mensaje":
                            "Los prepacks se crean en la pestaña Prepacks, con su código de producto y su explosión."})
        elif actual and actual.tipo == "PREPACK":
            # La explosión es fija: no cambia lo que la enlaza
            fijos = [c for c in ("tipo", "estilo", "color", "talla", "unidad") if c in limpio and limpio[c] != getattr(actual, c)]
            if fijos:
                errores.append({"campo": fijos[0], "mensaje":
                                "El prepack y su explosión no se modifican (estilo, color, prepack ID, unidad y tipo). "
                                "Crea un prepack nuevo."})
        elif final.get("tipo") == "SOLIDO":
            if actual and db.scalar(select(PrepackComponente.id).where(PrepackComponente.articulo_id == actual.id)):
                fijos = [c for c in ("estilo", "color", "talla", "unidad") if c in limpio and limpio[c] != getattr(actual, c)]
                if fijos:
                    errores.append({"campo": fijos[0], "mensaje":
                                    "Este sólido forma parte de la explosión de un prepack: no cambia su estilo, "
                                    "color, talla ni unidad."})
            limpio["prepack_id"] = None
            if final.get("unidad") == "CJ":
                errores.append({"campo": "unidad", "mensaje": "Un sólido se maneja en pares o unidades."})
    if cat["modelo"] is Articulo and final.get("proveedor_id") and final.get("marca_id"):
        prov = db.get(Proveedor, final["proveedor_id"])
        if prov and prov.marcas and final["marca_id"] not in {m.id for m in prov.marcas}:
            errores.append({"campo": "marca_id", "mensaje":
                            f"La marca no es de {prov.nombre}; sus marcas son {', '.join(m.codigo for m in prov.marcas)}."})
    if cat["modelo"] is Proveedor and actual and "marcas" in limpio:
        quedan = {m.id for m in limpio["marcas"]}
        usadas = {m for (m,) in db.execute(select(Articulo.marca_id).where(Articulo.proveedor_id == actual.id).distinct())}
        if quedan and usadas - quedan:
            nombres_m = [m.codigo for m in db.scalars(select(Marca).where(Marca.id.in_(usadas - quedan)))]
            errores.append({"campo": "marcas", "mensaje":
                            f"El proveedor tiene artículos de {', '.join(nombres_m)}: no se pueden quitar esas marcas."})
    if cat["modelo"] is Contacto and not final.get("sociedad_id") and not final.get("centro_id"):
        errores.append({"campo": "sociedad_id", "mensaje": "Indica la sociedad o el centro del contacto."})
    if cat["modelo"] is Prepack and actual:
        fijos = [c for c in ("codigo", "estilo", "color") if c in limpio and limpio[c] != getattr(actual, c)]
        if fijos:
            errores.append({"campo": fijos[0], "mensaje":
                            "El prepack ID, estilo y color no se modifican; solo la descripción y si está activo."})
    if errores:
        raise ErrorNegocio("Revisa los datos.", 422, "validacion", errores)
    return limpio


def crear(db: Session, user: Usuario, tipo: str, datos: dict) -> dict:
    exigir(user, "catalogos.editar")
    if tipo == "prepacks":
        return crear_prepack(db, user, datos)
    cat = _cat(tipo)
    limpio = _limpiar(db, cat, datos, parcial=False)
    for campo in cat["campos"]:
        if campo["tipo"] == "bool" and campo["nombre"] not in datos:
            limpio[campo["nombre"]] = True
    obj = cat["modelo"](**limpio)
    try:
        with db.begin_nested():
            db.add(obj)
            db.flush()
    except IntegrityError:
        raise ErrorNegocio(f"Ya existe un {cat['singular']} con ese código.", 409, "duplicado") from None
    registrar(db, user, tipo, obj.id, "crear", {"codigo": _mostrar(obj)})
    return _fila(cat, obj, _refs(db, cat, [obj]))


def actualizar(db: Session, user: Usuario, tipo: str, obj_id: int, datos: dict) -> dict:
    exigir(user, "catalogos.editar")
    cat = _cat(tipo)
    obj = db.get(cat["modelo"], obj_id)
    if not obj:
        raise ErrorNegocio(f"El {cat['singular']} no existe.", 404, "no_encontrado")
    limpio = _limpiar(db, cat, datos, parcial=True, actual=obj)
    cambios = {}
    for k, v in limpio.items():
        if getattr(obj, k) != v:
            antes = getattr(obj, k)
            if isinstance(v, list):  # relaciones: se guardan los códigos en el historial
                cambios[k] = [[x.codigo for x in antes], [x.codigo for x in v]]
            else:
                cambios[k] = [antes, v]
            setattr(obj, k, v)
    try:
        with db.begin_nested():
            db.flush()
    except IntegrityError:
        raise ErrorNegocio(f"Ya existe un {cat['singular']} con ese código.", 409, "duplicado") from None
    if cambios:
        registrar(db, user, tipo, obj.id, "editar", cambios)
    return _fila(cat, obj, _refs(db, cat, [obj]))


def eliminar(db: Session, user: Usuario, tipo: str, obj_id: int) -> dict:
    exigir(user, "catalogos.editar")
    cat = _cat(tipo)
    obj = db.get(cat["modelo"], obj_id)
    if not obj:
        raise ErrorNegocio(f"El {cat['singular']} no existe.", 404, "no_encontrado")
    try:
        with db.begin_nested():
            db.delete(obj)
            db.flush()
    except IntegrityError:
        raise ErrorNegocio(f"No se puede eliminar: el {cat['singular']} está en uso. Desactívalo en su lugar.",
                           409, "en_uso") from None
    registrar(db, user, tipo, obj_id, "eliminar", None)
    return {"ok": True}


# ---- Prepacks: componentes -------------------------------------------------
def componentes(db: Session, user: Usuario, prepack_id: int, validar: bool = True) -> dict:
    if validar:
        exigir(user, "catalogos.ver")
    p = db.get(Prepack, prepack_id)
    if not p:
        raise ErrorNegocio("El prepack no existe.", 404, "no_encontrado")
    art = db.scalar(select(Articulo).where(Articulo.prepack_id == p.id))
    return {
        "sku": art.sku if art else None, "unidad": "CJ", "marca": art.marca.codigo if art else None,
        "id": p.id, "codigo": p.codigo, "estilo": p.estilo, "color": p.color, "descripcion": p.descripcion,
        "total": p.total,
        "unidad_componentes": p.componentes[0].articulo.unidad if p.componentes else None,
        "componentes": [{"articulo_id": x.articulo_id, "sku": x.articulo.sku, "estilo": x.articulo.estilo,
                         "color": x.articulo.color, "talla": x.articulo.talla, "unidad": x.articulo.unidad,
                         "cantidad": x.cantidad} for x in p.componentes],
    }


def _validar_curva(db: Session, estilo: str, color: str, items: list[dict]) -> tuple[list, list]:
    """Solo sólidos del mismo estilo y color del prepack, con cantidad, sin
    repetir artículo y sin mezclar pares con unidades."""
    errores = []
    arts = []
    for it in items:
        a = db.get(Articulo, int(it.get("articulo_id") or 0))
        try:
            cant = int(it.get("cantidad") or 0)
        except (TypeError, ValueError):
            cant = 0
        if not a:
            errores.append({"mensaje": "Uno de los artículos no existe."})
            continue
        if a.tipo != "SOLIDO":
            errores.append({"mensaje": f"{a.sku}: la explosión solo lleva artículos sólidos."})
        if cant < 1:
            errores.append({"mensaje": f"{a.sku}: la cantidad debe ser mayor que cero."})
        arts.append((a, cant))
    if not arts:
        errores.append({"mensaje": "La explosión necesita al menos un artículo sólido."})
    if len({a.id for a, _ in arts}) != len(arts):
        errores.append({"mensaje": "Un artículo aparece dos veces en la explosión."})
    otros = [a for a, _ in arts if (a.estilo, a.color) != (estilo, color)]
    if otros:
        errores.append({"mensaje": f"El prepack es de {estilo} {color}: "
                                   + ", ".join(f"{a.sku} ({a.estilo} {a.color})" for a in otros)
                                   + " no es del mismo estilo y color."})
    if len({a.unidad for a, _ in arts}) > 1:
        errores.append({"mensaje": "No se pueden mezclar pares con unidades en una explosión."})
    return arts, errores


def crear_prepack(db: Session, user: Usuario, datos: dict) -> dict:
    """Crea el prepack completo en un paso: su curva (explosión) y el artículo
    prepack con su propio código de producto. La explosión ya no cambia."""
    import re

    exigir(user, "catalogos.editar")
    sku = str(datos.get("sku") or "").strip()
    codigo = str(datos.get("codigo") or "").strip().upper()
    estilo = str(datos.get("estilo") or "").strip().upper()
    color = str(datos.get("color") or "").strip()
    errores = []
    if not re.fullmatch(r"\d{6,18}", sku):
        errores.append({"campo": "sku", "mensaje": "Código de producto: solo dígitos, por ejemplo 30095120027."})
    elif db.scalar(select(Articulo.id).where(Articulo.sku == sku)):
        errores.append({"campo": "sku", "mensaje": f"El código {sku} ya existe en el maestro de artículos."})
    if not re.fullmatch(r"[A-Z0-9]{2,10}", codigo):
        errores.append({"campo": "codigo", "mensaje": "Prepack ID: letras y números, por ejemplo AB12."})
    if not estilo or not color:
        errores.append({"campo": "estilo", "mensaje": "Indica el estilo y el color del prepack."})
    elif db.scalar(select(Prepack.id).where(Prepack.estilo == estilo, Prepack.color == color, Prepack.codigo == codigo)):
        errores.append({"campo": "codigo", "mensaje": f"Ya existe el prepack {codigo} para {estilo} {color}."})
    arts, err_curva = _validar_curva(db, estilo, color, datos.get("componentes") or [])
    errores += err_curva
    if errores:
        raise ErrorNegocio("El prepack no es válido.", 422, "validacion", errores)
    base = arts[0][0]
    p = Prepack(codigo=codigo, estilo=estilo, color=color, activo=True,
                descripcion=(datos.get("descripcion") or "").strip()
                or f"{estilo} {color} prepack {codigo} ({sum(c for _, c in arts)} {base.unidad.lower()})")
    for a, cant in arts:
        p.componentes.append(PrepackComponente(articulo_id=a.id, cantidad=cant))
    db.add(p)
    db.flush()
    art = Articulo(sku=sku, upc=(datos.get("upc") or "").strip() or None, estilo=estilo, color=color, talla=codigo,
                   descripcion=p.descripcion, marca_id=base.marca_id, grupo_id=base.grupo_id,
                   proveedor_id=base.proveedor_id, unidad="CJ", tipo="PREPACK", prepack_id=p.id,
                   partida_arancelaria=base.partida_arancelaria, pais_origen=base.pais_origen, activo=True)
    db.add(art)
    db.flush()
    registrar(db, user, "prepacks", p.id, "crear",
              {"sku": sku, "prepack": codigo, "explosion": {a.talla: c for a, c in arts}})
    return componentes(db, user, p.id)


def explosion(db: Session, user: Usuario, sku: str) -> dict:
    """Explosión de un artículo prepack, de solo lectura (para OC, factura,
    packing list y seguimiento)."""
    exigir(user, "oc.ver")
    a = db.scalar(select(Articulo).where(Articulo.sku == sku))
    if not a or a.tipo != "PREPACK" or not a.prepack:
        raise ErrorNegocio("Ese código no es un artículo prepack.", 404, "no_encontrado")
    return componentes(db, user, a.prepack_id, validar=False)


# ---- Carga masiva ----------------------------------------------------------
def _filas_archivo(nombre: str, contenido: bytes) -> list[dict]:
    from .ordenes import _norm, _texto

    if nombre.lower().endswith((".xlsx", ".xlsm")):
        wb = load_workbook(io.BytesIO(contenido), read_only=True, data_only=True)
        filas = [[_texto(v) for v in f] for f in wb.active.iter_rows(values_only=True)]
    else:
        texto = contenido.decode("utf-8-sig", errors="replace")
        delim = ";" if texto[:2000].count(";") > texto[:2000].count(",") else ","
        filas = [[v.strip() for v in f] for f in csv.reader(io.StringIO(texto), delimiter=delim)]
    if not filas:
        return []
    enc = [_norm(h) for h in filas[0]]
    return [{**{enc[i]: (f[i] if i < len(f) else "") for i in range(len(enc))}, "_fila": n}
            for n, f in enumerate(filas[1:], start=2) if any(f)]


def importar_articulos(db: Session, user: Usuario, nombre: str, contenido: bytes) -> dict:
    """Crea o actualiza artículos por SKU. Marca, grupo, proveedor y prepack
    se indican por código."""
    exigir(user, "catalogos.editar")
    filas = _filas_archivo(nombre, contenido)
    if not filas:
        raise ErrorNegocio("El archivo no tiene filas con datos.", 422, "archivo_vacio")
    por_codigo = {
        "marca": {m.codigo: m.id for m in db.scalars(select(Marca))},
        "grupo": {g.codigo: g.id for g in db.scalars(select(GrupoArticulo))},
        "proveedor": {p.codigo: p.id for p in db.scalars(select(Proveedor))},
    }
    cat = CATALOGOS["articulos"]
    creados = actualizados = 0
    errores = []
    for f in filas:
        datos = {k: f.get(k, "") for k in ("sku", "estilo", "color", "talla", "descripcion", "upc",
                                            "partida_arancelaria", "pais_origen", "unidad", "casepack")}
        datos["tipo"] = (f.get("tipo") or "SOLIDO").upper()
        if datos["tipo"] == "PREPACK":
            errores.append({"fila": f["_fila"], "mensaje":
                            "Los prepacks se cargan con el formato de prepacks (código de producto y explosión)."})
            continue
        datos["unidad"] = (datos["unidad"] or "").upper()
        faltan = []
        for campo, destino in (("marca", "marca_id"), ("grupo", "grupo_id"), ("proveedor", "proveedor_id")):
            codigo = (f.get(campo) or "").strip().upper()
            if not codigo:
                continue
            if codigo not in por_codigo[campo]:
                faltan.append(f"{campo} {codigo} no existe")
            else:
                datos[destino] = por_codigo[campo][codigo]
        if faltan:
            errores.append({"fila": f["_fila"], "mensaje": "; ".join(faltan) + "."})
            continue
        existente = db.scalar(select(Articulo).where(Articulo.sku == datos["sku"].strip()))
        try:
            with db.begin_nested():
                if existente:
                    limpio = _limpiar(db, cat, {k: v for k, v in datos.items() if v != ""}, parcial=True, actual=existente)
                    for k, v in limpio.items():
                        setattr(existente, k, v)
                else:
                    limpio = _limpiar(db, cat, datos, parcial=False)
                    db.add(Articulo(**limpio, activo=True))
                db.flush()
            if existente:
                actualizados += 1
            else:
                creados += 1
        except IntegrityError:
            errores.append({"fila": f["_fila"], "mensaje": "Datos duplicados o inconsistentes."})
        except ErrorNegocio as e:
            errores.append({"fila": f["_fila"], "mensaje": "; ".join(d["mensaje"] for d in e.detalle or []) or e.mensaje})
    registrar(db, user, "articulos", 0, "importar", {"creados": creados, "actualizados": actualizados,
                                                      "errores": len(errores)})
    return {"creados": creados, "actualizados": actualizados, "errores": errores[:200]}


def importar_prepacks(db: Session, user: Usuario, nombre: str, contenido: bytes) -> dict:
    """Columnas: sku_prepack (código de producto del prepack), prepack_id,
    descripcion, sku (sólido) y cantidad. Una fila por talla de la explosión.
    Estilo y color salen de los sólidos. Un prepack que ya existe no cambia."""
    exigir(user, "catalogos.editar")
    filas = _filas_archivo(nombre, contenido)
    grupos: dict[str, dict] = {}
    errores = []
    for f in filas:
        sku_pp = (f.get("sku_prepack") or f.get("codigo_prepack") or "").strip()
        codigo = (f.get("prepack_id") or f.get("prepack") or "").strip().upper()
        sku = (f.get("sku") or "").strip()
        if not sku_pp or not codigo or not sku:
            errores.append({"fila": f["_fila"], "mensaje": "Faltan sku_prepack, prepack_id o sku."})
            continue
        a = db.scalar(select(Articulo).where(Articulo.sku == sku))
        if not a:
            errores.append({"fila": f["_fila"], "mensaje": f"El SKU {sku} no existe en el maestro de artículos."})
            continue
        g = grupos.setdefault(sku_pp, {"codigo": codigo, "estilo": a.estilo, "color": a.color,
                                       "descripcion": f.get("descripcion") or None, "items": []})
        g["items"].append({"articulo_id": a.id, "cantidad": f.get("cantidad") or 0})
    creados = sin_cambio = 0
    for sku_pp, g in grupos.items():
        existente = db.scalar(select(Articulo).where(Articulo.sku == sku_pp))
        if existente:
            actual = {x.articulo_id: x.cantidad for x in existente.prepack.componentes} if existente.prepack else {}
            nueva = {it["articulo_id"]: int(it["cantidad"] or 0) for it in g["items"]}
            if actual == nueva:
                sin_cambio += 1
            else:
                errores.append({"fila": sku_pp, "mensaje": "El prepack ya existe con otra explosión; "
                                                           "la explosión no se modifica. Usa un código nuevo."})
            continue
        try:
            with db.begin_nested():
                crear_prepack(db, user, {"sku": sku_pp, **g, "componentes": g["items"]})
            creados += 1
        except ErrorNegocio as e:
            errores.append({"fila": sku_pp, "mensaje": "; ".join(d["mensaje"] for d in e.detalle or []) or e.mensaje})
    return {"creados": creados, "actualizados": 0, "sin_cambio": sin_cambio, "errores": errores[:200]}
