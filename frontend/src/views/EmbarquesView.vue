<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api'
import EstadoBadge from '../components/EstadoBadge.vue'
import Modal from '../components/Modal.vue'
import { avisar, errorApi } from '../stores/ui'
import { fmtFecha, fmtNum } from '../utils'

const route = useRoute()
const router = useRouter()
const filtros = reactive({ estado: route.query.estado || '', q: '' })
const lista = ref([])
const modal = ref(null)

async function cargar() {
  try {
    lista.value = await api.get('/embarques', filtros)
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
      <h1>Transporte</h1>
      <p>El embarque existe desde la planificación (booking); el BL o AWB se agrega cuando se emite. Las asignaciones pueden ser tentativas hasta confirmar.</p>
    </div>
    <button class="btn btn-primario" @click="nuevo">Nuevo embarque</button>
  </div>

  <div class="filtros">
    <input v-model="filtros.q" type="search" placeholder="Buscar embarque o BL/AWB" aria-label="Buscar" @input="buscar" />
    <select v-model="filtros.estado" aria-label="Estado" @change="cargar">
      <option value="">Cualquier estado</option>
      <option value="PLANIFICADO">Planificado</option>
      <option value="EN_TRANSITO">En tránsito</option>
      <option value="ARRIBADO">Arribado</option>
      <option value="ENTREGADO">Entregado</option>
      <option value="RECIBIDO">Recibido</option>
    </select>
  </div>

  <div class="tabla-marco">
    <table class="tabla">
      <thead>
        <tr>
          <th>Embarque</th>
          <th>Tipo</th>
          <th>BL / AWB</th>
          <th>Ruta</th>
          <th>ETD</th>
          <th>ETA</th>
          <th>Estado</th>
          <th class="num">Unidades</th>
          <th class="num">PL</th>
          <th class="num">CBM</th>
          <th>Proveedores</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="e in lista" :key="e.id" class="clicable" @click="router.push(`/transporte/embarques/${e.id}`)">
          <td><router-link :to="`/transporte/embarques/${e.id}`" class="cajas-rango" @click.stop>{{ e.codigo }}</router-link></td>
          <td>{{ e.tipo_transporte.toLowerCase() }}{{ e.modalidad ? ` ${e.modalidad}` : '' }}</td>
          <td>{{ e.documento_numero || 'Pendiente' }}</td>
          <td>{{ e.puerto_origen || '—' }} a {{ e.puerto_destino || '—' }}</td>
          <td>{{ fmtFecha(e.etd) }}</td>
          <td>{{ fmtFecha(e.eta) }}</td>
          <td><EstadoBadge :estado="e.estado" /></td>
          <td class="num">{{ e.unidades }}</td>
          <td class="num">{{ e.packing_lists }}<span v-if="e.tentativas" class="etiqueta aviso">{{ e.tentativas }} tentativos</span></td>
          <td class="num">{{ fmtNum(e.cbm, 2) }}</td>
          <td>{{ e.proveedores.join(', ') || '—' }}</td>
        </tr>
        <tr v-if="!lista.length"><td colspan="11" class="vacio">No hay embarques con estos filtros.</td></tr>
      </tbody>
    </table>
  </div>

  <Modal v-if="modal" titulo="Nuevo embarque" ancho="640px" @cerrar="modal = null">
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
    <template #pie>
      <button class="btn" @click="modal = null">Cancelar</button>
      <button class="btn btn-primario" @click="crear">Crear embarque</button>
    </template>
  </Modal>
</template>
