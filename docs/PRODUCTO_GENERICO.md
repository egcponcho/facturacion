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
| Producto | El producto con su código propio, su ficha (`ficha`, JSON con un valor por atributo) y sus versiones cerradas. Estilo y color son opcionales. | Productos | `productos`, `producto_versiones` |
| Atributo de variante | Lo que distingue las variantes de un producto (talla, color, sabor, presentación, concentración, voltaje…). Talla y color vienen de fábrica; la empresa agrega los suyos con tipo: texto, número en una unidad (220 V, 500 ml) o una de sus opciones. Cada atributo vale en sus familias o en todas. | Datos maestros → Atributos; Familias | `atributos`, `atributo_familias`, `articulo_atributos` |
| Artículo (variante, SKU) | La unidad que se compra: sus datos, los valores de sus atributos de variante y sus campos propios. | Datos maestros → Artículos | `articulos` |
| Campos propios | Datos que la empresa agrega a artículos, OC, facturas y otros registros (texto, número, fecha, sí/no, opción). | Empresa → Campos propios | `definiciones_campo`, columna `extra` |
| Unidades de medida | En qué se cuenta o mide cada artículo. Una unidad contable solo admite enteros. Una unidad puede convertirse a una base de la lista (`base`, `equivale`). | Datos maestros → Unidades | `unidades_medida` |
| Empaque | Cómo se empaca: tipos de empaque (inner, master, pallet…), recetas de N niveles y reglas que eligen la receta. | Datos maestros → Empaque | `tipos_empaque`, `recetas_empaque`, `reglas_empaque` |
| Terminología | Cómo llama la empresa a cada cosa (estilo, modelo, referencia…). | Empresa → Terminología | configuración de la organización |

Nada de esto vive en el código: agregar un tipo de producto nuevo es crear su
dominio, sus categorías y sus atributos, y en los artículos sus atributos de
variante y sus unidades.

## Identidad del producto y sus variantes

- **El producto** se identifica por su código propio (`codigo_generico`, único en
  la empresa). Estilo y color son opcionales: los usa quien identifica así sus
  productos (calzado, ropa). Sin código, el producto toma estilo-color si el
  artículo tiene estilo; si no, el código del artículo (un producto sin
  variantes, como una resina o una materia prima).
- **La variante (artículo)** se distingue por sus valores de variante, guardados
  en `articulo_atributos`. Talla y color son dos atributos más (de fábrica); sus
  columnas en el artículo quedan como copia para lo que todavía las lee y se
  sincronizan solas en los dos sentidos.
- **Los atributos de cada familia:** cada atributo vale en las familias que
  tiene (y en sus subfamilias y categorías) o en todas si es general
  (`atributo_familias`, `atributos.general`, migración 0094). Las variantes de
  un producto se distinguen por los atributos de variante que valen en su
  familia, en el orden de los atributos:
  - calzado: COLOR, TALLA;
  - químico: CONCENTRACION, ENVASE;
  - alimento: SABOR, PRESENTACION.

  Un producto sin familia solo lleva atributos generales. Detalle en
  `docs/reestructuracion/06-articulos-genericos.md`, sección 8.
- **Sin repetidos:** dos variantes del mismo producto no pueden tener los mismos
  valores. Comparten estilo, marca y proveedor, y el color solo si el producto
  lo fija.
- **Líneas de documento:** cada línea de OC y de factura guarda sus valores de
  variante (`variante`, en el orden de los atributos). La columna «Variante» de
  los documentos se arma con ellos («BLACK · 9.5», «30 % · 1 L»).

## Plan de la generalización (G1–G6)

| Etapa | Contenido |
|---|---|
| G1 ✓ | Identidad por código, talla y color como valores de variante, ejes por familia, variante en las líneas (migración 0085) |
| G2 ✓ | Compuestos genéricos: simple, pack de variantes (la curva, de cualquier atributo) o kit; unidad del compuesto configurable en lugar de CJ |
| G3 ✓ | Alta de productos: familia → atributos → valores (escalas de cualquier atributo) → variantes; cargas sin estilo/color obligatorios |
| G4 ✓ | Documentos (factura, packing list, ficha, Excel, reportes) con la columna «Variante» y columnas configurables |
| G5 ✓ | Seguimiento, existencias por artículo, reportes, clasificación y empaque sin supuestos de calzado |
| G6 ✓ | Pantallas con «Variante» y los atributos configurados |

## Packs y kits (compuestos)

- **Pack de variantes** (la «curva»): junta variantes de un mismo producto, de
  cualquier atributo (tallas, sabores, presentaciones), con su cantidad por
  unidad. Comparte la ficha del producto.
- **Kit:** junta artículos de cualquier producto (un juego, una caja de
  regalo). Es su propio producto.
- **Unidad:** la de un compuesto es cualquier unidad que se cuente. Las
  unidades marcadas «solo para packs y kits» (la caja CJ de fábrica u otras de
  la empresa) no las usa un artículo simple.

## Alta de productos y variantes

1. Se crea el producto con su código, su nombre, su familia, el proveedor, la
   marca, el grupo y la unidad. Estilo y color fijo son opcionales.
2. Se agregan las variantes de una de dos formas:
   - **Combinando** los valores de los atributos de la familia: todos los
     colores por todas las tallas, todas las concentraciones por todos los
     envases. Se admiten tramos («7-10, 12», «S-XL») y escalas de valores.
   - **Fila por fila.**
3. **Código de cada artículo:** el que se escriba. Si no se escribe, se arma
   con el código del producto más uno de la variante: el de la escala de
   valores usada, la regla usual talla × 10 o el siguiente libre.
4. **Escalas de valores:** cada escala ordena los valores de un atributo
   (`escalas_talla.atributo`, migración 0087). No es solo de tallas.
5. **Carga masiva:** la hoja de variantes acepta una columna por atributo de
   variante, por código o por nombre.

## Documentos, pantallas y reportes

- **Factura y packing list (PDF y Excel):** en lugar de Estilo, Color y Talla
  fijos llevan los datos de línea que la empresa elige en Configuración →
  Empresa → Documentos (`columnas_linea`). Por defecto, `estilo,variante`:
  - `variante`: todos los valores de variante, en su orden;
  - `estilo`: estilo o modelo;
  - `upc`;
  - `atributo.<CÓDIGO>`: un atributo de variante por separado.
- **Ficha técnica en PDF:** lista las variantes del producto.
- **Seguimiento, existencias, recepción, OC, factura y packing list:** muestran
  la «Variante» de cada línea. Las existencias van por artículo, sin talla.
- **Empaque:** «mezclar productos» compara el producto, no el estilo-color.
  «Mezclar variantes» compara el artículo.

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
