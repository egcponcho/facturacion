<script setup>
// Las filas son el arreglo reactivo de la ficha: se editan en su lugar a propósito.
/* eslint-disable vue/no-mutating-props */
import { t, tx } from '@/i18n/index.js'
import { computed, nextTick, ref } from 'vue'
import Seleccion from '@/componentes/Seleccion.vue'
import { norm, textoDesdeFilas, totalFilas } from '@/modulos/clasificacion/formato.js'

// Composición de una parte (tela exterior, corte, suela…) por filas
// material | %. Lo que el motor lee de la parte (clase de cada material, lo
// que se deriva, palabras dudosas o desconocidas, materiales sugeridos y
// composiciones ya usadas) lo calcula el servidor: aquí solo se edita.
const props = defineProps({
  campo: { type: Object, required: true }, // campo del motor (tipo composition) con su análisis
  filas: { type: Array, required: true }, // filas que se editan
  editable: Boolean,
})
const emit = defineEmits(['cambio', 'ensenar'])
const caja = ref(null)
const pegado = ref('')
const verPegar = ref(false)

const an = computed(() => props.campo.composicion || { filas: [], lectura: [], ambiguas: [], desconocidas: [], sugerencias: [], todos: [], usadas: [], equivalencias: [] })
const r1 = (n) => Math.round(n * 10) / 10
const total = computed(() => totalFilas(props.filas))
const resto = computed(() => r1(100 - total.value))
const texto = computed(() => textoDesdeFilas(props.filas))
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
// Clase de cada fila según el servidor (cuando la fila ya llegó al motor)
function clase(f) {
  const k = norm(f.m).trim()
  return an.value.filas.find((x) => norm(x.m).trim() === k)?.clase || null
}
const usados = computed(() => new Set(props.filas.map((f) => norm(f.m).trim())))
const sugerencias = computed(() => an.value.sugerencias.filter((x) => !usados.value.has(norm(x.m).trim())))
const deUsadas = (u) => (u.de?.estilo ? t('style {0}{1}', [u.de.estilo, u.de.color ? `, ${u.de.color}` : '']) : `${u.de?.productos || ''} ${t('products')}${u.de?.marca ? t(' of {0}', [u.de.marca]) : ''}`)

