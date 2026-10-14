<script setup>
import { t, tx } from '@/i18n/index.js'
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '@/nucleo/api'
import EstadoBadge from '@/componentes/EstadoBadge.vue'
import Icono from '@/componentes/Icono.vue'
import Modal from '@/componentes/Modal.vue'
import Pasos from '@/componentes/Pasos.vue'
import Seleccion from '@/componentes/Seleccion.vue'
import SelectBusqueda from '@/componentes/SelectBusqueda.vue'
import { fmtNum } from '@/nucleo/utils'
import { puede } from '@/stores/sesion'
import { avisar, errorApi } from '@/stores/ui'
import { MODALIDADES, UNIDADES, UNIDADES_DE, textoModalidad } from '@/modulos/etiquetado/etiquetas.js'
import { buscarArticulos, buscarOrdenes } from '@/modulos/etiquetado/componentes/buscadores.js'

// Generar etiquetas: 1) de dónde salen los datos (una OC o artículos sueltos),
// 2) qué se etiqueta y cuántas, 3) revisar el plan del servidor (qué diseño y
// versión usa cada grupo y por qué, problemas, vista previa con datos reales),
// 4) formato y generar. El lote queda en el historial y se puede volver a
// descargar idéntico.
const route = useRoute()
const router = useRouter()
const paso = ref(0)
const p = reactive({
  origen: route.query.articulo ? 'articulos' : 'oc',
  oc_id: route.query.oc ? Number(route.query.oc) : '',
  modalidad: 'OC_ARTICULO',
  unidad: 'LINEA',
  posiciones: [],
  cantidades: {},
  articulos: route.query.articulo ? [{ articulo_id: Number(route.query.articulo), cantidad: 1, sku: '' }] : [],
  plantilla_id: '',
  elegidas: {},
  formato: 'PDF',
  manuales: {},
  prueba: false,
  aceptar: false,
})
const resumen = ref(null)
const plan = ref(null)
const resultado = ref(null)
const cargando = ref(false)
const plantillas = ref([])

const pasos = computed(() => [t('Origin'), t('What to label'), t('Review'), t('Generate')].map((titulo, i) => ({
  titulo, estado: i < paso.value ? 'hecho' : i === paso.value ? (i === 2 && plan.value?.errores ? 'alerta' : 'actual') : 'pendiente',
})))

// ---- 1. Origen ----------------------------------------------------------------------------
async function cargarOc(id) {
  resumen.value = null
  plan.value = null
  if (!id) return
  try {
    resumen.value = await api.get(`/etiquetas/oc/${id}`)
    p.posiciones = resumen.value.lineas.filter((l) => !l.bloqueada).map((l) => l.id)
    p.cantidades = Object.fromEntries(resumen.value.lineas.map((l) => [String(l.id), Math.ceil(l.cantidad || 0)]))
  } catch (e) {
    errorApi(e)
  }
}
watch(() => p.oc_id, cargarOc)
watch(() => p.origen, (o) => {
  p.modalidad = o === 'articulos' ? 'ARTICULO' : 'OC_ARTICULO'
  plan.value = null
})
watch(() => p.modalidad, (m) => {
  if (!UNIDADES_DE[m].includes(p.unidad)) p.unidad = UNIDADES_DE[m][0]
  p.plantilla_id = ''
  p.elegidas = {}
  api.get('/etiquetas/plantillas', { modalidad: m, size: 200 }).then((r) => (plantillas.value = r.items.filter((x) => x.vigente))).catch(() => {})
}, { immediate: true })
const listoOrigen = computed(() => (p.origen === 'oc' ? !!resumen.value : p.articulos.length > 0))

// Artículos sueltos
const nuevoArticulo = ref('')
async function agregarArticulo(id) {
  if (!id || p.articulos.some((a) => a.articulo_id === id)) return
  p.articulos.push({ articulo_id: id, cantidad: 1 })
  nuevoArticulo.value = ''
}
const etiquetaArticulo = ref({})
async function nombreArticulo(id) {
  if (etiquetaArticulo.value[id]) return
  try {
    const r = await api.get('/etiquetas/articulos', { ids: String(id), size: 1 })
    const a = r.items.find((x) => x.id === id)
    if (a) etiquetaArticulo.value = { ...etiquetaArticulo.value, [id]: `${a.sku} · ${a.descripcion || ''}` }
  } catch { /* solo un nombre para mostrar */ }
}
watch(() => p.articulos.map((a) => a.articulo_id), (ids) => ids.forEach(nombreArticulo), { immediate: true })

