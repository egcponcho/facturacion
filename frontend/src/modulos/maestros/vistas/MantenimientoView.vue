<script setup>
import { t, tr, tx } from '@/i18n/index.js'
import { computed, onMounted, reactive, ref, watch } from 'vue'
import Seleccion from '@/componentes/Seleccion.vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '@/nucleo/api'
import BotonesExportar from '@/componentes/BotonesExportar.vue'
import CargaArchivo from '@/componentes/CargaArchivo.vue'
import CargaArticulos from '@/modulos/maestros/componentes/CargaArticulos.vue'
import ArticulosGenericos from '@/modulos/maestros/componentes/ArticulosGenericos.vue'
import CargaMasiva from '@/componentes/CargaMasiva.vue'
import EditorReglaLT from '@/modulos/maestros/componentes/EditorReglaLT.vue'
import Icono from '@/componentes/Icono.vue'
import Modal from '@/componentes/Modal.vue'
import ExplosionPrepack from '@/componentes/ExplosionPrepack.vue'
import SelectBusqueda from '@/componentes/SelectBusqueda.vue'
import TablaDatos from '@/componentes/TablaDatos.vue'
import { avisar, errorApi } from '@/stores/ui'
import { ACCIONES, fmtFecha, fmtFechaHora } from '@/nucleo/utils'
import { catalogosHermanos } from '@/nucleo/modulos.js'

// Un solo lugar para todos los datos maestros. Cada catálogo llega descrito
// desde el servidor (campos, tipos, obligatorios, filtros) y esta vista dibuja
// el formulario y la tabla a partir de esa descripción. La tabla (TablaDatos
// en modo servidor, una por catálogo) filtra cada columna por sus valores; el
// buscador va por fuera.
const route = useRoute()
const router = useRouter()
const catalogos = ref([])
const tipo = ref(route.query.catalogo || 'articulos')
const datos = ref({ items: [], total: 0 })
const filtros = reactive({ q: '' })
const cargando = ref(false)
const tabla = ref(null)
// Filtros de columna con los que se abre el catálogo (p. ej. los centros de una
// sociedad) y la última consulta de la tabla (orden, filtros y página)
const iniciales = ref({})
const ultima = ref(null)
// Cada vez que se elige un catálogo, su tabla se arma de nuevo (sus columnas y su vista)
const montaje = ref(0)
const opciones = reactive({})
const form = ref({})
const editando = ref(null)
const erroresForm = ref({})
const modal = ref(null)
const ocupado = ref(false)
const formAbierto = ref(false) // alta y edición en ventana emergente
// Artículos: compacto por genérico (por defecto) o listado de todos los artículos
const leerVista = () => { try { return localStorage.getItem('mant.vistaArticulos') } catch { return null } }
const vista = ref(route.query.vista || leerVista() || 'compacta')
const recarga = ref(0)
const compacta = computed(() => tipo.value === 'articulos' && vista.value === 'compacta')
function cambiarVista(v) {
  if (v === vista.value) return
  vista.value = v
  try { localStorage.setItem('mant.vistaArticulos', v) } catch { /* sin almacenamiento */ }
  // La otra tabla se monta y pide sus datos; conserva los filtros de columna que comparten
  iniciales.value = filtrosComunes(ultima.value?.filtros || iniciales.value)
  ultima.value = null
  datos.value = { items: [], total: 0 }
}
const ESTADO_FICHA = { borrador: t('Sheet in draft'), sugerida: t('Draft complete'), revision: t('In review'), observado: t('Returned') }

