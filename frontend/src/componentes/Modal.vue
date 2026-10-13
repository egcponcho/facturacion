<script setup>
import { t, tx } from '@/i18n/index.js'
import { onBeforeUnmount, onMounted, ref } from 'vue'
import Icono from './Icono.vue'
import { abrirCapa, cerrarCapa, esLaDeArriba } from '@/nucleo/capas.js'

const props = defineProps({ titulo: String, ancho: { type: String, default: '560px' } })
const emit = defineEmits(['cerrar'])
const cuerpo = ref(null)
let capa = null

// Esc cierra solo la ventana de más arriba (p. ej. la confirmación sobre un formulario)
function tecla(e) {
  if (e.key === 'Escape' && esLaDeArriba(capa)) emit('cerrar')
}
onMounted(() => {
  capa = abrirCapa()
  document.addEventListener('keydown', tecla)
  cuerpo.value?.querySelector('input:not([type=checkbox]),select,textarea')?.focus()
})
onBeforeUnmount(() => {
  cerrarCapa(capa)
  document.removeEventListener('keydown', tecla)
})
</script>

<template>
  <Teleport to="body">
    <div class="modal-fondo" @mousedown.self="emit('cerrar')">
      <div class="modal" role="dialog" aria-modal="true" :aria-label="tx(props.titulo)" :style="{ maxWidth: props.ancho }">
        <header class="modal-cabeza">
          <h2>{{ tx(props.titulo) }}</h2>
          <button class="btn-icono" type="button" :aria-label="t('Close')" @click="emit('cerrar')"><Icono nombre="cerrar" :tam="20" /></button>
        </header>
        <div ref="cuerpo" class="modal-cuerpo"><slot /></div>
        <footer v-if="$slots.pie" class="modal-pie"><slot name="pie" /></footer>
      </div>
    </div>
  </Teleport>
</template>
