<script setup>
import { t, tx } from '@/i18n/index.js'
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '@/nucleo/api'
import Asistente from '@/componentes/Asistente.vue'
import EstadoBadge from '@/componentes/EstadoBadge.vue'
import Icono from '@/componentes/Icono.vue'
import Modal from '@/componentes/Modal.vue'
import Seleccion from '@/componentes/Seleccion.vue'
import SelectBusqueda from '@/componentes/SelectBusqueda.vue'
import { fmtNum } from '@/nucleo/utils'
import { avisar, errorApi } from '@/stores/ui'
import { CATEGORIAS, MODALIDADES, ORIGENES, UNIDADES, UNIDADES_DE } from '@/modulos/etiquetado/etiquetas.js'
import { buscarArticulos, buscarOrdenes } from '@/modulos/etiquetado/componentes/buscadores.js'

// Asistente único de etiquetado. Todas las entradas (una OC, varias OC desde
// su lista, artículos, una lista de empaque, el centro) crean un trabajo en el
// servidor con el mismo servicio; cada paso se guarda como borrador y al
// volver se sigue en el mismo paso. El servidor valida cada registro (reglas,
// datos, empaque, códigos leídos con un lector) y genera: todo, o solo lo
// listo si la empresa lo permite; desde cierto tamaño, en segundo plano.
const route = useRoute()
const router = useRouter()
const trabajo = ref(null)
const ocupado = ref(false)
const guardado = ref('')
const paso = ref(0)
const p = reactive({ oc_ids: [], posiciones: [], cantidades: {}, articulos: [], pl_id: '', tipo_empaque_id: '', familia_id: '', modalidad: '',
  unidad: '', plantilla_id: '', motivo_diseno: '', elegidas: {}, manuales: {}, formato: 'PDF',
  zip: { carpetas: [], nombre: '', contenido: 'PDF' } })
const origen = ref('OC')

const PASOS = () => [
  ['origen', t('Origin')], ['registros', t('Records')], ['empaque', t('Packaging')], ['reglas', t('Rules and designs')],
  ['previa', t('Preview')], ['errores', t('Errors and warnings')], ['generar', t('Generate')], ['descargas', t('Downloads and history')],
]
const registros = computed(() => trabajo.value?.registros || [])
const conteo = computed(() => trabajo.value?.resumen?.conteo || {})
const validado = computed(() => trabajo.value && trabajo.value.estado !== 'BORRADOR' && trabajo.value.validado_en)
const pasos = computed(() => PASOS().map(([clave, titulo], i) => ({
  clave, titulo,
  errores: clave === 'errores' && validado.value ? (conteo.value.ERROR || 0) + (trabajo.value.resumen.problemas?.length || 0) : 0,
  completo: i < paso.value,
  bloqueado: !trabajo.value && i > 0,
})))

// ---- Carga, alta y borrador ---------------------------------------------------------------
function aplicar(tr) {
  trabajo.value = tr
  origen.value = tr.origen
  const par = tr.parametros || {}
  Object.assign(p, { oc_ids: par.oc_ids || [], posiciones: par.posiciones || [], cantidades: par.cantidades || {}, articulos: par.articulos || [],
    pl_id: par.pl_id || '', tipo_empaque_id: par.tipo_empaque_id || '', familia_id: par.familia_id || '', modalidad: par.modalidad || '',
    unidad: par.unidad || '', plantilla_id: par.plantilla_id || '', motivo_diseno: par.motivo_diseno || '', elegidas: par.elegidas || {},
    manuales: par.manuales || {}, formato: par.formato || 'PDF', zip: { carpetas: [], nombre: '', contenido: 'PDF', ...(par.zip || {}) } })
  if (!p.modalidad) p.modalidad = { OC: 'OC_ARTICULO', ARTICULOS: 'ARTICULO', PACKING: 'OC_ARTICULO' }[tr.origen]
  if (!p.unidad) p.unidad = { OC: 'LINEA', ARTICULOS: 'MANUAL', PACKING: 'BULTO' }[tr.origen]
}

async function cargar(id) {
  try {
    aplicar(await api.get(`/etiquetas/trabajos/${id}`))
    paso.value = Math.min(trabajo.value.paso || 0, PASOS().length - 1)
    if (trabajo.value.estado === 'EN_PROCESO') seguir()
  } catch (e) {
    errorApi(e)
  }
}

