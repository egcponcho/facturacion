"""Modelo de datos.

Todo se maneja por cantidades:
  Posición OC --(FacturaLinea.cantidad)--> Factura
  FacturaLinea --(PLLinea.cantidad)--> Packing list
  PLLinea --(GrupoCajasItem.cantidad_por_caja x GrupoCajas.num_cajas)--> Cajas
  Packing list --> Unidad de carga (contenedor, aéreo, LCL...) --> Embarque
"""
from datetime import date, datetime, timezone

from sqlalchemy import (
    JSON,
    Column,
    Table,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def ahora() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# --------------------------------------------------------------------------
# Relaciones muchos a muchos de los maestros
# --------------------------------------------------------------------------
proveedor_marcas = Table(
    "proveedor_marcas", Base.metadata,
    Column("proveedor_id", ForeignKey("proveedores.id", ondelete="CASCADE"), primary_key=True),
    Column("marca_id", ForeignKey("marcas.id", ondelete="CASCADE"), primary_key=True),
)
proveedor_sociedades = Table(
    "proveedor_sociedades", Base.metadata,
    Column("proveedor_id", ForeignKey("proveedores.id", ondelete="CASCADE"), primary_key=True),
    Column("sociedad_id", ForeignKey("sociedades.id", ondelete="CASCADE"), primary_key=True),
)
transportista_sociedades = Table(
    "transportista_sociedades", Base.metadata,
    Column("transportista_id", ForeignKey("transportistas.id", ondelete="CASCADE"), primary_key=True),
    Column("sociedad_id", ForeignKey("sociedades.id", ondelete="CASCADE"), primary_key=True),
)
# Qué tipos de empaque puede llevar dentro cada tipo (relación configurable)
tipo_empaque_contiene = Table(
    "tipo_empaque_contiene", Base.metadata,
    Column("padre_id", ForeignKey("tipos_empaque.id", ondelete="CASCADE"), primary_key=True),
    Column("hijo_id", ForeignKey("tipos_empaque.id", ondelete="CASCADE"), primary_key=True),
)
centro_puertos = Table(
    "centro_puertos", Base.metadata,
    Column("centro_id", ForeignKey("centros.id", ondelete="CASCADE"), primary_key=True),
    Column("puerto_id", ForeignKey("puertos.id", ondelete="CASCADE"), primary_key=True),
)


# --------------------------------------------------------------------------
# Usuarios y proveedores
# --------------------------------------------------------------------------
class Proveedor(Base):
    """Proveedor (exportador). Maneja sus propias marcas y artículos y solo
    trabaja con las sociedades que tiene asignadas."""

    __tablename__ = "proveedores"
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(30), unique=True)
    nombre: Mapped[str] = mapped_column(String(200))
    razon_social: Mapped[str | None] = mapped_column(String(200))
    id_fiscal: Mapped[str | None] = mapped_column(String(40))
    pais: Mapped[str | None] = mapped_column(String(2))
    direccion: Mapped[str | None] = mapped_column(String(300))
    contacto: Mapped[str | None] = mapped_column(String(120))
    correos: Mapped[str | None] = mapped_column(String(500))
    telefono: Mapped[str | None] = mapped_column(String(40))
    activo: Mapped[bool] = mapped_column(Boolean, default=True)

    marcas: Mapped[list["Marca"]] = relationship(secondary=proveedor_marcas, order_by="Marca.codigo")
    sociedades: Mapped[list["Sociedad"]] = relationship(secondary=proveedor_sociedades, order_by="Sociedad.codigo")


class Transportista(Base):
    """Naviera, aerolínea o empresa de transporte terrestre registrada, con
    las sociedades para las que puede trabajar."""

    __tablename__ = "transportistas"
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(20), unique=True)
    nombre: Mapped[str] = mapped_column(String(150))
    tipo: Mapped[str] = mapped_column(String(12))  # MARITIMO | AEREO | TERRESTRE | MULTIMODAL
    codigo_internacional: Mapped[str | None] = mapped_column(String(10))  # SCAC o prefijo IATA
    id_fiscal: Mapped[str | None] = mapped_column(String(40))
    pais: Mapped[str | None] = mapped_column(String(2))
    contacto: Mapped[str | None] = mapped_column(String(120))
    correos: Mapped[str | None] = mapped_column(String(500))
    telefono: Mapped[str | None] = mapped_column(String(40))
    activo: Mapped[bool] = mapped_column(Boolean, default=True)

    sociedades: Mapped[list["Sociedad"]] = relationship(secondary=transportista_sociedades, order_by="Sociedad.codigo")


class TipoUnidad(Base):
    """Tipo de unidad de carga por modo de transporte (contenedores, LCL,
    guía aérea, camión…) con su capacidad nominal."""

    __tablename__ = "tipos_unidad"
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(10), unique=True)
    nombre: Mapped[str] = mapped_column(String(100))
    modo: Mapped[str] = mapped_column(String(12))  # MARITIMO | AEREO | TERRESTRE
    modalidad: Mapped[str] = mapped_column(String(10))  # FCL | LCL | AEREO | FTL | LTL
    capacidad_cbm: Mapped[float | None] = mapped_column(Float)
    capacidad_kg: Mapped[float | None] = mapped_column(Float)
    requiere_sello: Mapped[bool] = mapped_column(Boolean, default=False)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class Rol(Base):
    """Rol con sus permisos: el tipo dice qué datos ve el usuario (el
    proveedor solo lo suyo) y los permisos, a qué módulos y acciones entra."""

    __tablename__ = "roles"
    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(80), unique=True)
    descripcion: Mapped[str | None] = mapped_column(String(300))
    tipo: Mapped[str] = mapped_column(String(20))  # admin | interno | proveedor
    permisos: Mapped[list] = mapped_column(JSON, default=list)
    sistema: Mapped[bool] = mapped_column(Boolean, default=False)  # los de fábrica no se borran
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class Usuario(Base):
    __tablename__ = "usuarios"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(200), unique=True)
    nombre: Mapped[str] = mapped_column(String(200))
    rol: Mapped[str] = mapped_column(String(20))  # tipo del rol: admin | interno | proveedor
    rol_id: Mapped[int | None] = mapped_column(ForeignKey("roles.id"))
    proveedor_id: Mapped[int | None] = mapped_column(ForeignKey("proveedores.id"))
    password_hash: Mapped[str] = mapped_column(String(300))
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    # Seguridad del acceso: celular registrado para la verificación en dos
    # pasos, intentos fallidos y bloqueo temporal.
    telefono: Mapped[str | None] = mapped_column(String(20))  # formato E.164: +50370000000
    dos_pasos: Mapped[bool] = mapped_column(Boolean, default=True)
    intentos_fallidos: Mapped[int] = mapped_column(Integer, default=0)
    bloqueado_hasta: Mapped[datetime | None] = mapped_column(DateTime)
    ultimo_acceso: Mapped[datetime | None] = mapped_column(DateTime)
    password_cambiado_en: Mapped[datetime | None] = mapped_column(DateTime)
    # Idioma, formatos de fecha/hora/número, tema, filas por página (solo lo que difiere del defecto)
    preferencias: Mapped[dict] = mapped_column(JSON, default=dict)
    # Datos del perfil: la foto la cambia el usuario; cargo, área y empresa, la administración
    foto: Mapped[str | None] = mapped_column(Text)  # imagen pequeña (data URL)
    cargo: Mapped[str | None] = mapped_column(String(120))
    area: Mapped[str | None] = mapped_column(String(120))
    empresa: Mapped[str | None] = mapped_column(String(200))
    # Contraseña temporal (creada o restablecida por la administración): hasta
    # cambiarla, el usuario solo puede completar el asistente inicial
    clave_temporal: Mapped[bool] = mapped_column(Boolean, default=False)
    proveedor: Mapped[Proveedor | None] = relationship()
    rol_ref: Mapped[Rol | None] = relationship()


