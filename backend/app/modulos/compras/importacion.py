"""Importación y alta de OCs: vista previa de un archivo, aplicarla (crea o
actualiza OCs y posiciones), el alta desde el formulario, la plantilla para
llenar y las opciones del formulario.
"""
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import empresa, listas
from app.core.empresa import regla, tope_filas
from app.core.errores import ErrorNegocio
from app.core.estados import OC
from app.modelos import (
    Alerta,
    Almacen,
    Centro,
    ImportacionOC,
    OrdenCompra,
    Pais,
    PosicionOC,
    Proveedor,
    Puerto,
    Sociedad,
    Usuario,
    ahora,
)
from app.modulos.acceso.permisos import (
    exigir,
    exigir_alguno,
    proveedores_de,
    un_proveedor,
)
from app.modulos.catalogo import servicio as catalogo
from app.modulos.comex import servicio as comex
from app.modulos.compras import liberaciones, perfiles
from app.modulos.compras.lectura_oc import (
    ALIAS,
    CAMPOS_CABECERA,
    CAMPOS_POSICION,
    REQUERIDOS,
    Maestros,
    _leer_archivo,
    _normalizar,
)
from app.modulos.comun.historial import registrar
from app.modulos.comun.normalizar import celda
from app.modulos.empaque import recetas
from app.modulos.facturacion.cantidades import facturado_por_posicion


def _valores_posicion(d: dict) -> dict:
    v = {c: d.get(c) for c in CAMPOS_POSICION}
    v["pais_origen"] = d.get("pais_origen_pos") or d.get("pais_origen")
    return v


def _clasificar(db: Session, filas: list[dict], propia: int | None = None) -> list[dict]:
    """Clasifica cada fila (nuevo, cambio, sin cambio, conflicto, error).
    `propia`: la OC que el asistente está enviando (su borrador sí se aplica)."""
    m = Maestros(db)
    vistos: set = set()
    cabeceras: dict = {}
    resultado = []
    normalizadas = [(r, *_normalizar(r, m)) for r in filas]

    claves_oc = {(d["proveedor"], d["oc"]) for _, d, _ in normalizadas}
    ocs_existentes = {}
    for codigo, numero in claves_oc:
        prov = m.proveedores.get(codigo)
        if prov:
            oc = db.scalar(select(OrdenCompra).where(OrdenCompra.proveedor_id == prov.id, OrdenCompra.numero == numero))
            if oc:
                ocs_existentes[(codigo, numero)] = oc
    ids_pos = [p.id for oc in ocs_existentes.values() for p in oc.posiciones]
    facturado = facturado_por_posicion(db, ids_pos)

    for registro, d, errores in normalizadas:
        clave = f"{d['proveedor']} / PO {d['oc']} / line {d['posicion']}"
        salida = {"fila": registro.get("_fila"), "clave": clave, "datos": registro,
                  "mensajes": list(errores), "cambios": {}}
        if d["proveedor"] and d["proveedor"] not in m.proveedores:
            salida["mensajes"].append(f"Supplier {d['proveedor']} does not exist.")
        k = (d["proveedor"], d["oc"], d["posicion"])
        if k in vistos:
            salida["mensajes"].append("Line repeated within the file.")
        vistos.add(k)
        cab = {c: d.get(c) for c in CAMPOS_CABECERA} | {"extra": d.get("extra") or {}}
        previa = cabeceras.setdefault((d["proveedor"], d["oc"]), cab)
        if previa != cab:
            salida["mensajes"].append("The header data does not match other rows of the same PO.")
        if salida["mensajes"]:
            salida["estado"] = "error"
            resultado.append(salida)
            continue

        oc = ocs_existentes.get((d["proveedor"], d["oc"]))
        if oc and oc.id != propia and not OC.puede("importar", oc.estado):
            salida["estado"] = "conflicto"
            salida["mensajes"].append(f"The PO is {OC.texto(oc.estado)} in the platform: a file cannot change it.")
            resultado.append(salida)
            continue
        pos = next((p for p in oc.posiciones if p.posicion == d["posicion"]), None) if oc else None
        if not pos:
            salida["estado"] = "nuevo"
            resultado.append(salida)
            continue

        cambios = {}
        for c in CAMPOS_CABECERA:
            anterior = getattr(oc, c)
            if anterior != d.get(c):
                cambios[c] = {"antes": anterior, "despues": d.get(c)}
        for k, v in (d.get("extra") or {}).items():
            if (oc.extra or {}).get(k) != v:
                cambios[f"extra.{k}"] = {"antes": (oc.extra or {}).get(k), "despues": v}
        for c, nuevo in _valores_posicion(d).items():
            if c == "articulo_id":
                continue
            anterior = getattr(pos, c)
            igual = abs(anterior - nuevo) < 1e-9 if isinstance(anterior, float) and nuevo is not None else anterior == nuevo
            if not igual:
                cambios[c] = {"antes": anterior, "despues": nuevo}
        salida["cambios"] = cambios
        fact = facturado.get(pos.id, 0)
        if not cambios:
            salida["estado"] = "sin_cambio"
        elif fact and d["cantidad"] is not None and d["cantidad"] < fact:
            salida["estado"] = "conflicto"
            salida["mensajes"].append(f"The new quantity ({d['cantidad']}) is less than what is already invoiced ({fact}).")
        elif fact and any(c in cambios for c in ("sociedad", "moneda", "centro", "unidad", "codigo_articulo")):
            salida["estado"] = "conflicto"
            salida["mensajes"].append(
                "Key data (company, currency, plant, SKU or unit) changes on an already invoiced line.")
        elif fact and any(c in cambios for c in ("casepack", "inner_pack")):
            salida["estado"] = "conflicto"
            salida["mensajes"].append("The casepack or inner pack changes on a line that is already invoiced.")
        else:
            salida["estado"] = "cambio"
        resultado.append(salida)
    return resultado


