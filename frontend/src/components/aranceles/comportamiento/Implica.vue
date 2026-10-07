<script setup>
import { t, tx } from '../../../i18n/index.js'
import { computed } from 'vue'
import Icono from '../../Icono.vue'
import SelectBusqueda from '../../SelectBusqueda.vue'

// Lo que elegir esta opción completa en otras preguntas (si están vacías).
const props = defineProps({
  modelValue: { type: Object, default: null },
  atributos: { type: Array, default: () => [] },
  propio: { type: String, default: '' },
  deshabilitado: Boolean,
})
const emit = defineEmits(['update:modelValue'])
const filas = computed(() => Object.entries(props.modelValue || {}))
const elegibles = computed(() => props.atributos.filter((a) => a.codigo !== props.propio && ['select', 'boolean', 'multi_select'].includes(a.tipo_dato))
  .map((a) => ({ valor: a.codigo, texto: a.etiqueta, sub: a.codigo })))
const def = (k) => props.atributos.find((a) => a.codigo === k)
const opciones = (k) => (def(k)?.tipo_dato === 'boolean' ? [{ valor: true, texto: t('Yes') }, { valor: false, texto: t('No') }]
  : (def(k)?.opciones_min || []).map((o) => ({ valor: o.codigo, texto: o.etiqueta })))
function emitir(pares) {
  const o = Object.fromEntries(pares.filter(([k]) => k))
  emit('update:modelValue', Object.keys(o).length ? o : null)
}
const cambiarCampo = (i, k) => emitir(filas.value.map((p, j) => (j === i ? [k, null] : p)))
const cambiarValor = (i, v) => emitir(filas.value.map((p, j) => (j === i ? [p[0], v] : p)))
const quitar = (i) => emitir(filas.value.filter((_, j) => j !== i))
const agregar = () => emit('update:modelValue', { ...(props.modelValue || {}), '': null })
</script>

<template>
  <div class="cfilas">
    <p v-if="!filas.length" class="ayuda">{{ t('Choosing it fills in nothing else.') }}</p>
    <div v-for="([k, v], i) in filas" :key="i" class="cfila linea">
      <SelectBusqueda :model-value="k" :opciones="elegibles" :etiqueta="t('Question')" :placeholder="t('Question…')" :deshabilitado="deshabilitado" class="crece" @update:model-value="cambiarCampo(i, $event)" />
      <span class="ayuda">=</span>
      <select class="entrada" :value="String(v ?? '')" :disabled="deshabilitado || !k" :aria-label="t('Value')"
              @change="cambiarValor(i, opciones(k).find((o) => String(o.valor) === $event.target.value)?.valor ?? null)">
        <option value="">{{ t('Choose…') }}</option>
        <option v-for="o in opciones(k)" :key="String(o.valor)" :value="String(o.valor)">{{ tx(o.texto) }}</option>
      </select>
      <button v-if="!deshabilitado" type="button" class="btn-icono" :aria-label="t('Remove')" @click="quitar(i)"><Icono nombre="basura" :tam="15" /></button>
    </div>
    <button v-if="!deshabilitado" type="button" class="btn btn-chico" @click="agregar"><Icono nombre="mas" :tam="14" />{{ t('Add answer it fills in') }}</button>
  </div>
</template>
