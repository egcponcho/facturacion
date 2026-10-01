<script setup>
import { t, tx } from '../i18n/index.js'
import { computed, onMounted, reactive, ref, watch } from 'vue'
import Seleccion from '../components/Seleccion.vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api'
import BarraSeleccion from '../components/BarraSeleccion.vue'
import BotonesExportar from '../components/BotonesExportar.vue'
import CargaMasiva from '../components/CargaMasiva.vue'
import CeldaEditable from '../components/CeldaEditable.vue'
import FiltroMulti from '../components/FiltroMulti.vue'
import Icono from '../components/Icono.vue'
import Modal from '../components/Modal.vue'
import Paginacion from '../components/Paginacion.vue'
import ThOrden from '../components/ThOrden.vue'
import PanelArbol from '../components/aranceles/PanelArbol.vue'
import PanelCapitulos from '../components/aranceles/PanelCapitulos.vue'
import PanelDominios from '../components/aranceles/PanelDominios.vue'
import PanelFuentes from '../components/aranceles/PanelFuentes.vue'
import PanelImportacion from '../components/aranceles/PanelImportacion.vue'
import { cargarContexto } from '../clasificacion/useClasificacion'
import { siguienteOrden } from '../composables/useTabla'
import { puede } from '../stores/sesion'
import { avisar, errorApi } from '../stores/ui'
import { fmtNum, useSeleccion } from '../utils'
import { filasDefecto } from '../stores/preferencias'

// Arancel: países destino (con sus dígitos), subpartidas SAC y códigos
// nacionales con las condiciones que los eligen. Todo editable, con carga
// desde Excel y exportación con los filtros de la pantalla.
const route = useRoute()
const router = useRouter()
const edita = puede('aranceles.editar')
const vista = ref(route.query.vista || 'codigos')
const paises = ref([])
const meta = ref({ condiciones: {}, fuentes: {} })
const modal = ref(null)
const ocupado = ref(false)
const sel = useSeleccion()

const opcionesPais = computed(() => paises.value.map((p) => ({ valor: p.iso, texto: `${p.iso} · ${p.nombre}` })))
const opcionesFuente = computed(() => Object.entries(meta.value.fuentes).map(([v, t]) => ({ valor: v, texto: t })))
const CAPITULOS = [['42', t('42 · Leather goods, bags')], ['61', t('61 · Knitted apparel')], ['62', t('62 · Woven apparel')], ['63', t('63 · Other textile articles')],
  ['64', t('64 · Footwear')], ['65', t('65 · Headwear')], ['39', t('39 · Plastics')], ['40', t('40 · Rubber')], ['48', t('48 · Paper')], ['66', t('66 · Umbrellas')],
  ['71', t('71 · Jewelry')], ['73', t('73 · Iron or steel')], ['76', t('76 · Aluminum')], ['90', t('90 · Optics')], ['91', t('91 · Watches')], ['94', t('94 · Furniture, bedding')],
  ['95', t('95 · Sports articles')], ['96', t('96 · Miscellaneous')]].map(([valor, texto]) => ({ valor, texto }))

async function cargarBase() {
  try {
    const [ps, m] = await Promise.all([api.get('/aranceles/paises'), api.get('/aranceles/opciones')])
    paises.value = ps
    meta.value = m
  } catch (e) {
    errorApi(e)
  }
}

// ---- Códigos nacionales -------------------------------------------------------
const fc = reactive({ q: route.query.q || '', pais: route.query.pais ? String(route.query.pais).split(',') : [], capitulo: [], fuente: [], activo: '', orden: '', page: 1, size: filasDefecto() })
const codigos = ref({ items: [], total: 0, por_pais: {} })
const paramsC = computed(() => ({ q: fc.q, pais: fc.pais.join(','), capitulo: fc.capitulo.join(','), fuente: fc.fuente.join(','), activo: fc.activo, orden: fc.orden }))
async function cargarCodigos() {
  try {
    codigos.value = await api.get('/aranceles/codigos', { ...paramsC.value, page: fc.page, size: fc.size })
    sel.podar(codigos.value.items.map((x) => x.id))
  } catch (e) {
    errorApi(e)
  }
}
const recargarC = () => { fc.page = 1; cargarCodigos() }
let espera
const buscarC = () => { clearTimeout(espera); espera = setTimeout(recargarC, 300) }
const digitosDe = (iso) => paises.value.find((p) => p.iso === iso)?.digitos || 10
const digits = (v) => String(v || '').replace(/\D/g, '')
function fmtPais(c, n) {
  const d = String(c || '').replace(/\D/g, '')
  const s = d.padEnd(n, '_').slice(0, n)
  return [s.slice(0, 4), ...s.slice(4).match(/.{1,2}/g) || []].join('.')
}

