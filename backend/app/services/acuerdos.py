"""Acuerdos comerciales vigentes para los países destino.

Referencia para saber, según el país de origen del producto, a qué destinos
entra con preferencia arancelaria y qué prueba de origen (CO) se pide. Es una
base de consulta: se edita en Master data → Trade agreements.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import AcuerdoComercial

UE = ("AT,BE,BG,CY,CZ,DE,DK,EE,ES,FI,FR,GR,HR,HU,IE,IT,LT,LU,LV,MT,NL,PL,PT,RO,SE,SI,SK")
CA5 = "GT,SV,HN,NI,CR"
CA6 = "GT,SV,HN,NI,CR,PA"

# (código, nombre, orígenes, destinos, prueba de origen, nota)
ACUERDOS_BASE = [
    ("MCCA", "Central American Common Market (MCCA)", CA5, CA5,
     "FAUCA / DUCA-F (Central American origin)", "Free trade among the five members; Panama trades under its protocol."),
    ("CAFTA-DR", "DR-CAFTA (United States – Central America – Dominican Republic)", "US,DO", CA5,
     "Certification of origin (DR-CAFTA)", None),
    ("MX-CA", "Mexico – Central America FTA", "MX", CA5, "Certificate of origin (Mexico – CA)", None),
    ("MX-PA", "Mexico – Panama FTA", "MX", "PA", "Certificate of origin (Mexico – Panama)", None),
    ("UE-CA", "EU – Central America Association Agreement", UE, CA6,
     "EUR.1 or origin declaration on the invoice", None),
    ("UK-CA", "United Kingdom – Central America Association Agreement", "GB", CA6,
     "EUR.1 or origin declaration on the invoice", None),
    ("KR-CA", "Korea – Central America FTA", "KR", "CR,SV,HN,NI,PA",
     "Certificate of origin (Korea – CA)", "Guatemala's accession is pending entry into force."),
    ("CN-CR", "China – Costa Rica FTA", "CN", "CR", "Certificate of origin (China – Costa Rica)", None),
    ("CN-NI", "China – Nicaragua FTA", "CN", "NI", "Certificate of origin (China – Nicaragua)", "In force since 1 Jan 2024."),
    ("TW-GT", "Taiwan – Guatemala FTA", "TW", "GT", "Certificate of origin (Taiwan – Guatemala)", None),
    ("CO-CA", "Colombia FTAs (Northern Triangle, Costa Rica, Panama)", "CO", "GT,SV,HN,CR,PA",
     "Certificate of origin", None),
    ("CL-CA", "Chile – Central America FTA", "CL", CA6, "Certificate of origin", None),
    ("PE-CA", "Peru FTAs (Costa Rica, Panama, Guatemala)", "PE", "CR,PA,GT", "Certificate of origin", None),
    ("CA-CA", "Canada FTAs (Costa Rica, Honduras, Panama)", "CA", "CR,HN,PA", "Certificate of origin", None),
    ("SG-CA", "Singapore FTAs (Costa Rica, Panama)", "SG", "CR,PA", "Certificate of origin", None),
    ("DO-CA", "Dominican Republic – Central America FTA", "DO", CA5, "Certificate of origin", None),
    ("EFTA-CA", "EFTA – Central American States FTA", "CH,NO,IS,LI", "CR,PA",
     "EUR.1 or origin declaration on the invoice", "Guatemala's accession is pending."),
    ("IL-PA", "Israel – Panama FTA", "IL", "PA", "Certificate of origin", None),
]


def _lista(txt: str | None) -> list[str]:
    return [x.strip().upper() for x in (txt or "").split(",") if x.strip()]


def cargar_acuerdos(db: Session) -> int:
    for cod, nombre, origenes, dest, prueba, nota in ACUERDOS_BASE:
        db.add(AcuerdoComercial(codigo=cod, nombre=nombre, origenes=origenes, destinos=dest, prueba=prueba, nota=nota))
    return len(ACUERDOS_BASE)


def acuerdos_contexto(db: Session) -> list[dict]:
    return [{"codigo": x.codigo, "nombre": x.nombre, "origenes": _lista(x.origenes), "destinos": _lista(x.destinos),
             "prueba": x.prueba, "nota": x.nota}
            for x in db.scalars(select(AcuerdoComercial).where(AcuerdoComercial.activo.is_(True))
                                .order_by(AcuerdoComercial.codigo))]


def acuerdos_para(db: Session, origen: str | None, destinos: list[str]) -> dict[str, list[dict]]:
    """Por país destino, los acuerdos que cubren el origen dado."""
    origen = (origen or "").upper()
    res: dict[str, list[dict]] = {d: [] for d in destinos}
    for a in acuerdos_contexto(db):
        if origen in a["origenes"]:
            for d in destinos:
                if d in a["destinos"]:
                    res[d].append(a)
    return res
