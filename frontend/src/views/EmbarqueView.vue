<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api'
import Avance from '../components/Avance.vue'
import BarraSeleccion from '../components/BarraSeleccion.vue'
import CeldaEditable from '../components/CeldaEditable.vue'
import EstadoBadge from '../components/EstadoBadge.vue'
import Icono from '../components/Icono.vue'
import Modal from '../components/Modal.vue'
import SelectBusqueda from '../components/SelectBusqueda.vue'
import TarjetaParte from '../components/TarjetaParte.vue'
import ThOrden from '../components/ThOrden.vue'
import { MODOS, useRutas } from '../composables/useRutas'
import { useTabla } from '../composables/useTabla'
import { sesion } from '../stores/sesion'
import { avisar, errorApi, guardando } from '../stores/ui'
import { ACCIONES, diasTxt, fmtFecha, fmtFechaHora, fmtFechaHoraLocal, fmtNum, plural, porUnidadTxt, useSeleccion } from '../utils'

// El embarque es el espacio de trabajo de logística: sus datos, sus
// contenedores (cada uno con su carga) y el seguimiento, en una sola vista.
const props = defineProps({ id: String })
const route = useRoute()
const router = useRouter()
const e = ref(null)
const u = ref(null)
const unidadId = ref(Number(route.query.unidad) || null)
const disponibles = ref([])
const filtros = reactive({ q: '', solo_listos: false })
const selA = useSeleccion()
const selD = useSeleccion()
const abiertas = reactive(new Set())
const modal = ref(null)
const cajon = ref(false)
const confirmarListos = ref(true)
const ocupado = ref(false)
const verHistorial = ref(false)

const EVENTOS = [
  ['RECOLECCION', 'Pickup'],
  ['SALIDA', 'Departure'],
  ['TRANSITO', 'In transit'],
  ['ARRIBO', 'Arrival'],
  ['LIBERACION', 'Customs release'],
  ['ENTREGA', 'Delivery'],
  ['RECEPCION', 'Warehouse receipt'],
  ['OTRO', 'Other'],
]
const nombreEvento = (t) => EVENTOS.find((x) => x[0] === t)?.[1] || t
const HITOS = [['PLANIFICADO', 'Planned'], ['EN_TRANSITO', 'In transit'], ['ARRIBADO', 'Arrived'], ['ENTREGADO', 'Delivered'], ['RECIBIDO', 'Received']]
const SIGUIENTE = { PLANIFICADO: 'SALIDA', EN_TRANSITO: 'ARRIBO', ARRIBADO: 'ENTREGA', ENTREGADO: 'RECEPCION' }
// El cuarto valor marca lo que exige el documento de transporte (BL, AWB o
// carta de porte): sin eso no se registra la salida.
const CAMPOS = [
  ['documento_numero', 'Transport document', 'text', true],
  ['etd', 'ETD (estimated departure)', 'date', false],
  ['eta', 'ETA (estimated arrival)', 'date', false],
]
// Al registrar la salida la carga queda cerrada: no se agregan, quitan ni
// mueven PL o contenedores, y los datos del viaje quedan fijos.
const cerrado = computed(() => !!e.value?.cerrado)
const FIJOS_SALIDA = ['documento_numero', 'transportista_id', 'puerto_origen', 'etd', 'centro']
const fijo = (campo) => cerrado.value && (FIJOS_SALIDA.includes(campo) || (e.value.arribo_real && ['eta', 'puerto_destino'].includes(campo)))
const eventosPermitidos = computed(() => EVENTOS.filter(([k]) => (e.value?.eventos_permitidos || []).includes(k)))
const ultimoEvento = computed(() => (e.value?.eventos || []).reduce((a, ev) => (!a || ev.fecha > a ? ev.fecha : a), null))
const tonoHolgura = (d) => (d === null || d === undefined ? '' : d < 0 ? 'error' : d < 7 ? 'aviso' : 'ok')
const holguraTxt = (d) => (d < 0 ? `${-d} d late for the store` : `${d} d margin`)
const exigeSello = computed(() => !!u.value?.requiere_sello)
const modo = computed(() => MODOS[e.value?.tipo_transporte] || MODOS.MARITIMO)
const UNIDADES_TXT = { MARITIMO: ['Container', 'Containers'], AEREO: ['Air waybill', 'Air waybills'], TERRESTRE: ['Truck', 'Trucks'] }
const unidadTxt = computed(() => UNIDADES_TXT[e.value?.tipo_transporte] || UNIDADES_TXT.MARITIMO)
const indiceEstado = computed(() => HITOS.findIndex(([k]) => k === e.value?.estado))
const icono = computed(() => ({ AEREO: 'avion', TERRESTRE: 'camion' })[e.value?.tipo_transporte] || 'barco')
const totales = computed(() => (e.value?.unidades || []).reduce((a, x) => ({
  pls: a.pls + x.packing_lists, cajas: a.cajas + x.cajas, cbm: a.cbm + x.cbm, kg: a.kg + x.peso_bruto, tentativas: a.tentativas + x.tentativas,
}), { pls: 0, cajas: 0, cbm: 0, kg: 0, tentativas: 0 }))

