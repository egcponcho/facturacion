<script setup>
import { t, tx } from '@/i18n/index.js'
import { computed, ref } from 'vue'
import Seleccion from '@/componentes/Seleccion.vue'
import { ALCANCES, ALCANCES_DE, CANTIDADES, CANTIDADES_REGLA, CANTIDADES_REGLA_DE } from '@/modulos/etiquetado/etiquetas.js'

// Lo que decide una regla (la normal de un lugar o una excepción), como en
// clasificación pero sin base oficial: la empresa elige si la etiqueta va (con
// qué diseño, en el espacio del slot) o no va, dónde se pone (la OC, cada
// posición, el artículo genérico, cada variante, la lista de empaque, cada
// empaque…), cuántas salen y, entre excepciones del mismo tipo, cuál pesa más.
const props = defineProps({
  modelValue: { type: Object, required: true }, // { accion, alcance, cantidad, prioridad }
  tipo: { type: Object, required: true }, // el tipo de etiqueta (sujeto, cantidad, alcance_efectivo)
  prioridad: { type: Boolean, default: false }, // solo en las excepciones
  editable: { type: Boolean, default: true },
})
const x = props.modelValue
const alcances = computed(() => ALCANCES_DE[props.tipo.sujeto] || [])
const cantidades = computed(() => CANTIDADES_REGLA_DE[props.tipo.sujeto] || [])
const alcanceTipo = computed(() => ALCANCES()[props.tipo.alcance_efectivo] || '')
const cantidadTipo = computed(() => CANTIDADES()[props.tipo.cantidad] || '')
// «Más opciones» se abre solo si la regla ya cambia dónde va, cuántas o la prioridad
const abiertas = ref(!!(x.alcance || x.cantidad || x.prioridad))
const resumen = computed(() => [x.alcance && ALCANCES()[x.alcance], x.cantidad && CANTIDADES_REGLA()[x.cantidad],
  x.prioridad ? t('priority {0}', [x.prioridad]) : ''].filter(Boolean).join(' · '))
function poner(accion) {
  x.accion = accion
  if (accion === 'NO_LLEVA') {
    x.alcance = ''
    x.cantidad = ''
  }
}
</script>

<template>
  <div class="salida">
    <div class="salida-accion" role="radiogroup" :aria-label="t('Does this label go?')">
      <label class="check"><input type="radio" :checked="x.accion !== 'NO_LLEVA'" :disabled="!editable" @change="poner('USAR')" /> {{ t('It goes, with this design') }}</label>
      <label class="check"><input type="radio" :checked="x.accion === 'NO_LLEVA'" :disabled="!editable" @change="poner('NO_LLEVA')" /> {{ t('Does not carry this label') }}</label>
    </div>
    <template v-if="x.accion !== 'NO_LLEVA'">
      <slot />
      <button type="button" class="enlace salida-mas" :aria-expanded="abiertas" @click="abiertas = !abiertas">
        {{ abiertas ? t('Fewer options') : t('Where it goes and how many') }}<template v-if="!abiertas && resumen"> · {{ resumen }}</template>
      </button>
      <div v-if="abiertas" class="salida-opciones">
        <label v-if="alcances.length > 1"><span>{{ t('Where it goes') }}</span>
          <Seleccion v-model="x.alcance" :disabled="!editable">
            <option value="">{{ t('Like the label type ({0})', [alcanceTipo]) }}</option>
            <option v-for="a in alcances" :key="a" :value="a">{{ ALCANCES()[a] }}</option>
          </Seleccion></label>
        <label><span>{{ t('How many') }}</span>
          <Seleccion v-model="x.cantidad" :disabled="!editable">
            <option value="">{{ t('Like the label type ({0})', [cantidadTipo]) }}</option>
            <option v-for="c in cantidades" :key="c" :value="c">{{ CANTIDADES_REGLA()[c] }}</option>
          </Seleccion></label>
        <label v-if="prioridad"><span>{{ t('Priority') }}</span>
          <input v-model.number="x.prioridad" type="number" min="-1000" max="1000" step="1" :disabled="!editable" class="salida-prioridad" /></label>
        <p class="ayuda salida-ayuda">
          <template v-if="prioridad">{{ t('If two exceptions of the same kind apply, the one with the higher priority wins.') }} </template>
          {{ t('Where it goes groups the records: one label for the whole PO, per position, per generic item, per variant…') }}
        </p>
      </div>
    </template>
    <p v-else class="ayuda">{{ t('No label of type {0} comes out for what falls here (it is not an error).', [tx(tipo.nombre)]) }}</p>
  </div>
</template>

<style scoped>
.salida { display: flex; flex-direction: column; gap: 8px; }
.salida-accion { display: flex; gap: 16px; flex-wrap: wrap; }
.salida-mas { align-self: flex-start; font-size: 0.86rem; }
.salida-opciones { display: flex; flex-wrap: wrap; gap: 10px 14px; align-items: flex-end; border-inline-start: 3px solid var(--linea); padding-inline-start: 10px; }
.salida-opciones label { display: flex; flex-direction: column; gap: 3px; font-size: 0.86rem; min-width: 200px; }
.salida-opciones label > span { color: var(--tinta-2); }
.salida-prioridad { width: 100px; }
.salida-ayuda { flex-basis: 100%; margin: 0; }
</style>
