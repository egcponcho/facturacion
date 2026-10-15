import { t } from '@/i18n/index.js'
const BASE = '/api'
let alNoAutorizado = null

export function manejarNoAutorizado(fn) {
  alNoAutorizado = fn
}

export class ApiError extends Error {
  constructor(status, cuerpo) {
    super(cuerpo?.mensaje || t('Error {0}', [status]))
    this.status = status
    this.codigo = cuerpo?.codigo
    this.detalle = cuerpo?.detalle
  }
}

// crypto.randomUUID solo existe en contextos seguros (https o localhost)
function nuevaClave() {
  if (globalThis.crypto?.randomUUID) return crypto.randomUUID()
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}-${Math.random().toString(36).slice(2)}`
}

function qs(params) {
  if (!params) return ''
  const p = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v !== null && v !== undefined && v !== '') p.append(k, v)
  }
  const s = p.toString()
  return s ? `?${s}` : ''
}

// ---- Datos guardados en la pestaña ----------------------------------------------------------------
// Cada GET de la API se guarda con su ETag y las tablas que lo produjeron
// (encabezados del servidor, backend app/core/cambios.py). Mientras el canal de
// cambios esté abierto y no avise de un cambio en esas tablas, el dato
// guardado se usa sin pedirlo (cero peticiones). Si no, se pide con
// If-None-Match: el servidor responde 304 sin consultar cuando nada cambió.
// Cada lectura entrega una copia nueva: quien la modifique no altera lo guardado.
const MAX_GUARDADAS = 150
const guardadas = new Map() // url → { etag, texto, tablas: Set, vigente, dia }
const enCurso = new Map() // url → promesa: dos pantallas que piden lo mismo a la vez hacen una sola petición
let canal = false
let generacion = 0 // sube con cada aviso: una respuesta que salió antes de un aviso no se da por vigente
const hoy = () => new Date().toDateString()

export function marcarCanal(abierto) {
  canal = abierto
}
export function invalidarTodo() {
  generacion++
  for (const g of guardadas.values()) g.vigente = false
}
// Deja de dar por vigente lo que leyó estas tablas; devuelve sus URLs
export function invalidar(tablas) {
  const t = new Set(tablas)
  const urls = []
  generacion++
  for (const [url, g] of guardadas) {
    if ([...g.tablas].some((x) => t.has(x))) {
      g.vigente = false
      urls.push(url)
    }
  }
  return urls
}
// Al salir: lo guardado era de esa sesión
export function vaciarGuardadas() {
  generacion++
  guardadas.clear()
}
// URLs guardadas de estas rutas de la API (p. ej. ['/ordenes'])
export const entradasDe = (rutas) => [...guardadas.keys()].filter((u) => rutas.some((r) => u.startsWith(`${BASE}${r}`)))

function guardar(url, etag, texto, tablas, vigente) {
  guardadas.delete(url)
  guardadas.set(url, { etag, texto, tablas: new Set((tablas || '').split(',').filter(Boolean)), vigente: vigente && !!tablas, dia: hoy() })
  if (guardadas.size > MAX_GUARDADAS) guardadas.delete(guardadas.keys().next().value)
}

async function leer(url) {
  const g = guardadas.get(url)
  if (g && g.vigente && g.dia === hoy()) {
    guardadas.delete(url) // la más usada queda al final (se descarta la más vieja)
    guardadas.set(url, g)
    return g.texto
  }
  if (enCurso.has(url)) return enCurso.get(url)
  const promesa = (async () => {
    const gen = generacion
    const headers = { 'X-Requested-With': 'fetch' }
    if (g?.etag) headers['If-None-Match'] = g.etag
    let r
    try {
      r = await fetch(url, { headers, credentials: 'same-origin', cache: 'no-store' })
    } catch {
      throw new ApiError(0, { mensaje: t('No connection to the server. Check your network and try again.') })
    }
    const vigente = canal && gen === generacion
    if (r.status === 304 && g) {
      g.vigente = vigente && g.tablas.size > 0
      g.dia = hoy()
      return g.texto
    }
    const texto = await r.text()
    const datos = (() => {
      try {
        return JSON.parse(texto)
      } catch {
        return null
      }
    })()
    if (r.status === 401 && !url.startsWith(`${BASE}/auth/`) && alNoAutorizado) alNoAutorizado()
    if (!r.ok) {
      guardadas.delete(url)
      throw new ApiError(r.status, datos)
    }
    const etag = r.headers.get('ETag')
    if (etag) guardar(url, etag, texto, r.headers.get('X-Tablas'), vigente)
    else guardadas.delete(url)
    return texto
  })()
  enCurso.set(url, promesa)
  try {
    return await promesa
  } finally {
    enCurso.delete(url)
  }
}

async function pedir(metodo, url, cuerpo, { params, clave } = {}) {
  if (metodo === 'GET') {
    const texto = await leer(BASE + url + qs(params))
    try {
      return JSON.parse(texto)
    } catch {
      return null // sin cuerpo o no es JSON (como antes)
    }
  }
  // La sesión viaja en una cookie httpOnly (JavaScript no la ve). Este
  // encabezado identifica a la aplicación: el servidor rechaza cambios sin él.
  const headers = { 'X-Requested-With': 'fetch' }
  let body
  if (cuerpo instanceof FormData) body = cuerpo
  else if (cuerpo !== undefined) {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify(cuerpo)
  }
  // Cada operación que modifica datos lleva su clave: si la red la repite,
  // el servidor devuelve el mismo resultado en vez de duplicarla.
  headers['Idempotency-Key'] = clave || nuevaClave()
  let r
  try {
    r = await fetch(BASE + url + qs(params), { method: metodo, headers, body, credentials: 'same-origin' })
  } catch {
    throw new ApiError(0, { mensaje: t('No connection to the server. Check your network and try again.') })
  }
  // Un cambio propio: lo guardado se revalida (el aviso del canal llega después)
  invalidarTodo()
  const datos = await r.json().catch(() => null)
  if (r.status === 401 && !url.startsWith('/auth/') && alNoAutorizado) alNoAutorizado()
  if (!r.ok) throw new ApiError(r.status, datos)
  return datos
}

export const api = {
  get: (url, params) => pedir('GET', url, undefined, { params }),
  post: (url, cuerpo, opciones) => pedir('POST', url, cuerpo ?? {}, opciones),
  patch: (url, cuerpo, opciones) => pedir('PATCH', url, cuerpo ?? {}, opciones),
  put: (url, cuerpo, opciones) => pedir('PUT', url, cuerpo ?? {}, opciones),
  del: (url) => pedir('DELETE', url),
  // Descarga un archivo (GET); con `cuerpo`, lo pide por POST (p. ej. un reporte armado en pantalla)
  async descargar(url, nombre, params, cuerpo) {
    const q = params ? new URLSearchParams(Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== '')).toString() : ''
    const r = await fetch(BASE + url + (q ? `?${q}` : ''), cuerpo === undefined
      ? { credentials: 'same-origin', headers: { 'X-Requested-With': 'fetch' } }
      : { method: 'POST', credentials: 'same-origin', body: JSON.stringify(cuerpo),
          headers: { 'X-Requested-With': 'fetch', 'Content-Type': 'application/json', 'Idempotency-Key': nuevaClave() } })
    // Descargar también escribe (cuenta la descarga, registra una reimpresión): lo guardado se revalida
    invalidarTodo()
    if (!r.ok) {
      const datos = await r.json().catch(() => null)
      throw new ApiError(r.status, datos)
    }
    const disposicion = r.headers.get('Content-Disposition') || ''
    const coincide = disposicion.match(/filename="?([^";]+)"?/)
    const blob = await r.blob()
    const enlace = document.createElement('a')
    enlace.href = URL.createObjectURL(blob)
    enlace.download = coincide ? coincide[1] : nombre
    document.body.appendChild(enlace)
    enlace.click()
    enlace.remove()
    setTimeout(() => URL.revokeObjectURL(enlace.href), 2000)
  },
}
