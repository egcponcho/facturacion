<script setup>
import { estadosEmbarque } from '@/nucleo/estados.js'
import { opcionesLista } from '@/nucleo/listas.js'
import { t, tx } from '@/i18n/index.js'
import { computed, nextTick, reactive, ref, watch } from 'vue'
import Seleccion from '@/componentes/Seleccion.vue'
import { useRoute, useRouter } from 'vue-router'
import VistasGuardadas from '@/componentes/VistasGuardadas.vue'
import BotonesExportar from '@/componentes/BotonesExportar.vue'
import Icono from '@/componentes/Icono.vue'
import SeguimientoDocumentos from '@/modulos/seguimiento/componentes/SeguimientoDocumentos.vue'
import SelectBusqueda from '@/componentes/SelectBusqueda.vue'
import TableroEmbarques from '@/modulos/seguimiento/componentes/TableroEmbarques.vue'
import TableroLeadTimes from '@/modulos/seguimiento/componentes/TableroLeadTimes.vue'
import TableroOrdenes from '@/modulos/seguimiento/componentes/TableroOrdenes.vue'
import { esInterno, sesion } from '@/stores/sesion'
import { TIEMPO, fmtFecha } from '@/nucleo/utils'

// Filtros de varios valores: se guardan como texto separado por comas
const lst = (v) => (v ? String(v).split(',').filter(Boolean) : [])

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
  ['ordenes', t('Purchase orders'), 'ordenes'], ['embarques', t('Shipments and load units'), 'contenedor'],
  ['documentos', t('Invoicing and packing lists'), 'factura'], ['leadtimes', t('Lead times'), 'reloj'],
]
// Enlaces anteriores: "contenedores" y "mercancia" ahora son embarques y OCs
const ANTERIORES = { contenedores: 'embarques', mercancia: 'ordenes' }
const inicial = ANTERIORES[route.query.vista] || route.query.vista
const vista = ref(VISTAS.some(([v]) => v === inicial) ? inicial : 'ordenes')
const NOMBRES = {
  estado: t('Status'), modo: t('Mode'), etapa: t('Stage'), liberacion_comercial: t('Commercial rel.'), liberacion_logistica: t('Logistics rel.'),
  proveedor: t('Supplier'), sociedad: t('Company'), centro: t('Plant'), xf_vencida: t('XF overdue'),
  marca: t('Brand'), grupo: t('Group'), estilo: t('Style / model'), sku: 'SKU', almacen: t('Warehouse'),
  contenedor: t('Load unit'), documento: 'B/L / AWB', riesgo: t('In-store arrival'), embarque_id: t('Shipment'),
  eta_desde: t('ETA from'), eta_hasta: t('ETA to'), fecha_xf_desde: t('XF from'), fecha_xf_hasta: t('XF to'),
  fecha_tienda_desde: t('In store from'), fecha_tienda_hasta: t('In store to'),
}
// Filtros de variante: uno por atributo del catálogo (var_<CÓDIGO>), sin suponer cuáles usa la empresa
const VAR = 'var_'
const FILTROS = ['q', ...Object.keys(NOMBRES)]
const filtros = reactive(Object.fromEntries(FILTROS.map((k) => [k, ''])))
for (const k of FILTROS) if (route.query[k]) filtros[k] = String(route.query[k])
for (const [k, v] of Object.entries(route.query)) if (k.startsWith(VAR) && v) filtros[k] = String(v)
const claves = () => Object.keys(filtros).filter((k) => FILTROS.includes(k) || k.startsWith(VAR))
// Filtros secundarios: van plegados en «Más filtros», con cuántos hay activos
const AVANZADOS = ['grupo', 'estilo', 'contenedor', 'documento', 'liberacion_comercial', 'liberacion_logistica', 'sku',
  'almacen', 'embarque_id', 'riesgo', 'xf_vencida', 'eta_desde', 'eta_hasta', 'fecha_xf_desde', 'fecha_xf_hasta', 'fecha_tienda_desde',
  'fecha_tienda_hasta', 'sociedad', 'centro', 'proveedor']