function cambio() {
  emit('cambio', props.campo.codigo, texto.value)
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
// Un texto pegado o una composición ya usada: el servidor la parte en filas
function usarTexto(txt) {
  props.filas.splice(0, props.filas.length)
  emit('cambio', props.campo.codigo, txt, true)
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
      <span class="lbl">{{ tx(props.campo.etiqueta) }}<span v-if="props.campo.modo === 'REQUIRE'" class="req-ast" aria-hidden="true">*</span><span v-else class="opcional"> {{ t('(optional)') }}</span></span>
      <span v-if="props.filas.length && Math.abs(resto) < 0.05" class="est ok">{{ t('Total 100%') }}</span>
      <span v-else-if="props.filas.length && resto > 0" class="est pend">{{ t('Total {0}% · {1}% missing', [total, resto]) }}</span>
      <span v-else-if="props.filas.length" class="est mal">{{ t('Total {0}% · {1}% over', [total, -resto]) }}</span>
    </div>

    <div v-for="(f, i) in props.filas" :key="i" class="crow">
      <span class="cmat">
        <input v-model="f.m" class="entrada" type="text" :list="`mat_${props.campo.codigo}`" :data-mat="i" :placeholder="t('Material')" :aria-label="t('Material {0}', [i + 1])"
               :disabled="!props.editable" @input="cambio" @keydown.enter.prevent="enfocar(i, 'pct')" />
        <span v-if="f.m && clase(f)" class="ctag" :class="clase(f).clase" :title="t('Counts as {0} for the tariff', [tx(clase(f).lbl).toLowerCase()])">{{ tx(clase(f).lbl) }}</span>
        <span v-else-if="f.m && f.m.trim().length > 2 && an.desconocidas.some((w) => norm(f.m).includes(w))" class="ctag desconocido" :title="t('Not recognized: choose what it is below so the system learns it')">?</span>
      </span>
      <span class="cpct">
        <input class="entrada" type="text" inputmode="decimal" :value="f.pct" :data-pct="i" :placeholder="tx(placeholders[i])" :aria-label="t('Percentage of {0}', [f.m || 'material'])"
               :disabled="!props.editable" @input="escribirPct(i, $event)" @keydown.enter.prevent="enterPct(i)" /><span>%</span>
      </span>
      <button v-if="props.editable" type="button" class="cx" :aria-label="t('Remove {0}', [f.m || 'row'])" @click="quitar(i)">×</button>
    </div>
    <p v-if="!props.filas.length" class="cvacio">{{ tx(props.editable ? t('Tap a material to add it.') : t('Not given.')) }}</p>
    <datalist :id="`mat_${props.campo.codigo}`"><option v-for="m in an.todos" :key="m" :value="m"></option></datalist>

    <template v-if="props.editable">
      <div v-if="soloUno || faltaUltimo" class="mchips">
        <button type="button" class="lleno" @click="llenar">{{ tx(soloUno ? `100% ${props.filas[0].m}` : t('Complete {0} with {1}%', [props.filas.at(-1).m || 'last', resto])) }}</button>
      </div>
      <div v-if="resto > 0 || !props.filas.length" class="mchips">
        <button v-for="x in sugerencias" :key="x.m" type="button" :class="{ rel: x.fuente === 'rel' }"
                :title="tx(x.fuente === 'rel' ? t('Mentioned in the product name') : x.fuente === 'base' ? t('What you use most for this category') : t('Common for this product'))"
                @click="agregar(x.m)">+ {{ tx(x.m) }}</button>
        <button type="button" @click="agregar('')">{{ t('+ Other') }}</button>
      </div>
      <div v-if="an.usadas.length && !props.filas.length" class="mchips">
        <span class="mlbl">{{ t('Already used:') }}</span>
        <button v-for="u in an.usadas" :key="u.txt" type="button" class="fix" @click="usarTexto(u.txt)">{{ tx(u.txt) }}<small>{{ tx(deUsadas(u)) }}</small></button>
      </div>
    </template>

    <div v-if="an.lectura.length || an.ambiguas.length || an.desconocidas.length" class="chips-lectura">
      <span v-for="x in an.lectura" :key="x.campo" class="chip-l main">{{ tx(x.etiqueta) }}: {{ tx(x.texto) }}<template v-if="x.pct"> ({{ tx(x.pct) }}%)</template></span>
      <span v-for="w in an.ambiguas" :key="w.palabra" class="chip-l">{{ tx(w.texto) }}</span>
      <span v-for="w in an.desconocidas" :key="w" class="teach">{{ t('What is “{0}”?', [w]) }}
        <Seleccion :aria-label="t('What is {0}', [w])" :disabled="!props.editable" @change="$event && emit('ensenar', w, $event)">
          <option value="">{{ t('Choose…') }}</option>
          <option v-for="e in an.equivalencias" :key="e.codigo" :value="e.codigo">{{ tx(e.etiqueta) }}</option>
        </Seleccion>
      </span>
    </div>

    <div v-if="props.editable" class="ctexto">
      <button type="button" class="resumen" :aria-expanded="verPegar" @click="verPegar = !verPegar">{{ t('{0} Paste as text', [verPegar ? '▾' : '▸']) }}</button>
      <input v-if="verPegar" v-model="pegado" class="entrada" type="text" :placeholder="t('E.g. 60% cotton, 35% polyester, 5% elastane')" @keydown.enter.prevent="pegar" @change="pegar" />
    </div>
  </div>
</template>

<style scoped>
.cparte { border: 1px solid var(--linea); border-radius: 10px; padding: 12px 14px; margin-bottom: 12px; background: var(--superficie); }
.chead { display: flex; justify-content: space-between; align-items: center; gap: 10px; margin-bottom: 8px; }
.lbl { font-size: 0.86rem; font-weight: 620; }
.req-ast { color: var(--error); font-weight: 700; margin-inline-start: 2px; }
.opcional { font-weight: 400; color: var(--tinta-3); }
.cmat { position: relative; display: block; min-width: 0; }
.cmat input { width: 100%; padding-inline-end: 150px; }
.ctag { position: absolute; inset-inline-end: 6px; top: 50%; transform: translateY(-50%); font-size: 0.7rem; font-weight: 650; padding: 2px 7px; border-radius: 999px;
  background: var(--superficie-2); color: var(--tinta-2); border: 1px solid var(--linea); pointer-events: auto; white-space: nowrap; max-width: 140px; overflow: hidden; text-overflow: ellipsis; }
.ctag.cuero { background: var(--aviso-fondo); color: var(--aviso); border-color: var(--aviso-borde); }
.ctag.textil { background: var(--info-fondo); color: var(--info-texto); border-color: transparent; }
.ctag.plastico { background: var(--acento-claro); color: var(--acento-texto); border-color: transparent; }
.ctag.desconocido { background: var(--error-fondo); color: var(--error); border-color: transparent; }
.crow { display: grid; grid-template-columns: minmax(0, 1fr) 108px 34px; gap: 8px; align-items: center; margin-bottom: 6px; }
.cpct { position: relative; display: block; }
.cpct input { padding-inline-end: 26px; text-align: end; font-variant-numeric: tabular-nums; font-weight: 620; width: 100%; }
.cpct span { position: absolute; inset-inline-end: 10px; top: 50%; transform: translateY(-50%); color: var(--tinta-3); font-weight: 620; pointer-events: none; }
.cx { border: 1px solid var(--linea); background: none; border-radius: 7px; height: 36px; cursor: pointer; color: var(--tinta-3); font-size: 17px; line-height: 1; }
.cx:hover { color: var(--error); border-color: var(--error); background: var(--error-fondo); }
.cvacio { font-size: 0.84rem; color: var(--tinta-3); margin: 0 0 6px; }
.est { font-size: 0.74rem; font-weight: 620; padding: 1px 8px; border-radius: 999px; white-space: nowrap; }
.est.ok { background: var(--ok-fondo); color: var(--ok); }
.est.pend { background: var(--aviso-fondo); color: var(--aviso); }
.est.mal { background: var(--error-fondo); color: var(--error); }
.mchips { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 6px; align-items: center; }
.mlbl { font-size: 0.76rem; color: var(--tinta-3); margin-inline-end: 2px; }
.mchips button { border: 1px dashed var(--borde-hover); background: none; border-radius: 999px; padding: 2px 10px; font-size: 0.8rem; cursor: pointer; color: var(--tinta); font-family: inherit; }
.mchips button:hover { border-color: var(--acento); color: var(--acento-texto); background: var(--acento-claro); }
.mchips button.rel, .mchips button.fix { border-style: solid; border-color: var(--acento); color: var(--acento-texto); font-weight: 600; }
.mchips button small { color: var(--tinta-3); font-weight: 400; margin-inline-start: 5px; }
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
