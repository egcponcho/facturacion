<script setup>
import { t, tx } from '@/i18n/index.js'
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue'
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router'
import { api } from '@/nucleo/api'
import BarraSeleccion from '@/componentes/BarraSeleccion.vue'
import Icono from '@/componentes/Icono.vue'
import Segmentos from '@/componentes/Segmentos.vue'
import Seleccion from '@/componentes/Seleccion.vue'
import TablaDatos from '@/componentes/TablaDatos.vue'
import { fmtFecha, textoVariante } from '@/nucleo/utils'
import { confirmar } from '@/stores/confirmar'
import { puede } from '@/stores/sesion'
import { avisar, errorApi } from '@/stores/ui'
import CabezaEtiquetado from '@/modulos/etiquetado/componentes/CabezaEtiquetado.vue'
import FormFamilia from '@/modulos/etiquetado/componentes/FormFamilia.vue'

// Asistente de una familia de etiquetado, en orden: 1 sus datos → 2 qué entra
// (productos, grupos o artículos sueltos) → 3 su diseño por tipo de etiqueta →
// 4 revisar. Nada cambia mientras se avanza: se termina de una vez (una sola
// operación en el servidor, todo o nada) o se deja como borrador personal para
// seguir después. /etiquetas/configuracion/familia/:id (id de la familia, o
// «nueva»/«nueva-<n>» para una que aún no existe).
const props = defineProps({ id: { type: String, required: true } })
const route = useRoute()
const router = useRouter()
const PASOS = () => [
  { titulo: t('Family data'), que: t('Code, name, whether it is a subfamily and the fields its items usually need.') },
  { titulo: t('What goes in it'), que: t('Choose products (all their sizes inherit the family), whole item groups or single items. You can search and choose across pages.') },
  { titulo: t('Its designs'), que: t('For each label type: inherit the design of the family above (or of the whole company), or use its own.') },
  { titulo: t('Review and finish'), que: t('Nothing has been applied yet. Finish to apply everything at once, or keep it as a draft.') },
]
const existente = computed(() => /^\d+$/.test(props.id))
const clave = ref(`etiquetas.familia.${props.id}`)
const e = reactive({
  paso: 0,
  familia: { codigo: '', nombre: '', descripcion: '', activa: true, campos: [], padre_id: route.query.padre ? Number(route.query.padre) : null },
  productos: [], grupos: [], articulos: [],
  nombres: { productos: {}, grupos: {}, articulos: {} }, // para mostrar lo elegido sin volver a consultarlo
  disenos: {}, // tipo_id -> plantilla_id (null: hereda)
})
const original = ref('')
const borrador = ref(null) // { actualizado } si se retomó o guardó uno
const listo = ref(false)
const ocupado = ref(false)
const familias = ref([])
const tipos = ref([])
const plantillas = ref([])
const matriz = ref(null)
const foto = () => JSON.stringify({ ...e, paso: 0 })
const cambiado = computed(() => listo.value && foto() !== original.value)

onMounted(async () => {
  try {
    const [fs, ts, ps, m, bs] = await Promise.all([api.get('/etiquetas/familias'), api.get('/etiquetas/tipos'), api.get('/etiquetas/plantillas', { size: 200 }),
      api.get('/etiquetas/matriz', { sujeto: 'ARTICULO' }), api.get('/perfil/borradores', { prefijo: clave.value })])
    familias.value = fs
    tipos.value = ts.filter((x) => x.sujeto === 'ARTICULO')
    plantillas.value = ps.items.filter((p) => p.vigente)
    matriz.value = m
    const f = existente.value ? fs.find((x) => String(x.id) === props.id) : null
    if (existente.value && !f) throw Object.assign(new Error(t('The labeling family does not exist.')), { status: 404 })
    if (f) {
      Object.assign(e.familia, { id: f.id, codigo: f.codigo, nombre: f.nombre, descripcion: f.descripcion || '', activa: f.activa,
        campos: (f.campos || []).map((c) => ({ ...c })), padre_id: f.padre_id || null, heredados: f.heredados })
      const fila = m.filas.find((x) => x.nivel === 'FAMILIA' && x.id === f.id)
      for (const tp of tipos.value) e.disenos[tp.id] = fila?.celdas[tp.id]?.normal?.plantilla_id || null
    } else for (const tp of tipos.value) e.disenos[tp.id] = null
    original.value = foto()
    const b = bs.find((x) => x.clave === clave.value)
    if (b) {
      Object.assign(e, b.datos)
      borrador.value = b
      original.value = foto() // lo del borrador ya está guardado
    }
  } catch (err) {
    errorApi(err)
  } finally {
    listo.value = true
  }
})

