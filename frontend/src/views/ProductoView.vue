<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { onBeforeRouteLeave, useRouter } from 'vue-router'
import { api } from '../api'
import EstadoBadge from '../components/EstadoBadge.vue'
import FichaTecnica from '../components/ficha/FichaTecnica.vue'
import GenericoModal from '../components/GenericoModal.vue'
import Icono from '../components/Icono.vue'
import Modal from '../components/Modal.vue'
import { M, calcular, cargarContexto, fichaDe, fichaParaGuardar, resultadoServidor } from '../clasificacion/useClasificacion'
import { puede } from '../stores/sesion'
import { avisar, errorApi } from '../stores/ui'
import { fmtFecha, fmtFechaHora } from '../utils'

// Ficha técnica del producto (estilo-color) y su clasificación arancelaria.
// El motor corre en el navegador mientras se escribe; el servidor guarda la
// ficha, valida la aprobación y lleva el código a la OC y la factura.
const props = defineProps({ id: [String, Number] })
const router = useRouter()

const p = ref(null)
const ctx = ref(null)
const opciones = ref({ paises: [] })
const f = reactive({})
const pestana = ref('ficha')
const ocupado = ref(false)
const base = ref('')
const codOficial = ref('')
const otroCodigo = ref('')
const modal = ref(null)
const verRazones = ref(false)
const agregarTallas = ref(false)
const cargas = ref(0) // vuelve a montar el formulario tras guardar

const aprobado = computed(() => ['aprobado', 'corregido'].includes(p.value?.estado))
const puedeEditar = computed(() => !!p.value && !aprobado.value && puede('producto.ficha'))
const puedeAprobar = computed(() => !!p.value?.puede_aprobar)

const r = computed(() => (ctx.value && p.value && f.id ? calcular(f, ctx.value, codOficial.value) : null))
const codigo = computed(() => (aprobado.value ? p.value.codigo : codOficial.value || M.fmtCode(r.value?.o.completo || r.value?.o.codigo || '')))
const codigo6 = computed(() => M.digits(codigo.value).slice(0, 6))

// ---- Carga ---------------------------------------------------------------
function tomar(det) {
  p.value = det
  for (const k of Object.keys(f)) delete f[k]
  Object.assign(f, fichaDe(det))
  codOficial.value = ''
  cargas.value++
  base.value = instantanea()
}
function instantanea() {
  return JSON.stringify([fichaParaGuardar(f), f.tipo, f.descArchivo, f.generico, f.origen, f.alertasOk, f.partidas])
}
const sucio = computed(() => !!p.value && instantanea() !== base.value)

async function recargarContexto() {
  ctx.value = await cargarContexto(true)
}

async function cargar() {
  try {
    const [det, c, op] = await Promise.all([api.get(`/productos/${props.id}`), cargarContexto(), api.get('/productos/opciones')])
    ctx.value = c
    opciones.value = op
    tomar(det)
  } catch (e) {
    errorApi(e)
    if (e.status === 404) router.replace('/productos')
  }
}

// ---- Clasificación -------------------------------------------------------
const alertas = computed(() => (r.value ? M.alertasVivas(r.value.o.alertas || [], f.alertasOk) : []))
// Lo que subiría la confianza (no bloquea la ficha)
const pistas = computed(() => (r.value ? [...(r.value.o.faltantes || []), ...(r.value.o.avisos || [])].filter((x) => !r.value.faltan.includes(x)).slice(0, 3) : []))
const errores = computed(() => alertas.value.filter((a) => a.nivel === 'error'))
const confNivel = computed(() => ({ high: 3, medium: 2, low: 1 })[r.value?.o.confianza] || 0)

function revisada(a) {
  f.alertasOk = [...new Set([...(f.alertasOk || []), M.alertaKey(a.msg)])]
}
function usarCodigo(c) {
  codOficial.value = M.fmtCode(c)
  otroCodigo.value = ''
}
function aplicarOtro() {
  const d = M.digits(otroCodigo.value)
  if (d.length < 6) return avisar('Write at least the 6-digit subheading.', 'error')
  usarCodigo(d)
}

