import base64
import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone

import jwt

from .config import settings

_ITERACIONES = 200_000


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _ITERACIONES)
    return f"pbkdf2${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def verificar_password(password: str, guardado: str) -> bool:
    try:
        _, salt_b64, hash_b64 = guardado.split("$")
    except ValueError:
        return False
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), base64.b64decode(salt_b64), _ITERACIONES)
    return hmac.compare_digest(dk, base64.b64decode(hash_b64))


def crear_token(usuario_id: int) -> str:
    exp = datetime.now(timezone.utc) + timedelta(hours=settings.TOKEN_HORAS)
    return jwt.encode({"sub": str(usuario_id), "exp": exp}, settings.SECRET_KEY, algorithm="HS256")


def leer_token(token: str) -> int | None:
    try:
        datos = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        return int(datos["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None
