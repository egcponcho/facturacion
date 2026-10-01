<script setup>
import { t, tx } from '../../i18n/index.js'
import { computed, onMounted, ref } from 'vue'
import { api } from '../../api'
import { filtrar } from '../../busqueda.js'
import Icono from '../Icono.vue'
import { fechaTexto } from '../../stores/preferencias'
import { errorApi } from '../../stores/ui'

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
            <td class="ayuda">{{ tx(f.verificacion) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>

<style scoped>
.titulo-seccion { font-size: 1rem; margin: 14px 0 8px; }
.sub.enlace { display: block; }
</style>
