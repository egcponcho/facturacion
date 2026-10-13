<script setup>
import { ESTADOS_EMBARQUE } from '@/nucleo/estados.js'
import { t, tx } from '@/i18n/index.js'
import { computed, onMounted, reactive, ref } from 'vue'
import Seleccion from '@/componentes/Seleccion.vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '@/nucleo/api'
import Avance from '@/componentes/Avance.vue'
import EstadoBadge from '@/componentes/EstadoBadge.vue'
import EstadoTiempo from '@/componentes/EstadoTiempo.vue'
import EstadoVacio from '@/componentes/EstadoVacio.vue'
import ResumenEmbarque from '@/modulos/transporte/componentes/ResumenEmbarque.vue'
import Icono from '@/componentes/Icono.vue'
import Modal from '@/componentes/Modal.vue'
import SelectBusqueda from '@/componentes/SelectBusqueda.vue'
import TablaDatos from '@/componentes/TablaDatos.vue'
import { datosModo, modoInicial, modosTransporte, useRutas } from '@/composables/useRutas'
import { avisar, errorApi } from '@/stores/ui'
import { fmtFecha, fmtNum } from '@/nucleo/utils'

const route = useRoute()
const router = useRouter()
const filtros = reactive({ estado: route.query.estado || '', q: '' })
const lista = ref([])
// Clic en la fila: resumen en el panel lateral; el código abre la página
const resumenId = ref(null)
const todos = ref([])
const modal = ref(null)
const listas = ref(null)

const ESTADOS = [['', t('All')], ...ESTADOS_EMBARQUE]
const cuenta = computed(() => {
  const r = { '': todos.value.length }
  for (const e of todos.value) r[e.estado] = (r[e.estado] || 0) + 1
  return r
})
// Tabla común: ordena y filtra aquí (la lista ya viene filtrada por estado y búsqueda)
const columnas = [
  { clave: 'codigo', texto: t('Shipment'), fija: true, prioridad: 1, filtro: 'texto', valor: (e) => `${e.codigo} ${e.documento_numero || ''} ${e.transportista || ''}` },
  { clave: 'ruta', texto: t('Route'), prioridad: 2, filtro: 'texto', valor: (e) => `${e.puerto_origen || ''} ${e.puerto_destino || ''} ${e.centro || ''}` },
  { clave: 'etd', texto: 'ETD', prioridad: 2, valor: (e) => e.salida_real || e.etd },
  { clave: 'eta', texto: 'ETA', prioridad: 1, valor: (e) => e.arribo_real || e.eta },
  { clave: 'estado', texto: t('Status'), prioridad: 1, valor: (e) => ESTADOS.findIndex(([k]) => k === e.estado) },
  { clave: 'holgura_dias', texto: t('Vs. in-store date'), prioridad: 2 },
  { clave: 'unidades', texto: t('Load units'), ordenable: false, prioridad: 3 },
  { clave: 'packing_lists', texto: 'PL', num: true, prioridad: 3 },
  { clave: 'proveedores', texto: t('Suppliers'), prioridad: 3, filtro: 'texto', valor: (e) => e.proveedores.join(', ') },
]

async function cargar() {
  try {
    ;[lista.value, todos.value, listas.value] = await Promise.all([
      api.get('/embarques', filtros),
      api.get('/embarques'),
      api.get('/facturas', { vista: 'lista_transporte', size: 1 }),
    ])
  } catch (e) {
    errorApi(e)
  }
}

// Ruta coherente con el modo: puertos, destinos del centro y transportistas
const { cargarRutas, centros, puertosDe, destinosDe, transportistasDe } = useRutas()
function nuevo() {
  cargarRutas()
  modal.value = {
    tipo_transporte: modoInicial(), documento_numero: '', transportista_id: '', centro: '',
    puerto_origen: '', puerto_destino: '', etd: '', eta: '', observaciones: '',
  }
}
const modo = computed(() => datosModo(modal.value?.tipo_transporte))
const destinos = computed(() => (modal.value ? destinosDe(modal.value.tipo_transporte, modal.value.centro) : []))
const opcionesTransportista = computed(() => (modal.value ? transportistasDe(modal.value.tipo_transporte, modal.value.centro) : []))
// Al cambiar el modo o el centro se limpia lo que ya no aplica y se sugiere el destino principal del centro
function ajustarRuta() {
  const m = modal.value
  if (!puertosDe(m.tipo_transporte).some((p) => p.valor === m.puerto_origen)) m.puerto_origen = ''
  if (!destinos.value.some((p) => p.valor === m.puerto_destino)) m.puerto_destino = ''
  if (m.centro && !m.puerto_destino && destinos.value.length && destinos.value[0].sub) m.puerto_destino = destinos.value[0].valor
  if (!opcionesTransportista.value.some((t) => String(t.valor) === String(m.transportista_id))) m.transportista_id = ''
}

