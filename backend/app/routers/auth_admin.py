from fastapi import APIRouter
from sqlalchemy import select

from ..config import settings
from ..models import Usuario
from ..schemas import LoginIn, ProveedorIn, ProveedorPatch, UsuarioIn, UsuarioPatch
from ..security import crear_token, verificar_password
from ..services import varios
from ..services.common import ErrorNegocio, permisos_de
from .base import Clave, Db, User, ejecutar

router = APIRouter()


def _yo(u: Usuario) -> dict:
    return {
        "id": u.id,
        "email": u.email,
        "nombre": u.nombre,
        "rol": u.rol,
        "proveedor_id": u.proveedor_id,
        "proveedor": u.proveedor.nombre if u.proveedor else None,
        "permisos": permisos_de(u),
        "config": {
            "posicion_en_varias_facturas": settings.POSICION_EN_VARIAS_FACTURAS,
            "factura_en_una_sola_unidad": settings.FACTURA_EN_UNA_SOLA_UNIDAD,
            "requerir_datos_aduana": settings.REQUERIR_DATOS_ADUANA,
            "dias_alerta_borrador": settings.DIAS_ALERTA_BORRADOR,
        },
    }


@router.post("/auth/login")
def login(datos: LoginIn, db: Db):
    u = db.scalar(select(Usuario).where(Usuario.email == datos.email.strip().lower()))
    if not u or not u.activo or not verificar_password(datos.password, u.password_hash):
        raise ErrorNegocio("Correo o contraseña incorrectos.", 401, "credenciales")
    return {"token": crear_token(u.id), "usuario": _yo(u)}


@router.get("/auth/me")
def yo(user: User):
    return _yo(user)


@router.get("/proveedores")
def proveedores(db: Db, user: User):
    return varios.listar_proveedores(db, user)


@router.post("/proveedores")
def crear_proveedor(datos: ProveedorIn, db: Db, user: User, clave: Clave = None):
    return ejecutar(db, user, clave, lambda: varios.crear_proveedor(db, user, datos))


@router.patch("/proveedores/{proveedor_id}")
def actualizar_proveedor(proveedor_id: int, datos: ProveedorPatch, db: Db, user: User, clave: Clave = None):
    return ejecutar(db, user, clave, lambda: varios.actualizar_proveedor(db, user, proveedor_id, datos))


@router.get("/usuarios")
def usuarios(db: Db, user: User):
    return varios.listar_usuarios(db, user)


@router.post("/usuarios")
def crear_usuario(datos: UsuarioIn, db: Db, user: User, clave: Clave = None):
    return ejecutar(db, user, clave, lambda: varios.crear_usuario(db, user, datos))


@router.patch("/usuarios/{usuario_id}")
def actualizar_usuario(usuario_id: int, datos: UsuarioPatch, db: Db, user: User, clave: Clave = None):
    return ejecutar(db, user, clave, lambda: varios.actualizar_usuario(db, user, usuario_id, datos))
