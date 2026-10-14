<script setup>
import { t, tx } from '@/i18n/index.js'
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '@/nucleo/api'
import EstadoBadge from '@/componentes/EstadoBadge.vue'
import Icono from '@/componentes/Icono.vue'
import Paginacion from '@/componentes/Paginacion.vue'
import Pasos from '@/componentes/Pasos.vue'
import Seleccion from '@/componentes/Seleccion.vue'
import SelectBusqueda from '@/componentes/SelectBusqueda.vue'
import { fmtFecha, fmtNum } from '@/nucleo/utils'
import { avisar, errorApi } from '@/stores/ui'

// Generación masiva paso a paso: 1) qué se etiqueta (órdenes de compra,
// artículos o una lista de empaque), 2) cuáles (las de una familia, todas las
// del filtro de una vez), 3) con qué diseño, 4) los datos que se escriben al
// generar y la revisión del servidor (problemas por OC, avisos de datos que
// quedarán vacíos), 5) generar y descargar: una etiqueta por página, un PDF
// por OC en un ZIP, un solo PDF de artículos o las imágenes en un ZIP.
const route = useRoute()
const paso = ref(0)
const f = reactive({
  tipo: route.query.pl ? 'packing' : route.query.tipo || (route.query.familia ? 'ordenes' : ''),
  familia_id: route.query.familia ? Number(route.query.familia) : '',
  q: '',
  oc_ids: [],
  articulo_ids: [],
  cantidad: 1,
  pl_id: route.query.pl ? Number(route.query.pl) : '',
  tipo_empaque_id: '',
  plantilla_id: '',
  manuales: {},
  formato: 'PDF',
  omitir: false,
  aceptar: false,
})
const familias = ref([])
onMounted(() => api.get('/etiquetas/familias', { activas: true }).then((r) => (familias.value = r)).catch(() => {}))

const TIPOS = computed(() => [
  ['ordenes', 'ordenes', t('Purchase orders'), t('One PDF per PO with one label per different item (or one per PO). Choose the POs of a family all at once.')],
  ['articulos', 'etiqueta', t('Items'), t('One PDF with one label per page, or the images in a ZIP. Choose the items of a family all at once.')],
  ['packing', 'caja', t('Packing list'), t('One label per pallet, carton, inner or the packaging level you choose, with its contents.')],
])
const pasos = computed(() => [t('What to label'), t('Choose'), t('Design'), t('Review'), t('Generate')].map((titulo, i) => ({
  titulo, estado: i < paso.value ? 'hecho' : i === paso.value ? (i === 3 && plan.value?.errores ? 'alerta' : 'actual') : 'pendiente',
})))
function elegirTipo(tipo) {
  f.tipo = tipo
  f.plantilla_id = ''
  plan.value = null
  paso.value = 1
}