// ---- Paso 2: qué entra ---------------------------------------------------------------------------------
const que = ref('productos')
const origen = ref('sin') // sin familia · '' todas las demás
const q = ref('')
const tabla = ref(null)
const datos = ref({ items: [], total: 0 })
const grupos = ref([])
const cargando = ref(false)
let ultima = null
async function consultar(c = ultima) {
  if (que.value === 'grupos') return cargarGrupos()
  if (!c) return
  ultima = c
  cargando.value = true
  try {
    const r = await api.get(que.value === 'productos' ? '/etiquetas/productos' : '/etiquetas/articulos',
      { q: q.value || undefined, familia: origen.value || undefined, page: c.page, size: c.size })
    datos.value = { ...r, items: r.items.filter((x) => !e.familia.id || x.familia_id !== e.familia.id) }
  } catch (err) {
    errorApi(err)
  } finally {
    cargando.value = false
  }
}
async function cargarGrupos() {
  cargando.value = true
  try {
    const r = await api.get('/etiquetas/grupos-articulos', { q: q.value || undefined, familia: origen.value || undefined })
    grupos.value = r.filter((g) => !e.familia.id || g.familia_id !== e.familia.id)
  } catch (err) {
    errorApi(err)
  } finally {
    cargando.value = false
  }
}
async function recargar() {
  if (que.value === 'grupos') return cargarGrupos()
  await nextTick()
  if (tabla.value && tabla.value.pagina !== 1) tabla.value.pagina = 1
  else consultar()
}
let espera
watch(q, () => {
  clearTimeout(espera)
  espera = setTimeout(recargar, 300)
})
watch([que, origen], recargar)
watch(() => e.paso, (p) => p === 1 && que.value === 'grupos' && cargarGrupos())
// Lo elegido se guarda por clase (productos, grupos, artículos) y no se pierde al buscar o cambiar de página
const seleccion = computed({
  get: () => e[que.value],
  set: (ids) => {
    const filas = que.value === 'grupos' ? grupos.value : datos.value.items
    for (const x of filas) if (ids.includes(x.id)) e.nombres[que.value][x.id] = nombreDe(x)
    e[que.value] = ids
  },
})
const nombreDe = (x) => (que.value === 'productos' ? `${x.estilo} ${x.color || ''}`.trim() : que.value === 'grupos' ? `${x.codigo} · ${x.nombre}` : x.sku)
const columnas = computed(() => (que.value === 'productos' ? [
  { clave: 'estilo', texto: t('Product'), fija: true, prioridad: 1, ordenable: false, filtro: false },
  { clave: 'nombre', texto: t('Description'), prioridad: 2, ordenable: false, filtro: false },
  { clave: 'grupo', texto: t('Group'), prioridad: 3, ordenable: false, filtro: false },
  { clave: 'tallas', texto: t('Sizes'), num: true, prioridad: 3, ordenable: false, filtro: false },
  { clave: 'familia', texto: t('Labeling family'), prioridad: 1, ordenable: false, filtro: false },
] : que.value === 'articulos' ? [
  { clave: 'sku', texto: t('SKU'), fija: true, prioridad: 1, ordenable: false, filtro: false },
  { clave: 'descripcion', texto: t('Description'), prioridad: 2, ordenable: false, filtro: false },
  { clave: 'variante', texto: t('Variant'), valor: (x) => textoVariante(x), prioridad: 2, ordenable: false, filtro: false },
  { clave: 'familia', texto: t('Labeling family'), prioridad: 1, ordenable: false, filtro: false },
] : [
  { clave: 'codigo', texto: t('Group'), fija: true, prioridad: 1 },
  { clave: 'nombre', texto: t('Name'), prioridad: 1 },
  { clave: 'articulos', texto: t('Items'), num: true, prioridad: 2 },
  { clave: 'familia', texto: t('Labeling family'), prioridad: 1 },
]))
const elegidos = computed(() => e.productos.length + e.grupos.length + e.articulos.length)
function quitar(clase, id) {
  e[clase] = e[clase].filter((x) => x !== id)
}