function parametros() {
  const base = { modalidad: p.modalidad, unidad: p.unidad, manuales: p.manuales, elegidas: p.elegidas, formato: p.formato,
    familia_id: p.familia_id || null, plantilla_id: p.plantilla_id || null, motivo_diseno: p.motivo_diseno || null }
  if (origen.value === 'OC') Object.assign(base, { oc_ids: p.oc_ids, posiciones: p.posiciones.length ? p.posiciones : null, cantidades: p.cantidades })
  if (origen.value === 'ARTICULOS') base.articulos = p.articulos
  if (origen.value === 'PACKING') Object.assign(base, { pl_id: p.pl_id || null, tipo_empaque_id: p.tipo_empaque_id || null })
  if (['GENERADO', 'PARCIAL'].includes(trabajo.value?.estado)) return { zip: p.zip, formato: p.formato, manuales: p.manuales }
  return { ...base, zip: p.zip }
}

async function guardar(silencioso = false) {
  if (!trabajo.value) return crear()
  if (['EN_PROCESO', 'CANCELADO'].includes(trabajo.value.estado)) return true
  try {
    guardado.value = t('Saving…')
    aplicar(await api.patch(`/etiquetas/trabajos/${trabajo.value.id}`, { paso: paso.value, parametros: parametros(), version: trabajo.value.version }))
    guardado.value = t('Saved at {0}', [new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })])
    if (!silencioso) avisar(t('Draft saved: you can continue later from the labels center.'))
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

async function crear() {
  const datos = { origen: origen.value, paso: 1, parametros: p.familia_id ? { familia_id: p.familia_id } : {} }
  if (origen.value === 'OC') datos.parametros.oc_ids = p.oc_ids
  if (origen.value === 'ARTICULOS') datos.parametros.articulos = p.articulos
  if (origen.value === 'PACKING') datos.parametros.pl_id = p.pl_id || null
  try {
    const tr = await api.post('/etiquetas/trabajos', datos)
    router.replace(`/etiquetas/trabajos/${tr.id}`)
    aplicar(tr)
    paso.value = 1
    return true
  } catch (e) {
    errorApi(e)
    return false
  }
}

onMounted(async () => {
  if (route.params.id) return cargar(route.params.id)
  // Entradas: ?origen=OC&oc=1 | &ocs=1,2 · ?origen=ARTICULOS&articulos=1,2 · ?origen=PACKING&pl=3
  const q = route.query
  origen.value = ['OC', 'ARTICULOS', 'PACKING'].includes(q.origen) ? q.origen : 'OC'
  const ids = (v) => String(v || '').split(',').map(Number).filter(Boolean)
  p.oc_ids = ids(q.ocs || q.oc)
  p.articulos = ids(q.articulos).map((id) => ({ articulo_id: id, cantidad: 1 }))
  p.pl_id = q.pl ? Number(q.pl) : ''
  if (q.familia) {
    // Desde una familia: sus OC (las que tienen artículos de ella), etiquetando solo esos artículos
    p.familia_id = Number(q.familia)
    if (!p.oc_ids.length) p.oc_ids = (await api.get('/etiquetas/masivo/ordenes', { familia_id: q.familia, solo_ids: true }).catch(() => ({ ids: [] }))).ids.slice(0, 200)
  }
  await cargarNombres()
  if ((origen.value === 'OC' && p.oc_ids.length) || (origen.value === 'ARTICULOS' && p.articulos.length) || (origen.value === 'PACKING' && p.pl_id)) {
    ocupado.value = true
    await crear()
    ocupado.value = false
  }
})

// ---- Navegación -------------------------------------------------------------------------------
const NECESITA_VALIDAR = ['reglas', 'previa', 'errores', 'generar']
async function ir(i) {
  if (ocupado.value) return
  ocupado.value = true
  try {
    if (!trabajo.value) {
      if (i > 0 && !(await crear())) return
    } else if (!(await guardar(true))) return
    const clave = PASOS()[i][0]
    if (NECESITA_VALIDAR.includes(clave) && trabajo.value.estado === 'BORRADOR') await validar(true)
    paso.value = i
    if (clave === 'previa' && !previa.value && registros.value.length) verPrevia(registros.value[0])
    if (clave === 'empaque' && origen.value === 'PACKING' && p.pl_id && !niveles.value) cargarNiveles()
  } finally {
    ocupado.value = false
  }
}

async function validar(silencioso = false) {
  try {
    aplicar(await api.post(`/etiquetas/trabajos/${trabajo.value.id}/validar`))
    previa.value = null
    if (!silencioso) avisar(t('Checked on the server: {0} records.', [registros.value.length]))
  } catch (e) {
    errorApi(e)
  }
}

function cerrar() {
  router.push({ path: '/etiquetas', query: { vista: 'trabajos' } })
}

