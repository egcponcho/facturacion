<script setup>
import { t, tx } from '@/i18n/index.js'
import { computed, onBeforeUnmount, onMounted, reactive, ref, useSlots, watch } from 'vue'
import { api } from '@/nucleo/api'
import { buscador } from '@/nucleo/busqueda.js'
import { sesion, ve } from '@/stores/sesion'
import { filasDefecto } from '@/stores/preferencias'
import FilasEsqueleto from './FilasEsqueleto.vue'
import FiltroColumna from './FiltroColumna.vue'
import Icono from './Icono.vue'
import Paginacion from './Paginacion.vue'
import VistasGuardadas from './VistasGuardadas.vue'

// Tabla de datos común (docs/DISENO.md): todas las tablas del sistema.
// - Barra: buscador de la pantalla (ranura `barra`), vistas guardadas, los
//   demás filtros de la pantalla (`filtros`), «Más filtros» con los
//   secundarios (`mas-filtros`), densidad (compacta, normal, amplia) y
//   «Columnas» (mostrar, ocultar y ordenar).
// - Chips de todos los filtros activos (los de la pantalla y los de columna)
//   y «Limpiar filtros».
// - Cada columna ordena y filtra como Excel: se buscan y marcan uno o varios
//   de sus valores únicos.
// - Columnas, anchos y densidad se guardan por persona; una vista guardada
//   recuerda además los filtros, el orden, las columnas y la densidad.
// - «Prioridad +» en el celular, selección de filas, fila expandible y
//   paginación siempre.
//
// modo 'local': recibe todas las filas; ordena, filtra (y calcula los valores
//   de cada columna) y pagina aquí.
// modo 'servidor': recibe la página y emite `consulta` ({ orden, filtros:
//   {clave: [valores]}, page, size }) cada vez que cambia algo; los valores de
//   una columna los da `valores(clave, q, filtros)` (o sus `opciones`).
//
// columnas: [{ clave, texto, num, ordenable (true), filtro (false = sin filtro),
//   opciones [[valor, texto]], valor (fila) => dato para ordenar y filtrar (en
//   modo local; puede ser una lista), textoValor (valor, fila) => cómo se ve
//   en el filtro, prioridad (1 siempre · 2 desde tableta · 3 escritorio),
//   fija (no se oculta), inicial (false: empieza oculta), grupo (dato que el
//   rol puede no ver), ancho (px) }]
// Ranuras: celda-<clave> ({ fila, valor }), acciones ({ fila }), detalle
//   ({ fila }), barra, filtros, mas-filtros, vacio y pie-<clave> (fila de
//   totales al final: una ranura por columna, con { filas } ya filtradas).
//   `pie-inicio` va en la primera celda (p. ej. «Total»).
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
  // Valores únicos de una columna en modo servidor: (clave, q, filtros) => [{ valor, texto, n }]
  valores: { type: Function, default: null },
  // Vistas guardadas (filtros, orden, columnas y densidad con un nombre). `externos`
  // son los filtros propios de la pantalla que también se guardan; al elegir una
  // vista se devuelven en el evento `vista`.
  vistasGuardadas: { type: Boolean, default: true },
  externos: { type: Object, default: () => ({}) },
  // Filtros de la pantalla que se muestran como chips: [{ clave, texto }]
  chipsExternos: { type: Array, default: () => [] },
  masFiltrosActivos: { type: Number, default: 0 },
  // Selección de filas (v-model:seleccion con las claves); puedeSeleccionar(fila)
  seleccionable: Boolean,
  seleccion: { type: Array, default: () => [] },
  puedeSeleccionar: { type: Function, default: null },
  // Clase de cada fila (p. ej. resaltar una con error): (fila) => string | objeto
  claseFila: { type: Function, default: null },
})
const emit = defineEmits(['consulta', 'fila', 'vista', 'update:seleccion', 'quitar-externo', 'limpiar-externos'])
const slots = useSlots()

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
const ocultas = computed(() => listaColumnas.value.filter((c) => !c.visible).length)
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
const DENSIDADES = [['compacta', t('Compact')], ['normal', t('Normal')], ['amplia', t('Comfortable')]]
function cambiarDensidad(d) {
  conf.densidad = d
  guardar()
}

