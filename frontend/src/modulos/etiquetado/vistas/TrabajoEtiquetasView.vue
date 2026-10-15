<script setup>
import { t, tx } from '@/i18n/index.js'
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '@/nucleo/api'
import Asistente from '@/componentes/Asistente.vue'
import EstadoBadge from '@/componentes/EstadoBadge.vue'
import Icono from '@/componentes/Icono.vue'
import Modal from '@/componentes/Modal.vue'
import PanelLateral from '@/componentes/PanelLateral.vue'
import Seleccion from '@/componentes/Seleccion.vue'
import SelectBusqueda from '@/componentes/SelectBusqueda.vue'
import { fmtNum } from '@/nucleo/utils'
import { puede } from '@/stores/sesion'
import { avisar, errorApi } from '@/stores/ui'
import SelectorDiseno from '@/modulos/etiquetado/componentes/SelectorDiseno.vue'
import { CANTIDADES, CATEGORIAS, ORIGENES, SUJETOS, catalogos, textoDonde } from '@/modulos/etiquetado/etiquetas.js'
import { buscarArticulos, buscarOrdenes } from '@/modulos/etiquetado/componentes/buscadores.js'

// Asistente único de etiquetado en tres pasos: qué imprimir, revisar
// (los problemas se arreglan aquí mismo) y generar. Todas las entradas (OC,
// lista de empaque, producto, artículos, una familia) crean un trabajo en el
// servidor; el borrador se guarda y se retoma en el mismo paso. Desde la OC,
// la lista de empaque o el producto se entra directo a «Revisar».
const route = useRoute()
const router = useRouter()
const trabajo = ref(null)
const ocupado = ref(false)
const guardado = ref('')
const paso = ref(0)
const origen = ref('OC') // OC · PACKING · ARTICULOS · FAMILIA (una familia = OC con familia_id)
const p = reactive({ oc_ids: [], posiciones: [], cantidades: {}, articulos: [], pl_id: '', tipo_empaque_id: '', familia_id: '', tipos: [],
  prueba: false, elegidas: {}, manuales: {}, formato: 'PDF', zip: { carpetas: [], nombre: '', contenido: 'PDF', agrupar: 'plantilla' } })
const cat = ref(null)
const tipos = ref([])

const PASOS = () => [['que', t('What to print')], ['revisar', t('Review')], ['generar', t('Generate')]]
const registros = computed(() => trabajo.value?.registros || [])
const totalEtiquetas = computed(() => registros.value.reduce((s, r) => s + (r.cantidad || 0), 0))
const conteo = computed(() => trabajo.value?.resumen?.conteo || {})
const generales = computed(() => trabajo.value?.resumen?.problemas || [])
const bloqueantes = computed(() => (conteo.value.ERROR || 0) + generales.value.filter((x) => x.nivel === 'error').length)
const pasos = computed(() => PASOS().map(([clave, titulo], i) => ({
  clave, titulo, errores: clave === 'revisar' && trabajo.value?.validado_en ? bloqueantes.value : 0, completo: i < paso.value, bloqueado: !trabajo.value && i > 0,
})))
const origenServidor = computed(() => (origen.value === 'FAMILIA' ? 'OC' : origen.value))

// ---- Carga, alta y borrador ---------------------------------------------------------------------------
function zipConDefecto(z) {
  const r = { carpetas: [], nombre: '', contenido: 'PDF', ...(z || {}) }
  if (!r.agrupar) r.agrupar = r.contenido !== 'PDF' ? 'etiqueta' : r.carpetas.length ? 'carpeta' : 'plantilla'
  return r
}
function aplicar(tr) {
  trabajo.value = tr
  const par = tr.parametros || {}
  origen.value = tr.origen === 'OC' && par.familia_id ? 'FAMILIA' : tr.origen
  Object.assign(p, { oc_ids: par.oc_ids || [], posiciones: par.posiciones || [], cantidades: par.cantidades || {}, articulos: par.articulos || [],
    pl_id: par.pl_id || '', tipo_empaque_id: par.tipo_empaque_id || '', familia_id: par.familia_id || '', tipos: par.tipos || [],
    prueba: !!par.prueba, elegidas: par.elegidas || {}, manuales: par.manuales || {}, formato: par.formato || 'PDF', zip: zipConDefecto(par.zip) })
}
async function cargar(id) {
  try {
    aplicar(await api.get(`/etiquetas/trabajos/${id}`))
    paso.value = trabajo.value.generado_en ? 2 : Math.min(trabajo.value.paso || 0, 2)
    if (trabajo.value.estado === 'EN_PROCESO') {
      paso.value = 2
      seguir()
    }
  } catch (e) {
    errorApi(e)
  }
}
function parametros() {
  if (['GENERADO', 'PARCIAL'].includes(trabajo.value?.estado)) return { zip: p.zip, formato: p.formato }
  const base = { tipos: p.tipos, prueba: p.prueba, manuales: p.manuales, elegidas: p.elegidas, cantidades: p.cantidades, formato: p.formato, zip: p.zip,
    familia_id: p.familia_id || null }
  if (origenServidor.value === 'OC') Object.assign(base, { oc_ids: p.oc_ids, posiciones: p.posiciones.length ? p.posiciones : null })
  if (origen.value === 'ARTICULOS') base.articulos = p.articulos
  if (origen.value === 'PACKING') Object.assign(base, { pl_id: p.pl_id || null, tipo_empaque_id: p.tipo_empaque_id || null })
  return base
}
async function guardar(silencioso = false) {
  if (!trabajo.value) return crear()
  if (['EN_PROCESO', 'CANCELADO'].includes(trabajo.value.estado)) return true
  try {
    guardado.value = t('Saving…')
    aplicar(await api.patch(`/etiquetas/trabajos/${trabajo.value.id}`, { paso: paso.value, parametros: parametros(), version: trabajo.value.version }))
    guardado.value = t('Saved at {0}', [new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })])
    if (!silencioso) avisar(t('Draft saved: you can continue later from Labels.'))
    return true
  } catch (e) {
    guardado.value = ''
    if (e.status === 409) {
      avisar(t('Someone else changed this labeling job: it was reloaded.'), 'aviso')
      await cargar(trabajo.value.id)
    } else errorApi(e)
    return false
  }
}
async function crear(pasoInicial = 1) {
  try {
    const tr = await api.post('/etiquetas/trabajos', { origen: origenServidor.value, paso: pasoInicial, parametros: parametros() })
    router.replace(`/etiquetas/trabajos/${tr.id}`)
    aplicar(tr)
    return true
  } catch (e) {
    errorApi(e)
    return false
  }
}
async function validar() {
  try {
    aplicar(await api.post(`/etiquetas/trabajos/${trabajo.value.id}/validar`))
    previa.value = null
    return true
  } catch (e) {
    errorApi(e)
    return false
  }
}
// Guardar el cambio y volver a revisar (el usuario no pulsa «validar»)
async function revalidar() {
  ocupado.value = true
  try {
    if (await guardar(true)) await validar()
  } finally {
    ocupado.value = false
  }
}