const cat = computed(() => catalogos.value.find((c) => c.tipo === tipo.value))
// Lo que el usuario puede hacer en este catálogo: sus permisos y, si el
// catálogo tiene responsables, que su rol sea uno de ellos (lo decide el servidor)
const acciones = computed(() => cat.value?.puede || {})
// Catálogos de uso diario: a la vista; los de configuración, en «Más catálogos»
const PRINCIPALES = ['articulos', 'prepacks', 'marcas', 'proveedores', 'grupos', 'centros']
// Cada módulo ve solo sus catálogos (nucleo/modulos.js): los de productos en
// Productos, los de lugares y transportistas en Logística…
const hermanos = computed(() => catalogosHermanos(tipo.value))
const delModulo = computed(() => (hermanos.value ? catalogos.value.filter((c) => hermanos.value.includes(c.tipo)) : catalogos.value))
const principales = computed(() => delModulo.value.filter((c) => PRINCIPALES.includes(c.tipo) || delModulo.value.length <= 6))
const otros = computed(() => delModulo.value.filter((c) => !principales.value.includes(c)))
const campos = computed(() => cat.value?.campos || [])
// Un campo que solo aplica a algunos registros (mostrar_si) empieza visible si
// aplica a lo filtrado en su columna base o, sin filtro, si algún registro de la página lo tiene
const aplica = (c) => {
  if (!c.mostrar_si) return true
  const elegidos = ultima.value?.filtros?.[c.mostrar_si.campo] || []
  if (elegidos.length) return elegidos.some((v) => c.mostrar_si.valores.includes(v))
  return datos.value.items.some((f) => ![null, undefined, ''].includes(f[c.nombre]) && !(Array.isArray(f[c.nombre]) && !f[c.nombre].length))
}
const extras = computed(() => cat.value?.extras || [])
// Columnas de la tabla: un campo por columna (los largos, como la dirección,
// empiezan ocultos), luego los registros relacionados y lo propio del catálogo.
// Cada columna filtra por sus valores (el servidor da los valores únicos); las
// calculadas (relacionados, ficha técnica, total por caja, regla de lead time) no.
const OCULTAS = ['descripcion', 'direccion', 'razon_social', 'upc']
const SI_NO = [[true, t('Yes')], [false, t('No')]]
function opcionesColumna(c) {
  if (c.tipo === 'bool') return c.propio ? undefined : SI_NO
  if (c.tipo === 'opcion') return c.opciones
  if (['ref', 'multi', 'codigo'].includes(c.tipo) && c.catalogo) {
    return (opciones[c.catalogo] || []).map((o) => [c.tipo === 'codigo' ? o.codigo : o.id, o.texto])
  }
  return undefined
}
function textoValorColumna(c) {
  // Campo propio sí/no: el servidor lo da como texto (true/1)
  if (c.tipo === 'bool' && c.propio) return (v) => (['true', '1'].includes(String(v).toLowerCase()) ? t('Yes') : t('No'))
  if (c.tipo === 'opciones') return (v) => String(v).split(',').filter(Boolean).map((k) => tx(c.opciones.find((o) => o[0] === k)?.[1] || k)).join(', ')
  if (c.tipo === 'fecha') return (v) => fmtFecha(v)
  return undefined
}
const columnasTabla = computed(() => [
  ...campos.value.map((c, i) => ({
    clave: c.nombre, texto: c.etiqueta, num: ['entero', 'numero'].includes(c.tipo), fija: i === 0,
    prioridad: i < 2 ? 1 : i < 4 ? 2 : 3,
    inicial: !OCULTAS.includes(c.nombre) && !(c.nombre === 'correos' && tipo.value !== 'contactos') && aplica(c),
    ordenable: !['multi', 'regla_lt'].includes(c.tipo), filtro: c.tipo === 'regla_lt' ? false : undefined,
    opciones: opcionesColumna(c), textoValor: textoValorColumna(c),
  })),
  ...extras.value.map((ex) => ({ clave: ex.nombre, texto: ex.etiqueta, ordenable: false, filtro: false, prioridad: 3 })),
  ...(tipo.value === 'articulos' ? [{ clave: 'ficha', texto: t('HS code · description'), ordenable: false, filtro: false, prioridad: 3 }] : []),
  ...(tipo.value === 'prepacks' ? [{ clave: 'sku', texto: t('Item code'), prioridad: 1 },
    { clave: 'total', texto: t('Per carton'), num: true, ordenable: false, filtro: false, prioridad: 2 }] : []),
])
// Valores únicos de una columna (del servidor, bajo los demás filtros)
const valoresColumna = (columna, buscar, otros) => api.get(`/catalogos/${tipo.value}/valores`, { columna, buscar, q: filtros.q || undefined, f: JSON.stringify(otros) })
// Nombre de una referencia (marca, grupo, proveedor…) por su id, para los filtros de la vista por genérico
function nombreRef(clave, v) {
  const c = campos.value.find((x) => x.nombre === clave)
  const o = c?.catalogo && (opciones[c.catalogo] || []).find((x) => String(x.id) === String(v))
  return o ? o.texto : v
}
// Filtros por campo «por fuera» (en Más filtros): son los mismos filtros de su columna
const filtroFuera = (c) => tabla.value?.filtros?.[c.nombre]?.[0] ?? ''
function ponerFiltroFuera(c, v) {
  if (!tabla.value) return
  if (v === '' || v === null || v === undefined) delete tabla.value.filtros[c.nombre]
  else tabla.value.filtros[c.nombre] = [String(v)]
  tabla.value.pagina = 1
}
const fueraActivos = computed(() => conFiltro.value.filter((c) => filtroFuera(c) !== '').length)
// Filtros de columna que la vista por genérico y el listado de artículos comparten
const COMUNES = ['generico', 'estilo', 'color', 'marca_id', 'grupo_id', 'proveedor_id', 'unidad']
const filtrosComunes = (fs) => Object.fromEntries(Object.entries(fs || {}).filter(([k]) => COMUNES.includes(k)))
const conFiltro = computed(() => campos.value.filter((c) => c.filtro && ['ref', 'codigo', 'multi', 'bool', 'opcion'].includes(c.tipo)))
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

// ---- Secciones: primero lo común; lo propio de la empresa, al final
const SECCIONES = [['general', t('General data')], ['variante', t('Variant attributes')], ['comercial', t('Commercial')], ['logistica', t('Logistics')],
  ['contacto', t('Contact')], ['estado', t('Status')], ['propios', t('Own fields')]]
const porSeccion = (lista) => SECCIONES.map(([clave, titulo]) => ({ clave, titulo, campos: lista.filter((c) => (c.seccion || 'general') === clave) }))
  .filter((x) => x.campos.length)
const seccionesForm = computed(() => porSeccion(camposVisibles.value))
const etiquetaCampo = (n) => campos.value.find((c) => c.nombre === n)?.etiqueta || n

// ---- Ver un registro (solo lectura, con su historial); «Editar» abre el formulario
const viendo = ref(null) // { fila, historial }
const camposVista = computed(() => porSeccion(campos.value.filter((c) => !c.mostrar_si || c.mostrar_si.valores.includes(viendo.value?.fila?.[c.mostrar_si.campo]))))
async function ver(fila) {
  viendo.value = { fila, historial: null, versiones: null }
  try {
    const h = await api.get(`/catalogos/${tipo.value}/${fila.id}/historial`)
    if (viendo.value?.fila === fila) viendo.value.historial = h
  } catch (e) {
    errorApi(e)
    if (viendo.value) viendo.value.historial = []
  }
  // Un artículo muestra también sus versiones: cómo era cuando cada OC o factura lo usó
  if (tipo.value === 'articulos') {
    try {
      const v = await api.get(`/catalogos/articulos/${fila.id}/versiones`)
      if (viendo.value?.fila === fila) viendo.value.versiones = v
    } catch (e) {
      errorApi(e)
      if (viendo.value) viendo.value.versiones = []
    }
  }
}
const cambiosVersion = (v) => v.cambios.slice(0, 8).map((c) => `${c.campo}: ${valorTxt(c.antes)} → ${valorTxt(c.despues)}`).join(' · ')
  + (v.cambios.length > 8 ? ` · +${v.cambios.length - 8}` : '')
