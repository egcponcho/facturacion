<script setup>
import { t, tx } from '@/i18n/index.js'
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '@/nucleo/api'
import FiltroMulti from '@/componentes/FiltroMulti.vue'
import Icono from '@/componentes/Icono.vue'
import Interruptor from '@/componentes/Interruptor.vue'
import Modal from '@/componentes/Modal.vue'
import Paginacion from '@/componentes/Paginacion.vue'
import Seleccion from '@/componentes/Seleccion.vue'
import EditorRegla from './EditorRegla.vue'
import SelectBusqueda from '@/componentes/SelectBusqueda.vue'
import { cargarContexto } from '@/modulos/clasificacion/useClasificacion'
import { puede } from '@/stores/sesion'
import { avisar, errorApi } from '@/stores/ui'
import { fmtNum } from '@/nucleo/utils'

// Reglas de clasificación en datos. Las del sistema describen cómo decide el
// motor (paquete 02); las de selección nacional son las condiciones del
// producto que eligen cada código nacional dentro de su subpartida, separadas
// del código oficial: se revisan, priorizan y apagan aquí.
const props = defineProps({ paises: { type: Array, default: () => [] }, condiciones: { type: Object, default: () => ({}) } })
const edita = puede('clasificacion.configurar')
const datos = ref({ items: [], total: 0, por_tipo: {} })
const route = useRoute()
const f = reactive({ q: '', tipo: '', pais: '', page: 1, size: 50 })
const modal = ref(null)
const ocupado = ref(false)

const TIPO = { HARD_CONSTRAINT: t('Limit the codes'), SOFT_SIGNAL: t('Prefer codes'), QUESTION_GATE: t('Ask a question'), REVIEW_GATE: t('Send to review'), NATIONAL_SELECT: t('National selection') }
const FUENTE = { INTERNAL_ENGINE: t('Engine'), SHEET_RULES: t('Product sheet logic'), LEGAL_NOTE: t('Legal note'), NATIONAL_TARIFF: t('National tariff'), LEARNED: t('Learned'), MANUAL: t('Manual') }
const OPERADOR = { EQUAL: '=', NOT_EQUAL: '≠', IN: t('one of'), GT: '>', GTE: '≥', LT: '<', LTE: '≤', BETWEEN: t('between'), EXISTS: t('has a value') }
const PESTANAS = [['', t('All')], ['NATIONAL_SELECT', t('National selection')], ['HARD_CONSTRAINT', t('Limit the codes')], ['SHEET_RULES', t('Product sheet logic')],
  ['QUESTION_GATE', t('Questions')], ['REVIEW_GATE', t('Review')], ['SOFT_SIGNAL', t('Prefer codes')]]

let temporizador = null
async function cargar() {
  try {
    // Las reglas de la ficha (por categoría) van en su propia pestaña
    const fuente = f.tipo === 'SHEET_RULES' ? 'SHEET_RULES' : f.tipo ? '-SHEET_RULES' : undefined
    datos.value = await api.get('/aranceles/reglas', { q: f.q || undefined, tipo: f.tipo && f.tipo !== 'SHEET_RULES' ? f.tipo : undefined, fuente,
      pais: f.pais || undefined, page: f.page, size: f.size })
  } catch (e) {
    errorApi(e)
  }
}
function buscar() {
  clearTimeout(temporizador)
  temporizador = setTimeout(() => { f.page = 1; cargar() }, 250)
}
const filtrar = (k, v) => { f[k] = v; f.page = 1; cargar() }
onMounted(async () => {
  cargar()
  cargarCatalogo()
  // Desde un artículo: regla nueva ya llena con la decisión de aduanas
  if (route.query.desde && edita) {
    try {
      editor.value = { regla: null, borrador: await api.get(`/aranceles/reglas/desde-producto/${route.query.desde}`) }
    } catch (e) {
      errorApi(e)
    }
  }
})

