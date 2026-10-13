# Flujos de negocio

Cómo debe fluir cada caso de uso, independientemente de la pantalla. El
servidor aplica estas transiciones con una sola máquina de estados
(`app/core/estados.py`); la interfaz solo ofrece las acciones que el
servidor permite (`puede` de cada documento).

## 1. Orden de compra

Una OC tiene **dos dimensiones** que no se mezclan:

- **Estado del documento** (`estado`, guardado): quién puede hacer qué con la OC.
- **Avance logístico** (`avance`, calculado de las cantidades): qué pasó con la mercancía.

Una OC puede estar *Aprobada* mientras su mercancía está *En tránsito
parcial*.

### Estado del documento

```
BORRADOR ──enviar──▶ EN_APROBACION ──aprobar (último paso)──▶ APROBADA ──cerrar──▶ CERRADA
   ▲  │                   │                                     │  ▲                  │
   │  └──enviar (sin regla de aprobación)───────────────────────┘  └──reabrir─────────┘
   │                      └──rechazar──▶ RECHAZADA ──editar──┐
   └─────────────────────────────────────────────────────────┘
BORRADOR | EN_APROBACION | RECHAZADA | APROBADA ──cancelar──▶ CANCELADA
```

| Acción | Desde | Quién | Condiciones |
|---|---|---|---|
| Crear / editar | BORRADOR, RECHAZADA | `oc.editar` | Guarda aunque falten datos (borrador). |
| Enviar | BORRADOR, RECHAZADA | `oc.editar` | Todos los pasos completos. Si alguna regla de aprobación aplica, pasa a EN_APROBACION; si no, a APROBADA. |
| Aprobar | EN_APROBACION | `oc.aprobar` y el rol del paso | En orden de pasos; quien la creó no la aprueba si la regla `APROBACION_CUATRO_OJOS` está activa. |
| Rechazar | EN_APROBACION | `oc.aprobar` y el rol del paso | Motivo obligatorio. |
| Cancelar | todos menos CERRADA y CANCELADA | `oc.cancelar` | Motivo obligatorio; sin facturas activas. |
| Cerrar | APROBADA | `oc.cancelar` | Motivo obligatorio; lo pendiente deja de estar disponible para facturar. |
| Reabrir | CERRADA | `oc.aprobar` | Motivo obligatorio. |

- **OCs importadas del ERP.** Entran como APROBADA porque el ERP ya las
  aprobó. Si la empresa activa `APROBAR_OC_IMPORTADAS`, entran como
  EN_APROBACION.
- **Liberaciones del ERP.** Las liberaciones comercial y logística, si la
  empresa las usa, siguen siendo un requisito adicional para facturar.
- **Disponible para facturar** = `estado == APROBADA` y liberada.

**Reglas de aprobación.** Se configuran en Configuración → Empresa →
Aprobaciones. Cada regla tiene:
- nombre;
- monto mínimo y moneda;
- sociedad (opcional);
- rol aprobador.

Todas las reglas que aplican a una OC forman sus pasos, ordenados por monto.
Cada decisión queda en la bitácora: quién, cuándo, paso y comentario.

### Avance logístico (calculado)

| Avance | Condición |
|---|---|
| SIN_FACTURAR | Nada facturado. |
| FACTURADA_PARCIAL / FACTURADA | Parte o todo en facturas activas. |
| EMBARCADA_PARCIAL | Parte en unidades de carga que ya salieron. |
| EN_TRANSITO | Todo lo facturado salió y nada se ha recibido. |
| RECIBIDA_PARCIAL / RECIBIDA | Según las cantidades recibidas en bodega. |

### Creación: asistente por pasos

Cada paso valida en el acto, se guarda como borrador y permite volver sin
perder datos.

1. **Datos generales:** proveedor, número, sociedad, fecha de la OC.
2. **Artículos y cantidades:** buscador de artículos del proveedor, cantidad,
   empaque.
3. **Condiciones económicas:** moneda, incoterm, condición de pago, precio por
   línea y total.
4. **Logística y fechas:** centro destino y de recepción, puerto, país de
   origen, fecha de despacho (XF), fecha en tienda. Los datos de aduana se
   piden aquí, no antes.
