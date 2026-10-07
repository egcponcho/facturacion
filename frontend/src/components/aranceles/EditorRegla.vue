<script setup>
import { t, tx } from '../../i18n/index.js'
import { computed, onMounted, ref } from 'vue'
import { api } from '../../api'
import EditorCondiciones from './EditorCondiciones.vue'
import FiltroMulti from '../FiltroMulti.vue'
import Modal from '../Modal.vue'
import SelectBusqueda from '../SelectBusqueda.vue'
import { cargarContexto } from '../../clasificacion/useClasificacion'
import { avisar, errorApi } from '../../stores/ui'

// Regla propia del motor: DÓNDE aplica (ámbito), CUÁNDO (condiciones en
// grupos Y / O) y QUÉ hace (restringir, excluir o subir códigos, preguntar
// atributos o exigir revisión). El motor del servidor la ejecuta al clasificar.
const props = defineProps({ regla: { type: Object, default: null } })
const emit = defineEmits(['cerrar', 'guardada'])
const atributos = ref([])
const dominios = ref([])
const categorias = ref({})
const ocupado = ref(false)
const r = props.regla
const m = ref({
  tipo_regla: r?.tipo_regla || 'HARD_CONSTRAINT', tipo_ambito: r?.tipo_ambito || 'DOMAIN', codigo_ambito: r?.codigo_ambito || '',
  prioridad: r?.prioridad ?? 800, efecto: r?.efecto || '', requiere_revision: !!r?.requiere_revision,
  condiciones: (r?.condiciones || []).map(({ grupo, campo, operador, valor, valor_hasta, negado }) => ({ grupo, campo, operador, valor, valor_hasta, negado })),
  accion: { tipo: r?.accion?.tipo || 'RESTRICT', codigos: (r?.accion?.codigos || []).join(', '), peso: r?.accion?.peso ?? null,
    atributos: r?.accion?.atributos || [], mensaje: r?.accion?.mensaje || '' },
  // Código según un hecho (p. ej. subpartida por fibra predominante): [[valor, código]]
  por: r?.accion?.por || '', mapa: Object.entries(r?.accion?.mapa || {}),
})
onMounted(async () => {
  try {
    const [a, d] = await Promise.all([api.get('/aranceles/atributos'), api.get('/aranceles/oficial/dominios')])
    atributos.value = a.items.filter((x) => x.activo)
    dominios.value = d
    // Categorías de la configuración (las mismas que ve la ficha)
    const ctx = await cargarContexto()
    categorias.value = Object.fromEntries((ctx.categorias || []).map((c) => [c.codigo, c.nombre_corto || c.nombre]))
  } catch (e) {
    errorApi(e)
  }
})
const TIPOS = [['HARD_CONSTRAINT', t('Limit the codes'), t('Keeps only some codes, or excludes some, when the conditions are met.')],
  ['SOFT_SIGNAL', t('Prefer codes'), t('Raises (or adds) candidate codes; never excludes.')],
  ['QUESTION_GATE', t('Ask a question'), t('Asks more questions when the conditions are met.')],
  ['REVIEW_GATE', t('Send to review'), t('Requires specialist review when the conditions are met.')]]
const ACCIONES = { HARD_CONSTRAINT: [['RESTRICT', t('Keep only these codes')], ['EXCLUDE', t('Exclude these codes')]], SOFT_SIGNAL: [['BOOST', t('Raise these codes')]],
  QUESTION_GATE: [['ASK', t('Ask these questions')]], REVIEW_GATE: [['REVIEW', t('Require review')]] }
const AMBITOS = [['SYSTEM', t('Whole system')], ['DOMAIN', t('Product family')], ['CATEGORY', t('Product category')], ['CHAPTER', t('Chapter')],
  ['HEADING', t('Heading')], ['SUBHEADING', t('Subheading')]]
