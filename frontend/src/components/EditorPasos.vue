<script setup>
import { t, tx } from '../i18n/index.js'
import { computed } from 'vue'
import Icono from './Icono.vue'
import Seleccion from './Seleccion.vue'

// Cadena de pasos de un plan de lead time. Cada paso cae en un tramo entre
// hitos medidos, cuenta días naturales o hábiles, arranca tras el paso
// anterior (o tras otro del tramo, o en paralelo) y puede aplicar a un solo
// modo de transporte. Se reordena con las flechas; el servidor valida igual.
const props = defineProps({ modelValue: { type: Array, default: () => [] } })
const emit = defineEmits(['update:modelValue'])

const TRAMOS = [
  ['liberacion', t('Logistics release to XF')],
  ['transito', t('XF to port arrival')],
  ['puerto', t('Port to warehouse')],
  ['ingreso', t('Warehouse entry')],
  ['tienda', t('Entry to store')],
]
const MODOS = [['', t('All modes')], ['MARITIMO', t('Ocean')], ['AEREO', t('Air')], ['TERRESTRE', t('Road')]]

const pasos = computed(() => props.modelValue || [])
const clave = (p, i) => p.codigo || `P${i + 1}`

function cambiar(lista) {
  emit('update:modelValue', lista)
}
function poner(i, campo, valor) {
  const lista = pasos.value.map((p) => ({ ...p }))
  lista[i][campo] = valor
  // El código de un paso nuevo sale de su nombre (igual que en el servidor); quien dependía de él lo sigue
  if (campo === 'nombre' && (!lista[i].codigo || lista[i]._auto)) {
    const antes = lista[i].codigo
    const cod = valor.normalize('NFKD').replace(/[^A-Za-z0-9]/g, '').toUpperCase().slice(0, 12)
    Object.assign(lista[i], { codigo: cod, _auto: true })
    for (const q of lista) if (antes && q.depende === antes) q.depende = cod
  }
  // Si cambia de tramo, la dependencia de otro tramo deja de valer
  if (campo === 'tramo' && lista[i].depende !== 'INICIO') lista[i].depende = ''
  cambiar(lista)
}
function agregar() {
  const ultimo = pasos.value[pasos.value.length - 1]
  cambiar([...pasos.value, { codigo: '', nombre: '', tramo: ultimo?.tramo || 'liberacion', dias: 1, habiles: false, depende: '', modo: '' }])
}
function quitar(i) {
  const cod = clave(pasos.value[i], i)
  cambiar(pasos.value.filter((_, j) => j !== i).map((p) => (p.depende === cod ? { ...p, depende: '' } : p)))
}
function mover(i, d) {
  const lista = [...pasos.value]
  const j = i + d
  if (j < 0 || j >= lista.length) return
  ;[lista[i], lista[j]] = [lista[j], lista[i]]
  // Una dependencia solo puede apuntar a un paso anterior del mismo tramo
  const ok = lista.map((p, k) => (p.depende && p.depende !== 'INICIO' && !lista.slice(0, k).some((q, m) => clave(q, m) === p.depende && q.tramo === p.tramo) ? { ...p, depende: '' } : p))
  cambiar(ok)
}
function anteriores(i) {
  const p = pasos.value[i]
  return pasos.value.slice(0, i).map((q, j) => [clave(q, j), q]).filter(([, q]) => q.tramo === p.tramo && q.codigo)
}

// Días naturales aproximados por tramo (los hábiles cuentan 7/5) para ver el total mientras se edita
const resumen = computed(() => TRAMOS.map(([k, nombre]) => {
  const ps = pasos.value.map((p, i) => [p, i]).filter(([p]) => p.tramo === k)
  const fin = {}
  let previo = null
  for (const [p, i] of ps) {
    const c = clave(p, i)
    const dep = p.depende === 'INICIO' ? null : p.depende || previo
    const dias = Number(p.dias) || 0
    fin[c] = (dep && fin[dep] !== undefined ? fin[dep] : 0) + (p.habiles ? Math.ceil((dias * 7) / 5) : dias)
    previo = c
  }
  return { clave: k, nombre, dias: Math.max(0, ...Object.values(fin)), pasos: ps.length }
}))
const total = computed(() => resumen.value.reduce((s, r) => s + r.dias, 0))
</script>

