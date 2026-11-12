"""Listado de un catálogo de datos maestros: sus filas como las muestra la tabla,
filtros por columna (también de datos calculados), búsqueda, orden y las opciones
de los campos que apuntan a otro catálogo.
"""
from sqlalchemy import String, cast, func, select
from sqlalchemy.orm import Session

from app.modelos import (
    Articulo,
    ArticuloAtributo,
    ArticuloCodigo,
    Atributo,
    Contacto,
    Producto,
    Sociedad,
    Usuario,
)
from app.modulos.acceso.permisos import exigir
from app.modulos.comun import tabla
from app.modulos.comun.texto import filtro_texto
from app.modulos.maestros.catalogos import campos_propios, campos_variante, catalogo_de, texto_registro
from app.modulos.maestros.definiciones import CATALOGOS
from app.modulos.productos.productos import (
    fmt_codigo,
    producto_de,
)
from app.modulos.transporte import reglas_lt as rlt


def fila_tabla(cat: dict, obj, refs: dict) -> dict:
    fila = {"id": obj.id}
    for x in campos_propios(cat):
        fila[x["nombre"]] = (obj.extra or {}).get(x["nombre"][6:])
    if campos_variante(cat):
        variantes = obj.variantes
        for x in campos_variante(cat):
            fila[x["nombre"]] = variantes.get(x["nombre"][4:])
    for campo in cat["campos"]:
        v = getattr(obj, campo["nombre"])
        if campo["tipo"] == "opciones":
            fila[campo["nombre"]] = [x for x in (v or "").split(",") if x]
            continue
        if campo["tipo"] == "multi":
            fila[campo["nombre"]] = [x.id for x in v]
            fila[campo["nombre"] + "_txt"] = ", ".join(x.codigo for x in v) or None
            continue
        if campo["tipo"] == "regla_lt":
            fila[campo["nombre"]] = rlt.cargar(v)
            n = len(fila[campo["nombre"]]["pasos"])
            fila[campo["nombre"] + "_txt"] = f"{n} change" if n == 1 else f"{n} changes"
            continue
        fila[campo["nombre"]] = v
        if campo["tipo"] == "ref" and v:
            fila[campo["nombre"] + "_txt"] = refs.get((campo["catalogo"], v))
    if isinstance(obj, Articulo):
        # La ficha técnica y la partida viven en el producto
        prod = producto_de(obj)
        fila["producto_id"] = prod.id if prod else None
        fila["descripcion_txt"] = descripcion_articulo(obj)
        fila["variante"] = " · ".join(str(v) for v in obj.variantes.values() if v not in (None, "")) or None
        fila["codigo_pack"] = obj.codigo_pack
        fila["partida_txt"] = fmt_codigo(prod.comex.codigo) if prod and prod.comex.codigo else None
        fila["clasificacion"] = prod.comex.estado if prod else None
        if obj.tipo == "PREPACK":
            fila["total"] = obj.total_componentes
            fila["componentes"] = len(obj.componentes)
    # Relaciones hijas: centros de la sociedad, artículos del grupo, contactos
    if isinstance(obj, Sociedad):
        fila["centros_txt"] = ", ".join(c.codigo for c in obj.centros) or None
    for ex in cat.get("extras", []):
        if ex["nombre"] != "centros_txt":
            fila[ex["nombre"]] = refs.get(("_" + ex["nombre"], obj.id), 0)
    return fila


