<script setup>
import { t, tx } from '@/i18n/index.js'
import { computed } from 'vue'
import Icono from '@/componentes/Icono.vue'
import TablaDatos from '@/componentes/TablaDatos.vue'

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

// Tabla común en modo local: cada columna filtra por sus valores (el resultado
// con su nombre; acuerdos y pruebas, uno por valor)
const RESULTADOS = [['local', t('Domestic product')], ['preferencia', t('Preference')], ['dai', t('Full DAI')]]
const resultado = (d) => (d.local ? 'local' : d.acuerdos.length ? 'preferencia' : 'dai')
const nombreAcuerdo = (codigo) => {
  const a = (props.ctx.acuerdos || []).find((x) => x.codigo === codigo)
  return a ? `${a.codigo} · ${tx(a.nombre)}` : codigo
}
const columnas = [
  { clave: 'destino', texto: t('Destination'), fija: true, prioridad: 1, ancho: 200, valor: (d) => d.nombre },
  { clave: 'resultado', texto: t('Result'), prioridad: 1, ancho: 150, valor: resultado, opciones: RESULTADOS },
  { clave: 'acuerdo', texto: t('Agreement'), prioridad: 2, valor: (d) => d.acuerdos.map((a) => a.codigo), textoValor: nombreAcuerdo },
  { clave: 'prueba', texto: t('Proof of origin to present'), prioridad: 3, valor: (d) => d.acuerdos.map((a) => a.prueba || t('Certificate of origin')) },
]
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
    <TablaDatos v-if="origen" tabla="productos_acuerdos" :columnas="columnas" :filas="filas" clave-fila="iso" :etiqueta="t('Trade agreements by destination')">
      <template #celda-destino="{ fila: d }"><span class="codigo apagado">{{ tx(d.iso) }}</span> <span class="fuerte">{{ tx(d.nombre) }}</span></template>
      <template #celda-resultado="{ fila: d }">
        <span v-if="d.local" class="etiqueta ms-0">{{ t('Domestic product') }}</span>
        <span v-else-if="d.acuerdos.length" class="etiqueta ok ms-0"><Icono nombre="check" :tam="12" />{{ t('Preference') }}</span>
        <span v-else class="etiqueta aviso ms-0">{{ t('Full DAI') }}</span>
      </template>
      <template #celda-acuerdo="{ fila: d }">
        <template v-if="d.acuerdos.length">
          <div v-for="a in d.acuerdos" :key="a.codigo" class="acuerdo"><b>{{ tx(a.codigo) }}</b> {{ tx(a.nombre) }}<span v-if="a.nota" class="sub">{{ tx(a.nota) }}</span></div>
        </template>
        <span v-else class="apagado">{{ tx(d.local ? t('Made in the destination country') : t('No agreement with this origin')) }}</span>
      </template>
      <template #celda-prueba="{ fila: d }">
        <div v-for="a in d.acuerdos" :key="a.codigo">{{ tx(a.prueba || t('Certificate of origin')) }}</div>
        <span v-if="!d.acuerdos.length" class="apagado">—</span>
      </template>
    </TablaDatos>
    <p class="ayuda mt-chico">{{ t('Reference base kept in') }} <i>{{ t('Master data → Trade agreements') }}</i>. {{ t('Check the rules of origin of each agreement before claiming the preference.') }}</p>
  </section>
</template>

<style scoped>
.acuerdos-panel { margin-top: 12px; }
.acuerdo + .acuerdo { margin-top: 4px; }
.acuerdo .sub { display: block; }
</style>