// ---- Filtros por columna: valores únicos, uno o varios -------------------------------
const VACIO = '__vacio__'
const lista = (v) => (Array.isArray(v) ? v : v === undefined || v === null || v === '' ? [] : [v])
const normalizar = (o) => Object.fromEntries(Object.entries(o || {}).map(([k, v]) => [k, lista(v).map(String)]).filter(([, v]) => v.length))
const orden = ref(props.ordenInicial)
const filtros = reactive(normalizar(props.filtrosIniciales))
const pagina = ref(1)
const tamano = ref(props.porPagina || filasDefecto())
const activos = computed(() => Object.entries(filtros).filter(([, v]) => v?.length))
const filtrable = (c) => c.filtro !== false && (props.modo === 'local' || !!props.valores || !!c.opciones)
const filtrada = (c) => !!filtros[c.clave]?.length

// Cómo se ve cada valor elegido (para los chips), según lo último que mostró el filtro
const etiquetas = reactive({})
const valorDe = (c, fila) => (c.valor ? c.valor(fila) : fila[c.clave])
const claveValor = (v) => (v === null || v === undefined || v === '' ? VACIO : String(v))
function textoValor(c, v, fila) {
  if (claveValor(v) === VACIO) return t('(Empty)')
  const op = c.opciones?.find((o) => String(o[0]) === String(v))
  if (op) return tx(op[1])
  if (c.textoValor) return c.textoValor(v, fila)
  if (typeof v === 'boolean') return v ? t('Yes') : t('No')
  return String(v)
}
const textoElegido = (c, k) => etiquetas[c.clave]?.[k] ?? (k === VACIO ? t('(Empty)') : textoValor(c, k))

// Filas que pasan los filtros (en modo local), sin contar el de la columna `excepto`
function pasan(filas, excepto = null) {
  let res = filas
  for (const [k, vals] of activos.value) {
    if (k === excepto) continue
    const c = props.columnas.find((x) => x.clave === k)
    if (!c) continue
    const set = new Set(vals)
    res = res.filter((f) => {
      const vs = lista(valorDe(c, f))
      return vs.length ? vs.some((v) => set.has(claveValor(v))) : set.has(VACIO)
    })
  }
  return res
}

async function cargarValores(c, q) {
  const otros = Object.fromEntries(activos.value.filter(([k]) => k !== c.clave))
  let res
  if (props.modo === 'local') {
    const cuenta = new Map()
    for (const f of pasan(props.filas, c.clave)) {
      const vs = lista(valorDe(c, f))
      for (const v of vs.length ? vs : [null]) {
        const k = claveValor(v)
        const x = cuenta.get(k)
        if (x) x.n++
        else cuenta.set(k, { valor: k === VACIO ? null : v, texto: textoValor(c, v, f), n: 1 })
      }
    }
    res = [...cuenta.values()]
    const coincide = buscador(q)
    if (q) res = res.filter((x) => coincide([x.texto]))
    res.sort((a, b) => (a.valor === null) - (b.valor === null) || (c.num && typeof a.valor === 'number' && typeof b.valor === 'number'
      ? a.valor - b.valor : String(a.texto).localeCompare(String(b.texto), undefined, { numeric: true })))
  } else if (props.valores) {
    // Con opciones (códigos con su nombre), la búsqueda es sobre el nombre: se trae todo y se filtra aquí
    res = (await props.valores(c.clave, c.opciones ? '' : q, otros)) || []
    res = res.map((x) => ({ ...x, texto: x.texto ?? textoValor(c, x.valor) }))
    if (c.opciones && q) {
      const coincide = buscador(q)
      res = res.filter((x) => coincide([x.texto]))
    }
  } else {
    const coincide = buscador(q)
    res = (c.opciones || []).map(([v, txt]) => ({ valor: v, texto: tx(txt) })).filter((x) => !q || coincide([x.texto]))
  }
  etiquetas[c.clave] = { ...(etiquetas[c.clave] || {}), ...Object.fromEntries(res.map((x) => [claveValor(x.valor), x.texto])) }
  return res
}

