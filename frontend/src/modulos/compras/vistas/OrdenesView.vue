<script setup>
import { t, tx } from '@/i18n/index.js'
import FechaTienda from '@/componentes/FechaTienda.vue'
import { computed, onMounted, reactive, ref, watch } from 'vue'
import Seleccion from '@/componentes/Seleccion.vue'
import { useRoute, useRouter } from 'vue-router'
import TablaDatos from '@/componentes/TablaDatos.vue'
import { api } from '@/nucleo/api'
import Avance from '@/componentes/Avance.vue'
import BarraSeleccion from '@/componentes/BarraSeleccion.vue'
import Modal from '@/componentes/Modal.vue'
import EstadoBadge from '@/componentes/EstadoBadge.vue'
import Icono from '@/componentes/Icono.vue'
import ExplosionPrepack from '@/componentes/ExplosionPrepack.vue'
import SelectBusqueda from '@/componentes/SelectBusqueda.vue'
import { agregarPosiciones, carrito, quitarOC, quitarPosicion, vaciarCarrito } from '@/stores/carrito'
import { camposPropios, nombreProveedor, puede, sesion, valorPropio, ve } from '@/stores/sesion'
import { avisar, errorApi } from '@/stores/ui'
import { cantTxt, unidadTxt, diasTxt, fmtFecha, fmtMoneda, fmtNum, porUnidadTxt, useSeleccion } from '@/nucleo/utils'
import { pasoCantidad } from '@/nucleo/unidades.js'
import { estadosOC, estado as leerEstado } from '@/nucleo/estados.js'

const ESTADOS_OC = estadosOC()

const route = useRoute()
const router = useRouter()

// Filtros que se eligen de listas armadas con lo que realmente hay en las OCs
const EXTRA = { estado: t('Status'), sociedad: t('Company'), centro: t('Plant'), almacen: t('Warehouse'), marca: t('Brand'), comercial: t('Commercial rel.'), liberacion: t('Logistics rel.'), liberada: t('Release'), destino: t('Destination plant'), puerto: t('Port') }
const filtros = reactive({
  q: route.query.q || '',
  solo_disponible: route.query.solo_disponible !== '0',
  ...Object.fromEntries(Object.keys(EXTRA).map((k) => [k, route.query[k] || ''])),
})
const opcionesFiltro = ref({ sociedades: [], centros: [], almacenes: [], marcas: [], destinos: [], puertos: [], liberaciones: [], comerciales: [] })
const activos = computed(() => Object.keys(EXTRA).filter((k) => filtros[k]).map((k) => {
  let v = filtros[k]
  if (k === 'destino') v = opcionesFiltro.value.destinos.find((d) => d.codigo === v)?.nombre || v
  if (k === 'puerto') v = opcionesFiltro.value.puertos.find((d) => d.codigo === v)?.nombre || v
  // Nombres de los estados de liberación que definió la empresa (Datos maestros)
  if (k === 'liberacion') v = opcionesFiltro.value.liberaciones.find((x) => x.codigo === v)?.nombre || v
  if (k === 'comercial') v = opcionesFiltro.value.comerciales.find((x) => x.codigo === v)?.nombre || v
  if (k === 'liberada') v = v === '0' ? t('Not released') : t('Released')
  if (k === 'estado') v = leerEstado(v, 'oc')[0]
  return { k, texto: `${EXTRA[k]}: ${v}` }
}))
const datos = ref({ items: [], total: 0 })
const cargando = ref(false)
const detalles = reactive({})
const tablaOC = ref(null)
const seleccionOC = ref([])
const selPos = useSeleccion()
const explosion = ref(null) // { sku, cajas } del prepack que se está viendo

const panel = ref(!!route.query.seleccion || !!route.query.factura)
const destino = ref(route.query.factura ? Number(route.query.factura) : '')
const borradores = ref([])
const nueva = reactive({ numero: '', fecha: '' })
const enviando = ref(false)