def _resumen(clasificadas: list[dict]) -> dict:
    res = {"nuevo": 0, "cambio": 0, "sin_cambio": 0, "conflicto": 0, "error": 0}
    for c in clasificadas:
        res[c["estado"]] += 1
    res["total"] = len(clasificadas)
    return res


def importar_previa(db: Session, user: Usuario, nombre: str, contenido: bytes, perfil_id: int | None = None) -> dict:
    exigir(user, "oc.importar")
    filas = _leer_archivo(nombre, contenido, perfiles.elegido(db, perfil_id))
    if not filas:
        raise ErrorNegocio("The file has no rows with data.", 422, "archivo_vacio")
    tope_filas(len(filas))
    clasificadas = _clasificar(db, filas)
    imp = ImportacionOC(usuario_id=user.id, nombre_archivo=nombre, filas=filas)
    db.add(imp)
    db.flush()
    return {
        "importacion_id": imp.id,
        "archivo": nombre,
        "resumen": _resumen(clasificadas),
        "filas": [{k: v for k, v in c.items() if k != "datos"} for c in clasificadas],
    }


def importar_aplicar(db: Session, user: Usuario, importacion_id: int) -> dict:
    exigir(user, "oc.importar")
    imp = db.get(ImportacionOC, importacion_id)
    if not imp:
        raise ErrorNegocio("The import does not exist.", 404, "no_encontrado")
    return aplicar_importacion(db, user, imp)