const esAvanzado = (k) => AVANZADOS.includes(k) || k.startsWith(VAR)
const masFiltros = ref(claves().some((k) => esAvanzado(k) && filtros[k]))
const avanzadosActivos = computed(() => claves().filter((k) => esAvanzado(k) && filtros[k]).length)
const opciones = ref({})
// Filtros activos que se mandan a los tableros
const params = computed(() => Object.fromEntries(claves().filter((k) => filtros[k]).map((k) => [k, filtros[k]])))
const atributos = computed(() => opciones.value.atributos || [])
const nombreAtributo = (codigo) => tx(atributos.value.find((a) => a.codigo === codigo)?.nombre || codigo)
const liberaciones = (tipo) => opciones.value.liberaciones?.[tipo] || []
const paramsExportar = computed(() => ({ ...params.value, proveedor_id: sesion.proveedorId || undefined }))
const ESTADOS_EMB = estadosEmbarque()
const ESTADOS_OC = [['SIN_COMERCIAL', t('No commercial release')], ['SIN_LOGISTICA', t('No logistics release')],
  ['POR_FACTURAR', t('Released, not invoiced')], ['PARCIAL', t('Partly invoiced')], ['FACTURADA', t('Invoiced, in process')],
  ['EN_CAMINO', t('On the way')], ['RECIBIDA', t('Received')]]
const ETAPAS = [['PEND_LIBERACION', t('Pending release')], ['POR_FACTURAR', t('To invoice')], ['FACTURADO', t('Invoiced, no PL')],
  ['EN_PL', t('In packing list')], ['CONTENEDOR', t('Assigned to a unit')], ['EN_TRANSITO', t('In transit')], ['ARRIBADO', t('Arrived')],
  ['ENTREGADO', t('Delivered')], ['RECIBIDO', t('Received')]]
const MODOS = computed(() => opcionesLista('modo_transporte'))
const RIESGOS = Object.fromEntries(Object.entries(TIEMPO).map(([k, v]) => [k, v[0]]))