const ids = (v) => String(v || '').split(',').map(Number).filter(Boolean)
onMounted(async () => {
  try {
    cat.value = await catalogos()
    tipos.value = await api.get('/etiquetas/tipos')
  } catch (e) {
    errorApi(e)
  }
  if (route.params.id) return cargar(route.params.id)
  // Entradas: ?origen=OC&oc=1 | &ocs=1,2 · ?origen=ARTICULOS&articulos=1,2 · ?origen=PACKING&pl=3 · ?origen=FAMILIA&familia=2
  // (&tipos=1,2 &prueba=1). Con el origen completo se crea el trabajo y se va directo a «Revisar».
  const q = route.query
  origen.value = ['OC', 'ARTICULOS', 'PACKING', 'FAMILIA'].includes(q.origen) ? q.origen : 'OC'
  p.oc_ids = ids(q.ocs || q.oc)
  p.articulos = ids(q.articulos).map((id) => ({ articulo_id: id, cantidad: 1 }))
  p.pl_id = q.pl ? Number(q.pl) : ''
  p.prueba = q.prueba === '1'
  if (q.familia) await elegirFamilia(Number(q.familia))
  p.tipos = ids(q.tipos).length ? ids(q.tipos) : porDefecto()
  cargarNombres()
  if (listoParaCrear.value && q.paso !== 'que') {
    ocupado.value = true
    if (await crear(1)) {
      await validar()
      paso.value = 1
    }
    ocupado.value = false
  }
})

// ---- Navegación -------------------------------------------------------------------------------------------
async function ir(i) {
  if (ocupado.value || i === paso.value) return
  if (i === 2 && paso.value < 2 && bloqueantes.value && !trabajo.value?.permite_parcial && !p.prueba) {
    avisar(t('There are {0} problems to fix before generating.', [bloqueantes.value]), 'aviso')
    return
  }
  ocupado.value = true
  try {
    if (!trabajo.value) {
      if (!listoParaCrear.value) {
        avisar(t('Choose what to print first.'), 'aviso')
        return
      }
      if (!(await crear(1))) return
      await validar()
    } else if (paso.value === 0 && i > 0) {
      if (!(await guardar(true))) return
      await validar()
    } else if (!(await guardar(true))) return
    paso.value = i
  } finally {
    ocupado.value = false
  }
}
const cerrar = () => router.push('/etiquetas')

// ---- 1. Qué imprimir ------------------------------------------------------------------------------------------
const listoParaCrear = computed(() => p.tipos.length > 0 && ((origenServidor.value === 'OC' && p.oc_ids.length) || (origen.value === 'ARTICULOS' && p.articulos.length)
  || (origen.value === 'PACKING' && p.pl_id)))
const sujetosOrigen = computed(() => cat.value?.origenes?.[origenServidor.value] || [])
const tiposOrigen = computed(() => tipos.value.filter((x) => sujetosOrigen.value.includes(x.sujeto)))
function porDefecto() {
  const lista = tipos.value.filter((x) => (cat.value?.origenes?.[origenServidor.value] || []).includes(x.sujeto))
  const obligatorios = lista.filter((x) => x.obligatoria)
  return (obligatorios.length ? obligatorios : lista).map((x) => x.id)
}
watch(origen, (o, antes) => {
  if (trabajo.value || !antes) return
  p.tipos = porDefecto()
})
const nombres = reactive({ oc: {}, articulo: {}, pl: {} })
async function cargarNombres() {
  for (const id of p.oc_ids) {
    if (!nombres.oc[id]) api.get(`/ordenes/${id}`).then((r) => (nombres.oc[id] = r.oc.numero)).catch(() => {})
  }
  const faltan = p.articulos.map((a) => a.articulo_id).filter((id) => !nombres.articulo[id])
  if (faltan.length) {
    api.get('/etiquetas/articulos', { ids: faltan.slice(0, 200).join(','), size: 200 })
      .then((r) => r.items.forEach((a) => (nombres.articulo[a.id] = `${a.sku}${a.talla ? ` · ${a.talla}` : ''}`))).catch(() => {})
  }
}
const nuevaOc = ref('')
watch(nuevaOc, (id) => {
  if (id && !p.oc_ids.includes(Number(id))) {
    p.oc_ids.push(Number(id))
    cargarNombres()
  }
  nuevaOc.value = ''
})
const nuevoArticulo = ref('')
watch(nuevoArticulo, (id) => {
  if (id && !p.articulos.some((a) => a.articulo_id === Number(id))) {
    p.articulos.push({ articulo_id: Number(id), cantidad: 1 })
    cargarNombres()
  }
  nuevoArticulo.value = ''
})
// Listas de empaque y sus niveles («qué cajas»)
const listasEmpaque = ref([])
onMounted(() => api.get('/etiquetas/packing').then((r) => (listasEmpaque.value = r)).catch(() => {}))
const buscarPl = async (q) => (await api.get('/etiquetas/packing', { q })).map((x) => ({ valor: x.id, texto: x.numero, sub: [x.factura, x.proveedor].filter(Boolean).join(' · ') }))
const niveles = ref(null)
async function cargarNiveles() {
  try {
    niveles.value = p.pl_id ? await api.get(`/etiquetas/packing/${p.pl_id}`) : null
    if (niveles.value && !niveles.value.etiquetas_reales) p.prueba = true
  } catch (e) {
    errorApi(e)
  }
}
watch(() => p.pl_id, () => cargarNiveles())
const conCajas = computed(() => tiposOrigen.value.some((x) => x.sujeto === 'BULTO' && p.tipos.includes(x.id)))
// Una familia: sus OC abiertas (las que tienen artículos de ella), etiquetando solo esos artículos
const familias = ref([])
onMounted(() => api.get('/etiquetas/familias', { activas: true }).then((r) => (familias.value = r)).catch(() => {}))
async function elegirFamilia(id) {
  p.familia_id = id || ''
  p.oc_ids = id ? (await api.get('/etiquetas/ordenes', { familia_id: id, solo_ids: true }).catch(() => ({ ids: [] }))).ids.slice(0, 200) : []
}
// Líneas de la OC (solo con pocas OC): por defecto todas las abiertas
const lineas = reactive({})
const verLineas = ref(false)
watch(verLineas, (v) => v && p.oc_ids.slice(0, 5).forEach((id) => {
  if (!lineas[id]) api.get(`/ordenes/${id}`).then((r) => (lineas[id] = r.posiciones)).catch(() => {})
}))
const elegida = (id) => !p.posiciones.length || p.posiciones.includes(id)
function alternarLinea(id) {
  let lista = p.posiciones.length ? [...p.posiciones] : Object.values(lineas).flat().map((x) => x.id)
  lista = lista.includes(id) ? lista.filter((x) => x !== id) : [...lista, id]
  p.posiciones = lista
}
// Cuántas etiquetas de cada tipo, antes de crear el trabajo (una OC o una lista de empaque)
const resumen = ref(null)
watch(() => [origen.value, p.oc_ids.join(), p.pl_id], async () => {
  resumen.value = null
  const o = origen.value === 'PACKING' && p.pl_id ? ['PACKING', p.pl_id] : origen.value === 'OC' && p.oc_ids.length === 1 ? ['OC', p.oc_ids[0]] : null
  if (o && !trabajo.value) resumen.value = await api.get('/etiquetas/resumen', { origen: o[0], id: o[1] }).catch(() => null)
}, { immediate: true })
const deResumen = (id) => resumen.value?.tipos?.find((x) => x.tipo.id === id)
const noAplica = (id) => resumen.value?.problemas?.find((x) => x.codigo === 'tipo_no_aplica' && x.tipo_etiqueta_id === id)
function alternarTipo(id) {
  p.tipos = p.tipos.includes(id) ? p.tipos.filter((x) => x !== id) : [...p.tipos, id]
}