def referencias_de(db: Session, cat: dict, objs: list) -> dict:
    refs = {}
    ids_obj = [o.id for o in objs]
    for ex in cat.get("extras", []):
        if ex["nombre"] == "centros_txt" or not ids_obj:
            continue
        hijo = CATALOGOS[ex["catalogo"]]["modelo"]
        if hijo is Articulo and ex["filtro"] == "proveedor_id":
            # El proveedor es del producto: se cuentan las variantes de sus productos
            col = Producto.proveedor_id
            consulta = select(col, func.count(Articulo.id)).join(Producto, Producto.id == Articulo.producto_id)
        else:
            col = getattr(hijo, ex["filtro"])
            consulta = select(col, func.count())
        for padre, n in db.execute(consulta.where(col.in_(ids_obj)).group_by(col)):
            refs[("_" + ex["nombre"], padre)] = n
    for campo in cat["campos"]:
        if campo["tipo"] != "ref":
            continue
        ids = {getattr(o, campo["nombre"]) for o in objs} - {None}
        if not ids:
            continue
        modelo = CATALOGOS[campo["catalogo"]]["modelo"]
        for r in db.scalars(select(modelo).where(modelo.id.in_(ids))).all():
            refs[(campo["catalogo"], r.id)] = texto_registro(r)
    return refs


def es_virtual(modelo, nombre: str) -> bool:
    """Un dato que no es columna sino propiedad del modelo (correos, teléfono,
    dirección y contacto viven en medios_contacto, direcciones y contactos)."""
    import inspect as _inspect

    return isinstance(_inspect.getattr_static(modelo, nombre, None), property)


def _columna_virtual(modelo, nombre: str):
    """Filtro por columna de un dato virtual: la fila pasa si alguno de sus registros tiene el valor."""
    from app.modelos import Direccion, MedioContacto

    if hasattr(modelo, "_rol_tercero"):  # proveedor o transportista: en su tercero
        dueno_medio, dueno_dir, padre = MedioContacto.tercero_id, Direccion.tercero_id, modelo.tercero_id
    else:
        clave = {"sociedades": "sociedad_id", "centros": "centro_id", "contactos": "contacto_id"}.get(modelo.__tablename__)
        if clave is None:  # otro dato calculado (p. ej. las tallas de una escala): no se filtra por columna
            return None
        dueno_medio, padre = getattr(MedioContacto, clave), modelo.id
        dueno_dir = getattr(Direccion, clave) if hasattr(Direccion, clave) else None
    if nombre == "correos":
        return tabla.Relacion(MedioContacto.valor, dueno_medio, padre, MedioContacto.tipo == "CORREO")
    if nombre == "telefono":
        return tabla.Relacion(MedioContacto.valor, dueno_medio, padre, MedioContacto.tipo.in_(("TELEFONO", "MOVIL")))
    if nombre == "direccion" and dueno_dir is not None:
        return tabla.Relacion(Direccion.linea1, dueno_dir, padre)
    if nombre == "contacto":
        return tabla.Relacion(Contacto.nombre, Contacto.tercero_id, padre)
    return None


def columnas_tabla(cat: dict) -> dict:
    """Expresión SQL de cada columna de la tabla del catálogo para el filtro por
    columna (app/modulos/comun/tabla.py). Un campo con varios registros (multi)
    filtra por los ids relacionados; los números, por su texto (así el valor
    que se elige es el mismo en SQLite y en PostgreSQL); los campos propios,
    por su dato en `extra`. La regla de lead time no se filtra."""
    modelo = cat["modelo"]
    res = {}
    for x in cat["campos"]:
        n = x["nombre"]
        if x["tipo"] == "regla_lt":
            continue
        if es_virtual(modelo, n):
            if (col := _columna_virtual(modelo, n)) is not None:
                res[n] = col
            continue
        if x["tipo"] == "multi":
            rel = getattr(modelo, n).property
            res[n] = tabla.Relacion(rel.secondary_synchronize_pairs[0][1], rel.synchronize_pairs[0][1], modelo.id)
        elif x["tipo"] == "numero":
            res[n] = cast(getattr(modelo, n), String)
        else:
            res[n] = getattr(modelo, n)
    for x in campos_propios(cat):
        res[x["nombre"]] = modelo.extra[x["nombre"][6:]].as_string()
    for x in campos_variante(cat):
        atributo = select(Atributo.id).where(Atributo.codigo == x["nombre"][4:]).scalar_subquery()
        res[x["nombre"]] = tabla.Relacion(ArticuloAtributo.valor, ArticuloAtributo.articulo_id, Articulo.id,
                                          donde=ArticuloAtributo.atributo_id == atributo)
    if modelo is Articulo:
        # Lo que vive en el producto o en los códigos del artículo
        res["generico"] = tabla.Relacion(Producto.codigo_generico, Producto.id, Articulo.producto_id)
        res["proveedor_id"] = tabla.Relacion(Producto.proveedor_id, Producto.id, Articulo.producto_id)
        for campo, tipo in (("codigo_barras", "BARRAS"), ("codigo_proveedor", "PROVEEDOR")):
            res[campo] = tabla.Relacion(ArticuloCodigo.valor, ArticuloCodigo.articulo_id, Articulo.id,
                                        donde=ArticuloCodigo.tipo == tipo)
    return res


