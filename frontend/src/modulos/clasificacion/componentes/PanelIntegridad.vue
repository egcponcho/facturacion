<script setup>
import { t, tx } from '@/i18n/index.js'
import { computed, onMounted, ref } from 'vue'
import { api } from '@/nucleo/api'
import Icono from '@/componentes/Icono.vue'
import TablaDatos from '@/componentes/TablaDatos.vue'
import { fmtFechaHora } from '@/nucleo/utils'
import { errorApi } from '@/stores/ui'

// Auditor de integridad: que el dato oficial tenga fuente, versión y vigencia,
// que el historial de la empresa no se haya colado como dato oficial y que una
// guía o una regla propia no se presente como ley. Solo reporta: no corrige.
const datos = ref(null)
const cargando = ref(false)
const soloProblemas = ref(true)

async function cargar() {
  cargando.value = true
  try {
    datos.value = await api.get('/aranceles/oficial/integridad')
  } catch (e) {
    errorApi(e)
  } finally {
    cargando.value = false
  }
}
onMounted(cargar)

const NIVEL = {
  OK: ['ok', t('OK')],
  WARNING: ['aviso', t('Warning')],
  ERROR: ['error', t('Error')],
  SOURCE_MISSING: ['aviso', t('Source missing')],
  VERSION_EXPIRED: ['aviso', t('Version expired')],
  CONTAMINATION: ['error', t('Internal data contamination')],
}
const CAPA = { OFFICIAL: t('Official data'), ENGINE: t('Classification engine'), COMPANY: t('Company knowledge') }
const checks = computed(() => (datos.value?.checks || []).filter((c) => !soloProblemas.value || c.total))
const columnas = computed(() => [
  { clave: 'titulo', texto: t('Check'), fija: true, prioridad: 1, filtro: false },
  { clave: 'capa', texto: t('Layer'), prioridad: 2, opciones: Object.entries(CAPA) },
  { clave: 'estado', texto: t('Result'), prioridad: 1, opciones: Object.entries(NIVEL).map(([k, [, txt]]) => [k, txt]) },
  { clave: 'total', texto: t('Findings'), num: true, prioridad: 1 },
])
</script>

<template>
  <section>
    <p class="ayuda">{{ t('Checks that official tariff data has its source, version and validity, that company history has not been loaded as official data and that internal guidance or company rules are not presented as law. It only reports; nothing is changed.') }}</p>
    <div v-if="datos" class="kpis-integridad">
      <div class="kpi-i" :class="NIVEL[datos.estado][0]"><span>{{ t('Overall') }}</span><b>{{ NIVEL[datos.estado][1] }}</b></div>
      <div v-for="(n, k) in datos.hallazgos" :key="k" class="kpi-i" :class="n ? NIVEL[k][0] : ''"><span>{{ NIVEL[k][1] }}</span><b>{{ n }}</b></div>
    </div>
    <TablaDatos tabla="aranceles_integridad" :columnas="columnas" :filas="checks" :cargando="cargando && !datos" clave-fila="codigo" expandible
                :externos="{ problemas: soloProblemas ? '1' : '' }" :etiqueta="t('Tariff data integrity')"
                @vista="(x) => (soloProblemas = x.problemas === '1')" @limpiar-externos="soloProblemas = false">
      <template #filtros>
        <label class="check"><input v-model="soloProblemas" type="checkbox" /><span>{{ t('Only checks with findings') }}</span></label>
        <div class="separar fila-flex">
          <small v-if="datos" class="apagado">{{ t('Checked {0}', [fmtFechaHora(datos.generado_en)]) }}</small>
          <button type="button" class="btn" :disabled="cargando" @click="cargar"><Icono nombre="historial" />{{ t('Run again') }}</button>
        </div>
      </template>
      <template #celda-titulo="{ fila: c }">{{ tx(c.titulo) }}<span class="sub codigo">{{ c.codigo }}</span></template>
      <template #celda-capa="{ fila: c }">{{ CAPA[c.capa] || c.capa }}</template>
      <template #celda-estado="{ fila: c }"><span class="etiqueta ms-0" :class="NIVEL[c.estado][0]">{{ NIVEL[c.estado][1] }}</span></template>
      <template #detalle="{ fila: c }">
        <ul v-if="c.total" class="hallazgos">
          <li v-for="(h, i) in c.hallazgos" :key="i"><b class="codigo">{{ tx(h.ref) }}</b> · {{ tx(h.mensaje) }}</li>
          <li v-if="c.total > c.hallazgos.length" class="apagado">{{ t('…and {0} more', [c.total - c.hallazgos.length]) }}</li>
        </ul>
        <p v-else class="ayuda">{{ t('No findings.') }}</p>
      </template>
      <template #vacio>{{ t('All checks passed: the official layer contains only official data.') }}</template>
    </TablaDatos>
  </section>
</template>

<style scoped>
.kpis-integridad { display: flex; flex-wrap: wrap; gap: 10px; margin: 12px 0; }
.kpi-i { display: flex; flex-direction: column; gap: 2px; padding: 10px 14px; border: 1px solid var(--linea); border-radius: 10px; min-width: 120px; background: var(--superficie); }
.kpi-i span { font-size: var(--t-xs); color: var(--tinta-3); }
.kpi-i b { font-size: var(--t-lg); }
.kpi-i.ok b { color: var(--ok); }
.kpi-i.aviso b { color: var(--aviso, #b45309); }
.kpi-i.error b { color: var(--error); }
.hallazgos { margin: 0; padding-inline-start: 18px; display: grid; gap: 4px; font-size: var(--td-sub); }

</style>
