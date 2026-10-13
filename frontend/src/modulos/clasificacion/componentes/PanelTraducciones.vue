<script setup>
// Traducciones del catálogo: cada pregunta, opción, categoría y familia se
// configura en inglés y aquí se traduce a los idiomas de la interfaz. Así la
// ficha sale en el idioma de cada proveedor o comprador.
import { t, IDIOMAS } from '@/i18n/index.js'
import { computed, onMounted, reactive, ref } from 'vue'
import { api } from '@/nucleo/api'
import { filtrar } from '@/nucleo/busqueda.js'
import Icono from '@/componentes/Icono.vue'
import SelectBusqueda from '@/componentes/SelectBusqueda.vue'
import TablaDatos from '@/componentes/TablaDatos.vue'
import { puede } from '@/stores/sesion'
import { avisar, errorApi } from '@/stores/ui'

const edita = puede('clasificacion.configurar')
const f = reactive({ idioma: 'es', q: '', pendientes: false })
const datos = ref({ items: [], total: 0, faltan: 0 })
const cargando = ref(true)

// Llegan todos los textos del idioma; la búsqueda, «solo los que faltan» y los
// filtros de columna se aplican aquí y la tabla pagina.
async function cargar() {
  cargando.value = true
  try {
    datos.value = await api.get(`/familias/traducciones/${f.idioma}`)
  } catch (e) {
    errorApi(e)
  } finally {
    cargando.value = false
  }
}
const lista = computed(() => filtrar(datos.value.items.filter((x) => !f.pendientes || !x.traduccion), f.q, (x) => [x.texto, x.traduccion]))
const columnas = computed(() => [
  { clave: 'texto', texto: t('Text (English)'), fija: true, prioridad: 1 },
  { clave: 'traduccion', texto: t('Translation'), prioridad: 1 },
  { clave: 'estado', texto: t('Status'), prioridad: 3, opciones: [['ok', t('Translated')], ['falta', t('Missing')]],
    valor: (x) => (x.traduccion ? 'ok' : 'falta') },
])
const opcionesIdioma = IDIOMAS.filter((x) => x.codigo !== 'en').map((i) => ({ valor: i.codigo, texto: i.nombre }))
async function guardar(x, valor) {
  if ((valor || '').trim() === (x.traduccion || '')) return
  try {
    const r = await api.put(`/familias/traducciones/${f.idioma}`, { texto: x.texto, traduccion: valor })
    if (!x.traduccion && r.traduccion) datos.value.faltan--
    else if (x.traduccion && !r.traduccion) datos.value.faltan++
    x.traduccion = r.traduccion
    avisar(t('Translation saved. It shows the next time users sign in.'))
  } catch (e) {
    errorApi(e)
  }
}
onMounted(cargar)
</script>

<template>
  <section class="panel">
    <div class="panel-cabeza">
      <div>
        <h2>{{ t('Translations') }}</h2>
        <p class="sub-panel">{{ t('Questions, options, categories and families are set up in English and translated here, so each person sees the technical sheet in their own language.') }}</p>
      </div>
    </div>
    <TablaDatos tabla="familias_traducciones" :columnas="columnas" :filas="lista" :cargando="cargando" clave-fila="texto" :por-pagina="50"
                :externos="{ q: f.q, pendientes: f.pendientes ? '1' : '' }" :etiqueta="t('Translations')"
                @vista="(x) => Object.assign(f, { q: x.q || '', pendientes: x.pendientes === '1' })">
      <template #barra>
        <label class="buscador"><Icono nombre="buscar" :tam="16" /><input v-model="f.q" type="search" :placeholder="t('Search text or translation')" :aria-label="t('Search')" /></label>
      </template>
      <template #filtros>
        <SelectBusqueda v-if="opcionesIdioma.length > 1" v-model="f.idioma" :opciones="opcionesIdioma" :etiqueta="t('Language')" @update:model-value="cargar" />
        <label class="check"><input v-model="f.pendientes" type="checkbox" /><span>{{ t('Only missing') }}</span></label>
        <span class="ayuda separar">{{ t('{0} of {1} translated', [datos.total - datos.faltan, datos.total]) }}</span>
      </template>
      <template #celda-texto="{ fila: x }"><span class="envolver texto">{{ x.texto }}</span></template>
      <template #celda-traduccion="{ fila: x }">
        <input class="celda ancha" :value="x.traduccion || ''" :disabled="!edita" :placeholder="t('Not translated: shown in English')"
               :aria-label="t('Translation of {0}', [x.texto])" @change="guardar(x, $event.target.value)" />
      </template>
      <template #celda-estado="{ fila: x }"><span class="etiqueta ms-0" :class="x.traduccion ? 'ok' : 'aviso'">{{ x.traduccion ? t('Translated') : t('Missing') }}</span></template>
      <template #vacio>{{ t('Nothing to show with these filters.') }}</template>
    </TablaDatos>
  </section>
</template>

<style scoped>
.ancha { width: 100%; min-width: 260px; }
.texto { display: block; min-width: 240px; max-width: 520px; white-space: normal; }
</style>