class SesionUsuario(Base):
    """Sesión iniciada. La cookie lleva un token aleatorio; aquí solo se guarda
    su hash. Vence por inactividad y por duración máxima, y se revoca al
    cerrar sesión o al cambiar la contraseña."""

    __tablename__ = "sesiones"
    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), index=True)
    creada: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    expira: Mapped[datetime] = mapped_column(DateTime)
    ultima_actividad: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    ip: Mapped[str | None] = mapped_column(String(64))
    agente: Mapped[str | None] = mapped_column(String(300))
    revocada: Mapped[bool] = mapped_column(Boolean, default=False)

    usuario: Mapped[Usuario] = relationship()


class DesafioDosPasos(Base):
    """Código de un solo uso enviado por SMS al celular registrado."""

    __tablename__ = "desafios_dos_pasos"
    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), index=True)
    codigo_hash: Mapped[str] = mapped_column(String(64))
    expira: Mapped[datetime] = mapped_column(DateTime)
    intentos: Mapped[int] = mapped_column(Integer, default=0)
    envios: Mapped[int] = mapped_column(Integer, default=1)
    ultimo_envio: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    usado: Mapped[bool] = mapped_column(Boolean, default=False)

    usuario: Mapped[Usuario] = relationship()


# --------------------------------------------------------------------------
# Órdenes de compra
# --------------------------------------------------------------------------
class Sociedad(Base):
    """Sociedad legal (compañía de SAP). Sus centros son bodegas fiscales."""

    __tablename__ = "sociedades"
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(10), unique=True)
    nombre: Mapped[str] = mapped_column(String(120))
    razon_social: Mapped[str | None] = mapped_column(String(200))
    id_fiscal: Mapped[str | None] = mapped_column(String(30))  # NIT / RUC
    pais: Mapped[str | None] = mapped_column(String(2))
    moneda: Mapped[str] = mapped_column(String(3), default="USD")
    direccion: Mapped[str | None] = mapped_column(String(300))
    correos: Mapped[str | None] = mapped_column(String(500))  # separados por coma
    activa: Mapped[bool] = mapped_column(Boolean, default=True)

    centros: Mapped[list["Centro"]] = relationship(back_populates="sociedad", order_by="Centro.codigo")


class Centro(Base):
    """Centro de SAP asignado a una sociedad. Es la bodega fiscal a la que
    llega la mercancía (notify party) y, como centro de destino de la OC,
    indica el país final. Su puerto es el de llegada de los embarques."""

    __tablename__ = "centros"
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(10), unique=True)
    sociedad_id: Mapped[int] = mapped_column(ForeignKey("sociedades.id"), index=True)
    nombre: Mapped[str] = mapped_column(String(120))
    tipo: Mapped[str] = mapped_column(String(20), default="BODEGA_FISCAL")
    pais: Mapped[str | None] = mapped_column(String(2))
    puerto: Mapped[str | None] = mapped_column(String(10))  # puerto de llegada
    direccion: Mapped[str | None] = mapped_column(String(300))
    correos: Mapped[str | None] = mapped_column(String(500))
    activo: Mapped[bool] = mapped_column(Boolean, default=True)

    sociedad: Mapped[Sociedad] = relationship(back_populates="centros")
    # Puertos por donde puede llegar (el principal es "puerto"); los del
    # embarque se sugieren de aquí y se pueden cambiar entre ellos
    puertos: Mapped[list["Puerto"]] = relationship(secondary=centro_puertos, order_by="Puerto.codigo")


class Contacto(Base):
    """Persona de contacto de una sociedad (facturación) o de un centro
    (notify party, recepción)."""

    __tablename__ = "contactos"
    id: Mapped[int] = mapped_column(primary_key=True)
    sociedad_id: Mapped[int | None] = mapped_column(ForeignKey("sociedades.id"), index=True)
    centro_id: Mapped[int | None] = mapped_column(ForeignKey("centros.id"), index=True)
    nombre: Mapped[str] = mapped_column(String(120))
    cargo: Mapped[str | None] = mapped_column(String(120))
    rol: Mapped[str] = mapped_column(String(15), default="NOTIFY")  # FACTURACION | NOTIFY | LOGISTICA
    correos: Mapped[str | None] = mapped_column(String(500))
    telefono: Mapped[str | None] = mapped_column(String(40))
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class Almacen(Base):
    """Separación lógica del inventario en el sistema (virtual, detalle,
    mayoreo…); no es un lugar físico. Cada posición de la OC elige el suyo."""

    __tablename__ = "almacenes"
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(10), unique=True)
    sociedad_id: Mapped[int] = mapped_column(ForeignKey("sociedades.id"), index=True)
    nombre: Mapped[str] = mapped_column(String(120))
    tipo: Mapped[str] = mapped_column(String(10))  # VIRTUAL | DETALLE | MAYOREO
    activo: Mapped[bool] = mapped_column(Boolean, default=True)

    sociedad: Mapped[Sociedad] = relationship()


class Pais(Base):
    __tablename__ = "paises"
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(2), unique=True)  # ISO 3166-1 alfa-2
    nombre: Mapped[str] = mapped_column(String(100))
    region: Mapped[str | None] = mapped_column(String(10))  # región de origen para los lead times (ASIA…)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class RegionLeadTime(Base):
    """Región de origen (Asia, Centroamérica…): agrupa países para filtrar,
    comparar y para que un plan de lead time aplique a toda la región."""

    __tablename__ = "regiones_leadtime"
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(10), unique=True)
    nombre: Mapped[str] = mapped_column(String(100))
    predeterminada: Mapped[bool] = mapped_column(Boolean, default=False)  # para orígenes sin región
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class PasoLeadTime(Base):
    """Catálogo de pasos de lead time (Booking, Liberación, XF, ETD, ETA,
    Aduana…). Cada empresa crea los suyos. `hito` enlaza el paso con una fecha
    que el sistema mide (liberación logística, XF, salida, arribo, entrega,
    ingreso, tienda); un paso sin hito es solo de planificación."""

    __tablename__ = "pasos_leadtime"
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(20), unique=True)
    nombre: Mapped[str] = mapped_column(String(100))
    hito: Mapped[str | None] = mapped_column(String(15))
    descripcion: Mapped[str | None] = mapped_column(String(300))
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class ReglaLeadTime(Base):
    """Configuración de lead time de un nivel geográfico: GLOBAL, REGION, PAIS
    o PUERTO. Hereda la del nivel superior (Puerto > País > Región > Global) y
    define solo lo que cambia: pasos que agrega, sobrescribe o quita, y si
    quiere, otro orden. `pasos` es JSON:
        {"pasos": [{"paso", "ref", "dias", "habiles", "modo", "quitar"}], "orden": [códigos] | null}
    `dias` es relativo al paso de referencia (negativo = antes)."""

    __tablename__ = "reglas_leadtime"
    id: Mapped[int] = mapped_column(primary_key=True)
    nivel: Mapped[str] = mapped_column(String(10))  # GLOBAL | REGION | PAIS | PUERTO
    region: Mapped[str | None] = mapped_column(String(10))
    pais: Mapped[str | None] = mapped_column(String(2))
    puerto: Mapped[str | None] = mapped_column(String(10))
    nombre: Mapped[str] = mapped_column(String(100))
    pasos: Mapped[str] = mapped_column(Text, default="{}")
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class AcuerdoComercial(Base):
    """Tratado o acuerdo comercial vigente: mercancías originarias de sus países
    de origen entran con preferencia arancelaria a sus países destino si se
    presenta la prueba de origen que pide."""

    __tablename__ = "acuerdos_comerciales"
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(20), unique=True)
    nombre: Mapped[str] = mapped_column(String(200))
    origenes: Mapped[str] = mapped_column(String(400))  # ISO separados por coma (US,DO)
    destinos: Mapped[str] = mapped_column(String(100))  # ISO de los países destino (GT,SV,HN…)
    prueba: Mapped[str | None] = mapped_column(String(200))  # certificado o declaración de origen
    nota: Mapped[str | None] = mapped_column(String(300))
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class Puerto(Base):
    __tablename__ = "puertos"
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(10), unique=True)  # UN/LOCODE
    nombre: Mapped[str] = mapped_column(String(100))
    pais: Mapped[str] = mapped_column(String(2))
    tipo: Mapped[str] = mapped_column(String(12), default="MARITIMO")
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class Marca(Base):
    __tablename__ = "marcas"
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(10), unique=True)
    nombre: Mapped[str] = mapped_column(String(100))
    activa: Mapped[bool] = mapped_column(Boolean, default=True)