// Ruta coherente con el modo: puertos del tipo del embarque, destino entre los
// puertos del centro (el principal sugerido) y transportistas del modo que
// trabajan con la sociedad del centro.
const { cargarRutas, centros, puertos, puertosDe, destinosDe, transportistasDe } = useRutas()
const origenes = computed(() => (e.value ? puertosDe(e.value.tipo_transporte) : []))
const destinos = computed(() => (e.value ? destinosDe(e.value.tipo_transporte, e.value.centro) : []))
const opcionesTransportista = computed(() => (e.value ? transportistasDe(e.value.tipo_transporte, e.value.centro) : []))
const nombrePuerto = (c) => puertos.value.find((x) => x.valor === c)?.texto || c || '—'
async function cambiarRuta(campo, valor) {
  const datos = { [campo]: valor || null }
  if (campo === 'centro') {
    // El destino pasa al principal del nuevo centro si el actual no es uno de sus puertos
    const nuevos = destinosDe(e.value.tipo_transporte, valor)
    if (valor && !nuevos.some((p) => p.valor === e.value.puerto_destino)) datos.puerto_destino = nuevos[0]?.valor || null
    // El transportista debe trabajar con la sociedad del nuevo centro
    if (e.value.transportista_id && !transportistasDe(e.value.tipo_transporte, valor).some((t) => t.valor === e.value.transportista_id)) datos.transportista_id = null
  }
  try {
    await guardando(api.patch(`/embarques/${props.id}`, datos))
    await cargar()
  } catch (err) {
    errorApi(err)
    await cargar()
  }
}

async function cargar() {
  try {
    e.value = await api.get(`/embarques/${props.id}`)
    if (!e.value.unidades.some((x) => x.id === unidadId.value)) unidadId.value = e.value.unidades[0]?.id || null
    await cargarUnidad()
  } catch (err) {
    errorApi(err)
    if (err.status === 404) router.push('/transporte')
  }
}

async function cargarUnidad() {
  if (!unidadId.value) {
    u.value = null
    return
  }
  try {
    u.value = await api.get(`/unidades/${unidadId.value}`)
    selA.podar(u.value.asignados.map((p) => p.id))
  } catch (err) {
    errorApi(err)
  }
}

async function cargarDisponibles() {
  if (!unidadId.value) return
  try {
    disponibles.value = await api.get(`/unidades/${unidadId.value}/disponibles`, { proveedor_id: sesion.proveedorId, ...filtros })
    selD.podar(todosDisponibles.value.map((p) => p.id))
  } catch (err) {
    errorApi(err)
  }
}

watch(unidadId, (id) => {
  router.replace({ query: { ...route.query, unidad: id || undefined } })
  selA.limpiar()
  cargarUnidad()
})

// ---- Datos del embarque ----------------------------------------------------
const guardar = (campo) => async (valor) => {
  try {
    await guardando(api.patch(`/embarques/${props.id}`, { [campo]: valor || null }))
    await cargar()
  } catch (err) {
    errorApi(err)
    throw err
  }
}
const guardarUnidad = (campo) => async (valor) => {
  try {
    await guardando(api.patch(`/unidades/${unidadId.value}`, { [campo]: valor || null }))
    await cargar()
  } catch (err) {
    errorApi(err)
    throw err
  }
}

async function ejecutar(fn, exito) {
  ocupado.value = true
  try {
    const r = await guardando(fn())
    avisar(typeof exito === 'function' ? exito(r) : exito)
    modal.value = null
    selA.limpiar()
    selD.limpiar()
    await cargar()
    return r
  } catch (err) {
    errorApi(err)
    return null
  } finally {
    ocupado.value = false
  }
}

// ---- Unidades de carga (del catálogo de tipos del modo) --------------------
const tipoTxt = (t) => `${t.codigo} · ${t.nombre} (${t.modalidad}${t.capacidad_cbm ? `, ${fmtNum(t.capacidad_cbm, 0)} m³` : ''}${t.capacidad_kg ? `, ${fmtNum(t.capacidad_kg, 0)} kg` : ''})`
const tipoElegido = computed(() => e.value?.tipos_unidad.find((t) => t.codigo === modal.value?.unidad))
function abrirNuevaUnidad() {
  const tipos = e.value.tipos_unidad
  modal.value = { tipo: 'unidad', unidad: (tipos.find((t) => t.codigo === '40HC') || tipos[0])?.codigo || '', numero: '', sello: '' }
}
async function agregarUnidad() {
  const m = modal.value
  const r = await ejecutar(() => api.post(`/embarques/${props.id}/unidades`, { tipo: m.unidad, numero: m.numero || null, sello: m.sello || null }),
    (x) => `${unidadTxt.value[0]} ${x.etiqueta} added.`)
  if (r) unidadId.value = r.id
}
function eliminarUnidad() {
  ejecutar(() => api.del(`/unidades/${unidadId.value}`), `${u.value.nombre} deleted.`)
}

// ---- Carga del contenedor --------------------------------------------------
const todosDisponibles = computed(() => disponibles.value.flatMap((g) => g.packing_lists))
const suma = (pls) => pls.reduce((a, p) => ({ cajas: a.cajas + p.cajas, cbm: a.cbm + p.cbm, kg: a.kg + p.peso_bruto }), { cajas: 0, cbm: 0, kg: 0 })
const tablaA = useTabla(computed(() => u.value?.asignados || []), { porPagina: 50, valores: { contenido: (p) => p.cajas } })
const selAsignados = computed(() => (u.value?.asignados || []).filter((p) => selA.tiene(p.id)))
const selDisponibles = computed(() => todosDisponibles.value.filter((p) => selD.tiene(p.id)))
const totSelA = computed(() => suma(selAsignados.value))
const totSelD = computed(() => suma(selDisponibles.value))
const listosSel = computed(() => selDisponibles.value.filter((p) => p.puede_confirmar).length)
const proyeccion = computed(() => {
  if (!u.value?.capacidad_cbm) return null
  const cbm = u.value.cbm + totSelD.value.cbm
  const kg = u.value.peso_bruto + totSelD.value.kg
  return { cbm, pct: (cbm * 100) / u.value.capacidad_cbm, kg, pctKg: u.value.capacidad_kg ? (kg * 100) / u.value.capacidad_kg : null }
})
const requiereMotivo = computed(() => selAsignados.value.some((p) => p.asignacion === 'CONFIRMADA'))

