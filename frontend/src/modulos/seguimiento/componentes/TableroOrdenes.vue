<script setup>
import { t, tx } from '@/i18n/index.js'
import FechaTienda from '@/componentes/FechaTienda.vue'
import { computed, reactive, ref, watch } from 'vue'
import { api } from '@/nucleo/api'
import { esInterno, sesion, ve } from '@/stores/sesion'
import { errorApi } from '@/stores/ui'
import { cantTxt, diasTxt, fmtFecha, fmtNum, porUnidadTxt, textoVariante, TIEMPO } from '@/nucleo/utils'
import ExplosionPrepack from '@/componentes/ExplosionPrepack.vue'
import Icono from '@/componentes/Icono.vue'
import Kpi from '@/componentes/Kpi.vue'
import TablaDatos from '@/componentes/TablaDatos.vue'
import BarrasEtapas from '@/componentes/BarrasEtapas.vue'

// Tablero de órdenes de compra: liberaciones (comercial y logística), cuánto
// falta por facturar, qué va en contenedor, en camino y recibido. Cada OC se
// abre en el detalle por SKU: en qué etapa está, en qué documento y unidad de
// carga va y si llega a tiempo a tienda. La tabla filtra cada columna por sus
// valores en el servidor (/seguimiento/ordenes/valores).
const props = defineProps({ filtros: { type: Object, required: true } })
const emit = defineEmits(['opciones', 'filtrar'])
const datos = ref({ items: [], total: 0, kpis: {}, estados: [] })
const cargando = ref(true)
const tablaOC = ref(null)
const TONO = {
  SIN_COMERCIAL: 'aviso', SIN_LOGISTICA: 'aviso', POR_FACTURAR: 'neutro', PARCIAL: 'info', FACTURADA: 'acento',
  EN_CAMINO: 'info', RECIBIDA: 'ok',
}
const RIESGOS = TIEMPO
// Tramos de la barra de avance: del pedido a lo recibido (un solo tono, de claro a oscuro)
const TRAMOS = [
  ['por_facturar', t('To invoice'), 'var(--tramo-1)'], ['facturado', t('Invoiced'), 'var(--tramo-2)'],
  ['en_contenedor', t('In load unit'), 'var(--tramo-3)'], ['en_camino', t('On the way'), 'var(--tramo-4)'],
  ['recibido', t('Received'), 'var(--tramo-5)'],
]
const ETAPAS = {
  PEND_LIBERACION: [t('Pending release'), 'aviso'], POR_FACTURAR: [t('To invoice'), 'neutro'],
  FACTURADO: [t('Invoiced, no PL'), 'info'], EN_PL: [t('In packing list'), 'acento'], CONTENEDOR: [t('In load unit'), 'acento'],
  EN_TRANSITO: [t('In transit'), 'info'], ARRIBADO: [t('Arrived'), 'info'], ENTREGADO: [t('Delivered'), 'ok'], RECIBIDO: [t('Received'), 'ok'],
}
const nombreEstado = computed(() => Object.fromEntries(datos.value.estados.map((e) => [e.clave, e.nombre])))
// Columnas: lo esencial a la vista; el resto en «Columnas» (y sin los datos que el rol no ve)
const columnas = computed(() => [
  { clave: 'oc', texto: t('Purchase order'), fija: true, prioridad: 1 },
  { clave: 'proveedor', texto: t('Supplier'), prioridad: 2, inicial: false },
  { clave: 'centro', texto: t('Company · plant'), grupo: 'codigos_internos', inicial: false, prioridad: 3 },
  { clave: 'liberaciones', texto: t('Releases'), grupo: 'liberaciones', inicial: false, ordenable: false, prioridad: 3 },
  { clave: 'estado', texto: t('Status'), prioridad: 1, opciones: datos.value.estados.map((e) => [e.clave, e.nombre]) },
  { clave: 'avance', texto: t('Progress'), prioridad: 2, textoValor: (v) => `${v}%` },
  { clave: 'por_facturar', texto: t('To invoice'), num: true, prioridad: 2 },
  { clave: 'fecha_xf', texto: 'XF', prioridad: 2, textoValor: (v) => fmtFecha(v) },
  { clave: 'fecha_tienda', texto: t('In store'), grupo: 'fechas_internas', inicial: false, prioridad: 3, textoValor: (v) => fmtFecha(v) },
  { clave: 'tienda_estimada', texto: t('Est. in store'), grupo: 'fechas_internas', prioridad: 3, textoValor: (v) => fmtFecha(v) },
  { clave: 'holgura', texto: t('Vs. port deadline'), grupo: 'fechas_internas', prioridad: 3, opciones: Object.entries(RIESGOS).map(([k, [txt]]) => [k, txt]) },
  { clave: 'embarques', texto: t('Shipments'), ordenable: false, prioridad: 3 },
])
const columnasLineas = computed(() => [
  { clave: 'posicion', texto: t('Line'), fija: true, prioridad: 1 },
  { clave: 'sku', texto: 'SKU', prioridad: 1 },
  { clave: 'estilo', texto: t('Brand · style · color'), prioridad: 2 },
  { clave: 'variante', texto: t('Variant'), valor: (x) => textoVariante(x), prioridad: 1 },
  { clave: 'almacen', texto: t('Warehouse'), grupo: 'codigos_internos', prioridad: 3 },
  { clave: 'cantidad', texto: t('Quantity'), num: true, prioridad: 2 },
  { clave: 'etapa', texto: t('Stage'), prioridad: 1, opciones: Object.entries(ETAPAS).map(([k, [txt]]) => [k, txt]) },
  { clave: 'factura', texto: t('Invoice / PL'), prioridad: 2 },
  { clave: 'embarque', texto: t('Shipment · unit'), prioridad: 3 },
  { clave: 'arribo', texto: t('Arrival'), prioridad: 3, valor: (l) => l.arribo_real || l.eta, textoValor: (v) => fmtFecha(v) },
  { clave: 'riesgo', texto: t('Vs. port deadline'), grupo: 'fechas_internas', prioridad: 3, opciones: Object.entries(RIESGOS).map(([k, [txt]]) => [k, txt]) },
])
// La gráfica por estado queda plegada: los estados ya están como pastillas
const detalles = reactive({})
const explosion = ref(null)
async function abrirDetalle(o) {
  if (detalles[o.oc_id]) return
  try {
    const r = await api.get('/seguimiento', { ...props.filtros, oc_id: o.oc_id, orden: 'etapa:asc', size: 200, proveedor_id: sesion.proveedorId || undefined })
    detalles[o.oc_id] = r.items.map((l, i) => ({ ...l, _i: i }))
  } catch (e) {
    errorApi(e)
  }
}

