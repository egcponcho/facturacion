<script setup>
import { t, tx } from '@/i18n/index.js'
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { api } from '@/nucleo/api'
import Icono from '@/componentes/Icono.vue'
import Modal from '@/componentes/Modal.vue'
import SelectBusqueda from '@/componentes/SelectBusqueda.vue'
import Seleccion from '@/componentes/Seleccion.vue'
import TablaDatos from '@/componentes/TablaDatos.vue'
import { puede } from '@/stores/sesion'
import { avisar, errorApi } from '@/stores/ui'
import { AMBITOS, LISTAS, MODALIDADES, NUMERICOS, OPERADORES, ORIGENES, SIN_VALOR, UNIDADES, textoModalidad } from '@/modulos/etiquetado/etiquetas.js'
import { buscarArticulos, buscarOrdenes, buscarProductos } from '@/modulos/etiquetado/componentes/buscadores.js'

// Reglas de etiquetado: qué diseño se usa para qué registros. Cada regla tiene
// prioridad (gana la mayor), destino opcional (familia y sus subfamilias,
// producto, artículo, OC), condiciones sobre los datos, contexto del trabajo y
// vigencia. Con la misma prioridad y diseños distintos es un conflicto: no se
// elige al azar. El probador explica, regla por regla, qué se elegiría.
const lista = ref([])
const plantillas = ref([])
const familias = ref([])
const conflictos = ref([])
const cargando = ref(false)
const soloActivas = ref(true)
const editable = computed(() => puede('etiquetas.asignar'))
const catalogos = reactive({}) // modalidad → campos

async function cargar() {
  cargando.value = true
  try {
    lista.value = await api.get('/etiquetas/asignaciones', { activas: soloActivas.value ? true : undefined })
    conflictos.value = await api.get('/etiquetas/reglas/conflictos')
  } catch (e) {
    errorApi(e)
  } finally {
    cargando.value = false
  }
}
async function campos(modalidad) {
  if (!catalogos[modalidad]) catalogos[modalidad] = (await api.get('/etiquetas/campos', { modalidad })).campos
  return catalogos[modalidad]
}
onMounted(() => {
  cargar()
  api.get('/etiquetas/plantillas', { size: 200 }).then((r) => (plantillas.value = r.items)).catch(() => {})
  api.get('/etiquetas/familias').then((r) => (familias.value = r)).catch(() => {})
})
watch(soloActivas, cargar)

const resumenCondicion = (c) => `${c.campo} ${tx(OPERADORES()[c.op] || c.op)}${SIN_VALOR.includes(c.op) ? ''
  : ` ${Array.isArray(c.valor) ? c.valor.join(c.op === 'entre' ? '–' : ', ') : c.valor}`}`
const resumenContexto = (x) => Object.entries(x || {}).map(([k, v]) => `${k}: ${v.join(', ')}`).join(' · ')
const enConflicto = computed(() => new Set(conflictos.value.filter((c) => c.nivel === 'error').flatMap((c) => c.reglas.map((r) => r.id))))
const columnas = computed(() => [
  { clave: 'prioridad', texto: t('Priority'), prioridad: 1 },
  { clave: 'nombre', texto: t('Rule'), fija: true, prioridad: 1 },
  { clave: 'plantilla', texto: t('Design'), prioridad: 1 },
  { clave: 'modalidad', texto: t('Data'), prioridad: 3, textoValor: (v) => tx(textoModalidad(v)) },
  { clave: 'destino', texto: t('Applies to'), prioridad: 2 },
  { clave: 'condiciones', texto: t('Conditions'), prioridad: 2, textoValor: (v) => (v || []).map(resumenCondicion).join('; ') },
  { clave: 'vigente', texto: t('Validity'), prioridad: 3 },
  { clave: 'version_vigente', texto: t('Version in use'), prioridad: 3 },
  { clave: 'predeterminada', texto: t('Default'), prioridad: 3, opciones: [[true, t('Yes')], [false, t('No')]] },
])

