<script setup>
const props = defineProps({
  cantidad: { type: Number, default: 0 },
  singular: { type: String, default: 'seleccionada' },
  plural: { type: String, default: 'seleccionadas' },
})
defineEmits(['limpiar'])
</script>

<template>
  <div v-if="props.cantidad > 0" class="barra-seleccion" role="region" aria-label="Acciones sobre la selección">
    <strong>{{ props.cantidad }} {{ props.cantidad === 1 ? props.singular : props.plural }}</strong>
    <span class="resumen"><slot name="resumen" /></span>
    <div class="acciones"><slot /></div>
    <button type="button" class="btn-texto" @click="$emit('limpiar')">Quitar selección</button>
  </div>
</template>
