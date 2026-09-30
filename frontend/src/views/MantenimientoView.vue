<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api'
import CargaArchivo from '../components/CargaArchivo.vue'
import Icono from '../components/Icono.vue'
import Modal from '../components/Modal.vue'
import ExplosionPrepack from '../components/ExplosionPrepack.vue'
import Paginacion from '../components/Paginacion.vue'
import SelectBusqueda from '../components/SelectBusqueda.vue'
import ThOrden from '../components/ThOrden.vue'
import { siguienteOrden } from '../composables/useTabla'
import { avisar, errorApi } from '../stores/ui'
import { fmtNum } from '../utils'

// Un solo lugar para todos los datos maestros. Cada catálogo llega descrito
// desde el servidor (campos, tipos, obligatorios, filtros) y esta vista dibuja
// el formulario, los filtros y la tabla a partir de esa descripción.
const route = useRoute()
const router = useRouter()
const catalogos = ref([])
const tipo = ref(route.query.catalogo || 'articulos')
const datos = ref({ items: [], total: 0 })
const filtros = reactive({ q: '', orden: '', page: 1, size: 15, extra: {} })
const opciones = reactive({})
const form = ref({})
const editando = ref(null)
const erroresForm = ref({})
const modal = ref(null)
const ocupado = ref(false)
const formAbierto = ref(false) // alta y edición en ventana emergente
const ESTADO_FICHA = { borrador: 'Sheet in draft', sugerida: 'To review', observado: 'Returned' }

const cat = computed(() => catalogos.value.find((c) => c.tipo === tipo.value))
const campos = computed(() => cat.value?.campos || [])
const columnas = computed(() => campos.value.filter((c) => !['descripcion', 'direccion', 'razon_social', 'upc'].includes(c.nombre) &&
  !(c.nombre === 'correos' && tipo.value !== 'contactos')))
const extras = computed(() => cat.value?.extras || [])
// Opciones para la lista con búsqueda: por id (ref) o por código
const opcionesDe = (c) => (opciones[c.catalogo] || []).map((o) => ({ valor: ['ref', 'multi'].includes(c.tipo) ? o.id : o.codigo, texto: o.texto }))
const conFiltro = computed(() => campos.value.filter((c) => c.filtro))

function vacio() {
  const f = {}
  for (const c of campos.value) f[c.nombre] = c.tipo === 'bool' ? true : c.tipo === 'multi' ? [] : ''
  return f
}

async function cargarMeta() {
  try {
    catalogos.value = await api.get('/catalogos')
  } catch (e) {
    errorApi(e)
  }
}

async function cargarOpciones() {
  const necesarios = new Set(campos.value.filter((c) => c.catalogo).map((c) => c.catalogo))
  await Promise.all([...necesarios].filter((t) => !opciones[t]).map(async (t) => {
    opciones[t] = await api.get(`/catalogos/${t}/opciones`)
  }))
}

async function cargar() {
  if (!cat.value) return
  try {
    datos.value = await api.get(`/catalogos/${tipo.value}`, {
      q: filtros.q, orden: filtros.orden, page: filtros.page, size: filtros.size, ...filtros.extra,
    })
  } catch (e) {
    errorApi(e)
  }
}

async function elegir(t, extra = {}) {
  if (t === 'prepacks' && !solidos.value.length) cargarSolidos()
  tipo.value = t
  router.replace({ query: { catalogo: t } })
  Object.assign(filtros, { q: '', orden: '', page: 1, extra: { ...extra } })
  editando.value = null
  erroresForm.value = {}
  form.value = vacio()
  await cargarOpciones()
  cargar()
}

let espera
function buscar() {
  clearTimeout(espera)
  espera = setTimeout(() => {
    filtros.page = 1
    cargar()
  }, 300)
}
function ordenar(campo) {
  filtros.orden = siguienteOrden(filtros.orden, campo)
  filtros.page = 1
  cargar()
}

