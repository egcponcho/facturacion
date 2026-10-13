"""Facturación recurrente: un documento modelo que se copia cada cierto
tiempo (suscripciones, alquileres, servicios fijos)."""
import calendar
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import dinero
from app.core.errores import ErrorNegocio
from app.modelos import Documento, DocumentoLinea, FacturacionRecurrente, Usuario
from app.modulos.acceso.permisos import exigir
from app.modulos.comercial import documentos as docs
from app.modulos.comun.historial import registrar

FRECUENCIAS = ("SEMANAL", "MENSUAL", "TRIMESTRAL", "ANUAL")


def _sumar_meses(d: date, meses: int, dia: int) -> date:
    m = d.month - 1 + meses
    anio, mes = d.year + m // 12, m % 12 + 1
    return date(anio, mes, min(dia, calendar.monthrange(anio, mes)[1]))


def siguiente_fecha(d: date, frecuencia: str, dia: int | None = None) -> date:
    """La fecha siguiente; las mensuales conservan el día de referencia (31 → 28 → 31…)."""
    if frecuencia == "SEMANAL":
        return d + timedelta(days=7)
    return _sumar_meses(d, {"MENSUAL": 1, "TRIMESTRAL": 3, "ANUAL": 12}[frecuencia], dia or d.day)


def _dict(r: FacturacionRecurrente) -> dict:
    return {"id": r.id, "nombre": r.nombre, "modelo_id": r.modelo_id, "frecuencia": r.frecuencia, "proxima": r.proxima,
            "hasta": r.hasta, "emitir": r.emitir, "activo": r.activo}


def listar(db: Session, user: Usuario) -> list[dict]:
    exigir(user, "comercial.ver")
    return [_dict(r) for r in db.scalars(select(FacturacionRecurrente).order_by(FacturacionRecurrente.proxima))]


def crear(db: Session, user: Usuario, datos) -> dict:
    exigir(user, "comercial.editar")
    if datos.frecuencia not in FRECUENCIAS:
        raise ErrorNegocio("Choose the frequency.", 422, "validacion")
    modelo = docs.cargar(db, user, datos.modelo_id)
    if modelo.tipo.direccion != "EMITIDO" or modelo.estado == "ANULADO":
        raise ErrorNegocio("The model must be an issued-type document that is not voided.", 422, "validacion")
    if datos.hasta and datos.hasta < datos.proxima:
        raise ErrorNegocio("The end date is before the next date.", 422, "validacion")
    r = FacturacionRecurrente(nombre=datos.nombre.strip(), modelo_id=modelo.id, frecuencia=datos.frecuencia,
                              proxima=datos.proxima, dia=datos.proxima.day, hasta=datos.hasta, emitir=datos.emitir, activo=True)
    db.add(r)
    db.flush()
    registrar(db, user, "recurrente", r.id, "crear", _dict(r))
    return _dict(r)


def generar(db: Session, user: Usuario, hasta: date | None = None) -> list[dict]:
    """Genera los documentos que tocan hasta la fecha (hoy por defecto)."""
    exigir(user, "comercial.editar")
    hasta = hasta or date.today()
    creados = []
    for r in db.scalars(select(FacturacionRecurrente).where(FacturacionRecurrente.activo.is_(True),
                                                            FacturacionRecurrente.proxima <= hasta).with_for_update()):
        while r.activo and r.proxima <= hasta:
            m = db.get(Documento, r.modelo_id)
            nuevo = Documento(tipo_documento_id=m.tipo_documento_id, sociedad_id=m.sociedad_id, tercero_id=m.tercero_id,
                              fecha=r.proxima, moneda=m.moneda, tipo_cambio=m.tipo_cambio, condicion_pago=m.condicion_pago,
                              notas=m.notas, extra={**(m.extra or {}), "recurrente_id": r.id}, estado="BORRADOR",
                              creado_por=user.id, version=1)
            nuevo.tipo = m.tipo
            for x in m.lineas:
                nuevo.lineas.append(DocumentoLinea(
                    orden=x.orden, articulo_id=x.articulo_id, codigo=x.codigo, descripcion=x.descripcion, cantidad=x.cantidad,
                    unidad=x.unidad, precio_unitario=x.precio_unitario, descuento_pct=x.descuento_pct,
                    impuestos_codigos=x.impuestos_codigos))
            db.add(nuevo)
            db.flush()
            docs.calcular(db, nuevo)
            db.flush()
            if r.emitir:
                docs.emitir(db, user, nuevo.id, interno=True)
            creados.append({"recurrente": r.nombre, "documento_id": nuevo.id, "fecha": r.proxima,
                            "total": dinero.numero(dinero.decimal(nuevo.total))})
            r.proxima = siguiente_fecha(r.proxima, r.frecuencia, r.dia)
            if r.hasta and r.proxima > r.hasta:
                r.activo = False
    db.flush()
    if creados:
        registrar(db, user, "recurrente", 0, "generar", {"documentos": len(creados)})
    return creados