// ---- 2. Elegir -------------------------------------------------------------------------------------
const lista = ref({ items: [], total: 0 })
const pagina = ref(1)
const cargando = ref(false)
async function cargarLista() {
  if (f.tipo !== 'ordenes' && f.tipo !== 'articulos') return
  cargando.value = true
  try {
    lista.value = f.tipo === 'ordenes'
      ? await api.get('/etiquetas/masivo/ordenes', { familia_id: f.familia_id || undefined, q: f.q || undefined, page: pagina.value, size: 25 })
      : await api.get('/etiquetas/articulos', { familia: f.familia_id || undefined, q: f.q || undefined, page: pagina.value, size: 25 })
  } catch (e) {
    errorApi(e)
  } finally {
    cargando.value = false
  }
}
let espera
watch(() => [f.tipo, f.familia_id], () => {
  pagina.value = 1
  cargarLista()
}, { immediate: true })
watch(() => f.q, () => {
  clearTimeout(espera)
  espera = setTimeout(() => {
    pagina.value = 1
    cargarLista()
  }, 300)
})
watch(pagina, cargarLista)
const elegidos = computed({
  get: () => (f.tipo === 'ordenes' ? f.oc_ids : f.articulo_ids),
  set: (v) => (f.tipo === 'ordenes' ? (f.oc_ids = v) : (f.articulo_ids = v)),
})
const paginaElegida = computed({
  get: () => lista.value.items.length > 0 && lista.value.items.every((x) => elegidos.value.includes(x.id)),
  set: (v) => {
    const ids = lista.value.items.map((x) => x.id)
    elegidos.value = v ? [...new Set([...elegidos.value, ...ids])] : elegidos.value.filter((id) => !ids.includes(id))
  },
})
async function elegirTodos() {
  try {
    const r = f.tipo === 'ordenes'
      ? await api.get('/etiquetas/masivo/ordenes', { familia_id: f.familia_id || undefined, q: f.q || undefined, solo_ids: true })
      : await api.get('/etiquetas/articulos', { familia: f.familia_id || undefined, q: f.q || undefined, solo_ids: true })
    elegidos.value = [...new Set([...elegidos.value, ...r.ids])]
    avisar(t('{0} chosen.', [fmtNum(elegidos.value.length)]))
  } catch (e) {
    errorApi(e)
  }
}
const quitarTodos = () => (elegidos.value = [])

// Lista de empaque y su nivel
const pl = ref(null)
async function buscarPl(q) {
  const r = await api.get('/etiquetas/masivo/packing', { q })
  return r.map((x) => ({ valor: x.id, texto: x.numero, sub: [x.factura, x.proveedor, x.estado].filter(Boolean).join(' · ') }))
}
watch(() => f.pl_id, async (id) => {
  pl.value = null
  f.tipo_empaque_id = ''
  if (!id) return
  try {
    pl.value = await api.get(`/etiquetas/masivo/packing/${id}`)
    const sup = pl.value.niveles.find((n) => n.superior)
    f.tipo_empaque_id = sup?.tipo_empaque_id ?? ''
  } catch (e) {
    errorApi(e)
  }
}, { immediate: true })
const listoElegir = computed(() => (f.tipo === 'packing' ? !!pl.value && (pl.value.niveles.length || pl.value.superiores) : elegidos.value.length > 0))

// ---- 3. Diseño --------------------------------------------------------------------------------------
const plantillas = ref([])
const MODOS = { ordenes: ['OC', 'OC_ARTICULO'], articulos: ['ARTICULO'], packing: ['OC', 'OC_ARTICULO'] }
watch(paso, async (p) => {
  if (p !== 2) return
  try {
    const r = await api.get('/etiquetas/plantillas', { size: 200 })
    plantillas.value = r.items.filter((x) => x.vigente && MODOS[f.tipo].includes(x.modalidad))
  } catch (e) {
    errorApi(e)
  }
})
const queRepresenta = (p) => ({
  ordenes: p.modalidad === 'OC' ? t('One label per PO') : t('One label per different item of each PO (repeated lines count once)'),
  articulos: t('{0} labels per item', [f.cantidad || 1]),
  packing: p.modalidad === 'OC' ? t('One label per package with the PO data') : t('One label per package with the PO and item data'),
})[f.tipo]

// ---- 4. Revisión -----------------------------------------------------------------------------------
const plan = ref(null)
function pedido(extra = {}) {
  const r = { tipo: f.tipo, plantilla_id: f.plantilla_id, manuales: f.manuales, ...extra }
  if (f.tipo === 'ordenes') Object.assign(r, { oc_ids: f.oc_ids, familia_id: f.familia_id || null })
  if (f.tipo === 'articulos') Object.assign(r, { articulo_ids: f.articulo_ids, cantidad: f.cantidad })
  if (f.tipo === 'packing') Object.assign(r, { pl_id: f.pl_id, tipo_empaque_id: f.tipo_empaque_id || null })
  return r
}
const revisando = ref(false)
async function revisar() {
  revisando.value = true
  try {
    plan.value = await api.post('/etiquetas/masivo/plan', pedido())
    for (const v of plan.value.plantilla.variables || []) if (!(v.clave in f.manuales)) f.manuales[v.clave] = v.defecto || ''
    paso.value = 3
  } catch (e) {
    errorApi(e)
  } finally {
    revisando.value = false
  }
}
const abierta = ref(null)
const partesVisibles = computed(() => (plan.value?.partes || []))
const sinListaEmpaque = computed(() => (plan.value?.partes || []).some((x) => x.problemas.some((q) => q.mensaje.includes('packing list data'))))
const puede = computed(() => plan.value && plan.value.puede_generar && (!plan.value.con_errores || f.omitir || plan.value.con_errores === 0)
  && (!plan.value.advertencias || f.aceptar))
