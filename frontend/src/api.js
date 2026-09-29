const BASE = '/api'
let alNoAutorizado = null

export function manejarNoAutorizado(fn) {
  alNoAutorizado = fn
}

export class ApiError extends Error {
  constructor(status, cuerpo) {
    super(cuerpo?.mensaje || `Error ${status}`)
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

async function pedir(metodo, url, cuerpo, { params, clave } = {}) {
  const headers = {}
  const token = localStorage.getItem('token')
  if (token) headers.Authorization = `Bearer ${token}`
  let body
  if (cuerpo instanceof FormData) body = cuerpo
  else if (cuerpo !== undefined) {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify(cuerpo)
  }
  // Cada operación que modifica datos lleva su clave: si la red la repite,
  // el servidor devuelve el mismo resultado en vez de duplicarla.
  if (metodo !== 'GET') headers['Idempotency-Key'] = clave || nuevaClave()
  let r
  try {
    r = await fetch(BASE + url + qs(params), { method: metodo, headers, body })
  } catch {
    throw new ApiError(0, { mensaje: 'No hay conexión con el servidor. Revisa tu red e intenta de nuevo.' })
  }
  const datos = await r.json().catch(() => null)
  if (r.status === 401 && url !== '/auth/login' && alNoAutorizado) alNoAutorizado()
  if (!r.ok) throw new ApiError(r.status, datos)
  return datos
}

export const api = {
  get: (url, params) => pedir('GET', url, undefined, { params }),
  post: (url, cuerpo, opciones) => pedir('POST', url, cuerpo ?? {}, opciones),
  patch: (url, cuerpo, opciones) => pedir('PATCH', url, cuerpo ?? {}, opciones),
  put: (url, cuerpo, opciones) => pedir('PUT', url, cuerpo ?? {}, opciones),
  del: (url) => pedir('DELETE', url),
  async descargar(url, nombre, params) {
    const q = params ? new URLSearchParams(Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== '')).toString() : ''
    const r = await fetch(BASE + url + (q ? `?${q}` : ''), { headers: { Authorization: `Bearer ${localStorage.getItem('token')}` } })
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
