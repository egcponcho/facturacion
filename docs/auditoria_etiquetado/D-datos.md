# D — Modelo de datos, integridad y migraciones del etiquetado

**Commit:** main `3b9d8b5`. **Modo:** solo lectura.

**Método:**
- Lectura completa de `modelos/etiquetado.py`, `grupos.py`, `referencias.py`, `restricciones.py`, `core/organizacion.py`, `instalacion/esquema.py` y de las migraciones 0070–0082. De `maestros.py`, `productos.py`, `compras.py`, `empaque.py`, `facturacion.py` y `empresa.py` leí solo las partes que tocan el etiquetado.
- Esquema real: SQLite migrado a `head` (0082) en `scratchpad/auditoria/tmp/m.db`.
- `alembic check`: «No new upgrade operations detected».
- Script contra `PRAGMA foreign_key_list` para comprobar las llaves de coherencia (`_org`) y los `ON DELETE`.
- `EXPLAIN QUERY PLAN` de la consulta de «ya impreso».

**Límites:** PostgreSQL no se pudo levantar (permisos del directorio). La RLS está verificada leyendo las migraciones, no ejecutándola.

**Etiquetas:** [VERIFICADO] = comprobado en código o esquema · [SOSPECHA] = probable, sin prueba.

---

## 1. Diagrama entidad-relación (texto)

```
organizaciones 1─* (todas las tablas: organizacion_id + RLS)

tipos_etiqueta ─1─* plantillas_etiqueta ─1─* versiones_plantilla
     │  └─*─* tipos_empaque  (tipos_etiqueta_empaques, CASCADE en ambos lados; «sin filas = todos»)
     │        plantillas_etiqueta.version_vigente_id ──> versiones_plantilla   (sin _org)
     │        plantillas_etiqueta.origen_id ──> plantillas_etiqueta            (sin _org)
     │        versiones_plantilla.basada_en_id ──> versiones_plantilla         (sin _org)
     │
     └─1─* usos_diseno (regla) ──> plantilla? · grupos_producto? · productos? · articulos? · tipos_empaque? · ordenes_compra?
                 contexto_valores JSON [códigos de centro, país o sociedad | ids de proveedor]   ← referencia blanda
                 condiciones JSON [{campo, op, valor}] (en_familia = CÓDIGO del grupo)        ← referencia blanda
                 [congeladas] familia_id ──> familias_etiquetado · categoria_id ──> categorias_etiquetado

grupos_producto (FAMILIA | CATEGORIA, padre_id ──> sí misma)
     <── articulos.grupo_producto_id · grupos_articulos.grupo_producto_id
     <── productos.grupo_producto_id (familia O categoría a mano)
     <── usos_diseno.grupo_id · reglas_empaque.grupo_id · generacion_items.grupo_id
     legado_familia_id / legado_categoria_id (enteros sin FK, para el downgrade de 0081)

campos_etiqueta (campos lógicos; el diseño los usa como «logico.<clave>» dentro del JSON)  ← referencia blanda

trabajos_etiqueta (parametros JSON: oc_ids, articulos, pl_id, elegidas, familia_id, tipos…)  ← referencias blandas
   └─1─* trabajo_etiqueta_registros (CASCADE)
            ──> ordenes_compra · posiciones_oc · articulos · packing_lists · plantilla · versión · tipo
            ──> usos_diseno (SET NULL) · generaciones_etiqueta (SET NULL)
            identidad del bulto solo en `clave` (texto)

generaciones_etiqueta (cabecera: oc_id?, pl_id?, trabajo_id?, lote, parametros {hoja, dpi, logo…},
                       impresion JSON, reimpresiones JSON, anulada_*)
   └─1─* generacion_items (CASCADE)
            ──> plantilla · version · tipo · articulo · posicion_oc · packing_list · grupos_cajas (SET NULL) · grupos_producto
            ──> trabajo_etiqueta_registros (UNIQUE, SET NULL)
            valores JSON (instantánea + _procedencia + _serie)
            [congelada] familia_id ──> familias_etiquetado
            (sin oc_id, sin uso_id)

recetas_empaque ─1─* receta_niveles (CASCADE) ──> tipos_empaque
reglas_empaque ──> receta · grupo · producto · articulo
posiciones_oc / factura_lineas: receta_id + receta_foto (instantánea) + casepack / inner_pack (duplicado)

[congeladas] familias_etiquetado (padre_id) ─1─* categorias_etiquetado
[eliminada en 0076] asignaciones_etiqueta
```

---

## 2. Inventario de tablas del etiquetado

**Notas comunes a todas las filas:**
- Todas tienen `organizacion_id` (FK + índice), RLS (`rls()` en su migración) y FK de coherencia `_org` hacia cada padre de la organización. El script no encontró ninguna `_org` faltante en `COHERENCIA`.
- Excepción: tres FK internas sin `_org` (D-07).
- Las FK a `usuarios` no llevan `_org`, a propósito (un usuario de plataforma puede actuar en varias organizaciones).

