<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
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

const ESTADOS = [['', 'Todos'], ['PLANIFICADO', 'Planificados'], ['EN_TRANSITO', 'En tránsito'], ['ARRIBADO', 'Arribados'], ['ENTREGADO', 'Entregados'], ['RECIBIDO', 'Recibidos']]
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
    avisar(`Embarque ${r.codigo} creado. Agrega sus unidades de carga.`)
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
      <h1>Embarques</h1>
      <p>Cada embarque existe desde la planificación (booking); el BL o AWB se agrega cuando se emite. Dentro de cada uno asignas la carga a sus unidades: contenedores, guías aéreas o camiones.</p>
    </div>
    <button class="btn btn-primario" @click="nuevo"><Icono nombre="mas" />Nuevo embarque</button>
  </div>

  <p v-if="listas?.total" class="nota ok" style="align-items: center; margin-bottom: 16px">
    <Icono nombre="check" />
    <span>{{ plural(listas.total, 'factura está lista', 'facturas están listas') }} para embarcar (finalizada, con todos sus packing lists finalizados).</span>
    <router-link class="btn btn-chico separar" :to="{ path: '/facturas', query: { vista: 'lista_transporte' } }">Ver cuáles</router-link>
  </p>

  <div class="filtros">
    <div class="segmentos" role="group" aria-label="Estado">
      <button v-for="[v, t] in ESTADOS" :key="v" class="segmento" :aria-pressed="filtros.estado === v" @click="filtros.estado = v; cargar()">
        {{ t }}<span v-if="cuenta[v]" class="cuenta">{{ cuenta[v] }}</span>
      </button>
    </div>
    <label class="buscador separar">
      <Icono nombre="buscar" :tam="16" />
      <input v-model="filtros.q" type="search" placeholder="Buscar embarque o BL/AWB" aria-label="Buscar" @input="buscar" />
    </label>
  </div>

  <div class="tabla-marco tabla-fija">
    <table class="tabla">
      <thead>
        <tr>
          <ThOrden campo="codigo" :orden="tabla.estado.orden" @ordenar="tabla.ordenar">Embarque</ThOrden>
          <ThOrden campo="ruta" :orden="tabla.estado.orden" @ordenar="tabla.ordenar">Ruta</ThOrden>
          <ThOrden campo="etd" :orden="tabla.estado.orden" @ordenar="tabla.ordenar">ETD</ThOrden>
          <ThOrden campo="eta" :orden="tabla.estado.orden" @ordenar="tabla.ordenar">ETA</ThOrden>
          <ThOrden campo="estado" :orden="tabla.estado.orden" @ordenar="tabla.ordenar">Estado</ThOrden>
          <th>Unidades de carga</th>
          <ThOrden campo="packing_lists" :orden="tabla.estado.orden" num @ordenar="tabla.ordenar">PL</ThOrden>
          <th>Proveedores</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="e in tabla.filas.value" :key="e.id" class="clicable" @click="router.push(`/transporte/embarques/${e.id}`)">
          <td>
            <span class="fila-flex" style="flex-wrap: nowrap"><Icono :nombre="ICONO[e.tipo_transporte]" />
              <router-link :to="`/transporte/embarques/${e.id}`" class="cajas-rango" @click.stop>{{ e.codigo }}</router-link></span>
            <span class="sub">{{ e.documento_numero ? `${MODOS[e.tipo_transporte]?.doc} ${e.documento_numero}` : `${MODOS[e.tipo_transporte]?.doc} pendiente` }}{{ e.transportista ? ` · ${e.transportista}` : '' }}<template v-if="e.modalidad"> · {{ e.modalidad }}</template></span>
          </td>
          <td>{{ e.puerto_origen || '—' }} <Icono nombre="flecha" :tam="13" /> {{ e.puerto_destino || '—' }}<span class="sub">{{ e.centro ? `centro ${e.centro}` : 'Centro por definir' }}</span></td>
          <td>{{ fmtFecha(e.salida_real || e.etd) }}<span class="sub">{{ e.salida_real ? 'real' : 'estimada' }}</span></td>
          <td>{{ fmtFecha(e.arribo_real || e.eta) }}<span class="sub">{{ e.arribo_real ? 'real' : 'estimada' }}</span></td>
          <td><EstadoBadge :estado="e.estado" /></td>
          <td>
            <div v-if="e.ocupacion.length" class="mini-ocupacion">
              <div v-for="o in e.ocupacion" :key="o.id"><span>{{ o.nombre }}</span><Avance v-if="o.pct_cbm !== null" :porcentaje="o.pct_cbm" /><span v-else>{{ fmtNum(o.cbm, 1) }} m³</span></div>
            </div>
            <span v-else class="apagado">Sin unidades</span>
          </td>
          <td class="num">{{ e.packing_lists }}<span v-if="e.tentativas" class="etiqueta aviso">{{ e.tentativas }} tentativos</span></td>
          <td class="envolver" style="min-width: 140px">{{ e.proveedores.join(', ') || '—' }}</td>
        </tr>
        <tr v-if="!lista.length"><td colspan="8" class="vacio">No hay embarques con estos filtros.</td></tr>
      </tbody>
    </table>
  </div>
  <Paginacion :page="tabla.estado.pagina" :size="tabla.estado.porPagina" :total="tabla.total.value"
              @cambiar="(p) => (tabla.estado.pagina = p)" @tamano="(t) => (tabla.estado.porPagina = t)" />

  <Modal v-if="modal" titulo="Nuevo embarque" ancho="660px" @cerrar="modal = null">
    <div class="rejilla-campos">
      <label class="campo"><span class="req">Tipo de transporte</span>
        <select v-model="modal.tipo_transporte" @change="ajustarRuta">
          <option value="MARITIMO">Marítimo</option><option value="AEREO">Aéreo</option><option value="TERRESTRE">Terrestre</option>
        </select>
        <small class="ayuda">Define los puertos, transportistas y unidades de carga que se ofrecen. La modalidad (FCL, LCL…) es de cada unidad; un embarque puede combinarlas.</small>
      </label>
      <label class="campo"><span class="req">Centro que recibe (notify)</span>
        <SelectBusqueda v-model="modal.centro" :opciones="centros" vacio="Lo define la primera carga" etiqueta="Centro" @change="ajustarRuta" />
      </label>
      <label class="campo"><span class="req">{{ modo.doc }}</span><input v-model="modal.documento_numero" placeholder="Si ya existe" /></label>
      <label class="campo"><span class="req">{{ modo.transportista }}</span>
        <SelectBusqueda v-model="modal.transportista_id" :opciones="opcionesTransportista" vacio="Sin definir" :etiqueta="modo.transportista" />
        <small class="ayuda">{{ modal.centro ? 'Del modo elegido y que trabajan con la sociedad del centro.' : 'Del modo elegido.' }}</small>
      </label>
      <label class="campo"><span class="req">{{ modo.puerto }} de origen</span>
        <SelectBusqueda v-model="modal.puerto_origen" :opciones="puertosDe(modal.tipo_transporte)" vacio="Sin definir" :etiqueta="`${modo.puerto} de origen`" />
      </label>
      <label class="campo"><span class="req">{{ modo.puerto }} de destino</span>
        <SelectBusqueda v-model="modal.puerto_destino" :opciones="destinos" vacio="Sin definir" :etiqueta="`${modo.puerto} de destino`" />
        <small v-if="modal.centro && destinos[0]?.sub" class="ayuda">Sugerido: el principal del centro {{ modal.centro }}; puedes cambiarlo por otro de sus puertos.</small>
      </label>
      <label class="campo"><span>ETD</span><input v-model="modal.etd" type="date" /></label>
      <label class="campo"><span>ETA</span><input v-model="modal.eta" type="date" /></label>
    </div>
    <p class="leyenda-req">Obligatorios en el documento de transporte; puedes crear el embarque sin ellos, pero la salida no se registra hasta completarlos.</p>
    <template #pie>
      <button class="btn" @click="modal = null">Cancelar</button>
      <button class="btn btn-primario" @click="crear">Crear embarque</button>
    </template>
  </Modal>
</template>
