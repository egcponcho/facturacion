<script setup>
import { onBeforeUnmount, ref } from 'vue'
import Icono from '@/componentes/Icono.vue'

// Menú desplegable de la barra del editor (Alinear, Orden…): un botón con su
// ícono y texto; la lista se abre debajo, en posición fija (no la corta el
// panel) y se cierra al elegir, al hacer clic fuera o con Escape.
const props = defineProps({ icono: { type: String, default: '' }, texto: { type: String, default: '' }, titulo: { type: String, default: '' },
  deshabilitado: Boolean })
const abierto = ref(false)
const raiz = ref(null)
const pos = ref({})
function fuera(e) {
  if (raiz.value && !raiz.value.contains(e.target)) cerrar()
}
function cerrar() {
  abierto.value = false
  document.removeEventListener('pointerdown', fuera, true)
  window.removeEventListener('resize', cerrar)
}
function alternar() {
  if (abierto.value) return cerrar()
  const r = raiz.value.getBoundingClientRect()
  pos.value = { left: `${Math.max(8, Math.min(r.left, window.innerWidth - 260))}px`, top: `${r.bottom + 4}px` }
  abierto.value = true
  document.addEventListener('pointerdown', fuera, true)
  window.addEventListener('resize', cerrar)
}
onBeforeUnmount(cerrar)
</script>

<template>
  <div ref="raiz" class="menu-barra" @keydown.esc="cerrar">
    <button type="button" class="btn btn-chico mb-boton" :class="{ activo: abierto }" :disabled="props.deshabilitado" aria-haspopup="menu"
            :aria-expanded="abierto" :title="props.titulo || props.texto" @click="alternar">
      <Icono v-if="props.icono" :nombre="props.icono" :tam="16" /><span v-if="props.texto" class="mb-texto">{{ props.texto }}</span>
      <Icono nombre="abajo" :tam="12" class="mb-flecha" />
    </button>
    <div v-if="abierto" class="menu-barra-lista" role="menu" :style="pos" @click="cerrar"><slot /></div>
  </div>
</template>

<style scoped>
.menu-barra { position: relative; display: inline-flex; }
.mb-boton { gap: 5px; }
.mb-flecha { opacity: 0.6; }
.menu-barra-lista { position: fixed; z-index: 70; min-width: 230px; padding: 6px; display: flex; flex-direction: column; gap: 1px;
  background: var(--superficie); border: 1px solid var(--linea); border-radius: 10px; box-shadow: var(--sombra-flotante); }
.menu-barra-lista :deep(button) { display: flex; align-items: center; gap: 9px; width: 100%; border: 0; background: transparent; text-align: start;
  padding: 7px 9px; border-radius: 6px; font: inherit; font-size: 0.86rem; color: var(--tinta); cursor: pointer; }
.menu-barra-lista :deep(button:hover:not(:disabled)), .menu-barra-lista :deep(button:focus-visible) { background: var(--superficie-2); outline: none; }
.menu-barra-lista :deep(button:disabled) { opacity: 0.45; cursor: default; }
.menu-barra-lista :deep(kbd) { margin-inline-start: auto; font-size: 0.72rem; color: var(--tinta-3); font-family: ui-monospace, monospace; }
.menu-barra-lista :deep(hr) { border: 0; border-top: 1px solid var(--linea); margin: 4px 2px; }
.menu-barra-lista :deep(.mb-seccion) { font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--tinta-3); padding: 6px 9px 2px; }
</style>
