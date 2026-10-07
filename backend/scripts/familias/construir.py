"""Construye la semilla del motor (app/data/motor/familias/*.json) desde los
módulos de cada familia, escritos con las Notas Explicativas del SA.

Uso (desde backend/): python scripts/familias/construir.py

Valida que cada código de regla y de caso exista en el árbol oficial vigente
y que cada condición nombre un atributo y una opción que existen.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import accesorios  # noqa: E402
import calzado  # noqa: E402
import comun  # noqa: E402
import materias_primas  # noqa: E402
import quimicos  # noqa: E402
import ropa  # noqa: E402
from base import escribir, validar  # noqa: E402

FAMILIAS = {"calzado": calzado, "ropa": ropa, "accesorios": accesorios, "quimicos": quimicos, "materias_primas": materias_primas}


def main() -> None:
    comunes = {a["codigo"]: a for a in comun.atributos()}
    escribir("comun", {"origen": "Classification engine configuration shared by every family (not official data).",
                       "clases_material": comun.CLASES_MATERIAL, "vocabulario_aduana": comun.VOCABULARIO,
                       "atributos": list(comunes.values())})
    vistos_cat, vistos_attr, vistas_reglas = set(), set(comunes), set()
    for nombre, mod in FAMILIAS.items():
        fam = mod.familia()
        validar(fam, comunes)
        for c in fam["categorias"]:
            assert c["codigo"] not in vistos_cat, f"category {c['codigo']} repeated"
            vistos_cat.add(c["codigo"])
        for a in fam["atributos"]:
            assert a["codigo"] not in vistos_attr, f"attribute {a['codigo']} repeated"
            vistos_attr.add(a["codigo"])
        for r in fam["reglas"]:
            assert r["codigo"] not in vistas_reglas, f"rule {r['codigo']} repeated"
            vistas_reglas.add(r["codigo"])
        for k in fam.get("ambitos_comunes", {}):
            assert k in comunes, f"{nombre}: {k} is not a shared attribute"
        ruta = escribir(nombre, {"origen": f"Classification engine configuration written from the {fam['fuente']} (not official data).",
                                 **fam})
        print(f"{ruta.name}: {len(fam['categorias'])} categories, {len(fam['atributos'])} attributes, {len(fam['reglas'])} rules, "
              f"{len(fam.get('casos', []))} cases")


if __name__ == "__main__":
    main()
