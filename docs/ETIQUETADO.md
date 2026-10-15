# Módulo de etiquetado

Diseño, versionado, aprobación y generación de etiquetas con datos reales de
artículos, órdenes de compra, listas de empaque y bultos. Este documento es
el manual del módulo tal como está hoy: conceptos, base de datos, pantallas,
endpoints, cómo se elige el diseño, versiones, formatos, pruebas ejecutadas y
limitaciones.

La propuesta que llevó a este modelo y su registro de errores corregidos está
en `docs/ETIQUETADO_EVALUACION.md` (revisión 2, §7 y §17).
`docs/ETIQUETADO_REDISENO.md` describe la etapa anterior (reglas con
prioridad numérica) y queda como historial.

## 1. Conceptos

| Concepto | Qué es |
|---|---|
| **Tipo de etiqueta** | Lo que la empresa imprime: colgante, sticker de precio, etiqueta de caja, hoja de contenido… Cada uno dice **qué se etiqueta** (sujeto: `ARTICULO`, `BULTO` o `DOCUMENTO`), **cuántas salen** (`POR_UNIDAD`, `POR_LINEA`, `POR_ARTICULO`, `POR_BULTO`, `POR_DOCUMENTO` o `MANUAL`) y si es **obligatoria** (todo registro debe tener diseño para imprimir). Cada empresa crea los suyos. |
| **Diseño** | Una plantilla de un tipo, con versiones que se aprueban. El editor ofrece solo los datos del sujeto de su tipo. |
| **Familia de etiquetado** | Agrupa artículos para darles el mismo diseño. Se asigna al **producto** (estilo-color; la heredan sus tallas), al **grupo de artículos** o a una **talla**. Puede tener subfamilias, que heredan sus diseños y campos obligatorios. |
| **Uso de diseño** | Dice qué diseño lleva un lugar. Un lugar es una **celda**: tipo × nivel × destino. Los niveles son toda la empresa (`GENERAL`), `FAMILIA`, `PRODUCTO`, una talla (`SKU`) y, para bultos, el `TIPO_EMPAQUE`. Cada celda tiene a lo sumo un **diseño normal** y las **excepciones** que haga falta. |
| **Excepción** | Un diseño distinto en una celda cuando se cumple algo: la OC es X (`OC`), el centro de destino (`CENTRO_DESTINO`), el país de destino (`PAIS_DESTINO`), la sociedad compradora (`SOCIEDAD`), el proveedor (`PROVEEDOR`) o condiciones sobre los datos (`CONDICION`), con vigencia opcional y motivo. |
| **Trabajo de etiquetado** | El único camino para generar: se crea desde una OC, una lista de empaque, unos artículos o una familia; se revisa, se corrige y se genera en ejecuciones. |

**El artículo es el sujeto; el origen solo aporta contexto.** Un mismo SKU
recibe el mismo diseño venga de una OC, de una lista de empaque o de una
selección de artículos, salvo una excepción explícita.

### Cómo se elige el diseño (escalera)

Para un registro (un artículo, un bulto o un documento) y un tipo:

1. Si hay una **excepción de la OC** del registro que aplica hoy, gana.
2. Si no, se recorre de lo más específico a lo general: **talla → producto →
   familia** (cada subfamilia antes que sus familias padre) → **tipo de
   empaque** (bultos) → **toda la empresa**.
3. En cada celda se miran sus excepciones en orden **centro, país,
   sociedad, proveedor, condiciones**; la primera que se cumple y está
   vigente gana. Si ninguna se cumple, se usa el **diseño normal** de la
   celda.
4. Una celda que solo tiene excepciones que no se cumplen no detiene la
   búsqueda: sigue la de arriba.
5. Si nada aplica: el tipo obligatorio da **error** («Sin diseño
   (obligatoria)»); el opcional queda **omitido**.

Siempre se muestra por qué se eligió (`porque`: clase, nivel, excepción) y
desde qué fila se hereda. Solo cuentan diseños activos con versión
aprobada; en **modo prueba**, quien tiene `etiquetas.disenar` también usa la
última versión sin aprobar (que no esté rechazada ni archivada).

Dos usos que podrían aplicar al mismo registro con el mismo peso no se pueden
guardar (`celda_ocupada`, `excepcion_repetida`); la comprobación bloquea las
filas de la celda para que dos personas no la crucen a la vez. La celda se
guarda entera con su **firma**: si alguien la cambió mientras estaba abierta,
el servidor responde 409 y la pantalla la vuelve a cargar.

## 2. Base de datos y migraciones

Migración **`0076_etiquetado_tipos_y_usos`** (reversible; probada ida y
vuelta en SQLite y PostgreSQL):