| Tabla (migración, RLS) | Propósito | PK / únicos | FK (→ padre; ON DELETE) | CHECK | Índices (observación) | ¿Se usa? |
|---|---|---|---|---|---|---|
| `tipos_etiqueta` (0076, RLS 0076:341) | Clase de etiqueta: sujeto, cantidad, alcance | id; (org, codigo); (id, org) | usuarios | sujeto, cantidad y alcance, cada uno solo enumerado (no se cruzan con el sujeto) | org (redundante con uq) | Sí: tipos.py, reglas, generacion, trabajos, usos |
| `tipos_etiqueta_empaques` (0079, RLS) | M:N tipo de etiqueta ↔ tipo de empaque | PK (tipo_etiqueta_id, tipo_empaque_id) | ambas FK **CASCADE**, simples y `_org` | — | tipo_empaque_id, org | Sí: tipos.py:141-153, generacion |
| `plantillas_etiqueta` (0070, RLS) | Diseño con nombre estable | id; (org, nombre); (id, org) | tipo (+`_org`); version_vigente_id, origen_id **sin `_org`** | estado ∈ ACTIVA, ARCHIVADA | org (redundante), estado (baja selectividad), tipo | Sí |
| `versiones_plantilla` (0070, RLS) | Versión numerada; la aprobada no se toca | id; (plantilla_id, numero); (id, org) | plantilla **CASCADE** (+`_org`); basada_en_id **sin `_org`** | estado; medidas > 0 | plantilla_id (redundante con uq), estado (baja selectividad) | Sí |
| `usos_diseno` (0076/0080/0081, RLS) | Regla: celda (tipo, nivel, destino) + excepción | id; (id, org); parcial único (org, celda) WHERE normal y vigente | tipo, plantilla, grupo, producto, articulo, tipo_empaque, oc (todas con `_org`); familia_id y categoria_id congeladas (con `_org`) | nivel, contexto, destino, accion, plantilla, alcance, cantidad, oc, vigencia, normal sin vigencia | 13 índices; `familia_id` y `categoria_id` inútiles | Sí: reglas.py:205-229, usos.py, arbol |
| `campos_etiqueta` (0073, RLS) | Campo lógico con fuentes en orden | id; (org, clave) | usuarios | tipo, politica (desde restricciones.py) | org (redundante) | Sí: campos_logicos.py |
| `trabajos_etiqueta` (0073/0074, RLS) | Asistente, borrador y ejecución durable | id; (id, org) | usuarios | origen, estado, total, progreso, paso ≥ 0 | estado, creado_por, creado_en, arriendo_hasta | Sí: trabajos.py |
| `trabajo_etiqueta_registros` (0073/0076/0077, RLS) | Registro validado (grupo de etiquetas) | id; (trabajo_id, clave); (id, org) | trabajo **CASCADE**; oc, posicion, articulo, pl, plantilla, version, tipo; uso **SET NULL**; generacion **SET NULL** (todas con `_org`) | estado; cantidad ≥ 0 | 12; trabajo_id redundante con uq; estado inútil | Sí |
| `generaciones_etiqueta` (0070…0078, RLS) | Lote generado (cabecera) | id; (id, org) | oc, pl, trabajo (con `_org`); usuarios | formato, estado, total ≥ 0, descargas ≥ 0, anulada ⇔ motivo | creada_en, creada_por, estado, oc, pl, lote, trabajo | Sí |
| `generacion_items` (0070…0081, RLS) | Grupo de etiquetas + instantánea | id; **UNIQUE trabajo_registro_id** | generacion **CASCADE**; plantilla, version, tipo, articulo, posicion, pl, grupo (todas con `_org`); grupo_cajas **SET NULL**; trabajo_registro **SET NULL**; familia_id congelada | cantidad ≥ 1 | 11; `familia_id` inútil | Sí |
| `grupos_producto` (0081, RLS) | Árbol compartido: familias y categorías | id; (org, codigo); (id, org) | padre (+`_org`) | clase; una categoría tiene padre | org (redundante), padre | Sí: arbol.py, familias.py, categorias.py, reglas, empaque |
| `familias_etiquetado` (0070, RLS) | **Congelada** desde 0081 | id; (org, codigo); (id, org) | padre (+`_org`) | — | org, padre | No: solo el modelo `*Anterior`, la FK, el downgrade de 0081 y tests de migración |
| `categorias_etiquetado` (0080, RLS) | **Congelada** desde 0081 | id; (org, codigo); (id, org) | familia (+`_org`) | — | org, familia | No: igual que la anterior |
| `recetas_empaque` / `receta_niveles` / `reglas_empaque` (0082, RLS) | Recetas de N niveles y reglas de empaque | uq por org; (receta_id, orden) | niveles **CASCADE** a la receta; reglas → grupo, producto, articulo (con `_org`) | cantidad ≥ 1, orden ≥ 1, destino único, vigencia | `posiciones_oc.receta_regla_id` es FK sin índice | Sí: empaque/recetas.py |

**Uso dinámico revisado:**
- `core/cambios.py` detecta las tablas por el SQL que llega al motor; no tiene nombres de tabla fijos.
- `instalacion/demo_etiquetado.py` siembra a través de los servicios, así que escribe en `grupos_producto`, nunca en las tablas congeladas.
- Ni reportes ni plataforma referencian las tablas del etiquetado.
- No hay borrado de organizaciones.
- Fuera de las migraciones, las tablas congeladas aparecen solo en `referencias.py:72-73,76,86,89-91,97`, en `modelos/__init__.py:76,78,150,152` y en dos tests de ida y vuelta de migraciones (`test_grupos_producto.py:131-218` y `test_etiquetado_trabajos.py:307-371`).

