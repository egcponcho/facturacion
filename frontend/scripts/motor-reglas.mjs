// Extrae la lógica de decisión de motor.js (clasificarReglas) a reglas de
// datos: por cada categoría ejecuta el motor sobre su espacio de entradas
// (atributos + composiciones de prueba), toma los hechos con que decide
// (M.hechosDe) y aprende un árbol de decisión hechos → código. Cada hoja es
// una regla (ámbito CATEGORY, condiciones del camino, RESTRICT al código).
// La subpartida por fibra predominante (Nota 2 de la Sección XI) no se
// abre en ramas: queda como mapa fibra → código dentro de la regla.
// Antes de escribir comprueba la paridad con muestras aleatorias del espacio
// completo: si el árbol no reproduce al motor, falla.
// Uso: node scripts/motor-reglas.mjs [salida.json]   (--verificar: solo compara)
import { readFileSync, writeFileSync } from 'node:fs'
import * as M from '../src/clasificacion/motor.js'

const RUTA = process.argv.find((a) => a.endsWith('.json')) || new URL('../../backend/app/data/motor_reglas.json', import.meta.url)
const SOLO_VERIFICAR = process.argv.includes('--verificar')

// Generador pseudoaleatorio fijo: el resultado no cambia entre corridas
let semilla = 20261006
const azar = () => ((semilla = (semilla * 1103515245 + 12345) % 2147483648) / 2147483648)
const uno = (xs) => xs[Math.floor(azar() * xs.length)]

// Composiciones de prueba: una por cada fibra o material que distingue el motor.
// El corte y la suela del calzado se cubren con upper/sole (mismos valores).
const COMP = {
  'comp.exterior': ['', '100% cotton', '100% polyester', '100% viscose', '100% wool', '100% silk', '100% linen', '100% leather', '100% polyurethane', '100% paper'],
  'comp.material': ['', '100% leather', '100% polyester', '100% pvc', '100% steel'],
}
const MANUALES = ['upper', 'sole', 'exterior', 'materialCinturon']
const dominio = (k) => {
  if (COMP[k]) return COMP[k]
  const a = M.ATTR_BY[k]
  if (!a) return ['']
  return a.tipo === 'check' ? [false, true] : ['', ...(a.ops || []).map((o) => o.v)]
}
const CAMPOS = [...M.HECHOS_CAMPOS, ...MANUALES, ...Object.keys(COMP)]

function ficha(tipo, asig) {
  const f = { tipo, comp: {} }
  for (const [k, v] of Object.entries(asig)) {
    if (k.startsWith('comp.')) { if (v) f.comp[k.slice(5)] = v } else if (v !== '' && v !== false) f[k] = v
  }
  return f
}
const codigo = (f) => M.digits(M.clasificarReglas(f).codigo) || ''
const base = () => Object.fromEntries(CAMPOS.map((k) => [k, dominio(k)[0]]))
const alAzar = () => Object.fromEntries(CAMPOS.map((k) => [k, uno(dominio(k))]))
const clave = (v) => (v === true ? 'true' : v === false ? 'false' : v == null ? '' : String(v))

// 1. Qué campos mueven el código en cada categoría (sensibilidad sobre bases al azar)
function relevantes(tipo) {
  const out = new Set()
  for (let i = 0; i < 160; i++) {
    const b = i === 0 ? base() : alAzar()
    const c0 = codigo(ficha(tipo, b))
    for (const k of CAMPOS) {
      if (out.has(k)) continue
      for (const v of dominio(k)) if (v !== b[k] && codigo(ficha(tipo, { ...b, [k]: v })) !== c0) { out.add(k); break }
    }
  }
  return [...out]
}

// 2. Muestras: producto completo de los campos relevantes (o muestreo si es enorme)
function muestras(tipo, campos) {
  const total = campos.reduce((n, k) => n * dominio(k).length, 1)
  const asigs = []
  if (total <= 300000) {
    const rec = (i, a) => { if (i === campos.length) { asigs.push({ ...base(), ...a }); return } for (const v of dominio(campos[i])) rec(i + 1, { ...a, [campos[i]]: v }) }
    rec(0, {})
  } else for (let i = 0; i < 60000; i++) asigs.push({ ...base(), ...Object.fromEntries(campos.map((k) => [k, uno(dominio(k))])) })
  return asigs.map((a) => { const f = ficha(tipo, a); const r = M.clasificarReglas(f); return { h: M.hechosDe(f), c: M.digits(r.codigo) || '', r } })
}