// Which load units suit the selected cargo (by volume and weight, for this mode)
const sugerencia = ref(null)
let esperaSug
watch(() => [totSelD.value.cbm, totSelD.value.kg], ([cbm, kg]) => {
  clearTimeout(esperaSug)
  if (!cbm && !kg) {
    sugerencia.value = null
    return
  }
  esperaSug = setTimeout(async () => {
    try {
      const r = await api.get('/sugerencia-unidades', { cbm: cbm.toFixed(3), kg: kg.toFixed(1), modo: e.value.tipo_transporte })
      sugerencia.value = r.modos[e.value.tipo_transporte] || null
    } catch {
      sugerencia.value = null
    }
  }, 250)
})

function abrirCajon() {
  cajon.value = true
  cargarDisponibles()
}
function asignar() {
  const modo = confirmarListos.value ? 'AUTO' : 'TENTATIVA'
  ejecutar(() => api.post(`/unidades/${unidadId.value}/asignar`, { pl_ids: selD.lista(), modo }), textoAsignados)
    .then((r) => r && (cajon.value = false))
}
function textoAsignados(r) {
  const partes = []
  if (r.confirmados) partes.push(`${r.confirmados} confirmed`)
  if (r.tentativos) partes.push(`${r.tentativos} tentative`)
  return `${plural(r.asignados, 'packing list assigned', 'packing lists assigned')} (${partes.join(', ')}).`
}
// Recolección en la bodega del proveedor: se marca antes de zarpar
const hoy = () => new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 10)
function abrirRecoleccion() {
  modal.value = { tipo: 'recoleccion', fecha: hoy() }
}
function recolectar(fecha) {
  ejecutar(() => api.post('/recoleccion', { pl_ids: selA.lista(), fecha }),
    (r) => (fecha ? `${plural(r.actualizados, 'packing list picked up', 'packing lists picked up')}.` : 'Pickup removed.'))
}
function confirmar() {
  ejecutar(() => api.post(`/unidades/${unidadId.value}/confirmar`, { pl_ids: selAsignados.value.filter((p) => p.asignacion === 'TENTATIVA').map((p) => p.id) }),
    (r) => `${plural(r.confirmados, 'packing list confirmed', 'packing lists confirmed')}.`)
}
function quitar() {
  ejecutar(() => api.post(`/unidades/${unidadId.value}/desasignar`, { pl_ids: selA.lista(), motivo: modal.value.motivo || null }),
    'Packing lists removed from the load unit.')
}
function mover() {
  const { destino, modo, motivo } = modal.value
  ejecutar(() => api.post(`/unidades/${destino}/asignar`, { pl_ids: selA.lista(), modo, motivo: motivo || null }),
    'Packing lists moved to the other load unit.')
}
function alternarAbierta(id) {
  if (abiertas.has(id)) abiertas.delete(id)
  else abiertas.add(id)
}
let espera
function buscar() {
  clearTimeout(espera)
  espera = setTimeout(cargarDisponibles, 300)
}

// ---- Seguimiento -----------------------------------------------------------
function abrirEvento(tipo = SIGUIENTE[e.value.estado] || 'OTRO') {
  if (!(e.value.eventos_permitidos || []).includes(tipo)) tipo = e.value.eventos_permitidos?.[0] || 'OTRO'
  const ahora = new Date()
  const local = new Date(ahora.getTime() - ahora.getTimezoneOffset() * 60000).toISOString().slice(0, 16)
  modal.value = { tipo: 'evento', evento: tipo, fecha: local, ubicacion: '', observacion: '' }
}
function registrarEvento() {
  const m = modal.value
  ejecutar(() => api.post(`/embarques/${props.id}/eventos`, {
    tipo: m.evento, fecha: m.fecha, ubicacion: m.ubicacion || null, observacion: m.observacion || null,
  }), (r) => (r.estado === e.value.estado ? 'Event recorded.' : `Event recorded; the shipment is now ${HITOS.find(([k]) => k === r.estado)?.[1].toLowerCase()}.`))
}
const detalleHistorial = (h) => (h.detalle ? Object.entries(h.detalle).map(([k, v]) => `${k.replaceAll('_', ' ')}: ${Array.isArray(v) ? `${v[0] ?? '—'} to ${v[1] ?? '—'}` : v}`).join(', ') : '')

onMounted(() => {
  cargar()
  cargarRutas()
})
watch(() => sesion.proveedorId, () => cajon.value && cargarDisponibles())
</script>

