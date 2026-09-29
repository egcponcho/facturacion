<script setup>
import { ref } from 'vue'
import { fmtNum } from '../utils'
import Icono from './Icono.vue'

// Zona para soltar o elegir un archivo. v-model: el File elegido (o null).
const props = defineProps({
  modelValue: { type: Object, default: null },
  acepta: { type: String, default: '.xlsx,.xlsm,.csv' },
  texto: { type: String, default: 'Drag the file here or choose it' },
  ayuda: { type: String, default: 'Excel (.xlsx) or CSV' },
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
  elegir(e.dataTransfer?.files?.[0])
}
function quitar() {
  emit('update:modelValue', null)
  if (entrada.value) entrada.value.value = ''
}
</script>

<template>
  <div v-if="props.modelValue" class="archivo-elegido">
    <span class="archivo-icono"><Icono nombre="archivo" :tam="20" /></span>
    <div class="archivo-datos">
      <b>{{ props.modelValue.name }}</b>
      <span class="ayuda">{{ fmtNum(props.modelValue.size / 1024, 0) }} KB</span>
    </div>
    <button type="button" class="btn btn-chico btn-fantasma" @click="entrada.click()">Change</button>
    <button type="button" class="btn-icono" aria-label="Remove file" @click="quitar"><Icono nombre="cerrar" :tam="16" /></button>
    <input ref="entrada" type="file" :accept="props.acepta" class="oculto-visual" @change="elegir($event.target.files[0])" />
  </div>
  <label v-else class="zona-carga" :class="{ encima }" @dragover.prevent="encima = true" @dragleave="encima = false" @drop.prevent="soltar">
    <span class="zona-icono"><Icono nombre="importar" :tam="22" /></span>
    <b>{{ props.texto }}</b>
    <span class="ayuda">{{ props.ayuda }}</span>
    <span class="btn btn-chico">Choose file</span>
    <input ref="entrada" type="file" :accept="props.acepta" class="oculto-visual" @change="elegir($event.target.files[0])" />
  </label>
</template>
