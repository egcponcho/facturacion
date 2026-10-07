"""Dominios y categorías de producto como configuración (CRUD).

Agregar un dominio nuevo (p. ej. ELECTRONICS) con sus categorías, atributos,
ámbitos y reglas, y habilitar sus capítulos, basta para que la ficha lo
ofrezca y el motor lo clasifique: no hace falta programar una ficha.
"""
import json
import re

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..datos import MOTOR
from ..models import CategoriaProducto, DominioClasificacion, Usuario
from .common import ErrorNegocio, exigir, registrar

DATOS = MOTOR


def sembrar(db: Session) -> int:
    """Categorías iniciales como datos: las de la ficha de ropa, calzado y
    accesorios (motor_atributos.json) y las técnicas de químicos y materias
    primas (motor_tecnico.json). Crea las que faltan y completa los campos
    vacíos; la base manda después. Una categoría solo decide qué preguntar."""
    datos = json.loads((DATOS / "motor_atributos.json").read_text(encoding="utf-8"))
    tecnico = json.loads((DATOS / "motor_tecnico.json").read_text(encoding="utf-8"))
    existentes = {c.codigo: c for c in db.scalars(select(CategoriaProducto))}
    n = 0
    filas = datos["categorias"] + tecnico["categorias"]  # cada categoría trae su dominio
    for c in filas:
        x = existentes.get(c["codigo"])
        if not x:
            x = CategoriaProducto(codigo=c["codigo"], nombre=c["nombre"], orden=c.get("orden", 0), activo=True)
            db.add(x)
            n += 1
        for k in ("grupo", "dominio", "alias", "familia", "nombre_corto", "nombre_aduana", "patrones", "capitulos", "plantilla_aduana", "terminos"):
            if getattr(x, k) in (None, [], "", {}) and c.get(k) not in (None, [], "", {}):
                setattr(x, k, c[k])
    db.flush()
    return n


def _cat(x: CategoriaProducto) -> dict:
    return {c: getattr(x, c) for c in ("id", "codigo", "nombre", "grupo", "dominio", "alias", "orden", "activo", "familia",
                                       "nombre_corto", "nombre_aduana", "patrones", "capitulos", "plantilla_aduana", "terminos")}


def categorias(db: Session, solo_activas: bool = True) -> list[dict]:
    q = select(CategoriaProducto).order_by(CategoriaProducto.orden, CategoriaProducto.nombre)
    if solo_activas:  # la ficha: sin las categorías de familias en borrador
        borrador = select(DominioClasificacion.codigo).where(DominioClasificacion.estado == "BORRADOR")
        q = q.where(CategoriaProducto.activo.is_(True), or_(CategoriaProducto.dominio.is_(None), CategoriaProducto.dominio.not_in(borrador)))
    return [_cat(x) for x in db.scalars(q)]


def guardar_categoria(db: Session, user: Usuario, cat_id: int | None, datos: dict) -> dict:
    exigir(user, "clasificacion.configurar")
    x = db.get(CategoriaProducto, cat_id) if cat_id else None
    if cat_id and not x:
        raise ErrorNegocio("The category does not exist.", 404, "no_encontrado")
    x = aplicar(db, x, datos)
    registrar(db, user, "aranceles", x.id, "categoria", {"codigo": x.codigo, "dominio": x.dominio})
    return _cat(x)


def aplicar(db: Session, x: CategoriaProducto | None, datos: dict) -> CategoriaProducto:
    """Crea (x None) o cambia una categoría con sus datos validados: dominio que
    existe, capítulos de 2 dígitos, patrones que compilan y plantilla aduanera
    que nombra atributos y partes que existen. La usan la pantalla y el paquete."""
    from . import validacion_config as v

    if not x:
        cod = re.sub(r"[^a-z0-9_]+", "_", (datos.get("codigo") or datos.get("nombre") or "").strip().lower()).strip("_")[:40]
        if not cod or db.scalar(select(CategoriaProducto.id).where(CategoriaProducto.codigo == cod)):
            raise ErrorNegocio("Give the category a code that is not in use.", 422, "validacion")
        x = CategoriaProducto(codigo=cod, orden=(db.scalar(select(func.max(CategoriaProducto.orden))) or 0) + 10)
        db.add(x)
    ctx = v.Contexto(db)
    for k in ("nombre", "grupo", "dominio", "alias", "orden", "activo", "familia", "nombre_corto", "nombre_aduana", "patrones", "capitulos",
              "plantilla_aduana", "terminos"):
        if k in datos and datos[k] is not None:
            setattr(x, k, datos[k])
    if "dominio" in datos and not datos["dominio"]:
        x.dominio = None  # fuera de una familia: ficha genérica
    # Cómo se reconoce en el nombre y su descripción aduanera: validados
    if datos.get("patrones") is not None:
        for i, p in enumerate(datos["patrones"], start=1):
            if not isinstance(p, dict) or not p.get("re"):
                raise ErrorNegocio(f"Pattern {i}: give the text pattern (re) that recognizes the category.", 422, "configuracion_invalida")
            v._regex(p["re"], f"Pattern {i}")
    if datos.get("plantilla_aduana") is not None:
        x.plantilla_aduana = v.plantilla(ctx, datos["plantilla_aduana"], "Customs template")
    if x.capitulos is not None:
        caps = sorted({"".join(ch for ch in str(c) if ch.isdigit()) for c in x.capitulos if str(c).strip()})
        malos = [c for c in caps if len(c) != 2 or not 1 <= int(c) <= 99]
        if malos:
            raise ErrorNegocio(f"These are not chapters (2 digits, 01 to 99): {', '.join(malos)}.", 422, "validacion")
        x.capitulos = caps
    if not (x.nombre or "").strip():
        raise ErrorNegocio("The name is required.", 422, "validacion")
    if x.dominio and not db.scalar(select(DominioClasificacion.id).where(DominioClasificacion.codigo == x.dominio)):
        raise ErrorNegocio(f"Domain {x.dominio} does not exist.", 422, "validacion")
    db.flush()
    return x


