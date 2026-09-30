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
    const porEstilo = new Map()
    const porGenerico = new Map()
    for (const r of c.recs) {
      const k = M.norm(r.estilo).trim()
      if (k) porEstilo.set(k, [...(porEstilo.get(k) || []), r])
      const g = M.norm(r.generico).trim()
      if (g) porGenerico.set(g, [...(porGenerico.get(g) || []), r])
    }
    const destinos = c.destinos.map((d) => ({ iso: d.iso, nombre: d.nombre, digitos: d.digitos }))
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
  return { s, o, partidas, completa: fe.completa, faltan: fe.faltan, desc, avisosNorm }
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

// Clasifica varios productos (lista) sin abrir cada uno
export async function clasificarVarios(ids) {
  const ctx = await cargarContexto()
  const items = []
  for (const id of ids) {
    const p = await api.get(`/productos/${id}`)
    if (['aprobado', 'corregido'].includes(p.estado)) continue
    items.push({ id, resultado: resultadoServidor(calcular(fichaDe(p), ctx)) })
  }
  if (!items.length) return { clasificados: 0, omitidos: [] }
  return api.post('/productos/clasificar', { items })
}

export { M }
