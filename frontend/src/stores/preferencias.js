import { reactive } from 'vue'

// Preferencias del usuario (perfil): idioma, formatos de fecha, hora y
// números, tema, filas por página y página de inicio. Vienen del servidor al
// iniciar sesión; se recuerdan en el navegador para que la pantalla de acceso
// y el primer dibujo ya salgan con ellas. Por defecto: inglés y MM/DD/YYYY.
export const DEFECTO = {
  idioma: 'en', formato_fecha: 'MM/DD/YYYY', formato_hora: '12', formato_numero: '1,234.56',
  tema: 'sistema', filas: 25, inicio: '/',
}
const CLAVE = 'preferencias'

function leer() {
  try {
    return { ...DEFECTO, ...JSON.parse(localStorage.getItem(CLAVE) || '{}') }
  } catch {
    return { ...DEFECTO }
  }
}

export const pref = reactive(leer())

export function aplicarPreferencias(p) {
  Object.assign(pref, DEFECTO, p || {})
  try {
    localStorage.setItem(CLAVE, JSON.stringify(pref))
  } catch {
    // sin almacenamiento: valen solo para esta visita
  }
}

export const filasDefecto = () => Number(pref.filas) || 25

// ---- Fechas en el formato elegido --------------------------------------------
const MESES = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const dos = (n) => String(n).padStart(2, '0')

// 'YYYY-MM-DD' -> texto en el formato del usuario
export function fechaTexto(iso, formato = pref.formato_fecha) {
  const [a, m, d] = String(iso || '').slice(0, 10).split('-').map(Number)
  if (!a || !m || !d) return iso ? String(iso) : ''
  switch (formato) {
    case 'DD/MM/YYYY': return `${dos(d)}/${dos(m)}/${a}`
    case 'YYYY-MM-DD': return `${a}-${dos(m)}-${dos(d)}`
    case 'DD-MMM-YYYY': return `${dos(d)}-${MESES[m - 1]}-${a}`
    case 'MMM DD, YYYY': return `${MESES[m - 1]} ${dos(d)}, ${a}`
    default: return `${dos(m)}/${dos(d)}/${a}`
  }
}

const valida = (a, m, d) => {
  const f = new Date(Date.UTC(a, m - 1, d))
  return f.getUTCFullYear() === a && f.getUTCMonth() === m - 1 && f.getUTCDate() === d
}

// Texto escrito por el usuario -> 'YYYY-MM-DD' (null si no se entiende)
export function textoAFecha(texto, formato = pref.formato_fecha) {
  const t = String(texto || '').trim()
  if (!t) return ''
  let a, m, d, x
  if ((x = t.match(/^(\d{4})-(\d{1,2})-(\d{1,2})$/))) [a, m, d] = [+x[1], +x[2], +x[3]]
  else if ((x = t.match(/^(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{2,4})$/))) {
    const [p, q, r] = [+x[1], +x[2], +x[3]]
    a = r < 100 ? 2000 + r : r
    ;[d, m] = formato.startsWith('DD') ? [p, q] : [q, p]
  } else if ((x = t.match(/^(\d{1,2})[\s\-]([A-Za-z]{3})[a-z]*[\s\-,]+(\d{4})$/))) {
    d = +x[1]; m = MESES.findIndex((n) => n.toLowerCase() === x[2].toLowerCase()) + 1; a = +x[3]
  } else if ((x = t.match(/^([A-Za-z]{3})[a-z]*\.?\s+(\d{1,2}),?\s+(\d{4})$/))) {
    m = MESES.findIndex((n) => n.toLowerCase() === x[1].toLowerCase()) + 1; d = +x[2]; a = +x[3]
  } else return null
  if (!m || !valida(a, m, d)) return null
  return `${a}-${dos(m)}-${dos(d)}`
}

// ---- Números con los separadores elegidos ---------------------------------
const SEPARADORES = { '1,234.56': [',', '.'], '1.234,56': ['.', ','], '1 234,56': [' ', ','], "1'234.56": ["'", '.'] }

export function numeroTexto(n, decimales = 0, formato = pref.formato_numero) {
  const [miles, dec] = SEPARADORES[formato] || SEPARADORES['1,234.56']
  const base = new Intl.NumberFormat('en-US', { minimumFractionDigits: decimales, maximumFractionDigits: decimales }).format(Number(n))
  return base.replace(/[,.]/g, (c) => (c === ',' ? miles : dec))
}

export function horaTexto(fecha, formato = pref.formato_hora) {
  const h = fecha.getHours(), mi = dos(fecha.getMinutes())
  if (formato === '24') return `${dos(h)}:${mi}`
  return `${h % 12 || 12}:${mi} ${h < 12 ? 'AM' : 'PM'}`
}
