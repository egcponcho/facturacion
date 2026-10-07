"""Auditor de integridad de los datos arancelarios.

Revisa que la capa OFFICIAL TARIFF DATA solo tenga lo que publicó una fuente
oficial (con fuente, versión y vigencia), que la capa de la empresa no la
contamine y que el motor no se haga pasar por ley. No corrige nada: reporta.

Niveles: OK, WARNING, ERROR, SOURCE_MISSING, VERSION_EXPIRED y
CONTAMINATION (dato interno o de la empresa dentro de la capa oficial).
"""
import json
from collections import Counter
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..datos import DEMO
from ..models import (FuenteOficial, HistorialClasificacion, IncisoNacional, NodoArancel, NotaSAC, PaisArancel, ReglaClasificacion,
                      ReglaImpuesto, Regulacion, Usuario, VersionDataset, ahora)
from .common import exigir

NIVELES = ("OK", "WARNING", "ERROR", "SOURCE_MISSING", "VERSION_EXPIRED", "CONTAMINATION")
# Del más grave al menos grave (el estado general es el peor encontrado)
GRAVEDAD = {"CONTAMINATION": 5, "ERROR": 4, "SOURCE_MISSING": 3, "VERSION_EXPIRED": 2, "WARNING": 1, "OK": 0}
DEMO_EMPRESA = DEMO / "historial_empresa_demo.json"
MAX_EJEMPLOS = 50


class _Informe:
    def __init__(self):
        self.checks: dict[str, dict] = {}

    def check(self, codigo: str, titulo: str, capa: str, nivel: str) -> None:
        self.checks[codigo] = {"codigo": codigo, "titulo": titulo, "capa": capa, "nivel": nivel, "total": 0, "hallazgos": []}

    def hallazgo(self, codigo: str, objeto: str, ref: str, mensaje: str, id_: int | None = None) -> None:
        c = self.checks[codigo]
        c["total"] += 1
        if len(c["hallazgos"]) < MAX_EJEMPLOS:
            c["hallazgos"].append({"objeto": objeto, "id": id_, "ref": ref, "mensaje": mensaje})

    def resultado(self) -> dict:
        checks = list(self.checks.values())
        for c in checks:
            c["estado"] = c["nivel"] if c["total"] else "OK"
        resumen = Counter(c["estado"] for c in checks)
        hallazgos = Counter()
        for c in checks:
            if c["total"]:
                hallazgos[c["nivel"]] += c["total"]
        estado = max((c["estado"] for c in checks), key=lambda n: GRAVEDAD[n], default="OK")
        return {"estado": estado, "generado_en": ahora(), "resumen": {n: resumen.get(n, 0) for n in NIVELES},
                "hallazgos": {n: hallazgos.get(n, 0) for n in NIVELES if n != "OK"}, "checks": checks}


def _fmt(c: str) -> str:
    return ".".join([c[:4]] + [c[i:i + 2] for i in range(4, len(c), 2)]) if len(c) > 4 else c