// ---- 2. Qué se etiqueta ---------------------------------------------------------------------
const MODOS_OC = computed(() => MODALIDADES().filter(([m]) => m !== 'ARTICULO'))
const lineas = computed(() => resumen.value?.lineas || [])
const todas = computed({
  get: () => lineas.value.length > 0 && p.posiciones.length === lineas.value.length,
  set: (v) => (p.posiciones = v ? lineas.value.map((l) => l.id) : []),
})
const porLinea = computed(() => p.modalidad === 'OC_ARTICULO' || (p.modalidad === 'OC' && p.unidad === 'BULTO'))
const estimado = computed(() => {
  if (p.origen === 'articulos') return p.articulos.reduce((s, a) => s + (Number(a.cantidad) || 0), 0)
  if (p.modalidad === 'OC') return p.unidad === 'BULTO' ? resumen.value?.bultos || 0 : Number(p.cantidades.oc ?? 1)
  const elegidas = lineas.value.filter((l) => p.posiciones.includes(l.id))
  if (p.unidad === 'LINEA') return elegidas.length
  if (p.unidad === 'UNIDAD') return elegidas.reduce((s, l) => s + Math.ceil(l.cantidad || 0), 0)
  if (p.unidad === 'MANUAL') return elegidas.reduce((s, l) => s + (Number(p.cantidades[String(l.id)]) || 0), 0)
  return null // por bulto: lo calcula el servidor
})

// ---- 3. Plan ---------------------------------------------------------------------------------
function pedido(extra = {}) {
  const r = { modalidad: p.modalidad, unidad: p.unidad, prueba: p.prueba, elegidas: p.elegidas, plantilla_id: p.plantilla_id || null,
    manuales: p.manuales, ...extra }
  if (p.origen === 'oc') {
    r.oc_id = p.oc_id
    if (p.modalidad === 'OC_ARTICULO' || p.unidad === 'BULTO') r.posiciones = p.posiciones
    r.cantidades = p.unidad === 'MANUAL' ? p.cantidades : undefined
  } else r.articulos = p.articulos.map((a) => ({ articulo_id: a.articulo_id, cantidad: Number(a.cantidad) || 0 }))
  return r
}
async function revisar() {
  cargando.value = true
  try {
    plan.value = await api.post('/etiquetas/plan', pedido())
    for (const v of plan.value.variables || []) if (!(v.clave in p.manuales)) p.manuales[v.clave] = v.defecto || ''
    paso.value = plan.value.puede_generar ? 3 : 2
  } catch (e) {
    errorApi(e)
  } finally {
    cargando.value = false
  }
}
function elegir(g, plantillaId) {
  const clave = g.articulo_id ? `a${g.articulo_id}` : 'oc'
  p.elegidas = { ...p.elegidas, [clave]: Number(plantillaId) }
  revisar()
}
const filtroPlan = ref('todos')
const gruposVisibles = computed(() => (plan.value?.grupos || []).filter((g) => filtroPlan.value === 'todos'
  || (filtroPlan.value === 'problemas' && g.problemas.length) || (filtroPlan.value === 'errores' && g.problemas.some((x) => x.nivel === 'error'))))
const resumenDisenos = computed(() => {
  const r = {}
  for (const g of plan.value?.grupos || []) {
    if (!g.plantilla) continue
    const k = `${g.plantilla} v${g.version}`
    r[k] = (r[k] || 0) + g.cantidad
  }
  return Object.entries(r)
})

// Vista previa de un grupo con sus datos reales y la versión que se usará
const previa = ref(null)
async function verPrevia(g) {
  try {
    const r = await api.post('/etiquetas/vista-previa', { version_id: g.version_id, oc_id: plan.value.oc_id || undefined,
      articulo_id: g.articulo_id || undefined, posicion_id: g.posicion_id || undefined, bulto: g.bulto || undefined, prueba: p.prueba })
    previa.value = { g, ...r }
  } catch (e) {
    errorApi(e)
  }
}

