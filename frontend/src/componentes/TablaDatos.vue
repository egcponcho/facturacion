<script setup>
import { t, tx } from '@/i18n/index.js'
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { api } from '@/nucleo/api'
import { buscador } from '@/nucleo/busqueda.js'
import { sesion, ve } from '@/stores/sesion'
import { filasDefecto } from '@/stores/preferencias'
import FilasEsqueleto from './FilasEsqueleto.vue'
import Icono from './Icono.vue'
import Paginacion from './Paginacion.vue'
import VistasGuardadas from './VistasGuardadas.vue'

// Tabla de datos común (docs/DISENO.md), con el aspecto de la tabla de órdenes
// de compra: barra de filtros de la pantalla, vistas guardadas y «Columnas»
// (con la densidad); chips de los filtros activos; encabezados que ordenan;
// filtro por columna (el embudo aparece al pasar por el encabezado);
// columnas que se muestran, se ocultan, se reordenan y se ensanchan (se guardan
// por persona); tres densidades; «prioridad +» en el celular (las columnas
// secundarias pasan al detalle de la fila); paginación y fila expandible.
//
// modo 'local': recibe todas las filas y ordena, filtra y pagina aquí.
// modo 'servidor': recibe la página y emite `consulta` ({ orden, filtros,
// page, size }) cada vez que cambia algo, para que la pantalla pida al servidor.
//
// columnas: [{ clave, texto, num, ordenable (true), filtro ('texto' | 'opcion'),
//   opciones [[valor, texto]], valor (fila) => dato para ordenar y filtrar en
//   modo local, prioridad (1 siempre visible · 2 desde tableta · 3 escritorio),
//   fija (no se oculta), inicial (false: empieza oculta), grupo (dato que el rol
//   puede no ver), ancho (px) }]
// Ranuras: celda-<clave> ({ fila, valor }), acciones ({ fila }),
//   detalle ({ fila }), barra (el buscador, va primero), filtros (los demás
//   filtros de la pantalla, después de las vistas guardadas), vacio.
const props = defineProps({
  tabla: { type: String, required: true },
  columnas: { type: Array, required: true },
  filas: { type: Array, default: () => [] },
  modo: { type: String, default: 'local' },
  total: { type: Number, default: 0 },
  cargando: Boolean,
  claveFila: { type: [String, Function], default: 'id' },
  expandible: Boolean,
  ordenInicial: { type: String, default: '' },
  filtrosIniciales: { type: Object, default: () => ({}) },
  porPagina: { type: Number, default: 0 },
  filaClicable: Boolean,
  filaActiva: { type: [String, Number], default: null },
  etiqueta: { type: String, default: '' },
  // Vistas guardadas: combinaciones de filtros con nombre. `externos` son los
  // filtros propios de la pantalla (vista predefinida, búsqueda) que también
  // se guardan; al elegir una vista se devuelven en el evento `vista`.
  vistasGuardadas: Boolean,
  externos: { type: Object, default: () => ({}) },
  // Tabla dentro de un documento (líneas, cajas): sin barra ni paginación si cabe en una página
  sinBarra: Boolean,
})
const emit = defineEmits(['consulta', 'fila', 'vista'])

// ---- Configuración guardada de la persona ------------------------------------
const guardada = () => sesion.usuario?.preferencias?.tablas?.[props.tabla] || {}
const conf = reactive({
  columnas: guardada().columnas || sesion.usuario?.preferencias?.columnas?.[props.tabla] || null,
  anchos: { ...(guardada().anchos || {}) },
  densidad: guardada().densidad || 'normal',
})
let reloj = null
function guardar() {
  clearTimeout(reloj)
  reloj = setTimeout(async () => {
    try {
      const r = await api.put(`/perfil/tablas/${props.tabla}`, { columnas: conf.columnas, anchos: conf.anchos, densidad: conf.densidad })
      if (sesion.usuario) sesion.usuario.preferencias = { ...(sesion.usuario.preferencias || {}), tablas: r.tablas }
    } catch {
      /* la tabla sigue funcionando aunque no se guarde la preferencia */
    }
  }, 600)
}
async function restaurar() {
  Object.assign(conf, { columnas: null, anchos: {}, densidad: 'normal' })
  try {
    const r = await api.put(`/perfil/tablas/${props.tabla}`, null)
    if (sesion.usuario) sesion.usuario.preferencias = { ...(sesion.usuario.preferencias || {}), tablas: r.tablas }
  } catch {
    /* sin efecto */
  }
}

