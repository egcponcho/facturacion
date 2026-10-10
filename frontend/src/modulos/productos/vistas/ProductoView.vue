<script setup>
import { t, tx } from '@/i18n/index.js'
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import Seleccion from '@/componentes/Seleccion.vue'
import { onBeforeRouteLeave, useRouter } from 'vue-router'
import { api } from '@/nucleo/api'
import EstadoBadge from '@/componentes/EstadoBadge.vue'
import AcuerdosOrigen from '@/modulos/productos/componentes/ficha/AcuerdosOrigen.vue'
import FichaTecnica from '@/modulos/productos/componentes/ficha/FichaTecnica.vue'
import DocumentosTecnicos from '@/modulos/productos/componentes/ficha/DocumentosTecnicos.vue'
import GenericoModal from '@/modulos/maestros/componentes/GenericoModal.vue'
import AvisoEdicion from '@/componentes/AvisoEdicion.vue'
import { useEdicion } from '@/composables/useEdicion'
import Icono from '@/componentes/Icono.vue'
import Modal from '@/componentes/Modal.vue'
import Pasos from '@/componentes/Pasos.vue'
import { cargarContexto, entradaDe, fichaDe, sesion } from '@/modulos/clasificacion/useClasificacion'
import { EST_PAIS, FUENTES, PAIS_LISTO, digits, fmtCode, fmtPais } from '@/modulos/clasificacion/formato.js'
import { puede, sesion as sesionUsuario } from '@/stores/sesion'
import { avisar, errorApi } from '@/stores/ui'
import { fmtFecha, fmtFechaHora } from '@/nucleo/utils'
import { confirmar } from '@/stores/confirmar'

// Ficha técnica del producto (estilo-color) y su clasificación arancelaria.
// Cada cambio se manda al motor único del servidor (/clasificacion/sesion),
// que devuelve los campos, la sugerencia, los códigos por país y la evidencia;
// guardar y aprobar vuelven a pasar por el mismo motor.
const props = defineProps({ id: [String, Number] })
const router = useRouter()

const p = ref(null)
const ctx = ref(null)
const opciones = ref({ paises: [] })
const f = reactive({ ficha: { comp: {} }, partidas: {}, alertasOk: [] })
const r = ref(null) // respuesta del motor
const tocados = reactive(new Set())
const filas = reactive({}) // filas de composición que se editan, por campo comp.*
const pestana = ref('ficha')
const NIVEL_CONF = { high: t('high'), medium: t('medium'), low: t('low') }
const ocupado = ref(false)
const calculando = ref(false)
const base = ref('')
const codOficial = ref('')
const otroCodigo = ref('')
const modal = ref(null)
const verRazones = ref(false)
const agregarTallas = ref(false)
const cargas = ref(0) // vuelve a montar el formulario tras guardar

const aprobado = computed(() => ['aprobado', 'corregido'].includes(p.value?.estado))
const enRevision = computed(() => p.value?.estado === 'revision')
// En borrador la edita cualquiera con permiso; enviada a revisión, solo quien revisa
const puedeEditar = computed(() => !!p.value && !p.value.edicion && !aprobado.value && puede('producto.ficha') && (!enRevision.value || !!p.value.puede_aprobar))
const puedeEnviar = computed(() => !!p.value && ['borrador', 'sugerida', 'observado'].includes(p.value.estado) && puede('producto.ficha'))
const puedeAprobar = computed(() => !!p.value?.puede_aprobar && !p.value?.edicion)
// Flujo de clasificación configurado por el administrador
const flujo = computed(() => sesionUsuario.usuario?.flujo || {})
const oculta = computed(() => !!(p.value?.sugerencia_oculta || r.value?.sugerencia_oculta))
const envioPrevio = computed(() => puedeEnviar.value && (!puedeAprobar.value || !!flujo.value.revision_obligatoria))
// Una decisión de aduanas que el motor no habría tomado solo se puede volver regla
const reglaDesdeAqui = computed(() => aprobado.value && puede('clasificacion.configurar') && !!p.value?.tipo
  && (p.value.estado === 'corregido' || p.value.confianza !== 'high' || (p.value.evidencia?.aprobacion?.sugerido || '') !== (p.value.evidencia?.aprobacion?.hs6 || '')))
// Recorrido del artículo: datos → ficha → clasificación → revisión → aprobado
const pasos = computed(() => {
  if (!p.value) return []
  const e = p.value.estado
  const base = !!f.tipo && !!f.origen
  const clasificado = oculta.value ? completa.value : codigo6.value.length === 6
  const revision = aprobado.value ? 'hecho' : e === 'revision' ? 'actual' : e === 'observado' ? 'alerta' : 'pendiente'
  return [
    { titulo: t('Product data'), estado: base || aprobado.value ? 'hecho' : 'actual', detalle: base ? '' : t('Category and country of origin') },
    { titulo: t('Technical sheet'), estado: completa.value || aprobado.value ? 'hecho' : base ? 'actual' : 'pendiente',
      detalle: !completa.value && !aprobado.value && faltan.value.length ? t('{0} to complete', [faltan.value.length]) : '' },
    { titulo: t('Classification'), estado: clasificado || aprobado.value ? 'hecho' : 'pendiente',
      detalle: oculta.value && !aprobado.value ? t('Assigned by customs') : codigo6.value.length === 6 ? fmtCode(codigo6.value) : '' },
    { titulo: t('Customs review'), estado: revision, detalle: e === 'observado' ? t('Returned with notes') : e === 'revision' ? t('In review') : '' },
    { titulo: t('Approved'), estado: aprobado.value ? 'hecho' : 'pendiente', detalle: aprobado.value && p.value.revisado_en ? fmtFecha(p.value.revisado_en) : '' },
  ]
})
const bloqueoAprobar = computed(() => {
  if (flujo.value.revision_obligatoria && !enRevision.value) return t('Send it to review first: the workflow asks for a review before approval.')
  if (flujo.value.cuatro_ojos && p.value?.enviado_por_mi) return t('You sent this sheet to review; another person has to approve it.')
  return ''
})

// Por qué no se puede aprobar todavía (visible, no solo en el tooltip)
const motivoNoAprobar = computed(() => {
  if (bloqueoAprobar.value) return bloqueoAprobar.value
  if (!completa.value) return t('Complete the technical sheet first: {0}.', [faltan.value.join(', ') || t('required fields')])
  if (errores.value.length) return t('Fix the errors first')
  if (!calculando.value && codigo6.value.length < 6) return t('There is no HS code to approve yet: answer the questions or choose a code.')
  return ''
})
const sugerido = computed(() => r.value?.clasificacion?.sac?.codigo || r.value?.hs6 || '')
const codigo = computed(() => (aprobado.value ? fmtCode(p.value.sac_codigo || p.value.codigo) : codOficial.value || fmtCode(sugerido.value)))
const codigo6 = computed(() => digits(codigo.value).slice(0, 6))
const descHs6 = computed(() => (aprobado.value || !r.value ? '' : r.value.clasificacion?.hs6?.descripcion || ''))

// ---- El motor del servidor ---------------------------------------------------
// Cada cambio pide una evaluación nueva (con espera corta); una respuesta vieja
// se descarta. Lo que el motor normaliza vuelve a la ficha.
let espera = null
let turno = 0
let cambioPend = null
const reiniciar = new Set()
function pedir(cambio = null, ms = 250) {
  if (cambio) cambioPend = cambio
  clearTimeout(espera)
  espera = setTimeout(evaluar, ms)
}
async function evaluar(alCargar = false) {
  if (!p.value) return
  const n = ++turno
  const cambio = cambioPend
  cambioPend = null
  calculando.value = true
  try {
    const res = await sesion(entradaDe(p.value, f, {
      tocados: [...tocados], autos: r.value?.autos || [], cambio, detectar: puedeEditar.value,
      codigo_final: digits(codOficial.value) || null,
    }))
    if (n !== turno) return
    r.value = res
    if (puedeEditar.value) {
      f.ficha = { ...res.ficha, comp: { ...(res.ficha.comp || {}) } }
      if (res.categoria?.codigo && res.categoria.codigo !== f.tipo) f.tipo = res.categoria.codigo
    }
    for (const c of res.campos.filter((x) => x.tipo_dato === 'composition' && x.codigo.startsWith('comp.'))) {
      if (!filas[c.codigo] || reiniciar.has(c.codigo)) filas[c.codigo] = (c.composicion?.filas || []).map(({ m, pct }) => ({ m, pct }))
      reiniciar.delete(c.codigo)
    }
    // Lo que el motor normaliza al abrir la ficha no es un cambio de la persona
    if (alCargar) base.value = instantanea()
  } catch (e) {
    if (n === turno) errorApi(e)
  } finally {
    if (n === turno) calculando.value = false
  }
}