// ---- Formulario -------------------------------------------------------------
function abrirNuevo() {
  nuevo()
  formAbierto.value = true
}
function cerrarForm() {
  formAbierto.value = false
  nuevo()
}
function editar(fila) {
  formAbierto.value = true
  editando.value = fila.id
  filaEditada.value = fila
  erroresForm.value = {}
  const f = vacio()
  for (const c of campos.value) f[c.nombre] = c.tipo === 'multi' ? [...(fila[c.nombre] || [])] : fila[c.nombre] ?? (c.tipo === 'bool' ? false : '')
  form.value = f
}
function nuevo() {
  editando.value = null
  erroresForm.value = {}
  form.value = vacio()
}
async function guardar() {
  ocupado.value = true
  erroresForm.value = {}
  try {
    const cuerpo = Object.fromEntries(Object.entries(form.value).map(([k, v]) => [k, v === '' ? null : v]))
    if (editando.value) {
      await api.patch(`/catalogos/${tipo.value}/${editando.value}`, cuerpo)
      avisar(`${cap(cat.value.singular)} updated.`)
    } else {
      await api.post(`/catalogos/${tipo.value}`, cuerpo)
      avisar(`${cap(cat.value.singular)} created.`)
      cat.value.total++
    }
    cerrarForm()
    delete opciones[tipo.value]
    cargar()
  } catch (e) {
    if (Array.isArray(e.detalle)) erroresForm.value = Object.fromEntries(e.detalle.filter((d) => d.campo).map((d) => [d.campo, d.mensaje]))
    errorApi(e)
  } finally {
    ocupado.value = false
  }
}
async function eliminar() {
  const fila = modal.value.fila
  ocupado.value = true
  try {
    await api.del(`/catalogos/${tipo.value}/${fila.id}`)
    avisar(`${cap(cat.value.singular)} deleted.`)
    cat.value.total--
    modal.value = null
    if (editando.value === fila.id) nuevo()
    cargar()
  } catch (e) {
    errorApi(e)
    modal.value = null
  } finally {
    ocupado.value = false
  }
}
async function alternarActivo(fila, campo) {
  try {
    await api.patch(`/catalogos/${tipo.value}/${fila.id}`, { [campo]: !fila[campo] })
    cargar()
  } catch (e) {
    errorApi(e)
  }
}
const cap = (t) => (t ? t[0].toUpperCase() + t.slice(1) : '')

function valorCelda(c, fila) {
  const v = fila[c.nombre]
  if (v === null || v === undefined || v === '') return '—'
  if (c.tipo === 'ref') return fila[`${c.nombre}_txt`] || v
  if (c.tipo === 'multi') return fila[`${c.nombre}_txt`] || '—'
  if (c.tipo === 'opcion') return c.opciones.find((o) => o[0] === v)?.[1] || v
  if (c.tipo === 'codigo') return opciones[c.catalogo]?.find((o) => o.codigo === v)?.texto || v
  return v
}
const campoActivo = computed(() => campos.value.find((c) => c.tipo === 'bool')?.nombre)

// ---- Carga masiva -----------------------------------------------------------
function abrirCarga() {
  modal.value = { tipo: 'carga', archivo: null, resultado: null }
}
async function cargarArchivo() {
  const datosForm = new FormData()
  datosForm.append('archivo', modal.value.archivo)
  ocupado.value = true
  try {
    modal.value.resultado = await api.post(`/catalogos/${tipo.value}/importar`, datosForm)
    const r = modal.value.resultado
    avisar(`${r.creados} created and ${r.actualizados} updated${r.errores.length ? `; ${r.errores.length} rows with errors` : ''}.`,
      r.errores.length ? 'error' : 'ok')
    await cargarMeta()
    cargar()
  } catch (e) {
    errorApi(e)
  } finally {
    ocupado.value = false
  }
}