const sistema = computed(() => [
  { valor: 'dominio', texto: t('Domain'), opciones: dominios.value.map((d) => ({ valor: d.codigo, texto: d.nombre })) },
  { valor: 'categoria', texto: t('Product category'), opciones: Object.entries(categorias.value).map(([valor, texto]) => ({ valor, texto })) },
  // Los hechos que se derivan de la composición (fibra, material…) son atributos del catálogo: van con los demás
])
function tipo(v) {
  m.value.tipo_regla = v
  m.value.accion.tipo = ACCIONES[v][0][0]
}
const necesitaCodigos = computed(() => ['RESTRICT', 'EXCLUDE', 'BOOST'].includes(m.value.accion.tipo))
async function guardar() {
  const x = m.value
  const cuerpo = {
    tipo_regla: x.tipo_regla, tipo_ambito: x.tipo_ambito, codigo_ambito: x.tipo_ambito === 'SYSTEM' ? 'ALL' : x.codigo_ambito,
    prioridad: Number(x.prioridad) || 0, efecto: x.efecto || null, requiere_revision: x.requiere_revision,
    condiciones: x.condiciones.filter((c) => c.campo),
    accion: { tipo: x.accion.tipo, codigos: x.por ? [] : x.accion.codigos.split(/[,\s]+/).filter(Boolean), peso: x.accion.peso ? Number(x.accion.peso) : null,
      atributos: x.accion.atributos, mensaje: x.accion.mensaje || null,
      ...(x.por ? { por: x.por, mapa: Object.fromEntries(x.mapa.filter(([, c]) => String(c).trim())) } : {}) },
  }
  ocupado.value = true
  try {
    const g = r ? await api.patch(`/aranceles/reglas/${r.id}`, cuerpo) : await api.post('/aranceles/reglas', cuerpo)
    avisar(t('Rule {0} saved. The engine uses it right away.', [g.codigo]))
    cargarContexto(true)
    emit('guardada', g)
  } catch (e) {
    errorApi(e)
  } finally {
    ocupado.value = false
  }
}
</script>

