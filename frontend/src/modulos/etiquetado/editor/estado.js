import { computed, inject, provide, reactive, watch } from 'vue'
import { api as servidor } from '@/nucleo/api'
import { t } from '@/i18n/index.js'
import { elementoNuevo, nuevoId } from '@/modulos/etiquetado/etiquetas.js'

// Estado del editor de etiquetas, compartido por el lienzo y los paneles
// (provide/inject). El diseño es el JSON que se guarda en la versión: todo en
// mm, el último elemento de la lista queda encima. Deshacer y rehacer guardan
// fotos del diseño (hasta 100); los cambios seguidos en menos de 400 ms (un
// arrastre, escribir en un campo) cuentan como uno solo.
const CLAVE = Symbol('editor-etiqueta')
const MAX_HISTORIA = 100

const clonar = (x) => JSON.parse(JSON.stringify(x))
const redondear = (v) => Math.round(v * 1000) / 1000

export function crearEditor() {
  const ed = reactive({
    diseno: null,
    sujeto: 'ARTICULO', // qué etiqueta el tipo del diseño (artículo, bulto, documento)
    tipo_etiqueta_id: null,
    editable: false,
    disenador: false, // puede pedir dibujos al servidor con un diseño sin guardar
    seleccion: [],
    zoom: 1,
    guias: [], // líneas de alineación mientras se arrastra: [{ eje: 'x'|'y', v }]
    previa: null, // respuesta de la vista previa del servidor (svg, problemas, valores)
    ejemplos: {}, // valores de ejemplo por campo (para dibujar en el lienzo)
    tipos: {}, // tipo de cada campo
    campos: [], // catálogo de campos del sujeto
    colecciones: [], // listas para las tablas (contenido del bulto, componentes…)
    portapapeles: null,
    // Datos de la vista previa: de ejemplo o reales (artículo, OC, línea y bulto)
    fuenteDatos: { real: false, articulo_id: '', oc_id: '', posicion_id: '', bulto: '' },
    historia: [],
    futuro: [],
    sucio: false,
  })
  let ultimaFoto = null
  let aplicando = false
  let espera = null

  function cargar(diseno) {
    aplicando = true
    ed.diseno = clonar(diseno)
    ed.seleccion = []
    ed.historia = []
    ed.futuro = []
    ultimaFoto = JSON.stringify(ed.diseno)
    ed.sucio = false
    queueMicrotask(() => (aplicando = false))
  }
  // Una foto por cambio: el watch profundo junta los cambios seguidos
  watch(() => ed.diseno, () => {
    if (aplicando || !ed.diseno) return
    ed.sucio = true
    clearTimeout(espera)
    espera = setTimeout(fotografiar, 400)
  }, { deep: true })
  function fotografiar() {
    clearTimeout(espera)
    const actual = JSON.stringify(ed.diseno)
    if (actual === ultimaFoto) return
    ed.historia.push(ultimaFoto)
    if (ed.historia.length > MAX_HISTORIA) ed.historia.shift()
    ed.futuro = []
    ultimaFoto = actual
  }
  function aplicar(foto) {
    aplicando = true
    ed.diseno = JSON.parse(foto)
    ultimaFoto = foto
    const ids = new Set(ed.diseno.elementos.map((e) => e.id))
    ed.seleccion = ed.seleccion.filter((id) => ids.has(id))
    ed.sucio = true
    queueMicrotask(() => (aplicando = false))
  }
  function deshacer() {
    fotografiar()
    if (!ed.historia.length) return
    ed.futuro.push(ultimaFoto)
    aplicar(ed.historia.pop())
  }
  function rehacer() {
    if (!ed.futuro.length) return
    ed.historia.push(ultimaFoto)
    aplicar(ed.futuro.pop())
  }
  function guardado(diseno) {
    // El servidor devuelve el diseño limpio (con valores por defecto): es la nueva base
    aplicando = true
    ed.diseno = clonar(diseno)
    ultimaFoto = JSON.stringify(ed.diseno)
    ed.sucio = false
    queueMicrotask(() => (aplicando = false))
  }

  // ---- Selección ------------------------------------------------------------------------
  const elementos = computed(() => ed.diseno?.elementos || [])
  const porId = (id) => elementos.value.find((e) => e.id === id)
  const seleccionados = computed(() => ed.seleccion.map(porId).filter(Boolean))
  const unico = computed(() => (seleccionados.value.length === 1 ? seleccionados.value[0] : null))
  // Con un elemento de un grupo se elige el grupo completo
  function conGrupo(ids) {
    const grupos = new Set(ids.map(porId).filter((e) => e?.grupo).map((e) => e.grupo))
    if (!grupos.size) return ids
    return [...new Set([...ids, ...elementos.value.filter((e) => grupos.has(e.grupo)).map((e) => e.id)])]
  }
  function seleccionar(id, sumar = false) {
    if (id == null) {
      ed.seleccion = []
      return
    }
    const ids = conGrupo([id])
    if (!sumar) ed.seleccion = ids
    else if (ed.seleccion.includes(id)) ed.seleccion = ed.seleccion.filter((x) => !ids.includes(x))
    else ed.seleccion = [...ed.seleccion, ...ids.filter((x) => !ed.seleccion.includes(x))]
  }
  const seleccionarTodo = () => (ed.seleccion = elementos.value.filter((e) => e.visible !== false && !e.bloqueado).map((e) => e.id))
  const movibles = () => seleccionados.value.filter((e) => !e.bloqueado)

  // ---- Cuadrícula -----------------------------------------------------------------------
  function ajustar(v) {
    const c = ed.diseno?.cuadricula
    if (!c?.ajustar) return redondear(v)
    return redondear(Math.round(v / c.paso) * c.paso)
  }

  // ---- Altas y bajas --------------------------------------------------------------------
  function agregar(tipo, extra = {}, pos = null) {
    if (!ed.editable) return null
    const d = ed.diseno
    const e = elementoNuevo(tipo, 0, 0, extra)
    e.w = Math.min(e.w, Math.max(d.ancho - 2 * d.margen, 5))
    if (tipo !== 'linea') e.h = Math.min(e.h, Math.max(d.alto - 2 * d.margen, 3))
    const x = pos ? pos.x - e.w / 2 : (d.ancho - e.w) / 2
    const y = pos ? pos.y - e.h / 2 : (d.alto - e.h) / 2
    e.x = ajustar(Math.min(Math.max(x, 0), Math.max(d.ancho - e.w, 0)))
    e.y = ajustar(Math.min(Math.max(y, 0), Math.max(d.alto - e.h, 0)))
    d.elementos.push(e)
    ed.seleccion = [e.id]
    return e
  }
  function eliminar() {
    if (!ed.editable) return
    const fuera = new Set(movibles().map((e) => e.id))
    ed.diseno.elementos = elementos.value.filter((e) => !fuera.has(e.id))
    ed.seleccion = ed.seleccion.filter((id) => !fuera.has(id))
  }
  function copiasDe(lista, desplazar) {
    const grupos = {}
    return lista.map((e) => {
      const c = clonar(e)
      c.id = nuevoId(e.tipo)
      if (e.grupo) c.grupo = grupos[e.grupo] || (grupos[e.grupo] = nuevoId('g'))
      c.x = redondear(c.x + desplazar)
      c.y = redondear(c.y + desplazar)
      c.bloqueado = false
      return c
    })
  }
  function duplicar() {
    if (!ed.editable || !seleccionados.value.length) return
    const paso = ed.diseno.cuadricula?.paso >= 1 ? ed.diseno.cuadricula.paso : 2
    const copias = copiasDe(seleccionados.value, paso)
    ed.diseno.elementos.push(...copias)
    ed.seleccion = copias.map((e) => e.id)
  }
  function copiar() {
    if (seleccionados.value.length) ed.portapapeles = clonar(seleccionados.value)
  }
  function pegar() {
    if (!ed.editable || !ed.portapapeles?.length) return
    const copias = copiasDe(ed.portapapeles, 2)
    ed.portapapeles = clonar(copias)
    ed.diseno.elementos.push(...copias)
    ed.seleccion = copias.map((e) => e.id)
  }

  // ---- Mover, alinear, distribuir ---------------------------------------------------------
  function mover(dx, dy) {
    if (!ed.editable) return
    for (const e of movibles()) {
      e.x = redondear(e.x + dx)
      e.y = redondear(e.y + dy)
    }
  }
  const caja = (lista) => {
    const xs = lista.flatMap((e) => [e.x, e.x + e.w])
    const ys = lista.flatMap((e) => [e.y, e.y + e.h])
    return { x1: Math.min(...xs), y1: Math.min(...ys), x2: Math.max(...xs), y2: Math.max(...ys) }
  }
  // Con un solo elemento se alinea a la etiqueta (dentro del área segura); con varios, entre ellos
  function alinear(modo) {
    if (!ed.editable) return
    const lista = movibles()
    if (!lista.length) return
    const m = ed.diseno.margen || 0
    const ref = lista.length === 1 && seleccionados.value.length === 1
      ? { x1: m, y1: m, x2: ed.diseno.ancho - m, y2: ed.diseno.alto - m }
      : caja(seleccionados.value)
    for (const e of lista) {
      if (modo === 'izq') e.x = ref.x1
      if (modo === 'centro') e.x = (ref.x1 + ref.x2 - e.w) / 2
      if (modo === 'der') e.x = ref.x2 - e.w
      if (modo === 'arriba') e.y = ref.y1
      if (modo === 'medio') e.y = (ref.y1 + ref.y2 - e.h) / 2
      if (modo === 'abajo') e.y = ref.y2 - e.h
      e.x = redondear(e.x)
      e.y = redondear(e.y)
    }
  }
  // Mismo espacio entre elementos (necesita tres o más)
  function distribuir(eje) {
    if (!ed.editable) return
    const lista = movibles()
    if (lista.length < 3) return
    const [p, t] = eje === 'h' ? ['x', 'w'] : ['y', 'h']
    lista.sort((a, b) => a[p] - b[p])
    const inicio = lista[0][p]
    const fin = lista.at(-1)[p] + lista.at(-1)[t]
    const hueco = (fin - inicio - lista.reduce((s, e) => s + e[t], 0)) / (lista.length - 1)
    let cursor = inicio
    for (const e of lista) {
      e[p] = redondear(cursor)
      cursor += e[t] + hueco
    }
  }
  function igualar(dim) {
    if (!ed.editable || seleccionados.value.length < 2) return
    const base = seleccionados.value[0][dim]
    for (const e of movibles()) e[dim] = base
  }

  // ---- Capas ----------------------------------------------------------------------------
  function ordenar(dir) {
    if (!ed.editable || !ed.seleccion.length) return
    const lista = [...elementos.value]
    const sel = new Set(ed.seleccion)
    if (dir === 'frente') ed.diseno.elementos = [...lista.filter((e) => !sel.has(e.id)), ...lista.filter((e) => sel.has(e.id))]
    else if (dir === 'fondo') ed.diseno.elementos = [...lista.filter((e) => sel.has(e.id)), ...lista.filter((e) => !sel.has(e.id))]
    else {
      const paso = dir === 'subir' ? 1 : -1
      const indices = lista.map((e, i) => (sel.has(e.id) ? i : -1)).filter((i) => i >= 0)
      if (paso > 0) indices.reverse()
      for (const i of indices) {
        const j = i + paso
        if (j < 0 || j >= lista.length || sel.has(lista[j].id)) continue
        ;[lista[i], lista[j]] = [lista[j], lista[i]]
      }
      ed.diseno.elementos = lista
    }
  }
  function moverCapa(id, destino) {
    if (!ed.editable) return
    const lista = [...elementos.value]
    const i = lista.findIndex((e) => e.id === id)
    if (i < 0) return
    const [e] = lista.splice(i, 1)
    lista.splice(Math.max(0, Math.min(destino, lista.length)), 0, e)
    ed.diseno.elementos = lista
  }
  function agrupar() {
    if (!ed.editable || seleccionados.value.length < 2) return
    const g = nuevoId('g')
    for (const e of seleccionados.value) e.grupo = g
  }
  function desagrupar() {
    if (!ed.editable) return
    for (const e of seleccionados.value) e.grupo = null
  }
  function alternar(prop) {
    if (!ed.editable || !seleccionados.value.length) return
    const valor = prop === 'visible' ? !seleccionados.value.every((e) => e.visible !== false) : !seleccionados.value.every((e) => e.bloqueado)
    for (const e of seleccionados.value) e[prop] = valor
  }

  // Códigos de barras y QR del lienzo dibujados por el servidor (los mismos
  // que se imprimen): uno por combinación de valor, medidas y opciones
  const codigos = reactive({})
  const MAX_CODIGOS = 300
  async function codigoServidor(clave, e, valor) {
    if (clave in codigos) return
    const claves = Object.keys(codigos)
    if (claves.length > MAX_CODIGOS) for (const k of claves.slice(0, 100)) delete codigos[k]
    codigos[clave] = null
    const elemento = { ...e, id: 'codigo', x: 0, y: 0, rot: 0, valor, condicion: null, grupo: null, bloqueado: false, visible: true }
    const diseno = { ancho: e.w, alto: e.h, margen: 0, fondo: e.relleno || ed.diseno?.fondo || '#ffffff', elementos: [elemento] }
    try {
      const r = await servidor.post('/etiquetas/vista-previa', { tipo_etiqueta_id: ed.tipo_etiqueta_id, diseno })
      const ok = !(r.problemas || []).some((p) => p.nivel === 'error')
      codigos[clave] = ok ? `data:image/svg+xml;charset=utf-8,${encodeURIComponent(r.svg)}` : false
    } catch {
      codigos[clave] = false
    }
  }

  // Los campos del catálogo más los que se escriben al generar (variables del diseño: {{manual.clave}})
  const manuales = computed(() => (ed.diseno?.variables || []).map((v) => ({
    clave: `manual.${v.clave}`, etiqueta: v.etiqueta || v.clave, grupo: 'manual', tipo: 'texto',
    origen: t('Written when generating'), ejemplo: v.defecto || `[${v.etiqueta || v.clave}]`,
  })))
  const camposTodos = computed(() => [...ed.campos, ...manuales.value])
  const ejemplosTodos = computed(() => ({ ...ed.ejemplos, ...Object.fromEntries(manuales.value.map((c) => [c.clave, c.ejemplo])) }))

  const problemasDe = computed(() => {
    const r = {}
    for (const p of ed.previa?.problemas || []) {
      if (!p.elemento) continue
      if (!r[p.elemento] || p.nivel === 'error') r[p.elemento] = p.nivel
    }
    return r
  })

  const api = {
    estado: ed, elementos, seleccionados, unico, problemasDe, porId,
    cargar, guardado, fotografiar, deshacer, rehacer, seleccionar, seleccionarTodo, ajustar,
    agregar, eliminar, duplicar, copiar, pegar, mover, alinear, distribuir, igualar, ordenar, moverCapa,
    agrupar, desagrupar, alternar, caja, codigos, codigoServidor, camposTodos, ejemplosTodos,
  }
  provide(CLAVE, api)
  return api
}

export const usarEditor = () => inject(CLAVE)