| Tabla / columna | Para qué |
|---|---|
| `tipos_etiqueta` | Tipos de la empresa: código único, nombre, descripción, sujeto, cantidad, obligatoria, orden, activo y `version` (concurrencia). |
| `plantillas_etiqueta.tipo_etiqueta_id` | Reemplaza `modalidad`, `unidad` y `familia_id` del diseño. |
| `usos_diseno` | Tipo, diseño, nivel y destino (`familia_id`, `producto_id`, `articulo_id`, `tipo_empaque_id`), `celda`, `contexto_tipo`, `contexto_valores`, `oc_id`, `condiciones`, vigencia, motivo, autor, baja lógica (`eliminado_en`) y `version`. Reemplaza `asignaciones_etiqueta`. |
| `productos.familia_etiquetado_id` | Familia del producto (la heredan sus tallas sin familia propia). |
| `trabajo_etiqueta_registros.tipo_etiqueta_id`, `uso_id` | Cada registro del trabajo es de un tipo y recuerda el uso que lo decidió (en lugar de `regla_id`). |
| `generacion_items.tipo_etiqueta_id`, `pl_id`, `grupo_cajas_id`, `bulto_indice` | El tipo y la identidad del bulto: «ya impreso» ya no se cruza por el texto de la clave. |
| `campos_etiqueta.sujetos` | Los campos propios de la empresa por sujeto (antes `modalidades`). |
| Permiso `etiquetas.asignar` → `etiquetas.configurar` | Mismo alcance, nombre nuevo. |

**Conversión de los datos existentes (opción A, automática con informe):**
cada combinación (modalidad, unidad) de los diseños se convierte en un tipo;
cada regla en un uso (GENERAL, FAMILIA, PRODUCTO, ARTICULO → su nivel; OC →
excepción de esa OC; reglas con condiciones o vigencia → excepción por
condición). Si en una celda quedaban varios diseños normales sigue el de mayor
prioridad (luego el predeterminado, luego el más antiguo) y los demás quedan
dados de baja. Cada conversión queda en el historial (entidad `uso_diseno`,
acción `migrar`) con la regla original y qué pasó con ella. El downgrade
vuelve a crear `asignaciones_etiqueta` (con sus restricciones e índices de
0075) con una regla por uso vigente; los tipos, los usos dados de baja y la
familia de los productos se pierden.

Siguen de antes: `familias_etiquetado` (con `padre_id`), `versiones_plantilla`,
`generaciones_etiqueta`, `generacion_items`, `trabajos_etiqueta` y
`trabajo_etiqueta_registros` (0070–0075). Todas llevan `organizacion_id`,
política RLS y llaves de coherencia `fk_<tabla>_<col>_org`.

## 3. Pantallas

Tres secciones con la misma cabecera (**Imprimir · Diseños · Configuración**):

- **Imprimir** (`/etiquetas`): trabajos de etiquetado (abiertos y
  generados) y «Nuevo trabajo». Si la empresa no tiene tipos, el asistente
  de **primer uso** pregunta qué etiquetas imprime (sugeridos u otro),
  cómo agrupa sus artículos (por grupo de artículos → una familia por grupo,
  por producto, o una sola etiqueta para todo) y crea los tipos, las
  familias y un diseño en blanco de cada tipo para toda la empresa.
- **Diseños** (`/etiquetas/disenos`): diseños agrupados por tipo, con
  miniatura, versión, «Se usa en: …» y crear (tipo, tamaño del catálogo, en
  blanco o copia de otro). Archivar avisa qué lugares dejan de usarlo.
  El editor está en `/etiquetas/disenos/:id`.
- **Configuración** (`/etiquetas/configuracion`):
  - **Qué diseño va en qué**: la **matriz** (filas: toda la empresa,
    familias y subfamilias, productos con diseño propio; columnas: tipos)
    con cobertura («N de M artículos tienen todas sus etiquetas
    obligatorias»). Cada celda muestra el diseño propio o «hereda X» y sus
    excepciones; al abrirla se edita en una ventana: diseño normal,
    excepciones escritas como frase («Si el país de destino es Panamá →
    usar Colgante bilingüe porque…»), **qué cambia al guardar** (simulación
    sin guardar: cuántos artículos cambian, cuáles quedan sin diseño) y
    «aplicar también a» otras celdas de la columna.
  - **Tipos de etiqueta** (con las medidas de etiqueta de la empresa).
  - **Familias y artículos**: árbol de familias y asignación en bloque de
    grupos, productos y tallas; «usar mis grupos como familias».
  - **Campos**: **nombres de los campos** (el nombre que usa la empresa y
    los que se ocultan al diseñar; la clave no cambia), campos lógicos
    propios y **Historial**.
