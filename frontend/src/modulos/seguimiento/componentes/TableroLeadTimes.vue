<script setup>
import { t, tx } from '@/i18n/index.js'
import FechaTienda from '@/componentes/FechaTienda.vue'
import { computed, reactive, ref, watch } from 'vue'
import Seleccion from '@/componentes/Seleccion.vue'
import { api } from '@/nucleo/api'
import { esInterno, sesion, ve } from '@/stores/sesion'
import { errorApi } from '@/stores/ui'
import { TIEMPO, fmtFecha, fmtNum } from '@/nucleo/utils'
import FiltroMulti from '@/componentes/FiltroMulti.vue'
import FiltroPeriodo, { rango } from '@/componentes/FiltroPeriodo.vue'
import Icono from '@/componentes/Icono.vue'
import Kpi from '@/componentes/Kpi.vue'
import TablaDatos from '@/componentes/TablaDatos.vue'
import Segmentos from '@/componentes/Segmentos.vue'

// Lead times por origen: cuánto tarda en promedio cada etapa (de la OC al
// ingreso en bodega), si logística libera a tiempo antes de la XF (Asia 21
// días, el resto 15) y, por OC, cada hito contra su meta. La llegada se mide
// contra la fecha límite en puerto: la fecha en tienda menos los días a la
// bodega, el ingreso y la reexportación de su región.
const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
const [d0, d1] = rango('12m')
const periodo = ref({ clave: '12m', desde: iso(d0), hasta: iso(d1) })
const f = reactive({ origen: [], region: [], proveedor: [], riesgo: '', lib: '' })
const tablaLT = ref(null)
const datos = ref({ items: [], total: 0, kpis: {}, origenes: [], etapas: [], regiones: [], opciones: {} })
const cargando = ref(true)

const COLOR = (i) => `var(--etapa-${i + 1})`
const ESTADO = {
  a_tiempo: [t('On time'), 'ok', 'check'], hecho: [t('Done'), 'neutro', 'check'], tarde: [t('Late'), 'error', 'alerta'],
  vencido: [t('Overdue'), 'error', 'reloj'], riesgo: [t('At risk'), 'aviso', 'alerta'], en_plan: [t('On plan'), 'info', 'reloj'],
  pendiente: [t('Pending'), 'neutro', 'reloj'],
}
const RIESGO = TIEMPO
// Meta de liberación a tiempo de la empresa (Configuración → Empresa → Reglas)
const meta = computed(() => sesion.usuario?.config?.meta_liberacion ?? 80)

