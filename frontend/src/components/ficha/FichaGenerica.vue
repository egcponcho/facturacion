<script setup>
import { t, tx } from '../../i18n/index.js'
import { computed, onMounted, ref, watch } from 'vue'
import { api } from '../../api'
import { M } from '../../clasificacion/useClasificacion'
import FiltroMulti from '../FiltroMulti.vue'
import Icono from '../Icono.vue'

// Ficha genérica (químicos, materias primas y lo que no está en la lista):
// las preguntas salen del catálogo de atributos (Aranceles → Atributos) según
// el dominio y los capítulos de los candidatos, y los candidatos salen del
// texto oficial del árbol arancelario. El dominio ordena, no obliga; el
// resultado es una sugerencia que revisa el especialista.
const props = defineProps({ f: { type: Object, required: true }, ctx: { type: Object, required: true }, editable: Boolean })
const f = props.f
if (!f.gen) f.gen = {}

const res = ref(null)
const cargando = ref(false)
const dominios = computed(() => props.ctx.dominios_genericos || [])
const TIPO_INPUT = { number: 'number', text: 'text', composition: 'text', measurement_set: 'text', country: 'text' }

const texto = computed(() => [f.descArchivo, f.uso, f.gen.product_name, f.gen.commercial_description, f.gen.technical_description,
  f.gen.chemical_name, f.gen.primary_function, f.gen.chemical_function, f.gen.intended_use].filter(Boolean).join(' '))

let espera = null
function buscar() {
  clearTimeout(espera)
  espera = setTimeout(async () => {
    cargando.value = true
    try {
      // Motor único del servidor: candidatos, preguntas discriminantes y reglas aplicadas
      const r = await api.post('/clasificacion/sesion', { texto: texto.value, dominio: f.dominio || null, categoria: f.categoria || null, respuestas: f.gen, paises: false })
      res.value = r
      if (props.editable) {
        // Evidencia guardada con la ficha: candidatos, obligatorios y confianza
        f.genCand = r.candidatos.map((c) => ({ codigo: c.codigo, descripcion: c.descripcion, terminos: c.terminos, puntaje: c.puntaje, origen: c.origen }))
        f.genReglas = r.reglas.filter((x) => x.resultado === true && !String(x.efecto).startsWith('BUILTIN')).map((x) => x.regla)
        // Si una regla dejó un solo candidato, el motor lo propone; la persona puede cambiarlo
        if (r.confianza === 'high' && r.hs6 && !f.codigoGen) f.codigoGen = r.hs6
        f.genReq = r.preguntas.filter((p) => p.modo === 'REQUIRE').map((p) => p.codigo)
        f.genConf = r.confianza
      }
    } catch {
      res.value = null
    } finally {
      cargando.value = false
    }
  }, 350)
}
onMounted(buscar)
watch([texto, () => f.dominio, () => f.categoria, () => JSON.stringify(f.gen)], buscar)

function poner(k, v) {
  f.gen = { ...f.gen, [k]: v }
  if (v === '' || v === null || (Array.isArray(v) && !v.length)) delete f.gen[k]
}
// Una subpartida con un solo inciso toma el inciso (así los países con el SAC
// a 10 dígitos reciben su código completo)
// El producto guarda el HS6; la línea SAC regional se elige aparte (opcional)
// y cada país elige su línea nacional por su cuenta
function elegir(c) {
  f.codigoGen = c.codigo
  f.sacGen = c.incisos.length === 1 ? c.incisos[0].codigo : ''
}
function elegirSac(c, x) {
  f.codigoGen = c.codigo
  f.sacGen = x.codigo
}
const traza = computed(() => (res.value?.reglas || []).filter((x) => !String(x.efecto).startsWith('BUILTIN') && x.resultado !== false))
const preguntas = computed(() => (res.value?.preguntas || []).filter((p) => p.codigo !== 'destination_country'))
const pendientes = computed(() => preguntas.value.filter((p) => !p.respondida).length)
const opciones = (p) => (p.opciones || []).filter((o) => o.activo)
</script>

