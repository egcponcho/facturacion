<script setup>
import { t, tx } from '@/i18n/index.js'
import { ref } from 'vue'
import Icono from '@/componentes/Icono.vue'
import EditorCondiciones from '@/modulos/clasificacion/componentes/EditorCondiciones.vue'

// Lo que aporta a la descripción aduanera: una frase, un nombre o un nombre
// comercial, con su orden. Varias filas son alternativas: va la primera cuya
// condición se cumple. Una sola fila se guarda como objeto.
const props = defineProps({
  modelValue: { type: [Object, Array], default: null },
  atributos: { type: Array, default: () => [] },
  deshabilitado: Boolean,
})
const emit = defineEmits(['update:modelValue'])
const filas = () => (Array.isArray(props.modelValue) ? props.modelValue : props.modelValue ? [props.modelValue] : [])
const abiertas = ref({})
function emitir(lista) {
  emit('update:modelValue', !lista.length ? null : lista.length === 1 && !lista[0].cuando?.length ? lista[0] : lista)
}
function cambiar(i, k, v) {
  const lista = filas().map((x) => ({ ...x }))
  if (v === '' || v == null || (Array.isArray(v) && !v.length)) delete lista[i][k]
  else lista[i][k] = v
  emitir(lista)
}
const agregar = () => emitir([...filas(), { frase: '' }])
const quitar = (i) => emitir(filas().filter((_, j) => j !== i))
</script>

<template>
  <div class="cfilas">
    <p v-if="!filas().length" class="ayuda">{{ t('It adds nothing to the customs description.') }}</p>
    <div v-for="(x, i) in filas()" :key="i" class="cfila bloque">
      <div class="linea">
        <label class="ccampo ancho"><span>{{ t('Phrase') }}</span>
          <input class="entrada" :value="x.frase || ''" maxlength="200" :disabled="deshabilitado" :placeholder="t('e.g. WITH LID')" @change="cambiar(i, 'frase', $event.target.value.trim())" /></label>
        <label class="ccampo"><span>{{ t('Name') }}</span>
          <input class="entrada" :value="x.nombre || ''" maxlength="200" :disabled="deshabilitado" @change="cambiar(i, 'nombre', $event.target.value.trim())" /></label>
        <label class="ccampo"><span>{{ t('Commercial name') }}</span>
          <input class="entrada" :value="x.comercial || ''" maxlength="200" :disabled="deshabilitado" @change="cambiar(i, 'comercial', $event.target.value.trim())" /></label>
        <label class="ccampo corto"><span>{{ t('Order') }}</span>
          <input class="entrada" type="number" step="1" :value="x.orden ?? ''" :disabled="deshabilitado" @change="cambiar(i, 'orden', $event.target.value === '' ? null : parseInt($event.target.value, 10))" /></label>
        <button v-if="!deshabilitado" type="button" class="btn-icono" :aria-label="t('Remove')" @click="quitar(i)"><Icono nombre="basura" :tam="15" /></button>
      </div>
      <button type="button" class="btn-texto" @click="abiertas[i] = !abiertas[i]">
        {{ tx(x.cuando?.length ? t('Only when ({0} conditions)', [x.cuando.length]) : t('Only when… (optional)')) }}</button>
      <EditorCondiciones v-if="abiertas[i]" :model-value="x.cuando || []" :atributos="atributos" @update:model-value="cambiar(i, 'cuando', $event)" />
    </div>
    <button v-if="!deshabilitado" type="button" class="btn btn-chico" @click="agregar"><Icono nombre="mas" :tam="14" />{{ tx(filas().length ? t('Add alternative') : t('Add text')) }}</button>
  </div>
</template>
