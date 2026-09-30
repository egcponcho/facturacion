<script setup>
import { fmtFecha } from '../utils'

// Fecha estimada en tienda (con los lead times del origen) y cuántos días
// antes o después de la fecha en tienda pedida en la OC.
defineProps({ fecha: { type: String, default: null }, dias: { type: Number, default: null } })
</script>

<template>
  <span v-if="fecha" class="fecha-tienda" title="Estimated with the lead times of its origin: arrival plus port, warehouse entry and re-export days">
    {{ fmtFecha(fecha) }}
    <span v-if="dias !== null" class="sub" :style="{ color: dias > 0 ? 'var(--error)' : 'var(--ok)' }">
      {{ dias > 0 ? `${dias} ${dias === 1 ? 'day' : 'days'} late` : dias < 0 ? `${-dias} ${dias === -1 ? 'day' : 'days'} early` : 'On the date' }}
    </span>
  </span>
  <span v-else class="apagado">—</span>
</template>
