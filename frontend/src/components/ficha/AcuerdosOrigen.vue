<script setup>
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
        <h2>Trade agreements by destination</h2>
        <p v-if="origen">Made in <b>{{ nombres[origen] || origen }}</b>: {{ conAcuerdo }} of {{ filas.length }} destinations enter with a preference if the proof of origin is presented.</p>
        <p v-else>Choose the country of origin in the technical sheet to see where the product enters with a preference.</p>
      </div>
    </div>
    <div v-if="origen" class="tabla-marco">
      <table class="tabla">
        <thead><tr><th style="width: 180px">Destination</th><th style="width: 140px">Result</th><th>Agreement</th><th>Proof of origin to present</th></tr></thead>
        <tbody>
          <tr v-for="d in filas" :key="d.iso">
            <td><span class="codigo apagado">{{ d.iso }}</span> <span class="fuerte">{{ d.nombre }}</span></td>
            <td>
              <span v-if="d.local" class="etiqueta" style="margin-left: 0">Domestic product</span>
              <span v-else-if="d.acuerdos.length" class="etiqueta ok" style="margin-left: 0"><Icono nombre="check" :tam="12" />Preference</span>
              <span v-else class="etiqueta aviso" style="margin-left: 0">Full DAI</span>
            </td>
            <td>
              <template v-if="d.acuerdos.length">
                <div v-for="a in d.acuerdos" :key="a.codigo" class="acuerdo"><b>{{ a.codigo }}</b> {{ a.nombre }}<span v-if="a.nota" class="sub">{{ a.nota }}</span></div>
              </template>
              <span v-else class="apagado">{{ d.local ? 'Made in the destination country' : 'No agreement with this origin' }}</span>
            </td>
            <td>
              <div v-for="a in d.acuerdos" :key="a.codigo">{{ a.prueba || 'Certificate of origin' }}</div>
              <span v-if="!d.acuerdos.length" class="apagado">—</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <p class="ayuda mt-chico">Reference base kept in <i>Master data → Trade agreements</i>. Check the rules of origin of each agreement before claiming the preference.</p>
  </section>
</template>

<style scoped>
.acuerdos-panel { margin-top: 12px; }
.acuerdo + .acuerdo { margin-top: 4px; }
.acuerdo .sub { display: block; }
</style>
