<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api'
import Avance from '../components/Avance.vue'
import BarraSeleccion from '../components/BarraSeleccion.vue'
import CeldaEditable from '../components/CeldaEditable.vue'
import EstadoBadge from '../components/EstadoBadge.vue'
import Modal from '../components/Modal.vue'
import { elegirProveedor, esInterno } from '../stores/sesion'
import { avisar, errorApi, guardando, textoDetalle } from '../stores/ui'
import {
  ACCIONES, fmtFecha, fmtFechaHora, fmtFechaHoraLocal, fmtMoneda, fmtNum, plural, porUnidadTxt, unidadTxt, useSeleccion,
} from '../utils'

const props = defineProps({ id: String })
const route = useRoute()
const router = useRouter()

const f = ref(null)
const tab = ref(route.query.tab || 'resumen')
const sel = useSeleccion()
const filtro = ref('')
const archivos = ref([])
const historial = ref([])
const subida = reactive({ archivo: null, tipo: 'FACTURA_OFICIAL' })
const modal = ref(null)
const ocupado = ref(false)

const editable = computed(() => !!f.value?.puede.editar)
const plsActivos = computed(() => (f.value?.packing_lists || []).filter((p) => p.estado !== 'CANCELADO'))
const conUnidad = computed(() => plsActivos.value.filter((p) => p.transporte).length)
const confirmados = computed(() => plsActivos.value.filter((p) => p.transporte?.asignacion === 'CONFIRMADA').length)
const plEditables = computed(() => plsActivos.value.some((p) => ['BORRADOR', 'EN_CORRECCION'].includes(p.estado)))

const lineasFiltradas = computed(() => {
  const q = filtro.value.trim().toLowerCase()
  if (!q) return f.value.lineas
  return f.value.lineas.filter((l) =>
    [l.codigo_sap, l.estilo, l.color, l.talla, l.oc_numero, l.upc, l.descripcion].some((v) => (v || '').toLowerCase().includes(q)))
})
const idsFiltrados = computed(() => lineasFiltradas.value.map((l) => l.id))
const seleccion = computed(() => (f.value?.lineas || []).filter((l) => sel.tiene(l.id)))
const resumenSeleccion = computed(() => {
  const porUnidad = {}
  let importe = 0
  for (const l of seleccion.value) {
    porUnidad[l.unidad] = (porUnidad[l.unidad] || 0) + l.cantidad
    importe += l.total
  }
  return `${porUnidadTxt(porUnidad, null)}, ${fmtMoneda(importe, f.value.moneda)}`
})
const pendientePorUnidad = computed(() => {
  const r = {}
  for (const l of f.value?.lineas || []) if (l.sin_asignar > 0) r[l.unidad] = (r[l.unidad] || 0) + l.sin_asignar
  return r
})

const TABS = [
  ['resumen', 'Resumen'],
  ['lineas', 'Posiciones'],
  ['pl', 'Packing lists'],
  ['transporte', 'Transporte'],
  ['archivos', 'Archivos'],
  ['historial', 'Historial'],
]

const CAMPOS_MASIVOS = [
  ['precio_unitario', 'Precio unitario', 'number'],
  ['cantidad', 'Cantidad', 'number'],
  ['pais_origen', 'País de origen', 'text'],
  ['partida_arancelaria', 'Partida arancelaria', 'text'],
  ['descripcion_comercial', 'Descripción comercial', 'text'],
]

async function cargar() {
  try {
    f.value = await api.get(`/facturas/${props.id}`)
    sel.podar(f.value.lineas.map((l) => l.id))
  } catch (e) {
    errorApi(e)
    if (e.status === 404) router.push('/facturas')
  }
}

async function cargarTab() {
  try {
    if (tab.value === 'archivos') archivos.value = await api.get(`/facturas/${props.id}/archivos`)
    if (tab.value === 'historial') historial.value = await api.get(`/facturas/${props.id}/historial`)
  } catch (e) {
    errorApi(e)
  }
}

watch(tab, (t) => {
  router.replace({ query: { ...route.query, tab: t } })
  cargarTab()
})

function trasError(e) {
  errorApi(e)
  if (e.codigo === 'conflicto_version') cargar()
}

// ---- Cabecera -------------------------------------------------------------
const guardarCabecera = (campo) => async (valor) => {
  try {
    await guardando(api.patch(`/facturas/${props.id}`, { version: f.value.version, [campo]: valor === '' ? null : valor }))
    await cargar()
  } catch (e) {
    trasError(e)
    throw e
  }
}

