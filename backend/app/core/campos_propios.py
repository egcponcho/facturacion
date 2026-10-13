"""Campos propios: datos que la empresa agrega a sus registros sin tocar el
código (Configuración → Empresa → Campos propios).

Cada entidad (artículos, proveedores, OCs, facturas…) puede tener campos de
tipo texto, número, fecha, sí/no u opción. Las definiciones se guardan en la
tabla definiciones_campo (la configuración de la petición las trae ya
cargadas) y los valores en la columna `extra` (JSON) del registro, con la
clave de cada campo.
"""
import re
from datetime import date

from app.core.errores import ErrorNegocio

# Entidad → etiqueta (las de datos maestros son los catálogos del mismo nombre)
ENTIDADES = {
    "articulos": "Items", "proveedores": "Suppliers", "sociedades": "Companies", "centros": "Plants",
    "marcas": "Brands", "transportistas": "Carriers", "ordenes": "Purchase orders", "facturas": "Invoices",
}
TIPOS = {"texto": "Text", "numero": "Number", "fecha": "Date", "bool": "Yes / no", "opcion": "Option"}
MAX_CAMPOS = 20


def definiciones(entidad: str) -> list[dict]:
    """Campos propios de una entidad en la petición en curso."""
    from app.core.empresa import configuracion_actual

    return list(((configuracion_actual().get("campos_propios") or {}).get(entidad)) or [])


def validar_definiciones(datos) -> dict:
    """{entidad: [{clave, etiqueta, tipo, opciones?, obligatorio?}]} limpio."""
    if not isinstance(datos, dict) or set(datos) - set(ENTIDADES):
        raise ErrorNegocio("Own fields go by entity.", 422, "validacion")
    limpio = {}
    for entidad, campos in datos.items():
        if not isinstance(campos, list) or len(campos) > MAX_CAMPOS:
            raise ErrorNegocio(f"At most {MAX_CAMPOS} own fields per entity.", 422, "validacion")
        vistas, lista = set(), []
        for c in campos:
            etiqueta = str((c or {}).get("etiqueta") or "").strip()[:60]
            clave = str(c.get("clave") or "").strip().lower() or re.sub(r"[^a-z0-9]+", "_", etiqueta.lower()).strip("_")
            tipo = c.get("tipo") or "texto"
            if not etiqueta or not re.fullmatch(r"[a-z][a-z0-9_]{0,29}", clave):
                raise ErrorNegocio("Every own field needs a name (and a key of letters, numbers and _).", 422, "validacion")
            if clave in vistas:
                raise ErrorNegocio(f"The own field {clave} is repeated.", 422, "validacion")
            if tipo not in TIPOS:
                raise ErrorNegocio(f"The type must be one of {', '.join(TIPOS)}.", 422, "validacion")
            opciones = [str(o).strip()[:60] for o in (c.get("opciones") or []) if str(o).strip()]
            if tipo == "opcion" and not opciones:
                raise ErrorNegocio(f"{etiqueta}: an option field needs its options.", 422, "validacion")
            vistas.add(clave)
            lista.append({"clave": clave, "etiqueta": etiqueta, "tipo": tipo, "obligatorio": bool(c.get("obligatorio")),
                          "indexado": bool(c.get("indexado")), **({"opciones": opciones} if tipo == "opcion" else {})})
        limpio[entidad] = lista
    return limpio


def convertir(campo: dict, valor):
    """El valor escrito, con el tipo del campo (ValueError si no lo cumple)."""
    if valor in (None, ""):
        return None
    tipo = campo["tipo"]
    if tipo == "numero":
        return float(str(valor).replace(",", ""))
    if tipo == "bool":
        return valor if isinstance(valor, bool) else str(valor).strip().lower() in ("1", "true", "si", "sí", "yes", "y", "x")
    if tipo == "fecha":
        return valor.isoformat() if isinstance(valor, date) else date.fromisoformat(str(valor)[:10]).isoformat()
    if tipo == "opcion":
        texto = str(valor).strip()
        elegida = next((o for o in campo["opciones"] if o.lower() == texto.lower()), None)
        if elegida is None:
            raise ValueError
        return elegida
    return str(valor).strip()[:500]


