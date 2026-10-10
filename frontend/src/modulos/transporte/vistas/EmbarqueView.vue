<script setup>
import { ESTADOS_EMBARQUE } from '@/nucleo/estados.js'
import { t, tx } from '@/i18n/index.js'
import { computed, onMounted, reactive, ref, watch } from 'vue'
import Seleccion from '@/componentes/Seleccion.vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '@/nucleo/api'
import Avance from '@/componentes/Avance.vue'
import BarraSeleccion from '@/componentes/BarraSeleccion.vue'
import CeldaEditable from '@/componentes/CeldaEditable.vue'
import EstadoBadge from '@/componentes/EstadoBadge.vue'
import EstadoTiempo from '@/componentes/EstadoTiempo.vue'
import AvisoEdicion from '@/componentes/AvisoEdicion.vue'
import { useEdicion } from '@/composables/useEdicion'
import Icono from '@/componentes/Icono.vue'
import Modal from '@/componentes/Modal.vue'
import SelectBusqueda from '@/componentes/SelectBusqueda.vue'
import TarjetaParte from '@/componentes/TarjetaParte.vue'
import ThOrden from '@/componentes/ThOrden.vue'
import { datosModo, iconoUnidad, useRutas } from '@/composables/useRutas'
import { useTabla } from '@/composables/useTabla'
import Paginacion from '@/componentes/Paginacion.vue'
import { sesion } from '@/stores/sesion'
import { avisar, errorApi, guardando } from '@/stores/ui'
import { ACCIONES, eventosEmbarque, fmtFecha, fmtFechaHora, fmtFechaHoraLocal, fmtNum, plural, porUnidadTxt, useSeleccion } from '@/nucleo/utils'

// El embarque es el espacio de trabajo de logística: sus datos, sus
// contenedores (cada uno con su carga) y el seguimiento, en una sola vista.
const props = defineProps({ id: String })
const route = useRoute()
const router = useRouter()
const e = ref(null)
const u = ref(null)
const unidadId = ref(Number(route.query.unidad) || null)
const disponibles = ref([])
const filtros = reactive({ q: '' })
const selA = useSeleccion()
const selD = useSeleccion()
const abiertas = reactive(new Set())
const modal = ref(null)
const cajon = ref(false)
const ocupado = ref(false)
const verHistorial = ref(false)

const nombreEvento = (t) => eventosEmbarque().find((x) => x[0] === t)?.[1] || t
// La línea de hitos muestra el camino normal (un embarque anulado no lo recorre)
const HITOS = ESTADOS_EMBARQUE.filter(([c]) => c !== 'CANCELADO')
const SIGUIENTE = { PLANIFICADO: 'SALIDA', EN_TRANSITO: 'ARRIBO', ARRIBADO: 'ENTREGA', ENTREGADO: 'RECEPCION' }
// El cuarto valor marca lo que exige el documento de transporte (BL, AWB o
// carta de porte): sin eso no se registra la salida.
const CAMPOS = [
  ['documento_numero', t('Transport document'), 'text', true],
  ['etd', t('ETD (estimated departure)'), 'date', false],
  ['eta', t('ETA (estimated arrival)'), 'date', false],
]
// Al registrar la salida la carga queda cerrada: no se agregan, quitan ni
// mueven PL o contenedores, y los datos del viaje quedan fijos.
const cerrado = computed(() => !!e.value?.cerrado)
// Mientras otra persona lo edita, se ve en solo lectura
const soloLectura = computed(() => !!e.value?.edicion)
const bloqueado = computed(() => cerrado.value || soloLectura.value)
const FIJOS_SALIDA = ['documento_numero', 'transportista_id', 'puerto_origen', 'etd', 'centro']
const fijo = (campo) => soloLectura.value || (cerrado.value && (FIJOS_SALIDA.includes(campo) || (e.value.arribo_real && ['eta', 'puerto_destino'].includes(campo))))
const eventosPermitidos = computed(() => eventosEmbarque().filter(([k]) => (e.value?.eventos_permitidos || []).includes(k)))
const ultimoEvento = computed(() => (e.value?.eventos || []).reduce((a, ev) => (!a || ev.fecha > a ? ev.fecha : a), null))
const exigeSello = computed(() => !!u.value?.requiere_sello)
const modo = computed(() => datosModo(e.value?.tipo_transporte))
const unidadTxt = computed(() => [modo.value.unidad, modo.value.unidades])
const indiceEstado = computed(() => HITOS.findIndex(([k]) => k === e.value?.estado))
const icono = computed(() => modo.value.icono)
const totales = computed(() => (e.value?.unidades || []).reduce((a, x) => ({
  pls: a.pls + x.packing_lists, cajas: a.cajas + x.cajas, cbm: a.cbm + x.cbm, kg: a.kg + x.peso_bruto,
}), { pls: 0, cajas: 0, cbm: 0, kg: 0 }))

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
const tipoTxt = (u) => `${u.codigo} · ${u.nombre} (${u.modalidad}${u.capacidad_cbm ? `, ${fmtNum(u.capacidad_cbm, 0)} m³` : ''}${u.capacidad_kg ? t(', {0} kg', [fmtNum(u.capacidad_kg, 0)]) : ''})`
const tipoElegido = computed(() => e.value?.tipos_unidad.find((t) => t.codigo === modal.value?.unidad))
function abrirNuevaUnidad() {
  const tipos = e.value.tipos_unidad
  modal.value = { tipo: 'unidad', unidad: (tipos.find((t) => t.codigo === '40HC') || tipos[0])?.codigo || '', numero: '', sello: '' }
}
async function agregarUnidad() {
  const m = modal.value
  const r = await ejecutar(() => api.post(`/embarques/${props.id}/unidades`, { tipo: m.unidad, numero: m.numero || null, sello: m.sello || null }),
    (x) => t('{0} {1} added.', [unidadTxt.value[0], x.etiqueta]))
  if (r) unidadId.value = r.id
}
function eliminarUnidad() {
  ejecutar(() => api.del(`/unidades/${unidadId.value}`), t('{0} deleted.', [u.value.nombre]))
}