// ---- 1. Origen ----------------------------------------------------------------------------------
const nombres = reactive({ oc: {}, articulo: {}, pl: {} })
async function cargarNombres() {
  for (const id of p.oc_ids) {
    if (!nombres.oc[id]) api.get(`/etiquetas/oc/${id}`).then((r) => (nombres.oc[id] = r.oc.numero)).catch(() => {})
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
const listasEmpaque = ref([])
const buscarPl = async (q) => (await api.get('/etiquetas/masivo/packing', { q })).map((x) => ({ valor: x.id, texto: x.numero, sub: [x.factura, x.proveedor].filter(Boolean).join(' · ') }))
onMounted(() => api.get('/etiquetas/masivo/packing').then((r) => (listasEmpaque.value = r)).catch(() => {}))

// ---- 2. Registros -----------------------------------------------------------------------------------
const lineas = reactive({})
async function cargarLineas() {
  if (origen.value !== 'OC' || p.oc_ids.length > 5) return
  for (const id of p.oc_ids) {
    if (!lineas[id]) api.get(`/etiquetas/oc/${id}`).then((r) => (lineas[id] = r.lineas)).catch(() => {})
  }
}
watch(paso, (v) => v === 1 && cargarLineas())
watch(() => p.modalidad, (m) => {
  if (m && !UNIDADES_DE[m].includes(p.unidad)) p.unidad = UNIDADES_DE[m][0]
})
const modalidades = computed(() => MODALIDADES().filter(([m]) => (origen.value === 'ARTICULOS' ? m === 'ARTICULO' : m !== 'ARTICULO')))
const unidades = computed(() => (origen.value === 'PACKING' ? ['BULTO'] : UNIDADES_DE[p.modalidad] || []))
const elegida = (id) => !p.posiciones.length || p.posiciones.includes(id)
function alternarLinea(id, todas) {
  let lista = p.posiciones.length ? [...p.posiciones] : todas.filter((x) => !x.bloqueada).map((x) => x.id)
  lista = lista.includes(id) ? lista.filter((x) => x !== id) : [...lista, id]
  p.posiciones = lista
}

// ---- 3. Empaque ---------------------------------------------------------------------------------------
const niveles = ref(null)
async function cargarNiveles() {
  try {
    niveles.value = await api.get(`/etiquetas/masivo/packing/${p.pl_id}`)
  } catch (e) {
    errorApi(e)
  }
}
const deEmpaque = computed(() => registros.value.flatMap((r) => (r.problemas || [])
  .filter((x) => ['empaque', 'inconsistencia'].includes(x.categoria)).map((x) => ({ ...x, referencia: r.referencia }))))

// ---- 4. Reglas y diseños ---------------------------------------------------------------------------
const disenos = computed(() => trabajo.value?.resumen?.disenos || [])
const plantillas = ref([])
watch(() => p.modalidad, (m) => m && api.get('/etiquetas/plantillas', { modalidad: m, size: 200 })
  .then((r) => (plantillas.value = r.items.filter((x) => x.vigente))).catch(() => {}), { immediate: true })
async function elegirDiseno(r, plantillaId) {
  p.elegidas = { ...p.elegidas, [r.clave]: Number(plantillaId) }
  ocupado.value = true
  if (await guardar(true)) await validar(true)
  ocupado.value = false
}
const candidatas = (r) => (r.problemas || []).find((x) => x.codigo === 'elegir_plantilla')

// ---- 5. Vista previa -----------------------------------------------------------------------------------
const previa = ref(null)
const registroPrevia = ref(null)
async function verPrevia(r) {
  registroPrevia.value = r.id
  try {
    previa.value = await api.get(`/etiquetas/trabajos/${trabajo.value.id}/registros/${r.id}/vista-previa`)
  } catch (e) {
    previa.value = null
    errorApi(e)
  }
}

// ---- 6. Errores ---------------------------------------------------------------------------------------
const filtroNivel = ref('')
const problemas = computed(() => registros.value.flatMap((r) => (r.problemas || []).map((x) => ({ ...x, referencia: r.referencia, estado: r.estado }))))
const porCategoria = computed(() => {
  const res = {}
  for (const x of problemas.value.filter((x) => !filtroNivel.value || x.nivel === filtroNivel.value)) {
    (res[x.categoria || 'diseno'] ||= []).push(x)
  }
  return Object.entries(res).sort((a, b) => b[1].filter((x) => x.nivel === 'error').length - a[1].filter((x) => x.nivel === 'error').length)
})
const variables = computed(() => trabajo.value?.resumen?.variables || [])

// ---- 7. Generar -----------------------------------------------------------------------------------------
const opciones = reactive({ aceptar: false, parcial: false })
const advertencias = computed(() => registros.value.filter((r) => r.estado === 'ADVERTENCIA').length)
const pendientes = computed(() => registros.value.filter((r) => ['LISTO', 'ADVERTENCIA'].includes(r.estado)))
const etiquetasPendientes = computed(() => pendientes.value.reduce((s, r) => s + r.cantidad, 0))
const CARPETAS = () => [['oc', t('PO')], ['plantilla', t('Design')], ['familia', t('Labeling family')], ['packing_list', t('Packing list')]]
const MARCADORES = ['oc', 'referencia', 'sku', 'n', 'total', 'i', 'plantilla', 'serie', 'bulto']
const marcadoresTxt = MARCADORES.map((m) => `{${m}}`).join(' ')
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
    } else {
      avisar(r.estado === 'PARCIAL' ? t('Generated the ready records; the ones with errors are pending.') : t('Labels generated.'))
      paso.value = 7
    }
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
      paso.value = 7
      if (e.error) avisar(tx(e.error), 'error')
    } catch {
      seguir()
    }
  }, 1200)
}
onBeforeUnmount(() => clearTimeout(temporizador))

