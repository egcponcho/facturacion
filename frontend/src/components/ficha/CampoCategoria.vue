<script setup>
import { t, tx } from '../../i18n/index.js'
import { computed, nextTick, ref, watch } from 'vue'
import { filtrar } from '../../busqueda.js'

// «¿Qué es el producto?»: las categorías salen de la configuración (Aranceles →
// Dominios y categorías), no del código. Todas abren la misma ficha dinámica
// del motor del servidor; las genéricas (químico, materia prima, otro) van al final.
const props = defineProps({ modelValue: { type: String, default: '' }, categorias: { type: Array, default: () => [] }, disabled: Boolean, id: String })
const emit = defineEmits(['update:modelValue'])

const texto = ref('')
const abierta = ref(false)
const activo = ref(-1)
const lista = ref(null)

const activas = computed(() => props.categorias.filter((c) => c.activo !== false))
const etiqueta = (k) => props.categorias.find((x) => x.codigo === k)?.nombre || ''
const sync = () => (texto.value = props.modelValue ? etiqueta(props.modelValue) : '')
watch(() => [props.modelValue, props.categorias.length], sync, { immediate: true })

const grupos = computed(() => {
  const q = texto.value.trim()
  if (q && q !== etiqueta(props.modelValue)) {
    const ks = filtrar(activas.value, q, (c) => [c.nombre, c.nombre_corto, c.alias, c.grupo, c.dominio]).map((c) => c.codigo)
    return [{ t: ks.length ? t('Matches') : '', items: ks.slice(0, 25) }]
  }
  const g = new Map()
  for (const c of [...activas.value].sort((a, b) => (a.orden ?? 0) - (b.orden ?? 0))) g.set(c.grupo || t('Other'), [...(g.get(c.grupo || t('Other')) || []), c.codigo])
  return [...g].map(([nombre, items]) => ({ t: nombre, items }))
})
const items = computed(() => grupos.value.flatMap((g) => g.items))
function abrir() {
  if (props.disabled) return
  abierta.value = true
  activo.value = -1
  nextTick(() => lista.value?.querySelector('.elegido')?.scrollIntoView({ block: 'center' }))
}
function cerrar() {
  abierta.value = false
  sync()
}
const alSalir = () => setTimeout(cerrar, 150)
function elegir(k) {
  emit('update:modelValue', k)
  texto.value = etiqueta(k)
  abierta.value = false
}
function tecla(e) {
  if (!abierta.value) {
    if (e.key === 'ArrowDown') { e.preventDefault(); abrir() }
    return
  }
  if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
    e.preventDefault()
    if (!items.value.length) return
    activo.value = Math.max(0, Math.min(items.value.length - 1, activo.value + (e.key === 'ArrowDown' ? 1 : -1)))
    nextTick(() => lista.value?.querySelector('.act')?.scrollIntoView({ block: 'nearest' }))
  } else if (e.key === 'Enter') {
    e.preventDefault()
    const k = activo.value >= 0 ? items.value[activo.value] : items.value.length === 1 ? items.value[0] : null
    if (k) elegir(k)
  } else if (e.key === 'Escape' || e.key === 'Tab') cerrar()
}
</script>

<template>
  <div class="cbx">
    <input :id="props.id" v-model="texto" class="entrada" type="text" autocomplete="off" role="combobox" aria-autocomplete="list"
           :aria-expanded="abierta" :disabled="props.disabled" :placeholder="t('Search or choose: sneaker, backpack, bottle…')"
           @focus="abrir" @click="abierta || abrir()" @input="abierta = true; activo = -1" @keydown="tecla" @blur="alSalir" />
    <div v-if="abierta" ref="lista" class="cbx-lista" role="listbox" @mousedown.prevent>
      <template v-for="g in grupos" :key="g.t">
        <div v-if="g.t" class="grp">{{ tx(g.t) }}</div>
        <button v-for="k in g.items" :key="k" type="button" role="option" :aria-selected="k === props.modelValue"
                :class="{ elegido: k === props.modelValue, act: items[activo] === k }" @click="elegir(k)">
          {{ tx(k === props.modelValue ? '✓ ' : '') }}{{ tx(etiqueta(k)) }}
        </button>
      </template>
      <div v-if="!items.length" class="vacio-cbx">{{ t('No category matches. Try another word (e.g. “jacket”, “bag”).') }}</div>
    </div>
  </div>
</template>

<style scoped>
.cbx { position: relative; width: 100%; }
.cbx .entrada { width: 100%; }
.cbx-lista { position: absolute; z-index: 40; inset-inline-start: 0; inset-inline-end: 0; top: calc(100% + 2px); min-width: min(320px, 90vw); max-height: 300px; overflow: auto; background: var(--superficie); border: 1px solid var(--linea); border-radius: 8px; box-shadow: var(--sombra-flotante); padding: 4px 0; }
.grp { font-size: 0.72rem; font-weight: 650; color: var(--tinta-3); padding: 8px 12px 4px; text-transform: uppercase; letter-spacing: 0.03em; }
.cbx-lista button { display: block; width: 100%; text-align: start; border: 0; background: none; padding: 7px 12px; font-size: 0.9rem; cursor: pointer; color: var(--tinta); font-family: inherit; }
.cbx-lista button.act, .cbx-lista button:hover { background: var(--acento-claro); }
.cbx-lista button.elegido { font-weight: 650; color: var(--acento-texto); }
.vacio-cbx { padding: 8px 12px; font-size: 0.84rem; color: var(--tinta-3); }
</style>
