import { reactive } from 'vue'

const numero = (d) => new Intl.NumberFormat('en-US', { minimumFractionDigits: d, maximumFractionDigits: d })

export function fmtNum(n, decimales = 0) {
  if (n === null || n === undefined || n === '') return '—'
  return numero(decimales).format(Number(n))
}

export function fmtMoneda(n, moneda = 'USD') {
  if (n === null || n === undefined) return '—'
  return `${moneda} ${fmtNum(n, 2)}`
}

export function fmtFecha(valor) {
  if (!valor) return '—'
  const [a, m, d] = String(valor).slice(0, 10).split('-')
  return `${d}/${m}/${a}`
}

export function fmtFechaHora(valor) {
  if (!valor) return '—'
  const f = new Date(String(valor).endsWith('Z') ? valor : `${valor}Z`)
  return f.toLocaleString('en-GB', { dateStyle: 'short', timeStyle: 'short' })
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
  if (unidad === 'PAR') return n === 1 ? 'pair' : 'pairs'
  if (unidad === 'CJ') return n === 1 ? 'prepack carton' : 'prepack cartons'
  return n === 1 ? 'unit' : 'units'
}

// Dos liberaciones de dos equipos: comercial (P/C) y logística (304/300/301).
// Sin liberación comercial no hay logística; se factura solo con C y 300/301.
export const COMERCIAL = {
  C: ['Commercial C', 'ok', 'Released by commercial'],
  P: ['Commercial P', 'aviso', 'Pending commercial release: logistics cannot release'],
}
export const LIBERACION = {
  300: ['300 · Released', 'ok', 'Released by logistics'],
  301: ['301 · Released with changes', 'info', 'Released by logistics; the PO changed afterwards'],
  304: ['304 · Not released', 'aviso', 'No logistics release: it cannot be invoiced'],
}

export function diasTxt(n) {
  if (n === null || n === undefined) return '—'
  if (n === 0) return 'today'
  return n > 0 ? `in ${n} d` : `${-n} d ago`
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
  return partes.length > 1 ? `${partes.slice(0, -1).join(', ')} and ${partes.at(-1)}` : partes[0]
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
  crear: 'Created the document',
  agregar_lineas: 'Added order lines',
  editar_lineas: 'Edited lines',
  quitar_lineas: 'Removed lines',
  editar_cabecera: 'Edited the header',
  finalizar: 'Finalized',
  reabrir: 'Reopened',
  cancelar: 'Cancelled',
  adjuntar_archivo: 'Attached a file',
  agregar: 'Added pending quantities',
  dividir: 'Split a row',
  mover: 'Moved quantities',
  quitar: 'Removed quantities',
  mover_cajas: 'Moved cartons',
  aplicar_plantilla: 'Applied a template',
  caja_sobrante: 'Packed leftovers',
  crear_caja: 'Created cartons',
  editar_cajas: 'Edited cartons',
  desempacar: 'Unpacked cartons',
  recepcion: 'Recorded receipt',
  asignar_unidad: 'Assigned to a load unit',
  confirmar_unidad: 'Confirmed in a load unit',
  quitar_unidad: 'Removed from the load unit',
  editar: 'Edited',
  evento: 'Recorded an event',
  agregar_unidad: 'Added a unit',
  editar_unidad: 'Edited a unit',
  eliminar_unidad: 'Deleted a unit',
  pallet: 'Palletized',
  empaque: 'Changed the packing',
}