def importar_hojas(db: Session, hojas: dict, cuenta, error, fase: int = 1) -> None:
    """Hoja Categories de un paquete del motor: una familia nueva llega con sus
    categorías (código, nombre, dominio, cómo reconocerla, capítulos y plantilla
    aduanera). Actualiza por código; lo inválido se informa por fila. Fase 1
    (antes de los atributos, que las nombran en sus ámbitos): todo menos la
    plantilla; fase 2 (después): la plantilla, que nombra atributos y partes."""
    from .oficial import _si, _txt
    from .atributos import json_celda

    for f in hojas.get("Categories", []):
        cod = (_txt(f.get("category_code")) or "").strip().lower()
        if not cod:
            if fase == 1:
                error("Categories", f["_fila"], "Category code is required.")
            continue
        if fase == 2:
            x = db.scalar(select(CategoriaProducto).where(CategoriaProducto.codigo == cod))
            try:
                plantilla = json_celda(f.get("customs_template_json"), "Customs template JSON")
                if x and plantilla is not None:
                    with db.begin_nested():
                        aplicar(db, x, {"plantilla_aduana": plantilla})
            except ErrorNegocio as e:
                error("Categories", f["_fila"], str(e))
            continue
        try:
            datos = {"codigo": cod, "nombre": _txt(f.get("name")), "dominio": (_txt(f.get("domain")) or "").upper() or None,
                     "grupo": _txt(f.get("group")), "nombre_corto": _txt(f.get("short_name")), "nombre_aduana": _txt(f.get("customs_name")),
                     "alias": _txt(f.get("aliases")), "terminos": _txt(f.get("search_terms")),
                     "capitulos": [c.strip() for c in str(_txt(f.get("chapters")) or "").replace(";", ",").split(",") if c.strip()] or None,
                     "patrones": json_celda(f.get("patterns_json"), "Patterns JSON")}
            json_celda(f.get("customs_template_json"), "Customs template JSON")  # que sea JSON; se aplica en la fase 2
            if f.get("active") is not None:
                datos["activo"] = _si(f.get("active"))
            x = db.scalar(select(CategoriaProducto).where(CategoriaProducto.codigo == cod))
            with db.begin_nested():
                aplicar(db, x, {k: v for k, v in datos.items() if v is not None})
            cuenta("Categories", x is None)
        except ErrorNegocio as e:
            error("Categories", f["_fila"], str(e))


def guardar_dominio(db: Session, user: Usuario, dom_id: int | None, datos: dict) -> dict:
    """Crea o edita un dominio. No se borra: se desactiva (archiva)."""
    exigir(user, "clasificacion.configurar")
    d = db.get(DominioClasificacion, dom_id) if dom_id else None
    if dom_id and not d:
        raise ErrorNegocio("The domain does not exist.", 404, "no_encontrado")
    if not d:
        cod = re.sub(r"[^A-Z0-9_]+", "_", (datos.get("codigo") or "").strip().upper()).strip("_")[:30]
        if not cod or db.scalar(select(DominioClasificacion.id).where(DominioClasificacion.codigo == cod)):
            raise ErrorNegocio("Give the domain a code that is not in use (e.g. ELECTRONICS).", 422, "validacion")
        # Una familia nueva nace en borrador: se prueba y se publica cuando está lista
        d = DominioClasificacion(codigo=cod, orden=(db.scalar(select(func.max(DominioClasificacion.orden))) or 0) + 10, estado="BORRADOR")
        db.add(d)
    for k in ("nombre", "descripcion", "modo", "activo", "orden"):
        if k in datos and datos[k] is not None:
            setattr(d, k, datos[k].upper() if k == "modo" else datos[k])
    if not (d.nombre or "").strip():
        raise ErrorNegocio("The name is required.", 422, "validacion")
    if d.modo not in ("AUTO", "MANUAL"):
        raise ErrorNegocio("Mode must be AUTO or MANUAL.", 422, "validacion")
    db.flush()
    registrar(db, user, "aranceles", d.id, "dominio", {"codigo": d.codigo, "activo": d.activo})
    return {"id": d.id, "codigo": d.codigo, "nombre": d.nombre, "descripcion": d.descripcion, "modo": d.modo, "activo": d.activo,
            "estado": d.estado}