function editarDesdeVista() {
  const fila = viendo.value.fila
  viendo.value = null
  editar(fila)
}
const valorTxt = (v) => (v === null || v === undefined || v === '' ? '—' : Array.isArray(v) ? v.join(', ') || '—'
  : typeof v === 'boolean' ? (v ? t('Yes') : t('No')) : String(v))
function cambiosTxt(h) {
  const d = h.detalle
  if (!d || typeof d !== 'object' || Array.isArray(d)) return ''
  return Object.entries(d).map(([k, v]) => (Array.isArray(v) && v.length === 2
    ? `${tx(etiquetaCampo(k))}: ${valorTxt(v[0])} → ${valorTxt(v[1])}` : `${tx(etiquetaCampo(k))}: ${valorTxt(v)}`)).join(' · ')
}

// ---- Gobierno del catálogo: responsables y datos que la empresa exige (administración)
const roles = ref([])
const gob = ref(null) // { responsables: [rol_id], obligatorios: [campo] }
async function abrirGobierno() {
  try {
    if (!roles.value.length) roles.value = (await api.get('/roles')).roles.filter((r) => r.activo).map((r) => ({ valor: r.id, texto: r.nombre }))
    gob.value = { responsables: cat.value.gobierno.responsables.map((r) => r.id), obligatorios: [...cat.value.gobierno.obligatorios] }
  } catch (e) {
    errorApi(e)
  }
}
async function guardarGobierno() {
  ocupado.value = true
  try {
    await api.put(`/catalogos/${tipo.value}/gobierno`, gob.value)
    gob.value = null
    avisar(t('Catalog governance saved.'))
    await cargarMeta()
  } catch (e) {
    errorApi(e)
  } finally {
    ocupado.value = false
  }
}

function vacio() {
  const f = {}
  for (const c of campos.value) f[c.nombre] = c.tipo === 'bool' ? !c.propio : ['multi', 'opciones'].includes(c.tipo) ? [] : c.tipo === 'regla_lt' ? { pasos: [], orden: null } : ''
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

// La tabla pide cada vez que cambia su orden, sus filtros o su página
async function consultar(c = ultima.value) {
  if (!c || !cat.value) return
  ultima.value = c
  const t = tipo.value
  cargando.value = true
  try {
    const r = await api.get(`/catalogos/${t}`, {
      q: filtros.q, orden: c.orden, page: c.page, size: c.size, f: Object.keys(c.filtros).length ? JSON.stringify(c.filtros) : undefined,
    })
    if (t === tipo.value) datos.value = r // una respuesta tardía de otro catálogo no pisa la tabla
  } catch (e) {
    errorApi(e)
  } finally {
    cargando.value = false
  }
}
// Después de guardar algo: la misma página con los mismos filtros
function cargar() {
  if (!cat.value) return
  if (compacta.value) recarga.value++
  else consultar()
}
// La búsqueda vuelve a la primera página
function recargar() {
  if (compacta.value) recarga.value++
  else if (tabla.value && tabla.value.pagina !== 1) tabla.value.pagina = 1
  else consultar()
}

// extra: filtros de columna con los que se abre ({ sociedad_id: 3 } = los de esa sociedad)
async function elegir(t, extra = {}, q = '') {
  if (t === 'prepacks' && !solidos.value.length) cargarSolidos()
  tipo.value = t
  router.replace({ query: { catalogo: t } })
  filtros.q = q
  iniciales.value = Object.fromEntries(Object.entries(extra).map(([k, v]) => [k, [String(v)]]))
  ultima.value = null
  datos.value = { items: [], total: 0 }
  editando.value = null
  erroresForm.value = {}
  form.value = vacio()
  await cargarOpciones()
  montaje.value++
}

let espera
function buscar() {
  clearTimeout(espera)
  espera = setTimeout(recargar, 300)
}
// Exportar con lo que se ve: búsqueda, filtros de columna y orden (la vista por
// genérico exporta sus artículos con los filtros que comparten)
const paramsExportar = computed(() => {
  const c = ultima.value || { orden: '', filtros: {} }
  const fs = compacta.value ? Object.fromEntries(Object.entries(c.filtros).map(([k, v]) => [k === 'tallas' ? 'talla' : k, v])) : c.filtros
  return { q: filtros.q, orden: c.orden || undefined, f: Object.keys(fs).length ? JSON.stringify(fs) : undefined }
})

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
  for (const c of campos.value) f[c.nombre] = ['multi', 'opciones'].includes(c.tipo) ? [...(fila[c.nombre] || [])] : c.tipo === 'regla_lt' ? JSON.parse(JSON.stringify(fila[c.nombre] || { pasos: [], orden: null })) : fila[c.nombre] ?? (c.tipo === 'bool' ? false : '')
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
      avisar(tr('{0} updated.', [cap(cat.value.singular)]))
    } else {
      await api.post(`/catalogos/${tipo.value}`, cuerpo)
      avisar(tr('{0} created.', [cap(cat.value.singular)]))
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
    avisar(tr('{0} deleted.', [cap(cat.value.singular)]))
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
  if (c.tipo === 'opciones') return v.map((k) => tx(c.opciones.find((o) => o[0] === k)?.[1] || k)).join(', ') || '—'
  if (c.tipo === 'codigo') return opciones[c.catalogo]?.find((o) => o.codigo === v)?.texto || v
  return v
}

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
const nuevoPP = reactive({ tipo: 'CURVA', sku: '', codigo: '', estilo: '', generico: '', descripcion: '', cantidades: {} })
// La variante de un artículo de la lista: talla, color y sus atributos propios (atr.*)
const varTxt = (a) => [a.color, a.talla, ...Object.entries(a).filter(([k, v]) => k.startsWith('atr.') && v).map(([, v]) => v)].filter(Boolean).join(' · ')
// Kit: artículos de cualquier estilo con su cantidad
const kitItems = ref([])
const kitElegido = ref('')
const opcionesKit = computed(() => solidos.value.filter((a) => !kitItems.value.some((k) => k.articulo_id === a.id))
  .map((a) => ({ valor: a.id, texto: [a.sku, a.estilo, varTxt(a)].filter(Boolean).join(' · ') })))
