<script setup>
import { t } from '../i18n/index.js'
import { onBeforeUnmount, ref } from 'vue'
import Icono from './Icono.vue'

// Acciones secundarias: en pantallas grandes se muestran tal cual; en el
// celular quedan detrás de un botón «Más opciones» que abre un menú.
const abierto = ref(false)
const raiz = ref(null)
const alFinal = ref(false) // abre hacia el lado con más espacio
function fuera(e) {
  if (raiz.value && !raiz.value.contains(e.target)) abierto.value = false
}
function alternar() {
  abierto.value = !abierto.value
  if (abierto.value && raiz.value) {
    const r = raiz.value.getBoundingClientRect()
    alFinal.value = r.left + r.width / 2 > window.innerWidth / 2
  }
  if (abierto.value) setTimeout(() => document.addEventListener('click', fuera), 0)
  else document.removeEventListener('click', fuera)
}
onBeforeUnmount(() => document.removeEventListener('click', fuera))
</script>

<template>
  <div ref="raiz" class="mas-opciones" :class="{ abierto, 'al-final': alFinal }" @keydown.esc="abierto = false">
    <button type="button" class="btn mas-toggle" :aria-expanded="abierto" aria-haspopup="true" @click="alternar">
      <Icono nombre="lista" :tam="15" />{{ t('More options') }}
    </button>
    <div class="mas-menu" @click="abierto && alternar()"><slot /></div>
  </div>
</template>