const paises = computed(() => {
  if (!ctx.value) return []
  return ctx.value.destinos.map((d) => {
    if (aprobado.value) {
      const x = p.value.partidas[d.iso] || {}
      return { ...d, codigo: x.codigo, dai: x.dai, estado: x.codigo ? 'ok' : 'sin_codigo', fuente: x.fuente, manual: x.manual }
    }
    return { ...d, ...(r.value?.partidas[d.iso] || { estado: 'sin_codigo' }) }
  })
})
const paisesOk = computed(() => paises.value.filter((x) => ['ok', 'auto'].includes(x.estado) && M.digits(x.codigo).length >= x.digitos).length)
function codigoPais(iso, c) {
  f.partidas = { ...(f.partidas || {}), [iso]: { codigo: M.digits(c), manual: true } }
}
// Código nacional escrito directo en la tabla de destinos: se aplica al salir
// del campo o con Enter si tiene los dígitos del país y empieza con la subpartida
const errPais = reactive({})
function escribirPais(x, el) {
  const c = M.digits(el.value)
  errPais[x.iso] = ''
  if (!c) {
    if (x.manual) quitarManual(x.iso)
    else el.value = x.codigo ? M.fmtPais(x.codigo, x.digitos) : ''
    return
  }
  if (c === M.digits(x.codigo || '')) {
    el.value = M.fmtPais(c, x.digitos)
    return
  }
  if (!c.startsWith(codigo6.value)) errPais[x.iso] = `Must start with ${M.fmtCode(codigo6.value)}`
  else if (c.length !== x.digitos) errPais[x.iso] = `${x.digitos} digits (${c.length} typed)`
  else {
    codigoPais(x.iso, c)
    el.value = M.fmtPais(c, x.digitos)
  }
}
function quitarManual(iso) {
  const { [iso]: _, ...resto } = f.partidas || {}
  f.partidas = resto
}

// ---- Guardar y flujo ---------------------------------------------------------
function cuerpoFicha() {
  const s = r.value.s
  return {
    version: p.value.version,
    tipo: f.tipo || null,
    ficha: fichaParaGuardar(s),
    nombre: f.descArchivo || '',
    pais_origen: f.origen || '',
    descripcion_aduana: s.descManual ? s.desc || '' : null,
    descripcion_comercial: s.comManual ? s.descCom || '' : null,
    alertas_ok: f.alertasOk || [],
    resultado: resultadoServidor(r.value),
  }
}

async function guardar(silencioso = false) {
  if (!puedeEditar.value) return
  ocupado.value = true
  try {
    tomar(await api.put(`/productos/${p.value.id}/ficha`, cuerpoFicha()))
    if (!silencioso) avisar(p.value.ficha_completa ? 'Technical sheet saved. It is ready for review.' : 'Technical sheet saved.')
    return true
  } catch (e) {
    errorApi(e)
    return false
  } finally {
    ocupado.value = false
  }
}

async function aprobar() {
  if (sucio.value && !(await guardar(true))) return
  const cod = codOficial.value || codigo.value
  ocupado.value = true
  try {
    const rr = calcular(f, ctx.value, cod)
    tomar(await api.post(`/productos/${p.value.id}/aprobar`, { version: p.value.version, codigo: M.digits(cod), partidas: resultadoServidor(rr).partidas }))
    avisar(`Approved as ${p.value.codigo}. Orders and invoices now use it.`)
    cargarContexto(true)
  } catch (e) {
    errorApi(e)
  } finally {
    ocupado.value = false
  }
}

async function devolver() {
  ocupado.value = true
  try {
    tomar(await api.post(`/productos/${p.value.id}/observar`, { version: p.value.version, observaciones: modal.value.texto, devolver: true }))
    modal.value = null
    avisar('Returned to the supplier with your notes.')
  } catch (e) {
    errorApi(e)
  } finally {
    ocupado.value = false
  }
}

async function nuevaVersion() {
  ocupado.value = true
  try {
    tomar(await api.post(`/productos/${p.value.id}/versiones`, { version: p.value.version, motivo: modal.value.texto, desde: modal.value.desde || null }))
    modal.value = null
    avisar(`Version ${p.value.version_ficha} opened. Update the sheet and send it for review.`)
  } catch (e) {
    errorApi(e)
  } finally {
    ocupado.value = false
  }
}

// Enseñar el código nacional para que se use en productos parecidos
function abrirEnsenar(x) {
  const conds = M.condDeArticulo(r.value.s)
  modal.value = { tipo: 'ensenar', pais: x, conds: conds.map((c) => ({ ...c, usar: (x.pedir || []).includes(c.k) })) }
}
async function ensenar() {
  const m = modal.value
  const cond = Object.fromEntries(m.conds.filter((c) => c.usar).map((c) => [c.k, c.v]))
  ocupado.value = true
  try {
    await api.post('/clasificacion/incisos', { pais: m.pais.iso, codigo: M.digits(m.pais.codigo), cond })
    ctx.value = await cargarContexto(true)
    modal.value = null
    avisar(`Saved. ${m.pais.nombre} will use ${M.fmtCode(m.pais.codigo)} for products like this one.`)
  } catch (e) {
    errorApi(e)
  } finally {
    ocupado.value = false
  }
}

// ---- Fotos -----------------------------------------------------------------
async function subirFoto(e) {
  const a = e.target.files?.[0]
  e.target.value = ''
  if (!a) return
  const datos = new FormData()
  datos.append('archivo', a)
  ocupado.value = true
  try {
    await api.post(`/productos/${p.value.id}/fotos`, datos)
    const det = await api.get(`/productos/${p.value.id}`)
    p.value = { ...det }
    f.fotos = det.fotos
    base.value = instantanea()
  } catch (err) {
    errorApi(err)
  } finally {
    ocupado.value = false
  }
}
async function borrarFoto(foto) {
  try {
    await api.del(`/productos/${p.value.id}/fotos/${foto.id}`)
    p.value.fotos = p.value.fotos.filter((x) => x.id !== foto.id)
    f.fotos = p.value.fotos
    base.value = instantanea()
  } catch (e) {
    errorApi(e)
  }
}

