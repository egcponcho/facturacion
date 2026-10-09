"""Configuración de la instalación (variables de entorno).

Aquí solo va lo que depende del servidor: base de datos, claves, acceso
seguro, SMS y archivos. Todo lo que es del negocio (reglas, preferencias,
catálogos, roles…) se guarda en la base de datos y se cambia desde la
aplicación; los valores de «Reglas de negocio» de abajo solo son los de
fábrica para una instalación nueva.

La lista completa de lo que hay que definir en producción está en
docs/PRODUCCION.md y en backend/.env.example.
"""
import logging
import os
import secrets


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
    # Firma las sesiones y los códigos de verificación. Obligatoria: sin ella
    # (o con menos de 32 caracteres) el servidor no arranca. Solo la
    # demostración, si no se define, usa una clave al azar por arranque.
    SECRET_KEY: str = os.getenv("SECRET_KEY", "")

    # ---- Acceso seguro -----------------------------------------------------
    # La sesión vive en una cookie httpOnly (el navegador no la expone a
    # JavaScript). Vence tras SESION_INACTIVIDAD_MIN sin uso o a las
    # SESION_HORAS desde que se inició.
    SESION_HORAS: int = int(os.getenv("SESION_HORAS", "12"))
    SESION_INACTIVIDAD_MIN: int = int(os.getenv("SESION_INACTIVIDAD_MIN", "30"))
    # La cookie de sesión solo viaja por https. Apagarla solo en desarrollo
    # local sin https (COOKIE_SEGURA=0).
    COOKIE_SEGURA: bool = _bool("COOKIE_SEGURA", True)
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
    # Tamaño máximo de una petición (archivos que se suben), en MB
    MAX_SUBIDA_MB: int = int(os.getenv("MAX_SUBIDA_MB", "25"))
    # Clasificación arancelaria: país cuyo código nacional completa la partida sugerida
    # (valor de fábrica; cada empresa lo elige en Configuración → Empresa)
    PAIS_BASE_CLASIF: str = os.getenv("PAIS_BASE_CLASIF", "").upper()
    # Opinión del especialista con Claude (opcional): sin clave, la opción no aparece
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    CLAUDE_MODELO: str = os.getenv("CLAUDE_MODELO", "claude-opus-5-5")
    FRONTEND_DIST: str = os.getenv("FRONTEND_DIST", "../frontend/dist")
    # Demostración: carga datos de ejemplo (empresa, proveedores, órdenes,
    # facturas…) en una base vacía. Es lo único que cambia: el esquema, las
    # migraciones y la seguridad son los mismos que en producción.
    SEED_DEMO: bool = _bool("SEED_DEMO", False)
    # Instalación nueva (sin usuarios): nombre de la empresa y primer
    # administrador. La contraseña es temporal: se cambia al primer ingreso.
    EMPRESA_NOMBRE: str = os.getenv("EMPRESA_NOMBRE", "")
    ADMIN_EMAIL: str = os.getenv("ADMIN_EMAIL", "")
    ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "")
    ADMIN_TELEFONO: str = os.getenv("ADMIN_TELEFONO", "")
    CORS_ORIGINS: list[str] = [
        o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()
    ]

    # ---- Reglas de negocio (valores de fábrica) ------------------------------
    # Cada empresa las cambia en Configuración → Empresa; estos valores solo
    # se usan mientras no lo haya hecho.
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
    COMPATIBILIDAD_BLOQUEANTE: list[str] = ["sociedad", "moneda", "centro"]
    # Holgura mínima (días) frente a la fecha en tienda para considerarse "en tiempo";
    # con menos queda "en riesgo" y con holgura negativa, "atrasado"
    DIAS_MARGEN_RIESGO: int = 7
    # Días antes de la fecha en tienda a partir de los que una OC se resalta
    DIAS_AVISO_TIENDA: int = 30
    COMPATIBILIDAD_ADVERTENCIA: list[str] = ["incoterm", "centro_destino"]


    def validar(self) -> None:
        """Revisa la configuración al arrancar: sin una clave secreta propia el
        servidor no arranca (salvo la demostración, que usa una al azar)."""
        log = logging.getLogger("configuracion")
        if not self.SECRET_KEY:
            if not self.SEED_DEMO:
                raise RuntimeError("Falta SECRET_KEY: defina una clave al azar de 32 caracteres o más "
                                   "(ver docs/PRODUCCION.md).")
            self.SECRET_KEY = secrets.token_urlsafe(48)
            log.warning("Demostración sin SECRET_KEY: se usa una clave al azar; las sesiones se cierran al reiniciar.")
        if len(self.SECRET_KEY) < 32:
            raise RuntimeError("SECRET_KEY es muy corta: use 32 caracteres o más.")
        if not self.SEED_DEMO:
            if not self.COOKIE_SEGURA:
                log.warning("COOKIE_SEGURA=0: la sesión puede viajar sin https. Úselo solo en desarrollo local.")
            if self.DOS_PASOS and self.SMS_PROVEEDOR == "consola":
                log.warning("SMS_PROVEEDOR=consola: los códigos de verificación solo quedan en el registro del "
                            "servidor. Configure twilio para enviarlos por SMS.")


settings = Settings()
