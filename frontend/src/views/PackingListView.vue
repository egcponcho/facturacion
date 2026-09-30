<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import Seleccion from '../components/Seleccion.vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api'
import Anillo from '../components/Anillo.vue'
import DestinosYUnidades from '../components/DestinosYUnidades.vue'
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
import { avisar, errorApi, guardando, textoDetalle } from '../stores/ui'
import { cantTxt, fmtNum, pct, plural, porUnidadTxt, useSeleccion } from '../utils'

const props = defineProps({ id: String })
const route = useRoute()
const router = useRouter()

const pl = ref(null)
const tab = ref(route.query.tab || '')
const selL = useSeleccion()
const selG = useSeleccion()
const filtro = reactive({ texto: '', solo_pendiente: true })
const modal = ref(null)
const ocupado = ref(false)
const recepcion = reactive({})
const explosion = ref(null)

const url = (s = '') => `/packing-lists/${props.id}${s}`
const editable = computed(() => !!pl.value?.puede.editar)
const plantillas = computed(() => pl.value?.plantillas || [])
const ref_ = (l) => `${l.estilo || l.codigo_sap}${l.color ? ` ${l.color}` : ''}${l.talla ? ` · size ${l.talla}` : ''}`

async function cargar() {
  try {
    pl.value = await api.get(url())
    selL.podar(pl.value.lineas.map((l) => l.id))
    selG.podar(pl.value.grupos.map((g) => g.id))
    for (const l of pl.value.lineas) {
      recepcion[l.id] = {
        cantidad_recibida: l.recepcion?.cantidad_recibida ?? l.cantidad,
        cantidad_danada: l.recepcion?.cantidad_danada ?? 0,
        observacion: l.recepcion?.observacion ?? '',
      }
    }
    if (!tab.value || (!editable.value && ['empacar', 'revision'].includes(tab.value))) {
      tab.value = editable.value && pendientes.value.length ? 'empacar' : editable.value ? 'revision' : 'cajas'
    }
  } catch (e) {
    errorApi(e)
    if (e.status === 404) router.push('/facturas')
  }
}

// Ejecuta una acción, recarga y deja el PL al día. Todo o nada en el servidor.
async function accion(fn, exito) {
  ocupado.value = true
  try {
    const r = await guardando(fn())
    if (exito) avisar(typeof exito === 'function' ? exito(r) : exito)
    modal.value = null
    await cargar()
    return r
  } catch (e) {
    if (e.codigo === 'pendientes') modal.value = { tipo: 'pendientes', detalle: e.detalle }
    else {
      errorApi(e)
      if (e.codigo === 'conflicto_version') await cargar()
    }
    return null
  } finally {
    ocupado.value = false
  }
}

watch(tab, (t) => router.replace({ query: { ...route.query, tab: t } }))

// ---- Resumen y avance ------------------------------------------------------
const total = (campo) => Object.values(pl.value?.totales.por_unidad || {}).reduce((a, u) => a + u[campo], 0)
const avanceEmpaque = computed(() => pct(total('en_cajas'), total('cantidad')))
const pendientes = computed(() => (pl.value?.lineas || []).filter((l) => l.sin_caja > 0))
const estimadas = computed(() => (pl.value?.grupos || []).filter((g) => g.peso_estimado))

// Pendientes para finalizar, agrupados en lo que el proveedor tiene que hacer
const revision = computed(() => {
  const v = pl.value?.validaciones || []
  const grupo = (fn) => v.filter(fn)
  const sinCaja = grupo((e) => e.codigo === 'sin_caja')
  const estimado = grupo((e) => e.codigo === 'peso_estimado')
  const medidas = grupo((e) => e.grupo_id && /medidas/.test(e.mensaje))
  const pesos = grupo((e) => e.grupo_id && !e.codigo && !/medidas/.test(e.mensaje))
  const otros = grupo((e) => !e.grupo_id && e.codigo !== 'sin_caja')
  return [
    { clave: 'contenido', titulo: 'All contents are in cartons (whole inner packs)', faltan: [...otros, ...sinCaja], accion: 'empacar' },
    { clave: 'medidas', titulo: 'Every carton has dimensions', faltan: medidas, accion: 'cajas' },
    { clave: 'pesos', titulo: 'Every carton has net and gross weight', faltan: pesos, accion: 'cajas' },
    { clave: 'estimados', titulo: 'Estimated weights are confirmed', faltan: estimado, accion: 'confirmar' },
  ]
})
const listoParaFinalizar = computed(() => editable.value && !(pl.value?.validaciones || []).length)

const pasos = computed(() => {
  if (!pl.value) return []
  const fin = pl.value.estado === 'FINALIZADO'
  const empacado = !pendientes.value.length && pl.value.lineas.length > 0
  const datosOk = revision.value.slice(1).every((r) => !r.faltan.length)
  return [
    { titulo: 'Contents', estado: pl.value.lineas.length ? 'hecho' : 'actual', detalle: `${plural(pl.value.lineas.length, 'row', 'rows')} · ${porUnidadTxt(pl.value.totales.por_unidad, 'cantidad')}` },
    { titulo: 'Pack', estado: empacado || fin ? 'hecho' : 'actual', detalle: empacado ? plural(pl.value.totales.cajas, 'carton', 'cartons') : `${porUnidadTxt(pl.value.totales.por_unidad, 'sin_caja')} not packed` },
    { titulo: 'Dimensions and weights', estado: (empacado && datosOk) || fin ? 'hecho' : estimadas.value.length ? 'alerta' : empacado ? 'actual' : 'pendiente',
      detalle: estimadas.value.length ? `${plural(estimadas.value.length, 'group', 'groups')} with estimated weight` : !pl.value.grupos.length ? 'After packing' : datosOk ? 'Complete' : 'To complete' },
    { titulo: 'Finalize', estado: fin ? 'hecho' : listoParaFinalizar.value ? 'actual' : 'pendiente', detalle: fin ? 'Ready to ship' : pl.value.estado === 'EN_CORRECCION' ? 'In correction' : 'Pending' },
  ]
})

// ---- Por empacar -----------------------------------------------------------
const partes = computed(() => {
  const cuenta = {}
  const indice = {}
  for (const l of pl.value?.lineas || []) {
    cuenta[l.factura_linea_id] = (cuenta[l.factura_linea_id] || 0) + 1
    indice[l.id] = cuenta[l.factura_linea_id]
  }
  return { cuenta, indice }
})
const lineasFiltradas = computed(() => {
  const q = filtro.texto.trim().toLowerCase()
  return (pl.value?.lineas || []).filter((l) =>
    (!filtro.solo_pendiente || l.sin_caja > 0) &&
    (!q || [l.codigo_sap, l.estilo, l.color, l.talla, l.oc_numero, l.upc].some((v) => (v || '').toLowerCase().includes(q))))
})
const tablaL = useTabla(lineasFiltradas, { porPagina: 25, valores: { oc: (l) => `${l.oc_numero}-${String(l.posicion).padStart(5, '0')}` } })
const tablaG = useTabla(computed(() => pl.value?.grupos || []), { porPagina: 25, valores: { rango: (g) => g.desde, etiqueta: (g) => g.etiqueta?.tipo } })
const idsFiltrados = computed(() => lineasFiltradas.value.map((l) => l.id))

// Packing rule of the PO line: prepack (1 size run per carton), exact casepack
// or free; with an inner pack, cartons carry whole inner packs
const REGLAS = { PREPACK: ['Prepack', 'acento'], CASEPACK: ['Casepack', 'info'], LIBRE: ['Free', ''] }
const reglaTxt = (l) => (l.regla === 'PREPACK' ? `Prepack ${l.prepack || ''} · ${l.unidades_por_caja || '?'} per carton`
  : `${l.regla === 'CASEPACK' ? `Casepack ${l.casepack}` : 'Free casepack'}${l.inner_pack ? ` · inner ${l.inner_pack}` : ''}`)
const innerTxt = (cant, inner) => (inner ? ` · ${fmtNum(cant / inner)} inner pack${cant / inner === 1 ? '' : 's'} of ${inner}` : '')
const porCajaRegla = (l) => (l.regla === 'PREPACK' ? 1 : l.regla === 'CASEPACK' ? l.casepack : null)
const selLineas = computed(() => (pl.value?.lineas || []).filter((l) => selL.tiene(l.id)))
const selConPendiente = computed(() => selLineas.value.filter((l) => l.sin_caja > 0))
const resumenSelLineas = computed(() => {
  const r = {}
  for (const l of selLineas.value) r[l.unidad] = (r[l.unidad] || 0) + l.sin_caja
  return `${porUnidadTxt(r, null)} not packed`
})
const nombrePlantilla = (id) => plantillas.value.find((t) => t.id === id)?.nombre

