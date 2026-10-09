<script setup>
import { t, tx } from '@/i18n/index.js'
import { ref, watch } from 'vue'
import { fechaTexto, pref, textoAFecha } from '@/stores/preferencias'
import Icono from './Icono.vue'

// Fecha en el formato del perfil (MM/DD/YYYY por defecto). Se escribe a mano
// o se elige en el calendario; el valor (v-model) siempre es YYYY-MM-DD.
defineOptions({ inheritAttrs: false })
const props = defineProps({
  modelValue: { type: String, default: '' },
  min: { type: String, default: undefined },
  max: { type: String, default: undefined },
  required: Boolean,
})
const emit = defineEmits(['update:modelValue', 'change'])
const texto = ref(fechaTexto(props.modelValue))
const error = ref(false)
const nativo = ref(null)
watch(() => [props.modelValue, pref.formato_fecha], () => { texto.value = fechaTexto(props.modelValue); error.value = false })

function fijar(iso) {
  if (iso && ((props.min && iso < props.min) || (props.max && iso > props.max))) {
    error.value = true
    return
  }
  error.value = false
  texto.value = fechaTexto(iso)
  if (iso !== (props.modelValue || '')) {
    emit('update:modelValue', iso)
    emit('change', iso)
  }
}
function leer() {
  const iso = textoAFecha(texto.value)
  if (iso === null) { error.value = true; return }
  fijar(iso)
}
function abrir() {
  try { nativo.value?.showPicker() } catch { nativo.value?.focus() }
}
</script>

<template>
  <span class="campo-fecha" :class="{ invalida: error }">
    <input v-bind="$attrs" v-model="texto" :inputmode="pref.formato_fecha.includes('MMM') ? 'text' : 'numeric'" type="text" autocomplete="off" class="entrada"
           :placeholder="pref.formato_fecha" :required="props.required" :aria-invalid="error"
           :title="tx(error ? t('Write the date as {0}', [pref.formato_fecha]) : pref.formato_fecha)"
           @change="leer" @keydown.enter.prevent="leer" />
    <button type="button" class="btn-icono" :aria-label="t('Open calendar')" tabindex="-1" @click="abrir"><Icono nombre="calendario" :tam="15" /></button>
    <input ref="nativo" class="nativo" type="date" tabindex="-1" aria-hidden="true" :value="props.modelValue" :min="props.min" :max="props.max"
           @change="fijar($event.target.value)" />
  </span>
</template>

<style scoped>
.campo-fecha { position: relative; display: inline-flex; align-items: center; min-width: 0; width: 100%; max-width: 100%; }
.campo-fecha .entrada { width: 100%; min-width: 9.5em; padding-inline-end: 34px; }
.campo-fecha .btn-icono { position: absolute; inset-inline-end: 4px; }
.campo-fecha .nativo { position: absolute; inset-inline-end: 0; bottom: 0; width: 1px; height: 1px; opacity: 0; pointer-events: none; }
.campo-fecha.invalida .entrada { border-color: var(--error); }
</style>