// ---- 2. Revisar ---------------------------------------------------------------------------------------------------
const tiposTrabajo = computed(() => (trabajo.value?.resumen?.tipos || []))
const tipoVista = ref(null)
watch(tiposTrabajo, (l) => {
  if (!l.some((x) => x.tipo_etiqueta_id === tipoVista.value)) tipoVista.value = l[0]?.tipo_etiqueta_id ?? null
}, { immediate: true })
const LIMITE = 200
const mostrar = ref(LIMITE)
watch(tipoVista, () => (mostrar.value = LIMITE))
const delTipo = computed(() => registros.value.filter((r) => r.tipo_etiqueta_id === tipoVista.value))
const tipoActual = computed(() => tipos.value.find((x) => x.id === tipoVista.value))
const disenosTrabajo = computed(() => trabajo.value?.resumen?.disenos || [])
const variables = computed(() => trabajo.value?.resumen?.variables || [])
const avisos = computed(() => trabajo.value?.resumen?.avisos || [])
// Problemas agrupados: «N artículos sin diseño de X» y el resto por categoría
const sinDiseno = computed(() => {
  const res = {}
  for (const r of registros.value) {
    if (!r.plantilla_id && (r.problemas || []).some((x) => x.codigo === 'sin_plantilla' && x.nivel === 'error')) (res[r.tipo_etiqueta_id] ||= []).push(r)
  }
  return Object.entries(res).map(([id, lista]) => ({ tipo: tipos.value.find((x) => x.id === Number(id)) || { id: Number(id), nombre: lista[0].tipo }, registros: lista }))
})
const NIVEL_ICONO = { error: 'alerta', advertencia: 'info', info: 'info' }
const otrosProblemas = computed(() => {
  const res = {}
  for (const r of registros.value) {
    for (const x of r.problemas || []) {
      if (x.codigo === 'sin_plantilla' || x.nivel === 'info') continue
      // Un renglón por clase de problema (los mensajes de una misma clase solo cambian en cifras)
      // (y por dato que falta: cada uno se completa aparte)
      const clave = `${x.categoria || 'diseno'}|${x.nivel}|${x.codigo || x.mensaje}|${x.campo || ''}`
      const g = (res[clave] ||= { categoria: x.categoria || 'diseno', nivel: x.nivel, mensaje: x.mensaje, campo: x.campo, referencias: [], articulos: {} })
      g.referencias.push(r.referencia)
      if (r.articulo_id) g.articulos[r.articulo_id] ||= r.referencia
    }
  }
  return Object.values(res).sort((a, b) => (a.nivel === 'error' ? -1 : 0) - (b.nivel === 'error' ? -1 : 0))
})
function cambiarCantidad(r, v) {
  p.cantidades = { ...p.cantidades, [r.clave]: Math.max(Number(v) || 0, 0) }
  revalidar()
}

// Completar el dato que falta en el maestro de artículos (UPC, SKU del proveedor, peso…) sin salir del asistente
const completable = (x) => !!x.campo && (cat.value?.completables || []).includes(x.campo) && puede('catalogos.editar')
const completando = ref(null)
function abrirCompletar(x) {
  const articulos = Object.entries(x.articulos).slice(0, 200).map(([id, referencia]) => ({ id, referencia }))
  completando.value = { campo: x.campo, nombre: x.mensaje, articulos, valores: Object.fromEntries(articulos.map((a) => [a.id, ''])) }
}
async function completar() {
  const c = completando.value
  ocupado.value = true
  try {
    const valores = Object.fromEntries(Object.entries(c.valores).filter(([, v]) => String(v ?? '').trim() !== ''))
    aplicar(await api.post(`/etiquetas/trabajos/${trabajo.value.id}/completar`, { campo: c.campo, valores }))
    avisar(t('Saved in the item master data; the job was checked again.'))
    completando.value = null
  } catch (e) {
    errorApi(e)
  } finally {
    ocupado.value = false
  }
}

// Elegir diseño: para este trabajo o guardado como regla en su lugar (familia o toda la empresa)
const eleccion = ref(null)
async function abrirEleccion(g) {
  const arts = [...new Set(g.registros.map((r) => r.articulo_id).filter(Boolean))]
  let lugares = [{ clave: 'GENERAL:0', nivel: 'GENERAL', destino_id: null, nombre: t('Whole company') }]
  let lugar = 'GENERAL:0'
  if (g.tipo.sujeto === 'ARTICULO' && arts.length) {
    const r = await api.get('/etiquetas/articulos', { ids: arts.slice(0, 200).join(','), size: 200 }).catch(() => ({ items: [] }))
    const fams = [...new Map(r.items.filter((a) => a.familia_id).map((a) => [a.familia_id, a.familia])).entries()]
    lugares = [...fams.map(([id, nombre]) => ({ clave: `FAMILIA:${id}`, nivel: 'FAMILIA', destino_id: id, nombre: textoDonde('FAMILIA', nombre) })), ...lugares]
    if (fams.length === 1) lugar = `FAMILIA:${fams[0][0]}`
  }
  eleccion.value = { grupo: g, plantilla_id: '', regla: puede('etiquetas.configurar'), lugares, lugar }
}
async function aplicarEleccion() {
  const e = eleccion.value
  ocupado.value = true
  try {
    if (e.regla) {
      const l = e.lugares.find((x) => x.clave === e.lugar)
      await api.post('/etiquetas/usos', { tipo_etiqueta_id: e.grupo.tipo.id, plantilla_id: Number(e.plantilla_id), nivel: l.nivel, destino_id: l.destino_id,
        contexto_tipo: 'NINGUNO', reemplazar: true })
      avisar(t('Saved as the design of {0}; the next jobs use it too.', [l.nombre]))
    } else {
      p.elegidas = { ...p.elegidas, ...Object.fromEntries(e.grupo.registros.map((r) => [r.clave, Number(e.plantilla_id)])) }
    }
    eleccion.value = null
    if (await guardar(true)) await validar()
  } catch (err) {
    errorApi(err)
  } finally {
    ocupado.value = false
  }
}