def valores(db: Session, user: Usuario, tipo: str, columna: str, buscar: str | None, filtros_columna: dict,
            q: str | None = None, filtros: dict | None = None) -> list[dict]:
    """Valores únicos de una columna del catálogo, con cuántos registros tienen
    cada uno, bajo la búsqueda y los demás filtros (como el filtro de Excel)."""
    cat, consulta = _consulta(db, user, tipo, q, filtros or {})
    cols = columnas_tabla(cat)
    expr = tabla.columna_valida(cols, columna)
    consulta = tabla.aplicar(consulta, cols, filtros_columna, excepto=columna)
    return tabla.valores(db, consulta, expr, buscar, contar=cat["modelo"].id)


def listar(db: Session, user: Usuario, tipo: str, q: str | None, filtros: dict, orden: str | None,
           page: int, size: int, filtros_columna: dict | None = None) -> dict:
    cat, consulta = _consulta(db, user, tipo, q, filtros)
    modelo = cat["modelo"]
    cols = columnas_tabla(cat)
    consulta = tabla.aplicar(consulta, cols, filtros_columna or {})
    nombres = {x["nombre"]: x for x in cat["campos"]}
    col, _, direccion = (orden or "").partition(":")
    if col in nombres and nombres[col]["tipo"] not in ("multi", "regla_lt") and not es_virtual(modelo, col):
        expr = getattr(modelo, col)
        consulta = consulta.order_by(expr.desc() if direccion == "desc" else expr.asc(), modelo.id)
    elif col.startswith("extra.") and col in cols:
        consulta = consulta.order_by(cols[col].desc() if direccion == "desc" else cols[col].asc(), modelo.id)
    else:
        consulta = consulta.order_by(modelo.id)
    total = db.scalar(select(func.count()).select_from(consulta.subquery())) or 0
    objs = list(db.scalars(consulta.offset((page - 1) * size).limit(size)).all())
    refs = referencias_de(db, cat, objs)
    return {"items": [fila_tabla(cat, o, refs) for o in objs], "total": total, "page": page, "size": size}


def _consulta(db: Session, user: Usuario, tipo: str, q: str | None, filtros: dict):
    """Registros del catálogo con la búsqueda y los filtros por campo de la
    pantalla (sin los filtros por columna ni el orden)."""
    exigir(user, "catalogos.ver")
    cat = catalogo_de(tipo)
    modelo = cat["modelo"]
    consulta = select(modelo)
    if cat.get("donde"):
        consulta = consulta.where(cat["donde"]())
    if q:
        consulta = consulta.where(filtro_texto(q, lambda p: [getattr(modelo, b).ilike(p) for b in cat["buscar"]
                                                             if not es_virtual(modelo, b)] + _buscar_extra(modelo, p)))
    nombres = {x["nombre"]: x for x in cat["campos"]}
    for k, v in filtros.items():
        if modelo is Articulo and k == "proveedor_id" and v not in (None, ""):
            consulta = consulta.where(Articulo.producto_id.in_(select(Producto.id).where(Producto.proveedor_id == int(v))))
            continue
        if k not in nombres or v in (None, "") or es_virtual(modelo, k):
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
    return cat, consulta


