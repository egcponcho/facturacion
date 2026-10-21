# Auditoría I · Integración del etiquetado con el resto del sistema

Repositorio `/home/user/facturacion`, commit `main 3b9d8b5`. Solo lectura. Rutas relativas a `backend/app/` salvo que se indique otra cosa.

**Cómo se verificó.**
- Lectura del flujo completo: `etiquetado/{datos,campos,generacion,trabajos,reglas,empaque_etiquetas}.py`, `empaque/{recetas,packing,empaques}.py`, `grupos/arbol.py`, `compras/{ordenes,flujo_oc}.py` y las pantallas que llaman al etiquetado.
- Dos pruebas propias en el directorio temporal, fuera del repositorio, contra la base SQLite de pruebas:
  - `scratchpad/auditoria_i/numeracion.py`: en memoria, sin base de datos.
  - `scratchpad/auditoria_i/test_integracion_auditoria.py`: con las fixtures del `conftest`. Pasaron 5 de 5; se muestran sus resultados.

**Relación con otros informes.** No repito lo que ya está en `L-logica-api.md`, `D-datos.md` y `C-codigo-pruebas.md`. Donde un hallazgo coincide, lo cito y agrego solo lo que esta área aporta.

---

## 1. Mapa de relaciones

### 1.1 Tabla

**Siglas de las columnas.** «Dir.» es la dirección del flujo:
- **L**: el etiquetado lee el dato en vivo.
- **E**: el etiquetado escribe en esa tabla.
- **I**: el etiquetado guarda una instantánea en `generacion_items.valores`.

**Clases de referencia:**
- **FK**: llave foránea real.
- **Blanda**: un id dentro de un JSON o un código en texto.

| Entidad (módulo) | Por dónde se une | Tipo | Dir. | Evidencia |
|---|---|---|---|---|
| `ordenes_compra` | `trabajo_etiqueta_registros.oc_id`, `generaciones_etiqueta.oc_id`, `usos_diseno.oc_id` | FK | L, I | `modelos/etiquetado.py:292,393,426`; `campos.py:394-410` |
| `ordenes_compra` | `trabajos_etiqueta.parametros.oc_ids` | Blanda (JSON) | L | `trabajos.py:154-160,232` |
| `posiciones_oc` | `registros.posicion_id`, `generacion_items.posicion_id` | FK sin ON DELETE | L, I | `modelos/etiquetado.py:394,473`; `campos.py:413-422` |
| `posiciones_oc` | `parametros.posiciones` | Blanda | L | `trabajos.py:230-239` |
| `posiciones_oc.casepack`, `inner_pack` | Valores y validación del empaque | L | L | `empaque_etiquetas.py:29,33`; `campos.py:418` |
| `posiciones_oc.receta_*` | **No se lee** | — | — | `grep receta etiquetado/` sin resultados |
| `articulos` | `registros.articulo_id`, `items.articulo_id`, `usos_diseno.articulo_id` | FK | L, I y **E** (`completar`) | `trabajos.py:436-481` → `maestros/catalogos.actualizar` |
| `productos` | `usos_diseno.producto_id`; los datos del producto | FK | L | `campos.py:358,371-373` |
| `prepacks`, `prepack_componentes` | `articulo.prepack` (vía `articulos.prepack_id`) | FK | L (curva viva) | `campos.py:387-391,498-520` |
| `posiciones_oc.prepack` | Código en texto | Blanda | L | `campos.py:418` |
| `grupos_articulos`, `grupos_producto` | Familia efectiva y categoría; `usos_diseno.grupo_id`, `generacion_items.grupo_id` | FK | L, I | `maestros.py:498-506`; `grupos/arbol.py:38-68`; `reglas.py:244-293` |
| `grupos_producto` | Condición `en_familia` | Blanda (por código) | L | `comun/condiciones.py:181-182` |
| `packing_lists` | `registros.pl_id`, `items.pl_id`, `generaciones.pl_id`; `parametros.pl_id` | FK y blanda | L | `generacion.py:138-151` |
| `grupos_cajas` | `generacion_items.grupo_cajas_id` | FK `SET NULL` | L, I | `modelos/etiquetado.py:471`. **No** en `trabajo_etiqueta_registros`: allí solo está en el texto de `clave` |
| `grupo_cajas_items` → `pl_lineas` → `factura_lineas` → `posiciones_oc` | Contenido del bulto | FK | L | `campos.py:470-486,555-560` |
| `factura_lineas` | Solo como puente a la posición | FK | L | `campos.py:474,505`. **No** usa sus columnas (instantánea de la factura, receta, aduana) |
| `facturas`, `embarques` | `bulto.factura`, `bulto.embarque`, `pl.*` | FK | L, I | `campos.py:541,571,585-589` |
| `tipos_empaque` | `usos_diseno.tipo_empaque_id`, `tipos_etiqueta_empaques`; prefijo y `cuenta_como` | FK | L | `campos.py:547,574-579`. **No** usa `identificador` (SSCC) |
| `sociedades`, `centros` | `oc.sociedad`, `oc.centro_destino` y país del centro (excepciones) | Blanda (código) | L | `campos.py:395-396`; `reglas.py:259-272` |
| `unidades` (lista) | `contable` | Blanda (código) | L | `generacion.py:116-135`; `maestros/unidades.py:52-55` |
| Recepción, lotes, transporte (fuera del embarque) | No hay relación | — | — | — |

