# Productos: auditoría de interfaz, valores fijos y rediseño

Continúa `06-articulos-genericos.md` (atributos por familia). Objetivo de esta
etapa: revisar el módulo de productos completo (catálogo, página del
producto, producto nuevo, configuración), buscar valores de un rubro fijos en
el código y rehacer el diseño: colores nuevos y una forma ordenada de mostrar
los datos que cambian según la familia (atributos y variantes).

Las capturas de antes y después se tomaron con la demostración (usuario
`interno@demo.com`, 1440 px y 390 px, tema claro y oscuro).

## 1. Hallazgos

| # | Pantalla | Hallazgo | Evidencia | Estado |
|---|---|---|---|---|
| H1 | Producto | La cabecera ponía todos los atributos en una sola línea corrida («Marca Vans · Estilo VN000EE3 · Género Unisex…»); con 6–8 atributos se volvía un párrafo y no se veía qué faltaba. | Captura de antes, `ProductoView.vue` (bloque `doc-cabeza`). | Corregido (2.2) |
| H2 | Producto y catálogo | El resumen de variantes era un texto armado en el servidor (`resumen_variantes`), con el nombre del atributo en inglés («Size 7–12») y los valores en mayúsculas («BLK BLACK»). | `variantes.rango` hacía `upper()`; el frontend mostraba el texto tal cual. | Corregido (2.1) |
| H3 | Producto → Variantes | Todas las variantes en una tabla con una sola columna «Variante» («BLK Black · 7»): no se podía ordenar ni filtrar por talla o color, y no se veía qué combinación faltaba. | `colArticulos` en `ProductoView.vue`. | Corregido (2.3) |
| H4 | Producto | 12 pestañas en una fila; en pantallas medianas la última quedaba fuera de la vista. | Captura de antes. | Corregido (2.2) |
| H5 | Producto → soporte de clasificación | Las notas legales se mostraban completas (algunas de 30+ líneas) y empujaban el resto del panel. | Captura de antes. | Corregido: cada nota se recorta a 4 líneas (completa al pasar el cursor) y «Ver las N notas» las abre |
| H6 | Traducción | «Pack {0}» se traducía «Empacar {0}» (verbo) en el título de cada pack. | `es.json` (frontend y servidor). | Corregido |
| H7 | Colores | Azul marino con celeste: poco contraste entre la barra lateral y el acento, y una sola paleta fija para todas las empresas. | `styles.css` (`--marino`, `--acento`). | Corregido (2.4) |
| H8 | Catálogo, artículos | Las variantes de cada fila salían como texto («Color BLK BLACK · Size 7–12»), difícil de leer en filas con muchos valores. | `ProductosView.vue`, `ArticulosGenericos.vue`. | Corregido: fichas por atributo |
| H9 | Producto nuevo | Las tarjetas de familia mostraban solo el nombre: no se sabía qué datos pedía cada familia ni por qué atributos se distinguían sus variantes hasta el paso siguiente. | `NuevoProductoView.vue`. | Corregido: «Datos» y «Variantes por» en cada tarjeta |
| H10 | Producto nuevo → Variantes | Los valores elegidos (rangos de talla, escalas) no se veían expandidos antes de crear: había que imaginar cuántas variantes saldrían. | `variantes.js`. | Corregido: fichas con los valores expandidos |
| H11 | Producto | Un atributo con valor que su familia ya no usa (por un cambio de familia anterior a 0094) no se distinguía de los demás. | `_atributos_familia` no existía. | Corregido: se marca con aviso «Su familia ya no usa este atributo» |
| H12 | Barra lateral | El selector de idioma tenía el texto blanco fijo; con una barra lateral clara no se leía. | `styles.css` (`#fff` fijo). | Corregido: tokens `--lateral-*` |

## 2. Qué se cambió

### 2.1 Datos estructurados en la API (sin textos armados)

- `variantes.por_atributo(db, articulos, ejes)` devuelve
  `[{codigo, nombre, valores, texto}]`: los valores de cada atributo **en su
  orden** (números como números; los demás en el orden de sus opciones y
  escalas), sin repetir y con el texto como se escribió la primera vez. Los
  ejes de la familia van primero aunque aún no tengan valores. Los packs no
  cuentan.
- Catálogo y artículos: cada fila trae `variantes_atributos`.
- Detalle del producto: `atributos_familia` (cada atributo de producto que
  pide su familia, con `valor`, `tipo`, `unidad`, `general` y `fuera`) y
  `ejes` (las variantes por atributo); cada componente de un pack trae sus
  `valores` por atributo.
- `rango` ya no pasa todo a mayúsculas.
- `resumen_variantes` (texto) se conserva para PDF, Excel y búsquedas.

### 2.2 Página del producto

- **Cabecera nueva** (`CabeceraProducto.vue`): ruta de la familia (enlace al
  catálogo filtrado), nombre, código, proveedor y estado; debajo, dos
  bloques:
  - **Datos del producto**: una tarjeta por atributo que pide la familia,
    más la unidad y el origen (con comercio exterior). Un dato vacío se ve
    punteado («Sin dato»), con un contador «N sin dato» y el enlace
    «Completar».
  - **Variantes**: una fila por eje con sus valores como fichas (hasta 14 y
    «+N»), el total y «Ver todo».