// ---- Columnas ------------------------------------------------------------------
const permitidas = computed(() => props.columnas.filter((c) => !c.grupo || ve(c.grupo)))
const visibles = computed(() => {
  if (!conf.columnas) return permitidas.value.filter((c) => c.fija || c.inicial !== false)
  const porClave = Object.fromEntries(permitidas.value.map((c) => [c.clave, c]))
  const elegidas = conf.columnas.map((k) => porClave[k]).filter(Boolean)
  const fijas = permitidas.value.filter((c) => c.fija && !conf.columnas.includes(c.clave))
  return [...fijas, ...elegidas]
})
function ordenColumnas() {
  // Todas las permitidas en el orden actual: primero las visibles, luego las ocultas
  const vis = visibles.value.map((c) => c.clave)
  return [...vis, ...permitidas.value.map((c) => c.clave).filter((k) => !vis.includes(k))]
}
const listaColumnas = computed(() => {
  const vis = new Set(visibles.value.map((c) => c.clave))
  const porClave = Object.fromEntries(permitidas.value.map((c) => [c.clave, c]))
  return ordenColumnas().map((k) => ({ ...porClave[k], visible: vis.has(k) }))
})
function alternarColumna(clave) {
  const vis = visibles.value.map((c) => c.clave)
  conf.columnas = vis.includes(clave) ? vis.filter((k) => k !== clave) : [...vis, clave]
  guardar()
}
function moverColumna(clave, paso) {
  const todas = ordenColumnas()
  const i = todas.indexOf(clave)
  const j = i + paso
  if (j < 0 || j >= todas.length) return
  ;[todas[i], todas[j]] = [todas[j], todas[i]]
  const vis = new Set(visibles.value.map((c) => c.clave))
  conf.columnas = todas.filter((k) => vis.has(k))
  guardar()
}

// «Prioridad +»: en pantallas angostas solo las columnas principales; el resto
// se ve en el detalle de la fila
const ancho = ref(window.innerWidth)
const medir = () => { ancho.value = window.innerWidth }
onMounted(() => window.addEventListener('resize', medir))
onBeforeUnmount(() => { window.removeEventListener('resize', medir); clearTimeout(reloj) })
const limite = computed(() => (ancho.value <= 720 ? 1 : ancho.value <= 900 ? 2 : 3))
const enPantalla = computed(() => visibles.value.filter((c) => c.fija || (c.prioridad ?? 2) <= limite.value))
const ocultasPorEspacio = computed(() => visibles.value.filter((c) => !enPantalla.value.includes(c)))
const conDetalle = computed(() => props.expandible || ocultasPorEspacio.value.length > 0)

// ---- Ancho de las columnas (arrastrando el borde del encabezado) -----------------
let arrastre = null
function empezarAncho(e, c) {
  const th = e.target.closest('th')
  arrastre = { clave: c.clave, x: e.clientX, ancho: th.getBoundingClientRect().width }
  window.addEventListener('mousemove', moverAncho)
  window.addEventListener('mouseup', soltarAncho, { once: true })
  e.preventDefault()
}
function moverAncho(e) {
  if (!arrastre) return
  conf.anchos[arrastre.clave] = Math.max(48, Math.min(900, Math.round(arrastre.ancho + e.clientX - arrastre.x)))
}
function soltarAncho() {
  window.removeEventListener('mousemove', moverAncho)
  arrastre = null
  guardar()
}
function anchoTeclado(e, c) {
  const actual = conf.anchos[c.clave] || e.target.closest('th').getBoundingClientRect().width
  conf.anchos[c.clave] = Math.max(48, Math.min(900, Math.round(actual + (e.key === 'ArrowRight' ? 16 : -16))))
  guardar()
}
const estiloColumna = (c) => {
  const w = conf.anchos[c.clave] || c.ancho
  return w ? { width: `${w}px`, minWidth: `${w}px`, maxWidth: `${w}px` } : null
}
function cambiarDensidad(d) {
  conf.densidad = d
  guardar()
}

