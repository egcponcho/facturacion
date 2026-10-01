"""Lead times configurables: catálogo de pasos → reglas por nivel geográfico →
herencia → lead time efectivo.

Cada regla (Global, Región, País o Puerto) define solo lo que cambia:

    {"pasos": [{"paso": "LIB", "ref": "XF", "dias": -21, "habiles": false, "modo": "", "quitar": false}],
     "orden": ["BOOKING", "LIB", "XF", ...] | null}

- `paso`: código del catálogo de pasos.
- `ref` y `dias`: la fecha del paso es la del paso de referencia más `dias`
  (negativo = antes). El paso sin referencia es el ancla (normalmente XF).
- `habiles`: cuenta solo lunes a viernes.
- `modo`: aplica solo a ese modo de transporte (vacío = todos).
- `quitar`: este nivel quita el paso heredado.
- `orden`: si viene, cambia el orden en que se muestran los pasos.

Herencia: Global → Región → País → Puerto. Un nivel más específico
sobrescribe el paso (mismo paso y modo) del nivel superior; lo que no toca lo
hereda. Así, Asia puede pedir la liberación 21 días antes de la XF, Vietnam 15
y el puerto de Cat Lai 12, sin configurar cada país ni cada puerto.
"""
import json
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Pais, PasoLeadTime, Puerto, ReglaLeadTime, RegionLeadTime

NIVELES = [("GLOBAL", "Global"), ("REGION", "Region"), ("PAIS", "Country"), ("PUERTO", "Port")]
CAMPO_NIVEL = {"REGION": "region", "PAIS": "pais", "PUERTO": "puerto"}
# Fechas que el sistema mide; un paso del catálogo puede representar una de ellas
HITOS = [
    ("lib_logistica", "Logistics release"), ("xf", "XF (ex-factory / pickup)"), ("salida", "Departure (ETD)"),
    ("arribo", "Port arrival (ETA)"), ("entrega", "Warehouse delivery"), ("ingreso", "Warehouse entry"),
    ("tienda", "In store"),
]
ORDEN_HITOS = [h for h, _ in HITOS]
MODOS = ["MARITIMO", "AEREO", "TERRESTRE"]


# ---- Lectura y validación de una regla ---------------------------------------
def cargar(v) -> dict:
    try:
        d = json.loads(v) if isinstance(v, str) else (v or {})
    except ValueError:
        d = {}
    if isinstance(d, list):
        d = {"pasos": d}
    return {"pasos": [p for p in d.get("pasos") or [] if isinstance(p, dict)], "orden": d.get("orden") or None}


def validar(db: Session, v) -> tuple[dict, list[str]]:
    """Normaliza las entradas de una regla y devuelve (regla, errores)."""
    d = cargar(v)
    catalogo = {p.codigo for p in db.scalars(select(PasoLeadTime))}
    pasos, errores, vistos = [], [], set()
    for i, e in enumerate(d["pasos"], 1):
        paso = str(e.get("paso") or "").strip().upper()
        modo = str(e.get("modo") or "").strip().upper()
        if paso not in catalogo:
            errores.append(f"Step {i}: {paso or '(empty)'} is not in the lead time steps catalog.")
            continue
        if modo and modo not in MODOS:
            errores.append(f"Step {i} ({paso}): invalid transport mode.")
            continue
        if (paso, modo) in vistos:
            errores.append(f"Step {paso} appears twice for the same transport mode.")
            continue
        vistos.add((paso, modo))
        if e.get("quitar"):
            pasos.append({"paso": paso, "modo": modo, "quitar": True})
            continue
        ref = str(e.get("ref") or "").strip().upper()
        if ref and ref not in catalogo:
            errores.append(f"Step {i} ({paso}): the reference {ref} is not in the catalog.")
            continue
        if ref == paso:
            errores.append(f"Step {i} ({paso}): a step cannot refer to itself.")
            continue
        try:
            dias = int(e.get("dias") or 0)
            if abs(dias) > 730:
                raise ValueError
        except (TypeError, ValueError):
            errores.append(f"Step {i} ({paso}): days between -730 and 730.")
            continue
        pasos.append({"paso": paso, "ref": ref, "dias": dias, "habiles": bool(e.get("habiles")), "modo": modo,
                      "quitar": False})
    orden = [str(x).upper() for x in d["orden"] if str(x).upper() in catalogo] if d["orden"] else None
    return {"pasos": pasos, "orden": orden}, errores


