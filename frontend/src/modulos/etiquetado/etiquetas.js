import { t } from '@/i18n/index.js'

// Etiquetado: textos y medidas comunes a las pantallas del módulo.
// El diseño guarda todo en milímetros y los tamaños de letra en puntos; la
// unidad elegida (mm, cm, pulgadas) solo cambia cómo se muestran.

export const MODALIDADES = () => [
  ['ARTICULO', t('Item'), t('Item and product data: the same design works for any PO.')],
  ['OC', t('Purchase order'), t('PO data: identifies the order or its packages.')],
  ['OC_ARTICULO', t('PO and item'), t('The PO data shared by every label plus the data of each line and item.')],
]
export const textoModalidad = (m) => MODALIDADES().find((x) => x[0] === m)?.[1] || m

export const UNIDADES = () => ({
  ORDEN: t('One per order'),
  LINEA: t('One per PO line'),
  ARTICULO: t('One per distinct item'),
  UNIDAD: t('One per unit ordered'),
  BULTO: t('One per package'),
  MANUAL: t('Quantity entered by hand'),
})
export const UNIDADES_DE = { ARTICULO: ['UNIDAD', 'MANUAL'], OC: ['ORDEN', 'BULTO', 'MANUAL'], OC_ARTICULO: ['LINEA', 'ARTICULO', 'UNIDAD', 'BULTO', 'MANUAL'] }

// Trabajos de etiquetado: de dónde salen los registros
export const ORIGENES = () => [
  ['OC', t('Purchase orders'), t('One or several POs: their lines, items or packages.')],
  ['ARTICULOS', t('Items'), t('Items without a PO: item and product data.')],
  ['PACKING', t('Packing list'), t('Each package of a level of the packing list (pallets, cartons, inner packs…).')],
]

// Operadores de las condiciones (los mismos del servidor: reglas.OPERADORES)
export const OPERADORES = () => ({
  existe: t('has a value'), vacio: t('is empty'), igual: t('is'), distinto: t('is not'), en: t('is one of'), no_en: t('is none of'),
  contiene: t('contains'), no_contiene: t('does not contain'), empieza: t('starts with'), termina: t('ends with'),
  mayor: t('is greater than'), mayor_igual: t('is at least'), menor: t('is less than'), menor_igual: t('is at most'),
  entre: t('is between'), en_familia: t('is in the family (or its subfamilies)'), coincide: t('matches the pattern'),
})
export const SIN_VALOR = ['existe', 'vacio']
export const NUMERICOS = ['mayor', 'mayor_igual', 'menor', 'menor_igual', 'entre']
export const LISTAS = ['en', 'no_en']

// Clase de cada problema de un trabajo (generacion.CATEGORIAS)
export const CATEGORIAS = () => ({
  dato_obligatorio: t('Required data missing'), dato_opcional: t('Optional data empty'), conflicto: t('Conflicts'),
  configuracion: t('Configuration'), empaque: t('Packaging'), inconsistencia: t('Inconsistencies (PO vs packing list)'),
  excepcion: t('Exceptions'), cantidad: t('Quantities'), codigo: t('Barcodes and QR'), diseno: t('Design and layout'),
})

export const AMBITOS = () => ({
  GENERAL: t('General (whole organization)'),
  FAMILIA: t('Labeling family'),
  PRODUCTO: t('Product (all its variants)'),
  ARTICULO: t('Item (one variant)'),
  OC: t('Exception for one PO'),
  REGLA: t('Any record that meets the conditions'),
})

// Tamaños habituales (ancho × alto en mm); el usuario puede poner cualquier otro
export const TAMANOS = [
  ['100 × 50 mm', 100, 50],
  ['100 × 150 mm (4 × 6 in)', 101.6, 152.4],
  ['102 × 76 mm (4 × 3 in)', 101.6, 76.2],
  ['76 × 51 mm (3 × 2 in)', 76.2, 50.8],
  ['60 × 40 mm', 60, 40],
  ['50 × 25 mm', 50, 25],
  ['38 × 25 mm', 38.1, 25.4],
  ['70 × 37 mm (A4 3 × 8)', 70, 37],
]

const FACTOR = { mm: 1, cm: 10, in: 25.4 }
export const aUnidad = (mm, unidad) => Math.round((Number(mm) / FACTOR[unidad || 'mm']) * 1000) / 1000
export const aMm = (valor, unidad) => Math.round(Number(valor) * FACTOR[unidad || 'mm'] * 1000) / 1000
export const PT_MM = 25.4 / 72