def aplicar_importacion(db: Session, user: Usuario, imp: ImportacionOC, propia: int | None = None,
                        formulario: bool = False) -> dict:
    """Aplica las filas de una carga (archivo, formulario o asistente). Las OCs
    nuevas entran aprobadas (vienen del ERP) salvo que la empresa pida aprobarlas
    también aquí; cada OC creada o cambiada deja sus cambios en su historial."""
    from app.modulos.compras import flujo_oc

    if imp.estado == "APLICADA":
        return {"ya_aplicada": True, **(imp.resultado or {})}
    # Se vuelve a clasificar: los datos pudieron cambiar desde la vista previa
    clasificadas = _clasificar(db, imp.filas, propia)
    m = Maestros(db)
    aplicadas = 0
    motor = None  # reglas de empaque, cargadas una vez
    ocs_tocadas: dict[int, dict] = {}
    for c in clasificadas:
        if c["estado"] == "conflicto":
            d, _ = _normalizar(c["datos"], m)
            prov = m.proveedores.get(d["proveedor"])
            db.add(Alerta(proveedor_id=prov.id if prov else None, tipo="conflicto_oc",
                          mensaje=f"{c['clave']}: " + " ".join(c["mensajes"]),
                          referencia={"importacion_id": imp.id, "fila": c["fila"]}))
        if c["estado"] not in ("nuevo", "cambio"):
            continue
        d, _ = _normalizar(c["datos"], m)
        prov = m.proveedores[d["proveedor"]]
        oc = db.scalar(select(OrdenCompra).where(OrdenCompra.proveedor_id == prov.id, OrdenCompra.numero == d["oc"]))
        nueva = oc is None
        if nueva:
            # Sin liberación logística hasta decidirla al final (abajo)
            oc = OrdenCompra(proveedor_id=prov.id, numero=d["oc"], liberacion_logistica=m.lib.logistica.sin_liberar() or "",
                             estado="APROBADA", origen="ERP", creada_por=user.id if user else None)
            db.add(oc)
        info = ocs_tocadas.setdefault(id(oc), {
            "oc": oc, "cambios": False, "explicita": d["liberacion_logistica_archivo"],
            "actual": None if nueva else oc.liberacion_logistica, "nueva": nueva, "lineas": 0, "detalle": {}})
        info["cambios"] = info["cambios"] or (c["estado"] == "cambio")
        info["lineas"] += 1
        for campo, cambio in (c.get("cambios") or {}).items():
            info["detalle"].setdefault(f"{d['posicion']}.{campo}" if campo in CAMPOS_POSICION + ["cantidad", "precio", "unidad"]
                                       else campo, cambio)
        for campo in CAMPOS_CABECERA:
            setattr(oc, campo, d.get(campo))
        if d.get("extra"):
            oc.extra = {**(oc.extra or {}), **d["extra"]}
        # Fechas de liberación: las del archivo si vienen; si no, el día en que se liberó
        for campo in ("fecha_lib_comercial", "fecha_lib_logistica"):
            if d.get(campo):
                setattr(oc, campo, d[campo])
        oc.actualizado_en = ahora()
        db.flush()
        pos = db.scalar(select(PosicionOC).where(PosicionOC.oc_id == oc.id, PosicionOC.posicion == d["posicion"]))
        if not pos:
            pos = PosicionOC(oc_id=oc.id, posicion=d["posicion"])
            db.add(pos)
        for campo, valor in _valores_posicion(d).items():
            setattr(pos, campo, valor)
        motor = motor or recetas.Motor(db)
        recetas.asignar(db, pos, oc, motor, trae_empaque=d.get("casepack") is not None)
        aplicadas += 1
    for info in ocs_tocadas.values():
        oc = info["oc"]
        oc.liberacion_logistica = m.lib.logistica_final(oc.liberacion_comercial, info["explicita"], info["actual"],
                                                        info["cambios"])
        oc.liberada = m.lib.liberada(oc.liberacion_comercial, oc.liberacion_logistica)
        m.lib.fechar(oc)
        if oc.id == propia or formulario:
            continue  # el asistente o el formulario deciden su estado y su historial
        db.flush()
        if info["nueva"] and regla("APROBAR_OC_IMPORTADAS"):
            flujo_oc.iniciar_aprobacion(db, user, oc)
        detalle = {"archivo": imp.nombre_archivo, "lineas": info["lineas"]}
        if not info["nueva"] and info["detalle"]:
            detalle["cambios"] = dict(list(info["detalle"].items())[:60])
        registrar(db, user, "orden", oc.id, "importada" if info["nueva"] else "actualizada", detalle)
    # Las OCs creadas o cambiadas: la capa de integración guarda su referencia externa
    ocs = [{"id": i["oc"].id, "numero": i["oc"].numero, "proveedor": i["oc"].proveedor.codigo, "nueva": i["nueva"]}
           for i in ocs_tocadas.values() if i["oc"].id is not None]
    resultado = {"resumen": _resumen(clasificadas), "aplicadas": aplicadas, "ocs": ocs}
    imp.estado = "APLICADA"
    imp.resultado = resultado
    registrar(db, user, "importacion_oc", imp.id, "aplicar", resultado)
    return resultado


