<script setup>
import { t, tx } from '@/i18n/index.js'
import { computed, onMounted, ref } from 'vue'
import { api } from '@/nucleo/api'
import Icono from '@/componentes/Icono.vue'
import { fmtFechaHora } from '@/nucleo/utils'
import { errorApi } from '@/stores/ui'

// Auditor de integridad: que el dato oficial tenga fuente, versión y vigencia,
// que el historial de la empresa no se haya colado como dato oficial y que una
// guía o una regla propia no se presente como ley. Solo reporta: no corrige.
const datos = ref(null)
const cargando = ref(false)
const abierto = ref(null)
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
</script>

<template>
  <section>
    <p class="ayuda">{{ t('Checks that official tariff data has its source, version and validity, that company history has not been loaded as official data and that internal guidance or company rules are not presented as law. It only reports; nothing is changed.') }}</p>
    <div v-if="datos" class="kpis-integridad">
      <div class="kpi-i" :class="NIVEL[datos.estado][0]"><span>{{ t('Overall') }}</span><b>{{ NIVEL[datos.estado][1] }}</b></div>
      <div v-for="(n, k) in datos.hallazgos" :key="k" class="kpi-i" :class="n ? NIVEL[k][0] : ''"><span>{{ NIVEL[k][1] }}</span><b>{{ n }}</b></div>
    </div>
    <div class="filtros" v-filtros>
      <label class="check"><input v-model="soloProblemas" type="checkbox" /><span>{{ t('Only checks with findings') }}</span></label>
      <div class="separar fila-flex">
        <small v-if="datos" class="apagado">{{ t('Checked {0}', [fmtFechaHora(datos.generado_en)]) }}</small>
        <button class="btn" :disabled="cargando" @click="cargar"><Icono nombre="historial" />{{ t('Run again') }}</button>
      </div>
    </div>
    <div class="tabla-marco">
      <table class="tabla" v-tarjetas>
        <thead><tr><th>{{ t('Check') }}</th><th>{{ t('Layer') }}</th><th>{{ t('Result') }}</th><th class="num">{{ t('Findings') }}</th></tr></thead>
        <tbody>
          <template v-for="c in checks" :key="c.codigo">
            <tr :class="{ clicable: c.total }" @click="c.total && (abierto = abierto === c.codigo ? null : c.codigo)">
              <td>{{ tx(c.titulo) }}<span class="sub codigo">{{ c.codigo }}</span></td>
              <td>{{ CAPA[c.capa] || c.capa }}</td>
              <td><span class="etiqueta" :class="NIVEL[c.estado][0]">{{ NIVEL[c.estado][1] }}</span></td>
              <td class="num">{{ c.total }}</td>
            </tr>
            <tr v-if="abierto === c.codigo" class="detalle">
              <td colspan="4">
                <ul class="hallazgos">
                  <li v-for="(h, i) in c.hallazgos" :key="i"><b class="codigo">{{ tx(h.ref) }}</b> · {{ tx(h.mensaje) }}</li>
                  <li v-if="c.total > c.hallazgos.length" class="apagado">{{ t('…and {0} more', [c.total - c.hallazgos.length]) }}</li>
                </ul>
              </td>
            </tr>
          </template>
          <tr v-if="datos && !checks.length"><td colspan="4" class="vacio">{{ t('All checks passed: the official layer contains only official data.') }}</td></tr>
        </tbody>
      </table>
    </div>
  </section>
</template>

<style scoped>
.kpis-integridad { display: flex; flex-wrap: wrap; gap: 10px; margin: 12px 0; }
.kpi-i { display: flex; flex-direction: column; gap: 2px; padding: 10px 14px; border: 1px solid var(--linea); border-radius: 10px; min-width: 120px; background: var(--superficie); }
.kpi-i span { font-size: 0.78rem; color: var(--tinta-3); }
.kpi-i b { font-size: 1.15rem; }
.kpi-i.ok b { color: var(--ok); }
.kpi-i.aviso b { color: var(--aviso, #b45309); }
.kpi-i.error b { color: var(--error); }
.clicable { cursor: pointer; }
.hallazgos { margin: 0; padding-inline-start: 18px; display: grid; gap: 4px; font-size: 0.86rem; }
.detalle td { background: var(--superficie-2); }
</style>