// ---- Alta y edición -----------------------------------------------------------------------------
const edicion = ref(null)
const plantillaEdicion = computed(() => plantillas.value.find((p) => p.id === Number(edicion.value?.plantilla_id)))
const camposEdicion = ref([])
watch(() => plantillaEdicion.value?.modalidad, async (m) => (camposEdicion.value = m ? await campos(m) : []))
const ambitosValidos = computed(() => {
  const m = plantillaEdicion.value?.modalidad
  if (!m) return []
  return Object.keys(AMBITOS()).filter((a) => ['GENERAL', 'REGLA'].includes(a) || (a === 'OC' ? m !== 'ARTICULO' : m !== 'OC'))
})
const SUGERIDA = { OC: 500, ARTICULO: 400, PRODUCTO: 300, REGLA: 250, FAMILIA: 200, GENERAL: 100 }
function abrir(r) {
  edicion.value = r
    ? { ...r, condiciones: (r.condiciones || []).map((c) => ({ ...c, valor: Array.isArray(c.valor) && c.op !== 'entre' ? c.valor.join(', ') : c.valor })),
        contexto: { origenes: [], unidades: [], ...r.contexto, tipos_empaque: (r.contexto?.tipos_empaque || []).join(', ') } }
    : { plantilla_id: '', ambito: 'REGLA', nombre: '', prioridad: '', familia_id: '', producto_id: '', articulo_id: '', oc_id: '', condiciones: [],
        contexto: { origenes: [], unidades: [], tipos_empaque: '' }, vigente_desde: '', vigente_hasta: '', predeterminada: false, motivo: '' }
}
const agregarCondicion = () => edicion.value.condiciones.push({ campo: '', op: 'igual', valor: '' })
function cuerpo() {
  const e = edicion.value
  const condiciones = e.condiciones.filter((c) => c.campo).map((c) => {
    let valor = c.valor
    if (SIN_VALOR.includes(c.op)) valor = null
    else if (LISTAS.includes(c.op)) valor = String(valor || '').split(',').map((x) => x.trim()).filter(Boolean)
    else if (c.op === 'entre') valor = [Number(c.valor?.[0]), Number(c.valor?.[1])]
    else if (NUMERICOS.includes(c.op)) valor = Number(valor)
    return { campo: c.campo, op: c.op, valor }
  })
  const contexto = { origenes: e.contexto.origenes, unidades: e.contexto.unidades,
    tipos_empaque: String(e.contexto.tipos_empaque || '').split(',').map((x) => x.trim()).filter(Boolean) }
  const res = { nombre: e.nombre || null, prioridad: e.prioridad === '' ? undefined : Number(e.prioridad), condiciones, contexto,
    vigente_desde: e.vigente_desde || null, vigente_hasta: e.vigente_hasta || null, predeterminada: e.predeterminada, motivo: e.motivo || null }
  if (!e.id) {
    Object.assign(res, { plantilla_id: Number(e.plantilla_id), ambito: e.ambito })
    const col = { FAMILIA: 'familia_id', PRODUCTO: 'producto_id', ARTICULO: 'articulo_id', OC: 'oc_id' }[e.ambito]
    if (col) res[col] = Number(e[col])
  } else res.version = e.version
  return res
}
async function guardar() {
  const e = edicion.value
  try {
    const r = e.id ? await api.patch(`/etiquetas/asignaciones/${e.id}`, cuerpo()) : await api.post('/etiquetas/asignaciones', cuerpo())
    const graves = (r.conflictos || []).filter((c) => c.nivel === 'error')
    avisar(graves.length ? t('Rule saved, but it is in conflict with {0} other rule(s): check the conflicts.', [graves.length]) : t('Rule saved.'),
      graves.length ? 'aviso' : undefined)
    edicion.value = null
    cargar()
  } catch (err) {
    errorApi(err)
    if (err.status === 409) cargar()
  }
}
async function cambiar(a, datos) {
  try {
    await api.patch(`/etiquetas/asignaciones/${a.id}`, { ...datos, version: a.version })
    cargar()
  } catch (e) {
    errorApi(e)
  }
}
async function quitar(a) {
  try {
    await api.del(`/etiquetas/asignaciones/${a.id}`)
    avisar(t('Rule removed; the design and generated labels did not change.'))
    cargar()
  } catch (e) {
    errorApi(e)
  }
}

