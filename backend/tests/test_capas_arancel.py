"""Separación de capas: solo fuentes oficiales determinan qué códigos, textos
legales, DAI, impuestos y regulaciones existen. El motor interpreta y la empresa
aporta historial, pero ninguno de los dos crea ni modifica datos oficiales."""
from sqlalchemy import func, select

from app.core.db import SessionLocal
from app.modelos import HistorialClasificacion, IncisoNacional, NotaSAC, ReglaClasificacion, ReglaImpuesto, Regulacion


def test_official_tariff_contains_only_official_sources(interno):
    with SessionLocal() as db:
        lineas = db.scalars(select(IncisoNacional)).all()
        assert lineas
        assert all(x.fuente == "oficial" and x.fuente_id and x.version_id for x in lineas)
        # Ninguna línea viene del historial de la empresa (sus códigos de NI, CR y PA no existen como líneas)
        assert not {x.pais for x in lineas} & {"NI", "CR", "PA"}


def test_every_official_line_has_version_and_source(interno):
    from app.modelos import FuenteOficial, VersionDataset

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
    from app.modulos.clasificacion.motor_clasificacion import CAPA

    with SessionLocal() as db:
        reglas = db.scalars(select(ReglaClasificacion).where(ReglaClasificacion.inciso_id.is_not(None))).all()
        # Las condiciones de selección nacional son del motor (interpretación del texto) o de la empresa, nunca ley
        assert reglas and all(r.tipo_fuente in ("CLASSIFIER", "MANUAL") for r in reglas)
        assert all(CAPA.get(r.tipo_fuente) != "LEGAL" for r in reglas)
        # Las condiciones de la base de artículos de la empresa están en el historial, no en las líneas
        hist = db.scalars(select(HistorialClasificacion).where(HistorialClasificacion.origen == "IMPORTADO")).all()
        assert any("estilo_calzado" in (h.condiciones or {}) or "puntera" in (h.condiciones or {}) for h in hist)
        # Las del motor (CLASSIFIER) son exactamente lo que el clasificador lee del texto oficial del ACI
        import json
        from pathlib import Path

        aci = json.loads((Path(__file__).parents[1] / "app/data/motor/interpretacion_aci.json").read_text())["condiciones"]
        # El archivo oficial del ACI no trae interpretaciones del clasificador
        assert not any("cond" in x for x in json.loads((Path(__file__).parents[1] / "app/data/oficial/aci_incisos.json").read_text()))
        for x in db.scalars(select(IncisoNacional)):
            if x.regla and x.regla.tipo_fuente == "CLASSIFIER":
                assert x.cond == aci.get(x.codigo), (x.pais, x.codigo, x.cond)


def test_official_tax_requires_source_or_legal_basis(interno):
    base = {"pais": "SV", "patron": "6404", "tipo": "SELECTIVO", "tasa": 5, "base_calculo": "CIF", "vigente_desde": "2026-01-01"}
    with SessionLocal() as db:
        from app.modelos import PaisArancel

        sv = db.scalar(select(PaisArancel).where(PaisArancel.iso == "SV"))
        tiene_fuente = bool(sv.fuente_impuestos_id)
    r = interno.post("/aranceles/impuestos", base)
    assert (r.status_code == 200) == tiene_fuente, r.text  # la fuente de impuestos configurada del país sirve como fuente
    if not tiene_fuente:
        assert "official source or its legal basis" in r.json()["mensaje"]
    assert interno.post("/aranceles/impuestos", {**base, "base_legal": "Ley de prueba, art. 1"}).status_code == 200
    # Sin tasa o sin base de cálculo no es un impuesto completo
    assert interno.post("/aranceles/impuestos", {**base, "tasa": None, "base_legal": "Ley"}).status_code == 422
    # Ni sin vigencia: nunca se supone desde cuándo rige
    r = interno.post("/aranceles/impuestos", {**base, "vigente_desde": None, "base_legal": "Ley"})
    assert r.status_code == 422 and r.json()["codigo"] == "sin_vigencia"
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


