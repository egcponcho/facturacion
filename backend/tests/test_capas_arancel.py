"""Separación de capas: solo fuentes oficiales determinan qué códigos, textos
legales, DAI, impuestos y regulaciones existen. El motor interpreta y la empresa
aporta historial, pero ninguno de los dos crea ni modifica datos oficiales."""
from sqlalchemy import func, select

from app.db import SessionLocal
from app.models import HistorialClasificacion, IncisoNacional, NotaSAC, ReglaClasificacion, ReglaImpuesto, Regulacion


def test_official_tariff_contains_only_official_sources(interno):
    with SessionLocal() as db:
        lineas = db.scalars(select(IncisoNacional)).all()
        assert lineas
        assert all(x.fuente == "oficial" and x.fuente_id and x.version_id for x in lineas)
        # Ninguna línea viene del historial de la empresa (sus códigos de NI, CR y PA no existen como líneas)
        assert not {x.pais for x in lineas} & {"NI", "CR", "PA"}


def test_every_official_line_has_version_and_source(interno):
    from app.models import FuenteOficial, VersionDataset

    with SessionLocal() as db:
        for x in db.scalars(select(IncisoNacional)):
            v, f = db.get(VersionDataset, x.version_id), db.get(FuenteOficial, x.fuente_id)
            assert v and f, x.codigo
            assert (v.ambito or "").upper() in (x.pais, "REGIONAL")
        for n in db.scalars(select(NotaSAC).where(NotaSAC.tipo_fuente.in_(NotaSAC.OFICIALES))):
            assert n.version_id and n.fuente_id, n.id


def test_company_history_cannot_create_national_tariff_lines(interno):
    with SessionLocal() as db:
        antes = db.scalar(select(func.count()).select_from(IncisoNacional))
        assert db.scalar(select(func.count()).select_from(HistorialClasificacion).where(HistorialClasificacion.pais == "PA"))
    # Recordar un código de un país sin arancel oficial cargado: no se crea la línea
    r = interno.post("/clasificacion/incisos", {"pais": "PA", "codigo": "640419990000"})
    assert r.status_code == 422 and r.json()["codigo"] == "no_es_linea_oficial"
    # Sobre una línea oficial: queda solo en el historial
    assert interno.post("/clasificacion/incisos", {"pais": "GT", "codigo": "6404.19.90.00", "cond": {"genero": "M"}}).status_code == 200
    # Crear una línea sin fuente ni versión oficial tampoco se puede
    r = interno.post("/aranceles/codigos", {"pais": "PA", "codigo": "640419990000"})
    assert r.status_code == 422 and r.json()["codigo"] == "sin_procedencia"
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(IncisoNacional)) == antes
        assert not db.scalar(select(IncisoNacional.id).where(IncisoNacional.pais == "PA"))


def test_company_conditions_never_marked_as_official(interno):
    from app.services.motor_clasificacion import CAPA

    with SessionLocal() as db:
        reglas = db.scalars(select(ReglaClasificacion).where(ReglaClasificacion.inciso_id.is_not(None))).all()
        # Las condiciones de selección nacional son del motor (interpretación del texto) o de la empresa, nunca ley
        assert reglas and all(r.tipo_fuente in ("CLASSIFIER", "MANUAL") for r in reglas)
        assert all(CAPA.get(r.tipo_fuente) != "LEGAL" for r in reglas)
        # Las condiciones de la base de artículos de la empresa están en el historial, no en las líneas
        hist = db.scalars(select(HistorialClasificacion).where(HistorialClasificacion.origen == "IMPORTADO")).all()
        assert any("estiloCalz" in (h.condiciones or {}) or "puntera" in (h.condiciones or {}) for h in hist)
        # Las del motor (CLASSIFIER) son exactamente lo que el clasificador lee del texto oficial del ACI
        import json
        from pathlib import Path

        aci = {x["codigo"]: x["cond"] for x in json.loads((Path(__file__).parents[1] / "app/data/aci_incisos.json").read_text()) if x.get("cond")}
        for x in db.scalars(select(IncisoNacional)):
            if x.regla and x.regla.tipo_fuente == "CLASSIFIER":
                assert x.cond == aci.get(x.codigo), (x.pais, x.codigo, x.cond)


def test_official_tax_requires_source_or_legal_basis(interno):
    base = {"pais": "SV", "patron": "6404", "tipo": "SELECTIVO", "tasa": 5, "base_calculo": "CIF"}
    with SessionLocal() as db:
        from app.models import PaisArancel

        sv = db.scalar(select(PaisArancel).where(PaisArancel.iso == "SV"))
        tiene_fuente = bool(sv.fuente_impuestos_id)
    r = interno.post("/aranceles/impuestos", base)
    assert (r.status_code == 200) == tiene_fuente, r.text  # la fuente de impuestos configurada del país sirve como fuente
    if not tiene_fuente:
        assert "official source or its legal basis" in r.json()["mensaje"]
    assert interno.post("/aranceles/impuestos", {**base, "base_legal": "Ley de prueba, art. 1"}).status_code == 200
    # Sin tasa o sin base de cálculo no es un impuesto completo
    assert interno.post("/aranceles/impuestos", {**base, "tasa": None, "base_legal": "Ley"}).status_code == 422
    # Ningún impuesto ni regulación queda sin fuente ni base legal (no hay impuestos de demostración)
    with SessionLocal() as db:
        for x in [*db.scalars(select(ReglaImpuesto)), *db.scalars(select(Regulacion))]:
            assert x.fuente_id or (x.base_legal or "").strip(), x.codigo


def test_official_notes_exclude_internal_summaries(interno):
    notas = interno.get("/aranceles/notas").json()["items"]
    tipos = {n["tipo_fuente"] for n in notas}
    assert {"OFFICIAL_LEGAL", "CLASSIFIER_GUIDANCE"} <= tipos
    # Los resúmenes propios de las Notas Explicativas son guía, nunca texto oficial
    assert all(not n["oficial"] for n in notas if n["ambito"] == "explicativa")
    assert all(n["oficial"] == n["tipo_fuente"].startswith("OFFICIAL_") for n in notas)
    # Una nota escrita por la empresa es guía interna
    r = interno.post("/aranceles/notas", {"ambito": "capitulo", "codigo": "64", "numero": "X1", "texto": "Nota interna de prueba",
                                          "capitulos": ["64"], "activo": True})
    assert r.status_code == 200 and r.json()["tipo_fuente"] == "INTERNAL_GUIDANCE" and not r.json()["oficial"]
    # El soporte del producto recibe el tipo para mostrar "Texto oficial" o "Guía"
    ctx = interno.get("/clasificacion/contexto").json()
    assert all("oficial" in n and "tipo_fuente" in n for n in ctx["notas_sac"])
