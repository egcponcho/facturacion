# Auditoría integral del etiquetado y propuesta de mejora

**Base:** rama `main`, commit `3b9d8b5`, que incluye las recetas de empaque y los
grupos de producto del PR #27.

**Modo:** solo lectura. No se cambió código, datos ni migraciones.

**Fecha:** 20 de octubre de 2026.

**Este documento** consolida cinco revisiones independientes. El detalle, con la
evidencia línea por línea, está en `docs/auditoria_etiquetado/`:

| Anexo | Área | Hallazgos |
|---|---|---|
| [`L-logica-api.md`](auditoria_etiquetado/L-logica-api.md) | Flujo, reglas de negocio, API, permisos, rendimiento | L-01 … L-26 |
| [`D-datos.md`](auditoria_etiquetado/D-datos.md) | Modelo de datos, integridad, historial, migraciones | D-01 … D-25 |
| [`I-integraciones.md`](auditoria_etiquetado/I-integraciones.md) | OC, artículos, empaque, packing list, prepacks, unidades | I-01 … I-17 |
| [`C-codigo-pruebas.md`](auditoria_etiquetado/C-codigo-pruebas.md) | Código sin uso, duplicados, dependencias, pruebas | C-01 … C-22, T-01 … T-11 y duplicados D-01 … D-12, que aquí se citan como **CD-01 … CD-12** para no confundirlos con los del anexo D |
| [`U-ux.md`](auditoria_etiquetado/U-ux.md) | Pantallas, recorridos, navegación, propuesta del módulo central | U-01 … U-23 |

**Cómo se verificó:**
- Lectura completa de los flujos.
- 17 pruebas propias, que pasaron todas: 12 de lógica y 5 de integración. Están en
  `docs/auditoria_etiquetado/pruebas/`, renombradas para que pytest no las recoja.
- Esquema real migrado con `alembic check`.
- `EXPLAIN` de las consultas críticas.
- Comparación ejecutada entre el código del navegador y el del servidor.
- Recorridos en la demo a 1440 px y 390 px.

**Marcas de evidencia:**
- **[V]**: verificado, con una prueba o leyendo el flujo completo.
- **[S]**: sospecha; falta confirmarlo.

Las tres más graves (L-01, D-01 e I-01) las volví a comprobar en el código al consolidar.

---

## 1. Diagnóstico del estado actual

### 1.1 Cómo funciona hoy

El etiquetado es un módulo grande y bien estructurado en su núcleo:
- ~8 800 líneas de backend en `modulos/etiquetado` y 83 rutas bajo `/api/etiquetas`.
- 6 pantallas, un editor de diseños y 20 componentes.

**Los conceptos son correctos:**
- **Tipo de etiqueta:** qué se etiqueta (artículo, bulto o documento) y cuántas salen.
- **Diseño** con versiones aprobables.
- **Reglas** por celda (tipo × nivel × destino), con excepciones.
- **Trabajo de etiquetado:** el único camino para generar.
- **Instantánea de los valores impresos.**

**Todos los puntos de entrada usan el mismo camino del servidor:**
- **Entradas:** OC, líneas de la OC, lista de OC, packing list y producto.
- **Camino:** `trabajos._limpiar` → `_partes` → `generacion.planear` → `producir`.
- **Diferencias:** solo cambian los parámetros que manda cada pantalla.

**El flujo real:**
1. Elegir el origen.
2. Crear el trabajo.
3. Validar: para cada registro se decide el diseño, se leen los datos en vivo, se
   dibuja y se revisa.
4. Generar: síncrono, o en segundo plano a partir de 2 000 etiquetas, con arriendo
   y recuperación.
5. Guardar el lote, los ítems y su instantánea, y reservar los números de serie.
6. Descargar: el archivo se vuelve a dibujar cada vez.
7. Confirmar la impresión a mano.
8. Si hace falta, anular o reimprimir.

El detalle paso a paso está en el anexo L §1.

### 1.2 Principales problemas

Hay cinco problemas de fondo. Los demás hallazgos son consecuencias de estos.

1. **Un proveedor ve más de lo que debe (seguridad).**
   - Lee cualquier imagen de la organización, incluidas las fotos de productos de
     otros proveedores (L-01).
   - Con solo `etiquetas.ver` lista todos los proveedores, las reglas con números de
     OC ajenos y los SKU de toda la empresa, y ve datos de otro proveedor en la
     vista previa de ejemplo (L-02).
   - Las rutas de etiquetado no aplican la visibilidad por rol: los precios y las
     fechas internas aparecen en el historial y en las instantáneas (D-01).
   - Además, varios parámetros sin validar provocan errores 500 o pueden agotar la
     memoria (L-05, L-06).

2. **Lo que se pega en la caja no siempre coincide con los documentos.**
   - El código de caja impreso no es el del packing list. En la prueba, la etiqueta
     dice C1–C2 donde el packing list dice C4–C5 (I-01).
   - El total de bultos difiere: «n de 5» en la etiqueta frente a 7 bultos en el
     documento (I-02).
   - Con un packing list de varias OC, la misma caja sale dos veces (L-04).
   - Las etiquetas de un packing list leen la OC en vivo y no la copia de la factura
     (I-03).
   - El inner y la receta definidos en el packing list no llegan a la etiqueta (I-06).

3. **Las cantidades no son confiables.**
   - La cantidad que el usuario escribe se ignora sin aviso salvo en los tipos
     MANUAL (L-03).
   - Los prepacks y kits dan una etiqueta por curva y no por par (I-04).
   - No hay conversión de unidades (I-04).
   - Al juntar líneas se suman pares y curvas: 24 PAR + 3 CJ = 27 (I-04).

4. **La trazabilidad se rompe.**
   - Al reempacar, lo impreso pierde su caja y un trabajo nuevo vuelve a generarla
     sin el aviso «ya generada» (I-07, D-04).
   - Al anular se pierde el vínculo con el registro que produjo la etiqueta (D-03).
   - El ítem impreso no guarda su OC (D-02).
   - No queda registrada la regla que eligió el diseño (D-06).
   - Los lotes anulados siguen contando como impresos (L-12).
   - Nada avisa cuando cambian la OC o el packing list después de imprimir (I-07).

5. **La misma pregunta tiene varias respuestas y varios lugares.**
   - «Qué diseño lleva» se calcula en cinco caminos con datos distintos (L-07) y se
     edita en seis lugares con cinco interfaces (U-06).
   - Las familias se editan en cuatro lugares, con tres servicios que validan
     distinto (U-04, CD-01).
   - El editor evalúa las condiciones y formatea números distinto del PDF impreso
     (CD-05, CD-06).
   - Hay tres historiales (U-02).
   - Cada entrada crea un trabajo nuevo, sin ofrecer continuar ni descartar el que
     ya existe (U-01).

