// Convierte las frases armadas por concatenación ('Upper of ' + x + ' and sole
// of ' + y) en una sola frase con marcadores: t('Upper of {0} and sole of {1}', [x, y]).
// Así cada idioma traduce la frase entera y ordena las partes a su manera.
// Uso: node scripts/i18n-frases.mjs archivo.js|archivo.vue …
import fs from 'node:fs'
import { parseAst } from 'rollup/parseAst'

const esTextoLit = (n) => (n.type === 'Literal' && typeof n.value === 'string')
const esLlamadaConArgs = (n, fn) => n.type === 'CallExpression' && n.callee.type === 'Identifier' && n.callee.name === fn
  && n.arguments.length === 2 && esTextoLit(n.arguments[0]) && n.arguments[1].type === 'ArrayExpression'
const esLlamadaT = (n, fn) => n.type === 'CallExpression' && n.callee.type === 'Identifier' && (n.callee.name === fn)
  && n.arguments.length === 1 && esTextoLit(n.arguments[0])

function operandos(n) {
  // aplana la cadena izquierda de sumas
  if (n.type === 'BinaryExpression' && n.operator === '+') return [...operandos(n.left), n.right]
  return [n]
}

function recorrer(n, fn, visitar) {
  if (!n || typeof n.type !== 'string') return
  visitar(n)
  for (const k of Object.keys(n)) {
    const v = n[k]
    if (Array.isArray(v)) v.forEach((x) => x && typeof x.type === 'string' && recorrer(x, fn, visitar))
    else if (v && typeof v.type === 'string') recorrer(v, fn, visitar)
  }
}

export function convertir(code, fn = 't') {
  let ast
  try { ast = parseAst(code) } catch (e) { console.error('no se pudo analizar:', e.message); return code }
  const cambios = []
  const tomados = []
  recorrer(ast, fn, (n) => {
    if (!(n.type === 'BinaryExpression' && n.operator === '+')) return
    if (tomados.some(([a, b]) => n.start >= a && n.end <= b)) return
    let ops = operandos(n)
    const textos = ops.map((o) => esTextoLit(o) ? o.value : esLlamadaT(o, fn) ? o.arguments[0].value : null)
    const primero = textos.findIndex((x) => x !== null)
    if (primero < 0) return
    if (!textos.some((x) => x !== null && /[A-Za-z]{2}/.test(x))) return
    if (!ops.some((o, i) => textos[i] === null)) return // ya es todo texto
    // Lo que va antes del primer texto se suma como número: queda como un solo valor
    let grupos = ops.map((o, i) => ({ nodo: o, texto: textos[i] }))
    if (primero > 1) {
      // el nodo de la suma que abarca esos primeros operandos (incluye sus paréntesis)
      let nodo = n
      while (operandos(nodo).length > primero) nodo = nodo.left
      grupos = [{ fuente: `(${code.slice(nodo.start, nodo.end)})`, texto: null }, ...grupos.slice(primero)]
    }
    // Textos que son rutas, clases o código: no se tocan
    const fijo = grupos.filter((g) => g.texto !== null).map((g) => g.texto).join(' ')
    if (/^\s*\//.test(fijo) || /[<>{}\\^$|]/.test(fijo) || !/[a-z]/.test(fijo)) return
    if (!/\s/.test(fijo) && !/[A-Z]/.test(fijo)) return // clases, claves, ids
    let clave = '', args = []
    for (const g of grupos) {
      if (g.texto !== null) clave += g.texto
      else if (g.nodo && esLlamadaConArgs(g.nodo, fn)) {
        // otra frase ya convertida: se une con sus marcadores renumerados
        const base = args.length
        clave += g.nodo.arguments[0].value.replace(/\{(\d)\}/g, (m, i) => `{${base + Number(i)}}`)
        for (const e of g.nodo.arguments[1].elements) args.push(code.slice(e.start, e.end))
      } else { clave += `{${args.length}}`; args.push(g.fuente || code.slice(g.nodo.start, g.nodo.end)) }
    }
    if (args.length > 9) return
    const lit = `'${clave.replace(/\\/g, '\\\\').replace(/'/g, "\\'").replace(/\n/g, '\\n')}'`
    cambios.push([n.start, n.end, `${fn}(${lit}, [${args.join(', ')}])`])
    tomados.push([n.start, n.end])
  })
  cambios.sort((a, b) => b[0] - a[0])
  let r = code
  for (const [a, b, x] of cambios) r = r.slice(0, a) + x + r.slice(b)
  return r
}

if (process.argv[1] && process.argv[1].endsWith('i18n-frases.mjs')) {
  for (const ruta of process.argv.slice(2)) {
    const src = fs.readFileSync(ruta, 'utf8')
    const fn = 't'
    let r = src
    for (let i = 0; i < 4; i++) {
      r = ruta.endsWith('.vue')
        ? r.replace(/(<script setup>\n)([\s\S]*?)(<\/script>)/, (m, a, cuerpo, b) => a + convertir(cuerpo, fn) + b)
        : convertir(r, fn)
    }
    if (r !== src) { fs.writeFileSync(ruta, r); console.log('✓', ruta) }
  }
}
