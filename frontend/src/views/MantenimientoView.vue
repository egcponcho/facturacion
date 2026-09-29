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
      avisar(`${cap(cat.value.singular)} actualizado.`)
    } else {
      await api.post(`/catalogos/${tipo.value}`, cuerpo)
      avisar(`${cap(cat.value.singular)} creado.`)
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
    avisar(`${cap(cat.value.singular)} eliminado.`)
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
    avisar(`${r.creados} creados y ${r.actualizados} actualizados${r.errores.length ? `; ${r.errores.length} filas con errores` : ''}.`,
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
    avisar(`Prepack ${r.codigo} creado con el código ${r.sku} (${r.total} por caja).`)
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
      <h1>Mantenimiento</h1>
      <p>Datos maestros que usa todo el sistema: validan la carga de OCs, definen las reglas de empaque y alimentan los filtros.</p>
    </div>
    <div class="acciones">
      <button v-if="cat" class="btn btn-primario" @click="abrirNuevo"><Icono nombre="mas" />Nuevo {{ cat.singular }}</button>
      <template v-if="tipo === 'articulos' || tipo === 'prepacks'">
        <a class="btn" :href="tipo === 'articulos' ? '/plantilla_articulos.csv' : '/plantilla_prepacks.csv'" download><Icono nombre="descargar" />Formato</a>
        <button class="btn" @click="abrirCarga"><Icono nombre="importar" />Cargar {{ tipo === 'articulos' ? 'artículos' : 'curvas' }}</button>
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
          <input v-model="filtros.q" type="search" :placeholder="`Buscar en ${cat.titulo.toLowerCase()}`" aria-label="Buscar" @input="buscar" />
        </label>
        <template v-for="c in conFiltro" :key="c.nombre">
          <SelectBusqueda v-if="['ref', 'codigo', 'multi'].includes(c.tipo)" v-model="filtros.extra[c.nombre]" :opciones="opcionesDe(c)"
                          :vacio="`${c.etiqueta}: todos`" :etiqueta="c.etiqueta" @change="filtros.page = 1; cargar()" />
          <select v-else v-model="filtros.extra[c.nombre]" :aria-label="c.etiqueta" @change="filtros.page = 1; cargar()">
            <option :value="undefined">{{ c.etiqueta }}: todos</option>
            <template v-if="c.tipo === 'bool'"><option value="true">{{ c.etiqueta }}: sí</option><option value="false">{{ c.etiqueta }}: no</option></template>
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
              <th v-if="tipo === 'prepacks'">Código de producto</th>
              <th v-if="tipo === 'prepacks'" class="num">Por caja</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="fila in datos.items" :key="fila.id" :class="{ seleccionada: editando === fila.id }">
              <td v-for="c in columnas" :key="c.nombre" :class="{ num: c.tipo === 'entero' }">
                <button v-if="c.tipo === 'bool'" type="button" class="etiqueta" :class="fila[c.nombre] ? 'ok' : ''" style="border: 0; cursor: pointer" :title="`Cambiar ${c.etiqueta.toLowerCase()}`" @click="alternarActivo(fila, c.nombre)">
                  {{ fila[c.nombre] ? 'Sí' : 'No' }}
                </button>
                <span v-else :class="{ codigo: ['codigo', 'sku'].includes(c.nombre), fuerte: c.nombre === 'codigo' || c.nombre === 'sku' }">{{ valorCelda(c, fila) }}</span>
              </td>
              <td v-for="ex in extras" :key="ex.nombre">
                <button type="button" class="enlace" :title="`Ver ${ex.etiqueta.toLowerCase()} de ${fila.codigo || fila.nombre}`"
                        @click="elegir(ex.catalogo, { [ex.filtro]: fila.id })">
                  {{ ex.nombre === 'centros_txt' ? (fila.centros_txt || 'Asignar centros') : `${fila[ex.nombre] || 0} ${fila[ex.nombre] === 1 ? ex.etiqueta.toLowerCase().replace(/s$/, '') : ex.etiqueta.toLowerCase()}` }}
                </button>
              </td>
              <td v-if="tipo === 'prepacks'" class="codigo fuerte">{{ fila.sku || '—' }}</td>
              <td v-if="tipo === 'prepacks'" class="num">{{ fila.total }} <span class="sub">{{ fila.componentes }} tallas</span></td>
              <td class="num" style="white-space: nowrap">
                <button v-if="tipo === 'prepacks' || fila.tipo === 'PREPACK'" class="btn btn-chico" title="Ver la explosión (no se modifica)"
                        @click="explosion = { sku: fila.sku }"><Icono nombre="lupa" :tam="13" />Explosión</button>
                <button class="btn-icono" :aria-label="`Editar ${cat.singular}`" title="Editar" @click="editar(fila)"><Icono nombre="editar" :tam="16" /></button>
                <button class="btn-icono" style="color: var(--error)" :aria-label="`Eliminar ${cat.singular}`" title="Eliminar" @click="modal = { tipo: 'eliminar', fila }"><Icono nombre="basura" :tam="16" /></button>
              </td>
            </tr>
            <tr v-if="!datos.items.length"><td :colspan="columnas.length + extras.length + (tipo === 'prepacks' ? 3 : 2)" class="vacio">No hay registros con estos filtros.</td></tr>
          </tbody>
        </table>
      </div>
      <Paginacion :page="filtros.page" :size="filtros.size" :total="datos.total" @cambiar="(p) => { filtros.page = p; cargar() }" @tamano="(t) => (filtros.size = t)" />
    </section>
  </div>

  <Modal v-if="formAbierto && cat" :titulo="editando ? `Editar ${cat.singular}` : `Nuevo ${cat.singular}`" ancho="640px" @cerrar="cerrarForm">
    <p v-if="cat.ayuda" class="ayuda" style="margin-top: 0">{{ cat.ayuda }}</p>
      <form v-if="tipo === 'prepacks' && !editando" class="form-catalogo" @submit.prevent="crearPrepack">
        <label class="campo"><span class="req">Código de producto</span>
          <input v-model="nuevoPP.sku" inputmode="numeric" placeholder="30095120027" required />
          <small v-if="erroresPP.sku" class="nota error" style="padding: 4px 8px">{{ erroresPP.sku }}</small>
          <small v-else class="ayuda">El prepack es un artículo más, con su propio código.</small>
        </label>
        <label class="campo"><span class="req">Estilo</span>
          <SelectBusqueda v-model="nuevoPP.estilo" :opciones="estilosPP" requerido etiqueta="Estilo" />
        </label>
        <label class="campo"><span class="req">Color</span>
          <SelectBusqueda v-model="nuevoPP.color" :opciones="coloresPP" requerido etiqueta="Color" :deshabilitado="!nuevoPP.estilo" />
        </label>
        <label class="campo"><span class="req">Prepack ID (talla)</span>
          <input v-model="nuevoPP.codigo" maxlength="10" placeholder="AB12" style="text-transform: uppercase" required />
          <small v-if="erroresPP.codigo" class="nota error" style="padding: 4px 8px">{{ erroresPP.codigo }}</small>
          <small v-else class="ayuda">Usualmente 2 letras y 2 números. Es la talla del artículo prepack.</small>
        </label>
        <label class="campo"><span>Descripción</span><input v-model="nuevoPP.descripcion" /></label>
        <div v-if="nuevoPP.estilo && nuevoPP.color" class="campo">
          <span class="req">Explosión por caja master<template v-if="tallasPP.length"> ({{ tallasPP[0].unidad }})</template></span>
          <div class="tabla-marco" style="box-shadow: none">
            <table class="tabla">
              <thead><tr><th>Talla</th><th>SKU</th><th class="num">Cant.</th></tr></thead>
              <tbody>
                <tr v-for="a in tallasPP" :key="a.id">
                  <td><b>{{ a.talla }}</b></td>
                  <td class="codigo">{{ a.sku }}</td>
                  <td class="num"><input v-model.number="nuevoPP.cantidades[a.id]" class="celda num" type="number" min="0" style="width: 64px; border-color: var(--linea)" :aria-label="`Cantidad talla ${a.talla}`" /></td>
                </tr>
              </tbody>
              <tfoot><tr><td colspan="2">Total por caja</td><td class="num">{{ totalPP }}</td></tr></tfoot>
            </table>
          </div>
          <small v-if="erroresPP.componentes" class="nota error" style="padding: 4px 8px">{{ erroresPP.componentes }}</small>
          <small v-else class="ayuda">Solo sólidos de {{ nuevoPP.estilo }} {{ nuevoPP.color }}. Deja en 0 las tallas que no lleva. Una vez creado no se modifica.</small>
        </div>
        <p class="leyenda-req">Obligatorio</p>
        <button class="btn btn-primario" type="submit" :disabled="ocupado || !totalPP"><Icono nombre="mas" :tam="16" />Crear prepack</button>
      </form>
      <form v-else class="form-catalogo" @submit.prevent="guardar">
        <label v-for="c in campos" :key="c.nombre" :class="c.tipo === 'bool' ? 'check' : 'campo'">
          <template v-if="c.tipo === 'bool'">
            <input v-model="form[c.nombre]" type="checkbox" /> {{ c.etiqueta }}
          </template>
          <template v-else>
            <span :class="{ req: c.obligatorio }">{{ c.etiqueta }}</span>
            <select v-if="c.tipo === 'opcion'" v-model="form[c.nombre]" :required="c.obligatorio" :disabled="bloqueado(c)">
              <option value="">Elige…</option>
              <option v-for="[v, t] in opcionesCampo(c)" :key="v" :value="v">{{ t }}</option>
            </select>
            <SelectBusqueda v-else-if="c.tipo === 'ref' || c.tipo === 'codigo'" v-model="form[c.nombre]" :opciones="opcionesDe(c)"
                            :vacio="c.obligatorio ? '' : 'Ninguno'" :requerido="c.obligatorio" :etiqueta="c.etiqueta" :deshabilitado="bloqueado(c)" />
            <SelectBusqueda v-else-if="c.tipo === 'multi'" v-model="form[c.nombre]" :opciones="opcionesDe(c)" multiple
                            placeholder="Elige uno o varios…" :requerido="c.obligatorio" :etiqueta="c.etiqueta" />
            <textarea v-else-if="c.tipo === 'correos'" v-model="form[c.nombre]" rows="2" :required="c.obligatorio"
                      placeholder="nombre@empresa.com, otro@empresa.com"></textarea>
            <input v-else v-model="form[c.nombre]" :type="c.tipo === 'entero' || c.tipo === 'numero' ? 'number' : 'text'"
                   :min="c.minimo" :maxlength="c.max" :required="c.obligatorio" :disabled="bloqueado(c)" :title="bloqueado(c) ? 'No se modifica: es parte del prepack' : ''" />
            <small v-if="erroresForm[c.nombre]" class="nota error" style="padding: 4px 8px">{{ erroresForm[c.nombre] }}</small>
            <small v-else-if="c.ayuda" class="ayuda">{{ c.ayuda }}</small>
          </template>
        </label>
        <p class="leyenda-req">Obligatorio</p>
        <div class="fila-flex">
          <button class="btn btn-primario" type="submit" :disabled="ocupado"><Icono :nombre="editando ? 'check' : 'mas'" :tam="16" />{{ editando ? 'Guardar cambios' : `Crear ${cat.singular}` }}</button>
          <button class="btn btn-fantasma" type="button" @click="cerrarForm">Cancelar</button>
        </div>
      </form>
  </Modal>

  <Modal v-if="modal?.tipo === 'eliminar'" :titulo="`Eliminar ${cat.singular}`" @cerrar="modal = null">
    <p>¿Eliminar <b>{{ modal.fila.codigo || modal.fila.sku }}</b>? Si ya se usa en otros registros no se podrá eliminar; en ese caso desactívalo.</p>
    <template #pie>
      <button class="btn" @click="modal = null">Cancelar</button>
      <button class="btn btn-peligro" :disabled="ocupado" @click="eliminar">Eliminar</button>
    </template>
  </Modal>

  <Modal v-if="modal?.tipo === 'carga'" :titulo="tipo === 'articulos' ? 'Cargar artículos' : 'Cargar curvas (prepacks)'" ancho="680px" @cerrar="modal = null">
    <p class="ayuda" v-if="tipo === 'articulos'">Una fila por número de artículo (SKU). Si ya existe se actualiza. Marca, grupo y proveedor se indican por código. Aquí solo sólidos; los prepacks se cargan en la pestaña Prepacks con su explosión.</p>
    <p class="ayuda" v-else>Una fila por talla de la explosión: sku_prepack (código de producto del prepack), prepack_id (p. ej. AB12), descripción, SKU sólido y cantidad. Estilo y color salen de los sólidos, que deben ser del mismo estilo y color. Crea el prepack y su artículo; un prepack que ya existe no se modifica.</p>
    <CargaArchivo v-model="modal.archivo" />
    <template v-if="modal.resultado">
      <div class="nota ok"><Icono nombre="check" />{{ modal.resultado.creados }} creados y {{ modal.resultado.actualizados }} actualizados.</div>
      <div v-if="modal.resultado.errores.length" class="tabla-marco" style="max-height: 240px; overflow: auto; box-shadow: none">
        <table class="tabla">
          <thead><tr><th>Fila</th><th>Error</th></tr></thead>
          <tbody><tr v-for="(er, i) in modal.resultado.errores" :key="i"><td>{{ er.fila }}</td><td class="envolver">{{ er.mensaje }}</td></tr></tbody>
        </table>
      </div>
    </template>
    <template #pie>
      <button class="btn" @click="modal = null">Cerrar</button>
      <button class="btn btn-primario" :disabled="ocupado || !modal.archivo" @click="cargarArchivo"><Icono nombre="importar" :tam="16" />Cargar</button>
    </template>
  </Modal>

  <ExplosionPrepack v-if="explosion" :sku="explosion.sku" @cerrar="explosion = null" />
</template>
