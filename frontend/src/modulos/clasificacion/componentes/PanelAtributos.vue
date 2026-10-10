<script setup>
import { cargarContexto } from '@/modulos/clasificacion/useClasificacion'
import { t, tx } from '@/i18n/index.js'
import { computed, onMounted, reactive, ref } from 'vue'
import { api } from '@/nucleo/api'
import { filtrar } from '@/nucleo/busqueda.js'
import Icono from '@/componentes/Icono.vue'
import Interruptor from '@/componentes/Interruptor.vue'
import Modal from '@/componentes/Modal.vue'
import SelectBusqueda from '@/componentes/SelectBusqueda.vue'
import EditorCondiciones from './EditorCondiciones.vue'
import CampoComportamiento from '@/modulos/clasificacion/componentes/comportamiento/CampoComportamiento.vue'
import { puede } from '@/stores/sesion'
import { avisar, errorApi } from '@/stores/ui'
import { fmtNum } from '@/nucleo/utils'

// Atributos de la ficha técnica en base de datos: qué se pregunta, con qué
// opciones y dónde (sistema, dominio, capítulo/partida/subpartida o categoría
// de producto). Las fichas toman de aquí etiquetas, opciones activas y los
// atributos apagados; agregar una pregunta ya no requiere cambiar el código.
const edita = puede('clasificacion.configurar')
const datos = ref({ items: [], por_origen: {}, total: 0 })
const dominios = ref([])
const categorias = ref({})
const f = reactive({ q: '', origen: '', dominio: '' })
const elegido = ref(null)
const det = ref(null)
const nuevaOp = reactive({ codigo: '', etiqueta: '', alias: '' })
const nuevoAmb = reactive({ tipo_ambito: 'DOMAIN', codigo_ambito: '', modo: 'SHOW', prioridad: 500 })
const modal = ref(null)

const ORIGEN = { PAQUETE: t('Engine package'), MOTOR: t('Included engine configuration'), USUARIO: t('Created by users') }
const TIPO = { text: t('Text'), select: t('One option'), multi_select: t('Several options'), boolean: t('Yes / no'), number: t('Number'),
  composition: t('Composition (%)'), country: t('Country'), measurement_set: t('Measurements') }
const AMBITO = { SYSTEM: t('Whole system'), DOMAIN: t('Product family'), CHAPTER: t('Chapter'), HEADING: t('Heading'), SUBHEADING: t('Subheading'), CATEGORY: t('Product category') }
const MODO = { SHOW: t('Ask'), REQUIRE: t('Required'), HIDE: t('Do not ask') }
const SECCION = { producto: t('Product data'), caracteristicas: t('Characteristics'), composicion: t('Composition'),
  nacional: t('National data'), derivado: t('Derived (not asked)') }

