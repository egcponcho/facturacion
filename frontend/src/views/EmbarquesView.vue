<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api'
import Avance from '../components/Avance.vue'
import EstadoBadge from '../components/EstadoBadge.vue'
import Icono from '../components/Icono.vue'
import Modal from '../components/Modal.vue'
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

function nuevo() {
  modal.value = {
    tipo_transporte: 'MARITIMO', modalidad: 'FCL', documento_numero: '', transportista: '',
    puerto_origen: '', puerto_destino: '', etd: '', eta: '', observaciones: '',
  }
}

async function crear() {
  const datos = Object.fromEntries(Object.entries(modal.value).map(([k, v]) => [k, v === '' ? null : v]))
  if (datos.tipo_transporte !== 'MARITIMO') datos.modalidad = null
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
      <p>Cada embarque existe desde la planificación (booking); el BL o AWB se agrega cuando se emite. Dentro de cada uno asignas la carga a sus contenedores.</p>
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

  <div class="tabla-marco">
    <table class="tabla">
      <thead>
        <tr>
          <th>Embarque</th>
          <th>Ruta</th>
          <th>ETD</th>
          <th>ETA</th>
          <th>Estado</th>
          <th>Contenedores</th>
          <th class="num">PL</th>
          <th>Proveedores</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="e in lista" :key="e.id" class="clicable" @click="router.push(`/transporte/embarques/${e.id}`)">
          <td>
            <span class="fila-flex" style="flex-wrap: nowrap"><Icono :nombre="ICONO[e.tipo_transporte]" />
              <router-link :to="`/transporte/embarques/${e.id}`" class="cajas-rango" @click.stop>{{ e.codigo }}</router-link></span>
            <span class="sub">{{ e.documento_numero ? `BL/AWB ${e.documento_numero}` : 'BL/AWB pendiente' }}{{ e.transportista ? ` · ${e.transportista}` : '' }}</span>
          </td>
          <td>{{ e.puerto_origen || '—' }} <Icono nombre="flecha" :tam="13" /> {{ e.puerto_destino || '—' }}</td>
          <td>{{ fmtFecha(e.salida_real || e.etd) }}<span class="sub">{{ e.salida_real ? 'real' : 'estimada' }}</span></td>
          <td>{{ fmtFecha(e.arribo_real || e.eta) }}<span class="sub">{{ e.arribo_real ? 'real' : 'estimada' }}</span></td>
          <td><EstadoBadge :estado="e.estado" /></td>
          <td>
            <div v-if="e.ocupacion.length" class="mini-ocupacion">
              <div v-for="o in e.ocupacion" :key="o.id"><span>{{ o.nombre }}</span><Avance v-if="o.pct_cbm !== null" :porcentaje="o.pct_cbm" /><span v-else>{{ fmtNum(o.cbm, 1) }} m³</span></div>
            </div>
            <span v-else class="apagado">Sin contenedores</span>
          </td>
          <td class="num">{{ e.packing_lists }}<span v-if="e.tentativas" class="etiqueta aviso">{{ e.tentativas }} tentativos</span></td>
          <td class="envolver" style="min-width: 140px">{{ e.proveedores.join(', ') || '—' }}</td>
        </tr>
        <tr v-if="!lista.length"><td colspan="8" class="vacio">No hay embarques con estos filtros.</td></tr>
      </tbody>
    </table>
  </div>

  <Modal v-if="modal" titulo="Nuevo embarque" ancho="660px" @cerrar="modal = null">
    <div class="rejilla-campos">
      <label class="campo"><span>Tipo de transporte</span>
        <select v-model="modal.tipo_transporte">
          <option value="MARITIMO">Marítimo</option><option value="AEREO">Aéreo</option><option value="TERRESTRE">Terrestre</option>
        </select>
      </label>
      <label v-if="modal.tipo_transporte === 'MARITIMO'" class="campo"><span>Modalidad</span>
        <select v-model="modal.modalidad"><option value="FCL">Contenedor completo (FCL)</option><option value="LCL">Carga consolidada (LCL)</option></select>
      </label>
      <label class="campo"><span>BL / AWB (si ya existe)</span><input v-model="modal.documento_numero" /></label>
      <label class="campo"><span>Naviera o transportista</span><input v-model="modal.transportista" /></label>
      <label class="campo"><span>Origen</span><input v-model="modal.puerto_origen" /></label>
      <label class="campo"><span>Destino</span><input v-model="modal.puerto_destino" /></label>
      <label class="campo"><span>ETD</span><input v-model="modal.etd" type="date" /></label>
      <label class="campo"><span>ETA</span><input v-model="modal.eta" type="date" /></label>
    </div>
    <p class="ayuda">Después de crearlo agregas sus contenedores y les asignas carga.</p>
    <template #pie>
      <button class="btn" @click="modal = null">Cancelar</button>
      <button class="btn btn-primario" @click="crear">Crear embarque</button>
    </template>
  </Modal>
</template>
