<script setup>
import { computed, nextTick, ref } from 'vue'
import Seleccion from '../Seleccion.vue'
import { M } from '../../clasificacion/useClasificacion'

// Composición de una parte (tela exterior, corte, suela…) por filas
// material | %. Sugiere materiales (los que dice el nombre del producto, los
// que más usas en esta categoría y los típicos), completa el porcentaje que
// falta y reconoce lo que se pega como texto.
const props = defineProps({
  parte: { type: String, required: true },
  filas: { type: Array, required: true },
  s: { type: Object, required: true }, // ficha ya normalizada por el motor
  recs: { type: Array, default: () => [] },
  usadas: { type: Array, default: () => [] }, // [{txt, de}]
  principal: Boolean,
  editable: Boolean,
})
const emit = defineEmits(['cambio', 'ensenar'])
const caja = ref(null)
const pegado = ref('')
const verPegar = ref(false)

const r1 = (n) => Math.round(n * 10) / 10
const total = computed(() => M.totalFilas(props.filas))
const resto = computed(() => r1(100 - total.value))
const texto = computed(() => M.textoDesdeFilas(props.filas))
const sug = computed(() => M.sugerenciasComp(props.parte, { ...props.s, comp: { ...props.s.comp, [props.parte]: texto.value } }, props.recs))
const soloUno = computed(() => props.filas.length === 1 && props.filas[0].m && String(props.filas[0].pct).trim() === '')
const faltaUltimo = computed(() => props.filas.length > 1 && String(props.filas.at(-1).pct).trim() === '' && resto.value > 0)
const placeholders = computed(() => {
  let acum = 0
  return props.filas.map((f) => {
    const x = r1(100 - acum)
    acum += parseFloat(f.pct) || 0
    return x > 0 ? String(x) : '0'
  })
})

// Lo que el motor entiende de esta parte
const lectura = computed(() => {
  const v = texto.value
  if (!v.trim()) return { main: '', ambiguas: [], desconocidas: [] }
  const g = M.grupoTipo(props.s.tipo)
  const pr = M.prepMat(v)
  let main = ''
  if (props.parte === 'corte' || props.parte === 'suela') {
    const pm = M.parseMat(v, props.parte === 'suela' ? 'suela' : 'corte')
    if (pm?.pred) main = (props.parte === 'corte' ? 'Upper material: ' : 'Sole of ') + M.MAT_LBL[pm.pred]
  } else if (props.parte === 'exterior' && (g === 'prenda' || ['tienda', 'manta', 'toalla', 'saco', 'colchoneta'].includes(props.s.tipo))) {
    const c = M.parseComp(v)
    if (c?.pred) main = `Predominates: ${M.FIB_LBL[c.pred.grupo] || c.pred.grupo} (${c.pred.pct}%)`
  } else if (props.parte === 'exterior' || props.parte === 'material') {
    const c = M.claseMat({ ...props.s, comp: { ...props.s.comp, [props.parte]: v } }, props.parte)
    if (c) main = 'Main material: ' + ({ plastico: 'plastic', cuero: 'leather', metal: 'metal', madera: 'wood', papel: 'paper or board', vidrio: 'glass', paja: 'straw', textil: 'textile' }[c.pred] || c.pred)
  }
  return { main, ambiguas: pr.ambiguas, desconocidas: ['relleno', 'plantilla'].includes(props.parte) ? [] : pr.desconocidas }
})

function cambio() {
  emit('cambio', props.parte, texto.value)
}
async function enfocar(i, campo) {
  await nextTick()
  const el = caja.value?.querySelector(`[data-${campo}="${i}"]`)
  if (el) {
    el.focus()
    try { el.setSelectionRange(el.value.length, el.value.length) } catch { /* número */ }
  }
}
function agregar(m) {
  props.filas.push({ m: m || '', pct: '' })
  cambio()
  enfocar(props.filas.length - 1, m ? 'pct' : 'mat')
}
function quitar(i) {
  props.filas.splice(i, 1)
  cambio()
}
function escribirPct(i, e) {
  const v = e.target.value.replace(',', '.').replace(/[^\d.]/g, '')
  if (v !== e.target.value) e.target.value = v
  props.filas[i].pct = v
  cambio()
}
// Enter en el material pasa al %; en el % vacío pone lo que falta y sigue
function enterMat(i) {
  enfocar(i, 'pct')
}
function enterPct(i) {
  const f = props.filas[i]
  if (!String(f.pct).trim() && resto.value > 0) {
    f.pct = String(resto.value)
    cambio()
  }
  if (i + 1 < props.filas.length) enfocar(i + 1, 'pct')
  else caja.value?.querySelector('.mchips button')?.focus()
}
function llenar() {
  const last = props.filas.at(-1)
  last.pct = props.filas.length === 1 ? '100' : String(resto.value)
  cambio()
}
function usarTexto(txt) {
  props.filas.splice(0, props.filas.length, ...M.filasDesdeTexto(txt))
  cambio()
}
function pegar() {
  if (!pegado.value.trim()) return
  usarTexto(pegado.value)
  pegado.value = ''
  verPegar.value = false
}
</script>