- **Pestañas**: las seis de uso diario a la vista (Ficha técnica, Variantes y
  packs, Documentos técnicos, Uso, Empaque, Etiquetas) y las de consulta
  (acuerdos, versiones, historial) en «Más». La barra pasa a dos líneas en
  pantallas angostas en vez de esconder pestañas.

### 2.3 Variantes y packs (`VariantesProducto.vue`)

- **Matriz** (por defecto): el último eje en columnas y los demás en filas,
  armadas con las combinaciones que existen. Cada celda muestra el código de
  la variante y si tiene código de barras; las inactivas van tachadas y las
  combinaciones que no existen, punteadas. Cada fila tiene su total.
- **Lista**: la tabla de siempre, con **una columna por atributo** (se puede
  ordenar y filtrar por talla, color, sabor…) más código de barras, código
  del proveedor, unidad, peso y estado. Se recuerda la última vista elegida.
- **Packs y kits** como tarjetas: lo que comparten sus componentes una sola
  vez («Color: BLK Black») y lo que cambia como fichas («7 ×1, 8 ×2…»).
- Si alguna variante no tiene valor para un eje de su familia, se avisa debajo de la matriz
  (esas variantes solo aparecen en la lista).

### 2.4 Colores

- Cuatro paletas, cada una con su tema claro y oscuro: **Índigo** (la de
  fábrica, barra lateral clara), **Esmeralda**, **Terracota** y **Marino**.
- Se elige en **Configuración → Empresa → Marca → Paleta**; se aplica al
  instante a todos los usuarios de la empresa (`organizacion.marca.paleta`,
  validada en el servidor). El «color de acento» anterior queda como ajuste
  opcional.
- Neutros y colores de estado (bien, aviso, error, info) son los mismos en
  todas las paletas: un estado nunca cambia de color por cambiar de paleta.
- Las barras del resumen de productos quedan en un solo tono a propósito:
  muestran cantidad, y cada estado ya lleva su etiqueta.

## 3. Revisión de valores fijos

Búsqueda en `frontend/src` y `backend/app` (sin semilla de demostración) de
códigos de atributos, familias o valores de un rubro (`TALLA`, `COLOR`,
`MARCA`, `CALZADO`, `ROPA`, `GENERO`, `CORTE`…):

- **Frontend**: ninguno. Las pantallas toman los atributos, sus nombres, ejes
  y valores de la API. Los únicos códigos fijos son los tipos de artículo del
  sistema (`SOLIDO`, `PREPACK`), que no son de un rubro.
- **Servidor**: los códigos de rubro solo aparecen en comentarios y
  docstrings como ejemplo (`modelos/compras.py:154`,
  `maestros/genericos.py:159`, `seguimiento/seguimiento.py:127`,
  `esquemas/productos.py:148` y `:204`).
- **Pendiente (no se cambió en esta etapa)**:
  - `productos/ficha.py` (historial de composiciones, líneas ~229–296) usa
    las llaves `estilo` y `color` para agrupar el historial de la ficha
    técnica. Es vocabulario de la clasificación, no un atributo fijo, pero
    convendría leerlo de los atributos de la familia. Cambiarlo toca datos
    guardados en el historial; requiere decidir cómo convertir lo existente.
  - `productos/descripciones.py:108`: la descripción comercial se arma en
    MAYÚSCULAS («CALZADO VANS»). Es la costumbre en documentos de aduana; si
    la empresa la quiere en otro formato, debería ser un ajuste de la
    plantilla y no un `upper()` fijo.

## 4. Sugerencias para siguientes etapas

1. **Edición en la matriz**: activar o desactivar una variante, o crear la
   combinación que falta, directamente desde la celda.
2. **Fotos por valor** (por ejemplo, una foto por color) y mostrarlas en la
   fila de la matriz.
3. **Completar datos en lote**: desde el catálogo, filtrar «productos con
   datos sin llenar» de una familia y llenarlos en una tabla editable.
4. **Ficha técnica y datos del producto**: hoy la ficha técnica (comercio
   exterior) y los datos de la familia se editan en lugares distintos; un
   solo formulario por secciones evitaría ir y venir.
5. **Historial de la ficha por atributos** (ver 3): reemplazar `estilo` y
   `color` por los atributos de la familia.
6. **Formato de la descripción comercial** configurable (mayúsculas o no).
7. **Paleta por usuario**: hoy la elige la empresa; se podría permitir que
   cada usuario la cambie en su perfil, como ya ocurre con el tema claro u
   oscuro.

## 5. Verificación

- Pruebas nuevas: `tests/test_producto_vista.py` (orden y casos de los
  valores; datos de la familia y ejes en el detalle y el catálogo; familia
  nueva con datos vacíos y ejes sin valores) y `test_marca.py::
  test_paleta_de_la_interfaz`.
- Suites: SQLite completa, PostgreSQL completa, ruff, eslint, extracción y
  prueba de traducciones, compilación de Vite y los recorridos e2e
  (`recorrido.mjs` con 4 usuarios en 1440 px y 390 px; `etiquetado.mjs`).
