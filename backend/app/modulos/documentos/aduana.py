"""Nombres aduaneros de cada país en los documentos.

Cada país llama de forma distinta a su nomenclatura arancelaria (SAC en
Centroamérica, HTS en Estados Unidos, TARIC en la Unión Europea), a su derecho
de importación (DAI, «duty», IGI…) y a la identificación fiscal de una empresa
(NIT, RUC, RFC, EIN…). Son datos del país (`paises_arancel.nomenclatura`,
`paises_arancel.nombre_derecho`, `paises.nombre_id_fiscal`), no del código: un
documento los toma del país al que corresponde y, si el país no los tiene,
usa el nombre genérico («HS code», «Duty», «Tax ID»).
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modelos import Pais, PaisArancel
from app.modulos.documentos.idioma_doc import L


def nombres(db: Session, paises: list[str] | None = None) -> dict:
    """{"nomenclatura": …, "derecho": …} de los países dados (o de todos los
    activos con arancel). Solo se nombra cuando todos coinciden: si dos
    países usan nomenclaturas distintas, el documento dice la genérica."""
    consulta = select(PaisArancel.nomenclatura, PaisArancel.nombre_derecho).where(PaisArancel.activo.is_(True))
    if paises is not None:
        consulta = consulta.where(PaisArancel.iso.in_([p for p in paises if p]))
    filas = db.execute(consulta).all()
    nomenclaturas = {f.nomenclatura for f in filas}
    derechos = {f.nombre_derecho for f in filas}
    return {"nomenclatura": next(iter(nomenclaturas)) if len(nomenclaturas) == 1 else None,
            "derecho": next(iter(derechos)) if len(derechos) == 1 else None}


def nombre_id_fiscal(db: Session, pais: str | None) -> str | None:
    """Cómo se llama la identificación fiscal en el país (NIT, RUC, RFC…)."""
    if not pais:
        return None
    return db.scalar(select(Pais.nombre_id_fiscal).where(Pais.codigo == pais))


def titulo_codigo(aduana: dict | None) -> str:
    nom = (aduana or {}).get("nomenclatura")
    return L("HS code ({0})", nom) if nom else L("HS code")


def titulo_derecho(aduana: dict | None) -> str:
    nom = (aduana or {}).get("derecho")
    return L("Duty ({0})", nom) if nom else L("Duty")


def texto_id_fiscal(parte: dict) -> str:
    nom = parte.get("id_fiscal_nombre")
    return L("Tax ID ({0}): {1}", nom, parte["id_fiscal"]) if nom else L("Tax ID: {0}", parte["id_fiscal"])