class EscalaTalla(Base):
    """Escala de tallas reutilizable (calzado, ropa, accesorios u otra): sus
    tallas en orden y cómo se forma el código de cada talla. Los genéricos
    parten de una escala; el código se genera con la regla o se escribe."""

    __tablename__ = "escalas_talla"
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(20), unique=True)
    nombre: Mapped[str] = mapped_column(String(120))
    categoria: Mapped[str | None] = mapped_column(String(20))
    # MULTIPLICAR: talla numérica × factor (7.5 × 10 → 075); CONSECUTIVO: 001, 002…;
    # TALLA: la misma talla (S, M, XL). Un código escrito en la lista manda.
    regla: Mapped[str] = mapped_column(String(15), default="CONSECUTIVO")
    factor: Mapped[int | None] = mapped_column(Integer, default=10)
    longitud: Mapped[int | None] = mapped_column(Integer, default=3)
    tallas: Mapped[str] = mapped_column(Text)  # "6, 6.5, 7=070, 8-10" o "S, M, L"
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class GrupoArticulo(Base):
    """Grupo de artículos. La categoría decide la regla de empaque:
    calzado (casepack exacto, sin mezclar tallas) o ropa y accesorios."""

    __tablename__ = "grupos_articulos"
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(15), unique=True)
    nombre: Mapped[str] = mapped_column(String(100))
    categoria: Mapped[str] = mapped_column(String(10))  # CALZADO | ROPA | ACCESORIO
    # Días que este tipo de producto necesita además de los de su región después
    # del puerto (inspección, etiquetado, permisos); se suman a la fecha en tienda
    dias_extra: Mapped[int | None] = mapped_column(Integer)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class Prepack(Base):
    """Curva de un estilo-color. Su prepack ID (p. ej. AB12) es la "talla"
    del artículo prepack y se arma con sólidos del mismo estilo y color."""

    __tablename__ = "prepacks"
    __table_args__ = (UniqueConstraint("estilo", "color", "codigo"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(10))
    estilo: Mapped[str] = mapped_column(String(40))
    color: Mapped[str | None] = mapped_column(String(60))
    descripcion: Mapped[str | None] = mapped_column(String(200))
    activo: Mapped[bool] = mapped_column(Boolean, default=True)

    componentes: Mapped[list["PrepackComponente"]] = relationship(
        back_populates="prepack", cascade="all, delete-orphan", order_by="PrepackComponente.id"
    )

    @property
    def total(self) -> int:
        return sum(c.cantidad for c in self.componentes)


class Producto(Base):
    """Ficha técnica de un estilo-color de un proveedor. La comparten todas sus
    tallas (artículos) y sus prepacks; aquí vive su clasificación arancelaria:
    la partida SAC aprobada y el código nacional de cada país destino."""

    __tablename__ = "productos"
    __table_args__ = (UniqueConstraint("proveedor_id", "estilo", "color"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    proveedor_id: Mapped[int] = mapped_column(ForeignKey("proveedores.id"), index=True)
    estilo: Mapped[str] = mapped_column(String(40))
    color: Mapped[str | None] = mapped_column(String(60))
    marca_id: Mapped[int | None] = mapped_column(ForeignKey("marcas.id"), index=True)
    grupo_id: Mapped[int | None] = mapped_column(ForeignKey("grupos_articulos.id"))
    # Genérico: los primeros 8 dígitos del código de artículo (estilo-color). Todas
    # sus tallas (los 3 últimos dígitos), sólidos y prepacks, comparten esta ficha
    codigo_generico: Mapped[str | None] = mapped_column(String(40), unique=True, index=True)
    unidad: Mapped[str | None] = mapped_column(String(5))  # unidad de sus tallas sólidas: PAR | UN
    nombre: Mapped[str | None] = mapped_column(String(200))  # nombre comercial del estilo
    # Ficha técnica: tipo de producto del clasificador, atributos, composición
    # por parte, uso, tallas, usuario y datos que piden los aranceles nacionales
    tipo: Mapped[str | None] = mapped_column(String(30))
    ficha: Mapped[dict] = mapped_column(JSON, default=dict)
    # Dos descripciones que se arman solas con la ficha (se pueden editar):
    # la técnica en español para la DUCA y la comercial para catálogos y documentos
    descripcion_aduana: Mapped[str | None] = mapped_column(String(400))
    descripcion_comercial: Mapped[str | None] = mapped_column(String(300))
    pais_origen: Mapped[str | None] = mapped_column(String(2))
    pais_procedencia: Mapped[str | None] = mapped_column(String(2))
    ficha_completa: Mapped[bool] = mapped_column(Boolean, default=False)
    faltan: Mapped[list] = mapped_column(JSON, default=list)
    # Versión de la ficha: al cambiar una ficha aprobada se cierra y se abre otra
    version_ficha: Mapped[int] = mapped_column(Integer, default=1)
    vigente_desde: Mapped[date | None] = mapped_column(Date)
    # borrador | sugerida (borrador completo) | revision (enviada) | aprobado | corregido | observado
    estado: Mapped[str] = mapped_column(String(12), default="borrador", index=True)
    sugerido: Mapped[str | None] = mapped_column(String(14))  # partida del motor
    propuesta: Mapped[str | None] = mapped_column(String(14))  # traída de un archivo o del proveedor
    codigo: Mapped[str | None] = mapped_column(String(14))  # partida aprobada
    confianza: Mapped[str | None] = mapped_column(String(10))
    fuente: Mapped[str | None] = mapped_column(String(12))  # regla | historial | criterio
    perfil: Mapped[str | None] = mapped_column(String(200))
    analisis: Mapped[dict | None] = mapped_column(JSON)  # razones, fundamento, alternativas, alertas
    alertas_ok: Mapped[list] = mapped_column(JSON, default=list)
    observaciones: Mapped[str | None] = mapped_column(String(2000))  # del especialista
    resolucion: Mapped[str | None] = mapped_column(String(200))  # resolución anticipada o criterio DGA
    notas: Mapped[str | None] = mapped_column(String(1000))
    opinion_ia: Mapped[dict | None] = mapped_column(JSON)
    revisado_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    revisado_en: Mapped[datetime | None] = mapped_column(DateTime)
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)  # control de concurrencia

    proveedor: Mapped["Proveedor"] = relationship()
    marca: Mapped["Marca | None"] = relationship()
    grupo: Mapped["GrupoArticulo | None"] = relationship()
    revisado_por: Mapped["Usuario | None"] = relationship()
    articulos: Mapped[list["Articulo"]] = relationship(back_populates="producto", order_by="Articulo.id")
    partidas: Mapped[list["PartidaPais"]] = relationship(
        back_populates="producto", cascade="all, delete-orphan", order_by="PartidaPais.pais"
    )
    fotos: Mapped[list["ProductoFoto"]] = relationship(
        back_populates="producto", cascade="all, delete-orphan", order_by="ProductoFoto.id"
    )
    versiones: Mapped[list["ProductoVersion"]] = relationship(
        back_populates="producto", cascade="all, delete-orphan", order_by="ProductoVersion.version"
    )

    @property
    def aprobado(self) -> bool:
        return self.estado in ("aprobado", "corregido") and bool(self.codigo)


class PartidaPais(Base):
    """Código arancelario nacional del producto en un país destino."""

    __tablename__ = "partidas_pais"
    __table_args__ = (UniqueConstraint("producto_id", "pais"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    producto_id: Mapped[int] = mapped_column(ForeignKey("productos.id", ondelete="CASCADE"), index=True)
    pais: Mapped[str] = mapped_column(String(2))
    codigo: Mapped[str] = mapped_column(String(14))
    dai: Mapped[str | None] = mapped_column(String(10))  # derecho arancelario a la importación, %
    estado: Mapped[str] = mapped_column(String(12))  # ok | auto | sac | nuevo | sinarancel | elegir
    fuente: Mapped[str | None] = mapped_column(String(12))  # base | aprendido | manual | arancel
    manual: Mapped[bool] = mapped_column(Boolean, default=False)

    producto: Mapped[Producto] = relationship(back_populates="partidas")


class ProductoFoto(Base):
    __tablename__ = "producto_fotos"
    id: Mapped[int] = mapped_column(primary_key=True)
    producto_id: Mapped[int] = mapped_column(ForeignKey("productos.id", ondelete="CASCADE"), index=True)
    nombre: Mapped[str] = mapped_column(String(300))
    ruta: Mapped[str] = mapped_column(String(500))
    tipo_mime: Mapped[str] = mapped_column(String(60))
    tamano: Mapped[int] = mapped_column(Integer)
    subido_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    subido_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)

    producto: Mapped[Producto] = relationship(back_populates="fotos")


class ProductoVersion(Base):
    """Versión cerrada de la ficha técnica, con su vigencia y la partida que tenía."""

    __tablename__ = "producto_versiones"
    id: Mapped[int] = mapped_column(primary_key=True)
    producto_id: Mapped[int] = mapped_column(ForeignKey("productos.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    desde: Mapped[date | None] = mapped_column(Date)
    hasta: Mapped[date | None] = mapped_column(Date)
    motivo: Mapped[str | None] = mapped_column(String(300))
    datos: Mapped[dict] = mapped_column(JSON)  # copia de la ficha y su clasificación
    cerrado_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    cerrado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)

    producto: Mapped[Producto] = relationship(back_populates="versiones")


class PaisArancel(Base):
    """País destino con arancel propio: cuántos dígitos usa su código nacional
    y si pertenece al Mercado Común Centroamericano (comparte el SAC a 8-10
    dígitos). Se pueden agregar países y cargar sus códigos."""

    __tablename__ = "paises_arancel"
    id: Mapped[int] = mapped_column(primary_key=True)
    iso: Mapped[str] = mapped_column(String(2), unique=True)
    nombre: Mapped[str] = mapped_column(String(80))
    digitos: Mapped[int] = mapped_column(Integer, default=10)  # longitud habitual (sugerencia, no regla fija)
    # Esquema del código nacional: longitudes admitidas (p. ej. "8,10,12"); vacío = 8 a 14 dígitos
    longitudes: Mapped[str | None] = mapped_column(String(40))
    nivel_base: Mapped[str | None] = mapped_column(String(10))  # HS6 | SAC8: de qué nivel cuelga la precisión nacional
    modelo_arancel: Mapped[str | None] = mapped_column(String(120))  # SAC regional + precisión nacional, nacional propio…
    contexto: Mapped[str | None] = mapped_column(String(120))
    fuente_id: Mapped[int | None] = mapped_column(ForeignKey("fuentes_oficiales.id"))
    mcca: Mapped[bool] = mapped_column(Boolean, default=False)
    impuesto: Mapped[str | None] = mapped_column(String(60))  # p. ej. "VAT 13%"
    nota: Mapped[str | None] = mapped_column(String(300))
    base_legal: Mapped[str | None] = mapped_column(String(300))  # arancel y norma que lo pone en vigor
    orden: Mapped[int] = mapped_column(Integer, default=0)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class FuenteOficial(Base):
    """Fuente oficial de datos arancelarios (SIECA, SAT, DGA, ATENA, ANA…):
    de dónde sale cada dato, cómo se consulta y cuándo se verificó."""

    __tablename__ = "fuentes_oficiales"
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(30), unique=True)  # SRC-SIECA-ACI
    ambito: Mapped[str] = mapped_column(String(20))  # Regional | GT | SV | … | International
    autoridad: Mapped[str] = mapped_column(String(150))
    dataset: Mapped[str] = mapped_column(String(200))
    uso: Mapped[str | None] = mapped_column(String(300))
    url: Mapped[str | None] = mapped_column(String(400))
    acceso: Mapped[str | None] = mapped_column(String(60))  # PDF público, aplicación web, API…
    autenticacion: Mapped[str | None] = mapped_column(String(60))
    nota_version: Mapped[str | None] = mapped_column(String(300))
    verificacion: Mapped[str | None] = mapped_column(String(120))
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class VersionDataset(Base):
    """Versión (instantánea) de un conjunto de datos oficial: el SAC regional,
    el arancel nacional de un país, sus regulaciones… Lo publicado no se
    sobrescribe: una actualización crea otra versión."""

    __tablename__ = "versiones_dataset"
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(30), unique=True)  # SAC-2025-V6
    dataset: Mapped[str] = mapped_column(String(120))
    etiqueta: Mapped[str] = mapped_column(String(200))
    estado: Mapped[str] = mapped_column(String(12), default="BORRADOR")  # BORRADOR | PUBLICADA | DINAMICA | ARCHIVADA
    vigente_desde: Mapped[date | None] = mapped_column(Date)
    vigente_hasta: Mapped[date | None] = mapped_column(Date)
    fuente_id: Mapped[int | None] = mapped_column(ForeignKey("fuentes_oficiales.id"))
    checksum: Mapped[str | None] = mapped_column(String(64))
    nota: Mapped[str | None] = mapped_column(String(400))
    importado_en: Mapped[datetime | None] = mapped_column(DateTime)

    fuente: Mapped[FuenteOficial | None] = relationship()


class ControlCapitulo(Base):
    """Qué capítulos del SAC usa el clasificador: activos, habilitados para
    clasificar, si generan candidatos automáticos o solo se eligen a mano."""

    __tablename__ = "control_capitulos"
    id: Mapped[int] = mapped_column(primary_key=True)
    capitulo: Mapped[str] = mapped_column(String(2), unique=True)
    seccion: Mapped[str | None] = mapped_column(String(6))
    titulo: Mapped[str] = mapped_column(String(400))
    activo: Mapped[bool] = mapped_column(Boolean, default=False)
    clasificacion: Mapped[bool] = mapped_column(Boolean, default=False)  # habilitado para clasificar
    candidato_auto: Mapped[bool] = mapped_column(Boolean, default=False)
    solo_manual: Mapped[bool] = mapped_column(Boolean, default=False)
    archivado: Mapped[bool] = mapped_column(Boolean, default=False)
    alcance: Mapped[str | None] = mapped_column(String(200))  # dominios iniciales (texto de referencia)
    version_id: Mapped[int | None] = mapped_column(ForeignKey("versiones_dataset.id"))
    fuente_id: Mapped[int | None] = mapped_column(ForeignKey("fuentes_oficiales.id"))
    nota: Mapped[str | None] = mapped_column(String(300))

    version: Mapped[VersionDataset | None] = relationship()


class DominioClasificacion(Base):
    """Familia comercial (químicos, materias primas, calzado, ropa,
    accesorios…). Ayuda a elegir preguntas y candidatos; nunca obliga ni
    excluye un capítulo por sí sola."""

    __tablename__ = "dominios_clasificacion"
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(30), unique=True)
    nombre: Mapped[str] = mapped_column(String(100))
    descripcion: Mapped[str | None] = mapped_column(String(400))
    modo: Mapped[str] = mapped_column(String(10), default="AUTO")  # AUTO | MANUAL
    orden: Mapped[int] = mapped_column(Integer, default=0)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)

    capitulos: Mapped[list["DominioCapitulo"]] = relationship(back_populates="dominio", cascade="all, delete-orphan")


