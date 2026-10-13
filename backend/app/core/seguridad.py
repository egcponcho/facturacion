"""Contraseñas: PBKDF2-SHA256 con sal propia por usuario.

El hash guarda sus iteraciones (`pbkdf2_sha256$<iteraciones>$<sal>$<hash>`),
así se pueden subir con el tiempo: al iniciar sesión, un hash con menos
iteraciones que las actuales se recalcula (`necesita_rehash`). Los hashes del
formato anterior (`pbkdf2$<sal>$<hash>`) usaban 200 000 iteraciones.
"""
import base64
import hashlib
import hmac
import os

# Recomendación de OWASP para PBKDF2-SHA256 (2023). Las pruebas la bajan con
# PBKDF2_ITERACIONES para no tardar.
ITERACIONES = int(os.getenv("PBKDF2_ITERACIONES", "600000"))
_ANTERIOR = 200_000


def _calcular(password: str, salt: bytes, iteraciones: int) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iteraciones)


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = _calcular(password, salt, ITERACIONES)
    return f"pbkdf2_sha256${ITERACIONES}${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def _partes(guardado: str) -> tuple[int, bytes, bytes] | None:
    try:
        partes = guardado.split("$")
        if partes[0] == "pbkdf2_sha256" and len(partes) == 4:
            return int(partes[1]), base64.b64decode(partes[2]), base64.b64decode(partes[3])
        if partes[0] == "pbkdf2" and len(partes) == 3:
            return _ANTERIOR, base64.b64decode(partes[1]), base64.b64decode(partes[2])
    except (ValueError, AttributeError):
        return None
    return None


def verificar_password(password: str, guardado: str) -> bool:
    partes = _partes(guardado or "")
    if not partes:
        return False
    iteraciones, salt, esperado = partes
    return hmac.compare_digest(_calcular(password, salt, iteraciones), esperado)


def necesita_rehash(guardado: str) -> bool:
    """Si el hash no está en el formato y las iteraciones actuales."""
    return not (guardado or "").startswith(f"pbkdf2_sha256${ITERACIONES}$")
