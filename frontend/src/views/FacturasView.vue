<script setup>
import { onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api'
import EstadoBadge from '../components/EstadoBadge.vue'
import Paginacion from '../components/Paginacion.vue'
import { esInterno, sesion } from '../stores/sesion'
import { errorApi } from '../stores/ui'
import { fmtFecha, fmtMoneda } from '../utils'

const route = useRoute()
const router = useRouter()
const filtros = reactive({
  estado: route.query.estado || '',
  vista: route.query.vista || '',
  q: route.query.q || '',
  page: 1,
  size: 25,
})
const datos = ref({ items: [], total: 0 })
const cargando = ref(false)

const VISTAS = [
  ['', 'Todas'],
  ['editables', 'En borrador o corrección'],
  ['pl_incompletos', 'Con packing lists sin finalizar'],
  ['borradores_antiguos', 'Borradores antiguos'],
]
if (esInterno()) VISTAS.push(['lista_transporte', 'Listas para asignar a transporte'], ['pl_sin_unidad', 'Con PL sin unidad de carga'])

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
      <h1>Facturas y packing lists</h1>
      <p>Cada factura es un espacio de trabajo: líneas y precios, sus packing lists con cajas y el seguimiento del transporte.</p>
    </div>
    <router-link class="btn btn-primario" to="/ordenes">Nueva factura desde OCs</router-link>
  </div>

  <div class="filtros">
    <input v-model="filtros.q" type="search" placeholder="Buscar número de factura u OC" aria-label="Buscar" @input="buscar" />
    <select v-model="filtros.vista" aria-label="Vista" @change="recargar">
      <option v-for="[v, t] in VISTAS" :key="v" :value="v">{{ t }}</option>
    </select>
    <select v-model="filtros.estado" aria-label="Estado" @change="recargar">
      <option value="">Cualquier estado</option>
      <option value="BORRADOR">Borrador</option>
      <option value="EN_CORRECCION">En corrección</option>
      <option value="FINALIZADA">Finalizada</option>
      <option value="CANCELADA">Cancelada</option>
    </select>
  </div>

  <div class="tabla-marco">
    <table class="tabla">
      <thead>
        <tr>
          <th>Factura</th>
          <th v-if="!sesion.proveedorId">Proveedor</th>
          <th>Fecha</th>
          <th>Estado</th>
          <th>Centro</th>
          <th class="num">Líneas</th>
          <th class="num">Importe</th>
          <th>Packing lists</th>
          <th>Transporte</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="f in datos.items" :key="f.id" class="clicable" @click="router.push(`/facturas/${f.id}`)">
          <td><router-link :to="`/facturas/${f.id}`" @click.stop><strong>{{ f.nombre }}</strong></router-link></td>
          <td v-if="!sesion.proveedorId">{{ f.proveedor }}</td>
          <td>{{ fmtFecha(f.fecha) }}</td>
          <td><EstadoBadge :estado="f.estado" /></td>
          <td>{{ f.centro }}</td>
          <td class="num">{{ f.lineas }}</td>
          <td class="num">{{ fmtMoneda(f.importe, f.moneda) }}</td>
          <td>
            <template v-if="f.pls">{{ f.pls_finalizados }} de {{ f.pls }} finalizados</template>
            <span v-else class="apagado">Sin PL</span>
            <span v-if="f.facturado > f.asignado" class="etiqueta aviso">Falta asignar</span>
          </td>
          <td>
            <span v-if="f.lista_transporte" class="etiqueta ok">Lista</span>
            <span v-else class="apagado">—</span>
          </td>
        </tr>
        <tr v-if="!datos.items.length && !cargando">
          <td colspan="9" class="vacio">
            No hay facturas con estos filtros.
            <div><router-link class="btn" to="/ordenes">Crear una desde órdenes de compra</router-link></div>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
  <Paginacion :page="filtros.page" :size="filtros.size" :total="datos.total" @cambiar="(p) => { filtros.page = p; cargar() }" />
</template>
