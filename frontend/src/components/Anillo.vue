<script setup>
import { computed } from 'vue'

// Proporción de un total (por ejemplo, lo empacado de un packing list)
const props = defineProps({ porcentaje: { type: Number, default: 0 }, titulo: String, detalle: String })
const R = 26
const C = 2 * Math.PI * R
const p = computed(() => Math.max(0, Math.min(100, props.porcentaje || 0)))
</script>

<template>
  <div class="anillo">
    <svg viewBox="0 0 64 64" role="img" :aria-label="`${props.titulo}: ${Math.round(p)}%`">
      <circle cx="32" cy="32" :r="R" fill="none" stroke="#e8f1fc" stroke-width="8" />
      <circle cx="32" cy="32" :r="R" fill="none" :stroke="p >= 100 ? '#217a45' : '#2a78d6'" stroke-width="8" stroke-linecap="round"
              :stroke-dasharray="`${(C * p) / 100} ${C}`" transform="rotate(-90 32 32)" />
      <text x="32" y="36.5" text-anchor="middle" font-size="13" font-weight="700" fill="#15212b">{{ Math.round(p) }}%</text>
    </svg>
    <div class="anillo-texto"><b>{{ props.titulo }}</b><span>{{ props.detalle }}</span></div>
  </div>
</template>
