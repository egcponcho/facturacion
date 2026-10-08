<script setup>
import { t, tx } from '../i18n/index.js'
import { puede } from '../stores/sesion'
import { computed, onMounted, reactive, ref, watch } from 'vue'
import Seleccion from '../components/Seleccion.vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api'
import BotonesExportar from '../components/BotonesExportar.vue'
import CargaArchivo from '../components/CargaArchivo.vue'
import CargaArticulos from '../components/CargaArticulos.vue'
import ArticulosGenericos from '../components/ArticulosGenericos.vue'
import CargaMasiva from '../components/CargaMasiva.vue'
import EditorReglaLT from '../components/EditorReglaLT.vue'
import Icono from '../components/Icono.vue'
import Modal from '../components/Modal.vue'
import ExplosionPrepack from '../components/ExplosionPrepack.vue'
import GenericoModal from '../components/GenericoModal.vue'
import Paginacion from '../components/Paginacion.vue'
import SelectBusqueda from '../components/SelectBusqueda.vue'
import ThOrden from '../components/ThOrden.vue'
import { siguienteOrden } from '../composables/useTabla'
import { avisar, errorApi } from '../stores/ui'
import { fmtNum } from '../utils'
import { filasDefecto } from '../stores/preferencias'

// Un solo lugar para todos los datos maestros. Cada catálogo llega descrito
// desde el servidor (campos, tipos, obligatorios, filtros) y esta vista dibuja
// el formulario, los filtros y la tabla a partir de esa descripción.
const route = useRoute()
const router = useRouter()
const catalogos = ref([])
const tipo = ref(route.query.catalogo || 'articulos')
const datos = ref({ items: [], total: 0 })
const filtros = reactive({ q: '', orden: '', page: 1, size: filasDefecto(), extra: {} })
const opciones = reactive({})
const form = ref({})
const editando = ref(null)
const erroresForm = ref({})
const modal = ref(null)
const ocupado = ref(false)
const formAbierto = ref(false) // alta y edición en ventana emergente
const genericoNuevo = ref(false)
// Artículos: compacto por genérico (por defecto) o listado de todos los artículos
const leerVista = () => { try { return localStorage.getItem('mant.vistaArticulos') } catch { return null } }
const vista = ref(route.query.vista || leerVista() || 'compacta')
const recarga = ref(0)
const compacta = computed(() => tipo.value === 'articulos' && vista.value === 'compacta')
function cambiarVista(v) {
  vista.value = v
  try { localStorage.setItem('mant.vistaArticulos', v) } catch { /* sin almacenamiento */ }
  cargar()
}
const ESTADO_FICHA = { borrador: t('Sheet in draft'), sugerida: t('Draft complete'), revision: t('In review'), observado: t('Returned') }

const cat = computed(() => catalogos.value.find((c) => c.tipo === tipo.value))
// Catálogos de uso diario: a la vista; los de configuración, en «Más catálogos»
const PRINCIPALES = ['articulos', 'prepacks', 'marcas', 'proveedores', 'grupos', 'centros']
const principales = computed(() => catalogos.value.filter((c) => PRINCIPALES.includes(c.tipo)))
const otros = computed(() => catalogos.value.filter((c) => !PRINCIPALES.includes(c.tipo)))
const campos = computed(() => cat.value?.campos || [])
const columnas = computed(() => campos.value.filter((c) => !['descripcion', 'direccion', 'razon_social', 'upc'].includes(c.nombre) &&
  !(c.nombre === 'correos' && tipo.value !== 'contactos')))
const extras = computed(() => cat.value?.extras || [])
// Campos que dependen de otro para mostrarse (p. ej. el país solo en una regla de nivel país)
const camposVisibles = computed(() => campos.value.filter((c) => !c.mostrar_si || c.mostrar_si.valores.includes(form.value?.[c.mostrar_si.campo])))
// Opciones para la lista con búsqueda: por id (ref) o por código
// Campo dependiente (c.depende): solo las opciones relacionadas con el valor del
// campo del que depende (p. ej. las marcas del proveedor elegido)
const valida = (c, o, datos) => {
  const dep = c.depende
  const base = dep && datos ? datos[dep.campo] : ''
  if (!dep || base === '' || base === null || base === undefined) return true
  const dato = o[dep.clave]
  return Array.isArray(dato) ? dato.map(String).includes(String(base)) : String(dato) === String(base)
}
const opcionesDe = (c, datos = null) => (opciones[c.catalogo] || []).filter((o) => valida(c, o, datos))
  .map((o) => ({ valor: ['ref', 'multi'].includes(c.tipo) ? o.id : o.codigo, texto: o.texto, sub: o.sub }))
