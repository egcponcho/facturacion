<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api'
import Avance from '../components/Avance.vue'
import BarraSeleccion from '../components/BarraSeleccion.vue'
import EstadoBadge from '../components/EstadoBadge.vue'
import Paginacion from '../components/Paginacion.vue'
import { agregarPosiciones, carrito, quitarOC, quitarPosicion, vaciarCarrito } from '../stores/carrito'
import { nombreProveedor, sesion } from '../stores/sesion'
import { avisar, errorApi } from '../stores/ui'
import { cantTxt, fmtFecha, fmtMoneda, fmtNum, porUnidadTxt, useSeleccion } from '../utils'

const route = useRoute()
const router = useRouter()

const filtros = reactive({
  q: route.query.q || '',
  solo_disponible: route.query.solo_disponible !== '0',
  page: 1,
  size: 20,
})
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

function informar(r, texto) {
  if (r.error) {
    avisar(r.error, 'error')
    return
  }
  avisar(`${texto}: ${r.agregadas} posiciones en la selección` + (r.omitidas ? `; ${r.omitidas} sin saldo se omitieron.` : '.'))
  panel.value = true
}

async function agregarOCs(ids) {
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
  informar(total, ids.length > 1 ? `${ids.length} OCs completas` : 'OC completa')
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

onMounted(cargar)
watch(() => sesion.proveedorId, () => {
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
      <h1>Órdenes de compra</h1>
      <p>Agrega OCs completas o solo algunas posiciones y cantidades. Puedes juntar varias OCs del mismo proveedor en una factura.</p>
    </div>
    <button class="btn btn-primario" type="button" @click="panel = true">Selección para facturar ({{ carrito.items.length }})</button>
  </div>

  <div class="filtros">
    <input v-model="filtros.q" type="search" placeholder="Buscar OC, estilo, código SAP o UPC" aria-label="Buscar" @input="buscar" />
    <label class="check">
      <input v-model="filtros.solo_disponible" type="checkbox" @change="filtros.page = 1; cargar()" />
      Solo con saldo por facturar
    </label>
  </div>

  <div class="tabla-marco">
    <table class="tabla">
      <thead>
        <tr>
          <th class="chk">
            <input type="checkbox" aria-label="Seleccionar todas las OCs con saldo" :checked="selOC.todos(conSaldo)" @change="selOC.alternarTodos(conSaldo)" />
          </th>
          <th><span class="oculto-visual">Ver posiciones</span></th>
          <th>OC</th>
          <th v-if="!sesion.proveedorId">Proveedor</th>
          <th>Fecha</th>
          <th>Sociedad / centro</th>
          <th class="num">Posiciones</th>
          <th>Cantidad OC</th>
          <th>Por facturar</th>
          <th class="num">Importe</th>
          <th>Facturado (valor)</th>
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
                {{ abiertas.has(oc.id) ? '▾' : '▸' }}
              </button>
            </td>
            <td>
              <strong class="codigo">{{ oc.numero }}</strong>
              <span v-if="!oc.liberada" class="etiqueta error">No liberada</span>
            </td>
            <td v-if="!sesion.proveedorId">{{ oc.proveedor }}</td>
            <td>{{ fmtFecha(oc.fecha) }}</td>
            <td>{{ oc.sociedad }} / {{ oc.centro || '—' }}</td>
            <td class="num">{{ oc.posiciones }}</td>
            <td>{{ porUnidadTxt(oc.por_unidad, 'cantidad') }}</td>
            <td>{{ porUnidadTxt(oc.por_unidad, 'disponible') }}</td>
            <td class="num">{{ fmtMoneda(oc.importe, oc.moneda) }}</td>
            <td><Avance :porcentaje="oc.avance" /></td>
            <td>
              <button class="btn btn-chico" type="button" :disabled="!tieneSaldo(oc)" @click="agregarOCs([oc.id])">Agregar completa</button>
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
                        <th>Código SAP</th>
                        <th>Estilo</th>
                        <th>Color</th>
                        <th>Talla</th>
                        <th class="num">Cantidad</th>
                        <th class="num">Facturado</th>
                        <th class="num">Disponible</th>
                        <th class="num">A facturar</th>
                        <th class="num">Precio</th>
                        <th>Estado</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="p in detalles[oc.id].posiciones" :key="p.id" :class="{ seleccionada: selPos.tiene(p.id) }">
                        <td class="chk">
                          <input type="checkbox" :aria-label="`Seleccionar posición ${p.posicion}`" :disabled="!p.disponible || p.estado === 'NO_DISPONIBLE'" :checked="selPos.tiene(p.id)" @change="selPos.alternar(p.id)" />
                        </td>
                        <td class="codigo">{{ p.posicion }}</td>
                        <td class="codigo">{{ p.codigo_sap }}</td>
                        <td>{{ p.estilo }}</td>
                        <td>{{ p.color }}</td>
                        <td><strong>{{ p.talla }}</strong></td>
                        <td class="num">{{ cantTxt(p.cantidad, p.unidad) }}</td>
                        <td class="num">{{ fmtNum(p.facturado) }}</td>
                        <td class="num"><strong>{{ fmtNum(p.disponible) }}</strong></td>
                        <td class="num">
                          <input
                            v-model.number="p.a_facturar"
                            class="celda num"
                            type="number"
                            min="1"
                            :max="p.disponible"
                            style="width: 84px"
                            :aria-label="`A facturar de la posición ${p.posicion}`"
                            :disabled="!p.disponible || p.estado === 'NO_DISPONIBLE'"
                            @focus="selPos.ids.add(p.id)"
                          />
                        </td>
                        <td class="num">{{ fmtNum(p.precio, 2) }}</td>
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
                    Agregar {{ seleccionadas(oc.id) || '' }} seleccionadas
                  </button>
                  <span class="ayuda">Cambia “A facturar” para tomar solo una parte; el resto queda disponible en la OC.</span>
                </div>
              </div>
            </td>
          </tr>
        </template>
        <tr v-if="!datos.items.length && !cargando">
          <td :colspan="columnas" class="vacio">No hay OCs con estos filtros.</td>
        </tr>
      </tbody>
    </table>
  </div>
  <Paginacion :page="filtros.page" :size="filtros.size" :total="datos.total" @cambiar="(p) => { filtros.page = p; cargar() }" />

  <BarraSeleccion :cantidad="selOC.ids.size" singular="OC seleccionada" plural="OCs seleccionadas" @limpiar="selOC.limpiar()">
    <button class="btn btn-primario" type="button" @click="agregarOCs(selOC.lista())">Agregar completas a la selección</button>
  </BarraSeleccion>

  <aside v-if="panel" class="cajon" aria-label="Selección para facturar">
    <div class="cajon-cabeza">
      <h2>Selección para facturar</h2>
      <button class="btn-icono" type="button" aria-label="Cerrar" @click="panel = false">×</button>
    </div>
    <div class="cajon-cuerpo">
      <p v-if="!carrito.items.length" class="vacio">
        Aún no hay posiciones. Usa “Agregar completa” en una OC o ábrela y elige posiciones.
      </p>
      <template v-else>
        <p class="ayuda" style="margin-bottom: 10px">Proveedor: <b>{{ nombreProveedor(carrito.proveedorId) }}</b></p>
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
            <button class="btn-icono" type="button" :aria-label="`Quitar posición ${i.posicion}`" @click="quitarPosicion(i.posicion_id)">×</button>
          </div>
        </div>
      </template>
    </div>
    <div v-if="carrito.items.length" class="cajon-pie">
      <div class="fila-flex">
        <span>{{ porUnidadTxt(totales.porUnidad, null) }}</span>
        <strong class="separar">{{ fmtMoneda(totales.importe, carrito.items[0].moneda) }}</strong>
      </div>
      <p v-for="a in mezclas" :key="a" class="nota aviso">{{ a }}</p>
      <p v-if="invalida" class="nota error">Hay cantidades fuera de rango (entre 1 y lo disponible).</p>
      <label class="campo">
        <span>Destino</span>
        <select v-model="destino">
          <option value="">Nueva factura</option>
          <option v-for="b in borradores" :key="b.id" :value="b.id">Agregar a {{ b.nombre }}</option>
        </select>
      </label>
      <div v-if="!destino" class="rejilla-campos">
        <label class="campo"><span>Número de factura (opcional)</span><input v-model="nueva.numero" /></label>
        <label class="campo"><span>Fecha (opcional)</span><input v-model="nueva.fecha" type="date" /></label>
      </div>
      <div class="fila-flex">
        <button class="btn-texto" type="button" @click="vaciarCarrito()">Vaciar selección</button>
        <button class="btn btn-primario separar" type="button" :disabled="enviando || invalida" @click="facturar">
          {{ destino ? 'Agregar a la factura' : 'Crear factura' }}
        </button>
      </div>
    </div>
  </aside>
</template>
