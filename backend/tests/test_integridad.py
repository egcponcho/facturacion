"""Auditor de integridad de los datos arancelarios: la base incluida está limpia
y cada contaminación o dato oficial incompleto se detecta."""
from datetime import date

from sqlalchemy import select

from app.core.db import SessionLocal
from app.modelos import IncisoNacional, NotaSAC, ReglaImpuesto, Usuario, VersionDataset


def _checks(api):
    r = api.get("/aranceles/oficial/integridad")
    assert r.status_code == 200, r.text
    return r.json(), {c["codigo"]: c for c in r.json()["checks"]}


def test_base_incluida_sin_contaminacion(interno):
    d, c = _checks(interno)
    for codigo in ("LINE_SOURCE", "LINE_NOT_OFFICIAL", "LINE_COMPANY_BASE", "LINE_PARENT", "LINE_BASE_NOMENCLATURE", "LINE_DUPLICATE",
                   "TAX_SOURCE", "REGULATION_SOURCE", "NOTE_SOURCE", "NOTE_SUMMARY_AS_OFFICIAL", "RULE_AS_LEGAL", "VERSION_SOURCE"):
        assert c[codigo]["estado"] == "OK", (codigo, c[codigo]["hallazgos"][:3])
    assert d["estado"] in ("OK", "WARNING", "SOURCE_MISSING") and set(d["resumen"]) == {"OK", "WARNING", "ERROR", "SOURCE_MISSING",
                                                                                           "VERSION_EXPIRED", "CONTAMINATION"}


def test_detecta_contaminacion_y_datos_incompletos(interno):
    creados = []
    with SessionLocal() as db:
        sac = db.scalar(select(VersionDataset).where(VersionDataset.codigo == "SAC-2025-V6"))
        user = db.scalar(select(Usuario).where(Usuario.email == "interno@demo.com"))
        filas = [
            IncisoNacional(pais="NI", codigo="640299900000", sub6="640299", fuente="base"),  # base de artículos de la empresa
            IncisoNacional(pais="SV", codigo="6404199000", sub6="640419", fuente="oficial", version_id=sac.id, fuente_id=sac.fuente_id),  # duplicada
            IncisoNacional(pais="SV", codigo="9999990000", sub6="999999", fuente="oficial", version_id=sac.id, fuente_id=sac.fuente_id),  # sin padre
            IncisoNacional(pais="GT", codigo="64041999", sub6="640419", fuente="oficial", version_id=sac.id, fuente_id=sac.fuente_id,
                           creado_por=user.id),  # largo inválido, fuera del SAC y escrita a mano en una versión publicada
            IncisoNacional(pais="ZZ", codigo="6404199000", sub6="640419", fuente="oficial", version_id=sac.id, fuente_id=sac.fuente_id),
            IncisoNacional(pais="HN", codigo="6404190000", sub6="640419", fuente="oficial", version_id=sac.id, fuente_id=sac.fuente_id,
                           vigente_hasta=date(2020, 1, 1)),
        ]
        imp = ReglaImpuesto(codigo="TAX-TEST-SIN", pais="GT", patron="64", tipo="IVA", tasa=None)
        nota = NotaSAC(ambito="explicativa", codigo="6404", numero="X", texto="Resumen propio", tipo_fuente="OFFICIAL_LEGAL")
        db.add_all([*filas, imp, nota])
        db.commit()
        creados = [(IncisoNacional, x.id) for x in filas] + [(ReglaImpuesto, imp.id), (NotaSAC, nota.id)]
    try:
        d, c = _checks(interno)
        refs = lambda k: {h["ref"] for h in c[k]["hallazgos"]}  # noqa: E731
        assert d["estado"] == "CONTAMINATION"
        assert "NI 6402.99.90.00.00" in refs("LINE_NOT_OFFICIAL") and "NI 6402.99.90.00.00" in refs("LINE_SOURCE")
        assert "NI 6402.99.90.00.00" in refs("LINE_COMPANY_BASE")
        assert "SV 6404.19.90.00" in refs("LINE_DUPLICATE")
        assert "SV 9999.99.00.00" in refs("LINE_PARENT")
        assert "GT 6404.19.99" in refs("LINE_LENGTH") and "GT 6404.19.99" in refs("LINE_BASE_NOMENCLATURE")
        assert "GT 6404.19.99" in refs("PUBLISHED_MODIFIED")
        assert "ZZ 6404.19.90.00" in refs("LINE_COUNTRY")
        assert "HN 6404.19.00.00" in refs("LINE_EXPIRED") and c["LINE_EXPIRED"]["estado"] == "VERSION_EXPIRED"
        assert any(r.startswith("TAX-TEST-SIN") for r in refs("TAX_SOURCE")) and any(r.startswith("TAX-TEST-SIN") for r in refs("TAX_INCOMPLETE"))
        assert "6404 X" in refs("NOTE_SUMMARY_AS_OFFICIAL") and "6404 X" in refs("NOTE_SOURCE")
        assert c["LINE_NOT_OFFICIAL"]["estado"] == "CONTAMINATION" and c["TAX_SOURCE"]["estado"] == "SOURCE_MISSING"
        assert d["hallazgos"]["CONTAMINATION"] >= 3 and d["hallazgos"]["ERROR"] >= 4
    finally:
        with SessionLocal() as db:
            for modelo, i in creados:
                x = db.get(modelo, i)
                if x:
                    db.delete(x)
            db.commit()
    # Sin los datos inyectados vuelve a estar limpio
    _, c = _checks(interno)
    assert c["LINE_NOT_OFFICIAL"]["estado"] == "OK"


def test_proveedor_no_audita(vans):
    assert vans.get("/aranceles/oficial/integridad").status_code == 403
