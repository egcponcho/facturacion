// Migración única: convierte la lógica de atributos de motor.js (ATTRS,
// partesDe, detectar, categorías) en datos para el motor del servidor
// (backend/app/data/motor_atributos.json) y genera los casos de paridad
// (backend/tests/paridad/atributos.json).
//
// - Cuándo aplica cada atributo y cada parte de la composición (las funciones
//   aplica/partesDe) → ámbitos CATEGORY con condiciones, aprendidas con un
//   árbol de decisión y comprobadas contra el motor con muestras al azar.
// - Opciones imposibles (off/offCheck) → bloqueos con condiciones y mensaje.
// - Valores fijados por la composición (fijo) → derivaciones declarativas.
// - Implicaciones, valores por defecto, secciones de la ficha, patrones de
//   detección (DET_TIPO, DET_ESTILO, detectar, detectarNac), capítulos
//   compatibles por categoría (CAP_OK) y nombres → datos.
// Uso: node scripts/motor-atributos.mjs
import { writeFileSync } from 'node:fs'
import * as M from '../src/clasificacion/motor.js'

let semilla = 7
const azar = () => ((semilla = (semilla * 1103515245 + 12345) % 2147483648) / 2147483648)
const uno = (xs) => xs[Math.floor(azar() * xs.length)]
const clave = (v) => (v === true ? 'true' : v === false ? 'false' : v == null ? '' : String(v))

const TIPOS = M.TIPOS.flatMap(([, ts]) => ts.map(([t]) => t))
const FIB_TXT = { '': '', algodon: '100% cotton', sintetica: '100% polyester', artificial: '100% viscose', lana: '100% wool', seda: '100% silk',
  vegetal: '100% linen', cuero: '100% leather', otra: '100% paper' }
const CORTE_TXT = { '': '', textil: '100% polyester', cuero: '100% leather', plastico: '100% polyurethane', otro: '100% wood' }
const NAC_SEL = { edadNac: ['', 'adulto', 'nino', 'bebe'] }
const CHECKS = new Set(M.ATTRS.filter((a) => a.tipo === 'check').map((a) => a.id))
const dominio = (k) => {
  if (k === 'fibra') return Object.keys(FIB_TXT)
  if (k === 'corte_material') return Object.keys(CORTE_TXT)
  if (NAC_SEL[k]) return NAC_SEL[k]
  const a = M.ATTR_BY[k]
  return a.tipo === 'check' ? [false, true] : ['', ...(a.ops || []).map((o) => o.v)]
}
const CAMPOS = [...M.ATTR_IDS, 'edadNac', 'fibra', 'corte_material']

function ficha(tipo, asig) {
  const f = { tipo, comp: {} }
  for (const [k, v] of Object.entries(asig)) {
    if (k === 'fibra') { if (FIB_TXT[v]) f.comp.exterior = FIB_TXT[v] } else if (k === 'corte_material') { if (CORTE_TXT[v]) f.comp.corte = CORTE_TXT[v] } else if (v !== '' && v !== false) f[k] = v
  }
  return f
}
function rasgos(f) {
  const h = { categoria: f.tipo || '' }
  for (const k of M.ATTR_IDS) h[k] = CHECKS.has(k) ? !!f[k] : (f[k] || '')
  h.edadNac = f.edadNac || ''
  const pc = M.parseComp((f.comp || {}).exterior || '')
  h.fibra = pc && pc.pred ? pc.pred.grupo : ''
  const pm = M.parseMat((f.comp || {}).corte || '', 'corte')
  h.corte_material = pm && pm.pred ? pm.pred : ''
  return h
}
const base = () => Object.fromEntries(CAMPOS.map((k) => [k, dominio(k)[0]]))
const alAzar = () => Object.fromEntries(CAMPOS.map((k) => [k, azar() < 0.5 ? dominio(k)[0] : uno(dominio(k))]))

// ---- Árbol de decisión: rasgos → objetivo (cadena) -------------------------------
function entropia(xs) {
  const n = {}
  xs.forEach((x) => (n[x.y] = (n[x.y] || 0) + 1))
  return Object.values(n).reduce((s, k) => s - (k / xs.length) * Math.log2(k / xs.length), 0)
}
function arbol(xs, campos) {
  if (new Set(xs.map((x) => x.y)).size === 1) return { hoja: xs[0].y }
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
  if (!mejor) throw new Error('Los rasgos no alcanzan: ' + JSON.stringify(xs.slice(0, 2).map((x) => [x.h, x.y])))
  const porForma = new Map()
  for (const [v, p] of Object.entries(mejor.g)) {
    const nodo = arbol(p, campos.filter((c) => c !== mejor.k))
    const forma = JSON.stringify(forma_(nodo))
    const x = porForma.get(forma)
    if (x) x.vs.push(v); else porForma.set(forma, { vs: [v], nodo })
  }
  return { campo: mejor.k, ramas: [...porForma.values()] }
}
const forma_ = (n) => (n.campo === undefined ? n.hoja : { c: n.campo, r: n.ramas.map((r) => [r.vs.sort(), forma_(r.nodo)]) })
function condicion(campo, vs) {
  if (vs.length === 1 && vs[0] === '') return { campo, operador: 'EXISTS', valor: null, negado: true }
  if (vs.every((v) => v === 'true' || v === 'false')) return vs.length === 1 ? { campo, operador: 'EQUAL', valor: vs[0] === 'true', negado: false } : null
  if (vs.includes('')) return { campo, operador: 'IN', valor: [...vs.filter(Boolean), ''], negado: false }
  return vs.length === 1 ? { campo, operador: 'EQUAL', valor: vs[0], negado: false } : { campo, operador: 'IN', valor: vs, negado: false }
}
// Caminos hasta las hojas con cada objetivo: {objetivo: [grupo de condiciones]}
function caminos(n, camino = [], out = {}) {
  if (n.campo === undefined) { (out[n.hoja] ||= []).push(camino); return out }
  for (const r of n.ramas) { const c = condicion(n.campo, r.vs); caminos(r.nodo, c ? [...camino, c] : camino, out) }
  return out
}
function predecir(n, h) {
  while (n.campo !== undefined) {
    const r = n.ramas.find((x) => x.vs.includes(clave(h[n.campo])))
    if (!r) return null
    n = r.nodo
  }
  return n.hoja
}