// ---- Especialista (Claude) -----------------------------------------------------
async function consultar() {
  const s = r.value.s
  ocupado.value = true
  try {
    const op = await api.post(`/productos/${p.value.id}/analizar`, {
      ficha_texto: M.fichaTexto({ ...s, estilo: f.descArchivo || f.estilo, desc: r.value.desc }),
      sugerido: M.fmtCode(r.value.o.codigo || ''),
      confianza: r.value.o.confianza,
      razones: r.value.o.razones || [],
      alertas: alertas.value.map((a) => a.msg).slice(0, 30),
      parecidos: (r.value.o.parecidos || []).map((x) => `${x.r.estilo} ${x.r.color || ''}: ${M.fmtCode(x.r.codigo)}`),
      campos: M.camposCorregibles({ ...s }),
      con_fotos: true,
    })
    p.value = { ...p.value, opinion_ia: op }
  } catch (e) {
    errorApi(e)
  } finally {
    ocupado.value = false
  }
}
function aplicarCorreccion(c) {
  if (c.campo.startsWith('comp.')) f.comp = { ...f.comp, [c.campo.slice(5)]: c.valor }
  else if (M.ATTR_BY[c.campo]?.tipo === 'check') f[c.campo] = c.valor === true || c.valor === 'true'
  else f[c.campo] = c.valor
}

async function descargarPdf() {
  try {
    await api.descargar(`/productos/${p.value.id}/pdf`, `sheet_${p.value.estilo}.pdf`)
  } catch (e) {
    errorApi(e)
  }
}

// ---- Historial -------------------------------------------------------------
const ACCION = {
  ficha_guardada: 'Saved the technical sheet',
  clasificado: 'Ran the classification',
  aprobado: 'Approved the classification',
  corregido: 'Approved with a different code',
  devuelto: 'Returned to the supplier',
  observacion: 'Added a note',
  nueva_version: 'Opened a new version',
  opinion_especialista: 'Asked the specialist',
  foto_agregada: 'Added a photo',
  foto_quitada: 'Removed a photo',
}
function detalleHist(h) {
  const d = h.detalle || {}
  if (d.codigo) return d.codigo + (d.sugerido && d.sugerido !== d.codigo ? ` (suggested ${d.sugerido})` : '')
  if (d.sugerido) return `Suggested ${d.sugerido}`
  if (d.observaciones) return d.observaciones
  if (d.version) return `Version ${d.version}`
  return ''
}

// Aviso al salir con cambios sin guardar
function antesDeSalir(e) {
  if (sucio.value && puedeEditar.value) {
    e.preventDefault()
    e.returnValue = ''
  }
}
onBeforeRouteLeave(() => !(sucio.value && puedeEditar.value) || window.confirm('The technical sheet has unsaved changes. Leave anyway?'))
onMounted(() => {
  cargar()
  window.addEventListener('beforeunload', antesDeSalir)
})
onBeforeUnmount(() => window.removeEventListener('beforeunload', antesDeSalir))
</script>

