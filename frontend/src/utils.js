import { reactive } from 'vue'

const numero = (d) => new Intl.NumberFormat('es-SV', { minimumFractionDigits: d, maximumFractionDigits: d })

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
  return f.toLocaleString('es-SV', { dateStyle: 'short', timeStyle: 'short' })
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
  if (unidad === 'PAR') return n === 1 ? 'par' : 'pares'
  if (unidad === 'CJ') return n === 1 ? 'caja prepack' : 'cajas prepack'
  return n === 1 ? 'unidad' : 'unidades'
}

// Dos liberaciones de dos equipos: comercial (P/C) y logística (304/300/301).
// Sin liberación comercial no hay logística; se factura solo con C y 300/301.
export const COMERCIAL = {
  C: ['Comercial C', 'ok', 'Liberada por comercial'],
  P: ['Comercial P', 'aviso', 'Pendiente de liberación comercial: logística no puede liberar'],
}
export const LIBERACION = {
  300: ['300 · Liberada', 'ok', 'Liberada por logística'],
  301: ['301 · Liberada con cambios', 'info', 'Liberada por logística; la OC cambió después'],
  304: ['304 · No liberada', 'aviso', 'Sin liberación logística: no se puede facturar'],
}

export function diasTxt(n) {
  if (n === null || n === undefined) return '—'
  if (n === 0) return 'hoy'
  return n > 0 ? `en ${n} d` : `hace ${-n} d`
}

export function cantTxt(n, unidad) {
  return `${fmtNum(n)} ${unidadTxt(unidad, Number(n))}`
}

// {PAR: {cantidad: 10}, UN: {cantidad: 5}} -> "10 pares y 5 unidades"
export function porUnidadTxt(obj, campo = 'cantidad') {
  const partes = Object.entries(obj || {})
    .filter(([, v]) => (campo ? v[campo] : v) > 0)
    .map(([u, v]) => cantTxt(campo ? v[campo] : v, u))
  if (!partes.length) return '—'
  return partes.length > 1 ? `${partes.slice(0, -1).join(', ')} y ${partes.at(-1)}` : partes[0]
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
  crear: 'Creó el documento',
  agregar_lineas: 'Agregó posiciones',
  editar_lineas: 'Editó líneas',
  quitar_lineas: 'Quitó líneas',
  editar_cabecera: 'Editó la cabecera',
  finalizar: 'Finalizó',
  reabrir: 'Reabrió',
  cancelar: 'Canceló',
  adjuntar_archivo: 'Adjuntó un archivo',
  agregar: 'Agregó pendientes',
  dividir: 'Dividió una fila',
  mover: 'Movió cantidades',
  quitar: 'Quitó cantidades',
  mover_cajas: 'Movió cajas',
  aplicar_plantilla: 'Aplicó plantilla',
  caja_sobrante: 'Empacó sobrantes',
  crear_caja: 'Creó cajas',
  editar_cajas: 'Editó cajas',
  desempacar: 'Desempacó cajas',
  recepcion: 'Registró recepción',
  asignar_unidad: 'Asignó a unidad de carga',
  confirmar_unidad: 'Confirmó en unidad de carga',
  quitar_unidad: 'Quitó de la unidad de carga',
  editar: 'Editó',
  evento: 'Registró evento',
  agregar_unidad: 'Agregó unidad',
  editar_unidad: 'Editó unidad',
  eliminar_unidad: 'Eliminó unidad',
}