// ---- Líneas: una celda o muchas a la vez usan el mismo camino --------------
async function enviarCambios(cambios, ajuste = 'error') {
  try {
    await guardando(api.patch(`/facturas/${props.id}/lineas`, { version: f.value.version, cambios, ajuste_pl: ajuste }))
    modal.value = null
    await cargar()
    return true
  } catch (e) {
    if (e.codigo === 'requiere_ajuste_pl') modal.value = { tipo: 'ajuste', detalle: e.detalle, cambios }
    else if (e.codigo === 'validacion' && e.detalle?.some((d) => d.codigo === 'motivo_precio')) {
      modal.value = { tipo: 'motivo_precio', cambios, motivo: '', lineas: e.detalle.map(textoDetalle) }
    } else trasError(e)
    return false
  }
}

const celda = (l, campo) => async (valor) => {
  const ok = await enviarCambios([{ linea_id: l.id, [campo]: valor }])
  if (!ok) throw new Error('no guardado')
}

function abrirMasivo() {
  modal.value = { tipo: 'masivo', campo: 'precio_unitario', valor: '', motivo: '' }
}

function aplicarMasivo() {
  const { campo, valor, motivo } = modal.value
  const tipo = CAMPOS_MASIVOS.find((c) => c[0] === campo)[2]
  const v = tipo === 'number' ? Number(valor) : valor
  if (tipo === 'number' && (valor === '' || Number.isNaN(v))) return avisar('Escribe un número válido.', 'error')
  enviarCambios(seleccion.value.map((l) => ({
    linea_id: l.id,
    [campo]: v,
    ...(campo === 'precio_unitario' && motivo ? { motivo_precio: motivo } : {}),
  })))
}

async function eliminar(confirmar) {
  const ids = sel.lista()
  ocupado.value = true
  try {
    await guardando(api.post(`/facturas/${props.id}/lineas/eliminar`, {
      version: f.value.version, linea_ids: ids, confirmar_cascada: confirmar,
    }))
    avisar(`Se ${ids.length === 1 ? 'quitó' : 'quitaron'} ${plural(ids.length, 'línea', 'líneas')}; sus cantidades volvieron a estar disponibles en las OCs.`)
    sel.limpiar()
    modal.value = null
    await cargar()
  } catch (e) {
    if (e.codigo === 'requiere_confirmacion') modal.value = { tipo: 'eliminar', mensaje: e.message, impacto: e.detalle }
    else {
      modal.value = null
      trasError(e)
    }
  } finally {
    ocupado.value = false
  }
}

// ---- Estados ---------------------------------------------------------------
async function finalizar(incluir) {
  ocupado.value = true
  try {
    await api.post(`/facturas/${props.id}/finalizar`, { version: f.value.version, incluir_packing_lists: incluir })
    avisar(incluir ? 'Factura y packing lists finalizados.' : 'Factura finalizada.')
    await cargar()
  } catch (e) {
    if (e.codigo === 'pendientes') modal.value = { tipo: 'pendientes', titulo: 'Datos pendientes para finalizar', detalle: e.detalle }
    else trasError(e)
  } finally {
    ocupado.value = false
  }
}

async function cambiarEstado() {
  const { accion, motivo } = modal.value
  ocupado.value = true
  try {
    await api.post(`/facturas/${props.id}/${accion}`, { version: f.value.version, motivo })
    avisar(accion === 'reabrir' ? 'Factura reabierta para corrección.' : 'Factura cancelada; sus cantidades volvieron a las OCs.')
    modal.value = null
    await cargar()
  } catch (e) {
    trasError(e)
  } finally {
    ocupado.value = false
  }
}

// ---- Packing lists ---------------------------------------------------------
async function crearPL(soloSeleccion) {
  const lineas = soloSeleccion
    ? seleccion.value.filter((l) => l.sin_asignar > 0).map((l) => ({ factura_linea_id: l.id, cantidad: l.sin_asignar }))
    : null
  ocupado.value = true
  try {
    const r = await api.post(`/facturas/${props.id}/packing-lists`, { lineas })
    avisar(`Se creó ${r.numero} con lo pendiente de asignar.`)
    router.push(`/packing-lists/${r.id}`)
  } catch (e) {
    if (e.codigo === 'sin_saldo') {
      avisar(e.message, 'error', (e.detalle || []).map((d) => `${d.numero}: ${fmtNum(d.cantidad)}`))
    } else trasError(e)
  } finally {
    ocupado.value = false
  }
}

