<script setup>
import { t, tx } from '@/i18n/index.js'
import { computed, onMounted, reactive, ref } from 'vue'
import { api } from '@/nucleo/api'
import Icono from '@/componentes/Icono.vue'
import Seleccion from '@/componentes/Seleccion.vue'
import TablaDatos from '@/componentes/TablaDatos.vue'
import { puede } from '@/stores/sesion'
import { avisar, errorApi } from '@/stores/ui'

// La familia de etiquetado de cada artículo (variante): se asigna de a uno,
// a los elegidos o a todos los que cumplen el filtro. No es una segunda ficha
// del producto: solo la referencia a la familia.
const tabla = ref(null)
const filtros = reactive({ q: '', familia: '' })
const datos = ref({ items: [], total: 0 })
const familias = ref([])
const cargando = ref(false)
const seleccion = ref([])
const destino = ref('')
const editable = computed(() => puede('etiquetas.familias'))

const columnas = computed(() => [
  { clave: 'sku', texto: t('SKU'), fija: true, prioridad: 1, ordenable: false, filtro: false },
  { clave: 'descripcion', texto: t('Description'), prioridad: 2, ordenable: false, filtro: false },
  { clave: 'color', texto: t('Color'), prioridad: 2, ordenable: false, filtro: false },
  { clave: 'talla', texto: t('Size'), prioridad: 2, ordenable: false, filtro: false },
  { clave: 'marca', texto: t('Brand'), prioridad: 3, ordenable: false, filtro: false },
  { clave: 'grupo', texto: t('Group'), prioridad: 3, ordenable: false, filtro: false },
  { clave: 'familia', texto: t('Labeling family'), prioridad: 1, ordenable: false, filtro: false },
])
let ultima = null
async function consultar(c = ultima) {
  if (!c) return
  ultima = c
  cargando.value = true
  try {
    datos.value = await api.get('/etiquetas/articulos', { q: filtros.q || undefined, familia: filtros.familia || undefined, page: c.page, size: c.size })
  } catch (e) {
    errorApi(e)
  } finally {
    cargando.value = false
  }
}
function recargar() {
  seleccion.value = []
  if (tabla.value?.pagina !== 1) tabla.value.pagina = 1
  else consultar()
}
let espera
const buscar = () => {
  clearTimeout(espera)
  espera = setTimeout(recargar, 300)
}
onMounted(() => api.get('/etiquetas/familias').then((r) => (familias.value = r)).catch(() => {}))

async function asignar(todos) {
  const familia_id = destino.value === 'ninguna' ? null : Number(destino.value)
  const cuerpo = todos ? { familia_id, filtro: { q: filtros.q || undefined, familia: filtros.familia || undefined } } : { familia_id, ids: seleccion.value }
  try {
    const r = await api.post('/etiquetas/articulos/familia', cuerpo)
    avisar(t('{0} items changed.', [r.cambiados]))
    recargar()
  } catch (e) {
    errorApi(e)
  }
}
</script>

<template>
  <TablaDatos ref="tabla" tabla="etiquetas_articulos" modo="servidor" :columnas="columnas" :filas="datos.items" :total="datos.total" :cargando="cargando"
              :seleccionable="editable" v-model:seleccion="seleccion" :etiqueta="t('Items')" :externos="{ q: filtros.q, familia: filtros.familia }"
              @consulta="consultar">
    <template #barra>
      <label class="buscador"><Icono nombre="buscar" :tam="16" />
        <input v-model="filtros.q" type="search" :placeholder="t('Search SKU, style, color or UPC')" :aria-label="t('Search')" @input="buscar" /></label>
    </template>
    <template #filtros>
      <Seleccion v-model="filtros.familia" :aria-label="t('Labeling family')" @change="recargar">
        <option value="">{{ t('Any family') }}</option>
        <option value="sin">{{ t('Without family') }}</option>
        <option v-for="f in familias" :key="f.id" :value="f.id">{{ tx(f.nombre) }}</option>
      </Seleccion>
    </template>
    <template #celda-sku="{ fila: a }"><strong class="codigo">{{ a.sku }}</strong><span class="sub">{{ a.estilo }}</span></template>
    <template #celda-familia="{ fila: a }">
      <span v-if="a.familia" class="etiqueta ms-0">{{ tx(a.familia) }}</span>
      <span v-else class="etiqueta aviso ms-0">{{ t('Without family') }}</span>
    </template>
    <template #vacio>{{ t('No items match these filters.') }}</template>
  </TablaDatos>

  <div v-if="editable" class="barra-asignar panel mt">
    <label class="campo"><span>{{ t('Labeling family') }}</span>
      <Seleccion v-model="destino" :aria-label="t('Labeling family')">
        <option value="">{{ t('Choose…') }}</option>
        <option value="ninguna">{{ t('No family (remove it)') }}</option>
        <option v-for="f in familias.filter((x) => x.activa)" :key="f.id" :value="f.id">{{ tx(f.nombre) }}</option>
      </Seleccion>
    </label>
    <button type="button" class="btn btn-primario" :disabled="!destino || !seleccion.length" @click="asignar(false)">{{ t('Apply to the {0} selected', [seleccion.length]) }}</button>
    <button type="button" class="btn" :disabled="!destino || !datos.total" @click="asignar(true)">{{ t('Apply to all {0} of the filter', [datos.total]) }}</button>
  </div>
</template>

<style scoped>
.barra-asignar { display: flex; flex-wrap: wrap; gap: 12px; align-items: flex-end; }
.barra-asignar .campo { min-width: 240px; }
</style>
