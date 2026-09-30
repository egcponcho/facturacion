/* Puente entre el motor de clasificación (lógica pura en el navegador) y el
servidor: carga el contexto una vez (historial, códigos nacionales, lo
aprendido), arma la ficha que el motor entiende a partir del producto y
devuelve el resultado en el formato que guarda el servidor. */
import { reactive } from 'vue'
import { api } from '../api'
import * as M from './motor'

const estado = reactive({ ctx: null, cargando: null })

export async function cargarContexto(forzar = false) {
  if (estado.ctx && !forzar) return estado.ctx
  if (estado.cargando && !forzar) return estado.cargando
  estado.cargando = api.get('/clasificacion/contexto').then((c) => {
    M.setSinonimos(c.sinonimos || [])
    M.setSac(c.sac || [])
    const porEstilo = new Map()
    const porGenerico = new Map()
    for (const r of c.recs) {
      const k = M.norm(r.estilo).trim()
      if (k) porEstilo.set(k, [...(porEstilo.get(k) || []), r])
      const g = M.norm(r.generico).trim()
      if (g) porGenerico.set(g, [...(porGenerico.get(g) || []), r])
    }
    const destinos = c.destinos.map((d) => ({ iso: d.iso, nombre: d.nombre, digitos: d.digitos, mcca: d.mcca }))
    estado.ctx = {
      ...c,
      destinos,
      base: M.incisosBase(c.incisos, c.pais_base, destinos),
      validar: { marcas: c.marcas, proveedores: c.proveedores, palabras: c.palabras, porEstilo, porGenerico },
    }
    estado.cargando = null
    return estado.ctx
  })
  return estado.cargando
}

export const contexto = estado

// Producto del servidor -> ficha del motor
export function fichaDe(p) {
  const f = JSON.parse(JSON.stringify(p.ficha || {}))
  return {
    ...f,
    comp: f.comp || {},
    id: p.id,
    tipo: p.tipo || '',
    estilo: p.estilo,
    descArchivo: p.nombre || '',
    color: p.color,
    generico: p.codigo_generico,
    marca: p.marca_nombre || p.marca || '',
    proveedor: p.proveedor || '',
    origen: p.pais_origen || '',
    alertasOk: p.alertas_ok || [],
    fotos: p.fotos || [],
    partidas: Object.fromEntries(Object.entries(p.partidas || {}).filter(([, x]) => x.manual).map(([k, x]) => [k, x])),
  }
}

// Campos del motor que no se guardan dentro de la ficha (van en columnas propias)
const FUERA = ['id', 'tipo', 'estilo', 'descArchivo', 'color', 'generico', 'marca', 'proveedor', 'origen', 'alertasOk', 'fotos', 'partidas', '_matGuante']
export function fichaParaGuardar(f) {
  const out = {}
  for (const [k, v] of Object.entries(f)) if (!FUERA.includes(k) && v !== undefined) out[k] = v
  return out
}

// Evalúa la ficha: código sugerido, razones, alertas, códigos por país y si está completa
export function calcular(f, ctx, codFinal) {
  const s = { ...f, comp: { ...(f.comp || {}) } }
  const avisosNorm = M.normalizar(s)
  const o = M.evaluar(s, ctx.recs, ctx.base, ctx.validar, codFinal, f.id)
  const base = codFinal || o.completo || o.codigo
  const partidas = M.digits(base).length >= 6 ? M.partidasDe(s, base, { incisos: ctx.incisos, destinos: ctx.destinos }) : {}
  const fe = M.estadoFicha(s, ctx.obligatorios)
  const desc = s.descManual ? (s.desc || '') : M.descripcionProfesional(s)
  const descCom = s.comManual ? (s.descCom || '') : M.descripcionComercial(s)
  return { s, o, partidas, completa: fe.completa, faltan: fe.faltan, desc, descCom, avisosNorm }
}

// Resultado para el servidor (esquema ResultadoMotor)
export function resultadoServidor(r) {
  const { o } = r
  const partidas = {}
  for (const [iso, x] of Object.entries(r.partidas)) {
    partidas[iso] = { codigo: x.codigo, dai: x.dai, estado: x.estado, fuente: x.fuente, manual: !!x.manual }
  }
  return {
    sugerido: M.digits(o.completo || o.codigo) || null,
    confianza: o.confianza,
    fuente: o.fuente,
    perfil: o.perfil,
    razones: (o.razones || []).slice(0, 30),
    razones_regla: (o.razonesRegla || []).slice(0, 30),
    codigo_regla: o.codigoRegla || null,
    fundamento: o.fundamento ? String(o.fundamento).slice(0, 1000) : null,
    alternativas: (o.alternativas || []).slice(0, 20),
    avisos: (o.avisos || []).slice(0, 20),
    faltantes: (o.faltantes || []).slice(0, 20),
    alertas: (o.alertas || []).slice(0, 60),
    descripcion_aduana: r.desc ? r.desc.slice(0, 400) : null,
    descripcion_comercial: r.descCom ? r.descCom.slice(0, 300) : null,
    completa: r.completa,
    faltan: r.faltan.slice(0, 30),
    partidas,
    tipo_txt: M.TIPO_LBL[r.s.tipo] || null,
    atributos: [
      ...(r.s.genero ? [['Gender', { M: 'Men', F: 'Women', U: 'Unisex' }[r.s.genero] || r.s.genero]] : []),
      ...(M.edadDe(r.s) ? [['Who it is for', { adulto: 'Adult', nino: 'Child or youth', bebe: 'Baby' }[M.edadDe(r.s)]]] : []),
      ...M.atributosLegibles(r.s).filter(([k]) => k !== 'Gender' && k !== 'Who it is for'),
    ].slice(0, 60).map(([k, v]) => [String(k), String(v)]),
  }
}

// Completa lo que no trae la ficha (por ejemplo, de una carga masiva): la
// categoría escrita en el archivo, los atributos que se deducen del nombre,
// el uso y la composición, y los datos de los códigos nacionales.
export function completarFicha(f, ctx) {
  const vacio = (v) => v === undefined || v === null || v === ''
  if (!f.tipo && f._categoria) f.tipo = M.buscarTipos(f._categoria, 1)[0] || ''
  const d = M.detectarFicha({ ...f }, ctx.palabras)
  for (const k of ['tipo', ...M.ATTR_IDS]) if (vacio(f[k]) && !vacio(d[k])) f[k] = d[k]
  M.detectarNac(f, true)
  M.normalizar(f)
  return f
}

// Clasifica varios productos (lista o carga masiva) sin abrir cada uno
export async function clasificarVarios(ids, alAvanzar) {
  const ctx = await cargarContexto()
  const items = []
  let n = 0
  for (const id of ids) {
    const p = await api.get(`/productos/${id}`)
    alAvanzar?.(++n, ids.length)
    if (['aprobado', 'corregido'].includes(p.estado)) continue
    const f = completarFicha(fichaDe(p), ctx)
    const r = calcular(f, ctx)
    items.push({ id, tipo: r.s.tipo || null, ficha: fichaParaGuardar(r.s), resultado: resultadoServidor(r) })
  }
  if (!items.length) return { clasificados: 0, omitidos: [] }
  let total = { clasificados: 0, omitidos: [] }
  for (let i = 0; i < items.length; i += 200) {
    const x = await api.post('/productos/clasificar', { items: items.slice(i, i + 200) })
    total = { clasificados: total.clasificados + x.clasificados, omitidos: [...total.omitidos, ...x.omitidos] }
  }
  return total
}

export { M }