function agregarDesdeOC() {
  if (esInterno()) elegirProveedor(f.value.proveedor_id)
  router.push({ path: '/ordenes', query: { factura: f.value.id } })
}

// ---- Archivos y exportación ------------------------------------------------
async function subir() {
  if (!subida.archivo) return
  const datos = new FormData()
  datos.append('archivo', subida.archivo)
  datos.append('tipo', subida.tipo)
  try {
    await api.post(`/facturas/${props.id}/archivos`, datos)
    avisar('Archivo adjuntado.')
    subida.archivo = null
    cargarTab()
  } catch (e) {
    errorApi(e)
  }
}

const descargar = (url, nombre) => api.descargar(url, nombre).catch(errorApi)

function resumenDetalle(d) {
  if (!d) return ''
  const valor = (v) => {
    if (Array.isArray(v) && v.length === 2 && typeof v[0] !== 'object') return `${v[0] ?? '—'} a ${v[1] ?? '—'}`
    if (v && typeof v === 'object') return JSON.stringify(v)
    return String(v)
  }
  const par = ([k, v]) => (k === 'ref' || k === 'fila' ? valor(v) : `${k.replaceAll('_', ' ')}: ${valor(v)}`)
  if (Array.isArray(d)) {
    return d.map((x) => (x && typeof x === 'object'
      ? Object.entries(x).filter(([k]) => k !== 'linea_id').map(par).join(', ')
      : String(x))).join('; ')
  }
  return Object.entries(d).filter(([, v]) => v !== null).map(par).join(', ')
}

onMounted(async () => {
  await cargar()
  cargarTab()
})
</script>

