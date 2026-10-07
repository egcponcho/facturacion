"""Carga de los datos incluidos, separada por capa (nunca se mezclan):

1. MOTOR (data/motor): paquete 02 (dominios, atributos, reglas del sistema),
   atributos de la ficha, categorías técnicas y reglas de la ficha. Es
   configuración interna, nunca dato oficial. Se pone al día en cada arranque
   sin pisar lo editado.
2. OFICIAL (data/oficial): paquetes 01 y 03, árbol del ACI, notas legales y
   las líneas regionales de los países que aplican el SAC a 10 dígitos. Solo
   se carga en una base sin datos oficiales; después lo oficial entra por la
   carga por etapas (previa → diferencias → publicar). Un paquete con errores
   detiene la carga.
3. DEMO (data/demo): la empresa de demostración (configuración de países de
   ejemplo, historial de clasificaciones, palabras clave, acuerdos de
   referencia). Solo con SEED_DEMO=1.

El orden importa: los atributos de la ficha van antes del paquete 02 (que
declara «Same as» sobre ellos), el 02 define los dominios que el 01 relaciona
con capítulos, la capa técnica completa atributos del 02 y las reglas de la
ficha leen el árbol oficial.
"""
import json

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .datos import DEMO, MOTOR, OFICIAL
from .models import AcuerdoComercial, PaisArancel, VersionDataset


def cargar_motor_paquete(db: Session) -> None:
    """Los atributos de la ficha primero (el paquete 02 declara «Same as» sobre
    ellos) y después el paquete 02 (dominios, atributos genéricos y reglas del sistema)."""
    from .services import atributos, oficial

    atributos.cargar_motor(db)
    oficial.cargar_paquetes_base(db, [MOTOR / "02_carga_motor_dinamico_v3.xlsx"])


def cargar_oficial(db: Session) -> bool:
    """Datos oficiales incluidos, solo en una base que aún no tiene ninguno."""
    from .services import arbol, oficial

    if db.scalar(select(func.count()).select_from(VersionDataset)):
        return False
    oficial.cargar_paquetes_base(db, [OFICIAL / "01_carga_oficial_catalogos_v3.xlsx", OFICIAL / "03_carga_nacional_regulaciones_v3.xlsx"])
    arbol.cargar_sac(db)
    oficial.cargar_notas_incluidas(db)
    oficial.cargar_lineas_regionales(db)  # solo países que su configuración declara SAC10
    db.flush()
    return True


def cargar_motor(db: Session) -> None:
    """Configuración del motor incluida (no pisa lo editado)."""
    from .services import atributos, categorias, materiales, reglas

    atributos.cargar_tecnico(db)  # categorías técnicas de químicos y materias primas
    materiales.sembrar(db)  # clases de material de base con su palabra aduanera
    categorias.sembrar(db)
    reglas.cargar_reglas_ficha(db)
    db.flush()


def cargar_base(db: Session) -> None:
    """Motor y datos oficiales incluidos, en orden. Nunca carga la demostración."""
    cargar_motor_paquete(db)
    cargar_oficial(db)
    cargar_motor(db)


# ---- Demostración -------------------------------------------------------------------
# Configuración de países de la empresa de ejemplo: qué países aplican el SAC regional
# a 10 dígitos como código nacional. Con datos reales esto se configura en Countries.
PAISES_DEMO = {"GT": {"nivel_base": "SAC10", "longitudes": "10", "digitos": 10},
               "SV": {"nivel_base": "SAC10", "longitudes": "10", "digitos": 10},
               "HN": {"nivel_base": "SAC10", "longitudes": "10", "digitos": 10},
               "NI": {"digitos": 12}, "CR": {"digitos": 12}, "PA": {"digitos": 12}}


def cargar_demo(db: Session) -> None:
    """La empresa de demostración: países, historial, palabras clave y acuerdos de referencia."""
    from .services import conocimiento, oficial

    for i, (iso, conf) in enumerate(PAISES_DEMO.items()):
        p = db.scalar(select(PaisArancel).where(PaisArancel.iso == iso))
        if p:
            for k, v in conf.items():
                setattr(p, k, v)
            p.orden = i
    db.flush()
    oficial.cargar_lineas_regionales(db)  # las líneas oficiales del ACI para los países SAC10 de la demo
    if not db.scalar(select(func.count()).select_from(AcuerdoComercial)):
        for x in json.loads((DEMO / "acuerdos_demo.json").read_text(encoding="utf-8"))["acuerdos"]:
            db.add(AcuerdoComercial(**x))
    conocimiento.cargar_historial_demo(db)
    conocimiento.cargar_palabras_demo(db)
    db.flush()