**Lo que está bien y conviene conservar:**
- **Un solo camino de generación:** todas las entradas terminan en el mismo servicio.
- **Concurrencia y aislamiento:**
  - generación duradera con arriendo y toma atómica;
  - celda de reglas con firma y 409;
  - aislamiento por organización con FK compuestas y RLS.
- **Versiones e historial:**
  - versiones aprobables con cuatro ojos;
  - la instantánea de valores por ítem;
  - el 409 `datos_cambiaron`.
- **Pruebas:** 114 de 115 pasan (la omitida solo corre en PostgreSQL), y la base de
  datos coincide con los modelos.

---

## 2. Mapa de relaciones

### 2.1 Diagrama

```
                    grupos_producto (familias/categorías, árbol único)  ◄── reglas_empaque
                          ▲   motor común grupos/arbol.py (ruta del artículo)
 grupos_articulos ──┐     │
 productos ─────────┼──► articulos ──(prepack_id)──► prepacks ─► prepack_componentes (curva, leída en vivo)
                    │       ▲ escribe «completar» (UPC, SKU prov., peso, unidad)
 ordenes_compra ──► posiciones_oc ── casepack / inner_pack (leídos)    receta_id / receta_foto (NO leídos)
     │  └► sociedades / centros / países (códigos en texto)
     │                     ▲
     │             factura_lineas (instantánea de la factura + receta_foto: NO leídas por el etiquetado)
     │                     ▲
     │             pl_lineas ◄─ grupo_cajas_items ─► grupos_cajas (árbol, tipos_empaque) ◄─ packing_lists ─► unidades_carga ─► embarques
     │                                                      ▲ SET NULL (se pierde al reempacar)
 ETIQUETADO
  tipos_etiqueta ─► plantillas_etiqueta ─► versiones_plantilla
  tipos_etiqueta ─*─* tipos_empaque (tipos_etiqueta_empaques, CASCADE)
  usos_diseno (reglas) ─► tipo · plantilla · grupo · producto · artículo · tipo_empaque · OC
                        contexto_valores JSON (códigos)  ← referencia blanda
  trabajos_etiqueta (parametros JSON: oc_ids, posiciones, pl_id…)  ← referencias blandas
     └─► trabajo_etiqueta_registros ─► OC · posición · artículo · PL · versión · uso (SET NULL)
  generaciones_etiqueta (lote) ─► OC · PL · trabajo
     └─► generacion_items ─► versión · artículo · posición · PL · grupo_cajas (SET NULL) · grupo
                             valores JSON = INSTANTÁNEA     (no guarda OC ni regla)
```

### 2.2 Qué se consulta en vivo, qué se guarda como referencia y qué como instantánea

| Información | Debería ser | Hoy | Brecha |
|---|---|---|---|
| Datos maestros para una etiqueta nueva | En vivo | En vivo al validar y al generar | — |
| Datos de un bulto desde el packing list (UPC, descripción, destino, país) | Instantánea del documento (línea de factura) | La posición de la OC, en vivo | I-03 |
| Empaque planificado (inner, caja, pallet) | Foto de la receta de la línea | `casepack` e `inner_pack` | I-06, D-13 |
| Código y número de caja | La numeración del packing list | Una numeración propia | I-01, I-02 |
| Qué se generó (versión, artículo, línea, OC, PL, bulto) | FK | FK, salvo la OC; el bulto se pierde al reempacar | D-02, D-04 |
| Por qué ese diseño (regla y su versión) | FK + versión | Solo un texto | D-06 |
| Valores impresos | Instantánea | `generacion_items.valores` | Correcto, pero se muestran sin filtrar datos reservados (D-01) |
| Formato de los campos, imágenes y logo | Instantánea o referencia inmutable | Formatos e imágenes en vivo; logo copiado en cada lote | D-05, D-17 |
| Impresión y reimpresiones | Filas con FK | JSON que se sobrescribe | D-16 |
| Destinatarios de una excepción (centro, sociedad, proveedor) | FK | Códigos en JSON | D-08 |

### 2.3 Cómo se propagan los cambios

| Cambio | Registros pendientes | Etiquetas ya generadas |
|---|---|---|
| Dato que el diseño imprime | 409 `datos_cambiaron` al generar | Nada |
| Dato que no se imprime pero decide algo (cantidad con alcance UNA, contenido de la caja, categoría) | Nada | Nada |
| Reabrir o reempacar el packing list | Nada | Pierden su caja (SET NULL); se pueden volver a generar sin aviso |
| Reenviar una OC rechazada | — | Error de FK, con el mensaje equivocado de «factura repetida» (D-10, I-08) |
| Borrar un tipo de empaque | — | Una etiqueta «solo pallet» pasa a aplicar a todos los empaques (D-09) |
| Renombrar el código de un grupo | Las condiciones `en_familia` dejan de cumplirse en silencio | — |

---

## 3. Inventario de funcionalidades

| Funcionalidad | Existe | Funciona | Duplicada | Falta o problema |
|---|---|---|---|---|
| Tipos de etiqueta | Sí | Sí | El alta del primer uso no es atómica; el endpoint atómico no se usa (C-08) | — |
| Diseños, editor y versiones con aprobación | Sí | Sí | — | El aprobador no recibe aviso (U-09); la vista del editor no coincide con el PDF (CD-05, CD-06) |
| Reglas (celda, excepciones, «no lleva», dónde va, cuántas) | Sí | Con huecos (L-08, L-09, L-11, L-19) | 5 caminos de escritura y 6 pantallas (U-06) | No hay «Probar» de etiquetas (sí lo hay en empaque) |
| Familias y categorías | Sí (árbol compartido) | Sí | 3 servicios y 4 pantallas (CD-01, U-04) | Validaciones contradictorias |
| Campos lógicos y nombres de campos | Sí | Sí | — | La caché no lleva la organización en la clave [S] (D-24) |
| Etiquetas de una OC completa | Sí | Sí | — | Acepta OC canceladas o rechazadas (I-08) |
| Etiquetas de posiciones elegidas | Sí | Parcial | — | Las cajas y documentos no se filtran (I-05) |
| Por artículo o por línea | Sí | Sí | — | Suma unidades distintas (I-04) |
| Cantidad manual | Parcial | No: se ignora salvo MANUAL (L-03) | — | — |
| Lotes de producción | **No** | — | — | Solo variables por trabajo |
| Kits y prepacks | Parcial | No se explotan en componentes (I-04) | — | — |
| Etiqueta que combina OC, artículo y caja | Parcial | Solo con caja de un artículo y una OC | — | La etiqueta de artículo no lleva el número de caja |
| Desde los bultos del packing list | Sí | Con fallas (I-01, I-02, L-04) | — | No se pueden elegir cajas concretas (U-23) |
| Diseño automático por reglas | Sí | Sí | 5 cálculos (L-07) | — |
| Aviso de datos faltantes antes de generar | Parcial | El panel de la OC no avisa lo que bloqueará (U-10) | — | — |
| Errores, reintentos y segundo plano | Sí | Sí, con fallas (L-14, L-26) | — | — |
| Impresión | Mínima | Descarga + confirmación manual | — | No hay impresión directa ni ZPL |
| Historial, anular y reimprimir | Sí | Sí, con fallas (L-12, D-03) | 3 historiales y 2 empaquetadores ZIP (U-02, CD-07) | No hay ruta de historial |
| SSCC | **No** | — | — | `tipos_empaque.identificador` no se usa (I-15) |
| Cancelar un trabajo | Solo en la API | — | — | Sin botón (L-21, U-01) |
| Tareas en el inicio (por aprobar, con errores) | **No** | — | — | U-09 |
| Sin uso | `POST /tipos/sugeridos`, `GET /usos`; funciones `_soltar`, `render.vacio`, `campos.por_clave`, `condiciones.cumple`; 11 constantes; ~229 traducciones de etiquetado y empaque | — | — | Anexo C §1 |

