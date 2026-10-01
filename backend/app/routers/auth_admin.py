from fastapi import APIRouter, Request, Response
from sqlalchemy import select

from ..config import settings
from ..models import Usuario
from ..deps import COOKIE
from ..schemas import DesafioIn, LoginIn, PasswordIn, PerfilIn, ProveedorIn, ProveedorPatch, RolIn, RolPatch, UsuarioIn, UsuarioPatch, VerificarIn
from ..services import acceso, preferencias
from ..services.limites import limitar
from ..services import varios
from ..services.common import permisos_de
from .base import Clave, Db, User, ejecutar

router = APIRouter()


def _yo(u: Usuario) -> dict:
    return {
        "id": u.id,
        "email": u.email,
        "nombre": u.nombre,
        "rol": u.rol,
        "rol_nombre": u.rol_ref.nombre if u.rol_ref else None,
        "proveedor_id": u.proveedor_id,
        "proveedor": u.proveedor.nombre if u.proveedor else None,
        "permisos": permisos_de(u),
        "preferencias": preferencias.de(u),
        "telefono": acceso.mascara_telefono(u.telefono),
        "dos_pasos": bool(settings.DOS_PASOS and u.dos_pasos),
        "sesion_inactividad_min": settings.SESION_INACTIVIDAD_MIN,
        "config": {
            "posicion_en_varias_facturas": settings.POSICION_EN_VARIAS_FACTURAS,
            "factura_en_una_sola_unidad": settings.FACTURA_EN_UNA_SOLA_UNIDAD,
            "requerir_datos_aduana": settings.REQUERIR_DATOS_ADUANA,
            "dias_alerta_borrador": settings.DIAS_ALERTA_BORRADOR,
        },
    }


def _cookie(resp: Response, token: str) -> None:
    resp.set_cookie(COOKIE, token, httponly=True, secure=settings.COOKIE_SEGURA, samesite="strict",
                    max_age=settings.SESION_HORAS * 3600, path="/")


def _cliente(request: Request) -> tuple[str | None, str | None]:
    return (request.client.host if request.client else None), request.headers.get("user-agent")


@router.post("/auth/login")
def login(datos: LoginIn, request: Request, response: Response, db: Db):
    """Paso 1: correo y contraseña. Con verificación en dos pasos devuelve el
    desafío; sin ella, abre la sesión."""
    limitar(request, "login")
    r = acceso.iniciar(db, datos.email, datos.password, *_cliente(request))
    if not r["dos_pasos"]:
        _cookie(response, r.pop("token"))
        db.expire_all()
        r["usuario"] = _yo(db.scalar(select(Usuario).where(Usuario.email == datos.email.strip().lower())))
    return r


@router.post("/auth/verificar")
def verificar(datos: VerificarIn, request: Request, response: Response, db: Db):
    """Paso 2: el código recibido por SMS."""
    limitar(request, "verificar")
    token = acceso.verificar(db, datos.desafio, datos.codigo, *_cliente(request))
    _cookie(response, token)
    return {"usuario": _yo(acceso.usuario_de_sesion(db, token))}


@router.post("/auth/reenviar")
def reenviar(datos: DesafioIn, request: Request, db: Db):
    limitar(request, "reenviar")
    return acceso.reenviar(db, datos.desafio)


@router.post("/auth/logout")
def logout(request: Request, response: Response, db: Db):
    acceso.cerrar_sesion(db, request.cookies.get(COOKIE))
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


@router.post("/auth/password")
def cambiar_password(datos: PasswordIn, request: Request, db: Db, user: User):
    """Cambia la contraseña propia y cierra las demás sesiones abiertas."""
    acceso.cambiar_password(db, user, datos.actual, datos.nueva, getattr(request.state, "token", None))
    db.commit()
    return {"ok": True}


@router.get("/auth/me")
def yo(user: User):
    return _yo(user)


@router.get("/perfil")
def perfil(user: User):
    return {**_yo(user), "opciones": preferencias.opciones()}


@router.patch("/perfil")
def editar_perfil(datos: PerfilIn, db: Db, user: User, clave: Clave = None):
    return ejecutar(db, user, clave, lambda: preferencias.guardar(db, user, datos))


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


@router.get("/roles")
def roles(db: Db, user: User):
    return varios.listar_roles(db, user)


@router.post("/roles")
def crear_rol(datos: RolIn, db: Db, user: User, clave: Clave = None):
    return ejecutar(db, user, clave, lambda: varios.guardar_rol(db, user, datos))


@router.patch("/roles/{rol_id}")
def actualizar_rol(rol_id: int, datos: RolPatch, db: Db, user: User, clave: Clave = None):
    return ejecutar(db, user, clave, lambda: varios.guardar_rol(db, user, datos, rol_id))


@router.delete("/roles/{rol_id}")
def borrar_rol(rol_id: int, db: Db, user: User, clave: Clave = None):
    return ejecutar(db, user, clave, lambda: varios.borrar_rol(db, user, rol_id) or {"ok": True})