### 1.2 Diagrama

```
                   grupos_producto (familia/categoría)   ◄─── reglas_empaque (empaque)
                         ▲  (familia_efectiva / categoria_de: motor común grupos/arbol.py)
 grupos_articulos ──┐    │
 productos ─────────┼──► articulos ──(prepack_id)──► prepacks ─► prepack_componentes
                    │       ▲  ▲ E: completar (upc, sku_prov, peso, unidad)
                    │       │  │
 ordenes_compra ──► posiciones_oc ──(casepack/inner, receta_* NO LEÍDA)
      ▲  │ (código texto)    ▲
      │  └► sociedades/centros/países
      │                      │ posicion_oc_id
      │              factura_lineas (instantánea factura + receta_foto: NO LEÍDAS) ◄─ facturas
      │                      ▲ factura_linea_id
      │              pl_lineas ◄─ grupo_cajas_items ─► grupos_cajas (árbol, tipos_empaque) ◄─ packing_lists ─► unidades_carga ─► embarques
      │                                                        ▲ SET NULL
 ETIQUETADO: trabajos_etiqueta(parametros JSON: oc_ids, posiciones, pl_id…) ─► trabajo_etiqueta_registros(oc, posición, artículo, pl; FK)
            └─► generaciones_etiqueta(oc, pl) ─► generacion_items(artículo, posición, pl, grupo_cajas SET NULL, grupo_id, valores=INSTANTÁNEA)
```

---

## 2. Origen de cada dato de la etiqueta

**Cuándo se lee y qué se guarda.** Todo se lee **en vivo** al validar y al generar (`datos.py:38-58`, `generacion.py:442-452`). Al generar, se guarda la **instantánea** solo de los campos que usa el diseño (`generacion.py:626-645`).

**Qué pasa si el maestro cambia después.** La respuesta es la misma para todos los datos de la tabla:
- **Registro pendiente:** `generar` vuelve a leer los datos y compara contra `revisado`, que guarda solo los campos del diseño, la versión y la cantidad (`trabajos.py:489-502`, `736-774`). Si algo cambió, responde 409 `datos_cambiaron`.
- **Registro generado:** queda con la instantánea. No hay invalidación ni aviso.