---

## 4. Propuesta de UX/UI

### 4.1 Un módulo central «Etiquetas» con cinco secciones

No hacen falta pantallas nuevas: se reubica lo que ya existe.

| Sección | Qué contiene | De dónde sale |
|---|---|---|
| **Imprimir** | Bandeja de trabajos: Por continuar · Con errores · Generados sin confirmar · Todos. En cada fila: Continuar / Descargar / Descartar. Botón «Nuevo trabajo» con el asistente de 3 pasos de hoy | Imprimir + asistente |
| **Historial** | Una sola tabla de **ejecuciones**: descargar, marcar impresas, reimprimir y anular. Filtros por OC, packing list, artículo, fecha y estado | El historial de «lotes» de Configuración + la tabla de ejecuciones del asistente |
| **Diseños** | Tarjetas por tipo + pestaña **Por aprobar**, con contador. Al aprobar: «Asignar a…» | Diseños + editor |
| **Reglas** | La matriz como pantalla principal. Cada celda se abre en un **panel lateral**, que es el **único** editor de reglas: normal, excepciones (también «para esta OC») y las propias del producto y la talla, con el efecto simulado. Pantalla **Probar**: se elige una OC, un packing list o un artículo y se ve qué diseño sale y por qué. El árbol de familias es de solo lectura, con «Editar en Grupos de producto» | El paso «Qué diseño va en qué», la ficha de la familia, el «diseño especial» de la OC y el producto |
| **Configuración** | Tipos, tamaños, campos y nombres, conversión de reglas antiguas. Una lista de **puesta en marcha** que solo aparece mientras falte algo | La guía de 6 pasos |

**Grupos de producto** (Datos maestros) pasa a ser el **único dueño** de:
- el árbol de familias y categorías, con «Probar» de las categorías;
- los miembros: qué grupos de artículos, productos y artículos van en cada familia,
  con asignación en lote.

El etiquetado y el empaque solo lo leen. El asistente de familia nueva se lanza
desde ahí.

### 4.2 Atajos en otros módulos

Los atajos no llevan lógica propia: todos abren el flujo central con el contexto ya
cargado y vuelven al origen al terminar.

| Dónde | Atajo |
|---|---|
| **Detalle de la OC** | «Etiquetas» abre un panel que muestra: <ul><li>qué saldría;</li><li>qué falta, incluidos los datos manuales que pedirá el diseño;</li><li>los trabajos abiertos o generados de esa OC, con Continuar / Descargar;</li><li>«Ver historial de esta OC».</li></ul> |
| **Líneas de la OC** | «Etiquetas de estas líneas» abre **el mismo panel**, con las mismas reglas para elegir los tipos de etiqueta (hoy no coinciden: U-03) |
| **Lista de OC** | Selección para etiquetas que no dependa del saldo por facturar (U-05) |
| **Packing list** | El mismo panel, con los niveles de empaque visibles. En la selección de cajas: «Etiquetas de estas cajas» |
| **Producto** | Pestaña de solo lectura, «qué lleva y por qué». Desde ahí: <ul><li>Imprimir;</li><li>Cambiar diseño, que abre la celda;</li><li>Etiquetas generadas, que abre el Historial filtrado.</li></ul> |
| **Inicio** | Tareas: <ul><li>versiones por aprobar;</li><li>trabajos con errores;</li><li>ejecuciones sin confirmar.</li></ul> |

**Qué se queda en cada módulo:**

| Lugar | Qué hace |
|---|---|
| Módulo central | Configurar, diseñar, decidir las reglas, preparar, generar y consultar el historial |
| OC, packing list y producto | Solo lo que necesita su contexto: un panel de resumen y atajos |
| Empaque | Armar las cajas: es responsabilidad del empaque. El etiquetado solo lee el árbol de cajas y su numeración |
| Grupos de producto | Quién pertenece a qué grupo |

### 4.3 Flujos guiados

1. **Imprimir desde el contexto:**
   - Panel: qué sale, qué falta y qué ya existe.
   - Revisar: primero los datos manuales y los problemas, con arreglo en el mismo lugar.
   - Generar: un solo botón principal y el formato predeterminado de la empresa.
   - Descargar → confirmar la impresión → volver al origen.

   Objetivo: de **11 a 7 acciones** para una OC completa, sin cambios de módulo para
   volver.
2. **Sin diseño en Revisar:**
   - «Solo para este trabajo».
   - O «Guardar como regla», que abre la celda con el efecto simulado.
3. **Diseño nuevo:**
   - El tipo viene del contexto → editor → enviar a aprobación.
   - El aprobador recibe la tarea, aprueba desde el aviso y elige «Asignar a…».
4. **Familia nueva:** Grupos de producto → asistente (datos, miembros y diseños
   opcionales) → Reglas filtrado por esa familia.

### 4.4 Qué se elimina o fusiona en la interfaz

| Hoy | Pasa a |
|---|---|
| Formulario «Diseño especial para esta OC» y formulario propio del producto | La celda de Reglas |
| Modal «Cambiar familia» del producto y formulario de familia de Configuración | Grupos de producto |
| Guía de 6 pasos | Lista de puesta en marcha |
| Historial de lotes dentro de Configuración | Historial |
| Los nombres «lote» y «ejecución» | Un solo nombre |
| Selectores de diseño propios | `SelectorDiseno` |
| Las cinco tablas hechas a mano del asistente | `TablaDatos` |
| Segmentos, barra de avance y pasos propios | Componentes comunes (anexo U §5) |

**Correcciones visuales y de accesibilidad:**
- Códigos en crudo en las tablas (U-13).
- Filas que solo se abren con el ratón (U-17).
- Desbordes a 390 px (U-18).
- Plurales rotos (U-12).
- Dos botones primarios a la vez en Generar (U-11).

---

## 5. Propuesta técnica

### 5.1 Backend: responsabilidades

Solo se mueven funciones; no se agrega ninguna capa nueva (anexo L §4).