// Comportamiento como configuración (el servidor lo valida y dice qué falla y dónde)
const EJEMPLO = {
  derivacion: '{\n  "modo": "clase",\n  "parte": "material",\n  "mapa": {"metal": "metal", "plastico": "plastico", "*": "otro"}\n}',
  patrones: '[\n  {"re": "\\\\b(lid|tapa)\\\\b", "en": "todo", "prioridad": 10}\n]',
  patrones_falso: '[\n  {"re": "\\\\b(no lid|sin tapa)\\\\b", "en": "todo"}\n]',
  texto_aduana: '{"frase": "CON TAPA", "orden": 60}',
  bloqueo: '[\n  {"condiciones": [{"campo": "categoria", "operador": "EQUAL", "valor": "caja"}], "mensaje": "A box has no lid of this kind."}\n]',
  implica: '{"otro_atributo": "su_opcion"}',
}
const AYUDA = {
  derivacion: t('Leave it to the person, or let the data set it: a fixed value, another question, or what a composition part says.'),
  patrones: t('Words that mark it in the product name, use or composition. The highest priority wins.'),
  patrones_falso: t('Words that say the box is NOT checked.'),
  texto_aduana: t('Several rows are alternatives: the first whose condition is met is used.'),
  bloqueo: t('Impossible combinations: when the conditions are met it cannot be chosen, and the message says why.'),
  implica: t('Answers that choosing this option fills in when they are still empty.'),
}
const comp = ref(null)
const malos = ref({})
const hayComportamiento = (o) => (o.patrones?.length || o.bloqueo?.length || Object.keys(o.implica || {}).length || o.texto_aduana) ? true : false
function abrirComportamiento() {
  const d = det.value
  const campos = { derivacion: d.derivacion }
  if (d.tipo_dato === 'boolean') Object.assign(campos, { patrones: d.patrones, patrones_falso: d.patrones_falso, texto_aduana: d.texto_aduana, bloqueo: d.bloqueo })
  malos.value = {}
  comp.value = { tipo: 'atributo', titulo: d.etiqueta, campos }
}
function abrirOpcion(o) {
  malos.value = {}
  comp.value = { tipo: 'opcion', o, titulo: `${det.value.etiqueta} = ${o.etiqueta}`,
    campos: { patrones: o.patrones, implica: o.implica, texto_aduana: o.texto_aduana, bloqueo: o.bloqueo } }
}
async function guardarComportamiento() {
  const c = comp.value
  const ruta = c.tipo === 'atributo' ? base() : `${base()}/opciones/${c.o.id}`
  // Filas a medio llenar no se envían (una respuesta sin pregunta, un patrón vacío)
  const campos = { ...c.campos }
  if (campos.implica) campos.implica = Object.fromEntries(Object.entries(campos.implica).filter(([k]) => k))
  for (const k of ['patrones', 'patrones_falso']) if (Array.isArray(campos[k])) campos[k] = campos[k].filter((x) => x.re || x.cuando?.length || x.defecto)
  if (await guardar(ruta, campos, 'patch', t('Behavior saved.'))) comp.value = null
}
const aliasTexto = (d) => (d.alias || []).join(', ')
const guardarAlias = (v) => campo('alias', v.split(/[,;\s]+/).map((x) => x.trim()).filter(Boolean))

async function cargar() {
  try {
    datos.value = await api.get('/aranceles/atributos')
  } catch (e) {
    errorApi(e)
  }
}
onMounted(async () => {
  cargar()
  dominios.value = await api.get('/aranceles/oficial/dominios').catch(() => [])
  cargarContexto().then((c) => (categorias.value = Object.fromEntries((c.categorias || []).map((x) => [x.codigo, x.nombre_corto || x.nombre])))).catch(() => {})
})
const lista = computed(() => filtrar(datos.value.items.filter((a) => (!f.origen || a.origen === f.origen) && (!f.dominio || a.dominio === f.dominio)),
  f.q, (a) => [a.codigo, a.etiqueta, a.descripcion, a.dominio, TIPO[a.tipo_dato]]))
const etiquetaDe = computed(() => Object.fromEntries(datos.value.items.map((a) => [a.codigo, a.etiqueta])))
// Etiqueta de una opción de cualquier atributo del catálogo
const opcionDe = (k, v) => datos.value.items.find((a) => a.codigo === k)?.opciones_min?.find((o) => o.codigo === v)?.etiqueta || v
const nombreDominio = (c) => (c === 'CORE' ? t('Core (all products)') : dominios.value.find((d) => d.codigo === c)?.nombre || c || '—')
const opcionesDominio = computed(() => [{ valor: 'CORE', texto: t('Core (all products)') }, ...dominios.value.map((d) => ({ valor: d.codigo, texto: d.nombre }))])

