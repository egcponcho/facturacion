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
import ThOrden from '../components/ThOrden.vue'
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
  ['RECOLECCION', 'Recolección'],
  ['SALIDA', 'Salida'],
  ['TRANSITO', 'En tránsito'],
  ['ARRIBO', 'Arribo'],
  ['LIBERACION', 'Liberación'],
  ['ENTREGA', 'Entrega'],
  ['RECEPCION', 'Recepción en bodega'],
  ['OTRO', 'Otro'],
]
const nombreEvento = (t) => EVENTOS.find((x) => x[0] === t)?.[1] || t
const HITOS = [['PLANIFICADO', 'Planificado'], ['EN_TRANSITO', 'En tránsito'], ['ARRIBADO', 'Arribado'], ['ENTREGADO', 'Entregado'], ['RECIBIDO', 'Recibido']]
const SIGUIENTE = { PLANIFICADO: 'SALIDA', EN_TRANSITO: 'ARRIBO', ARRIBADO: 'ENTREGA', ENTREGADO: 'RECEPCION' }
// El cuarto valor marca lo que exige el documento de transporte (BL, AWB o
// carta de porte): sin eso no se registra la salida.
const CAMPOS = [
  ['documento_numero', 'BL / AWB', 'text', true],
  ['transportista', 'Naviera o transportista', 'text', true],
  ['puerto_origen', 'Origen', 'text', true],
  ['puerto_destino', 'Destino', 'text', true],
  ['etd', 'ETD (salida estimada)', 'date', false],
  ['eta', 'ETA (llegada estimada)', 'date', false],
]
// Al registrar la salida la carga queda cerrada: no se agregan, quitan ni
// mueven PL o contenedores, y los datos del viaje quedan fijos.
const cerrado = computed(() => !!e.value?.cerrado)
const FIJOS_SALIDA = ['documento_numero', 'transportista', 'puerto_origen', 'etd']
const fijo = (campo) => cerrado.value && (FIJOS_SALIDA.includes(campo) || (e.value.arribo_real && ['eta', 'puerto_destino'].includes(campo)))
const eventosPermitidos = computed(() => EVENTOS.filter(([k]) => (e.value?.eventos_permitidos || []).includes(k)))
const ultimoEvento = computed(() => (e.value?.eventos || []).reduce((a, ev) => (!a || ev.fecha > a ? ev.fecha : a), null))
const tonoHolgura = (d) => (d === null || d === undefined ? '' : d < 0 ? 'error' : d < 7 ? 'aviso' : 'ok')
const holguraTxt = (d) => (d < 0 ? `${-d} d tarde para tienda` : `${d} d de margen`)
const exigeSello = computed(() => e.value?.tipo_transporte === 'MARITIMO' && e.value?.modalidad === 'FCL')
const indiceEstado = computed(() => HITOS.findIndex(([k]) => k === e.value?.estado))
const icono = computed(() => ({ AEREO: 'avion', TERRESTRE: 'camion' })[e.value?.tipo_transporte] || 'barco')
const totales = computed(() => (e.value?.unidades || []).reduce((a, x) => ({
  pls: a.pls + x.packing_lists, cajas: a.cajas + x.cajas, cbm: a.cbm + x.cbm, kg: a.kg + x.peso_bruto, tentativas: a.tentativas + x.tentativas,
}), { pls: 0, cajas: 0, cbm: 0, kg: 0, tentativas: 0 }))

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

