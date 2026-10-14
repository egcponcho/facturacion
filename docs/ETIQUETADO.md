# Módulo de etiquetado

> Reglas declarativas, campos lógicos, subfamilias, tablas, códigos compuestos y
> trabajos de etiquetado (asistente único): ver `docs/ETIQUETADO_REDISENO.md`.

Diseño, versionado, aprobación y generación de etiquetas con datos reales de
artículos, órdenes de compra y bultos. Este documento es la entrega del
módulo: arquitectura, base de datos, componentes, endpoints, reglas,
formatos, pruebas ejecutadas y limitaciones conocidas.

## 1. Arquitectura

### Principios

- **Sin duplicar datos maestros.** Una etiqueta referencia el origen de sus
  datos (artículo, línea de OC, OC, bulto) y los lee al generar; nunca copia
  la ficha del producto. El artículo solo gana una referencia a su familia de
  etiquetado. Solo la instantánea de los valores usados queda en el historial.
- **Familia de etiquetado ≠ clasificación arancelaria.** Son catálogos y
  reglas separados; asignar una familia de etiquetado no toca la partida.
- **Un solo motor de dibujo en el servidor.** El mismo diseño produce PDF,
  SVG y PNG con las mismas fuentes (Liberation Sans, Serif y Mono, incluidas
  en `backend/app/data/fuentes`, licencia SIL OFL 1.1) y las mismas medidas.
  El editor del navegador carga esas mismas fuentes; los códigos de barras y
  QR del lienzo, y la vista previa exacta, los dibuja el servidor.
- **Versiones inmutables una vez aprobadas.** Cada lote guarda la versión
  exacta y la instantánea de los valores: volver a descargar un lote produce
  el mismo archivo (se comprueba con la huella SHA-256) aunque el diseño o
  los datos cambien después.

### Capas

```
Vue (frontend/src/modulos/etiquetado)
  vistas/  EtiquetasView · EditorEtiquetaView · GenerarEtiquetasView
  editor/  estado.js (selección, deshacer, alinear, capas) · LienzoEtiqueta
           ElementoSvg · BibliotecaCampos · CapasEtiqueta · PanelElemento
           PanelEtiqueta · VistaPrevia · VersionesEtiqueta · Medida · CampoColor
  componentes/  ListaPlantillas · FamiliasEtiquetado · ArticulosFamilia
           AsignacionesEtiqueta · HistorialEtiquetas · EtiquetadoProducto
        │  JSON (/api/etiquetas/…)
FastAPI (backend/app/modulos/etiquetado)
  api.py          rutas y permisos
  familias.py     familias y familia de cada artículo
  plantillas.py   plantillas, versiones, aprobación, bitácora, imágenes
  asignaciones.py dónde se aplica cada diseño y la resolución por prioridad
  campos.py       catálogo de campos (origen tabla.columna) y valores reales
  datos.py        carga con alcance (proveedor solo ve lo suyo)
  diseno.py       esquema validado del diseño (pydantic)
  render.py       composición: texto, formato, condiciones, códigos, límites
  codigos.py      barras y QR (reportlab) · salidas.py PDF / SVG / PNG
  previa.py       vista previa y miniaturas · generacion.py plan, lotes, ZIP
        │
PostgreSQL (RLS por organización) / SQLite en pruebas
```

### Familias: grupos de artículos y artículos específicos

Un **grupo de artículos** (Datos maestros → Categorías) pertenece a una
familia de etiquetado y todos sus artículos la heredan. Un **artículo**
puede tener su familia propia, que manda sobre la del grupo. La familia
efectiva (propia o del grupo) es la que usan la prioridad de diseños, los
datos `articulo.familia*`, los datos obligatorios de la familia, los conteos
y los filtros. Desde el panel de la familia se agregan varios grupos a la
vez (búsqueda, «todos los mostrados», aviso si pasan de otra familia) y la
pestaña Artículos asigna artículos específicos en bloque.

### Generación masiva (`/etiquetas/masiva`)

Asistente en cinco pasos: qué etiquetar → elegir → diseño → revisión →
generar. Siempre con un diseño elegido por el usuario y su versión aprobada.

