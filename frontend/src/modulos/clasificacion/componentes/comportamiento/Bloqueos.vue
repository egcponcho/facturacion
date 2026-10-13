<script setup>
import { t } from '@/i18n/index.js'
import Icono from '@/componentes/Icono.vue'
import EditorCondiciones from '@/modulos/clasificacion/componentes/EditorCondiciones.vue'

// Combinaciones imposibles: cuando se cumplen las condiciones no se puede
// elegir, y el mensaje dice por qué.
const props = defineProps({
  modelValue: { type: Array, default: () => [] },
  atributos: { type: Array, default: () => [] },
  deshabilitado: Boolean,
})
const emit = defineEmits(['update:modelValue'])
function cambiar(i, k, v) {
  const lista = (props.modelValue || []).map((b) => ({ ...b }))
  lista[i][k] = v
  emit('update:modelValue', lista)
}
const agregar = () => emit('update:modelValue', [...(props.modelValue || []), { condiciones: [], mensaje: '' }])
const quitar = (i) => emit('update:modelValue', props.modelValue.filter((_, j) => j !== i))
</script>

<template>
  <div class="cfilas">
    <p v-if="!modelValue?.length" class="ayuda">{{ t('Nothing blocks it.') }}</p>
    <div v-for="(b, i) in modelValue || []" :key="i" class="cfila bloque">
      <div class="linea">
        <label class="ccampo ancho"><span class="req">{{ t('Message (why it is not possible)') }}</span>
          <input class="entrada" :value="b.mensaje" maxlength="300" :disabled="deshabilitado" @change="cambiar(i, 'mensaje', $event.target.value)" /></label>
        <button v-if="!deshabilitado" type="button" class="btn-icono" :aria-label="t('Remove')" @click="quitar(i)"><Icono nombre="basura" :tam="15" /></button>
      </div>
      <EditorCondiciones :model-value="b.condiciones || []" :atributos="atributos" @update:model-value="cambiar(i, 'condiciones', $event)" />
    </div>
    <button v-if="!deshabilitado" type="button" class="btn btn-chico" @click="agregar"><Icono nombre="mas" :tam="14" />{{ t('Add block') }}</button>
  </div>
</template>
