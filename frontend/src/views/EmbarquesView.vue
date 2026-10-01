<script setup>
import { t, tx } from '../i18n/index.js'
import { computed, onMounted, reactive, ref } from 'vue'
import Seleccion from '../components/Seleccion.vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api'
import Avance from '../components/Avance.vue'
import EstadoBadge from '../components/EstadoBadge.vue'
import Icono from '../components/Icono.vue'
import Modal from '../components/Modal.vue'
import Paginacion from '../components/Paginacion.vue'
import SelectBusqueda from '../components/SelectBusqueda.vue'
import ThOrden from '../components/ThOrden.vue'
import { MODOS, useRutas } from '../composables/useRutas'
import { useTabla } from '../composables/useTabla'
import { avisar, errorApi } from '../stores/ui'
import { fmtFecha, fmtNum, plural } from '../utils'

const route = useRoute()
const router = useRouter()
const filtros = reactive({ estado: route.query.estado || '', q: '' })
const lista = ref([])
const todos = ref([])
const modal = ref(null)
const listas = ref(null)

const ESTADOS = [['', t('All')], ['PLANIFICADO', t('Planned')], ['EN_TRANSITO', t('In transit')], ['ARRIBADO', t('Arrived')], ['ENTREGADO', t('Delivered')], ['RECIBIDO', t('Received')]]
const cuenta = computed(() => {
  const r = { '': todos.value.length }
  for (const e of todos.value) r[e.estado] = (r[e.estado] || 0) + 1
  return r
})
const tabla = useTabla(lista, {
  valores: { etd: (e) => e.salida_real || e.etd, eta: (e) => e.arribo_real || e.eta, estado: (e) => ESTADOS.findIndex(([k]) => k === e.estado), ruta: (e) => e.puerto_origen },
})
const ICONO = { MARITIMO: 'barco', AEREO: 'avion', TERRESTRE: 'camion' }

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
    tipo_transporte: 'MARITIMO', documento_numero: '', transportista_id: '', centro: '',
    puerto_origen: '', puerto_destino: '', etd: '', eta: '', observaciones: '',
  }
}
const modo = computed(() => MODOS[modal.value?.tipo_transporte] || MODOS.MARITIMO)
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

onMounted(cargar)
</script>