# ---- Alta desde el formulario ------------------------------------------------------
# El formulario arma las mismas filas que un archivo de carga: una por línea con
# los datos de la cabecera; se validan y se guardan con el mismo proceso.
CAMPOS_FORM_CAB = ("proveedor", "oc", "sociedad", "centro", "centro_destino", "moneda", "incoterm", "fecha_oc",
                   "puerto_despacho", "pais_origen", "pais_procedencia", "fecha_xf", "fecha_tienda",
                   "liberacion_comercial", "liberacion_logistica")
CAMPOS_FORM_LINEA = ("posicion", "codigo_articulo", "cantidad", "precio", "unidad", "casepack", "inner_pack", "almacen",
                     "fecha_entrega")


def crear_oc(db: Session, user: Usuario, datos: dict) -> dict:
    """Orden de compra creada en la plataforma de una sola vez (sin borrador):
    misma estructura y mismas validaciones que la carga masiva, y pasa por las
    reglas de aprobación como la del asistente."""
    from app.modulos.compras import flujo_oc

    exigir(user, "oc.editar")
    cab = {k: celda(v) for k, v in (datos.get("cabecera") or {}).items() if k in CAMPOS_FORM_CAB}
    permitidos = proveedores_de(user)
    if permitidos is not None:  # solo OCs de los proveedores de su alcance
        prov = db.scalar(select(Proveedor).where(Proveedor.codigo == str(cab.get("proveedor") or "").upper()))
        if not prov or prov.id not in permitidos:
            unico = un_proveedor(permitidos)
            prov = db.get(Proveedor, unico) if unico else None
        cab["proveedor"] = prov.codigo if prov else ""
    lineas = [x for x in (datos.get("lineas") or []) if any(celda(v) for v in x.values())]
    if not lineas:
        raise ErrorNegocio("Add at least one line.", 422, "validacion", [{"campo": "lineas", "mensaje": "Add at least one line."}])
    filas = []
    for i, linea in enumerate(lineas, start=1):
        fila = {**cab, **{k: celda(v) for k, v in linea.items() if k in CAMPOS_FORM_LINEA}, "_fila": i}
        fila["posicion"] = fila.get("posicion") or str(i * 10)
        filas.append(fila)
    m = Maestros(db)
    prov = m.proveedores.get((cab.get("proveedor") or "").upper())
    if prov and cab.get("oc") and db.scalar(select(OrdenCompra.id).where(
            OrdenCompra.proveedor_id == prov.id, OrdenCompra.numero == cab["oc"])):
        raise ErrorNegocio(f"PO {cab['oc']} already exists for this supplier.", 409, "duplicado",
                           [{"campo": "oc", "mensaje": f"PO {cab['oc']} already exists for this supplier."}])
    clasificadas = _clasificar(db, filas)
    malas = [c for c in clasificadas if c["estado"] in ("error", "conflicto")]
    if malas:
        # Lo que falla en todas las líneas es de la cabecera; lo demás, de su línea
        comunes = set.intersection(*(set(c["mensajes"]) for c in clasificadas)) if len(malas) == len(clasificadas) else set()
        errores = [{"campo": "cabecera", "mensaje": x} for x in sorted(comunes)]
        for c in malas:
            errores += [{"campo": f"lineas.{c['fila'] - 1}", "mensaje": f"Line {c['fila']}: {x}"}
                        for x in c["mensajes"] if x not in comunes]
        raise ErrorNegocio("Check the purchase order.", 422, "validacion", errores)
    imp = ImportacionOC(usuario_id=user.id, nombre_archivo="(form)", filas=filas)
    db.add(imp)
    db.flush()
    resultado = aplicar_importacion(db, user, imp, formulario=True)
    oc = db.scalar(select(OrdenCompra).where(OrdenCompra.proveedor_id == m.proveedores[cab["proveedor"].upper()].id,
                                             OrdenCompra.numero == cab["oc"]))
    oc.origen = "PLATAFORMA"
    flujo_oc.iniciar_aprobacion(db, user, oc)
    registrar(db, user, "orden", oc.id, "enviada", {"numero": oc.numero, "lineas": resultado["aplicadas"], "origen": "formulario",
                                                     "estado": oc.estado})
    return {"oc_id": oc.id, "numero": oc.numero, "lineas": resultado["aplicadas"]}