5. **Documentación y extras:** campos propios de la OC y notas.
6. **Revisión:** resumen y «Enviar».

En pantalla (`/ordenes/nueva` y `/ordenes/{id}/editar`, componente
`Asistente.vue`): «Siguiente» exige el paso completo según el servidor
(`POST /ordenes/validar`); el primer «Siguiente» crea el borrador y desde ahí
se guarda solo, unos segundos después de cada cambio y al cambiar de paso
(`PATCH /ordenes/{id}`). «Guardar borrador» guarda aunque falten datos. Los
pasos se pueden recorrer en cualquier orden una vez creado el borrador; al
volver a abrirlo sigue en el primer paso incompleto. En el celular el
asistente ocupa toda la pantalla.

La vista de la OC (`/ordenes/{id}`) es de solo lectura y distinta del
asistente: estado y avance, lo acordado agrupado por tema, líneas, avance
logístico, aprobaciones e historial. Los botones de cada acción los decide el
servidor (`puede`): aprobar o rechazar solo aparecen a quien aprueba el paso
pendiente (su rol y, con cuatro ojos, si no creó ni envió la OC). Quien
aprueba ve en «Órdenes de compra» la bandeja de las OCs que esperan su
aprobación. Las reglas de aprobación y los datos obligatorios se configuran en
Configuración → Empresa.

## 2. Factura y lista de empaque

```
BORRADOR ──finalizar──▶ FINALIZADA ──reabrir──▶ EN_CORRECCION ──finalizar──▶ FINALIZADA
cualquiera (sin unidad confirmada) ──cancelar──▶ CANCELADA
```

- **Finalizar** exige que no haya pendientes. La empresa decide si el
  proveedor puede finalizar (`PROVEEDOR_PUEDE_FINALIZAR`) y si se exigen los
  datos de aduana (`REQUERIR_DATOS_ADUANA`).
- **Reabrir** pide motivo y no se permite si la unidad de carga ya salió.
  Saca las listas de su unidad de carga y la interfaz lo dice.
- La lista de empaque sigue el mismo ciclo, con BORRADOR, FINALIZADO,
  EN_CORRECCION y CANCELADO.

## 3. Embarque y recepción

```
PLANIFICADO ──salida──▶ EN_TRANSITO ──arribo──▶ ARRIBADO ──entrega──▶ ENTREGADO ──recepción──▶ RECIBIDO
PLANIFICADO ──cancelar──▶ CANCELADO
```

**Hitos.**
- Los hitos se configuran en Datos maestros → Listas → Eventos del embarque.
- Cada hito declara en qué estados se permite.
- La salida exige BL o AWB, transportista, puertos, centro de arribo,
  contenedores y sellos.

**Recepción.**
- Se registra por línea de la lista de empaque (recibido y dañado), y solo
  cuando el embarque ya arribó o se entregó.
- Si se recibieron todas las listas del embarque, el embarque pasa a RECIBIDO.
- El hito «Recepción» sin detalle registra todo como recibido sin novedad.
- Una diferencia (faltante o daño) crea una alerta para el equipo interno.

## 4. Importación de OCs desde el ERP

1. **Archivo:** Excel o CSV, con un perfil de mapeo opcional (columnas,
   fila de encabezado, formato de fecha, valores por defecto).
2. **Vista previa:** OCs nuevas, cambios campo por campo, conflictos y
   errores por fila.
3. **Aplicar.**
   - Los conflictos no se aplican: quedan como alertas.
   - Cada OC creada o cambiada queda en su historial con sus cambios.
   - Una OC liberada que cambia pasa al estado de liberación «con cambios».
4. **Validación contra los maestros:** proveedor, sociedad, centro, moneda,
   incoterm, unidad y artículo deben existir y estar activos.

## 5. Quién ve qué

- **Pantalla:** el permiso del rol decide qué pantallas aparecen. El servidor
  exige el mismo permiso.
- **Datos:** el alcance del usuario limita los registros (proveedores,
  sociedades, transportistas).
- **Campos:** los datos visibles del rol quitan columnas de las respuestas.
- **Organización:** cada usuario pertenece a una organización y solo ve sus
  datos; el filtro lo aplica la capa de datos, no cada pantalla.
