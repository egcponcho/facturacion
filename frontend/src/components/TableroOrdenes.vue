<script setup>
import { t, tx } from '../i18n/index.js'
import FechaTienda from './FechaTienda.vue'
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { api } from '../api'
import { siguienteOrden } from '../composables/useTabla'
import { esInterno, sesion, ve } from '../stores/sesion'
import { useColumnas } from '../composables/useColumnas'
import SelectorColumnas from './SelectorColumnas.vue'
import { errorApi } from '../stores/ui'
import { COMERCIAL, LIBERACION, TIEMPO, cantTxt, diasTxt, fmtFecha, fmtNum } from '../utils'
import ExplosionPrepack from './ExplosionPrepack.vue'
import GraficoColumnas from './GraficoColumnas.vue'
import Icono from './Icono.vue'
import Kpi from './Kpi.vue'
import Paginacion from './Paginacion.vue'
import ThOrden from './ThOrden.vue'
import { filasDefecto } from '../stores/preferencias'

// Tablero de órdenes de compra: liberaciones (comercial y logística), cuánto
// falta por facturar, qué va en contenedor, en camino y recibido. Cada OC se
// abre en el detalle por SKU: en qué etapa está, en qué documento y unidad de
// carga va y si llega a tiempo a tienda.
const props = defineProps({ filtros: { type: Object, required: true } })
const emit = defineEmits(['opciones', 'filtrar'])
const datos = ref({ items: [], total: 0, kpis: {}, estados: [] })
const cargando = ref(true)
const tabla = reactive({ orden: 'fecha_xf:asc', page: 1, size: filasDefecto() })
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
// Columnas: lo esencial a la vista; el resto en «Columnas» (y sin los datos que el rol no ve)
const cols = useColumnas('seguimiento', [
  { clave: 'oc', texto: t('Purchase order'), fija: true },
  { clave: 'sociedad', texto: t('Company · plant'), grupo: 'codigos_internos', inicial: false },
  { clave: 'liberaciones', texto: t('Releases'), grupo: 'liberaciones', inicial: false },
  { clave: 'estado', texto: t('Status') },
  { clave: 'avance', texto: t('Progress') },
  { clave: 'por_facturar', texto: t('To invoice') },
  { clave: 'xf', texto: 'XF' },
  { clave: 'tienda', texto: t('In store'), grupo: 'fechas_internas', inicial: false },
  { clave: 'tienda_estimada', texto: t('Est. in store'), grupo: 'fechas_internas' },
  { clave: 'holgura', texto: t('Vs. port deadline'), grupo: 'fechas_internas' },
  { clave: 'embarques', texto: t('Shipments') },
])
const ncols = computed(() => cols.cuantas.value + 1)
// La gráfica por estado queda plegada: los estados ya están como pastillas
const verGrafica = ref(false)
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
const grafica = computed(() => datos.value.estados.map((e) => ({ etiqueta: e.nombre.split(' (')[0].replace('No commercial release', t('No comm. rel.')).replace('No logistics release', t('No log. rel.')), valor: e.total, detalle: e.nombre })))

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
    <Kpi :titulo="t('Purchase orders')" :valor="datos.kpis.ocs" icono="ordenes" :detalle="t('{0}% invoiced', [fmtNum(datos.kpis.avance || 0, 1)])" @abrir="emit('filtrar', {})" />
    <Kpi :titulo="t('Released')" :valor="datos.kpis.liberadas" icono="check" tono="exito" :detalle="t('can be invoiced')" @abrir="emit('filtrar', {})" />
    <Kpi :titulo="t('Not released')" :valor="datos.kpis.sin_liberar" icono="candado" :tono="datos.kpis.sin_liberar ? 'alerta' : 'exito'"
         :detalle="t('cannot be invoiced yet')" @abrir="emit('filtrar', { estado: 'SIN_COMERCIAL' })" />
    <Kpi :titulo="t('XF overdue, not invoiced')" :valor="datos.kpis.xf_vencida" icono="reloj" :tono="datos.kpis.xf_vencida ? 'alerta' : 'exito'"
         :detalle="t('the XF date has passed')" @abrir="emit('filtrar', { xf_vencida: '1' })" />
    <Kpi v-if="ve('fechas_internas')" :titulo="t('Late for the port deadline')" :valor="datos.kpis.atraso" icono="alerta" :tono="datos.kpis.atraso ? 'alerta' : 'exito'"
         :detalle="t('port arrival after the port deadline')" @abrir="emit('filtrar', { riesgo: 'ATRASO' })" />
  </section>

  <section class="panel" style="margin-bottom: 16px">
    <div class="panel-cabeza">
      <div><h2>{{ t('POs by status') }}</h2><p>{{ t('From release to receipt. Click a status to filter the table.') }}</p></div>
      <div class="fila-flex">
        <button type="button" class="btn btn-fantasma btn-chico" :aria-expanded="verGrafica" @click="verGrafica = !verGrafica">
          <Icono nombre="grafica" :tam="15" />{{ verGrafica ? t('Hide chart') : t('Show chart') }}
        </button>
        <SelectorColumnas :columnas="cols" />
      </div>
    </div>
    <GraficoColumnas v-if="verGrafica" :datos="grafica" :titulo="t('Purchase orders by status')" />
    <div class="chips" style="margin: 10px 0 0">
      <button v-for="e in datos.estados" :key="e.clave" type="button" class="pildora" :aria-pressed="filtros.estado === e.clave"
              @click="emit('filtrar', { estado: filtros.estado === e.clave ? '' : e.clave })">
        {{ tx(e.nombre) }}<span class="cuenta">{{ tx(e.total) }}</span>
      </button>
    </div>
  </section>

  <div class="tabla-marco tabla-fija">
    <table class="tabla" v-tarjetas>
      <thead>
        <tr>
          <th><span class="oculto-visual">{{ t('Open') }}</span></th>
          <ThOrden campo="oc" :orden="tabla.orden" @ordenar="ordenar">{{ t('Purchase order') }}</ThOrden>
          <ThOrden v-if="cols.ver('sociedad')" campo="centro" :orden="tabla.orden" @ordenar="ordenar">{{ t('Company · plant') }}</ThOrden>
          <th v-if="cols.ver('liberaciones')">{{ t('Releases') }}</th>
          <ThOrden v-if="cols.ver('estado')" campo="estado" :orden="tabla.orden" @ordenar="ordenar">{{ t('Status') }}</ThOrden>
          <ThOrden v-if="cols.ver('avance')" campo="avance" :orden="tabla.orden" @ordenar="ordenar">{{ t('Progress') }}</ThOrden>
          <ThOrden v-if="cols.ver('por_facturar')" campo="por_facturar" :orden="tabla.orden" num @ordenar="ordenar">{{ t('To invoice') }}</ThOrden>
          <ThOrden v-if="cols.ver('xf')" campo="fecha_xf" :orden="tabla.orden" @ordenar="ordenar">XF</ThOrden>
          <ThOrden v-if="cols.ver('tienda')" campo="fecha_tienda" :orden="tabla.orden" @ordenar="ordenar">{{ t('In store') }}</ThOrden>
          <ThOrden v-if="cols.ver('tienda_estimada')" campo="tienda_estimada" :orden="tabla.orden" @ordenar="ordenar" :title="t('Estimated with the lead times of its origin')">{{ t('Est. in store') }}</ThOrden>
          <ThOrden v-if="cols.ver('holgura')" campo="holgura" :orden="tabla.orden" :title="t('Port arrival against the port deadline: the in-store date minus the days to the warehouse, the warehouse entry and the re-export of its origin')" @ordenar="ordenar">{{ t('Vs. port deadline') }}</ThOrden>
          <th v-if="cols.ver('embarques')">{{ t('Shipments') }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-if="cargando && !datos.items.length"><td :colspan="ncols" class="vacio">{{ t('Loading…') }}</td></tr>
        <tr v-else-if="!datos.items.length"><td :colspan="ncols" class="vacio">{{ t('No purchase orders match these filters.') }}</td></tr>
        <template v-for="o in datos.items" :key="o.oc_id">
        <tr class="clicable" @click="alternar(o)">
          <td>
            <button type="button" class="btn-icono" :aria-expanded="!!detalles[o.oc_id]" :aria-label="t('See the SKU detail of {0}', [o.oc])">
              <Icono :nombre="detalles[o.oc_id] ? 'abajo' : 'derecha'" :tam="16" />
            </button>
          </td>
          <td>
            <router-link :to="{ path: '/ordenes', query: { q: o.oc, solo_disponible: '0' } }" class="codigo fuerte" @click.stop>{{ tx(o.oc) }}</router-link>
            <span class="sub">{{ tx(o.proveedor) }}<template v-if="o.marcas.length"> · {{ tx(o.marcas.join(', ')) }}</template></span>
          </td>
          <td v-if="cols.ver('sociedad')" class="codigo">{{ tx(o.sociedad) }} · {{ tx(o.centro) }}<span class="sub">{{ t('destination {0}', [o.centro_destino || '—']) }}</span></td>
          <td v-if="cols.ver('liberaciones')">
            <span class="insignias columna" style="margin-top: 0">
              <span class="etiqueta" :class="COMERCIAL[o.liberacion_comercial]?.[1]" :title="tx(COMERCIAL[o.liberacion_comercial]?.[2])">{{ tx(COMERCIAL[o.liberacion_comercial]?.[0]) }}</span>
              <span class="etiqueta" :class="LIBERACION[o.liberacion_logistica]?.[1]" :title="tx(LIBERACION[o.liberacion_logistica]?.[2])">{{ tx(LIBERACION[o.liberacion_logistica]?.[0]) }}</span>
            </span>
          </td>
          <td v-if="cols.ver('estado')" class="ajustar"><span class="etiqueta" :class="TONO[o.estado]" style="margin-inline-start: 0; white-space: normal">{{ tx(nombreEstado[o.estado]) }}</span></td>
          <td v-if="cols.ver('avance')" style="min-width: 150px">
            <div class="apilada" role="img" :aria-label="tx(TRAMOS.map(([k, t]) => `${t}: ${o.cantidades[k]}`).join(', '))">
              <span v-for="[k, txt, c] in TRAMOS.filter(([k]) => o.cantidades[k])" :key="k"
                    :style="{ width: `${(o.cantidades[k] * 100) / o.total}%`, background: c }" :title="`${tx(txt)}: ${fmtNum(o.cantidades[k])}`"></span>
            </div>
            <span class="sub">{{ t('{0}% invoiced · {1} {2}', [fmtNum(o.avance, 0), fmtNum(o.total), o.unidades.join('/')]) }}</span>
          </td>
          <td v-if="cols.ver('por_facturar')" class="num">{{ fmtNum(o.por_facturar) }}</td>
          <td v-if="cols.ver('xf')">{{ fmtFecha(o.fecha_xf) }}<span v-if="o.xf_vencida" class="sub" style="color: var(--error)">overdue</span></td>
          <td v-if="cols.ver('tienda')">{{ fmtFecha(o.fecha_tienda) }}<span class="sub">{{ diasTxt(o.dias_tienda) }}</span></td>
          <td v-if="cols.ver('tienda_estimada')"><FechaTienda :fecha="o.tienda_estimada" :dias="o.dias_vs_tienda" /></td>
          <td v-if="cols.ver('holgura')">
            <span v-if="o.riesgo" class="etiqueta" :class="RIESGOS[o.riesgo][1]" style="margin-inline-start: 0">{{ tx(RIESGOS[o.riesgo][0]) }}</span>
            <span v-if="o.holgura !== null" class="sub">{{ tx(o.holgura < 0 ? t('{0} d late', [-o.holgura]) : t('{0} d margin', [o.holgura])) }}</span>
          </td>
          <td v-if="cols.ver('embarques')" class="codigo">{{ tx(o.embarques.join(', ') || '—') }}</td>
        </tr>
        <tr v-if="detalles[o.oc_id]" class="fila-hija">
          <td :colspan="ncols">
            <div class="subtabla">
              <div class="tabla-marco">
                <table class="tabla" v-tarjetas>
                  <thead>
                    <tr><th>{{ t('Line') }}</th><th>SKU</th><th>{{ t('Brand · style · color') }}</th><th>{{ t('Size') }}</th><th v-if="ve('codigos_internos')">{{ t('Warehouse') }}</th><th class="num">{{ t('Quantity') }}</th>
                      <th>{{ t('Stage') }}</th><th>{{ t('Invoice / PL') }}</th><th>{{ t('Shipment · unit') }}</th><th>{{ t('Arrival') }}</th><th v-if="ve('fechas_internas')" :title="t('Port arrival against the port deadline (in-store date minus warehouse, entry and re-export days)')">{{ t('Vs. port deadline') }}</th></tr>
                  </thead>
                  <tbody>
                    <tr v-if="!detalles[o.oc_id].length"><td colspan="12" class="vacio">{{ t('No lines match these filters.') }}</td></tr>
                    <tr v-for="(l, i) in detalles[o.oc_id]" :key="i">
                      <td class="codigo">{{ tx(l.posicion) }}</td>
                      <td class="codigo">{{ tx(l.sku) }}</td>
                      <td>{{ tx(l.marca) }} {{ tx(l.estilo) }}<span class="sub">{{ tx(l.color) }}<template v-if="l.grupo"> · {{ tx(l.grupo) }}</template></span></td>
                      <td>
                        <b>{{ tx(l.talla || '—') }}</b>
                        <button v-if="l.tipo_empaque === 'PREPACK'" type="button" class="etiqueta acento btn-explosion" :title="t('See the prepack breakdown')"
                                @click="explosion = { sku: l.sku, cajas: l.cantidad }">{{ t('Prepack') }} <Icono nombre="lupa" :tam="12" /></button>
                      </td>
                      <td v-if="ve('codigos_internos')">{{ tx(l.almacen || '—') }}</td>
                      <td class="num">{{ cantTxt(l.cantidad, l.unidad) }}</td>
                      <td><span class="etiqueta" :class="ETAPAS[l.etapa]?.[1]" style="margin-inline-start: 0">{{ tx(ETAPAS[l.etapa]?.[0] || l.etapa) }}</span></td>
                      <td>
                        <router-link v-if="l.factura_id" :to="`/facturas/${l.factura_id}`">{{ tx(l.factura) }}</router-link>
                        <span v-else class="ayuda">—</span>
                        <router-link v-if="l.pl_id" :to="`/packing-lists/${l.pl_id}`" class="sub">{{ t('PL {0}', [l.pl]) }}</router-link>
                      </td>
                      <td>
                        <template v-if="l.embarque_id">
                          <router-link v-if="esInterno()" :to="`/transporte/embarques/${l.embarque_id}`" class="codigo">{{ tx(l.embarque) }}</router-link>
                          <span v-else class="codigo">{{ tx(l.embarque) }}</span>
                          <span class="sub codigo">{{ tx(l.contenedor) }}<template v-if="l.documento"> · {{ tx(l.documento) }}</template></span>
                        </template>
                        <span v-else class="ayuda">—</span>
                      </td>
                      <td>{{ fmtFecha(l.arribo_real || l.eta) }}<span v-if="l.arribo_real" class="sub">{{ t('actual') }}</span></td>
                      <td v-if="ve('fechas_internas')">
                        <span v-if="l.riesgo" class="etiqueta" :class="RIESGOS[l.riesgo][1]" style="margin-inline-start: 0">{{ tx(l.holgura < 0 ? t('{0} d late', [-l.holgura]) : `${l.holgura} d`) }}</span>
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
    <span v-for="[k, txt, c] in TRAMOS" :key="k"><i class="punto" :style="{ background: c }"></i>{{ tx(txt) }}</span>
  </div>
  <ExplosionPrepack v-if="explosion" :sku="explosion.sku" :cajas="explosion.cajas" @cerrar="explosion = null" />
</template>