def moneda_base() -> str | None:
    """Moneda de la empresa (Configuración → Empresa) o la primera de la lista."""
    from app.core.empresa import configuracion_actual

    return (configuracion_actual().get("preferencias") or {}).get("moneda") or next(iter(listas.codigos("moneda")), None)


def plantilla_oc(db: Session, user: Usuario) -> bytes:
    """Plantilla de carga de OC en Excel, con las fechas de ejemplo en el
    formato del usuario (el mismo con el que se leerán)."""
    from datetime import timedelta

    from app.modulos.acceso.preferencias import actual, fecha_txt
    from app.modulos.documentos.plantillas import plantilla

    hoy = date.today()
    fechas = {"fecha_oc": hoy, "fecha_xf_original": hoy + timedelta(days=45), "fecha_xf": hoy + timedelta(days=50),
              "fecha_tienda": hoy + timedelta(days=100), "fecha_lib_comercial": None, "fecha_lib_logistica": None,
              "fecha_entrega": None}
    ayudas = {"proveedor": "Supplier code.", "oc": "PO number (letters and numbers, up to 40).", "posicion": "Line number.",
              "codigo_articulo": "Item code from the item master.", "cantidad": "Quantity in the item unit.",
              "sociedad": "Company (bill to). Optional; needed to invoice.", "moneda": "Needed if there is a price.",
              "precio": "Optional; needed to invoice.", "casepack": "Solids: exact quantity per carton (optional).",
              "inner_pack": "Usually defined later in the packing list.",
              "liberacion_comercial": "",
              "liberacion_logistica": ""}
    # Códigos de liberación de la empresa (Datos maestros → Estados de liberación)
    lib = liberaciones.de(db)
    ayudas["liberacion_comercial"] = f"{lib.comercial.ayuda()} (or the words)."
    ayudas["liberacion_logistica"] = f"{lib.logistica.ayuda()} (or the words)."
    formato = actual()["formato_fecha"]
    columnas = []
    for campo, alias in ALIAS.items():
        ayuda = ayudas.get(campo, "")
        if campo.startswith("fecha"):
            ayuda = (ayuda + " " if ayuda else "") + f"Date as {formato} (your profile setting) or YYYY-MM-DD."
        columnas.append({"nombre": alias[0], "req": campo in REQUERIDOS, "ayuda": ayuda})
    base = {"proveedor": "SUPPLIER", "oc": "PO-0001", "sociedad": "",
            "moneda": moneda_base() or "", "incoterm": next(iter(listas.codigos("incoterm")), ""),
            "liberacion_comercial": lib.comercial.predeterminado() or "",
            "liberacion_logistica": next((x.codigo for x in lib.logistica.lista if x.libera and not x.con_cambios), ""), "unidad": "", "precio": 10.5, "casepack": 12}
    ejemplos = []
    for linea, cant in ((10, 48), (20, 36)):
        fila = {**base, "posicion": linea, "codigo_articulo": "ITEM-CODE", "cantidad": cant,
                **{k: fecha_txt(v) for k, v in fechas.items() if v}}
        ejemplos.append([fila.get(c, "") for c in ALIAS])
    return plantilla("Purchase orders", columnas, ejemplos, [
        "One row per PO line; the header data (supplier, PO, company…) is repeated on each line.",
        "Columns with * are required. Company, currency and price can be completed later; they are needed to invoice.",
        f"Dates: {formato} — the format chosen in your profile — or YYYY-MM-DD. Excel date cells are also read.",
    ])


