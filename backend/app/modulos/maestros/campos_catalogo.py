"""Cómo se describe un campo de un catálogo de datos maestros
(definiciones.py y definiciones_logistica.py).
"""


# Dependencias entre campos (configurables, no propias de una empresa):
#   depende={"campo": <campo del mismo formulario>, "clave": <dato de la opción>}
# La opción solo vale si su dato `clave` coincide con el valor del campo (o lo
# contiene, si es una lista). Ej.: la marca de un artículo depende del
# proveedor (la marca trae la lista de proveedores que la manejan). El
# formulario filtra las opciones y el servidor lo valida al guardar.
# tipo: texto | entero | numero | bool | opcion (opciones) | opciones (varias, separadas por coma)
#       | ref (catalogo: guarda el id)
#       | codigo (catalogo: guarda el código, p. ej. país ISO) | correos
#       | multi (catalogo: varios registros, p. ej. las marcas de un proveedor)
# Las opciones de un campo con `lista` salen de las listas de valores de la
# empresa (core/listas.py), no del código.


def c(nombre, etiqueta, tipo="texto", obligatorio=False, **extra) -> dict:
    """Un campo: su nombre técnico, su etiqueta, su tipo y si es obligatorio; `extra` lleva el resto (max, filtro, catalogo…)."""
    return {"nombre": nombre, "etiqueta": etiqueta, "tipo": tipo, "obligatorio": obligatorio, **extra}