---

## 3. Qué consultar en vivo, qué guardar como referencia (FK) y qué como instantánea

| Información | Debería ser | Hoy | Brecha |
|---|---|---|---|
| Datos maestros para una etiqueta nueva (artículo, producto, OC, línea, PL, bulto, organización) | Vivo | Vivo, leído al planear (`datos.py:39-58`) | — |
| Reglas, tipos, árbol de grupos, campos lógicos y receta al planear | Vivo | Vivo | — |
| Qué se generó: lote → versión, plantilla, tipo, artículo, línea, PL, bulto, registro del trabajo | FK | FK | Falta `generacion_items.oc_id` (D-02); `grupo_cajas_id` se pierde con SET NULL (D-04) |
| Por qué ese diseño: regla, su versión, categoría o grupo que decidió | FK + versión | Solo `motivo` en texto (en inglés) | D-06 |
| Quién, cuándo, anulación | FK y columnas | `creada_*`, `anulada_*` | Falta un CHECK de `anulada_por` (D-20) |
| Impresión y reimpresiones | Filas con FK a usuario | JSON: `impresion` se sobrescribe; `reimpresiones.por` es un id sin FK | D-16 |
| Valores impresos | Instantánea | `generacion_items.valores` (con `_serie` y `_procedencia` mezclados) | Bien. Expuestos sin filtro de datos reservados (D-01) |
| Diseño usado | Referencia inmutable (versión aprobada) | `version_id`; la inmutabilidad solo la garantiza el código | Los lotes PRUEBA apuntan a borradores editables (D-05) |
| Formato de cada campo (texto, número, fecha) | Instantánea | Vivo: `campos.tipos(db)` (`generacion.py:700`) | D-05 |
| Imágenes del diseño y logo | Referencia inmutable (sha) | Imagen: `adjunto_id` vivo dentro del JSON (`generacion.py:701`). Logo: data URL copiado en cada lote (`generacion.py:619-620`) | D-05, D-17 |
| Hoja, dpi, serie | Instantánea | `parametros` y `valores._serie` | — |
| Familia al generar | FK al nodo | `generacion_items.grupo_id` (FK; el nombre se lee vivo) | Aceptable |
| Receta de la línea | FK + instantánea | `receta_id` + `receta_foto` | `casepack` e `inner_pack` duplicados (D-13) |
| Datos del artículo en la línea de OC o de factura | Instantánea del documento | Copiados (`facturacion.py:84-104`, `compras.py:126-143`) | Intencional. Conservar |
| Caches (`trabajos.total`, `progreso`, `resumen.ejecuciones`, `generaciones.total`) | Derivables | Guardados | Aceptable. `resumen.ejecuciones` repite lo de `generaciones.trabajo_id` |
| Destinatarios de una excepción (centro, país, sociedad, proveedor) | FK | Códigos o ids en JSON | D-08 |

---

## 4. Elementos obsoletos o congelados

| Elemento | Dependencias verificadas | Decisión |
|---|---|---|
| Tabla `familias_etiquetado` | Modelo `FamiliaEtiquetadoAnterior` (`etiquetado.py:94-109`). FK desde `articulos`, `grupos_articulos`, `productos`, `usos_diseno`, `generacion_items` y `categorias_etiquetado`, cada una con su `_org`. `COHERENCIA` (`referencias.py`). RLS. Downgrade de 0081 (`_devolver`, `_celdas_anteriores`). Tests de ida y vuelta. Datos copiados 1:1 en `grupos_producto.legado_familia_id`. Nada la lee ni la escribe en `app/` | **Eliminar** en la fase 5 |
| Tabla `categorias_etiquetado` | Igual. FK desde `productos.categoria_etiquetado_id` y `usos_diseno.categoria_id` | **Eliminar** en la fase 5 |
| Columnas congeladas | `articulos.familia_etiquetado_id`, `grupos_articulos.familia_etiquetado_id`, `productos.familia_etiquetado_id`, `productos.categoria_etiquetado_id`, `usos_diseno.familia_id`, `usos_diseno.categoria_id` y `generacion_items.familia_id`. En el ORM se mapean como `*_anterior_id`; en filas nuevas siempre quedan NULL. Ojo: el nombre físico `familia_etiquetado_id` coincide con el *synonym* hacia `grupo_producto_id` (`maestros.py:419,494`). No encontré SQL de texto que use el nombre físico | **Eliminar** junto con sus 7 índices y 9 FK `_org`. Conservar los synonyms y hybrids (contrato de la API) hasta renombrarlos |
| `grupos_producto.legado_familia_id` / `legado_categoria_id` | Solo los usa el downgrade de 0081 | **Conservar** hasta retirar la ruta de downgrade; después, eliminar |
| `asignaciones_etiqueta` | Borrada en 0076. Queda en el downgrade de 0076 y en `test_etiquetado_trabajos.py:307-371` | Ya eliminada. Conservar las migraciones |
| `plantillas.modalidad`, `unidad`, `familia_id`; `generaciones.modalidad`, `unidad`; `campos.modalidades`; `registros.regla_id` | Quitadas en 0076. Su downgrade las reconstruye con pérdida (`0076:453-574`) | Ya eliminadas |
| `historial` con entidad `uso_diseno` y acción `migrar` | Informe de conversión de 0076. Lo lee `usos.py:181-182` | **Conservar**. Además, el downgrade de 0076 borra todo el historial de `uso_diseno` (D-21) |
| `casepack` e `inner_pack` en `posiciones_oc` y `factura_lineas` | Leídos por el etiquetado (`empaque_etiquetas.py:28-34`, `campos.py:413-421`), el PL, los documentos y la importación ERP. Se sincronizan desde la receta (`recetas.py:660-667`) | **Conservar**. Primero hacer que el etiquetado lea la receta (D-13) |
| `plantilla_id` en `generacion_items` y en `trabajo_etiqueta_registros` | Derivable de `version_id`, pero lo usa el filtro del historial (`generacion.py:851-853`) | **Refactorizar** a FK compuesta (D-07), no borrar |

