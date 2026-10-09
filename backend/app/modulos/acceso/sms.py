"""Envío de SMS para la verificación en dos pasos.

- consola: escribe el mensaje en el log del servidor (desarrollo y demo).
- twilio: usa la API REST de Twilio (TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN y
  TWILIO_FROM). Sin dependencias extra: una petición HTTPS con urllib.
"""
import base64
import logging
import urllib.error
import urllib.parse
import urllib.request

from app.core.config import settings
from app.core.errores import ErrorNegocio

log = logging.getLogger("sms")


def enviar_sms(telefono: str, mensaje: str) -> None:
    if settings.SMS_PROVEEDOR == "twilio":
        _twilio(telefono, mensaje)
        return
    log.warning("SMS a %s: %s", telefono, mensaje)


def _twilio(telefono: str, mensaje: str) -> None:
    sid, token, origen = settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN, settings.TWILIO_FROM
    if not (sid and token and origen):
        raise ErrorNegocio("SMS delivery is not configured. Contact the administrator.", 503, "sms_no_configurado")
    url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
    datos = urllib.parse.urlencode({"To": telefono, "From": origen, "Body": mensaje}).encode()
    req = urllib.request.Request(url, data=datos, method="POST")
    req.add_header("Authorization", "Basic " + base64.b64encode(f"{sid}:{token}".encode()).decode())
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            if r.status >= 300:
                raise ErrorNegocio("The verification code could not be sent. Try again.", 502, "sms_fallo")
    except urllib.error.URLError as e:
        log.error("Twilio: %s", e)
        raise ErrorNegocio("The verification code could not be sent. Try again.", 502, "sms_fallo") from e
