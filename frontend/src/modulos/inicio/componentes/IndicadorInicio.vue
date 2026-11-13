<script setup>
import { t, tx } from '@/i18n/index.js'
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import Tendencia from '@/componentes/Tendencia.vue'
import { fmtFecha, fmtNum } from '@/nucleo/utils'

// Un indicador del Inicio (tableros/inicio): nombre, cifra, cómo va frente al
// período anterior o a la meta, y su tendencia. Toda la tarjeta abre la lista
// que lo explica.
const props = defineProps({
  i: { type: Object, required: true }, // indicador calculado (indicadores.tablero)
  def: { type: Object, required: true }, // su definición (catálogo: título, formato, mejor)
  monedaBase: { type: String, default: '' },
})
const router = useRouter()

const cifra = (v) => {
  if (v === null || v === undefined) return '—'
  const dec = Number.isInteger(Number(v)) ? 0 : 1
  const f = props.def.formato
  if (f === 'moneda') {
    const n = Math.abs(v) >= 1e6 ? `${fmtNum(v / 1e6, 2)} M` : Math.abs(v) >= 1e4 ? `${fmtNum(v / 1e3, 1)} K` : fmtNum(v, 0)
    return `${props.i.moneda || props.monedaBase} ${n}`
  }
  if (f === 'porcentaje') return `${fmtNum(v, dec)} %`
  if (f === 'dias') return t('{0} days', [fmtNum(v, dec)])
  return fmtNum(v)
}
// Variación frente al período anterior (porcentajes en puntos); el tono dice si es buena
const variacion = computed(() => {
  const { valor, anterior } = props.i
  if (anterior === null || anterior === undefined || valor === null || valor === undefined || valor === anterior) return null
  const dif = valor - anterior
  const tono = props.def.mejor ? ((dif > 0) === (props.def.mejor === 'alto') ? 'ok' : 'aviso') : ''
  const signo = dif > 0 ? '▲' : '▼'
  if (props.def.formato === 'porcentaje') return { texto: t('{0} {1} pp vs. previous period', [signo, fmtNum(Math.abs(dif), 1)]), tono }
  if (!anterior) return null
  return { texto: t('{0} {1}% vs. previous period', [signo, fmtNum(Math.abs((dif * 100) / anterior), 1)]), tono }
})
const pie = computed(() => {
  if (props.i.meta !== null && props.i.meta !== undefined) return { texto: t('Target {0}', [cifra(props.i.meta)]), tono: '' }
  if (variacion.value) return variacion.value
  if (props.i.base?.m) return { texto: t('{0} records', [fmtNum(props.i.base.m)]), tono: '' }
  return { texto: props.def.momento === 'hoy' ? t('Today') : t('Last 30 days'), tono: '' }
})
const serie = computed(() => (props.i.serie || []).map((s) => ({ etiqueta: `${fmtFecha(s.desde)} – ${fmtFecha(s.hasta)}`, valor: s.valor })))
function abrir() {
  if (props.i.ruta) router.push(props.i.ruta)
}
</script>

<template>
  <button type="button" class="panel indicador-inicio" :disabled="!i.ruta" @click="abrir">
    <span class="ii-titulo">{{ tx(def.titulo) }}</span>
    <span class="ii-cuerpo">
      <span>
        <span class="ii-valor">{{ tx(cifra(i.valor)) }}</span>
        <span class="ii-pie" :class="pie.tono && `tono-${pie.tono}`">{{ tx(pie.texto) }}</span>
      </span>
      <Tendencia v-if="serie.length" class="ii-tendencia" :serie="serie" :formato="cifra" :tono="variacion?.tono" />
    </span>
  </button>
</template>

<style scoped>
.indicador-inicio { display: flex; flex-direction: column; gap: 6px; text-align: start; padding: 16px 18px; width: 100%; font: inherit; color: inherit; cursor: pointer; }
.indicador-inicio:disabled { cursor: default; }
.indicador-inicio:not(:disabled):hover { border-color: var(--borde-hover); }
.ii-titulo { color: var(--tinta-2); font-size: var(--t-sm); }
.ii-cuerpo { display: flex; align-items: flex-end; justify-content: space-between; gap: 12px; }
.ii-valor { display: block; font-size: var(--t-xl); font-weight: 600; letter-spacing: -0.01em; font-variant-numeric: tabular-nums; }
.ii-pie { display: block; color: var(--tinta-3); font-size: var(--t-sm); margin-top: 2px; }
.ii-pie.tono-ok { color: var(--ok); }
.ii-pie.tono-aviso { color: var(--aviso); }
.ii-tendencia { width: 96px; flex: none; height: 36px; }
</style>
