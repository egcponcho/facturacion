"""Rutas de acceso: inicio de sesión, perfil, proveedores, usuarios y roles.
"""
from fastapi import APIRouter, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import object_session

from app.core.config import settings
from app.core.empresa import regla
from app.esquemas import (
    DesafioIn,
    FotoIn,
    LoginIn,
    PasswordIn,
    PerfilIn,
    ProveedorIn,
    ProveedorPatch,
    RolIn,
    RolPatch,
    UsuarioIn,
    UsuarioPatch,
    VerificarIn,
)
from app.modelos import Organizacion, Usuario
from app.modulos.acceso import autenticacion as acceso
from app.modulos.acceso import preferencias, visibilidad
from app.modulos.acceso import proveedores as servicio_proveedores
from app.modulos.acceso import roles as servicio_roles
from app.modulos.acceso import usuarios as servicio_usuarios
from app.modulos.acceso.limites import limitar
from app.modulos.acceso.permisos import catalogo_permisos, permisos_de
from app.modulos.empresa import organizacion
from app.modulos.productos import flujo
from app.web.dependencias import COOKIE
from app.web.rutas import Clave, Db, User, ejecutar

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
        "alcance": u.alcance or {},
        "permisos": permisos_de(u),
        "preferencias": preferencias.de(u),
        "foto": u.foto, "cargo": u.cargo, "area": u.area, "empresa": u.empresa,
        "clave_temporal": bool(u.clave_temporal), "ultimo_acceso": u.ultimo_acceso,
        "password_cambiado_en": u.password_cambiado_en,
        "telefono": acceso.mascara_telefono(u.telefono),
        "dos_pasos": bool(settings.DOS_PASOS and u.dos_pasos),
        "sesion_inactividad_min": settings.SESION_INACTIVIDAD_MIN,
        "config": {
            "posicion_en_varias_facturas": regla("POSICION_EN_VARIAS_FACTURAS"),
            "factura_en_una_sola_unidad": regla("FACTURA_EN_UNA_SOLA_UNIDAD"),
            "requerir_datos_aduana": regla("REQUERIR_DATOS_ADUANA"),
            "dias_alerta_borrador": regla("DIAS_ALERTA_BORRADOR"),
            "dias_aviso_tienda": regla("DIAS_AVISO_TIENDA"),
        },
        "max_subida_mb": settings.MAX_SUBIDA_MB,
        "flujo": flujo.valores(object_session(u)) if object_session(u) else dict(flujo.DEFECTOS),
        "organizacion": _empresa(u),
        "datos_ocultos": visibilidad.ocultos_de(u),
    }


def _empresa(u: Usuario) -> dict | None:
    """Nombre, logo y marca de la empresa para el menú."""
    db = object_session(u)
    o = db.get(Organizacion, organizacion.ID_EMPRESA) if db else None
    return {"nombre": o.nombre, "logo": o.logo,
            "marca": {**organizacion.MARCA, **(o.configuracion or {}).get("marca", {})},
            "textos": organizacion._textos_de(o.configuracion or {})} if o else None


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
    token = request.cookies.get(COOKIE)
    if token and (u := acceso.usuario_de_sesion(db, token)):
        from app.modulos.comun.edicion import liberar_de_usuario
        liberar_de_usuario(db, u.id)  # sus documentos quedan libres para los demás
    acceso.cerrar_sesion(db, token)
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
    # Lo que el usuario puede hacer, por módulo (solo lectura: lo define su rol)
    propios = set(permisos_de(user))
    accesos = [{"modulo": m["modulo"], "permisos": [p["etiqueta"] for p in m["permisos"] if p["clave"] in propios]}
               for m in catalogo_permisos()]
    return {**_yo(user), "opciones": preferencias.opciones(), "accesos": [a for a in accesos if a["permisos"]]}


@router.get("/auth/politica")
def politica():
    """Reglas de la contraseña, para mostrarlas mientras se escribe."""
    return acceso.reglas_password()


@router.put("/perfil/foto")
def foto_perfil(datos: FotoIn, db: Db, user: User, clave: Clave = None):
    return ejecutar(db, user, clave, lambda: preferencias.guardar_foto(db, user, datos.foto))


@router.patch("/perfil")
def editar_perfil(datos: PerfilIn, db: Db, user: User, clave: Clave = None):
    return ejecutar(db, user, clave, lambda: preferencias.guardar(db, user, datos))


@router.put("/perfil/columnas/{tabla}")
def guardar_columnas(tabla: str, datos: dict, db: Db, user: User, clave: Clave = None):
    """Columnas visibles de una tabla del propio usuario ({"columnas": [...]} o null para la vista inicial)."""
    return ejecutar(db, user, clave, lambda: preferencias.guardar_columnas(db, user, tabla, datos.get("columnas")))


@router.put("/perfil/vistas/{pantalla}")
def guardar_vistas(pantalla: str, datos: list[dict], db: Db, user: User, clave: Clave = None):
    """Vistas guardadas de una pantalla (filtros con nombre) del propio usuario."""
    return ejecutar(db, user, clave, lambda: preferencias.guardar_vistas(db, user, pantalla, datos))


@router.get("/proveedores")
def proveedores(db: Db, user: User):
    return servicio_proveedores.listar_proveedores(db, user)


@router.post("/proveedores")
def crear_proveedor(datos: ProveedorIn, db: Db, user: User, clave: Clave = None):
    return ejecutar(db, user, clave, lambda: servicio_proveedores.crear_proveedor(db, user, datos))


@router.patch("/proveedores/{proveedor_id}")
def actualizar_proveedor(proveedor_id: int, datos: ProveedorPatch, db: Db, user: User, clave: Clave = None):
    return ejecutar(db, user, clave, lambda: servicio_proveedores.actualizar_proveedor(db, user, proveedor_id, datos))


@router.get("/usuarios")
def usuarios(db: Db, user: User):
    return servicio_usuarios.listar_usuarios(db, user)


@router.post("/usuarios")
def crear_usuario(datos: UsuarioIn, db: Db, user: User, clave: Clave = None):
    return ejecutar(db, user, clave, lambda: servicio_usuarios.crear_usuario(db, user, datos))


@router.patch("/usuarios/{usuario_id}")
def actualizar_usuario(usuario_id: int, datos: UsuarioPatch, db: Db, user: User, clave: Clave = None):
    return ejecutar(db, user, clave, lambda: servicio_usuarios.actualizar_usuario(db, user, usuario_id, datos))


@router.get("/roles")
def roles(db: Db, user: User):
    return servicio_roles.listar_roles(db, user)


@router.post("/roles")
def crear_rol(datos: RolIn, db: Db, user: User, clave: Clave = None):
    return ejecutar(db, user, clave, lambda: servicio_roles.guardar_rol(db, user, datos))


@router.patch("/roles/{rol_id}")
def actualizar_rol(rol_id: int, datos: RolPatch, db: Db, user: User, clave: Clave = None):
    return ejecutar(db, user, clave, lambda: servicio_roles.guardar_rol(db, user, datos, rol_id))


@router.delete("/roles/{rol_id}")
def borrar_rol(rol_id: int, db: Db, user: User, clave: Clave = None):
    return ejecutar(db, user, clave, lambda: servicio_roles.borrar_rol(db, user, rol_id) or {"ok": True})
