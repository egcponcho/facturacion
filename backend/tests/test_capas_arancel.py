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


QUIMICAS = {"inorganic_chemical", "organic_chemical", "acid", "base_alkali", "salt", "solvent", "alcohol", "polymer_resin", "rubber_preparation",
            "dye", "pigment", "paint_coating", "ink", "adhesive", "surfactant", "detergent_cleaning", "lubricant", "wax", "laboratory_reagent",
            "chemical_preparation"}
MATERIAS = {"textile_fiber", "staple_fiber", "filament", "yarn", "sewing_thread", "woven_fabric", "knitted_fabric", "nonwoven", "felt",
            "coated_fabric", "laminated_fabric", "leather", "split_leather", "synthetic_leather", "plastic_resin", "plastic_primary_form",
            "plastic_sheet", "plastic_film", "plastic_profile", "plastic_foam", "natural_rubber", "synthetic_rubber", "rubber_compound",
            "rubber_sheet", "paper", "paperboard", "metal_sheet", "metal_wire", "metal_profile", "metal_component"}


def _sesion(api, **kw):
    r = api.post("/clasificacion/sesion", {"paises": False, **kw})
    assert r.status_code == 200, r.text
    return r.json()


def test_chemical_categories_are_configurable(interno):
    cats = {c["codigo"]: c for c in interno.get("/aranceles/categorias").json()}
    assert QUIMICAS <= set(cats) and all(cats[c]["dominio"] == "CHEMICALS" for c in QUIMICAS)
    # Cada categoría decide qué preguntar (dinámico, no siempre obligatorio)
    d = _sesion(interno, categoria="alcohol", texto="alcohol etílico")
    campos = {c["codigo"]: c for c in d["campos"]}
    assert campos["alcohol_type"]["modo"] == "REQUIRE" and "alcohol_strength" not in campos  # depende del tipo de alcohol
    d = _sesion(interno, categoria="alcohol", texto="alcohol etílico", respuestas={"alcohol_type": "ethanol"})
    assert "alcohol_strength" in {c["codigo"] for c in d["campos"]}
    d = _sesion(interno, categoria="adhesive", texto="pegamento")
    assert {"adhesive_base", "retail_packaging"} <= {f["campo"] for f in d["faltantes"]} and "dye_class" not in {c["codigo"] for c in d["campos"]}
    # Una categoría nueva y su pregunta se crean como configuración, sin programar
    r = interno.post("/aranceles/categorias", {"codigo": "fragrance_compound", "nombre": "Fragrance compound", "dominio": "CHEMICALS",
                                               "patrones": [{"re": "\\b(fragrance compound|compuesto de fragancia)\\b", "prioridad": 70}],
                                               "terminos": "mezclas de sustancias odoríferas"})
    assert r.status_code == 200, r.text
    attr = next(a for a in interno.get("/aranceles/atributos", params={"q": "main_ingredient"}).json()["items"] if a["codigo"] == "main_ingredient")
    assert interno.post(f"/aranceles/atributos/{attr['id']}/ambitos", {"tipo_ambito": "CATEGORY", "codigo_ambito": "fragrance_compound",
                                                                         "modo": "REQUIRE"}).status_code == 200
    d = _sesion(interno, texto="fragrance compound for soaps")
    assert d["categoria"]["codigo"] == "fragrance_compound" and "main_ingredient" in {f["campo"] for f in d["faltantes"]}


