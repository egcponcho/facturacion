<script setup>
import { t, tx } from '@/i18n/index.js'
import { ref, watch } from 'vue'

// Campo de configuración avanzada en JSON (patrones, derivación, textos de
// aduana…). Comprueba aquí que sea JSON; el servidor valida el contenido
// (atributos, opciones y partes que existen) y dice qué falla y dónde.
const props = defineProps({
  modelValue: { type: [Object, Array, String, Number, Boolean, null], default: null },
  etiqueta: { type: String, required: true },
  ayuda: { type: String, default: '' },
  ejemplo: { type: String, default: '' },
  deshabilitado: { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelValue', 'valido'])
const texto = ref('')
const error = ref('')
const vacio = (v) => v == null || (Array.isArray(v) && !v.length) || (typeof v === 'object' && !Object.keys(v).length)
watch(() => props.modelValue, (v) => {
  let actual = null
  try {
    actual = texto.value.trim() ? JSON.parse(texto.value) : null
  } catch {
    actual = undefined
  }
  if (JSON.stringify(actual) !== JSON.stringify(v)) texto.value = vacio(v) ? '' : JSON.stringify(v, null, 2)
}, { immediate: true })
function cambio() {
  const s = texto.value.trim()
  if (!s) {
    error.value = ''
    emit('valido', true)
    emit('update:modelValue', null)
    return
  }
  try {
    const v = JSON.parse(s)
    error.value = ''
    emit('valido', true)
    emit('update:modelValue', v)
  } catch (e) {
    error.value = t('It is not valid JSON: {0}', [e.message])
    emit('valido', false)
  }
}
function usarEjemplo() {
  texto.value = props.ejemplo
  cambio()
}
</script>

<template>
  <div class="editor-json">
    <div class="cab">
      <span class="lbl">{{ tx(etiqueta) }}</span>
      <button v-if="ejemplo && !deshabilitado" type="button" class="btn-texto" @click="usarEjemplo">{{ t('Use an example') }}</button>
    </div>
    <p v-if="ayuda" class="ayuda">{{ tx(ayuda) }}</p>
    <textarea v-model="texto" :disabled="deshabilitado" :aria-label="etiqueta" spellcheck="false" rows="5" :class="{ mal: error }" @input="cambio" />
    <p v-if="error" class="error" role="alert">{{ tx(error) }}</p>
  </div>
</template>

<style scoped>
.editor-json { display: flex; flex-direction: column; gap: 4px; margin-bottom: 10px; }
.cab { display: flex; justify-content: space-between; align-items: baseline; gap: 8px; }
.lbl { font-size: 0.84rem; font-weight: 600; }
textarea { width: 100%; font-family: var(--mono); font-size: 0.8rem; resize: vertical; min-height: 84px; }
textarea.mal { border-color: var(--error); }
.error { color: var(--error); font-size: 0.8rem; margin: 0; }
.ayuda { margin: 0; }
</style>
