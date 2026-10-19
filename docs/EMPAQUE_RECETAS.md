# Recetas de empaque y reglas de empaque

Cómo se empaca cada artículo (inner pack, caja, pallet…) y qué receta toma cada
línea de OC. Es la base para que el packing list y el etiquetado trabajen sobre
la misma estructura física, sin casepack e inner pack fijos ni roles adivinados.

Pantalla: **Configuración → Datos maestros → Recetas de empaque**
(`/empaque/recetas`), con tres vistas: Recetas, Reglas y Probar. En la OC,
cada línea muestra su receta en la columna **Empaque**.

## 1. Conceptos

| Concepto | Qué es | Dónde vive |
|---|---|---|
| Tipo de empaque | Unidad logística configurable (inner, caja, pallet, bolsa, display…) y qué puede contener | Datos maestros (`tipos_empaque`, `tipo_empaque_contiene`) |
| Receta | Jerarquía de N niveles armada con esos tipos. Cada nivel dice cuántas unidades del nivel de abajo lleva; el primero, cuántas unidades del artículo | `recetas_empaque`, `receta_niveles` |
| Regla de empaque | «Para [toda la empresa, familia, producto o artículo] si [condiciones] → usar [receta]» | `reglas_empaque` |
| Receta de la línea | La receta que tomó una línea de OC, de dónde salió y una **foto** congelada de sus niveles | `posiciones_oc.receta_*`, `factura_lineas.receta_*` |

Ejemplo de receta, del nivel más externo al más interno:

| Nivel | Tipo | Lleva | Unidades del artículo |
|---|---|---|---|
| 3 | Pallet | 40 del nivel 2 | 960 |
| 2 | Master carton | 2 del nivel 1 | 24 |
| 1 | Inner pack | 12 unidades del artículo | 12 |

## 2. Decisiones respecto de la propuesta original

1. **La curva no es parte de la receta.** Un prepack ya existe como artículo,
   con su curva (`prepacks` y `prepack_componentes`). Su unidad es la curva, así
   que «una curva por caja» es una receta normal: Caja × 1. Así la composición
   por talla vive en un solo lugar y la receta solo describe el empaque.
2. **El «por defecto» del proveedor o de la empresa es una regla más.** Por
   ejemplo, «Toda la empresa → Caja 12» o «Toda la empresa si proveedor = Vans
   → Vans 6×4». No hace falta un cuarto mecanismo.
3. **El casepack de la OC cuenta como dato de la compra (origen DATOS).** Si la
   OC trae casepack e inner pack, se usa la receta con esa forma o se crea una
   automática. Esto respeta lo que manda el ERP y evita que una regla lo pise.
4. **Una foto por línea.** La línea guarda los niveles de la receta tal como
   estaban al asignarla, igual que una factura guarda el precio: cambiar la
   receta después no altera OC emitidas ni facturas.
5. **Un solo evaluador de condiciones** (`app/modulos/comun/condiciones.py`):
   lo usan ya el empaque y el etiquetado. Es el primer paso del motor de reglas
   común (fase 3).
6. **La validación viene del catálogo.** «Un inner pack no puede contener un
   master carton» se rechaza porque el tipo no lo tiene en «Puede contener».
   La pantalla solo ofrece, en cada nivel, los tipos que caben.

## 3. Quién decide la receta de una línea de OC

| Prioridad | Quién decide | Origen guardado |
|---|---|---|
| 1 | El packing list real (lo armado o cargado desde Excel) | — (fase 2) |
| 2 | La receta elegida a mano en la línea | `MANUAL` |
| 3 | El casepack e inner pack que trae la OC | `DATOS` |
| 4 | La regla de empaque que aplica | `REGLA` |

**Qué regla gana:**
- La más específica: artículo, luego producto, luego la familia más profunda y
  por último toda la empresa.
- A igual destino, una regla con condiciones gana sobre una sin condiciones.
- Si aun así empatan, gana la que está más arriba en la lista. El orden se
  cambia arrastrando o con las flechas, también con teclado.

**Condiciones disponibles:**
- **OC:** proveedor, sociedad, centro, centro destino, país destino (del centro
  destino), país de origen, incoterm y puerto.
- **Línea:** marca, grupo, categoría, estilo, color, talla, unidad, cantidad,
  bodega y sólido/prepack.
- **Artículo:** SKU.

**Cuándo se aplica:**
- Al crear o actualizar una OC (archivo, formulario o asistente).
- Al guardar una regla, con la casilla «Aplicarla a esas líneas».
- Con «Aplicar las reglas» en Probar.

Nunca se tocan las líneas facturadas ni las que tienen receta a mano o del
casepack.

