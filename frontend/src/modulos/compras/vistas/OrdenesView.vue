<script setup>
import { t, tx } from '@/i18n/index.js'
import FechaTienda from '@/componentes/FechaTienda.vue'
import { computed, onMounted, reactive, ref, watch } from 'vue'
import Seleccion from '@/componentes/Seleccion.vue'
import { useRoute, useRouter } from 'vue-router'
import VistasGuardadas from '@/componentes/VistasGuardadas.vue'
import SelectorColumnas from '@/componentes/SelectorColumnas.vue'
import { useColumnas } from '@/composables/useColumnas'
import { api } from '@/nucleo/api'
import Avance from '@/componentes/Avance.vue'
import BarraSeleccion from '@/componentes/BarraSeleccion.vue'
import Modal from '@/componentes/Modal.vue'
import EstadoBadge from '@/componentes/EstadoBadge.vue'
import Icono from '@/componentes/Icono.vue'
import FilasEsqueleto from '@/componentes/FilasEsqueleto.vue'
import ExplosionPrepack from '@/componentes/ExplosionPrepack.vue'
import Paginacion from '@/componentes/Paginacion.vue'
import SelectBusqueda from '@/componentes/SelectBusqueda.vue'
import ThOrden from '@/componentes/ThOrden.vue'
import { siguienteOrden } from '@/composables/useTabla'
import { agregarPosiciones, carrito, quitarOC, quitarPosicion, vaciarCarrito } from '@/stores/carrito'
import { camposPropios, nombreProveedor, puede, sesion, valorPropio, ve } from '@/stores/sesion'
import { avisar, errorApi } from '@/stores/ui'
import { cantTxt, unidadTxt, diasTxt, fmtFecha, fmtMoneda, fmtNum, porUnidadTxt, useSeleccion } from '@/nucleo/utils'
import { pasoCantidad } from '@/nucleo/unidades.js'
import { filasDefecto } from '@/stores/preferencias'

const route = useRoute()
const router = useRouter()