watch(kitElegido, (id) => {
  const a = solidos.value.find((x) => x.id === id)
  if (a) kitItems.value.push({ articulo_id: a.id, sku: a.sku, texto: [a.estilo, varTxt(a)].filter(Boolean).join(' · ') || a.sku, cantidad: 1 })
  kitElegido.value = ''
})
const erroresPP = ref({})
async function cargarSolidos() {
  try {
    solidos.value = (await api.get('/catalogos/articulos', { tipo: 'SOLIDO', activo: 'true', size: 200, orden: 'sku:asc' })).items
  } catch (e) {
    errorApi(e)
  }
}
// Un pack lleva variantes de un mismo producto: se elige el producto y se reparten sus variantes
const productosPP = computed(() => {
  const vistos = new Map()
  for (const a of solidos.value) {
    if (a.generico && !vistos.has(a.generico)) vistos.set(a.generico, { valor: a.generico, texto: a.generico, sub: [a.estilo, a.descripcion].filter(Boolean).join(' · ') })
  }
  return [...vistos.values()].sort((x, y) => x.texto.localeCompare(y.texto))
})
const tallasPP = computed(() => solidos.value.filter((a) => a.generico && a.generico === nuevoPP.generico))
const totalPP = computed(() => nuevoPP.tipo === 'KIT'
  ? kitItems.value.reduce((t, k) => t + (Number(k.cantidad) || 0), 0)
  : tallasPP.value.reduce((t, a) => t + (Number(nuevoPP.cantidades[a.id]) || 0), 0))