const base = () => ({
  desde: periodo.value.desde, hasta: periodo.value.hasta, origen: f.origen.join(','), region: f.region.join(','),
  proveedor: f.proveedor.join(','), riesgo: f.riesgo, lib: f.lib, proveedor_id: sesion.proveedorId || undefined,
})
// La lista de OCs filtra cada columna por sus valores en el servidor (/seguimiento/leadtimes/valores)
let ultima = null
async function cargar(c = ultima) {
  if (!c) return
  ultima = c
  cargando.value = true
  try {
    datos.value = await api.get('/seguimiento/leadtimes', { ...base(), orden: c.orden || 'fecha_xf:asc', page: c.page, size: c.size,
      f: Object.keys(c.filtros).length ? JSON.stringify(c.filtros) : undefined })
  } catch (e) {
    errorApi(e)
  } finally {
    cargando.value = false
  }
}
const valores = (columna, buscar, otros) => api.get('/seguimiento/leadtimes/valores', { ...base(), columna, buscar, f: JSON.stringify(otros) })
function recargar() {
  if (tablaLT.value && tablaLT.value.pagina !== 1) tablaLT.value.pagina = 1
  else cargar()
}
const LIB = [['a_tiempo', t('On time')], ['tarde', t('Late')], ['vencida', t('Overdue')], ['pendiente', t('Pending')]]
const columnas = computed(() => [
  { clave: 'oc', texto: t('Purchase order'), fija: true, prioridad: 1 },
  { clave: 'proveedor', texto: t('Supplier'), prioridad: 3, inicial: false },
  { clave: 'origen', texto: t('Origin'), prioridad: 2 },
  { clave: 'lib', texto: t('Logistics release'), prioridad: 2, ordenable: false, opciones: LIB },
  { clave: 'fecha_xf', texto: 'XF', prioridad: 2, textoValor: (v) => fmtFecha(v) },
  { clave: 'arribo', texto: t('Port arrival'), prioridad: 3, textoValor: (v) => fmtFecha(v) },
  { clave: 'limite_puerto', texto: t('Port deadline'), prioridad: 3, textoValor: (v) => fmtFecha(v) },
  { clave: 'fecha_tienda', texto: t('In store'), grupo: 'fechas_internas', prioridad: 3, textoValor: (v) => fmtFecha(v) },
  { clave: 'tienda_estimada', texto: t('Est. in store'), grupo: 'fechas_internas', prioridad: 3, textoValor: (v) => fmtFecha(v) },
  { clave: 'holgura', texto: t('Early / late'), grupo: 'fechas_internas', prioridad: 2, opciones: Object.entries(RIESGO).map(([k, [txt]]) => [k, txt]) },
])
// Resumen por origen: una fila por origen con el promedio de cada etapa
const columnasOrigen = computed(() => [
  { clave: 'nombre', texto: t('Origin'), fija: true, prioridad: 1 },
  { clave: 'ocs', texto: t('POs'), num: true, prioridad: 1 },
  { clave: 'barra', texto: t('Lead time'), prioridad: 2, filtro: false, ordenable: false },
  ...datos.value.etapas.map((e, i) => ({ clave: `e_${e.clave}`, texto: e.nombre, corto: String(i + 1), num: true, prioridad: 3, valor: (o) => o.etapas[e.clave]?.prom ?? null, textoValor: (v) => d(v) })),
  { clave: 'total_prom', texto: t('Total'), num: true, prioridad: 1, textoValor: (v) => d(v) },
  { clave: 'lib', texto: t('Release vs XF'), prioridad: 2, valor: (o) => (o.lib.total ? o.lib.pct : null), textoValor: (v) => `${v}%` },
  { clave: 'recoleccion_vs_xf', texto: t('Pickup vs XF'), num: true, prioridad: 3, textoValor: (v) => d(v) },
  { clave: 'holgura', texto: t('Slack at port'), num: true, prioridad: 3, textoValor: (v) => d(v) },
])
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
// Hitos de una OC en orden, agrupados por el documento que los cumple (la OC,
// la lista de empaque, el embarque…) cuando van seguidos
const DOCUMENTO = { OC: t('Purchase order'), FACTURA: t('Invoice'), PL: t('Packing list'), EMBARQUE: t('Shipment') }
function grupos(hitos) {
  const out = []
  hitos.forEach((h, i) => {
    const ultimo = out[out.length - 1]
    if (ultimo && ultimo.doc === h.documento) ultimo.hitos.push({ ...h, n: i + 1 })
    else out.push({ doc: h.documento, hitos: [{ ...h, n: i + 1 }] })
  })
  return out
}
const reglas = computed(() => datos.value.regiones.map((r) => `${r.nombre} ${r.dias_liberacion} d`).join(' · '))