// ---- 4. Generar --------------------------------------------------------------------------------
async function generar() {
  cargando.value = true
  try {
    resultado.value = await api.post('/etiquetas/generaciones', { ...pedido(), formato: p.formato, aceptar_advertencias: p.aceptar })
    avisar(t('Batch #{0} generated: {1} labels.', [resultado.value.id, resultado.value.total]))
    await descargar(p.formato)
  } catch (e) {
    if (e.codigo === 'confirmar_advertencias') avisar(t('Check the warnings and confirm them to generate.'), 'error')
    else errorApi(e)
  } finally {
    cargando.value = false
  }
}
async function descargar(formato) {
  try {
    await api.descargar(`/etiquetas/generaciones/${resultado.value.id}/archivo`, `labels-${resultado.value.id}`, { formato })
  } catch (e) {
    errorApi(e)
  }
}
function otraVez() {
  resultado.value = null
  plan.value = null
  p.aceptar = false
  paso.value = 0
  if (p.oc_id) cargarOc(p.oc_id)
}
const FORMATOS = computed(() => [
  ['PDF', t('For printing: one label per page or several per sheet, as the design says')],
  ['PNG', t('Images at the design resolution (in a ZIP if there are several)')],
  ['SVG', t('Vector files to edit or send (in a ZIP if there are several)')],
  ['ZIP', t('PDF, PNG and the batch data together')],
])
onMounted(() => {
  if (p.oc_id) cargarOc(p.oc_id)
})
const irOrden = () => router.push(`/ordenes/${p.oc_id}`)
</script>

