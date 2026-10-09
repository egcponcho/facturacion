<script setup>
import { t, tx } from '@/i18n/index.js'
import { onMounted, reactive, ref, watch } from 'vue'
import { api } from '@/nucleo/api'
import Icono from '@/componentes/Icono.vue'
import Seleccion from '@/componentes/Seleccion.vue'
import { fmtCode } from '@/modulos/clasificacion/formato.js'
import { fmtFecha } from '@/nucleo/utils'
import { errorApi } from '@/stores/ui'

// COMPANY KNOWLEDGE: lo que la empresa aprendió al clasificar. Solo ordena los
// candidatos que el dato oficial permite (historical_confidence); nunca crea
// códigos, DAI, impuestos ni regulaciones.
const props = defineProps({ edita: Boolean })
const vista = ref('historial')
const ORIGEN = { APROBACION: t('Approved'), CORRECCION: t('Correction'), ENSENADO: t('Remembered from the sheet'), IMPORTADO: t('Imported history') }
const VISTAS = [['historial', t('Classification history')], ['decisiones', t('Manual decisions and corrections')], ['palabras', t('Learned keywords')],
  ['sinonimos', t('Material synonyms')]]
const f = reactive({ pais: '', q: '', page: 1 })
const hist = ref({ items: [], total: 0 })
const palabras = ref([])
const sinonimos = ref([])
const resumen = ref(null)
const paises = ref([])  // los países configurados (Aranceles → Países), no una lista fija
api.get('/aranceles/paises').then((r) => (paises.value = r.map((p) => p.iso))).catch(() => {})

async function cargar() {
  try {
    if (vista.value === 'historial' || vista.value === 'decisiones') {
      hist.value = await api.get('/conocimiento/historial', { pais: f.pais || undefined, q: f.q || undefined, page: f.page, size: 50,
        origen: vista.value === 'decisiones' ? 'CORRECCION,ENSENADO' : undefined })
    } else if (vista.value === 'palabras') palabras.value = await api.get('/conocimiento/palabras')
    else sinonimos.value = await api.get('/conocimiento/sinonimos')
  } catch (e) {
    errorApi(e)
  }
}
onMounted(async () => {
  try {
    resumen.value = await api.get('/conocimiento')
  } catch (e) {
    errorApi(e)
  }
  cargar()
})
watch(vista, () => { f.page = 1; cargar() })

