import { t } from './i18n/index.js'
import { fechaTexto, horaTexto, numeroTexto, pref } from './stores/preferencias'
import { reactive } from 'vue'
import { UNIDADES } from './unidades.js'

// Números, fechas y horas siguen las preferencias del perfil (separadores,
// formato de fecha MM/DD/YYYY por defecto y reloj de 12 o 24 horas)
export function fmtNum(n, decimales = 0) {
  if (n === null || n === undefined || n === '') return '—'
  return numeroTexto(n, decimales)
}

export function fmtMoneda(n, moneda = 'USD') {
  if (n === null || n === undefined) return '—'
  return `${moneda} ${fmtNum(n, 2)}`
}

export function fmtFecha(valor) {
  if (!valor) return '—'
  return fechaTexto(valor) || String(valor)
}

export function fmtDiaMes(valor) {
  if (!valor) return '—'
  const f = fechaTexto(valor)
  switch (pref.formato_fecha) {
    case 'YYYY-MM-DD': return f.slice(5)
    case 'DD-MMM-YYYY': return f.slice(0, 6)
    case 'MMM DD, YYYY': return f.slice(0, 6)
    default: return f.slice(0, 5)
  }
}

export function fmtFechaHora(valor) {
  if (!valor) return '—'
  const f = new Date(String(valor).endsWith('Z') ? valor : `${valor}Z`)
  const iso = `${f.getFullYear()}-${String(f.getMonth() + 1).padStart(2, '0')}-${String(f.getDate()).padStart(2, '0')}`
  return `${fechaTexto(iso)} ${horaTexto(f)}`
}

export function plural(n, singular, plural) {
  return `${fmtNum(n)} ${Number(n) === 1 ? singular : plural}`
}

// Fechas que el usuario captura en su hora local (eventos): sin conversión de zona
export function fmtFechaHoraLocal(valor) {
  if (!valor) return '—'
  const [f, h = ''] = String(valor).split('T')
  return `${fmtFecha(f)} ${h.slice(0, 5)}`.trim()
}

export function unidadTxt(unidad, n) {
  const u = UNIDADES[unidad] || UNIDADES.UN
  return n === 1 ? u[0] : u[1]
}

// Dos liberaciones de dos equipos: comercial (P/C) y logística (304/300/301).
// Sin liberación comercial no hay logística; se factura solo con C y 300/301.
export const COMERCIAL = {
  C: [t('Commercial released'), 'ok', t('Released by commercial')],
  P: [t('Commercial pending'), 'aviso', t('Pending commercial release: logistics cannot release')],
}
// Frente a la fecha requerida en tienda (la holgura mínima se configura en el servidor)
export const TIEMPO = {
  A_TIEMPO: [t('On time'), 'ok'],
  JUSTO: [t('At risk'), 'aviso'],
  ATRASO: [t('Late'), 'error'],
}
export const LIBERACION = {
  300: [t('Released'), 'ok', t('Released by logistics')],
  301: [t('Released with changes'), 'info', t('Released by logistics; the PO changed afterwards')],
  304: [t('Not released'), 'aviso', t('No logistics release: it cannot be invoiced')],
}

export function diasTxt(n) {
  if (n === null || n === undefined) return '—'
  if (n === 0) return t('today')
  return n > 0 ? t('in {0} d', [n]) : t('{0} d ago', [-n])
}

export function cantTxt(n, unidad) {
  return `${fmtNum(n)} ${unidadTxt(unidad, Number(n))}`
}

// {PAR: {cantidad: 10}, UN: {cantidad: 5}} -> "10 pairs and 5 units"
export function porUnidadTxt(obj, campo = 'cantidad') {
  const partes = Object.entries(obj || {})
    .filter(([, v]) => (campo ? v[campo] : v) > 0)
    .map(([u, v]) => cantTxt(campo ? v[campo] : v, u))
  if (!partes.length) return '—'
  return partes.length > 1 ? t('{0} and {1}', [partes.slice(0, -1).join(', '), partes.at(-1)]) : partes[0]
}

export function pct(parte, total) {
  if (!total) return 0
  return Math.min(100, Math.round((parte * 100) / total))
}

// Selección múltiple reutilizable para todas las tablas
export function useSeleccion() {
  const ids = reactive(new Set())
  return {
    ids,
    tiene: (id) => ids.has(id),
    alternar: (id) => (ids.has(id) ? ids.delete(id) : ids.add(id)),
    todos: (lista) => lista.length > 0 && lista.every((i) => ids.has(i)),
    alternarTodos(lista) {
      if (lista.length && lista.every((i) => ids.has(i))) lista.forEach((i) => ids.delete(i))
      else lista.forEach((i) => ids.add(i))
    },
    limpiar: () => ids.clear(),
    lista: () => [...ids],
    podar(validos) {
      const v = new Set(validos)
      for (const i of [...ids]) if (!v.has(i)) ids.delete(i)
    },
  }
}

export const ACCIONES = {
  crear: t('Created the document'),
  agregar_lineas: t('Added order lines'),
  editar_lineas: t('Edited lines'),
  quitar_lineas: t('Removed lines'),
  editar_cabecera: t('Edited the header'),
  finalizar: t('Finalized'),
  reabrir: t('Reopened'),
  cancelar: t('Cancelled'),
  adjuntar_archivo: t('Attached a file'),
  agregar: t('Added pending quantities'),
  dividir: t('Split a row'),
  mover: t('Moved quantities'),
  quitar: t('Removed quantities'),
  mover_cajas: t('Moved cartons'),
  aplicar_plantilla: t('Applied a template'),
  caja_sobrante: t('Packed leftovers'),
  crear_caja: t('Created cartons'),
  editar_cajas: t('Edited cartons'),
  desempacar: t('Unpacked cartons'),
  recepcion: t('Recorded receipt'),
  asignar_unidad: t('Assigned to a load unit'),
  confirmar_unidad: t('Confirmed in a load unit'),
  quitar_unidad: t('Removed from the load unit'),
  editar: t('Edited'),
  evento: t('Recorded an event'),
  agregar_unidad: t('Added a unit'),
  editar_unidad: t('Edited a unit'),
  eliminar_unidad: t('Deleted a unit'),
  pallet: t('Palletized'),
  empaque: t('Changed the packing'),
}

// Foto de perfil: se recorta al centro y se reduce en el navegador antes de enviarla
export function reducirImagen(archivo, lado = 256) {
  return new Promise((resolve, reject) => {
    if (!archivo || !/^image\/(png|jpeg|webp)$/.test(archivo.type)) return reject(new Error(t('Use a PNG, JPEG or WebP image.')))
    const img = new Image()
    img.onload = () => {
      const c = document.createElement('canvas')
      c.width = c.height = lado
      const m = Math.min(img.width, img.height)
      c.getContext('2d').drawImage(img, (img.width - m) / 2, (img.height - m) / 2, m, m, 0, 0, lado, lado)
      URL.revokeObjectURL(img.src)
      resolve(c.toDataURL('image/jpeg', 0.85))
    }
    img.onerror = () => reject(new Error(t('The image could not be read.')))
    img.src = URL.createObjectURL(archivo)
  })
}