// ---- Orden, filtros y página -------------------------------------------------------
const orden = ref(props.ordenInicial)
const filtros = reactive({ ...props.filtrosIniciales })
const pagina = ref(1)
const tamano = ref(props.porPagina || filasDefecto())
const activos = computed(() => Object.entries(filtros).filter(([, v]) => v !== '' && v !== null && v !== undefined))
function cerrarFiltro(clave) {
  quitarFiltro(clave)
  filtroAbierto.value = null
}
const filtroAbierto = ref(null)
const textoFiltro = ref('')

function ordenar(c) {
  if (c.ordenable === false) return
  const [campo, dir] = orden.value.split(':')
  orden.value = campo !== c.clave ? `${c.clave}:asc` : dir === 'asc' ? `${c.clave}:desc` : ''
  pagina.value = 1
}
const dirOrden = (c) => {
  const [campo, dir] = orden.value.split(':')
  return campo === c.clave ? dir : ''
}
function abrirFiltro(c) {
  filtroAbierto.value = filtroAbierto.value === c.clave ? null : c.clave
  textoFiltro.value = filtros[c.clave] ?? ''
}
function aplicarFiltro(c, v) {
  filtros[c.clave] = v
  filtroAbierto.value = null
  pagina.value = 1
}
function quitarFiltro(clave) {
  delete filtros[clave]
  pagina.value = 1
}
function limpiar() {
  for (const k of Object.keys(filtros)) delete filtros[k]
  pagina.value = 1
}
const textoActivo = ([k, v]) => {
  const c = props.columnas.find((x) => x.clave === k)
  const txt = c?.opciones?.find((o) => String(o[0]) === String(v))?.[1] ?? v
  return `${tx(c?.texto || k)}: ${tx(txt)}`
}

// Modo servidor: la pantalla pide cada vez que cambia algo
watch([orden, filtros, pagina, tamano], () => {
  if (props.modo === 'servidor') emit('consulta', { orden: orden.value, filtros: { ...filtros }, page: pagina.value, size: tamano.value })
}, { deep: true })
onMounted(() => {
  if (props.modo === 'servidor') emit('consulta', { orden: orden.value, filtros: { ...filtros }, page: pagina.value, size: tamano.value })
})
defineExpose({ limpiar, pagina, filtros })

// Vista guardada: los filtros de las columnas van con «f.» delante
const consultaActual = computed(() => ({ ...props.externos, orden: orden.value,
  ...Object.fromEntries(activos.value.map(([k, v]) => [`f.${k}`, v])) }))
function aplicarVista(q) {
  for (const k of Object.keys(filtros)) delete filtros[k]
  const externos = {}
  for (const [k, v] of Object.entries(q || {})) {
    if (k.startsWith('f.')) filtros[k.slice(2)] = v
    else if (k !== 'orden') externos[k] = v
  }
  orden.value = q?.orden || ''
  pagina.value = 1
  emit('vista', externos)
}

// Modo local: ordena, filtra y pagina aquí
const valorDe = (c, fila) => (c.valor ? c.valor(fila) : fila[c.clave])
const procesadas = computed(() => {
  if (props.modo === 'servidor') return props.filas
  let res = props.filas
  for (const [k, v] of activos.value) {
    const c = props.columnas.find((x) => x.clave === k)
    if (!c) continue
    if (c.filtro === 'opcion') res = res.filter((f) => String(valorDe(c, f) ?? '') === String(v))
    else {
      const coincide = buscador(String(v))
      res = res.filter((f) => coincide([valorDe(c, f)]))
    }
  }
  const [campo, dir] = orden.value.split(':')
  const c = props.columnas.find((x) => x.clave === campo)
  if (c) {
    const s = dir === 'desc' ? -1 : 1
    res = [...res].sort((a, b) => {
      const x = valorDe(c, a)
      const y = valorDe(c, b)
      if (x === y) return 0
      if (x === null || x === undefined || x === '') return 1
      if (y === null || y === undefined || y === '') return -1
      return (typeof x === 'number' && typeof y === 'number' ? x - y : String(x).localeCompare(String(y), undefined, { numeric: true })) * s
    })
  }
  return res
})
const totalFilas = computed(() => (props.modo === 'servidor' ? props.total : procesadas.value.length))
const filasPagina = computed(() => (props.modo === 'servidor' ? props.filas
  : procesadas.value.slice((pagina.value - 1) * tamano.value, pagina.value * tamano.value)))
watch(() => props.filas, () => {
  if (props.modo === 'local' && (pagina.value - 1) * tamano.value >= procesadas.value.length) pagina.value = 1
})

