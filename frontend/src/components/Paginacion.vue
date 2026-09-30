<script setup>
import { computed } from 'vue'
import Seleccion from './Seleccion.vue'
import Icono from './Icono.vue'

// Pie de tabla: rango mostrado, páginas y filas por página
const props = defineProps({ page: Number, size: Number, total: Number, tamanos: { type: Array, default: () => [10, 15, 25, 50, 100] } })
const emit = defineEmits(['cambiar', 'tamano'])
const paginas = computed(() => Math.max(1, Math.ceil((props.total || 0) / props.size)))
const desde = computed(() => (props.total ? (props.page - 1) * props.size + 1 : 0))
const hasta = computed(() => Math.min(props.page * props.size, props.total || 0))
// Hasta 7 botones: primera, última y las vecinas de la actual
const botones = computed(() => {
  const n = paginas.value
  const p = props.page
  if (n <= 7) return Array.from({ length: n }, (_, i) => i + 1)
  const set = new Set([1, n, p - 1, p, p + 1].filter((x) => x >= 1 && x <= n))
  const lista = [...set].sort((a, b) => a - b)
  const res = []
  lista.forEach((x, i) => {
    if (i && x - lista[i - 1] > 1) res.push('…')
    res.push(x)
  })
  return res
})
</script>

<template>
  <div class="paginacion">
    <span class="ayuda">{{ desde }}–{{ hasta }} of {{ props.total || 0 }} records</span>
    <div class="paginas" role="navigation" aria-label="Pages">
      <button type="button" class="pag-btn" :disabled="props.page <= 1" aria-label="Previous page" @click="emit('cambiar', props.page - 1)"><Icono nombre="atras" :tam="14" /></button>
      <template v-for="(b, i) in botones" :key="i">
        <span v-if="b === '…'" class="ayuda">…</span>
        <button v-else type="button" class="pag-btn" :aria-current="b === props.page ? 'page' : undefined" @click="emit('cambiar', b)">{{ b }}</button>
      </template>
      <button type="button" class="pag-btn" :disabled="props.page >= paginas" aria-label="Next page" @click="emit('cambiar', props.page + 1)"><Icono nombre="flecha" :tam="14" /></button>
    </div>
    <label class="fila-flex ayuda" style="gap: 6px">
      Rows per page
      <Seleccion class="entrada" style="padding: 4px 8px" :value="props.size" @change="emit('tamano', Number($event)); emit('cambiar', 1)">
        <option v-for="t in props.tamanos" :key="t" :value="t">{{ t }}</option>
      </Seleccion>
    </label>
  </div>
</template>
