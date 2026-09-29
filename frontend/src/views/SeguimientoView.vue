<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import BotonesExportar from '../components/BotonesExportar.vue'
import Icono from '../components/Icono.vue'
import SeguimientoDocumentos from '../components/SeguimientoDocumentos.vue'
import SelectBusqueda from '../components/SelectBusqueda.vue'
import TableroEmbarques from '../components/TableroEmbarques.vue'
import TableroOrdenes from '../components/TableroOrdenes.vue'
import { esInterno, sesion } from '../stores/sesion'
import { fmtFecha } from '../utils'

// Tres tableros sin repetir información:
//  - Órdenes de compra: liberaciones y avance; cada OC se abre en su detalle
//    por SKU (etapa, factura/PL, embarque y unidad, llegada vs. tienda).
//  - Embarques: un renglón por documento de transporte; se abre en sus
//    unidades de carga y cada unidad en lo que lleva por OC.
//  - Facturación y packing lists: en qué paso va cada documento.
// Los dos primeros comparten los mismos filtros de mercancía.
const route = useRoute()
const router = useRouter()
const VISTAS = [
  ['ordenes', 'Purchase orders', 'ordenes'], ['embarques', 'Shipments and load units', 'contenedor'],
  ['documentos', 'Invoicing and packing lists', 'factura'],
]
// Enlaces anteriores: "contenedores" y "mercancia" ahora son embarques y OCs
const ANTERIORES = { contenedores: 'embarques', mercancia: 'ordenes' }
const inicial = ANTERIORES[route.query.vista] || route.query.vista
const vista = ref(VISTAS.some(([v]) => v === inicial) ? inicial : 'ordenes')
const NOMBRES = {
  estado: 'Status', modo: 'Mode', etapa: 'Stage', liberacion_comercial: 'Commercial rel.', liberacion_logistica: 'Logistics rel.',
  proveedor: 'Supplier', sociedad: 'Company', centro: 'Plant', xf_vencida: 'XF overdue',
  marca: 'Brand', grupo: 'Group', estilo: 'Style', color: 'Color', talla: 'Size', sku: 'SKU', almacen: 'Warehouse',
  contenedor: 'Load unit', documento: 'B/L / AWB', riesgo: 'In-store arrival', embarque_id: 'Shipment',
  eta_desde: 'ETA from', eta_hasta: 'ETA to', fecha_xf_desde: 'XF from', fecha_xf_hasta: 'XF to',
  fecha_tienda_desde: 'In store from', fecha_tienda_hasta: 'In store to',
}
const FILTROS = ['q', ...Object.keys(NOMBRES)]
const filtros = reactive(Object.fromEntries(FILTROS.map((k) => [k, ''])))
for (const k of FILTROS) if (route.query[k]) filtros[k] = String(route.query[k])
const masFiltros = ref(['talla', 'sku', 'almacen', 'embarque_id', 'riesgo', 'eta_desde', 'eta_hasta', 'fecha_xf_desde',
  'fecha_xf_hasta', 'fecha_tienda_desde', 'fecha_tienda_hasta', 'sociedad', 'centro', 'proveedor'].some((k) => filtros[k]))
const opciones = ref({})
// Filtros activos que se mandan a los tableros
const params = computed(() => Object.fromEntries(FILTROS.filter((k) => filtros[k]).map((k) => [k, filtros[k]])))
const paramsExportar = computed(() => ({ ...params.value, proveedor_id: sesion.proveedorId || undefined }))
const ESTADOS_EMB = [['PLANIFICADO', 'Planned'], ['EN_TRANSITO', 'In transit'], ['ARRIBADO', 'Arrived'], ['ENTREGADO', 'Delivered'], ['RECIBIDO', 'Received']]
const ESTADOS_OC = [['SIN_COMERCIAL', 'No commercial release (P)'], ['SIN_LOGISTICA', 'No logistics release (304)'],
  ['POR_FACTURAR', 'Released, not invoiced'], ['PARCIAL', 'Partly invoiced'], ['FACTURADA', 'Invoiced, in process'],
  ['EN_CAMINO', 'On the way'], ['RECIBIDA', 'Received']]
const ETAPAS = [['PEND_LIBERACION', 'Pending release'], ['POR_FACTURAR', 'To invoice'], ['FACTURADO', 'Invoiced, no PL'],
  ['EN_PL', 'In packing list'], ['CONTENEDOR', 'Assigned to a unit'], ['EN_TRANSITO', 'In transit'], ['ARRIBADO', 'Arrived'],
  ['ENTREGADO', 'Delivered'], ['RECIBIDO', 'Received']]