export const SIMBOLOGIAS = () => [
  ['code128', 'CODE 128', t('Internal codes, references: letters and digits')],
  ['code39', 'CODE 39', t('Capital letters and digits')],
  ['ean13', 'EAN-13', t('Registered GS1 retail code (13 digits with check digit)')],
  ['upca', 'UPC-A', t('Registered GS1 retail code (12 digits)')],
  ['ean8', 'EAN-8', t('Short GS1 retail code (8 digits)')],
  ['qr', 'QR', t('Any text or link')],
]

// Las fuentes de las etiquetas (las mismas que usa el servidor), una sola vez por sesión
let fuentesCargadas = null
export function cargarFuentes() {
  if (fuentesCargadas) return fuentesCargadas
  const familias = { LiberationSans: 'sans', LiberationSerif: 'serif', LiberationMono: 'mono' }
  const estilos = [['Regular', 400, 'normal'], ['Bold', 700, 'normal'], ['Italic', 400, 'italic'], ['BoldItalic', 700, 'italic']]
  const caras = []
  for (const familia of Object.keys(familias)) {
    for (const [sufijo, peso, estilo] of estilos) {
      const f = new FontFace(`Etiqueta-${familias[familia]}`, `url(/api/etiquetas/fuentes/${familia}-${sufijo}.ttf)`, { weight: String(peso), style: estilo })
      document.fonts.add(f)
      caras.push(f.load().catch(() => null))
    }
  }
  fuentesCargadas = Promise.all(caras)
  return fuentesCargadas
}

// Medida de un texto en mm con la fuente de la etiqueta (para maquetar en el editor)
let lienzoMedida = null
export function anchoTexto(texto, estilo, tam) {
  lienzoMedida = lienzoMedida || document.createElement('canvas').getContext('2d')
  lienzoMedida.font = `${estilo.cursiva ? 'italic ' : ''}${estilo.negrita ? 700 : 400} ${tam}pt Etiqueta-${estilo.fuente || 'sans'}`
  const esp = (estilo.espaciado || 0) * Math.max(texto.length - 1, 0)
  return (lienzoMedida.measureText(texto).width * 0.75 + esp) * PT_MM // px a 96 ppp → pt → mm
}

// Partir y ajustar como el servidor (render.py): por palabras, reducir hasta el mínimo o cortar con «…»
export function maquetar(texto, estilo, ancho, alto) {
  const rel = estilo.relleno || 0
  const w = Math.max(ancho - 2 * rel, 0.1)
  const h = Math.max(alto - 2 * rel, 0.1)
  const partir = (tam) => {
    if (!estilo.multilinea) return [texto.split('\n')[0]]
    const lineas = []
    for (const parrafo of texto.split('\n')) {
      let actual = ''
      for (const palabra of parrafo.split(' ')) {
        const prueba = actual ? `${actual} ${palabra}` : palabra
        if (anchoTexto(prueba, estilo, tam) <= w || !actual) actual = prueba
        else {
          lineas.push(actual)
          actual = palabra
        }
      }
      lineas.push(actual)
    }
    return lineas
  }
  const cabe = (lineas, tam) => lineas.every((l) => anchoTexto(l, estilo, tam) <= w + 1e-6)
    && (lineas.length - 1) * tam * (estilo.interlineado || 1.15) * PT_MM + tam * PT_MM <= h + 1e-6
  let tam = estilo.tam || 10
  let lineas = partir(tam)
  let desborda = !cabe(lineas, tam)
  if (desborda && estilo.ajuste === 'reducir') {
    while (desborda && tam - 0.25 >= (estilo.tam_min || 6)) {
      tam -= 0.25
      lineas = partir(tam)
      desborda = !cabe(lineas, tam)
    }
  }
  if (desborda && estilo.ajuste === 'cortar') {
    const alto_linea = tam * (estilo.interlineado || 1.15) * PT_MM
    const maximo = estilo.multilinea ? Math.max(Math.floor((h - tam * PT_MM) / alto_linea) + 1, 1) : 1
    if (lineas.length > maximo) {
      lineas = lineas.slice(0, maximo)
      lineas[maximo - 1] += '…'
    }
    lineas = lineas.map((l) => {
      if (anchoTexto(l, estilo, tam) <= w) return l
      let x = l.replace(/…$/, '')
      while (x && anchoTexto(`${x}…`, estilo, tam) > w) x = x.slice(0, -1)
      return `${x}…`
    })
    desborda = false
  }
  return { lineas, tam, desborda, interlinea: tam * (estilo.interlineado || 1.15) * PT_MM }
}

// Transformaciones de las partes de un código (render._transformar)
export const TRANSFORMACIONES = () => ({ mayus: t('Capitals'), minus: t('Lowercase'), solo_digitos: t('Digits only'),
  sin_espacios: t('No spaces'), alfanumerico: t('Letters and digits only') })
