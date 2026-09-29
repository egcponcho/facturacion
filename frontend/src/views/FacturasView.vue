<script setup>
import { onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api'
import Avance from '../components/Avance.vue'
import EstadoBadge from '../components/EstadoBadge.vue'
import Icono from '../components/Icono.vue'
import Paginacion from '../components/Paginacion.vue'
import ThOrden from '../components/ThOrden.vue'
import { siguienteOrden } from '../composables/useTabla'
import { esInterno, sesion } from '../stores/sesion'
import { errorApi } from '../stores/ui'
import { fmtFecha, fmtMoneda } from '../utils'

const route = useRoute()
const router = useRouter()
const filtros = reactive({
  estado: route.query.estado || '',
  vista: route.query.vista || '',
  q: route.query.q || '',
  orden: '',
  page: 1,
  size: 15,
})
const datos = ref({ items: [], total: 0 })
const cargando = ref(false)

const VISTAS = [
  ['', 'Todas'],
  ['editables', 'En proceso'],
  ['pl_incompletos', 'Empaque pendiente'],
  ['borradores_antiguos', 'Borradores antiguos'],
]
if (esInterno()) VISTAS.push(['lista_transporte', 'Listas para embarcar'], ['pl_sin_unidad', 'PL sin contenedor'])

async function cargar() {
  cargando.value = true
  try {
    datos.value = await api.get('/facturas', { ...filtros, proveedor_id: sesion.proveedorId })
    router.replace({ query: { ...(filtros.estado && { estado: filtros.estado }), ...(filtros.vista && { vista: filtros.vista }), ...(filtros.q && { q: filtros.q }) } })
  } catch (e) {
    errorApi(e)
  } finally {
    cargando.value = false
  }
}

let espera
function buscar() {
  clearTimeout(espera)
  espera = setTimeout(() => {
    filtros.page = 1
    cargar()
  }, 300)
}

function ordenar(campo) {
  filtros.orden = siguienteOrden(filtros.orden, campo)
  recargar()
}

function recargar() {
  filtros.page = 1
  cargar()
}

onMounted(cargar)
watch(() => sesion.proveedorId, recargar)
</script>

<template>
  <div class="pagina-cabeza">
    <div>
      <h1>Facturas y empaque</h1>
      <p>Cada factura es un espacio de trabajo: sus líneas, sus packing lists con cajas y el seguimiento del embarque.</p>
    </div>
    <router-link class="btn btn-primario" to="/ordenes"><Icono nombre="mas" />Nueva factura desde OCs</router-link>
  </div>

  <div class="filtros">
    <div class="segmentos" role="group" aria-label="Vista">
      <button v-for="[v, t] in VISTAS" :key="v" class="segmento" type="button" :aria-pressed="filtros.vista === v" @click="filtros.vista = v; recargar()">{{ t }}</button>
    </div>
  </div>
  <div class="filtros">
    <label class="buscador">
      <Icono nombre="buscar" :tam="16" />
      <input v-model="filtros.q" type="search" placeholder="Buscar número de factura u OC" aria-label="Buscar" @input="buscar" />
    </label>
    <select v-model="filtros.estado" aria-label="Estado" @change="recargar">
      <option value="">Cualquier estado</option>
      <option value="BORRADOR">Borrador</option>
      <option value="EN_CORRECCION">En corrección</option>
      <option value="FINALIZADA">Finalizada</option>
      <option value="CANCELADA">Cancelada</option>
    </select>
    <span class="ayuda separar">{{ datos.total }} facturas</span>
  </div>

  <div class="tabla-marco tabla-fija">
    <table class="tabla">
      <thead>
        <tr>
          <ThOrden campo="nombre" :orden="filtros.orden" @ordenar="ordenar">Factura</ThOrden>
          <ThOrden v-if="!sesion.proveedorId" campo="proveedor" :orden="filtros.orden" @ordenar="ordenar">Proveedor</ThOrden>
          <ThOrden campo="estado" :orden="filtros.orden" @ordenar="ordenar">Estado</ThOrden>
          <th class="num">Importe</th>
          <th>En packing lists</th>
          <th>Empaque</th>
          <th>Transporte</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="f in datos.items" :key="f.id" class="clicable" @click="router.push(`/facturas/${f.id}`)">
          <td>
            <router-link :to="`/facturas/${f.id}`" class="cajas-rango" @click.stop>{{ f.nombre }}</router-link>
            <span class="sub">{{ fmtFecha(f.fecha) }} · {{ f.centro }} · {{ f.lineas }} líneas</span>
          </td>
          <td v-if="!sesion.proveedorId">{{ f.proveedor }}</td>
          <td><EstadoBadge :estado="f.estado" /></td>
          <td class="num fuerte">{{ fmtMoneda(f.importe, f.moneda) }}</td>
          <td style="min-width: 130px"><Avance :valor="f.asignado" :total="f.facturado" /></td>
          <td>
            <template v-if="f.pls">{{ f.pls_finalizados }} de {{ f.pls }} PL finalizados</template>
            <span v-else class="apagado">Sin packing list</span>
          </td>
          <td>
            <span v-if="f.pls && f.pls_confirmados === f.pls" class="etiqueta info"><Icono nombre="contenedor" :tam="12" />En contenedor</span>
            <span v-else-if="f.lista_transporte" class="etiqueta ok"><Icono nombre="check" :tam="12" />Lista para embarcar</span>
            <span v-else-if="f.pls_confirmados" class="etiqueta info">{{ f.pls_confirmados }} de {{ f.pls }} en contenedor</span>
            <span v-else class="apagado">—</span>
          </td>
          <td class="num"><Icono nombre="derecha" :tam="16" /></td>
        </tr>
        <tr v-if="!datos.items.length && !cargando">
          <td colspan="8" class="vacio">
            No hay facturas con estos filtros.
            <div><router-link class="btn" to="/ordenes">Crear una desde órdenes de compra</router-link></div>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
  <Paginacion :page="filtros.page" :size="filtros.size" :total="datos.total" @cambiar="(p) => { filtros.page = p; cargar() }" @tamano="(t) => (filtros.size = t)" />
</template>
