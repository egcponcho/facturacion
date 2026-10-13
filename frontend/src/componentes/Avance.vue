<script setup>
import { tx } from '@/i18n/index.js'
import { computed } from 'vue'

const props = defineProps({ valor: { type: Number, default: 0 }, total: { type: Number, default: 0 }, porcentaje: { type: Number, default: null } })
const p = computed(() => {
  if (props.porcentaje !== null) return props.porcentaje
  return props.total ? (props.valor * 100) / props.total : 0
})
</script>

<template>
  <div class="avance" :title="tx(`${Math.round(p)}%`)">
    <div class="avance-riel">
      <div class="avance-relleno" :class="{ completo: p >= 99.95 && p <= 100.05, excedido: p > 100.05 }" :style="{ width: `${Math.min(100, p)}%` }"></div>
    </div>
    <span class="avance-texto">{{ tx(Math.round(p)) }}%</span>
  </div>
</template>