const tieneSaldo = (oc) => oc.liberada && Object.values(oc.por_unidad).some((u) => u.disponible > 0)
// Columnas (TablaDatos): las esenciales a la vista y el resto en «Columnas»; las
// de datos que el rol no ve no aparecen. Cada una filtra por sus valores (el
// servidor da los valores únicos); las calculadas al vuelo no.
const fecha = (v) => fmtFecha(v)
const columnasOC = computed(() => [
  { clave: 'oc', texto: t('Purchase order'), fija: true, prioridad: 1 },
  { clave: 'estado', texto: t('Status'), inicial: false, ordenable: false, prioridad: 3, opciones: ESTADOS_OC },
  { clave: 'proveedor', texto: t('Supplier'), inicial: !sesion.proveedorId, prioridad: 2 },
  { clave: 'sociedad', texto: t('Company · plant · warehouse'), grupo: 'codigos_internos', inicial: false, ordenable: false, prioridad: 3 },
  { clave: 'destino', texto: t('Destination plant / port'), inicial: false, ordenable: false, prioridad: 3 },
  { clave: 'xf', texto: t('XF date'), prioridad: 2, textoValor: fecha },
  { clave: 'tienda', texto: t('In store'), grupo: 'fechas_internas', prioridad: 3, textoValor: fecha },
  { clave: 'tienda_estimada', texto: t('Est. in store'), grupo: 'fechas_internas', inicial: false, ordenable: false, filtro: false, prioridad: 3 },
  { clave: 'por_facturar', texto: t('To invoice'), ordenable: false, filtro: false, prioridad: 2 },
  { clave: 'importe', texto: t('PO value'), grupo: 'precios', num: true, filtro: false, prioridad: 2 },
  { clave: 'avance', texto: t('Invoiced'), prioridad: 3, textoValor: (v) => `${v}%` },
])
// Líneas de una OC (al abrirla): filtro por columna en el navegador
const columnasLineas = computed(() => [
  { clave: 'posicion', texto: t('Line'), fija: true, prioridad: 1 },
  { clave: 'articulo', texto: t('Item'), prioridad: 1, valor: (p) => [p.marca, p.estilo, p.color].filter(Boolean).join(' · ') },
  { clave: 'talla', texto: t('Size'), prioridad: 1 },
  { clave: 'unidad', texto: t('UoM'), prioridad: 3 },
  { clave: 'partida', texto: t('HS code'), prioridad: 3, valor: (p) => p.partida_arancelaria || null },
  { clave: 'almacen', texto: t('Warehouse'), grupo: 'codigos_internos', prioridad: 3 },
  { clave: 'empaque', texto: t('Packing'), prioridad: 3, valor: (p) => (p.tipo_empaque === 'PREPACK' ? t('Prepack')
    : [p.casepack && t('Casepack {0}', [p.casepack]), p.inner_pack && t('Inner {0}', [p.inner_pack])].filter(Boolean).join(' · ') || t('Free')) },
  { clave: 'cantidad', texto: t('Quantity'), num: true, prioridad: 2 },
  { clave: 'disponible', texto: t('Available'), num: true, prioridad: 2 },
  { clave: 'a_facturar', texto: t('To invoice'), num: true, filtro: false, ordenable: false, prioridad: 1 },
  { clave: 'precio', texto: t('Price'), num: true, grupo: 'precios', prioridad: 3 },
  { clave: 'importe', texto: t('Total'), num: true, grupo: 'precios', prioridad: 3 },
  { clave: 'estado', texto: t('Status'), prioridad: 2, textoValor: (v) => tx(leerEstado(v, 'oc')[0]) },
])
// Liberación en una sola insignia: solo si no se puede facturar o si cambió
// después de liberada (los nombres son los de la empresa)
function liberacion(oc) {
  const motivo = [oc.comercial_txt, oc.liberacion_txt].filter(Boolean).join(' · ')
  if (!oc.liberada) return { texto: t('Not released'), clase: 'aviso', motivo }
  if (oc.con_cambios) return { texto: t('Released with changes'), clase: 'info', motivo }
  return null
}

// Filtros de la pantalla que viajan con la lista y con los valores de cada columna
const filtrosPantalla = () => ({
  proveedor_id: sesion.proveedorId, q: filtros.q || undefined, solo_disponible: filtros.solo_disponible,
  ...Object.fromEntries(Object.keys(EXTRA).filter((k) => filtros[k]).map((k) => [k, filtros[k]])),
})
const ORDEN_SERVIDOR = { oc: 'numero', xf: 'fecha_xf', tienda: 'fecha_tienda' }
const ordenServidor = (o) => {
  const [c, dir] = (o || '').split(':')
  return c ? `${ORDEN_SERVIDOR[c] || c}:${dir}` : undefined
}
const valoresColumna = (columna, buscar, otros) => api.get('/ordenes/valores', { columna, buscar, f: JSON.stringify(otros), ...filtrosPantalla() })
let ultima = null
async function consultar(c = ultima) {
  if (!c) return
  ultima = c
  cargando.value = true
  try {
    datos.value = await api.get('/ordenes', {
      ...filtrosPantalla(), orden: ordenServidor(c.orden), page: c.page, size: c.size,
      f: Object.keys(c.filtros).length ? JSON.stringify(c.filtros) : undefined,
    })
    const ids = new Set(datos.value.items.map((o) => o.id))
    seleccionOC.value = seleccionOC.value.filter((id) => ids.has(id))
  } catch (e) {
    errorApi(e)
  } finally {
    cargando.value = false
  }
}
// Un filtro de la pantalla vuelve a la primera página
function cargar() {
  if (tablaOC.value && tablaOC.value.pagina !== 1) tablaOC.value.pagina = 1
  else consultar()
}

async function cargarFiltros() {
  try {
    opcionesFiltro.value = await api.get('/ordenes/filtros', { proveedor_id: sesion.proveedorId })
  } catch (e) {
    errorApi(e)
  }
}

function filtrar() {
  const query = { ...route.query }
  for (const k of Object.keys(EXTRA)) {
    if (filtros[k]) query[k] = filtros[k]
    else delete query[k]
  }
  router.replace({ query })
  cargar()
}

