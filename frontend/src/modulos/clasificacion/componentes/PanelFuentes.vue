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

// Fuentes oficiales y versiones de los datos: de dónde sale cada dato, si la
// versión está publicada (no se sobrescribe) o es dinámica (se toma una
// instantánea en cada carga) y su vigencia.
const datos = ref({ fuentes: [], versiones: [] })
const q = ref('')
onMounted(async () => {
  try {
    datos.value = await api.get('/aranceles/oficial/fuentes')
  } catch (e) {
    errorApi(e)
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
const versiones = computed(() => filtrar(datos.value.versiones, q.value, (v) => [v.codigo, v.dataset, v.etiqueta, v.fuente]))
</script>

<template>
  <section>
    <div class="filtros" v-filtros>
      <label class="buscador"><Icono nombre="buscar" :tam="16" /><input v-model="q" type="search" :placeholder="t('Source, authority, country or dataset')" :aria-label="t('Search')" /></label>
    </div>
    <h3 class="titulo-seccion">{{ t('Dataset versions') }}</h3>
    <div class="tabla-marco">
      <table class="tabla" v-tarjetas>
        <thead><tr><th>{{ t('Version') }}</th><th>{{ t('Dataset') }}</th><th>{{ t('Status') }}</th><th>{{ t('Valid from') }}</th><th>{{ t('Valid to') }}</th><th>{{ t('Source') }}</th><th>{{ t('Notes') }}</th></tr></thead>
        <tbody>
          <tr v-for="v in versiones" :key="v.id">
            <td class="codigo fuerte">{{ tx(v.codigo) }}</td>
            <td>{{ tx(v.dataset) }}<span class="sub">{{ tx(v.etiqueta) }}</span></td>
            <td><span class="etiqueta" :class="ESTADO[v.estado]?.[0]">{{ tx(ESTADO[v.estado]?.[1] || v.estado) }}</span></td>
            <td>{{ v.vigente_desde ? fechaTexto(v.vigente_desde) : '—' }}</td>
            <td>{{ v.vigente_hasta ? fechaTexto(v.vigente_hasta) : '—' }}</td>
            <td class="codigo">{{ tx(v.fuente || '—') }}</td>
            <td class="envolver ayuda">{{ tx(v.nota) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <h3 class="titulo-seccion">{{ t('Official sources') }}</h3>
    <div class="tabla-marco">
      <table class="tabla" v-tarjetas>
        <thead><tr><th>{{ t('Source') }}</th><th>{{ t('Scope') }}</th><th>{{ t('Authority · dataset') }}</th><th>{{ t('Access') }}</th><th>{{ t('Version / status') }}</th><th>{{ t('Verification') }}</th></tr></thead>
        <tbody>
          <tr v-for="f in fuentes" :key="f.id">
            <td class="codigo fuerte">{{ tx(f.codigo) }}</td>
            <td><span class="etiqueta">{{ tx(f.ambito) }}</span></td>
            <td class="envolver">{{ tx(f.autoridad) }}<span class="sub">{{ tx(f.dataset) }}</span>
              <a v-if="f.url" :href="f.url" target="_blank" rel="noopener" class="enlace sub">{{ tx(f.url.replace(/^https?:\/\//, '').slice(0, 60)) }}</a></td>
            <td>{{ tx(f.acceso || '—') }}<span v-if="f.autenticacion && f.autenticacion !== 'No'" class="sub">{{ t('Authentication: {0}', [f.autenticacion]) }}</span></td>
            <td class="envolver ayuda">{{ tx(f.nota_version) }}</td>
            <td class="ayuda">
              <span v-if="f.verificado_en" class="etiqueta ok">{{ t('Verified {0}', [fechaTexto(f.verificado_en)]) }}</span>
              <span v-else class="etiqueta aviso">{{ t('Not verified') }}</span>
              <span v-if="f.verificado_por" class="sub">{{ tx(f.verificado_por) }}</span>
              <span v-if="f.documento" class="sub">{{ tx(f.documento) }}</span>
              <span v-for="p in f.problemas" :key="p" class="sub texto-error">{{ tx(p) }}</span>
              <button v-if="edita" type="button" class="btn-texto" @click="modal = { id: f.id, codigo: f.codigo, documento: f.documento || '', url: f.url || '', verificado_en: '' }">{{ t('Record verification') }}</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <Modal v-if="modal" :titulo="t('Verify {0}', [modal.codigo])" @cerrar="modal = null">
      <p class="ayuda">{{ t('Record that the source was checked against its official publication. Without a verification the source does not back any official data.') }}</p>
      <div class="rejilla-campos">
        <label class="campo col-completa"><span>{{ t('Official document or dataset checked') }}</span><input v-model="modal.documento" class="entrada" maxlength="300" /></label>
        <label class="campo col-completa"><span>{{ t('Official link') }}</span><input v-model="modal.url" class="entrada" maxlength="400" type="url" /></label>
        <label class="campo"><span>{{ t('Verified on') }}</span><input v-model="modal.verificado_en" class="entrada" type="date" /></label>
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
</style>