def test_raw_material_categories_are_configurable(interno):
    cats = {c["codigo"]: c for c in interno.get("/aranceles/categorias").json()}
    assert MATERIAS <= set(cats) and all(cats[c]["dominio"] == "RAW_MATERIALS" for c in MATERIAS)
    # Hilado: fibra, %, filamento o discontinuo, presentación; textured solo si es filamento
    d = _sesion(interno, texto="polyester yarn")
    assert d["categoria"]["codigo"] == "yarn"
    assert {"fiber", "fiber_pct", "filament_or_staple", "put_up_retail"} <= {f["campo"] for f in d["faltantes"]}
    assert "textured" not in {c["codigo"] for c in d["campos"]}
    d = _sesion(interno, texto="polyester yarn", respuestas={"filament_or_staple": "filament"})
    assert "textured" in {c["codigo"] for c in d["campos"]}
    # Tela: tejido, composición, gramaje, acabado; resina: polímero y forma primaria; película: espesor, celular, reforzada
    assert {"weave", "fabric_weight", "fabric_finish"} <= {f["campo"] for f in _sesion(interno, categoria="woven_fabric", texto="tela")["faltantes"]}
    assert {"polymer_type", "primary_form"} <= {f["campo"] for f in _sesion(interno, categoria="plastic_resin", texto="resina")["faltantes"]}
    assert {"thickness", "cellular", "reinforced"} <= {f["campo"] for f in _sesion(interno, categoria="plastic_film", texto="film")["faltantes"]}
    # Apagar una pregunta en una categoría es configuración (sin programar)
    attr = next(a for a in interno.get("/aranceles/atributos", params={"q": "fabric_weight"}).json()["items"] if a["codigo"] == "fabric_weight")
    det = interno.get(f"/aranceles/atributos/{attr['id']}").json()
    amb = next(x for x in det["ambitos"] if x["codigo_ambito"] == "woven_fabric")
    assert interno.patch(f"/aranceles/atributos/{attr['id']}/ambitos/{amb['id']}", {"modo": "HIDE"}).status_code == 200
    assert "fabric_weight" not in {f["campo"] for f in _sesion(interno, categoria="woven_fabric", texto="tela")["faltantes"]}
    interno.patch(f"/aranceles/atributos/{attr['id']}/ambitos/{amb['id']}", {"modo": "REQUIRE"})


def test_same_engine_classifies_footwear_chemical_and_raw_material(interno):
    calzado = _sesion(interno, categoria="calzado", ficha={"comp": {"corte": "100% leather", "suela": "100% rubber"}, "estiloCalz": "tenis",
                                                            "altura": "bajo", "genero": "U", "edadNac": "adulto", "puntera": "ninguna"})
    quimico = _sesion(interno, texto="dióxido de titanio", categoria="pigment", respuestas={"pigment_type": "titanium_dioxide"})
    materia = _sesion(interno, texto="PVC resin pellets", respuestas={"polymer_type": "pvc", "primary_form": "granules"})
    assert calzado["hs6"].startswith("6403") and quimico["hs6"].startswith("3206") and materia["hs6"].startswith("3904")
    # La misma forma de respuesta y la misma traza de reglas del sistema
    for d in (calzado, quimico, materia):
        assert {"hs6", "candidatos", "preguntas", "faltantes", "reglas", "evidencia", "version"} <= set(d)
        assert any(t["regla"] == "R-SYS-001" for t in d["reglas"])
    assert quimico["categoria"]["dominio"] == "CHEMICALS" and materia["categoria"]["dominio"] == "RAW_MATERIALS"


def test_domain_does_not_define_tariff_code_directly(interno):
    from app.services.motor_clasificacion import codigo_existe

    cats = interno.get("/aranceles/categorias").json()
    # Las categorías técnicas no traen códigos ni capítulos fijos: solo deciden qué preguntar
    assert all(not c["capitulos"] for c in cats if c["codigo"] in QUIMICAS | MATERIAS)
    for kw in ({"texto": "pegamento de contacto", "respuestas": {"adhesive_base": "rubber"}},
               {"texto": "woven fabric", "categoria": "woven_fabric", "respuestas": {"fiber": "cotton", "weave": "twill"}}):
        d = _sesion(interno, **kw)
        # Todo candidato existe en el árbol oficial vigente; nada sale de la categoría
        with SessionLocal() as db:
            assert d["candidatos"] and all(codigo_existe(db, c["codigo"]) for c in d["candidatos"])
        assert d["requiere_revision"] or d["confianza"] != "high"
    # El mismo texto en otro dominio no toma una categoría ajena
    d = _sesion(interno, texto="ácido acético", dominio="RAW_MATERIALS")
    assert (d.get("categoria") or {}).get("dominio") != "CHEMICALS"