const MODOS = [['MARITIMO', 'Ocean'], ['AEREO', 'Air'], ['TERRESTRE', 'Road']]
const RIESGOS = { ATRASO: 'Arrives late', JUSTO: 'Tight', A_TIEMPO: 'On time' }

const activos = computed(() => FILTROS.filter((k) => k !== 'q' && filtros[k]).map((k) => {
  let texto = filtros[k]
  if (k === 'etapa') texto = ETAPAS.find(([v]) => v === filtros[k])?.[1] || texto
  if (k === 'modo') texto = MODOS.find(([v]) => v === filtros[k])?.[1] || texto
  if (k === 'riesgo') texto = RIESGOS[filtros[k]] || texto
  if (k === 'estado') texto = [...ESTADOS_EMB, ...ESTADOS_OC].find(([v]) => v === filtros[k])?.[1] || texto
  if (k === 'xf_vencida') texto = 'yes'
  if (k === 'embarque_id') texto = opciones.value.embarques?.find((e) => String(e.id) === String(filtros[k]))?.codigo || texto
  if (k.endsWith('_desde') || k.endsWith('_hasta')) texto = fmtFecha(texto)
  return { k, texto: `${NOMBRES[k]}: ${texto}` }
}))

// Cambia la URL; los tableros recargan solos al cambiar los filtros
function aplicar() {
  router.replace({ query: { vista: vista.value, ...params.value } })
}
// Clic en un indicador del tablero: aplica ese filtro
function aplicarDesde(obj) {
  for (const [k, v] of Object.entries(obj)) filtros[k] = v
  aplicar()
}
watch(vista, () => {
  filtros.estado = '' // el estado es del embarque o de la OC según el tablero
  aplicar()
})
function quitar(k) {
  filtros[k] = ''
  aplicar()
}
function limpiar() {
  for (const k of FILTROS) filtros[k] = ''
  aplicar()
}
let espera
function buscar() {
  clearTimeout(espera)
  espera = setTimeout(aplicar, 300)
}
</script>

