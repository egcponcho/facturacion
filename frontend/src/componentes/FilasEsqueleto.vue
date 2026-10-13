<script setup>
// Filas de carga para una tabla: la forma de la lista aparece al instante y
// los datos la llenan al llegar (en vez de una tabla vacía o un «Cargando…»).
const props = defineProps({ columnas: { type: Number, default: 6 }, filas: { type: Number, default: 6 } })
const anchos = ['70%', '55%', '40%', '85%', '60%', '45%', '75%', '50%']
</script>

<template>
  <tr v-for="f in props.filas" :key="f" class="fila-esqueleto" aria-hidden="true">
    <td v-for="c in props.columnas" :key="c"><span class="esqueleto" :style="{ width: anchos[(f + c) % anchos.length], height: '12px' }"></span></td>
  </tr>
</template>