// ---- Contenedores ----------------------------------------------------------
function abrirNuevaUnidad() {
  modal.value = { tipo: 'unidad', unidad: e.value.tipos_unidad.includes('40HC') ? '40HC' : e.value.tipos_unidad[0], numero: '', sello: '' }
}
async function agregarUnidad() {
  const m = modal.value
  const r = await ejecutar(() => api.post(`/embarques/${props.id}/unidades`, { tipo: m.unidad, numero: m.numero || null, sello: m.sello || null }),
    (x) => `Contenedor ${x.etiqueta} agregado.`)
  if (r) unidadId.value = r.id
}
function eliminarUnidad() {
  ejecutar(() => api.del(`/unidades/${unidadId.value}`), `${u.value.nombre} eliminado.`)
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
  if (r.confirmados) partes.push(`${r.confirmados} confirmados`)
  if (r.tentativos) partes.push(`${r.tentativos} tentativos`)
  return `${plural(r.asignados, 'packing list asignado', 'packing lists asignados')} (${partes.join(', ')}).`
}
// Recolección en la bodega del proveedor: se marca antes de zarpar
const hoy = () => new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 10)
function abrirRecoleccion() {
  modal.value = { tipo: 'recoleccion', fecha: hoy() }
}
function recolectar(fecha) {
  ejecutar(() => api.post('/recoleccion', { pl_ids: selA.lista(), fecha }),
    (r) => (fecha ? `${plural(r.actualizados, 'packing list recolectado', 'packing lists recolectados')}.` : 'Recolección quitada.'))
}
function confirmar() {
  ejecutar(() => api.post(`/unidades/${unidadId.value}/confirmar`, { pl_ids: selAsignados.value.filter((p) => p.asignacion === 'TENTATIVA').map((p) => p.id) }),
    (r) => `${plural(r.confirmados, 'packing list confirmado', 'packing lists confirmados')}.`)
}
function quitar() {
  ejecutar(() => api.post(`/unidades/${unidadId.value}/desasignar`, { pl_ids: selA.lista(), motivo: modal.value.motivo || null }),
    'Packing lists quitados del contenedor.')
}
function mover() {
  const { destino, modo, motivo } = modal.value
  ejecutar(() => api.post(`/unidades/${destino}/asignar`, { pl_ids: selA.lista(), modo, motivo: motivo || null }),
    'Packing lists movidos al otro contenedor.')
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
  }), (r) => (r.estado === e.value.estado ? 'Evento registrado.' : `Evento registrado; el embarque pasó a ${HITOS.find(([k]) => k === r.estado)?.[1].toLowerCase()}.`))
}
const detalleHistorial = (h) => (h.detalle ? Object.entries(h.detalle).map(([k, v]) => `${k.replaceAll('_', ' ')}: ${Array.isArray(v) ? `${v[0] ?? '—'} a ${v[1] ?? '—'}` : v}`).join(', ') : '')

onMounted(cargar)
watch(() => sesion.proveedorId, () => cajon.value && cargarDisponibles())
</script>

