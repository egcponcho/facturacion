<script setup>
import { t, tx } from '@/i18n/index.js'
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router'
import { api } from '@/nucleo/api'
import { pasoCantidad } from '@/nucleo/unidades.js'
import { cantTxt, fmtFecha, fmtMoneda, fmtNum, porUnidadTxt, unidadTxt } from '@/nucleo/utils'
import { horaTexto } from '@/stores/preferencias'
import { camposPropios, valorPropio } from '@/stores/sesion'
import { avisar, errorApi } from '@/stores/ui'
import Asistente from '@/componentes/Asistente.vue'
import Icono from '@/componentes/Icono.vue'
import Interruptor from '@/componentes/Interruptor.vue'
import Seleccion from '@/componentes/Seleccion.vue'
import SelectBusqueda from '@/componentes/SelectBusqueda.vue'

// Asistente de la orden de compra (docs/FLUJOS.md §1): seis pasos con solo los
// datos de cada uno. El primer «Siguiente» crea el borrador; desde ahí todo se
// guarda solo (y al cambiar de paso), así se puede salir y seguir después.
// Cada paso se valida en el servidor con las mismas reglas que el envío.
const props = defineProps({ id: { type: String, default: '' } })
const route = useRoute()
const router = useRouter()

const PASOS = [
  { clave: 'general', titulo: t('General data') },
  { clave: 'articulos', titulo: t('Items and quantities') },
  { clave: 'condiciones', titulo: t('Commercial terms') },
  { clave: 'logistica', titulo: t('Logistics and dates') },
  { clave: 'documentacion', titulo: t('Documentation and extras') },
  { clave: 'revision', titulo: t('Review and send') },
]
// Lo que el flujo siempre exige y lo que la empresa puede volver obligatorio
// (Configuración → Empresa → Datos obligatorios de la OC)
const SIEMPRE = new Set(['proveedor', 'oc', 'sociedad', 'moneda', 'fecha_xf'])
const OBLIGABLE = { fecha_oc: 'fecha', incoterm: 'incoterm', condicion_pago: 'condicion_pago', centro: 'centro', centro_destino: 'centro_destino',
  puerto_despacho: 'puerto_despacho', pais_origen: 'pais_origen', fecha_tienda: 'fecha_tienda' }
// Dónde se muestra el error de cada dato
const CAMPOS_PASO = {
  general: ['proveedor', 'oc', 'sociedad', 'fecha_oc'],
  articulos: ['lineas'],
  condiciones: ['moneda', 'incoterm', 'condicion_pago'],
  logistica: ['fecha_xf', 'fecha_tienda', 'centro', 'centro_destino', 'puerto_despacho', 'pais_origen', 'pais_procedencia'],
  documentacion: ['notas'],
}

const op = ref(null)
const cargando = ref(true)
const ocId = ref(props.id ? Number(props.id) : null)
const oc = ref(null) // número, estado y motivo de la OC guardada
const version = ref(null)
const actual = ref(0)
const CABECERA_VACIA = { proveedor: '', oc: '', sociedad: '', fecha_oc: '', moneda: '', incoterm: '', condicion_pago: '', centro: '', centro_destino: '',
  puerto_despacho: '', pais_origen: '', pais_procedencia: '', fecha_xf: '', fecha_tienda: '', notas: '' }
const cab = reactive({ ...CABECERA_VACIA, extra: {} })
const nuevaLinea = () => ({ codigo_sap: '', cantidad: '', unidad: '', precio: '', casepack: '', almacen: '', fecha_entrega: '' })
const lineas = ref([nuevaLinea()])
const errores = ref([])
const conErrores = reactive({}) // paso → cuántos errores tiene según el servidor
const intentados = reactive(new Set()) // pasos en los que ya se pidió avanzar: se revalidan al escribir
const ocupado = ref(false)
const guardandoAhora = ref(false)
const guardadoEn = ref(null)
const guardadoComo = ref('')
const infoArt = reactive({}) // sku → { valor, texto, unidad, tipo, sub, pais_origen }

const paso = computed(() => PASOS[actual.value])
const propios = computed(() => camposPropios('ordenes'))
const req = (c) => SIEMPRE.has(c) || (op.value?.obligatorios || []).includes(OBLIGABLE[c])
const texto = (v) => (v === null || v === undefined ? '' : String(v))

// ---- Opciones coherentes con el proveedor: sus sociedades y, de ellas, centros y almacenes
const proveedor = computed(() => op.value?.proveedores.find((p) => p.valor === cab.proveedor))
const sociedades = computed(() => (op.value?.sociedades || []).filter((x) => (proveedor.value?.sociedades || []).includes(x.valor)))
const permitida = (soc) => !soc || (cab.sociedad ? soc === cab.sociedad : (proveedor.value?.sociedades || []).includes(soc))
const centros = computed(() => (op.value?.centros || []).filter((c) => permitida(c.sociedad)))
const almacenes = computed(() => (op.value?.almacenes || []).filter((a) => permitida(a.sociedad)))
const opcionesArt = computed(() => Object.values(infoArt))
const esPrepack = (l) => infoArt[l.codigo_sap]?.tipo === 'PREPACK'
const unidadDe = (l) => l.unidad || infoArt[l.codigo_sap]?.unidad || ''
const textoDe = (lista, v) => (v ? (op.value?.[lista] || []).find((o) => o.valor === v)?.texto || v : '—')