// La mejor plantilla para una fila: la sugerida por el historial o, si no
// hay, la primera activa con la misma unidad.
function sugerida(l) {
  const s = plantillas.value.find((t) => t.id === l.plantilla_sugerida_id && t.unidad === l.unidad)
  return (s || plantillas.value.find((t) => t.unidad === l.unidad))?.id || ''
}
// Con casepack o prepack la plantilla solo aporta medidas y pesos: sirve cualquiera
const plantillasFila = (f) => (f.regla === 'LIBRE' ? plantillasDe(f.unidad) : plantillas.value)

// ---- Empaque automático: cada fila con su plantilla ------------------------
function abrirAuto(soloSeleccion = false) {
  const filas = (soloSeleccion ? selConPendiente.value : pendientes.value).map((l) => ({
    pl_linea_id: l.id, ref: ref_(l), unidad: l.unidad, sin_caja: l.sin_caja, plantilla_id: sugerida(l),
    regla: l.regla, por_caja: porCajaRegla(l), regla_txt: reglaTxt(l), inner: l.inner_pack,
  }))
  modal.value = { tipo: 'auto', filas, sobrante: 'caja_parcial' }
}
const calculoAuto = computed(() => {
  const m = modal.value
  if (m?.tipo !== 'auto') return null
  let completas = 0
  let parciales = 0
  let sobrante = 0
  let validas = 0
  const filas = m.filas.map((f) => {
    const t = plantillas.value.find((x) => x.id === f.plantilla_id)
    const porCaja = f.por_caja || t?.cantidad_por_caja
    if (!porCaja || f.plantilla_id === 'omitir') return { ...f, cajas: null, sobrante: null }
    // The template must hold whole inner packs (the server skips it otherwise)
    if (f.inner && porCaja % f.inner) return { ...f, cajas: null, sobrante: null, nota: `Template is not a multiple of the inner pack (${f.inner})` }
    validas++
    const cajas = Math.floor(f.sin_caja / porCaja)
    const resto = f.sin_caja % porCaja
    completas += cajas
    if (resto) {
      parciales++
      sobrante += resto
    }
    return { ...f, cajas, sobrante: resto }
  })
  return { filas, completas, parciales, sobrante, validas }
})
const plantillasDe = (unidad) => plantillas.value.filter((t) => t.unidad === unidad)
const unidadesAuto = computed(() => [...new Set((modal.value?.filas || []).map((f) => f.unidad))])
function aplicarATodas(unidad, id) {
  if (!id) return
  for (const f of modal.value.filas) if (f.unidad === unidad || f.regla !== 'LIBRE') f.plantilla_id = Number(id)
}
function empacarAuto() {
  const m = modal.value
  const filas = m.filas.filter((f) => f.plantilla_id !== 'omitir' && (f.plantilla_id || f.por_caja))
    .map((f) => ({ pl_linea_id: f.pl_linea_id, plantilla_id: f.plantilla_id || null }))
  accion(() => api.post(url('/empaque/aplicar'), { version: pl.value.version, filas, sobrante: m.sobrante }), (r) => {
    selL.limpiar()
    const partesTxt = [plural(r.resumen.cajas_completas, 'full carton', 'full cartons')]
    if (r.resumen.sobrante_total && m.sobrante === 'caja_parcial') partesTxt.push(plural(r.resumen.filas_con_sobrante, 'partial carton (confirm its weight)', 'partial cartons (confirm their weights)'))
    if (r.resumen.sobrante_total && m.sobrante === 'sin_caja') partesTxt.push(`${fmtNum(r.resumen.sobrante_total)} left unpacked`)
    return `Done: ${partesTxt.join(' and ')}.`
  }).then((r) => {
    if (r && !pendientes.value.length) tab.value = 'revision'
  })
}

// ---- Caja manual o mixta ---------------------------------------------------
function abrirCaja() {
  modal.value = {
    tipo: 'caja',
    num_cajas: 1,
    plantilla_id: '',
    valores: { largo: '', ancho: '', alto: '', peso_neto_caja: '', peso_bruto_caja: '', observacion: '' },
    items: selConPendiente.value.map((l) => ({
      pl_linea_id: l.id, ref: ref_(l), unidad: l.unidad, sin_caja: l.sin_caja, inner: l.inner_pack,
      cantidad_por_caja: selConPendiente.value.length === 1 ? (l.regla === 'CASEPACK' ? Math.min(l.casepack, l.sin_caja) : l.sin_caja) : (l.regla === 'CASEPACK' ? l.casepack : ''),
    })),
  }
}
const plantillaModal = computed(() => plantillas.value.find((t) => t.id === modal.value?.plantilla_id))
const cajaInvalida = computed(() => {
  const m = modal.value
  if (m?.tipo !== 'caja') return true
  return !(m.num_cajas >= 1) || m.items.some((i) => !(i.cantidad_por_caja >= 1) || i.cantidad_por_caja * m.num_cajas > i.sin_caja || (i.inner && i.cantidad_por_caja % i.inner))
})
function crearCaja() {
  const m = modal.value
  const valores = Object.fromEntries(Object.entries(m.valores).filter(([, v]) => v !== '' && v !== null)
    .map(([k, v]) => [k, k === 'observacion' ? v : Number(v)]))
  accion(() => api.post(url('/cajas'), {
    version: pl.value.version,
    num_cajas: Number(m.num_cajas),
    plantilla_id: m.plantilla_id || null,
    items: m.items.map((i) => ({ pl_linea_id: i.pl_linea_id, cantidad_por_caja: Number(i.cantidad_por_caja) })),
    ...valores,
  }), m.items.length > 1 ? 'Mixed carton created.' : `${plural(m.num_cajas, 'carton', 'cartons')} created.`)
  selL.limpiar()
}

// ---- Mover o quitar lo que no está en cajas -------------------------------
function filasMovibles() {
  const base = selConPendiente.value.length ? selConPendiente.value : pendientes.value
  return base.map((l) => ({ pl_linea_id: l.id, ref: ref_(l), unidad: l.unidad, sin_caja: l.sin_caja, cantidad: l.sin_caja, inner: l.inner_pack }))
}
function abrirMover() {
  modal.value = { tipo: 'mover', destino: pl.value.otros_pl[0]?.id || '', filas: filasMovibles() }
}
function abrirQuitar() {
  modal.value = { tipo: 'quitar', filas: filasMovibles() }
}
const movInvalido = computed(() => (modal.value?.filas || []).some((f) => f.cantidad !== 0 && (!(f.cantidad >= 1) || f.cantidad > f.sin_caja || (f.inner && f.cantidad % f.inner))) ||
  !(modal.value?.filas || []).some((f) => f.cantidad > 0))
const movimientos = () => modal.value.filas.filter((f) => f.cantidad > 0).map((f) => ({ pl_linea_id: f.pl_linea_id, cantidad: Number(f.cantidad) }))
function mover() {
  const m = modal.value
  accion(() => api.post(url('/mover'), { version: pl.value.version, destino_pl_id: m.destino || null, movimientos: movimientos() }),
    (r) => `Quantities moved to ${r.destino_numero}.`)
  selL.limpiar()
}
function quitar() {
  accion(() => api.post(url('/quitar'), { version: pl.value.version, movimientos: movimientos() }),
    'Quantities returned to the invoice; they are pending assignment to a packing list.')
  selL.limpiar()
}

// ---- Cajas -----------------------------------------------------------------
const selGrupos = computed(() => (pl.value?.grupos || []).filter((g) => selG.tiene(g.id)))
const idsGrupos = computed(() => (pl.value?.grupos || []).map((g) => g.id))
const cajasSel = computed(() => selGrupos.value.reduce((a, g) => a + g.num_cajas, 0))
const rango = (g) => (g.desde === g.hasta ? `${g.desde}` : `${g.desde}–${g.hasta}`)

const celdaGrupo = (g, campo) => async (valor) => {
  try {
    await guardando(api.patch(url('/cajas'), { version: pl.value.version, grupo_ids: [g.id], [campo]: valor }))
    await cargar()
  } catch (e) {
    errorApi(e)
    if (e.codigo === 'conflicto_version') cargar()
    throw e
  }
}