| Origen | Qué se genera | Archivo |
|---|---|---|
| Órdenes de compra (las de una familia; «elegir todas las del filtro») | Un lote por OC. Diseño de OC y artículo: una etiqueta por **artículo distinto** de la familia en esa OC (un artículo repetido en varias líneas va una sola vez); diseño de OC: una por OC. | ZIP con **un PDF por OC**, una etiqueta por página con las medidas del diseño (o carpetas de PNG). |
| Artículos (los de una familia; «elegir todos») | Un lote con N etiquetas por artículo. | **Un solo PDF**, una etiqueta por página (o las PNG en un ZIP). |
| Lista de empaque | Una etiqueta por unidad del **nivel de empaque** elegido (tarima, caja, inner…), con tipo, código (C3, P1), empaque que la contiene, contenido (incluido lo de los empaques interiores), pesos y medidas. | Un PDF (o PNG en ZIP). |

Si el diseño usa datos de la lista de empaque (`bulto.*`) y lo que se
etiqueta no tiene lista de empaque, se avisa: el usuario puede continuar y
esos campos salen vacíos (igual con cualquier dato que falte). Las OC con
errores se pueden omitir para generar las demás. Accesos: botón «Generación
masiva» en Etiquetas, «Generar etiquetas» en cada familia y «Etiquetas» en la
lista de empaque.

### Campos que se escriben al generar

Además del texto libre, un diseño puede declarar campos que no están en el
sistema (lote, temporada, destino…): nombre, valor por defecto y si es
obligatorio. Se usan como cualquier campo o como `{{manual.clave}}` dentro de
un texto; ambos asistentes los piden antes de generar y el valor queda en la
instantánea del lote.

## 2. Base de datos y migraciones

Migración `0070_etiquetado` (reversible; probada ida y vuelta en SQLite y
PostgreSQL con las 6 políticas RLS):

| Tabla | Para qué |
|---|---|
| `familias_etiquetado` | Familias propias (código, nombre, descripción, orden, activa) con sus campos habituales y obligatorios (`[{campo, obligatorio}]`). |
| `articulos.familia_etiquetado_id` | La familia de cada artículo (variante). |
| `plantillas_etiqueta` | Nombre único, modalidad de datos (ARTICULO, OC, OC_ARTICULO), unidad (ORDEN, LINEA, UNIDAD, BULTO, MANUAL), familia, estado, versión vigente y origen si es copia. |
| `versiones_plantilla` | Número, estado, diseño JSON validado, medidas, resumen de cambios, base, autor, envío, revisión, aprobación, comentario y control de concurrencia (`version`). |
| `asignaciones_etiqueta` | Ámbito GENERAL, FAMILIA, PRODUCTO, ARTICULO u OC (con restricción de destino), predeterminada, activa y motivo (obligatorio en la excepción de OC). |
| `generaciones_etiqueta` | Lote: OC, modalidad, unidad, formato, estado (GENERADA o PRUEBA), total, parámetros, advertencias aceptadas, archivo y SHA-256. |
| `generacion_items` | Por grupo: plantilla y versión exactas, artículo, línea, familia, referencia, cantidad, valores usados y motivo de la elección. |

Migración `0071_etiquetado_masivo` (reversible; probada en SQLite y
PostgreSQL): `grupos_articulos.familia_etiquetado_id` (con su llave de
coherencia), `generaciones_etiqueta.pl_id` y `lote`, y la unidad `ARTICULO`
en `plantillas_etiqueta`. Las variables del diseño van en el JSON de la
versión (`variables`), sin tabla propia.

Todas llevan `organizacion_id`, política RLS y llaves de coherencia
`fk_<tabla>_<col>_org` (declaradas en `app/modelos/referencias.py`). La
migración también da los permisos a los roles de fábrica. Los elementos del
diseño no tienen tabla propia: son una lista tipada dentro de la versión.

## 3. Componentes de la interfaz

- **Etiquetas** (`/etiquetas`): pestañas Diseños (tarjetas con miniatura,
  versión en uso y la que está en curso), Familias de etiquetado, Artículos
  (familia de cada variante, asignación en bloque), Dónde se aplica cada
  diseño (con el probador «¿Qué diseño se usaría?») y Etiquetas generadas.
