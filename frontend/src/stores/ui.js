import { t, tx } from '../i18n/index.js'
import { reactive } from 'vue'

export const ui = reactive({ toasts: [], guardado: '', navegando: false })
let siguiente = 0

export function avisar(mensaje, tipo = 'ok', detalle = null, ms = tipo === 'error' && detalle?.length ? 0 : tipo === 'error' ? 8000 : 4500) {
  const t = { id: ++siguiente, mensaje: tx(mensaje), tipo, detalle: Array.isArray(detalle) ? detalle.map(tx) : detalle }
  ui.toasts.push(t)
  if (ms) setTimeout(() => cerrarAviso(t.id), ms)
}

export function cerrarAviso(id) {
  const i = ui.toasts.findIndex((t) => t.id === id)
  if (i >= 0) ui.toasts.splice(i, 1)
}

export function textoDetalle(d) {
  if (!d) return ''
  if (typeof d === 'string') return d
  return d.mensaje || d.ref || JSON.stringify(d)
}

export function errorApi(e) {
  const detalle = Array.isArray(e?.detalle) ? e.detalle.map(textoDetalle).filter(Boolean).map(tx) : null
  avisar(tx(e?.message) || t('An unexpected error occurred.'), 'error', detalle?.length ? detalle.slice(0, 8) : null,
    detalle?.length ? 12000 : 7000)
}

// Indicador global "Guardando… / Cambios guardados"
let temporizador
export async function guardando(promesa) {
  ui.guardado = 'guardando'
  clearTimeout(temporizador)
  try {
    const r = await promesa
    ui.guardado = 'guardado'
    temporizador = setTimeout(() => (ui.guardado = ''), 3000)
    return r
  } catch (e) {
    ui.guardado = 'error'
    throw e
  }
}
