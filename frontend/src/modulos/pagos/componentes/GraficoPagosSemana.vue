<script setup>
import { actual, t, tx } from '@/i18n/index.js'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { fmtMoneda, fmtNum } from '@/nucleo/utils'

// Pagos de las próximas semanas en columnas agrupadas: lo programado y lo que
// vence sin programar (lo ya vencido cae en la semana actual). Un solo eje, en
// la moneda de la empresa. Leyenda siempre visible, globo al pasar el ratón o
// enfocar una semana, y la misma información como tabla.
const props = defineProps({ resumen: { type: Object, default: null } })
const verTabla = ref(false)

const caja = ref(null)
const ancho = ref(640)
let obs = null
onMounted(() => {
  obs = new ResizeObserver(([e]) => (ancho.value = Math.max(280, Math.round(e.contentRect.width))))
  if (caja.value) obs.observe(caja.value)
})
onBeforeUnmount(() => obs?.disconnect())
const ALTO = 200
const M = { arriba: 12, abajo: 26, izq: 52, der: 8 }

const semanas = computed(() => props.resumen?.semanas || [])
const SERIES = [['programado', t('Scheduled')], ['sin_programar', t('Due, not scheduled')]]
const tope = computed(() => {
  const max = Math.max(0, ...semanas.value.flatMap((s) => [s.programado, s.sin_programar]))
  if (!max) return 1
  const paso = 10 ** Math.floor(Math.log10(max))
  return Math.ceil(max / paso) * paso
})
const banda = computed(() => (ancho.value - M.izq - M.der) / Math.max(1, semanas.value.length))
// Columnas delgadas (≤ 18 px) con 2 px de separación entre las dos del grupo
const barra = computed(() => Math.min(18, Math.max(6, banda.value * 0.22)))
const xBarra = (i, j) => M.izq + banda.value * (i + 0.5) + (j === 0 ? -barra.value - 1 : 1)
const y = (v) => M.arriba + (1 - v / tope.value) * (ALTO - M.arriba - M.abajo)
// Columna con las esquinas de arriba redondeadas (4 px) y apoyada en la base
function columna(x, v) {
  const y0 = y(0)
  const alto = Math.max(0, y0 - y(v))
  if (!alto) return ''
  const r = Math.min(4, alto, barra.value / 2)
  const w = barra.value
  return `M${x},${y0} V${y0 - alto + r} Q${x},${y0 - alto} ${x + r},${y0 - alto} H${x + w - r} Q${x + w},${y0 - alto} ${x + w},${y0 - alto + r} V${y0} Z`
}
const marcas = computed(() => [0, 0.25, 0.5, 0.75, 1].map((f) => f * tope.value))
const corto = (v) => (v >= 1e6 ? `${fmtNum(v / 1e6, 1)} M` : v >= 1e3 ? `${fmtNum(v / 1e3, 0)} K` : fmtNum(v, 0))
const dinero = (v) => fmtMoneda(v, props.resumen?.moneda)
const fecha = (s) => new Intl.DateTimeFormat(actual.locale, { day: 'numeric', month: 'short' }).format(new Date(`${s}T00:00:00`))
const hayDatos = computed(() => semanas.value.some((s) => s.programado || s.sin_programar))
const foco = ref(null)
</script>

