<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api'
import Avance from '../components/Avance.vue'
import BarraSeleccion from '../components/BarraSeleccion.vue'
import EstadoBadge from '../components/EstadoBadge.vue'
import Icono from '../components/Icono.vue'
import Paginacion from '../components/Paginacion.vue'
import ThOrden from '../components/ThOrden.vue'
import { siguienteOrden } from '../composables/useTabla'
import { agregarPosiciones, carrito, quitarOC, quitarPosicion, vaciarCarrito } from '../stores/carrito'
import { esInterno, nombreProveedor, sesion } from '../stores/sesion'
import { avisar, errorApi } from '../stores/ui'
import { LIBERACION, cantTxt, diasTxt, fmtFecha, fmtMoneda, fmtNum, porUnidadTxt, useSeleccion } from '../utils'

const route = useRoute()
const router = useRouter()

// Filtros que se eligen de listas armadas con lo que realmente hay en las OCs
const EXTRA = { sociedad: 'Sociedad', centro: 'Centro', marca: 'Marca', liberacion: 'Liberación', destino: 'Destino', puerto: 'Puerto' }
const filtros = reactive({
  q: route.query.q || '',
  solo_disponible: route.query.solo_disponible !== '0',
  orden: '',
  page: 1,
  size: 15,
  ...Object.fromEntries(Object.keys(EXTRA).map((k) => [k, route.query[k] || ''])),
})
const opcionesFiltro = ref({ sociedades: [], centros: [], marcas: [], destinos: [], puertos: [], liberaciones: [] })
const activos = computed(() => Object.keys(EXTRA).filter((k) => filtros[k]).map((k) => {
  let v = filtros[k]
  if (k === 'destino') v = opcionesFiltro.value.destinos.find((d) => d.codigo === v)?.nombre || v
  if (k === 'puerto') v = opcionesFiltro.value.puertos.find((d) => d.codigo === v)?.nombre || v
  if (k === 'liberacion') v = LIBERACION[v]?.[0] || v
  return { k, texto: `${EXTRA[k]}: ${v}` }
}))
const datos = ref({ items: [], total: 0 })
const cargando = ref(false)
const abiertas = reactive(new Set())
const detalles = reactive({})
const selOC = useSeleccion()
const selPos = useSeleccion()

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
  avisar(`${texto}: ${r.agregadas} posiciones en la selección` + (r.omitidas ? `; ${r.omitidas} sin saldo se omitieron.` : '.'))
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
  informar(total, ids.length > 1 ? `${ids.length} OCs completas` : 'OC completa', abrir)
}

function agregarSeleccionadas(ocId) {
  const d = detalles[ocId]
  const posiciones = d.posiciones.filter((p) => selPos.tiene(p.id))
  const invalidas = posiciones.filter((p) => !(p.a_facturar > 0) || p.a_facturar > p.disponible)
  if (invalidas.length) {
    avisar(`Revisa “A facturar” en ${invalidas.length} posiciones: debe estar entre 1 y lo disponible.`, 'error')
    return
  }
  const r = agregarPosiciones(d.oc, posiciones)
  posiciones.forEach((p) => selPos.ids.delete(p.id))
  informar(r, `OC ${d.oc.numero}`)
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
  if (centros.size > 1) avisos.push(`La selección mezcla centros (${[...centros].join(', ')}); deben ir en facturas separadas.`)
  if (monedas.size > 1) avisos.push(`La selección mezcla monedas (${[...monedas].join(', ')}); deben ir en facturas separadas.`)
  return avisos
})