def limpiar(entidad: str, valores: dict | None, actuales: dict | None = None, parcial: bool = True) -> dict:
    """Valores de los campos propios (los que llegan sobre los actuales), validados."""
    campos = {c["clave"]: c for c in definiciones(entidad)}
    resultado = {k: v for k, v in (actuales or {}).items() if k in campos}
    errores = []
    for clave, valor in (valores or {}).items():
        if clave not in campos:
            continue
        try:
            resultado[clave] = convertir(campos[clave], valor)
        except (TypeError, ValueError):
            errores.append({"campo": f"extra.{clave}", "mensaje": f"{campos[clave]['etiqueta']}: invalid value."})
    if not parcial:
        errores += [{"campo": f"extra.{k}", "mensaje": f"{c['etiqueta']} is required."}
                    for k, c in campos.items() if c["obligatorio"] and resultado.get(k) in (None, "")]
    if errores:
        raise ErrorNegocio("Check the data.", 422, "validacion", errores)
    return {k: v for k, v in resultado.items() if v is not None}


# ---- Guardadas en la tabla definiciones_campo ----------------------------------------------
TABLAS = {"articulos": "articulos", "proveedores": "proveedores", "sociedades": "sociedades", "centros": "centros",
          "marcas": "marcas", "transportistas": "transportistas", "ordenes": "ordenes_compra", "facturas": "facturas"}


def cargar(db) -> dict:
    """{entidad: [definiciones en su orden]} de la organización de la sesión."""
    from sqlalchemy import select

    from app.modelos import DefinicionCampo

    res: dict[str, list] = {}
    for d in db.scalars(select(DefinicionCampo).order_by(DefinicionCampo.entidad, DefinicionCampo.orden, DefinicionCampo.id)):
        res.setdefault(d.entidad, []).append(
            {"clave": d.clave, "etiqueta": d.etiqueta, "tipo": d.tipo, "obligatorio": d.obligatorio, "indexado": d.indexado,
             **({"opciones": list(d.opciones or [])} if d.tipo == "opcion" else {})})
    return res


def _indice(db, entidad: str, clave: str, crear: bool) -> None:
    """PostgreSQL: índice sobre el valor de un campo propio (extra->>'clave')."""
    con = db.connection()
    if con.dialect.name != "postgresql" or not re.fullmatch(r"[a-z][a-z0-9_]{0,29}", clave):
        return
    tabla = TABLAS[entidad]
    nombre = f"ix_{tabla}_extra_{clave}"[:63]
    if crear:
        con.exec_driver_sql(f"CREATE INDEX IF NOT EXISTS {nombre} ON {tabla} ((extra->>'{clave}'))")
    else:
        con.exec_driver_sql(f"DROP INDEX IF EXISTS {nombre}")


def guardar(db, definiciones: dict) -> None:
    """Reemplaza todas las definiciones (ya validadas; una entidad ausente
    queda sin campos): conserva las que siguen, agrega las nuevas y quita las
    que ya no están (sus valores en `extra` se conservan, solo dejan de
    mostrarse)."""
    from sqlalchemy import select

    from app.modelos import DefinicionCampo

    for entidad in ENTIDADES:
        campos = definiciones.get(entidad, [])
        actuales = {d.clave: d for d in db.scalars(select(DefinicionCampo).where(DefinicionCampo.entidad == entidad))}
        for i, c in enumerate(campos, start=1):
            d = actuales.pop(c["clave"], None) or DefinicionCampo(entidad=entidad, clave=c["clave"])
            antes = bool(d.indexado)
            d.etiqueta, d.tipo, d.obligatorio, d.orden = c["etiqueta"], c["tipo"], c["obligatorio"], i
            d.opciones, d.indexado = c.get("opciones") or [], bool(c.get("indexado"))
            db.add(d)
            if d.indexado != antes:
                _indice(db, entidad, c["clave"], d.indexado)
        for d in actuales.values():
            if d.indexado:
                _indice(db, entidad, d.clave, False)
            db.delete(d)
    db.flush()