QUIMICAS = {"quimico_inorganico", "quimico_organico", "colorante", "pigmento", "pintura", "tinta", "adhesivo", "tensoactivo", "jabon",
            "lubricante", "cera", "betun", "apresto", "aditivo_polimero", "disolvente", "biocida", "reactivo", "preparacion_quimica"}
MATERIAS = {"fibra_textil", "hilado", "tejido_plano", "tejido_punto", "no_tejido", "tela_recubierta", "cinta_etiqueta", "avio",
            "resina_plastica", "lamina_plastica", "caucho", "cuero", "cuero_sintetico", "papel_carton", "metal"}


def _sesion(api, **kw):
    r = api.post("/clasificacion/sesion", {"paises": False, **kw})
    assert r.status_code == 200, r.text
    return r.json()


def test_chemical_categories_are_configurable(interno):
    cats = {c["codigo"]: c for c in interno.get("/aranceles/categorias").json()}
    assert QUIMICAS <= set(cats) and all(cats[c]["dominio"] == "CHEMICALS" for c in QUIMICAS)
    # Cada categoría decide qué preguntar (dinámico, no siempre obligatorio)
    d = _sesion(interno, categoria="quimico_organico", texto="acetona", ficha={"compuesto_definido": False})
    assert "grupo_organico" not in {c["codigo"] for c in d["campos"]}  # depende de que sea un compuesto definido
    d = _sesion(interno, categoria="quimico_organico", texto="acetona", respuestas={"compuesto_definido": True})
    assert next(c for c in d["campos"] if c["codigo"] == "grupo_organico")["modo"] == "REQUIRE"
    d = _sesion(interno, categoria="adhesivo", texto="pegamento")
    assert "base_adhesivo" in {f["campo"] for f in d["faltantes"]} and "clase_colorante" not in {c["codigo"] for c in d["campos"]}
    # Una categoría nueva y su pregunta se crean como configuración, sin programar
    r = interno.post("/aranceles/categorias", {"codigo": "fragrance_compound", "nombre": "Fragrance compound", "dominio": "CHEMICALS",
                                               "patrones": [{"re": "\\b(fragrance compound|compuesto de fragancia)\\b", "prioridad": 70}],
                                               "terminos": "mezclas de sustancias odoríferas"})
    assert r.status_code == 200, r.text
    attr = next(a for a in interno.get("/aranceles/atributos", params={"q": "componentes"}).json()["items"] if a["codigo"] == "componentes")
    assert interno.post(f"/aranceles/atributos/{attr['id']}/ambitos", {"tipo_ambito": "CATEGORY", "codigo_ambito": "fragrance_compound",
                                                                         "modo": "REQUIRE"}).status_code == 200
    d = _sesion(interno, texto="fragrance compound for soaps")
    assert d["categoria"]["codigo"] == "fragrance_compound" and "componentes" in {c["codigo"] for c in d["campos"]}


