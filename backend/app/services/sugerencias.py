"""Sugerencia de unidades de carga para un volumen y un peso (de uno o varios
packing lists), usando los tipos de unidad del mantenimiento.

- Marítimo: contenedores FCL con un aprovechamiento real de volumen (no se
  llena el 100 % por la forma de las cajas), o LCL cuando el volumen no
  justifica un contenedor; también la combinación de contenedores llenos más
  un LCL para el resto.
- Aéreo: una guía por peso cobrable (el mayor entre el peso real y el
  volumétrico, 167 kg por m³).
- Terrestre: camiones completos (FTL) o carga parcial (LTL).
"""
from math import ceil

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import TipoUnidad

APROVECHAMIENTO = 0.85  # volumen útil de un contenedor o camión con cajas
MINIMO_COMPLETO = 0.45  # por debajo de esto conviene consolidado (LCL/LTL)
KG_POR_CBM_AEREO = 167


def _tipos(db: Session, modo: str) -> list[TipoUnidad]:
    return list(db.scalars(select(TipoUnidad).where(TipoUnidad.modo == modo, TipoUnidad.activo.is_(True))))


def _opcion(tipos: list[tuple[TipoUnidad, int]], cbm: float, kg: float, nota: str | None = None) -> dict:
    cap_cbm = sum((t.capacidad_cbm or 0) * n for t, n in tipos)
    cap_kg = sum((t.capacidad_kg or 0) * n for t, n in tipos)
    return {
        "unidades": [{"codigo": t.codigo, "nombre": t.nombre, "modalidad": t.modalidad, "cantidad": n}
                     for t, n in tipos if n],
        "texto": " + ".join(f"{n} × {t.codigo}" for t, n in tipos if n),
        "pct_cbm": round(cbm * 100 / cap_cbm, 1) if cap_cbm else None,
        "pct_kg": round(kg * 100 / cap_kg, 1) if cap_kg else None,
        "nota": nota,
    }


def _completos(completos: list[TipoUnidad], consolidado: TipoUnidad | None, cbm: float, kg: float,
               etiqueta: str) -> list[dict]:
    """Opciones con unidades completas (y consolidado para el resto)."""
    completos = sorted([t for t in completos if t.capacidad_cbm], key=lambda t: t.capacidad_cbm)
    if not completos:
        return [_opcion([(consolidado, 1)], cbm, kg)] if consolidado else []
    menor, mayor = completos[0], completos[-1]
    opciones = []
    if consolidado and cbm <= menor.capacidad_cbm * APROVECHAMIENTO * MINIMO_COMPLETO:
        opciones.append(_opcion([(consolidado, 1)], cbm, kg,
                                f"The volume does not justify a full {etiqueta}; ship it consolidated."))
    # Solo un tipo de unidad completa
    for t in completos:
        util = t.capacidad_cbm * APROVECHAMIENTO
        n = max(ceil(cbm / util), ceil(kg / t.capacidad_kg) if t.capacidad_kg else 0, 1)
        opciones.append(_opcion([(t, n)], cbm, kg))
    # Unidades grandes llenas y el resto en una más chica o consolidado
    util_mayor = mayor.capacidad_cbm * APROVECHAMIENTO
    llenos = int(cbm // util_mayor)
    resto = cbm - llenos * util_mayor
    if llenos and resto > 0:
        chica = next((t for t in completos if t.capacidad_cbm * APROVECHAMIENTO >= resto), None)
        if chica and chica is not mayor:
            opciones.append(_opcion([(mayor, llenos), (chica, 1)], cbm, kg))
        if consolidado and resto <= menor.capacidad_cbm * APROVECHAMIENTO * MINIMO_COMPLETO:
            opciones.append(_opcion([(mayor, llenos), (consolidado, 1)], cbm, kg,
                                    f"The remainder ({resto:.1f} m³) ships consolidated."))
    # Sin repetidas; la recomendada: menos unidades y luego menos capacidad sobrante
    vistas, unicas = set(), []
    for o in opciones:
        if o["texto"] not in vistas:
            vistas.add(o["texto"])
            unicas.append(o)

    def costo(o):
        completas = sum(u["cantidad"] for u in o["unidades"] if u["modalidad"] not in ("LCL", "LTL"))
        sobra = 100 - (o["pct_cbm"] or 100)
        return (completas, sobra)

    unicas.sort(key=costo)
    if unicas:
        unicas[0]["recomendada"] = True
    return unicas[:4]


def sugerir_unidades(db: Session, cbm: float, kg: float, modo: str | None = None) -> dict:
    cbm, kg = round(cbm or 0, 3), round(kg or 0, 1)
    res = {"cbm": cbm, "kg": kg, "modos": {}}
    if cbm <= 0 and kg <= 0:
        return res
    for m in ([modo] if modo else ["MARITIMO", "AEREO", "TERRESTRE"]):
        tipos = _tipos(db, m)
        if not tipos:
            continue
        if m == "AEREO":
            cobrable = max(kg, cbm * KG_POR_CBM_AEREO)
            guia = next((t for t in tipos if t.modalidad == "AEREO"), tipos[0])
            n = max(ceil(cobrable / guia.capacidad_kg), 1) if guia.capacidad_kg else 1
            o = _opcion([(guia, n)], cbm, kg, f"Chargeable weight {cobrable:,.0f} kg "
                                              f"(greater of actual weight and {KG_POR_CBM_AEREO} kg per m³).")
            o["recomendada"] = True
            o["peso_cobrable"] = round(cobrable, 1)
            res["modos"][m] = [o]
            continue
        consolidado = next((t for t in tipos if t.modalidad in ("LCL", "LTL")), None)
        completos = [t for t in tipos if t.modalidad in ("FCL", "FTL")]
        res["modos"][m] = _completos(completos, consolidado, cbm, kg,
                                     "container" if m == "MARITIMO" else "truck")
    return res