// ---- Carga del contenedor --------------------------------------------------
const todosDisponibles = computed(() => disponibles.value.flatMap((g) => g.packing_lists))
const suma = (pls) => pls.reduce((a, p) => ({ cajas: a.cajas + p.cajas, cbm: a.cbm + p.cbm, kg: a.kg + p.peso_bruto }), { cajas: 0, cbm: 0, kg: 0 })
const tablaA = useTabla(computed(() => u.value?.asignados || []), { porPagina: 50, valores: { contenido: (p) => p.cajas } })
const selAsignados = computed(() => (u.value?.asignados || []).filter((p) => selA.tiene(p.id)))
const selDisponibles = computed(() => todosDisponibles.value.filter((p) => selD.tiene(p.id)))
const totSelA = computed(() => suma(selAsignados.value))
const totSelD = computed(() => suma(selDisponibles.value))
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
  ejecutar(() => api.post(`/unidades/${unidadId.value}/asignar`, { pl_ids: selD.lista() }), textoAsignados)
    .then((r) => r && (cajon.value = false))
}
function textoAsignados(r) {
  return `${plural(r.asignados, t('packing list assigned'), t('packing lists assigned'))}.`
}
// Recolección en la bodega del proveedor: se marca antes de zarpar
const hoy = () => new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 10)
function abrirRecoleccion() {
  modal.value = { tipo: 'recoleccion', fecha: hoy() }
}
function recolectar(fecha) {
  ejecutar(() => api.post('/recoleccion', { pl_ids: selA.lista(), fecha }),
    (r) => (fecha ? `${plural(r.actualizados, t('packing list picked up'), t('packing lists picked up'))}.` : t('Pickup removed.')))
}
function quitar() {
  ejecutar(() => api.post(`/unidades/${unidadId.value}/desasignar`, { pl_ids: selA.lista(), motivo: modal.value.motivo || null }),
    t('Packing lists removed from the load unit.'))
}
function mover() {
  const { destino, motivo } = modal.value
  ejecutar(() => api.post(`/unidades/${destino}/asignar`, { pl_ids: selA.lista(), motivo: motivo || null }),
    t('Packing lists moved to the other load unit.'))
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
// Anular un embarque que no salió: su carga vuelve a estar disponible
function cancelarEmbarque() {
  modal.value = { tipo: 'cancelar', motivo: '' }
}
function confirmarCancelacion() {
  ejecutar(() => api.post(`/embarques/${props.id}/cancelar`, { motivo: modal.value.motivo }), t('Shipment called off: its packing lists are available again.'))
}

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
  }), (r) => (r.estado === e.value.estado ? t('Event recorded.') : t('Event recorded; the shipment is now {0}.', [HITOS.find(([k]) => k === r.estado)?.[1].toLowerCase()])))
}
const detalleHistorial = (h) => (h.detalle ? Object.entries(h.detalle).map(([k, v]) => `${k.replaceAll('_', ' ')}: ${Array.isArray(v) ? t('{0} to {1}', [v[0] ?? '—', v[1] ?? '—']) : v}`).join(', ') : '')

onMounted(() => {
  cargar()
  cargarRutas()
})
watch(() => sesion.proveedorId, () => cajon.value && cargarDisponibles())

// Edición exclusiva: una persona edita y las demás ven en solo lectura
const edicion = useEdicion('embarque', () => Number(props.id), () => ({ editable: !!e.value, edicion: e.value?.edicion }), cargar)
</script>

