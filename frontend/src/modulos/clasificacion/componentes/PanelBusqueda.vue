<script setup>
import { t, tx } from '@/i18n/index.js'
import { computed, onMounted, reactive, ref } from 'vue'
import { api } from '@/nucleo/api'
import { filtrar } from '@/nucleo/busqueda.js'
import Icono from '@/componentes/Icono.vue'
import Interruptor from '@/componentes/Interruptor.vue'
import TablaDatos from '@/componentes/TablaDatos.vue'
import { puede } from '@/stores/sesion'
import { avisar, errorApi } from '@/stores/ui'

// Vocabulario para buscar en el texto oficial del arancel (que está en
// español): un nombre en inglés o un término comercial y las palabras del
// texto oficial a las que equivale. Solo ayuda a encontrar candidatos.
const edita = puede('clasificacion.configurar')
const items = ref([])
const q = ref('')
const nueva = reactive({ palabra: '', equivale: '' })
const cargando = ref(true)
async function cargar() {
  try {
    items.value = await api.get('/aranceles/busqueda')
  } catch (e) {
    errorApi(e)
  } finally {
    cargando.value = false
  }
}
const columnas = computed(() => [
  { clave: 'palabra', texto: t('Word'), fija: true, prioridad: 1 },
  { clave: 'equivale', texto: t('Words of the official text'), prioridad: 1 },
  { clave: 'origen', texto: t('Origin'), prioridad: 3, opciones: [['MOTOR', t('Included')], ['USUARIO', t('Created by users')]],
    valor: (x) => (x.origen === 'MOTOR' ? 'MOTOR' : 'USUARIO') },
  { clave: 'activo', texto: t('Active'), prioridad: 2, opciones: [[true, t('Yes')], [false, t('No')]] },
])
onMounted(cargar)
const lista = computed(() => filtrar(items.value, q.value, (x) => [x.palabra, x.equivale]))
async function guardar(x, k, v) {
  try {
    Object.assign(x, await api.patch(`/aranceles/busqueda/${x.id}`, { [k]: v }))
  } catch (e) {
    errorApi(e)
    cargar()
  }
}
async function agregar() {
  try {
    await api.post('/aranceles/busqueda', { ...nueva })
    Object.assign(nueva, { palabra: '', equivale: '' })
    avisar(t('Search word added.'))
    cargar()
  } catch (e) {
    errorApi(e)
  }
}
</script>

<template>
  <section class="panel">
    <h3><Icono nombre="buscar" :tam="16" />{{ t('Search vocabulary') }} <span class="cuenta">{{ tx(items.length) }}</span></h3>
    <p class="ayuda">{{ t('The official tariff text is in Spanish. Here a word in English or a commercial term says which words of the official text it means (drill → taladro). It only helps find candidates; it never confirms a code.') }}</p>
    <form v-if="edita" class="agregar" @submit.prevent="agregar">
      <strong>{{ t('New word') }}</strong>
      <input v-model="nueva.palabra" class="entrada" :placeholder="t('e.g. drill')" :aria-label="t('Word')" maxlength="60" />
      <input v-model="nueva.equivale" class="entrada ancha" :placeholder="t('e.g. taladro perforadora')" :aria-label="t('Words of the official text')" maxlength="300" />
      <button class="btn btn-chico" type="submit" :disabled="!nueva.palabra || !nueva.equivale"><Icono nombre="mas" :tam="14" />{{ t('Add') }}</button>
    </form>
    <TablaDatos tabla="familias_vocabulario" :columnas="columnas" :filas="lista" :cargando="cargando" :clase-fila="(x) => ({ apagada: !x.activo })"
                :externos="{ q }" :etiqueta="t('Search vocabulary')" @vista="(x) => (q = x.q || '')">
      <template #barra>
        <label class="buscador"><Icono nombre="buscar" :tam="16" /><input v-model="q" type="search" :placeholder="t('Search')" :aria-label="t('Search')" /></label>
      </template>
      <template #celda-palabra="{ fila: x }"><span class="codigo">{{ tx(x.palabra) }}</span></template>
      <template #celda-equivale="{ fila: x }"><input class="celda ancha" :value="x.equivale" :disabled="!edita" :aria-label="t('Words of the official text')" maxlength="300" @change="guardar(x, 'equivale', $event.target.value)" /></template>
      <template #celda-origen="{ fila: x }"><span class="etiqueta ms-0" :class="x.origen === 'MOTOR' ? 'acento' : ''">{{ x.origen === 'MOTOR' ? t('Included') : t('Created by users') }}</span></template>
      <template #celda-activo="{ fila: x }"><Interruptor :model-value="x.activo" :deshabilitado="!edita" :etiqueta="t('Active')" @update:model-value="guardar(x, 'activo', $event)" /></template>
      <template #vacio>{{ t('No results.') }}</template>
    </TablaDatos>
  </section>
</template>

<style scoped>
h3 { margin: 0 0 6px; font-size: 1rem; display: flex; gap: 6px; align-items: center; }
.celda { width: 100%; min-width: 90px; }
.celda::placeholder { color: var(--tinta-3); }
.celda.ancha { min-width: 260px; }
:deep(tr.apagada > td) { opacity: 0.55; }
.agregar { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin: 10px 0 14px; }
.agregar .entrada { width: auto; flex: 1 1 140px; min-width: 0; }
.agregar .entrada.ancha { flex: 2 1 260px; }
</style>