# ---- Herencia ---------------------------------------------------------------
def ambitos(db: Session, region: str | None, pais: str | None, puerto: str | None) -> list[tuple[str, str | None]]:
    """Niveles que aplican, del más general al más específico. Un puerto trae
    su país y el país su región."""
    if puerto and not pais:
        pais = db.scalar(select(Puerto.pais).where(Puerto.codigo == puerto))
    if pais and not region:
        region = db.scalar(select(Pais.region).where(Pais.codigo == pais))
    out = [("GLOBAL", None)]
    if region:
        out.append(("REGION", region))
    if pais:
        out.append(("PAIS", pais))
    if puerto:
        out.append(("PUERTO", puerto))
    return out


def _reglas(db: Session) -> dict:
    return {(r.nivel, getattr(r, CAMPO_NIVEL[r.nivel]) if r.nivel in CAMPO_NIVEL else None): r
            for r in db.scalars(select(ReglaLeadTime).where(ReglaLeadTime.activo))}


def combinar(niveles: list[tuple[str, str | None, str | None, dict]], catalogo: dict) -> dict:
    """Aplica las reglas de los niveles en orden. Cada paso efectivo lleva de
    qué nivel viene y, si sobrescribió algo, el valor anterior."""
    eff: dict[tuple, dict] = {}
    orden: list[str] = []
    quitados = []
    for nivel, ambito, nombre, regla in niveles:
        origen = {"nivel": nivel, "ambito": ambito, "nombre": nombre}
        for e in regla["pasos"]:
            k = (e["paso"], e.get("modo") or "")
            if e.get("quitar"):
                if k in eff:
                    quitados.append({**eff.pop(k), "quitado_por": origen})
                continue
            previo = eff.get(k)
            antes = {"ref": previo["ref"], "dias": previo["dias"], "habiles": previo["habiles"],
                     "origen": previo["origen"]} if previo else None
            eff[k] = {**{x: e.get(x) for x in ("paso", "ref", "dias", "habiles", "modo")}, "origen": origen,
                      "previo": antes,
                      # Todos los valores anteriores, del nivel más general al que sobrescribió
                      "historial": ((previo or {}).get("historial") or []) + ([antes] if antes else []),
                      "nombre": catalogo.get(e["paso"], {}).get("nombre", e["paso"]),
                      "hito": catalogo.get(e["paso"], {}).get("hito")}
            if e["paso"] not in orden:
                orden.append(e["paso"])
        if regla.get("orden"):
            orden = [c for c in regla["orden"] if c in orden] + [c for c in orden if c not in regla["orden"]]
    pos = {c: i for i, c in enumerate(orden)}
    pasos = sorted(eff.values(), key=lambda x: (pos.get(x["paso"], 999), x["modo"]))
    return {"pasos": pasos, "orden": [c for c in orden if any(p["paso"] == c for p in pasos)], "quitados": quitados}


def catalogo(db: Session) -> dict:
    return {p.codigo: {"codigo": p.codigo, "nombre": p.nombre, "hito": p.hito, "activo": p.activo,
                       "descripcion": p.descripcion}
            for p in db.scalars(select(PasoLeadTime).order_by(PasoLeadTime.codigo))}


def nombres_ambito(db: Session) -> dict:
    out = {("REGION", r.codigo): r.nombre for r in db.scalars(select(RegionLeadTime))}
    out.update({("PAIS", p.codigo): p.nombre for p in db.scalars(select(Pais))})
    out.update({("PUERTO", p.codigo): p.nombre for p in db.scalars(select(Puerto))})
    return out


def efectivo(db: Session, region=None, pais=None, puerto=None, sin_regla: int | None = None,
             con_regla: tuple | None = None, modo: str | None = None) -> dict:
    """Lead time efectivo de un ámbito con la procedencia de cada paso.
    `sin_regla`: deja fuera una regla (para ver lo heredado al editarla).
    `con_regla`: (nivel, ámbito, regla) en lugar de la guardada (para validar antes de guardar)."""
    cat = catalogo(db)
    reglas = _reglas(db)
    nombres = nombres_ambito(db)
    niveles = []
    for nivel, ambito in ambitos(db, region, pais, puerto):
        r = reglas.get((nivel, ambito))
        nombre = "Global" if nivel == "GLOBAL" else nombres.get((nivel, ambito), ambito)
        if con_regla and con_regla[0] == nivel and con_regla[1] == ambito:
            niveles.append((nivel, ambito, nombre, con_regla[2]))
        elif r and r.id != sin_regla:
            niveles.append((nivel, ambito, nombre, cargar(r.pasos)))
        else:
            niveles.append((nivel, ambito, nombre, {"pasos": [], "orden": None}))
    res = combinar(niveles, cat)
    res["niveles"] = [{"nivel": n, "ambito": a, "nombre": nm,
                       "regla_id": (reglas.get((n, a)).id if reglas.get((n, a)) else None),
                       "cambios": len(rg["pasos"])} for n, a, nm, rg in niveles]
    res["errores"] = errores_cadena(res["pasos"])
    res["dias"] = desplazamientos(res["pasos"], modo)
    res["ancla"] = next((c for c, p in de_modo(res["pasos"], modo).items() if not p.get("ref")), None)
    return res