<template>
  <template v-if="f">
    <router-link to="/facturas" class="volver">Facturas</router-link>
    <section class="doc-cabeza">
      <div class="doc-fila">
        <span class="doc-numero">{{ f.nombre }}</span>
        <EstadoBadge :estado="f.estado" />
        <span v-if="f.lista_transporte" class="etiqueta ok">Lista para transporte</span>
        <div class="doc-acciones">
          <button v-if="f.puede.finalizar" class="btn btn-primario" :disabled="ocupado" @click="finalizar(false)">Finalizar factura</button>
          <button v-if="f.puede.finalizar && plEditables" class="btn" :disabled="ocupado" @click="finalizar(true)">Finalizar con sus packing lists</button>
          <button v-if="f.puede.reabrir" class="btn" @click="modal = { tipo: 'estado', accion: 'reabrir', motivo: '' }">Reabrir para corregir</button>
          <button class="btn" @click="descargar(`/facturas/${f.id}/exportar`, 'factura.xlsx')">Descargar Excel</button>
          <button v-if="f.puede.cancelar" class="btn btn-peligro" @click="modal = { tipo: 'estado', accion: 'cancelar', motivo: '' }">Cancelar factura</button>
        </div>
      </div>
      <div class="doc-meta">
        <span>Proveedor <b>{{ f.proveedor }}</b></span>
        <span>Sociedad <b>{{ f.sociedad }}</b></span>
        <span>Centro <b>{{ f.centro || '—' }}</b></span>
        <span>Moneda <b>{{ f.moneda }}</b></span>
        <span>Fecha <b>{{ fmtFecha(f.fecha) }}</b></span>
        <span>Importe <b>{{ fmtMoneda(f.totales.importe, f.moneda) }}</b></span>
      </div>
      <div class="progresos">
        <div class="progreso">
          <h3>Documentación</h3>
          <p v-if="f.estado === 'FINALIZADA'">Finalizada el {{ fmtFechaHora(f.finalizado_en) }}.</p>
          <p v-else-if="f.estado === 'CANCELADA'">Cancelada.</p>
          <p v-else-if="f.pendientes.length">
            <button class="btn-texto" style="padding: 0" @click="modal = { tipo: 'pendientes', titulo: 'Datos pendientes para finalizar', detalle: f.pendientes }">
              {{ f.pendientes.length }} datos pendientes para finalizar
            </button>
          </p>
          <p v-else>Completa; ya puedes finalizarla.</p>
        </div>
        <div class="progreso">
          <h3>Distribución y empaque</h3>
          <template v-for="(u, unidad) in f.totales.por_unidad" :key="unidad">
            <div class="linea-avance"><span>{{ unidadTxt(unidad) }} en PL</span><Avance :valor="u.en_pl" :total="u.facturado" /></div>
            <div class="linea-avance"><span>{{ unidadTxt(unidad) }} en cajas</span><Avance :valor="u.empacado" :total="u.facturado" /></div>
          </template>
          <p v-if="!f.lineas.length" class="ayuda">Sin líneas todavía.</p>
        </div>
        <div class="progreso">
          <h3>Transporte</h3>
          <p v-if="!plsActivos.length" class="ayuda">Aún no hay packing lists.</p>
          <p v-else>{{ conUnidad }} de {{ plsActivos.length }} PL con unidad de carga; {{ confirmados }} confirmados.</p>
        </div>
      </div>
    </section>

    <div class="pestanas" role="tablist">
      <button v-for="[clave, texto] in TABS" :key="clave" class="pestana" role="tab" :aria-selected="tab === clave" @click="tab = clave">
        {{ texto }}
        <span v-if="clave === 'lineas'" class="cuenta">{{ f.lineas.length }}</span>
        <span v-if="clave === 'pl'" class="cuenta">{{ plsActivos.length }}</span>
      </button>
    </div>

    <!-- Resumen -->
    <section v-if="tab === 'resumen'" class="panel">
      <div class="panel-cabeza"><h2>Datos de la factura</h2><span class="ayuda">Los datos de sociedad, centro y moneda vienen de la OC.</span></div>
      <div class="rejilla-campos">
        <label class="campo"><span>Número de factura del proveedor</span>
          <CeldaEditable v-if="editable" class="entrada" :valor="f.numero" :guardar="guardarCabecera('numero')" etiqueta="Número de factura" vacia-texto="Obligatorio para finalizar" />
          <b v-else>{{ f.numero || '—' }}</b>
        </label>
        <label class="campo"><span>Fecha</span>
          <CeldaEditable v-if="editable" class="entrada" tipo="date" :valor="f.fecha" :guardar="guardarCabecera('fecha')" etiqueta="Fecha" />
          <b v-else>{{ fmtFecha(f.fecha) }}</b>
        </label>
        <label class="campo"><span>Incoterm</span>
          <CeldaEditable v-if="editable" class="entrada" :valor="f.incoterm" :guardar="guardarCabecera('incoterm')" etiqueta="Incoterm" />
          <b v-else>{{ f.incoterm || '—' }}</b>
        </label>
        <label class="campo"><span>Condiciones de pago</span>
          <CeldaEditable v-if="editable" class="entrada" :valor="f.condiciones" :guardar="guardarCabecera('condiciones')" etiqueta="Condiciones" />
          <b v-else>{{ f.condiciones || '—' }}</b>
        </label>
      </div>
      <label class="campo mt"><span>Observaciones</span>
        <CeldaEditable v-if="editable" class="entrada" :valor="f.observaciones" :guardar="guardarCabecera('observaciones')" etiqueta="Observaciones" />
        <span v-else>{{ f.observaciones || '—' }}</span>
      </label>
      <div class="doc-meta">
        <span>Cantidad <b>{{ porUnidadTxt(f.totales.por_unidad, 'facturado') }}</b></span>
        <span>Líneas <b>{{ f.lineas.length }}</b></span>
        <span>Creada <b>{{ fmtFechaHora(f.creado_en) }}</b></span>
        <span>Última modificación <b>{{ fmtFechaHora(f.actualizado_en) }}</b></span>
      </div>
    </section>

    <!-- Posiciones -->
    <section v-if="tab === 'lineas'">
      <div class="filtros">
        <input v-model="filtro" type="search" placeholder="Filtrar por código, estilo, color, talla u OC" aria-label="Filtrar líneas" />
        <span class="separar"></span>
        <button v-if="editable" class="btn" @click="agregarDesdeOC">Agregar posiciones desde OCs</button>
      </div>
      <div class="tabla-marco">
        <table class="tabla">
          <thead>
            <tr>
              <th class="chk"><input type="checkbox" aria-label="Seleccionar todas las líneas filtradas" :checked="sel.todos(idsFiltrados)" @change="sel.alternarTodos(idsFiltrados)" /></th>
              <th>OC / pos.</th>
              <th>Código SAP</th>
              <th>Estilo</th>
              <th>Color</th>
              <th>Talla</th>
              <th class="num">Cantidad</th>
              <th>Unidad</th>
              <th class="num">Precio unitario</th>
              <th class="num">Total</th>
              <th class="num">En PL</th>
              <th class="num">Sin asignar</th>
              <th class="num">En cajas</th>
              <th>País origen</th>
              <th>Partida</th>
              <th>Descripción comercial</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="l in lineasFiltradas" :key="l.id" :class="{ seleccionada: sel.tiene(l.id) }">
              <td class="chk"><input type="checkbox" :aria-label="`Seleccionar ${l.codigo_sap} talla ${l.talla}`" :checked="sel.tiene(l.id)" @change="sel.alternar(l.id)" /></td>
              <td class="codigo">{{ l.oc_numero }} / {{ l.posicion }}</td>
              <td class="codigo">{{ l.codigo_sap }}</td>
              <td>{{ l.estilo }}</td>
              <td>{{ l.color }}</td>
              <td><strong>{{ l.talla }}</strong></td>
              <td class="num" style="width: 100px">
                <CeldaEditable v-if="editable" tipo="number" :min="1" paso="1" :valor="l.cantidad" :guardar="celda(l, 'cantidad')" :etiqueta="`Cantidad de ${l.codigo_sap}`" />
                <template v-else>{{ fmtNum(l.cantidad) }}</template>
              </td>
              <td>{{ unidadTxt(l.unidad) }}</td>
              <td class="num" style="width: 130px">
                <CeldaEditable v-if="editable" tipo="number" :min="0" paso="0.0001" :valor="l.precio_unitario" :guardar="celda(l, 'precio_unitario')" :etiqueta="`Precio de ${l.codigo_sap}`" />
                <template v-else>{{ fmtNum(l.precio_unitario, 2) }}</template>
                <span v-if="Math.abs(l.precio_unitario - l.precio_oc) > 1e-9" class="etiqueta aviso" :title="`Precio OC ${l.precio_oc}. Motivo: ${l.motivo_precio || 'sin indicar'}`">Distinto a OC</span>
              </td>
              <td class="num">{{ fmtNum(l.total, 2) }}</td>
              <td class="num">{{ fmtNum(l.en_pl) }}</td>
              <td class="num"><span :class="{ 'etiqueta aviso': l.sin_asignar > 0 }">{{ fmtNum(l.sin_asignar) }}</span></td>
              <td class="num">{{ fmtNum(l.empacado) }}</td>
              <td style="width: 80px">
                <CeldaEditable v-if="editable" :valor="l.pais_origen" :guardar="celda(l, 'pais_origen')" vacia-texto="Falta" :etiqueta="`País de origen de ${l.codigo_sap}`" />
                <template v-else>{{ l.pais_origen }}</template>
              </td>
              <td style="width: 110px">
                <CeldaEditable v-if="editable" :valor="l.partida_arancelaria" :guardar="celda(l, 'partida_arancelaria')" vacia-texto="Falta" :etiqueta="`Partida de ${l.codigo_sap}`" />
                <template v-else>{{ l.partida_arancelaria }}</template>
              </td>
              <td class="envolver">
                <CeldaEditable v-if="editable" :valor="l.descripcion_comercial" :guardar="celda(l, 'descripcion_comercial')" :etiqueta="`Descripción de ${l.codigo_sap}`" />
                <template v-else>{{ l.descripcion_comercial }}</template>
              </td>
            </tr>
            <tr v-if="!lineasFiltradas.length">
              <td colspan="16" class="vacio">
                {{ f.lineas.length ? 'Ninguna línea coincide con el filtro.' : 'La factura no tiene líneas.' }}
                <div v-if="editable && !f.lineas.length"><button class="btn" @click="agregarDesdeOC">Agregar posiciones desde OCs</button></div>
              </td>
            </tr>
          </tbody>
          <tfoot v-if="f.lineas.length">
            <tr>
              <td></td>
              <td colspan="5">{{ lineasFiltradas.length }} de {{ f.lineas.length }} líneas</td>
              <td colspan="3" class="num">{{ porUnidadTxt(f.totales.por_unidad, 'facturado') }}</td>
              <td class="num">{{ fmtMoneda(f.totales.importe, f.moneda) }}</td>
              <td colspan="6"></td>
            </tr>
          </tfoot>
        </table>
      </div>
      <BarraSeleccion :cantidad="sel.ids.size" singular="línea seleccionada" plural="líneas seleccionadas" @limpiar="sel.limpiar()">
        <template #resumen>{{ resumenSeleccion }}</template>
        <button v-if="editable" class="btn" @click="abrirMasivo">Cambiar un dato en todas</button>
        <button class="btn" :disabled="ocupado || f.estado === 'CANCELADA' || !seleccion.some((l) => l.sin_asignar > 0)" @click="crearPL(true)">Crear PL con la selección</button>
        <button v-if="editable" class="btn" @click="modal = { tipo: 'eliminar', mensaje: `¿Quitar ${sel.ids.size} líneas de la factura? Sus cantidades vuelven a estar disponibles en las OCs.` }">
          Quitar de la factura
        </button>
      </BarraSeleccion>
    </section>

    <!-- Packing lists -->
    <section v-if="tab === 'pl'">
      <div class="fila-flex" style="margin-bottom: 12px">
        <button class="btn btn-primario" :disabled="ocupado || !f.puede.crear_pl" @click="crearPL(false)">Crear packing list con lo pendiente</button>
        <span class="ayuda">
          {{ f.puede.crear_pl ? `Pendiente de asignar: ${porUnidadTxt(pendientePorUnidad, null)}.` : 'Toda la mercancía ya está en packing lists.' }}
        </span>
      </div>
      <div class="tabla-marco">
        <table class="tabla">
          <thead>
            <tr>
              <th>Packing list</th>
              <th>Estado</th>
              <th>Cantidad</th>
              <th class="num">Cajas</th>
              <th>Sin caja</th>
              <th class="num">Peso bruto kg</th>
              <th class="num">CBM</th>
              <th>Unidad de carga</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="p in f.packing_lists" :key="p.id" class="clicable" @click="router.push(`/packing-lists/${p.id}`)">
              <td><router-link :to="`/packing-lists/${p.id}`" class="cajas-rango" @click.stop>{{ p.numero }}</router-link></td>
              <td><EstadoBadge :estado="p.estado" /></td>
              <td>{{ porUnidadTxt(p.totales.por_unidad, 'cantidad') }}</td>
              <td class="num">{{ fmtNum(p.totales.cajas) }}</td>
              <td>
                <span v-if="Object.values(p.totales.por_unidad).some((u) => u.sin_caja)" class="etiqueta error">{{ porUnidadTxt(p.totales.por_unidad, 'sin_caja') }}</span>
                <span v-else class="apagado">—</span>
              </td>
              <td class="num">{{ fmtNum(p.totales.peso_bruto, 2) }}</td>
              <td class="num">{{ fmtNum(p.totales.cbm, 3) }}</td>
              <td>
                <template v-if="p.transporte">{{ p.transporte.unidad }} <EstadoBadge :estado="p.transporte.asignacion" /></template>
                <span v-else class="apagado">Sin asignar</span>
              </td>
            </tr>
            <tr v-if="!f.packing_lists.length">
              <td colspan="8" class="vacio">Todavía no hay packing lists. Crea el primero con lo pendiente de la factura.</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <!-- Transporte -->
    <section v-if="tab === 'transporte'">
      <div class="tabla-marco">
        <table class="tabla">
          <thead>
            <tr>
              <th>Packing list</th>
              <th>Unidad de carga</th>
              <th>Asignación</th>
              <th>Embarque</th>
              <th>BL / AWB</th>
              <th>Estado</th>
              <th>ETD</th>
              <th>ETA</th>
              <th>Salida real</th>
              <th>Arribo real</th>
              <th>Último evento</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="p in plsActivos" :key="p.id">
              <td class="cajas-rango">{{ p.numero }}</td>
              <template v-if="p.transporte">
                <td>{{ p.transporte.unidad }} <span class="etiqueta">{{ p.transporte.tipo }}</span></td>
                <td><EstadoBadge :estado="p.transporte.asignacion" /></td>
                <td>
                  <router-link v-if="esInterno()" :to="`/transporte/embarques/${p.transporte.embarque_id}`">{{ p.transporte.embarque }}</router-link>
                  <template v-else>{{ p.transporte.embarque }}</template>
                </td>
                <td>{{ p.transporte.documento || 'Pendiente' }}</td>
                <td><EstadoBadge :estado="p.transporte.estado" /></td>
                <td>{{ fmtFecha(p.transporte.etd) }}</td>
                <td>{{ fmtFecha(p.transporte.eta) }}</td>
                <td>{{ fmtFecha(p.transporte.salida_real) }}</td>
                <td>{{ fmtFecha(p.transporte.arribo_real) }}</td>
                <td>
                  <template v-if="p.transporte.ultimo_evento">
                    {{ p.transporte.ultimo_evento.tipo.toLowerCase() }}, {{ fmtFechaHoraLocal(p.transporte.ultimo_evento.fecha) }}
                  </template>
                  <span v-else class="apagado">—</span>
                </td>
              </template>
              <td v-else colspan="10" class="apagado">Sin unidad de carga asignada.</td>
            </tr>
            <tr v-if="!plsActivos.length"><td colspan="11" class="vacio">No hay packing lists para transportar.</td></tr>
          </tbody>
        </table>
      </div>
    </section>

    <!-- Archivos -->
    <section v-if="tab === 'archivos'" class="panel">
      <div class="panel-cabeza"><h2>Archivos</h2><span class="ayuda">Adjunta la factura oficial del proveedor (PDF) y otros soportes.</span></div>
      <div v-if="f.estado !== 'CANCELADA'" class="fila-flex">
        <input type="file" aria-label="Archivo" @change="subida.archivo = $event.target.files[0]" />
        <select v-model="subida.tipo" class="entrada" aria-label="Tipo de archivo">
          <option value="FACTURA_OFICIAL">Factura oficial</option>
          <option value="OTRO">Otro soporte</option>
        </select>
        <button class="btn btn-primario" :disabled="!subida.archivo" @click="subir">Adjuntar</button>
      </div>
      <div class="tabla-marco mt">
        <table class="tabla">
          <thead><tr><th>Archivo</th><th>Tipo</th><th class="num">Tamaño</th><th>Subido</th><th></th></tr></thead>
          <tbody>
            <tr v-for="a in archivos" :key="a.id">
              <td>{{ a.nombre }}</td>
              <td>{{ a.tipo === 'FACTURA_OFICIAL' ? 'Factura oficial' : 'Otro soporte' }}</td>
              <td class="num">{{ fmtNum(a.tamano / 1024, 0) }} KB</td>
              <td>{{ fmtFechaHora(a.subido_en) }}</td>
              <td><button class="btn btn-chico" @click="descargar(`/archivos/${a.id}`, a.nombre)">Descargar</button></td>
            </tr>
            <tr v-if="!archivos.length"><td colspan="5" class="vacio">Sin archivos adjuntos.</td></tr>
          </tbody>
        </table>
      </div>
    </section>

    <!-- Historial -->
    <section v-if="tab === 'historial'" class="panel">
      <ul class="linea-tiempo">
        <li v-for="h in historial" :key="h.id">
          <span class="ayuda">{{ fmtFechaHora(h.fecha) }}<br />{{ h.usuario }}</span>
          <div>
            <b>{{ ACCIONES[h.accion] || h.accion }}</b>
            <span class="etiqueta">{{ h.entidad === 'packing_list' ? 'Packing list' : 'Factura' }}</span>
            <div v-if="h.motivo">Motivo: {{ h.motivo }}</div>
            <div class="ayuda">{{ resumenDetalle(h.detalle) }}</div>
          </div>
        </li>
        <li v-if="!historial.length"><span></span><span class="ayuda">Sin movimientos.</span></li>
      </ul>
    </section>
  </template>

  <!-- Modales -->
  <Modal v-if="modal?.tipo === 'ajuste'" titulo="Esa cantidad ya está en packing lists" ancho="640px" @cerrar="modal = null">
    <p>La nueva cantidad es menor que lo que ya se asignó. Hay que liberar la diferencia de los PL.</p>
    <div v-for="d in modal.detalle" :key="d.linea_id" class="nota aviso">
      <b>{{ d.ref }}</b>: nueva cantidad {{ fmtNum(d.cantidad_nueva) }}, en PL {{ fmtNum(d.en_packing_lists) }}. Hay que liberar {{ fmtNum(d.hay_que_liberar) }}.
      <ul class="lista-mensajes">
        <li v-for="p in d.packing_lists" :key="p.pl_id">
          <router-link :to="`/packing-lists/${p.pl_id}`">{{ p.numero }}</router-link>: {{ fmtNum(p.cantidad) }}, de las cuales {{ fmtNum(p.sin_caja) }} sin caja
        </li>
      </ul>
    </div>
    <p class="ayuda">La liberación automática solo toma lo que no está en cajas, empezando por el PL más reciente. Si no alcanza, desempaca primero en el PL.</p>
    <template #pie>
      <button class="btn" @click="modal = null">Cancelar</button>
      <button class="btn btn-primario" @click="enviarCambios(modal.cambios, 'automatico')">Liberar lo que no está en cajas</button>
    </template>
  </Modal>

  <Modal v-if="modal?.tipo === 'motivo_precio'" titulo="Motivo del cambio de precio" @cerrar="modal = null">
    <ul class="lista-mensajes"><li v-for="(m, i) in modal.lineas" :key="i">{{ m }}</li></ul>
    <label class="campo"><span>Motivo</span><textarea v-model="modal.motivo" placeholder="Por ejemplo: precio acordado por volumen"></textarea></label>
    <template #pie>
      <button class="btn" @click="modal = null">Cancelar</button>
      <button class="btn btn-primario" :disabled="!modal.motivo.trim()" @click="enviarCambios(modal.cambios.map((c) => ({ ...c, motivo_precio: modal.motivo })))">Guardar precio</button>
    </template>
  </Modal>

  <Modal v-if="modal?.tipo === 'masivo'" :titulo="`Cambiar un dato en ${sel.ids.size} líneas`" @cerrar="modal = null">
    <label class="campo"><span>Dato</span>
      <select v-model="modal.campo">
        <option v-for="[c, t] in CAMPOS_MASIVOS" :key="c" :value="c">{{ t }}</option>
      </select>
    </label>
    <label class="campo"><span>Nuevo valor</span>
      <input v-model="modal.valor" :type="CAMPOS_MASIVOS.find((c) => c[0] === modal.campo)[2]" step="any" />
    </label>
    <label v-if="modal.campo === 'precio_unitario'" class="campo"><span>Motivo (obligatorio si difiere del precio de la OC)</span><textarea v-model="modal.motivo"></textarea></label>
    <p class="ayuda">Si algún cambio no se puede aplicar, no se aplica ninguno y verás qué líneas lo impiden.</p>
    <template #pie>
      <button class="btn" @click="modal = null">Cancelar</button>
      <button class="btn btn-primario" :disabled="modal.valor === ''" @click="aplicarMasivo">Aplicar a {{ sel.ids.size }} líneas</button>
    </template>
  </Modal>

  <Modal v-if="modal?.tipo === 'eliminar'" titulo="Quitar líneas de la factura" ancho="620px" @cerrar="modal = null">
    <p>{{ modal.mensaje }}</p>
    <div v-for="d in modal.impacto || []" :key="d.linea_id" class="nota aviso">
      <b>{{ d.ref }}</b>
      <ul class="lista-mensajes">
        <li v-for="p in d.packing_lists" :key="p.numero">{{ p.numero }}: {{ fmtNum(p.cantidad) }}, {{ fmtNum(p.en_cajas) }} en cajas</li>
      </ul>
    </div>
    <template #pie>
      <button class="btn" @click="modal = null">Cancelar</button>
      <button class="btn btn-peligro" :disabled="ocupado" @click="eliminar(!!modal.impacto)">
        {{ modal.impacto ? 'Quitar también de los packing lists' : 'Quitar líneas' }}
      </button>
    </template>
  </Modal>

  <Modal v-if="modal?.tipo === 'pendientes'" :titulo="modal.titulo" ancho="640px" @cerrar="modal = null">
    <ul class="lista-mensajes"><li v-for="(d, i) in modal.detalle" :key="i">{{ textoDetalle(d) }}</li></ul>
    <template #pie><button class="btn btn-primario" @click="modal = null">Entendido</button></template>
  </Modal>

  <Modal v-if="modal?.tipo === 'estado'" :titulo="modal.accion === 'reabrir' ? 'Reabrir factura para corrección' : 'Cancelar factura'" @cerrar="modal = null">
    <p v-if="modal.accion === 'cancelar'">Sus packing lists también se cancelan y las cantidades vuelven a estar disponibles en las OCs.</p>
    <p v-else>La factura vuelve a ser editable. Sus packing lists mantienen su estado.</p>
    <label class="campo"><span>Motivo{{ modal.accion === 'cancelar' && f?.estado === 'BORRADOR' ? ' (opcional)' : '' }}</span><textarea v-model="modal.motivo"></textarea></label>
    <template #pie>
      <button class="btn" @click="modal = null">Volver</button>
      <button class="btn" :class="modal.accion === 'cancelar' ? 'btn-peligro' : 'btn-primario'" :disabled="ocupado" @click="cambiarEstado">
        {{ modal.accion === 'reabrir' ? 'Reabrir' : 'Cancelar factura' }}
      </button>
    </template>
  </Modal>
</template>
