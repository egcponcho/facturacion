"""Acceso seguro: contraseña, bloqueo por intentos, verificación en dos pasos
por SMS y sesiones del lado del servidor.

- La contraseña se guarda con PBKDF2-SHA256 (200 000 iteraciones y sal).
- Tras INTENTOS_MAX contraseñas incorrectas la cuenta se bloquea BLOQUEO_MIN.
- Con verificación en dos pasos, la contraseña correcta solo abre un
  "desafío": se envía un código de 6 dígitos al celular registrado, válido
  CODIGO_VALIDEZ_MIN minutos y 5 intentos. Solo con el código se crea la sesión.
- La sesión es un token aleatorio en una cookie httpOnly; en la base solo se
  guarda su hash. Vence por inactividad y por duración máxima, y se revoca al
  cerrar sesión, al cambiar la contraseña o al desactivar al usuario.
"""
import hashlib
import hmac
import re
import secrets
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errores import ErrorNegocio
from app.core.seguridad import hash_password, verificar_password
from app.modelos import DesafioDosPasos, SesionUsuario, Usuario
from app.modelos import ahora as _ahora
from app.modulos.acceso.sms import enviar_sms
from app.modulos.comun.historial import registrar

INTENTOS_CODIGO = 5
ENVIOS_MAX = 5
TELEFONO = re.compile(r"^\+[1-9]\d{7,14}$")


def _hash(valor: str) -> str:
    return hashlib.sha256(valor.encode()).hexdigest()


def _hash_codigo(desafio_token: str, codigo: str) -> str:
    # El código se liga a su desafío y a la clave del servidor
    return hmac.new(settings.SECRET_KEY.encode(), f"{desafio_token}:{codigo}".encode(), hashlib.sha256).hexdigest()


def mascara_telefono(tel: str | None) -> str | None:
    if not tel:
        return None
    return f"{tel[:4]} •••• {tel[-2:]}"


def validar_telefono(tel: str | None) -> str | None:
    if tel in (None, ""):
        return None
    tel = re.sub(r"[\s\-().]", "", tel)
    if not TELEFONO.match(tel):
        raise ErrorNegocio("Enter the mobile number in international format, e.g. +50370001234.", 422, "validacion",
                           [{"campo": "telefono", "mensaje": "International format: + country code and number."}])
    return tel


# Reglas de la contraseña (las mismas que muestra la pantalla mientras se escribe)
REGLAS_PASSWORD = [
    ("largo", "At least 10 characters", lambda p, e: len(p) >= 10),
    ("mayuscula", "An uppercase letter", lambda p, e: bool(re.search(r"[A-Z]", p))),
    ("minuscula", "A lowercase letter", lambda p, e: bool(re.search(r"[a-z]", p))),
    ("numero", "A number", lambda p, e: bool(re.search(r"\d", p))),
    ("simbolo", "A symbol (such as ! # $ % * -)", lambda p, e: bool(re.search(r"[^A-Za-z0-9]", p))),
    ("usuario", "Does not contain your user name", lambda p, e: not (e and e.split("@")[0].lower() in p.lower())),
]


def reglas_password() -> list[dict]:
    return [{"clave": k, "texto": t} for k, t, _ in REGLAS_PASSWORD]


def politica_password(password: str, email: str | None = None) -> list[str]:
    return [t + "." for _, t, ok in REGLAS_PASSWORD if not ok(password or "", email)]


def password_temporal() -> str:
    """Contraseña temporal que cumple la política (se cambia al primer ingreso)."""
    import string

    while True:
        letras = string.ascii_letters + string.digits
        p = "".join(secrets.choice(letras) for _ in range(10)) + secrets.choice("!#$%*-") + secrets.choice("0123456789")
        if not politica_password(p):
            return p


def exigir_politica(password: str, email: str | None = None) -> None:
    errores = politica_password(password, email)
    if errores:
        raise ErrorNegocio("The password is not strong enough.", 422, "password_debil",
                           [{"campo": "password", "mensaje": e} for e in errores])