async function guardarCampo(x, campo, valor) {
  await api.put(`/aranceles/codigos/${x.id}`, { pais: x.pais, codigo: x.codigo, descripcion: x.descripcion, dai: x.dai, cond: x.cond, prio: x.prio, nota: x.nota, activo: x.activo, [campo]: valor })
  x[campo] = valor
  cargarContexto(true)
}
function nuevoCodigo() {
  modal.value = { tipo: 'codigo', id: null, pais: fc.pais[0] || paises.value[0]?.iso, codigo: '', descripcion: '', dai: '', prio: 0, nota: '', activo: true, cond: {} }
}
function editarCodigo(x) {
  modal.value = { tipo: 'codigo', ...JSON.parse(JSON.stringify(x)) }
}
// Solo las condiciones que aplican al país y la subpartida del código: las que
// ya usa ese país, las que usan los demás y las que abren incisos en su capítulo
const aplicables = ref(null)
const verTodas = ref(false)
let esperaCond
watch(() => modal.value?.tipo === 'codigo' && [modal.value.pais, digits(modal.value.codigo).slice(0, 6)].join('|'), (clave) => {
  clearTimeout(esperaCond)
  if (!clave) return
  esperaCond = setTimeout(async () => {
    try {
      aplicables.value = await api.get('/aranceles/condiciones', { pais: modal.value.pais, codigo: modal.value.codigo })
    } catch {
      aplicables.value = null
    }
  }, 250)
}, { immediate: true })
const condActivas = computed(() => {
  const todas = meta.value.condiciones
  const a = aplicables.value
  if (verTodas.value || !a || digits(modal.value?.codigo || '').length < 6) return Object.entries(todas)
  const puestas = Object.keys(modal.value?.cond || {})
  return [...new Set([...a.aplican, ...puestas])].filter((k) => todas[k]).map((k) => [k, todas[k]])
})
const origenCond = (k) => (aplicables.value?.del_pais.includes(k) ? 'pais' : aplicables.value?.de_otros.includes(k) ? 'otros' : '')
function valorCond(k) {
  const v = modal.value.cond[k]
  return v === undefined ? [] : Array.isArray(v) ? v : [v]
}
function ponerCond(k, v) {
  const c = { ...modal.value.cond }
  if (v === '' || v === null || (Array.isArray(v) && !v.length)) delete c[k]
  else c[k] = Array.isArray(v) && v.length === 1 ? v[0] : v
  modal.value.cond = c
}
async function guardarCodigo() {
  const m = modal.value
  ocupado.value = true
  try {
    const cuerpo = { pais: m.pais, codigo: m.codigo, descripcion: m.descripcion, dai: m.dai, cond: m.cond, prio: Number(m.prio) || 0, nota: m.nota, activo: m.activo }
    if (m.id) await api.put(`/aranceles/codigos/${m.id}`, cuerpo)
    else await api.post('/aranceles/codigos', cuerpo)
    modal.value = null
    avisar(t('National code saved. The classification uses it right away.'))
    cargarCodigos()
    cargarBase()
    cargarContexto(true)
  } catch (e) {
    errorApi(e)
  } finally {
    ocupado.value = false
  }
}
async function borrarSeleccion() {
  if (!window.confirm(t('Delete {0} national codes? Products already approved keep their codes.', [sel.ids.size]))) return
  try {
    const r = await api.post('/aranceles/codigos/borrar', { ids: sel.lista() })
    avisar(t('{0} codes deleted.', [r.borrados]))
    sel.limpiar()
    cargarCodigos()
    cargarBase()
    cargarContexto(true)
  } catch (e) {
    errorApi(e)
  }
}

// ---- Subpartidas SAC ---------------------------------------------------------------
const fs = reactive({ q: '', capitulo: [], nivel: '', fuente: [], page: 1, size: filasDefecto() })
const sac = ref({ items: [], total: 0 })
const paramsS = computed(() => ({ q: fs.q, capitulo: fs.capitulo.join(','), nivel: fs.nivel, fuente: fs.fuente.join(',') }))
async function cargarSac() {
  try {
    sac.value = await api.get('/aranceles/sac', { ...paramsS.value, page: fs.page, size: fs.size })
  } catch (e) {
    errorApi(e)
  }
}
const recargarS = () => { fs.page = 1; cargarSac() }
const buscarS = () => { clearTimeout(espera); espera = setTimeout(recargarS, 300) }
// ---- Notas legales del SAC ----------------------------------------------------
const notas = ref({ items: [], ambitos: {} })
const fn = reactive({ q: '', capitulo: [] })
async function cargarNotas() {
  try {
    notas.value = await api.get('/aranceles/notas', { q: fn.q, capitulo: fn.capitulo.join(',') })
  } catch (e) {
    errorApi(e)
  }
}
let esperaN
function buscarN() {
  clearTimeout(esperaN)
  esperaN = setTimeout(cargarNotas, 300)
}
async function guardarNota() {
  const m = modal.value
  ocupado.value = true
  try {
    const cuerpo = { ambito: m.ambito, codigo: m.codigo, numero: m.numero, texto: m.texto, activo: m.activo,
                     capitulos: String(m.capitulos_txt || '').split(/[\s,;]+/).filter(Boolean) }
    if (m.id) await api.put(`/aranceles/notas/${m.id}`, cuerpo)
    else await api.post('/aranceles/notas', cuerpo)
    modal.value = null
    avisar(t('Note saved. Classification takes it into account from now on.'))
    cargarNotas()
    cargarContexto(true)
  } catch (e) {
    errorApi(e)
  } finally {
    ocupado.value = false
  }
}
async function borrarNota(n) {
  if (!confirm(t('Delete note {0} {1}?', [n.codigo, n.numero]))) return
  try {
    await api.del(`/aranceles/notas/${n.id}`)
    cargarNotas()
    cargarContexto(true)
  } catch (e) {
    errorApi(e)
  }
}

async function guardarSac() {
  const m = modal.value
  ocupado.value = true
  try {
    const cuerpo = { codigo: m.codigo, descripcion: m.descripcion, nota: m.nota, activo: m.activo }
    if (m.id) await api.put(`/aranceles/sac/${m.id}`, cuerpo)
    else await api.post('/aranceles/sac', cuerpo)
    modal.value = null
    avisar(t('Subheading saved.'))
    cargarSac()
    cargarContexto(true)
  } catch (e) {
    errorApi(e)
  } finally {
    ocupado.value = false
  }
}
async function borrarSac(x) {
  if (!window.confirm(t('Delete {0}?', [x.codigo_txt]))) return
  try {
    await api.del(`/aranceles/sac/${x.id}`)
    cargarSac()
  } catch (e) {
    errorApi(e)
  }
}
function verCodigosDe(x) {
  fc.q = x.codigo
  fc.pais = []
  cambiarVista('codigos')
}