| Dato | Fuente maestra que usa el etiquetado | Observación |
|---|---|---|
| SKU | `articulos.sku`; en tablas y líneas, `posiciones_oc.codigo_articulo` | En la tabla del bulto y de la PL, el «sku» es el código de la línea de OC (`campos.py:491`) y no el del artículo |
| UPC | `articulos.upc` o `posiciones_oc.upc` (campo lógico con prioridad) | Desde la PL se lee la posición en vivo, no la copia de la factura (I-03) |
| Descripción, color, talla | `articulos.*`; en tablas, `posiciones_oc.*` | Igual que el UPC |
| Cantidad | Plan: `posiciones_oc.cantidad`. Empacado: `pl_lineas.cantidad` y `cantidad_por_caja` | Se suman unidades distintas (I-04) |
| Casepack, inner | `posiciones_oc.casepack/inner_pack` | Se ignoran la receta y el inner definido en la PL (I-07) |
| Bulto n de N y código | Calculado en `campos._unidades` (`527-580`) | No coincide con la numeración del documento PL (I-01, I-02) |
| OC, proveedor | `ordenes_compra.numero` y `proveedores.*` de la OC | En un bulto con varias OC queda vacío. Sin OC (artículos sueltos) no hay campo de proveedor del artículo (I-15) |
| Destino | `ordenes_compra.centro_destino` (en vivo) | La PL y la factura usan `factura_lineas.centro_destino` (instantánea, I-03) |
| País de origen | `linea.pais_origen`, `oc.pais_origen`, `producto.pais_origen` | Nunca el país corregido en la factura (`facturacion.py:107`) (I-03) |
| Peso | `grupos_cajas.peso_bruto_caja/peso_neto_caja` (los calcula el empaque) y `articulos.peso_unitario` | En vivo |
| Lote | **No existe** en el modelo. Solo puede venir de un campo propio (`*.extra`) | `etiqueta.numero_lote` es el número dentro del lote generado, no un lote de producción |
| Curva del prepack | `articulo.componentes` y `bulto.componentes`, desde `prepack_componentes` (en vivo) | La factura guarda `unidades_por_caja` como instantánea (I-16) |
| Familia y categoría | `grupos_producto` vía `familia_efectiva` / `arbol.categoria_de` | El ítem guarda la familia (`grupo_id`), no la categoría |
| SSCC | **No hay fuente**. `tipos_empaque.identificador` no se usa | I-15 |

---

## 3. Cantidades por escenario

Código: `generacion.py:198-317` (artículo y bulto) y `320-350` (documento).

| Escenario | Qué hace hoy | Problema |
|---|---|---|
| OC completa | Todas las posiciones no bloqueadas (`155-163`). Un registro por línea, según `alcance` | — |
| Posiciones elegidas | Solo las elegidas, también las bloqueadas (`157-158`) | Los **bultos y documentos no se filtran** por posiciones ni por familia (`289-290`, I-06) |
| Mismo artículo en varias posiciones | LINEA: un registro por línea. ARTICULO o PRODUCTO: los junta y suma `unidades` (`244-253`). UNA: 1 | Suma unidades distintas (I-04) |
| Artículo en varias OC | Una parte por OC (`trabajos.py:232-240`) | Nunca se juntan entre OC: «una por artículo» da una por OC (por diseño, no documentado) |
| Por artículo (UNA) | 1 por grupo | — |
| POR_UNIDAD | `int(unidades)`. Error si la unidad no es contable o la cantidad es fraccionaria (`116-135`) | Sin factor de conversión: DOC, JGO y CJ cuentan 1 por docena, juego o curva (I-04) |
| Cantidad manual | Solo con `MANUAL` (`265-266`) | Con UNA o POR_UNIDAD se ignora lo escrito. Ya informado (L-03). Lo reproduje: 24 → escrito 5 → sigue 24 |
| Artículos sueltos | Con POR_UNIDAD o MANUAL, la cantidad escrita. Con las demás, 1 (`259-260`) | `"2.5"` pasa a 0 y `"-5"` a −5 sin aviso (`trabajos.py:168-169`). Termina en el error `cantidad` |
| Cero o negativa | `g.cantidad < 1` da el error «Enter how many labels» (`443-444`) | Para una línea con cantidad 0, el mensaje pide escribir una cantidad que el servidor ignora (L-03) |
| Bulto de la PL | 1 por unidad física. Varios niveles sin repetir unidades (`279-288`) | — |
| Bulto desde la OC | Todas las cajas de primer nivel de **toda PL no cancelada** que tenga mercancía de la OC (`campos.py:592-604`) | Cajas duplicadas entre OC y PL en borrador como reales (L-04). Reproducido: 4 registros para 2 cajas, sin errores |
| PL inexistente | Aviso `tipo_no_aplica` | — |
| PL incompleta (líneas sin cajas) | Artículos: `pl_lineas.cantidad` completa. Bultos: solo lo encajado | No hay aviso de mercancía sin caja |
| PL con varias OC | Artículos: cada línea con su OC. Documento: una por OC o una por PL. Bulto: `oc_bulto` vacío | Sin excepciones de OC en bultos mixtos (L-11) |
| Prepack o kit | Se etiqueta **el prepack** (la curva, unidad CJ) y nunca sus componentes. La curva solo aparece como tabla (`articulo.componentes`, `bulto.componentes` = componente × paquetes) | Un colgante por par en un prepack de 12 pares da 1 etiqueta por curva (I-04) |
| Prepack sin componentes | Bulto: aviso `prepack_sin_componentes` (`empaque_etiquetas.py:20`). Artículo: tabla vacía | Bien |