// ---- Paso 3: diseños -----------------------------------------------------------------------------------
// Lo que heredaría cada tipo: lo de la familia madre (o su herencia) o lo de toda la empresa
function heredado(tp) {
  const filas = matriz.value?.filas || []
  const madre = e.familia.padre_id ? filas.find((x) => x.nivel === 'FAMILIA' && x.id === e.familia.padre_id) : filas.find((x) => x.nivel === 'GENERAL')
  const c = madre?.celdas[tp.id]
  const de = e.familia.padre_id ? tx(familias.value.find((x) => x.id === e.familia.padre_id)?.nombre || '') : t('Whole company')
  if (c?.normal) return { plantilla: c.normal.plantilla, de }
  if (c?.hereda) return { plantilla: c.hereda.plantilla, de: c.hereda.destino ? tx(c.hereda.destino) : t('Whole company') }
  return null
}
const disenosDe = (tp) => plantillas.value.filter((p) => p.tipo_etiqueta_id === tp.id)
const nombrePlantilla = (id) => plantillas.value.find((p) => p.id === id)?.nombre || ''
const configurar = computed(() => puede('etiquetas.configurar'))

// ---- Revisar -------------------------------------------------------------------------------------------
const faltan = computed(() => {
  const r = []
  if (!e.familia.codigo?.trim() || !e.familia.nombre?.trim()) r.push({ paso: 0, texto: t('Enter the code and the name.') })
  for (const tp of tipos.value) {
    if (tp.obligatoria && !e.disenos[tp.id] && !heredado(tp)) r.push({ paso: 2, texto: t('“{0}” is required and has no design to use.', [tx(tp.nombre)]) })
  }
  return r
})
const madre = computed(() => familias.value.find((x) => x.id === e.familia.padre_id))

// ---- Navegar, borrador y terminar ---------------------------------------------------------------------
function ir(p) {
  if (p === 1 && (!e.familia.codigo?.trim() || !e.familia.nombre?.trim())) {
    avisar(t('Enter the code and the name first.'), 'aviso')
    return
  }
  e.paso = p
  window.scrollTo({ top: 0 })
}
const titulo = computed(() => e.familia.nombre?.trim() || (existente.value ? '' : t('New family')))
async function guardarBorrador(salir = false) {
  ocupado.value = true
  try {
    if (!existente.value && props.id === 'nueva') clave.value = `etiquetas.familia.nueva-${Date.now()}`
    const r = await api.put(`/perfil/borradores/${clave.value}`, { titulo: titulo.value || t('New family'), datos: JSON.parse(JSON.stringify(e)) })
    borrador.value = r
    original.value = foto()
    avisar(t('Draft saved. Nothing was applied; continue it whenever you want from Setup.'))
    if (salir) router.push({ path: '/etiquetas/configuracion', query: { paso: 'familias' } })
    else if (props.id === 'nueva') router.replace(`/etiquetas/configuracion/familia/${clave.value.split('.')[2]}`)
  } catch (err) {
    errorApi(err)
  } finally {
    ocupado.value = false
  }
}
async function descartar() {
  if (borrador.value && !(await confirmar(t('Discard the draft? Nothing of it was applied.'), { titulo: t('Discard draft'), boton: t('Discard'), peligro: true }))) return
  try {
    if (borrador.value) await api.del(`/perfil/borradores/${clave.value}`)
    original.value = foto()
    borrador.value = null
    router.push({ path: '/etiquetas/configuracion', query: { paso: 'familias', familia: e.familia.id || undefined } })
  } catch (err) {
    errorApi(err)
  }
}
async function terminar() {
  ocupado.value = true
  const f = e.familia
  try {
    const r = await api.post('/etiquetas/familias/configurar', {
      familia: { id: f.id, codigo: f.codigo, nombre: f.nombre, descripcion: f.descripcion, activa: f.activa, campos: f.campos, padre_id: f.padre_id || null },
      productos: e.productos, grupos: e.grupos, articulos: e.articulos,
      disenos: configurar.value ? tipos.value.map((tp) => ({ tipo_etiqueta_id: tp.id, plantilla_id: e.disenos[tp.id] || null })) : [],
    })
    if (borrador.value) await api.del(`/perfil/borradores/${clave.value}`).catch(() => {})
    original.value = foto()
    borrador.value = null
    avisar(f.id ? t('Family “{0}” updated.', [r.familia.nombre]) : t('Family “{0}” created and set up.', [r.familia.nombre]))
    router.push({ path: '/etiquetas/configuracion', query: { paso: 'familias', familia: r.familia.id } })
  } catch (err) {
    errorApi(err)
  } finally {
    ocupado.value = false
  }
}
onBeforeRouteLeave(async (to) => {
  if (!cambiado.value || to.path.startsWith('/etiquetas/configuracion/familia/')) return true
  return confirmar(t('You have changes that are not applied nor saved as a draft. Leave anyway?'), { titulo: t('Leave the assistant'), boton: t('Leave'), peligro: true })
})
</script>