def opciones_formulario(db: Session, user: Usuario) -> dict:
    """Listas para el formulario y el asistente de OC (códigos, como en el archivo de carga)."""
    exigir_alguno(user, "oc.editar", "oc.importar")
    provs = db.scalars(select(Proveedor).where(Proveedor.activo.is_(True),
                                               *([Proveedor.id.in_(proveedores_de(user))] if proveedores_de(user) is not None else []))
                       .order_by(Proveedor.nombre)).all()
    op = lambda xs, f=lambda x: x.nombre: [{"valor": x.codigo, "texto": f"{x.codigo} · {f(x)}"} for x in xs]  # noqa: E731
    # Las monedas de la lista y las que ya traen las OCs (de antes de la lista)
    usadas = {m for (m,) in db.execute(select(OrdenCompra.moneda).distinct()) if m}
    monedas = listas.codigos("moneda") + sorted(usadas - set(listas.codigos("moneda")))
    return {
        # Cada proveedor lleva sus sociedades: el formulario solo ofrece esas
        "proveedores": [{**o, "sociedades": [x.codigo for x in p.sociedades]} for o, p in zip(op(provs), provs, strict=False)],
        "sociedades": op(db.scalars(select(Sociedad).order_by(Sociedad.codigo))),
        "centros": [{"valor": c.codigo, "texto": f"{c.codigo} · {c.nombre}", "sociedad": c.sociedad.codigo if c.sociedad else None}
                    for c in db.scalars(select(Centro).order_by(Centro.codigo))],
        "almacenes": [{"valor": a.codigo, "texto": f"{a.codigo} · {a.nombre}", "sociedad": a.sociedad.codigo if a.sociedad else None}
                      for a in db.scalars(select(Almacen).order_by(Almacen.codigo))],
        "puertos": op(db.scalars(select(Puerto).order_by(Puerto.codigo))),
        "paises": op(db.scalars(select(Pais).order_by(Pais.nombre))),
        "monedas": [{"valor": m, "texto": f"{m} · {listas.nombre('moneda', m)}" if listas.valor("moneda", m) else m}
                    for m in monedas],
        "incoterms": [{"valor": x["codigo"], "texto": f"{x['codigo']} · {x['nombre']}"} for x in listas.valores("incoterm")],
        "condiciones_pago": [{"valor": x["codigo"], "texto": x["nombre"]} for x in listas.valores("condicion_pago")],
        "unidades": [{"valor": x["codigo"], "texto": x["nombre"]} for x in listas.valores("unidad")],
        "moneda_base": moneda_base(),
        "obligatorios": sorted((empresa.configuracion_actual().get("obligatorios") or {}).get("orden") or []),
    }


def articulos_formulario(db: Session, user: Usuario, proveedor: str, q: str = "") -> list[dict]:
    """Artículos activos del proveedor para las líneas de la OC."""
    exigir_alguno(user, "oc.editar", "oc.importar")
    prov = db.scalar(select(Proveedor).where(Proveedor.codigo == (proveedor or "").upper()))
    if not prov or (proveedores_de(user) is not None and prov.id not in proveedores_de(user)):
        return []
    arts = catalogo.buscar(db, q, proveedor_id=prov.id, solo_activos=True, limite=300)
    fichas = comex.de_articulos(db, [a.id for a in arts])  # el origen es del producto (ficha técnica)

    def opcion(a: catalogo.FichaArticulo, ficha: comex.FichaComex | None) -> dict:
        return {"valor": a.codigo, "texto": " · ".join(x for x in (a.codigo, catalogo.texto(a.valores)) if x),
                "unidad": a.unidad, "tipo": a.tipo, "sub": a.descripcion, "pais_origen": ficha.pais_origen if ficha else None}

    return [opcion(a, fichas.get(a.id)) for a in arts]