// ---- Países ----------------------------------------------------------------------------
async function guardarPais() {
  const m = modal.value
  ocupado.value = true
  try {
    const cuerpo = { iso: m.iso, nombre: m.nombre, digitos: Number(m.digitos), mcca: !!m.mcca, impuesto: m.impuesto, nota: m.nota, base_legal: m.base_legal || null, activo: m.activo }
    if (m.id) await api.put(`/aranceles/paises/${m.id}`, cuerpo)
    else await api.post('/aranceles/paises', cuerpo)
    modal.value = null
    avisar(t('Country saved. Technical sheets now ask for its national code.'))
    cargarBase()
    cargarContexto(true)
  } catch (e) {
    errorApi(e)
  } finally {
    ocupado.value = false
  }
}
async function borrarPais(p) {
  if (!window.confirm(t('Delete {0}?', [p.nombre]))) return
  try {
    await api.del(`/aranceles/paises/${p.id}`)
    cargarBase()
  } catch (e) {
    errorApi(e)
  }
}
function cargarPais(p) {
  modal.value = { tipo: 'carga-codigos', pais: p.iso, reemplazar: false }
}

function cambiarVista(v) {
  vista.value = v
  router.replace({ query: { vista: v } })
  if (v === 'codigos') recargarC()
  if (v === 'sac') cargarSac()
  if (v === 'notas') cargarNotas()
}
function alCargar() {
  cargarBase()
  cargarContexto(true)
  if (vista.value === 'sac') cargarSac()
  else cargarCodigos()
}

onMounted(async () => {
  await cargarBase()
  if (vista.value === 'sac') cargarSac()
  else if (vista.value === 'notas') cargarNotas()
  else cargarCodigos()
})
watch(() => fc.size, recargarC)
watch(() => fs.size, recargarS)
</script>