# ---- Cadena: referencias y fechas ---------------------------------------------
def de_modo(pasos: list[dict], modo: str | None) -> dict[str, dict]:
    """Un paso por código para un modo: el del modo exacto o, si no hay, el general."""
    out: dict[str, dict] = {}
    for p in pasos:
        if p.get("modo") and p["modo"] != (modo or ""):
            continue
        if p["paso"] not in out or (p.get("modo") and not out[p["paso"]].get("modo")):
            out[p["paso"]] = p
    return out


def errores_cadena(pasos: list[dict]) -> list[str]:
    errores = []
    for modo in [None, *sorted({p["modo"] for p in pasos if p.get("modo")})]:
        nodos = de_modo(pasos, modo)
        sufijo = f" ({modo})" if modo else ""
        raices = [c for c, p in nodos.items() if not p.get("ref")]
        if nodos and len(raices) != 1:
            errores.append(f"There must be exactly one anchor step (without reference){sufijo}: "
                           f"{', '.join(raices) or 'none'}.")
        for c, p in nodos.items():
            if p.get("ref") and p["ref"] not in nodos:
                errores.append(f"{c}{sufijo}: its reference {p['ref']} is not in this lead time.")
        for c in nodos:
            vistos, x = set(), c
            while x and x in nodos:
                if x in vistos:
                    errores.append(f"{c}{sufijo}: the references form a loop.")
                    break
                vistos.add(x)
                x = nodos[x].get("ref")
    return list(dict.fromkeys(errores))


def sumar(fecha: date, dias: int, habiles: bool = False) -> date:
    """Suma días naturales o hábiles (lunes a viernes); `dias` puede ser negativo."""
    if not habiles:
        return fecha + timedelta(days=dias)
    paso = 1 if dias >= 0 else -1
    d, n = fecha, abs(dias)
    while n > 0:
        d += timedelta(days=paso)
        if d.weekday() < 5:
            n -= 1
    return d


def _ancestros(nodos: dict, c: str) -> list[str]:
    out = []
    while c and c in nodos and c not in out:
        out.append(c)
        c = nodos[c].get("ref")
    return out


def entre_pasos(fecha: date | None, nodos: dict, desde: str, hasta: str) -> date | None:
    """Fecha de `hasta` conociendo la de `desde`, recorriendo las referencias:
    hacia arriba se restan los días de cada paso, hacia abajo se suman."""
    if fecha is None or desde not in nodos or hasta not in nodos:
        return fecha
    arriba, abajo = _ancestros(nodos, desde), _ancestros(nodos, hasta)
    comun = next((x for x in arriba if x in abajo), None)
    for x in arriba:
        if x == comun:
            break
        p = nodos[x]
        fecha = sumar(fecha, -int(p.get("dias") or 0), bool(p.get("habiles")))
    for x in reversed(abajo[:abajo.index(comun)] if comun in abajo else abajo):
        p = nodos[x]
        fecha = sumar(fecha, int(p.get("dias") or 0), bool(p.get("habiles")))
    return fecha


def desplazamientos(pasos: list[dict], modo: str | None = None, ref: date = date(2026, 1, 5)) -> dict[str, int]:
    """Días (naturales) de cada paso respecto del ancla, para dibujar la línea de tiempo."""
    nodos = de_modo(pasos, modo)
    if errores_cadena([p for p in pasos if not p.get("modo") or p["modo"] == (modo or "")]):
        return {}
    raiz = next((c for c, p in nodos.items() if not p.get("ref")), None)
    if not raiz:
        return {}
    return {c: (entre_pasos(ref, nodos, raiz, c) - ref).days for c in nodos}
