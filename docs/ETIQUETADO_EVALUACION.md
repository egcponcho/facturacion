# Etiquetado: evaluación completa y propuesta de sistema genérico

> **Para quién es este documento.** Está escrito para que otra IA (o una
> persona) lo implemente sin tener que volver a investigar. Cada hallazgo
> trae dónde está (`archivo:línea`), cómo reproducirlo, qué impacto tiene,
> cómo corregirlo y cómo comprobar que quedó bien. Las propuestas de
> rediseño traen modelo de datos, algoritmo, API, pantallas, migración y
> pruebas.
>
> **Estado del código evaluado:** rama `claude/bold-lovelace-iwx2wa`
> (= `main` + el commit 7a1422b de vista previa y formularios en ventanas).
> Complementa `docs/ETIQUETADO.md` (manual del módulo) y
> `docs/ETIQUETADO_REDISENO.md` (rediseño anterior ya implementado).

---

## 0. Reglas de trabajo para quien implemente

1. **No fusionar ramas ni borrar archivos sin autorización expresa** del dueño.
2. **Si una corrección cambia la arquitectura o migra datos existentes,
   explicar antes las alternativas y sus consecuencias** y esperar la decisión
   (la sección 15 lista las decisiones pendientes).
3. **No declarar que una prueba pasó si no se ejecutó.** Reportar el comando
   y el resultado real.
4. Cada fase de la hoja de ruta (sección 14) se entrega por separado, con sus
   pruebas, y sin romper los trabajos de etiquetado ya existentes.
5. Lo que hoy funciona y está probado (editor, versiones con aprobación,
   trabajos durables, caché/ETag/SSE) **no se reescribe**: se adapta.
6. Mantener el estilo del repositorio: nombres en español, mensajes de error
   para el usuario en inglés (como el resto del backend) hasta que exista la
   traducción del lado del servidor, comentarios breves.

---

## 1. Resumen ejecutivo

El módulo es **potente pero difícil de usar y rígido**. El motor de dibujo,
el editor, las versiones con aprobación y los trabajos durables están bien
resueltos. Los problemas están en tres capas:

| Capa | Diagnóstico | Gravedad |
|---|---|---|
| **Reglas (qué diseño va a qué registro)** | Demasiados conceptos que se cruzan (modalidad × unidad × ámbito × prioridad numérica × contexto × condiciones × predeterminada × vigencia). El mismo artículo necesita reglas distintas según venga de una OC o de una lista de artículos. Una regla no se puede corregir (diseño y destino fijos). Una sola etiqueta por registro. | Alta (es lo que el usuario percibe como "complejo y fijo") |
| **Datos y errores reales** | 12 errores confirmados: claves de bulto que chocan entre listas de empaque, versiones rechazadas usadas en prueba, fecha del servidor en vez de la de la empresa, cantidades fraccionarias, listas de empaque en borrador, etiqueta "Sin familia" falsa, etc. | Alta/Media |
| **Valores fijos en el código** | Catálogo de campos, columnas de tablas, prioridades, tamaños, simbologías, textos impresos en inglés, formatos de número y fecha, nombres de carpetas, fuentes, ejemplos de una marca concreta. | Media (impide que sea genérico) |
| **Experiencia de uso** | 7 pestañas, asistente de 8 pasos, claves técnicas a la vista, borrados sin confirmación, botón duplicado. | Media |
| **Rendimiento** | El plan completo se recalcula 2–3 veces por generación; consultas por registro; vista previa recalcula todo. | Media |

**Propuesta central (sección 7):** el **artículo es el sujeto** de la
etiqueta; la OC, la lista de empaque o la selección manual solo **aportan
contexto** (datos adicionales y, si la empresa lo quiere, excepciones). Se
reemplazan `modalidad` + `unidad` por **tipos de etiqueta definidos por la
empresa**, la prioridad numérica por una **escalera de especificidad fija y
legible**, y se permiten **varias etiquetas por registro** (una por tipo).

---

## 2. Mapa del módulo (estado actual)

### 2.1 Backend — `backend/app/modulos/etiquetado/`

| Archivo | Responsabilidad | Observaciones |
|---|---|---|
| `api.py` | 60 rutas bajo `/api/etiquetas` | 3 rutas sin uso en la interfaz (ver 2.4) |
| `reglas.py` | Motor de reglas: `Motor`, `PRIORIDAD`, `MODALIDADES_DE`, `conflictos()` | Núcleo de la complejidad (sección 6) |
| `asignaciones.py` | CRUD de reglas, `probar`, `resolver` | No permite cambiar diseño ni destino al editar |
| `generacion.py` | `_grupos`, `plan()`, `generar()`, `_previas`, `resumen_oc`, `_version_de` | Errores E1, E2, rendimiento R1–R3 |
| `trabajos.py` | Trabajos durables (asistente): crear, validar, vista previa, generar, ZIP | Errores E1, E6, E9, E10; valores fijos F10, F11 |
| `masivo.py` | Generación masiva (tercer camino) | Duplica lógica de `trabajos.py`; límite distinto (E8) |
| `campos.py` | Catálogo fijo de campos, colecciones (tablas), valores de OC y bultos | Valores fijos F1–F3; errores E4, E5; rendimiento R2 |
| `campos_logicos.py` | Campos lógicos con varias fuentes y política de conflicto | Bien planteado; cuarta forma de "obligatorio" |
| `datos.py` | Carga OC/línea/artículo y arma los valores | Error E3 (fecha) |
| `datos_campos.py` | Ejemplos para la vista previa del editor | Valor fijo F4 (datos de una marca) |
| `empaque_etiquetas.py` | Avisos de casepack e inner | Valor fijo F9 (siempre activo) |
| `diseno.py` | Esquema Pydantic del diseño | Tres formas de "obligatorio" (sección 6.5) |
| `render.py` | Dibujo común (PDF/SVG/PNG) | Valores fijos F5, F6 (meses en inglés, formato numérico) |
| `salidas.py` | PDF, SVG, PNG | `png()` acepta dpi; `trabajos.archivo` no lo pasa (E10) |
| `codigos.py` | Códigos de barras | Faltan GS1-128, ITF-14, SSCC, DataMatrix, PDF417 (F7) |
| `fuentes.py` | Fuentes incrustadas | Solo Liberation: sin chino, hindi ni árabe (F8) |
| `plantillas.py` | Diseños, versiones, aprobación (cuatro ojos), imágenes | Correcto |
| `familias.py` | Familias y campos obligatorios por familia | La familia vive en SKU y grupo, no en producto (sección 6.4) |
| `previa.py`, `verificacion.py` | SVG del servidor, miniaturas; verificación | Correcto |

### 2.2 Modelos — `backend/app/modelos/etiquetado.py`