function cambio({ campo, valor, reiniciar: rei, extra }) {
  if (campo === 'tipo') {
    f.tipo = valor
    tocados.add('tipo')
    return pedir()
  }
  if (campo === 'origen') {
    f.origen = valor
    return pedir()
  }
  if (campo.startsWith('comp.')) {
    f.ficha.comp = { ...(f.ficha.comp || {}), [campo.slice(5)]: valor }
    tocados.add(campo)
    if (rei) reiniciar.add(campo)
    return pedir()
  }
  if (['desc', 'descCom', 'descManual', 'comManual'].includes(campo)) {
    f.ficha[campo] = valor
    Object.assign(f.ficha, extra || {})
    return
  }
  f.ficha[campo] = valor
  tocados.add(campo)
  pedir(campo === 'uso' ? null : { campo, valor }, campo === 'uso' ? 400 : 150)
}

// ---- Notas legales de apoyo ---------------------------------------------------
// Primero las del capítulo y de subpartida, luego las de sección y al final las
// reglas generales; las que cita el razonamiento del motor y las que tocan datos
// de esta ficha (r.etiquetas: categoría, género, edad, materiales…) van primero
const ORDEN_NOTA = { explicativa: 0, subpartida: 0, capitulo: 1, complementaria: 1, seccion: 2, reglas: 3 }
const etiquetasFicha = computed(() => new Set(r.value?.etiquetas || []))
const citada = (n) => {
  const txt = (r.value?.razones || []).join(' ').toLowerCase()
  const cita = n.ambito !== 'reglas' && txt.includes(`note ${String(n.numero).toLowerCase().split(' ')[0]}`) && txt.includes(`chapter ${n.codigo}`) ? 3 : 0
  const propio = n.codigo === codigo6.value.slice(0, 2) ? 0.5 : 0
  const legal = (r.value?.evidencia?.notas || []).some((x) => x.id === n.id) ? 4 : 0 // la cita una regla legal aplicada
  return legal + cita + propio + (n.claves || []).filter((k) => etiquetasFicha.value.has(k)).length
}
const notasSac = computed(() => {
  const cap = codigo6.value.slice(0, 2)
  if (!cap) return []
  return (ctx.value?.notas_sac || []).filter((n) => (!n.capitulos.length || n.capitulos.includes(cap))
    && (n.ambito !== 'explicativa' || codigo6.value.startsWith(n.codigo)))
    .sort((a, b) => citada(b) - citada(a) || (ORDEN_NOTA[a.ambito] ?? 9) - (ORDEN_NOTA[b.ambito] ?? 9))
})
const verNotas = ref(false)
const soporte = ref('legales')
// Texto legal publicado (oficial) aparte de la guía: resúmenes del clasificador y notas internas
const notasLegales = computed(() => notasSac.value.filter((n) => n.oficial))
const notasExplicativas = computed(() => notasSac.value.filter((n) => !n.oficial))
const notasVista = computed(() => (soporte.value === 'explicativas' ? notasExplicativas.value : notasLegales.value))

// Base legal de cada país destino (agrupada: varios comparten el mismo arancel)
const basesLegales = computed(() => {
  const g = new Map()
  for (const d of ctx.value?.destinos || []) if (d.base_legal) g.set(d.base_legal, [...(g.get(d.base_legal) || []), d.iso])
  return [...g].map(([texto, isos]) => ({ texto, isos }))
})

// Reglas que decidieron: las de nota legal (evidencia legal) aparte de las ejecutadas del sistema o propias
const reglasAplicadas = computed(() => (r.value?.reglas || []).filter((x) => x.aplicada && !String(x.efecto).startsWith('BUILTIN')))

// ---- Carga ---------------------------------------------------------------
function tomar(det) {
  p.value = det
  const x = fichaDe(det)
  for (const k of Object.keys(f)) delete f[k]
  Object.assign(f, x)
  tocados.clear()
  // Al abrir una ficha guardada, lo que ya tiene valor cuenta como elegido
  for (const [k, v] of Object.entries(x.ficha)) if (k !== 'comp' && v !== '' && v != null && v !== false) tocados.add(k)
  if (x.tipo) tocados.add('tipo')
  for (const k of Object.keys(filas)) delete filas[k]
  codOficial.value = ''
  cargas.value++
  base.value = instantanea()
  evaluar(true)
}
function instantanea() {
  return JSON.stringify([f.tipo, f.ficha, f.nombre, f.origen, f.alertasOk, f.partidas])
}
const sucio = computed(() => !!p.value && instantanea() !== base.value)

async function recargarContexto() {
  ctx.value = await cargarContexto(true)
  pedir()
}

async function cargar() {
  try {
    const [det, c, op] = await Promise.all([api.get(`/productos/${props.id}`), cargarContexto(), api.get('/productos/opciones')])
    ctx.value = c
    opciones.value = op
    tomar(det)
  } catch (e) {
    errorApi(e)
    if (e.status === 404) router.replace('/productos')
  }
}

// ---- Clasificación -------------------------------------------------------
const alertas = computed(() => r.value?.alertas || [])
const faltan = computed(() => [...(f.tipo ? [] : [t('Product type')]), ...(r.value?.faltantes || []).map((x) => x.etiqueta)])
const completa = computed(() => !!r.value?.completa && !!f.tipo)
// Lo que subiría la confianza (no bloquea la ficha)
const pistas = computed(() => [...(r.value?.avisos || []).map((x) => x.texto), ...(r.value?.revision_por || [])].slice(0, 3))
const errores = computed(() => alertas.value.filter((a) => a.nivel === 'error'))
const confNivel = computed(() => ({ high: 3, medium: 2, low: 1 })[r.value?.confianza] || 0)
const fuente = computed(() => {
  const o = r.value?.candidatos?.[0]?.origen || []
  return o.some((x) => x.startsWith('regla')) ? 'regla' : o.includes('historial') ? 'historial' : 'texto'
})

function revisada(a) {
  f.alertasOk = [...new Set([...(f.alertasOk || []), a.clave])]
  pedir()
}
function usarCodigo(c) {
  codOficial.value = fmtCode(c)
  otroCodigo.value = ''
  pedir()
}
function aplicarOtro() {
  const d = digits(otroCodigo.value)
  if (d.length < 6) return avisar(t('Write at least the 6-digit subheading.'), 'error')
  usarCodigo(d)
}
watch(codOficial, (v, antes) => { if (!v && antes) pedir() })

const paises = computed(() => {
  if (!ctx.value) return []
  if (aprobado.value) {
    return ctx.value.destinos.map((d) => {
      const x = p.value.partidas[d.iso] || {}
      return { ...d, codigo: x.codigo, dai: x.dai, estado: x.codigo ? (x.estado || 'ok') : 'sin_codigo', fuente: x.fuente, manual: x.manual,
        opciones: opcionesPais[d.iso] || [] }
    })
  }
  const por = Object.fromEntries((r.value?.clasificacion?.paises || []).map((x) => [x.pais, x]))
  return ctx.value.destinos.map((d) => ({ ...d, ...(por[d.iso] ? { ...por[d.iso], iso: d.iso } : { estado: 'sin_codigo', opciones: [] }) }))
})
// Producto aprobado: las líneas nacionales son referencia y se confirman país por país
const opcionesPais = reactive({})
async function cargarOpcionesPais(x) {
  try {
    opcionesPais[x.iso] = (await api.get(`/productos/${p.value.id}/partidas/${x.iso}`)).opciones
    if (!opcionesPais[x.iso].length) avisar(t('{0} has no official national line in force for this subheading.', [x.nombre]))
  } catch (e) {
    errorApi(e)
  }
}
async function confirmarPais(x, codigo) {
  if (!codigo) return
  try {
    tomar(await api.post(`/productos/${p.value.id}/partidas/${x.iso}`, { codigo: digits(codigo) }))
    delete opcionesPais[x.iso]
    avisar(t('National code of {0} confirmed.', [x.nombre]))
  } catch (e) {
    errorApi(e)
  }
}
const paisesOk = computed(() => paises.value.filter((x) => PAIS_LISTO.includes(x.estado) && x.codigo).length)
function codigoPais(iso, c) {
  f.partidas = { ...(f.partidas || {}), [iso]: { codigo: digits(c), manual: true } }
  pedir()
}
// Código nacional escrito en la tabla de destinos: se aplica al salir del
// campo o con Enter si empieza con la subpartida y tiene una longitud válida
// del país; el motor lo vuelve a validar (línea del arancel o código propio)
const errPais = reactive({})
function escribirPais(x, el) {
  const c = digits(el.value)
  errPais[x.iso] = ''
  if (!c) {
    if (x.manual) quitarManual(x.iso)
    else el.value = x.codigo ? fmtPais(x.codigo, x.digitos) : ''
    return
  }
  if (c === digits(x.codigo || '')) {
    el.value = fmtPais(c, x.digitos)
    return
  }
  const lons = x.longitudes?.length ? x.longitudes : [x.digitos]
  if (!c.startsWith(codigo6.value)) errPais[x.iso] = t('Must start with {0}', [fmtCode(codigo6.value)])
  else if (!lons.includes(c.length)) errPais[x.iso] = t('{0} digits ({1} typed)', [lons.join(' / '), c.length])
  else {
    codigoPais(x.iso, c)
    el.value = fmtPais(c, x.digitos)
  }
}
function quitarManual(iso) {
  const { [iso]: _, ...resto } = f.partidas || {}
  f.partidas = resto
  pedir()
}