// Etiquetas del catálogo de atributos (también los que se derivan de la composición)
const catalogo = ref({})
async function cargarCatalogo() {
  try {
    const a = await api.get('/aranceles/atributos')
    catalogo.value = Object.fromEntries(a.items.map((x) => [x.codigo, { label: x.etiqueta, ops: Object.fromEntries((x.opciones_min || []).map((o) => [o.codigo, o.etiqueta])) }]))
  } catch {
    /* sin catálogo se muestran los códigos */
  }
}
function valorTxt(c) {
  const v = Array.isArray(c.valor) ? c.valor : [c.valor]
  const ops = props.condiciones[c.campo]?.ops || catalogo.value[c.campo]?.ops || {}
  return v.map((x) => (x === true ? t('Yes') : x === false ? t('No') : x === '' ? t('(no value)') : ops[x] || x)).join(', ') + (c.valor_hasta != null ? ` – ${c.valor_hasta}` : '')
}
const DERIVADOS = { valorCIF: t('CIF value (US$)'), fibra: t('Predominant fiber'), material_corte: t('Outer material (non-textile)'), categoria: t('Product category') }
const campoTxt = (c) => DERIVADOS[c.campo] || props.condiciones[c.campo]?.label || catalogo.value[c.campo]?.label || c.campo
const total = computed(() => Object.values(datos.value.por_tipo || {}).reduce((a, b) => a + b, 0))

async function guardar(r, cambios, msg) {
  try {
    const nuevo = await api.patch(`/aranceles/reglas/${r.id}`, cambios)
    Object.assign(r, nuevo)
    if (msg) avisar(msg)
    if (r.tipo_regla === 'NATIONAL_SELECT') cargarContexto(true)
    return true
  } catch (e) {
    errorApi(e)
    return false
  }
}

// ---- Edición: en selección nacional, las condiciones con el mismo catálogo que la ficha
const editor = ref(null) // regla propia: constructor completo (ámbito, condiciones Y/O, acción)
function abrir(r) {
  if (r.editable_completa) return (editor.value = { regla: r })
  const cond = {}
  for (const c of r.condiciones) {
    if (c.campo === 'valorCIF') cond[c.operador === 'LTE' ? 'cifMax' : 'cifMin'] = c.valor
    else cond[c.campo] = c.valor
  }
  modal.value = { r, prioridad: r.prioridad, efecto: r.efecto || '', requiere_revision: r.requiere_revision, cond, extra: '' }
}
const condUsadas = computed(() => {
  if (!modal.value) return []
  const todas = props.condiciones
  return Object.keys(modal.value.cond).filter((k) => todas[k]).map((k) => [k, todas[k]])
})
const condLibres = computed(() => Object.entries(props.condiciones).filter(([k]) => !(k in (modal.value?.cond || {}))).map(([k, d]) => ({ valor: k, texto: d.label })))
function valorCond(k) {
  const v = modal.value.cond[k]
  return v === undefined ? [] : Array.isArray(v) ? v : [v]
}
function ponerCond(k, v) {
  const c = { ...modal.value.cond }
  if (v === null || (Array.isArray(v) && !v.length)) delete c[k]
  else c[k] = Array.isArray(v) && v.length === 1 ? v[0] : v
  modal.value.cond = c
}
function agregarCond(k) {
  if (!k) return
  const d = props.condiciones[k]
  modal.value.cond = { ...modal.value.cond, [k]: d.tipo === 'sino' ? true : d.tipo === 'numero' ? 0 : [] }
  modal.value.extra = ''
}
function quitarCond(k) {
  const c = { ...modal.value.cond }
  delete c[k]
  modal.value.cond = c
}
async function guardarModal() {
  const m = modal.value
  const cambios = { prioridad: Number(m.prioridad) || 0, efecto: m.efecto || null, requiere_revision: m.requiere_revision }
  if (m.r.tipo_regla === 'NATIONAL_SELECT') {
    cambios.condiciones = Object.entries(m.cond).filter(([, v]) => !(Array.isArray(v) && !v.length)).map(([k, v]) =>
      k === 'cifMax' || k === 'cifMin' ? { campo: 'valorCIF', operador: k === 'cifMax' ? 'LTE' : 'GT', valor: Number(v) }
        : { campo: k, operador: Array.isArray(v) ? 'IN' : 'EQUAL', valor: v })
  }
  ocupado.value = true
  if (await guardar(m.r, cambios, t('Rule saved.'))) modal.value = null
  ocupado.value = false
}
</script>

