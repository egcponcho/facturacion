// Envuelve en t() los textos de la interfaz de los .vue y .js indicados.
// Los textos fijos de las plantillas, los atributos visibles (title,
// placeholder, aria-label y las props de texto de los componentes) y las
// cadenas que parecen texto para personas dentro de las expresiones. Las
// partes dinámicas quedan como {0}, {1}… para que cada idioma ordene la frase.
// Uso: node scripts/i18n-envolver.mjs archivo.vue [más archivos…]
import fs from 'node:fs'

const ATRIBUTOS = new Set(['title', 'placeholder', 'aria-label', 'alt', 'titulo', 'etiqueta', 'vacio', 'ayuda', 'plural',
  'singular', 'texto', 'vacia-texto', 'detalle', 'subtitulo', 'label', 'confirmar'])
const SIN_TOCAR = new Set([':class', ':style', ':key', 'ref', 'v-if', 'v-else-if', 'v-show', 'v-model', ':id', ':for', ':name',
  ':type', ':to', 'v-bind:class', ':nombre', ':icono', ':src', ':href'])
const LLAMADAS_SIN_TOCAR = new Set(['get', 'post', 'put', 'patch', 'del', 'descargar', 'replace', 'querySelector',
  'getItem', 'setItem', 'removeItem', 'addEventListener', 'removeEventListener', 'emit', '$emit', 'import', 'require', 't',
  'includes', 'startsWith', 'endsWith', 'getElementById', 'matchMedia', 'createElement', 'setAttribute', 'getAttribute', 'test',
  'indexOf', 'split', 'join', 'padStart', 'scrollIntoView', 'focus', 'RegExp', 'has', 'set', 'delete', 'add', 'tr'])

