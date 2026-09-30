<script setup>
import { computed, ref } from 'vue'

// Periodo rápido: semana, mes, trimestre, año, últimos 12 meses o rango propio.
// v-model: { clave, desde, hasta } con fechas ISO (YYYY-MM-DD).
const props = defineProps({ modelValue: { type: Object, required: true } })
const emit = defineEmits(['update:modelValue'])

const OPCIONES = [['semana', 'This week'], ['mes', 'This month'], ['mes_ant', 'Last month'], ['trimestre', 'This quarter'], ['anio', 'This year'], ['12m', '12 months']]
const propio = ref(props.modelValue.clave === 'propio')
const texto = computed(() => {
  const f = (s) => new Date(`${s}T00:00:00`).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' })
  return `${f(props.modelValue.desde)} – ${f(props.modelValue.hasta)}`
})

function elegir(clave) {
  propio.value = false
  const [a, b] = rango(clave)
  emit('update:modelValue', { clave, desde: iso(a), hasta: iso(b) })
}
function rangoPropio(campo, v) {
  if (!v) return
  emit('update:modelValue', { ...props.modelValue, clave: 'propio', [campo]: v })
}
</script>

<script>
const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
export function rango(clave) {
  const h = new Date()
  h.setHours(0, 0, 0, 0)
  const y = h.getFullYear()
  const m = h.getMonth()
  switch (clave) {
    case 'semana': { const d = new Date(h); d.setDate(h.getDate() - ((h.getDay() + 6) % 7)); return [d, h] }
    case 'mes_ant': return [new Date(y, m - 1, 1), new Date(y, m, 0)]
    case 'trimestre': return [new Date(y, Math.floor(m / 3) * 3, 1), h]
    case 'anio': return [new Date(y, 0, 1), h]
    case '12m': return [new Date(y, m - 11, 1), h]
    default: return [new Date(y, m, 1), h]
  }
}
// Periodo inicial para quien usa el componente (por defecto, el mes en curso)
export function periodoInicial(clave = 'mes') {
  const [a, b] = rango(clave)
  return { clave, desde: iso(a), hasta: iso(b) }
}
</script>

<template>
  <div class="periodo">
    <div class="segmentos" role="group" aria-label="Period">
      <button v-for="[k, t] in OPCIONES" :key="k" type="button" class="segmento" :aria-pressed="props.modelValue.clave === k" @click="elegir(k)">{{ t }}</button>
      <button type="button" class="segmento" :aria-pressed="props.modelValue.clave === 'propio'" @click="propio = true">Custom</button>
    </div>
    <span v-if="propio || props.modelValue.clave === 'propio'" class="rango-propio">
      <input type="date" class="entrada" :value="props.modelValue.desde" aria-label="From" @change="rangoPropio('desde', $event.target.value)" />
      <span class="ayuda">to</span>
      <input type="date" class="entrada" :value="props.modelValue.hasta" aria-label="To" @change="rangoPropio('hasta', $event.target.value)" />
    </span>
    <span v-else class="ayuda">{{ texto }}</span>
  </div>
</template>

<style scoped>
.periodo { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 12px; }
.rango-propio { display: inline-flex; align-items: center; gap: 6px; }
.rango-propio input { padding: 5px 8px; }
</style>