def _buscar_extra(modelo, p) -> list:
    """Búsqueda en lo que no es columna del registro: un artículo también por su producto y sus códigos."""
    if modelo is not Articulo:
        return []
    return [Articulo.producto_id.in_(select(Producto.id).where(Producto.codigo_generico.ilike(p) | Producto.nombre.ilike(p))),
            Articulo.id.in_(select(ArticuloCodigo.articulo_id).where(ArticuloCodigo.valor.ilike(p)))]


def descripcion_articulo(a: Articulo) -> str | None:
    """La descripción del artículo: la suya o la del producto con los valores de la variante."""
    if a.descripcion:
        return a.descripcion
    prod = a.producto
    base = (prod.comex.descripcion_comercial or prod.nombre) if prod else None
    valores = " · ".join(str(v) for v in a.variantes.values() if v not in (None, ""))
    if a.tipo == "PREPACK" and a.codigo_pack:
        valores = f"pack {a.codigo_pack}"
    return ", ".join(x for x in (base, valores) if x) or None


def opciones(db: Session, user: Usuario, tipo: str) -> list[dict]:
    """Lista corta (id, código, texto) para selects y filtros."""
    exigir(user, "catalogos.ver")
    cat = catalogo_de(tipo)
    modelo = cat["modelo"]
    objs = db.scalars(select(modelo).order_by(modelo.id)).all()
    clave = "sku" if tipo == "articulos" else "codigo"
    # Datos para filtrar campos dependientes: sus referencias y, al revés, qué
    # registros de otros catálogos lo incluyen (p. ej. los proveedores de una marca)
    propios = [x for x in cat["campos"] if x["tipo"] in ("ref", "codigo", "multi", "opcion")]
    inversas = [(t, x["nombre"]) for t, c2 in CATALOGOS.items() for x in c2["campos"]
                if x["tipo"] == "multi" and x.get("catalogo") == tipo]
    inv: dict[str, dict[int, list[int]]] = {}
    for t, campo in inversas:
        m = inv.setdefault(t, {})
        for otro in db.scalars(select(CATALOGOS[t]["modelo"])).all():
            for rel in getattr(otro, campo):
                m.setdefault(rel.id, []).append(otro.id)
    # Nombres de los registros referidos (país de un puerto, región de un país…):
    # van en `sub` para que la búsqueda los encuentre ("vietnam cat" → Cat Lai)
    nombres_ref: dict[str, dict] = {}
    for x in propios:
        if x["tipo"] in ("ref", "codigo") and x.get("catalogo") and x["catalogo"] != tipo:
            m = CATALOGOS[x["catalogo"]]["modelo"]
            k = "id" if x["tipo"] == "ref" else ("sku" if x["catalogo"] == "articulos" else "codigo")
            nombres_ref[x["nombre"]] = {getattr(r, k): (getattr(r, "nombre", None) or texto_registro(r))
                                        for r in db.scalars(select(m)).all()}
    res = []
    for o in objs:
        fila = {"id": o.id, "codigo": getattr(o, clave), "texto": texto_registro(o)}
        sub = [nombres_ref[n].get(getattr(o, n)) for n in nombres_ref if getattr(o, n, None) is not None]
        if any(sub):
            fila["sub"] = " · ".join(x for x in sub if x)
        if hasattr(o, "activo") or hasattr(o, "activa"):
            fila["activo"] = bool(getattr(o, "activo", getattr(o, "activa", True)))
        for x in propios:
            v = getattr(o, x["nombre"])
            fila[x["nombre"]] = [y.id for y in v] if x["tipo"] == "multi" else v
        for t, m in inv.items():
            fila[t] = m.get(o.id, [])
        res.append(fila)
    return res


