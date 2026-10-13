import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { api } from '@/nucleo/api'

// Edición exclusiva: mientras esta pantalla puede editar el documento, toma el
// permiso de edición y lo renueva; si otra persona lo tiene, el detalle llega
// con `edicion` (quién y desde cuándo) y la pantalla queda en solo lectura
// hasta que se libere. Se suelta al salir, al ocultar la pestaña un rato
// (vence solo en el servidor) o tras INACTIVO sin uso.
//   entidad: 'factura' | 'packing_list' | 'embarque' | 'producto'
//   id: () => id del documento
//   estado: () => ({ editable, edicion }) del detalle cargado
//   recargar: () => vuelve a pedir el detalle
const RENOVAR = 30000
const ESPERAR = 15000
const INACTIVO = 10 * 60 * 1000

export function useEdicion(entidad, id, estado, recargar) {
  const propio = ref(false)
  const pausado = ref(false)
  let temporizador = null
  let ultimoUso = Date.now()

  let tomadoId = null // documento del que se tiene el permiso
  const url = (doc = id()) => `/edicion/${entidad}/${doc}`
  const limpiar = () => {
    clearInterval(temporizador)
    temporizador = null
  }

  async function tomar() {
    try {
      await api.post(url())
      tomadoId = id()
      propio.value = true
      pausado.value = false
      limpiar()
      temporizador = setInterval(renovar, RENOVAR)
    } catch (e) {
      propio.value = false
      if (e.codigo === 'en_edicion') await recargar()
    }
  }

  async function renovar() {
    if (document.visibilityState !== 'visible') return
    if (Date.now() - ultimoUso > INACTIVO) {
      await soltar()
      pausado.value = true
      return
    }
    await tomar()
  }

  async function soltar(keepalive = false) {
    limpiar()
    if (!propio.value || !tomadoId) return
    propio.value = false
    const doc = tomadoId
    tomadoId = null
    // keepalive: el aviso sale aunque la pestaña se esté cerrando
    fetch(`/api${url(doc)}`, { method: 'DELETE', credentials: 'same-origin', keepalive, headers: { 'X-Requested-With': 'fetch' } }).catch(() => {})
  }

  // Quien ve en solo lectura revisa cada tanto si ya quedó libre
  async function esperar() {
    try {
      const r = await api.get(url())
      if (!r.editando) {
        limpiar()
        await recargar()
      }
    } catch {
      /* sin red: se reintenta en la siguiente vuelta */
    }
  }

  watch(() => [id(), estado().editable, !!estado().edicion], ([actual, editable, ocupado]) => {
    if (!actual) return
    if (tomadoId && tomadoId !== actual) soltar() // pasó a otro documento
    if (ocupado) {
      propio.value = false
      limpiar()
      temporizador = setInterval(esperar, ESPERAR)
    } else if (editable && !propio.value && !pausado.value) {
      tomar()
    } else if (!editable && propio.value) {
      soltar()
    }
  }, { immediate: true })

  const usar = () => (ultimoUso = Date.now())
  const ocupada = () => recargar()
  const alVolver = () => {
    if (document.visibilityState === 'visible' && propio.value) tomar()
  }
  const alCerrar = () => soltar(true)
  onMounted(() => {
    for (const ev of ['keydown', 'pointerdown']) window.addEventListener(ev, usar, { passive: true })
    window.addEventListener('edicion-ocupada', ocupada)
    document.addEventListener('visibilitychange', alVolver)
    window.addEventListener('pagehide', alCerrar)
  })
  onBeforeUnmount(() => {
    for (const ev of ['keydown', 'pointerdown']) window.removeEventListener(ev, usar)
    window.removeEventListener('edicion-ocupada', ocupada)
    document.removeEventListener('visibilitychange', alVolver)
    window.removeEventListener('pagehide', alCerrar)
    soltar(true)
  })

  // Tras pausar por inactividad, la persona decide seguir editando
  const continuar = async () => {
    pausado.value = false
    ultimoUso = Date.now()
    await recargar()
    await tomar()
  }

  return { propio, pausado, continuar }
}
