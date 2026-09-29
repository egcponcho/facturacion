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
  ['ordenes', 'Órdenes de compra', 'ordenes'], ['embarques', 'Embarques y unidades de carga', 'contenedor'],
  ['documentos', 'Facturación y packing lists', 'factura'],
]
// Enlaces anteriores: "contenedores" y "mercancia" ahora son embarques y OCs
const ANTERIORES = { contenedores: 'embarques', mercancia: 'ordenes' }
const inicial = ANTERIORES[route.query.vista] || route.query.vista
const vista = ref(VISTAS.some(([v]) => v === inicial) ? inicial : 'ordenes')
const NOMBRES = {
  estado: 'Estado', modo: 'Modo', etapa: 'Etapa', liberacion_comercial: 'Lib. comercial', liberacion_logistica: 'Lib. logística',
  proveedor: 'Proveedor', sociedad: 'Sociedad', centro: 'Centro', xf_vencida: 'XF vencida',
  marca: 'Marca', grupo: 'Grupo', estilo: 'Estilo', color: 'Color', talla: 'Talla', sku: 'SKU', almacen: 'Almacén',
  contenedor: 'Unidad de carga', documento: 'BL / AWB', riesgo: 'Llegada a tienda', embarque_id: 'Embarque',
  eta_desde: 'ETA desde', eta_hasta: 'ETA hasta', fecha_xf_desde: 'XF desde', fecha_xf_hasta: 'XF hasta',
  fecha_tienda_desde: 'En tienda desde', fecha_tienda_hasta: 'En tienda hasta',
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
const ESTADOS_EMB = [['PLANIFICADO', 'Planificado'], ['EN_TRANSITO', 'En tránsito'], ['ARRIBADO', 'Arribado'], ['ENTREGADO', 'Entregado'], ['RECIBIDO', 'Recibido']]
const ESTADOS_OC = [['SIN_COMERCIAL', 'Sin liberación comercial (P)'], ['SIN_LOGISTICA', 'Sin liberación logística (304)'],
  ['POR_FACTURAR', 'Liberada, sin facturar'], ['PARCIAL', 'Facturada en parte'], ['FACTURADA', 'Facturada, en proceso'],
  ['EN_CAMINO', 'En camino'], ['RECIBIDA', 'Recibida']]
const ETAPAS = [['PEND_LIBERACION', 'Pendiente de liberación'], ['POR_FACTURAR', 'Por facturar'], ['FACTURADO', 'Facturado sin PL'],
  ['EN_PL', 'En packing list'], ['CONTENEDOR', 'Asignado a unidad'], ['EN_TRANSITO', 'En tránsito'], ['ARRIBADO', 'Arribado'],
  ['ENTREGADO', 'Entregado'], ['RECIBIDO', 'Recibido']]
const MODOS = [['MARITIMO', 'Marítimo'], ['AEREO', 'Aéreo'], ['TERRESTRE', 'Terrestre']]
const RIESGOS = { ATRASO: 'Llega tarde', JUSTO: 'Justo', A_TIEMPO: 'A tiempo' }

const activos = computed(() => FILTROS.filter((k) => k !== 'q' && filtros[k]).map((k) => {
  let texto = filtros[k]
  if (k === 'etapa') texto = ETAPAS.find(([v]) => v === filtros[k])?.[1] || texto
  if (k === 'modo') texto = MODOS.find(([v]) => v === filtros[k])?.[1] || texto
  if (k === 'riesgo') texto = RIESGOS[filtros[k]] || texto
  if (k === 'estado') texto = [...ESTADOS_EMB, ...ESTADOS_OC].find(([v]) => v === filtros[k])?.[1] || texto
  if (k === 'xf_vencida') texto = 'sí'
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
      <h1>Seguimiento</h1>
      <p v-if="vista === 'ordenes'">Cada orden de compra con sus liberaciones y avance. Ábrela para ver cada SKU: en qué etapa está, en qué documento y unidad de carga va y si llega a tiempo a tienda.</p>
      <p v-else-if="vista === 'embarques'">Cada embarque con su documento de transporte, sus unidades de carga (contenedores, guías o camiones) y lo que lleva cada una por orden de compra.</p>
      <p v-else>Cada factura y packing list: en qué paso va, qué le falta y si ya tiene unidad de carga.</p>
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
      <input v-model="filtros.q" type="search" placeholder="SKU, OC, factura, PL, contenedor o BL" aria-label="Buscar" @input="buscar" />
    </label>
    <template v-if="vista === 'embarques'">
      <select v-model="filtros.modo" aria-label="Modo de transporte" @change="aplicar">
        <option value="">Modo: todos</option><option v-for="[v, t] in MODOS" :key="v" :value="v">{{ t }}</option>
      </select>
      <select v-model="filtros.estado" aria-label="Estado del embarque" @change="aplicar">
        <option value="">Estado: todos</option><option v-for="[v, t] in ESTADOS_EMB" :key="v" :value="v">{{ t }}</option>
      </select>
    </template>
    <template v-if="vista === 'ordenes'">
      <select v-model="filtros.estado" aria-label="Estado de la OC" @change="aplicar">
        <option value="">Estado OC: todos</option><option v-for="[v, t] in ESTADOS_OC" :key="v" :value="v">{{ t }}</option>
      </select>
      <select v-model="filtros.liberacion_comercial" aria-label="Liberación comercial" @change="aplicar">
        <option value="">Lib. comercial: todas</option><option value="C">C · Liberada</option><option value="P">P · Pendiente</option>
      </select>
      <select v-model="filtros.liberacion_logistica" aria-label="Liberación logística" @change="aplicar">
        <option value="">Lib. logística: todas</option><option value="300">300</option><option value="301">301</option><option value="304">304 · No liberada</option>
      </select>
    </template>
    <select v-model="filtros.etapa" aria-label="Etapa de la mercancía" @change="aplicar">
      <option value="">Etapa: todas</option><option v-for="[v, t] in ETAPAS" :key="v" :value="v">{{ t }}</option>
    </select>
    <SelectBusqueda v-model="filtros.marca" :opciones="opciones.marcas || []" vacio="Marca: todas" etiqueta="Marca" @change="aplicar" />
    <SelectBusqueda v-model="filtros.grupo" :opciones="opciones.grupos || []" vacio="Grupo: todos" etiqueta="Grupo de artículos" @change="aplicar" />
    <SelectBusqueda v-model="filtros.estilo" :opciones="opciones.estilos || []" vacio="Estilo: todos" etiqueta="Estilo" @change="aplicar" />
    <SelectBusqueda v-model="filtros.color" :opciones="opciones.colores || []" vacio="Color: todos" etiqueta="Color" @change="aplicar" />
    <SelectBusqueda v-model="filtros.contenedor" :opciones="opciones.contenedores || []" vacio="Unidad de carga: todas" etiqueta="Contenedor, guía o camión" @change="aplicar" />
    <SelectBusqueda v-model="filtros.documento" :opciones="opciones.documentos || []" vacio="BL / AWB: todos" etiqueta="Documento de transporte" @change="aplicar" />
    <button type="button" class="btn btn-fantasma btn-chico" :aria-expanded="masFiltros" @click="masFiltros = !masFiltros">
      <Icono nombre="filtro" :tam="14" />{{ masFiltros ? 'Menos filtros' : 'Más filtros' }}
    </button>
  </div>
  <div v-if="masFiltros" class="filtros filtros-extra">
    <SelectBusqueda v-model="filtros.talla" :opciones="opciones.tallas || []" vacio="Talla: todas" etiqueta="Talla" @change="aplicar" />
    <SelectBusqueda v-model="filtros.sku" :opciones="opciones.skus || []" vacio="SKU: todos" etiqueta="Código de producto" @change="aplicar" />
    <SelectBusqueda v-model="filtros.almacen" :opciones="opciones.almacenes || []" vacio="Almacén: todos" etiqueta="Almacén" @change="aplicar" />
    <SelectBusqueda v-model="filtros.embarque_id" :opciones="(opciones.embarques || []).map((e) => ({ valor: String(e.id), texto: e.codigo }))"
                    vacio="Embarque: todos" etiqueta="Embarque" @change="aplicar" />
    <SelectBusqueda v-if="esInterno()" v-model="filtros.proveedor" :opciones="opciones.proveedores || []" vacio="Proveedor: todos" etiqueta="Proveedor" @change="aplicar" />
    <SelectBusqueda v-model="filtros.sociedad" :opciones="opciones.sociedades || []" vacio="Sociedad: todas" etiqueta="Sociedad" @change="aplicar" />
    <SelectBusqueda v-model="filtros.centro" :opciones="opciones.centros || []" vacio="Centro: todos" etiqueta="Centro" @change="aplicar" />
    <select v-model="filtros.riesgo" aria-label="Riesgo" @change="aplicar">
      <option value="">Llegada a tienda: todas</option>
      <option v-for="(r, k) in RIESGOS" :key="k" :value="k">{{ r }}</option>
    </select>
    <label v-if="vista === 'ordenes'" class="check"><input type="checkbox" :checked="!!filtros.xf_vencida" @change="filtros.xf_vencida = $event.target.checked ? '1' : ''; aplicar()" /> XF vencida sin facturar</label>
    <label v-for="[k, t] in [['eta', 'ETA'], ['fecha_xf', 'XF'], ['fecha_tienda', 'En tienda']]" :key="k" class="rango-fechas">
      <span>{{ t }}</span>
      <input v-model="filtros[`${k}_desde`]" type="date" :aria-label="`${t} desde`" @change="aplicar" />
      <span>a</span>
      <input v-model="filtros[`${k}_hasta`]" type="date" :aria-label="`${t} hasta`" @change="aplicar" />
    </label>
  </div>
  <div v-if="activos.length" class="chips">
    <span v-for="a in activos" :key="a.k" class="chip">{{ a.texto }}<button type="button" :aria-label="`Quitar ${a.texto}`" @click="quitar(a.k)"><Icono nombre="cerrar" :tam="13" /></button></span>
    <button type="button" class="btn btn-fantasma btn-chico" @click="limpiar">Limpiar filtros</button>
  </div>

  <TableroOrdenes v-if="vista === 'ordenes'" :filtros="params" @opciones="(o) => (opciones = o)" @filtrar="aplicarDesde" />
  <TableroEmbarques v-else :filtros="params" @opciones="(o) => (opciones = o)" @filtrar="aplicarDesde" />
  </template>
</template>