// Aprende una función del estado (tipo fijo o al azar entre `tipos`) con paridad sobre muestras
function aprender(fn, tipos, conCategoria) {
  const campos = new Set()
  for (let i = 0; i < 200; i++) {
    const t = uno(tipos), b = i === 0 ? base() : alAzar()
    const y0 = fn(ficha(t, b))
    for (const k of CAMPOS) {
      if (campos.has(k)) continue
      for (const v of dominio(k)) if (v !== b[k] && fn(ficha(t, { ...b, [k]: v })) !== y0) { campos.add(k); break }
    }
  }
  let lista = [...campos]
  for (let intento = 0; intento < 5; intento++) {
    const xs = []
    const total = lista.reduce((n, k) => n * dominio(k).length, 1) * tipos.length
    const rec = (t, i, a) => {
      if (i === lista.length) { const f = ficha(t, { ...base(), ...a }); xs.push({ h: rasgos(f), y: fn(f) }); return }
      for (const v of dominio(lista[i])) rec(t, i + 1, { ...a, [lista[i]]: v })
    }
    if (total <= 200000) tipos.forEach((t) => rec(t, 0, {}))
    else for (let i = 0; i < 100000; i++) { const t = uno(tipos); const f = ficha(t, { ...base(), ...Object.fromEntries(lista.map((k) => [k, uno(dominio(k))])) }); xs.push({ h: rasgos(f), y: fn(f) }) }
    const feats = [...lista, ...(conCategoria && tipos.length > 1 ? ['categoria'] : [])]
    const raiz = arbol(xs, feats)
    const malas = []
    for (let i = 0; i < 2000; i++) {
      const t = uno(tipos), a = alAzar(), f = ficha(t, a)
      if (predecir(raiz, rasgos(f)) !== fn(f)) malas.push({ t, a })
    }
    if (!malas.length) return raiz
    const b = base(), antes = lista.length
    for (const m of malas.slice(0, 20)) for (const k of CAMPOS) if (!lista.includes(k) && m.a[k] !== b[k] && fn(ficha(m.t, { ...m.a, [k]: b[k] })) !== fn(ficha(m.t, m.a))) lista.push(k)
    if (lista.length === antes) throw new Error('Sin paridad: ' + JSON.stringify(malas[0]))
  }
  throw new Error('Sin paridad tras 5 intentos')
}
// Condiciones (grupos O de condiciones Y) para un objetivo; null = siempre; [] = nunca
function condiciones(raiz, objetivo) {
  const c = caminos(raiz)[objetivo] || []
  if (!c.length) return []
  if (c.some((g) => !g.length)) return null
  return c.flatMap((g, i) => g.map((x) => ({ grupo: i + 1, ...x })))
}

// ---- 1. Cuándo aplica cada atributo y cada parte de la composición ------------------------
const prep = (f) => M.prepararEstado({ ...f, comp: { ...f.comp } })
const ambitos = {}
for (const a of M.ATTRS) {
  for (const t of TIPOS) {
    const fn = (f) => (a.aplica(prep(f)) ? 'si' : 'no')
    let alguna = false
    for (let i = 0; i < 300 && !alguna; i++) alguna = fn(ficha(t, i ? alAzar() : base())) === 'si'
    if (!alguna) continue
    const c = condiciones(aprender(fn, [t], false), 'si')
    if (c && !c.length) continue
    ;(ambitos[a.id] ||= []).push({ tipo_ambito: 'CATEGORY', codigo_ambito: t, condicion: c })
  }
}
const PARTES = Object.keys(M.PARTE_LBL)
for (const p of PARTES) {
  for (const t of TIPOS) {
    const fn = (f) => (M.partesDe(f.tipo, f).includes(p) ? 'si' : 'no')
    let alguna = false
    for (let i = 0; i < 300 && !alguna; i++) alguna = fn(ficha(t, i ? alAzar() : base())) === 'si'
    if (!alguna) continue
    const c = condiciones(aprender(fn, [t], false), 'si')
    const req = M.partesPrincipales(t).includes(p)
    ;(ambitos[`comp.${p}`] ||= []).push({ tipo_ambito: 'CATEGORY', codigo_ambito: t, condicion: c, modo: req ? 'REQUIRE' : 'SHOW' })
  }
}

// ---- 2. Opciones imposibles y casillas que no aplican -----------------------------
function bloqueos(fn, tipos) {
  const raiz = aprender((f) => fn(prep(f)) || '', tipos, true)
  const out = []
  for (const [msg, grupos] of Object.entries(caminos(raiz))) {
    if (!msg) continue
    grupos.forEach((g) => out.push({ condiciones: g.map((x) => ({ grupo: 1, ...x })), mensaje: msg }))
  }
  return out
}
const tiposDe = (id) => [...new Set((ambitos[id] || []).map((x) => x.codigo_ambito))]
const bloqueoOpcion = {}, bloqueoCheck = {}
for (const a of M.ATTRS) {
  const tipos = tiposDe(a.id)
  if (!tipos.length) continue
  if (a.offCheck) bloqueoCheck[a.id] = bloqueos(a.offCheck, tipos)
  for (const o of a.ops || []) if (o.off) bloqueoOpcion[`${a.id}.${o.v}`] = bloqueos(o.off, tipos)
}

