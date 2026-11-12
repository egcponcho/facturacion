# Catálogo de productos desde cero: propuesta de diseño

**Estado: propuesta para aprobar.** No se ha cambiado código ni datos.

Pedido: eliminar todo lo de producto, montarlo de nuevo desde cero y que el
resto del sistema se adapte, sin partes mal integradas. Las **familias** son un
solo controlador, y cada módulo que las usa agrega lo suyo aparte.

## 1. Por qué hoy no se siente integrado (diagnóstico)

| Problema | Evidencia |
|---|---|
| **Tres «familias» distintas** | `grupos_producto` (árbol familia/categoría: productos, empaque, etiquetado); `dominios_clasificacion` + `categorias_producto` (clasificación arancelaria), con un campo de texto `familia` que no apunta al árbol. |
| **La familia guarda cosas de otros módulos** | `grupos_producto.dias_extra` (lead times), `campos` y `condiciones` (perfil de datos y reconocimiento) en la misma tabla. |
| **El producto mezcla núcleo y comercio exterior** | `productos` tiene, además de código, nombre y unidad, la ficha técnica (`ficha`, `faltan`, `ficha_completa`, `version_ficha`), la descripción aduanera, la partida (`sac_codigo`), el país de origen y el estado de aprobación aduanera. |
| **El modelo está repartido** | Producto en `modelos/productos.py`; artículos, atributos y códigos en `modelos/maestros.py`; la familia en `modelos/grupos.py`. Hay pantallas en Productos y en Datos maestros → Artículos. |
| **Cada módulo lee las tablas a su manera** | 13 módulos del servidor importan `Producto` o `Articulo` directamente (etiquetado 19 archivos, maestros 16, clasificación 6, empaque 6, seguimiento 6…). 20 llaves foráneas apuntan a productos, artículos, atributos o familias. Cuando el modelo cambia, cada módulo se arregla por separado: ese es el origen de las partes «mal integradas». |
| **Nombres heredados** | `codigo_generico`, `PREPACK`/`SOLIDO`, `resumen_variantes` en texto, la marca como atributo y también como catálogo. |

## 2. Principios del diseño nuevo

1. **Un módulo dueño: `catalogo`.** Familias, atributos, productos y
   artículos viven en un solo módulo (modelos, servicio, API y pantallas).
2. **Nadie más toca sus tablas.** Los demás módulos usan solo el **servicio
   del catálogo** (funciones con datos ya listos: buscar un artículo,
   describirlo, sus valores por atributo, su familia). Una prueba de
   arquitectura falla si un módulo importa los modelos del catálogo.
3. **La familia es un solo controlador.** Una tabla, un árbol y una
   pantalla. Cada módulo que la usa guarda **su configuración en su propia
   tabla** (`familia_<modulo>`), ligada por `familia_id`, y aporta **su
   pestaña** a la pantalla de la familia.
4. **El producto es el núcleo; lo demás son complementos.** Comercio
   exterior (ficha, clasificación, partidas) es un complemento con sus
   propias tablas `producto_comex…`. Sin el complemento activo, no existe.
5. **Datos, no textos armados.** La API devuelve los valores por atributo;
   las pantallas y los documentos los presentan.

## 3. Modelo nuevo (módulo `catalogo`)

| Tabla | Qué guarda |
|---|---|
| `familias` | El árbol único: `codigo`, `nombre`, `padre_id`, `orden`, `activa`. Sin campos de otros módulos. |
| `atributos` | Los atributos de la empresa: `codigo`, `nombre`, `tipo` (texto, número con unidad, opción, fecha, sí/no, catálogo), opciones o escala de valores. |
| `familia_atributos` | Qué atributos lleva cada familia y **con qué papel**: `dato` (del producto) o `eje` (distingue variantes); `obligatorio`, `orden`. Lo heredan las subfamilias. Reemplaza `atributos.nivel`, `atributos.general`, `atributo_familias` y `grupos_producto.campos`. El mismo atributo puede ser dato en una familia y eje en otra (p. ej. el color). |
| `productos` | Solo el núcleo: `codigo`, `nombre`, `familia_id` (**obligatoria**; la empresa tiene una familia «General» de fábrica), `unidad`, `proveedor_id` (opcional), `estado` (borrador, activo, inactivo), fechas. |
| `producto_valores` | Los valores de sus atributos `dato`. |
| `articulos` | Lo que se pide, factura y etiqueta: `codigo`, `producto_id`, `tipo` (`VARIANTE` o `PACK`), `activo`, `peso`, `unidad` si difiere. |
| `articulo_valores` | Los valores de sus ejes (talla, color, sabor…). |
| `articulo_codigos` | Código de barras y código del proveedor (varios). |
| `pack_componentes` | Qué variantes y cuántas lleva un pack o kit. |

