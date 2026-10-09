<script setup>
import { t, tx } from '@/i18n/index.js'
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue'
import Seleccion from '@/componentes/Seleccion.vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '@/nucleo/api'
import BarraSeleccion from '@/componentes/BarraSeleccion.vue'
import BotonesExportar from '@/componentes/BotonesExportar.vue'
import CargaMasiva from '@/componentes/CargaMasiva.vue'
import CeldaEditable from '@/componentes/CeldaEditable.vue'
import FiltroMulti from '@/componentes/FiltroMulti.vue'
import Icono from '@/componentes/Icono.vue'
import Modal from '@/componentes/Modal.vue'
import Paginacion from '@/componentes/Paginacion.vue'
import ThOrden from '@/componentes/ThOrden.vue'
import PanelArbol from '@/modulos/clasificacion/componentes/PanelArbol.vue'
import PanelCapitulos from '@/modulos/clasificacion/componentes/PanelCapitulos.vue'
import PanelRegulaciones from '@/modulos/clasificacion/componentes/PanelRegulaciones.vue'
import PanelImpuestos from '@/modulos/clasificacion/componentes/PanelImpuestos.vue'
import PanelFuentes from '@/modulos/clasificacion/componentes/PanelFuentes.vue'
import PanelIntegridad from '@/modulos/clasificacion/componentes/PanelIntegridad.vue'
import PanelConocimiento from '@/modulos/clasificacion/componentes/PanelConocimiento.vue'
import PanelImportacion from '@/modulos/clasificacion/componentes/PanelImportacion.vue'
import { cargarContexto } from '@/modulos/clasificacion/useClasificacion'
import { digits, fmtPais } from '@/modulos/clasificacion/formato.js'
import { siguienteOrden } from '@/composables/useTabla'
import { puede } from '@/stores/sesion'
import { avisar, errorApi } from '@/stores/ui'
import { fmtNum, useSeleccion } from '@/nucleo/utils'
import { filasDefecto } from '@/stores/preferencias'

// Arancel: países destino (con sus dígitos), subpartidas SAC y códigos
// nacionales con las condiciones que los eligen. Todo editable, con carga
// desde Excel y exportación con los filtros de la pantalla.
const route = useRoute()
const router = useRouter()
const edita = puede('aranceles.editar')
// La configuración del motor vive en Familias de producto: los enlaces anteriores llevan allá
const DEL_MOTOR = ['dominios', 'atributos', 'materiales', 'busqueda', 'reglas']
const vista = ref(route.query.vista || 'arbol')
if (DEL_MOTOR.includes(vista.value)) router.replace({ path: '/familias', query: { vista: vista.value } })
const paises = ref([])
const meta = ref({ condiciones: {}, fuentes: {} })
const modal = ref(null)
const ocupado = ref(false)
const sel = useSeleccion()

const opcionesPais = computed(() => paises.value.map((p) => ({ valor: p.iso, texto: `${p.iso} · ${p.nombre}` })))
// Versiones oficiales a las que puede pertenecer una línea del país (la nacional o la regional del SAC)
// (las publicadas no cambian: solo borrador o dinámica)
const versionesDe = (iso) => (meta.value.versiones_oficiales || []).filter((v) => v.fuente && [iso, 'REGIONAL'].includes(v.ambito)
  && ['BORRADOR', 'DINAMICA'].includes(v.estado))
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
const longitudesDe = (iso) => paises.value.find((p) => p.iso === iso)?.longitudes_validas || [digitosDe(iso)]