---

## 4. Puntos de entrada

Todos crean un trabajo (`/etiquetas/trabajos/nuevo`) y usan el **mismo camino de servidor**: `trabajos._limpiar` → `_partes` → `generacion.planear`. No hay reglas distintas según de dónde se entra. Las diferencias están en los parámetros que manda cada pantalla.

| Pantalla (frontend/src) | Qué envía | Observación |
|---|---|---|
| `compras/vistas/OrdenView.vue:190,361` (botón «Etiquetas», `ResumenEtiquetas`) | `GET /etiquetas/resumen?origen=OC`, luego `?origen=OC&oc=…&tipos=…[&prueba=1]` (`ResumenEtiquetas.vue:29,41-42`) | El botón se ve en **todo estado salvo BORRADOR**, también en CANCELADA, RECHAZADA y EN_APROBACION. El servidor no revisa el estado (`datos.py:14-19`) (I-09) |
| `OrdenView.vue:29-30,301` («Etiquetas de estas líneas») | `origen=OC&oc&posiciones` | Los bultos y documentos no respetan las posiciones (I-06) |
| `compras/vistas/OrdenesView.vue:596` | `origen=OC&ocs=…` | Las líneas elegidas en la lista no se pasan |
| `ResumenEtiquetas.vue:56` («Diseño especial para esta OC») | `POST /etiquetas/usos` con contexto OC | Solo desde la OC |
| `empaque/vistas/PackingListView.vue:569,1167` | `origen=PACKING&pl=…` | Si la PL no está finalizada, propone prueba |
| `productos/vistas/ProductoView.vue` → `EtiquetadoProducto.vue:103,178` | `origen=ARTICULOS&articulos=<todas las tallas activas>` | Incluye los prepacks del producto, con cantidad 1 |
| `grupos/vistas/GruposProductoView.vue` | Edita los mismos nodos (familias y categorías) | Puede renombrar códigos (I-12) |
| `empaque/componentes/ReglasEmpaque.vue:12-14` | Reutiliza `EditorCondiciones` y los buscadores del etiquetado | Vocabulario de campos distinto (I-10) |
| `router.js:43-46` | Redirige `/etiquetas/masiva` y `/etiquetas/generar` | — |
| `etiquetado/vistas/ImprimirView.vue:73` | Trabajo vacío | — |

---

## 5. Hallazgos

Los hallazgos ya informados por otras áreas se citan al final, en «Coincidencias», y no se repiten aquí.

### I-01 · Alto · El código de caja impreso (C3, P1…) no coincide con el del documento de la lista de empaque [VERIFICADO, prueba en memoria]

**Problema.**
- El empaque numera por **prefijo**, en orden de lectura del árbol: cada raíz seguida de sus hijos. Sin prefijo, usa `codigo[:2]`, o «C» si el nodo no tiene tipo.
- El etiquetado numera por **`tipo_empaque_id`**, en **orden de id**. Sin prefijo, `bulto.codigo` queda vacío.

**Evidencia.**
- Empaque: `empaque/empaques.py:113-115` (prefijo) y `161-190` (numeración y orden del árbol).
- Etiquetado: `etiquetado/campos.py:536-540` (inicio por id), `547` y `576`.
- Prueba `numeracion.py`: un pallet (id 10) con 3 cajas dentro (id 12) y 2 cajas sueltas (id 11).

| Grupo | Documento PL | Etiqueta |
|---|---|---|
| id 11 (2 cajas sueltas) | C4–C5 | C1, C2 |
| id 12 (3 cajas en el pallet) | C1–C3 | C3–C5 |
| Tipo sin prefijo | BO1–BO2 | `None` |

**Impacto.** La caja física rotulada «C1» no es la «C1» del packing list ni la que se usa en la recepción o en los reclamos.

**Solución.** El etiquetado debe usar `empaques.numeracion()` y `empaques.prefijo()`: una sola función para los dos módulos.

**Riesgo.** Medio. Cambian los códigos de etiquetas futuras de PL ya armadas. Las generadas no cambian (tienen instantánea).