// ---- 3. Derivaciones (lo que fija la composición), secciones y defectos -----------
const ID = { cuero: 'cuero', textil: 'textil', plastico: 'plastico', otro: 'otro' }
const RESPALDO = ['composicion', 'texto%']
const DERIVACION = {
  genero: { modo: 'constante', valor: 'F', cuando: [{ campo: 'categoria', operador: 'IN', valor: ['falda', 'vestido', 'brasier'] }, { campo: 'edad', operador: 'IN', valor: ['general', ''] }], motivo: 'categoria' },
  edad: { modo: 'valor', desde: 'edadNac', mapa: { bebe: 'bebe', '*': 'general' }, motivo: 'categoria' },
  upper: { modo: 'material', parte: 'corte', lectura: 'corte' },
  sole: { modo: 'material', parte: 'suela', lectura: 'suela' },
  materialCinturon: { modo: 'material', parte: 'material', mapa: { ...ID, metal: 'otro' }, metal: true, respaldo_texto: true },
  exterior: { modo: 'material', parte: 'exterior', mapa: ID },
  materialGorra: { modo: 'material', parte: 'exterior', mapa: { textil: 'textil', cuero: 'otro', plastico: 'otro', otro: 'otro' }, paja: true },
  materialBotella: { modo: 'clase', parte: 'material', mapa: { 'metal+aluminio': 'aluminio', metal: 'acero', plastico: 'plastico' } },
  materialAvio: { modo: 'clase', parte: 'material', mapa: { metal: 'metal', plastico: 'plastico', textil: 'textil', cuero: 'cuero', '*': 'otro' } },
  materialLlavero: { modo: 'material', parte: 'material', mapa: { cuero: 'cuero', textil: 'textil', plastico: 'plastico' }, metal: true },
  materialMueble: { modo: 'clase', parte: 'material', mapa: { metal: 'metal', madera: 'madera', plastico: 'plastico' } },
  materialBisu: { modo: 'clase', parte: 'material', mapa: { metal: 'metal', cuero: 'cuero', textil: 'textil', '*': 'otro' } },
  materialBolsa: { modo: 'clase', parte: 'material', mapa: { papel: 'papel', textil: 'tela', plastico: 'plastico' } },
  materialCaja: { modo: 'clase', parte: 'material', mapa: { 'papel+corrugado': 'corrugado', papel: 'plegadizo', plastico: 'plastico' } },
  materialGancho: { modo: 'clase', parte: 'material', mapa: { plastico: 'plastico', metal: 'metal', madera: 'madera' } },
  materialEtiqueta: { modo: 'clase', parte: 'material', mapa: { papel: 'papel', textil: 'tejida', plastico: 'plastico' } },
}
const SECCION = { genero: 'producto', edad: 'derivado' }
for (const a of M.ATTRS) if (a.deComp) SECCION[a.id] = 'composicion'
for (const a of M.ATTRS) if (a.soloNac) SECCION[a.id] = 'nacional'

