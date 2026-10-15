import { t, tx } from '@/i18n/index.js'
import { api } from '@/nucleo/api'

// Etiquetado: textos y medidas comunes a las pantallas del módulo.
// El diseño guarda todo en milímetros y los tamaños de letra en puntos; la
// unidad elegida (mm, cm, pulgadas) solo cambia cómo se muestran.

// Lo que la interfaz necesita para armar sus formularios (qué se etiqueta,
// cuántas salen, niveles, excepciones, simbologías, tamaños): lo da el servidor
// (GET /etiquetas/catalogos), una vez por sesión.
let catalogo = null
export function catalogos() {
  catalogo = catalogo || api.get('/etiquetas/catalogos').catch((e) => {
    catalogo = null
    throw e
  })
  return catalogo
}
export function olvidarCatalogos() {
  catalogo = null
}

// Qué se etiqueta (sujeto del tipo de etiqueta)
export const SUJETOS = () => ({ ARTICULO: t('Item'), BULTO: t('Package'), DOCUMENTO: t('Document') })
export const SUJETOS_PLURAL = () => ({ ARTICULO: t('Items'), BULTO: t('Packages'), DOCUMENTO: t('Documents') })
// Cuántas etiquetas salen de cada registro
export const CANTIDADES = () => ({
  POR_UNIDAD: t('One per unit (piece or pair)'), POR_LINEA: t('One per PO line'), POR_ARTICULO: t('One per distinct item'),
  POR_BULTO: t('One per package'), POR_DOCUMENTO: t('One per document'), MANUAL: t('Quantity entered by hand'),
})
// Dónde se pone un diseño (la fila de la matriz)
export const NIVELES = () => ({ GENERAL: t('Whole company'), FAMILIA: t('Family'), PRODUCTO: t('Product'), SKU: t('Item (one size)'),
  TIPO_EMPAQUE: t('Package type') })
// Excepciones: la primera parte de la frase «Si … usar …»
export const CONTEXTOS = () => ({
  PAIS_DESTINO: t('the destination country is'), CENTRO_DESTINO: t('the destination center is'), SOCIEDAD: t('the buying company is'),
  PROVEEDOR: t('the supplier is'), CONDICION: t('Advanced: the conditions are met'), OC: t('the purchase order is'),
})
// Dónde está el diseño elegido, en palabras («Por la familia Calzado»)
export function textoDonde(nivel, destino) {
  if (nivel === 'GENERAL') return t('Whole company')
  const plantilla = { FAMILIA: t('Family {0}'), PRODUCTO: t('Product {0}'), SKU: t('Item {0}'), TIPO_EMPAQUE: t('Package type {0}') }[nivel]
  return plantilla ? plantilla.replace('{0}', tx(destino || '')) : nivel
}
// La excepción en una frase: «Si el país destino es Panamá, Costa Rica»
export function textoExcepcion(u) {
  if (u.contexto_tipo === 'OC') return t('If the purchase order is {0}', [u.oc || u.oc_id])
  if (u.contexto_tipo === 'CONDICION') {
    const partes = []
    if (u.condiciones?.length) partes.push(t('{0} conditions', [u.condiciones.length]))
    if (u.vigente_desde || u.vigente_hasta) partes.push(textoVigencia(u))
    return `${t('If')} ${partes.join(' · ') || t('the conditions are met')}`
  }
  const valores = (u.contexto_nombres?.length ? u.contexto_nombres : u.contexto_valores || []).map((x) => tx(String(x))).join(', ')
  return `${t('If')} ${CONTEXTOS()[u.contexto_tipo] || u.contexto_tipo} ${valores}`
}
export function textoVigencia(u) {
  const f = (v) => (v ? new Date(`${v}T00:00:00`).toLocaleDateString() : '')
  if (u.vigente_desde && u.vigente_hasta) return t('from {0} to {1}', [f(u.vigente_desde), f(u.vigente_hasta)])
  if (u.vigente_desde) return t('from {0}', [f(u.vigente_desde)])
  if (u.vigente_hasta) return t('until {0}', [f(u.vigente_hasta)])
  return ''
}
// Por qué un registro lleva su diseño (Eleccion.porque del servidor)
export function textoPorque(e) {
  const p = e?.porque || {}
  if (!e || p.clase === 'sin_diseno') return t('No design applies')
  if (p.clase === 'elegida') return t('Chosen for this job')
  const donde = textoDonde(p.nivel, p.destino)
  if (p.clase === 'oc') return t('Special design for PO {0}', [p.oc])
  if (p.clase === 'excepcion') return `${donde} · ${textoExcepcion({ contexto_tipo: p.contexto_tipo, contexto_valores: p.contexto_valores })}`
  return donde
}

