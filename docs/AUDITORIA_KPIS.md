# Auditoría integral de KPIs, indicadores y tableros

Fecha: 13/10/2026 · Rama: `claude/focused-cerf-5qb8tf` (commit `a981f7a`) · Fase: **solo auditoría** (no se cambió
código, base de datos, fórmulas ni pantallas).

## Cómo se hizo y cómo leer este informe

- **Lectura del código** de punta a punta: servicios y endpoints del backend (`backend/app/modulos/**`), modelos
  (`backend/app/modelos/**`), migraciones, componentes y pantallas del frontend (`frontend/src/**`).
- **Ejecución real** sobre una **copia** de la base de demostración (`/tmp/claude-0/audit/audit.db`; la base del proyecto
  no se tocó). Se midieron los indicadores, luego se introdujeron casos que la demo no trae (una OC cancelada, una en
  borrador, una OC en EUR, una factura reabierta y 9 embarques en tránsito más) y se volvieron a medir.
- **Medición de consultas SQL y tiempo** de cada endpoint de indicadores con la base de demostración.

Cada hallazgo lleva su grado de certeza:

| Marca | Significado |
|---|---|
| **[E]** | Defecto **comprobado ejecutando** el sistema (con el resultado medido). |
| **[C]** | Defecto **comprobado leyendo el código** (la lógica no admite otra lectura), sin reproducirlo con datos. |
| **[S]** | **Sospecha**: requiere una prueba con datos o confirmar la intención de negocio. |
| **[M]** | **Mejora opcional**: no es un error. |

Rutas: `backend/app/…` se abrevia `app/…`; `frontend/src/…` se abrevia `src/…`.

---

## 1. Resumen ejecutivo

**Calidad general: media.** El sistema tiene una base sólida —un catálogo de indicadores con fórmula, fuente y período
declarados (`app/modulos/seguimiento/indicadores.py`), aislamiento por organización automático en todas las consultas del
ORM y respaldo con RLS en PostgreSQL, permisos por indicador y datos ocultos por rol—, pero **los mismos conceptos se
calculan en varios lugares con definiciones distintas**, y algunos cálculos **mezclan monedas, unidades de medida o
estados** de forma que la cifra puede engañar.

Lo más importante:

1. **Montos de distintas monedas sumados o descartados sin aviso [E].** La columna «Por facturar» por proveedor de Inicio
   suma USD y EUR como si fueran la misma moneda; la tarjeta «Por facturar» muestra solo la moneda mayor pero dice
   «en 6 OC» contando también las de otras monedas; «Monto facturado» descarta en silencio las facturas que no están en
   la moneda base. El generador de reportes suma importes de distintas monedas al agrupar.
2. **Un mismo indicador, tres números [E].** «Por facturar» (Inicio) da USD 40,129 y «Saldo por facturar» (Indicadores)
   USD 41,543 sobre los mismos datos de la demo. «Embarques en camino» da **8** en Inicio, **10** en Indicadores y **1** en
   Seguimiento con 10 embarques en tránsito. «Liberación logística a tiempo» da 92 % y 91,7 %. «OC en riesgo» da 1 o 2.
3. **Documentos que no deberían contar [E].** Seguimiento y Lead times incluyen OC **canceladas, en borrador o
   rechazadas**: tras cancelar una OC y pasar otra a borrador, «Órdenes de compra» siguió en 14. Indicadores sigue
   contando como **finalizada** (y su monto como facturado) una factura **reabierta** para corrección; Inicio no.
4. **Conteos topados [E].** «Embarques en camino» de Inicio nunca pasa de 8 porque se calcula sobre la lista del panel,
   que se corta en 8 (`app/modulos/seguimiento/dashboard.py:232`).
5. **Porcentajes que suman unidades distintas [C].** «% facturado» de Seguimiento suma pares, unidades y cajas en el
   numerador y el denominador; el «% facturado» de la lista de OC usa otra base (valor), así que ambos difieren.
6. **Fugas de alcance de datos [C].** Paneles de Inicio (embarques, unidades de carga, salidas y llegadas) no aplican el
   alcance por sociedad/centro/transportista que sí aplica el módulo de transporte; el estado de cuenta de un tercero
   suma pagos de sociedades que el usuario no puede ver.
7. **Sin indicadores financieros de cobro/pago**, aunque el módulo comercial ya tiene los datos (documentos emitidos y
   recibidos, vencimientos, pagos, aplicaciones y notas de crédito): no hay cuentas por cobrar, vencidos ni antigüedad.
8. **Rendimiento aceptable hoy, frágil mañana [E].** Inicio hace **127 consultas** y carga **todas** las facturas no
   canceladas de la historia en cada visita; los indicadores de lead time analizan **todas** las OC en memoria.

**Decisión propuesta**: corregir primero los P0 (monedas, estados incluidos por error, permisos y el tope de 8), luego
**unificar las definiciones en un único servicio de métricas** que usen Inicio, Indicadores, Seguimiento y Reportes, y
después agregar el bloque financiero (cuentas por cobrar y por pagar) que hoy no existe.

Resultado del inventario (§2–3): **87 indicadores o cifras** con valor de gestión. Clasificación: **Mantener 23 ·
Corregir 38 · Mejorar 8 · Combinar 15 · Eliminar 2 · Reemplazar 1**. Prioridad: **P0 12 · P1 25 · P2 21 · P3 29**.
Se recomiendan **12 indicadores nuevos** (§6), sobre todo financieros, que el sistema ya puede calcular.

---

## 2. Inventario completo de los indicadores

Se encontraron **87 indicadores o cifras** con valor de gestión, en 9 grupos. Además existen contadores de navegación (pestañas, «Columnas 7/11», paginación, insignias de menú) que **no** se tratan como KPI.

**Actualización (común a todos):** ningún indicador se guarda. Todos se calculan **al abrir la pantalla**, con consultas directas a la base y con el alcance de datos del usuario. No hay caché, tablas de resumen ni procesos programados. Los de Indicadores calculan además la serie de tramos iguales para la tendencia (8 tramos para 7 días, 6 para 30, 4 para 90 y 3 para 365).

La fórmula exacta, la fuente (archivo:línea y endpoint) y los filtros de cada uno están en su **ficha** (Anexo A, mismo identificador).

### Inicio — franja de indicadores

| ID | Indicador | Dónde aparece | Qué decisión apoya | Período | Quién lo consulta |
|---|---|---|---|---|---|
| I01 | Por facturar | Inicio (franja) | Cuánto valor de OC liberadas falta facturar; priorizar proveedores y OCs. | Foto de hoy | Dirección, compras, proveedor |
| I02 | Documentos en curso | Inicio (franja) | Cuánto trabajo documental está abierto. | Foto de hoy | Proveedor, equipo de facturación |
| I03 | Lista para embarcar | Inicio (franja, interno) | Qué facturas ya pueden asignarse a un contenedor. | Foto de hoy | Logística |
| I04 | Embarques en camino | Inicio (franja) | Cuánta carga viaja ahora. | Foto de hoy | Logística, dirección |
| I05 | OC en riesgo de atraso | Inicio (franja) | Qué OC llegarán tarde a tienda para actuar antes. | Foto de hoy | Compras, logística |

### Inicio — «Necesita su atención», pasos y paneles

| ID | Indicador | Dónde aparece | Qué decisión apoya | Período | Quién lo consulta |
|---|---|---|---|---|---|
| I06 | Productos que bloquean facturas | Inicio › Necesita su atención | Qué productos sin partida aprobada impiden finalizar facturas. | Foto de hoy | Clasificación, proveedor |
| I07 | Productos por clasificar | Inicio › Necesita su atención (interno) | Cola de fichas que el equipo debe revisar. | Foto de hoy | Clasificación |
| I08 | Fichas devueltas | Inicio › Necesita su atención (proveedor) | Fichas que el proveedor debe corregir. | Foto de hoy | Proveedor |
| I09 | Facturas por finalizar | Inicio › Necesita su atención | Facturas abiertas que frenan el embarque. | Foto de hoy | Proveedor, facturación |
| I10 | Listas de empaque incompletas | Inicio › Necesita su atención | PL por empacar o finalizar. | Foto de hoy | Proveedor, bodega |
| I11 | OC con XF esta semana | Inicio › Necesita su atención | Qué despachos vencen en 7 días con cantidad por facturar. | Próximos 7 días | Proveedor, compras |
| I12 | OC con XF vencida | Inicio › Necesita su atención | Despachos atrasados con saldo por facturar. | Foto de hoy | Compras, proveedor |
| I13 | Listas de empaque sin unidad de carga | Inicio › Necesita su atención | PL finalizadas esperando contenedor. | Foto de hoy | Logística |
| I14 | Embarques que salen esta semana | Inicio › Necesita su atención | Preparar salidas próximas. | Próximos 7 días | Logística |
| I15 | OC en riesgo de llegar tarde | Inicio › Necesita su atención | Igual que I05. | Foto de hoy | — |
| I16 | Llegadas esta semana | Inicio › Necesita su atención | Prever recepciones. | Próximos 7 días | Bodega, logística |
| I17 | Siguientes pasos (cantidad) | Inicio | Lista priorizada de tareas. | Foto de hoy | Todos |
| I18 | Panel «Embarques» (avance del viaje, cajas) | Inicio | Ver dónde va la carga. | Foto de hoy | Logística, proveedor |
| I19 | Unidades de carga en planificación (% llenado) | Inicio (interno) | Aprovechar el contenedor antes de que salga. | Foto de hoy | Logística |

### Inicio — «Desempeño» y «Por proveedor»

| ID | Indicador | Dónde aparece | Qué decisión apoya | Período | Quién lo consulta |
|---|---|---|---|---|---|
| I20 | Facturado (período) | Inicio › Desempeño | Cuánto se facturó en el período elegido. | Período elegido | Dirección, finanzas, proveedor |
| I21 | Listas de empaque finalizadas (período) | Inicio › Desempeño | Ritmo de empaque. | Período elegido | Bodega, proveedor |
| I22 | Embarques por llegar (período) | Inicio › Desempeño | Cuántos embarques llegan en el período. | Período elegido | Logística |
| I23 | Gráfica «Valor facturado» | Inicio › Desempeño | Tendencia de la facturación. | Período elegido | Dirección, finanzas |
| I24 | Dónde está la mercancía | Inicio › Desempeño | En qué etapa está la cantidad (por facturar → embarcada). | Foto de hoy | Dirección, logística |
| I25 | Tabla «Por proveedor» (por facturar, en proceso, PL abiertas, listas, en camino) | Inicio (interno) | Comparar la carga pendiente por proveedor. | Foto de hoy | Compras, dirección |

### Indicadores (catálogo de tableros)

| ID | Indicador | Dónde aparece | Qué decisión apoya | Período | Quién lo consulta |
|---|---|---|---|---|---|
| T01 | OC pendientes de aprobación | Indicadores › Compras | Cola de aprobación. | Foto de hoy | Aprobadores |
| T02 | OC aprobadas | Indicadores › Compras | Volumen de aprobación. | Período + tendencia | Compras |
| T03 | Días para aprobar | Indicadores › Compras y Resumen | Rapidez del circuito de aprobación. | Período + tendencia | Dirección de compras |
| T04 | Saldo por facturar | Indicadores › Compras y Resumen | Compromiso de compra pendiente de facturar. | Foto de hoy | Dirección, finanzas, compras |
| T05 | OC con fecha de despacho vencida | Indicadores › Compras | Despachos atrasados. | Foto de hoy | Compras, proveedor |
| T06 | Facturas finalizadas | Indicadores › Facturación | Volumen de facturación. | Período + tendencia | Facturación |
| T07 | Monto facturado | Indicadores › Facturación y Resumen | Facturación del período. | Período + tendencia | Dirección, finanzas |
| T08 | Facturas en curso | Indicadores › Facturación | Trabajo abierto. | Foto de hoy | Facturación |
| T09 | Listas de empaque en curso | Indicadores › Facturación | Empaque abierto. | Foto de hoy | Bodega, proveedor |
| T10 | Embarques en tránsito | Indicadores › Logística | Carga viajando. | Foto de hoy | Logística |
| T11 | Arribos | Indicadores › Logística | Volumen recibido en puerto. | Período + tendencia | Logística |
| T12 | Arribos a tiempo | Indicadores › Logística y Resumen | Cumplimiento del transportista. | Período + tendencia | Logística, dirección |
| T13 | Días de tránsito | Indicadores › Logística | Duración del viaje. | Período + tendencia | Logística |
| T14 | Recepciones con diferencias | Indicadores › Logística y Resumen | Calidad de lo recibido. | Período + tendencia | Bodega, calidad, compras |
| T15 | Lead time promedio | Indicadores › Logística y Resumen | Tiempo de ciclo de la OC a bodega. | Período + tendencia | Dirección, logística |
| T16 | Liberación logística a tiempo | Indicadores › Logística y Resumen | Si logística libera antes de la meta. | Período + tendencia | Logística |
| T17 | OC en riesgo de llegar tarde | Indicadores › Logística y Resumen | Igual que I05. | Foto de hoy | Compras, logística |
| T18 | Fichas en revisión | Indicadores › Productos | Cola de clasificación. | Foto de hoy | Clasificación |
| T19 | Fichas devueltas | Indicadores › Productos | Correcciones pendientes del proveedor. | Foto de hoy | Proveedor, clasificación |
| T20 | Fichas aprobadas | Indicadores › Productos | Ritmo de clasificación. | Período + tendencia | Clasificación |
| T21 | Productos sin clasificar | Indicadores › Productos | Avance de clasificación. | Foto de hoy | Clasificación, proveedor |

### Seguimiento — Órdenes de compra

| ID | Indicador | Dónde aparece | Qué decisión apoya | Período | Quién lo consulta |
|---|---|---|---|---|---|
| S01 | Órdenes de compra (y «% facturado») | Seguimiento › Órdenes | Volumen y avance de facturación. | Foto de hoy | Compras |
| S02 | Liberadas | Seguimiento › Órdenes | OCs que se pueden facturar. | Foto de hoy | Compras |
| S03 | No liberadas | Seguimiento › Órdenes | Qué bloquea la facturación. | Foto de hoy | Compras, logística |
| S04 | XF vencida, sin facturar | Seguimiento › Órdenes | Despachos atrasados. | Foto de hoy | Compras |
| S05 | Atrasado para el cierre de puerto | Seguimiento › Órdenes | OCs que llegan tarde. | Foto de hoy | Compras, logística |
| S06 | OC por estado (barras) | Seguimiento › Órdenes | Distribución por etapa; filtra la tabla. | Foto de hoy | Compras |
| S07 | Avance por OC (barra y «% facturado · total») | Seguimiento › Órdenes (fila) | Avance de cada OC. | Foto de hoy | Compras |

### Seguimiento — Embarques y unidades de carga

| ID | Indicador | Dónde aparece | Qué decisión apoya | Período | Quién lo consulta |
|---|---|---|---|---|---|
| S08 | Embarques (por modo) | Seguimiento › Embarques | Volumen de embarques. | Foto de hoy | Logística |
| S09 | Unidades de carga | Seguimiento › Embarques | Contenedores en juego. | Foto de hoy | Logística |
| S10 | En tránsito | Seguimiento › Embarques | Carga viajando. | Foto de hoy | Logística |
| S11 | Llegan en 7 días | Seguimiento › Embarques | Prever recepciones. | Próximos 7 días | Bodega |
| S12 | Atrasado para el cierre de puerto | Seguimiento › Embarques | Embarques que llegan tarde. | Foto de hoy | Logística |
| S13 | Llegadas por semana (gráfica) | Seguimiento › Embarques | Carga de recepción próxima. | 8 semanas | Bodega, logística |
| S14 | Embarques por estado | Seguimiento › Embarques | Distribución por estado. | Foto de hoy | Logística |

### Seguimiento — Facturación y listas de empaque

| ID | Indicador | Dónde aparece | Qué decisión apoya | Período | Quién lo consulta |
|---|---|---|---|---|---|
| S15 | Facturas (importe por moneda) | Seguimiento › Documentos | Volumen facturado en curso. | Foto de hoy | Facturación |
| S16 | Facturas abiertas | Seguimiento › Documentos | Trabajo abierto. | Foto de hoy | Facturación |
| S17 | Empaque | Seguimiento › Documentos | PL en proceso. | Foto de hoy | Bodega |
| S18 | Lista para embarcar | Seguimiento › Documentos | PL listas para contenedor. | Foto de hoy | Logística |
| S19 | Con datos pendientes | Seguimiento › Documentos | Documentos que no pueden finalizarse. | Foto de hoy | Proveedor, facturación |
| S20 | Documentos por paso (barras) | Seguimiento › Documentos | Embudo documental; filtra la tabla. | Foto de hoy | Facturación, logística |
| S21 | Carga empacada (PL, cajas, pallets, peso, volumen) | Seguimiento › Documentos | Volumen físico en curso. | Foto de hoy | Logística |

### Seguimiento — Lead times

| ID | Indicador | Dónde aparece | Qué decisión apoya | Período | Quién lo consulta |
|---|---|---|---|---|---|
| L01 | Liberación logística a tiempo (%) | Seguimiento › Lead times | Cumplimiento de liberación antes de la XF. | Período | Logística |
| L02 | Liberación vencida | Seguimiento › Lead times | OCs sin liberar con meta pasada. | Foto de hoy | Logística |
| L03 | Lead time promedio (días) | Seguimiento › Lead times | Tiempo de ciclo. | Período | Dirección, logística |
| L04 | Atrasado para el cierre de puerto (y en riesgo) | Seguimiento › Lead times | OCs que llegan tarde / con poca holgura. | Foto de hoy | Logística |
| L05 | OC creadas en el período | Seguimiento › Lead times | Contexto del análisis. | Período | Logística |
| L06 | Tabla por origen (días por etapa, total, liberación vs XF, recogida vs XF, holgura) | Seguimiento › Lead times | Dónde se pierde el tiempo por origen. | Período | Logística, dirección |
| L07 | Hitos de cada OC (fecha, meta, estado) | Seguimiento › Lead times (detalle) | Qué hito de qué documento se atrasa. | Por OC | Logística |

### Cifras en pantallas operativas, comercial y reportes

| ID | Indicador | Dónde aparece | Qué decisión apoya | Período | Quién lo consulta |
|---|---|---|---|---|---|
| O01 | % facturado de la OC (lista Órdenes) | Órdenes de compra | Avance de facturación por OC. | Foto de hoy | Compras, proveedor |
| O02 | Por facturar por OC (por unidad) | Órdenes de compra | Saldo disponible. | Foto de hoy | Proveedor, compras |
| O03 | Total de la selección a facturar | Órdenes de compra (carrito) | Monto a facturar. | — | Proveedor |
| O04 | Factura: % en listas de empaque y % en cajas | Factura y panel de resumen | Avance de empaque. | Por documento | Proveedor |
| O05 | PL: avance de empaque | Lista de empaque | Cuánto está en cajas. | Por documento | Proveedor, bodega |
| O06 | Embarques: conteo por estado | Embarques | Distribución. | Foto de hoy | Logística |
| O07 | Unidad de carga: % de volumen y de peso | Embarque | No exceder la capacidad. | Por unidad | Logística |
| O08 | Resumen del embarque (facturas, PL, cajas, kg, m³) | Embarque | Contenido del embarque. | Por embarque | Logística |
| O09 | Productos: conteos por vista | Productos | Colas de clasificación. | Foto de hoy | Clasificación |
| O10 | Familias: % aprobados como se sugirió, baja confianza | Familias de producto | Calidad del motor de sugerencias. | Acumulado | Clasificación |
| O11 | Estado de cobro de un documento (pendiente, parcial, vencido, pagado) | Facturación › Documentos | Qué documento cobrar. | Foto de hoy | Cobranza |
| O12 | Estado de cuenta de un tercero (saldo por moneda) | Facturación › Terceros | Cuánto debe o se le debe a un tercero. | Foto de hoy | Cobranza, tesorería |
| O13 | Reportes: medidas (suma, promedio, mín., máx., conteo) | Reportes (analíticos) | Análisis libre. | Según filtros | Analistas |

---

## 3. Evaluación individual de cada indicador

Clasificación: **Mantener** 23 · **Corregir** 38 · **Mejorar** 8 · **Combinar** 15 · **Eliminar** 2 · **Reemplazar** 1.
Prioridad: **P0** 12 · **P1** 25 · **P2** 21 · **P3** 29.

La justificación completa (con evidencia) está en la ficha de cada indicador (Anexo A).

