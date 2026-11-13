<script setup>
import { actual, t, tx } from '@/i18n/index.js'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { api } from '@/nucleo/api'
import { fmtMoneda, fmtNum } from '@/nucleo/utils'
import { errorApi } from '@/stores/ui'

// Gráfica del Inicio: comprado contra recibido por mes, en la moneda de la empresa
// (GET /dashboard/compras-recepcion). Dos líneas en un solo eje; al pasar el ratón,
// una guía vertical con los dos valores del mes. Leyenda siempre visible y la
// misma información como tabla (para lectores de pantalla y para copiar).
const MESES = [[12, t('12 months')], [6, t('6 months')], [3, t('3 months')]]
const meses = ref(12)
const d = ref(null)
const verTabla = ref(false)

async function cargar() {
  try {
    d.value = await api.get('/dashboard/compras-recepcion', { meses: meses.value })
  } catch (e) {
    errorApi(e)
  }
}
onMounted(cargar)
watch(meses, cargar)
defineExpose({ cargar })

// ---- Medidas: el ancho sigue al contenedor (las letras no se estiran) ----
const caja = ref(null)
const ancho = ref(720)
let obs = null
onMounted(() => {
  obs = new ResizeObserver(([e]) => (ancho.value = Math.max(280, Math.round(e.contentRect.width))))
  if (caja.value) obs.observe(caja.value)
})
onBeforeUnmount(() => obs?.disconnect())
const ALTO = 220
const M = { arriba: 12, abajo: 26, izq: 52, der: 14 }

const serie = computed(() => d.value?.serie || [])
const nombreMes = (k) => new Intl.DateTimeFormat(actual.locale, { month: 'short', ...(k.endsWith('-01') ? { year: '2-digit' } : {}) })
  .format(new Date(Number(k.slice(0, 4)), Number(k.slice(5)) - 1, 1))
