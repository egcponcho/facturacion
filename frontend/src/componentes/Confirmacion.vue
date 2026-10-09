<script setup>
import { t, tx } from '@/i18n/index.js'
import { nextTick, ref, watch } from 'vue'
import { dialogo, responder } from '@/stores/confirmar'
import Modal from './Modal.vue'

// La pregunta de confirmar (ver stores/confirmar.js). Con una acción que
// destruye algo, el foco empieza en «Cancelar».
const cancelar = ref(null)
const aceptar = ref(null)
watch(() => dialogo.abierto, async (v) => {
  if (!v) return
  await nextTick()
  ;(dialogo.peligro ? cancelar : aceptar).value?.focus()
})
</script>

<template>
  <Modal v-if="dialogo.abierto" :titulo="tx(dialogo.titulo)" ancho="460px" @cerrar="responder(false)">
    <p class="confirmacion-texto">{{ tx(dialogo.texto) }}</p>
    <template #pie>
      <button ref="cancelar" type="button" class="btn" @click="responder(false)">{{ t('Cancel') }}</button>
      <button ref="aceptar" type="button" class="btn" :class="dialogo.peligro ? 'btn-peligro' : 'btn-primario'" @click="responder(true)">{{ tx(dialogo.boton) }}</button>
    </template>
  </Modal>
</template>

<style scoped>
.confirmacion-texto { margin: 0; line-height: 1.5; }
</style>
