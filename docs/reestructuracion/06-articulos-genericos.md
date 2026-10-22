# Artículos genéricos: núcleo mínimo, atributos, códigos y compuestos

Objetivo: que un producto y sus variantes guarden solo lo que tiene cualquier
producto de cualquier rubro, y que todo lo demás (marca, modelo, talla,
color, sabor, concentración, presentación…) sea un **atributo** que la
empresa define. Continúa `05-productos-generico.md` (núcleo mínimo y perfil
por familia), que había conservado las columnas de rubro; esta etapa las
retira (migración destructiva **0092**, autorizada, con respaldo y vuelta
atrás).

## 1. Modelo nuevo

| Tabla | Qué guarda |
|---|---|
| `productos` | Núcleo: código del producto (`codigo_generico`), nombre, unidad, familia (`grupo_producto_id`), proveedor (opcional), país de origen; con comercio exterior, la ficha técnica y la clasificación. |
| `articulos` | La variante, o un pack o kit: código de artículo (`sku`), producto (obligatorio), unidad, peso unitario, descripción, tipo (`SOLIDO` = simple, `PREPACK` = pack o kit), activo. |
| `atributos` | Los atributos de la empresa. Cada uno tiene su **nivel** (`PRODUCTO`: los comparten todas sus variantes; `VARIANTE`: las distinguen) y su **tipo de valor** (texto, número con unidad, una de sus opciones, fecha, sí/no o un registro de un catálogo: la marca apunta a `marcas` y, con proveedor, solo acepta sus marcas). |
| `producto_atributos` | Valores de los atributos de producto (marca, modelo, material…). |
| `articulo_atributos` | Valores de los atributos de variante (talla, color, sabor…). |
| `articulo_codigos` | Los códigos de la variante, varios por variante: `BARRAS` (GTIN/EAN/UPC), `PROVEEDOR` (con su proveedor) y `PACK` (el identificador de un pack, p. ej. `AB12`). |
| `articulo_componentes` | El contenido de un pack o un kit: el compuesto es el artículo mismo. Un **pack** junta variantes de un mismo producto (es de ese producto); un **kit** junta artículos de cualquier producto (es su propio producto). El contenido no cambia después de creado. |
| `escalas_valores` | Escalas de cualquier atributo de variante (antes solo tallas): sus valores en orden y la regla de su código (valor × factor, consecutivo o el mismo valor). |
| `grupos_producto` | La familia: la **única clasificación** del producto (antes había además grupos de artículos y categorías de artículo). Lleva sus ejes de variante, los datos que exige a sus productos y los días extra de lead time (antes en el grupo de artículos). |

Las líneas de OC y de factura guardan la **foto** de lo que eran el producto y
la variante al crearse: `atributos` (los del producto), `variante` (los de la
variante), `codigo_barras` y `codigo_pack`; la versión del artículo
(`articulo_versiones`) sigue igual.

En el código, `Articulo` lee del producto `generico`, `proveedor_id` y la
familia (propiedades híbridas: también sirven en consultas), y lee y escribe
sus códigos con `codigo(tipo)` / `poner_codigo(tipo, valor)` y sus valores
con `variantes`.

## 2. Qué se retiró

Tablas: `grupos_articulos`, `categorias_articulo`, `prepacks`,
`prepack_componentes`, `escalas_talla` y `atributos_variante` (reemplazadas
por las de arriba) y `familias_etiquetado` y `categorias_etiquetado`
(congeladas desde 0081).

Columnas: de `articulos` (`generico`, `sku_proveedor`, `upc`, `estilo`,
`color`, `talla`, `marca_id`, `grupo_id`, `proveedor_id`, `prepack_id`,
`extra`, familias de etiquetado), de `productos` (`estilo`, `color`,
`marca_id`, `grupo_id`, familias de etiquetado), de las líneas de OC y de
factura (`upc`, `estilo`, `color`, `talla`, `marca`, `grupo`, `categoria`,
`prepack`) y las referencias congeladas de `grupos_producto`.

Pantallas y archivos: el catálogo *Prepacks* (ahora *Nuevo pack o kit* en
Artículos y su carga masiva), *Grupos de artículos*, *Categorías de
artículo*, *Atributos de variante* (ahora *Atributos*, con su nivel), las
plantillas estáticas `plantilla_articulos.csv` y `plantilla_prepacks.csv`
(se usan las que arma el servidor con los atributos de la empresa) y los
campos propios de artículos (pasan a ser atributos de variante).

## 3. Migración 0092

1. Respalda en `respaldos_migracion` cada tabla y columna que se borra, tal
   como estaba.