- **Ficha del producto**, pestaña **Etiquetas**: la familia del producto,
  qué diseño usa cada tipo (y por qué), «usar otro diseño para este
  producto» (todo el producto o algunas tallas) y «volver a heredar».
- **OC y lista de empaque**, botón **Etiquetas**: un panel con las etiquetas
  de cada tipo, cuántas salen y qué falta; «Diseño especial para esta OC»
  (crea la excepción con motivo), **Imprimir** e **Imprimir prueba**.
- **Asistente de trabajo** (`/etiquetas/trabajos/:id`), tres pasos:
  1. **Qué**: origen, selección (OC y sus líneas, lista de empaque y qué
     bultos, artículos, familia), tipos a imprimir con su conteo y modo
     Real/Prueba.
  2. **Revisar**: problemas agrupados por causa con su arreglo («Elegir
     diseño» lo usa solo en este trabajo o lo guarda como regla para los
     siguientes; «Completar el dato» escribe en el maestro del artículo el
     UPC, SKU del proveedor, peso o unidad que falta, un valor por
     artículo), datos que pide el diseño, una pestaña por tipo con
     cantidades editables y vista previa con anterior/siguiente.
  3. **Generar**: archivo de cada ejecución, contenido y reparto del ZIP,
     ejecuciones, marcar como impresas, **reimprimir** (copias idénticas de
     todo o de grupos y rangos, con motivo) y **anular** (con motivo: sus
     registros vuelven a pendientes) y «Nuevo trabajo, igual». Si lo que se
     va a imprimir cambió desde la revisión (un SKU, el contenido de una
     caja, el diseño), generar avisa con cada cambio (409 `datos_cambiaron`)
     antes de imprimir: revisar de nuevo o generar con los datos nuevos.

  Desde la OC: `?origen=OC&oc=…&tipos=…&prueba=1` crea el trabajo y entra
  directo a Revisar. Las rutas anteriores (`/etiquetas?vista=…`,
  `/etiquetas/plantillas/:id`, `/etiquetas/generar`, `/etiquetas/masiva`)
  llevan a su lugar nuevo.

## 4. Endpoints (`/api/etiquetas`, etiqueta «Etiquetado» en `/docs`)

| Método y ruta | Uso |
|---|---|
| `GET /catalogos` · `PUT /tamanos` | Sujetos con sus cantidades, niveles por sujeto, contextos y su orden, operadores de condición, simbologías, medidas de etiqueta, tipos sugeridos y orígenes; medidas propias de la empresa. |
| `GET, POST /tipos` · `PATCH /tipos/{id}` · `POST /tipos/sugeridos` | Tipos de etiqueta (`todos=true` suma los inactivos); el sujeto no cambia si el tipo ya tiene diseños. |
| `GET /matriz` · `GET /celda` | La matriz con cobertura y una celda con su firma, lo que hereda y cuántos artículos tiene. |
| `PUT /usos/celda` · `POST /usos/simular` · `POST /usos/lote` | Guardar la celda entera (con `firma`), «qué cambia» sin guardar, la misma excepción en varias celdas. |
| `GET, POST /usos` · `PATCH /usos/{id}` · `POST /usos/{id}/baja` · `GET /usos/{id}/historial` · `GET /usos/valores?contexto=` | Usos sueltos (desde el producto, la OC o el asistente), baja lógica con motivo, historial y valores para las excepciones. |
| `GET /resolver` · `GET /resumen` | Qué diseño lleva un artículo, bulto o documento y por qué; resumen de etiquetas de una OC o lista de empaque. |
| `GET, POST /familias` · `PUT /familias/orden` · `PATCH, DELETE /familias/{id}` · `POST /familias/desde-grupos` | Familias (no se borra una en uso: se desactiva). |
| `GET /articulos` · `POST /articulos/familia` · `GET /productos` · `GET /productos/{id}` · `POST /productos/familia` · `GET /grupos-articulos` · `POST /grupos-articulos/familia` | Familia de tallas, productos y grupos (en bloque); pestaña Etiquetas del producto. |
| `GET /campos?sujeto=` · `GET, POST /campos-logicos` · `PATCH, DELETE /campos-logicos/{id}` | Campos por grupo con origen y ejemplo; campos propios. |
| `GET, POST /plantillas` · `GET, PATCH /plantillas/{id}` · `POST /plantillas/{id}/duplicar · archivar · reactivar · versiones` · `GET /plantillas/{id}/bitacora` | Diseños. |
| `GET /versiones/{id}` · `PUT /versiones/{id}/diseno` · `POST /versiones/{id}/{enviar·retirar·aprobar·rechazar·archivar·usar}` · `GET /versiones/{id}/miniatura.svg` · `POST /vista-previa` | Versiones, aprobación y vista previa exacta. |
| `GET, POST /trabajos` · `GET, PATCH /trabajos/{id}` · `POST /trabajos/{id}/validar · generar · cancelar` · `GET /trabajos/{id}/estado · archivo` · `GET /trabajos/{id}/registros/{r}/vista-previa` | Trabajos de etiquetado (el único camino de generación). |
| `GET /generaciones` · `GET /generaciones/{id}` · `GET /generaciones/{id}/archivo` · `POST /generaciones/{id}/impresion` | Historial de lo generado, descarga reproducible (`X-Identico`) y marca de impresión. |
| `POST /generaciones/{id}/reimprimir` · `POST /generaciones/{id}/anular` | Reimpresión con motivo (todo o `seleccion` [{item_id, desde, hasta}]) y anulación con motivo. |
| `GET /usos/migracion` | Cómo quedaron las reglas anteriores al convertirse en usos (migración 0076). |
| `GET /ordenes` · `GET /packing` · `GET /packing/{id}` | Listados para elegir en el asistente. |
| `POST /imagenes` · `GET /imagenes/{id}` · `GET /fuentes/{archivo}` | Logos del diseño y fuentes del editor. |