<template>
  <CabezaEtiquetado :titulo="existente ? t('Set up the family {0}', [titulo]) : t('New labeling family')"
                    :texto="t('Step by step; nothing is applied until you finish.')">
    <router-link :to="{ path: '/etiquetas/configuracion', query: { paso: 'familias', familia: e.familia.id || undefined } }" class="btn">
      <Icono nombre="atras" :tam="15" />{{ t('Back to setup') }}</router-link>
  </CabezaEtiquetado>

  <div v-if="!listo" class="vacio">{{ t('Loading…') }}</div>
  <div v-else class="af">
    <ol class="af-pasos">
      <li v-for="(p, i) in PASOS()" :key="i">
        <button type="button" class="af-paso" :class="{ actual: i === e.paso, hecho: i < e.paso }" :aria-current="i === e.paso ? 'step' : undefined" @click="ir(i)">
          <span class="af-num"><Icono v-if="i < e.paso" nombre="check" :tam="13" /><template v-else>{{ i + 1 }}</template></span>{{ p.titulo }}
        </button>
      </li>
    </ol>

    <p v-if="borrador" class="nota af-borrador"><Icono nombre="historial" :tam="16" />
      <span>{{ t('Draft saved on {0}: nothing of it is applied yet.', [fmtFecha(borrador.actualizado)]) }}</span>
      <button type="button" class="enlace" @click="descartar">{{ t('Discard draft') }}</button></p>

    <section class="panel af-cuerpo">
      <header class="af-cabeza">
        <p class="af-sup">{{ t('Step {0} of {1}', [e.paso + 1, PASOS().length]) }}</p>
        <h2>{{ PASOS()[e.paso].titulo }}</h2>
        <p class="ayuda">{{ PASOS()[e.paso].que }}</p>
      </header>

      <!-- 1. Datos -->
      <FormFamilia v-if="e.paso === 0" v-model="e.familia" :familias="familias" />

      <!-- 2. Qué entra -->
      <template v-else-if="e.paso === 1">
        <div class="af-barra">
          <Segmentos v-model="que" :opciones="[['productos', t('Products')], ['grupos', t('Item groups')], ['articulos', t('Items (sizes)')]]" :etiqueta="t('Show')" />
          <label class="buscador af-buscar"><Icono nombre="buscar" :tam="16" /><input v-model="q" type="search" :placeholder="t('Search')" :aria-label="t('Search')" /></label>
          <Segmentos v-model="origen" :opciones="[['sin', t('Without family')], ['', t('All the others')]]" :etiqueta="t('From')" />
        </div>
        <div v-if="elegidos" class="af-elegidos">
          <strong>{{ t('Chosen so far') }}</strong>
          <template v-for="clase in ['productos', 'grupos', 'articulos']" :key="clase">
            <span v-for="id in e[clase].slice(0, 12)" :key="`${clase}-${id}`" class="af-chip">{{ e.nombres[clase][id] || `#${id}` }}
              <button type="button" :aria-label="t('Remove')" @click="quitar(clase, id)"><Icono nombre="cerrar" :tam="12" /></button></span>
            <span v-if="e[clase].length > 12" class="ayuda">{{ t('and {0} more', [e[clase].length - 12]) }}</span>
          </template>
        </div>
        <TablaDatos v-if="que !== 'grupos'" :key="que" ref="tabla" :tabla="`etiquetas_asistente_${que}`" modo="servidor" :columnas="columnas" :filas="datos.items"
                    :total="datos.total" :cargando="cargando" seleccionable v-model:seleccion="seleccion" :etiqueta="PASOS()[1].titulo"
                    :externos="{ q, origen }" @consulta="consultar">
          <template #celda-estilo="{ fila: p }"><strong>{{ p.estilo }}</strong><span class="sub">{{ p.color }}</span></template>
          <template #celda-sku="{ fila: a }"><strong class="codigo">{{ a.sku }}</strong><span class="sub">{{ a.estilo }}</span></template>
          <template #celda-familia="{ fila: x }">
            <span v-if="x.familia" class="etiqueta ms-0">{{ tx(x.familia) }}</span><span v-else class="etiqueta aviso ms-0">{{ t('Without family') }}</span></template>
          <template #vacio>{{ t('Nothing to add here: everything already has a family.') }}</template>
        </TablaDatos>
        <TablaDatos v-else tabla="etiquetas_asistente_grupos" :columnas="columnas" :filas="grupos" :cargando="cargando" seleccionable v-model:seleccion="seleccion"
                    :etiqueta="t('Item groups')">
          <template #celda-codigo="{ fila: g }"><strong class="codigo">{{ g.codigo }}</strong></template>
          <template #celda-familia="{ fila: g }"><span v-if="g.familia" class="etiqueta ms-0">{{ tx(g.familia) }}</span><span v-else class="etiqueta aviso ms-0">{{ t('Without family') }}</span></template>
          <template #vacio>{{ t('Nothing here.') }}</template>
        </TablaDatos>
      </template>

      <!-- 3. Diseños -->
      <template v-else-if="e.paso === 2">
        <p v-if="!configurar" class="nota aviso"><Icono nombre="info" :tam="16" />{{ t('You cannot assign designs: the family will inherit them. Someone with the setup permission can change it later.') }}</p>
        <div class="af-disenos">
          <article v-for="tp in tipos" :key="tp.id" class="af-tipo">
            <div class="af-tipo-nombre"><strong>{{ tx(tp.nombre) }}</strong>
              <span v-if="tp.obligatoria" class="etiqueta aviso ms-0">{{ t('Required') }}</span></div>
            <label class="af-opcion"><input v-model="e.disenos[tp.id]" type="radio" :value="null" :disabled="!configurar" />
              <span>{{ t('Inherit') }}<small class="ayuda">{{ heredado(tp) ? t('{0} (from {1})', [heredado(tp).plantilla, heredado(tp).de]) : t('Nothing to inherit: no design') }}</small></span></label>
            <label class="af-opcion"><input type="radio" :checked="!!e.disenos[tp.id]" :disabled="!configurar || !disenosDe(tp).length"
                                            @change="e.disenos[tp.id] = disenosDe(tp)[0]?.id || null" />
              <span>{{ t('Its own design') }}
                <Seleccion v-if="e.disenos[tp.id]" v-model="e.disenos[tp.id]" :disabled="!configurar" :aria-label="t('Design')">
                  <option v-for="p in disenosDe(tp)" :key="p.id" :value="p.id">{{ p.nombre }}</option></Seleccion>
                <small v-else-if="!disenosDe(tp).length" class="ayuda">{{ t('There is no approved design of this type yet.') }}</small></span></label>
          </article>
          <p v-if="!tipos.length" class="vacio">{{ t('There are no label types for items.') }}</p>
        </div>
        <p class="ayuda">{{ t('Exceptions (by PO, customer, destination…) are set later in «Which design goes on what».') }}</p>
      </template>

      <!-- 4. Revisar -->
      <template v-else>
        <dl class="af-resumen">
          <dt>{{ t('Family') }}</dt>
          <dd><strong>{{ e.familia.nombre }}</strong> <span class="etiqueta ms-0">{{ (e.familia.codigo || '').toUpperCase() }}</span>
            <span v-if="!e.familia.activa" class="etiqueta aviso ms-0">{{ t('Inactive') }}</span>
            <small v-if="madre" class="ayuda"> · {{ t('Subfamily of {0}', [tx(madre.nombre)]) }}</small>
            <button type="button" class="enlace af-cambiar" @click="ir(0)">{{ t('Change') }}</button></dd>
          <dt>{{ t('Fields') }}</dt>
          <dd>{{ e.familia.campos.length ? t('{0} usual, {1} required', [e.familia.campos.length, e.familia.campos.filter((c) => c.obligatorio).length]) : t('None') }}</dd>
          <dt>{{ t('What goes in it') }}</dt>
          <dd>{{ elegidos ? t('{0} products, {1} groups and {2} single items will be added', [e.productos.length, e.grupos.length, e.articulos.length]) : t('Nothing new') }}
            <button type="button" class="enlace af-cambiar" @click="ir(1)">{{ t('Change') }}</button></dd>
          <dt>{{ t('Designs') }}</dt>
          <dd>
            <ul class="af-lista">
              <li v-for="tp in tipos" :key="tp.id"><strong>{{ tx(tp.nombre) }}:</strong>
                {{ e.disenos[tp.id] ? nombrePlantilla(e.disenos[tp.id]) : heredado(tp) ? t('inherits {0}', [heredado(tp).plantilla]) : t('no design') }}</li>
            </ul>
            <button type="button" class="enlace af-cambiar" @click="ir(2)">{{ t('Change') }}</button></dd>
        </dl>
        <div v-for="(f, i) in faltan" :key="i" class="nota aviso af-falta"><Icono nombre="alerta" :tam="16" /><span>{{ f.texto }}</span>
          <button type="button" class="enlace" @click="ir(f.paso)">{{ t('Go to the step') }}</button></div>
      </template>

      <footer class="af-pie">
        <button v-if="e.paso > 0" type="button" class="btn" @click="ir(e.paso - 1)"><Icono nombre="atras" :tam="15" />{{ t('Back') }}</button>
        <span class="separar" />
        <button type="button" class="btn" :disabled="ocupado || !cambiado" @click="guardarBorrador(true)">{{ t('Save draft and exit') }}</button>
        <button v-if="e.paso < PASOS().length - 1" type="button" class="btn btn-primario" @click="ir(e.paso + 1)">
          {{ t('Next: {0}', [PASOS()[e.paso + 1].titulo]) }}<Icono nombre="derecha" :tam="15" /></button>
        <button v-else type="button" class="btn btn-primario" :disabled="ocupado || faltan.some((f) => f.paso === 0)" @click="terminar">
          <Icono nombre="check" :tam="15" />{{ t('Finish and apply') }}</button>
      </footer>
    </section>
  </div>

  <!-- Paso 2: lo elegido en esta página, en la barra flotante -->
  <BarraSeleccion v-if="listo && e.paso === 1" :cantidad="elegidos" :singular="t('record chosen')" :plural="t('records chosen')"
                  @limpiar="e.productos = []; e.grupos = []; e.articulos = []">
    <button type="button" class="btn btn-primario" @click="ir(2)">{{ t('Next: {0}', [PASOS()[2].titulo]) }}<Icono nombre="derecha" :tam="15" /></button>
  </BarraSeleccion>
