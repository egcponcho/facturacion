<script setup>
import { computed } from 'vue'
import Icono from './Icono.vue'

// Encabezado de columna que se puede ordenar. `orden` es "campo:asc|desc".
const props = defineProps({ campo: { type: String, required: true }, orden: { type: String, default: '' }, num: Boolean })
defineEmits(['ordenar'])
const dir = computed(() => {
  const [c, d] = props.orden.split(':')
  return c === props.campo ? d : null
})
</script>

<template>
  <th :class="{ num: props.num }" :aria-sort="dir === 'asc' ? 'ascending' : dir === 'desc' ? 'descending' : 'none'">
    <button type="button" class="orden-btn" :class="{ activo: dir }" @click="$emit('ordenar', props.campo)">
      <slot />
      <span class="orden-flecha" aria-hidden="true">
        <Icono :nombre="dir === 'desc' ? 'abajo' : dir === 'asc' ? 'arriba' : 'arribaabajo'" :tam="13" />
      </span>
    </button>
  </th>
</template>