// ---- 4. Detección por texto (antes en detectar/detectarNac) -------------------------
// Cada patrón: re (expresión sobre el texto normalizado), en (estilo: nombre y
// estilo; todo: además la composición; tallas; uso; comp.suela), y (también
// debe aparecer), no (no debe aparecer), prioridad (gana la menor), defecto
// (si nada más coincide), cuando (condiciones sobre lo ya detectado).
const P = (re, extra = {}) => ({ re: re.source, ...extra })
const LEATHER = /\b(leather|cuero)\b/, SYNTH = /\b(sintetic[oa]|synthetic|faux|vegan)\b/
const DET = {
  genero: { F: [P(/^(w|wm|wmn|wmns|f)\b/, { prioridad: 1 }), P(/\b(womens?|mujer(es)?|damas?|ladies|girls?|nina|ninas|female|femenino)\b/, { prioridad: 2 })],
    M: [P(/^(m|mn|mns)\b/, { prioridad: 3 }), P(/\b(mens?|hombres?|caballeros?|boys?|nino|ninos|male|masculino)\b/, { prioridad: 4 })],
    U: [P(/^(u|ua|uy)\b/, { prioridad: 5 }), P(/\b(unisex)\b/, { prioridad: 6 })] },
  edadNac: { bebe: [P(/\b(bebes?|baby|infante|infant|toddler|primera infancia)\b/, { prioridad: 1, en: 'uso' }), P(/\b(baby|bebe|infant|newborn|recien nacido|onesies?|mameluco|panalero)\b/, { prioridad: 4 }),
    P(/\b(nb|newborn|recien nacido|\d{1,2}\s*-\s*\d{1,2}\s*(m|meses)|\d{1,2}\s*(m|meses)|0-3|3-6|6-9|6-12|12-18|18-24)\b/, { prioridad: 6, en: 'tallas' })],
  nino: [P(/\b(ninos?|ninas?|kids?|youth|boys?|girls?|juvenil|infantil|escolar)\b/, { prioridad: 2, en: 'uso' }), P(/\b(kids?|youth|junior|jr|nino|nina|ninos|ninas|infantil|toddler|td|ps|gs|boys?|girls?|juvenil)\b/, { prioridad: 5 }),
    P(/\b([2-7]t|youth|kids|junior|jr|\d{1,2}\s*(y|yrs|anos)|toddler|xs\/s kids)\b/, { prioridad: 7, en: 'tallas' })],
  adulto: [P(/\b(hombres?|mujer(es)?|damas?|caballeros?|mens?|womens?|ladies|adultos?)\b/, { prioridad: 3, en: 'uso' })] },
  tejido: { punto: [P(/\b(fleece|polar|denali|glacier|knit|knitted|punto|jersey|pique|terry|waffle|polos?|hoodies?|sweatshirts?|leggings?|onesies?)\b/, { en: 'todo', prioridad: 1 })],
    plano: [P(/\b(board ?shorts?|boardshorts|swim trunks|woven|plano|denim|jeans?|flannel|franela|poplin|popelina|canvas|lona|ripstop|twill|sarga|taslan|oxford|chambray|corduroy|pana|puffer|down|nuptse|thermoball|insulated|parkas?|anoraks?|windbreakers?|rompevientos|cargo|chinos?|coveralls?|boiler ?suit)\b/, { en: 'todo', prioridad: 2 })] },
  relleno_tipo: { plumon: [P(/\b(down|plumon|pluma|goose|duck|700 fill|600 fill|550 fill)\b/, { en: 'todo', prioridad: 1 })],
    sintetico: [P(/\b(thermoball|primaloft|heatseeker|synthetic insulation|relleno sintetico|insulated)\b/, { en: 'todo', prioridad: 2 })] },
  hechura: { reflectivo: [P(/\b(reflectiv[oa]|hi-?vis|alta visibilidad|safety vest|chaleco de seguridad)\b/, { prioridad: 1 })],
    blazer: [P(/\b(blazers?|sport ?coat|saco de vestir|americana)\b/, { prioridad: 2 })],
    chaleco_relleno: [P(/\b(vests?|chalecos?|gilet)\b/, { prioridad: 3, y: [/\b(down|puffer|insulated|acolchad[oa]|relleno|thermoball|nuptse|padded|plumon)\b/.source], y_en: 'todo' })],
    chaleco: [P(/\b(vests?|chalecos?|gilet)\b/, { prioridad: 4, y: [/\b(fleece|polar|knit|softshell)\b/.source], y_en: 'todo' })],
    chaqueta: [{ defecto: true, no: [/\b(vests?|chalecos?|gilet)\b/.source], prioridad: 9 }] },
  hechuraSud: { cierre: [P(/\b(full ?zip|fz|cierre completo|zip ?up|zip hoodie)\b/, { prioridad: 1 })], pullover: [P(/\b(pullover|po|crew|crewneck|1\/4 ?zip|quarter ?zip|half ?zip)\b/, { prioridad: 2 })] },
  prendaInt: { bata: [P(/\b(robes?|bata|albornoz|bathrobe)\b/, { prioridad: 1 })], pijama: [P(/\b(pajamas?|pyjamas?|pijamas?|sleepwear|camison|nightgown)\b/, { prioridad: 2 })],
    camiseta_int: [P(/\b(undershirt|camiseta interior)\b/, { prioridad: 3 })], interior: [{ defecto: true, prioridad: 9 }] },
  tipoBufanda: { bandana: [P(/\b(bandanas?|panuelos?|handkerchief)\b/, { prioridad: 1 })], bufanda: [{ defecto: true, prioridad: 9 }] },
  estiloCalz: Object.fromEntries(Object.entries(M.DET_ESTILO.reduce((o, [st, re], i) => { (o[st] ||= []).push(P(re, { prioridad: i + 1 })); return o }, { tenis: [{ defecto: true, prioridad: 99 }] }))),
  altura: { tobillo: [P(/\b(hi|high|high-?top|mid|boots?|botas?|botin(es)?|chukka|mte)\b/, { prioridad: 1 })] },
  disenio: { entrenamiento: [P(/\b(running|run|trail|training|trainers?|basketball|baloncesto|gym|gimnasia|entrenamiento|vectiv|deportivo)\b/, { prioridad: 1 })],
    skate: [P(/\b(skate|pro|skateboarding)\b/, { prioridad: 2 })], casual: [{ defecto: true, prioridad: 9, cuando: [{ campo: 'estiloCalz', operador: 'IN', valor: ['tenis', ''] }] }] },
  puntera: { metalica: [P(/\b(steel toe|punta de acero|acero|aluminum toe|alloy toe|puntera metalica)\b/, { prioridad: 1 })],
    no_metalica: [P(/\b(composite|nano toe|carbon toe|punta de composite)\b/, { prioridad: 2 })] },
  upper: { cuero: [P(/\b(leather|cuero|suede|gamuza|nubuck|piel|charol)\b/, { en: 'todo', prioridad: 1, no: [SYNTH.source, /\b(canvas|lona|mesh|malla|knit|textile|textil|nylon|ripstop|corduroy|pana|poliester|polyester)\b/.source] })],
    textil: [P(/\b(canvas|lona|mesh|malla|knit|textile|textil|nylon|ripstop|corduroy|pana|poliester|polyester)\b/, { en: 'todo', prioridad: 2, no: [/\b(leather|cuero|suede|gamuza|nubuck|piel|charol)\b/.source] }),
      P(/\b(canvas|lona|mesh|malla|knit|textile|textil|nylon|ripstop|corduroy|pana|poliester|polyester)\b/, { en: 'todo', prioridad: 3, y: [SYNTH.source] })],
    plastico: [P(/\b(pvc|eva|rubber upper|plastic|plastico|hule|sintetic[oa]|synthetic|faux leather|pu leather)\b/, { en: 'todo', prioridad: 4 })] },
  sole: { cuero: [P(/\b(leather sole|suela de cuero)\b/, { en: 'todo', prioridad: 1 })] },
  exterior: { cuero: [P(LEATHER, { en: 'todo', prioridad: 1, no: [SYNTH.source] })], textil: [P(/\b(nylon|polyester|poliester|canvas|lona|textil|textile|ripstop|cordura)\b/, { en: 'todo', prioridad: 2 })],
    plastico: [P(/\b(pvc|tpu|plastic|plastico)\b/, { en: 'todo', prioridad: 3 })] },
  materialCinturon: { cuero: [P(LEATHER, { en: 'todo', prioridad: 1, no: [/\b(sintetic|synthetic|faux)\b/.source] })],
    textil: [P(/\b(web|webbing|canvas|lona|nylon|poliester|polyester|textil|elastic|elastico|tejido)\b/, { en: 'todo', prioridad: 2 })],
    plastico: [P(/\b(pu|pvc|plastic|plastico|sintetic[oa]|synthetic)\b/, { en: 'todo', prioridad: 3 })] },
  materialGorra: { paja: [P(/\b(straw|paja|palma)\b/, { en: 'todo', prioridad: 1 })] },
  materialBotella: { acero: [P(/\b(stainless|acero)\b/, { en: 'todo', prioridad: 1 })], aluminio: [P(/\b(aluminio|aluminum)\b/, { en: 'todo', prioridad: 2 })],
    plastico: [P(/\b(plastic|plastico|tritan|bpa)\b/, { en: 'todo', prioridad: 3 })] },
  tipoAvio: { cremallera: [P(/\b(zippers?|cremalleras?|zipper pulls?)\b/, { prioridad: 1 })], hebilla: [P(/\b(hebillas?|buckles?)\b/, { prioridad: 2 })],
    ojete: [P(/\b(ojetes?|eyelets?)\b/, { prioridad: 3 })], remache: [P(/\b(remaches?|rivets?)\b/, { prioridad: 4 })], boton: [P(/\b(botones|buttons?|snaps?|broches?)\b/, { prioridad: 5 })] },
  tipoPelo: { liga: [P(/\b(scrunchies?|hair ?ties?|ligas?)\b/, { prioridad: 1 }), P(/\b(headbands?|diademas?|bandas?)\b/, { prioridad: 2, no: [/\b(plastic|plastico|metal|rigid|rigida)\b/.source] })],
    horquilla: [P(/\b(horquillas?|bobby pins?)\b/, { prioridad: 3 })], pasador: [{ defecto: true, prioridad: 9 }] },
  pelNat: { artificial: [P(/\b(faux|sintetic|artificial|peluche)\b/, { prioridad: 1 })] },
  producto: { spray: [P(/\b(spray|protector|impermeabilizante|repelente)\b/, { prioridad: 1 })], cepillo: [P(/\b(cepillo|brush)\b/, { prioridad: 2 })], crema: [{ defecto: true, prioridad: 9 }] },
  materialLlavero: { textil: [P(/\b(lanyards?|webbing|cinta|textil|nylon|poliester|polyester)\b/, { en: 'todo', prioridad: 1 })], cuero: [P(LEATHER, { en: 'todo', prioridad: 2 })],
    metal: [P(/\b(metal|metalic[oa]|zinc|acero|steel|aluminio|aluminum|bronce|brass)\b/, { en: 'todo', prioridad: 3 })], plastico: [P(/\b(pvc|plastic|plastico|silicona|silicone|caucho|rubber)\b/, { en: 'todo', prioridad: 4 })] },
  pantalla: { inteligente: [P(/\b(smart|inteligente|gps|bluetooth)\b/, { prioridad: 1 })], combinado: [P(/\b(ana-?digi|anadigi|analogico digital|combinado)\b/, { prioridad: 2 })],
    digital: [P(/\b(digital)\b/, { prioridad: 3 })], analogico: [P(/\b(analog|analogico|agujas)\b/, { prioridad: 4 })] },
  actividad: { escalada: [P(/\b(crash ?pads?|boulder)/, { prioridad: 1 })], fitness: [P(/\b(yoga|resistance|resistencia|ligas|jump|saltar|fitness|gym)\b/, { prioridad: 2 })],
    protecciones: [P(/\b(knee|rodilleras?|coderas?|elbow|wrist|munequeras?|pads?)\b/, { prioridad: 3 })], pelota: [P(/\b(pelotas?|balon(es)?|balls?)\b/, { prioridad: 4 })] },
  tipoColch: { espuma: [P(/\b(self-?inflating|autoinflable|foam|espuma)\b/, { prioridad: 1 })], inflable: [P(/\b(inflatable|inflable|air)\b/, { prioridad: 2 })],
    almohada: [P(/\b(pillows?|almohadas?|cojin(es)?|cushions?)\b/, { prioridad: 3 })] },
  mueble: { mesa: [P(/\b(tables?|mesas?)\b/, { prioridad: 1 })], silla: [{ defecto: true, prioridad: 9 }] },
  tipoParche: { sticker: [P(/\b(stickers?|calcomanias?|decals?)\b/, { prioridad: 1 })], bordado: [P(/\b(embroider|bordad)/, { prioridad: 2 })], tejido: [P(/\b(woven|tejid)/, { prioridad: 3 })],
    pvc: [P(/\b(pvc|rubber|goma)\b/, { prioridad: 4 })] },
  materialBisu: { cuero: [P(LEATHER, { en: 'todo', prioridad: 1 })], textil: [P(/\b(cord|cordon|hilo|textil|woven|tejid)/, { en: 'todo', prioridad: 2 })],
    metal: [P(/\b(metal|acero|steel|brass|laton|zinc|enamel|esmalte)/, { en: 'todo', prioridad: 3 })] },
  materialBolsa: { papel: [P(/\b(paper|papel|kraft)\b/, { en: 'todo', prioridad: 1 })], plastico: [P(/\b(plastic|plastico|polietileno|pe|ldpe|hdpe)\b/, { en: 'todo', prioridad: 2 })],
    tela: [P(/\b(reutilizable|reusable|tela|non ?woven|no tejid|canvas|lona|algodon|cotton)/, { en: 'todo', prioridad: 3 })] },
  materialCaja: { corrugado: [P(/\b(corrugad|corrugated)/, { en: 'todo', prioridad: 1 })], plegadizo: [P(/\b(shoe ?box|zapatos|calzado|cartulina|folding)/, { en: 'todo', prioridad: 2 })],
    plastico: [P(/\b(plastic|plastico)\b/, { en: 'todo', prioridad: 3 })] },
  materialGancho: { madera: [P(/\b(wood|madera)\b/, { en: 'todo', prioridad: 1 })], metal: [P(/\b(wire|alambre|metal)\b/, { en: 'todo', prioridad: 2 })], plastico: [P(/\b(plastic|plastico)\b/, { en: 'todo', prioridad: 3 })] },
  materialEtiqueta: { tejida: [P(/\b(woven|tejid)/, { en: 'todo', prioridad: 1 })], papel: [P(/\b(hang ?tags?|papel|paper|carton|price)/, { en: 'todo', prioridad: 2 })],
    plastico: [P(/\b(pvc|plastic|plastico)\b/, { en: 'todo', prioridad: 3 })] },
  tipoExhib: { maniqui: [P(/\b(mannequins?|maniqui(es)?|bustos?)\b/, { prioridad: 1 })], mueble: [{ defecto: true, prioridad: 9 }] },
  materialMueble: { metal: [P(/\b(metal|steel|acero)\b/, { en: 'todo', prioridad: 1 })], madera: [P(/\b(wood|madera|mdf)\b/, { en: 'todo', prioridad: 2 })],
    plastico: [P(/\b(acrylic|acrilico|plastic|plastico)\b/, { en: 'todo', prioridad: 3 })] },
  presentacion: { liquido: [P(/\b(liquid|liquido)\b/, { prioridad: 1 })], polvo: [{ defecto: true, prioridad: 9 }] },
  parteSkate: { completa: [P(/\b(complete|completa)\b/, { prioridad: 1 })], tabla: [P(/\b(deck|tabla)\b/, { prioridad: 2 })], partes: [P(/\b(wheels?|ruedas|trucks?|bearings?|rodamientos)\b/, { prioridad: 3 })] },
  // Datos que piden los aranceles nacionales (detectarNac)
  usoPrevisto: { escolar: [P(/\b(escolar|school|uniforme)\b/, { en: 'uso', prioridad: 1 })], trabajo: [P(/\b(work|trabajo|industrial|safety|seguridad)\b/, { en: 'uso', prioridad: 2 })] },
  largo: { corto: [P(/\b(shorts?|bermudas?|short)\b/, { en: 'uso', prioridad: 1 })], largo: [P(/\b(pants?|pantalon(es)?|jeans?|joggers?|trousers?|leggings?|chinos?)\b/, { en: 'uso', prioridad: 2 })] },
  formaTocado: { sombrero: [P(/\b(hats?|sombrero|bucket|boonie|fedora|panama|sun hat)\b/, { en: 'uso', prioridad: 1 })], gorro: [P(/\b(beanie|gorro|toque|knit cap)\b/, { en: 'uso', prioridad: 2 })],
    gorra: [P(/\b(caps?|gorra|trucker|snapback|visera)\b/, { en: 'uso', prioridad: 3 })] },
  claseBolso: Object.fromEntries([['cangurera', /\b(cangurera|rinonera|fanny|waist ?pack|belt bag|hip pack|bum bag)\b/], ['termico', /\b(termic[oa]|cooler|lonchera|lunch|insulated)\b/],
    ['duffel', /\b(duffel|duffle|bolso de viaje|travel bag|weekender)\b/], ['deporte', /\b(deporte|gym bag|sports? bag|bolsa para articulos de deporte)\b/], ['neceser', /\b(neceser|toiletry|dopp|cosmetic bag)\b/],
    ['crossbody', /\b(crossbody|cross body|bandolera)\b/], ['tote', /\b(tote)\b/], ['satchel', /\b(satchel)\b/], ['bolso_mano', /\b(bolso de mano|handbag)\b/], ['cartera', /\b(cartera|clutch|purse)\b/],
    ['mochila', /\b(mochila|backpack|daypack|rucksack|morral|sling)\b/]].map(([k, re], i) => [k, [P(re, { en: 'uso', prioridad: i + 1 }), ...(k === 'mochila' ? [{ defecto: true, prioridad: 99, cuando: [{ campo: 'categoria', operador: 'EQUAL', valor: 'mochila' }] }] : [])]])),
}
const DET_CHECK = {
  recubierta: [P(/\b(dryvent|dry vent|gore-?tex|futurelight|waterproof|laminad[oa]s?|laminated|pu coated|coated|recubiert[oa]s?|hyvent|hardshell|rain ?jacket|rain ?shell)\b/, { en: 'todo' })],
  polo: [P(/\b(polo|henley con cuello)\b/)], rodeaDedo: [P(/\b(toe ?loop|toe ?post|rodea el dedo|entre dedo|thong)\b/)], casco: [P(/\b(helmet|casco)\b/)],
  alVacio: [P(/\b(vacuum|al vacio|termo|thermos|insulated|termico)\b/, { en: 'todo' })], telescopica: [P(/\b(telescopic|telescopica|plegable|compact|folding)\b/)],
  esBase: [P(/\b(footprint|base de tienda|base para tienda)\b/)], baseAncha: [P(/\b(base (superior|mayor) a 40|40 ?cm)\b/)], kitViaje: [P(/\b(kit|set|juego|travel|estuche)\b/)],
  acolchada: [P(/\b(padded|acolchad[oa]|cushion|relleno)\b/)], rizo: [P(/\b(terry|rizo|felpa)\b/, { en: 'todo' })],
  mezclilla: [P(/\b(denim|jeans?|mezclilla)\b/, { en: 'uso_comp' })], peto: [P(/\b(overall|overol|bib)\b/, { en: 'uso' })],
  suelaEspumosa: [P(/\b(eva|phylon|md|foam|espuma|espumos)/, { en: 'comp.suela' })], capucha: [P(/\b(hood|hooded|hoodie|capucha)\b/, { en: 'uso' })],
  sueter: [P(/\b(sweaters?|sueter(es)?|jerseys?|cardigans?|knit sweater)\b/, { en: 'uso' })], conCuello: [P(/\b(polo|collar|cuello)\b/, { en: 'uso' })],
}
// Falsos explícitos de los datos nacionales (detectarNac)
const DET_FALSO = {
  suelaEspumosa: [P(/\b(caucho|rubber|goma|cuero|leather|tpr|tpu|pvc)\b/, { en: 'comp.suela' })],
  sueter: [P(/\b(hoodie|sudadera|sweatshirt|crew|fleece|pullover|pulover)\b/, { en: 'uso' })],
}