## 4. Convivencia con casepack e inner pack (alternativa A)

- La migración **0081** crea una receta automática (`CP12`, `CP12-IN6`…) por
  cada combinación distinta de casepack e inner pack de los sólidos. La arma
  con los tipos del catálogo: el bulto que lleva producto y, si hay inner, el
  interior que puede ir dentro. Luego la enlaza a sus líneas y facturas con
  origen `DATOS`.
- Quedan sin receta, como hoy:
  - las combinaciones que no cierran (casepack que no es múltiplo del inner);
  - los prepacks;
  - las empresas sin tipos de empaque.
- Las columnas `casepack` e `inner_pack` no se borran. Con una receta, en los
  sólidos se calculan de ella:
  - casepack = unidades del primer nivel que cuenta como bulto;
  - inner = unidades del nivel justo dentro de él.

  Así el packing list, los documentos y los exportes siguen funcionando igual.
- El downgrade quita solo lo agregado.

## 5. Packing list

- **Empacar según la receta** (opción recomendada cuando las líneas tienen
  receta): cada fila se arma con todos los niveles de su receta en un paso.
  - Se crean N unidades completas del nivel más externo, con todo lo de adentro.
  - Lo que sobra va en una unidad parcial que lleva lo que cabe en los niveles
    de abajo: pallet parcial con sus cajas y, si hace falta, una caja o un
    inner parcial.
  - Opciones: con o sin los niveles opcionales (el pallet), y lo que no llena
    el nivel más interno queda en una unidad parcial o sin empacar.
  - Ejemplo: 1008 pares con la receta Pallet 40 × Master 2 × Inner 12 dan
    2 pallets (1 parcial), 42 masters y 84 inners.
- **Totales por tipo de empaque.** La cabecera muestra «Pallet 2 · Master
  carton 42 · Inner pack 84» con los nombres del catálogo, no «Cajas» y
  «Pallets» fijos.
- **Sin roles adivinados para las líneas con receta.** El empaque automático
  por plantilla toma de la receta cuál es la caja y cuál el inner. Sin receta
  sigue como antes: el primer tipo que cuenta como bulto y el interior que
  puede contener.
- **Inner pack.** Definir el inner pack en el packing list también actualiza
  la receta de la línea de factura.

## 6. API

| Ruta | Para qué |
|---|---|
| `GET/POST /api/recetas-empaque`, `GET/PATCH/DELETE /api/recetas-empaque/{id}` | Recetas. Una receta en uso no se borra: se desactiva |
| `POST /api/recetas-empaque/calcular` | Totales en vivo de una receta sin guardar |
| `GET/POST /api/reglas-empaque`, `PATCH/DELETE /api/reglas-empaque/{id}`, `PUT /api/reglas-empaque/orden` | Reglas. Se dan de baja, no se borran |
| `GET /api/reglas-empaque/campos` | Datos de las condiciones, operadores y familias |
| `POST /api/reglas-empaque/probar` | Receta de cada línea de una OC hoy y según las reglas, regla por regla |
| `POST /api/reglas-empaque/impacto` | Cuántas líneas abiertas cambiarían al guardar o quitar una regla |
| `POST /api/reglas-empaque/reaplicar` | Aplica las reglas a las líneas abiertas que las siguen |
| `PUT /api/ordenes/{oc}/posiciones/{id}/receta` | Elegir la receta a mano o devolverla a las reglas |
| `POST /api/packing-lists/{id}/empaque-receta/previa` y `POST /api/packing-lists/{id}/empaque-receta` | Qué armaría y armar el árbol de cada fila según su receta |

Permisos:
- Recetas y reglas: `catalogos.ver` y `catalogos.editar`.
- Receta de una línea: `oc.empaque`.

## 7. Fases

| Fase | Contenido | Estado |
|---|---|---|
| 1 | Recetas, reglas de empaque, receta en la línea de OC y conversión del casepack | **Hecha** (este documento) |
| 2 | Packing list genérico: «Empacar según la receta» con N niveles, totales por tipo de empaque, caja e inner tomados de la receta de la línea | **Hecha en lo principal**. Pendiente: columnas de la tabla de cajas por nivel y el alta manual de un tipo sin receta |
| 3 | Grupos de producto compartidos (familias y categorías en un árbol) y motor de reglas común | Pendiente; el evaluador de condiciones ya es común |
| 4 | Etiquetado sobre el árbol físico: «¿Dónde se pega?», reglas en lista y Probar unificado | Pendiente |
| 5 | Limpieza: retirar columnas y pantallas viejas, con migración e informe | Pendiente |
