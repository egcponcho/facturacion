<script setup>
import { t } from '@/i18n/index.js'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import Icono from '@/componentes/Icono.vue'
import { usarEditor } from './estado.js'

// Clic derecho en el lienzo: lo de siempre a mano (copiar, pegar, agrupar,
// orden, centrar, bloquear, borrar). Sin nada elegido: pegar y elegir todo.
const props = defineProps({ x: { type: Number, required: true }, y: { type: Number, required: true } })
const emit = defineEmits(['cerrar'])
const ed = usarEditor()
const est = ed.estado
const sel = computed(() => ed.seleccionados.value)
const menu = ref(null)
const pos = ref({ left: `${props.x}px`, top: `${props.y}px` })
function hacer(f) {
  f()
  emit('cerrar')
}
function fuera(e) {
  if (menu.value && !menu.value.contains(e.target)) emit('cerrar')
}
const cerrar = () => emit('cerrar')
onMounted(() => {
  // Que no se salga de la ventana
  const r = menu.value.getBoundingClientRect()
  pos.value = { left: `${Math.min(props.x, window.innerWidth - r.width - 8)}px`, top: `${Math.min(props.y, window.innerHeight - r.height - 8)}px` }
  setTimeout(() => document.addEventListener('pointerdown', fuera, true))
  window.addEventListener('blur', cerrar)
  window.addEventListener('resize', cerrar)
})
onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', fuera, true)
  window.removeEventListener('blur', cerrar)
  window.removeEventListener('resize', cerrar)
})
</script>

<template>
  <div ref="menu" class="menu-contexto" role="menu" :style="pos" @keydown.esc="emit('cerrar')" @contextmenu.prevent>
    <template v-if="sel.length">
      <button type="button" :disabled="!est.editable" @click="hacer(ed.duplicar)"><Icono nombre="copiar" :tam="15" />{{ t('Duplicate') }}<kbd>Ctrl D</kbd></button>
      <button type="button" @click="hacer(ed.copiar)"><Icono nombre="copiar" :tam="15" />{{ t('Copy') }}<kbd>Ctrl C</kbd></button>
      <button type="button" :disabled="!est.editable || !est.portapapeles" @click="hacer(ed.pegar)"><Icono nombre="archivo" :tam="15" />{{ t('Paste') }}<kbd>Ctrl V</kbd></button>
      <hr />
      <button v-if="ed.agrupables.value" type="button" :disabled="!est.editable" @click="hacer(ed.agrupar)"><Icono nombre="agrupar" :tam="15" />{{ t('Group them') }}<kbd>Ctrl G</kbd></button>
      <button v-if="ed.agrupados.value" type="button" :disabled="!est.editable" @click="hacer(ed.desagrupar)"><Icono nombre="desagrupar" :tam="15" />{{ t('Ungroup') }}<kbd>Ctrl ⇧ G</kbd></button>
      <button type="button" :disabled="!est.editable" @click="hacer(() => ed.ordenar('frente'))"><Icono nombre="frente" :tam="15" />{{ t('Bring to front') }}</button>
      <button type="button" :disabled="!est.editable" @click="hacer(() => ed.ordenar('fondo'))"><Icono nombre="fondo" :tam="15" />{{ t('Send to back') }}</button>
      <button type="button" :disabled="!est.editable" @click="hacer(() => ed.centrar('ambos'))"><Icono nombre="ajustar" :tam="15" />{{ t('Center on the label') }}</button>
      <button type="button" :disabled="!est.editable" @click="hacer(() => ed.girar(90))"><Icono nombre="girar" :tam="15" />{{ t('Rotate 90°') }}</button>
      <hr />
      <button type="button" :disabled="!est.editable" @click="hacer(() => ed.alternar('bloqueado'))"><Icono nombre="candado" :tam="15" />{{ sel.every((e) => e.bloqueado) ? t('Unlock') : t('Lock') }}</button>
      <button type="button" :disabled="!est.editable" @click="hacer(() => ed.alternar('visible'))"><Icono nombre="ojo" :tam="15" />{{ sel.every((e) => e.visible === false) ? t('Show') : t('Hide') }}</button>
      <button type="button" class="peligro" :disabled="!est.editable" @click="hacer(ed.eliminar)"><Icono nombre="basura" :tam="15" />{{ t('Delete') }}<kbd>Supr</kbd></button>
    </template>
    <template v-else>
      <button type="button" :disabled="!est.editable || !est.portapapeles" @click="hacer(ed.pegar)"><Icono nombre="archivo" :tam="15" />{{ t('Paste') }}<kbd>Ctrl V</kbd></button>
      <button type="button" @click="hacer(ed.seleccionarTodo)"><Icono nombre="lista" :tam="15" />{{ t('Select all') }}<kbd>Ctrl A</kbd></button>
    </template>
  </div>
</template>

<style scoped>
.menu-contexto { position: fixed; z-index: 80; min-width: 220px; padding: 6px; display: flex; flex-direction: column; gap: 1px;
  background: var(--superficie); border: 1px solid var(--linea); border-radius: 10px; box-shadow: var(--sombra-flotante); }
.menu-contexto button { display: flex; align-items: center; gap: 9px; width: 100%; border: 0; background: transparent; text-align: start;
  padding: 6px 9px; border-radius: 6px; font: inherit; font-size: var(--t-sm); color: var(--tinta); cursor: pointer; }
.menu-contexto button:hover:not(:disabled) { background: var(--superficie-2); }
.menu-contexto button:disabled { opacity: 0.45; cursor: default; }
.menu-contexto button.peligro { color: var(--error); }
.menu-contexto kbd { margin-inline-start: auto; font-size: var(--t-2xs); color: var(--tinta-3); font-family: ui-monospace, monospace; }
.menu-contexto hr { border: 0; border-top: 1px solid var(--linea); margin: 4px 2px; }
</style>
