/* La pantalla y el motor único del servidor: el contexto para mostrar
(destinos, categorías, capítulos, notas de apoyo) se carga una vez; cada
cambio de la ficha se manda a /clasificacion/sesion, que devuelve los campos
que aplican, las preguntas, la composición leída, la sugerencia, los códigos
por país y la evidencia. El navegador no clasifica. */
import { reactive } from 'vue'
import { api } from '@/nucleo/api'

const estado = reactive({ ctx: null, cargando: null })

export async function cargarContexto(forzar = false) {
  if (estado.ctx && !forzar) return estado.ctx
  if (estado.cargando && !forzar) return estado.cargando
  estado.cargando = api.get('/clasificacion/contexto').then((c) => {
    estado.ctx = c
    estado.cargando = null
    return c
  })
  return estado.cargando
}

export const contexto = estado

// Lo editable de un producto del servidor
export function fichaDe(p) {
  const ficha = JSON.parse(JSON.stringify(p.ficha || {}))
  ficha.comp = ficha.comp || {}
  return {
    id: p.id,
    tipo: p.tipo || '',
    ficha,
    nombre: p.nombre || '',
    origen: p.pais_origen || '',
    alertasOk: [...(p.alertas_ok || [])],
    // Solo los códigos nacionales escritos a mano viajan: los demás los elige el motor
    partidas: Object.fromEntries(Object.entries(p.partidas || {}).filter(([, x]) => x.manual).map(([k, x]) => [k, { codigo: x.codigo, manual: true }])),
  }
}

// Lo que el motor necesita del producto y de la ficha que se está editando
export function entradaDe(p, f, extra = {}) {
  return {
    categoria: f.tipo || null,
    ficha: f.ficha,
    estilo: p.estilo,
    nombre: f.nombre || '',
    uso: f.ficha.uso || '',
    tallas: f.ficha.tallas || p.rango_tallas || '',
    marca: p.marca_nombre || p.marca || null,
    proveedor: p.proveedor || null,
    origen: f.origen || null,
    generico: p.codigo_generico || null,
    producto_id: p.id,
    alertas_ok: f.alertasOk || [],
    partidas: f.partidas || {},
    ...extra,
  }
}

export function sesion(entrada) {
  return api.post('/clasificacion/sesion', entrada)
}

// Clasifica varios productos (lista o carga masiva) en el servidor, con el mismo motor
export async function clasificarVarios(ids, alAvanzar) {
  let total = { clasificados: 0, omitidos: [] }
  for (let i = 0; i < ids.length; i += 200) {
    const x = await api.post('/productos/clasificar', { ids: ids.slice(i, i + 200) })
    total = { clasificados: total.clasificados + x.clasificados, omitidos: [...total.omitidos, ...x.omitidos] }
    alAvanzar?.(Math.min(i + 200, ids.length), ids.length)
  }
  return total
}
