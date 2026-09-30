<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import Seleccion from '../components/Seleccion.vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api'
import Avance from '../components/Avance.vue'
import BarraSeleccion from '../components/BarraSeleccion.vue'
import Modal from '../components/Modal.vue'
import EstadoBadge from '../components/EstadoBadge.vue'
import Icono from '../components/Icono.vue'
import ExplosionPrepack from '../components/ExplosionPrepack.vue'
import Paginacion from '../components/Paginacion.vue'
import SelectBusqueda from '../components/SelectBusqueda.vue'
import ThOrden from '../components/ThOrden.vue'
import { siguienteOrden } from '../composables/useTabla'
import { agregarPosiciones, carrito, quitarOC, quitarPosicion, vaciarCarrito } from '../stores/carrito'
import { esInterno, nombreProveedor, puede, sesion } from '../stores/sesion'
import { avisar, errorApi } from '../stores/ui'
import { COMERCIAL, LIBERACION, cantTxt, unidadTxt, diasTxt, fmtFecha, fmtMoneda, fmtNum, porUnidadTxt, useSeleccion } from '../utils'

const route = useRoute()
const router = useRouter()

// Filtros que se eligen de listas armadas con lo que realmente hay en las OCs
const EXTRA = { sociedad: 'Company', centro: 'Plant', almacen: 'Warehouse', marca: 'Brand', comercial: 'Commercial rel.', liberacion: 'Logistics rel.', destino: 'Destination plant', puerto: 'Port' }
const filtros = reactive({
  q: route.query.q || '',
  solo_disponible: route.query.solo_disponible !== '0',
  orden: '',
  page: 1,
  size: 15,
  ...Object.fromEntries(Object.keys(EXTRA).map((k) => [k, route.query[k] || ''])),
})
const opcionesFiltro = ref({ sociedades: [], centros: [], almacenes: [], marcas: [], destinos: [], puertos: [], liberaciones: [] })
const activos = computed(() => Object.keys(EXTRA).filter((k) => filtros[k]).map((k) => {
  let v = filtros[k]
  if (k === 'destino') v = opcionesFiltro.value.destinos.find((d) => d.codigo === v)?.nombre || v
  if (k === 'puerto') v = opcionesFiltro.value.puertos.find((d) => d.codigo === v)?.nombre || v
  if (k === 'liberacion') v = LIBERACION[v]?.[0] || v
  if (k === 'comercial') v = COMERCIAL[v]?.[2] || v
  return { k, texto: `${EXTRA[k]}: ${v}` }
}))
const datos = ref({ items: [], total: 0 })
const cargando = ref(false)
const abiertas = reactive(new Set())
const detalles = reactive({})
const selOC = useSeleccion()
const selPos = useSeleccion()
const explosion = ref(null) // { sku, cajas } del prepack que se está viendo

const panel = ref(!!route.query.seleccion || !!route.query.factura)
const destino = ref(route.query.factura ? Number(route.query.factura) : '')
const borradores = ref([])
const nueva = reactive({ numero: '', fecha: '' })
const enviando = ref(false)

const tieneSaldo = (oc) => oc.liberada && Object.values(oc.por_unidad).some((u) => u.disponible > 0)
const conSaldo = computed(() => datos.value.items.filter(tieneSaldo).map((o) => o.id))
const columnas = computed(() => (sesion.proveedorId ? 11 : 12))

async function cargar() {
  cargando.value = true
  try {
    datos.value = await api.get('/ordenes', {
      proveedor_id: sesion.proveedorId,
      q: filtros.q,
      solo_disponible: filtros.solo_disponible,
      orden: filtros.orden || undefined,
      ...Object.fromEntries(Object.keys(EXTRA).filter((k) => filtros[k]).map((k) => [k, filtros[k]])),
      page: filtros.page,
      size: filtros.size,
    })
    selOC.podar(datos.value.items.map((o) => o.id))
  } catch (e) {
    errorApi(e)
  } finally {
    cargando.value = false
  }
}

async function cargarFiltros() {
  try {
    opcionesFiltro.value = await api.get('/ordenes/filtros', { proveedor_id: sesion.proveedorId })
  } catch (e) {
    errorApi(e)
  }
}

function filtrar() {
  filtros.page = 1
  const query = { ...route.query }
  for (const k of Object.keys(EXTRA)) {
    if (filtros[k]) query[k] = filtros[k]
    else delete query[k]
  }
  router.replace({ query })
  cargar()
}

