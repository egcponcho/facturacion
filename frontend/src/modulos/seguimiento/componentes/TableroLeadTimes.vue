<script setup>
import { t, tx } from '@/i18n/index.js'
import FechaTienda from '@/componentes/FechaTienda.vue'
import { computed, onMounted, reactive, ref, watch } from 'vue'
import Seleccion from '@/componentes/Seleccion.vue'
import { api } from '@/nucleo/api'
import { siguienteOrden } from '@/composables/useTabla'
import { esInterno, sesion, ve } from '@/stores/sesion'
import { errorApi } from '@/stores/ui'
import { TIEMPO, fmtFecha, fmtNum } from '@/nucleo/utils'
import FiltroMulti from '@/componentes/FiltroMulti.vue'
import FiltroPeriodo, { rango } from '@/componentes/FiltroPeriodo.vue'
import Icono from '@/componentes/Icono.vue'
import Kpi from '@/componentes/Kpi.vue'
import Paginacion from '@/componentes/Paginacion.vue'
import ThOrden from '@/componentes/ThOrden.vue'
import { filasDefecto } from '@/stores/preferencias'

// Lead times por origen: cuánto tarda en promedio cada etapa (de la OC al
// ingreso en bodega), si logística libera a tiempo antes de la XF (Asia 21
// días, el resto 15) y, por OC, cada hito contra su meta. La llegada se mide
// contra la fecha límite en puerto: la fecha en tienda menos los días a la
// bodega, el ingreso y la reexportación de su región.
const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
const [d0, d1] = rango('12m')
const periodo = ref({ clave: '12m', desde: iso(d0), hasta: iso(d1) })
const f = reactive({ origen: [], region: [], proveedor: [], riesgo: '', lib: '' })
const tabla = reactive({ orden: 'fecha_xf:asc', page: 1, size: filasDefecto() })
const datos = ref({ items: [], total: 0, kpis: {}, origenes: [], etapas: [], regiones: [], opciones: {} })
const cargando = ref(true)
const abiertas = reactive(new Set())

const COLOR = (i) => `var(--etapa-${i + 1})`
const ESTADO = {
  a_tiempo: [t('On time'), 'ok', 'check'], hecho: [t('Done'), 'neutro', 'check'], tarde: [t('Late'), 'error', 'alerta'],
  vencido: [t('Overdue'), 'error', 'reloj'], riesgo: [t('At risk'), 'aviso', 'alerta'], en_plan: [t('On plan'), 'info', 'reloj'],
  pendiente: [t('Pending'), 'neutro', 'reloj'],
}
const RIESGO = TIEMPO

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
const d = (n) => (n === null || n === undefined ? '—' : `${fmtNum(n, Number.isInteger(Number(n)) ? 0 : 1)} d`)
const difTxt = (h) => {
  if (h.dif === null || h.dif === undefined) return ''
  if (h.dif === 0) return t('on the day')
  if (h.estado === 'vencido') return t('{0} d overdue', [h.dif])
  return h.dif > 0 ? t('{0} d late', [h.dif]) : t('{0} d early', [-h.dif])
}
const reglas = computed(() => datos.value.regiones.map((r) => `${r.nombre} ${r.dias_liberacion} d`).join(' · '))

watch(() => [periodo.value, sesion.proveedorId], recargar, { deep: true })
watch(() => tabla.size, recargar)
onMounted(cargar)
</script>