**Estrategia segura para la fase 5 (migración nueva, p. ej. 0083):**
1. Verificar antes de borrar:
   - Cada fila de las tablas congeladas tiene su nodo (`legado_*`).
   - No hay valores congelados distintos de los mapeados.
   - Usar `sin_violaciones` para detener la migración con un informe si algo no cuadra.
2. En `batch_alter_table`, quitar en este orden: las FK `_org`, las FK simples, los índices y las 7 columnas. Después, `DROP TABLE categorias_etiquetado` y luego `familias_etiquetado` (las políticas RLS caen con la tabla).
3. En el mismo commit, actualizar el código:
   - Quitar las entradas de `COHERENCIA` y los modelos `*Anterior`.
   - Ajustar `test_integridad_bd`.
4. Downgrade reconstructivo:
   - Recrear las tablas y columnas.
   - Repoblarlas desde `grupos_producto` reutilizando los ids `legado_*`; los nodos nuevos reciben ids nuevos, como en `0081._devolver`.
   - Los tests de ida y vuelta (0075↔head y 0080↔head) obligan a que esta ruta exista.
5. Hacer un respaldo antes de aplicarla en producción.
6. `legado_*` se elimina en un corte posterior, cuando se acepte no volver a 0080.

---

## 5. Hallazgos

### D-01 · Alto · Datos reservados expuestos por las rutas de etiquetado y en las instantáneas [VERIFICADO]

**Problema:** las rutas `/api/etiquetas/*` no están en `visibilidad.RUTAS`, así que para ellas se ejecuta `visibilidad.usar(None)` y ningún grupo de datos queda oculto. En consecuencia:
- El catálogo y `valores_linea` incluyen `linea.precio` aunque el rol del usuario oculte los precios.
- `GET /etiquetas/generaciones/{id}` devuelve `valores` completos.
- El proveedor ve los lotes de sus OC creados por usuarios internos (`_alcance`), con campos como `oc.fecha_tienda` («fechas_internas», oculto al proveedor por defecto) o `linea.precio`.
- El filtro global no serviría aunque se aplicara: compara claves exactas (`precio`), y las de la instantánea llevan prefijo (`linea.precio`).
- Solo `linea.precio` está marcado como dato reservado (`dato=`). `oc.sociedad`, `oc.centro*`, `oc.fecha_tienda` y `linea.almacen` no lo están.
- La ejecución en segundo plano sí aplica la visibilidad del usuario (`trabajos.py:881`), así que lo revisado y lo generado pueden diferir.

No hay fuga entre proveedores en los valores: cada fuente pertenece a un solo proveedor.

**Evidencia:**
- `acceso/visibilidad.py:65,69-71,79-87,126-133`
- `web/dependencias.py:70`
- `etiquetado/campos.py:151,239-247,394-406,413-421`
- `generacion.py:790-795,824-829`
- `api.py:593-596`

**Solución:**
- Marcar `dato` en todos los campos de grupos reservados.
- Filtrar `valores`, `revisado` y el `lote.json` del ZIP con el catálogo del usuario al leerlos.
- Aplicar `visibilidad.usar(user)` también en `/api/etiquetas`.
- Definir la política: «lo impreso» frente a «lo mostrado en pantalla».

**Riesgo de modificación:** medio. Un diseño que use esos campos imprimiría vacío para ciertos roles.

**Clasificación:** refactorizar.

### D-02 · Medio · `generacion_items` no guarda la OC del ítem [VERIFICADO]

**Problema:**
- Desde una lista de empaque con varias OC, la cabecera queda con `oc_id` NULL (`generacion.py:377`).
- Las etiquetas de documento por OC (`generacion.py:339-346`) solo dejan el número de la OC en `referencia` y en `valores`.
- `_previas` arma la clave `("D", tipo, None, pl)` y mezcla todas las OC de la lista (`generacion.py:566-567,574-575`).
- El historial no se puede filtrar por OC.
- El registro del trabajo sí tiene `oc_id`, pero el ítem lo pierde si el vínculo se anula (D-03).

