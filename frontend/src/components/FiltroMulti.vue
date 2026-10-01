<script setup>
import { t, tx } from '../i18n/index.js'
import { computed, ref } from 'vue'
import Icono from './Icono.vue'

// Filtro de varios valores: v-model es una lista; se envía separada por comas.
const props = defineProps({
  modelValue: { type: Array, default: () => [] },
  opciones: { type: Array, default: () => [] }, // [{valor, texto}]
  etiqueta: { type: String, required: true },
  vacio: { type: String, default: () => t('all') },
})
const emit = defineEmits(['update:modelValue', 'change'])
const abierto = ref(false)
const q = ref('')
const visibles = computed(() => props.opciones.filter((o) => !q.value || o.texto.toLowerCase().includes(q.value.toLowerCase())))
const resumen = computed(() => {
  const n = props.modelValue.length
  if (!n) return props.vacio
  if (n <= 2) return props.modelValue.map((v) => props.opciones.find((o) => o.valor === v)?.texto || v).join(', ')
  return t('{0} selected', [n])
})
function alternar(v) {
  const s = new Set(props.modelValue)
  s.has(v) ? s.delete(v) : s.add(v)
  emit('update:modelValue', [...s])
  emit('change')
}
function limpiar() {
  emit('update:modelValue', [])
  emit('change')
}
</script>

<template>
  <div class="fm" @keydown.esc="abierto = false">
    <button type="button" class="fm-boton" :class="{ activo: props.modelValue.length }" :aria-expanded="abierto" @click="abierto = !abierto">
      <span>{{ tx(props.etiqueta) }}: <b>{{ tx(resumen) }}</b></span><Icono nombre="abajo" :tam="14" />
    </button>
    <div v-if="abierto" class="fm-velo" @click="abierto = false"></div>
    <div v-if="abierto" class="fm-panel" role="listbox" aria-multiselectable="true">
      <input v-if="props.opciones.length > 8" v-model="q" class="entrada" type="search" :placeholder="t('Search')" :aria-label="t('Search options')" />
      <div class="fm-lista">
        <label v-for="o in visibles" :key="o.valor" class="fm-op">
          <input type="checkbox" :checked="props.modelValue.includes(o.valor)" @change="alternar(o.valor)" /><span>{{ tx(o.texto) }}</span>
        </label>
      </div>
      <button v-if="props.modelValue.length" type="button" class="btn-texto" @click="limpiar">{{ t('Clear') }}</button>
    </div>
  </div>
</template>

<style scoped>
.fm { position: relative; }
.fm-boton { display: inline-flex; align-items: center; gap: 6px; min-height: 36px; padding: 6px 10px; border: 1px solid var(--linea); border-radius: var(--radio); background: var(--superficie); cursor: pointer; font: inherit; font-size: 0.88rem; color: var(--tinta-2); white-space: nowrap; }
.fm-boton b { color: var(--tinta); font-weight: 620; }
.fm-boton.activo { border-color: var(--acento); background: var(--acento-claro); }
.fm-velo { position: fixed; inset: 0; z-index: 38; }
.fm-panel { position: absolute; z-index: 39; top: calc(100% + 4px); inset-inline-start: 0; min-width: 240px; background: var(--superficie); border: 1px solid var(--linea); border-radius: 10px; box-shadow: var(--sombra-flotante); padding: 8px; display: flex; flex-direction: column; gap: 6px; }
.fm-lista { max-height: 280px; overflow: auto; display: flex; flex-direction: column; }
.fm-op { display: flex; gap: 8px; align-items: center; padding: 5px 6px; border-radius: 6px; font-size: 0.88rem; cursor: pointer; }
.fm-op:hover { background: var(--acento-claro); }
.fm-op input { accent-color: var(--acento); }
</style>
