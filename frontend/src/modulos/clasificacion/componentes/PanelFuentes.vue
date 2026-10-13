<script setup>
import { t, tx } from '@/i18n/index.js'
import { computed, onMounted, ref } from 'vue'
import { api } from '@/nucleo/api'
import { filtrar } from '@/nucleo/busqueda.js'
import Icono from '@/componentes/Icono.vue'
import { fechaTexto } from '@/stores/preferencias'
import { avisar, errorApi } from '@/stores/ui'
import { puede } from '@/stores/sesion'
import Modal from '@/componentes/Modal.vue'
import TablaDatos from '@/componentes/TablaDatos.vue'
import CampoFecha from '@/componentes/CampoFecha.vue'

// Fuentes oficiales y versiones de los datos: de dónde sale cada dato, si la
// versión está publicada (no se sobrescribe) o es dinámica (se toma una
// instantánea en cada carga) y su vigencia.
const datos = ref({ fuentes: [], versiones: [] })
const q = ref('')
const qv = ref('')
const cargando = ref(true)
onMounted(async () => {
  try {
    datos.value = await api.get('/aranceles/oficial/fuentes')
  } catch (e) {
    errorApi(e)
  } finally {
    cargando.value = false
  }
})
const edita = puede('aranceles.editar')
// Verificar una fuente: quién comparó qué documento o enlace con la publicación oficial, y cuándo
const modal = ref(null)
async function verificar() {
  const m = modal.value
  try {
    const f = await api.post(`/aranceles/oficial/fuentes/${m.id}/verificar`, { documento: m.documento || null, url: m.url || null,
      verificado_en: m.verificado_en || null })
    datos.value.fuentes = datos.value.fuentes.map((x) => (x.id === f.id ? f : x))
    modal.value = null
    avisar(t('Verification recorded.'))
  } catch (e) {
    errorApi(e)
  }
}
const ESTADO = { PUBLICADA: ['ok', t('Published')], DINAMICA: ['acento', t('Dynamic')], BORRADOR: ['', t('Draft')], ARCHIVADA: ['', t('Archived')] }
const fuentes = computed(() => filtrar(datos.value.fuentes, q.value, (f) => [f.codigo, f.ambito, f.autoridad, f.dataset, f.uso]))
const versiones = computed(() => filtrar(datos.value.versiones, qv.value, (v) => [v.codigo, v.dataset, v.etiqueta, v.fuente]))
const fecha = (v) => (v ? fechaTexto(v) : '—')
const columnasV = computed(() => [
  { clave: 'codigo', texto: t('Version'), fija: true, prioridad: 1 },
  { clave: 'dataset', texto: t('Dataset'), prioridad: 1 },
  { clave: 'estado', texto: t('Status'), prioridad: 2, opciones: Object.entries(ESTADO).map(([k, [, txt]]) => [k, txt]) },
  { clave: 'vigente_desde', texto: t('Valid from'), prioridad: 3, textoValor: fecha },
  { clave: 'vigente_hasta', texto: t('Valid to'), prioridad: 3, textoValor: fecha },
  { clave: 'fuente', texto: t('Source'), prioridad: 2, textoValor: (v) => v || '—' },
  { clave: 'nota', texto: t('Notes'), prioridad: 3, filtro: false, ordenable: false },
])
const columnasF = computed(() => [
  { clave: 'codigo', texto: t('Source'), fija: true, prioridad: 1 },
  { clave: 'ambito', texto: t('Scope'), prioridad: 2 },
  { clave: 'autoridad', texto: t('Authority · dataset'), prioridad: 1 },
  { clave: 'acceso', texto: t('Access'), prioridad: 3, textoValor: (v) => v || '—' },
  { clave: 'nota_version', texto: t('Version / status'), prioridad: 3, filtro: false, ordenable: false },
  { clave: 'verificada', texto: t('Verification'), prioridad: 2, opciones: [[true, t('Verified')], [false, t('Not verified')]], valor: (f) => !!f.verificado_en },
])
</script>