<template>
  <div class="pagina-cabeza">
    <div>
      <h1>Tracking</h1>
      <p v-if="vista === 'ordenes'">Each purchase order with its releases and progress. Open it to see every SKU: its stage, the document and load unit it travels in, and whether it reaches the store on time.</p>
      <p v-else-if="vista === 'embarques'">Each shipment with its transport document, its load units (containers, air waybills or trucks) and what each one carries per purchase order.</p>
      <p v-else>Each invoice and packing list: its step, what it is missing and whether it already has a load unit.</p>
    </div>
    <BotonesExportar v-if="vista !== 'documentos'" :ruta="`/seguimiento/${vista}/exportar`" :params="paramsExportar" />
  </div>
  <div class="pestanas-pildora" role="tablist">
    <button v-for="[v, t, i] in VISTAS" :key="v" class="pildora" role="tab" :aria-selected="vista === v" @click="vista = v"><Icono :nombre="i" :tam="15" />{{ t }}</button>
  </div>

  <SeguimientoDocumentos v-if="vista === 'documentos'" />
  <template v-else>
  <div class="filtros">
    <label class="buscador">
      <Icono nombre="buscar" :tam="16" />
      <input v-model="filtros.q" type="search" placeholder="SKU, PO, invoice, PL, container or B/L" aria-label="Search" @input="buscar" />
    </label>
    <template v-if="vista === 'embarques'">
      <select v-model="filtros.modo" aria-label="Mode of transport" @change="aplicar">
        <option value="">Mode: all</option><option v-for="[v, t] in MODOS" :key="v" :value="v">{{ t }}</option>
      </select>
      <select v-model="filtros.estado" aria-label="Shipment status" @change="aplicar">
        <option value="">Status: all</option><option v-for="[v, t] in ESTADOS_EMB" :key="v" :value="v">{{ t }}</option>
      </select>
    </template>
    <template v-if="vista === 'ordenes'">
      <select v-model="filtros.estado" aria-label="PO status" @change="aplicar">
        <option value="">PO status: all</option><option v-for="[v, t] in ESTADOS_OC" :key="v" :value="v">{{ t }}</option>
      </select>
      <select v-model="filtros.liberacion_comercial" aria-label="Commercial release" @change="aplicar">
        <option value="">Commercial rel.: all</option><option value="C">C · Released</option><option value="P">P · Pending</option>
      </select>
      <select v-model="filtros.liberacion_logistica" aria-label="Logistics release" @change="aplicar">
        <option value="">Logistics rel.: all</option><option value="300">300</option><option value="301">301</option><option value="304">304 · Not released</option>
      </select>
    </template>
    <select v-model="filtros.etapa" aria-label="Goods stage" @change="aplicar">
      <option value="">Stage: all</option><option v-for="[v, t] in ETAPAS" :key="v" :value="v">{{ t }}</option>
    </select>
    <SelectBusqueda v-model="filtros.marca" :opciones="opciones.marcas || []" vacio="Brand: all" etiqueta="Brand" @change="aplicar" />
    <SelectBusqueda v-model="filtros.grupo" :opciones="opciones.grupos || []" vacio="Group: all" etiqueta="Item group" @change="aplicar" />
    <SelectBusqueda v-model="filtros.estilo" :opciones="opciones.estilos || []" vacio="Style: all" etiqueta="Style" @change="aplicar" />
    <SelectBusqueda v-model="filtros.color" :opciones="opciones.colores || []" vacio="Color: all" etiqueta="Color" @change="aplicar" />
    <SelectBusqueda v-model="filtros.contenedor" :opciones="opciones.contenedores || []" vacio="Load unit: all" etiqueta="Container, air waybill or truck" @change="aplicar" />
    <SelectBusqueda v-model="filtros.documento" :opciones="opciones.documentos || []" vacio="B/L / AWB: all" etiqueta="Transport document" @change="aplicar" />
    <button type="button" class="btn btn-fantasma btn-chico" :aria-expanded="masFiltros" @click="masFiltros = !masFiltros">
      <Icono nombre="filtro" :tam="14" />{{ masFiltros ? 'Fewer filters' : 'More filters' }}
    </button>
  </div>
  <div v-if="masFiltros" class="filtros filtros-extra">
    <SelectBusqueda v-model="filtros.talla" :opciones="opciones.tallas || []" vacio="Size: all" etiqueta="Size" @change="aplicar" />
    <SelectBusqueda v-model="filtros.sku" :opciones="opciones.skus || []" vacio="SKU: all" etiqueta="Item code" @change="aplicar" />
    <SelectBusqueda v-model="filtros.almacen" :opciones="opciones.almacenes || []" vacio="Warehouse: all" etiqueta="Warehouse" @change="aplicar" />
    <SelectBusqueda v-model="filtros.embarque_id" :opciones="(opciones.embarques || []).map((e) => ({ valor: String(e.id), texto: e.codigo }))"
                    vacio="Shipment: all" etiqueta="Shipment" @change="aplicar" />
    <SelectBusqueda v-if="esInterno()" v-model="filtros.proveedor" :opciones="opciones.proveedores || []" vacio="Supplier: all" etiqueta="Supplier" @change="aplicar" />
    <SelectBusqueda v-model="filtros.sociedad" :opciones="opciones.sociedades || []" vacio="Company: all" etiqueta="Company" @change="aplicar" />
    <SelectBusqueda v-model="filtros.centro" :opciones="opciones.centros || []" vacio="Plant: all" etiqueta="Plant" @change="aplicar" />
    <select v-model="filtros.riesgo" aria-label="Risk" @change="aplicar">
      <option value="">In-store arrival: all</option>
      <option v-for="(r, k) in RIESGOS" :key="k" :value="k">{{ r }}</option>
    </select>
    <label v-if="vista === 'ordenes'" class="check"><input type="checkbox" :checked="!!filtros.xf_vencida" @change="filtros.xf_vencida = $event.target.checked ? '1' : ''; aplicar()" /> XF overdue, not invoiced</label>
    <label v-for="[k, t] in [['eta', 'ETA'], ['fecha_xf', 'XF'], ['fecha_tienda', 'In store']]" :key="k" class="rango-fechas">
      <span>{{ t }}</span>
      <input v-model="filtros[`${k}_desde`]" type="date" :aria-label="`${t} from`" @change="aplicar" />
      <span>to</span>
      <input v-model="filtros[`${k}_hasta`]" type="date" :aria-label="`${t} to`" @change="aplicar" />
    </label>
  </div>
  <div v-if="activos.length" class="chips">
    <span v-for="a in activos" :key="a.k" class="chip">{{ a.texto }}<button type="button" :aria-label="`Remove ${a.texto}`" @click="quitar(a.k)"><Icono nombre="cerrar" :tam="13" /></button></span>
    <button type="button" class="btn btn-fantasma btn-chico" @click="limpiar">Clear filters</button>
  </div>

  <TableroOrdenes v-if="vista === 'ordenes'" :filtros="params" @opciones="(o) => (opciones = o)" @filtrar="aplicarDesde" />
  <TableroEmbarques v-else :filtros="params" @opciones="(o) => (opciones = o)" @filtrar="aplicarDesde" />
  </template>
</template>
