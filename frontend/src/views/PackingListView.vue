<script setup>
import { buscador } from '../busqueda.js'
import { t, tx } from '../i18n/index.js'
import { computed, onMounted, reactive, ref, watch } from 'vue'
import Seleccion from '../components/Seleccion.vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api'
import Anillo from '../components/Anillo.vue'
import DestinosYUnidades from '../components/DestinosYUnidades.vue'
import BarraSeleccion from '../components/BarraSeleccion.vue'
import ArbolEmpaque from '../components/ArbolEmpaque.vue'
import CeldaEditable from '../components/CeldaEditable.vue'
import CargaMasiva from '../components/CargaMasiva.vue'
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
import { filasDefecto } from '../stores/preferencias'

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
const ref_ = (l) => `${l.estilo || l.codigo_sap}${l.color ? ` ${l.color}` : ''}${l.talla ? t(' · size {0}', [l.talla]) : ''}`

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
    { clave: 'contenido', titulo: t('All contents are in cartons (whole inner packs)'), faltan: [...otros, ...sinCaja], accion: 'empacar' },
    { clave: 'medidas', titulo: t('Every carton has dimensions'), faltan: medidas, accion: 'cajas' },
    { clave: 'pesos', titulo: t('Every carton has net and gross weight'), faltan: pesos, accion: 'cajas' },
    { clave: 'estimados', titulo: t('Estimated weights are confirmed'), faltan: estimado, accion: 'confirmar' },
  ]
})
const listoParaFinalizar = computed(() => editable.value && !(pl.value?.validaciones || []).length)

const pasos = computed(() => {
  if (!pl.value) return []
  const fin = pl.value.estado === 'FINALIZADO'
  const empacado = !pendientes.value.length && pl.value.lineas.length > 0
  const datosOk = revision.value.slice(1).every((r) => !r.faltan.length)
  return [
    { titulo: t('Contents'), estado: pl.value.lineas.length ? 'hecho' : 'actual', detalle: `${plural(pl.value.lineas.length, t('row'), t('rows'))} · ${porUnidadTxt(pl.value.totales.por_unidad, 'cantidad')}` },
    { titulo: t('Pack'), estado: empacado || fin ? 'hecho' : 'actual', detalle: empacado ? plural(pl.value.totales.cajas, t('carton'), t('cartons')) : t('{0} not packed', [porUnidadTxt(pl.value.totales.por_unidad, 'sin_caja')]) },
    { titulo: t('Dimensions and weights'), estado: (empacado && datosOk) || fin ? 'hecho' : estimadas.value.length ? 'alerta' : empacado ? 'actual' : 'pendiente',
      detalle: estimadas.value.length ? t('{0} with estimated weight', [plural(estimadas.value.length, t('group'), t('groups'))]) : !pl.value.grupos.length ? t('After packing') : datosOk ? t('Complete') : t('To complete') },
    { titulo: t('Finalize'), estado: fin ? 'hecho' : listoParaFinalizar.value ? 'actual' : 'pendiente', detalle: fin ? t('Ready to ship') : pl.value.estado === 'EN_CORRECCION' ? t('In correction') : t('Pending') },
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
  const coincide = buscador(filtro.texto)
  return (pl.value?.lineas || []).filter((l) =>
    (!filtro.solo_pendiente || l.sin_caja > 0) && coincide([l.codigo_sap, l.estilo, l.color, l.talla, l.oc_numero, l.upc, l.descripcion]))
})
const tablaL = useTabla(lineasFiltradas, { porPagina: filasDefecto(), valores: { oc: (l) => `${l.oc_numero}-${String(l.posicion).padStart(5, '0')}` } })
// La tabla de cajas muestra los bultos (y lo suelto que no va dentro de otro empaque);
// los inner packs y los pallets se ven en la estructura física
const cajasLista = computed(() => (pl.value?.grupos || []).filter((g) => g.cuenta_como === 'BULTO' || (!g.padre_id && g.cuenta_como !== 'SOPORTE')))
const tiposEmpaque = computed(() => pl.value?.tipos_empaque || [])
const tablaG = useTabla(cajasLista, { porPagina: filasDefecto(), valores: { rango: (g) => g.desde, etiqueta: (g) => g.etiqueta?.tipo } })
const idsFiltrados = computed(() => lineasFiltradas.value.map((l) => l.id))

// Packing rule of the PO line: prepack (1 size run per carton), exact casepack
// or free; with an inner pack, cartons carry whole inner packs
const REGLAS = { PREPACK: [t('Prepack'), 'acento'], CASEPACK: [t('Casepack'), 'info'], LIBRE: [t('Free'), ''] }
// La regla dice cómo se arma la caja; las cantidades van en columnas aparte
// (por caja, por inner pack e inner packs por caja) para no leer "3x4" ambiguo
const reglaTxt = (l) => (l.regla === 'PREPACK' ? t('Prepack {0}', [l.prepack || '']) : l.regla === 'CASEPACK' ? t('Casepack') : t('Free'))
const porCajaLinea = (l) => (l.regla === 'PREPACK' ? l.unidades_por_caja : l.regla === 'CASEPACK' ? l.casepack : null)
const innersPorCaja = (l) => (porCajaLinea(l) && l.inner_pack && l.regla !== 'PREPACK' ? porCajaLinea(l) / l.inner_pack : null)
async function guardarNumero(valor) {
  let r
  try {
    r = await api.put(`/packing-lists/${props.id}/numero`, { version: pl.value.version, numero: valor })
  } catch (e) {
    errorApi(e)
    throw e
  }
  pl.value.version = r.version
  pl.value.numero = r.numero
  avisar(t('Packing list number saved: {0}.', [r.numero]))
}
async function guardarInner(l, valor) {
  const n = valor === '' || valor === null ? null : Number(valor)
  const r = await api.put(`/packing-lists/${props.id}/lineas/${l.id}/inner`, { version: pl.value.version, inner_pack: n })
  pl.value.version = r.version
  await cargar()
  avisar(n ? t('Inner pack of {0} set for {1}.', [n, l.codigo_sap]) : t('Inner pack removed for {0}.', [l.codigo_sap]))
}
const innerTxt = (cant, inner) => (inner ? t(' · {0} inner pack{1} of {2}', [fmtNum(cant / inner), cant / inner === 1 ? '' : 's', inner]) : '')
const porCajaRegla = (l) => (l.regla === 'PREPACK' ? 1 : l.regla === 'CASEPACK' ? l.casepack : null)
const selLineas = computed(() => (pl.value?.lineas || []).filter((l) => selL.tiene(l.id)))
const selConPendiente = computed(() => selLineas.value.filter((l) => l.sin_caja > 0))
const resumenSelLineas = computed(() => {
  const r = {}
  for (const l of selLineas.value) r[l.unidad] = (r[l.unidad] || 0) + l.sin_caja
  return t('{0} not packed', [porUnidadTxt(r, null)])
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
    const plant = plantillas.value.find((x) => x.id === f.plantilla_id)
    const porCaja = f.por_caja || plant?.cantidad_por_caja
    if (!porCaja || f.plantilla_id === 'omitir') return { ...f, cajas: null, sobrante: null }
    // The template must hold whole inner packs (the server skips it otherwise)
    if (f.inner && porCaja % f.inner) return { ...f, cajas: null, sobrante: null, nota: t('Template is not a multiple of the inner pack ({0})', [f.inner]) }
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
    const partesTxt = [plural(r.resumen.cajas_completas, t('full carton'), t('full cartons'))]
    if (r.resumen.sobrante_total && m.sobrante === 'caja_parcial') partesTxt.push(plural(r.resumen.filas_con_sobrante, t('partial carton (confirm its weight)'), t('partial cartons (confirm their weights)')))
    if (r.resumen.sobrante_total && m.sobrante === 'sin_caja') partesTxt.push(t('{0} left unpacked', [fmtNum(r.resumen.sobrante_total)]))
    return t('Done: {0}.', [partesTxt.join(' and ')])
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
    tipo_empaque_id: '',
    valores: { largo: '', ancho: '', alto: '', tara: '', peso_neto_caja: '', observacion: '' },
    items: selConPendiente.value.map((l) => ({
      pl_linea_id: l.id, ref: ref_(l), unidad: l.unidad, sin_caja: l.sin_caja, inner: l.inner_pack, peso_unitario: l.peso_unitario,
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
    tipo_empaque_id: m.tipo_empaque_id || null,
    items: m.items.map((i) => ({ pl_linea_id: i.pl_linea_id, cantidad_por_caja: Number(i.cantidad_por_caja) })),
    ...valores,
  }), m.items.length > 1 ? t('Mixed carton created.') : t('{0} created.', [plural(m.num_cajas, t('carton'), t('cartons'))]))
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
    (r) => t('Quantities moved to {0}.', [r.destino_numero]))
  selL.limpiar()
}
function quitar() {
  accion(() => api.post(url('/quitar'), { version: pl.value.version, movimientos: movimientos() }),
    t('Quantities returned to the invoice; they are pending assignment to a packing list.'))
  selL.limpiar()
}

// ---- Cajas -----------------------------------------------------------------
const selGrupos = computed(() => (pl.value?.grupos || []).filter((g) => selG.tiene(g.id)))
const idsGrupos = computed(() => cajasLista.value.map((g) => g.id))
const cajasSel = computed(() => selGrupos.value.reduce((a, g) => a + g.num_cajas, 0))
const rango = (g) => g.etiqueta_rango || (g.desde === g.hasta ? `${g.desde}` : `${g.desde}–${g.hasta}`)
// Si algún artículo no tiene peso unitario, el neto se escribe a mano
const faltaPeso = (filas) => filas.some((x) => x.peso_unitario == null)

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
    tipo_empaque_id: '', manual: grupos.some((g) => !g.peso_calculado),
    valores: { num_cajas: '', largo: '', ancho: '', alto: '', tara: '', peso_neto_caja: '', observacion: '' },
  }
}
function editarCajas() {
  const m = modal.value
  const valores = Object.fromEntries(Object.entries(m.valores).filter(([, v]) => v !== '')
    .map(([k, v]) => [k, k === 'observacion' ? v : Number(v)]))
  if (!Object.keys(valores).length && !m.plantilla_id && !m.tipo_empaque_id) return avisar(t('Choose a template or enter at least one value.'), 'error')
  accion(() => api.patch(url('/cajas'), {
    version: pl.value.version, grupo_ids: m.grupo_ids, ...valores, ...(m.plantilla_id ? { desde_plantilla_id: m.plantilla_id } : {}),
    ...(m.tipo_empaque_id ? { tipo_empaque_id: m.tipo_empaque_id } : {}),
  }), t('{0} updated.', [plural(m.cajas, t('carton'), t('cartons'))]))
}
function confirmarPesos(grupos) {
  accion(() => api.patch(url('/cajas'), { version: pl.value.version, grupo_ids: grupos.map((g) => g.id), confirmar_pesos: true }),
    t('Weights confirmed on {0}.', [plural(grupos.length, t('carton group'), t('carton groups'))]))
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
  }), (r) => t('Cartons moved to {0} with their contents.', [r.destino_numero]))
}
// ---- Pallets -----------------------------------------------------------------
// Tipos que pueden llevar lo seleccionado (según el catálogo de tipos de empaque)
const contenedoresPosibles = computed(() => {
  const sel = new Set(selGrupos.value.map((g) => g.tipo_empaque_id).filter(Boolean))
  return tiposEmpaque.value.filter((x) => [...sel].every((id) => x.contiene.includes(id)) && x.contiene.length)
})
function tipoContenedor(id) {
  const x = tiposEmpaque.value.find((y) => y.id === Number(id))
  if (!x || !modal.value) return
  Object.assign(modal.value, { tipo_empaque_id: x.id, largo: x.largo || '', ancho: x.ancho || '', peso_tara: x.tara ?? 0,
    alto: x.cuenta_como === 'SOPORTE' ? '' : x.alto || '' })
}
function abrirPaletizar() {
  modal.value = { tipo: 'pallet', destino: '', tipo_empaque_id: '', num: 1, largo: '', ancho: '', alto: '', peso_tara: 0 }
  const def = contenedoresPosibles.value.find((x) => x.cuenta_como === 'SOPORTE') || contenedoresPosibles.value[0]
  if (def) tipoContenedor(def.id)
}
const nombreTipo = (id) => tiposEmpaque.value.find((x) => x.id === Number(id))?.nombre || t('Pallet')
function paletizar() {
  const m = modal.value
  const nuevo = !m.destino
  const cajas = cajasSel.value
  accion(() => api.post(url('/pallets'), {
    version: pl.value.version, grupo_ids: selG.lista(), pallet_id: m.destino || null,
    ...(nuevo ? { tipo_empaque_id: m.tipo_empaque_id || null, num: Number(m.num) || 1, largo: Number(m.largo), ancho: Number(m.ancho),
      alto: Number(m.alto), peso_tara: Number(m.peso_tara) || 0 } : {}),
  }), (r) => t('{0} in {1} {2}.', [plural(cajas, t('carton'), t('cartons')), nombreTipo(m.tipo_empaque_id).toLowerCase(), r.numero]))
  selG.limpiar()
}
function despaletizar(grupoIds, palletId = null) {
  accion(() => api.post(url('/pallets/quitar'), { version: pl.value.version, grupo_ids: grupoIds, pallet_id: palletId }),
    palletId ? t('Pallet undone; its cartons are loose.') : t('Cartons taken off the pallet.'))
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
    t('Cartons unpacked; their contents went back to “To pack”.'))
}
function guardarPlantilla() {
  accion(() => api.post(url(`/cajas/${modal.value.grupo_id}/plantilla`), { nombre: modal.value.nombre }),
    (r) => t('Template “{0}” saved; you can now use it when packing.', [r.nombre]))
}