// Filtros secundarios: plegados hasta que se piden o ya tienen un valor
const AVANZADOS = ['sociedad', 'centro', 'almacen', 'destino', 'puerto', 'comercial', 'liberacion']
const avanzadosActivos = computed(() => AVANZADOS.filter((k) => filtros[k]).length)
// Vistas guardadas: búsqueda, «solo con saldo» y los filtros de lista
const filtrosVista = computed(() => ({ q: filtros.q, solo_disponible: filtros.solo_disponible ? '' : '0',
  ...Object.fromEntries(Object.keys(EXTRA).map((k) => [k, filtros[k]])) }))
function aplicarVista(q) {
  filtros.q = q.q || ''
  filtros.solo_disponible = q.solo_disponible !== '0'
  for (const k of Object.keys(EXTRA)) filtros[k] = q[k] || ''
  filtrar()
}
function quitarFiltro(k) {
  filtros[k] = ''
  filtrar()
}

function limpiarFiltros() {
  for (const k of Object.keys(EXTRA)) filtros[k] = ''
  filtrar()
}

const xfCambio = (oc) => oc.fecha_xf_original && oc.fecha_xf && oc.fecha_xf_original !== oc.fecha_xf
// Se resalta a partir de los días de aviso de la empresa (Configuración → Empresa → Reglas)
const tonoTienda = (d) => (d === null || d === undefined ? '' : d < 0 ? 'error' : d < (sesion.usuario?.config?.dias_aviso_tienda ?? 30) ? 'aviso' : '')

let espera
function buscar() {
  clearTimeout(espera)
  espera = setTimeout(cargar, 300)
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

// Al abrir una OC en la tabla se cargan sus líneas
async function abrirDetalle(oc) {
  try {
    await cargarDetalle(oc.id)
  } catch (e) {
    errorApi(e)
  }
}

const lineaSeleccionable = (p) => p.disponible > 0 && p.estado !== 'NO_DISPONIBLE'
const seleccionables = (ocId) => (detalles[ocId]?.posiciones || []).filter(lineaSeleccionable).map((p) => p.id)
// Las líneas elegidas de una OC (la selección de líneas es una sola para todas las OCs abiertas)
const lineasElegidas = (ocId) => seleccionables(ocId).filter((id) => selPos.tiene(id))
function elegirLineas(ocId, ids) {
  const nuevas = new Set(ids)
  for (const id of seleccionables(ocId)) {
    if (nuevas.has(id)) selPos.ids.add(id)
    else selPos.ids.delete(id)
  }
}
const seleccionadas = (ocId) => seleccionables(ocId).filter((id) => selPos.tiene(id)).length

function informar(r, texto, abrir = false) {
  if (r.error) {
    avisar(r.error, 'error')
    return
  }
  avisar(t('{0}: {1} lines in the selection', [texto, r.agregadas]) + (r.omitidas ? t('; {0} without balance were skipped.', [r.omitidas]) : '.'))
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
  seleccionOC.value = []
  informar(total, ids.length > 1 ? t('{0} full POs', [ids.length]) : t('Full PO'), abrir)
}

function agregarSeleccionadas(ocId) {
  const d = detalles[ocId]
  const posiciones = d.posiciones.filter((p) => selPos.tiene(p.id))
  const invalidas = posiciones.filter((p) => cantidadInvalida(p.a_facturar, p.disponible, p.inner_pack))
  if (invalidas.length) {
    avisar(t('Check “To invoice” on {0} lines: between 1 and the available quantity, in whole inner packs.', [invalidas.length]), 'error')
    return
  }
  const r = agregarPosiciones(d.oc, posiciones)
  posiciones.forEach((p) => selPos.ids.delete(p.id))
  informar(r, t('PO {0}', [d.oc.numero]))
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
    avisar(t('PO {0} line {1}: packing updated.', [e.oc.numero, e.p.posicion]))
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
  if (centros.size > 1) avisos.push(t('The selection mixes plants ({0}); they must go on separate invoices.', [[...centros].join(', ')]))
  if (monedas.size > 1) avisos.push(t('The selection mixes currencies ({0}); they must go on separate invoices.', [[...monedas].join(', ')]))
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
      avisar(t('{0}: {1} new lines and {2} with more quantity.', [f.nombre, r.agregadas, r.aumentadas]), 'ok',
        r.advertencias?.length ? r.advertencias : null)
    } else {
      const r = await api.post('/facturas', {
        proveedor_id: carrito.proveedorId,
        lineas,
        numero: nueva.numero || null,
        fecha: nueva.fecha || null,
      })
      id = r.id
      avisar(t('Invoice {0} created as a draft.', [r.nombre]), 'ok', r.advertencias?.length ? r.advertencias : null)
    }
    vaciarCarrito()
    router.push(`/facturas/${id}?tab=lineas`)
  } catch (e) {
    errorApi(e)
  } finally {
    enviando.value = false
  }
}

// Bandeja de aprobación: las OCs que esperan al rol del usuario
const pendientes = ref([])
async function cargarPendientes() {
  if (!puede('oc.aprobar')) return
  try {
    pendientes.value = await api.get('/ordenes/pendientes-aprobacion')
  } catch (e) {
    errorApi(e)
  }
}
// Un estado distinto de «aprobada» no tiene saldo para facturar: se muestran todas
function elegirEstado() {
  if (filtros.estado && filtros.estado !== 'APROBADA') filtros.solo_disponible = false
  filtrar()
}
function verPendientes() {
  filtros.estado = 'EN_APROBACION'
  elegirEstado()
}
function soloConSaldo(v) {
  filtros.solo_disponible = v
  if (v && filtros.estado && filtros.estado !== 'APROBADA') filtros.estado = ''
  filtrar()
}