function quitarFiltro(k) {
  filtros[k] = ''
  filtrar()
}

function limpiarFiltros() {
  for (const k of Object.keys(EXTRA)) filtros[k] = ''
  filtrar()
}

function ordenar(campo) {
  filtros.orden = siguienteOrden(filtros.orden, campo)
  filtros.page = 1
  cargar()
}

const xfCambio = (oc) => oc.fecha_xf_original && oc.fecha_xf && oc.fecha_xf_original !== oc.fecha_xf
const tonoTienda = (d) => (d === null || d === undefined ? '' : d < 0 ? 'error' : d < 30 ? 'aviso' : '')

let espera
function buscar() {
  clearTimeout(espera)
  espera = setTimeout(() => {
    filtros.page = 1
    cargar()
  }, 300)
}

const enCarrito = (id) => carrito.items.find((i) => i.posicion_id === id)

async function cargarDetalle(ocId, forzar = false) {
  if (!detalles[ocId] || forzar) {
    const d = await api.get(`/ordenes/${ocId}/posiciones`)
    for (const p of d.posiciones) {
      p.a_facturar = enCarrito(p.id)?.cantidad ?? (p.estado !== 'NO_DISPONIBLE' ? p.disponible : 0)
    }
    detalles[ocId] = d
  }
  return detalles[ocId]
}

async function alternar(oc) {
  if (abiertas.has(oc.id)) {
    abiertas.delete(oc.id)
    return
  }
  try {
    await cargarDetalle(oc.id)
    abiertas.add(oc.id)
  } catch (e) {
    errorApi(e)
  }
}

const seleccionables = (ocId) =>
  (detalles[ocId]?.posiciones || []).filter((p) => p.disponible > 0 && p.estado !== 'NO_DISPONIBLE').map((p) => p.id)
const seleccionadas = (ocId) => seleccionables(ocId).filter((id) => selPos.tiene(id)).length

function informar(r, texto, abrir = false) {
  if (r.error) {
    avisar(r.error, 'error')
    return
  }
  avisar(`${texto}: ${r.agregadas} lines in the selection` + (r.omitidas ? `; ${r.omitidas} without balance were skipped.` : '.'))
  if (abrir) panel.value = true
}

async function agregarOCs(ids, abrir = false) {
  const total = { agregadas: 0, omitidas: 0 }
  for (const id of ids) {
    try {
      const d = await cargarDetalle(id, true)
      const r = agregarPosiciones(d.oc, d.posiciones.map((p) => ({ ...p, a_facturar: p.disponible })))
      if (r.error) return informar(r)
      total.agregadas += r.agregadas
      total.omitidas += r.omitidas
    } catch (e) {
      return errorApi(e)
    }
  }
  selOC.limpiar()
  informar(total, ids.length > 1 ? `${ids.length} full POs` : 'Full PO', abrir)
}

function agregarSeleccionadas(ocId) {
  const d = detalles[ocId]
  const posiciones = d.posiciones.filter((p) => selPos.tiene(p.id))
  const invalidas = posiciones.filter((p) => cantidadInvalida(p.a_facturar, p.disponible, p.inner_pack))
  if (invalidas.length) {
    avisar(`Check “To invoice” on ${invalidas.length} lines: between 1 and the available quantity, in whole inner packs.`, 'error')
    return
  }
  const r = agregarPosiciones(d.oc, posiciones)
  posiciones.forEach((p) => selPos.ids.delete(p.id))
  informar(r, `PO ${d.oc.numero}`)
}

// With an inner pack, everything moves in whole inner packs
const cantidadInvalida = (c, disponible, inner) => !(c >= 1) || c > disponible || (inner && c % inner !== 0)

// ---- Packing of a PO line (purchase condition) ------------------------------
// Casepack: exact quantity per master carton. Inner pack: units per inner pack
// (all equal). With both, the casepack is a multiple of the inner pack.
const empaque = ref(null)
function editarEmpaque(oc, p) {
  empaque.value = { oc, p, casepack: p.casepack || '', inner_pack: p.inner_pack || '', error: '' }
}
async function guardarEmpaque() {
  const e = empaque.value
  try {
    await api.put(`/ordenes/${e.oc.id}/posiciones/${e.p.id}/empaque`, {
      casepack: Number(e.casepack) || null, inner_pack: Number(e.inner_pack) || null,
    })
    avisar(`PO ${e.oc.numero} line ${e.p.posicion}: packing updated.`)
    empaque.value = null
    await cargarDetalle(e.oc.id, true)
  } catch (err) {
    e.error = [err.message, ...(err.detalle || []).map((d) => d.mensaje)].join(' ')
  }
}