### I-02 · Medio · Tres definiciones de «bultos» [VERIFICADO, prueba en memoria]

**Problema.** El mismo PL de la prueba anterior da tres totales distintos:
- `empaques.totales()["bultos"]` = **7**: todo nodo `cuenta_como = BULTO`, a cualquier nivel (`empaques.py:224`).
- `pl.bultos` = **5**: solo raíces, incluido el pallet (`campos.py:583-589`).
- `bulto.total` = «n/5» en los exteriores, o el total por tipo (`campos.py:531-534`).

**Impacto.** «Caja 2 de 5» en la etiqueta frente a «7 bultos» en el documento y en el transporte.

**Solución.**
- Definir un único «bultos del documento» en `empaques`.
- Exponer `bulto.total_tipo` y `pl.bultos` desde allí.
- Documentarlo.

**Riesgo.** Bajo o medio: cambia lo que dicen las etiquetas nuevas.

### I-03 · Medio · Las etiquetas desde una lista de empaque leen la OC en vivo, mientras el documento PL y la factura usan su instantánea [VERIFICADO, lectura]

**Problema.**
- `_fila_linea` y `valores_linea` toman código, UPC, descripción, color, talla, unidad y país de `posiciones_oc` (`campos.py:413-422`, `489-495`).
- El documento PL usa la copia de `factura_lineas` (`empaque/packing.py:1283-1310`).
- `oc.centro_destino` es el de la cabecera de la OC en vivo; el empaque usa `factura_lineas.centro_destino` (`packing.py:200-206`).
- La importación del ERP sí cambia UPC, descripción y `centro_destino` en líneas ya facturadas. Solo trata como conflicto la cantidad y los campos clave (`compras/ordenes.py:864-873`, `473-480`).
- El país de origen corregido en la factura (`modelos/facturacion.py:107`) nunca llega a la etiqueta.

**Impacto.** El rótulo de la caja (UPC, país de origen, destino) puede contradecir la factura y el PL: un problema de aduana y de cumplimiento.

**Solución.**
- Desde PACKING (y para bultos), leer la línea de factura: un grupo `factura.*`/`linea_factura.*`, o que `linea.*` prefiera la copia de la factura.
- Agregar `factura_linea.pais_origen` y `centro_destino`.

**Riesgo.** Medio. Cambia valores impresos; hay que decidir la prioridad por campo lógico.

### I-04 · Alto · Unidades: prepacks y kits no se explotan, no hay conversión y se suman unidades distintas [VERIFICADO, prueba]

**Problema.**
- POR_UNIDAD cuenta en la unidad de la línea, sin factores (`generacion.py:116-135`; `core/listas.py:115-128`, la lista de unidades no tiene factor). Un prepack (CJ) da una etiqueta por curva y nunca por par o componente. Lo mismo DOC y JGO.
- Al juntar por ARTICULO o PRODUCTO se suman cantidades de unidades distintas, y `g.unidad` es la de la primera línea (`generacion.py:247-253`, `261-262`).
- La prueba, con una OC A de 24 PAR del sólido y 3 CJ del prepack del mismo producto, da:
  - registro PRODUCTO = **27** (LISTO, sin aviso);
  - registros LINEA = 24 y **3**.
- `bulto.unidades` suma igual pares y curvas (`campos.py:572`).

**Impacto.** Faltan colgantes (12 pares por curva dan 1 etiqueta) o el conteo es absurdo (27).

**Solución.**
1. Error `unidades_distintas` al juntar unidades diferentes.
2. Opción en el tipo o la regla «explotar prepack/kit en componentes»: un registro por componente con cantidad = componente × curvas, y los datos del componente.
3. Factor opcional en la lista de unidades (DOC = 12 UN).
4. `bulto.unidades` por unidad, o en unidades base.

**Riesgo.** Medio. Afecta conteos de trabajos existentes; conviene ponerlo detrás de una opción del tipo.

### I-05 · Medio · Bultos y documentos ignoran el filtro de líneas o familia del trabajo [VERIFICADO, lectura]

**Problema.**
- «Etiquetas de estas líneas» (`OrdenView.vue:29-30`) y el origen FAMILIA filtran solo las etiquetas de artículo (`generacion.py:155-163`).
- Los bultos salen de todas las cajas de la OC (`generacion.py:289-290`) y el documento de toda la OC (`320-346`).
- Los tipos por defecto de una OC incluyen los obligatorios de bulto y de documento (`trabajos.py:244-251`).

