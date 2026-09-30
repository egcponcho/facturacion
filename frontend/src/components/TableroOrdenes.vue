<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { api } from '../api'
import { siguienteOrden } from '../composables/useTabla'
import { esInterno, sesion } from '../stores/sesion'
import { errorApi } from '../stores/ui'
import { COMERCIAL, LIBERACION, cantTxt, diasTxt, fmtFecha, fmtNum } from '../utils'
import ExplosionPrepack from './ExplosionPrepack.vue'
import GraficoColumnas from './GraficoColumnas.vue'
import Icono from './Icono.vue'
import Kpi from './Kpi.vue'
import Paginacion from './Paginacion.vue'
import ThOrden from './ThOrden.vue'

// Tablero de órdenes de compra: liberaciones (comercial y logística), cuánto
// falta por facturar, qué va en contenedor, en camino y recibido. Cada OC se
// abre en el detalle por SKU: en qué etapa está, en qué documento y unidad de
// carga va y si llega a tiempo a tienda.
const props = defineProps({ filtros: { type: Object, required: true } })
const emit = defineEmits(['opciones', 'filtrar'])
const datos = ref({ items: [], total: 0, kpis: {}, estados: [] })
const cargando = ref(true)
const tabla = reactive({ orden: 'fecha_xf:asc', page: 1, size: 25 })
const TONO = {
  SIN_COMERCIAL: 'aviso', SIN_LOGISTICA: 'aviso', POR_FACTURAR: 'neutro', PARCIAL: 'info', FACTURADA: 'acento',
  EN_CAMINO: 'info', RECIBIDA: 'ok',
}
const RIESGOS = { ATRASO: ['Arrives late', 'error'], JUSTO: ['Tight', 'aviso'], A_TIEMPO: ['On time', 'ok'] }
// Tramos de la barra de avance: del pedido a lo recibido (un solo tono, de claro a oscuro)
const TRAMOS = [
  ['por_facturar', 'To invoice', 'var(--tramo-1)'], ['facturado', 'Invoiced', 'var(--tramo-2)'],
  ['en_contenedor', 'In load unit', 'var(--tramo-3)'], ['en_camino', 'On the way', 'var(--tramo-4)'],
  ['recibido', 'Received', 'var(--tramo-5)'],
]
const ETAPAS = {
  PEND_LIBERACION: ['Pending release', 'aviso'], POR_FACTURAR: ['To invoice', 'neutro'],
  FACTURADO: ['Invoiced, no PL', 'info'], EN_PL: ['In packing list', 'acento'], CONTENEDOR: ['In load unit', 'acento'],
  EN_TRANSITO: ['In transit', 'info'], ARRIBADO: ['Arrived', 'info'], ENTREGADO: ['Delivered', 'ok'], RECIBIDO: ['Received', 'ok'],
}
const detalles = reactive({})
const explosion = ref(null)
async function alternar(o) {
  if (detalles[o.oc_id]) {
    delete detalles[o.oc_id]
    return
  }
  try {
    const r = await api.get('/seguimiento', { ...props.filtros, oc_id: o.oc_id, orden: 'etapa:asc', size: 200, proveedor_id: sesion.proveedorId || undefined })
    detalles[o.oc_id] = r.items
  } catch (e) {
    errorApi(e)
  }
}
const nombreEstado = computed(() => Object.fromEntries(datos.value.estados.map((e) => [e.clave, e.nombre])))
const grafica = computed(() => datos.value.estados.map((e) => ({ etiqueta: e.nombre.split(' (')[0].replace('No commercial release', 'No comm. rel.').replace('No logistics release', 'No log. rel.'), valor: e.total, detalle: e.nombre })))

async function cargar() {
  cargando.value = true
  try {
    datos.value = await api.get('/seguimiento/ordenes', { ...props.filtros, ...tabla, proveedor_id: sesion.proveedorId || undefined })
    emit('opciones', datos.value.opciones)
  } catch (e) {
    errorApi(e)
  } finally {
    cargando.value = false
  }
}
function ordenar(campo) {
  tabla.orden = siguienteOrden(tabla.orden, campo)
  tabla.page = 1
  cargar()
}
watch(() => [props.filtros, sesion.proveedorId], () => {
  tabla.page = 1
  for (const k of Object.keys(detalles)) delete detalles[k]
  cargar()
}, { deep: true })
onMounted(cargar)
</script>