// ---- Selección para facturar ---------------------------------------------
const grupos = computed(() => {
  const mapa = new Map()
  for (const i of carrito.items) {
    if (!mapa.has(i.oc_id)) mapa.set(i.oc_id, { oc_id: i.oc_id, oc_numero: i.oc_numero, centro: i.centro, items: [] })
    mapa.get(i.oc_id).items.push(i)
  }
  return [...mapa.values()]
})

const totales = computed(() => {
  const porUnidad = {}
  let importe = 0
  for (const i of carrito.items) {
    const c = Number(i.cantidad || 0)
    porUnidad[i.unidad] = (porUnidad[i.unidad] || 0) + c
    importe += c * i.precio
  }
  return { porUnidad, importe }
})

const mezclas = computed(() => {
  const avisos = []
  const centros = new Set(carrito.items.map((i) => i.centro))
  const monedas = new Set(carrito.items.map((i) => i.moneda))
  if (centros.size > 1) avisos.push(`The selection mixes plants (${[...centros].join(', ')}); they must go on separate invoices.`)
  if (monedas.size > 1) avisos.push(`The selection mixes currencies (${[...monedas].join(', ')}); they must go on separate invoices.`)
  return avisos
})

const invalida = computed(() => carrito.items.some((i) => cantidadInvalida(i.cantidad, i.disponible, i.inner_pack)))

async function cargarBorradores() {
  if (!carrito.proveedorId) {
    borradores.value = []
    return
  }
  try {
    const r = await api.get('/facturas', { proveedor_id: carrito.proveedorId, vista: 'editables', size: 100 })
    borradores.value = r.items
    if (destino.value && !r.items.some((b) => b.id === destino.value)) destino.value = ''
  } catch (e) {
    errorApi(e)
  }
}

async function facturar() {
  const lineas = carrito.items.map((i) => ({ posicion_id: i.posicion_id, cantidad: Number(i.cantidad) }))
  enviando.value = true
  try {
    let id
    if (destino.value) {
      const f = await api.get(`/facturas/${destino.value}`)
      const r = await api.post(`/facturas/${destino.value}/lineas`, { version: f.version, lineas })
      id = destino.value
      avisar(`${f.nombre}: ${r.agregadas} new lines and ${r.aumentadas} with more quantity.`, 'ok',
        r.advertencias?.length ? r.advertencias : null)
    } else {
      const r = await api.post('/facturas', {
        proveedor_id: carrito.proveedorId,
        lineas,
        numero: nueva.numero || null,
        fecha: nueva.fecha || null,
      })
      id = r.id
      avisar(`Invoice ${r.nombre} created as a draft.`, 'ok', r.advertencias?.length ? r.advertencias : null)
    }
    vaciarCarrito()
    router.push(`/facturas/${id}?tab=lineas`)
  } catch (e) {
    errorApi(e)
  } finally {
    enviando.value = false
  }
}

onMounted(() => {
  cargar()
  cargarFiltros()
})
watch(() => sesion.proveedorId, () => {
  cargarFiltros()
  filtros.page = 1
  abiertas.clear()
  Object.keys(detalles).forEach((k) => delete detalles[k])
  cargar()
})
watch(() => route.query.seleccion, (v) => v && (panel.value = true))
watch([panel, () => carrito.proveedorId], ([abierto]) => abierto && cargarBorradores(), { immediate: true })
</script>