<template>
  <template v-if="e">
    <router-link to="/transporte" class="volver"><Icono nombre="atras" :tam="15" />{{ t('Shipments') }}</router-link>
    <AvisoEdicion :edicion="e.edicion" :pausado="edicion.pausado.value" entidad="embarque" :id="Number(props.id)" @liberado="cargar" @continuar="edicion.continuar" />
    <section class="doc-cabeza">
      <div class="doc-fila">
        <Icono :nombre="icono" :tam="26" />
        <span class="doc-numero">{{ tx(e.codigo) }}</span>
        <EstadoBadge :estado="e.estado" tipo="embarque" />
        <EstadoTiempo :estado="e.estado_tiempo" :holgura="e.holgura_dias" />
        <span class="doc-sub">{{ tx(modo.nombre) }}</span>
        <span v-if="e.modalidad" class="etiqueta acento" :title="tx(e.modalidad === 'MIXTO' ? t('Combines units of different modalities (e.g. FCL and LCL)') : '')">{{ tx(e.modalidad) }}</span>
        <div class="doc-acciones">
          <button v-if="!soloLectura" class="btn" @click="abrirEvento('OTRO')"><Icono nombre="ubicacion" />{{ t('Record event') }}</button>
          <button v-if="SIGUIENTE[e.estado] && !soloLectura" class="btn btn-primario" :disabled="e.estado === 'PLANIFICADO' && !totales.pls" @click="abrirEvento()">
            <Icono nombre="flecha" />{{ t('Record {0}', [nombreEvento(SIGUIENTE[e.estado]).toLowerCase()]) }}
          </button>
          <button v-if="e.estado === 'PLANIFICADO' && !soloLectura" class="btn btn-fantasma" @click="cancelarEmbarque"><Icono nombre="cerrar" />{{ t('Call off shipment') }}</button>
          <!-- Un botón deshabilitado siempre dice por qué y qué hacer -->
          <span v-if="SIGUIENTE[e.estado] && !soloLectura && e.estado === 'PLANIFICADO' && !totales.pls" class="ayuda bloqueo-motivo">
            <Icono nombre="info" :tam="14" />{{ t('Assign at least one finalized packing list to a load unit below first.') }}
          </span>
        </div>
      </div>
      <ol class="hitos" :aria-label="t('Shipment status')">
        <li v-for="([k, txt], i) in HITOS" :key="k" class="hito" :class="{ hecho: i < indiceEstado || (i === indiceEstado && i === HITOS.length - 1), actual: i === indiceEstado && i < HITOS.length - 1 }">
          <span class="hito-punto"><Icono v-if="i < indiceEstado" nombre="check" :tam="12" /></span>{{ tx(txt) }}
        </li>
      </ol>
      <p v-if="cerrado" class="bloqueo mt"><Icono nombre="candado" />
        <span><b>{{ t('Cargo closed.') }}</b> {{ t('The shipment departed') }}<template v-if="e.salida_real"> {{ t('on {0}', [fmtFecha(e.salida_real)]) }}</template>{{ t(': packing lists and load units can no longer be added, removed or moved, and the voyage data is fixed. Only the next tracking events can be recorded.') }}</span>
      </p>
      <div class="doc-datos">
        <label v-for="[campo, texto, tipo, obligatorio] in CAMPOS" :key="campo" class="dato">
          <span :class="{ req: obligatorio }">{{ tx(campo === 'documento_numero' ? modo.doc : texto) }}</span>
          <b v-if="fijo(campo)" :title="t('Fixed since departure')">{{ tx(tipo === 'date' ? fmtFecha(e[campo]) : e[campo] || '—') }} <Icono nombre="candado" :tam="12" /></b>
          <CeldaEditable v-else :tipo="tipo" :valor="e[campo]" :guardar="guardar(campo)" :etiqueta="tx(texto)" :vacia-texto="tx(obligatorio ? t('Required') : '')" />
        </label>
        <div class="dato"><span class="req">{{ tx(modo.transportista) }}</span>
          <b v-if="fijo('transportista_id')">{{ tx(e.transportista || '—') }} <Icono nombre="candado" :tam="12" /></b>
          <SelectBusqueda v-else :model-value="e.transportista_id || ''" :opciones="opcionesTransportista" :vacio="t('Not defined')" :etiqueta="tx(modo.transportista)"
                          @change="(v) => cambiarRuta('transportista_id', v)" />
        </div>
        <div class="dato"><span class="req">{{ t('Receiving plant') }}</span>
          <b v-if="bloqueado">{{ tx(e.centro || '—') }} <Icono nombre="candado" :tam="12" /></b>
          <SelectBusqueda v-else :model-value="e.centro || ''" :opciones="centros" :vacio="t('Set by the first cargo')" :etiqueta="t('Plant')"
                          @change="(v) => cambiarRuta('centro', v)" />
        </div>
        <div class="dato"><span class="req">{{ t('{0} of loading', [modo.puerto]) }}</span>
          <b v-if="fijo('puerto_origen')">{{ tx(nombrePuerto(e.puerto_origen)) }} <Icono nombre="candado" :tam="12" /></b>
          <SelectBusqueda v-else :model-value="e.puerto_origen || ''" :opciones="origenes" :vacio="t('Not defined')" :etiqueta="t('{0} of loading', [modo.puerto])"
                          @change="(v) => cambiarRuta('puerto_origen', v)" />
        </div>
        <div class="dato"><span class="req">{{ t('{0} of discharge', [modo.puerto]) }}</span>
          <b v-if="fijo('puerto_destino')">{{ tx(nombrePuerto(e.puerto_destino)) }} <Icono nombre="candado" :tam="12" /></b>
          <SelectBusqueda v-else :model-value="e.puerto_destino || ''" :opciones="destinos" :vacio="t('Not defined')" :etiqueta="t('{0} of discharge', [modo.puerto])"
                          @change="(v) => cambiarRuta('puerto_destino', v)" />
          <small v-if="!fijo('puerto_destino') && e.puertos_sugeridos?.length > 1" class="ayuda">{{ t('The plant receives via {0}.', [e.puertos_sugeridos.join(', ')]) }}</small>
        </div>
        <div class="dato"><span>{{ t('Actual departure') }}</span><b>{{ fmtFecha(e.salida_real) }}</b></div>
        <div class="dato"><span>{{ t('Actual arrival') }}</span><b>{{ fmtFecha(e.arribo_real) }}</b></div>
      </div>
      <div class="empaque-resumen">
        <div class="cifra"><span>{{ tx(unidadTxt[1]) }}</span><b>{{ tx(e.unidades.length) }}</b></div>
        <div class="cifra"><span>{{ t('Packing lists') }}</span><b>{{ tx(totales.pls) }}</b></div>
        <div class="cifra"><span>{{ t('Cartons') }}</span><b>{{ fmtNum(totales.cajas) }}</b></div>
        <div class="cifra"><span>{{ t('Volume') }}</span><b>{{ fmtNum(totales.cbm, 2) }} m³</b></div>
        <div class="cifra"><span>{{ t('Gross weight') }}</span><b>{{ t('{0} kg', [fmtNum(totales.kg, 0)]) }}</b></div>
      </div>
    </section>

    <section class="panel">
      <div class="panel-cabeza"><div><h2>{{ tx(unidadTxt[1]) }}</h2><p>{{ t('Choose a unit to see and assign its cargo. Only {0} unit types are offered.', [modo.nombre.toLowerCase()]) }}</p></div></div>
      <div class="unidades-pestanas" role="tablist">
        <button v-for="x in e.unidades" :key="x.id" class="unidad-pestana" role="tab" :aria-selected="x.id === unidadId" @click="unidadId = x.id">
          <span class="fila-flex"><Icono :nombre="iconoUnidad(e.tipo_transporte)" /><span class="unidad-nombre">{{ tx(x.nombre) }}</span><span class="etiqueta" :title="tx(x.tipo_nombre)">{{ tx(x.tipo) }}</span><span v-if="x.modalidad" class="etiqueta acento">{{ tx(x.modalidad) }}</span></span>
          <Avance v-if="x.capacidad_cbm" :porcentaje="x.pct_cbm || 0" />
          <span class="ayuda">{{ plural(x.packing_lists, 'PL', t('PLs')) }} · {{ fmtNum(x.cbm, 1) }} m³</span>
          <span v-if="x.marcas?.length" class="ayuda">{{ tx(x.marcas.join(' · ')) }}</span>
          <EstadoTiempo v-if="x.estado_tiempo" :estado="x.estado_tiempo" :holgura="x.holgura_dias" />
          <span v-for="a in x.alertas" :key="a" class="etiqueta error">{{ tx(a) }}</span>
        </button>
        <button v-if="!bloqueado" class="unidad-pestana agregar" @click="abrirNuevaUnidad"><Icono nombre="mas" :tam="20" />{{ t('Add {0}', [unidadTxt[0].toLowerCase()]) }}</button>
      </div>

      <template v-if="u">
        <div class="dos-columnas mt" style="align-items: start">
          <div>
            <div class="rejilla-campos">
              <label class="dato"><span class="req">{{ t('{0} number', [unidadTxt[0]]) }}</span>
                <b v-if="bloqueado">{{ tx(u.numero || '—') }}</b>
                <CeldaEditable v-else :valor="u.numero" :guardar="guardarUnidad('numero')" :etiqueta="t('Number')" :vacia-texto="t('Required')" />
              </label>
              <label class="dato"><span :class="{ req: exigeSello }">{{ t('Seal') }}</span>
                <b v-if="bloqueado">{{ tx(u.sello || '—') }}</b>
                <CeldaEditable v-else :valor="u.sello" :guardar="guardarUnidad('sello')" :etiqueta="t('Seal')" :vacia-texto="tx(exigeSello ? t('Required') : '')" />
              </label>
              <div class="dato"><span>{{ t('First in-store date') }}</span><b>{{ fmtFecha(u.fecha_tienda) }}</b></div>
              <div class="dato"><span>{{ t('Arrival vs. store') }}</span>
                <b><EstadoTiempo :estado="u.estado_tiempo" :holgura="u.holgura_dias" /></b>
              </div>
            </div>
          </div>
          <div>
            <div v-if="u.capacidad_cbm" class="linea-avance">
              <span class="ayuda">{{ t('Volume: {0} of {1} m³', [fmtNum(u.cbm, 2), fmtNum(u.capacidad_cbm, 0)]) }}</span>
              <Avance :porcentaje="u.pct_cbm || 0" />
            </div>
            <div v-if="u.capacidad_kg" class="linea-avance mt-chico">
              <span class="ayuda">{{ t('Weight: {0} of {1} kg', [fmtNum(u.peso_bruto, 0), fmtNum(u.capacidad_kg, 0)]) }}</span>
              <Avance :porcentaje="u.pct_kg || 0" />
            </div>
            <p v-if="!u.capacidad_cbm" class="ayuda">{{ t('{0} m³ · {1} kg (no nominal capacity)', [fmtNum(u.cbm, 2), fmtNum(u.peso_bruto, 0)]) }}</p>
            <p v-for="a in u.alertas" :key="a" class="nota error mt-chico"><Icono nombre="alerta" />{{ tx(a) }}</p>
          </div>
        </div>

        <div class="fila-flex mt">
          <h3>{{ t('Cargo of {0}', [u.nombre]) }}</h3>
          <span class="ayuda">{{ t('{0} · {1} · {2} of {3} picked up', [plural(u.facturas, t('invoice'), t('invoices')), plural(u.cajas, t('carton'), t('cartons')), u.recolectados, u.packing_lists]) }}</span>
          <span class="separar"></span>
          <template v-if="!bloqueado">
            <button v-if="!u.packing_lists" class="btn btn-fantasma btn-peligro" @click="eliminarUnidad"><Icono nombre="basura" :tam="15" />{{ t('Delete {0}', [unidadTxt[0].toLowerCase()]) }}</button>
            <button class="btn btn-primario" @click="abrirCajon"><Icono nombre="mas" />{{ t('Assign cargo') }}</button>
          </template>
        </div>
        <div class="tabla-marco mt-chico sin-sombra">
          <table class="tabla" v-tarjetas>
            <thead>
              <tr>
                <th v-if="!bloqueado" class="chk"><input type="checkbox" :aria-label="t('Select all assigned')" :checked="selA.todos(u.asignados.map((p) => p.id))" @change="selA.alternarTodos(u.asignados.map((p) => p.id))" /></th>
                <ThOrden campo="factura" :orden="tablaA.estado.orden" @ordenar="tablaA.ordenar">{{ t('Invoice') }}</ThOrden>
                <ThOrden campo="numero" :orden="tablaA.estado.orden" @ordenar="tablaA.ordenar">{{ t('Packing list') }}</ThOrden>
                <ThOrden campo="proveedor" :orden="tablaA.estado.orden" @ordenar="tablaA.ordenar">{{ t('Supplier · brands') }}</ThOrden>
                <ThOrden campo="asignacion" :orden="tablaA.estado.orden" @ordenar="tablaA.ordenar">{{ t('Assignment') }}</ThOrden>
                <ThOrden campo="fecha_xf" :orden="tablaA.estado.orden" @ordenar="tablaA.ordenar">XF</ThOrden>
                <ThOrden campo="recolectado_en" :orden="tablaA.estado.orden" @ordenar="tablaA.ordenar">{{ t('Pickup') }}</ThOrden>
                <ThOrden campo="fecha_tienda" :orden="tablaA.estado.orden" @ordenar="tablaA.ordenar">{{ t('In store') }}</ThOrden>
                <th>{{ t('Contents') }}</th>
                <ThOrden campo="cajas" :orden="tablaA.estado.orden" num @ordenar="tablaA.ordenar">{{ t('Cartons') }}</ThOrden>
                <ThOrden campo="peso_bruto" :orden="tablaA.estado.orden" num @ordenar="tablaA.ordenar">{{ t('Gross kg') }}</ThOrden>
                <ThOrden campo="cbm" :orden="tablaA.estado.orden" num @ordenar="tablaA.ordenar">m³</ThOrden>
              </tr>
            </thead>
            <tbody>
              <tr v-for="p in tablaA.filas.value" :key="p.id" :class="{ seleccionada: selA.tiene(p.id) }">
                <td v-if="!bloqueado" class="chk"><input type="checkbox" :aria-label="t('Select {0} {1}', [p.factura, p.numero])" :checked="selA.tiene(p.id)" @change="selA.alternar(p.id)" /></td>
                <td><router-link :to="`/facturas/${p.factura_id}`" class="enlace-doc"><strong class="codigo">{{ tx(p.factura) }}</strong></router-link><span class="sub codigo">{{ tx(p.ocs?.join(', ')) }}</span></td>
                <td><router-link :to="`/packing-lists/${p.id}`" class="enlace codigo">{{ tx(p.numero) }}</router-link> <EstadoBadge :estado="p.estado" /></td>
                <td>{{ tx(p.proveedor) }}<span v-if="p.marcas?.length" class="sub">{{ tx(p.marcas.join(' · ')) }}</span></td>
                <td>
                  <EstadoBadge :estado="p.asignacion" />
                  <span v-if="!p.puede_confirmar" class="sub">{{ tx(p.motivo_no_confirmable) }}</span>
                </td>
                <td>{{ fmtFecha(p.fecha_xf) }}</td>
                <td>
                  <template v-if="p.recolectado_en">
                    {{ fmtFecha(p.recolectado_en) }}
                    <span v-if="p.fecha_xf && p.recolectado_en > p.fecha_xf" class="sub texto-error">{{ t('after the XF') }}</span>
                  </template>
                  <span v-else class="etiqueta aviso ms-0">{{ t('Pending') }}</span>
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
                  <p>{{ t('The load unit is empty.') }}</p>
                  <button v-if="!bloqueado" class="btn btn-primario" @click="abrirCajon"><Icono nombre="mas" />{{ t('Assign cargo') }}</button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <!-- Una unidad puede llevar más de 50 listas de empaque: ninguna queda fuera de la vista -->
        <Paginacion v-if="tablaA.total.value > tablaA.estado.porPagina" :page="tablaA.estado.pagina" :size="tablaA.estado.porPagina" :total="tablaA.total.value"
                    @cambiar="(p) => (tablaA.estado.pagina = p)" @tamano="(n) => (tablaA.estado.porPagina = n)" />
        <BarraSeleccion :cantidad="selA.ids.size" :singular="t('PL selected')" :plural="t('PLs selected')" @limpiar="selA.limpiar()">
          <template #resumen>{{ t('{0} cartons · {1} m³', [fmtNum(totSelA.cajas), fmtNum(totSelA.cbm, 2)]) }}</template>
          <button class="btn" :disabled="ocupado || selAsignados.some((p) => p.estado !== 'FINALIZADO')" :title="t('Finalized packing lists only')" @click="abrirRecoleccion"><Icono nombre="camion" :tam="15" />{{ t('Mark picked up') }}</button>
          <button v-if="selAsignados.some((p) => p.recolectado_en)" class="btn" :disabled="ocupado" @click="recolectar(null)">{{ t('Remove pickup') }}</button>
          <button class="btn" :disabled="!u.otras_unidades.length" @click="modal = { tipo: 'mover', destino: u.otras_unidades[0]?.id, motivo: '' }"><Icono nombre="mover" :tam="15" />{{ t('Move to another unit') }}</button>
          <button class="btn btn-peligro" @click="modal = { tipo: 'quitar', motivo: '' }">{{ t('Remove') }}</button>
        </BarraSeleccion>
      </template>
      <div v-else class="vacio">
        <Icono nombre="contenedor" :tam="28" />
        <p>{{ t('This shipment has no load units yet. Add a {0}.', [unidadTxt[0].toLowerCase()]) }}</p>
        <button v-if="!bloqueado" class="btn btn-primario" @click="abrirNuevaUnidad"><Icono nombre="mas" />{{ t('Add {0}', [unidadTxt[0].toLowerCase()]) }}</button>
      </div>
    </section>

    <div v-if="e.notify" class="partes mt">
      <TarjetaParte :titulo="t('Notify party')" icono="ubicacion" :parte="e.notify" />
    </div>

    <div class="dos-columnas mt">
      <section class="panel">
        <div class="panel-cabeza">
          <div><h2>{{ t('Tracking') }}</h2><p>{{ t('Departure, arrival, delivery and receipt events change the shipment status.') }}</p></div>
          <button v-if="!soloLectura" class="btn btn-chico" @click="abrirEvento('OTRO')"><Icono nombre="mas" :tam="14" />{{ t('Event') }}</button>
        </div>
        <ul class="linea-tiempo">
          <li v-for="ev in [...e.eventos].reverse()" :key="ev.id">
            <span class="ayuda">{{ fmtFechaHoraLocal(ev.fecha) }}</span>
            <span><b>{{ tx(nombreEvento(ev.tipo)) }}</b>{{ tx(ev.ubicacion ? ` · ${ev.ubicacion}` : '') }}<span v-if="ev.observacion" class="sub">{{ tx(ev.observacion) }}</span></span>
          </li>
          <li v-if="!e.eventos.length"><span></span><span class="ayuda">{{ t('No events yet.') }}</span></li>
        </ul>
      </section>
      <section class="panel">
        <div class="panel-cabeza">
          <div><h2>{{ t('Change history') }}</h2><p>{{ t('Who changed dates, load units or cargo.') }}</p></div>
          <button v-if="e.historial.length > 5" class="btn btn-chico btn-fantasma" @click="verHistorial = !verHistorial">{{ tx(verHistorial ? t('See less') : t('See all ({0})', [e.historial.length])) }}</button>
        </div>
        <ul class="linea-tiempo">
          <li v-for="(h, i) in verHistorial ? e.historial : e.historial.slice(0, 5)" :key="i">
            <span class="ayuda">{{ fmtFechaHora(h.fecha) }}<br />{{ tx(h.usuario) }}</span>
            <span>
              <b>{{ tx(ACCIONES[h.accion] || h.accion) }}</b>
              <span class="sub">{{ tx(detalleHistorial(h)) }}</span>
              <span v-if="h.motivo" class="sub">{{ t('Reason: {0}', [h.motivo]) }}</span>
            </span>
          </li>
          <li v-if="!e.historial.length"><span></span><span class="ayuda">{{ t('No changes.') }}</span></li>
        </ul>
      </section>
    </div>
  </template>

  <!-- Assign cargo -->
  <div v-if="cajon" class="cajon-fondo" @click="cajon = false"></div>
  <aside v-if="cajon && u" class="cajon" style="width: min(760px, 100vw)" :aria-label="t('Assign cargo')">
    <div class="cajon-cabeza">
      <div>
        <h2>{{ t('Assign cargo to {0}', [u.nombre]) }}</h2>
        <p>{{ t('Packing lists without a load unit, grouped by invoice. Tick an invoice to take all its PLs.') }}</p>
      </div>
      <button class="btn-icono" type="button" :aria-label="t('Close')" @click="cajon = false"><Icono nombre="cerrar" :tam="20" /></button>
    </div>
    <div class="cajon-cuerpo">
      <div class="filtros" v-filtros>
        <label class="buscador">
          <Icono nombre="buscar" :tam="16" />
          <input v-model="filtros.q" type="search" :placeholder="t('Search invoice number')" :aria-label="t('Search invoice')" @input="buscar" />
        </label>
      </div>
      <div class="tabla-marco sin-sombra">
        <table class="tabla" v-tarjetas>
          <thead>
            <tr>
              <th class="chk"><input type="checkbox" :aria-label="t('Select everything available')" :checked="selD.todos(todosDisponibles.map((p) => p.id))" @change="selD.alternarTodos(todosDisponibles.map((p) => p.id))" /></th>
              <th><span class="oculto-visual">{{ t('See PLs') }}</span></th>
              <th>{{ t('Invoice') }}</th>
              <th>{{ t('Packing lists') }}</th>
              <th class="num">{{ t('Cartons') }}</th>
              <th class="num">m³</th>
            </tr>
          </thead>
          <tbody>
            <template v-for="g in disponibles" :key="g.factura_id">
              <tr :class="{ seleccionada: selD.todos(g.packing_lists.map((p) => p.id)) }">
                <td class="chk">
                  <input type="checkbox" :aria-label="t('Select the whole invoice {0}', [g.factura])" :checked="selD.todos(g.packing_lists.map((p) => p.id))" @change="selD.alternarTodos(g.packing_lists.map((p) => p.id))" />
                </td>
                <td><button class="btn-icono" :aria-expanded="abiertas.has(g.factura_id)" :aria-label="t('See the PLs of {0}', [g.factura])" @click="alternarAbierta(g.factura_id)"><Icono :nombre="abiertas.has(g.factura_id) ? 'abajo' : 'derecha'" :tam="16" /></button></td>
                <td><b>{{ tx(g.factura) }}</b> <EstadoBadge :estado="g.factura_estado" /><span class="sub">{{ tx(g.proveedor) }}</span></td>
                <td>
                  {{ plural(g.packing_lists.length, 'PL', t('PLs')) }}
                </td>
                <td class="num">{{ fmtNum(g.cajas) }}</td>
                <td class="num">{{ fmtNum(g.cbm, 2) }}</td>
              </tr>
              <template v-if="abiertas.has(g.factura_id)">
                <tr v-for="p in g.packing_lists" :key="p.id" :class="{ seleccionada: selD.tiene(p.id) }">
                  <td></td>
                  <td class="chk"><input type="checkbox" :aria-label="t('Select {0}', [p.numero])" :checked="selD.tiene(p.id)" @change="selD.alternar(p.id)" /></td>
                  <td><span class="cajas-rango">{{ tx(p.numero) }}</span> <EstadoBadge :estado="p.estado" /></td>
                  <td>{{ porUnidadTxt(p.por_unidad, 'cantidad') }}</td>
                  <td class="num">{{ fmtNum(p.cajas) }}</td>
                  <td class="num">{{ fmtNum(p.cbm, 2) }}</td>
                </tr>
              </template>
            </template>
            <tr v-if="!disponibles.length"><td colspan="6" class="vacio">{{ t('No finalized packing lists without a load unit match these filters.') }}</td></tr>
          </tbody>
        </table>
      </div>
    </div>
    <div class="cajon-pie">
      <div v-if="proyeccion && selD.ids.size" class="linea-avance">
        <span class="ayuda">{{ t('With the selection: {0} m³ ({1}% of the volume)', [fmtNum(proyeccion.cbm, 2), Math.round(proyeccion.pct)]) }}</span>
        <Avance :porcentaje="proyeccion.pct" />
      </div>
      <p v-if="proyeccion && proyeccion.pct > 100" class="nota error"><Icono nombre="alerta" />{{ t('The selection exceeds the unit\'s nominal capacity.') }}</p>
      <p v-if="sugerencia?.length" class="nota info sugerencia-unidades">
        <Icono nombre="contenedor" />
        <span>{{ t('For {0} m³ and {1} kg the suggested load is', [fmtNum(totSelD.cbm, 2), fmtNum(totSelD.kg, 0)]) }} <b>{{ tx(sugerencia[0].texto) }}</b>
          <template v-if="sugerencia[0].pct_cbm"> {{ t('({0}% of the volume)', [fmtNum(sugerencia[0].pct_cbm, 0)]) }}</template>.
          <template v-if="sugerencia[0].nota"> {{ tx(sugerencia[0].nota) }}</template>
          <template v-if="sugerencia.length > 1"> {{ t('Other options: {0}.', [sugerencia.slice(1).map((o) => o.texto).join(' · ')]) }}</template>
        </span>
      </p>
      <p class="ayuda">{{ t('Only finalized invoices and packing lists are listed: a document goes on a shipment once it is final.') }}</p>
      <div class="fila-flex">
        <span class="ayuda">{{ plural(selD.ids.size, t('PL selected'), t('PLs selected')) }}</span>
        <button class="btn btn-primario separar" :disabled="ocupado || !selD.ids.size" @click="asignar"><Icono nombre="contenedor" :tam="16" />{{ t('Assign to {0}', [u.nombre]) }}</button>
      </div>
    </div>
  </aside>

  <Modal v-if="modal?.tipo === 'unidad'" :titulo="t('Add {0}', [unidadTxt[0].toLowerCase()])" @cerrar="modal = null">
    <div class="rejilla-campos">
      <label class="campo"><span class="req">{{ t('Type') }}</span>
        <Seleccion v-model="modal.unidad"><option v-for="txt in e.tipos_unidad" :key="txt.codigo" :value="txt.codigo">{{ tx(tipoTxt(txt)) }}</option></Seleccion>
      </label>
      <label class="campo"><span>{{ t('Number (optional)') }}</span><input v-model="modal.numero" /></label>
      <label v-if="tipoElegido?.requiere_sello" class="campo"><span>{{ t('Seal (optional)') }}</span><input v-model="modal.sello" /></label>
    </div>
    <p class="ayuda">{{ t('The number') }}<template v-if="tipoElegido?.requiere_sello"> {{ t('and the seal') }}</template> {{ t('can be entered later, when the carrier assigns them;') }} <template v-if="tipoElegido?.requiere_sello">{{ t('they are required') }}</template><template v-else>{{ t('the number is required') }}</template> {{ t('to record departure.') }}</p>
    <template #pie>
      <button class="btn" @click="modal = null">{{ t('Cancel') }}</button>
      <button class="btn btn-primario" :disabled="ocupado" @click="agregarUnidad">{{ t('Add') }}</button>
    </template>
  </Modal>

  <Modal v-if="modal?.tipo === 'evento'" :titulo="t('Record event')" @cerrar="modal = null">
    <div class="rejilla-campos">
      <label class="campo"><span class="req">{{ t('Event') }}</span>
        <Seleccion v-model="modal.evento"><option v-for="[v, txt] in eventosPermitidos" :key="v" :value="v">{{ tx(txt) }}</option></Seleccion>
      </label>
      <label class="campo"><span class="req">{{ t('Date and time') }}</span><input v-model="modal.fecha" type="datetime-local" required :min="ultimoEvento?.slice(0, 16)" /></label>
      <label class="campo"><span>{{ t('Location') }}</span><input v-model="modal.ubicacion" /></label>
      <label class="campo"><span>{{ t('Remark') }}</span><input v-model="modal.observacion" /></label>
    </div>
    <p class="ayuda">{{ t('Events go in order: only those following the current status appear, and the date cannot be in the future or before the last event.') }}</p>
    <p v-if="modal.evento === 'SALIDA'" class="nota aviso">{{ t('To record departure every packing list must be confirmed. Once recorded, the shipment cargo is closed and PLs without pickup are marked picked up on this date.') }}</p>
    <template #pie>
      <button class="btn" @click="modal = null">{{ t('Cancel') }}</button>
      <button class="btn btn-primario" :disabled="ocupado || !modal.fecha" @click="registrarEvento">{{ t('Record') }}</button>
    </template>
  </Modal>

  <Modal v-if="modal?.tipo === 'cancelar'" :titulo="t('Call off shipment')" @cerrar="modal = null">
    <p>{{ t('The shipment is called off and its packing lists leave their load units, available for another shipment. This cannot be undone.') }}</p>
    <label class="campo"><span class="req">{{ t('Reason') }}</span><textarea v-model="modal.motivo"></textarea></label>
    <template #pie>
      <button class="btn" @click="modal = null">{{ t('Back') }}</button>
      <button class="btn btn-peligro" :disabled="ocupado || !modal.motivo.trim()" @click="confirmarCancelacion">{{ t('Call off shipment') }}</button>
    </template>
  </Modal>

  <Modal v-if="modal?.tipo === 'quitar'" :titulo="t('Remove from the load unit')" @cerrar="modal = null">
    <p>{{ t('The {0} packing lists are left without a load unit and become available again.', [selA.ids.size]) }}</p>
    <label class="campo"><span :class="{ req: requiereMotivo }">{{ t('Reason{0}', [requiereMotivo ? '' : t(' (optional)')]) }}</span><textarea v-model="modal.motivo"></textarea></label>
    <template #pie>
      <button class="btn" @click="modal = null">{{ t('Back') }}</button>
      <button class="btn btn-peligro" :disabled="ocupado || (requiereMotivo && !modal.motivo.trim())" @click="quitar">{{ t('Remove') }}</button>
    </template>
  </Modal>

  <Modal v-if="modal?.tipo === 'mover'" :titulo="t('Move to another load unit')" @cerrar="modal = null">
    <label class="campo"><span>{{ t('Destination unit') }}</span>
      <Seleccion v-model="modal.destino"><option v-for="o in u.otras_unidades" :key="o.id" :value="o.id">{{ tx(o.nombre) }}</option></Seleccion>
    </label>
    <label class="campo"><span :class="{ req: requiereMotivo }">{{ t('Reason{0}', [requiereMotivo ? '' : t(' (optional)')]) }}</span><textarea v-model="modal.motivo"></textarea></label>
    <template #pie>
      <button class="btn" @click="modal = null">{{ t('Back') }}</button>
      <button class="btn btn-primario" :disabled="ocupado || !modal.destino || (requiereMotivo && !modal.motivo.trim())" @click="mover">{{ t('Move') }}</button>
    </template>
  </Modal>

  <Modal v-if="modal?.tipo === 'recoleccion'" :titulo="t('Mark pickup')" @cerrar="modal = null">
    <p>{{ t('Packing lists picked up at the supplier\'s warehouse: {0}.', [fmtNum(selA.ids.size)]) }}</p>
    <label class="campo"><span class="req">{{ t('Pickup date') }}</span><CampoFecha v-model="modal.fecha" :max="hoy()" /></label>
    <p class="ayuda">{{ t('It is compared with each PO\'s XF date to measure supplier compliance.') }}</p>
    <template #pie>
      <button class="btn" @click="modal = null">{{ t('Back') }}</button>
      <button class="btn btn-primario" :disabled="ocupado || !modal.fecha" @click="recolectar(modal.fecha)">{{ t('Save') }}</button>
    </template>
  </Modal>
</template>