def test_sds_tds_are_technical_evidence_not_tariff_source(interno):
    import io
    import json

    p = interno.get("/productos", params={"size": 5}).json()["items"][0]

    def subir(datos, tipo="SDS"):
        return interno.c.post(f"/api/productos/{p['id']}/documentos", headers=interno.h,
                              data={"tipo": tipo, "datos": json.dumps(datos), "emisor": "Lab X"},
                              files={"archivo": ("sds.pdf", io.BytesIO(b"%PDF-1.4 prueba"), "application/pdf")})

    # Un código arancelario no se toma de una ficha técnica
    r = subir({"cas_number": "64-19-7", "hs_code": "2915.21"})
    assert r.status_code == 422 and r.json()["codigo"] == "no_es_fuente_arancelaria"
    assert subir({"no_existe": 1}).status_code == 422
    assert subir({}, tipo="XYZ").status_code == 422
    r = subir({"cas_number": "64-19-7", "physical_state": "LIQUID", "density": 1.05})
    assert r.status_code == 200, r.text
    det = interno.get(f"/productos/{p['id']}").json()
    assert det["documentos"][0]["tipo"] == "SDS" and det["documentos"][0]["datos"]["cas_number"] == "64-19-7"
    # Sus datos son hechos del producto para el motor (sin pisar lo que dice la ficha)
    s = _sesion(interno, producto_id=p["id"], categoria="acid", texto="ácido acético")
    assert s["hechos"].get("cas_number") == "64-19-7" and s["hechos"].get("physical_state") == "LIQUID"
    s = _sesion(interno, producto_id=p["id"], categoria="acid", texto="ácido acético", respuestas={"physical_state": "SOLID"})
    assert s["hechos"].get("physical_state") == "SOLID"
    assert interno.get(f"/productos/documentos/{det['documentos'][0]['id']}").content.startswith(b"%PDF")
    assert interno.delete_(f"/productos/{p['id']}/documentos/{det['documentos'][0]['id']}").status_code == 200


def test_company_history_only_affects_ranking(interno):
    """640391 tiene dos líneas oficiales en GT sin condiciones que las separen:
    sin historial hay que elegir; con historial se prefiere una, pero las
    opciones siguen siendo las mismas líneas oficiales y la confianza legal no cambia."""
    with SessionLocal() as db:
        for h in db.scalars(select(HistorialClasificacion).where(HistorialClasificacion.sub6 == "640391")):
            db.delete(h)
        db.commit()
    entrada = {"categoria": "calzado", "codigo_final": "640391", "ficha": {"comp": {"corte": "100% leather", "suela": "100% rubber"}}}

    def gt():
        d = interno.post("/clasificacion/sesion", entrada).json()
        return d, next(p for p in d["clasificacion"]["paises"] if p["pais"] == "GT")

    antes, p0 = gt()
    assert p0["estado"] == "elegir" and sorted(o["codigo"] for o in p0["opciones"]) == ["6403911000", "6403919000"]
    # La empresa recuerda una de las líneas oficiales para productos así
    r = interno.post("/clasificacion/incisos", {"pais": "GT", "codigo": "6403.91.90.00", "cond": {}})
    assert r.status_code == 200, r.text
    despues, p1 = gt()
    assert p1["estado"] == "historial" and p1["codigo"] == "6403919000" and p1["historial"]["historical_confidence"]
    # Mismas opciones oficiales, misma subpartida y misma confianza legal: el historial solo ordenó
    assert sorted(o["codigo"] for o in p1["opciones"]) == sorted(o["codigo"] for o in p0["opciones"])
    assert despues["hs6"] == antes["hs6"] and despues["legal_confidence"] == antes["legal_confidence"]
    assert {"legal_confidence", "historical_confidence"} <= set(despues)
    # Las capas se consultan por separado; quitar la entrada del historial vuelve a pedir la elección
    hist = interno.get("/conocimiento/historial", params={"pais": "GT", "q": "6403919000"}).json()["items"]
    assert hist and all(h["linea_oficial"] for h in hist)
    for h in hist:
        assert interno.delete_(f"/conocimiento/historial/{h['id']}").status_code == 200
    assert gt()[1]["estado"] == "elegir"
    assert interno.get("/clasificacion/configuracion").json()["capa"] == "CLASSIFICATION_ENGINE"
    assert interno.get("/conocimiento").json()["palabras"] >= 1
