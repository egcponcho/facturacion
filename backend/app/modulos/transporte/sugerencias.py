"""Sugerencia de unidades de carga para un volumen y un peso (de uno o varios
packing lists), usando los tipos de unidad del mantenimiento.

Cada modo de transporte (Datos maestros → Listas de valores) dice cómo se
calcula:

- Por volumen: unidades completas (p. ej. contenedores FCL o camiones FTL)
  con un aprovechamiento real de volumen (no se llena el 100 % por la forma de
  las cajas), o consolidado (LCL, LTL) cuando el volumen no justifica una
  unidad completa; también unidades llenas más un consolidado para el resto.
  Una modalidad es consolidada según su lista.
- Por peso cobrable: el mayor entre el peso real y el volumétrico (volumen ×
  el factor del modo, p. ej. 167 kg por m³ en aéreo).
"""
from math import ceil

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import listas
from app.core.errores import ErrorNegocio
from app.modelos import TipoUnidad

APROVECHAMIENTO = 0.85  # volumen útil de un contenedor o camión con cajas
MINIMO_COMPLETO = 0.45  # por debajo de esto conviene consolidado (LCL/LTL)


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


def _consolidadas() -> set[str]:
    return {m["codigo"] for m in listas.valores("modalidad_transporte") if m.get("consolidado")}


def _completos(completos: list[TipoUnidad], consolidado: TipoUnidad | None, cbm: float, kg: float) -> list[dict]:
    """Opciones con unidades completas (y consolidado para el resto)."""
    completos = sorted([t for t in completos if t.capacidad_cbm], key=lambda t: t.capacidad_cbm)
    if not completos:
        return [_opcion([(consolidado, 1)], cbm, kg)] if consolidado else []
    menor, mayor = completos[0], completos[-1]
    opciones = []
    if consolidado and cbm <= menor.capacidad_cbm * APROVECHAMIENTO * MINIMO_COMPLETO:
        opciones.append(_opcion([(consolidado, 1)], cbm, kg,
                                f"The volume does not justify a full {menor.nombre}; ship it consolidated."))
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
        completas = sum(u["cantidad"] for u in o["unidades"] if u["modalidad"] not in consolidadas)
        sobra = 100 - (o["pct_cbm"] or 100)
        return (completas, sobra)

    consolidadas = _consolidadas()
    unicas.sort(key=costo)
    if unicas:
        unicas[0]["recomendada"] = True
    return unicas[:4]


def sugerir_unidades(db: Session, cbm: float, kg: float, modo: str | None = None) -> dict:
    cbm, kg = round(cbm or 0, 3), round(kg or 0, 1)
    res = {"cbm": cbm, "kg": kg, "modos": {}}
    if cbm <= 0 and kg <= 0:
        return res
    modos = listas.valores("modo_transporte")
    if modo and modo not in {m["codigo"] for m in modos}:
        raise ErrorNegocio(f"The transport mode {modo} does not exist.", 422, "validacion")
    consolidadas = _consolidadas()
    for m in [x for x in modos if not modo or x["codigo"] == modo]:
        tipos = _tipos(db, m["codigo"])
        if not tipos:
            continue
        if m.get("calculo") == "PESO_COBRABLE":
            factor = m.get("factor") or 0
            cobrable = max(kg, cbm * factor)
            guia = next((t for t in tipos if t.modalidad not in consolidadas), tipos[0])
            n = max(ceil(cobrable / guia.capacidad_kg), 1) if guia.capacidad_kg else 1
            o = _opcion([(guia, n)], cbm, kg, f"Chargeable weight {cobrable:,.0f} kg "
                                              f"(greater of actual weight and {factor:g} kg per m³).")
            o["recomendada"] = True
            o["peso_cobrable"] = round(cobrable, 1)
            res["modos"][m["codigo"]] = [o]
            continue
        consolidado = next((t for t in tipos if t.modalidad in consolidadas), None)
        completos = [t for t in tipos if t.modalidad not in consolidadas]
        res["modos"][m["codigo"]] = _completos(completos, consolidado, cbm, kg)
    return res
