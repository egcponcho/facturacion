<script setup>
import { t, tx } from '@/i18n/index.js'
import { ref } from 'vue'
import Icono from '@/componentes/Icono.vue'
import EditorCondiciones from '@/modulos/clasificacion/componentes/EditorCondiciones.vue'

// Cómo se reconoce en el texto del producto: una fila por patrón (palabras o
// expresión, dónde buscar, prioridad, palabras que lo anulan y condiciones).
// Las claves avanzadas (y, y_en, nombre) se conservan tal cual.
const props = defineProps({
  modelValue: { type: Array, default: () => [] },
  atributos: { type: Array, default: () => [] },
  deshabilitado: Boolean,
})
const emit = defineEmits(['update:modelValue'])
const partes = () => props.atributos.filter((a) => a.codigo.startsWith('comp.'))
const DONDE = [['todo', t('Name, use and composition')], ['estilo', t('Style name')], ['uso', t('Use')], ['uso_comp', t('Use and composition')], ['tallas', t('Sizes')]]
const abiertas = ref({})

function cambiar(i, k, v) {
  const lista = (props.modelValue || []).map((p) => ({ ...p }))
  if (v === '' || v == null || (Array.isArray(v) && !v.length)) delete lista[i][k]
  else lista[i][k] = v
  emit('update:modelValue', lista)
}
const agregar = () => emit('update:modelValue', [...(props.modelValue || []), { re: '', en: 'todo', prioridad: 10 }])
const quitar = (i) => emit('update:modelValue', props.modelValue.filter((_, j) => j !== i))
const lista = (txt) => txt.split(',').map((x) => x.trim()).filter(Boolean)
</script>

<template>
  <div class="cfilas">
    <p v-if="!modelValue?.length" class="ayuda">{{ t('No patterns: it is never recognized by itself.') }}</p>
    <div v-for="(p, i) in modelValue || []" :key="i" class="cfila bloque">
      <div class="linea">
        <label class="ccampo ancho"><span>{{ t('Words or pattern') }}</span>
          <input class="entrada" :value="p.re || ''" :disabled="deshabilitado" :placeholder="t('e.g. lid|tapa')" @change="cambiar(i, 're', $event.target.value.trim())" /></label>
        <label class="ccampo"><span>{{ t('Look in') }}</span>
          <select class="entrada" :value="p.en || 'todo'" :disabled="deshabilitado" @change="cambiar(i, 'en', $event.target.value)">
            <option v-for="[v, l] in DONDE" :key="v" :value="v">{{ tx(l) }}</option>
            <option v-for="a in partes()" :key="a.codigo" :value="a.codigo">{{ t('Composition: {0}', [a.etiqueta]) }}</option>
          </select></label>
        <label class="ccampo corto"><span>{{ t('Priority') }}</span>
          <input class="entrada" type="number" step="1" :value="p.prioridad ?? ''" :disabled="deshabilitado" @change="cambiar(i, 'prioridad', $event.target.value === '' ? null : parseInt($event.target.value, 10))" /></label>
        <button v-if="!deshabilitado" type="button" class="btn-icono" :aria-label="t('Remove')" @click="quitar(i)"><Icono nombre="basura" :tam="15" /></button>
      </div>
      <div class="linea">
        <label class="ccampo ancho"><span>{{ t('Not when the text also says (comma separated)') }}</span>
          <input class="entrada" :value="(p.no || []).join(', ')" :disabled="deshabilitado" @change="cambiar(i, 'no', lista($event.target.value))" /></label>
        <label class="ccheck"><input type="checkbox" :checked="!!p.defecto" :disabled="deshabilitado" @change="cambiar(i, 'defecto', $event.target.checked || null)" />{{ t('Default when nothing else matches') }}</label>
      </div>
      <button type="button" class="btn-texto" @click="abiertas[i] = !abiertas[i]">
        {{ tx(p.cuando?.length ? t('Only when ({0} conditions)', [p.cuando.length]) : t('Only when… (optional)')) }}</button>
      <EditorCondiciones v-if="abiertas[i]" :model-value="p.cuando || []" :atributos="atributos" @update:model-value="cambiar(i, 'cuando', $event)" />
    </div>
    <button v-if="!deshabilitado" type="button" class="btn btn-chico" @click="agregar"><Icono nombre="mas" :tam="14" />{{ t('Add pattern') }}</button>
  </div>
</template>