async function quitar(ruta, id) {
  if (!window.confirm(t('Remove this entry? It stops influencing the order of candidates.'))) return
  try {
    await api.del(`${ruta}/${id}`)
    cargar()
  } catch (e) {
    errorApi(e)
  }
}
const condTxt = (c) => Object.entries(c || {}).map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(', ') : v}`).join(' · ')
</script>

<template>
  <section>
    <p class="nota info"><Icono nombre="info" /><span>{{ t('Company knowledge only orders the candidates that official data allows (historical confidence). It never creates national lines, duties, taxes or regulations, and never changes official data.') }}</span></p>
    <div v-if="resumen" class="doc-meta">
      <span v-for="(n, k) in resumen.historial" :key="k">{{ ORIGEN[k] || k }} <b>{{ n }}</b></span>
      <span>{{ t('Keywords') }} <b>{{ resumen.palabras }}</b></span><span>{{ t('Synonyms') }} <b>{{ resumen.sinonimos }}</b></span>
    </div>
    <div class="pestanas-pildora mt-chico" role="tablist">
      <button v-for="[k, txt] in VISTAS" :key="k" type="button" role="tab" class="pildora" :aria-selected="vista === k" @click="vista = k">{{ txt }}</button>
    </div>

    <template v-if="vista === 'historial' || vista === 'decisiones'">
      <div class="filtros" v-filtros>
        <label class="buscador"><Icono nombre="buscar" :tam="16" /><input v-model="f.q" type="search" :placeholder="t('Code')" :aria-label="t('Search')" @change="cargar" /></label>
        <Seleccion v-model="f.pais" :aria-label="t('Country')" @change="cargar"><option value="">{{ t('All countries') }}</option>
          <option v-for="p in paises" :key="p" :value="p">{{ p }}</option></Seleccion>
      </div>
      <div class="tabla-marco">
        <table class="tabla" v-tarjetas>
          <thead><tr><th>{{ t('Country') }}</th><th>{{ t('Code') }}</th><th>{{ t('When (product data)') }}</th><th>{{ t('Origin') }}</th><th class="num">{{ t('Times') }}</th><th></th></tr></thead>
          <tbody>
            <tr v-for="x in hist.items" :key="x.id">
              <td>{{ tx(x.pais || 'HS') }}</td>
              <td class="codigo-sac">{{ fmtCode(x.codigo) }}
                <span v-if="x.linea_oficial === false" class="etiqueta aviso" :title="t('Not an official line today: it cannot be used')">{{ t('not official') }}</span></td>
              <td class="ayuda">{{ tx(condTxt(x.condiciones) || '—') }}<span v-if="x.nota" class="sub">{{ tx(x.nota) }}</span></td>
              <td><span class="etiqueta">{{ ORIGEN[x.origen] || x.origen }}</span></td>
              <td class="num">{{ x.conteo }}</td>
              <td class="num"><button v-if="props.edita" class="btn-icono" :aria-label="t('Remove')" @click="quitar('/conocimiento/historial', x.id)"><Icono nombre="basura" :tam="16" /></button></td>
            </tr>
            <tr v-if="!hist.items.length"><td colspan="6" class="vacio">{{ t('No history yet: it grows with each approval.') }}</td></tr>
          </tbody>
        </table>
      </div>
      <p class="ayuda">{{ t('{0} entries', [hist.total]) }}</p>
    </template>

    <div v-else-if="vista === 'palabras'" class="tabla-marco mt-chico">
      <table class="tabla" v-tarjetas>
        <thead><tr><th>{{ t('Phrase in the product name') }}</th><th>{{ t('Category') }}</th><th>{{ t('Answers it sets') }}</th><th>{{ t('Created') }}</th><th></th></tr></thead>
        <tbody>
          <tr v-for="x in palabras" :key="x.id">
            <td class="fuerte">{{ tx(x.frase) }}<span v-if="x.marca" class="sub">{{ tx(x.marca) }}</span></td><td>{{ tx(x.tipo) }}</td>
            <td class="ayuda">{{ tx(condTxt(x.atributos) || '—') }}</td><td>{{ fmtFecha(x.creado_en) }}</td>
            <td class="num"><button v-if="props.edita" class="btn-icono" :aria-label="t('Remove')" @click="quitar('/conocimiento/palabras', x.id)"><Icono nombre="basura" :tam="16" /></button></td>
          </tr>
          <tr v-if="!palabras.length"><td colspan="5" class="vacio">{{ t('No keywords learned yet.') }}</td></tr>
        </tbody>
      </table>
    </div>

    <div v-else class="tabla-marco mt-chico">
      <table class="tabla" v-tarjetas>
        <thead><tr><th>{{ t('Word') }}</th><th>{{ t('Counts as') }}</th><th>{{ t('Created') }}</th><th></th></tr></thead>
        <tbody>
          <tr v-for="x in sinonimos" :key="x.id">
            <td class="fuerte">{{ tx(x.palabra) }}</td><td>{{ tx(x.equivale) }}</td><td>{{ fmtFecha(x.creado_en) }}</td>
            <td class="num"><button v-if="props.edita" class="btn-icono" :aria-label="t('Remove')" @click="quitar('/conocimiento/sinonimos', x.id)"><Icono nombre="basura" :tam="16" /></button></td>
          </tr>
          <tr v-if="!sinonimos.length"><td colspan="4" class="vacio">{{ t('No synonyms learned yet.') }}</td></tr>
        </tbody>
      </table>
    </div>
  </section>
</template>