<template>
  <div v-if="p && ctx">
    <router-link to="/productos" class="volver"><Icono nombre="atras" :tam="15" />Products</router-link>

    <section class="doc-cabeza">
      <div class="doc-fila">
        <span class="foto-cabeza">
          <img v-if="p.fotos.length" :src="`/api/productos/fotos/${p.fotos[0].id}`" alt="" />
          <Icono v-else nombre="caja" :tam="24" />
        </span>
        <div>
          <span class="doc-numero">{{ p.estilo }} · {{ p.color }}</span>
          <div class="doc-sub"><span v-if="p.codigo_generico" class="etiqueta acento" style="margin-left: 0" title="Generic: first 8 digits of the item code">Generic {{ p.codigo_generico }}</span> {{ p.descripcion_comercial || '—' }} · {{ p.marca_nombre || p.marca }}<template v-if="p.proveedor && p.proveedor !== (p.marca_nombre || p.marca)"> · {{ p.proveedor }}</template></div>
        </div>
        <EstadoBadge :estado="p.estado" />
        <span v-if="p.version_ficha > 1" class="etiqueta">Version {{ p.version_ficha }}</span>
        <div class="doc-acciones">
          <button class="btn btn-fantasma" title="Technical sheet with the classification, as PDF" @click="descargarPdf"><Icono nombre="descargar" />PDF</button>
          <button v-if="aprobado && puede('producto.ficha')" class="btn" @click="modal = { tipo: 'version', texto: '', desde: '' }"><Icono nombre="editar" />New version</button>
          <button v-if="puedeEditar" class="btn btn-primario" :disabled="ocupado || !sucio" @click="guardar()"><Icono nombre="check" />{{ sucio ? 'Save sheet' : 'Saved' }}</button>
        </div>
      </div>
      <div class="doc-meta">
        <span>Sizes <b>{{ p.rango_tallas || '—' }}</b></span>
        <span>SKUs <b>{{ p.skus }}</b></span>
        <span>Origin <b>{{ f.origen || '—' }}</b></span>
        <span v-if="p.revisado_por">Reviewed by <b>{{ p.revisado_por }}</b> · {{ fmtFecha(p.revisado_en) }}</span>
      </div>
    </section>

    <p v-if="p.estado === 'observado' && p.observaciones" class="nota aviso" role="status">
      <Icono nombre="alerta" /><span><b>Returned for correction.</b> {{ p.observaciones }}</span>
    </p>
    <p v-else-if="aprobado" class="nota ok">
      <Icono nombre="check" /><span>This sheet is approved and locked. Purchase orders and invoices use its codes. To change it, open a new version.</span>
    </p>

    <div class="producto-layout">
      <div class="producto-principal">
        <div class="pestanas" role="tablist">
          <button class="pestana" role="tab" :aria-selected="pestana === 'ficha'" @click="pestana = 'ficha'"><Icono nombre="lista" :tam="16" />Technical sheet
            <span v-if="r && r.faltan.length && !aprobado" class="cuenta alerta">{{ r.faltan.length }}</span></button>
          <button class="pestana" role="tab" :aria-selected="pestana === 'tallas'" @click="pestana = 'tallas'"><Icono nombre="caja" :tam="16" />Sizes and prepacks
            <span class="cuenta">{{ p.articulos.length }}</span></button>
          <button class="pestana" role="tab" :aria-selected="pestana === 'historial'" @click="pestana = 'historial'"><Icono nombre="historial" :tam="16" />History</button>
        </div>

        <!-- Ficha técnica -->
        <FichaTecnica v-if="pestana === 'ficha'" :key="`${p.id}-${p.version_ficha}-${cargas}`" :f="f" :r="r" :ctx="ctx" :producto="p" :paises="opciones.paises"
                      :editable="puedeEditar" @subir-foto="subirFoto" @borrar-foto="borrarFoto" @contexto="recargarContexto" />

        <!-- Tallas y prepacks -->
        <div v-else-if="pestana === 'tallas'">
          <div class="fila-flex mt-chico" style="justify-content: space-between">
            <p class="ayuda">Every size of generic <b>{{ p.codigo_generico || '—' }}</b> (first 8 digits of the item code) shares the technical sheet and the HS code. Prepacks are not classified: they are built with these solids and take their code.</p>
            <button v-if="p.codigo_generico && puede('catalogos.editar')" class="btn btn-chico" @click="agregarTallas = true"><Icono nombre="mas" :tam="14" />Add sizes</button>
          </div>
          <div class="tabla-marco mt-chico">
            <table class="tabla">
              <thead><tr><th>Item code</th><th>Size code</th><th>Supplier SKU</th><th>UPC</th><th>Size</th><th>Unit</th><th>Description</th><th>Status</th></tr></thead>
              <tbody>
                <tr v-for="a in p.articulos" :key="a.id">
                  <td class="fuerte">{{ a.sku }}<span v-if="a.tipo === 'PREPACK'" class="etiqueta acento">Prepack</span></td>
                  <td class="apagado">{{ a.sku.length === 11 ? a.sku.slice(8) : '—' }}</td>
                  <td>{{ a.sku_proveedor || '—' }}</td>
                  <td>{{ a.upc || '—' }}</td>
                  <td>{{ a.talla || '—' }}</td>
                  <td>{{ a.unidad }}</td>
                  <td class="apagado">{{ p.descripcion_comercial ? `${p.descripcion_comercial}, ${a.tipo === 'PREPACK' ? 'prepack' : 'size'} ${a.talla}` : a.descripcion }}</td>
                  <td><span v-if="a.activo" class="etiqueta ok">Active</span><span v-else class="etiqueta">Inactive</span></td>
                </tr>
              </tbody>
            </table>
          </div>
          <div v-for="x in p.prepacks" :key="x.id" class="panel mt">
            <div class="panel-cabeza"><div><h2>Prepack {{ x.codigo }}</h2><p>{{ x.descripcion }} · {{ x.total }} per carton<template v-if="x.sku"> · SKU {{ x.sku }}</template></p></div></div>
            <div class="chips"><span v-for="c in x.componentes" :key="c.sku" class="etiqueta">{{ c.talla }} × {{ c.cantidad }}</span></div>
          </div>
        </div>

        <!-- Historial -->
        <div v-else class="panel">
          <ol class="linea-hist">
            <li v-for="(h, i) in p.historial" :key="i">
              <b>{{ ACCION[h.accion] || h.accion }}</b>
              <span class="apagado"> · {{ h.usuario || 'System' }} · {{ fmtFechaHora(h.fecha) }}</span>
              <div v-if="detalleHist(h) || h.motivo" class="sub">{{ detalleHist(h) }}<template v-if="h.motivo"> · {{ h.motivo }}</template></div>
            </li>
            <li v-if="!p.historial.length" class="apagado">No changes recorded yet.</li>
          </ol>
          <template v-if="p.versiones.length">
            <h3 class="mt">Previous versions</h3>
            <table class="tabla mt-chico">
              <thead><tr><th>Version</th><th>Valid</th><th>HS code</th><th>Reason for the change</th></tr></thead>
              <tbody>
                <tr v-for="v in p.versiones" :key="v.version">
                  <td>{{ v.version }}</td><td>{{ fmtFecha(v.desde) }} – {{ fmtFecha(v.hasta) }}</td>
                  <td class="codigo-sac">{{ v.codigo || '—' }}</td><td>{{ v.motivo || '—' }}</td>
                </tr>
              </tbody>
            </table>
          </template>
        </div>
      </div>

      <!-- Panel de clasificación -->
      <aside class="clasif" aria-label="Classification">
        <section class="panel">
          <div class="eyebrow">Tariff classification</div>
          <div class="sello" :class="aprobado ? 'aprobado' : codigo6.length === 6 ? 'sugerido' : 'vacio'">
            <span class="codigo-grande">{{ codigo || '——.——' }}</span>
            <span class="sello-texto">{{ aprobado ? 'Approved' : codigo6.length === 6 ? (codOficial ? 'Chosen by you' : 'Suggested') : 'No code yet' }}</span>
          </div>
          <p v-if="codigo6.length === 6" class="desc-sac">{{ M.descDe(codigo6) }}</p>

          <template v-if="!aprobado && r">
            <div class="confianza" :title="`Confidence: ${r.o.confianza}`">
              <span v-for="n in 3" :key="n" class="barra" :class="{ llena: n <= confNivel, ['n' + confNivel]: true }"></span>
              <span class="ayuda">{{ r.o.confianza }} confidence · {{ M.FUENTES[r.o.fuente] || 'rules' }}</span>
            </div>
            <ul class="razones">
              <li v-for="(x, i) in (verRazones ? r.o.razones : r.o.razones.slice(0, 3))" :key="i">{{ x }}</li>
            </ul>
            <ul v-if="pistas.length" class="pistas">
              <li v-for="x in pistas" :key="x"><Icono nombre="info" :tam="13" />{{ x }}</li>
            </ul>
            <button v-if="r.o.razones.length > 3" type="button" class="btn-texto" @click="verRazones = !verRazones">{{ verRazones ? 'Less' : `Why (${r.o.razones.length} steps)` }}</button>
          </template>

          <div v-if="!aprobado && r && r.faltan.length" class="bloque-clasif">
            <h3><Icono nombre="alerta" :tam="15" />To complete the sheet</h3>
            <ul class="lista-simple"><li v-for="x in r.faltan" :key="x">{{ x }}</li></ul>
          </div>

          <div v-if="!aprobado && alertas.length" class="bloque-clasif">
            <h3><Icono nombre="info" :tam="15" />Check</h3>
            <ul class="alertas">
              <li v-for="a in alertas" :key="a.msg" :class="a.nivel">
                <span>{{ a.msg }}</span>
                <button v-if="a.nivel !== 'error' && puedeEditar" type="button" class="btn-texto" @click="revisada(a)">Reviewed</button>
              </li>
            </ul>
          </div>

          <div v-if="!aprobado && puedeAprobar && r" class="bloque-clasif">
            <h3>Other codes</h3>
            <ul class="alternativas">
              <li v-for="a in r.o.alternativas.slice(0, 4)" :key="a.codigo">
                <button type="button" class="enlace" @click="usarCodigo(a.codigo)">{{ M.fmtCode(a.codigo) }}</button>
                <span class="sub">{{ a.cuando }}</span>
              </li>
            </ul>
            <form class="fila-flex otro-codigo" @submit.prevent="aplicarOtro">
              <input v-model="otroCodigo" class="entrada" placeholder="Another code, e.g. 6404.11" aria-label="Another HS code" />
              <button class="btn btn-chico" type="submit">Use</button>
              <button v-if="codOficial" type="button" class="btn-texto" @click="codOficial = ''">Back to suggested</button>
            </form>
          </div>
        </section>

        <section class="panel">
          <div class="panel-cabeza"><div><h2>By destination</h2><p>{{ paisesOk }} of {{ paises.length }} national codes complete</p></div></div>
          <table class="tabla paises">
            <tbody>
              <tr v-for="x in paises" :key="x.iso">
                <td class="fuerte">{{ x.iso }}</td>
                <td>
                  <template v-if="!aprobado && puedeAprobar">
                    <input class="entrada entrada-pais" :class="{ invalida: errPais[x.iso], tentativo: !['ok', 'auto'].includes(x.estado) && !x.manual }"
                           :value="x.codigo ? M.fmtPais(x.codigo, x.digitos) : ''" :placeholder="`${M.fmtCode(codigo6) || 'Code'}… (${x.digitos} digits)`"
                           :list="x.opciones?.length ? `ops-${x.iso}` : undefined" inputmode="numeric" :maxlength="x.digitos + 6"
                           :aria-label="`National code for ${x.nombre}`" :title="`Type the ${x.digitos}-digit code; it applies when you leave the field`"
                           @blur="escribirPais(x, $event.target)" @keydown.enter.prevent="$event.target.blur()" />
                    <datalist v-if="x.opciones?.length" :id="`ops-${x.iso}`">
                      <option v-for="o in x.opciones" :key="o.codigo" :value="M.fmtPais(o.codigo, x.digitos)">{{ M.condTexto(o.cond) }}</option>
                    </datalist>
                    <span v-if="errPais[x.iso]" class="sub" style="color: var(--error)">{{ errPais[x.iso] }}</span>
                    <span v-else-if="x.manual" class="sub">Set by hand · <button type="button" class="btn-texto" @click="quitarManual(x.iso)">use automatic</button> · <button type="button" class="btn-texto" @click="abrirEnsenar(x)">remember for similar</button></span>
                    <span v-else-if="!['ok', 'auto'].includes(x.estado)" class="sub">{{ x.estado === 'elegir' ? 'Choose one of the listed codes or type it' : M.EST_PAIS[x.estado]?.[1] }}</span>
                  </template>
                  <template v-else>
                    <select v-if="x.estado === 'elegir' && x.opciones?.length && puedeEditar" class="entrada" :aria-label="`Code for ${x.nombre}`" @change="codigoPais(x.iso, $event.target.value)">
                      <option value="">Choose…</option>
                      <option v-for="o in x.opciones" :key="o.codigo" :value="o.codigo">{{ M.fmtPais(o.codigo, x.digitos) }} · {{ M.condTexto(o.cond) }}</option>
                    </select>
                    <template v-else>
                      <span class="codigo-sac" :class="{ tentativo: !['ok', 'auto'].includes(x.estado) }">{{ x.codigo ? M.fmtPais(x.codigo, x.digitos) : '—' }}</span>
                      <span v-if="x.manual" class="etiqueta acento" title="Set by hand">manual</span>
                    </template>
                    <span v-if="!['ok', 'auto'].includes(x.estado) && x.estado !== 'elegir'" class="sub">{{ M.EST_PAIS[x.estado]?.[1] }}</span>
                  </template>
                </td>
                <td class="num apagado">{{ x.dai !== '' && x.dai != null ? `${x.dai}%` : '' }}</td>
              </tr>
            </tbody>
          </table>
        </section>

        <section v-if="!aprobado && r?.o.parecidos?.length" class="panel">
          <div class="panel-cabeza"><div><h2>Similar products</h2><p>Already classified</p></div></div>
          <ul class="parecidos">
            <li v-for="x in r.o.parecidos.slice(0, 3)" :key="x.r.id">
              <router-link :to="`/productos/${x.r.id}`"><span v-if="x.r.generico" class="codigo">{{ x.r.generico }}</span> {{ x.r.estilo }} {{ x.r.color }}</router-link>
              <span class="codigo-sac">{{ M.fmtCode(x.r.codigo) }}</span>
              <span class="sub">{{ x.r.desc }}</span>
            </li>
          </ul>
        </section>

        <section v-if="(ctx.especialista && puedeAprobar && !aprobado) || p.opinion_ia" class="panel">
          <div class="panel-cabeza"><div><h2>Specialist opinion</h2><p>A second opinion by Claude. It never approves anything.</p></div>
            <button v-if="ctx.especialista && puedeAprobar && !aprobado" class="btn btn-chico" :disabled="ocupado" @click="consultar"><Icono nombre="varita" />{{ p.opinion_ia ? 'Ask again' : 'Ask' }}</button>
          </div>
          <div v-if="p.opinion_ia" class="opinion">
            <p><span class="codigo-sac">{{ M.fmtCode(p.opinion_ia.codigo) }}</span> <span class="etiqueta">{{ p.opinion_ia.confianza }}</span>
              <button v-if="!aprobado && puedeAprobar && p.opinion_ia.codigo" type="button" class="btn-texto" @click="usarCodigo(p.opinion_ia.codigo)">Use this code</button></p>
            <p class="sub">{{ p.opinion_ia.razonamiento }}</p>
            <ul v-if="p.opinion_ia.correcciones?.length" class="lista-simple">
              <li v-for="c in p.opinion_ia.correcciones" :key="c.campo">{{ M.nombreCampo(c) }} → <b>{{ M.valorLegible(c) }}</b> <span class="apagado">{{ c.motivo }}</span>
                <button v-if="puedeEditar" type="button" class="btn-texto" @click="aplicarCorreccion(c)">Apply</button></li>
            </ul>
            <ul v-if="p.opinion_ia.preguntas_proveedor?.length" class="lista-simple apagado">
              <li v-for="q in p.opinion_ia.preguntas_proveedor" :key="q">{{ q }}</li>
            </ul>
          </div>
        </section>

        <div v-if="!aprobado && puedeAprobar" class="acciones-clasif">
          <button class="btn btn-primario btn-grande" :disabled="ocupado || !r || codigo6.length < 6 || !r.completa || errores.length > 0"
                  :title="!r?.completa ? 'Complete the technical sheet first' : errores.length ? 'Fix the errors first' : ''" @click="aprobar">
            <Icono nombre="check" />Approve {{ codigo }}
          </button>
          <button class="btn" :disabled="ocupado" @click="modal = { tipo: 'devolver', texto: p.observaciones || (r?.faltan.length ? `Please complete: ${r.faltan.join(', ')}.` : '') }">Return to supplier</button>
        </div>
        <p v-else-if="!aprobado && puedeEditar" class="ayuda acciones-clasif">
          <template v-if="r?.completa">Complete. Save it and customs will review it.</template>
          <template v-else>Complete the required fields; customs reviews it once the sheet is complete.</template>
        </p>
      </aside>
    </div>

    <!-- Ventanas -->
    <GenericoModal v-if="agregarTallas" :generico="p.codigo_generico" @cerrar="agregarTallas = false" @listo="agregarTallas = false; cargar()" />
    <Modal v-if="modal?.tipo === 'devolver'" titulo="Return to the supplier" @cerrar="modal = null">
      <label class="campo"><span class="req">What should be corrected</span><textarea v-model="modal.texto" class="entrada" rows="4" maxlength="2000"></textarea></label>
      <template #pie>
        <button class="btn" @click="modal = null">Cancel</button>
        <button class="btn btn-primario" :disabled="ocupado || !modal.texto.trim()" @click="devolver">Return</button>
      </template>
    </Modal>
    <Modal v-if="modal?.tipo === 'version'" titulo="New version of the sheet" @cerrar="modal = null">
      <p class="ayuda">The approved version is kept in the history with its code. The new one starts as a draft and needs approval again.</p>
      <div class="rejilla-campos mt-chico">
        <label class="campo ancho-2"><span class="req">Reason for the change</span><input v-model="modal.texto" class="entrada" maxlength="300" placeholder="E.g. new outsole material" /></label>
        <label class="campo"><span>Valid from</span><input v-model="modal.desde" type="date" class="entrada" /></label>
      </div>
      <template #pie>
        <button class="btn" @click="modal = null">Cancel</button>
        <button class="btn btn-primario" :disabled="ocupado || !modal.texto.trim()" @click="nuevaVersion">Open new version</button>
      </template>
    </Modal>
    <Modal v-if="modal?.tipo === 'ensenar'" :titulo="`Remember ${M.fmtPais(modal.pais.codigo, modal.pais.digitos)} for ${modal.pais.nombre}`" ancho="480px" @cerrar="modal = null">
      <p class="ayuda">Products with this subheading that match the checked data will get this code automatically.</p>
      <div class="lista-cond">
        <label v-for="c in modal.conds" :key="c.k" class="check"><input v-model="c.usar" type="checkbox" /><span>{{ c.l }}: <b>{{ M.textoValor(c.k, c.v) }}</b></span></label>
        <p v-if="!modal.conds.length" class="apagado">No distinguishing data: it will apply to the whole subheading.</p>
      </div>
      <template #pie>
        <button class="btn" @click="modal = null">Only this product</button>
        <button class="btn btn-primario" :disabled="ocupado" @click="ensenar">Remember</button>
      </template>
    </Modal>
  </div>
  <p v-else class="vacio">Loading…</p>