<template>
  <section>
    <h3 class="titulo-seccion">{{ t('Dataset versions') }}</h3>
    <TablaDatos tabla="aranceles_versiones" :columnas="columnasV" :filas="versiones" :cargando="cargando" :externos="{ q: qv }" :etiqueta="t('Dataset versions')"
                @vista="(x) => (qv = x.q || '')" @limpiar-externos="qv = ''">
      <template #barra>
        <label class="buscador"><Icono nombre="buscar" :tam="16" /><input v-model="qv" type="search" :placeholder="t('Version, dataset or source')" :aria-label="t('Search versions')" /></label>
      </template>
      <template #celda-codigo="{ fila: v }"><span class="codigo fuerte">{{ tx(v.codigo) }}</span></template>
      <template #celda-dataset="{ fila: v }">{{ tx(v.dataset) }}<span class="sub">{{ tx(v.etiqueta) }}</span></template>
      <template #celda-estado="{ fila: v }"><span class="etiqueta ms-0" :class="ESTADO[v.estado]?.[0]">{{ tx(ESTADO[v.estado]?.[1] || v.estado) }}</span></template>
      <template #celda-vigente_desde="{ fila: v }">{{ fecha(v.vigente_desde) }}</template>
      <template #celda-vigente_hasta="{ fila: v }">{{ fecha(v.vigente_hasta) }}</template>
      <template #celda-fuente="{ fila: v }"><span class="codigo">{{ tx(v.fuente || '—') }}</span></template>
      <template #celda-nota="{ fila: v }"><div class="nota ayuda">{{ tx(v.nota) }}</div></template>
      <template #vacio>{{ t('No results.') }}</template>
    </TablaDatos>
    <h3 class="titulo-seccion">{{ t('Official sources') }}</h3>
    <TablaDatos tabla="aranceles_fuentes" :columnas="columnasF" :filas="fuentes" :cargando="cargando" :externos="{ q }" :etiqueta="t('Official sources')"
                @vista="(x) => (q = x.q || '')" @limpiar-externos="q = ''">
      <template #barra>
        <label class="buscador"><Icono nombre="buscar" :tam="16" /><input v-model="q" type="search" :placeholder="t('Source, authority, country or dataset')" :aria-label="t('Search')" /></label>
      </template>
      <template #celda-codigo="{ fila: f }"><span class="codigo fuerte">{{ tx(f.codigo) }}</span></template>
      <template #celda-ambito="{ fila: f }"><span class="etiqueta ms-0">{{ tx(f.ambito) }}</span></template>
      <template #celda-autoridad="{ fila: f }">
        <div class="nota">{{ tx(f.autoridad) }}<span class="sub">{{ tx(f.dataset) }}</span>
          <a v-if="f.url" :href="f.url" target="_blank" rel="noopener" class="enlace sub">{{ tx(f.url.replace(/^https?:\/\//, '').slice(0, 60)) }}</a></div>
      </template>
      <template #celda-acceso="{ fila: f }">{{ tx(f.acceso || '—') }}<span v-if="f.autenticacion && f.autenticacion !== 'No'" class="sub">{{ t('Authentication: {0}', [f.autenticacion]) }}</span></template>
      <template #celda-nota_version="{ fila: f }"><div class="nota ayuda">{{ tx(f.nota_version) }}</div></template>
      <template #celda-verificada="{ fila: f }">
        <div class="ayuda">
          <span v-if="f.verificado_en" class="etiqueta ok ms-0">{{ t('Verified {0}', [fechaTexto(f.verificado_en)]) }}</span>
          <span v-else class="etiqueta aviso ms-0">{{ t('Not verified') }}</span>
          <span v-if="f.verificado_por" class="sub">{{ tx(f.verificado_por) }}</span>
          <span v-if="f.documento" class="sub">{{ tx(f.documento) }}</span>
          <span v-for="p in f.problemas" :key="p" class="sub texto-error">{{ tx(p) }}</span>
          <button v-if="edita" type="button" class="btn-texto" @click="modal = { id: f.id, codigo: f.codigo, documento: f.documento || '', url: f.url || '', verificado_en: '' }">{{ t('Record verification') }}</button>
        </div>
      </template>
      <template #vacio>{{ t('No results.') }}</template>
    </TablaDatos>
    <Modal v-if="modal" :titulo="t('Verify {0}', [modal.codigo])" @cerrar="modal = null">
      <p class="ayuda">{{ t('Record that the source was checked against its official publication. Without a verification the source does not back any official data.') }}</p>
      <div class="rejilla-campos">
        <label class="campo col-completa"><span>{{ t('Official document or dataset checked') }}</span><input v-model="modal.documento" class="entrada" maxlength="300" /></label>
        <label class="campo col-completa"><span>{{ t('Official link') }}</span><input v-model="modal.url" class="entrada" maxlength="400" type="url" /></label>
        <label class="campo"><span>{{ t('Verified on') }}</span><CampoFecha v-model="modal.verificado_en" /></label>
      </div>
      <template #pie>
        <button class="btn" @click="modal = null">{{ t('Cancel') }}</button>
        <button class="btn btn-primario" @click="verificar">{{ t('Record verification') }}</button>
      </template>
    </Modal>
  </section>
</template>

<style scoped>
.titulo-seccion { font-size: 1rem; margin: 14px 0 8px; }
.sub.enlace { display: block; }
.nota { min-width: 200px; max-width: 420px; white-space: normal; }
</style>