| Hoy | Propuesta |
|---|---|
| `trabajos.py` (1 226 líneas) mezcla CRUD, validación, ejecución duradera, ZIP, impresión y anulación | <ul><li>`trabajos.py`: parámetros, CRUD, validar y generar.</li><li>`ejecucion.py`: arriendo y segundo plano.</li><li>`lotes.py`: historial, impresión, anulación y reimpresión.</li></ul> |
| Dos empaquetadores con reglas distintas (CD-07) | `paquetes.py`, uno solo, que respete hoja, dpi y nombres |
| `generacion.py` mezcla qué se etiqueta, planificación, persistencia y descargas | <ul><li>`registros.py`: qué se etiqueta desde cada origen.</li><li>`generacion.py`: planear y producir.</li></ul> |
| `campos.py` incluye la estructura física del packing list | <ul><li>`bultos.py`, en la frontera con el empaque, que usa `empaques.numeracion()` y `prefijo()` (I-01, I-02).</li><li>Una sola definición de bultos del documento y de caja mixta (I-12).</li></ul> |
| `usos.py` arma valores propios para la matriz, la ficha y la simulación | <ul><li>`cobertura.py`, con **una sola función** de valores del registro y elección, compartida con la generación (L-07).</li><li>`/resolver` pasa a ser la base de la pantalla «Probar».</li></ul> |
| 3 servicios sobre `grupos_producto` (CD-01) y 5 cálculos de la familia (CD-03) | <ul><li>`grupos/arbol.py` como único servicio.</li><li>`familias.py` y `categorias.py` solo adaptan.</li><li>Una definición de familia efectiva en SQL y en Python, con una prueba de paridad.</li></ul> |
| Resolvedor y receta con escaleras propias (CD-04) | El resolvedor usa `arbol.ruta_efectiva` |
| El catálogo de datos de las condiciones difiere entre empaque y etiquetado (I-09) | <ul><li>Un catálogo común de valores del registro en `comun/`.</li><li>Claves inequívocas (`oc.proveedor_codigo` frente a `oc.proveedor_nombre`).</li><li>Resuelve el ciclo de imports empaque/grupos → etiquetado (I-13).</li></ul> |
| Condiciones y formato evaluados dos veces, en el navegador y en el servidor (CD-05, CD-06) | <ul><li>La decisión de «mostrar solo si» y el formato los da el servidor, que ya dibuja la vista previa.</li><li>O una tabla de casos compartida que pruebe los dos lados.</li><li>Redondeo explícito, `ROUND_HALF_UP`.</li></ul> |

### 5.2 Reglas de negocio que hay que corregir

| Regla | Qué cambia | Hallazgo |
|---|---|---|
| **Cantidad** | <ul><li>Lo escrito en Revisar se aplica a cualquier registro como ajuste manual registrado.</li><li>O el campo solo se habilita donde vale.</li></ul> | L-03 (decisión 1) |
| **Unidades** | <ul><li>Error `unidades_distintas` al juntar líneas de unidades diferentes.</li><li>Factor opcional en la lista de unidades (DOC = 12 UN).</li><li>Opción del tipo de etiqueta «explotar prepack o kit en componentes».</li></ul> | I-04 (decisión 2) |
| **Bultos desde la OC** | <ul><li>Solo las cajas con mercancía de esa OC.</li><li>Una caja mixta sale una sola vez por trabajo.</li><li>Ningún packing list en borrador da etiquetas reales.</li></ul> | L-04 |
| **Selección parcial** | Las cajas y documentos respetan las posiciones o la familia elegidas | I-05 |
| **Estado de la OC** | <ul><li>No se generan etiquetas reales de una OC cancelada, rechazada o en borrador.</li><li>En aprobación, solo en modo prueba.</li></ul> | I-08 |
| **Packing list** | <ul><li>Los datos del bulto salen de la línea de factura.</li><li>El empaque, de `receta_foto`.</li><li>La validación revisa todos los niveles de la receta.</li></ul> | I-03, I-06, D-13 |
| **Diseño sin versión aprobada** | <ul><li>No se puede asignar a una regla.</li><li>La matriz lo marca.</li></ul> | L-09 |
| **Condiciones** | <ul><li>Las de categoría, solo sobre `articulo.*` y `producto.*`.</li><li>Las de regla no pueden usar campos que aún no existen al decidir (`contexto.*`, `logico.*`).</li><li>`en_familia` compara por id del grupo, no por código.</li></ul> | L-08, L-18, I-10, I-11 |
| **Advertencias** | <ul><li>Se aceptan con la huella de lo que se vio.</li><li>Bloqueo opcional de duplicados entre trabajos de la misma línea.</li></ul> | L-13 |
| **Series** | La prueba no consume números y la reserva no bloquea mientras se dibuja | L-16 |
| **Anulados** | No cuentan como impresos | L-12 |
| **Precedencia de excepciones** | Avisar cuando coinciden excepciones de clases distintas y documentar el orden | L-19 |

### 5.3 API

| Endpoint | Propuesta |
|---|---|
| `POST /tipos/sugeridos` | Usarlo en el primer uso, que así queda atómico, o retirarlo |
| `GET /usos` | Retirarlo |
| `POST /trabajos/{id}/cancelar` | Exponerlo en la pantalla |
| `GET /usos/{id}/historial` | Mostrarlo en la celda |
| `GET /trabajos` | Agregar filtros por origen (OC, packing list, artículo) para «Continuar» |
| Historial | Filtrable por OC, packing list y artículo |

**Permisos:**
- `usos/simular`, `usos`, `usos/valores`, `matriz` y `celda` pasan a exigir un
  permiso interno (L-02).
- Las imágenes se leen solo de la carpeta del etiquetado (L-01).
- `/api/etiquetas` entra en la visibilidad por rol (D-01).
- `elegidas` solo se acepta para registros sin diseño, o con
  `etiquetas.configurar` y un motivo (L-10).
- Alcance por sociedad en trabajos y lotes (L-15).

**Validación:**
- `hoja`, `dpi` en 72–1200, enteros y tamaños: todo error da 422, ninguno 500 (L-05).
- Tope de registros antes de planificar (L-06).
- Validación y descargas grandes en segundo plano (L-06).

### 5.4 Base de datos

Primero los cambios aditivos; los destructivos van al final (§7):