watch(() => cab.proveedor, async (p, antes) => {
  if (antes && cab.sociedad && !(proveedor.value?.sociedades || []).includes(cab.sociedad)) cab.sociedad = ''
  if (!cab.sociedad && sociedades.value.length === 1) cab.sociedad = sociedades.value[0].valor
  await cargarArticulos(p)
})
watch(() => cab.sociedad, () => {
  for (const k of ['centro', 'centro_destino']) if (cab[k] && !centros.value.some((c) => c.valor === cab[k])) cab[k] = ''
  lineas.value.forEach((l) => { if (l.almacen && !almacenes.value.some((a) => a.valor === l.almacen)) l.almacen = '' })
})

async function cargarArticulos(prov) {
  if (!prov) return
  try {
    for (const a of await api.get('/ordenes/formulario/articulos', { proveedor: prov })) infoArt[a.valor] = a
    // Los artículos de las líneas que no vinieron en la primera página
    const faltan = [...new Set(lineas.value.map((l) => l.codigo_sap).filter((s) => s && !infoArt[s]))].slice(0, 40)
    for (const sku of faltan) {
      for (const a of await api.get('/ordenes/formulario/articulos', { proveedor: prov, q: sku })) infoArt[a.valor] = a
    }
  } catch (e) {
    errorApi(e)
  }
}
const buscarArticulos = (q) => api.get('/ordenes/formulario/articulos', { proveedor: cab.proveedor, q }).then((r) => {
  for (const a of r) infoArt[a.valor] = a
  return r
})
function elegirArticulo(l, a) {
  if (!a) return
  l.unidad = a.unidad || ''
  if (a.tipo === 'PREPACK') l.casepack = ''
}

// ---- Lo que se envía al servidor
const cabecera = () => ({ ...cab, extra: { ...cab.extra } })
const lineasEnvio = () => lineas.value.map((l) => ({ ...l, casepack: esPrepack(l) ? '' : l.casepack }))
const instantanea = () => JSON.stringify([cabecera(), lineasEnvio()])
const sucio = computed(() => instantanea() !== guardadoComo.value)

function aplicar(d) {
  oc.value = d.oc
  version.value = d.oc.version
  const b = d.borrador || { cabecera: {}, lineas: [] }
  for (const k of Object.keys(CABECERA_VACIA)) cab[k] = texto(b.cabecera?.[k])
  cab.extra = { ...(b.cabecera?.extra || {}) }
  lineas.value = (b.lineas || []).map((l) => ({ ...nuevaLinea(), ...Object.fromEntries(Object.entries(l).map(([k, v]) => [k, texto(v)])) }))
  if (!lineas.value.length) lineas.value = [nuevaLinea()]
  marcarPasos(d.pasos)
  guardadoComo.value = instantanea()
}
function marcarPasos(pasos) {
  for (const p of pasos || []) conErrores[p.clave] = p.errores.length
}

async function cargarOC() {
  const d = await api.get(`/ordenes/${ocId.value}`)
  if (!d.puede.editar) {
    router.replace(`/ordenes/${ocId.value}`)
    return
  }
  aplicar(d)
  // Sigue donde quedó: el paso pedido o el primero incompleto
  const pedido = PASOS.findIndex((p) => p.clave === route.query.paso)
  const pendiente = (d.pasos || []).findIndex((p) => p.errores.length)
  actual.value = pedido >= 0 ? pedido : pendiente >= 0 ? pendiente : PASOS.length - 1
  if (paso.value.clave === 'revision') await revisar()
}

onMounted(async () => {
  window.addEventListener('beforeunload', alSalir)
  try {
    op.value = await api.get('/ordenes/formulario')
    if (ocId.value) await cargarOC()
    else {
      if (op.value.proveedores.length === 1) cab.proveedor = op.value.proveedores[0].valor
      else if (route.query.proveedor) cab.proveedor = String(route.query.proveedor)
      cab.moneda = op.value.moneda_base || ''
      guardadoComo.value = instantanea()
    }
  } catch (e) {
    errorApi(e)
  } finally {
    cargando.value = false
  }
})
onBeforeUnmount(() => {
  window.removeEventListener('beforeunload', alSalir)
  clearTimeout(reloj)
  clearTimeout(relojValidar)
})
// Abierta desde la búsqueda global con otra OC: se carga esa
watch(() => props.id, async (id) => {
  if (id && Number(id) !== ocId.value) {
    ocId.value = Number(id)
    intentados.clear()
    errores.value = []
    await cargarOC()
  }
})