const abierto = ref(null) // { c, ancla }
function abrirFiltro(c, e) {
  abierto.value = abierto.value?.c.clave === c.clave ? null : { c, ancla: e.currentTarget }
}
function aplicarFiltro(c, vals) {
  if (vals?.length) filtros[c.clave] = vals.map(String)
  else delete filtros[c.clave]
  abierto.value = null
  pagina.value = 1
}
function quitarFiltro(clave) {
  delete filtros[clave]
  pagina.value = 1
}
function limpiar() {
  for (const k of Object.keys(filtros)) delete filtros[k]
  pagina.value = 1
  emit('limpiar-externos')
}
function textoChip([k, vals]) {
  const c = props.columnas.find((x) => x.clave === k)
  const textos = vals.map((v) => textoElegido(c || { clave: k }, v))
  const ver = textos.slice(0, 2).join(', ') + (textos.length > 2 ? ` ${t('(+{0})', [textos.length - 2])}` : '')
  return `${tx(c?.texto || k)}: ${ver}`
}

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

// Modo servidor: la pantalla pide cada vez que cambia algo
const consulta = () => ({ orden: orden.value, filtros: Object.fromEntries(activos.value.map(([k, v]) => [k, [...v]])),
  page: pagina.value, size: tamano.value })
watch([orden, filtros, pagina, tamano], () => {
  if (props.modo === 'servidor') emit('consulta', consulta())
}, { deep: true })
onMounted(() => {
  if (props.modo === 'servidor') emit('consulta', consulta())
})
defineExpose({ limpiar, pagina, filtros })

// ---- Vistas guardadas: filtros, orden, columnas y densidad ---------------------------
const consultaActual = computed(() => ({
  ...props.externos,
  orden: orden.value,
  ...Object.fromEntries(activos.value.map(([k, v]) => [`f.${k}`, JSON.stringify(v)])),
  ...(conf.columnas ? { _cols: conf.columnas.join(',') } : {}),
  ...(conf.densidad !== 'normal' ? { _dens: conf.densidad } : {}),
}))
function leerValores(v) {
  try {
    const x = JSON.parse(v)
    return lista(x).map(String)
  } catch {
    return [String(v)]
  }
}
function aplicarVista(q) {
  for (const k of Object.keys(filtros)) delete filtros[k]
  const externos = {}
  for (const [k, v] of Object.entries(q || {})) {
    if (k.startsWith('f.')) filtros[k.slice(2)] = leerValores(v)
    else if (!['orden', '_cols', '_dens'].includes(k)) externos[k] = v
  }
  orden.value = q?.orden || ''
  conf.columnas = q?._cols ? q._cols.split(',').filter(Boolean) : null
  conf.densidad = q?._dens || 'normal'
  guardar()
  pagina.value = 1
  emit('vista', externos)
}