Se retiraron: `/asignaciones`, `/plan`, `/oc/{id}`, `POST /generaciones`,
`/masivo*` y el generador directo; todo pasa por los trabajos.

## 5. Generación

- Claves de registro estables: `oc{id}:t{tipo}-p{posición}` (artículos de
  una OC), `pl{id}:t{tipo}-pl{línea}-g{grupo}-u{bulto}` (bultos) y
  equivalentes para documentos. Cantidades y diseños elegidos en el trabajo
  se guardan por esa clave.
- Desde **artículos sueltos**, la cantidad escrita cuenta solo en los tipos
  `POR_UNIDAD` y `MANUAL`; `POR_LINEA` y `POR_ARTICULO` dan una.
- Una lista de empaque en **borrador** solo da etiquetas de prueba
  (regla `ETIQUETAS_PL_SIN_FINALIZAR` para permitir reales).
- Un bulto con varios artículos deja vacíos los campos del artículo y lo
  avisa: el contenido completo está en `bulto.lineas` y `bulto.componentes`;
  `bulto.mixto` y `bulto.parcial` son sí/no reales.
- Empaques interiores que no se reparten en partes iguales: cada unidad se
  calcula por separado, sin fracciones. `ETIQUETAS_VALIDAR_EMPAQUE` decide si
  se avisa cuando la lista de empaque difiere del casepack o inner de la OC.
- La fecha de la etiqueta es la de la empresa (zona horaria de la
  organización), no la del servidor.
- Límites por regla de empresa: `ETIQUETAS_MAXIMO_TRABAJO`,
  `ETIQUETAS_ASINCRONO_DESDE` (en segundo plano con arriendo y latido),
  `ETIQUETAS_GENERACION_PARCIAL` y `ETIQUETAS_CUATRO_OJOS`.
- Generar sin nada pendiente: 409 `ya_generado` si algo ya se generó; si
  no, 422 «No hay nada que generar en este trabajo de etiquetado».

## 6. Versiones y aprobación

1. Un diseño nace con la versión 1 en borrador.
2. Un borrador (o una versión rechazada) se guarda cuantas veces haga falta;
   el servidor rechaza un guardado sobre una versión que otra persona cambió.
3. Solo se envía un borrador sin errores; mientras espera aprobación no se
   edita (se puede retirar).
4. Aprobar o rechazar requiere `etiquetas.aprobar`; el rechazo lleva
   comentario. Con `ETIQUETAS_CUATRO_OJOS` quien creó o envió la versión no
   la aprueba.
5. Una versión aprobada no cambia nunca: los cambios van en una versión nueva
   que no reemplaza a la vigente hasta aprobarse.
6. Hay a lo sumo una versión abierta por diseño.
7. Una versión aprobada anterior puede volver a usarse.
8. Cada acción queda en la bitácora con autor, fecha y motivo.
9. Lo ya generado no cambia: cada lote guarda la versión y los valores.
10. Un diseño en uso solo cambia de tipo a otro del mismo sujeto.

## 7. Formatos

- **PDF** (reportlab, determinista): una etiqueta por página o varias por
  hoja; un único PDF no mezcla medidas distintas.
