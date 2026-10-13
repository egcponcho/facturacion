<script setup>
import { t, tx } from '@/i18n/index.js'
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { api } from '@/nucleo/api'
import Icono from '@/componentes/Icono.vue'
import Seleccion from '@/componentes/Seleccion.vue'
import TablaDatos from '@/componentes/TablaDatos.vue'
import { fmtCode } from '@/modulos/clasificacion/formato.js'
import { fmtFecha } from '@/nucleo/utils'
import { errorApi } from '@/stores/ui'
import { confirmar } from '@/stores/confirmar'

// COMPANY KNOWLEDGE: lo que la empresa aprendió al clasificar. Solo ordena los
// candidatos que el dato oficial permite (historical_confidence); nunca crea
// códigos, DAI, impuestos ni regulaciones.
const props = defineProps({ edita: Boolean })
const vista = ref('historial')
const ORIGEN = { APROBACION: t('Approved'), CORRECCION: t('Correction'), ENSENADO: t('Remembered from the sheet'), IMPORTADO: t('Imported history') }
const VISTAS = [['historial', t('Classification history')], ['decisiones', t('Manual decisions and corrections')], ['palabras', t('Learned keywords')],
  ['sinonimos', t('Material synonyms')]]
const f = reactive({ pais: '', q: '' })
const hist = ref({ items: [], total: 0 })
const palabras = ref([])
const sinonimos = ref([])
const resumen = ref(null)
const paises = ref([])  // los países configurados (Aranceles → Países), no una lista fija
api.get('/aranceles/paises').then((r) => (paises.value = r.map((p) => p.iso))).catch(() => {})

const cargando = ref(false)
const tablaH = ref(null)
const esHistorial = computed(() => vista.value === 'historial' || vista.value === 'decisiones')
// Historial y decisiones: paginados en el servidor, con filtro por columna allá
const filtrosH = () => ({ pais: f.pais || undefined, q: f.q || undefined, origen: vista.value === 'decisiones' ? 'CORRECCION,ENSENADO' : undefined })
let consultaH = null
async function cargarHistorial(c = consultaH) {
  if (!c) return
  consultaH = c
  cargando.value = true
  try {
    hist.value = await api.get('/conocimiento/historial', { ...filtrosH(), page: c.page, size: c.size, orden: c.orden || undefined,
      f: Object.keys(c.filtros).length ? JSON.stringify(c.filtros) : undefined })
  } catch (e) {
    errorApi(e)
  } finally {
    cargando.value = false
  }
}
const valoresH = (columna, buscar, otros) => api.get('/conocimiento/historial/valores', { columna, buscar, f: JSON.stringify(otros), ...filtrosH() })
async function cargar() {
  if (esHistorial.value) {
    if (tablaH.value && tablaH.value.pagina !== 1) tablaH.value.pagina = 1
    else cargarHistorial()
    return
  }
  cargando.value = true
  try {
    if (vista.value === 'palabras') palabras.value = await api.get('/conocimiento/palabras')
    else sinonimos.value = await api.get('/conocimiento/sinonimos')
  } catch (e) {
    errorApi(e)
  } finally {
    cargando.value = false
  }
}
const columnasH = computed(() => [
  { clave: 'pais', texto: t('Country'), prioridad: 1, textoValor: (v) => v || 'HS' },
  { clave: 'codigo', texto: t('Code'), fija: true, prioridad: 1, textoValor: (v) => fmtCode(v) },
  { clave: 'condiciones', texto: t('When (product data)'), prioridad: 2, filtro: false, ordenable: false },
  { clave: 'origen', texto: t('Origin'), prioridad: 2, opciones: Object.entries(ORIGEN) },
  { clave: 'conteo', texto: t('Times'), num: true, prioridad: 2 },
])
const columnasP = computed(() => [
  { clave: 'frase', texto: t('Phrase in the product name'), fija: true, prioridad: 1 },
  { clave: 'tipo', texto: t('Category'), prioridad: 1 },
  { clave: 'marca', texto: t('Brand'), prioridad: 3, inicial: false, textoValor: (v) => v || '—' },
  { clave: 'atributos', texto: t('Answers it sets'), prioridad: 2, filtro: false, ordenable: false },
  { clave: 'creado_en', texto: t('Created'), prioridad: 3, valor: (x) => (x.creado_en || '').slice(0, 10), textoValor: (v) => (v ? fmtFecha(v) : '—') },
])
const columnasS = computed(() => [
  { clave: 'palabra', texto: t('Word'), fija: true, prioridad: 1 },
  { clave: 'equivale', texto: t('Counts as'), prioridad: 1 },
  { clave: 'creado_en', texto: t('Created'), prioridad: 3, valor: (x) => (x.creado_en || '').slice(0, 10), textoValor: (v) => (v ? fmtFecha(v) : '—') },
])
onMounted(async () => {
  try {
    resumen.value = await api.get('/conocimiento')
  } catch (e) {
    errorApi(e)
  }
  if (!esHistorial.value) cargar()
})
// El historial lo pide su tabla al aparecer; las otras listas, al cambiar de pestaña
watch(vista, () => { if (!esHistorial.value) cargar() })

