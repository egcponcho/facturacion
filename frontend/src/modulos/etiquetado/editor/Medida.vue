<script setup>
import { computed } from 'vue'
import { aMm, aUnidad } from '@/modulos/etiquetado/etiquetas.js'

// Un número guardado en mm (o en la magnitud que se indique) que se muestra y
// se escribe en la unidad elegida del diseño (mm, cm o pulgadas).
const props = defineProps({
  modelValue: { type: Number, default: 0 },
  etiqueta: { type: String, required: true },
  unidad: { type: String, default: 'mm' }, // mm | cm | in | pt | ° | ''
  min: { type: Number, default: undefined },
  max: { type: Number, default: undefined },
  disabled: Boolean,
})
const emit = defineEmits(['update:modelValue'])
const longitud = computed(() => ['mm', 'cm', 'in'].includes(props.unidad))
const paso = computed(() => ({ mm: 0.1, cm: 0.01, in: 0.01, pt: 0.5, '°': 1 })[props.unidad] ?? 0.1)
const mostrado = computed(() => (longitud.value ? aUnidad(props.modelValue ?? 0, props.unidad) : Math.round((props.modelValue ?? 0) * 1000) / 1000))
function cambiar(ev) {
  const v = Number(String(ev.target.value).replace(',', '.'))
  if (ev.target.value === '' || Number.isNaN(v)) return
  let mm = longitud.value ? aMm(v, props.unidad) : v
  if (props.min != null) mm = Math.max(mm, props.min)
  if (props.max != null) mm = Math.min(mm, props.max)
  emit('update:modelValue', mm)
}
</script>

<template>
  <label class="medida">
    <span class="medida-etq">{{ props.etiqueta }}</span>
    <span class="medida-caja">
      <input type="number" :value="mostrado" :step="paso" :disabled="props.disabled" inputmode="decimal" @change="cambiar" @keydown.enter="cambiar" />
      <span v-if="props.unidad" class="medida-u">{{ props.unidad }}</span>
    </span>
  </label>
</template>

<style scoped>
.medida { display: flex; flex-direction: column; gap: 3px; min-width: 0; }
.medida-etq { font-size: 0.72rem; color: var(--tinta-3); }
.medida-caja { position: relative; display: flex; }
.medida-caja input { width: 100%; padding-right: 26px; min-width: 0; }
.medida-u { position: absolute; right: 8px; top: 50%; transform: translateY(-50%); font-size: 0.72rem; color: var(--tinta-3); pointer-events: none; }
</style>