**Solución:**
- Agregar `generacion_items.oc_id`: FK, `_org` e índice (org, oc_id).
- Rellenarlo desde `trabajo_etiqueta_registros.oc_id` o, si no hay registro, desde la cabecera.

**Riesgo:** bajo (es aditivo).

**Clasificación:** refactorizar.

### D-03 · Medio · Anular rompe el vínculo ítem ↔ registro [VERIFICADO]

**Problema:**
- `UNIQUE(trabajo_registro_id)` impone una relación 1:1 donde en realidad hay 1:N en el tiempo (original anulado + regenerado).
- `anular` pone `trabajo_registro_id = NULL` en los ítems anulados (`trabajos.py:1161-1167`), así que se pierde de qué registro salió lo anulado.
- Al volver a revisar, `uso_id` y `version_id` del registro se sobrescriben (`trabajos.py:552-575`).

**Solución:**
- Mantener la FK y reemplazar el UNIQUE por un índice único parcial `WHERE NOT anulado`, con una columna `anulado` o `anulada_en` en el ítem. PostgreSQL y SQLite admiten índices parciales.
- Dejar de anular el vínculo en `anular`.

**Riesgo:** medio (cambia una restricción y la lógica de anulación).

**Clasificación:** refactorizar.

### D-04 · Medio · La identidad del bulto no es estable [VERIFICADO]

**Problema:**
- `generacion_items.grupo_cajas_id` tiene `ON DELETE SET NULL`.
- Rearmar o editar el PL borra los `grupos_cajas`: `packing.py:40-62,517`, `estructura_pl.py:143`, `facturas.py:463`.
- Resultado: el historial pierde qué bulto físico era, y `_previas` deja de detectar la reimpresión.
- `trabajo_etiqueta_registros` guarda la identidad del bulto solo en `clave` (texto).

**Solución:**
- Bulto persistente: tabla de bultos con serial o SSCC, o un código estable por unidad.
- Mientras tanto, impedir rearmar un PL con etiquetas reales vigentes sin anularlas antes.
- Agregar `grupo_cajas_id` y `bulto_indice` al registro.

**Riesgo:** medio.

**Clasificación:** refactorizar.

### D-05 · Medio · La «reproducción exacta» depende de datos vivos o mutables [VERIFICADO]

**Problema:** `_lienzos` vuelve a dibujar el lote leyendo datos actuales:
1. Formatos: `campos.tipos(db)` es el catálogo vivo (`generacion.py:700`; `campos_logicos.py:35-39` solo trae los activos). Desactivar o cambiar el tipo de un campo lógico cambia el formato de lotes viejos (`render.py:172,490`).
2. Imágenes: `imagen_adjunta` lee el adjunto vivo por id (`plantillas.py:250-262`). Se acepta cualquier adjunto de la organización (`:243`), incluidas fotos de producto que `adjuntos.quitar` puede borrar.
3. Lotes PRUEBA: usan versiones BORRADOR (`generacion.py:613`) que `guardar_diseno` sigue editando (`plantillas.py:86,362-382`).
4. Versión aprobada: su inmutabilidad solo la garantiza el código; la base no la impide.
5. No se registra la versión del motor de dibujo.

El `sha256` detecta la diferencia, pero no permite recuperar el original.

**Solución:**
- Guardar en el lote los tipos de los campos usados.
- Copiar las imágenes a adjuntos inmutables referenciados por sha, con una tabla `versiones_plantilla_imagenes`.
- Prohibir editar una versión referenciada por algún ítem (o clonarla).
- Guardar `diseno_sha256` al aprobar, más un trigger de PostgreSQL que impida `UPDATE` de `diseno` cuando el estado sea APROBADA o ARCHIVADA.
- Guardar la versión del motor en `parametros`.

**Riesgo:** bajo a medio.

**Clasificación:** refactorizar.

### D-06 · Medio · El «por qué» de cada etiqueta no queda estructurado [VERIFICADO]

**Problema:**
- `generacion_items` no tiene `uso_id`, ni la versión del uso, ni la categoría reconocida; solo `motivo` en texto en inglés (`generacion.py:639-647`).
- Las reglas se editan en el lugar (`version` + historial), así que hoy no se puede reconstruir qué regla decidió un ítem.

**Solución:** agregar `uso_id` (FK RESTRICT; los usos nunca se borran), `uso_version` y `grupo_regla_id`.

**Riesgo:** bajo.

**Clasificación:** refactorizar.

### D-07 · Medio · Integridad interna diseño / versión / tipo solo en código [VERIFICADO]

**Problema:**
- (a) Tres FK internas sin `_org` ni comprobación de pertenencia (las únicas que encontró el script):
  - `plantillas_etiqueta.version_vigente_id` puede apuntar a una versión de otra plantilla;
  - `origen_id`;
  - `versiones_plantilla.basada_en_id`.
- (b) En ítems y registros, la base no exige que `version_id` sea de `plantilla_id`.
- (c) Que `usos_diseno.tipo_etiqueta_id` coincida con `plantilla.tipo_etiqueta_id` solo lo garantiza el código. Además, `plantillas.py:207-219` deja cambiar el tipo cuando solo hay usos dados de baja.
- (d) Que el nivel, el alcance y la cantidad de la regla correspondan al sujeto del tipo solo lo garantiza el código.
- (e) En `tipos_etiqueta`, `cantidad` y `alcance` no se cruzan con `sujeto`, aunque se podría con un CHECK de la misma fila.

