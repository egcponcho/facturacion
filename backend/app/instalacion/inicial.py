"""Preparación de una instalación nueva (producción).

Al arrancar, después de las migraciones:

- La ficha de la empresa existe (con el nombre de EMPRESA_NOMBRE si se dio).
- Los roles de fábrica existen (Administrador, Equipo interno, Proveedor y los
  sugeridos). Se pueden editar desde Usuarios y accesos.
- Si la base no tiene usuarios, se crea el primer administrador con
  ADMIN_EMAIL y ADMIN_PASSWORD. La contraseña es temporal: al primer ingreso
  el sistema pide cambiarla. Con la verificación en dos pasos activa también
  hace falta ADMIN_TELEFONO.

También se puede crear (o restablecer) un administrador a mano:

    python -m app.instalacion.inicial admin@empresa.com +50370000000

que escribe en pantalla una contraseña temporal.
"""
import logging
import sys

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.seguridad import hash_password
from app.modelos import Usuario

log = logging.getLogger("inicial")


def preparar_instalacion(db: Session) -> None:
    from app.modulos.acceso.roles import crear_roles_fabrica, crear_roles_sugeridos
    from app.modulos.empresa.organizacion import asegurar_principal

    empresa = asegurar_principal(db, settings.EMPRESA_NOMBRE or "My company")
    if settings.EMPRESA_NOMBRE and empresa.nombre in ("My company", "Main company"):
        empresa.nombre = settings.EMPRESA_NOMBRE
    crear_roles_fabrica(db)
    crear_roles_sugeridos(db)
    if not db.scalar(select(func.count(Usuario.id))) and settings.ADMIN_EMAIL:
        if not settings.ADMIN_PASSWORD:
            raise RuntimeError("Falta ADMIN_PASSWORD para crear el primer administrador.")
        crear_admin(db, settings.ADMIN_EMAIL, settings.ADMIN_TELEFONO, settings.ADMIN_PASSWORD)
        log.warning("Se creó el primer administrador %s con contraseña temporal.", settings.ADMIN_EMAIL)
    db.commit()


def crear_admin(db: Session, email: str, telefono: str | None, password: str) -> Usuario:
    """Administrador con contraseña temporal (lo crea o lo restablece)."""
    from app.modulos.acceso.autenticacion import politica_password, validar_telefono
    from app.modulos.acceso.roles import crear_roles_fabrica

    email = email.strip().lower()
    faltan = politica_password(password, email)
    if faltan:
        raise RuntimeError("La contraseña del administrador no cumple la política: " + " ".join(faltan))
    telefono = validar_telefono(telefono) if telefono else None
    if settings.DOS_PASOS and not telefono:
        raise RuntimeError("Con la verificación en dos pasos activa, el administrador necesita un celular "
                           "(ADMIN_TELEFONO, formato +50370000000).")
    rol = crear_roles_fabrica(db)["admin"]
    u = db.scalar(select(Usuario).where(func.lower(Usuario.email) == email))
    if not u:
        u = Usuario(email=email, nombre="Administrator")
        db.add(u)
    u.rol, u.rol_id, u.activo = "admin", rol.id, True
    u.password_hash = hash_password(password)
    u.clave_temporal = True
    u.telefono = telefono or u.telefono
    u.intentos_fallidos, u.bloqueado_hasta = 0, None
    db.flush()
    return u


if __name__ == "__main__":
    from app.core.db import SessionLocal
    from app.modulos.acceso.autenticacion import password_temporal

    if len(sys.argv) < 2:
        sys.exit("Uso: python -m app.instalacion.inicial <correo> [celular]")
    clave = password_temporal()
    with SessionLocal() as s:
        crear_admin(s, sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None, clave)
        s.commit()
    print(f"Administrador {sys.argv[1]} listo. Contraseña temporal: {clave}")