class DominioCapitulo(Base):
    """Capítulo relacionado con un dominio: PRIMARY genera candidatos
    automáticos; SECONDARY queda disponible si los datos lo justifican."""

    __tablename__ = "dominio_capitulos"
    __table_args__ = (UniqueConstraint("dominio_id", "capitulo"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    dominio_id: Mapped[int] = mapped_column(ForeignKey("dominios_clasificacion.id", ondelete="CASCADE"), index=True)
    capitulo: Mapped[str] = mapped_column(String(2))
    relevancia: Mapped[str] = mapped_column(String(10), default="PRIMARY")  # PRIMARY | SECONDARY
    habilitado: Mapped[bool] = mapped_column(Boolean, default=True)
    proposito: Mapped[str | None] = mapped_column(String(300))

    dominio: Mapped[DominioClasificacion] = relationship(back_populates="capitulos")


class NotaSAC(Base):
    """Nota legal del SAC (Reglas Generales, notas de sección, de capítulo o de
    subpartida) que se tiene en cuenta al clasificar. `capitulos` dice a qué
    capítulos aplica (vacío: a todos) y `claves` qué datos de la ficha toca."""

    __tablename__ = "notas_sac"
    id: Mapped[int] = mapped_column(primary_key=True)
    ambito: Mapped[str] = mapped_column(String(16))  # reglas | seccion | capitulo | subpartida | complementaria
    codigo: Mapped[str] = mapped_column(String(10))  # RGI, XI, 64…
    numero: Mapped[str] = mapped_column(String(20))
    texto: Mapped[str] = mapped_column(Text)
    capitulos: Mapped[list] = mapped_column(JSON, default=list)
    claves: Mapped[list] = mapped_column(JSON, default=list)
    fuente: Mapped[str] = mapped_column(String(12), default="base")
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)


class PartidaSAC(Base):
    """Subpartida del Sistema Arancelario Centroamericano (6 dígitos) o partida
    (4 dígitos) con su texto oficial."""

    __tablename__ = "partidas_sac"
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(6), unique=True)
    descripcion: Mapped[str] = mapped_column(String(400))
    nota: Mapped[str | None] = mapped_column(String(300))
    fuente: Mapped[str] = mapped_column(String(12), default="base")  # base | manual | archivo
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)


