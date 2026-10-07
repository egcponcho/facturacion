<script setup>
import { t, tx } from '../../../i18n/index.js'
import { computed } from 'vue'
import Icono from '../../Icono.vue'
import SelectBusqueda from '../../SelectBusqueda.vue'

// El valor que fijan los datos solos: uno fijo, el de otra pregunta (con un
// mapa) o lo que se lee de una parte de la composición (fibra, material o
// clase de material, con un mapa a las opciones de esta pregunta).
const props = defineProps({
  modelValue: { type: Object, default: null },
  atributos: { type: Array, default: () => [] },
  atributo: { type: Object, required: true }, // la pregunta que se deriva: {codigo, tipo_dato, opciones}
  deshabilitado: Boolean,
})
const emit = defineEmits(['update:modelValue'])
const MODOS = [['', t('Not derived: the person answers it')], ['constante', t('Always the same value')], ['valor', t('From another question')],
  ['material', t('From the material of a composition part')], ['fibra', t('From the main fiber of a composition part')],
  ['clase', t('From the material class of a composition part')]]
const d = computed(() => props.modelValue || {})
const partes = computed(() => props.atributos.filter((a) => a.codigo.startsWith('comp.')).map((a) => ({ valor: a.codigo.slice(5), texto: a.etiqueta })))
const otras = computed(() => props.atributos.filter((a) => a.codigo !== props.atributo.codigo && !a.codigo.startsWith('comp.'))
  .map((a) => ({ valor: a.codigo, texto: a.etiqueta, sub: a.codigo })))
const valores = computed(() => (props.atributo.tipo_dato === 'boolean' ? [{ valor: true, texto: t('Yes') }, { valor: false, texto: t('No') }]
  : (props.atributo.opciones || props.atributo.opciones_min || []).map((o) => ({ valor: o.codigo, texto: o.etiqueta }))))
const mapa = computed(() => Object.entries(d.value.mapa || {}))
function poner(k, v) {
  const n = { ...d.value }
  if (v === '' || v == null) delete n[k]
  else n[k] = v
  emit('update:modelValue', n.modo ? n : null)
}
function modo(m) {
  emit('update:modelValue', m ? { modo: m, ...(m === 'valor' || m === 'constante' ? {} : { parte: d.value.parte }), ...(m !== 'constante' && d.value.mapa ? { mapa: d.value.mapa } : {}) } : null)
}
function cambiarMapa(i, k, v) {
  const pares = mapa.value.map((p, j) => (j === i ? (k === 'de' ? [v, p[1]] : [p[0], v]) : p))
  poner('mapa', pares.length ? Object.fromEntries(pares) : null)
}
const agregarMapa = () => poner('mapa', { ...(d.value.mapa || {}), '': valores.value[0]?.valor ?? '' })
const quitarMapa = (i) => {
  const pares = mapa.value.filter((_, j) => j !== i)
  poner('mapa', pares.length ? Object.fromEntries(pares) : null)
}
const valorDe = (txt) => valores.value.find((o) => String(o.valor) === txt)?.valor ?? txt
</script>

<template>
  <div class="cfilas">
    <div class="linea">
      <label class="ccampo ancho"><span>{{ t('How its value is set') }}</span>
        <select class="entrada" :value="d.modo || ''" :disabled="deshabilitado" @change="modo($event.target.value)">
          <option v-for="[v, l] in MODOS" :key="v" :value="v">{{ tx(l) }}</option>
        </select></label>
    </div>
    <div v-if="d.modo === 'constante'" class="linea">
      <label class="ccampo"><span>{{ t('Value') }}</span>
        <select v-if="valores.length" class="entrada" :value="String(d.valor ?? '')" :disabled="deshabilitado" @change="poner('valor', valorDe($event.target.value))">
          <option value="">{{ t('Choose…') }}</option>
          <option v-for="o in valores" :key="String(o.valor)" :value="String(o.valor)">{{ tx(o.texto) }}</option>
        </select>
        <input v-else class="entrada" :value="d.valor ?? ''" :disabled="deshabilitado" @change="poner('valor', $event.target.value)" /></label>
    </div>
    <div v-else-if="d.modo === 'valor'" class="linea">
      <label class="ccampo ancho"><span>{{ t('Question it is read from') }}</span>
        <SelectBusqueda :model-value="d.desde || ''" :opciones="otras" :etiqueta="t('Question')" :deshabilitado="deshabilitado" @update:model-value="poner('desde', $event)" /></label>
    </div>
    <div v-else-if="d.modo" class="linea">
      <label class="ccampo"><span>{{ t('Composition part') }}</span>
        <select class="entrada" :value="d.parte || ''" :disabled="deshabilitado" @change="poner('parte', $event.target.value)">
          <option value="">{{ t('Choose…') }}</option>
          <option v-for="p in partes" :key="p.valor" :value="p.valor">{{ tx(p.texto) }}</option>
        </select></label>
      <label class="ccampo"><span>{{ t('Read') }}</span>
        <select class="entrada" :value="d.lectura || ''" :disabled="deshabilitado" @change="poner('lectura', $event.target.value)">
          <option value="">{{ t('The outer surface') }}</option>
          <option value="contacto">{{ t('What touches the ground or the skin') }}</option>
        </select></label>
    </div>
    <template v-if="d.modo && d.modo !== 'constante'">
      <p class="ayuda">{{ t('Map: what is read → the answer it gives. Use * for anything else.') }}</p>
      <div v-for="([de, a], i) in mapa" :key="i" class="cfila linea">
        <input class="entrada" :value="de" :disabled="deshabilitado" :placeholder="t('e.g. leather, or *')" :aria-label="t('Read value')" @change="cambiarMapa(i, 'de', $event.target.value.trim())" />
        <Icono nombre="derecha" :tam="14" />
        <select v-if="valores.length" class="entrada" :value="String(a ?? '')" :disabled="deshabilitado" :aria-label="t('Answer')" @change="cambiarMapa(i, 'a', valorDe($event.target.value))">
          <option v-for="o in valores" :key="String(o.valor)" :value="String(o.valor)">{{ tx(o.texto) }}</option>
        </select>
        <input v-else class="entrada" :value="a ?? ''" :disabled="deshabilitado" :aria-label="t('Answer')" @change="cambiarMapa(i, 'a', $event.target.value)" />
        <button v-if="!deshabilitado" type="button" class="btn-icono" :aria-label="t('Remove')" @click="quitarMapa(i)"><Icono nombre="basura" :tam="15" /></button>
      </div>
      <button v-if="!deshabilitado" type="button" class="btn btn-chico" @click="agregarMapa"><Icono nombre="mas" :tam="14" />{{ t('Add to the map') }}</button>
    </template>
  </div>
</template>