// 3. Árbol de decisión (ID3, ramas múltiples) sobre los hechos
function entropia(xs) {
  const n = {}
  xs.forEach((x) => (n[x.c] = (n[x.c] || 0) + 1))
  return Object.values(n).reduce((s, k) => s - (k / xs.length) * Math.log2(k / xs.length), 0)
}
const POR = 'fibra'
function arbol(xs, campos, conflictos) {
  const cods = new Set(xs.map((x) => x.c))
  if (cods.size === 1) return { hoja: xs[0].c, ej: xs[0] }
  let mejor = null
  const e0 = entropia(xs)
  for (const k of campos) {
    const g = {}
    xs.forEach((x) => (g[clave(x.h[k])] ||= []).push(x))
    const partes = Object.values(g)
    if (partes.length < 2) continue
    const gan = e0 - partes.reduce((s, p) => s + (p.length / xs.length) * entropia(p), 0)
    if (gan > 1e-9 && (!mejor || gan > mejor.gan + 1e-12)) mejor = { k, g, gan }
  }
  if (!mejor) {
    // Solo la fibra separa lo que queda: hoja con mapa fibra → código
    const mapa = {}
    let puro = true
    for (const x of xs) {
      const v = clave(x.h[POR])
      if (mapa[v] !== undefined && mapa[v] !== x.c) puro = false
      mapa[v] = x.c
    }
    if (!puro) conflictos.push(xs.slice(0, 3).map((x) => [x.h, x.c]))
    return { hoja: xs[0].c, mapa, ej: xs.find((x) => x.h[POR]) || xs[0] }
  }
  const hijos = Object.entries(mejor.g).map(([v, p]) => ({ v, nodo: arbol(p, campos.filter((c) => c !== mejor.k), conflictos) }))
  // Ramas con el mismo subárbol se juntan (IN; «sin dato» va en la lista como '')
  const porForma = new Map()
  for (const h of hijos) {
    const forma = JSON.stringify(sinEj(h.nodo))
    const x = porForma.get(forma)
    if (x) x.vs.push(h.v); else porForma.set(forma, { vs: [h.v], nodo: h.nodo })
  }
  const ramas = [...porForma.values()]
  // La rama con más valores es «cualquier otro valor» (también los que el motor aún no conoce)
  const llenas = ramas.filter((r) => !r.vs.includes('') && !BOOL.has(mejor.k))
  const resto = llenas.sort((a, b) => b.vs.length - a.vs.length)[0]
  if (resto && resto.vs.length > 1 && llenas.length > 1) resto.resto = llenas.filter((r) => r !== resto).flatMap((r) => r.vs)
  return { campo: mejor.k, ramas }
}
const sinEj = (n) => (n.campo === undefined ? (n.mapa ? n.mapa : n.hoja) : { c: n.campo, r: n.ramas.map((r) => [r.vs.sort(), sinEj(r.nodo)]) })
// Subpartida por fibra con el criterio del motor (pickSub): sin dato o cuero → la partida
function porFibra(mapa, v) {
  return mapa[v] !== undefined ? mapa[v] : null
}
function predecir(n, h) {
  while (n.campo !== undefined) {
    const v = clave(h[n.campo])
    const r = n.ramas.find((x) => x.vs.includes(v)) || (v !== '' && n.ramas.find((x) => x.resto))
    if (!r) return null
    n = r.nodo
  }
  return n.mapa ? porFibra(n.mapa, clave(h[POR])) : n.hoja
}
const BOOL = new Set(M.HECHOS_CAMPOS.filter((k) => M.ATTR_BY[k]?.tipo === 'check'))
function condicion(campo, r) {
  const vs = r.vs
  if (vs.length === 1 && vs[0] === '') return { campo, operador: 'EXISTS', valor: null, negado: true }
  if (BOOL.has(campo)) return { campo, operador: 'EQUAL', valor: vs[0] === 'true', negado: false }
  if (vs.includes('')) return { campo, operador: 'IN', valor: [...vs.filter(Boolean), ''], negado: false }
  if (r.resto) return { campo, operador: 'IN', valor: r.resto, negado: true }
  return vs.length === 1 ? { campo, operador: 'EQUAL', valor: vs[0], negado: false } : { campo, operador: 'IN', valor: vs, negado: false }
}
function hojas(n, camino, out) {
  if (n.campo === undefined) { out.push({ conds: camino, codigo: n.hoja, mapa: n.mapa, ej: n.ej, nodo: n }); return out }
  for (const r of n.ramas) hojas(r.nodo, [...camino, condicion(n.campo, r)], out)
  return out
}