class IncisoNacional(Base):
    """Código nacional conocido de un país (8 a 12 dígitos), con las condiciones
    que lo distinguen dentro de su subpartida: de la base cargada, aprendido al
    confirmar un producto o escrito a mano."""

    __tablename__ = "incisos_nacionales"
    id: Mapped[int] = mapped_column(primary_key=True)
    pais: Mapped[str] = mapped_column(String(2), index=True)
    codigo: Mapped[str] = mapped_column(String(14))
    sub6: Mapped[str] = mapped_column(String(6), index=True)
    cond: Mapped[dict] = mapped_column(JSON, default=dict)
    prio: Mapped[int] = mapped_column(Integer, default=0)
    dai: Mapped[str | None] = mapped_column(String(10))
    descripcion: Mapped[str | None] = mapped_column(String(300))
    nota: Mapped[str | None] = mapped_column(String(300))
    fuente: Mapped[str] = mapped_column(String(12), default="manual")  # base | aprendido | manual | archivo
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    creado_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)


class PalabraClave(Base):
    """Frase del nombre del estilo que el clasificador aprendió a reconocer
    (p. ej. "old skool" es un tenis)."""

    __tablename__ = "clasif_palabras"
    id: Mapped[int] = mapped_column(primary_key=True)
    frase: Mapped[str] = mapped_column(String(100))
    tipo: Mapped[str] = mapped_column(String(30))
    marca: Mapped[str | None] = mapped_column(String(100))
    atributos: Mapped[dict] = mapped_column(JSON, default=dict)
    creado_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)


class SinonimoMaterial(Base):
    """Palabra de composición que el clasificador aprendió (p. ej. "cordura" es nylon)."""

    __tablename__ = "clasif_sinonimos"
    id: Mapped[int] = mapped_column(primary_key=True)
    palabra: Mapped[str] = mapped_column(String(60), unique=True)
    equivale: Mapped[str] = mapped_column(String(30))
    creado_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)


class Articulo(Base):
    """Dato maestro del artículo (SKU). Un sólido es un estilo-color-talla;
    un prepack es una caja con una curva de sólidos."""

    __tablename__ = "articulos"
    id: Mapped[int] = mapped_column(primary_key=True)
    # Código de artículo de la empresa (numérico o alfanumérico, el formato lo
    # define cada empresa); distinto del SKU del proveedor
    sku: Mapped[str] = mapped_column(String(40), unique=True)  # texto: conserva ceros
    # Genérico: agrupa las tallas y prepacks de un estilo-color, que comparten ficha
    generico: Mapped[str | None] = mapped_column(String(40), index=True)
    sku_proveedor: Mapped[str | None] = mapped_column(String(60), index=True)
    upc: Mapped[str | None] = mapped_column(String(40))
    estilo: Mapped[str] = mapped_column(String(40))
    color: Mapped[str | None] = mapped_column(String(60))
    talla: Mapped[str | None] = mapped_column(String(20))
    descripcion: Mapped[str | None] = mapped_column(String(300))
    marca_id: Mapped[int] = mapped_column(ForeignKey("marcas.id"), index=True)
    grupo_id: Mapped[int] = mapped_column(ForeignKey("grupos_articulos.id"), index=True)
    proveedor_id: Mapped[int | None] = mapped_column(ForeignKey("proveedores.id"))
    unidad: Mapped[str] = mapped_column(String(5))  # PAR | UN | CJ (prepack)
    # Peso neto de una unidad (par, pieza o, en un prepack, la curva completa), en kg.
    # El peso del empaque no va aquí: es la tara de cada nivel de empaque.
    peso_unitario: Mapped[float | None] = mapped_column(Float)
    tipo: Mapped[str] = mapped_column(String(10), default="SOLIDO")  # SOLIDO | PREPACK
    prepack_id: Mapped[int | None] = mapped_column(ForeignKey("prepacks.id"))
    # La ficha técnica y la clasificación son del estilo-color (producto)
    producto_id: Mapped[int | None] = mapped_column(ForeignKey("productos.id"), index=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)

    marca: Mapped[Marca] = relationship()
    grupo: Mapped[GrupoArticulo] = relationship()
    prepack: Mapped[Prepack | None] = relationship()
    producto: Mapped[Producto | None] = relationship(back_populates="articulos")