# ---- Contraseña y bloqueo ---------------------------------------------------
def _bloqueado(u: Usuario) -> int | None:
    """Minutos que faltan para desbloquear, o None."""
    if u.bloqueado_hasta and u.bloqueado_hasta > _ahora():
        return max(1, int((u.bloqueado_hasta - _ahora()).total_seconds() // 60) + 1)
    return None


def iniciar(db: Session, email: str, password: str, ip: str | None, agente: str | None) -> dict:
    """Primer paso: contraseña. Devuelve la sesión (sin dos pasos) o el desafío."""
    u = db.scalar(select(Usuario).where(Usuario.email == email.strip().lower()))
    error = ErrorNegocio("Incorrect email or password.", 401, "credenciales")
    if not u or not u.activo:
        # Mismo trabajo que con un usuario real: no revela si el correo existe
        verificar_password(password, "pbkdf2$AAAAAAAAAAAAAAAAAAAAAA==$AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")
        raise error
    if (faltan := _bloqueado(u)):
        raise ErrorNegocio(f"Too many failed attempts. Try again in {faltan} min.", 423, "bloqueado")
    if not verificar_password(password, u.password_hash):
        u.intentos_fallidos += 1
        if u.intentos_fallidos >= settings.INTENTOS_MAX:
            u.bloqueado_hasta = _ahora() + timedelta(minutes=settings.BLOQUEO_MIN)
            u.intentos_fallidos = 0
            registrar(db, u, "usuario", u.id, "bloqueo", {"ip": ip})
            db.commit()
            raise ErrorNegocio(f"Too many failed attempts. The account is locked for {settings.BLOQUEO_MIN} min.",
                               423, "bloqueado")
        db.commit()
        raise error
    u.intentos_fallidos = 0
    u.bloqueado_hasta = None
    if settings.DOS_PASOS and u.dos_pasos:
        if not u.telefono:
            raise ErrorNegocio("Your account has no registered mobile for two-step verification. "
                               "Ask the administrator to register it.", 403, "sin_telefono")
        return _nuevo_desafio(db, u)
    return {"dos_pasos": False, "token": crear_sesion(db, u, ip, agente)}


# ---- Verificación en dos pasos ----------------------------------------------
def _enviar_codigo(d: DesafioDosPasos, token: str) -> str:
    codigo = f"{secrets.randbelow(10**6):06d}"
    d.codigo_hash = _hash_codigo(token, codigo)
    d.expira = _ahora() + timedelta(minutes=settings.CODIGO_VALIDEZ_MIN)
    d.ultimo_envio = _ahora()
    d.intentos = 0
    enviar_sms(d.usuario.telefono, f"Your supplier workspace code is {codigo}. It expires in "
                                   f"{settings.CODIGO_VALIDEZ_MIN} min. Never share it.")
    return codigo


def _respuesta_desafio(d: DesafioDosPasos, token: str, codigo: str) -> dict:
    r = {"dos_pasos": True, "desafio": token, "telefono": mascara_telefono(d.usuario.telefono),
         "reenviar_en": settings.CODIGO_REENVIO_SEG, "expira_en": settings.CODIGO_VALIDEZ_MIN * 60}
    # Solo en la demo sin SMS real se muestra el código en pantalla
    if settings.SMS_PROVEEDOR == "consola" and settings.SEED_DEMO:
        r["codigo_demo"] = codigo
    return r


def _nuevo_desafio(db: Session, u: Usuario) -> dict:
    # Un desafío abierto por usuario: los anteriores dejan de servir
    db.execute(update(DesafioDosPasos).where(DesafioDosPasos.usuario_id == u.id, DesafioDosPasos.usado.is_(False))
               .values(usado=True))
    token = secrets.token_urlsafe(32)
    d = DesafioDosPasos(token_hash=_hash(token), usuario=u, codigo_hash="", expira=_ahora())
    db.add(d)
    codigo = _enviar_codigo(d, token)
    db.commit()
    return _respuesta_desafio(d, token, codigo)


def _desafio(db: Session, token: str) -> DesafioDosPasos:
    d = db.scalar(select(DesafioDosPasos).where(DesafioDosPasos.token_hash == _hash(token or "")))
    if not d or d.usado or not d.usuario.activo:
        raise ErrorNegocio("The verification expired. Sign in again.", 401, "desafio_invalido")
    return d


def reenviar(db: Session, token: str) -> dict:
    d = _desafio(db, token)
    espera = settings.CODIGO_REENVIO_SEG - int((_ahora() - d.ultimo_envio).total_seconds())
    if espera > 0:
        raise ErrorNegocio(f"Wait {espera} s to request a new code.", 429, "espera")
    if d.envios >= ENVIOS_MAX:
        d.usado = True
        db.commit()
        raise ErrorNegocio("Too many codes requested. Sign in again.", 429, "demasiados_envios")
    d.envios += 1
    codigo = _enviar_codigo(d, token)
    db.commit()
    return _respuesta_desafio(d, token, codigo)


def verificar(db: Session, token: str, codigo: str, ip: str | None, agente: str | None) -> str:
    d = _desafio(db, token)
    if d.expira < _ahora():
        raise ErrorNegocio("The code expired. Request a new one.", 401, "codigo_vencido")
    if not hmac.compare_digest(d.codigo_hash, _hash_codigo(token, (codigo or "").strip())):
        d.intentos += 1
        if d.intentos >= INTENTOS_CODIGO:
            d.usado = True
            registrar(db, d.usuario, "usuario", d.usuario_id, "codigo_fallido", {"ip": ip})
            db.commit()
            raise ErrorNegocio("Too many wrong codes. Sign in again.", 401, "desafio_invalido")
        db.commit()
        raise ErrorNegocio(f"Incorrect code. {INTENTOS_CODIGO - d.intentos} attempts left.", 401, "codigo_incorrecto")
    d.usado = True
    return crear_sesion(db, d.usuario, ip, agente)


# ---- Sesiones -----------------------------------------------------------------
def crear_sesion(db: Session, u: Usuario, ip: str | None, agente: str | None) -> str:
    token = secrets.token_urlsafe(32)
    ahora = _ahora()
    db.add(SesionUsuario(token_hash=_hash(token), usuario_id=u.id, creada=ahora, ultima_actividad=ahora,
                         expira=ahora + timedelta(hours=settings.SESION_HORAS), ip=ip, agente=(agente or "")[:300]))
    u.ultimo_acceso = ahora
    registrar(db, u, "usuario", u.id, "inicio_sesion", {"ip": ip})
    db.commit()
    return token


def usuario_de_sesion(db: Session, token: str) -> Usuario | None:
    s = db.scalar(select(SesionUsuario).where(SesionUsuario.token_hash == _hash(token)))
    ahora = _ahora()
    if (not s or s.revocada or s.expira < ahora
            or s.ultima_actividad + timedelta(minutes=settings.SESION_INACTIVIDAD_MIN) < ahora
            or not s.usuario.activo):
        return None
    # Renueva la inactividad sin escribir en cada petición
    if (ahora - s.ultima_actividad).total_seconds() > 60:
        s.ultima_actividad = ahora
        db.commit()
    return s.usuario


def cerrar_sesion(db: Session, token: str | None) -> None:
    if token:
        db.execute(update(SesionUsuario).where(SesionUsuario.token_hash == _hash(token)).values(revocada=True))
        db.commit()


def revocar_sesiones(db: Session, usuario_id: int, excepto: str | None = None) -> None:
    q = update(SesionUsuario).where(SesionUsuario.usuario_id == usuario_id, SesionUsuario.revocada.is_(False))
    if excepto:
        q = q.where(SesionUsuario.token_hash != _hash(excepto))
    db.execute(q.values(revocada=True))


def cambiar_password(db: Session, u: Usuario, actual: str, nueva: str, token_actual: str | None) -> None:
    if not verificar_password(actual, u.password_hash):
        raise ErrorNegocio("The current password is incorrect.", 422, "validacion",
                           [{"campo": "actual", "mensaje": "Incorrect password."}])
    exigir_politica(nueva, u.email)
    if verificar_password(nueva, u.password_hash):
        raise ErrorNegocio("The new password must be different.", 422, "validacion")
    u.password_hash = hash_password(nueva)
    u.password_cambiado_en = _ahora()
    u.clave_temporal = False
    revocar_sesiones(db, u.id, excepto=token_actual)
    registrar(db, u, "usuario", u.id, "cambio_password", None)