// ---- Probar -----------------------------------------------------------------------------------------
const prueba = reactive({ modalidad: 'OC_ARTICULO', oc_id: '', posicion_id: '', articulo_id: '', fecha: '', valores: '', borrador: false })
const lineasOc = ref([])
watch(() => prueba.oc_id, async (id) => {
  prueba.posicion_id = ''
  lineasOc.value = id ? (await api.get(`/etiquetas/oc/${id}`).catch(() => ({ lineas: [] }))).lineas : []
})
const resultado = ref(null)
async function probar() {
  const valores = {}
  for (const linea of prueba.valores.split('\n')) {
    const [k, ...v] = linea.split('=')
    if (k.trim()) valores[k.trim()] = v.join('=').trim()
  }
  try {
    resultado.value = await api.post('/etiquetas/reglas/probar', {
      modalidad: prueba.modalidad, oc_id: prueba.oc_id || undefined, posicion_id: prueba.posicion_id || undefined,
      articulo_id: prueba.articulo_id || undefined, fecha: prueba.fecha || undefined, valores,
      regla: prueba.borrador && edicion.value?.plantilla_id && !edicion.value.id ? cuerpo() : undefined })
  } catch (e) {
    errorApi(e)
  }
}
const RESULTADOS = () => ({ aplica: t('Applies'), inactiva: t('Inactive'), otra_modalidad: t('Other data mode'), fuera_de_vigencia: t('Out of its validity'),
  destino_distinto: t('Other target'), contexto_distinto: t('Other context'), condiciones: t('Conditions not met') })
</script>

