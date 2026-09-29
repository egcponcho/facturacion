<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api'
import CargaArchivo from '../components/CargaArchivo.vue'
import Icono from '../components/Icono.vue'
import Modal from '../components/Modal.vue'
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

const cat = computed(() => catalogos.value.find((c) => c.tipo === tipo.value))
const campos = computed(() => cat.value?.campos || [])
const columnas = computed(() => campos.value.filter((c) => !['descripcion', 'direccion', 'razon_social', 'upc'].includes(c.nombre) &&
  !(c.nombre === 'correos' && tipo.value !== 'contactos')))
const extras = computed(() => cat.value?.extras || [])
// Opciones para la lista con búsqueda: por id (ref) o por código
const opcionesDe = (c) => (opciones[c.catalogo] || []).map((o) => ({ valor: c.tipo === 'ref' ? o.id : o.codigo, texto: o.texto }))
const conFiltro = computed(() => campos.value.filter((c) => c.filtro))

function vacio() {
  const f = {}
  for (const c of campos.value) f[c.nombre] = c.tipo === 'bool' ? true : ''
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
function editar(fila) {
  editando.value = fila.id
  erroresForm.value = {}
  const f = vacio()
  for (const c of campos.value) f[c.nombre] = fila[c.nombre] ?? (c.tipo === 'bool' ? false : '')
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
    nuevo()
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

// ---- Curva de un prepack ----------------------------------------------------
// La curva solo se arma con sólidos del mismo estilo y color del prepack:
// se ofrecen directamente esas tallas
async function abrirCurva(fila) {
  try {
    const [c, r] = await Promise.all([
      api.get(`/catalogos/prepacks/${fila.id}/componentes`),
      api.get('/catalogos/articulos', { estilo: fila.estilo, color: fila.color, tipo: 'SOLIDO', size: 100, orden: 'sku:asc' }),
    ])
    modal.value = { tipo: 'curva', prepack: c, items: c.componentes.map((x) => ({ ...x })), resultados: r.items }
  } catch (e) {
    errorApi(e)
  }
}
function agregarComponente(a) {
  const m = modal.value
  if (m.items.some((x) => x.articulo_id === a.id)) return
  m.items.push({ articulo_id: a.id, sku: a.sku, estilo: a.estilo, color: a.color, talla: a.talla, unidad: a.unidad, cantidad: 1 })
}
const totalCurva = computed(() => (modal.value?.items || []).reduce((s, x) => s + (Number(x.cantidad) || 0), 0))
async function guardarCurva() {
  ocupado.value = true
  try {
    await api.put(`/catalogos/prepacks/${modal.value.prepack.id}/componentes`,
      modal.value.items.map((x) => ({ articulo_id: x.articulo_id, cantidad: Number(x.cantidad) })))
    avisar('Curva guardada.')
    modal.value = null
    cargar()
  } catch (e) {
    errorApi(e)
  } finally {
    ocupado.value = false
  }
}

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
      <template v-if="tipo === 'articulos' || tipo === 'prepacks'">
        <a class="btn" :href="tipo === 'articulos' ? '/plantilla_articulos.csv' : '/plantilla_prepacks.csv'" download><Icono nombre="descargar" />Formato</a>
        <button class="btn btn-primario" @click="abrirCarga"><Icono nombre="importar" />Cargar {{ tipo === 'articulos' ? 'artículos' : 'curvas' }}</button>
      </template>
    </div>
  </div>

  <div class="pestanas-pildora" role="tablist">
    <button v-for="c in catalogos" :key="c.tipo" class="pildora" role="tab" :aria-selected="c.tipo === tipo" @click="elegir(c.tipo)">
      {{ c.titulo }}<span class="cuenta">{{ c.total }}</span>
    </button>
  </div>

  <div v-if="cat" class="mantenimiento">
    <section class="panel">
      <div class="panel-cabeza">
        <div><h2>{{ editando ? `Editar ${cat.singular}` : `Nuevo ${cat.singular}` }}</h2><p v-if="cat.ayuda">{{ cat.ayuda }}</p></div>
      </div>
      <form class="form-catalogo" @submit.prevent="guardar">
        <label v-for="c in campos" :key="c.nombre" :class="c.tipo === 'bool' ? 'check' : 'campo'">
          <template v-if="c.tipo === 'bool'">
            <input v-model="form[c.nombre]" type="checkbox" /> {{ c.etiqueta }}
          </template>
          <template v-else>
            <span :class="{ req: c.obligatorio }">{{ c.etiqueta }}</span>
            <select v-if="c.tipo === 'opcion'" v-model="form[c.nombre]" :required="c.obligatorio">
              <option value="">Elige…</option>
              <option v-for="[v, t] in c.opciones" :key="v" :value="v">{{ t }}</option>
            </select>
            <SelectBusqueda v-else-if="c.tipo === 'ref' || c.tipo === 'codigo'" v-model="form[c.nombre]" :opciones="opcionesDe(c)"
                            :vacio="c.obligatorio ? '' : 'Ninguno'" :requerido="c.obligatorio" :etiqueta="c.etiqueta" />
            <textarea v-else-if="c.tipo === 'correos'" v-model="form[c.nombre]" rows="2" :required="c.obligatorio"
                      placeholder="nombre@empresa.com, otro@empresa.com"></textarea>
            <input v-else v-model="form[c.nombre]" :type="c.tipo === 'entero' || c.tipo === 'numero' ? 'number' : 'text'"
                   :min="c.minimo" :maxlength="c.max" :required="c.obligatorio" />
            <small v-if="erroresForm[c.nombre]" class="nota error" style="padding: 4px 8px">{{ erroresForm[c.nombre] }}</small>
            <small v-else-if="c.ayuda" class="ayuda">{{ c.ayuda }}</small>
          </template>
        </label>
        <p class="leyenda-req">Obligatorio</p>
        <div class="fila-flex">
          <button class="btn btn-primario" type="submit" :disabled="ocupado"><Icono :nombre="editando ? 'check' : 'mas'" :tam="16" />{{ editando ? 'Guardar cambios' : `Crear ${cat.singular}` }}</button>
          <button v-if="editando" class="btn btn-fantasma" type="button" @click="nuevo">Cancelar edición</button>
        </div>
      </form>
    </section>

    <section>
      <div class="filtros">
        <label class="buscador">
          <Icono nombre="buscar" :tam="16" />
          <input v-model="filtros.q" type="search" :placeholder="`Buscar en ${cat.titulo.toLowerCase()}`" aria-label="Buscar" @input="buscar" />
        </label>
        <template v-for="c in conFiltro" :key="c.nombre">
          <SelectBusqueda v-if="c.tipo === 'ref' || c.tipo === 'codigo'" v-model="filtros.extra[c.nombre]" :opciones="opcionesDe(c)"
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
              <th v-if="tipo === 'prepacks'" class="num">Pares por caja</th>
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
                  {{ ex.nombre === 'centros_txt' ? (fila.centros_txt || 'Asignar centros') : `${fila[ex.nombre] || 0} ${ex.etiqueta.toLowerCase()}` }}
                </button>
              </td>
              <td v-if="tipo === 'prepacks'" class="num">{{ fila.total }} <span class="sub">{{ fila.componentes }} tallas</span></td>
              <td class="num" style="white-space: nowrap">
                <button v-if="tipo === 'prepacks'" class="btn btn-chico" @click="abrirCurva(fila)">Curva</button>
                <button class="btn-icono" :aria-label="`Editar ${cat.singular}`" title="Editar" @click="editar(fila)"><Icono nombre="editar" :tam="16" /></button>
                <button class="btn-icono" style="color: var(--error)" :aria-label="`Eliminar ${cat.singular}`" title="Eliminar" @click="modal = { tipo: 'eliminar', fila }"><Icono nombre="basura" :tam="16" /></button>
              </td>
            </tr>
            <tr v-if="!datos.items.length"><td :colspan="columnas.length + extras.length + 2" class="vacio">No hay registros con estos filtros.</td></tr>
          </tbody>
        </table>
      </div>
      <Paginacion :page="filtros.page" :size="filtros.size" :total="datos.total" @cambiar="(p) => { filtros.page = p; cargar() }" @tamano="(t) => (filtros.size = t)" />
    </section>
  </div>

  <Modal v-if="modal?.tipo === 'eliminar'" :titulo="`Eliminar ${cat.singular}`" @cerrar="modal = null">
    <p>¿Eliminar <b>{{ modal.fila.codigo || modal.fila.sku }}</b>? Si ya se usa en otros registros no se podrá eliminar; en ese caso desactívalo.</p>
    <template #pie>
      <button class="btn" @click="modal = null">Cancelar</button>
      <button class="btn btn-peligro" :disabled="ocupado" @click="eliminar">Eliminar</button>
    </template>
  </Modal>

  <Modal v-if="modal?.tipo === 'carga'" :titulo="tipo === 'articulos' ? 'Cargar artículos' : 'Cargar curvas (prepacks)'" ancho="680px" @cerrar="modal = null">
    <p class="ayuda" v-if="tipo === 'articulos'">Una fila por número de artículo (SKU). Si ya existe se actualiza. Marca, grupo y proveedor se indican por código. Para un prepack usa tipo PREPACK, unidad CJ y como talla su prepack ID (p. ej. AB12); su curva debe existir antes.</p>
    <p class="ayuda" v-else>Una fila por talla de la curva: prepack_id (p. ej. AB12), descripción, SKU sólido y cantidad. El estilo y color del prepack salen de sus SKU, que deben ser todos del mismo estilo y color. Reemplaza la curva completa.</p>
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

  <Modal v-if="modal?.tipo === 'curva'" :titulo="`Prepack ${modal.prepack.codigo} · ${modal.prepack.estilo} ${modal.prepack.color}`" ancho="760px" @cerrar="modal = null">
    <p class="ayuda">Tallas y pares por caja master. Se arma con los artículos sólidos de {{ modal.prepack.estilo }} {{ modal.prepack.color }}; cada caja de este prepack trae exactamente esta distribución. El prepack ID ({{ modal.prepack.codigo }}) es la talla del artículo prepack.</p>
    <div class="tabla-marco" style="box-shadow: none">
      <table class="tabla">
        <thead><tr><th>SKU</th><th>Estilo · color</th><th>Talla</th><th class="num">Cantidad</th><th></th></tr></thead>
        <tbody>
          <tr v-for="(x, i) in modal.items" :key="x.articulo_id">
            <td class="codigo">{{ x.sku }}</td>
            <td>{{ x.estilo }} · {{ x.color }}</td>
            <td><b>{{ x.talla }}</b></td>
            <td class="num"><input v-model.number="x.cantidad" class="celda num" type="number" min="1" style="width: 80px; border-color: var(--linea)" :aria-label="`Cantidad talla ${x.talla}`" /></td>
            <td class="num"><button class="btn-icono" :aria-label="`Quitar talla ${x.talla}`" @click="modal.items.splice(i, 1)"><Icono nombre="cerrar" :tam="15" /></button></td>
          </tr>
          <tr v-if="!modal.items.length"><td colspan="5" class="vacio">La curva está vacía. Busca abajo los artículos sólidos que la forman.</td></tr>
        </tbody>
        <tfoot v-if="modal.items.length"><tr><td colspan="3">Total por caja master</td><td class="num">{{ fmtNum(totalCurva) }}</td><td></td></tr></tfoot>
      </table>
    </div>
    <p class="ayuda" style="margin: 12px 0 6px">Tallas de {{ modal.prepack.estilo }} {{ modal.prepack.color }} para agregar:</p>
    <p v-if="!modal.resultados.length" class="nota aviso">No hay artículos sólidos de ese estilo y color. Créalos primero en Artículos.</p>
    <div v-else class="chips">
      <button v-for="a in modal.resultados" :key="a.id" type="button" class="pildora" :disabled="modal.items.some((x) => x.articulo_id === a.id)" @click="agregarComponente(a)">
        <Icono nombre="mas" :tam="13" />{{ a.estilo }} · {{ a.color }} · <b>{{ a.talla }}</b>
      </button>
    </div>
    <template #pie>
      <button class="btn" @click="modal = null">Cancelar</button>
      <button class="btn btn-primario" :disabled="ocupado || !modal.items.length" @click="guardarCurva">Guardar curva</button>
    </template>
  </Modal>
</template>
