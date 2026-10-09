<script setup>
import { t, tx } from '@/i18n/index.js'
import { ref } from 'vue'
import EditorJson from '@/modulos/clasificacion/componentes/EditorJson.vue'
import Bloqueos from './Bloqueos.vue'
import Derivacion from './Derivacion.vue'
import Implica from './Implica.vue'
import Patrones from './Patrones.vue'
import Plantilla from './Plantilla.vue'
import TextosAduana from './TextosAduana.vue'

// Un campo del comportamiento de una pregunta u opción, con su editor visual.
// «Editar como JSON» queda solo para casos avanzados; el servidor valida igual.
const props = defineProps({
  tipo: { type: String, required: true }, // derivacion | patrones | patrones_falso | texto_aduana | bloqueo | implica | plantilla
  modelValue: { type: [Object, Array, null], default: null },
  atributos: { type: Array, default: () => [] },
  atributo: { type: Object, default: null },
  etiqueta: { type: String, required: true },
  ayuda: { type: String, default: '' },
  ejemplo: { type: String, default: '' },
  deshabilitado: Boolean,
})
const emit = defineEmits(['update:modelValue', 'valido'])
const comoJson = ref(false)
const EDITOR = { derivacion: Derivacion, patrones: Patrones, patrones_falso: Patrones, texto_aduana: TextosAduana, bloqueo: Bloqueos, implica: Implica, plantilla: Plantilla }
function alternar() {
  comoJson.value = !comoJson.value
  emit('valido', true)
}
</script>

<template>
  <fieldset class="comportamiento">
    <legend>{{ tx(etiqueta) }}</legend>
    <p v-if="ayuda" class="ayuda">{{ tx(ayuda) }}</p>
    <EditorJson v-if="comoJson" :model-value="modelValue" :etiqueta="etiqueta" :ejemplo="ejemplo" :deshabilitado="deshabilitado"
                @update:model-value="emit('update:modelValue', $event)" @valido="emit('valido', $event)" />
    <component :is="EDITOR[tipo]" v-else :model-value="modelValue" :atributos="atributos" :atributo="atributo" :propio="atributo?.codigo"
               :deshabilitado="deshabilitado" @update:model-value="emit('update:modelValue', $event)" />
    <button type="button" class="btn-texto avanzado" @click="alternar">{{ tx(comoJson ? t('Back to the form') : t('Edit as JSON (advanced)')) }}</button>
  </fieldset>
</template>

<style scoped>
.comportamiento { border: 1px solid var(--linea); border-radius: var(--radio); padding: 10px 12px 8px; margin: 0 0 12px; display: grid; gap: 8px; min-width: 0; }
.comportamiento legend { font-weight: 650; font-size: 0.92rem; padding: 0 4px; }
.comportamiento .ayuda { margin: 0; }
.avanzado { justify-self: end; font-size: 0.8rem; }
.comportamiento :deep(.cfilas) { display: grid; gap: 8px; }
.comportamiento :deep(.cfila.bloque) { border: 1px solid var(--linea-suave); border-radius: 9px; padding: 8px; display: grid; gap: 6px; background: var(--superficie-2); }
.comportamiento :deep(.linea) { display: flex; gap: 8px; align-items: flex-end; flex-wrap: wrap; }
.comportamiento :deep(.ccampo) { display: flex; flex-direction: column; gap: 3px; font-size: 0.8rem; color: var(--tinta-2); min-width: 140px; flex: 1; }
.comportamiento :deep(.ccampo.ancho) { flex: 3; min-width: 200px; }
.comportamiento :deep(.ccampo.corto) { flex: 0 0 90px; min-width: 90px; }
.comportamiento :deep(.ccheck) { display: inline-flex; gap: 6px; align-items: center; font-size: 0.82rem; padding-bottom: 8px; }
.comportamiento :deep(.crece) { flex: 1; min-width: 180px; }
.comportamiento :deep(.btn-chico) { justify-self: start; }
</style>