</template>

<style scoped>
.producto-layout { display: grid; grid-template-columns: minmax(0, 1fr) 380px; gap: 20px; align-items: start; margin-top: 4px; }
.producto-principal .pestanas { margin-top: 4px; }
.clasif { display: flex; flex-direction: column; gap: 14px; }
.clasif .panel + .panel { margin-top: 0; }
@media (max-width: 1080px) {
  .producto-layout { grid-template-columns: minmax(0, 1fr); }
  .clasif { position: static; max-height: none; overflow: visible; }
}
.ficha { border: 0; padding: 0; margin: 0; min-width: 0; }
.ficha .panel + .panel { margin-top: 14px; }
.ficha:disabled .segmento:not([aria-pressed='true']) { opacity: 0.55; }
.ancho-2 { grid-column: span 2; }
@media (max-width: 640px) { .ancho-2 { grid-column: auto; } }
.composicion { grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); }
.atributos { display: flex; flex-direction: column; gap: 14px; }
.atributo { display: flex; flex-direction: column; gap: 6px; }
.atributo-nombre { font-weight: 580; font-size: 0.86rem; color: var(--tinta-2); }
.atributo.definido { flex-direction: row; justify-content: space-between; flex-wrap: wrap; gap: 6px; font-size: 0.88rem; padding: 8px 10px; background: var(--superficie-2); border-radius: var(--radio); }
.atributo.check { flex-direction: row; align-items: flex-start; gap: 8px; font-size: 0.9rem; }
.atributo select { max-width: 420px; }
.foto-cabeza { width: 52px; height: 52px; border-radius: 10px; border: 1px solid var(--linea); background: var(--superficie-2); display: grid; place-items: center; overflow: hidden; color: var(--tinta-3); flex: none; }
.foto-cabeza img { width: 100%; height: 100%; object-fit: cover; }
.fotos { display: flex; gap: 10px; flex-wrap: wrap; }
.foto { position: relative; margin: 0; width: 120px; height: 120px; border-radius: 10px; overflow: hidden; border: 1px solid var(--linea); }
.foto img { width: 100%; height: 100%; object-fit: cover; }
.foto .btn-icono { position: absolute; top: 4px; right: 4px; background: var(--superficie); }
.desc-aduana { font-size: 0.9rem; letter-spacing: 0.01em; background: var(--superficie-2); border: 1px dashed var(--linea); border-radius: var(--radio); padding: 10px 12px; }
.sello { display: flex; align-items: baseline; justify-content: space-between; gap: 10px; margin: 6px 0 4px; }
.codigo-grande { font-stretch: 125%; font-weight: 780; font-size: 2rem; line-height: 1.1; font-variant-numeric: tabular-nums; }
.sello.vacio .codigo-grande { color: var(--tinta-3); }
.sello-texto { font-size: 0.78rem; font-weight: 650; text-transform: uppercase; letter-spacing: 0.05em; padding: 3px 8px; border-radius: 6px; background: var(--linea-suave); color: var(--tinta-2); }
.sello.aprobado .sello-texto { background: var(--ok-fondo); color: var(--ok); }
.sello.sugerido .sello-texto { background: var(--info-fondo); color: var(--info); }
.desc-sac { font-size: 0.86rem; color: var(--tinta-2); }
.confianza { display: flex; align-items: center; gap: 4px; margin: 12px 0 6px; }
.confianza .barra { width: 22px; height: 6px; border-radius: 3px; background: var(--linea); }
.confianza .barra.llena.n3 { background: var(--ok); }
.confianza .barra.llena.n2 { background: #d69e2e; }
.confianza .barra.llena.n1 { background: var(--error); }
.confianza .ayuda { margin-left: 6px; }
.razones { margin: 6px 0 2px; padding-left: 18px; font-size: 0.86rem; color: var(--tinta-2); display: flex; flex-direction: column; gap: 3px; }
.pistas { list-style: none; margin: 8px 0 0; padding: 0; font-size: 0.82rem; color: var(--aviso); display: flex; flex-direction: column; gap: 4px; }
.pistas li { display: flex; gap: 6px; align-items: flex-start; }
.pistas svg { margin-top: 2px; flex: none; }
.bloque-clasif { border-top: 1px solid var(--linea-suave); margin-top: 12px; padding-top: 10px; }
.bloque-clasif h3 { font-size: 0.86rem; display: flex; align-items: center; gap: 6px; margin-bottom: 6px; }
.lista-simple { margin: 0; padding-left: 18px; font-size: 0.86rem; display: flex; flex-direction: column; gap: 3px; }
.alertas { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
.alertas li { font-size: 0.84rem; padding: 7px 9px; border-radius: 7px; background: var(--info-fondo); color: var(--info-texto); display: flex; gap: 8px; justify-content: space-between; align-items: flex-start; }
.alertas li.aviso { background: var(--aviso-fondo); color: var(--aviso); }
.alertas li.error { background: var(--error-fondo); color: var(--error); }
.alertas .btn-texto { color: inherit; font-size: 0.8rem; white-space: nowrap; }
.alternativas { list-style: none; margin: 0 0 8px; padding: 0; display: flex; flex-direction: column; gap: 5px; font-size: 0.86rem; }
.otro-codigo { gap: 6px; flex-wrap: nowrap; }
.otro-codigo .entrada { flex: 1; min-width: 0; }
.paises td { padding-top: 7px; padding-bottom: 7px; }
.paises select { max-width: 100%; font-size: 0.84rem; }
.entrada-pais { width: 100%; min-width: 0; font-family: var(--mono, ui-monospace, monospace); font-weight: 600; padding: 6px 8px; }
.entrada-pais.tentativo { border-style: dashed; }
.entrada-pais.invalida { border-color: var(--error); box-shadow: 0 0 0 3px var(--error-fondo); }
.paises .sub .btn-texto { font-size: inherit; padding: 0; }
.parecidos { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 8px; font-size: 0.88rem; }
.parecidos .codigo-sac { margin-left: 6px; }
.opinion p + p { margin-top: 6px; }
.acciones-clasif { display: flex; flex-direction: column; gap: 8px; }
.acciones-clasif .btn { justify-content: center; }
.linea-hist { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 12px; }
.linea-hist li { padding-left: 14px; border-left: 2px solid var(--linea); }
.lista-cond { display: flex; flex-direction: column; gap: 8px; margin-top: 10px; }
</style>
