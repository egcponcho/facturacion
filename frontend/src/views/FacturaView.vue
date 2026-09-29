<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api'
import BarraSeleccion from '../components/BarraSeleccion.vue'
import CeldaEditable from '../components/CeldaEditable.vue'
import EstadoBadge from '../components/EstadoBadge.vue'
import Icono from '../components/Icono.vue'
import Modal from '../components/Modal.vue'
import TarjetaParte from '../components/TarjetaParte.vue'
import ExplosionPrepack from '../components/ExplosionPrepack.vue'
import Paginacion from '../components/Paginacion.vue'
import Pasos from '../components/Pasos.vue'
import ThOrden from '../components/ThOrden.vue'
import { useTabla } from '../composables/useTabla'
import { elegirProveedor, esInterno } from '../stores/sesion'
import { avisar, errorApi, guardando, textoDetalle } from '../stores/ui'
import {
  ACCIONES, fmtFecha, fmtFechaHora, fmtFechaHoraLocal, fmtMoneda, fmtNum, pct, plural, porUnidadTxt, useSeleccion,
} from '../utils'

const props = defineProps({ id: String })
const route = useRoute()
const router = useRouter()

const f = ref(null)
const tab = ref(['lineas', 'pl', 'archivos', 'historial'].includes(route.query.tab) ? route.query.tab : 'lineas')
const sel = useSeleccion()
const explosion = ref(null)
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
  if (!f.value) return []
  const q = filtro.value.trim().toLowerCase()
  if (!q) return f.value.lineas
  return f.value.lineas.filter((l) =>
    [l.codigo_sap, l.estilo, l.color, l.talla, l.oc_numero, l.upc, l.descripcion].some((v) => (v || '').toLowerCase().includes(q)))
})
const tablaLineas = useTabla(lineasFiltradas, { porPagina: 25, valores: { oc: (l) => `${l.oc_numero}-${String(l.posicion).padStart(5, '0')}` } })
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
  ['lineas', 'Líneas', 'lista'],
  ['pl', 'Packing lists', 'caja'],
  ['archivos', 'Archivos', 'archivo'],
  ['historial', 'Historial', 'historial'],
]

// ---- Avance del documento ---------------------------------------------------
const pendLineas = computed(() => (f.value?.pendientes || []).filter((p) => p.linea_id))
const pendCabecera = computed(() => (f.value?.pendientes || []).filter((p) => !p.linea_id))
const sumaUnidades = (campo) => Object.values(f.value?.totales.por_unidad || {}).reduce((a, u) => a + u[campo], 0)
const pasos = computed(() => {
  const x = f.value
  if (!x) return []
  const fin = x.estado === 'FINALIZADA'
  const facturado = sumaUnidades('facturado')
  const enPl = sumaUnidades('en_pl')
  const empacado = sumaUnidades('empacado')
  const plFin = plsActivos.value.filter((p) => p.estado === 'FINALIZADO').length
  const empaqueListo = facturado > 0 && empacado === facturado && plFin === plsActivos.value.length
  const lineasOk = x.lineas.length > 0 && !pendLineas.value.length
  const datosOk = fin || !pendCabecera.value.some((p) => p.campo)
  const est = (ok, alerta, actual) => (ok ? 'hecho' : alerta ? 'alerta' : actual ? 'actual' : 'pendiente')
  return [
    { titulo: 'Líneas', estado: est(lineasOk || fin, pendLineas.value.length, true),
      detalle: pendLineas.value.length ? `${pendLineas.value.length} datos por completar` : `${x.lineas.length} líneas · ${fmtMoneda(x.totales.importe, x.moneda)}` },
    { titulo: 'Datos de la factura', estado: est(datosOk, false, lineasOk),
      detalle: datosOk ? `${x.numero || 'Sin número'} · ${fmtFecha(x.fecha)}` : 'Falta número o fecha' },
    { titulo: 'Empaque', estado: est(empaqueListo, false, lineasOk && facturado > 0),
      detalle: !facturado ? 'Sin líneas' : enPl < facturado ? `${pct(enPl, facturado)}% en packing lists` : `${pct(empacado, facturado)}% en cajas · ${plFin}/${plsActivos.value.length} PL finalizados` },
    { titulo: 'Finalizar', estado: est(fin, x.estado === 'EN_CORRECCION', lineasOk && datosOk),
      detalle: fin ? `El ${fmtFecha(x.finalizado_en)}` : x.estado === 'EN_CORRECCION' ? 'Reabierta para corregir' : x.estado === 'CANCELADA' ? 'Cancelada' : 'Pendiente' },
    { titulo: 'Embarque', estado: est(plsActivos.value.length > 0 && confirmados.value === plsActivos.value.length, false, fin),
      detalle: plsActivos.value.length ? `${confirmados.value} de ${plsActivos.value.length} PL confirmados` : 'Sin packing lists' },
  ]
})
const sinAsignar = computed(() => (f.value?.lineas || []).reduce((a, l) => a + Math.max(l.sin_asignar, 0), 0))
const accionPrincipal = computed(() => {
  const x = f.value
  if (!x || x.estado === 'CANCELADA') return null
  if (x.estado !== 'FINALIZADA' && x.lineas.length && sinAsignar.value > 0) return 'empacar'
  if (x.puede.finalizar) return 'finalizar'
  return null
})

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
function abrirFinalizar() {
  modal.value = { tipo: 'finalizar', incluir: plEditables.value }
}

