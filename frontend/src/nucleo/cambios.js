// Canal de cambios del servidor (backend app/core/cambios.py).
//
// Una sola conexión (Server-Sent Events) por pestaña avisa qué tablas
// cambiaron en la organización. Con eso:
// - lo que la pestaña ya tiene guardado (nucleo/api.js) se usa sin volver a
//   pedirlo mientras no cambie ninguna de sus tablas;
// - una pantalla abierta (alCambiar) vuelve a pedir sus datos solo cuando
//   cambió algo suyo, sin consultar cada tanto.
// Si el canal se corta, todo lo guardado se vuelve a validar con el servidor
// (pedido condicional: 304 si no cambió), así que nunca se muestra algo viejo
// por haber perdido un aviso.
import { onBeforeUnmount, onMounted } from 'vue'
import { entradasDe, invalidar, invalidarTodo, marcarCanal } from './api'

let fuente = null
const oyentes = new Set()

function avisar(urls) {
  for (const o of oyentes) o(urls)
}

export function abrirCanal() {
  if (fuente || typeof EventSource === 'undefined') return
  fuente = new EventSource('/api/cambios')
  fuente.onopen = () => {
    // Lo que cambió mientras no había canal no llegó como aviso: se revalida
    invalidarTodo()
    marcarCanal(true)
    avisar(null)
  }
  fuente.onmessage = (e) => {
    let tablas = []
    try {
      tablas = JSON.parse(e.data).tablas || []
    } catch {
      return
    }
    avisar(invalidar(tablas))
  }
  fuente.onerror = () => {
    // El navegador reintenta solo; hasta entonces nada guardado se da por vigente
    marcarCanal(false)
    invalidarTodo()
  }
}

export function cerrarCanal() {
  if (fuente) fuente.close()
  fuente = null
  marcarCanal(false)
  invalidarTodo()
}

// La pantalla vuelve a pedir sus datos cuando cambia algo de lo que pidió a
// estas rutas de la API (p. ej. ['/ordenes']). Espera a que la pestaña esté a
// la vista y junta varios avisos seguidos en una sola recarga.
export function alCambiar(recargar, rutas) {
  let espera = null
  let pendiente = false
  const correr = () => {
    espera = null
    if (document.hidden) {
      pendiente = true
      return
    }
    pendiente = false
    recargar()
  }
  const oyente = (urls) => {
    // urls null: el canal se (re)abrió y todo se revalida
    const toca = urls === null || urls.some((u) => rutas.some((r) => u.startsWith(`/api${r}`)))
    if (!toca || (urls === null && !entradasDe(rutas).length)) return
    clearTimeout(espera)
    espera = setTimeout(correr, 300)
  }
  const alVolver = () => {
    if (!document.hidden && pendiente) correr()
  }
  onMounted(() => {
    oyentes.add(oyente)
    document.addEventListener('visibilitychange', alVolver)
  })
  onBeforeUnmount(() => {
    oyentes.delete(oyente)
    document.removeEventListener('visibilitychange', alVolver)
    clearTimeout(espera)
  })
}
