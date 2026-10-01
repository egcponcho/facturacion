<script setup>
import { t, tx } from '../../i18n/index.js'
import { computed } from 'vue'
import Icono from '../Icono.vue'

// Con qué países destino hay acuerdo comercial según el país de origen del
// producto, y qué prueba de origen (CO) se presenta para la preferencia.
const props = defineProps({
  origen: { type: String, default: '' },
  ctx: { type: Object, required: true },
  paises: { type: Array, default: () => [] },
})
const nombres = computed(() => Object.fromEntries(props.paises.map((x) => [x.codigo, x.nombre])))
const filas = computed(() => (props.ctx.destinos || []).map((d) => ({
  iso: d.iso,
  nombre: nombres.value[d.iso] || d.nombre,
  local: props.origen === d.iso,
  acuerdos: props.origen ? (props.ctx.acuerdos || []).filter((a) => a.origenes.includes(props.origen) && a.destinos.includes(d.iso)) : [],
})))
const conAcuerdo = computed(() => filas.value.filter((d) => d.local || d.acuerdos.length).length)
</script>

<template>
  <section class="panel acuerdos-panel">
    <div class="panel-cabeza">
      <div>
        <h2>{{ t('Trade agreements by destination') }}</h2>
        <p v-if="origen">{{ t('Made in') }} <b>{{ tx(nombres[origen] || origen) }}</b>{{ t(': {0} of {1} destinations enter with a preference if the proof of origin is presented.', [conAcuerdo, filas.length]) }}</p>
        <p v-else>{{ t('Choose the country of origin in the technical sheet to see where the product enters with a preference.') }}</p>
      </div>
    </div>
    <div v-if="origen" class="tabla-marco">
      <table class="tabla">
        <thead><tr><th style="width: 180px">{{ t('Destination') }}</th><th style="width: 140px">{{ t('Result') }}</th><th>{{ t('Agreement') }}</th><th>{{ t('Proof of origin to present') }}</th></tr></thead>
        <tbody>
          <tr v-for="d in filas" :key="d.iso">
            <td><span class="codigo apagado">{{ tx(d.iso) }}</span> <span class="fuerte">{{ tx(d.nombre) }}</span></td>
            <td>
              <span v-if="d.local" class="etiqueta" style="margin-inline-start: 0">{{ t('Domestic product') }}</span>
              <span v-else-if="d.acuerdos.length" class="etiqueta ok" style="margin-inline-start: 0"><Icono nombre="check" :tam="12" />{{ t('Preference') }}</span>
              <span v-else class="etiqueta aviso" style="margin-inline-start: 0">{{ t('Full DAI') }}</span>
            </td>
            <td>
              <template v-if="d.acuerdos.length">
                <div v-for="a in d.acuerdos" :key="a.codigo" class="acuerdo"><b>{{ tx(a.codigo) }}</b> {{ tx(a.nombre) }}<span v-if="a.nota" class="sub">{{ tx(a.nota) }}</span></div>
              </template>
              <span v-else class="apagado">{{ tx(d.local ? t('Made in the destination country') : t('No agreement with this origin')) }}</span>
            </td>
            <td>
              <div v-for="a in d.acuerdos" :key="a.codigo">{{ tx(a.prueba || t('Certificate of origin')) }}</div>
              <span v-if="!d.acuerdos.length" class="apagado">—</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <p class="ayuda mt-chico">{{ t('Reference base kept in') }} <i>{{ t('Master data → Trade agreements') }}</i>. {{ t('Check the rules of origin of each agreement before claiming the preference.') }}</p>
  </section>
</template>

<style scoped>
.acuerdos-panel { margin-top: 12px; }
.acuerdo + .acuerdo { margin-top: 4px; }
.acuerdo .sub { display: block; }
</style>