// ---- Filas expandidas ---------------------------------------------------------------
const clave = (fila) => (typeof props.claveFila === 'function' ? props.claveFila(fila) : fila[props.claveFila])
const abiertas = reactive(new Set())
const alternar = (fila) => (abiertas.has(clave(fila)) ? abiertas.delete(clave(fila)) : abiertas.add(clave(fila)))
const nColumnas = computed(() => enPantalla.value.length + (conDetalle.value ? 1 : 0) + 1)

// ---- Menú de columnas ----------------------------------------------------------------
const menuColumnas = ref(false)
const raiz = ref(null)
function fuera(e) {
  if (!raiz.value?.contains(e.target)) {
    menuColumnas.value = false
    filtroAbierto.value = null
  }
}
onMounted(() => document.addEventListener('mousedown', fuera))
onBeforeUnmount(() => document.removeEventListener('mousedown', fuera))
const DENSIDADES = [['compacta', t('Compact')], ['normal', t('Normal')], ['amplia', t('Comfortable')]]
const filtrada = (c) => filtros[c.clave] !== undefined && filtros[c.clave] !== ''
const ocultas = computed(() => listaColumnas.value.filter((c) => !c.visible).length)
// Como en órdenes de compra: el pie con el total y las filas por página siempre
// que haya filas (una tabla dentro de un documento solo si no cabe en una página)
const conPaginacion = computed(() => (props.sinBarra ? totalFilas.value > tamano.value || pagina.value > 1 : totalFilas.value > 0 || pagina.value > 1))
const vFoco = { mounted: (el) => el.focus() }
</script>

