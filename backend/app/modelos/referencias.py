"""Llaves foráneas de los códigos que guardan los documentos.

Los documentos guardan el código de la sociedad, el centro, la moneda… (es lo
que se lee en el documento y lo que llega del ERP) y la base garantiza que ese
código exista en su catálogo de la misma organización: llave foránea compuesta
(organizacion_id, código) → catálogo(organizacion_id, codigo). Un catálogo en
uso no se puede borrar ni cambiar de código; se desactiva. Los países son
compartidos: la llave es solo el código ISO.

Se declaran aquí, en un solo lugar, y se agregan a las tablas al importar los
modelos (las migraciones crean las mismas; Alembic las compara al revisar).
"""
from sqlalchemy import ForeignKeyConstraint

# tabla → [(columna, catálogo)]; catálogo de una organización salvo «paises»
REFERENCIAS: dict[str, list[tuple[str, str]]] = {
    "ordenes_compra": [("sociedad", "sociedades"), ("centro", "centros"), ("centro_destino", "centros"),
                       ("puerto_despacho", "puertos"), ("moneda", "monedas"), ("incoterm", "incoterms"),
                       ("condicion_pago", "condiciones_pago"), ("pais_origen", "paises"),
                       ("pais_procedencia", "paises")],
    "posiciones_oc": [("almacen", "almacenes"), ("marca", "marcas"), ("grupo", "grupos_articulos"),
                      ("categoria", "categorias_articulo"), ("unidad", "unidades_medida"), ("pais_origen", "paises")],
    "facturas": [("sociedad", "sociedades"), ("centro", "centros"), ("centro_destino", "centros"),
                 ("moneda", "monedas"), ("incoterm", "incoterms")],
    "factura_lineas": [("pais_origen", "paises")],
    "embarques": [("centro", "centros"), ("puerto_origen", "puertos"), ("puerto_destino", "puertos"),
                  ("tipo_transporte", "modos_transporte")],
    "unidades_carga": [("centro", "centros")],
    "recepcion_registros": [("centro", "centros")],
    "reglas_aprobacion_oc": [("moneda", "monedas"), ("sociedad", "sociedades")],
    "sociedades": [("moneda", "monedas"), ("pais", "paises")],
    "centros": [("puerto", "puertos"), ("pais", "paises")],
    "puertos": [("tipo", "modos_transporte"), ("pais", "paises")],
    "proveedores": [("pais", "paises")],
    "transportistas": [("pais", "paises")],
    "organizaciones": [("pais", "paises")],
    "grupos_articulos": [("categoria", "categorias_articulo")],
    "escalas_talla": [("categoria", "categorias_articulo")],
    "articulos": [("unidad", "unidades_medida")],
    "unidades_medida": [("base", "unidades_medida")],
    "atributos_variante": [("unidad", "unidades_medida")],
    "plantillas_caja": [("unidad", "unidades_medida")],
    "tipos_unidad": [("modo", "modos_transporte")],
    "reglas_leadtime": [("region", "regiones_leadtime"), ("pais", "paises"), ("puerto", "puertos")],
}
COMPARTIDOS = {"paises"}