<template>
  <div ref="caja" class="cparte">
    <div class="chead">
      <span class="lbl">{{ M.PARTE_LBL[props.parte] }}<span v-if="props.principal" class="req-ast" aria-hidden="true">*</span><span v-else class="opcional"> (optional)</span></span>
      <span v-if="props.filas.length && Math.abs(resto) < 0.05" class="est ok">Total 100%</span>
      <span v-else-if="props.filas.length && resto > 0" class="est pend">Total {{ total }}% · {{ resto }}% missing</span>
      <span v-else-if="props.filas.length" class="est mal">Total {{ total }}% · {{ -resto }}% over</span>
    </div>

    <div v-for="(f, i) in props.filas" :key="i" class="crow">
      <span class="cmat">
        <input v-model="f.m" class="entrada" type="text" :list="`mat_${props.parte}`" :data-mat="i" placeholder="Material" :aria-label="`Material ${i + 1}`"
               :disabled="!props.editable" @input="cambio" @keydown.enter.prevent="enterMat(i)" />
        <span v-if="f.m && M.claseTexto(f.m)" class="ctag" :class="M.claseTexto(f.m).clase" :title="`Counts as ${M.claseTexto(f.m).lbl.toLowerCase()} for the tariff`">{{ M.claseTexto(f.m).lbl }}</span>
        <span v-else-if="f.m && f.m.trim().length > 2" class="ctag desconocido" title="Not recognized: choose what it is below so the system learns it">?</span>
      </span>
      <span class="cpct">
        <input class="entrada" type="text" inputmode="decimal" :value="f.pct" :data-pct="i" :placeholder="placeholders[i]" :aria-label="`Percentage of ${f.m || 'material'}`"
               :disabled="!props.editable" @input="escribirPct(i, $event)" @keydown.enter.prevent="enterPct(i)" /><span>%</span>
      </span>
      <button v-if="props.editable" type="button" class="cx" :aria-label="`Remove ${f.m || 'row'}`" @click="quitar(i)">×</button>
    </div>
    <p v-if="!props.filas.length" class="cvacio">{{ props.editable ? 'Tap a material to add it.' : 'Not given.' }}</p>
    <datalist :id="`mat_${props.parte}`"><option v-for="m in sug.todos" :key="m" :value="m">{{ M.claseTexto(m)?.lbl || '' }}</option></datalist>

    <template v-if="props.editable">
      <div v-if="soloUno || faltaUltimo" class="mchips">
        <button type="button" class="lleno" @click="llenar">{{ soloUno ? `100% ${props.filas[0].m}` : `Complete ${props.filas.at(-1).m || 'last'} with ${resto}%` }}</button>
      </div>
      <div v-if="resto > 0 || !props.filas.length" class="mchips">
        <button v-for="x in sug.mats" :key="x.m" type="button" :class="{ rel: x.fuente === 'rel' }"
                :title="x.fuente === 'rel' ? 'Mentioned in the product name' : x.fuente === 'base' ? 'What you use most for this category' : 'Common for this product'"
                @click="agregar(x.m)">+ {{ x.m }}</button>
        <button type="button" @click="agregar('')">+ Other</button>
      </div>
      <div v-if="props.usadas.length && !props.filas.length" class="mchips">
        <span class="mlbl">Already used:</span>
        <button v-for="c in props.usadas" :key="c.txt" type="button" class="fix" @click="usarTexto(c.txt)">{{ c.txt }}<small>{{ c.de }}</small></button>
      </div>
    </template>

    <div v-if="lectura.main || lectura.ambiguas.length || lectura.desconocidas.length" class="chips-lectura">
      <span v-if="lectura.main" class="chip-l main">{{ lectura.main }}</span>
      <span v-for="w in lectura.ambiguas" :key="w" class="chip-l">{{ M.MAT_AMBIGUAS[w] }}</span>
      <span v-for="w in lectura.desconocidas" :key="w" class="teach">What is “{{ w }}”?
        <Seleccion :aria-label="`What is ${w}`" :disabled="!props.editable" @change="$event && emit('ensenar', w, $event)">
          <option value="">Choose…</option>
          <option v-for="[k, l] in M.MAT_EQUIV" :key="k" :value="k">{{ l }}</option>
        </Seleccion>
      </span>
    </div>

    <div v-if="props.editable" class="ctexto">
      <button type="button" class="resumen" :aria-expanded="verPegar" @click="verPegar = !verPegar">{{ verPegar ? '▾' : '▸' }} Paste as text</button>
      <input v-if="verPegar" v-model="pegado" class="entrada" type="text" placeholder="E.g. 60% cotton, 35% polyester, 5% elastane" @keydown.enter.prevent="pegar" @change="pegar" />
    </div>
  </div>
