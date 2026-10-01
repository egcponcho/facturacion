import { t } from '../i18n/index.js'
import { computed, reactive, watch } from 'vue'

// Orden y paginación en el navegador para tablas con todos los datos a mano.
// `fuente` es un ref/computed con las filas; `valores` permite ordenar por un
// dato calculado ({ columna: (fila) => valor }).
export function useTabla(fuente, { porPagina = 15, orden = '', valores = {} } = {}) {
  const estado = reactive({ pagina: 1, porPagina, orden })

  const comparar = (a, b) => {
    if (a === b) return 0
    if (a === null || a === undefined || a === '') return 1
    if (b === null || b === undefined || b === '') return -1
    if (typeof a === 'number' && typeof b === 'number') return a - b
    return String(a).localeCompare(String(b), 'en', { numeric: true, sensitivity: 'base' })
  }

  const ordenadas = computed(() => {
    const lista = [...(fuente.value || [])]
    const [campo, dir] = estado.orden.split(':')
    if (!campo) return lista
    const valor = valores[campo] || ((f) => f[campo])
    lista.sort((x, y) => {
      const r = comparar(valor(x), valor(y))
      // Los vacíos siempre al final, sin importar la dirección
      const vx = valor(x)
      const vy = valor(y)
      if (vx === null || vx === undefined || vx === '' || vy === null || vy === undefined || vy === '') return r
      return dir === 'desc' ? -r : r
    })
    return lista
  })
  const total = computed(() => ordenadas.value.length)
  const filas = computed(() => ordenadas.value.slice((estado.pagina - 1) * estado.porPagina, estado.pagina * estado.porPagina))

  watch([total, () => estado.porPagina], () => {
    const max = Math.max(1, Math.ceil(total.value / estado.porPagina))
    if (estado.pagina > max) estado.pagina = max
  })

  function ordenar(campo) {
    const [actual, dir] = estado.orden.split(':')
    estado.orden = actual === campo ? (dir === 'asc' ? `${campo}:desc` : '') : `${campo}:asc`
    estado.pagina = 1
  }

  return { estado, filas, total, ordenadas, ordenar }
}

// Para listas paginadas en el servidor: alterna "campo:asc" → "campo:desc" → sin orden
export function siguienteOrden(actual, campo) {
  const [c, dir] = (actual || '').split(':')
  return c === campo ? (dir === 'asc' ? `${campo}:desc` : '') : `${campo}:asc`
}