// Vista previa: el registro dibujado por el servidor, con anterior/siguiente
const previa = ref(null)
const registroPrevia = ref(null)
async function verPrevia(r) {
  registroPrevia.value = r
  try {
    previa.value = await api.get(`/etiquetas/trabajos/${trabajo.value.id}/registros/${r.id}/vista-previa`)
  } catch (e) {
    previa.value = null
    registroPrevia.value = null
    errorApi(e)
  }
}
const conDiseno = computed(() => registros.value.filter((r) => r.plantilla_id))
function moverPrevia(delta) {
  const i = conDiseno.value.findIndex((r) => r.id === registroPrevia.value?.id)
  const r = conDiseno.value[i + delta]
  if (r) verPrevia(r)
}

// ---- 3. Generar ---------------------------------------------------------------------------------------------------
const opciones = reactive({ aceptar: false, parcial: false })
const advertencias = computed(() => registros.value.filter((r) => r.estado === 'ADVERTENCIA').length)
const pendientes = computed(() => registros.value.filter((r) => ['LISTO', 'ADVERTENCIA'].includes(r.estado)))
const etiquetasPendientes = computed(() => pendientes.value.reduce((s, r) => s + r.cantidad, 0))
const CARPETAS = () => [['oc', t('PO')], ['plantilla', t('Design')], ['familia', t('Labeling family')], ['packing_list', t('Packing list')]]
const MARCADORES = ['oc', 'referencia', 'sku', 'n', 'total', 'i', 'plantilla', 'serie', 'bulto']
const marcadoresTxt = MARCADORES.map((m) => `{${m}}`).join(' ')
// Cómo se reparten las etiquetas en archivos del ZIP (PNG y SVG, siempre una por archivo)
const AGRUPACIONES = () => [['etiqueta', t('One file per label')], ['plantilla', t('One PDF per design and version')],
  ['carpeta', t('One PDF per folder (one per design if a folder has several)')], ['unico', t('A single PDF (all labels the same size)')]]
const conCarpetas = computed(() => ['etiqueta', 'carpeta'].includes(p.zip.agrupar))
function cambiarContenido(v) {
  p.zip = { ...p.zip, contenido: v, agrupar: v === 'PDF' ? (p.zip.carpetas.length ? 'carpeta' : 'plantilla') : 'etiqueta' }
}
function cambiarAgrupar(v) {
  p.zip = { ...p.zip, agrupar: v, carpetas: ['etiqueta', 'carpeta'].includes(v) ? p.zip.carpetas : [] }
}
function alternarCarpeta(c) {
  const lista = p.zip.carpetas.includes(c) ? p.zip.carpetas.filter((x) => x !== c) : [...p.zip.carpetas, c].slice(0, 3)
  p.zip = { ...p.zip, carpetas: lista }
}
let temporizador = null
async function generar() {
  if (!(await guardar(true))) return
  ocupado.value = true
  try {
    const r = await api.post(`/etiquetas/trabajos/${trabajo.value.id}/generar`, { aceptar_advertencias: opciones.aceptar, parcial: opciones.parcial,
      formato: p.formato, version: trabajo.value.version })
    aplicar(r)
    if (r.estado === 'EN_PROCESO') {
      avisar(t('The labels are being generated in the background: you can leave this page.'))
      seguir()
    } else avisar(r.estado === 'PARCIAL' ? t('Generated the ready records; the ones with errors are pending.') : t('Labels generated.'))
  } catch (e) {
    errorApi(e)
  } finally {
    ocupado.value = false
  }
}
function seguir() {
  clearTimeout(temporizador)
  temporizador = setTimeout(async () => {
    try {
      const e = await api.get(`/etiquetas/trabajos/${trabajo.value.id}/estado`)
      trabajo.value = { ...trabajo.value, ...e }
      if (e.estado === 'EN_PROCESO') return seguir()
      await cargar(trabajo.value.id)
      if (e.error) avisar(tx(e.error), 'error')
    } catch {
      seguir()
    }
  }, 1200)
}
onBeforeUnmount(() => clearTimeout(temporizador))
async function descargarTodo(contenido) {
  try {
    await api.descargar(`/etiquetas/trabajos/${trabajo.value.id}/archivo`, 'labels.zip', { contenido })
    await cargar(trabajo.value.id)
  } catch (e) {
    errorApi(e)
  }
}
async function descargarEjecucion(e) {
  try {
    await api.descargar(`/etiquetas/generaciones/${e.id}/archivo`, `labels-${e.id}`)
    await cargar(trabajo.value.id)
  } catch (err) {
    errorApi(err)
  }
}
const impresion = ref(null)
async function confirmarImpresion() {
  const x = impresion.value
  try {
    await api.post(`/etiquetas/generaciones/${x.id}/impresion`, { confirmo: x.confirmo, cantidad: Number(x.cantidad), impresora: x.impresora,
      observacion: x.observacion })
    impresion.value = null
    avisar(t('Printing confirmed.'))
    cargar(trabajo.value.id)
  } catch (e) {
    errorApi(e)
  }
}
// Otro trabajo con lo mismo (otra tanda de las mismas etiquetas)
async function otroIgual() {
  try {
    const par = { ...trabajo.value.parametros }
    const tr = await api.post('/etiquetas/trabajos', { origen: trabajo.value.origen, paso: 1, parametros: par })
    await router.push(`/etiquetas/trabajos/${tr.id}`)
    aplicar(tr)
    await validar()
    paso.value = 1
  } catch (e) {
    errorApi(e)
  }
}
</script>

