<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { api } from '../api'
import { siguienteOrden } from '../composables/useTabla'
import { esInterno, sesion } from '../stores/sesion'
import { errorApi } from '../stores/ui'
import { fmtFecha } from '../utils'
import FiltroMulti from './FiltroMulti.vue'
import FiltroPeriodo, { rango } from './FiltroPeriodo.vue'
import Icono from './Icono.vue'
import Kpi from './Kpi.vue'
import Paginacion from './Paginacion.vue'
import ThOrden from './ThOrden.vue'

// Lead times por origen: cuánto tarda en promedio cada etapa (de la OC al
// ingreso en bodega), si logística libera a tiempo antes de la XF (Asia 21
// días, el resto 15) y, por OC, cada hito contra su meta. La llegada se mide
// contra la fecha límite en puerto: la fecha en tienda menos los días a la
// bodega, el ingreso y la reexportación de su región.
const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
const [d0, d1] = rango('12m')
const periodo = ref({ clave: '12m', desde: iso(d0), hasta: iso(d1) })
const f = reactive({ origen: [], region: [], proveedor: [], riesgo: '', lib: '' })
const tabla = reactive({ orden: 'fecha_xf:asc', page: 1, size: 15 })
const datos = ref({ items: [], total: 0, kpis: {}, origenes: [], etapas: [], regiones: [], opciones: {} })
const cargando = ref(true)
const abiertas = reactive(new Set())

const COLOR = (i) => `var(--etapa-${i + 1})`
const ESTADO = {
  a_tiempo: ['On time', 'ok', 'check'], hecho: ['Done', 'neutro', 'check'], tarde: ['Late', 'error', 'alerta'],
  vencido: ['Overdue', 'error', 'reloj'], riesgo: ['At risk', 'aviso', 'alerta'], en_plan: ['On plan', 'info', 'reloj'],
  pendiente: ['Pending', 'neutro', 'reloj'],
}
const RIESGO = { ATRASO: ['Late', 'error'], JUSTO: ['Tight', 'aviso'], A_TIEMPO: ['On time', 'ok'] }

async function cargar() {
  cargando.value = true
  try {
    datos.value = await api.get('/seguimiento/leadtimes', {
      desde: periodo.value.desde, hasta: periodo.value.hasta, origen: f.origen.join(','), region: f.region.join(','),
      proveedor: f.proveedor.join(','), riesgo: f.riesgo, lib: f.lib, ...tabla, proveedor_id: sesion.proveedorId || undefined,
    })
  } catch (e) {
    errorApi(e)
  } finally {
    cargando.value = false
  }
}
function recargar() {
  tabla.page = 1
  cargar()
}
function ordenar(campo) {
  tabla.orden = siguienteOrden(tabla.orden, campo)
  recargar()
}
function alternar(id) {
  if (abiertas.has(id)) abiertas.delete(id)
  else abiertas.add(id)
}
// Barra de un origen: cada etapa con su promedio (solo las que tienen datos)
const segmentos = (o) => datos.value.etapas.map((e, i) => ({ ...e, i, prom: o.etapas[e.clave]?.prom, n: o.etapas[e.clave]?.n }))
  .filter((s) => s.prom)
const maxTotal = computed(() => Math.max(1, ...datos.value.origenes.map((o) => segmentos(o).reduce((a, s) => a + s.prom, 0))))
const d = (n) => (n === null || n === undefined ? '—' : `${Number(n).toLocaleString('en-US', { maximumFractionDigits: 1 })} d`)
const difTxt = (h) => {
  if (h.dif === null || h.dif === undefined) return ''
  if (h.dif === 0) return 'on the day'
  if (h.estado === 'vencido') return `${h.dif} d overdue`
  return h.dif > 0 ? `${h.dif} d late` : `${-h.dif} d early`
}
const reglas = computed(() => datos.value.regiones.map((r) => `${r.nombre} ${r.dias_liberacion} d`).join(' · '))

watch(() => [periodo.value, sesion.proveedorId], recargar, { deep: true })
watch(() => tabla.size, recargar)
onMounted(cargar)
</script>

