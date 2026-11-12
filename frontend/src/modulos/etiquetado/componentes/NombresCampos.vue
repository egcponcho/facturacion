<script setup>
import { t, tx } from '@/i18n/index.js'
import { computed, onMounted, ref } from 'vue'
import { api } from '@/nucleo/api'
import Icono from '@/componentes/Icono.vue'
import TablaDatos from '@/componentes/TablaDatos.vue'
import { puede } from '@/stores/sesion'
import { avisar, errorApi } from '@/stores/ui'

// Los campos de las etiquetas con el nombre que les da la empresa (el que se
// ve al diseñar) y los que no se ofrecen. Los diseños que ya usan un campo
// oculto lo siguen imprimiendo; la clave técnica ({{articulo.codigo_barras}}) no cambia.
const campos = ref([])
const grupos = ref({})
const cambios = ref({}) // clave → { nombre, oculto }
const cargando = ref(false)
const guardando = ref(false)
const editable = computed(() => puede('etiquetas.configurar'))

async function cargar() {
  cargando.value = true
  try {
    const r = await api.get('/etiquetas/campos')
    grupos.value = r.grupos || {}
    campos.value = r.campos.filter((c) => c.grupo !== 'manual')
    cambios.value = Object.fromEntries(campos.value.filter((c) => c.propio || c.oculto)
      .map((c) => [c.clave, { nombre: c.propio ? c.etiqueta : '', oculto: c.oculto }]))
  } catch (e) {
    errorApi(e)
  } finally {
    cargando.value = false
  }
}
onMounted(cargar)

const de = (c) => cambios.value[c.clave] || { nombre: '', oculto: false }
function poner(c, prop, v) {
  cambios.value = { ...cambios.value, [c.clave]: { ...de(c), [prop]: v } }
}
const filas = computed(() => campos.value.map((c) => ({ ...c, grupoTxt: tx(grupos.value[c.grupo] || c.grupo), original: tx(c.etiqueta_original) })))
const columnas = computed(() => [
  { clave: 'grupoTxt', texto: t('Group'), prioridad: 2 },
  { clave: 'original', texto: t('Name in the system'), prioridad: 1 },
  { clave: 'nombre', texto: t('Name in your company'), prioridad: 1, filtro: false, ordenable: false },
  { clave: 'oculto', texto: t('Offer when designing'), prioridad: 1, filtro: false, ordenable: false },
  { clave: 'clave', texto: t('Key in the designs'), prioridad: 3 },
  { clave: 'origen', texto: t('Where it comes from'), prioridad: 3 },
])
const nPropios = computed(() => Object.values(cambios.value).filter((x) => x.nombre?.trim()).length)
const nOcultos = computed(() => Object.values(cambios.value).filter((x) => x.oculto).length)

async function guardar() {
  guardando.value = true
  try {
    const limpio = Object.fromEntries(Object.entries(cambios.value).filter(([, v]) => v.nombre?.trim() || v.oculto)
      .map(([k, v]) => [k, { nombre: (v.nombre || '').trim(), oculto: !!v.oculto }]))
    await api.put('/etiquetas/campos/propios', { campos: limpio })
    avisar(t('Field names saved.'))
    await cargar()
  } catch (e) {
    errorApi(e)
  } finally {
    guardando.value = false
  }
}
</script>

<template>
  <section class="panel nc">
    <header class="nc-cab">
      <div>
        <h3>{{ t('Field names') }}</h3>
        <p class="ayuda">{{ t('Give the fields the names your company uses and hide the ones it never prints. The key of each field does not change: designs keep working.') }}</p>
      </div>
      <span class="ayuda">{{ t('{0} renamed · {1} hidden', [nPropios, nOcultos]) }}</span>
      <button v-if="editable" type="button" class="btn btn-primario" :disabled="guardando" @click="guardar"><Icono nombre="check" :tam="15" />{{ t('Save') }}</button>
    </header>
    <TablaDatos tabla="etiquetas_nombres_campos" :columnas="columnas" :filas="filas" :cargando="cargando" :etiqueta="t('Field names')">
      <template #celda-nombre="{ fila: c }">
        <input class="nc-input" :value="de(c).nombre" :placeholder="c.original" maxlength="60" :disabled="!editable"
               :aria-label="t('Name in your company')" @input="poner(c, 'nombre', $event.target.value)" />
      </template>
      <template #celda-oculto="{ fila: c }">
        <label class="check"><input type="checkbox" :checked="!de(c).oculto" :disabled="!editable" @change="poner(c, 'oculto', !$event.target.checked)" />
          {{ de(c).oculto ? t('Hidden') : t('Yes') }}</label>
      </template>
      <template #celda-clave="{ fila: c }"><code v-text="`{{${c.clave}}}`"></code></template>
    </TablaDatos>
  </section>
</template>

<style scoped>
.nc { margin-bottom: 16px; }
.nc-cab { display: flex; gap: 12px; align-items: flex-start; flex-wrap: wrap; margin-bottom: 8px; }
.nc-cab > div { flex: 1 1 320px; }
.nc-cab h3 { margin: 0 0 4px; }
.nc-input { width: 100%; min-width: 140px; }
code { font-size: var(--t-xs); color: var(--tinta-3); }
</style>