| Cambio | Hallazgo |
|---|---|
| `generacion_items.oc_id` (FK, índice) y `uso_id` + `uso_version` | D-02, D-06 |
| Ítem `anulado`; UNIQUE parcial de `trabajo_registro_id` solo para los no anulados; `anular` deja de borrar el vínculo | D-03 |
| `grupo_cajas_id` y `bulto_indice` en el registro del trabajo. Identidad estable del bulto: código o SSCC por unidad, o impedir reempacar con etiquetas vigentes | D-04, I-07 |
| «Vigente» = GENERADA y no anulada, con índice parcial; corregir las consultas que lo olvidan | D-12, L-12 |
| `tipos_etiqueta_empaques`: RESTRICT y bandera `aplica_a_todos` | D-09 |
| FK compuestas versión ↔ plantilla y plantilla ↔ tipo; CHECK de cantidad y alcance según el sujeto | D-07, D-14 |
| Tabla `usos_diseno_contexto` con FK tipadas, en lugar de códigos en JSON | D-08 |
| Tablas de uso de campos e imágenes por versión. Imágenes inmutables por sha. Formatos guardados en el lote. Bloqueo de edición de versiones aprobadas o ya usadas | D-05, D-08 |
| Tablas `impresiones_etiqueta` y `reimpresiones_etiqueta` | D-16 |
| Índices para «ya impreso», historial, reglas y recuperación; quitar los redundantes | D-18, D-19 |
| CHECK que faltan (anulación, impresión, bulto); listas de restricciones tomadas de las constantes del modelo | D-20 |
| RESTRICT en las cabeceras del historial | D-11 |

---

## 6. Matriz de hallazgos

Los hallazgos están ordenados por prioridad. La evidencia completa, con
archivo:línea, está en el anexo indicado.

| # | Problema | Evidencia (anexo) | Impacto | Solución | Riesgo |
|---|---|---|---|---|---|
| 1 | Un proveedor lee cualquier imagen de la organización | [V] L-01: `plantillas.py:250-261,513-519` | Alto | Solo imágenes del etiquetado | Bajo |
| 2 | El proveedor ve configuración y datos ajenos con `etiquetas.ver` | [V] L-02: `usos.py:121,436,679` | Alto | Permiso interno; vista previa con datos neutros o filtrados | Bajo |
| 3 | Precios y fechas internas sin filtrar en el etiquetado | [V] D-01: `visibilidad.py:69-71` | Alto | Visibilidad por rol en `/api/etiquetas` y en las instantáneas | Medio |
| 4 | Parámetros sin validar: errores 500 y riesgo de memoria | [V] L-05: `trabajos.py:151-207`, `salidas.py:306` | Alto | Validar y responder 422 | Bajo |
| 5 | Sin tope previo; validar y descargar en la misma petición | [V] L-06: `trabajos.py:953-1046` | Alto | Tope + segundo plano + guardar el archivo | Medio |
| 6 | Código de caja impreso ≠ código del packing list | [V] I-01: `campos.py:536-547` frente a `empaques.py:113-190` | Alto | Usar la numeración del empaque | Medio |
| 7 | Cajas duplicadas con un packing list de varias OC; un packing list en borrador da etiquetas reales | [V] L-04: `campos.py:592-604` | Alto | Filtrar por OC y revisar cada packing list | Medio |
| 8 | Cantidad escrita ignorada sin aviso | [V] L-03: `generacion.py:257-268` | Alto | Decisión 1 | Medio |
| 9 | Prepacks y kits sin explotar; sin conversión; suma de unidades distintas | [V] I-04: `generacion.py:116-135,247-262` | Alto | Error, factor y opción de explotar | Medio |
| 10 | Reempacar borra la caja de lo impreso; se reimprime sin aviso | [V] I-07, D-04: `etiquetado.py:471` (SET NULL) | Alto | Identidad estable y aviso al reabrir | Medio |
| 11 | Tres totales de bultos | [V] I-02 | Medio | Una definición en el empaque | Bajo |
| 12 | Etiquetas del packing list con datos de la OC en vivo y no de la factura | [V] I-03: `campos.py:413-422` | Medio | Leer la línea de factura | Medio |
| 13 | Selección de líneas no filtra cajas ni documentos | [V] I-05: `generacion.py:289-290` | Medio | Filtrar por las posiciones elegidas | Bajo |
| 14 | Receta e inner del packing list no llegan a la etiqueta | [V] I-06, D-13, CD-10 | Medio | Leer `receta_foto` | Bajo |
| 15 | La misma pregunta da 5 respuestas (ficha, resumen, editor, matriz, trabajo) | [V] L-07 | Medio | Una función de valores y elección | Medio |
| 16 | El editor no dibuja lo mismo que se imprime | [V] CD-05, CD-06 (5 de 8 casos discrepan; 2,5 da «3» frente a «2») | Medio | El servidor decide, o una prueba de paridad | Bajo |
| 17 | Diseño sin versión aprobada bloquea toda una familia | [V] L-09 | Medio | Impedirlo al guardar | Bajo |
| 18 | El proveedor impone un diseño distinto del de la regla | [V] L-10 | Medio | Restringir `elegidas` | Bajo |
| 19 | Los anulados cuentan como impresos | [V] L-12, D-12 | Medio | Filtrar por vigentes | Bajo |
| 20 | Advertencias aceptadas a ciegas; dos trabajos de la misma línea generan los dos | [V] L-13 | Medio | Huella de las advertencias y bloqueo opcional | Bajo |
| 21 | El ítem no guarda la OC; anular rompe el vínculo; no queda la regla que decidió | [V] D-02, D-03, D-06 | Medio | Columnas nuevas y UNIQUE parcial | Bajo a medio |
| 22 | Reproducción exacta no garantizada (formatos, imágenes y versiones vivas) | [V] D-05 | Medio | Instantánea de formatos; imágenes y versiones inmutables | Bajo a medio |
| 23 | Se aceptan OC canceladas o rechazadas; reenviar una OC da un error engañoso | [V] I-08, D-10 | Medio | Filtrar por estado; mensaje específico | Bajo |
| 24 | Condiciones `contexto.*` y `logico.*` nunca se cumplen en las reglas | [V] L-08 | Medio | Rechazarlas o decidir con todos los valores | Bajo |
| 25 | Excepciones de proveedor u OC no aplican en cajas mixtas | [V] L-11 | Medio | Contexto desde la factura | Bajo |
| 26 | `oc.proveedor` significa código en empaque y nombre en etiquetado | [V] I-09 | Medio | Catálogo común | Medio |
| 27 | Borrar un tipo de empaque generaliza una etiqueta | [V] D-09 | Medio | RESTRICT + `aplica_a_todos` | Bajo |
| 28 | Referencias blandas (códigos en JSON; `en_familia` por código editable) | [V] D-08, I-11 | Medio | Tablas con FK; condición por id | Medio |
| 29 | Integridad versión/plantilla/tipo solo en código | [V] D-07 | Medio | FK compuestas | Medio |
| 30 | Consulta de «ya impreso» sin índices | [V] D-18 | Medio | UNION + índices | Bajo |
| 31 | La serie de prueba consume números; la reserva bloquea mientras se dibuja | [V] L-16 | Medio | Reservar al final; no en prueba | Medio |
| 32 | En segundo plano se marcan como generados registros sin ítem | [V] L-14 | Medio | Marcar solo lo producido | Bajo |
| 33 | Un error en una parte bloquea todo el trabajo | [V] L-26 | Medio | Errores por parte | Bajo |
| 34 | Alcance por sociedad ignorado | [V] L-15 | Medio | Filtrar por sociedad | Bajo |
| 35 | Cálculos repetidos y consultas N+1 | [V] L-17, CD-02 | Medio | Calcular una vez; conteo en SQL | Bajo |
| 36 | Cada entrada crea un trabajo nuevo; no se puede descartar | [V] U-01 | Alto (UX) | Continuar / Descartar | Bajo |
| 37 | Tres historiales; el principal está en Configuración | [V] U-02 | Alto (UX) | Sección Historial | Bajo |
| 38 | La misma OC da otros tipos de etiqueta según la entrada | [V] U-03 | Alto (UX) | Un cálculo de tipos por defecto | Bajo |
| 39 | Familias en 4 lugares; «familia» con 3 significados | [V] U-04, CD-01 | Alto (UX) | Grupos de producto como dueño | Medio |
| 40 | «Qué diseño lleva» en 6 lugares con 5 interfaces | [V] U-06 | Alto (UX) | La celda como único editor | Medio |
| 41 | Enlaces sin contexto; la guía se impone; aprobar no se descubre | [V] U-07, U-08, U-09 | Medio | Pasar el contexto; lista de puesta en marcha; bandeja | Bajo |
| 42 | El panel no avisa lo que bloqueará; Generar con dos botones primarios; conteos distintos | [V] U-10, U-11, U-12 | Medio | Ver §4 | Bajo |
| 43 | Tablas con códigos en crudo; filas solo con ratón; 390 px | [V] U-13, U-17, U-18 | Medio | `textoValor`; foco; diseño móvil | Bajo |
| 44 | Controles y tablas hechos a mano | [V] U-20, U-21 | Medio | Componentes comunes | Medio |
| 45 | `pdfplumber` no declarado; prueba que falla según la zona horaria | [V] C-20, T-01 | Medio | Declararlo; usar UTC | Nulo |
| 46 | 8 pruebas que se omiten si cambia la demo; aserciones que no prueban nada | [V] T-02 … T-07 | Medio | Fixture propia; aserciones exactas | Bajo |
| 47 | Sin pruebas de frontend ni CI | [V] anexo C §5 | Medio | Vitest, Playwright y CI | Bajo |
| 48 | SSCC y lote de producción inexistentes | [V] I-15, L-23 | Bajo-medio | Decisión 4 | Bajo |
| 49 | Compatibilidad con 0081 extendida (alias, sinónimos, columnas congeladas) | [V] C-18, D-25 | Bajo | Plan de limpieza | Medio |
| 50 | Código y traducciones sin uso | [V] C-01 … C-15 | Bajo | Plan de limpieza | Nulo |