<template>
  <div ref="raiz" class="td" :class="`td-${conf.densidad}`">
    <div v-if="!sinBarra" class="filtros" v-filtros>
      <slot name="barra" />
      <VistasGuardadas v-if="vistasGuardadas" :pantalla="tabla" :actual="consultaActual" @aplicar="aplicarVista" />
      <slot name="filtros" />
      <div class="sel-columnas" @keydown.esc="menuColumnas = false">
        <button type="button" class="btn btn-fantasma" :aria-expanded="menuColumnas" aria-haspopup="true" @click="menuColumnas = !menuColumnas">
          <Icono nombre="columnas" :tam="16" />{{ t('Columns') }}<span v-if="ocultas" class="cuenta">{{ listaColumnas.length - ocultas }}/{{ listaColumnas.length }}</span>
        </button>
        <div v-if="menuColumnas" class="sel-columnas-menu td-menu" role="dialog" :aria-label="t('Columns')">
          <p class="sel-columnas-ayuda">{{ t('Show, hide and order the columns. Drag the edge of a header to make it wider.') }}</p>
          <ul>
            <li v-for="(c, i) in listaColumnas" :key="c.clave" class="sel-columnas-op">
              <label class="check"><input type="checkbox" :checked="c.visible" :disabled="c.fija" @change="alternarColumna(c.clave)" />{{ tx(c.texto) }}</label>
              <span class="td-mover">
                <button type="button" class="btn-icono" :disabled="i === 0" :aria-label="t('Move {0} up', [tx(c.texto)])" @click="moverColumna(c.clave, -1)"><Icono nombre="arriba" :tam="14" /></button>
                <button type="button" class="btn-icono" :disabled="i === listaColumnas.length - 1" :aria-label="t('Move {0} down', [tx(c.texto)])" @click="moverColumna(c.clave, 1)"><Icono nombre="abajo" :tam="14" /></button>
              </span>
            </li>
          </ul>
          <div class="td-densidad">
            <span class="sel-columnas-ayuda">{{ t('Density') }}</span>
            <div class="segmentos" role="group" :aria-label="t('Density')">
              <button v-for="[d, txt] in DENSIDADES" :key="d" type="button" class="segmento" :aria-pressed="conf.densidad === d" @click="cambiarDensidad(d)">{{ tx(txt) }}</button>
            </div>
          </div>
          <button type="button" class="btn btn-chico btn-fantasma" @click="restaurar">{{ t('Back to the initial view') }}</button>
        </div>
      </div>
    </div>
    <div v-if="activos.length" class="chips">
      <span v-for="a in activos" :key="a[0]" class="chip">{{ textoActivo(a) }}
        <button type="button" :aria-label="t('Remove {0}', [textoActivo(a)])" @click="quitarFiltro(a[0])"><Icono nombre="cerrar" :tam="13" /></button></span>
      <button type="button" class="btn btn-fantasma btn-chico" @click="limpiar">{{ t('Clear filters') }}</button>
    </div>

    <div class="tabla-marco" :class="{ 'tabla-fija': conPaginacion }">
      <table class="tabla" :aria-label="tx(etiqueta) || undefined" :aria-busy="cargando">
        <thead>
          <tr>
            <th v-if="conDetalle" class="td-exp"><span class="oculto-visual">{{ t('Detail') }}</span></th>
            <th v-for="c in enPantalla" :key="c.clave" :class="{ num: c.num, 'td-filtrada': filtrada(c) }" :style="estiloColumna(c)"
                :aria-sort="dirOrden(c) === 'asc' ? 'ascending' : dirOrden(c) === 'desc' ? 'descending' : undefined">
              <div class="td-th">
                <button v-if="c.ordenable !== false" type="button" class="orden-btn" :class="{ activo: dirOrden(c) }" @click="ordenar(c)">
                  {{ tx(c.texto) }}<Icono :nombre="dirOrden(c) === 'asc' ? 'arriba' : dirOrden(c) === 'desc' ? 'abajo' : 'arribaabajo'" :tam="12" class="td-flecha" :class="{ activa: dirOrden(c) }" />
                </button>
                <span v-else>{{ tx(c.texto) }}</span>
                <button v-if="c.filtro" type="button" class="btn-icono td-filtrar" :class="{ activo: filtrada(c) }" :aria-expanded="filtroAbierto === c.clave"
                        :aria-label="t('Filter by {0}', [tx(c.texto)])" @click="abrirFiltro(c)"><Icono nombre="filtro" :tam="13" /></button>
              </div>
              <div v-if="filtroAbierto === c.clave" class="td-filtro" @click.stop>
                <template v-if="c.filtro === 'opcion'">
                  <button v-for="[v, txt] in c.opciones" :key="v" type="button" class="td-opcion" :aria-pressed="String(filtros[c.clave]) === String(v)" @click="aplicarFiltro(c, v)">{{ tx(txt) }}</button>
                </template>
                <form v-else @submit.prevent="aplicarFiltro(c, textoFiltro.trim() || undefined)">
                  <input v-model="textoFiltro" v-foco class="entrada" type="search" :placeholder="t('Contains…')" :aria-label="t('Filter by {0}', [tx(c.texto)])" />
                  <button type="submit" class="btn btn-chico btn-primario">{{ t('Apply') }}</button>
                </form>
                <button v-if="filtrada(c)" type="button" class="btn btn-fantasma btn-chico" @click="cerrarFiltro(c.clave)">{{ t('Remove filter') }}</button>
              </div>
              <span class="td-redim" role="separator" aria-orientation="vertical" tabindex="0" :aria-label="t('Width of {0}', [tx(c.texto)])"
                    @mousedown="empezarAncho($event, c)" @keydown.left.prevent="anchoTeclado($event, c)" @keydown.right.prevent="anchoTeclado($event, c)"></span>
            </th>
            <th class="td-acciones"><span class="oculto-visual">{{ t('Actions') }}</span></th>
          </tr>
        </thead>
        <tbody>
          <template v-for="fila in filasPagina" :key="clave(fila)">
            <tr :class="{ clicable: filaClicable, 'fila-activa': filaActiva !== null && filaActiva === clave(fila) }" @click="filaClicable && emit('fila', fila)">
              <td v-if="conDetalle" class="td-exp">
                <button type="button" class="btn-icono" :aria-expanded="abiertas.has(clave(fila))" :aria-label="t('Show detail')" @click.stop="alternar(fila)">
                  <Icono :nombre="abiertas.has(clave(fila)) ? 'abajo' : 'derecha'" :tam="16" /></button>
              </td>
              <td v-for="c in enPantalla" :key="c.clave" :class="{ num: c.num }" :style="estiloColumna(c)">
                <slot :name="`celda-${c.clave}`" :fila="fila" :valor="fila[c.clave]">{{ tx(fila[c.clave] ?? '—') }}</slot>
              </td>
              <td class="td-acciones" @click.stop><slot name="acciones" :fila="fila" /></td>
            </tr>
            <tr v-if="conDetalle && abiertas.has(clave(fila))" class="fila-hija">
              <td :colspan="nColumnas">
                <dl v-if="ocultasPorEspacio.length" class="td-datos">
                  <template v-for="c in ocultasPorEspacio" :key="c.clave">
                    <dt>{{ tx(c.texto) }}</dt>
                    <dd><slot :name="`celda-${c.clave}`" :fila="fila" :valor="fila[c.clave]">{{ tx(fila[c.clave] ?? '—') }}</slot></dd>
                  </template>
                </dl>
                <slot name="detalle" :fila="fila" />
              </td>
            </tr>
          </template>
          <FilasEsqueleto v-if="cargando && !filasPagina.length" :columnas="nColumnas" />
          <tr v-if="!cargando && !filasPagina.length">
            <td :colspan="nColumnas" class="vacio">
              <template v-if="activos.length">
                {{ t('No records match these filters.') }}
                <div><button type="button" class="btn btn-chico mt-chico" @click="limpiar">{{ t('Clear filters') }}</button></div>
              </template>
              <slot v-else name="vacio">{{ t('No records yet.') }}</slot>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <Paginacion v-if="conPaginacion" :page="pagina" :size="tamano" :total="totalFilas"
                @cambiar="(p) => (pagina = p)" @tamano="(n) => { tamano = n; pagina = 1 }" />
  </div>
