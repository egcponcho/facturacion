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
    GrupoArticulo,
    Marca,
    Pais,
    PaisDestino,
    Prepack,
    PrepackComponente,
    Proveedor,
    Puerto,
    Sociedad,
    Usuario,
)
from .common import ErrorNegocio, exigir, registrar

UNIDADES = [["PAR", "Pares"], ["UN", "Unidades"], ["CJ", "Cajas (prepack)"]]
CATEGORIAS = [["CALZADO", "Calzado"], ["ROPA", "Ropa"], ["ACCESORIO", "Accesorios"]]


def c(nombre, etiqueta, tipo="texto", obligatorio=False, **extra):
    return {"nombre": nombre, "etiqueta": etiqueta, "tipo": tipo, "obligatorio": obligatorio, **extra}


# tipo: texto | entero | numero | bool | opcion (opciones) | ref (catalogo: guarda el id)
#       | codigo (catalogo: guarda el código, p. ej. país ISO)
CATALOGOS = {
    "sociedades": {
        "modelo": Sociedad, "titulo": "Sociedades", "singular": "sociedad",
        "ayuda": "Compañías legales. Sus centros son las bodegas fiscales de destino.",
        "campos": [
            c("codigo", "Código", obligatorio=True, max=10, mayus=True),
            c("nombre", "Nombre", obligatorio=True),
            c("razon_social", "Razón social"),
            c("id_fiscal", "NIT / RUC"),
            c("pais", "País", "codigo", catalogo="paises", filtro=True),
            c("moneda", "Moneda", obligatorio=True, max=3, mayus=True),
            c("direccion", "Dirección"),
            c("activa", "Activa", "bool", filtro=True),
        ],
        "buscar": ["codigo", "nombre", "razon_social", "id_fiscal"],
    },
    "centros": {
        "modelo": Centro, "titulo": "Centros", "singular": "centro",
        "ayuda": "Bodegas fiscales a las que llega la mercancía. Cada centro pertenece a una sociedad.",
        "campos": [
            c("codigo", "Código", obligatorio=True, max=10, mayus=True),
            c("sociedad_id", "Sociedad", "ref", obligatorio=True, catalogo="sociedades", filtro=True),
            c("nombre", "Nombre", obligatorio=True),
            c("tipo", "Tipo", "opcion", obligatorio=True,
              opciones=[["BODEGA_FISCAL", "Bodega fiscal"], ["ZONA_FRANCA", "Zona franca"], ["LOCAL", "Bodega local"]]),
            c("direccion", "Dirección"),
            c("activo", "Activo", "bool", filtro=True),
        ],
        "buscar": ["codigo", "nombre"],
    },
    "almacenes": {
        "modelo": Almacen, "titulo": "Almacenes", "singular": "almacén",
        "ayuda": "Almacenes de cada sociedad: virtual, detalle o mayoreo. Una OC puede repartir sus posiciones entre varios.",
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
    "paises_destino": {
        "modelo": PaisDestino, "titulo": "Países de destino", "singular": "país de destino",
        "ayuda": "Código de 4 dígitos que trae la OC y el país que representa.",
        "campos": [
            c("codigo", "Código", obligatorio=True, max=4, patron=r"^\d{4}$", mensaje_patron="Debe tener 4 dígitos."),
            c("pais", "País", "codigo", obligatorio=True, catalogo="paises", filtro=True),
            c("nombre", "Nombre", obligatorio=True),
            c("sociedad_id", "Sociedad", "ref", catalogo="sociedades", filtro=True),
            c("activo", "Activo", "bool", filtro=True),
        ],
        "buscar": ["codigo", "nombre"],
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
        "buscar": ["codigo", "nombre"],
    },
    "proveedores": {
        "modelo": Proveedor, "titulo": "Proveedores", "singular": "proveedor",
        "campos": [
            c("codigo", "Código", obligatorio=True, max=30, mayus=True),
            c("nombre", "Nombre", obligatorio=True),
            c("activo", "Activo", "bool", filtro=True),
        ],
        "buscar": ["codigo", "nombre"],
    },
    "articulos": {
        "modelo": Articulo, "titulo": "Artículos", "singular": "artículo",
        "ayuda": "Dato maestro de cada SKU. Al cargar OCs se valida contra este maestro.",
        "campos": [
            c("sku", "SKU", obligatorio=True, max=40),
            c("estilo", "Estilo", obligatorio=True),
            c("color", "Color", obligatorio=True),
            c("talla", "Talla", obligatorio=True),
            c("descripcion", "Descripción"),
            c("marca_id", "Marca", "ref", obligatorio=True, catalogo="marcas", filtro=True),
            c("grupo_id", "Grupo", "ref", obligatorio=True, catalogo="grupos", filtro=True),
            c("proveedor_id", "Proveedor", "ref", catalogo="proveedores", filtro=True),
            c("tipo", "Tipo", "opcion", obligatorio=True, filtro=True,
              opciones=[["SOLIDO", "Sólido"], ["PREPACK", "Prepack"]]),
            c("unidad", "Unidad", "opcion", obligatorio=True, opciones=UNIDADES, filtro=True),
            c("casepack", "Casepack", "entero", minimo=1,
              ayuda="Cantidad exacta por caja definida por el Commercial Brand Manager. Vacío = libre."),
            c("prepack_id", "Prepack (curva)", "ref", catalogo="prepacks"),
            c("upc", "UPC"),
            c("partida_arancelaria", "Partida arancelaria"),
            c("pais_origen", "País de origen", "codigo", catalogo="paises"),
            c("activo", "Activo", "bool", filtro=True),
        ],
        "buscar": ["sku", "estilo", "color", "upc", "descripcion"],
    },
    "prepacks": {
        "modelo": Prepack, "titulo": "Prepacks (curvas)", "singular": "prepack",
        "ayuda": "Cada curva define tallas y cantidades por caja master. Se arma con artículos sólidos.",
        "campos": [
            c("codigo", "Prepack ID", obligatorio=True, max=30, mayus=True),
            c("descripcion", "Descripción"),
            c("activo", "Activo", "bool", filtro=True),
        ],
        "buscar": ["codigo", "descripcion"],
    },
}
ORDEN_CATALOGOS = ["articulos", "prepacks", "marcas", "grupos", "proveedores", "sociedades", "centros",
                   "almacenes", "paises_destino", "paises", "puertos"]


def _cat(tipo: str) -> dict:
    if tipo not in CATALOGOS:
        raise ErrorNegocio("El catálogo no existe.", 404, "no_encontrado")
    return CATALOGOS[tipo]


def _mostrar(obj) -> str:
    """Texto corto para mostrar un registro referido."""
    for a, b in (("codigo", "nombre"), ("sku", "estilo"), ("codigo", "descripcion")):
        if hasattr(obj, a):
            extra = getattr(obj, b, None)
            return f"{getattr(obj, a)} · {extra}" if extra else str(getattr(obj, a))
    return str(obj.id)


def meta(db: Session, user: Usuario) -> list[dict]:
    exigir(user, "catalogos.ver")
    return [{"tipo": t, "titulo": CATALOGOS[t]["titulo"], "singular": CATALOGOS[t]["singular"],
             "ayuda": CATALOGOS[t].get("ayuda"), "campos": CATALOGOS[t]["campos"],
             "total": db.scalar(select(func.count()).select_from(CATALOGOS[t]["modelo"])) or 0}
            for t in ORDEN_CATALOGOS]


def _fila(cat: dict, obj, refs: dict) -> dict:
    fila = {"id": obj.id}
    for campo in cat["campos"]:
        v = getattr(obj, campo["nombre"])
        fila[campo["nombre"]] = v
        if campo["tipo"] == "ref" and v:
            fila[campo["nombre"] + "_txt"] = refs.get((campo["catalogo"], v))
    if isinstance(obj, Prepack):
        fila["total"] = obj.total
        fila["componentes"] = len(obj.componentes)
    return fila


def _refs(db: Session, cat: dict, objs: list) -> dict:
    refs = {}
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
        if campo["tipo"] == "bool":
            v = str(v).lower() in ("1", "true", "si", "sí")
        elif campo["tipo"] in ("ref", "entero"):
            v = int(v)
        consulta = consulta.where(getattr(modelo, k) == v)
    col, _, direccion = (orden or "").partition(":")
    if col in nombres:
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
        if v in ("", None):
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

    # Reglas propias de los artículos
    if cat["modelo"] is Articulo:
        final = {**({c["nombre"]: getattr(actual, c["nombre"]) for c in cat["campos"]} if actual else {}), **limpio}
        if final.get("tipo") == "PREPACK":
            if not final.get("prepack_id"):
                errores.append({"campo": "prepack_id", "mensaje": "Un artículo prepack debe tener su prepack (curva)."})
            if final.get("unidad") != "CJ":
                errores.append({"campo": "unidad", "mensaje": "Un prepack se maneja en cajas (CJ)."})
        elif final.get("tipo") == "SOLIDO":
            if final.get("prepack_id"):
                errores.append({"campo": "prepack_id", "mensaje": "Solo los artículos prepack llevan curva."})
            if final.get("unidad") == "CJ":
                errores.append({"campo": "unidad", "mensaje": "Un sólido se maneja en pares o unidades."})
    if errores:
        raise ErrorNegocio("Revisa los datos.", 422, "validacion", errores)
    return limpio


def crear(db: Session, user: Usuario, tipo: str, datos: dict) -> dict:
    exigir(user, "catalogos.editar")
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
            cambios[k] = [getattr(obj, k), v]
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
def componentes(db: Session, user: Usuario, prepack_id: int) -> dict:
    exigir(user, "catalogos.ver")
    p = db.get(Prepack, prepack_id)
    if not p:
        raise ErrorNegocio("El prepack no existe.", 404, "no_encontrado")
    return {
        "id": p.id, "codigo": p.codigo, "descripcion": p.descripcion, "total": p.total,
        "componentes": [{"articulo_id": x.articulo_id, "sku": x.articulo.sku, "estilo": x.articulo.estilo,
                         "color": x.articulo.color, "talla": x.articulo.talla, "unidad": x.articulo.unidad,
                         "cantidad": x.cantidad} for x in p.componentes],
    }


def guardar_componentes(db: Session, user: Usuario, prepack_id: int, items: list[dict]) -> dict:
    """Reemplaza la curva completa. Solo artículos sólidos, del mismo estilo y
    color, con la misma unidad y sin repetir talla."""
    exigir(user, "catalogos.editar")
    p = db.get(Prepack, prepack_id)
    if not p:
        raise ErrorNegocio("El prepack no existe.", 404, "no_encontrado")
    errores = []
    arts = []
    for it in items:
        a = db.get(Articulo, int(it.get("articulo_id") or 0))
        cant = int(it.get("cantidad") or 0)
        if not a:
            errores.append({"mensaje": "Uno de los artículos no existe."})
            continue
        if a.tipo != "SOLIDO":
            errores.append({"mensaje": f"{a.sku}: una curva solo se arma con artículos sólidos."})
        if cant < 1:
            errores.append({"mensaje": f"{a.sku}: la cantidad debe ser mayor que cero."})
        arts.append((a, cant))
    if not arts:
        errores.append({"mensaje": "La curva necesita al menos un artículo."})
    if len({a.id for a, _ in arts}) != len(arts):
        errores.append({"mensaje": "Un artículo aparece dos veces en la curva."})
    if len({(a.estilo, a.color) for a, _ in arts}) > 1:
        errores.append({"mensaje": "Todos los artículos de la curva deben ser del mismo estilo y color."})
    if len({a.unidad for a, _ in arts}) > 1:
        errores.append({"mensaje": "No se pueden mezclar pares con unidades en una curva."})
    if errores:
        raise ErrorNegocio("La curva no es válida.", 422, "validacion", errores)
    p.componentes.clear()
    db.flush()
    for a, cant in arts:
        p.componentes.append(PrepackComponente(articulo_id=a.id, cantidad=cant))
    db.flush()
    registrar(db, user, "prepacks", p.id, "editar", {"curva": {a.talla: cant for a, cant in arts}})
    return componentes(db, user, prepack_id)


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
        "prepack": {p.codigo: p.id for p in db.scalars(select(Prepack))},
    }
    cat = CATALOGOS["articulos"]
    creados = actualizados = 0
    errores = []
    for f in filas:
        datos = {k: f.get(k, "") for k in ("sku", "estilo", "color", "talla", "descripcion", "upc",
                                            "partida_arancelaria", "pais_origen", "unidad", "casepack")}
        datos["tipo"] = (f.get("tipo") or "SOLIDO").upper()
        datos["unidad"] = (datos["unidad"] or "").upper()
        faltan = []
        for campo, destino in (("marca", "marca_id"), ("grupo", "grupo_id"), ("proveedor", "proveedor_id"),
                               ("prepack_id", "prepack_id")):
            codigo = (f.get(campo) or "").strip().upper()
            if not codigo:
                continue
            clave = "prepack" if campo == "prepack_id" else campo
            if codigo not in por_codigo[clave]:
                faltan.append(f"{campo} {codigo} no existe")
            else:
                datos[destino] = por_codigo[clave][codigo]
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
    """Columnas: prepack_id, descripcion, sku, cantidad. Una fila por talla."""
    exigir(user, "catalogos.editar")
    filas = _filas_archivo(nombre, contenido)
    curvas: dict[str, dict] = {}
    errores = []
    for f in filas:
        codigo = (f.get("prepack_id") or f.get("prepack") or "").strip().upper()
        sku = (f.get("sku") or "").strip()
        if not codigo or not sku:
            errores.append({"fila": f["_fila"], "mensaje": "Faltan prepack_id o sku."})
            continue
        a = db.scalar(select(Articulo).where(Articulo.sku == sku))
        if not a:
            errores.append({"fila": f["_fila"], "mensaje": f"El SKU {sku} no existe en el maestro de artículos."})
            continue
        cv = curvas.setdefault(codigo, {"descripcion": f.get("descripcion") or None, "items": []})
        cv["items"].append({"articulo_id": a.id, "cantidad": f.get("cantidad") or 0})
    creados = actualizados = 0
    for codigo, cv in curvas.items():
        p = db.scalar(select(Prepack).where(Prepack.codigo == codigo))
        try:
            with db.begin_nested():
                if not p:
                    p = Prepack(codigo=codigo, descripcion=cv["descripcion"], activo=True)
                    db.add(p)
                    db.flush()
                    creados += 1
                else:
                    actualizados += 1
                guardar_componentes(db, user, p.id, cv["items"])
        except ErrorNegocio as e:
            errores.append({"fila": codigo, "mensaje": "; ".join(d["mensaje"] for d in e.detalle or []) or e.mensaje})
    return {"creados": creados, "actualizados": actualizados, "errores": errores[:200]}
