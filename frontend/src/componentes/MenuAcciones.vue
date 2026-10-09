<script setup>
import { t } from '@/i18n/index.js'
import { onBeforeUnmount, ref } from 'vue'
import Icono from './Icono.vue'

// Menú «⋯» con las acciones de una fila: la tabla queda en una línea por
// registro y las acciones a un clic.
const props = defineProps({ etiqueta: { type: String, default: '' } })
const abierto = ref(false)
const raiz = ref(null)
// Posición fija en la ventana: así el menú no queda cortado por la tabla
const pos = ref({})
function fuera(e) {
  if (raiz.value && !raiz.value.contains(e.target)) cerrar()
}
function cerrar() {
  abierto.value = false
  document.removeEventListener('click', fuera)
}
function alternar() {
  abierto.value = !abierto.value
  if (abierto.value && raiz.value) {
    const r = raiz.value.getBoundingClientRect()
    const abajo = window.innerHeight - r.bottom > 260
    pos.value = { right: `${window.innerWidth - r.right}px`, ...(abajo ? { top: `${r.bottom + 4}px` } : { bottom: `${window.innerHeight - r.top + 4}px` }) }
  }
  if (abierto.value) {
    setTimeout(() => {
      document.addEventListener('click', fuera)
      window.addEventListener('scroll', cerrar, { capture: true, once: true }) // el menú no sigue a la página
    }, 150)
  } else document.removeEventListener('click', fuera)
}
onBeforeUnmount(() => document.removeEventListener('click', fuera))
</script>

<template>
  <div ref="raiz" class="menu-acciones" @keydown.esc="cerrar">
    <button type="button" class="btn-icono" :aria-expanded="abierto" aria-haspopup="true" :aria-label="props.etiqueta || t('Actions')" :title="t('Actions')" @click="alternar">
      <Icono nombre="puntos" :tam="18" />
    </button>
    <div v-if="abierto" class="menu-acciones-lista" role="menu" :style="pos" @click="cerrar"><slot /></div>
  </div>
</template>

<style scoped>
.menu-acciones { position: relative; display: inline-block; }
.menu-acciones-lista { position: fixed; z-index: 60; min-width: 210px; padding: 6px;
  background: var(--superficie); border: 1px solid var(--linea); border-radius: 10px; box-shadow: var(--sombra-flotante);
  display: flex; flex-direction: column; }
.menu-acciones-lista :deep(button) { justify-content: flex-start; width: 100%; border: 0; background: transparent; text-align: start;
  padding: 8px 10px; border-radius: 6px; font: inherit; font-size: 0.9rem; color: var(--tinta); cursor: pointer; }
.menu-acciones-lista :deep(button:hover), .menu-acciones-lista :deep(button:focus-visible) { background: var(--superficie-2); outline: none; }
</style>
