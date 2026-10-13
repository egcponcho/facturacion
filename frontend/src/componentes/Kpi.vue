<script setup>
import { t, tx } from '@/i18n/index.js'
import { computed } from 'vue'
import { fmtMoneda, fmtNum } from '@/nucleo/utils'

// Indicador del tablero: título, cifra y una línea de contexto. Todo el
// recuadro lleva a la lista ya filtrada. Sin datos dice «—» (nunca 0) y sin
// tono; un monto dice su moneda y, si hay montos en otras monedas, los
// muestra aparte (nunca se suman).
const props = defineProps({
  titulo: String,
  valor: { type: Number, default: null },
  formato: { type: String, default: 'numero' }, // numero | moneda | porcentaje | dias
  moneda: { type: String, default: '' },
  otras: { type: Array, default: () => [] }, // [{ moneda, valor }]
  detalle: String,
  icono: { type: String, default: 'grafica' },
  tono: { type: String, default: 'normal' },
})
defineEmits(['abrir'])

const sinDato = computed(() => props.valor === null || props.valor === undefined || Number.isNaN(Number(props.valor)))
// 1,284 / 12.9 K / 4.2 M · 92.5% · 118 d
const cifra = computed(() => {
  if (sinDato.value) return '—'
  const v = Number(props.valor)
  if (props.formato === 'porcentaje') return `${fmtNum(v, Number.isInteger(v) ? 0 : 1)}%`
  if (props.formato === 'dias') return t('{0} d', [fmtNum(v, Number.isInteger(v) ? 0 : 1)])
  if (props.formato !== 'moneda') return fmtNum(v)
  if (Math.abs(v) >= 1e6) return `${fmtNum(v / 1e6, 1)} M`
  if (Math.abs(v) >= 1e4) return `${fmtNum(v / 1e3, 1)} K`
  return fmtNum(v, 0)
})
const tono = computed(() => (sinDato.value ? 'normal' : props.tono))
const otrasTxt = computed(() => props.otras.map((o) => fmtMoneda(o.valor, o.moneda)).join(' · '))
</script>

<template>
  <!-- Indicador: etiqueta, cifra y contexto; el tono se marca con un punto (nunca solo con color: el texto lo dice) -->
  <button type="button" class="kpi" :class="`tono-${tono}`" @click="$emit('abrir')">
    <span class="kpi-titulo" :title="tx(props.titulo)"><i v-if="tono !== 'normal'" class="kpi-punto" aria-hidden="true"></i><span>{{ tx(props.titulo) }}</span></span>
    <span class="kpi-valor"><small v-if="props.formato === 'moneda' && !sinDato">{{ tx(props.moneda) }}</small>{{ tx(cifra) }}</span>
    <span v-if="props.otras.length" class="kpi-otras" :title="t('Amounts in other currencies are shown apart, never added')">+ {{ tx(otrasTxt) }}</span>
    <span v-if="props.detalle" class="kpi-detalle">{{ tx(props.detalle) }}</span>
  </button>
</template>