**Impacto.** Al imprimir «solo estas 2 líneas» salen también todas las etiquetas de caja de la OC.

**Solución.** Filtrar los bultos cuyo `por_posicion` cruce las posiciones o la familia elegidas. Para documentos, avisar o excluir cuando hay selección parcial.

**Riesgo.** Bajo.

### I-06 · Medio · La receta y el inner definidos en el PL no llegan al etiquetado [VERIFICADO, lectura]

**Problema.**
- El PL puede fijar el inner y la receta en `factura_lineas` cuando la OC no lo trae (`empaque/packing.py:555-581`). `posiciones_oc.inner_pack` queda vacío.
- El etiquetado lee solo la posición: `linea.inner_pack` sale vacío (`campos.py:418`) y `inner_incompleto` no se revisa (`empaque_etiquetas.py:33`).
- No existe ningún campo `receta.*`.
- Esto complementa C-D10 (`empaque_etiquetas` compara contra el casepack derivado y no contra la foto de N niveles).

**Impacto.** El inner impreso y las validaciones no coinciden con el árbol físico que armó «Empacar según la receta».

**Solución.**
- La validación y los campos de empaque deben leer `factura_lineas.receta_foto` (desde la PL) o `posiciones_oc.receta_foto` (desde la OC).
- Agregar `linea.receta`, `linea.receta_resumen` y las unidades por nivel.
- Es la fase 4 pendiente de `docs/EMPAQUE_RECETAS.md:148`.

**Riesgo.** Bajo o medio.

### I-07 · Alto · Propagación de cambios: nada se invalida ni se avisa a otros módulos; reempacar borra la identidad de lo impreso [VERIFICADO, prueba]

**Problema.**

*Registros pendientes:*
- El único control está en `generar`: compara los valores que usa el diseño (`trabajos.py:736-774`).
- No se detecta el cambio de un dato que no se imprime pero decide algo: la cantidad de la OC con alcance UNA, el contenido de una caja cuando el diseño no lo muestra, o un cambio de categoría que no cambia el diseño.

*Registros generados:*
- Ningún cambio en la OC (cantidad, posición), en la PL (reapertura, reempacado) o en el artículo deja marca en el trabajo ni en la generación.
- `reabrir_pl` no mira si hay etiquetas reales generadas (`empaque/packing.py:1199-1215`).

*Reempacado* (prueba `test_reempacar_despues_de_generar`):
- Tras quitar la caja y volver a crearla, los ítems impresos quedan con `grupo_cajas_id = NULL` y `posicion_id = NULL` (`modelos/etiquetado.py:471`, `SET NULL`).
- El trabajo nuevo genera las mismas 2 cajas **sin aviso** `ya_generada` (`generacion.py:559-560`, `572-573`).
- En SQLite, el id del grupo se reutilizó (`g14`): la clave del registro coincide con la del registro GENERADO anterior. Con PostgreSQL no pasaría.

**Impacto.**
- Etiquetas viejas pegadas en cajas que ya no existen o cambiaron, y reimpresión duplicada sin alerta.
- Imposible rastrear a qué caja corresponde lo impreso.

**Solución.**
1. Al reabrir o editar una PL (y al cambiar la cantidad o la receta de una posición) con generaciones reales, avisar y marcar esas generaciones como «posiblemente desactualizadas» (columna `desactualizada_en` o evento en el historial). Mostrarlo en el trabajo.
2. Guardar en el ítem una huella del contenido de la caja y la referencia lógica: número y código de la caja más el `pl_id`.
3. Hacer `_previas` por `(pl, código de caja)` y no solo por `grupo_cajas_id`.

**Riesgo.** Medio: toca empaque y compras (llamada a un servicio de etiquetado o evento).

### I-08 · Medio · OC no vigentes: el etiquetado no mira el estado de la OC [VERIFICADO, lectura y prueba de FK]