<template>
  <div class="pagina-cabeza">
    <div>
      <h1>{{ t('Generate labels') }}</h1>
      <p>{{ t('Each label uses the approved version of the design that applies to it; the batch is kept and can be downloaded again exactly the same.') }}</p>
    </div>
    <div class="acciones">
      <button v-if="p.oc_id && resumen" type="button" class="btn" @click="irOrden"><Icono nombre="ordenes" />{{ t('Back to the PO') }}</button>
      <router-link class="btn" to="/etiquetas?vista=historial"><Icono nombre="historial" />{{ t('Generated labels') }}</router-link>
    </div>
  </div>

  <Pasos :pasos="pasos" class="gen-pasos" />

  <!-- Resultado -->
  <section v-if="resultado" class="panel gen-panel">
    <div class="gen-listo">
      <Icono nombre="check" :tam="28" />
      <div>
        <h2>{{ t('Batch #{0} ready', [resultado.id]) }}</h2>
        <p>{{ t('{0} labels · {1}', [fmtNum(resultado.total), resultado.formato]) }} · <EstadoBadge :estado="resultado.estado" tipo="lote" /></p>
        <p class="ayuda">{{ t('The download started. You can download it again in any format; it is drawn with the same versions and values.') }}</p>
      </div>
    </div>
    <div class="gen-botones">
      <button v-for="f in ['PDF', 'PNG', 'SVG', 'ZIP']" :key="f" type="button" class="btn" :class="{ 'btn-primario': f === resultado.formato }" @click="descargar(f)">
        <Icono nombre="descargar" :tam="15" />{{ f }}</button>
      <span class="crece" />
      <button type="button" class="btn" @click="otraVez">{{ t('Generate other labels') }}</button>
      <router-link class="btn" to="/etiquetas?vista=historial">{{ t('See history') }}</router-link>
    </div>
  </section>

  <!-- 1. Origen -->
  <section v-else-if="paso === 0" class="panel gen-panel">
    <h2>{{ t('Where does the data come from?') }}</h2>
    <div class="gen-opciones">
      <button type="button" class="gen-opcion" :aria-pressed="p.origen === 'oc'" @click="p.origen = 'oc'">
        <Icono nombre="ordenes" :tam="22" /><strong>{{ t('A purchase order') }}</strong>
        <span>{{ t('Labels for its lines, units or packages, with the PO data.') }}</span></button>
      <button type="button" class="gen-opcion" :aria-pressed="p.origen === 'articulos'" @click="p.origen = 'articulos'">
        <Icono nombre="etiqueta" :tam="22" /><strong>{{ t('Items without a PO') }}</strong>
        <span>{{ t('Product labels with item data only (price tags, hang tags…).') }}</span></button>
    </div>
    <template v-if="p.origen === 'oc'">
      <label class="campo gen-campo"><span>{{ t('Purchase order') }}</span>
        <SelectBusqueda v-model="p.oc_id" :buscar="buscarOrdenes" :etiqueta="t('PO')" :vacio="t('Choose a PO')"
                        :opciones="resumen ? [{ valor: resumen.oc.id, texto: resumen.oc.numero, sub: resumen.oc.proveedor }] : []" /></label>
      <div v-if="resumen" class="gen-oc">
        <p><strong>{{ resumen.oc.numero }}</strong> · {{ resumen.oc.proveedor }} · <EstadoBadge :estado="resumen.oc.estado" tipo="oc" /></p>
        <p class="ayuda">{{ t('{0} lines · {1} packages in packing lists', [resumen.lineas.length, resumen.bultos]) }}
          <template v-if="resumen.generaciones"> · <router-link :to="`/etiquetas?vista=historial&oc_id=${resumen.oc.id}`" class="enlace">{{ t('{0} batches already generated', [resumen.generaciones]) }}</router-link></template></p>
      </div>
    </template>
    <template v-else>
      <label class="campo gen-campo"><span>{{ t('Add item') }}</span>
        <SelectBusqueda v-model="nuevoArticulo" :buscar="buscarArticulos" :etiqueta="t('Item')" :vacio="t('Search SKU, style, color or UPC')" @change="agregarArticulo" /></label>
      <table v-if="p.articulos.length" class="tabla mt">
        <thead><tr><th>{{ t('Item') }}</th><th class="num">{{ t('Labels') }}</th><th /></tr></thead>
        <tbody>
          <tr v-for="(a, i) in p.articulos" :key="a.articulo_id">
            <td>{{ etiquetaArticulo[a.articulo_id] || `#${a.articulo_id}` }}</td>
            <td class="num"><input v-model.number="a.cantidad" type="number" min="1" max="5000" class="gen-cant" :aria-label="t('Labels')" /></td>
            <td class="num"><button type="button" class="btn btn-icono btn-chico" :aria-label="t('Remove')" @click="p.articulos.splice(i, 1)"><Icono nombre="basura" :tam="15" /></button></td>
          </tr>
        </tbody>
      </table>
    </template>
    <div class="gen-pie">
      <span class="crece" />
      <button type="button" class="btn btn-primario" :disabled="!listoOrigen" @click="paso = 1">{{ t('Next') }}<Icono nombre="derecha" :tam="16" /></button>
    </div>
  </section>

  <!-- 2. Qué se etiqueta -->
  <section v-else-if="paso === 1" class="panel gen-panel">
    <h2>{{ t('What to label') }}</h2>
    <div class="rejilla-gen">
      <label v-if="p.origen === 'oc'" class="campo"><span>{{ t('Data on the label') }}</span>
        <Seleccion v-model="p.modalidad" :aria-label="t('Data on the label')">
          <option v-for="[m, txt] in MODOS_OC" :key="m" :value="m">{{ txt }}</option>
        </Seleccion>
      </label>
      <label class="campo"><span>{{ t('One label for each…') }}</span>
        <Seleccion v-model="p.unidad" :aria-label="t('One label for each…')">
          <option v-for="u in UNIDADES_DE[p.modalidad]" :key="u" :value="u">{{ UNIDADES()[u] }}</option>
        </Seleccion>
      </label>
      <label class="campo"><span>{{ t('Design') }}</span>
        <Seleccion v-model="p.plantilla_id" :aria-label="t('Design')">
          <option value="">{{ t('The one that applies to each item (recommended)') }}</option>
          <option v-for="x in plantillas" :key="x.id" :value="x.id">{{ tx(x.nombre) }} · v{{ x.vigente.numero }}</option>
        </Seleccion>
      </label>
      <label v-if="p.origen === 'oc' && p.modalidad === 'OC' && p.unidad !== 'BULTO'" class="campo"><span>{{ t('How many labels') }}</span>
        <input v-model.number="p.cantidades.oc" type="number" min="1" max="5000" /></label>
    </div>
    <p class="ayuda">{{ textoModalidad(p.modalidad) }}: {{ MODALIDADES().find((m) => m[0] === p.modalidad)?.[2] }}
      <template v-if="p.unidad === 'BULTO' && resumen && !resumen.bultos"><br /><span class="texto-error">{{ t('This PO has no packing list with packages yet: label by line or by order.') }}</span></template></p>

    <div v-if="p.origen === 'oc' && porLinea" class="tabla-marco mt">
      <table class="tabla">
        <thead><tr>
          <th class="col-check"><input v-model="todas" type="checkbox" :aria-label="t('All lines')" /></th>
          <th>{{ t('Line') }}</th><th>{{ t('Item') }}</th><th>{{ t('Labeling family') }}</th><th>{{ t('Design that applies') }}</th>
          <th class="num">{{ t('Quantity') }}</th><th v-if="p.unidad === 'MANUAL'" class="num">{{ t('Labels') }}</th>
        </tr></thead>
        <tbody>
          <tr v-for="l in lineas" :key="l.id" :class="{ apagada: l.bloqueada }">
            <td class="col-check"><input v-model="p.posiciones" type="checkbox" :value="l.id" :aria-label="t('Line {0}', [l.posicion])" /></td>
            <td>{{ l.posicion }}</td>
            <td><strong class="codigo">{{ l.codigo }}</strong><span class="sub">{{ [l.descripcion, l.color, l.talla].filter(Boolean).join(' · ') }}</span></td>
            <td><span v-if="l.familia" class="etiqueta ms-0">{{ tx(l.familia) }}</span><span v-else class="etiqueta aviso ms-0">{{ t('Without family') }}</span></td>
            <td>
              <template v-if="l.plantilla.plantilla">{{ tx(l.plantilla.plantilla) }} <span class="etiqueta ms-0">v{{ l.plantilla.version }}</span><span class="sub">{{ tx(l.plantilla.motivo || '') }}</span></template>
              <span v-else-if="l.plantilla.ambigua" class="texto-aviso">{{ t('Several apply: you choose in the review') }}</span>
              <span v-else class="texto-error">{{ t('No approved design applies') }}</span>
            </td>
            <td class="num">{{ fmtNum(l.cantidad) }} {{ l.unidad }}</td>
            <td v-if="p.unidad === 'MANUAL'" class="num"><input v-model.number="p.cantidades[String(l.id)]" type="number" min="0" max="5000" class="gen-cant" :aria-label="t('Labels')" /></td>
          </tr>
        </tbody>
      </table>
    </div>
    <div class="gen-pie">
      <button type="button" class="btn" @click="paso = 0"><Icono nombre="atras" :tam="16" />{{ t('Back') }}</button>
      <span class="crece" />
      <span v-if="estimado != null" class="ayuda">{{ t('About {0} labels', [fmtNum(estimado)]) }}</span>
      <button type="button" class="btn btn-primario" :disabled="cargando || (porLinea && p.origen === 'oc' && !p.posiciones.length)" @click="revisar">{{ t('Review') }}<Icono nombre="derecha" :tam="16" /></button>
    </div>
  </section>

  <!-- 3 y 4. Revisar y generar -->
  <template v-else-if="plan && paso >= 2">
    <section class="panel gen-panel">
      <div class="gen-cifras">
        <div><span>{{ t('Labels') }}</span><strong>{{ fmtNum(plan.total) }}</strong></div>
        <div><span>{{ t('Groups') }}</span><strong>{{ fmtNum(plan.grupos.length) }}</strong></div>
        <div :class="{ error: plan.errores }"><span>{{ t('Errors') }}</span><strong>{{ plan.errores }}</strong></div>
        <div :class="{ aviso: plan.advertencias }"><span>{{ t('Warnings') }}</span><strong>{{ plan.advertencias }}</strong></div>
        <div class="gen-disenos"><span>{{ t('Designs and versions') }}</span>
          <p v-for="[d, n] in resumenDisenos" :key="d">{{ tx(d) }} · {{ t('{0} labels', [fmtNum(n)]) }}</p>
          <p v-if="!resumenDisenos.length" class="ayuda">—</p></div>
      </div>
      <p v-for="(x, i) in plan.problemas" :key="i" class="texto-error">{{ tx(x.mensaje) }}</p>
      <div v-if="plan.variables?.length" class="gen-manuales">
        <strong>{{ t('Fields written when generating') }}</strong>
        <div class="gen-manuales-campos">
          <label v-for="v in plan.variables" :key="v.clave" class="campo"><span :class="{ req: v.obligatorio }">{{ v.etiqueta }}</span>
            <input v-model="p.manuales[v.clave]" maxlength="200" :placeholder="v.defecto || ''" /></label>
        </div>
        <button type="button" class="btn btn-chico" :disabled="cargando" @click="revisar">{{ t('Apply and review again') }}</button>
      </div>
      <div class="gen-filtro segmentos" role="group" :aria-label="t('Show')">
        <button v-for="[v, txt] in [['todos', t('All')], ['problemas', t('With problems')], ['errores', t('With errors')]]" :key="v" type="button" class="segmento"
                :aria-pressed="filtroPlan === v" @click="filtroPlan = v">{{ txt }}</button>
      </div>
      <div class="tabla-marco">
        <table class="tabla">
          <thead><tr><th>{{ t('Origin') }}</th><th class="num">{{ t('Labels') }}</th><th>{{ t('Design and version') }}</th><th>{{ t('Why') }}</th><th>{{ t('Problems') }}</th><th /></tr></thead>
          <tbody>
            <tr v-for="g in gruposVisibles" :key="g.clave">
              <td>{{ g.referencia }}<span v-if="g.familia" class="sub">{{ tx(g.familia) }}</span></td>
              <td class="num">{{ fmtNum(g.cantidad) }}</td>
              <td>
                <template v-if="g.plantilla">{{ tx(g.plantilla) }} <span class="etiqueta ms-0">v{{ g.version }}</span>
                  <EstadoBadge v-if="g.version_estado !== 'APROBADA'" :estado="g.version_estado" tipo="etiqueta" /></template>
                <Seleccion v-else-if="g.candidatas.length" :model-value="''" :aria-label="t('Choose the design')" @change="(v) => elegir(g, v)">
                  <option value="">{{ t('Choose the design…') }}</option>
                  <option v-for="c in g.candidatas" :key="c.plantilla_id" :value="c.plantilla_id">{{ tx(c.plantilla) }}</option>
                </Seleccion>
                <span v-else class="texto-error">{{ t('None') }}</span>
              </td>
              <td class="ayuda">{{ tx(g.motivo || '') }}</td>
              <td>
                <p v-for="(x, i) in g.problemas" :key="i" class="gen-problema" :class="x.nivel">
                  <Icono :nombre="x.nivel === 'error' ? 'alerta' : 'info'" :tam="14" />{{ tx(x.mensaje) }}</p>
                <span v-if="!g.problemas.length" class="gen-ok"><Icono nombre="check" :tam="14" />{{ t('OK') }}</span>
              </td>
              <td class="num"><button v-if="g.version_id" type="button" class="btn btn-chico" @click="verPrevia(g)"><Icono nombre="ojo" :tam="15" />{{ t('See') }}</button></td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <section class="panel gen-panel">
      <h2>{{ t('Format') }}</h2>
      <div class="gen-opciones formatos">
        <button v-for="[f, d] in FORMATOS" :key="f" type="button" class="gen-opcion" :aria-pressed="p.formato === f" @click="p.formato = f">
          <strong>{{ f }}</strong><span>{{ d }}</span></button>
      </div>
      <label v-if="puede('etiquetas.disenar')" class="check-linea"><input v-model="p.prueba" type="checkbox" @change="revisar" />
        {{ t('Test print with the latest version (even if not approved): marked as a test and not counted as generated') }}</label>
      <label v-if="plan.advertencias" class="check-linea aviso"><input v-model="p.aceptar" type="checkbox" />
        {{ t('I reviewed the {0} warnings and want to generate anyway', [plan.advertencias]) }}</label>
      <div class="gen-pie">
        <button type="button" class="btn" @click="paso = 1"><Icono nombre="atras" :tam="16" />{{ t('Back') }}</button>
        <button type="button" class="btn" :disabled="cargando" @click="revisar">{{ t('Review again') }}</button>
        <span class="crece" />
        <span v-if="plan.errores" class="texto-error">{{ t('Fix the errors to generate: assign a design, approve it or complete the data.') }}</span>
        <button type="button" class="btn btn-primario" :disabled="cargando || !plan.puede_generar || (plan.advertencias > 0 && !p.aceptar)" @click="generar">
          <Icono nombre="descargar" :tam="16" />{{ t('Generate {0} labels', [fmtNum(plan.total)]) }}</button>
      </div>
    </section>
  </template>

  <Modal v-if="previa" :titulo="previa.g.referencia" ancho="640px" @cerrar="previa = null">
    <!-- eslint-disable-next-line vue/no-v-html -->
    <div class="gen-previa" v-html="previa.svg" />
    <p class="ayuda">{{ tx(previa.g.plantilla) }} v{{ previa.g.version }} · {{ t('With real data') }}</p>
    <ul v-if="previa.problemas.length" class="gen-lista">
      <li v-for="(x, i) in previa.problemas" :key="i" :class="x.nivel"><strong v-if="x.nombre">{{ x.nombre }}: </strong>{{ tx(x.mensaje) }}</li>
    </ul>
  </Modal>
