// Búsqueda inteligente, la misma en todo el sistema (selects, filtros y
// buscadores de tablas). El servidor aplica las mismas reglas (common.filtro_texto).
// - Ignora mayúsculas, acentos y espacios de más.
// - Los términos se separan por espacios, comas, punto y coma, barras o saltos
//   de línea, y pueden ir en cualquier orden y estar en atributos distintos:
//   "vietnam cat", "cat vietnam", "viet lai" encuentran "Vietnam | Ho Chi Minh | Cat Lai".
// - Todas las palabras deben estar; varios códigos (términos con números)
//   traen cualquiera de ellos (pegar "4400003904 4400003850" trae las dos).
// - En los códigos se ignoran separadores: 4400-003904 = 4400003904.

export const normal = (v) => String(v ?? '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase()
export const compacto = (v) => normal(v).replace(/[\s.\-_/|]/g, '')
export const terminos = (q) => [...new Set(normal(q).split(/[\s,;|]+/).filter(Boolean))]

// Prepara la búsqueda una vez y devuelve una función que dice si un registro
// coincide. `campos`: texto o lista de textos del registro.
export function buscador(q) {
  const ts = terminos(q)
  if (!ts.length) return () => true
  const algunos = ts.length > 1 && ts.every((p) => /\d/.test(p))
  const tc = ts.map(compacto)
  return (campos) => {
    const lista = Array.isArray(campos) ? campos : [campos]
    const heno = normal(lista.filter((x) => x !== null && x !== undefined).join(' | '))
    const hc = compacto(heno)
    const ok = (p, i) => heno.includes(p) || (tc[i] && hc.includes(tc[i]))
    return algunos ? ts.some(ok) : ts.every(ok)
  }
}

// Filtra una lista con la búsqueda; `campos(x)` da los textos de cada registro.
export function filtrar(lista, q, campos) {
  const coincide = buscador(q)
  return (lista || []).filter((x) => coincide(campos(x)))
}

// Para ordenar: 0 si algún término empieza un campo principal (código, nombre)
export function relevancia(q, principales) {
  const ts = terminos(q)
  return ts.some((p) => principales.some((c) => normal(c).startsWith(p))) ? 0 : 1
}