<template>
  <section class="kpis" style="margin-bottom: 16px">
    <Kpi titulo="Purchase orders" :valor="datos.kpis.ocs" icono="ordenes" :detalle="`${fmtNum(datos.kpis.avance || 0, 1)}% invoiced`" @abrir="emit('filtrar', {})" />
    <Kpi titulo="Released" :valor="datos.kpis.liberadas" icono="check" tono="exito" detalle="commercial C and logistics 300/301" @abrir="emit('filtrar', {})" />
    <Kpi titulo="Not released" :valor="datos.kpis.sin_liberar" icono="candado" :tono="datos.kpis.sin_liberar ? 'alerta' : 'exito'"
         detalle="commercial P or logistics 304" @abrir="emit('filtrar', { estado: 'SIN_COMERCIAL' })" />
    <Kpi titulo="XF overdue, not invoiced" :valor="datos.kpis.xf_vencida" icono="reloj" :tono="datos.kpis.xf_vencida ? 'alerta' : 'exito'"
         detalle="the XF date has passed" @abrir="emit('filtrar', { xf_vencida: '1' })" />
    <Kpi titulo="Late for the store" :valor="datos.kpis.atraso" icono="alerta" :tono="datos.kpis.atraso ? 'alerta' : 'exito'"
         detalle="port arrival after the port deadline" @abrir="emit('filtrar', { riesgo: 'ATRASO' })" />
  </section>

  <section class="panel" style="margin-bottom: 16px">
    <div class="panel-cabeza">
      <div><h2>POs by status</h2><p>From release to receipt. Click a status to filter the table.</p></div>
    </div>
    <GraficoColumnas :datos="grafica" titulo="Purchase orders by status" />
    <div class="chips" style="margin: 10px 0 0">
      <button v-for="e in datos.estados" :key="e.clave" type="button" class="pildora" :aria-pressed="filtros.estado === e.clave"
              @click="emit('filtrar', { estado: filtros.estado === e.clave ? '' : e.clave })">
        {{ e.nombre }}<span class="cuenta">{{ e.total }}</span>
      </button>
    </div>
  </section>

  <div class="tabla-marco tabla-fija">
    <table class="tabla">
      <thead>
        <tr>
          <th><span class="oculto-visual">Open</span></th>
          <ThOrden campo="oc" :orden="tabla.orden" @ordenar="ordenar">Purchase order</ThOrden>
          <ThOrden campo="centro" :orden="tabla.orden" @ordenar="ordenar">Company · plant</ThOrden>
          <th>Releases</th>
          <ThOrden campo="estado" :orden="tabla.orden" @ordenar="ordenar">Status</ThOrden>
          <ThOrden campo="avance" :orden="tabla.orden" @ordenar="ordenar">Progress</ThOrden>
          <ThOrden campo="por_facturar" :orden="tabla.orden" num @ordenar="ordenar">To invoice</ThOrden>
          <ThOrden campo="fecha_xf" :orden="tabla.orden" @ordenar="ordenar">XF</ThOrden>
          <ThOrden campo="fecha_tienda" :orden="tabla.orden" @ordenar="ordenar">In store</ThOrden>
          <ThOrden campo="holgura" :orden="tabla.orden" title="Port arrival against the port deadline: the in-store date minus the days to the warehouse, the warehouse entry and the re-export of its origin" @ordenar="ordenar">Vs. port deadline</ThOrden>
          <th>Shipments</th>
        </tr>
      </thead>
      <tbody>
        <tr v-if="cargando && !datos.items.length"><td colspan="11" class="vacio">Loading…</td></tr>
        <tr v-else-if="!datos.items.length"><td colspan="11" class="vacio">No purchase orders match these filters.</td></tr>
        <template v-for="o in datos.items" :key="o.oc_id">
        <tr class="clicable" @click="alternar(o)">
          <td>
            <button type="button" class="btn-icono" :aria-expanded="!!detalles[o.oc_id]" :aria-label="`See the SKU detail of ${o.oc}`">
              <Icono :nombre="detalles[o.oc_id] ? 'abajo' : 'derecha'" :tam="16" />
            </button>
          </td>
          <td>
            <router-link :to="{ path: '/ordenes', query: { q: o.oc, solo_disponible: '0' } }" class="codigo fuerte" @click.stop>{{ o.oc }}</router-link>
            <span class="sub">{{ o.proveedor }}<template v-if="o.marcas.length"> · {{ o.marcas.join(', ') }}</template></span>
          </td>
          <td class="codigo">{{ o.sociedad }} · {{ o.centro }}<span class="sub">destination {{ o.centro_destino || '—' }}</span></td>
          <td>
            <span class="etiqueta" :class="COMERCIAL[o.liberacion_comercial]?.[1]" style="margin-left: 0" :title="COMERCIAL[o.liberacion_comercial]?.[2]">{{ COMERCIAL[o.liberacion_comercial]?.[0] }}</span>
            <span class="etiqueta" :class="LIBERACION[o.liberacion_logistica]?.[1]" :title="LIBERACION[o.liberacion_logistica]?.[2]">{{ LIBERACION[o.liberacion_logistica]?.[0] }}</span>
          </td>
          <td><span class="etiqueta" :class="TONO[o.estado]" style="margin-left: 0">{{ nombreEstado[o.estado] }}</span></td>
          <td style="min-width: 170px">
            <div class="apilada" role="img" :aria-label="TRAMOS.map(([k, t]) => `${t}: ${o.cantidades[k]}`).join(', ')">
              <span v-for="[k, t, c] in TRAMOS.filter(([k]) => o.cantidades[k])" :key="k"
                    :style="{ width: `${(o.cantidades[k] * 100) / o.total}%`, background: c }" :title="`${t}: ${fmtNum(o.cantidades[k])}`"></span>
            </div>
            <span class="sub">{{ fmtNum(o.avance, 0) }}% invoiced · {{ fmtNum(o.total) }} {{ o.unidades.join('/') }}</span>
          </td>
          <td class="num">{{ fmtNum(o.por_facturar) }}</td>
          <td>{{ fmtFecha(o.fecha_xf) }}<span v-if="o.xf_vencida" class="sub" style="color: var(--error)">overdue</span></td>
          <td>{{ fmtFecha(o.fecha_tienda) }}<span class="sub">{{ diasTxt(o.dias_tienda) }}</span></td>
          <td>
            <span v-if="o.riesgo" class="etiqueta" :class="RIESGOS[o.riesgo][1]" style="margin-left: 0">{{ RIESGOS[o.riesgo][0] }}</span>
            <span v-if="o.holgura !== null" class="sub">{{ o.holgura < 0 ? `${-o.holgura} d late` : `${o.holgura} d margin` }}</span>
          </td>
          <td class="codigo">{{ o.embarques.join(', ') || '—' }}</td>
        </tr>
        <tr v-if="detalles[o.oc_id]" class="fila-hija">
          <td colspan="11">
            <div class="subtabla">
              <div class="tabla-marco">
                <table class="tabla">
                  <thead>
                    <tr><th>Line</th><th>SKU</th><th>Brand · style · color</th><th>Size</th><th>Warehouse</th><th class="num">Quantity</th>
                      <th>Stage</th><th>Invoice / PL</th><th>Shipment · unit</th><th>Arrival</th><th title="Port arrival against the port deadline (in-store date minus warehouse, entry and re-export days)">Vs. port deadline</th></tr>
                  </thead>
                  <tbody>
                    <tr v-if="!detalles[o.oc_id].length"><td colspan="11" class="vacio">No lines match these filters.</td></tr>
                    <tr v-for="(l, i) in detalles[o.oc_id]" :key="i">
                      <td class="codigo">{{ l.posicion }}</td>
                      <td class="codigo">{{ l.sku }}</td>
                      <td>{{ l.marca }} {{ l.estilo }}<span class="sub">{{ l.color }}<template v-if="l.grupo"> · {{ l.grupo }}</template></span></td>
                      <td>
                        <b>{{ l.talla || '—' }}</b>
                        <button v-if="l.tipo_empaque === 'PREPACK'" type="button" class="etiqueta acento btn-explosion" title="See the prepack breakdown"
                                @click="explosion = { sku: l.sku, cajas: l.cantidad }">Prepack <Icono nombre="lupa" :tam="12" /></button>
                      </td>
                      <td>{{ l.almacen || '—' }}</td>
                      <td class="num">{{ cantTxt(l.cantidad, l.unidad) }}</td>
                      <td><span class="etiqueta" :class="ETAPAS[l.etapa]?.[1]" style="margin-left: 0">{{ ETAPAS[l.etapa]?.[0] || l.etapa }}</span></td>
                      <td>
                        <router-link v-if="l.factura_id" :to="`/facturas/${l.factura_id}`">{{ l.factura }}</router-link>
                        <span v-else class="ayuda">—</span>
                        <router-link v-if="l.pl_id" :to="`/packing-lists/${l.pl_id}`" class="sub">PL {{ l.pl }}</router-link>
                      </td>
                      <td>
                        <template v-if="l.embarque_id">
                          <router-link v-if="esInterno()" :to="`/transporte/embarques/${l.embarque_id}`" class="codigo">{{ l.embarque }}</router-link>
                          <span v-else class="codigo">{{ l.embarque }}</span>
                          <span class="sub codigo">{{ l.contenedor }}<template v-if="l.documento"> · {{ l.documento }}</template></span>
                        </template>
                        <span v-else class="ayuda">—</span>
                      </td>
                      <td>{{ fmtFecha(l.arribo_real || l.eta) }}<span v-if="l.arribo_real" class="sub">actual</span></td>
                      <td>
                        <span v-if="l.riesgo" class="etiqueta" :class="RIESGOS[l.riesgo][1]" style="margin-left: 0">{{ l.holgura < 0 ? `${-l.holgura} d late` : `${l.holgura} d` }}</span>
                        <span v-else class="ayuda">—</span>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </td>
        </tr>
        </template>
      </tbody>
    </table>
  </div>
  <Paginacion :page="tabla.page" :size="tabla.size" :total="datos.total" @cambiar="(p) => { tabla.page = p; cargar() }" @tamano="(t) => (tabla.size = t)" />
  <div class="leyenda-etapas">
    <span v-for="[k, t, c] in TRAMOS" :key="k"><i class="punto" :style="{ background: c }"></i>{{ t }}</span>
  </div>
  <ExplosionPrepack v-if="explosion" :sku="explosion.sku" :cajas="explosion.cajas" @cerrar="explosion = null" />
</template>