- **PNG** (Pillow) a la resolución del diseño; **SVG** con el texto en
  trazos. **ZIP** del trabajo: un PDF por diseño y versión, por carpeta,
  uno solo, o un archivo por etiqueta (PNG y SVG siempre uno por archivo),
  con carpetas (hasta 3 niveles), patrón de nombres y texto para «sin
  valor» configurables.
- **Códigos**: Code 128, Code 39, EAN-13, EAN-8, UPC-A, ITF-14, GS1-128 (con
  identificadores de aplicación), SSCC (dígito verificador), QR,
  DataMatrix, GS1 DataMatrix y PDF417. El catálogo lo sirve el servidor.
- **Recuadro que se ajusta al contenido** (por elemento): medidas fijas, o
  el recuadro sigue al texto con su tamaño de letra (ancho, alto con líneas,
  o ambos) desde su alineación y hasta el área segura; la tabla crece con
  sus filas y la imagen toma su proporción. Se recalcula con los datos de
  cada etiqueta y el editor lo muestra en vivo. **Debajo de**: un elemento
  sigue el borde inferior de otro (más una separación); si el de arriba crece,
  baja; si no se imprime, sube a su lugar. Si con los datos reales dos
  elementos que se leen se tapan, la vista previa y el trabajo avisan
  (`elementos_encimados`), salvo los marcados «Puede ir encima de otros».
- **Escrituras**: latín, griego y cirílico con Liberation; chino, árabe
  (de derecha a izquierda, letras unidas) y devanagari con Noto y forma
  HarfBuzz (`escritura.py`). En el PDF esas líneas van como contornos.
- **Regional por diseño**: idioma de meses y sí/no (en, es, pt, fr, zh, ar, hi),
  separador de miles y decimal, y patrón de fecha libre (`dd`, `d`, `mm`,
  `mmm`, `mmmm`, `aa`, `aaaa`).
- **Marca de prueba** traducida según el idioma del diseño.
- **ZPL no se implementó** (no hay impresora para comprobarlo).

## 8. Datos de demostración

`app/instalacion/demo_etiquetado.py`, creado con los mismos servicios que la
pantalla: tipos Colgante (obligatorio), Sticker de precio, Etiqueta de caja
(obligatoria) y Hoja de contenido de OC; familias Calzado (con la subfamilia
Calzado técnico) y Ropa, puestas a un grupo de artículos, a un producto y a
un producto concreto (la mochila queda sin familia y con diseño propio);
diseños aprobados de cada tipo, uno con una versión nueva esperando
aprobación; usos generales, por familia y por producto, una excepción por
país de destino (Panamá → colgante bilingüe), una de OC (franja de pedido
especial) y un uso dado de baja con su historial; y cinco trabajos de
ejemplo (desde una OC ya generado, artículos sueltos en prueba, una lista de
empaque validada, una familia en borrador y uno con un dato pendiente).

## 9. Pruebas ejecutadas

Ver la sección de entrega en `docs/ETIQUETADO_EVALUACION.md` (§17) con los
comandos y resultados reales de esta versión. Archivos del módulo:
`test_etiquetado_reglas.py` (escalera, celda con firma, simulación, lote,
matriz, tipos, patrones), `_generacion`, `_trabajos` (incluye la migración
0075 → 0076 → 0075 → 0076 con datos), `_contenido`, `_durable`, `_familias`,
`_integracion`, `_origenes`, `_plantillas` y `_render`; en el navegador
`frontend/e2e/etiquetado.mjs` y el recorrido general `frontend/e2e/recorrido.mjs`.

## 10. Limitaciones conocidas

La lista completa de deficiencias y sugerencias, con prioridad, está en
`docs/ETIQUETADO_EVALUACION.md` §18.

- **Escrituras**: sin coreano, hebreo ni tailandés; el orden bidireccional
  es básico (sin espejar paréntesis); no se suben fuentes propias.
- **Recuadros automáticos**: «Debajo de» mueve un elemento en vertical; no
  hay flujo horizontal ni aviso de solapamiento.
- **Completar**: solo cuatro datos del artículo; lo demás se corrige donde se
  origina.
- **Escalera fija**: el orden de niveles y de excepciones no se configura
  por empresa (decisión D3).
- **Imágenes**: PNG, JPEG o WebP de hasta 2 MB y 4000 px.

## Permisos

`etiquetas.ver`, `etiquetas.generar` (todos, incluido el proveedor sobre sus
propias OC), `etiquetas.disenar`, `etiquetas.configurar` (tipos, usos,
familias, medidas), `etiquetas.familias` y `etiquetas.aprobar`. El módulo se
puede apagar como los demás (Configuración → Empresa → Módulos).