<template>
  <div class="filtros">
    <FiltroPeriodo v-model="periodo" />
    <FiltroMulti v-model="f.origen" etiqueta="Origin" :opciones="datos.opciones.origenes || []" @change="recargar" />
    <FiltroMulti v-model="f.region" etiqueta="Region" :opciones="datos.opciones.regiones || []" @change="recargar" />
    <FiltroMulti v-if="esInterno()" v-model="f.proveedor" etiqueta="Supplier" :opciones="(datos.opciones.proveedores || []).map((p) => ({ valor: p, texto: p }))" @change="recargar" />
    <span class="ayuda separar">POs created in the period · {{ datos.kpis.ocs ?? 0 }}</span>
  </div>

  <section class="kpis">
    <Kpi titulo="Logistics release on time (%)" :valor="datos.kpis.lib_pct ?? 0" icono="check" :tono="(datos.kpis.lib_pct ?? 100) >= 80 ? 'exito' : 'alerta'"
         :detalle="`${datos.kpis.lib_total || 0} released · target ${reglas || '—'} before XF`" @abrir="f.lib = f.lib === 'tarde' ? '' : 'tarde'; recargar()" />
    <Kpi titulo="Release overdue" :valor="datos.kpis.lib_vencidas ?? 0" icono="reloj" :tono="datos.kpis.lib_vencidas ? 'alerta' : 'exito'"
         detalle="not released and the target date passed" @abrir="f.lib = f.lib === 'vencida' ? '' : 'vencida'; recargar()" />
    <Kpi titulo="Average lead time (days)" :valor="datos.kpis.total_prom ?? 0" icono="grafica"
         :detalle="`PO created to warehouse entry · transit ${d(datos.kpis.transito_prom)}`" />
    <Kpi titulo="Late for the port deadline" :valor="datos.kpis.tarde ?? 0" icono="alerta" :tono="datos.kpis.tarde ? 'alerta' : 'exito'"
         :detalle="`${datos.kpis.justo || 0} tight (under 7 days of slack)`" @abrir="f.riesgo = f.riesgo === 'ATRASO' ? '' : 'ATRASO'; recargar()" />
  </section>

  <section class="panel" style="margin-bottom: 16px">
    <div class="panel-cabeza">
      <div>
        <h2>Average days per stage, by origin</h2>
        <p>Each stage goes from one milestone to the next. Only POs that already reached both milestones count.</p>
      </div>
    </div>
    <div class="tabla-marco">
      <table class="tabla lt-origenes">
        <thead>
          <tr>
            <th>Origin</th>
            <th class="num">POs</th>
            <th style="min-width: 150px">Lead time</th>
            <th v-for="(e, i) in datos.etapas" :key="e.clave" class="num col-etapa"><i class="punto" :style="{ background: COLOR(i) }"></i> {{ e.nombre }}</th>
            <th class="num">Total</th>
            <th title="Logistics release before the XF: average days and share on time">Release vs XF</th>
            <th class="num" title="Pickup date minus XF: positive = picked up after the XF">Pickup vs XF</th>
            <th class="num" title="Days between the port arrival and the port deadline (in-store date minus warehouse, entry and re-export)">Slack at port</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="!datos.origenes.length"><td :colspan="datos.etapas.length + 7" class="vacio">{{ cargando ? 'Loading…' : 'No purchase orders in this period.' }}</td></tr>
          <tr v-for="o in datos.origenes" :key="o.origen">
            <td><span class="fuerte">{{ o.nombre }}</span><span class="sub">{{ o.origen }} · {{ o.region_nombre }}</span></td>
            <td class="num">{{ o.ocs }}</td>
            <td>
              <div v-if="segmentos(o).length" class="apilada" :style="{ width: `${Math.max(12, (segmentos(o).reduce((a, s) => a + s.prom, 0) * 100) / maxTotal)}%` }"
                   role="img" :aria-label="segmentos(o).map((s) => `${s.nombre}: ${d(s.prom)}`).join(', ')">
                <span v-for="s in segmentos(o)" :key="s.clave" :style="{ flex: s.prom, background: COLOR(s.i) }" :title="`${s.nombre}: ${d(s.prom)} (${s.n} POs)`"></span>
              </div>
              <span v-else class="apagado">No stage completed yet</span>
            </td>
            <td v-for="e in datos.etapas" :key="e.clave" class="num col-etapa" :title="o.etapas[e.clave].n ? `${o.etapas[e.clave].n} POs` : 'No data yet'">{{ d(o.etapas[e.clave].prom) }}</td>
            <td class="num fuerte" :title="o.completas ? `${o.completas} POs with every stage` : 'No PO has every stage yet'">{{ d(o.total_prom) }}</td>
            <td class="ajustar" style="max-width: 150px">
              <template v-if="o.lib.total">
                <span class="etiqueta" :class="o.lib.pct >= 80 ? 'ok' : 'error'" style="margin-left: 0">{{ o.lib.pct }}% on time</span>
                <span class="sub">avg {{ d(o.lib.dias_antes_xf) }} before · target {{ o.lib.meta }} d</span>
              </template>
              <span v-else class="apagado">Target {{ o.lib.meta }} d</span>
              <span v-if="o.lib.vencidas" class="sub" style="color: var(--error)">{{ o.lib.vencidas }} overdue</span>
            </td>
            <td class="num">{{ o.recoleccion_vs_xf === null ? '—' : `${o.recoleccion_vs_xf > 0 ? '+' : ''}${d(o.recoleccion_vs_xf)}` }}</td>
            <td class="num">{{ d(o.holgura) }}<span v-if="o.tarde" class="sub" style="color: var(--error)">{{ o.tarde }} late</span></td>
          </tr>
        </tbody>
      </table>
    </div>
    <div class="leyenda-etapas">
      <span v-for="(e, i) in datos.etapas" :key="e.clave"><i class="punto" :style="{ background: COLOR(i) }"></i>{{ e.nombre }}</span>
    </div>
    <p class="ayuda" style="margin: 10px 0 0">
      Port deadline = in-store date minus port to warehouse, warehouse entry and re-export days of each region
      <template v-for="(r, i) in datos.regiones" :key="r.codigo">{{ i ? ' · ' : ' (' }}{{ r.nombre }} {{ r.dias_puerto_bodega }}+{{ r.dias_ingreso }}+{{ r.dias_reexportacion }} d{{ i === datos.regiones.length - 1 ? ')' : '' }}</template>.
      Re-export is not recorded yet: its days are reserved. <router-link v-if="esInterno()" to="/mantenimiento?catalogo=regiones" class="enlace">Edit the targets</router-link>
    </p>
  </section>

  <div class="filtros">
    <div class="segmentos" role="group" aria-label="Arrival">
      <button v-for="[v, t] in [['', 'All'], ['ATRASO', 'Late'], ['JUSTO', 'Tight'], ['A_TIEMPO', 'On time']]" :key="v" type="button" class="segmento"
              :aria-pressed="f.riesgo === v" @click="f.riesgo = v; recargar()">{{ t }}</button>
    </div>
    <select v-model="f.lib" aria-label="Logistics release" @change="recargar">
      <option value="">Logistics release: all</option><option value="tarde">Released late</option><option value="vencida">Overdue, not released</option>
    </select>
  </div>
  <div class="tabla-marco tabla-fija">
    <table class="tabla">
      <thead>
        <tr>
          <th><span class="oculto-visual">Open</span></th>
          <ThOrden campo="oc" :orden="tabla.orden" @ordenar="ordenar">Purchase order</ThOrden>
          <ThOrden campo="origen" :orden="tabla.orden" @ordenar="ordenar">Origin</ThOrden>
          <th>Logistics release</th>
          <ThOrden campo="fecha_xf" :orden="tabla.orden" @ordenar="ordenar">XF</ThOrden>
          <ThOrden campo="arribo" :orden="tabla.orden" @ordenar="ordenar">Port arrival</ThOrden>
          <ThOrden campo="limite_puerto" :orden="tabla.orden" @ordenar="ordenar">Port deadline</ThOrden>
          <ThOrden campo="fecha_tienda" :orden="tabla.orden" @ordenar="ordenar">In store</ThOrden>
          <ThOrden campo="holgura" :orden="tabla.orden" @ordenar="ordenar">Early / late</ThOrden>
        </tr>
      </thead>
      <tbody>
        <tr v-if="!datos.items.length"><td colspan="9" class="vacio">{{ cargando ? 'Loading…' : 'No purchase orders match these filters.' }}</td></tr>
        <template v-for="o in datos.items" :key="o.oc_id">
          <tr class="clicable" @click="alternar(o.oc_id)">
            <td><button type="button" class="btn-icono" :aria-expanded="abiertas.has(o.oc_id)" :aria-label="`See the milestones of ${o.oc}`"><Icono :nombre="abiertas.has(o.oc_id) ? 'abajo' : 'derecha'" :tam="16" /></button></td>
            <td><span class="codigo fuerte">{{ o.oc }}</span><span class="sub">{{ o.proveedor }}<template v-if="o.embarques.length"> · {{ o.embarques.join(', ') }}</template></span></td>
            <td>{{ o.origen_nombre || '—' }}<span class="sub">{{ o.region_nombre }}</span></td>
            <td>
              <template v-if="o.lib_dias_antes_xf !== null">
                <span class="etiqueta" :class="o.lib_a_tiempo ? 'ok' : 'error'" style="margin-left: 0">{{ o.lib_a_tiempo ? 'On time' : 'Late' }}</span>
                <span class="sub">{{ o.lib_dias_antes_xf }} d before XF · target {{ o.dias_liberacion }}</span>
              </template>
              <template v-else-if="o.lib_vencida"><span class="etiqueta error" style="margin-left: 0">Overdue</span><span class="sub">target {{ o.dias_liberacion }} d before XF</span></template>
              <span v-else class="apagado">Pending · target {{ o.dias_liberacion }} d</span>
            </td>
            <td>{{ fmtFecha(o.fecha_xf) }}</td>
            <td>{{ fmtFecha(o.arribo) }}<span class="sub">{{ o.arribo_real ? 'actual' : 'estimated' }}</span></td>
            <td>{{ fmtFecha(o.limite_puerto) }}</td>
            <td>{{ fmtFecha(o.fecha_tienda) }}</td>
            <td>
              <span v-if="o.riesgo" class="etiqueta" :class="RIESGO[o.riesgo][1]" style="margin-left: 0">{{ RIESGO[o.riesgo][0] }}</span>
              <span class="sub">{{ o.holgura === null ? '—' : o.holgura >= 0 ? `${o.holgura} d to spare` : `${-o.holgura} d late` }}</span>
            </td>
          </tr>
          <tr v-if="abiertas.has(o.oc_id)" class="fila-hija">
            <td colspan="9">
              <div class="subtabla">
                <ol class="lt-hitos" :aria-label="`Milestones of ${o.oc}`">
                  <li v-for="h in o.hitos" :key="h.clave" :class="`hito-${ESTADO[h.estado][1]}`">
                    <span class="hito-nombre">{{ h.nombre }}</span>
                    <span class="hito-fecha">{{ h.fecha ? fmtFecha(h.fecha) : h.estimada ? `≈ ${fmtFecha(h.estimada)}` : '—' }}</span>
                    <span class="hito-meta">{{ h.meta ? `target ${fmtFecha(h.meta)}` : '&nbsp;' }}</span>
                    <span class="etiqueta" :class="ESTADO[h.estado][1]" style="margin-left: 0"><Icono :nombre="ESTADO[h.estado][2]" :tam="12" />{{ ESTADO[h.estado][0] }}<template v-if="difTxt(h)"> · {{ difTxt(h) }}</template></span>
                  </li>
                </ol>
                <p class="ayuda" style="margin: 8px 0 0">≈ estimated from the shipment ETA or the standard days of {{ o.region_nombre }}. In store is estimated after warehouse entry plus re-export (not recorded yet).</p>
              </div>
            </td>
          </tr>
        </template>
      </tbody>
    </table>
  </div>
  <Paginacion :page="tabla.page" :size="tabla.size" :total="datos.total" @cambiar="(p) => { tabla.page = p; cargar() }" @tamano="(t) => (tabla.size = t)" />