**Problema.**
- `datos.cargar_oc` (`datos.py:14-19`) y el botón de la OC (`OrdenView.vue:190`) permiten etiquetas de OC CANCELADA, RECHAZADA o EN_APROBACION.
- Al reenviar una OC rechazada, `flujo_oc.enviar` borra sus posiciones (`compras/flujo_oc.py:368-369`).
- La FK de `trabajo_etiqueta_registros`/`generacion_items.posicion_id` lo impide. Prueba: «IntegrityError FOREIGN KEY constraint failed».
- La causa del 409 engañoso ya está en D-10. Aquí agrego el origen: el etiquetado acepta OC en ese estado.

**Solución.**
- Rechazar en `cargar_oc` (para generar) las OC CANCELADA, BORRADOR y RECHAZADA. EN_APROBACION, solo en prueba.
- Ocultar el botón en esos estados.

**Riesgo.** Bajo.

### I-09 · Medio · Dos vocabularios de condiciones con la misma clave y otro significado (empaque frente a etiquetado) [VERIFICADO, lectura]

**Problema.**
- Las reglas de empaque usan `oc.proveedor` = **código** del proveedor (`empaque/recetas.py:613`). El etiquetado usa `oc.proveedor` = **nombre** (`campos.py:399`).
- El empaque tiene `oc.pais_destino`, `linea.marca`, `linea.grupo`, `linea.tipo`, que el etiquetado no tiene. El etiquetado resuelve el país con su propia caché (`reglas.py:259-264`, duplicada en `recetas.py:601-604`).
- El evaluador es común (`comun/condiciones.py`); el catálogo de datos no.

**Impacto.** La regla «proveedor = VANS» funciona en el empaque y nunca se cumple en una excepción de etiqueta (o al revés).

**Solución.** Un solo catálogo de valores del registro (`valores_registro`) para los dos módulos, con claves únicas: `oc.proveedor_codigo` frente a `oc.proveedor_nombre`.

**Riesgo.** Medio: hay que migrar las condiciones guardadas.

### I-10 · Bajo-Medio · Una misma categoría puede resolverse distinto en el empaque y en el etiquetado [VERIFICADO, lectura]

**Problema.**
- Las condiciones de categoría se validan contra **todo** el catálogo, incluidos `oc.*` y `linea.*`: `grupos/arbol.py:205-209` → `reglas.validar_condiciones` (`reglas.py:79-92`).
- La interfaz ofrece solo `articulo.*` y `producto.*` (`CategoriasFamilia.vue:44-45`, `arbol.campos` `156-164`).
- El empaque evalúa la categoría con `valores_articulo` (`recetas.py:592-599`). El etiquetado la evalúa con los valores del primer registro, que incluyen la OC, y la guarda en caché por artículo (L-18).

**Impacto.** Una categoría creada por la API con condiciones de OC da una receta y una etiqueta de categorías distintas para el mismo artículo.

**Solución.** Validar en el servidor por grupo (`articulo.` y `producto.`).

**Riesgo.** Bajo.

### I-11 · Bajo-Medio · Renombrar un código en «Grupos de producto» rompe en silencio las condiciones `en_familia` [VERIFICADO, lectura]

**Problema.**
- `arbol.actualizar` permite cambiar `codigo` (`grupos/arbol.py:181-187`, `237-250`).
- `en_familia` compara el código como texto contra `articulo.familia_ruta` (`comun/condiciones.py:181-182`).
- Nada revisa las reglas que lo usan.

**Solución.**
- Guardar el id del nodo en la condición, o bloquear o propagar el cambio de código.
- `arbol.usos` debe contar esas condiciones.

**Riesgo.** Bajo.

### I-12 · Bajo · «Caja mixta» se define distinto en cada módulo [VERIFICADO, lectura]

**Problema.**
- El empaque muestra «Standard / Consolidated label» según el número de **líneas de factura** de la caja y su destino (`packing.py:200-206`; `PackingListView.vue:757-763`).
- El etiquetado usa `bulto.mixto` según el número de **artículos** distintos (`campos.py:557,575`).
- Una caja con el mismo SKU de dos OC es «Consolidada» en el PL y «no mixta» en la etiqueta.

**Solución.** Una sola definición en `empaques`, con las dos dimensiones (`mixto_articulos`, `mixto_oc`).

**Riesgo.** Bajo.

### I-13 · Bajo · Dependencias cruzadas e invertidas [VERIFICADO, lectura]