function hojaDe(n, h) {
  while (n.campo !== undefined) {
    const v = clave(h[n.campo])
    n = (n.ramas.find((x) => x.vs.includes(v)) || (v !== '' && n.ramas.find((x) => x.resto)) || {}).nodo
    if (!n) return null
  }
  return n
}
// 4. Recorrido por todas las categorías del motor
const tipos = M.TIPOS.flatMap(([, ts]) => ts.map(([t]) => t))
const reglas = [], casos = [], resumen = []
let fallas = 0
for (const tipo of tipos) {
  let campos = relevantes(tipo), xs, raiz, malas, conflictos
  for (let intento = 0; intento < 5; intento++) {
    xs = muestras(tipo, campos)
    const feats = [...new Set(xs.flatMap((x) => Object.keys(x.h)))].filter((k) => k !== 'categoria' && k !== POR)
    conflictos = []
    raiz = arbol(xs, feats, conflictos)
    // Paridad sobre el espacio completo (todos los campos al azar)
    malas = []
    for (let i = 0; i < 3000; i++) {
      const a = alAzar(), f = ficha(tipo, a)
      const c = codigo(f), p = predecir(raiz, M.hechosDe(f))
      if (p !== c && !(p === null && c === '')) malas.push({ a, c, p, h: M.hechosDe(f) })
    }
    if (!malas.length) break
    // Un campo que el muestreo de sensibilidad no vio: el que, vuelto a su valor base, cambia el código
    const b = base(), antes = campos.length
    for (const m of malas.slice(0, 20)) {
      for (const k of CAMPOS) if (!campos.includes(k) && m.a[k] !== b[k] && codigo(ficha(tipo, { ...m.a, [k]: b[k] })) !== m.c) campos.push(k)
    }
    if (campos.length === antes) break
  }
  if (conflictos.length) { console.error(`✗ ${tipo}: los hechos no alcanzan para decidir`, JSON.stringify(conflictos[0])); fallas++ }
  if (malas.length) { console.error(`✗ ${tipo}: motor ${malas[0].c} ≠ árbol ${malas[0].p}`, JSON.stringify(malas[0].h)); fallas++ }
  const hs = hojas(raiz, [], [])
  const porHoja = new Map()
  for (const y of xs) { const n = hojaDe(raiz, y.h); if (n) (porHoja.get(n) || porHoja.set(n, []).get(n)).push(y) }
  // Hechos que deciden en esta categoría (los casos de paridad solo llevan esos)
  const usados = new Set(['categoria', POR, ...hs.flatMap((x) => x.conds.map((c) => c.campo))])
  hs.forEach((x, i) => {
    const mapa = x.mapa && new Set(Object.values(x.mapa)).size > 1 ? x.mapa : null
    const cod = mapa ? null : (x.mapa ? Object.values(x.mapa)[0] : x.codigo)
    if (!cod && !mapa) return
    const ejs = porHoja.get(x.nodo) || []
    // Explicación: los motivos del motor que comparte la mayoría de los casos de la hoja
    const veces = new Map()
    ejs.forEach((y) => new Set(y.r.razones).forEach((t) => veces.set(t, (veces.get(t) || 0) + 1)))
    const comunes = [...veces].filter(([, n]) => n >= 0.6 * ejs.length).map(([t]) => t)
    const accion = mapa ? { tipo: 'RESTRICT', codigos: [...new Set(Object.values(mapa).filter(Boolean))].sort(), por: POR, mapa } : { tipo: 'RESTRICT', codigos: [cod] }
    reglas.push({ codigo: `R-MJS-${tipo.toUpperCase()}-${String(i + 1).padStart(3, '0')}`, categoria: tipo, grupo: M.grupoTipo(tipo) || 'otro',
      condiciones: x.conds, accion, efecto: comunes.join(' · ').slice(0, 480) || null })
    // Casos de paridad: uno por hoja (y uno por fibra en las hojas con mapa)
    const vistos = new Set()
    for (const y of ejs) {
      const k = clave(y.h[POR])
      if (vistos.has(k) || (!mapa && vistos.size)) continue
      vistos.add(k)
      casos.push({ hechos: Object.fromEntries(Object.entries(y.h).filter(([c]) => usados.has(c))), codigo: y.c })
    }
  })
  resumen.push(`${tipo}: ${campos.length} campos, ${xs.length} muestras, ${hs.length} reglas${malas.length ? `, ${malas.length} diferencias` : ''}`)
}
console.log(resumen.join('\n'))
console.log(`${reglas.length} reglas, ${casos.length} casos de paridad`)
if (fallas) { console.error(`✗ ${fallas} categorías sin paridad`); process.exit(1) }

const salida = { origen: 'frontend/src/clasificacion/motor.js (clasificarReglas)', reglas, casos }
const texto = JSON.stringify(salida, null, 0).replace(/\},\{"codigo":"R-/g, '},\n{"codigo":"R-').replace(/\},\{"hechos"/g, '},\n{"hechos"')
if (SOLO_VERIFICAR) {
  const actual = readFileSync(RUTA, 'utf8')
  if (actual.trim() !== texto.trim()) { console.error('✗ motor_reglas.json no está al día con motor.js: corre node scripts/motor-reglas.mjs'); process.exit(1) }
  console.log('✓ motor_reglas.json al día con motor.js')
} else {
  writeFileSync(RUTA, texto + '\n')
  console.log('→', String(RUTA))
}