<template>
  <div class="pagina-cabeza">
    <div>
      <div class="eyebrow">Step 1 of 3 · Invoice</div>
      <h1>Purchase orders</h1>
      <p>Choose what to invoice: full POs or only some lines and quantities. You can combine several POs of the same supplier in one invoice.</p>
    </div>
    <div class="acciones">
      <router-link v-if="esInterno()" to="/importar" class="btn"><Icono nombre="importar" />Import POs</router-link>
      <button class="btn btn-primario" type="button" :disabled="!carrito.items.length" @click="panel = true">
        <Icono nombre="carrito" />Review selection ({{ carrito.items.length }})
      </button>
    </div>
  </div>

  <div class="filtros">
    <label class="buscador">
      <Icono nombre="buscar" :tam="16" />
      <input v-model="filtros.q" type="search" placeholder="Search PO, style, color, SKU or UPC" aria-label="Search" @input="buscar" />
    </label>
    <SelectBusqueda v-model="filtros.sociedad" :opciones="opcionesFiltro.sociedades" vacio="Company: all" etiqueta="Company" @change="filtrar" />
    <SelectBusqueda v-model="filtros.centro" :opciones="opcionesFiltro.centros" vacio="Plant: all" etiqueta="Plant" @change="filtrar" />
    <SelectBusqueda v-model="filtros.almacen" :opciones="opcionesFiltro.almacenes" vacio="Warehouse: all" etiqueta="Warehouse" @change="filtrar" />
    <SelectBusqueda v-model="filtros.marca" :opciones="opcionesFiltro.marcas" vacio="Brand: all" etiqueta="Brand" @change="filtrar" />
    <SelectBusqueda v-model="filtros.destino" :opciones="opcionesFiltro.destinos.map((d) => ({ valor: d.codigo, texto: `${d.codigo} · ${d.nombre}` }))"
                    vacio="Destination plant: all" etiqueta="Destination plant" @change="filtrar" />
    <SelectBusqueda v-model="filtros.puerto" :opciones="opcionesFiltro.puertos.map((d) => ({ valor: d.codigo, texto: `${d.codigo} · ${d.nombre}` }))"
                    vacio="Port: all" etiqueta="Port of loading" @change="filtrar" />
    <Seleccion v-model="filtros.comercial" aria-label="Commercial release" @change="filtrar">
      <option value="">Commercial rel.: all</option><option value="C">C · Released</option><option value="P">P · Pending</option>
    </Seleccion>
    <Seleccion v-model="filtros.liberacion" aria-label="Logistics release" @change="filtrar"><option value="">Logistics rel.: all</option><option v-for="l in opcionesFiltro.liberaciones" :key="l.codigo" :value="l.codigo">{{ l.codigo }} · {{ l.nombre }}</option></Seleccion>
    <div class="segmentos" role="group" aria-label="Show">
      <button class="segmento" type="button" :aria-pressed="filtros.solo_disponible" @click="filtros.solo_disponible = true; filtros.page = 1; cargar()">With balance to invoice</button>
      <button class="segmento" type="button" :aria-pressed="!filtros.solo_disponible" @click="filtros.solo_disponible = false; filtros.page = 1; cargar()">All</button>
    </div>
  </div>
  <div v-if="activos.length" class="chips">
    <span v-for="a in activos" :key="a.k" class="chip">{{ a.texto }}<button type="button" :aria-label="`Remove ${a.texto}`" @click="quitarFiltro(a.k)"><Icono nombre="cerrar" :tam="13" /></button></span>
    <button type="button" class="btn btn-fantasma btn-chico" @click="limpiarFiltros">Clear filters</button>
  </div>

  <div class="tabla-marco tabla-fija">
    <table class="tabla">
      <thead>
        <tr>
          <th class="chk">
            <input type="checkbox" aria-label="Select all POs with balance" :checked="selOC.todos(conSaldo)" @change="selOC.alternarTodos(conSaldo)" />
          </th>
          <th><span class="oculto-visual">See lines</span></th>
          <ThOrden campo="numero" :orden="filtros.orden" @ordenar="ordenar">Purchase order</ThOrden>
          <ThOrden v-if="!sesion.proveedorId" campo="proveedor" :orden="filtros.orden" @ordenar="ordenar">Supplier</ThOrden>
          <th>Company · plant · warehouse</th>
          <th>Destination plant / port</th>
          <ThOrden campo="fecha_xf" :orden="filtros.orden" @ordenar="ordenar">XF date</ThOrden>
          <ThOrden campo="fecha_tienda" :orden="filtros.orden" @ordenar="ordenar">In store</ThOrden>
          <th>To invoice</th>
          <ThOrden campo="importe" :orden="filtros.orden" num @ordenar="ordenar">PO value</ThOrden>
          <ThOrden campo="avance" :orden="filtros.orden" @ordenar="ordenar">Invoiced</ThOrden>
          <th></th>
        </tr>
      </thead>
      <tbody>
        <template v-for="oc in datos.items" :key="oc.id">
          <tr :class="{ seleccionada: selOC.tiene(oc.id) }">
            <td class="chk">
              <input type="checkbox" :aria-label="`Select PO ${oc.numero}`" :disabled="!tieneSaldo(oc)" :checked="selOC.tiene(oc.id)" @change="selOC.alternar(oc.id)" />
            </td>
            <td>
              <button class="btn-icono" type="button" :aria-expanded="abiertas.has(oc.id)" :aria-label="`See the lines of PO ${oc.numero}`" @click="alternar(oc)">
                <Icono :nombre="abiertas.has(oc.id) ? 'abajo' : 'derecha'" :tam="16" />
              </button>
            </td>
            <td>
              <strong class="codigo">{{ oc.numero }}</strong>
              <span class="sub">{{ fmtFecha(oc.fecha) }} · {{ oc.posiciones }} lines<template v-if="oc.marcas.length"> · {{ oc.marcas.join(', ') }}</template></span>
              <span class="insignias">
                <span class="etiqueta" :class="COMERCIAL[oc.liberacion_comercial]?.[1]" :title="COMERCIAL[oc.liberacion_comercial]?.[2]">{{ COMERCIAL[oc.liberacion_comercial]?.[0] }}</span>
                <span v-if="LIBERACION[oc.liberacion_logistica]" class="etiqueta" :class="LIBERACION[oc.liberacion_logistica][1]" :title="LIBERACION[oc.liberacion_logistica][2]">{{ LIBERACION[oc.liberacion_logistica][0] }}</span>
              </span>
            </td>
            <td v-if="!sesion.proveedorId">{{ oc.proveedor }}</td>
            <td><span class="codigo">{{ oc.sociedad }} · {{ oc.centro || '—' }}</span><span class="sub" :title="oc.almacenes.length > 1 ? 'Lines go to different warehouses' : ''">{{ oc.almacenes.join(' · ') || 'No warehouse' }}</span></td>
            <td>
              <span class="codigo" :title="oc.destino_nombre || ''">{{ oc.centro_destino || '—' }}<template v-if="oc.pais_destino"> · {{ oc.pais_destino }}</template></span>
              <span class="sub">{{ oc.puerto_despacho || 'No port' }}<template v-if="oc.pais_origen"> · origin {{ oc.pais_origen }}</template></span>
            </td>
            <td>
              {{ fmtFecha(oc.fecha_xf) }}
              <span v-if="xfCambio(oc)" class="sub" :title="`Original XF ${fmtFecha(oc.fecha_xf_original)}`">was <s>{{ fmtFecha(oc.fecha_xf_original) }}</s></span>
            </td>
            <td>
              {{ fmtFecha(oc.fecha_tienda) }}
              <span v-if="oc.dias_tienda !== null" class="sub" :style="tonoTienda(oc.dias_tienda) ? { color: `var(--${tonoTienda(oc.dias_tienda)})` } : null">{{ diasTxt(oc.dias_tienda) }}</span>
            </td>
            <td class="ajustar" style="min-width: 100px">
              <span class="fuerte">{{ porUnidadTxt(oc.por_unidad, 'disponible') }}</span>
              <span class="sub">of {{ porUnidadTxt(oc.por_unidad, 'cantidad') }}</span>
            </td>
            <td class="num">{{ fmtMoneda(oc.importe, oc.moneda) }}</td>
            <td style="min-width: 110px"><Avance :porcentaje="oc.avance" /></td>
            <td class="num">
              <div class="acciones-apiladas">
                <button class="btn btn-chico" type="button" :disabled="!tieneSaldo(oc)" title="Add the whole balance to the selection" @click="agregarOCs([oc.id])"><Icono nombre="mas" :tam="14" />Add</button>
                <button class="btn btn-chico btn-primario" type="button" :disabled="!tieneSaldo(oc)" title="Add the whole balance and review the invoice" @click="agregarOCs([oc.id], true)">Invoice</button>
              </div>
            </td>
          </tr>
          <tr v-if="abiertas.has(oc.id) && detalles[oc.id]" class="fila-hija">
            <td :colspan="columnas">
              <div class="subtabla">
                <div class="tabla-marco">
                  <table class="tabla">
                    <thead>
                      <!-- Item data comes from the item master; PO line data comes with the purchase order -->
                      <tr class="grupo-columnas">
                        <th colspan="2"></th>
                        <th colspan="4" title="Taken from the item master and its technical sheet (the same on every PO)">Item · master data</th>
                        <th colspan="7" title="Comes with this purchase order line">PO line · purchase data</th>
                        <th></th>
                      </tr>
                      <tr>
                        <th class="chk">
                          <input type="checkbox" aria-label="Select the lines with balance" :checked="selPos.todos(seleccionables(oc.id))" @change="selPos.alternarTodos(seleccionables(oc.id))" />
                        </th>
                        <th>Line</th>
                        <th>Item</th>
                        <th>Size</th>
                        <th>UoM</th>
                        <th title="HS code for the destination country, from the approved technical sheet">HS code</th>
                        <th>Warehouse</th>
                        <th>Packing</th>
                        <th class="num">Quantity</th>
                        <th class="num">Available</th>
                        <th class="num">To invoice</th>
                        <th class="num">Price</th>
                        <th class="num">Total</th>
                        <th>Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="p in detalles[oc.id].posiciones" :key="p.id" :class="{ seleccionada: selPos.tiene(p.id) }">
                        <td class="chk">
                          <input type="checkbox" :aria-label="`Select line ${p.posicion}`" :disabled="!p.disponible || p.estado === 'NO_DISPONIBLE'" :checked="selPos.tiene(p.id)" @change="selPos.alternar(p.id)" />
                        </td>
                        <td class="codigo">{{ p.posicion }}</td>
                        <td>
                          <span v-if="p.marca" class="fuerte">{{ p.marca }}</span> {{ p.estilo }} · {{ p.color }}
                          <span class="sub codigo">{{ p.codigo_sap }}<template v-if="p.grupo"> · {{ p.grupo }}</template></span>
                        </td>
                        <td><strong>{{ p.talla }}</strong></td>
                        <td><span class="etiqueta" style="margin-left: 0" :title="unidadTxt(p.unidad, 2)">{{ p.unidad }}</span></td>
                        <td>
                          <router-link v-if="p.clasificacion?.producto_id" :to="`/productos/${p.clasificacion.producto_id}`" class="enlace"
                                       :title="p.partida_arancelaria ? 'Approved HS code for the destination country' : 'Open the technical sheet'">
                            <span v-if="p.partida_arancelaria" class="codigo-sac">{{ p.partida_arancelaria }}</span>
                            <span v-else class="etiqueta aviso" style="margin-left: 0">{{ p.clasificacion.estado === 'observado' ? 'Sheet returned' : 'Not classified' }}</span>
                          </router-link>
                          <span v-else class="apagado">—</span>
                        </td>
                        <td class="codigo">{{ p.almacen || '—' }}</td>
                        <td>
                          <span class="fila-flex" style="gap: 4px; flex-wrap: wrap">
                            <button v-if="p.tipo_empaque === 'PREPACK'" type="button" class="etiqueta acento btn-explosion" style="margin-left: 0"
                                    title="See the prepack breakdown" @click="explosion = { sku: p.codigo_sap, cajas: p.cantidad }">
                              Prepack {{ p.prepack }} · {{ p.unidades_por_caja }} per carton <Icono nombre="lupa" :tam="12" />
                            </button>
                            <template v-else>
                              <span v-if="p.casepack" class="etiqueta info" style="margin-left: 0" title="Exact quantity per master carton">Casepack {{ p.casepack }}</span>
                              <span v-if="p.inner_pack" class="etiqueta acento" style="margin-left: 0"
                                    :title="`Inner packs of ${p.inner_pack}${p.casepack ? `; ${p.casepack / p.inner_pack} inner packs per carton` : ''}`">Inner {{ p.inner_pack }}</span>
                              <span v-if="!p.casepack && !p.inner_pack" class="ayuda">Free</span>
                            </template>
                            <button v-if="puede('oc.empaque') && p.tipo_empaque !== 'PREPACK' && !p.facturado" type="button" class="btn-icono"
                                    :aria-label="`Edit the packing of line ${p.posicion}`" title="Edit casepack and inner pack" @click="editarEmpaque(oc, p)">
                              <Icono nombre="editar" :tam="14" />
                            </button>
                          </span>
                        </td>
                        <td class="num">{{ cantTxt(p.cantidad, p.unidad) }}</td>
                        <td class="num"><strong>{{ fmtNum(p.disponible) }}</strong></td>
                        <td class="num">
                          <input
                            v-model.number="p.a_facturar"
                            class="celda num"
                            type="number"
                            :min="p.inner_pack || 1"
                            :step="p.inner_pack || 1"
                            :max="p.disponible"
                            style="width: 84px; border-color: var(--linea)"
                            :aria-label="`To invoice on line ${p.posicion}`"
                            :disabled="!p.disponible || p.estado === 'NO_DISPONIBLE'"
                            @focus="selPos.ids.add(p.id)"
                          />
                        </td>
                        <td class="num">{{ fmtNum(p.precio, 2) }}</td>
                        <td class="num">{{ fmtNum(p.total, 2) }}</td>
                        <td>
                          <EstadoBadge :estado="p.estado" />
                          <span v-if="enCarrito(p.id)" class="etiqueta ok">In selection</span>
                          <div v-if="p.motivo || p.facturas.length" class="ayuda">
                            {{ p.motivo }}
                            <template v-for="fa in p.facturas" :key="fa.id">
                              <router-link :to="`/facturas/${fa.id}`">{{ fa.nombre }}</router-link> ({{ fmtNum(fa.cantidad) }})
                            </template>
                          </div>
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
                <div class="fila-flex mt">
                  <button class="btn btn-primario btn-chico" type="button" :disabled="!seleccionadas(oc.id)" @click="agregarSeleccionadas(oc.id)">
                    <Icono nombre="mas" :tam="14" />Add {{ seleccionadas(oc.id) || '' }} selected
                  </button>
                  <span class="ayuda">Change “To invoice” to take only part; the rest stays available on the PO. With an inner pack it goes in whole inner packs.</span>
                </div>
              </div>
            </td>
          </tr>
        </template>
        <tr v-if="!datos.items.length && !cargando">
          <td :colspan="columnas" class="vacio">{{ filtros.solo_disponible ? 'No POs with balance to invoice.' : 'No POs match these filters.' }}</td>
        </tr>
      </tbody>
    </table>
  </div>
  <Paginacion :page="filtros.page" :size="filtros.size" :total="datos.total" @cambiar="(p) => { filtros.page = p; cargar() }" @tamano="(t) => (filtros.size = t)" />

  <BarraSeleccion :cantidad="selOC.ids.size" singular="PO selected" plural="POs selected" @limpiar="selOC.limpiar()">
    <button class="btn" type="button" @click="agregarOCs(selOC.lista())">Add to the selection</button>
    <button class="btn btn-primario" type="button" @click="agregarOCs(selOC.lista(), true)">Invoice together</button>
  </BarraSeleccion>

  <div v-if="carrito.items.length && !panel && !selOC.ids.size" class="barra-seleccion" role="region" aria-label="Selection to invoice">
    <Icono nombre="carrito" />
    <strong>{{ carrito.items.length }} lines ready to invoice</strong>
    <span class="resumen">{{ porUnidadTxt(totales.porUnidad, null) }} · {{ fmtMoneda(totales.importe, carrito.items[0].moneda) }}</span>
    <div class="acciones">
      <button class="btn btn-primario" type="button" @click="panel = true">Review and create invoice<Icono nombre="flecha" :tam="16" /></button>
    </div>
  </div>

  <div v-if="panel" class="cajon-fondo" @click="panel = false"></div>
  <aside v-if="panel" class="cajon" aria-label="Selection to invoice">
    <div class="cajon-cabeza">
      <div>
        <div class="eyebrow">Step 2 of 3</div>
        <h2>Review and create the invoice</h2>
        <p v-if="carrito.items.length">Supplier {{ nombreProveedor(carrito.proveedorId) }}</p>
      </div>
      <button class="btn-icono" type="button" aria-label="Close" @click="panel = false"><Icono nombre="cerrar" :tam="20" /></button>
    </div>
    <div class="cajon-cuerpo">
      <div v-if="!carrito.items.length" class="vacio">
        <Icono nombre="carrito" :tam="28" />
        <p>No lines yet. Use “Add” on a PO or open it and choose lines.</p>
      </div>
      <template v-else>
        <div v-for="g in grupos" :key="g.oc_id" class="grupo-oc">
          <div class="grupo-oc-cabeza">
            <span>PO {{ g.oc_numero }} <span class="etiqueta">{{ g.centro }}</span></span>
            <button class="btn-texto" type="button" @click="quitarOC(g.oc_id)">Remove PO</button>
          </div>
          <div v-for="i in g.items" :key="i.posicion_id" class="item-carrito">
            <div>
              <span class="codigo">{{ i.posicion }}</span> {{ i.estilo }} {{ i.color }} <b>{{ i.talla }}</b>
              <div class="ayuda">
                {{ cantTxt(i.disponible, i.unidad) }} available<template v-if="i.inner_pack"> · inner packs of {{ i.inner_pack }}</template><template v-if="i.aviso">. {{ i.aviso }}</template>
              </div>
            </div>
            <input v-model.number="i.cantidad" type="number" :min="i.inner_pack || 1" :step="i.inner_pack || 1" :max="i.disponible" :aria-label="`Quantity to invoice on ${i.posicion}`" />
            <button class="btn-icono" type="button" :aria-label="`Remove line ${i.posicion}`" @click="quitarPosicion(i.posicion_id)"><Icono nombre="cerrar" :tam="16" /></button>
          </div>
        </div>
      </template>
    </div>
    <div v-if="carrito.items.length" class="cajon-pie">
      <div class="total-carrito">
        <span>{{ porUnidadTxt(totales.porUnidad, null) }}</span>
        <strong>{{ fmtMoneda(totales.importe, carrito.items[0].moneda) }}</strong>
      </div>
      <p v-for="a in mezclas" :key="a" class="nota aviso"><Icono nombre="alerta" />{{ a }}</p>
      <p v-if="invalida" class="nota error"><Icono nombre="alerta" />Some quantities are out of range (between 1 and the available quantity, in whole inner packs).</p>
      <label class="campo">
        <span>Where do you invoice it?</span>
        <Seleccion v-model="destino">
          <option value="">On a new invoice</option>
          <option v-for="b in borradores" :key="b.id" :value="b.id">Add to {{ b.nombre }} ({{ b.estado === 'BORRADOR' ? 'draft' : 'in correction' }})</option>
        </Seleccion>
      </label>
      <div v-if="!destino" class="rejilla-campos">
        <label class="campo"><span class="req">Invoice number</span><input v-model="nueva.numero" placeholder="You can add it later" /></label>
        <label class="campo"><span class="req">Date</span><input v-model="nueva.fecha" type="date" /></label>
      </div>
      <p v-if="!destino" class="leyenda-req">Required to finalize the invoice; you can complete them later.</p>
      <div class="fila-flex">
        <button class="btn-texto" type="button" @click="vaciarCarrito()">Clear selection</button>
        <button class="btn btn-primario separar" type="button" :disabled="enviando || invalida" @click="facturar">
          {{ destino ? 'Add to the invoice' : 'Create invoice' }}<Icono nombre="flecha" :tam="16" />
        </button>
      </div>
    </div>
  </aside>
  <ExplosionPrepack v-if="explosion" :sku="explosion.sku" :cajas="explosion.cajas" @cerrar="explosion = null" />
  <Modal v-if="empaque" :titulo="`Packing of PO ${empaque.oc.numero} line ${empaque.p.posicion}`" ancho="520px" @cerrar="empaque = null">
    <p class="ayuda" style="margin-top: 0">{{ empaque.p.estilo }} · {{ empaque.p.color }} · size {{ empaque.p.talla }} · {{ cantTxt(empaque.p.cantidad, empaque.p.unidad) }}</p>
    <form id="form-empaque" class="rejilla-campos" @submit.prevent="guardarEmpaque">
      <label class="campo"><span>Casepack (per master carton)</span>
        <input v-model="empaque.casepack" type="number" min="1" placeholder="Free" />
        <small class="ayuda">Exact quantity per carton; only the last carton may be incomplete.</small>
      </label>
      <label class="campo"><span>Inner pack (units per pack)</span>
        <input v-model="empaque.inner_pack" type="number" min="1" placeholder="None" />
        <small class="ayuda">All inner packs carry the same quantity and their own label.</small>
      </label>
    </form>
    <p v-if="empaque.casepack && empaque.inner_pack && empaque.casepack % empaque.inner_pack === 0" class="nota info">
      <Icono nombre="info" />Each carton carries {{ empaque.casepack / empaque.inner_pack }} inner packs of {{ empaque.inner_pack }}.
    </p>
    <p v-else-if="!empaque.casepack && empaque.inner_pack" class="nota info">
      <Icono nombre="info" />Without a casepack, each carton carries the inner packs you define (always multiples of {{ empaque.inner_pack }}).
    </p>
    <p v-if="empaque.error" class="nota error" role="alert"><Icono nombre="alerta" />{{ empaque.error }}</p>
    <p class="ayuda">It can only change while nothing on this line is invoiced.</p>
    <template #pie>
      <button class="btn" @click="empaque = null">Cancel</button>
      <button class="btn btn-primario" type="submit" form="form-empaque">Save packing</button>
    </template>
  </Modal>
</template>