El resto de los hallazgos menores está en los anexos: D-11, D-14 … D-24, I-12 … I-17,
L-19 … L-25, U-14 … U-23 y C-16 … C-22.

---

## 7. Plan de limpieza

Antes de cada eliminación se verificaron todas las formas de referencia: imports
directos e indirectos, strings dinámicos, router, demo, scripts, migraciones,
pruebas, documentación y el canal de cambios (anexo C §1, anexo D §4).

| Elemento | Dependencias verificadas | Acción | Cuándo |
|---|---|---|---|
| `trabajos._soltar` | Sin llamadas; el `UPDATE` se repite en 3 sitios | Usarla en esos 3 sitios | Etapa 7 |
| `render.vacio`, `campos.por_clave` | Sin uso | Eliminar | Etapa 7 |
| `condiciones.cumple` | Sin uso, pero 3 sitios hacen lo mismo a mano | Usarla en esos sitios | Etapa 4 |
| 11 constantes sin lectura (anexo C, C-05) | — | Las de etiquetado pasan a ser la fuente de los `Literal` y los CHECK; las de empaque se eliminan | Etapa 7 |
| Re-exportaciones de `reglas.py` | 9 sin uso a través de `reglas` | Importar directo de `comun.condiciones` | Etapa 7 |
| `POST /tipos/sugeridos` | Sin uso | Usarlo en el primer uso o retirarlo | Etapa 6 |
| `GET /usos` | Sin uso; solo como clave de evento en `alCambiar` | Retirar | Etapa 6 |
| `/trabajos/{id}/cancelar`, `/usos/{id}/historial` | Solo pruebas | **Conservar** y exponer en la pantalla | Etapa 6 |
| `/resolver` | 7 pruebas y el e2e | **Conservar**: base de «Probar» | Etapa 4 |
| `usos.TEXTOS_0076` | Lo lee el extractor de i18n | **Conservar**, con un comentario | — |
| ~229 traducciones de etiquetado y empaque huérfanas (861 en total) | Lista en el anexo C | Eliminar + prueba de sobrantes | Etapa 7 |
| Formularios duplicados de familia, diseño especial, cambiar familia y guía de pasos | Ver §4.4 | Fusionar | Etapa 6 |
| Segundo `Resolvedor` en `planear` | Su resultado no se usa | Eliminar | Etapa 4 |
| Empaquetador ZIP del trabajo y `_seguro` duplicado | Ver CD-07 | Unificar | Etapa 3 |
| Alias `FamiliaEtiquetado` / `CategoriaEtiquetado`, sinónimos `familia_etiquetado_id`, propiedades híbridas del producto | ~60 usos | Renombrar a `grupo_*` y mover la lógica a `grupos.arbol` | Etapa 7 |
| Tablas `familias_etiquetado`, `categorias_etiquetado` y 7 columnas congeladas con sus índices y 9 FK | Solo modelos «Anterior», `referencias.py`, el downgrade de 0081 y 2 pruebas de migración | **Eliminar** con la migración 0083: verifica antes, tiene downgrade reconstructivo y requiere respaldo | Etapa 8 |
| `legado_familia_id`, `legado_categoria_id` | Solo el downgrade de 0081 | Conservar hasta renunciar a volver a 0080 | Después de la etapa 8 |
| `casepack`, `inner_pack` | Etiquetado, packing list, documentos e importación ERP | **Conservar.** Primero hacer que el etiquetado lea la receta | Etapa 5 |
| Datos del artículo copiados en la línea de OC y de factura | Instantánea de los documentos | **Conservar** | — |
| Índices redundantes o de columnas congeladas | Anexo D, D-19 | Eliminar | Etapa 8 |
| `.pyc` de módulos borrados | Restos locales no versionados | Borrar localmente | — |

---

## 8. Plan de pruebas

El detalle de los escenarios está en el anexo C §6.

**Infraestructura (antes de todo):**
- **Dependencias:** declarar `pdfplumber` y `pillow`.
- **CI** con tres corridas:
  - SQLite con `TZ=America/Guatemala`;
  - PostgreSQL, para RLS y FK compuestas;
  - frontend.