<template>
  <div class="editor-pasos">
    <ol class="lista">
      <li v-for="(p, i) in pasos" :key="i" class="paso">
        <span class="num">{{ i + 1 }}</span>
        <div class="campos">
          <label class="campo nombre"><span class="req">{{ t('Step') }}</span>
            <input :value="p.nombre" required maxlength="80" :placeholder="t('e.g. Customs clearance')" @input="poner(i, 'nombre', $event.target.value)" /></label>
          <label class="campo"><span class="req">{{ t('Stage') }}</span>
            <Seleccion :model-value="p.tramo" required @update:model-value="poner(i, 'tramo', $event)">
              <option v-for="[v, txt] in TRAMOS" :key="v" :value="v">{{ tx(txt) }}</option>
            </Seleccion></label>
          <label class="campo dias"><span class="req">{{ t('Days') }}</span>
            <input :value="p.dias" type="number" min="0" max="365" required @input="poner(i, 'dias', $event.target.value === '' ? '' : Number($event.target.value))" /></label>
          <label class="check habiles"><input type="checkbox" :checked="p.habiles" @change="poner(i, 'habiles', $event.target.checked)" />{{ t('Business days') }}</label>
          <label class="campo inicio"><span>{{ t('Starts') }}</span>
            <Seleccion :model-value="p.depende || ''" @update:model-value="poner(i, 'depende', $event)">
              <option value="">{{ t('After the previous step') }}</option>
              <option value="INICIO">{{ t('At the start of the stage (in parallel)') }}</option>
              <option v-for="[c, q] in anteriores(i)" :key="c" :value="c">{{ t('After {0}', [q.nombre]) }}</option>
            </Seleccion></label>
          <label class="campo modo"><span>{{ t('Applies to') }}</span>
            <Seleccion :model-value="p.modo || ''" @update:model-value="poner(i, 'modo', $event)">
              <option v-for="[v, txt] in MODOS" :key="v" :value="v">{{ tx(txt) }}</option>
            </Seleccion></label>
        </div>
        <div class="acciones">
          <button type="button" class="btn btn-chico btn-fantasma" :disabled="i === 0" :aria-label="t('Move up')" :title="t('Move up')" @click="mover(i, -1)"><Icono nombre="arriba" :tam="14" /></button>
          <button type="button" class="btn btn-chico btn-fantasma" :disabled="i === pasos.length - 1" :aria-label="t('Move down')" :title="t('Move down')" @click="mover(i, 1)"><Icono nombre="abajo" :tam="14" /></button>
          <button type="button" class="btn btn-chico btn-fantasma" :aria-label="t('Remove step')" :title="t('Remove step')" @click="quitar(i)"><Icono nombre="basura" :tam="14" /></button>
        </div>
      </li>
    </ol>
    <p v-if="!pasos.length" class="ayuda">{{ t('No steps yet. Add the first one.') }}</p>
    <button type="button" class="btn btn-chico" @click="agregar"><Icono nombre="mas" :tam="14" />{{ t('Add step') }}</button>
    <div class="resumen" :aria-label="t('Days per stage')">
      <span v-for="r in resumen" :key="r.clave" class="chip" :class="{ vacio: !r.pasos }">{{ tx(r.nombre) }} <b>{{ t('{0} d', [r.dias]) }}</b></span>
      <span class="chip total">{{ t('Total ≈ {0} d', [total]) }}</span>
    </div>
  </div>
</template>

<style scoped>
.editor-pasos { display: flex; flex-direction: column; gap: 10px; align-items: flex-start; }
.lista { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 8px; width: 100%; }
.paso { display: grid; grid-template-columns: auto 1fr auto; gap: 10px; align-items: start; padding: 10px; border: 1px solid var(--linea); border-radius: var(--radio); background: var(--superficie-2); }
.num { width: 24px; height: 24px; border-radius: 50%; display: grid; place-items: center; background: var(--acento-claro); color: var(--acento-texto); font-weight: 700; font-size: 0.78rem; margin-top: 22px; }
.campos { display: grid; grid-template-columns: minmax(0, 1.5fr) minmax(0, 0.6fr) auto; gap: 8px 10px; min-width: 0; }
.campos .nombre { grid-column: 1 / -1; }
.campos .inicio { grid-column: 1 / 2; }
.campos .modo { grid-column: 2 / -1; }
.campos .dias input { width: 100%; }
.habiles { align-self: end; padding-bottom: 8px; }
.acciones { display: flex; flex-direction: column; gap: 2px; margin-top: 18px; }
.resumen { display: flex; flex-wrap: wrap; gap: 6px; }
.chip { font-size: 0.78rem; padding: 3px 9px; border-radius: 99px; background: var(--superficie-2); border: 1px solid var(--linea); color: var(--tinta-2); }
.chip.vacio { opacity: 0.55; }
.chip.total { background: var(--acento-claro); color: var(--acento-texto); border-color: transparent; font-weight: 650; }
@media (max-width: 560px) {
  .paso { grid-template-columns: 1fr; }
  .campos { grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); }
  .campos .inicio, .campos .modo { grid-column: 1 / -1; }
  .num { margin-top: 0; }
  .acciones { flex-direction: row; margin-top: 0; justify-content: flex-end; }
}
</style>