- `FamiliaEtiquetado` (con `campos` obligatorios).
- `PlantillaEtiqueta` (`modalidad` ARTICULO | OC | OC_ARTICULO, `unidad`
  ORDEN | LINEA | ARTICULO | UNIDAD | BULTO | MANUAL, `familia_id` "para la que
  se diseñó") y `VersionPlantilla` (estados, aprobación).
- `AsignacionEtiqueta` (líneas 152–200): `ambito` GENERAL | FAMILIA | PRODUCTO |
  ARTICULO | OC | REGLA, un FK por cada destino con un `CHECK` que obliga a
  llenar exactamente uno, `prioridad` numérica, `condiciones` (JSON, 17
  operadores), `contexto` (JSON con modalidades, orígenes, unidades, tipos de
  empaque), `predeterminada`, vigencia, `motivo`, `version`.
- `GeneracionEtiquetas` / `GeneracionItem` (`referencia` en texto: el bulto se
  identifica solo por texto).
- Campos lógicos (`campos_etiqueta`) con `modalidades` (línea 220).
- Trabajos (`trabajos_etiqueta` y sus registros).
- En `modelos/maestros.py`: `Articulo.familia_etiquetado_id` (474) y
  `GrupoArticulo.familia_etiquetado_id` (411); `familia_efectiva` (485). El
  **producto** (`modelos/productos.py`, estilo-color) **no tiene familia**.

### 2.3 Frontend — `frontend/src/modulos/etiquetado/`

- `vistas/EtiquetasView.vue`: centro con **7 pestañas**.
- `vistas/TrabajoEtiquetasView.vue`: asistente con **8 pasos** (`PASOS`).
- `vistas/EditorEtiquetaView.vue` + `editor/*` (11 componentes): editor.
- `componentes/`: `AsignacionesEtiqueta`, `CamposEtiqueta`,
  `FamiliasEtiquetado`, `ArticulosFamilia`, `GruposFamilia`,
  `HistorialEtiquetas`, `ListaPlantillas`, `TrabajosEtiqueta`,
  `EtiquetadoProducto` (pestaña dentro del producto).
- `etiquetas.js`: catálogos **fijos en el cliente** (MODALIDADES, UNIDADES,
  UNIDADES_DE, ORIGENES, OPERADORES, AMBITOS, TAMANOS, SIMBOLOGIAS).
- Entradas desde otros módulos: OC (`OrdenView`), lista de empaque
  (`PackingListView`), producto (`EtiquetadoProducto`), rutas antiguas
  `/etiquetas/generar` y `/etiquetas/masiva` que redirigen al asistente.

### 2.4 Tres caminos de generación (debe quedar uno)

| Camino | Rutas | ¿Lo usa la interfaz? | ZIP propio |
|---|---|---|---|
| Generación directa | `POST /etiquetas/plan`, `POST /etiquetas/generaciones` | **No** | Sí (`generacion._producir`, respeta dpi) |
| Masiva | `POST /etiquetas/masivo/plan`, `POST /etiquetas/masivo`, `GET /etiquetas/masivo/{lote}/archivo` | Solo los **listados** `GET /masivo/ordenes` y `GET /masivo/packing` | Sí |
| Trabajos (asistente) | `/etiquetas/trabajos/*` | **Sí** | Sí (`trabajos.archivo`, **no** pasa dpi) |

Consecuencia: tres implementaciones de agrupación, nombres de archivo y ZIP
que ya divergen (dpi, límites, carpetas). Ver sección 8.

### 2.5 Pruebas existentes

`backend/tests/test_etiquetado_{contenido,durable,familias,generacion,integracion,masivo,plantillas,reglas,render,trabajos}.py`
y `frontend/e2e/etiquetado.mjs`. Cualquier cambio debe mantenerlas en verde
o actualizarlas explicando por qué cambió el comportamiento esperado.

---

## 3. Verificación de la revisión anterior (la que pegó el usuario)

| Afirmación de la otra revisión | Resultado | Evidencia |
|---|---|---|
| Las claves de bulto chocan entre listas de empaque | **Confirmado** | E1 |
| "Sin familia" aparece en artículos que sí tienen familia | **Confirmado** | E7 |
| Consultas repetidas por registro | **Confirmado** | R2 |
| El plan se recalcula varias veces | **Confirmado** (2–3 veces) | R1 |
| Límites inconsistentes (2000 vs 5000) | **Confirmado** | E8 |
| `ETIQUETAS_MAXIMO_TRABAJO` no está en las reglas de empresa | **Confirmado** | F12 |
| La `unidad` del diseño no se usa al generar | **Confirmado** (solo sugiere) | 6.2 |
| Se puede generar desde listas de empaque en borrador | **Confirmado** | E6 |
| En prueba se puede usar una versión rechazada o archivada | **Confirmado** | E2 |
| Fecha del servidor en vez de la zona horaria de la empresa | **Confirmado** | E3 |
| Cantidades fraccionarias en inner | **Confirmado** | E4 |
| Ejemplos de una marca concreta en el editor | **Confirmado** | F4 |
| Catálogo de campos y columnas de tabla fijos | **Confirmado** | F1, F2 |
| Aviso de casepack siempre activo | **Confirmado** | F9 |
| Textos impresos en inglés, formatos fijos | **Confirmado** | F5, F6 |
| Tamaños y simbologías fijos; faltan GS1 | **Confirmado** | F7, F13 |
| Prioridades y nombres de carpeta fijos | **Confirmado** | F10, F11 |
| Uso de `estilo` en `reglas.py` | **Confirmado** (`reglas.py:442`) | E11 |
| Tres caminos de generación con tres ZIP | **Confirmado** | 2.4 |
| Varios mecanismos de "obligatorio" | **Confirmado** (son cuatro) | 6.5 |
| 7 pestañas y botón duplicado | **Confirmado** | U1 |
| Claves técnicas visibles | **Confirmado** | U4 |
| Borrados sin confirmación | **Confirmado** | U5 |
| No se puede cambiar diseño o destino de una regla | **Confirmado** | 6.3 |
| La familia del diseño no se usa para asignar | **Confirmado** (solo advierte) | 6.2 |
| El bulto solo se referencia por texto | **Confirmado** | E1, 11 |
| Faltan clientes como contexto | **Parcial**: el sistema no tiene "clientes"; el contexto real disponible es proveedor, sociedad, centro, centro destino, país, marca y OC | 7.3 |
| Faltan recepciones, almacenes, direcciones | **Parcial/no verificado**: `Almacen` existe en maestros pero no se usa en etiquetado; recepciones no se revisaron | 11 |
| Faltan datos de línea de factura | **Parcial**: el contenido del bulto ya usa la línea de factura (`campos.py:383`); faltan campos sueltos de factura | 11 |
| Propuesta: tipos de etiqueta, matriz familia × tipo, escalera de especificidad, ver efecto antes de guardar, asignar desde cada pantalla | **De acuerdo**, con ajustes (sección 7): sujeto = artículo, contexto separado del sujeto, escalera fija (no editable al principio), varias etiquetas por registro | 7 |

**Hallazgos adicionales míos** (no estaban en la otra revisión): fuentes sin
CJK/árabe (F8), mezcla de hora local y UTC (E9), vista previa que recalcula
todo el plan (R3), `resumen_oc` que resuelve línea por línea (R4), bulto con
contenido mixto que solo toma los datos del primer artículo (E5), rutas sin
uso (2.4), familia a nivel SKU/grupo y no de producto (6.4), y el problema de
fondo: la división ARTICULO / OC_ARTICULO obliga a duplicar diseños y reglas
para el mismo artículo (6.1).

---

## 4. Errores reales (corregir primero)

Formato: **dónde** · **cómo reproducir** · **impacto** · **corrección** ·
**criterio de aceptación**.

### E1. Las claves de bulto chocan entre listas de empaque — Alta

- **Dónde:** `generacion.py:137` (`Grupo(f"b{b.numero}", …)`) y
  `generacion.py:167` (`f"b{b.numero}-p{p.id}"`); `campos.py:436–450`
  (`_unidades`: el contador `n` es local a cada lista, así que la numeración
  reinicia en 1 por lista); `trabajos.py` `_validar` guarda
  `nuevos[f"{prefijo}:{g.clave}"]` → la segunda clave **sobrescribe** a la
  primera sin aviso.
- **Reproducir:** crear un trabajo de origen PACKING (o de OC con bultos) que
  incluya dos listas de empaque con bultos; validar. El número de registros
  es menor que el número real de bultos; el bulto 1 de la lista B reemplaza
  al bulto 1 de la lista A.
- **Impacto:** se dejan de imprimir etiquetas de cajas; además
  `_previas` (generacion.py:402) cruza bultos por el texto de `referencia`,
  así que "ya impreso" puede marcarse sobre el bulto equivocado.
- **Corrección:** la clave debe incluir la identidad estable del bulto:
  `f"pl{pl.id}-g{grupo_cajas.id}-n{k}"` (lista, grupo de cajas, índice dentro
  del grupo). Guardar en `GeneracionItem` columnas `pl_id`,
  `grupo_cajas_id`, `indice_bulto` (o un `bulto_id` si se crea la tabla de
  bultos, ver 11) y cruzar por ellas, no por texto. Además, `_validar` debe
  **fallar** si dos grupos producen la misma clave (aserción defensiva).
- **Aceptación:** prueba con 2 listas × 3 bultos → 6 registros distintos;
  generar, volver a planear y comprobar que "ya impreso" marca exactamente
  los 6 correctos; una clave repetida provoca error 500 en pruebas (nunca
  pérdida silenciosa).

### E2. En modo prueba se usa la última versión aunque esté rechazada o archivada — Alta

- **Dónde:** `generacion.py:244–247`, `_version_de`: en prueba devuelve
  `plantilla.versiones[-1]` sin mirar su estado.
- **Reproducir:** diseño con v1 APROBADA y v2 RECHAZADA; generar en prueba →
  sale v2.
- **Impacto:** se imprime (aunque con marca de prueba) un diseño que alguien
  rechazó; confunde la revisión.
- **Corrección:** en prueba, usar la última versión en estado BORRADOR,
  EN_REVISION o APROBADA (nunca RECHAZADA ni ARCHIVADA); si se quiere probar
  una versión concreta, que el usuario la elija explícitamente
  (`version_id` en las opciones del trabajo).
- **Aceptación:** prueba unitaria con las combinaciones de estados.

### E3. La fecha de la etiqueta es la del servidor — Media

- **Dónde:** `datos.py:50` (`date.today()`), `reglas.py:385` (vigencia con
  `date.today()`). La organización tiene `zona_horaria`
  (`empresa/organizacion.py:48`) que el módulo ignora.
- **Reproducir:** servidor en UTC, empresa en America/El_Salvador (UTC−6);
  generar a las 19:00 locales → la etiqueta dice mañana y una regla que vence
  hoy ya no aplica.
- **Corrección:** función única `hoy_de(org)` en `core/` que devuelva
  `datetime.now(ZoneInfo(org.zona_horaria)).date()`; usarla en datos, reglas,
  nombres de trabajo y carpetas.
- **Aceptación:** prueba con zona fija y reloj simulado (freezegun o
  inyectar `hoy`).

### E4. Cantidades fraccionarias en empaques interiores — Media

- **Dónde:** `campos.py:385`: `por_unidad = h.num_cajas / g.num_cajas`. Si un
  grupo de 3 cajas lleva 10 inner, cada caja "lleva 3.333 inner".
- **Impacto:** la etiqueta imprime 3.33 unidades o un contenido que no
  corresponde a ninguna caja física.
- **Corrección:** si la división no es exacta, repartir enteros (4, 3, 3)
  usando el índice del bulto, o marcar el bulto como "contenido mixto" y
  emitir advertencia bloqueante en la validación. Decidir con el usuario
  (sección 15, D6). Nunca imprimir decimales en cantidades contables.
- **Aceptación:** prueba 10 inner / 3 cajas → contenidos 4, 3, 3 (o error
  claro), suma = 10.

### E5. Un bulto con varios artículos toma los datos del primero — Media

- **Dónde:** armado de valores del bulto en `campos.py` (`bultos()` /
  `_filas_contenido`): los campos escalares `articulo.*` se llenan con el
  primer artículo del contenido.
- **Impacto:** una caja mixta imprime el SKU/UPC de un solo artículo como si
  fuera todo el contenido.
- **Corrección:** en bultos mixtos, los campos escalares de artículo quedan
  vacíos y se exponen `bulto.mixto = true` y la colección `bulto.lineas`;
  el diseño de caja debe usar la tabla. La validación avisa si un diseño de
  bulto usa `articulo.sku` y hay cajas mixtas.
- **Aceptación:** prueba con caja de 2 SKU → `articulo.sku` vacío y aviso.

### E6. Se puede etiquetar desde una lista de empaque en borrador — Media

- **Dónde:** `generacion.py:208` en `cargar_pl`: solo excluye `CANCELADO`.
- **Impacto:** se imprimen cajas que todavía pueden cambiar; luego la lista
  cambia y las etiquetas ya pegadas no coinciden.
- **Corrección:** regla de empresa `ETIQUETAS_PL_ESTADOS` (por defecto:
  solo confirmadas/enviadas). En prueba se permite borrador con marca de
  prueba.
- **Aceptación:** borrador → 422 en real, 200 en prueba.

### E7. Insignia "Sin familia" falsa — Baja (pero confunde)

- **Dónde:** `componentes/ArticulosFamilia.vue:88–91`: el `v-else` de la
  insignia "Without family" cuelga del `span` "por grupo", así que un artículo
  con familia propia también muestra "Sin familia".
- **Corrección:** tres casos explícitos: propia (`familia_origen ===
  'ARTICULO'`), heredada del grupo (`'GRUPO'`), sin familia (`null`).
- **Aceptación:** prueba e2e o de componente con los tres casos.

### E8. Límites distintos según el camino — Baja

- **Dónde:** `trabajos.py:61` `MAX_ARTICULOS = 5000`, `masivo.py:37`
  `MAX_ARTICULOS = 2000`.
- **Corrección:** un solo límite leído de la regla de empresa
  `ETIQUETAS_MAXIMO_TRABAJO` (y que esa regla exista en `core/empresa.py`
  REGLAS, ver F12). Al unificar caminos (sección 8) desaparece el segundo.

### E9. Hora local mezclada con UTC — Baja

- **Dónde:** `trabajos.py:231, 270, 460, 487, 943` usan `datetime.now()`;
  el resto del sistema usa `ahora()` (UTC).
- **Impacto:** orden incorrecto en historial y comparaciones de "actualizado
  después de validar" erróneas si el servidor no está en UTC.
- **Corrección:** `ahora()` para todo lo que se guarda; `hoy_de(org)` solo
  para lo que se imprime o se muestra.

### E10. El PNG del ZIP del trabajo ignora la resolución — Baja

- **Dónde:** `trabajos.py:851`: `salidas.png(lz)` sin `dpi`;
  `generacion._producir` sí lo pasa.
- **Corrección:** pasar `dpi` de las opciones del trabajo (por defecto 300).
- **Aceptación:** PNG de 4×6 in a 300 dpi mide 1200×1800 px.

### E11. Motivo de la regla usa `estilo` — Baja

- **Dónde:** `reglas.py:442–443`: "Assigned to the product {a.estilo}". El
  producto es estilo-color; la regla de producto aplica a un `producto_id`.
- **Corrección:** mostrar `producto.estilo + color` (o el nombre del
  producto) cargado desde el `producto_id` de la regla.

### E12. Borrado físico de reglas sin confirmación — Media

- **Dónde:** `asignaciones.py` (delete físico) y la interfaz
  (`AsignacionesEtiqueta.vue`) no pide confirmación. Tampoco al borrar campos
  ni al archivar diseños (solo `EditorEtiquetaView.vue` usa `confirmar(`).
- **Impacto:** se pierde el historial de por qué un trabajo pasado usó un
  diseño.
- **Corrección:** baja lógica (`activa=false`, `eliminada_en`, `eliminada_por`)
  y confirmación en la interfaz mostrando cuántos artículos cambian de diseño
  (ver 7.6, "ver el efecto antes de guardar").

---

## 5. Valores fijos que deben ser configurables

| Id | Qué está fijo | Dónde | Propuesta |
|---|---|---|---|
| F1 | Catálogo de campos con nombres en inglés y estilo SAP ("Company code", "Plant code", "XF", casepack, inner, prepack, color/talla) | `campos.py` `_FIJOS` | Mantener las **claves** técnicas fijas, pero las **etiquetas visibles** salen del diccionario de traducción y cada empresa puede **renombrar y ocultar** campos (tabla `campos_etiqueta_alias`: clave, nombre, visible). Los atributos de variante ya son dinámicos; extender igual a los `extra` de OC/artículo. |
| F2 | Columnas de las tablas (colecciones) fijas a color y talla | `campos.py:66–78` (`_COL_*`) | Las columnas de una colección se arman con los atributos de variante de la empresa (`EscalaTalla`, atributos) y el diseño elige cuáles mostrar. |
| F3 | `bulto.parcial` = "yes"/"no" | `campos.py:181` | Booleano real; el diseño decide el texto (con traducción). |
| F4 | Ejemplos de una marca concreta (The North Face, NF0A7QEY…, OC 4500012345, PAR) | `datos_campos.py` | Los ejemplos salen de un artículo/OC real de la empresa (el más reciente) y, si no hay, de ejemplos neutros ("ACME", "SKU-0001"). |
| F5 | Meses en inglés (JAN…DEC) | `render.py:27` | Usar el idioma de la etiqueta (propiedad del diseño, no del usuario) con Babel o tabla por idioma. |
| F6 | Formato numérico `f"{n:,.{dec}f}"` y 4 patrones de fecha | `render.py:113, 121` | Formato según la configuración regional del diseño (separador de miles y decimal); patrones de fecha libres (`dd/MM/yyyy`, `yyyy-MM-dd`, `MMM yy`, …). |
| F7 | Simbologías: code128, code39, ean13, ean8, upca, qr | `codigos.py`, `etiquetas.js` SIMBOLOGIAS | Agregar GS1-128 (con identificadores de aplicación), ITF-14, SSCC-18 (dígito verificador), DataMatrix (GS1), PDF417. El catálogo debe venir del servidor (`GET /etiquetas/simbologias`), no de `etiquetas.js`. |
| F8 | Solo fuentes Liberation | `fuentes.py` | Incluir Noto Sans (latín), Noto Sans CJK, Noto Sans Devanagari, Noto Naskh Arabic, y permitir subir fuentes propias (TTF/OTF) por empresa con subconjunto al incrustar. Advertir si un texto tiene caracteres que la fuente no cubre. |
| F9 | Avisos de casepack e inner siempre activos | `empaque_etiquetas.py:29` | Regla de empresa `ETIQUETAS_VALIDAR_EMPAQUE` (apagado / advertencia / bloqueo). |
| F10 | Prioridades numéricas `{"OC":500,"ARTICULO":400,…}` | `reglas.py:36` | Se reemplazan por la escalera de especificidad (sección 7.4). |
| F11 | Nombres de carpeta `no-po`, `no-family`, `no-packing-list` y nombres de trabajo "PO …", "items" | `trabajos.py:236, 813–819` | Traducibles; el patrón de carpetas y nombres ya es configurable en el paso "Generar": que los textos de "sin valor" también lo sean. |
| F12 | `ETIQUETAS_MAXIMO_TRABAJO`, `ETIQUETAS_MAXIMO_LOTE` no editables | `core/empresa.py` REGLAS (solo tiene ETIQUETAS_CUATRO_OJOS, GENERACION_PARCIAL, ASINCRONO_DESDE) | Agregarlas a REGLAS con mínimo/máximo, visibles en Configuración de empresa. |
| F13 | Tamaños de etiqueta (4×6, A4 3×8…) | `etiquetas.js` TAMANOS | Tabla `tamanos_etiqueta` por empresa (nombre, ancho, alto, hoja, filas, columnas, márgenes) con los actuales como semilla. |
| F14 | MODALIDADES, UNIDADES, UNIDADES_DE, ORIGENES, AMBITOS, OPERADORES | `etiquetas.js` | Desaparecen o se sirven del servidor tras el rediseño (sección 7). Nunca duplicar catálogos de negocio en el cliente. |
| F15 | Marca de prueba "TEST · NOT APPROVED" | `fuentes.py` | Texto traducible configurable por empresa. |
| F16 | "… +{resto}" al recortar tablas | `render.py:616` | Texto traducible ("y {n} más"). |

---

## 6. Por qué las reglas se sienten complejas y fijas (diagnóstico)

### 6.1 El mismo artículo se trata distinto según de dónde venga

Hoy un diseño tiene `modalidad` ARTICULO, OC u OC_ARTICULO, y
`MODALIDADES_DE` decide qué reglas se cargan según el origen del trabajo.
Resultado: la etiqueta colgante del artículo X necesita **un diseño y una
regla para "artículo suelto"** y **otro diseño y otra regla para "artículo
dentro de una OC"**, aunque sea la misma etiqueta física. Como dijo el
usuario: *"la info de la OC es propia y las OC se componen de artículos; la
info no debería diferir del artículo en sí"*.

La diferencia real entre ambos casos es solo **qué datos adicionales hay
disponibles** (número de OC, destino, fecha XF). Eso no justifica un concepto
de primer nivel; basta con que el diseño declare qué datos necesita y la
validación avise si el origen no los trae.

### 6.2 Conceptos que existen pero no deciden nada

- `PlantillaEtiqueta.unidad` (qué representa cada etiqueta) solo se usa como
  sugerencia; al generar manda lo que elija el trabajo.
- `PlantillaEtiqueta.familia_id` ("para la que se diseñó") solo produce una
  advertencia (`reglas.py` ~420–425); no asigna.
- `contexto.unidades` y `contexto.modalidades` en la regla repiten lo que ya
  dice el diseño.

Cada concepto que no decide nada es una pregunta más que el usuario tiene que
contestar sin saber para qué.

### 6.3 Las reglas no se pueden corregir

`asignaciones.py` al actualizar no permite cambiar `plantilla_id` ni el
destino (`ambito` + FK). Para corregir un error hay que borrar (borrado
físico, sin confirmación) y volver a crear, perdiendo historial.

### 6.4 La familia vive en el lugar equivocado

La familia de etiquetado está en el **SKU** (`Articulo`) y en el **grupo**;
no en el **producto** (estilo-color, tabla `productos`). En la práctica todas
las tallas de un estilo-color llevan la misma etiqueta, así que asignar por
SKU obliga a repetir por cada talla y deja tallas sueltas sin familia.

### 6.5 Cuatro formas de decir "obligatorio"

1. `Variable.obligatorio` (variables manuales del diseño, `diseno.py`).
2. Obligatorio por elemento (`render.py:373`).
3. Campos obligatorios de la familia (`FamiliaEtiquetado.campos`).
4. `BLOQUEAR` como política de conflicto de un campo lógico.

El usuario no puede saber cuál de las cuatro bloqueó su trabajo.

### 6.6 Prioridad numérica y desempates

`PRIORIDAD` (500/400/300/250/200/100) más `prioridad` editable, más
`predeterminada`, más "elección del usuario" en el trabajo. Los números no
significan nada para el usuario; los conflictos se descubren al generar, no al
guardar la regla; `conflictos()` compara todas las reglas por pares (O(n²)).

### 6.7 Una sola etiqueta por registro

El motor resuelve **un** diseño por registro. Si un artículo necesita
etiqueta colgante + etiqueta de precio + sticker de bolsa, hay que hacer tres
trabajos distintos y acordarse de cuáles.

---

## 7. Rediseño propuesto: reglas genéricas

### 7.1 Principios

1. **El sujeto decide, el contexto ajusta.** El diseño de una etiqueta lo
   determina **qué se etiqueta** (el artículo, el bulto, el documento) y **qué
   tipo de etiqueta es**. El origen del trabajo (OC, lista de empaque,
   selección de artículos, el propio módulo) solo aporta **contexto**: datos
   extra para imprimir y, opcionalmente, excepciones explícitas.
2. **Lo general se define una vez y se hereda.** Empresa → grupo → familia →
   producto → SKU. Lo más específico gana; no hay números.
3. **Las excepciones son explícitas y legibles.** "Para el proveedor X / el
   destino Y / la OC Z, usar este otro diseño" — con motivo y vigencia.
4. **Ver el efecto antes de guardar.** Toda regla nueva o cambiada muestra
   cuántos artículos/bultos cambian de diseño y cuáles quedan sin diseño.
5. **Varias etiquetas por registro**, una por tipo de etiqueta.
6. **Todo se puede editar**, con historial (versión de la regla) y baja
   lógica.

### 7.2 Conceptos nuevos (lo que ve el usuario)

| Concepto | Qué es | Ejemplo |
|---|---|---|
| **Tipo de etiqueta** (definido por la empresa) | Una clase de etiqueta física, con qué se etiqueta y cuántas salen | "Etiqueta colgante" (artículo, una por unidad); "Sticker de precio" (artículo, una por unidad); "Etiqueta de caja master" (bulto, una por bulto); "Hoja de contenido de OC" (documento, una por OC) |
| **Diseño** | El dibujo (ya existe), ahora pertenece a un tipo de etiqueta | "Colgante TNF 2×3 in" |
| **Uso de diseño** (reemplaza a "asignación/regla") | "Para este tipo de etiqueta, en este nivel, usar este diseño" | "Etiqueta colgante → familia Calzado → diseño Colgante calzado v3" |
| **Excepción** | Un uso con contexto | "Etiqueta colgante → familia Calzado → **si el destino es Panamá** → Colgante calzado bilingüe" |
| **Familia** | Igual que hoy, pero asignable al producto (estilo-color) y heredable | "Calzado", "Ropa", "Accesorios" |

**Desaparecen para el usuario:** modalidad, unidad del diseño, ámbito
"REGLA", prioridad numérica, `predeterminada`, `contexto.modalidades`,
`contexto.unidades`.

### 7.3 Sujeto, cantidad y contexto

**Sujeto** (fijo en el sistema, solo 3 valores, propiedad del tipo de
etiqueta):

| Sujeto | Un registro es… | Datos disponibles siempre | Datos que agrega el contexto |
|---|---|---|---|
| `ARTICULO` | un SKU (con cantidad) | `articulo.*`, `producto.*`, `organizacion.*`, `etiqueta.*` | `oc.*`, `linea.*` si viene de OC; `bulto.*` si viene de lista de empaque |
| `BULTO` | una caja/unidad de empaque de una lista de empaque | `bulto.*`, `bulto.lineas`, `bulto.componentes`, `organizacion.*` | `oc.*` de la OC del bulto (si es una sola) |
| `DOCUMENTO` | una OC o una lista de empaque completa | `oc.*`, `oc.lineas` o `pl.*` | — |

**Cantidad** (propiedad del tipo, el trabajo puede ajustarla):
`POR_UNIDAD` (una por pieza/par), `POR_LINEA` (una por línea o SKU),
`POR_BULTO`, `POR_DOCUMENTO`, `MANUAL` (la escribe el usuario).
Esto reemplaza a `unidad` (ORDEN, LINEA, ARTICULO, UNIDAD, BULTO, MANUAL) con
el mismo poder pero en un solo lugar.

**Contexto** (para excepciones; dimensiones que **sí existen** en el modelo
de datos actual):

| Dimensión | Fuente | Ejemplo |
|---|---|---|
| `PROVEEDOR` | `OrdenCompra.proveedor_id`, `Articulo.proveedor_id` | "Si lo fabrica el proveedor X" |
| `MARCA` | `Articulo.marca_id` | (normalmente es mejor usar familia; se deja como condición) |
| `SOCIEDAD` | `OrdenCompra.sociedad` | "Si compra la sociedad 1000" |
| `CENTRO_DESTINO` | `OrdenCompra.centro_destino` | "Si va al centro 2220" |
| `PAIS_DESTINO` | país del centro destino | "Si va a Panamá" |
| `OC` | `OrdenCompra.id` | "Solo para la OC 4500…" (excepción puntual, motivo obligatorio) |
| `TIPO_EMPAQUE` | `TipoEmpaque` del bulto (solo sujeto BULTO) | "Si la caja es inner" |

Si el registro no tiene contexto (artículos sueltos, sin OC), las
excepciones con contexto simplemente **no aplican** y rige el uso general.
**Así, el mismo artículo recibe el mismo diseño venga de donde venga**, salvo
que exista una excepción explícita para ese contexto.

**Datos que el diseño necesita:** al guardar una versión del diseño se
calcula `requiere` (lista de grupos de campos usados: `oc`, `linea`, `bulto`…).
Al validar un trabajo, si un registro no tiene un grupo requerido (por
ejemplo, el diseño imprime `oc.numero` y el origen son artículos sueltos):
el campo queda vacío si el elemento es opcional, o bloquea si es obligatorio
(un solo mecanismo de obligatorio, ver 7.8).

### 7.4 Escalera de especificidad (reemplaza la prioridad numérica)

Para un registro y un tipo de etiqueta se toman todos los usos activos y
vigentes que coinciden, y gana el de **mayor especificidad**, comparando en
este orden (lexicográfico):

1. **Contexto:** `OC` > `CENTRO_DESTINO` > `PAIS_DESTINO` > `SOCIEDAD` >
   `PROVEEDOR` > sin contexto.
   (Una exigencia del destino o de una OC concreta manda sobre la regla
   general del artículo.)
2. **Nivel del sujeto:** `SKU` > `PRODUCTO` (estilo-color) > `FAMILIA` >
   `GRUPO` > `GENERAL` (empresa).
3. **Condiciones adicionales:** un uso con condiciones gana a uno igual sin
   condiciones.

Si después de esto quedan **dos usos empatados que coinciden**, es un
**conflicto** y se impide **al guardar** el segundo (no al generar). El
mensaje dice cuáles son y qué registros afectan.

> Alternativa considerada: escalera editable por empresa (la otra revisión
> lo propone). Recomiendo **fija** en la primera versión: es más fácil de
> explicar, de probar y de migrar. Si un cliente real necesita otro orden,
> se agrega después como regla de empresa (decisión D3).

### 7.5 Modelo de datos

```text
tipos_etiqueta
  id, organizacion_id
  codigo            varchar(30)   único por organización
  nombre            varchar(120)
  descripcion       text
  sujeto            ARTICULO | BULTO | DOCUMENTO
  cantidad          POR_UNIDAD | POR_LINEA | POR_BULTO | POR_DOCUMENTO | MANUAL
  obligatoria       bool          -- si todo sujeto debe tener diseño de este tipo (avisa "sin diseño")
  orden             int
  activo            bool
  creado_en/por, actualizado_en/por, version

plantillas_etiqueta  (existente)
  + tipo_etiqueta_id   FK tipos_etiqueta  NOT NULL tras migrar
  - modalidad          (se conserva solo lectura durante la transición; se elimina en fase 4)
  - unidad             (ídem)
  - familia_id         (ídem: pasa a ser un "uso")

versiones_plantilla  (existente)
  + requiere          JSON   -- ["oc","linea","bulto"...] calculado al guardar el diseño

productos  (existente)
  + familia_etiquetado_id  FK familias_etiquetado  (herencia: SKU → producto → grupo)

usos_diseno  (reemplaza asignaciones_etiqueta)
  id, organizacion_id
  tipo_etiqueta_id   FK  NOT NULL
  plantilla_id       FK  NOT NULL       -- editable
  nivel              GENERAL | GRUPO | FAMILIA | PRODUCTO | SKU
  grupo_id / familia_id / producto_id / articulo_id   -- exactamente uno según nivel (CHECK), o ninguno en GENERAL
  contexto_tipo      NINGUNO | PROVEEDOR | SOCIEDAD | CENTRO_DESTINO | PAIS_DESTINO | OC | TIPO_EMPAQUE
  contexto_valor     varchar(40)        -- id o código según el tipo; NULL si NINGUNO
  condiciones        JSON  default []   -- mismas condiciones de hoy, operadores reducidos (7.8)
  vigente_desde, vigente_hasta  date
  motivo             varchar(300)       -- obligatorio si contexto_tipo = OC
  activo             bool
  eliminado_en, eliminado_por           -- baja lógica
  creado_en/por, actualizado_en/por
  version            int                -- concurrencia optimista
  INDEX (organizacion_id, tipo_etiqueta_id, nivel, contexto_tipo)

usos_diseno_historial
  id, uso_id, version, datos JSON (foto completa), cambiado_en, cambiado_por, accion (CREAR|EDITAR|BAJA)
```

Todas las tablas nuevas con `organizacion_id`, RLS igual que el resto
(revisar la migración 0070 como modelo), y registradas en el mecanismo de
versiones de datos (`versiones_datos`) para que la caché y el canal de
cambios las vean.

**Varias etiquetas por registro:** los registros de un trabajo pasan a
tener la clave `(sujeto, tipo_etiqueta_id)`. Un trabajo elige qué tipos de
etiqueta imprime (por defecto: todos los tipos `obligatoria` del sujeto).

### 7.6 Algoritmo de resolución

```python
def resolver(registros, tipos, hoy):
    # 1) Cargar UNA vez todos los usos activos y vigentes de esos tipos
    usos = cargar_usos(tipos, hoy)                      # 1 consulta
    indice = indexar(usos)  # {(tipo, nivel, sujeto_id, contexto_tipo, contexto_valor): [usos]}

    # 2) Precargar datos de los sujetos (familia efectiva, producto, grupo, contexto)
    datos = precargar(registros)                         # consultas por lote, no por registro

    for r in registros:
        for tipo in tipos_aplicables(r, tipos):          # por sujeto
            candidatos = []
            for ctx in contextos_de(r):                  # [("OC",id), ("CENTRO_DESTINO",c), ..., ("NINGUNO",None)]
                for nivel, sid in escalones(r):          # [("SKU",a), ("PRODUCTO",p), ("FAMILIA",f), ("GRUPO",g), ("GENERAL",None)]
                    for u in indice.get((tipo, nivel, sid, *ctx), []):
                        if cumple(u.condiciones, r):
                            candidatos.append((rango(ctx, nivel, u), u))
            elegir(r, tipo, candidatos)                  # mayor rango; empate => conflicto (no debería pasar: se impide al guardar)
```

- Complejidad: O(registros × escalones × contextos) con búsquedas en
  diccionario; sin consultas por registro.
- El resultado incluye **por qué** ("Familia Calzado, excepción destino
  Panamá, motivo: requisito aduana") en lenguaje claro y traducible.
- **Detección de conflictos al guardar:** buscar usos con la misma clave
  `(tipo, nivel, sujeto, contexto_tipo, contexto_valor)`, condiciones
  equivalentes y vigencias que se superponen. Es una consulta indexada, no
  O(n²).

### 7.7 API

```text
GET    /api/etiquetas/tipos                     listar tipos
POST   /api/etiquetas/tipos                     crear
PATCH  /api/etiquetas/tipos/{id}                editar (con version)
POST   /api/etiquetas/tipos/{id}/desactivar

GET    /api/etiquetas/usos?tipo=&nivel=&q=      listar usos (con nombres legibles del destino)
POST   /api/etiquetas/usos/simular              {uso} -> {cambian:[{sujeto, antes, despues}], sin_diseno:[...], conflictos:[...]}  (no guarda)
POST   /api/etiquetas/usos                      crear (rechaza conflictos con 409 + detalle)
PATCH  /api/etiquetas/usos/{id}                 editar TODO (diseño, nivel, destino, contexto) con version
POST   /api/etiquetas/usos/{id}/baja            baja lógica (con motivo)
GET    /api/etiquetas/usos/{id}/historial

GET    /api/etiquetas/matriz?tipo=              filas = familias (y "sin familia"), columnas = tipos; celda = diseño general + n.º de excepciones
GET    /api/etiquetas/resolver?sujeto=ARTICULO&id=123&contexto=OC:45   qué diseño(s) le tocan y por qué
GET    /api/etiquetas/cobertura                 sujetos sin diseño para tipos obligatorios (para el tablero)
```

Se retiran (fase 4, tras confirmar que nadie las usa): `POST /etiquetas/plan`,
`POST /etiquetas/generaciones`, `POST /etiquetas/masivo/plan`,
`POST /etiquetas/masivo`, `GET /etiquetas/masivo/{lote}/archivo`,
`/etiquetas/asignaciones*`, `/etiquetas/reglas*`. Durante la transición,
`/asignaciones` responde leyendo de `usos_diseno` (adaptador).

### 7.8 Un solo "obligatorio" y condiciones más simples

- **Obligatorio = propiedad del elemento del diseño** (el campo debe tener
  valor para imprimir). Las variables manuales son elementos con origen
  "manual". La familia deja de tener `campos` obligatorios propios: en su
  lugar, la validación del trabajo informa "el diseño X necesita el campo
  `articulo.composicion` y estos 12 artículos no lo tienen" con enlace para
  completarlo. La política `BLOQUEAR` de campos lógicos se mantiene, pero su
  mensaje de error dice "el campo *Origen* tiene dos valores distintos
  (A en la OC, B en el artículo)".
- **Operadores de condición:** mostrar en la interfaz solo `es`, `no es`,
  `es uno de`, `no es uno de`, `contiene`, `está vacío`, `no está vacío`,
  `mayor que`, `menor que`. Los 17 actuales siguen aceptándose en la API
  para no romper reglas migradas.

### 7.9 Pantallas

**Centro de etiquetado: 3 secciones** (en vez de 7 pestañas)

1. **Imprimir** — trabajos recientes, botón único "Nuevo trabajo".
2. **Diseños** — lista de diseños agrupados por tipo de etiqueta; editor.
3. **Configuración** — subpestañas: *Tipos de etiqueta*, *Qué diseño usa
   cada familia* (la matriz), *Excepciones*, *Familias y artículos*, *Campos*,
   *Historial*.

**La matriz "Qué diseño usa cada familia"**

| Familia ↓ / Tipo → | Etiqueta colgante | Sticker de precio | Caja master |
|---|---|---|---|
| (Toda la empresa) | — | Precio estándar | Caja GS1 4×6 |
| Calzado | Colgante calzado (+2 excepciones) | *(hereda)* | *(hereda)* |
| Ropa | Colgante ropa | *(hereda)* | *(hereda)* |
| Sin familia (37 artículos) | ⚠ sin diseño | *(hereda)* | *(hereda)* |

- Hacer clic en una celda abre una **ventana (Modal)** con: diseño
  (buscador con miniatura), "aplicar también a…" (producto / SKU concretos),
  y la **simulación**: "Cambia el diseño de 214 artículos; 0 quedan sin
  diseño". Guardar solo si no hay conflictos.
- "(+2 excepciones)" abre la lista de excepciones de esa celda.
- Las celdas heredadas se ven en gris con el texto "hereda de Toda la
  empresa".

**Excepciones:** lista legible, una por fila: *"Etiqueta colgante · Calzado ·
si el destino es Panamá → Colgante bilingüe · hasta 31/12/2026 · motivo:
requisito aduana"*, con editar / dar de baja / ver historial.

**Asignar desde cada pantalla** (sin ir al módulo):

- Ficha de producto (`EtiquetadoProducto.vue`): "Este producto usa: Colgante
  calzado (por familia Calzado) · Caja GS1 (por empresa)" + "Usar otro diseño
  para este producto" (crea un uso nivel PRODUCTO) + "Imprimir".
- OC (`OrdenView`): resumen por tipo de etiqueta con conteos y
  "Agregar excepción para esta OC" (motivo obligatorio) + "Imprimir".
- Lista de empaque (`PackingListView`): igual, sujeto BULTO y ARTICULO.

**Asistente de trabajo: 3 pasos** (en vez de 8)

1. **Qué** — origen (OC / lista de empaque / artículos / familia) y
   selección; tipos de etiqueta a imprimir (marcados los obligatorios).
2. **Revisar** — tabla con cada registro, su diseño y por qué, cantidades
   editables, problemas con **corrección en el lugar** (completar un dato
   faltante, elegir diseño, ajustar cantidad) y vista previa al lado (panel
   lateral: solo vista previa).
3. **Generar** — formato, agrupación del ZIP (ya existe), modo prueba/real.

Los pasos actuales de parámetros, validación, conflictos y variables
manuales se integran en "Revisar". Los valores manuales se piden **solo** si
algún diseño elegido tiene variables manuales.

**Lenguaje claro:** nunca mostrar `({{ f.clave }})`
(`AsignacionesEtiqueta.vue:291`, `CamposEtiqueta.vue:129`), `manual.clave`
(`PanelEtiqueta.vue`) ni la "huella" sha256 (`HistorialEtiquetas.vue`) salvo
en un detalle técnico plegado.

**Primer uso guiado:** si la empresa no tiene tipos de etiqueta, el centro
muestra un asistente: "¿Qué etiquetas usas?" con plantillas de tipos
(colgante, precio, caja master, contenido de OC), crea los tipos y un diseño
de ejemplo por tipo, y lleva a la matriz.

### 7.10 Migración de reglas existentes

**Alternativas (decisión D1):**

| Opción | Qué implica | Consecuencias |
|---|---|---|
| **A. Migración automática con informe** (recomendada) | Una migración Alembic crea tipos de etiqueta a partir de `(modalidad, unidad)` de los diseños y convierte cada `asignacion_etiqueta` en un `uso_diseno`. Lo que no se pueda convertir 1:1 se deja **inactivo** y en un informe. | Sin trabajo manual en la mayoría de los casos; el comportamiento puede cambiar en los casos marcados (por diseño: ARTICULO y OC_ARTICULO se juntan). Requiere revisar el informe. |
| B. Convivencia | Mantener el motor actual para lo existente y el nuevo solo para lo nuevo. | Dos motores, el doble de pruebas, el usuario ve dos formas de hacer lo mismo. No recomendado. |
| C. Empezar de cero | Desactivar las reglas viejas y pedir al usuario que configure la matriz. | Más simple de programar, pero se pierde la configuración y se rompen trabajos en curso. |

**Mapeo de la opción A:**

| Hoy | Nuevo |
|---|---|
| Diseño con `modalidad`=ARTICULO u OC_ARTICULO y `unidad` UNIDAD/ARTICULO/LINEA | Tipo `ARTICULO` (uno por combinación de unidad distinta, nombre "Etiqueta de artículo (por unidad)" etc.). ARTICULO y OC_ARTICULO con la misma unidad caen en **el mismo tipo**. |
| `modalidad`=OC, `unidad`=ORDEN | Tipo `DOCUMENTO`, cantidad POR_DOCUMENTO |
| `unidad`=BULTO | Tipo `BULTO`, cantidad POR_BULTO |
| `unidad`=MANUAL | Cantidad MANUAL |
| `ambito` GENERAL | nivel GENERAL, contexto NINGUNO |
| `ambito` FAMILIA / PRODUCTO / ARTICULO | nivel FAMILIA / PRODUCTO / SKU |
| `ambito` OC | nivel GENERAL (o el de sus condiciones), contexto OC, motivo copiado |
| `ambito` REGLA (solo condiciones) | nivel GENERAL + condiciones; si las condiciones son "familia es X" o "marca es Y", se convierte a nivel FAMILIA o contexto MARCA |
| `prioridad` y `predeterminada` | Se descartan; si al convertir aparecen empates, el de mayor prioridad antigua queda activo y los demás **inactivos** con nota en el informe |
| `contexto.origenes` = solo OC | contexto: requiere OC → se marca en el informe para revisión |
| `contexto.tipos_empaque` | contexto TIPO_EMPAQUE |
| Dos reglas iguales para ARTICULO y OC_ARTICULO con el mismo diseño | Se fusionan en un uso |
| Dos reglas iguales para ARTICULO y OC_ARTICULO con **diseños distintos** | El de ARTICULO queda como uso general; el de OC_ARTICULO queda **inactivo** con nota "antes se usaba otro diseño cuando venía de una OC; si es necesario, cree una excepción por destino o proveedor" |
| Trabajos ya generados | No se tocan: guardan versión de diseño e historial; solo se agrega `tipo_etiqueta_id` calculado |
| Trabajos en BORRADOR/VALIDADO | Se marcan "requiere revalidar" |

**Informe de migración:** tabla `migracion_etiquetado_informe` (o un JSON en
la tabla de bitácora) visible en Configuración → Historial, con cada regla
original, el uso resultante y su estado (convertida / fusionada / inactiva y
por qué).

**Reversibilidad:** la migración no borra `asignaciones_etiqueta` ni las
columnas viejas hasta la fase 4; `downgrade` borra solo las tablas nuevas.

### 7.11 Cómo se resuelven los ejemplos del usuario

| Situación | Hoy | Con el rediseño |
|---|---|---|
| Etiqueta colgante del SKU 123, impresa sola | Regla ARTICULO con diseño modalidad ARTICULO | Uso "Colgante · Familia Calzado" |
| Mismo SKU 123 dentro de la OC 4500 | Otra regla (modalidad OC_ARTICULO) y a menudo otro diseño | **El mismo uso**; el diseño puede imprimir `oc.numero` si lo trae |
| La OC 4500 exige una etiqueta especial | Regla ámbito OC con prioridad 500 | Excepción contexto OC 4500 + motivo |
| Todo lo que va a Panamá lleva etiqueta bilingüe | Regla REGLA con condición `oc.centro_destino en [...]` y prioridad a mano | Excepción contexto PAIS_DESTINO = PA |
| Caja master de la lista de empaque | Diseño unidad BULTO + regla | Uso "Caja master · Toda la empresa" |
| Colgante + precio + caja | 3 trabajos | 1 trabajo con 3 tipos marcados |

---

## 8. Generación: un solo camino

1. **Un solo servicio de planeación** (`generacion.planear(origen,
   parametros, tipos)`) que devuelve registros con clave estable, diseño
   resuelto y datos; lo usan el asistente, la vista previa y la generación.
2. **Un solo productor de archivos** (`salidas.empaquetar(plan, opciones)`)
   con agrupación, carpetas, nombres y dpi. Base: el de `trabajos.py` (es el
   que usa la interfaz y ya tiene agrupación configurable) más el dpi de
   `generacion._producir`.
3. `masivo.py` queda como **listados** (`GET /masivo/ordenes`,
   `GET /masivo/packing`, que el asistente usa) movidos a `trabajos.py` o a
   un `buscadores.py`; el resto se retira tras una versión con aviso de
   obsolescencia (cabecera `Deprecation`).
4. Rutas antiguas `/etiquetas/generar` y `/etiquetas/masiva` del cliente
   siguen redirigiendo al asistente (ya cubiertas por `e2e/etiquetado.mjs`).

**Aceptación:** `grep -rn "def _producir\|ZipFile(" backend/app/modulos/etiquetado`
muestra un solo lugar; las pruebas de `test_etiquetado_masivo.py` se
reescriben contra trabajos o se retiran con autorización.

---

## 9. Rendimiento

| Id | Problema | Dónde | Corrección | Aceptación |
|---|---|---|---|---|
| R1 | Generar recalcula el plan 2–3 veces (`_validar` + `generacion.generar` → `plan()`) | `trabajos.py:571`, `generacion.py` | Guardar el resultado de validar en los registros del trabajo (ya existen) con una huella de los datos; generar reutiliza si la huella no cambió (las versiones de `versiones_datos` sirven de huella barata: si no cambió ninguna tabla leída, el plan sigue vigente) | Contador de consultas en prueba: generar tras validar no vuelve a resolver reglas |
| R2 | Consultas por registro en `valores_oc` (posiciones; sociedad y centro buscados por código de texto) | `campos.py:315–333` | Precargar por lote (`selectinload`, diccionarios de sociedad/centro por código) | OC de 200 líneas: consultas constantes (no crecen con las líneas) |
| R3 | La vista previa de un registro ejecuta todo `plan()` | `trabajos.vista_previa` (`trabajos.py:951`) | Planear solo ese registro (por clave) | Vista previa de 1 registro en trabajo de 2000: < 300 ms |
| R4 | `resumen_oc` resuelve cada línea por separado | `generacion.py:674` | Usar el resolvedor por lote (7.6) | Igual que R2 |
| R5 | `plan()` dibuja todos los grupos aunque solo se necesite contar | `generacion.py` | Separar "resolver" de "dibujar"; dibujar solo al generar o al pedir vista previa | — |
| R6 | `conflictos()` compara por pares | `reglas.py:508` | Consulta por clave (7.6) | — |

Las tablas nuevas deben participar en la caché por ETag y en el canal de
cambios (`backend/app/core/cambios.py`); las pantallas nuevas usan
`alCambiar(recargar, ['/etiquetas/usos', '/etiquetas/tipos'])`
(`frontend/src/nucleo/cambios.js`).

---

## 10. Experiencia de uso (detalle)

| Id | Problema | Dónde | Corrección |
|---|---|---|---|
| U1 | 7 pestañas; botón "Nuevo trabajo" duplicado | `EtiquetasView.vue`, `TrabajosEtiqueta.vue:53` | 3 secciones (7.9); un solo botón |
| U2 | Asistente de 8 pasos | `TrabajoEtiquetasView.vue` `PASOS` | 3 pasos (7.9) |
| U3 | No se puede corregir un problema desde la validación | asistente | Corrección en el lugar: completar dato, elegir diseño, ajustar cantidad, sin salir del paso |
| U4 | Claves técnicas visibles | `AsignacionesEtiqueta.vue:291`, `CamposEtiqueta.vue:129`, `PanelEtiqueta.vue`, `HistorialEtiquetas.vue` | Nombres legibles; lo técnico en un detalle plegado |
| U5 | Sin confirmación al borrar/archivar | reglas, campos, diseños | `confirmar()` con el efecto ("214 artículos quedarán sin diseño") |
| U6 | "Sin familia" falsa | E7 | — |
| U7 | Mensajes de motivo en inglés fijo | `reglas.py` `_motivo` | Claves de traducción con parámetros |
| U8 | Creación en paneles laterales | (corregido en 7a1422b) | Mantener: crear/editar en Modal, panel solo para ver |
| U9 | Vista previa desbordada | (corregido en 7a1422b, clase `.previa-etiqueta`) | Reutilizar la clase en toda pantalla nueva |
| U10 | Sin estado vacío útil | centro | Primer uso guiado (7.9) |

---

## 11. Datos relacionados e integraciones que faltan

1. **Bulto como entidad.** Hoy un bulto es "grupo de cajas + índice" y en
   el historial solo un texto. Crear `bultos` (id, pl_id, grupo_cajas_id,
   indice, sscc, estado_impresion) o al menos guardar `pl_id`,
   `grupo_cajas_id`, `indice` en `GeneracionItem` (E1). Con eso se puede
   asignar un **SSCC** único por bulto (usar `core/numeracion.py`, series con
   contador bloqueado; el prefijo GS1 de la empresa como regla de empresa) y
   reimprimir exactamente una caja.
2. **Almacén y direcciones.** `Almacen` existe en maestros pero no se expone
   como campo; agregar `destino.*` (nombre, dirección, país del centro
   destino) y `origen.*` (almacén/planta del proveedor) al catálogo.
3. **Factura.** Agregar campos sueltos de la factura del bulto
   (`factura.numero`, `factura.fecha`) cuando el bulto viene de una lista de
   empaque facturada.
4. **Recepciones.** No verificado si existe un módulo de recepciones; si
   existe, permitir sujeto BULTO desde una recepción (reetiquetado).
5. **Impresoras directas (ZPL).** Fuera de alcance inmediato; el diseño ya es
   independiente del formato, se puede agregar `salidas.zpl()` después.

---

## 12. Datos de demostración (semilla)

Objetivo: que al abrir el módulo con `SEED_DEMO=1` se vea **cómo se armó
todo** y se pueda generar desde los cuatro orígenes. Implementar en la
semilla de demo existente (la misma que activa `SEED_DEMO=1`), idempotente,
solo para la organización demo.

**Familias** (asignadas al **producto**, con algunos SKU con familia propia
para mostrar la herencia):

| Código | Nombre | Asignación demo |
|---|---|---|
| CALZ | Calzado | productos de calzado; un SKU con familia propia "Calzado técnico" |
| ROPA | Ropa | por grupo de artículos (herencia de grupo) |
| ACC | Accesorios | 2 productos |
| — | Sin familia | 3 artículos a propósito, para que la cobertura muestre el aviso |

**Tipos de etiqueta:**

| Código | Nombre | Sujeto | Cantidad | Obligatoria |
|---|---|---|---|---|
| COLG | Etiqueta colgante | ARTICULO | POR_UNIDAD | sí |
| PREC | Sticker de precio | ARTICULO | POR_UNIDAD | no |
| CAJA | Etiqueta de caja master | BULTO | POR_BULTO | sí |
| CONT | Hoja de contenido de OC | DOCUMENTO | POR_DOCUMENTO | no |

**Diseños** (con versión APROBADA, y uno con una v2 EN_REVISION para mostrar
el flujo de aprobación):

- "Colgante calzado 2×3 in" (code128 + campos de artículo + `oc.numero`
  opcional), "Colgante ropa 2×3 in", "Colgante bilingüe" (para la excepción),
  "Precio estándar 1.5×1 in", "Caja master GS1 4×6 in" (con tabla
  `bulto.lineas`), "Contenido de OC A4".

**Usos (la matriz):**

- GENERAL: PREC → Precio estándar; CAJA → Caja master; CONT → Contenido de OC.
- FAMILIA CALZ: COLG → Colgante calzado. FAMILIA ROPA: COLG → Colgante ropa.
- PRODUCTO (uno concreto de ACC): COLG → Colgante ropa (muestra nivel producto).
- **Excepción** PAIS_DESTINO (el país de un centro destino que exista en la
  demo): COLG Calzado → Colgante bilingüe, motivo "requisito de aduana",
  vigente hasta fin de año.
- **Excepción** OC (una OC demo concreta): CAJA → Caja master con logo del
  cliente, motivo "pedido especial".
- Un uso dado de baja (para que el historial muestre una baja con motivo).

**Trabajos de ejemplo** (en distintos estados, con nombre descriptivo):

1. Desde **OC** — "Demo · OC {n} · colgantes y contenido" (GENERADO real).
2. Desde **artículos** — "Demo · 5 artículos sueltos · precio" (GENERADO
   prueba).
3. Desde **lista de empaque** — "Demo · PL {n} · cajas" (VALIDADO, listo para
   generar; incluye dos listas para cubrir E1).
4. Desde **el módulo / familia** — "Demo · familia Calzado" (BORRADOR).
5. Uno con un problema pendiente (artículo sin dato obligatorio) para mostrar
   la corrección en el lugar.

Cada trabajo y cada uso deben tener en su nota/motivo una línea que diga
cómo se creó ("Creado desde la OC 4500… con el botón Imprimir etiquetas"),
para que el usuario lo vea como guía.

**Aceptación:** con base vacía y `SEED_DEMO=1`, el centro muestra la matriz
completa, 2 excepciones, 5 trabajos; generar el trabajo 3 produce un ZIP con
el número correcto de cajas; ejecutar la semilla dos veces no duplica nada.

---

## 13. Plan de pruebas

**Backend (pytest, SQLite y PostgreSQL con RLS):**

- E1–E12: una prueba por error (descritas en cada uno).
- Resolución: tabla de casos (nivel × contexto × condiciones × vigencia) con
  el resultado esperado; mismo artículo desde OC y desde artículos sueltos →
  mismo diseño (prueba explícita del principio 7.1.1).
- Conflictos: crear dos usos empatados → 409 con detalle.
- Simulación: `POST /usos/simular` no escribe (contar filas antes/después).
- Edición completa de un uso (cambiar diseño y destino) con `version`;
  versión vieja → 409.
- Varias etiquetas por registro: trabajo con COLG + PREC → 2 registros por
  artículo.
- Migración (opción A): base con reglas de cada `ambito` y modalidad →
  resultado e informe esperados; `downgrade` deja la base como estaba.
- Aislamiento por organización (RLS) en tablas nuevas.
- Caché: crear un uso sube la versión de `usos_diseno` y el GET siguiente con
  ETag vieja da 200 (seguir el patrón de `backend/tests/test_cambios.py`).
- Rendimiento: contador de consultas (patrón `event.listen(engine,
  "before_cursor_execute", …)` de `test_cambios.py`) para R1–R4.

**Frontend (Playwright, `frontend/e2e/`):**

- Ampliar `etiquetado.mjs`: matriz (editar celda, ver simulación, guardar),
  excepción, asistente de 3 pasos de punta a punta desde OC, lista de empaque
  y artículos, corrección en el lugar, confirmación al dar de baja.
- Usar `vigilarRed`/`quieto` (`e2e/quieto.mjs`), nunca `networkidle` (el
  canal SSE no deja la red quieta).
- Ancho móvil 390 px: sin desbordes en la matriz (desplazamiento horizontal
  solo dentro de la tabla).

---

## 14. Hoja de ruta por fases

| Fase | Contenido | Criterio de aceptación | Riesgo |
|---|---|---|---|
| **1. Errores** | E1–E12, F12 (reglas de empresa de límites), R2 | Pruebas nuevas en verde; suites `test_etiquetado_*` y `e2e/etiquetado.mjs` en verde | Bajo (sin cambio de modelo salvo columnas en `GeneracionItem`) |
| **2. Generación única + rendimiento** | Sección 8, R1, R3–R6 | Un solo productor de ZIP; contadores de consultas; rutas viejas con `Deprecation` | Medio |
| **3. Modelo genérico** | Tablas `tipos_etiqueta`, `usos_diseno`, historial; familia en producto; resolvedor nuevo; migración opción A con informe; adaptador `/asignaciones` | Pruebas de resolución y migración; mismo artículo = mismo diseño desde cualquier origen | Alto (migra datos: requiere D1) |
| **4. Interfaz nueva** | 3 secciones, matriz, excepciones, asistente de 3 pasos, asignar desde producto/OC/PL, primer uso guiado, lenguaje claro, confirmaciones | e2e nuevo en verde; sin claves técnicas visibles | Medio |
| **5. Semilla demo** | Sección 12 | Criterio de la sección 12 | Bajo |
| **6. Configurables** | F1–F11, F13–F16 (fuentes, simbologías GS1, formatos regionales, tamaños por empresa, SSCC) | Diseño en árabe/chino se dibuja; SSCC con dígito verificador correcto; formato `1.234,56` según diseño | Medio |
| **7. Limpieza** | Quitar columnas `modalidad`, `unidad`, `familia_id` del diseño, tabla `asignaciones_etiqueta`, `masivo.py` (salvo listados), rutas retiradas, catálogos de `etiquetas.js` | Solo con **autorización expresa** (borra archivos y datos) | — |

Cada fase en su propia rama/PR, sin fusionar sin aprobación.

---

## 15. Decisiones que debe tomar el dueño antes de implementar

| Id | Decisión | Recomendación |
|---|---|---|
| D1 | Cómo migrar las reglas existentes (A automática con informe / B convivencia / C de cero) | **A** |
| D2 | ¿Se aceptan los tres sujetos (ARTICULO, BULTO, DOCUMENTO) y las cinco cantidades? | Sí |
| D3 | Escalera de especificidad fija o editable por empresa | **Fija** en la primera versión |
| D4 | Orden de la escalera: ¿el contexto (destino/OC) manda sobre el nivel del artículo? | Sí (como hoy: OC 500 > ARTICULO 400) |
| D5 | ¿La familia pasa al producto, manteniendo SKU y grupo como herencia? | Sí: SKU → producto → grupo |
| D6 | Inner no divisible: repartir enteros (4,3,3) o bloquear | Repartir y avisar |
| D7 | Estados de lista de empaque que permiten etiquetas reales | Solo confirmada/enviada; borrador solo en prueba |
| D8 | ¿Se crea la entidad `bultos` con SSCC ahora o después? | Columnas en `GeneracionItem` en fase 1; tabla `bultos` + SSCC en fase 6 |
| D9 | ¿Se retiran las rutas sin uso (`/plan`, `/generaciones` POST, `/masivo` POST)? | Sí, con aviso de obsolescencia en fase 2 y retiro en fase 7 |

---

## 16. Resumen para la IA que implemente

1. Empieza por la **fase 1** (errores); no requiere decisiones de
   arquitectura salvo D6 y D7.
2. No empieces la **fase 3** sin respuesta a D1–D5.
3. El principio que no se negocia: **el artículo es el sujeto; el origen solo
   aporta contexto**. Un mismo SKU recibe el mismo diseño venga de una OC, de
   una lista de empaque o de una selección, salvo excepción explícita.
4. Todo lo nuevo: con `organizacion_id` y RLS, en el mecanismo de versiones
   de datos (caché/SSE), con concurrencia por `version`, baja lógica e
   historial, textos traducibles, formularios en Modal y vista previa con
   `.previa-etiqueta`.
5. Reporta cada fase con: archivos cambiados, migraciones, comandos de
   prueba ejecutados y su resultado real.