// ---- Guardar y flujo ---------------------------------------------------------
function cuerpoFicha() {
  return {
    version: p.value.version,
    tipo: f.tipo || null,
    ficha: f.ficha,
    nombre: f.nombre || '',
    pais_origen: f.origen || '',
    descripcion_aduana: f.ficha.descManual ? f.ficha.desc || '' : null,
    descripcion_comercial: f.ficha.comManual ? f.ficha.descCom || '' : null,
    alertas_ok: f.alertasOk || [],
    tocados: [...tocados],
    partidas: f.partidas || {},
  }
}

async function guardar(silencioso = false) {
  if (!puedeEditar.value) return
  ocupado.value = true
  try {
    tomar(await api.put(`/productos/${p.value.id}/ficha`, cuerpoFicha()))
    if (!silencioso) avisar(p.value.ficha_completa && puedeEnviar.value ? t('Draft saved. Send it to review when it is ready.') : t('Technical sheet saved.'))
    return true
  } catch (e) {
    errorApi(e)
    return false
  } finally {
    ocupado.value = false
  }
}

async function aprobar() {
  if (sucio.value && !(await guardar(true))) return
  const cod = codOficial.value || codigo.value
  ocupado.value = true
  try {
    tomar(await api.post(`/productos/${p.value.id}/aprobar`, { version: p.value.version, codigo: digits(cod), partidas: f.partidas || {} }))
    avisar(t('Approved as {0}. Orders and invoices now use it.', [fmtCode(p.value.codigo)]))
    cargarContexto(true)
  } catch (e) {
    errorApi(e)
  } finally {
    ocupado.value = false
  }
}

async function devolver() {
  ocupado.value = true
  try {
    tomar(await api.post(`/productos/${p.value.id}/observar`, { version: p.value.version, observaciones: modal.value.texto, devolver: true }))
    modal.value = null
    avisar(t('Returned to the supplier with your notes.'))
  } catch (e) {
    errorApi(e)
  } finally {
    ocupado.value = false
  }
}

async function nuevaVersion() {
  ocupado.value = true
  try {
    tomar(await api.post(`/productos/${p.value.id}/versiones`, { version: p.value.version, motivo: modal.value.texto, desde: modal.value.desde || null }))
    modal.value = null
    avisar(t('Version {0} opened. Update the sheet and send it for review.', [p.value.version_ficha]))
  } catch (e) {
    errorApi(e)
  } finally {
    ocupado.value = false
  }
}

// Enseñar el código nacional para que se use en productos parecidos: las
// condiciones son los datos de esta ficha que separan las líneas del país
const campoDe = (k) => (r.value?.campos || []).find((c) => c.codigo === k)
function textoHecho(k, v) {
  const c = campoDe(k)
  if (typeof v === 'boolean') return v ? t('Yes') : t('No')
  return c?.opciones?.find((o) => o.codigo === v)?.etiqueta || String(v)
}
function abrirEnsenar(x) {
  const hechos = r.value?.hechos || {}
  const ks = [...new Set([...(x.opciones || []).flatMap((o) => Object.keys(o.cond || {})), ...(x.faltan || [])])]
  const conds = ks.filter((k) => hechos[k] !== undefined && hechos[k] !== null && hechos[k] !== '')
    .map((k) => ({ k, v: hechos[k], l: campoDe(k)?.etiqueta || k, usar: true }))
  modal.value = { tipo: 'ensenar', pais: x, conds }
}
async function ensenar() {
  const m = modal.value
  const cond = Object.fromEntries(m.conds.filter((c) => c.usar).map((c) => [c.k, c.v]))
  ocupado.value = true
  try {
    await api.post('/clasificacion/incisos', { pais: m.pais.iso, codigo: digits(m.pais.codigo), cond })
    modal.value = null
    avisar(t('Saved in your company history: {0} will prefer {1} for products like this one.', [m.pais.nombre, fmtCode(m.pais.codigo)]))
    pedir()
  } catch (e) {
    errorApi(e)
  } finally {
    ocupado.value = false
  }
}

// ---- Fotos -----------------------------------------------------------------
async function subirFoto(e) {
  const a = e.target.files?.[0]
  e.target.value = ''
  if (!a) return
  const datos = new FormData()
  datos.append('archivo', a)
  ocupado.value = true
  try {
    await api.post(`/productos/${p.value.id}/fotos`, datos)
    const det = await api.get(`/productos/${p.value.id}`)
    p.value = { ...det }
    f.fotos = det.fotos
    base.value = instantanea()
  } catch (err) {
    errorApi(err)
  } finally {
    ocupado.value = false
  }
}
async function borrarFoto(foto) {
  try {
    await api.del(`/productos/${p.value.id}/fotos/${foto.id}`)
    p.value.fotos = p.value.fotos.filter((x) => x.id !== foto.id)
    f.fotos = p.value.fotos
    base.value = instantanea()
  } catch (e) {
    errorApi(e)
  }
}

// Fichas técnicas: sus datos son hechos del producto, el motor vuelve a clasificar
async function recargarDocumentos() {
  try {
    const det = await api.get(`/productos/${p.value.id}`)
    p.value = { ...p.value, documentos: det.documentos }
    pedir()
  } catch (e) {
    errorApi(e)
  }
}

// ---- Especialista (Claude) -----------------------------------------------------
// El servidor arma lo que ve el especialista con el mismo motor (ficha, sugerencia,
// razones, alertas, parecidos y los campos que puede corregir)
async function consultar() {
  if (sucio.value && !(await guardar(true))) return
  ocupado.value = true
  try {
    const op = await api.post(`/productos/${p.value.id}/analizar`, { con_fotos: true })
    p.value = { ...p.value, opinion_ia: op }
  } catch (e) {
    errorApi(e)
  } finally {
    ocupado.value = false
  }
}
const nombreCampo = (c) => campoDe(c.campo)?.etiqueta || c.campo
function valorCorreccion(c) {
  const k = campoDe(c.campo)
  if (k?.tipo_dato === 'boolean') return c.valor === true || c.valor === 'true'
  return c.valor
}
const valorLegible = (c) => textoHecho(c.campo, valorCorreccion(c))
function aplicarCorreccion(c) {
  cambio({ campo: c.campo, valor: valorCorreccion(c) })
}

async function descargarFicha(formato, version) {
  try {
    await api.descargar(`/productos/${p.value.id}/ficha`, `sheet_${p.value.estilo}${version ? `_v${version}` : ''}.${formato}`, { formato, version })
  } catch (e) {
    errorApi(e)
  }
}

// ---- Borrador → revisión ------------------------------------------------------
async function enviarRevision() {
  if (sucio.value && !(await guardar(true))) return
  ocupado.value = true
  try {
    await api.post('/productos/enviar', { ids: [p.value.id] })
    tomar(await api.get(`/productos/${p.value.id}`))
    avisar(t('Sent to review. It stays locked until customs approves or returns it.'))
  } catch (e) {
    errorApi(e)
  } finally {
    ocupado.value = false
  }
}
async function retirarRevision() {
  ocupado.value = true
  try {
    tomar(await api.post(`/productos/${p.value.id}/retirar`))
    avisar(t('Back to draft: you can edit it again.'))
  } catch (e) {
    errorApi(e)
  } finally {
    ocupado.value = false
  }
}

// ---- Versiones anteriores ------------------------------------------------------
const versionVista = ref(null)
async function verVersion(v) {
  try {
    versionVista.value = await api.get(`/productos/${p.value.id}/versiones/${v.version}`)
  } catch (e) {
    errorApi(e)
  }
}

// ---- Historial -------------------------------------------------------------
const ACCION = {
  ficha_guardada: t('Saved the technical sheet'),
  clasificado: t('Ran the classification'),
  aprobado: t('Approved the classification'),
  corregido: t('Approved with a different code'),
  devuelto: t('Returned to the supplier'),
  observacion: t('Added a note'),
  nueva_version: t('Opened a new version'),
  enviado: t('Sent to review'),
  retirado: t('Took it back to draft'),
  opinion_especialista: t('Asked the specialist'),
  foto_agregada: t('Added a photo'),
  foto_quitada: t('Removed a photo'),
}
function detalleHist(h) {
  const d = h.detalle || {}
  if (d.codigo) return d.codigo + (d.sugerido && d.sugerido !== d.codigo ? t(' (suggested {0})', [d.sugerido]) : '')
  if (d.sugerido) return t('Suggested {0}', [d.sugerido])
  if (d.observaciones) return d.observaciones
  if (d.version) return t('Version {0}', [d.version])
  return ''
}

// Aviso al salir con cambios sin guardar
function antesDeSalir(e) {
  if (sucio.value && puedeEditar.value) {
    e.preventDefault()
    e.returnValue = ''
  }
}
onBeforeRouteLeave(async () => !(sucio.value && puedeEditar.value)
  || confirmar(t('The technical sheet has unsaved changes. Leave anyway?'), { boton: t('Leave without saving'), peligro: true }))
