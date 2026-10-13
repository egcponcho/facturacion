<script setup>
import { t, tx } from '@/i18n/index.js'
const props = defineProps({
  cantidad: { type: Number, default: 0 },
  singular: { type: String, default: 'selected' },
  plural: { type: String, default: 'selected' },
})
defineEmits(['limpiar'])
</script>

<template>
  <div v-if="props.cantidad > 0" class="barra-seleccion" role="region" :aria-label="t('Actions on the selection')">
    <strong>{{ tx(props.cantidad) }} {{ tx(props.cantidad === 1 ? props.singular : props.plural) }}</strong>
    <span class="resumen"><slot name="resumen" /></span>
    <div class="acciones"><slot /></div>
    <button type="button" class="btn-texto" @click="$emit('limpiar')">{{ t('Clear selection') }}</button>
  </div>
</template>
