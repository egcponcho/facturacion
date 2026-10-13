<script setup>
import { tx } from '@/i18n/index.js'
import Seleccion from './Seleccion.vue'

// Opciones excluyentes de un filtro (vista, estado, período). En escritorio,
// botones segmentados; en tableta y celular (≤ 900 px) se pliegan en una sola
// lista para que la barra de filtros no ocupe varios renglones.
// opciones: [[valor, texto, cuenta?]]
const props = defineProps({
  modelValue: { type: [String, Number, Boolean], default: '' },
  opciones: { type: Array, required: true },
  etiqueta: { type: String, required: true },
})
const emit = defineEmits(['update:modelValue', 'change'])
function elegir(v) {
  emit('update:modelValue', v)
  emit('change', v)
}
const textoLista = ([, txt, n]) => `${tx(props.etiqueta)}: ${tx(txt)}${n ? ` (${n})` : ''}`
</script>

<template>
  <div class="segmentos-resp" :class="{ plegable: props.opciones.length > 2 }">
    <div class="segmentos" role="group" :aria-label="tx(props.etiqueta)">
      <button v-for="[v, txt, n] in props.opciones" :key="String(v)" type="button" class="segmento" :aria-pressed="props.modelValue === v" @click="elegir(v)">
        {{ tx(txt) }}<span v-if="n" class="cuenta">{{ tx(n) }}</span>
      </button>
    </div>
    <Seleccion class="seg-lista" :model-value="props.modelValue" :aria-label="tx(props.etiqueta)" @change="elegir">
      <option v-for="o in props.opciones" :key="String(o[0])" :value="o[0]">{{ textoLista(o) }}</option>
    </Seleccion>
  </div>
</template>