// Una sola ventana para medidas, pesos, número de cajas y valores de plantilla
function abrirEditarCajas(grupos = selGrupos.value) {
  modal.value = {
    tipo: 'editar_cajas', grupo_ids: grupos.map((g) => g.id), cajas: grupos.reduce((a, g) => a + g.num_cajas, 0), plantilla_id: '',
    valores: { num_cajas: '', largo: '', ancho: '', alto: '', peso_neto_caja: '', peso_bruto_caja: '', observacion: '' },
  }
}
function editarCajas() {
  const m = modal.value
  const valores = Object.fromEntries(Object.entries(m.valores).filter(([, v]) => v !== '')
    .map(([k, v]) => [k, k === 'observacion' ? v : Number(v)]))
  if (!Object.keys(valores).length && !m.plantilla_id) return avisar('Choose a template or enter at least one value.', 'error')
  accion(() => api.patch(url('/cajas'), {
    version: pl.value.version, grupo_ids: m.grupo_ids, ...valores, ...(m.plantilla_id ? { desde_plantilla_id: m.plantilla_id } : {}),
  }), `${plural(m.cajas, 'carton', 'cartons')} updated.`)
}
function confirmarPesos(grupos) {
  accion(() => api.patch(url('/cajas'), { version: pl.value.version, grupo_ids: grupos.map((g) => g.id), confirmar_pesos: true }),
    `Weights confirmed on ${plural(grupos.length, 'carton group', 'carton groups')}.`)
}
function abrirMoverCajas() {
  modal.value = {
    tipo: 'mover_cajas',
    destino: pl.value.otros_pl[0]?.id || '',
    grupos: selGrupos.value.map((g) => ({ grupo_id: g.id, rango: rango(g), max: g.num_cajas, num_cajas: g.num_cajas })),
  }
}
function moverCajas() {
  const m = modal.value
  accion(() => api.post(url('/mover-cajas'), {
    version: pl.value.version, destino_pl_id: m.destino || null,
    grupos: m.grupos.map((g) => ({ grupo_id: g.grupo_id, num_cajas: Number(g.num_cajas) })),
  }), (r) => `Cartons moved to ${r.destino_numero} with their contents.`)
}
// ---- Pallets -----------------------------------------------------------------
function abrirPaletizar() {
  modal.value = { tipo: 'pallet', destino: '', largo: 120, ancho: 100, alto: 150, peso_tara: 25 }
}
function paletizar() {
  const m = modal.value
  const nuevo = !m.destino
  const cajas = cajasSel.value
  accion(() => api.post(url('/pallets'), {
    version: pl.value.version, grupo_ids: selG.lista(), pallet_id: m.destino || null,
    ...(nuevo ? { largo: Number(m.largo), ancho: Number(m.ancho), alto: Number(m.alto), peso_tara: Number(m.peso_tara) || 0 } : {}),
  }), (r) => `${plural(cajas, 'carton', 'cartons')} on pallet ${r.numero}.`)
  selG.limpiar()
}
function despaletizar(grupoIds, palletId = null) {
  accion(() => api.post(url('/pallets/quitar'), { version: pl.value.version, grupo_ids: grupoIds, pallet_id: palletId }),
    palletId ? 'Pallet undone; its cartons are loose.' : 'Cartons taken off the pallet.')
  selG.limpiar()
}
const celdaPallet = (p, campo) => async (valor) => {
  try {
    await guardando(api.patch(url(`/pallets/${p.id}`), { version: pl.value.version, [campo]: valor }))
    await cargar()
  } catch (e) {
    errorApi(e)
    if (e.codigo === 'conflicto_version') cargar()
    throw e
  }
}

function desempacar() {
  accion(() => api.post(url('/cajas/eliminar'), { version: pl.value.version, grupo_ids: selG.lista() }),
    'Cartons unpacked; their contents went back to “To pack”.')
}
function guardarPlantilla() {
  accion(() => api.post(url(`/cajas/${modal.value.grupo_id}/plantilla`), { nombre: modal.value.nombre }),
    (r) => `Template “${r.nombre}” saved; you can now use it when packing.`)
}

// ---- Estados, recepción y exportación -------------------------------------
const finalizar = () => accion(() => api.post(url('/finalizar'), { version: pl.value.version }), 'Packing list finalized.')
const agregarPendientes = () => accion(() => api.post(url('/agregar'), { version: pl.value.version }),
  (r) => `${fmtNum(r.agregado)} added from the invoice.`)
function cambiarEstado() {
  const { accion: a, motivo } = modal.value
  accion(() => api.post(url(`/${a}`), { motivo }), (r) => (a === 'reabrir'
    ? `Packing list reopened.${r.nota ? ` ${r.nota}` : ''}` : 'Packing list cancelled; its quantities went back to the invoice.'))
}
function guardarRecepcion() {
  accion(() => api.post(url('/recepcion'), {
    lineas: pl.value.lineas.map((l) => ({ pl_linea_id: l.id, ...recepcion[l.id], cantidad_recibida: Number(recepcion[l.id].cantidad_recibida), cantidad_danada: Number(recepcion[l.id].cantidad_danada) })),
  }), (r) => (r.diferencias.length ? `Receipt saved with ${plural(r.diferencias.length, 'difference', 'differences')}.` : 'Receipt saved with no differences.'))
}
const descargar = (formato) => api.descargar(url('/exportar'), `packing_list.${formato}`, { formato }).catch(errorApi)

function irA(accionRevision) {
  if (accionRevision === 'confirmar') confirmarPesos(estimadas.value)
  else tab.value = accionRevision
}

onMounted(cargar)
</script>