// ---- Estados, recepción y exportación -------------------------------------
const finalizar = () => accion(() => api.post(url('/finalizar'), { version: pl.value.version }), t('Packing list finalized.'))
const agregarPendientes = () => accion(() => api.post(url('/agregar'), { version: pl.value.version }),
  (r) => t('{0} added from the invoice.', [fmtNum(r.agregado)]))
function cambiarEstado() {
  const { accion: a, motivo } = modal.value
  accion(() => api.post(url(`/${a}`), { motivo }), (r) => (a === 'reabrir'
    ? t('Packing list reopened.{0}', [r.nota ? ` ${r.nota}` : '']) : t('Packing list cancelled; its quantities went back to the invoice.')))
}
function guardarRecepcion() {
  accion(() => api.post(url('/recepcion'), {
    lineas: pl.value.lineas.map((l) => ({ pl_linea_id: l.id, ...recepcion[l.id], cantidad_recibida: Number(recepcion[l.id].cantidad_recibida), cantidad_danada: Number(recepcion[l.id].cantidad_danada) })),
  }), (r) => (r.diferencias.length ? t('Receipt saved with {0}.', [plural(r.diferencias.length, t('difference'), t('differences'))]) : t('Receipt saved with no differences.')))
}
const descargar = (formato) => api.descargar(url('/exportar'), t('packing_list.{0}', [formato]), { formato }).catch(errorApi)

function irA(accionRevision) {
  if (accionRevision === 'confirmar') confirmarPesos(estimadas.value)
  else tab.value = accionRevision
}

onMounted(cargar)
</script>