def test_raw_material_categories_are_configurable(interno):
    cats = {c["codigo"]: c for c in interno.get("/aranceles/categorias").json()}
    assert MATERIAS <= set(cats) and all(cats[c]["dominio"] == "RAW_MATERIALS" for c in MATERIAS)
    # Hilado: la fibra sale de la composición; filamento o discontinua solo si es sintética o artificial
    d = _sesion(interno, texto="polyester yarn", ficha={"comp": {"material": "100% polyester"}})
    assert d["categoria"]["codigo"] == "hilado" and d["hechos"]["fibra"] == "sintetica"
    assert "filamento" in {f["campo"] for f in d["faltantes"]}
    d = _sesion(interno, texto="cotton yarn", ficha={"comp": {"material": "100% cotton"}})
    assert "filamento" not in {c["codigo"] for c in d["campos"]}
    d = _sesion(interno, texto="polyester yarn", ficha={"comp": {"material": "100% polyester"}}, respuestas={"filamento": "filamento"})
    assert d["hs6"][:4] in ("5402", "5404")
    # Tela: peso por m²; resina y lámina: el polímero
    assert "peso_g_m2" in {f["campo"] for f in _sesion(interno, categoria="tejido_plano", texto="tela")["faltantes"]}
    assert "polimero" in {f["campo"] for f in _sesion(interno, categoria="resina_plastica", texto="resina")["faltantes"]}
    assert "polimero" in {f["campo"] for f in _sesion(interno, categoria="lamina_plastica", texto="film")["faltantes"]}
    # Apagar una pregunta en una categoría es configuración (sin programar)
    attr = next(a for a in interno.get("/aranceles/atributos", params={"q": "peso_g_m2"}).json()["items"] if a["codigo"] == "peso_g_m2")
    det = interno.get(f"/aranceles/atributos/{attr['id']}").json()
    amb = next(x for x in det["ambitos"] if x["codigo_ambito"] == "tejido_plano")
    assert interno.patch(f"/aranceles/atributos/{attr['id']}/ambitos/{amb['id']}", {"modo": "HIDE"}).status_code == 200
    # Oculta deja de ser obligatoria; solo se pregunta si de verdad decide entre los candidatos que quedan
    campo = next((c for c in _sesion(interno, categoria="tejido_plano", texto="tela")["campos"] if c["codigo"] == "peso_g_m2"), None)
    assert campo is None or (campo["modo"] != "REQUIRE" and campo["discrimina"])
    interno.patch(f"/aranceles/atributos/{attr['id']}/ambitos/{amb['id']}", {"modo": "REQUIRE"})


def test_same_engine_classifies_footwear_chemical_and_raw_material(interno):
    calzado = _sesion(interno, categoria="calzado", ficha={"comp": {"corte": "100% leather", "suela": "100% rubber"}, "estilo_calzado": "tenis",
                                                            "altura": "bajo", "genero": "U", "edad": "adulto"})
    quimico = _sesion(interno, texto="dióxido de titanio", categoria="pigmento", respuestas={"tipo_pigmento": "dioxido_titanio"})
    materia = _sesion(interno, texto="PVC resin pellets", categoria="resina_plastica", respuestas={"polimero": "pvc"})
    assert calzado["hs6"] == "640399" and quimico["hs6"] == "320611" and materia["hs6"].startswith("3904")
    # La misma forma de respuesta y la misma traza de reglas del sistema
    for d in (calzado, quimico, materia):
        assert {"hs6", "candidatos", "preguntas", "faltantes", "reglas", "evidencia", "version"} <= set(d)
        assert any(t["regla"] == "R-SYS-001" for t in d["reglas"])
    assert quimico["categoria"]["dominio"] == "CHEMICALS" and materia["categoria"]["dominio"] == "RAW_MATERIALS"


def test_domain_does_not_define_tariff_code_directly(interno):
    from app.modulos.clasificacion.motor_clasificacion import codigo_existe

    cats = interno.get("/aranceles/categorias").json()
    # Una categoría no trae códigos: sus capítulos solo sirven para avisar si un código no le corresponde
    assert all("codigos" not in c for c in cats)
    for kw in ({"texto": "pegamento de contacto"},
               {"texto": "woven fabric", "categoria": "tejido_plano", "ficha": {"comp": {"material": "100% cotton"}}}):
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
    r = subir({"cas": "64-19-7", "hs_code": "2915.21"})
    assert r.status_code == 422 and r.json()["codigo"] == "no_es_fuente_arancelaria"
    assert subir({"no_existe": 1}).status_code == 422
    assert subir({}, tipo="XYZ").status_code == 422
    r = subir({"cas": "64-19-7", "estado_fisico": "liquido", "densidad": 1.05})
    assert r.status_code == 200, r.text
    det = interno.get(f"/productos/{p['id']}").json()
    assert det["documentos"][0]["tipo"] == "SDS" and det["documentos"][0]["datos"]["cas"] == "64-19-7"
    # Sus datos son hechos del producto para el motor (sin pisar lo que dice la ficha)
    s = _sesion(interno, producto_id=p["id"], categoria="quimico_organico", texto="ácido acético")
    assert s["hechos"].get("cas") == "64-19-7" and s["ficha"].get("estado_fisico") == "liquido"
    s = _sesion(interno, producto_id=p["id"], categoria="quimico_organico", texto="ácido acético", respuestas={"estado_fisico": "solido"})
    assert s["ficha"].get("estado_fisico") == "solido"
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


