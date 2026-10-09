<script setup>
import { t, tx } from '@/i18n/index.js'
import { computed } from 'vue'
import FiltroMulti from '@/componentes/FiltroMulti.vue'
import Icono from '@/componentes/Icono.vue'
import SelectBusqueda from '@/componentes/SelectBusqueda.vue'

// Condiciones en grupos: dentro de un grupo se cumplen TODAS (Y); entre
// grupos basta UNO (O). Se usa en las reglas y en las dependencias de los
// ámbitos de atributos. El campo es un atributo del catálogo o un dato del
// sistema (dominio, categoría); el valor se elige de sus opciones.
const props = defineProps({
  modelValue: { type: Array, default: () => [] }, // [{grupo, campo, operador, valor, valor_hasta, negado}]
  atributos: { type: Array, default: () => [] }, // catálogo: [{codigo, etiqueta, tipo_dato, opciones_min}]
  sistema: { type: Array, default: () => [] }, // [{valor, texto, opciones: [{valor, texto}]}]
})
const emit = defineEmits(['update:modelValue'])

const OPERADORES = [['EQUAL', '='], ['NOT_EQUAL', '≠'], ['IN', t('one of')], ['GT', '>'], ['GTE', '≥'], ['LT', '<'], ['LTE', '≤'],
  ['BETWEEN', t('between')], ['EXISTS', t('has a value')]]
const campos = computed(() => [...props.sistema.map((s) => ({ valor: s.valor, texto: s.texto, sub: t('System') })),
  ...props.atributos.map((a) => ({ valor: a.codigo, texto: a.etiqueta, sub: a.codigo }))])
const def = (campo) => props.atributos.find((a) => a.codigo === campo)
function opciones(campo) {
  const s = props.sistema.find((x) => x.valor === campo)
  if (s) return s.opciones || []
  const a = def(campo)
  if (a?.tipo_dato === 'boolean') return [{ valor: true, texto: t('Yes') }, { valor: false, texto: t('No') }]
  return (a?.opciones_min || []).map((o) => ({ valor: o.codigo, texto: o.etiqueta }))
}
const grupos = computed(() => {
  const g = {}
  props.modelValue.forEach((c, i) => (g[c.grupo || 1] ||= []).push({ ...c, i }))
  return Object.entries(g).sort((a, b) => a[0] - b[0])
})
function cambiar(i, k, v) {
  const lista = props.modelValue.map((c) => ({ ...c }))
  lista[i][k] = v
  if (k === 'operador') lista[i].valor = v === 'IN' ? [] : null
  if (k === 'campo') lista[i].valor = null
  emit('update:modelValue', lista)
}
function agregar(grupo) {
  emit('update:modelValue', [...props.modelValue, { grupo, campo: '', operador: 'EQUAL', valor: null, negado: false }])
}
function quitar(i) {
  emit('update:modelValue', props.modelValue.filter((_, j) => j !== i))
}
const nuevoGrupo = () => agregar(Math.max(0, ...props.modelValue.map((c) => c.grupo || 1)) + 1)
const numerico = (c) => ['GT', 'GTE', 'LT', 'LTE', 'BETWEEN'].includes(c.operador)
</script>

<template>
  <div class="cond-editor">
    <p v-if="!modelValue.length" class="ayuda">{{ t('No conditions: it always applies.') }}</p>
    <template v-for="([g, conds], gi) in grupos" :key="g">
      <p v-if="gi" class="o">{{ t('OR') }}</p>
      <div class="grupo">
        <span class="grupo-tit">{{ t('All of these') }}</span>
        <div v-for="(c, ci) in conds" :key="c.i" class="fila">
          <span class="y">{{ ci ? t('AND') : t('IF') }}</span>
          <SelectBusqueda :model-value="c.campo" :opciones="campos" :placeholder="t('Field…')" :etiqueta="t('Field')" class="campo" @update:model-value="cambiar(c.i, 'campo', $event)" />
          <select :value="c.operador" class="entrada op" :aria-label="t('Operator')" @change="cambiar(c.i, 'operador', $event.target.value)">
            <option v-for="[v, l] in OPERADORES" :key="v" :value="v">{{ tx(l) }}</option>
          </select>
          <template v-if="c.operador !== 'EXISTS'">
            <FiltroMulti v-if="c.operador === 'IN' && opciones(c.campo).length" :model-value="c.valor || []" :etiqueta="t('Values')" vacio="—"
                         :opciones="[...opciones(c.campo), { valor: '', texto: t('(no value)') }]" @update:model-value="cambiar(c.i, 'valor', $event)" />
            <input v-else-if="c.operador === 'IN'" class="entrada val" :value="(c.valor || []).join(', ')" :placeholder="t('values separated by commas')"
                   @change="cambiar(c.i, 'valor', $event.target.value.split(',').map((x) => x.trim()).filter(Boolean))" />
            <select v-else-if="!numerico(c) && opciones(c.campo).length" class="entrada val" :value="String(c.valor ?? '')" :aria-label="t('Value')"
                    @change="cambiar(c.i, 'valor', opciones(c.campo).find((o) => String(o.valor) === $event.target.value)?.valor ?? $event.target.value)">
              <option value="">{{ t('Choose…') }}</option>
              <option v-for="o in opciones(c.campo)" :key="String(o.valor)" :value="String(o.valor)">{{ tx(o.texto) }}</option>
            </select>
            <input v-else class="entrada val" :type="numerico(c) ? 'number' : 'text'" step="any" :value="c.valor ?? ''" :aria-label="t('Value')"
                   @change="cambiar(c.i, 'valor', numerico(c) && $event.target.value !== '' ? Number($event.target.value) : $event.target.value)" />
            <input v-if="c.operador === 'BETWEEN'" class="entrada val" type="number" step="any" :value="c.valor_hasta ?? ''" :aria-label="t('Up to')"
                   @change="cambiar(c.i, 'valor_hasta', $event.target.value === '' ? null : Number($event.target.value))" />
          </template>
          <label class="neg"><input type="checkbox" :checked="c.negado" @change="cambiar(c.i, 'negado', $event.target.checked)" />{{ t('not') }}</label>
          <button type="button" class="btn-icono" :aria-label="t('Remove')" @click="quitar(c.i)"><Icono nombre="basura" :tam="14" /></button>
        </div>
        <button type="button" class="btn-texto" @click="agregar(Number(g))">{{ t('+ AND condition') }}</button>
      </div>
    </template>
    <div class="acciones">
      <button v-if="!modelValue.length" type="button" class="btn btn-chico" @click="agregar(1)"><Icono nombre="mas" :tam="14" />{{ t('Add condition') }}</button>
      <button v-else type="button" class="btn btn-chico" @click="nuevoGrupo"><Icono nombre="mas" :tam="14" />{{ t('OR group') }}</button>
    </div>
  </div>
</template>

<style scoped>
.cond-editor { display: grid; gap: 6px; }
.grupo { border: 1px solid var(--linea); border-radius: var(--radio); padding: 8px 10px; display: grid; gap: 6px; }
.grupo-tit { font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.04em; color: var(--tinta-3); font-weight: 650; }
.fila { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.y { width: 32px; font-size: 0.74rem; font-weight: 700; color: var(--acento-texto); }
.campo { min-width: 200px; flex: 1; }
.op { width: auto; }
.val { width: 150px; }
.neg { display: inline-flex; gap: 4px; align-items: center; font-size: 0.8rem; color: var(--tinta-3); }
.o { margin: 0; text-align: center; font-weight: 700; font-size: 0.78rem; color: var(--tinta-3); }
.acciones { display: flex; gap: 6px; }
</style>