</template>

<style scoped>
.lt-origenes td { white-space: nowrap; }
/* En pantallas angostas las etapas se leen en la barra (con su detalle al pasar el cursor) */
@media (max-width: 1360px) { .col-etapa { display: none; } }
.lt-origenes th { white-space: normal; vertical-align: bottom; min-width: 64px; line-height: 1.25; font-size: 0.7rem; }
.lt-origenes td, .lt-origenes th { padding-left: 8px; padding-right: 8px; }
.lt-origenes th .punto { margin-right: 2px; }
.lt-hitos { list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 8px; }
.lt-hitos li { display: flex; flex-direction: column; gap: 3px; padding: 10px 12px; border-radius: var(--radio); background: var(--superficie); border: 1px solid var(--linea); border-top: 3px solid var(--linea); }
.lt-hitos li.hito-ok { border-top-color: var(--ok); }
.lt-hitos li.hito-error { border-top-color: var(--error); }
.lt-hitos li.hito-aviso { border-top-color: var(--aviso); }
.lt-hitos li.hito-info { border-top-color: var(--azul); }
.hito-nombre { font-size: 0.78rem; color: var(--tinta-2); font-weight: 600; }
.hito-fecha { font-weight: 700; }
.hito-meta { font-size: 0.78rem; color: var(--tinta-3); }
.lt-hitos .etiqueta { align-self: flex-start; font-size: 0.72rem; }
</style>
