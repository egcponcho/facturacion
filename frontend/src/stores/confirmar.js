import { reactive } from 'vue'
import { t } from '@/i18n/index.js'

// Diálogo de confirmación de toda la aplicación (componentes/Confirmacion.vue,
// montado una vez en App.vue). Reemplaza a window.confirm: mismo aspecto que
// el resto de las ventanas, botón con el nombre de la acción y, si la acción
// destruye algo, en rojo. Devuelve una promesa con true o false.
export const dialogo = reactive({ abierto: false, titulo: '', texto: '', boton: '', peligro: false, resolver: null })

export function confirmar(texto, { titulo = t('Confirm'), boton = t('Confirm'), peligro = false } = {}) {
  if (dialogo.resolver) dialogo.resolver(false) // una pregunta nueva descarta la anterior
  return new Promise((resolve) => Object.assign(dialogo, { abierto: true, titulo, texto, boton, peligro, resolver: resolve }))
}

export function responder(si) {
  const resolver = dialogo.resolver
  Object.assign(dialogo, { abierto: false, resolver: null })
  resolver?.(si)
}