- **Editor** (`/etiquetas/plantillas/:id`): lienzo a escala en mm con reglas,
  cuadrícula, margen seguro, zoom y desplazamiento; mover, cambiar tamaño y
  girar con guías inteligentes y ajuste a la cuadrícula (Alt lo desactiva);
  selección por marco, alinear, distribuir, igualar, agrupar, capas (orden,
  ocultar, bloquear, renombrar), copiar, pegar, duplicar, deshacer y rehacer
  (100 pasos), edición del texto sobre la etiqueta y atajos de teclado (`?`).
  Biblioteca de elementos y de campos reales por grupo con su origen y un
  ejemplo, con los habituales de la familia arriba. Paneles de propiedades
  del elemento (estilo del texto, formato del valor, qué hacer si está vacío,
  condición para mostrarlo, códigos, imágenes, formas) y de la etiqueta
  (medidas y unidad mm/cm/in, orientación, margen seguro, fondo, borde,
  resolución, cuadrícula, impresión en hoja). Vista previa exacta con datos
  de ejemplo o reales (artículo, OC, línea, bulto) y lista de problemas que
  también se marcan en el lienzo. Barra de versión con guardado (control de
  concurrencia), envío, aprobación y rechazo con comentario, versión nueva,
  volver a una versión anterior, comparación visual y bitácora.
- **Generar** (`/etiquetas/generar?oc=ID` o `?articulo=ID`): asistente en
  cuatro pasos (origen, qué etiquetar, revisión del plan, formato) con
  descarga y enlace al historial. Botón **Etiquetas** en la OC.
- **Ficha del producto**: pestaña **Etiquetas** con la familia y el diseño
  que usa cada variante, la vista previa y el acceso a generar.

## 4. Endpoints (`/api/etiquetas`, etiqueta «Etiquetado» en `/docs`)

| Método y ruta | Uso |
|---|---|
| `GET /campos?modalidad=` | Campos por grupo con origen y ejemplo. |
| `GET, POST /familias` · `PUT /familias/orden` · `PATCH, DELETE /familias/{id}` | Familias (no se borra una en uso: se desactiva). |
| `GET /articulos` (q, familia, marca_id, grupo_id, producto_id, ids) · `POST /articulos/familia` | Familia de los artículos (elegidos o todos los del filtro). |
| `GET, POST /plantillas` · `GET, PATCH /plantillas/{id}` | Diseños. |
| `POST /plantillas/{id}/duplicar · /archivar · /reactivar · /versiones` | Copia independiente, archivo, versión nueva. |
| `GET /plantillas/{id}/bitacora` | Quién hizo qué, con fecha y motivo. |
| `GET /versiones/{id}` · `PUT /versiones/{id}/diseno` | Leer y guardar un borrador (con `version`). |
| `POST /versiones/{id}/{enviar·retirar·aprobar·rechazar·archivar·usar}` | Flujo de aprobación. |
| `GET /versiones/{id}/miniatura.svg` · `POST /vista-previa` | Miniatura y vista previa exacta con problemas. |
| `GET, POST /asignaciones` · `PATCH, DELETE /asignaciones/{id}` · `GET /resolver` | Dónde se aplica y qué diseño se usaría. |
| `POST /imagenes` · `GET /imagenes/{id}` · `GET /fuentes/{archivo}` | Logos del diseño y fuentes del editor. |
| `GET /oc/{id}` · `POST /plan` | Resumen de la OC y plan de generación. |
| `GET /grupos-articulos` · `POST /grupos-articulos/familia` | Grupos de artículos con su familia; asignar varios a la vez. |
| `GET /masivo/ordenes` (familia_id, q, estado, solo_ids) | OC con artículos de la familia: líneas, artículos distintos, bultos y lotes ya generados. |
| `GET /masivo/packing` · `GET /masivo/packing/{id}` | Listas de empaque y sus niveles de empaque con cuántas unidades tiene cada uno. |
| `POST /masivo/plan` · `POST /masivo` · `GET /masivo/{lote}/archivo?formato=` | Plan, generación y descarga de la generación masiva. |
| `POST, GET /generaciones` · `GET /generaciones/{id}` · `GET /generaciones/{id}/archivo?formato=` | Generar, historial y descarga reproducible (encabezado `X-Identico`). |

