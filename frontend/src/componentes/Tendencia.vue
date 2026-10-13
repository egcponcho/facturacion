<script setup>
import { t, tx } from '@/i18n/index.js'
import { computed } from 'vue'

// Tendencia de un indicador: una columna por período (iguales y seguidos) y
// la última, el período actual, resaltada. Sin dato, una marca baja en gris.
// El detalle de cada columna va en su título y en la etiqueta para lectores.
const props = defineProps({
  serie: { type: Array, required: true }, // [{ etiqueta, valor }]
  formato: { type: Function, default: (v) => String(v) },
  tono: { type: String, default: '' }, // ok | aviso: cómo va el último frente al anterior
})
const max = computed(() => Math.max(0, ...props.serie.map((s) => Number(s.valor) || 0)))
const alto = (v) => (v === null || v === undefined ? 0 : max.value ? Math.max(6, (Number(v) / max.value) * 100) : 6)
const texto = (s) => `${s.etiqueta}: ${s.valor === null || s.valor === undefined ? t('no data') : props.formato(s.valor)}`
</script>

<template>
  <div class="tendencia" :class="props.tono && `tono-${props.tono}`" role="img" :aria-label="tx(props.serie.map(texto).join(' · '))">
    <span v-for="(s, i) in props.serie" :key="i" class="col" :class="{ actual: i === props.serie.length - 1, vacia: s.valor === null || s.valor === undefined }"
          :style="{ height: alto(s.valor) + '%' }" :title="tx(texto(s))"></span>
  </div>
</template>

<style scoped>
.tendencia { display: flex; align-items: flex-end; gap: 4px; height: 44px; padding-top: 2px; border-bottom: 1px solid var(--linea); }
.col { flex: 1 1 0; min-width: 4px; border-radius: 3px 3px 0 0; background: color-mix(in srgb, var(--acento) 28%, var(--superficie)); transition: height 0.2s ease; }
.col.actual { background: var(--acento); }
.tono-ok .col.actual { background: var(--ok); }
.tono-aviso .col.actual { background: var(--aviso); }
.col.vacia { height: 3px !important; background: var(--linea); border-radius: 2px; }
</style>