watch(() => nuevoPP.generico, async () => {
  nuevoPP.cantidades = {}
  // El pack es del producto de sus variantes; se propone el código del producto + un código libre
  const gen = nuevoPP.generico
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
    const componentes = nuevoPP.tipo === 'KIT'
      ? kitItems.value.filter((k) => Number(k.cantidad) > 0).map((k) => ({ articulo_id: k.articulo_id, cantidad: Number(k.cantidad) }))
      : tallasPP.value.filter((a) => Number(nuevoPP.cantidades[a.id]) > 0)
        .map((a) => ({ articulo_id: a.id, cantidad: Number(nuevoPP.cantidades[a.id]) }))
    const r = await api.post('/catalogos/prepacks', { ...nuevoPP, generico: undefined, cantidades: undefined, componentes })
    avisar(t('Pack {0} created with item code {1} ({2} per unit).', [r.codigo, r.sku, r.total]))
    Object.assign(nuevoPP, { sku: '', codigo: '', descripcion: '', cantidades: {} })
    kitItems.value = []
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
        <BotonesExportar v-if="cat" :ruta="`/catalogos/${tipo}/exportar`" :params="paramsExportar" />
        <router-link v-if="tipo === 'leadtimes' || tipo === 'pasos_lt'" class="btn" to="/leadtimes"><Icono nombre="reloj" :tam="15" />{{ t('Effective lead time') }}</router-link>
        <a v-if="tipo === 'prepacks'" class="btn" href="/plantilla_prepacks.csv" download><Icono nombre="descargar" />{{ t('Template') }}</a>
        <button v-if="cat && acciones.crear" class="btn" @click="abrirCarga"><Icono nombre="importar" />{{ tx(tipo === 'articulos' ? t('Upload items and sheets') : tipo === 'prepacks' ? t('Upload size runs') : t('Upload Excel')) }}</button>
      </MasOpciones>
      <!-- Los artículos se crean con su producto: «Nuevo producto» en la barra del módulo -->
      <button v-if="cat && tipo !== 'articulos' && acciones.crear" class="btn btn-primario" @click="abrirNuevo"><Icono nombre="mas" />{{ tr('New {0}', [cat.singular]) }}</button>
    </div>
  </div>

  <!-- En el celular, un selector en lugar de las 16 pestañas -->
  <label class="selector-catalogo solo-movil">
    <span>{{ t('Catalog') }}</span>
    <Seleccion class="entrada" :value="tipo" @change="elegir">
      <option v-for="c in delModulo" :key="c.tipo" :value="c.tipo">{{ tx(c.titulo) }} ({{ tx(c.total) }})</option>
    </Seleccion>
  </label>
  <!-- Los catálogos de uso diario como pestañas; el resto en una lista con búsqueda -->
  <div class="selector-catalogos solo-escritorio">
    <div class="pestanas-pildora" role="tablist">
      <button v-for="c in principales" :key="c.tipo" class="pildora" role="tab" :aria-selected="c.tipo === tipo" @click="elegir(c.tipo)">
        {{ tx(c.titulo) }}<span class="cuenta">{{ tx(c.total) }}</span>
      </button>
    </div>
    <SelectBusqueda v-if="otros.length" :model-value="otros.some((c) => c.tipo === tipo) ? tipo : ''" :opciones="otros.map((c) => ({ valor: c.tipo, texto: c.titulo, sub: String(c.total) }))"
                    :vacio="t('More catalogs')" :etiqueta="t('Catalog')" :prefijo="false" :busqueda="true" class="selector-otros"
                    :class="{ activo: otros.some((c) => c.tipo === tipo) }" @update:model-value="(v) => v && elegir(v)" />
  </div>

  <div v-if="cat">
    <div v-if="cat.gobierno?.gobernable && (cat.gobierno.responsables.length || cat.gobierno.obligatorios.length || acciones.gobernar)" class="gobierno" role="note">
      <Icono nombre="candado" :tam="15" />
      <span v-if="cat.gobierno.responsables.length">{{ t('Maintained by: {0}', [cat.gobierno.responsables.map((r) => tx(r.nombre)).join(', ')]) }}</span>
      <span v-else>{{ t('Maintained by every role with master data permissions.') }}</span>
      <span v-if="cat.gobierno.obligatorios.length">{{ t('Your company also requires: {0}', [cat.gobierno.obligatorios.map((n) => tx(etiquetaCampo(n))).join(', ')]) }}</span>
      <button v-if="acciones.gobernar" type="button" class="btn btn-chico btn-fantasma" @click="abrirGobierno"><Icono nombre="engrane" :tam="14" />{{ t('Governance') }}</button>
    </div>

    <section>
      <ArticulosGenericos v-if="compacta" :key="`gen-${montaje}`" :acciones="acciones" :q="filtros.q" :iniciales="iniciales" :recarga="recarga" :nombre="nombreRef"
                          @consulta="(c) => (ultima = c)" @editar-articulo="editar" @eliminar-articulo="(fila) => (modal = { tipo: 'eliminar', fila })"
                          @desglose="(a) => (explosion = { sku: a.sku })" @cambio="cargarMeta">
        <template #barra>
          <label class="buscador">
            <Icono nombre="buscar" :tam="16" />
            <input v-model="filtros.q" type="search" :placeholder="t('Search generic, style, color, item code, UPC or supplier SKU')" :aria-label="t('Search')" @input="buscar" />
          </label>
        </template>
        <template #filtros>
          <div class="segmentos" role="group" :aria-label="t('Items view')">
            <button type="button" class="segmento" aria-pressed="true" :title="t('One row per generic; expand it to see its sizes')">{{ t('Compact') }}</button>
            <button type="button" class="segmento" aria-pressed="false" :title="t('One row per item code')" @click="cambiarVista('lista')">{{ t('List') }}</button>
          </div>
        </template>
      </ArticulosGenericos>
      <TablaDatos v-else ref="tabla" :key="`${tipo}-${montaje}`" :tabla="`catalogo_${tipo}`" modo="servidor" :columnas="columnasTabla" :filas="datos.items"
                  :total="datos.total" :cargando="cargando" :valores="valoresColumna" :filtros-iniciales="iniciales" :fila-activa="editando"
                  :externos="{ q: filtros.q }" :mas-filtros-activos="fueraActivos" :etiqueta="cat.titulo"
                  @consulta="consultar" @vista="(x) => { filtros.q = x.q || ''; recargar() }" @limpiar-externos="filtros.q = ''; recargar()">
        <template #barra>
          <label class="buscador">
            <Icono nombre="buscar" :tam="16" />
            <input v-model="filtros.q" type="search" :placeholder="t('Search {0}', [tx(cat.titulo).toLowerCase()])" :aria-label="t('Search')" @input="buscar" />
          </label>
        </template>
        <template v-if="tipo === 'articulos'" #filtros>
          <div class="segmentos" role="group" :aria-label="t('Items view')">
            <button type="button" class="segmento" aria-pressed="false" :title="t('One row per generic; expand it to see its sizes')" @click="cambiarVista('compacta')">{{ t('Compact') }}</button>
            <button type="button" class="segmento" aria-pressed="true" :title="t('One row per item code')">{{ t('List') }}</button>
          </div>
        </template>
        <template v-if="conFiltro.length" #mas-filtros>
          <template v-for="c in conFiltro" :key="c.nombre">
            <SelectBusqueda v-if="['ref', 'codigo', 'multi'].includes(c.tipo)" :model-value="filtroFuera(c)" :opciones="opcionesDe(c)"
                            :vacio="t('{0}: all', [tx(c.etiqueta)])" :etiqueta="tx(c.etiqueta)" @update:model-value="(v) => ponerFiltroFuera(c, v)" />
            <Seleccion v-else :model-value="filtroFuera(c)" :aria-label="tx(c.etiqueta)" @update:model-value="(v) => ponerFiltroFuera(c, v)">
              <option value="">{{ t('{0}: all', [tx(c.etiqueta)]) }}</option>
              <template v-if="c.tipo === 'bool'"><option value="true">{{ t('{0}: yes', [c.etiqueta]) }}</option><option value="false">{{ t('{0}: no', [c.etiqueta]) }}</option></template>
              <template v-else-if="c.tipo === 'opcion'"><option v-for="[v, txt] in c.opciones" :key="v" :value="v">{{ tx(c.etiqueta) }}: {{ tx(txt) }}</option></template>
            </Seleccion>
          </template>
        </template>
        <template v-for="c in campos" :key="c.nombre" #[`celda-${c.nombre}`]="{ fila }">
          <button v-if="c.tipo === 'bool'" type="button" class="etiqueta" :disabled="!acciones.editar" :class="fila[c.nombre] ? 'ok' : ''" style="border: 0; cursor: pointer" :title="t('Change {0}', [c.etiqueta.toLowerCase()])" @click.stop="alternarActivo(fila, c.nombre)">
            {{ tx(fila[c.nombre] ? t('Yes') : t('No')) }}
          </button>
          <span v-else :class="{ codigo: ['codigo', 'sku'].includes(c.nombre), fuerte: c.nombre === 'codigo' || c.nombre === 'sku' }">{{ tx(valorCelda(c, fila)) }}</span>
        </template>
        <template v-for="ex in extras" :key="ex.nombre" #[`celda-${ex.nombre}`]="{ fila }">
          <button type="button" class="enlace" :title="t('See {0} of {1}', [ex.etiqueta.toLowerCase(), fila.codigo || fila.nombre])"
                  @click="elegir(ex.catalogo, { [ex.filtro]: fila.id })">
            {{ tx(ex.nombre === 'centros_txt' ? (fila.centros_txt || t('Assign plants')) : `${fila[ex.nombre] || 0} ${fila[ex.nombre] === 1 ? ex.etiqueta.toLowerCase().replace(/s$/, '') : ex.etiqueta.toLowerCase()}`) }}
          </button>
        </template>
        <template #celda-ficha="{ fila }">
          <router-link v-if="fila.producto_id" :to="`/productos/${fila.producto_id}`" class="enlace" :title="t('Technical sheet of {0} {1}', [fila.estilo, fila.color])">
            <span v-if="fila.partida_txt" class="codigo-sac">{{ tx(fila.partida_txt) }}</span>
            <template v-else>{{ tx(ESTADO_FICHA[fila.clasificacion] || t('Open sheet')) }}</template>
          </router-link>
          <span v-else class="apagado">—</span>
          <span v-if="fila.descripcion" class="sub desc-corta" :title="tx(fila.descripcion)">{{ tx(fila.descripcion) }}</span>
        </template>
        <template v-if="tipo === 'prepacks'" #celda-sku="{ fila }"><span class="codigo fuerte">{{ tx(fila.sku || '—') }}</span></template>
        <template v-if="tipo === 'prepacks'" #celda-total="{ fila }">{{ tx(fila.total) }} <span class="sub">{{ t('{0} sizes', [fila.componentes]) }}</span></template>
        <template #acciones="{ fila }">
          <span class="nowrap">
            <button v-if="tipo === 'prepacks' || fila.tipo === 'PREPACK'" type="button" class="btn btn-chico" :title="t('See the breakdown (it never changes)')"
                    @click="explosion = { sku: fila.sku }"><Icono nombre="lupa" :tam="13" />{{ t('Breakdown') }}</button>
            <button type="button" class="btn-icono" :aria-label="tr('See {0}', [cat.singular])" :title="t('See details and history')" @click="ver(fila)"><Icono nombre="ojo" :tam="16" /></button>
            <button v-if="acciones.editar" type="button" class="btn-icono" :aria-label="tr('Edit {0}', [cat.singular])" :title="t('Edit')" @click="editar(fila)"><Icono nombre="editar" :tam="16" /></button>
            <button v-if="acciones.eliminar" type="button" class="btn-icono texto-error" :aria-label="tr('Delete {0}', [cat.singular])" :title="t('Delete')" @click="modal = { tipo: 'eliminar', fila }"><Icono nombre="basura" :tam="16" /></button>
          </span>
        </template>
        <template #vacio>{{ t('No records match these filters.') }}</template>
      </TablaDatos>
    </section>
  </div>

  <Modal v-if="formAbierto && cat" :titulo="editando ? tr('Edit {0}', [cat.singular]) : tr('New {0}', [cat.singular])" ancho="640px" @cerrar="cerrarForm">
    <p v-if="cat.ayuda" class="ayuda mt-0">{{ tx(cat.ayuda) }}</p>
      <form v-if="tipo === 'prepacks' && !editando" class="form-catalogo" @submit.prevent="crearPrepack">
        <div class="campo"><span class="req">{{ t('Kind') }}</span>
          <div class="pestanas-pildora" role="radiogroup" :aria-label="t('Kind')">
            <button type="button" class="pildora" role="radio" :aria-checked="nuevoPP.tipo === 'CURVA'" @click="nuevoPP.tipo = 'CURVA'">{{ t('Pack of variants') }}</button>
            <button type="button" class="pildora" role="radio" :aria-checked="nuevoPP.tipo === 'KIT'" @click="nuevoPP.tipo = 'KIT'">{{ t('Kit') }}</button>
          </div>
          <small class="ayuda">{{ nuevoPP.tipo === 'KIT' ? t('A kit puts together items of any products (a set, a gift box).') : t('Variants of one product (sizes, flavors, presentations…) per unit.') }}</small>
        </div>
        <label class="campo"><span class="req">{{ t('Item code') }}</span>
          <input v-model="nuevoPP.sku" maxlength="40" :placeholder="t('Your item code for the pack')" required />
          <small v-if="erroresPP.sku" class="nota error relleno-chico">{{ tx(erroresPP.sku) }}</small>
          <small v-else class="ayuda">{{ t('Any code in your format. A pack belongs to the product of its variants; a code is proposed when you choose the product.') }}</small>
        </label>
        <label v-if="nuevoPP.tipo === 'KIT'" class="campo"><span>{{ t('Kit style / model') }}</span>
          <input class="mayus" v-model="nuevoPP.estilo" maxlength="40" :placeholder="t('Optional')" />
        </label>
        <label v-else class="campo"><span class="req">{{ t('Product') }}</span>
          <SelectBusqueda v-model="nuevoPP.generico" :opciones="productosPP" requerido :etiqueta="t('Product')" />
        </label>
        <label class="campo"><span class="req">{{ t('Pack ID') }}</span>
          <input class="mayus" v-model="nuevoPP.codigo" maxlength="10" placeholder="AB12" required />
          <small v-if="erroresPP.codigo" class="nota error relleno-chico">{{ tx(erroresPP.codigo) }}</small>
          <small v-else class="ayuda">{{ t('Usually 2 letters and 2 digits. It tells the packs of a product apart.') }}</small>
        </label>
        <label class="campo"><span>{{ t('Description') }}</span><input v-model="nuevoPP.descripcion" /></label>
        <div v-if="nuevoPP.tipo === 'KIT'" class="campo">
          <span class="req">{{ t('Kit contents') }}</span>
          <SelectBusqueda v-model="kitElegido" :opciones="opcionesKit" :etiqueta="t('Add item')" :placeholder="t('Add item')" />
          <div v-if="kitItems.length" class="tabla-marco tabla-captura">
            <table class="tabla" v-tarjetas>
              <thead><tr><th>SKU</th><th>{{ t('Item') }}</th><th class="num">{{ t('Qty') }}</th><th /></tr></thead>
              <tbody>
                <tr v-for="(k, i) in kitItems" :key="k.articulo_id">
                  <td class="codigo">{{ tx(k.sku) }}</td>
                  <td>{{ tx(k.texto) }}</td>
                  <td class="num"><input v-model.number="k.cantidad" class="celda num ancho-xs con-borde" type="number" min="1" :aria-label="t('Quantity')" /></td>
                  <td><button type="button" class="btn-icono" :aria-label="t('Remove')" @click="kitItems.splice(i, 1)"><Icono nombre="basura" :tam="16" /></button></td>
                </tr>
              </tbody>
              <tfoot><tr><td colspan="2">{{ t('Total pieces') }}</td><td class="num">{{ tx(totalPP) }}</td><td /></tr></tfoot>
            </table>
          </div>
          <small v-if="erroresPP.componentes" class="nota error relleno-chico">{{ tx(erroresPP.componentes) }}</small>
        </div>
        <div v-else-if="nuevoPP.generico" class="campo">
          <span class="req">{{ t('Contents per unit') }}<template v-if="tallasPP.length"> ({{ tx(tallasPP[0].unidad) }})</template></span>
          <div class="tabla-marco tabla-captura">
            <table class="tabla" v-tarjetas>
              <thead><tr><th>{{ t('Variant') }}</th><th>SKU</th><th class="num">{{ t('Qty') }}</th></tr></thead>
              <tbody>
                <tr v-for="a in tallasPP" :key="a.id">
                  <td><b>{{ tx(varTxt(a) || a.sku) }}</b></td>
                  <td class="codigo">{{ tx(a.sku) }}</td>
                  <td class="num"><input v-model.number="nuevoPP.cantidades[a.id]" class="celda num ancho-xs con-borde" type="number" min="0" :aria-label="t('Quantity of {0}', [varTxt(a) || a.sku])" /></td>
                </tr>
              </tbody>
              <tfoot><tr><td colspan="2">{{ t('Total per unit') }}</td><td class="num">{{ tx(totalPP) }}</td></tr></tfoot>
            </table>
          </div>
          <small v-if="erroresPP.componentes" class="nota error relleno-chico">{{ tx(erroresPP.componentes) }}</small>
          <small v-else class="ayuda">{{ t('Only variants of product {0}. Leave at 0 the ones it does not carry. Once created it never changes.', [nuevoPP.generico]) }}</small>
        </div>
        <p class="leyenda-req">{{ t('Required') }}</p>
        <button class="btn btn-primario" type="submit" :disabled="ocupado || !totalPP"><Icono nombre="mas" :tam="16" />{{ nuevoPP.tipo === 'KIT' ? t('Create kit') : t('Create prepack') }}</button>
      </form>
      <form v-else class="form-catalogo" @submit.prevent="guardar">
        <template v-for="sec in seccionesForm" :key="sec.clave">
        <h3 v-if="seccionesForm.length > 1" class="seccion-form">{{ tx(sec.titulo) }}</h3>
        <component :is="c.tipo === 'regla_lt' ? 'div' : 'label'" v-for="c in sec.campos" :key="c.nombre" :class="c.tipo === 'bool' ? 'check' : 'campo'">
          <template v-if="c.tipo === 'bool'">
            <input v-model="form[c.nombre]" type="checkbox" /> {{ tx(c.etiqueta) }}
          </template>
          <template v-else>
            <span :class="{ req: c.obligatorio }" :title="tx(c.obligatorio_empresa ? t('Required by your company') : '')">{{ tx(c.etiqueta) }}</span>
            <Seleccion v-if="c.tipo === 'opcion'" v-model="form[c.nombre]" :required="c.obligatorio" :disabled="bloqueado(c)">
              <option value="">{{ t('Choose…') }}</option>
              <option v-for="[v, txt] in opcionesCampo(c)" :key="v" :value="v">{{ tx(txt) }}</option>
            </Seleccion>
            <SelectBusqueda v-else-if="c.tipo === 'ref' || c.tipo === 'codigo'" v-model="form[c.nombre]" :opciones="opcionesDe(c, form)"
                            :vacio="tx(c.obligatorio ? '' : t('None'))" :requerido="c.obligatorio" :etiqueta="tx(c.etiqueta)" :prefijo="false" :deshabilitado="bloqueado(c)" />
            <SelectBusqueda v-else-if="c.tipo === 'multi'" v-model="form[c.nombre]" :opciones="opcionesDe(c, form)" multiple
                            :placeholder="t('Choose one or more…')" :requerido="c.obligatorio" :etiqueta="tx(c.etiqueta)" />
            <SelectBusqueda v-else-if="c.tipo === 'opciones'" v-model="form[c.nombre]" :opciones="c.opciones.map(([valor, texto]) => ({ valor, texto: tx(texto) }))" multiple
                            :placeholder="t('Choose one or more…')" :requerido="c.obligatorio" :etiqueta="tx(c.etiqueta)" />
            <EditorReglaLT v-else-if="c.tipo === 'regla_lt'" v-model="form[c.nombre]" :form="form" :regla-id="editando" />
            <textarea v-else-if="c.tipo === 'correos'" v-model="form[c.nombre]" rows="2" :required="c.obligatorio"
                      :placeholder="t('name@company.com, other@company.com')"></textarea>
            <input v-else v-model="form[c.nombre]" :type="c.tipo === 'entero' || c.tipo === 'numero' ? 'number' : c.tipo === 'fecha' ? 'date' : 'text'"
                   :min="c.minimo" :maxlength="c.max" :required="c.obligatorio" :disabled="bloqueado(c)" :title="tx(bloqueado(c) ? t('Cannot change: it is part of the prepack') : '')" />
            <small v-if="erroresForm[c.nombre]" class="nota error relleno-chico">{{ tx(erroresForm[c.nombre]) }}</small>
            <small v-else-if="c.ayuda" class="ayuda">{{ tx(c.ayuda) }}</small>
          </template>
        </component>
        </template>
        <p class="leyenda-req">{{ t('Required') }}</p>
        <div class="fila-flex">
          <button class="btn btn-primario" type="submit" :disabled="ocupado"><Icono :nombre="editando ? 'check' : 'mas'" :tam="16" />{{ editando ? t('Save changes') : tr('Create {0}', [cat.singular]) }}</button>
          <button class="btn btn-fantasma" type="button" @click="cerrarForm">{{ t('Cancel') }}</button>
        </div>
      </form>
  </Modal>

  <Modal v-if="viendo && cat" :titulo="tx(viendo.fila.codigo || viendo.fila.sku || viendo.fila.nombre || cap(cat.singular))" ancho="680px" @cerrar="viendo = null">
    <section v-for="sec in camposVista" :key="sec.clave" class="vista-seccion">
      <h3 v-if="camposVista.length > 1">{{ tx(sec.titulo) }}</h3>
      <dl class="datos">
        <template v-for="c in sec.campos" :key="c.nombre">
          <dt>{{ tx(c.etiqueta) }}</dt>
          <dd>{{ c.tipo === 'bool' ? tx(viendo.fila[c.nombre] ? t('Yes') : t('No')) : tx(valorCelda(c, viendo.fila)) }}</dd>
        </template>
      </dl>
    </section>
    <section class="vista-seccion">
      <h3>{{ t('History') }}</h3>
      <p v-if="!viendo.historial" class="ayuda">{{ t('Loading…') }}</p>
      <ul v-else class="linea-tiempo">
        <li v-for="h in viendo.historial" :key="h.id">
          <span class="ayuda">{{ fmtFechaHora(h.fecha) }}<br />{{ tx(h.usuario || t('System')) }}</span>
          <div><b>{{ tx(ACCIONES[h.accion] || h.accion) }}</b><div v-if="cambiosTxt(h)" class="ayuda">{{ tx(cambiosTxt(h)) }}</div></div>
        </li>
        <li v-if="!viendo.historial.length"><span></span><span class="ayuda">{{ t('No changes recorded.') }}</span></li>
      </ul>
    </section>
    <section v-if="tipo === 'articulos'" class="vista-seccion">
      <h3>{{ t('Versions used by documents') }}</h3>
      <p class="ayuda">{{ t('Each PO and invoice line keeps the version of the item it used: changing the item does not change old documents.') }}</p>
      <p v-if="!viendo.versiones" class="ayuda">{{ t('Loading…') }}</p>
      <ul v-else class="linea-tiempo">
        <li v-for="v in viendo.versiones" :key="v.id">
          <span class="ayuda">{{ fmtFechaHora(v.creada_en) }}</span>
          <div>
            <b>{{ t('Version {0}', [v.numero]) }}</b>
            <span class="ayuda"> · {{ t('{0} PO lines · {1} invoice lines', [v.lineas_oc, v.lineas_factura]) }}</span>
            <div v-if="v.migracion" class="ayuda">{{ t('Data of the item when versions started (older documents).') }}</div>
            <div v-else-if="v.cambios.length" class="ayuda">{{ cambiosVersion(v) }}</div>
          </div>
        </li>
        <li v-if="!viendo.versiones.length"><span></span><span class="ayuda">{{ t('No document uses this item yet.') }}</span></li>
      </ul>
    </section>
    <template #pie>
      <button type="button" class="btn" @click="viendo = null">{{ t('Close') }}</button>
      <button v-if="acciones.editar" type="button" class="btn btn-primario" @click="editarDesdeVista"><Icono nombre="editar" :tam="15" />{{ t('Edit') }}</button>
    </template>
  </Modal>

  <Modal v-if="gob && cat" :titulo="t('Governance of {0}', [tx(cat.titulo)])" ancho="620px" @cerrar="gob = null">
    <p class="ayuda">{{ t('Who maintains this catalog and which of its data your company requires besides the ones the system always asks for. Without owners, every role with master data permissions maintains it. Every change is recorded in the activity log.') }}</p>
    <div class="campo"><span>{{ t('Owners (roles)') }}</span>
      <SelectBusqueda v-model="gob.responsables" :opciones="roles" multiple :placeholder="t('Every role with permissions')" :etiqueta="t('Owners (roles)')" :prefijo="false" /></div>
    <div class="campo mt-chico"><span>{{ t('Also required') }}</span>
      <div class="lista-checks">
        <label v-for="o in cat.gobierno.obligables" :key="o.nombre" class="check"><input v-model="gob.obligatorios" type="checkbox" :value="o.nombre" />{{ tx(o.etiqueta) }}</label>
      </div>
    </div>
    <template #pie>
      <button type="button" class="btn" @click="gob = null">{{ t('Cancel') }}</button>
      <button type="button" class="btn btn-primario" :disabled="ocupado" @click="guardarGobierno"><Icono nombre="check" :tam="15" />{{ t('Save') }}</button>
    </template>
  </Modal>

  <Modal v-if="modal?.tipo === 'eliminar'" :titulo="tr('Delete {0}', [cat.singular])" @cerrar="modal = null">
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
      <div v-if="modal.resultado.errores.length" class="tabla-marco tabla-captura alto-limitado">
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

  <ExplosionPrepack v-if="explosion" :sku="explosion.sku" @cerrar="explosion = null" />
</template>

<style scoped>
.desc-corta { max-width: 280px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.gobierno { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 12px; margin: 0 0 12px; padding: 8px 12px; border: 1px solid var(--linea);
  border-radius: var(--radio); background: var(--superficie-2); color: var(--tinta-2); font-size: var(--t-sm); }
.gobierno .btn { margin-inline-start: auto; }
.seccion-form { grid-column: 1 / -1; margin: 6px 0 -4px; font-size: var(--t-xs); font-weight: 700; letter-spacing: 0.04em; text-transform: uppercase; color: var(--tinta-3); }
.seccion-form:first-child { margin-top: 0; }
.vista-seccion + .vista-seccion { margin-top: 16px; }
.vista-seccion h3 { margin: 0 0 8px; font-size: var(--t-xs); font-weight: 700; letter-spacing: 0.04em; text-transform: uppercase; color: var(--tinta-3); }
.datos { display: grid; grid-template-columns: minmax(140px, auto) 1fr; gap: 6px 16px; margin: 0; font-size: var(--t-base); }
.datos dt { color: var(--tinta-2); }
.datos dd { margin: 0; min-width: 0; overflow-wrap: anywhere; }
.lista-checks { display: flex; flex-wrap: wrap; gap: 8px 20px; }
</style>
