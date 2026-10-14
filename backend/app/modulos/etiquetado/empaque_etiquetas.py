"""Empaque en las etiquetas: lo planificado en la OC frente a lo declarado en
la lista de empaque, sin inventar cantidades.

- casepack de la línea (unidades por caja master) frente a las unidades de
  esa línea en un bulto de primer nivel que no está marcado como parcial;
- inner pack: las unidades de la línea en un bulto deben ser múltiplo;
- un prepack sin componentes definidos no se reparte por talla (lo avisa
  campos._filas_contenido).

Son advertencias de inconsistencia: la etiqueta dice lo que se declaró en la
lista de empaque, y quien genera ve la diferencia antes de imprimir.
"""
from __future__ import annotations

from app.modelos import PosicionOC
from app.modulos.etiquetado.campos import Bulto


def revisar(bulto: Bulto, posiciones: dict[int, PosicionOC]) -> list[dict]:
    res = [{"nivel": "advertencia", "codigo": "prepack_sin_componentes", "elemento": None, "mensaje": m} for m in bulto.avisos]
    for pid, q in sorted(bulto.por_posicion.items()):
        p = posiciones.get(pid)
        if p is None:
            continue
        if bulto.parcial:
            res.append({"nivel": "info", "codigo": "bulto_parcial", "elemento": None,
                        "mensaje": f"Partial package: line {p.posicion} has {q:g} units."})
            continue
        if bulto.cuenta_como == "BULTO" and p.casepack and abs(q - p.casepack) > 1e-9:
            res.append({"nivel": "advertencia", "codigo": "casepack_distinto", "elemento": None,
                        "mensaje": f"Line {p.posicion}: the packing list declares {q:g} units in this package and the PO "
                                   f"plans {p.casepack} per case."})
        if p.inner_pack and bulto.cuenta_como != "INTERIOR" and q % p.inner_pack > 1e-9:
            res.append({"nivel": "advertencia", "codigo": "inner_incompleto", "elemento": None,
                        "mensaje": f"Line {p.posicion}: {q:g} units are not whole inner packs of {p.inner_pack}."})
    return res