// ---- Modo local: ordena, filtra y pagina aquí -------------------------------------------
const procesadas = computed(() => {
  if (props.modo === 'servidor') return props.filas
  let res = pasan(props.filas)
  const [campo, dir] = orden.value.split(':')
  const c = props.columnas.find((x) => x.clave === campo)
  if (c) {
    const s = dir === 'desc' ? -1 : 1
    const v = (f) => {
      const x = valorDe(c, f)
      return Array.isArray(x) ? x.join(', ') : x
    }
    res = [...res].sort((a, b) => {
      const x = v(a)
      const y = v(b)
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
const conPaginacion = computed(() => totalFilas.value > 0 || pagina.value > 1)

// ---- Selección y filas expandidas ---------------------------------------------------------
const clave = (fila) => (typeof props.claveFila === 'function' ? props.claveFila(fila) : fila[props.claveFila])
const elegidas = computed(() => new Set(props.seleccion))
const seleccionables = computed(() => filasPagina.value.filter((f) => !props.puedeSeleccionar || props.puedeSeleccionar(f)).map(clave))
const todasElegidas = computed(() => seleccionables.value.length > 0 && seleccionables.value.every((k) => elegidas.value.has(k)))
function alternarSeleccion(fila) {
  const k = clave(fila)
  emit('update:seleccion', elegidas.value.has(k) ? props.seleccion.filter((x) => x !== k) : [...props.seleccion, k])
}
function alternarTodas() {
  const pagina = new Set(seleccionables.value)
  emit('update:seleccion', todasElegidas.value ? props.seleccion.filter((x) => !pagina.has(x))
    : [...props.seleccion, ...seleccionables.value.filter((k) => !elegidas.value.has(k))])
}
const abiertas = reactive(new Set())
const alternar = (fila) => (abiertas.has(clave(fila)) ? abiertas.delete(clave(fila)) : abiertas.add(clave(fila)))
const nColumnas = computed(() => enPantalla.value.length + (conDetalle.value ? 1 : 0) + (props.seleccionable ? 1 : 0) + 1)

// ---- Menú de columnas y «Más filtros» --------------------------------------------------------
const menuColumnas = ref(false)
const masFiltros = ref(false)
const raiz = ref(null)
function fuera(e) {
  if (!raiz.value?.querySelector('.sel-columnas')?.contains(e.target)) menuColumnas.value = false
}
onMounted(() => document.addEventListener('mousedown', fuera))
onBeforeUnmount(() => document.removeEventListener('mousedown', fuera))
const nFiltros = computed(() => activos.value.length + props.chipsExternos.length)
const hayPie = computed(() => Object.keys(slots).some((k) => k.startsWith('pie-')))
</script>

<template>
  <div ref="raiz" class="td" :class="`td-${conf.densidad}`">
    <div class="filtros" v-filtros>
      <slot name="barra" />
      <VistasGuardadas v-if="vistasGuardadas" :pantalla="tabla" :actual="consultaActual" @aplicar="aplicarVista" />
      <slot name="filtros" />
      <button v-if="slots['mas-filtros']" type="button" class="btn btn-fantasma mas-filtros-toggle" :aria-expanded="masFiltros" @click="masFiltros = !masFiltros">
        <Icono nombre="filtro" :tam="15" />{{ masFiltros ? t('Fewer filters') : t('More filters') }}<span v-if="masFiltrosActivos" class="cuenta">{{ masFiltrosActivos }}</span>
      </button>
      <div class="segmentos td-densidad" role="group" :aria-label="t('Density')">
        <button v-for="[d, txt] in DENSIDADES" :key="d" type="button" class="segmento" :aria-pressed="conf.densidad === d" :title="tx(txt)" @click="cambiarDensidad(d)">
          <span class="td-icono-densidad" :class="d" aria-hidden="true"></span><span class="oculto-visual">{{ tx(txt) }}</span>
        </button>
      </div>
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
          <button type="button" class="btn btn-chico btn-fantasma" @click="restaurar">{{ t('Back to the initial view') }}</button>
        </div>
      </div>
    </div>
    <div v-if="masFiltros && slots['mas-filtros']" class="filtros filtros-avanzados"><slot name="mas-filtros" /></div>
    <div v-if="nFiltros" class="chips">
      <span v-for="x in chipsExternos" :key="`e-${x.clave}`" class="chip">{{ tx(x.texto) }}
        <button type="button" :aria-label="t('Remove {0}', [tx(x.texto)])" @click="emit('quitar-externo', x.clave)"><Icono nombre="cerrar" :tam="13" /></button></span>
      <span v-for="a in activos" :key="a[0]" class="chip">{{ textoChip(a) }}
        <button type="button" :aria-label="t('Remove {0}', [textoChip(a)])" @click="quitarFiltro(a[0])"><Icono nombre="cerrar" :tam="13" /></button></span>
      <button type="button" class="btn btn-fantasma btn-chico" @click="limpiar">{{ t('Clear filters') }}</button>
    </div>

    <div class="tabla-marco" :class="{ 'tabla-fija': conPaginacion }">
      <table class="tabla" :aria-label="tx(etiqueta) || undefined" :aria-busy="cargando">
        <thead>
          <tr>
            <th v-if="seleccionable" class="chk">
              <input type="checkbox" :aria-label="t('Select all on this page')" :checked="todasElegidas" :disabled="!seleccionables.length" @change="alternarTodas" />
            </th>
            <th v-if="conDetalle" class="td-exp"><span class="oculto-visual">{{ t('Detail') }}</span></th>
            <th v-for="c in enPantalla" :key="c.clave" :class="{ num: c.num, 'td-filtrada': filtrada(c) }" :style="estiloColumna(c)"
                :aria-sort="dirOrden(c) === 'asc' ? 'ascending' : dirOrden(c) === 'desc' ? 'descending' : undefined">
              <div class="td-th">
                <button v-if="c.ordenable !== false" type="button" class="orden-btn" :class="{ activo: dirOrden(c) }" @click="ordenar(c)">
                  {{ tx(c.texto) }}<Icono :nombre="dirOrden(c) === 'asc' ? 'arriba' : dirOrden(c) === 'desc' ? 'abajo' : 'arribaabajo'" :tam="12" class="td-flecha" :class="{ activa: dirOrden(c) }" />
                </button>
                <span v-else>{{ tx(c.texto) }}</span>
                <button v-if="filtrable(c)" type="button" class="btn-icono td-filtrar" :class="{ activo: filtrada(c) }" :aria-expanded="abierto?.c.clave === c.clave"
                        :aria-label="t('Filter by {0}', [tx(c.texto)])" :title="t('Filter by {0}', [tx(c.texto)])" @click="abrirFiltro(c, $event)">
                  <Icono nombre="filtro" :tam="13" /><span v-if="filtrada(c)" class="td-n">{{ filtros[c.clave].length }}</span>
                </button>
              </div>
              <span class="td-redim" role="separator" aria-orientation="vertical" tabindex="0" :aria-label="t('Width of {0}', [tx(c.texto)])"
                    @mousedown="empezarAncho($event, c)" @keydown.left.prevent="anchoTeclado($event, c)" @keydown.right.prevent="anchoTeclado($event, c)"></span>
            </th>
            <th class="td-acciones"><span class="oculto-visual">{{ t('Actions') }}</span></th>
          </tr>
        </thead>
        <tbody>
          <template v-for="fila in filasPagina" :key="clave(fila)">
            <tr :class="[{ clicable: filaClicable, seleccionada: seleccionable && elegidas.has(clave(fila)), 'fila-activa': filaActiva !== null && filaActiva === clave(fila) }, claseFila?.(fila)]"
                @click="filaClicable && emit('fila', fila)">
              <td v-if="seleccionable" class="chk" @click.stop>
                <input type="checkbox" :aria-label="t('Select row')" :checked="elegidas.has(clave(fila))"
                       :disabled="!!puedeSeleccionar && !puedeSeleccionar(fila)" @change="alternarSeleccion(fila)" />
              </td>
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
              <template v-if="nFiltros">
                {{ t('No records match these filters.') }}
                <div><button type="button" class="btn btn-chico mt-chico" @click="limpiar">{{ t('Clear filters') }}</button></div>
              </template>
              <slot v-else name="vacio">{{ t('No records yet.') }}</slot>
            </td>
          </tr>
        </tbody>
        <tfoot v-if="hayPie && filasPagina.length">
          <tr>
            <td v-if="seleccionable"></td>
            <td v-if="conDetalle"></td>
            <td v-for="(c, i) in enPantalla" :key="c.clave" :class="{ num: c.num }">
              <slot v-if="i === 0 && slots['pie-inicio'] && !slots[`pie-${c.clave}`]" name="pie-inicio" :filas="procesadas" />
              <slot :name="`pie-${c.clave}`" :filas="procesadas" />
            </td>
            <td></td>
          </tr>
        </tfoot>
      </table>
    </div>
    <Paginacion v-if="conPaginacion" :page="pagina" :size="tamano" :total="totalFilas"
                @cambiar="(p) => (pagina = p)" @tamano="(n) => { tamano = n; pagina = 1 }" />
    <FiltroColumna v-if="abierto" :key="abierto.c.clave" :ancla="abierto.ancla" :titulo="abierto.c.texto" :elegidos="filtros[abierto.c.clave] || []"
                   :cargar="(q) => cargarValores(abierto.c, q)" @aplicar="(v) => aplicarFiltro(abierto.c, v)" @cerrar="abierto = null" />
  </div>
</template>

<style scoped>
.td-menu { width: 300px; }
.td-menu ul { list-style: none; margin: 0; padding: 0; }
.td-menu li { justify-content: space-between; gap: 6px; padding: 2px 6px; }
.td-mover { display: inline-flex; }
.td-icono-densidad { display: inline-block; width: 14px; height: 12px; background:
  linear-gradient(currentColor, currentColor) 0 0 / 100% 2px no-repeat,
  linear-gradient(currentColor, currentColor) 0 50% / 100% 2px no-repeat,
  linear-gradient(currentColor, currentColor) 0 100% / 100% 2px no-repeat; }
.td-icono-densidad.compacta { height: 8px; }
.td-icono-densidad.amplia { height: 15px; }
.td-densidad .segmento { padding-inline: 9px; }
.td-th { display: flex; align-items: center; gap: 2px; }
th.num .td-th { justify-content: flex-end; }
.td-flecha { opacity: 0.35; }
.td-flecha.activa { opacity: 1; color: var(--acento); }
/* El embudo de cada columna siempre a la vista, más fuerte al pasar o con el filtro puesto */
.td-filtrar { padding: 3px; opacity: 0.45; display: inline-flex; align-items: center; gap: 2px; }
.td-filtrar.activo, .td-filtrar[aria-expanded='true'], th:hover .td-filtrar, .td-filtrar:focus-visible { opacity: 1; }
.td-filtrar.activo { color: var(--acento); }
.td-n { font-size: 0.68rem; font-weight: 700; }
th { position: relative; }
.td-filtrada { background: var(--acento-claro); }
.td-redim { position: absolute; top: 0; inset-inline-end: -3px; width: 7px; height: 100%; cursor: col-resize; z-index: 3; }
.td-redim:hover, .td-redim:focus-visible { background: var(--acento-medio); outline: none; }
.td-exp { width: 36px; }
.td-acciones { width: 1%; white-space: nowrap; text-align: end; }
.td-datos { display: grid; grid-template-columns: minmax(110px, auto) 1fr; gap: 4px 14px; margin: 0 0 8px; font-size: var(--t-sm); padding: 10px 16px 0; }
.td-datos dt { color: var(--tinta-3); }
.td-datos dd { margin: 0; min-width: 0; }
/* Densidad: alto de las filas */
.td-compacta :deep(.tabla td), .td-compacta :deep(.tabla th) { padding-top: 4px; padding-bottom: 4px; font-size: 0.84rem; }
.td-compacta :deep(.tabla .sub) { display: inline; margin-inline-start: 6px; }
.td-amplia :deep(.tabla td) { padding-top: 16px; padding-bottom: 16px; }
@media (max-width: 720px) {
  .td-densidad { display: none; }
}
</style>