const activos = computed(() => claves().filter((k) => k !== 'q' && filtros[k]).map((k) => {
  if (k.startsWith(VAR)) return { k, texto: `${nombreAtributo(k.slice(VAR.length))}: ${lst(filtros[k]).join(', ')}` }
  let texto = filtros[k]
  const nombres = (lista) => lst(filtros[k]).map((c) => lista.find(([v]) => v === c)?.[1] || c).join(', ')
  if (k === 'etapa') texto = nombres(ETAPAS)
  if (k === 'modo') texto = MODOS.value.find(([v]) => v === filtros[k])?.[1] || texto
  if (k === 'riesgo') texto = RIESGOS[filtros[k]] || texto
  if (k === 'estado') texto = nombres([...ESTADOS_EMB, ...ESTADOS_OC])
  if (k === 'xf_vencida') texto = 'yes'
  if (k === 'liberacion_comercial' || k === 'liberacion_logistica') {
    const lista = liberaciones(k === 'liberacion_comercial' ? 'comercial' : 'logistica')
    texto = tx(lista.find((x) => x.codigo === filtros[k])?.nombre || filtros[k])
  }
  if (k === 'embarque_id') texto = lst(filtros[k]).map((id) => opciones.value.embarques?.find((e) => String(e.id) === id)?.codigo || id).join(', ')
  else if (!k.endsWith('_desde') && !k.endsWith('_hasta')) texto = String(texto).split(',').join(', ')
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
// Una vista guardada: su pestaña y sus filtros (los demás se limpian)
async function aplicarVista(q) {
  if (q.vista && q.vista !== vista.value && VISTAS.some(([v]) => v === q.vista)) {
    vista.value = q.vista
    await nextTick()
  }
  for (const k of claves()) filtros[k] = ''
  for (const [k, v] of Object.entries(q)) if (FILTROS.includes(k) || k.startsWith(VAR)) filtros[k] = v || ''
  masFiltros.value = masFiltros.value || Object.keys(q).some(esAvanzado)
  aplicar()
}
function quitar(k) {
  filtros[k] = ''
  aplicar()
}
function limpiar() {
  for (const k of claves()) filtros[k] = ''
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
      <h1>{{ t('Tracking') }}</h1>
      <p v-if="vista === 'ordenes'">{{ t('Each purchase order with its releases and progress. Open it to see every SKU: its stage, the document and load unit it travels in, and whether it reaches the store on time.') }}</p>
      <p v-else-if="vista === 'embarques'">{{ t('Each shipment with its transport document, its load units (containers, air waybills or trucks) and what each one carries per purchase order.') }}</p>
      <p v-else-if="vista === 'documentos'">{{ t('Each invoice and packing list: its step, what it is missing and whether it already has a load unit.') }}</p>
      <p v-else>{{ t('How long each stage takes by origin, whether logistics releases on time before the XF, and whether each PO reaches the port early or late for its in-store date.') }}</p>
    </div>
    <BotonesExportar v-if="!['documentos', 'leadtimes'].includes(vista)" :ruta="`/seguimiento/${vista}/exportar`" :params="paramsExportar" />
  </div>
  <div class="pestanas-pildora" role="tablist">
    <button v-for="[v, txt, i] in VISTAS" :key="v" class="pildora" role="tab" :aria-selected="vista === v" @click="vista = v"><Icono :nombre="i" :tam="15" />{{ tx(txt) }}</button>
  </div>

  <SeguimientoDocumentos v-if="vista === 'documentos'" />
  <TableroLeadTimes v-else-if="vista === 'leadtimes'" />
  <template v-else>
  <div class="filtros" v-filtros>
    <label class="buscador">
      <Icono nombre="buscar" :tam="16" />
      <input v-model="filtros.q" type="search" :placeholder="t('SKU, PO, invoice, PL, B/L…')" :aria-label="t('Search')" @input="buscar" />
    </label>
    <VistasGuardadas pantalla="seguimiento" :actual="{ vista, ...params }" @aplicar="aplicarVista" />
    <template v-if="vista === 'embarques'">
      <Seleccion v-model="filtros.modo" :aria-label="t('Mode of transport')" @change="aplicar">
        <option value="">{{ t('Mode: all') }}</option><option v-for="[v, txt] in MODOS" :key="v" :value="v">{{ t('Mode: {0}', [txt]) }}</option>
      </Seleccion>
      <Seleccion v-model="filtros.estado" :aria-label="t('Shipment status')" @change="aplicar">
        <option value="">{{ t('Status: all') }}</option><option v-for="[v, txt] in ESTADOS_EMB" :key="v" :value="v">{{ t('Status: {0}', [txt]) }}</option>
      </Seleccion>
    </template>
    <template v-if="vista === 'ordenes'">
      <Seleccion v-model="filtros.estado" :aria-label="t('PO status')" @change="aplicar">
        <option value="">{{ t('PO status: all') }}</option><option v-for="[v, txt] in ESTADOS_OC" :key="v" :value="v">{{ t('PO status: {0}', [txt]) }}</option>
      </Seleccion>
    </template>
    <Seleccion v-model="filtros.etapa" :aria-label="t('Goods stage')" @change="aplicar">
      <option value="">{{ t('Stage: all') }}</option><option v-for="[v, txt] in ETAPAS" :key="v" :value="v">{{ t('Stage: {0}', [txt]) }}</option>
    </Seleccion>
    <SelectBusqueda multiple :model-value="lst(filtros.marca)" @update:model-value="(v) => (filtros.marca = v.join(','))" :opciones="opciones.marcas || []" :vacio="t('Brand: all')" :etiqueta="t('Brand')" @change="aplicar" />
    <button type="button" class="btn btn-fantasma mas-filtros-toggle" :aria-expanded="masFiltros" @click="masFiltros = !masFiltros">
      <Icono nombre="filtro" :tam="15" />{{ tx(masFiltros ? t('Fewer filters') : t('More filters')) }}<span v-if="avanzadosActivos" class="cuenta">{{ avanzadosActivos }}</span>
    </button>
  </div>
  <div v-if="masFiltros" class="filtros filtros-avanzados" v-filtros>
    <SelectBusqueda multiple :model-value="lst(filtros.grupo)" @update:model-value="(v) => (filtros.grupo = v.join(','))" :opciones="opciones.grupos || []" :vacio="t('Group: all')" :etiqueta="t('Item group')" @change="aplicar" />
    <SelectBusqueda v-if="(opciones.estilos || []).length" multiple :model-value="lst(filtros.estilo)" @update:model-value="(v) => (filtros.estilo = v.join(','))" :opciones="opciones.estilos" :vacio="t('Style / model: all')" :etiqueta="t('Style / model')" @change="aplicar" />
    <SelectBusqueda v-for="a in atributos" :key="a.codigo" multiple :model-value="lst(filtros[VAR + a.codigo])" @update:model-value="(v) => (filtros[VAR + a.codigo] = v.join(','))"
                    :opciones="a.valores" :vacio="t('{0}: all', [tx(a.nombre)])" :etiqueta="tx(a.nombre)" @change="aplicar" />
    <SelectBusqueda multiple :model-value="lst(filtros.contenedor)" @update:model-value="(v) => (filtros.contenedor = v.join(','))" :opciones="opciones.contenedores || []" :vacio="t('Load unit: all')" :etiqueta="t('Container, air waybill or truck')" @change="aplicar" />
    <SelectBusqueda multiple :model-value="lst(filtros.documento)" @update:model-value="(v) => (filtros.documento = v.join(','))" :opciones="opciones.documentos || []" :vacio="t('B/L / AWB: all')" :etiqueta="t('Transport document')" @change="aplicar" />
    <template v-if="vista === 'ordenes'">
      <!-- Los estados de liberación son los del catálogo: los códigos que manda el ERP de la empresa -->
      <Seleccion v-model="filtros.liberacion_comercial" :aria-label="t('Commercial release')" @change="aplicar">
        <option value="">{{ t('Commercial rel.: all') }}</option>
        <option v-for="x in liberaciones('comercial')" :key="x.codigo" :value="x.codigo">{{ t('Commercial rel.: {0}', [tx(x.nombre)]) }}</option>
      </Seleccion>
      <Seleccion v-model="filtros.liberacion_logistica" :aria-label="t('Logistics release')" @change="aplicar">
        <option value="">{{ t('Logistics rel.: all') }}</option>
        <option v-for="x in liberaciones('logistica')" :key="x.codigo" :value="x.codigo">{{ t('Logistics rel.: {0}', [tx(x.nombre)]) }}</option>
      </Seleccion>
    </template>
    <SelectBusqueda multiple :model-value="lst(filtros.sku)" @update:model-value="(v) => (filtros.sku = v.join(','))" :opciones="opciones.skus || []" :vacio="t('SKU: all')" :etiqueta="t('Item code')" @change="aplicar" />
    <SelectBusqueda multiple :model-value="lst(filtros.almacen)" @update:model-value="(v) => (filtros.almacen = v.join(','))" :opciones="opciones.almacenes || []" :vacio="t('Warehouse: all')" :etiqueta="t('Warehouse')" @change="aplicar" />
    <SelectBusqueda multiple :model-value="lst(filtros.embarque_id)" @update:model-value="(v) => (filtros.embarque_id = v.join(','))" :opciones="(opciones.embarques || []).map((e) => ({ valor: String(e.id), texto: e.codigo }))"
                    :vacio="t('Shipment: all')" :etiqueta="t('Shipment')" @change="aplicar" />
    <SelectBusqueda v-if="esInterno()" multiple :model-value="lst(filtros.proveedor)" @update:model-value="(v) => (filtros.proveedor = v.join(','))" :opciones="opciones.proveedores || []" :vacio="t('Supplier: all')" :etiqueta="t('Supplier')" @change="aplicar" />
    <SelectBusqueda multiple :model-value="lst(filtros.sociedad)" @update:model-value="(v) => (filtros.sociedad = v.join(','))" :opciones="opciones.sociedades || []" :vacio="t('Company: all')" :etiqueta="t('Company')" @change="aplicar" />
    <SelectBusqueda multiple :model-value="lst(filtros.centro)" @update:model-value="(v) => (filtros.centro = v.join(','))" :opciones="opciones.centros || []" :vacio="t('Plant: all')" :etiqueta="t('Plant')" @change="aplicar" />
    <Seleccion v-model="filtros.riesgo" :aria-label="t('Risk')" @change="aplicar">
      <option value="">{{ t('Vs. port deadline: all') }}</option>
      <option v-for="(r, k) in RIESGOS" :key="k" :value="k">{{ t('Vs. port deadline: {0}', [r]) }}</option>
    </Seleccion>
    <label v-if="vista === 'ordenes'" class="check"><input type="checkbox" :checked="!!filtros.xf_vencida" @change="filtros.xf_vencida = $event.target.checked ? '1' : ''; aplicar()" /> {{ t('XF overdue, not invoiced') }}</label>
    <label v-for="[k, txt] in [['eta', 'ETA'], ['fecha_xf', 'XF'], ['fecha_tienda', t('In store')]]" :key="k" class="rango-fechas">
      <span>{{ tx(txt) }}</span>
      <CampoFecha v-model="filtros[`${k}_desde`]" :aria-label="tx(t('{0} from', [txt]))" @change="aplicar" />
      <span>to</span>
      <CampoFecha v-model="filtros[`${k}_hasta`]" :aria-label="tx(t('{0} to', [txt]))" @change="aplicar" />
    </label>
  </div>
  <div v-if="activos.length" class="chips">
    <span v-for="a in activos" :key="a.k" class="chip">{{ tx(a.texto) }}<button type="button" :aria-label="t('Remove {0}', [a.texto])" @click="quitar(a.k)"><Icono nombre="cerrar" :tam="13" /></button></span>
    <button type="button" class="btn btn-fantasma btn-chico" @click="limpiar">{{ t('Clear filters') }}</button>
  </div>

  <TableroOrdenes v-if="vista === 'ordenes'" :filtros="params" @opciones="(o) => (opciones = o)" @filtrar="aplicarDesde" />
  <TableroEmbarques v-else :filtros="params" @opciones="(o) => (opciones = o)" @filtrar="aplicarDesde" />
  </template>
</template>