// Trabajos de etiquetado: de dónde salen los registros
export const ORIGENES = () => [
  ['OC', t('Purchase orders'), t('One or several POs: their items, their packages and a content sheet.')],
  ['PACKING', t('Packing list'), t('The packages of a packing list and the items inside them.')],
  ['ARTICULOS', t('Items'), t('Items without a PO: item and product data.')],
  ['FAMILIA', t('A family'), t('The items of a labeling family in the open POs.')],
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
// Simbologías: las da el servidor (catalogos().simbologias) con su nombre y para qué sirven

const FACTOR = { mm: 1, cm: 10, in: 25.4 }
export const aUnidad = (mm, unidad) => Math.round((Number(mm) / FACTOR[unidad || 'mm']) * 1000) / 1000
export const aMm = (valor, unidad) => Math.round(Number(valor) * FACTOR[unidad || 'mm'] * 1000) / 1000
export const PT_MM = 25.4 / 72

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
  // Chino, árabe y devanagari con las fuentes Noto del servidor (escritura.py); el navegador
  // solo las descarga si el texto usa esas letras (unicode-range)
  for (const [archivo, rango] of ESCRITURAS) {
    for (const familia of Object.values(familias)) {
      for (const [peso, sufijo] of [[400, 'Regular'], [700, 'Bold']]) {
        for (const estilo of ['normal', 'italic']) {
          document.fonts.add(new FontFace(`Etiqueta-${familia}`, `url(/api/etiquetas/fuentes/${archivo}-${sufijo}.ttf)`,
            { weight: String(peso), style: estilo, unicodeRange: rango }))
        }
      }
    }
  }
  fuentesCargadas = Promise.all(caras)
  return fuentesCargadas
}
const ESCRITURAS = [
  ['NotoSansArabic', 'U+0600-06FF, U+0750-077F, U+08A0-08FF, U+FB50-FDFF, U+FE70-FEFF'],
  ['NotoSansDevanagari', 'U+0900-097F, U+A8E0-A8FF'],
  ['NotoSansSC', 'U+2E80-2FDF, U+3000-33FF, U+3400-4DBF, U+4E00-9FFF, U+F900-FAFF, U+FE30-FE4F, U+FF00-FFEF'],
]
// Avisa cuando el navegador termina de bajar una fuente (p. ej. la de chino al escribir un texto en chino)
export function alCargarFuente(fn) {
  document.fonts.addEventListener('loadingdone', fn)
  return () => document.fonts.removeEventListener('loadingdone', fn)
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

// ---- Recuadro que se ajusta al contenido (render.ajustar_caja) ---------------------------------
export const AJUSTES_CAJA = () => [['no', t('Fixed size')], ['ambos', t('Fit the box to the content')],
  ['ancho', t('Fit the width')], ['alto', t('Fit the height (wrap lines)')]]
export const AJUSTABLES = ['texto', 'campo', 'tabla', 'imagen']
const ANCLA_H = { izq: 'ini', centro: 'centro', der: 'fin' }
const ANCLA_V = { arriba: 'ini', medio: 'centro', abajo: 'fin' }
function anclar(inicio, largo, nuevo, ancla, minimo, maximo) {
  const disponible = { ini: maximo - inicio, fin: inicio + largo - minimo,
    centro: 2 * Math.min(inicio + largo / 2 - minimo, maximo - inicio - largo / 2) }[ancla]
  const n = Math.max(Math.min(nuevo, Math.max(disponible, 1)), 0.5)
  return [{ ini: inicio, centro: inicio + (largo - n) / 2, fin: inicio + largo - n }[ancla], n]
}
function partirEn(texto, estilo, tam, ancho) {
  const lineas = []
  for (const parrafo of texto.split('\n')) {
    let actual = ''
    for (const palabra of parrafo.split(' ')) {
      const prueba = actual ? `${actual} ${palabra}` : palabra
      if (anchoTexto(prueba, estilo, tam) <= ancho || !actual) actual = prueba
      else {
        lineas.push(actual)
        actual = palabra
      }
    }
    lineas.push(actual)
  }
  return lineas
}
// Ancho y alto (mm, con el relleno) que ocupa el texto con su letra sin reducir; con `ancho`, partido en líneas
export function medidaTexto(texto, estilo, ancho = null) {
  const tam = estilo.tam || 10
  const rel = estilo.relleno || 0
  const txt = estilo.mayusculas ? texto.toUpperCase() : texto
  const lineas = ancho != null ? partirEn(txt, estilo, tam, Math.max(ancho - 2 * rel, 0.1))
    : estilo.multilinea ? txt.split('\n') : txt.split('\n').slice(0, 1)
  const w = Math.max(0, ...lineas.map((l) => anchoTexto(l, estilo, tam))) + 2 * rel
  const h = (lineas.length - 1) * tam * (estilo.interlineado || 1.15) * PT_MM + tam * PT_MM + 2 * rel
  return [w, h]
}
// El recuadro del elemento ajustado a su contenido (texto, filas de la tabla o proporción de la imagen),
// desde su anclaje y dentro del área segura. Devuelve { x, y, w, h, multilinea } o null si no se ajusta.
export function ajustarCaja(e, diseno, { texto = null, filas = null, proporcion = null } = {}) {
  const modo = e.ajustar || 'no'
  if (modo === 'no' || !AJUSTABLES.includes(e.tipo)) return null
  let { x, y, w, h } = e
  const m = diseno.margen || 0
  const limX = [m, diseno.ancho - m]
  const limY = [m, diseno.alto - m]
  const est = { fuente: 'sans', tam: 10, interlineado: 1.15, espaciado: 0, relleno: 0, alin: 'izq', valign: 'arriba', ...(e.estilo || {}) }
  let multilinea = est.multilinea
  if (['texto', 'campo'].includes(e.tipo) && texto != null) {
    if (modo === 'ancho' || modo === 'ambos') [x, w] = anclar(x, w, medidaTexto(texto, est)[0], ANCLA_H[est.alin], ...limX)
    if (modo === 'alto' || modo === 'ambos') {
      multilinea = true
      ;[y, h] = anclar(y, h, medidaTexto(texto, { ...est, multilinea }, modo === 'alto' ? w : null)[1], ANCLA_V[est.valign], ...limY)
    }
  } else if (e.tipo === 'tabla' && filas != null && modo !== 'ancho') {
    const fijas = (e.encabezado ? 1 : 0) + (e.totales?.length ? 1 : 0)
    ;[y, h] = anclar(y, h, (e.alto_fila || 5) * Math.max(filas + fijas, 1), 'ini', ...limY)
  } else if (e.tipo === 'imagen' && proporcion) {
    if (modo === 'ancho') [x, w] = anclar(x, w, h / proporcion, 'ini', ...limX)
    else [y, h] = anclar(y, h, w * proporcion, 'ini', ...limY)
  } else return null
  const r = (v) => Math.round(v * 1000) / 1000
  return { x: r(x), y: r(y), w: r(w), h: r(h), multilinea }
}
// La imagen que muestra un elemento imagen (subida, propia del diseño o de un campo)
export function fuenteImagen(e, valores) {
  if (e.tipo !== 'imagen') return null
  if (e.fuente_imagen === 'adjunto' && e.adjunto_id) return `/api/etiquetas/imagenes/${e.adjunto_id}`
  if (e.fuente_imagen === 'datos' && e.datos) return e.datos
  const v = e.fuente_imagen === 'campo' ? valores[e.campo] : null
  return typeof v === 'string' && (v.startsWith('data:image/') || v.startsWith('/')) ? v : null
}
// Los elementos «debajo de» otro toman su borde inferior más la separación, en cadena (cajas: id → {x, y, w, h})
export function apilar(elementos, cajas) {
  const porId = Object.fromEntries(elementos.map((e) => [e.id, e]))
  const listos = new Set()
  const colocar = (id, camino = new Set()) => {
    if (listos.has(id) || camino.has(id)) return
    const e = porId[id]
    if (e?.debajo_de && cajas[e.debajo_de]) {
      camino.add(id)
      colocar(e.debajo_de, camino)
      const a = cajas[e.debajo_de]
      cajas[id] = { ...cajas[id], y: Math.round((a.y + a.h + (e.separacion ?? 1)) * 1000) / 1000 }
    }
    listos.add(id)
  }
  for (const e of elementos) colocar(e.id)
  return cajas
}
// Los elementos que siguen (directa o indirectamente) a este: no pueden ser su «de arriba»
export function seguidores(elementos, id) {
  const res = new Set()
  let cambio = true
  while (cambio) {
    cambio = false
    for (const e of elementos) {
      if (e.debajo_de && (e.debajo_de === id || res.has(e.debajo_de)) && !res.has(e.id)) {
        res.add(e.id)
        cambio = true
      }
    }
  }
  return res
}
// El texto que muestra un texto o un campo con estos valores (vacío si no hay dato)
export function textoElemento(e, valores, tipos) {
  if (e.tipo === 'texto') return sustituir(e.contenido, valores, tipos)
  if (e.tipo !== 'campo') return ''
  let v = formatear(valores[e.campo], e.formato, tipos[e.campo])
  if (v == null) v = e.si_vacio === 'alternativo' ? e.alternativo || '' : ''
  return v ? `${e.prefijo || ''}${v}${e.sufijo || ''}` : ''
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
  if (tipo === 'texto') return { ...base, contenido: t('Text'), estilo: { tam: 10 }, ajustar: 'ambos', ...extra }
  if (tipo === 'campo') return { ...base, w: 50, campo: extra.campo, estilo: { tam: 10 }, si_vacio: 'advertir', ajustar: 'ambos', ...extra }
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
// y decimales, fechas con su patrón, sí/no, mayúsculas o minúsculas, con el
// idioma y los separadores del diseño (ponerRegional)
const MESES = {
  en: ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'],
  es: ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'],
  pt: ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho', 'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro'],
  fr: ['janvier', 'février', 'mars', 'avril', 'mai', 'juin', 'juillet', 'août', 'septembre', 'octobre', 'novembre', 'décembre'],
  zh: ['一', '二', '三', '四', '五', '六', '七', '八', '九', '十', '十一', '十二'].map((n) => `${n}月`),
  ar: ['يناير', 'فبراير', 'مارس', 'أبريل', 'مايو', 'يونيو', 'يوليو', 'أغسطس', 'سبتمبر', 'أكتوبر', 'نوفمبر', 'ديسمبر'],
  hi: ['जनवरी', 'फ़रवरी', 'मार्च', 'अप्रैल', 'मई', 'जून', 'जुलाई', 'अगस्त', 'सितंबर', 'अक्टूबर', 'नवंबर', 'दिसंबर'],
}
const MES_CORTO_3 = ['en', 'es', 'pt', 'fr'] // en los demás idiomas, el mes corto es el mes completo
const SI_NO = { en: ['Yes', 'No'], es: ['Sí', 'No'], pt: ['Sim', 'Não'], fr: ['Oui', 'Non'], zh: ['是', '否'], ar: ['نعم', 'لا'], hi: ['हाँ', 'नहीं'] }
export const IDIOMAS_ETIQUETA = () => [['en', t('English')], ['es', t('Spanish')], ['pt', t('Portuguese')], ['fr', t('French')],
  ['zh', t('Chinese')], ['ar', t('Arabic')], ['hi', t('Hindi')]]
// Patrones de fecha sugeridos (se puede escribir cualquiera con dd, d, mm, mmm, mmmm, aa y aaaa)
export const PATRONES_FECHA = ['dd/mm/aaaa', 'aaaa-mm-dd', 'mm/dd/aaaa', 'dd-mmm-aaaa', 'd mmmm aaaa', 'mmm aa']
let regional = {}
export function ponerRegional(diseno) {
  regional = { idioma: diseno?.idioma || 'en', miles: diseno?.separador_miles ?? ',', decimal: diseno?.separador_decimal || '.' }
}
export function fechaConPatron(a, mes, dia, patron) {
  const meses = MESES[regional.idioma] || MESES.en
  const piezas = { aaaa: String(a).padStart(4, '0'), aa: String(a % 100).padStart(2, '0'), mmmm: meses[mes - 1],
    mmm: MES_CORTO_3.includes(regional.idioma) ? meses[mes - 1].slice(0, 3).toUpperCase() : meses[mes - 1], mm: String(mes).padStart(2, '0'), dd: String(dia).padStart(2, '0'), d: String(dia) }
  return (patron || 'dd/mm/aaaa').replace(/aaaa|aa|mmmm|mmm|mm|dd|d/g, (m) => piezas[m])
}
const vacio = (v) => v == null || (typeof v === 'string' && !v.trim())
export function formatear(v, formato, tipo = 'texto') {
  if (vacio(v)) return null
  if (typeof v === 'boolean' || tipo === 'si_no') {
    const [si, no] = SI_NO[regional.idioma] || SI_NO.en
    return [true, 'yes', 'true', 1].includes(v) ? si : no
  }
  const f = formato || {}
  const t = f.tipo || 'auto'
  if (t === 'numero' || (t === 'auto' && (tipo === 'numero' || typeof v === 'number'))) {
    const n = Number(v)
    if (Number.isNaN(n)) return String(v)
    const dec = t === 'numero' ? f.decimales || 0 : Number.isInteger(n) ? 0 : 2
    const txt = Math.abs(n).toFixed(dec)
    const [ent, frac] = txt.split('.')
    const conMiles = f.miles === false ? ent : ent.replace(/\B(?=(\d{3})+(?!\d))/g, regional.miles ?? ',')
    return `${n < 0 ? '-' : ''}${conMiles}${frac ? `${regional.decimal || '.'}${frac}` : ''}`
  }
  if (t === 'fecha' || (t === 'auto' && tipo === 'fecha')) {
    const m = String(v).match(/^(\d{4})-(\d{2})-(\d{2})/)
    if (!m) return String(v)
    return fechaConPatron(Number(m[1]), Number(m[2]), Number(m[3]), f.fecha)
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
