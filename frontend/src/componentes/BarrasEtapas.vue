<script setup>
import { t, tx } from '@/i18n/index.js'
import { computed } from 'vue'
import { fmtNum } from '@/nucleo/utils'

// Cuántos documentos hay en cada etapa del proceso, en barras horizontales
// en el orden del proceso. Cada barra filtra la tabla (otro clic la quita);
// las etapas vacías quedan atenuadas pero a la vista para no perder el orden.
const props = defineProps({
  etapas: { type: Array, required: true }, // [{ clave, nombre, total }]
  activa: { type: String, default: '' },
  etiqueta: { type: String, required: true },
})
const emit = defineEmits(['elegir'])
const max = computed(() => Math.max(1, ...props.etapas.map((e) => e.total || 0)))
</script>

<template>
  <ol class="barras-etapas" :aria-label="tx(props.etiqueta)">
    <li v-for="(e, i) in props.etapas" :key="e.clave">
      <button type="button" class="be-fila" :class="{ vacia: !e.total }" :aria-pressed="props.activa === e.clave"
              :title="tx(props.activa === e.clave ? t('Remove the filter') : t('Filter by {0}', [e.nombre]))" @click="emit('elegir', props.activa === e.clave ? '' : e.clave)">
        <span class="be-num">{{ i + 1 }}</span>
        <span class="be-nombre">{{ tx(e.nombre) }}</span>
        <span class="be-pista"><span class="be-barra" :style="{ width: `${((e.total || 0) * 100) / max}%` }"></span></span>
        <b class="be-total">{{ fmtNum(e.total || 0) }}</b>
      </button>
    </li>
  </ol>
</template>

<style scoped>
.barras-etapas { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 2px; }
.be-fila { width: 100%; display: grid; grid-template-columns: 20px minmax(110px, 38%) minmax(0, 1fr) 36px; align-items: center; gap: 10px;
  padding: 5px 8px; border: 0; border-radius: var(--radio); background: none; color: var(--tinta); font: inherit; font-size: 0.84rem; text-align: start; cursor: pointer; }
.be-fila:hover { background: var(--superficie-2); }
.be-fila[aria-pressed='true'] { background: var(--acento-claro); box-shadow: inset 0 0 0 1px var(--acento-medio); }
.be-num { font-size: 0.7rem; font-weight: 700; color: var(--tinta-3); text-align: center; font-variant-numeric: tabular-nums; }
.be-nombre { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--tinta-2); }
.be-pista { height: 10px; border-radius: 5px; background: var(--linea-suave); overflow: hidden; }
.be-barra { display: block; height: 100%; border-radius: 5px; background: var(--acento); min-width: 0; transition: width 0.2s ease; }
.be-total { text-align: end; font-variant-numeric: tabular-nums; }
.vacia .be-nombre, .vacia .be-total { color: var(--tinta-3); font-weight: 500; }
@media (max-width: 600px) { .be-fila { grid-template-columns: 18px minmax(0, 1fr) 70px 30px; } }
</style>