def _paquete(api, hojas):
    import io

    from openpyxl import Workbook

    wb = Workbook()
    wb.remove(wb.active)
    for nombre, filas in hojas.items():
        ws = wb.create_sheet(nombre)
        for f in filas:
            ws.append(f)
    b = io.BytesIO()
    wb.save(b)
    return api.c.post("/api/aranceles/oficial/importar", headers=api.h,
                      files={"archivo": ("p.xlsx", io.BytesIO(b.getvalue()), "application/octet-stream")})


def test_official_source_requires_document_version_validity_and_verification(interno):
    enc_src = ["Source ID", "Country/Region", "Authority", "Official dataset", "Use", "Official URL", "Access mode", "Authentication",
               "Version/status note", "Verification"]
    enc_ver = ["Version ID", "Dataset", "Version label", "Status", "Valid from", "Valid to", "Source ID"]
    # Una fuente sin verificar no respalda una versión publicada: el lote entero se rechaza
    r = _paquete(interno, {"Sources": [enc_src, ["SRC-SV-TEST", "SV", "DGA", "Arancel de prueba", None, "https://example.gob.sv/arancel",
                                                 None, None, None, "Pending"]],
                           "Versions": [enc_ver, ["SV-TEST-1", "SV tariff", "2026", "Published", "2026-01-01", None, "SRC-SV-TEST"]]})
    assert r.status_code == 422 and r.json()["codigo"] == "lote_con_errores"
    assert any("has not been verified" in e["mensaje"] for e in r.json()["detalle"])
    # Ni una versión publicada sin vigencia
    r = _paquete(interno, {"Versions": [enc_ver, ["SV-TEST-2", "SV tariff", "2026", "Published", None, None, "SRC-SV-DGA"]]})
    assert r.status_code == 422 and any("without its validity" in e["mensaje"] for e in r.json()["detalle"])
    # La fuente sin verificar se carga sola (no respalda nada todavía) y se verifica: documento, enlace, fecha y quién
    assert _paquete(interno, {"Sources": [enc_src, ["SRC-SV-TEST", "SV", "DGA", "Arancel de prueba", None, "https://example.gob.sv/arancel",
                                                    None, None, None, "Pending"]]}).status_code == 200
    fuentes = {f["codigo"]: f for f in interno.get("/aranceles/oficial/fuentes").json()["fuentes"]}
    f = fuentes["SRC-SV-TEST"]
    assert f["problemas"] and not f["verificado_en"] and not fuentes["SRC-SIECA-ACI"]["problemas"]
    assert interno.post(f"/aranceles/oficial/fuentes/{f['id']}/verificar", {"verificado_en": "2999-01-01"}).status_code == 422
    r = interno.post(f"/aranceles/oficial/fuentes/{f['id']}/verificar", {"documento": "Arancel SV 2026, Diario Oficial tomo 450"})
    assert r.status_code == 200 and r.json()["verificado_en"] and r.json()["verificado_por"] and not r.json()["problemas"]
    assert _paquete(interno, {"Versions": [enc_ver, ["SV-TEST-1", "SV tariff", "2026", "Draft", "2026-01-01", None, "SRC-SV-TEST"]]}).status_code == 200
    # Una línea en una versión dinámica sin fecha necesita su vigencia; con ella queda trazable
    r = interno.post("/aranceles/codigos", {"pais": "CR", "codigo": "6404.19.90.00.77", "fuente": "SRC-CR-ATENA", "version": "CR-ATENA"})
    assert r.status_code == 422 and r.json()["codigo"] == "sin_vigencia"
    r = interno.post("/aranceles/codigos", {"pais": "CR", "codigo": "6404.19.90.00.77", "fuente": "SRC-CR-ATENA", "version": "CR-ATENA",
                                            "vigente_desde": "2026-02-01"})
    assert r.status_code == 200, r.text
    with SessionLocal() as db:
        x = db.get(IncisoNacional, r.json()["id"])
        assert str(x.vigente_desde) == "2026-02-01" and x.fuente_id and x.version_id