**Problema.**
- `empaque/recetas.py:595` importa `etiquetado.campos.valores_articulo`.
- `grupos/arbol.py:159,175` importa `etiquetado.campos` y `etiquetado.reglas`, mientras el etiquetado importa `grupos.arbol` (`reglas.py:186`, `familias.py`, `categorias.py`).
- Es un ciclo resuelto con imports dentro de funciones. Los módulos «comunes» (grupos, empaque) dependen del etiquetado, que se puede apagar.
- Complementa D-23 y C-D04.

**Solución.** Mover `valores_articulo`, el catálogo de campos y `validar_condiciones` a `comun/` (o a `grupos`) y que el etiquetado los consuma.

**Riesgo.** Bajo.

### I-14 · Bajo · `completar` escribe `articulos.unidad` desde el etiquetado [VERIFICADO, lectura]

**Problema.**
- `COMPLETABLES` incluye `articulo.unidad` (`trabajos.py:436-437`).
- Las etiquetas desde una OC usan `posiciones_oc.unidad`. Cambiar la unidad del maestro no corrige el caso que la pide y puede descuadrar el maestro frente a las OC abiertas en otra unidad.

**Solución.** Quitar `unidad` de `COMPLETABLES`, o exigir que coincida con las líneas del trabajo.

**Riesgo.** Bajo.

### I-15 · Bajo-Medio · Datos que una etiqueta logística necesita y el sistema no da [VERIFICADO, lectura]

**Faltan:**
- **SSCC:** `tipos_empaque.identificador = SSCC` no se usa en el etiquetado (`grep identificador etiquetado/` sin resultados). `etiqueta.serie` no calcula el dígito verificador, y `render.py:253-258` rechaza un SSCC sin él. El documento dice que se cubre «un SSCC por unidad» (`docs/ETIQUETADO.md` §11).
- **Lote de producción:** no existe.
- **Proveedor del artículo sin OC:** no hay campo, aunque la excepción PROVEEDOR sí lo usa (`reglas.py:269`).

**Solución.**
- Fuente `bulto.sscc`: prefijo GS1 de la empresa + serie + dígito, guardado por unidad.
- Campo `articulo.proveedor*`.

**Riesgo.** Bajo.

### I-16 · Bajo · La curva del prepack se lee en vivo; la factura guarda su total [VERIFICADO, lectura]

**Problema.**
- `bulto.componentes` y `articulo.componentes` usan `prepack_componentes` actuales (`campos.py:387-391`, `507-513`).
- `factura_lineas.unidades_por_caja` es la instantánea del total al facturar.
- Si cambia la curva, la tabla de la caja difiere de los pares facturados, sin aviso.

**Solución.** Avisar `curva_distinta` cuando la suma de la curva ≠ `unidades_por_caja` de la línea.

**Riesgo.** Bajo.

### I-17 · Bajo · El origen técnico de las familias está desactualizado [VERIFICADO, lectura]

**Problema.** `datos_campos.py:51-52,83` dice `familias_etiquetado.*`. Desde 0081 es `grupos_producto`. Se muestra en «Nombres y origen de los campos».

**Solución.** Actualizar el texto.

**Riesgo.** Nulo.

### Coincidencias con otros informes, confirmadas en `3b9d8b5`

| Informe | Qué confirma esta auditoría |
|---|---|
| **L-03** (cantidad escrita ignorada) | Reproducido con POR_UNIDAD desde la OC: 24 → escrito 5 → 24 |
| **L-04 / GN-01** (cajas de la PL consolidada duplicadas; PL en borrador da reales) | Reproducido: trabajo de OC A+B → `oc15:…-u1/u2` y `oc16:…-u1/u2` para 2 cajas, todos LISTO y sin `pl_sin_finalizar`. Desde PACKING, la misma PL da el error. Además, `resumen` informa `etiquetas_reales: True` siempre para una OC (`generacion.py:938`) |
| **L-12 / D-12** | Los lotes anulados siguen contando en `_previas`, `resumen` y `ordenes_familia` |
| **D-10** | Reenviar una OC rechazada con etiquetas da `IntegrityError` (la causa de raíz está en I-08) |
| **GN-10** | Suma de unidades distintas (ampliado a prepacks en I-04) |
| **L-18 / MN-10** | Caché de categoría (su efecto en el empaque está en I-10) |

**Prioridad sugerida:**
1. I-01, I-04 y I-07: lo que se pega en la caja.
2. I-03 e I-05.
3. I-06, I-08 e I-09.
4. El resto.