// Al cambiar el campo base, se quita lo que ya no corresponde
watch(() => campos.value.filter((c) => c.depende).map((c) => form.value?.[c.depende.campo]), () => {
  for (const c of campos.value.filter((x) => x.depende)) {
    const v = form.value?.[c.nombre]
    if (v === '' || v === null || v === undefined) continue
    const validos = new Set(opcionesDe(c, form.value).map((o) => String(o.valor)))
    if (Array.isArray(v)) form.value[c.nombre] = v.filter((x) => validos.has(String(x)))
    else if (!validos.has(String(v))) form.value[c.nombre] = ''
  }
})
const conFiltro = computed(() => campos.value.filter((c) => c.filtro && !(compacta.value && ['tipo', 'activo'].includes(c.nombre))))

function vacio() {
  const f = {}
  for (const c of campos.value) f[c.nombre] = c.tipo === 'bool' ? true : c.tipo === 'multi' ? [] : c.tipo === 'regla_lt' ? { pasos: [], orden: null } : ''
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
  if (compacta.value) {
    recarga.value++
    return
  }
  try {
    datos.value = await api.get(`/catalogos/${tipo.value}`, {
      q: filtros.q, orden: filtros.orden, page: filtros.page, size: filtros.size, ...filtros.extra,
    })
  } catch (e) {
    errorApi(e)
  }
}