function transformar(v, parte) {
  for (const x of parte.transformar || []) {
    if (x === 'mayus') v = v.toUpperCase()
    else if (x === 'minus') v = v.toLowerCase()
    else if (x === 'solo_digitos') v = v.replace(/\D/g, '')
    else if (x === 'sin_espacios') v = v.replace(/\s/g, '')
    else if (x === 'alfanumerico') v = v.replace(/[^\p{L}\p{N}]/gu, '')
  }
  if (parte.recortar) v = v.slice(0, parte.recortar)
  if (parte.rellenar) v = v.padStart(parte.rellenar, parte.relleno || '0')
  return v
}
// El texto que codifica un código: sus partes unidas por el separador o su texto con {{campos}}
export function valorCodigo(e, valores, tipos) {
  if (!e.partes?.length) return sustituir(e.valor, valores, tipos)
  return e.partes.map((p) => (p.tipo === 'fijo' ? transformar(p.texto || '', p)
    : (formatear(valores[p.campo], null, tipos[p.campo]) == null ? null : transformar(formatear(valores[p.campo], null, tipos[p.campo]), p))))
    .filter((x) => x != null).join(e.separador || '')
}

export const nuevoId = (tipo) => `${tipo}-${Math.random().toString(36).slice(2, 8)}`

export function elementoNuevo(tipo, x = 5, y = 5, extra = {}) {
  const base = { id: nuevoId(tipo), tipo, x, y, w: 40, h: 8, rot: 0, visible: true, bloqueado: false }
  if (tipo === 'texto') return { ...base, contenido: t('Text'), estilo: { tam: 10 }, ...extra }
  if (tipo === 'campo') return { ...base, w: 50, campo: extra.campo, estilo: { tam: 10 }, si_vacio: 'advertir', ...extra }
  if (tipo === 'codigo') return { ...base, w: 50, h: 18, simbologia: 'code128', valor: '{{articulo.sku}}', legible: true, margen: 1, ...extra }
  if (tipo === 'imagen') return { ...base, w: 20, h: 12, fuente_imagen: 'campo', campo: 'organizacion.logo', encaje: 'contener', ...extra }
  if (tipo === 'rect') return { ...base, w: 30, h: 15, relleno: null, borde: '#000000', grosor: 0.3, ...extra }
  if (tipo === 'elipse') return { ...base, w: 15, h: 15, relleno: null, borde: '#000000', grosor: 0.3, ...extra }
  if (tipo === 'linea') return { ...base, w: 40, h: 0, color: '#000000', grosor: 0.3, ...extra }
  if (tipo === 'tabla') return { ...base, w: 80, h: 30, alto_fila: 5, encabezado: true, cuadricula: true, desborde: 'error', totales: [],
    color: '#000000', grosor: 0.2, estilo: { tam: 7, tam_min: 5 }, coleccion: '', columnas: [], ...extra }
  return { ...base, ...extra }
}

// El valor como lo imprime el servidor (render.formatear): números con miles
// y decimales, fechas con su patrón, mayúsculas o minúsculas
const MESES = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC']
const vacio = (v) => v == null || (typeof v === 'string' && !v.trim())
export function formatear(v, formato, tipo = 'texto') {
  if (vacio(v)) return null
  const f = formato || {}
  const t = f.tipo || 'auto'
  if (t === 'numero' || (t === 'auto' && (tipo === 'numero' || typeof v === 'number'))) {
    const n = Number(v)
    if (Number.isNaN(n)) return String(v)
    const dec = t === 'numero' ? f.decimales || 0 : Number.isInteger(n) ? 0 : 2
    const txt = Math.abs(n).toFixed(dec)
    const [ent, frac] = txt.split('.')
    const conMiles = f.miles === false ? ent : ent.replace(/\B(?=(\d{3})+(?!\d))/g, ',')
    return `${n < 0 ? '-' : ''}${conMiles}${frac ? `.${frac}` : ''}`
  }
  if (t === 'fecha' || (t === 'auto' && tipo === 'fecha')) {
    const m = String(v).match(/^(\d{4})-(\d{2})-(\d{2})/)
    if (!m) return String(v)
    const [, a, mes, d] = m
    return { 'dd/mm/aaaa': `${d}/${mes}/${a}`, 'aaaa-mm-dd': `${a}-${mes}-${d}`, 'mm/dd/aaaa': `${mes}/${d}/${a}`,
      'dd-mmm-aaaa': `${d}-${MESES[Number(mes) - 1]}-${a}` }[f.fecha || 'dd/mm/aaaa']
  }
  if (t === 'mayus') return String(v).toUpperCase()
  if (t === 'minus') return String(v).toLowerCase()
  return String(v)
}
// Reemplaza {{campo}} por su valor (vacío si no hay)
export const CAMPO = /\{\{\s*([\w.]+)\s*\}\}/g
export const sustituir = (texto, valores, tipos) =>
  (texto || '').replace(CAMPO, (_, c) => formatear(valores[c], null, tipos[c]) ?? '')

