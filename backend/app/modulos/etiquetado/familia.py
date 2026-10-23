"""Lo del etiquetado en la familia del catálogo.

La familia (y sus categorías) es una sola y la edita el catálogo
(`catalogo/familias.py`). El etiquetado le agrega su sección: los campos que
esperan las etiquetas de sus productos (y cuáles son obligatorios para
imprimir). Las reglas de diseño por familia o categoría están en usos_diseno.

Aquí también están las lecturas que las pantallas del etiquetado hacen de las
familias (con lo de etiquetado de cada una), los productos y los artículos, y el
asistente que arma una familia en un solo paso (los datos de la familia los
guarda el catálogo; los diseños, el etiquetado).
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errores import ErrorNegocio
from app.modelos import EtiquetadoFamilia, GeneracionItem, Marca, UsoDiseno, Usuario
from app.modulos.acceso.permisos import exigir, exigir_alguno, exigir_interno, proveedor_filtro
from app.modulos.catalogo import familias as controlador
from app.modulos.catalogo import servicio as catalogo
from app.modulos.catalogo.secciones import SeccionFamilia, registrar_seccion_familia
from app.modulos.comun.historial import registrar

MAX_CAMPOS = 60


# ---- La sección: campos que piden sus etiquetas ---------------------------------------------------
def validar_campos(db: Session, campos) -> list[dict]:
    """[{campo, obligatorio}] con campos del artículo o del producto que existan."""
    from app.modulos.etiquetado import campos as svc_campos

    if campos is None:
        return []
    if not isinstance(campos, list) or len(campos) > MAX_CAMPOS:
        raise ErrorNegocio(f"At most {MAX_CAMPOS} fields per family.", 422, "validacion")
    validos = {c.clave for c in svc_campos.catalogo(db, "ARTICULO") if c.grupo in ("articulo", "producto")}
    limpio, vistos = [], set()
    for x in campos:
        clave = (x or {}).get("campo") if isinstance(x, dict) else None
        if clave not in validos:
            raise ErrorNegocio(f"Unknown item field: {clave}.", 422, "validacion",
                               [{"campo": "campos", "mensaje": f"Unknown item field: {clave}."}])
        if clave in vistos:
            continue
        vistos.add(clave)
        limpio.append({"campo": clave, "obligatorio": bool(x.get("obligatorio"))})
    return limpio


def _propios(db: Session) -> dict[int, list[dict]]:
    return {f.familia_id: list(f.campos or []) for f in db.scalars(select(EtiquetadoFamilia))}


def _de_ruta(db: Session, familia_id: int | None, propios: dict | None = None) -> tuple[list[dict], list[dict]]:
    """(los campos de la familia, los heredados de las que la contienen)."""
    f = catalogo.nodo(db, familia_id)
    if f is None:
        return [], []
    propios = _propios(db) if propios is None else propios
    return propios.get(f.id, []), [c for x in f.ruta_ids[:-1] for c in propios.get(x, [])]


def obligatorios(db: Session, familia_id: int | None) -> list[str]:
    """Campos obligatorios de la familia y de las familias que la contienen."""
    suyos, heredados = _de_ruta(db, familia_id)
    res: list[str] = []
    for c in heredados + suyos:
        if c.get("obligatorio") and c["campo"] not in res:
            res.append(c["campo"])
    return res


def faltantes(db: Session, familia_id: int | None, valores: dict) -> list[str]:
    """Campos obligatorios de la familia (incluidos los heredados) que el artículo no tiene."""
    return [c for c in obligatorios(db, familia_id) if valores.get(c) in (None, "")]


def _leer(db: Session, familia_id: int) -> dict:
    suyos, heredados = _de_ruta(db, familia_id)
    reglas = db.scalar(select(func.count()).select_from(UsoDiseno).where(
        UsoDiseno.grupo_id == familia_id, UsoDiseno.eliminado_en.is_(None))) or 0
    return {"campos": suyos, "heredados": heredados, "reglas": reglas}


def _guardar(db: Session, user: Usuario, familia_id: int, datos: dict) -> dict:
    if catalogo.nodo(db, familia_id) is None:
        raise ErrorNegocio("The family does not exist.", 404, "no_encontrado")
    campos = validar_campos(db, datos.get("campos"))
    fila = db.get(EtiquetadoFamilia, familia_id)
    antes = list(fila.campos or []) if fila else []
    if fila is None:
        fila = EtiquetadoFamilia(familia_id=familia_id)
        db.add(fila)
    fila.campos = campos
    db.flush()
    if antes != campos:
        registrar(db, user, "grupo_producto", familia_id, "etiquetado", {"campos": [antes, campos]})
    return _leer(db, familia_id)


def _usos(db: Session) -> dict[int, dict[str, int]]:
    res: dict[int, dict[str, int]] = {}

    def sumar(clave, filas):
        for gid, n in filas:
            if gid is not None:
                res.setdefault(gid, {})[clave] = n

    sumar("reglas_etiqueta", db.execute(select(UsoDiseno.grupo_id, func.count()).where(UsoDiseno.eliminado_en.is_(None))
                                        .group_by(UsoDiseno.grupo_id)))
    sumar("reglas_etiqueta_bajas", db.execute(select(UsoDiseno.grupo_id, func.count()).where(UsoDiseno.eliminado_en.is_not(None))
                                              .group_by(UsoDiseno.grupo_id)))
    sumar("etiquetas", db.execute(select(GeneracionItem.grupo_id, func.count()).group_by(GeneracionItem.grupo_id)))
    return res


registrar_seccion_familia(SeccionFamilia(
    clave="etiquetado", nombre="Labeling", orden=40, leer=_leer, guardar=_guardar, usos=_usos,
    permisos_ver=("etiquetas.ver", "etiquetas.familias"), permisos_editar=("etiquetas.familias",)))


# ---- Lecturas de las pantallas del etiquetado ----------------------------------------------------
def cargar(db: Session, familia_id: int) -> catalogo.FichaFamilia:
    f = catalogo.nodo(db, familia_id)
    if f is None or f.es_categoria:
        raise ErrorNegocio("The family does not exist.", 404, "no_encontrado")
    return f


def listar(db: Session, user: Usuario, activas: bool | None = None) -> list[dict]:
    """Las familias del catálogo con lo del etiquetado de cada una: sus campos, los heredados y
    cuántos artículos, productos y reglas de diseño tiene."""
    exigir_interno(user, "etiquetas.ver", "etiquetas.familias")
    propios = _propios(db)
    articulos = catalogo.contar_por_familia(db)
    productos = catalogo.contar_productos_por_familia(db)
    reglas = dict(db.execute(select(UsoDiseno.grupo_id, func.count()).where(
        UsoDiseno.nivel == "FAMILIA", UsoDiseno.eliminado_en.is_(None)).group_by(UsoDiseno.grupo_id)).all())
    res = []
    for f in sorted(catalogo.familias(db).values(), key=lambda f: (f.orden, f.nombre)):
        if f.es_categoria or (activas is not None and f.activa != activas):
            continue
        suyos, heredados = _de_ruta(db, f.id, propios)
        res.append({"id": f.id, "codigo": f.codigo, "nombre": f.nombre, "padre_id": f.padre_id, "ruta": f.texto_ruta,
                    "orden": f.orden, "activa": f.activa, "campos": suyos, "heredados": heredados,
                    "articulos": articulos.get(f.id, 0), "productos": productos.get(f.id, 0), "usos": reglas.get(f.id, 0)})
    return res


def _filtro_familia(familia) -> dict:
    if familia == "sin":
        return {"sin_familia": True}
    return {"familia_exacta_id": int(familia)} if familia else {}


def productos(db: Session, user: Usuario, q: str | None = None, familia: str | None = None, page: int = 1,
              size: int = 50) -> dict:
    """Productos con su familia, su categoría de etiquetado y cuántas variantes tienen."""
    from app.modulos.etiquetado import reglas

    exigir_alguno(user, "etiquetas.ver", "etiquetas.familias")
    filtro = catalogo.ids_productos(texto=q, proveedores=proveedor_filtro(user), **_filtro_familia(familia))
    total, filas = catalogo.pagina_productos(db, filtro, page, size)
    variantes = catalogo.contar_articulos_por_producto(db, [p.id for p in filas])
    cache: dict = {}
    res = []
    for p in filas:
        cats = [reglas.categoria_de(db, a, cache) for a in catalogo.articulos_de(db, producto_id=p.id)]
        distintas = {c.id: c for c in cats if c is not None}
        cat = next(iter(distintas.values())) if len(distintas) == 1 else None
        parcial = len(distintas) > 1 or (cat is not None and None in cats)
        fam = p.familia
        manual = p.grupo_id if p.grupo_id is not None and (fam is None or p.grupo_id != fam.id) else None
        res.append({"id": p.id, "nombre": p.nombre, "codigo_generico": p.codigo, "atributos": p.datos,
                    "variantes": variantes.get(p.id, 0), "familia_propia_id": fam.id if fam else None,
                    "familia_id": fam.id if fam else None, "familia": fam.nombre if fam else None,
                    "familia_origen": "PRODUCTO" if fam else None,
                    "categoria_id": cat.id if cat else None, "categoria": cat.nombre if cat else None,
                    "categoria_propia_id": manual,
                    "categoria_origen": ("MANUAL" if cat and cat.id == manual else "CONDICIONES") if cat else None,
                    "categoria_parcial": parcial, "categorias": [c.nombre for c in distintas.values()]})
    return {"total": total, "items": res}


def articulos(db: Session, user: Usuario, q=None, familia=None, producto_id=None, page: int = 1, size: int = 50,
              ids: list[int] | None = None, solo_ids: bool = False) -> dict:
    """Artículos activos (de la familia de su producto, si se indica) para elegir o ver su familia."""
    exigir_alguno(user, "etiquetas.ver", "etiquetas.familias")
    filtro = catalogo.ids(texto=q, proveedores=proveedor_filtro(user), producto_id=producto_id, solo_activos=True,
                          **_filtro_familia(familia))
    if ids:
        filtro = catalogo.ids_entre(filtro, ids)
    if solo_ids:
        return {"ids": catalogo.lista_ids(db, filtro, 5000)}
    total, filas = catalogo.pagina_articulos(db, filtro, page, size)
    marcas = {m.codigo: m.nombre for m in db.scalars(select(Marca))}
    return {"total": total, "items": [{
        "id": a.id, "sku": a.codigo, "variante": a.texto_variante, "descripcion": a.descripcion,
        "producto": a.producto_nombre, "generico": a.producto_codigo, "marca": marcas.get(a.marca),
        "producto_id": a.producto_id, "familia_id": a.familia.id if a.familia else None,
        "familia": a.familia.nombre if a.familia else None, "familia_origen": "PRODUCTO" if a.familia else None}
        for a in filas]}


# ---- Asistente: una familia lista para etiquetar en un solo paso ---------------------------------
def configurar(db: Session, user: Usuario, datos: dict) -> dict:
    """Termina el asistente de una familia en una sola operación (todo o nada): sus datos
    (`familia`, con `id` si ya existe; los guarda el catálogo), los campos de sus etiquetas,
    lo que entra en ella (`productos`, `articulos`: ids; un artículo lleva a su producto) y su
    diseño normal por tipo de etiqueta (`disenos`: [{tipo_etiqueta_id, plantilla_id}],
    plantilla_id vacío = hereda). Mientras el asistente está a medias nada de esto cambia."""
    from app.modulos.etiquetado import usos as svc_usos

    exigir(user, "etiquetas.familias")
    fam = datos.get("familia") or {}
    if not isinstance(fam, dict):
        raise ErrorNegocio("Check the family.", 422, "validacion")
    cuerpo = {k: fam[k] for k in ("codigo", "nombre", "padre_id", "descripcion", "activa") if k in fam}
    r = controlador.actualizar(db, user, int(fam["id"]), cuerpo) if fam.get("id") else \
        controlador.crear(db, user, {**cuerpo, "clase": "FAMILIA"})
    fid = r["id"]
    if "campos" in fam:
        _guardar(db, user, fid, {"campos": fam["campos"]})
    hecho = {"productos": 0, "articulos": 0, "disenos": 0}
    if datos.get("productos"):
        hecho["productos"] = controlador.asignar_productos(db, user, fid, [int(x) for x in datos["productos"]])["cambiados"]
    if datos.get("articulos"):
        hecho["articulos"] = controlador.asignar_articulos(db, user, fid, [int(x) for x in datos["articulos"]])["cambiados"]
    disenos = datos.get("disenos") or []
    if disenos:
        exigir(user, "etiquetas.configurar")
    for d in disenos:
        tipo_id = int((d or {}).get("tipo_etiqueta_id") or 0)
        antes = next((u for u in svc_usos._usos_celda(db, svc_usos.celda_de(tipo_id, "FAMILIA", fid))
                      if u.contexto_tipo == "NINGUNO"), None)
        nuevo = d.get("plantilla_id") or None
        if (antes.plantilla_id if antes else None) == nuevo:
            continue
        svc_usos.guardar_celda(db, user, {"tipo_etiqueta_id": tipo_id, "nivel": "FAMILIA", "destino_id": fid,
                                          "normal": {"plantilla_id": nuevo} if nuevo else None,
                                          "motivo_cambio": "Family set up step by step"})
        hecho["disenos"] += 1
    familia = next((f for f in listar(db, user) if f["id"] == fid), None)
    return {"familia": familia, "hecho": hecho}