async function elegir(t, extra = {}, q = '') {
  if (t === 'prepacks' && !solidos.value.length) cargarSolidos()
  tipo.value = t
  router.replace({ query: { catalogo: t } })
  Object.assign(filtros, { q, orden: '', page: 1, extra: { ...extra } })
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
  for (const c of campos.value) f[c.nombre] = c.tipo === 'multi' ? [...(fila[c.nombre] || [])] : c.tipo === 'regla_lt' ? JSON.parse(JSON.stringify(fila[c.nombre] || { pasos: [], orden: null })) : fila[c.nombre] ?? (c.tipo === 'bool' ? false : '')
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
      avisar(t('{0} updated.', [cap(cat.value.singular)]))
    } else {
      await api.post(`/catalogos/${tipo.value}`, cuerpo)
      avisar(t('{0} created.', [cap(cat.value.singular)]))
      cat.value.total++
    }
    cerrarForm()
    delete opciones[tipo.value]
    cargar()
  } catch (e) {
    if (Array.isArray(e.detalle)) erroresForm.value = e.detalle.filter((d) => d.campo).reduce((o, d) => ({ ...o, [d.campo]: o[d.campo] ? `${o[d.campo]} ${d.mensaje}` : d.mensaje }), {})
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
    avisar(t('{0} deleted.', [cap(cat.value.singular)]))
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
  if (c.tipo === 'regla_lt') return fila[`${c.nombre}_txt`] || '—'
  if (c.tipo === 'opcion') return c.opciones.find((o) => o[0] === v)?.[1] || v
  if (c.tipo === 'codigo') return opciones[c.catalogo]?.find((o) => o.codigo === v)?.texto || v
  return v
}
const campoActivo = computed(() => campos.value.find((c) => c.tipo === 'bool' && ['activo', 'activa'].includes(c.nombre))?.nombre || campos.value.find((c) => c.tipo === 'bool')?.nombre)

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
    avisar(t('{0} created and {1} updated{2}.', [r.creados, r.actualizados, r.errores.length ? t('; {0} rows with errors', [r.errores.length]) : '']),
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
watch(() => [nuevoPP.estilo, nuevoPP.color], async () => {
  nuevoPP.cantidades = {}
  // El prepack lleva el genérico de sus sólidos; se propone genérico + código libre
  const gen = tallasPP.value[0]?.generico
  if (!gen) return
  try {
    const d = await api.get(`/catalogos/genericos/${encodeURIComponent(gen)}`)
    if (!nuevoPP.sku || !nuevoPP.sku.startsWith(gen)) nuevoPP.sku = `${gen}${d.siguiente}`
  } catch {
    /* sin genérico registrado: se escribe a mano */
  }
})
async function crearPrepack() {
  ocupado.value = true
  erroresPP.value = {}
  try {
    const componentes = tallasPP.value.filter((a) => Number(nuevoPP.cantidades[a.id]) > 0)
      .map((a) => ({ articulo_id: a.id, cantidad: Number(nuevoPP.cantidades[a.id]) }))
    const r = await api.post('/catalogos/prepacks', { ...nuevoPP, cantidades: undefined, componentes })
    avisar(t('Prepack {0} created with item code {1} ({2} per carton).', [r.codigo, r.sku, r.total]))
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
  // Desde la búsqueda global: ?catalogo=proveedores&q=VANS abre el catálogo ya filtrado
  await elegir(tipo.value, {}, String(route.query.q || ''))
})
</script>

<template>
  <div class="pagina-cabeza">
    <div>
      <h1>{{ t('Master data') }}</h1>
      <p>{{ t('Master data used across the system: it validates the PO upload, defines the packing rules and feeds the filters. Every catalog can be edited here, loaded from Excel and exported with the filters you apply. The technical sheet, description and HS code of each item live in Products.') }}</p>
    </div>
    <div class="acciones">
      <MasOpciones>
        <BotonesExportar v-if="cat" :ruta="`/catalogos/${tipo}/exportar`" :params="{ q: filtros.q, orden: filtros.orden, ...filtros.extra }" />
        <router-link v-if="tipo === 'leadtimes' || tipo === 'pasos_lt'" class="btn" to="/leadtimes"><Icono nombre="reloj" :tam="15" />{{ t('Effective lead time') }}</router-link>
        <a v-if="tipo === 'prepacks'" class="btn" href="/plantilla_prepacks.csv" download><Icono nombre="descargar" />{{ t('Template') }}</a>
        <button v-if="cat && puede('catalogos.crear')" class="btn" @click="abrirCarga"><Icono nombre="importar" />{{ tx(tipo === 'articulos' ? t('Upload items and sheets') : tipo === 'prepacks' ? t('Upload size runs') : t('Upload Excel')) }}</button>
      </MasOpciones>
      <button v-if="tipo === 'articulos' && puede('catalogos.crear')" class="btn btn-primario" :title="t('Generic (style-color) with its sizes')" @click="genericoNuevo = true"><Icono nombre="mas" />{{ t('New generic') }}</button>
      <button v-else-if="cat && tipo !== 'articulos' && puede('catalogos.crear')" class="btn btn-primario" @click="abrirNuevo"><Icono nombre="mas" />{{ t('New {0}', [cat.singular]) }}</button>
    </div>
  </div>

  <!-- En el celular, un selector en lugar de las 16 pestañas -->
  <label class="selector-catalogo solo-movil">
    <span>{{ t('Catalog') }}</span>
    <Seleccion class="entrada" :value="tipo" @change="elegir">
      <option v-for="c in catalogos" :key="c.tipo" :value="c.tipo">{{ tx(c.titulo) }} ({{ tx(c.total) }})</option>
    </Seleccion>
  </label>
  <!-- Los catálogos de uso diario como pestañas; el resto en una lista con búsqueda -->
  <div class="selector-catalogos solo-escritorio">
    <div class="pestanas-pildora" role="tablist">
      <button v-for="c in principales" :key="c.tipo" class="pildora" role="tab" :aria-selected="c.tipo === tipo" @click="elegir(c.tipo)">
        {{ tx(c.titulo) }}<span class="cuenta">{{ tx(c.total) }}</span>
      </button>
    </div>
    <SelectBusqueda :model-value="otros.some((c) => c.tipo === tipo) ? tipo : ''" :opciones="otros.map((c) => ({ valor: c.tipo, texto: c.titulo, sub: String(c.total) }))"
                    :vacio="t('More catalogs')" :etiqueta="t('Catalog')" :prefijo="false" :busqueda="true" class="selector-otros"
                    :class="{ activo: otros.some((c) => c.tipo === tipo) }" @update:model-value="(v) => v && elegir(v)" />
  </div>

  <div v-if="cat">

    <section>
      <div class="filtros" v-filtros>
        <label class="buscador">
          <Icono nombre="buscar" :tam="16" />
          <input v-model="filtros.q" type="search" :placeholder="tx(compacta ? t('Search generic, style, color, item code, UPC or supplier SKU') : t('Search {0}', [cat.titulo.toLowerCase()]))" :aria-label="t('Search')" @input="buscar" />
        </label>
        <div v-if="tipo === 'articulos'" class="segmentos" role="group" :aria-label="t('Items view')">
          <button type="button" class="segmento" :aria-pressed="vista === 'compacta'" :title="t('One row per generic; expand it to see its sizes')" @click="cambiarVista('compacta')">{{ t('Compact') }}</button>
          <button type="button" class="segmento" :aria-pressed="vista === 'lista'" :title="t('One row per item code')" @click="cambiarVista('lista')">{{ t('List') }}</button>
        </div>
        <template v-for="c in conFiltro" :key="c.nombre">
          <SelectBusqueda v-if="['ref', 'codigo', 'multi'].includes(c.tipo)" v-model="filtros.extra[c.nombre]" :opciones="opcionesDe(c, filtros.extra)"
                          :vacio="t('{0}: all', [tx(c.etiqueta)])" :etiqueta="tx(c.etiqueta)" @change="filtros.page = 1; cargar()" />
          <Seleccion v-else v-model="filtros.extra[c.nombre]" :aria-label="tx(c.etiqueta)" @change="filtros.page = 1; cargar()">
            <option :value="undefined">{{ t('{0}: all', [tx(c.etiqueta)]) }}</option>
            <template v-if="c.tipo === 'bool'"><option value="true">{{ t('{0}: yes', [c.etiqueta]) }}</option><option value="false">{{ t('{0}: no', [c.etiqueta]) }}</option></template>
            <template v-else-if="c.tipo === 'opcion'"><option v-for="[v, txt] in c.opciones" :key="v" :value="v">{{ tx(c.etiqueta) }}: {{ tx(txt) }}</option></template>
          </Seleccion>
        </template>
      </div>
      <ArticulosGenericos v-if="compacta" :q="filtros.q" :extra="filtros.extra" :recarga="recarga"
                          @editar-articulo="editar" @eliminar-articulo="(fila) => (modal = { tipo: 'eliminar', fila })" @desglose="(a) => (explosion = { sku: a.sku })" @cambio="cargarMeta" />
      <template v-else>
      <div class="tabla-marco tabla-fija">
        <table class="tabla" v-tarjetas>
          <thead>
            <tr>
              <ThOrden v-for="c in columnas" :key="c.nombre" :campo="c.nombre" :orden="filtros.orden" :num="c.tipo === 'entero'" @ordenar="ordenar">{{ tx(c.etiqueta) }}</ThOrden>
              <th v-for="ex in extras" :key="ex.nombre">{{ tx(ex.etiqueta) }}</th>
              <th v-if="tipo === 'articulos'" :title="t('The technical sheet, description and HS code belong to the style and color')">{{ t('HS code · description') }}</th>
              <th v-if="tipo === 'prepacks'">{{ t('Item code') }}</th>
              <th v-if="tipo === 'prepacks'" class="num">{{ t('Per carton') }}</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="fila in datos.items" :key="fila.id" :class="{ seleccionada: editando === fila.id }">
              <td v-for="c in columnas" :key="c.nombre" :class="{ num: c.tipo === 'entero' }">
                <button v-if="c.tipo === 'bool'" type="button" class="etiqueta" :disabled="!puede('catalogos.editar')" :class="fila[c.nombre] ? 'ok' : ''" style="border: 0; cursor: pointer" :title="t('Change {0}', [c.etiqueta.toLowerCase()])" @click="alternarActivo(fila, c.nombre)">
                  {{ tx(fila[c.nombre] ? t('Yes') : t('No')) }}
                </button>
                <span v-else :class="{ codigo: ['codigo', 'sku'].includes(c.nombre), fuerte: c.nombre === 'codigo' || c.nombre === 'sku' }">{{ tx(valorCelda(c, fila)) }}</span>
              </td>
              <td v-for="ex in extras" :key="ex.nombre">
                <button type="button" class="enlace" :title="t('See {0} of {1}', [ex.etiqueta.toLowerCase(), fila.codigo || fila.nombre])"
                        @click="elegir(ex.catalogo, { [ex.filtro]: fila.id })">
                  {{ tx(ex.nombre === 'centros_txt' ? (fila.centros_txt || t('Assign plants')) : `${fila[ex.nombre] || 0} ${fila[ex.nombre] === 1 ? ex.etiqueta.toLowerCase().replace(/s$/, '') : ex.etiqueta.toLowerCase()}`) }}
                </button>
              </td>
              <td v-if="tipo === 'articulos'">
                <router-link v-if="fila.producto_id" :to="`/productos/${fila.producto_id}`" class="enlace" :title="t('Technical sheet of {0} {1}', [fila.estilo, fila.color])">
                  <span v-if="fila.partida_txt" class="codigo-sac">{{ tx(fila.partida_txt) }}</span>
                  <template v-else>{{ tx(ESTADO_FICHA[fila.clasificacion] || t('Open sheet')) }}</template>
                </router-link>
                <span v-else class="apagado">—</span>
                <span v-if="fila.descripcion" class="sub" style="max-width: 280px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis" :title="tx(fila.descripcion)">{{ tx(fila.descripcion) }}</span>
              </td>
              <td v-if="tipo === 'prepacks'" class="codigo fuerte">{{ tx(fila.sku || '—') }}</td>
              <td v-if="tipo === 'prepacks'" class="num">{{ tx(fila.total) }} <span class="sub">{{ t('{0} sizes', [fila.componentes]) }}</span></td>
              <td class="num" style="white-space: nowrap">
                <button v-if="tipo === 'prepacks' || fila.tipo === 'PREPACK'" class="btn btn-chico" :title="t('See the breakdown (it never changes)')"
                        @click="explosion = { sku: fila.sku }"><Icono nombre="lupa" :tam="13" />{{ t('Breakdown') }}</button>
                <button v-if="puede('catalogos.editar')" class="btn-icono" :aria-label="t('Edit {0}', [cat.singular])" :title="t('Edit')" @click="editar(fila)"><Icono nombre="editar" :tam="16" /></button>
                <button v-if="puede('catalogos.eliminar')" class="btn-icono" style="color: var(--error)" :aria-label="t('Delete {0}', [cat.singular])" :title="t('Delete')" @click="modal = { tipo: 'eliminar', fila }"><Icono nombre="basura" :tam="16" /></button>
              </td>
            </tr>
            <tr v-if="!datos.items.length"><td :colspan="columnas.length + extras.length + (tipo === 'prepacks' ? 3 : tipo === 'articulos' ? 3 : 2)" class="vacio">{{ t('No records match these filters.') }}</td></tr>
          </tbody>
        </table>
      </div>
      <Paginacion :page="filtros.page" :size="filtros.size" :total="datos.total" @cambiar="(p) => { filtros.page = p; cargar() }" @tamano="(t) => (filtros.size = t)" />
      </template>
    </section>
  </div>

  <Modal v-if="formAbierto && cat" :titulo="tx(editando ? t('Edit {0}', [cat.singular]) : t('New {0}', [cat.singular]))" ancho="640px" @cerrar="cerrarForm">
    <p v-if="cat.ayuda" class="ayuda" style="margin-top: 0">{{ tx(cat.ayuda) }}</p>
      <form v-if="tipo === 'prepacks' && !editando" class="form-catalogo" @submit.prevent="crearPrepack">
        <label class="campo"><span class="req">{{ t('Item code') }}</span>
          <input v-model="nuevoPP.sku" maxlength="40" :placeholder="t('Your item code for the prepack')" required />
          <small v-if="erroresPP.sku" class="nota error" style="padding: 4px 8px">{{ tx(erroresPP.sku) }}</small>
          <small v-else class="ayuda">{{ t('Any code in your format. The prepack takes the generic of its solids; a code is proposed when you choose style and color.') }}</small>
        </label>
        <label class="campo"><span class="req">{{ t('Style') }}</span>
          <SelectBusqueda v-model="nuevoPP.estilo" :opciones="estilosPP" requerido :etiqueta="t('Style')" />
        </label>
        <label class="campo"><span class="req">{{ t('Color') }}</span>
          <SelectBusqueda v-model="nuevoPP.color" :opciones="coloresPP" requerido :etiqueta="t('Color')" :deshabilitado="!nuevoPP.estilo" />
        </label>
        <label class="campo"><span class="req">{{ t('Prepack ID (size)') }}</span>
          <input v-model="nuevoPP.codigo" maxlength="10" placeholder="AB12" style="text-transform: uppercase" required />
          <small v-if="erroresPP.codigo" class="nota error" style="padding: 4px 8px">{{ tx(erroresPP.codigo) }}</small>
          <small v-else class="ayuda">{{ t('Usually 2 letters and 2 digits. It is the size of the prepack item.') }}</small>
        </label>
        <label class="campo"><span>{{ t('Description') }}</span><input v-model="nuevoPP.descripcion" /></label>
        <div v-if="nuevoPP.estilo && nuevoPP.color" class="campo">
          <span class="req">{{ t('Breakdown per master carton') }}<template v-if="tallasPP.length"> ({{ tx(tallasPP[0].unidad) }})</template></span>
          <div class="tabla-marco" style="box-shadow: none">
            <table class="tabla" v-tarjetas>
              <thead><tr><th>{{ t('Size') }}</th><th>SKU</th><th class="num">{{ t('Qty') }}</th></tr></thead>
              <tbody>
                <tr v-for="a in tallasPP" :key="a.id">
                  <td><b>{{ tx(a.talla) }}</b></td>
                  <td class="codigo">{{ tx(a.sku) }}</td>
                  <td class="num"><input v-model.number="nuevoPP.cantidades[a.id]" class="celda num" type="number" min="0" style="width: 64px; border-color: var(--linea)" :aria-label="t('Quantity size {0}', [a.talla])" /></td>
                </tr>
              </tbody>
              <tfoot><tr><td colspan="2">{{ t('Total per carton') }}</td><td class="num">{{ tx(totalPP) }}</td></tr></tfoot>
            </table>
          </div>
          <small v-if="erroresPP.componentes" class="nota error" style="padding: 4px 8px">{{ tx(erroresPP.componentes) }}</small>
          <small v-else class="ayuda">{{ t('Only solids of {0} {1}. Leave at 0 the sizes it does not carry. Once created it never changes.', [nuevoPP.estilo, nuevoPP.color]) }}</small>
        </div>
        <p class="leyenda-req">{{ t('Required') }}</p>
        <button class="btn btn-primario" type="submit" :disabled="ocupado || !totalPP"><Icono nombre="mas" :tam="16" />{{ t('Create prepack') }}</button>
      </form>
      <form v-else class="form-catalogo" @submit.prevent="guardar">
        <component :is="c.tipo === 'regla_lt' ? 'div' : 'label'" v-for="c in camposVisibles" :key="c.nombre" :class="c.tipo === 'bool' ? 'check' : 'campo'">
          <template v-if="c.tipo === 'bool'">
            <input v-model="form[c.nombre]" type="checkbox" /> {{ tx(c.etiqueta) }}
          </template>
          <template v-else>
            <span :class="{ req: c.obligatorio }">{{ tx(c.etiqueta) }}</span>
            <Seleccion v-if="c.tipo === 'opcion'" v-model="form[c.nombre]" :required="c.obligatorio" :disabled="bloqueado(c)">
              <option value="">{{ t('Choose…') }}</option>
              <option v-for="[v, txt] in opcionesCampo(c)" :key="v" :value="v">{{ tx(txt) }}</option>
            </Seleccion>
            <SelectBusqueda v-else-if="c.tipo === 'ref' || c.tipo === 'codigo'" v-model="form[c.nombre]" :opciones="opcionesDe(c, form)"
                            :vacio="tx(c.obligatorio ? '' : t('None'))" :requerido="c.obligatorio" :etiqueta="tx(c.etiqueta)" :deshabilitado="bloqueado(c)" />
            <SelectBusqueda v-else-if="c.tipo === 'multi'" v-model="form[c.nombre]" :opciones="opcionesDe(c, form)" multiple
                            :placeholder="t('Choose one or more…')" :requerido="c.obligatorio" :etiqueta="tx(c.etiqueta)" />
            <EditorReglaLT v-else-if="c.tipo === 'regla_lt'" v-model="form[c.nombre]" :form="form" :regla-id="editando" />
            <textarea v-else-if="c.tipo === 'correos'" v-model="form[c.nombre]" rows="2" :required="c.obligatorio"
                      :placeholder="t('name@company.com, other@company.com')"></textarea>
            <input v-else v-model="form[c.nombre]" :type="c.tipo === 'entero' || c.tipo === 'numero' ? 'number' : 'text'"
                   :min="c.minimo" :maxlength="c.max" :required="c.obligatorio" :disabled="bloqueado(c)" :title="tx(bloqueado(c) ? t('Cannot change: it is part of the prepack') : '')" />
            <small v-if="erroresForm[c.nombre]" class="nota error" style="padding: 4px 8px">{{ tx(erroresForm[c.nombre]) }}</small>
            <small v-else-if="c.ayuda" class="ayuda">{{ tx(c.ayuda) }}</small>
          </template>
        </component>
        <p class="leyenda-req">{{ t('Required') }}</p>
        <div class="fila-flex">
          <button class="btn btn-primario" type="submit" :disabled="ocupado"><Icono :nombre="editando ? 'check' : 'mas'" :tam="16" />{{ tx(editando ? t('Save changes') : t('Create {0}', [cat.singular])) }}</button>
          <button class="btn btn-fantasma" type="button" @click="cerrarForm">{{ t('Cancel') }}</button>
        </div>
      </form>
  </Modal>

  <Modal v-if="modal?.tipo === 'eliminar'" :titulo="t('Delete {0}', [cat.singular])" @cerrar="modal = null">
    <p>{{ t('Delete') }} <b>{{ tx(modal.fila.codigo || modal.fila.sku) }}</b>{{ t('? If other records already use it, it cannot be deleted; deactivate it instead.') }}</p>
    <template #pie>
      <button class="btn" @click="modal = null">{{ t('Cancel') }}</button>
      <button class="btn btn-peligro" :disabled="ocupado" @click="eliminar">{{ t('Delete') }}</button>
    </template>
  </Modal>

  <CargaArticulos v-if="modal?.tipo === 'carga' && tipo === 'articulos'" @cerrar="modal = null" @listo="cargarMeta(); cargar()" />
  <CargaMasiva v-else-if="modal?.tipo === 'carga' && tipo !== 'prepacks'" :titulo="t('Upload {0}', [cat.titulo.toLowerCase()])" :ruta="`/catalogos/${tipo}/importar`"
               :plantilla="`/catalogos/${tipo}/plantilla`" :ayuda="tx(cat.ayuda)" @cerrar="modal = null" @cargado="cargarMeta(); cargar()" />
  <Modal v-else-if="modal?.tipo === 'carga'" :titulo="t('Upload size runs (prepacks)')" ancho="680px" @cerrar="modal = null">
    <p class="ayuda">{{ t('One row per size of the breakdown: sku_prepack (item code of the prepack), prepack_id (e.g. AB12), description, solid SKU and quantity. Style and color come from the solids, which must share style and color. It creates the prepack and its item; an existing prepack is never changed.') }}</p>
    <CargaArchivo v-model="modal.archivo" />
    <template v-if="modal.resultado">
      <div class="nota ok"><Icono nombre="check" />{{ t('{0} created and {1} updated.', [modal.resultado.creados, modal.resultado.actualizados]) }}</div>
      <div v-if="modal.resultado.errores.length" class="tabla-marco" style="max-height: 240px; overflow: auto; box-shadow: none">
        <table class="tabla" v-tarjetas>
          <thead><tr><th>{{ t('Row') }}</th><th>{{ t('Error') }}</th></tr></thead>
          <tbody><tr v-for="(er, i) in modal.resultado.errores" :key="i"><td>{{ tx(er.fila) }}</td><td class="envolver">{{ tx(er.mensaje) }}</td></tr></tbody>
        </table>
      </div>
    </template>
    <template #pie>
      <button class="btn" @click="modal = null">{{ t('Close') }}</button>
      <button class="btn btn-primario" :disabled="ocupado || !modal.archivo" @click="cargarArchivo"><Icono nombre="importar" :tam="16" />{{ t('Upload') }}</button>
    </template>
  </Modal>

  <GenericoModal v-if="genericoNuevo" @cerrar="genericoNuevo = false" @listo="genericoNuevo = false; cargarMeta(); cargar()" />
  <ExplosionPrepack v-if="explosion" :sku="explosion.sku" @cerrar="explosion = null" />
</template>