const FORMATOS = computed(() => [
  ['PDF', f.tipo === 'ordenes' ? t('One PDF per PO (in a ZIP), one label per page with the size of the design') : t('One PDF, one label per page with the size of the design')],
  ['PNG', t('One image per label, all in a ZIP')],
])

// ---- 5. Generar -------------------------------------------------------------------------------------
const resultado = ref(null)
const generando = ref(false)
async function generar() {
  generando.value = true
  try {
    resultado.value = await api.post('/etiquetas/masivo', pedido({ formato: f.formato, omitir_con_errores: f.omitir, aceptar_advertencias: f.aceptar }))
    paso.value = 4
    avisar(t('{0} labels generated.', [fmtNum(resultado.value.total)]))
    await descargar(f.formato)
  } catch (e) {
    errorApi(e)
  } finally {
    generando.value = false
  }
}
async function descargar(formato) {
  try {
    await api.descargar(`/etiquetas/masivo/${resultado.value.lote}/archivo`, `labels-${resultado.value.lote.slice(0, 8)}`, { formato })
  } catch (e) {
    errorApi(e)
  }
}
function otraVez() {
  resultado.value = null
  plan.value = null
  f.oc_ids = []
  f.articulo_ids = []
  f.aceptar = false
  f.omitir = false
  paso.value = 0
}
const nombreFamilia = computed(() => familias.value.find((x) => x.id === f.familia_id)?.nombre)
</script>