onMounted(() => {
  cargar()
  window.addEventListener('beforeunload', antesDeSalir)
})
onBeforeUnmount(() => window.removeEventListener('beforeunload', antesDeSalir))

// Edición exclusiva: una persona edita y las demás ven en solo lectura
const edicion = useEdicion('producto', () => Number(props.id), () => ({ editable: puedeEditar.value, edicion: p.value?.edicion }), cargar)
</script>

<template>
  <div v-if="p && ctx">
    <router-link to="/productos" class="volver"><Icono nombre="atras" :tam="15" />{{ t('Products') }}</router-link>
    <AvisoEdicion :edicion="p.edicion" :pausado="edicion.pausado.value" entidad="producto" :id="Number(props.id)" @liberado="cargar" @continuar="edicion.continuar" />

    <section class="doc-cabeza">
      <div class="doc-fila">
        <span class="foto-cabeza">
          <img v-if="p.fotos.length" :src="`/api/productos/fotos/${p.fotos[0].id}`" alt="" />
          <Icono v-else nombre="caja" :tam="24" />
        </span>
        <div>
          <span class="doc-numero">{{ tx(p.estilo) }} · {{ tx(p.color) }}</span>
          <div class="doc-sub"><span v-if="p.codigo_generico" class="etiqueta acento ms-0" :title="t('Generic (style-color)')">{{ t('Generic {0}', [p.codigo_generico]) }}</span> {{ tx(p.descripcion_comercial || '—') }} · {{ tx(p.marca_nombre || p.marca) }}<template v-if="p.proveedor && p.proveedor !== (p.marca_nombre || p.marca)"> · {{ tx(p.proveedor) }}</template></div>
        </div>
        <EstadoBadge :estado="p.estado" />
        <span v-if="p.version_ficha > 1" class="etiqueta">{{ t('Version {0}', [p.version_ficha]) }}</span>
        <div class="doc-acciones">
          <MasOpciones>
            <button class="btn btn-fantasma" :title="t('Technical sheet with the classification, as PDF')" @click="descargarFicha('pdf')"><Icono nombre="descargar" />PDF</button>
            <button class="btn btn-fantasma" :title="t('Technical sheet with composition and national codes, as Excel')" @click="descargarFicha('xlsx')"><Icono nombre="descargar" />{{ t('Excel') }}</button>
            <button v-if="aprobado && puede('producto.ficha')" class="btn" @click="modal = { tipo: 'version', texto: '', desde: '' }"><Icono nombre="editar" />{{ t('New version') }}</button>
            <router-link v-if="reglaDesdeAqui" class="btn" :to="{ path: '/familias', query: { vista: 'reglas', desde: p.id } }"
                         :title="t('Next time the engine suggests this code by itself')"><Icono nombre="varita" />{{ t('Turn this decision into a rule') }}</router-link>
            <button v-if="enRevision && puede('producto.ficha')" class="btn" :disabled="ocupado" :title="t('Take it back to draft to change it')" @click="retirarRevision"><Icono nombre="atras" />{{ t('Back to draft') }}</button>
          </MasOpciones>
          <button v-if="puedeEditar" class="btn" :class="{ 'btn-primario': !puedeEnviar || puedeAprobar }" :disabled="ocupado || !sucio" @click="guardar()"><Icono nombre="check" />{{ tx(sucio ? (puedeEnviar ? t('Save draft') : t('Save sheet')) : t('Saved')) }}</button>
          <button v-if="envioPrevio" class="btn btn-primario" :disabled="ocupado || !completa || (!oculta && codigo6.length < 6)"
                  :title="tx(!completa ? t('Complete first: {0}', [faltan.join(', ')]) : t('Customs reviews it and approves or returns it'))" @click="enviarRevision"><Icono nombre="enviar" />{{ t('Send to review') }}</button>
        </div>
      </div>
      <div class="doc-meta">
        <span>{{ t('Sizes') }} <b>{{ tx(p.rango_tallas || '—') }}</b></span>
        <span>{{ t('SKUs') }} <b>{{ tx(p.skus) }}</b></span>
        <span>{{ t('Origin') }} <b>{{ tx(f.origen || '—') }}</b></span>
        <span v-if="p.revisado_por">{{ t('Reviewed by') }} <b>{{ tx(p.revisado_por) }}</b> · {{ fmtFecha(p.revisado_en) }}</span>
      </div>
    </section>

    <Pasos class="pasos-producto" :pasos="pasos" />

    <p v-if="p.estado === 'observado' && p.observaciones" class="nota aviso" role="status">
      <Icono nombre="alerta" /><span><b>{{ t('Returned for correction.') }}</b> {{ tx(p.observaciones) }}</span>
    </p>
    <p v-else-if="enRevision" class="nota info" role="status">
      <Icono nombre="reloj" /><span><b>{{ t('In review.') }}</b> {{ tx(p.puede_aprobar ? t('Check it and approve the code or return it with notes.') : t('Customs is reviewing it; it stays locked until they approve or return it. Take it back to draft if you need to change something.')) }}</span>
    </p>
    <p v-else-if="puedeEnviar && p.estado !== 'observado'" class="nota" role="status">
      <Icono nombre="editar" /><span><b>{{ t('Draft.') }}</b> {{ t('Anyone with access can edit it. Nobody reviews it until it is') }} <b>{{ t('sent to review') }}</b>.</span>
    </p>
    <p v-else-if="aprobado" class="nota ok">
      <Icono nombre="check" /><span>{{ t('This sheet is approved and locked. Purchase orders and invoices use its codes. To change it, open a new version.') }}</span>
    </p>

    <div class="producto-layout">
      <div class="producto-principal">
        <div class="pestanas" role="tablist">
          <button class="pestana" role="tab" :aria-selected="pestana === 'ficha'" @click="pestana = 'ficha'"><Icono nombre="lista" :tam="16" />{{ t('Technical sheet') }}
            <span v-if="r && faltan.length && !aprobado" class="cuenta alerta">{{ tx(faltan.length) }}</span></button>
          <button class="pestana" role="tab" :aria-selected="pestana === 'tallas'" @click="pestana = 'tallas'"><Icono nombre="caja" :tam="16" />{{ t('Sizes and prepacks') }}
            <span class="cuenta">{{ tx(p.articulos.length) }}</span></button>
          <button class="pestana" role="tab" :aria-selected="pestana === 'documentos'" @click="pestana = 'documentos'"><Icono nombre="archivo" :tam="16" />{{ t('Technical documents') }}
            <span v-if="p.documentos?.length" class="cuenta">{{ tx(p.documentos.length) }}</span></button>
          <button class="pestana" role="tab" :aria-selected="pestana === 'acuerdos'" @click="pestana = 'acuerdos'"><Icono nombre="ruta" :tam="16" />{{ t('Trade agreements') }}</button>
          <button class="pestana" role="tab" :aria-selected="pestana === 'versiones'" @click="pestana = 'versiones'"><Icono nombre="capas" :tam="16" />{{ t('Versions') }}
            <span class="cuenta">{{ tx(p.versiones.length + 1) }}</span></button>
          <button class="pestana" role="tab" :aria-selected="pestana === 'historial'" @click="pestana = 'historial'"><Icono nombre="historial" :tam="16" />{{ t('History') }}</button>
        </div>

        <!-- Ficha técnica -->
        <FichaTecnica v-if="pestana === 'ficha'" :key="`${p.id}-${p.version_ficha}-${cargas}`" :f="f" :r="r" :ctx="ctx" :producto="p" :paises="opciones.paises"
                      :filas="filas" :tocados="tocados" :editable="puedeEditar" @cambio="cambio" @subir-foto="subirFoto" @borrar-foto="borrarFoto" @contexto="recargarContexto" @acuerdos="pestana = 'acuerdos'" />

        <!-- Fichas técnicas SDS / TDS / COA: evidencia técnica, nunca fuente arancelaria -->
        <DocumentosTecnicos v-else-if="pestana === 'documentos'" :producto="p" :campos="r?.campos || []" :editable="puedeEditar" @cambio="recargarDocumentos" />

        <!-- Acuerdos comerciales por destino según el origen -->
        <AcuerdosOrigen v-else-if="pestana === 'acuerdos'" :origen="f.origen || ''" :ctx="ctx" :paises="opciones.paises" />

        <!-- Versiones: la vigente y las anteriores, para verlas y descargarlas -->
        <div v-else-if="pestana === 'versiones'" class="panel mt-chico">
          <div class="tabla-marco">
            <table class="tabla" v-tarjetas>
              <thead><tr><th>{{ t('Version') }}</th><th>{{ t('Valid') }}</th><th>{{ t('Status') }}</th><th>{{ t('HS code') }}</th><th>{{ t('Reason for the change') }}</th><th></th></tr></thead>
              <tbody>
                <tr class="seleccionada">
                  <td class="fuerte">{{ tx(p.version_ficha) }} <span class="etiqueta acento">{{ t('Current') }}</span></td>
                  <td>{{ tx(p.vigente_desde ? t('From {0}', [fmtFecha(p.vigente_desde)]) : t('Current')) }}</td>
                  <td><EstadoBadge :estado="p.estado" /></td>
                  <td class="codigo-sac">{{ tx(p.codigo || p.sugerido || '—') }}</td><td class="apagado">—</td>
                  <td class="num fila-flex" style="justify-content: flex-end">
                    <button class="btn btn-chico" @click="pestana = 'ficha'">{{ t('Open') }}</button>
                    <button class="btn btn-chico" @click="descargarFicha('pdf')">PDF</button>
                    <button class="btn btn-chico" @click="descargarFicha('xlsx')">{{ t('Excel') }}</button>
                  </td>
                </tr>
                <tr v-for="v in p.versiones" :key="v.version" :class="{ seleccionada: versionVista?.version === v.version }">
                  <td class="fuerte">{{ tx(v.version) }}</td><td>{{ fmtFecha(v.desde) }} – {{ fmtFecha(v.hasta) }}</td>
                  <td><EstadoBadge :estado="v.estado" /></td>
                  <td class="codigo-sac">{{ tx(v.codigo || '—') }}</td><td>{{ tx(v.motivo || '—') }}</td>
                  <td class="num fila-flex" style="justify-content: flex-end">
                    <button class="btn btn-chico" @click="verVersion(v)"><Icono nombre="lupa" :tam="13" />{{ t('View') }}</button>
                    <button class="btn btn-chico" @click="descargarFicha('pdf', v.version)">PDF</button>
                    <button class="btn btn-chico" @click="descargarFicha('xlsx', v.version)">{{ t('Excel') }}</button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <p v-if="!p.versiones.length" class="ayuda mt-chico">{{ t('There are no previous versions yet. Approved sheets are changed by opening a new version; the previous one stays here as it was.') }}</p>
          <div v-if="versionVista" class="version-vista mt">
            <div class="fila-flex" style="justify-content: space-between">
              <h3>{{ t('Version {0} · {1}', [versionVista.version, versionVista.estado_txt]) }}<span v-if="versionVista.vigencia" class="apagado"> · {{ fmtFecha(versionVista.vigencia.desde) }} – {{ fmtFecha(versionVista.vigencia.hasta) }}</span></h3>
              <button class="btn-icono" :aria-label="t('Close version')" @click="versionVista = null"><Icono nombre="cerrar" :tam="16" /></button>
            </div>
            <div class="rejilla-dl"><div v-for="[k, v] in versionVista.clasificacion" :key="k" class="par"><span>{{ tx(k) }}</span><b>{{ tx(v) }}</b></div></div>
            <p v-if="versionVista.descripcion" class="mt-chico"><b>{{ t('Customs description:') }}</b> {{ tx(versionVista.descripcion) }}</p>
            <h4 class="mt">{{ t('Product data') }}</h4>
            <div class="rejilla-dl"><div v-for="[k, v] in versionVista.datos" :key="k" class="par"><span>{{ tx(k) }}</span><b>{{ tx(v) }}</b></div></div>
            <template v-if="versionVista.composicion.length">
              <h4 class="mt">{{ t('Composition') }}</h4>
              <div class="rejilla-dl"><div v-for="[k, v] in versionVista.composicion" :key="k" class="par"><span>{{ tx(k) }}</span><b>{{ tx(v) }}</b></div></div>
            </template>
            <template v-if="versionVista.partidas.length">
              <h4 class="mt">{{ t('National codes by destination') }}</h4>
              <table class="tabla mt-chico" v-tarjetas>
                <thead><tr><th>{{ t('Country') }}</th><th>{{ t('Code') }}</th><th>{{ t('Duty (DAI)') }}</th><th>{{ t('Status') }}</th><th>{{ t('Source') }}</th></tr></thead>
                <tbody><tr v-for="x in versionVista.partidas" :key="x[0]"><td>{{ tx(x[0]) }}</td><td class="codigo-sac">{{ tx(x[1]) }}</td><td>{{ tx(x[2]) }}</td><td>{{ tx(x[3]) }}</td><td>{{ tx(x[4]) }}</td></tr></tbody>
              </table>
            </template>
          </div>
        </div>

        <!-- Tallas y prepacks -->
        <div v-else-if="pestana === 'tallas'">
          <div class="fila-flex mt-chico" style="justify-content: space-between">
            <p class="ayuda">{{ t('Every size of generic') }} <b>{{ tx(p.codigo_generico || '—') }}</b> {{ t('(style-color) shares the technical sheet and the HS code. Prepacks are not classified: they are built with these solids and take their code.') }}</p>
            <button v-if="p.codigo_generico && puede('catalogos.crear')" class="btn btn-chico" @click="agregarTallas = true"><Icono nombre="mas" :tam="14" />{{ t('Add sizes') }}</button>
          </div>
          <div class="tabla-marco mt-chico">
            <table class="tabla" v-tarjetas>
              <thead><tr><th>{{ t('Item code') }}</th><th>{{ t('Size code') }}</th><th>{{ t('Supplier SKU') }}</th><th>UPC</th><th>{{ t('Size') }}</th><th>{{ t('Unit') }}</th><th>{{ t('Description') }}</th><th>{{ t('Status') }}</th></tr></thead>
              <tbody>
                <tr v-for="a in p.articulos" :key="a.id">
                  <td class="fuerte">{{ tx(a.sku) }}<span v-if="a.tipo === 'PREPACK'" class="etiqueta acento">{{ t('Prepack') }}</span></td>
                  <td class="apagado">{{ tx(a.sku.length === 11 ? a.sku.slice(8) : '—') }}</td>
                  <td>{{ tx(a.sku_proveedor || '—') }}</td>
                  <td>{{ tx(a.upc || '—') }}</td>
                  <td>{{ tx(a.talla || '—') }}</td>
                  <td>{{ tx(a.unidad) }}</td>
                  <td class="apagado">{{ tx(p.descripcion_comercial ? `${p.descripcion_comercial}, ${a.tipo === 'PREPACK' ? t('prepack') : t('size')} ${a.talla}` : a.descripcion) }}</td>
                  <td><span v-if="a.activo" class="etiqueta ok">{{ t('Active') }}</span><span v-else class="etiqueta">{{ t('Inactive') }}</span></td>
                </tr>
              </tbody>
            </table>
          </div>
          <div v-for="x in p.prepacks" :key="x.id" class="panel mt">
            <div class="panel-cabeza"><div><h2>{{ t('Prepack {0}', [x.codigo]) }}</h2><p>{{ t('{0} · {1} per carton', [x.descripcion, x.total]) }}<template v-if="x.sku"> {{ t('· SKU {0}', [x.sku]) }}</template></p></div></div>
            <div class="chips"><span v-for="c in x.componentes" :key="c.sku" class="etiqueta">{{ tx(c.talla) }} × {{ tx(c.cantidad) }}</span></div>
          </div>
        </div>

        <!-- Historial -->
        <div v-else class="panel">
          <ol class="linea-hist">
            <li v-for="(h, i) in p.historial" :key="i">
              <b>{{ tx(ACCION[h.accion] || h.accion) }}</b>
              <span class="apagado"> · {{ tx(h.usuario || t('System')) }} · {{ fmtFechaHora(h.fecha) }}</span>
              <div v-if="detalleHist(h) || h.motivo" class="sub">{{ tx(detalleHist(h)) }}<template v-if="h.motivo"> · {{ tx(h.motivo) }}</template></div>
            </li>
            <li v-if="!p.historial.length" class="apagado">{{ t('No changes recorded yet.') }}</li>
          </ol>
        </div>
      </div>

      <!-- Panel de clasificación -->
      <aside class="clasif" :aria-label="t('Classification')">
        <section class="panel">
          <div class="eyebrow">{{ t('Tariff classification') }}</div>
          <div class="sello" :class="aprobado ? 'aprobado' : codigo6.length === 6 ? 'sugerido' : 'vacio'">
            <span class="codigo-grande">{{ tx(codigo6.length === 6 ? fmtCode(codigo6) : '——.——') }}</span>
            <span class="sello-texto">{{ tx(aprobado ? t('Approved') : codigo6.length === 6 ? (codOficial ? t('Chosen by you') : t('Suggested')) : t('No code yet')) }}</span>
          </div>
          <p v-if="codigo6.length === 6 && descHs6" class="desc-sac">{{ tx(descHs6) }}</p>

          <p v-if="!aprobado && oculta" class="ayuda">{{ t('The customs team assigns the code when it approves the sheet. Fill in what is missing below.') }}</p>
          <template v-if="!aprobado && r && !oculta">
            <div class="confianza" :title="tx(t('Confidence: {0}', [r.confianza]))">
              <span v-for="n in 3" :key="n" class="barra" :class="{ llena: n <= confNivel, ['n' + confNivel]: true }"></span>
              <span class="ayuda">{{ t('Legal confidence: {0} · {1}', [NIVEL_CONF[r.legal_confidence || r.confianza], FUENTES[fuente] || '']) }}</span>
            </div>
            <!-- El historial de la empresa es una señal aparte: ordena, nunca da certeza legal -->
            <p v-if="r.historical_confidence && r.historical_confidence !== 'none'" class="ayuda conf-hist">
              {{ t('Company history: {0} (it only orders the official candidates)', [NIVEL_CONF[r.historical_confidence]]) }}</p>
            <ul class="razones">
              <li v-for="(x, i) in (verRazones ? r.razones : r.razones.slice(0, 3))" :key="i">{{ tx(x) }}</li>
            </ul>
            <ul v-if="pistas.length" class="pistas">
              <li v-for="x in pistas" :key="x"><Icono nombre="info" :tam="13" />{{ tx(x) }}</li>
            </ul>
            <button v-if="r.razones.length > 3" type="button" class="btn-texto" @click="verRazones = !verRazones">{{ tx(verRazones ? t('Less') : t('Why ({0} steps)', [r.razones.length])) }}</button>
          </template>

          <div v-if="!aprobado && reglasAplicadas.length" class="bloque-clasif">
            <h3><Icono nombre="lista" :tam="15" />{{ t('Rules that decided') }}</h3>
            <ul class="reglas-ev">
              <li v-for="x in reglasAplicadas" :key="x.regla" :class="x.capa === 'LEGAL' ? 'legal' : ''">
                <span class="etiqueta" :class="x.capa === 'LEGAL' ? 'ok' : x.capa === 'PROPIA' ? 'acento' : ''">{{ tx(x.capa === 'LEGAL' ? t('Legal evidence') : x.capa === 'PROPIA' ? t('Company rule') : t('System rule')) }}</span>
                <b>{{ tx(x.regla) }}</b> <span class="apagado">{{ tx(x.efecto) }} · {{ t('priority {0}', [x.prioridad]) }} · {{ t('rev. {0}', [x.revision]) }}</span>
                <span v-if="x.foto?.efecto" class="sub">{{ tx(x.foto.efecto) }}</span>
              </li>
            </ul>
          </div>

          <div v-if="!aprobado && r && faltan.length" class="bloque-clasif">
            <h3><Icono nombre="alerta" :tam="15" />{{ t('To complete the sheet') }}</h3>
            <ul class="lista-simple"><li v-for="x in faltan" :key="x">{{ tx(x) }}</li></ul>
          </div>

          <div v-if="!aprobado && alertas.length" class="bloque-clasif">
            <h3><Icono nombre="info" :tam="15" />{{ t('Check') }}</h3>
            <ul class="alertas">
              <li v-for="a in alertas" :key="a.clave" :class="a.nivel">
                <span>{{ tx(a.msg) }}</span>
                <button v-if="a.nivel !== 'error' && puedeEditar" type="button" class="btn-texto" @click="revisada(a)">{{ t('Reviewed') }}</button>
              </li>
            </ul>
          </div>

          <div v-if="!aprobado && puedeAprobar && r" class="bloque-clasif">
            <h3>{{ t('Other codes') }}</h3>
            <ul class="alternativas">
              <li v-for="a in r.alternativas.slice(0, 4)" :key="a.codigo">
                <button type="button" class="enlace" @click="usarCodigo(a.codigo)">{{ fmtCode(a.codigo) }}</button>
                <span class="sub">{{ tx(a.cuando) }}</span>
              </li>
            </ul>
            <form class="fila-flex otro-codigo" @submit.prevent="aplicarOtro">
              <input v-model="otroCodigo" class="entrada" :placeholder="t('Another code, e.g. 6404.11')" :aria-label="t('Another HS code')" />
              <button class="btn btn-chico" type="submit">{{ t('Use') }}</button>
              <button v-if="codOficial" type="button" class="btn-texto" @click="codOficial = ''">{{ t('Back to suggested') }}</button>
            </form>
          </div>
        </section>

        <section v-if="codigo6.length === 6" class="panel soporte">
          <div class="panel-cabeza"><div><h2>{{ t('Classification support') }}</h2><p>{{ t('Official legal notes, classifier guidance and legal basis to check heading {0} before approving it.', [fmtCode(codigo6.slice(0, 4))]) }}</p></div></div>
          <div class="pestanas-pildora" role="tablist">
            <button v-for="[k, txt, n] in [['legales', t('Official legal notes'), notasLegales.length], ['explicativas', t('Guidance (not legal text)'), notasExplicativas.length], ['base', t('Legal basis'), basesLegales.length]]" :key="k"
                    type="button" role="tab" class="pildora" :aria-selected="soporte === k" @click="soporte = k">{{ txt }} <span class="cuenta">{{ n }}</span></button>
          </div>
          <ul v-if="soporte !== 'base'" class="notas-sac">
            <li v-for="n in (verNotas ? notasVista : notasVista.slice(0, 3))" :key="n.id">
              <b>{{ tx(n.ambito === 'explicativa' ? t('Explanatory note, heading {0}', [fmtCode(n.codigo)]) : n.codigo === 'RGI' ? t('General rule {0}', [n.numero]) : n.ambito === 'seccion' ? t('Section {0}, note {1}', [n.codigo, n.numero]) : n.ambito === 'complementaria' ? t('Chapter {0}, Central American note {1}', [n.codigo, n.numero.replace('NCC ', '')]) : t('Chapter {0}, note {1}', [n.codigo, n.numero])) }}</b>
              <span class="etiqueta" :class="n.oficial ? 'ok' : 'aviso'">{{ n.oficial ? t('Official text') : n.tipo_fuente === 'CLASSIFIER_GUIDANCE' ? t('Classifier summary') : t('Internal guidance') }}</span>
              <span>{{ tx(n.texto) }}</span>
            </li>
            <li v-if="!notasVista.length" class="apagado">{{ soporte === 'explicativas' ? t('No guidance for this heading. Internal guidance and classifier summaries are added in Tariff schedule → Notes.') : t('No legal notes loaded for this chapter.') }}</li>
          </ul>
          <button v-if="soporte !== 'base' && notasVista.length > 3" type="button" class="btn-texto" @click="verNotas = !verNotas">{{ tx(verNotas ? t('Show fewer') : t('See all {0} notes', [notasVista.length])) }}</button>
          <div v-if="soporte === 'base'" class="bases-legales">
            <p v-for="b in basesLegales" :key="b.texto"><b>{{ tx(b.isos.join(', ')) }}</b> · {{ tx(b.texto) }}</p>
            <p v-if="!basesLegales.length" class="apagado">{{ t('No legal basis registered for the destination countries. Add it in Tariff schedule → Countries.') }}</p>
          </div>
        </section>

        <section v-if="!oculta" class="panel">
          <div class="panel-cabeza"><div><h2>{{ t('By destination') }}</h2><p>{{ t('{0} of {1} national codes complete', [paisesOk, paises.length]) }}</p></div></div>
          <table class="tabla paises" v-tarjetas>
            <tbody>
              <tr v-for="x in paises" :key="x.iso">
                <td class="fuerte">{{ tx(x.iso) }}</td>
                <td>
                  <template v-if="!aprobado && puedeAprobar">
                    <input class="entrada entrada-pais" :class="{ invalida: errPais[x.iso], tentativo: !PAIS_LISTO.includes(x.estado) && !x.manual }"
                           :value="x.codigo ? fmtPais(x.codigo, x.digitos) : ''" :placeholder="t('{0}… ({1} digits)', [fmtCode(codigo6) || t('Code'), x.digitos])"
                           :list="x.opciones?.length ? `ops-${x.iso}` : undefined" inputmode="numeric" :maxlength="Math.max(...(x.longitudes?.length ? x.longitudes : [x.digitos])) + 8"
                           :aria-label="t('National code for {0}', [x.nombre])" :title="t('Type the {0}-digit code; it applies when you leave the field', [x.digitos])"
                           @blur="escribirPais(x, $event.target)" @keydown.enter.prevent="$event.target.blur()" />
                    <datalist v-if="x.opciones?.length" :id="`ops-${x.iso}`">
                      <option v-for="o in x.opciones" :key="o.codigo" :value="fmtPais(o.codigo, x.digitos)">{{ tx(o.cond_txt || o.descripcion) }}</option>
                    </datalist>
                    <span v-if="errPais[x.iso]" class="sub texto-error">{{ tx(errPais[x.iso]) }}</span>
                    <span v-else-if="x.manual" class="sub">{{ t('Set by hand ·') }} <button type="button" class="btn-texto" @click="quitarManual(x.iso)">{{ t('use automatic') }}</button> · <button type="button" class="btn-texto" @click="abrirEnsenar(x)">{{ t('remember for similar') }}</button></span>
                    <span v-else-if="x.estado === 'historial'" class="sub">{{ EST_PAIS.historial }} ·
                      <button type="button" class="btn-texto" @click="codigoPais(x.iso, x.codigo)">{{ t('confirm') }}</button></span>
                    <span v-else-if="!PAIS_LISTO.includes(x.estado)" class="sub">{{ tx(x.error || (x.estado === 'elegir' ? t('Choose one of the listed codes or type it') : EST_PAIS[x.estado])) }}</span>
                  </template>
                  <template v-else-if="aprobado && puedeAprobar && !PAIS_LISTO.includes(x.estado)">
                    <span v-if="x.codigo" class="codigo-sac tentativo">{{ tx(fmtPais(x.codigo, x.digitos)) }}</span>
                    <Seleccion v-if="x.opciones?.length" class="entrada" :aria-label="t('Code for {0}', [x.nombre])" @change="confirmarPais(x, $event)">
                      <option value="">{{ t('Choose…') }}</option>
                      <option v-for="o in x.opciones" :key="o.codigo" :value="o.codigo">{{ fmtPais(o.codigo, x.digitos) }} · {{ tx(o.cond_txt || o.descripcion) }}</option>
                    </Seleccion>
                    <span class="sub">{{ tx(x.estado === 'historial' ? EST_PAIS.historial : t('Not confirmed (reference only: documents use the 6-digit subheading)')) }} ·
                      <button v-if="x.codigo" type="button" class="btn-texto" @click="confirmarPais(x, x.codigo)">{{ t('confirm') }}</button>
                      <button v-else-if="!x.opciones?.length" type="button" class="btn-texto" @click="cargarOpcionesPais(x)">{{ t('choose') }}</button></span>
                  </template>
                  <template v-else>
                    <Seleccion v-if="x.estado === 'elegir' && x.opciones?.length && puedeEditar" class="entrada" :aria-label="t('Code for {0}', [x.nombre])" @change="codigoPais(x.iso, $event)">
                      <option value="">{{ t('Choose…') }}</option>
                      <option v-for="o in x.opciones" :key="o.codigo" :value="o.codigo">{{ fmtPais(o.codigo, x.digitos) }} · {{ tx(o.cond_txt || o.descripcion) }}</option>
                    </Seleccion>
                    <template v-else>
                      <span class="codigo-sac" :class="{ tentativo: !PAIS_LISTO.includes(x.estado) }">{{ tx(x.codigo ? fmtPais(x.codigo, x.digitos) : '—') }}</span>
                      <span v-if="x.manual" class="etiqueta acento" :title="t('Set by hand')">{{ t('manual') }}</span>
                    </template>
                    <span v-if="!PAIS_LISTO.includes(x.estado) && x.estado !== 'elegir'" class="sub">{{ tx(x.error || EST_PAIS[x.estado]) }}</span>
                    <span v-else-if="x.estado === 'historial'" class="sub">{{ EST_PAIS.historial }}</span>
                  </template>
                </td>
                <td class="num apagado">{{ tx(x.dai !== '' && x.dai != null ? `${x.dai}%` : '') }}</td>
              </tr>
            </tbody>
          </table>
        </section>

        <section v-if="!aprobado && r?.parecidos?.length" class="panel">
          <div class="panel-cabeza"><div><h2>{{ t('Similar products') }}</h2><p>{{ t('Already classified') }}</p></div></div>
          <ul class="parecidos">
            <li v-for="x in r.parecidos.slice(0, 3)" :key="x.id">
              <router-link :to="`/productos/${x.id}`"><span v-if="x.generico" class="codigo">{{ tx(x.generico) }}</span> {{ tx(x.estilo) }} {{ tx(x.color) }}</router-link>
              <span class="codigo-sac">{{ tx(x.codigo_txt) }}</span>
              <span class="sub">{{ tx(x.descripcion) }}</span>
            </li>
          </ul>
        </section>

        <section v-if="(opciones.especialista && puedeAprobar && !aprobado) || p.opinion_ia" class="panel">
          <div class="panel-cabeza"><div><h2>{{ t('Specialist opinion') }}</h2><p>{{ t('A second opinion by Claude. It never approves anything.') }}</p></div>
            <button v-if="opciones.especialista && puedeAprobar && !aprobado" class="btn btn-chico" :disabled="ocupado" @click="consultar"><Icono nombre="varita" />{{ tx(p.opinion_ia ? t('Ask again') : t('Ask')) }}</button>
          </div>
          <div v-if="p.opinion_ia" class="opinion">
            <p><span class="codigo-sac">{{ fmtCode(p.opinion_ia.codigo) }}</span> <span class="etiqueta">{{ tx(p.opinion_ia.confianza) }}</span>
              <button v-if="!aprobado && puedeAprobar && p.opinion_ia.codigo" type="button" class="btn-texto" @click="usarCodigo(p.opinion_ia.codigo)">{{ t('Use this code') }}</button></p>
            <p class="sub">{{ tx(p.opinion_ia.razonamiento) }}</p>
            <ul v-if="p.opinion_ia.correcciones?.length" class="lista-simple">
              <li v-for="c in p.opinion_ia.correcciones" :key="c.campo">{{ tx(nombreCampo(c)) }} → <b>{{ tx(valorLegible(c)) }}</b> <span class="apagado">{{ tx(c.motivo) }}</span>
                <button v-if="puedeEditar" type="button" class="btn-texto" @click="aplicarCorreccion(c)">{{ t('Apply') }}</button></li>
            </ul>
            <ul v-if="p.opinion_ia.preguntas_proveedor?.length" class="lista-simple apagado">
              <li v-for="q in p.opinion_ia.preguntas_proveedor" :key="q">{{ tx(q) }}</li>
            </ul>
          </div>
        </section>

        <div v-if="!aprobado && puedeAprobar" class="acciones-clasif">
          <button class="btn btn-primario btn-grande" :disabled="ocupado || calculando || !r || codigo6.length < 6 || !completa || errores.length > 0 || !!bloqueoAprobar"
                  :title="tx(bloqueoAprobar || (!completa ? t('Complete the technical sheet first') : errores.length ? t('Fix the errors first') : ''))" @click="aprobar">
            <Icono nombre="check" />{{ t('Approve {0}', [codigo]) }}
          </button>
          <p v-if="motivoNoAprobar" class="ayuda bloqueo-motivo"><Icono nombre="info" :tam="14" />{{ tx(motivoNoAprobar) }}</p>
          <button class="btn" :disabled="ocupado" @click="modal = { tipo: 'devolver', texto: p.observaciones || (faltan.length ? t('Please complete: {0}.', [faltan.join(', ')]) : '') }">{{ t('Return to supplier') }}</button>
        </div>
        <p v-else-if="!aprobado && puedeEditar" class="ayuda acciones-clasif">
          <template v-if="!puedeEnviar">{{ t('Sent to review.') }}</template>
          <template v-else-if="completa">{{ t('Complete. Send it to review when it is ready; until then it stays as a draft.') }}</template>
          <template v-else>{{ t('Complete the required fields, then send it to review.') }}</template>
        </p>
      </aside>
    </div>

    <!-- Ventanas -->
    <GenericoModal v-if="agregarTallas" :generico="p.codigo_generico" @cerrar="agregarTallas = false" @listo="agregarTallas = false; cargar()" />
    <Modal v-if="modal?.tipo === 'devolver'" :titulo="t('Return to the supplier')" @cerrar="modal = null">
      <label class="campo"><span class="req">{{ t('What should be corrected') }}</span><textarea v-model="modal.texto" class="entrada" rows="4" maxlength="2000"></textarea></label>
      <template #pie>
        <button class="btn" @click="modal = null">{{ t('Cancel') }}</button>
        <button class="btn btn-primario" :disabled="ocupado || !modal.texto.trim()" @click="devolver">{{ t('Return') }}</button>
      </template>
    </Modal>
    <Modal v-if="modal?.tipo === 'version'" :titulo="t('New version of the sheet')" @cerrar="modal = null">
      <p class="ayuda">{{ t('The approved version is kept in the history with its code. The new one starts as a draft and needs approval again.') }}</p>
      <div class="rejilla-campos mt-chico">
        <label class="campo ancho-2"><span class="req">{{ t('Reason for the change') }}</span><input v-model="modal.texto" class="entrada" maxlength="300" :placeholder="t('E.g. new outsole material')" /></label>
        <label class="campo"><span>{{ t('Valid from') }}</span><CampoFecha v-model="modal.desde" /></label>
      </div>
      <template #pie>
        <button class="btn" @click="modal = null">{{ t('Cancel') }}</button>
        <button class="btn btn-primario" :disabled="ocupado || !modal.texto.trim()" @click="nuevaVersion">{{ t('Open new version') }}</button>
      </template>
    </Modal>
    <Modal v-if="modal?.tipo === 'ensenar'" :titulo="t('Remember {0} for {1}', [fmtPais(modal.pais.codigo, modal.pais.digitos), modal.pais.nombre])" ancho="480px" @cerrar="modal = null">
      <p class="ayuda">{{ t('Products with this subheading that match the checked data will get this code automatically.') }}</p>
      <div class="lista-cond">
        <label v-for="c in modal.conds" :key="c.k" class="check"><input v-model="c.usar" type="checkbox" /><span>{{ tx(c.l) }}: <b>{{ tx(textoHecho(c.k, c.v)) }}</b></span></label>
        <p v-if="!modal.conds.length" class="apagado">{{ t('No distinguishing data: it will apply to the whole subheading.') }}</p>
      </div>
      <template #pie>
        <button class="btn" @click="modal = null">{{ t('Only this product') }}</button>
        <button class="btn btn-primario" :disabled="ocupado" @click="ensenar">{{ t('Remember') }}</button>
      </template>
    </Modal>
  </div>
  <p v-else class="vacio">{{ t('Loading…') }}</p>