// ---- 5. Atributos nacionales (NAC_PREG) ----------------------------------------
const NAC = M.NAC_PREG.filter((q) => q.tipo !== 'attr' && q.id !== 'edadNac' && !M.ATTR_BY[q.id]).map((q) => ({
  codigo: q.id, etiqueta: q.label, tipo_dato: q.tipo === 'num' ? 'number' : q.tipo === 'sino' ? 'boolean' : 'select', seccion: 'nacional', unidad: q.tipo === 'num' ? 'USD' : null,
  opciones: (q.ops || []).map(([v, l], i) => ({ codigo: v, etiqueta: l, orden: (i + 1) * 10, patrones: DET[q.id]?.[v] || [] })),
  patrones: DET_CHECK[q.id] || [], patrones_falso: DET_FALSO[q.id] || [],
}))
const EDAD_NAC = {
  codigo: 'edadNac', etiqueta: 'Who it is for', tipo_dato: 'select', seccion: 'producto',
  opciones: [['adulto', 'Adult'], ['nino', 'Child or youth'], ['bebe', 'Baby (up to 86 cm tall)']].map(([v, l], i) => ({ codigo: v, etiqueta: l, orden: (i + 1) * 10, patrones: DET.edadNac[v] || [],
    bloqueo: v === 'bebe' ? [{ condiciones: [{ grupo: 1, campo: 'categoria', operador: 'EQUAL', valor: 'calzado' }, { grupo: 1, campo: 'estiloCalz', operador: 'IN', valor: ['seguridad', 'tacon', 'tacos', 'esqui'] }], mensaje: 'Does not apply to this product' },
      { condiciones: [{ grupo: 1, campo: 'categoria', operador: 'EQUAL', valor: 'brasier' }], mensaje: 'Does not apply to this product' },
      { condiciones: [{ grupo: 1, campo: 'categoria', operador: 'EQUAL', valor: 'chaqueta' }, { grupo: 1, campo: 'hechura', operador: 'IN', valor: ['blazer', 'reflectivo'] }], mensaje: 'Does not apply to this product' }]
      : v === 'nino' ? [{ condiciones: [{ grupo: 1, campo: 'categoria', operador: 'EQUAL', valor: 'calzado' }, { grupo: 1, campo: 'estiloCalz', operador: 'IN', valor: ['seguridad', 'tacon', 'tacos', 'esqui'] }], mensaje: 'Does not apply to this product' }] : [] })),
}
const GRUPOS_PERSONA = TIPOS.filter((t) => ['prenda', 'calzado', 'gorra'].includes(M.grupoTipo(t)))