## 5. Reglas de prioridad

Para una modalidad y un artículo (o una OC):

1. Excepción asignada a la OC (con motivo obligatorio).
2. Asignada al artículo (variante).
3. Asignada al producto (estilo: todas sus variantes).
4. De la familia de etiquetado del artículo.
5. General de la organización.

Solo cuentan plantillas activas con una versión aprobada vigente y de la
misma modalidad. En el primer nivel con candidatas: una → se usa; varias →
la marcada como predeterminada; si aun así hay empate, el usuario elige en la
revisión. Siempre se muestran el diseño, la familia, la versión y el motivo
(«Asignado al artículo …», «Diseño de la familia …»…). Se advierte si el
artículo no tiene familia o si el diseño es de otra familia, y la familia
puede exigir datos obligatorios (error si faltan).

## 6. Versiones y aprobación

1. Una plantilla nace con la versión 1 en borrador.
2. Un borrador (o una versión rechazada) se guarda cuantas veces haga falta;
   el servidor rechaza un guardado sobre una versión que otra persona cambió.
3. Solo se envía un borrador sin errores; mientras espera aprobación no se
   edita (se puede retirar).
4. Aprobar o rechazar requiere `etiquetas.aprobar`; el rechazo lleva
   comentario. Con la regla `ETIQUETAS_CUATRO_OJOS` quien creó o envió la
   versión no la aprueba.
5. Una versión aprobada no cambia nunca: los cambios van en una versión nueva
   basada en ella, que no reemplaza a la vigente hasta aprobarse.
6. Hay a lo sumo una versión abierta por plantilla.
7. Una versión aprobada anterior (aunque esté archivada) puede volver a
   usarse sin borrar las demás; la vigente no se archiva.
8. Cada acción (crear, guardar, enviar, retirar, aprobar, rechazar, archivar,
   usar, nueva versión, editar datos, duplicar) queda en la bitácora con su
   autor, fecha y motivo.
9. Lo ya generado no cambia: cada lote guarda la versión y los valores.

## 7. Formatos

- **PDF** (reportlab, sin escalado de impresión, determinista): una etiqueta
  por página o varias por hoja con columnas, filas, márgenes y separación.
- **PNG** (Pillow) a la resolución del diseño (203, 300 o 600 dpi); varias
  etiquetas van en un ZIP.
- **SVG** con el texto convertido en trazos (fontTools): se ve igual sin las
  fuentes instaladas.
- **ZIP** con PDF, PNG y `lote.json` (datos del lote).
- **Códigos**: Code 128, Code 39, EAN-13, EAN-8, UPC-A y QR (con corrección
  L/M/Q/H), con validación del valor y del dígito verificador GS1, zona en
  blanco, ancho mínimo de módulo y contraste. No se inventan identificadores:
  el código usa el dato real del campo.
- **ZPL no se implementó**: no hay impresora Zebra para comprobar que lo
  impreso coincida con el PDF, y la regla del proyecto es no declarar algo
  funcional sin probarlo. Las etiquetadoras térmicas imprimen el PDF a 203 o
  300 dpi con la opción «una por página».

## 8. Pruebas ejecutadas

Servidor (`pytest`): **615 pasan, 3 omitidas** en la suite completa; las del
módulo son 41 en cinco archivos más las de traducción:

- `test_etiquetado_familias.py` (4): alta, cambio, orden y desactivación;
  asignación a artículos (elegidos, filtro, `ids`) sin tocar la
  clasificación; permisos y proveedor; campos con origen por modalidad.
- `test_etiquetado_familias.py` también prueba la familia por grupos de
  artículos (varios a la vez, el artículo con familia propia la conserva,
  conteos, prioridad y que una familia con grupos no se borra).