async function finalizar(incluir) {
  ocupado.value = true
  try {
    await api.post(`/facturas/${props.id}/finalizar`, { version: f.value.version, incluir_packing_lists: incluir })
    avisar(incluir ? 'Factura y packing lists finalizados.' : 'Factura finalizada.')
    modal.value = null
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

// Un solo botón para empacar: crea el packing list con todo lo pendiente o
// suma lo pendiente al único PL abierto, y lo abre.
async function empacar() {
  const abiertos = plsActivos.value.filter((p) => ['BORRADOR', 'EN_CORRECCION'].includes(p.estado))
  if (!sinAsignar.value) {
    const destino = abiertos[0]
    if (destino) router.push(`/packing-lists/${destino.id}`)
    else tab.value = 'pl'
    return
  }
  ocupado.value = true
  try {
    if (abiertos.length === 1) {
      const r = await api.post(`/packing-lists/${abiertos[0].id}/agregar`, { version: abiertos[0].version })
      avisar(`Se agregaron ${fmtNum(r.agregado)} a ${abiertos[0].numero}.`)
      router.push(`/packing-lists/${abiertos[0].id}`)
    } else {
      const r = await api.post(`/facturas/${props.id}/packing-lists`, { lineas: null })
      avisar(`Se creó ${r.numero} con todo lo pendiente.`)
      router.push(`/packing-lists/${r.id}`)
    }
  } catch (e) {
    trasError(e)
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
    <router-link to="/facturas" class="volver"><Icono nombre="atras" :tam="15" />Facturas</router-link>
    <section class="doc-cabeza">
      <div class="doc-fila">
        <span class="doc-numero">{{ f.nombre }}</span>
        <EstadoBadge :estado="f.estado" />
        <span v-if="f.lista_transporte && confirmados < plsActivos.length" class="etiqueta ok"><Icono nombre="check" :tam="12" />Lista para embarcar</span>
        <div class="doc-acciones">
          <button class="btn btn-fantasma" title="Descargar Excel" @click="descargar(`/facturas/${f.id}/exportar`, 'factura.xlsx')"><Icono nombre="descargar" />Excel</button>
          <button v-if="f.puede.reabrir" class="btn" @click="modal = { tipo: 'estado', accion: 'reabrir', motivo: '' }">Reabrir para corregir</button>
          <button v-if="f.puede.cancelar" class="btn btn-peligro" @click="modal = { tipo: 'estado', accion: 'cancelar', motivo: '' }">Cancelar</button>
          <button v-if="f.puede.finalizar" :class="['btn', accionPrincipal === 'finalizar' ? 'btn-primario' : '']" :disabled="ocupado" @click="abrirFinalizar">
            <Icono nombre="check" />Finalizar
          </button>
          <button v-if="accionPrincipal === 'empacar'" class="btn btn-primario" :disabled="ocupado" @click="empacar">
            <Icono nombre="caja" />Empacar {{ fmtNum(sinAsignar) }} pendientes
          </button>
        </div>
      </div>
      <div class="doc-meta">
        <span>Proveedor <b>{{ f.proveedor }}</b></span>
        <span>Sociedad / centro <b>{{ f.sociedad }} / {{ f.centro || '—' }}</b></span>
        <span>Cantidad <b>{{ porUnidadTxt(f.totales.por_unidad, 'facturado') }}</b></span>
        <span>Importe <b>{{ fmtMoneda(f.totales.importe, f.moneda) }}</b></span>
      </div>
      <div class="doc-datos">
        <label class="dato"><span class="req">Número de factura</span>
          <CeldaEditable v-if="editable" :valor="f.numero" :guardar="guardarCabecera('numero')" etiqueta="Número de factura" vacia-texto="Obligatorio" />
          <b v-else>{{ f.numero || '—' }}</b>
        </label>
        <label class="dato"><span class="req">Fecha</span>
          <CeldaEditable v-if="editable" tipo="date" :valor="f.fecha" :guardar="guardarCabecera('fecha')" etiqueta="Fecha" vacia-texto="Obligatorio" />
          <b v-else>{{ fmtFecha(f.fecha) }}</b>
        </label>
        <label class="dato"><span class="req">Incoterm</span>
          <CeldaEditable v-if="editable" :valor="f.incoterm" :guardar="guardarCabecera('incoterm')" etiqueta="Incoterm" vacia-texto="Obligatorio" />
          <b v-else>{{ f.incoterm || '—' }}</b>
        </label>
        <label class="dato"><span>Condiciones de pago</span>
          <CeldaEditable v-if="editable" :valor="f.condiciones" :guardar="guardarCabecera('condiciones')" etiqueta="Condiciones" />
          <b v-else>{{ f.condiciones || '—' }}</b>
        </label>
        <label class="dato" style="grid-column: span 2"><span>Observaciones</span>
          <CeldaEditable v-if="editable" :valor="f.observaciones" :guardar="guardarCabecera('observaciones')" etiqueta="Observaciones" />
          <b v-else>{{ f.observaciones || '—' }}</b>
        </label>
      </div>
      <Pasos :pasos="pasos" />
    </section>

    <div v-if="f" class="partes" style="margin-bottom: 16px">
      <TarjetaParte titulo="Facturar a" icono="factura" :parte="f.facturar_a" />
      <TarjetaParte titulo="Notify party (centro que recibe)" icono="ubicacion" :parte="f.notify" />
      <section v-if="f.destino" class="panel tarjeta-parte">
        <div class="tp-cabeza">
          <span class="tp-icono"><Icono nombre="ruta" :tam="16" /></span>
          <div><span class="eyebrow">Destino final</span><b>{{ f.destino.codigo }} · {{ f.destino.nombre || 'Centro no registrado' }}</b></div>
        </div>
        <p class="tp-linea">País de llegada: <b>{{ f.destino.pais || '—' }}</b></p>
      </section>
    </div>

    <div class="pestanas" role="tablist">
      <button v-for="[clave, texto, icono] in TABS" :key="clave" class="pestana" role="tab" :aria-selected="tab === clave" @click="tab = clave">
        <Icono :nombre="icono" :tam="16" />{{ texto }}
        <span v-if="clave === 'lineas'" class="cuenta" :class="{ alerta: pendLineas.length }">{{ f.lineas.length }}</span>
        <span v-if="clave === 'pl'" class="cuenta">{{ plsActivos.length }}</span>
      </button>
    </div>

    <!-- Líneas -->
    <section v-if="tab === 'lineas'">
      <p v-if="pendLineas.length && editable" class="nota aviso bloque" style="margin-bottom: 12px">
        Faltan {{ pendLineas.length }} datos en las líneas para poder finalizar (celdas marcadas “Falta”).
        <button class="btn-texto" @click="modal = { tipo: 'pendientes', titulo: 'Datos pendientes para finalizar', detalle: f.pendientes }">Ver cuáles</button>
      </p>
      <div class="filtros">
        <label class="buscador">
          <Icono nombre="buscar" :tam="16" />
          <input v-model="filtro" type="search" placeholder="Filtrar por código, estilo, color, talla u OC" aria-label="Filtrar líneas" />
        </label>
        <span class="leyenda-req separar">Obligatorio en la factura comercial</span>
        <button v-if="editable" class="btn" @click="agregarDesdeOC"><Icono nombre="mas" />Agregar desde OCs</button>
      </div>
      <div class="tabla-marco tabla-fija">
        <table class="tabla">
          <thead>
            <tr>
              <th class="chk"><input type="checkbox" aria-label="Seleccionar todas las líneas filtradas" :checked="sel.todos(idsFiltrados)" @change="sel.alternarTodos(idsFiltrados)" /></th>
              <ThOrden campo="oc" :orden="tablaLineas.estado.orden" @ordenar="tablaLineas.ordenar">OC / pos.</ThOrden>
              <ThOrden campo="estilo" :orden="tablaLineas.estado.orden" @ordenar="tablaLineas.ordenar">Producto</ThOrden>
              <ThOrden campo="talla" :orden="tablaLineas.estado.orden" @ordenar="tablaLineas.ordenar">Talla</ThOrden>
              <ThOrden campo="cantidad" :orden="tablaLineas.estado.orden" num @ordenar="tablaLineas.ordenar"><span class="req">Cantidad</span></ThOrden>
              <th>UM</th>
              <ThOrden campo="precio_unitario" :orden="tablaLineas.estado.orden" num @ordenar="tablaLineas.ordenar"><span class="req">Precio unitario</span></ThOrden>
              <ThOrden campo="total" :orden="tablaLineas.estado.orden" num @ordenar="tablaLineas.ordenar">Total</ThOrden>
              <ThOrden campo="sin_asignar" :orden="tablaLineas.estado.orden" num @ordenar="tablaLineas.ordenar">En packing list</ThOrden>
              <ThOrden campo="pais_origen" :orden="tablaLineas.estado.orden" @ordenar="tablaLineas.ordenar"><span class="req">País origen</span></ThOrden>
              <th><span class="req">Partida</span></th>
              <th><span class="req">Descripción comercial</span></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="l in tablaLineas.filas.value" :key="l.id" :class="{ seleccionada: sel.tiene(l.id) }">
              <td class="chk"><input type="checkbox" :aria-label="`Seleccionar ${l.codigo_sap} talla ${l.talla}`" :checked="sel.tiene(l.id)" @change="sel.alternar(l.id)" /></td>
              <td class="codigo">{{ l.oc_numero }} / {{ l.posicion }}<span v-if="l.almacen" class="sub">almacén {{ l.almacen }}</span></td>
              <td>
                <span v-if="l.marca" class="fuerte">{{ l.marca }}</span> {{ l.estilo }} · {{ l.color }}
                <button v-if="l.tipo_empaque === 'PREPACK'" type="button" class="etiqueta acento btn-explosion" title="Ver la explosión del prepack"
                        @click="explosion = { sku: l.codigo_sap, cajas: l.cantidad }">Prepack {{ l.prepack }} <Icono nombre="lupa" :tam="12" /></button>
                <span v-else-if="l.casepack" class="etiqueta info">Casepack {{ l.casepack }}</span>
                <span class="sub codigo">{{ l.codigo_sap }}</span>
              </td>
              <td><strong>{{ l.talla }}</strong></td>
              <td class="num" style="width: 100px">
                <CeldaEditable v-if="editable" tipo="number" :min="1" paso="1" :valor="l.cantidad" :guardar="celda(l, 'cantidad')" :etiqueta="`Cantidad de ${l.codigo_sap}`" />
                <template v-else>{{ fmtNum(l.cantidad) }}</template>
              </td>
              <td><span class="etiqueta" style="margin-left: 0">{{ l.unidad }}</span></td>
              <td class="num" style="width: 130px">
                <CeldaEditable v-if="editable" tipo="number" :min="0" paso="0.0001" :valor="l.precio_unitario" :guardar="celda(l, 'precio_unitario')" :etiqueta="`Precio de ${l.codigo_sap}`" />
                <template v-else>{{ fmtNum(l.precio_unitario, 2) }}</template>
                <span v-if="Math.abs(l.precio_unitario - l.precio_oc) > 1e-9" class="etiqueta aviso" :title="`Precio OC ${l.precio_oc}. Motivo: ${l.motivo_precio || 'sin indicar'}`">Distinto a OC</span>
              </td>
              <td class="num">{{ fmtNum(l.total, 2) }}</td>
              <td class="num">
                {{ fmtNum(l.en_pl) }}
                <span v-if="l.sin_asignar > 0" class="etiqueta aviso">{{ fmtNum(l.sin_asignar) }} sin PL</span>
                <span class="sub">{{ fmtNum(l.empacado) }} en cajas</span>
              </td>
              <td style="width: 84px">
                <CeldaEditable v-if="editable" :valor="l.pais_origen" :guardar="celda(l, 'pais_origen')" vacia-texto="Falta" :etiqueta="`País de origen de ${l.codigo_sap}`" />
                <template v-else>{{ l.pais_origen }}</template>
              </td>
              <td style="width: 110px">
                <CeldaEditable v-if="editable" :valor="l.partida_arancelaria" :guardar="celda(l, 'partida_arancelaria')" vacia-texto="Falta" :etiqueta="`Partida de ${l.codigo_sap}`" />
                <template v-else>{{ l.partida_arancelaria }}</template>
              </td>
              <td class="envolver">
                <CeldaEditable v-if="editable" :valor="l.descripcion_comercial" :guardar="celda(l, 'descripcion_comercial')" vacia-texto="Falta" :etiqueta="`Descripción de ${l.codigo_sap}`" />
                <template v-else>{{ l.descripcion_comercial }}</template>
              </td>
            </tr>
            <tr v-if="!lineasFiltradas.length">
              <td colspan="12" class="vacio">
                {{ f.lineas.length ? 'Ninguna línea coincide con el filtro.' : 'La factura no tiene líneas.' }}
                <div v-if="editable && !f.lineas.length"><button class="btn" @click="agregarDesdeOC">Agregar posiciones desde OCs</button></div>
              </td>
            </tr>
          </tbody>
          <tfoot v-if="f.lineas.length">
            <tr>
              <td></td>
              <td colspan="3">{{ lineasFiltradas.length }} de {{ f.lineas.length }} líneas</td>
              <td class="num" colspan="3">{{ porUnidadTxt(f.totales.por_unidad, 'facturado') }}</td>
              <td class="num">{{ fmtMoneda(f.totales.importe, f.moneda) }}</td>
              <td colspan="4"></td>
            </tr>
          </tfoot>
        </table>
      </div>
      <Paginacion :page="tablaLineas.estado.pagina" :size="tablaLineas.estado.porPagina" :total="tablaLineas.total.value"
                  @cambiar="(p) => (tablaLineas.estado.pagina = p)" @tamano="(t) => (tablaLineas.estado.porPagina = t)" />
      <BarraSeleccion :cantidad="sel.ids.size" singular="línea seleccionada" plural="líneas seleccionadas" @limpiar="sel.limpiar()">
        <template #resumen>{{ resumenSeleccion }}</template>
        <button v-if="editable" class="btn" @click="abrirMasivo"><Icono nombre="editar" :tam="15" />Cambiar un dato</button>
        <button class="btn" :disabled="ocupado || f.estado === 'CANCELADA' || !seleccion.some((l) => l.sin_asignar > 0)" title="Crea un packing list aparte solo con estas líneas" @click="crearPL(true)"><Icono nombre="caja" :tam="15" />PL aparte con estas</button>
        <button v-if="editable" class="btn btn-peligro" @click="modal = { tipo: 'eliminar', mensaje: `¿Quitar ${sel.ids.size} líneas de la factura? Sus cantidades vuelven a estar disponibles en las OCs.` }">
          <Icono nombre="basura" :tam="15" />Quitar
        </button>
      </BarraSeleccion>
    </section>

    <!-- Packing lists y transporte -->
    <section v-if="tab === 'pl'">
      <div class="fila-flex" style="margin-bottom: 14px">
        <button v-if="f.puede.crear_pl" class="btn btn-primario" :disabled="ocupado" @click="empacar"><Icono nombre="caja" />Empacar {{ porUnidadTxt(pendientePorUnidad, null) }} pendientes</button>
        <span v-else-if="f.lineas.length" class="nota ok" style="padding: 6px 12px"><Icono nombre="check" />Toda la mercancía ya está en packing lists.</span>
        <span class="ayuda">Casi siempre basta un packing list por factura. Para dividir el envío usa “Mover” dentro del PL.</span>
      </div>
      <div class="tabla-marco">
        <table class="tabla">
          <thead>
            <tr>
              <th>Packing list</th>
              <th>Estado</th>
              <th>Contenido</th>
              <th>Empaque</th>
              <th class="num">Peso bruto</th>
              <th class="num">Volumen</th>
              <th>Contenedor</th>
              <th>Embarque</th>
              <th>ETA</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="p in f.packing_lists" :key="p.id" class="clicable" :class="{ apagado: p.estado === 'CANCELADO' }" @click="router.push(`/packing-lists/${p.id}`)">
              <td><router-link :to="`/packing-lists/${p.id}`" class="cajas-rango" @click.stop>{{ p.numero }}</router-link></td>
              <td><EstadoBadge :estado="p.estado" /></td>
              <td>{{ porUnidadTxt(p.totales.por_unidad, 'cantidad') }}<span class="sub">{{ plural(p.totales.cajas, 'caja', 'cajas') }}</span></td>
              <td style="min-width: 140px">
                <span v-if="Object.values(p.totales.por_unidad).some((u) => u.sin_caja)" class="etiqueta error">{{ porUnidadTxt(p.totales.por_unidad, 'sin_caja') }} sin caja</span>
                <span v-else-if="p.totales.cajas" class="etiqueta ok"><Icono nombre="check" :tam="12" />Todo en cajas</span>
                <span v-else class="apagado">—</span>
              </td>
              <td class="num">{{ fmtNum(p.totales.peso_bruto, 1) }} kg</td>
              <td class="num">{{ fmtNum(p.totales.cbm, 2) }} m³</td>
              <td>
                <template v-if="p.transporte">{{ p.transporte.unidad }} <EstadoBadge :estado="p.transporte.asignacion" /></template>
                <span v-else class="apagado">Sin asignar</span>
              </td>
              <td>
                <template v-if="p.transporte">
                  <router-link v-if="esInterno()" :to="`/transporte/embarques/${p.transporte.embarque_id}`" @click.stop>{{ p.transporte.embarque }}</router-link>
                  <template v-else>{{ p.transporte.embarque }}</template>
                  <EstadoBadge :estado="p.transporte.estado" />
                  <span class="sub">{{ p.transporte.documento ? `BL/AWB ${p.transporte.documento}` : 'BL/AWB pendiente' }}<template v-if="p.transporte.ultimo_evento"> · {{ p.transporte.ultimo_evento.tipo.toLowerCase() }} {{ fmtFechaHoraLocal(p.transporte.ultimo_evento.fecha) }}</template></span>
                </template>
                <span v-else class="apagado">—</span>
              </td>
              <td>
                <template v-if="p.transporte">{{ fmtFecha(p.transporte.arribo_real || p.transporte.eta) }}<span class="sub">{{ p.transporte.arribo_real ? 'arribó' : 'estimada' }}</span></template>
                <span v-else class="apagado">—</span>
              </td>
            </tr>
            <tr v-if="!f.packing_lists.length">
              <td colspan="9" class="vacio">
                <Icono nombre="caja" :tam="28" />
                <p>Todavía no hay packing lists. Con “Empacar” se crea uno con toda la mercancía de la factura.</p>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <!-- Archivos -->
    <section v-if="tab === 'archivos'" class="panel">
      <div class="panel-cabeza"><div><h2>Archivos</h2><p>Adjunta la factura oficial del proveedor (PDF) y otros soportes.</p></div></div>
      <div v-if="f.estado !== 'CANCELADA'" class="fila-flex">
        <input type="file" aria-label="Archivo" @change="subida.archivo = $event.target.files[0]" />
        <select v-model="subida.tipo" class="entrada" aria-label="Tipo de archivo">
          <option value="FACTURA_OFICIAL">Factura oficial</option>
          <option value="OTRO">Otro soporte</option>
        </select>
        <button class="btn btn-primario" :disabled="!subida.archivo" @click="subir"><Icono nombre="importar" />Adjuntar</button>
      </div>
      <div class="tabla-marco mt" style="box-shadow: none">
        <table class="tabla">
          <thead><tr><th>Archivo</th><th>Tipo</th><th class="num">Tamaño</th><th>Subido</th><th></th></tr></thead>
          <tbody>
            <tr v-for="a in archivos" :key="a.id">
              <td>{{ a.nombre }}</td>
              <td>{{ a.tipo === 'FACTURA_OFICIAL' ? 'Factura oficial' : 'Otro soporte' }}</td>
              <td class="num">{{ fmtNum(a.tamano / 1024, 0) }} KB</td>
              <td>{{ fmtFechaHora(a.subido_en) }}</td>
              <td class="num"><button class="btn btn-chico" @click="descargar(`/archivos/${a.id}`, a.nombre)"><Icono nombre="descargar" :tam="14" />Descargar</button></td>
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

  <Modal v-if="modal?.tipo === 'finalizar'" titulo="Finalizar factura" ancho="600px" @cerrar="modal = null">
    <ul class="checklist">
      <li :class="pendCabecera.length ? 'falta' : 'ok'">
        <span class="marca"><Icono :nombre="pendCabecera.length ? 'alerta' : 'check'" :tam="14" /></span>
        <span>Número, fecha y líneas<span class="sub ayuda">{{ pendCabecera.length ? pendCabecera.map((p) => p.mensaje).join(' ') : 'Completos' }}</span></span>
      </li>
      <li :class="pendLineas.length ? 'falta' : 'ok'">
        <span class="marca"><Icono :nombre="pendLineas.length ? 'alerta' : 'check'" :tam="14" /></span>
        <span>Datos de aduana y precios<span class="sub ayuda">{{ pendLineas.length ? `${pendLineas.length} por completar` : 'Completos' }}</span></span>
      </li>
      <li :class="sinAsignar ? 'falta' : 'ok'">
        <span class="marca"><Icono :nombre="sinAsignar ? 'alerta' : 'check'" :tam="14" /></span>
        <span>Todo en packing lists<span class="sub ayuda">{{ sinAsignar ? `${fmtNum(sinAsignar)} sin packing list (puedes finalizar la factura y empacar después)` : 'Sí' }}</span></span>
      </li>
    </ul>
    <label v-if="plEditables" class="check"><input v-model="modal.incluir" type="checkbox" /> Finalizar también sus packing lists abiertos</label>
    <p class="ayuda">Si falta algo, verás exactamente qué y no se finaliza nada.</p>
    <template #pie>
      <button class="btn" @click="modal = null">Volver</button>
      <button class="btn btn-primario" :disabled="ocupado || f.pendientes.length > 0" @click="finalizar(modal.incluir)"><Icono nombre="check" />Finalizar</button>
    </template>
  </Modal>

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
    <label class="campo"><span class="req">Motivo</span><textarea v-model="modal.motivo" placeholder="Por ejemplo: precio acordado por volumen"></textarea></label>
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
    <label class="campo"><span :class="{ req: !(modal.accion === 'cancelar' && f?.estado === 'BORRADOR') }">Motivo{{ modal.accion === 'cancelar' && f?.estado === 'BORRADOR' ? ' (opcional)' : '' }}</span><textarea v-model="modal.motivo"></textarea></label>
    <template #pie>
      <button class="btn" @click="modal = null">Volver</button>
      <button class="btn" :class="modal.accion === 'cancelar' ? 'btn-peligro' : 'btn-primario'" :disabled="ocupado" @click="cambiarEstado">
        {{ modal.accion === 'reabrir' ? 'Reabrir' : 'Cancelar factura' }}
      </button>
    </template>
  </Modal>
  <ExplosionPrepack v-if="explosion" :sku="explosion.sku" :cajas="explosion.cajas" @cerrar="explosion = null" />
</template>