</template>

<style scoped>
.cparte { border: 1px solid var(--linea); border-radius: 10px; padding: 12px 14px; margin-bottom: 12px; background: var(--superficie); }
.chead { display: flex; justify-content: space-between; align-items: center; gap: 10px; margin-bottom: 8px; }
.lbl { font-size: 0.86rem; font-weight: 620; }
.req-ast { color: var(--error); font-weight: 700; margin-left: 2px; }
.opcional { font-weight: 400; color: var(--tinta-3); }
.cmat { position: relative; display: block; min-width: 0; }
.cmat input { width: 100%; padding-right: 150px; }
.ctag { position: absolute; right: 6px; top: 50%; transform: translateY(-50%); font-size: 0.7rem; font-weight: 650; padding: 2px 7px; border-radius: 999px;
  background: var(--superficie-2); color: var(--tinta-2); border: 1px solid var(--linea); pointer-events: auto; white-space: nowrap; max-width: 140px; overflow: hidden; text-overflow: ellipsis; }
.ctag.cuero { background: var(--aviso-fondo); color: var(--aviso); border-color: var(--aviso-borde); }
.ctag.textil { background: var(--info-fondo); color: var(--info-texto); border-color: transparent; }
.ctag.plastico { background: var(--acento-claro); color: var(--acento-texto); border-color: transparent; }
.ctag.desconocido { background: var(--error-fondo); color: var(--error); border-color: transparent; }
.crow { display: grid; grid-template-columns: minmax(0, 1fr) 108px 34px; gap: 8px; align-items: center; margin-bottom: 6px; }
.cpct { position: relative; display: block; }
.cpct input { padding-right: 26px; text-align: right; font-variant-numeric: tabular-nums; font-weight: 620; width: 100%; }
.cpct span { position: absolute; right: 10px; top: 50%; transform: translateY(-50%); color: var(--tinta-3); font-weight: 620; pointer-events: none; }
.cx { border: 1px solid var(--linea); background: none; border-radius: 7px; height: 36px; cursor: pointer; color: var(--tinta-3); font-size: 17px; line-height: 1; }
.cx:hover { color: var(--error); border-color: var(--error); background: var(--error-fondo); }
.cvacio { font-size: 0.84rem; color: var(--tinta-3); margin: 0 0 6px; }
.est { font-size: 0.74rem; font-weight: 620; padding: 1px 8px; border-radius: 999px; white-space: nowrap; }
.est.ok { background: var(--ok-fondo); color: var(--ok); }
.est.pend { background: var(--aviso-fondo); color: var(--aviso); }
.est.mal { background: var(--error-fondo); color: var(--error); }
.mchips { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 6px; align-items: center; }
.mlbl { font-size: 0.76rem; color: var(--tinta-3); margin-right: 2px; }
.mchips button { border: 1px dashed var(--borde-hover); background: none; border-radius: 999px; padding: 2px 10px; font-size: 0.8rem; cursor: pointer; color: var(--tinta); font-family: inherit; }
.mchips button:hover { border-color: var(--acento); color: var(--acento-texto); background: var(--acento-claro); }
.mchips button.rel, .mchips button.fix { border-style: solid; border-color: var(--acento); color: var(--acento-texto); font-weight: 600; }
.mchips button small { color: var(--tinta-3); font-weight: 400; margin-left: 5px; }
.mchips .lleno { border-style: solid; background: var(--acento); border-color: var(--acento); color: var(--sobre-acento); font-weight: 650; }
.mchips .lleno:hover { background: var(--acento-hover); color: var(--sobre-acento); }
.chips-lectura { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
.chip-l { font-size: 0.78rem; padding: 2px 9px; border-radius: 999px; border: 1px solid var(--linea); color: var(--tinta-2); }
.chip-l.main { border-color: var(--acento); color: var(--acento-texto); font-weight: 600; }
.teach { display: inline-flex; gap: 6px; align-items: center; font-size: 0.8rem; border: 1px solid var(--aviso-borde); border-radius: 8px; padding: 3px 6px; background: var(--aviso-fondo); color: var(--aviso); }
.teach select { width: auto; padding: 2px 6px; font-size: 0.8rem; }
.ctexto { margin-top: 8px; }
.ctexto .resumen { border: 1px solid var(--linea); border-radius: 7px; background: var(--superficie-2); font-size: 0.78rem; font-weight: 600; padding: 3px 10px; cursor: pointer; color: var(--tinta-2); font-family: inherit; }
.ctexto .resumen:hover { border-color: var(--acento); }
.ctexto input { margin-top: 6px; width: 100%; }
</style>
