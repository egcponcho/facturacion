<script setup>
import { tx } from '../i18n/index.js'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { fmtNum } from '../utils'

// Una serie en columnas (magnitud en el tiempo). Tooltip al pasar el
// cursor o enfocar cada columna; la tabla equivalente queda para lectores.
const props = defineProps({
  datos: { type: Array, required: true }, // [{ etiqueta, valor, detalle }]
  formato: { type: Function, default: (v) => fmtNum(v) },
  titulo: { type: String, default: '' },
})

// El ancho del SVG sigue al contenedor para que el texto no se escale
const marco = ref(null)
const ANCHO_REF = ref(560)
const ALTO = 220
let observador
onMounted(() => {
  observador = new ResizeObserver(([e]) => (ANCHO_REF.value = Math.max(280, Math.round(e.contentRect.width))))
  observador.observe(marco.value)
})
onBeforeUnmount(() => observador?.disconnect())
const M = { arriba: 16, derecha: 8, abajo: 26, izquierda: 52 }
// Con muchas columnas se rotula una de cada n para que las etiquetas no se encimen
const cadaN = computed(() => Math.max(1, Math.ceil(props.datos.length / Math.max(1, Math.floor((ANCHO_REF.value - 60) / 58)))))
const activo = ref(null)

// Máximo "limpio" para las marcas del eje: 1, 2, 2.5 o 5 × 10^n
const escala = computed(() => {
  const max = Math.max(0, ...props.datos.map((d) => d.valor))
  if (!max) return { max: 1, marcas: [0] }
  const bruto = max / 4
  const pot = 10 ** Math.floor(Math.log10(bruto))
  let paso = [1, 2, 2.5, 5, 10].map((m) => m * pot).find((p) => p >= bruto)
  // Conteos: marcas en números enteros (nunca 0.25 contenedores)
  if (props.datos.every((d) => Number.isInteger(d.valor))) paso = Math.max(1, Math.ceil(paso))
  const tope = Math.ceil(max / paso) * paso
  const marcas = []
  for (let v = 0; v <= tope + 1e-9; v += paso) marcas.push(v)
  return { max: tope, marcas }
})

const alto = ALTO - M.arriba - M.abajo
const y = (v) => M.arriba + alto - (v / escala.value.max) * alto
const banda = computed(() => (ANCHO_REF.value - M.izquierda - M.derecha) / Math.max(1, props.datos.length))
const anchoCol = computed(() => Math.min(28, banda.value * 0.55))

// Columna con esquinas de 4px arriba y base recta
function camino(d, i) {
  const h = Math.max(0, (d.valor / escala.value.max) * alto)
  if (!h) return ''
  const x = M.izquierda + banda.value * i + (banda.value - anchoCol.value) / 2
  const r = Math.min(4, h, anchoCol.value / 2)
  const base = M.arriba + alto
  const w = anchoCol.value
  return `M${x},${base}V${base - h + r}Q${x},${base - h} ${x + r},${base - h}H${x + w - r}Q${x + w},${base - h} ${x + w},${base - h + r}V${base}Z`
}
const centro = (i) => M.izquierda + banda.value * i + banda.value / 2
const compacto = (v) => (v >= 1e6 ? `${fmtNum(v / 1e6, 1)} M` : v >= 1e3 ? `${fmtNum(v / 1e3, v >= 1e4 ? 0 : 1)} K` : fmtNum(v))
const posTooltip = computed(() => {
  if (activo.value === null) return null
  const d = props.datos[activo.value]
  return { left: `${(centro(activo.value) / ANCHO_REF.value) * 100}%`, top: `${(y(d.valor) / ALTO) * 100}%`, d }
})
</script>

<template>
  <div ref="marco" class="grafica" @mouseleave="activo = null">
    <svg :viewBox="`0 0 ${ANCHO_REF} ${ALTO}`" :height="ALTO" role="img" :aria-label="tx(props.titulo)">
      <g>
        <template v-for="m in escala.marcas" :key="m">
          <line :class="m === 0 ? 'base' : 'rejilla'" :x1="M.izquierda" :x2="ANCHO_REF - M.derecha" :y1="y(m)" :y2="y(m)" />
          <text class="eje" :x="M.izquierda - 8" :y="y(m) + 4" text-anchor="end">{{ tx(compacto(m)) }}</text>
        </template>
      </g>
      <g v-for="(d, i) in props.datos" :key="d.etiqueta">
        <path class="columna" :class="{ apagada: activo !== null && activo !== i }" :d="camino(d, i)" />
        <text v-if="i % cadaN === 0" class="eje" :x="centro(i)" :y="ALTO - 8" text-anchor="middle">{{ tx(d.etiqueta) }}</text>
        <rect class="zona" :x="M.izquierda + banda * i" :y="M.arriba" :width="banda" :height="alto" tabindex="0"
              :aria-label="tx(`${d.etiqueta}: ${props.formato(d.valor)}`)" @mouseenter="activo = i" @focus="activo = i" @blur="activo = null" />
      </g>
    </svg>
    <div v-if="posTooltip" class="info-flotante" :style="{ left: posTooltip.left, top: posTooltip.top }">
      <b>{{ tx(props.formato(posTooltip.d.valor)) }}</b>{{ tx(posTooltip.d.etiqueta) }}<template v-if="posTooltip.d.detalle"> · {{ tx(posTooltip.d.detalle) }}</template>
    </div>
    <table class="oculto-visual">
      <caption>{{ tx(props.titulo) }}</caption>
      <tr v-for="d in props.datos" :key="d.etiqueta"><th>{{ tx(d.etiqueta) }}</th><td>{{ tx(props.formato(d.valor)) }}</td></tr>
    </table>
  </div>
</template>
