<script setup>
import { tx } from '../i18n/index.js'
import { computed } from 'vue'
import { fmtNum } from '../utils'

// Indicador del tablero: título, cifra y una línea de contexto. Todo el
// recuadro lleva a la lista ya filtrada.
const props = defineProps({
  titulo: String,
  valor: { type: Number, default: 0 },
  formato: { type: String, default: 'numero' },
  moneda: { type: String, default: '' },
  detalle: String,
  icono: { type: String, default: 'grafica' },
  tono: { type: String, default: 'normal' },
})
defineEmits(['abrir'])

// 1,284 / 12.9 K / 4.2 M
const cifra = computed(() => {
  const v = Number(props.valor || 0)
  if (props.formato !== 'moneda') return fmtNum(v)
  if (Math.abs(v) >= 1e6) return `${fmtNum(v / 1e6, 1)} M`
  if (Math.abs(v) >= 1e4) return `${fmtNum(v / 1e3, 1)} K`
  return fmtNum(v, 0)
})
</script>

<template>
  <!-- Indicador: etiqueta, cifra y contexto; el tono se marca con un punto (nunca solo con color: el texto lo dice) -->
  <button type="button" class="kpi" :class="`tono-${props.tono}`" @click="$emit('abrir')">
    <span class="kpi-titulo" :title="tx(props.titulo)"><i v-if="props.tono !== 'normal'" class="kpi-punto" aria-hidden="true"></i><span>{{ tx(props.titulo) }}</span></span>
    <span class="kpi-valor"><small v-if="props.formato === 'moneda'">{{ tx(props.moneda) }}</small>{{ tx(cifra) }}</span>
    <span v-if="props.detalle" class="kpi-detalle">{{ tx(props.detalle) }}</span>
  </button>
</template>
