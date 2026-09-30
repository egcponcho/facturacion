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


class Usuario(Base):
    __tablename__ = "usuarios"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(200), unique=True)
    nombre: Mapped[str] = mapped_column(String(200))
    rol: Mapped[str] = mapped_column(String(20))  # admin | interno | proveedor
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
    proveedor: Mapped[Proveedor | None] = relationship()


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
    """Estándares de tiempo por región de origen: con cuántos días de
    anticipación a la XF se libera logísticamente la OC y cuánto toma cada
    etapa después de la llegada al puerto (bodega, ingreso y reexportación
    a tienda) para saber si un embarque llega temprano o tarde."""

    __tablename__ = "regiones_leadtime"
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(10), unique=True)
    nombre: Mapped[str] = mapped_column(String(100))
    dias_liberacion: Mapped[int] = mapped_column(Integer, default=15)  # liberación logística antes de la XF
    dias_transito: Mapped[int] = mapped_column(Integer, default=10)  # XF a arribo al puerto destino (estimado)
    dias_puerto_bodega: Mapped[int] = mapped_column(Integer, default=3)
    dias_ingreso: Mapped[int] = mapped_column(Integer, default=2)
    dias_reexportacion: Mapped[int] = mapped_column(Integer, default=5)  # aún no se registra en el sistema
    predeterminada: Mapped[bool] = mapped_column(Boolean, default=False)  # para orígenes sin región
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


class GrupoArticulo(Base):
    """Grupo de artículos. La categoría decide la regla de empaque:
    calzado (casepack exacto, sin mezclar tallas) o ropa y accesorios."""

    __tablename__ = "grupos_articulos"
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(15), unique=True)
    nombre: Mapped[str] = mapped_column(String(100))
    categoria: Mapped[str] = mapped_column(String(10))  # CALZADO | ROPA | ACCESORIO
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
    codigo_generico: Mapped[str | None] = mapped_column(String(20), unique=True, index=True)
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
    # borrador | sugerida | aprobado | corregido | observado
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
    digitos: Mapped[int] = mapped_column(Integer, default=10)
    mcca: Mapped[bool] = mapped_column(Boolean, default=False)
    impuesto: Mapped[str | None] = mapped_column(String(60))  # p. ej. "VAT 13%"
    nota: Mapped[str | None] = mapped_column(String(300))
    orden: Mapped[int] = mapped_column(Integer, default=0)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


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
    # Código de artículo interno (11 dígitos, empieza con 3); distinto del SKU del proveedor
    sku: Mapped[str] = mapped_column(String(40), unique=True)  # texto: conserva ceros
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
    numero: Mapped[str] = mapped_column(String(30))  # 44xxxxxxxx
    sociedad: Mapped[str] = mapped_column(String(10))
    centro: Mapped[str | None] = mapped_column(String(10))
    centro_destino: Mapped[str | None] = mapped_column(String(10))  # centro del país al que va (p. ej. 2220)
    moneda: Mapped[str] = mapped_column(String(3))
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
    precio: Mapped[float] = mapped_column(Float)
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
    numero: Mapped[str] = mapped_column(String(20))
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
    pallets: Mapped[list["Pallet"]] = relationship(cascade="all, delete-orphan", order_by="Pallet.numero")


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
    """N cajas iguales. Guarda sus propios valores: la plantilla solo sirvió
    para llenarlos rápido. Si tiene varios items es una caja mixta/surtida;
    el peso y volumen pertenecen al grupo y se cuentan una sola vez."""

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
    pallet_id: Mapped[int | None] = mapped_column(ForeignKey("pallets.id"), index=True)

    pl: Mapped[PackingList] = relationship(back_populates="grupos")
    pallet: Mapped["Pallet | None"] = relationship(back_populates="grupos")
    items: Mapped[list["GrupoCajasItem"]] = relationship(
        back_populates="grupo", cascade="all, delete-orphan", order_by="GrupoCajasItem.id"
    )


class Pallet(Base):
    """Tarima con cajas del PL. Sus medidas son las del pallet armado."""

    __tablename__ = "pallets"
    id: Mapped[int] = mapped_column(primary_key=True)
    pl_id: Mapped[int] = mapped_column(ForeignKey("packing_lists.id"), index=True)
    numero: Mapped[int] = mapped_column(Integer)
    largo: Mapped[float] = mapped_column(Float)  # cm
    ancho: Mapped[float] = mapped_column(Float)
    alto: Mapped[float] = mapped_column(Float)
    peso_tara: Mapped[float] = mapped_column(Float, default=0)  # kg de la tarima vacía

    grupos: Mapped[list[GrupoCajas]] = relationship(back_populates="pallet")


class GrupoCajasItem(Base):
    __tablename__ = "grupo_cajas_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    grupo_id: Mapped[int] = mapped_column(ForeignKey("grupos_cajas.id"), index=True)
    pl_linea_id: Mapped[int] = mapped_column(ForeignKey("pl_lineas.id"), index=True)
    cantidad_por_caja: Mapped[int] = mapped_column(Integer)

    grupo: Mapped[GrupoCajas] = relationship(back_populates="items")
    pl_linea: Mapped[PLLinea] = relationship(back_populates="items")


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
    peso_neto: Mapped[float | None] = mapped_column(Float)
    peso_bruto: Mapped[float | None] = mapped_column(Float)
    tara: Mapped[float | None] = mapped_column(Float)
    activa: Mapped[bool] = mapped_column(Boolean, default=True)


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
