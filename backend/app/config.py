"""Configuración general y reglas de negocio.

Las reglas que todavía pueden cambiar en el negocio se controlan aquí,
para no tener que tocar el modelo de datos cuando cambien.
"""
import os


def _bool(nombre: str, defecto: bool) -> bool:
    valor = os.getenv(nombre)
    if valor is None:
        return defecto
    return valor.strip().lower() in ("1", "true", "si", "sí", "yes", "y")


def _url_bd(url: str) -> str:
    # Los proveedores en la nube (Render, Railway, Heroku) entregan la URL como
    # postgres:// o postgresql://; SQLAlchemy necesita el driver explícito.
    for prefijo in ("postgres://", "postgresql://"):
        if url.startswith(prefijo):
            return "postgresql+psycopg://" + url[len(prefijo):]
    return url


class Settings:
    DATABASE_URL: str = _url_bd(os.getenv("DATABASE_URL", "sqlite:///./facturas_pl.db"))
    SECRET_KEY: str = os.getenv("SECRET_KEY", "cambia-esta-clave-en-produccion-con-32-caracteres-o-mas")

    # ---- Acceso seguro -----------------------------------------------------
    # La sesión vive en una cookie httpOnly (el navegador no la expone a
    # JavaScript). Vence tras SESION_INACTIVIDAD_MIN sin uso o a las
    # SESION_HORAS desde que se inició.
    SESION_HORAS: int = int(os.getenv("SESION_HORAS", "12"))
    SESION_INACTIVIDAD_MIN: int = int(os.getenv("SESION_INACTIVIDAD_MIN", "30"))
    COOKIE_SEGURA: bool = _bool("COOKIE_SEGURA", False)  # True detrás de https (producción)
    # Bloqueo tras intentos fallidos de contraseña
    INTENTOS_MAX: int = int(os.getenv("INTENTOS_MAX", "5"))
    BLOQUEO_MIN: int = int(os.getenv("BLOQUEO_MIN", "15"))
    # Verificación en dos pasos por SMS al celular registrado del usuario
    DOS_PASOS: bool = _bool("DOS_PASOS", True)
    CODIGO_VALIDEZ_MIN: int = int(os.getenv("CODIGO_VALIDEZ_MIN", "5"))
    CODIGO_REENVIO_SEG: int = int(os.getenv("CODIGO_REENVIO_SEG", "30"))
    # consola: el código se escribe en el log (y, en modo demo, se muestra en
    # pantalla). twilio: se envía por SMS con las credenciales de abajo.
    SMS_PROVEEDOR: str = os.getenv("SMS_PROVEEDOR", "consola")
    TWILIO_ACCOUNT_SID: str = os.getenv("TWILIO_ACCOUNT_SID", "")
    TWILIO_AUTH_TOKEN: str = os.getenv("TWILIO_AUTH_TOKEN", "")
    TWILIO_FROM: str = os.getenv("TWILIO_FROM", "")
    UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", "./archivos")
    # Clasificación arancelaria: país cuyo código nacional completa la partida sugerida
    PAIS_BASE_CLASIF: str = os.getenv("PAIS_BASE_CLASIF", "SV").upper()
    # Opinión del especialista con Claude (opcional): sin clave, la opción no aparece
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    CLAUDE_MODELO: str = os.getenv("CLAUDE_MODELO", "claude-opus-5-5")
    FRONTEND_DIST: str = os.getenv("FRONTEND_DIST", "../frontend/dist")
    SEED_DEMO: bool = _bool("SEED_DEMO", True)
    # Versión del esquema de datos. En modo demo (SEED_DEMO=1), si la base
    # tiene otra versión se borra y se vuelve a crear con los datos de prueba.
    ESQUEMA_VERSION: str = "34"
    CORS_ORIGINS: list[str] = [
        o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()
    ]

    # ---- Reglas de negocio -------------------------------------------------
    # False: una posición de OC solo puede estar en UNA factura activa.
    #        La factura puede tomar una parte; el saldo solo se agrega a esa
    #        misma factura (o a otra si se quita de la primera).
    # True:  el saldo puede ir a otras facturas mientras la primera sigue activa.
    POSICION_EN_VARIAS_FACTURAS: bool = _bool("POSICION_EN_VARIAS_FACTURAS", False)

    # True: todos los PL de una factura deben ir en la misma unidad de carga.
    FACTURA_EN_UNA_SOLA_UNIDAD: bool = _bool("FACTURA_EN_UNA_SOLA_UNIDAD", False)

    # El proveedor puede finalizar sus facturas y PL (flujo Borrador -> Finalizado).
    PROVEEDOR_PUEDE_FINALIZAR: bool = _bool("PROVEEDOR_PUEDE_FINALIZAR", True)

    # Exige país de origen y partida arancelaria por línea para finalizar.
    REQUERIR_DATOS_ADUANA: bool = _bool("REQUERIR_DATOS_ADUANA", True)

    # Días para avisar de borradores que siguen reservando cantidades.
    DIAS_ALERTA_BORRADOR: int = int(os.getenv("DIAS_ALERTA_BORRADOR", "7"))

    # Campos de la OC que no se pueden mezclar en una factura (bloquean)
    # y campos que solo generan advertencia.
    COMPATIBILIDAD_BLOQUEANTE: tuple[str, ...] = ("sociedad", "moneda", "centro")
    # Holgura mínima (días) frente a la fecha en tienda para considerarse "en tiempo";
    # con menos queda "en riesgo" y con holgura negativa, "atrasado"
    DIAS_MARGEN_RIESGO: int = 7
    COMPATIBILIDAD_ADVERTENCIA: tuple[str, ...] = ("incoterm", "centro_destino")



settings = Settings()