</template>

<style scoped>
.pasos-producto { margin: 4px 0 16px; }
.bases-legales { margin-top: 10px; padding-top: 8px; border-top: 1px solid var(--linea); }
.bases-legales p { margin: 4px 0 0; font-size: 0.78rem; color: var(--tinta-3); line-height: 1.35; }
.bases-legales b { color: var(--tinta-2); }
.version-vista { border-top: 1px solid var(--linea); padding-top: 12px; }
.version-vista h3 { font-size: 1rem; margin: 0; }
.version-vista h4 { font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.04em; color: var(--tinta-3); margin-bottom: 6px; }
.rejilla-dl { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 8px 16px; }
.rejilla-dl .par { display: flex; flex-direction: column; gap: 1px; min-width: 0; }
.rejilla-dl .par span { font-size: 0.76rem; color: var(--tinta-3); }
.rejilla-dl .par b { font-weight: 560; font-size: 0.9rem; overflow-wrap: anywhere; }
.producto-layout { display: grid; grid-template-columns: minmax(0, 1fr) 380px; gap: 20px; align-items: start; margin-top: 4px; }
.producto-principal .pestanas { margin-top: 4px; }
.clasif { display: flex; flex-direction: column; gap: 14px; }
.clasif .panel + .panel { margin-top: 0; }
@media (max-width: 1100px) {
  .producto-layout { grid-template-columns: minmax(0, 1fr); }
  .clasif { position: static; max-height: none; overflow: visible; }
}
.ficha { border: 0; padding: 0; margin: 0; min-width: 0; }
.ficha .panel + .panel { margin-top: 14px; }
.ficha:disabled .segmento:not([aria-pressed='true']) { opacity: 0.55; }
.ancho-2 { grid-column: span 2; }
@media (max-width: 600px) { .ancho-2 { grid-column: auto; } }
.composicion { grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); }
.reglas-ev { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; font-size: 0.82rem; }
.reglas-ev li { display: flex; flex-wrap: wrap; gap: 4px 6px; align-items: baseline; }
.reglas-ev li .sub { flex-basis: 100%; color: var(--tinta-3); font-size: 0.78rem; }
.reglas-ev li.legal b { color: var(--ok); }
.atributos { display: flex; flex-direction: column; gap: 14px; }
.atributo { display: flex; flex-direction: column; gap: 6px; }
.atributo-nombre { font-weight: 580; font-size: 0.86rem; color: var(--tinta-2); }
.atributo.definido { flex-direction: row; justify-content: space-between; flex-wrap: wrap; gap: 6px; font-size: 0.88rem; padding: 8px 10px; background: var(--superficie-2); border-radius: var(--radio); }
.atributo.check { flex-direction: row; align-items: flex-start; gap: 8px; font-size: 0.9rem; }
.atributo select { max-width: 420px; }
.foto-cabeza { width: 52px; height: 52px; border-radius: 10px; border: 1px solid var(--linea); background: var(--superficie-2); display: grid; place-items: center; overflow: hidden; color: var(--tinta-3); flex: none; }
.foto-cabeza img { width: 100%; height: 100%; object-fit: cover; }
.fotos { display: flex; gap: 10px; flex-wrap: wrap; }
.foto { position: relative; margin: 0; width: 120px; height: 120px; border-radius: 10px; overflow: hidden; border: 1px solid var(--linea); }
.foto img { width: 100%; height: 100%; object-fit: cover; }
.foto .btn-icono { position: absolute; top: 4px; inset-inline-end: 4px; background: var(--superficie); }
.desc-aduana { font-size: 0.9rem; letter-spacing: 0.01em; background: var(--superficie-2); border: 1px dashed var(--linea); border-radius: var(--radio); padding: 10px 12px; }
.sello { display: flex; align-items: baseline; justify-content: space-between; gap: 6px 10px; flex-wrap: wrap; margin: 6px 0 4px; }
.codigo-grande { font-stretch: 125%; font-weight: 780; font-size: 2rem; line-height: 1.1; font-variant-numeric: tabular-nums; }
.sello.vacio .codigo-grande { color: var(--tinta-3); }
.sello-texto { font-size: 0.78rem; font-weight: 650; text-transform: uppercase; letter-spacing: 0.05em; padding: 3px 8px; border-radius: 6px; background: var(--linea-suave); color: var(--tinta-2); }
.sello.aprobado .sello-texto { background: var(--ok-fondo); color: var(--ok); }
.sello.sugerido .sello-texto { background: var(--info-fondo); color: var(--info); }
.desc-sac { font-size: 0.86rem; color: var(--tinta-2); }
.confianza { display: flex; align-items: center; gap: 4px; margin: 12px 0 6px; }
.confianza .barra { width: 22px; height: 6px; border-radius: 3px; background: var(--linea); }
.confianza .barra.llena.n3 { background: var(--ok); }
.confianza .barra.llena.n2 { background: #d69e2e; }
.confianza .barra.llena.n1 { background: var(--error); }
.confianza .ayuda { margin-inline-start: 6px; }
.razones { margin: 6px 0 2px; padding-inline-start: 18px; font-size: 0.86rem; color: var(--tinta-2); display: flex; flex-direction: column; gap: 3px; }
.pistas { list-style: none; margin: 8px 0 0; padding: 0; font-size: 0.82rem; color: var(--aviso); display: flex; flex-direction: column; gap: 4px; }
.pistas li { display: flex; gap: 6px; align-items: flex-start; }
.pistas svg { margin-top: 2px; flex: none; }
.bloque-clasif { border-top: 1px solid var(--linea-suave); margin-top: 12px; padding-top: 10px; }
.bloque-clasif h3 { font-size: 0.86rem; display: flex; align-items: center; gap: 6px; margin-bottom: 6px; }
.lista-simple { margin: 0; padding-inline-start: 18px; font-size: 0.86rem; display: flex; flex-direction: column; gap: 3px; }
.alertas { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
.alertas li { font-size: 0.84rem; padding: 7px 9px; border-radius: 7px; background: var(--info-fondo); color: var(--info-texto); display: flex; gap: 8px; justify-content: space-between; align-items: flex-start; }
.alertas li.aviso { background: var(--aviso-fondo); color: var(--aviso); }
.alertas li.error { background: var(--error-fondo); color: var(--error); }
.alertas .btn-texto { color: inherit; font-size: 0.8rem; white-space: nowrap; }
.alternativas { list-style: none; margin: 0 0 8px; padding: 0; display: flex; flex-direction: column; gap: 5px; font-size: 0.86rem; }
.otro-codigo { gap: 6px; flex-wrap: nowrap; }
.otro-codigo .entrada { flex: 1; min-width: 0; }
.paises td { padding-top: 7px; padding-bottom: 7px; }
.paises select { max-width: 100%; font-size: 0.84rem; }
.entrada-pais { width: 100%; min-width: 0; font-family: var(--mono); font-weight: 600; padding: 6px 8px; }
.entrada-pais.tentativo { border-style: dashed; }
.entrada-pais.invalida { border-color: var(--error); box-shadow: 0 0 0 3px var(--error-fondo); }
.paises .sub .btn-texto { font-size: inherit; padding: 0; }
.paises { table-layout: fixed; width: 100%; }
.paises td { overflow-wrap: anywhere; }
.paises td:first-child { width: 44px; }
.paises td:last-child { width: 56px; }
.paises .sub { white-space: normal; display: block; }
.notas-sac { list-style: none; margin: 0 0 6px; padding: 0; display: flex; flex-direction: column; gap: 10px; font-size: 0.84rem; line-height: 1.45; }
.notas-sac li { display: flex; flex-direction: column; gap: 2px; padding-inline-start: 10px; border-inline-start: 3px solid var(--acento-claro); }
.notas-sac b { font-size: 0.78rem; color: var(--acento-texto); }
.notas-sac li .etiqueta { align-self: flex-start; }
.conf-hist { margin: -4px 0 8px; }
.notas-sac span { color: var(--tinta-2); }
.parecidos { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 8px; font-size: 0.88rem; }
.parecidos .codigo-sac { margin-inline-start: 6px; }
.opinion p + p { margin-top: 6px; }
.acciones-clasif { display: flex; flex-direction: column; gap: 8px; }
.acciones-clasif .btn { justify-content: center; }
.linea-hist { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 12px; }
.linea-hist li { padding-inline-start: 14px; border-inline-start: 2px solid var(--linea); }
.lista-cond { display: flex; flex-direction: column; gap: 8px; margin-top: 10px; }
</style>