// ---- 8. Descargas -----------------------------------------------------------------------------------------
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
const NIVEL_ICONO = { error: 'alerta', advertencia: 'info', info: 'info' }
</script>

<template>
  <Asistente :documento="trabajo ? trabajo.nombre : t('New labeling job')" :pasos="pasos" :actual="paso" :ocupado="ocupado" :guardado="guardado"
             :text-final="t('Back to the labels center')" @ir="ir" @anterior="ir(paso - 1)" @siguiente="ir(paso + 1)" @guardar="guardar()"
             @finalizar="cerrar" @cerrar="cerrar">
    <div v-if="trabajo" class="tj-estado">
      <EstadoBadge :estado="trabajo.estado" tipo="trabajo" />
      <span v-if="validado">{{ t('{0} records · {1} labels to generate', [registros.length, fmtNum(trabajo.total)]) }}</span>
      <span v-if="conteo.ERROR" class="etiqueta error ms-0">{{ t('{0} with errors', [conteo.ERROR]) }}</span>
      <span v-if="conteo.ADVERTENCIA" class="etiqueta aviso ms-0">{{ t('{0} with warnings', [conteo.ADVERTENCIA]) }}</span>
      <span v-if="conteo.GENERADO" class="etiqueta info ms-0">{{ t('{0} generated', [conteo.GENERADO]) }}</span>
      <button v-if="trabajo.estado !== 'EN_PROCESO' && paso > 0" type="button" class="btn btn-chico separar" :disabled="ocupado" @click="validar()">
        <Icono nombre="rehacer" :tam="14" />{{ t('Check again') }}</button>
    </div>

    <!-- 1. Origen -->
    <section v-if="paso === 0" class="panel">
      <div class="tj-origenes" role="radiogroup" :aria-label="t('Origin')">
        <button v-for="[clave, titulo, ayuda] in ORIGENES()" :key="clave" type="button" class="tj-origen" role="radio"
                :aria-checked="origen === clave" :disabled="!!trabajo" @click="origen = clave">
          <strong>{{ tx(titulo) }}</strong><span>{{ tx(ayuda) }}</span></button>
      </div>
      <div v-if="origen === 'OC'" class="tj-bloque">
        <label class="campo"><span>{{ t('Add a purchase order') }}</span>
          <SelectBusqueda v-model="nuevaOc" :buscar="buscarOrdenes" :etiqueta="t('Purchase order')" :prefijo="false" :vacio="t('Search a PO…')" /></label>
        <div class="tj-chips">
          <span v-for="id in p.oc_ids" :key="id" class="chip">{{ nombres.oc[id] || id }}
            <button type="button" class="btn-icono" :aria-label="t('Remove')" @click="p.oc_ids = p.oc_ids.filter((x) => x !== id)"><Icono nombre="cerrar" :tam="12" /></button></span>
          <span v-if="!p.oc_ids.length" class="ayuda">{{ t('Choose one or more POs (or start from the PO list and select several).') }}</span>
        </div>
      </div>
      <div v-else-if="origen === 'ARTICULOS'" class="tj-bloque">
        <label class="campo"><span>{{ t('Add an item') }}</span>
          <SelectBusqueda v-model="nuevoArticulo" :buscar="buscarArticulos" :etiqueta="t('Item')" :prefijo="false" :vacio="t('Search an item…')" /></label>
        <table v-if="p.articulos.length" class="tabla tj-tabla">
          <thead><tr><th>{{ t('Item') }}</th><th class="num">{{ t('Labels') }}</th><th></th></tr></thead>
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
                          :opciones="listasEmpaque.map((x) => ({ valor: x.id, texto: x.numero, sub: x.factura }))" /></label>
      </div>
    </section>

    <!-- 2. Registros -->
    <section v-else-if="paso === 1" class="panel tj-bloque">
      <div class="tj-fila">
        <label class="campo"><span>{{ t('Data on the label') }}</span>
          <Seleccion v-model="p.modalidad"><option v-for="[m, txt] in modalidades" :key="m" :value="m">{{ tx(txt) }}</option></Seleccion></label>
        <label class="campo"><span>{{ t('Each label represents') }}</span>
          <Seleccion v-model="p.unidad"><option v-for="u in unidades" :key="u" :value="u">{{ tx(UNIDADES()[u]) }}</option></Seleccion></label>
      </div>
      <p class="ayuda">{{ tx(MODALIDADES().find((m) => m[0] === p.modalidad)?.[2] || '') }}</p>
      <template v-if="origen === 'OC'">
        <p v-if="p.oc_ids.length > 5" class="nota">{{ t('With more than 5 POs all their open lines are labeled; to choose lines, use fewer POs.') }}</p>
        <div v-for="id in p.oc_ids.length <= 5 ? p.oc_ids : []" :key="id" class="tj-oc">
          <h3>{{ t('PO {0}', [nombres.oc[id] || id]) }}</h3>
          <table v-if="lineas[id]" class="tabla tj-tabla">
            <thead><tr><th></th><th>{{ t('Line') }}</th><th>{{ t('Item') }}</th><th>{{ t('Family') }}</th><th class="num">{{ t('Quantity') }}</th>
              <th v-if="p.unidad === 'MANUAL'" class="num">{{ t('Labels') }}</th></tr></thead>
            <tbody><tr v-for="l in lineas[id]" :key="l.id" :class="{ apagada: l.bloqueada }">
              <td><input type="checkbox" :checked="elegida(l.id) && !l.bloqueada" :disabled="l.bloqueada" :aria-label="t('Label this line')"
                         @change="alternarLinea(l.id, Object.values(lineas).flat())" /></td>
              <td>{{ l.posicion }}</td><td>{{ l.codigo }} <span class="ayuda">{{ [l.color, l.talla].filter(Boolean).join(' · ') }}</span></td>
              <td>{{ tx(l.familia || '—') }}</td><td class="num">{{ fmtNum(l.cantidad) }} {{ tx(l.unidad) }}</td>
              <td v-if="p.unidad === 'MANUAL'" class="num"><input v-model.number="p.cantidades[l.id]" type="number" min="0" class="tj-num" :aria-label="t('Labels')" /></td>
            </tr></tbody>
          </table>
          <p v-else class="ayuda">{{ t('Loading…') }}</p>
        </div>
      </template>
      <p v-else-if="origen === 'ARTICULOS'" class="ayuda">{{ t('{0} items; the quantity of each one is set in the first step.', [p.articulos.length]) }}</p>
      <p v-else class="ayuda">{{ t('One label per package of the level chosen in the next step.') }}</p>
    </section>

    <!-- 3. Empaque -->
    <section v-else-if="paso === 2" class="panel tj-bloque">
      <template v-if="origen === 'PACKING'">
        <label class="campo"><span>{{ t('Packaging level') }}</span>
          <Seleccion v-model="p.tipo_empaque_id">
            <option value="">{{ t('Outer packages ({0})', [niveles?.superiores ?? '…']) }}</option>
            <option v-for="n in niveles?.niveles || []" :key="n.tipo_empaque_id" :value="n.tipo_empaque_id">{{ tx(n.nombre || t('No type')) }} · {{ fmtNum(n.unidades) }}</option>
          </Seleccion></label>
      </template>
      <p v-else-if="p.unidad === 'BULTO'" class="ayuda">{{ t('The packages come from the packing lists of the PO; the PO plan is compared with what was declared.') }}</p>
      <p v-else class="ayuda">{{ t('These labels do not depend on packages. Kits and prepacks show their components in tables of the design.') }}</p>
      <h3>{{ t('Planned (PO) vs declared (packing list)') }}</h3>
      <p v-if="!validado" class="ayuda">{{ t('Check the job to compare the casepack and inner pack of the PO with each package.') }}</p>
      <p v-else-if="!deEmpaque.length" class="ayuda ok-txt"><Icono nombre="check" :tam="14" /> {{ t('No differences between what was planned and what was declared.') }}</p>
      <ul v-else class="tj-problemas">
        <li v-for="(x, i) in deEmpaque.slice(0, 200)" :key="i" :class="x.nivel"><Icono :nombre="NIVEL_ICONO[x.nivel]" :tam="14" />
          <b>{{ x.referencia }}</b> {{ tx(x.mensaje) }}</li>
      </ul>
      <button v-if="trabajo" type="button" class="btn" :disabled="ocupado" @click="guardar(true).then((ok) => ok && validar())">{{ t('Check packaging') }}</button>
    </section>

    <!-- 4. Reglas y diseños -->
    <section v-else-if="paso === 3" class="panel tj-bloque">
      <div class="tj-chips">
        <span v-for="d in disenos" :key="d.plantilla_id" class="chip">{{ tx(d.plantilla) }} · {{ t('{0} labels', [fmtNum(d.etiquetas)]) }}</span>
      </div>
      <table class="tabla tj-tabla">
        <thead><tr><th>{{ t('Labeled record') }}</th><th>{{ t('Design') }}</th><th>{{ t('Why') }}</th><th class="num">{{ t('Labels') }}</th></tr></thead>
        <tbody><tr v-for="r in registros" :key="r.id">
          <td>{{ r.referencia }}</td>
          <td>
            <template v-if="r.plantilla">{{ tx(r.plantilla) }} <span class="ayuda">v{{ r.version }}</span></template>
            <Seleccion v-else-if="candidatas(r)" :model-value="''" :aria-label="t('Choose the design')" @update:model-value="(v) => elegirDiseno(r, v)">
              <option value="">{{ t('Choose…') }}</option>
              <option v-for="pl in plantillas" :key="pl.id" :value="pl.id">{{ tx(pl.nombre) }}</option>
            </Seleccion>
            <span v-else class="etiqueta error ms-0">{{ t('No design') }}</span>
          </td>
          <td class="ayuda">{{ tx(r.motivo || '') }}</td>
          <td class="num">{{ fmtNum(r.cantidad) }}</td>
        </tr></tbody>
      </table>
      <details class="tj-forzar">
        <summary>{{ t('Use one design for the whole job (exception)') }}</summary>
        <div class="tj-fila">
          <label class="campo"><span>{{ t('Design') }}</span>
            <Seleccion v-model="p.plantilla_id"><option value="">{{ t('By rules (recommended)') }}</option>
              <option v-for="pl in plantillas" :key="pl.id" :value="pl.id">{{ tx(pl.nombre) }}</option></Seleccion></label>
          <label class="campo"><span :class="{ req: p.plantilla_id }">{{ t('Reason') }}</span>
            <input v-model="p.motivo_diseno" maxlength="200" :required="!!p.plantilla_id" /></label>
        </div>
        <p class="ayuda">{{ t('The rules are skipped for this job and the reason stays in each record.') }}</p>
      </details>
    </section>

    <!-- 5. Vista previa -->
    <section v-else-if="paso === 4" class="tj-previa">
      <div class="panel">
        <label class="campo"><span>{{ t('Labeled record') }}</span>
          <Seleccion :model-value="registroPrevia" @update:model-value="(id) => verPrevia(registros.find((r) => r.id === Number(id)))">
            <option v-for="r in registros.filter((x) => x.plantilla_id)" :key="r.id" :value="r.id">{{ r.referencia }} · {{ tx(r.plantilla) }}</option>
          </Seleccion></label>
        <div v-if="previa" class="tj-svg" v-html="previa.svg"></div>
        <p v-else class="ayuda">{{ t('Choose a record with a design.') }}</p>
      </div>
      <aside v-if="previa" class="panel">
        <h3>{{ tx(previa.plantilla) }} · v{{ previa.version }}</h3>
        <p class="ayuda">{{ tx(previa.motivo || '') }}</p>
        <dl class="tj-valores">
          <template v-for="(v, k) in previa.valores" :key="k"><dt>{{ k }}</dt><dd>{{ v ?? '—' }}
            <span v-if="previa.procedencia[k]" class="etiqueta info ms-0">{{ t('from {0}', [previa.procedencia[k]]) }}</span></dd></template>
        </dl>
      </aside>
    </section>

    <!-- 6. Errores -->
    <section v-else-if="paso === 5" class="panel tj-bloque">
      <div v-if="trabajo?.resumen?.problemas?.length" class="tj-problemas">
        <p v-for="(x, i) in trabajo.resumen.problemas" :key="i" class="error"><Icono nombre="alerta" :tam="14" /> {{ tx(x.mensaje) }}</p>
      </div>
      <div v-if="variables.length" class="tj-fila">
        <label v-for="v in variables" :key="v.clave" class="campo"><span :class="{ req: v.obligatorio }">{{ tx(v.etiqueta) }}</span>
          <input v-model="p.manuales[v.clave]" :placeholder="v.defecto || ''" maxlength="200" /></label>
      </div>
      <div class="tj-fila">
        <Seleccion v-model="filtroNivel" :aria-label="t('Show')"><option value="">{{ t('Everything') }}</option>
          <option value="error">{{ t('Errors') }}</option><option value="advertencia">{{ t('Warnings') }}</option><option value="info">{{ t('Information') }}</option></Seleccion>
        <span class="ayuda">{{ trabajo?.resumen?.verificacion === 'lector' ? t('Codes read back with a scanner on a sample per design.') : t('No scanner on the server: codes validated, not read back.') }}</span>
      </div>
      <p v-if="!problemas.length" class="ok-txt"><Icono nombre="check" :tam="14" /> {{ t('No problems: everything is ready to generate.') }}</p>
      <div v-for="[cat, lista] in porCategoria" :key="cat" class="tj-categoria">
        <h3>{{ tx(CATEGORIAS()[cat] || cat) }} <span class="ayuda">({{ lista.length }})</span></h3>
        <ul class="tj-problemas">
          <li v-for="(x, i) in lista.slice(0, 100)" :key="i" :class="x.nivel"><Icono :nombre="NIVEL_ICONO[x.nivel]" :tam="14" />
            <b>{{ x.referencia }}</b> {{ tx(x.mensaje) }}</li>
        </ul>
      </div>
    </section>

    <!-- 7. Generar -->
    <section v-else-if="paso === 6" class="panel tj-bloque">
      <p>{{ t('{0} records ready ({1} labels).', [pendientes.length, fmtNum(etiquetasPendientes)]) }}
        <span v-if="conteo.ERROR">{{ t('{0} with errors stay pending.', [conteo.ERROR]) }}</span></p>
      <div class="tj-fila">
        <label class="campo"><span>{{ t('File of each run') }}</span>
          <Seleccion v-model="p.formato"><option value="PDF">PDF</option><option value="ZIP">{{ t('ZIP (PDF, PNG and SVG)') }}</option></Seleccion></label>
        <label class="campo"><span>{{ t('Files inside the job ZIP') }}</span>
          <Seleccion v-model="p.zip.contenido"><option value="PDF">{{ t('PDF per folder') }}</option><option value="PNG">{{ t('PNG per label') }}</option>
            <option value="SVG">{{ t('SVG per label') }}</option></Seleccion></label>
      </div>
      <fieldset class="tj-carpetas"><legend>{{ t('Folders in the ZIP (in this order)') }}</legend>
        <label v-for="[c, txt] in CARPETAS()" :key="c" class="check"><input type="checkbox" :checked="p.zip.carpetas.includes(c)" @change="alternarCarpeta(c)" />
          {{ tx(txt) }}<span v-if="p.zip.carpetas.includes(c)" class="ayuda"> ({{ p.zip.carpetas.indexOf(c) + 1 }})</span></label>
      </fieldset>
      <label class="campo"><span>{{ t('File names') }}</span>
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
      <button type="button" class="btn btn-primario" :disabled="ocupado || !pendientes.length || trabajo?.estado === 'EN_PROCESO'" @click="generar">
        <Icono nombre="etiqueta" :tam="16" />{{ t('Generate {0} labels', [fmtNum(etiquetasPendientes)]) }}</button>
    </section>

    <!-- 8. Descargas -->
    <section v-else-if="paso === 7" class="panel tj-bloque">
      <div class="tj-fila">
        <button type="button" class="btn btn-primario" :disabled="!trabajo?.ejecuciones?.length" @click="descargarTodo()"><Icono nombre="descargar" :tam="16" />{{ t('Download the job ZIP') }}</button>
        <button v-if="trabajo?.estado === 'PARCIAL'" type="button" class="btn" @click="ir(5)"><Icono nombre="rehacer" :tam="16" />{{ t('Fix and generate the pending ones') }}</button>
      </div>
      <table class="tabla tj-tabla">
        <thead><tr><th>#</th><th>{{ t('PO') }}</th><th class="num">{{ t('Labels') }}</th><th>{{ t('Status') }}</th><th>{{ t('Date') }}</th><th></th></tr></thead>
        <tbody><tr v-for="e in trabajo?.ejecuciones || []" :key="e.id">
          <td>{{ e.id }}</td><td>{{ e.oc || '—' }}</td><td class="num">{{ fmtNum(e.total) }}</td>
          <td><EstadoBadge :estado="e.situacion" tipo="ejecucion" />
            <span v-if="e.impresa_en" class="ayuda"> {{ e.impresa_por }} · {{ e.impresion?.cantidad }}/{{ e.total }}</span></td>
          <td class="ayuda">{{ new Date(e.creada_en).toLocaleString() }}</td>
          <td class="tj-acciones">
            <button type="button" class="btn btn-chico" @click="descargarEjecucion(e)"><Icono nombre="descargar" :tam="14" />{{ t('Download') }}</button>
            <button v-if="!e.impresa_en" type="button" class="btn btn-chico" :disabled="!e.descargas"
                    :title="e.descargas ? '' : t('Download it before confirming the printing')"
                    @click="impresion = { id: e.id, total: e.total, cantidad: e.total, impresora: '', observacion: '', confirmo: false }">{{ t('Confirm printing') }}</button>
          </td>
        </tr></tbody>
      </table>
      <p class="ayuda">{{ t('Generated, downloaded and printed are different: printed is recorded only when someone confirms it.') }}</p>
    </section>
  </Asistente>

  <Modal v-if="impresion" :titulo="t('Confirm printing')" @cerrar="impresion = null">
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
.tj-origenes { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 10px; margin-bottom: 14px; }
.tj-origen { display: flex; flex-direction: column; gap: 4px; text-align: start; border: 1px solid var(--linea); border-radius: 10px; padding: 12px;
  background: var(--superficie); font: inherit; color: var(--tinta); cursor: pointer; min-height: 44px; }