<template>
  <div class="pagina-cabeza">
    <div>
      <h1>{{ t('Bulk label generation') }}</h1>
      <p>{{ t('Labels for many purchase orders, items or packages at once, one label per page, with the approved version of the design you choose.') }}</p>
    </div>
    <div class="acciones">
      <router-link class="btn" to="/etiquetas/generar"><Icono nombre="ordenes" />{{ t('One PO') }}</router-link>
      <router-link class="btn" to="/etiquetas?vista=historial"><Icono nombre="historial" />{{ t('Generated labels') }}</router-link>
    </div>
  </div>
  <Pasos :pasos="pasos" class="gm-pasos" />

  <!-- 1. Qué etiquetar -->
  <section v-if="paso === 0" class="panel gm-panel">
    <h2>{{ t('What do you want to label?') }}</h2>
    <div class="gm-opciones">
      <button v-for="[v, icono, titulo, desc] in TIPOS" :key="v" type="button" class="gm-opcion" :aria-pressed="f.tipo === v" @click="elegirTipo(v)">
        <Icono :nombre="icono" :tam="24" /><strong>{{ titulo }}</strong><span>{{ desc }}</span>
      </button>
    </div>
  </section>

  <!-- 2. Elegir -->
  <section v-else-if="paso === 1" class="panel gm-panel">
    <h2>{{ f.tipo === 'ordenes' ? t('Choose the purchase orders') : f.tipo === 'articulos' ? t('Choose the items') : t('Choose the packing list and the packaging level') }}</h2>
    <template v-if="f.tipo !== 'packing'">
      <div class="gm-filtros">
        <label class="campo"><span>{{ t('Labeling family') }}</span>
          <Seleccion v-model="f.familia_id" :aria-label="t('Labeling family')">
            <option value="">{{ f.tipo === 'ordenes' ? t('Any family (all POs)') : t('Any family') }}</option>
            <option v-for="x in familias" :key="x.id" :value="x.id">{{ tx(x.nombre) }} · {{ t('{0} items', [fmtNum(x.articulos)]) }}</option>
          </Seleccion>
        </label>
        <label class="buscador gm-buscar"><Icono nombre="buscar" :tam="16" />
          <input v-model="f.q" type="search" :placeholder="f.tipo === 'ordenes' ? t('Search PO number') : t('Search SKU, style, color or UPC')" :aria-label="t('Search')" /></label>
      </div>
      <div class="gm-barra">
        <span><strong>{{ fmtNum(elegidos.length) }}</strong> {{ t('chosen') }} · {{ t('{0} in the filter', [fmtNum(lista.total)]) }}</span>
        <button type="button" class="btn btn-chico" :disabled="!lista.total" @click="elegirTodos">{{ t('Choose all {0} of the filter', [fmtNum(lista.total)]) }}</button>
        <button v-if="elegidos.length" type="button" class="btn btn-chico btn-texto" @click="quitarTodos">{{ t('Clear selection') }}</button>
      </div>
      <div class="tabla-marco">
        <table class="tabla">
          <thead v-if="f.tipo === 'ordenes'"><tr>
            <th class="col-check"><input v-model="paginaElegida" type="checkbox" :aria-label="t('This page')" /></th>
            <th>{{ t('PO') }}</th><th>{{ t('Supplier') }}</th><th>{{ t('Status') }}</th><th>{{ t('Date') }}</th>
            <th class="num">{{ nombreFamilia ? t('Lines of the family') : t('Lines') }}</th><th class="num">{{ t('Different items') }}</th>
            <th class="num">{{ t('Packages') }}</th><th class="num">{{ t('Batches') }}</th>
          </tr></thead>
          <thead v-else><tr>
            <th class="col-check"><input v-model="paginaElegida" type="checkbox" :aria-label="t('This page')" /></th>
            <th>{{ t('SKU') }}</th><th>{{ t('Description') }}</th><th>{{ t('Color') }}</th><th>{{ t('Size') }}</th><th>{{ t('Labeling family') }}</th>
          </tr></thead>
          <tbody>
            <tr v-for="x in lista.items" :key="x.id" class="gm-fila" @click="elegidos = elegidos.includes(x.id) ? elegidos.filter((i) => i !== x.id) : [...elegidos, x.id]">
              <td class="col-check"><input v-model="elegidos" type="checkbox" :value="x.id" :aria-label="x.numero || x.sku" @click.stop /></td>
              <template v-if="f.tipo === 'ordenes'">
                <td><strong class="codigo">{{ x.numero }}</strong></td><td>{{ x.proveedor }}</td><td><EstadoBadge :estado="x.estado" tipo="oc" /></td>
                <td>{{ fmtFecha(x.fecha) }}</td><td class="num">{{ fmtNum(x.lineas) }}</td><td class="num">{{ fmtNum(x.articulos) }}</td>
                <td class="num">{{ x.bultos ? fmtNum(x.bultos) : '—' }}</td>
                <td class="num"><span v-if="x.generaciones" class="etiqueta aviso ms-0" :title="t('Labels were already generated for this PO')">{{ x.generaciones }}</span><span v-else class="apagado">—</span></td>
              </template>
              <template v-else>
                <td><strong class="codigo">{{ x.sku }}</strong><span class="sub">{{ x.estilo }}</span></td><td>{{ x.descripcion }}</td><td>{{ x.color }}</td><td>{{ x.talla }}</td>
                <td><span v-if="x.familia" class="etiqueta ms-0">{{ tx(x.familia) }}</span><span v-else class="etiqueta aviso ms-0">{{ t('Without family') }}</span></td>
              </template>
            </tr>
            <tr v-if="!lista.items.length && !cargando"><td colspan="9" class="apagado">{{ f.tipo === 'ordenes' ? t('No purchase order has items of this family.') : t('No items match these filters.') }}</td></tr>
          </tbody>
        </table>
      </div>
      <Paginacion v-if="lista.total > 25" :page="pagina" :size="25" :total="lista.total" :tamanos="[25]" @cambiar="(n) => (pagina = n)" />
      <label v-if="f.tipo === 'articulos'" class="campo gm-cantidad"><span>{{ t('Labels per item') }}</span>
        <input v-model.number="f.cantidad" type="number" min="1" max="500" /></label>
    </template>
    <template v-else>
      <label class="campo gm-pl"><span>{{ t('Packing list') }}</span>
        <SelectBusqueda v-model="f.pl_id" :buscar="buscarPl" :etiqueta="t('Packing list')" :vacio="t('Search packing list or invoice')"
                       :opciones="pl ? [{ valor: pl.id, texto: pl.numero, sub: pl.factura }] : []" /></label>
      <div v-if="pl" class="gm-niveles">
        <p class="ayuda">{{ t('{0} · invoice {1} · {2}', [pl.numero, pl.factura || '—', pl.proveedor || '—']) }}</p>
        <button v-for="n in pl.niveles" :key="n.tipo_empaque_id ?? 'x'" type="button" class="gm-opcion gm-nivel" :aria-pressed="f.tipo_empaque_id === (n.tipo_empaque_id ?? '')"
                @click="f.tipo_empaque_id = n.tipo_empaque_id ?? ''">
          <Icono nombre="caja" :tam="20" /><strong>{{ tx(n.nombre || t('Package')) }}</strong>
          <span>{{ t('{0} labels', [fmtNum(n.unidades)]) }}<template v-if="n.superior"> · {{ t('outer packaging') }}</template></span>
        </button>
        <p v-if="!pl.niveles.length" class="texto-error">{{ t('This packing list has no packages yet.') }}</p>
      </div>
    </template>
    <div class="gm-pie">
      <button type="button" class="btn" @click="paso = 0"><Icono nombre="atras" :tam="16" />{{ t('Back') }}</button>
      <span class="crece" />
      <button type="button" class="btn btn-primario" :disabled="!listoElegir" @click="paso = 2">{{ t('Next') }}<Icono nombre="derecha" :tam="16" /></button>
    </div>
  </section>

  <!-- 3. Diseño -->
  <section v-else-if="paso === 2" class="panel gm-panel">
    <h2>{{ t('Which label design?') }}</h2>
    <p class="ayuda">{{ t('Only approved designs that fit what you are labeling. Every label uses the version in use.') }}</p>
    <div class="gm-disenos">
      <button v-for="p in plantillas" :key="p.id" type="button" class="gm-diseno" :aria-pressed="f.plantilla_id === p.id" @click="f.plantilla_id = p.id">
        <img :src="`/api/etiquetas/versiones/${p.vigente.id}/miniatura.svg`" :alt="p.nombre" />
        <strong>{{ tx(p.nombre) }} <span class="etiqueta ms-0">v{{ p.vigente.numero }}</span></strong>
        <span>{{ fmtNum(p.vigente.ancho_mm, 1) }} × {{ fmtNum(p.vigente.alto_mm, 1) }} mm<template v-if="p.familia"> · {{ tx(p.familia) }}</template></span>
        <span class="gm-repr">{{ queRepresenta(p) }}</span>
      </button>
      <p v-if="!plantillas.length" class="apagado">{{ t('There is no approved design for this. Create one in Labels → Designs and approve it.') }}</p>
    </div>
    <div class="gm-pie">
      <button type="button" class="btn" @click="paso = 1"><Icono nombre="atras" :tam="16" />{{ t('Back') }}</button>
      <span class="crece" />
      <button type="button" class="btn btn-primario" :disabled="!f.plantilla_id || revisando" @click="revisar">{{ t('Review') }}<Icono nombre="derecha" :tam="16" /></button>
    </div>
  </section>

  <!-- 4. Revisión, datos y formato -->
  <template v-else-if="paso === 3 && plan">
    <section class="panel gm-panel">
      <div class="gm-cifras">
        <div><span>{{ t('Labels') }}</span><strong>{{ fmtNum(plan.total) }}</strong></div>
        <div><span>{{ f.tipo === 'ordenes' ? t('Purchase orders') : t('Files') }}</span><strong>{{ fmtNum(plan.partes.length) }}</strong></div>
        <div :class="{ error: plan.errores }"><span>{{ t('With errors') }}</span><strong>{{ plan.con_errores }}</strong></div>
        <div :class="{ aviso: plan.advertencias }"><span>{{ t('Warnings') }}</span><strong>{{ plan.advertencias }}</strong></div>
        <div class="gm-diseno-elegido"><span>{{ t('Design') }}</span>
          <p>{{ tx(plan.plantilla.nombre) }} v{{ plan.plantilla.version }} · {{ fmtNum(plan.plantilla.ancho_mm, 1) }} × {{ fmtNum(plan.plantilla.alto_mm, 1) }} mm</p></div>
      </div>
      <p v-if="sinListaEmpaque" class="nota aviso"><Icono nombre="alerta" :tam="16" />
        {{ t('This design uses packing list data, and some labels have no packing list: those fields will be empty. You can continue anyway.') }}</p>
      <p v-for="(x, i) in plan.problemas" :key="i" class="texto-error">{{ tx(x.mensaje) }}</p>

      <div v-if="plan.plantilla.variables?.length" class="gm-manuales">
        <h3>{{ t('Fields written when generating') }}</h3>
        <div class="gm-manuales-campos">
          <label v-for="v in plan.plantilla.variables" :key="v.clave" class="campo"><span :class="{ req: v.obligatorio }">{{ v.etiqueta }}</span>
            <input v-model="f.manuales[v.clave]" maxlength="200" :placeholder="v.defecto || ''" /></label>
        </div>
        <button type="button" class="btn btn-chico" :disabled="revisando" @click="revisar">{{ t('Apply and review again') }}</button>
      </div>

      <div class="tabla-marco">
        <table class="tabla">
          <thead><tr><th>{{ f.tipo === 'ordenes' ? t('PO') : t('Batch') }}</th><th class="num">{{ t('Labels') }}</th><th>{{ t('Problems') }}</th><th /></tr></thead>
          <tbody>
            <template v-for="(x, i) in partesVisibles" :key="i">
              <tr>
                <td><strong class="codigo">{{ x.oc || (f.tipo === 'packing' ? pl?.numero : t('Items')) }}</strong></td>
                <td class="num">{{ fmtNum(x.total) }}</td>
                <td>
                  <span v-if="x.errores" class="gm-problema error"><Icono nombre="alerta" :tam="14" />{{ t('{0} errors', [x.errores]) }}</span>
                  <span v-if="x.advertencias" class="gm-problema"><Icono nombre="info" :tam="14" />{{ x.advertencias === 1 ? t('1 warning') : t('{0} warnings', [x.advertencias]) }}</span>
                  <span v-if="!x.errores && !x.advertencias" class="gm-ok"><Icono nombre="check" :tam="14" />{{ t('OK') }}</span>
                </td>
                <td class="num"><button v-if="x.problemas.length || x.grupos.length" type="button" class="btn btn-chico btn-texto" @click="abierta = abierta === i ? null : i">{{ abierta === i ? t('Hide') : t('See') }}</button></td>
              </tr>
              <tr v-if="abierta === i" class="gm-detalle">
                <td colspan="4">
                  <p v-for="(q, j) in x.problemas.slice(0, 30)" :key="`p${j}`" class="gm-problema" :class="q.nivel">
                    <Icono :nombre="q.nivel === 'error' ? 'alerta' : 'info'" :tam="14" /><span><strong v-if="q.referencia">{{ q.referencia }}: </strong>{{ tx(q.mensaje) }}</span></p>
                  <p class="ayuda">{{ x.grupos.slice(0, 40).map((g) => g.referencia).join(' · ') }}<template v-if="x.grupos.length > 40"> …</template></p>
                </td>
              </tr>
            </template>
          </tbody>
        </table>
      </div>
    </section>

    <section class="panel gm-panel">
      <h2>{{ t('Format') }}</h2>
      <div class="gm-opciones formatos">
        <button v-for="[v, d] in FORMATOS" :key="v" type="button" class="gm-opcion" :aria-pressed="f.formato === v" @click="f.formato = v"><strong>{{ v }}</strong><span>{{ d }}</span></button>
      </div>
      <label v-if="plan.con_errores && plan.con_errores < plan.partes.length" class="check-linea"><input v-model="f.omitir" type="checkbox" />
        {{ t('Generate the others and skip the {0} with errors', [plan.con_errores]) }}</label>
      <label v-if="plan.advertencias" class="check-linea aviso"><input v-model="f.aceptar" type="checkbox" />
        {{ t('I reviewed the {0} warnings and want to generate anyway', [plan.advertencias]) }}</label>
      <div class="gm-pie">
        <button type="button" class="btn" @click="paso = 2"><Icono nombre="atras" :tam="16" />{{ t('Back') }}</button>
        <span class="crece" />
        <button type="button" class="btn btn-primario" :disabled="!puede || generando" @click="generar"><Icono nombre="descargar" :tam="16" />{{ t('Generate {0} labels', [fmtNum(plan.total)]) }}</button>
      </div>
    </section>
  </template>

  <!-- 5. Resultado -->
  <section v-else-if="paso === 4 && resultado" class="panel gm-panel">
    <div class="gm-listo">
      <Icono nombre="check" :tam="28" />
      <div>
        <h2>{{ t('{0} labels ready', [fmtNum(resultado.total)]) }}</h2>
        <p>{{ resultado.generaciones.length > 1 ? t('{0} batches, one per PO, downloaded together in a ZIP.', [resultado.generaciones.length]) : t('One batch.') }}
          {{ t('The download started; you can download them again in the other format.') }}</p>
      </div>
    </div>
    <div class="gm-botones">
      <button v-for="x in ['PDF', 'PNG']" :key="x" type="button" class="btn" :class="{ 'btn-primario': x === resultado.formato }" @click="descargar(x)"><Icono nombre="descargar" :tam="15" />{{ x }}</button>
      <span class="crece" />
      <button type="button" class="btn" @click="otraVez">{{ t('Generate other labels') }}</button>
      <router-link class="btn" to="/etiquetas?vista=historial">{{ t('See history') }}</router-link>
    </div>
    <table v-if="resultado.generaciones.length > 1" class="tabla mt">
      <thead><tr><th>{{ t('PO') }}</th><th class="num">{{ t('Labels') }}</th><th>{{ t('Batch') }}</th></tr></thead>
      <tbody><tr v-for="g in resultado.generaciones" :key="g.id"><td>{{ g.oc }}</td><td class="num">{{ fmtNum(g.total) }}</td><td>#{{ g.id }}</td></tr></tbody>
    </table>
    <div v-if="resultado.omitidas.length" class="nota aviso mt"><Icono nombre="alerta" :tam="16" />
      <div>{{ t('Skipped because of errors:') }} {{ resultado.omitidas.map((x) => x.oc).join(', ') }}</div></div>
  </section>