const tope = computed(() => {
  const max = Math.max(0, ...serie.value.flatMap((x) => [x.comprado, x.recibido]))
  if (!max) return 1
  const paso = 10 ** Math.floor(Math.log10(max))
  return Math.ceil(max / paso) * paso
})
const x = (i) => M.izq + (serie.value.length > 1 ? (i * (ancho.value - M.izq - M.der)) / (serie.value.length - 1) : 0)
const y = (v) => M.arriba + (1 - v / tope.value) * (ALTO - M.arriba - M.abajo)
const linea = (campo) => serie.value.map((p, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(p[campo]).toFixed(1)}`).join(' ')
const area = computed(() => (serie.value.length ? `${linea('comprado')} L${x(serie.value.length - 1)},${y(0)} L${x(0)},${y(0)} Z` : ''))
const marcas = computed(() => [0, 0.25, 0.5, 0.75, 1].map((f) => f * tope.value))
const corto = (v) => (v >= 1e6 ? `${fmtNum(v / 1e6, 1)} M` : v >= 1e3 ? `${fmtNum(v / 1e3, 0)} K` : fmtNum(v, 0))
const dinero = (v) => fmtMoneda(v, d.value?.moneda)
const hayDatos = computed(() => serie.value.some((p) => p.comprado || p.recibido))
// Etiquetas del eje x: todas si caben; si no, una sí y otra no
const cadaCuanto = computed(() => (ancho.value / Math.max(1, serie.value.length) < 46 ? 2 : 1))

// ---- Guía al pasar el ratón ----
const foco = ref(null)
function mover(e) {
  const r = e.currentTarget.getBoundingClientRect()
  const px = e.clientX - r.left
  const n = serie.value.length
  if (!n) return
  const i = Math.round(((px - M.izq) / (ancho.value - M.izq - M.der)) * (n - 1))
  foco.value = Math.min(n - 1, Math.max(0, i))
}
</script>

<template>
  <section class="panel grafico-cr" :aria-label="t('Purchased vs. received')">
    <div class="panel-cabeza">
      <div><h2>{{ t('Purchased vs. received') }} <span v-if="d?.moneda" class="ayuda">{{ tx(d.moneda) }}</span></h2></div>
      <div class="fila-flex gap-2">
        <button type="button" class="btn btn-fantasma btn-chico" :aria-pressed="verTabla" @click="verTabla = !verTabla">{{ verTabla ? t('See chart') : t('See as table') }}</button>
        <div class="segmentos" role="group" :aria-label="t('Period')">
          <button v-for="[n, txt] in MESES" :key="n" type="button" class="segmento" :aria-pressed="meses === n" @click="meses = n">{{ tx(txt) }}</button>
        </div>
      </div>
    </div>
    <div class="leyenda" aria-hidden="true">
      <span><i class="l-comprado"></i>{{ t('Purchased') }}</span>
      <span><i class="l-recibido"></i>{{ t('Received') }}</span>
    </div>
    <div v-show="!verTabla" ref="caja" class="grafico-caja">
      <p v-if="d && !hayDatos" class="vacio">{{ t('No approved purchases or receipts in this period.') }}</p>
      <svg v-else-if="d" :width="ancho" :height="ALTO" role="img" :aria-label="t('Purchased vs. received per month')"
           @mousemove="mover" @mouseleave="foco = null">
        <g class="rejilla">
          <g v-for="v in marcas" :key="v">
            <line :x1="M.izq" :x2="ancho - M.der" :y1="y(v)" :y2="y(v)" />
            <text :x="M.izq - 8" :y="y(v) + 4" text-anchor="end">{{ corto(v) }}</text>
          </g>
          <template v-for="(p, i) in serie" :key="p.mes">
            <text v-if="i % cadaCuanto === (serie.length - 1) % cadaCuanto" :x="x(i)" :y="ALTO - 8" text-anchor="middle">{{ nombreMes(p.mes) }}</text>
          </template>
        </g>
        <path class="area" :d="area" />
        <path class="linea comprado" :d="linea('comprado')" />
        <path class="linea recibido" :d="linea('recibido')" />
        <!-- Último mes: punto con anillo del color de la superficie -->
        <template v-if="serie.length">
          <circle class="punto comprado" :cx="x(serie.length - 1)" :cy="y(serie.at(-1).comprado)" r="4" />
          <circle class="punto recibido" :cx="x(serie.length - 1)" :cy="y(serie.at(-1).recibido)" r="4" />
        </template>
        <g v-if="foco !== null" class="guia">
          <line :x1="x(foco)" :x2="x(foco)" :y1="M.arriba" :y2="ALTO - M.abajo" />
          <circle class="punto comprado" :cx="x(foco)" :cy="y(serie[foco].comprado)" r="4" />
          <circle class="punto recibido" :cx="x(foco)" :cy="y(serie[foco].recibido)" r="4" />
        </g>
      </svg>
      <div v-if="foco !== null" class="globo" :style="{ left: `${Math.min(x(foco) + 12, ancho - 190)}px` }" role="status">
        <b>{{ nombreMes(serie[foco].mes) }} {{ serie[foco].mes.slice(0, 4) }}</b>
        <span><i class="l-comprado"></i>{{ t('Purchased') }} <b>{{ dinero(serie[foco].comprado) }}</b></span>
        <span><i class="l-recibido"></i>{{ t('Received') }} <b>{{ dinero(serie[foco].recibido) }}</b></span>
      </div>
    </div>
    <div v-if="verTabla && d" class="tabla-marco">
      <table class="tabla">
        <thead><tr><th>{{ t('Month') }}</th><th class="num">{{ t('Purchased') }}</th><th class="num">{{ t('Received') }}</th></tr></thead>
        <tbody>
          <tr v-for="p in serie" :key="p.mes"><td>{{ nombreMes(p.mes) }} {{ p.mes.slice(0, 4) }}</td>
            <td class="num">{{ dinero(p.comprado) }}</td><td class="num">{{ dinero(p.recibido) }}</td></tr>
        </tbody>
      </table>
    </div>
    <p v-if="d?.otras?.length" class="ayuda">{{ t('Also in other currencies (not in the chart): {0}', [d.otras.map((o) => fmtMoneda(o.valor, o.moneda)).join(' · ')]) }}</p>
  </section>
</template>

<style scoped>
/* Dos series: petróleo (comprado) y ocre (recibido). Separación validada para daltonismo
   (ΔE ≥ 16) y contraste ≥ 3:1 en los dos temas; la leyenda siempre acompaña. */
.grafico-cr { --s-comprado: var(--serie-1); --s-recibido: var(--serie-2); }
.leyenda { display: flex; gap: 16px; font-size: var(--t-sm); color: var(--tinta-2); margin: -6px 0 8px; }
.leyenda span, .globo span { display: inline-flex; align-items: center; gap: 6px; }
.leyenda i, .globo i { width: 14px; height: 2px; border-radius: 2px; display: inline-block; }
.l-comprado { background: var(--s-comprado); }
.l-recibido { background: var(--s-recibido); }
.grafico-caja { position: relative; width: 100%; }
svg { display: block; overflow: visible; }
.rejilla line { stroke: var(--rejilla); stroke-width: 1; }
.rejilla text { fill: var(--eje); font-size: 11px; font-variant-numeric: tabular-nums; }
.area { fill: color-mix(in srgb, var(--s-comprado) 10%, transparent); }
.linea { fill: none; stroke-width: 2; stroke-linejoin: round; stroke-linecap: round; }
.linea.comprado { stroke: var(--s-comprado); }
.linea.recibido { stroke: var(--s-recibido); }
.punto { stroke: var(--superficie); stroke-width: 2; }
.punto.comprado { fill: var(--s-comprado); }
.punto.recibido { fill: var(--s-recibido); }
.guia line { stroke: var(--borde-hover); stroke-width: 1; }
.globo { position: absolute; top: 8px; display: flex; flex-direction: column; gap: 3px; min-width: 176px; padding: 8px 10px; font-size: var(--t-sm);
  background: var(--superficie); border: 1px solid var(--linea); border-radius: var(--radio); box-shadow: var(--sombra-media); pointer-events: none; }
.globo span { justify-content: space-between; color: var(--tinta-2); }
.globo span b { margin-inline-start: auto; color: var(--tinta); font-variant-numeric: tabular-nums; }
</style>