// ---- Prepacks: se crean en un paso (código de producto + explosión) -------
// La explosión solo se ve; nunca se modifica.
const explosion = ref(null)
const solidos = ref([])
const nuevoPP = reactive({ sku: '', codigo: '', estilo: '', color: '', descripcion: '', cantidades: {} })
const erroresPP = ref({})
async function cargarSolidos() {
  try {
    solidos.value = (await api.get('/catalogos/articulos', { tipo: 'SOLIDO', activo: 'true', size: 200, orden: 'sku:asc' })).items
  } catch (e) {
    errorApi(e)
  }
}
const estilosPP = computed(() => [...new Set(solidos.value.map((a) => a.estilo))].sort())
const coloresPP = computed(() => [...new Set(solidos.value.filter((a) => a.estilo === nuevoPP.estilo).map((a) => a.color))].sort())
const tallasPP = computed(() => solidos.value.filter((a) => a.estilo === nuevoPP.estilo && a.color === nuevoPP.color))
const totalPP = computed(() => tallasPP.value.reduce((t, a) => t + (Number(nuevoPP.cantidades[a.id]) || 0), 0))
watch(() => [nuevoPP.estilo, nuevoPP.color], () => (nuevoPP.cantidades = {}))
async function crearPrepack() {
  ocupado.value = true
  erroresPP.value = {}
  try {
    const componentes = tallasPP.value.filter((a) => Number(nuevoPP.cantidades[a.id]) > 0)
      .map((a) => ({ articulo_id: a.id, cantidad: Number(nuevoPP.cantidades[a.id]) }))
    const r = await api.post('/catalogos/prepacks', { ...nuevoPP, cantidades: undefined, componentes })
    avisar(`Prepack ${r.codigo} created with item code ${r.sku} (${r.total} per carton).`)
    Object.assign(nuevoPP, { sku: '', codigo: '', descripcion: '', cantidades: {} })
    formAbierto.value = false
    cat.value.total++
    cargar()
  } catch (e) {
    if (Array.isArray(e.detalle)) erroresPP.value = Object.fromEntries(e.detalle.map((d) => [d.campo || 'componentes', d.mensaje]))
    errorApi(e)
  } finally {
    ocupado.value = false
  }
}

// Lo que no se modifica: prepack ID, estilo y color del prepack, y lo que enlaza al artículo prepack
const filaEditada = ref(null)
function bloqueado(c) {
  if (!editando.value) return false
  if (tipo.value === 'prepacks') return ['codigo', 'estilo', 'color'].includes(c.nombre)
  if (tipo.value === 'articulos' && filaEditada.value?.tipo === 'PREPACK') return ['tipo', 'estilo', 'color', 'talla', 'unidad'].includes(c.nombre)
  return false
}
// Un artículo nuevo aquí siempre es sólido; los prepacks se crean en su pestaña
const opcionesCampo = (c) => (c.nombre === 'tipo' && tipo.value === 'articulos' && !editando.value
  ? c.opciones.filter(([v]) => v === 'SOLIDO') : c.opciones)

watch(() => filtros.size, () => {
  filtros.page = 1
  cargar()
})

onMounted(async () => {
  await cargarMeta()
  if (!cat.value) tipo.value = 'articulos'
  await elegir(tipo.value)
})
</script>

