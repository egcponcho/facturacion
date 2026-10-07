import { t } from '../i18n/index.js'
/* Presentación de la clasificación (no clasifica nada: eso lo hace el motor
del servidor en /clasificacion/sesion). Formato de códigos, la composición
como filas editables y las etiquetas de estados y fuentes. */

export const norm = (s) => (s == null ? '' : String(s)).toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '')
export const digits = (s) => (s == null ? '' : String(s)).replace(/\D/g, '')

// 640419 -> 6404.19; 6404199000 -> 6404.19.90.00 (todos los dígitos, nunca se recorta)
export function fmtCode(c) {
  const d = digits(c)
  if (d.length <= 4) return d
  let o = `${d.slice(0, 4)}.${d.slice(4, 6)}`
  for (let i = 6; i < d.length; i += 2) o += `.${d.slice(i, i + 2)}`
  return o
}

// Código nacional con los dígitos que lleva el país (lo que falta se ve como _)
export function fmtPais(cod, n) {
  const d = digits(cod)
  if (!d) return ''
  const s = d + '_'.repeat(Math.max(0, (n || 0) - d.length))
  let o = `${s.slice(0, 4)}.${s.slice(4, 6)}`
  for (let i = 6; i < s.length; i += 2) o += `.${s.slice(i, i + 2)}`
  return o
}

// La composición de una parte como filas material | % (lo que se edita) y de vuelta a texto
export function textoDesdeFilas(rows) {
  return rows.filter((r) => String(r.m || '').trim()).map((r) => (r.pct !== '' && r.pct != null ? `${r.pct}% ` : '') + String(r.m).trim()).join(', ')
}
export function totalFilas(rows) {
  return Math.round(rows.reduce((a, r) => a + (parseFloat(String(r.pct).replace(',', '.')) || 0), 0) * 10) / 10
}

// Estado de la línea nacional de cada país (lo calcula el servidor). Solo hay
// líneas publicadas por una fuente oficial; el historial de la empresa solo ayuda a elegir
export const EST_PAIS = {
  ok: t('Official national line'),
  historial: t('Suggested by your company history: confirm it'),
  elegir: t('Needs data or a choice'),
  pendiente: t('Official national tariff data not available'),
  invalido: t('Invalid code'),
  sin_codigo: t('No code'),
}
// Estados con un código nacional oficial elegido. «historial» es solo una
// sugerencia del historial de la empresa: la confirma una persona
export const PAIS_LISTO = ['ok']

// De dónde salió la sugerencia
export const FUENTES = { regla: t('Harmonized System rules'), historial: t('Your history: product already classified'), texto: t('Official tariff text') }