<template>
  <Asistente :documento="trabajo ? trabajo.nombre : t('New labeling job')" :pasos="pasos" :actual="paso" :ocupado="ocupado" :guardado="guardado"
             :texto-final="t('Back to Labels')" @ir="ir" @anterior="ir(paso - 1)" @siguiente="ir(paso + 1)" @guardar="guardar()"
             @finalizar="cerrar" @cerrar="cerrar">
    <div v-if="trabajo" class="tj-estado">
      <EstadoBadge :estado="trabajo.estado" tipo="trabajo" />
      <span v-if="p.prueba" class="etiqueta aviso ms-0">{{ t('Test mode') }}</span>
      <span v-if="trabajo.validado_en">{{ t('{0} labels · {1} designs', [fmtNum(totalEtiquetas), disenosTrabajo.length]) }}</span>
      <span v-if="bloqueantes" class="etiqueta error ms-0">{{ t('{0} problems to fix', [bloqueantes]) }}</span>
      <span v-if="conteo.ADVERTENCIA" class="etiqueta aviso ms-0">{{ t('{0} with warnings', [conteo.ADVERTENCIA]) }}</span>
      <span v-if="conteo.GENERADO" class="etiqueta info ms-0">{{ t('{0} generated', [conteo.GENERADO]) }}</span>
      <button v-if="paso === 1 && conDiseno.length" type="button" class="btn btn-chico separar" @click="verPrevia(conDiseno[0])"><Icono nombre="ojo" :tam="14" />{{ t('Preview') }}</button>
    </div>

    <!-- 1. Qué imprimir -->
    <section v-if="paso === 0" class="panel tj-bloque">
      <div class="tj-origenes" role="radiogroup" :aria-label="t('Print labels of')">
        <button v-for="[clave, titulo, ayuda] in ORIGENES()" :key="clave" type="button" class="tj-origen" role="radio"
                :aria-checked="origen === clave" :disabled="!!trabajo" @click="origen = clave">
          <strong>{{ titulo }}</strong><span>{{ ayuda }}</span></button>
      </div>
      <div v-if="origen === 'OC'" class="tj-bloque">
        <label class="campo"><span>{{ t('Add a purchase order') }}</span>
          <SelectBusqueda v-model="nuevaOc" :buscar="buscarOrdenes" :etiqueta="t('Purchase order')" :prefijo="false" :vacio="t('Search a PO…')" /></label>
        <div class="tj-chips">
          <span v-for="id in p.oc_ids" :key="id" class="chip">{{ nombres.oc[id] || id }}
            <button type="button" class="btn-icono" :aria-label="t('Remove')" @click="p.oc_ids = p.oc_ids.filter((x) => x !== id)"><Icono nombre="cerrar" :tam="12" /></button></span>
          <span v-if="!p.oc_ids.length" class="ayuda">{{ t('Choose one or more POs (or start from the PO list and select several).') }}</span>
        </div>
        <details v-if="p.oc_ids.length && p.oc_ids.length <= 5" class="tj-lineas" @toggle="verLineas = $event.target.open">
          <summary>{{ p.posiciones.length ? t('Lines: {0} chosen', [p.posiciones.length]) : t('Lines: all the open ones') }}</summary>
          <div v-for="id in p.oc_ids" :key="id">
            <h4>{{ t('PO {0}', [nombres.oc[id] || id]) }}</h4>
            <table v-if="lineas[id]" class="tabla tj-tabla">
              <tbody><tr v-for="l in lineas[id]" :key="l.id">
                <td><input type="checkbox" :checked="elegida(l.id)" :aria-label="t('Label this line')" @change="alternarLinea(l.id)" /></td>
                <td>{{ l.posicion }}</td><td>{{ l.codigo_articulo }} <span class="ayuda">{{ [l.color, l.talla].filter(Boolean).join(' · ') }}</span></td>
                <td class="num">{{ fmtNum(l.cantidad) }} {{ l.unidad }}</td>
              </tr></tbody>
            </table>
            <p v-else class="ayuda">{{ t('Loading…') }}</p>
          </div>
        </details>
      </div>
      <div v-else-if="origen === 'FAMILIA'" class="tj-bloque">
        <label class="campo"><span>{{ t('Labeling family') }}</span>
          <Seleccion :model-value="p.familia_id" @update:model-value="(v) => elegirFamilia(Number(v) || '')">
            <option value="">{{ t('Choose…') }}</option>
            <option v-for="f in familias" :key="f.id" :value="f.id">{{ tx(f.ruta || f.nombre) }}</option></Seleccion></label>
        <p v-if="p.familia_id" class="ayuda">{{ t('{0} open POs have items of this family; only those items are labeled.', [p.oc_ids.length]) }}</p>
      </div>
      <div v-else-if="origen === 'ARTICULOS'" class="tj-bloque">
        <label class="campo"><span>{{ t('Add an item') }}</span>
          <SelectBusqueda v-model="nuevoArticulo" :buscar="buscarArticulos" :etiqueta="t('Item')" :prefijo="false" :vacio="t('Search an item…')" /></label>
        <table v-if="p.articulos.length" class="tabla tj-tabla">
          <thead><tr><th>{{ t('Item') }}</th><th class="num">{{ t('Labels of each type') }}</th><th></th></tr></thead>
          <tbody><tr v-for="a in p.articulos" :key="a.articulo_id">
            <td>{{ nombres.articulo[a.articulo_id] || a.articulo_id }}</td>
            <td class="num"><input v-model.number="a.cantidad" type="number" min="1" class="tj-num" :aria-label="t('Labels')" /></td>
            <td><button type="button" class="btn-icono" :aria-label="t('Remove')" @click="p.articulos = p.articulos.filter((x) => x !== a)"><Icono nombre="basura" :tam="14" /></button></td>
          </tr></tbody>
        </table>
      </div>
      <div v-else class="tj-bloque">
        <label class="campo"><span>{{ t('Packing list') }}</span>
          <SelectBusqueda v-model="p.pl_id" :buscar="buscarPl" :etiqueta="t('Packing list')" :prefijo="false"
                          :opciones="listasEmpaque.map((x) => ({ valor: x.id, texto: x.numero, sub: [x.factura, x.proveedor].filter(Boolean).join(' · ') }))" /></label>
        <p v-if="niveles && !niveles.etiquetas_reales" class="nota aviso"><Icono nombre="alerta" :tam="16" />
          {{ t('The packing list is a draft: its packages can still change. Only test labels until it is confirmed.') }}</p>
      </div>

      <fieldset class="tj-tipos">
        <legend>{{ t('Which labels') }}</legend>
        <label v-for="x in tiposOrigen" :key="x.id" class="tj-tipo" :class="{ apagado: noAplica(x.id) }">
          <input type="checkbox" :checked="p.tipos.includes(x.id)" @change="alternarTipo(x.id)" />
          <strong>{{ tx(x.nombre) }}</strong>
          <span class="num">{{ deResumen(x.id) ? fmtNum(deResumen(x.id).etiquetas) : '' }}</span>
          <span class="ayuda">{{ CANTIDADES()[x.cantidad] }} · {{ SUJETOS()[x.sujeto] }}</span>
          <span v-if="noAplica(x.id)" class="ayuda">({{ x.sujeto === 'BULTO' ? t('needs a packing list') : t('nothing to label here') }})</span>
        </label>
        <p v-if="!tiposOrigen.length" class="ayuda">{{ t('There are no label types for this origin.') }}
          <router-link to="/etiquetas/configuracion?vista=tipos" class="enlace">{{ t('Set them up') }}</router-link></p>
      </fieldset>
      <label v-if="origen === 'PACKING' && conCajas && niveles" class="campo tj-cajas"><span>{{ t('Which packages') }}</span>
        <Seleccion v-model="p.tipo_empaque_id">
          <option value="">{{ t('Outer packages ({0})', [niveles.superiores]) }}</option>
          <option v-for="n in niveles.niveles" :key="n.tipo_empaque_id" :value="n.tipo_empaque_id">{{ tx(n.nombre || t('No type')) }} · {{ fmtNum(n.unidades) }}</option>
        </Seleccion></label>
      <fieldset class="tj-modo">
        <legend>{{ t('Mode') }}</legend>
        <label class="check"><input v-model="p.prueba" type="radio" :value="false" :disabled="niveles && !niveles.etiquetas_reales && origen === 'PACKING'" /> {{ t('Real') }}</label>
        <label class="check"><input v-model="p.prueba" type="radio" :value="true" /> {{ t('Test (marked TEST, not counted as printed)') }}</label>
      </fieldset>
    </section>

    <!-- 2. Revisar -->
    <section v-else-if="paso === 1" class="tj-bloque">
      <div v-if="generales.length || sinDiseno.length || otrosProblemas.length || avisos.length" class="panel tj-bloque">
        <h3 class="tj-h">{{ t('Problems') }}</h3>
        <p v-for="(x, i) in generales" :key="`g${i}`" :class="x.nivel === 'error' ? 'error-txt' : 'aviso-txt'"><Icono :nombre="NIVEL_ICONO[x.nivel]" :tam="14" /> {{ tx(x.mensaje) }}</p>
        <div v-for="g in sinDiseno" :key="g.tipo.id" class="tj-problema">
          <span class="error-txt"><Icono nombre="alerta" :tam="14" /> {{ t('{0} records without a design of “{1}”', [g.registros.length, tx(g.tipo.nombre)]) }}</span>
          <button type="button" class="btn btn-chico" :disabled="ocupado" @click="abrirEleccion(g)">{{ t('Choose design') }}</button>
        </div>
        <details v-for="(x, i) in otrosProblemas" :key="`o${i}`" class="tj-problema-det">
          <summary :class="x.nivel === 'error' ? 'error-txt' : 'aviso-txt'"><Icono :nombre="NIVEL_ICONO[x.nivel]" :tam="14" />
            {{ tx(x.mensaje) }} <span class="ayuda">· {{ CATEGORIAS()[x.categoria] || x.categoria }} · {{ t('{0} records', [x.referencias.length]) }}</span></summary>
          <p class="ayuda">{{ x.referencias.slice(0, 30).join(' · ') }}<template v-if="x.referencias.length > 30"> …</template></p>
          <button v-if="completable(x)" type="button" class="btn btn-chico" :disabled="ocupado"
                  @click="abrirCompletar(x)">{{ t('Complete the datum') }}</button>
        </details>
        <p v-for="(x, i) in avisos" :key="`a${i}`" class="aviso-txt"><Icono nombre="info" :tam="14" /> {{ tx(x.mensaje || x) }}</p>
      </div>
      <div v-else-if="trabajo?.validado_en" class="panel ok-txt"><Icono nombre="check" :tam="15" /> {{ t('No problems: everything is ready to generate.') }}</div>

      <div v-if="variables.length" class="panel tj-bloque">
        <h3 class="tj-h">{{ t('Data the design asks for') }}</h3>
        <div class="tj-fila"><label v-for="v in variables" :key="v.clave" class="campo"><span :class="{ req: v.obligatorio }">{{ tx(v.etiqueta) }}</span>
          <input v-model="p.manuales[v.clave]" :placeholder="v.defecto || ''" maxlength="200" @change="revalidar" /></label></div>
      </div>

      <div class="panel">
        <nav class="pestanas tj-pestanas" role="tablist" :aria-label="t('Label types')">
          <button v-for="x in tiposTrabajo" :key="x.tipo_etiqueta_id" type="button" class="pestana" role="tab" :aria-selected="tipoVista === x.tipo_etiqueta_id"
                  @click="tipoVista = x.tipo_etiqueta_id">{{ tx(x.tipo) }} <span class="cuenta" :class="{ alerta: x.errores }">{{ fmtNum(x.etiquetas) }}</span></button>
        </nav>
        <div class="tj-scroll">
          <table class="tabla tj-tabla">
            <thead><tr><th>{{ t('Labeled record') }}</th><th>{{ t('Design') }}</th><th>{{ t('Why') }}</th><th class="num">{{ t('Quantity') }}</th><th></th></tr></thead>
            <tbody>
              <tr v-for="r in delTipo.slice(0, mostrar)" :key="r.id" :class="{ 'con-error': r.estado === 'ERROR' }">
                <td>{{ r.referencia }}</td>
                <td><template v-if="r.plantilla">{{ tx(r.plantilla) }} <span class="ayuda">v{{ r.version }}</span></template>
                  <span v-else class="etiqueta error ms-0">{{ t('No design') }}</span></td>
                <td class="ayuda">{{ tx(r.motivo || '') }}</td>
                <td class="num">
                  <input v-if="tipoActual?.cantidad === 'MANUAL' || origen === 'ARTICULOS' || p.cantidades[r.clave] != null" :value="r.cantidad" type="number" min="0" class="tj-num"
                         :aria-label="t('Labels')" :disabled="ocupado" @change="cambiarCantidad(r, $event.target.value)" />
                  <button v-else type="button" class="enlace" :title="t('Change the quantity')" @click="p.cantidades = { ...p.cantidades, [r.clave]: r.cantidad }">{{ fmtNum(r.cantidad) }}</button>
                </td>
                <td><button v-if="r.plantilla_id" type="button" class="btn-icono" :aria-label="t('Preview')" @click="verPrevia(r)"><Icono nombre="ojo" :tam="15" /></button></td>
              </tr>
            </tbody>
          </table>
        </div>
        <button v-if="delTipo.length > mostrar" type="button" class="btn btn-chico mt" @click="mostrar += LIMITE">{{ t('Show {0} more of {1}', [Math.min(LIMITE, delTipo.length - mostrar), fmtNum(delTipo.length)]) }}</button>
        <p v-if="!delTipo.length" class="ayuda">{{ t('Nothing to label of this type here.') }}</p>
      </div>
    </section>

    <!-- 3. Generar -->
    <section v-else class="panel tj-bloque">
      <template v-if="!['GENERADO'].includes(trabajo?.estado)">
        <p>{{ t('{0} records ready ({1} labels).', [pendientes.length, fmtNum(etiquetasPendientes)]) }}
          <span v-if="conteo.ERROR">{{ t('{0} with errors stay pending.', [conteo.ERROR]) }}</span></p>
        <div class="tj-fila">
          <label class="campo"><span>{{ t('File of each run') }}</span>
            <Seleccion v-model="p.formato"><option value="PDF">PDF</option><option value="ZIP">{{ t('ZIP (PDF, PNG and SVG)') }}</option></Seleccion></label>
          <label class="campo"><span>{{ t('Files inside the job ZIP') }}</span>
            <Seleccion :model-value="p.zip.contenido" @update:model-value="cambiarContenido"><option value="PDF">PDF</option>
              <option value="PNG">{{ t('PNG (one per label)') }}</option><option value="SVG">{{ t('SVG (one per label)') }}</option></Seleccion></label>
          <label v-if="p.zip.contenido === 'PDF'" class="campo"><span>{{ t('Split into files') }}</span>
            <Seleccion :model-value="p.zip.agrupar" @update:model-value="cambiarAgrupar">
              <option v-for="[a, txt] in AGRUPACIONES()" :key="a" :value="a">{{ txt }}</option></Seleccion></label>
        </div>
        <fieldset v-if="conCarpetas" class="tj-carpetas"><legend>{{ t('Folders in the ZIP (in this order)') }}</legend>
          <label v-for="[c, txt] in CARPETAS()" :key="c" class="check"><input type="checkbox" :checked="p.zip.carpetas.includes(c)" @change="alternarCarpeta(c)" />
            {{ txt }}<span v-if="p.zip.carpetas.includes(c)" class="ayuda"> ({{ p.zip.carpetas.indexOf(c) + 1 }})</span></label>
          <small v-if="p.zip.agrupar === 'carpeta' && !p.zip.carpetas.length" class="ayuda">{{ t('Choose at least one folder level.') }}</small>
        </fieldset>
        <label v-if="p.zip.agrupar === 'etiqueta'" class="campo"><span>{{ t('File names') }}</span>
          <input v-model="p.zip.nombre" maxlength="120" :placeholder="'{i}-{referencia}-{n}'" />
          <small class="ayuda">{{ t('Fields: {0}. Repeated names get -2, -3…', [marcadoresTxt]) }}</small></label>
        <label v-if="advertencias" class="check"><input v-model="opciones.aceptar" type="checkbox" /> {{ t('I reviewed the {0} records with warnings', [advertencias]) }}</label>
        <label v-if="conteo.ERROR && trabajo?.permite_parcial" class="check"><input v-model="opciones.parcial" type="checkbox" />
          {{ t('Generate only the ready records and leave the ones with errors for later') }}</label>
        <p v-else-if="conteo.ERROR" class="nota">{{ t('Fix the errors to generate (your company does not allow partial generation).') }}</p>
        <p v-if="etiquetasPendientes >= (trabajo?.asincrono_desde || Infinity)" class="ayuda">{{ t('Large job: it is generated in the background and you can follow its progress.') }}</p>
        <div v-if="trabajo?.estado === 'EN_PROCESO'" class="tj-avance" role="progressbar" :aria-valuenow="trabajo.progreso" aria-valuemin="0" :aria-valuemax="trabajo.total">
          <div :style="{ width: `${Math.min(100, (trabajo.progreso * 100) / Math.max(trabajo.total, 1))}%` }"></div>
          <span>{{ t('{0} of {1} labels', [fmtNum(trabajo.progreso), fmtNum(trabajo.total)]) }}</span>
        </div>
        <button type="button" class="btn btn-primario tj-generar" :disabled="ocupado || !pendientes.length || trabajo?.estado === 'EN_PROCESO'" @click="generar">
          <Icono nombre="etiqueta" :tam="16" />{{ t('Generate {0} labels', [fmtNum(etiquetasPendientes)]) }}</button>
      </template>

      <template v-if="trabajo?.ejecuciones?.length">
        <p class="ok-txt"><Icono nombre="check" :tam="15" />
          {{ t('Generated: {0} labels in {1} runs.', [fmtNum(trabajo.ejecuciones.reduce((s, e) => s + e.total, 0)), trabajo.ejecuciones.length]) }}</p>
        <div class="tj-fila">
          <button type="button" class="btn btn-primario" @click="descargarTodo()"><Icono nombre="descargar" :tam="16" />{{ t('Download the job ZIP') }}</button>
          <button v-if="trabajo.estado === 'PARCIAL'" type="button" class="btn" @click="ir(1)"><Icono nombre="rehacer" :tam="16" />{{ t('Fix and generate the pending ones') }}</button>
          <button type="button" class="btn" @click="otroIgual"><Icono nombre="copiar" :tam="16" />{{ t('New job, the same') }}</button>
        </div>
        <details class="tj-historial" open>
          <summary>{{ t('Runs and printing') }}</summary>
          <table class="tabla tj-tabla">
            <thead><tr><th>#</th><th>{{ t('PO') }}</th><th class="num">{{ t('Labels') }}</th><th>{{ t('Status') }}</th><th>{{ t('Date') }}</th><th></th></tr></thead>
            <tbody><tr v-for="e in trabajo.ejecuciones" :key="e.id">
              <td>{{ e.id }}</td><td>{{ e.oc || '—' }}</td><td class="num">{{ fmtNum(e.total) }}</td>
              <td><EstadoBadge :estado="e.situacion" tipo="ejecucion" />
                <span v-if="e.impresa_en" class="ayuda"> {{ e.impresa_por }} · {{ e.impresion?.cantidad }}/{{ e.total }}</span></td>
              <td class="ayuda">{{ new Date(e.creada_en).toLocaleString() }} · {{ e.creada_por }}</td>
              <td class="tj-acciones">
                <button type="button" class="btn btn-chico" @click="descargarEjecucion(e)"><Icono nombre="descargar" :tam="14" />{{ t('Download') }}</button>
                <button v-if="!e.impresa_en" type="button" class="btn btn-chico" :disabled="!e.descargas"
                        :title="e.descargas ? '' : t('Download it before confirming the printing')"
                        @click="impresion = { id: e.id, total: e.total, cantidad: e.total, impresora: '', observacion: '', confirmo: false }">{{ t('Mark as printed') }}</button>
              </td>
            </tr></tbody>
          </table>
          <p class="ayuda">{{ t('Generated, downloaded and printed are different: printed is recorded only when someone confirms it.') }}</p>
        </details>
      </template>
    </section>
  </Asistente>

  <Modal v-if="completando" :titulo="t('Complete the datum')" ancho="480px" @cerrar="completando = null">
    <form id="form-completar" class="tj-bloque" @submit.prevent="completar">
      <p class="ayuda">{{ tx(completando.nombre) }}</p>
      <p class="nota">{{ t('Each item gets its own value; it is saved in its master data (same validations and history as Master data). Leave empty the ones you do not know.') }}</p>
      <div class="tj-completar">
        <label v-for="a in completando.articulos" :key="a.id" class="campo"><span>{{ a.referencia }}</span>
          <input v-model="completando.valores[a.id]" maxlength="120" /></label>
      </div>
    </form>
    <template #pie>
      <button class="btn separar" type="button" @click="completando = null">{{ t('Cancel') }}</button>
      <button class="btn btn-primario" type="submit" form="form-completar" :disabled="ocupado || !Object.values(completando.valores).some((v) => String(v).trim())">{{ t('Save and check again') }}</button>
    </template>
  </Modal>

  <Modal v-if="eleccion" :titulo="t('Design for “{0}”', [tx(eleccion.grupo.tipo.nombre)])" ancho="620px" @cerrar="eleccion = null">
    <div class="tj-bloque">
      <p class="ayuda">{{ t('{0} records have no design of this type.', [eleccion.grupo.registros.length]) }}</p>
      <SelectorDiseno v-model="eleccion.plantilla_id" :tipo-id="eleccion.grupo.tipo.id" />
      <label v-if="puede('etiquetas.configurar')" class="check"><input v-model="eleccion.regla" type="checkbox" /> {{ t('Save it as the design of') }}
        <Seleccion v-model="eleccion.lugar" :disabled="!eleccion.regla" :aria-label="t('Place')">
          <option v-for="l in eleccion.lugares" :key="l.clave" :value="l.clave">{{ l.nombre }}</option></Seleccion></label>
      <p class="ayuda">{{ eleccion.regla ? t('Next jobs use it too; it can be changed in Setup → Which design goes on what.') : t('Only for this job.') }}</p>
    </div>
    <template #pie>
      <button type="button" class="btn separar" @click="eleccion = null">{{ t('Cancel') }}</button>
      <button type="button" class="btn btn-primario" :disabled="!eleccion.plantilla_id || ocupado" @click="aplicarEleccion">{{ t('Use this design') }}</button>
    </template>
  </Modal>

  <PanelLateral v-if="previa" :titulo="registroPrevia?.referencia || t('Preview')" ancho="720px" @cerrar="previa = null">
    <template #estado><span class="ayuda">{{ tx(previa.plantilla) }} · v{{ previa.version }}</span></template>
    <div class="tj-svg previa-etiqueta" v-html="previa.svg"></div>
    <p class="ayuda">{{ tx(previa.motivo || '') }}</p>
    <dl class="tj-valores">
      <template v-for="(v, k) in previa.valores" :key="k"><dt>{{ k }}</dt><dd>{{ v ?? '—' }}
        <span v-if="previa.procedencia?.[k]" class="etiqueta info ms-0">{{ t('from {0}', [previa.procedencia[k]]) }}</span></dd></template>
    </dl>
    <template #pie>
      <button type="button" class="btn" @click="moverPrevia(-1)"><Icono nombre="atras" :tam="15" />{{ t('Previous') }}</button>
      <button type="button" class="btn" @click="moverPrevia(1)">{{ t('Next') }}<Icono nombre="derecha" :tam="15" /></button>
    </template>
  </PanelLateral>

  <Modal v-if="impresion" :titulo="t('Mark as printed')" @cerrar="impresion = null">
    <form id="form-impresion" class="tj-bloque" @submit.prevent="confirmarImpresion">
      <label class="campo"><span class="req">{{ t('Labels printed') }}</span>
        <input v-model.number="impresion.cantidad" type="number" min="1" :max="impresion.total" required /></label>
      <label class="campo"><span>{{ t('Printer') }}</span><input v-model="impresion.impresora" maxlength="100" /></label>
      <label class="campo"><span :class="{ req: impresion.cantidad !== impresion.total }">{{ t('Note') }}</span>
        <input v-model="impresion.observacion" maxlength="300" :required="impresion.cantidad !== impresion.total"
               :placeholder="impresion.cantidad !== impresion.total ? t('Why not all of them') : ''" /></label>
      <label class="check"><input v-model="impresion.confirmo" type="checkbox" required /> {{ t('I confirm these labels were printed') }}</label>
    </form>
    <template #pie>
      <button type="button" class="btn separar" @click="impresion = null">{{ t('Cancel') }}</button>
      <button type="submit" class="btn btn-primario" form="form-impresion">{{ t('Confirm') }}</button>
    </template>
  </Modal>
