"""Las familias del catálogo: un solo controlador.

Un árbol de familias (con subfamilias) y categorías (dentro de una familia,
reconocidas por condiciones sobre los datos del catálogo o puestas a mano en el
producto) para toda la empresa. Aquí se crean, se cambian, se ordenan y se
borran, se les asignan atributos y productos, y se prueban las condiciones de
una categoría.

Lo que cada módulo guarda de una familia (logística, etiquetado, empaque…) es
su sección (`catalogo/secciones.py`): el catálogo no conoce a los módulos, los
recorre por ese registro para leer sus secciones y saber si una familia se usa.
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errores import ErrorNegocio
from app.modelos import Articulo, GrupoCategoria, GrupoFamilia, GrupoProducto, Producto, Usuario
from app.modelos.grupos import CLASES_GRUPO
from app.modulos.acceso.permisos import exigir_alguno, proveedor_filtro
from app.modulos.catalogo import secciones
from app.modulos.comun.condiciones import cumple_condicion, limpiar
from app.modulos.comun.historial import registrar

PERMISOS_VER = ("catalogos.ver", "etiquetas.familias")
PERMISOS_EDITAR = ("catalogos.editar", "etiquetas.familias")
MAX_PRUEBA = 20000  # artículos que se revisan al probar unas condiciones
EJEMPLOS = 20


# ---- Pertenencia y ruta ----------------------------------------------------------------------
def categoria_de(db: Session, a: Articulo | None, valores: dict, cache: dict | None = None) -> GrupoCategoria | None:
    """La categoría de un artículo: la puesta a mano en su producto o, si no, la
    primera que se reconoce por sus condiciones, empezando por la familia más
    específica y en el orden de cada familia. Una categoría sin condiciones solo
    se pone a mano."""
    if a is None or a.familia_efectiva is None:
        return None
    familias = [f.id for f in reversed(a.familia_efectiva.ruta())]
    manual = a.producto.grupo_producto if a.producto is not None else None
    if manual is not None and manual.clase == "CATEGORIA":
        # La de su producto, si es de la familia del artículo o de una superior (un artículo puede tener su propia familia)
        return manual if manual.activa and manual.padre_id in familias else None
    clave = ("cats", tuple(familias))
    if cache is None or clave not in cache:
        cats = list(db.scalars(select(GrupoCategoria).where(GrupoCategoria.padre_id.in_(familias),
                                                            GrupoCategoria.activa.is_(True))))
        cats.sort(key=lambda c: (familias.index(c.padre_id), c.orden, c.id))
        if cache is None:
            cache = {}
        cache[clave] = cats
    return next((c for c in cache[clave] if c.condiciones and all(cumple_condicion(x, valores) for x in c.condiciones)), None)


def ruta_efectiva(db: Session, a: Articulo | None, valores: dict, cache: dict | None = None) -> list[GrupoProducto]:
    """Los nodos del artículo de lo más específico a lo más general: su categoría (si tiene),
    su familia y las familias de arriba. Es lo que recorren las reglas de etiquetado y de empaque."""
    if a is None or a.familia_efectiva is None:
        return []
    cat = categoria_de(db, a, valores, cache)
    return ([cat] if cat is not None else []) + list(reversed(a.familia_efectiva.ruta()))


# ---- Validación común ------------------------------------------------------------------------
def codigo_ocupado(db: Session, codigo: str, excepto_id: int | None = None) -> bool:
    """Otro nodo (familia o categoría) ya tiene el código."""
    return bool(db.scalar(select(GrupoProducto.id).where(func.upper(GrupoProducto.codigo) == codigo.upper(),
                                                         GrupoProducto.id != (excepto_id or 0))))


def _usos_propios(db: Session) -> dict[int, dict[str, int]]:
    """Lo del catálogo que apunta a cada nodo: productos, artículos y subgrupos."""
    res: dict[int, dict[str, int]] = {}

    def sumar(clave, filas):
        for gid, n in filas:
            if gid is not None and n:
                res.setdefault(gid, {})[clave] = n

    sumar("articulos", db.execute(select(Producto.grupo_producto_id, func.count()).select_from(Articulo)
                                  .join(Producto, Producto.id == Articulo.producto_id).group_by(Producto.grupo_producto_id)))
    sumar("productos", db.execute(select(Producto.grupo_producto_id, func.count()).group_by(Producto.grupo_producto_id)))
    sumar("hijos", db.execute(select(GrupoProducto.padre_id, func.count()).group_by(GrupoProducto.padre_id)))
    return res


def _conteos(db: Session) -> dict[int, dict[str, int]]:
    """{nodo: {qué: cuántos}}: lo del catálogo y lo de cada módulo (sus secciones)."""
    res = _usos_propios(db)
    for gid, cuenta in secciones.usos(db).items():
        res.setdefault(gid, {}).update(cuenta)
    return res


def usos(db: Session, g: GrupoProducto) -> dict:
    """Qué apunta al nodo: productos, subgrupos y lo de cada módulo (reglas, etiquetas generadas…)."""
    return _conteos(db).get(g.id, {})


def en_uso(db: Session, g: GrupoProducto) -> bool:
    """Algo apunta al nodo (incluso una regla dada de baja o una etiqueta del historial): no se puede borrar."""
    return any(usos(db, g).values())


# ---- Lectura ----------------------------------------------------------------------------------
def _atributos_de(db: Session, g: GrupoProducto) -> dict:
    """Los atributos del nodo: los que se le asignaron (no generales) y los que valen en él por
    nivel (generales, suyos y de las familias que lo contienen), en orden. Los de variante
    («ejes») distinguen las variantes de sus productos."""
    from app.modulos.catalogo import valores as variantes

    propios = [a.codigo for n in ("PRODUCTO", "VARIANTE") for a in variantes.atributos(db, n)
               if not a.general and any(f.id == g.id for f in a.familias)]
    valen = {n: [a.codigo for a in variantes.de_grupo(db, g, n)] for n in ("PRODUCTO", "VARIANTE")}
    return {"atributos": propios, "atributos_producto": valen["PRODUCTO"], "ejes": valen["VARIANTE"]}


def dict_grupo(db: Session, g: GrupoProducto, conteos: dict | None = None) -> dict:
    c = (conteos or {}).get(g.id, {})
    return {"id": g.id, "clase": g.clase, "codigo": g.codigo, "nombre": g.nombre, "descripcion": g.descripcion,
            "padre_id": g.padre_id, "ruta": " / ".join(x.nombre for x in g.ruta()), "profundidad": len(g.ruta()) - 1,
            "condiciones": g.condiciones or [], **_atributos_de(db, g), "campos": g.campos or [],
            "orden": g.orden, "activa": g.activa,
            **{k: c.get(k, 0) for k in ("articulos", "productos", "reglas_etiqueta", "reglas_empaque")},
            "usos": c, "en_uso": any(c.values())}


def arbol(db: Session, user: Usuario, incluir_inactivos: bool = True, clase: str | None = None) -> list[dict]:
    """Todos los nodos en orden de árbol (cada familia, sus categorías y luego sus subfamilias)."""
    exigir_alguno(user, *PERMISOS_VER)
    c = select(GrupoProducto).order_by(GrupoProducto.orden, GrupoProducto.nombre)
    if not incluir_inactivos:
        c = c.where(GrupoProducto.activa.is_(True))
    nodos = list(db.scalars(c))
    ids = {g.id for g in nodos}
    hijos: dict = {}
    for g in nodos:
        hijos.setdefault(g.padre_id if g.padre_id in ids else None, []).append(g)
    conteos = _conteos(db)
    res: list[dict] = []
    vistos: set = set()

    def poner(padre):
        # Primero las categorías (lo más específico de la familia), luego las subfamilias
        for g in sorted(hijos.get(padre, []), key=lambda x: (x.clase != "CATEGORIA", x.orden, x.nombre)):
            if g.id in vistos:
                continue
            vistos.add(g.id)
            if clase is None or g.clase == clase:
                res.append(dict_grupo(db, g, conteos))
            poner(g.id)
    poner(None)
    return res


def campos(db: Session, user: Usuario) -> dict:
    """Los datos del catálogo con que se reconoce una categoría, y los operadores."""
    from app.modulos.catalogo import servicio as catalogo
    from app.modulos.comun.condiciones import OPERADORES_SIMPLES

    exigir_alguno(user, *PERMISOS_VER)
    return {"campos": catalogo.campos_condiciones(db), "operadores": list(OPERADORES_SIMPLES)}


def cargar(db: Session, grupo_id: int) -> GrupoProducto:
    g = db.get(GrupoProducto, grupo_id)
    if g is None:
        raise ErrorNegocio("The product group does not exist.", 404, "no_encontrado")
    return g


def categorias(db: Session, user: Usuario, familia_id: int | None = None) -> list[dict]:
    """Las categorías (de una familia, si se indica), con cuántos artículos caen en cada una."""
    exigir_alguno(user, *PERMISOS_VER)
    c = select(GrupoCategoria).order_by(GrupoCategoria.padre_id, GrupoCategoria.orden, GrupoCategoria.id)
    if familia_id:
        c = c.where(GrupoCategoria.padre_id == familia_id)
    lista = list(db.scalars(c))
    n = _articulos_por_categoria(db, {x.padre_id for x in lista}) if lista else {}
    return [{"id": x.id, "familia_id": x.padre_id, "familia": x.padre.nombre if x.padre else None, "codigo": x.codigo,
             "nombre": x.nombre, "descripcion": x.descripcion, "condiciones": x.condiciones or [], "orden": x.orden,
             "activa": x.activa, "articulos": n.get(x.id, 0)} for x in lista]


def _articulos_por_categoria(db: Session, familias: set[int]) -> dict[int, int]:
    from app.modulos.catalogo import servicio as catalogo

    res: dict[int, int] = {}
    cache: dict = {}
    vistos: set[int] = set()
    for fid in familias:
        for a in catalogo.articulos_de(db, familia_id=fid, limite=MAX_PRUEBA):
            if a.id in vistos:
                continue
            vistos.add(a.id)
            c = catalogo.categoria(db, a, cache)
            if c is not None:
                res[c.id] = res.get(c.id, 0) + 1
    return res


def probar(db: Session, user: Usuario, datos: dict) -> dict:
    """Qué artículos de la familia caerían en una categoría con estas condiciones (sin guardar),
    cuáles ya están en otra y cuáles cambiarían."""
    from app.modulos.catalogo import servicio as catalogo

    exigir_alguno(user, *PERMISOS_EDITAR, "etiquetas.configurar")
    fam = db.get(GrupoFamilia, int(datos.get("familia_id") or 0))
    if fam is None:
        raise ErrorNegocio("The family does not exist.", 404, "no_encontrado")
    condiciones = validar_condiciones(db, datos.get("condiciones") or [])
    propia = int(datos["categoria_id"]) if datos.get("categoria_id") else None
    cache: dict = {}
    entran, ejemplos, en_otra = 0, [], 0
    revisados = catalogo.articulos_de(db, familia_id=fam.id, limite=MAX_PRUEBA)
    for a in revisados:
        v = catalogo.valores_condiciones(db, a, cache)
        if not condiciones or not all(cumple_condicion(x, v) for x in condiciones):
            continue
        entran += 1
        actual = catalogo.categoria(db, a, cache)
        if actual is not None and actual.id != propia:
            en_otra += 1
        if len(ejemplos) < EJEMPLOS:
            ejemplos.append({"articulo_id": a.id, "sku": a.codigo, "descripcion": a.descripcion,
                             "categoria_actual": actual.nombre if actual else None})
    return {"revisados": len(revisados), "entran": entran, "en_otra": en_otra, "ejemplos": ejemplos}


# ---- Alta y cambios ---------------------------------------------------------------------------
def validar_condiciones(db: Session, condiciones) -> list[dict]:
    """Las condiciones limpias o 422: un dato del catálogo, un operador de la lista y un valor del
    tipo que el operador necesita («en_familia» pide el código de una familia que exista)."""
    from app.modulos.catalogo import servicio as catalogo

    def familia(campo, op, valor):
        if op == "en_familia" and ((f := catalogo.nodo_por_codigo(db, valor)) is None or f.es_categoria):
            return f"There is no family {valor}."
        return None

    if condiciones in (None, ""):
        return []
    return limpiar(condiciones, {c["clave"] for c in catalogo.campos_condiciones(db)}, familia)


def validar_campos(db: Session, campos_) -> list[dict]:
    """[{campo, obligatorio}]: los datos que la familia exige a sus productos (del artículo o del producto)."""
    from app.modulos.productos import perfil

    return perfil.validar_campos(db, campos_)


def _validar(db: Session, datos: dict, actual: GrupoProducto | None) -> dict:
    errores, limpio = [], {}
    clase = actual.clase if actual is not None else str(datos.get("clase") or "FAMILIA").upper()
    if clase not in CLASES_GRUPO:
        errores.append({"campo": "clase", "mensaje": "Choose family or category."})
    if actual is None or "codigo" in datos:
        codigo = (datos.get("codigo") or "").strip().upper()
        if not codigo or len(codigo) > 20 or not all(ch.isalnum() or ch in "-_." for ch in codigo):
            errores.append({"campo": "codigo", "mensaje": "Enter a code of up to 20 letters, digits, - _ or ."})
        elif codigo_ocupado(db, codigo, actual.id if actual else None):
            errores.append({"campo": "codigo", "mensaje": "Another family or category has this code."})
        limpio["codigo"] = codigo
    if actual is None or "nombre" in datos:
        nombre = (datos.get("nombre") or "").strip()
        if not nombre or len(nombre) > 100:
            errores.append({"campo": "nombre", "mensaje": "Enter the name (up to 100 characters)."})
        limpio["nombre"] = nombre
    if "descripcion" in datos:
        limpio["descripcion"] = (datos.get("descripcion") or "").strip()[:300] or None
    if actual is None or "padre_id" in datos:
        padre_id = datos.get("padre_id") or None
        padre = db.get(GrupoFamilia, int(padre_id)) if padre_id else None
        if padre_id and padre is None:
            errores.append({"campo": "padre_id", "mensaje": "Choose a family as the parent."})
        elif clase == "CATEGORIA" and padre is None:
            errores.append({"campo": "padre_id", "mensaje": "A category goes inside a family."})
        elif padre is not None and actual is not None and actual in padre.ruta():
            errores.append({"campo": "padre_id", "mensaje": "A family cannot be inside itself or one of its subfamilies."})
        limpio["padre_id"] = padre.id if padre is not None else None
    if "condiciones" in datos:
        if clase != "CATEGORIA" and datos.get("condiciones"):
            errores.append({"campo": "condiciones", "mensaje": "Only a category is recognized by conditions."})
        else:
            limpio["condiciones"] = validar_condiciones(db, datos.get("condiciones") or [])
    if "atributos" in datos:
        # Los atributos que se le asignan a la familia (valen también en sus subfamilias y categorías)
        from app.modelos import Atributo

        codigos = list(dict.fromkeys(str(x).strip().upper() for x in (datos.get("atributos") or []) if str(x).strip()))
        validos = {a.codigo: a for a in db.scalars(select(Atributo).where(Atributo.activo.is_(True)))}
        malos = [x for x in codigos if x not in validos]
        if clase != "FAMILIA" and codigos:
            errores.append({"campo": "atributos", "mensaje": "Attributes are assigned to a family: its categories take them."})
        elif malos:
            errores.append({"campo": "atributos", "mensaje": f"{malos[0]} is not an active attribute."})
        limpio["atributos"] = [validos[x] for x in codigos if x in validos]
    if "campos" in datos:
        # Los datos que la familia vuelve obligatorios: los pide el alta y el cambio de sus productos
        try:
            limpio["campos"] = validar_campos(db, datos.get("campos"))
        except ErrorNegocio as e:
            errores += e.detalle or [{"campo": "campos", "mensaje": e.mensaje}]
    if "orden" in datos:
        try:
            limpio["orden"] = max(int(datos["orden"]), 0)
        except (TypeError, ValueError):
            errores.append({"campo": "orden", "mensaje": "Write a whole number."})
    if "activa" in datos:
        limpio["activa"] = bool(datos["activa"])
    if errores:
        raise ErrorNegocio("Check the product group.", 422, "validacion", errores)
    return limpio


def crear(db: Session, user: Usuario, datos: dict) -> dict:
    exigir_alguno(user, *PERMISOS_EDITAR)
    limpio = _validar(db, datos, None)
    clase = GrupoCategoria if str(datos.get("clase") or "FAMILIA").upper() == "CATEGORIA" else GrupoFamilia
    if "orden" not in limpio:
        limpio["orden"] = (db.scalar(select(func.max(GrupoProducto.orden)).where(
            GrupoProducto.padre_id.is_(None) if limpio["padre_id"] is None else GrupoProducto.padre_id == limpio["padre_id"]))
            or 0) + 10
    atrs = limpio.pop("atributos", None)
    g = clase(**{"activa": True, "condiciones": [], "campos": [], **limpio})
    db.add(g)
    db.flush()
    if atrs:
        _asignar_atributos(db, g, atrs)
    registrar(db, user, "grupo_producto", g.id, "crear", {"codigo": g.codigo, "clase": g.clase, "padre_id": g.padre_id,
                                                          **({"atributos": [a.codigo for a in atrs]} if atrs else {})})
    return dict_grupo(db, g, _conteos(db))


def _asignar_atributos(db: Session, g: GrupoProducto, elegidos: list) -> list | None:
    """Deja asignados a la familia exactamente esos atributos (los generales ya valen en todas).
    Devuelve [antes, después] si cambió."""
    from app.modelos import Atributo
    from app.modulos.catalogo import valores as variantes

    elegidos_ids = {a.id for a in elegidos if not a.general}
    antes, despues = [], []
    for a in db.scalars(select(Atributo).where(Atributo.general.is_(False)).order_by(Atributo.orden, Atributo.codigo)):
        tiene = any(f.id == g.id for f in a.familias)
        if tiene:
            antes.append(a.codigo)
        if a.id in elegidos_ids:
            despues.append(a.codigo)
            if not tiene:
                a.familias.append(g)
        elif tiene:
            a.familias.remove(g)
    variantes.olvidar(db)
    return [antes, despues] if antes != despues else None


def actualizar(db: Session, user: Usuario, grupo_id: int, datos: dict) -> dict:
    exigir_alguno(user, *PERMISOS_EDITAR)
    g = cargar(db, grupo_id)
    limpio = _validar(db, datos, g)
    if g.clase == "CATEGORIA" and limpio.get("padre_id", g.padre_id) != g.padre_id and en_uso(db, g):
        raise ErrorNegocio("The category is in use (rules or products): it cannot move to another family.", 409, "en_uso")
    atrs = limpio.pop("atributos", None)
    cambios = {k: [getattr(g, k), v] for k, v in limpio.items() if getattr(g, k) != v}
    for k, v in limpio.items():
        setattr(g, k, v)
    db.flush()
    if atrs is not None and (cambio := _asignar_atributos(db, g, atrs)):
        cambios["atributos"] = cambio
    if "atributos" in cambios or "padre_id" in cambios:
        # Quitarle atributos o moverla no deja valores guardados fuera de la familia de su atributo
        from app.modulos.catalogo import valores as variantes
        from app.modulos.maestros import atributos as atr_svc

        variantes.olvidar(db)
        atr_svc.exigir(atr_svc.sin_alcance(db, campo="atributos"), "The family's products use those attributes.")
    if cambios:
        registrar(db, user, "grupo_producto", g.id, "editar", {k: v for k, v in cambios.items() if k != "condiciones"}
                  | ({"condiciones": True} if "condiciones" in cambios else {}))
    return dict_grupo(db, g, _conteos(db))


def ordenar(db: Session, user: Usuario, ids: list[int]) -> list[dict]:
    """El orden de los nodos: el de la lista recibida (cada uno entre sus hermanos)."""
    exigir_alguno(user, *PERMISOS_EDITAR)
    nodos = {g.id: g for g in db.scalars(select(GrupoProducto).where(GrupoProducto.id.in_(set(ids))))}
    if not ids or len(nodos) != len(set(ids)):
        raise ErrorNegocio("Some families do not exist.", 422, "validacion")
    for i, gid in enumerate(ids, start=1):
        nodos[gid].orden = i * 10
    db.flush()
    registrar(db, user, "grupo_producto", 0, "ordenar", {"orden": ids})
    return arbol(db, user)


def eliminar(db: Session, user: Usuario, grupo_id: int) -> dict:
    """Solo un nodo sin uso; si se usa, se desactiva."""
    exigir_alguno(user, *PERMISOS_EDITAR)
    g = cargar(db, grupo_id)
    if en_uso(db, g):
        raise ErrorNegocio("The group has items, products, rules or subgroups: deactivate it instead.", 409, "en_uso")
    registrar(db, user, "grupo_producto", g.id, "eliminar", {"codigo": g.codigo, "clase": g.clase})
    db.delete(g)
    db.flush()
    return {"ok": True}


# ---- Productos de cada familia ------------------------------------------------------------------
def _productos_elegidos(db: Session, user: Usuario, ids: list[int]) -> list[Producto]:
    if not ids:
        raise ErrorNegocio("Choose the products.", 422, "validacion")
    c = select(Producto).where(Producto.id.in_(set(ids)))
    prov = proveedor_filtro(user)
    if prov is not None:
        c = c.where(Producto.proveedor_id.in_(prov))
    elegidos = list(db.scalars(c))
    if len(elegidos) != len(set(ids)):
        raise ErrorNegocio("Some products do not exist or are out of your scope.", 404, "no_encontrado")
    return elegidos


def _exigir_atributos(db: Session, productos: list[Producto], grupo) -> None:
    """Los atributos que ya tienen los productos (y sus variantes) deben valer en su familia nueva."""
    from app.modulos.maestros import atributos as atr_svc

    atr_svc.exigir([{**e, "mensaje": f"{p.codigo_generico or p.nombre}: {e['mensaje']}"}
                    for p in productos for e in atr_svc.fuera_de_familia(db, p, grupo)],
                   "Some products have attributes that do not apply to that family.")


def asignar_productos(db: Session, user: Usuario, familia_id: int | None, ids: list[int]) -> dict:
    """Pone (o quita, con familia vacía) la familia de varios productos: la comparten sus variantes.
    Una categoría puesta a mano se conserva si es de esa familia."""
    exigir_alguno(user, *PERMISOS_EDITAR)
    fam = db.get(GrupoFamilia, familia_id) if familia_id is not None else None
    if familia_id is not None and (fam is None or not fam.activa):
        raise ErrorNegocio("The family does not exist or is inactive.", 422, "validacion")
    elegidos = _productos_elegidos(db, user, ids)
    cambiados = [p for p in elegidos if p.familia_etiquetado_id != familia_id]
    _exigir_atributos(db, cambiados, fam)
    for p in cambiados:
        p.familia_etiquetado_id = familia_id
    db.flush()
    if cambiados:
        registrar(db, user, "grupo_producto", familia_id or 0, "asignar_productos",
                  {"familia_id": familia_id, "productos": [p.codigo_generico or p.nombre for p in cambiados[:50]]})
    return {"cambiados": len(cambiados), "elegidos": len(elegidos)}


def asignar_articulos(db: Session, user: Usuario, familia_id: int | None, ids: list[int]) -> dict:
    """La familia es del producto: la pone (o la quita) en los productos de esos artículos."""
    exigir_alguno(user, *PERMISOS_EDITAR)
    if not ids:
        raise ErrorNegocio("Choose the items.", 422, "validacion")
    productos = sorted(set(db.scalars(select(Articulo.producto_id).where(Articulo.id.in_(set(ids))))))
    if len(set(db.scalars(select(Articulo.id).where(Articulo.id.in_(set(ids)))))) != len(set(ids)):
        raise ErrorNegocio("Some items do not exist or are out of your scope.", 404, "no_encontrado")
    r = asignar_productos(db, user, familia_id, productos) if productos else {"cambiados": 0}
    return {"cambiados": r["cambiados"], "elegidos": len(set(ids)), "productos": len(productos)}


def asignar_categoria(db: Session, user: Usuario, categoria_id: int | None, ids: list[int]) -> dict:
    """Pone a mano la categoría de varios productos (o la quita: vuelve a reconocerse sola)."""
    exigir_alguno(user, *PERMISOS_EDITAR)
    cat = db.get(GrupoCategoria, categoria_id) if categoria_id else None
    if categoria_id and cat is None:
        raise ErrorNegocio("The category does not exist.", 404, "no_encontrado")
    if cat is not None and not cat.activa:
        raise ErrorNegocio("The category is inactive.", 422, "validacion")
    elegidos = _productos_elegidos(db, user, ids)
    cambiados = [p for p in elegidos if p.categoria_etiquetado_id != (cat.id if cat else None)]
    if cat is not None:  # quitarla deja la misma familia
        _exigir_atributos(db, cambiados, cat)
    for p in cambiados:
        p.categoria_etiquetado_id = cat.id if cat else None
    db.flush()
    if cambiados:
        registrar(db, user, "grupo_producto", cat.id if cat else 0, "asignar_categoria",
                  {"categoria_id": cat.id if cat else None, "productos": [p.codigo_generico or p.nombre for p in cambiados[:50]]})
    return {"cambiados": len(cambiados), "elegidos": len(elegidos)}


# ---- Secciones de los módulos -------------------------------------------------------------------
def leer_secciones(db: Session, user: Usuario, grupo_id: int) -> list[dict]:
    exigir_alguno(user, *PERMISOS_VER)
    g = cargar(db, grupo_id)
    return secciones.leer_todas(db, user, g.id, g.clase == "CATEGORIA")


def guardar_seccion(db: Session, user: Usuario, grupo_id: int, clave: str, datos: dict) -> dict:
    g = cargar(db, grupo_id)
    s = secciones.seccion(clave)
    if s.solo_familias and g.clase == "CATEGORIA":
        raise ErrorNegocio("This section is for families, not categories.", 422, "validacion")
    return secciones.guardar(db, user, g.id, clave, datos)
