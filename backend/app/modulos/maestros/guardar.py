"""Crear, editar y eliminar registros de un catálogo de datos maestros, con su
historial. Un registro en uso no se borra.
"""
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import listas
from app.core.errores import ErrorNegocio
from app.modelos import (
    Articulo,
    Atributo,
    PasoLeadTime,
    Proveedor,
    ReglaLeadTime,
    Transportista,
    Usuario,
)
from app.modulos.acceso.permisos import exigir, exigir_compartido
from app.modulos.comun.historial import registrar
from app.modulos.maestros import atributos as atr_svc
from app.modulos.maestros import gobierno
from app.modulos.maestros import variantes as variantes_svc
from app.modulos.maestros.catalogos import catalogo_de, exigir_editable, texto_registro
from app.modulos.maestros.listado import fila_tabla, referencias_de
from app.modulos.maestros.validacion import atributo_en_uso, limpiar_datos
from app.modulos.productos.productos import (
    asegurar_producto,
)
from app.modulos.transporte import reglas_lt as rlt


def crear(db: Session, user: Usuario, tipo: str, datos: dict) -> dict:
    exigir(user, "catalogos.crear")
    exigir_editable(tipo)
    exigir_compartido(user, tipo)
    gobierno.exigir_responsable(db, user, tipo)
    cat = catalogo_de(tipo)
    limpio = limpiar_datos(db, cat, datos, parcial=False)
    for campo in cat["campos"]:
        if campo["tipo"] == "bool" and campo["nombre"] not in datos:
            limpio[campo["nombre"]] = campo.get("defecto", True)
    virtuales = {k: limpio.pop(k) for k in cat.get("virtuales", ()) if k in limpio}
    variantes = limpio.pop("variantes", None)
    obj = cat["modelo"](**limpio)
    if isinstance(obj, Articulo):
        asegurar_producto(db, obj, virtuales.get("generico"))
        db.add(obj)
        if variantes:
            obj.variantes = variantes
        _poner_codigos(obj, virtuales)
    try:
        with db.begin_nested():
            db.add(obj)
            db.flush()
    except IntegrityError:
        raise ErrorNegocio(f"A {cat['singular']} with that code already exists.", 409, "duplicado") from None
    if isinstance(obj, Articulo):
        _exigir_articulo(db, obj)
    if isinstance(obj, Atributo):
        variantes_svc.olvidar(db)
    _asegurar_tercero(db, obj)
    registrar(db, user, tipo, obj.id, "crear", {"codigo": texto_registro(obj)})
    return fila_tabla(cat, obj, referencias_de(db, cat, [obj]))


def _asegurar_tercero(db: Session, obj) -> None:
    """Un proveedor o transportista tiene su tercero (identidad fiscal, direcciones y contacto)."""
    from app.modulos.maestros.terceros import asegurar

    if isinstance(obj, Proveedor):
        asegurar(db, obj, "PROVEEDOR")
    elif isinstance(obj, Transportista):
        asegurar(db, obj, "TRANSPORTISTA")


def actualizar(db: Session, user: Usuario, tipo: str, obj_id: int, datos: dict) -> dict:
    exigir(user, "catalogos.editar")
    exigir_editable(tipo)
    exigir_compartido(user, tipo)
    gobierno.exigir_responsable(db, user, tipo)
    cat = catalogo_de(tipo)
    obj = db.get(cat["modelo"], obj_id)
    if not obj:
        raise ErrorNegocio(f"The {cat['singular']} does not exist.", 404, "no_encontrado")
    limpio = limpiar_datos(db, cat, datos, parcial=True, actual=obj)
    if "codigo" in limpio and limpio["codigo"] != getattr(obj, "codigo", None) and gobierno.en_uso(db, tipo, obj.codigo):
        raise ErrorNegocio(f"{obj.codigo} is used in documents or other records: its code cannot change.", 409, "en_uso",
                           [{"campo": "codigo", "mensaje": "It is in use: its code cannot change."}])
    cambios = {}
    if isinstance(obj, Articulo):
        cambios.update(_cambiar_virtuales(db, obj, {k: limpio.pop(k) for k in cat.get("virtuales", ()) if k in limpio}))
        variantes = limpio.pop("variantes", None)
        if variantes is not None and variantes != obj.variantes:
            cambios["variantes"] = [obj.variantes, variantes]
            obj.variantes = variantes
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
        raise ErrorNegocio(f"A {cat['singular']} with that code already exists.", 409, "duplicado") from None
    if isinstance(obj, Articulo) and cambios:
        _exigir_articulo(db, obj)
    if isinstance(obj, Atributo) and cambios:
        variantes_svc.olvidar(db)
        # Quitarle familias no deja valores guardados fuera de ellas
        atr_svc.exigir(atr_svc.sin_alcance(db, [obj]), "The attribute is in use outside those families.")
    if {"nombre", "razon_social", "id_fiscal", "pais"} & set(cambios):
        _asegurar_tercero(db, obj)
    if cambios:
        registrar(db, user, tipo, obj.id, "editar", cambios)
    return fila_tabla(cat, obj, referencias_de(db, cat, [obj]))