**Solución:**
- FK compuestas:
  - `(version_vigente_id, id) → versiones(id, plantilla_id)`;
  - `(version_id, plantilla_id) → versiones(id, plantilla_id)`;
  - `(plantilla_id, tipo_etiqueta_id) → plantillas(id, tipo_etiqueta_id)`.
- CHECK de fila en `tipos_etiqueta` con `CANTIDADES_DE` y `ALCANCES_DE`.
- `usos_diseno.sujeto` desnormalizado con FK `(tipo_etiqueta_id, sujeto)` + CHECK.
- Revisar antes con `sin_violaciones`.

**Riesgo:** medio (puede haber filas que violen las restricciones nuevas).

**Clasificación:** refactorizar.

### D-08 · Medio · Referencias blandas que se rompen en silencio [VERIFICADO]

**Problema:**
- `usos_diseno.contexto_valores`: códigos de centro, país o sociedad e ids de proveedor como texto. `gobierno.USOS_CODIGO` (`maestros/gobierno.py:142-157`) no revisa esta columna, así que se puede borrar un centro o una sociedad que una regla usa.
- `condiciones` con `en_familia` compara por **código** (`reglas.py:83-90`, `comun/condiciones.py:181-182`), y el código del grupo es editable (`grupos/arbol.py:181-187`). Lo mismo pasa en las condiciones de los diseños aprobados, que ya no se pueden editar.
- `logico.<clave>` y `adjunto_id` viven dentro del JSON del diseño. `_en_uso` busca subcadenas en todas las versiones (`campos_logicos.py:93-96`).
- `trabajos_etiqueta.parametros` guarda ids; `familia_id` no se valida (`trabajos.py:150-202`).
- `reimpresiones[].por` es un id de usuario sin FK.

**Solución:**
- Tabla `usos_diseno_contexto(uso_id, centro|sociedad|pais|proveedor_id)` con FK tipadas y un CHECK de «una sola».
- Condiciones `en_grupo` por id, mostradas con el código.
- Tablas de uso `versiones_plantilla_campos(version_id, campo)` y `…_imagenes(version_id, adjunto_id FK)` llenadas al guardar.
- Agregar `usos_diseno` a `USOS_CODIGO`.

**Riesgo:** medio (migrar los JSON).

**Clasificación:** refactorizar.

### D-09 · Medio · Borrar un tipo de empaque generaliza en silencio una etiqueta de bulto [VERIFICADO]

**Problema:**
- `tipos_etiqueta_empaques` tiene CASCADE hacia `tipos_empaque` (`0079`, `etiquetado.py:175-176`), y la tabla significa «sin filas = todos los empaques» (`etiquetado.py:170-172`).
- Al borrar el único empaque asociado, la etiqueta de «solo pallet» pasa a aplicar a todos los empaques.
- El borrado del catálogo no revisa esta tabla: `catalogos.py:1330-1350`, sin entrada para tipos de empaque en `USOS_CODIGO`.

**Solución:** cambiar a `ON DELETE RESTRICT` (o comprobar el uso al borrar) y agregar un flag explícito `aplica_a_todos`.

**Riesgo:** bajo.

**Clasificación:** refactorizar.

### D-10 · Medio · Reenviar una OC rechazada con etiquetas falla con un mensaje equivocado [VERIFICADO]

**Problema:**
- `enviar` borra y recrea todas las posiciones (`compras/flujo_oc.py:367-369`).
- Una OC RECHAZADA admite `enviar` (`core/estados.py:47`).
- El etiquetado no filtra el estado de la OC (`etiquetado/datos.py:14-19`).
- Las FK `generacion_items.posicion_id` y `trabajo_etiqueta_registros.posicion_id` no tienen acción, así que el borrado da `IntegrityError`.
- Ese error se traduce como «número de factura repetido» (`main.py:204-207`).

**Solución:** no generar etiquetas reales de OC no aprobadas, actualizar las posiciones en el lugar en vez de recrearlas, y dar un mensaje específico.

**Riesgo:** bajo.

**Clasificación:** refactorizar.

### D-11 · Bajo · ON DELETE que borrarían historial [VERIFICADO]

**Problema:** `generacion_items.generacion_id` CASCADE, `versiones_plantilla.plantilla_id` CASCADE y `trabajo_etiqueta_registros.trabajo_id` CASCADE. Con este último, `generacion_items.trabajo_registro_id` pasa a NULL. Ningún código borra hoy esas cabeceras, pero una purga manual borraría historial sin aviso.

**Solución:** RESTRICT. El historial solo se agrega; la anulación es el único camino.

**Riesgo:** bajo.

**Clasificación:** refactorizar.

### D-12 · Bajo · Dos ejes de estado en `generaciones_etiqueta`: las consultas olvidan la anulación [VERIFICADO]

**Problema:** el estado vive en dos columnas: `estado` (GENERADA, PRUEBA) y `anulada_en`. `_previas` (`generacion.py:553`) y `resumen` (`:933-934`) filtran solo por `estado`. Por eso cuentan los lotes anulados como impresos y avisan «ya generada» de algo anulado.