watch(() => [periodo.value, sesion.proveedorId], recargar, { deep: true })
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
    <Kpi :titulo="t('Logistics release on time')" :valor="datos.kpis.lib_pct" formato="porcentaje" icono="check"
         :tono="datos.kpis.lib_pct == null ? 'normal' : datos.kpis.lib_pct >= meta ? 'exito' : 'alerta'"
         :detalle="t('{0} of {1} released on time · target {2}%', [datos.kpis.lib_a_tiempo || 0, datos.kpis.lib_total || 0, meta])" :title="t('Target before XF: {0}', [reglas || '—'])" @abrir="f.lib = f.lib === 'tarde' ? '' : 'tarde'; recargar()" />
    <Kpi :titulo="t('Release overdue')" :valor="datos.kpis.lib_vencidas ?? 0" icono="reloj" :tono="datos.kpis.lib_vencidas ? 'alerta' : 'exito'"
         :detalle="t('not released and the target date passed')" @abrir="f.lib = f.lib === 'vencida' ? '' : 'vencida'; recargar()" />
    <Kpi :titulo="t('Average lead time')" :valor="datos.kpis.total_prom" formato="dias" icono="grafica"
         :detalle="t('PO created to warehouse entry · transit {0}', [d(datos.kpis.transito_prom)])" />
    <Kpi v-if="ve('fechas_internas')" :titulo="t('Late for the port deadline')" :valor="datos.kpis.tarde ?? 0" icono="alerta" :tono="datos.kpis.tarde ? 'alerta' : 'exito'"
         :detalle="t('{0} at risk', [datos.kpis.justo || 0])" @abrir="f.riesgo = f.riesgo === 'ATRASO' ? '' : 'ATRASO'; recargar()" />
  </section>

  <section class="panel mb-4">
    <div class="panel-cabeza">
      <div>
        <h2>{{ t('Average days per stage, by origin') }}</h2>
      </div>
    </div>
    <TablaDatos tabla="leadtimes_origenes" :columnas="columnasOrigen" :filas="datos.origenes" clave-fila="origen" :cargando="cargando" :vistas-guardadas="false"
                :etiqueta="t('Average days per stage, by origin')">
      <template #celda-nombre="{ fila: o }"><span class="fuerte">{{ tx(o.nombre) }}</span><span class="sub">{{ tx(o.origen) }} · {{ tx(o.region_nombre) }}</span></template>
      <template #celda-barra="{ fila: o }">
        <div class="lt-barra">
          <div v-if="segmentos(o).length" class="apilada" :style="{ width: `${Math.max(12, (segmentos(o).reduce((a, s) => a + s.prom, 0) * 100) / maxTotal)}%` }"
               role="img" :aria-label="tx(segmentos(o).map((s) => `${s.nombre}: ${d(s.prom)}`).join(', '))">
            <span v-for="s in segmentos(o)" :key="s.clave" :style="{ flex: s.prom, background: COLOR(s.i) }" :title="t('{0}: {1} ({2} POs)', [`${s.i + 1}. ${s.nombre}`, d(s.prom), s.n])">{{ s.prom / segmentos(o).reduce((a, x) => a + x.prom, 0) >= 0.09 ? s.i + 1 : '' }}</span>
          </div>
          <span v-else class="apagado">{{ t('No stage completed yet') }}</span>
        </div>
      </template>
      <template v-for="(e, i) in datos.etapas" :key="e.clave" #[`celda-e_${e.clave}`]="{ fila: o }">
        <span :title="tx(o.etapas[e.clave].n ? t('{0} POs', [o.etapas[e.clave].n]) : t('No data yet'))"><i class="punto" :style="{ background: COLOR(i) }"></i> {{ tx(d(o.etapas[e.clave].prom)) }}</span>
      </template>
      <template #celda-total_prom="{ fila: o }"><span class="fuerte" :title="tx(o.completas ? t('{0} POs with every stage', [o.completas]) : t('No PO has every stage yet'))">{{ tx(d(o.total_prom)) }}</span></template>
      <template #celda-lib="{ fila: o }">
        <template v-if="o.lib.total">
          <span class="etiqueta ms-0" :class="o.lib.pct >= meta ? 'ok' : 'error'">{{ t('{0}% on time', [o.lib.pct]) }}</span>
          <span class="sub">{{ t('avg {0} before · target {1} d', [d(o.lib.dias_antes_xf), o.lib.meta]) }}</span>
        </template>
        <span v-else class="apagado">{{ t('Target {0} d', [o.lib.meta]) }}</span>
        <span v-if="o.lib.vencidas" class="sub texto-error">{{ t('{0} overdue', [o.lib.vencidas]) }}</span>
      </template>
      <template #celda-recoleccion_vs_xf="{ fila: o }">{{ tx(o.recoleccion_vs_xf === null ? '—' : `${o.recoleccion_vs_xf > 0 ? '+' : ''}${d(o.recoleccion_vs_xf)}`) }}</template>
      <template #celda-holgura="{ fila: o }">{{ tx(d(o.holgura)) }}<span v-if="o.tarde" class="sub texto-error">{{ t('{0} late', [o.tarde]) }}</span></template>
      <template #vacio>{{ t('No purchase orders in this period.') }}</template>
    </TablaDatos>
    <div class="leyenda-etapas">
      <span v-for="(e, i) in datos.etapas" :key="e.clave"><b class="num-etapa" :style="{ background: COLOR(i) }">{{ i + 1 }}</b>{{ tx(e.nombre) }}</span>
    </div>
    <details class="ayuda mt-chico">
      <summary>{{ t('How the port deadline is calculated') }}</summary>
      {{ t('Port deadline = in-store date minus the steps after the port arrival in the effective lead time of each PO (Port > Country > Region > Global)') }}
      <template v-for="(r, i) in datos.regiones" :key="r.codigo">{{ tx(tx(i ? ' · ' : ' (')) }}{{ tx(r.nombre) }} {{ tx(r.dias_puerto_bodega) }}+{{ tx(r.dias_ingreso) }}+{{ tx(r.dias_reexportacion) }} d{{ tx(tx(i === datos.regiones.length - 1 ? ')' : '')) }}</template>.
      <router-link v-if="esInterno()" to="/leadtimes" class="enlace">{{ t('See the effective lead time') }}</router-link>
    </details>
  </section>

  <TablaDatos ref="tablaLT" tabla="leadtimes_ocs" modo="servidor" :columnas="columnas" :filas="datos.items" :total="datos.total" :cargando="cargando"
              clave-fila="oc_id" :valores="valores" expandible :externos="{ riesgo: f.riesgo, lib: f.lib }" :etiqueta="t('Purchase orders')"
              @consulta="cargar" @vista="(x) => { Object.assign(f, { riesgo: x.riesgo || '', lib: x.lib || '' }); recargar() }"
              @limpiar-externos="Object.assign(f, { riesgo: '', lib: '' }); recargar()">
    <template #filtros>
      <Segmentos v-model="f.riesgo" :opciones="[['', t('All')], ['ATRASO', t('Late')], ['JUSTO', t('At risk')], ['A_TIEMPO', t('On time')]]" :etiqueta="t('Arrival')" @change="recargar()" />
      <Seleccion v-model="f.lib" :aria-label="t('Logistics release')" @change="recargar">
        <option value="">{{ t('Logistics release: all') }}</option><option value="tarde">{{ t('Released late') }}</option><option value="vencida">{{ t('Overdue, not released') }}</option>
      </Seleccion>
    </template>
    <template #celda-oc="{ fila: o }"><span class="codigo fuerte">{{ tx(o.oc) }}</span><span class="sub">{{ tx(o.proveedor) }}<template v-if="o.embarques.length"> · {{ tx(o.embarques.join(', ')) }}</template></span></template>
    <template #celda-origen="{ fila: o }">{{ tx(o.origen_nombre || '—') }}<span class="sub" :title="t('Lead time plan')">{{ tx(o.plan_nombre || o.region_nombre) }}</span></template>
    <template #celda-lib="{ fila: o }">
      <template v-if="o.lib_dias_antes_xf !== null">
        <span class="etiqueta ms-0" :class="o.lib_a_tiempo ? 'ok' : 'error'">{{ tx(o.lib_a_tiempo ? t('On time') : t('Late')) }}</span>
        <span class="sub">{{ t('{0} d before XF · target {1}', [o.lib_dias_antes_xf, o.dias_liberacion]) }}</span>
      </template>
      <template v-else-if="o.lib_vencida"><span class="etiqueta error ms-0">{{ t('Overdue') }}</span><span class="sub">{{ t('target {0} d before XF', [o.dias_liberacion]) }}</span></template>
      <span v-else class="apagado">{{ t('Pending · target {0} d', [o.dias_liberacion]) }}</span>
    </template>
    <template #celda-fecha_xf="{ fila: o }">{{ fmtFecha(o.fecha_xf) }}</template>
    <template #celda-arribo="{ fila: o }">{{ fmtFecha(o.arribo) }}<span class="sub">{{ o.arribo_real ? t('actual') : t('estimated') }}</span></template>
    <template #celda-limite_puerto="{ fila: o }">{{ fmtFecha(o.limite_puerto) }}</template>
    <template #celda-fecha_tienda="{ fila: o }">{{ fmtFecha(o.fecha_tienda) }}</template>
    <template #celda-tienda_estimada="{ fila: o }"><FechaTienda :fecha="o.tienda_estimada" :dias="o.dias_vs_tienda" /></template>
    <template #celda-holgura="{ fila: o }">
      <span v-if="o.riesgo" class="etiqueta ms-0" :class="RIESGO[o.riesgo][1]">{{ tx(RIESGO[o.riesgo][0]) }}</span>
      <span class="sub">{{ tx(o.holgura == null ? '—' : o.holgura >= 0 ? t('{0} d to spare', [o.holgura]) : t('{0} d late', [-o.holgura])) }}</span>
    </template>
    <template #detalle="{ fila: o }">
      <div class="lt-grupos" :aria-label="t('Milestones of {0}', [o.oc])">
        <section v-for="(g, gi) in grupos(o.hitos)" :key="gi" class="lt-grupo" :style="{ flexGrow: g.hitos.length }">
          <h4>{{ tx(DOCUMENTO[g.doc] || g.doc) }}</h4>
          <ol :style="{ '--n': g.hitos.length }">
            <li v-for="h in g.hitos" :key="h.clave" :class="`hito-${ESTADO[h.estado][1]}`"
                :title="tx([h.nombre, h.meta ? t('target {0}', [fmtFecha(h.meta)]) : '', ESTADO[h.estado][0], difTxt(h)].filter(Boolean).join(' · '))">
              <span class="h-num">{{ h.n }}</span>
              <span class="h-nombre">{{ tx(h.nombre) }}</span>
              <span class="h-fecha">{{ tx(h.fecha ? fmtFecha(h.fecha) : h.estimada ? `≈ ${fmtFecha(h.estimada)}` : '—') }}</span>
              <span class="h-estado"><Icono :nombre="ESTADO[h.estado][2]" :tam="11" />{{ tx(difTxt(h) || ESTADO[h.estado][0]) }}</span>
            </li>
          </ol>
        </section>
      </div>
      <p class="ayuda mt-chico">{{ t('≈ estimated · plan {0}', [o.plan_nombre || o.region_nombre]) }}</p>
    </template>
    <template #vacio>{{ t('No purchase orders match these filters.') }}</template>
  </TablaDatos>
