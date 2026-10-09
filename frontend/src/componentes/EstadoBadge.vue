<script setup>
import { tx } from '@/i18n/index.js'
import { computed } from 'vue'
import { estado as leerEstado } from '@/nucleo/estados.js'

// Etiqueta del estado de un documento; `tipo` distingue los códigos que se
// leen distinto según el documento (embarque, avance de la OC…)
const props = defineProps({ estado: { type: String, default: '' }, tipo: { type: String, default: '' } })
const e = computed(() => leerEstado(props.estado, props.tipo))
</script>

<template>
  <span class="estado" :class="`estado-${e[1]}`">
    <span class="estado-marca" aria-hidden="true"></span>{{ tx(e[0]) }}
  </span>
</template>