async function guardarCampo(x, campo, valor) {
  await api.put(`/aranceles/codigos/${x.id}`, { pais: x.pais, codigo: x.codigo, descripcion: x.descripcion, dai: x.dai, cond: x.cond, prio: x.prio, nota: x.nota, activo: x.activo, [campo]: valor })
  x[campo] = valor
  cargarContexto(true)
}
function nuevoCodigo() {
  modal.value = { tipo: 'codigo', id: null, pais: fc.pais[0] || paises.value[0]?.iso, codigo: '', descripcion: '', dai: '', prio: 0, nota: '', activo: true, cond: {}, version: '' }
}
async function quitarOverride(m) {
  try {
    await api.del(`/aranceles/codigos/${m.id}/override`)
    modal.value = null
    avisar(t('Back to the official line.'))
    cargarCodigos()
  } catch (e) {
    errorApi(e)
  }
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
    // Una línea oficial no se modifica: descripción, nota y activo se guardan como ajuste propio (con motivo)
    const cuerpo = { pais: m.pais, codigo: m.codigo, descripcion: m.descripcion, dai: m.dai, cond: m.cond, prio: Number(m.prio) || 0, nota: m.nota, activo: m.activo,
      motivo: m.oficial ? m.motivo || null : null }
    if (!m.id) Object.assign(cuerpo, { version: m.version || null, fuente: versionesDe(m.pais).find((v) => v.codigo === m.version)?.fuente || null,
      vigente_desde: m.vigente_desde || null })
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
    const cuerpo = { ambito: m.ambito, codigo: m.codigo, numero: m.numero, texto: m.texto, activo: m.activo, motivo: m.motivo || null,
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
  if (!confirm(n.oficial ? t('Deactivate official note {0} {1}? It stays in the official tariff.', [n.codigo, n.numero]) : t('Delete note {0} {1}?', [n.codigo, n.numero]))) return
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
    const cuerpo = { codigo: m.codigo, descripcion: m.descripcion, nota: m.nota, activo: m.activo, motivo: m.motivo || null }
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
  if (!window.confirm(t('Remove the custom text of {0} and go back to the official one?', [x.codigo_txt]))) return
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
    // Longitudes válidas del código nacional (p. ej. 10, 12): el código se valida contra ellas y nunca se recorta
    const longitudes = String(m.longitudes_txt || '').split(/[\s,;]+/).filter(Boolean).map(Number)
    const cuerpo = { iso: m.iso, nombre: m.nombre, digitos: Number(m.digitos), mcca: !!m.mcca, impuesto: m.impuesto, nota: m.nota, base_legal: m.base_legal || null,
      activo: m.activo, longitudes, nivel_base: m.nivel_base || null, modelo_arancel: m.modelo_arancel || null, contexto: m.contexto || null, fuente: m.fuente || null }
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

// Menú lateral en tres áreas separadas: lo que publicó una fuente oficial, la
// configuración del motor (no es dato oficial) y lo que sabe la empresa (solo ordena)
const MENU = computed(() => [
  { titulo: t('Official data'), items: [['fuentes', t('Sources and versions'), 'historial'], ['arbol', t('Tariff tree'), 'ruta'],
    ['paises', t('Countries'), 'globo', paises.value.length],
    ['codigos', t('National codes'), 'etiqueta', fmtNum(paises.value.reduce((a, p) => a + (p.codigos || 0), 0))],
    ['sac', t('SAC headings and subheadings'), 'base'], ['notas', t('Legal notes'), 'archivo'], ['impuestos', t('Taxes'), 'moneda'],
    ['regulaciones', t('Regulations'), 'candado'], ['capitulos', t('Chapters'), 'lista'], ['importacion', t('Data import'), 'importar'],
    ['integridad', t('Tariff data integrity'), 'check']] },
  { titulo: t('Company knowledge'), items: [['conocimiento', t('History, decisions and keywords'), 'usuarios']] },
])

// En pantallas chicas el menú es una fila con desplazamiento: se centra la sección activa
const menu = ref(null)
function centrarMenu() {
  nextTick(() => {
    const nav = menu.value
    const el = nav?.querySelector('[aria-current="page"]')
    if (nav && el && nav.scrollWidth > nav.clientWidth) nav.scrollLeft = el.offsetLeft - (nav.clientWidth - el.clientWidth) / 2
  })
}

function cambiarVista(v) {
  vista.value = v
  centrarMenu()
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
  centrarMenu()
  await cargarBase()
  if (vista.value === 'sac') cargarSac()
  else if (vista.value === 'notas') cargarNotas()
  else if (vista.value === 'codigos') cargarCodigos()
})
watch(() => fc.size, recargarC)
watch(() => fs.size, recargarS)
</script>

<template>
  <div class="pagina-cabeza">
    <div>
      <div class="pestanas-pildora sub-mod">
        <router-link to="/productos" class="pildora">{{ t('Products') }}</router-link>
        <router-link v-if="puede('clasificacion.ver')" to="/familias" class="pildora">{{ t('Product families') }}</router-link>
        <span class="pildora" aria-current="page" aria-pressed="true">{{ t('Tariff schedule') }}</span>
      </div>
      <h1>{{ t('Tariff schedule') }}</h1>
      <p>{{ t('Official data (only what an official source published, with its version) and company knowledge (history that only orders the official candidates).') }}</p>
      <router-link v-if="puede('clasificacion.ver')" to="/familias" class="enlace-motor"><Icono nombre="capas" :tam="15" />{{ t('Product families, questions and rules are set up in Product families') }}<Icono nombre="derecha" :tam="14" /></router-link>
    </div>
  </div>

  <div class="paises-resumen">
    <button v-for="p in paises" :key="p.iso" type="button" class="pais-tarjeta" :class="{ inactivo: !p.activo, elegido: vista === 'codigos' && fc.pais.includes(p.iso) }"
            @click="fc.pais = fc.pais.includes(p.iso) ? fc.pais.filter((x) => x !== p.iso) : [...fc.pais, p.iso]; cambiarVista('codigos')">
      <span class="iso">{{ tx(p.iso) }}</span>
      <span class="pt-datos"><b>{{ tx(p.nombre) }}</b><small>{{ t('{0} digits{1} · {2} codes', [p.digitos, p.mcca ? ' · CACM' : '', fmtNum(p.codigos)]) }}</small></span>
    </button>
    <button v-if="edita" type="button" class="pais-tarjeta nuevo" @click="modal = { tipo: 'pais', id: null, iso: '', nombre: '', digitos: 10, mcca: false, impuesto: '', nota: '', base_legal: '', activo: true, longitudes_txt: '', nivel_base: '', modelo_arancel: '', contexto: '', fuente: '' }">
      <Icono nombre="mas" :tam="16" /> {{ t('Add country') }}
    </button>
  </div>

  <div class="layout-lateral">
  <nav ref="menu" class="menu-lateral" :aria-label="t('Tariff schedule sections')">
    <template v-for="g in MENU" :key="g.titulo">
      <p class="menu-grupo">{{ tx(g.titulo) }}</p>
      <button v-for="[k, l, icono, n] in g.items" :key="k" type="button" class="menu-item" :aria-current="vista === k ? 'page' : undefined" @click="cambiarVista(k)">
        <Icono :nombre="icono" :tam="16" /><span class="menu-txt">{{ tx(l) }}</span><span v-if="n != null" class="cuenta">{{ tx(n) }}</span>
      </button>
    </template>
  </nav>
  <div class="layout-contenido">
  <PanelArbol v-if="vista === 'arbol'" />
  <PanelCapitulos v-else-if="vista === 'capitulos'" />
  <PanelRegulaciones v-else-if="vista === 'regulaciones'" :paises="paises" />
  <PanelImpuestos v-else-if="vista === 'impuestos'" :paises="paises" />
  <PanelFuentes v-else-if="vista === 'fuentes'" />
  <PanelIntegridad v-else-if="vista === 'integridad'" />
  <PanelConocimiento v-else-if="vista === 'conocimiento'" :edita="edita" />
  <PanelImportacion v-else-if="vista === 'importacion'" @cargado="cargarBase" />

  <!-- Códigos nacionales -->
  <section v-if="vista === 'codigos'">
    <div class="filtros" v-filtros>
      <label class="buscador"><Icono nombre="buscar" :tam="16" /><input v-model="fc.q" type="search" :placeholder="t('Code or description')" :aria-label="t('Search')" @input="buscarC" /></label>
      <FiltroMulti v-model="fc.pais" :etiqueta="t('Country')" :opciones="opcionesPais" @change="recargarC" />
      <FiltroMulti v-model="fc.capitulo" :etiqueta="t('Chapter')" :opciones="CAPITULOS" @change="recargarC" />
      <FiltroMulti v-model="fc.fuente" :etiqueta="t('Official source')" :opciones="(meta.fuentes_oficiales || []).map((f) => ({ valor: f.codigo, texto: f.texto }))" @change="recargarC" />
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
              <template v-if="x.oficial">{{ tx(x.descripcion || '—') }}<span v-if="x.override" class="etiqueta acento" :title="tx(t('Official text: {0}', [x.descripcion_oficial || '—']))">{{ t('company override') }}</span></template>
              <CeldaEditable v-else-if="edita" :valor="x.descripcion" vacia-texto="—" :etiqueta="t('Description of {0}', [x.codigo_txt])" :guardar="(v) => guardarCampo(x, 'descripcion', v)" />
              <template v-else>{{ tx(x.descripcion || '—') }}</template>
            </td>
            <td class="num" style="width: 90px">
              <CeldaEditable v-if="edita && !x.oficial" :valor="x.dai" vacia-texto="—" :etiqueta="t('Duty of {0}', [x.codigo_txt])" :guardar="(v) => guardarCampo(x, 'dai', v)" />
              <template v-else>{{ tx(x.dai ?? '—') }}</template>
            </td>
            <td class="cond">{{ tx(x.cond_txt) }}<span v-if="x.prio" class="etiqueta">{{ t('priority {0}', [x.prio]) }}</span></td>
            <td><span class="etiqueta ok" :title="tx(x.autoridad || '')">{{ tx(x.fuente_oficial || t('No source')) }}</span> <small class="apagado">{{ tx(x.version || '') }}</small><span v-if="!x.activo" class="etiqueta">{{ t('Inactive') }}</span></td>
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
        </template>
      </div>
    </div>
    <div class="tabla-marco tabla-fija">
      <table class="tabla" v-tarjetas>
        <thead><tr><th>{{ t('Code') }}</th><th>{{ t('Description') }}</th><th class="num">{{ t('National codes') }}</th><th>{{ t('Source') }}</th><th v-if="edita"></th></tr></thead>
        <tbody>
          <tr v-for="x in sac.items" :key="x.id">
            <td :class="x.codigo.length === 4 ? 'fuerte' : ''"><span class="codigo-sac">{{ tx(x.codigo_txt) }}</span></td>
            <td :class="{ fuerte: x.codigo.length === 4 }">{{ tx(x.descripcion) }}<span v-if="x.nota" class="sub">{{ tx(x.nota) }}</span>
              <details v-if="x.custom" class="oficial-txt"><summary>{{ t('Official text') }}</summary>{{ tx(x.descripcion_oficial) }}</details></td>
            <td class="num"><button v-if="x.nacionales" type="button" class="enlace" @click="verCodigosDe(x)">{{ tx(x.nacionales) }}</button><span v-else class="apagado">—</span></td>
            <td><span class="etiqueta" :class="x.custom ? 'acento' : 'ok'">{{ tx(x.custom ? t('Custom over official') : t('Official')) }}</span></td>
            <td v-if="edita" class="num" style="white-space: nowrap">
              <button class="btn-icono" :aria-label="t('Edit {0}', [x.codigo_txt])" @click="modal = { tipo: 'sac', ...x, motivo: '' }"><Icono nombre="editar" :tam="16" /></button>
              <button v-if="x.custom" class="btn-icono" :title="t('Back to the official text')" :aria-label="t('Back to the official text')" @click="borrarSac(x)"><Icono nombre="historial" :tam="16" /></button>
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
        <div><h2>{{ tx(p.iso) }} · {{ tx(p.nombre) }}</h2><p>{{ t('{0}-digit national codes{1}', [(p.longitudes?.length ? p.longitudes : [p.digitos]).join(' / '), p.mcca ? t(' · Central American Common Market') : '']) }}</p></div>
        <span v-if="!p.activo" class="etiqueta">{{ t('Inactive') }}</span>
      </div>
      <div class="doc-meta" style="margin-top: 0">
        <span>{{ t('Codes loaded') }} <b>{{ fmtNum(p.codigos) }}</b></span>
        <span v-if="p.impuesto">{{ t('Tax') }} <b>{{ tx(p.impuesto) }}</b></span>
      </div>
      <p class="mt-chico"><span class="etiqueta" :class="{ ok: p.datos_oficiales === 'OK', aviso: p.datos_oficiales !== 'OK' }">{{ tx(p.datos_oficiales_txt) }}</span></p>
      <p v-if="p.modelo_arancel" class="ayuda mt-chico"><b>{{ t('Tariff model:') }}</b> {{ tx(p.modelo_arancel) }}<template v-if="p.fuente"> · {{ t('Primary source {0}', [p.fuente]) }}</template></p>
      <p v-if="p.base_legal" class="ayuda mt-chico"><b>{{ t('Legal basis:') }}</b> {{ tx(p.base_legal) }}</p>
      <p v-if="p.nota" class="ayuda mt-chico">{{ tx(p.nota) }}</p>
      <div class="fila-flex mt-chico" style="gap: 6px">
        <button class="btn btn-chico" @click="fc.pais = [p.iso]; cambiarVista('codigos')"><Icono nombre="lista" :tam="14" />{{ t('See codes') }}</button>
        <template v-if="edita">
          <button class="btn btn-chico" @click="cargarPais(p)"><Icono nombre="importar" :tam="14" />{{ t('Upload codes') }}</button>
          <button class="btn btn-chico btn-fantasma" @click="modal = { tipo: 'pais', ...p, longitudes_txt: (p.longitudes || []).join(', ') }"><Icono nombre="editar" :tam="14" />{{ t('Edit') }}</button>
          <button v-if="!p.codigos" class="btn btn-chico btn-fantasma" style="color: var(--error)" @click="borrarPais(p)"><Icono nombre="basura" :tam="14" />{{ t('Delete') }}</button>
        </template>
      </div>
    </article>
  </section>

  <!-- Ventanas -->
  <Modal v-if="modal?.tipo === 'codigo'" :titulo="tx(modal.id ? t('National code {0}', [modal.codigo]) : t('New national code'))" ancho="760px" @cerrar="modal = null">
    <div class="rejilla-campos">
      <label class="campo"><span class="req">{{ t('Country') }}</span>
        <Seleccion v-model="modal.pais" class="entrada" :disabled="modal.oficial"><option v-for="p in paises" :key="p.iso" :value="p.iso">{{ tx(p.iso) }} · {{ tx(p.nombre) }}</option></Seleccion></label>
      <label class="campo"><span class="req">{{ t('Code ({0} digits)', [longitudesDe(modal.pais).join(' / ')]) }}</span><input v-model="modal.codigo" class="entrada" :disabled="modal.oficial" :placeholder="tx('0'.repeat(digitosDe(modal.pais)))" /></label>
      <label class="campo"><span>{{ t('Duty (DAI %)') }}</span><input v-model="modal.dai" class="entrada" :disabled="modal.oficial" /></label>
      <label class="campo"><span>{{ t('Priority') }}</span><input v-model="modal.prio" type="number" min="0" max="99" class="entrada" /></label>
      <label class="campo" style="grid-column: 1 / -1"><span>{{ t('Description') }}</span><input v-model="modal.descripcion" class="entrada" maxlength="300" /></label>
      <label v-if="!modal.id" class="campo" style="grid-column: 1 / -1"><span class="req">{{ t('Official version it comes from') }}</span>
        <Seleccion v-model="modal.version" class="entrada"><option value="">{{ t('Choose…') }}</option>
          <option v-for="v in versionesDe(modal.pais)" :key="v.codigo" :value="v.codigo">{{ tx(v.texto) }}{{ v.fuente ? ` · ${v.fuente}` : '' }}</option></Seleccion>
        <small class="ayuda">{{ t('National lines are official data: they are created only from a published source and version. Your own preferences go to the company history.') }}</small></label>
      <label v-if="!modal.id && modal.version && !versionesDe(modal.pais).find((v) => v.codigo === modal.version)?.vigente_desde" class="campo">
        <span class="req">{{ t('Valid from (as published)') }}</span><input v-model="modal.vigente_desde" type="date" class="entrada" /></label>
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
    <template v-if="modal.oficial">
      <p class="nota info mt-chico"><Icono nombre="info" /><span>{{ t('Official line of the tariff in force: its country, code and duty do not change. Description, note and active are saved as your company override, with the reason.') }}</span></p>
      <label class="campo mt-chico"><span>{{ t('Reason for the override') }}</span><input v-model="modal.motivo" class="entrada" maxlength="300" :placeholder="t('E.g. internal purchasing description')" /></label>
      <button v-if="modal.override" type="button" class="btn-texto mt-chico" @click="quitarOverride(modal)">{{ t('Remove the company override (back to the official text)') }}</button>
    </template>
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
            <td><span class="fuerte">{{ tx(n.codigo) }} · {{ tx(n.numero) }}</span><span class="sub">{{ tx(n.ambito_txt) }}</span>
              <span class="etiqueta" :class="n.custom ? 'acento' : n.oficial ? 'ok' : 'aviso'" :title="tx(n.tipo_txt)">{{ tx(n.custom ? t('Custom over official') : n.oficial ? t('Official text') : n.tipo_fuente === 'CLASSIFIER_GUIDANCE' ? t('Classifier summary') : t('Internal guidance')) }}</span></td>
            <td class="envolver" style="min-width: 420px; line-height: 1.45">{{ tx(n.texto) }}
              <details v-if="n.texto_oficial" class="oficial-txt"><summary>{{ t('Official text') }}</summary>{{ tx(n.texto_oficial) }}</details></td>
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
      <template v-if="modal.oficial">
        <p class="ayuda" style="grid-column: 1 / -1">{{ t('This is an official note: its text is never replaced. Your change is saved as a custom layer with its reason, and you can go back to the official text.') }}</p>
        <label class="campo" style="grid-column: 1 / -1"><span class="req">{{ t('Reason') }}</span><input v-model="modal.motivo" class="entrada" maxlength="300" /></label>
      </template>
    </div>
    <template #pie>
      <button class="btn" @click="modal = null">{{ t('Cancel') }}</button>
      <button class="btn btn-primario" :disabled="ocupado || (modal.oficial && !modal.motivo)" @click="guardarNota">{{ t('Save') }}</button>
    </template>
  </Modal>

  <Modal v-if="modal?.tipo === 'sac'" :titulo="t('Subheading {0}', [modal.codigo_txt])" @cerrar="modal = null">
    <p class="ayuda">{{ t('The official text comes from the tariff in force and is never edited. Here you add an internal description or note (custom layer) with its reason.') }}</p>
    <div class="rejilla-campos" style="grid-template-columns: 1fr">
      <div class="campo"><span>{{ t('Official text') }}</span><p class="oficial-fijo">{{ tx(modal.descripcion_oficial) }}</p></div>
      <label class="campo"><span>{{ t('Internal description') }}</span><textarea v-model="modal.descripcion" class="entrada" rows="3" maxlength="400"></textarea></label>
      <label class="campo"><span>{{ t('Internal note') }}</span><input v-model="modal.nota" class="entrada" maxlength="300" /></label>
      <label class="campo"><span class="req">{{ t('Reason') }}</span><input v-model="modal.motivo" class="entrada" maxlength="300" /></label>
    </div>
    <template #pie>
      <button class="btn" @click="modal = null">{{ t('Cancel') }}</button>
      <button class="btn btn-primario" :disabled="ocupado || !modal.motivo" @click="guardarSac">{{ t('Save') }}</button>
    </template>
  </Modal>

  <Modal v-if="modal?.tipo === 'pais'" :titulo="tx(modal.id ? `${modal.nombre}` : t('New destination country'))" @cerrar="modal = null">
    <div class="rejilla-campos">
      <label class="campo"><span class="req">{{ t('ISO code') }}</span><input v-model="modal.iso" class="entrada" maxlength="2" placeholder="DO" /></label>
      <label class="campo"><span class="req">{{ t('Name') }}</span><input v-model="modal.nombre" class="entrada" maxlength="80" /></label>
      <label class="campo"><span class="req">{{ t('Digits of its national code') }}</span><input v-model="modal.digitos" type="number" min="6" max="14" class="entrada" /></label>
      <label class="campo"><span>{{ t('Tax') }}</span><input v-model="modal.impuesto" class="entrada" placeholder="VAT 13%" /></label>
      <label class="campo"><span>{{ t('Valid lengths') }}</span><input v-model="modal.longitudes_txt" class="entrada" placeholder="10, 12" :title="t('Every length its national codes can have. Empty: 8 to 14 digits.')" /></label>
      <label class="campo"><span>{{ t('National precision hangs from') }}</span>
        <Seleccion v-model="modal.nivel_base" class="entrada"><option value="">—</option><option value="HS6">{{ t('HS6 (6 digits)') }}</option><option value="SAC8">{{ t('Regional SAC (8 digits)') }}</option></Seleccion></label>
      <label class="campo"><span>{{ t('Tariff model') }}</span><input v-model="modal.modelo_arancel" class="entrada" maxlength="120" :placeholder="t('E.g. regional SAC + national precision')" /></label>
      <label class="campo"><span>{{ t('Context') }}</span><input v-model="modal.contexto" class="entrada" maxlength="120" /></label>
      <label class="campo"><span>{{ t('Official source') }}</span>
        <Seleccion v-model="modal.fuente" class="entrada"><option value="">—</option><option v-for="f in meta.fuentes_oficiales || []" :key="f.codigo" :value="f.codigo">{{ tx(f.texto) }}</option></Seleccion></label>
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
               :params="{ pais: modal.pais, reemplazar: modal.reemplazar, version: modal.version, fuente: versionesDe(modal.pais).find((v) => v.codigo === modal.version)?.fuente,
                          vigente_desde: modal.vigente_desde }"
               @cerrar="modal = null" @cargado="alCargar"
               :ayuda="t('One row per official national line with its country, code and duty, from the published tariff of that version. Optional columns hold the conditions the engine uses to choose it.')">
    <div class="rejilla-campos mt-chico" style="margin-bottom: 10px">
      <label class="campo"><span>{{ t('Country') }}</span>
        <Seleccion v-model="modal.pais" class="entrada"><option value="">{{ t('The one in the Country column') }}</option><option v-for="p in paises" :key="p.iso" :value="p.iso">{{ tx(p.iso) }} · {{ tx(p.nombre) }}</option></Seleccion></label>
      <label class="campo"><span class="req">{{ t('Official version it comes from') }}</span>
        <Seleccion v-model="modal.version" class="entrada"><option value="">{{ t('Choose…') }}</option>
          <option v-for="v in versionesDe(modal.pais)" :key="v.codigo" :value="v.codigo">{{ tx(v.texto) }}{{ v.fuente ? ` · ${v.fuente}` : '' }}</option></Seleccion></label>
      <label v-if="modal.version && !versionesDe(modal.pais).find((v) => v.codigo === modal.version)?.vigente_desde" class="campo">
        <span class="req">{{ t('Valid from (as published)') }}</span><input v-model="modal.vigente_desde" type="date" class="entrada" /></label>
    </div>
    <label v-if="modal.pais" class="check" style="margin-bottom: 10px"><input v-model="modal.reemplazar" type="checkbox" /><span>{{ t('Replace every code of {0} with this file (for a new tariff version)', [modal.pais]) }}</span></label>
  </CargaMasiva>
  <CargaMasiva v-if="modal?.tipo === 'carga-notas'" :titulo="t('Upload SAC legal notes')" ruta="/aranceles/notas/importar" plantilla="/aranceles/notas/plantilla"
               @cerrar="modal = null" @cargado="cargarNotas(); cargarContexto(true)"
               :ayuda="t('A note with the same kind, section or chapter and number is replaced by the text of the file. Use it to load the official text of the SAC in force.')" />
  <CargaMasiva v-if="modal?.tipo === 'carga-sac'" :titulo="t('Upload SAC headings and subheadings')" ruta="/aranceles/sac/importar" plantilla="/aranceles/sac/plantilla"
               @cerrar="modal = null" @cargado="alCargar" :ayuda="t('Codes already loaded are updated with the new text.')" />
  </div>
  </div>
</template>

<style scoped>
.oficial-txt { font-size: 0.8rem; color: var(--tinta-3); margin-top: 4px; }
.oficial-txt summary { cursor: pointer; }
.oficial-fijo { margin: 0; padding: 8px 10px; background: var(--superficie-2); border-radius: var(--radio); font-size: 0.88rem; }
.enlace-motor { display: inline-flex; align-items: center; gap: 6px; margin-top: 6px; font-size: 0.88rem; font-weight: 600; color: var(--acento-texto); text-decoration: none; }
.enlace-motor:hover { text-decoration: underline; }
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