// Filtros que se eligen de listas armadas con lo que realmente hay en las OCs
const EXTRA = { sociedad: t('Company'), centro: t('Plant'), almacen: t('Warehouse'), marca: t('Brand'), comercial: t('Commercial rel.'), liberacion: t('Logistics rel.'), liberada: t('Release'), destino: t('Destination plant'), puerto: t('Port') }
const filtros = reactive({
  q: route.query.q || '',
  solo_disponible: route.query.solo_disponible !== '0',
  orden: '',
  page: 1,
  size: filasDefecto(),
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
// Columnas: las esenciales a la vista; el resto, en «Columnas». Las de datos
// que el rol no ve (Usuarios y accesos → Rol) no aparecen.
const cols = useColumnas('ordenes', () => [
  { clave: 'oc', texto: t('Purchase order'), fija: true },
  { clave: 'proveedor', texto: t('Supplier'), inicial: !sesion.proveedorId },
  { clave: 'sociedad', texto: t('Company · plant · warehouse'), grupo: 'codigos_internos', inicial: false },
  { clave: 'destino', texto: t('Destination plant / port'), inicial: false },
  { clave: 'xf', texto: t('XF date') },
  { clave: 'tienda', texto: t('In store'), grupo: 'fechas_internas' },
  { clave: 'tienda_estimada', texto: t('Est. in store'), grupo: 'fechas_internas', inicial: false },
  { clave: 'por_facturar', texto: t('To invoice') },
  { clave: 'importe', texto: t('PO value'), grupo: 'precios' },
  { clave: 'avance', texto: t('Invoiced') },
])
// Selección, ver líneas y acciones + las columnas visibles
const columnas = computed(() => cols.cuantas.value + 3)
// Liberación en una sola insignia: solo si no se puede facturar o si cambió
// después de liberada (los nombres son los de la empresa)
function liberacion(oc) {
  const motivo = [oc.comercial_txt, oc.liberacion_txt].filter(Boolean).join(' · ')
  if (!oc.liberada) return { texto: t('Not released'), clase: 'aviso', motivo }
  if (oc.con_cambios) return { texto: t('Released with changes'), clase: 'info', motivo }
  return null
}

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

// Filtros secundarios: plegados hasta que se piden o ya tienen un valor
const AVANZADOS = ['sociedad', 'centro', 'almacen', 'destino', 'puerto', 'comercial', 'liberacion']
const avanzadosActivos = computed(() => AVANZADOS.filter((k) => filtros[k]).length)
const masFiltros = ref(AVANZADOS.some((k) => route.query[k]))
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

function ordenar(campo) {
  filtros.orden = siguienteOrden(filtros.orden, campo)
  filtros.page = 1
  cargar()
}

const xfCambio = (oc) => oc.fecha_xf_original && oc.fecha_xf && oc.fecha_xf_original !== oc.fecha_xf
// Se resalta a partir de los días de aviso de la empresa (Configuración → Empresa → Reglas)
const tonoTienda = (d) => (d === null || d === undefined ? '' : d < 0 ? 'error' : d < (sesion.usuario?.config?.dias_aviso_tienda ?? 30) ? 'aviso' : '')

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
  selOC.limpiar()
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
      <div class="eyebrow">{{ t('Step 1 of 3 · Invoice') }}</div>
      <h1>{{ t('Purchase orders') }}</h1>
      <p>{{ t('Choose what to invoice: full POs or only some lines and quantities. You can combine several POs of the same supplier in one invoice.') }}</p>
    </div>
    <div class="acciones">
      <router-link v-if="puede('oc.importar')" :to="{ path: '/importar', query: { modo: 'formulario' } }" class="btn"><Icono nombre="mas" />{{ t('New PO') }}</router-link>
      <router-link v-if="puede('oc.importar')" to="/importar" class="btn"><Icono nombre="importar" />{{ t('Import POs') }}</router-link>
      <button class="btn btn-primario" type="button" :disabled="!carrito.items.length" @click="panel = true">
        <Icono nombre="carrito" />{{ t('Review selection ({0})', [carrito.items.length]) }}
      </button>
    </div>
  </div>

  <div class="filtros" v-filtros>
    <label class="buscador">
      <Icono nombre="buscar" :tam="16" />
      <input v-model="filtros.q" type="search" :placeholder="t('Search PO, style, color, SKU or UPC')" :aria-label="t('Search')" @input="buscar" />
    </label>
    <VistasGuardadas pantalla="ordenes" :actual="filtrosVista" @aplicar="aplicarVista" />
    <SelectBusqueda v-if="opcionesFiltro.marcas.length > 1 || filtros.marca" v-model="filtros.marca" :opciones="opcionesFiltro.marcas" :vacio="t('Brand: all')" :etiqueta="t('Brand')" @change="filtrar" />
    <div class="segmentos" role="group" :aria-label="t('Show')">
      <button class="segmento" type="button" :aria-pressed="filtros.solo_disponible" @click="filtros.solo_disponible = true; filtros.page = 1; cargar()">{{ t('With balance to invoice') }}</button>
      <button class="segmento" type="button" :aria-pressed="!filtros.solo_disponible" @click="filtros.solo_disponible = false; filtros.page = 1; cargar()">{{ t('All') }}</button>
    </div>
    <button type="button" class="btn btn-fantasma mas-filtros-toggle" :aria-expanded="masFiltros" @click="masFiltros = !masFiltros">
      <Icono nombre="filtro" :tam="15" />{{ masFiltros ? t('Fewer filters') : t('More filters') }}<span v-if="avanzadosActivos" class="cuenta">{{ avanzadosActivos }}</span>
    </button>
    <SelectorColumnas :columnas="cols" />
  </div>
  <div v-if="masFiltros" class="filtros filtros-avanzados">
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
  </div>
  <div v-if="activos.length" class="chips">
    <span v-for="a in activos" :key="a.k" class="chip">{{ tx(a.texto) }}<button type="button" :aria-label="t('Remove {0}', [a.texto])" @click="quitarFiltro(a.k)"><Icono nombre="cerrar" :tam="13" /></button></span>
    <button type="button" class="btn btn-fantasma btn-chico" @click="limpiarFiltros">{{ t('Clear filters') }}</button>
  </div>

  <div class="tabla-marco tabla-fija">
    <table class="tabla" v-tarjetas>
      <thead>
        <tr>
          <th class="chk">
            <input type="checkbox" :aria-label="t('Select all POs with balance')" :checked="selOC.todos(conSaldo)" @change="selOC.alternarTodos(conSaldo)" />
          </th>
          <th><span class="oculto-visual">{{ t('See lines') }}</span></th>
          <ThOrden campo="numero" :orden="filtros.orden" @ordenar="ordenar">{{ t('Purchase order') }}</ThOrden>
          <ThOrden v-if="cols.ver('proveedor')" campo="proveedor" :orden="filtros.orden" @ordenar="ordenar">{{ t('Supplier') }}</ThOrden>
          <th v-if="cols.ver('sociedad')">{{ t('Company · plant · warehouse') }}</th>
          <th v-if="cols.ver('destino')">{{ t('Destination plant / port') }}</th>
          <ThOrden v-if="cols.ver('xf')" campo="fecha_xf" :orden="filtros.orden" @ordenar="ordenar">{{ t('XF date') }}</ThOrden>
          <ThOrden v-if="cols.ver('tienda')" campo="fecha_tienda" :orden="filtros.orden" @ordenar="ordenar">{{ t('In store') }}</ThOrden>
          <th v-if="cols.ver('tienda_estimada')" :title="t('Estimated with the lead times of its origin')">{{ t('Est. in store') }}</th>
          <th v-if="cols.ver('por_facturar')">{{ t('To invoice') }}</th>
          <ThOrden v-if="cols.ver('importe')" campo="importe" :orden="filtros.orden" num @ordenar="ordenar">{{ t('PO value') }}</ThOrden>
          <ThOrden v-if="cols.ver('avance')" campo="avance" :orden="filtros.orden" @ordenar="ordenar">{{ t('Invoiced') }}</ThOrden>
          <th></th>
        </tr>
      </thead>
      <tbody>
        <template v-for="oc in datos.items" :key="oc.id">
          <tr :class="{ seleccionada: selOC.tiene(oc.id) }">
            <td class="chk">
              <input type="checkbox" :aria-label="t('Select PO {0}', [oc.numero])" :disabled="!tieneSaldo(oc)" :checked="selOC.tiene(oc.id)" @change="selOC.alternar(oc.id)" />
            </td>
            <td>
              <button class="btn-icono" type="button" :aria-expanded="abiertas.has(oc.id)" :aria-label="t('See the lines of PO {0}', [oc.numero])" @click="alternar(oc)">
                <Icono :nombre="abiertas.has(oc.id) ? 'abajo' : 'derecha'" :tam="16" />
              </button>
            </td>
            <td>
              <strong class="codigo">{{ tx(oc.numero) }}</strong>
              <span class="sub">{{ t('{0} · {1} lines', [fmtFecha(oc.fecha), oc.posiciones]) }}<template v-if="oc.marcas.length"> · {{ tx(oc.marcas.join(', ')) }}</template></span>
              <span v-if="liberacion(oc)" class="etiqueta" :class="liberacion(oc).clase" :title="tx(liberacion(oc).motivo || '')">{{ tx(liberacion(oc).texto) }}</span>
            </td>
            <td v-if="cols.ver('proveedor')">{{ tx(oc.proveedor) }}</td>
            <td v-if="cols.ver('sociedad')"><span class="codigo">{{ tx(oc.sociedad) }} · {{ tx(oc.centro || '—') }}</span><span class="sub" :title="tx(oc.almacenes.length > 1 ? t('Lines go to different warehouses') : '')">{{ tx(oc.almacenes.join(' · ') || t('No warehouse')) }}</span></td>
            <td v-if="cols.ver('destino')">
              <span class="codigo" :title="tx(oc.destino_nombre || '')">{{ tx(oc.centro_destino || '—') }}<template v-if="oc.pais_destino"> · {{ tx(oc.pais_destino) }}</template></span>
              <span class="sub">{{ tx(oc.puerto_despacho || t('No port')) }}<template v-if="oc.pais_origen"> {{ t('· origin {0}', [oc.pais_origen]) }}</template></span>
            </td>
            <td v-if="cols.ver('xf')">
              {{ fmtFecha(oc.fecha_xf) }}
              <span v-if="xfCambio(oc)" class="sub" :title="t('Original XF {0}', [fmtFecha(oc.fecha_xf_original)])">{{ t('was') }} <s>{{ fmtFecha(oc.fecha_xf_original) }}</s></span>
            </td>
            <td v-if="cols.ver('tienda')">
              {{ fmtFecha(oc.fecha_tienda) }}
              <span v-if="oc.dias_tienda != null" class="sub" :style="tonoTienda(oc.dias_tienda) ? { color: `var(--${tonoTienda(oc.dias_tienda)})` } : null">{{ diasTxt(oc.dias_tienda) }}</span>
            </td>
            <td v-if="cols.ver('tienda_estimada')"><FechaTienda :fecha="oc.tienda_estimada" :dias="oc.dias_vs_tienda" /></td>
            <td v-if="cols.ver('por_facturar')" class="ajustar" style="min-width: 100px">
              <span class="fuerte">{{ porUnidadTxt(oc.por_unidad, 'disponible') }}</span>
              <span class="sub">{{ t('of {0}', [porUnidadTxt(oc.por_unidad, 'cantidad')]) }}</span>
            </td>
            <td v-if="cols.ver('importe')" class="num">{{ fmtMoneda(oc.importe, oc.moneda) }}</td>
            <td v-if="cols.ver('avance')" style="min-width: 110px"><Avance :porcentaje="oc.avance" /></td>
            <td class="num">
              <div class="acciones-apiladas">
                <button class="btn btn-chico" type="button" :disabled="!tieneSaldo(oc)" :title="t('Add the whole balance to the selection')" @click="agregarOCs([oc.id])"><Icono nombre="mas" :tam="14" />{{ t('Add') }}</button>
                <button class="btn btn-chico btn-primario" type="button" :disabled="!tieneSaldo(oc)" :title="t('Add the whole balance and review the invoice')" @click="agregarOCs([oc.id], true)">{{ t('Invoice') }}</button>
              </div>
            </td>
          </tr>
          <tr v-if="abiertas.has(oc.id) && detalles[oc.id]" class="fila-hija">
            <td :colspan="columnas">
              <p v-if="camposPropios('ordenes').some((c) => detalles[oc.id].oc.extra?.[c.clave] != null)" class="ayuda propios">
                <span v-for="c in camposPropios('ordenes').filter((c) => detalles[oc.id].oc.extra?.[c.clave] != null)" :key="c.clave">{{ c.etiqueta }}: <b>{{ valorPropio(c, detalles[oc.id].oc.extra[c.clave]) }}</b></span>
              </p>
              <div class="subtabla">
                <div class="tabla-marco">
                  <table class="tabla" v-tarjetas>
                    <thead>
                      <!-- Item data comes from the item master; PO line data comes with the purchase order -->
                      <tr class="grupo-columnas">
                        <th colspan="2"></th>
                        <th colspan="4" :title="t('Taken from the item master and its technical sheet (the same on every PO)')">{{ t('Item · master data') }}</th>
                        <th :colspan="5 + (ve('codigos_internos') ? 1 : 0) + (ve('precios') ? 2 : 0)" :title="t('Comes with this purchase order line')">{{ t('PO line · purchase data') }}</th>
                        <th></th>
                      </tr>
                      <tr>
                        <th class="chk">
                          <input type="checkbox" :aria-label="t('Select the lines with balance')" :checked="selPos.todos(seleccionables(oc.id))" @change="selPos.alternarTodos(seleccionables(oc.id))" />
                        </th>
                        <th>{{ t('Line') }}</th>
                        <th>{{ t('Item') }}</th>
                        <th>{{ t('Size') }}</th>
                        <th class="col-sec">{{ t('UoM') }}</th>
                        <th :title="t('6-digit HS subheading from the approved technical sheet (the destination country is only projected)')">{{ t('HS code') }}</th>
                        <th v-if="ve('codigos_internos')" class="col-sec">{{ t('Warehouse') }}</th>
                        <th>{{ t('Packing') }}</th>
                        <th class="num">{{ t('Quantity') }}</th>
                        <th class="num col-sec">{{ t('Available') }}</th>
                        <th class="num">{{ t('To invoice') }}</th>
                        <th v-if="ve('precios')" class="num">{{ t('Price') }}</th>
                        <th v-if="ve('precios')" class="num">{{ t('Total') }}</th>
                        <th>{{ t('Status') }}</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="p in detalles[oc.id].posiciones" :key="p.id" :class="{ seleccionada: selPos.tiene(p.id) }">
                        <td class="chk">
                          <input type="checkbox" :aria-label="t('Select line {0}', [p.posicion])" :disabled="!p.disponible || p.estado === 'NO_DISPONIBLE'" :checked="selPos.tiene(p.id)" @change="selPos.alternar(p.id)" />
                        </td>
                        <td class="codigo">{{ tx(p.posicion) }}</td>
                        <td>
                          <span v-if="p.marca" class="fuerte">{{ tx(p.marca) }}</span> {{ tx(p.estilo) }} · {{ tx(p.color) }}
                          <span class="sub codigo">{{ tx(p.codigo_sap) }}<template v-if="p.grupo"> · {{ tx(p.grupo) }}</template></span>
                        </td>
                        <td><strong>{{ tx(p.talla) }}</strong></td>
                        <td><span class="etiqueta" style="margin-inline-start: 0" :title="tx(unidadTxt(p.unidad, 2))">{{ tx(p.unidad) }}</span></td>
                        <td>
                          <router-link v-if="p.clasificacion?.producto_id" :to="`/productos/${p.clasificacion.producto_id}`" class="enlace"
                                       :title="tx(p.partida_arancelaria ? t('Approved 6-digit HS subheading') : t('Open the technical sheet'))">
                            <span v-if="p.partida_arancelaria" class="codigo-sac">{{ tx(p.partida_arancelaria) }}</span>
                            <span v-else class="etiqueta aviso" style="margin-inline-start: 0">{{ tx(p.clasificacion.estado === 'observado' ? t('Sheet returned') : t('Not classified')) }}</span>
                          </router-link>
                          <span v-else class="apagado">—</span>
                        </td>
                        <td v-if="ve('codigos_internos')" class="codigo">{{ tx(p.almacen || '—') }}</td>
                        <td>
                          <span class="fila-flex" style="gap: 4px; flex-wrap: wrap">
                            <button v-if="p.tipo_empaque === 'PREPACK'" type="button" class="etiqueta acento btn-explosion" style="margin-inline-start: 0"
                                    :title="t('See the prepack breakdown')" @click="explosion = { sku: p.codigo_sap, cajas: p.cantidad }">
                              {{ t('Prepack {0} · {1} per carton', [p.prepack, p.unidades_por_caja]) }} <Icono nombre="lupa" :tam="12" />
                            </button>
                            <template v-else>
                              <span v-if="p.casepack" class="etiqueta info" style="margin-inline-start: 0" :title="t('Exact quantity per master carton')">{{ t('Casepack {0}', [p.casepack]) }}</span>
                              <span v-if="p.inner_pack" class="etiqueta acento" style="margin-inline-start: 0"
                                    :title="t('Inner packs of {0}{1}', [p.inner_pack, p.casepack ? t('; {0} inner packs per carton', [p.casepack / p.inner_pack]) : ''])">{{ t('Inner {0}', [p.inner_pack]) }}</span>
                              <span v-if="!p.casepack && !p.inner_pack" class="ayuda">{{ t('Free') }}</span>
                            </template>
                            <button v-if="puede('oc.empaque') && p.tipo_empaque !== 'PREPACK' && !p.facturado" type="button" class="btn-icono"
                                    :aria-label="t('Edit the packing of line {0}', [p.posicion])" :title="t('Edit casepack and inner pack')" @click="editarEmpaque(oc, p)">
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
                            :aria-label="t('To invoice on line {0}', [p.posicion])"
                            :disabled="!p.disponible || p.estado === 'NO_DISPONIBLE'"
                            @focus="selPos.ids.add(p.id)"
                          />
                        </td>
                        <td v-if="ve('precios')" class="num">{{ fmtNum(p.precio, 2) }}</td>
                        <td v-if="ve('precios')" class="num">{{ fmtNum(p.importe, 2) }}</td>
                        <td>
                          <EstadoBadge :estado="p.estado" />
                          <span v-if="enCarrito(p.id)" class="etiqueta ok">{{ t('In selection') }}</span>
                          <div v-if="p.motivo || p.facturas.length" class="ayuda">
                            {{ tx(p.motivo) }}
                            <template v-for="fa in p.facturas" :key="fa.id">
                              <router-link :to="`/facturas/${fa.id}`">{{ tx(fa.nombre) }}</router-link> ({{ fmtNum(fa.cantidad) }})
                            </template>
                          </div>
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
                <div class="fila-flex mt">
                  <button class="btn btn-primario btn-chico" type="button" :disabled="!seleccionadas(oc.id)" @click="agregarSeleccionadas(oc.id)">
                    <Icono nombre="mas" :tam="14" />{{ t('Add {0} selected', [seleccionadas(oc.id) || '']) }}
                  </button>
                  <span class="ayuda">{{ t('Change “To invoice” to take only part; the rest stays available on the PO. With an inner pack it goes in whole inner packs.') }}</span>
                </div>
              </div>
            </td>
          </tr>
        </template>
        <FilasEsqueleto v-if="cargando && !datos.items.length" :columnas="columnas" />
        <tr v-if="!datos.items.length && !cargando">
          <td :colspan="columnas" class="vacio">{{ tx(filtros.solo_disponible ? t('No POs with balance to invoice.') : t('No POs match these filters.')) }}</td>
        </tr>
      </tbody>
    </table>
  </div>
  <Paginacion :page="filtros.page" :size="filtros.size" :total="datos.total" @cambiar="(p) => { filtros.page = p; cargar() }" @tamano="(t) => (filtros.size = t)" />

  <BarraSeleccion :cantidad="selOC.ids.size" :singular="t('PO selected')" :plural="t('POs selected')" @limpiar="selOC.limpiar()">
    <button class="btn" type="button" @click="agregarOCs(selOC.lista())">{{ t('Add to the selection') }}</button>
    <button class="btn btn-primario" type="button" @click="agregarOCs(selOC.lista(), true)">{{ t('Invoice together') }}</button>
  </BarraSeleccion>

  <div v-if="carrito.items.length && !panel && !selOC.ids.size" class="barra-seleccion" role="region" :aria-label="t('Selection to invoice')">
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
    <p class="ayuda" style="margin-top: 0">{{ t('{0} · {1} · size {2} · {3}', [empaque.p.estilo, empaque.p.color, empaque.p.talla, cantTxt(empaque.p.cantidad, empaque.p.unidad)]) }}</p>
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
</style>