class PrepackComponente(Base):
    __tablename__ = "prepack_componentes"
    __table_args__ = (UniqueConstraint("prepack_id", "articulo_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    prepack_id: Mapped[int] = mapped_column(ForeignKey("prepacks.id"), index=True)
    articulo_id: Mapped[int] = mapped_column(ForeignKey("articulos.id"))
    cantidad: Mapped[int] = mapped_column(Integer)

    prepack: Mapped[Prepack] = relationship(back_populates="componentes")
    articulo: Mapped[Articulo] = relationship()


class OrdenCompra(Base):
    __tablename__ = "ordenes_compra"
    __table_args__ = (UniqueConstraint("proveedor_id", "numero"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    proveedor_id: Mapped[int] = mapped_column(ForeignKey("proveedores.id"), index=True)
    numero: Mapped[str] = mapped_column(String(40))  # formato de cada empresa
    # Empresa que factura, moneda y precio: opcionales al cargar la OC, se exigen al facturar
    sociedad: Mapped[str | None] = mapped_column(String(10))
    centro: Mapped[str | None] = mapped_column(String(10))
    centro_destino: Mapped[str | None] = mapped_column(String(10))  # centro del país al que va (p. ej. 2220)
    moneda: Mapped[str | None] = mapped_column(String(3))
    incoterm: Mapped[str | None] = mapped_column(String(10))
    fecha: Mapped[date | None] = mapped_column(Date)
    puerto_despacho: Mapped[str | None] = mapped_column(String(10))
    pais_origen: Mapped[str | None] = mapped_column(String(2))
    pais_procedencia: Mapped[str | None] = mapped_column(String(2))
    fecha_xf_original: Mapped[date | None] = mapped_column(Date)
    fecha_xf: Mapped[date | None] = mapped_column(Date)  # XF actualizada
    fecha_tienda: Mapped[date | None] = mapped_column(Date)  # requerida en tienda
    # Comercial: P pendiente, C completa. Logística: 304 sin liberación
    # comercial; 300 liberada por sourcing; 301 liberada con cambios posteriores.
    liberacion_comercial: Mapped[str] = mapped_column(String(1), default="C")
    liberacion_logistica: Mapped[str] = mapped_column(String(3), default="300")
    fecha_lib_comercial: Mapped[date | None] = mapped_column(Date)
    fecha_lib_logistica: Mapped[date | None] = mapped_column(Date)
    liberada: Mapped[bool] = mapped_column(Boolean, default=True)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)

    proveedor: Mapped[Proveedor] = relationship()
    posiciones: Mapped[list["PosicionOC"]] = relationship(
        back_populates="oc", order_by="PosicionOC.id", cascade="all, delete-orphan"
    )


class PosicionOC(Base):
    __tablename__ = "posiciones_oc"
    __table_args__ = (UniqueConstraint("oc_id", "posicion"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    oc_id: Mapped[int] = mapped_column(ForeignKey("ordenes_compra.id"), index=True)
    posicion: Mapped[str] = mapped_column(String(10))  # 10, 20, 30…
    almacen: Mapped[str | None] = mapped_column(String(10))  # cada posición va a su almacén
    articulo_id: Mapped[int | None] = mapped_column(ForeignKey("articulos.id"), index=True)
    codigo_sap: Mapped[str] = mapped_column(String(40))  # SKU; texto: conserva ceros iniciales
    upc: Mapped[str | None] = mapped_column(String(40))
    estilo: Mapped[str | None] = mapped_column(String(40))
    color: Mapped[str | None] = mapped_column(String(60))
    talla: Mapped[str | None] = mapped_column(String(20))
    descripcion: Mapped[str | None] = mapped_column(String(300))
    marca: Mapped[str | None] = mapped_column(String(10))
    grupo: Mapped[str | None] = mapped_column(String(15))
    categoria: Mapped[str | None] = mapped_column(String(10))
    tipo_empaque: Mapped[str] = mapped_column(String(10), default="SOLIDO")  # SOLIDO | PREPACK
    # Empaque de la compra (dato de la posición, no del artículo): casepack =
    # unidades exactas por caja master; inner_pack = unidades por paquete
    # interno (todos iguales). Con ambos, el casepack es múltiplo del inner.
    casepack: Mapped[int | None] = mapped_column(Integer)
    inner_pack: Mapped[int | None] = mapped_column(Integer)
    prepack: Mapped[str | None] = mapped_column(String(30))
    unidades_por_caja: Mapped[int | None] = mapped_column(Integer)  # total de la curva
    cantidad: Mapped[int] = mapped_column(Integer)
    unidad: Mapped[str] = mapped_column(String(5))  # PAR | UN | CJ
    precio: Mapped[float | None] = mapped_column(Float)
    fecha_entrega: Mapped[date | None] = mapped_column(Date)
    pais_origen: Mapped[str | None] = mapped_column(String(3))
    bloqueada: Mapped[bool] = mapped_column(Boolean, default=False)
    motivo_bloqueo: Mapped[str | None] = mapped_column(String(200))

    oc: Mapped[OrdenCompra] = relationship(back_populates="posiciones")
    articulo: Mapped[Articulo | None] = relationship()


# --------------------------------------------------------------------------
# Facturas
# --------------------------------------------------------------------------
class Factura(Base):
    __tablename__ = "facturas"
    __table_args__ = (
        # Número único por proveedor (se ignora en facturas canceladas)
        Index(
            "ux_factura_numero",
            "proveedor_id",
            "numero",
            unique=True,
            sqlite_where=text("numero IS NOT NULL AND estado <> 'CANCELADA'"),
            postgresql_where=text("numero IS NOT NULL AND estado <> 'CANCELADA'"),
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    proveedor_id: Mapped[int] = mapped_column(ForeignKey("proveedores.id"), index=True)
    numero: Mapped[str | None] = mapped_column(String(50))
    fecha: Mapped[date | None] = mapped_column(Date)
    moneda: Mapped[str] = mapped_column(String(3))
    incoterm: Mapped[str | None] = mapped_column(String(10))
    sociedad: Mapped[str] = mapped_column(String(10))
    centro: Mapped[str | None] = mapped_column(String(10))
    centro_destino: Mapped[str | None] = mapped_column(String(10))
    condiciones: Mapped[str | None] = mapped_column(String(200))
    observaciones: Mapped[str | None] = mapped_column(Text)
    estado: Mapped[str] = mapped_column(String(20), default="BORRADOR", index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    creado_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    finalizado_en: Mapped[datetime | None] = mapped_column(DateTime)

    proveedor: Mapped[Proveedor] = relationship()
    lineas: Mapped[list["FacturaLinea"]] = relationship(
        back_populates="factura", cascade="all, delete-orphan", order_by="FacturaLinea.id"
    )
    packing_lists: Mapped[list["PackingList"]] = relationship(
        back_populates="factura", order_by="PackingList.id"
    )


class FacturaLinea(Base):
    __tablename__ = "factura_lineas"
    __table_args__ = (UniqueConstraint("factura_id", "posicion_oc_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    factura_id: Mapped[int] = mapped_column(ForeignKey("facturas.id"), index=True)
    posicion_oc_id: Mapped[int] = mapped_column(ForeignKey("posiciones_oc.id"), index=True)
    cantidad: Mapped[int] = mapped_column(Integer)
    precio_unitario: Mapped[float] = mapped_column(Float)
    precio_oc: Mapped[float] = mapped_column(Float)
    motivo_precio: Mapped[str | None] = mapped_column(String(300))
    # Copia de los datos de la OC al momento de facturar (trazabilidad)
    oc_numero: Mapped[str] = mapped_column(String(30))
    almacen: Mapped[str | None] = mapped_column(String(10))
    posicion: Mapped[str] = mapped_column(String(10))
    codigo_sap: Mapped[str] = mapped_column(String(40))
    upc: Mapped[str | None] = mapped_column(String(40))
    estilo: Mapped[str | None] = mapped_column(String(40))
    color: Mapped[str | None] = mapped_column(String(40))
    talla: Mapped[str | None] = mapped_column(String(20))
    descripcion: Mapped[str | None] = mapped_column(String(300))
    unidad: Mapped[str] = mapped_column(String(5))
    marca: Mapped[str | None] = mapped_column(String(10))
    categoria: Mapped[str | None] = mapped_column(String(10))
    tipo_empaque: Mapped[str] = mapped_column(String(10), default="SOLIDO")
    casepack: Mapped[int | None] = mapped_column(Integer)
    inner_pack: Mapped[int | None] = mapped_column(Integer)
    prepack: Mapped[str | None] = mapped_column(String(30))
    unidades_por_caja: Mapped[int | None] = mapped_column(Integer)
    centro_destino: Mapped[str | None] = mapped_column(String(10))
    # Datos de aduana (editables en la factura)
    pais_origen: Mapped[str | None] = mapped_column(String(3))
    partida_arancelaria: Mapped[str | None] = mapped_column(String(20))
    descripcion_comercial: Mapped[str | None] = mapped_column(String(300))

    factura: Mapped[Factura] = relationship(back_populates="lineas")
    posicion_oc: Mapped[PosicionOC] = relationship()


class Archivo(Base):
    __tablename__ = "archivos"
    id: Mapped[int] = mapped_column(primary_key=True)
    factura_id: Mapped[int] = mapped_column(ForeignKey("facturas.id"), index=True)
    tipo: Mapped[str] = mapped_column(String(30))  # FACTURA_OFICIAL | OTRO
    nombre: Mapped[str] = mapped_column(String(300))
    ruta: Mapped[str] = mapped_column(String(500))
    tamano: Mapped[int] = mapped_column(Integer)
    subido_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    subido_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)


# --------------------------------------------------------------------------
# Packing lists y cajas
# --------------------------------------------------------------------------
class PackingList(Base):
    __tablename__ = "packing_lists"
    id: Mapped[int] = mapped_column(primary_key=True)
    factura_id: Mapped[int] = mapped_column(ForeignKey("facturas.id"), index=True)
    numero: Mapped[str] = mapped_column(String(40))  # PL-001 por defecto; el proveedor puede poner el suyo
    estado: Mapped[str] = mapped_column(String(20), default="BORRADOR", index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    unidad_carga_id: Mapped[int | None] = mapped_column(ForeignKey("unidades_carga.id"), index=True)
    asignacion: Mapped[str | None] = mapped_column(String(12))  # TENTATIVA | CONFIRMADA
    observaciones: Mapped[str | None] = mapped_column(Text)
    recolectado_en: Mapped[date | None] = mapped_column(Date)  # retiro en bodega del proveedor
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)

    factura: Mapped[Factura] = relationship(back_populates="packing_lists")
    lineas: Mapped[list["PLLinea"]] = relationship(
        back_populates="pl", cascade="all, delete-orphan", order_by="PLLinea.id"
    )
    grupos: Mapped[list["GrupoCajas"]] = relationship(
        back_populates="pl", cascade="all, delete-orphan", order_by="GrupoCajas.id"
    )
    unidad: Mapped["UnidadCarga | None"] = relationship(back_populates="packing_lists")


class PLLinea(Base):
    """Parte de una línea de factura dentro de un PL. Puede haber varias
    partes de la misma línea (resultado de dividir)."""

    __tablename__ = "pl_lineas"
    id: Mapped[int] = mapped_column(primary_key=True)
    pl_id: Mapped[int] = mapped_column(ForeignKey("packing_lists.id"), index=True)
    factura_linea_id: Mapped[int] = mapped_column(ForeignKey("factura_lineas.id"), index=True)
    cantidad: Mapped[int] = mapped_column(Integer)

    pl: Mapped[PackingList] = relationship(back_populates="lineas")
    factura_linea: Mapped[FacturaLinea] = relationship()
    items: Mapped[list["GrupoCajasItem"]] = relationship(back_populates="pl_linea")
    recepcion: Mapped["RecepcionLinea | None"] = relationship(
        back_populates="pl_linea", cascade="all, delete-orphan", uselist=False
    )


class GrupoCajas(Base):
    """Nodo del árbol físico de empaque: N unidades iguales de un tipo de
    empaque (caja, inner pack, pallet…). `num_cajas` es el total de esas
    unidades en el PL; si tiene padre, se reparten por igual entre las
    unidades del padre (40 inner en 10 cajas = 4 por caja). Lleva producto
    (items, por unidad) y/o empaques hijos.

    Pesos por unidad, calculados de abajo hacia arriba: neto = artículos
    (peso de cada artículo × cantidad) + neto de los hijos; bruto = neto +
    tara propia + tara de los hijos. Si falta el peso de un artículo, el neto
    se escribe a mano (neto_manual). El volumen es el de las medidas
    exteriores: lo que va dentro de otro empaque no suma volumen."""

    __tablename__ = "grupos_cajas"
    id: Mapped[int] = mapped_column(primary_key=True)
    pl_id: Mapped[int] = mapped_column(ForeignKey("packing_lists.id"), index=True)
    num_cajas: Mapped[int] = mapped_column(Integer)
    largo: Mapped[float | None] = mapped_column(Float)  # cm
    ancho: Mapped[float | None] = mapped_column(Float)
    alto: Mapped[float | None] = mapped_column(Float)
    peso_neto_caja: Mapped[float | None] = mapped_column(Float)  # kg
    peso_bruto_caja: Mapped[float | None] = mapped_column(Float)
    plantilla_id: Mapped[int | None] = mapped_column(ForeignKey("plantillas_caja.id"))
    plantilla_nombre: Mapped[str | None] = mapped_column(String(100))
    es_parcial: Mapped[bool] = mapped_column(Boolean, default=False)
    peso_estimado: Mapped[bool] = mapped_column(Boolean, default=False)
    observacion: Mapped[str | None] = mapped_column(String(300))
    tipo_empaque_id: Mapped[int | None] = mapped_column(ForeignKey("tipos_empaque.id"))
    padre_id: Mapped[int | None] = mapped_column(ForeignKey("grupos_cajas.id", ondelete="SET NULL"), index=True)
    tara: Mapped[float | None] = mapped_column(Float)  # kg de una unidad de este empaque vacía
    neto_manual: Mapped[float | None] = mapped_column(Float)  # neto por unidad si falta el peso de algún artículo

    pl: Mapped[PackingList] = relationship(back_populates="grupos")
    tipo_empaque: Mapped["TipoEmpaque | None"] = relationship()
    padre: Mapped["GrupoCajas | None"] = relationship(remote_side=lambda: GrupoCajas.id, back_populates="hijos")
    hijos: Mapped[list["GrupoCajas"]] = relationship(back_populates="padre", order_by="GrupoCajas.id")
    items: Mapped[list["GrupoCajasItem"]] = relationship(
        back_populates="grupo", cascade="all, delete-orphan", order_by="GrupoCajasItem.id"
    )


class GrupoCajasItem(Base):
    __tablename__ = "grupo_cajas_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    grupo_id: Mapped[int] = mapped_column(ForeignKey("grupos_cajas.id"), index=True)
    pl_linea_id: Mapped[int] = mapped_column(ForeignKey("pl_lineas.id"), index=True)
    cantidad_por_caja: Mapped[int] = mapped_column(Integer)

    grupo: Mapped[GrupoCajas] = relationship(back_populates="items")
    pl_linea: Mapped[PLLinea] = relationship(back_populates="items")


class TipoEmpaque(Base):
    """Unidad logística configurable (inner pack, caja, pallet, bolsa, tambor…).
    Nada está fijo en el código: cada empresa define sus tipos, qué puede
    contener cada uno, su tara, medidas y límites. Un PL se arma como un árbol
    de empaques dentro de empaques con el producto en las hojas."""

    __tablename__ = "tipos_empaque"
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(20), unique=True)
    nombre: Mapped[str] = mapped_column(String(100))
    nivel: Mapped[int] = mapped_column(Integer, default=1)  # 1 = el más interno
    prefijo: Mapped[str | None] = mapped_column(String(6))  # etiqueta de cada unidad: C1, PK1, P1
    # BULTO: cuenta como bulto del documento; INTERIOR: va dentro de un bulto;
    # SOPORTE: lleva bultos (pallet, rack)
    cuenta_como: Mapped[str] = mapped_column(String(10), default="BULTO")
    uom: Mapped[str | None] = mapped_column(String(10))
    largo: Mapped[float | None] = mapped_column(Float)  # cm, exteriores
    ancho: Mapped[float | None] = mapped_column(Float)
    alto: Mapped[float | None] = mapped_column(Float)
    tara: Mapped[float | None] = mapped_column(Float)  # kg del empaque vacío
    peso_max: Mapped[float | None] = mapped_column(Float)  # kg brutos por unidad
    max_unidades: Mapped[int | None] = mapped_column(Integer)  # unidades de producto por unidad
    max_contenido: Mapped[int | None] = mapped_column(Integer)  # empaques internos por unidad
    contiene_productos: Mapped[bool] = mapped_column(Boolean, default=True)
    mezcla_productos: Mapped[bool] = mapped_column(Boolean, default=True)
    mezcla_tallas: Mapped[bool] = mapped_column(Boolean, default=True)
    mezcla_oc: Mapped[bool] = mapped_column(Boolean, default=True)
    identificador: Mapped[str | None] = mapped_column(String(15))  # SERIAL | CODIGO_BARRAS | SSCC
    activo: Mapped[bool] = mapped_column(Boolean, default=True)

    contiene: Mapped[list["TipoEmpaque"]] = relationship(
        secondary=tipo_empaque_contiene, primaryjoin=lambda: TipoEmpaque.id == tipo_empaque_contiene.c.padre_id,
        secondaryjoin=lambda: TipoEmpaque.id == tipo_empaque_contiene.c.hijo_id, order_by="TipoEmpaque.nivel")


class PlantillaCaja(Base):
    __tablename__ = "plantillas_caja"
    __table_args__ = (UniqueConstraint("proveedor_id", "nombre"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    proveedor_id: Mapped[int] = mapped_column(ForeignKey("proveedores.id"), index=True)
    nombre: Mapped[str] = mapped_column(String(100))
    cantidad_por_caja: Mapped[int] = mapped_column(Integer)
    unidad: Mapped[str] = mapped_column(String(5))
    largo: Mapped[float | None] = mapped_column(Float)
    ancho: Mapped[float | None] = mapped_column(Float)
    alto: Mapped[float | None] = mapped_column(Float)
    # Solo la tara del empaque: el peso neto sale del peso de cada artículo
    tara: Mapped[float | None] = mapped_column(Float)
    tipo_empaque_id: Mapped[int | None] = mapped_column(ForeignKey("tipos_empaque.id"))
    activa: Mapped[bool] = mapped_column(Boolean, default=True)

    tipo_empaque: Mapped["TipoEmpaque | None"] = relationship()


class RecepcionLinea(Base):
    __tablename__ = "recepciones"
    id: Mapped[int] = mapped_column(primary_key=True)
    pl_linea_id: Mapped[int] = mapped_column(ForeignKey("pl_lineas.id"), unique=True)
    cantidad_recibida: Mapped[int] = mapped_column(Integer)
    cantidad_danada: Mapped[int] = mapped_column(Integer, default=0)
    observacion: Mapped[str | None] = mapped_column(String(300))
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    fecha: Mapped[datetime] = mapped_column(DateTime, default=ahora)

    pl_linea: Mapped[PLLinea] = relationship(back_populates="recepcion")


# --------------------------------------------------------------------------
# Transporte
# --------------------------------------------------------------------------
class Embarque(Base):
    """Existe desde la planificación (booking), antes de tener BL/AWB."""

    __tablename__ = "embarques"
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(20), unique=True)
    tipo_transporte: Mapped[str] = mapped_column(String(12))  # MARITIMO | AEREO | TERRESTRE
    documento_numero: Mapped[str | None] = mapped_column(String(50))  # BL / AWB / CP
    transportista_id: Mapped[int | None] = mapped_column(ForeignKey("transportistas.id"))
    transportista: Mapped[str | None] = mapped_column(String(150))  # nombre al momento de asignarlo
    puerto_origen: Mapped[str | None] = mapped_column(String(10))  # códigos del catálogo de puertos
    puerto_destino: Mapped[str | None] = mapped_column(String(10))
    centro: Mapped[str | None] = mapped_column(String(10))  # centro al que llega; su puerto debe coincidir
    etd: Mapped[date | None] = mapped_column(Date)
    eta: Mapped[date | None] = mapped_column(Date)
    salida_real: Mapped[date | None] = mapped_column(Date)
    arribo_real: Mapped[date | None] = mapped_column(Date)
    estado: Mapped[str] = mapped_column(String(20), default="PLANIFICADO")
    observaciones: Mapped[str | None] = mapped_column(Text)
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)

    unidades: Mapped[list["UnidadCarga"]] = relationship(
        back_populates="embarque", order_by="UnidadCarga.id", cascade="all, delete-orphan"
    )
    eventos: Mapped[list["EventoEmbarque"]] = relationship(
        back_populates="embarque", order_by="EventoEmbarque.fecha", cascade="all, delete-orphan"
    )


class UnidadCarga(Base):
    __tablename__ = "unidades_carga"
    id: Mapped[int] = mapped_column(primary_key=True)
    embarque_id: Mapped[int] = mapped_column(ForeignKey("embarques.id"), index=True)
    tipo: Mapped[str] = mapped_column(String(10))
    etiqueta: Mapped[str] = mapped_column(String(30))  # "40HC #1" mientras no hay número
    numero: Mapped[str | None] = mapped_column(String(20))
    sello: Mapped[str | None] = mapped_column(String(30))
    capacidad_cbm: Mapped[float | None] = mapped_column(Float)
    capacidad_kg: Mapped[float | None] = mapped_column(Float)

    embarque: Mapped[Embarque] = relationship(back_populates="unidades")
    packing_lists: Mapped[list[PackingList]] = relationship(back_populates="unidad")


class EventoEmbarque(Base):
    __tablename__ = "eventos_embarque"
    id: Mapped[int] = mapped_column(primary_key=True)
    embarque_id: Mapped[int] = mapped_column(ForeignKey("embarques.id"), index=True)
    tipo: Mapped[str] = mapped_column(String(20))
    fecha: Mapped[datetime] = mapped_column(DateTime)
    ubicacion: Mapped[str | None] = mapped_column(String(150))
    observacion: Mapped[str | None] = mapped_column(String(500))
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)

    embarque: Mapped[Embarque] = relationship(back_populates="eventos")


# --------------------------------------------------------------------------
# Soporte: historial, alertas, idempotencia, importaciones
# --------------------------------------------------------------------------
class Historial(Base):
    __tablename__ = "historial"
    id: Mapped[int] = mapped_column(primary_key=True)
    entidad: Mapped[str] = mapped_column(String(30))
    entidad_id: Mapped[int] = mapped_column(Integer)
    factura_id: Mapped[int | None] = mapped_column(Integer, index=True)
    accion: Mapped[str] = mapped_column(String(60))
    detalle: Mapped[dict | list | None] = mapped_column(JSON)
    motivo: Mapped[str | None] = mapped_column(String(500))
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    fecha: Mapped[datetime] = mapped_column(DateTime, default=ahora, index=True)

    usuario: Mapped[Usuario | None] = relationship()


class Alerta(Base):
    __tablename__ = "alertas"
    id: Mapped[int] = mapped_column(primary_key=True)
    proveedor_id: Mapped[int | None] = mapped_column(ForeignKey("proveedores.id"))
    tipo: Mapped[str] = mapped_column(String(40))
    mensaje: Mapped[str] = mapped_column(String(500))
    referencia: Mapped[dict | None] = mapped_column(JSON)
    resuelta: Mapped[bool] = mapped_column(Boolean, default=False)
    creada_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)


class Meta(Base):
    """Valores del sistema, como la versión del esquema."""

    __tablename__ = "meta"
    clave: Mapped[str] = mapped_column(String(40), primary_key=True)
    valor: Mapped[str] = mapped_column(String(200))


class Idempotencia(Base):
    __tablename__ = "idempotencia"
    clave: Mapped[str] = mapped_column(String(160), primary_key=True)
    usuario_id: Mapped[int] = mapped_column(Integer)
    respuesta: Mapped[dict | list | None] = mapped_column(JSON)
    creada_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)


class ImportacionOC(Base):
    __tablename__ = "importaciones_oc"
    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    nombre_archivo: Mapped[str] = mapped_column(String(300))
    estado: Mapped[str] = mapped_column(String(12), default="PREVIA")  # PREVIA | APLICADA
    filas: Mapped[list] = mapped_column(JSON)
    resultado: Mapped[dict | None] = mapped_column(JSON)
    creada_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)