2. Crea las tablas nuevas y copia: atributos (mismos ids), valores de
   variante, `MODELO` (desde estilo) y `MARCA` (desde `marca_id`) solo en las
   organizaciones que los usaban, códigos (upc → BARRAS, sku_proveedor →
   PROVEEDOR, el código del prepack → PACK), componentes, escalas (la regla
   TALLA pasa a VALOR) y la foto de las líneas.
3. Familia única: el producto sin familia toma la de su grupo de artículos;
   los días extra del grupo pasan a la familia (el mayor si varios grupos
   comparten familia; un grupo con días extra y sin familia se vuelve una
   familia).
4. `productos.proveedor_id` se completa con el de sus variantes;
   `articulos.producto_id` pasa a ser obligatorio (una variante sin producto
   recibe uno con su código).
5. Renombra las claves guardadas en diseños de etiqueta, reglas de etiquetado
   y de empaque, campos exigidos por familias, nombres propios de campos,
   datos obligatorios de la empresa y columnas de línea de los documentos:
   `articulo.upc` → `articulo.codigo_barras`, `articulo.talla` →
   `articulo.atributo.TALLA`, `articulo.estilo` → `producto.dato.MODELO`,
   `articulo.marca` → `producto.marca`, `linea.color` →
   `linea.atributo.COLOR`, `upc` → `codigo_barras`, `marca_id` →
   `atributo.MARCA`…
6. La vuelta atrás recrea la estructura anterior, devuelve lo respaldado y
   completa con los datos nuevos lo creado después.

## 4. API

| Antes | Ahora |
|---|---|
| `/catalogos/atributos_variante` | `/catalogos/atributos` (con `nivel`) |
| `POST /catalogos/genericos` con `estilo`, `color`, `marca_id`, `grupo_id`, `tallas` | `POST /catalogos/genericos` con `atributos` (`{"MARCA": "VANS", "MODELO": "…"}`), `variantes` (`[{"valores": {"TALLA": "8"}, "codigo_barras": …}]`) o `combinar` |
| `POST /catalogos/genericos/{gen}/tallas` | `POST /catalogos/genericos/{gen}/variantes` |
| `/catalogos/prepacks` (tipo CURVA o KIT) | `POST /catalogos/compuestos` (tipo PACK o KIT), `GET /catalogos/compuestos/{id}/componentes`, `/catalogos/compuestos/importar` y `/plantilla` |
| `/catalogos/escalas/{id}/tallas` | `/catalogos/escalas/{id}/valores` |
| Filtros de seguimiento `estilo`, `color`, `talla`, `grupo` | `familia`, `atr_<código>` (producto) y `var_<código>` (variante) |
| Respuestas con `upc`, `sku_proveedor`, `n_prepacks`, `prepacks`, `tallas` | `codigo_barras`, `codigo_proveedor`, `n_compuestos`, `compuestos`, `variantes` |

## 5. Decisiones

- **La marca es un atributo de producto** con tipo catálogo (`marcas`): sigue
  siendo un catálogo con sus proveedores autorizados, pero ningún código del
  sistema depende de que se llame MARCA.
- **El proveedor queda en el producto** (`productos.proveedor_id`): define
  quién ve y mantiene el producto; el código que el proveedor le da a cada
  variante va en `articulo_codigos` (PROVEEDOR).
- **Una sola clasificación**: la familia del producto. Grupos de artículos y
  categorías se retiraron; la regla de empaque y el lead time usan la familia.
- **Códigos en una tabla**: una variante puede tener varios códigos de
  barras; el identificador del pack es un código más.
- **Ningún atributo de fábrica** para una organización nueva: cada empresa
  define los suyos. La demostración (y las organizaciones que ya usaban
  marca, estilo, color o talla) los tienen porque venían de sus datos.
- La empresa puede volver obligatorio cualquier atributo
  (`atributo.<código>` en *Datos maestros → Artículos → datos
  obligatorios*); antes ese gobierno no veía los atributos.

## 6. Lo que se mantuvo a propósito

- `campos` y `ejes_variante` de la familia siguen como JSON (son
  configuración, no datos que se consulten por valor).
- No hay tabla aparte para comercio exterior: la ficha y la clasificación
  siguen en el producto, ocultas sin el complemento.
- Los tipos de artículo conservan sus códigos `SOLIDO` y `PREPACK` (se
  muestran como *Simple* y *Pack o kit*) y `productos.codigo_generico` su
  nombre, para no tocar índices ni integraciones que los leen.
- El motor de clasificación sigue leyendo un texto «estilo» de su entrada: es
  su vocabulario (texto de búsqueda), no una columna del artículo; la ficha
  le pasa el modelo.
