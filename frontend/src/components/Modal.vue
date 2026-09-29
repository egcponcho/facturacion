<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import Icono from './Icono.vue'

const props = defineProps({ titulo: String, ancho: { type: String, default: '560px' } })
const emit = defineEmits(['cerrar'])
const cuerpo = ref(null)

function tecla(e) {
  if (e.key === 'Escape') emit('cerrar')
}
onMounted(() => {
  document.addEventListener('keydown', tecla)
  cuerpo.value?.querySelector('input:not([type=checkbox]),select,textarea')?.focus()
})
onBeforeUnmount(() => document.removeEventListener('keydown', tecla))
</script>

<template>
  <Teleport to="body">
    <div class="modal-fondo" @mousedown.self="emit('cerrar')">
      <div class="modal" role="dialog" aria-modal="true" :aria-label="props.titulo" :style="{ maxWidth: props.ancho }">
        <header class="modal-cabeza">
          <h2>{{ props.titulo }}</h2>
          <button class="btn-icono" type="button" aria-label="Close" @click="emit('cerrar')"><Icono nombre="cerrar" :tam="20" /></button>
        </header>
        <div ref="cuerpo" class="modal-cuerpo"><slot /></div>
        <footer v-if="$slots.pie" class="modal-pie"><slot name="pie" /></footer>
      </div>
    </div>
  </Teleport>
</template>
