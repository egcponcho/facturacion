"""Recetas de empaque y reglas de empaque.

Una receta dice cómo se empaca un artículo en N niveles armados con los tipos
del catálogo (inner pack ⊂ master ⊂ pallet…): cada nivel lleva N unidades del
nivel de abajo y el primero N unidades del artículo (pares, piezas o, en un
packs y kits: el contenido es el artículo, no el empaque).

Quién decide la receta de una posición de OC, de mayor a menor:
1. la elegida a mano en la posición (MANUAL);
2. el casepack e inner pack que trae la OC (DATOS): se usa la receta con esa
   forma o se crea una automática;
3. la regla de empaque que aplica (REGLA): gana la más específica (artículo,
   producto, grupo de producto más profundo, toda la empresa); con condiciones gana
   sobre sin condiciones; si empatan, la de arriba en la lista.

La posición guarda una foto de los niveles: cambiar la receta después no
altera las OC emitidas. Mientras conviven con la receta, casepack e
inner_pack de los sólidos se calculan de ella (el empaque y los documentos
los siguen leyendo).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session, object_session, selectinload

from app.core.errores import ErrorNegocio
from app.modelos import (
    Centro,
    FacturaLinea,
    OrdenCompra,
    PosicionOC,
    Proveedor,
    RecetaEmpaque,
    RecetaNivel,
    ReglaEmpaque,
    TipoEmpaque,
    Usuario,
    ahora,
)
from app.modulos.acceso.permisos import asegurar_proveedor, exigir, exigir_alguno
from app.modulos.catalogo import servicio as catalogo
from app.modulos.comun import condiciones as cond
from app.modulos.comun.historial import registrar, verificar_version

CODIGO = re.compile(r"^[A-Z0-9][A-Z0-9_.-]{0,29}$")
MAX_NIVELES = 8
MAX_CANTIDAD = 100000
MAX_PROBAR = 5000  # posiciones abiertas que se revisan al medir el impacto de una regla
ABIERTAS = ("BORRADOR", "EN_APROBACION", "RECHAZADA", "APROBADA")
DESTINOS = ("EMPRESA", "GRUPO", "PRODUCTO", "ARTICULO")
PESO_DESTINO = {"EMPRESA": 1, "GRUPO": 2, "PRODUCTO": 3, "ARTICULO": 4}

# Datos de la posición, su OC y su artículo que las condiciones de una regla pueden usar. Además,
# un dato por atributo de producto y de variante de la empresa: «linea.atributo.<código>» (la foto
# de la línea), sin suponer qué atributos usa
CAMPOS = [
    ("oc.proveedor", "Supplier", "texto"), ("oc.sociedad", "Company", "texto"), ("oc.centro", "Center", "texto"),
    ("oc.centro_destino", "Destination center", "texto"), ("oc.pais_destino", "Destination country", "texto"),
    ("oc.pais_origen", "Country of origin", "texto"), ("oc.incoterm", "Incoterm", "texto"),
    ("oc.puerto_despacho", "Port of shipment", "texto"), ("linea.familia", "Product family (code)", "texto"),
    ("linea.unidad", "Unit", "texto"), ("linea.cantidad", "Quantity", "numero"), ("linea.almacen", "Warehouse", "texto"),
    ("linea.tipo", "Simple, pack or kit", "texto"), ("articulo.sku", "SKU", "texto"),
]


def campos(db: Session) -> list[tuple]:
    """Los datos fijos y uno por atributo de producto y de variante activo."""
    return CAMPOS + [(f"linea.atributo.{a['codigo']}", a["nombre"], "numero" if a["tipo"] == "numero" else "texto")
                     for a in (*catalogo.atributos(db, "PRODUCTO"), *catalogo.atributos(db))]


def nombres_campos(db: Session) -> dict[str, str]:
    return {c: e for c, e, _ in campos(db)}


# ---- Receta: foto, totales y forma ----------------------------------------------------------
def _medida(n, tipo: TipoEmpaque | None, campo: str):
    v = getattr(n, campo, None) if not isinstance(n, dict) else n.get(campo)
    return v if v is not None else (getattr(tipo, campo, None) if tipo is not None else None)


def foto(r: RecetaEmpaque) -> dict:
    """Los niveles de la receta tal como quedan en una posición (no cambian si la receta cambia)."""
    unidades, niveles = 1, []
    for n in r.niveles:
        t = n.tipo_empaque
        unidades *= n.cantidad
        niveles.append({"orden": n.orden, "tipo_empaque_id": t.id, "codigo": t.codigo, "nombre": t.nombre,
                        "cuenta_como": t.cuenta_como, "cantidad": n.cantidad, "unidades": unidades,
                        "largo": _medida(n, t, "largo"), "ancho": _medida(n, t, "ancho"), "alto": _medida(n, t, "alto"),
                        "tara": _medida(n, t, "tara"), "opcional": n.opcional})
    return {"receta_id": r.id, "codigo": r.codigo, "nombre": r.nombre, "niveles": niveles}


def derivar(f: dict | None) -> tuple[int | None, int | None]:
    """(casepack, inner_pack) de una foto: unidades del primer nivel que cuenta
    como bulto y del nivel justo dentro de él."""
    niveles = (f or {}).get("niveles") or []
    for i, n in enumerate(niveles):
        if n["cuenta_como"] == "BULTO":
            return n["unidades"], (niveles[i - 1]["unidades"] if i > 0 else None)
    sin_soporte = [n for n in niveles if n["cuenta_como"] != "SOPORTE"]
    return (sin_soporte[-1]["unidades"], None) if sin_soporte else (None, None)


def resumen(f: dict | None) -> str | None:
    """«Master carton 24 · Inner pack 12 · Pallet 960» para mostrar la forma de una receta."""
    if not f or not f.get("niveles"):
        return None
    return " · ".join(f"{n['nombre']} {n['unidades']:g}" for n in reversed(f["niveles"]))


def calcular(db: Session, niveles: list[dict], articulo_id: int | None = None) -> dict:
    """Totales de cada nivel (unidades del artículo, volumen, tara y, con un
    artículo con peso, peso neto y bruto por unidad) y avisos de los límites del tipo."""
    tipos = {t.id: t for t in db.scalars(select(TipoEmpaque).where(TipoEmpaque.id.in_(
        [n.get("tipo_empaque_id") for n in niveles if n.get("tipo_empaque_id")])))}
    art = catalogo.articulo(db, articulo_id)
    peso = art.peso if art is not None else None
    res, avisos, unidades, tara_dentro = [], [], 1, 0.0
    for i, n in enumerate(niveles):
        t = tipos.get(n.get("tipo_empaque_id"))
        cantidad = int(n.get("cantidad") or 0)
        unidades *= max(cantidad, 0)
        largo, ancho, alto = (_medida(n, t, c) for c in ("largo", "ancho", "alto"))
        tara = _medida(n, t, "tara") or 0.0
        volumen = largo * ancho * alto / 1e6 if largo and ancho and alto else None
        tara_dentro = tara_dentro * cantidad + tara if i else tara
        neto = peso * unidades if peso is not None else None
        res.append({"orden": i + 1, "tipo_empaque_id": t.id if t else None, "nombre": t.nombre if t else None,
                    "cantidad": cantidad, "unidades": unidades, "volumen": round(volumen, 4) if volumen else None,
                    "tara": round(tara_dentro, 3), "neto": round(neto, 3) if neto is not None else None,
                    "bruto": round(neto + tara_dentro, 3) if neto is not None else None})
        if t is None:
            continue
        if i == 0 and t.max_unidades and cantidad > t.max_unidades:
            avisos.append(f"{t.nombre}: {cantidad} units; the type allows up to {t.max_unidades}.")
        if i > 0 and t.max_contenido and cantidad > t.max_contenido:
            avisos.append(f"{t.nombre}: {cantidad} inner units; the type allows up to {t.max_contenido}.")
        if t.peso_max and neto is not None and neto + tara_dentro > t.peso_max:
            avisos.append(f"{t.nombre}: {neto + tara_dentro:g} kg gross; the type allows up to {t.peso_max:g} kg.")
    return {"niveles": res, "avisos": avisos, "peso_articulo": peso}


def validar_niveles(db: Session, niveles) -> list[dict]:
    """Niveles limpios o 422: tipos activos, cada uno puede contener al de abajo,
    el primero lleva producto, cantidades enteras y solo los de arriba opcionales."""
    if not isinstance(niveles, list) or not niveles:
        raise ErrorNegocio("A recipe needs at least one level.", 422, "validacion")
    if len(niveles) > MAX_NIVELES:
        raise ErrorNegocio(f"Up to {MAX_NIVELES} levels per recipe.", 422, "validacion")
    ids = [n.get("tipo_empaque_id") if isinstance(n, dict) else None for n in niveles]
    tipos = {t.id: t for t in db.scalars(select(TipoEmpaque).where(TipoEmpaque.id.in_([i for i in ids if i]))
                                         .options(selectinload(TipoEmpaque.contiene)))}
    errores, limpio = [], []
    for i, n in enumerate(niveles):
        donde = f"niveles.{i}"
        if not isinstance(n, dict):
            errores.append({"campo": donde, "mensaje": "Each level needs a packaging type and a quantity."})
            continue
        t = tipos.get(n.get("tipo_empaque_id"))
        if t is None or not t.activo:
            errores.append({"campo": donde, "mensaje": "Choose an active packaging type."})
            continue
        try:
            cantidad = int(n.get("cantidad"))
        except (TypeError, ValueError):
            cantidad = 0
        if cantidad < 1 or cantidad > MAX_CANTIDAD or str(n.get("cantidad")).strip() not in (str(cantidad), f"{cantidad}.0"):
            errores.append({"campo": donde, "mensaje": f"Write a whole quantity between 1 and {MAX_CANTIDAD}."})
            continue
        if i == 0 and not t.contiene_productos:
            errores.append({"campo": donde, "mensaje": f"The first level holds the item: a {t.nombre} cannot hold products "
                                                       "(change it in Packaging types)."})
            continue
        if i > 0 and limpio and limpio[-1]["tipo_empaque_id"] not in {x.id for x in t.contiene}:
            abajo = tipos[limpio[-1]["tipo_empaque_id"]]
            errores.append({"campo": donde, "mensaje": f"A {t.nombre} cannot contain a {abajo.nombre} "
                                                       "(set “Can contain” in Packaging types)."})
            continue
        medidas = {}
        for c in ("largo", "ancho", "alto", "tara"):
            v = n.get(c)
            if v in (None, ""):
                medidas[c] = None
                continue
            try:
                medidas[c] = float(v)
            except (TypeError, ValueError):
                medidas[c] = -1
            if medidas[c] < 0:
                errores.append({"campo": f"{donde}.{c}", "mensaje": "Write a number of 0 or more."})
        limpio.append({"orden": i + 1, "tipo_empaque_id": t.id, "cantidad": cantidad, "opcional": bool(n.get("opcional")),
                       **medidas})
    if not errores:
        opcionales = [n["opcional"] for n in limpio]
        if any(opcionales) and opcionales != sorted(opcionales):  # False… True: solo los de arriba
            errores.append({"campo": "niveles", "mensaje": "Only the outermost levels can be optional (like the pallet)."})
        if all(opcionales):
            errores.append({"campo": "niveles", "mensaje": "At least the first level is required."})
    if errores:
        raise ErrorNegocio("Check the recipe levels.", 422, "validacion", errores)
    return limpio


# ---- Recetas: alta, cambios, lista ----------------------------------------------------------
def _cargar_receta(db: Session, receta_id: int) -> RecetaEmpaque:
    r = db.get(RecetaEmpaque, receta_id)
    if r is None:
        raise ErrorNegocio("The packing recipe does not exist.", 404, "no_encontrado")
    return r


def _usos(db: Session, ids: list[int]) -> dict[int, dict]:
    res = {i: {"reglas": 0, "posiciones_abiertas": 0, "posiciones": 0} for i in ids}
    if not ids:
        return res
    for rid, n in db.execute(select(ReglaEmpaque.receta_id, func.count()).where(
            ReglaEmpaque.receta_id.in_(ids), ReglaEmpaque.eliminada_en.is_(None)).group_by(ReglaEmpaque.receta_id)):
        res[rid]["reglas"] = n
    for rid, n in db.execute(select(PosicionOC.receta_id, func.count()).where(PosicionOC.receta_id.in_(ids))
                             .group_by(PosicionOC.receta_id)):
        res[rid]["posiciones"] = n
    for rid, n in db.execute(select(PosicionOC.receta_id, func.count()).join(OrdenCompra).where(
            PosicionOC.receta_id.in_(ids), OrdenCompra.estado.in_(ABIERTAS)).group_by(PosicionOC.receta_id)):
        res[rid]["posiciones_abiertas"] = n
    return res


def dict_receta(r: RecetaEmpaque, usos: dict | None = None) -> dict:
    f = foto(r)
    casepack, inner = derivar(f)
    return {"id": r.id, "codigo": r.codigo, "nombre": r.nombre, "descripcion": r.descripcion, "activa": r.activa,
            "automatica": r.automatica, "version": r.version, "niveles": f["niveles"], "resumen": resumen(f),
            "casepack": casepack, "inner_pack": inner, "usos": usos}


def listar_recetas(db: Session, user: Usuario, incluir_inactivas: bool = False) -> list[dict]:
    exigir_alguno(user, "catalogos.ver", "oc.editar", "oc.empaque")
    q = select(RecetaEmpaque).options(selectinload(RecetaEmpaque.niveles).selectinload(RecetaNivel.tipo_empaque))
    if not incluir_inactivas:
        q = q.where(RecetaEmpaque.activa.is_(True))
    recetas = list(db.scalars(q.order_by(RecetaEmpaque.nombre)))
    usos = _usos(db, [r.id for r in recetas])
    return [dict_receta(r, usos[r.id]) for r in recetas]


def detalle_receta(db: Session, user: Usuario, receta_id: int) -> dict:
    exigir_alguno(user, "catalogos.ver", "oc.editar", "oc.empaque")
    r = _cargar_receta(db, receta_id)
    return dict_receta(r, _usos(db, [r.id])[r.id])


def _poner_niveles(db: Session, r: RecetaEmpaque, niveles: list[dict]) -> None:
    r.niveles.clear()
    db.flush()  # libera (receta, orden) antes de volver a crearlos
    for n in niveles:
        r.niveles.append(RecetaNivel(**n))


def _datos_receta(datos: dict, r: RecetaEmpaque | None = None) -> tuple[str, str]:
    codigo = str(datos.get("codigo") if datos.get("codigo") is not None else (r.codigo if r else "")).strip().upper()
    nombre = str(datos.get("nombre") if datos.get("nombre") is not None else (r.nombre if r else "")).strip()
    if not CODIGO.match(codigo):
        raise ErrorNegocio("Write a code of up to 30 letters, digits, dot, dash or underscore.", 422, "validacion",
                           [{"campo": "codigo", "mensaje": "Invalid code."}])
    if not nombre or len(nombre) > 100:
        raise ErrorNegocio("Write a name of up to 100 characters.", 422, "validacion",
                           [{"campo": "nombre", "mensaje": "Required."}])
    return codigo, nombre


def crear_receta(db: Session, user: Usuario, datos: dict) -> dict:
    exigir(user, "catalogos.editar")
    codigo, nombre = _datos_receta(datos)
    if db.scalar(select(RecetaEmpaque.id).where(RecetaEmpaque.codigo == codigo)):
        raise ErrorNegocio(f"There is already a recipe {codigo}.", 409, "duplicado")
    niveles = validar_niveles(db, datos.get("niveles"))
    r = RecetaEmpaque(codigo=codigo, nombre=nombre, descripcion=(datos.get("descripcion") or None), activa=True)
    db.add(r)
    db.flush()
    _poner_niveles(db, r, niveles)
    db.flush()
    db.refresh(r)
    registrar(db, user, "receta_empaque", r.id, "crear", {"codigo": codigo, "resumen": resumen(foto(r))})
    return dict_receta(r, _usos(db, [r.id])[r.id])


def actualizar_receta(db: Session, user: Usuario, receta_id: int, datos: dict) -> dict:
    """Las posiciones que ya la usan conservan su foto: el cambio vale para lo nuevo."""
    exigir(user, "catalogos.editar")
    r = _cargar_receta(db, receta_id)
    verificar_version(r, datos.get("version"), "recipe")
    codigo, nombre = _datos_receta(datos, r)
    if codigo != r.codigo and db.scalar(select(RecetaEmpaque.id).where(RecetaEmpaque.codigo == codigo)):
        raise ErrorNegocio(f"There is already a recipe {codigo}.", 409, "duplicado")
    antes = resumen(foto(r))
    r.codigo, r.nombre = codigo, nombre
    if "descripcion" in datos:
        r.descripcion = datos.get("descripcion") or None
    if "activa" in datos:
        r.activa = bool(datos["activa"])
    if "niveles" in datos:
        _poner_niveles(db, r, validar_niveles(db, datos["niveles"]))
    r.automatica = False
    r.actualizada_en = ahora()
    r.version += 1
    db.flush()
    db.refresh(r)
    despues = resumen(foto(r))
    registrar(db, user, "receta_empaque", r.id, "editar",
              {"codigo": r.codigo, **({"antes": antes, "despues": despues} if antes != despues else {})})
    return dict_receta(r, _usos(db, [r.id])[r.id])


def eliminar_receta(db: Session, user: Usuario, receta_id: int) -> dict:
    """Una receta en uso no se borra: se desactiva."""
    exigir(user, "catalogos.editar")
    r = _cargar_receta(db, receta_id)
    usos = _usos(db, [r.id])[r.id]
    en_facturas = db.scalar(select(func.count()).select_from(FacturaLinea).where(FacturaLinea.receta_id == r.id))
    if usos["reglas"] or usos["posiciones"] or en_facturas:
        r.activa = False
        r.version += 1
        registrar(db, user, "receta_empaque", r.id, "desactivar", {"codigo": r.codigo})
        return {"ok": True, "desactivada": True}
    registrar(db, user, "receta_empaque", r.id, "eliminar", {"codigo": r.codigo})
    db.delete(r)
    return {"ok": True, "desactivada": False}


def receta_para_datos(db: Session, casepack: int | None, inner: int | None, crear: bool = True) -> RecetaEmpaque | None:
    """La receta con la forma de un casepack e inner pack (o una automática nueva):
    el bulto del catálogo que lleva producto y, si hay inner, el interior que va dentro."""
    if not casepack or casepack < 1:
        return None
    tipos = list(db.scalars(select(TipoEmpaque).where(TipoEmpaque.activo.is_(True)).order_by(TipoEmpaque.nivel, TipoEmpaque.codigo)
                            .options(selectinload(TipoEmpaque.contiene))))
    bulto = next((t for t in tipos if t.cuenta_como == "BULTO" and t.contiene_productos), None)
    if bulto is None:
        return None
    interior = None
    if inner and inner < casepack:
        if casepack % inner:
            return None
        interior = next((t for t in bulto.contiene if t.activo and t.contiene_productos and t.nivel < bulto.nivel), None)
        if interior is None:
            return None
    forma = [(interior.id, inner), (bulto.id, casepack // inner)] if interior else [(bulto.id, casepack)]
    for r in db.scalars(select(RecetaEmpaque).where(RecetaEmpaque.activa.is_(True))
                        .options(selectinload(RecetaEmpaque.niveles))):
        if [(n.tipo_empaque_id, n.cantidad) for n in r.niveles if not n.opcional] == forma:
            return r
    if not crear:
        return None
    codigo = f"CP{casepack}" + (f"-IN{inner}" if interior else "")
    r = db.scalar(select(RecetaEmpaque).where(RecetaEmpaque.codigo == codigo))
    if r is not None:  # el código existe con otra forma (la editaron): se usa otro
        codigo = f"{codigo}-{db.scalar(select(func.count()).select_from(RecetaEmpaque)) + 1}"
    r = RecetaEmpaque(codigo=codigo[:30], automatica=True, activa=True,
                      nombre=(f"{bulto.nombre} {casepack}" + (f" · {interior.nombre} {inner}" if interior else ""))[:100])
    db.add(r)
    db.flush()
    for i, (tid, n) in enumerate(forma, start=1):
        r.niveles.append(RecetaNivel(orden=i, tipo_empaque_id=tid, cantidad=n))
    db.flush()
    db.refresh(r)
    return r


def convertir_existentes(db: Session) -> int:
    """Receta (origen DATOS) para las posiciones de sólidos con casepack que aún no
    tienen, y la misma en sus líneas de factura con igual empaque. Devuelve cuántas posiciones."""
    n = 0
    for p in db.scalars(select(PosicionOC).where(PosicionOC.receta_id.is_(None), PosicionOC.casepack > 0,
                                                 PosicionOC.tipo_empaque != catalogo.TIPO_PACK)):
        r = receta_para_datos(db, p.casepack, p.inner_pack)
        if r is None:
            continue
        poner(p, r, "DATOS")
        n += 1
        for fl in db.scalars(select(FacturaLinea).where(FacturaLinea.posicion_oc_id == p.id, FacturaLinea.receta_id.is_(None),
                                                        FacturaLinea.casepack == p.casepack)):
            if fl.inner_pack == p.inner_pack:
                fl.receta_id, fl.receta_foto = p.receta_id, p.receta_foto
    return n


# ---- Reglas ---------------------------------------------------------------------------------
def _cargar_regla(db: Session, regla_id: int) -> ReglaEmpaque:
    r = db.get(ReglaEmpaque, regla_id)
    if r is None or r.eliminada_en is not None:
        raise ErrorNegocio("The packing rule does not exist.", 404, "no_encontrado")
    return r


def nombre_destino(db: Session, r: ReglaEmpaque) -> str:
    """A quién va la regla: la ruta de su familia, su producto, su artículo o toda la empresa."""
    if r.destino == "GRUPO" and (g := catalogo.nodo(db, r.grupo_id)) is not None:
        return " › ".join(g.ruta_nombres)
    if r.destino == "PRODUCTO" and (p := catalogo.producto(db, r.producto_id)) is not None:
        return p.nombre or p.codigo or str(r.producto_id)
    if r.destino == "ARTICULO" and (a := catalogo.articulo(db, r.articulo_id)) is not None:
        return a.codigo
    return "Whole company"


def texto_condiciones(condiciones: list[dict] | None, db: Session | None = None) -> str:
    """«Supplier = VANS · Brand ∈ TNF, VANS» para el historial (la pantalla arma la suya, traducida)."""
    nombres = nombres_campos(db) if db is not None else {c: e for c, e, _ in CAMPOS}
    ops = {"igual": "=", "distinto": "≠", "en": "∈", "no_en": "∉", "mayor": ">", "mayor_igual": "≥", "menor": "<", "menor_igual": "≤"}
    partes = []
    for c in condiciones or []:
        v = c.get("valor")
        v = ", ".join(map(str, v)) if isinstance(v, list) else ("" if v is None else str(v))
        partes.append(f"{nombres.get(c['campo'], c['campo'])} {ops.get(c['op'], c['op'])} {v}".strip())
    return " · ".join(partes)


def dict_regla(r: ReglaEmpaque) -> dict:
    db = object_session(r)
    return {"id": r.id, "receta_id": r.receta_id, "receta": r.receta.nombre if r.receta else None,
            "receta_resumen": resumen(foto(r.receta)) if r.receta else None, "destino": r.destino,
            "grupo_id": r.grupo_id, "producto_id": r.producto_id, "articulo_id": r.articulo_id,
            "destino_nombre": nombre_destino(db, r), "condiciones": r.condiciones or [],
            "condiciones_texto": texto_condiciones(r.condiciones, object_session(r)), "orden": r.orden,
            "vigente_desde": r.vigente_desde.isoformat() if r.vigente_desde else None,
            "vigente_hasta": r.vigente_hasta.isoformat() if r.vigente_hasta else None, "motivo": r.motivo,
            "activa": r.activa, "version": r.version}


def listar_reglas(db: Session, user: Usuario) -> list[dict]:
    exigir(user, "catalogos.ver")
    reglas = db.scalars(select(ReglaEmpaque).where(ReglaEmpaque.eliminada_en.is_(None))
                        .options(selectinload(ReglaEmpaque.receta).selectinload(RecetaEmpaque.niveles)
                                 .selectinload(RecetaNivel.tipo_empaque))
                        .order_by(ReglaEmpaque.orden, ReglaEmpaque.id))
    return [dict_regla(r) for r in reglas]


def catalogo_campos(db: Session, user: Usuario) -> dict:
    """Lo que el editor de reglas ofrece: datos de las condiciones, operadores,
    destinos y los grupos de producto (familias y categorías, con su ruta) a los
    que puede ir una regla."""
    exigir(user, "catalogos.ver")
    grupos = [g for g in catalogo.familias(db).values() if g.activa]
    return {"campos": [{"clave": c, "etiqueta": e, "tipo": t} for c, e, t in campos(db)],
            "operadores": list(cond.OPERADORES_SIMPLES), "destinos": list(DESTINOS),
            "grupos": sorted(({"id": g.id, "clase": "CATEGORIA" if g.es_categoria else "FAMILIA",
                               "nombre": " › ".join(g.ruta_nombres)} for g in grupos), key=lambda x: x["nombre"].lower())}


def _fecha(v, campo: str) -> date | None:
    if v in (None, ""):
        return None
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError as e:
        raise ErrorNegocio("Write a valid date.", 422, "validacion", [{"campo": campo, "mensaje": "Invalid date."}]) from e


def _limpiar_regla(db: Session, datos: dict, r: ReglaEmpaque | None = None) -> dict:
    """Los datos de una regla, limpios y validados (sin guardar)."""
    def v(k, defecto=None):
        return datos[k] if k in datos else (getattr(r, k) if r is not None else defecto)

    destino = str(v("destino", "EMPRESA") or "EMPRESA").upper()
    if destino not in DESTINOS:
        raise ErrorNegocio("Choose where the rule applies.", 422, "validacion", [{"campo": "destino", "mensaje": "Invalid."}])
    ids = {"grupo_id": None, "producto_id": None, "articulo_id": None}
    modelo = {"GRUPO": ("grupo_id", catalogo.nodo), "PRODUCTO": ("producto_id", catalogo.producto),
              "ARTICULO": ("articulo_id", catalogo.articulo)}.get(destino)
    if modelo:
        campo, buscar = modelo
        valor = v(campo)
        try:
            valor = int(valor)
        except (TypeError, ValueError):
            valor = None
        if not valor or buscar(db, valor) is None:
            raise ErrorNegocio("Choose who the rule is for.", 422, "validacion", [{"campo": campo, "mensaje": "Required."}])
        ids[campo] = valor
    try:
        receta_id = int(v("receta_id"))
    except (TypeError, ValueError):
        receta_id = 0
    receta = db.get(RecetaEmpaque, receta_id) if receta_id else None
    if receta is None or not receta.activa:
        raise ErrorNegocio("Choose an active recipe.", 422, "validacion", [{"campo": "receta_id", "mensaje": "Required."}])
    desde, hasta = _fecha(v("vigente_desde"), "vigente_desde"), _fecha(v("vigente_hasta"), "vigente_hasta")
    if desde and hasta and hasta < desde:
        raise ErrorNegocio("The end date cannot be before the start date.", 422, "validacion",
                           [{"campo": "vigente_hasta", "mensaje": "Before the start date."}])
    motivo = (str(v("motivo") or "").strip() or None)
    if motivo and len(motivo) > 300:
        raise ErrorNegocio("The reason can have up to 300 characters.", 422, "validacion")
    return {"destino": destino, **ids, "receta_id": receta.id, "condiciones": cond.limpiar(v("condiciones"), {c for c, _, _ in campos(db)}),
            "vigente_desde": desde, "vigente_hasta": hasta, "motivo": motivo, "activa": bool(v("activa", True))}


def crear_regla(db: Session, user: Usuario, datos: dict) -> dict:
    exigir(user, "catalogos.editar")
    limpio = _limpiar_regla(db, datos)
    orden = (db.scalar(select(func.max(ReglaEmpaque.orden)).where(ReglaEmpaque.eliminada_en.is_(None))) or 0) + 1
    r = ReglaEmpaque(**limpio, orden=orden, creada_por=user.id)
    db.add(r)
    db.flush()
    db.refresh(r)
    registrar(db, user, "regla_empaque", r.id, "crear", {"destino": nombre_destino(db, r), "receta": r.receta.nombre,
                                                         "condiciones": texto_condiciones(r.condiciones, db)})
    res = dict_regla(r)
    if datos.get("aplicar"):
        res["aplicadas"] = reaplicar(db, user)
    return res


def actualizar_regla(db: Session, user: Usuario, regla_id: int, datos: dict) -> dict:
    exigir(user, "catalogos.editar")
    r = _cargar_regla(db, regla_id)
    verificar_version(r, datos.get("version"), "rule")
    antes = dict_regla(r)
    for k, valor in _limpiar_regla(db, datos, r).items():
        setattr(r, k, valor)
    r.actualizada_por, r.actualizada_en = user.id, ahora()
    r.version += 1
    db.flush()
    db.refresh(r)
    despues = dict_regla(r)
    registrar(db, user, "regla_empaque", r.id, "editar",
              {k: {"antes": antes[k], "despues": despues[k]} for k in ("destino_nombre", "receta", "condiciones_texto",
                                                                         "vigente_desde", "vigente_hasta", "activa", "motivo")
               if antes[k] != despues[k]})
    if datos.get("aplicar"):
        despues["aplicadas"] = reaplicar(db, user)
    return despues


def eliminar_regla(db: Session, user: Usuario, regla_id: int, aplicar: bool = False) -> dict:
    """Baja lógica: las posiciones que ya la usaron conservan su receta y su foto."""
    exigir(user, "catalogos.editar")
    r = _cargar_regla(db, regla_id)
    r.eliminada_en, r.eliminada_por, r.activa = ahora(), user.id, False
    r.version += 1
    registrar(db, user, "regla_empaque", r.id, "eliminar", {"destino": nombre_destino(db, r), "receta": r.receta.nombre})
    res = {"ok": True}
    if aplicar:
        db.flush()
        res["aplicadas"] = reaplicar(db, user)
    return res


def ordenar_reglas(db: Session, user: Usuario, ids: list[int]) -> list[dict]:
    """El orden de la lista: solo decide entre reglas igual de específicas."""
    exigir(user, "catalogos.editar")
    reglas = {r.id: r for r in db.scalars(select(ReglaEmpaque).where(ReglaEmpaque.eliminada_en.is_(None)))}
    if not isinstance(ids, list) or set(ids) != set(reglas):
        raise ErrorNegocio("Send every rule once, in the new order.", 422, "validacion")
    for i, rid in enumerate(ids, start=1):
        if reglas[rid].orden != i:
            reglas[rid].orden = i
            reglas[rid].version += 1
    registrar(db, user, "regla_empaque", 0, "ordenar", {"orden": ids})
    return listar_reglas(db, user)


# ---- Motor ----------------------------------------------------------------------------------
@dataclass
class Eleccion:
    regla: ReglaEmpaque | None = None
    explicacion: list[dict] = field(default_factory=list)


class Motor:
    """Las reglas vigentes cargadas una vez para resolver muchas posiciones.
    `borrador`: una regla sin guardar (o editada) para medir su efecto."""

    def __init__(self, db: Session, hoy: date | None = None, borrador: ReglaEmpaque | None = None,
                 sin: int | None = None):
        from app.core.empresa import hoy as hoy_empresa

        self.db = db
        self.hoy = hoy or hoy_empresa()
        q = (select(ReglaEmpaque).join(RecetaEmpaque).where(ReglaEmpaque.eliminada_en.is_(None), ReglaEmpaque.activa.is_(True),
                                                            RecetaEmpaque.activa.is_(True))
             .options(selectinload(ReglaEmpaque.receta).selectinload(RecetaEmpaque.niveles).selectinload(RecetaNivel.tipo_empaque)))
        self.reglas = [r for r in db.scalars(q.order_by(ReglaEmpaque.orden, ReglaEmpaque.id))
                       if r.id != sin and (borrador is None or r.id != borrador.id)]
        if borrador is not None:
            self.reglas.append(borrador)
        self._paises: dict | None = None
        self._rutas: dict = {}
        self._cache: dict = {}
        self._fichas: dict[int, catalogo.FichaArticulo | None] = {}
        self._destinos: dict[int, str] = {}
        self.nombres = nombres_campos(db)

    def precargar(self, posiciones) -> None:
        """Las fichas de los artículos de muchas posiciones, en una consulta."""
        faltan = {p.articulo_id for p in posiciones if p.articulo_id and p.articulo_id not in self._fichas}
        if faltan:
            fichas = catalogo.articulos(self.db, faltan)
            self._fichas.update({i: fichas.get(i) for i in faltan})

    def ruta(self, a: catalogo.FichaArticulo) -> list[int]:
        """Los nodos del árbol del artículo, de lo más específico (su categoría) a lo más general."""
        if a.id not in self._rutas:
            self._rutas[a.id] = catalogo.ruta_reglas(self.db, a, self._cache)
        return self._rutas[a.id]

    def destino(self, r: ReglaEmpaque) -> str:
        clave = r.id or 0
        if clave not in self._destinos or not r.id:
            self._destinos[clave] = nombre_destino(self.db, r)
        return self._destinos[clave]

    def pais(self, centro: str | None) -> str | None:
        if self._paises is None:
            self._paises = dict(self.db.execute(select(Centro.codigo, Centro.pais)).all())
        return self._paises.get(centro) if centro else None

    def articulo(self, p: PosicionOC) -> catalogo.FichaArticulo | None:
        if not p.articulo_id:
            return None
        if p.articulo_id not in self._fichas:
            self._fichas[p.articulo_id] = catalogo.articulo(self.db, p.articulo_id)
        return self._fichas[p.articulo_id]

    def valores(self, p: PosicionOC, oc: OrdenCompra, a: catalogo.FichaArticulo | None) -> dict:
        prov = oc.proveedor if oc.proveedor is not None else (self.db.get(Proveedor, oc.proveedor_id) if oc.proveedor_id else None)
        return {"oc.proveedor": prov.codigo if prov else None, "oc.sociedad": oc.sociedad,
                "oc.centro": oc.centro, "oc.centro_destino": oc.centro_destino, "oc.pais_destino": self.pais(oc.centro_destino),
                "oc.pais_origen": p.pais_origen or oc.pais_origen, "oc.incoterm": oc.incoterm,
                "oc.puerto_despacho": oc.puerto_despacho, "linea.familia": a.familia.codigo if a and a.familia else None,
                **{f"linea.atributo.{k}": v for k, v in {**(p.atributos or {}), **(p.variante or {})}.items()},
                "linea.unidad": p.unidad, "linea.cantidad": p.cantidad, "linea.almacen": p.almacen,
                "linea.tipo": p.tipo_empaque, "articulo.sku": a.codigo if a else p.codigo_articulo}

    def _peso(self, r: ReglaEmpaque, a: catalogo.FichaArticulo | None) -> tuple[int, int] | None:
        """Qué tan específica es la regla para el artículo (None si no es para él)."""
        if r.destino == "EMPRESA":
            return (1, 0)
        if a is None:
            return None
        if r.destino == "ARTICULO":
            return (4, 0) if a.id == r.articulo_id else None
        if r.destino == "PRODUCTO":
            return (3, 0) if a.producto_id and a.producto_id == r.producto_id else None
        ruta = self.ruta(a)  # de lo más específico a lo más general: el más profundo pesa más
        return (2, len(ruta) - ruta.index(r.grupo_id)) if r.grupo_id in ruta else None

    def elegir(self, p: PosicionOC, oc: OrdenCompra) -> Eleccion:
        a = self.articulo(p)
        valores = self.valores(p, oc, a)
        res, mejor, clave_mejor = Eleccion(), None, None
        for r in self.reglas:
            peso = self._peso(r, a)
            if peso is None:
                continue
            vigente = (not r.vigente_desde or self.hoy >= r.vigente_desde) and (not r.vigente_hasta or self.hoy <= r.vigente_hasta)
            detalle = [{**d, "etiqueta": self.nombres.get(d["campo"], d["campo"])} for d in cond.detalle(r.condiciones, valores)]
            cumple = vigente and all(d["cumple"] for d in detalle)
            res.explicacion.append({"regla_id": r.id, "destino": self.destino(r), "receta": r.receta.nombre,
                                    "condiciones": detalle, "vigente": vigente, "cumple": cumple, "orden": r.orden})
            if not cumple:
                continue
            clave = (*peso, 1 if r.condiciones else 0, -r.orden, -(r.id or 0))
            if clave_mejor is None or clave > clave_mejor:
                mejor, clave_mejor = r, clave
        res.regla = mejor
        for e in res.explicacion:
            e["gana"] = mejor is not None and e["regla_id"] == mejor.id
        return res


# ---- Posiciones ------------------------------------------------------------------------------
def poner(p: PosicionOC, receta: RecetaEmpaque | None, origen: str | None, regla: ReglaEmpaque | None = None) -> None:
    """Fija la receta de una posición con su foto y, en los sólidos, su casepack e inner pack."""
    if receta is None:
        p.receta_id = p.receta_origen = p.receta_regla_id = p.receta_foto = None
        return
    f = foto(receta)
    p.receta_id, p.receta_origen, p.receta_regla_id, p.receta_foto = receta.id, origen, regla.id if regla else None, f
    if p.tipo_empaque != catalogo.TIPO_PACK:
        p.casepack, p.inner_pack = derivar(f)


def asignar(db: Session, p: PosicionOC, oc: OrdenCompra, motor: Motor | None = None, trae_empaque: bool = False) -> None:
    """Receta de una posición que llega o cambia (archivo, formulario, asistente):
    la elegida a mano se queda; si la OC trae casepack, la receta con esa forma;
    si no, la regla que aplica."""
    if p.receta_origen in ("MANUAL", "DATOS") and p.receta_foto:
        # Sin casepack en lo que llega se conserva la receta (y el casepack sale de ella);
        # si la OC trae otra forma, manda la OC
        if not trae_empaque or p.tipo_empaque == catalogo.TIPO_PACK:
            if p.tipo_empaque != catalogo.TIPO_PACK:
                p.casepack, p.inner_pack = derivar(p.receta_foto)
            return
        if derivar(p.receta_foto) == (p.casepack, p.inner_pack):
            return
    if trae_empaque and p.tipo_empaque != catalogo.TIPO_PACK:
        r = receta_para_datos(db, p.casepack, p.inner_pack)
        if r is not None:
            if p.receta_id != r.id or p.receta_origen != "DATOS":
                poner(p, r, "DATOS")
            return
        poner(p, None, None)
        return
    e = (motor or Motor(db)).elegir(p, oc)
    if e.regla is not None:
        if p.receta_regla_id != e.regla.id or p.receta_id != e.regla.receta_id:
            poner(p, e.regla.receta, "REGLA", e.regla)
    elif p.receta_origen == "REGLA":
        poner(p, None, None)


def _facturada(db: Session, p: PosicionOC) -> bool:
    return bool(db.scalar(select(func.count()).select_from(FacturaLinea).where(FacturaLinea.posicion_oc_id == p.id)))


def _orden(db: Session, user: Usuario, oc_id: int) -> OrdenCompra:
    oc = db.get(OrdenCompra, oc_id)
    if oc is None:
        raise ErrorNegocio("The purchase order does not exist.", 404, "no_encontrado")
    asegurar_proveedor(user, oc.proveedor_id, oc.sociedad)
    return oc


def elegir_en_posicion(db: Session, user: Usuario, oc_id: int, posicion_id: int, receta_id: int | None) -> dict:
    """Receta elegida a mano en una posición (o, sin receta, la que digan las reglas).
    Una posición ya facturada no cambia: la factura conserva la suya."""
    exigir(user, "oc.empaque")
    p = db.get(PosicionOC, posicion_id)
    if p is None or p.oc_id != oc_id:
        raise ErrorNegocio("The purchase order line does not exist.", 404, "no_encontrado")
    oc = _orden(db, user, p.oc_id)
    if oc.estado not in ABIERTAS:
        raise ErrorNegocio("The PO is closed or cancelled: its packing no longer changes.", 409, "estado")
    if _facturada(db, p):
        raise ErrorNegocio("The line is already invoiced: the invoice keeps its recipe.", 409, "facturada")
    antes = p.receta_foto and p.receta_foto.get("nombre")
    if receta_id:
        r = db.get(RecetaEmpaque, int(receta_id))
        if r is None or not r.activa:
            raise ErrorNegocio("Choose an active recipe.", 422, "validacion")
        poner(p, r, "MANUAL")
    else:
        poner(p, None, None)
        asignar(db, p, oc)
    oc.actualizado_en = ahora()
    registrar(db, user, "orden", oc.id, "receta_empaque",
              {"posicion": p.posicion, "antes": antes, "despues": p.receta_foto and p.receta_foto.get("nombre"),
               "origen": p.receta_origen})
    return dict_posicion(p)


def dict_posicion(p: PosicionOC) -> dict:
    """Lo que la pantalla de la OC muestra de la receta de una posición."""
    f = p.receta_foto
    if not f:
        return {"posicion_id": p.id, "receta_id": None, "receta": None, "origen": None, "aviso": None}
    unidades = derivar(f)[0] if p.tipo_empaque != catalogo.TIPO_PACK else None
    aviso = None
    if unidades and p.cantidad and float(p.cantidad) % unidades:
        aviso = f"{float(p.cantidad):g} is not a multiple of {unidades}."
    return {"posicion_id": p.id, "receta_id": p.receta_id, "receta": f.get("nombre"), "resumen": resumen(f),
            "origen": p.receta_origen, "regla_id": p.receta_regla_id, "niveles": f.get("niveles"), "aviso": aviso}


def reaplicar(db: Session, user: Usuario, oc_id: int | None = None) -> int:
    """Vuelve a aplicar las reglas a las posiciones abiertas sin facturar que no
    tienen una receta elegida a mano ni del casepack de la OC. Devuelve cuántas cambiaron."""
    exigir_alguno(user, "catalogos.editar", "oc.editar")
    motor = Motor(db)
    q = (select(PosicionOC).join(OrdenCompra).where(OrdenCompra.estado.in_(ABIERTAS),
                                                   (PosicionOC.receta_origen.is_(None)) | (PosicionOC.receta_origen == "REGLA"),
                                                   ~select(FacturaLinea.id).where(FacturaLinea.posicion_oc_id == PosicionOC.id).exists())
         .options(selectinload(PosicionOC.oc).selectinload(OrdenCompra.proveedor)))
    if oc_id:
        q = q.where(PosicionOC.oc_id == oc_id)
    cambios = 0
    posiciones = list(db.scalars(q.limit(MAX_PROBAR)))
    motor.precargar(posiciones)
    for p in posiciones:
        antes = (p.receta_id, p.receta_regla_id)
        asignar(db, p, p.oc, motor)
        if (p.receta_id, p.receta_regla_id) != antes:
            cambios += 1
    if cambios:
        registrar(db, user, "regla_empaque", 0, "reaplicar", {"posiciones": cambios, "oc_id": oc_id})
    return cambios


# ---- Probar e impacto -----------------------------------------------------------------------
def probar(db: Session, user: Usuario, oc_id: int, borrador: dict | None = None) -> dict:
    """Qué receta lleva cada posición de una OC hoy y cuál le darían las reglas
    (con la regla en edición, si viene), con la explicación regla por regla."""
    exigir(user, "catalogos.ver")
    oc = _orden(db, user, oc_id)
    motor = _motor_con(db, borrador)
    filas = []
    motor.precargar(oc.posiciones)
    for p in sorted(oc.posiciones, key=lambda x: x.posicion.zfill(10)):
        e = motor.elegir(p, oc)
        filas.append({"posicion_id": p.id, "posicion": p.posicion, "articulo": p.codigo_articulo, "cantidad": p.cantidad,
                      "actual": dict_posicion(p),
                      "reglas": {"receta": e.regla.receta.nombre if e.regla else None,
                                 "resumen": resumen(foto(e.regla.receta)) if e.regla else None,
                                 "regla_id": e.regla.id if e.regla else None,
                                 "destino": motor.destino(e.regla) if e.regla else None},
                      "explicacion": e.explicacion})
    return {"oc_id": oc.id, "numero": oc.numero, "posiciones": filas}


def _motor_con(db: Session, borrador: dict | None) -> Motor:
    if not borrador:
        return Motor(db)
    rid = borrador.get("id")
    original = _cargar_regla(db, int(rid)) if rid else None
    limpio = _limpiar_regla(db, borrador, original)
    r = ReglaEmpaque(**limpio, orden=original.orden if original else 10**6)
    r.id = original.id if original else None
    r.receta = db.get(RecetaEmpaque, limpio["receta_id"])
    if r in db:  # solo se mide: nunca se guarda
        db.expunge(r)
    return Motor(db, borrador=r)


def impacto(db: Session, user: Usuario, borrador: dict | None = None, quitar: int | None = None) -> dict:
    """Cuántas posiciones abiertas sin facturar (que siguen a las reglas) cambiarían
    de receta si se guarda la regla (o si se da de baja `quitar`), con ejemplos."""
    exigir(user, "catalogos.ver")
    actual = Motor(db)
    nuevo = Motor(db, sin=quitar) if quitar else _motor_con(db, borrador)
    q = (select(PosicionOC).join(OrdenCompra).where(OrdenCompra.estado.in_(ABIERTAS),
                                                   (PosicionOC.receta_origen.is_(None)) | (PosicionOC.receta_origen == "REGLA"),
                                                   ~select(FacturaLinea.id).where(FacturaLinea.posicion_oc_id == PosicionOC.id).exists())
         .options(selectinload(PosicionOC.oc).selectinload(OrdenCompra.proveedor)))
    posiciones = list(db.scalars(q.limit(MAX_PROBAR + 1)))
    actual.precargar(posiciones[:MAX_PROBAR])
    nuevo.precargar(posiciones[:MAX_PROBAR])
    cambian, ejemplos = 0, []
    for p in posiciones[:MAX_PROBAR]:
        a, b = actual.elegir(p, p.oc).regla, nuevo.elegir(p, p.oc).regla
        ra, rb = (a.receta_id if a else None), (b.receta_id if b else None)
        if ra != rb:
            cambian += 1
            if len(ejemplos) < 10:
                ejemplos.append({"oc": p.oc.numero, "posicion": p.posicion, "articulo": p.codigo_articulo,
                                 "antes": a.receta.nombre if a else None, "despues": b.receta.nombre if b else None})
    return {"revisadas": min(len(posiciones), MAX_PROBAR), "truncado": len(posiciones) > MAX_PROBAR, "cambian": cambian,
            "ejemplos": ejemplos}
