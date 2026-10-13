<script setup>
import { t, tx } from '@/i18n/index.js'
import { computed } from 'vue'
import FiltroMulti from '@/componentes/FiltroMulti.vue'

// Cómo se arma la descripción aduanera de una categoría. Las alternativas
// («si») y las palabras por valor («como») se conservan y se editan como JSON.
const props = defineProps({
  modelValue: { type: Object, default: null },
  atributos: { type: Array, default: () => [] },
  deshabilitado: Boolean,
})
const emit = defineEmits(['update:modelValue'])
const p = computed(() => props.modelValue || {})
const partes = computed(() => props.atributos.filter((a) => a.codigo.startsWith('comp.')).map((a) => ({ valor: a.codigo.slice(5), texto: a.etiqueta })))
const preguntas = computed(() => props.atributos.filter((a) => !a.codigo.startsWith('comp.')).map((a) => ({ valor: a.codigo, texto: a.etiqueta })))
function poner(k, v) {
  const n = { ...p.value }
  if (v === '' || v == null || (Array.isArray(v) && !v.length)) delete n[k]
  else n[k] = v
  emit('update:modelValue', Object.keys(n).length ? n : null)
}
</script>

<template>
  <div class="cfilas">
    <div class="linea">
      <label class="ccampo"><span>{{ t('Name in the description') }}</span>
        <input class="entrada" :value="p.nombre || ''" :disabled="deshabilitado" :placeholder="t('e.g. TAZA')" @change="poner('nombre', $event.target.value.trim())" /></label>
      <label class="ccampo"><span>{{ t('Commercial name') }}</span>
        <input class="entrada" :value="p.comercial || ''" :disabled="deshabilitado" @change="poner('comercial', $event.target.value.trim())" /></label>
    </div>
    <div class="linea">
      <label class="ccampo ancho"><span>{{ t('Material text') }}</span>
        <input class="entrada" :value="p.material || ''" :disabled="deshabilitado" :placeholder="t('e.g. DE {clase}, or DE {material_principal}')" @change="poner('material', $event.target.value.trim())" /></label>
      <label class="ccampo"><span>{{ t('Composition parts it reads') }}</span>
        <FiltroMulti :model-value="p.clase || []" :opciones="partes" :etiqueta="t('Parts')" vacio="—" @update:model-value="poner('clase', $event)" /></label>
    </div>
    <div class="linea">
      <label class="ccampo"><span>{{ t('Questions it needs') }}</span>
        <FiltroMulti :model-value="p.requiere || []" :opciones="preguntas" :etiqueta="t('Questions')" vacio="—" @update:model-value="poner('requiere', $event)" /></label>
      <label class="ccampo ancho"><span>{{ t('Text when something is missing') }}</span>
        <input class="entrada" :value="p.si_falta || ''" :disabled="deshabilitado" @change="poner('si_falta', $event.target.value.trim())" /></label>
    </div>
    <p v-if="p.si?.length || Object.keys(p.como || {}).length" class="ayuda">
      {{ tx(t('It also has {0} alternatives and {1} word maps: edit them as JSON.', [p.si?.length || 0, Object.keys(p.como || {}).length])) }}</p>
    <p class="ayuda">{{ t('In the material text, {clase} is the material class read from the parts and {code} is the answer to a question.') }}</p>
  </div>
</template>