// ---- Guardado del borrador
let reloj = null
let enCurso = null
async function guardar() {
  if (!ocId.value) return crearBorrador()
  if (enCurso) await enCurso
  if (!sucio.value) return true
  const foto = instantanea()
  guardandoAhora.value = true
  enCurso = api.patch(`/ordenes/${ocId.value}`, { version: version.value, cabecera: cabecera(), lineas: lineasEnvio() })
  try {
    const d = await enCurso
    oc.value = d.oc
    version.value = d.oc.version
    marcarPasos(d.pasos)
    guardadoComo.value = foto
    guardadoEn.value = new Date()
    return true
  } catch (e) {
    if (e.detalle?.length) errores.value = e.detalle
    errorApi(e)
    return false
  } finally {
    enCurso = null
    guardandoAhora.value = false
  }
}
async function crearBorrador() {
  const errs = await validar('general')
  if (errs.some((e) => ['proveedor', 'oc'].includes(e.campo))) {
    errores.value = errs
    intentados.add('general')
    enfocarError()
    return false
  }
  const foto = instantanea()
  guardandoAhora.value = true
  try {
    const d = await api.post('/ordenes/borrador', { cabecera: cabecera() })
    ocId.value = d.oc.id
    oc.value = d.oc
    version.value = d.oc.version
    marcarPasos(d.pasos)
    guardadoComo.value = foto
    guardadoEn.value = new Date()
    // La dirección cambia sin volver a abrir la pantalla (misma vista)
    await router.replace({ path: `/ordenes/${d.oc.id}/editar`, query: { paso: paso.value.clave } })
    return true
  } catch (e) {
    if (e.detalle?.length) errores.value = e.detalle
    errorApi(e)
    return false
  } finally {
    guardandoAhora.value = false
  }
}
// Guardado automático unos segundos después del último cambio
watch(instantanea, () => {
  if (cargando.value) return
  if (ocId.value && sucio.value) {
    clearTimeout(reloj)
    reloj = setTimeout(guardar, 2500)
  }
  if (intentados.has(paso.value.clave)) revalidar()
})
const guardado = computed(() => {
  if (guardandoAhora.value) return t('Saving…')
  if (!ocId.value) return t('Not saved yet')
  if (sucio.value) return t('Unsaved changes')
  return guardadoEn.value ? t('Draft saved at {0}', [horaTexto(guardadoEn.value)]) : t('Draft saved')
})
function alSalir(e) {
  if (sucio.value) {
    e.preventDefault()
    e.returnValue = ''
  }
}
onBeforeRouteLeave(async (to) => {
  if (to.path.startsWith(`/ordenes/${ocId.value}/editar`)) return true
  clearTimeout(reloj)
  if (!sucio.value) return true
  if (ocId.value) return (await guardar()) || window.confirm(t('The last changes could not be saved. Leave anyway?'))
  return window.confirm(t('The purchase order has not been saved. Leave and discard it?'))
})

// ---- Validación en el servidor, campo por campo
async function validar(clave = paso.value.clave) {
  try {
    const r = await api.post('/ordenes/validar', { paso: clave, cabecera: cabecera(), lineas: lineasEnvio() }, { params: { oc_id: ocId.value || undefined } })
    if (clave !== 'revision') conErrores[clave] = r.errores.length
    return r.errores
  } catch (e) {
    errorApi(e)
    return [{ campo: '', mensaje: e.message }]
  }
}
let relojValidar = null
function revalidar() {
  clearTimeout(relojValidar)
  relojValidar = setTimeout(async () => {
    const clave = paso.value.clave
    const errs = await validar(clave)
    if (paso.value.clave === clave) errores.value = errs
  }, 500)
}
const msjs = (campo) => errores.value.filter((e) => e.campo === campo).map((e) => e.mensaje)
const msjsLinea = (i, ...campos) => errores.value.filter((e) => campos.some((c) => e.campo === `lineas.${i}.${c}`) || (!campos.length && e.campo === `lineas.${i}`)).map((e) => e.mensaje)
function colocado(c) {
  const p = paso.value.clave
  if ((CAMPOS_PASO[p] || []).includes(c)) return true
  const m = /^lineas\.\d+\.(\w+)$/.exec(c || '')
  if (m) return (p === 'articulos' && ['codigo_sap', 'cantidad', 'unidad'].includes(m[1])) || (p === 'condiciones' && m[1] === 'precio')
  if (String(c).startsWith('extra.')) return p === 'documentacion' && propios.value.some((x) => `extra.${x.clave}` === c)
  return false
}
const sueltos = computed(() => (paso.value.clave === 'revision' ? [] : errores.value.filter((e) => !colocado(e.campo)).map((e) => e.mensaje)))
function enfocarError() {
  nextTick(() => document.querySelector('.asistente .con-error :is(input, textarea, button.sb-boton)')?.focus())
}

// ---- Navegación
const pasosVista = computed(() => PASOS.map((p, i) => ({
  ...p,
  errores: p.clave !== 'revision' && intentados.has(p.clave) ? conErrores[p.clave] || 0 : 0,
  completo: p.clave !== 'revision' && ocId.value && conErrores[p.clave] === 0,
  bloqueado: !ocId.value && i > 0, // sin borrador, solo el primer paso
})))
async function ir(i) {
  if (i === actual.value || i < 0 || i >= PASOS.length) return
  if (!ocId.value && i > 0) return
  ocupado.value = true
  try {
    clearTimeout(reloj)
    if (sucio.value && !(await guardar())) return
    actual.value = i
    errores.value = []
    router.replace({ query: { ...route.query, paso: PASOS[i].clave } })
    if (PASOS[i].clave === 'revision') await revisar()
    else if (intentados.has(PASOS[i].clave)) errores.value = await validar()
    window.scrollTo({ top: 0 })
  } finally {
    ocupado.value = false
  }
}
async function siguiente() {
  ocupado.value = true
  try {
    const clave = paso.value.clave
    intentados.add(clave)
    // «Siguiente» exige el paso completo; «Guardar borrador» guarda lo que haya
    const errs = await validar(clave)
    if (errs.length) {
      errores.value = errs
      enfocarError()
      return
    }
    if (!ocId.value && !(await crearBorrador())) return
  } finally {
    ocupado.value = false
  }
  await ir(actual.value + 1)
}
async function revisar() {
  for (const p of PASOS) if (p.clave !== 'revision') intentados.add(p.clave)
  const errs = await validar('revision')
  for (const p of PASOS) if (p.clave !== 'revision') conErrores[p.clave] = errs.filter((e) => e.paso === p.clave).length
  errores.value = errs
}
const erroresPorPaso = computed(() => PASOS.slice(0, -1).map((p, i) => ({ ...p, i, mensajes: errores.value.filter((e) => e.paso === p.clave).map((e) => e.mensaje) }))
  .filter((p) => p.mensajes.length))

