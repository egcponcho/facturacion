<script setup>
import { tx } from '../i18n/index.js'
import { computed } from 'vue'

// Proporción de un total (por ejemplo, lo empacado de un packing list)
const props = defineProps({ porcentaje: { type: Number, default: 0 }, titulo: String, detalle: String })
const R = 26
const C = 2 * Math.PI * R
const p = computed(() => Math.max(0, Math.min(100, props.porcentaje || 0)))
</script>

<template>
  <div class="anillo">
    <svg viewBox="0 0 64 64" role="img" :aria-label="tx(`${props.titulo}: ${Math.round(p)}%`)">
      <circle cx="32" cy="32" :r="R" fill="none" style="stroke: var(--azul-claro)" stroke-width="8" />
      <circle cx="32" cy="32" :r="R" fill="none" :style="{ stroke: p >= 100 ? 'var(--ok)' : 'var(--azul)' }" stroke-width="8" stroke-linecap="round"
              :stroke-dasharray="`${(C * p) / 100} ${C}`" transform="rotate(-90 32 32)" />
      <text x="32" y="36.5" text-anchor="middle" font-size="13" font-weight="700" style="fill: var(--tinta)">{{ tx(Math.round(p)) }}%</text>
    </svg>
    <div class="anillo-texto"><b>{{ tx(props.titulo) }}</b><span>{{ tx(props.detalle) }}</span></div>
  </div>
</template>