onMounted(() => {
  cargarFiltros()
  cargarPendientes()
})
watch(() => sesion.proveedorId, () => {
  cargarFiltros()
  Object.keys(detalles).forEach((k) => delete detalles[k])
  cargar()
})
watch(() => route.query.seleccion, (v) => v && (panel.value = true))
watch([panel, () => carrito.proveedorId], ([abierto]) => abierto && cargarBorradores(), { immediate: true })
</script>

<template>
  <div class="pagina-cabeza">
    <div>
      <div class="eyebrow">{{ t('Step 1 of 3 · Invoice') }}</div>
      <h1>{{ t('Purchase orders') }}</h1>
      <p>{{ t('Choose what to invoice: full POs or only some lines and quantities. You can combine several POs of the same supplier in one invoice.') }}</p>
    </div>
    <div class="acciones">
      <router-link to="/tableros/compras" class="btn btn-fantasma"><Icono nombre="grafica" />{{ t('Indicators') }}</router-link>
      <router-link v-if="puede('oc.editar')" to="/ordenes/nueva" class="btn"><Icono nombre="mas" />{{ t('New PO') }}</router-link>
      <router-link v-if="puede('oc.importar')" to="/importar" class="btn"><Icono nombre="importar" />{{ t('Import POs') }}</router-link>
      <button class="btn btn-primario" type="button" :disabled="!carrito.items.length" @click="panel = true">
        <Icono nombre="carrito" />{{ t('Review selection ({0})', [carrito.items.length]) }}
      </button>
    </div>
  </div>

  <div v-if="pendientes.length" class="nota aviso bandeja" role="status">
    <Icono nombre="reloj" :tam="16" />
    <span>{{ t('{0} purchase orders wait for your approval:', [pendientes.length]) }}
      <router-link v-for="p in pendientes.slice(0, 4)" :key="p.id" :to="`/ordenes/${p.id}`" class="codigo">{{ tx(p.numero) }}</router-link></span>
    <button type="button" class="btn btn-chico" @click="verPendientes">{{ t('See them all') }}</button>
  </div>

  <TablaDatos ref="tablaOC" tabla="ordenes" modo="servidor" :columnas="columnasOC" :filas="datos.items" :total="datos.total" :cargando="cargando"
              :valores="valoresColumna" :externos="filtrosVista" :chips-externos="activos.map((a) => ({ clave: a.k, texto: a.texto }))"
              :mas-filtros-activos="avanzadosActivos" expandible seleccionable v-model:seleccion="seleccionOC" :puede-seleccionar="tieneSaldo"
              :etiqueta="t('Purchase orders')" @consulta="consultar" @vista="aplicarVista" @quitar-externo="quitarFiltro"
              @limpiar-externos="limpiarFiltros" @expandir="(oc) => abrirDetalle(oc)">
    <template #barra>
      <label class="buscador">
        <Icono nombre="buscar" :tam="16" />
        <input v-model="filtros.q" type="search" :placeholder="t('Search PO, style, color, SKU or UPC')" :aria-label="t('Search')" @input="buscar" />
      </label>
    </template>
    <template #filtros>
      <SelectBusqueda v-if="opcionesFiltro.marcas.length > 1 || filtros.marca" v-model="filtros.marca" :opciones="opcionesFiltro.marcas" :vacio="t('Brand: all')" :etiqueta="t('Brand')" @change="filtrar" />
      <div class="segmentos" role="group" :aria-label="t('Show')">
        <button class="segmento" type="button" :aria-pressed="filtros.solo_disponible" @click="soloConSaldo(true)">{{ t('With balance to invoice') }}</button>
        <button class="segmento" type="button" :aria-pressed="!filtros.solo_disponible" @click="soloConSaldo(false)">{{ t('All') }}</button>
      </div>
      <Seleccion v-model="filtros.estado" :aria-label="t('Status')" @change="elegirEstado">
        <option value="">{{ t('Status: all') }}</option><option v-for="[c, texto] in ESTADOS_OC" :key="c" :value="c">{{ tx(texto) }}</option>
      </Seleccion>
    </template>
    <template #mas-filtros>
      <SelectBusqueda v-if="ve('codigos_internos') && (opcionesFiltro.sociedades.length > 1 || filtros.sociedad)" v-model="filtros.sociedad" :opciones="opcionesFiltro.sociedades" :vacio="t('Company: all')" :etiqueta="t('Company')" @change="filtrar" />
      <SelectBusqueda v-if="ve('codigos_internos') && (opcionesFiltro.centros.length > 1 || filtros.centro)" v-model="filtros.centro" :opciones="opcionesFiltro.centros" :vacio="t('Plant: all')" :etiqueta="t('Plant')" @change="filtrar" />
      <SelectBusqueda v-if="ve('codigos_internos') && (opcionesFiltro.almacenes.length > 1 || filtros.almacen)" v-model="filtros.almacen" :opciones="opcionesFiltro.almacenes" :vacio="t('Warehouse: all')" :etiqueta="t('Warehouse')" @change="filtrar" />
      <SelectBusqueda v-if="ve('codigos_internos') && (opcionesFiltro.destinos.length > 1 || filtros.destino)" v-model="filtros.destino" :opciones="opcionesFiltro.destinos.map((d) => ({ valor: d.codigo, texto: `${d.codigo} · ${d.nombre}` }))"
                      :vacio="t('Destination plant: all')" :etiqueta="t('Destination plant')" @change="filtrar" />
      <SelectBusqueda v-if="opcionesFiltro.puertos.length > 1 || filtros.puerto" v-model="filtros.puerto" :opciones="opcionesFiltro.puertos.map((d) => ({ valor: d.codigo, texto: `${d.codigo} · ${d.nombre}` }))"
                      :vacio="t('Port: all')" :etiqueta="t('Port of loading')" @change="filtrar" />
      <Seleccion v-if="ve('liberaciones')" v-model="filtros.comercial" :aria-label="t('Commercial release')" @change="filtrar">
        <option value="">{{ t('Commercial rel.: all') }}</option><option v-for="l in opcionesFiltro.comerciales" :key="l.codigo" :value="l.codigo">{{ tx(l.nombre) }}</option>
      </Seleccion>
      <Seleccion v-if="ve('liberaciones')" v-model="filtros.liberacion" :aria-label="t('Logistics release')" @change="filtrar"><option value="">{{ t('Logistics rel.: all') }}</option><option v-for="l in opcionesFiltro.liberaciones" :key="l.codigo" :value="l.codigo">{{ tx(l.nombre) }}</option></Seleccion>
    </template>

    <template #celda-oc="{ fila: oc }">
      <router-link :to="`/ordenes/${oc.id}`" class="enlace-doc"><strong class="codigo">{{ tx(oc.numero) }}</strong></router-link>
      <EstadoBadge v-if="oc.estado !== 'APROBADA'" :estado="oc.estado" tipo="oc" />
      <span class="sub">{{ t('{0} · {1} lines', [fmtFecha(oc.fecha), oc.posiciones]) }}<template v-if="oc.marcas.length"> · {{ tx(oc.marcas.join(', ')) }}</template></span>
      <span v-if="liberacion(oc)" class="etiqueta" :class="liberacion(oc).clase" :title="tx(liberacion(oc).motivo || '')">{{ tx(liberacion(oc).texto) }}</span>
    </template>
    <template #celda-estado="{ fila: oc }"><EstadoBadge :estado="oc.estado" tipo="oc" /></template>
    <template #celda-sociedad="{ fila: oc }"><span class="codigo">{{ tx(oc.sociedad) }} · {{ tx(oc.centro || '—') }}</span><span class="sub" :title="tx(oc.almacenes.length > 1 ? t('Lines go to different warehouses') : '')">{{ tx(oc.almacenes.join(' · ') || t('No warehouse')) }}</span></template>
    <template #celda-destino="{ fila: oc }">
      <span class="codigo" :title="tx(oc.destino_nombre || '')">{{ tx(oc.centro_destino || '—') }}<template v-if="oc.pais_destino"> · {{ tx(oc.pais_destino) }}</template></span>
      <span class="sub">{{ tx(oc.puerto_despacho || t('No port')) }}<template v-if="oc.pais_origen"> {{ t('· origin {0}', [oc.pais_origen]) }}</template></span>
    </template>
    <template #celda-xf="{ fila: oc }">
      {{ fmtFecha(oc.fecha_xf) }}
      <span v-if="xfCambio(oc)" class="sub" :title="t('Original XF {0}', [fmtFecha(oc.fecha_xf_original)])">{{ t('was') }} <s>{{ fmtFecha(oc.fecha_xf_original) }}</s></span>
    </template>
    <template #celda-tienda="{ fila: oc }">
      {{ fmtFecha(oc.fecha_tienda) }}
      <span v-if="oc.dias_tienda != null" class="sub" :style="tonoTienda(oc.dias_tienda) ? { color: `var(--${tonoTienda(oc.dias_tienda)})` } : null">{{ diasTxt(oc.dias_tienda) }}</span>
    </template>
    <template #celda-tienda_estimada="{ fila: oc }"><FechaTienda :fecha="oc.tienda_estimada" :dias="oc.dias_vs_tienda" /></template>
    <template #celda-por_facturar="{ fila: oc }">
      <div class="celda-por-facturar">
        <span class="fuerte">{{ porUnidadTxt(oc.por_unidad, 'disponible') }}</span>
        <span class="sub">{{ t('of {0}', [porUnidadTxt(oc.por_unidad, 'cantidad')]) }}</span>
      </div>
    </template>
    <template #celda-importe="{ fila: oc }">{{ fmtMoneda(oc.importe, oc.moneda) }}</template>
    <template #celda-avance="{ fila: oc }"><div class="celda-avance"><Avance :porcentaje="oc.avance" /></div></template>
    <template #acciones="{ fila: oc }">
      <div class="acciones-apiladas">
        <button class="btn btn-chico" type="button" :disabled="!tieneSaldo(oc)" :title="t('Add the whole balance to the selection')" @click="agregarOCs([oc.id])"><Icono nombre="mas" :tam="14" />{{ t('Add') }}</button>
        <button class="btn btn-chico btn-primario" type="button" :disabled="!tieneSaldo(oc)" :title="t('Add the whole balance and review the invoice')" @click="agregarOCs([oc.id], true)">{{ t('Invoice') }}</button>
      </div>
    </template>
    <template #detalle="{ fila: oc }">
      <div>
        <p v-if="!detalles[oc.id]" class="ayuda">{{ t('Loading the lines…') }}</p>
        <template v-else>
          <p v-if="camposPropios('ordenes').some((c) => detalles[oc.id].oc.extra?.[c.clave] != null)" class="ayuda propios">
            <span v-for="c in camposPropios('ordenes').filter((c) => detalles[oc.id].oc.extra?.[c.clave] != null)" :key="c.clave">{{ c.etiqueta }}: <b>{{ valorPropio(c, detalles[oc.id].oc.extra[c.clave]) }}</b></span>
          </p>
          <div class="fila-flex mb-chico barra-detalle">
            <button class="btn btn-primario btn-chico" type="button" :disabled="!seleccionadas(oc.id)" @click="agregarSeleccionadas(oc.id)">
              <Icono nombre="mas" :tam="14" />{{ t('Add {0} selected', [seleccionadas(oc.id) || '']) }}
            </button>
            <span class="ayuda">{{ t('Change “To invoice” to take only part; the rest stays available on the PO. With an inner pack it goes in whole inner packs.') }}</span>
          </div>
          <TablaDatos tabla="ordenes_lineas" :columnas="columnasLineas" :filas="detalles[oc.id].posiciones" :vistas-guardadas="false"
                      seleccionable :seleccion="lineasElegidas(oc.id)" :puede-seleccionar="lineaSeleccionable"
                      :etiqueta="t('Lines of PO {0}', [oc.numero])" @update:seleccion="(ids) => elegirLineas(oc.id, ids)">
            <template #celda-posicion="{ fila: p }"><span class="codigo">{{ tx(p.posicion) }}</span></template>
            <template #celda-articulo="{ fila: p }">
              <span v-if="p.marca" class="fuerte">{{ tx(p.marca) }}</span> {{ tx(p.estilo) }} · {{ tx(p.color) }}
              <span class="sub codigo">{{ tx(p.codigo_articulo) }}<template v-if="p.grupo"> · {{ tx(p.grupo) }}</template></span>
            </template>
            <template #celda-talla="{ fila: p }"><strong>{{ tx(p.talla) }}</strong></template>
            <template #celda-unidad="{ fila: p }"><span class="etiqueta ms-0" :title="tx(unidadTxt(p.unidad, 2))">{{ tx(p.unidad) }}</span></template>
            <template #celda-partida="{ fila: p }">
              <router-link v-if="p.clasificacion?.producto_id" :to="`/productos/${p.clasificacion.producto_id}`" class="enlace"
                           :title="tx(p.partida_arancelaria ? t('Approved 6-digit HS subheading') : t('Open the technical sheet'))">
                <span v-if="p.partida_arancelaria" class="codigo-sac">{{ tx(p.partida_arancelaria) }}</span>
                <span v-else class="etiqueta aviso ms-0">{{ tx(p.clasificacion.estado === 'observado' ? t('Sheet returned') : t('Not classified')) }}</span>
              </router-link>
              <span v-else class="apagado">—</span>
            </template>
            <template #celda-almacen="{ fila: p }"><span class="codigo">{{ tx(p.almacen || '—') }}</span></template>
            <template #celda-empaque="{ fila: p }">
              <span class="fila-flex empaque-celda">
                <button v-if="p.tipo_empaque === 'PREPACK'" type="button" class="etiqueta acento btn-explosion ms-0"
                        :title="t('See the prepack breakdown')" @click="explosion = { sku: p.codigo_articulo, cajas: p.cantidad }">
                  {{ t('Prepack {0} · {1} per carton', [p.prepack, p.unidades_por_caja]) }} <Icono nombre="lupa" :tam="12" />
                </button>
                <template v-else>
                  <span v-if="p.casepack" class="etiqueta info ms-0" :title="t('Exact quantity per master carton')">{{ t('Casepack {0}', [p.casepack]) }}</span>
                  <span v-if="p.inner_pack" class="etiqueta acento ms-0"
                        :title="t('Inner packs of {0}{1}', [p.inner_pack, p.casepack ? t('; {0} inner packs per carton', [p.casepack / p.inner_pack]) : ''])">{{ t('Inner {0}', [p.inner_pack]) }}</span>
                  <span v-if="!p.casepack && !p.inner_pack" class="ayuda">{{ t('Free') }}</span>
                </template>
                <button v-if="puede('oc.empaque') && p.tipo_empaque !== 'PREPACK' && !p.facturado" type="button" class="btn-icono"
                        :aria-label="t('Edit the packing of line {0}', [p.posicion])" :title="t('Edit casepack and inner pack')" @click="editarEmpaque(oc, p)">
                  <Icono nombre="editar" :tam="14" />
                </button>
              </span>
            </template>
            <template #celda-cantidad="{ fila: p }">{{ cantTxt(p.cantidad, p.unidad) }}</template>
            <template #celda-disponible="{ fila: p }"><strong>{{ fmtNum(p.disponible) }}</strong></template>
            <template #celda-a_facturar="{ fila: p }">
              <input v-model.number="p.a_facturar" class="celda num a-facturar" type="number" :min="p.inner_pack || 1" :step="p.inner_pack || 1" :max="p.disponible"
                     :aria-label="t('To invoice on line {0}', [p.posicion])" :disabled="!lineaSeleccionable(p)" @focus="selPos.ids.add(p.id)" />
            </template>
            <template #celda-precio="{ fila: p }">{{ fmtNum(p.precio, 2) }}</template>
            <template #celda-importe="{ fila: p }">{{ fmtNum(p.importe, 2) }}</template>
            <template #celda-estado="{ fila: p }">
              <EstadoBadge :estado="p.estado" />
              <span v-if="enCarrito(p.id)" class="etiqueta ok">{{ t('In selection') }}</span>
              <div v-if="p.motivo || p.facturas.length" class="ayuda">
                {{ tx(p.motivo) }}
                <template v-for="fa in p.facturas" :key="fa.id">
                  <router-link :to="`/facturas/${fa.id}`" class="enlace codigo">{{ tx(fa.nombre) }}</router-link> ({{ fmtNum(fa.cantidad) }})
                </template>
              </div>
            </template>
          </TablaDatos>
        </template>
      </div>
    </template>
    <template #vacio>{{ tx(filtros.solo_disponible ? t('No POs with balance to invoice.') : t('No POs match these filters.')) }}</template>
  </TablaDatos>

  <BarraSeleccion :cantidad="seleccionOC.length" :singular="t('PO selected')" :plural="t('POs selected')" @limpiar="seleccionOC = []">
    <button class="btn" type="button" @click="agregarOCs([...seleccionOC])">{{ t('Add to the selection') }}</button>
    <button class="btn btn-primario" type="button" @click="agregarOCs([...seleccionOC], true)">{{ t('Invoice together') }}</button>
  </BarraSeleccion>

  <div v-if="carrito.items.length && !panel && !seleccionOC.length" class="barra-seleccion" role="region" :aria-label="t('Selection to invoice')">
    <Icono nombre="carrito" />
    <strong>{{ t('{0} lines ready to invoice', [carrito.items.length]) }}</strong>
    <span class="resumen">{{ porUnidadTxt(totales.porUnidad, null) }} · {{ fmtMoneda(totales.importe, carrito.items[0].moneda) }}</span>
    <div class="acciones">
      <button class="btn btn-primario" type="button" @click="panel = true">{{ t('Review and create invoice') }}<Icono nombre="flecha" :tam="16" /></button>
    </div>
  </div>

  <div v-if="panel" class="cajon-fondo" @click="panel = false"></div>
  <aside v-if="panel" class="cajon" :aria-label="t('Selection to invoice')">
    <div class="cajon-cabeza">
      <div>
        <div class="eyebrow">{{ t('Step 2 of 3') }}</div>
        <h2>{{ t('Review and create the invoice') }}</h2>
        <p v-if="carrito.items.length">{{ t('Supplier {0}', [nombreProveedor(carrito.proveedorId)]) }}</p>
      </div>
      <button class="btn-icono" type="button" :aria-label="t('Close')" @click="panel = false"><Icono nombre="cerrar" :tam="20" /></button>
    </div>
    <div class="cajon-cuerpo">
      <div v-if="!carrito.items.length" class="vacio">
        <Icono nombre="carrito" :tam="28" />
        <p>{{ t('No lines yet. Use “Add” on a PO or open it and choose lines.') }}</p>
      </div>
      <template v-else>
        <div v-for="g in grupos" :key="g.oc_id" class="grupo-oc">
          <div class="grupo-oc-cabeza">
            <span>{{ t('PO {0}', [g.oc_numero]) }} <span class="etiqueta">{{ tx(g.centro) }}</span></span>
            <button class="btn-texto" type="button" @click="quitarOC(g.oc_id)">{{ t('Remove PO') }}</button>
          </div>
          <div v-for="i in g.items" :key="i.posicion_id" class="item-carrito">
            <div>
              <span class="codigo">{{ tx(i.posicion) }}</span> {{ tx(i.estilo) }} {{ tx(i.color) }} <b>{{ tx(i.talla) }}</b>
              <div class="ayuda">
                {{ t('{0} available', [cantTxt(i.disponible, i.unidad)]) }}<template v-if="i.inner_pack"> {{ t('· inner packs of {0}', [i.inner_pack]) }}</template><template v-if="i.aviso">. {{ tx(i.aviso) }}</template>
              </div>
            </div>
            <input v-model.number="i.cantidad" type="number" :min="pasoCantidad(i.unidad, i.inner_pack)" :step="pasoCantidad(i.unidad, i.inner_pack)" :max="i.disponible" :aria-label="t('Quantity to invoice on {0}', [i.posicion])" />
            <button class="btn-icono" type="button" :aria-label="t('Remove line {0}', [i.posicion])" @click="quitarPosicion(i.posicion_id)"><Icono nombre="cerrar" :tam="16" /></button>
          </div>
        </div>
      </template>
    </div>
    <div v-if="carrito.items.length" class="cajon-pie">
      <div class="total-carrito">
        <span>{{ porUnidadTxt(totales.porUnidad, null) }}</span>
        <strong>{{ fmtMoneda(totales.importe, carrito.items[0].moneda) }}</strong>
      </div>
      <p v-for="a in mezclas" :key="a" class="nota aviso"><Icono nombre="alerta" />{{ tx(a) }}</p>
      <p v-if="invalida" class="nota error"><Icono nombre="alerta" />{{ t('Some quantities are out of range (between 1 and the available quantity, in whole inner packs).') }}</p>
      <label class="campo">
        <span>{{ t('Where do you invoice it?') }}</span>
        <Seleccion v-model="destino">
          <option value="">{{ t('On a new invoice') }}</option>
          <option v-for="b in borradores" :key="b.id" :value="b.id">{{ t('Add to {0} ({1})', [b.nombre, b.estado === 'BORRADOR' ? 'draft' : t('in correction')]) }}</option>
        </Seleccion>
      </label>
      <div v-if="!destino" class="rejilla-campos">
        <label class="campo"><span class="req">{{ t('Invoice number') }}</span><input v-model="nueva.numero" :placeholder="t('You can add it later')" /></label>
        <label class="campo"><span class="req">{{ t('Date') }}</span><CampoFecha v-model="nueva.fecha" /></label>
      </div>
      <p v-if="!destino" class="leyenda-req">{{ t('Required to finalize the invoice; you can complete them later.') }}</p>
      <div class="fila-flex">
        <button class="btn-texto" type="button" @click="vaciarCarrito()">{{ t('Clear selection') }}</button>
        <button class="btn btn-primario separar" type="button" :disabled="enviando || invalida" @click="facturar">
          {{ tx(destino ? t('Add to the invoice') : t('Create invoice')) }}<Icono nombre="flecha" :tam="16" />
        </button>
      </div>
    </div>
  </aside>
  <ExplosionPrepack v-if="explosion" :sku="explosion.sku" :cajas="explosion.cajas" @cerrar="explosion = null" />
  <Modal v-if="empaque" :titulo="t('Packing of PO {0} line {1}', [empaque.oc.numero, empaque.p.posicion])" ancho="520px" @cerrar="empaque = null">
    <p class="ayuda mt-0">{{ t('{0} · {1} · size {2} · {3}', [empaque.p.estilo, empaque.p.color, empaque.p.talla, cantTxt(empaque.p.cantidad, empaque.p.unidad)]) }}</p>
    <form id="form-empaque" class="rejilla-campos" @submit.prevent="guardarEmpaque">
      <label class="campo"><span>{{ t('Casepack (per master carton)') }}</span>
        <input v-model="empaque.casepack" type="number" min="1" :placeholder="t('Free')" />
        <small class="ayuda">{{ t('Exact quantity per carton; only the last carton may be incomplete.') }}</small>
      </label>
      <label class="campo"><span>{{ t('Inner pack (units per pack)') }}</span>
        <input v-model="empaque.inner_pack" type="number" min="1" :placeholder="t('None')" />
        <small class="ayuda">{{ t('All inner packs carry the same quantity and their own label.') }}</small>
      </label>
    </form>
    <p v-if="empaque.casepack && empaque.inner_pack && empaque.casepack % empaque.inner_pack === 0" class="nota info">
      <Icono nombre="info" />{{ t('Each carton carries {0} inner packs of {1}.', [empaque.casepack / empaque.inner_pack, empaque.inner_pack]) }}
    </p>
    <p v-else-if="!empaque.casepack && empaque.inner_pack" class="nota info">
      <Icono nombre="info" />{{ t('Without a casepack, each carton carries the inner packs you define (always multiples of {0}).', [empaque.inner_pack]) }}
    </p>
    <p v-if="empaque.error" class="nota error" role="alert"><Icono nombre="alerta" />{{ tx(empaque.error) }}</p>
    <p class="ayuda">{{ t('It can only change while nothing on this line is invoiced.') }}</p>
    <template #pie>
      <button class="btn" @click="empaque = null">{{ t('Cancel') }}</button>
      <button class="btn btn-primario" type="submit" form="form-empaque">{{ t('Save packing') }}</button>
    </template>
  </Modal>
</template>

<style scoped>
.propios { display: flex; flex-wrap: wrap; gap: 4px 16px; margin: 0 0 8px; }
.celda-por-facturar { min-width: 100px; white-space: normal; }
.celda-avance { min-width: 110px; }
.empaque-celda { gap: 4px; flex-wrap: wrap; }
.a-facturar { width: 84px; }
.bandeja { margin-bottom: 12px; align-items: center; }
.bandeja > span { flex: 1; }
.bandeja a { margin-inline-start: 8px; color: inherit; font-weight: 650; }
</style>
