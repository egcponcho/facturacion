<script setup>
import { t, tx } from '@/i18n/index.js'
import { computed, ref, watch } from 'vue'
import { api } from '@/nucleo/api'
import Icono from '@/componentes/Icono.vue'
import Seleccion from '@/componentes/Seleccion.vue'
import SelectBusqueda from '@/componentes/SelectBusqueda.vue'

// Regla de lead time de un nivel (Global, Región, País o Puerto). Muestra lo
// que hereda del nivel superior y permite cambiar solo lo necesario:
// sobrescribir un paso, quitarlo, agregar pasos del catálogo y reordenar.
// El servidor valida la cadena completa al guardar.
const props = defineProps({
  modelValue: { type: Object, default: () => ({ pasos: [], orden: null }) },
  form: { type: Object, required: true },
  reglaId: { type: [Number, String], default: null },
})
const emit = defineEmits(['update:modelValue'])

const MODOS = [['', t('All modes')], ['MARITIMO', t('Ocean')], ['AEREO', t('Air')], ['TERRESTRE', t('Road')]]
const catalogo = ref([])
const base = ref({ pasos: [], orden: [], niveles: [] }) // lo heredado
const cargando = ref(false)
const nuevo = ref('')

api.get('/leadtimes/ambitos').then((r) => (catalogo.value = r.pasos.filter((p) => p.activo))).catch(() => {})
const nombre = (c) => catalogo.value.find((p) => p.codigo === c)?.nombre || c

// Lo heredado: el lead time efectivo del ámbito sin esta regla
const ambito = computed(() => ({ REGION: { region: props.form.region }, PAIS: { pais: props.form.pais }, PUERTO: { puerto: props.form.puerto } }[props.form.nivel] || {}))
async function cargarBase() {
  if (!props.form.nivel || (props.form.nivel !== 'GLOBAL' && !Object.values(ambito.value)[0])) {
    base.value = { pasos: [], orden: [], niveles: [] }
    return
  }
  cargando.value = true
  try {
    base.value = await api.get('/leadtimes/efectivo', { ...ambito.value, sin_regla: props.reglaId || undefined })
  } catch {
    base.value = { pasos: [], orden: [], niveles: [] }
  } finally {
    cargando.value = false
  }
}
watch(() => [props.form.nivel, props.form.region, props.form.pais, props.form.puerto], cargarBase, { immediate: true })

const propios = computed(() => props.modelValue?.pasos || [])
const clave = (p) => `${p.paso}|${p.modo || ''}`
const ESTE = { nivel: 'ESTE', nombre: t('This rule') }

// Resultado: lo heredado con los cambios de esta regla encima
const filas = computed(() => {
  const mapa = new Map()
  const orden = []
  for (const p of base.value.pasos) {
    mapa.set(clave(p), { ...p, heredado: p, propio: null })
    if (!orden.includes(p.paso)) orden.push(p.paso)
  }
  const quitados = []
  for (const e of propios.value) {
    const k = clave(e)
    if (e.quitar) {
      if (mapa.has(k)) quitados.push(mapa.get(k))
      mapa.delete(k)
      continue
    }
    const h = mapa.get(k)?.heredado || null
    mapa.set(k, { ...e, nombre: nombre(e.paso), origen: ESTE, heredado: h, propio: e })
    if (!orden.includes(e.paso)) orden.push(e.paso)
  }
  const o = props.modelValue?.orden ? [...props.modelValue.orden.filter((c) => orden.includes(c)), ...orden.filter((c) => !props.modelValue.orden.includes(c))] : orden
  const pos = Object.fromEntries(o.map((c, i) => [c, i]))
  return { lista: [...mapa.values()].sort((a, b) => (pos[a.paso] ?? 999) - (pos[b.paso] ?? 999) || (a.modo || '').localeCompare(b.modo || '')), quitados, orden: o }
})
const codigos = computed(() => [...new Set(filas.value.lista.map((f) => f.paso))])