async function guardarBorrador() {
  ocupado.value = true
  try {
    clearTimeout(reloj)
    if (await guardar()) avisar(t('Draft saved. You can continue it from Purchase orders.'))
  } finally {
    ocupado.value = false
  }
}
async function enviar() {
  ocupado.value = true
  try {
    clearTimeout(reloj)
    if (sucio.value && !(await guardar())) return
    const d = await api.post(`/ordenes/${ocId.value}/enviar`, { version: version.value })
    guardadoComo.value = instantanea()
    avisar(d.oc.estado === 'APROBADA'
      ? t('PO {0} sent and approved: no approval rule applies to it.', [d.oc.numero])
      : t('PO {0} sent for approval.', [d.oc.numero]))
    router.push(`/ordenes/${ocId.value}`)
  } catch (e) {
    if (e.detalle?.length) {
      errores.value = e.detalle.map((x) => ({ paso: 'revision', ...x }))
      for (const p of PASOS) if (p.clave !== 'revision') conErrores[p.clave] = errores.value.filter((x) => x.paso === p.clave).length
    }
    errorApi(e)
  } finally {
    ocupado.value = false
  }
}
function cerrar() {
  router.push(ocId.value ? `/ordenes/${ocId.value}` : '/ordenes')
}

// ---- Líneas y totales
function quitarLinea(i) {
  lineas.value.splice(i, 1)
  if (!lineas.value.length) lineas.value.push(nuevaLinea())
}
const importe = (l) => (l.cantidad !== '' && l.precio !== '' ? Number(l.cantidad) * Number(l.precio) : null)
const total = computed(() => lineas.value.reduce((a, l) => a + (importe(l) || 0), 0))
const cantidades = computed(() => {
  const r = {}
  for (const l of lineas.value) if (l.codigo_sap && l.cantidad !== '') {
    const u = unidadDe(l) || 'UN'
    r[u] = { cantidad: (r[u]?.cantidad || 0) + Number(l.cantidad) }
  }
  return r
})
const documento = computed(() => (oc.value?.numero ? t('PO {0}', [oc.value.numero]) : t('New purchase order')))
const valorExtra = (c) => valorPropio(c, cab.extra?.[c.clave])
</script>