<template>
  <template v-if="pl">
    <router-link :to="`/facturas/${pl.factura.id}?tab=pl`" class="volver"><Icono nombre="atras" :tam="15" />{{ t('Invoice {0}', [pl.factura.nombre]) }}</router-link>
    <section class="doc-cabeza">
      <div class="doc-fila">
        <span v-if="!editable" class="doc-numero">{{ tx(pl.numero) }}</span>
        <CeldaEditable v-else class="doc-numero numero-editable" :valor="pl.numero" :guardar="guardarNumero"
                       :etiqueta="t('Packing list number')" :title="t('Your own packing list number; you can change it while it is not finalized')" />
        <EstadoBadge :estado="pl.estado" />
        <span class="doc-sub">{{ tx(pl.factura.nombre) }} · {{ tx(pl.factura.proveedor) }}</span>
        <div class="doc-acciones">
          <MasOpciones>
            <button class="btn btn-fantasma" :title="t('Packing list as PDF, ready to print and sign')" @click="descargar('pdf')"><Icono nombre="descargar" />PDF</button>
            <button class="btn btn-fantasma" :title="t('Packing list as Excel')" @click="descargar('xlsx')"><Icono nombre="descargar" />{{ t('Excel') }}</button>
            <button v-if="pl.puede.reabrir" class="btn" @click="modal = { tipo: 'estado', accion: 'reabrir', motivo: '' }">{{ t('Reopen to correct') }}</button>
            <button v-if="pl.puede.cancelar" class="btn btn-peligro" @click="modal = { tipo: 'estado', accion: 'cancelar', motivo: '' }">{{ t('Cancel PL') }}</button>
          </MasOpciones>
          <button v-if="pl.puede.finalizar" class="btn" :class="{ 'btn-primario': listoParaFinalizar }" :disabled="ocupado" @click="listoParaFinalizar ? finalizar() : (tab = 'revision')">
            <Icono nombre="check" />{{ tx(listoParaFinalizar ? t('Finalize packing list') : t('Finalize ({0} pending)', [pl.validaciones.length])) }}
          </button>
        </div>
      </div>
      <div class="empaque-resumen">
        <Anillo :porcentaje="avanceEmpaque" :titulo="t('Packed')" :detalle="tx(pendientes.length ? t('{0} missing', [porUnidadTxt(pl.totales.por_unidad, 'sin_caja')]) : t('{0} in cartons', [porUnidadTxt(pl.totales.por_unidad, 'cantidad')]))" />
        <div class="cifra"><span>{{ t('Cartons') }}</span><b>{{ fmtNum(pl.totales.cajas) }}</b></div>
        <div class="cifra"><span>{{ t('Net weight') }}</span><b>{{ t('{0} kg', [fmtNum(pl.totales.peso_neto, 1)]) }}</b></div>
        <div class="cifra"><span>{{ t('Gross weight') }}</span><b>{{ t('{0} kg', [fmtNum(pl.totales.peso_bruto, 1)]) }}</b></div>
        <div class="cifra"><span>{{ t('Volume') }}</span><b>{{ fmtNum(pl.totales.cbm, 2) }} m³</b></div>
        <div v-if="pl.totales.pallets" class="cifra"><span>{{ t('Pallets') }}</span><b>{{ tx(pl.totales.pallets) }}</b></div>
        <div class="cifra"><span>{{ t('Load unit') }}</span>
          <b v-if="pl.transporte" style="font-size: 0.95rem">{{ tx(pl.transporte.unidad) }} · {{ tx(pl.transporte.embarque) }} <EstadoBadge :estado="pl.transporte.asignacion" /></b>
          <b v-else class="apagado" style="font-size: 0.95rem">{{ t('Not assigned') }}</b>
        </div>
      </div>
      <Pasos :pasos="pasos" />
    </section>

    <div v-if="pl.partes" class="partes" style="margin-bottom: 16px">
      <TarjetaParte :titulo="t('Bill to')" icono="factura" :parte="pl.partes.facturar_a" />
      <TarjetaParte :titulo="t('Notify party (receiving plant)')" icono="ubicacion" :parte="pl.partes.notify" />
      <section v-if="pl.partes.destino" class="panel tarjeta-parte">
        <div class="tp-cabeza">
          <span class="tp-icono"><Icono nombre="ruta" :tam="16" /></span>
          <div><span class="eyebrow">{{ t('Final destination') }}</span><b>{{ tx(pl.partes.destino.codigo) }} · {{ tx(pl.partes.destino.nombre || t('Plant not registered')) }}</b></div>
        </div>
        <p class="tp-linea">{{ t('Country of arrival:') }} <b>{{ tx(pl.partes.destino.pais || '—') }}</b></p>
      </section>
    </div>

    <p v-if="editable && pl.saldo_factura > 0" class="nota aviso" style="align-items: center">
      <Icono nombre="info" />
      <span>{{ t('The invoice has {0} not in any packing list.', [fmtNum(pl.saldo_factura)]) }}</span>
      <button class="btn btn-chico separar" :disabled="ocupado" @click="agregarPendientes"><Icono nombre="mas" :tam="14" />{{ t('Add to {0}', [pl.numero]) }}</button>
    </p>

    <div class="pestanas" role="tablist">
      <button v-if="editable" class="pestana" role="tab" :aria-selected="tab === 'empacar'" @click="tab = 'empacar'">
        <Icono nombre="caja" :tam="16" />{{ t('To pack') }}<span class="cuenta" :class="{ alerta: pendientes.length }">{{ tx(pendientes.length) }}</span>
      </button>
      <button class="pestana" role="tab" :aria-selected="tab === 'cajas'" @click="tab = 'cajas'">
        <Icono nombre="lista" :tam="16" />{{ t('Cartons') }}<span class="cuenta">{{ tx(pl.totales.cajas) }}</span>
      </button>
      <button v-if="editable" class="pestana" role="tab" :aria-selected="tab === 'revision'" @click="tab = 'revision'">
        <Icono nombre="check" :tam="16" />{{ t('Review') }}<span class="cuenta" :class="{ alerta: pl.validaciones.length }">{{ tx(pl.validaciones.length || '✓') }}</span>
      </button>
      <button v-if="!editable" class="pestana" role="tab" :aria-selected="tab === 'contenido'" @click="tab = 'contenido'">
        <Icono nombre="lista" :tam="16" />{{ t('Contents') }}<span class="cuenta">{{ tx(pl.lineas.length) }}</span>
      </button>
      <button v-if="pl.puede.recepcion" class="pestana" role="tab" :aria-selected="tab === 'recepcion'" @click="tab = 'recepcion'"><Icono nombre="importar" :tam="16" />{{ t('Receipt') }}</button>
    </div>

    <!-- To pack -->
    <section v-if="tab === 'empacar' && editable">
      <div v-if="!pendientes.length && pl.lineas.length" class="panel vacio">
        <div class="todo-listo" style="justify-content: center">
          <span class="icono-ok"><Icono nombre="check" :tam="22" /></span>
          <div style="text-align: start"><b>{{ t('Everything is in cartons') }}</b><p class="ayuda">{{ t('Check dimensions and weights and finalize the packing list.') }}</p></div>
          <button class="btn btn-primario" @click="tab = 'revision'">{{ t('Go to review') }}<Icono nombre="flecha" :tam="16" /></button>
        </div>
      </div>
      <template v-else>
        <div class="opciones-empaque">
          <button class="opcion recomendada" :disabled="!pendientes.length || (!plantillas.length && !pendientes.some((l) => l.regla !== 'LIBRE'))" @click="abrirAuto(selConPendiente.length > 0)">
            <span class="opcion-icono"><Icono nombre="varita" /></span>
            <b>{{ t('Auto-pack') }} <span class="etiqueta acento">{{ t('Recommended') }}</span></b>
            <span>{{ t('{0} in one step, following each line\'s casepack, inner pack or prepack. The template adds dimensions and weights; you decide what to do with leftovers.', [selConPendiente.length ? t('The {0} selected rows', [selConPendiente.length]) : t('All rows ({0})', [pendientes.length])]) }}</span>
            <span v-if="!plantillas.length" class="etiqueta aviso">{{ t('Create a template first') }}</span>
          </button>
          <button class="opcion" :disabled="!selConPendiente.length" @click="abrirCaja">
            <span class="opcion-icono"><Icono nombre="caja" /></span>
            <b>{{ t('Manual or mixed carton') }}</b>
            <span>{{ t('{0} You set how many go per carton; with several rows it is an assorted carton (same destination only).', [selConPendiente.length ? t('With the {0} selected rows.', [selConPendiente.length]) : t('Select rows below.')]) }}</span>
          </button>
          <button class="opcion" @click="modal = { tipo: 'estructura' }">
            <span class="opcion-icono"><Icono nombre="importar" /></span>
            <b>{{ t('Upload the physical structure') }}</b>
            <span>{{ t('From Excel: one row per item with the identifier of each level (pallet, carton, inner pack…). Identical units are grouped and weights are calculated. Replaces the current packing.') }}</span>
          </button>
          <button class="opcion" :disabled="!pendientes.length" @click="abrirMover">
            <span class="opcion-icono"><Icono nombre="mover" /></span>
            <b>{{ t('Split into another packing list') }}</b>
            <span>{{ t('Move unpacked quantities to another PL of the invoice (or a new one), for example per destination country or for another container.') }}</span>
          </button>
        </div>

        <div class="filtros mt" v-filtros>
          <label class="buscador">
            <Icono nombre="buscar" :tam="16" />
            <input v-model="filtro.texto" type="search" :placeholder="t('Filter by code, style, color, size or PO')" :aria-label="t('Filter contents')" />
          </label>
          <div class="segmentos" role="group" :aria-label="t('Show')">
            <button class="segmento" :aria-pressed="filtro.solo_pendiente" @click="filtro.solo_pendiente = true">{{ t('Not packed') }}<span class="cuenta">{{ tx(pendientes.length) }}</span></button>
            <button class="segmento" :aria-pressed="!filtro.solo_pendiente" @click="filtro.solo_pendiente = false">{{ t('All') }}<span class="cuenta">{{ tx(pl.lineas.length) }}</span></button>
          </div>
        </div>
        <div class="tabla-marco tabla-fija">
          <table class="tabla" v-tarjetas>
            <thead>
              <tr>
                <th class="chk"><input type="checkbox" :aria-label="t('Select all filtered rows')" :checked="selL.todos(idsFiltrados)" @change="selL.alternarTodos(idsFiltrados)" /></th>
                <ThOrden campo="estilo" :orden="tablaL.estado.orden" @ordenar="tablaL.ordenar">{{ t('Item') }}</ThOrden>
                <ThOrden campo="talla" :orden="tablaL.estado.orden" @ordenar="tablaL.ordenar">{{ t('Size') }}</ThOrden>
                <ThOrden campo="oc" :orden="tablaL.estado.orden" @ordenar="tablaL.ordenar">{{ t('PO / line') }}</ThOrden>
                <ThOrden class="col-sec" campo="regla" :orden="tablaL.estado.orden" @ordenar="tablaL.ordenar">{{ t('Rule') }}</ThOrden>
                <th class="num" :title="t('Units or pairs per carton: casepack of the PO or the prepack size run')">{{ t('Per carton') }}</th>
                <th class="num" :title="t('Units or pairs per inner pack; defined here when the PO does not bring it')">{{ t('Per inner pack') }}</th>
                <th class="num col-sec">{{ t('Inner packs per carton') }}</th>
                <ThOrden campo="cantidad" :orden="tablaL.estado.orden" num @ordenar="tablaL.ordenar">{{ t('Quantity') }}</ThOrden>
                <ThOrden campo="en_cajas" :orden="tablaL.estado.orden" num @ordenar="tablaL.ordenar">{{ t('In cartons') }}</ThOrden>
                <ThOrden campo="sin_caja" :orden="tablaL.estado.orden" num @ordenar="tablaL.ordenar">{{ t('Not packed') }}</ThOrden>
                <th class="col-sec">{{ t('Suggested template') }}</th>
                <ThOrden campo="estado_empaque" :orden="tablaL.estado.orden" @ordenar="tablaL.ordenar">{{ t('Packing') }}</ThOrden>
              </tr>
            </thead>
            <tbody>
              <tr v-for="l in tablaL.filas.value" :key="l.id" :class="{ seleccionada: selL.tiene(l.id) }">
                <td class="chk"><input type="checkbox" :aria-label="t('Select {0}', [ref_(l)])" :checked="selL.tiene(l.id)" @change="selL.alternar(l.id)" /></td>
                <td><span v-if="l.marca" class="fuerte">{{ tx(l.marca) }}</span> {{ tx(l.estilo) }} · {{ tx(l.color) }}
                  <span v-if="partes.cuenta[l.factura_linea_id] > 1" class="etiqueta">{{ t('part {0}', [partes.indice[l.id]]) }}</span>
                  <span class="sub codigo">{{ tx(l.codigo_sap) }}</span>
                </td>
                <td><strong>{{ tx(l.talla) }}</strong></td>
                <td class="codigo">{{ tx(l.oc_numero) }} / {{ tx(l.posicion) }}<span v-if="l.centro_destino || l.almacen" class="sub">{{ tx([l.almacen && t('warehouse {0}', [l.almacen]), l.centro_destino && t('destination {0}', [l.centro_destino])].filter(Boolean).join(' · ')) }}</span></td>
                <td>
                  <button v-if="l.regla === 'PREPACK'" type="button" class="etiqueta acento btn-explosion" style="margin-inline-start: 0"
                          :title="t('See the prepack breakdown')" @click="explosion = { sku: l.codigo_sap, cajas: l.cantidad }">{{ tx(reglaTxt(l)) }} <Icono nombre="lupa" :tam="12" /></button>
                  <span v-else class="etiqueta" :class="REGLAS[l.regla]?.[1]" style="margin-inline-start: 0">{{ tx(reglaTxt(l)) }}</span>
                </td>
                <td class="num">{{ porCajaLinea(l) ? cantTxt(porCajaLinea(l), l.regla === 'PREPACK' ? l.unidad_componentes || 'UN' : l.unidad) : '—' }}</td>
                <td class="num" style="width: 96px">
                  <CeldaEditable v-if="editable && l.inner_editable" tipo="number" :min="1" paso="1" :valor="l.inner_pack" :vacia-texto="t('Define')"
                                 :guardar="(v) => guardarInner(l, v)" :etiqueta="t('Per inner pack')" />
                  <template v-else>{{ l.inner_pack ? cantTxt(l.inner_pack, l.unidad) : '—' }}</template>
                </td>
                <td class="num">{{ innersPorCaja(l) ? fmtNum(innersPorCaja(l)) : '—' }}</td>
                <td class="num">{{ cantTxt(l.cantidad, l.unidad) }}</td>
                <td class="num">{{ fmtNum(l.en_cajas) }}</td>
                <td class="num"><strong v-if="l.sin_caja">{{ fmtNum(l.sin_caja) }}</strong><span v-else class="apagado">0</span></td>
                <td>
                  <span v-if="sugerida(l)">{{ tx(nombrePlantilla(sugerida(l))) }}<span v-if="l.plantilla_sugerida_id === sugerida(l)" class="etiqueta info" :title="t('The one you used last time with this item')">{{ t('used before') }}</span></span>
                  <span v-else-if="l.regla !== 'LIBRE'" class="apagado">{{ t('Not needed (uses the casepack)') }}</span>
                  <span v-else class="apagado">{{ t('No template for {0}', [l.unidad === 'PAR' ? t('pairs') : t('units')]) }}</span>
                </td>
                <td>
                  <EstadoBadge :estado="l.estado_empaque" />
                  <span v-if="l.en_parcial" class="etiqueta aviso">{{ t('partial carton') }}</span>
                </td>
              </tr>
              <tr v-if="!lineasFiltradas.length">
                <td colspan="13" class="vacio">{{ tx(pl.lineas.length ? t('No row matches the filter.') : t('The packing list is empty.')) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <Paginacion :page="tablaL.estado.pagina" :size="tablaL.estado.porPagina" :total="tablaL.total.value"
                    @cambiar="(p) => (tablaL.estado.pagina = p)" @tamano="(t) => (tablaL.estado.porPagina = t)" />
        <BarraSeleccion :cantidad="selL.ids.size" :singular="t('row selected')" :plural="t('rows selected')" @limpiar="selL.limpiar()">
          <template #resumen>{{ tx(resumenSelLineas) }}</template>
          <button class="btn btn-primario" :disabled="!selConPendiente.length" @click="abrirAuto(true)"><Icono nombre="varita" :tam="15" />{{ t('Auto-pack') }}</button>
          <button class="btn" :disabled="!selConPendiente.length" @click="abrirCaja"><Icono nombre="caja" :tam="15" />{{ tx(selConPendiente.length > 1 ? t('Mixed carton') : t('Manual carton')) }}</button>
          <button class="btn" :disabled="!selConPendiente.length" @click="abrirMover"><Icono nombre="mover" :tam="15" />{{ t('Move to another PL') }}</button>
          <button class="btn btn-peligro" :disabled="!selConPendiente.length" @click="abrirQuitar">{{ t('Remove from PL') }}</button>
        </BarraSeleccion>
      </template>
    </section>

    <!-- Cartons -->
    <section v-if="tab === 'cajas'">
      <p v-if="editable && estimadas.length" class="nota aviso" style="align-items: center; margin-bottom: 12px">
        <Icono nombre="escala" />
        <span>{{ t('Carton groups with an estimated weight (partial cartons): {0}. Weigh and correct them, or confirm the estimate.', [fmtNum(estimadas.length)]) }}</span>
        <button class="btn btn-chico separar" :disabled="ocupado" @click="confirmarPesos(estimadas)">{{ t('Confirm all estimates') }}</button>
      </p>
      <section v-if="pl.grupos.some((g) => g.padre_id)" class="panel" style="margin-bottom: 14px">
        <div class="panel-cabeza"><div><h2>{{ t('Physical structure') }}</h2>
          <p>{{ t('Packaging inside packaging. Net = products (unit weight of each item); gross adds the tare of every level. The volume is the outer size of the top level.') }}</p></div></div>
        <ArbolEmpaque :grupos="pl.grupos" :editable="editable" :ocupado="ocupado" :guardar="celdaPallet" @deshacer="(g) => despaletizar([], g.id)" />
      </section>
      <p v-if="pl.avisos?.length" class="nota aviso bloque" style="margin-bottom: 12px">
        <Icono nombre="alerta" />
        <span><b>{{ t('Check with the Commercial Brand Manager:') }}</b> <template v-for="a in pl.avisos" :key="a.grupo_id">{{ tx(a.mensaje) }} </template></span>
      </p>
      <div class="tabla-marco tabla-fija">
        <table class="tabla" v-tarjetas>
          <thead>
            <tr>
              <th class="chk"><input type="checkbox" :aria-label="t('Select all cartons')" :checked="selG.todos(idsGrupos)" @change="selG.alternarTodos(idsGrupos)" /></th>
              <ThOrden campo="rango" :orden="tablaG.estado.orden" @ordenar="tablaG.ordenar">{{ t('Cartons') }}</ThOrden>
              <ThOrden campo="etiqueta" :orden="tablaG.estado.orden" @ordenar="tablaG.ordenar">{{ t('Contents per carton') }}</ThOrden>
              <th class="num">{{ t('Inner packs per carton') }}</th>
              <th class="num">{{ t('Per inner pack') }}</th>
              <th class="num">{{ t('Total per carton') }}</th>
              <th class="num">{{ t('Cartons') }}</th>
              <th class="num"><span class="req">{{ t('Length') }}</span></th>
              <th class="num"><span class="req">{{ t('Width') }}</span></th>
              <th class="num"><span class="req">{{ t('Height cm') }}</span></th>
              <th class="num">{{ t('Tare kg') }}</th>
              <th class="num">{{ t('Net/ctn') }}</th>
              <th class="num">{{ t('Gross/ctn kg') }}</th>
              <th class="num col-sec">m³</th>
              <th class="num">{{ t('Gross total') }}</th>
              <th class="col-sec">{{ t('Notes') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="g in tablaG.filas.value" :key="g.id" :class="{ seleccionada: selG.tiene(g.id) }">
              <td class="chk"><input type="checkbox" :aria-label="t('Select cartons {0}', [rango(g)])" :checked="selG.tiene(g.id)" @change="selG.alternar(g.id)" /></td>
              <td class="cajas-rango">{{ tx(rango(g)) }}<span v-if="g.pallet" class="etiqueta acento" :title="t('On pallet')">{{ tx(g.pallet) }}</span>
                <span class="sub">{{ tx(g.tipo) }}</span></td>
              <td class="envolver">
                <div class="caja-items">
                  <div v-for="it in g.contenido" :key="it.pl_linea_id">{{ tx(it.estilo) }} <b>{{ tx(it.talla) }}</b></div>
                </div>
                <div v-if="g.etiqueta" class="fila-flex" style="gap: 4px; margin-top: 4px">
                  <span class="etiqueta" :class="g.etiqueta.tipo === 'ESTANDAR' ? 'ok' : 'acento'" style="margin-inline-start: 0"
                        :title="tx(g.etiqueta.tipo === 'ESTANDAR' ? t('A single PO, style, color and size') : t('Several POs, styles, colors or sizes'))">
                    {{ t('{0} label', [g.etiqueta.tipo === 'ESTANDAR' ? t('Standard') : t('Consolidated')]) }}
                  </span>
                  <span class="ayuda codigo">{{ t('PO {0}', [g.etiqueta.ocs.join(', ')]) }}</span>
                  <span v-if="g.etiqueta.centro_destino" class="ayuda">{{ t('· destination {0}', [g.etiqueta.centro_destino]) }}</span>
                </div>
              </td>
              <td class="num"><div class="caja-items"><div v-for="it in g.contenido" :key="it.pl_linea_id">{{ it.inner_packs_por_caja ? fmtNum(it.inner_packs_por_caja) : '—' }}</div></div></td>
              <td class="num"><div class="caja-items"><div v-for="it in g.contenido" :key="it.pl_linea_id">{{ it.inner_pack ? cantTxt(it.inner_pack, it.unidad) : '—' }}</div></div></td>
              <td class="num"><div class="caja-items"><div v-for="it in g.contenido" :key="it.pl_linea_id">{{ cantTxt(it.cantidad_por_caja, it.unidad) }}</div></div></td>
              <td class="num" style="width: 70px">
                <CeldaEditable v-if="editable" tipo="number" :min="1" paso="1" :valor="g.num_cajas" :guardar="celdaGrupo(g, 'num_cajas')" :etiqueta="t('Number of cartons')" />
                <template v-else>{{ tx(g.num_cajas) }}</template>
              </td>
              <td v-for="campo in ['largo', 'ancho', 'alto', 'tara']" :key="campo" class="num" style="width: 78px">
                <CeldaEditable v-if="editable" tipo="number" :min="0" :valor="g[campo]" :guardar="celdaGrupo(g, campo)" :vacia-texto="tx(campo === 'tara' ? '0' : t('Missing'))" :etiqueta="tx(campo.replaceAll('_', ' '))" />
                <template v-else>{{ fmtNum(g[campo], campo === 'tara' ? 2 : 0) }}</template>
              </td>
              <td class="num" style="width: 82px">
                <CeldaEditable v-if="editable && !g.peso_calculado" tipo="number" :min="0" :valor="g.peso_neto_caja" :guardar="celdaGrupo(g, 'peso_neto_caja')"
                               :vacia-texto="t('Missing')" :etiqueta="t('Net weight per carton (items without unit weight)')" />
                <span v-else :title="t('Calculated: unit weight of each item × quantity')">{{ fmtNum(g.peso_neto_caja, 2) }}</span>
              </td>
              <td class="num" :title="t('Net + tare of the carton and of everything inside it')">{{ fmtNum(g.peso_bruto_caja, 2) }}</td>
              <td class="num">{{ fmtNum(g.cbm_total, 3) }}</td>
              <td class="num">{{ fmtNum(g.peso_bruto_total, 1) }}</td>
              <td>
                <span v-if="g.mixta" class="etiqueta">{{ t('Mixed') }}</span>
                <span v-if="g.es_parcial" class="etiqueta aviso">{{ t('Partial') }}</span>
                <span v-if="g.peso_estimado" class="etiqueta error">{{ t('Estimated weight') }}</span>
                <span v-if="g.plantilla_nombre" class="sub">{{ tx(g.plantilla_nombre) }}</span>
                <span v-if="g.observacion" class="sub">{{ tx(g.observacion) }}</span>
              </td>
            </tr>
            <tr v-if="!pl.grupos.length">
              <td colspan="16" class="vacio">
                <Icono nombre="caja" :tam="28" />
                <p>{{ t('No cartons yet.') }}</p>
                <button v-if="editable" class="btn btn-primario" @click="tab = 'empacar'">{{ t('Start packing') }}</button>
              </td>
            </tr>
          </tbody>
          <tfoot v-if="pl.grupos.length">
            <tr>
              <td></td>
              <td colspan="5">{{ t('Total') }}</td>
              <td class="num">{{ fmtNum(pl.totales.cajas) }}</td>
              <td colspan="6"></td>
              <td class="num">{{ fmtNum(pl.totales.cbm, 3) }}</td>
              <td class="num">{{ fmtNum(pl.totales.peso_bruto, 1) }}</td>
              <td></td>
            </tr>
          </tfoot>
        </table>
      </div>
      <Paginacion :page="tablaG.estado.pagina" :size="tablaG.estado.porPagina" :total="tablaG.total.value"
                  @cambiar="(p) => (tablaG.estado.pagina = p)" @tamano="(t) => (tablaG.estado.porPagina = t)" />
      <BarraSeleccion :cantidad="selG.ids.size" :singular="t('group selected')" :plural="t('groups selected')" @limpiar="selG.limpiar()">
        <template #resumen>{{ plural(cajasSel, t('carton'), t('cartons')) }}</template>
        <template v-if="editable">
          <button class="btn btn-primario" @click="abrirEditarCajas()"><Icono nombre="editar" :tam="15" />{{ t('Dimensions and weights') }}</button>
          <button v-if="selGrupos.some((g) => g.peso_estimado)" class="btn" :disabled="ocupado" @click="confirmarPesos(selGrupos.filter((g) => g.peso_estimado))">{{ t('Confirm weights') }}</button>
          <button class="btn" @click="abrirMoverCajas"><Icono nombre="mover" :tam="15" />{{ t('Move to another PL') }}</button>
          <button class="btn" :disabled="selGrupos.length !== 1 || selGrupos[0].mixta" :title="t('Single-item cartons only')" @click="modal = { tipo: 'guardar_plantilla', grupo_id: selGrupos[0].id, nombre: '' }"><Icono nombre="capas" :tam="15" />{{ t('Save as template') }}</button>
          <button class="btn" @click="abrirPaletizar"><Icono nombre="capas" :tam="15" />{{ t('Put in a pallet or container') }}</button>
          <button v-if="selGrupos.some((g) => g.padre_id)" class="btn" :disabled="ocupado" @click="despaletizar(selGrupos.filter((g) => g.padre_id).map((g) => g.id))">{{ t('Take out of its container') }}</button>
          <button class="btn btn-peligro" @click="modal = { tipo: 'desempacar' }">{{ t('Unpack') }}</button>
        </template>
      </BarraSeleccion>
    </section>

    <!-- Review -->
    <section v-if="tab === 'revision' && editable" class="dos-columnas">
      <div class="panel">
        <div class="panel-cabeza"><div><h2>{{ t('Before finalizing') }}</h2><p>{{ t('Everything must be green. Each point takes you to fix it.') }}</p></div></div>
        <ul class="checklist">
          <li v-for="r in revision" :key="r.clave" :class="r.faltan.length ? 'falta' : 'ok'">
            <span class="marca"><Icono :nombre="r.faltan.length ? 'alerta' : 'check'" :tam="14" /></span>
            <span>
              {{ tx(r.titulo) }}
              <span v-if="r.faltan.length" class="sub ayuda">{{ tx(r.faltan.slice(0, 3).map((e) => e.mensaje).join(' ')) }}<template v-if="r.faltan.length > 3"> {{ t('And {0} more.', [r.faltan.length - 3]) }}</template></span>
            </span>
            <button v-if="r.faltan.length" class="btn btn-chico" :disabled="ocupado" @click="irA(r.accion)">
              {{ tx({ empacar: t('Pack'), cajas: t('Go to cartons'), confirmar: t('Confirm estimates') }[r.accion]) }}
            </button>
          </li>
        </ul>
        <div class="fila-flex mt">
          <button v-if="pl.puede.finalizar" class="btn btn-primario btn-grande" :disabled="ocupado || !listoParaFinalizar" @click="finalizar"><Icono nombre="check" />{{ t('Finalize packing list') }}</button>
          <span v-if="!listoParaFinalizar" class="ayuda">{{ plural(pl.validaciones.length, t('pending item'), t('pending items')) }}</span>
        </div>
      </div>
      <div class="panel">
        <div class="panel-cabeza"><div><h2>{{ t('Packing list summary') }}</h2><p>{{ t('This is how it will appear on the PDF and Excel.') }}</p></div></div>
        <div class="doc-datos" style="margin-top: 0; padding-top: 0; border-top: 0">
          <div class="dato"><span>{{ t('Contents') }}</span><b>{{ porUnidadTxt(pl.totales.por_unidad, 'cantidad') }}</b></div>
          <div class="dato"><span>{{ t('Cartons') }}</span><b>{{ fmtNum(pl.totales.cajas) }}</b></div>
          <div class="dato"><span>{{ t('Net weight') }}</span><b>{{ t('{0} kg', [fmtNum(pl.totales.peso_neto, 2)]) }}</b></div>
          <div class="dato"><span>{{ t('Gross weight') }}</span><b>{{ t('{0} kg', [fmtNum(pl.totales.peso_bruto, 2)]) }}</b></div>
          <div class="dato"><span>{{ t('Volume') }}</span><b>{{ fmtNum(pl.totales.cbm, 3) }} m³</b></div>
          <div class="dato"><span>{{ t('Rows') }}</span><b>{{ tx(pl.lineas.length) }}</b></div>
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
        <table class="tabla" v-tarjetas>
          <thead><tr><th>{{ t('Item') }}</th><th>{{ t('Size') }}</th><th>{{ t('PO / line') }}</th><th class="num">{{ t('Quantity') }}</th><th class="num">{{ t('In cartons') }}</th><th>{{ t('Packing') }}</th></tr></thead>
          <tbody>
            <tr v-for="l in pl.lineas" :key="l.id">
              <td>{{ tx(l.estilo) }} · {{ tx(l.color) }}<span class="sub codigo">{{ tx(l.codigo_sap) }}</span></td>
              <td><strong>{{ tx(l.talla) }}</strong></td>
              <td class="codigo">{{ tx(l.oc_numero) }} / {{ tx(l.posicion) }}<span v-if="l.almacen" class="sub">{{ t('warehouse {0}', [l.almacen]) }}</span></td>
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
        <div><h2>{{ t('Warehouse receipt') }}</h2><p>{{ t('Record what was received and damaged per row; differences are kept in the history.') }}</p></div>
        <button class="btn btn-primario" :disabled="ocupado" @click="guardarRecepcion">{{ t('Save receipt') }}</button>
      </div>
      <div class="tabla-marco" style="box-shadow: none">
        <table class="tabla" v-tarjetas>
          <thead>
            <tr><th>{{ t('Row') }}</th><th class="num">{{ t('Per PL') }}</th><th class="num">{{ t('Received') }}</th><th class="num">{{ t('Damaged') }}</th><th class="num">{{ t('Difference') }}</th><th>{{ t('Remark') }}</th></tr>
          </thead>
          <tbody>
            <tr v-for="l in pl.lineas" :key="l.id">
              <td>{{ tx(l.estilo) }} <b>{{ tx(l.talla) }}</b><span class="sub codigo">{{ tx(l.codigo_sap) }}</span></td>
              <td class="num">{{ cantTxt(l.cantidad, l.unidad) }}</td>
              <td class="num"><input v-model.number="recepcion[l.id].cantidad_recibida" class="celda num" type="number" min="0" style="width: 90px; border-color: var(--linea)" :aria-label="t('Received {0}', [ref_(l)])" /></td>
              <td class="num"><input v-model.number="recepcion[l.id].cantidad_danada" class="celda num" type="number" min="0" style="width: 80px; border-color: var(--linea)" :aria-label="t('Damaged {0}', [ref_(l)])" /></td>
              <td class="num">
                <span :class="{ 'etiqueta error': recepcion[l.id].cantidad_recibida !== l.cantidad }">{{ fmtNum(recepcion[l.id].cantidad_recibida - l.cantidad) }}</span>
              </td>
              <td><input v-model="recepcion[l.id].observacion" class="celda" style="border-color: var(--linea)" :aria-label="t('Remark {0}', [ref_(l)])" /></td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </template>

  <!-- Dialogs -->
  <CargaMasiva v-if="modal?.tipo === 'estructura'" :titulo="t('Upload the physical structure')" :ruta="url('/estructura/importar')"
               :plantilla="url('/estructura/plantilla')" :ayuda="t('The columns are your packaging types. Leave empty the levels you do not use.')"
               @cerrar="modal = null" @cargado="modal = null; cargar(); tab = 'cajas'" />
  <Modal v-if="modal?.tipo === 'auto'" :titulo="t('Auto-pack')" ancho="1000px" @cerrar="modal = null">
    <p class="ayuda">{{ t('Each row is packed into full cartons. If the PO line has a') }} <b>casepack</b>{{ t(', every carton carries exactly that quantity (no mixed sizes); a') }} <b>prepack</b> {{ t('goes one size run per master carton. Without a casepack, the template sets the quantity per carton. With an') }} <b>{{ t('inner pack') }}</b>{{ t(', cartons always carry whole inner packs. The template also adds dimensions and weights.') }}</p>
    <div class="fila-flex">
      <label v-for="u in unidadesAuto" :key="u" class="campo" style="min-width: 240px">
        <span>{{ t('Template for all rows in {0}', [{ PAR: t('pairs'), UN: t('units'), CJ: t('prepack cartons') }[u]]) }}</span>
        <Seleccion @change="aplicarATodas(u, $event)">
          <option value="">{{ t('Choose template…') }}</option>
          <option v-for="txt in plantillasDe(u)" :key="txt.id" :value="txt.id">{{ t('{0} ({1} per carton)', [txt.nombre, txt.cantidad_por_caja]) }}</option>
        </Seleccion>
      </label>
    </div>
    <div class="tabla-marco" style="max-height: 320px; overflow-y: auto; box-shadow: none">
      <table class="tabla" v-tarjetas>
        <thead><tr><th>{{ t('Row') }}</th><th>{{ t('Rule') }}</th><th class="num">{{ t('Not packed') }}</th><th>{{ t('Template') }}</th><th class="num">{{ t('Cartons') }}</th><th class="num">{{ t('Leftover') }}</th></tr></thead>
        <tbody>
          <tr v-for="(f, i) in calculoAuto.filas" :key="f.pl_linea_id">
            <td>{{ tx(f.ref) }}</td>
            <td><span class="etiqueta" :class="REGLAS[f.regla]?.[1]" style="margin-inline-start: 0">{{ tx(f.regla_txt) }}</span></td>
            <td class="num">{{ cantTxt(f.sin_caja, f.unidad) }}</td>
            <td>
              <Seleccion v-model="modal.filas[i].plantilla_id" class="entrada" style="max-width: 210px" :aria-label="t('Template for {0}', [f.ref])">
                <option value="omitir">{{ t('Do not pack this row') }}</option>
                <option v-if="f.regla !== 'LIBRE'" value="">{{ t('No template (dimensions later)') }}</option>
                <option v-else value="" disabled>{{ t('Choose a template…') }}</option>
                <option v-for="txt in plantillasFila(f)" :key="txt.id" :value="txt.id">{{ tx(txt.nombre) }}<template v-if="f.regla === 'LIBRE'"> ({{ tx(txt.cantidad_por_caja) }})</template></option>
              </Seleccion>
            </td>
            <template v-if="f.cajas !== null">
              <td class="num">{{ tx(f.cajas) }}</td>
              <td class="num"><span :class="{ 'etiqueta aviso': f.sobrante }">{{ tx(f.sobrante) }}</span></td>
            </template>
            <td v-else colspan="2" class="apagado">{{ tx(f.nota || t('Skipped')) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <div class="nota bloque">
      <b>{{ plural(calculoAuto.completas, t('full carton'), t('full cartons')) }}</b> {{ t('will be created on {0}.', [plural(calculoAuto.validas, t('row'), t('rows'))]) }}
    </div>
    <div v-if="calculoAuto.sobrante" class="nota aviso bloque">
      {{ t('Rows with a leftover that does not fill a carton: {0} ({1} in total). What should we do with it?', [fmtNum(calculoAuto.parciales), fmtNum(calculoAuto.sobrante)]) }}
      <label class="check mt-chico"><input v-model="modal.sobrante" type="radio" value="caja_parcial" /> {{ t('One partial carton per row, with the template dimensions and an estimated weight (you confirm it later). With a casepack it is flagged as an incomplete carton.') }}</label>
      <label class="check mt-chico"><input v-model="modal.sobrante" type="radio" value="sin_caja" /> {{ t('Leave it unpacked to build mixed cartons by hand') }}</label>
    </div>
    <template #pie>
      <router-link class="btn btn-fantasma" to="/plantillas" style="margin-inline-end: auto">{{ t('Manage templates') }}</router-link>
      <button class="btn" @click="modal = null">{{ t('Cancel') }}</button>
      <button class="btn btn-primario" :disabled="ocupado || !calculoAuto.validas" @click="empacarAuto"><Icono nombre="varita" :tam="15" />{{ t('Pack') }}</button>
    </template>
  </Modal>

  <Modal v-if="modal?.tipo === 'caja'" :titulo="tx(modal.items.length > 1 ? t('Mixed carton') : t('Manual carton'))" ancho="700px" @cerrar="modal = null">
    <div class="rejilla-campos">
      <label class="campo"><span class="req">{{ t('Number of identical cartons') }}</span><input v-model.number="modal.num_cajas" type="number" min="1" /></label>
      <label class="campo"><span>{{ t('Dimensions and tare from a template (optional)') }}</span>
        <Seleccion v-model="modal.plantilla_id">
          <option value="">{{ t('No template') }}</option>
          <option v-for="txt in plantillas" :key="txt.id" :value="txt.id">{{ tx(txt.nombre) }}</option>
        </Seleccion>
      </label>
      <label class="campo"><span>{{ t('Packaging type') }}</span>
        <Seleccion v-model="modal.tipo_empaque_id">
          <option value="">{{ t('From the template or the default') }}</option>
          <option v-for="x in tiposEmpaque.filter((y) => y.contiene_productos)" :key="x.id" :value="x.id">{{ tx(x.nombre) }}</option>
        </Seleccion>
      </label>
    </div>
    <div class="tabla-marco" style="box-shadow: none">
      <table class="tabla" v-tarjetas>
        <thead><tr><th>{{ t('Row') }}</th><th class="num">{{ t('Not packed') }}</th><th class="num"><span class="req">{{ t('Per carton') }}</span></th><th class="num">{{ t('Total') }}</th></tr></thead>
        <tbody>
          <tr v-for="i in modal.items" :key="i.pl_linea_id">
            <td>{{ tx(i.ref) }}<span v-if="i.inner" class="sub">{{ t('inner packs of {0}{1}', [i.inner, i.cantidad_por_caja ? innerTxt(i.cantidad_por_caja, i.inner) : '']) }}</span></td>
            <td class="num">{{ cantTxt(i.sin_caja, i.unidad) }}</td>
            <td class="num"><input v-model.number="i.cantidad_por_caja" class="celda num" type="number" :min="i.inner || 1" :step="i.inner || 1" style="width: 90px; border-color: var(--linea)" :aria-label="t('Per carton {0}', [i.ref])" /></td>
            <td class="num"><span :class="{ 'etiqueta error': i.cantidad_por_caja * modal.num_cajas > i.sin_caja }">{{ fmtNum((i.cantidad_por_caja || 0) * modal.num_cajas) }}</span></td>
          </tr>
        </tbody>
      </table>
    </div>
    <p class="ayuda">{{ t('Leave blank what you want to take from the template{0}. With an inner pack the quantity per carton must be a multiple of it; a casepack is exact.', [plantillaModal ? t(' ({0}×{1}×{2} cm, tare {3} kg)', [plantillaModal.largo, plantillaModal.ancho, plantillaModal.alto, plantillaModal.tara ?? 0]) : '']) }}
      {{ t('The weight is calculated: unit weight of each item × quantity, plus the tare of each packaging level.') }}</p>
    <div class="rejilla-campos">
      <label class="campo"><span>{{ t('Length cm') }}</span><input v-model="modal.valores.largo" type="number" min="0" step="any" /></label>
      <label class="campo"><span>{{ t('Width cm') }}</span><input v-model="modal.valores.ancho" type="number" min="0" step="any" /></label>
      <label class="campo"><span>{{ t('Height cm') }}</span><input v-model="modal.valores.alto" type="number" min="0" step="any" /></label>
      <label class="campo"><span>{{ t('Tare per carton kg') }}</span><input v-model="modal.valores.tara" type="number" min="0" step="any" /></label>
      <label v-if="faltaPeso(modal.items)" class="campo"><span>{{ t('Net weight per carton kg') }}</span><input v-model="modal.valores.peso_neto_caja" type="number" min="0" step="any" />
        <small class="ayuda">{{ t('Some items have no unit weight: enter the net weight.') }}</small></label>
      <label class="campo"><span>{{ t('Remark') }}</span><input v-model="modal.valores.observacion" /></label>
    </div>
    <template #pie>
      <button class="btn" @click="modal = null">{{ t('Cancel') }}</button>
      <button class="btn btn-primario" :disabled="ocupado || cajaInvalida" @click="crearCaja">{{ t('Create') }}</button>
    </template>
  </Modal>

  <Modal v-if="modal?.tipo === 'mover' || modal?.tipo === 'quitar'" :titulo="tx(modal.tipo === 'mover' ? t('Split into another packing list') : t('Remove from the packing list'))" ancho="660px" @cerrar="modal = null">
    <label v-if="modal.tipo === 'mover'" class="campo"><span>{{ t('Destination PL') }}</span>
      <Seleccion v-model="modal.destino">
        <option v-for="o in pl.otros_pl" :key="o.id" :value="o.id">{{ tx(o.numero) }}</option>
        <option value="">{{ t('A new packing list') }}</option>
      </Seleccion>
    </label>
    <p v-else class="ayuda">{{ t('The quantity goes back to the invoice as pending assignment to a packing list.') }}</p>
    <div class="tabla-marco" style="max-height: 300px; overflow-y: auto; box-shadow: none">
      <table class="tabla" v-tarjetas>
        <thead><tr><th>{{ t('Row') }}</th><th class="num">{{ t('Not packed') }}</th><th class="num">{{ tx(modal.tipo === 'mover' ? t('Move') : t('Remove')) }}</th></tr></thead>
        <tbody>
          <tr v-for="fm in modal.filas" :key="fm.pl_linea_id">
            <td>{{ tx(fm.ref) }}</td>
            <td class="num">{{ cantTxt(fm.sin_caja, fm.unidad) }}</td>
            <td class="num"><input v-model.number="fm.cantidad" class="celda num" type="number" min="0" :step="fm.inner || 1" :max="fm.sin_caja" style="width: 90px; border-color: var(--linea)" :aria-label="t('Quantity {0}', [fm.ref])" /></td>
          </tr>
        </tbody>
      </table>
    </div>
    <p class="ayuda">{{ t('Put 0 on the rows you do not want to touch. Only unpacked quantities move (in whole inner packs); to take whole cartons use “Move to another PL” on the Cartons tab.') }}</p>
    <template #pie>
      <button class="btn" @click="modal = null">{{ t('Cancel') }}</button>
      <button class="btn btn-primario" :disabled="ocupado || movInvalido" @click="modal.tipo === 'mover' ? mover() : quitar()">
        {{ tx(modal.tipo === 'mover' ? t('Move') : t('Remove from PL')) }}
      </button>
    </template>
  </Modal>

  <Modal v-if="modal?.tipo === 'editar_cajas'" :titulo="t('Dimensions and weights of {0}', [plural(modal.cajas, t('carton'), t('cartons'))])" ancho="640px" @cerrar="modal = null">
    <label class="campo"><span>{{ t('Copy from a template (optional)') }}</span>
      <Seleccion v-model="modal.plantilla_id">
        <option value="">{{ t('Do not copy') }}</option>
        <option v-for="txt in plantillas" :key="txt.id" :value="txt.id">{{ t('{0} · {1}×{2}×{3} cm, tare {4} kg', [txt.nombre, txt.largo, txt.ancho, txt.alto, txt.tara ?? 0]) }}</option>
      </Seleccion>
    </label>
    <label class="campo"><span>{{ t('Packaging type') }}</span>
      <Seleccion v-model="modal.tipo_empaque_id">
        <option value="">{{ t('Do not change') }}</option>
        <option v-for="x in tiposEmpaque" :key="x.id" :value="x.id">{{ tx(x.nombre) }}</option>
      </Seleccion>
    </label>
    <p class="ayuda">{{ t('Leave blank what you do not want to change. What you type here overrides the template. The weight is calculated from the items and the tare of each level.') }}</p>
    <div class="rejilla-campos">
      <label class="campo"><span>{{ t('Length cm') }}</span><input v-model="modal.valores.largo" type="number" min="0" step="any" /></label>
      <label class="campo"><span>{{ t('Width cm') }}</span><input v-model="modal.valores.ancho" type="number" min="0" step="any" /></label>
      <label class="campo"><span>{{ t('Height cm') }}</span><input v-model="modal.valores.alto" type="number" min="0" step="any" /></label>
      <label class="campo"><span>{{ t('Tare per carton kg') }}</span><input v-model="modal.valores.tara" type="number" min="0" step="any" /></label>
      <label v-if="modal.manual" class="campo"><span>{{ t('Net weight per carton kg') }}</span><input v-model="modal.valores.peso_neto_caja" type="number" min="0" step="any" />
        <small class="ayuda">{{ t('Only for cartons with items without unit weight.') }}</small></label>
      <label class="campo"><span>{{ t('Cartons per group') }}</span><input v-model="modal.valores.num_cajas" type="number" min="1" /></label>
      <label class="campo" style="grid-column: 1 / -1"><span>{{ t('Remark') }}</span><input v-model="modal.valores.observacion" /></label>
    </div>
    <template #pie>
      <button class="btn" @click="modal = null">{{ t('Cancel') }}</button>
      <button class="btn btn-primario" :disabled="ocupado" @click="editarCajas">{{ t('Apply') }}</button>
    </template>
  </Modal>

  <Modal v-if="modal?.tipo === 'mover_cajas'" :titulo="t('Move cartons to another packing list')" ancho="600px" @cerrar="modal = null">
    <label class="campo"><span>{{ t('Destination PL') }}</span>
      <Seleccion v-model="modal.destino">
        <option v-for="o in pl.otros_pl" :key="o.id" :value="o.id">{{ tx(o.numero) }}</option>
        <option value="">{{ t('A new packing list') }}</option>
      </Seleccion>
    </label>
    <div class="tabla-marco" style="box-shadow: none">
      <table class="tabla" v-tarjetas>
        <thead><tr><th>{{ t('Cartons') }}</th><th class="num">{{ t('Available') }}</th><th class="num">{{ t('Move') }}</th></tr></thead>
        <tbody>
          <tr v-for="gm in modal.grupos" :key="gm.grupo_id">
            <td class="cajas-rango">{{ tx(gm.rango) }}</td>
            <td class="num">{{ tx(gm.max) }}</td>
            <td class="num"><input v-model.number="gm.num_cajas" class="celda num" type="number" min="1" :max="gm.max" style="width: 80px; border-color: var(--linea)" :aria-label="t('Cartons to move from {0}', [gm.rango])" /></td>
          </tr>
        </tbody>
      </table>
    </div>
    <p class="ayuda">{{ t('The contents travel with their cartons. Numbering is recalculated in both packing lists.') }}</p>
    <template #pie>
      <button class="btn" @click="modal = null">{{ t('Cancel') }}</button>
      <button class="btn btn-primario" :disabled="ocupado || modal.grupos.some((g) => !(g.num_cajas >= 1) || g.num_cajas > g.max)" @click="moverCajas">{{ t('Move cartons') }}</button>
    </template>
  </Modal>

  <Modal v-if="modal?.tipo === 'guardar_plantilla'" :titulo="t('Save as template')" @cerrar="modal = null">
    <label class="campo"><span class="req">{{ t('Template name') }}</span><input v-model="modal.nombre" :placeholder="t('For example: 12-pair carton large sizes')" /></label>
    <p class="ayuda">{{ t('Saves the quantity per carton, packaging type, dimensions and tare to use in auto-pack.') }}</p>
    <template #pie>
      <button class="btn" @click="modal = null">{{ t('Cancel') }}</button>
      <button class="btn btn-primario" :disabled="ocupado || !modal.nombre.trim()" @click="guardarPlantilla">{{ t('Save template') }}</button>
    </template>
  </Modal>

  <Modal v-if="modal?.tipo === 'pallet'" :titulo="t('Put in a pallet or container')" ancho="600px" @cerrar="modal = null">
    <p>{{ t('{0} selected. Group them inside another packaging (pallet or any type that can contain them); each group is split evenly among its units.', [plural(cajasSel, t('carton'), t('cartons'))]) }}</p>
    <label class="campo"><span>{{ t('Container') }}</span>
      <Seleccion v-model="modal.destino">
        <option value="">{{ t('New container') }}</option>
        <option v-for="p in pl.pallets" :key="p.id" :value="p.id">{{ t('Add to {0} {1} ({2} inside)', [p.tipo, p.etiqueta, p.cajas]) }}</option>
      </Seleccion>
    </label>
    <div v-if="!modal.destino" class="rejilla-campos">
      <label class="campo"><span class="req">{{ t('Packaging type') }}</span>
        <Seleccion :model-value="modal.tipo_empaque_id" @update:model-value="tipoContenedor">
          <option v-for="x in contenedoresPosibles" :key="x.id" :value="x.id">{{ tx(x.nombre) }}</option>
        </Seleccion>
        <small v-if="!contenedoresPosibles.length" class="ayuda">{{ t('No packaging type can contain the selection. Set “Can contain” in Master data › Packaging types.') }}</small>
      </label>
      <label class="campo"><span class="req">{{ t('Units') }}</span><input v-model.number="modal.num" type="number" min="1" /></label>
      <label class="campo"><span class="req">{{ t('Length cm') }}</span><input v-model.number="modal.largo" type="number" min="1" /></label>
      <label class="campo"><span class="req">{{ t('Width cm') }}</span><input v-model.number="modal.ancho" type="number" min="1" /></label>
      <label class="campo"><span class="req">{{ t('Height cm (loaded)') }}</span><input v-model.number="modal.alto" type="number" min="1" /></label>
      <label class="campo"><span>{{ t('Tare kg') }}</span><input v-model.number="modal.peso_tara" type="number" min="0" /></label>
    </div>
    <template #pie>
      <button class="btn" @click="modal = null">{{ t('Cancel') }}</button>
      <button class="btn btn-primario" :disabled="ocupado || (!modal.destino && !(modal.largo > 0 && modal.ancho > 0 && modal.alto > 0 && modal.num >= 1))" @click="paletizar">{{ t('Put inside') }}</button>
    </template>
  </Modal>

  <Modal v-if="modal?.tipo === 'desempacar'" :titulo="t('Unpack cartons')" @cerrar="modal = null">
    <p>{{ t('Cartons to remove: {0}. Their contents go back to “To pack”.', [fmtNum(cajasSel)]) }}</p>
    <template #pie>
      <button class="btn" @click="modal = null">{{ t('Cancel') }}</button>
      <button class="btn btn-peligro" :disabled="ocupado" @click="desempacar">{{ t('Unpack') }}</button>
    </template>
  </Modal>

  <Modal v-if="modal?.tipo === 'pendientes'" :titulo="t('Pending to finalize')" ancho="620px" @cerrar="modal = null">
    <ul class="lista-mensajes"><li v-for="(d, i) in modal.detalle" :key="i">{{ tx(textoDetalle(d)) }}</li></ul>
    <template #pie><button class="btn btn-primario" @click="modal = null; tab = 'revision'">{{ t('See in review') }}</button></template>
  </Modal>

  <Modal v-if="modal?.tipo === 'estado'" :titulo="tx(modal.accion === 'reabrir' ? t('Reopen packing list') : t('Cancel packing list'))" @cerrar="modal = null">
    <p v-if="modal.accion === 'reabrir'">{{ t('It becomes editable again. If it was confirmed in a load unit, the assignment becomes tentative.') }}</p>
    <p v-else>{{ t('Its quantities go back to the invoice as pending assignment.') }}</p>
    <label class="campo"><span :class="{ req: !(modal.accion === 'cancelar' && pl?.estado === 'BORRADOR') }">{{ t('Reason{0}', [modal.accion === 'cancelar' && pl?.estado === 'BORRADOR' ? t(' (optional)') : '']) }}</span><textarea v-model="modal.motivo"></textarea></label>
    <template #pie>
      <button class="btn" @click="modal = null">{{ t('Back') }}</button>
      <button class="btn" :class="modal.accion === 'cancelar' ? 'btn-peligro' : 'btn-primario'" :disabled="ocupado" @click="cambiarEstado">
        {{ tx(modal.accion === 'reabrir' ? t('Reopen') : t('Cancel packing list')) }}
      </button>
    </template>
  </Modal>
  <ExplosionPrepack v-if="explosion" :sku="explosion.sku" :cajas="explosion.cajas" @cerrar="explosion = null" />
</template>

<style scoped>
.numero-editable { font: inherit; font-stretch: 125%; font-weight: 780; font-size: 1.6rem; max-width: 100%; width: 16ch; }
</style>