// ---- 6. Armado -------------------------------------------------------------------------
const FIBRAS = Object.entries(M.FIB_LBL).map(([v, l], i) => ({ codigo: v, etiqueta: l, orden: (i + 1) * 10 }))
const MATS = ['textil', 'cuero', 'plastico', 'otro'].map((v, i) => ({ codigo: v, etiqueta: M.MAT_LBL[v], orden: (i + 1) * 10 }))
const atributos = []
for (const a of M.ATTRS) {
  const seccion = SECCION[a.id] || 'caracteristicas'
  const amb = (ambitos[a.id] || []).map((x) => ({ ...x, modo: 'SHOW' }))
  if (a.id === 'genero') { amb.length = 0; GRUPOS_PERSONA.forEach((t) => amb.push({ tipo_ambito: 'CATEGORY', codigo_ambito: t, condicion: null, modo: 'REQUIRE' })) }
  atributos.push({
    codigo: a.id, etiqueta: a.label, tipo_dato: a.tipo === 'check' ? 'boolean' : 'select', seccion, ayuda: a.ayuda || null, informativo: !!a.info,
    valor_defecto: a.tipo === 'check' ? 'false' : null, derivacion: DERIVACION[a.id] || null, bloqueo: bloqueoCheck[a.id] || null,
    patrones: DET_CHECK[a.id] || [], control: a.tipo === 'select' ? 'lista' : null,
    opciones: (a.ops || []).map((o, i) => ({ codigo: o.v, etiqueta: o.l, orden: (i + 1) * 10, bloqueo: bloqueoOpcion[`${a.id}.${o.v}`] || [],
      implica: a.implica?.[o.v] || null, patrones: DET[a.id]?.[o.v] || [] })),
    ambitos: amb,
  })
}
atributos.push({ ...EDAD_NAC, ambitos: TIPOS.filter((t) => M.grupoTipo(t) === 'prenda' || ['calzado', 'gorra'].includes(M.grupoTipo(t)) || true).map((t) => ({ tipo_ambito: 'CATEGORY', codigo_ambito: t, condicion: null, modo: 'REQUIRE' })) })
// Hechos derivados de la composición (no se preguntan: se muestran como definidos)
atributos.push({ codigo: 'fibra', etiqueta: 'Predominant fiber of the outer fabric', tipo_dato: 'select', seccion: 'derivado', opciones: FIBRAS,
  derivacion: { modo: 'fibra', parte: 'exterior', respaldo: RESPALDO }, ambitos: [{ tipo_ambito: 'SYSTEM', codigo_ambito: 'ALL', condicion: null, modo: 'SHOW' }] })