</template>

<style scoped>
.td-menu { width: 300px; }
.td-menu ul { list-style: none; margin: 0; padding: 0; }
.td-menu li { justify-content: space-between; gap: 6px; padding: 2px 6px; }
.td-mover { display: inline-flex; }
.td-densidad { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin: 8px 0 0; padding-top: 8px; border-top: 1px solid var(--linea-suave); }
.td-densidad .sel-columnas-ayuda { margin: 0 6px; }
.td-th { display: flex; align-items: center; gap: 2px; }
th.num .td-th { justify-content: flex-end; }
.td-flecha { opacity: 0.35; }
.td-flecha.activa { opacity: 1; color: var(--acento); }
/* El embudo no recarga el encabezado: aparece al pasar o con el filtro puesto */
.td-filtrar { padding: 3px; opacity: 0; transition: opacity 0.12s; }
.td-filtrar.activo, .td-filtrar[aria-expanded='true'], .td-filtrar:focus-visible, th:hover .td-filtrar { opacity: 1; }
@media (hover: none) { .td-filtrar { opacity: 0.5; } }
.td-filtrar.activo { color: var(--acento); }
th { position: relative; }
.td-filtrada { background: var(--acento-claro); }
.td-filtro { position: absolute; top: calc(100% + 4px); inset-inline-start: 0; z-index: 25; min-width: 220px; padding: 8px; display: flex; flex-direction: column; gap: 6px;
  background: var(--superficie); border: 1px solid var(--linea); border-radius: var(--radio); box-shadow: var(--sombra-flotante); font-weight: 400; text-transform: none; letter-spacing: 0; }
.td-filtro form { display: flex; gap: 6px; }
.td-opcion { border: 1px solid transparent; background: none; text-align: start; padding: 5px 8px; border-radius: 6px; cursor: pointer; font: inherit; color: var(--tinta); }
.td-opcion:hover { background: var(--fila-hover); }
.td-opcion[aria-pressed='true'] { border-color: var(--acento); color: var(--acento-texto); }
.td-redim { position: absolute; top: 0; inset-inline-end: -3px; width: 7px; height: 100%; cursor: col-resize; z-index: 3; }
.td-redim:hover, .td-redim:focus-visible { background: var(--acento-medio); outline: none; }
.td-exp { width: 36px; }
.td-acciones { width: 1%; white-space: nowrap; text-align: end; }
.td-datos { display: grid; grid-template-columns: minmax(110px, auto) 1fr; gap: 4px 14px; margin: 0 0 8px; font-size: var(--t-sm); }
.td-datos dt { color: var(--tinta-3); }
.td-datos dd { margin: 0; min-width: 0; }
/* Densidad: alto de las filas */
.td-compacta :deep(.tabla td), .td-compacta :deep(.tabla th) { padding-top: 4px; padding-bottom: 4px; font-size: 0.84rem; }
.td-amplia :deep(.tabla td) { padding-top: 14px; padding-bottom: 14px; }
</style>