def auditar(db: Session, user: Usuario | None = None, hoy: date | None = None) -> dict:
    if user is not None:
        exigir(user, "aranceles.ver")
    hoy = hoy or date.today()
    inf = _Informe()
    paises = {p.iso: p for p in db.scalars(select(PaisArancel))}
    versiones = {v.id: v for v in db.scalars(select(VersionDataset))}
    fuentes = {f.id: f for f in db.scalars(select(FuenteOficial))}
    # Árbol oficial: subpartidas y líneas de cada versión
    subpartidas: dict[int, set] = {}
    incisos: dict[int, set] = {}
    for vid, cod, nivel in db.execute(select(NodoArancel.version_id, NodoArancel.codigo_norm, NodoArancel.nivel)):
        if nivel == "SUBPARTIDA":
            subpartidas.setdefault(vid, set()).add(cod)
        elif nivel == "INCISO":
            incisos.setdefault(vid, set()).add(cod)
    regionales = [v for v in versiones.values() if (v.ambito or "").upper() == "REGIONAL" and v.id in subpartidas]
    sub_todas = set().union(*subpartidas.values()) if subpartidas else set()
    inc_regionales = set().union(*(incisos.get(v.id, set()) for v in regionales)) if regionales else set()

    # ---- Líneas nacionales (capa oficial) ----------------------------------------------
    inf.check("LINE_SOURCE", "National line without official source or version", "OFFICIAL", "SOURCE_MISSING")
    inf.check("LINE_NOT_OFFICIAL", "National line that does not come from an official source", "OFFICIAL", "CONTAMINATION")
    inf.check("LINE_COMPANY_BASE", "National line that only exists in the company item base", "OFFICIAL", "CONTAMINATION")
    inf.check("LINE_COUNTRY", "National line without a configured country", "OFFICIAL", "ERROR")
    inf.check("LINE_PARENT", "National line that does not hang from its SAC/HS subheading", "OFFICIAL", "ERROR")
    inf.check("LINE_BASE_NOMENCLATURE", "National line missing from its base nomenclature (regional SAC)", "OFFICIAL", "ERROR")
    inf.check("LINE_LENGTH", "National line with an invalid length", "OFFICIAL", "ERROR")
    inf.check("LINE_VERSION_SCOPE", "National line in a version of another country", "OFFICIAL", "ERROR")
    inf.check("LINE_DUPLICATE", "Duplicate national line in the same version", "OFFICIAL", "ERROR")
    inf.check("LINE_EXPIRED", "Active national line past its validity", "OFFICIAL", "VERSION_EXPIRED")
    inf.check("LINE_NO_VALIDITY", "National line without validity", "OFFICIAL", "SOURCE_MISSING")
    inf.check("PUBLISHED_MODIFIED", "Published version modified by hand", "OFFICIAL", "WARNING")

    empresa = set()
    if DEMO_EMPRESA.exists():
        empresa = {(x["pais"], x["codigo"]) for x in json.loads(DEMO_EMPRESA.read_text(encoding="utf-8"))}
    empresa |= {(p, c) for p, c in db.execute(select(HistorialClasificacion.pais, HistorialClasificacion.codigo)
                                              .where(HistorialClasificacion.origen == "IMPORTADO"))}
    vistos = Counter()
    for x in db.scalars(select(IncisoNacional)):
        ref = f"{x.pais} {_fmt(x.codigo)}"
        v = versiones.get(x.version_id)
        vistos[(x.pais, x.codigo, x.version_id)] += 1
        if x.fuente != "oficial":
            inf.hallazgo("LINE_NOT_OFFICIAL", "national_line", ref, f"Marked “{x.fuente}”: only official sources create national lines.", x.id)
        if not x.fuente_id or not x.version_id or not v:
            inf.hallazgo("LINE_SOURCE", "national_line", ref, "No official source or version.", x.id)
        en_arbol = x.codigo in inc_regionales or (v and x.codigo in incisos.get(v.id, set()))
        if (x.pais, x.codigo) in empresa and not en_arbol and not (v and (v.ambito or "").upper() == x.pais and x.fuente_id):
            inf.hallazgo("LINE_COMPANY_BASE", "national_line", ref, "Same code as the company item base and no official publication of it.", x.id)
        p = paises.get(x.pais)
        if not p:
            inf.hallazgo("LINE_COUNTRY", "national_line", ref, f"Country {x.pais} is not configured.", x.id)
        elif msg := p.error_longitud(x.codigo):
            inf.hallazgo("LINE_LENGTH", "national_line", ref, msg, x.id)
        if x.codigo[:6] not in sub_todas or (x.sub6 and x.sub6 != x.codigo[:6]) or (x.codigo_base and not x.codigo.startswith(x.codigo_base)):
            inf.hallazgo("LINE_PARENT", "national_line", ref, "Its first six digits are not an official subheading, or its base code does not match.", x.id)
        if p and p.nivel_base == "SAC10" and v and (v.ambito or "").upper() == "REGIONAL" and x.codigo not in incisos.get(v.id, set()):
            inf.hallazgo("LINE_BASE_NOMENCLATURE", "national_line", ref, f"Not a line of {v.codigo}, which {x.pais} applies as its national tariff.", x.id)
        if v and (v.ambito or "").upper() not in (x.pais, "REGIONAL"):
            inf.hallazgo("LINE_VERSION_SCOPE", "national_line", ref, f"Version {v.codigo} belongs to {v.ambito}.", x.id)
        if not (x.vigente_desde or (v and v.vigente_desde)):
            inf.hallazgo("LINE_NO_VALIDITY", "national_line", ref, "No valid-from date, neither its own nor its version's.", x.id)
        hasta = x.vigente_hasta or (v.vigente_hasta if v else None)
        if x.activo and hasta and hasta < hoy:
            inf.hallazgo("LINE_EXPIRED", "national_line", ref, f"Valid until {hasta.isoformat()}.", x.id)
        if v and v.estado == "PUBLICADA" and x.creado_por:
            inf.hallazgo("PUBLISHED_MODIFIED", "national_line", ref, f"Added by a user to the published version {v.codigo}.", x.id)
    for (pais, cod, vid), n in vistos.items():
        if n > 1:
            inf.hallazgo("LINE_DUPLICATE", "national_line", f"{pais} {_fmt(cod)}", f"{n} rows in version {versiones[vid].codigo if vid in versiones else '—'}.")

    # ---- Versiones, fuentes y países ---------------------------------------------------
    inf.check("VERSION_SOURCE", "Version without official source", "OFFICIAL", "SOURCE_MISSING")
    inf.check("VERSION_OVERLAP", "Published versions of the same scope with overlapping validity", "OFFICIAL", "WARNING")
    inf.check("VERSION_EXPIRED", "Scope whose versions are all past their validity", "OFFICIAL", "VERSION_EXPIRED")
    inf.check("COUNTRY_SOURCE", "Active country pending official source verification", "OFFICIAL", "SOURCE_MISSING")
    inf.check("SOURCE_NOT_TRACEABLE", "Source without document, link or verification", "OFFICIAL", "SOURCE_MISSING")
    inf.check("SOURCE_STALE", "Source not verified in the last year", "OFFICIAL", "WARNING")
    inf.check("VERSION_NO_VALIDITY", "Published version without validity", "OFFICIAL", "SOURCE_MISSING")
    from .oficial import VERIFICACION_MAX_DIAS, problemas_fuente

    usadas = {v.fuente_id for v in versiones.values() if v.estado in ("PUBLICADA", "DINAMICA")}
    for f in fuentes.values():
        if f.id in usadas and (faltas := problemas_fuente(f)):
            inf.hallazgo("SOURCE_NOT_TRACEABLE", "source", f.codigo, " ".join(faltas), f.id)
        elif f.id in usadas and f.verificado_en and (hoy - f.verificado_en).days > VERIFICACION_MAX_DIAS:
            inf.hallazgo("SOURCE_STALE", "source", f.codigo, f"Last verified {f.verificado_en.isoformat()}.", f.id)
    for v in versiones.values():
        if v.estado == "PUBLICADA" and not v.vigente_desde:
            inf.hallazgo("VERSION_NO_VALIDITY", "version", v.codigo, "Published without valid from.", v.id)
    por_ambito: dict[str, list] = {}
    for v in versiones.values():
        if not v.fuente_id or v.fuente_id not in fuentes:
            inf.hallazgo("VERSION_SOURCE", "version", v.codigo, "No official source.", v.id)
        if v.estado in ("PUBLICADA", "DINAMICA"):
            por_ambito.setdefault((v.ambito or "REGIONAL").upper(), []).append(v)
    for ambito, vs in por_ambito.items():
        pub = sorted((v for v in vs if v.estado == "PUBLICADA"), key=lambda v: v.vigente_desde or date.min)
        for a, b in zip(pub, pub[1:]):
            if not a.vigente_hasta or (b.vigente_desde and a.vigente_hasta >= b.vigente_desde):
                inf.hallazgo("VERSION_OVERLAP", "version", f"{a.codigo} / {b.codigo}", f"Both in force at once for {ambito}.", b.id)
        if all(v.vigente_hasta and v.vigente_hasta < hoy for v in vs):
            inf.hallazgo("VERSION_EXPIRED", "version", ambito, "No version in force.", None)
    for p in paises.values():
        if p.activo and not p.fuente_id:
            inf.hallazgo("COUNTRY_SOURCE", "country", p.iso, "Pending official source verification.", p.id)

    # ---- Impuestos y regulaciones -----------------------------------------------------
    inf.check("TAX_SOURCE", "Tax without official source or legal basis", "OFFICIAL", "SOURCE_MISSING")
    inf.check("TAX_INCOMPLETE", "Tax without rate or calculation basis", "OFFICIAL", "ERROR")
    inf.check("REGULATION_SOURCE", "Regulation without official source or legal basis", "OFFICIAL", "SOURCE_MISSING")
    inf.check("REQUIREMENT_EXPIRED", "Active tax or regulation past its validity", "OFFICIAL", "VERSION_EXPIRED")
    for x in db.scalars(select(ReglaImpuesto)):
        ref = f"{x.codigo} ({x.pais} {x.tipo})"
        if not x.fuente_id and not (x.base_legal or "").strip():
            inf.hallazgo("TAX_SOURCE", "tax", ref, "No official source or legal basis.", x.id)
        if x.tasa is None or not (x.base_calculo or "").strip():
            inf.hallazgo("TAX_INCOMPLETE", "tax", ref, "Rate and calculation basis are required.", x.id)
        if x.activo and x.vigente_hasta and x.vigente_hasta < hoy:
            inf.hallazgo("REQUIREMENT_EXPIRED", "tax", ref, f"Valid until {x.vigente_hasta.isoformat()}.", x.id)
    for x in db.scalars(select(Regulacion)):
        ref = f"{x.codigo} ({x.pais})"
        if not x.fuente_id and not (x.base_legal or "").strip():
            inf.hallazgo("REGULATION_SOURCE", "regulation", ref, "No official source or legal basis.", x.id)
        if x.activo and x.vigente_hasta and x.vigente_hasta < hoy:
            inf.hallazgo("REQUIREMENT_EXPIRED", "regulation", ref, f"Valid until {x.vigente_hasta.isoformat()}.", x.id)

    # ---- Notas: texto oficial vs guía --------------------------------------------------
    inf.check("NOTE_SOURCE", "Official legal note without source or version", "OFFICIAL", "SOURCE_MISSING")
    inf.check("NOTE_SUMMARY_AS_OFFICIAL", "Internal summary marked as official legal text", "OFFICIAL", "CONTAMINATION")
    for n in db.scalars(select(NotaSAC)):
        ref = f"{n.codigo} {n.numero}".strip()
        if n.oficial and (not n.version_id or not n.fuente_id):
            inf.hallazgo("NOTE_SOURCE", "note", ref, "Official text without source or version.", n.id)
        if n.oficial and n.ambito == "explicativa":
            inf.hallazgo("NOTE_SUMMARY_AS_OFFICIAL", "note", ref, "Explanatory summaries are classifier guidance, not legal text.", n.id)

    # ---- Motor y empresa no se hacen pasar por ley ------------------------------------
    inf.check("RULE_AS_LEGAL", "Engine or company rule presented as legal", "ENGINE", "CONTAMINATION")
    notas_oficiales = {i for (i,) in db.execute(select(NotaSAC.id).where(NotaSAC.tipo_fuente.in_(NotaSAC.OFICIALES)))}
    for r in db.scalars(select(ReglaClasificacion).where(ReglaClasificacion.tipo_fuente.in_(("LEGAL_NOTE", "NATIONAL_TARIFF", "LEARNED")))):
        if r.tipo_regla == "NATIONAL_SELECT":
            inf.hallazgo("RULE_AS_LEGAL", "rule", r.codigo, f"National selection conditions marked {r.tipo_fuente}: they are engine or company "
                         "configuration, not legal text.", r.id)
        elif r.tipo_fuente == "LEGAL_NOTE" and r.nota_id not in notas_oficiales:
            inf.hallazgo("RULE_AS_LEGAL", "rule", r.codigo, "Legal rule that does not cite an official legal text.", r.id)
        elif r.tipo_fuente == "LEARNED":
            inf.hallazgo("RULE_AS_LEGAL", "rule", r.codigo, "Learned rule: company knowledge belongs in the classification history.", r.id)
    return inf.resultado()