- **Marcador `migracion`** para separar las pruebas lentas.
- **Fixture `escenario_empaque`**, que reemplaza los 8 `skip` que hoy dependen de la
  demo. Incluye:
  - OC A y B con el mismo artículo en dos posiciones y en las dos OC;
  - packing list solo de A, packing list consolidado de A y B, y uno en borrador;
  - pallet con cajas e inners, y una caja mixta;
  - prepack de curva y kit;
  - líneas en kg con 2,5, en PAR con 0 y con la cantidad nula.

**Escenarios que hoy no se prueban:**

| Nivel | Escenario |
|---|---|
| Unitarias | <ul><li>Paridad de las condiciones y del formato entre el navegador y el servidor, con una tabla de casos compartida.</li><li>Validación única de los grupos («NIÑO», orden, descripción, padre).</li><li>`derivar` de recetas de 1 a 3 niveles.</li><li>Paridad SQL frente a Python de la familia efectiva.</li></ul> |
| Integración | <ul><li>Packing list consolidado sin cajas duplicadas.</li><li>El mismo artículo en varias posiciones y OC con cada alcance.</li><li>Cantidades cero, nulas y decimales.</li><li>Prepack por unidad.</li><li>Prioridad combinada con «no lleva».</li><li>Archivar el diseño vigente.</li><li>Segundo plano con datos cambiados.</li><li>Una parte con error no detiene las demás.</li><li>ZIP del trabajo igual al del lote.</li><li>Código de caja igual al del packing list.</li><li>Reempacar después de imprimir avisa.</li><li>OC cancelada rechazada.</li></ul> |
| API y permisos | <ul><li>El proveedor no ve la matriz, la simulación, otros proveedores, imágenes ajenas ni datos reservados.</li><li>`dpi` y `hoja` inválidos dan 422.</li><li>Reimprimir es idempotente.</li><li>Un nodo editado desde las dos rutas sigue las mismas reglas.</li><li>Dos `PATCH` concurrentes del mismo trabajo.</li></ul> |
| Interfaz | <ul><li>Vitest de `etiquetas.js`.</li><li>Asistente: «0 líneas» no equivale a «toda la OC»; «Siguiente» se bloquea si hay errores.</li><li>Primer uso atómico.</li><li>Playwright del recorrido completo a 1440 y 390 px.</li></ul> |
| Regresión | <ul><li>Una prueba por hallazgo corregido, con su id.</li><li>sha256 de 3 lotes de referencia.</li><li>Techo de consultas para la matriz, las categorías, `planear` y las familias.</li><li>Traducciones sobrantes.</li></ul> |

**Consistencia con los registros originales:** en cada prueba de generación se
compara la instantánea con la fuente correcta:
- desde la OC, con la posición;
- desde el packing list, con la línea de factura y la numeración del empaque.

---

## 9. Plan de implementación por etapas

Cada etapa:
- es un PR propio;
- deja la suite verde (backend, frontend, migraciones de ida y vuelta);
- agrega las pruebas de sus hallazgos;
- no cambia el comportamiento de otros módulos salvo lo indicado.

Las etapas 0 a 5 no cambian la estructura de pantallas.

| Etapa | Contenido | Depende de | Riesgo | Criterios de aceptación |
|---|---|---|---|---|
| **0 · Base de pruebas** | Dependencias declaradas, prueba de zona horaria, fixture `escenario_empaque` sin `skip`, marcador `migracion`, aserciones exactas (T-01 … T-07, C-20, C-21) | — | Nulo | Suite verde con `TZ=America/Guatemala`; 0 `skip` por la demo |
| **1 · Seguridad** | L-01, L-02, D-01, L-05, L-06 (tope y segundo plano), L-10, L-15 | 0 | Bajo a medio | Pruebas de proveedor: 403 o datos filtrados; ninguna entrada da 500; un trabajo grande no bloquea la petición |
| **2 · Lo que se imprime** | I-01, I-02, L-04, I-05, L-03 (decisión 1), L-12, I-08/D-10, L-09, L-13 | 0 | Medio | Código y total de caja iguales a los del packing list; sin cajas duplicadas; la cantidad escrita se aplica o no se ofrece; los anulados no cuentan |
| **3 · Trazabilidad** | D-02, D-03, D-04/I-07 (aviso al reabrir o reempacar), D-06, L-14, L-16, L-26, D-05, D-16, un solo empaquetador (CD-07) | 2 | Medio | Cada ítem guarda la OC, el bulto y la regla; reempacar avisa; anular conserva el vínculo; ZIP de trabajo igual al de lote |
| **4 · Un solo motor** | Partir los archivos (anexo L §4); una función de valores y elección (L-07) con «Probar»; L-08, L-18/I-10, L-19, L-11; catálogo común de condiciones (I-09, I-13); paridad navegador/servidor (CD-05, CD-06); `grupos.arbol` como único servicio (CD-01 … CD-04); `en_familia` por id (I-11) | 0 | Medio | Ficha, resumen, Probar y trabajo dan el mismo resultado en las pruebas; misma validación por cualquier ruta |
| **5 · Empaque y unidades** (antes «fase 4») | Datos del packing list desde la factura (I-03); receta en la etiqueta y su validación (I-06, D-13); unidades (I-04, decisión 2); SSCC y lote (I-15, decisión 4); D-09 | 2, 4 | Medio | Prepack por unidad según la opción; error de unidades distintas; inner y pallet desde la receta |
| **6 · Módulo central** | Secciones, Historial, bandeja con Continuar y Descartar, Por aprobar, celda en panel como único editor, atajos con contexto y regreso, Grupos de producto como dueño (U-01 … U-23); endpoints sin uso | 3, 4 | Medio | Recorrido (a) en 7 acciones; 1 lugar para cada edición; sin desbordes a 390 px; Playwright verde |
| **7 · Integridad y limpieza de código** | D-07, D-08, D-11, D-12, D-14, D-18 … D-20, D-24; código y traducciones sin uso; alias y sinónimos renombrados | 4 | Bajo a medio | `alembic check` limpio; pruebas de paridad; 0 traducciones sobrantes |
| **8 · Corte de la compatibilidad** (antes «fase 5») | Migración 0083 que elimina las tablas y columnas congeladas, con verificación previa y downgrade reconstructivo | 7, respaldo | Medio | Ida y vuelta 0075↔head y 0080↔head; sin referencias a «Anterior» |

---

## 10. Decisiones que necesito antes de implementar

1. **Cantidad escrita en Revisar:** ¿se aplica a cualquier etiqueta como ajuste
   manual registrado, o solo se puede escribir en los tipos «a mano»?
2. **Prepacks y kits:** con «una por unidad», ¿se etiqueta cada par o componente, o
   cada curva? Mi recomendación es una opción en el tipo de etiqueta, por defecto
   por componente para colgantes y precios.
3. **Proveedor:** ¿debe ver algo de la configuración (reglas, matriz)? Recomiendo
   que no, y que vea solo sus trabajos e historial. ¿Los lotes que el equipo
   interno generó para sus OC también?