</template>

<style scoped>
.gen-pasos { margin: 4px 0 16px; }
.gen-panel { display: flex; flex-direction: column; gap: 12px; margin-bottom: 16px; }
.gen-panel h2 { margin: 0; font-size: 1.05rem; }
.gen-opciones { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 10px; }
.gen-opciones.formatos { grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); }
.gen-opcion { display: flex; flex-direction: column; gap: 4px; align-items: flex-start; text-align: left; padding: 14px; border: 1.5px solid var(--linea);
  border-radius: 12px; background: var(--superficie); cursor: pointer; color: var(--tinta-2); }
.gen-opcion span { font-size: 0.8rem; color: var(--tinta-3); }
.gen-opcion strong { color: var(--tinta); }
.gen-opcion[aria-pressed='true'] { border-color: var(--acento); background: var(--acento-claro); color: var(--acento-texto); }
.gen-campo { max-width: 460px; }
.gen-oc p { margin: 0; }
.rejilla-gen { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; }
.gen-cant { width: 90px; text-align: right; }
.col-check { width: 36px; }
.apagada { opacity: 0.55; }
.gen-pie { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; border-top: 1px solid var(--linea-suave); padding-top: 12px; }
.gen-cifras { display: grid; grid-template-columns: repeat(4, minmax(100px, 0.6fr)) minmax(220px, 2fr); gap: 10px; }
.gen-cifras > div { border: 1px solid var(--linea); border-radius: 10px; padding: 10px 12px; display: flex; flex-direction: column; gap: 2px; }
.gen-cifras span { font-size: 0.74rem; color: var(--tinta-3); text-transform: uppercase; letter-spacing: 0.04em; }
.gen-cifras strong { font-size: 1.4rem; }
.gen-cifras .error strong { color: var(--error); }
.gen-cifras .aviso strong { color: var(--aviso); }
.gen-disenos p { margin: 2px 0 0; font-size: 0.84rem; }
.gen-filtro { align-self: flex-start; }
.gen-manuales { border: 1px solid var(--linea); border-radius: 10px; padding: 12px; display: flex; flex-direction: column; gap: 8px; }
.gen-manuales-campos { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 10px; }
.gen-problema { display: flex; gap: 5px; align-items: flex-start; margin: 0 0 3px; font-size: 0.8rem; color: var(--aviso); }
.gen-problema.error { color: var(--error); }
.gen-problema svg { flex: none; margin-top: 2px; }
.gen-ok { display: inline-flex; gap: 4px; align-items: center; color: var(--ok); font-size: 0.8rem; }
.check-linea { display: flex; gap: 8px; align-items: flex-start; font-size: 0.86rem; }
.check-linea.aviso { color: var(--aviso); }
.gen-listo { display: flex; gap: 14px; align-items: flex-start; color: var(--ok); }
.gen-listo h2, .gen-listo p { color: var(--tinta); margin: 0 0 4px; }
.gen-botones { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.gen-previa { display: flex; justify-content: center; padding: 14px; background: repeating-conic-gradient(#eef1f5 0 25%, #fff 0 50%) 0 0 / 14px 14px; border-radius: 8px; }
.gen-previa :deep(svg) { max-width: 100%; height: auto; max-height: 420px; box-shadow: 0 1px 3px rgba(16, 24, 40, 0.25); }
.gen-lista { margin: 8px 0 0; padding-left: 18px; font-size: 0.82rem; }
.gen-lista .error { color: var(--error); }
.gen-lista .advertencia { color: var(--aviso); }
.texto-aviso { color: var(--aviso); font-size: 0.82rem; }
@media (max-width: 900px) { .gen-cifras { grid-template-columns: repeat(2, 1fr); } .gen-disenos { grid-column: 1 / -1; } }
</style>