Las marcas siguen siendo un catálogo; el atributo «marca» es de tipo
catálogo y apunta a él.

## 4. Familias: un controlador, una sección por módulo

```
familias (catálogo) ─┬─ familia_atributos      (catálogo: datos y ejes)
                     ├─ familia_comex          (comercio exterior: dominio, categoría aduanera, plantilla de descripción, capítulos)
                     ├─ familia_empaque        (empaque: reglas por familia; hoy reglas_empaque.grupo_id)
                     ├─ familia_etiquetado     (etiquetado: categorías y reglas; hoy usos_diseno.grupo_id)
                     └─ familia_logistica      (logística: días extra; hoy grupos_producto.dias_extra)
```

- **Servidor.** Cada módulo registra su sección (`registrar_seccion_familia`)
  con su esquema, validación y qué hacer cuando una familia se mueve o se
  borra. El catálogo no conoce a los módulos; los recorre por el registro.
- **Pantalla.** *Productos → Configuración → Familias*: árbol a la
  izquierda y, a la derecha, la familia con las pestañas **General**
  (nombre, padre) y **Atributos** (datos y ejes), más una por cada módulo
  activo (*Comercio exterior*, *Empaque*, *Etiquetado*, *Logística*).
  Las pantallas de configuración de cada módulo muestran la misma sección
  con un enlace a la familia: nada se configura en dos lugares.
- **Clasificación.** `dominios_clasificacion` y `categorias_producto`
  (conocimiento del arancel: preguntas, plantillas, capítulos) se quedan
  como catálogo de comercio exterior. La familia **elige** su categoría
  aduanera en `familia_comex`, con lo que desaparece el campo de texto
  `familia` suelto.

## 5. Cómo se conecta cada módulo

| Módulo | Hoy | Nuevo |
|---|---|---|
| Compras (OC) | `posiciones_oc.articulo_id` + foto de atributos | Igual llave, pero lee el artículo por el servicio (`catalogo.describir`) y guarda la foto que este le da. |
| Facturación / packing list | Leen artículos y producto directo | Por el servicio; la descripción aduanera la da el complemento de comercio exterior. |
| Recepción, seguimiento, transporte, reportes | Consultas propias a artículos y atributos | Filtros y columnas por atributo desde `catalogo.ejes()` y `catalogo.valores()`. |
| Etiquetado | `usos_diseno` → producto, artículo y grupo; resolución propia de familia | Reglas por familia en `familia_etiquetado`; datos del artículo por el servicio. |
| Empaque | `reglas_empaque` → producto, artículo y grupo | Reglas por familia en `familia_empaque`; reglas por producto o artículo igual que hoy, por el servicio. |
| Comercio exterior | Campos dentro de `productos` + `clasificaciones_producto`, `partidas_pais`, documentos, versiones | Tablas propias `producto_comex`, `producto_clasificacion`, `producto_partidas`, `producto_documentos`, `producto_versiones`; el motor de clasificación (unas 8 000 líneas, árbol arancelario y reglas) **se conserva** y solo cambia su entrada. |
| Lead times | `grupos_producto.dias_extra` | `familia_logistica.dias_extra`. |

## 6. Pantallas nuevas de Productos

- **Catálogo**: lista con columnas por atributo de la familia filtrada,
  variantes como fichas, filtros por familia y por cada atributo.
- **Producto**: la cabecera y la matriz de variantes de la etapa anterior,
  ahora sobre el modelo nuevo; pestañas aportadas por los módulos (Comercio
  exterior, Empaque, Etiquetas, Uso) con el mismo registro que las familias.
- **Producto nuevo**: familia → datos (los de su familia, con obligatorios)
  → variantes (ejes de su familia) → revisar.
- **Configuración**: Familias (el controlador único), Atributos, Escalas,
  Marcas.
- Se elimina *Datos maestros → Artículos* como pantalla aparte: los
  artículos se ven y editan dentro de su producto, y hay una lista de
  artículos dentro del catálogo para buscar por código.

## 7. Datos existentes: decisión pendiente