async function quitar(ruta, id) {
  if (!(await confirmar(t('Remove this entry? It stops influencing the order of candidates.'), { boton: t('Remove'), peligro: true }))) return
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

    <TablaDatos v-if="esHistorial" ref="tablaH" :key="vista" :tabla="`conocimiento_${vista}`" modo="servidor" :columnas="columnasH" :filas="hist.items"
                :total="hist.total" :cargando="cargando" :valores="valoresH" :externos="{ q: f.q, pais: f.pais }" :etiqueta="t('Classification history')"
                @consulta="cargarHistorial" @vista="(x) => { Object.assign(f, { q: x.q || '', pais: x.pais || '' }); cargar() }"
                @limpiar-externos="Object.assign(f, { q: '', pais: '' }); cargar()">
      <template #barra>
        <label class="buscador"><Icono nombre="buscar" :tam="16" /><input v-model="f.q" type="search" :placeholder="t('Code')" :aria-label="t('Search')" @change="cargar" /></label>
      </template>
      <template #filtros>
        <Seleccion v-model="f.pais" :aria-label="t('Country')" @change="cargar"><option value="">{{ t('All countries') }}</option>
          <option v-for="p in paises" :key="p" :value="p">{{ p }}</option></Seleccion>
      </template>
      <template #celda-pais="{ fila: x }">{{ tx(x.pais || 'HS') }}</template>
      <template #celda-codigo="{ fila: x }"><span class="codigo-sac">{{ fmtCode(x.codigo) }}</span>
        <span v-if="x.linea_oficial === false" class="etiqueta aviso" :title="t('Not an official line today: it cannot be used')">{{ t('not official') }}</span></template>
      <template #celda-condiciones="{ fila: x }"><div class="ayuda envolver-celda">{{ tx(condTxt(x.condiciones) || '—') }}<span v-if="x.nota" class="sub">{{ tx(x.nota) }}</span></div></template>
      <template #celda-origen="{ fila: x }"><span class="etiqueta ms-0">{{ ORIGEN[x.origen] || x.origen }}</span></template>
      <template v-if="props.edita" #acciones="{ fila: x }"><button type="button" class="btn-icono" :aria-label="t('Remove')" @click="quitar('/conocimiento/historial', x.id)"><Icono nombre="basura" :tam="16" /></button></template>
      <template #vacio>{{ t('No history yet: it grows with each approval.') }}</template>
    </TablaDatos>

    <TablaDatos v-else-if="vista === 'palabras'" tabla="conocimiento_palabras" :columnas="columnasP" :filas="palabras" :cargando="cargando" :etiqueta="t('Learned keywords')">
      <template #celda-frase="{ fila: x }"><span class="fuerte">{{ tx(x.frase) }}</span><span v-if="x.marca" class="sub">{{ tx(x.marca) }}</span></template>
      <template #celda-tipo="{ fila: x }">{{ tx(x.tipo) }}</template>
      <template #celda-atributos="{ fila: x }"><div class="ayuda envolver-celda">{{ tx(condTxt(x.atributos) || '—') }}</div></template>
      <template #celda-creado_en="{ fila: x }">{{ fmtFecha(x.creado_en) }}</template>
      <template v-if="props.edita" #acciones="{ fila: x }"><button type="button" class="btn-icono" :aria-label="t('Remove')" @click="quitar('/conocimiento/palabras', x.id)"><Icono nombre="basura" :tam="16" /></button></template>
      <template #vacio>{{ t('No keywords learned yet.') }}</template>
    </TablaDatos>

    <TablaDatos v-else tabla="conocimiento_sinonimos" :columnas="columnasS" :filas="sinonimos" :cargando="cargando" :etiqueta="t('Material synonyms')">
      <template #celda-palabra="{ fila: x }"><span class="fuerte">{{ tx(x.palabra) }}</span></template>
      <template #celda-equivale="{ fila: x }">{{ tx(x.equivale) }}</template>
      <template #celda-creado_en="{ fila: x }">{{ fmtFecha(x.creado_en) }}</template>
      <template v-if="props.edita" #acciones="{ fila: x }"><button type="button" class="btn-icono" :aria-label="t('Remove')" @click="quitar('/conocimiento/sinonimos', x.id)"><Icono nombre="basura" :tam="16" /></button></template>
      <template #vacio>{{ t('No synonyms learned yet.') }}</template>
    </TablaDatos>
  </section>
</template>

<style scoped>
.envolver-celda { min-width: 220px; max-width: 460px; white-space: normal; }
</style>