| ID | Indicador | Clasificación | Prioridad | Motivo principal | Esfuerzo |
|---|---|---|---|---|---|
| I01 | Por facturar | **Corregir** | P0 | [E] Con una OC en EUR, el valor bajó de USD 40,129 a 37,219 (el saldo en EUR desaparece) pero el detalle siguió diciendo «en 6 OC». [E] Ya en la demo difiere de «Saldo… | Bajo |
| I02 | Documentos en curso | **Mantener** | P3 | [M] Suma dos tipos de documento en una cifra; el detalle sí los separa. | Bajo |
| I03 | Lista para embarcar | **Corregir** | P1 | [C] Otra pantalla usa el mismo nombre con otra regla: Seguimiento › Documentos cuenta filas de PL en LISTO_EMBARQUE sin exigir que toda la factura esté asignada. [S]… | Medio |
| I04 | Embarques en camino | **Corregir** | P0 | [E] Con 10 embarques en tránsito: Inicio = 8, Indicadores «Embarques en tránsito» = 10, Seguimiento «En tránsito» = 1. [C] Cuenta EN_TRANSITO + ARRIBADO pero el clic… | Bajo |
| I05 | OC en riesgo de atraso | **Combinar** | P1 | [C] El título dice «en riesgo» pero cuenta las ya atrasadas (ATRASO); «en riesgo» en el resto del sistema es JUSTO. [E] Incluye OC canceladas/borrador (ver S01). [E]… | Bajo |
| I06 | Productos que bloquean facturas | **Mantener** | P3 | [C] Recorre las líneas en Python (O(líneas)); en la lista de productos ignora búsqueda, marca y filtros de columna. | Bajo |
| I07 | Productos por clasificar | **Mantener** | P3 | Sin deficiencias relevantes. | Bajo |
| I08 | Fichas devueltas | **Mantener** | P3 | Sin deficiencias relevantes. | Bajo |
| I09 | Facturas por finalizar | **Combinar** | P2 | [C] Repite en la misma pantalla lo que ya cuenta I02 «Documentos en curso». | Bajo |
| I10 | Listas de empaque incompletas | **Combinar** | P2 | [C] Mismo universo que la parte de PL de I02. [C] Ejecuta `validar_pl` por cada PL abierta en cada visita a Inicio. | Bajo |
| I11 | OC con XF esta semana | **Corregir** | P1 | [E] Incluye OC canceladas, en borrador o rechazadas (ver S01). | Bajo |
| I12 | OC con XF vencida | **Combinar** | P1 | [E] Incluye OC canceladas/borrador. [C] Tres definiciones de «XF vencida»: esta (por línea), Seguimiento S04 (por OC) e Indicadores T05 (OC APROBADAS, facturado incluye… | Bajo |
| I13 | Listas de empaque sin unidad de carga | **Combinar** | P2 | [C] Es el detalle de I03 «Lista para embarcar» (que ya dice «N PL sin contenedor»). | Bajo |
| I14 | Embarques que salen esta semana | **Corregir** | P0 | [C] No aplica el alcance de sociedad/centro/transportista que sí aplica el módulo de transporte (`transporte.py:69 condiciones_alcance`): un usuario limitado ve cuántos… | Bajo |
| I15 | OC en riesgo de llegar tarde | **Eliminar** | P2 | [C] Duplica I05 en la misma pantalla. | Bajo |
| I16 | Llegadas esta semana | **Combinar** | P2 | [C] Seguimiento › Embarques «Llegan en 7 días» usa otra regla (no arribados, 0–7 días, sobre `arribo_real or eta`). | Bajo |
| I17 | Siguientes pasos (cantidad) | **Mantener** | P3 | [C] El contador muestra como máximo 12 aunque haya más. [C] Valida cada factura y PL editable en cada visita (costo). | Bajo |
| I18 | Panel «Embarques» (avance del viaje, cajas) | **Corregir** | P0 | [C] Un usuario interno limitado ve códigos de embarque, puertos y números de factura de otras sociedades. [C] `avanceViaje` devuelve 50 % para un estado no previsto (p.… | Bajo |
| I19 | Unidades de carga en planificación (% llenado) | **Corregir** | P0 | [C] Sin alcance de sociedad/centro/transportista. [C] Solo % por volumen; el peso (también limitante) no se muestra. | Bajo |
| I20 | Facturado (período) | **Corregir** | P0 | [C] Las facturas en otra moneda se descartan en silencio, pero sí se cuentan en «N facturas finalizadas» (cifra y conteo no corresponden). [C] El filtro de marca recorta… | Medio |
| I21 | Listas de empaque finalizadas (período) | **Corregir** | P1 | [C] `actualizado_en` cambia con cualquier edición (`comun/historial.py:22 tocar`), no es la fecha de finalización: una PL finalizada el mes pasado y tocada hoy cuenta… | Medio |
| I22 | Embarques por llegar (período) | **Reemplazar** | P1 | [C] Usa la ETA estimada, no el arribo real; incluye CANCELADO; sin alcance de sociedad/transportista; filtra proveedor recorriendo unidades y PL en Python. | Bajo |
| I23 | Gráfica «Valor facturado» | **Corregir** | P0 | [C] Igual que I20: otras monedas desaparecen sin aviso. | Medio |
| I24 | Dónde está la mercancía | **Mejorar** | P3 | [C] Correcto en unidades (no mezcla). Hereda el universo de I01 (OC CERRADAS/CANCELADAS con `liberada`). [S] «Embarcado» = unidad CONFIRMADA en embarque ≠ PLANIFICADO,… | Bajo |
| I25 | Tabla «Por proveedor» (por facturar, en proceso, PL abiertas, listas, en camino) | **Corregir** | P0 | [E] Con una OC de The North Face en EUR (2,910), la columna siguió en 28,537 «USD»: sumó EUR como USD. | Bajo |
| T01 | OC pendientes de aprobación | **Mantener** | P3 | Sin deficiencias relevantes. | Bajo |
| T02 | OC aprobadas | **Combinar** | P3 | [M] Cuenta sola aporta poco; incluye aprobaciones automáticas (sin reglas). | Bajo |
| T03 | Días para aprobar | **Corregir** | P1 | [C] Las OCs aprobadas automáticamente (sin reglas) aportan 0 días (`compras/flujo_oc.py:332-334`) y bajan el promedio. [C] Al reenviar tras un rechazo, `enviada_en` se… | Medio |
| T04 | Saldo por facturar | **Corregir** | P0 | [E] Con una OC en EUR el valor bajó de 41,543 a 37,219: el saldo en EUR se descarta sin aviso. [E] Difiere de I01 con los mismos datos (41,543 vs 40,129). [C] Incluye… | Bajo |
| T05 | OC con fecha de despacho vencida | **Combinar** | P1 | [C] Una factura en borrador ya «cubre» la cantidad aunque no se haya despachado. [C] Tercera definición de XF vencida (I12, S04). | Bajo |
| T06 | Facturas finalizadas | **Combinar** | P1 | [E] Una factura reabierta (EN_CORRECCION) siguió contando: 6 → 6 (Inicio pasó a 5). `reabrir` no limpia `finalizado_en` (`facturacion/facturas.py:629`) y al volver a… | Bajo |
| T07 | Monto facturado | **Corregir** | P0 | [E] Incluye la factura reabierta (17,285 se mantuvo; Inicio bajó a 15,920). [C] Las facturas en otra moneda se descartan sin aviso. [C] Distinta fecha base que Inicio… | Bajo |
| T08 | Facturas en curso | **Mantener** | P3 | Sin deficiencias relevantes. | Bajo |
| T09 | Listas de empaque en curso | **Mantener** | P3 | Sin deficiencias relevantes. | Bajo |
| T10 | Embarques en tránsito | **Mantener** | P3 | [E] Correcto (10 con 10 en tránsito); es la referencia para corregir I04 y S10. | Bajo |
| T11 | Arribos | **Mantener** | P3 | Sin deficiencias relevantes. | Bajo |
| T12 | Arribos a tiempo | **Corregir** | P1 | [C] La ETA se puede editar en tránsito hasta el arribo (`transporte/transporte.py:343-345`) y no se guarda la ETA comprometida: actualizar la ETA en ruta convierte un… | Medio |
| T13 | Días de tránsito | **Mantener** | P3 | [M] Sin mediana ni separación por modo/ruta. | Bajo |
| T14 | Recepciones con diferencias | **Corregir** | P2 | [S] Si una línea de PL se recibe en dos recepciones parciales, cada una se compara con la cantidad total empacada y ambas cuentan como diferencia. | Bajo |
| T15 | Lead time promedio | **Corregir** | P1 | [C] Incluye OCs de cualquier estado. [C] Una OC con una etapa de duración negativa (dato erróneo) queda fuera sin aviso. [C] Distinto de L03 (OCs creadas en el período).… | Medio |
| T16 | Liberación logística a tiempo | **Corregir** | P1 | [E] En la demo da 91,7 % y L01 92 % con otro universo (OCs creadas vs liberadas). [C] Incluye OCs de cualquier estado. | Bajo |
| T17 | OC en riesgo de llegar tarde | **Combinar** | P1 | [E] Da 1 donde Inicio/Seguimiento/Lead times dan 2. [C] Nombre «en riesgo» para ATRASO. | Bajo |
| T18 | Fichas en revisión | **Mantener** | P3 | Sin deficiencias relevantes. | Bajo |
| T19 | Fichas devueltas | **Mantener** | P3 | Sin deficiencias relevantes. | Bajo |
| T20 | Fichas aprobadas | **Mejorar** | P3 | [C] `revisado_en` guarda solo la última revisión; una ficha reaprobada se mueve de período. | Bajo |
| T21 | Productos sin clasificar | **Corregir** | P2 | [C] El nombre engaña: excluye `revision` y `observado`, que tampoco están clasificados. | Bajo |
| S01 | Órdenes de compra (y «% facturado») | **Corregir** | P1 | [E] Tras cancelar una OC y pasar otra a borrador, siguió en 14. [C] El % suma pares + unidades + cajas. [C] La lista de Órdenes calcula el % por valor (O01): dos «%… | Bajo |
| S02 | Liberadas | **Eliminar** | P3 | [C] Es S01 − S03; siempre en verde; el clic no filtra nada. | Bajo |
| S03 | No liberadas | **Corregir** | P2 | [C] El clic filtra solo SIN_COMERCIAL (`TableroOrdenes.vue:112`): la lista muestra menos que la cifra. [E] Incluye OCs canceladas. | Bajo |
| S04 | XF vencida, sin facturar | **Combinar** | P1 | Ver I12. | Bajo |
| S05 | Atrasado para el cierre de puerto | **Combinar** | P1 | Ver I05. | Bajo |
| S06 | OC por estado (barras) | **Corregir** | P1 | [E] Incluye OCs canceladas/borrador en «Liberada, sin facturar». | Bajo |
| S07 | Avance por OC (barra y «% facturado · total») | **Corregir** | P2 | [C] Total y % mezclan unidades de medida. | Bajo |
| S08 | Embarques (por modo) | **Mantener** | P2 | [E] Solo cuenta embarques con mercancía asociada (con 10 en tránsito sin carga, cuenta 1). [C] Alcance distinto del de /embarques. | Bajo |
| S09 | Unidades de carga | **Mantener** | P3 | Sin deficiencias relevantes. | Bajo |
| S10 | En tránsito | **Combinar** | P1 | [E] Da 1 con 10 en tránsito (Indicadores 10, Inicio 8). | Bajo |
| S11 | Llegan en 7 días | **Combinar** | P2 | [C] El clic no aplica filtro. [C] Distinto de I16. | Bajo |
| S12 | Atrasado para el cierre de puerto | **Corregir** | P2 | [C] El texto de detalle dice «ETA después de la fecha en tienda», contrario al título (límite en puerto). | Bajo |
| S13 | Llegadas por semana (gráfica) | **Mantener** | P3 | [M] La primera etiqueta «Esta sem.» está fija en el código. | Bajo |
| S14 | Embarques por estado | **Mantener** | P3 | Sin deficiencias relevantes. | Bajo |
| S15 | Facturas (importe por moneda) | **Mantener** | P3 | [C] Es la única cifra de montos del sistema que separa monedas: referencia para corregir I01, I20, T04, T07. | Bajo |
| S16 | Facturas abiertas | **Corregir** | P2 | [C] El clic filtra solo BORRADOR (`SeguimientoDocumentos.vue`): la lista muestra menos que la cifra. | Bajo |
| S17 | Empaque | **Corregir** | P2 | [C] El clic filtra solo EMPACANDO. | Bajo |
| S18 | Lista para embarcar | **Corregir** | P1 | Ver I03 (otra definición con el mismo nombre). | Bajo |
| S19 | Con datos pendientes | **Mantener** | P3 | Sin deficiencias relevantes. | Bajo |
| S20 | Documentos por paso (barras) | **Mantener** | P3 | Sin deficiencias relevantes. | Bajo |
| S21 | Carga empacada (PL, cajas, pallets, peso, volumen) | **Mejorar** | P3 | [C] Por diseño ignora los filtros de columna de la tabla; no se indica en pantalla. | Bajo |
| L01 | Liberación logística a tiempo (%) | **Corregir** | P1 | [C] Sin datos muestra «0» en verde: el valor usa `?? 0` y el tono `?? 100 >= 80` (`TableroLeadTimes.vue:124`); el componente `Kpi` convierte `null` en 0. [C] Umbral 80 %… | Bajo |
| L02 | Liberación vencida | **Corregir** | P1 | [C] Incluye OCs canceladas o rechazadas (nunca se liberarán). | Bajo |
| L03 | Lead time promedio (días) | **Corregir** | P1 | [C] Sin datos muestra 0. [C] Distinto de T15 (por fecha de ingreso). | Bajo |
| L04 | Atrasado para el cierre de puerto (y en riesgo) | **Combinar** | P1 | Ver I05. | Bajo |
| L05 | OC creadas en el período | **Corregir** | P1 | [E] Incluye OCs canceladas y en borrador (siguió en 14). | Bajo |
| L06 | Tabla por origen (días por etapa, total, liberación vs XF, recogida vs XF, holgura) | **Mejorar** | P2 | [C] La barra (suma de promedios de poblaciones distintas) y el «Total» pueden no coincidir. [C] Umbral 80 % fijo en «Liberación vs XF». | Bajo |
| L07 | Hitos de cada OC (fecha, meta, estado) | **Mantener** | P3 | Sin deficiencias relevantes. | Bajo |
| O01 | % facturado de la OC (lista Órdenes) | **Corregir** | P2 | [C] Cuenta como facturado lo que está en borradores; difiere de S01/S07 (por cantidad). | Bajo |
| O02 | Por facturar por OC (por unidad) | **Mantener** | P3 | [C] Agrega por unidad: una línea sobrefacturada oculta el saldo de otra de la misma unidad. [C] El filtro «con saldo» (`:130`) suma entre unidades. | Bajo |
| O03 | Total de la selección a facturar | **Mejorar** | P2 | [C] Con monedas mezcladas suma ambas y muestra un solo código (hay un aviso aparte). | Bajo |
| O04 | Factura: % en listas de empaque y % en cajas | **Corregir** | P2 | [C] Suma pares + unidades; el tope de 100 % oculta el sobreempaque; «sin asignar» se muestra sin unidad. | Bajo |
| O05 | PL: avance de empaque | **Corregir** | P2 | [C] Igual que O04. | Bajo |
| O06 | Embarques: conteo por estado | **Mejorar** | P3 | [C] Ignora la búsqueda y descarga dos veces la lista completa (que es costosa). | Bajo |
| O07 | Unidad de carga: % de volumen y de peso | **Mejorar** | P2 | [C] La proyección al asignar calcula % de peso pero solo avisa por volumen. | Bajo |
| O08 | Resumen del embarque (facturas, PL, cajas, kg, m³) | **Corregir** | P2 | [C] Una factura repartida en dos unidades se cuenta dos veces. [C] kg con 0 decimales aquí y 1 en otra vista. | Bajo |
| O09 | Productos: conteos por vista | **Mantener** | P3 | [C] «Bloquean» ignora los filtros de la lista. [C] Los segmentos ocultan los conteos en 0. | Bajo |
| O10 | Familias: % aprobados como se sugirió, baja confianza | **Mejorar** | P3 | [M] No muestra el denominador. | Bajo |
| O11 | Estado de cobro de un documento (pendiente, parcial, vencido, pagado) | **Corregir** | P1 | [C] `fecha_vencimiento` es la de la última cuota (`documentos.py:492`): una cuota anterior vencida no marca el documento. | Medio |
| O12 | Estado de cuenta de un tercero (saldo por moneda) | **Corregir** | P0 | [C] Los pagos se consultan sin filtro de sociedad: un usuario limitado ve y resta pagos de sociedades ajenas. [C] Además `pagos.py:120` permite aplicar un pago a un… | Bajo |
| O13 | Reportes: medidas (suma, promedio, mín., máx., conteo) | **Corregir** | P0 | [C] Sumar `valor`/`importe` agrupando por proveedor suma monedas distintas; la fuente `lineas_oc` no tiene campo moneda; sumar cantidades mezcla unidades; `pendiente`… | Medio |

---

## 4. Deficiencias confirmadas, con evidencia

### 4.1 Reproducción con datos

La base de demostración tiene **una sola moneda (USD), todas las OC aprobadas y todas las facturas finalizadas**, así
que varios defectos no se ven en ella. Por eso se midieron los indicadores en una **copia** y se agregaron casos reales:

| Cambio introducido en la copia | Qué debería pasar | Qué pasó |
|---|---|---|
| Sin cambios (demo tal cual) | «Por facturar» (Inicio) = «Saldo por facturar» (Indicadores) | **40,129 vs 41,543 USD** |
| OC 4400003851 → CANCELADA; OC 4400003904 → BORRADOR | Dejan de contar como OC en Seguimiento y Lead times | «Órdenes de compra» **14 → 14**; «OC creadas en el período» **14 → 14** |
| OC 4400003850 (TNF, 2,910) → moneda EUR | El saldo en EUR se muestra aparte | Inicio: **40,129 → 37,219 USD**, detalle **«en 6 OC»** sin cambio; tabla por proveedor TNF **28,537 → 28,537 «USD»** (sumó los EUR) |
| Factura TNF-2026-0915 (1,365) → EN_CORRECCION (reabierta) | Deja de contar como finalizada en todas partes | Inicio: **17,285 → 15,920**, «6 → 5 facturas»; Indicadores: **17,285 → 17,285**, **6 → 6** |
| +9 embarques EN_TRANSITO (10 en total) | Las tres pantallas dicen 10 | Inicio **8** · Indicadores **10** · Seguimiento **1** |

Los resultados completos (JSON antes/después y el script de medición) quedaron en `/tmp/claude-0/audit/` (fuera del
repositorio, se pierden al cerrar la sesión; el procedimiento se describe en el Anexo B para repetirlo).

### 4.2 Deficiencias, por tema

**D-01 · Monedas sumadas o descartadas sin aviso — P0**
- [E] Tabla «Por proveedor» de Inicio: `por_proveedor[prov_id] += saldo * precio` sin separar monedas
  (`app/modulos/seguimiento/dashboard.py:61-62`), mostrado con la moneda principal (`DashboardView.vue:75`). → I25.
- [E] «Por facturar» de Inicio muestra solo la moneda de mayor saldo (`dashboard.py:68 _moneda_principal`) y el detalle
  cuenta OCs de todas las monedas. → I01.
- [C] «Facturado» y la gráfica de Inicio filtran `f.moneda == moneda` (`dashboard.py:142,171`) y el conteo de facturas no.
  → I20, I23.
- [E] Indicadores «Saldo por facturar» y «Monto facturado» filtran la moneda base y descartan el resto sin indicarlo
  (`indicadores.py:126-134, 157-163`). → T04, T07.
- [C] Reportes: `SUM(expr) … GROUP BY` sin exigir la moneda (`app/modulos/reportes/generador.py:213-215`); la fuente
  `lineas_oc` no tiene campo moneda (`fuentes.py:101-125`); los importes se muestran sin código (`ReportesView.vue:169`). → O13.
- [C] Selección a facturar: suma monedas y muestra la primera (`OrdenesView.vue:298-307`, hay un aviso aparte). → O03.
- [C] Tipo de cambio: `tipo_cambio` vale 1 por defecto en documentos y pagos (`comercial/documentos.py:385`,
  `pagos.py:158`) y está fijo en 1 para los documentos de proveedor (`comercial/proveedores.py:39`); la tabla `TipoCambio`
  existe pero **ningún cálculo la lee** (solo su catálogo, `maestros/catalogos.py:504`). Ninguna conversión actual sería
  confiable.

**D-02 · Estados que no deberían contar — P1**
- [E] `filas_seguimiento` (`seguimiento.py:140-147`) y `leadtimes()` (`transporte/leadtimes.py:374-387`) no filtran el estado
  de la OC: BORRADOR, EN_APROBACION, RECHAZADA, CANCELADA y CERRADA entran en Seguimiento, Lead times, «OC en riesgo» de
  Inicio, «XF vencida/esta semana» de Inicio y los indicadores de lead time (S01–S06, L01–L05, I05, I11, I12, T15–T17).
- [E] Factura reabierta: `reabrir` no limpia `finalizado_en` (`facturacion/facturas.py:629-651`) y los indicadores filtran
  `estado != 'CANCELADA'` + `finalizado_en` (`indicadores.py:146-163`). Al volver a finalizar, `finalizado_en` se
  sobrescribe (`facturas.py:614`) y el monto **cambia de período**. → T06, T07.
- [C] «Facturado» de cantidades (`facturacion/cantidades.py:17-27`) y el % de avance de OC cuentan **facturas en borrador**
  como facturadas (reservan cantidad). Es una regla válida para el saldo disponible, pero la etiqueta «facturado» engaña en
  los indicadores de avance. → O01, T05.
- [C] «Embarques por llegar» incluye CANCELADO (`dashboard.py:176`). → I22.
- [C] `_saldo_ocs` toma `liberada = true` sin mirar el estado: las OC CERRADAS conservan `liberada`
  (`compras/flujo_oc.py:467`). → I01, I24.

**D-03 · Mismo nombre, distinta definición — P1** (detalle en §5.1)
- [E] Saldo por facturar (I01/T04/I25), embarques en tránsito (I04/T10/S10), liberación a tiempo (L01/T16), OC en riesgo
  (I05/T17/S05/L04), lead time promedio (L03/T15), XF vencida (I12/S04/T05), facturado (I20/T07), «Lista para embarcar»
  (I03/S18), llegadas (I16/S11/I22/T11), «% facturado» (S01/O01).

**D-04 · Conteos y porcentajes que engañan — P0/P1**
- [E] «Embarques en camino» topado en 8 (`dashboard.py:232` y `:437`). → I04.
- [C] `Kpi.vue:20-26` convierte `null` en 0 (`Number(props.valor || 0)`): «Lead time promedio» sin datos dice 0; «Liberación
  a tiempo» sin datos dice 0 **en verde** (`TableroLeadTimes.vue:124`: valor `?? 0`, tono `?? 100 >= 80`). → L01, L03.
- [C] Porcentajes que suman unidades distintas (pares + unidades + cajas): Seguimiento «% facturado» (`seguimiento.py:530,
  584`), avance de empaque de factura y PL (`FacturaView.vue:116-142`, `ResumenFactura.vue:44`,
  `PackingListView.vue:93`). → S01, S07, O04, O05.
- [C] `pct()` (`src/nucleo/utils.js:84`) y el anillo de empaque topan en 100 %: el sobreempaque no se ve. → O04, O05.
- [C] La variación de Indicadores para porcentajes es **relativa** («▲ 50 %» al pasar de 66,7 % a 100 %), no en puntos
  porcentuales (`TableroView.vue:66-74`). → todos los T de formato porcentaje.
- [C] «Días para aprobar» promedia ceros de las aprobaciones automáticas (`compras/flujo_oc.py:332-334`). → T03.
- [C] «Arribos a tiempo» compara con una ETA editable en tránsito (`transporte/transporte.py:343-345`), sin ETA
  comprometida. → T12.
- [C] «Listas de empaque finalizadas» usa `actualizado_en` (cualquier edición, `comun/historial.py:22`) como fecha de
  finalización; la PL no tiene `finalizado_en`. → I21.
- [C] Un documento con una cuota vencida y la última futura no figura como VENCIDO: `fecha_vencimiento` es la última cuota
  (`comercial/documentos.py:492`). → O11.
- [C] Una factura repartida en dos unidades de carga se cuenta dos veces en el resumen del embarque
  (`ResumenEmbarque.vue:83`). → O08.

**D-05 · El clic no muestra lo que la cifra cuenta — P2**
- [C] «No liberadas» → solo SIN_COMERCIAL (`TableroOrdenes.vue:112`); «Facturas abiertas» → solo BORRADOR y «Empaque» →
  solo EMPACANDO (`SeguimientoDocumentos.vue:96-97`); «Embarques en camino» cuenta ARRIBADO y filtra EN_TRANSITO;
  «Llegan en 7 días» y «Liberadas» no filtran; los indicadores de «Desempeño» de Inicio no pasan el período a la lista.

**D-06 · Alcance de datos incompleto — P0** (detalle en §8.3)
- [C] Inicio: embarques, unidades de carga, salidas de la semana y llegadas del período sin `condiciones_alcance`
  (`dashboard.py:176, 206, 365, 382`). → I14, I18, I19, I22.
- [C] Estado de cuenta: pagos sin filtro de sociedad (`comercial/documentos.py:643-645`); aplicación de pagos sin validar
  la sociedad (`comercial/pagos.py:108-128`). → O12.

## 5. Indicadores redundantes, incorrectos o de escaso valor

### 5.1 Un concepto, varias cifras

| Concepto | Dónde y cómo se calcula | Decisión |
|---|---|---|
| Saldo por facturar | I01 (liberadas, moneda mayor), I25 (todas las monedas sumadas), T04 (APROBADAS, moneda base), O02 (cantidades), I24 (cantidades por unidad) | **Una** definición de valor (OC APROBADAS, posiciones no bloqueadas, por moneda) y una de cantidad (por unidad). |
| Embarques en tránsito | I04 (EN_TRANSITO+ARRIBADO, tope 8, sin alcance), T10 (EN_TRANSITO, con alcance), S10 (solo con carga) | T10 como fuente única; si ARRIBADO cuenta, otra métrica «en puerto». |
| OC atrasadas / en riesgo | I05 e I15 (ATRASO), T17 (ATRASO, no ingresadas), S05, L04, S12 (con texto contradictorio) | «OC con llegada tarde» (ATRASO, vigentes, no ingresadas) y «OC con poca holgura» (JUSTO). |
| XF vencida | I12 (por línea), S04 (por OC), T05 (APROBADAS, borrador cubre) | Una sola: OC vigente con XF < hoy y saldo sin facturar (borradores no cubren). |
| Liberación a tiempo | L01 (OC creadas en el período, entero), T16 (OC liberadas en el período) | Por fecha de liberación (T16), mostrando n de m. |
| Lead time promedio | L03 (OC creadas), T15 (OC ingresadas) | Por fecha de ingreso (T15): mide ciclos terminados. |
| Facturado del período | I20/I23 (`fecha` del documento, moneda mayor, solo FINALIZADA), T07 (`finalizado_en`, moneda base, incluye reabiertas), S15 (por moneda) | Solo FINALIZADA, por moneda, con una fecha de devengo elegida por la empresa (fecha del documento por defecto). |
| Lista para embarcar | I03 (factura completa), S18 (fila de PL) | Nombrar distinto o unificar: «Facturas listas» vs «PL listas». |
| Llegadas | I16, S11 (7 días, reglas distintas), I22 (ETA en el período), T11 (arribo real) | «Arribos» (real) y «Llegadas previstas» (ETA, no arribados). |
| % facturado | S01/S07 (cantidad, mezcla unidades), O01 (valor a precio de OC, incluye borradores) | Por valor, separando «facturado» de «en borrador». |
| Documentos abiertos | I02, I09, I10, T08, T09, S16 | Mantener T08/T09; en Inicio una sola entrada con el desglose. |

### 5.2 Incorrectos (fórmula o universo erróneo)
I01, I04, I20, I23, I25, T04, T07 (P0) · I21, I22, T03, T06, T12, T15, T16, S01, S06, L01, L02, L03, L05, O11 (P1) · O04,
O05, O08, T14 [S], T21 (P2). Detalle en las fichas.

### 5.3 Escaso valor o duplicados — eliminar o combinar
- **Eliminar**: I15 (duplicado en la misma pantalla), S02 «Liberadas» (= S01 − S03, siempre verde, el clic no filtra).
- **Combinar**: I09, I10 e I13 con las tarjetas I02/I03; T02 «OC aprobadas» con T01/T03 en una tarjeta de aprobación;
  T06 con T07 (monto y cantidad en una tarjeta); y los grupos de §5.1.
- **Reemplazar**: I22 «Embarques por llegar» (ETA estimada, cualquier estado) por «Arribos» (T11).
- Un indicador sin datos debe decir «—», no «0» (afecta a todas las tarjetas que usan `Kpi.vue`).

## 6. KPIs recomendados para incorporar

Criterio: solo los que el sistema **ya puede calcular de forma confiable** o que necesitan un dato pequeño y concreto. Los
importes, siempre por moneda (o convertidos con una moneda de reporte y tipos de cambio válidos, ver R04).

| ID | KPI | Ámbito | Calculable hoy | Prioridad |
|---|---|---|---|---|
| R01 | Cuentas por cobrar pendientes | Finanzas | Sí | P1 |
| R02 | Cartera vencida y antigüedad de saldos | Finanzas | Sí (por documento); por cuota con asignación FIFO | P1 |
| R03 | Facturación emitida y cobros del período | Finanzas | Sí | P1 |
| R04 | DSO (días de cobro) | Finanzas | **No** confiable: falta moneda de reporte y tipos de cambio validados | P2 |
| R05 | Cuentas por pagar y vencimientos próximos | Finanzas / compras | Sí | P1 |
| R06 | Notas de crédito del período y créditos sin aplicar | Finanzas | Sí | P2 |
| R07 | Cumplimiento de XF del proveedor | Compras / proveedores | Sí (`fecha_xf_original`, `recolectado_en`) | P1 |
| R08 | Puntualidad contra ETA comprometida | Logística | Necesita la ETA comprometida (campo nuevo) | P1 |
| R09 | Tiempo de clasificación y tasa de devolución de fichas | Productos | Sí (bitácora `historial`) | P2 |
| R10 | Antigüedad de pendientes documentales | Operaciones | Sí | P2 |
| R11 | Calidad de datos (registros incompletos o inconsistentes) | Administración | Sí | P2 |
| R12 | Ocupación de contenedores despachados | Logística | Sí | P3 |

**No recomendados por ahora** (falta información):
- **Costos logísticos y diferencia estimado vs. real**: no existe ningún campo de costo en `Embarque`, `UnidadCarga` ni
  `PackingList`, ni un vínculo entre un documento comercial (flete) y un embarque. Haría falta: costos estimados por
  embarque (concepto, moneda, importe) y un `embarque_id` en las líneas de documentos recibidos de transportistas/agentes.
- **Carga de trabajo por persona**: la bitácora tiene `usuario_id` por acción, pero no hay asignación de responsables ni
  tareas con dueño; contar acciones mediría actividad, no carga. Requiere un responsable por documento.

### Fichas de los recomendados

#### R01 · Cuentas por cobrar pendientes
| Campo | Contenido |
|---|---|
| Nombre | Cuentas por cobrar pendientes |
| Estado | Recomendado |
| Objetivo | Saber cuánto se espera cobrar y a quién llamar primero. |
| Fórmula | Σ `saldo(d)` de documentos con `estado = EMITIDO`, `tipo.direccion = EMITIDO`, `tipo.afecta_saldo` y `signo > 0`, menos créditos sin aplicar y cobros sin aplicar; **por moneda**. Detalle: número de documentos y de clientes. |
| Fuente | `comercial.documentos.saldo` (`app/modulos/comercial/documentos.py:125`), `pagos.sin_aplicar` (`pagos.py:29`); tablas `documentos`, `aplicaciones`, `pagos`. Nuevo endpoint en el servicio de métricas. |
| Filtros | Sociedades del usuario (documentos **y** pagos), tercero opcional; foto de hoy. Excluye BORRADOR, ANULADO y PROFORMA. |
| Deficiencia | No existe hoy. |
| Mejora | Tarjeta en el tablero ejecutivo y en Facturación › Documentos, con clic a la lista filtrada «con saldo». |
| Prioridad | P1 |
| Esfuerzo | Medio: agregación nueva sobre datos existentes (evitar el cálculo por documento en Python con una subconsulta de aplicaciones). |
| Validación | Igual a la suma de los estados de cuenta de todos los clientes, por moneda. |

#### R02 · Cartera vencida y antigüedad de saldos
| Campo | Contenido |
|---|---|
| Nombre | Cartera vencida (0–30, 31–60, 61–90, > 90 días) |
| Estado | Recomendado |
| Objetivo | Priorizar la cobranza y medir el riesgo de cobro. |
| Fórmula | Saldo pendiente de R01 agrupado por días desde el vencimiento. Primera versión: por documento con `fecha_vencimiento`. Versión correcta: por **cuota** (`documento_vencimientos`), aplicando los cobros a las cuotas más antiguas (FIFO) cuando la aplicación no indica cuota. % vencido = vencido ÷ total por cobrar. |
| Fuente | `documentos`, `documento_vencimientos`, `aplicaciones`. |
| Filtros | Sociedades, moneda (obligatoria como agrupación), cliente. Tramos configurables. |
| Deficiencia | No existe; el estado VENCIDO actual mira solo la última cuota (O11). |
| Mejora | Gráfica de barras apiladas por tramo, por moneda; clic a los documentos de cada tramo. |
| Prioridad | P1 |
| Esfuerzo | Medio (la asignación por cuota es la parte delicada). |
| Validación | Documento de 3 cuotas con la primera vencida 40 días: su cuota cae en 31–60 y el resto en «por vencer». |

#### R03 · Facturación emitida y cobros del período
| Campo | Contenido |
|---|---|
| Nombre | Facturación emitida (neta) y cobros del período |
| Estado | Recomendado |
| Objetivo | Ver si el negocio cobra al ritmo que factura. |
| Fórmula | Emitida: Σ `subtotal` (neto de descuentos, sin impuestos) de FACTURA y NOTA_DEBITO EMITIDAS con `fecha` en el período, menos NOTA_CREDITO emitidas en el período; bruto (`total`) como dato secundario. Cobros: Σ `importe` de pagos COBRO REGISTRADOS con `fecha` en el período. Por moneda; comparación con el período anterior de igual duración. |
| Fuente | `documentos`, `tipos_documento`, `pagos`. |
| Filtros | Sociedades; excluye BORRADOR/ANULADO/PROFORMA; pagos anulados excluidos. |
| Deficiencia | No existe; hoy solo se mide la factura del proveedor (T07), no la facturación comercial. |
| Mejora | Una tarjeta con dos cifras y tendencia. |
| Prioridad | P1 |
| Esfuerzo | Bajo–medio. |
| Validación | Una factura anulada después del cierre del período desaparece de la cifra; una nota de crédito resta en su fecha. |

#### R04 · DSO (días de cobro)
| Campo | Contenido |
|---|---|
| Nombre | Días promedio de cobro (DSO) |
| Estado | Recomendado, **condicionado** |
| Objetivo | Medir la eficiencia de la cobranza en el tiempo. |
| Fórmula | (Cuentas por cobrar al cierre ÷ facturación emitida de los últimos N días) × N, en una moneda de reporte. |
| Fuente | R01 y R03. |
| Filtros | Sociedad. |
| Deficiencia | No es confiable hoy: necesita sumar monedas, y `tipo_cambio` vale 1 por defecto y `TipoCambio` no se usa. |
| Mejora | Primero: moneda de reporte por empresa + tipo de cambio obligatorio y validado al emitir. Mientras tanto, DSO **por moneda**. |
| Prioridad | P2 |
| Esfuerzo | Medio (incluye la regla de tipos de cambio). |
| Validación | Con una sola moneda, coincide con el cálculo manual en una hoja de cálculo. |

#### R05 · Cuentas por pagar y vencimientos próximos
| Campo | Contenido |
|---|---|
| Nombre | Por pagar y vencimientos de los próximos 7/30 días |
| Estado | Recomendado |
| Objetivo | Planificar pagos a proveedores. |
| Fórmula | Igual que R01 para documentos RECIBIDOS y pagos PAGO; detalle de lo que vence en 7 y 30 días (por cuota). |
| Fuente | `documentos` (incluye los `FACTURA_PROVEEDOR` creados al finalizar facturas, `comercial/proveedores.py:24-54`), `pagos`, `aplicaciones`. |
| Filtros | Sociedades, proveedor, moneda. |
| Deficiencia | No existe. Los documentos de proveedor se crean con `tipo_cambio = 1` y sin impuestos. |
| Mejora | Tarjeta para tesorería. |
| Prioridad | P1 |
| Esfuerzo | Medio. |
| Validación | Finalizar una factura de proveedor suma su total; reabrirla lo quita (vuelve a borrador). |

#### R06 · Notas de crédito y créditos sin aplicar
| Campo | Contenido |
|---|---|
| Nombre | Notas de crédito del período (% sobre lo facturado) y créditos sin aplicar |
| Estado | Recomendado |
| Objetivo | Detectar devoluciones y ajustes frecuentes; no olvidar créditos a favor. |
| Fórmula | Σ notas de crédito emitidas en el período ÷ facturación emitida × 100; Σ `saldo` de notas de crédito (crédito sin aplicar). |
| Fuente | `documentos` (clase NOTA_CREDITO), `aplicaciones.credito_id`. |
| Filtros | Sociedades, moneda. |
| Deficiencia | Además: el remanente de una nota de crédito **no se puede aplicar después** (solo se aplica al emitir, `comercial/documentos.py:565-568`); el indicador lo haría visible. |
| Mejora | Indicador + permitir aplicar créditos remanentes. |
| Prioridad | P2 |
| Esfuerzo | Bajo (indicador); medio (aplicación posterior). |
| Validación | Nota de crédito mayor que el saldo del documento corregido: el remanente aparece como crédito sin aplicar. |

#### R07 · Cumplimiento de XF del proveedor
| Campo | Contenido |
|---|---|
| Nombre | Despachos a tiempo por proveedor |
| Estado | Recomendado |
| Objetivo | Evaluar a los proveedores con un criterio objetivo. |
| Fórmula | OCs (o líneas) recogidas en el período con `recolectado_en ≤ fecha_xf_original` (+ tolerancia configurable) ÷ recogidas en el período × 100, por proveedor. Usa `fecha_xf_original` para que un cambio de XF no borre el atraso. |
| Fuente | `ordenes_compra.fecha_xf_original`, `packing_lists.recolectado_en` (o el hito «recoleccion» de `leadtimes._hitos_por_oc`). |
| Filtros | OCs vigentes, proveedor, sociedad, período. |
| Deficiencia | No existe; hoy solo hay conteos de XF vencida. |
| Mejora | Ranking por proveedor en Indicadores › Compras. |
| Prioridad | P1 |
| Esfuerzo | Medio. |
| Validación | OC con XF movida de 1 a 15 de mes y recogida el 10: cuenta como tarde frente a la original. |

#### R08 · Puntualidad contra ETA comprometida
| Campo | Contenido |
|---|---|
| Nombre | Arribos a tiempo (contra la ETA al salir) |
| Estado | Recomendado (reemplaza la fórmula de T12) |
| Objetivo | Evaluar transportistas y rutas sin que las actualizaciones en ruta oculten el atraso. |
| Fórmula | Arribados en el período con `arribo_real ≤ eta_comprometida + tolerancia` ÷ arribados con ETA comprometida × 100; por transportista y modo. |
| Fuente | `embarques` + campo nuevo `eta_comprometida` (se fija al registrar la salida). Alternativa sin migración: leer la ETA vigente al evento SALIDA en `historial`. |
| Filtros | Alcance de transporte, período, transportista, modo. |
| Deficiencia | T12 compara con la ETA editable. |
| Mejora | Reemplaza la fórmula de T12. |
| Prioridad | P1 |
| Esfuerzo | Medio. |
| Validación | ETA movida en ruta del 1 al 10, arribo el 8: cuenta como tarde. |

#### R09 · Tiempo de clasificación y devoluciones
| Campo | Contenido |
|---|---|
| Nombre | Días de envío a aprobación y % de fichas devueltas |
| Estado | Recomendado |
| Objetivo | Medir el cuello de botella de clasificación arancelaria. |
| Fórmula | Mediana de (aprobación − primer envío a revisión) de fichas aprobadas en el período; % de fichas con al menos una devolución. |
| Fuente | `historial` (acciones `enviado`, `aprobado`/`corregido`, `devuelto` de la entidad `producto`, `app/modulos/productos/productos.py:796, 913, 935`). |
| Filtros | Proveedor, familia, período. |
| Deficiencia | No existe; `revisado_en` guarda solo la última revisión. |
| Mejora | Agregar índice `historial(entidad, accion, fecha)`. |
| Prioridad | P2 |
| Esfuerzo | Medio. |
| Validación | Ficha enviada el 1, devuelta el 3, reenviada el 5 y aprobada el 6: 5 días, cuenta como devuelta. |

#### R10 · Antigüedad de pendientes
| Campo | Contenido |
|---|---|
| Nombre | Pendientes por antigüedad (facturas en borrador, PL abiertas, OCs en aprobación, fichas en revisión) |
| Estado | Recomendado |
| Objetivo | Que nada quede olvidado. |
| Fórmula | Conteo por tramos de días desde `creado_en` (o desde el último cambio de estado según la bitácora). |
| Fuente | `facturas.creado_en`, `packing_lists.creado_en`, `ordenes_compra.enviada_en`, `historial`. |
| Filtros | Alcance del usuario. Umbral configurable (`DIAS_ALERTA_BORRADOR` ya existe). |
| Deficiencia | Hoy solo existe la tarea «borrador antiguo» de facturas. |
| Mejora | En «Necesita su atención»: «N pendientes con más de X días». |
| Prioridad | P2 |
| Esfuerzo | Bajo. |
| Validación | Factura en borrador de hace 10 días con umbral 7 aparece. |

#### R11 · Calidad de datos
| Campo | Contenido |
|---|---|
| Nombre | Registros que requieren revisión |
| Estado | Recomendado |
| Objetivo | Corregir datos antes de que distorsionen operaciones e indicadores. |
| Fórmula | Conteos de: posiciones de OC sin precio (su valor no entra en «por facturar»); OCs sin fecha en tienda o sin XF; embarques en tránsito sin ETA; documentos en moneda distinta de la de la empresa con `tipo_cambio = 1`; PL con pesos estimados; OCs con etapas de lead time negativas; productos aprobados sin partida. |
| Fuente | Tablas respectivas; la integridad arancelaria ya tiene su auditor (`/aranceles/oficial/integridad`). |
| Filtros | Alcance del usuario. |
| Deficiencia | No existe un tablero de calidad de datos. |
| Mejora | Sección «Calidad de datos» en Indicadores (diagnóstico), visible para administración. |
| Prioridad | P2 |
| Esfuerzo | Bajo por regla. |
| Validación | Cada regla con un caso de prueba que la activa. |

#### R12 · Ocupación de contenedores despachados
| Campo | Contenido |
|---|---|
| Nombre | Ocupación promedio (volumen y peso) de unidades que salieron en el período |
| Estado | Recomendado |
| Objetivo | Reducir fletes con contenedores mejor aprovechados. |
| Fórmula | Promedio de max(% volumen, % peso) de unidades de embarques con `salida_real` en el período. |
| Fuente | `transporte.resumen_unidad` (`app/modulos/transporte/transporte.py:124`). |
| Filtros | Alcance de transporte, modo, tipo de unidad. |
| Deficiencia | No existe. |
| Mejora | Indicador en Logística. |
| Prioridad | P3 |
| Esfuerzo | Bajo. |
| Validación | Dos unidades al 50 % y 90 % → 70 %. |

## 7. Propuesta de organización de los tableros

### 7.1 Evaluación de la presentación actual
- **Prioridad visible**: Inicio ya ordena «Necesita su atención» por gravedad; pero la franja superior y la lista repiten
  cifras (I05/I15, I02/I09/I10, I03/I13).
- **Cantidad**: Inicio muestra 5 tarjetas + hasta 11 avisos + 3 tarjetas de período + 2 gráficas + tabla; razonable tras el
  último ajuste, con las duplicaciones señaladas.
- **Nombre, unidad, período**: Indicadores declara fórmula, fuente y período (bien). Fallan: la tarjeta `Kpi` no muestra
  «%» en los porcentajes ni «—» sin datos; los montos compactos («40.1 K») no avisan que excluyen otras monedas.
- **Colores**: el verde de «Liberadas» y «Lista para embarcar» es fijo (siempre «bien»); «0 en verde» sin datos (L01);
  umbral 80 % fijo en código.
- **Tipos de valor**: montos, cantidades por unidad, porcentajes y días tienen formato propio, salvo los casos que mezclan
  unidades (§4, D-04).
- **Comparaciones**: solo Indicadores compara contra el período anterior; la variación de porcentajes es relativa (debe
  ser en puntos). Inicio y Seguimiento no comparan.
- **Llegar al detalle**: casi todas las cifras llevan a la lista filtrada, pero varias muestran menos o más que la cifra
  (D-05), y el período de Inicio no viaja a la lista.
- **Filtros persistentes**: el proveedor elegido arriba se respeta en todo el sistema; el período no se comparte entre
  Inicio, Indicadores y Seguimiento (cada uno tiene el suyo).
- **Responsive**: verificado en esta rama con el recorrido e2e (47 pantallas, 4 usuarios, 1440 y 390 px, sin problemas) y
  capturas a 820 px: indicadores en franja deslizable en celular, segmentos plegados en tableta.
- **Atención sin abrir ventanas**: se cumple en Inicio; Seguimiento requiere cambiar de pestaña para ver riesgos de OC y de
  embarques.

### 7.2 Jerarquía propuesta

| Nivel | Para quién | Dónde | Qué muestra (máximo) |
|---|---|---|---|
| **Ejecutivo** | Dirección, finanzas | Indicadores › Resumen | 8 tarjetas con tendencia: facturado (por moneda), saldo por facturar, cuentas por cobrar vencidas (R02), lead time promedio, puntualidad contra ETA comprometida (R08), cumplimiento de XF de proveedores (R07), OC con llegada tarde, recepciones con diferencias. |
| **Operativo** | Cada rol, cada día | Inicio | 4–5 tarjetas sin duplicados (por facturar, documentos por completar, listas para embarcar, embarques en tránsito, OC con llegada tarde) + «Necesita su atención» (una entrada por concepto, con antigüedad R10) + paneles de embarques y contenedores con alcance. |
| **Diagnóstico** | Analistas, responsables de área | Seguimiento, Lead times, Reportes, Calidad de datos (R11) | Distribuciones (barras por etapa), tablas por origen y proveedor, hitos por documento, reportes analíticos con moneda obligatoria. |

Reglas de presentación: una cifra sin datos dice «—»; todo monto dice su moneda (y cuántos montos quedaron fuera si se
muestra una sola); todo porcentaje dice su base («n de m»); toda tarjeta lleva a una lista que muestra exactamente lo que
cuenta; las comparaciones de porcentajes, en puntos.

## 8. Arquitectura, rendimiento, seguridad y calidad de datos

### 8.1 Dónde se calcula cada cosa
- **Backend**: casi todo. Pero en **cinco módulos distintos** con su propia lógica: `seguimiento/dashboard.py` (Inicio),
  `seguimiento/indicadores.py` (Indicadores), `seguimiento/seguimiento.py` (Seguimiento), `transporte/leadtimes.py` (Lead
  times), `reportes/` (Reportes), además de `compras/ordenes.py` y `productos/productos.py` para sus listas.
- **Frontend** (debería estar en el backend): conteos por estado de Embarques (`EmbarquesView.vue:33-37`, sobre una segunda
  descarga completa), totales del embarque (`EmbarqueView.vue:69-71`, `ResumenEmbarque.vue:80-87`), avance de empaque de
  factura/PL (`FacturaView.vue`, `ResumenFactura.vue`, `PackingListView.vue`) y el total de la selección a facturar.
- **Propuesta proporcional**: un módulo `app/modulos/metricas/` con **definiciones de universo** reutilizables (p. ej. «OC
  vigentes», «facturas finalizadas», «embarques en alcance») y **una función por métrica**, que llamen Inicio, Indicadores,
  Seguimiento y Reportes. No hace falta un motor de métricas ni un almacén analítico.

### 8.2 Rendimiento (medido en la base de demostración, usuario interno)

| Endpoint | Consultas SQL | Tiempo |
|---|---|---|
| GET /api/dashboard (Inicio) | **127** | 89 ms |
| GET /api/tableros/resumen?dias=30 | 74 | 78 ms |
| GET /api/tableros/resumen?dias=365 | 62 | 56 ms |
| GET /api/tableros/logistica?dias=30 | 74 | 80 ms |
| GET /api/seguimiento/ordenes?size=25 | 75 | 54 ms |
| GET /api/seguimiento/leadtimes?size=25 | 49 | 41 ms |
| GET /api/seguimiento/documentos?size=25 | 61 | 52 ms |
| GET /api/seguimiento/embarques?size=25 | 81 | 59 ms |

Los tiempos son buenos con la demo (14 OC, 6 facturas); lo que preocupa es **cómo crecen**:
- [C] Inicio carga **todas** las facturas no canceladas de la historia con líneas y PL (`dashboard.py:424-428`), valida cada
  factura y PL editable (`validar_factura`, `validar_pl`) y además ejecuta `filas_seguimiento`, que carga **todas** las
  posiciones de OC (`seguimiento.py:143-147`). Crece con el historial completo, no con lo pendiente.
- [C] Los indicadores de lead time llaman a `leadtimes(size=1_000_000)` (`indicadores.py:208-221`): analizan todas las OC
  en memoria (se calcula una sola vez por petición, pero en cada petición).
- [C] Cada pestaña de Seguimiento recalcula `filas_seguimiento` completa; los KPI y los valores de filtro por columna
  vuelven a recorrerla. `filas_seguimiento` hace una consulta de líneas de PL por línea de factura (`seguimiento.py:179`).
- [C] `/embarques` es costosa (`resumen_unidad` por unidad, con consultas por unidad) y la pantalla la pide dos veces.
- [C] La prueba de rendimiento existente (`tests/test_rendimiento.py`) cubre listas, no `/dashboard` ni `/tableros`.
- **Índices que faltan** para filtrar por período: `facturas.finalizado_en`, `facturas.fecha`, `ordenes_compra.aprobada_en`,
  `embarques.arribo_real`/`eta`/`salida_real`, `recepciones.fecha`, `eventos_embarque(fecha, tipo)`,
  `historial(entidad, accion, fecha)`. No hay índices compuestos `(organizacion_id, estado)`.
- **Caché o tablas de resumen**: **no hacen falta hoy**. Primero: limitar Inicio a lo pendiente (no a toda la historia),
  agregar en SQL en lugar de en Python y los índices. Revaluar con más de ~50.000 líneas de OC o si Inicio supera 500 ms.
  Si algún día se guardan resultados, deben llevar su hora de cálculo visible para no presentar datos viejos como actuales.

### 8.3 Seguridad, permisos y aislamiento
- **Aislamiento por organización: correcto.** Todas las consultas del ORM reciben `with_loader_criteria(DeOrganizacion…)`
  (`app/core/organizacion.py:105-116`), incluidas subconsultas; en PostgreSQL hay RLS forzada
  (`alembic/versions/0047_multiempresa.py:74-81`). Observación: la política deja ver todo si no hay organización fijada en la
  conexión (diseño para tareas de plataforma); conviene una prueba que lo cubra para los tableros.
- **Permisos por indicador: correctos** (`indicadores.py:314`: permiso y datos ocultos por indicador; los de lead time
  exigen `seguimiento.ver`; Seguimiento exige `seguimiento.ver` en cada ruta).
- **Fugas de alcance dentro de la organización [C]**:
  1. Inicio: embarques (`_envios`), unidades de carga (`_contenedores`), «salen esta semana» y «embarques por llegar» no
     aplican `condiciones_alcance` (centros de sus sociedades y transportistas). El panel de embarques muestra **números de
     factura** de otras sociedades.
  2. Seguimiento › Embarques aplica proveedor y sociedad pero no centro/transportista; `indicadores._emb` aplica centro y
     transportista pero no proveedor (lo que es correcto solo porque logística es interna).
  3. Estado de cuenta de un tercero: pagos sin filtro de sociedad (`comercial/documentos.py:643-645`).
  4. Aplicar un pago a un documento de otra sociedad no se valida en el servidor (`comercial/pagos.py:108-128`).
  5. `visibilidad.RUTAS` no incluye `/api/documentos`, `/api/pagos` ni `/api/terceros` (`acceso/visibilidad.py:69`): un rol
     con «precios» ocultos que tuviera `comercial.ver` vería montos. Hoy `comercial.*` es solo interno.
- **Pruebas**: no hay pruebas de alcance (sociedad, transportista) para `/dashboard` ni `/tableros`.

### 8.4 Calidad de datos que afecta a los indicadores
- `tipo_cambio` = 1 por defecto y sin validación; `TipoCambio` sin uso (D-01).
- No se guarda la ETA comprometida ni la fecha de finalización de la PL; `enviada_en` y `revisado_en` se sobrescriben.
- `Aplicacion` (pago aplicado) no tiene fecha de negocio, solo `creado_en`: no se puede reconstruir el saldo a una fecha
  pasada con exactitud.
- Las etapas de lead time con duración negativa (fechas mal cargadas) se descartan sin aviso (`leadtimes.py:342-343`).
- La ficha de producto no guarda cuándo se envió a revisión (solo la bitácora).

### 8.5 Diseño genérico y configurable

**Ya configurable**: margen de riesgo (`DIAS_MARGEN_RIESGO`), aviso de borradores (`DIAS_ALERTA_BORRADOR`), aviso de
tienda (`DIAS_AVISO_TIENDA`) en `core/empresa.py:19-32`; reglas de lead time por región/país/puerto; qué indicadores ve
cada persona y cada rol; nombres de estados y listas de valores.

**Fijo en el código y que debería ser configurable** (sin tocar fórmulas):
- Umbral de «bueno» de la liberación a tiempo: **80 %** (`TableroLeadTimes.vue:124, 158`). → meta por indicador.
- Períodos (7/30/90/365) y número de tramos de la tendencia (`indicadores.py:41-43`).
- Ventanas «esta semana» = 7 días (`dashboard.py:331`, `seguimiento.py:363, 372`).
- Selección de Resumen (`PRINCIPALES`, `indicadores.py:309`) → ya se puede cambiar por rol; falta el valor por empresa.
- Tramos de antigüedad (R02/R10), tolerancias de puntualidad (R07/R08).
- Moneda de reporte y fuente de tipos de cambio.

**Debe quedar como regla del negocio (no configurable por el usuario)**: qué estados cuentan como vigentes, finalizados o
anulados en cada universo; la exclusión de borradores y anulados de los montos; la regla de no sumar monedas sin
conversión; la separación por unidad de medida; el alcance de datos.

**Propuesta**: que un usuario autorizado (`admin` o un permiso nuevo `indicadores.configurar`) defina **metas y umbrales**
(verde/ámbar por indicador), períodos por defecto, tolerancias y la moneda de reporte, guardados en
`Organizacion.configuracion` (como `reglas`), con registro en la bitácora. Las fórmulas siguen en el código, con pruebas.

## 9. Cambios necesarios en la base de datos

Solo los que necesitan los indicadores; todos con migración reversible y llenado desde la bitácora cuando sea posible.

| Cambio | Para qué | Llenado de datos existentes |
|---|---|---|
| `packing_lists.finalizado_en` (DateTime, índice) | I21 y ritmo de empaque | Desde `historial` (entidad `packing_list`, acción `finalizar`, última fecha); si falta, `actualizado_en`. |
| `embarques.eta_comprometida` (Date) | R08 / T12 | Para embarques ya salidos: ETA vigente en el evento SALIDA según `historial`; si no, `eta`. |
| `aplicaciones.fecha` (Date) | Saldos a una fecha, cobros por período | `creado_en::date`. |
| Índices: `facturas(finalizado_en)`, `facturas(fecha)`, `ordenes_compra(aprobada_en)`, `embarques(arribo_real)`, `embarques(eta)`, `recepciones(fecha)`, `eventos_embarque(fecha, tipo)`, `historial(entidad, accion, fecha)` | Indicadores por período | — |
| Opcional: `facturas.primera_finalizacion_en` | Si la empresa quiere fijar el período de una factura reabierta en su primera finalización | Desde `historial`. |

No se recomienda guardar saldos ni tablas de resumen por ahora.

## 10. Plan de mejoras ordenado por prioridad

### P0 — Crítica (datos financieros, indicadores engañosos, permisos)
| # | Mejora | KPI | Esfuerzo |
|---|---|---|---|
| 1 | Montos **por moneda** en Inicio (tarjeta, gráfica, período, tabla por proveedor) e Indicadores; nunca descartar ni sumar monedas en silencio. | I01, I20, I23, I25, T04, T07 | Medio |
| 2 | Reportes: moneda obligatoria al sumar importes; `moneda` en `lineas_oc`; código de moneda en pantalla y exportación. | O13 | Medio |
| 3 | Alcance de transporte en Inicio (`condiciones_alcance`). | I14, I18, I19, I22 | Bajo |
| 4 | Estado de cuenta y aplicación de pagos con sociedad validada en el servidor. | O12 | Bajo |
| 5 | «Embarques en camino» con conteo propio (sin el tope de 8). | I04 | Bajo |
| 6 | Indicadores: solo facturas FINALIZADAS (las reabiertas dejan de contar). | T06, T07 | Bajo |

### P1 — Alta (exactitud de métricas importantes, rendimiento)
| # | Mejora | KPI | Esfuerzo |
|---|---|---|---|
| 7 | Universo «OC vigentes» en Seguimiento, Lead times e Inicio (excluir BORRADOR, EN_APROBACION, RECHAZADA, CANCELADA; CERRADA según la métrica). | S01–S06, L01–L05, I05, I11, I12, T15–T17 | Medio |
| 8 | Servicio de métricas único y una definición por concepto (§5.1); Inicio, Indicadores y Seguimiento lo usan. | Grupos de §5.1 | Alto |
| 9 | `Kpi` muestra «—» sin datos y «%» en porcentajes; tono neutro sin datos. | L01, L03 y todos | Bajo |
| 10 | «Listas finalizadas» con `finalizado_en` de la PL (migración). | I21 | Medio |
| 11 | Puntualidad contra ETA comprometida (migración) y tolerancia configurable. | T12, R08 | Medio |
| 12 | «Días para aprobar» sin aprobaciones automáticas y desde el primer envío. | T03 | Medio |
| 13 | Inicio sobre lo pendiente (no toda la historia); agregaciones en SQL; índices de §9. | Rendimiento | Medio |
| 14 | Bloque financiero: R01, R02, R03, R05; R07 por proveedor. | Nuevos | Medio |
| 15 | Vencimiento por cuota en el estado de cobro. | O11 | Medio |

### P2 — Media (UX, contexto, comparabilidad, mantenimiento)
| # | Mejora | KPI | Esfuerzo |
|---|---|---|---|
| 16 | Clics que muestran exactamente lo que cuenta la cifra; período de Inicio hacia las listas. | S03, S11, S16, S17, I04, I20–I22 | Bajo |
| 17 | Porcentajes y avances por unidad de medida (o por valor) y sin tope oculto de 100 %. | S01, S07, O01, O04, O05 | Bajo–medio |
| 18 | Variación en **puntos porcentuales** para indicadores en %; «n de m» como base. | T12, T14, T16, L01, O10 | Bajo |
| 19 | Eliminar/combinar duplicados de Inicio y Seguimiento. | I09, I10, I13, I15, S02, T02 | Bajo |
| 20 | Metas y umbrales configurables por indicador (permiso dedicado, bitácora). | L01, L06 y Resumen | Medio |
| 21 | R04 (DSO por moneda), R06, R09, R10, R11. | Nuevos | Medio |
| 22 | Recepciones parciales en T14 (confirmar y corregir). | T14 | Bajo |
| 23 | Mover al backend los conteos y totales calculados en el navegador. | O06, O08 | Bajo |
| 24 | Pruebas de alcance y de consistencia entre pantallas (§11). | Todos | Medio |

### P3 — Baja (estética o beneficio limitado)
| # | Mejora | KPI | Esfuerzo |
|---|---|---|---|
| 25 | «12 de N» en Siguientes pasos; etiquetas fijas («Esta sem.»); formato único de kg. | I17, S13, O08 | Bajo |
| 26 | Desglose por modo en días de tránsito; denominador en familias; R12. | T13, O10, R12 | Bajo |
| 27 | Explicar en pantalla que los KPI de Seguimiento ignoran los filtros de columna. | S21 | Bajo |

## 11. Pruebas necesarias para demostrar que los indicadores son correctos

Ninguna de estas pruebas se ejecutó como prueba automatizada en esta fase: lo ejecutado fue la medición manual del §4.1.

1. **Multimoneda**: OCs y facturas en USD y EUR → cada tarjeta y tabla muestra un importe por moneda; la suma por moneda
   coincide con la lista de documentos filtrada por esa moneda; los reportes que suman importes agrupan por moneda.
2. **Estados**: una OC en cada estado (BORRADOR, EN_APROBACION, RECHAZADA, APROBADA, CERRADA, CANCELADA) → solo las
   vigentes cuentan en Seguimiento, Lead times, XF vencida y riesgo.
3. **Ciclo de una factura**: finalizar → reabrir → volver a finalizar en otro mes → el monto aparece en el período que fija
   la regla elegida y nunca en dos períodos; mientras está reabierta no cuenta.
4. **Cancelaciones**: factura cancelada, PL cancelada, embarque cancelado y pago anulado no cuentan en ningún indicador.
5. **Más de 8 embarques**: 10 en tránsito → 10 en Inicio, Indicadores y Seguimiento.
6. **Consistencia entre pantallas**: una prueba que pida el mismo concepto a Inicio, Indicadores y Seguimiento con los mismos
   filtros y compare (saldo por facturar, en tránsito, OC con llegada tarde, XF vencida, liberación a tiempo, lead time).
7. **Alcance**: usuario interno limitado a una sociedad y a un transportista → Inicio (paneles y conteos), Indicadores,
   Seguimiento y estado de cuenta muestran solo lo suyo; un proveedor solo ve sus números (ya cubierto en parte por
   `tests/test_indicadores.py::test_un_proveedor_ve_solo_sus_numeros`).
8. **Datos ocultos**: rol sin «precios» no recibe montos en `/dashboard`, `/tableros`, reportes ni rutas comerciales.
9. **Sin datos**: período vacío → «—» y sin tono (no «0» ni verde).
10. **Unidades de medida**: OC con pares y unidades → ningún total ni porcentaje las suma.
11. **Comparación de períodos**: los tramos tienen igual duración y el penúltimo es el período anterior (ya se cumple; dejarlo
    probado).
12. **Fechas de corte**: documento con fecha en el último día del período cuenta; en el primero del siguiente, no.
13. **Clic al detalle**: para cada tarjeta, el número de filas de la lista destino = la cifra.
14. **Puntualidad**: ETA movida en ruta → cuenta contra la comprometida.
15. **Rendimiento**: consultas de `/dashboard` y `/tableros/*` acotadas e independientes del tamaño del historial (como
    `tests/test_rendimiento.py` hace con las listas), y tiempo < 500 ms con un volumen sintético (p. ej. 20.000 líneas de OC).

## 12. Criterios de aceptación para validar las mejoras

1. Ningún monto mezcla monedas: cada importe muestra su código; si se convierte, indica la moneda de reporte, el tipo de
   cambio y su fecha.
2. Para los conceptos de §5.1, Inicio, Indicadores, Seguimiento y Reportes devuelven **el mismo valor** con los mismos
   filtros (prueba automática de consistencia en verde).
3. Las OC no vigentes, las facturas no finalizadas, las PL y embarques cancelados y los pagos anulados no cuentan donde la
   definición no los incluye (pruebas 2–4 en verde).
4. Ningún conteo está limitado por el tamaño de una lista visible.
5. Un indicador sin datos muestra «—»; un porcentaje muestra «%» y su base («n de m»); la variación de porcentajes está en
   puntos.
6. Cada tarjeta lleva a una lista cuya cantidad de filas es igual a la cifra.
7. Un usuario limitado por sociedad, centro o transportista no ve en ningún tablero datos fuera de su alcance (prueba 7 en
   verde); la aplicación de pagos entre sociedades responde 422.
8. `/dashboard` hace un número de consultas acotado y responde en < 500 ms con el volumen sintético acordado.
9. Las metas y umbrales se configuran por empresa sin tocar fórmulas, y su cambio queda en la bitácora.
10. Cada indicador del catálogo conserva su fórmula, fuente y período visibles («¿Cómo se calcula?») y coinciden con el
    código.
11. Suite completa del backend, lint del frontend y recorrido e2e en verde.

---

## Anexo A. Fichas de los indicadores existentes

Formato pedido: Nombre, Estado, Objetivo, Fórmula, Fuente, Filtros, Deficiencia, Mejora, Prioridad, Esfuerzo y Validación. Se agregan Pantalla, Período y Clasificación.

### Inicio — franja de indicadores

#### I01 · Por facturar

| Campo | Contenido |
|---|---|
| Nombre | Por facturar |
| Estado | Existente |
| Pantalla | Inicio (franja) |
| Objetivo | Cuánto valor de OC liberadas falta facturar; priorizar proveedores y OCs. |
| Fórmula | Σ max(cantidad − facturado, 0) × precio por posición de OC con `liberada = true` y posición no bloqueada; agrupado por moneda y se muestra **solo la moneda con mayor saldo** (`_moneda_principal`). Detalle «en N OC» = OCs con saldo de **todas** las monedas. |
| Fuente | `app/modulos/seguimiento/dashboard.py:37 _saldo_ocs`, `:68 _moneda_principal`, `:444`; `facturacion/cantidades.py:17 facturado_por_posicion` (facturas ≠ CANCELADA, incluye borradores); GET /api/dashboard |
| Filtros | Proveedor (alcance), sociedades del usuario; no filtra estado de la OC (CERRADA conserva `liberada`). |
| Período | Foto de hoy |
| Clasificación | Corregir |
| Deficiencia | [E] Con una OC en EUR, el valor bajó de USD 40,129 a 37,219 (el saldo en EUR desaparece) pero el detalle siguió diciendo «en 6 OC». [E] Ya en la demo difiere de «Saldo por facturar» de Indicadores (USD 41,543): universos distintos (liberada vs APROBADA, posiciones bloqueadas, moneda mayor vs moneda base). [C] Las OC CERRADAS o CANCELADAS con `liberada=true` siguen sumando. |
| Mejora | Una sola definición «Saldo por facturar» (OC APROBADAS, no bloqueadas) en el servicio de métricas; mostrar **un importe por moneda** (o convertido a la moneda de reporte con tipo de cambio documentado) y el conteo de OC por moneda. |
| Prioridad | P0 |
| Esfuerzo | Bajo: cambiar la consulta y la tarjeta para listar monedas. |
| Validación | Prueba con OC en dos monedas: la tarjeta muestra ambas y el total por moneda coincide con Σ de la lista de OC filtrada por moneda. |

#### I02 · Documentos en curso

| Campo | Contenido |
|---|---|
| Nombre | Documentos en curso |
| Estado | Existente |
| Pantalla | Inicio (franja) |
| Objetivo | Cuánto trabajo documental está abierto. |
| Fórmula | Facturas en BORRADOR/EN_CORRECCION + listas de empaque en BORRADOR/EN_CORRECCION de esas facturas no canceladas. |
| Fuente | `app/modulos/seguimiento/dashboard.py:450`; GET /api/dashboard |
| Filtros | Proveedor, sociedades. |
| Período | Foto de hoy |
| Clasificación | Mantener |
| Deficiencia | [M] Suma dos tipos de documento en una cifra; el detalle sí los separa. |
| Mejora | Mantenerla como cifra operativa; el clic lleva a facturas editables (no a las PL). |
| Prioridad | P3 |
| Esfuerzo | Bajo |
| Validación | Comparar con /facturas?vista=editables + PL abiertas. |

#### I03 · Lista para embarcar

| Campo | Contenido |
|---|---|
| Nombre | Lista para embarcar |
| Estado | Existente |
| Pantalla | Inicio (franja, interno) |
| Objetivo | Qué facturas ya pueden asignarse a un contenedor. |
| Fórmula | Facturas no canceladas con `_lista_para_transporte` (finalizada, todo en PL finalizadas) y con PL aún no confirmadas en unidad. |
| Fuente | `app/modulos/seguimiento/dashboard.py:453`, `facturacion/facturas.py:721 _lista_para_transporte` |
| Filtros | Proveedor, sociedades. |
| Período | Foto de hoy |
| Clasificación | Corregir |
| Deficiencia | [C] Otra pantalla usa el mismo nombre con otra regla: Seguimiento › Documentos cuenta **filas de PL** en LISTO_EMBARQUE sin exigir que toda la factura esté asignada. [S] `_lista_para_transporte` compara cantidades sumadas entre unidades de medida distintas. |
| Mejora | Definir «Lista para embarcar» una vez (por factura o por PL, explícito en el nombre) y usarla en Inicio, Facturas y Seguimiento. |
| Prioridad | P1 |
| Esfuerzo | Medio: unificar dos funciones. |
| Validación | Misma base: Inicio, /facturas?vista=lista_transporte y Seguimiento dan el mismo número. |

#### I04 · Embarques en camino

| Campo | Contenido |
|---|---|
| Nombre | Embarques en camino |
| Estado | Existente |
| Pantalla | Inicio (franja) |
| Objetivo | Cuánta carga viaja ahora. |
| Fórmula | Cuenta de embarques EN_TRANSITO o ARRIBADO **dentro de la lista del panel de embarques, que se corta en 8** (`res[:8]`). |
| Fuente | `app/modulos/seguimiento/dashboard.py:206 _envios` (`:232 return res[:8]`), `:437`, `:456` |
| Filtros | Proveedor (vía PL); sin alcance por sociedad/centro/transportista. |
| Período | Foto de hoy |
| Clasificación | Corregir |
| Deficiencia | [E] Con 10 embarques en tránsito: Inicio = **8**, Indicadores «Embarques en tránsito» = 10, Seguimiento «En tránsito» = 1. [C] Cuenta EN_TRANSITO + ARRIBADO pero el clic filtra solo EN_TRANSITO. [C] Sin alcance de transporte (ver §8). |
| Mejora | Contar con una consulta propia (no sobre la lista recortada), con el alcance de `condiciones_alcance`, y decidir si ARRIBADO cuenta (el clic debe coincidir). |
| Prioridad | P0 |
| Esfuerzo | Bajo |
| Validación | Con 10 embarques en tránsito, la tarjeta muestra 10 y el clic lista 10. |

#### I05 · OC en riesgo de atraso

| Campo | Contenido |
|---|---|
| Nombre | OC en riesgo de atraso |
| Estado | Existente |
| Pantalla | Inicio (franja) |
| Objetivo | Qué OC llegarán tarde a tienda para actuar antes. |
| Fórmula | OCs con alguna línea de seguimiento con `riesgo == 'ATRASO'` (holgura < 0 frente al límite en puerto). |
| Fuente | `app/modulos/seguimiento/dashboard.py:466`; `app/modulos/seguimiento/seguimiento.py:140 filas_seguimiento`; `app/modulos/transporte/leadtimes.py:272 _riesgo` (`DIAS_MARGEN_RIESGO`) |
| Filtros | Proveedor, sociedades; **no filtra estado de la OC**. |
| Período | Foto de hoy |
| Clasificación | Combinar |
| Deficiencia | [C] El título dice «en riesgo» pero cuenta las ya **atrasadas** (ATRASO); «en riesgo» en el resto del sistema es JUSTO. [E] Incluye OC canceladas/borrador (ver S01). [E] Indicadores «OC en riesgo de llegar tarde» da 1 y aquí 2 (excluye las ya ingresadas). Aparece dos veces en Inicio (I15). |
| Mejora | Una sola métrica «OC con llegada tarde» (ATRASO, OC vigentes, no ingresadas) y otra opcional «OC con poca holgura» (JUSTO); un solo lugar en Inicio. |
| Prioridad | P1 |
| Esfuerzo | Bajo |
| Validación | Misma cifra en Inicio, Indicadores, Seguimiento y Lead times para los mismos filtros. |

### Inicio — «Necesita su atención», pasos y paneles

#### I06 · Productos que bloquean facturas

| Campo | Contenido |
|---|---|
| Nombre | Productos que bloquean facturas |
| Estado | Existente |
| Pantalla | Inicio › Necesita su atención |
| Objetivo | Qué productos sin partida aprobada impiden finalizar facturas. |
| Fórmula | Productos (por artículo) de líneas de facturas editables sin partida arancelaria cuyo producto no está aprobado. |
| Fuente | `app/modulos/productos/productos.py:112 ids_bloquean_facturas` |
| Filtros | Proveedor. |
| Período | Foto de hoy |
| Clasificación | Mantener |
| Deficiencia | [C] Recorre las líneas en Python (O(líneas)); en la lista de productos ignora búsqueda, marca y filtros de columna. |
| Mejora | Mantener; mover el cálculo a una consulta agregada cuando crezca el volumen. |
| Prioridad | P3 |
| Esfuerzo | Bajo |
| Validación | Una factura borrador con un artículo sin partida suma 1. |

#### I07 · Productos por clasificar

| Campo | Contenido |
|---|---|
| Nombre | Productos por clasificar |
| Estado | Existente |
| Pantalla | Inicio › Necesita su atención (interno) |
| Objetivo | Cola de fichas que el equipo debe revisar. |
| Fórmula | Productos en estado `revision`. |
| Fuente | `app/modulos/seguimiento/dashboard.py:346` |
| Filtros | Proveedor. |
| Período | Foto de hoy |
| Clasificación | Mantener |
| Deficiencia | — |
| Mejora | — |
| Prioridad | P3 |
| Esfuerzo | Bajo |
| Validación | Igual a Indicadores «Fichas en revisión». |

#### I08 · Fichas devueltas

| Campo | Contenido |
|---|---|
| Nombre | Fichas devueltas |
| Estado | Existente |
| Pantalla | Inicio › Necesita su atención (proveedor) |
| Objetivo | Fichas que el proveedor debe corregir. |
| Fórmula | Productos en estado `observado`. |
| Fuente | `app/modulos/seguimiento/dashboard.py:349` |
| Filtros | Proveedor. |
| Período | Foto de hoy |
| Clasificación | Mantener |
| Deficiencia | — |
| Mejora | — |
| Prioridad | P3 |
| Esfuerzo | Bajo |
| Validación | Igual a Indicadores «Fichas devueltas». |

#### I09 · Facturas por finalizar

| Campo | Contenido |
|---|---|
| Nombre | Facturas por finalizar |
| Estado | Existente |
| Pantalla | Inicio › Necesita su atención |
| Objetivo | Facturas abiertas que frenan el embarque. |
| Fórmula | Facturas BORRADOR/EN_CORRECCION. |
| Fuente | `app/modulos/seguimiento/dashboard.py:351` |
| Filtros | Proveedor, sociedades. |
| Período | Foto de hoy |
| Clasificación | Combinar |
| Deficiencia | [C] Repite en la misma pantalla lo que ya cuenta I02 «Documentos en curso». |
| Mejora | Dejar una sola entrada (la de «Necesita su atención» con el detalle facturas/PL) y quitar la duplicada. |
| Prioridad | P2 |
| Esfuerzo | Bajo |
| Validación | Inicio no muestra dos cifras para el mismo universo. |

#### I10 · Listas de empaque incompletas

| Campo | Contenido |
|---|---|
| Nombre | Listas de empaque incompletas |
| Estado | Existente |
| Pantalla | Inicio › Necesita su atención |
| Objetivo | PL por empacar o finalizar. |
| Fórmula | PL en BORRADOR/EN_CORRECCION de facturas no canceladas; detalle: cuántas tienen pesos por confirmar (`validar_pl`). |
| Fuente | `app/modulos/seguimiento/dashboard.py:354` |
| Filtros | Proveedor, sociedades. |
| Período | Foto de hoy |
| Clasificación | Combinar |
| Deficiencia | [C] Mismo universo que la parte de PL de I02. [C] Ejecuta `validar_pl` por cada PL abierta en cada visita a Inicio. |
| Mejora | Unir con I02/I09 como un solo bloque «Documentos por completar». |
| Prioridad | P2 |
| Esfuerzo | Bajo |
| Validación | — |

#### I11 · OC con XF esta semana

| Campo | Contenido |
|---|---|
| Nombre | OC con XF esta semana |
| Estado | Existente |
| Pantalla | Inicio › Necesita su atención |
| Objetivo | Qué despachos vencen en 7 días con cantidad por facturar. |
| Fórmula | OCs con líneas en etapa POR_FACTURAR y `hoy ≤ fecha_xf ≤ hoy+7`. |
| Fuente | `app/modulos/seguimiento/dashboard.py:357`; `app/modulos/seguimiento/seguimiento.py:140` |
| Filtros | Proveedor, sociedades; **no filtra estado de la OC**. |
| Período | Próximos 7 días |
| Clasificación | Corregir |
| Deficiencia | [E] Incluye OC canceladas, en borrador o rechazadas (ver S01). |
| Mejora | Limitar a OC vigentes (APROBADA). |
| Prioridad | P1 |
| Esfuerzo | Bajo |
| Validación | Una OC cancelada con XF mañana no aparece. |

#### I12 · OC con XF vencida

| Campo | Contenido |
|---|---|
| Nombre | OC con XF vencida |
| Estado | Existente |
| Pantalla | Inicio › Necesita su atención |
| Objetivo | Despachos atrasados con saldo por facturar. |
| Fórmula | OCs con líneas POR_FACTURAR y `fecha_xf < hoy`. |
| Fuente | `app/modulos/seguimiento/dashboard.py:360` |
| Filtros | Proveedor, sociedades; no filtra estado de la OC. |
| Período | Foto de hoy |
| Clasificación | Combinar |
| Deficiencia | [E] Incluye OC canceladas/borrador. [C] Tres definiciones de «XF vencida»: esta (por línea), Seguimiento S04 (por OC) e Indicadores T05 (OC APROBADAS, facturado incluye borradores). |
| Mejora | Una sola métrica «OC con XF vencida y saldo» en el servicio de métricas. |
| Prioridad | P1 |
| Esfuerzo | Bajo |
| Validación | Misma cifra en Inicio, Seguimiento e Indicadores. |

#### I13 · Listas de empaque sin unidad de carga

| Campo | Contenido |
|---|---|
| Nombre | Listas de empaque sin unidad de carga |
| Estado | Existente |
| Pantalla | Inicio › Necesita su atención |
| Objetivo | PL finalizadas esperando contenedor. |
| Fórmula | PL FINALIZADO sin `unidad_carga_id` de facturas no canceladas. |
| Fuente | `app/modulos/seguimiento/dashboard.py:363` |
| Filtros | Proveedor, sociedades. |
| Período | Foto de hoy |
| Clasificación | Combinar |
| Deficiencia | [C] Es el detalle de I03 «Lista para embarcar» (que ya dice «N PL sin contenedor»). |
| Mejora | Mostrarla solo en un lugar. |
| Prioridad | P2 |
| Esfuerzo | Bajo |
| Validación | — |

#### I14 · Embarques que salen esta semana

| Campo | Contenido |
|---|---|
| Nombre | Embarques que salen esta semana |
| Estado | Existente |
| Pantalla | Inicio › Necesita su atención |
| Objetivo | Preparar salidas próximas. |
| Fórmula | Embarques PLANIFICADO con `hoy ≤ etd ≤ hoy+7`. |
| Fuente | `app/modulos/seguimiento/dashboard.py:367` |
| Filtros | **Ninguno** salvo la organización. |
| Período | Próximos 7 días |
| Clasificación | Corregir |
| Deficiencia | [C] No aplica el alcance de sociedad/centro/transportista que sí aplica el módulo de transporte (`transporte.py:69 condiciones_alcance`): un usuario limitado ve cuántos embarques salen fuera de su alcance. |
| Mejora | Aplicar `condiciones_alcance`. |
| Prioridad | P0 |
| Esfuerzo | Bajo |
| Validación | Usuario limitado a una sociedad: solo cuenta los de sus centros. |

#### I15 · OC en riesgo de llegar tarde

| Campo | Contenido |
|---|---|
| Nombre | OC en riesgo de llegar tarde |
| Estado | Existente |
| Pantalla | Inicio › Necesita su atención |
| Objetivo | Igual que I05. |
| Fórmula | Igual que I05 (mismo conjunto `atrasadas`). |
| Fuente | `app/modulos/seguimiento/dashboard.py:369` |
| Filtros | Igual que I05. |
| Período | Foto de hoy |
| Clasificación | Eliminar |
| Deficiencia | [C] Duplica I05 en la misma pantalla. |
| Mejora | Quitarla de la lista o de la franja (dejar una). |
| Prioridad | P2 |
| Esfuerzo | Bajo |
| Validación | — |

#### I16 · Llegadas esta semana

| Campo | Contenido |
|---|---|
| Nombre | Llegadas esta semana |
| Estado | Existente |
| Pantalla | Inicio › Necesita su atención |
| Objetivo | Prever recepciones. |
| Fórmula | Embarques (de filas de seguimiento en etapa CONTENEDOR/EN_TRANSITO) con `hoy ≤ eta ≤ hoy+7`. |
| Fuente | `app/modulos/seguimiento/dashboard.py:373` |
| Filtros | Proveedor, sociedades. |
| Período | Próximos 7 días |
| Clasificación | Combinar |
| Deficiencia | [C] Seguimiento › Embarques «Llegan en 7 días» usa otra regla (no arribados, 0–7 días, sobre `arribo_real or eta`). |
| Mejora | Una sola definición de «llegadas próximas». |
| Prioridad | P2 |
| Esfuerzo | Bajo |
| Validación | Misma cifra en ambas pantallas. |

#### I17 · Siguientes pasos (cantidad)

| Campo | Contenido |
|---|---|
| Nombre | Siguientes pasos (cantidad) |
| Estado | Existente |
| Pantalla | Inicio |
| Objetivo | Lista priorizada de tareas. |
| Fórmula | Tareas generadas por reglas (corregir, empacar, completar, finalizar, borrador antiguo, embarcar, fichas), máximo 12. |
| Fuente | `app/modulos/seguimiento/dashboard.py:235 _tareas` |
| Filtros | Proveedor, sociedades. |
| Período | Foto de hoy |
| Clasificación | Mantener |
| Deficiencia | [C] El contador muestra como máximo 12 aunque haya más. [C] Valida cada factura y PL editable en cada visita (costo). |
| Mejora | Mostrar «12 de N». |
| Prioridad | P3 |
| Esfuerzo | Bajo |
| Validación | Con 15 tareas muestra «12 de 15». |

#### I18 · Panel «Embarques» (avance del viaje, cajas)

| Campo | Contenido |
|---|---|
| Nombre | Panel «Embarques» (avance del viaje, cajas) |
| Estado | Existente |
| Pantalla | Inicio |
| Objetivo | Ver dónde va la carga. |
| Fórmula | Hasta 8 embarques PLANIFICADO/EN_TRANSITO/ARRIBADO; avance = (hoy − salida)/(ETA − salida) acotado 4–96 %; cajas = Σ cajas de sus PL. |
| Fuente | `app/modulos/seguimiento/dashboard.py:206 _envios`; `src/nucleo/utils.js:166 avanceViaje` |
| Filtros | Proveedor (vía PL); **sin alcance de sociedad/centro/transportista**. |
| Período | Foto de hoy |
| Clasificación | Corregir |
| Deficiencia | [C] Un usuario interno limitado ve códigos de embarque, puertos y **números de factura** de otras sociedades. [C] `avanceViaje` devuelve 50 % para un estado no previsto (p. ej. CANCELADO). |
| Mejora | Aplicar `condiciones_alcance`; tratar estados no previstos sin barra. |
| Prioridad | P0 |
| Esfuerzo | Bajo |
| Validación | Usuario limitado: el panel no muestra embarques ajenos. |

#### I19 · Unidades de carga en planificación (% llenado)

| Campo | Contenido |
|---|---|
| Nombre | Unidades de carga en planificación (% llenado) |
| Estado | Existente |
| Pantalla | Inicio (interno) |
| Objetivo | Aprovechar el contenedor antes de que salga. |
| Fórmula | Primeras 8 unidades de embarques PLANIFICADO; % = cbm × 100 / capacidad. |
| Fuente | `app/modulos/seguimiento/dashboard.py:382 _contenedores`; `transporte/transporte.py:124 resumen_unidad` |
| Filtros | **Ninguno** salvo la organización. |
| Período | Foto de hoy |
| Clasificación | Corregir |
| Deficiencia | [C] Sin alcance de sociedad/centro/transportista. [C] Solo % por volumen; el peso (también limitante) no se muestra. |
| Mejora | Aplicar el alcance; mostrar el mayor de % volumen y % peso. |
| Prioridad | P0 |
| Esfuerzo | Bajo |
| Validación | Usuario limitado solo ve sus unidades; una unidad con 95 % de peso y 40 % de volumen se marca. |

### Inicio — «Desempeño» y «Por proveedor»

#### I20 · Facturado (período)

| Campo | Contenido |
|---|---|
| Nombre | Facturado (período) |
| Estado | Existente |
| Pantalla | Inicio › Desempeño |
| Objetivo | Cuánto se facturó en el período elegido. |
| Fórmula | Σ cantidad × precio unitario de facturas FINALIZADAS con `fecha` (o `finalizado_en`) en el período, **solo en la moneda de mayor saldo por facturar**; filtro por marca en las líneas. Detalle: N facturas finalizadas. |
| Fuente | `app/modulos/seguimiento/dashboard.py:167 _resumen_periodo` (`:180`), `:133 _fecha_factura` |
| Filtros | Proveedor, sociedades, marca, período (mes en curso por defecto). |
| Período | Período elegido |
| Clasificación | Corregir |
| Deficiencia | [C] Las facturas en otra moneda **se descartan en silencio**, pero sí se cuentan en «N facturas finalizadas» (cifra y conteo no corresponden). [C] El filtro de marca recorta el monto pero no el conteo. [C] Fecha base distinta de Indicadores (`fecha` del documento vs `finalizado_en`): mismos datos, cifras distintas. [C] La «moneda principal» se elige por el saldo **por facturar**, no por lo facturado. |
| Mejora | Un importe por moneda (o conversión documentada); una sola fecha de devengo para «facturado» en todo el sistema; el conteo con los mismos filtros que el monto. |
| Prioridad | P0 |
| Esfuerzo | Medio |
| Validación | Factura en EUR finalizada en el mes: aparece su monto en EUR; conteo = facturas incluidas en el monto. |

#### I21 · Listas de empaque finalizadas (período)

| Campo | Contenido |
|---|---|
| Nombre | Listas de empaque finalizadas (período) |
| Estado | Existente |
| Pantalla | Inicio › Desempeño |
| Objetivo | Ritmo de empaque. |
| Fórmula | PL FINALIZADO cuyo `actualizado_en` cae en el período; detalle Σ cajas. |
| Fuente | `app/modulos/seguimiento/dashboard.py:174` |
| Filtros | Proveedor, sociedades; marca no aplica. |
| Período | Período elegido |
| Clasificación | Corregir |
| Deficiencia | [C] `actualizado_en` cambia con cualquier edición (`comun/historial.py:22 tocar`), no es la fecha de finalización: una PL finalizada el mes pasado y tocada hoy cuenta hoy. No existe `PackingList.finalizado_en`. |
| Mejora | Agregar `finalizado_en` a la PL (o leerlo de la bitácora `historial` acción `finalizar`). |
| Prioridad | P1 |
| Esfuerzo | Medio (migración + llenado desde historial) |
| Validación | PL finalizada en septiembre y editada en octubre cuenta en septiembre. |

#### I22 · Embarques por llegar (período)

| Campo | Contenido |
|---|---|
| Nombre | Embarques por llegar (período) |
| Estado | Existente |
| Pantalla | Inicio › Desempeño |
| Objetivo | Cuántos embarques llegan en el período. |
| Fórmula | Embarques con `eta` en el período (cualquier estado); detalle: cuántos ya arribaron. |
| Fuente | `app/modulos/seguimiento/dashboard.py:176` |
| Filtros | Proveedor (en Python); sin alcance de transporte. |
| Período | Período elegido |
| Clasificación | Reemplazar |
| Deficiencia | [C] Usa la ETA estimada, no el arribo real; incluye CANCELADO; sin alcance de sociedad/transportista; filtra proveedor recorriendo unidades y PL en Python. |
| Mejora | Reemplazar por «Arribos del período» (`arribo_real`, como T11) y, aparte, «Llegadas previstas» con el alcance correcto. |
| Prioridad | P1 |
| Esfuerzo | Bajo |
| Validación | Un embarque cancelado con ETA en el mes no cuenta. |

#### I23 · Gráfica «Valor facturado»

| Campo | Contenido |
|---|---|
| Nombre | Gráfica «Valor facturado» |
| Estado | Existente |
| Pantalla | Inicio › Desempeño |
| Objetivo | Tendencia de la facturación. |
| Fórmula | Σ cantidad × precio de facturas FINALIZADAS por día/semana/mes según el largo del período, **una sola moneda**. |
| Fuente | `app/modulos/seguimiento/dashboard.py:137 _serie_facturado`; `src/modulos/inicio/vistas/DashboardView.vue:228` |
| Filtros | Igual que I20. |
| Período | Período elegido |
| Clasificación | Corregir |
| Deficiencia | [C] Igual que I20: otras monedas desaparecen sin aviso. |
| Mejora | Serie por moneda o convertida; leyenda que diga la moneda y si hay montos excluidos. |
| Prioridad | P0 |
| Esfuerzo | Medio |
| Validación | Ver I20. |

#### I24 · Dónde está la mercancía

| Campo | Contenido |
|---|---|
| Nombre | Dónde está la mercancía |
| Estado | Existente |
| Pantalla | Inicio › Desempeño |
| Objetivo | En qué etapa está la cantidad (por facturar → embarcada). |
| Fórmula | Por unidad de medida: por facturar, facturada sin PL, en PL sin caja, empacada, embarcada. |
| Fuente | `app/modulos/seguimiento/dashboard.py:77 _flujo`; `src/modulos/inicio/componentes/BarraFlujo.vue` |
| Filtros | Proveedor, sociedades (facturas); por facturar = I01. |
| Período | Foto de hoy |
| Clasificación | Mejorar |
| Deficiencia | [C] Correcto en unidades (no mezcla). Hereda el universo de I01 (OC CERRADAS/CANCELADAS con `liberada`). [S] «Embarcado» = unidad CONFIRMADA en embarque ≠ PLANIFICADO, incluye CANCELADO si la PL siguió asignada. |
| Mejora | Usar el universo corregido de I01; excluir embarques cancelados. |
| Prioridad | P3 |
| Esfuerzo | Bajo |
| Validación | — |

#### I25 · Tabla «Por proveedor» (por facturar, en proceso, PL abiertas, listas, en camino)

| Campo | Contenido |
|---|---|
| Nombre | Tabla «Por proveedor» (por facturar, en proceso, PL abiertas, listas, en camino) |
| Estado | Existente |
| Pantalla | Inicio (interno) |
| Objetivo | Comparar la carga pendiente por proveedor. |
| Fórmula | Por facturar = Σ saldo × precio **de todas las monedas** (`por_proveedor[prov] += saldo*precio`), mostrado con la moneda principal; los conteos, por factura/PL. |
| Fuente | `app/modulos/seguimiento/dashboard.py:59-62`, `:396 _por_proveedor`; `src/modulos/inicio/vistas/DashboardView.vue:75` |
| Filtros | Sociedades (facturas); proveedores activos. |
| Período | Foto de hoy |
| Clasificación | Corregir |
| Deficiencia | [E] Con una OC de The North Face en EUR (2,910), la columna siguió en **28,537 «USD»**: sumó EUR como USD. |
| Mejora | Por facturar por proveedor y moneda. |
| Prioridad | P0 |
| Esfuerzo | Bajo |
| Validación | Proveedor con OC en USD y EUR muestra dos importes. |

### Indicadores (catálogo de tableros)

#### T01 · OC pendientes de aprobación

| Campo | Contenido |
|---|---|
| Nombre | OC pendientes de aprobación |
| Estado | Existente |
| Pantalla | Indicadores › Compras |
| Objetivo | Cola de aprobación. |
| Fórmula | OCs en EN_APROBACION. |
| Fuente | `app/modulos/seguimiento/indicadores.py:103 oc_en_aprobacion`; GET /api/tableros/{modulo} |
| Filtros | Proveedor, sociedades. |
| Período | Foto de hoy |
| Clasificación | Mantener |
| Deficiencia | — |
| Mejora | — |
| Prioridad | P3 |
| Esfuerzo | Bajo |
| Validación | Igual al banner de aprobaciones pendientes. |

#### T02 · OC aprobadas

| Campo | Contenido |
|---|---|
| Nombre | OC aprobadas |
| Estado | Existente |
| Pantalla | Indicadores › Compras |
| Objetivo | Volumen de aprobación. |
| Fórmula | OCs con `aprobada_en` en el período. |
| Fuente | `app/modulos/seguimiento/indicadores.py:107 oc_aprobadas`; GET /api/tableros/{modulo} |
| Filtros | Proveedor, sociedades. |
| Período | Período + tendencia |
| Clasificación | Combinar |
| Deficiencia | [M] Cuenta sola aporta poco; incluye aprobaciones automáticas (sin reglas). |
| Mejora | Unir con T01 y T03 en una tarjeta «Aprobación de OC» (pendientes, aprobadas, días). |
| Prioridad | P3 |
| Esfuerzo | Bajo |
| Validación | — |

#### T03 · Días para aprobar

| Campo | Contenido |
|---|---|
| Nombre | Días para aprobar |
| Estado | Existente |
| Pantalla | Indicadores › Compras y Resumen |
| Objetivo | Rapidez del circuito de aprobación. |
| Fórmula | Promedio de `aprobada_en − enviada_en` (días) de OCs aprobadas en el período. |
| Fuente | `app/modulos/seguimiento/indicadores.py:113 dias_aprobacion`; GET /api/tableros/{modulo} |
| Filtros | Proveedor, sociedades. |
| Período | Período + tendencia |
| Clasificación | Corregir |
| Deficiencia | [C] Las OCs aprobadas **automáticamente** (sin reglas) aportan 0 días (`compras/flujo_oc.py:332-334`) y bajan el promedio. [C] Al reenviar tras un rechazo, `enviada_en` se sobrescribe: el ciclo completo no se mide. [M] Sin mediana. |
| Mejora | Excluir las aprobaciones automáticas; medir desde el primer envío (bitácora `historial` acción `enviada`); mostrar mediana y cantidad. |
| Prioridad | P1 |
| Esfuerzo | Medio |
| Validación | OC aprobada automáticamente no cambia el promedio. |

#### T04 · Saldo por facturar

| Campo | Contenido |
|---|---|
| Nombre | Saldo por facturar |
| Estado | Existente |
| Pantalla | Indicadores › Compras y Resumen |
| Objetivo | Compromiso de compra pendiente de facturar. |
| Fórmula | Σ (cantidad − facturado) × precio de posiciones de OC APROBADAS con saldo, **solo en la moneda base**; facturado = facturas ≠ CANCELADA (incluye borradores). |
| Fuente | `app/modulos/seguimiento/indicadores.py:126 saldo_por_facturar`; GET /api/tableros/{modulo} |
| Filtros | Proveedor, sociedades; oculto sin el dato «precios». |
| Período | Foto de hoy |
| Clasificación | Corregir |
| Deficiencia | [E] Con una OC en EUR el valor bajó de 41,543 a 37,219: el saldo en EUR se descarta sin aviso. [E] Difiere de I01 con los mismos datos (41,543 vs 40,129). [C] Incluye posiciones bloqueadas. |
| Mejora | Ver I01: una definición, importes por moneda. |
| Prioridad | P0 |
| Esfuerzo | Bajo |
| Validación | Igual a I01 y a Σ de la lista de OC por moneda. |

#### T05 · OC con fecha de despacho vencida

| Campo | Contenido |
|---|---|
| Nombre | OC con fecha de despacho vencida |
| Estado | Existente |
| Pantalla | Indicadores › Compras |
| Objetivo | Despachos atrasados. |
| Fórmula | OCs APROBADAS con `fecha_xf < hoy` y alguna posición con cantidad > facturado (incluye borradores). |
| Fuente | `app/modulos/seguimiento/indicadores.py:137 oc_atrasadas`; GET /api/tableros/{modulo} |
| Filtros | Proveedor, sociedades. |
| Período | Foto de hoy |
| Clasificación | Combinar |
| Deficiencia | [C] Una factura en borrador ya «cubre» la cantidad aunque no se haya despachado. [C] Tercera definición de XF vencida (I12, S04). |
| Mejora | Unificar con I12/S04 en el servicio de métricas; decidir si el borrador cuenta como cubierto. |
| Prioridad | P1 |
| Esfuerzo | Bajo |
| Validación | — |

#### T06 · Facturas finalizadas

| Campo | Contenido |
|---|---|
| Nombre | Facturas finalizadas |
| Estado | Existente |
| Pantalla | Indicadores › Facturación |
| Objetivo | Volumen de facturación. |
| Fórmula | Facturas ≠ CANCELADA con `finalizado_en` en el período. |
| Fuente | `app/modulos/seguimiento/indicadores.py:146 facturas_finalizadas`; GET /api/tableros/{modulo} |
| Filtros | Proveedor, sociedades. |
| Período | Período + tendencia |
| Clasificación | Combinar |
| Deficiencia | [E] Una factura **reabierta** (EN_CORRECCION) siguió contando: 6 → 6 (Inicio pasó a 5). `reabrir` no limpia `finalizado_en` (`facturacion/facturas.py:629`) y al volver a finalizar se sobrescribe y la factura cambia de período. |
| Mejora | Contar solo FINALIZADA y unir con T07 (monto y cantidad en una tarjeta). |
| Prioridad | P1 |
| Esfuerzo | Bajo |
| Validación | Factura reabierta deja de contar; al refinalizar cuenta en la fecha nueva y queda registrado. |

#### T07 · Monto facturado

| Campo | Contenido |
|---|---|
| Nombre | Monto facturado |
| Estado | Existente |
| Pantalla | Indicadores › Facturación y Resumen |
| Objetivo | Facturación del período. |
| Fórmula | Σ cantidad × precio unitario de facturas ≠ CANCELADA con `finalizado_en` en el período **en la moneda base**. |
| Fuente | `app/modulos/seguimiento/indicadores.py:157 importe_facturado`; GET /api/tableros/{modulo} |
| Filtros | Proveedor, sociedades; oculto sin «precios». |
| Período | Período + tendencia |
| Clasificación | Corregir |
| Deficiencia | [E] Incluye la factura reabierta (17,285 se mantuvo; Inicio bajó a 15,920). [C] Las facturas en otra moneda se descartan sin aviso. [C] Distinta fecha base que Inicio I20. |
| Mejora | Solo FINALIZADA; importe por moneda; fecha de devengo única. |
| Prioridad | P0 |
| Esfuerzo | Bajo |
| Validación | Igual a I20 para el mismo período y filtros. |

#### T08 · Facturas en curso

| Campo | Contenido |
|---|---|
| Nombre | Facturas en curso |
| Estado | Existente |
| Pantalla | Indicadores › Facturación |
| Objetivo | Trabajo abierto. |
| Fórmula | Facturas BORRADOR/EN_CORRECCION. |
| Fuente | `app/modulos/seguimiento/indicadores.py:152 facturas_abiertas`; GET /api/tableros/{modulo} |
| Filtros | Proveedor, sociedades. |
| Período | Foto de hoy |
| Clasificación | Mantener |
| Deficiencia | — |
| Mejora | — |
| Prioridad | P3 |
| Esfuerzo | Bajo |
| Validación | Igual a /facturas?vista=editables. |

#### T09 · Listas de empaque en curso

| Campo | Contenido |
|---|---|
| Nombre | Listas de empaque en curso |
| Estado | Existente |
| Pantalla | Indicadores › Facturación |
| Objetivo | Empaque abierto. |
| Fórmula | PL BORRADOR/EN_CORRECCION de facturas no canceladas. |
| Fuente | `app/modulos/seguimiento/indicadores.py:166 pls_pendientes`; GET /api/tableros/{modulo} |
| Filtros | Proveedor, sociedades. |
| Período | Foto de hoy |
| Clasificación | Mantener |
| Deficiencia | — |
| Mejora | — |
| Prioridad | P3 |
| Esfuerzo | Bajo |
| Validación | Igual a I10. |

#### T10 · Embarques en tránsito

| Campo | Contenido |
|---|---|
| Nombre | Embarques en tránsito |
| Estado | Existente |
| Pantalla | Indicadores › Logística |
| Objetivo | Carga viajando. |
| Fórmula | Embarques EN_TRANSITO. |
| Fuente | `app/modulos/seguimiento/indicadores.py:172 embarques_en_transito`; GET /api/tableros/{modulo} |
| Filtros | Alcance de transporte (centros y transportistas). |
| Período | Foto de hoy |
| Clasificación | Mantener |
| Deficiencia | [E] Correcto (10 con 10 en tránsito); es la referencia para corregir I04 y S10. |
| Mejora | — |
| Prioridad | P3 |
| Esfuerzo | Bajo |
| Validación | — |

#### T11 · Arribos

| Campo | Contenido |
|---|---|
| Nombre | Arribos |
| Estado | Existente |
| Pantalla | Indicadores › Logística |
| Objetivo | Volumen recibido en puerto. |
| Fórmula | Embarques ≠ CANCELADO con `arribo_real` en el período. |
| Fuente | `app/modulos/seguimiento/indicadores.py:176 arribos`; GET /api/tableros/{modulo} |
| Filtros | Alcance de transporte. |
| Período | Período + tendencia |
| Clasificación | Mantener |
| Deficiencia | — |
| Mejora | Reemplaza a I22. |
| Prioridad | P3 |
| Esfuerzo | Bajo |
| Validación | — |

#### T12 · Arribos a tiempo

| Campo | Contenido |
|---|---|
| Nombre | Arribos a tiempo |
| Estado | Existente |
| Pantalla | Indicadores › Logística y Resumen |
| Objetivo | Cumplimiento del transportista. |
| Fórmula | Embarques arribados en el período con `arribo_real ≤ eta` ÷ arribados con ETA × 100. |
| Fuente | `app/modulos/seguimiento/indicadores.py:181 puntualidad`; GET /api/tableros/{modulo} |
| Filtros | Alcance de transporte. |
| Período | Período + tendencia |
| Clasificación | Corregir |
| Deficiencia | [C] La ETA se puede editar en tránsito hasta el arribo (`transporte/transporte.py:343-345`) y no se guarda la ETA comprometida: actualizar la ETA en ruta convierte un atraso en «a tiempo». [M] Sin tolerancia configurable. |
| Mejora | Guardar la ETA comprometida al registrar la salida (o leerla del historial) y medir contra ella; tolerancia en días configurable. |
| Prioridad | P1 |
| Esfuerzo | Medio (campo nuevo) |
| Validación | Embarque con ETA movida en ruta y arribo después de la original cuenta como tarde. |

#### T13 · Días de tránsito

| Campo | Contenido |
|---|---|
| Nombre | Días de tránsito |
| Estado | Existente |
| Pantalla | Indicadores › Logística |
| Objetivo | Duración del viaje. |
| Fórmula | Promedio de `arribo_real − salida_real` de embarques arribados en el período. |
| Fuente | `app/modulos/seguimiento/indicadores.py:188 dias_transito`; GET /api/tableros/{modulo} |
| Filtros | Alcance de transporte. |
| Período | Período + tendencia |
| Clasificación | Mantener |
| Deficiencia | [M] Sin mediana ni separación por modo/ruta. |
| Mejora | Agregar desglose por modo de transporte. |
| Prioridad | P3 |
| Esfuerzo | Bajo |
| Validación | — |

#### T14 · Recepciones con diferencias

| Campo | Contenido |
|---|---|
| Nombre | Recepciones con diferencias |
| Estado | Existente |
| Pantalla | Indicadores › Logística y Resumen |
| Objetivo | Calidad de lo recibido. |
| Fórmula | Líneas de recepción del período con cantidad recibida ≠ empacada o con dañadas ÷ líneas recibidas × 100. |
| Fuente | `app/modulos/seguimiento/indicadores.py:195 recepcion_con_diferencias`; GET /api/tableros/{modulo} |
| Filtros | Proveedor, sociedades (de la factura). |
| Período | Período + tendencia |
| Clasificación | Corregir |
| Deficiencia | [S] Si una línea de PL se recibe en dos recepciones parciales, cada una se compara con la cantidad total empacada y ambas cuentan como diferencia. |
| Mejora | Comparar por línea de PL el total recibido acumulado; confirmar si existen recepciones parciales. |
| Prioridad | P2 |
| Esfuerzo | Bajo |
| Validación | Recepción parcial 50+50 de 100 no cuenta como diferencia. |

#### T15 · Lead time promedio

| Campo | Contenido |
|---|---|
| Nombre | Lead time promedio |
| Estado | Existente |
| Pantalla | Indicadores › Logística y Resumen |
| Objetivo | Tiempo de ciclo de la OC a bodega. |
| Fórmula | Promedio de Σ duraciones de etapas de OCs con todas las etapas y con ingreso a bodega en el período. |
| Fuente | `app/modulos/seguimiento/indicadores.py:224 lead_time_prom`; GET /api/tableros/{modulo} |
| Filtros | Proveedor, sociedades (vía `leadtimes()`); **no filtra estado de la OC**. |
| Período | Período + tendencia |
| Clasificación | Corregir |
| Deficiencia | [C] Incluye OCs de cualquier estado. [C] Una OC con una etapa de duración negativa (dato erróneo) queda fuera sin aviso. [C] Distinto de L03 (OCs **creadas** en el período). [E] Analiza todas las OC en memoria en cada consulta. |
| Mejora | OCs vigentes; contar las excluidas por datos incompletos; una sola definición con L03 (por fecha de ingreso). |
| Prioridad | P1 |
| Esfuerzo | Medio |
| Validación | Igual a L03 con el mismo período. |

#### T16 · Liberación logística a tiempo

| Campo | Contenido |
|---|---|
| Nombre | Liberación logística a tiempo |
| Estado | Existente |
| Pantalla | Indicadores › Logística y Resumen |
| Objetivo | Si logística libera antes de la meta. |
| Fórmula | OCs liberadas en el período en o antes de su meta ÷ liberadas en el período × 100. |
| Fuente | `app/modulos/seguimiento/indicadores.py:229 lib_a_tiempo`; GET /api/tableros/{modulo} |
| Filtros | Igual que T15. |
| Período | Período + tendencia |
| Clasificación | Corregir |
| Deficiencia | [E] En la demo da 91,7 % y L01 92 % con otro universo (OCs creadas vs liberadas). [C] Incluye OCs de cualquier estado. |
| Mejora | Una definición; OCs vigentes; mostrar «n de m». |
| Prioridad | P1 |
| Esfuerzo | Bajo |
| Validación | Igual a L01. |

#### T17 · OC en riesgo de llegar tarde

| Campo | Contenido |
|---|---|
| Nombre | OC en riesgo de llegar tarde |
| Estado | Existente |
| Pantalla | Indicadores › Logística y Resumen |
| Objetivo | Igual que I05. |
| Fórmula | OCs con riesgo ATRASO y sin ingreso a bodega. |
| Fuente | `app/modulos/seguimiento/indicadores.py:235 oc_en_riesgo`; GET /api/tableros/{modulo} |
| Filtros | Igual que T15. |
| Período | Foto de hoy |
| Clasificación | Combinar |
| Deficiencia | [E] Da 1 donde Inicio/Seguimiento/Lead times dan 2. [C] Nombre «en riesgo» para ATRASO. |
| Mejora | Ver I05. |
| Prioridad | P1 |
| Esfuerzo | Bajo |
| Validación | Ver I05. |

#### T18 · Fichas en revisión

| Campo | Contenido |
|---|---|
| Nombre | Fichas en revisión |
| Estado | Existente |
| Pantalla | Indicadores › Productos |
| Objetivo | Cola de clasificación. |
| Fórmula | Productos en `revision`. |
| Fuente | `app/modulos/seguimiento/indicadores.py:240 fichas_en_revision`; GET /api/tableros/{modulo} |
| Filtros | Proveedor. |
| Período | Foto de hoy |
| Clasificación | Mantener |
| Deficiencia | — |
| Mejora | — |
| Prioridad | P3 |
| Esfuerzo | Bajo |
| Validación | Igual a I07. |

#### T19 · Fichas devueltas

| Campo | Contenido |
|---|---|
| Nombre | Fichas devueltas |
| Estado | Existente |
| Pantalla | Indicadores › Productos |
| Objetivo | Correcciones pendientes del proveedor. |
| Fórmula | Productos en `observado`. |
| Fuente | `app/modulos/seguimiento/indicadores.py:244 fichas_devueltas`; GET /api/tableros/{modulo} |
| Filtros | Proveedor. |
| Período | Foto de hoy |
| Clasificación | Mantener |
| Deficiencia | — |
| Mejora | — |
| Prioridad | P3 |
| Esfuerzo | Bajo |
| Validación | Igual a I08. |

#### T20 · Fichas aprobadas

| Campo | Contenido |
|---|---|
| Nombre | Fichas aprobadas |
| Estado | Existente |
| Pantalla | Indicadores › Productos |
| Objetivo | Ritmo de clasificación. |
| Fórmula | Productos aprobados/corregidos con `revisado_en` en el período. |
| Fuente | `app/modulos/seguimiento/indicadores.py:248 fichas_aprobadas`; GET /api/tableros/{modulo} |
| Filtros | Proveedor. |
| Período | Período + tendencia |
| Clasificación | Mejorar |
| Deficiencia | [C] `revisado_en` guarda solo la última revisión; una ficha reaprobada se mueve de período. |
| Mejora | Complementar con «Tiempo de clasificación» (R09). |
| Prioridad | P3 |
| Esfuerzo | Bajo |
| Validación | — |

#### T21 · Productos sin clasificar

| Campo | Contenido |
|---|---|
| Nombre | Productos sin clasificar |
| Estado | Existente |
| Pantalla | Indicadores › Productos |
| Objetivo | Avance de clasificación. |
| Fórmula | Productos en `borrador` o `sugerida`. |
| Fuente | `app/modulos/seguimiento/indicadores.py:254 sin_clasificar`; GET /api/tableros/{modulo} |
| Filtros | Proveedor. |
| Período | Foto de hoy |
| Clasificación | Corregir |
| Deficiencia | [C] El nombre engaña: excluye `revision` y `observado`, que tampoco están clasificados. |
| Mejora | Renombrar «Fichas sin enviar» o incluir todos los no aprobados. |
| Prioridad | P2 |
| Esfuerzo | Bajo |
| Validación | Suma de T18+T19+T21 = productos no aprobados. |

### Seguimiento — Órdenes de compra

#### S01 · Órdenes de compra (y «% facturado»)

| Campo | Contenido |
|---|---|
| Nombre | Órdenes de compra (y «% facturado») |
| Estado | Existente |
| Pantalla | Seguimiento › Órdenes |
| Objetivo | Volumen y avance de facturación. |
| Fórmula | OCs con filas de seguimiento; % = Σ(total − por facturar) × 100 / Σ total **sumando cantidades de distintas unidades de medida**. |
| Fuente | `app/modulos/seguimiento/seguimiento.py:524-530`, `:140 filas_seguimiento`; GET /api/seguimiento/ordenes |
| Filtros | Proveedor, sociedades, filtros de pantalla; **no filtra estado de la OC**; los filtros de columna no cambian los KPI. |
| Período | Foto de hoy |
| Clasificación | Corregir |
| Deficiencia | [E] Tras cancelar una OC y pasar otra a borrador, siguió en **14**. [C] El % suma pares + unidades + cajas. [C] La lista de Órdenes calcula el % por **valor** (O01): dos «% facturado» distintos. |
| Mejora | OCs vigentes; % por valor (como O01) o por unidad de medida, explícito. |
| Prioridad | P1 |
| Esfuerzo | Bajo |
| Validación | OC cancelada no cuenta; % igual al de la lista de OC. |

#### S02 · Liberadas

| Campo | Contenido |
|---|---|
| Nombre | Liberadas |
| Estado | Existente |
| Pantalla | Seguimiento › Órdenes |
| Objetivo | OCs que se pueden facturar. |
| Fórmula | OCs con estado de seguimiento distinto de SIN_COMERCIAL/SIN_LOGISTICA. |
| Fuente | `app/modulos/seguimiento/seguimiento.py:526` |
| Filtros | Igual que S01. |
| Período | Foto de hoy |
| Clasificación | Eliminar |
| Deficiencia | [C] Es S01 − S03; siempre en verde; el clic no filtra nada. |
| Mejora | Quitarla (la información está en S01 y S03). |
| Prioridad | P3 |
| Esfuerzo | Bajo |
| Validación | — |

#### S03 · No liberadas

| Campo | Contenido |
|---|---|
| Nombre | No liberadas |
| Estado | Existente |
| Pantalla | Seguimiento › Órdenes |
| Objetivo | Qué bloquea la facturación. |
| Fórmula | OCs SIN_COMERCIAL + SIN_LOGISTICA. |
| Fuente | `app/modulos/seguimiento/seguimiento.py:527` |
| Filtros | Igual que S01. |
| Período | Foto de hoy |
| Clasificación | Corregir |
| Deficiencia | [C] El clic filtra solo SIN_COMERCIAL (`TableroOrdenes.vue:112`): la lista muestra menos que la cifra. [E] Incluye OCs canceladas. |
| Mejora | Filtro con ambos estados; OCs vigentes. |
| Prioridad | P2 |
| Esfuerzo | Bajo |
| Validación | Cifra = filas tras el clic. |

#### S04 · XF vencida, sin facturar

| Campo | Contenido |
|---|---|
| Nombre | XF vencida, sin facturar |
| Estado | Existente |
| Pantalla | Seguimiento › Órdenes |
| Objetivo | Despachos atrasados. |
| Fórmula | OCs con `fecha_xf < hoy` y por facturar > 0. |
| Fuente | `app/modulos/seguimiento/seguimiento.py:528`, `:590` |
| Filtros | Igual que S01. |
| Período | Foto de hoy |
| Clasificación | Combinar |
| Deficiencia | Ver I12. |
| Mejora | Ver I12. |
| Prioridad | P1 |
| Esfuerzo | Bajo |
| Validación | Ver I12. |

#### S05 · Atrasado para el cierre de puerto

| Campo | Contenido |
|---|---|
| Nombre | Atrasado para el cierre de puerto |
| Estado | Existente |
| Pantalla | Seguimiento › Órdenes |
| Objetivo | OCs que llegan tarde. |
| Fórmula | OCs con riesgo ATRASO. |
| Fuente | `app/modulos/seguimiento/seguimiento.py:529` |
| Filtros | Igual que S01; visible con «fechas internas». |
| Período | Foto de hoy |
| Clasificación | Combinar |
| Deficiencia | Ver I05. |
| Mejora | Ver I05. |
| Prioridad | P1 |
| Esfuerzo | Bajo |
| Validación | Ver I05. |

#### S06 · OC por estado (barras)

| Campo | Contenido |
|---|---|
| Nombre | OC por estado (barras) |
| Estado | Existente |
| Pantalla | Seguimiento › Órdenes |
| Objetivo | Distribución por etapa; filtra la tabla. |
| Fórmula | Cuenta de OCs por estado de seguimiento. |
| Fuente | `app/modulos/seguimiento/seguimiento.py:520-536` |
| Filtros | Igual que S01. |
| Período | Foto de hoy |
| Clasificación | Corregir |
| Deficiencia | [E] Incluye OCs canceladas/borrador en «Liberada, sin facturar». |
| Mejora | OCs vigentes. |
| Prioridad | P1 |
| Esfuerzo | Bajo |
| Validación | Σ barras = S01. |

#### S07 · Avance por OC (barra y «% facturado · total»)

| Campo | Contenido |
|---|---|
| Nombre | Avance por OC (barra y «% facturado · total») |
| Estado | Existente |
| Pantalla | Seguimiento › Órdenes (fila) |
| Objetivo | Avance de cada OC. |
| Fórmula | Por OC: tramos de cantidad por etapa ÷ total; texto con el total sumado entre unidades. |
| Fuente | `app/modulos/seguimiento/seguimiento.py:584`; `src/modulos/seguimiento/componentes/TableroOrdenes.vue:140` |
| Filtros | — |
| Período | Foto de hoy |
| Clasificación | Corregir |
| Deficiencia | [C] Total y % mezclan unidades de medida. |
| Mejora | Por unidad o por valor. |
| Prioridad | P2 |
| Esfuerzo | Bajo |
| Validación | — |

### Seguimiento — Embarques y unidades de carga

#### S08 · Embarques (por modo)

| Campo | Contenido |
|---|---|
| Nombre | Embarques (por modo) |
| Estado | Existente |
| Pantalla | Seguimiento › Embarques |
| Objetivo | Volumen de embarques. |
| Fórmula | Embarques con filas de seguimiento; detalle por modo. |
| Fuente | `app/modulos/seguimiento/seguimiento.py:368-376`; GET /api/seguimiento/embarques |
| Filtros | Proveedor, sociedades; **sin alcance de centro/transportista** (a diferencia de /embarques). |
| Período | Foto de hoy |
| Clasificación | Mantener |
| Deficiencia | [E] Solo cuenta embarques con mercancía asociada (con 10 en tránsito sin carga, cuenta 1). [C] Alcance distinto del de /embarques. |
| Mejora | Alinear el alcance con `condiciones_alcance`. |
| Prioridad | P2 |
| Esfuerzo | Bajo |
| Validación | — |

#### S09 · Unidades de carga

| Campo | Contenido |
|---|---|
| Nombre | Unidades de carga |
| Estado | Existente |
| Pantalla | Seguimiento › Embarques |
| Objetivo | Contenedores en juego. |
| Fórmula | Σ unidades con filas. |
| Fuente | `app/modulos/seguimiento/seguimiento.py:371` |
| Filtros | Igual que S08. |
| Período | Foto de hoy |
| Clasificación | Mantener |
| Deficiencia | — |
| Mejora | — |
| Prioridad | P3 |
| Esfuerzo | Bajo |
| Validación | — |

#### S10 · En tránsito

| Campo | Contenido |
|---|---|
| Nombre | En tránsito |
| Estado | Existente |
| Pantalla | Seguimiento › Embarques |
| Objetivo | Carga viajando. |
| Fórmula | Embarques EN_TRANSITO con filas. |
| Fuente | `app/modulos/seguimiento/seguimiento.py:372` |
| Filtros | Igual que S08. |
| Período | Foto de hoy |
| Clasificación | Combinar |
| Deficiencia | [E] Da 1 con 10 en tránsito (Indicadores 10, Inicio 8). |
| Mejora | Una sola métrica (T10) para las tres pantallas. |
| Prioridad | P1 |
| Esfuerzo | Bajo |
| Validación | Misma cifra en las tres pantallas. |

#### S11 · Llegan en 7 días

| Campo | Contenido |
|---|---|
| Nombre | Llegan en 7 días |
| Estado | Existente |
| Pantalla | Seguimiento › Embarques |
| Objetivo | Prever recepciones. |
| Fórmula | No arribados con 0 ≤ (arribo_real o ETA − hoy) ≤ 7. |
| Fuente | `app/modulos/seguimiento/seguimiento.py:373` |
| Filtros | Igual que S08. |
| Período | Próximos 7 días |
| Clasificación | Combinar |
| Deficiencia | [C] El clic no aplica filtro. [C] Distinto de I16. |
| Mejora | Una definición; el clic filtra por ETA. |
| Prioridad | P2 |
| Esfuerzo | Bajo |
| Validación | — |

#### S12 · Atrasado para el cierre de puerto

| Campo | Contenido |
|---|---|
| Nombre | Atrasado para el cierre de puerto |
| Estado | Existente |
| Pantalla | Seguimiento › Embarques |
| Objetivo | Embarques que llegan tarde. |
| Fórmula | Embarques con peor riesgo ATRASO. |
| Fuente | `app/modulos/seguimiento/seguimiento.py:375` |
| Filtros | Igual que S08. |
| Período | Foto de hoy |
| Clasificación | Corregir |
| Deficiencia | [C] El texto de detalle dice «ETA después de la fecha en tienda», contrario al título (límite en puerto). |
| Mejora | Corregir el texto; unificar con I05. |
| Prioridad | P2 |
| Esfuerzo | Bajo |
| Validación | — |

#### S13 · Llegadas por semana (gráfica)

| Campo | Contenido |
|---|---|
| Nombre | Llegadas por semana (gráfica) |
| Estado | Existente |
| Pantalla | Seguimiento › Embarques |
| Objetivo | Carga de recepción próxima. |
| Fórmula | 8 semanas desde hoy: embarques no arribados con ETA en la semana. |
| Fuente | `app/modulos/seguimiento/seguimiento.py:362-367` |
| Filtros | Igual que S08. |
| Período | 8 semanas |
| Clasificación | Mantener |
| Deficiencia | [M] La primera etiqueta «Esta sem.» está fija en el código. |
| Mejora | — |
| Prioridad | P3 |
| Esfuerzo | Bajo |
| Validación | — |

#### S14 · Embarques por estado

| Campo | Contenido |
|---|---|
| Nombre | Embarques por estado |
| Estado | Existente |
| Pantalla | Seguimiento › Embarques |
| Objetivo | Distribución por estado. |
| Fórmula | Cuenta por estado (sin CANCELADO). |
| Fuente | `app/modulos/seguimiento/seguimiento.py:358-360` |
| Filtros | Igual que S08. |
| Período | Foto de hoy |
| Clasificación | Mantener |
| Deficiencia | — |
| Mejora | — |
| Prioridad | P3 |
| Esfuerzo | Bajo |
| Validación | — |

### Seguimiento — Facturación y listas de empaque

#### S15 · Facturas (importe por moneda)

| Campo | Contenido |
|---|---|
| Nombre | Facturas (importe por moneda) |
| Estado | Existente |
| Pantalla | Seguimiento › Documentos |
| Objetivo | Volumen facturado en curso. |
| Fórmula | Facturas no canceladas con filas; importe agrupado **por moneda** (correcto). |
| Fuente | `app/modulos/seguimiento/seguimiento.py:653-663`; GET /api/seguimiento/documentos |
| Filtros | Proveedor, sociedades, filtros de pantalla. |
| Período | Foto de hoy |
| Clasificación | Mantener |
| Deficiencia | [C] Es la única cifra de montos del sistema que separa monedas: referencia para corregir I01, I20, T04, T07. |
| Mejora | — |
| Prioridad | P3 |
| Esfuerzo | Bajo |
| Validación | — |

#### S16 · Facturas abiertas

| Campo | Contenido |
|---|---|
| Nombre | Facturas abiertas |
| Estado | Existente |
| Pantalla | Seguimiento › Documentos |
| Objetivo | Trabajo abierto. |
| Fórmula | Facturas BORRADOR/EN_CORRECCION. |
| Fuente | `app/modulos/seguimiento/seguimiento.py:655` |
| Filtros | Igual que S15. |
| Período | Foto de hoy |
| Clasificación | Corregir |
| Deficiencia | [C] El clic filtra solo BORRADOR (`SeguimientoDocumentos.vue`): la lista muestra menos que la cifra. |
| Mejora | Filtro con ambos estados. |
| Prioridad | P2 |
| Esfuerzo | Bajo |
| Validación | Cifra = filas tras el clic. |

#### S17 · Empaque

| Campo | Contenido |
|---|---|
| Nombre | Empaque |
| Estado | Existente |
| Pantalla | Seguimiento › Documentos |
| Objetivo | PL en proceso. |
| Fórmula | Filas EMPACANDO + POR_FINALIZAR_PL. |
| Fuente | `app/modulos/seguimiento/seguimiento.py:657` |
| Filtros | Igual que S15. |
| Período | Foto de hoy |
| Clasificación | Corregir |
| Deficiencia | [C] El clic filtra solo EMPACANDO. |
| Mejora | Filtro con ambas etapas. |
| Prioridad | P2 |
| Esfuerzo | Bajo |
| Validación | — |

#### S18 · Lista para embarcar

| Campo | Contenido |
|---|---|
| Nombre | Lista para embarcar |
| Estado | Existente |
| Pantalla | Seguimiento › Documentos |
| Objetivo | PL listas para contenedor. |
| Fórmula | Filas de PL en LISTO_EMBARQUE (PL y factura finalizadas). |
| Fuente | `app/modulos/seguimiento/seguimiento.py:658` |
| Filtros | Igual que S15. |
| Período | Foto de hoy |
| Clasificación | Corregir |
| Deficiencia | Ver I03 (otra definición con el mismo nombre). |
| Mejora | Ver I03. |
| Prioridad | P1 |
| Esfuerzo | Bajo |
| Validación | — |

#### S19 · Con datos pendientes

| Campo | Contenido |
|---|---|
| Nombre | Con datos pendientes |
| Estado | Existente |
| Pantalla | Seguimiento › Documentos |
| Objetivo | Documentos que no pueden finalizarse. |
| Fórmula | Filas con pendientes de PL o de factura. |
| Fuente | `app/modulos/seguimiento/seguimiento.py:659` |
| Filtros | Igual que S15. |
| Período | Foto de hoy |
| Clasificación | Mantener |
| Deficiencia | — |
| Mejora | — |
| Prioridad | P3 |
| Esfuerzo | Bajo |
| Validación | — |

#### S20 · Documentos por paso (barras)

| Campo | Contenido |
|---|---|
| Nombre | Documentos por paso (barras) |
| Estado | Existente |
| Pantalla | Seguimiento › Documentos |
| Objetivo | Embudo documental; filtra la tabla. |
| Fórmula | Cuenta de filas por etapa. |
| Fuente | `app/modulos/seguimiento/seguimiento.py:649-651` |
| Filtros | Igual que S15. |
| Período | Foto de hoy |
| Clasificación | Mantener |
| Deficiencia | — |
| Mejora | — |
| Prioridad | P3 |
| Esfuerzo | Bajo |
| Validación | Σ barras = filas. |

#### S21 · Carga empacada (PL, cajas, pallets, peso, volumen)

| Campo | Contenido |
|---|---|
| Nombre | Carga empacada (PL, cajas, pallets, peso, volumen) |
| Estado | Existente |
| Pantalla | Seguimiento › Documentos |
| Objetivo | Volumen físico en curso. |
| Fórmula | Σ de las filas filtradas. |
| Fuente | `app/modulos/seguimiento/seguimiento.py:660-661` |
| Filtros | Igual que S15. |
| Período | Foto de hoy |
| Clasificación | Mejorar |
| Deficiencia | [C] Por diseño ignora los filtros de columna de la tabla; no se indica en pantalla. |
| Mejora | Indicar «según los filtros de la pantalla, no los de la tabla». |
| Prioridad | P3 |
| Esfuerzo | Bajo |
| Validación | — |

### Seguimiento — Lead times

#### L01 · Liberación logística a tiempo (%)

| Campo | Contenido |
|---|---|
| Nombre | Liberación logística a tiempo (%) |
| Estado | Existente |
| Pantalla | Seguimiento › Lead times |
| Objetivo | Cumplimiento de liberación antes de la XF. |
| Fórmula | OCs **creadas** en el período con liberación ≤ meta ÷ OCs liberadas × 100, redondeado a entero. |
| Fuente | `app/modulos/transporte/leadtimes.py:436-445`; GET /api/seguimiento/leadtimes |
| Filtros | Período (12 meses), origen, región, proveedor; **no filtra estado de la OC**. |
| Período | Período |
| Clasificación | Corregir |
| Deficiencia | [C] Sin datos muestra «0» **en verde**: el valor usa `?? 0` y el tono `?? 100 >= 80` (`TableroLeadTimes.vue:124`); el componente `Kpi` convierte `null` en 0. [C] Umbral 80 % fijo. [E] Universo distinto de T16. |
| Mejora | «—» sin datos; umbral configurable; una definición con T16. |
| Prioridad | P1 |
| Esfuerzo | Bajo |
| Validación | Sin OCs liberadas muestra «—» sin tono. |

#### L02 · Liberación vencida

| Campo | Contenido |
|---|---|
| Nombre | Liberación vencida |
| Estado | Existente |
| Pantalla | Seguimiento › Lead times |
| Objetivo | OCs sin liberar con meta pasada. |
| Fórmula | OCs sin liberación logística con meta < hoy. |
| Fuente | `app/modulos/transporte/leadtimes.py:440` |
| Filtros | Igual que L01. |
| Período | Foto de hoy |
| Clasificación | Corregir |
| Deficiencia | [C] Incluye OCs canceladas o rechazadas (nunca se liberarán). |
| Mejora | OCs vigentes. |
| Prioridad | P1 |
| Esfuerzo | Bajo |
| Validación | OC cancelada no cuenta. |

#### L03 · Lead time promedio (días)

| Campo | Contenido |
|---|---|
| Nombre | Lead time promedio (días) |
| Estado | Existente |
| Pantalla | Seguimiento › Lead times |
| Objetivo | Tiempo de ciclo. |
| Fórmula | Promedio de Σ duraciones de OCs **creadas** en el período con todas las etapas. |
| Fuente | `app/modulos/transporte/leadtimes.py:441` |
| Filtros | Igual que L01. |
| Período | Período |
| Clasificación | Corregir |
| Deficiencia | [C] Sin datos muestra 0. [C] Distinto de T15 (por fecha de ingreso). |
| Mejora | «—» sin datos; unificar con T15. |
| Prioridad | P1 |
| Esfuerzo | Bajo |
| Validación | Igual a T15. |

#### L04 · Atrasado para el cierre de puerto (y en riesgo)

| Campo | Contenido |
|---|---|
| Nombre | Atrasado para el cierre de puerto (y en riesgo) |
| Estado | Existente |
| Pantalla | Seguimiento › Lead times |
| Objetivo | OCs que llegan tarde / con poca holgura. |
| Fórmula | OCs con riesgo ATRASO; detalle: JUSTO. |
| Fuente | `app/modulos/transporte/leadtimes.py:443-444` |
| Filtros | Igual que L01. |
| Período | Foto de hoy |
| Clasificación | Combinar |
| Deficiencia | Ver I05. |
| Mejora | Ver I05. |
| Prioridad | P1 |
| Esfuerzo | Bajo |
| Validación | Ver I05. |

#### L05 · OC creadas en el período

| Campo | Contenido |
|---|---|
| Nombre | OC creadas en el período |
| Estado | Existente |
| Pantalla | Seguimiento › Lead times |
| Objetivo | Contexto del análisis. |
| Fórmula | OCs con `fecha` en el período. |
| Fuente | `app/modulos/transporte/leadtimes.py:437` |
| Filtros | Igual que L01. |
| Período | Período |
| Clasificación | Corregir |
| Deficiencia | [E] Incluye OCs canceladas y en borrador (siguió en 14). |
| Mejora | OCs vigentes. |
| Prioridad | P1 |
| Esfuerzo | Bajo |
| Validación | — |

#### L06 · Tabla por origen (días por etapa, total, liberación vs XF, recogida vs XF, holgura)

| Campo | Contenido |
|---|---|
| Nombre | Tabla por origen (días por etapa, total, liberación vs XF, recogida vs XF, holgura) |
| Estado | Existente |
| Pantalla | Seguimiento › Lead times |
| Objetivo | Dónde se pierde el tiempo por origen. |
| Fórmula | Promedio por etapa de las OCs que completaron esa etapa; «Total» = promedio de OCs con **todas** las etapas; barra = suma de los promedios por etapa. |
| Fuente | `app/modulos/transporte/leadtimes.py:413-432`; `TableroLeadTimes.vue:353` |
| Filtros | Igual que L01. |
| Período | Período |
| Clasificación | Mejorar |
| Deficiencia | [C] La barra (suma de promedios de poblaciones distintas) y el «Total» pueden no coincidir. [C] Umbral 80 % fijo en «Liberación vs XF». |
| Mejora | Mostrar n por etapa y explicar la diferencia, o dibujar la barra con las OCs completas. |
| Prioridad | P2 |
| Esfuerzo | Bajo |
| Validación | — |

#### L07 · Hitos de cada OC (fecha, meta, estado)

| Campo | Contenido |
|---|---|
| Nombre | Hitos de cada OC (fecha, meta, estado) |
| Estado | Existente |
| Pantalla | Seguimiento › Lead times (detalle) |
| Objetivo | Qué hito de qué documento se atrasa. |
| Fórmula | Por hito: fecha real/estimada vs meta derivada del lead time efectivo. |
| Fuente | `app/modulos/transporte/leadtimes.py:288 analizar_oc` |
| Filtros | — |
| Período | Por OC |
| Clasificación | Mantener |
| Deficiencia | — |
| Mejora | — |
| Prioridad | P3 |
| Esfuerzo | Bajo |
| Validación | — |

### Cifras en pantallas operativas, comercial y reportes

#### O01 · % facturado de la OC (lista Órdenes)

| Campo | Contenido |
|---|---|
| Nombre | % facturado de la OC (lista Órdenes) |
| Estado | Existente |
| Pantalla | Órdenes de compra |
| Objetivo | Avance de facturación por OC. |
| Fórmula | Σ cantidad facturada × precio de la OC ÷ Σ cantidad × precio × 100 (facturas ≠ CANCELADA, incluye borradores; sin tope de 100). |
| Fuente | `app/modulos/compras/ordenes.py:84,244` |
| Filtros | Proveedor, sociedades. |
| Período | Foto de hoy |
| Clasificación | Corregir |
| Deficiencia | [C] Cuenta como facturado lo que está en borradores; difiere de S01/S07 (por cantidad). |
| Mejora | Nombrarlo «facturado o en borrador» o separar ambos; misma base que Seguimiento. |
| Prioridad | P2 |
| Esfuerzo | Bajo |
| Validación | — |

#### O02 · Por facturar por OC (por unidad)

| Campo | Contenido |
|---|---|
| Nombre | Por facturar por OC (por unidad) |
| Estado | Existente |
| Pantalla | Órdenes de compra |
| Objetivo | Saldo disponible. |
| Fórmula | Por unidad de medida: max(Σ cantidad − Σ facturado, 0). |
| Fuente | `app/modulos/compras/ordenes.py:203-221` |
| Filtros | Proveedor, sociedades. |
| Período | Foto de hoy |
| Clasificación | Mantener |
| Deficiencia | [C] Agrega por unidad: una línea sobrefacturada oculta el saldo de otra de la misma unidad. [C] El filtro «con saldo» (`:130`) suma entre unidades. |
| Mejora | Calcular el saldo por línea y luego agregar. |
| Prioridad | P3 |
| Esfuerzo | Bajo |
| Validación | — |

#### O03 · Total de la selección a facturar

| Campo | Contenido |
|---|---|
| Nombre | Total de la selección a facturar |
| Estado | Existente |
| Pantalla | Órdenes de compra (carrito) |
| Objetivo | Monto a facturar. |
| Fórmula | Σ cantidad × precio de lo elegido, con la moneda del primer elemento. |
| Fuente | `src/modulos/compras/vistas/OrdenesView.vue:298-307` |
| Filtros | — |
| Período | — |
| Clasificación | Mejorar |
| Deficiencia | [C] Con monedas mezcladas suma ambas y muestra un solo código (hay un aviso aparte). |
| Mejora | Total por moneda. |
| Prioridad | P2 |
| Esfuerzo | Bajo |
| Validación | — |

#### O04 · Factura: % en listas de empaque y % en cajas

| Campo | Contenido |
|---|---|
| Nombre | Factura: % en listas de empaque y % en cajas |
| Estado | Existente |
| Pantalla | Factura y panel de resumen |
| Objetivo | Avance de empaque. |
| Fórmula | Cantidades sumadas entre unidades; `pct()` con tope de 100. |
| Fuente | `src/modulos/facturacion/vistas/FacturaView.vue:116-142`, `componentes/ResumenFactura.vue:44`, `src/nucleo/utils.js:84` |
| Filtros | — |
| Período | Por documento |
| Clasificación | Corregir |
| Deficiencia | [C] Suma pares + unidades; el tope de 100 % oculta el sobreempaque; «sin asignar» se muestra sin unidad. |
| Mejora | Por unidad de medida; sin tope (mostrar «excedido»). |
| Prioridad | P2 |
| Esfuerzo | Bajo |
| Validación | — |

#### O05 · PL: avance de empaque

| Campo | Contenido |
|---|---|
| Nombre | PL: avance de empaque |
| Estado | Existente |
| Pantalla | Lista de empaque |
| Objetivo | Cuánto está en cajas. |
| Fórmula | `pct(Σ en cajas, Σ cantidad)` entre unidades, tope 100. |
| Fuente | `src/modulos/empaque/vistas/PackingListView.vue:93` |
| Filtros | — |
| Período | Por documento |
| Clasificación | Corregir |
| Deficiencia | [C] Igual que O04. |
| Mejora | Igual que O04. |
| Prioridad | P2 |
| Esfuerzo | Bajo |
| Validación | — |

#### O06 · Embarques: conteo por estado

| Campo | Contenido |
|---|---|
| Nombre | Embarques: conteo por estado |
| Estado | Existente |
| Pantalla | Embarques |
| Objetivo | Distribución. |
| Fórmula | Cuenta en el navegador sobre una segunda llamada sin filtros a /embarques. |
| Fuente | `src/modulos/transporte/vistas/EmbarquesView.vue:33-56` |
| Filtros | Alcance de transporte. |
| Período | Foto de hoy |
| Clasificación | Mejorar |
| Deficiencia | [C] Ignora la búsqueda y descarga dos veces la lista completa (que es costosa). |
| Mejora | Conteos desde el servidor con los mismos filtros. |
| Prioridad | P3 |
| Esfuerzo | Bajo |
| Validación | — |

#### O07 · Unidad de carga: % de volumen y de peso

| Campo | Contenido |
|---|---|
| Nombre | Unidad de carga: % de volumen y de peso |
| Estado | Existente |
| Pantalla | Embarque |
| Objetivo | No exceder la capacidad. |
| Fórmula | cbm × 100 / capacidad; kg × 100 / capacidad kg. |
| Fuente | `app/modulos/transporte/transporte.py:124-192`; `EmbarqueView.vue:270-276` |
| Filtros | — |
| Período | Por unidad |
| Clasificación | Mejorar |
| Deficiencia | [C] La proyección al asignar calcula % de peso pero solo avisa por volumen. |
| Mejora | Avisar por el mayor de los dos. |
| Prioridad | P2 |
| Esfuerzo | Bajo |
| Validación | — |

#### O08 · Resumen del embarque (facturas, PL, cajas, kg, m³)

| Campo | Contenido |
|---|---|
| Nombre | Resumen del embarque (facturas, PL, cajas, kg, m³) |
| Estado | Existente |
| Pantalla | Embarque |
| Objetivo | Contenido del embarque. |
| Fórmula | Σ por unidad de carga. |
| Fuente | `src/modulos/transporte/componentes/ResumenEmbarque.vue:80-87` |
| Filtros | — |
| Período | Por embarque |
| Clasificación | Corregir |
| Deficiencia | [C] Una factura repartida en dos unidades se cuenta dos veces. [C] kg con 0 decimales aquí y 1 en otra vista. |
| Mejora | Contar facturas distintas; formato único. |
| Prioridad | P2 |
| Esfuerzo | Bajo |
| Validación | — |

#### O09 · Productos: conteos por vista

| Campo | Contenido |
|---|---|
| Nombre | Productos: conteos por vista |
| Estado | Existente |
| Pantalla | Productos |
| Objetivo | Colas de clasificación. |
| Fórmula | Cuentas por estado (y «bloquean», «baja confianza»). |
| Fuente | `app/modulos/productos/productos.py:452-501` |
| Filtros | Proveedor y filtros de la lista (salvo «bloquean»). |
| Período | Foto de hoy |
| Clasificación | Mantener |
| Deficiencia | [C] «Bloquean» ignora los filtros de la lista. [C] Los segmentos ocultan los conteos en 0. |
| Mejora | — |
| Prioridad | P3 |
| Esfuerzo | Bajo |
| Validación | — |

#### O10 · Familias: % aprobados como se sugirió, baja confianza

| Campo | Contenido |
|---|---|
| Nombre | Familias: % aprobados como se sugirió, baja confianza |
| Estado | Existente |
| Pantalla | Familias de producto |
| Objetivo | Calidad del motor de sugerencias. |
| Fórmula | aprobado ÷ (aprobado + corregido) × 100. |
| Fuente | `app/modulos/clasificacion/familias.py:30-86` |
| Filtros | Sin alcance de proveedor (permiso interno). |
| Período | Acumulado |
| Clasificación | Mejorar |
| Deficiencia | [M] No muestra el denominador. |
| Mejora | Mostrar «n de m». |
| Prioridad | P3 |
| Esfuerzo | Bajo |
| Validación | — |

#### O11 · Estado de cobro de un documento (pendiente, parcial, vencido, pagado)

| Campo | Contenido |
|---|---|
| Nombre | Estado de cobro de un documento (pendiente, parcial, vencido, pagado) |
| Estado | Existente |
| Pantalla | Facturación › Documentos |
| Objetivo | Qué documento cobrar. |
| Fórmula | Saldo = total − aplicado; VENCIDO si saldo > 0 y `fecha_vencimiento < hoy`. |
| Fuente | `app/modulos/comercial/documentos.py:125-143` |
| Filtros | Sociedades. |
| Período | Foto de hoy |
| Clasificación | Corregir |
| Deficiencia | [C] `fecha_vencimiento` es la de la **última** cuota (`documentos.py:492`): una cuota anterior vencida no marca el documento. |
| Mejora | Vencimiento por cuota (asignación FIFO de los pagos a cuotas). |
| Prioridad | P1 |
| Esfuerzo | Medio |
| Validación | Documento con cuota 1 vencida y cuota 2 futura aparece VENCIDO. |

#### O12 · Estado de cuenta de un tercero (saldo por moneda)

| Campo | Contenido |
|---|---|
| Nombre | Estado de cuenta de un tercero (saldo por moneda) |
| Estado | Existente |
| Pantalla | Facturación › Terceros |
| Objetivo | Cuánto debe o se le debe a un tercero. |
| Fórmula | Σ saldo × signo de documentos emitidos − pagos sin aplicar, por moneda. |
| Fuente | `app/modulos/comercial/documentos.py:633-656` |
| Filtros | Sociedades **solo para los documentos**. |
| Período | Foto de hoy |
| Clasificación | Corregir |
| Deficiencia | [C] Los pagos se consultan sin filtro de sociedad: un usuario limitado ve y resta pagos de sociedades ajenas. [C] Además `pagos.py:120` permite aplicar un pago a un documento de otra sociedad (solo el frontend lo impide). |
| Mejora | Filtrar pagos por sociedad; validar sociedad al aplicar. |
| Prioridad | P0 |
| Esfuerzo | Bajo |
| Validación | Usuario limitado a la sociedad A no ve pagos de B; aplicar un pago de A a un documento de B responde 422. |

#### O13 · Reportes: medidas (suma, promedio, mín., máx., conteo)

| Campo | Contenido |
|---|---|
| Nombre | Reportes: medidas (suma, promedio, mín., máx., conteo) |
| Estado | Existente |
| Pantalla | Reportes (analíticos) |
| Objetivo | Análisis libre. |
| Fórmula | SUM/AVG/… agrupado por hasta 3 campos. |
| Fuente | `app/modulos/reportes/generador.py:39,213`, `fuentes.py:73-184` |
| Filtros | Permiso por fuente, alcance de proveedor/sociedad/transporte, datos ocultos. |
| Período | Según filtros |
| Clasificación | Corregir |
| Deficiencia | [C] Sumar `valor`/`importe` agrupando por proveedor suma monedas distintas; la fuente `lineas_oc` no tiene campo moneda; sumar cantidades mezcla unidades; `pendiente` puede ser negativo. Los montos se muestran sin código de moneda (`ReportesView.vue:169`). [C] No hay fuentes comerciales (cobros/pagos). |
| Mejora | Exigir la moneda (y la unidad) como agrupación al sumar importes/cantidades; agregar `moneda` a `lineas_oc`; piso 0 en pendiente; mostrar el código. |
| Prioridad | P0 |
| Esfuerzo | Medio |
| Validación | Un reporte que suma importes sin agrupar por moneda es rechazado o se agrupa solo. |

---

## Anexo B. Cómo se midió (para repetirlo)

1. Copiar la base de demostración a un archivo aparte y levantar el servidor contra la copia
   (`DATABASE_URL=sqlite:////ruta/copia.db SEED_DEMO=1 uvicorn app.main:app --port 8767`).
2. Iniciar sesión como `interno@demo.com` y pedir: `/api/dashboard?desde=2026-01-01&hasta=2026-12-31`,
   `/api/seguimiento/ordenes`, `/api/seguimiento/leadtimes`, `/api/tableros/{resumen,compras,facturacion,logistica}?dias=365`.
3. Aplicar en la copia: OC `4400003851` → `CANCELADA`; `4400003904` → `BORRADOR`; `4400003850` → moneda `EUR`; factura
   `TNF-2026-0915` → `EN_CORRECCION`; duplicar 9 veces el embarque EN_TRANSITO. Repetir las consultas y comparar.
4. Consultas SQL por endpoint: un contador en el evento `before_cursor_execute` del motor (como `tests/test_rendimiento.py`).
