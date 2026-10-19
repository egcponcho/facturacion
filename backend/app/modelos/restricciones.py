"""Restricciones CHECK del esquema: la base rechaza datos imposibles aunque
falle una validación del código (cantidades o precios negativos, vigencias
invertidas, estados fuera de su máquina de estados).

Se declaran aquí, en un solo lugar, y se agregan a las tablas al importar los
modelos. Las migraciones crean las mismas (Alembic no compara las CHECK al
autogenerar: tests/test_integridad_bd.py verifica que la base tenga todas).
"""
from sqlalchemy import CheckConstraint

from app.core import estados


def _en(columna: str, valores) -> str:
    return f"{columna} IN ({', '.join(repr(str(v)) for v in valores)})"


def _no_negativo(*columnas: str) -> list[tuple[str, str]]:
    return [(c, f"{c} IS NULL OR {c} >= 0") for c in columnas]


def _vigencia(desde: str = "vigente_desde", hasta: str = "vigente_hasta") -> tuple[str, str]:
    return ("vigencia" if desde == "vigente_desde" else f"{desde}_{hasta}",
            f"{hasta} IS NULL OR {desde} IS NULL OR {hasta} >= {desde}")


# tabla → [(sufijo del nombre, condición)]; el nombre es ck_<tabla>_<sufijo>
RESTRICCIONES: dict[str, list[tuple[str, str]]] = {
    "ordenes_compra": [("estado", _en("estado", estados.OC.estados))],
    "posiciones_oc": _no_negativo("cantidad", "precio", "casepack", "inner_pack", "unidades_por_caja"),
    "aprobaciones_oc": [("estado", _en("estado", ("PENDIENTE", "APROBADA", "RECHAZADA"))), ("paso", "paso >= 0")],
    "facturas": [("estado", _en("estado", estados.FACTURA.estados))],
    "factura_lineas": _no_negativo("cantidad", "precio_unitario", "precio_oc", "casepack", "inner_pack",
                                   "unidades_por_caja"),
    "packing_lists": [("estado", _en("estado", estados.PL.estados))],
    "pl_lineas": _no_negativo("cantidad"),
    "grupos_cajas": _no_negativo("num_cajas", "largo", "ancho", "alto", "peso_neto_caja", "peso_bruto_caja", "tara",
                                 "neto_manual"),
    "grupo_cajas_items": _no_negativo("cantidad_por_caja"),
    "plantillas_caja": _no_negativo("cantidad_por_caja", "largo", "ancho", "alto", "tara"),
    "tipos_empaque": _no_negativo("largo", "ancho", "alto", "tara", "peso_max", "max_unidades", "max_contenido"),
    "recepciones": _no_negativo("cantidad_recibida", "cantidad_danada") + [
        ("danada_hasta_recibida", "cantidad_danada IS NULL OR cantidad_danada <= cantidad_recibida")],
    "tipos_etiqueta": [("sujeto", _en("sujeto", ("ARTICULO", "BULTO", "DOCUMENTO"))),
                       ("cantidad", _en("cantidad", ("POR_UNIDAD", "POR_LINEA", "POR_ARTICULO", "POR_BULTO", "POR_DOCUMENTO",
                                                     "MANUAL")))],
    "campos_etiqueta": [("tipo", _en("tipo", ("texto", "numero", "fecha"))),
                        ("politica", _en("politica", ("PRIMERA", "ADVERTIR", "BLOQUEAR")))],
    "trabajos_etiqueta": [("origen", _en("origen", ("OC", "ARTICULOS", "PACKING"))),
                          ("estado", _en("estado", ("BORRADOR", "VALIDADO", "EN_PROCESO", "GENERADO", "PARCIAL", "ERROR",
                                                    "CANCELADO"))),
                          *_no_negativo("total", "progreso", "paso")],
    "generaciones_etiqueta": _no_negativo("descargas"),
    "trabajo_etiqueta_registros": [("estado", _en("estado", ("LISTO", "ADVERTENCIA", "ERROR", "GENERADO", "OMITIDO"))),
                                   *_no_negativo("cantidad")],
    "recepcion_registros": [("tipo", _en("tipo", ("CONTEO", "AJUSTE", "SIN_CONTEO")))],
    "unidades_carga": [("recepcion_estado", _en("recepcion_estado", ("PENDIENTE", "EN_RECEPCION", "RECIBIDA")))],
    "embarques": [("estado", _en("estado", estados.EMBARQUE.estados))],
    "reglas_impuesto": _no_negativo("tasa") + [_vigencia(), _vigencia("umbral_desde", "umbral_hasta")],
    "incisos_nacionales": [_vigencia()],
    "nodos_arancel": [_vigencia()],
    "notas_sac": [_vigencia()],
    "overrides_arancel": [_vigencia()],
    "regulaciones": [_vigencia()],
    "versiones_dataset": [_vigencia()],
    "producto_versiones": [_vigencia("desde", "hasta")],
}


def nombre(tabla: str, sufijo: str) -> str:
    return f"ck_{tabla}_{sufijo}"


def aplicar(metadata) -> None:
    """Agrega las restricciones a las tablas de los modelos."""
    for tabla, lista in RESTRICCIONES.items():
        t = metadata.tables[tabla]
        existentes = {c.name for c in t.constraints}
        for sufijo, condicion in lista:
            if nombre(tabla, sufijo) not in existentes:
                t.append_constraint(CheckConstraint(condicion, name=nombre(tabla, sufijo)))
