"""Vocabulario de la ficha para plantillas, cargas y condiciones de los
códigos nacionales. Sale del catálogo único (atributos, opciones y categorías
de la base, los mismos que usa el motor de clasificación): nada está escrito
en el código."""
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modelos import CondicionRegla, ReglaClasificacion
from app.modulos.documentos.plantillas import norm
from app.modulos.productos.ficha import catalogo

# Condiciones propias de las líneas nacionales que no son atributos de la ficha
CIF = {"cifMax": {"label": "CIF value up to (US$)", "tipo": "numero", "ops": {}},
       "cifMin": {"label": "CIF value over (US$)", "tipo": "numero", "ops": {}}}


def opciones_cond(db: Session) -> dict[str, dict]:
    """Por cada dato que puede separar líneas nacionales (atributos de producto
    y nacionales, y los que ya usan las líneas cargadas): etiqueta, tipo
    (opciones | sino | numero) y sus opciones {valor: etiqueta}."""
    if "opciones_cond" in db.info and db.info.get("catalogo") is db.info["opciones_cond"][0]:
        return db.info["opciones_cond"][1]
    cat = catalogo(db)
    # Campos que ya usan las reglas de selección de las líneas nacionales
    usados = set(db.scalars(select(CondicionRegla.campo).join(ReglaClasificacion)
                            .where(ReglaClasificacion.tipo_regla == "NATIONAL_SELECT").distinct()))
    out = {}
    for a in cat.atributos:
        if a.tipo_dato not in ("select", "boolean", "number") or not (a.seccion in ("producto", "nacional") or a.codigo in usados):
            continue
        tipo = "sino" if a.booleano else "numero" if a.tipo_dato == "number" else "opciones"
        out[a.codigo] = {"label": a.etiqueta, "tipo": tipo, "ops": {o.codigo: o.etiqueta for o in a.opciones if o.activo}}
    out.update(CIF)
    db.info["opciones_cond"] = (cat, out)
    return out


def valor_opcion(ops: dict, texto: str) -> str | None:
    """Valor de una opción por su código o su etiqueta; también por el inicio
    de la etiqueta («Men» para «Men or boys», «Unisex» para «Unisex (anyone)»)
    si solo una opción empieza así."""
    t = norm(texto)
    if not t:
        return None
    for v, lbl in ops.items():
        if t in (norm(v), norm(lbl)):
            return v
    cortas = [v for v, lbl in ops.items() if norm(re.split(r" or |\(|,| o ", str(lbl))[0]) == t]
    return cortas[0] if len(cortas) == 1 else None


def cond_texto(db: Session, cond: dict) -> str:
    """Condiciones en palabras, para listas y reportes."""
    oc = opciones_cond(db) if cond else {}
    partes = []
    for k, v in (cond or {}).items():
        d = oc.get(k, {"label": k, "ops": {}, "tipo": ""})
        if d["tipo"] == "numero":
            partes.append(f"{d['label']} {v}")
        elif isinstance(v, bool):
            partes.append(("" if v else "no ") + d["label"].lower())
        else:
            vals = v if isinstance(v, list) else [v]
            partes.append(f"{d['label']}: " + " or ".join(str(d["ops"].get(x, x)) for x in vals))
    return "; ".join(partes) or "Whole subheading"


def categoria_de(db: Session, valor: str) -> str | None:
    """Categoría por su código, su nombre, su nombre corto o en español."""
    v = norm(valor)
    if not v:
        return None
    for c in catalogo(db).categorias.values():
        if c.activo and v in (norm(c.codigo), norm(c.nombre), norm(c.nombre_corto or ""), norm(c.nombre_aduana or "")):
            return c.codigo
    return None


def atributos_carga(db: Session) -> list:
    """Atributos de la ficha que van como columnas en la carga masiva (de
    cualquier familia): los que deciden el código (en las condiciones de una
    regla activa) o que alguna categoría exige, de lista o sí/no, que no se
    deducen de la composición."""
    from app.modelos import AtributoAmbito, AtributoDef

    cat = catalogo(db)
    campos = set(db.scalars(select(CondicionRegla.campo).join(ReglaClasificacion).where(ReglaClasificacion.activo.is_(True))))
    campos |= set(db.scalars(select(AtributoDef.codigo).join(AtributoAmbito).where(AtributoAmbito.modo == "REQUIRE", AtributoAmbito.activo.is_(True))))
    return [a for a in cat.atributos if a.codigo in campos and a.tipo_dato in ("select", "boolean")
            and a.seccion in ("producto", "caracteristicas", "nacional") and not a.derivacion]


def partes_carga(db: Session) -> list:
    """Partes de la composición (atributos comp.*) del catálogo."""
    return [a for a in catalogo(db).atributos if a.tipo_dato == "composition" and a.codigo.startswith("comp.")]