function guardar(pasos, orden = props.modelValue?.orden || null) {
  emit('update:modelValue', { pasos, orden })
}
function sobrescribir(f) {
  guardar([...propios.value.filter((e) => clave(e) !== clave(f)), { paso: f.paso, ref: f.ref || '', dias: f.dias || 0, habiles: !!f.habiles, modo: f.modo || '', quitar: false }])
}
function poner(f, campo, valor) {
  guardar(propios.value.map((e) => (clave(e) === clave(f) ? { ...e, [campo]: valor } : e)))
}
function quitar(f) {
  const resto = propios.value.filter((e) => clave(e) !== clave(f))
  // Si viene heredado, esta regla lo quita; si es propio, solo se borra
  guardar(f.heredado ? [...resto, { paso: f.paso, modo: f.modo || '', quitar: true }] : resto)
}
function restaurar(f) {
  guardar(propios.value.filter((e) => clave(e) !== clave(f)))
}
function agregar() {
  if (!nuevo.value) return
  const ancla = filas.value.lista.find((f) => !f.ref)?.paso || ''
  guardar([...propios.value, { paso: nuevo.value, ref: ancla, dias: 0, habiles: false, modo: '', quitar: false }])
  nuevo.value = ''
}
function mover(f, d) {
  const o = [...filas.value.orden]
  const i = o.indexOf(f.paso)
  const j = i + d
  if (i < 0 || j < 0 || j >= o.length) return
  ;[o[i], o[j]] = [o[j], o[i]]
  guardar(propios.value, o)
}
const diasTxt = (f) => (!f.ref ? t('Anchor') : t('{0} {1} {2}', [Math.abs(f.dias || 0), f.habiles ? t('business days') : t('days'), (f.dias || 0) < 0 ? t('before {0}', [nombre(f.ref)]) : t('after {0}', [nombre(f.ref)])]))
const disponibles = computed(() => catalogo.value.filter((p) => !filas.value.lista.some((f) => f.paso === p.codigo && !f.modo)).map((p) => ({ valor: p.codigo, texto: p.nombre, sub: p.codigo })))
</script>