<template>
  <section class="panel grafico-pagos" :aria-label="t('Payments per week')">
    <div class="panel-cabeza">
      <h2>{{ t('Payments per week') }} <span v-if="resumen?.moneda" class="ayuda">{{ tx(resumen.moneda) }}</span></h2>
      <button type="button" class="btn btn-fantasma btn-chico" :aria-pressed="verTabla" @click="verTabla = !verTabla">{{ verTabla ? t('See chart') : t('See as table') }}</button>
    </div>
    <div class="leyenda" aria-hidden="true">
      <span v-for="[k, txt] in SERIES" :key="k"><i :class="`c-${k}`"></i>{{ txt }}</span>
    </div>
    <div v-show="!verTabla" ref="caja" class="grafico-caja" @mouseleave="foco = null">
      <p v-if="resumen && !hayDatos" class="vacio">{{ t('Nothing to pay in the coming weeks.') }}</p>
      <svg v-else-if="resumen" :width="ancho" :height="ALTO" role="img" :aria-label="t('Payments per week')">
        <g class="rejilla">
          <g v-for="v in marcas" :key="v">
            <line :x1="M.izq" :x2="ancho - M.der" :y1="y(v)" :y2="y(v)" />
            <text :x="M.izq - 8" :y="y(v) + 4" text-anchor="end">{{ corto(v) }}</text>
          </g>
        </g>
        <g v-for="(s, i) in semanas" :key="s.inicio" class="grupo" tabindex="0" :aria-label="`${fecha(s.inicio)}: ${t('Scheduled')} ${dinero(s.programado)}, ${t('Due, not scheduled')} ${dinero(s.sin_programar)}`"
           @mouseenter="foco = i" @focus="foco = i" @blur="foco = null">
          <!-- Área de contacto: toda la banda de la semana -->
          <rect class="zona" :x="M.izq + banda * i" :y="M.arriba" :width="banda" :height="ALTO - M.arriba - M.abajo" />
          <path v-for="([k], j) in SERIES" :key="k" :class="`c-${k}`" :d="columna(xBarra(i, j), s[k])" />
          <text class="eje-x" :x="M.izq + banda * (i + 0.5)" :y="ALTO - 8" text-anchor="middle">{{ i === 0 && banda > 72 ? t('This week') : fecha(s.inicio) }}</text>
        </g>
      </svg>
      <div v-if="foco !== null && semanas[foco]" class="globo" :style="{ left: `${Math.min(M.izq + banda * (foco + 0.5) + 14, ancho - 200)}px` }" role="status">
        <b>{{ t('Week of {0}', [fecha(semanas[foco].inicio)]) }}</b>
        <span v-for="[k, txt] in SERIES" :key="k"><i :class="`c-${k}`"></i>{{ txt }} <b>{{ dinero(semanas[foco][k]) }}</b></span>
      </div>
    </div>
    <div v-if="verTabla && resumen" class="tabla-marco">
      <table class="tabla">
        <thead><tr><th>{{ t('Week') }}</th><th v-for="[k, txt] in SERIES" :key="k" class="num">{{ txt }}</th></tr></thead>
        <tbody>
          <tr v-for="s in semanas" :key="s.inicio"><td>{{ fecha(s.inicio) }}</td>
            <td v-for="[k] in SERIES" :key="k" class="num">{{ dinero(s[k]) }}</td></tr>
        </tbody>
      </table>
    </div>
  </section>
</template>

<style scoped>
/* Mismas dos series que el Inicio: petróleo (programado) y ocre (sin programar);
   separación validada para daltonismo, con leyenda y tabla siempre disponibles. */
.leyenda { display: flex; gap: 16px; font-size: var(--t-sm); color: var(--tinta-2); margin: -6px 0 8px; }
.leyenda span, .globo span { display: inline-flex; align-items: center; gap: 6px; }
.leyenda i, .globo i { width: 10px; height: 10px; border-radius: 3px; display: inline-block; }
.c-programado { fill: var(--serie-1); background: var(--serie-1); }
.c-sin_programar { fill: var(--serie-2); background: var(--serie-2); }
.grafico-caja { position: relative; width: 100%; min-width: 0; overflow: hidden; }
svg { display: block; overflow: visible; }
.rejilla line { stroke: var(--rejilla); stroke-width: 1; }
.rejilla text, .eje-x { fill: var(--eje); font-size: 11px; font-variant-numeric: tabular-nums; }
.zona { fill: transparent; }
.grupo:hover .zona, .grupo:focus .zona { fill: color-mix(in srgb, var(--tinta) 4%, transparent); }
.grupo:focus { outline: none; }
.globo { position: absolute; top: 8px; display: flex; flex-direction: column; gap: 3px; min-width: 190px; padding: 8px 10px; font-size: var(--t-sm);
  background: var(--superficie); border: 1px solid var(--linea); border-radius: var(--radio); box-shadow: var(--sombra-media); pointer-events: none; }
.globo span { justify-content: space-between; color: var(--tinta-2); }
.globo span b { margin-inline-start: auto; color: var(--tinta); font-variant-numeric: tabular-nums; }
.vacio { color: var(--tinta-3); padding: 40px 0; text-align: center; }
</style>