<template>
  <section>
    <p class="ayuda">{{ t('How the engine decides, as data. System rules come from the dynamic engine package; national selection rules are the product conditions that pick each national code within its subheading, kept apart from the official code.') }}</p>
    <div class="pestanas-pildora">
      <button v-for="[k, l] in PESTANAS" :key="k" class="pildora" :aria-pressed="f.tipo === k" @click="filtrar('tipo', k)">
        {{ tx(l) }} <span class="cuenta">{{ fmtNum(k ? datos.por_tipo[k] || 0 : total) }}</span></button>
    </div>
    <div class="filtros" v-filtros>
      <label class="buscador"><Icono nombre="buscar" :tam="16" /><input v-model="f.q" type="search" :placeholder="t('Rule, family, attribute or national code')" :aria-label="t('Search')" @input="buscar" /></label>
      <SelectBusqueda :model-value="f.pais" :opciones="paises.map((p) => ({ valor: p.iso, texto: `${p.iso} · ${p.nombre}` }))" :vacio="t('All countries')" :etiqueta="t('Country')" @update:model-value="filtrar('pais', $event)" />
      <button v-if="edita" class="btn btn-primario separar" @click="editor = { regla: null }"><Icono nombre="mas" />{{ t('New rule') }}</button>
    </div>
    <div class="tabla-marco">
      <table class="tabla" v-tarjetas>
        <thead><tr><th>{{ t('Rule') }}</th><th>{{ t('Type') }}</th><th>{{ t('Applies to') }}</th><th>{{ t('Conditions') }}</th><th class="num">{{ t('Priority') }}</th><th>{{ t('Active') }}</th><th></th></tr></thead>
        <tbody>
          <tr v-if="!datos.items.length"><td colspan="7" class="vacio">{{ t('No results.') }}</td></tr>
          <tr v-for="r in datos.items" :key="r.id" :class="{ apagada: !r.activo }">
            <td :data-label="t('Rule')" class="regla envolver">
              <template v-if="r.inciso"><span class="codigo-sac">{{ tx(r.pais) }} {{ tx(r.inciso.codigo) }}</span><span class="sub">{{ tx(r.inciso.descripcion || '') }}</span></template>
              <template v-else><b class="codigo">{{ tx(r.codigo) }}</b><span class="sub envolver">{{ tx(r.efecto || r.familia) }}</span></template>
            </td>
            <td :data-label="t('Type')"><span class="etiqueta" :class="{ acento: r.tipo_regla === 'HARD_CONSTRAINT' }">{{ tx(TIPO[r.tipo_regla] || r.tipo_regla) }}</span>
              <span class="sub">{{ tx(FUENTE[r.tipo_fuente] || r.tipo_fuente) }}<template v-if="r.requiere_revision"> · {{ t('needs review') }}</template></span></td>
            <td :data-label="t('Applies to')" class="codigo">{{ tx(r.tipo_ambito === 'NATIONAL_CODE' ? r.codigo_ambito : `${r.tipo_ambito} · ${r.codigo_ambito}`) }}</td>
            <td :data-label="t('Conditions')" class="envolver condiciones">
              <span v-if="!r.condiciones.length" class="ayuda">{{ t('Always') }}</span>
              <span v-if="r.accion?.mapa" class="cond accion">→ {{ tx(r.accion.tipo) }} {{ t('by {0}', [campoTxt({ campo: r.accion.por })]) }}:
                {{ tx(Object.entries(r.accion.mapa).map(([k, v]) => `${k ? valorTxt({ campo: r.accion.por, valor: k }) : t('(no value)')} ${v}`).join(' · ')) }}</span>
              <span v-else-if="r.accion?.tipo" class="cond accion">→ {{ tx(r.accion.tipo) }} {{ tx((r.accion.codigos || r.accion.atributos || []).join(', ')) }}</span>
              <span v-for="c in r.condiciones" :key="c.id" class="cond"><b>{{ tx(campoTxt(c)) }}</b> {{ tx(c.negado ? t('not') + ' ' : '') }}{{ tx(OPERADOR[c.operador] || c.operador) }} {{ tx(valorTxt(c)) }}</span>
            </td>
            <td :data-label="t('Priority')" class="num">{{ fmtNum(r.prioridad) }}</td>
            <td :data-label="t('Active')"><Interruptor :model-value="r.activo" :deshabilitado="!edita" :etiqueta="t('Active')" @update:model-value="guardar(r, { activo: $event })" /></td>
            <td><button v-if="edita" type="button" class="btn-icono" :aria-label="t('Edit')" @click="abrir(r)"><Icono nombre="editar" :tam="15" /></button></td>
          </tr>
        </tbody>
      </table>
    </div>
    <Paginacion :page="f.page" :size="f.size" :total="datos.total" @cambiar="(p) => { f.page = p; cargar() }" @tamano="(n) => { f.size = n; f.page = 1; cargar() }" />

    <EditorRegla v-if="editor" :regla="editor.regla" :borrador="editor.borrador" @cerrar="editor = null" @guardada="editor = null; cargar()" />
    <Modal v-if="modal" :titulo="modal.r.inciso ? t('Selection rule for {0} {1}', [modal.r.pais, modal.r.inciso.codigo]) : t('Rule {0}', [modal.r.codigo])" ancho="640px" @cerrar="modal = null">
      <div class="campos">
        <label class="campo"><span>{{ t('Priority') }}</span><input v-model="modal.prioridad" type="number" min="0" max="10000" class="entrada" /></label>
        <label class="check"><input v-model="modal.requiere_revision" type="checkbox" /><span>{{ t('Requires specialist review') }}</span></label>
        <label class="campo ancho"><span>{{ t('Effect / rationale') }}</span><input v-model="modal.efecto" class="entrada" maxlength="500" /></label>
      </div>
      <template v-if="modal.r.tipo_regla === 'NATIONAL_SELECT'">
        <h3 class="mt">{{ t('When it applies') }}</h3>
        <p class="ayuda">{{ t('All conditions must match the technical sheet. Without conditions the code applies to any product of its subheading.') }}</p>
        <div class="conds">
          <div v-for="[k, d] in condUsadas" :key="k" class="campo">
            <span>{{ tx(d.label) }} <button type="button" class="btn-texto" :aria-label="t('Remove')" @click="quitarCond(k)">×</button></span>
            <FiltroMulti v-if="d.tipo === 'opciones'" :model-value="valorCond(k)" :etiqueta="t('Values')" vacio="any" :opciones="Object.entries(d.ops).map(([valor, texto]) => ({ valor, texto }))" @update:model-value="(v) => ponerCond(k, v)" />
            <Seleccion v-else-if="d.tipo === 'sino'" class="entrada" :value="String(modal.cond[k])" @change="ponerCond(k, $event === 'true')">
              <option value="true">{{ t('Yes') }}</option><option value="false">{{ t('No') }}</option>
            </Seleccion>
            <input v-else class="entrada" type="number" min="0" step="0.01" :value="modal.cond[k] ?? ''" @input="ponerCond(k, $event.target.value === '' ? null : Number($event.target.value))" />
          </div>
        </div>
        <SelectBusqueda v-model="modal.extra" class="mt-chico" :opciones="condLibres" :placeholder="t('Add a condition…')" :etiqueta="t('Condition')" @update:model-value="agregarCond" />
      </template>
      <template v-else-if="modal.r.condiciones.length">
        <h3 class="mt">{{ t('Conditions') }}</h3>
        <ul class="lista-cond"><li v-for="c in modal.r.condiciones" :key="c.id">{{ t('Group {0}', [c.grupo]) }} · <b>{{ tx(campoTxt(c)) }}</b> {{ tx(OPERADOR[c.operador] || c.operador) }} {{ tx(valorTxt(c)) }}</li></ul>
        <p class="ayuda">{{ t('System rule conditions are loaded from the dynamic engine package.') }}</p>
      </template>
      <template #pie>
        <button class="btn" @click="modal = null">{{ t('Cancel') }}</button>
        <button class="btn btn-primario" :disabled="ocupado" @click="guardarModal">{{ t('Save') }}</button>
      </template>
    </Modal>
  </section>
</template>

<style scoped>
.pestanas-pildora { margin: 10px 0; }
.regla { min-width: 220px; max-width: 420px; }
.regla .sub { display: block; }
.condiciones { min-width: 200px; max-width: 360px; }
.cond { display: inline-block; margin: 0 6px 3px 0; padding: 2px 7px; border-radius: 8px; background: var(--superficie-2); font-size: 0.82rem; }
tr.apagada td { opacity: 0.55; }
.cond.accion { background: var(--acento-claro); color: var(--acento-texto); font-weight: 600; }
.campos { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; align-items: end; }
.campo.ancho { grid-column: 1 / -1; }
.conds { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 10px; }
.lista-cond { margin: 0; padding-inline-start: 18px; font-size: 0.88rem; }
.mt { margin: 16px 0 4px; font-size: 1rem; }
.mt-chico { margin-top: 10px; }
</style>