**Solución:** columna o vista `vigente` derivada de ambas, un índice parcial y corregir las dos consultas.

**Riesgo:** bajo.

**Clasificación:** refactorizar.

### D-13 · Medio · `casepack` / `inner_pack` duplican la receta [VERIFICADO]

**Problema:**
- La duplicación en `posiciones_oc` y `factura_lineas` es intencional (convivencia, `EMPAQUE_RECETAS.md` §4).
- Solo el código la sincroniza (`recetas.py:660-667`); no hay invariante en la base.
- El etiquetado compara con `casepack` e `inner_pack` (`empaque_etiquetas.py:28-34`) y no con la receta de N niveles, así que no valida el pallet y bloquea retirar las columnas (fase 5).

**Solución:** que el etiquetado lea `derivar(receta_foto)` (con respaldo en las columnas) y valide todos los niveles. Después, la fase 5.

**Riesgo:** bajo.

**Clasificación:** conservar las columnas; refactorizar la lectura.

### D-14 · Bajo · Sujeto, cantidad y alcance en el tipo y en la regla, con dos vocabularios [VERIFICADO]

**Problema:**
- El tipo tiene `cantidad` con 6 valores; la regla tiene `cantidad` con 3 (UNA, POR_UNIDAD, MANUAL). El `alcance` está en ambos.
- La regla sobrescribe al tipo (patrón «defecto + excepción», intencional), pero la base no impide combinaciones sin sentido. Ver D-07(d,e).

**Solución:** un solo vocabulario de cantidad (más el override como NULL) y CHECK por sujeto.

**Clasificación:** refactorizar.

### D-15 · Bajo · La familia vive en varias tablas y `productos.grupo_producto_id` tiene dos significados [VERIFICADO]

**Problema:**
- La familia se asigna en artículo, grupo de artículos y producto (herencia intencional, `maestros.py:497-506`).
- En el producto, la misma columna guarda la familia **o** la categoría a mano; los hybrids la decodifican (`productos.py:110-164`).
- La base no exige que los artículos y grupos apunten a una FAMILIA, ni que el padre sea una FAMILIA; solo lo controla el código (`arbol.py:193-201`, `familias.py:87-91`).

**Solución:** columnas separadas `familia_id` y `categoria_id` en el producto, o una FK compuesta con la clase (`padre_clase` constante + FK `(padre_id, padre_clase) → (id, clase)`).

**Clasificación:** conservar a corto plazo; refactorizar.

### D-16 · Bajo · Impresión y reimpresión en JSON y columnas que se sobrescriben [VERIFICADO]

**Problema:** `confirmar_impresion` reescribe `impresa_en`, `impresa_por` e `impresion` sin control (`trabajos.py:1131-1133`). `reimpresiones` es una lista JSON con `por` sin FK (`trabajos.py:1191-1193`). El rastro completo queda solo en `historial`.

**Solución:** tablas `impresiones_etiqueta` y `reimpresiones_etiqueta` con FK a la generación y al usuario, y la selección.

**Clasificación:** refactorizar.

### D-17 · Bajo · El logo se copia en cada lote [VERIFICADO]

**Problema:** el data URL del logo de la organización se copia en `parametros` de cada lote que lo usa (`generacion.py:619-620`, `empresa.py:41`).

**Solución:** adjunto inmutable por sha y guardar solo la referencia.

**Clasificación:** refactorizar.

### D-18 · Medio · La consulta de «ya impreso» recorre todos los ítems de la organización [VERIFICADO]

**Problema:** `_previas` combina con OR condiciones sobre `generacion_items` y `generaciones_etiqueta` (`generacion.py:550-556`). El `EXPLAIN` en SQLite da `SEARCH gi USING INDEX ix_generacion_items_organizacion_id` + `TEMP B-TREE`: no usa los índices de `posicion_id` ni de `pl_id`. Crece con el historial completo.

**Solución:**
- Una consulta por rama, unidas con UNION.
- Índices `(organizacion_id, posicion_id, tipo_etiqueta_id)` y `(organizacion_id, pl_id, grupo_cajas_id, bulto_indice)` en los ítems.
- Índice parcial en cabeceras `(oc_id)` y `(pl_id)` `WHERE estado='GENERADA' AND anulada_en IS NULL`.

**Clasificación:** refactorizar.

### D-19 · Bajo · Índices faltantes, redundantes o inútiles [VERIFICADO]

**Faltan:**
- `generaciones_etiqueta (organizacion_id, creada_en DESC)` para el historial (`generacion.py:840-856`).
- `usos_diseno (organizacion_id, tipo_etiqueta_id) WHERE eliminado_en IS NULL` (`reglas.py:216-218`).
- `trabajos_etiqueta` parcial `WHERE estado='EN_PROCESO'` para la recuperación (`trabajos.py:648-653`).
- `posiciones_oc.receta_regla_id` (FK sin índice).
- Una tabla de uso de campos en los diseños para reemplazar el escaneo de `_en_uso` (`campos_logicos.py:93-96`).

**Redundantes:** el índice de una sola columna que ya cubre la primera columna de un único.
- `organizacion_id` en `tipos_etiqueta`, `plantillas_etiqueta`, `campos_etiqueta`, `grupos_producto` y `recetas_empaque`.
- `versiones_plantilla.plantilla_id`.
- `trabajo_etiqueta_registros.trabajo_id`.