</template>

<style scoped>
.tj-estado { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; font-size: 0.9rem; }
.tj-bloque { display: flex; flex-direction: column; gap: 12px; }
.tj-fila { display: flex; gap: 12px; flex-wrap: wrap; align-items: flex-end; }
.tj-fila > .campo { flex: 1 1 220px; }
.tj-h { margin: 0; font-size: 0.95rem; font-weight: 650; }
.tj-origenes { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 10px; }
.tj-origen { display: flex; flex-direction: column; gap: 4px; text-align: start; border: 1px solid var(--linea); border-radius: 10px; padding: 12px;
  background: var(--superficie); font: inherit; color: var(--tinta); cursor: pointer; min-height: 44px; }
.tj-origen span { color: var(--tinta-3); font-size: 0.85rem; }
.tj-origen[aria-checked='true'] { border-color: var(--acento); background: var(--acento-claro); }
.tj-origen:disabled:not([aria-checked='true']) { opacity: 0.5; cursor: default; }
.tj-chips { display: flex; gap: 6px; flex-wrap: wrap; align-items: center; }
.chip { display: inline-flex; align-items: center; gap: 4px; border: 1px solid var(--linea); border-radius: 16px; padding: 2px 4px 2px 10px; font-size: 0.85rem; }
.tj-lineas summary, .tj-problema-det summary, .tj-historial summary { cursor: pointer; }
.tj-lineas h4 { margin: 8px 0 4px; font-size: 0.9rem; }
.tj-tipos, .tj-modo, .tj-carpetas { border: 1px solid var(--linea); border-radius: 8px; padding: 8px 12px; display: flex; flex-direction: column; gap: 6px; }
.tj-modo { flex-direction: row; gap: 18px; flex-wrap: wrap; }
.tj-tipo { display: grid; grid-template-columns: auto minmax(140px, 1fr) 80px minmax(0, 1.4fr); gap: 10px; align-items: center; min-height: 36px; }
.tj-tipo.apagado { opacity: 0.6; }
.tj-tipo .num { text-align: end; font-variant-numeric: tabular-nums; }
.tj-cajas { max-width: 420px; }
.tj-problema { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
.tj-problema-det p { margin: 4px 0 0 22px; }
.tj-pestanas { margin: 0 0 8px; }
.tj-scroll { max-height: 60vh; overflow: auto; }
.tj-tabla { width: 100%; }
.tj-tabla .num { text-align: end; }
.tj-num { width: 80px; text-align: end; }
tr.con-error > td { background: var(--error-fondo, transparent); }
.tj-carpetas { flex-direction: row; gap: 14px; flex-wrap: wrap; }
.tj-avance { position: relative; height: 22px; border-radius: 6px; background: var(--linea-suave); overflow: hidden; }
.tj-avance > div { height: 100%; background: var(--acento); transition: width 0.3s; }
.tj-avance > span { position: absolute; inset: 0; display: grid; place-items: center; font-size: 0.8rem; }
.tj-generar { align-self: flex-start; }
.tj-acciones { display: flex; gap: 6px; flex-wrap: wrap; }
.tj-svg { background: var(--papel); border: 1px dashed var(--linea); padding: 12px; --previa-alto: min(56vh, 520px); }
.tj-svg :deep(svg) { box-shadow: 0 1px 4px rgba(0, 0, 0, 0.15); background: #fff; }
.tj-valores { display: grid; grid-template-columns: auto 1fr; gap: 4px 10px; font-size: 0.84rem; margin: 0; }
.tj-valores dt { color: var(--tinta-3); font-family: var(--mono, monospace); }
.tj-valores dd { margin: 0; overflow-wrap: anywhere; }
.ok-txt { color: var(--ok); display: flex; gap: 6px; align-items: center; }
.error-txt { color: var(--error); margin: 0; }
.aviso-txt { color: var(--aviso); margin: 0; }
@media (max-width: 640px) { .tj-tipo { grid-template-columns: auto 1fr auto; } .tj-tipo .ayuda { grid-column: 2 / -1; } }
.tj-completar { display: flex; flex-direction: column; gap: 8px; max-height: 50vh; overflow: auto; }
</style>
