<script setup>
import { t, tx } from '@/i18n/index.js'
import { computed, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '@/nucleo/api'
import Avance from '@/componentes/Avance.vue'
import EstadoBadge from '@/componentes/EstadoBadge.vue'
import EstadoVacio from '@/componentes/EstadoVacio.vue'
import TablaDatos from '@/componentes/TablaDatos.vue'
import ResumenFactura from '@/modulos/facturacion/componentes/ResumenFactura.vue'
import Icono from '@/componentes/Icono.vue'
import { esInterno, sesion, ve } from '@/stores/sesion'
import { errorApi } from '@/stores/ui'
import { fmtFecha, fmtMoneda } from '@/nucleo/utils'

const route = useRoute()
const router = useRouter()
// Clic en la fila: resumen en el panel lateral (sin perder filtros ni página); el número abre la página
const resumenId = ref(null)
const tabla = ref(null)
// Vistas predefinidas (filtros de un clic) y búsqueda; el resto de los filtros va en cada columna
const filtros = reactive({ vista: route.query.vista || '', q: route.query.q || '' })
const datos = ref({ items: [], total: 0 })
const cargando = ref(false)

const VISTAS = [
  ['', t('All')],
  ['editables', t('In progress')],
  ['pl_incompletos', t('Packing pending')],
  ['borradores_antiguos', t('Old drafts')],
]
if (esInterno()) VISTAS.push(['lista_transporte', t('Ready to ship')], ['pl_sin_unidad', t('PL without load unit')])
const ESTADOS = [['BORRADOR', t('Draft')], ['EN_CORRECCION', t('In correction')], ['FINALIZADA', t('Finalized')], ['CANCELADA', t('Cancelled')]]
const columnas = computed(() => [
  { clave: 'nombre', texto: t('Invoice'), fija: true, prioridad: 1 },
  ...(sesion.proveedorId ? [] : [{ clave: 'proveedor', texto: t('Supplier'), prioridad: 2, filtro: 'opcion',
    opciones: (sesion.proveedores || []).map((p) => [p.id, p.nombre]) }]),
  { clave: 'estado', texto: t('Status'), prioridad: 1, filtro: 'opcion', opciones: ESTADOS },
  { clave: 'importe', texto: t('Amount'), num: true, grupo: 'precios', ordenable: false, prioridad: 2 },
  { clave: 'asignado', texto: t('In packing lists'), ordenable: false, prioridad: 3 },
  { clave: 'pls', texto: t('Packing'), ordenable: false, prioridad: 3 },
  { clave: 'transporte', texto: t('Transport'), ordenable: false, prioridad: 2 },
])

let ultima = null
async function consultar(c = ultima) {
  if (!c) return
  ultima = c
  cargando.value = true
  try {
    datos.value = await api.get('/facturas', {
      q: filtros.q, vista: filtros.vista, estado: c.filtros.estado, orden: c.orden, page: c.page, size: c.size,
      proveedor_id: sesion.proveedorId || c.filtros.proveedor,
    })
    router.replace({ query: { ...(c.filtros.estado && { estado: c.filtros.estado }), ...(filtros.vista && { vista: filtros.vista }), ...(filtros.q && { q: filtros.q }) } })
  } catch (e) {
    errorApi(e)
  } finally {
    cargando.value = false
  }
}
// La búsqueda, la vista o el proveedor elegido vuelven a la primera página
function recargar() {
  if (tabla.value?.pagina !== 1) tabla.value.pagina = 1
  else consultar()
}
let espera
function buscar() {
  clearTimeout(espera)
  espera = setTimeout(recargar, 300)
}
watch(() => sesion.proveedorId, recargar)
</script>

<template>
  <div class="pagina-cabeza">
    <div>
      <h1>{{ t('Invoices and packing') }}</h1>
      <p>{{ t('Each invoice is a workspace: its lines, its packing lists with cartons and the shipment tracking.') }}</p>
    </div>
    <div class="acciones">
      <router-link to="/tableros/facturacion" class="btn btn-fantasma"><Icono nombre="grafica" />{{ t('Indicators') }}</router-link>
      <router-link class="btn btn-primario" to="/ordenes"><Icono nombre="mas" />{{ t('New invoice from POs') }}</router-link>
    </div>
  </div>

  <div class="filtros" v-filtros>
    <div class="segmentos" role="group" :aria-label="t('View')">
      <button v-for="[v, txt] in VISTAS" :key="v" class="segmento" type="button" :aria-pressed="filtros.vista === v" @click="filtros.vista = v; recargar()">{{ tx(txt) }}</button>
    </div>
  </div>

  <TablaDatos ref="tabla" tabla="facturas" modo="servidor" :columnas="columnas" :filas="datos.items" :total="datos.total" :cargando="cargando"
              :filtros-iniciales="route.query.estado ? { estado: route.query.estado } : {}" fila-clicable :fila-activa="resumenId" :etiqueta="t('Invoices')"
              vistas-guardadas :externos="{ vista: filtros.vista, q: filtros.q }"
              @consulta="consultar" @fila="(f) => (resumenId = f.id)" @vista="(q) => { filtros.vista = q.vista || ''; filtros.q = q.q || ''; recargar() }">
    <template #barra>
      <label class="buscador">
        <Icono nombre="buscar" :tam="16" />
        <input v-model="filtros.q" type="search" :placeholder="t('Search invoice or PO number')" :aria-label="t('Search')" @input="buscar" />
      </label>
    </template>
    <template #celda-nombre="{ fila: f }">
      <router-link :to="`/facturas/${f.id}`" class="cajas-rango" @click.stop>{{ tx(f.nombre) }}</router-link>
      <span class="sub">{{ ve('codigos_internos') ? t('{0} · {1} · {2} lines', [fmtFecha(f.fecha), f.centro, f.lineas]) : t('{0} · {1} lines', [fmtFecha(f.fecha), f.lineas]) }}</span>
    </template>
    <template #celda-estado="{ fila: f }"><EstadoBadge :estado="f.estado" /></template>
    <template #celda-importe="{ fila: f }"><span class="fuerte">{{ fmtMoneda(f.importe, f.moneda) }}</span></template>
    <template #celda-asignado="{ fila: f }"><Avance :valor="f.asignado" :total="f.facturado" /></template>
    <template #celda-pls="{ fila: f }">
      <template v-if="f.pls">{{ t('{0} of {1} PL finalized', [f.pls_finalizados, f.pls]) }}</template>
      <span v-else class="apagado">{{ t('No packing list') }}</span>
    </template>
    <template #celda-transporte="{ fila: f }">
      <span v-if="f.pls && f.pls_confirmados === f.pls" class="etiqueta info ms-0"><Icono nombre="contenedor" :tam="12" />{{ t('In load unit') }}</span>
      <span v-else-if="f.lista_transporte" class="etiqueta ok ms-0"><Icono nombre="check" :tam="12" />{{ t('Ready to ship') }}</span>
      <span v-else-if="f.pls_confirmados" class="etiqueta info ms-0">{{ t('{0} of {1} in load unit', [f.pls_confirmados, f.pls]) }}</span>
      <span v-else class="apagado">—</span>
    </template>
    <template #acciones><Icono nombre="derecha" :tam="16" /></template>
    <template #vacio>
      <div v-if="filtros.vista || filtros.q" class="vacio">
        {{ t('No invoices match these filters.') }}
        <div><router-link class="btn" to="/ordenes">{{ t('Create one from purchase orders') }}</router-link></div>
      </div>
      <EstadoVacio v-else icono="factura" :titulo="t('There are no invoices yet.')"
                   :texto="t('An invoice is created from the released purchase order lines you are going to ship; its packing lists say how the goods are packed.')"
                   :titulo-requisitos="t('To create one you need:')"
                   :requisitos="[t('A released purchase order with quantity to invoice')]">
        <router-link class="btn btn-primario" to="/ordenes"><Icono nombre="mas" />{{ t('Invoice from POs') }}</router-link>
      </EstadoVacio>
    </template>
  </TablaDatos>
  <ResumenFactura v-if="resumenId" :id="resumenId" @cerrar="resumenId = null" />
</template>