**Inútiles:**
- Por baja selectividad: `estado` en plantillas, versiones, generaciones y registros.
- Sobre columnas congeladas: los 7 `ix_*familia*` y `ix_*categoria*`.

**Clasificación:** refactorizar (bajo).

### D-20 · Bajo · CHECK duplicados y CHECK faltantes [VERIFICADO]

**Duplicados:** las listas de `modelos/etiquetado.py:38-74` se repiten como literales en `restricciones.py:47-58`. Si cambia una, la otra se queda atrás en silencio, porque `aplicar` omite los nombres que ya existen.

**Faltan:**
- `anulada_por` ⇔ `anulada_en`.
- `impresa_en` ⇔ `impresa_por`.
- `(grupo_cajas_id IS NULL) = (bulto_indice IS NULL)`.
- `estado='GENERADO'` ⇔ `generacion_id IS NOT NULL` en los registros.
- Que `campos_etiqueta.sujetos` solo tenga valores de `SUJETOS`.
- Unicidad de las excepciones iguales en una celda (hoy solo en código).

**Solución:** importar las constantes en `restricciones.py` y agregar los CHECK faltantes.

**Clasificación:** refactorizar.

### D-21 · Bajo · Migraciones [VERIFICADO]

**Problemas:**
- (a) En SQLite, 0074 **omite** la FK `_org` si hay filas que la violan (`0074:73-85`); en PostgreSQL la crea NOT VALID. Una base puede quedar sin coherencia y solo queda un aviso en el log.
- (b) El downgrade de 0076 borra **todo** el historial de `uso_diseno`, incluidas las ediciones de usuarios (`0076:571`).
- (c) Los downgrades de 0076 y 0080 pierden datos (documentado).
- (d) La fecha de creación de 0082 es anterior a la de 0081 (cosmético; la cadena es correcta).

`alembic check` no muestra diferencias entre modelos y esquema.

**Solución:**
- Un script o test que verifique las `_org` en la base real.
- Que el downgrade de 0076 borre solo `accion='migrar'`.

**Clasificación:** conservar las migraciones; refactorizar el downgrade.

### D-22 · Bajo · Pares de FK SET NULL simple + `_org` NO ACTION sobre la misma columna [SOSPECHA]

**Problema:** se da en `registros.uso_id`, `registros.generacion_id`, `items.grupo_cajas_id` e `items.trabajo_registro_id`. En PostgreSQL funciona si la acción SET NULL se dispara antes que la comprobación NO ACTION, y el orden lo da el OID de los triggers. La migración las creó en el orden correcto, pero una recreación (dump/restore, cambio de restricciones) podría invertirlo. No lo pude probar sin PostgreSQL.

**Solución:** una sola FK compuesta con `ON DELETE SET NULL (col)` (PostgreSQL ≥ 15).

**Clasificación:** refactorizar.

### D-23 · Bajo · Acoplamiento del árbol compartido [VERIFICADO]

**Problema:**
- El permiso `etiquetas.familias` edita `grupos_producto` (`arbol.py:33-34`), un árbol que también gobierna `reglas_empaque`. Quien solo configura etiquetas puede renombrar o mover nodos que cambian el empaque.
- El código del grupo es editable y lo usan las condiciones (D-08).

**Solución:** permiso propio del árbol (`catalogos.editar`) y avisar del impacto en el empaque.

**Clasificación:** refactorizar.

### D-24 · Bajo · Coherencia multiempresa [VERIFICADO salvo la caché]

**Resultado:**
- Las 14 tablas propias (más las 2 congeladas) tienen `organizacion_id`, RLS y FK `_org` hacia cada padre. Las excepciones son D-07(a) y las referencias blandas en JSON (D-08).
- Las referencias blandas se validan al guardar con el filtro de organización del ORM (`usos.py:236`, `plantillas.py:243`), pero la base no las protege.

**Caché [SOSPECHA]:** la caché de campos lógicos en `db.info` no lleva la organización en la clave (`campos_logicos.py:35-39`). Podría servir campos de otra organización si una misma sesión cambia de organización con `trabajando_en`.

**Solución:** incluir la organización en la clave de la caché y aplicar D-07(a).

**Clasificación:** refactorizar.

### D-25 · Bajo · Elementos congelados del modelo [VERIFICADO]

**Problema:** 2 tablas, 7 columnas, 7 índices y 9 FK `_org` sin uso. Tienen costo de escritura y de comprobación de FK, y se prestan a confusión: el nombre físico `familia_etiquetado_id` es igual al del synonym que apunta a otra columna.

**Solución:** la estrategia de la §4.

**Riesgo:** medio (exige downgrade reconstructivo y ajustar los tests de ida y vuelta).

**Clasificación:** eliminar.

**Prioridad sugerida:**
1. D-01, D-02, D-03, D-04 y D-05 (seguridad y trazabilidad).
2. D-07, D-08, D-09 y D-10 (integridad).
3. D-12, D-13 y D-18 (correctitud y rendimiento).
4. D-25 (limpieza de la fase 5).
5. El resto.
