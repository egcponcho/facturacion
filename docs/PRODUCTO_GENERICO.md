# Producto genérico

El sistema maneja cualquier tipo de producto (calzado, ropa, químicos, materias
primas, electrodomésticos, alimentos…) sin código propio de ningún tipo. Lo que
cambia de un tipo a otro se define con datos, desde la aplicación, sin cambiar
la base de datos.

## Capas

| Capa | Qué es | Dónde se configura | Tabla |
|---|---|---|---|
| Dominio | La familia comercial: químicos, calzado, materias primas… Orienta preguntas y candidatos. | Clasificación → Familias | `dominios_clasificacion` |
| Categoría | «¿Qué es el producto?». Pertenece a un dominio. | Clasificación → Familias | `categorias_producto` |
| Atributo de la ficha | Un dato técnico del producto, con tipo: texto, opción, varias opciones, sí/no, número con unidad, composición, país o juego de medidas. | Clasificación → Atributos | `atributos_def`, `atributo_opciones` |
| Ámbito del atributo | Dónde se pregunta y si es obligatorio: en todo el sistema, en un dominio, un capítulo o partida arancelaria o una categoría (SHOW, REQUIRE, HIDE), con condiciones. | Clasificación → Atributos | `atributo_ambitos` |
| Producto (estilo-color) | El producto con su ficha (`ficha`, JSON con un valor por atributo) y sus versiones cerradas. | Productos | `productos`, `producto_versiones` |
| Atributo de variante | Lo que distingue las variantes de un producto. Talla y color vienen de fábrica; la empresa agrega los suyos con tipo: texto, número en una unidad (220 V, 500 ml) o una de sus opciones. | Datos maestros → Atributos de variante | `atributos_variante`, `articulo_atributos` |
| Artículo (variante, SKU) | La unidad que se compra: sus datos, los valores de sus atributos de variante y sus campos propios. | Datos maestros → Artículos | `articulos` |
| Campos propios | Datos que la empresa agrega a artículos, OC, facturas y otros registros (texto, número, fecha, sí/no, opción). | Empresa → Campos propios | `definiciones_campo`, columna `extra` |
| Unidades de medida | En qué se cuenta o mide cada artículo. Una unidad contable solo admite enteros. Una unidad puede convertirse a una base de la lista (`base`, `equivale`). | Datos maestros → Unidades | `unidades_medida` |
| Empaque | Cómo se empaca: tipos de empaque (inner, master, pallet…), recetas de N niveles y reglas que eligen la receta. | Datos maestros → Empaque | `tipos_empaque`, `recetas_empaque`, `reglas_empaque` |
| Terminología | Cómo llama la empresa a cada cosa (estilo, modelo, referencia…). | Empresa → Terminología | configuración de la organización |

Nada de esto vive en el código: agregar un tipo de producto nuevo es crear su
dominio, sus categorías y sus atributos, y en los artículos sus atributos de
variante y sus unidades.

## Unidades que convierten

Cada unidad puede declarar a qué unidad base se convierte y cuántas unidades base
equivale una de ella:

| Unidad | Base | Equivale |
|---|---|---|
| DOC (docena) | UN | 12 |
| G (gramo) | KG | 0.001 |
| ML (mililitro) | L | 0.001 |

Las conversiones son de **un solo paso**: la base no se convierte a otra unidad.
Así, cualquier cantidad pasa a su base con una sola multiplicación, y dos
unidades se pueden comparar si llegan a la misma base. Unidades de magnitudes
distintas (DOC y KG) no se convierten.

En el código, `maestros/unidades.py` tiene dos funciones:

- `a_base(cantidad, unidad)`: devuelve la cantidad en su unidad base.
- `convertir(cantidad, de, a)`: convierte entre dos unidades, o devuelve None si
  no llegan a la misma base.

## Atributos de variante con tipo

- **Texto:** valor libre, como hasta ahora.
- **Número:** se guarda sin ceros de más (`500,0` → `500`) y lleva su unidad. En
  las etiquetas es un campo numérico.
- **Una de las opciones:** el formulario muestra solo esas opciones. Al guardar se
  respeta la forma escrita en el catálogo (`220 v` → `220 V`).

Un atributo que ya tiene valores en artículos solo cambia de tipo, o pierde
opciones, si todos esos valores siguen siendo válidos.

## Atributos de la ficha en etiquetas y reglas

Cada atributo activo de la ficha técnica está disponible como campo
`producto.atributo.<código>` en los diseños y en las condiciones de las reglas.
El valor se imprime así:

- una opción: el nombre de la opción;
- varias opciones: la lista de nombres;
- sí/no: Yes o No;
- composición: el texto «Parte: material»;
- número: el número, tal cual.

Los atributos de variante propios están en `articulo.atributo.<código>`.

## Versiones del artículo en los documentos

Un artículo cambia con el tiempo, pero un documento debe mostrar el artículo
como era cuando se hizo. Por eso cada línea de OC (`posiciones_oc`) y de factura
(`factura_lineas`) guarda `articulo_version_id`: la versión del artículo que usó.

- **Contenido:** una versión (`articulo_versiones`) es la foto completa del
  artículo: sus datos, marca, grupo, familia, prepack, valores de variante,
  campos propios, componentes del prepack y producto, con la ficha y el número
  de versión de la ficha.
- **Cuándo se crea:** solo cuando la foto cambia. La huella sha256 de los datos
  lo decide. Mientras el artículo no cambie, todas las líneas comparten la
  misma versión.
- **Asignación:** la versión se fija sola al crear la línea, o al cambiarle el
  artículo. Lo hace el hook de `app/modelos/versiones.py`, así que vale para
  cualquier origen: carga del ERP, asistente, factura o demo. Cambiar el
  artículo después no toca las líneas viejas.
- **Documentos anteriores:** los que ya existían al migrar (migración 0084)
  reciben la versión 1, con los datos del artículo de ese momento y marcada
  `migracion`.
- **Consulta:** `GET /api/catalogos/articulos/{id}/versiones` lista las
  versiones, con cuántas líneas de OC y de factura usa cada una y qué cambió
  respecto de la anterior. La vista del artículo en Datos maestros muestra esta
  misma lista.

El etiquetado de una lista de empaque lee el artículo desde la versión de la
línea de factura (etapa E4 de `ETIQUETADO_AUDITORIA.md`).
