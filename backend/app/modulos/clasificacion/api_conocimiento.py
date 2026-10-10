"""Dos capas fuera del dato oficial, cada una con sus rutas:

- /clasificacion/configuracion/…: el MOTOR (dominios, categorías, atributos,
  reglas). Es configuración interna, no dato arancelario oficial.
- /conocimiento/…: lo que sabe la EMPRESA (historial de clasificaciones,
  decisiones y correcciones, palabras clave, sinónimos). Solo ordena candidatos.

El dato oficial (fuentes, versiones, árbol, líneas nacionales, notas legales,
impuestos y regulaciones) sigue en /aranceles/oficial/… y /aranceles/….
"""
from fastapi import APIRouter, Query

from app.modelos import PalabraClave, SinonimoMaterial
from app.modulos.clasificacion import conocimiento
from app.web.rutas import Db, User

router = APIRouter()


# ---- CLASSIFICATION ENGINE ---------------------------------------------------------
@router.get("/clasificacion/configuracion")
def configuracion(db: Db, user: User):
    """Resumen de la configuración del motor (no es dato oficial)."""
    from app.modulos.clasificacion import atributos, categorias, oficial, reglas

    doms = oficial.dominios(db, user)
    return {"capa": "CLASSIFICATION_ENGINE", "dominios": len(doms),
            "categorias": len(categorias.categorias(db, False)), "atributos": atributos.listar(db, user)["total"],
            "reglas": reglas.listar(db, user, None, None, None, 1, 1, None)["total"]}


@router.get("/clasificacion/configuracion/dominios")
def config_dominios(db: Db, user: User):
    """Dominios del motor de clasificación con sus capítulos."""
    from app.modulos.clasificacion import oficial

    return oficial.dominios(db, user)


@router.get("/clasificacion/configuracion/categorias")
def config_categorias(db: Db, user: User, todas: bool = False, dominio: str | None = None):
    """Categorías del motor; sin `todas`, solo las activas, y con `dominio`, solo las de ese dominio."""
    from app.modulos.acceso.permisos import exigir
    from app.modulos.clasificacion import categorias

    exigir(user, "producto.ver")
    return [c for c in categorias.categorias(db, not todas) if not dominio or c["dominio"] == dominio]


@router.get("/clasificacion/configuracion/atributos")
def config_atributos(db: Db, user: User, q: str | None = None, dominio: str | None = None):
    """Atributos del motor de clasificación, filtrados por texto y dominio."""
    from app.modulos.clasificacion import atributos

    return atributos.listar(db, user, q, dominio, None)


@router.get("/clasificacion/configuracion/reglas")
def config_reglas(db: Db, user: User, q: str | None = None, tipo: str | None = None, page: int = Query(1, ge=1),
                  size: int = Query(50, ge=1, le=200)):
    """Reglas del motor de clasificación, paginadas y filtradas por texto y tipo."""
    from app.modulos.clasificacion import reglas

    return reglas.listar(db, user, q, tipo, None, page, size, None)


# ---- COMPANY KNOWLEDGE ---------------------------------------------------------------
@router.get("/conocimiento")
def conocimiento_resumen(db: Db, user: User):
    """Conocimiento de la empresa en números: historial por origen, palabras clave y sinónimos."""
    return conocimiento.resumen(db, user)


@router.get("/conocimiento/historial")
def historial(db: Db, user: User, pais: str | None = None, q: str | None = None, origen: str | None = None,
              page: int = Query(1, ge=1), size: int = Query(50, ge=1, le=200)):
    """Historial de clasificaciones de la empresa, paginado y filtrado por país, código y origen."""
    return conocimiento.listar(db, user, pais, q, page, size, origen)


@router.delete("/conocimiento/historial/{hid}")
def historial_borrar(hid: int, db: Db, user: User):
    """Quita una entrada del historial: deja de influir en el orden de candidatos."""
    conocimiento.borrar(db, user, hid)
    db.commit()
    return {"ok": True}


@router.get("/conocimiento/palabras")
def palabras(db: Db, user: User):
    """Palabras clave aprendidas del nombre del estilo, con su tipo, marca y atributos."""
    return conocimiento.palabras(db, user)


@router.delete("/conocimiento/palabras/{pid}")
def palabra_borrar(pid: int, db: Db, user: User):
    """Borra una palabra clave aprendida."""
    conocimiento.borrar_palabra(db, user, PalabraClave, pid)
    db.commit()
    return {"ok": True}


@router.get("/conocimiento/sinonimos")
def sinonimos(db: Db, user: User):
    """Sinónimos de material aprendidos (palabra de composición → material)."""
    return conocimiento.sinonimos(db, user)


@router.delete("/conocimiento/sinonimos/{sid}")
def sinonimo_borrar(sid: int, db: Db, user: User):
    """Borra un sinónimo de material aprendido."""
    conocimiento.borrar_palabra(db, user, SinonimoMaterial, sid)
    db.commit()
    return {"ok": True}