<template>
  <p v-if="cargando" class="ayuda">{{ t('Loading…') }}</p>
  <Asistente v-else-if="op" :documento="documento" :pasos="pasosVista" :actual="actual" :ocupado="ocupado" :guardado="guardado"
             :texto-final="t('Send purchase order')" @ir="ir" @anterior="ir(actual - 1)" @siguiente="siguiente" @guardar="guardarBorrador"
             @finalizar="enviar" @cerrar="cerrar">
    <div v-if="oc?.motivo_estado && ['RECHAZADA', 'BORRADOR'].includes(oc.estado) && oc.enviada_en" class="nota aviso">
      <Icono nombre="alerta" :tam="16" /><span>{{ t('It was rejected: {0}. Correct it and send it again.', [oc.motivo_estado]) }}</span>
    </div>
    <div v-if="sueltos.length" class="nota error bloque" role="alert"><ul class="lista-mensajes"><li v-for="(m, i) in sueltos" :key="i">{{ tx(m) }}</li></ul></div>

    <!-- 1. Datos generales -->
    <section v-if="paso.clave === 'general'" class="panel">
      <div class="panel-cabeza"><div><h2>{{ t('Who sells and who buys') }}</h2><p>{{ t('With the supplier and the PO number the draft is saved; the rest can be completed later.') }}</p></div></div>
      <div class="rejilla-campos">
        <div class="campo" :class="{ 'con-error': msjs('proveedor').length }"><span :class="{ req: req('proveedor') }">{{ t('Supplier') }}</span>
          <div v-if="ocId || op.proveedores.length === 1" class="valor-fijo">{{ tx(textoDe('proveedores', cab.proveedor)) }}</div>
          <SelectBusqueda v-else v-model="cab.proveedor" :opciones="op.proveedores" :etiqueta="t('Supplier')" :prefijo="false" />
          <small v-if="ocId" class="ayuda">{{ t('To change the supplier, create another PO.') }}</small>
          <small v-for="m in msjs('proveedor')" :key="m" class="campo-error">{{ tx(m) }}</small>
        </div>
        <label class="campo" :class="{ 'con-error': msjs('oc').length }"><span :class="{ req: req('oc') }">{{ t('PO number') }}</span>
          <input v-model.trim="cab.oc" class="entrada" maxlength="40" autocomplete="off" />
          <small v-for="m in msjs('oc')" :key="m" class="campo-error">{{ tx(m) }}</small>
        </label>
        <div class="campo" :class="{ 'con-error': msjs('sociedad').length }"><span :class="{ req: req('sociedad') }">{{ t('Company (bill to)') }}</span>
          <SelectBusqueda v-model="cab.sociedad" :opciones="sociedades" :vacio="t('Not defined')" :etiqueta="t('Company (bill to)')" :prefijo="false" />
          <small v-if="cab.proveedor && !sociedades.length" class="campo-error">{{ t('This supplier has no companies assigned. Assign them in Master data → Suppliers.') }}</small>
          <small v-for="m in msjs('sociedad')" :key="m" class="campo-error">{{ tx(m) }}</small>
        </div>
        <label class="campo" :class="{ 'con-error': msjs('fecha_oc').length }"><span :class="{ req: req('fecha_oc') }">{{ t('PO date') }}</span>
          <CampoFecha v-model="cab.fecha_oc" />
          <small v-for="m in msjs('fecha_oc')" :key="m" class="campo-error">{{ tx(m) }}</small>
        </label>
      </div>
    </section>

    <!-- 2. Artículos y cantidades -->
    <section v-else-if="paso.clave === 'articulos'" class="panel">
      <div class="panel-cabeza">
        <div><h2>{{ t('What is ordered') }}</h2><p>{{ t('Items of the supplier from the item master. Solids may bring their casepack (exact quantity per carton); a prepack brings its size run.') }}</p></div>
        <span v-if="Object.keys(cantidades).length" class="etiqueta">{{ porUnidadTxt(cantidades, 'cantidad') }}</span>
      </div>
      <p v-for="m in msjs('lineas')" :key="m" class="nota error">{{ tx(m) }}</p>
      <div class="lineas-oc">
        <div v-for="(l, i) in lineas" :key="i" class="linea-oc" :class="{ invalida: msjsLinea(i, 'codigo_sap', 'cantidad', 'unidad').length }">
          <span class="linea-num">{{ tx(i + 1) }}</span>
          <div class="campo campo-ancho" :class="{ 'con-error': msjsLinea(i, 'codigo_sap').length }"><span class="req">{{ t('Item') }}</span>
            <SelectBusqueda v-model="l.codigo_sap" :opciones="opcionesArt" :buscar="buscarArticulos" :etiqueta="t('Item')" :prefijo="false" @opcion="elegirArticulo(l, $event)" /></div>
          <label class="campo" :class="{ 'con-error': msjsLinea(i, 'cantidad').length }"><span class="req">{{ t('Quantity') }}</span>
            <span class="con-unidad"><input v-model="l.cantidad" class="entrada" type="number" :min="pasoCantidad(unidadDe(l))" :step="pasoCantidad(unidadDe(l))" />
              <small>{{ tx(l.codigo_sap ? unidadTxt(unidadDe(l), 2) : '') }}</small></span></label>
          <label v-if="!esPrepack(l)" class="campo"><span>{{ t('Casepack') }}</span><input v-model="l.casepack" class="entrada" type="number" min="1" step="1" :placeholder="t('Optional')" /></label>
          <div v-else class="campo"><span>{{ t('Packing') }}</span><span class="sub">{{ t('Size run of the prepack') }}</span></div>
          <div v-if="almacenes.length" class="campo"><span>{{ t('Warehouse') }}</span>
            <SelectBusqueda v-model="l.almacen" :opciones="almacenes" :vacio="t('Not defined')" :etiqueta="t('Warehouse')" :prefijo="false" /></div>
          <label class="campo"><span>{{ t('Delivery date') }}</span><CampoFecha v-model="l.fecha_entrega" /></label>
          <button type="button" class="btn-icono quitar" :aria-label="t('Remove line {0}', [i + 1])" @click="quitarLinea(i)"><Icono nombre="basura" :tam="16" /></button>
          <ul v-if="msjsLinea(i, 'codigo_sap', 'cantidad', 'unidad').length" class="lista-mensajes error-linea">
            <li v-for="(m, j) in msjsLinea(i, 'codigo_sap', 'cantidad', 'unidad')" :key="j">{{ tx(m) }}</li></ul>
        </div>
        <button type="button" class="btn btn-chico" @click="lineas.push(nuevaLinea())"><Icono nombre="mas" :tam="14" />{{ t('Add line') }}</button>
      </div>
    </section>

    <!-- 3. Condiciones económicas -->
    <template v-else-if="paso.clave === 'condiciones'">
      <section class="panel">
        <div class="panel-cabeza"><div><h2>{{ t('Currency and terms') }}</h2></div></div>
        <div class="rejilla-campos">
          <div class="campo" :class="{ 'con-error': msjs('moneda').length }"><span :class="{ req: req('moneda') }">{{ t('Currency') }}</span>
            <SelectBusqueda v-model="cab.moneda" :opciones="op.monedas" :vacio="t('Not defined')" :etiqueta="t('Currency')" :prefijo="false" />
            <small v-for="m in msjs('moneda')" :key="m" class="campo-error">{{ tx(m) }}</small></div>
          <div class="campo" :class="{ 'con-error': msjs('incoterm').length }"><span :class="{ req: req('incoterm') }">{{ t('Incoterm') }}</span>
            <SelectBusqueda v-model="cab.incoterm" :opciones="op.incoterms" :vacio="t('Not defined')" :etiqueta="t('Incoterm')" :prefijo="false" />
            <small v-for="m in msjs('incoterm')" :key="m" class="campo-error">{{ tx(m) }}</small></div>
          <div class="campo" :class="{ 'con-error': msjs('condicion_pago').length }"><span :class="{ req: req('condicion_pago') }">{{ t('Payment terms') }}</span>
            <SelectBusqueda v-model="cab.condicion_pago" :opciones="op.condiciones_pago" :vacio="t('Not defined')" :etiqueta="t('Payment terms')" :prefijo="false" />
            <small v-for="m in msjs('condicion_pago')" :key="m" class="campo-error">{{ tx(m) }}</small></div>
        </div>
      </section>
      <section class="panel">
        <div class="panel-cabeza"><div><h2>{{ t('Prices') }}</h2><p>{{ t('Unit price of each line, in the currency of the PO.') }}</p></div>
          <span class="etiqueta acento">{{ t('Total') }} {{ fmtMoneda(total, cab.moneda) }}</span></div>
        <div class="tabla-marco">
          <table class="tabla">
            <thead><tr><th>#</th><th>{{ t('Item') }}</th><th class="num">{{ t('Quantity') }}</th><th class="num">{{ t('Unit price') }}</th><th class="num">{{ t('Amount') }}</th></tr></thead>
            <tbody>
              <tr v-for="(l, i) in lineas" :key="i" :class="{ 'con-error': msjsLinea(i, 'precio').length }">
                <td>{{ tx(i + 1) }}</td>
                <td>{{ tx(infoArt[l.codigo_sap]?.texto || l.codigo_sap || '—') }}<small v-for="m in msjsLinea(i, 'precio')" :key="m" class="campo-error">{{ tx(m) }}</small></td>
                <td class="num">{{ l.cantidad !== '' ? cantTxt(l.cantidad, unidadDe(l)) : '—' }}</td>
                <td class="num"><input v-model="l.precio" class="entrada precio" type="number" min="0" step="any" :aria-label="t('Unit price of line {0}', [i + 1])" /></td>
                <td class="num">{{ importe(l) === null ? '—' : fmtMoneda(importe(l), cab.moneda) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </template>

    <!-- 4. Logística y fechas (los datos de aduana se piden aquí, no antes) -->
    <template v-else-if="paso.clave === 'logistica'">
      <section class="panel">
        <div class="panel-cabeza"><div><h2>{{ t('Dates and route') }}</h2></div></div>
        <div class="rejilla-campos">
          <label class="campo" :class="{ 'con-error': msjs('fecha_xf').length }"><span :class="{ req: req('fecha_xf') }">{{ t('Ship date (XF)') }}</span>
            <CampoFecha v-model="cab.fecha_xf" /><small v-for="m in msjs('fecha_xf')" :key="m" class="campo-error">{{ tx(m) }}</small></label>
          <label class="campo" :class="{ 'con-error': msjs('fecha_tienda').length }"><span :class="{ req: req('fecha_tienda') }">{{ t('In-store date') }}</span>
            <CampoFecha v-model="cab.fecha_tienda" :min="cab.fecha_xf || undefined" /><small v-for="m in msjs('fecha_tienda')" :key="m" class="campo-error">{{ tx(m) }}</small></label>
          <div class="campo" :class="{ 'con-error': msjs('puerto_despacho').length }"><span :class="{ req: req('puerto_despacho') }">{{ t('Port of loading') }}</span>
            <SelectBusqueda v-model="cab.puerto_despacho" :opciones="op.puertos" :vacio="t('Not defined')" :etiqueta="t('Port of loading')" :prefijo="false" />
            <small v-for="m in msjs('puerto_despacho')" :key="m" class="campo-error">{{ tx(m) }}</small></div>
          <div class="campo" :class="{ 'con-error': msjs('centro').length }"><span :class="{ req: req('centro') }">{{ t('Receiving plant') }}</span>
            <SelectBusqueda v-model="cab.centro" :opciones="centros" :vacio="t('Not defined')" :etiqueta="t('Receiving plant')" :prefijo="false" />
            <small v-for="m in msjs('centro')" :key="m" class="campo-error">{{ tx(m) }}</small></div>
          <div class="campo" :class="{ 'con-error': msjs('centro_destino').length }"><span :class="{ req: req('centro_destino') }">{{ t('Destination plant') }}</span>
            <SelectBusqueda v-model="cab.centro_destino" :opciones="centros" :vacio="t('Not defined')" :etiqueta="t('Destination plant')" :prefijo="false" />
            <small v-for="m in msjs('centro_destino')" :key="m" class="campo-error">{{ tx(m) }}</small></div>
        </div>
      </section>
      <section class="panel">
        <div class="panel-cabeza"><div><h2>{{ t('Customs data') }}</h2><p>{{ t('Origin of the goods for the customs documents. If empty, each item’s own country of origin is used.') }}</p></div></div>
        <div class="rejilla-campos">
          <div class="campo" :class="{ 'con-error': msjs('pais_origen').length }"><span :class="{ req: req('pais_origen') }">{{ t('Country of origin') }}</span>
            <SelectBusqueda v-model="cab.pais_origen" :opciones="op.paises" :vacio="t('Not defined')" :etiqueta="t('Country of origin')" :prefijo="false" />
            <small v-for="m in msjs('pais_origen')" :key="m" class="campo-error">{{ tx(m) }}</small></div>
          <div class="campo" :class="{ 'con-error': msjs('pais_procedencia').length }"><span>{{ t('Country of provenance') }}</span>
            <SelectBusqueda v-model="cab.pais_procedencia" :opciones="op.paises" :vacio="t('Not defined')" :etiqueta="t('Country of provenance')" :prefijo="false" />
            <small v-for="m in msjs('pais_procedencia')" :key="m" class="campo-error">{{ tx(m) }}</small></div>
        </div>
      </section>
    </template>

    <!-- 5. Documentación y datos propios de la empresa -->
    <section v-else-if="paso.clave === 'documentacion'" class="panel">
      <div class="panel-cabeza"><div><h2>{{ t('Notes and own fields') }}</h2><p>{{ t('Instructions for the supplier and the data your company adds to its POs.') }}</p></div></div>
      <div class="rejilla-campos">
        <label class="campo campo-ancho"><span>{{ t('Notes') }}</span><textarea v-model="cab.notas" class="entrada" rows="4" maxlength="2000" /></label>
        <template v-for="c in propios" :key="c.clave">
          <div class="campo" :class="{ 'con-error': msjs(`extra.${c.clave}`).length }"><span :class="{ req: c.obligatorio }">{{ c.etiqueta }}</span>
            <Interruptor v-if="c.tipo === 'bool'" :model-value="!!cab.extra[c.clave]" :etiqueta="c.etiqueta" @update:model-value="cab.extra[c.clave] = $event" />
            <CampoFecha v-else-if="c.tipo === 'fecha'" v-model="cab.extra[c.clave]" />
            <Seleccion v-else-if="c.tipo === 'opcion'" v-model="cab.extra[c.clave]" class="entrada" :aria-label="c.etiqueta">
              <option value="">{{ t('Not defined') }}</option><option v-for="x in c.opciones" :key="x" :value="x">{{ x }}</option></Seleccion>
            <input v-else v-model="cab.extra[c.clave]" class="entrada" :type="c.tipo === 'numero' ? 'number' : 'text'" step="any" :aria-label="c.etiqueta" />
            <small v-for="m in msjs(`extra.${c.clave}`)" :key="m" class="campo-error">{{ tx(m) }}</small>
          </div>
        </template>
      </div>
      <p v-if="!propios.length" class="ayuda mt-chico">{{ t('Your company has no own fields for POs (Settings → Company → Own fields).') }}</p>
    </section>

    <!-- 6. Revisión y envío -->
    <template v-else>
      <div v-if="erroresPorPaso.length" class="nota aviso bloque" role="alert">
        <b>{{ t('Complete these steps before sending:') }}</b>
        <div v-for="p in erroresPorPaso" :key="p.clave" class="rev-error">
          <button type="button" class="btn btn-chico" @click="ir(p.i)">{{ tx(p.titulo) }}<Icono nombre="derecha" :tam="14" /></button>
          <ul class="lista-mensajes"><li v-for="(m, j) in p.mensajes" :key="j">{{ tx(m) }}</li></ul>
        </div>
      </div>
      <div v-else class="nota ok"><Icono nombre="check" :tam="16" /><span>{{ t('Everything is complete. When you send it, your company’s approval rules decide who approves it; if none applies, it is approved right away.') }}</span></div>

      <div class="revision">
        <section class="panel">
          <div class="panel-cabeza"><h2>{{ t('General data') }}</h2><button type="button" class="btn btn-chico btn-fantasma" @click="ir(0)"><Icono nombre="editar" :tam="14" />{{ t('Edit') }}</button></div>
          <dl class="datos">
            <dt>{{ t('Supplier') }}</dt><dd>{{ tx(textoDe('proveedores', cab.proveedor)) }}</dd>
            <dt>{{ t('PO number') }}</dt><dd>{{ tx(cab.oc || '—') }}</dd>
            <dt>{{ t('Company (bill to)') }}</dt><dd>{{ tx(textoDe('sociedades', cab.sociedad)) }}</dd>
            <dt>{{ t('PO date') }}</dt><dd>{{ fmtFecha(cab.fecha_oc) }}</dd>
          </dl>
        </section>
        <section class="panel">
          <div class="panel-cabeza"><h2>{{ t('Commercial terms') }}</h2><button type="button" class="btn btn-chico btn-fantasma" @click="ir(2)"><Icono nombre="editar" :tam="14" />{{ t('Edit') }}</button></div>
          <dl class="datos">
            <dt>{{ t('Currency') }}</dt><dd>{{ tx(cab.moneda || '—') }}</dd>
            <dt>{{ t('Incoterm') }}</dt><dd>{{ tx(textoDe('incoterms', cab.incoterm)) }}</dd>
            <dt>{{ t('Payment terms') }}</dt><dd>{{ tx(textoDe('condiciones_pago', cab.condicion_pago)) }}</dd>
            <dt>{{ t('Total') }}</dt><dd><b>{{ fmtMoneda(total, cab.moneda) }}</b></dd>
          </dl>
        </section>
        <section class="panel">
          <div class="panel-cabeza"><h2>{{ t('Logistics and dates') }}</h2><button type="button" class="btn btn-chico btn-fantasma" @click="ir(3)"><Icono nombre="editar" :tam="14" />{{ t('Edit') }}</button></div>
          <dl class="datos">
            <dt>{{ t('Ship date (XF)') }}</dt><dd>{{ fmtFecha(cab.fecha_xf) }}</dd>
            <dt>{{ t('In-store date') }}</dt><dd>{{ fmtFecha(cab.fecha_tienda) }}</dd>
            <dt>{{ t('Port of loading') }}</dt><dd>{{ tx(textoDe('puertos', cab.puerto_despacho)) }}</dd>
            <dt>{{ t('Receiving plant') }}</dt><dd>{{ tx(textoDe('centros', cab.centro)) }}</dd>
            <dt>{{ t('Destination plant') }}</dt><dd>{{ tx(textoDe('centros', cab.centro_destino)) }}</dd>
            <dt>{{ t('Country of origin') }}</dt><dd>{{ tx(textoDe('paises', cab.pais_origen)) }}</dd>
          </dl>
        </section>
        <section class="panel">
          <div class="panel-cabeza"><h2>{{ t('Documentation and extras') }}</h2><button type="button" class="btn btn-chico btn-fantasma" @click="ir(4)"><Icono nombre="editar" :tam="14" />{{ t('Edit') }}</button></div>
          <dl class="datos">
            <dt>{{ t('Notes') }}</dt><dd class="notas">{{ tx(cab.notas || '—') }}</dd>
            <template v-for="c in propios" :key="c.clave"><dt>{{ c.etiqueta }}</dt><dd>{{ valorExtra(c) }}</dd></template>
          </dl>
        </section>
      </div>
      <section class="panel">
        <div class="panel-cabeza"><h2>{{ t('Lines ({0})', [lineas.filter((l) => l.codigo_sap).length]) }}</h2>
          <button type="button" class="btn btn-chico btn-fantasma" @click="ir(1)"><Icono nombre="editar" :tam="14" />{{ t('Edit') }}</button></div>
        <div class="tabla-marco">
          <table class="tabla">
            <thead><tr><th>#</th><th>{{ t('Item') }}</th><th class="num">{{ t('Quantity') }}</th><th class="num">{{ t('Unit price') }}</th><th class="num">{{ t('Amount') }}</th><th>{{ t('Warehouse') }}</th></tr></thead>
            <tbody>
              <tr v-for="(l, i) in lineas" :key="i">
                <td>{{ tx(i + 1) }}</td>
                <td>{{ tx(infoArt[l.codigo_sap]?.texto || l.codigo_sap || '—') }}<small v-for="m in msjsLinea(i)" :key="m" class="campo-error">{{ tx(m) }}</small></td>
                <td class="num">{{ l.cantidad !== '' ? cantTxt(l.cantidad, unidadDe(l)) : '—' }}</td>
                <td class="num">{{ l.precio !== '' ? fmtNum(l.precio) : '—' }}</td>
                <td class="num">{{ importe(l) === null ? '—' : fmtMoneda(importe(l), cab.moneda) }}</td>
                <td>{{ tx(l.almacen || '—') }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </template>
  </Asistente>
</template>

<style scoped>
.campo-error { color: var(--error); font-size: 0.8rem; font-weight: 500; display: block; }
.con-error :deep(.entrada), .con-error :deep(.sb-boton) { border-color: var(--error); }
.lineas-oc { display: flex; flex-direction: column; gap: 10px; }
.linea-oc { display: grid; grid-template-columns: 28px minmax(220px, 2.2fr) repeat(auto-fit, minmax(120px, 1fr)) auto; gap: 10px; align-items: end;
  padding: 10px; border: 1px solid var(--linea); border-radius: 10px; background: var(--superficie); }
.linea-oc.invalida { border-color: var(--error); }
.linea-num { align-self: center; color: var(--tinta-3); font-weight: 650; font-size: 0.85rem; }
.linea-oc .quitar { align-self: center; }
.error-linea { grid-column: 1 / -1; color: var(--error); margin: 0; font-size: 0.84rem; }
.con-unidad { display: flex; align-items: center; gap: 6px; }
.con-unidad small { color: var(--tinta-2); white-space: nowrap; }
.entrada.precio { width: 130px; text-align: end; }
.revision { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 16px; }
.revision .panel { margin: 0; }
.datos { display: grid; grid-template-columns: auto 1fr; gap: 6px 14px; margin: 0; font-size: 0.9rem; }
.datos dt { color: var(--tinta-2); }
.datos dd { margin: 0; color: var(--tinta); min-width: 0; overflow-wrap: anywhere; }
.datos .notas { white-space: pre-line; }
.rev-error { display: flex; gap: 10px; align-items: flex-start; margin-top: 8px; }
.rev-error .lista-mensajes { margin: 2px 0 0; }
@media (max-width: 720px) {
  .linea-oc { grid-template-columns: 1fr 1fr; }
  .linea-oc .campo-ancho { grid-column: 1 / -1; }
  .linea-num { grid-column: 1; }
  .linea-oc .quitar { grid-column: 2; grid-row: 1; justify-self: end; }
}
</style>