atributos.push({ codigo: 'material_corte', etiqueta: 'Outer material (non-textile)', tipo_dato: 'select', seccion: 'derivado', opciones: MATS,
  derivacion: { modo: 'material', parte: 'exterior', lectura: 'corte', respaldo: RESPALDO, cuando: [{ campo: 'fibra', operador: 'IN', valor: ['otra', ''] }] },
  ambitos: TIPOS.filter((t) => M.grupoTipo(t) === 'prenda').map((t) => ({ tipo_ambito: 'CATEGORY', codigo_ambito: t, condicion: null, modo: 'SHOW' })) })
atributos.push({ codigo: 'corte_material', etiqueta: 'Upper material from the composition', tipo_dato: 'select', seccion: 'derivado', opciones: MATS,
  derivacion: { modo: 'material', parte: 'corte', lectura: 'corte' }, ambitos: [{ tipo_ambito: 'CATEGORY', codigo_ambito: 'calzado', condicion: null, modo: 'SHOW' }] })
// Partes de la composición
for (const p of PARTES) {
  atributos.push({ codigo: `comp.${p}`, etiqueta: M.PARTE_LBL[p], tipo_dato: 'composition', seccion: 'composicion', ayuda: M.PARTE_PH?.[p] || null,
    ambitos: ambitos[`comp.${p}`] || [] })
}
NAC.forEach((x) => atributos.push({ ...x, ambitos: [] }))