</template>

<style scoped>
.lt-barra { min-width: 150px; }
.lt-origenes td { white-space: nowrap; }
/* En pantallas angostas las etapas se leen en la barra (con su detalle al pasar el cursor) */
@media (max-width: 1360px) { .col-etapa { display: none; } }
.lt-origenes th { white-space: normal; vertical-align: bottom; min-width: 64px; line-height: 1.25; font-size: var(--t-2xs); }
.lt-origenes th .punto { margin-inline-end: 2px; }
.lt-barra .apilada { height: 16px; border-radius: 8px; line-height: 1; }
.apilada > span { display: grid; place-items: center; color: #fff; font-size: var(--t-2xs); font-weight: 700; overflow: hidden; }
.num-etapa { display: inline-grid; place-items: center; width: 17px; height: 17px; border-radius: 50%; color: #fff; font-size: var(--t-2xs); margin-inline-end: 5px; }
details.ayuda summary { cursor: pointer; color: var(--tinta-2); font-weight: 600; }
details.ayuda[open] summary { margin-bottom: 4px; }
/* Hitos de la OC: una barra de pasos numerados que cabe en el ancho del
   detalle, agrupada por el documento que cumple cada paso */
.lt-grupos { display: flex; gap: 10px; min-width: 0; }
.lt-grupo { flex: 1 1 0; min-width: 0; }
.lt-grupo h4 { font-size: var(--t-2xs); text-transform: uppercase; letter-spacing: 0.05em; color: var(--tinta-3); font-weight: 700;
  padding-bottom: 4px; margin-bottom: 8px; border-bottom: 2px solid var(--linea); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.lt-grupo ol { list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: repeat(var(--n), minmax(0, 1fr)); gap: 4px; }
.lt-grupo li { --c: var(--tinta-3); position: relative; display: flex; flex-direction: column; gap: 1px; min-width: 0; font-size: var(--t-xs); }
.lt-grupo li.hito-ok { --c: var(--ok); }
.lt-grupo li.hito-error { --c: var(--error); }
.lt-grupo li.hito-aviso { --c: var(--aviso); }
.lt-grupo li.hito-info { --c: var(--azul); }
.lt-grupo li::before { content: ''; position: absolute; top: 10px; inset-inline: 22px -4px; height: 2px; background: var(--linea); }
.lt-grupo li:last-child::before { display: none; }
.h-num { width: 22px; height: 22px; border-radius: 50%; display: grid; place-items: center; font-size: var(--t-2xs); font-weight: 700; color: #fff; background: var(--c); margin-bottom: 3px; position: relative; }
.hito-neutro .h-num { background: var(--superficie); color: var(--tinta-2); box-shadow: inset 0 0 0 2px var(--linea); }
.h-nombre { color: var(--tinta-2); font-weight: 600; font-size: var(--t-xs); line-height: 1.25; overflow: hidden; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; min-height: 2.5em; }
.h-fecha { font-weight: 700; font-variant-numeric: tabular-nums; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.h-estado { display: inline-flex; align-items: center; gap: 3px; color: var(--c); font-size: var(--t-2xs); font-weight: 650; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.hito-neutro .h-estado { color: var(--tinta-3); }
@media (max-width: 900px) {
  .lt-grupos { flex-direction: column; gap: 8px; }
  .lt-grupo ol { grid-template-columns: 1fr; gap: 6px; }
  .lt-grupo li { display: grid; grid-template-columns: 22px minmax(0, 1fr) auto; column-gap: 8px; align-items: center; }
  .lt-grupo li::before { display: none; }
  .h-num { margin: 0; grid-row: span 2; }
  .h-nombre { min-height: 0; -webkit-line-clamp: 1; }
  .h-fecha { grid-column: 3; grid-row: 1; text-align: end; }
  .h-estado { grid-column: 2 / 4; }
}
</style>