<template>
  <Modal :titulo="r ? t('Rule {0}', [r.codigo]) : t('New rule')" ancho="820px" @cerrar="emit('cerrar')">
    <h3 class="paso">1 · {{ t('What it does') }}</h3>
    <div class="tipos" role="radiogroup" :aria-label="t('Rule type')">
      <button v-for="[v, l, d] in TIPOS" :key="v" type="button" role="radio" class="tipo" :aria-checked="m.tipo_regla === v" @click="tipo(v)">
        <b>{{ tx(l) }}</b><small>{{ tx(d) }}</small></button>
    </div>

    <h3 class="paso">2 · {{ t('Where it applies') }}</h3>
    <div class="rejilla-campos">
      <label class="campo"><span>{{ t('Applies to') }}</span>
        <select v-model="m.tipo_ambito" class="entrada" @change="m.codigo_ambito = ''"><option v-for="[v, l] in AMBITOS" :key="v" :value="v">{{ tx(l) }}</option></select></label>
      <label v-if="m.tipo_ambito === 'DOMAIN'" class="campo"><span>{{ t('Domain') }}</span>
        <SelectBusqueda v-model="m.codigo_ambito" :opciones="dominios.map((d) => ({ valor: d.codigo, texto: d.nombre }))" :etiqueta="t('Domain')" /></label>
      <label v-else-if="m.tipo_ambito === 'CATEGORY'" class="campo"><span>{{ t('Product category') }}</span>
        <SelectBusqueda v-model="m.codigo_ambito" :opciones="Object.entries(categorias).map(([valor, texto]) => ({ valor, texto }))" :etiqueta="t('Product category')" /></label>
      <label v-else-if="m.tipo_ambito !== 'SYSTEM'" class="campo"><span>{{ t('Code') }}</span>
        <input v-model="m.codigo_ambito" class="entrada" inputmode="numeric" :placeholder="m.tipo_ambito === 'CHAPTER' ? '64' : m.tipo_ambito === 'HEADING' ? '6404' : '640419'" /></label>
      <label class="campo"><span>{{ t('Priority') }}</span><input v-model="m.prioridad" type="number" min="0" max="10000" class="entrada" /></label>
    </div>

    <h3 class="paso">3 · {{ t('When (conditions)') }}</h3>
    <EditorCondiciones v-model="m.condiciones" :atributos="atributos" :sistema="sistema" />

    <h3 class="paso">4 · {{ t('Then') }}</h3>
    <div class="rejilla-campos">
      <label class="campo"><span>{{ t('Action') }}</span>
        <select v-model="m.accion.tipo" class="entrada"><option v-for="[v, l] in ACCIONES[m.tipo_regla]" :key="v" :value="v">{{ tx(l) }}</option></select></label>
      <div v-if="necesitaCodigos && m.por" class="campo ancho"><span>{{ t('Code by {0}', [m.por === 'fibra' ? t('predominant fiber') : m.por]) }}</span>
        <div class="mapa">
          <label v-for="(fila, i) in m.mapa" :key="i" class="mapa-fila"><span>{{ fila[0] ? tx(fila[0]) : t('(no value)') }}</span>
            <input v-model="fila[1]" class="entrada" inputmode="numeric" :aria-label="t('Code')" /></label>
        </div>
      </div>
      <label v-else-if="necesitaCodigos" class="campo ancho"><span>{{ t('Codes (HS6, heading or chapter)') }}</span>
        <input v-model="m.accion.codigos" class="entrada" :placeholder="t('e.g. 6401.92, 6402')" /></label>
      <label v-if="m.accion.tipo === 'BOOST'" class="campo"><span>{{ t('Weight') }}</span><input v-model="m.accion.peso" type="number" step="any" class="entrada" placeholder="5" /></label>
      <label v-if="m.accion.tipo === 'ASK'" class="campo ancho"><span>{{ t('Questions to ask') }}</span>
        <FiltroMulti v-model="m.accion.atributos" :etiqueta="t('Attributes')" vacio="—" :opciones="atributos.map((a) => ({ valor: a.codigo, texto: a.etiqueta }))" /></label>
      <label v-if="m.accion.tipo === 'REVIEW'" class="campo ancho"><span>{{ t('Message for the specialist') }}</span><input v-model="m.accion.mensaje" class="entrada" maxlength="300" /></label>
      <label class="campo ancho"><span>{{ t('Rationale / legal basis') }}</span><input v-model="m.efecto" class="entrada" maxlength="500" :placeholder="t('e.g. Chapter 64, note 4')" /></label>
    </div>
    <template #pie>
      <button class="btn" @click="emit('cerrar')">{{ t('Cancel') }}</button>
      <button class="btn btn-primario" :disabled="ocupado" @click="guardar">{{ t('Save rule') }}</button>
    </template>
  </Modal>
</template>

<style scoped>
.paso { font-size: 0.95rem; margin: 14px 0 8px; }
.paso:first-child { margin-top: 0; }
.tipos { display: grid; grid-template-columns: repeat(auto-fill, minmax(170px, 1fr)); gap: 8px; }
.tipo { text-align: start; border: 1px solid var(--linea); border-radius: var(--radio); padding: 8px 10px; background: var(--superficie); cursor: pointer; display: grid; gap: 3px; font: inherit; color: inherit; }
.tipo small { color: var(--tinta-3); font-size: 0.78rem; }
.tipo[aria-checked='true'] { border-color: var(--acento); background: var(--acento-claro); }
.campo.ancho { grid-column: 1 / -1; }
.mapa { display: grid; grid-template-columns: repeat(auto-fill, minmax(190px, 1fr)); gap: 6px; }
.mapa-fila { display: grid; grid-template-columns: 1fr 110px; gap: 6px; align-items: center; font-size: 0.85rem; }
</style>