const invalida = computed(() => carrito.items.some((i) => !(i.cantidad >= 1) || i.cantidad > i.disponible))

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
      avisar(`${f.nombre}: ${r.agregadas} líneas nuevas y ${r.aumentadas} con más cantidad.`, 'ok',
        r.advertencias?.length ? r.advertencias : null)
    } else {
      const r = await api.post('/facturas', {
        proveedor_id: carrito.proveedorId,
        lineas,
        numero: nueva.numero || null,
        fecha: nueva.fecha || null,
      })
      id = r.id
      avisar(`Factura ${r.nombre} creada en borrador.`, 'ok', r.advertencias?.length ? r.advertencias : null)
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
      <div class="eyebrow">Paso 1 de 3 · Facturar</div>
      <h1>Órdenes de compra</h1>
      <p>Elige qué facturar: OCs completas o solo algunas posiciones y cantidades. Puedes juntar varias OCs del mismo proveedor en una factura.</p>
    </div>
    <div class="acciones">
      <router-link v-if="esInterno()" to="/importar" class="btn"><Icono nombre="importar" />Importar OCs</router-link>
      <button class="btn btn-primario" type="button" :disabled="!carrito.items.length" @click="panel = true">
        <Icono nombre="carrito" />Revisar selección ({{ carrito.items.length }})
      </button>
    </div>
  </div>

  <div class="filtros">
    <label class="buscador">
      <Icono nombre="buscar" :tam="16" />
      <input v-model="filtros.q" type="search" placeholder="Buscar OC, estilo, color, SKU o UPC" aria-label="Buscar" @input="buscar" />
    </label>
    <select v-model="filtros.sociedad" aria-label="Sociedad" @change="filtrar"><option value="">Sociedad: todas</option><option v-for="v in opcionesFiltro.sociedades" :key="v">{{ v }}</option></select>
    <select v-model="filtros.centro" aria-label="Centro" @change="filtrar"><option value="">Centro: todos</option><option v-for="v in opcionesFiltro.centros" :key="v">{{ v }}</option></select>
    <select v-model="filtros.marca" aria-label="Marca" @change="filtrar"><option value="">Marca: todas</option><option v-for="v in opcionesFiltro.marcas" :key="v">{{ v }}</option></select>
    <select v-model="filtros.destino" aria-label="País destino" @change="filtrar"><option value="">Destino: todos</option><option v-for="d in opcionesFiltro.destinos" :key="d.codigo" :value="d.codigo">{{ d.codigo }} · {{ d.nombre }}</option></select>
    <select v-model="filtros.puerto" aria-label="Puerto de despacho" @change="filtrar"><option value="">Puerto: todos</option><option v-for="d in opcionesFiltro.puertos" :key="d.codigo" :value="d.codigo">{{ d.codigo }} · {{ d.nombre }}</option></select>
    <select v-model="filtros.liberacion" aria-label="Liberación logística" @change="filtrar"><option value="">Liberación: todas</option><option v-for="l in opcionesFiltro.liberaciones" :key="l.codigo" :value="l.codigo">{{ l.codigo }} · {{ l.nombre }}</option></select>
    <div class="segmentos" role="group" aria-label="Mostrar">
      <button class="segmento" type="button" :aria-pressed="filtros.solo_disponible" @click="filtros.solo_disponible = true; filtros.page = 1; cargar()">Con saldo por facturar</button>
      <button class="segmento" type="button" :aria-pressed="!filtros.solo_disponible" @click="filtros.solo_disponible = false; filtros.page = 1; cargar()">Todas</button>
    </div>
  </div>
  <div v-if="activos.length" class="chips">
    <span v-for="a in activos" :key="a.k" class="chip">{{ a.texto }}<button type="button" :aria-label="`Quitar ${a.texto}`" @click="quitarFiltro(a.k)"><Icono nombre="cerrar" :tam="13" /></button></span>
    <button type="button" class="btn btn-fantasma btn-chico" @click="limpiarFiltros">Limpiar filtros</button>
  </div>

  <div class="tabla-marco tabla-fija">
    <table class="tabla">
      <thead>
        <tr>
          <th class="chk">
            <input type="checkbox" aria-label="Seleccionar todas las OCs con saldo" :checked="selOC.todos(conSaldo)" @change="selOC.alternarTodos(conSaldo)" />
          </th>
          <th><span class="oculto-visual">Ver posiciones</span></th>
          <ThOrden campo="numero" :orden="filtros.orden" @ordenar="ordenar">Orden de compra</ThOrden>
          <ThOrden v-if="!sesion.proveedorId" campo="proveedor" :orden="filtros.orden" @ordenar="ordenar">Proveedor</ThOrden>
          <th>Sociedad · centro · almacén</th>
          <th>Destino / puerto</th>
          <ThOrden campo="fecha_xf" :orden="filtros.orden" @ordenar="ordenar">Fecha XF</ThOrden>
          <ThOrden campo="fecha_tienda" :orden="filtros.orden" @ordenar="ordenar">En tienda</ThOrden>
          <th>Por facturar</th>
          <ThOrden campo="importe" :orden="filtros.orden" num @ordenar="ordenar">Valor OC</ThOrden>
          <ThOrden campo="avance" :orden="filtros.orden" @ordenar="ordenar">Facturado</ThOrden>
          <th></th>
        </tr>
      </thead>
      <tbody>
        <template v-for="oc in datos.items" :key="oc.id">
          <tr :class="{ seleccionada: selOC.tiene(oc.id) }">
            <td class="chk">
              <input type="checkbox" :aria-label="`Seleccionar OC ${oc.numero}`" :disabled="!tieneSaldo(oc)" :checked="selOC.tiene(oc.id)" @change="selOC.alternar(oc.id)" />
            </td>
            <td>
              <button class="btn-icono" type="button" :aria-expanded="abiertas.has(oc.id)" :aria-label="`Ver posiciones de la OC ${oc.numero}`" @click="alternar(oc)">
                <Icono :nombre="abiertas.has(oc.id) ? 'abajo' : 'derecha'" :tam="16" />
              </button>
            </td>
            <td>
              <strong class="codigo">{{ oc.numero }}</strong>
              <span v-if="LIBERACION[oc.liberacion_logistica]" class="etiqueta" :class="LIBERACION[oc.liberacion_logistica][1]" :title="LIBERACION[oc.liberacion_logistica][2]">{{ LIBERACION[oc.liberacion_logistica][0] }}</span>
              <span class="sub">{{ fmtFecha(oc.fecha) }} · {{ oc.posiciones }} posiciones<template v-if="oc.marcas.length"> · {{ oc.marcas.join(', ') }}</template></span>
            </td>
            <td v-if="!sesion.proveedorId">{{ oc.proveedor }}</td>
            <td><span class="codigo">{{ oc.sociedad }} · {{ oc.centro || '—' }}</span><span class="sub">{{ oc.almacen || 'Sin almacén' }}</span></td>
            <td>
              <span class="codigo">{{ oc.pais_destino || '—' }}</span>
              <span class="sub">{{ oc.puerto_despacho || 'Sin puerto' }}<template v-if="oc.pais_origen"> · origen {{ oc.pais_origen }}</template></span>
            </td>
            <td>
              {{ fmtFecha(oc.fecha_xf) }}
              <span v-if="xfCambio(oc)" class="sub" :title="`XF original ${fmtFecha(oc.fecha_xf_original)}`"><s>{{ fmtFecha(oc.fecha_xf_original) }}</s> original</span>
            </td>
            <td>
              {{ fmtFecha(oc.fecha_tienda) }}
              <span v-if="oc.dias_tienda !== null" class="sub" :style="tonoTienda(oc.dias_tienda) ? { color: `var(--${tonoTienda(oc.dias_tienda)})` } : null">{{ diasTxt(oc.dias_tienda) }}</span>
            </td>
            <td>
              <span class="fuerte">{{ porUnidadTxt(oc.por_unidad, 'disponible') }}</span>
              <span class="sub">de {{ porUnidadTxt(oc.por_unidad, 'cantidad') }}</span>
            </td>
            <td class="num">{{ fmtMoneda(oc.importe, oc.moneda) }}</td>
            <td style="min-width: 130px"><Avance :porcentaje="oc.avance" /></td>
            <td class="num">
              <div class="fila-flex" style="justify-content: flex-end; flex-wrap: nowrap">
                <button class="btn btn-chico" type="button" :disabled="!tieneSaldo(oc)" title="Agregar todo el saldo a la selección" @click="agregarOCs([oc.id])"><Icono nombre="mas" :tam="14" />Agregar</button>
                <button class="btn btn-chico btn-primario" type="button" :disabled="!tieneSaldo(oc)" title="Agregar todo el saldo y revisar la factura" @click="agregarOCs([oc.id], true)">Facturar</button>
              </div>
            </td>
          </tr>
          <tr v-if="abiertas.has(oc.id) && detalles[oc.id]" class="fila-hija">
            <td :colspan="columnas">
              <div class="subtabla">
                <div class="tabla-marco">
                  <table class="tabla">
                    <thead>
                      <tr>
                        <th class="chk">
                          <input type="checkbox" aria-label="Seleccionar las posiciones con saldo" :checked="selPos.todos(seleccionables(oc.id))" @change="selPos.alternarTodos(seleccionables(oc.id))" />
                        </th>
                        <th>Pos.</th>
                        <th>Producto</th>
                        <th>Talla</th>
                        <th>Empaque</th>
                        <th class="num">Cantidad</th>
                        <th class="num">Disponible</th>
                        <th class="num">A facturar</th>
                        <th class="num">Precio</th>
                        <th class="num">Total</th>
                        <th>Estado</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="p in detalles[oc.id].posiciones" :key="p.id" :class="{ seleccionada: selPos.tiene(p.id) }">
                        <td class="chk">
                          <input type="checkbox" :aria-label="`Seleccionar posición ${p.posicion}`" :disabled="!p.disponible || p.estado === 'NO_DISPONIBLE'" :checked="selPos.tiene(p.id)" @change="selPos.alternar(p.id)" />
                        </td>
                        <td class="codigo">{{ p.posicion }}</td>
                        <td>
                          <span v-if="p.marca" class="fuerte">{{ p.marca }}</span> {{ p.estilo }} · {{ p.color }}
                          <span class="sub codigo">{{ p.codigo_sap }}<template v-if="p.grupo"> · {{ p.grupo }}</template></span>
                        </td>
                        <td><strong>{{ p.talla }}</strong></td>
                        <td>
                          <span v-if="p.tipo_empaque === 'PREPACK'" class="etiqueta acento" style="margin-left: 0" :title="`Curva ${p.prepack}`">Prepack · {{ p.unidades_por_caja }} pares</span>
                          <span v-else-if="p.casepack" class="etiqueta info" style="margin-left: 0">Casepack {{ p.casepack }}</span>
                          <span v-else class="ayuda">Libre</span>
                        </td>
                        <td class="num">{{ cantTxt(p.cantidad, p.unidad) }}</td>
                        <td class="num"><strong>{{ fmtNum(p.disponible) }}</strong></td>
                        <td class="num">
                          <input
                            v-model.number="p.a_facturar"
                            class="celda num"
                            type="number"
                            min="1"
                            :max="p.disponible"
                            style="width: 84px; border-color: var(--linea)"
                            :aria-label="`A facturar de la posición ${p.posicion}`"
                            :disabled="!p.disponible || p.estado === 'NO_DISPONIBLE'"
                            @focus="selPos.ids.add(p.id)"
                          />
                        </td>
                        <td class="num">{{ fmtNum(p.precio, 2) }}</td>
                        <td class="num">{{ fmtNum(p.total, 2) }}</td>
                        <td>
                          <EstadoBadge :estado="p.estado" />
                          <span v-if="enCarrito(p.id)" class="etiqueta ok">En selección</span>
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
                    <Icono nombre="mas" :tam="14" />Agregar {{ seleccionadas(oc.id) || '' }} seleccionadas
                  </button>
                  <span class="ayuda">Cambia “A facturar” para tomar solo una parte; el resto queda disponible en la OC.</span>
                </div>
              </div>
            </td>
          </tr>
        </template>
        <tr v-if="!datos.items.length && !cargando">
          <td :colspan="columnas" class="vacio">{{ filtros.solo_disponible ? 'No hay OCs con saldo por facturar.' : 'No hay OCs con estos filtros.' }}</td>
        </tr>
      </tbody>
    </table>
  </div>
  <Paginacion :page="filtros.page" :size="filtros.size" :total="datos.total" @cambiar="(p) => { filtros.page = p; cargar() }" @tamano="(t) => (filtros.size = t)" />

  <BarraSeleccion :cantidad="selOC.ids.size" singular="OC seleccionada" plural="OCs seleccionadas" @limpiar="selOC.limpiar()">
    <button class="btn" type="button" @click="agregarOCs(selOC.lista())">Agregar a la selección</button>
    <button class="btn btn-primario" type="button" @click="agregarOCs(selOC.lista(), true)">Facturar juntas</button>
  </BarraSeleccion>

  <div v-if="carrito.items.length && !panel && !selOC.ids.size" class="barra-seleccion" role="region" aria-label="Selección para facturar">
    <Icono nombre="carrito" />
    <strong>{{ carrito.items.length }} posiciones listas para facturar</strong>
    <span class="resumen">{{ porUnidadTxt(totales.porUnidad, null) }} · {{ fmtMoneda(totales.importe, carrito.items[0].moneda) }}</span>
    <div class="acciones">
      <button class="btn btn-primario" type="button" @click="panel = true">Revisar y crear factura<Icono nombre="flecha" :tam="16" /></button>
    </div>
  </div>

  <div v-if="panel" class="cajon-fondo" @click="panel = false"></div>
  <aside v-if="panel" class="cajon" aria-label="Selección para facturar">
    <div class="cajon-cabeza">
      <div>
        <div class="eyebrow">Paso 2 de 3</div>
        <h2>Revisa y crea la factura</h2>
        <p v-if="carrito.items.length">Proveedor {{ nombreProveedor(carrito.proveedorId) }}</p>
      </div>
      <button class="btn-icono" type="button" aria-label="Cerrar" @click="panel = false"><Icono nombre="cerrar" :tam="20" /></button>
    </div>
    <div class="cajon-cuerpo">
      <div v-if="!carrito.items.length" class="vacio">
        <Icono nombre="carrito" :tam="28" />
        <p>Aún no hay posiciones. Usa “Agregar” en una OC o ábrela y elige posiciones.</p>
      </div>
      <template v-else>
        <div v-for="g in grupos" :key="g.oc_id" class="grupo-oc">
          <div class="grupo-oc-cabeza">
            <span>OC {{ g.oc_numero }} <span class="etiqueta">{{ g.centro }}</span></span>
            <button class="btn-texto" type="button" @click="quitarOC(g.oc_id)">Quitar OC</button>
          </div>
          <div v-for="i in g.items" :key="i.posicion_id" class="item-carrito">
            <div>
              <span class="codigo">{{ i.posicion }}</span> {{ i.estilo }} {{ i.color }} <b>{{ i.talla }}</b>
              <div class="ayuda">
                {{ cantTxt(i.disponible, i.unidad) }} disponibles<template v-if="i.aviso">. {{ i.aviso }}</template>
              </div>
            </div>
            <input v-model.number="i.cantidad" type="number" min="1" :max="i.disponible" :aria-label="`Cantidad a facturar de ${i.posicion}`" />
            <button class="btn-icono" type="button" :aria-label="`Quitar posición ${i.posicion}`" @click="quitarPosicion(i.posicion_id)"><Icono nombre="cerrar" :tam="16" /></button>
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
      <p v-if="invalida" class="nota error"><Icono nombre="alerta" />Hay cantidades fuera de rango (entre 1 y lo disponible).</p>
      <label class="campo">
        <span>¿Dónde la facturas?</span>
        <select v-model="destino">
          <option value="">En una factura nueva</option>
          <option v-for="b in borradores" :key="b.id" :value="b.id">Agregar a {{ b.nombre }} ({{ b.estado === 'BORRADOR' ? 'borrador' : 'en corrección' }})</option>
        </select>
      </label>
      <div v-if="!destino" class="rejilla-campos">
        <label class="campo"><span class="req">Número de factura</span><input v-model="nueva.numero" placeholder="Puedes ponerlo después" /></label>
        <label class="campo"><span class="req">Fecha</span><input v-model="nueva.fecha" type="date" /></label>
      </div>
      <p v-if="!destino" class="leyenda-req">Obligatorios para finalizar la factura; puedes completarlos después.</p>
      <div class="fila-flex">
        <button class="btn-texto" type="button" @click="vaciarCarrito()">Vaciar selección</button>
        <button class="btn btn-primario separar" type="button" :disabled="enviando || invalida" @click="facturar">
          {{ destino ? 'Agregar a la factura' : 'Crear factura' }}<Icono nombre="flecha" :tam="16" />
        </button>
      </div>
    </div>
  </aside>
</template>