<template>
  <div class="editor-lt">
    <p v-if="base.niveles?.length > 1" class="ayuda">{{ t('Inherits from: {0}.', [base.niveles.slice(0, -1).map((n) => n.nombre).join(' › ')]) }}</p>
    <p v-if="cargando" class="ayuda">{{ t('Loading…') }}</p>
    <ol class="lista">
      <li v-for="(f, i) in filas.lista" :key="`${f.paso}|${f.modo}`" class="paso" :class="{ heredado: !f.propio, cambio: f.propio && f.heredado }">
        <span class="num">{{ i + 1 }}</span>
        <div class="cuerpo">
          <div class="titulo">
            <b>{{ tx(f.nombre || nombre(f.paso)) }}</b>
            <span v-if="f.modo" class="etiqueta">{{ tx(MODOS.find((m) => m[0] === f.modo)?.[1]) }}</span>
            <span class="origen" :class="f.propio ? 'propio' : ''">{{ tx(f.propio ? (f.heredado ? t('Overridden here') : t('Added here')) : t('From {0}', [f.origen?.nombre])) }}</span>
          </div>
          <div v-if="!f.propio" class="sub">{{ tx(diasTxt(f)) }}</div>
          <div v-else class="campos">
            <label class="campo"><span>{{ t('Reference') }}</span>
              <Seleccion :model-value="f.ref || ''" @update:model-value="poner(f, 'ref', $event)">
                <option value="">{{ t('None (anchor)') }}</option>
                <option v-for="c in codigos.filter((x) => x !== f.paso)" :key="c" :value="c">{{ tx(nombre(c)) }}</option>
              </Seleccion></label>
            <label v-if="f.ref" class="campo dias"><span>{{ t('Days') }}</span>
              <input :value="Math.abs(f.dias || 0)" type="number" min="0" max="730" @input="poner(f, 'dias', (f.dias < 0 ? -1 : 1) * Number($event.target.value || 0))" /></label>
            <label v-if="f.ref" class="campo"><span>{{ t('When') }}</span>
              <Seleccion :model-value="(f.dias || 0) < 0 ? 'antes' : 'despues'" @update:model-value="poner(f, 'dias', ($event === 'antes' ? -1 : 1) * Math.abs(f.dias || 0))">
                <option value="antes">{{ t('Before') }}</option><option value="despues">{{ t('After') }}</option>
              </Seleccion></label>
            <label v-if="f.ref" class="check"><input type="checkbox" :checked="f.habiles" @change="poner(f, 'habiles', $event.target.checked)" />{{ t('Business days') }}</label>
            <label class="campo"><span>{{ t('Applies to') }}</span>
              <Seleccion :model-value="f.modo || ''" :disabled="!!f.heredado" @update:model-value="poner(f, 'modo', $event)">
                <option v-for="[v, txt] in MODOS" :key="v" :value="v">{{ tx(txt) }}</option>
              </Seleccion></label>
          </div>
          <div v-if="f.propio && f.heredado" class="sub">{{ t('Inherited: {0} ({1})', [diasTxt(f.heredado), f.heredado.origen?.nombre]) }}</div>
        </div>
        <div class="acciones">
          <button type="button" class="btn btn-chico btn-fantasma" :disabled="i === 0" :aria-label="t('Move up')" :title="t('Move up')" @click="mover(f, -1)"><Icono nombre="arriba" :tam="14" /></button>
          <button type="button" class="btn btn-chico btn-fantasma" :disabled="i === filas.lista.length - 1" :aria-label="t('Move down')" :title="t('Move down')" @click="mover(f, 1)"><Icono nombre="abajo" :tam="14" /></button>
          <button v-if="!f.propio" type="button" class="btn btn-chico" @click="sobrescribir(f)"><Icono nombre="editar" :tam="13" />{{ t('Override') }}</button>
          <button v-if="f.propio && f.heredado" type="button" class="btn btn-chico btn-fantasma" :title="t('Use the inherited value again')" @click="restaurar(f)">{{ t('Restore') }}</button>
          <button type="button" class="btn btn-chico btn-fantasma" :aria-label="t('Remove step')" :title="tx(f.heredado ? t('Remove it at this level') : t('Remove step'))" @click="quitar(f)"><Icono nombre="basura" :tam="14" /></button>
        </div>
      </li>
    </ol>
    <div v-if="filas.quitados.length" class="quitados">
      <span class="ayuda">{{ t('Removed at this level:') }}</span>
      <button v-for="q in filas.quitados" :key="`${q.paso}|${q.modo}`" type="button" class="etiqueta" :title="t('Restore')" @click="restaurar(q)">{{ tx(q.nombre || nombre(q.paso)) }} ↺</button>
    </div>
    <div class="agregar">
      <SelectBusqueda v-model="nuevo" :opciones="disponibles" :placeholder="t('Add a step from the catalog…')" :etiqueta="t('Step')" />
      <button type="button" class="btn btn-chico" :disabled="!nuevo" @click="agregar"><Icono nombre="mas" :tam="14" />{{ t('Add step') }}</button>
      <router-link to="/mantenimiento?catalogo=pasos_lt" class="enlace ayuda">{{ t('Manage the steps catalog') }}</router-link>
    </div>
  </div>
</template>

<style scoped>
.editor-lt { display: flex; flex-direction: column; gap: 8px; }
.lista { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
.paso { display: grid; grid-template-columns: auto 1fr auto; gap: 10px; align-items: start; padding: 9px 10px; border: 1px solid var(--linea); border-radius: var(--radio); background: var(--superficie); }
.paso.heredado { background: var(--superficie-2); }
.paso.heredado .titulo b { color: var(--tinta-2); }
.paso.cambio { border-color: color-mix(in srgb, var(--acento) 45%, var(--linea)); }
.num { width: 22px; height: 22px; border-radius: 50%; display: grid; place-items: center; background: var(--acento-claro); color: var(--acento-texto); font-size: 0.75rem; font-weight: 700; }
.titulo { display: flex; flex-wrap: wrap; gap: 4px 8px; align-items: center; }
.origen { font-size: 0.75rem; color: var(--tinta-3); }
.origen.propio { color: var(--acento-texto); font-weight: 650; }
.sub { font-size: 0.8rem; color: var(--tinta-3); margin-top: 2px; }
.campos { display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 6px 10px; margin-top: 6px; align-items: end; }
.campos .dias input { width: 100%; }
.campos .check { padding-bottom: 8px; }
.acciones { display: flex; gap: 2px; flex-wrap: wrap; justify-content: flex-end; }
.quitados { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
.quitados .etiqueta { cursor: pointer; border: 0; text-decoration: line-through; }
.agregar { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.agregar :deep(.sb) { min-width: 240px; }
@media (max-width: 560px) {
  .paso { grid-template-columns: auto 1fr; }
  .acciones { grid-column: 1 / -1; }
}
</style>