// Si el elemento se dibuja según su condición (render.cumple → reglas.cumple_condicion)
const txt = (v) => (v == null ? '' : String(v).trim().toLowerCase())
export function cumple(cond, valores) {
  if (!cond?.campo) return true
  const v = valores[cond.campo]
  const op = cond.op || 'existe'
  let esperado = cond.valor
  if (op === 'existe') return !vacio(v)
  if (op === 'vacio') return vacio(v)
  if (NUMERICOS.includes(op)) {
    const n = Number(v)
    if (v == null || v === '' || Number.isNaN(n)) return false
    if (op === 'entre') {
      const [a, b] = (Array.isArray(esperado) ? esperado : []).map(Number).sort((x, y) => x - y)
      return n >= a && n <= b
    }
    const m = Number(esperado)
    return { mayor: n > m, mayor_igual: n >= m, menor: n < m, menor_igual: n <= m }[op]
  }
  if (LISTAS.includes(op) && typeof esperado === 'string') esperado = esperado.split(',').map((x) => x.trim()).filter(Boolean)
  const s = txt(v)
  if (op === 'igual') return s === txt(esperado)
  if (op === 'distinto') return s !== txt(esperado)
  if (op === 'en') return (esperado || []).map(txt).includes(s)
  if (op === 'no_en') return !(esperado || []).map(txt).includes(s)
  if (op === 'contiene') return s.includes(txt(esperado))
  if (op === 'no_contiene') return !s.includes(txt(esperado))
  if (op === 'empieza') return s.startsWith(txt(esperado))
  if (op === 'termina') return s.endsWith(txt(esperado))
  if (op === 'en_familia') return String(v || '').split('/').map(txt).includes(txt(esperado))
  if (op === 'coincide') {
    try {
      return new RegExp(`^(?:${esperado})$`, 'i').test(v == null ? '' : String(v))
    } catch {
      return false
    }
  }
  return false
}

export const TRAZOS = { discontinuo: (g) => `${3 * g + 0.7} ${2 * g + 0.5}`, punteado: (g) => `${Math.max(g, 0.18)} ${2 * g + 0.35}` }

// El resumen de cambios que guarda el servidor (diseno.resumen_cambios) en el idioma de la pantalla
const PROPIEDADES_DISENO = () => ({ margen: t('Safe margin'), fondo: t('Background'), borde: t('Border'), dpi: t('PNG resolution'), hoja: t('How it prints') })
export function textoCambios(s) {
  if (!s) return ''
  return s.split('; ').map((parte) => {
    let m = parte.match(/^size (.+) mm$/)
    if (m) return `${t('Dimensions')}: ${m[1]} mm`
    m = parte.match(/^(\w+) changed$/)
    if (m) return `${PROPIEDADES_DISENO()[m[1]] || m[1]}: ${t('changed')}`
    m = parte.match(/^(added|removed|edited): (.*)$/)
    if (m) return `${{ added: t('Added'), removed: t('Removed'), edited: t('Changed') }[m[1]]}: ${m[2]}`
    if (parte === 'layer order changed') return `${t('Layers')}: ${t('order changed')}`
    if (parte === 'no changes') return t('No changes')
    return parte
  }).join(' · ')
}

// Nombre legible de cada propiedad de un elemento (para comparar versiones)
export const PROPIEDADES = () => ({
  x: 'X', y: 'Y', w: t('Width'), h: t('Height'), rot: t('Rotation'), nombre: t('Name'), visible: t('Hide'), bloqueado: t('Lock'),
  grupo: t('Group'), condicion: t('Show only if'), contenido: t('Text'), campo: t('Field'), prefijo: t('Prefix'), sufijo: t('Suffix'),
  formato: t('Format'), si_vacio: t('If the data is empty'), alternativo: t('Alternative text'), estilo: t('Text style'),
  fuente_imagen: t('Image source'), adjunto_id: t('Image'), datos: t('Image'), encaje: t('Fit'), simbologia: t('Symbology'),
  valor: t('Value to encode'), legible: t('Human-readable text'), margen: t('Quiet zone'), correccion: t('Error correction'),
  relleno: t('Fill'), borde: t('Border'), grosor: t('Thickness'), radio: t('Corner radius'), trazo: t('Stroke'), color: t('Color'),
})