const base = () => ({ ...props.filtros, proveedor_id: sesion.proveedorId || undefined })
let ultima = null
async function cargar(c = ultima) {
  if (!c) return
  ultima = c
  cargando.value = true
  try {
    datos.value = await api.get('/seguimiento/ordenes', { ...base(), orden: c.orden || 'fecha_xf:asc', page: c.page, size: c.size,
      f: Object.keys(c.filtros).length ? JSON.stringify(c.filtros) : undefined })
    emit('opciones', datos.value.opciones)
  } catch (e) {
    errorApi(e)
  } finally {
    cargando.value = false
  }
}
const valores = (columna, buscar, otros) => api.get('/seguimiento/ordenes/valores', { ...base(), columna, buscar, f: JSON.stringify(otros) })
watch(() => [props.filtros, sesion.proveedorId], () => {
  for (const k of Object.keys(detalles)) delete detalles[k]
  if (tablaOC.value && tablaOC.value.pagina !== 1) tablaOC.value.pagina = 1
  else cargar()
}, { deep: true })
</script>

<template>
  <section class="kpis mb-4">
    <Kpi :titulo="t('Purchase orders')" :valor="datos.kpis.ocs" icono="ordenes"
         :detalle="datos.kpis.avance == null ? t('approved or closed') : t('{0}% invoiced on average (by value)', [fmtNum(datos.kpis.avance, 1)])" @abrir="emit('filtrar', {})" />
    <Kpi :titulo="t('Not released')" :valor="datos.kpis.sin_liberar" icono="candado" :tono="datos.kpis.sin_liberar ? 'alerta' : 'exito'"
         :detalle="t('cannot be invoiced yet')" @abrir="emit('filtrar', { estado: 'SIN_COMERCIAL,SIN_LOGISTICA' })" />
    <Kpi :titulo="t('XF overdue, not invoiced')" :valor="datos.kpis.xf_vencida" icono="reloj" :tono="datos.kpis.xf_vencida ? 'alerta' : 'exito'"
         :detalle="t('the XF date has passed')" @abrir="emit('filtrar', { xf_vencida: '1' })" />
    <Kpi v-if="ve('fechas_internas')" :titulo="t('Late for the port deadline')" :valor="datos.kpis.atraso" icono="alerta" :tono="datos.kpis.atraso ? 'alerta' : 'exito'"
         :detalle="t('not yet received · port arrival after the port deadline')" @abrir="emit('filtrar', { riesgo: 'ATRASO' })" />
  </section>

  <section class="panel mb-4">
    <div class="panel-cabeza"><h2>{{ t('POs by status') }}</h2></div>
    <BarrasEtapas :etapas="datos.estados" :activa="filtros.estado" :etiqueta="t('Purchase orders by status')" @elegir="(c) => emit('filtrar', { estado: c })" />
  </section>

  <TablaDatos ref="tablaOC" tabla="seguimiento_ordenes" modo="servidor" :columnas="columnas" :filas="datos.items" :total="datos.total" :cargando="cargando"
              clave-fila="oc_id" :valores="valores" expandible :etiqueta="t('Purchase orders')" @consulta="cargar" @expandir="abrirDetalle">
    <template #celda-oc="{ fila: o }">
      <router-link :to="{ path: '/ordenes', query: { q: o.oc, solo_disponible: '0' } }" class="enlace-doc" @click.stop><strong class="codigo">{{ tx(o.oc) }}</strong></router-link>
      <span class="sub">{{ tx(o.proveedor) }}<template v-if="o.marcas.length"> · {{ tx(o.marcas.join(', ')) }}</template></span>
    </template>
    <template #celda-centro="{ fila: o }"><span class="codigo">{{ tx(o.sociedad) }} · {{ tx(o.centro) }}</span><span class="sub">{{ t('destination {0}', [o.centro_destino || '—']) }}</span></template>
    <template #celda-liberaciones="{ fila: o }">
      <span class="insignias columna mt-0">
        <span class="etiqueta" :class="o.comercial_ok ? 'ok' : 'aviso'" :title="o.liberacion_comercial">{{ tx(o.comercial_txt) }}</span>
        <span class="etiqueta" :class="o.logistica_ok ? 'ok' : 'aviso'" :title="o.liberacion_logistica">{{ tx(o.liberacion_txt) }}</span>
      </span>
    </template>
    <template #celda-estado="{ fila: o }"><span class="etiqueta" :class="TONO[o.estado]" style="margin-inline-start: 0; white-space: normal">{{ tx(nombreEstado[o.estado]) }}</span></template>
    <template #celda-avance="{ fila: o }">
      <div class="avance-oc">
        <!-- Tramos por valor (o por cantidad si toda la OC usa una sola unidad); nunca suma pares con unidades -->
        <div class="apilada" role="img" :aria-label="tx(TRAMOS.map(([k, txt]) => `${txt}: ${fmtNum(o.tramos?.[k] || 0, 1)}%`).join(', '))">
          <span v-for="[k, txt, c] in TRAMOS.filter(([k]) => o.tramos?.[k])" :key="k"
                :style="{ width: `${o.tramos[k]}%`, background: c }" :title="`${tx(txt)}: ${fmtNum(o.tramos[k], 1)}%`"></span>
        </div>
        <span class="sub">{{ tx(o.avance == null ? porUnidadTxt(o.por_unidad) : t('{0}% invoiced · {1}', [fmtNum(o.avance, 0), porUnidadTxt(o.por_unidad)])) }}</span>
      </div>
    </template>
    <template #celda-por_facturar="{ fila: o }">{{ tx(porUnidadTxt(o.por_unidad, 'por_facturar')) }}</template>
    <template #celda-fecha_xf="{ fila: o }">{{ fmtFecha(o.fecha_xf) }}<span v-if="o.xf_vencida" class="sub texto-error">{{ t('overdue') }}</span></template>
    <template #celda-fecha_tienda="{ fila: o }">{{ fmtFecha(o.fecha_tienda) }}<span class="sub">{{ diasTxt(o.dias_tienda) }}</span></template>
    <template #celda-tienda_estimada="{ fila: o }"><FechaTienda :fecha="o.tienda_estimada" :dias="o.dias_vs_tienda" /></template>
    <template #celda-holgura="{ fila: o }">
      <span v-if="o.riesgo" class="etiqueta ms-0" :class="RIESGOS[o.riesgo][1]">{{ tx(RIESGOS[o.riesgo][0]) }}</span>
      <span v-if="o.holgura != null" class="sub">{{ tx(o.holgura < 0 ? t('{0} d late', [-o.holgura]) : t('{0} d margin', [o.holgura])) }}</span>
    </template>
    <template #celda-embarques="{ fila: o }"><span class="codigo">{{ tx(o.embarques.join(', ') || '—') }}</span></template>
    <template #detalle="{ fila: o }">
      <p v-if="!detalles[o.oc_id]" class="ayuda">{{ t('Loading…') }}</p>
      <TablaDatos v-else tabla="seguimiento_ordenes_lineas" :columnas="columnasLineas" :filas="detalles[o.oc_id]" clave-fila="_i" :vistas-guardadas="false"
                  :etiqueta="t('See the SKU detail of {0}', [o.oc])">
        <template #celda-posicion="{ fila: l }"><span class="codigo">{{ tx(l.posicion) }}</span></template>
        <template #celda-sku="{ fila: l }"><span class="codigo">{{ tx(l.sku) }}</span></template>
        <template #celda-estilo="{ fila: l }">{{ tx(l.marca) }} {{ tx(l.estilo) }}<span class="sub">{{ tx(l.grupo) }}</span></template>
        <template #celda-variante="{ fila: l }">
          <b>{{ tx(textoVariante(l) || '—') }}</b>
          <button v-if="l.tipo_empaque === 'PREPACK'" type="button" class="etiqueta acento btn-explosion" :title="t('See the pack breakdown')"
                  @click="explosion = { sku: l.sku, cajas: l.cantidad }">{{ t('Pack') }} <Icono nombre="lupa" :tam="12" /></button>
        </template>
        <template #celda-almacen="{ fila: l }">{{ tx(l.almacen || '—') }}</template>
        <template #celda-cantidad="{ fila: l }">{{ cantTxt(l.cantidad, l.unidad) }}</template>
        <template #celda-etapa="{ fila: l }"><span class="etiqueta ms-0" :class="ETAPAS[l.etapa]?.[1]">{{ tx(ETAPAS[l.etapa]?.[0] || l.etapa) }}</span></template>
        <template #celda-factura="{ fila: l }">
          <router-link v-if="l.factura_id" :to="`/facturas/${l.factura_id}`" class="enlace codigo">{{ tx(l.factura) }}</router-link>
          <span v-else class="ayuda">—</span>
          <router-link v-if="l.pl_id" :to="`/packing-lists/${l.pl_id}`" class="sub enlace">{{ t('PL {0}', [l.pl]) }}</router-link>
        </template>
        <template #celda-embarque="{ fila: l }">
          <template v-if="l.embarque_id">
            <router-link v-if="esInterno()" :to="`/transporte/embarques/${l.embarque_id}`" class="enlace codigo">{{ tx(l.embarque) }}</router-link>
            <span v-else class="codigo">{{ tx(l.embarque) }}</span>
            <span class="sub codigo">{{ tx(l.contenedor) }}<template v-if="l.documento"> · {{ tx(l.documento) }}</template></span>
          </template>
          <span v-else class="ayuda">—</span>
        </template>
        <template #celda-arribo="{ fila: l }">{{ fmtFecha(l.arribo_real || l.eta) }}<span v-if="l.arribo_real" class="sub">{{ t('actual') }}</span></template>
        <template #celda-riesgo="{ fila: l }">
          <span v-if="l.riesgo" class="etiqueta ms-0" :class="RIESGOS[l.riesgo][1]">{{ tx(l.holgura < 0 ? t('{0} d late', [-l.holgura]) : `${l.holgura} d`) }}</span>
          <span v-else class="ayuda">—</span>
        </template>
        <template #vacio>{{ t('No lines match these filters.') }}</template>
      </TablaDatos>
    </template>
    <template #vacio>{{ t('No purchase orders match these filters.') }}</template>
  </TablaDatos>
  <div class="leyenda-etapas">
    <span v-for="[k, txt, c] in TRAMOS" :key="k"><i class="punto" :style="{ background: c }"></i>{{ tx(txt) }}</span>
  </div>
  <ExplosionPrepack v-if="explosion" :sku="explosion.sku" :cajas="explosion.cajas" @cerrar="explosion = null" />
</template>

<style scoped>
/* La leyenda explica la barra de avance, que en celular no se muestra */
@media (max-width: 720px) { .leyenda-etapas { display: none; } }
.avance-oc { min-width: 150px; }
</style>