4. **SSCC y lote de producción:**
   - ¿Hacen falta ya?
   - Para el SSCC: prefijo GS1 de la empresa, serie y dígito verificador.
   - Para el lote: ¿por línea de OC, por caja o por recepción?
5. **Datos reservados en etiquetas:** si un rol no puede ver precios pero el diseño
   imprime el precio, ¿la etiqueta lo imprime igual (lo impreso manda) o sale
   vacío?
6. **Packing list con datos distintos de la OC:** ¿la etiqueta de un bulto debe
   llevar los datos de la factura (UPC, país de origen y destino corregidos)?
   Recomiendo que sí.
7. **Grupos de producto:** ¿basta `etiquetas.familias` para mover nodos que también
   cambian las reglas de empaque, o solo `catalogos.editar`?
8. **Orden de las etapas:** ¿empiezo por la 0 y la 1 (pruebas y seguridad), como
   recomiendo, o prefieres otra prioridad?

---

## 11. Decisiones tomadas (20 de octubre de 2026) y plan actualizado

**Cambio de enfoque.** El etiquetado tiene solo dos orígenes:
- **El artículo**, sin documento.
- **La packing list**, completa o con lo que se elija.

La OC deja de ser un origen; sus datos se leen a través de la packing list
(línea de la packing list → línea de factura → posición de la OC).

**Datos propios de cada fuente:**
- Cada documento (OC, packing list) tiene sus datos propios.
- Los datos del artículo son una referencia a la **versión del artículo que usó ese
  documento**, no a la versión actual.

**Se aprobaron todas las opciones recomendadas:**

| # | Decisión |
|---|---|
| 1-2 | Versión del artículo guardada en cada línea de documento. Se toma al crear la línea de la OC y pasa a la factura. La packing list usa la de la factura. Mientras la packing list está en borrador hay un botón «Actualizar con el artículo actual». A pedido del usuario, se guarda como **versiones del artículo** (tabla propia con la foto completa), a las que apunta cada línea. |
| 3 | Las etiquetas sin packing list usan los datos actuales del artículo. Las reglas con condiciones de OC o de packing list no aplican. |
| 4 | De la packing list se puede elegir: toda, por nivel, por cajas o por líneas. |
| 5-6 | Etiquetas de artículo: por unidad empacada, por línea, una por cada etiqueta distinta o a mano por línea. El tipo de etiqueta trae el modo por defecto y se cambia en cada trabajo. Desde el artículo solo: una por artículo distinto o a mano. |
| 7 | Etiquetas de caja: por defecto una por caja física; también «una por caja distinta» o a mano. |
| 8 | Las etiquetas reales salen solo de una packing list finalizada; en borrador, solo en modo prueba. |
| 9 | Se puede reempacar después de imprimir: avisa y marca las etiquetas como desactualizadas. |
| 10-12 | El prepack y el kit son una unidad de empaque, con su propia etiqueta. Sus componentes se etiquetan según la curva, con la cantidad exacta o una por componente distinto, a elegir en el trabajo con un valor por defecto en el tipo. |
| 13 | La regla «para una OC» pasa a ser una condición (número de OC). Se agrega la condición «número de packing list». |
| 14 | La hoja de contenido solo se genera de la packing list. |
| 15-16 | Lo generado desde una OC queda como historial de solo lectura. Los botones de la OC pasan a «Etiquetas de sus packing lists». |
| 17 | El proveedor no ve la configuración; solo ve sus trabajos y su historial. |
| 18 | El SSCC se genera ya, uno por caja; el lote de producción queda para más adelante. |
| 19 | Lo impreso manda: el precio se imprime, pero se oculta en las pantallas y el historial de los roles que no lo ven. |
| 20 | Solo el permiso de catálogos mueve familias. |
| 21 | Primero la base de pruebas y la seguridad. |

**Pedido adicional: producto genérico.**
- Cualquier tipo de producto (calzado, químicos, materias primas, electrodomésticos,
  alimentos…).
- Atributos dinámicos configurables.
- Versiones del producto y del artículo.
- Nada fijo en el código: tipos, atributos, unidades y presentaciones se configuran.
- Diseño extensible.

**Lo que ya existe y se reutiliza:**
- Campos propios por entidad (`definiciones_campo` + `extra`).
- Atributos de variante configurables (`atributos_variante`).
- Ficha técnica en JSON.
- Árbol de grupos de producto.
- Unidades de medida configurables.
- Recetas de empaque.

**Lo que es rígido hoy:**
- Columnas de calzado en el artículo (estilo, color, talla).
- Tipo `SOLIDO/PREPACK` y unidades `PAR/UN/CJ` en el código (unas 70 referencias).
- El producto como «estilo-color de un proveedor».
- No hay versiones del artículo a las que un documento pueda apuntar.

**Plan por etapas (reemplaza al §9).** Cada etapa es uno o varios commits con la
suite en verde.

| Etapa | Contenido |
|---|---|
| 0 | Base de pruebas: dependencias, zona horaria, aserciones exactas |
| 1 | Seguridad: L-01, L-02, D-01 (con la decisión 19), L-05, L-06, L-10, L-15 |
| 2 | Producto genérico: <ul><li>catálogo de atributos con tipo de dato, nivel (producto o variante), unidad, opciones y obligatoriedad;</li><li>atributos por grupo de producto, heredados en el árbol;</li><li>valores de los atributos del producto;</li><li>unidades con factor de conversión;</li><li>el tipo de artículo (sólido, curva, kit) como configuración;</li><li>quitar lo fijo del código donde se pueda sin romper los documentos.</li></ul> |
| 3 | Versiones del artículo: <ul><li>tabla `articulo_versiones` con la foto completa (artículo, atributos y producto) y su huella;</li><li>versión nueva automática cuando cambia algo;</li><li>las líneas de la OC y de la factura apuntan a su versión;</li><li>«Actualizar con el artículo actual» en la packing list en borrador.</li></ul> |
| 4 | Orígenes del etiquetado: artículo y packing list; selección; modos de cantidad; datos desde la factura y la versión del artículo; condiciones `oc.*`, `pl.*` y `articulo.*`; excepción de OC convertida en condición; hoja de contenido de la packing list; atajos desde la OC |
| 5 | Empaque físico: <ul><li>numeración y total de bultos del empaque (I-01, I-02) y caja mixta;</li><li>receta y validación por niveles;</li><li>prepack y kit como unidad con etiquetas de sus componentes;</li><li>SSCC;</li><li>reempacar marca las etiquetas como desactualizadas;</li><li>identidad estable del bulto.</li></ul> |
| 6 | Trazabilidad: D-02, D-03, D-06, L-12, L-13, L-14, L-16, L-26, D-05, D-16, un solo empaquetador |
| 7 | Un solo motor (L-07 y relacionados) y Grupos de producto como único dueño |
| 8 | Módulo central de pantallas (§4) |
| 9 | Integridad y limpieza de código |
| 10 | Corte de la compatibilidad con las tablas congeladas |
