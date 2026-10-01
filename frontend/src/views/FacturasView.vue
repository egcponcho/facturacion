<script setup>
import { t, tx } from '../i18n/index.js'
import { onMounted, reactive, ref, watch } from 'vue'
import Seleccion from '../components/Seleccion.vue'
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
  ['', t('All')],
  ['editables', t('In progress')],
  ['pl_incompletos', t('Packing pending')],
  ['borradores_antiguos', t('Old drafts')],
]
if (esInterno()) VISTAS.push(['lista_transporte', t('Ready to ship')], ['pl_sin_unidad', t('PL without load unit')])

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
      <h1>{{ t('Invoices and packing') }}</h1>
      <p>{{ t('Each invoice is a workspace: its lines, its packing lists with cartons and the shipment tracking.') }}</p>
    </div>
    <router-link class="btn btn-primario" to="/ordenes"><Icono nombre="mas" />{{ t('New invoice from POs') }}</router-link>
  </div>

  <div class="filtros">
    <div class="segmentos" role="group" :aria-label="t('View')">
      <button v-for="[v, txt] in VISTAS" :key="v" class="segmento" type="button" :aria-pressed="filtros.vista === v" @click="filtros.vista = v; recargar()">{{ tx(txt) }}</button>
    </div>
  </div>
  <div class="filtros">
    <label class="buscador">
      <Icono nombre="buscar" :tam="16" />
      <input v-model="filtros.q" type="search" :placeholder="t('Search invoice or PO number')" :aria-label="t('Search')" @input="buscar" />
    </label>
    <Seleccion v-model="filtros.estado" :aria-label="t('Status')" @change="recargar">
      <option value="">{{ t('Any status') }}</option>
      <option value="BORRADOR">{{ t('Draft') }}</option>
      <option value="EN_CORRECCION">{{ t('In correction') }}</option>
      <option value="FINALIZADA">{{ t('Finalized') }}</option>
      <option value="CANCELADA">{{ t('Cancelled') }}</option>
    </Seleccion>
    <span class="ayuda separar">{{ t('{0} invoices', [datos.total]) }}</span>
  </div>

  <div class="tabla-marco tabla-fija">
    <table class="tabla">
      <thead>
        <tr>
          <ThOrden campo="nombre" :orden="filtros.orden" @ordenar="ordenar">{{ t('Invoice') }}</ThOrden>
          <ThOrden v-if="!sesion.proveedorId" campo="proveedor" :orden="filtros.orden" @ordenar="ordenar">{{ t('Supplier') }}</ThOrden>
          <ThOrden campo="estado" :orden="filtros.orden" @ordenar="ordenar">{{ t('Status') }}</ThOrden>
          <th class="num">{{ t('Amount') }}</th>
          <th>{{ t('In packing lists') }}</th>
          <th>{{ t('Packing') }}</th>
          <th>{{ t('Transport') }}</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="f in datos.items" :key="f.id" class="clicable" @click="router.push(`/facturas/${f.id}`)">
          <td>
            <router-link :to="`/facturas/${f.id}`" class="cajas-rango" @click.stop>{{ tx(f.nombre) }}</router-link>
            <span class="sub">{{ t('{0} · {1} · {2} lines', [fmtFecha(f.fecha), f.centro, f.lineas]) }}</span>
          </td>
          <td v-if="!sesion.proveedorId">{{ tx(f.proveedor) }}</td>
          <td><EstadoBadge :estado="f.estado" /></td>
          <td class="num fuerte">{{ fmtMoneda(f.importe, f.moneda) }}</td>
          <td style="min-width: 130px"><Avance :valor="f.asignado" :total="f.facturado" /></td>
          <td>
            <template v-if="f.pls">{{ t('{0} of {1} PL finalized', [f.pls_finalizados, f.pls]) }}</template>
            <span v-else class="apagado">{{ t('No packing list') }}</span>
          </td>
          <td>
            <span v-if="f.pls && f.pls_confirmados === f.pls" class="etiqueta info"><Icono nombre="contenedor" :tam="12" />{{ t('In load unit') }}</span>
            <span v-else-if="f.lista_transporte" class="etiqueta ok"><Icono nombre="check" :tam="12" />{{ t('Ready to ship') }}</span>
            <span v-else-if="f.pls_confirmados" class="etiqueta info">{{ t('{0} of {1} in load unit', [f.pls_confirmados, f.pls]) }}</span>
            <span v-else class="apagado">—</span>
          </td>
          <td class="num"><Icono nombre="derecha" :tam="16" /></td>
        </tr>
        <tr v-if="!datos.items.length && !cargando">
          <td colspan="8" class="vacio">
            {{ t('No invoices match these filters.') }}
            <div><router-link class="btn" to="/ordenes">{{ t('Create one from purchase orders') }}</router-link></div>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
  <Paginacion :page="filtros.page" :size="filtros.size" :total="datos.total" @cambiar="(p) => { filtros.page = p; cargar() }" @tamano="(t) => (filtros.size = t)" />
</template>