<template>
  <div class="pagina-cabeza">
    <div>
      <h1>Master data</h1>
      <p>Master data used across the system: it validates the PO upload, defines the packing rules and feeds the filters. Item data (style, color, size, brand, UoM, HS code, origin) lives here; purchase data (quantity, price, casepack, inner pack) comes with each PO line.</p>
    </div>
    <div class="acciones">
      <button v-if="cat" class="btn btn-primario" @click="abrirNuevo"><Icono nombre="mas" />New {{ cat.singular }}</button>
      <template v-if="tipo === 'articulos' || tipo === 'prepacks'">
        <a class="btn" :href="tipo === 'articulos' ? '/plantilla_articulos.csv' : '/plantilla_prepacks.csv'" download><Icono nombre="descargar" />Template</a>
        <button class="btn" @click="abrirCarga"><Icono nombre="importar" />Upload {{ tipo === 'articulos' ? 'items' : 'size runs' }}</button>
      </template>
    </div>
  </div>

  <div class="pestanas-pildora" role="tablist">
    <button v-for="c in catalogos" :key="c.tipo" class="pildora" role="tab" :aria-selected="c.tipo === tipo" @click="elegir(c.tipo)">
      {{ c.titulo }}<span class="cuenta">{{ c.total }}</span>
    </button>
  </div>

  <div v-if="cat">

    <section>
      <div class="filtros">
        <label class="buscador">
          <Icono nombre="buscar" :tam="16" />
          <input v-model="filtros.q" type="search" :placeholder="`Search ${cat.titulo.toLowerCase()}`" aria-label="Search" @input="buscar" />
        </label>
        <template v-for="c in conFiltro" :key="c.nombre">
          <SelectBusqueda v-if="['ref', 'codigo', 'multi'].includes(c.tipo)" v-model="filtros.extra[c.nombre]" :opciones="opcionesDe(c)"
                          :vacio="`${c.etiqueta}: all`" :etiqueta="c.etiqueta" @change="filtros.page = 1; cargar()" />
          <select v-else v-model="filtros.extra[c.nombre]" :aria-label="c.etiqueta" @change="filtros.page = 1; cargar()">
            <option :value="undefined">{{ c.etiqueta }}: todos</option>
            <template v-if="c.tipo === 'bool'"><option value="true">{{ c.etiqueta }}: yes</option><option value="false">{{ c.etiqueta }}: no</option></template>
            <template v-else-if="c.tipo === 'opcion'"><option v-for="[v, t] in c.opciones" :key="v" :value="v">{{ t }}</option></template>
          </select>
        </template>
      </div>
      <div class="tabla-marco tabla-fija">
        <table class="tabla">
          <thead>
            <tr>
              <ThOrden v-for="c in columnas" :key="c.nombre" :campo="c.nombre" :orden="filtros.orden" :num="c.tipo === 'entero'" @ordenar="ordenar">{{ c.etiqueta }}</ThOrden>
              <th v-for="ex in extras" :key="ex.nombre">{{ ex.etiqueta }}</th>
              <th v-if="tipo === 'articulos'" title="The technical sheet and the HS code belong to the style and color">Sheet · HS code</th>
              <th v-if="tipo === 'prepacks'">Item code</th>
              <th v-if="tipo === 'prepacks'" class="num">Per carton</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="fila in datos.items" :key="fila.id" :class="{ seleccionada: editando === fila.id }">
              <td v-for="c in columnas" :key="c.nombre" :class="{ num: c.tipo === 'entero' }">
                <button v-if="c.tipo === 'bool'" type="button" class="etiqueta" :class="fila[c.nombre] ? 'ok' : ''" style="border: 0; cursor: pointer" :title="`Change ${c.etiqueta.toLowerCase()}`" @click="alternarActivo(fila, c.nombre)">
                  {{ fila[c.nombre] ? 'Yes' : 'No' }}
                </button>
                <span v-else :class="{ codigo: ['codigo', 'sku'].includes(c.nombre), fuerte: c.nombre === 'codigo' || c.nombre === 'sku' }">{{ valorCelda(c, fila) }}</span>
              </td>
              <td v-for="ex in extras" :key="ex.nombre">
                <button type="button" class="enlace" :title="`See ${ex.etiqueta.toLowerCase()} of ${fila.codigo || fila.nombre}`"
                        @click="elegir(ex.catalogo, { [ex.filtro]: fila.id })">
                  {{ ex.nombre === 'centros_txt' ? (fila.centros_txt || 'Assign plants') : `${fila[ex.nombre] || 0} ${fila[ex.nombre] === 1 ? ex.etiqueta.toLowerCase().replace(/s$/, '') : ex.etiqueta.toLowerCase()}` }}
                </button>
              </td>
              <td v-if="tipo === 'articulos'">
                <router-link v-if="fila.producto_id" :to="`/productos/${fila.producto_id}`" class="enlace" :title="`Technical sheet of ${fila.estilo} ${fila.color}`">
                  <span v-if="fila.partida_txt" class="codigo-sac">{{ fila.partida_txt }}</span>
                  <template v-else>{{ ESTADO_FICHA[fila.clasificacion] || 'Open sheet' }}</template>
                </router-link>
                <span v-else class="apagado">—</span>
              </td>
              <td v-if="tipo === 'prepacks'" class="codigo fuerte">{{ fila.sku || '—' }}</td>
              <td v-if="tipo === 'prepacks'" class="num">{{ fila.total }} <span class="sub">{{ fila.componentes }} tallas</span></td>
              <td class="num" style="white-space: nowrap">
                <button v-if="tipo === 'prepacks' || fila.tipo === 'PREPACK'" class="btn btn-chico" title="See the breakdown (it never changes)"
                        @click="explosion = { sku: fila.sku }"><Icono nombre="lupa" :tam="13" />Breakdown</button>
                <button class="btn-icono" :aria-label="`Edit ${cat.singular}`" title="Edit" @click="editar(fila)"><Icono nombre="editar" :tam="16" /></button>
                <button class="btn-icono" style="color: var(--error)" :aria-label="`Delete ${cat.singular}`" title="Delete" @click="modal = { tipo: 'eliminar', fila }"><Icono nombre="basura" :tam="16" /></button>
              </td>
            </tr>
            <tr v-if="!datos.items.length"><td :colspan="columnas.length + extras.length + (tipo === 'prepacks' ? 3 : tipo === 'articulos' ? 3 : 2)" class="vacio">No records match these filters.</td></tr>
          </tbody>
        </table>
      </div>
      <Paginacion :page="filtros.page" :size="filtros.size" :total="datos.total" @cambiar="(p) => { filtros.page = p; cargar() }" @tamano="(t) => (filtros.size = t)" />
    </section>
  </div>

  <Modal v-if="formAbierto && cat" :titulo="editando ? `Edit ${cat.singular}` : `New ${cat.singular}`" ancho="640px" @cerrar="cerrarForm">
    <p v-if="cat.ayuda" class="ayuda" style="margin-top: 0">{{ cat.ayuda }}</p>
      <form v-if="tipo === 'prepacks' && !editando" class="form-catalogo" @submit.prevent="crearPrepack">
        <label class="campo"><span class="req">Item code</span>
          <input v-model="nuevoPP.sku" inputmode="numeric" placeholder="30095120027" required />
          <small v-if="erroresPP.sku" class="nota error" style="padding: 4px 8px">{{ erroresPP.sku }}</small>
          <small v-else class="ayuda">A prepack is an item like any other, with its own code.</small>
        </label>
        <label class="campo"><span class="req">Style</span>
          <SelectBusqueda v-model="nuevoPP.estilo" :opciones="estilosPP" requerido etiqueta="Style" />
        </label>
        <label class="campo"><span class="req">Color</span>
          <SelectBusqueda v-model="nuevoPP.color" :opciones="coloresPP" requerido etiqueta="Color" :deshabilitado="!nuevoPP.estilo" />
        </label>
        <label class="campo"><span class="req">Prepack ID (size)</span>
          <input v-model="nuevoPP.codigo" maxlength="10" placeholder="AB12" style="text-transform: uppercase" required />
          <small v-if="erroresPP.codigo" class="nota error" style="padding: 4px 8px">{{ erroresPP.codigo }}</small>
          <small v-else class="ayuda">Usually 2 letters and 2 digits. It is the size of the prepack item.</small>
        </label>
        <label class="campo"><span>Description</span><input v-model="nuevoPP.descripcion" /></label>
        <div v-if="nuevoPP.estilo && nuevoPP.color" class="campo">
          <span class="req">Breakdown per master carton<template v-if="tallasPP.length"> ({{ tallasPP[0].unidad }})</template></span>
          <div class="tabla-marco" style="box-shadow: none">
            <table class="tabla">
              <thead><tr><th>Size</th><th>SKU</th><th class="num">Qty</th></tr></thead>
              <tbody>
                <tr v-for="a in tallasPP" :key="a.id">
                  <td><b>{{ a.talla }}</b></td>
                  <td class="codigo">{{ a.sku }}</td>
                  <td class="num"><input v-model.number="nuevoPP.cantidades[a.id]" class="celda num" type="number" min="0" style="width: 64px; border-color: var(--linea)" :aria-label="`Quantity size ${a.talla}`" /></td>
                </tr>
              </tbody>
              <tfoot><tr><td colspan="2">Total per carton</td><td class="num">{{ totalPP }}</td></tr></tfoot>
            </table>
          </div>
          <small v-if="erroresPP.componentes" class="nota error" style="padding: 4px 8px">{{ erroresPP.componentes }}</small>
          <small v-else class="ayuda">Only solids of {{ nuevoPP.estilo }} {{ nuevoPP.color }}. Leave at 0 the sizes it does not carry. Once created it never changes.</small>
        </div>
        <p class="leyenda-req">Required</p>
        <button class="btn btn-primario" type="submit" :disabled="ocupado || !totalPP"><Icono nombre="mas" :tam="16" />Create prepack</button>
      </form>
      <form v-else class="form-catalogo" @submit.prevent="guardar">
        <label v-for="c in campos" :key="c.nombre" :class="c.tipo === 'bool' ? 'check' : 'campo'">
          <template v-if="c.tipo === 'bool'">
            <input v-model="form[c.nombre]" type="checkbox" /> {{ c.etiqueta }}
          </template>
          <template v-else>
            <span :class="{ req: c.obligatorio }">{{ c.etiqueta }}</span>
            <select v-if="c.tipo === 'opcion'" v-model="form[c.nombre]" :required="c.obligatorio" :disabled="bloqueado(c)">
              <option value="">Choose…</option>
              <option v-for="[v, t] in opcionesCampo(c)" :key="v" :value="v">{{ t }}</option>
            </select>
            <SelectBusqueda v-else-if="c.tipo === 'ref' || c.tipo === 'codigo'" v-model="form[c.nombre]" :opciones="opcionesDe(c)"
                            :vacio="c.obligatorio ? '' : 'None'" :requerido="c.obligatorio" :etiqueta="c.etiqueta" :deshabilitado="bloqueado(c)" />
            <SelectBusqueda v-else-if="c.tipo === 'multi'" v-model="form[c.nombre]" :opciones="opcionesDe(c)" multiple
                            placeholder="Choose one or more…" :requerido="c.obligatorio" :etiqueta="c.etiqueta" />
            <textarea v-else-if="c.tipo === 'correos'" v-model="form[c.nombre]" rows="2" :required="c.obligatorio"
                      placeholder="name@company.com, other@company.com"></textarea>
            <input v-else v-model="form[c.nombre]" :type="c.tipo === 'entero' || c.tipo === 'numero' ? 'number' : 'text'"
                   :min="c.minimo" :maxlength="c.max" :required="c.obligatorio" :disabled="bloqueado(c)" :title="bloqueado(c) ? 'Cannot change: it is part of the prepack' : ''" />
            <small v-if="erroresForm[c.nombre]" class="nota error" style="padding: 4px 8px">{{ erroresForm[c.nombre] }}</small>
            <small v-else-if="c.ayuda" class="ayuda">{{ c.ayuda }}</small>
          </template>
        </label>
        <p class="leyenda-req">Required</p>
        <div class="fila-flex">
          <button class="btn btn-primario" type="submit" :disabled="ocupado"><Icono :nombre="editando ? 'check' : 'mas'" :tam="16" />{{ editando ? 'Save changes' : `Create ${cat.singular}` }}</button>
          <button class="btn btn-fantasma" type="button" @click="cerrarForm">Cancel</button>
        </div>
      </form>
  </Modal>

  <Modal v-if="modal?.tipo === 'eliminar'" :titulo="`Delete ${cat.singular}`" @cerrar="modal = null">
    <p>Delete <b>{{ modal.fila.codigo || modal.fila.sku }}</b>? If other records already use it, it cannot be deleted; deactivate it instead.</p>
    <template #pie>
      <button class="btn" @click="modal = null">Cancel</button>
      <button class="btn btn-peligro" :disabled="ocupado" @click="eliminar">Delete</button>
    </template>
  </Modal>

  <Modal v-if="modal?.tipo === 'carga'" :titulo="tipo === 'articulos' ? 'Upload items' : 'Upload size runs (prepacks)'" ancho="680px" @cerrar="modal = null">
    <p class="ayuda" v-if="tipo === 'articulos'">One row per item number (SKU). If it exists it is updated. Brand, group and supplier are given by code. Only solids here; prepacks are uploaded in the Prepacks tab with their breakdown. The casepack is not item data: it comes with each PO line.</p>
    <p class="ayuda" v-else>One row per size of the breakdown: sku_prepack (item code of the prepack), prepack_id (e.g. AB12), description, solid SKU and quantity. Style and color come from the solids, which must share style and color. It creates the prepack and its item; an existing prepack is never changed.</p>
    <CargaArchivo v-model="modal.archivo" />
    <template v-if="modal.resultado">
      <div class="nota ok"><Icono nombre="check" />{{ modal.resultado.creados }} created and {{ modal.resultado.actualizados }} updated.</div>
      <div v-if="modal.resultado.errores.length" class="tabla-marco" style="max-height: 240px; overflow: auto; box-shadow: none">
        <table class="tabla">
          <thead><tr><th>Row</th><th>Error</th></tr></thead>
          <tbody><tr v-for="(er, i) in modal.resultado.errores" :key="i"><td>{{ er.fila }}</td><td class="envolver">{{ er.mensaje }}</td></tr></tbody>
        </table>
      </div>
    </template>
    <template #pie>
      <button class="btn" @click="modal = null">Close</button>
      <button class="btn btn-primario" :disabled="ocupado || !modal.archivo" @click="cargarArchivo"><Icono nombre="importar" :tam="16" />Upload</button>
    </template>
  </Modal>

  <ExplosionPrepack v-if="explosion" :sku="explosion.sku" @cerrar="explosion = null" />
</template>