<template>
  <div class="ficha-gen">
    <fieldset class="fs" :disabled="!props.editable">
      <legend>{{ t('Kind of product') }}</legend>
      <p class="hint">{{ t('The domain only orders the questions and candidates; it never forces or excludes a chapter.') }}</p>
      <div class="segs dominios" role="radiogroup" :aria-label="t('Kind of product')">
        <button v-for="d in dominios" :key="d.codigo" type="button" role="radio" :aria-checked="f.dominio === d.codigo" :title="tx(d.descripcion || '')"
                @click="f.dominio = d.codigo">{{ tx(d.nombre) }}</button>
        <button type="button" role="radio" :aria-checked="!f.dominio" @click="f.dominio = ''">{{ t('Other') }}</button>
      </div>
    </fieldset>

    <fieldset class="fs" :disabled="!props.editable">
      <legend>{{ t('Technical data') }} <span v-if="pendientes" class="cuenta">{{ t('{0} to answer', [pendientes]) }}</span></legend>
      <p class="hint">{{ t('Only what can distinguish the candidates or is mandatory is asked. Describe the product in Spanish, like the tariff text, for better candidates.') }}</p>
      <div class="rejilla-gen">
        <div v-for="p in preguntas" :key="p.codigo" class="campo-f" :class="{ ancho: ['text', 'composition'].includes(p.tipo_dato) && /description|function|use/.test(p.codigo) }">
          <label :for="`g_${p.codigo}`">{{ tx(p.etiqueta) }}<span v-if="p.modo === 'REQUIRE'" class="req-ast">*</span><span v-if="p.discrimina && !p.respondida" class="etiqueta acento disc">{{ t('decides the code') }}</span><span v-if="p.unidad" class="opcional"> ({{ tx(p.unidad) }})</span></label>
          <div v-if="p.tipo_dato === 'select' && opciones(p).length <= 6" class="segs" role="radiogroup" :aria-label="tx(p.etiqueta)">
            <button v-for="o in opciones(p)" :key="o.codigo" type="button" role="radio" :aria-checked="f.gen[p.codigo] === o.codigo"
                    @click="poner(p.codigo, f.gen[p.codigo] === o.codigo ? '' : o.codigo)">{{ tx(o.etiqueta) }}</button>
          </div>
          <select v-else-if="p.tipo_dato === 'select'" :id="`g_${p.codigo}`" class="entrada" :value="f.gen[p.codigo] || ''" @change="poner(p.codigo, $event.target.value)">
            <option value="">{{ t('Choose…') }}</option>
            <option v-for="o in opciones(p)" :key="o.codigo" :value="o.codigo">{{ tx(o.etiqueta) }}</option>
          </select>
          <FiltroMulti v-else-if="p.tipo_dato === 'multi_select'" :model-value="f.gen[p.codigo] || []" :etiqueta="tx(p.etiqueta)" vacio="—"
                       :opciones="opciones(p).map((o) => ({ valor: o.codigo, texto: o.etiqueta }))" @update:model-value="(v) => poner(p.codigo, v)" />
          <label v-else-if="p.tipo_dato === 'boolean'" class="check-f"><input type="checkbox" :checked="!!f.gen[p.codigo]" @change="poner(p.codigo, $event.target.checked || '')" /><span>{{ t('Yes') }}</span></label>
          <textarea v-else-if="/description/.test(p.codigo)" :id="`g_${p.codigo}`" class="entrada" rows="2" maxlength="600" :value="f.gen[p.codigo] || ''"
                    @input="poner(p.codigo, $event.target.value)"></textarea>
          <input v-else :id="`g_${p.codigo}`" class="entrada" :type="TIPO_INPUT[p.tipo_dato] || 'text'" :step="p.tipo_dato === 'number' ? 'any' : undefined"
                 :value="f.gen[p.codigo] ?? ''" maxlength="200"
                 @input="poner(p.codigo, p.tipo_dato === 'number' ? ($event.target.value === '' ? '' : Number($event.target.value)) : $event.target.value)" />
          <small v-if="p.nota_ambito" class="hint">{{ tx(p.nota_ambito) }}</small>
        </div>
      </div>
    </fieldset>

    <fieldset class="fs">
      <legend>{{ t('Candidates from the official tariff') }} <span v-if="cargando" class="ayuda">…</span></legend>
      <p v-if="!res?.candidatos?.length" class="hint">{{ t('Write the name or technical description to see candidates. Only chapters enabled for classification are searched.') }}</p>
      <ul v-else class="cands">
        <li v-for="(c, i) in res.candidatos" :key="c.codigo" :class="{ elegido: (f.codigoGen || '').startsWith(c.codigo) }">
          <div class="cand-cab">
            <span class="codigo-sac">{{ tx(c.codigo_txt) }}</span>
            <span class="cand-txt">{{ tx(c.descripcion.split(' — ').slice(-1)[0]) }}<small>{{ t('Chapter {0} · {1}', [c.capitulo, c.titulo_capitulo]) }}</small></span>
            <span v-if="i === 0" class="etiqueta acento">{{ t('Best match') }}</span>
            <span v-if="c.dominio" class="etiqueta" :title="t('Chapter related to the chosen domain')">{{ t('domain') }}</span>
            <span v-if="c.origen?.some((o) => o.startsWith('regla:'))" class="etiqueta ok" :title="tx(c.origen.join(', '))">{{ t('by rule') }}</span>
            <button v-if="props.editable" type="button" class="btn btn-chico" @click="elegir(c)">{{ t('Use') }}</button>
          </div>
          <p class="hint">{{ t('Matches: {0}', [c.terminos.join(', ')]) }}</p>
          <ul v-if="c.incisos.length" class="incisos">
            <li v-for="x in c.incisos" :key="x.codigo">
              <button v-if="props.editable" type="button" class="enlace" :class="{ fuerte: f.sacGen === x.codigo }" @click="elegirSac(c, x)">{{ tx(x.codigo_txt) }}</button>
              <span v-else class="codigo">{{ tx(x.codigo_txt) }}</span>
              {{ tx(x.descripcion) }}<span v-if="x.dai != null" class="ayuda"> · {{ t('DAI {0}%', [x.dai]) }}</span>
            </li>
          </ul>
        </li>
      </ul>
      <p v-if="f.codigoGen" class="elegido-txt"><Icono nombre="check" :tam="15" />{{ t('Suggested HS6: {0}. A specialist confirms it.', [M.fmtCode(f.codigoGen)]) }}
        <span v-if="f.sacGen" class="ayuda">{{ t('SAC line {0}', [M.fmtCode(f.sacGen)]) }}</span>
        <button v-if="props.editable" type="button" class="btn-texto" @click="f.codigoGen = ''; f.sacGen = ''">{{ t('Clear') }}</button></p>
      <div v-if="traza.length" class="traza">
        <b>{{ t('Rules that acted') }}</b>
        <ul><li v-for="x in traza" :key="x.regla"><span class="codigo">{{ tx(x.regla) }}</span>
          <template v-if="x.resultado === null"> · {{ t('waiting for: {0}', [x.faltan.join(', ')]) }}</template>
          <template v-else> · {{ tx(x.efecto) }}<template v-if="x.codigos?.length"> {{ tx(x.codigos.map(M.fmtCode).join(', ')) }}</template><template v-if="x.mensaje"> — {{ tx(x.mensaje) }}</template></template></li></ul>
      </div>
    </fieldset>
  </div>