</template>

<style scoped>
.gm-pasos { margin: 4px 0 16px; }
.gm-panel { display: flex; flex-direction: column; gap: 12px; margin-bottom: 16px; }
.gm-panel h2 { margin: 0; font-size: 1.05rem; }
.gm-panel h3 { margin: 0 0 6px; font-size: 0.92rem; }
.gm-opciones { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 10px; }
.gm-opcion { display: flex; flex-direction: column; gap: 4px; align-items: flex-start; text-align: left; padding: 16px; border: 1.5px solid var(--linea);
  border-radius: 12px; background: var(--superficie); cursor: pointer; color: var(--tinta-2); }
.gm-opcion span { font-size: 0.8rem; color: var(--tinta-3); }
.gm-opcion strong { color: var(--tinta); }
.gm-opcion[aria-pressed='true'] { border-color: var(--acento); background: var(--acento-claro); color: var(--acento-texto); }
.gm-filtros { display: flex; gap: 12px; flex-wrap: wrap; align-items: flex-end; }
.gm-filtros .campo { min-width: 260px; }
.gm-buscar { flex: 1; min-width: 220px; }
.gm-barra { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; font-size: 0.86rem; }
.gm-fila { cursor: pointer; }
.col-check { width: 36px; }
.gm-cantidad { max-width: 200px; }
.gm-pl { max-width: 460px; }
.gm-niveles { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 10px; }
.gm-niveles .ayuda { grid-column: 1 / -1; margin: 0; }
.gm-disenos { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 12px; }
.gm-diseno { display: flex; flex-direction: column; gap: 4px; text-align: left; padding: 12px; border: 1.5px solid var(--linea); border-radius: 12px; background: var(--superficie); cursor: pointer; }
.gm-diseno img { width: 100%; height: 120px; object-fit: contain; background: repeating-conic-gradient(#eef1f5 0 25%, #fff 0 50%) 0 0 / 12px 12px; border-radius: 8px; padding: 6px; box-sizing: border-box; }
.gm-diseno span { font-size: 0.78rem; color: var(--tinta-3); }
.gm-diseno .gm-repr { color: var(--tinta-2); }
.gm-diseno[aria-pressed='true'] { border-color: var(--acento); background: var(--acento-claro); }
.gm-pie { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; border-top: 1px solid var(--linea-suave); padding-top: 12px; }
.gm-cifras { display: grid; grid-template-columns: repeat(4, minmax(100px, 0.6fr)) minmax(220px, 2fr); gap: 10px; }
.gm-cifras > div { border: 1px solid var(--linea); border-radius: 10px; padding: 10px 12px; display: flex; flex-direction: column; gap: 2px; }
.gm-cifras span { font-size: 0.74rem; color: var(--tinta-3); text-transform: uppercase; letter-spacing: 0.04em; }
.gm-cifras strong { font-size: 1.4rem; }
.gm-cifras .error strong { color: var(--error); }
.gm-cifras .aviso strong { color: var(--aviso); }
.gm-diseno-elegido p { margin: 2px 0 0; font-size: 0.86rem; }
.gm-manuales { border: 1px solid var(--linea); border-radius: 10px; padding: 12px; }
.gm-manuales-campos { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 10px; margin-bottom: 8px; }
.gm-problema { display: inline-flex; gap: 5px; align-items: flex-start; margin: 0 10px 3px 0; font-size: 0.8rem; color: var(--aviso); }
.gm-problema.error { color: var(--error); }
.gm-ok { display: inline-flex; gap: 4px; align-items: center; color: var(--ok); font-size: 0.8rem; }
.gm-detalle td { background: var(--superficie-2); }
.gm-detalle .gm-problema { display: flex; }
.check-linea { display: flex; gap: 8px; align-items: flex-start; font-size: 0.86rem; }
.check-linea.aviso { color: var(--aviso); }
.gm-listo { display: flex; gap: 14px; align-items: flex-start; color: var(--ok); }
.gm-listo h2, .gm-listo p { color: var(--tinta); margin: 0 0 4px; }
.gm-botones { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
@media (max-width: 900px) { .gm-cifras { grid-template-columns: repeat(2, 1fr); } .gm-diseno-elegido { grid-column: 1 / -1; } }
</style>
