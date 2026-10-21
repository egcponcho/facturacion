"""Listas de valores de la empresa.

Las listas con reglas propias tienen su tabla (monedas, unidades_medida,
modos_transporte, incoterms, condiciones_pago) y los documentos las
referencian con llave foránea; las demás viven en `valores_lista`.

`cargar` arma, para cada petición, los valores activos de todas las listas
con la misma forma para todas ({código, nombre, atributos}); `validar` revisa
un valor que se crea o cambia en Datos maestros. La definición de las listas
está en core/listas.py.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import listas
from app.modelos import CondicionPago, Incoterm, ModoTransporte, Moneda, UnidadMedida, ValorLista

# lista → modelo de su tabla propia
MODELOS = {"unidad": UnidadMedida, "moneda": Moneda, "modo_transporte": ModoTransporte, "incoterm": Incoterm,
           "condicion_pago": CondicionPago}


def modelo(lista: str):
    return MODELOS.get(lista, ValorLista)


def lista_de(obj) -> str | None:
    """Lista a la que pertenece un registro de cualquiera de las tablas."""
    if isinstance(obj, ValorLista):
        return obj.lista
    return next((k for k, m in MODELOS.items() if isinstance(obj, m)), None)


def _dict(lista: str, v) -> dict:
    atributos = listas.LISTAS.get(lista, {}).get("atributos", [])
    return {"codigo": v.codigo, "nombre": v.nombre,
            **{a: getattr(v, a) for a in atributos if getattr(v, a, None) is not None}}


def cargar(db: Session) -> dict:
    """{lista: [valores activos en su orden]} de todas las listas."""
    res = {k: [] for k in listas.LISTAS}
    for v in db.scalars(select(ValorLista).where(ValorLista.activo.is_(True))
                        .order_by(ValorLista.lista, ValorLista.orden, ValorLista.codigo)):
        res.setdefault(v.lista, []).append(_dict(v.lista, v))
    for lista, m in MODELOS.items():
        res[lista] = [_dict(lista, v) for v in db.scalars(select(m).where(m.activo.is_(True)).order_by(m.orden, m.codigo))]
    return res


def sembrar(db: Session) -> None:
    """Valores de fábrica en una organización que aún no tiene ninguno."""
    if not db.scalar(select(ValorLista.id).limit(1)):
        for lista, valores in listas.FABRICA.items():
            if lista not in MODELOS:
                for orden, v in enumerate(valores, start=1):
                    db.add(ValorLista(lista=lista, orden=orden, activo=True, **v))
    for lista, m in MODELOS.items():
        if not db.scalar(select(m.id).limit(1)):
            for orden, v in enumerate(listas.FABRICA[lista], start=1):
                db.add(m(orden=orden, activo=True, **v))


def validar(db: Session, final: dict, actual, limpio: dict, lista: str | None = None) -> list[dict]:
    """Reglas de un valor: los atributos de su lista y los valores de sistema."""
    errores = []
    lista = lista or final.get("lista")
    definicion = listas.LISTAS.get(lista, {})
    if lista not in MODELOS:
        # Los atributos que no son de la lista no se guardan
        for a in ("padre", "consolidado", "estados"):
            if a not in definicion.get("atributos", []):
                final[a] = limpio[a] = None
    if actual:
        if isinstance(actual, ValorLista) and "lista" in limpio and limpio["lista"] != actual.lista:
            errores.append({"campo": "lista", "mensaje": "A value cannot move to another list."})
        if actual.codigo in definicion.get("sistema", []):
            if "codigo" in limpio and limpio["codigo"] != actual.codigo:
                errores.append({"campo": "codigo", "mensaje": "The system relies on this value: its code cannot change."})
            if final.get("activo") is False:
                errores.append({"campo": "activo", "mensaje": "The system relies on this value: it cannot be deactivated."})
    if lista == "evento_embarque":
        fabrica = {v["codigo"]: v["estados"] for v in listas.FABRICA["evento_embarque"]}
        codigo = actual.codigo if actual else final.get("codigo")
        if codigo in fabrica and (final.get("estados") or "") != fabrica[codigo]:
            errores.append({"campo": "estados", "mensaje": "A system milestone keeps its statuses: they drive the shipment."})
        elif not final.get("estados"):
            errores.append({"campo": "estados", "mensaje": "Choose the statuses where the milestone can be recorded."})
    if lista == "moneda" and final.get("decimales") is not None and final["decimales"] > 4:
        errores.append({"campo": "decimales", "mensaje": "At most 4 decimals."})
    for a in ("letras_en", "letras_es", "etiqueta_unidad"):
        if final.get(a) and final[a].count("|") != 1:
            errores.append({"campo": a, "mensaje": "Write the singular and the plural separated by |, e.g. DOLLAR|DOLLARS."})
    if lista == "modo_transporte" and final.get("calculo") == "PESO_COBRABLE" and not final.get("factor"):
        errores.append({"campo": "factor", "mensaje": "Chargeable weight needs the volumetric factor (kg per m³)."})
    if lista == "modalidad_transporte" and not final.get("padre"):
        errores.append({"campo": "padre", "mensaje": "Choose the transport mode of this modality."})
    if lista == "unidad":
        errores += _validar_base(db, final, actual)
    return errores


def _validar_base(db: Session, final: dict, actual) -> list[dict]:
    """Una unidad convierte a una base de un solo paso: la base no convierte a otra
    (así cualquier cantidad pasa a su base con una multiplicación)."""
    base, equivale = final.get("base") or None, final.get("equivale")
    codigo = final.get("codigo") or (actual.codigo if actual else None)
    if (base is None) != (equivale is None):
        return [{"campo": "equivale" if base else "base",
                 "mensaje": "Write both the base unit and how many of it one equals, or neither."}]
    if base is None:
        return []
    if equivale <= 0:
        return [{"campo": "equivale", "mensaje": "The equivalence must be greater than zero."}]
    if base == codigo:
        return [{"campo": "base", "mensaje": "A unit cannot convert to itself."}]
    otra = db.scalar(select(UnidadMedida).where(UnidadMedida.codigo == base))
    if otra is None:
        return [{"campo": "base", "mensaje": "The base unit is not in the list."}]
    if otra.base:
        return [{"campo": "base", "mensaje": f"{base} converts to {otra.base}: choose {otra.base} as the base."}]
    if codigo and db.scalar(select(UnidadMedida.id).where(UnidadMedida.base == codigo).limit(1)):
        return [{"campo": "base", "mensaje": "Other units convert to this one: it is a base unit."}]
    return []