// Orden de la ficha: como en motor.js
atributos.forEach((a, i) => { a.orden = (i + 1) * 10 })

// Categorías: nombres, encabezados, alias, patrones de detección, capítulos compatibles
const patronesTipo = {}
M.DET_TIPO.forEach(([t, re], i) => (patronesTipo[t] ||= []).push({ re: re.source, prioridad: i + 1 }))
const categorias = []
M.TIPOS.forEach(([grupo, ts], gi) => ts.forEach(([k, l], ti) => categorias.push({
  codigo: k, nombre: l, nombre_corto: M.TIPO_CORTO[k], nombre_aduana: M.TIPO_CORTO_ES[k], grupo, familia: M.grupoTipo(k) || null, orden: gi * 100 + ti,
  alias: (M.TIPO_ALIAS[k] || '').trim() || null, patrones: patronesTipo[k] || [], capitulos: M.CAP_OK[k] || M.CAP_OK[M.grupoTipo(k)] || [],
})))

// Detecciones que motor.js limitaba a una categoría, e implicaciones que hacía en código
const BOLSOS_ = ['mochila', 'bolso_viaje', 'bolso_mano', 'maleta', 'billetera']
const enCat = (...c) => [{ campo: 'categoria', operador: 'IN', valor: c }]
const SOLO = { suelaEspumosa: enCat('calzado'), claseBolso: enCat(...BOLSOS_), largo: enCat('pantalon'), peto: enCat('pantalon'), formaTocado: enCat('gorra'),
  sueter: enCat('sudadera'), parteSkate: enCat('patineta'), materialMueble: [...enCat('exhibidor'), { campo: 'tipoExhib', operador: 'IN', valor: ['mueble', ''] }] }
for (const a of atributos) {
  const pats = [...(a.opciones || []).flatMap((o) => o.patrones || []), ...(a.patrones || []), ...(a.patrones_falso || [])]
  if (SOLO[a.codigo]) pats.forEach((p) => { p.cuando = [...(p.cuando || []), ...SOLO[a.codigo]] })
  if (a.codigo === 'tipoBufanda') a.opciones.find((o) => o.codigo === 'bandana').implica = { tejido: 'plano' }
  if (a.codigo === 'edadNac') a.opciones.find((o) => o.codigo === 'adulto').patrones.push({ prioridad: 3, cuando: [...enCat('calzado'), { campo: 'estiloCalz', operador: 'IN', valor: ['seguridad', 'tacon'] }] })
}
const salida = { origen: 'frontend/src/clasificacion/motor.js (ATTRS, partesDe, detectar, DET_TIPO, CAP_OK)', categorias, atributos }
writeFileSync(new URL('../../backend/app/data/motor_atributos.json', import.meta.url), JSON.stringify(salida, null, 1) + '\n')
console.log(categorias.length, 'categorías,', atributos.length, 'atributos,', Object.values(ambitos).flat().length, 'ámbitos,',
  Object.values(bloqueoOpcion).flat().length + Object.values(bloqueoCheck).flat().length, 'bloqueos')

// ---- 7. Casos de paridad del normalizador y de las preguntas --------------------------------
semilla = 99
const casos = []
for (let i = 0; i < 1500; i++) {
  const t = uno(TIPOS)
  const f = ficha(t, alAzar())
  // En la ficha «edad» sale de «¿para quién es?» (edadNac)
  if (f.edadNac) f.edad = f.edadNac === 'bebe' ? 'bebe' : 'general'
  else delete f.edad
  if (azar() < 0.3) f.comp.material = uno(['100% leather', '100% stainless steel', '100% aluminum', '100% plastic', 'corrugated cardboard', 'card stock', '100% wood', '100% polyester', 'straw'])
  if (azar() < 0.3) f.comp.suela = uno(['100% rubber', '100% leather', '100% cork', 'EVA'])
  const entrada = JSON.parse(JSON.stringify(f))
  const s = { ...f, comp: { ...f.comp } }
  const avisos = M.normalizar(s)
  const valores = {}
  for (const a of M.ATTRS) valores[a.id] = a.tipo === 'check' ? !!s[a.id] : (s[a.id] || '')
  const estados = {}
  for (const a of M.ATTRS) {
    const e = M.estadoAttr(a, s)
    if (e === 'oculto') continue
    estados[a.id] = { estado: e, opciones: a.tipo === 'check' ? null : M.opcionesValidas(a, s).map((o) => o.v) }
  }
  casos.push({ entrada, valores, avisos, estados, partes: M.partesDe(t, s) })
}
writeFileSync(new URL('../../backend/tests/paridad/atributos.json', import.meta.url), JSON.stringify({ casos }) + '\n')
console.log(casos.length, 'casos de paridad del normalizador')