async function crear() {
  const datos = Object.fromEntries(Object.entries(modal.value).map(([k, v]) => [k, v === '' ? null : v]))
  try {
    const r = await api.post('/embarques', datos)
    avisar(t('Shipment {0} created. Add its load units.', [r.codigo]))
    router.push(`/transporte/embarques/${r.id}`)
  } catch (e) {
    errorApi(e)
  }
}

let espera
function buscar() {
  clearTimeout(espera)
  espera = setTimeout(cargar, 300)
}

onMounted(() => {
  cargar()
  if (route.query.nuevo) nuevo() // desde la paleta de comandos: «New shipment»
})
</script>

<template>
  <div class="pagina-cabeza">
    <div>
      <h1>{{ t('Shipments') }}</h1>
      <p>{{ t('Each shipment exists from planning (booking); the B/L or AWB is added when issued. Inside each one you assign the cargo to its load units: containers, air waybills or trucks.') }}</p>
    </div>
    <div class="acciones">
      <router-link to="/tableros/logistica" class="btn btn-fantasma"><Icono nombre="grafica" />{{ t('Indicators') }}</router-link>
      <button class="btn btn-primario" @click="nuevo"><Icono nombre="mas" />{{ t('New shipment') }}</button>
    </div>
  </div>

  <p v-if="listas?.total" class="nota ok" style="align-items: center; margin-bottom: 16px">
    <Icono nombre="check" />
    <span>{{ t('Invoices ready to ship (finalized, with all their packing lists finalized): {0}.', [fmtNum(listas.total)]) }}</span>
    <router-link class="btn btn-chico separar" :to="{ path: '/facturas', query: { vista: 'lista_transporte' } }">{{ t('See which') }}</router-link>
  </p>

  <TablaDatos tabla="embarques" :columnas="columnas" :filas="lista" fila-clicable :fila-activa="resumenId" :etiqueta="t('Shipments')"
              vistas-guardadas :externos="{ estado: filtros.estado, q: filtros.q }"
              @fila="(e) => (resumenId = e.id)" @vista="(q) => { filtros.estado = q.estado || ''; filtros.q = q.q || ''; cargar() }">
    <template #barra>
      <label class="buscador">
        <Icono nombre="buscar" :tam="16" />
        <input v-model="filtros.q" type="search" :placeholder="t('Search shipment or B/L / AWB')" :aria-label="t('Search')" @input="buscar" />
      </label>
    </template>
    <template #filtros>
      <div class="segmentos" role="group" :aria-label="t('Status')">
        <button v-for="[v, txt] in ESTADOS" :key="v" class="segmento" type="button" :aria-pressed="filtros.estado === v" @click="filtros.estado = v; cargar()">
          {{ tx(txt) }}<span v-if="cuenta[v]" class="cuenta">{{ tx(cuenta[v]) }}</span>
        </button>
      </div>
    </template>
    <template #celda-codigo="{ fila: e }">
      <span class="fila-flex" style="flex-wrap: nowrap"><Icono :nombre="datosModo(e.tipo_transporte).icono" />
        <router-link :to="`/transporte/embarques/${e.id}`" class="enlace-doc" @click.stop><strong class="codigo">{{ tx(e.codigo) }}</strong></router-link></span>
      <span class="sub">{{ tx(e.documento_numero ? `${datosModo(e.tipo_transporte).doc} ${e.documento_numero}` : t('{0} pending', [datosModo(e.tipo_transporte).doc])) }}{{ tx(e.transportista ? ` · ${e.transportista}` : '') }}<template v-if="e.modalidad"> · {{ tx(e.modalidad) }}</template></span>
    </template>
    <template #celda-ruta="{ fila: e }">{{ tx(e.puerto_origen || '—') }} <Icono nombre="flecha" :tam="13" /> {{ tx(e.puerto_destino || '—') }}<span class="sub">{{ tx(e.centro ? t('plant {0}', [e.centro]) : t('Plant to be defined')) }}</span></template>
    <template #celda-etd="{ fila: e }">{{ fmtFecha(e.salida_real || e.etd) }}<span class="sub">{{ e.salida_real ? t('actual') : t('estimated') }}</span></template>
    <template #celda-eta="{ fila: e }">{{ fmtFecha(e.arribo_real || e.eta) }}<span class="sub">{{ e.arribo_real ? t('actual') : t('estimated') }}</span></template>
    <template #celda-estado="{ fila: e }"><EstadoBadge :estado="e.estado" tipo="embarque" /></template>
    <template #celda-holgura_dias="{ fila: e }"><EstadoTiempo :estado="e.estado_tiempo" :holgura="e.holgura_dias" /></template>
    <template #celda-unidades="{ fila: e }">
      <div v-if="e.ocupacion.length" class="mini-ocupacion">
        <div v-for="o in e.ocupacion" :key="o.id"><span>{{ tx(o.nombre) }}</span><Avance v-if="o.pct_cbm !== null" :porcentaje="o.pct_cbm" /><span v-else>{{ fmtNum(o.cbm, 1) }} m³</span></div>
      </div>
      <span v-else class="apagado">{{ t('No units') }}</span>
    </template>
    <template #celda-proveedores="{ fila: e }"><span class="envolver">{{ tx(e.proveedores.join(', ') || '—') }}</span></template>
    <template #vacio>
      <span v-if="todos.length">{{ t('No shipments match these filters.') }}</span>
      <EstadoVacio v-else icono="barco" :titulo="t('There are no shipments yet.')"
                   :texto="t('A shipment groups the load units (containers, air waybills or trucks) that carry goods ready to ship.')"
                   :titulo-requisitos="t('To fill one you need:')"
                   :requisitos="[t('A finalized invoice'), t('A finalized packing list')]">
        <button class="btn btn-primario" @click="nuevo"><Icono nombre="mas" />{{ t('New shipment') }}</button>
      </EstadoVacio>
    </template>
  </TablaDatos>

  <Modal v-if="modal" :titulo="t('New shipment')" ancho="660px" @cerrar="modal = null">
    <div class="rejilla-campos">
      <label class="campo"><span class="req">{{ t('Mode of transport') }}</span>
        <Seleccion v-model="modal.tipo_transporte" @change="ajustarRuta">
          <option v-for="m in modosTransporte()" :key="m.codigo" :value="m.codigo">{{ m.nombre }}</option>
        </Seleccion>
        <small class="ayuda">{{ t('It sets the ports, carriers and load units offered. The modality (FCL, LCL…) belongs to each unit; a shipment can combine them.') }}</small>
      </label>
      <label class="campo"><span class="req">{{ t('Receiving plant (notify)') }}</span>
        <SelectBusqueda v-model="modal.centro" :opciones="centros" :vacio="t('Set by the first cargo')" :etiqueta="t('Plant')" @change="ajustarRuta" />
      </label>
      <label class="campo"><span class="req">{{ tx(modo.doc) }}</span><input v-model="modal.documento_numero" :placeholder="t('If already issued')" /></label>
      <label class="campo"><span class="req">{{ tx(modo.transportista) }}</span>
        <SelectBusqueda v-model="modal.transportista_id" :opciones="opcionesTransportista" :vacio="t('Not defined')" :etiqueta="tx(modo.transportista)" />
        <small class="ayuda">{{ tx(modal.centro ? t('Of the chosen mode and working with the plant\'s company.') : t('Of the chosen mode.')) }}</small>
      </label>
      <label class="campo"><span class="req">{{ t('{0} of loading', [modo.puerto]) }}</span>
        <SelectBusqueda v-model="modal.puerto_origen" :opciones="puertosDe(modal.tipo_transporte)" :vacio="t('Not defined')" :etiqueta="t('{0} of loading', [modo.puerto])" />
      </label>
      <label class="campo"><span class="req">{{ t('{0} of discharge', [modo.puerto]) }}</span>
        <SelectBusqueda v-model="modal.puerto_destino" :opciones="destinos" :vacio="t('Not defined')" :etiqueta="t('{0} of discharge', [modo.puerto])" />
        <small v-if="modal.centro && destinos[0]?.sub" class="ayuda">{{ t('Suggested: the main port of plant {0}; you can change it to another of its ports.', [modal.centro]) }}</small>
      </label>
      <label class="campo"><span>ETD</span><CampoFecha v-model="modal.etd" /></label>
      <label class="campo"><span>ETA</span><CampoFecha v-model="modal.eta" /></label>
    </div>
    <p class="leyenda-req">{{ t('Required on the transport document; you can create the shipment without them, but departure cannot be recorded until they are complete.') }}</p>
    <template #pie>
      <button class="btn" @click="modal = null">{{ t('Cancel') }}</button>
      <button class="btn btn-primario" @click="crear">{{ t('Create shipment') }}</button>
    </template>
  </Modal>
  <ResumenEmbarque v-if="resumenId" :id="resumenId" @cerrar="resumenId = null" />
</template>