<template>
  <div class="dos-columnas-asig">
    <div>
      <div v-if="conflictos.length" class="aviso-conflictos" role="status">
        <h3><Icono nombre="alerta" :tam="16" /> {{ t('{0} possible conflicts between rules', [conflictos.length]) }}</h3>
        <ul>
          <li v-for="(c, i) in conflictos" :key="i" :class="c.nivel">
            <b>{{ c.reglas.map((r) => `${r.nombre} → ${r.plantilla}`).join('  ×  ') }}</b> · {{ t('priority {0}', [c.prioridad]) }} — {{ tx(c.mensaje) }}
          </li>
        </ul>
      </div>
      <TablaDatos tabla="etiquetas_reglas" :columnas="columnas" :filas="lista" :cargando="cargando" :etiqueta="t('Rules')" orden-inicial="-prioridad"
                  :clase-fila="(x) => ({ apagada: !x.activa, conflicto: enConflicto.has(x.id) })">
        <template #filtros>
          <label class="check"><input v-model="soloActivas" type="checkbox" /> {{ t('Only active') }}</label>
          <button v-if="editable" type="button" class="btn btn-primario separar" @click="abrir(null)"><Icono nombre="mas" />{{ t('New rule') }}</button>
        </template>
        <template #celda-nombre="{ fila: a }">
          <button v-if="editable" type="button" class="btn-texto" @click="abrir(a)">{{ tx(a.nombre) }}</button><span v-else>{{ tx(a.nombre) }}</span>
          <span v-if="enConflicto.has(a.id)" class="etiqueta error">{{ t('Conflict') }}</span>
        </template>
        <template #celda-plantilla="{ fila: a }"><router-link :to="`/etiquetas/plantillas/${a.plantilla_id}`" class="enlace">{{ tx(a.plantilla) }}</router-link></template>
        <template #celda-destino="{ fila: a }">{{ ['GENERAL', 'REGLA'].includes(a.ambito) ? tx(AMBITOS()[a.ambito]) : `${tx(AMBITOS()[a.ambito])}: ${tx(a.destino || '—')}` }}</template>
        <template #celda-condiciones="{ fila: a }">
          <span v-for="(c, i) in a.condiciones" :key="i" class="cond">{{ resumenCondicion(c) }}</span>
          <span v-if="Object.keys(a.contexto || {}).length" class="cond ctx">{{ resumenContexto(a.contexto) }}</span>
          <span v-if="!a.condiciones.length && !Object.keys(a.contexto || {}).length" class="ayuda">—</span>
        </template>
        <template #celda-vigente="{ fila: a }">
          <span v-if="a.vigente_desde || a.vigente_hasta" :class="{ 'aviso-txt': !a.vigente }">{{ a.vigente_desde || '…' }} → {{ a.vigente_hasta || '…' }}</span>
          <span v-else class="ayuda">{{ t('Always') }}</span>
        </template>
        <template #celda-version_vigente="{ fila: a }">
          <span v-if="a.version_vigente" class="etiqueta ok ms-0">v{{ a.version_vigente }}</span>
          <span v-else class="etiqueta aviso ms-0">{{ t('Not approved: it is skipped') }}</span>
        </template>
        <template #celda-predeterminada="{ fila: a }">
          <label v-if="editable" class="check"><input type="checkbox" :checked="a.predeterminada" :aria-label="t('Default')" @change="cambiar(a, { predeterminada: $event.target.checked })" /></label>
          <span v-else>{{ a.predeterminada ? t('Yes') : '—' }}</span>
        </template>
        <template #acciones="{ fila: a }">
          <template v-if="editable">
            <button type="button" class="btn btn-chico" @click="cambiar(a, { activa: !a.activa })">{{ a.activa ? t('Deactivate') : t('Activate') }}</button>
            <button type="button" class="btn-icono" :aria-label="t('Remove')" :title="t('Remove')" @click="quitar(a)"><Icono nombre="basura" :tam="15" /></button>
          </template>
        </template>
        <template #vacio>{{ t('There are no rules yet. A rule says which design is used for which records.') }}</template>
      </TablaDatos>
    </div>

    <aside class="panel">
      <div class="panel-cabeza"><div><h2>{{ t('Test the rules') }}</h2>
        <p>{{ t('With a real record or sample values: which design would be used and why, rule by rule.') }}</p></div></div>
      <form class="formulario-asig" @submit.prevent="probar">
        <label class="campo"><span>{{ t('Data') }}</span>
          <Seleccion v-model="prueba.modalidad"><option v-for="[v, txt] in MODALIDADES()" :key="v" :value="v">{{ tx(txt) }}</option></Seleccion></label>
        <label v-if="prueba.modalidad !== 'ARTICULO'" class="campo"><span>{{ t('Purchase order') }}</span>
          <SelectBusqueda v-model="prueba.oc_id" :buscar="buscarOrdenes" :etiqueta="t('Purchase order')" :prefijo="false" :vacio="t('None')" /></label>
        <label v-if="prueba.modalidad === 'OC_ARTICULO' && lineasOc.length" class="campo"><span>{{ t('PO line') }}</span>
          <Seleccion v-model="prueba.posicion_id"><option value="">{{ t('None') }}</option>
            <option v-for="l in lineasOc" :key="l.id" :value="l.id">{{ l.posicion }} · {{ l.codigo }}</option></Seleccion></label>
        <label v-if="prueba.modalidad !== 'OC' && !prueba.posicion_id" class="campo"><span>{{ t('Item') }}</span>
          <SelectBusqueda v-model="prueba.articulo_id" :buscar="buscarArticulos" :etiqueta="t('Item')" :prefijo="false" :vacio="t('None')" /></label>
        <label class="campo"><span>{{ t('Date') }}</span><input v-model="prueba.fecha" type="date" /></label>
        <label class="campo"><span>{{ t('Sample values (one field=value per line)') }}</span>
          <textarea v-model="prueba.valores" rows="3" placeholder="linea.cantidad=24" spellcheck="false"></textarea></label>
        <label v-if="edicion && !edicion.id && edicion.plantilla_id" class="check"><input v-model="prueba.borrador" type="checkbox" /> {{ t('Include the rule being created') }}</label>
        <button type="submit" class="btn">{{ t('Test') }}</button>
      </form>
      <div v-if="resultado" class="resultado-asig mt">
        <template v-if="resultado.plantilla">
          <strong>{{ tx(resultado.plantilla) }}</strong> <span class="etiqueta ok">v{{ resultado.version }}</span>
          <p class="ayuda">{{ tx(resultado.motivo) }}</p>
        </template>
        <p v-else-if="resultado.ambigua" class="nota">{{ tx(resultado.motivo) }} {{ resultado.candidatas.map((c) => c.plantilla).join(', ') }}</p>
        <p v-else class="nota">{{ t('No approved design applies.') }}</p>
        <p v-for="a in resultado.avisos" :key="a" class="ayuda aviso-txt">{{ tx(a) }}</p>
        <ol class="explicacion">
          <li v-for="e in resultado.explicacion" :key="`${e.regla_id}-${e.regla}`" :class="{ elegida: e.elegida, aplica: e.resultado === 'aplica' }">
            <div><b>{{ tx(e.regla) }}</b> · {{ e.prioridad }} → {{ tx(e.plantilla) }}
              <span class="etiqueta" :class="e.resultado === 'aplica' ? (e.elegida ? 'ok' : 'info') : ''">{{ e.elegida ? t('Chosen') : tx(RESULTADOS()[e.resultado]) }}</span>
              <span v-if="e.resultado === 'aplica' && !e.aprobada" class="etiqueta aviso">{{ t('Not approved') }}</span></div>
            <ul v-if="e.detalle.length">
              <li v-for="(d, i) in e.detalle" :key="i" :class="d.cumple ? 'ok-txt' : 'aviso-txt'">
                <Icono :nombre="d.cumple ? 'check' : 'cerrar'" :tam="12" />
                <template v-if="d.contexto">{{ d.contexto }}: {{ d.real ?? '—' }}</template>
                <template v-else>{{ resumenCondicion(d) }} <span class="ayuda">({{ t('value: {0}', [d.real ?? '—']) }})</span></template>
              </li>
            </ul>
          </li>
        </ol>
      </div>
    </aside>
  </div>

  <Modal v-if="edicion" :titulo="edicion.id ? t('Edit rule') : t('New rule')" ancho="640px" @cerrar="edicion = null">
    <form id="form-regla" class="formulario-asig" @submit.prevent="guardar">
      <label class="campo"><span class="req">{{ t('Design') }}</span>
        <Seleccion v-model="edicion.plantilla_id" required :disabled="!!edicion.id">
          <option value="">{{ t('Choose…') }}</option>
          <option v-for="p in plantillas" :key="p.id" :value="p.id">{{ tx(p.nombre) }} · {{ tx(textoModalidad(p.modalidad)) }}{{ p.vigente ? '' : ` (${t('not approved')})` }}</option>
        </Seleccion></label>
      <div class="fila-asig">
        <label class="campo"><span>{{ t('Rule name') }}</span><input v-model="edicion.nombre" maxlength="120" /></label>
        <label class="campo"><span>{{ t('Priority') }}</span>
          <input v-model="edicion.prioridad" type="number" min="0" max="100000" :placeholder="String(SUGERIDA[edicion.ambito] || 100)" /></label>
      </div>
      <label class="campo"><span class="req">{{ t('Applies to') }}</span>
        <Seleccion v-model="edicion.ambito" :disabled="!plantillaEdicion || !!edicion.id"><option v-for="a in ambitosValidos" :key="a" :value="a">{{ tx(AMBITOS()[a]) }}</option></Seleccion></label>
      <template v-if="!edicion.id">
        <label v-if="edicion.ambito === 'FAMILIA'" class="campo"><span class="req">{{ t('Labeling family (and its subfamilies)') }}</span>
          <Seleccion v-model="edicion.familia_id" required><option value="">{{ t('Choose…') }}</option>
            <option v-for="f in familias.filter((x) => x.activa)" :key="f.id" :value="f.id">{{ tx(f.ruta || f.nombre) }}</option></Seleccion></label>
        <label v-if="edicion.ambito === 'PRODUCTO'" class="campo"><span class="req">{{ t('Product') }}</span>
          <SelectBusqueda v-model="edicion.producto_id" :buscar="buscarProductos" :etiqueta="t('Product')" :prefijo="false" requerido /></label>
        <label v-if="edicion.ambito === 'ARTICULO'" class="campo"><span class="req">{{ t('Item') }}</span>
          <SelectBusqueda v-model="edicion.articulo_id" :buscar="buscarArticulos" :etiqueta="t('Item')" :prefijo="false" requerido /></label>
        <label v-if="edicion.ambito === 'OC'" class="campo"><span class="req">{{ t('Purchase order') }}</span>
          <SelectBusqueda v-model="edicion.oc_id" :buscar="buscarOrdenes" :etiqueta="t('Purchase order')" :prefijo="false" requerido /></label>
      </template>

      <fieldset class="grupo-asig">
        <legend>{{ t('Conditions (all must be met)') }}</legend>
        <div v-for="(c, i) in edicion.condiciones" :key="i" class="condicion">
          <Seleccion v-model="c.campo" :aria-label="t('Field')"><option value="">{{ t('Field…') }}</option>
            <option v-for="f in camposEdicion" :key="f.clave" :value="f.clave">{{ tx(f.etiqueta) }} ({{ f.clave }})</option></Seleccion>
          <Seleccion v-model="c.op" :aria-label="t('Operator')"><option v-for="(txt, op) in OPERADORES()" :key="op" :value="op">{{ tx(txt) }}</option></Seleccion>
          <template v-if="c.op === 'entre'">
            <input :value="c.valor?.[0]" type="number" :aria-label="t('From')" @input="c.valor = [$event.target.value, c.valor?.[1]]" />
            <input :value="c.valor?.[1]" type="number" :aria-label="t('To')" @input="c.valor = [c.valor?.[0], $event.target.value]" />
          </template>
          <input v-else-if="!SIN_VALOR.includes(c.op)" v-model="c.valor" :type="NUMERICOS.includes(c.op) ? 'number' : 'text'" :aria-label="t('Value')"
                 :placeholder="LISTAS.includes(c.op) ? t('values separated by commas') : ''" />
          <button type="button" class="btn-icono" :aria-label="t('Remove')" @click="edicion.condiciones.splice(i, 1)"><Icono nombre="cerrar" :tam="14" /></button>
        </div>
        <button type="button" class="btn btn-chico" :disabled="!plantillaEdicion" @click="agregarCondicion"><Icono nombre="mas" :tam="14" />{{ t('Add a condition') }}</button>
      </fieldset>
      <fieldset class="grupo-asig">
        <legend>{{ t('Only for these jobs (empty: all)') }}</legend>
        <div class="checks">
          <label v-for="[o, txt] in ORIGENES()" :key="o" class="check"><input v-model="edicion.contexto.origenes" type="checkbox" :value="o" /> {{ tx(txt) }}</label>
        </div>
        <div class="checks">
          <label v-for="(txt, u) in UNIDADES()" :key="u" class="check"><input v-model="edicion.contexto.unidades" type="checkbox" :value="u" /> {{ tx(txt) }}</label>
        </div>
        <label class="campo"><span>{{ t('Package type codes') }}</span><input v-model="edicion.contexto.tipos_empaque" :placeholder="t('values separated by commas')" /></label>
      </fieldset>
      <div class="fila-asig">
        <label class="campo"><span>{{ t('Valid from') }}</span><input v-model="edicion.vigente_desde" type="date" /></label>
        <label class="campo"><span>{{ t('Valid until') }}</span><input v-model="edicion.vigente_hasta" type="date" /></label>
      </div>
      <label class="campo"><span :class="{ req: edicion.ambito === 'OC' }">{{ t('Reason') }}</span>
        <input v-model="edicion.motivo" maxlength="300" :required="edicion.ambito === 'OC'" /></label>
      <label class="check"><input v-model="edicion.predeterminada" type="checkbox" /> {{ t('Default when several rules of the same priority apply') }}</label>
      <p class="ayuda">{{ t('The rule with the highest priority among those that apply wins. Only an approved version is used.') }}</p>
    </form>
    <template #pie>
      <button class="btn separar" type="button" @click="edicion = null">{{ t('Cancel') }}</button>
      <button class="btn btn-primario" type="submit" form="form-regla">{{ t('Save') }}</button>
    </template>
  </Modal>