<template>
  <template v-if="e">
    <router-link to="/transporte" class="volver"><Icono nombre="atras" :tam="15" />Shipments</router-link>
    <section class="doc-cabeza">
      <div class="doc-fila">
        <Icono :nombre="icono" :tam="26" />
        <span class="doc-numero">{{ e.codigo }}</span>
        <EstadoBadge :estado="e.estado" />
        <span class="doc-sub">{{ modo.nombre }}</span>
        <span v-if="e.modalidad" class="etiqueta acento" :title="e.modalidad === 'MIXTO' ? 'Combines units of different modalities (e.g. FCL and LCL)' : ''">{{ e.modalidad }}</span>
        <div class="doc-acciones">
          <button class="btn" @click="abrirEvento('OTRO')"><Icono nombre="ubicacion" />Record event</button>
          <button v-if="SIGUIENTE[e.estado]" class="btn btn-primario" :disabled="e.estado === 'PLANIFICADO' && (totales.tentativas > 0 || !totales.pls)"
                  :title="e.estado === 'PLANIFICADO' && totales.tentativas ? 'Confirm or remove the tentative PLs first' : ''" @click="abrirEvento()">
            <Icono nombre="flecha" />Record {{ nombreEvento(SIGUIENTE[e.estado]).toLowerCase() }}
          </button>
        </div>
      </div>
      <ol class="hitos" aria-label="Shipment status">
        <li v-for="([k, t], i) in HITOS" :key="k" class="hito" :class="{ hecho: i < indiceEstado || (i === indiceEstado && i === HITOS.length - 1), actual: i === indiceEstado && i < HITOS.length - 1 }">
          <span class="hito-punto"><Icono v-if="i < indiceEstado" nombre="check" :tam="12" /></span>{{ t }}
        </li>
      </ol>
      <p v-if="cerrado" class="bloqueo mt"><Icono nombre="candado" />
        <span><b>Cargo closed.</b> The shipment departed<template v-if="e.salida_real"> on {{ fmtFecha(e.salida_real) }}</template>: packing lists and load units can no longer be added, removed or moved, and the voyage data is fixed. Only the next tracking events can be recorded.</span>
      </p>
      <p v-if="e.estado === 'PLANIFICADO' && totales.tentativas" class="nota aviso mt"><Icono nombre="alerta" />There {{ totales.tentativas === 1 ? 'is' : 'are' }} {{ plural(totales.tentativas, 'tentative packing list', 'tentative packing lists') }}. Confirm or remove them before recording departure.</p>
      <div class="doc-datos">
        <label v-for="[campo, texto, tipo, obligatorio] in CAMPOS" :key="campo" class="dato">
          <span :class="{ req: obligatorio }">{{ campo === 'documento_numero' ? modo.doc : texto }}</span>
          <b v-if="fijo(campo)" :title="'Fixed since departure'">{{ tipo === 'date' ? fmtFecha(e[campo]) : e[campo] || '—' }} <Icono nombre="candado" :tam="12" /></b>
          <CeldaEditable v-else :tipo="tipo" :valor="e[campo]" :guardar="guardar(campo)" :etiqueta="texto" :vacia-texto="obligatorio ? 'Required' : ''" />
        </label>
        <div class="dato"><span class="req">{{ modo.transportista }}</span>
          <b v-if="fijo('transportista_id')">{{ e.transportista || '—' }} <Icono nombre="candado" :tam="12" /></b>
          <SelectBusqueda v-else :model-value="e.transportista_id || ''" :opciones="opcionesTransportista" vacio="Not defined" :etiqueta="modo.transportista"
                          @change="(v) => cambiarRuta('transportista_id', v)" />
        </div>
        <div class="dato"><span class="req">Receiving plant</span>
          <b v-if="cerrado">{{ e.centro || '—' }} <Icono nombre="candado" :tam="12" /></b>
          <SelectBusqueda v-else :model-value="e.centro || ''" :opciones="centros" vacio="Set by the first cargo" etiqueta="Plant"
                          @change="(v) => cambiarRuta('centro', v)" />
        </div>
        <div class="dato"><span class="req">{{ modo.puerto }} of loading</span>
          <b v-if="fijo('puerto_origen')">{{ nombrePuerto(e.puerto_origen) }} <Icono nombre="candado" :tam="12" /></b>
          <SelectBusqueda v-else :model-value="e.puerto_origen || ''" :opciones="origenes" vacio="Not defined" :etiqueta="`${modo.puerto} of loading`"
                          @change="(v) => cambiarRuta('puerto_origen', v)" />
        </div>
        <div class="dato"><span class="req">{{ modo.puerto }} of discharge</span>
          <b v-if="fijo('puerto_destino')">{{ nombrePuerto(e.puerto_destino) }} <Icono nombre="candado" :tam="12" /></b>
          <SelectBusqueda v-else :model-value="e.puerto_destino || ''" :opciones="destinos" vacio="Not defined" :etiqueta="`${modo.puerto} of discharge`"
                          @change="(v) => cambiarRuta('puerto_destino', v)" />
          <small v-if="!fijo('puerto_destino') && e.puertos_sugeridos?.length > 1" class="ayuda">The plant receives via {{ e.puertos_sugeridos.join(', ') }}.</small>
        </div>
        <div class="dato"><span>Actual departure</span><b>{{ fmtFecha(e.salida_real) }}</b></div>
        <div class="dato"><span>Actual arrival</span><b>{{ fmtFecha(e.arribo_real) }}</b></div>
      </div>
      <div class="empaque-resumen">
        <div class="cifra"><span>{{ unidadTxt[1] }}</span><b>{{ e.unidades.length }}</b></div>
        <div class="cifra"><span>Packing lists</span><b>{{ totales.pls }}</b></div>
        <div class="cifra"><span>Cartons</span><b>{{ fmtNum(totales.cajas) }}</b></div>
        <div class="cifra"><span>Volume</span><b>{{ fmtNum(totales.cbm, 2) }} m³</b></div>
        <div class="cifra"><span>Gross weight</span><b>{{ fmtNum(totales.kg, 0) }} kg</b></div>
      </div>
    </section>

    <section class="panel">
      <div class="panel-cabeza"><div><h2>{{ unidadTxt[1] }}</h2><p>Choose a unit to see and assign its cargo. Only {{ modo.nombre.toLowerCase() }} unit types are offered.</p></div></div>
      <div class="unidades-pestanas" role="tablist">
        <button v-for="x in e.unidades" :key="x.id" class="unidad-pestana" role="tab" :aria-selected="x.id === unidadId" @click="unidadId = x.id">
          <span class="fila-flex"><Icono :nombre="e.tipo_transporte === 'MARITIMO' ? 'contenedor' : modo.icono" /><span class="unidad-nombre">{{ x.nombre }}</span><span class="etiqueta" :title="x.tipo_nombre">{{ x.tipo }}</span><span v-if="x.modalidad" class="etiqueta acento">{{ x.modalidad }}</span></span>
          <Avance v-if="x.capacidad_cbm" :porcentaje="x.pct_cbm || 0" />
          <span class="ayuda">{{ plural(x.packing_lists, 'PL', 'PLs') }} · {{ fmtNum(x.cbm, 1) }} m³<template v-if="x.tentativas"> · <span class="etiqueta aviso">{{ x.tentativas }} tentative</span></template></span>
          <span v-if="x.marcas?.length" class="ayuda">{{ x.marcas.join(' · ') }}</span>
          <span v-if="x.holgura_dias !== null && x.holgura_dias !== undefined" class="etiqueta" :class="tonoHolgura(x.holgura_dias)" style="margin-left: 0">{{ holguraTxt(x.holgura_dias) }}</span>
          <span v-for="a in x.alertas" :key="a" class="etiqueta error">{{ a }}</span>
        </button>
        <button v-if="!cerrado" class="unidad-pestana agregar" @click="abrirNuevaUnidad"><Icono nombre="mas" :tam="20" />Add {{ unidadTxt[0].toLowerCase() }}</button>
      </div>

      <template v-if="u">
        <div class="dos-columnas mt" style="align-items: start">
          <div>
            <div class="rejilla-campos">
              <label class="dato"><span class="req">{{ unidadTxt[0] }} number</span>
                <b v-if="cerrado">{{ u.numero || '—' }}</b>
                <CeldaEditable v-else :valor="u.numero" :guardar="guardarUnidad('numero')" etiqueta="Number" vacia-texto="Required" />
              </label>
              <label class="dato"><span :class="{ req: exigeSello }">Seal</span>
                <b v-if="cerrado">{{ u.sello || '—' }}</b>
                <CeldaEditable v-else :valor="u.sello" :guardar="guardarUnidad('sello')" etiqueta="Seal" :vacia-texto="exigeSello ? 'Required' : ''" />
              </label>
              <div class="dato"><span>First in-store date</span><b>{{ fmtFecha(u.fecha_tienda) }}</b></div>
              <div class="dato"><span>Arrival vs. store</span>
                <b v-if="u.holgura_dias !== null && u.holgura_dias !== undefined"><span class="etiqueta" :class="tonoHolgura(u.holgura_dias)" style="margin-left: 0">{{ holguraTxt(u.holgura_dias) }}</span></b>
                <b v-else class="apagado">ETA or in-store date missing</b>
              </div>
            </div>
          </div>
          <div>
            <div v-if="u.capacidad_cbm" class="linea-avance">
              <span class="ayuda">Volume: {{ fmtNum(u.cbm, 2) }} of {{ fmtNum(u.capacidad_cbm, 0) }} m³</span>
              <Avance :porcentaje="u.pct_cbm || 0" />
            </div>
            <div v-if="u.capacidad_kg" class="linea-avance mt-chico">
              <span class="ayuda">Weight: {{ fmtNum(u.peso_bruto, 0) }} of {{ fmtNum(u.capacidad_kg, 0) }} kg</span>
              <Avance :porcentaje="u.pct_kg || 0" />
            </div>
            <p v-if="!u.capacidad_cbm" class="ayuda">{{ fmtNum(u.cbm, 2) }} m³ · {{ fmtNum(u.peso_bruto, 0) }} kg (no nominal capacity)</p>
            <p v-for="a in u.alertas" :key="a" class="nota error mt-chico"><Icono nombre="alerta" />{{ a }}</p>
          </div>
        </div>

        <div class="fila-flex mt">
          <h3>Cargo of {{ u.nombre }}</h3>
          <span class="ayuda">{{ plural(u.facturas, 'invoice', 'invoices') }} · {{ plural(u.cajas, 'carton', 'cartons') }} · {{ u.recolectados }} of {{ u.packing_lists }} picked up</span>
          <span class="separar"></span>
          <template v-if="!cerrado">
            <button v-if="!u.packing_lists" class="btn btn-fantasma btn-peligro" @click="eliminarUnidad"><Icono nombre="basura" :tam="15" />Delete {{ unidadTxt[0].toLowerCase() }}</button>
            <button class="btn btn-primario" @click="abrirCajon"><Icono nombre="mas" />Assign cargo</button>
          </template>
        </div>
        <div class="tabla-marco mt-chico" style="box-shadow: none">
          <table class="tabla">
            <thead>
              <tr>
                <th v-if="!cerrado" class="chk"><input type="checkbox" aria-label="Select all assigned" :checked="selA.todos(u.asignados.map((p) => p.id))" @change="selA.alternarTodos(u.asignados.map((p) => p.id))" /></th>
                <ThOrden campo="factura" :orden="tablaA.estado.orden" @ordenar="tablaA.ordenar">Invoice</ThOrden>
                <ThOrden campo="numero" :orden="tablaA.estado.orden" @ordenar="tablaA.ordenar">Packing list</ThOrden>
                <ThOrden campo="proveedor" :orden="tablaA.estado.orden" @ordenar="tablaA.ordenar">Supplier · brands</ThOrden>
                <ThOrden campo="asignacion" :orden="tablaA.estado.orden" @ordenar="tablaA.ordenar">Assignment</ThOrden>
                <ThOrden campo="fecha_xf" :orden="tablaA.estado.orden" @ordenar="tablaA.ordenar">XF</ThOrden>
                <ThOrden campo="recolectado_en" :orden="tablaA.estado.orden" @ordenar="tablaA.ordenar">Pickup</ThOrden>
                <ThOrden campo="fecha_tienda" :orden="tablaA.estado.orden" @ordenar="tablaA.ordenar">In store</ThOrden>
                <th>Contents</th>
                <ThOrden campo="cajas" :orden="tablaA.estado.orden" num @ordenar="tablaA.ordenar">Cartons</ThOrden>
                <ThOrden campo="peso_bruto" :orden="tablaA.estado.orden" num @ordenar="tablaA.ordenar">Gross kg</ThOrden>
                <ThOrden campo="cbm" :orden="tablaA.estado.orden" num @ordenar="tablaA.ordenar">m³</ThOrden>
              </tr>
            </thead>
            <tbody>
              <tr v-for="p in tablaA.filas.value" :key="p.id" :class="{ seleccionada: selA.tiene(p.id) }">
                <td v-if="!cerrado" class="chk"><input type="checkbox" :aria-label="`Select ${p.factura} ${p.numero}`" :checked="selA.tiene(p.id)" @change="selA.alternar(p.id)" /></td>
                <td><router-link :to="`/facturas/${p.factura_id}`" class="fuerte">{{ p.factura }}</router-link><span class="sub codigo">{{ p.ocs?.join(', ') }}</span></td>
                <td><router-link :to="`/packing-lists/${p.id}`" class="cajas-rango">{{ p.numero }}</router-link> <EstadoBadge :estado="p.estado" /></td>
                <td>{{ p.proveedor }}<span v-if="p.marcas?.length" class="sub">{{ p.marcas.join(' · ') }}</span></td>
                <td>
                  <EstadoBadge :estado="p.asignacion" />
                  <span v-if="p.asignacion === 'TENTATIVA' && !p.puede_confirmar" class="sub">{{ p.motivo_no_confirmable }}</span>
                </td>
                <td>{{ fmtFecha(p.fecha_xf) }}</td>
                <td>
                  <template v-if="p.recolectado_en">
                    {{ fmtFecha(p.recolectado_en) }}
                    <span v-if="p.fecha_xf && p.recolectado_en > p.fecha_xf" class="sub" style="color: var(--error)">after the XF</span>
                  </template>
                  <span v-else class="etiqueta aviso" style="margin-left: 0">Pending</span>
                </td>
                <td>{{ fmtFecha(p.fecha_tienda) }}</td>
                <td>{{ porUnidadTxt(p.por_unidad, 'cantidad') }}</td>
                <td class="num">{{ fmtNum(p.cajas) }}</td>
                <td class="num">{{ fmtNum(p.peso_bruto, 1) }}</td>
                <td class="num">{{ fmtNum(p.cbm, 2) }}</td>
              </tr>
              <tr v-if="!u.asignados.length">
                <td colspan="12" class="vacio">
                  <Icono nombre="contenedor" :tam="28" />
                  <p>The load unit is empty.</p>
                  <button v-if="!cerrado" class="btn btn-primario" @click="abrirCajon"><Icono nombre="mas" />Assign cargo</button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <BarraSeleccion :cantidad="selA.ids.size" singular="PL selected" plural="PLs selected" @limpiar="selA.limpiar()">
          <template #resumen>{{ fmtNum(totSelA.cajas) }} cartons · {{ fmtNum(totSelA.cbm, 2) }} m³</template>
          <button class="btn btn-primario" :disabled="ocupado || !selAsignados.some((p) => p.asignacion === 'TENTATIVA' && p.puede_confirmar)" @click="confirmar"><Icono nombre="check" :tam="15" />Confirm</button>
          <button class="btn" :disabled="ocupado || selAsignados.some((p) => p.estado !== 'FINALIZADO')" title="Finalized packing lists only" @click="abrirRecoleccion"><Icono nombre="camion" :tam="15" />Mark picked up</button>
          <button v-if="selAsignados.some((p) => p.recolectado_en)" class="btn" :disabled="ocupado" @click="recolectar(null)">Remove pickup</button>
          <button class="btn" :disabled="!u.otras_unidades.length" @click="modal = { tipo: 'mover', destino: u.otras_unidades[0]?.id, modo: 'AUTO', motivo: '' }"><Icono nombre="mover" :tam="15" />Move to another unit</button>
          <button class="btn btn-peligro" @click="modal = { tipo: 'quitar', motivo: '' }">Remove</button>
        </BarraSeleccion>
      </template>
      <div v-else class="vacio">
        <Icono nombre="contenedor" :tam="28" />
        <p>This shipment has no load units yet. Add a {{ unidadTxt[0].toLowerCase() }}.</p>
        <button class="btn btn-primario" @click="abrirNuevaUnidad"><Icono nombre="mas" />Add {{ unidadTxt[0].toLowerCase() }}</button>
      </div>
    </section>

    <div v-if="e.notify" class="partes mt">
      <TarjetaParte titulo="Notify party" icono="ubicacion" :parte="e.notify" />
    </div>

    <div class="dos-columnas mt">
      <section class="panel">
        <div class="panel-cabeza">
          <div><h2>Tracking</h2><p>Departure, arrival, delivery and receipt events change the shipment status.</p></div>
          <button class="btn btn-chico" @click="abrirEvento('OTRO')"><Icono nombre="mas" :tam="14" />Event</button>
        </div>
        <ul class="linea-tiempo">
          <li v-for="ev in [...e.eventos].reverse()" :key="ev.id">
            <span class="ayuda">{{ fmtFechaHoraLocal(ev.fecha) }}</span>
            <span><b>{{ nombreEvento(ev.tipo) }}</b>{{ ev.ubicacion ? ` · ${ev.ubicacion}` : '' }}<span v-if="ev.observacion" class="sub">{{ ev.observacion }}</span></span>
          </li>
          <li v-if="!e.eventos.length"><span></span><span class="ayuda">No events yet.</span></li>
        </ul>
      </section>
      <section class="panel">
        <div class="panel-cabeza">
          <div><h2>Change history</h2><p>Who changed dates, load units or cargo.</p></div>
          <button v-if="e.historial.length > 5" class="btn btn-chico btn-fantasma" @click="verHistorial = !verHistorial">{{ verHistorial ? 'See less' : `See all (${e.historial.length})` }}</button>
        </div>
        <ul class="linea-tiempo">
          <li v-for="(h, i) in verHistorial ? e.historial : e.historial.slice(0, 5)" :key="i">
            <span class="ayuda">{{ fmtFechaHora(h.fecha) }}<br />{{ h.usuario }}</span>
            <span>
              <b>{{ ACCIONES[h.accion] || h.accion }}</b>
              <span class="sub">{{ detalleHistorial(h) }}</span>
              <span v-if="h.motivo" class="sub">Reason: {{ h.motivo }}</span>
            </span>
          </li>
          <li v-if="!e.historial.length"><span></span><span class="ayuda">No changes.</span></li>
        </ul>
      </section>
    </div>
  </template>

  <!-- Assign cargo -->
  <div v-if="cajon" class="cajon-fondo" @click="cajon = false"></div>
  <aside v-if="cajon && u" class="cajon" style="width: min(760px, 100vw)" aria-label="Assign cargo">
    <div class="cajon-cabeza">
      <div>
        <h2>Assign cargo to {{ u.nombre }}</h2>
        <p>Packing lists without a load unit, grouped by invoice. Tick an invoice to take all its PLs.</p>
      </div>
      <button class="btn-icono" type="button" aria-label="Close" @click="cajon = false"><Icono nombre="cerrar" :tam="20" /></button>
    </div>
    <div class="cajon-cuerpo">
      <div class="filtros">
        <label class="buscador">
          <Icono nombre="buscar" :tam="16" />
          <input v-model="filtros.q" type="search" placeholder="Search invoice number" aria-label="Search invoice" @input="buscar" />
        </label>
        <label class="check"><input v-model="filtros.solo_listos" type="checkbox" @change="cargarDisponibles" /> Only ready to confirm</label>
      </div>
      <div class="tabla-marco" style="box-shadow: none">
        <table class="tabla">
          <thead>
            <tr>
              <th class="chk"><input type="checkbox" aria-label="Select everything available" :checked="selD.todos(todosDisponibles.map((p) => p.id))" @change="selD.alternarTodos(todosDisponibles.map((p) => p.id))" /></th>
              <th><span class="oculto-visual">See PLs</span></th>
              <th>Invoice</th>
              <th>Packing lists</th>
              <th class="num">Cartons</th>
              <th class="num">m³</th>
            </tr>
          </thead>
          <tbody>
            <template v-for="g in disponibles" :key="g.factura_id">
              <tr :class="{ seleccionada: selD.todos(g.packing_lists.map((p) => p.id)) }">
                <td class="chk">
                  <input type="checkbox" :aria-label="`Select the whole invoice ${g.factura}`" :checked="selD.todos(g.packing_lists.map((p) => p.id))" @change="selD.alternarTodos(g.packing_lists.map((p) => p.id))" />
                </td>
                <td><button class="btn-icono" :aria-expanded="abiertas.has(g.factura_id)" :aria-label="`See the PLs of ${g.factura}`" @click="alternarAbierta(g.factura_id)"><Icono :nombre="abiertas.has(g.factura_id) ? 'abajo' : 'derecha'" :tam="16" /></button></td>
                <td><b>{{ g.factura }}</b> <EstadoBadge :estado="g.factura_estado" /><span class="sub">{{ g.proveedor }}</span></td>
                <td>
                  {{ plural(g.packing_lists.length, 'PL', 'PLs') }}
                  <span v-if="g.todos_confirmables" class="etiqueta ok">Ready</span>
                  <span v-else class="etiqueta aviso">Will go tentative</span>
                </td>
                <td class="num">{{ fmtNum(g.cajas) }}</td>
                <td class="num">{{ fmtNum(g.cbm, 2) }}</td>
              </tr>
              <template v-if="abiertas.has(g.factura_id)">
                <tr v-for="p in g.packing_lists" :key="p.id" :class="{ seleccionada: selD.tiene(p.id) }">
                  <td></td>
                  <td class="chk"><input type="checkbox" :aria-label="`Select ${p.numero}`" :checked="selD.tiene(p.id)" @change="selD.alternar(p.id)" /></td>
                  <td><span class="cajas-rango">{{ p.numero }}</span> <EstadoBadge :estado="p.estado" /><span v-if="!p.puede_confirmar" class="sub">{{ p.motivo_no_confirmable }}</span></td>
                  <td>{{ porUnidadTxt(p.por_unidad, 'cantidad') }}</td>
                  <td class="num">{{ fmtNum(p.cajas) }}</td>
                  <td class="num">{{ fmtNum(p.cbm, 2) }}</td>
                </tr>
              </template>
            </template>
            <tr v-if="!disponibles.length"><td colspan="6" class="vacio">No packing lists without a load unit match these filters.</td></tr>
          </tbody>
        </table>
      </div>
    </div>
    <div class="cajon-pie">
      <div v-if="proyeccion && selD.ids.size" class="linea-avance">
        <span class="ayuda">With the selection: {{ fmtNum(proyeccion.cbm, 2) }} m³ ({{ Math.round(proyeccion.pct) }}% of the volume)</span>
        <Avance :porcentaje="proyeccion.pct" />
      </div>
      <p v-if="proyeccion && proyeccion.pct > 100" class="nota error"><Icono nombre="alerta" />The selection exceeds the unit's nominal capacity.</p>
      <p v-if="sugerencia?.length" class="nota info sugerencia-unidades">
        <Icono nombre="contenedor" />
        <span>For {{ fmtNum(totSelD.cbm, 2) }} m³ and {{ fmtNum(totSelD.kg, 0) }} kg the suggested load is <b>{{ sugerencia[0].texto }}</b>
          <template v-if="sugerencia[0].pct_cbm"> ({{ fmtNum(sugerencia[0].pct_cbm, 0) }}% of the volume)</template>.
          <template v-if="sugerencia[0].nota"> {{ sugerencia[0].nota }}</template>
          <template v-if="sugerencia.length > 1"> Other options: {{ sugerencia.slice(1).map((o) => o.texto).join(' · ') }}.</template>
        </span>
      </p>
      <label class="check"><input v-model="confirmarListos" type="checkbox" /> Confirm right away the ones that are ready (invoice and PL finalized); the rest stay tentative</label>
      <div class="fila-flex">
        <span class="ayuda">{{ plural(selD.ids.size, 'PL selected', 'PLs selected') }}<template v-if="selD.ids.size && confirmarListos"> · {{ listosSel }} will be confirmed</template></span>
        <button class="btn btn-primario separar" :disabled="ocupado || !selD.ids.size" @click="asignar"><Icono nombre="contenedor" :tam="16" />Assign to {{ u.nombre }}</button>
      </div>
    </div>
  </aside>

  <Modal v-if="modal?.tipo === 'unidad'" :titulo="`Add ${unidadTxt[0].toLowerCase()}`" @cerrar="modal = null">
    <div class="rejilla-campos">
      <label class="campo"><span class="req">Type</span>
        <select v-model="modal.unidad"><option v-for="t in e.tipos_unidad" :key="t.codigo" :value="t.codigo">{{ tipoTxt(t) }}</option></select>
      </label>
      <label class="campo"><span>Number (optional)</span><input v-model="modal.numero" :placeholder="{ MARITIMO: 'MSKU 123456-7', AEREO: '045-12345675', TERRESTRE: 'Plate C-123456' }[e.tipo_transporte]" /></label>
      <label v-if="tipoElegido?.requiere_sello" class="campo"><span>Seal (optional)</span><input v-model="modal.sello" /></label>
    </div>
    <p class="ayuda">The number<template v-if="tipoElegido?.requiere_sello"> and the seal</template> can be entered later, when the carrier assigns them; <template v-if="tipoElegido?.requiere_sello">they are required</template><template v-else>the number is required</template> to record departure.</p>
    <template #pie>
      <button class="btn" @click="modal = null">Cancel</button>
      <button class="btn btn-primario" :disabled="ocupado" @click="agregarUnidad">Add</button>
    </template>
  </Modal>

  <Modal v-if="modal?.tipo === 'evento'" titulo="Record event" @cerrar="modal = null">
    <div class="rejilla-campos">
      <label class="campo"><span class="req">Event</span>
        <select v-model="modal.evento"><option v-for="[v, t] in eventosPermitidos" :key="v" :value="v">{{ t }}</option></select>
      </label>
      <label class="campo"><span class="req">Date and time</span><input v-model="modal.fecha" type="datetime-local" required :min="ultimoEvento?.slice(0, 16)" /></label>
      <label class="campo"><span>Location</span><input v-model="modal.ubicacion" /></label>
      <label class="campo"><span>Remark</span><input v-model="modal.observacion" /></label>
    </div>
    <p class="ayuda">Events go in order: only those following the current status appear, and the date cannot be in the future or before the last event.</p>
    <p v-if="modal.evento === 'SALIDA'" class="nota aviso">To record departure every packing list must be confirmed. Once recorded, the shipment cargo is closed and PLs without pickup are marked picked up on this date.</p>
    <template #pie>
      <button class="btn" @click="modal = null">Cancel</button>
      <button class="btn btn-primario" :disabled="ocupado || !modal.fecha" @click="registrarEvento">Record</button>
    </template>
  </Modal>

  <Modal v-if="modal?.tipo === 'quitar'" titulo="Remove from the load unit" @cerrar="modal = null">
    <p>The {{ selA.ids.size }} packing lists are left without a load unit and become available again.</p>
    <label class="campo"><span :class="{ req: requiereMotivo }">Reason{{ requiereMotivo ? '' : ' (optional)' }}</span><textarea v-model="modal.motivo"></textarea></label>
    <template #pie>
      <button class="btn" @click="modal = null">Back</button>
      <button class="btn btn-peligro" :disabled="ocupado || (requiereMotivo && !modal.motivo.trim())" @click="quitar">Remove</button>
    </template>
  </Modal>

  <Modal v-if="modal?.tipo === 'mover'" titulo="Move to another load unit" @cerrar="modal = null">
    <label class="campo"><span>Destination unit</span>
      <select v-model="modal.destino"><option v-for="o in u.otras_unidades" :key="o.id" :value="o.id">{{ o.nombre }}</option></select>
    </label>
    <label class="check"><input v-model="modal.modo" type="checkbox" true-value="AUTO" false-value="TENTATIVA" /> Confirm the ready ones at the destination</label>
    <label class="campo"><span :class="{ req: requiereMotivo }">Reason{{ requiereMotivo ? '' : ' (optional)' }}</span><textarea v-model="modal.motivo"></textarea></label>
    <template #pie>
      <button class="btn" @click="modal = null">Back</button>
      <button class="btn btn-primario" :disabled="ocupado || !modal.destino || (requiereMotivo && !modal.motivo.trim())" @click="mover">Move</button>
    </template>
  </Modal>

  <Modal v-if="modal?.tipo === 'recoleccion'" titulo="Mark pickup" @cerrar="modal = null">
    <p>{{ plural(selA.ids.size, 'packing list was', 'packing lists were') }} picked up at the supplier's warehouse.</p>
    <label class="campo"><span class="req">Pickup date</span><input v-model="modal.fecha" type="date" :max="hoy()" /></label>
    <p class="ayuda">It is compared with each PO's XF date to measure supplier compliance.</p>
    <template #pie>
      <button class="btn" @click="modal = null">Back</button>
      <button class="btn btn-primario" :disabled="ocupado || !modal.fecha" @click="recolectar(modal.fecha)">Save</button>
    </template>
  </Modal>
</template>