<template>
  <template v-if="e">
    <router-link to="/transporte" class="volver"><Icono nombre="atras" :tam="15" />Embarques</router-link>
    <section class="doc-cabeza">
      <div class="doc-fila">
        <Icono :nombre="icono" :tam="26" />
        <span class="doc-numero">{{ e.codigo }}</span>
        <EstadoBadge :estado="e.estado" />
        <span class="doc-sub">{{ { MARITIMO: 'Marítimo', AEREO: 'Aéreo', TERRESTRE: 'Terrestre' }[e.tipo_transporte] }}{{ e.modalidad ? ` ${e.modalidad}` : '' }}</span>
        <div class="doc-acciones">
          <button class="btn" @click="abrirEvento('OTRO')"><Icono nombre="ubicacion" />Registrar evento</button>
          <button v-if="SIGUIENTE[e.estado]" class="btn btn-primario" :disabled="e.estado === 'PLANIFICADO' && (totales.tentativas > 0 || !totales.pls)"
                  :title="e.estado === 'PLANIFICADO' && totales.tentativas ? 'Confirma o quita los PL tentativos primero' : ''" @click="abrirEvento()">
            <Icono nombre="flecha" />Registrar {{ nombreEvento(SIGUIENTE[e.estado]).toLowerCase() }}
          </button>
        </div>
      </div>
      <ol class="hitos" aria-label="Estado del embarque">
        <li v-for="([k, t], i) in HITOS" :key="k" class="hito" :class="{ hecho: i < indiceEstado || (i === indiceEstado && i === HITOS.length - 1), actual: i === indiceEstado && i < HITOS.length - 1 }">
          <span class="hito-punto"><Icono v-if="i < indiceEstado" nombre="check" :tam="12" /></span>{{ t }}
        </li>
      </ol>
      <p v-if="cerrado" class="bloqueo mt"><Icono nombre="candado" />
        <span><b>Carga cerrada.</b> El embarque salió<template v-if="e.salida_real"> el {{ fmtFecha(e.salida_real) }}</template>: ya no se agregan, quitan ni mueven packing lists o contenedores, y los datos del viaje quedaron fijos. Solo se registran los siguientes eventos del seguimiento.</span>
      </p>
      <p v-if="e.estado === 'PLANIFICADO' && totales.tentativas" class="nota aviso mt"><Icono nombre="alerta" />Hay {{ plural(totales.tentativas, 'packing list tentativo', 'packing lists tentativos') }}. Confírmalos o quítalos antes de registrar la salida.</p>
      <div class="doc-datos">
        <label v-for="[campo, texto, tipo, obligatorio] in CAMPOS" :key="campo" class="dato">
          <span :class="{ req: obligatorio }">{{ texto }}</span>
          <b v-if="fijo(campo)" :title="'Fijo desde la salida'">{{ tipo === 'date' ? fmtFecha(e[campo]) : e[campo] || '—' }} <Icono nombre="candado" :tam="12" /></b>
          <CeldaEditable v-else :tipo="tipo" :valor="e[campo]" :guardar="guardar(campo)" :etiqueta="texto" :vacia-texto="obligatorio ? 'Obligatorio' : ''" />
        </label>
        <div class="dato"><span>Salida real</span><b>{{ fmtFecha(e.salida_real) }}</b></div>
        <div class="dato"><span>Arribo real</span><b>{{ fmtFecha(e.arribo_real) }}</b></div>
      </div>
      <div class="empaque-resumen">
        <div class="cifra"><span>Contenedores</span><b>{{ e.unidades.length }}</b></div>
        <div class="cifra"><span>Packing lists</span><b>{{ totales.pls }}</b></div>
        <div class="cifra"><span>Cajas</span><b>{{ fmtNum(totales.cajas) }}</b></div>
        <div class="cifra"><span>Volumen</span><b>{{ fmtNum(totales.cbm, 2) }} m³</b></div>
        <div class="cifra"><span>Peso bruto</span><b>{{ fmtNum(totales.kg, 0) }} kg</b></div>
      </div>
    </section>

    <section class="panel">
      <div class="panel-cabeza"><div><h2>Contenedores</h2><p>Elige uno para ver y asignar su carga.</p></div></div>
      <div class="unidades-pestanas" role="tablist">
        <button v-for="x in e.unidades" :key="x.id" class="unidad-pestana" role="tab" :aria-selected="x.id === unidadId" @click="unidadId = x.id">
          <span class="fila-flex"><Icono nombre="contenedor" /><span class="unidad-nombre">{{ x.nombre }}</span><span class="etiqueta">{{ x.tipo }}</span></span>
          <Avance v-if="x.capacidad_cbm" :porcentaje="x.pct_cbm || 0" />
          <span class="ayuda">{{ plural(x.packing_lists, 'PL', 'PL') }} · {{ fmtNum(x.cbm, 1) }} m³<template v-if="x.tentativas"> · <span class="etiqueta aviso">{{ x.tentativas }} tentativos</span></template></span>
          <span v-if="x.marcas?.length" class="ayuda">{{ x.marcas.join(' · ') }}</span>
          <span v-if="x.holgura_dias !== null && x.holgura_dias !== undefined" class="etiqueta" :class="tonoHolgura(x.holgura_dias)" style="margin-left: 0">{{ holguraTxt(x.holgura_dias) }}</span>
          <span v-for="a in x.alertas" :key="a" class="etiqueta error">{{ a }}</span>
        </button>
        <button v-if="!cerrado" class="unidad-pestana agregar" @click="abrirNuevaUnidad"><Icono nombre="mas" :tam="20" />Agregar contenedor</button>
      </div>

      <template v-if="u">
        <div class="dos-columnas mt" style="align-items: start">
          <div>
            <div class="rejilla-campos">
              <label class="dato"><span class="req">Número de contenedor o guía</span>
                <b v-if="cerrado">{{ u.numero || '—' }}</b>
                <CeldaEditable v-else :valor="u.numero" :guardar="guardarUnidad('numero')" etiqueta="Número" vacia-texto="Obligatorio" />
              </label>
              <label class="dato"><span :class="{ req: exigeSello }">Sello</span>
                <b v-if="cerrado">{{ u.sello || '—' }}</b>
                <CeldaEditable v-else :valor="u.sello" :guardar="guardarUnidad('sello')" etiqueta="Sello" :vacia-texto="exigeSello ? 'Obligatorio' : ''" />
              </label>
              <div class="dato"><span>Primera fecha en tienda</span><b>{{ fmtFecha(u.fecha_tienda) }}</b></div>
              <div class="dato"><span>Llegada vs. tienda</span>
                <b v-if="u.holgura_dias !== null && u.holgura_dias !== undefined"><span class="etiqueta" :class="tonoHolgura(u.holgura_dias)" style="margin-left: 0">{{ holguraTxt(u.holgura_dias) }}</span></b>
                <b v-else class="apagado">Falta ETA o fecha en tienda</b>
              </div>
            </div>
          </div>
          <div>
            <div v-if="u.capacidad_cbm" class="linea-avance">
              <span class="ayuda">Volumen: {{ fmtNum(u.cbm, 2) }} de {{ fmtNum(u.capacidad_cbm, 0) }} m³</span>
              <Avance :porcentaje="u.pct_cbm || 0" />
            </div>
            <div v-if="u.capacidad_kg" class="linea-avance mt-chico">
              <span class="ayuda">Peso: {{ fmtNum(u.peso_bruto, 0) }} de {{ fmtNum(u.capacidad_kg, 0) }} kg</span>
              <Avance :porcentaje="u.pct_kg || 0" />
            </div>
            <p v-if="!u.capacidad_cbm" class="ayuda">{{ fmtNum(u.cbm, 2) }} m³ · {{ fmtNum(u.peso_bruto, 0) }} kg (sin capacidad nominal)</p>
            <p v-for="a in u.alertas" :key="a" class="nota error mt-chico"><Icono nombre="alerta" />{{ a }}</p>
          </div>
        </div>

        <div class="fila-flex mt">
          <h3>Carga de {{ u.nombre }}</h3>
          <span class="ayuda">{{ plural(u.facturas, 'factura', 'facturas') }} · {{ plural(u.cajas, 'caja', 'cajas') }} · {{ u.recolectados }} de {{ u.packing_lists }} recolectados</span>
          <span class="separar"></span>
          <template v-if="!cerrado">
            <button v-if="!u.packing_lists" class="btn btn-fantasma btn-peligro" @click="eliminarUnidad"><Icono nombre="basura" :tam="15" />Eliminar contenedor</button>
            <button class="btn btn-primario" @click="abrirCajon"><Icono nombre="mas" />Asignar carga</button>
          </template>
        </div>
        <div class="tabla-marco mt-chico" style="box-shadow: none">
          <table class="tabla">
            <thead>
              <tr>
                <th v-if="!cerrado" class="chk"><input type="checkbox" aria-label="Seleccionar todos los asignados" :checked="selA.todos(u.asignados.map((p) => p.id))" @change="selA.alternarTodos(u.asignados.map((p) => p.id))" /></th>
                <ThOrden campo="factura" :orden="tablaA.estado.orden" @ordenar="tablaA.ordenar">Factura</ThOrden>
                <ThOrden campo="numero" :orden="tablaA.estado.orden" @ordenar="tablaA.ordenar">Packing list</ThOrden>
                <ThOrden campo="proveedor" :orden="tablaA.estado.orden" @ordenar="tablaA.ordenar">Proveedor · marcas</ThOrden>
                <ThOrden campo="asignacion" :orden="tablaA.estado.orden" @ordenar="tablaA.ordenar">Asignación</ThOrden>
                <ThOrden campo="fecha_xf" :orden="tablaA.estado.orden" @ordenar="tablaA.ordenar">XF</ThOrden>
                <ThOrden campo="recolectado_en" :orden="tablaA.estado.orden" @ordenar="tablaA.ordenar">Recolección</ThOrden>
                <ThOrden campo="fecha_tienda" :orden="tablaA.estado.orden" @ordenar="tablaA.ordenar">En tienda</ThOrden>
                <th>Contenido</th>
                <ThOrden campo="cajas" :orden="tablaA.estado.orden" num @ordenar="tablaA.ordenar">Cajas</ThOrden>
                <ThOrden campo="peso_bruto" :orden="tablaA.estado.orden" num @ordenar="tablaA.ordenar">Bruto kg</ThOrden>
                <ThOrden campo="cbm" :orden="tablaA.estado.orden" num @ordenar="tablaA.ordenar">m³</ThOrden>
              </tr>
            </thead>
            <tbody>
              <tr v-for="p in tablaA.filas.value" :key="p.id" :class="{ seleccionada: selA.tiene(p.id) }">
                <td v-if="!cerrado" class="chk"><input type="checkbox" :aria-label="`Seleccionar ${p.factura} ${p.numero}`" :checked="selA.tiene(p.id)" @change="selA.alternar(p.id)" /></td>
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
                    <span v-if="p.fecha_xf && p.recolectado_en > p.fecha_xf" class="sub" style="color: var(--error)">después del XF</span>
                  </template>
                  <span v-else class="etiqueta aviso" style="margin-left: 0">Pendiente</span>
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
                  <p>El contenedor está vacío.</p>
                  <button v-if="!cerrado" class="btn btn-primario" @click="abrirCajon"><Icono nombre="mas" />Asignar carga</button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <BarraSeleccion :cantidad="selA.ids.size" singular="PL seleccionado" plural="PL seleccionados" @limpiar="selA.limpiar()">
          <template #resumen>{{ fmtNum(totSelA.cajas) }} cajas · {{ fmtNum(totSelA.cbm, 2) }} m³</template>
          <button class="btn btn-primario" :disabled="ocupado || !selAsignados.some((p) => p.asignacion === 'TENTATIVA' && p.puede_confirmar)" @click="confirmar"><Icono nombre="check" :tam="15" />Confirmar</button>
          <button class="btn" :disabled="ocupado || selAsignados.some((p) => p.estado !== 'FINALIZADO')" title="Solo packing lists finalizados" @click="abrirRecoleccion"><Icono nombre="camion" :tam="15" />Marcar recolectado</button>
          <button v-if="selAsignados.some((p) => p.recolectado_en)" class="btn" :disabled="ocupado" @click="recolectar(null)">Quitar recolección</button>
          <button class="btn" :disabled="!u.otras_unidades.length" @click="modal = { tipo: 'mover', destino: u.otras_unidades[0]?.id, modo: 'AUTO', motivo: '' }"><Icono nombre="mover" :tam="15" />Mover a otro contenedor</button>
          <button class="btn btn-peligro" @click="modal = { tipo: 'quitar', motivo: '' }">Quitar</button>
        </BarraSeleccion>
      </template>
      <div v-else class="vacio">
        <Icono nombre="contenedor" :tam="28" />
        <p>Este embarque aún no tiene contenedores. Agrega un contenedor, una guía aérea o un camión.</p>
        <button class="btn btn-primario" @click="abrirNuevaUnidad"><Icono nombre="mas" />Agregar contenedor</button>
      </div>
    </section>

    <div class="dos-columnas mt">
      <section class="panel">
        <div class="panel-cabeza">
          <div><h2>Seguimiento</h2><p>Los eventos de salida, arribo, entrega y recepción cambian el estado del embarque.</p></div>
          <button class="btn btn-chico" @click="abrirEvento('OTRO')"><Icono nombre="mas" :tam="14" />Evento</button>
        </div>
        <ul class="linea-tiempo">
          <li v-for="ev in [...e.eventos].reverse()" :key="ev.id">
            <span class="ayuda">{{ fmtFechaHoraLocal(ev.fecha) }}</span>
            <span><b>{{ nombreEvento(ev.tipo) }}</b>{{ ev.ubicacion ? ` · ${ev.ubicacion}` : '' }}<span v-if="ev.observacion" class="sub">{{ ev.observacion }}</span></span>
          </li>
          <li v-if="!e.eventos.length"><span></span><span class="ayuda">Sin eventos todavía.</span></li>
        </ul>
      </section>
      <section class="panel">
        <div class="panel-cabeza">
          <div><h2>Historial de cambios</h2><p>Quién cambió fechas, contenedores o carga.</p></div>
          <button v-if="e.historial.length > 5" class="btn btn-chico btn-fantasma" @click="verHistorial = !verHistorial">{{ verHistorial ? 'Ver menos' : `Ver todo (${e.historial.length})` }}</button>
        </div>
        <ul class="linea-tiempo">
          <li v-for="(h, i) in verHistorial ? e.historial : e.historial.slice(0, 5)" :key="i">
            <span class="ayuda">{{ fmtFechaHora(h.fecha) }}<br />{{ h.usuario }}</span>
            <span>
              <b>{{ ACCIONES[h.accion] || h.accion }}</b>
              <span class="sub">{{ detalleHistorial(h) }}</span>
              <span v-if="h.motivo" class="sub">Motivo: {{ h.motivo }}</span>
            </span>
          </li>
          <li v-if="!e.historial.length"><span></span><span class="ayuda">Sin cambios.</span></li>
        </ul>
      </section>
    </div>
  </template>

  <!-- Asignar carga -->
  <div v-if="cajon" class="cajon-fondo" @click="cajon = false"></div>
  <aside v-if="cajon && u" class="cajon" style="width: min(760px, 100vw)" aria-label="Asignar carga">
    <div class="cajon-cabeza">
      <div>
        <h2>Asignar carga a {{ u.nombre }}</h2>
        <p>Packing lists sin contenedor, agrupados por factura. Marca una factura para llevar todos sus PL.</p>
      </div>
      <button class="btn-icono" type="button" aria-label="Cerrar" @click="cajon = false"><Icono nombre="cerrar" :tam="20" /></button>
    </div>
    <div class="cajon-cuerpo">
      <div class="filtros">
        <label class="buscador">
          <Icono nombre="buscar" :tam="16" />
          <input v-model="filtros.q" type="search" placeholder="Buscar número de factura" aria-label="Buscar factura" @input="buscar" />
        </label>
        <label class="check"><input v-model="filtros.solo_listos" type="checkbox" @change="cargarDisponibles" /> Solo listos para confirmar</label>
      </div>
      <div class="tabla-marco" style="box-shadow: none">
        <table class="tabla">
          <thead>
            <tr>
              <th class="chk"><input type="checkbox" aria-label="Seleccionar todo lo disponible" :checked="selD.todos(todosDisponibles.map((p) => p.id))" @change="selD.alternarTodos(todosDisponibles.map((p) => p.id))" /></th>
              <th><span class="oculto-visual">Ver PL</span></th>
              <th>Factura</th>
              <th>Packing lists</th>
              <th class="num">Cajas</th>
              <th class="num">m³</th>
            </tr>
          </thead>
          <tbody>
            <template v-for="g in disponibles" :key="g.factura_id">
              <tr :class="{ seleccionada: selD.todos(g.packing_lists.map((p) => p.id)) }">
                <td class="chk">
                  <input type="checkbox" :aria-label="`Seleccionar la factura ${g.factura} completa`" :checked="selD.todos(g.packing_lists.map((p) => p.id))" @change="selD.alternarTodos(g.packing_lists.map((p) => p.id))" />
                </td>
                <td><button class="btn-icono" :aria-expanded="abiertas.has(g.factura_id)" :aria-label="`Ver PL de ${g.factura}`" @click="alternarAbierta(g.factura_id)"><Icono :nombre="abiertas.has(g.factura_id) ? 'abajo' : 'derecha'" :tam="16" /></button></td>
                <td><b>{{ g.factura }}</b> <EstadoBadge :estado="g.factura_estado" /><span class="sub">{{ g.proveedor }}</span></td>
                <td>
                  {{ plural(g.packing_lists.length, 'PL', 'PL') }}
                  <span v-if="g.todos_confirmables" class="etiqueta ok">Listos</span>
                  <span v-else class="etiqueta aviso">Irán tentativos</span>
                </td>
                <td class="num">{{ fmtNum(g.cajas) }}</td>
                <td class="num">{{ fmtNum(g.cbm, 2) }}</td>
              </tr>
              <template v-if="abiertas.has(g.factura_id)">
                <tr v-for="p in g.packing_lists" :key="p.id" :class="{ seleccionada: selD.tiene(p.id) }">
                  <td></td>
                  <td class="chk"><input type="checkbox" :aria-label="`Seleccionar ${p.numero}`" :checked="selD.tiene(p.id)" @change="selD.alternar(p.id)" /></td>
                  <td><span class="cajas-rango">{{ p.numero }}</span> <EstadoBadge :estado="p.estado" /><span v-if="!p.puede_confirmar" class="sub">{{ p.motivo_no_confirmable }}</span></td>
                  <td>{{ porUnidadTxt(p.por_unidad, 'cantidad') }}</td>
                  <td class="num">{{ fmtNum(p.cajas) }}</td>
                  <td class="num">{{ fmtNum(p.cbm, 2) }}</td>
                </tr>
              </template>
            </template>
            <tr v-if="!disponibles.length"><td colspan="6" class="vacio">No hay packing lists sin contenedor con estos filtros.</td></tr>
          </tbody>
        </table>
      </div>
    </div>
    <div class="cajon-pie">
      <div v-if="proyeccion && selD.ids.size" class="linea-avance">
        <span class="ayuda">Con la selección: {{ fmtNum(proyeccion.cbm, 2) }} m³ ({{ Math.round(proyeccion.pct) }}% del volumen)</span>
        <Avance :porcentaje="proyeccion.pct" />
      </div>
      <p v-if="proyeccion && proyeccion.pct > 100" class="nota error"><Icono nombre="alerta" />La selección supera la capacidad nominal del contenedor.</p>
      <label class="check"><input v-model="confirmarListos" type="checkbox" /> Confirmar de una vez los que estén listos (factura y PL finalizados); los demás quedan tentativos</label>
      <div class="fila-flex">
        <span class="ayuda">{{ plural(selD.ids.size, 'PL seleccionado', 'PL seleccionados') }}<template v-if="selD.ids.size && confirmarListos"> · {{ listosSel }} se confirmarán</template></span>
        <button class="btn btn-primario separar" :disabled="ocupado || !selD.ids.size" @click="asignar"><Icono nombre="contenedor" :tam="16" />Asignar a {{ u.nombre }}</button>
      </div>
    </div>
  </aside>

  <Modal v-if="modal?.tipo === 'unidad'" titulo="Agregar contenedor" @cerrar="modal = null">
    <div class="rejilla-campos">
      <label class="campo"><span class="req">Tipo</span>
        <select v-model="modal.unidad"><option v-for="t in e.tipos_unidad" :key="t" :value="t">{{ t }}</option></select>
      </label>
      <label class="campo"><span>Número (opcional)</span><input v-model="modal.numero" placeholder="MSKU 123456-7" /></label>
      <label class="campo"><span>Sello (opcional)</span><input v-model="modal.sello" /></label>
    </div>
    <p class="ayuda">El número y el sello se pueden capturar después, cuando la naviera los asigne; son obligatorios para registrar la salida.</p>
    <template #pie>
      <button class="btn" @click="modal = null">Cancelar</button>
      <button class="btn btn-primario" :disabled="ocupado" @click="agregarUnidad">Agregar</button>
    </template>
  </Modal>

  <Modal v-if="modal?.tipo === 'evento'" titulo="Registrar evento" @cerrar="modal = null">
    <div class="rejilla-campos">
      <label class="campo"><span class="req">Evento</span>
        <select v-model="modal.evento"><option v-for="[v, t] in eventosPermitidos" :key="v" :value="v">{{ t }}</option></select>
      </label>
      <label class="campo"><span class="req">Fecha y hora</span><input v-model="modal.fecha" type="datetime-local" required :min="ultimoEvento?.slice(0, 16)" /></label>
      <label class="campo"><span>Ubicación</span><input v-model="modal.ubicacion" /></label>
      <label class="campo"><span>Observación</span><input v-model="modal.observacion" /></label>
    </div>
    <p class="ayuda">Los eventos van en orden: solo aparecen los que siguen al estado actual, y la fecha no puede ser futura ni anterior al último evento.</p>
    <p v-if="modal.evento === 'SALIDA'" class="nota aviso">Para registrar la salida todos los packing lists deben estar confirmados. Al registrarla, la carga del embarque queda cerrada y los PL sin recolección se marcan recolectados con esta fecha.</p>
    <template #pie>
      <button class="btn" @click="modal = null">Cancelar</button>
      <button class="btn btn-primario" :disabled="ocupado || !modal.fecha" @click="registrarEvento">Registrar</button>
    </template>
  </Modal>

  <Modal v-if="modal?.tipo === 'quitar'" titulo="Quitar del contenedor" @cerrar="modal = null">
    <p>Los {{ selA.ids.size }} packing lists quedan sin contenedor y vuelven a estar disponibles.</p>
    <label class="campo"><span :class="{ req: requiereMotivo }">Motivo{{ requiereMotivo ? '' : ' (opcional)' }}</span><textarea v-model="modal.motivo"></textarea></label>
    <template #pie>
      <button class="btn" @click="modal = null">Volver</button>
      <button class="btn btn-peligro" :disabled="ocupado || (requiereMotivo && !modal.motivo.trim())" @click="quitar">Quitar</button>
    </template>
  </Modal>

  <Modal v-if="modal?.tipo === 'mover'" titulo="Mover a otro contenedor" @cerrar="modal = null">
    <label class="campo"><span>Contenedor destino</span>
      <select v-model="modal.destino"><option v-for="o in u.otras_unidades" :key="o.id" :value="o.id">{{ o.nombre }}</option></select>
    </label>
    <label class="check"><input v-model="modal.modo" type="checkbox" true-value="AUTO" false-value="TENTATIVA" /> Confirmar en el destino los que estén listos</label>
    <label class="campo"><span :class="{ req: requiereMotivo }">Motivo{{ requiereMotivo ? '' : ' (opcional)' }}</span><textarea v-model="modal.motivo"></textarea></label>
    <template #pie>
      <button class="btn" @click="modal = null">Volver</button>
      <button class="btn btn-primario" :disabled="ocupado || !modal.destino || (requiereMotivo && !modal.motivo.trim())" @click="mover">Mover</button>
    </template>
  </Modal>

  <Modal v-if="modal?.tipo === 'recoleccion'" titulo="Marcar recolección" @cerrar="modal = null">
    <p>{{ plural(selA.ids.size, 'packing list se recogió', 'packing lists se recogieron') }} en la bodega del proveedor.</p>
    <label class="campo"><span class="req">Fecha de recolección</span><input v-model="modal.fecha" type="date" :max="hoy()" /></label>
    <p class="ayuda">Se compara con la fecha XF de cada OC para medir el cumplimiento del proveedor.</p>
    <template #pie>
      <button class="btn" @click="modal = null">Volver</button>
      <button class="btn btn-primario" :disabled="ocupado || !modal.fecha" @click="recolectar(modal.fecha)">Guardar</button>
    </template>
  </Modal>
</template>
