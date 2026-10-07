<script setup>
import { t, tx } from '../../i18n/index.js'
import { computed, onMounted, reactive, ref } from 'vue'
import { api } from '../../api'
import { filtrar } from '../../busqueda.js'
import Icono from '../Icono.vue'
import Interruptor from '../Interruptor.vue'
import { puede } from '../../stores/sesion'
import { avisar, errorApi } from '../../stores/ui'

// Vocabulario para buscar en el texto oficial del arancel (que está en
// español): un nombre en inglés o un término comercial y las palabras del
// texto oficial a las que equivale. Solo ayuda a encontrar candidatos.
const edita = puede('aranceles.editar')
const items = ref([])
const q = ref('')
const nueva = reactive({ palabra: '', equivale: '' })
async function cargar() {
  try {
    items.value = await api.get('/aranceles/busqueda')
  } catch (e) {
    errorApi(e)
  }
}
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
    <label class="buscador"><Icono nombre="buscar" :tam="16" /><input v-model="q" type="search" :placeholder="t('Search')" :aria-label="t('Search')" /></label>
    <div class="tabla-marco">
      <table class="tabla">
        <thead><tr><th>{{ t('Word') }}</th><th>{{ t('Words of the official text') }}</th><th>{{ t('Active') }}</th></tr></thead>
        <tbody>
          <tr v-if="edita" class="nueva">
            <td><input v-model="nueva.palabra" class="celda" :placeholder="t('e.g. drill')" :aria-label="t('Word')" maxlength="60" /></td>
            <td><input v-model="nueva.equivale" class="celda" :placeholder="t('e.g. taladro perforadora')" :aria-label="t('Words of the official text')" maxlength="300" /></td>
            <td><button class="btn btn-chico" :disabled="!nueva.palabra || !nueva.equivale" @click="agregar"><Icono nombre="mas" :tam="14" />{{ t('Add') }}</button></td>
          </tr>
          <tr v-for="x in lista.slice(0, 300)" :key="x.id" :class="{ apagada: !x.activo }">
            <td class="codigo">{{ tx(x.palabra) }}<br /><small class="ayuda">{{ tx(x.origen === 'MOTOR' ? t('Included') : t('Created by users')) }}</small></td>
            <td><input class="celda" :value="x.equivale" :disabled="!edita" :aria-label="t('Words of the official text')" maxlength="300" @change="guardar(x, 'equivale', $event.target.value)" /></td>
            <td><Interruptor :model-value="x.activo" :deshabilitado="!edita" :etiqueta="t('Active')" @update:model-value="guardar(x, 'activo', $event)" /></td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>

<style scoped>
h3 { margin: 0 0 6px; font-size: 1rem; display: flex; gap: 6px; align-items: center; }
.buscador { margin: 8px 0; max-width: 360px; }
.celda { width: 100%; min-width: 90px; }
.celda::placeholder { color: var(--tinta-3); }
.tabla-marco { max-height: 62vh; overflow-y: auto; }
tr.apagada td { opacity: 0.55; }
</style>