async function elegir(a) {
  elegido.value = a.id
  try {
    det.value = await api.get(`/aranceles/atributos/${a.id}`)
  } catch (e) {
    errorApi(e)
  }
}
async function guardar(ruta, cuerpo, metodo = 'patch', msg = null) {
  try {
    det.value = await api[metodo](ruta, cuerpo)
    if (msg) avisar(msg)
    const i = datos.value.items.findIndex((x) => x.id === det.value.id)
    if (i >= 0) datos.value.items[i] = { ...datos.value.items[i], ...det.value }
    return true
  } catch (e) {
    errorApi(e)
    return false
  }
}
const base = () => `/aranceles/atributos/${det.value.id}`
const campo = (k, v) => guardar(base(), { [k]: v })
const opcion = (o, k, v) => guardar(`${base()}/opciones/${o.id}`, { [k]: v })
async function agregarOpcion() {
  if (await guardar(`${base()}/opciones`, { ...nuevaOp }, 'post', t('Option added.'))) Object.assign(nuevaOp, { codigo: '', etiqueta: '', alias: '' })
}
const ambito = (x, datosAmb) => guardar(`${base()}/ambitos/${x.id}`, datosAmb)
async function agregarAmbito() {
  if (await guardar(`${base()}/ambitos`, { ...nuevoAmb }, 'post', t('Added: it is asked there too.'))) nuevoAmb.codigo_ambito = ''
}
// {superficie_exterior: 'textil'} → «Material of the outer surface: Textile»; {'material.corte': 'cuero'} → «Upper: Leather»
// Dependencia de un ámbito: la pregunta solo aparece si se cumplen estas condiciones
const dep = ref(null)
function abrirDep(x) {
  const c = x.condicion || []
  const conds = c.every((y) => y && 'campo' in y) ? c.map((y) => ({ ...y }))
    : c.flatMap((alt, i) => Object.entries(alt || {}).map(([campo, valor]) => ({ grupo: i + 1, campo, operador: Array.isArray(valor) ? 'IN' : 'EQUAL', valor, negado: false })))
  dep.value = { x, conds }
}
async function guardarDep() {
  if (await ambito(dep.value.x, { condicion: dep.value.conds.filter((c) => c.campo) })) dep.value = null
}
function condTexto(cond) {
  if (!cond || !cond.length) return t('Always')
  const una = ([k, v]) => `${etiquetaDe.value[k] || k}: ${v === true ? t('Yes') : v === false ? t('No') : opcionDe(k, v)}`
  if (cond.every((c) => c && 'campo' in c)) {
    const g = {}
    cond.forEach((c) => (g[c.grupo || 1] ||= []).push(`${etiquetaDe.value[c.campo] || c.campo} ${c.negado ? t('not') + ' ' : ''}${c.operador === 'EQUAL' ? '=' : c.operador === 'IN' ? t('one of') : c.operador} ${Array.isArray(c.valor) ? c.valor.join(', ') : c.valor ?? ''}`))
    return Object.values(g).map((x) => x.join(t(' and '))).join(t(' or '))
  }
  return cond.map((c) => Object.entries(c).map(una).join(', ')).join(t(' or '))
}
function codigoAmbito(x) {
  if (x.tipo_ambito === 'CATEGORY') return categorias.value[x.codigo_ambito] || x.codigo_ambito
  if (x.tipo_ambito === 'DOMAIN') return nombreDominio(x.codigo_ambito)
  if (x.tipo_ambito === 'SYSTEM') return t('All products')
  return x.codigo_ambito
}
const opcionesCodigoAmbito = computed(() => {
  if (nuevoAmb.tipo_ambito === 'DOMAIN') return dominios.value.map((d) => ({ valor: d.codigo, texto: d.nombre }))
  if (nuevoAmb.tipo_ambito === 'CATEGORY') return Object.entries(categorias.value).map(([k, v]) => ({ valor: k, texto: v }))
  if (nuevoAmb.tipo_ambito === 'SYSTEM') return [{ valor: 'ALL', texto: t('All products') }]
  return null
})
function abrirNuevo() {
  modal.value = { codigo: '', etiqueta: '', tipo_dato: 'select', unidad: '', dominio: f.dominio || 'CORE', descripcion: '' }
}
async function crear() {
  try {
    const a = await api.post('/aranceles/atributos', { ...modal.value, unidad: modal.value.unidad || null })
    modal.value = null
    avisar(t('Question created.'))
    await cargar()
    elegir(a)
  } catch (e) {
    errorApi(e)
  }
}
async function sincronizar() {
  try {
    const r = await api.post('/aranceles/atributos/motor')
    avisar(t('{0} engine attributes added.', [r.nuevos]))
    cargar()
  } catch (e) {
    errorApi(e)
  }
}
</script>