<template>
  <div class="pagina-cabeza">
    <div>
      <h1>{{ t('Shipments') }}</h1>
      <p>{{ t('Each shipment exists from planning (booking); the B/L or AWB is added when issued. Inside each one you assign the cargo to its load units: containers, air waybills or trucks.') }}</p>
    </div>
    <button class="btn btn-primario" @click="nuevo"><Icono nombre="mas" />{{ t('New shipment') }}</button>
  </div>

  <p v-if="listas?.total" class="nota ok" style="align-items: center; margin-bottom: 16px">
    <Icono nombre="check" />
    <span>{{ t('Invoices ready to ship (finalized, with all their packing lists finalized): {0}.', [fmtNum(listas.total)]) }}</span>
    <router-link class="btn btn-chico separar" :to="{ path: '/facturas', query: { vista: 'lista_transporte' } }">{{ t('See which') }}</router-link>
  </p>

  <div class="filtros">
    <div class="segmentos" role="group" :aria-label="t('Status')">
      <button v-for="[v, txt] in ESTADOS" :key="v" class="segmento" :aria-pressed="filtros.estado === v" @click="filtros.estado = v; cargar()">
        {{ tx(txt) }}<span v-if="cuenta[v]" class="cuenta">{{ tx(cuenta[v]) }}</span>
      </button>
    </div>
    <label class="buscador separar">
      <Icono nombre="buscar" :tam="16" />
      <input v-model="filtros.q" type="search" :placeholder="t('Search shipment or B/L / AWB')" :aria-label="t('Search')" @input="buscar" />
    </label>
  </div>

  <div class="tabla-marco tabla-fija">
    <table class="tabla">
      <thead>
        <tr>
          <ThOrden campo="codigo" :orden="tabla.estado.orden" @ordenar="tabla.ordenar">{{ t('Shipment') }}</ThOrden>
          <ThOrden campo="ruta" :orden="tabla.estado.orden" @ordenar="tabla.ordenar">{{ t('Route') }}</ThOrden>
          <ThOrden campo="etd" :orden="tabla.estado.orden" @ordenar="tabla.ordenar">ETD</ThOrden>
          <ThOrden campo="eta" :orden="tabla.estado.orden" @ordenar="tabla.ordenar">ETA</ThOrden>
          <ThOrden campo="estado" :orden="tabla.estado.orden" @ordenar="tabla.ordenar">{{ t('Status') }}</ThOrden>
          <th>{{ t('Load units') }}</th>
          <ThOrden campo="packing_lists" :orden="tabla.estado.orden" num @ordenar="tabla.ordenar">PL</ThOrden>
          <th>{{ t('Suppliers') }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="e in tabla.filas.value" :key="e.id" class="clicable" @click="router.push(`/transporte/embarques/${e.id}`)">
          <td>
            <span class="fila-flex" style="flex-wrap: nowrap"><Icono :nombre="ICONO[e.tipo_transporte]" />
              <router-link :to="`/transporte/embarques/${e.id}`" class="cajas-rango" @click.stop>{{ tx(e.codigo) }}</router-link></span>
            <span class="sub">{{ tx(e.documento_numero ? `${MODOS[e.tipo_transporte]?.doc} ${e.documento_numero}` : t('{0} pending', [MODOS[e.tipo_transporte]?.doc])) }}{{ tx(e.transportista ? ` · ${e.transportista}` : '') }}<template v-if="e.modalidad"> · {{ tx(e.modalidad) }}</template></span>
          </td>
          <td>{{ tx(e.puerto_origen || '—') }} <Icono nombre="flecha" :tam="13" /> {{ tx(e.puerto_destino || '—') }}<span class="sub">{{ tx(e.centro ? t('plant {0}', [e.centro]) : t('Plant to be defined')) }}</span></td>
          <td>{{ fmtFecha(e.salida_real || e.etd) }}<span class="sub">{{ tx(e.salida_real ? 'actual' : 'estimated') }}</span></td>
          <td>{{ fmtFecha(e.arribo_real || e.eta) }}<span class="sub">{{ tx(e.arribo_real ? 'actual' : 'estimated') }}</span></td>
          <td><EstadoBadge :estado="e.estado" /></td>
          <td>
            <div v-if="e.ocupacion.length" class="mini-ocupacion">
              <div v-for="o in e.ocupacion" :key="o.id"><span>{{ tx(o.nombre) }}</span><Avance v-if="o.pct_cbm !== null" :porcentaje="o.pct_cbm" /><span v-else>{{ fmtNum(o.cbm, 1) }} m³</span></div>
            </div>
            <span v-else class="apagado">{{ t('No units') }}</span>
          </td>
          <td class="num">{{ tx(e.packing_lists) }}<span v-if="e.tentativas" class="etiqueta aviso">{{ t('{0} tentative', [e.tentativas]) }}</span></td>
          <td class="envolver" style="min-width: 140px">{{ tx(e.proveedores.join(', ') || '—') }}</td>
        </tr>
        <tr v-if="!lista.length"><td colspan="8" class="vacio">{{ t('No shipments match these filters.') }}</td></tr>
      </tbody>
    </table>
  </div>
  <Paginacion :page="tabla.estado.pagina" :size="tabla.estado.porPagina" :total="tabla.total.value"
              @cambiar="(p) => (tabla.estado.pagina = p)" @tamano="(t) => (tabla.estado.porPagina = t)" />

  <Modal v-if="modal" :titulo="t('New shipment')" ancho="660px" @cerrar="modal = null">
    <div class="rejilla-campos">
      <label class="campo"><span class="req">{{ t('Mode of transport') }}</span>
        <Seleccion v-model="modal.tipo_transporte" @change="ajustarRuta">
          <option value="MARITIMO">{{ t('Ocean') }}</option><option value="AEREO">{{ t('Air') }}</option><option value="TERRESTRE">{{ t('Road') }}</option>
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
      <label class="campo"><span>ETD</span><input v-model="modal.etd" type="date" /></label>
      <label class="campo"><span>ETA</span><input v-model="modal.eta" type="date" /></label>
    </div>
    <p class="leyenda-req">{{ t('Required on the transport document; you can create the shipment without them, but departure cannot be recorded until they are complete.') }}</p>
    <template #pie>
      <button class="btn" @click="modal = null">{{ t('Cancel') }}</button>
      <button class="btn btn-primario" @click="crear">{{ t('Create shipment') }}</button>
    </template>
  </Modal>
</template>
