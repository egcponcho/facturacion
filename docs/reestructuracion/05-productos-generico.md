# Productos para cualquier rubro

Objetivo: que el módulo de Productos sirva igual a una empresa de calzado, de
químicos, de alimentos o de materias primas, sin datos de un rubro en el
código, en la base ni en los textos. Sigue la propuesta del análisis de
Productos (núcleo mínimo, perfil por familia, complementos) con las
alternativas **no destructivas** en todo lo que toca datos.

## 1. Qué pide ahora un producto

| Nivel | Qué se exige | Dónde se configura |
|---|---|---|
| Núcleo (siempre) | Código del producto, nombre, unidad; en cada variante, su código y los valores de los ejes de su familia | Fijo en el sistema |
| Empresa | Lo que marque como obligatorio para todos los productos (marca, grupo, proveedor, modelo, código de barras, peso, código del proveedor…) | Datos maestros → Artículos → datos obligatorios (gobierno, ya existía) |
| Familia | Lo que marque como obligatorio para sus productos (y sus subfamilias y categorías suman lo suyo) | Productos → Configuración → Familias → «Datos que exige a sus productos» |
| Comercio exterior | Ficha técnica aduanera, clasificación, acuerdos, versiones de ficha | Configuración → Empresa → Módulos → «Comercio exterior» |

El nombre, si no se escribe (carga masiva, API), toma el código del producto.

## 2. Cambios

### Datos (migración 0091, no destructiva)

- `articulos.marca_id`, `articulos.grupo_id` y `productos.proveedor_id` pasan
  a aceptar vacío. Solo cambia la nulabilidad: no se mueve ni se borra nada.
- La vuelta atrás se detiene si ya hay filas sin esos datos (no inventa
  valores).
- Las columnas `estilo`, `color` y `talla` **se conservan** (alternativa A del
  análisis): las variantes nuevas las llenan desde sus atributos y el modelo
  es un dato opcional más. Retirarlas sería destructivo y no hace falta para
  que el sistema sea genérico.

### Perfil de datos (`app/modulos/productos/perfil.py`)

- Una sola validación para el alta y el cambio de productos y variantes:
  asistente, modal de producto, agregar variantes, carga masiva (las dos
  plantillas) y edición.
- Lee los campos obligatorios de la familia (`GrupoProducto.campos`, los
  mismos que el etiquetado revisa antes de imprimir). Se exigen al guardar
  los que se escriben en el producto o la variante; los que salen de la ficha
  técnica los sigue revisando el etiquetado.
- `GET /api/productos/perfil?grupo_id=` devuelve el núcleo, lo que exige la
  empresa, lo que exige la familia y sus ejes: el asistente y el modal marcan
  esos datos como obligatorios.
- El editor de familias (`/grupos-producto`) permite marcar los datos que la
  familia exige; la API de grupos acepta `campos`.

> Corrección al análisis anterior: dije que `GrupoProducto.campos` no se usaba
> en ningún lado. No era así: el etiquetado ya lo leía para avisar de datos
> faltantes al imprimir. Ahora lo usan los dos.

### Comercio exterior como complemento

- Se apoya en el módulo activable «clasificacion», que ya existía
  (Configuración → Empresa → Módulos), y que ahora se describe como
  «Comercio exterior».
- `permisos.comercio_exterior()` y `permisos.exige_datos_aduana()`: sin el
  complemento, la factura no exige país de origen ni partida, ningún producto
  «bloquea facturas» y la sesión informa `requerir_datos_aduana: false`.
- Con el complemento apagado, la página del producto abre en sus variantes y
  oculta ficha técnica, clasificación, acuerdos, versiones y el flujo de
  revisión. El catálogo queda como lista simple (sin bandejas por estado ni
  columnas aduaneras) y el resumen muestra cifras del catálogo.
- Con el complemento encendido (la configuración actual de la demo) todo
  sigue como estaba.

### Interfaz

- Asistente «Nuevo producto»:
  - pide código, nombre y unidad;
  - muestra arriba lo que exijan la empresa o la familia;
  - el resto (proveedor, marca, grupo, modelo) va en «Más datos (opcionales)»;
  - la unidad no viene elegida de antemano;
  - «color fijo» desaparece: un valor único en un eje es compartido por todas
    las variantes.
- Modal de producto y botón «Editar producto» en la página del producto, con
  los mismos criterios.
- Sin proveedor elegido se ofrecen todas las marcas; con proveedor, solo las
  suyas (como antes).
- La columna «Producto» del catálogo ordena y filtra por nombre (o código), no
  por estilo.
- El código de variante en Datos maestros ya no supone códigos de producto
  de 8 caracteres (`sku.slice(8)`): se calcula con el código real del
  producto.
- Textos neutrales: Producto / Variante / Pack o kit / Código de barras /
  Código del proveedor / Modelo, sin rubros de ejemplo («calzado,
  químicos…»), sin «estilo-color», «prepack», «cartón» ni «UPC» como nombre
  del código de barras.

### Carga masiva

- Plantilla nueva con hojas **Products** y **Variants**:
  - código, nombre y unidad obligatorios; proveedor, marca, grupo y modelo
    opcionales;
  - una columna por atributo de variante.
- Se siguen leyendo las hojas Generics y Sizes de las plantillas anteriores.
- Un proveedor solo carga productos propios.
- Cada variante pasa por el perfil de su familia: la fila que no cumple se
  rechaza con el dato que falta.

## 3. Lo que no se hizo y por qué

| Tema | Estado | Motivo |
|---|---|---|
| Unificar grupo de artículos y familia (D-01) | Pendiente de decisión | Cambia cómo se clasifica todo y mueve datos (días extra, etiquetado anterior). Para ser genérico basta con que el grupo sea opcional, y ya lo es. |
| Borrar las columnas estilo, color y talla | No se hará sin autorización | Es destructivo; se conservan como copias. |
| Proveedores con varios códigos por variante | Fuera de alcance | Requiere tabla nueva; hoy hay un código del proveedor por variante. |

## 4. Verificación

- Suite completa del servidor (SQLite): 743 pasan, 4 omitidas, 0 fallan.
- `verificar.sh`: extracción de textos, ruff, traducciones al día, eslint y build: sin errores.
- Pruebas nuevas en `backend/tests/test_producto_cualquier_rubro.py`:
  - producto solo con su núcleo;
  - marca exigida por la empresa;
  - código de barras exigido por la familia (asistente, agregar variantes,
    editor de familias);
  - carga masiva con las hojas nuevas;
  - complemento de comercio exterior apagado.
- `test_filtros_productos.py` ajustada: la columna «Producto» ahora es el
  nombre.
- Recorrido en el navegador (escritorio y celular):
  - asistente sin familia;
  - página del producto con y sin el complemento;
  - editor de familias;
  - catálogo y resumen sin el complemento.

  Sin errores de página ni respuestas 4xx/5xx inesperadas, y sin desborde
  horizontal en 390 px.
- PostgreSQL: no verificado en este entorno (no hay servidor). La migración
  0091 solo cambia nulabilidad con `batch_alter_table`, igual que la 0085.