<template>
  <div class="atributos">
    <section class="panel lista">
      <div class="cabeza">
        <h3><Icono nombre="lista" :tam="16" />{{ t('Questions') }} <span class="cuenta">{{ fmtNum(datos.total) }}</span></h3>
        <div v-if="edita" class="acciones">
          <button class="btn btn-chico" :title="t('Add the product sheet attributes that are not in the database yet')" @click="sincronizar"><Icono nombre="varita" :tam="14" /></button>
          <button class="btn btn-chico btn-primario" @click="abrirNuevo"><Icono nombre="mas" :tam="14" />{{ t('New') }}</button>
        </div>
      </div>
      <label class="buscador"><Icono nombre="buscar" :tam="16" /><input v-model="f.q" type="search" :placeholder="t('Code, label or domain')" :aria-label="t('Search')" /></label>
      <div class="filtros-mini">
        <SelectBusqueda v-model="f.origen" :opciones="Object.entries(ORIGEN).map(([k, v]) => ({ valor: k, texto: v, sub: fmtNum(datos.por_origen[k] || 0) }))" :vacio="t('All origins')" :etiqueta="t('Origin')" />
        <SelectBusqueda v-model="f.dominio" :opciones="opcionesDominio" :vacio="t('All domains')" :etiqueta="t('Domain')" />
      </div>
      <ul class="items" role="list">
        <li v-if="!lista.length" class="ayuda">{{ t('No results.') }}</li>
        <li v-for="a in lista" :key="a.id">
          <button type="button" class="item" :class="{ elegido: elegido === a.id, off: !a.activo }" @click="elegir(a)">
            <span class="txt"><b>{{ tx(a.etiqueta) }}</b><small class="codigo">{{ tx(a.codigo) }}</small></span>
            <span class="meta"><span class="etiqueta">{{ tx(TIPO[a.tipo_dato] || a.tipo_dato) }}</span><small>{{ tx(nombreDominio(a.dominio)) }}</small></span>
          </button>
        </li>
      </ul>
    </section>

    <section class="panel detalle">
      <template v-if="det">
        <div class="titulo">
          <div>
            <span class="etiqueta acento">{{ tx(ORIGEN[det.origen] || det.origen) }}</span>
            <h3>{{ tx(det.etiqueta) }}</h3>
            <p class="ayuda codigo">{{ tx(det.codigo) }} · {{ tx(TIPO[det.tipo_dato] || det.tipo_dato) }}<template v-if="det.unidad"> · {{ tx(det.unidad) }}</template></p>
          </div>
          <label class="sw"><Interruptor :model-value="det.activo" :deshabilitado="!edita" :etiqueta="t('Active')" @update:model-value="campo('activo', $event)" />{{ t('Active') }}</label>
        </div>
        <p v-if="det.origen === 'MOTOR' && !det.activo" class="aviso">{{ t('The product sheet stops asking this question. Codes that depend on it may stay unresolved.') }}</p>
        <div class="campos">
          <label class="campo"><span>{{ t('Label') }}</span><input :value="det.etiqueta" :disabled="!edita" maxlength="200" @change="campo('etiqueta', $event.target.value)" /></label>
          <label class="campo"><span>{{ t('Domain (hint)') }}</span>
            <SelectBusqueda :model-value="det.dominio || ''" :opciones="opcionesDominio" :deshabilitado="!edita" :etiqueta="t('Domain')" @update:model-value="campo('dominio', $event)" /></label>
          <label class="campo ancho"><span>{{ t('Description') }}</span><input :value="det.descripcion" :disabled="!edita" maxlength="400" @change="campo('descripcion', $event.target.value)" /></label>
          <label class="campo"><span>{{ t('Section of the sheet') }}</span>
            <SelectBusqueda :model-value="det.seccion || 'caracteristicas'" :opciones="Object.entries(SECCION).map(([k, v]) => ({ valor: k, texto: v }))"
                            :deshabilitado="!edita" :etiqueta="t('Section of the sheet')" @update:model-value="campo('seccion', $event)" /></label>
          <label class="campo"><span>{{ t('Other codes (aliases)') }}</span>
            <input :value="aliasTexto(det)" :disabled="!edita" :placeholder="t('separated by commas')" @change="guardarAlias($event.target.value)" /></label>
          <label v-if="det.tipo_dato === 'boolean'" class="campo"><span>{{ t('Default answer') }}</span>
            <select :value="det.valor_defecto || ''" :disabled="!edita" class="celda" :aria-label="t('Default answer')" @change="campo('valor_defecto', $event.target.value)">
              <option value="">{{ t('None (must be answered)') }}</option><option value="true">{{ t('Yes') }}</option><option value="false">{{ t('No') }}</option>
            </select></label>
          <label class="sw"><Interruptor :model-value="det.usado_clasificacion" :deshabilitado="!edita" :etiqueta="t('Used to classify')" @update:model-value="campo('usado_clasificacion', $event)" />{{ t('Used to classify') }}</label>
          <label class="sw"><Interruptor :model-value="det.informativo" :deshabilitado="!edita" :etiqueta="t('Descriptive only')" @update:model-value="campo('informativo', $event)" />{{ t('Descriptive only') }}</label>
          <span v-if="det.de_composicion" class="ayuda">{{ t('Deduced from the composition when possible.') }}</span>
          <span v-if="det.informativo" class="ayuda">{{ t('Descriptive only: does not change the code.') }}</span>
          <button type="button" class="btn btn-chico" @click="abrirComportamiento"><Icono nombre="varita" :tam="14" />{{ t('Behavior') }}<span v-if="det.derivacion || det.patrones?.length || det.texto_aduana" class="punto" /></button>
        </div>

        <template v-if="['select', 'multi_select'].includes(det.tipo_dato)">
          <h4>{{ t('Options') }} <span class="cuenta">{{ tx(det.opciones.length) }}</span></h4>
          <p v-if="!det.opciones.length" class="ayuda">{{ t('No options yet: add the values the product sheet can choose.') }}</p>
          <div class="tabla-marco">
            <table class="tabla" v-tarjetas>
              <thead><tr><th>{{ t('Code') }}</th><th>{{ t('Label') }}</th><th>{{ t('Synonyms') }}</th><th>{{ t('Order') }}</th><th>{{ t('Active') }}</th><th>{{ t('Behavior') }}</th></tr></thead>
              <tbody>
                <tr v-for="o in det.opciones" :key="o.id" :class="{ apagada: !o.activo }">
                  <td class="codigo">{{ tx(o.codigo) }}</td>
                  <td><input class="celda" :value="o.etiqueta" :disabled="!edita" :aria-label="t('Label')" @change="opcion(o, 'etiqueta', $event.target.value)" /></td>
                  <td><input class="celda" :value="o.alias" :disabled="!edita" :aria-label="t('Synonyms')" :placeholder="t('separated by ;')" @change="opcion(o, 'alias', $event.target.value)" /></td>
                  <td><input class="celda num" type="number" :value="o.orden" :disabled="!edita" :aria-label="t('Order')" @change="opcion(o, 'orden', +$event.target.value)" /></td>
                  <td><Interruptor :model-value="o.activo" :deshabilitado="!edita" :etiqueta="t('Active')" @update:model-value="opcion(o, 'activo', $event)" /></td>
                  <td><button type="button" class="btn-icono" :aria-label="t('Behavior')" :title="t('Detection, implications, customs text and blocks')" @click="abrirOpcion(o)">
                    <Icono nombre="varita" :tam="15" /><span v-if="hayComportamiento(o)" class="punto" /></button></td>
                </tr>
                <tr v-if="edita" class="nueva">
                  <td><input v-model="nuevaOp.codigo" class="celda" :placeholder="t('Code')" :aria-label="t('Code')" maxlength="60" /></td>
                  <td><input v-model="nuevaOp.etiqueta" class="celda" :placeholder="t('Label')" :aria-label="t('Label')" maxlength="300" /></td>
                  <td><input v-model="nuevaOp.alias" class="celda" :placeholder="t('separated by ;')" :aria-label="t('Synonyms')" maxlength="400" /></td>
                  <td colspan="3"><button class="btn btn-chico" :disabled="!nuevaOp.codigo || !nuevaOp.etiqueta" @click="agregarOpcion"><Icono nombre="mas" :tam="14" />{{ t('Add') }}</button></td>
                </tr>
              </tbody>
            </table>
          </div>
        </template>

        <h4>{{ t('Where it is asked') }} <span class="cuenta">{{ tx(det.ambitos.length) }}</span></h4>
        <div class="tabla-marco ambitos">
          <table class="tabla" v-tarjetas>
            <thead><tr><th>{{ t('Asked in') }}</th><th>{{ t('Mode') }}</th><th>{{ t('Priority') }}</th><th>{{ t('When') }}</th><th></th></tr></thead>
            <tbody>
              <tr v-for="x in det.ambitos" :key="x.id" :class="{ apagada: !x.activo }">
                <td><small class="ayuda">{{ tx(AMBITO[x.tipo_ambito]) }}</small><br />{{ tx(codigoAmbito(x)) }}</td>
                <td>
                  <select :value="x.modo" :disabled="!edita" class="celda" :aria-label="t('Mode')" @change="ambito(x, { modo: $event.target.value })">
                    <option v-for="(l, k) in MODO" :key="k" :value="k">{{ tx(l) }}</option>
                  </select>
                </td>
                <td><input class="celda num" type="number" :value="x.prioridad" :disabled="!edita" :aria-label="t('Priority')" @change="ambito(x, { prioridad: +$event.target.value })" /></td>
                <td class="envolver ayuda">{{ tx(condTexto(x.condicion)) }}<template v-if="x.nota"><br />{{ tx(x.nota) }}</template>
                  <button v-if="edita" type="button" class="btn-texto" @click="abrirDep(x)">{{ t('Edit dependency') }}</button></td>
                <td><button v-if="edita" type="button" class="btn-icono" :aria-label="t('Remove')" @click="ambito(x, { quitar: true })"><Icono nombre="basura" :tam="15" /></button></td>
              </tr>
            </tbody>
          </table>
        </div>
        <div v-if="edita" class="agregar">
          <select v-model="nuevoAmb.tipo_ambito" class="celda" :aria-label="t('Asked in')" @change="nuevoAmb.codigo_ambito = ''">
            <option v-for="(l, k) in AMBITO" :key="k" :value="k">{{ tx(l) }}</option>
          </select>
          <SelectBusqueda v-if="opcionesCodigoAmbito" v-model="nuevoAmb.codigo_ambito" :opciones="opcionesCodigoAmbito" :etiqueta="t('Asked in')" :placeholder="t('Choose…')" />
          <input v-else v-model="nuevoAmb.codigo_ambito" class="celda" :placeholder="t('Code, e.g. 28 or 2915')" :aria-label="t('Code')" maxlength="10" inputmode="numeric" />
          <select v-model="nuevoAmb.modo" class="celda" :aria-label="t('Mode')"><option v-for="(l, k) in MODO" :key="k" :value="k">{{ tx(l) }}</option></select>
          <button class="btn btn-chico" :disabled="!nuevoAmb.codigo_ambito" @click="agregarAmbito"><Icono nombre="mas" :tam="14" />{{ t('Ask it here too') }}</button>
        </div>
      </template>
      <p v-else class="ayuda vacio-det"><Icono nombre="info" :tam="18" />{{ t('Choose an attribute to see its options and where the product sheet asks it.') }}</p>
    </section>

    <Modal v-if="dep" :titulo="t('When to ask {0}', [det?.etiqueta])" ancho="760px" @cerrar="dep = null">
      <p class="ayuda">{{ t('The question appears only when these conditions are met by the answers already given. Without conditions it is asked whenever its scope applies.') }}</p>
      <EditorCondiciones v-model="dep.conds" :atributos="datos.items.filter((a) => a.id !== det?.id)" />
      <template #pie>
        <button class="btn" @click="dep = null">{{ t('Cancel') }}</button>
        <button class="btn btn-primario" @click="guardarDep">{{ t('Save') }}</button>
      </template>
    </Modal>
    <Modal v-if="comp" :titulo="t('Behavior of {0}', [comp.titulo])" ancho="760px" @cerrar="comp = null">
      <p class="ayuda">{{ t('How this answer behaves by itself. The server checks every reference (questions, options, composition parts) before saving.') }}</p>
      <CampoComportamiento v-for="(_, k) in comp.campos" :key="k" v-model="comp.campos[k]" :tipo="k" :atributos="datos.items" :atributo="det"
                           :etiqueta="{ derivacion: t('How its value is set'), patrones: t('How it is recognized in the product text'),
                                        patrones_falso: t('How a «no» is recognized'), texto_aduana: t('What it adds to the customs description'),
                                        bloqueo: t('When it cannot be chosen'), implica: t('What it fills in') }[k]"
                           :ayuda="AYUDA[k]" :ejemplo="EJEMPLO[k]" :deshabilitado="!edita" @valido="malos[k] = !$event" />
      <template #pie>
        <button class="btn" @click="comp = null">{{ t('Cancel') }}</button>
        <button v-if="edita" class="btn btn-primario" :disabled="Object.values(malos).some(Boolean)" @click="guardarComportamiento">{{ t('Save') }}</button>
      </template>
    </Modal>
    <Modal v-if="modal" :titulo="t('New question')" @cerrar="modal = null">
      <div class="campos">
        <label class="campo"><span>{{ t('Code') }}</span><input v-model="modal.codigo" maxlength="40" :placeholder="t('e.g. flash_point')" /></label>
        <label class="campo"><span>{{ t('Label') }}</span><input v-model="modal.etiqueta" maxlength="200" /></label>
        <label class="campo"><span>{{ t('Data type') }}</span>
          <SelectBusqueda v-model="modal.tipo_dato" :opciones="Object.entries(TIPO).map(([k, v]) => ({ valor: k, texto: v }))" :etiqueta="t('Data type')" /></label>
        <label class="campo"><span>{{ t('Unit') }}</span><input v-model="modal.unidad" maxlength="10" :placeholder="t('e.g. %, kg, °C')" /></label>
        <label class="campo"><span>{{ t('Domain (hint)') }}</span><SelectBusqueda v-model="modal.dominio" :opciones="opcionesDominio" :etiqueta="t('Domain')" /></label>
        <label class="campo ancho"><span>{{ t('Description') }}</span><input v-model="modal.descripcion" maxlength="400" /></label>
      </div>
      <template #pie>
        <button class="btn" @click="modal = null">{{ t('Cancel') }}</button>
        <button class="btn btn-primario" :disabled="!modal.codigo || !modal.etiqueta" @click="crear">{{ t('Create') }}</button>
      </template>
    </Modal>
  </div>