</template>

<style scoped>
.af { display: flex; flex-direction: column; gap: 14px; max-width: 1180px; padding-bottom: 80px; }
.af-pasos { list-style: none; margin: 0; padding: 0; display: flex; gap: 6px; flex-wrap: wrap; align-items: center; }
.af-pasos li + li::before { content: ''; display: inline-block; width: 22px; height: 1px; background: var(--linea); vertical-align: middle; margin-inline-end: 6px; }
.af-paso { display: inline-flex; gap: 8px; align-items: center; border: 1px solid var(--linea); border-radius: 999px; padding: 5px 12px 5px 6px; background: var(--superficie);
  font: inherit; font-size: 0.84rem; color: var(--tinta-2); cursor: pointer; }
.af-paso.actual { border-color: var(--acento); color: var(--acento-texto); font-weight: 600; }
.af-num { display: inline-grid; place-items: center; width: 22px; height: 22px; border-radius: 50%; background: var(--superficie-2); font-size: 0.75rem; font-weight: 700; }
.af-paso.actual .af-num { background: var(--acento); color: var(--sobre-acento, #fff); }
.af-paso.hecho .af-num { background: var(--ok); color: #fff; }
.af-borrador { align-items: center; }
.af-borrador .enlace { margin-inline-start: auto; }
.af-cabeza { margin-bottom: 16px; }
.af-sup { margin: 0; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--tinta-3); font-weight: 600; }
.af-cabeza h2 { margin: 2px 0 4px; font-size: 1.2rem; }
.af-cabeza .ayuda { margin: 0; max-width: 760px; }
.af-barra { display: flex; gap: 10px; flex-wrap: wrap; align-items: center; margin-bottom: 10px; }
.af-buscar { flex: 1; min-width: 200px; }
.af-buscar input { min-width: 0; }
.af-elegidos { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; padding: 10px; margin-bottom: 10px; border-radius: 10px; background: var(--acento-claro); font-size: 0.82rem; }
.af-chip { display: inline-flex; align-items: center; gap: 4px; padding: 2px 4px 2px 8px; border-radius: 999px; background: var(--superficie); border: 1px solid var(--acento-medio); }
.af-chip button { border: 0; background: none; padding: 2px; cursor: pointer; color: var(--tinta-3); display: inline-flex; }
.af-disenos { display: flex; flex-direction: column; gap: 8px; margin-bottom: 10px; }
.af-tipo { display: grid; grid-template-columns: minmax(160px, 220px) minmax(0, 1fr) minmax(0, 1fr); gap: 12px; align-items: start; padding: 12px; border: 1px solid var(--linea); border-radius: 10px; }
.af-tipo-nombre { display: flex; flex-direction: column; gap: 4px; align-items: flex-start; }
.af-opcion { display: flex; gap: 8px; align-items: flex-start; padding: 8px 10px; border: 1px solid var(--linea); border-radius: 8px; cursor: pointer; }
.af-opcion > span { display: flex; flex-direction: column; gap: 4px; min-width: 0; flex: 1; }
.af-opcion:has(input:checked) { border-color: var(--acento); background: var(--acento-claro); }
.af-opcion :deep(.sb) { min-width: 0; width: 100%; }
.af-resumen { display: grid; grid-template-columns: 180px minmax(0, 1fr); gap: 12px 16px; margin: 0 0 14px; }
.af-resumen dt { color: var(--tinta-3); font-size: 0.84rem; font-weight: 600; }
.af-resumen dd { margin: 0; }
.af-lista { margin: 0 0 4px; padding-inline-start: 18px; }
.af-cambiar { margin-inline-start: 8px; font-size: 0.82rem; }
.af-falta { margin-top: 8px; align-items: center; }
.af-falta .enlace { margin-inline-start: auto; }
.af-pie { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 22px; padding-top: 14px; border-top: 1px solid var(--linea); }
@media (max-width: 860px) {
  .af-tipo { grid-template-columns: minmax(0, 1fr); }
  .af-resumen { grid-template-columns: minmax(0, 1fr); gap: 2px; }
  .af-resumen dd { margin-bottom: 10px; }
}
</style>