<template>
  <div class="pagina-cabeza">
    <div>
      <div class="pestanas-pildora sub-mod">
        <router-link to="/productos" class="pildora">{{ t('Products') }}</router-link>
        <span class="pildora" aria-current="page" aria-pressed="true">{{ t('Tariff schedule') }}</span>
      </div>
      <h1>{{ t('Tariff schedule') }}</h1>
      <p>{{ t('Destination countries and their digits, the SAC headings and subheadings, and each country\'s national codes with the conditions that select them. The classification engine uses what is loaded here.') }}</p>
    </div>
  </div>

  <div class="paises-resumen">
    <button v-for="p in paises" :key="p.iso" type="button" class="pais-tarjeta" :class="{ inactivo: !p.activo, elegido: vista === 'codigos' && fc.pais.includes(p.iso) }"
            @click="fc.pais = fc.pais.includes(p.iso) ? fc.pais.filter((x) => x !== p.iso) : [...fc.pais, p.iso]; cambiarVista('codigos')">
      <span class="iso">{{ tx(p.iso) }}</span>
      <span class="pt-datos"><b>{{ tx(p.nombre) }}</b><small>{{ t('{0} digits{1} · {2} codes', [p.digitos, p.mcca ? ' · CACM' : '', fmtNum(p.codigos)]) }}</small></span>
    </button>
    <button v-if="edita" type="button" class="pais-tarjeta nuevo" @click="modal = { tipo: 'pais', id: null, iso: '', nombre: '', digitos: 10, mcca: false, impuesto: '', nota: '', base_legal: '', activo: true }">
      <Icono nombre="mas" :tam="16" /> {{ t('Add country') }}
    </button>
  </div>

  <div class="pestanas" role="tablist">
    <button class="pestana" role="tab" :aria-selected="vista === 'arbol'" @click="cambiarVista('arbol')">{{ t('Tariff tree') }}</button>
    <button class="pestana" role="tab" :aria-selected="vista === 'codigos'" @click="cambiarVista('codigos')">{{ t('National codes') }} <span class="cuenta">{{ fmtNum(codigos.total) }}</span></button>
    <button class="pestana" role="tab" :aria-selected="vista === 'sac'" @click="cambiarVista('sac')">{{ t('SAC headings and subheadings') }}</button>
    <button class="pestana" role="tab" :aria-selected="vista === 'notas'" @click="cambiarVista('notas')">{{ t('SAC legal notes') }}</button>
    <button class="pestana" role="tab" :aria-selected="vista === 'paises'" @click="cambiarVista('paises')">{{ t('Countries') }} <span class="cuenta">{{ tx(paises.length) }}</span></button>
    <button class="pestana" role="tab" :aria-selected="vista === 'capitulos'" @click="cambiarVista('capitulos')">{{ t('Chapters') }}</button>
    <button class="pestana" role="tab" :aria-selected="vista === 'dominios'" @click="cambiarVista('dominios')">{{ t('Domains') }}</button>
    <button class="pestana" role="tab" :aria-selected="vista === 'fuentes'" @click="cambiarVista('fuentes')">{{ t('Sources and versions') }}</button>
    <button class="pestana" role="tab" :aria-selected="vista === 'importacion'" @click="cambiarVista('importacion')">{{ t('Data import') }}</button>
  </div>
  <PanelArbol v-if="vista === 'arbol'" />
  <PanelCapitulos v-else-if="vista === 'capitulos'" />
  <PanelDominios v-else-if="vista === 'dominios'" />
  <PanelFuentes v-else-if="vista === 'fuentes'" />
  <PanelImportacion v-else-if="vista === 'importacion'" @cargado="cargarBase" />

  <!-- Códigos nacionales -->
  <section v-if="vista === 'codigos'">
    <div class="filtros" v-filtros>
      <label class="buscador"><Icono nombre="buscar" :tam="16" /><input v-model="fc.q" type="search" :placeholder="t('Code or description')" :aria-label="t('Search')" @input="buscarC" /></label>
      <FiltroMulti v-model="fc.pais" :etiqueta="t('Country')" :opciones="opcionesPais" @change="recargarC" />
      <FiltroMulti v-model="fc.capitulo" :etiqueta="t('Chapter')" :opciones="CAPITULOS" @change="recargarC" />
      <FiltroMulti v-model="fc.fuente" :etiqueta="t('Source')" :opciones="opcionesFuente" @change="recargarC" />
      <Seleccion v-model="fc.activo" :aria-label="t('Active')" @change="recargarC"><option value="">{{ t('Active and inactive') }}</option><option value="true">{{ t('Active') }}</option><option value="false">{{ t('Inactive') }}</option></Seleccion>
      <div class="separar fila-flex">
        <BotonesExportar ruta="/aranceles/codigos/exportar" :params="paramsC" />
        <template v-if="edita">
          <button class="btn" @click="modal = { tipo: 'carga-codigos', pais: fc.pais.length === 1 ? fc.pais[0] : '', reemplazar: false }"><Icono nombre="importar" />{{ t('Upload Excel') }}</button>
          <button class="btn btn-primario" @click="nuevoCodigo"><Icono nombre="mas" />{{ t('Add code') }}</button>
        </template>
      </div>
    </div>
    <div class="tabla-marco tabla-fija">
      <table class="tabla" v-tarjetas>
        <thead>
          <tr>
            <th v-if="edita" class="check"><input type="checkbox" :aria-label="t('Select all')" :checked="sel.todos(codigos.items.map((x) => x.id))" @change="sel.alternarTodos(codigos.items.map((x) => x.id))" /></th>
            <ThOrden campo="pais" :orden="fc.orden" @ordenar="(c) => { fc.orden = siguienteOrden(fc.orden, c); recargarC() }">{{ t('Country') }}</ThOrden>
            <ThOrden campo="codigo" :orden="fc.orden" @ordenar="(c) => { fc.orden = siguienteOrden(fc.orden, c); recargarC() }">{{ t('National code') }}</ThOrden>
            <th>{{ t('Description') }}</th>
            <ThOrden campo="dai" :orden="fc.orden" num @ordenar="(c) => { fc.orden = siguienteOrden(fc.orden, c); recargarC() }">{{ t('Duty %') }}</ThOrden>
            <th>{{ t('When it applies') }}</th>
            <ThOrden campo="fuente" :orden="fc.orden" @ordenar="(c) => { fc.orden = siguienteOrden(fc.orden, c); recargarC() }">{{ t('Source') }}</ThOrden>
            <th v-if="edita"></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="x in codigos.items" :key="x.id" :class="{ seleccionada: sel.tiene(x.id), apagada: !x.activo }">
            <td v-if="edita" class="check"><input type="checkbox" :aria-label="t('Select {0}', [x.codigo_txt])" :checked="sel.tiene(x.id)" @change="sel.alternar(x.id)" /></td>
            <td class="fuerte">{{ tx(x.pais) }}</td>
            <td><span class="codigo-sac">{{ fmtPais(x.codigo, digitosDe(x.pais)) }}</span><span class="sub" :title="tx(x.sac)">{{ tx(x.sac ? x.sac.slice(0, 70) + (x.sac.length > 70 ? '…' : '') : '') }}</span></td>
            <td style="min-width: 220px">
              <CeldaEditable v-if="edita" :valor="x.descripcion" vacia-texto="—" :etiqueta="t('Description of {0}', [x.codigo_txt])" :guardar="(v) => guardarCampo(x, 'descripcion', v)" />
              <template v-else>{{ tx(x.descripcion || '—') }}</template>
            </td>
            <td class="num" style="width: 90px">
              <CeldaEditable v-if="edita" :valor="x.dai" vacia-texto="—" :etiqueta="t('Duty of {0}', [x.codigo_txt])" :guardar="(v) => guardarCampo(x, 'dai', v)" />
              <template v-else>{{ tx(x.dai ?? '—') }}</template>
            </td>
            <td class="cond">{{ tx(x.cond_txt) }}<span v-if="x.prio" class="etiqueta">{{ t('priority {0}', [x.prio]) }}</span></td>
            <td><span class="etiqueta" :class="{ acento: x.fuente === 'aprendido', info: x.fuente === 'archivo' }">{{ tx(x.fuente_txt) }}</span><span v-if="!x.activo" class="etiqueta">{{ t('Inactive') }}</span></td>
            <td v-if="edita" class="num"><button class="btn-icono" :aria-label="t('Edit {0}', [x.codigo_txt])" :title="t('Edit')" @click="editarCodigo(x)"><Icono nombre="editar" :tam="16" /></button></td>
          </tr>
          <tr v-if="!codigos.items.length"><td :colspan="edita ? 8 : 6" class="vacio">{{ t('No national codes match these filters.') }}</td></tr>
        </tbody>
      </table>
    </div>
    <Paginacion :page="fc.page" :size="fc.size" :total="codigos.total" @cambiar="(p) => { fc.page = p; cargarCodigos() }" @tamano="(t) => (fc.size = t)" />
    <BarraSeleccion :cantidad="sel.ids.size" singular="code" plural="codes" @limpiar="sel.limpiar()">
      <button class="btn btn-peligro" @click="borrarSeleccion"><Icono nombre="basura" />{{ t('Delete') }}</button>
    </BarraSeleccion>
  </section>

  <!-- SAC -->
  <section v-else-if="vista === 'sac'">
    <div class="filtros" v-filtros>
      <label class="buscador"><Icono nombre="buscar" :tam="16" /><input v-model="fs.q" type="search" :placeholder="t('Code or text')" :aria-label="t('Search')" @input="buscarS" /></label>
      <FiltroMulti v-model="fs.capitulo" :etiqueta="t('Chapter')" :opciones="CAPITULOS" @change="recargarS" />
      <Seleccion v-model="fs.nivel" :aria-label="t('Level')" @change="recargarS"><option value="">{{ t('Headings and subheadings') }}</option><option value="4">{{ t('Headings (4 digits)') }}</option><option value="6">{{ t('Subheadings (6 digits)') }}</option></Seleccion>
      <div class="separar fila-flex">
        <BotonesExportar ruta="/aranceles/sac/exportar" :params="paramsS" />
        <template v-if="edita">
          <button class="btn" @click="modal = { tipo: 'carga-sac' }"><Icono nombre="importar" />{{ t('Upload Excel') }}</button>
          <button class="btn btn-primario" @click="modal = { tipo: 'sac', id: null, codigo: '', descripcion: '', nota: '', activo: true }"><Icono nombre="mas" />{{ t('Add') }}</button>
        </template>
      </div>
    </div>
    <div class="tabla-marco tabla-fija">
      <table class="tabla" v-tarjetas>
        <thead><tr><th>{{ t('Code') }}</th><th>{{ t('Official description') }}</th><th class="num">{{ t('National codes') }}</th><th>{{ t('Source') }}</th><th v-if="edita"></th></tr></thead>
        <tbody>
          <tr v-for="x in sac.items" :key="x.id">
            <td :class="x.codigo.length === 4 ? 'fuerte' : ''"><span class="codigo-sac">{{ tx(x.codigo_txt) }}</span></td>
            <td :class="{ fuerte: x.codigo.length === 4 }">{{ tx(x.descripcion) }}<span v-if="x.nota" class="sub">{{ tx(x.nota) }}</span></td>
            <td class="num"><button v-if="x.nacionales" type="button" class="enlace" @click="verCodigosDe(x)">{{ tx(x.nacionales) }}</button><span v-else class="apagado">—</span></td>
            <td><span class="etiqueta">{{ tx(meta.fuentes[x.fuente] || x.fuente) }}</span></td>
            <td v-if="edita" class="num" style="white-space: nowrap">
              <button class="btn-icono" :aria-label="t('Edit {0}', [x.codigo_txt])" @click="modal = { tipo: 'sac', ...x }"><Icono nombre="editar" :tam="16" /></button>
              <button class="btn-icono" style="color: var(--error)" :aria-label="t('Delete {0}', [x.codigo_txt])" @click="borrarSac(x)"><Icono nombre="basura" :tam="16" /></button>
            </td>
          </tr>
          <tr v-if="!sac.items.length"><td colspan="5" class="vacio">{{ t('Nothing matches these filters.') }}</td></tr>
        </tbody>
      </table>
    </div>
    <Paginacion :page="fs.page" :size="fs.size" :total="sac.total" @cambiar="(p) => { fs.page = p; cargarSac() }" @tamano="(t) => (fs.size = t)" />
  </section>

  <!-- Países -->
  <section v-else-if="vista === 'paises'" class="paises-grid">
    <article v-for="p in paises" :key="p.iso" class="panel pais-panel" :class="{ inactivo: !p.activo }">
      <div class="panel-cabeza">
        <div><h2>{{ tx(p.iso) }} · {{ tx(p.nombre) }}</h2><p>{{ t('{0}-digit national codes{1}', [p.digitos, p.mcca ? t(' · Central American Common Market') : '']) }}</p></div>
        <span v-if="!p.activo" class="etiqueta">{{ t('Inactive') }}</span>
      </div>
      <div class="doc-meta" style="margin-top: 0">
        <span>{{ t('Codes loaded') }} <b>{{ fmtNum(p.codigos) }}</b></span>
        <span v-if="p.impuesto">{{ t('Tax') }} <b>{{ tx(p.impuesto) }}</b></span>
      </div>
      <p v-if="p.modelo_arancel" class="ayuda mt-chico"><b>{{ t('Tariff model:') }}</b> {{ tx(p.modelo_arancel) }}<template v-if="p.fuente"> · {{ t('Primary source {0}', [p.fuente]) }}</template></p>
      <p v-if="p.base_legal" class="ayuda mt-chico"><b>{{ t('Legal basis:') }}</b> {{ tx(p.base_legal) }}</p>
      <p v-if="p.nota" class="ayuda mt-chico">{{ tx(p.nota) }}</p>
      <div class="fila-flex mt-chico" style="gap: 6px">
        <button class="btn btn-chico" @click="fc.pais = [p.iso]; cambiarVista('codigos')"><Icono nombre="lista" :tam="14" />{{ t('See codes') }}</button>
        <template v-if="edita">
          <button class="btn btn-chico" @click="cargarPais(p)"><Icono nombre="importar" :tam="14" />{{ t('Upload codes') }}</button>
          <button class="btn btn-chico btn-fantasma" @click="modal = { tipo: 'pais', ...p }"><Icono nombre="editar" :tam="14" />{{ t('Edit') }}</button>
          <button v-if="!p.codigos" class="btn btn-chico btn-fantasma" style="color: var(--error)" @click="borrarPais(p)"><Icono nombre="basura" :tam="14" />{{ t('Delete') }}</button>
        </template>
      </div>
    </article>
  </section>

  <!-- Ventanas -->
  <Modal v-if="modal?.tipo === 'codigo'" :titulo="tx(modal.id ? t('National code {0}', [modal.codigo]) : t('New national code'))" ancho="760px" @cerrar="modal = null">
    <div class="rejilla-campos">
      <label class="campo"><span class="req">{{ t('Country') }}</span>
        <Seleccion v-model="modal.pais" class="entrada"><option v-for="p in paises" :key="p.iso" :value="p.iso">{{ tx(p.iso) }} · {{ tx(p.nombre) }}</option></Seleccion></label>
      <label class="campo"><span class="req">{{ t('Code ({0} digits)', [digitosDe(modal.pais)]) }}</span><input v-model="modal.codigo" class="entrada" :placeholder="tx('0'.repeat(digitosDe(modal.pais)))" /></label>
      <label class="campo"><span>{{ t('Duty (DAI %)') }}</span><input v-model="modal.dai" class="entrada" /></label>
      <label class="campo"><span>{{ t('Priority') }}</span><input v-model="modal.prio" type="number" min="0" max="99" class="entrada" /></label>
      <label class="campo" style="grid-column: 1 / -1"><span>{{ t('Description') }}</span><input v-model="modal.descripcion" class="entrada" maxlength="300" /></label>
    </div>
    <h3 class="mt">{{ t('When it applies') }}</h3>
    <p class="ayuda">{{ t('Leave empty what does not matter. The engine picks the code whose conditions match the technical sheet.') }}
      <template v-if="aplicables?.subpartida && !verTodas"> {{ t('Only the data that splits {0} is shown: what {1} already uses, what the other countries use and what opens national codes in chapter {2}.', [aplicables.subpartida.codigo, modal.pais, aplicables.subpartida.codigo.slice(0, 2)]) }}</template>
      <template v-else-if="digits(modal.codigo || '').length < 6"> {{ t('Type the code to see only the conditions that apply to its subheading.') }}</template>
      <button v-if="aplicables?.subpartida" type="button" class="btn-texto" @click="verTodas = !verTodas">{{ tx(verTodas ? t('Show only the ones that apply') : t('Show all conditions')) }}</button></p>
    <div v-if="aplicables?.hermanos?.length" class="hermanos">
      <b>{{ t('How {0} splits {1} today', [modal.pais, aplicables.subpartida.codigo]) }}</b>
      <ul><li v-for="h in aplicables.hermanos" :key="h.codigo" :class="{ actual: digits(h.codigo) === digits(modal.codigo || '') }"><span class="codigo-sac">{{ tx(h.codigo_txt) }}</span> {{ tx(h.cond_txt) }}<template v-if="h.dai !== null && h.dai !== ''"> {{ t('· DAI {0}%', [h.dai]) }}</template></li></ul>
    </div>
    <div class="conds">
      <div v-for="[k, d] in condActivas" :key="k" class="campo">
        <span>{{ tx(d.label) }}<small v-if="origenCond(k) === 'pais'" class="etiqueta acento" :title="t('{0} already uses it in this subheading', [modal.pais])">{{ tx(modal.pais) }}</small><small v-else-if="origenCond(k) === 'otros'" class="etiqueta" :title="t('Other countries use it in this subheading')">{{ t('other countries') }}</small></span>
        <FiltroMulti v-if="d.tipo === 'opciones'" :model-value="valorCond(k)" :etiqueta="t('Values')" vacio="any" :opciones="Object.entries(d.ops).map(([valor, texto]) => ({ valor, texto }))" @update:model-value="(v) => ponerCond(k, v)" />
        <Seleccion v-else-if="d.tipo === 'sino'" class="entrada" :value="modal.cond[k] === undefined ? '' : String(modal.cond[k])" @change="ponerCond(k, $event === '' ? '' : $event === 'true')">
          <option value="">{{ t('Any') }}</option><option value="true">{{ t('Yes') }}</option><option value="false">{{ t('No') }}</option>
        </Seleccion>
        <input v-else class="entrada" type="number" min="0" step="0.01" :value="modal.cond[k] ?? ''" @input="ponerCond(k, $event.target.value === '' ? '' : Number($event.target.value))" />
      </div>
    </div>
    <label class="campo mt-chico"><span>{{ t('Note') }}</span><input v-model="modal.nota" class="entrada" maxlength="300" /></label>
    <label class="check mt-chico"><input v-model="modal.activo" type="checkbox" /><span>{{ t('Active (the engine uses it)') }}</span></label>
    <template #pie>
      <button class="btn" @click="modal = null">{{ t('Cancel') }}</button>
      <button class="btn btn-primario" :disabled="ocupado" @click="guardarCodigo">{{ t('Save') }}</button>
    </template>
  </Modal>

  <section v-if="vista === 'notas'">
    <p class="ayuda" style="margin-top: 0">{{ t('General rules of interpretation and the section, chapter and subheading notes of the SAC (HS 2022) for the chapters used by the classification: exclusions, definitions and priority rules. The classification panel shows the ones that apply to the suggested code, starting with the ones that concern the product, and the specialist opinion reads them. Load the official text in force with') }} <b>{{ t('Upload official text') }}</b>.</p>
    <div class="filtros" v-filtros>
      <label class="buscador"><Icono nombre="buscar" :tam="16" /><input v-model="fn.q" type="search" :placeholder="t('Text, chapter or number')" :aria-label="t('Search notes')" @input="buscarN" /></label>
      <FiltroMulti v-model="fn.capitulo" :etiqueta="t('Chapter')" :opciones="CAPITULOS" @change="cargarNotas" />
      <span class="ayuda">{{ t('{0} notes', [notas.items.length]) }}</span>
      <div class="separar fila-flex">
        <BotonesExportar ruta="/aranceles/notas/exportar" :params="{ q: fn.q, capitulo: fn.capitulo.join(',') }" />
        <template v-if="edita">
          <button class="btn" @click="modal = { tipo: 'carga-notas' }"><Icono nombre="importar" />{{ t('Upload official text') }}</button>
          <button class="btn btn-primario" @click="modal = { tipo: 'nota', id: null, ambito: 'capitulo', codigo: '', numero: '', texto: '', capitulos_txt: '', activo: true }"><Icono nombre="mas" />{{ t('Add note') }}</button>
        </template>
      </div>
    </div>
    <div class="tabla-marco">
      <table class="tabla" v-tarjetas>
        <thead><tr><th>{{ t('Note') }}</th><th>{{ t('Text') }}</th><th>{{ t('Applies to chapters') }}</th><th v-if="edita"></th></tr></thead>
        <tbody>
          <tr v-for="n in notas.items" :key="n.id" :class="{ apagado: !n.activo }">
            <td><span class="fuerte">{{ tx(n.codigo) }} · {{ tx(n.numero) }}</span><span class="sub">{{ tx(n.ambito_txt) }}<template v-if="n.fuente !== 'base'"> {{ t('· edited') }}</template></span></td>
            <td class="envolver" style="min-width: 420px; line-height: 1.45">{{ tx(n.texto) }}</td>
            <td>{{ tx(n.capitulos.length ? n.capitulos.join(', ') : t('All')) }}</td>
            <td v-if="edita" class="num" style="white-space: nowrap">
              <button class="btn-icono" :aria-label="t('Edit note {0} {1}', [n.codigo, n.numero])" @click="modal = { tipo: 'nota', ...n, capitulos_txt: n.capitulos.join(', ') }"><Icono nombre="editar" :tam="16" /></button>
              <button class="btn-icono" style="color: var(--error)" :aria-label="t('Delete note {0} {1}', [n.codigo, n.numero])" @click="borrarNota(n)"><Icono nombre="basura" :tam="16" /></button>
            </td>
          </tr>
          <tr v-if="!notas.items.length"><td colspan="4" class="vacio">{{ t('No notes match these filters.') }}</td></tr>
        </tbody>
      </table>
    </div>
  </section>

  <Modal v-if="modal?.tipo === 'nota'" :titulo="tx(modal.id ? t('Note {0} {1}', [modal.codigo, modal.numero]) : t('New SAC note'))" ancho="640px" @cerrar="modal = null">
    <div class="rejilla-campos">
      <label class="campo"><span class="req">{{ t('Kind') }}</span>
        <Seleccion v-model="modal.ambito" :aria-label="t('Kind of note')"><option v-for="(txt, k) in notas.ambitos" :key="k" :value="k">{{ tx(txt) }}</option></Seleccion></label>
      <label class="campo"><span class="req">{{ t('Section or chapter') }}</span><input v-model="modal.codigo" class="entrada" maxlength="10" :placeholder="t('64, XI or RGI')" /></label>
      <label class="campo"><span>{{ t('Note number') }}</span><input v-model="modal.numero" class="entrada" maxlength="20" placeholder="4" /></label>
      <label class="campo"><span>{{ t('Applies to chapters') }}</span><input v-model="modal.capitulos_txt" class="entrada" :placeholder="t('64 (empty = all)')" /></label>
      <label class="campo" style="grid-column: 1 / -1"><span class="req">{{ t('Text') }}</span><textarea v-model="modal.texto" class="entrada" rows="6" maxlength="4000"></textarea></label>
      <label class="check" style="grid-column: 1 / -1"><input v-model="modal.activo" type="checkbox" /><span>{{ t('Active: used by the classification') }}</span></label>
    </div>
    <template #pie>
      <button class="btn" @click="modal = null">{{ t('Cancel') }}</button>
      <button class="btn btn-primario" :disabled="ocupado" @click="guardarNota">{{ t('Save') }}</button>
    </template>
  </Modal>

  <Modal v-if="modal?.tipo === 'sac'" :titulo="tx(modal.id ? t('Subheading {0}', [modal.codigo_txt]) : t('New heading or subheading'))" @cerrar="modal = null">
    <div class="rejilla-campos" style="grid-template-columns: 1fr">
      <label class="campo"><span class="req">{{ t('Code (4 or 6 digits)') }}</span><input v-model="modal.codigo" class="entrada" placeholder="6404.19" /></label>
      <label class="campo"><span class="req">{{ t('Official description') }}</span><textarea v-model="modal.descripcion" class="entrada" rows="3" maxlength="400"></textarea></label>
      <label class="campo"><span>{{ t('Note') }}</span><input v-model="modal.nota" class="entrada" maxlength="300" /></label>
    </div>
    <template #pie>
      <button class="btn" @click="modal = null">{{ t('Cancel') }}</button>
      <button class="btn btn-primario" :disabled="ocupado" @click="guardarSac">{{ t('Save') }}</button>
    </template>
  </Modal>

  <Modal v-if="modal?.tipo === 'pais'" :titulo="tx(modal.id ? `${modal.nombre}` : t('New destination country'))" @cerrar="modal = null">
    <div class="rejilla-campos">
      <label class="campo"><span class="req">{{ t('ISO code') }}</span><input v-model="modal.iso" class="entrada" maxlength="2" placeholder="DO" /></label>
      <label class="campo"><span class="req">{{ t('Name') }}</span><input v-model="modal.nombre" class="entrada" maxlength="80" /></label>
      <label class="campo"><span class="req">{{ t('Digits of its national code') }}</span><input v-model="modal.digitos" type="number" min="6" max="14" class="entrada" /></label>
      <label class="campo"><span>{{ t('Tax') }}</span><input v-model="modal.impuesto" class="entrada" placeholder="VAT 13%" /></label>
      <label class="campo" style="grid-column: 1 / -1"><span>{{ t('Legal basis') }}</span><input v-model="modal.base_legal" class="entrada" maxlength="300" :placeholder="t('Tariff and rule that puts it in force')" /></label>
      <label class="campo" style="grid-column: 1 / -1"><span>{{ t('Note') }}</span><input v-model="modal.nota" class="entrada" maxlength="300" /></label>
    </div>
    <label class="check mt-chico"><input v-model="modal.mcca" type="checkbox" /><span>{{ t('Central American Common Market (shares the SAC codes up to 8–10 digits)') }}</span></label>
    <label class="check mt-chico"><input v-model="modal.activo" type="checkbox" /><span>{{ t('Active: technical sheets ask for its national code') }}</span></label>
    <template #pie>
      <button class="btn" @click="modal = null">{{ t('Cancel') }}</button>
      <button class="btn btn-primario" :disabled="ocupado || !modal.iso || !modal.nombre" @click="guardarPais">{{ t('Save') }}</button>
    </template>
  </Modal>

  <CargaMasiva v-if="modal?.tipo === 'carga-codigos'" :titulo="t('Upload national codes')" ruta="/aranceles/codigos/importar" plantilla="/aranceles/codigos/plantilla"
               :params="{ pais: modal.pais, reemplazar: modal.reemplazar }" @cerrar="modal = null" @cargado="alCargar"
               :ayuda="t('One row per national code with its country, code, duty and the conditions that select it (gender, age, CIF value, footwear style…).')">
    <div class="rejilla-campos mt-chico" style="margin-bottom: 10px">
      <label class="campo"><span>{{ t('Country') }}</span>
        <Seleccion v-model="modal.pais" class="entrada"><option value="">{{ t('The one in the Country column') }}</option><option v-for="p in paises" :key="p.iso" :value="p.iso">{{ tx(p.iso) }} · {{ tx(p.nombre) }}</option></Seleccion></label>
    </div>
    <label v-if="modal.pais" class="check" style="margin-bottom: 10px"><input v-model="modal.reemplazar" type="checkbox" /><span>{{ t('Replace every code of {0} with this file (for a new tariff version)', [modal.pais]) }}</span></label>
  </CargaMasiva>
  <CargaMasiva v-if="modal?.tipo === 'carga-notas'" :titulo="t('Upload SAC legal notes')" ruta="/aranceles/notas/importar" plantilla="/aranceles/notas/plantilla"
               @cerrar="modal = null" @cargado="cargarNotas(); cargarContexto(true)"
               :ayuda="t('A note with the same kind, section or chapter and number is replaced by the text of the file. Use it to load the official text of the SAC in force.')" />
  <CargaMasiva v-if="modal?.tipo === 'carga-sac'" :titulo="t('Upload SAC headings and subheadings')" ruta="/aranceles/sac/importar" plantilla="/aranceles/sac/plantilla"
               @cerrar="modal = null" @cargado="alCargar" :ayuda="t('Codes already loaded are updated with the new text.')" />
