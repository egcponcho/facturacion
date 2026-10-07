<script setup>
// Traducciones del catálogo: cada pregunta, opción, categoría y familia se
// configura en inglés y aquí se traduce a los idiomas de la interfaz. Así la
// ficha sale en el idioma de cada proveedor o comprador.
import { t, tx, IDIOMAS } from '../../i18n/index.js'
import { onMounted, reactive, ref } from 'vue'
import { api } from '../../api'
import Seleccion from '../Seleccion.vue'
import { puede } from '../../stores/sesion'
import { avisar, errorApi } from '../../stores/ui'

const edita = puede('clasificacion.configurar')
const f = reactive({ idioma: 'es', q: '', pendientes: false })
const datos = ref({ items: [], total: 0, faltan: 0 })
let espera

async function cargar() {
  try {
    datos.value = await api.get(`/familias/traducciones/${f.idioma}`, { q: f.q || undefined, pendientes: f.pendientes || undefined })
  } catch (e) {
    errorApi(e)
  }
}
function buscar() {
  clearTimeout(espera)
  espera = setTimeout(cargar, 300)
}
async function guardar(x, valor) {
  if ((valor || '').trim() === (x.traduccion || '')) return
  try {
    const r = await api.put(`/familias/traducciones/${f.idioma}`, { texto: x.texto, traduccion: valor })
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
    <div class="filtros">
      <Seleccion v-model="f.idioma" :aria-label="t('Language')" @change="cargar">
        <option v-for="i in IDIOMAS.filter((x) => x.codigo !== 'en')" :key="i.codigo" :value="i.codigo">{{ i.nombre }}</option>
      </Seleccion>
      <label class="buscador"><input v-model="f.q" type="search" :placeholder="t('Search text or translation')" :aria-label="t('Search')" @input="buscar" /></label>
      <label class="check"><input v-model="f.pendientes" type="checkbox" @change="cargar" /><span>{{ t('Only missing') }}</span></label>
      <span class="ayuda separar">{{ t('{0} of {1} translated', [datos.total - datos.faltan, datos.total]) }}</span>
    </div>
    <div class="tabla-marco tabla-fija">
      <table class="tabla">
        <thead><tr><th>{{ t('Text (English)') }}</th><th>{{ t('Translation') }}</th></tr></thead>
        <tbody>
          <tr v-for="x in datos.items" :key="x.texto">
            <td class="envolver">{{ x.texto }}</td>
            <td><input class="celda ancha" :value="x.traduccion || ''" :disabled="!edita" :placeholder="t('Not translated: shown in English')"
                       :aria-label="t('Translation of {0}', [x.texto])" @change="guardar(x, $event.target.value)" /></td>
          </tr>
          <tr v-if="!datos.items.length"><td colspan="2" class="vacio">{{ t('Nothing to show with these filters.') }}</td></tr>
        </tbody>
      </table>
    </div>
  </section>
</template>

<style scoped>
.ancha { width: 100%; }
td.envolver { width: 45%; }
</style>