def _poner_codigos(a: Articulo, virtuales: dict) -> None:
    if "codigo_barras" in virtuales:
        a.poner_codigo("BARRAS", virtuales["codigo_barras"])
    if "codigo_proveedor" in virtuales:
        a.poner_codigo("PROVEEDOR", virtuales["codigo_proveedor"], a.proveedor_id)


def _cambiar_virtuales(db: Session, a: Articulo, virtuales: dict) -> dict:
    """Producto y códigos del artículo editado en el catálogo: {dato: [antes, después]} de lo que cambió."""
    cambios = {}
    gen = virtuales.get("generico")
    if gen and gen != a.generico:
        cambios["generico"] = [a.generico, gen]
        asegurar_producto(db, a, gen)
    for campo in ("codigo_barras", "codigo_proveedor"):
        if campo in virtuales and (virtuales[campo] or None) != getattr(a, campo):
            cambios[campo] = [getattr(a, campo), virtuales[campo]]
    _poner_codigos(a, {k: v for k, v in virtuales.items() if k in cambios})
    return cambios


def _exigir_articulo(db: Session, a: Articulo) -> None:
    """Lo que la empresa y la familia exigen a la variante guardada."""
    from app.modulos.maestros.genericos import _exigidos_empresa
    from app.modulos.productos import perfil

    db.flush()
    errores = _exigidos_empresa(db, a)
    # Sus valores de variante valen en la familia de su producto (también si cambió de producto)
    errores += [{"campo": f"atr.{x.atributo.codigo}", "mensaje": f"{x.atributo.nombre} does not apply to the family of "
                 f"product {a.generico}."} for x in a.atributos if not variantes_svc.aplica(x.atributo, a.familia_efectiva)]
    if errores:
        raise ErrorNegocio("Some data your company requires is missing.", 422, "validacion", errores)
    perfil.exigir_variantes(db, [a])




def eliminar(db: Session, user: Usuario, tipo: str, obj_id: int) -> dict:
    exigir(user, "catalogos.eliminar")
    exigir_editable(tipo)
    exigir_compartido(user, tipo)
    gobierno.exigir_responsable(db, user, tipo)
    cat = catalogo_de(tipo)
    obj = db.get(cat["modelo"], obj_id)
    if not obj:
        raise ErrorNegocio(f"The {cat['singular']} does not exist.", 404, "no_encontrado")
    gobierno.exigir_sin_uso(db, tipo, obj)
    from app.modulos.maestros.listas import lista_de

    if obj.codigo in listas.LISTAS.get(lista_de(obj) or "", {}).get("sistema", []):
        raise ErrorNegocio("The system relies on this value: it can be renamed but not deleted.", 409, "en_uso")
    if isinstance(obj, Atributo) and atributo_en_uso(db, obj.id):
        raise ErrorNegocio("Products use this attribute: deactivate it instead.", 409, "en_uso")
    if isinstance(obj, PasoLeadTime):
        usan = [r.nombre for r in db.scalars(select(ReglaLeadTime)) if any(
            e["paso"] == obj.codigo or e.get("ref") == obj.codigo for e in rlt.cargar(r.pasos)["pasos"])]
        if usan:
            raise ErrorNegocio(f"It cannot be deleted: the step is used in {', '.join(usan)}. Deactivate it instead.",
                               409, "en_uso")
    try:
        with db.begin_nested():
            db.delete(obj)
            db.flush()
    except IntegrityError:
        raise ErrorNegocio(f"It cannot be deleted: the {cat['singular']} is in use. Deactivate it instead.",
                           409, "en_uso") from None
    registrar(db, user, tipo, obj_id, "eliminar", None)
    return {"ok": True}