| Opción | Qué pasa | Consecuencia |
|---|---|---|
| **A. Empezar en limpio** (recomendada si todo es de demostración) | La migración borra productos, artículos, atributos y familias **y todo lo que los usa** (OC, facturas, packing lists, embarques, etiquetas, historial de clasificación); deja respaldo en un archivo antes. La demostración se regenera con el modelo nuevo. | Irreversible fuera del respaldo. Es lo más rápido y deja el código más limpio. |
| **B. Migrar** | La migración convierte familias, atributos, productos, artículos y las referencias de cada módulo al modelo nuevo, con vuelta atrás. | Conserva el historial. Cerca de una etapa más de trabajo y una migración larga que mantener. |

En ambos casos, el árbol arancelario oficial, los países, proveedores,
centros, usuarios y roles **no se tocan**.

## 8. Etapas (cada una probada y publicada)

1. **Núcleo del catálogo**: tablas nuevas, servicio, API, pruebas; prueba
   de arquitectura (nadie importa los modelos del catálogo).
2. **Familias como controlador único**: registro de secciones,
   `familia_logistica`, `familia_empaque`, `familia_etiquetado`,
   `familia_comex`; pantalla de familias.
3. **Comercio exterior como complemento**: tablas `producto_comex…` y
   motor de clasificación reconectado.
4. **Compras, facturación, packing list, recepción, seguimiento,
   transporte y reportes** por el servicio.
5. **Etiquetado y empaque** por el servicio y sus secciones de familia.
6. **Pantallas de Productos** nuevas.
7. **Retiro de lo viejo**: tablas, columnas, código y pantallas
   anteriores (migración según la opción A o B), demostración nueva,
   suites completas (SQLite, PostgreSQL, e2e), documentación.

Mientras no termine la etapa 7, el sistema sigue funcionando con lo
actual; lo viejo solo se borra al final, cuando todo ya usa lo nuevo.

## 9. Avance

| Etapa | Estado | Qué quedó |
|---|---|---|
| 1. Núcleo y servicio | En curso | `catalogo/servicio.py` (fichas de familia, producto y artículo; consultas de ids; conteos y listados por familia) y la prueba de arquitectura. Faltan las tablas nuevas (llegan con la etapa 7, opción A). |
| 2. Familias | Hecha | Un solo controlador: `catalogo/familias.py` (rutas `/grupos-producto`: familias, categorías, probar condiciones, orden, poner familia o categoría a productos y artículos). Registro de secciones (`catalogo/secciones.py`) con comercio exterior (etapa 3), logística (`familia_logistica`: días extra), etiquetado (`familia_etiquetado`: campos de sus etiquetas) y empaque (sus reglas, solo lectura). Migración 0095. Las familias y categorías del etiquetado dejaron de tener su propio alta y cambio: las pantallas del etiquetado usan el controlador del catálogo. |
| 3. Comercio exterior | Hecha | La ficha de comercio exterior salió de `productos` a su propia tabla `producto_comex` (1:1, se crea sola con el producto y se borra con él): tipo, ficha técnica, descripciones aduanera y comercial, origen y procedencia, estado de revisión, versión de la ficha, HS6 y SAC aprobados, notas. El trabajo de clasificar sigue en `clasificaciones_producto` y se lee desde la ficha (`producto.comex.sugerido`…). Sección de la familia `familia_comex`: la categoría aduanera con que empiezan las fichas de sus productos (la heredan las subfamilias; el motor la usa mientras la ficha no tenga la suya). Migración 0096 con vuelta atrás. El motor, la bandeja, la carga masiva, la demo, los documentos y las etiquetas leen la ficha por `producto.comex` o por `comex/servicio.py`. |
| 4. Compras, facturación, PL, recepción, seguimiento, transporte, reportes | Hecha | Leen por los servicios del catálogo y de comercio exterior. |
| 5. Etiquetado y empaque | Hecha | Motor de reglas, generación, trabajos, matriz y simulación con fichas del catálogo; la categoría se reconoce solo con datos del catálogo. |
| 6. Pantallas | Pendiente | La pantalla de familias ya muestra una pestaña por sección. |
| 7. Retiro de lo viejo | Pendiente | |

Las categorías se reconocen con el vocabulario del catálogo
(`catalogo.campos_condiciones`): datos del artículo, de su producto y sus
atributos. Los datos de comercio exterior no deciden la categoría.
