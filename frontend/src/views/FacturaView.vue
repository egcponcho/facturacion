<script setup>
import { t, tx } from '../i18n/index.js'
import { computed, onMounted, reactive, ref, watch } from 'vue'
import Seleccion from '../components/Seleccion.vue'
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
  ['lineas', t('Lines'), 'lista'],
  ['pl', t('Packing lists'), 'caja'],
  ['archivos', t('Files'), 'archivo'],
  ['historial', t('History'), 'historial'],
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
    { titulo: t('Lines'), estado: est(lineasOk || fin, pendLineas.value.length, true),
      detalle: pendLineas.value.length ? t('{0} fields to complete', [pendLineas.value.length]) : t('{0} lines · {1}', [x.lineas.length, fmtMoneda(x.totales.importe, x.moneda)]) },
    { titulo: t('Invoice data'), estado: est(datosOk, false, lineasOk),
      detalle: datosOk ? `${x.numero || t('No number')} · ${fmtFecha(x.fecha)}` : t('Number or date missing') },
    { titulo: t('Packing'), estado: est(empaqueListo, false, lineasOk && facturado > 0),
      detalle: !facturado ? t('No lines') : enPl < facturado ? t('{0}% in packing lists', [pct(enPl, facturado)]) : t('{0}% in cartons · {1}/{2} PL finalized', [pct(empacado, facturado), plFin, plsActivos.value.length]) },
    { titulo: t('Finalize'), estado: est(fin, x.estado === 'EN_CORRECCION', lineasOk && datosOk),
      detalle: fin ? t('On {0}', [fmtFecha(x.finalizado_en)]) : x.estado === 'EN_CORRECCION' ? t('Reopened for correction') : x.estado === 'CANCELADA' ? t('Cancelled') : t('Pending') },
    { titulo: t('Shipment'), estado: est(plsActivos.value.length > 0 && confirmados.value === plsActivos.value.length, false, fin),
      detalle: plsActivos.value.length ? t('{0} of {1} PL confirmed', [confirmados.value, plsActivos.value.length]) : t('No packing lists') },
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
  ['precio_unitario', t('Unit price'), 'number'],
  ['cantidad', t('Quantity'), 'number'],
  ['pais_origen', t('Country of origin'), 'text'],
  ['descripcion_comercial', t('Commercial description'), 'text'],
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
  if (!ok) throw new Error(t('Not saved'))
}

function abrirMasivo() {
  modal.value = { tipo: 'masivo', campo: 'precio_unitario', valor: '', motivo: '' }
}