</template>

<style scoped>
.dos-columnas-asig { display: grid; grid-template-columns: minmax(0, 1fr) 360px; gap: 16px; align-items: start; }
@media (max-width: 1100px) { .dos-columnas-asig { grid-template-columns: 1fr; } }
.formulario-asig { display: flex; flex-direction: column; gap: 12px; }
.fila-asig { display: flex; gap: 12px; flex-wrap: wrap; }
.fila-asig > .campo { flex: 1 1 160px; }
.grupo-asig { border: 1px solid var(--linea); border-radius: 8px; padding: 10px 12px; display: flex; flex-direction: column; gap: 8px; }
.condicion { display: grid; grid-template-columns: minmax(0, 2fr) minmax(0, 1.4fr) minmax(0, 1.4fr) auto; gap: 6px; align-items: center; }
.condicion:has(input + input) { grid-template-columns: minmax(0, 2fr) minmax(0, 1.4fr) minmax(0, 0.7fr) minmax(0, 0.7fr) auto; }
@media (max-width: 600px) { .condicion, .condicion:has(input + input) { grid-template-columns: 1fr auto; } }
.checks { display: flex; gap: 10px; flex-wrap: wrap; }
.cond { display: inline-block; background: var(--linea-suave); border-radius: 6px; padding: 1px 6px; margin: 1px 4px 1px 0; font-size: 0.8rem; }
.cond.ctx { background: var(--acento-claro); }
.resultado-asig { border-top: 1px solid var(--linea); padding-top: 12px; display: flex; flex-direction: column; gap: 6px; }
.explicacion { margin: 6px 0 0; padding-inline-start: 18px; display: flex; flex-direction: column; gap: 6px; font-size: 0.84rem; }
.explicacion > li.elegida { font-weight: 600; }
.explicacion ul { list-style: none; padding: 0; margin: 2px 0 0; }
.aviso-txt { color: var(--aviso); }
.ok-txt { color: var(--ok); }
.aviso-conflictos { border: 1px solid var(--aviso-borde); background: var(--aviso-fondo); border-radius: 8px; padding: 8px 12px; margin-bottom: 12px; }
.aviso-conflictos h3 { margin: 0 0 4px; font-size: 0.95rem; display: flex; gap: 6px; align-items: center; }
.aviso-conflictos ul { margin: 0; padding-inline-start: 18px; font-size: 0.85rem; }
.aviso-conflictos li.advertencia { opacity: 0.8; }
:deep(tr.apagada > td) { opacity: 0.6; }
:deep(tr.conflicto > td:first-child) { box-shadow: inset 3px 0 0 var(--error); }
</style>