<template>
  <div class="filtros" v-filtros>
    <FiltroPeriodo v-model="periodo" />
    <FiltroMulti v-if="(datos.opciones.origenes || []).length > 1 || f.origen.length" v-model="f.origen" :etiqueta="t('Origin')" :opciones="datos.opciones.origenes || []" @change="recargar" />
    <FiltroMulti v-if="(datos.opciones.regiones || []).length > 1 || f.region.length" v-model="f.region" :etiqueta="t('Region')" :opciones="datos.opciones.regiones || []" @change="recargar" />
    <FiltroMulti v-if="esInterno()" v-model="f.proveedor" :etiqueta="t('Supplier')" :opciones="(datos.opciones.proveedores || []).map((p) => ({ valor: p, texto: p }))" @change="recargar" />
    <span class="ayuda separar">{{ t('POs created in the period · {0}', [datos.kpis.ocs ?? 0]) }}</span>
  </div>

  <section class="kpis">
    <Kpi :titulo="t('Logistics release on time (%)')" :valor="datos.kpis.lib_pct ?? 0" icono="check" :tono="(datos.kpis.lib_pct ?? 100) >= 80 ? 'exito' : 'alerta'"
         :detalle="t('{0} released · target {1} before XF', [datos.kpis.lib_total || 0, reglas || '—'])" @abrir="f.lib = f.lib === 'tarde' ? '' : 'tarde'; recargar()" />
    <Kpi :titulo="t('Release overdue')" :valor="datos.kpis.lib_vencidas ?? 0" icono="reloj" :tono="datos.kpis.lib_vencidas ? 'alerta' : 'exito'"
         :detalle="t('not released and the target date passed')" @abrir="f.lib = f.lib === 'vencida' ? '' : 'vencida'; recargar()" />
    <Kpi :titulo="t('Average lead time (days)')" :valor="datos.kpis.total_prom ?? 0" icono="grafica"
         :detalle="t('PO created to warehouse entry · transit {0}', [d(datos.kpis.transito_prom)])" />
    <Kpi v-if="ve('fechas_internas')" :titulo="t('Late for the port deadline')" :valor="datos.kpis.tarde ?? 0" icono="alerta" :tono="datos.kpis.tarde ? 'alerta' : 'exito'"
         :detalle="t('{0} at risk (little slack before the in-store date)', [datos.kpis.justo || 0])" @abrir="f.riesgo = f.riesgo === 'ATRASO' ? '' : 'ATRASO'; recargar()" />
  </section>

  <section class="panel mb-4">
    <div class="panel-cabeza">
      <div>
        <h2>{{ t('Average days per stage, by origin') }}</h2>
        <p>{{ t('Each stage goes from one milestone to the next. Only POs that already reached both milestones count.') }}</p>
      </div>
    </div>
    <div class="tabla-marco">
      <table class="tabla lt-origenes" v-tarjetas>
        <thead>
          <tr>
            <th>{{ t('Origin') }}</th>
            <th class="num">{{ t('POs') }}</th>
            <th style="min-width: 150px">{{ t('Lead time') }}</th>
            <th v-for="(e, i) in datos.etapas" :key="e.clave" class="num col-etapa"><i class="punto" :style="{ background: COLOR(i) }"></i> {{ tx(e.nombre) }}</th>
            <th class="num">{{ t('Total') }}</th>
            <th :title="t('Logistics release before the XF: average days and share on time')">{{ t('Release vs XF') }}</th>
            <th class="num" :title="t('Pickup date minus XF: positive = picked up after the XF')">{{ t('Pickup vs XF') }}</th>
            <th class="num" :title="t('Days between the port arrival and the port deadline (in-store date minus warehouse, entry and re-export)')">{{ t('Slack at port') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="!datos.origenes.length"><td :colspan="datos.etapas.length + 7" class="vacio">{{ tx(cargando ? t('Loading…') : t('No purchase orders in this period.')) }}</td></tr>
          <tr v-for="o in datos.origenes" :key="o.origen">
            <td><span class="fuerte">{{ tx(o.nombre) }}</span><span class="sub">{{ tx(o.origen) }} · {{ tx(o.region_nombre) }}</span></td>
            <td class="num">{{ tx(o.ocs) }}</td>
            <td>
              <div v-if="segmentos(o).length" class="apilada" :style="{ width: `${Math.max(12, (segmentos(o).reduce((a, s) => a + s.prom, 0) * 100) / maxTotal)}%` }"
                   role="img" :aria-label="tx(segmentos(o).map((s) => `${s.nombre}: ${d(s.prom)}`).join(', '))">
                <span v-for="s in segmentos(o)" :key="s.clave" :style="{ flex: s.prom, background: COLOR(s.i) }" :title="t('{0}: {1} ({2} POs)', [s.nombre, d(s.prom), s.n])"></span>
              </div>
              <span v-else class="apagado">{{ t('No stage completed yet') }}</span>
            </td>
            <td v-for="e in datos.etapas" :key="e.clave" class="num col-etapa" :title="tx(o.etapas[e.clave].n ? t('{0} POs', [o.etapas[e.clave].n]) : t('No data yet'))">{{ tx(d(o.etapas[e.clave].prom)) }}</td>
            <td class="num fuerte" :title="tx(o.completas ? t('{0} POs with every stage', [o.completas]) : t('No PO has every stage yet'))">{{ tx(d(o.total_prom)) }}</td>
            <td class="ajustar" style="max-width: 150px">
              <template v-if="o.lib.total">
                <span class="etiqueta ms-0" :class="o.lib.pct >= 80 ? 'ok' : 'error'">{{ t('{0}% on time', [o.lib.pct]) }}</span>
                <span class="sub">{{ t('avg {0} before · target {1} d', [d(o.lib.dias_antes_xf), o.lib.meta]) }}</span>
              </template>
              <span v-else class="apagado">{{ t('Target {0} d', [o.lib.meta]) }}</span>
              <span v-if="o.lib.vencidas" class="sub texto-error">{{ t('{0} overdue', [o.lib.vencidas]) }}</span>
            </td>
            <td class="num">{{ tx(o.recoleccion_vs_xf === null ? '—' : `${o.recoleccion_vs_xf > 0 ? '+' : ''}${d(o.recoleccion_vs_xf)}`) }}</td>
            <td class="num">{{ tx(d(o.holgura)) }}<span v-if="o.tarde" class="sub texto-error">{{ t('{0} late', [o.tarde]) }}</span></td>
          </tr>
        </tbody>
      </table>
    </div>
    <div class="leyenda-etapas">
      <span v-for="(e, i) in datos.etapas" :key="e.clave"><i class="punto" :style="{ background: COLOR(i) }"></i>{{ tx(e.nombre) }}</span>
    </div>
    <p class="ayuda" style="margin: 10px 0 0">
      {{ t('Port deadline = in-store date minus the steps after the port arrival in the effective lead time of each PO (Port > Country > Region > Global)') }}
      <template v-for="(r, i) in datos.regiones" :key="r.codigo">{{ tx(tx(i ? ' · ' : ' (')) }}{{ tx(r.nombre) }} {{ tx(r.dias_puerto_bodega) }}+{{ tx(r.dias_ingreso) }}+{{ tx(r.dias_reexportacion) }} d{{ tx(tx(i === datos.regiones.length - 1 ? ')' : '')) }}</template>.
      {{ t('Re-export is not recorded yet: its days are reserved.') }} <router-link v-if="esInterno()" to="/leadtimes" class="enlace">{{ t('See the effective lead time') }}</router-link>
    </p>
  </section>

  <div class="filtros" v-filtros>
    <div class="segmentos" role="group" :aria-label="t('Arrival')">
      <button v-for="[v, txt] in [['', t('All')], ['ATRASO', t('Late')], ['JUSTO', t('At risk')], ['A_TIEMPO', t('On time')]]" :key="v" type="button" class="segmento"
              :aria-pressed="f.riesgo === v" @click="f.riesgo = v; recargar()">{{ tx(txt) }}</button>
    </div>
    <Seleccion v-model="f.lib" :aria-label="t('Logistics release')" @change="recargar">
      <option value="">{{ t('Logistics release: all') }}</option><option value="tarde">{{ t('Released late') }}</option><option value="vencida">{{ t('Overdue, not released') }}</option>
    </Seleccion>
  </div>
  <div class="tabla-marco tabla-fija">
    <table class="tabla" v-tarjetas>
      <thead>
        <tr>
          <th><span class="oculto-visual">{{ t('Open') }}</span></th>
          <ThOrden campo="oc" :orden="tabla.orden" @ordenar="ordenar">{{ t('Purchase order') }}</ThOrden>
          <ThOrden campo="origen" :orden="tabla.orden" @ordenar="ordenar">{{ t('Origin') }}</ThOrden>
          <th>{{ t('Logistics release') }}</th>
          <ThOrden campo="fecha_xf" :orden="tabla.orden" @ordenar="ordenar">XF</ThOrden>
          <ThOrden campo="arribo" :orden="tabla.orden" @ordenar="ordenar">{{ t('Port arrival') }}</ThOrden>
          <ThOrden campo="limite_puerto" :orden="tabla.orden" @ordenar="ordenar">{{ t('Port deadline') }}</ThOrden>
          <ThOrden v-if="ve('fechas_internas')" campo="fecha_tienda" :orden="tabla.orden" @ordenar="ordenar">{{ t('In store') }}</ThOrden>
          <ThOrden v-if="ve('fechas_internas')" campo="tienda_estimada" :orden="tabla.orden" @ordenar="ordenar" :title="t('Estimated: arrival plus port, warehouse entry and re-export days')">{{ t('Est. in store') }}</ThOrden>
          <ThOrden v-if="ve('fechas_internas')" campo="holgura" :orden="tabla.orden" @ordenar="ordenar">{{ t('Early / late') }}</ThOrden>
        </tr>
      </thead>
      <tbody>
        <tr v-if="!datos.items.length"><td colspan="10" class="vacio">{{ tx(cargando ? t('Loading…') : t('No purchase orders match these filters.')) }}</td></tr>
        <template v-for="o in datos.items" :key="o.oc_id">
          <tr class="clicable" @click="alternar(o.oc_id)">
            <td><button type="button" class="btn-icono" :aria-expanded="abiertas.has(o.oc_id)" :aria-label="t('See the milestones of {0}', [o.oc])"><Icono :nombre="abiertas.has(o.oc_id) ? 'abajo' : 'derecha'" :tam="16" /></button></td>
            <td><span class="codigo fuerte">{{ tx(o.oc) }}</span><span class="sub">{{ tx(o.proveedor) }}<template v-if="o.embarques.length"> · {{ tx(o.embarques.join(', ')) }}</template></span></td>
            <td>{{ tx(o.origen_nombre || '—') }}<span class="sub" :title="t('Lead time plan')">{{ tx(o.plan_nombre || o.region_nombre) }}</span></td>
            <td>
              <template v-if="o.lib_dias_antes_xf !== null">
                <span class="etiqueta ms-0" :class="o.lib_a_tiempo ? 'ok' : 'error'">{{ tx(o.lib_a_tiempo ? t('On time') : t('Late')) }}</span>
                <span class="sub">{{ t('{0} d before XF · target {1}', [o.lib_dias_antes_xf, o.dias_liberacion]) }}</span>
              </template>
              <template v-else-if="o.lib_vencida"><span class="etiqueta error ms-0">{{ t('Overdue') }}</span><span class="sub">{{ t('target {0} d before XF', [o.dias_liberacion]) }}</span></template>
              <span v-else class="apagado">{{ t('Pending · target {0} d', [o.dias_liberacion]) }}</span>
            </td>
            <td>{{ fmtFecha(o.fecha_xf) }}</td>
            <td>{{ fmtFecha(o.arribo) }}<span class="sub">{{ o.arribo_real ? t('actual') : t('estimated') }}</span></td>
            <td>{{ fmtFecha(o.limite_puerto) }}</td>
            <td v-if="ve('fechas_internas')">{{ fmtFecha(o.fecha_tienda) }}</td>
            <td v-if="ve('fechas_internas')"><FechaTienda :fecha="o.tienda_estimada" :dias="o.dias_vs_tienda" /></td>
            <td v-if="ve('fechas_internas')">
              <span v-if="o.riesgo" class="etiqueta ms-0" :class="RIESGO[o.riesgo][1]">{{ tx(RIESGO[o.riesgo][0]) }}</span>
              <span class="sub">{{ tx(o.holgura == null ? '—' : o.holgura >= 0 ? t('{0} d to spare', [o.holgura]) : t('{0} d late', [-o.holgura])) }}</span>
            </td>
          </tr>
          <tr v-if="abiertas.has(o.oc_id)" class="fila-hija">
            <td colspan="10">
              <div class="subtabla">
                <ol class="lt-hitos" :aria-label="t('Milestones of {0}', [o.oc])">
                  <li v-for="h in o.hitos" :key="h.clave" :class="`hito-${ESTADO[h.estado][1]}`">
                    <span class="hito-nombre">{{ tx(h.nombre) }}</span>
                    <span class="hito-fecha">{{ tx(h.fecha ? fmtFecha(h.fecha) : h.estimada ? `≈ ${fmtFecha(h.estimada)}` : '—') }}</span>
                    <span class="hito-meta">{{ tx(h.meta ? t('target {0}', [fmtFecha(h.meta)]) : t('&nbsp;')) }}</span>
                    <span class="etiqueta ms-0" :class="ESTADO[h.estado][1]"><Icono :nombre="ESTADO[h.estado][2]" :tam="12" />{{ tx(ESTADO[h.estado][0]) }}<template v-if="difTxt(h)"> · {{ tx(difTxt(h)) }}</template></span>
                  </li>
                </ol>
                <p class="ayuda" style="margin: 8px 0 0">{{ t('≈ estimated from the shipment ETA or the standard days of {0}. In store is estimated after warehouse entry plus re-export (not recorded yet).', [o.plan_nombre || o.region_nombre]) }}</p>
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
.lt-origenes td, .lt-origenes th { padding-inline-start: 8px; padding-inline-end: 8px; }
.lt-origenes th .punto { margin-inline-end: 2px; }
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
