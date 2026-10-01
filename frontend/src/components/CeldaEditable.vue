<script setup>
import { tx } from '../i18n/index.js'
import { ref, watch } from 'vue'

// Guarda al salir del campo o con Enter; Escape deshace.
// Si el guardado falla, vuelve al valor anterior.
const props = defineProps({
  valor: { type: [String, Number], default: null },
  tipo: { type: String, default: 'text' },
  guardar: { type: Function, required: true },
  etiqueta: { type: String, default: '' },
  min: { type: Number, default: undefined },
  paso: { type: String, default: 'any' },
  ancho: { type: String, default: '' },
  vaciaTexto: { type: String, default: '' },
})
const local = ref(props.valor ?? '')
const estado = ref('')
watch(() => props.valor, (v) => (local.value = v ?? ''))

async function confirmar() {
  const original = props.valor ?? ''
  let nuevo = local.value
  if (props.tipo === 'number') nuevo = nuevo === '' || nuevo === null ? null : Number(nuevo)
  else nuevo = String(nuevo).trim()
  if (String(nuevo ?? '') === String(original)) return
  estado.value = 'guardando'
  try {
    await props.guardar(nuevo)
    estado.value = ''
  } catch {
    estado.value = 'error'
    local.value = original
    setTimeout(() => (estado.value = ''), 2500)
  }
}

function tecla(e) {
  if (e.key === 'Enter') e.target.blur()
  if (e.key === 'Escape') {
    local.value = props.valor ?? ''
    e.target.blur()
  }
}
</script>

<template>
  <input
    v-model="local"
    class="celda"
    :class="[estado, { num: props.tipo === 'number' }]"
    :type="props.tipo"
    :min="props.min"
    :step="props.paso"
    :aria-label="tx(props.etiqueta)"
    :placeholder="tx(props.vaciaTexto)"
    :style="props.ancho ? { width: props.ancho } : null"
    @change="confirmar"
    @keydown="tecla"
  />
</template>