def test_history_never_creates_candidates(interno, monkeypatch):
    """El historial solo refuerza candidatos que ya salieron del árbol oficial y de las reglas."""
    from app.modulos.clasificacion import motor_clasificacion as mc

    entrada = {"categoria": "calzado", "ficha": {"comp": {"corte": "100% leather", "suela": "100% rubber"}, "estilo_calzado": "tenis",
                                                 "altura": "bajo", "genero": "U", "edad": "adulto", "uso_deportivo": "no"}}
    with SessionLocal() as db:
        limpio = mc.clasificar_producto(db, entrada, paises=False)
    original = mc._historial

    def con_historial(db, ent, categoria, perfil):
        h = original(db, ent, categoria, perfil)
        h["tally"] = {"950300": 50, limpio["candidatos"][-1]["codigo"]: 50}  # un juguete (ajeno) y un candidato real
        return h

    monkeypatch.setattr(mc, "_historial", con_historial)
    with SessionLocal() as db:
        r = mc.clasificar_producto(db, entrada, paises=False)
    assert "950300" not in {c["codigo"] for c in r["candidatos"]}
    assert {c["codigo"] for c in r["candidatos"]} == {c["codigo"] for c in limpio["candidatos"]}
    assert r["legal_confidence"] == limpio["legal_confidence"]


def test_uncertain_cases_are_never_approved_automatically(interno, monkeypatch):
    from app.modulos.clasificacion import motor_clasificacion as mc

    pend = [p for p in interno.get("/productos", params={"estado": "pendientes", "size": 100}).json()["items"]
            if p["estado"] == "sugerida" and p["ficha_completa"]]
    assert pend
    p = pend[0]
    original = mc.clasificar_producto

    def incierto(db, entrada, **kw):
        r = original(db, entrada, **kw)
        return {**r, "requiere_revision": True, "revision_por": ["Several plausible candidates remain."]}

    monkeypatch.setattr(mc, "clasificar_producto", incierto)
    r = interno.post("/productos/aprobar", {"ids": [p["id"]]}).json()
    assert r["aprobados"] == 0 and "specialist review" in r["errores"][0]["mensaje"]
    assert interno.get(f"/productos/{p['id']}").json()["estado"] == "sugerida"


def test_history_preferred_national_line_needs_confirmation(interno):
    """640399 tiene dos líneas oficiales en GT sin condiciones: la que solo el historial
    prefiere es una sugerencia; al aprobar, una persona la confirma."""
    m = {x["codigo"]: x["id"] for x in interno.get("/catalogos/marcas", params={"size": 100}).json()["items"]}
    g = {x["codigo"]: x["id"] for x in interno.get("/catalogos/grupos").json()["items"]}
    pv = {x["codigo"]: x["id"] for x in interno.get("/catalogos/proveedores").json()["items"]}
    r = interno.post("/catalogos/genericos", {"generico": "30077702", "estilo": "VNHIST01", "color": "Black", "marca_id": m["VANS"],
                                              "grupo_id": g["CALZ-CAS"], "proveedor_id": pv["VANS"], "unidad": "PAR", "nombre": "Leather court shoe",
                                              "tallas": [{"talla": "8"}]})
    assert r.status_code == 200, r.text
    p = next(x for x in interno.get("/productos", params={"q": "VNHIST01"}).json()["items"] if x["estilo"] == "VNHIST01")
    det = interno.get(f"/productos/{p['id']}").json()
    det = interno.put(f"/productos/{p['id']}/ficha", {"version": det["version"], "tipo": "calzado", "pais_origen": "VN", "ficha": {
        "comp": {"corte": "100% leather", "suela": "100% rubber"}, "estilo_calzado": "tenis", "altura": "bajo", "genero": "U", "edad": "adulto"}}).json()
    assert det["sugerido"].replace(".", "") == "640399", det["sugerido"]
    with SessionLocal() as db:
        for h in db.scalars(select(HistorialClasificacion).where(HistorialClasificacion.sub6 == "640399")):
            db.delete(h)
        db.commit()
    assert interno.post("/clasificacion/incisos", {"pais": "GT", "codigo": "6403.99.90.00", "cond": {}}).status_code == 200
    # Aprobar no exige las líneas nacionales (la OC y la factura llevan 6 dígitos): la que solo
    # el historial prefiere queda como sugerencia, sin confirmar
    r = interno.post(f"/productos/{p['id']}/aprobar", {"version": det["version"], "codigo": "640399"})
    assert r.status_code == 200, r.text
    gt = r.json()["partidas"].get("GT")
    assert not gt or gt["estado"] != "ok"
    ops = interno.get(f"/productos/{p['id']}/partidas/GT").json()
    assert sorted(o["codigo"] for o in ops["opciones"]) == ["6403991000", "6403999000"]
    # Una línea que no es oficial para la subpartida no se confirma
    r = interno.post(f"/productos/{p['id']}/partidas/GT", {"codigo": "6404199000"})
    assert r.status_code == 422 and r.json()["codigo"] == "codigo_nacional_invalido", r.text
    # Confirmada por una persona, queda como línea oficial confirmada
    r = interno.post(f"/productos/{p['id']}/partidas/GT", {"codigo": "6403.99.90.00"})
    assert r.status_code == 200, r.text
    gt = r.json()["partidas"]["GT"]
    assert gt["codigo"].replace(".", "") == "6403999000" and gt["estado"] == "ok" and gt["manual"]