# Coherencia de organización entre documentos: el hijo es de la misma
# organización que su padre. Llave compuesta (padre_id, organizacion_id) →
# padre(id, organizacion_id); el padre tiene un único (id, organizacion_id).
# Estas llaves las crean las migraciones y viven solo en la base: declaradas
# en los modelos harían ambiguas las relaciones del ORM (dos caminos entre las
# mismas tablas). alembic/env.py no las compara (terminan en _org) y
# tests/test_integridad_bd.py verifica que existan.
# tabla hija → [(columna, tabla padre)]
COHERENCIA: dict[str, list[tuple[str, str]]] = {
    "posiciones_oc": [("oc_id", "ordenes_compra"), ("receta_id", "recetas_empaque"), ("receta_regla_id", "reglas_empaque"),
                      ("articulo_version_id", "articulo_versiones")],
    "articulo_versiones": [("articulo_id", "articulos")],
    "aprobaciones_oc": [("oc_id", "ordenes_compra")],
    "ordenes_compra": [("proveedor_id", "proveedores")],
    "facturas": [("proveedor_id", "proveedores")],
    "factura_lineas": [("factura_id", "facturas"), ("posicion_oc_id", "posiciones_oc"), ("receta_id", "recetas_empaque"),
                       ("articulo_version_id", "articulo_versiones")],
    "packing_lists": [("factura_id", "facturas"), ("unidad_carga_id", "unidades_carga")],
    "pl_lineas": [("pl_id", "packing_lists"), ("factura_linea_id", "factura_lineas")],
    "grupos_cajas": [("pl_id", "packing_lists")],
    "grupo_cajas_items": [("grupo_id", "grupos_cajas"), ("pl_linea_id", "pl_lineas")],
    "recepciones": [("pl_linea_id", "pl_lineas")],
    "recepcion_registros": [("unidad_carga_id", "unidades_carga")],
    "recepcion_movimientos": [("registro_id", "recepcion_registros"), ("pl_linea_id", "pl_lineas")],
    "unidades_carga": [("embarque_id", "embarques")],
    "eventos_embarque": [("embarque_id", "embarques"), ("unidad_carga_id", "unidades_carga")],
    "tercero_roles": [("tercero_id", "terceros")],
    "clasificaciones_producto": [("producto_id", "productos")],
    "articulo_atributos": [("articulo_id", "articulos"), ("atributo_id", "atributos_variante")],
    "articulos": [("familia_etiquetado_id", "familias_etiquetado"), ("grupo_producto_id", "grupos_producto")],
    "grupos_articulos": [("familia_etiquetado_id", "familias_etiquetado"), ("grupo_producto_id", "grupos_producto")],
    "grupos_producto": [("padre_id", "grupos_producto")],
    "generaciones_etiqueta": [("pl_id", "packing_lists"), ("trabajo_id", "trabajos_etiqueta"), ("oc_id", "ordenes_compra")],
    "familias_etiquetado": [("padre_id", "familias_etiquetado")],
    "trabajo_etiqueta_registros": [("trabajo_id", "trabajos_etiqueta"), ("generacion_id", "generaciones_etiqueta"),
                                   ("oc_id", "ordenes_compra"), ("posicion_id", "posiciones_oc"), ("articulo_id", "articulos"),
                                   ("pl_id", "packing_lists"), ("plantilla_id", "plantillas_etiqueta"),
                                   ("version_id", "versiones_plantilla"), ("uso_id", "usos_diseno"),
                                   ("tipo_etiqueta_id", "tipos_etiqueta")],
    "plantillas_etiqueta": [("tipo_etiqueta_id", "tipos_etiqueta")],
    "tipos_etiqueta_empaques": [("tipo_etiqueta_id", "tipos_etiqueta"), ("tipo_empaque_id", "tipos_empaque")],
    "versiones_plantilla": [("plantilla_id", "plantillas_etiqueta")],
    "usos_diseno": [("tipo_etiqueta_id", "tipos_etiqueta"), ("plantilla_id", "plantillas_etiqueta"),
                    ("familia_id", "familias_etiquetado"), ("categoria_id", "categorias_etiquetado"), ("producto_id", "productos"),
                    ("articulo_id", "articulos"), ("tipo_empaque_id", "tipos_empaque"), ("oc_id", "ordenes_compra"),
                    ("grupo_id", "grupos_producto")],
    "productos": [("familia_etiquetado_id", "familias_etiquetado"), ("categoria_etiquetado_id", "categorias_etiquetado"),
                  ("grupo_producto_id", "grupos_producto")],
    "categorias_etiquetado": [("familia_id", "familias_etiquetado")],
    "receta_niveles": [("receta_id", "recetas_empaque"), ("tipo_empaque_id", "tipos_empaque")],
    "integracion_mapeos": [("integracion_id", "integraciones")],
    "integracion_ejecuciones": [("integracion_id", "integraciones")],
    "referencias_externas": [("integracion_id", "integraciones")],
    "reglas_empaque": [("receta_id", "recetas_empaque"), ("grupo_id", "grupos_producto"), ("producto_id", "productos"),
                       ("articulo_id", "articulos")],
    "generacion_items": [("generacion_id", "generaciones_etiqueta"), ("version_id", "versiones_plantilla"),
                         ("plantilla_id", "plantillas_etiqueta"), ("articulo_id", "articulos"), ("posicion_id", "posiciones_oc"),
                         ("familia_id", "familias_etiquetado"), ("trabajo_registro_id", "trabajo_etiqueta_registros"),
                         ("tipo_etiqueta_id", "tipos_etiqueta"), ("pl_id", "packing_lists"), ("grupo_cajas_id", "grupos_cajas"),
                         ("grupo_id", "grupos_producto")],
}
PADRES = sorted({p for lista in COHERENCIA.values() for _, p in lista})


def nombre_coherencia(tabla: str, columna: str) -> str:
    return f"fk_{tabla}_{columna}_org"


def nombre_unico_padre(tabla: str) -> str:
    return f"uq_{tabla}_id_org"


def nombre(tabla: str, columna: str) -> str:
    return f"fk_{tabla}_{columna}"


def restriccion(tabla: str, columna: str, catalogo: str) -> ForeignKeyConstraint:
    if catalogo in COMPARTIDOS:
        return ForeignKeyConstraint([columna], [f"{catalogo}.codigo"], name=nombre(tabla, columna))
    return ForeignKeyConstraint(["organizacion_id", columna], [f"{catalogo}.organizacion_id", f"{catalogo}.codigo"],
                                name=nombre(tabla, columna))


def aplicar(metadata) -> None:
    from sqlalchemy import UniqueConstraint

    for tabla in PADRES:
        t = metadata.tables[tabla]
        if nombre_unico_padre(tabla) not in {c.name for c in t.constraints}:
            t.append_constraint(UniqueConstraint("id", "organizacion_id", name=nombre_unico_padre(tabla)))
    for tabla, lista in REFERENCIAS.items():
        t = metadata.tables[tabla]
        existentes = {c.name for c in t.constraints}
        for columna, catalogo in lista:
            if nombre(tabla, columna) not in existentes:
                t.append_constraint(restriccion(tabla, columna, catalogo))
