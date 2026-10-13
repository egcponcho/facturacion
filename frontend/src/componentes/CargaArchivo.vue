<script setup>
import { t, tx } from '@/i18n/index.js'
import { ref } from 'vue'
import { fmtNum } from '@/nucleo/utils'
import Icono from './Icono.vue'

// Elegir un archivo: el único control de archivo del sistema (no hay
// <input type="file"> a la vista). v-model: el File elegido (o null).
// - Zona grande para soltar o elegir (cargas de Excel, documentos).
// - `compacta`: una línea con el aspecto de un campo, para formularios y barras.
const props = defineProps({
  modelValue: { type: Object, default: null },
  acepta: { type: String, default: '.xlsx,.xlsm,.csv' },
  texto: { type: String, default: t('Drag the file here or choose it') },
  ayuda: { type: String, default: t('Excel (.xlsx) or CSV') },
  compacta: Boolean,
  etiqueta: { type: String, default: '' },
  deshabilitado: Boolean,
})
const emit = defineEmits(['update:modelValue'])
const encima = ref(false)
const entrada = ref(null)

function elegir(archivo) {
  if (!archivo) return
  emit('update:modelValue', archivo)
}
function soltar(e) {
  encima.value = false
  if (!props.deshabilitado) elegir(e.dataTransfer?.files?.[0])
}
function quitar() {
  emit('update:modelValue', null)
  if (entrada.value) entrada.value.value = ''
}
const kb = (a) => t('{0} KB', [fmtNum(a.size / 1024, 0)])
</script>

<template>
  <div v-if="props.compacta" class="archivo-campo" :class="{ encima, elegido: !!props.modelValue, deshabilitado: props.deshabilitado }"
       @dragover.prevent="encima = true" @dragleave="encima = false" @drop.prevent="soltar">
    <Icono nombre="archivo" :tam="16" class="archivo-campo-icono" />
    <span v-if="props.modelValue" class="archivo-campo-nombre"><b>{{ tx(props.modelValue.name) }}</b> <span class="ayuda">{{ kb(props.modelValue) }}</span></span>
    <span v-else class="archivo-campo-nombre apagado">{{ t('No file chosen') }}</span>
    <label class="btn btn-chico">{{ props.modelValue ? t('Change') : t('Choose file') }}
      <input ref="entrada" type="file" :accept="props.acepta" class="oculto-visual" :disabled="props.deshabilitado"
             :aria-label="tx(props.etiqueta) || t('Choose file')" @change="elegir($event.target.files[0])" /></label>
    <button v-if="props.modelValue" type="button" class="btn-icono" :aria-label="t('Remove file')" @click="quitar"><Icono nombre="cerrar" :tam="15" /></button>
  </div>
  <div v-else-if="props.modelValue" class="archivo-elegido">
    <span class="archivo-icono"><Icono nombre="archivo" :tam="20" /></span>
    <div class="archivo-datos">
      <b>{{ tx(props.modelValue.name) }}</b>
      <span class="ayuda">{{ kb(props.modelValue) }}</span>
    </div>
    <button type="button" class="btn btn-chico btn-fantasma" @click="entrada.click()">{{ t('Change') }}</button>
    <button type="button" class="btn-icono" :aria-label="t('Remove file')" @click="quitar"><Icono nombre="cerrar" :tam="16" /></button>
    <input ref="entrada" type="file" :accept="props.acepta" class="oculto-visual" @change="elegir($event.target.files[0])" />
  </div>
  <label v-else class="zona-carga" :class="{ encima }" @dragover.prevent="encima = true" @dragleave="encima = false" @drop.prevent="soltar">
    <span class="zona-icono"><Icono nombre="importar" :tam="22" /></span>
    <b>{{ tx(props.texto) }}</b>
    <span class="ayuda">{{ tx(props.ayuda) }}</span>
    <span class="btn btn-chico">{{ t('Choose file') }}</span>
    <input ref="entrada" type="file" :accept="props.acepta" class="oculto-visual" @change="elegir($event.target.files[0])" />
  </label>
</template>
