"""Cambios de datos: saber qué cambió para no volver a consultar lo que no.

Tres piezas:

1. **Versión por tabla** (`versiones_datos`). Cada INSERT, UPDATE o DELETE que
   se confirma sube, en la misma transacción, la versión de su tabla en su
   organización (0 si no tiene). Se detecta en el SQL que llega al motor, así
   que cubre el ORM, las actualizaciones masivas y el SQL directo. Una
   transacción que se revierte no sube nada.

2. **Respuestas condicionales** (`middleware`). Cada GET de la API anota qué
   tablas leyó. Con eso su respuesta lleva una ETag formada por la URL, el
   usuario, la organización, la fecha del día y las versiones de esas tablas.
   Si el navegador vuelve a pedir lo mismo con `If-None-Match` y nada de eso
   cambió, se responde 304 **sin ejecutar la consulta**: solo se valida la
   sesión (que se renueva igual) y se leen las versiones. Las versiones se
   leen antes de consultar los datos: si algo cambia mientras tanto, la ETag
   queda vieja y la siguiente visita trae los datos nuevos (nunca al revés).

3. **Canal de cambios** (`Difusor`, `/api/cambios`). Un solo lector por
   proceso revisa las versiones cada pocos segundos y avisa a los navegadores
   conectados (Server-Sent Events) qué tablas cambiaron en su organización. La
   pantalla abierta vuelve a pedir sus datos solo cuando cambió algo suyo.

Funciona igual con varios procesos o servidores (todo está en la base) y en
SQLite. Las tablas técnicas que cambian solas (sesiones, idempotencia, la
edición exclusiva) no cuentan.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from collections import OrderedDict
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from pathlib import Path

from sqlalchemy import event, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import Base, SessionLocal, engine

log = logging.getLogger("app.cambios")

# Tablas técnicas: cambian sin que cambien los datos que se muestran
EXCLUIDAS = frozenset({"versiones_datos", "alembic_version", "sesiones", "desafios_dos_pasos", "idempotencia", "ediciones"})
# Columnas de rastreo: un UPDATE que solo toca estas no cambia lo que se muestra
# (el último ingreso se escribe en cada inicio de sesión y lo leen todas las
# respuestas al autenticar: contarlo invalidaría todo con cada ingreso)
SOLO_RASTREO = {"usuarios": frozenset({"ultimo_acceso"})}
_set = re.compile(r"\bSET\s+(.*?)\s+WHERE\b", re.I | re.S)
# Rutas sin respuesta condicional: la sesión misma, la edición exclusiva (vence
# con el reloj, sin escribir) y el propio canal de cambios
SIN_ETAG = ("/api/auth/", "/api/edicion/", "/api/cambios", "/api/salud")
MAX_RUTAS = 20000

_activo = False  # hasta que exista la tabla (después de las migraciones)
_estado: ContextVar[dict | None] = ContextVar("cambios_estado", default=None)
_rutas: OrderedDict[str, frozenset] = OrderedDict()  # URL → tablas que lee (aprendidas)
_patron: re.Pattern | None = None
_escritura = re.compile(r'^\s*(?:INSERT\s+(?:OR\s+\w+\s+)?INTO|UPDATE|DELETE\s+FROM)\s+"?(\w+)"?', re.I)


def _codigo() -> str:
    """Huella del código desplegado: otra versión de la aplicación puede
    responder distinto con los mismos datos."""
    raiz = Path(__file__).resolve().parents[1]
    h = hashlib.sha256()
    for f in sorted(raiz.rglob("*.py")):
        st = f.stat()
        h.update(f"{f.relative_to(raiz)}:{st.st_size}:{int(st.st_mtime)}".encode())
    return h.hexdigest()[:16]


CODIGO = _codigo()


def activar() -> None:
    """Empieza a contar los cambios (la tabla ya existe)."""
    global _activo
    _activo = True


@lru_cache(maxsize=4096)  # el SQL del ORM se repite casi siempre igual
def _tablas_en(sql: str) -> frozenset[str]:
    global _patron
    if _patron is None:
        nombres = sorted(Base.metadata.tables, key=len, reverse=True)
        _patron = re.compile(r'(?<![\w.])"?(' + "|".join(map(re.escape, nombres)) + r')"?(?!\w)')
    return frozenset(_patron.findall(sql)) - EXCLUIDAS


# ---- 1. Versión por tabla -----------------------------------------------------------------------
@event.listens_for(engine, "before_cursor_execute")
def _anotar(conn, _cursor, sql, _params, _contexto, _varios):
    if sql.lstrip()[:6].upper().startswith(("SELECT", "WITH")):
        estado = _estado.get()
        if estado is not None:
            estado["leidas"] |= _tablas_en(sql)
        return
    m = _escritura.match(sql)
    if m and _activo and m.group(1) not in EXCLUIDAS and not _solo_rastreo(m.group(1), sql):
        conn.info.setdefault("cambios_escritas", set()).add((m.group(1), int(conn.info.get("cambios_org") or 0)))


def _solo_rastreo(tabla: str, sql: str) -> bool:
    ignorables = SOLO_RASTREO.get(tabla)
    if not ignorables or not sql.lstrip()[:6].upper().startswith("UPDATE"):
        return False
    m = _set.search(sql)
    columnas = {c.strip().strip('"').split(".")[-1] for c in re.findall(r'([\w."]+)\s*=', m.group(1))} if m else set()
    return bool(columnas) and columnas <= ignorables


@event.listens_for(engine, "commit")
def _al_confirmar(conn):
    escritas = conn.info.pop("cambios_escritas", None)
    conn.info.pop("cambios_org", None)
    if not escritas or not _activo:
        return
    marca = "?" if conn.dialect.paramstyle == "qmark" else "%s"
    sql = (f"INSERT INTO versiones_datos (tabla, ambito, version) VALUES ({marca}, {marca}, 1) "
           "ON CONFLICT (tabla, ambito) DO UPDATE SET version = versiones_datos.version + 1")
    cur = conn.connection.cursor()  # directo al driver: dentro de la misma transacción, sin volver a los eventos
    try:
        for tabla, ambito in sorted(escritas):  # siempre en el mismo orden: sin bloqueos cruzados
            cur.execute(sql, (tabla, ambito))
    finally:
        cur.close()


@event.listens_for(engine, "rollback")
def _al_revertir(conn):
    conn.info.pop("cambios_escritas", None)
    conn.info.pop("cambios_org", None)


@event.listens_for(Session, "after_begin")
def _organizacion_de_la_conexion(db: Session, _transaccion, conexion) -> None:
    from app.core.organizacion import de_sesion

    conexion.info["cambios_org"] = de_sesion(db)


def fijar_organizacion(conexion, organizacion_id: int | None) -> None:
    """La sesión cambió de organización con la transacción abierta."""
    conexion.info["cambios_org"] = organizacion_id


def versiones(db: Session, tablas=None) -> dict[str, int]:
    """Versión de cada tabla (todas sus organizaciones: lo que cambia en una
    tabla compartida desde otra organización también cuenta)."""
    if tablas is None:  # todas (una tabla chica: una fila por tabla y organización)
        return {t: int(v or 0) for t, v in db.execute(text("SELECT tabla, SUM(version) FROM versiones_datos GROUP BY tabla"))}
    tablas = sorted(set(tablas))
    if not tablas:
        return {}
    filas = db.execute(text("SELECT tabla, SUM(version) FROM versiones_datos WHERE tabla IN :t GROUP BY tabla")
                       .bindparams(_expandir("t")), {"t": tablas}).all()
    res = dict.fromkeys(tablas, 0)
    res.update({t: int(v or 0) for t, v in filas})
    return res


def _expandir(nombre: str):
    from sqlalchemy import bindparam

    return bindparam(nombre, expanding=True)


# ---- 2. Respuestas condicionales ----------------------------------------------------------------
def _etag(clave: str, identidad: tuple, vers: dict[str, int]) -> str:
    h = hashlib.sha256("|".join([clave, *map(str, identidad), date.today().isoformat(), CODIGO,
                                 *(f"{t}={v}" for t, v in sorted(vers.items()))]).encode())
    return f'W/"{h.hexdigest()[:32]}"'


def _token(request) -> str | None:
    auth = request.headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.cookies.get("sesion")


def _preparar(token: str | None, tablas: frozenset | None) -> tuple[tuple, dict] | None:
    """Sesión válida (se renueva como en cualquier petición) y versiones de
    las tablas, leídas ANTES de consultar los datos."""
    from app.core.organizacion import de_sesion
    from app.modulos.acceso.autenticacion import usuario_de_sesion

    if not token:
        return None
    with SessionLocal() as db:
        u = usuario_de_sesion(db, token)
        if not u:
            return None
        identidad = (u.id, de_sesion(db) or 0)
        vers = versiones(db, tablas)
        db.commit()
    return identidad, vers


def _recordar(clave: str, tablas: frozenset) -> None:
    _rutas[clave] = tablas
    _rutas.move_to_end(clave)
    while len(_rutas) > MAX_RUTAS:
        _rutas.popitem(last=False)


async def middleware(request, call_next):
    from starlette.concurrency import run_in_threadpool
    from starlette.responses import Response

    ruta = request.url.path
    if request.method != "GET" or not ruta.startswith("/api/") or ruta.startswith(SIN_ETAG) or not _activo:
        return await call_next(request)
    clave = f"{ruta}?{request.url.query}"
    conocidas = _rutas.get(clave)
    # Sesión y versiones ANTES de consultar: de las tablas que esta URL lee, o
    # de todas si es la primera vez (así la ETag sale desde la primera visita)
    previo = await run_in_threadpool(_preparar, _token(request), conocidas)
    pedida = [x.strip() for x in (request.headers.get("if-none-match") or "").split(",") if x.strip()]
    if previo is not None and conocidas is not None:
        etag = _etag(clave, previo[0], previo[1])
        if etag in pedida:
            return Response(status_code=304, headers={"ETag": etag, "X-Tablas": ",".join(sorted(conocidas))})
    estado = {"leidas": set()}
    marca = _estado.set(estado)
    try:
        resp = await call_next(request)
    finally:
        _estado.reset(marca)
    if resp.status_code != 200 or not (resp.headers.get("content-type") or "").startswith("application/json"):
        return resp
    leidas = frozenset(estado["leidas"])
    if conocidas is not None and not leidas <= conocidas:
        # Leyó tablas que no se esperaban (otro camino del código): se aprende
        # y la ETag va desde la próxima vez (sus versiones no se leyeron antes)
        _recordar(clave, leidas | conocidas)
        return resp
    tablas = conocidas if conocidas is not None else leidas
    if conocidas is None:
        _recordar(clave, tablas)
    if previo is not None:
        etag = _etag(clave, previo[0], {t: previo[1].get(t, 0) for t in tablas})
        if etag in pedida:  # el navegador ya lo tenía: se ahorra el envío
            return Response(status_code=304, headers={"ETag": etag, "X-Tablas": ",".join(sorted(tablas))})
        resp.headers["ETag"] = etag
        resp.headers["X-Tablas"] = ",".join(sorted(tablas))
    return resp


# ---- 3. Canal de cambios ------------------------------------------------------------------------
@dataclass(eq=False)
class _Cliente:
    organizacion: int
    cola: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(maxsize=100))


class Difusor:
    """Un solo lector de versiones por proceso para todos los navegadores."""

    def __init__(self) -> None:
        self.clientes: set[_Cliente] = set()
        self._ultimas: dict[tuple[str, int], int] | None = None

    async def conectar(self, organizacion: int) -> _Cliente:
        """Registra al navegador. Si nadie escuchaba, primero toma la base de
        versiones: un cambio hecho justo después de conectarse no se pierde."""
        if self._ultimas is None:
            self._ultimas = await asyncio.to_thread(self._leer)
        c = _Cliente(int(organizacion or 0))
        self.clientes.add(c)
        return c

    def desconectar(self, c: _Cliente) -> None:
        self.clientes.discard(c)

    @staticmethod
    def _leer() -> dict[tuple[str, int], int]:
        with SessionLocal() as db:
            return {(t, int(a)): int(v) for t, a, v in db.execute(text("SELECT tabla, ambito, version FROM versiones_datos"))}

    def revisar(self, actuales: dict[tuple[str, int], int]) -> None:
        """Avisa a cada cliente las tablas que cambiaron en su organización o
        en lo compartido desde la última revisión."""
        if self._ultimas is None:
            self._ultimas = actuales
            return
        cambiadas = {k for k, v in actuales.items() if self._ultimas.get(k) != v}
        self._ultimas = actuales
        if not cambiadas:
            return
        for c in list(self.clientes):
            tablas = sorted({t for t, a in cambiadas if a in (0, c.organizacion)} - EXCLUIDAS)
            if tablas:
                try:
                    c.cola.put_nowait(tablas)
                except asyncio.QueueFull:  # un navegador que no lee: que vuelva a pedir todo al reconectar
                    self.desconectar(c)

    async def correr(self) -> None:
        while True:
            try:
                if self.clientes:
                    self.revisar(await asyncio.to_thread(self._leer))
                else:
                    # Nadie escucha: no se consulta. Quien se conecte vuelve a pedir
                    # sus datos al abrir el canal, así que no hace falta lo anterior.
                    self._ultimas = None
            except Exception:  # noqa: BLE001 - el canal no debe tumbar el servidor
                log.exception("No se pudieron revisar los cambios")
            await asyncio.sleep(settings.CAMBIOS_INTERVALO_SEG)


difusor = Difusor()