</template>

<style scoped>
.atributos { display: grid; grid-template-columns: minmax(280px, 380px) 1fr; gap: 14px; align-items: start; }
.cabeza { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; gap: 8px; }
.cabeza h3 { margin: 0; font-size: 1rem; display: flex; gap: 6px; align-items: center; }
.acciones { display: flex; gap: 6px; }
.lista .buscador { width: 100%; max-width: none; }
.filtros-mini { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; margin: 8px 0; }
.items { list-style: none; margin: 0; padding: 0; max-height: 62vh; overflow-y: auto; }
.item { display: flex; justify-content: space-between; gap: 8px; width: 100%; text-align: start; border: 0; background: none; padding: 7px 8px; border-radius: 8px; cursor: pointer; color: inherit; font: inherit; font-size: 0.86rem; }
.item:hover { background: var(--superficie-2); }
.item.elegido { background: var(--acento-claro); color: var(--acento-texto); }
.item.off { opacity: 0.55; }
.item .txt { display: flex; flex-direction: column; min-width: 0; }
.item .txt small { color: var(--tinta-3); }
.item .meta { display: flex; flex-direction: column; align-items: flex-end; gap: 2px; flex: none; }
.item .meta small { color: var(--tinta-3); font-size: 0.74rem; }
.titulo { display: flex; justify-content: space-between; gap: 12px; align-items: flex-start; }
.titulo h3 { margin: 4px 0 0; font-size: 1.3rem; }
.titulo p { margin: 2px 0 0; }
.sw { display: inline-flex; gap: 8px; align-items: center; font-size: 0.86rem; }
.aviso { background: var(--aviso-fondo); padding: 8px 10px; border-radius: var(--radio); font-size: 0.86rem; }
.campos { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 10px; margin: 12px 0; align-items: end; }
.campo { display: flex; flex-direction: column; gap: 4px; font-size: 0.82rem; }
.campo.ancho { grid-column: 1 / -1; }
h4 { margin: 16px 0 6px; font-size: 0.92rem; display: flex; gap: 6px; align-items: center; }
.celda { width: 100%; min-width: 70px; }
.celda::placeholder { color: var(--tinta-3); }
.nueva .celda, .agregar .celda { border-color: var(--linea); background: var(--superficie); }
.agregar select.celda { font-size: 0.86rem; padding: 6px 8px; }
.celda.num { width: 80px; min-width: 0; }
tr.apagada td { opacity: 0.55; }
.ambitos { max-height: 340px; overflow-y: auto; }
.agregar { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin-top: 8px; }
.agregar .celda { width: auto; }
.agregar :deep(.sb) { min-width: 220px; }
.punto { width: 7px; height: 7px; border-radius: 50%; background: var(--acento); display: inline-block; margin-inline-start: 4px; }
.vacio-det { display: flex; gap: 8px; align-items: center; justify-content: center; min-height: 260px; }
@media (max-width: 900px) { .atributos { grid-template-columns: 1fr; } }
</style>