const ENTIDADES = { '&nbsp;': ' ', '&amp;': '&', '&lt;': '<', '&gt;': '>', '&quot;': '"', '&#39;': "'", '&times;': '×', '&middot;': '·' }
const decodificar = (s) => s.replace(/&(nbsp|amp|lt|gt|quot|#39|times|middot);/g, (m) => ENTIDADES[m])
const comillas = (s) => `'${s.replace(/\\/g, '\\\\').replace(/'/g, "\\'").replace(/\n/g, '\\n')}'`

export function esTexto(s) {
  if (!/[A-Za-z]/.test(s)) return false
  const t = s.trim()
  if (!t) return false
  if (/^(\/|#|\.|@|https?:|var\(|url\(|mailto:|data:)/.test(t)) return false
  if (/^[\w.:-]+$/.test(t) && !/[A-Z]/.test(t)) return false // claves, clases, valores
  if (!/[a-z]/.test(t)) return false // siglas y textos en mayúsculas (PDF, CALZADO VANS)
  if (/^[a-z][\w-]*(\s+[a-z][\w-]*)+$/.test(t) && /-/.test(t)) return false // listas de clases
  if (/^[A-Za-z]+(\.[A-Za-z_]+)+$/.test(t)) return false // producto.ver
  if (/^[\w-]+\.(pdf|xlsx|csv|png|jpg|json)$/i.test(t)) return false
  if (/^\d/.test(t) && !/\s/.test(t)) return false
  if (!/\s/.test(t) && /[:/_?=\-]/.test(t)) return false // update:modelValue, Content-Type, en-US, ?x=1
  if (/^[a-z]+[A-Z]\w*$/.test(t) || /^_/.test(t)) return false // identificadores camelCase
  return true
}

let FN = 't' // nombre de la función de traducción (en motor.js es tr: ahí t es una variable)
export const usarNombre = (n) => { FN = n }

// ---- Tokenizador mínimo de JS: cadenas, plantillas, comentarios y regex ----
const PREVIO_REGEX = new Set(['(', ',', '=', ':', '[', '!', '&', '|', '?', '{', '}', ';', '+', '-', '*', '%', '<', '>', '~', '^', 'return', 'typeof', 'case', 'in', 'of', '=>', '&&', '||', '??'])

export function transformarJS(code, opciones = {}) {
  let out = ''
  let i = 0
  const n = code.length
  const tokens = [] // tokens significativos previos (para el contexto)
  const previo = (k = 1) => tokens[tokens.length - k] || ''
  while (i < n) {
    const c = code[i]
    if (c === '/' && code[i + 1] === '/') {
      const j = code.indexOf('\n', i)
      const fin = j < 0 ? n : j
      out += code.slice(i, fin); i = fin; continue
    }
    if (c === '/' && code[i + 1] === '*') {
      const j = code.indexOf('*/', i + 2)
      const fin = j < 0 ? n : j + 2
      out += code.slice(i, fin); i = fin; continue
    }
    if (c === '/' && (PREVIO_REGEX.has(previo()) || tokens.length === 0)) {
      // regex literal
      let j = i + 1, clase = false
      while (j < n) {
        if (code[j] === '\\') { j += 2; continue }
        if (code[j] === '[') clase = true
        else if (code[j] === ']') clase = false
        else if (code[j] === '/' && !clase) break
        else if (code[j] === '\n') break
        j++
      }
      j++
      while (j < n && /[a-z]/.test(code[j])) j++
      out += code.slice(i, j); tokens.push('regex'); i = j; continue
    }
    if (c === "'" || c === '"') {
      let j = i + 1
      while (j < n && code[j] !== c) { if (code[j] === '\\') j++; j++ }
      const crudo = code.slice(i, j + 1)
      const valor = crudo.slice(1, -1).replace(/\\(.)/g, (m, x) => (x === 'n' ? '\n' : x))
      const siguiente = code.slice(j + 1).match(/^\s*(\S{1,3})/)?.[1] || ''
      const p1 = previo(), p2 = previo(2), p3 = previo(3)
      const llamada = p1 === '(' && LLAMADAS_SIN_TOCAR.has(p2)
      const comparacion = ['===', '!==', '==', '!='].includes(p1) || /^(===|!==|==|!=)/.test(siguiente)
      const clave = siguiente.startsWith(':') && ['{', ','].includes(p1)
      const importa = ['import', 'from'].includes(p1) || p3 === 'import'
      const esCase = p1 === 'case'
      const enT = p1 === '(' && (p2 === 't' || p2 === FN)
      const indice = p1 === '[' && siguiente.startsWith(']') && /[\w)\]]/.test(p2.slice(-1) || '')
      const omitir = llamada || comparacion || clave || importa || esCase || enT || indice || (opciones.omitir && opciones.omitir(valor))
      if (!omitir && esTexto(valor)) out += `${FN}(${comillas(valor)})`
      else out += crudo
      tokens.push('str'); i = j + 1; continue
    }
    if (c === '`') {
      // plantilla: partes fijas y ${expresiones}
      const partes = [], exprs = []
      let j = i + 1, buf = ''
      while (j < n && code[j] !== '`') {
        if (code[j] === '\\') { buf += code[j] + code[j + 1]; j += 2; continue }
        if (code[j] === '$' && code[j + 1] === '{') {
          let prof = 1, k = j + 2
          while (k < n && prof) {
            if (code[k] === '{') prof++
            else if (code[k] === '}') prof--
            else if (code[k] === "'" || code[k] === '"' || code[k] === '`') {
              const q = code[k]; k++
              while (k < n && code[k] !== q) { if (code[k] === '\\') k++; k++ }
            }
            if (prof) k++
          }
          partes.push(buf); buf = ''
          exprs.push(code.slice(j + 2, k))
          j = k + 1; continue
        }
        buf += code[j]; j++
      }
      partes.push(buf)
      const crudo = code.slice(i, j + 1)
      const fijo = partes.join(' x ')
      const p1 = previo(), p2 = previo(2)
      const llamada = p1 === '(' && LLAMADAS_SIN_TOCAR.has(p2)
      if (!llamada && esTexto(fijo) && /[A-Za-z]{2,}/.test(fijo) && !/^\s*\//.test(partes[0])) {
        let clave = ''
        partes.forEach((p, k) => { clave += p.replace(/\\`/g, '`').replace(/\\\$/g, '$'); if (k < exprs.length) clave += `{${k}}` })
        const args = exprs.map((e) => transformarJS(e, opciones))
        out += `${FN}(${comillas(clave)}${args.length ? `, [${args.join(', ')}]` : ''})`
      } else {
        // solo las expresiones internas
        let r = '`'
        partes.forEach((p, k) => { r += p; if (k < exprs.length) r += '${' + transformarJS(exprs[k], opciones) + '}' })
        out += r + '`'
      }
      tokens.push('str'); i = j + 1; continue
    }
    // identificadores, números y operadores
    const m = code.slice(i).match(/^([A-Za-z_$][\w$]*|\d[\w.]*|===|!==|==|!=|=>|&&|\|\||\?\?|\s+|.)/s)
    const tok = m[0]
    out += tok
    if (!/^\s+$/.test(tok)) tokens.push(tok)
    i += tok.length
  }
  return out
}

// ---- Plantillas de Vue ------------------------------------------------------
function transformarTexto(txt) {
  const partes = [], exprs = []
  let i = 0, buf = ''
  while (i < txt.length) {
    if (txt.startsWith('{{', i)) {
      const j = txt.indexOf('}}', i + 2)
      partes.push(buf); buf = ''
      exprs.push(txt.slice(i + 2, j).trim())
      i = j + 2; continue
    }
    buf += txt[i]; i++
  }
  partes.push(buf)
  const fijo = partes.join('')
  if (!/[A-Za-z]{2,}/.test(fijo) || !esTexto(decodificar(fijo).replace(/\s+/g, ' ') + (exprs.length ? ' x' : ''))) {
    // solo traducir lo que haya dentro de las expresiones
    let r = ''
    partes.forEach((p, k) => { r += p; if (k < exprs.length) r += `{{ ${conTx(transformarJS(exprs[k]))} }}` })
    return r
  }
  const lead = txt.match(/^\s*/)[0], trail = txt.match(/\s*$/)[0]
  let clave = ''
  partes.forEach((p, k) => { clave += decodificar(p); if (k < exprs.length) clave += `{${k}}` })
  clave = clave.replace(/\s+/g, ' ').trim()
  const args = exprs.map((e) => conTx(transformarJS(e)))
  return `${lead}{{ t(${comillas(clave)}${args.length ? `, [${args.join(', ')}]` : ''}) }}${trail}`
}

// Lo que no es un t(...) puede traer texto del servidor: pasa por tx()
function conTx(e) {
  const x = e.trim()
  if (/^(t|tx)\(/.test(x) && cierraAlFinal(x)) return e
  if (/^[\d.]+$/.test(x) || /^(fmt\w+|M\.fmt\w+|plural|cantTxt|porUnidadTxt|diasTxt)\(/.test(x)) return e
  return `tx(${x})`
}
function cierraAlFinal(x) {
  let prof = 0
  for (let i = x.indexOf('('); i < x.length; i++) {
    if (x[i] === '(') prof++
    else if (x[i] === ')') { prof--; if (prof === 0) return i === x.length - 1 }
  }
  return false
}

function transformarEtiqueta(tag) {
  // tag: "<nombre ...>" o "<nombre .../>"
  return tag.replace(/(\s)([@:#]?[\w.:\-@#]+)(?:=("[^"]*"|'[^']*'))?/g, (m, esp, nombre, valor) => {
    if (valor === undefined) return m
    const v = valor.slice(1, -1)
    if (ATRIBUTOS.has(nombre) && esTexto(decodificar(v))) {
      return `${esp}:${nombre}="t(${comillas(decodificar(v)).replace(/"/g, '&quot;')})"`
    }
    if (nombre.startsWith(':') && ATRIBUTOS.has(nombre.slice(1))) {
      const js = v.replace(/&quot;/g, '"')
      const r = conTx(transformarJS(js))
      if (r !== js) return `${esp}${nombre}=${valor[0]}${valor[0] === '"' ? r.replace(/"/g, "'") : r}${valor[0]}`
      return m
    }
    const dinamico = nombre.startsWith(':') || nombre.startsWith('@') || nombre.startsWith('v-on:') || nombre.startsWith('v-bind:') || nombre === 'v-for'
    if (dinamico && !SIN_TOCAR.has(nombre)) {
      const js = v.replace(/&quot;/g, '"')
      const r = transformarJS(js)
      if (r !== js) return `${esp}${nombre}=${valor[0]}${valor[0] === '"' ? r.replace(/"/g, "'") : r}${valor[0]}`
    }
    return m
  })
}

export function transformarPlantilla(src) {
  let out = '', i = 0
  const n = src.length
  const crudo = [] // pila: dentro de <style>/<script> internos no se toca
  while (i < n) {
    if (src.startsWith('<!--', i)) {
      const j = src.indexOf('-->', i)
      out += src.slice(i, j + 3); i = j + 3; continue
    }
    if (src[i] === '<' && /[A-Za-z/]/.test(src[i + 1] || '')) {
      let j = i + 1, q = null
      while (j < n) {
        const c = src[j]
        if (q) { if (c === q) q = null }
        else if (c === '"' || c === "'") q = c
        else if (c === '>') break
        j++
      }
      const tag = src.slice(i, j + 1)
      const nombre = (tag.match(/^<\/?([\w-]+)/) || [])[1] || ''
      if (['code', 'pre'].includes(nombre)) { crudo.push(nombre) }
      out += tag.startsWith('</') ? tag : transformarEtiqueta(tag)
      if (tag.startsWith('</') && crudo.at(-1) === nombre) crudo.pop()
      i = j + 1; continue
    }
    // texto hasta la próxima etiqueta (saltando {{ }})
    let j = i
    while (j < n) {
      if (src.startsWith('{{', j)) { j = src.indexOf('}}', j) + 2; continue }
      if (src[j] === '<' && /[A-Za-z/!]/.test(src[j + 1] || '')) break
      j++
    }
    const txt = src.slice(i, j)
    out += crudo.length ? txt : transformarTexto(txt)
    i = j
  }
  return out
}

export function transformarVue(src) {
  const a = src.indexOf('<template>')
  const b = src.lastIndexOf('</template>')
  let r = src
  if (a >= 0 && b > a) {
    r = src.slice(0, a + 10) + transformarPlantilla(src.slice(a + 10, b)) + src.slice(b)
  }
  // <script setup>
  r = r.replace(/(<script setup>\n)([\s\S]*?)(<\/script>)/, (m, ini, cuerpo, fin) => {
    let nuevo = transformarJS(cuerpo)
    return ini + nuevo + fin
  })
  return r
}

export function asegurarImport(src, ruta) {
  const usa = ['t', 'tx'].filter((f) => new RegExp(`(^|[^\\w.$])${f}\\(`).test(src))
  if (!usa.length) return src
  const re = /import \{([^}]*)\} from '([./]+i18n\/index\.js)'\n/
  const m = src.match(re)
  if (m) {
    const ya = m[1].split(',').map((x) => x.trim()).filter(Boolean)
    const todos = [...new Set([...ya, ...usa])].sort()
    return src.replace(re, `import { ${todos.join(', ')} } from '${m[2]}'\n`)
  }
  const prof = ruta.split('/src/')[1].split('/').length - 1
  const rel = (prof === 0 ? './i18n' : '../'.repeat(prof) + 'i18n') + '/index.js'
  const linea = `import { ${usa.join(', ')} } from '${rel}'\n`
  if (ruta.endsWith('.vue')) return src.replace(/<script setup>\n/, `<script setup>\n${linea}`)
  return linea + src
}

if (process.argv[1] && process.argv[1].endsWith('i18n-envolver.mjs')) {
  for (const ruta of process.argv.slice(2)) {
    const src = fs.readFileSync(ruta, 'utf8')
    usarNombre(ruta.endsWith('motor.js') ? 'tr' : 't')
    let r = ruta.endsWith('.vue') ? transformarVue(src) : transformarJS(src)
    if (ruta.endsWith('motor.js')) {
      // Textos oficiales del SAC (español), descripción aduanal y palabras de búsqueda: no se traducen
      r = r.replace(/('\d+'\s*:\s*)tr\(('(?:[^'\\]|\\.)*')\)/g, '$1$2')
      for (const bloque of ['TIPO_ALIAS', 'TIPO_CORTO_ES', 'MAT_STOP', 'SINONIMOS_BASE', 'ISO_DE', 'NOMBRE_CALZ', 'MAT_TXT', 'CAT_MAT']) {
        r = r.replace(new RegExp(`((?:const ${bloque} =|Object\\.assign\\(${bloque},)[\\s\\S]*?\\n\\S*?[};)]+;?\\n)`, 'g'),
          (m) => m.replace(/tr\(('(?:[^'\\]|\\.)*')\)/g, '$1'))
      }
      if (!/import \{ t as tr \}/.test(r)) r = "import { t as tr } from '../i18n/index.js'\n" + r
    } else r = asegurarImport(r, fs.realpathSync(ruta))
    if (r !== src) { fs.writeFileSync(ruta, r); console.log('✓', ruta) }
  }
}