</template>

<style scoped>
/* Mismo estilo que la ficha (FichaTecnica tiene sus estilos con alcance propio) */
.req-ast { color: var(--error); font-weight: 700; margin-inline-start: 2px; }
.opcional { font-weight: 400; color: var(--tinta-3); }
.campo-f { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
.campo-f label { font-size: 0.84rem; font-weight: 620; color: var(--tinta); }
.campo-f .hint { white-space: normal; font-size: 0.76rem; }
.hint { margin: 0 0 8px; font-size: 0.8rem; color: var(--tinta-3); }
.fs { border: 0; border-top: 1px solid var(--linea-suave); margin: 4px 0 0; padding: 12px 0 6px; min-width: 0; }
.fs:first-of-type { border-top: 0; padding-top: 0; }
legend { font-size: 0.84rem; font-weight: 650; color: var(--tinta-3); padding: 0 8px 0 0; text-transform: uppercase; letter-spacing: 0.04em; }
legend .cuenta { text-transform: none; letter-spacing: 0; font-weight: 500; }
.segs { display: flex; flex-wrap: wrap; gap: 6px; }
.segs button { padding: 6px 12px; font-size: 0.88rem; border: 1px solid var(--linea); border-radius: 7px; background: var(--superficie-2); color: var(--tinta); cursor: pointer; font-family: inherit; }
.segs button:hover:not(:disabled) { border-color: var(--acento); }
.segs button[aria-checked='true'] { background: var(--acento-claro); border-color: var(--acento); color: var(--acento-texto); font-weight: 620; }
.check-f { display: flex; gap: 8px; align-items: center; font-size: 0.9rem; cursor: pointer; }
.check-f input { accent-color: var(--acento); }
.ficha-gen { display: grid; gap: 4px; }
.disc { margin-inline-start: 6px; font-size: 0.7rem; }
.dominios { flex-wrap: wrap; }
.rejilla-gen { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 12px 16px; }
.rejilla-gen .ancho { grid-column: 1 / -1; }
.cands { list-style: none; margin: 0; padding: 0; display: grid; gap: 8px; }
.cands > li { border: 1px solid var(--linea); border-radius: var(--radio); padding: 8px 10px; }
.cands > li.elegido { border-color: var(--acento-medio); background: var(--acento-claro); }
.cand-cab { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.cand-txt { flex: 1; min-width: 180px; }
.cand-txt small { display: block; color: var(--tinta-3); }
.incisos { margin: 4px 0 0; padding-inline-start: 18px; font-size: 0.86rem; }
.traza { margin-top: 10px; font-size: 0.84rem; }
.traza ul { margin: 4px 0 0; padding-inline-start: 18px; }
.elegido-txt { display: flex; gap: 6px; align-items: center; margin-top: 8px; font-weight: 600; }
</style>
