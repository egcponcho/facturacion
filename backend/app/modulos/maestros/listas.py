"""Listas de valores de la empresa (tabla valores_lista).

`cargar` arma, para cada petición, los valores activos de todas las listas;
`validar` revisa un valor que se crea o cambia en Datos maestros → Listas de
valores. La definición de las listas está en core/listas.py.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import listas
from app.modelos import ValorLista

_COLUMNAS = ("codigo", "nombre", *listas.ATRIBUTOS)


def _dict(v: ValorLista) -> dict:
    return {c: getattr(v, c) for c in _COLUMNAS if c in ("codigo", "nombre") or getattr(v, c) is not None}


def cargar(db: Session) -> dict:
    """{lista: [valores activos en su orden]} de todas las listas."""
    res = {k: [] for k in listas.LISTAS}
    for v in db.scalars(select(ValorLista).where(ValorLista.activo.is_(True))
                        .order_by(ValorLista.lista, ValorLista.orden, ValorLista.codigo)):
        res.setdefault(v.lista, []).append(_dict(v))
    return res


def validar(db: Session, final: dict, actual: ValorLista | None, limpio: dict) -> list[dict]:
    """Reglas de un valor: los atributos de su lista y los valores de sistema."""
    errores = []
    lista = final.get("lista")
    definicion = listas.LISTAS.get(lista, {})
    # Los atributos que no son de la lista no se guardan
    for a in listas.ATRIBUTOS:
        if a not in definicion.get("atributos", []):
            final[a] = limpio[a] = None
    if actual:
        if "lista" in limpio and limpio["lista"] != actual.lista:
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
    return errores