def test_old_engine_routes_are_gone(interno):
    """Un solo motor: no quedan rutas del clasificador anterior."""
    rutas = set(interno.c.get("/openapi.json").json()["paths"])
    assert "/api/clasificacion/sesion" in rutas
    assert not [r for r in rutas if r.startswith(("/api/clasificacion/generico", "/api/clasificacion/sac", "/api/clasificar"))]
    assert interno.post("/clasificacion/generico", {"texto": "x"}).status_code in (404, 405)


def test_documents_use_six_digits_never_the_projected_destination(interno):
    """El destino de la OC es solo una proyección: la OC y la factura llevan la
    subpartida de 6 dígitos aprobada, nunca la línea nacional del país ni el SAC."""
    from app.modelos import FacturaLinea, Producto
    from app.modulos.productos.productos import partida_para

    with SessionLocal() as db:
        p = next(x for x in db.scalars(select(Producto)) if x.aprobado and x.partidas)
        assert partida_para(p) == f"{p.codigo[:4]}.{p.codigo[4:6]}"
        no_aprobado = next((x for x in db.scalars(select(Producto)) if not x.aprobado), None)
        if no_aprobado:
            assert partida_para(no_aprobado) is None
        for l in db.scalars(select(FacturaLinea).where(FacturaLinea.partida_arancelaria.is_not(None))):
            assert len(l.partida_arancelaria.replace(".", "")) == 6, l.partida_arancelaria


def test_una_linea_nacional_sin_fuente_no_se_edita_ni_se_duplica(interno):
    """Una línea sin fuente oficial (de una versión anterior) no se edita: antes
    se creaba otra línea «oficial» al lado en vez de cambiarla."""
    with SessionLocal() as db:
        x = IncisoNacional(pais="GT", codigo="6404199098", sub6="640419", fuente="empresa", descripcion="Antigua", activo=True)
        db.add(x)
        db.commit()
        iid = x.id
    try:
        r = interno.put(f"/aranceles/codigos/{iid}", {"pais": "GT", "codigo": "6404.19.90.98", "descripcion": "Cambio", "cond": {}, "prio": 0})
        assert r.status_code == 409 and r.json()["codigo"] == "sin_fuente", r.text
        with SessionLocal() as db:
            assert db.scalar(select(func.count()).select_from(IncisoNacional)
                             .where(IncisoNacional.pais == "GT", IncisoNacional.codigo == "6404199098")) == 1
    finally:
        with SessionLocal() as db:
            db.delete(db.get(IncisoNacional, iid))
            db.commit()