function aplicarMasivo() {
  const { campo, valor, motivo } = modal.value
  const tipo = CAMPOS_MASIVOS.find((c) => c[0] === campo)[2]
  const v = tipo === 'number' ? Number(valor) : valor
  if (tipo === 'number' && (valor === '' || Number.isNaN(v))) return avisar(t('Enter a valid number.'), 'error')
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
    avisar(t('{0} removed; their quantities are available again on the POs.', [plural(ids.length, t('line'), t('lines'))]))
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
    avisar(incluir ? t('Invoice and packing lists finalized.') : t('Invoice finalized.'))
    modal.value = null
    await cargar()
  } catch (e) {
    if (e.codigo === 'pendientes' || e.detalle?.some((d) => d.codigo === 'sin_clasificar')) modal.value = { tipo: 'pendientes', titulo: t('Pending data to finalize'), detalle: e.detalle }
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
    avisar(accion === 'reabrir' ? t('Invoice reopened for correction.') : t('Invoice cancelled; its quantities went back to the POs.'))
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
    avisar(t('{0} created with the pending quantities.', [r.numero]))
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
      avisar(t('{0} added to {1}.', [fmtNum(r.agregado), abiertos[0].numero]))
      router.push(`/packing-lists/${abiertos[0].id}`)
    } else {
      const r = await api.post(`/facturas/${props.id}/packing-lists`, { lineas: null })
      avisar(t('{0} created with everything pending.', [r.numero]))
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
    avisar(t('File attached.'))
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
    if (Array.isArray(v) && v.length === 2 && typeof v[0] !== 'object') return t('{0} to {1}', [v[0] ?? '—', v[1] ?? '—'])
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
    <router-link to="/facturas" class="volver"><Icono nombre="atras" :tam="15" />{{ t('Invoices') }}</router-link>
    <section class="doc-cabeza">
      <div class="doc-fila">
        <span class="doc-numero">{{ tx(f.nombre) }}</span>
        <EstadoBadge :estado="f.estado" />
        <span v-if="f.lista_transporte && confirmados < plsActivos.length" class="etiqueta ok"><Icono nombre="check" :tam="12" />{{ t('Ready to ship') }}</span>
        <div class="doc-acciones">
          <button class="btn btn-fantasma" :title="t('Commercial invoice as PDF, ready to print and sign')" @click="descargar(`/facturas/${f.id}/exportar?formato=pdf`, 'invoice.pdf')"><Icono nombre="descargar" />PDF</button>
          <button class="btn btn-fantasma" :title="t('Commercial invoice as Excel')" @click="descargar(`/facturas/${f.id}/exportar?formato=xlsx`, 'invoice.xlsx')"><Icono nombre="descargar" />{{ t('Excel') }}</button>
          <button v-if="f.puede.reabrir" class="btn" @click="modal = { tipo: 'estado', accion: 'reabrir', motivo: '' }">{{ t('Reopen to correct') }}</button>
          <button v-if="f.puede.cancelar" class="btn btn-peligro" @click="modal = { tipo: 'estado', accion: 'cancelar', motivo: '' }">{{ t('Cancel invoice') }}</button>
          <button v-if="f.puede.finalizar" :class="['btn', accionPrincipal === 'finalizar' ? 'btn-primario' : '']" :disabled="ocupado" @click="abrirFinalizar">
            <Icono nombre="check" />{{ t('Finalize') }}
          </button>
          <button v-if="accionPrincipal === 'empacar'" class="btn btn-primario" :disabled="ocupado" @click="empacar">
            <Icono nombre="caja" />{{ t('Pack {0} pending', [fmtNum(sinAsignar)]) }}
          </button>
        </div>
      </div>
      <div class="doc-meta">
        <span>{{ t('Supplier') }} <b>{{ tx(f.proveedor) }}</b></span>
        <span>{{ t('Company / plant') }} <b>{{ tx(f.sociedad) }} / {{ tx(f.centro || '—') }}</b></span>
        <span>{{ t('Quantity') }} <b>{{ porUnidadTxt(f.totales.por_unidad, 'facturado') }}</b></span>
        <span>{{ t('Amount') }} <b>{{ fmtMoneda(f.totales.importe, f.moneda) }}</b></span>
      </div>
      <div class="doc-datos">
        <label class="dato"><span class="req">{{ t('Invoice number') }}</span>
          <CeldaEditable v-if="editable" :valor="f.numero" :guardar="guardarCabecera('numero')" :etiqueta="t('Invoice number')" :vacia-texto="t('Required')" />
          <b v-else>{{ tx(f.numero || '—') }}</b>
        </label>
        <label class="dato"><span class="req">{{ t('Date') }}</span>
          <CeldaEditable v-if="editable" tipo="date" :valor="f.fecha" :guardar="guardarCabecera('fecha')" :etiqueta="t('Date')" :vacia-texto="t('Required')" />
          <b v-else>{{ fmtFecha(f.fecha) }}</b>
        </label>
        <label class="dato"><span class="req">{{ t('Incoterm') }}</span>
          <CeldaEditable v-if="editable" :valor="f.incoterm" :guardar="guardarCabecera('incoterm')" :etiqueta="t('Incoterm')" :vacia-texto="t('Required')" />
          <b v-else>{{ tx(f.incoterm || '—') }}</b>
        </label>
        <label class="dato"><span>{{ t('Payment terms') }}</span>
          <CeldaEditable v-if="editable" :valor="f.condiciones" :guardar="guardarCabecera('condiciones')" :etiqueta="t('Payment terms')" />
          <b v-else>{{ tx(f.condiciones || '—') }}</b>
        </label>
        <label class="dato" style="grid-column: span 2"><span>{{ t('Remarks') }}</span>
          <CeldaEditable v-if="editable" :valor="f.observaciones" :guardar="guardarCabecera('observaciones')" :etiqueta="t('Remarks')" />
          <b v-else>{{ tx(f.observaciones || '—') }}</b>
        </label>
      </div>
      <Pasos :pasos="pasos" />
    </section>

    <div v-if="f" class="partes" style="margin-bottom: 16px">
      <TarjetaParte :titulo="t('Bill to')" icono="factura" :parte="f.facturar_a" />
      <TarjetaParte :titulo="t('Notify party (receiving plant)')" icono="ubicacion" :parte="f.notify" />
      <section v-if="f.destino" class="panel tarjeta-parte">
        <div class="tp-cabeza">
          <span class="tp-icono"><Icono nombre="ruta" :tam="16" /></span>
          <div><span class="eyebrow">{{ t('Final destination') }}</span><b>{{ tx(f.destino.codigo) }} · {{ tx(f.destino.nombre || t('Plant not registered')) }}</b></div>
        </div>
        <p class="tp-linea">{{ t('Country of arrival:') }} <b>{{ tx(f.destino.pais || '—') }}</b></p>
      </section>
    </div>

    <div class="pestanas" role="tablist">
      <button v-for="[clave, texto, icono] in TABS" :key="clave" class="pestana" role="tab" :aria-selected="tab === clave" @click="tab = clave">
        <Icono :nombre="icono" :tam="16" />{{ tx(texto) }}
        <span v-if="clave === 'lineas'" class="cuenta" :class="{ alerta: pendLineas.length }">{{ tx(f.lineas.length) }}</span>
        <span v-if="clave === 'pl'" class="cuenta">{{ tx(plsActivos.length) }}</span>
      </button>
    </div>

    <!-- Lines -->
    <section v-if="tab === 'lineas'">
      <p v-if="pendLineas.length && editable" class="nota aviso bloque" style="margin-bottom: 12px">
        {{ t('{0} fields are missing on the lines before you can finalize (cells marked “Missing”).', [pendLineas.length]) }}
        <button class="btn-texto" @click="modal = { tipo: 'pendientes', titulo: t('Pending data to finalize'), detalle: f.pendientes }">{{ t('See which') }}</button>
      </p>
      <div class="filtros">
        <label class="buscador">
          <Icono nombre="buscar" :tam="16" />
          <input v-model="filtro" type="search" :placeholder="t('Filter by code, style, color, size or PO')" :aria-label="t('Filter lines')" />
        </label>
        <span class="leyenda-req separar">{{ t('Required on the commercial invoice') }}</span>
        <button v-if="editable" class="btn" @click="agregarDesdeOC"><Icono nombre="mas" />{{ t('Add from POs') }}</button>
      </div>
      <div class="tabla-marco tabla-fija">
        <table class="tabla">
          <thead>
            <tr>
              <th class="chk"><input type="checkbox" :aria-label="t('Select all filtered lines')" :checked="sel.todos(idsFiltrados)" @change="sel.alternarTodos(idsFiltrados)" /></th>
              <ThOrden campo="oc" :orden="tablaLineas.estado.orden" @ordenar="tablaLineas.ordenar">{{ t('PO / line') }}</ThOrden>
              <ThOrden campo="estilo" :orden="tablaLineas.estado.orden" @ordenar="tablaLineas.ordenar">{{ t('Item') }}</ThOrden>
              <ThOrden campo="talla" :orden="tablaLineas.estado.orden" @ordenar="tablaLineas.ordenar">{{ t('Size') }}</ThOrden>
              <ThOrden campo="cantidad" :orden="tablaLineas.estado.orden" num @ordenar="tablaLineas.ordenar"><span class="req">{{ t('Quantity') }}</span></ThOrden>
              <th>{{ t('UoM') }}</th>
              <ThOrden campo="precio_unitario" :orden="tablaLineas.estado.orden" num @ordenar="tablaLineas.ordenar"><span class="req">{{ t('Unit price') }}</span></ThOrden>
              <ThOrden campo="total" :orden="tablaLineas.estado.orden" num @ordenar="tablaLineas.ordenar">{{ t('Total') }}</ThOrden>
              <ThOrden campo="sin_asignar" :orden="tablaLineas.estado.orden" num @ordenar="tablaLineas.ordenar">{{ t('In packing list') }}</ThOrden>
              <ThOrden campo="pais_origen" :orden="tablaLineas.estado.orden" @ordenar="tablaLineas.ordenar"><span class="req">{{ t('Country of origin') }}</span></ThOrden>
              <th><span class="req">{{ t('HS code') }}</span></th>
              <th><span class="req">{{ t('Commercial description') }}</span></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="l in tablaLineas.filas.value" :key="l.id" :class="{ seleccionada: sel.tiene(l.id) }">
              <td class="chk"><input type="checkbox" :aria-label="t('Select {0} size {1}', [l.codigo_sap, l.talla])" :checked="sel.tiene(l.id)" @change="sel.alternar(l.id)" /></td>
              <td class="codigo">{{ tx(l.oc_numero) }} / {{ tx(l.posicion) }}<span v-if="l.almacen" class="sub">{{ t('warehouse {0}', [l.almacen]) }}</span></td>
              <td>
                <span v-if="l.marca" class="fuerte">{{ tx(l.marca) }}</span> {{ tx(l.estilo) }} · {{ tx(l.color) }}
                <button v-if="l.tipo_empaque === 'PREPACK'" type="button" class="etiqueta acento btn-explosion" :title="t('See the prepack breakdown')"
                        @click="explosion = { sku: l.codigo_sap, cajas: l.cantidad }">{{ t('Prepack {0}', [l.prepack]) }} <Icono nombre="lupa" :tam="12" /></button>
                <span v-else-if="l.casepack" class="etiqueta info">{{ t('Casepack {0}', [l.casepack]) }}</span>
                <span v-if="l.inner_pack" class="etiqueta acento" :title="t('Inner packs of {0}: the quantity goes in whole inner packs', [l.inner_pack])">{{ t('Inner {0}', [l.inner_pack]) }}</span>
                <span class="sub codigo">{{ tx(l.codigo_sap) }}</span>
              </td>
              <td><strong>{{ tx(l.talla) }}</strong></td>
              <td class="num" style="width: 100px">
                <CeldaEditable v-if="editable" tipo="number" :min="l.inner_pack || 1" :paso="String(l.inner_pack || 1)" :valor="l.cantidad" :guardar="celda(l, 'cantidad')" :etiqueta="t('Quantity of {0}', [l.codigo_sap])" />
                <template v-else>{{ fmtNum(l.cantidad) }}</template>
              </td>
              <td><span class="etiqueta" style="margin-inline-start: 0">{{ tx(l.unidad) }}</span></td>
              <td class="num" style="width: 130px">
                <CeldaEditable v-if="editable" tipo="number" :min="0" paso="0.0001" :valor="l.precio_unitario" :guardar="celda(l, 'precio_unitario')" :etiqueta="t('Price of {0}', [l.codigo_sap])" />
                <template v-else>{{ fmtNum(l.precio_unitario, 2) }}</template>
                <span v-if="Math.abs(l.precio_unitario - l.precio_oc) > 1e-9" class="etiqueta aviso" :title="t('PO price {0}. Reason: {1}', [l.precio_oc, l.motivo_precio || t('not given')])">{{ t('Differs from PO') }}</span>
              </td>
              <td class="num">{{ fmtNum(l.total, 2) }}</td>
              <td class="num">
                {{ fmtNum(l.en_pl) }}
                <span v-if="l.sin_asignar > 0" class="etiqueta aviso">{{ t('{0} without PL', [fmtNum(l.sin_asignar)]) }}</span>
                <span class="sub">{{ t('{0} in cartons', [fmtNum(l.empacado)]) }}</span>
              </td>
              <td style="width: 84px">
                <CeldaEditable v-if="editable" :valor="l.pais_origen" :guardar="celda(l, 'pais_origen')" :vacia-texto="t('Missing')" :etiqueta="t('Country of origin of {0}', [l.codigo_sap])" />
                <template v-else>{{ tx(l.pais_origen) }}</template>
              </td>
              <td style="width: 110px">
                <router-link v-if="l.producto_id" :to="`/productos/${l.producto_id}`" class="enlace" :title="t('From the approved technical sheet of the product')">
                  <span v-if="l.partida_arancelaria" class="codigo-sac">{{ tx(l.partida_arancelaria) }}</span>
                  <span v-else class="etiqueta aviso" style="margin-inline-start: 0">{{ t('Not classified') }}</span>
                </router-link>
                <span v-else class="codigo-sac">{{ tx(l.partida_arancelaria || '—') }}</span>
              </td>
              <td class="envolver">
                <CeldaEditable v-if="editable" :valor="l.descripcion_comercial" :guardar="celda(l, 'descripcion_comercial')" :vacia-texto="t('Missing')" :etiqueta="t('Description of {0}', [l.codigo_sap])" />
                <template v-else>{{ tx(l.descripcion_comercial) }}</template>
              </td>
            </tr>
            <tr v-if="!lineasFiltradas.length">
              <td colspan="12" class="vacio">
                {{ tx(f.lineas.length ? t('No line matches the filter.') : t('The invoice has no lines.')) }}
                <div v-if="editable && !f.lineas.length"><button class="btn" @click="agregarDesdeOC">{{ t('Add lines from POs') }}</button></div>
              </td>
            </tr>
          </tbody>
          <tfoot v-if="f.lineas.length">
            <tr>
              <td></td>
              <td colspan="3">{{ t('{0} of {1} lines', [lineasFiltradas.length, f.lineas.length]) }}</td>
              <td class="num" colspan="3">{{ porUnidadTxt(f.totales.por_unidad, 'facturado') }}</td>
              <td class="num">{{ fmtMoneda(f.totales.importe, f.moneda) }}</td>
              <td colspan="4"></td>
            </tr>
          </tfoot>
        </table>
      </div>
      <Paginacion :page="tablaLineas.estado.pagina" :size="tablaLineas.estado.porPagina" :total="tablaLineas.total.value"
                  @cambiar="(p) => (tablaLineas.estado.pagina = p)" @tamano="(t) => (tablaLineas.estado.porPagina = t)" />
      <BarraSeleccion :cantidad="sel.ids.size" :singular="t('line selected')" :plural="t('lines selected')" @limpiar="sel.limpiar()">
        <template #resumen>{{ tx(resumenSeleccion) }}</template>
        <button v-if="editable" class="btn" @click="abrirMasivo"><Icono nombre="editar" :tam="15" />{{ t('Change a field') }}</button>
        <button class="btn" :disabled="ocupado || f.estado === 'CANCELADA' || !seleccion.some((l) => l.sin_asignar > 0)" :title="t('Creates a separate packing list with only these lines')" @click="crearPL(true)"><Icono nombre="caja" :tam="15" />{{ t('Separate PL with these') }}</button>
        <button v-if="editable" class="btn btn-peligro" @click="modal = { tipo: 'eliminar', mensaje: t('Remove {0} lines from the invoice? Their quantities become available again on the POs.', [sel.ids.size]) }">
          <Icono nombre="basura" :tam="15" />{{ t('Remove') }}
        </button>
      </BarraSeleccion>
    </section>

    <!-- Packing lists and transport -->
    <section v-if="tab === 'pl'">
      <div class="fila-flex" style="margin-bottom: 14px">
        <button v-if="f.puede.crear_pl" class="btn btn-primario" :disabled="ocupado" @click="empacar"><Icono nombre="caja" />{{ t('Pack {0} pending', [porUnidadTxt(pendientePorUnidad, null)]) }}</button>
        <span v-else-if="f.lineas.length" class="nota ok" style="padding: 6px 12px"><Icono nombre="check" />{{ t('All goods are already in packing lists.') }}</span>
        <span class="ayuda">{{ t('One packing list per invoice is usually enough. To split the shipment use “Move” inside the PL.') }}</span>
      </div>
      <div class="tabla-marco">
        <table class="tabla">
          <thead>
            <tr>
              <th>{{ t('Packing list') }}</th>
              <th>{{ t('Status') }}</th>
              <th>{{ t('Contents') }}</th>
              <th>{{ t('Packing') }}</th>
              <th class="num">{{ t('Gross weight') }}</th>
              <th class="num">{{ t('Volume') }}</th>
              <th>{{ t('Load unit') }}</th>
              <th>{{ t('Shipment') }}</th>
              <th>ETA</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="p in f.packing_lists" :key="p.id" class="clicable" :class="{ apagado: p.estado === 'CANCELADO' }" @click="router.push(`/packing-lists/${p.id}`)">
              <td><router-link :to="`/packing-lists/${p.id}`" class="cajas-rango" @click.stop>{{ tx(p.numero) }}</router-link></td>
              <td><EstadoBadge :estado="p.estado" /></td>
              <td>{{ porUnidadTxt(p.totales.por_unidad, 'cantidad') }}<span class="sub">{{ plural(p.totales.cajas, t('carton'), t('cartons')) }}</span></td>
              <td style="min-width: 140px">
                <span v-if="Object.values(p.totales.por_unidad).some((u) => u.sin_caja)" class="etiqueta error">{{ t('{0} not packed', [porUnidadTxt(p.totales.por_unidad, 'sin_caja')]) }}</span>
                <span v-else-if="p.totales.cajas" class="etiqueta ok"><Icono nombre="check" :tam="12" />{{ t('All in cartons') }}</span>
                <span v-else class="apagado">—</span>
              </td>
              <td class="num">{{ t('{0} kg', [fmtNum(p.totales.peso_bruto, 1)]) }}</td>
              <td class="num">{{ fmtNum(p.totales.cbm, 2) }} m³</td>
              <td>
                <template v-if="p.transporte">{{ tx(p.transporte.unidad) }} <EstadoBadge :estado="p.transporte.asignacion" /></template>
                <span v-else class="apagado">{{ t('Not assigned') }}</span>
              </td>
              <td>
                <template v-if="p.transporte">
                  <router-link v-if="esInterno()" :to="`/transporte/embarques/${p.transporte.embarque_id}`" @click.stop>{{ tx(p.transporte.embarque) }}</router-link>
                  <template v-else>{{ tx(p.transporte.embarque) }}</template>
                  <EstadoBadge :estado="p.transporte.estado" />
                  <span class="sub">{{ tx(p.transporte.documento ? t('B/L / AWB {0}', [p.transporte.documento]) : t('B/L / AWB pending')) }}<template v-if="p.transporte.ultimo_evento"> · {{ tx(p.transporte.ultimo_evento.tipo.toLowerCase()) }} {{ fmtFechaHoraLocal(p.transporte.ultimo_evento.fecha) }}</template></span>
                </template>
                <span v-else class="apagado">—</span>
              </td>
              <td>
                <template v-if="p.transporte">{{ fmtFecha(p.transporte.arribo_real || p.transporte.eta) }}<span class="sub">{{ tx(p.transporte.arribo_real ? 'arrived' : 'estimated') }}</span></template>
                <span v-else class="apagado">—</span>
              </td>
            </tr>
            <tr v-if="!f.packing_lists.length">
              <td colspan="9" class="vacio">
                <Icono nombre="caja" :tam="28" />
                <p>{{ t('No packing lists yet. “Pack” creates one with all the goods on the invoice.') }}</p>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <!-- Files -->
    <section v-if="tab === 'archivos'" class="panel">
      <div class="panel-cabeza"><div><h2>{{ t('Files') }}</h2><p>{{ t('Attach the supplier\'s official invoice (PDF) and other supporting documents.') }}</p></div></div>
      <div v-if="f.estado !== 'CANCELADA'" class="fila-flex">
        <input type="file" :aria-label="t('File')" @change="subida.archivo = $event.target.files[0]" />
        <Seleccion v-model="subida.tipo" class="entrada" :aria-label="t('File type')">
          <option value="FACTURA_OFICIAL">{{ t('Official invoice') }}</option>
          <option value="OTRO">{{ t('Other document') }}</option>
        </Seleccion>
        <button class="btn btn-primario" :disabled="!subida.archivo" @click="subir"><Icono nombre="importar" />{{ t('Attach') }}</button>
      </div>
      <div class="tabla-marco mt" style="box-shadow: none">
        <table class="tabla">
          <thead><tr><th>{{ t('File') }}</th><th>{{ t('Type') }}</th><th class="num">{{ t('Size') }}</th><th>{{ t('Uploaded') }}</th><th></th></tr></thead>
          <tbody>
            <tr v-for="a in archivos" :key="a.id">
              <td>{{ tx(a.nombre) }}</td>
              <td>{{ tx(a.tipo === 'FACTURA_OFICIAL' ? t('Official invoice') : t('Other document')) }}</td>
              <td class="num">{{ t('{0} KB', [fmtNum(a.tamano / 1024, 0)]) }}</td>
              <td>{{ fmtFechaHora(a.subido_en) }}</td>
              <td class="num"><button class="btn btn-chico" @click="descargar(`/archivos/${a.id}`, a.nombre)"><Icono nombre="descargar" :tam="14" />{{ t('Download') }}</button></td>
            </tr>
            <tr v-if="!archivos.length"><td colspan="5" class="vacio">{{ t('No attached files.') }}</td></tr>
          </tbody>
        </table>
      </div>
    </section>

    <!-- History -->
    <section v-if="tab === 'historial'" class="panel">
      <ul class="linea-tiempo">
        <li v-for="h in historial" :key="h.id">
          <span class="ayuda">{{ fmtFechaHora(h.fecha) }}<br />{{ tx(h.usuario) }}</span>
          <div>
            <b>{{ tx(ACCIONES[h.accion] || h.accion) }}</b>
            <span class="etiqueta">{{ tx(h.entidad === 'packing_list' ? t('Packing list') : t('Invoice')) }}</span>
            <div v-if="h.motivo">{{ t('Reason: {0}', [h.motivo]) }}</div>
            <div class="ayuda">{{ tx(resumenDetalle(h.detalle)) }}</div>
          </div>
        </li>
        <li v-if="!historial.length"><span></span><span class="ayuda">{{ t('No activity.') }}</span></li>
      </ul>
    </section>
  </template>

  <Modal v-if="modal?.tipo === 'finalizar'" :titulo="t('Finalize invoice')" ancho="600px" @cerrar="modal = null">
    <ul class="checklist">
      <li :class="pendCabecera.length ? 'falta' : 'ok'">
        <span class="marca"><Icono :nombre="pendCabecera.length ? 'alerta' : 'check'" :tam="14" /></span>
        <span>{{ t('Number, date and lines') }}<span class="sub ayuda">{{ tx(pendCabecera.length ? pendCabecera.map((p) => p.mensaje).join(' ') : t('Complete')) }}</span></span>
      </li>
      <li :class="pendLineas.length ? 'falta' : 'ok'">
        <span class="marca"><Icono :nombre="pendLineas.length ? 'alerta' : 'check'" :tam="14" /></span>
        <span>{{ t('Customs data and prices') }}<span class="sub ayuda">{{ tx(pendLineas.length ? t('{0} to complete', [pendLineas.length]) : t('Complete')) }}</span></span>
      </li>
      <li :class="sinAsignar ? 'falta' : 'ok'">
        <span class="marca"><Icono :nombre="sinAsignar ? 'alerta' : 'check'" :tam="14" /></span>
        <span>{{ t('All in packing lists') }}<span class="sub ayuda">{{ tx(sinAsignar ? t('{0} without packing list (you can finalize the invoice and pack later)', [fmtNum(sinAsignar)]) : t('Yes')) }}</span></span>
      </li>
    </ul>
    <label v-if="plEditables" class="check"><input v-model="modal.incluir" type="checkbox" /> {{ t('Also finalize its open packing lists') }}</label>
    <p class="ayuda">{{ t('If something is missing, you will see exactly what and nothing is finalized.') }}</p>
    <template #pie>
      <button class="btn" @click="modal = null">{{ t('Back') }}</button>
      <button class="btn btn-primario" :disabled="ocupado || f.pendientes.length > 0" @click="finalizar(modal.incluir)"><Icono nombre="check" />{{ t('Finalize') }}</button>
    </template>
  </Modal>

  <!-- Dialogs -->
  <Modal v-if="modal?.tipo === 'ajuste'" :titulo="t('That quantity is already in packing lists')" ancho="640px" @cerrar="modal = null">
    <p>{{ t('The new quantity is lower than what is already assigned. The difference has to be released from the PLs.') }}</p>
    <div v-for="d in modal.detalle" :key="d.linea_id" class="nota aviso">
      <b>{{ tx(d.ref) }}</b>{{ t(': new quantity {0}, in PL {1}. {2} must be released.', [fmtNum(d.cantidad_nueva), fmtNum(d.en_packing_lists), fmtNum(d.hay_que_liberar)]) }}
      <ul class="lista-mensajes">
        <li v-for="p in d.packing_lists" :key="p.pl_id">
          <router-link :to="`/packing-lists/${p.pl_id}`">{{ tx(p.numero) }}</router-link>{{ t(': {0}, of which {1} not packed', [fmtNum(p.cantidad), fmtNum(p.sin_caja)]) }}
        </li>
      </ul>
    </div>
    <p class="ayuda">{{ t('Automatic release only takes what is not in cartons, starting with the most recent PL. If that is not enough, unpack in the PL first.') }}</p>
    <template #pie>
      <button class="btn" @click="modal = null">{{ t('Cancel') }}</button>
      <button class="btn btn-primario" @click="enviarCambios(modal.cambios, 'automatico')">{{ t('Release what is not in cartons') }}</button>
    </template>
  </Modal>

  <Modal v-if="modal?.tipo === 'motivo_precio'" :titulo="t('Reason for the price change')" @cerrar="modal = null">
    <ul class="lista-mensajes"><li v-for="(m, i) in modal.lineas" :key="i">{{ tx(m) }}</li></ul>
    <label class="campo"><span class="req">{{ t('Reason') }}</span><textarea v-model="modal.motivo" :placeholder="t('For example: volume price agreed')"></textarea></label>
    <template #pie>
      <button class="btn" @click="modal = null">{{ t('Cancel') }}</button>
      <button class="btn btn-primario" :disabled="!modal.motivo.trim()" @click="enviarCambios(modal.cambios.map((c) => ({ ...c, motivo_precio: modal.motivo })))">{{ t('Save price') }}</button>
    </template>
  </Modal>

  <Modal v-if="modal?.tipo === 'masivo'" :titulo="t('Change a field on {0} lines', [sel.ids.size])" @cerrar="modal = null">
    <label class="campo"><span>{{ t('Field') }}</span>
      <Seleccion v-model="modal.campo">
        <option v-for="[c, txt] in CAMPOS_MASIVOS" :key="c" :value="c">{{ tx(txt) }}</option>
      </Seleccion>
    </label>
    <label class="campo"><span>{{ t('New value') }}</span>
      <input v-model="modal.valor" :type="CAMPOS_MASIVOS.find((c) => c[0] === modal.campo)[2]" step="any" />
    </label>
    <label v-if="modal.campo === 'precio_unitario'" class="campo"><span>{{ t('Reason (required if it differs from the PO price)') }}</span><textarea v-model="modal.motivo"></textarea></label>
    <p class="ayuda">{{ t('If any change cannot be applied, none is applied and you will see which lines prevent it.') }}</p>
    <template #pie>
      <button class="btn" @click="modal = null">{{ t('Cancel') }}</button>
      <button class="btn btn-primario" :disabled="modal.valor === ''" @click="aplicarMasivo">{{ t('Apply to {0} lines', [sel.ids.size]) }}</button>
    </template>
  </Modal>

  <Modal v-if="modal?.tipo === 'eliminar'" :titulo="t('Remove lines from the invoice')" ancho="620px" @cerrar="modal = null">
    <p>{{ tx(modal.mensaje) }}</p>
    <div v-for="d in modal.impacto || []" :key="d.linea_id" class="nota aviso">
      <b>{{ tx(d.ref) }}</b>
      <ul class="lista-mensajes">
        <li v-for="p in d.packing_lists" :key="p.numero">{{ t('{0}: {1}, {2} in cartons', [p.numero, fmtNum(p.cantidad), fmtNum(p.en_cajas)]) }}</li>
      </ul>
    </div>
    <template #pie>
      <button class="btn" @click="modal = null">{{ t('Cancel') }}</button>
      <button class="btn btn-peligro" :disabled="ocupado" @click="eliminar(!!modal.impacto)">
        {{ tx(modal.impacto ? t('Also remove from the packing lists') : t('Remove lines')) }}
      </button>
    </template>
  </Modal>

  <Modal v-if="modal?.tipo === 'pendientes'" :titulo="tx(modal.titulo)" ancho="640px" @cerrar="modal = null">
    <ul class="lista-mensajes">
      <li v-for="(d, i) in modal.detalle" :key="i">{{ tx(textoDetalle(d)) }}
        <router-link v-if="d.producto_id" :to="`/productos/${d.producto_id}`" class="enlace">{{ t('Open technical sheet') }}</router-link></li>
    </ul>
    <template #pie><button class="btn btn-primario" @click="modal = null">{{ t('Got it') }}</button></template>
  </Modal>

  <Modal v-if="modal?.tipo === 'estado'" :titulo="tx(modal.accion === 'reabrir' ? t('Reopen invoice for correction') : t('Cancel invoice'))" @cerrar="modal = null">
    <p v-if="modal.accion === 'cancelar'">{{ t('Its packing lists are cancelled too and the quantities become available again on the POs.') }}</p>
    <p v-else>{{ t('The invoice becomes editable again. Its packing lists keep their status.') }}</p>
    <label class="campo"><span :class="{ req: !(modal.accion === 'cancelar' && f?.estado === 'BORRADOR') }">{{ t('Reason{0}', [modal.accion === 'cancelar' && f?.estado === 'BORRADOR' ? t(' (optional)') : '']) }}</span><textarea v-model="modal.motivo"></textarea></label>
    <template #pie>
      <button class="btn" @click="modal = null">{{ t('Back') }}</button>
      <button class="btn" :class="modal.accion === 'cancelar' ? 'btn-peligro' : 'btn-primario'" :disabled="ocupado" @click="cambiarEstado">
        {{ tx(modal.accion === 'reabrir' ? t('Reopen') : t('Cancel invoice')) }}
      </button>
    </template>
  </Modal>
  <ExplosionPrepack v-if="explosion" :sku="explosion.sku" :cajas="explosion.cajas" @cerrar="explosion = null" />
</template>