<template>
  <template v-if="pl">
    <router-link :to="`/facturas/${pl.factura.id}?tab=pl`" class="volver"><Icono nombre="atras" :tam="15" />Invoice {{ pl.factura.nombre }}</router-link>
    <section class="doc-cabeza">
      <div class="doc-fila">
        <span class="doc-numero">{{ pl.numero }}</span>
        <EstadoBadge :estado="pl.estado" />
        <span class="doc-sub">{{ pl.factura.nombre }} · {{ pl.factura.proveedor }}</span>
        <div class="doc-acciones">
          <button class="btn btn-fantasma" title="Packing list as PDF, ready to print and sign" @click="descargar('pdf')"><Icono nombre="descargar" />PDF</button>
          <button class="btn btn-fantasma" title="Packing list as Excel" @click="descargar('xlsx')"><Icono nombre="descargar" />Excel</button>
          <button v-if="pl.puede.reabrir" class="btn" @click="modal = { tipo: 'estado', accion: 'reabrir', motivo: '' }">Reopen to correct</button>
          <button v-if="pl.puede.cancelar" class="btn btn-peligro" @click="modal = { tipo: 'estado', accion: 'cancelar', motivo: '' }">Cancel PL</button>
          <button v-if="pl.puede.finalizar" class="btn" :class="{ 'btn-primario': listoParaFinalizar }" :disabled="ocupado" @click="listoParaFinalizar ? finalizar() : (tab = 'revision')">
            <Icono nombre="check" />{{ listoParaFinalizar ? 'Finalize packing list' : `Finalize (${pl.validaciones.length} pending)` }}
          </button>
        </div>
      </div>
      <div class="empaque-resumen">
        <Anillo :porcentaje="avanceEmpaque" titulo="Packed" :detalle="pendientes.length ? `${porUnidadTxt(pl.totales.por_unidad, 'sin_caja')} missing` : `${porUnidadTxt(pl.totales.por_unidad, 'cantidad')} in cartons`" />
        <div class="cifra"><span>Cartons</span><b>{{ fmtNum(pl.totales.cajas) }}</b></div>
        <div class="cifra"><span>Net weight</span><b>{{ fmtNum(pl.totales.peso_neto, 1) }} kg</b></div>
        <div class="cifra"><span>Gross weight</span><b>{{ fmtNum(pl.totales.peso_bruto, 1) }} kg</b></div>
        <div class="cifra"><span>Volume</span><b>{{ fmtNum(pl.totales.cbm, 2) }} m³</b></div>
        <div v-if="pl.totales.pallets" class="cifra"><span>Pallets</span><b>{{ pl.totales.pallets }}</b></div>
        <div class="cifra"><span>Load unit</span>
          <b v-if="pl.transporte" style="font-size: 0.95rem">{{ pl.transporte.unidad }} · {{ pl.transporte.embarque }} <EstadoBadge :estado="pl.transporte.asignacion" /></b>
          <b v-else class="apagado" style="font-size: 0.95rem">Not assigned</b>
        </div>
      </div>
      <Pasos :pasos="pasos" />
    </section>

    <div v-if="pl.partes" class="partes" style="margin-bottom: 16px">
      <TarjetaParte titulo="Bill to" icono="factura" :parte="pl.partes.facturar_a" />
      <TarjetaParte titulo="Notify party (receiving plant)" icono="ubicacion" :parte="pl.partes.notify" />
      <section v-if="pl.partes.destino" class="panel tarjeta-parte">
        <div class="tp-cabeza">
          <span class="tp-icono"><Icono nombre="ruta" :tam="16" /></span>
          <div><span class="eyebrow">Final destination</span><b>{{ pl.partes.destino.codigo }} · {{ pl.partes.destino.nombre || 'Plant not registered' }}</b></div>
        </div>
        <p class="tp-linea">Country of arrival: <b>{{ pl.partes.destino.pais || '—' }}</b></p>
      </section>
    </div>

    <p v-if="editable && pl.saldo_factura > 0" class="nota aviso" style="align-items: center">
      <Icono nombre="info" />
      <span>The invoice has {{ fmtNum(pl.saldo_factura) }} not in any packing list.</span>
      <button class="btn btn-chico separar" :disabled="ocupado" @click="agregarPendientes"><Icono nombre="mas" :tam="14" />Add to {{ pl.numero }}</button>
    </p>

    <div class="pestanas" role="tablist">
      <button v-if="editable" class="pestana" role="tab" :aria-selected="tab === 'empacar'" @click="tab = 'empacar'">
        <Icono nombre="caja" :tam="16" />To pack<span class="cuenta" :class="{ alerta: pendientes.length }">{{ pendientes.length }}</span>
      </button>
      <button class="pestana" role="tab" :aria-selected="tab === 'cajas'" @click="tab = 'cajas'">
        <Icono nombre="lista" :tam="16" />Cartons<span class="cuenta">{{ pl.totales.cajas }}</span>
      </button>
      <button v-if="editable" class="pestana" role="tab" :aria-selected="tab === 'revision'" @click="tab = 'revision'">
        <Icono nombre="check" :tam="16" />Review<span class="cuenta" :class="{ alerta: pl.validaciones.length }">{{ pl.validaciones.length || '✓' }}</span>
      </button>
      <button v-if="!editable" class="pestana" role="tab" :aria-selected="tab === 'contenido'" @click="tab = 'contenido'">
        <Icono nombre="lista" :tam="16" />Contents<span class="cuenta">{{ pl.lineas.length }}</span>
      </button>
      <button v-if="pl.puede.recepcion" class="pestana" role="tab" :aria-selected="tab === 'recepcion'" @click="tab = 'recepcion'"><Icono nombre="importar" :tam="16" />Receipt</button>
    </div>

    <!-- To pack -->
    <section v-if="tab === 'empacar' && editable">
      <div v-if="!pendientes.length && pl.lineas.length" class="panel vacio">
        <div class="todo-listo" style="justify-content: center">
          <span class="icono-ok"><Icono nombre="check" :tam="22" /></span>
          <div style="text-align: left"><b>Everything is in cartons</b><p class="ayuda">Check dimensions and weights and finalize the packing list.</p></div>
          <button class="btn btn-primario" @click="tab = 'revision'">Go to review<Icono nombre="flecha" :tam="16" /></button>
        </div>
      </div>
      <template v-else>
        <div class="opciones-empaque">
          <button class="opcion recomendada" :disabled="!pendientes.length || (!plantillas.length && !pendientes.some((l) => l.regla !== 'LIBRE'))" @click="abrirAuto(selConPendiente.length > 0)">
            <span class="opcion-icono"><Icono nombre="varita" /></span>
            <b>Auto-pack <span class="etiqueta acento">Recommended</span></b>
            <span>{{ selConPendiente.length ? `The ${selConPendiente.length} selected rows` : `All rows (${pendientes.length})` }} in one step, following each line's casepack, inner pack or prepack. The template adds dimensions and weights; you decide what to do with leftovers.</span>
            <span v-if="!plantillas.length" class="etiqueta aviso">Create a template first</span>
          </button>
          <button class="opcion" :disabled="!selConPendiente.length" @click="abrirCaja">
            <span class="opcion-icono"><Icono nombre="caja" /></span>
            <b>Manual or mixed carton</b>
            <span>{{ selConPendiente.length ? `With the ${selConPendiente.length} selected rows.` : 'Select rows below.' }} You set how many go per carton; with several rows it is an assorted carton (same destination only).</span>
          </button>
          <button class="opcion" :disabled="!pendientes.length" @click="abrirMover">
            <span class="opcion-icono"><Icono nombre="mover" /></span>
            <b>Split into another packing list</b>
            <span>Move unpacked quantities to another PL of the invoice (or a new one), for example per destination country or for another container.</span>
          </button>
        </div>

        <div class="filtros mt">
          <label class="buscador">
            <Icono nombre="buscar" :tam="16" />
            <input v-model="filtro.texto" type="search" placeholder="Filter by code, style, color, size or PO" aria-label="Filter contents" />
          </label>
          <div class="segmentos" role="group" aria-label="Show">
            <button class="segmento" :aria-pressed="filtro.solo_pendiente" @click="filtro.solo_pendiente = true">Not packed<span class="cuenta">{{ pendientes.length }}</span></button>
            <button class="segmento" :aria-pressed="!filtro.solo_pendiente" @click="filtro.solo_pendiente = false">All<span class="cuenta">{{ pl.lineas.length }}</span></button>
          </div>
        </div>
        <div class="tabla-marco tabla-fija">
          <table class="tabla">
            <thead>
              <tr>
                <th class="chk"><input type="checkbox" aria-label="Select all filtered rows" :checked="selL.todos(idsFiltrados)" @change="selL.alternarTodos(idsFiltrados)" /></th>
                <ThOrden campo="estilo" :orden="tablaL.estado.orden" @ordenar="tablaL.ordenar">Item</ThOrden>
                <ThOrden campo="talla" :orden="tablaL.estado.orden" @ordenar="tablaL.ordenar">Size</ThOrden>
                <ThOrden campo="oc" :orden="tablaL.estado.orden" @ordenar="tablaL.ordenar">PO / line</ThOrden>
                <ThOrden campo="regla" :orden="tablaL.estado.orden" @ordenar="tablaL.ordenar">Rule</ThOrden>
                <th>UoM</th>
                <ThOrden campo="cantidad" :orden="tablaL.estado.orden" num @ordenar="tablaL.ordenar">Quantity</ThOrden>
                <ThOrden campo="en_cajas" :orden="tablaL.estado.orden" num @ordenar="tablaL.ordenar">In cartons</ThOrden>
                <ThOrden campo="sin_caja" :orden="tablaL.estado.orden" num @ordenar="tablaL.ordenar">Not packed</ThOrden>
                <th>Suggested template</th>
                <ThOrden campo="estado_empaque" :orden="tablaL.estado.orden" @ordenar="tablaL.ordenar">Packing</ThOrden>
              </tr>
            </thead>
            <tbody>
              <tr v-for="l in tablaL.filas.value" :key="l.id" :class="{ seleccionada: selL.tiene(l.id) }">
                <td class="chk"><input type="checkbox" :aria-label="`Select ${ref_(l)}`" :checked="selL.tiene(l.id)" @change="selL.alternar(l.id)" /></td>
                <td><span v-if="l.marca" class="fuerte">{{ l.marca }}</span> {{ l.estilo }} · {{ l.color }}
                  <span v-if="partes.cuenta[l.factura_linea_id] > 1" class="etiqueta">part {{ partes.indice[l.id] }}</span>
                  <span class="sub codigo">{{ l.codigo_sap }}</span>
                </td>
                <td><strong>{{ l.talla }}</strong></td>
                <td class="codigo">{{ l.oc_numero }} / {{ l.posicion }}<span v-if="l.centro_destino || l.almacen" class="sub">{{ [l.almacen && `warehouse ${l.almacen}`, l.centro_destino && `destination ${l.centro_destino}`].filter(Boolean).join(' · ') }}</span></td>
                <td>
                  <button v-if="l.regla === 'PREPACK'" type="button" class="etiqueta acento btn-explosion" style="margin-left: 0"
                          title="See the prepack breakdown" @click="explosion = { sku: l.codigo_sap, cajas: l.cantidad }">{{ reglaTxt(l) }} <Icono nombre="lupa" :tam="12" /></button>
                  <span v-else class="etiqueta" :class="REGLAS[l.regla]?.[1]" style="margin-left: 0">{{ reglaTxt(l) }}</span>
                </td>
                <td><span class="etiqueta" style="margin-left: 0">{{ l.unidad }}</span></td>
                <td class="num">{{ cantTxt(l.cantidad, l.unidad) }}</td>
                <td class="num">{{ fmtNum(l.en_cajas) }}</td>
                <td class="num"><strong v-if="l.sin_caja">{{ fmtNum(l.sin_caja) }}</strong><span v-else class="apagado">0</span></td>
                <td>
                  <span v-if="sugerida(l)">{{ nombrePlantilla(sugerida(l)) }}<span v-if="l.plantilla_sugerida_id === sugerida(l)" class="etiqueta info" title="The one you used last time with this item">used before</span></span>
                  <span v-else-if="l.regla !== 'LIBRE'" class="apagado">Not needed (uses the casepack)</span>
                  <span v-else class="apagado">No template for {{ l.unidad === 'PAR' ? 'pairs' : 'units' }}</span>
                </td>
                <td>
                  <EstadoBadge :estado="l.estado_empaque" />
                  <span v-if="l.en_parcial" class="etiqueta aviso">partial carton</span>
                </td>
              </tr>
              <tr v-if="!lineasFiltradas.length">
                <td colspan="11" class="vacio">{{ pl.lineas.length ? 'No row matches the filter.' : 'The packing list is empty.' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <Paginacion :page="tablaL.estado.pagina" :size="tablaL.estado.porPagina" :total="tablaL.total.value"
                    @cambiar="(p) => (tablaL.estado.pagina = p)" @tamano="(t) => (tablaL.estado.porPagina = t)" />
        <BarraSeleccion :cantidad="selL.ids.size" singular="row selected" plural="rows selected" @limpiar="selL.limpiar()">
          <template #resumen>{{ resumenSelLineas }}</template>
          <button class="btn btn-primario" :disabled="!selConPendiente.length" @click="abrirAuto(true)"><Icono nombre="varita" :tam="15" />Auto-pack</button>
          <button class="btn" :disabled="!selConPendiente.length" @click="abrirCaja"><Icono nombre="caja" :tam="15" />{{ selConPendiente.length > 1 ? 'Mixed carton' : 'Manual carton' }}</button>
          <button class="btn" :disabled="!selConPendiente.length" @click="abrirMover"><Icono nombre="mover" :tam="15" />Move to another PL</button>
          <button class="btn btn-peligro" :disabled="!selConPendiente.length" @click="abrirQuitar">Remove from PL</button>
        </BarraSeleccion>
      </template>
    </section>

    <!-- Cartons -->
    <section v-if="tab === 'cajas'">
      <p v-if="editable && estimadas.length" class="nota aviso" style="align-items: center; margin-bottom: 12px">
        <Icono nombre="escala" />
        <span>{{ plural(estimadas.length, 'carton group has', 'carton groups have') }} an estimated weight (partial cartons). Weigh and correct them, or confirm the estimate.</span>
        <button class="btn btn-chico separar" :disabled="ocupado" @click="confirmarPesos(estimadas)">Confirm all estimates</button>
      </p>
      <section v-if="pl.pallets?.length" class="panel" style="margin-bottom: 14px">
        <div class="panel-cabeza"><div><h2>Pallets</h2><p>The shipment volume uses the pallet dimensions; the gross weight adds its tare.</p></div></div>
        <div class="tabla-marco" style="box-shadow: none">
          <table class="tabla">
            <thead><tr><th>Pallet</th><th>Cartons</th><th class="num"><span class="req">Length</span></th><th class="num"><span class="req">Width</span></th><th class="num"><span class="req">Height cm</span></th><th class="num">Tare kg</th><th class="num">Gross kg</th><th class="num">m³</th><th></th></tr></thead>
            <tbody>
              <tr v-for="p in pl.pallets" :key="p.id">
                <td class="fuerte">Pallet {{ p.numero }}</td>
                <td>{{ p.cajas }} <span class="sub">cartons {{ p.rangos.join(', ') }}</span></td>
                <td v-for="campo in ['largo', 'ancho', 'alto', 'peso_tara']" :key="campo" class="num" style="width: 90px">
                  <CeldaEditable v-if="editable" tipo="number" :min="0" :valor="p[campo]" :guardar="celdaPallet(p, campo)" :etiqueta="`${campo} of pallet ${p.numero}`" />
                  <template v-else>{{ fmtNum(p[campo], campo === 'peso_tara' ? 1 : 0) }}</template>
                </td>
                <td class="num">{{ fmtNum(p.peso_bruto, 1) }}</td>
                <td class="num">{{ fmtNum(p.cbm, 3) }}</td>
                <td class="num"><button v-if="editable" class="btn btn-chico btn-fantasma" :disabled="ocupado" @click="despaletizar([], p.id)">Undo</button></td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
      <p v-if="pl.avisos?.length" class="nota aviso bloque" style="margin-bottom: 12px">
        <Icono nombre="alerta" />
        <span><b>Check with the Commercial Brand Manager:</b> <template v-for="a in pl.avisos" :key="a.grupo_id">{{ a.mensaje }} </template></span>
      </p>
      <div class="tabla-marco tabla-fija">
        <table class="tabla">
          <thead>
            <tr>
              <th class="chk"><input type="checkbox" aria-label="Select all cartons" :checked="selG.todos(idsGrupos)" @change="selG.alternarTodos(idsGrupos)" /></th>
              <ThOrden campo="rango" :orden="tablaG.estado.orden" @ordenar="tablaG.ordenar">Cartons</ThOrden>
              <ThOrden campo="etiqueta" :orden="tablaG.estado.orden" @ordenar="tablaG.ordenar">Contents per carton</ThOrden>
              <th class="num">Qty</th>
              <th class="num"><span class="req">Length</span></th>
              <th class="num"><span class="req">Width</span></th>
              <th class="num"><span class="req">Height cm</span></th>
              <th class="num"><span class="req">Net/ctn</span></th>
              <th class="num"><span class="req">Gross/ctn kg</span></th>
              <th class="num">m³</th>
              <th class="num">Gross total</th>
              <th>Notes</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="g in tablaG.filas.value" :key="g.id" :class="{ seleccionada: selG.tiene(g.id) }">
              <td class="chk"><input type="checkbox" :aria-label="`Select cartons ${rango(g)}`" :checked="selG.tiene(g.id)" @change="selG.alternar(g.id)" /></td>
              <td class="cajas-rango">{{ rango(g) }}<span v-if="g.pallet" class="etiqueta acento" title="On pallet">P{{ g.pallet }}</span></td>
              <td class="envolver">
                <div class="caja-items">
                  <div v-for="it in g.items" :key="it.pl_linea_id">
                    {{ it.estilo }} <b>{{ it.talla }}</b> × {{ cantTxt(it.cantidad_por_caja, it.unidad) }}<span v-if="it.inner_packs_por_caja" class="ayuda"> ({{ it.inner_packs_por_caja }} inner packs of {{ it.inner_pack }})</span>
                  </div>
                </div>
                <div v-if="g.etiqueta" class="fila-flex" style="gap: 4px; margin-top: 4px">
                  <span class="etiqueta" :class="g.etiqueta.tipo === 'ESTANDAR' ? 'ok' : 'acento'" style="margin-left: 0"
                        :title="g.etiqueta.tipo === 'ESTANDAR' ? 'A single PO, style, color and size' : 'Several POs, styles, colors or sizes'">
                    {{ g.etiqueta.tipo === 'ESTANDAR' ? 'Standard' : 'Consolidated' }} label
                  </span>
                  <span class="ayuda codigo">PO {{ g.etiqueta.ocs.join(', ') }}</span>
                  <span v-if="g.etiqueta.centro_destino" class="ayuda">· destination {{ g.etiqueta.centro_destino }}</span>
                </div>
              </td>
              <td class="num" style="width: 70px">
                <CeldaEditable v-if="editable" tipo="number" :min="1" paso="1" :valor="g.num_cajas" :guardar="celdaGrupo(g, 'num_cajas')" etiqueta="Number of cartons" />
                <template v-else>{{ g.num_cajas }}</template>
              </td>
              <td v-for="campo in ['largo', 'ancho', 'alto', 'peso_neto_caja', 'peso_bruto_caja']" :key="campo" class="num" style="width: 82px">
                <CeldaEditable v-if="editable" tipo="number" :min="0" :valor="g[campo]" :guardar="celdaGrupo(g, campo)" vacia-texto="Missing" :etiqueta="campo.replaceAll('_', ' ')" />
                <template v-else>{{ fmtNum(g[campo], campo.startsWith('peso') ? 2 : 0) }}</template>
              </td>
              <td class="num">{{ fmtNum(g.cbm_total, 3) }}</td>
              <td class="num">{{ fmtNum(g.peso_bruto_total, 1) }}</td>
              <td>
                <span v-if="g.mixta" class="etiqueta">Mixed</span>
                <span v-if="g.es_parcial" class="etiqueta aviso">Partial</span>
                <span v-if="g.peso_estimado" class="etiqueta error">Estimated weight</span>
                <span v-if="g.plantilla_nombre" class="sub">{{ g.plantilla_nombre }}</span>
                <span v-if="g.observacion" class="sub">{{ g.observacion }}</span>
              </td>
            </tr>
            <tr v-if="!pl.grupos.length">
              <td colspan="12" class="vacio">
                <Icono nombre="caja" :tam="28" />
                <p>No cartons yet.</p>
                <button v-if="editable" class="btn btn-primario" @click="tab = 'empacar'">Start packing</button>
              </td>
            </tr>
          </tbody>
          <tfoot v-if="pl.grupos.length">
            <tr>
              <td></td>
              <td colspan="2">Total</td>
              <td class="num">{{ fmtNum(pl.totales.cajas) }}</td>
              <td colspan="5"></td>
              <td class="num">{{ fmtNum(pl.totales.cbm, 3) }}</td>
              <td class="num">{{ fmtNum(pl.totales.peso_bruto, 1) }}</td>
              <td></td>
            </tr>
          </tfoot>
        </table>
      </div>
      <Paginacion :page="tablaG.estado.pagina" :size="tablaG.estado.porPagina" :total="tablaG.total.value"
                  @cambiar="(p) => (tablaG.estado.pagina = p)" @tamano="(t) => (tablaG.estado.porPagina = t)" />
      <BarraSeleccion :cantidad="selG.ids.size" singular="group selected" plural="groups selected" @limpiar="selG.limpiar()">
        <template #resumen>{{ plural(cajasSel, 'carton', 'cartons') }}</template>
        <template v-if="editable">
          <button class="btn btn-primario" @click="abrirEditarCajas()"><Icono nombre="editar" :tam="15" />Dimensions and weights</button>
          <button v-if="selGrupos.some((g) => g.peso_estimado)" class="btn" :disabled="ocupado" @click="confirmarPesos(selGrupos.filter((g) => g.peso_estimado))">Confirm weights</button>
          <button class="btn" @click="abrirMoverCajas"><Icono nombre="mover" :tam="15" />Move to another PL</button>
          <button class="btn" :disabled="selGrupos.length !== 1 || selGrupos[0].mixta" title="Single-item cartons only" @click="modal = { tipo: 'guardar_plantilla', grupo_id: selGrupos[0].id, nombre: '' }"><Icono nombre="capas" :tam="15" />Save as template</button>
          <button class="btn" @click="abrirPaletizar"><Icono nombre="capas" :tam="15" />Palletize</button>
          <button v-if="selGrupos.some((g) => g.pallet)" class="btn" :disabled="ocupado" @click="despaletizar(selGrupos.filter((g) => g.pallet).map((g) => g.id))">Take off pallet</button>
          <button class="btn btn-peligro" @click="modal = { tipo: 'desempacar' }">Unpack</button>
        </template>
      </BarraSeleccion>
    </section>

    <!-- Review -->
    <section v-if="tab === 'revision' && editable" class="dos-columnas">
      <div class="panel">
        <div class="panel-cabeza"><div><h2>Before finalizing</h2><p>Everything must be green. Each point takes you to fix it.</p></div></div>
        <ul class="checklist">
          <li v-for="r in revision" :key="r.clave" :class="r.faltan.length ? 'falta' : 'ok'">
            <span class="marca"><Icono :nombre="r.faltan.length ? 'alerta' : 'check'" :tam="14" /></span>
            <span>
              {{ r.titulo }}
              <span v-if="r.faltan.length" class="sub ayuda">{{ r.faltan.slice(0, 3).map((e) => e.mensaje).join(' ') }}<template v-if="r.faltan.length > 3"> And {{ r.faltan.length - 3 }} more.</template></span>
            </span>
            <button v-if="r.faltan.length" class="btn btn-chico" :disabled="ocupado" @click="irA(r.accion)">
              {{ { empacar: 'Pack', cajas: 'Go to cartons', confirmar: 'Confirm estimates' }[r.accion] }}
            </button>
          </li>
        </ul>
        <div class="fila-flex mt">
          <button v-if="pl.puede.finalizar" class="btn btn-primario btn-grande" :disabled="ocupado || !listoParaFinalizar" @click="finalizar"><Icono nombre="check" />Finalize packing list</button>
          <span v-if="!listoParaFinalizar" class="ayuda">{{ plural(pl.validaciones.length, 'pending item', 'pending items') }}</span>
        </div>
      </div>
      <div class="panel">
        <div class="panel-cabeza"><div><h2>Packing list summary</h2><p>This is how it will appear on the PDF and Excel.</p></div></div>
        <div class="doc-datos" style="margin-top: 0; padding-top: 0; border-top: 0">
          <div class="dato"><span>Contents</span><b>{{ porUnidadTxt(pl.totales.por_unidad, 'cantidad') }}</b></div>
          <div class="dato"><span>Cartons</span><b>{{ fmtNum(pl.totales.cajas) }}</b></div>
          <div class="dato"><span>Net weight</span><b>{{ fmtNum(pl.totales.peso_neto, 2) }} kg</b></div>
          <div class="dato"><span>Gross weight</span><b>{{ fmtNum(pl.totales.peso_bruto, 2) }} kg</b></div>
          <div class="dato"><span>Volume</span><b>{{ fmtNum(pl.totales.cbm, 3) }} m³</b></div>
          <div class="dato"><span>Rows</span><b>{{ pl.lineas.length }}</b></div>
        </div>
        <DestinosYUnidades :pl="pl" />
      </div>
    </section>
    <section v-else-if="tab === 'cajas' && pl.grupos.length" class="panel mt">
      <DestinosYUnidades :pl="pl" />
    </section>

    <!-- Contents (read only) -->
    <section v-if="tab === 'contenido'">
      <div class="tabla-marco">
        <table class="tabla">
          <thead><tr><th>Item</th><th>Size</th><th>PO / line</th><th class="num">Quantity</th><th class="num">In cartons</th><th>Packing</th></tr></thead>
          <tbody>
            <tr v-for="l in pl.lineas" :key="l.id">
              <td>{{ l.estilo }} · {{ l.color }}<span class="sub codigo">{{ l.codigo_sap }}</span></td>
              <td><strong>{{ l.talla }}</strong></td>
              <td class="codigo">{{ l.oc_numero }} / {{ l.posicion }}<span v-if="l.almacen" class="sub">warehouse {{ l.almacen }}</span></td>
              <td class="num">{{ cantTxt(l.cantidad, l.unidad) }}</td>
              <td class="num">{{ fmtNum(l.en_cajas) }}</td>
              <td><EstadoBadge :estado="l.estado_empaque" /></td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <!-- Receipt -->
    <section v-if="tab === 'recepcion'" class="panel">
      <div class="panel-cabeza">
        <div><h2>Warehouse receipt</h2><p>Record what was received and damaged per row; differences are kept in the history.</p></div>
        <button class="btn btn-primario" :disabled="ocupado" @click="guardarRecepcion">Save receipt</button>
      </div>
      <div class="tabla-marco" style="box-shadow: none">
        <table class="tabla">
          <thead>
            <tr><th>Row</th><th class="num">Per PL</th><th class="num">Received</th><th class="num">Damaged</th><th class="num">Difference</th><th>Remark</th></tr>
          </thead>
          <tbody>
            <tr v-for="l in pl.lineas" :key="l.id">
              <td>{{ l.estilo }} <b>{{ l.talla }}</b><span class="sub codigo">{{ l.codigo_sap }}</span></td>
              <td class="num">{{ cantTxt(l.cantidad, l.unidad) }}</td>
              <td class="num"><input v-model.number="recepcion[l.id].cantidad_recibida" class="celda num" type="number" min="0" style="width: 90px; border-color: var(--linea)" :aria-label="`Received ${ref_(l)}`" /></td>
              <td class="num"><input v-model.number="recepcion[l.id].cantidad_danada" class="celda num" type="number" min="0" style="width: 80px; border-color: var(--linea)" :aria-label="`Damaged ${ref_(l)}`" /></td>
              <td class="num">
                <span :class="{ 'etiqueta error': recepcion[l.id].cantidad_recibida !== l.cantidad }">{{ fmtNum(recepcion[l.id].cantidad_recibida - l.cantidad) }}</span>
              </td>
              <td><input v-model="recepcion[l.id].observacion" class="celda" style="border-color: var(--linea)" :aria-label="`Remark ${ref_(l)}`" /></td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </template>

  <!-- Dialogs -->
  <Modal v-if="modal?.tipo === 'auto'" titulo="Auto-pack" ancho="1000px" @cerrar="modal = null">
    <p class="ayuda">Each row is packed into full cartons. If the PO line has a <b>casepack</b>, every carton carries exactly that quantity (no mixed sizes); a <b>prepack</b> goes one size run per master carton. Without a casepack, the template sets the quantity per carton. With an <b>inner pack</b>, cartons always carry whole inner packs. The template also adds dimensions and weights.</p>
    <div class="fila-flex">
      <label v-for="u in unidadesAuto" :key="u" class="campo" style="min-width: 240px">
        <span>Template for all rows in {{ { PAR: 'pairs', UN: 'units', CJ: 'prepack cartons' }[u] }}</span>
        <Seleccion @change="aplicarATodas(u, $event)">
          <option value="">Choose template…</option>
          <option v-for="t in plantillasDe(u)" :key="t.id" :value="t.id">{{ t.nombre }} ({{ t.cantidad_por_caja }} per carton)</option>
        </Seleccion>
      </label>
    </div>
    <div class="tabla-marco" style="max-height: 320px; overflow-y: auto; box-shadow: none">
      <table class="tabla">
        <thead><tr><th>Row</th><th>Rule</th><th class="num">Not packed</th><th>Template</th><th class="num">Cartons</th><th class="num">Leftover</th></tr></thead>
        <tbody>
          <tr v-for="(f, i) in calculoAuto.filas" :key="f.pl_linea_id">
            <td>{{ f.ref }}</td>
            <td><span class="etiqueta" :class="REGLAS[f.regla]?.[1]" style="margin-left: 0">{{ f.regla_txt }}</span></td>
            <td class="num">{{ cantTxt(f.sin_caja, f.unidad) }}</td>
            <td>
              <Seleccion v-model="modal.filas[i].plantilla_id" class="entrada" style="max-width: 210px" :aria-label="`Template for ${f.ref}`">
                <option value="omitir">Do not pack this row</option>
                <option v-if="f.regla !== 'LIBRE'" value="">No template (dimensions later)</option>
                <option v-else value="" disabled>Choose a template…</option>
                <option v-for="t in plantillasFila(f)" :key="t.id" :value="t.id">{{ t.nombre }}<template v-if="f.regla === 'LIBRE'"> ({{ t.cantidad_por_caja }})</template></option>
              </Seleccion>
            </td>
            <template v-if="f.cajas !== null">
              <td class="num">{{ f.cajas }}</td>
              <td class="num"><span :class="{ 'etiqueta aviso': f.sobrante }">{{ f.sobrante }}</span></td>
            </template>
            <td v-else colspan="2" class="apagado">{{ f.nota || 'Skipped' }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <div class="nota bloque">
      <b>{{ plural(calculoAuto.completas, 'full carton', 'full cartons') }}</b> will be created on {{ plural(calculoAuto.validas, 'row', 'rows') }}.
    </div>
    <div v-if="calculoAuto.sobrante" class="nota aviso bloque">
      {{ plural(calculoAuto.parciales, 'row leaves', 'rows leave') }} a leftover that does not fill a carton ({{ fmtNum(calculoAuto.sobrante) }} in total). What should we do with it?
      <label class="check mt-chico"><input v-model="modal.sobrante" type="radio" value="caja_parcial" /> One partial carton per row, with the template dimensions and an estimated weight (you confirm it later). With a casepack it is flagged as an incomplete carton.</label>
      <label class="check mt-chico"><input v-model="modal.sobrante" type="radio" value="sin_caja" /> Leave it unpacked to build mixed cartons by hand</label>
    </div>
    <template #pie>
      <router-link class="btn btn-fantasma" to="/plantillas" style="margin-right: auto">Manage templates</router-link>
      <button class="btn" @click="modal = null">Cancel</button>
      <button class="btn btn-primario" :disabled="ocupado || !calculoAuto.validas" @click="empacarAuto"><Icono nombre="varita" :tam="15" />Pack</button>
    </template>
  </Modal>

  <Modal v-if="modal?.tipo === 'caja'" :titulo="modal.items.length > 1 ? 'Mixed carton' : 'Manual carton'" ancho="700px" @cerrar="modal = null">
    <div class="rejilla-campos">
      <label class="campo"><span class="req">Number of identical cartons</span><input v-model.number="modal.num_cajas" type="number" min="1" /></label>
      <label class="campo"><span>Dimensions and weights from a template (optional)</span>
        <Seleccion v-model="modal.plantilla_id">
          <option value="">No template</option>
          <option v-for="t in plantillas" :key="t.id" :value="t.id">{{ t.nombre }}</option>
        </Seleccion>
      </label>
    </div>
    <div class="tabla-marco" style="box-shadow: none">
      <table class="tabla">
        <thead><tr><th>Row</th><th class="num">Not packed</th><th class="num"><span class="req">Per carton</span></th><th class="num">Total</th></tr></thead>
        <tbody>
          <tr v-for="i in modal.items" :key="i.pl_linea_id">
            <td>{{ i.ref }}<span v-if="i.inner" class="sub">inner packs of {{ i.inner }}{{ i.cantidad_por_caja ? innerTxt(i.cantidad_por_caja, i.inner) : '' }}</span></td>
            <td class="num">{{ cantTxt(i.sin_caja, i.unidad) }}</td>
            <td class="num"><input v-model.number="i.cantidad_por_caja" class="celda num" type="number" :min="i.inner || 1" :step="i.inner || 1" style="width: 90px; border-color: var(--linea)" :aria-label="`Per carton ${i.ref}`" /></td>
            <td class="num"><span :class="{ 'etiqueta error': i.cantidad_por_caja * modal.num_cajas > i.sin_caja }">{{ fmtNum((i.cantidad_por_caja || 0) * modal.num_cajas) }}</span></td>
          </tr>
        </tbody>
      </table>
    </div>
    <p class="ayuda">Leave blank what you want to take from the template{{ plantillaModal ? ` (${plantillaModal.largo}×${plantillaModal.ancho}×${plantillaModal.alto} cm, ${plantillaModal.peso_bruto} kg gross)` : '' }}. With an inner pack the quantity per carton must be a multiple of it; a casepack is exact.</p>
    <div class="rejilla-campos">
      <label class="campo"><span>Largo cm</span><input v-model="modal.valores.largo" type="number" min="0" step="any" /></label>
      <label class="campo"><span>Ancho cm</span><input v-model="modal.valores.ancho" type="number" min="0" step="any" /></label>
      <label class="campo"><span>Alto cm</span><input v-model="modal.valores.alto" type="number" min="0" step="any" /></label>
      <label class="campo"><span>Peso neto por caja kg</span><input v-model="modal.valores.peso_neto_caja" type="number" min="0" step="any" /></label>
      <label class="campo"><span>Peso bruto por caja kg</span><input v-model="modal.valores.peso_bruto_caja" type="number" min="0" step="any" /></label>
      <label class="campo"><span>Remark</span><input v-model="modal.valores.observacion" /></label>
    </div>
    <template #pie>
      <button class="btn" @click="modal = null">Cancel</button>
      <button class="btn btn-primario" :disabled="ocupado || cajaInvalida" @click="crearCaja">Create</button>
    </template>
  </Modal>

  <Modal v-if="modal?.tipo === 'mover' || modal?.tipo === 'quitar'" :titulo="modal.tipo === 'mover' ? 'Split into another packing list' : 'Remove from the packing list'" ancho="660px" @cerrar="modal = null">
    <label v-if="modal.tipo === 'mover'" class="campo"><span>Destination PL</span>
      <Seleccion v-model="modal.destino">
        <option v-for="o in pl.otros_pl" :key="o.id" :value="o.id">{{ o.numero }}</option>
        <option value="">A new packing list</option>
      </Seleccion>
    </label>
    <p v-else class="ayuda">The quantity goes back to the invoice as pending assignment to a packing list.</p>
    <div class="tabla-marco" style="max-height: 300px; overflow-y: auto; box-shadow: none">
      <table class="tabla">
        <thead><tr><th>Row</th><th class="num">Not packed</th><th class="num">{{ modal.tipo === 'mover' ? 'Move' : 'Remove' }}</th></tr></thead>
        <tbody>
          <tr v-for="fm in modal.filas" :key="fm.pl_linea_id">
            <td>{{ fm.ref }}</td>
            <td class="num">{{ cantTxt(fm.sin_caja, fm.unidad) }}</td>
            <td class="num"><input v-model.number="fm.cantidad" class="celda num" type="number" min="0" :step="fm.inner || 1" :max="fm.sin_caja" style="width: 90px; border-color: var(--linea)" :aria-label="`Quantity ${fm.ref}`" /></td>
          </tr>
        </tbody>
      </table>
    </div>
    <p class="ayuda">Put 0 on the rows you do not want to touch. Only unpacked quantities move (in whole inner packs); to take whole cartons use “Move to another PL” on the Cartons tab.</p>
    <template #pie>
      <button class="btn" @click="modal = null">Cancel</button>
      <button class="btn btn-primario" :disabled="ocupado || movInvalido" @click="modal.tipo === 'mover' ? mover() : quitar()">
        {{ modal.tipo === 'mover' ? 'Move' : 'Remove from PL' }}
      </button>
    </template>
  </Modal>

  <Modal v-if="modal?.tipo === 'editar_cajas'" :titulo="`Dimensions and weights of ${plural(modal.cajas, 'carton', 'cartons')}`" ancho="640px" @cerrar="modal = null">
    <label class="campo"><span>Copy from a template (optional)</span>
      <Seleccion v-model="modal.plantilla_id">
        <option value="">Do not copy</option>
        <option v-for="t in plantillas" :key="t.id" :value="t.id">{{ t.nombre }} · {{ t.largo }}×{{ t.ancho }}×{{ t.alto }} cm, {{ t.peso_bruto }} kg</option>
      </Seleccion>
    </label>
    <p class="ayuda">Leave blank what you do not want to change. What you type here overrides the template. Entering a weight removes the estimated flag.</p>
    <div class="rejilla-campos">
      <label class="campo"><span>Largo cm</span><input v-model="modal.valores.largo" type="number" min="0" step="any" /></label>
      <label class="campo"><span>Ancho cm</span><input v-model="modal.valores.ancho" type="number" min="0" step="any" /></label>
      <label class="campo"><span>Alto cm</span><input v-model="modal.valores.alto" type="number" min="0" step="any" /></label>
      <label class="campo"><span>Peso neto por caja kg</span><input v-model="modal.valores.peso_neto_caja" type="number" min="0" step="any" /></label>
      <label class="campo"><span>Peso bruto por caja kg</span><input v-model="modal.valores.peso_bruto_caja" type="number" min="0" step="any" /></label>
      <label class="campo"><span>Cartons per group</span><input v-model="modal.valores.num_cajas" type="number" min="1" /></label>
      <label class="campo" style="grid-column: 1 / -1"><span>Remark</span><input v-model="modal.valores.observacion" /></label>
    </div>
    <template #pie>
      <button class="btn" @click="modal = null">Cancel</button>
      <button class="btn btn-primario" :disabled="ocupado" @click="editarCajas">Apply</button>
    </template>
  </Modal>

  <Modal v-if="modal?.tipo === 'mover_cajas'" titulo="Move cartons to another packing list" ancho="600px" @cerrar="modal = null">
    <label class="campo"><span>Destination PL</span>
      <Seleccion v-model="modal.destino">
        <option v-for="o in pl.otros_pl" :key="o.id" :value="o.id">{{ o.numero }}</option>
        <option value="">A new packing list</option>
      </Seleccion>
    </label>
    <div class="tabla-marco" style="box-shadow: none">
      <table class="tabla">
        <thead><tr><th>Cartons</th><th class="num">Available</th><th class="num">Move</th></tr></thead>
        <tbody>
          <tr v-for="gm in modal.grupos" :key="gm.grupo_id">
            <td class="cajas-rango">{{ gm.rango }}</td>
            <td class="num">{{ gm.max }}</td>
            <td class="num"><input v-model.number="gm.num_cajas" class="celda num" type="number" min="1" :max="gm.max" style="width: 80px; border-color: var(--linea)" :aria-label="`Cartons to move from ${gm.rango}`" /></td>
          </tr>
        </tbody>
      </table>
    </div>
    <p class="ayuda">The contents travel with their cartons. Numbering is recalculated in both packing lists.</p>
    <template #pie>
      <button class="btn" @click="modal = null">Cancel</button>
      <button class="btn btn-primario" :disabled="ocupado || modal.grupos.some((g) => !(g.num_cajas >= 1) || g.num_cajas > g.max)" @click="moverCajas">Move cartons</button>
    </template>
  </Modal>

  <Modal v-if="modal?.tipo === 'guardar_plantilla'" titulo="Save as template" @cerrar="modal = null">
    <label class="campo"><span class="req">Template name</span><input v-model="modal.nombre" placeholder="For example: 12-pair carton large sizes" /></label>
    <p class="ayuda">Saves the quantity per carton, dimensions and weights to use in auto-pack.</p>
    <template #pie>
      <button class="btn" @click="modal = null">Cancel</button>
      <button class="btn btn-primario" :disabled="ocupado || !modal.nombre.trim()" @click="guardarPlantilla">Save template</button>
    </template>
  </Modal>

  <Modal v-if="modal?.tipo === 'pallet'" titulo="Palletize cartons" ancho="560px" @cerrar="modal = null">
    <p>{{ plural(cajasSel, 'carton', 'cartons') }} selected. If the goods travel on pallets, group them into pallets with their dimensions.</p>
    <label class="campo"><span>Pallet</span>
      <Seleccion v-model="modal.destino">
        <option value="">New pallet</option>
        <option v-for="p in pl.pallets" :key="p.id" :value="p.id">Add to pallet {{ p.numero }} ({{ p.cajas }} cartons)</option>
      </Seleccion>
    </label>
    <div v-if="!modal.destino" class="rejilla-campos">
      <label class="campo"><span class="req">Length cm</span><input v-model.number="modal.largo" type="number" min="1" /></label>
      <label class="campo"><span class="req">Width cm</span><input v-model.number="modal.ancho" type="number" min="1" /></label>
      <label class="campo"><span class="req">Height cm (loaded)</span><input v-model.number="modal.alto" type="number" min="1" /></label>
      <label class="campo"><span>Tare kg (pallet)</span><input v-model.number="modal.peso_tara" type="number" min="0" /></label>
    </div>
    <template #pie>
      <button class="btn" @click="modal = null">Cancel</button>
      <button class="btn btn-primario" :disabled="ocupado || (!modal.destino && !(modal.largo > 0 && modal.ancho > 0 && modal.alto > 0))" @click="paletizar">Palletize</button>
    </template>
  </Modal>

  <Modal v-if="modal?.tipo === 'desempacar'" titulo="Unpack cartons" @cerrar="modal = null">
    <p>{{ plural(cajasSel, 'carton is', 'cartons are') }} removed and the contents go back to “To pack”.</p>
    <template #pie>
      <button class="btn" @click="modal = null">Cancel</button>
      <button class="btn btn-peligro" :disabled="ocupado" @click="desempacar">Unpack</button>
    </template>
  </Modal>

  <Modal v-if="modal?.tipo === 'pendientes'" titulo="Pending to finalize" ancho="620px" @cerrar="modal = null">
    <ul class="lista-mensajes"><li v-for="(d, i) in modal.detalle" :key="i">{{ textoDetalle(d) }}</li></ul>
    <template #pie><button class="btn btn-primario" @click="modal = null; tab = 'revision'">See in review</button></template>
  </Modal>

  <Modal v-if="modal?.tipo === 'estado'" :titulo="modal.accion === 'reabrir' ? 'Reopen packing list' : 'Cancel packing list'" @cerrar="modal = null">
    <p v-if="modal.accion === 'reabrir'">It becomes editable again. If it was confirmed in a load unit, the assignment becomes tentative.</p>
    <p v-else>Its quantities go back to the invoice as pending assignment.</p>
    <label class="campo"><span :class="{ req: !(modal.accion === 'cancelar' && pl?.estado === 'BORRADOR') }">Reason{{ modal.accion === 'cancelar' && pl?.estado === 'BORRADOR' ? ' (optional)' : '' }}</span><textarea v-model="modal.motivo"></textarea></label>
    <template #pie>
      <button class="btn" @click="modal = null">Back</button>
      <button class="btn" :class="modal.accion === 'cancelar' ? 'btn-peligro' : 'btn-primario'" :disabled="ocupado" @click="cambiarEstado">
        {{ modal.accion === 'reabrir' ? 'Reopen' : 'Cancel packing list' }}
      </button>
    </template>
  </Modal>
  <ExplosionPrepack v-if="explosion" :sku="explosion.sku" :cajas="explosion.cajas" @cerrar="explosion = null" />
</template>
