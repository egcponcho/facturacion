// Ventanas y paneles abiertos, en orden. Esc cierra solo la capa de más
// arriba (p. ej. la confirmación sobre un panel), no todas a la vez.
const abiertas = []

export function abrirCapa() {
  const capa = Symbol('capa')
  abiertas.push(capa)
  return capa
}
export function cerrarCapa(capa) {
  const i = abiertas.indexOf(capa)
  if (i >= 0) abiertas.splice(i, 1)
}
export const esLaDeArriba = (capa) => abiertas.at(-1) === capa