</template>

<style scoped>
.sub-mod { margin-bottom: 10px; }
.hermanos { border: 1px solid var(--linea); border-radius: var(--radio); padding: 10px 12px; margin: 8px 0 12px; background: var(--superficie-2); font-size: 0.84rem; }
.hermanos ul { margin: 6px 0 0; padding-inline-start: 18px; display: flex; flex-direction: column; gap: 3px; }
.hermanos li.actual { font-weight: 650; }
.conds .campo > span .etiqueta { margin-inline-start: 6px; font-size: 0.66rem; }
.sub-mod .pildora { text-decoration: none; }
.paises-resumen { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 4px; }
.pais-tarjeta { display: flex; align-items: center; gap: 10px; border: 1px solid var(--linea); background: var(--superficie); border-radius: 10px; padding: 8px 12px; cursor: pointer; font: inherit; text-align: start; color: var(--tinta); }
.pais-tarjeta:hover { border-color: var(--acento); }
.pais-tarjeta.elegido { border-color: var(--acento); background: var(--acento-claro); }
.pais-tarjeta.inactivo { opacity: 0.55; }
.pais-tarjeta.nuevo { border-style: dashed; color: var(--acento-texto); font-weight: 600; }
.pais-tarjeta .iso { font-weight: 800; font-stretch: 115%; font-size: 1.05rem; color: var(--acento-texto); }
.pt-datos b { display: block; font-size: 0.86rem; }
.pt-datos small { color: var(--tinta-3); font-size: 0.76rem; }
.tabla :deep(.celda)::placeholder { color: var(--tinta-3); font-weight: 400; }
.cond { font-size: 0.84rem; color: var(--tinta-2); min-width: 200px; }
tr.apagada td { opacity: 0.6; }
.paises-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 14px; }
@media (max-width: 720px) {
  .paises-resumen { display: grid; grid-template-columns: 1fr 1fr; }
  .pais-tarjeta { min-width: 0; }
  .paises-grid { grid-template-columns: minmax(0, 1fr); }
}
.paises-grid .panel + .panel { margin-top: 0; }
.pais-panel.inactivo { opacity: 0.65; }
.conds { display: grid; grid-template-columns: repeat(auto-fill, minmax(210px, 1fr)); gap: 10px 14px; margin-top: 8px; }
</style>