.tj-origen span { color: var(--tinta-3); font-size: 0.85rem; }
.tj-origen[aria-checked='true'] { border-color: var(--acento); background: var(--acento-claro); }
.tj-origen:disabled:not([aria-checked='true']) { opacity: 0.5; cursor: default; }
.tj-chips { display: flex; gap: 6px; flex-wrap: wrap; align-items: center; }
.chip { display: inline-flex; align-items: center; gap: 4px; border: 1px solid var(--linea); border-radius: 16px; padding: 2px 4px 2px 10px; font-size: 0.85rem; }
.tj-tabla { width: 100%; }
.tj-tabla .num { text-align: end; }
.tj-num { width: 80px; text-align: end; }
.tj-oc h3 { margin: 8px 0 4px; font-size: 0.95rem; }
.tj-problemas { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 4px; }
.tj-problemas li, .tj-problemas p { display: flex; gap: 6px; align-items: baseline; font-size: 0.88rem; margin: 0; }
.tj-problemas .error { color: var(--error); }
.tj-problemas .advertencia { color: var(--aviso); }
.tj-categoria h3 { margin: 10px 0 4px; font-size: 0.95rem; }
.tj-previa { display: grid; grid-template-columns: minmax(0, 1fr) 340px; gap: 16px; align-items: start; }
.tj-svg { margin-top: 12px; background: var(--papel); border: 1px dashed var(--linea); padding: 12px; overflow: auto; }
.tj-svg :deep(svg) { max-width: 100%; height: auto; box-shadow: 0 1px 4px rgba(0, 0, 0, 0.15); background: #fff; }
.tj-valores { display: grid; grid-template-columns: auto 1fr; gap: 4px 10px; font-size: 0.84rem; margin: 0; }
.tj-valores dt { color: var(--tinta-3); font-family: var(--mono, monospace); }
.tj-valores dd { margin: 0; overflow-wrap: anywhere; }
.tj-carpetas { border: 1px solid var(--linea); border-radius: 8px; display: flex; gap: 14px; flex-wrap: wrap; padding: 8px 12px; }
.tj-avance { position: relative; height: 22px; border-radius: 6px; background: var(--linea-suave); overflow: hidden; }
.tj-avance > div { height: 100%; background: var(--acento); transition: width 0.3s; }
.tj-avance > span { position: absolute; inset: 0; display: grid; place-items: center; font-size: 0.8rem; }
.tj-acciones { display: flex; gap: 6px; flex-wrap: wrap; }
.ok-txt { color: var(--ok); }
tr.apagada > td { opacity: 0.55; }
@media (max-width: 900px) { .tj-previa { grid-template-columns: 1fr; } }
</style>