- `test_etiquetado_masivo.py` (5): OC de una familia con un artículo
  repetido en dos líneas (una sola etiqueta), ZIP con un PDF por OC y página
  del tamaño del diseño, PNG; artículos de una familia en un solo PDF y en
  PNG; lista de empaque con tarima y cajas (contenido de la tarima, código
  del contenedor, numeración por nivel); aviso de datos de empaque vacíos que
  pide confirmar; campos que se escriben al generar (obligatorio, valor por
  defecto, valor en el PDF).
- `test_etiquetado_render.py` (13): validación del diseño; PDF, PNG y SVG
  con medidas, colores y fuentes reales; **lectura con zxing-cpp** de
  Code 128, EAN-13, UPC-A, EAN-8, Code 39 y QR; códigos inválidos; texto
  largo, vacío, condiciones y límites; formatos de número y fecha; hoja de
  varias etiquetas y giro.
- `test_etiquetado_plantillas.py` (7): ciclo completo de versiones con
  concurrencia, permisos, rechazo con comentario, volver a una versión y
  bitácora (también por la API); diseño con errores; cuatro ojos;
  duplicación independiente; prioridad en los cinco niveles y desempate;
  vista previa con datos de ejemplo y reales; imágenes.
- `test_etiquetado_generacion.py` (11): sin plantilla aprobada no se genera;
  por línea, unidad y cantidad manual; ZIP con PNG y SVG y código legible;
  familia con dato obligatorio; advertencias y duplicados que piden
  confirmar; unidad no contable; **reproducción de un lote histórico**
  idéntica tras cambiar versión y datos; prueba con versión sin aprobar; por
  bulto desde las listas de empaque; **lote de 2000 etiquetas** y tope;
  alcance del proveedor.

Interfaz: ESLint sin observaciones; `npm run build` correcto; recorrido
`npm run e2e` con administrador, interno y dos proveedores a 1440 px y
390 px, incluidas las cinco pestañas de etiquetas, el asistente y el editor,
**sin errores**. Además se probaron en el navegador, con capturas: mover,
cambiar tamaño, girar, deshacer, selección por marco, agregar campos, capas,
guardar, enviar, aprobar con comentario, versión nueva, comparar versiones,
bitácora y la generación desde una OC con descarga del PDF.

## 9. Limitaciones conocidas

- **Plantillas por organización.** Cada empresa diseña las suyas (RLS); no
  hay plantillas del sistema compartidas entre organizaciones.
- **Lotes** de hasta `ETIQUETAS_MAXIMO_LOTE` (5000) etiquetas por pedido
  directo; los trabajos de etiquetado generan en segundo plano desde
  `ETIQUETAS_ASINCRONO_DESDE` (ver ETIQUETADO_REDISENO.md §10.5).
- **Empaques con contenido mixto**: la etiqueta de OC y artículo toma los
  datos del primer artículo del empaque (y lo avisa); el contenido completo
  está en las tablas `bulto.lineas` y `bulto.componentes`.
- **Generación masiva** (API anterior): hasta 200 OC y 2000 artículos por
  vez, síncrona; la pantalla usa ahora el asistente de trabajos.
- **Idioma**: un diseño tiene un solo juego de textos fijos; no hay
  plantillas con variantes por idioma.
- **Editor**: en el lienzo el texto se mide con las mismas fuentes que el
  servidor, pero la referencia es la vista previa del servidor. Quien no
  diseña ve en el lienzo el dibujo del servidor. Una línea girada se ajusta
  desde el panel, no con sus extremos.
- **Formatos**: sin ZPL ni EPL (ver §7); sin GS1-128 con identificadores de
  aplicación ni DataMatrix.
- **Imágenes**: PNG, JPEG o WebP de hasta 2 MB y 4000 px.
- **Familias**: los campos obligatorios se comprueban con los datos del
  artículo y del producto; no hay reglas condicionales entre campos.

## Permisos

`etiquetas.ver`, `etiquetas.generar` (todos, incluido el proveedor sobre sus
propias OC), `etiquetas.disenar`, `etiquetas.asignar`, `etiquetas.familias`
(equipo interno) y `etiquetas.aprobar` (administración). El módulo se puede
apagar como los demás (Configuración → Empresa → Módulos).
